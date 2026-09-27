"""
Zones: switch individual components (fan rings, strips, ...) off inside any effect.

SignalRGB effects draw on a 320x200 canvas and every LED samples one cell of it,
so a component can be "switched off" by painting its LED cells black after the
effect has drawn its frame. This module

  * reads the current SignalRGB layout + component definitions from the registry
    (position, scale, rotation and the per-LED grid coordinates of each component),
  * turns them into canvas polygons - one small quad per LED cell, so an outer
    ring can go dark while the inner ring inside it stays lit,
  * creates a "twin" of any effect: the original HTML plus a small script that
    paints the masked cells black after each frame and takes the mask from a
    "zones|..." canvas event sent by rgb_controller.py.

Twins live in SignalRGB's program folder next to the built-in effects (the free
tier caps effects in Documents at 10). Effects that read SignalRGB's screen data
(engine.zone) cannot be twinned - SignalRGB locks third-party screen effects.
"""

import hashlib
import json
import math
import re
import winreg
from pathlib import Path

REG_ROOT = r"Software\WhirlwindFX\SignalRgb"
CANVAS_W, CANVAS_H = 320, 200
TWIN_SUFFIX = " (Zones)"
TWIN_MARK = "<!-- zones-twin:"


# ----------------------------------------------------------------- registry

def _values(path):
    """{name: value} for a registry key under HKCU, or {} if it does not exist."""
    out = {}

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        return out

    i = 0

    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
        except OSError:
            break

        i += 1
        out[name] = value

    return out


def _subkeys(path):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
    except OSError:
        return []

    names, i = [], 0

    while True:
        try:
            names.append(winreg.EnumKey(key, i))
        except OSError:
            return names

        i += 1


def _qt_json(value):
    """SignalRGB stores per-component layout settings as a Qt variant wrapping JSON."""
    if isinstance(value, bytes):
        text = value.decode("utf-16le", errors="ignore")
        match = re.search(r"(\{.*\})", text, re.S)

        if match:
            try:
                return json.loads(match.group(1))
            except ValueError:
                return None

    return None


def current_layout_name():
    return _values(REG_ROOT + r"\layouts").get("currentLayout") or ""


def component_definitions():
    """{component id: {name, width, height, leds: [(cx, cy), ...], header, device}} from every device."""
    comps = {}

    for device in _subkeys(REG_ROOT + r"\devices"):
        for header, value in _values(REG_ROOT + r"\devices\\" + device).items():
            if not isinstance(value, str) or not value.startswith("["):
                continue

            try:
                items = json.loads(value)
            except ValueError:
                continue

            for item in items:
                cid = item.get("ComponentId")

                if not cid or not item.get("LedCoordinates"):
                    continue

                comps[cid] = {
                    "name": item.get("DisplayName") or item.get("ProductName") or cid,
                    "width": float(item.get("Width") or 1),
                    "height": float(item.get("Height") or 1),
                    "leds": [tuple(c) for c in item["LedCoordinates"]],
                    "header": header,
                    "device": device,
                }

    return comps


def zones():
    """Components placed in the current layout, with their canvas geometry.
    Each: {id, name, header, x, y, sx, sy, rotation, flipped, flippedV, width, height, leds}."""
    layout = current_layout_name()

    if not layout:
        return []

    comps = component_definitions()
    out = []

    for cid, value in _values(REG_ROOT + r"\layouts\\" + layout).items():
        if cid not in comps:
            continue

        placement = _qt_json(value)

        if not placement:
            continue

        scale = placement.get("scale") or {}
        comp = comps[cid]
        out.append({
            "id": cid,
            "name": comp["name"],
            "header": comp["header"],
            "x": float(placement.get("x", 0)),
            "y": float(placement.get("y", 0)),
            "sx": float(scale.get("x", 1) or 1),
            "sy": float(scale.get("y", 1) or 1),
            "rotation": float(placement.get("rotation", 0) or 0),
            "flipped": bool(placement.get("flipped")),
            "flippedV": bool(placement.get("flippedV")),
            "width": comp["width"],
            "height": comp["height"],
            "leds": comp["leds"],
        })

    out.sort(key=lambda z: (z["header"], z["name"]))
    return out


# ----------------------------------------------------------------- geometry

def led_polygons(zone):
    """One quad (x1,y1,...,x4,y4 on the 320x200 canvas) per LED cell of the component,
    rotated about the component's centre like SignalRGB's layout editor does."""
    x, y, sx, sy = zone["x"], zone["y"], zone["sx"], zone["sy"]
    w, h = zone["width"], zone["height"]
    cx, cy = x + w * sx / 2, y + h * sy / 2
    angle = math.radians(zone["rotation"])
    cos_a, sin_a = math.cos(angle), math.sin(angle)

    def rotate(px, py):
        dx, dy = px - cx, py - cy
        return cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a

    polys = []

    for lx, ly in zone["leds"]:
        if zone["flipped"]:
            lx = w - 1 - lx

        if zone["flippedV"]:
            ly = h - 1 - ly

        left, top = x + lx * sx, y + ly * sy
        corners = [(left, top), (left + sx, top), (left + sx, top + sy), (left, top + sy)]
        quad = []

        for px, py in corners:
            rx, ry = rotate(px, py)
            quad += [round(rx, 1), round(ry, 1)]

        polys.append(quad)

    return polys


def mask_events(polys, version, max_len=1500):
    """'zones|<version>|<i>/<n>|x1,y1,...;...' chunks small enough for a URL, or ['zones|clear']."""
    if not polys:
        return ["zones|clear"]

    items = [",".join(str(v) for v in q) for q in polys]
    chunks, current = [], ""

    for item in items:
        candidate = item if not current else current + ";" + item

        if len(candidate) > max_len and current:
            chunks.append(current)
            current = item
        else:
            current = candidate

    chunks.append(current)
    return [f"zones|{version}|{i + 1}/{len(chunks)}|{chunk}" for i, chunk in enumerate(chunks)]


# ----------------------------------------------------------------- twins

OVERLAY_SCRIPT = r"""
<script>
/* zones overlay - added by SignalRGB Sync System; paints switched-off components black after every frame */
(function () {
    var chunks = {}, masks = [];
    var previous = window.onCanvasApiEvent;

    window.onCanvasApiEvent = function (e) {
        if (typeof previous === "function") { try { previous(e); } catch (err) {} }
        if (!e || e.sender !== "AlbumSpectrumBridge" || typeof e.event !== "string" || e.event.indexOf("zones|") !== 0) { return; }
        var p = e.event.split("|");
        if (p[1] === "clear") { masks = []; chunks = {}; return; }
        var ver = p[1], idx = p[2].split("/"), i = Number(idx[0]), n = Number(idx[1]);
        if (!chunks[ver]) { chunks[ver] = { n: n, parts: {} }; }
        chunks[ver].parts[i] = p[3] || "";
        if (Object.keys(chunks[ver].parts).length !== n) { return; }
        var all = [];
        for (var k = 1; k <= n; k++) {
            var polys = chunks[ver].parts[k].split(";");
            for (var j = 0; j < polys.length; j++) {
                if (!polys[j]) { continue; }
                var v = polys[j].split(",").map(Number);
                if (v.length === 8) { all.push(v); }
            }
        }
        masks = all;
        chunks = {};
    };

    function overlay() {
        if (!masks.length) { return; }
        var canvases = document.querySelectorAll("canvas");
        for (var c = 0; c < canvases.length; c++) {
            var cv = canvases[c], ctx = cv.getContext("2d");
            if (!ctx) { continue; }
            var sx = cv.width / 320, sy = cv.height / 200;
            ctx.save();
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.globalAlpha = 1;
            ctx.globalCompositeOperation = "source-over";
            ctx.fillStyle = "#000000";
            for (var m = 0; m < masks.length; m++) {
                var q = masks[m];
                ctx.beginPath();
                ctx.moveTo(q[0] * sx, q[1] * sy);
                ctx.lineTo(q[2] * sx, q[3] * sy);
                ctx.lineTo(q[4] * sx, q[5] * sy);
                ctx.lineTo(q[6] * sx, q[7] * sy);
                ctx.closePath();
                ctx.fill();
            }
            ctx.restore();
        }
    }

    var raf = window.requestAnimationFrame.bind(window);
    window.requestAnimationFrame = function (cb) {
        return raf(function (t) { try { cb(t); } finally { overlay(); } });
    };
})();
</script>
"""


def twin_name(effect_name):
    return effect_name + TWIN_SUFFIX


# ----------------------------------------------------------------- settings

def _settings_key(source_path):
    """Registry key name SignalRGB uses for an effect's saved settings: local effects by file
    name ("Album Pump Up Beats.html"), library effects by their id (the cache folder name)."""
    path = Path(source_path)

    if path.name.lower() == "effect.html" and path.parent.parent.name == "effects":
        return path.parent.name

    return path.name


def copy_settings(source_path, effect_name, force=False):
    """Clone the source effect's saved settings to the twin's key so the twin looks the same
    (Multizone's colours, Album's display style, ...). Returns True when something was written."""
    src_key = _settings_key(source_path)
    dst_key = twin_name(effect_name) + ".html"

    try:
        src = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT + r"\effects" + "\\" + src_key)
    except OSError:
        return False

    values = []
    i = 0

    while True:
        try:
            values.append(winreg.EnumValue(src, i))
        except OSError:
            break

        i += 1

    if not values:
        return False

    # only copy over a twin whose settings are still empty, unless forced
    try:
        dst_probe = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT + r"\effects" + "\\" + dst_key)
        has_values = winreg.QueryInfoKey(dst_probe)[1] > 0
    except OSError:
        has_values = False

    if has_values and not force:
        return False

    dst = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_ROOT + r"\effects" + "\\" + dst_key)

    for name, value, typ in values:
        if name.startswith("-Remote"):
            continue

        winreg.SetValueEx(dst, name, 0, typ, value)

    # the layout SignalRGB remembers for the effect (states\<effect>.html) - keep the twin on the same one
    try:
        state = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_ROOT + r"\states" + "\\" + src_key)
        state_dst = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_ROOT + r"\states" + "\\" + dst_key)
        i = 0

        while True:
            try:
                name, value, typ = winreg.EnumValue(state, i)
            except OSError:
                break

            winreg.SetValueEx(state_dst, name, 0, typ, value)
            i += 1
    except OSError:
        pass

    return True


def can_twin(source_path):
    """(ok, reason). Screen-reading effects are Pro-locked as third-party effects and are refused."""
    try:
        text = Path(source_path).read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return False, str(e)

    if "engine.zone" in text:
        return False, "reads SignalRGB screen data (Pro-locked for copies)"

    if "<title>" not in text or "requestAnimationFrame" not in text:
        return False, "not a canvas effect"

    return True, ""


def make_twin(effect_name, source_path, target_dir):
    """Write '<effect> (Zones).html' into target_dir (if missing or the source changed).
    Returns (path, created: bool)."""
    source = Path(source_path).read_text(encoding="utf-8", errors="ignore")
    digest = hashlib.sha1(source.encode("utf-8", errors="ignore")).hexdigest()[:12]
    target = Path(target_dir) / (twin_name(effect_name) + ".html")

    if target.exists() and f"{TWIN_MARK}{digest}" in target.read_text(encoding="utf-8", errors="ignore")[:400]:
        return target, False

    html = re.sub(r"<title>\s*.*?\s*</title>", f"<title>{twin_name(effect_name)}</title>", source, count=1, flags=re.S)
    html = f"{TWIN_MARK}{digest} source={Path(source_path).name} -->\n" + html + OVERLAY_SCRIPT
    target.write_text(html, encoding="utf-8")
    return target, True
