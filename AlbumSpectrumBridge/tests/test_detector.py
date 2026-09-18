"""Unit tests for the mode detector / app rules / effect table. Run:  py tests\\test_detector.py"""
import json
import os
import sys
import tempfile
import time

sys.coinit_flags = 0
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rgb_controller as rc  # noqa: E402

TMP = tempfile.mkdtemp(prefix="albumsync_test_")
rc.EFFECTS_FILE = rc.Path(TMP) / "effects.json"
rc.APPS_FILE = rc.Path(TMP) / "apps.json"
rc.ENTER_SECONDS = {m: 0.0 for m in rc.MODE_PRIORITY}   # decide instantly unless a test says otherwise
rc.EXIT_SECONDS = 0.3
rc.PAUSE_EXIT_SECONDS = {"MUSIC": 0.1, "BROWSER": 0.15, "MOVIE": 0.15}
quiet = lambda *a, **k: None


class FakeSonar:
    def __init__(self): self.data = {}
    def sessions(self, ch): return self.data.get(ch, {})
    def playing_processes(self, ch): return {n for n, (p, _) in self.sessions(ch).items() if p >= rc.AUDIO_THRESHOLD}
    def peak(self, ch): return max([p for p, _ in self.sessions(ch).values()] or [0.0])


s = FakeSonar()
rules = rc.AppRules(log=quiet)
d = rc.ModeDetector(rules)

# 1. game launched, stream open but silent (loading screen) -> GAMING; launcher ignored
s.data = {"Gaming": {"pubg.exe": (0.0, True), "steam.exe": (0.0, True)}}
assert d.update(s) == "GAMING" and "pubg.exe" in d.reasons["GAMING"] and "steam" not in d.reasons["GAMING"]
# 2. only ignored processes -> IDLE after exit grace
s.data = {"Gaming": {"steam.exe": (0.2, True), "discord.exe": (0.3, True)}}
time.sleep(0.35); assert d.update(s) == "IDLE", d.reasons
# 3. spotify on Gaming -> MUSIC, not GAMING
s.data = {"Gaming": {"spotify.exe": (0.4, True)}}; assert d.update(s) == "MUSIC", d.reasons
# 4. music + game -> GAMING; 5. game closed -> MUSIC
s.data = {"Gaming": {"pubg.exe": (0.0, True)}, "Aux": {"aimp.exe": (0.5, True)}}; assert d.update(s) == "GAMING"
s.data = {"Aux": {"aimp.exe": (0.5, True)}}; time.sleep(0.35); assert d.update(s) == "MUSIC"
# 6. gap between tracks (silent, not paused) -> still MUSIC inside grace
s.data = {"Aux": {"aimp.exe": (0.0, True)}}; assert d.update(s) == "MUSIC"
# 7. explicit pause -> IDLE after the short pause grace, not instantly
assert d.update(s, media_paused=True) == "MUSIC"; time.sleep(0.12); assert d.update(s, media_paused=True) == "IDLE"
# 8. browser vs movie on Media; 9. movie + browser -> MOVIE; + game -> GAMING
s.data = {"Media": {"brave.exe": (0.3, True)}}; assert d.update(s) == "BROWSER"
s.data = {"Media": {"vlc.exe": (0.3, True)}}; assert d.update(s) == "MOVIE"
s.data = {"Media": {"vlc.exe": (0.3, True), "brave.exe": (0.3, True)}}; assert d.update(s) == "MOVIE"
s.data["Gaming"] = {"cs2.exe": (0.0, True)}; assert d.update(s) == "GAMING"
print("core detector tests passed")

# 10. video player on Gaming -> MOVIE; with a real game -> GAMING; silent video player -> nothing
d = rc.ModeDetector(rules)
s.data = {"Gaming": {"microsoft.media.player.exe": (0.3, True)}}; assert d.update(s) == "MOVIE", d.reasons
s.data = {"Gaming": {"microsoft.media.player.exe": (0.3, True), "pubg.exe": (0.0, True)}}; assert d.update(s) == "GAMING"
s.data = {"Gaming": {"vlc.exe": (0.0, True)}}; time.sleep(0.35); assert d.update(s) == "IDLE", d.reasons
print("video player tests passed")

# 11. notification dings on Gaming never become a game; a real game still does; browser on Gaming is a browser
rc.ENTER_SECONDS = {"GAMING": 0.3, "MUSIC": 0.0, "BROWSER": 0.0, "MOVIE": 0.0}
d = rc.ModeDetector(rules)
s.data = {"Aux": {"spotify.exe": (0.5, True)}}; assert d.update(s) == "MUSIC"
for _ in range(3):
    s.data = {"Aux": {"spotify.exe": (0.5, True)}, "Gaming": {"someapp.exe": (0.3, True)}}
    assert d.update(s) == "MUSIC", d.reasons; time.sleep(0.1)
    s.data = {"Aux": {"spotify.exe": (0.5, True)}}; assert d.update(s) == "MUSIC"; time.sleep(0.15)
s.data = {"Aux": {"spotify.exe": (0.5, True)}, "Gaming": {"telegram.exe": (0.3, True)}}; assert d.update(s) == "MUSIC"
s.data = {"Aux": {"spotify.exe": (0.5, True)}, "Gaming": {"pubg.exe": (0.0, True)}}
assert d.update(s) == "MUSIC"; time.sleep(0.35); assert d.update(s) == "GAMING"
s.data = {"Gaming": {"brave.exe": (0.4, True)}}; time.sleep(0.35); assert d.update(s) == "BROWSER", d.reasons
print("notification tests passed")

# 12. app rules
rc.ENTER_SECONDS = {m: 0.0 for m in rc.MODE_PRIORITY}
d = rc.ModeDetector(rules)
s.data = {"Media": {"camtasiastudio.exe": (0.4, True)}}; assert d.update(s) == "MOVIE"
rules.set_rule("camtasiastudio.exe", "ignored"); d = rc.ModeDetector(rules); assert d.update(s) == "IDLE", d.reasons
assert json.loads(rc.APPS_FILE.read_text())["ignored"] == ["camtasiastudio.exe"]
s.data = {"Aux": {"myplayer.exe": (0.4, True)}}; assert d.update(s) == "MUSIC"
rules.set_rule("myplayer.exe", "video"); d = rc.ModeDetector(rules); assert d.update(s) == "MOVIE", d.reasons
s.data = {"Media": {"indiegame.exe": (0.0, True)}}
rules.set_rule("indiegame.exe", "game"); d = rc.ModeDetector(rules); assert d.update(s) == "GAMING", d.reasons
rules.set_rule("indiegame.exe", None); d = rc.ModeDetector(rules); assert d.update(s) == "IDLE"
assert rules.user_rule("camtasiastudio.exe") == "ignored" and rules.category_of("vlc.exe") == "video" and rules.category_of("x.exe") is None
rc.APPS_FILE.write_text(json.dumps({"browser": ["librewolf.exe"]}), encoding="utf-8"); time.sleep(0.05)
assert rules.reload() and "librewolf.exe" in rules.browser and rules.user_rule("camtasiastudio.exe") is None
print("app rules tests passed")

# 13. between two YouTube videos: silent + Paused for a moment must NOT drop BROWSER; a real pause does
rc.EXIT_SECONDS = 1.0
d = rc.ModeDetector(rules)
s.data = {"Media": {"brave.exe": (0.3, True)}}; assert d.update(s) == "BROWSER"
s.data = {"Media": {"brave.exe": (0.0, True)}}
assert d.update(s, media_paused=True) == "BROWSER"; time.sleep(0.1); assert d.update(s, media_paused=True) == "BROWSER"
s.data = {"Media": {"brave.exe": (0.3, True)}}; assert d.update(s) == "BROWSER"
s.data = {"Media": {"brave.exe": (0.0, True)}}; d.update(s, media_paused=True); time.sleep(0.2)
assert d.update(s, media_paused=True) == "IDLE"
print("pause grace tests passed")

# 14. effect table: created, hot reload, random pick without repeats, broken json ignored
t = rc.EffectTable()
assert t.table["IDLE"] and rc.EFFECTS_FILE.exists() and t.reload() is False
time.sleep(0.05); rc.EFFECTS_FILE.write_text(json.dumps({"IDLE": ["Rainbow", "Neon Shift", "Multizone"]}), encoding="utf-8")
assert t.reload() is True and t.table["MUSIC"] == ["Album Pump Up Beats"]
picks = [t.pick("IDLE") for _ in range(20)]
assert all(a != b for a, b in zip(picks, picks[1:])) and set(picks) <= {"Rainbow", "Neon Shift", "Multizone"}
rc.EFFECTS_FILE.write_text("{ broken", encoding="utf-8"); time.sleep(0.05); assert t.reload() is False
print("effect table tests passed")

print("ALL TESTS PASSED")
