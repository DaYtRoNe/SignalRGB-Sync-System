"""
Mixes the audio of several Sonar channels into one virtual playback device.

    Sonar - Media  (loopback) --+
                                +--> sum --> "CABLE Input" (VB-Audio Virtual Cable)
    Sonar - Aux    (loopback) --+

SignalRGB then captures the cable and hears Media + Aux no matter which
speakers / DAC Sonar is playing to, while Game and Chat stay out of it.

The loopback taps the raw audio apps send into each Sonar channel, before
Sonar applies its presets, so Immersion / Bass Boost are unaffected.

Used by rgb_controller.py (runs in a background thread); can also be run on
its own for testing:  py audio_mixer.py
"""

import queue
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio


SOURCE_CHANNELS = ["Media", "Aux"]                 # Sonar channels to mix
OUTPUT_DEVICE_MATCH = "CABLE Input"                # substring of the virtual cable's playback device name
FRAMES_PER_BUFFER = 960                            # 10 ms at 96 kHz / 20 ms at 48 kHz
MIX_GAIN = 1.0                                     # 1.0 = plain sum, clipped to [-1, 1]


def _wasapi_devices(pa):
    api = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)

        if info["hostApi"] == api:
            yield info


def find_loopback(pa, channel):
    """Loopback (capturable) side of the 'SteelSeries Sonar - <channel>' playback device."""
    for info in _wasapi_devices(pa):
        if info.get("isLoopbackDevice") and info["name"].startswith(f"SteelSeries Sonar - {channel} "):
            return info

    return None


def find_output(pa, match):
    for info in _wasapi_devices(pa):
        if match.lower() in info["name"].lower() and info["maxOutputChannels"] > 0 and not info.get("isLoopbackDevice"):
            return info

    return None


def _resample(block, src_rate, dst_rate):
    """Linear resampling of a (frames, channels) float32 block. Plenty for visualisation."""
    if src_rate == dst_rate:
        return block

    n_out = int(round(len(block) * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, len(block), endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)

    return np.stack([np.interp(x_new, x_old, block[:, c]) for c in range(block.shape[1])], axis=1).astype(np.float32)


def _to_stereo(block, out_channels):
    """Fold any channel layout down to the output channel count (mono/stereo)."""
    n = block.shape[1]

    if n == out_channels:
        return block

    if n == 1:
        return np.repeat(block, out_channels, axis=1)

    if out_channels == 1:
        return block.mean(axis=1, keepdims=True)

    # multichannel (e.g. 7.1: FL FR C LFE BL BR SL SR) -> stereo: front pair plus the rest at half gain
    stereo = block[:, :2].copy()

    if n > 2:
        rest = block[:, 2:]
        stereo[:, 0] += 0.5 * rest[:, 0::2].sum(axis=1)
        stereo[:, 1] += 0.5 * rest[:, 1::2].sum(axis=1)

    return stereo


class ChannelMixer:
    """Captures SOURCE_CHANNELS via WASAPI loopback and plays their sum to the virtual cable."""

    def __init__(self, log=print):
        self.log = log
        self.pa = None
        self.inputs = []
        self.output = None
        self.buffers = {}          # channel -> queue of float32 (frames, 2) blocks, already at output rate
        self.out_rate = None
        self.out_channels = 2
        self.running = False
        self.level = 0.0           # last output peak, for diagnostics

    # ------------------------------------------------------------------ setup

    def start(self):
        self.pa = pyaudio.PyAudio()
        out_info = find_output(self.pa, OUTPUT_DEVICE_MATCH)

        if out_info is None:
            self.log(f"Mixer  : no playback device matching '{OUTPUT_DEVICE_MATCH}' - mixer disabled")
            self.pa.terminate()
            self.pa = None
            return False

        self.out_rate = int(out_info["defaultSampleRate"])
        self.out_channels = min(2, out_info["maxOutputChannels"])
        sources = []

        for channel in SOURCE_CHANNELS:
            info = find_loopback(self.pa, channel)

            if info is None:
                self.log(f"Mixer  : Sonar - {channel} loopback not found, skipped")
                continue

            self.buffers[channel] = queue.Queue(maxsize=32)
            in_rate = int(info["defaultSampleRate"])
            in_channels = info["maxInputChannels"]     # shared-mode WASAPI needs the device's native count (Sonar = 8)

            stream = self.pa.open(
                format=pyaudio.paFloat32,
                channels=in_channels,
                rate=in_rate,
                input=True,
                input_device_index=info["index"],
                frames_per_buffer=FRAMES_PER_BUFFER,
                stream_callback=self._make_input_callback(channel, in_rate, in_channels),
            )
            self.inputs.append(stream)
            sources.append(f"{channel}@{in_rate}")

        if not self.inputs:
            self.log("Mixer  : no Sonar loopback devices found - mixer disabled")
            self.stop()
            return False

        self.output = self.pa.open(
            format=pyaudio.paFloat32,
            channels=self.out_channels,
            rate=self.out_rate,
            output=True,
            output_device_index=out_info["index"],
            frames_per_buffer=FRAMES_PER_BUFFER,
            stream_callback=self._output_callback,
        )

        self.running = True
        self.log(f"Mixer  : {' + '.join(sources)} -> {out_info['name']} @ {self.out_rate} Hz")
        return True

    def stop(self):
        self.running = False

        for stream in self.inputs + ([self.output] if self.output else []):
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass

        self.inputs = []
        self.output = None

        if self.pa is not None:
            self.pa.terminate()
            self.pa = None

    # -------------------------------------------------------------- callbacks

    def _make_input_callback(self, channel, in_rate, in_channels):
        buf = self.buffers[channel]

        def callback(in_data, frame_count, time_info, status):
            block = np.frombuffer(in_data, dtype=np.float32).reshape(-1, in_channels)
            block = _to_stereo(block, self.out_channels)

            block = _resample(block, in_rate, self.out_rate)

            try:
                buf.put_nowait(block)
            except queue.Full:          # consumer stalled: drop the oldest, keep latency bounded
                try:
                    buf.get_nowait()
                    buf.put_nowait(block)
                except queue.Empty:
                    pass

            return (None, pyaudio.paContinue)

        return callback

    def _output_callback(self, in_data, frame_count, time_info, status):
        mix = np.zeros((frame_count, self.out_channels), dtype=np.float32)

        for channel, buf in self.buffers.items():
            pending = getattr(buf, "_carry", None)
            filled = 0

            while filled < frame_count:
                if pending is None or len(pending) == 0:
                    try:
                        pending = buf.get_nowait()
                    except queue.Empty:
                        break                       # channel silent (no loopback data): contributes zeros

                take = min(len(pending), frame_count - filled)
                mix[filled:filled + take] += pending[:take]
                pending = pending[take:]
                filled += take

            buf._carry = pending if pending is not None and len(pending) else None

        if MIX_GAIN != 1.0:
            mix *= MIX_GAIN

        np.clip(mix, -1.0, 1.0, out=mix)
        self.level = float(np.abs(mix).max()) if frame_count else 0.0

        return (mix.tobytes(), pyaudio.paContinue)


def run_in_thread(log=print):
    """Start the mixer on a daemon thread; returns the ChannelMixer (running or not)."""
    mixer = ChannelMixer(log)
    started = threading.Event()

    def worker():
        if mixer.start():
            started.set()

            while mixer.running:
                time.sleep(1)
        else:
            started.set()

    threading.Thread(target=worker, name="audio-mixer", daemon=True).start()
    started.wait(10)
    return mixer


if __name__ == "__main__":
    m = ChannelMixer()

    if m.start():
        print("Mixing... Ctrl+C to stop")

        try:
            while True:
                time.sleep(1)
                print(f"output peak: {m.level:.3f}")
        except KeyboardInterrupt:
            pass

        m.stop()
