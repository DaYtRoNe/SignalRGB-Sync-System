"""
SignalRGB automation controller.

Watches the SteelSeries Sonar channels (Gaming / Media / Aux) to work out what
you are doing, then:

  GAMING   audio on Sonar-Gaming                     -> Screen Ambience effect
  MOVIE    audio on Sonar-Media from a video player  -> Screen Ambience effect
  BROWSER  audio on Sonar-Media from a browser       -> Album Pump Up Beats + screen colours
  MUSIC    audio on Sonar-Aux                        -> Album Pump Up Beats + album-art colours
  IDLE     nothing playing                           -> IDLE_EFFECT
  AWAY     monitor switched off by Windows           -> "Lights Off" effect (any input restores)

Effects are switched with SignalRGB's URL scheme (signalrgb://effect/apply/...),
only when the target effect actually changes. Colours are sent with the same
"palette|RRGGBB|RRGGBB|RRGGBB" canvas event album_bridge.py uses.

Reuses the album-art / colour code from album_bridge.py unchanged.
"""

import sys

# COM must be multi-threaded (MTA) on the main thread: comtypes/pycaw default to
# single-threaded (STA), and in STA the WinRT album-art stream calls never
# return, which froze the whole controller. Must be set before comtypes loads.
sys.coinit_flags = 0

import asyncio
import ctypes
import ctypes.wintypes as wintypes
import hashlib
import io
import json
import os
import random
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import psutil
from PIL import Image
from comtypes import CLSCTX_ALL, COINIT_MULTITHREADED, CoInitializeEx
from pycaw.pycaw import (
    AudioUtilities,
    IAudioMeterInformation,
    IAudioSessionControl2,
    IAudioSessionManager2,
)
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)

sys.path.insert(0, str(Path(__file__).parent))
from album_bridge import extract_dominant_colors, read_thumbnail, send_palette  # noqa: E402
import audio_mixer  # noqa: E402


# ============================== CONFIG ======================================

# Which SignalRGB effect(s) each mode uses lives in effects.json next to this
# file (created with these defaults on first run). Edit it any time - it is
# re-read live, no restart needed. Give a mode several effects and a random
# one is picked each time that mode starts.
EFFECTS_FILE = Path(__file__).parent / "effects.json"
DEFAULT_EFFECTS = {
    "AWAY": ["Lights Off"],               # monitor off: all lights off (custom effect in Documents\WhirlwindFX\Effects)
    "IDLE": ["Multizone"],
    "GAMING": ["Screen Ambience"],
    "MOVIE": ["Screen Ambience"],
    "BROWSER": ["Album Pump Up Beats"],   # screen colours are sent to Album Pump Up Beats
    "MUSIC": ["Album Pump Up Beats"],     # album-art colours are sent to Album Pump Up Beats
}

# Processes on the Media channel treated as browsers (screen colours + audio bars).
# Anything else on the Media channel (VLC, KMPlayer, MPC-HC, ...) counts as a movie.
BROWSER_PROCESSES = {
    "chrome.exe", "firefox.exe", "msedge.exe", "brave.exe", "opera.exe",
    "opera_gx.exe", "vivaldi.exe", "chromium.exe", "arc.exe", "zen.exe",
}

# A game counts as running as soon as it has an audio stream open on the Gaming
# channel (loading screens, menus, paused game - no sound needed). These
# processes are never treated as games.
IGNORED_PROCESSES = {
    "system idle process", "audiodg.exe", "explorer.exe", "shellexperiencehost.exe",
    "steam.exe", "steamwebhelper.exe", "epicgameslauncher.exe", "galaxyclient.exe",
    "steelseriesggclient.exe", "steelseriessonar.exe", "steelseriesgg.exe",
    "signalrgb.exe", "wallpaper64.exe", "wallpaper32.exe", "nvidia broadcast.exe",
    "discord.exe", "teamspeak3.exe", "ts3client_win64.exe", "zoom.exe", "whatsapp.exe",
    "powershell.exe", "python.exe", "pythonw.exe", "msedgewebview2.exe",
    "svchost.exe", "runtimebroker.exe", "dwm.exe", "ctfmon.exe", "textinputhost.exe",
    "searchhost.exe", "startmenuexperiencehost.exe", "widgets.exe", "lockapp.exe",
    # messengers / mail: their notification sounds land on the default (Gaming) device
    "telegram.exe", "signal.exe", "slack.exe", "ms-teams.exe", "msteams.exe", "teams.exe",
    "skype.exe", "viber.exe", "outlook.exe", "olk.exe", "thunderbird.exe", "hxoutlook.exe",
}

# Music players: count as MUSIC whichever Sonar channel they are routed to.
MUSIC_PROCESSES = {
    "spotify.exe", "aimp.exe", "musicbee.exe", "foobar2000.exe", "itunes.exe",
    "winamp.exe", "tidal.exe", "deezer.exe", "amazon music.exe",
}

# Video players: count as MOVIE whichever Sonar channel they are routed to,
# and are never treated as games.
VIDEO_PROCESSES = {
    "microsoft.media.player.exe", "wmplayer.exe", "vlc.exe", "kmplayer.exe",
    "kmplayer64.exe", "mpc-hc.exe", "mpc-hc64.exe", "mpc-be.exe", "mpc-be64.exe",
    "potplayermini.exe", "potplayermini64.exe", "mpv.exe", "smplayer.exe",
    "plex.exe", "plex htpc.exe", "stremio.exe", "video.ui.exe",
}

# Helper apps that should run only while another app runs: started a few
# seconds after the main app appears, terminated when it exits.
#   "main process name": "full path to helper.exe"
COMPANIONS = {
    "aimp.exe": str(Path(__file__).parent / "AIMPSmtc" / "bin" / "Release"
                    / "net8.0-windows10.0.19041.0" / "win-x64" / "AimpSmtc.exe"),
}
COMPANION_START_DELAY = 3.0    # seconds after the main app appears

# Windows media sessions are matched to the playing process by looking for the
# exe name (without .exe) inside the session's app id, e.g. "spotify" in
# "SpotifyAB.SpotifyMusic_...!Spotify", "aimp" in "NimiGames68.AimpSmtc".
# Add an entry here only for apps where that does not hold.
SESSION_ALIASES = {
    # "someplayer.exe": "text-in-its-session-app-id",
}
COMPANION_CHECK_SECONDS = 2.0

# Your own app rules (tray icon -> Apps): which apps count as game / browser /
# music player / video player, or are ignored. Overrides the lists above per app.
APPS_FILE = Path(__file__).parent / "apps.json"

AUDIO_THRESHOLD = 0.01     # peak level (0-1) above which a channel counts as playing
# How long a channel must be active before its mode is entered (guards against
# short notification sounds), and how long it must be silent before it is left.
ENTER_SECONDS = {
    "GAMING": 3.0,         # a game keeps its stream open from the first second; notification sounds do not
    "MUSIC": 0.5,
    "BROWSER": 1.0,        # a web-app "ding" should not switch effects
    "MOVIE": 1.0,
}
EXIT_SECONDS = 8.0
# When the playing app reports "Paused" AND is silent, leave its mode after this
# long instead of the full EXIT_SECONDS. Not instant: between two YouTube videos
# (or Spotify tracks) apps briefly report Paused while silent, which is not a pause.
PAUSE_EXIT_SECONDS = {"MUSIC": 1.5, "BROWSER": 4.0, "MOVIE": 4.0}
POLL_SECONDS = 0.25        # how often the meters are read

SCREEN_INTERVAL = 0.5      # seconds between screen colour updates in BROWSER mode
SCREEN_MIN_BRIGHTNESS = 6  # mean pixel value below this = black (DRM video), keep last palette
ALBUM_RESEND_SECONDS = 15.0
# Right after an effect switch SignalRGB is still loading the effect and drops
# palette messages; resend every second for this long so the colours land.
SETTLE_SECONDS = 6.0
SETTLE_RESEND_SECONDS = 1.0

# Turn the lights off while Windows has switched the monitor off (power plan
# timeout). Any key / mouse movement turns the monitor - and the lights - back on.
LIGHTS_OFF_WITH_MONITOR = True

# Tray icon with status, "Pause automation", "Force mode", shuffle, and quick
# links to effects.json / the log. Needs the pystray package.
TRAY_ENABLED = True

# Mix Sonar Media + Aux into a virtual cable so SignalRGB can capture both
# (SignalRGB audio device -> "CABLE Input"). Needs VB-Audio Virtual Cable;
# silently disabled if the cable is not installed.
MIXER_ENABLED = True

LOG_FILE = Path(__file__).parent / "controller.log"

# Higher priority wins when several channels play at once.
MODE_PRIORITY = ["GAMING", "MOVIE", "BROWSER", "MUSIC"]

MODE_PALETTE = {          # where the colours sent to Album Pump Up Beats come from
    "BROWSER": "screen",
    "MUSIC": "album",
}


# ============================== RESTART =====================================

TASK_NAME = "SignalRGBController"
RESTART_REQUEST_FILE = Path(__file__).parent / "restart.request"   # create this file to restart the controller


RESTART_HELPER = """
import subprocess, sys, time
time.sleep(3)                                              # let the old instance finish exiting
task, pythonw, script = sys.argv[1:4]
rc = subprocess.run(["schtasks", "/Run", "/TN", task], capture_output=True).returncode
if rc != 0:                                                # no scheduled task (started by hand): start directly
    subprocess.Popen([pythonw, script], cwd=script.rsplit("\\\\", 1)[0], creationflags=0x00000008)
"""


def schedule_restart():
    """Spawn a detached helper that re-runs the scheduled task 3 s after we exit, so
    Task Scheduler keeps tracking the new instance (falls back to a direct start)."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw if pythonw.exists() else Path(sys.executable))
    script = str(Path(__file__).resolve())

    try:
        subprocess.Popen([exe, "-c", RESTART_HELPER, TASK_NAME, exe, script],
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                         close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


class SingleInstance:
    """Named mutex so only one controller runs. A new copy waits a little for the old one to exit."""

    NAME = r"Local\SignalRGBAlbumSyncController"

    def __init__(self, wait_seconds=10.0):
        self.kernel32 = ctypes.windll.kernel32
        self.handle = self.kernel32.CreateMutexW(None, False, self.NAME)
        deadline = time.monotonic() + wait_seconds
        self.acquired = False

        while time.monotonic() < deadline:
            if self.kernel32.WaitForSingleObject(self.handle, 500) in (0, 0x80):   # signalled / abandoned
                self.acquired = True
                return


# ============================== SIGNALRGB ===================================

def apply_effect(name):
    # signalrgb://effect/apply/<name>?_silent=true  (_silent = do not bring the window up)
    os.startfile(f"signalrgb://effect/apply/{quote(name)}?_silent=true")


class EffectTable:
    """mode -> list of effect names, hot-reloaded from effects.json."""

    def __init__(self):
        self.table = dict(DEFAULT_EFFECTS)
        self.mtime = None
        self.last_pick = {}

        if not EFFECTS_FILE.exists():
            EFFECTS_FILE.write_text(json.dumps(DEFAULT_EFFECTS, indent=4), encoding="utf-8")

        self.reload()

    def reload(self):
        """Re-read the file if it changed. Returns True when the table changed."""
        try:
            mtime = EFFECTS_FILE.stat().st_mtime
        except OSError:
            return False

        if mtime == self.mtime:
            return False

        self.mtime = mtime

        try:
            raw = json.loads(EFFECTS_FILE.read_text(encoding="utf-8"))
            table = {}

            for mode, default in DEFAULT_EFFECTS.items():
                value = raw.get(mode, default)
                names = [value] if isinstance(value, str) else list(value)
                names = [n.strip() for n in names if isinstance(n, str) and n.strip()]
                table[mode] = names or default

            changed = table != self.table
            self.table = table
            print("Effects: " + ", ".join(f"{m}={'|'.join(v)}" for m, v in table.items()))
            return changed

        except Exception as e:
            print(f"Effects: effects.json invalid ({e}), keeping previous table")
            return False

    def pick(self, mode):
        """Random effect for the mode, avoiding the one used last time when there is a choice."""
        names = self.table.get(mode) or DEFAULT_EFFECTS[mode]
        options = [n for n in names if n != self.last_pick.get(mode)] or names
        choice = random.choice(options)
        self.last_pick[mode] = choice
        return choice


# ============================== TRAY ICON ===================================

class TrayIcon:
    """System-tray icon: coloured dot per mode, right-click menu for overrides."""

    COLORS = {
        "IDLE": (150, 150, 160), "MUSIC": (40, 190, 90), "BROWSER": (50, 130, 255),
        "MOVIE": (160, 80, 230), "GAMING": (235, 60, 60), "AWAY": (45, 45, 55),
    }
    LABELS = {"IDLE": "Idle", "MUSIC": "Music", "BROWSER": "Browser", "MOVIE": "Film",
              "GAMING": "Game", "AWAY": "Lights off"}
    FORCE_CHOICES = [("Auto", None), ("Game", "GAMING"), ("Film", "MOVIE"), ("Browser", "BROWSER"),
                     ("Music", "MUSIC"), ("Idle", "IDLE"), ("Lights off", "AWAY")]

    def __init__(self, log=print, seen_apps=None, rules=None):
        self.log = log
        self.seen_apps = seen_apps or (lambda: {})
        self.rules = rules
        self.paused = False
        self.forced = None             # mode name forced from the menu, None = automatic
        self.shuffle_requested = False
        self.quit_requested = False
        self.restart_requested = False
        self.mode, self.reason, self.effect, self.choices = "IDLE", "starting", "-", 1
        self.apply_requested = None    # effect name ticked in the picker for the current mode: apply it now
        self.available = False
        self._images = {}
        self._shown = None
        self._effects_cache = ([], 0.0)

        try:
            import pystray
            self._pystray = pystray
            self.icon = pystray.Icon("SignalRGB Sync System", self._image("IDLE", False),
                                     "SignalRGB Sync System", self._menu())
            self.icon.run_detached()
            self.available = True
        except Exception as e:
            self.log(f"Tray   : unavailable ({e})")

    # ------------------------------------------------------------ drawing

    def _image(self, mode, override):
        key = (mode, override)

        if key not in self._images:
            from PIL import ImageDraw
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((8, 8, 56, 56), fill=self.COLORS.get(mode, (150, 150, 160)) + (255,))

            if override:                                  # amber ring = paused / forced
                draw.ellipse((2, 2, 62, 62), outline=(255, 180, 40, 255), width=6)

            self._images[key] = img

        return self._images[key]

    # ------------------------------------------------------------ menu

    def _menu(self):
        Menu, Item = self._pystray.Menu, self._pystray.MenuItem

        def force_item(label, mode):
            return Item(label, lambda: self._force(mode), radio=True,
                        checked=lambda item, m=mode: self.forced == m)

        def picker(mode):
            return Item(self.LABELS[mode], Menu(lambda: self._picker_items(mode)))

        return Menu(
            Item(lambda item: f"{self.LABELS.get(self.mode, self.mode)} - {self.reason}", None, enabled=False),
            Item(lambda item: f"Effect: {self.effect}", None, enabled=False),
            Menu.SEPARATOR,
            Item("Lights off now", self._toggle_lights_off, checked=lambda item: self.forced == "AWAY"),
            Item("Pause automation", self._toggle_pause, checked=lambda item: self.paused),
            Item("Force mode", Menu(*[force_item(label, mode) for label, mode in self.FORCE_CHOICES])),
            Item("Shuffle effect", self._shuffle, enabled=lambda item: self.choices > 1 and not self.paused),
            Item("Effects for...", Menu(*[picker(mode) for mode in ("IDLE", "GAMING", "MOVIE", "BROWSER", "MUSIC", "AWAY")])),
            Item("Apps", Menu(lambda: self._app_items())),
            Menu.SEPARATOR,
            Item("Open effects.json", lambda: os.startfile(EFFECTS_FILE)),
            Item("Open log", lambda: os.startfile(LOG_FILE)),
            Item("Open folder", lambda: os.startfile(Path(__file__).parent)),
            Menu.SEPARATOR,
            Item("Restart controller", self._restart),
            Item("Quit controller", self._quit),
        )

    def _toggle_pause(self):
        self.paused = not self.paused
        self.log(f"Tray   : automation {'paused' if self.paused else 'resumed'}")
        self._refresh()

    def _toggle_lights_off(self):
        self._force(None if self.forced == "AWAY" else "AWAY")

    # ---- effect picker: tick/untick which effects each mode may use (writes effects.json)

    def _installed(self):
        names, when = self._effects_cache

        if time.monotonic() - when > 10:
            try:
                names = sorted(installed_effects(), key=str.lower)
            except Exception as e:
                self.log(f"Tray   : effect scan failed ({e})")

            self._effects_cache = (names, time.monotonic())

        return names

    @staticmethod
    def _read_table():
        try:
            raw = json.loads(EFFECTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = {}

        table = {}

        for mode, default in DEFAULT_EFFECTS.items():
            value = raw.get(mode, default)
            table[mode] = [value] if isinstance(value, str) else list(value)

        return table

    def _picker_items(self, mode):
        Item = self._pystray.MenuItem
        chosen = set(self._read_table().get(mode, []))
        names = self._installed()

        # effects chosen for this mode but not found on disk still show, marked, so they can be unticked
        missing = sorted(chosen - set(names), key=str.lower)

        if not names and not missing:
            return [Item("(no effects found)", None, enabled=False)]

        def toggle(m, n):
            return lambda: self._toggle_effect(m, n)

        def is_chosen(m, n):
            return lambda item: n in set(self._read_table().get(m, []))

        items = [Item(name, toggle(mode, name), checked=is_chosen(mode, name)) for name in names]
        items += [Item(f"{name}  (not installed)", toggle(mode, name), checked=lambda item: True) for name in missing]
        return items

    # ---- app rules: what each app that makes sound should count as (writes apps.json)

    def _app_items(self):
        Item, Menu = self._pystray.MenuItem, self._pystray.Menu

        if self.rules is None:
            return [Item("(app rules unavailable)", None, enabled=False)]

        seen = dict(self.seen_apps())
        names = sorted(set(seen) | set().union(*self.rules.user.values()), key=str.lower)

        if not names:
            return [Item("(no apps have made sound yet)", None, enabled=False)]

        def choose(n, cat):
            return lambda: self.rules.set_rule(n, cat)

        def is_rule(n, cat):
            return lambda item: self.rules.user_rule(n) == cat

        items = [Item("Apps that made sound recently - choose what each one counts as", None, enabled=False), Menu.SEPARATOR]

        for name in names:
            rule = self.rules.user_rule(name)
            builtin = self.rules.category_of(name) if rule is None else None
            label = self.rules.CATEGORIES.get(rule or builtin, "by channel")
            channel = seen.get(name, (0, None))[1]
            text = f"{name}   [{label}{' *' if rule else ''}]" + (f"   ({channel})" if channel else "")
            auto_label = "Automatic" + (f" ({self.rules.CATEGORIES[builtin]})" if builtin else " (by channel)")
            sub = [Item(auto_label, choose(name, None), radio=True, checked=is_rule(name, None))]
            sub += [Item(self.rules.CATEGORIES[cat], choose(name, cat), radio=True, checked=is_rule(name, cat))
                    for cat in self.rules.CATEGORIES]
            items.append(Item(text, Menu(*sub)))

        return items

    def _toggle_effect(self, mode, name):
        table = self._read_table()
        names = table[mode]

        if name in names:
            if len(names) == 1:
                self.log(f"Tray   : {mode} needs at least one effect, keeping {name}")
                return

            names.remove(name)
            self.log(f"Tray   : {mode} effects - removed {name}")
        else:
            names.append(name)
            self.log(f"Tray   : {mode} effects + added {name}")

        try:
            EFFECTS_FILE.write_text(json.dumps(table, indent=4), encoding="utf-8")
        except Exception as e:
            self.log(f"Tray   : could not write effects.json ({e})")
            return

        if name in names and mode == self.mode:
            self.apply_requested = name           # show the new choice right away (file is written first)

        self._refresh()

    def _force(self, mode):
        self.forced = mode
        self.log(f"Tray   : force mode {mode or 'off (auto)'}")
        self._refresh()

    def _shuffle(self):
        self.shuffle_requested = True

    def _quit(self):
        self.quit_requested = True

    def _restart(self):
        self.restart_requested = True

    # ------------------------------------------------------------ updates from the main loop

    def status(self, mode, reason, effect, choices):
        self.mode, self.reason, self.effect, self.choices = mode, reason, effect or "-", choices
        self._refresh()

    def _refresh(self):
        if not self.available:
            return

        override = self.paused or self.forced is not None
        shown = (self.mode, override, self.reason, self.effect)

        if shown == self._shown:
            return

        self._shown = shown

        try:
            self.icon.icon = self._image(self.mode, override)
            state = " (paused)" if self.paused else (" (forced)" if self.forced else "")
            self.icon.title = f"SignalRGB Sync System: {self.LABELS.get(self.mode, self.mode)}{state}"
            self.icon.update_menu()
        except Exception:
            pass

    def stop(self):
        if self.available:
            try:
                self.icon.stop()
            except Exception:
                pass


# ============================== DISPLAY STATE ===============================

class DisplayWatcher:
    """display_on flips when Windows turns the monitor off/on (power setting notification)."""

    _WM_POWERBROADCAST = 0x0218
    _PBT_POWERSETTINGCHANGE = 0x8013
    _GUID_CONSOLE_DISPLAY_STATE = uuid.UUID("6FE69556-704A-47A0-8F24-C28D936FDA47")

    def __init__(self, log=print):
        self.display_on = True
        self.available = False
        self.log = log
        self._wndproc = None           # keep the callback alive
        threading.Thread(target=self._run, name="display-watcher", daemon=True).start()

    def _run(self):
        try:
            self._loop()
        except Exception as e:
            self.log(f"Display: watcher unavailable ({e}); lights-off-with-monitor disabled")

    def _loop(self):
        user32 = ctypes.windll.user32
        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                        ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        class POWERBROADCAST_SETTING(ctypes.Structure):
            _fields_ = [("PowerSetting", GUID), ("DataLength", wintypes.DWORD), ("Data", ctypes.c_ubyte * 1)]

        user32.DefWindowProcW.restype = LRESULT
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        user32.RegisterPowerSettingNotification.restype = wintypes.HANDLE
        user32.RegisterPowerSettingNotification.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.DWORD]

        guid = GUID.from_buffer_copy(self._GUID_CONSOLE_DISPLAY_STATE.bytes_le)
        watcher = self

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == watcher._WM_POWERBROADCAST and wparam == watcher._PBT_POWERSETTINGCHANGE and lparam:
                setting = POWERBROADCAST_SETTING.from_address(lparam)

                if bytes(setting.PowerSetting) == bytes(guid):
                    state = setting.Data[0]                  # 0 = off, 1 = on, 2 = dimmed
                    watcher.display_on = state != 0

            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(wndproc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.lpszClassName = "AlbumSyncDisplayWatcher"
        wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)

        if not user32.RegisterClassW(ctypes.byref(wc)):
            raise ctypes.WinError()

        HWND_MESSAGE = wintypes.HWND(-3 & 0xFFFFFFFFFFFFFFFF)
        hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "display watcher", 0, 0, 0, 0, 0,
                                      HWND_MESSAGE, None, wc.hInstance, None)

        if not hwnd:
            raise ctypes.WinError()

        if not user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(guid), 0):   # 0 = window handle
            raise ctypes.WinError()

        self.available = True
        msg = wintypes.MSG()

        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


# ============================== COMPANION APPS ==============================

class CompanionManager:
    """Keeps each helper in COMPANIONS running exactly while its main app runs."""

    def __init__(self):
        self.first_seen = {}       # main name -> when it was first seen running
        self.started = {}          # main name -> Popen we launched
        self.last_check = 0.0

    @staticmethod
    def _running():
        names = set()

        for proc in psutil.process_iter(["name"]):
            try:
                names.add((proc.info["name"] or "").lower())
            except Exception:
                pass

        return names

    @staticmethod
    def _kill_by_name(exe_name):
        for proc in psutil.process_iter(["name"]):
            try:
                if (proc.info["name"] or "").lower() == exe_name:
                    proc.terminate()
            except Exception:
                pass

    def update(self):
        now = time.monotonic()

        if now - self.last_check < COMPANION_CHECK_SECONDS:
            return

        self.last_check = now
        running = self._running()

        for main, helper_path in COMPANIONS.items():
            helper_name = Path(helper_path).name.lower()
            main_running = main in running
            helper_running = helper_name in running

            if main_running:
                self.first_seen.setdefault(main, now)

                if not helper_running and now - self.first_seen[main] >= COMPANION_START_DELAY:
                    try:
                        self.started[main] = subprocess.Popen(
                            [helper_path],
                            cwd=str(Path(helper_path).parent),
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                        print(f"Companion: started {helper_name} for {main}")
                    except Exception as e:
                        print(f"Companion: failed to start {helper_name}: {e}")
                        self.first_seen[main] = now     # retry after another delay
            else:
                self.first_seen.pop(main, None)

                if helper_running:
                    self._kill_by_name(helper_name)
                    self.started.pop(main, None)
                    print(f"Companion: stopped {helper_name} ({main} closed)")


def documents_dir():
    """The user's Documents folder as Windows knows it (it may be redirected, e.g. to D:)."""
    try:
        buf = ctypes.c_wchar_p()
        folder_id = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")     # FOLDERID_Documents

        class GUID(ctypes.Structure):
            _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]

        guid = GUID.from_buffer_copy(folder_id.bytes_le)

        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(buf)) == 0:
            path = Path(buf.value)
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return path
    except Exception:
        pass

    return Path.home() / "Documents"


def installed_effects():
    """{effect title: file} for every effect SignalRGB can show: your own (Documents),
    installed from the library (cache), and built in (program folder)."""
    roots = [
        documents_dir() / "WhirlwindFX" / "Effects",
        Path(os.environ.get("LOCALAPPDATA", "")) / "WhirlwindFX" / "SignalRgb" / "cache" / "effects",
    ] + list((Path(os.environ.get("LOCALAPPDATA", "")) / "VortxEngine").glob("app-*/Signal-x64/Effects"))

    found = {}

    for root in roots:
        if not root.exists():
            continue

        for file in root.rglob("*.html"):
            try:
                match = re.search(r"<title>\s*(.*?)\s*</title>", file.read_text(encoding="utf-8", errors="ignore")[:8000], re.I | re.S)
            except Exception:
                continue

            if match:
                found.setdefault(match.group(1), file)

    return found


# ============================== APP RULES ===================================

class AppRules:
    """Effective app categories = built-in lists + your rules from apps.json (hot-reloaded).
    A rule for an app wins over the built-in lists."""

    CATEGORIES = {"game": "Game", "browser": "Browser", "music": "Music player",
                  "video": "Video player", "ignored": "Ignore"}
    BUILTIN = {"game": set(), "browser": BROWSER_PROCESSES, "music": MUSIC_PROCESSES,
               "video": VIDEO_PROCESSES, "ignored": IGNORED_PROCESSES}

    def __init__(self, log=print):
        self.log = log
        self.user = {cat: set() for cat in self.CATEGORIES}
        self.effective = {}
        self.mtime = None
        self._recompute()
        self.reload()

    def reload(self):
        try:
            mtime = APPS_FILE.stat().st_mtime
        except OSError:
            return False

        if mtime == self.mtime:
            return False

        self.mtime = mtime

        try:
            raw = json.loads(APPS_FILE.read_text(encoding="utf-8"))
            user = {cat: {str(n).strip().lower() for n in raw.get(cat, []) if str(n).strip()} for cat in self.CATEGORIES}
        except Exception as e:
            self.log(f"Apps   : apps.json invalid ({e}), keeping previous rules")
            return False

        changed = user != self.user
        self.user = user
        self._recompute()

        if changed:
            self.log("Apps   : " + ", ".join(f"{self.CATEGORIES[c]}={'|'.join(sorted(v))}" for c, v in user.items() if v) or "Apps   : no custom rules")

        return changed

    def _recompute(self):
        ruled = set().union(*self.user.values())
        self.effective = {cat: (self.BUILTIN[cat] - ruled) | self.user[cat] for cat in self.CATEGORIES}

    game = property(lambda self: self.effective["game"])
    browser = property(lambda self: self.effective["browser"])
    music = property(lambda self: self.effective["music"])
    video = property(lambda self: self.effective["video"])
    ignored = property(lambda self: self.effective["ignored"])

    def user_rule(self, name):
        return next((cat for cat, names in self.user.items() if name in names), None)

    def category_of(self, name):
        """Effective category key for an app, or None when it is judged by its Sonar channel."""
        return next((cat for cat in self.CATEGORIES if name in self.effective[cat]), None)

    def set_rule(self, name, category):
        """category: one of CATEGORIES keys, or None to remove the rule (back to automatic)."""
        name = name.lower()

        for names in self.user.values():
            names.discard(name)

        if category:
            self.user[category].add(name)

        try:
            APPS_FILE.write_text(json.dumps({cat: sorted(v) for cat, v in self.user.items()}, indent=4), encoding="utf-8")
        except Exception as e:
            self.log(f"Apps   : could not write apps.json ({e})")

        self._recompute()
        self.log(f"Apps   : {name} -> {self.CATEGORIES.get(category, 'automatic')}")


# ============================== SONAR METERS ================================

def _process_name(pid, control):
    """exe name for an audio session: psutil, else the exe path embedded in the session id."""
    try:
        return psutil.Process(pid).name().lower()
    except Exception:
        pass

    for getter in (control.GetSessionInstanceIdentifier, control.GetSessionIdentifier):
        try:
            match = re.search(r"([^\\|]+\.exe)", getter() or "", re.I)

            if match:
                return match.group(1).lower()
        except Exception:
            pass

    return f"pid{pid}"


class SonarMeters:
    """Peak meters + per-process sessions of the Sonar virtual playback devices."""

    def __init__(self):
        self.meters = {}
        self.managers = {}
        self.seen = {}             # process name -> (last seen time, channel): apps that had an audio session
        self.refresh()

    def refresh(self):
        self.meters.clear()
        self.managers.clear()

        for device in AudioUtilities.GetAllDevices():
            if "Active" not in str(device.state):
                continue

            name = device.FriendlyName or ""

            if not name.startswith("SteelSeries Sonar - "):
                continue

            channel = name.split(" - ", 1)[1].split(" (", 1)[0]   # Gaming / Media / Aux / ...
            dev = device._dev

            self.meters[channel] = dev.Activate(
                IAudioMeterInformation._iid_, CLSCTX_ALL, None
            ).QueryInterface(IAudioMeterInformation)

            self.managers[channel] = dev.Activate(
                IAudioSessionManager2._iid_, CLSCTX_ALL, None
            ).QueryInterface(IAudioSessionManager2)

        print(f"Sonar channels found: {', '.join(self.meters) or 'none'}")

    def peak(self, channel):
        meter = self.meters.get(channel)
        return meter.GetPeakValue() if meter else 0.0

    def sessions(self, channel):
        """{process name: (peak, stream_open)} for every audio session on this channel."""
        manager = self.managers.get(channel)

        if manager is None:
            return {}

        result = {}
        sessions = manager.GetSessionEnumerator()

        for i in range(sessions.GetCount()):
            session = sessions.GetSession(i)
            control = session.QueryInterface(IAudioSessionControl2)
            pid = control.GetProcessId()

            if pid == 0 or pid == os.getpid():        # system sounds / our own mixer loopback
                continue

            name = _process_name(pid, control)

            peak = session.QueryInterface(IAudioMeterInformation).GetPeakValue()
            stream_open = session.GetState() == 1     # AudioSessionStateActive
            old_peak, old_open = result.get(name, (0.0, False))
            result[name] = (max(old_peak, peak), old_open or stream_open)

            if not name.startswith("pid"):
                self.seen[name] = (time.monotonic(), channel)

        return result

    def playing_processes(self, channel):
        """Names of processes currently producing audio on this channel."""
        return {n for n, (peak, _) in self.sessions(channel).items() if peak >= AUDIO_THRESHOLD}


# ============================== MODE DETECTION ==============================

class ModeDetector:
    """Turns raw channel activity into a stable mode using enter/exit hysteresis."""

    def __init__(self, rules=None):
        self.rules = rules or AppRules()
        self.first_seen = {}
        self.last_seen = {}
        self.reasons = {}
        self.procs = {}            # mode -> processes behind it, kept while the mode is alive (also during gaps/pause)
        self.entered = set()       # modes that passed their enter delay; they stay until the exit grace runs out

    @staticmethod
    def _procs_of(reason):
        return {n.strip() for n in reason.split(":", 1)[1].split(",")} if ":" in reason else set()

    def _active_now(self, sonar):
        """{mode: reason} for everything that is active right now."""
        active = {}
        r = self.rules
        r.reload()

        # GAMING: any non-ignored process with an open stream on the Gaming channel (players/browsers excluded),
        # plus apps you marked as games, on any channel
        games = [n for n, (_, stream_open) in sonar.sessions("Gaming").items()
                 if stream_open and n not in r.ignored and n not in r.music
                 and n not in r.video and n not in r.browser]

        for channel in ("Media", "Aux", "Chat", "Stream"):
            games += [n for n, (_, stream_open) in sonar.sessions(channel).items() if stream_open and n in r.game]

        if games:
            active["GAMING"] = "Gaming: " + ", ".join(dict.fromkeys(games))

        if sonar.peak("Media") >= AUDIO_THRESHOLD:
            procs = sonar.playing_processes("Media") - r.music - r.ignored - r.game

            if procs & r.browser:
                active["BROWSER"] = "Media: " + ", ".join(procs & r.browser)

            if procs - r.browser:
                active["MOVIE"] = "Media: " + ", ".join(procs - r.browser)

        aux_players = sonar.playing_processes("Aux") - r.ignored - r.game - r.video - r.browser

        if aux_players:
            active["MUSIC"] = "Aux: " + ", ".join(aux_players)

        # music / video players / browsers count as such even when routed to another channel
        for channel in ("Gaming", "Media", "Aux", "Chat", "Stream"):
            playing = sonar.playing_processes(channel)

            if "MUSIC" not in active and playing & r.music:
                active["MUSIC"] = f"{channel}: " + ", ".join(playing & r.music)

            if "MOVIE" not in active and playing & r.video:
                active["MOVIE"] = f"{channel}: " + ", ".join(playing & r.video)

            if "BROWSER" not in active and playing & r.browser and channel != "Media":
                active["BROWSER"] = f"{channel}: " + ", ".join(playing & r.browser)

        return active

    def update(self, sonar, media_paused=False):
        now = time.monotonic()
        active = self._active_now(sonar)
        self.reasons = active

        for mode, reason in active.items():
            self.procs[mode] = self._procs_of(reason)

        for mode in MODE_PRIORITY:
            if mode in active:
                self.first_seen.setdefault(mode, now)
                self.last_seen[mode] = now

                # enter only while the app is still active: two short notification sounds
                # a few seconds apart must not add up to a "game"
                if now - self.first_seen[mode] >= ENTER_SECONDS.get(mode, 1.0):
                    self.entered.add(mode)
            elif mode in self.first_seen and (
                now - self.last_seen[mode] > EXIT_SECONDS
                # explicit pause: shorter grace, but it must persist (video/track transitions look like this too)
                or (media_paused and now - self.last_seen[mode] > PAUSE_EXIT_SECONDS.get(mode, 2.0))
            ):
                del self.first_seen[mode]
                del self.last_seen[mode]
                self.procs.pop(mode, None)
                self.entered.discard(mode)
            elif mode in self.first_seen and mode not in self.entered:
                # went quiet before ever qualifying (a "ding"): forget it right away
                del self.first_seen[mode]
                del self.last_seen[mode]
                self.procs.pop(mode, None)

        for mode in MODE_PRIORITY:
            if mode in self.entered:
                return mode

        return "IDLE"


# ============================== PALETTE SOURCES =============================

class ScreenPalette:
    def __init__(self):
        import mss
        self.sct = getattr(mss, "MSS", mss.mss)()   # mss >= 10 renamed the class
        self.monitor = self.sct.monitors[1]   # primary monitor
        self.last_time = 0.0

    def colors(self):
        now = time.monotonic()

        if now - self.last_time < SCREEN_INTERVAL:
            return None

        self.last_time = now
        shot = self.sct.grab(self.monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        image.thumbnail((160, 90))

        # DRM protected video captures as black: keep whatever palette is showing
        grey = image.convert("L")
        if sum(grey.tobytes()) / (grey.width * grey.height) < SCREEN_MIN_BRIGHTNESS:
            return None

        return extract_dominant_colors(image, 3)


class AlbumPalette:
    """Same track-change / cover-hash logic as album_bridge.main()."""

    def __init__(self, manager):
        self.manager = manager
        self.last_track_key = None
        self.last_cover_hash = None
        self.last_colors = None

    def session_for(self, procs):
        """The Windows media session belonging to one of these processes, else None."""
        try:
            sessions = list(self.manager.get_sessions())
        except Exception:
            return None

        keys = set()

        for name in procs:
            keys.add(SESSION_ALIASES.get(name, name[:-4] if name.endswith(".exe") else name).lower())

        for session in sessions:
            app_id = (session.source_app_user_model_id or "").lower()

            if any(key and key in app_id for key in keys):
                return session

        return None

    def is_paused(self, procs):
        """True when the session of one of these processes reports Paused."""
        try:
            session = self.session_for(procs)

            if session is None:
                return False

            return session.get_playback_info().playback_status == PlaybackStatus.PAUSED
        except Exception:
            return False

    async def colors(self, procs):
        session = self.session_for(procs)

        if session is None:
            return None            # playing app has no media session: nothing to read

        props = await session.try_get_media_properties_async()
        track_key = f"{props.title}|{props.artist}|{props.album_title}"

        if track_key == self.last_track_key and self.last_colors is not None:
            return self.last_colors          # same track: no need to re-read the cover

        if props.thumbnail is None:
            return self.last_colors

        image_bytes = await read_thumbnail(props.thumbnail)

        if not image_bytes:
            return self.last_colors

        cover_hash = hashlib.md5(image_bytes).hexdigest()

        if track_key != self.last_track_key or cover_hash != self.last_cover_hash:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            self.last_colors = extract_dominant_colors(image, 3)
            self.last_track_key = track_key
            self.last_cover_hash = cover_hash
            print(f"Track  : {props.title} - {props.artist}")
            print(f"Colors : {' -> '.join(self.last_colors)}")

        return self.last_colors


# ============================== MAIN LOOP ===================================

async def main():
    print()
    print("======================================")
    print("      SignalRGB Automation Controller")
    print("======================================")
    print("Publisher: Eshan")
    print()

    CoInitializeEx(COINIT_MULTITHREADED)

    sonar = SonarMeters()
    rules = AppRules(log=print)
    detector = ModeDetector(rules)
    screen = ScreenPalette()
    album = AlbumPalette(await GlobalSystemMediaTransportControlsSessionManager.request_async())

    if MIXER_ENABLED:
        audio_mixer.run_in_thread(log=print)

    effects = EffectTable()
    companions = CompanionManager()
    display = DisplayWatcher(log=print) if LIGHTS_OFF_WITH_MONITOR else None
    tray = TrayIcon(log=print, seen_apps=lambda: sonar.seen, rules=rules) if TRAY_ENABLED else None
    was_paused = False
    current_mode = None
    current_effect = None      # effect we last applied; None = unknown (whatever SignalRGB shows)
    effect_applied_at = 0.0
    last_sent_palette = None
    last_sent_time = 0.0

    while True:
        try:
            companions.update()

            # pause status of the app behind the mode we are in
            paused = current_mode in detector.procs and album.is_paused(detector.procs[current_mode])
            mode = detector.update(sonar, media_paused=paused)

            reason = detector.reasons.get(mode, "nothing playing")

            if tray is not None and tray.forced is not None:
                mode, reason = tray.forced, "forced from tray"

            if display is not None and not display.display_on:
                mode, reason = "AWAY", "monitor off"   # monitor is off: lights off, whatever else is happening

            if tray is not None and tray.quit_requested:
                print("Tray   : quit - controller stopped (run Install.bat or log in again to restart)")
                break

            if (tray is not None and tray.restart_requested) or RESTART_REQUEST_FILE.exists():
                try:
                    RESTART_REQUEST_FILE.unlink()
                except OSError:
                    pass

                print("Restart: requested - starting again in a few seconds")

                if not schedule_restart():
                    print("Restart: could not start a new copy; run Install.bat to start again")

                if tray is not None:
                    tray.stop()

                sys.stdout.flush()
                os._exit(0)                        # leave at once: threads (mixer, tray, watcher) die with us

            mode_changed = mode != current_mode
            table_changed = effects.reload()
            paused_now = tray is not None and tray.paused
            resumed = was_paused and not paused_now
            was_paused = paused_now
            shuffle = tray is not None and tray.shuffle_requested and not paused_now

            if tray is not None:
                tray.shuffle_requested = False

            if mode_changed:
                print(f"Mode   : {current_mode} -> {mode}  ({reason})")
                current_mode = mode

            requested = tray.apply_requested if tray is not None else None

            if tray is not None:
                tray.apply_requested = None

            if (mode_changed or table_changed or resumed or shuffle or requested) and not paused_now:
                effect = effects.pick(mode)

                if requested and requested in effects.table.get(mode, []):
                    effect = requested
                    effects.last_pick[mode] = requested
                elif shuffle and effect == current_effect:
                    effect = effects.pick(mode)

                if effect != current_effect:
                    apply_effect(effect)
                    current_effect = effect
                    effect_applied_at = time.monotonic()
                    print(f"Effect : {effect}")

                # a freshly (re)loaded effect starts without a palette: resend at once
                last_sent_palette = None
                last_sent_time = 0.0

            if tray is not None:
                tray.status(mode, reason, current_effect, len(effects.table.get(mode, [])))

            source = MODE_PALETTE.get(mode)
            colors = None

            if source == "screen":
                colors = screen.colors()
            elif source == "album":
                colors = await album.colors(detector.procs.get(mode, set()))

            if colors is not None:
                now = time.monotonic()
                changed = colors != last_sent_palette
                settling = now - effect_applied_at < SETTLE_SECONDS
                resend_after = SETTLE_RESEND_SECONDS if settling else ALBUM_RESEND_SECONDS

                if changed or now - last_sent_time >= resend_after:
                    try:
                        send_palette(colors)
                        last_sent_palette = colors
                        last_sent_time = now
                    except Exception as e:
                        print(f"SignalRGB send failed: {e}")

            await asyncio.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            print("\nController stopped.")
            break

        except Exception as e:
            print(f"Controller error: {e}")

            # Sonar devices vanish when SteelSeries GG restarts; re-enumerate them
            try:
                sonar.refresh()
            except Exception as e2:
                print(f"Sonar refresh failed: {e2}")

            await asyncio.sleep(2)

    if tray is not None:
        tray.stop()


class TimestampedLog:
    """File writer that prefixes every line with the time of day."""

    def __init__(self, file):
        self.file = file
        self.at_line_start = True

    def write(self, text):
        for piece in text.splitlines(keepends=True):
            if self.at_line_start and piece.strip():
                self.file.write(time.strftime("%H:%M:%S ") + piece)
            else:
                self.file.write(piece)

            self.at_line_start = piece.endswith("\n")

    def flush(self):
        self.file.flush()


if __name__ == "__main__":
    # A restarted copy waits for the previous instance to let go of the log and the audio devices.
    time.sleep(float(os.environ.get("ALBUMSYNC_RESTART_DELAY", "0") or 0))

    lock = SingleInstance()

    if not lock.acquired:
        sys.exit(0)                                # another controller is running: nothing to do

    # Started by pythonw.exe (scheduled task): no console, log to file instead.
    if sys.stdout is None or sys.stderr is None:
        log = TimestampedLog(open(LOG_FILE, "w", encoding="utf-8", buffering=1))
        sys.stdout = log
        sys.stderr = log

    asyncio.run(main())
