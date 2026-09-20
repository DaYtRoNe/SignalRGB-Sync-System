# SignalRGB Sync System

Your RGB lighting follows what you're doing — automatically.

> **Built on SteelSeries GG (Sonar).** Sonar's separate Game / Chat / Media / Aux audio channels are how this tells music, videos and games apart. GG and Sonar are free and work **without any SteelSeries hardware**. Also needs the free SignalRGB (no Pro subscription) and Python.

| When you… | The lights… |
|---|---|
| play music (Spotify, AIMP, …) | run the audio‑reactive **Album Pump Up Beats** effect in the **colours of the album cover**, changing with every song |
| play something in a browser (YouTube, …) | run the same audio‑reactive effect in the **colours of your screen** |
| watch a film in a video player (VLC, Media Player, …) | mirror the screen (**Screen Ambience**) |
| play a game | mirror the screen (**Screen Ambience**) — from the moment the game opens. Or use **Sync Screen Dominant** (included): every LED takes the one standout colour of the screen — the whole setup goes red on an Among Us *Impostor* reveal |
| do nothing / pause | show your **idle pattern** (any SignalRGB effect; can rotate between several) |
| walk away and Windows switches the monitor off | **turn off** (the included *Sync Lights Off* effect) — and come back the moment you touch the mouse or keyboard |

No clicking, no switching effects by hand. A small helper runs in the background (≈0.01 % CPU) with a tray icon for the rare times you want to override it. Free SignalRGB is enough — no Pro subscription needed.

If several things play at once: **Game > Film > Browser > Music**. Voice chat (Discord, TeamSpeak, …) never changes the lights.

---

## Contents

1. [How it works (short version)](#how-it-works-short-version)
2. [What you need](#what-you-need)
3. [Installation](#installation) — nine short steps
4. [Optional: AIMP users](#optional-aimp-users)
5. [Everyday use & the tray icon](#everyday-use--the-tray-icon)
6. [Customising](#customising)
7. [Changing how the effect looks](#changing-how-the-effect-looks)
8. [Troubleshooting](#troubleshooting)
9. [Turning it off / uninstalling](#turning-it-off--uninstalling)
10. [What's in the folder](#whats-in-the-folder)
11. [For developers](#for-developers)

---

## How it works (short version)

SteelSeries **Sonar** gives every kind of sound its own channel (Game, Chat, Media, Aux). The helper watches those channels to see *what* is playing and *which app* is playing it, reads the album cover from Windows' "now playing" info, captures screen colours when a browser plays, and tells SignalRGB which effect to show. A tiny virtual audio cable lets SignalRGB hear music and browser audio at the same time, whatever headphones or speakers you're using.

---

## What you need

- Windows 10 or 11, about 30 minutes, one restart.
- **SignalRGB** (free) — <https://signalrgb.com>
- **SteelSeries GG** with **Sonar** (free) — <https://steelseries.com/gg>. Sonar is how the helper tells music, games and videos apart, so it's required even without SteelSeries hardware.
- **Python** (free) — <https://www.python.org/downloads/>. The helper is written in it. 3.12 or newer; tested with 3.14.
- **VB‑Audio Virtual Cable** (free) — <https://vb-audio.com/Cable/>. The "virtual wire" that lets SignalRGB hear everything.
- This project: click the green **Code** button on GitHub → **Download ZIP**, and unzip it anywhere (Desktop is fine).
- Optional, AIMP users only: **.NET 8 Desktop Runtime** — see [Optional: AIMP users](#optional-aimp-users).

---

## Installation

Do the steps in order. Each one is short.

### Step 1 — Install SignalRGB
1. Install SignalRGB, create / sign in to an account, let it find your devices.
2. Arrange your devices in **Layout** so the picture matches your desk (screen colours are mapped onto this).
3. Two effects are used by default. **Screen Ambience** is built in. **Multizone** is the default idle pattern: open **Effects**, search for *Multizone* and install it — or choose any effect you like as the idle pattern later (see [Customising](#customising)).

### Step 2 — Install SteelSeries GG and set up Sonar
1. Install GG, open **Sonar**, switch it on, and choose your headphones/speakers as the output. Windows' default playback device becomes *SteelSeries Sonar – Gaming* — that's correct, leave it.
2. Tell Sonar which app belongs to which channel. In the Sonar mixer each column has an **Apps** box at the bottom: click it and pick the app (the app must be open once to appear). You can also use Windows: *Settings → System → Sound → Volume mixer* → set each app's *Output device*.

| Sonar channel | Put these apps here |
|---|---|
| **Game** | Games (they land here by default) |
| **Chat** | Discord, TeamSpeak, Zoom, WhatsApp — anything with voices |
| **Media** | Browsers (Chrome, Firefox, Edge, Brave…) and video players (VLC, KMPlayer, Media Player…) |
| **Aux** | Music players (Spotify, AIMP, MusicBee…) |

> **Why this matters:** the helper decides "music vs. video vs. game" from these channels. The most common mistake is a music player still on the Game channel — the lights then mirror the screen instead of the album cover. (You can also fix such cases later from the tray icon's *Apps* menu.)

### Step 3 — Install Python
Run the installer from python.org. On the first screen tick **"Add python.exe to PATH"**, then **Install Now**. Leave "py launcher" ticked (it is by default).

### Step 4 — Install VB‑Audio Virtual Cable, then restart the PC
1. Download the "VB‑CABLE Driver Pack" zip and unzip it.
2. Right‑click `VBCABLE_Setup_x64.exe` → **Run as administrator** → **Install Driver**.
3. **Restart Windows.**
4. After the restart open *Settings → System → Sound* and make sure **Output** is still *SteelSeries Sonar – Gaming*. If Windows switched it to "CABLE Input", switch it back.

### Step 5 — Copy the program folder to your C: drive
From the unzipped download, copy the folder **`AlbumSpectrumBridge`** to the root of `C:` so that this file exists:

```
C:\AlbumSpectrumBridge\rgb_controller.py
```

### Step 6 — Run the installer
1. Open `C:\AlbumSpectrumBridge` and double‑click **`Install.bat`**.
2. A black window works for 1–2 minutes: it downloads a few Python add‑ons, copies the three effects into SignalRGB's program folder, and sets the helper to start automatically when you log in.
3. It ends with **"Installed. The controller is running."** Press any key to close it.
4. **Restart SignalRGB once** (its tray icon → Exit, then open it again) — it only looks for new effects when it starts.

> Why the program folder and not `Documents\WhirlwindFX\Effects`? The free tier of SignalRGB loads at most **10** custom effects from the Documents folder and silently ignores the rest. The program folder has no such limit; a SignalRGB update wipes it, so the helper re‑copies the effects automatically (you'll see a note in the log asking for one SignalRGB restart).

> If Windows shows *"Windows protected your PC"*: click **More info → Run anyway**. It's a plain script; you can open it in Notepad.

`Install.bat` is safe to run again at any time — for example after you change something, or if the helper ever stops.

### Step 7 — Two settings inside SignalRGB
1. **Settings → Audio → Audio Device**: choose **CABLE Input (VB‑Audio Virtual Cable)** (not the "16ch" one).
2. In **Effects**, find **Album Pump Up Beats** (your own effects are listed with the others), click it once, and in its settings set **Color Style = Album**. Feel free to adjust *Display Style*, *Volume Boost*, *Background Beat Flash* — settings are saved automatically.

You can now leave any effect selected; from here on the helper chooses.

### Step 8 — Try it
- Play a song in Spotify/AIMP → within ~2 s the audio effect appears in the cover's colours. Skip a track → colours change at once.
- Pause → after a moment your idle effect comes back.
- Play a YouTube video → audio effect with screen colours.
- Open a game → Screen Ambience (even on the loading screen). Try *Sync Screen Dominant* for games via the tray (*Effects for… → Game*): the whole setup takes the screen's standout colour.

Something not right? See [Troubleshooting](#troubleshooting) — `C:\AlbumSpectrumBridge\controller.log` says exactly what the helper saw, with times.

### Step 9 — Find the tray icon
A small coloured dot appears next to the clock (Windows may tuck it into the **^** overflow area — drag it out once to keep it visible). That's your remote control; see [Everyday use](#everyday-use--the-tray-icon).

---

## Optional: AIMP users

AIMP doesn't tell Windows what's playing, so its covers can't be read directly. A small third‑party helper called **AimpSmtc** fixes that (it forwards AIMP's remote‑control info to Windows' media controls).

1. Install the free **.NET 8 Desktop Runtime** (<https://dotnet.microsoft.com/download/dotnet/8.0> → *Desktop Runtime* → Windows x64).
2. Put the AimpSmtc build in `C:\AlbumSpectrumBridge\AIMPSmtc\` so that this file exists:
   `C:\AlbumSpectrumBridge\AIMPSmtc\bin\Release\net8.0-windows10.0.19041.0\win-x64\AimpSmtc.exe`
   (AimpSmtc is not part of this repository.)

Nothing else to do: the controller starts AimpSmtc a few seconds after AIMP opens and closes it when AIMP closes.

---

## Everyday use & the tray icon

There is nothing to start or click. The helper starts ~10 s after you log in.

**The tray icon** — a coloured dot next to the clock: grey idle · green music · blue browser · purple film · red game · dark lights‑off; an amber ring means you've paused or forced something. Hover for details. **Right‑click** for the menu:

| Menu item | What it does |
|---|---|
| *(status lines)* | Current situation + why (e.g. `Music - Aux: spotify.exe`) and the effect showing |
| **Lights off now** | One click to switch everything off (the *Sync Lights Off* effect) — click again to resume |
| **Pause automation** | Effects stop switching; pick whatever you like in SignalRGB. Untick to resume |
| **Force mode ▸** | Keep one situation on (e.g. *Game* while you watch a stream) until you choose *Auto* |
| **Shuffle effect** | Jump to another effect from this situation's list (when it has several) |
| **Effects for… ▸** | **The easiest way to choose effects.** Pick a situation, tick any of your installed SignalRGB effects; tick several and one is chosen at random each time. Ticking one for the situation you're in shows it immediately |
| **Apps ▸** | **Teach it your apps.** Lists every app that made sound recently with what it counts as. Open one to set *Game / Browser / Music player / Video player / Ignore* (e.g. a new media player as *Video player*, a video editor or a chatty app as *Ignore* so it never changes the lights). `*` marks your own rules; *Automatic* removes a rule |
| **Open effects.json / log / folder** | Shortcuts to the files described below |
| **Restart controller** | Restarts the helper (a few seconds of darkness) — use after editing a `.py` file or if something looks stuck |
| **Quit controller** | Stops the automation until your next login (or `Install.bat`) |

Good to know:
- Manual picks inside SignalRGB stick until the next automatic change.
- Effects switch silently — the SignalRGB window doesn't pop up.
- Short quiet passages inside a song, gaps between tracks and the moment between two YouTube videos don't switch to idle; a real pause does.
- Lights‑off follows **Windows** switching the monitor off (*Settings → System → Power → Screen timeout*); the monitor's own power button doesn't tell Windows anything. Watching a film keeps the monitor — and the lights — on. Want a faint night glow instead of full off? Open the *Sync Lights Off* effect in SignalRGB and set its *Glow colour*.
- DRM video in a browser (Netflix, Prime, Disney+) shows as black to Windows, so screen colours can't be read there — the lights keep the last colours. YouTube, Twitch etc. work normally.
- Pause / Force are forgotten at the next login, so it can't stay in a strange state by accident.
- Resource use: ≈0.01 % CPU and 50–100 MB of memory; screen‑colour mode adds 1–3 % of one core while a browser plays.

---

## Customising

Everything below is either a tray‑menu action or a text file edited with **Notepad** (right‑click → *Open with* → *Notepad*, save with Ctrl+S).

### The included effects
- **Album Pump Up Beats** — audio‑reactive bars that take their colours from the album cover (music) or the screen (browser).
- **Sync Screen Dominant** — every LED shows the single standout colour of the screen. Great for games: an Among Us *Impostor* reveal turns the whole room red. The helper measures the colour (GPU capture, only when the screen changes — negligible cost) and sends it to the effect. Settings: saturation boost, brightness, smoothing, what to do on a black screen. Pick it for *Game* / *Film* via the tray's *Effects for…* menu if you prefer it to Screen Ambience's per‑zone mirror.
- **Sync Lights Off** — everything off (or a faint glow colour of your choice).

Why the "Sync" prefix? SignalRGB looks effects up on its marketplace by name; a name that also exists there as a paid effect makes SignalRGB lock yours. Unique names avoid that.

### Which effect for which situation
Use the tray's **Effects for…** menu. The same information lives in `C:\AlbumSpectrumBridge\effects.json`, which you can also edit by hand — changes apply immediately, no restart:

```json
{
    "AWAY":    ["Sync Lights Off"],
    "IDLE":    ["Multizone", "Rainbow", "Neon Shift"],
    "GAMING":  ["Screen Ambience"],
    "MOVIE":   ["Screen Ambience"],
    "BROWSER": ["Album Pump Up Beats"],
    "MUSIC":   ["Album Pump Up Beats"]
}
```

- Names must match SignalRGB **exactly** (capitals and spaces), inside quotes.
- Several names for one situation → a random one each time that situation starts.
- Keep *Album Pump Up Beats* for MUSIC and BROWSER if you want album/screen colours — it's the only effect that understands them.
- A typo makes the helper keep the previous settings (noted in the log).

### Which apps count as what
Use the tray's **Apps** menu. The rules are saved in `C:\AlbumSpectrumBridge\apps.json` (created on the first rule). The built‑in lists are at the top of `rgb_controller.py` (`BROWSER_PROCESSES`, `MUSIC_PROCESSES`, `VIDEO_PROCESSES`, `IGNORED_PROCESSES`).

> **How do I find an app's process name?** Task Manager (Ctrl+Shift+Esc) → *Details* → the *Name* column, e.g. `Spotify.exe`. The helper's log also prints it on every switch: `Mode : IDLE -> MUSIC (Aux: aimp.exe)`.

### Timing and other settings — `C:\AlbumSpectrumBridge\rgb_controller.py`
All settings are near the top, each with a comment. After editing, use the tray's **Restart controller** (or run `Install.bat`).

| I want to… | Find this text | Change |
|---|---|---|
| Switch faster/slower when something starts | `ENTER_SECONDS = {` | Seconds to wait per situation |
| Wait longer/shorter before going idle after sound stops | `EXIT_SECONDS = 8.0` | Seconds of silence |
| React faster/slower to a real pause | `PAUSE_EXIT_SECONDS = {` | Seconds a pause must last before it counts |
| Screen colours update faster/slower | `SCREEN_INTERVAL = 0.5` | Seconds between screen reads |
| Run a helper only while another app runs (like AimpSmtc) | `COMPANIONS = {` | Add `"app.exe": r"C:\path\to\helper.exe",` |
| Keep the lights on when the monitor is off | `LIGHTS_OFF_WITH_MONITOR = True` | `False` |
| Hide the tray icon | `TRAY_ENABLED = True` | `False` |
| Album‑cover colour fade speed | — | It's the *Album color fade speed* slider in the effect's settings inside SignalRGB |

### Which channels the effect hears — `audio_mixer.py`
By default the effect hears the **Media** and **Aux** channels (browser + music), never Game or Chat. Edit `SOURCE_CHANNELS = ["Media", "Aux"]` to change that (e.g. add `"Gaming"`), then restart the controller.

---

## Changing how the effect looks

Most looks are settings inside SignalRGB (click the effect, use the panel on the right): *Display Style*, *Volume Boost*, *Frequency spectrum width*, *Background Beat Flash*, decay speeds, *Album color fade speed*. Only the things below need a file edit.

The file is `Documents\WhirlwindFX\Effects\Album Pump Up Beats.html`. Open it with Notepad, Ctrl+F the text shown, edit, save. Then in SignalRGB click a different effect and click *Album Pump Up Beats* again so it reloads.

### The regions of the effect
```
┌──────┬───────────────────────────┬──────┬──────┬────────┬───────┐
│ left │  top-left bar: BASS        │ bass │ vol. │ circle │ ring/ │
│ bar: │  (reacts to low notes)     │ rect │ rect │ (vol.) │ strip │
│ VOL. ├───────────────────────────┴──────┴──────┴────────┴───────┤
│      │                                                          │
│ (re- │       centre: frequency spectrum bars (the main part)    │
│ acts │                                                          │
│ to   ├──────────────────────────────────────────────────────────┤
│ loud)│  bottom line: frequency spectrum                         │
└──────┴──────────────────────────────────────────────────────────┘
```
Two "meters" drive these: `audioLevel` = overall loudness, `baseVolume` = bass only (their `…Rect` versions fall back more slowly).

### Make the bass bar react to overall volume instead of bass
1. Find `// print base detection bar` — in the two long lines under it change every `baseVolume` to `audioLevel`.
2. Find `// base rect` — in the line under it change `baseVolumeRect` to `audioLevelRect`.
3. Find `// middle part of wraith prism` — in the line under it change `baseVolumeRect` to `audioLevelRect`.

The reverse works the same way: under `// left volume display` change `audioLevel` to `baseVolume`; under `// display volumeRect` change `audioLevelRect` to `baseVolumeRect`.

### How the two colours are chosen from the cover
The cover gives three colours; the effect keeps the best two. Find `let score = 0.55*hueDist`: `0.55` prefers two clearly different hues, `0.35` prefers vivid colours, `0.10` prefers keeping the cover's main colour. Raise the last one (e.g. `0.30`) to keep the main colour more often; raise the first for more contrast.

### What shows before the first colours arrive
The effect stays dark until it receives colours and falls back to *Static Color 1/2* after 10 s if nothing arrives (helper not running). Find `albumFallbackAfterMs = 10000` to change that (milliseconds).

The *Sync Lights Off* effect has one setting in SignalRGB (*Glow colour*) and nothing to edit.

---

## Troubleshooting

First stop: `C:\AlbumSpectrumBridge\controller.log` — what the helper found at start and every switch it made, with the reason and time. To watch it live, double‑click **`Run controller with a window (troubleshooting).bat`**.

| Symptom | Likely cause → what to do |
|---|---|
| Nothing ever switches; log missing or old | Helper not running → double‑click **Install.bat** |
| No tray icon | Look in the **^** overflow area first. Log says `Tray : unavailable` → run Install.bat again |
| Log: `Sonar channels found: none` | SteelSeries GG / Sonar not running or off → start GG, turn Sonar on, Restart controller |
| Log: `Mixer : no playback device matching 'CABLE Input'` | VB‑Cable not installed or PC not restarted → Step 4, then Install.bat |
| Bars don't move for browser music but do for Spotify (or vice‑versa) | SignalRGB's audio device isn't *CABLE Input* → Step 7 |
| Plain cyan/static colours, no cover colours | Color Style isn't *Album* (Step 7), or the helper isn't running |
| Music shows Screen Ambience instead of the album effect | The player is on the Game channel → move it to Aux in Sonar, or tray → *Apps* → mark it *Music player* |
| An app is treated as a game / film but isn't | Tray → *Apps* → set it to *Ignore* (or the right category). Log line `-> GAMING (Gaming: xyz.exe)` names the culprit |
| A notification sound switched the lights | Same: *Apps* → *Ignore*. Most messengers are already ignored |
| Log says `Effect : WARNING - SignalRGB did not load '…'` | The helper checks SignalRGB's own log after every switch. Either the name doesn't exist in SignalRGB (fix via *Effects for…*) or it's one of ours and SignalRGB hasn't been restarted since it was (re)installed → restart SignalRGB |
| An effect shows "requires SignalRGB Pro" | Third‑party effects that read SignalRGB's screen data are Pro‑only — ours don't (the helper measures the screen instead). If it's one of ours, its name collides with a marketplace effect: rename it (keep the "Sync" prefix) |
| A custom effect I put in Documents never appears | Free tier loads only 10 custom effects from `Documents\WhirlwindFX\Effects`. Put it in SignalRGB's program folder instead (`%LOCALAPPDATA%\VortxEngine\app-<version>\Signal-x64\Effects\Dynamic`) and restart SignalRGB |
| SignalRGB window pops up on every switch | Very old SignalRGB version → update SignalRGB |
| Lights go idle in quiet parts of songs | The player has no "now playing" info (AIMP without AimpSmtc, rare players) → see AIMP section |
| Lights don't go off when the monitor does | Log says `Display: watcher unavailable`, or *Sync Lights Off* isn't loaded (run Install.bat, then restart SignalRGB). Only Windows switching the display off counts |
| Everything stopped after a SignalRGB update | The update wiped its program folder; the helper re‑copies the effects within a minute and logs `Effects: installed into SignalRGB … restart SignalRGB once` → restart SignalRGB, re‑select Color Style = Album |
| Windows changed my sound output to "CABLE Input" | *Settings → System → Sound → Output → SteelSeries Sonar – Gaming* |

Restart the helper any time: tray → **Restart controller**, or `Install.bat`, or in PowerShell `Stop-ScheduledTask SignalRGBController; Start-ScheduledTask SignalRGBController`.

---

## Turning it off / uninstalling

- **For a while:** tray → *Pause automation*, or *Quit controller* (until next login).
- **Completely:** double‑click **`Uninstall.bat`** in `C:\AlbumSpectrumBridge`, then delete the folder. Python and VB‑Cable stay installed (remove them from *Installed apps* if you wish). In SignalRGB set the Audio Device back to your normal output.

---

## What's in the folder

| File | What it is |
|---|---|
| `Install.bat` / `Uninstall.bat` | Set everything up / remove it. Double‑click |
| `Run controller with a window (troubleshooting).bat` | Runs the helper in a visible window |
| `effects.json` | Which effect(s) for which situation (tray → *Effects for…*) |
| `apps.json` | Your app rules (tray → *Apps*); appears after the first rule |
| `rgb_controller.py` | The helper: watches Sonar, switches effects, sends colours, tray icon, lights‑off, AimpSmtc. Settings at the top |
| `audio_mixer.py` | Combines the Media + Aux channels into the virtual cable SignalRGB listens to |
| `album_bridge.py` | Reads album covers and picks their colours |
| `effect\Album Pump Up Beats.html`, `effect\Sync Lights Off.html`, `effect\Sync Screen Dominant.html` | The SignalRGB effects — the source copies; the installer and the helper place them in SignalRGB's program folder |
| `requirements.txt`, `scripts\` | Used by the installer |
| `tests\` | Unit tests for the decision logic (`py tests\test_detector.py`) |
| `controller.log` | Appears after the first run. Safe to delete; recreated at each start |
| `restart.request` | Create an empty file with this name to make the helper restart (used by scripts) |

---

## For developers

- **Detection:** per‑app audio sessions on each Sonar virtual device (pycaw / WASAPI meters), with process names resolved via psutil or the session identifier. Games = an open stream on the Gaming device from a non‑ignored process, held for 3 s. Modes use enter/exit hysteresis; explicit pauses (Windows media session status) shorten the exit.
- **Colours:** Windows `GlobalSystemMediaTransportControls` sessions matched to the playing process → cover thumbnail → median‑cut palette (`album_bridge.py`) → `POST http://localhost:16034/canvas/event?sender=AlbumSpectrumBridge&event=palette|rrggbb|rrggbb|rrggbb`, which the effect receives in `onCanvasApiEvent`. Screen colours come from `mss` at 2 Hz.
- **Effect switching:** `signalrgb://effect/apply/<name>?_silent=true` (URL scheme; `_silent` keeps the window hidden).
- **Audio:** `audio_mixer.py` captures the Sonar Media/Aux loopbacks (8‑ch/96 kHz), folds to stereo and plays into VB‑Cable, which SignalRGB captures.
- **Lights off:** `RegisterPowerSettingNotification(GUID_CONSOLE_DISPLAY_STATE)` on a message‑only window.
- COM must be initialised **multi‑threaded** before comtypes loads (`sys.coinit_flags = 0`); in STA the WinRT thumbnail stream calls never return.
- **Screen colours for the dominant effect:** `dxcam` (Desktop Duplication) frames, only delivered when the screen changed; stride‑sampled to ~14k pixels; HSL histogram (36 hue bins, saturation/mid‑lightness weighted, circular mean) → `dominant|h|s|l|lit` canvas event at ≤4 Hz. mss fallback.
- **Effect installation:** into `%LOCALAPPDATA%\VortxEngine\app-<newest>\Signal-x64\Effects\Dynamic` (free tier caps Documents effects at 10). Re‑checked every minute. Each switch is verified against SignalRGB's own log (`EffectRunning: Activated '<name>'`), selecting the log of the running main process by PID because every `signalrgb://` URL spawns a short‑lived helper process with its own log.
- Not possible from outside SignalRGB (checked): changing the audio capture device, global brightness or device components while it runs — those settings are read at startup only, and the REST API is Pro‑only. Third‑party effects that read `engine.zone` (screen data) are Pro‑locked.

Tests: `py AlbumSpectrumBridge\tests\test_detector.py`.

---

SignalRGB, SteelSeries Sonar, VB‑Audio and AimpSmtc belong to their respective owners. Effect *Album Pump Up Beats* and the helper by Eshan (DaYtRoNe).
