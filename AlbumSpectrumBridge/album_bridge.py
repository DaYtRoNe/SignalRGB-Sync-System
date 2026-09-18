import asyncio
import colorsys
import hashlib
import io
import sys
import time
import urllib.request
from urllib.parse import urlencode
from pathlib import Path

from PIL import Image
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
from winrt.windows.storage.streams import DataReader


SIGNALRGB_URL = "http://localhost:16034/canvas/event"
SENDER = "AlbumSpectrumBridge"
OUTPUT_IMAGE = Path(__file__).parent / "current_cover.png"
LOG_FILE = Path(__file__).parent / "bridge.log"

POLL_SECONDS = 1.5
RESEND_SECONDS = 15.0


async def read_thumbnail(thumbnail_ref):
    if thumbnail_ref is None:
        return None

    stream = await thumbnail_ref.open_read_async()
    size = int(stream.size)

    if size <= 0:
        return None

    reader = DataReader(stream)
    loaded = await reader.load_async(size)

    if loaded <= 0:
        return None

    data = bytearray(loaded)
    reader.read_bytes(data)
    return bytes(data)


def rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def color_distance(a, b):
    return (
        (a[0] - b[0]) ** 2
        + (a[1] - b[1]) ** 2
        + (a[2] - b[2]) ** 2
    ) ** 0.5


def enhance_for_led(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    # Slightly improve LED visibility without completely changing the artwork.
    s = min(1.0, max(0.28, s * 1.18))
    v = min(1.0, max(0.42, v * 1.06))

    rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)

    return (
        round(rr * 255),
        round(gg * 255),
        round(bb * 255),
    )


def extract_dominant_colors(image, count=3):
    img = image.convert("RGB")
    img.thumbnail((180, 180))

    quantized = img.quantize(
        colors=20,
        method=Image.Quantize.MEDIANCUT
    )

    palette = quantized.getpalette()
    color_counts = quantized.getcolors()

    if not color_counts:
        return ["#FF1493", "#A832FF", "#168CFF"]

    candidates = []

    for pixel_count, palette_index in color_counts:
        offset = palette_index * 3
        rgb = tuple(palette[offset:offset + 3])

        r, g, b = [value / 255.0 for value in rgb]
        _, saturation, value = colorsys.rgb_to_hsv(r, g, b)

        # Ignore colors that are too dark to be useful on RGB LEDs.
        if value < 0.10:
            continue

        # Ignore near-white / grey colors unless there are very few alternatives.
        if saturation < 0.10 and value > 0.70:
            continue

        # Prefer colors that are common in the artwork, with a small
        # preference toward more saturated colors.
        score = pixel_count * (0.55 + saturation * 0.45)
        candidates.append((score, rgb))

    candidates.sort(key=lambda item: item[0], reverse=True)

    selected = []

    # First pass: choose visibly different colors.
    for _, rgb in candidates:
        if all(color_distance(rgb, existing) >= 50 for existing in selected):
            selected.append(rgb)

        if len(selected) == count:
            break

    # Second pass: fill remaining slots with the strongest unused colors.
    if len(selected) < count:
        for _, rgb in candidates:
            if rgb not in selected:
                selected.append(rgb)

            if len(selected) == count:
                break

    fallback = [
        (255, 20, 147),
        (168, 50, 255),
        (22, 140, 255),
    ]

    while len(selected) < count:
        selected.append(fallback[len(selected)])

    selected = [enhance_for_led(c) for c in selected[:count]]
    return [rgb_to_hex(c) for c in selected]


def send_palette(colors):
    # SignalRGB event format that we already verified works:
    # palette|00ff88|00aaff|9d4edd
    clean = [c.replace("#", "").lower() for c in colors[:3]]
    event = "palette|" + "|".join(clean)

    query = urlencode({
        "sender": SENDER,
        "event": event,
    })

    url = f"{SIGNALRGB_URL}?{query}"

    request = urllib.request.Request(
        url,
        data=b"",
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=3) as response:
        response.read()


async def main():
    print()
    print("======================================")
    print("      Album Spectrum Live Bridge")
    print("======================================")
    print("Publisher: Eshan")
    print()
    print("Keep SignalRGB open with Album Spectrum selected.")
    print("Press Ctrl+C to stop.")
    print()

    manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()

    last_track_key = None
    last_cover_hash = None
    last_colors = None
    last_sent_time = 0.0

    while True:
        try:
            session = manager.get_current_session()

            if session is None:
                print("No active media session. Waiting...")
                await asyncio.sleep(POLL_SECONDS)
                continue

            props = await session.try_get_media_properties_async()

            title = props.title or "Unknown Title"
            artist = props.artist or "Unknown Artist"
            album = props.album_title or "Unknown Album"
            track_key = f"{title}|{artist}|{album}"

            if props.thumbnail is None:
                await asyncio.sleep(POLL_SECONDS)
                continue

            image_bytes = await read_thumbnail(props.thumbnail)

            if not image_bytes:
                await asyncio.sleep(POLL_SECONDS)
                continue

            cover_hash = hashlib.md5(image_bytes).hexdigest()

            track_changed = (
                track_key != last_track_key
                or cover_hash != last_cover_hash
            )

            if track_changed:
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                image.save(OUTPUT_IMAGE, format="PNG")

                colors = extract_dominant_colors(image, 3)

                print("--------------------------------------")
                print(f"Title  : {title}")
                print(f"Artist : {artist}")
                print(f"Album  : {album}")
                print(f"Colors : {' -> '.join(colors)}")

                last_track_key = track_key
                last_cover_hash = cover_hash
                last_colors = colors

            now = time.monotonic()

            # Send immediately on a song change, and periodically re-send.
            # The periodic resend means the palette also recovers if SignalRGB
            # or the effect was restarted while the same song is still playing.
            should_send = (
                last_colors is not None
                and (
                    track_changed
                    or (now - last_sent_time) >= RESEND_SECONDS
                )
            )

            if should_send:
                try:
                    send_palette(last_colors)
                    last_sent_time = now

                    if track_changed:
                        print("SignalRGB palette updated.")
                except Exception as e:
                    print(f"SignalRGB send failed: {e}")

            await asyncio.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            print("\nBridge stopped.")
            break

        except Exception as e:
            print(f"Bridge error: {e}")
            await asyncio.sleep(2)


if __name__ == "__main__":
    # When started by pythonw.exe (no console, e.g. from the scheduled task)
    # there is no stdout, so send all output to a log file instead.
    if sys.stdout is None or sys.stderr is None:
        log = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log

    asyncio.run(main())
