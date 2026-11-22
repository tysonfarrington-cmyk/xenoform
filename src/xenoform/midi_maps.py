"""MIDI maps by device name (UI_REVIEW 6.5, the 4 Nov handoff's T1 and T1b): each controller keeps its own map on the
desk's machine, and shipped presets pick a map by the controller's port name.

    ~/.xenoform/midi_map.json      the user's maps, one entry per device name (XENO_HOME moves the folder). The pages
                                   mirror it in localStorage["xeno-midi"] and the newer copy wins, so a map survives a
                                   restart, a cleared browser and a song or video change.
    configs/midi_presets/*.json    shipped presets: {"device", "match" (a regex on the port name), "label", "profile",
                                   "pages": {"vj": [rows], "desk": [rows]}}; XENO_MIDI_PRESETS moves the folder.

A row is midi.js's mapping row: {"source": {"type", "ch", "num"}, "target", "mode", "min", "max", "label"}. A device
with no map of its own takes the first preset that matches its name, else the built-in profile its name matches (the
MiniLab 3), else the generic map; Reset to default deletes the device's own rows for a page.

Routes (stems_api's router includes this one, beside the MIDI hub):
    GET    /api/midi/maps                    every saved map, and the shipped presets
    GET    /api/midi/maps/{device}           one device's map (its exact name, or the same name with or without the
                                             port number a backend appends: "Minilab3 0" is "Minilab3")
    PUT    /api/midi/maps/{device}           save pages of it: {"pages": {"vj": [rows]}} or {"page": "vj", "rows": [...]}
    DELETE /api/midi/maps/{device}?page=vj   Reset to default (one page, or the whole device without ?page)
    GET    /api/midi/presets                 the shipped presets
    POST   /api/midi/presets                 "Save as the shipped preset": {"device", "pages", ...} written to
                                             configs/midi_presets/<device>.json for the repository
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

log = logging.getLogger("xenoform")
ROOT = Path(__file__).resolve().parents[2]
KINDS = ("cc", "note", "pitch", "prog", "touch")
MODES = ("abs", "toggle", "trigger", "rel", "hold")
MAX_ROWS = 256
MAX_DEVICES = 64
_PAGE = re.compile(r"^[a-z][a-z0-9_-]{0,15}$")
_LOCK = threading.Lock()


def home_dir() -> Path:
    """The desk's own folder for per-user files: ~/.xenoform, or XENO_HOME."""
    env = os.environ.get("XENO_HOME")
    return Path(env).expanduser() if env else Path.home() / ".xenoform"


def maps_path() -> Path:
    return home_dir() / "midi_map.json"


def presets_dir() -> Path:
    env = os.environ.get("XENO_MIDI_PRESETS")
    return Path(env).expanduser() if env else ROOT / "configs" / "midi_presets"


# ---------------------------------------------------------------- names and rows
def clean_device(name) -> str:
    n = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "")).strip()[:96]
    if not n:
        raise ValueError("A device name is needed.")
    return n


def bare(name: str) -> str:
    """The name without the port number some MIDI backends append (rtmidi on Windows lists "Minilab3 0")."""
    return re.sub(r"\s+\d+$", "", str(name or "").strip())


def same_device(a: str, b: str) -> bool:
    a, b = str(a or "").strip(), str(b or "").strip()
    return bool(a and b) and (a == b or bare(a) == b or a == bare(b))


def page_ok(page) -> bool:
    return isinstance(page, str) and bool(_PAGE.match(page))


def clean_rows(rows) -> list[dict]:
    """Keep the rows midi.js can play: a source (cc/note/pitch/prog/touch, channel 0..16 with 0 = any, number 0..127),
    a target, a known mode, a range; anything else is dropped, at most 256 rows."""
    if not isinstance(rows, list):
        raise ValueError("A page's rows are a list.")
    out = []
    for r in rows[:MAX_ROWS]:
        if not isinstance(r, dict) or not isinstance(r.get("source"), dict) or not r.get("target"):
            continue
        s = r["source"]
        kind = str(s.get("type") or "")
        if kind not in KINDS:
            continue
        try:
            ch = max(0, min(16, int(s.get("ch") or 0)))
            num = max(0, min(127, int(s.get("num"))))
            lo = float(r.get("min") or 0.0)
            hi = 1.0 if r.get("max") is None else float(r.get("max"))
        except (TypeError, ValueError):
            continue
        mode = str(r.get("mode") or "abs")
        row = {"source": {"type": kind, "ch": ch, "num": num}, "target": str(r["target"])[:64],
               "mode": mode if mode in MODES else "abs", "min": lo, "max": hi}
        if r.get("label"):
            row["label"] = str(r["label"])[:64]
        out.append(row)
    return out


def _pages(pages) -> dict[str, list[dict]]:
    if not isinstance(pages, dict):
        return {}
    return {p: clean_rows(rows) for p, rows in pages.items() if page_ok(p) and isinstance(rows, list)}


def _write(path: Path, text: str) -> None:
    """Write next to the target and swap it in, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- the user's maps
def load_maps() -> dict:
    """The maps file as {"kind", "version", "devices": {name: entry}}; a missing file is empty, an unreadable one is
    empty too (and set aside the next time a map is saved, never overwritten in place)."""
    p = maps_path()
    empty = {"kind": "xenoform-midi-maps", "version": 1, "devices": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty
    except (OSError, ValueError):
        log.warning("MIDI maps: %s does not read; the desk starts without it", p)
        return {**empty, "unreadable": True}
    devs = data.get("devices") if isinstance(data, dict) else None
    out = {}
    for name, entry in (devs or {}).items() if isinstance(devs, dict) else ():
        if not isinstance(entry, dict):
            continue
        try:
            key = clean_device(name)
        except ValueError:
            continue
        row = {"device": key, "pages": _pages(entry.get("pages")), "updated": float(entry.get("updated") or 0.0)}
        for k in ("profile", "label"):
            if entry.get(k):
                row[k] = str(entry[k])[:80]
        out[key] = row
    return {**empty, "devices": out}


def save_maps(data: dict) -> None:
    p = maps_path()
    if data.get("unreadable") and p.exists():  # keep what was there for a person to look at
        os.replace(p, p.with_name(f"midi_map.unreadable-{time.strftime('%Y%m%d-%H%M%S')}.json"))
    body = {"kind": "xenoform-midi-maps", "version": 1, "devices": data.get("devices") or {}}
    _write(p, json.dumps(body, indent=1))


def _key_for(devices: dict, name: str) -> str | None:
    if name in devices:
        return name
    return next((k for k in devices if same_device(k, name)), None)


def get_map(device: str) -> dict | None:
    data = load_maps()
    key = _key_for(data["devices"], clean_device(device))
    return data["devices"].get(key) if key else None


def put_map(device: str, body: dict) -> dict:
    """Save pages of a device's map. Only the pages sent are replaced, so the desk and /vj never overwrite each
    other's rows; ``updated`` is the sender's clock (the pages keep the newer of their copy and this one)."""
    device = clean_device(device)
    body = body if isinstance(body, dict) else {}
    pages = body.get("pages")
    if not isinstance(pages, dict) and page_ok(body.get("page")):
        pages = {body["page"]: body.get("rows")}
    if not isinstance(pages, dict) or not pages:
        raise ValueError('Send {"pages": {"vj": [rows]}} or {"page": "vj", "rows": [...]}.')
    clean = {}
    for page, rows in pages.items():
        if not page_ok(page):
            raise ValueError(f"{page!r} is not a page name.")
        clean[page] = clean_rows(rows)
    with _LOCK:
        data = load_maps()
        devs = data["devices"]
        key = _key_for(devs, device) or device
        entry = devs.get(key) or {"device": key, "pages": {}}
        entry["pages"].update(clean)
        for k in ("profile", "label"):
            if body.get(k):
                entry[k] = str(body[k])[:80]
        try:
            entry["updated"] = float(body.get("updated") or time.time())
        except (TypeError, ValueError):
            entry["updated"] = time.time()
        devs[key] = entry
        if len(devs) > MAX_DEVICES:  # the oldest go first
            for old in sorted(devs, key=lambda k: devs[k].get("updated") or 0.0)[: len(devs) - MAX_DEVICES]:
                devs.pop(old, None)
        save_maps(data)
        return entry


def delete_map(device: str, page: str = "") -> bool:
    """Reset to default: drop the device's own rows for ``page`` (or the whole device)."""
    device = clean_device(device)
    with _LOCK:
        data = load_maps()
        devs = data["devices"]
        key = _key_for(devs, device)
        if not key:
            return False
        if page:
            if page not in devs[key]["pages"]:
                return False
            devs[key]["pages"].pop(page)
            devs[key]["updated"] = time.time()
            if not devs[key]["pages"]:
                devs.pop(key)
        else:
            devs.pop(key)
        save_maps(data)
        return True


# ---------------------------------------------------------------- shipped presets
def default_match(device: str) -> str:
    """A regex on the port name that finds this controller however a backend spells it: its name without the port
    number, any spaces optional, case ignored ("Minilab3" matches "Minilab3 0", "Minilab3 MIDI", "MIDIIN2 (Minilab3)")."""
    words = [re.escape(w) for w in bare(device).split()]
    return r"\s*".join(words) or re.escape(device)


def load_presets() -> list[dict]:
    """configs/midi_presets/*.json, in name order; a file that does not read or names no device is skipped."""
    folder = presets_dir()
    out = []
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        try:
            j = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("MIDI preset %s does not read; skipped", path.name)
            continue
        if not isinstance(j, dict):
            continue
        pages = _pages(j.get("pages"))
        device = str(j.get("device") or "").strip()[:96]
        match = str(j.get("match") or "")
        if match:
            try:
                re.compile(match, re.I)
            except re.error:
                log.warning("MIDI preset %s: its match %r is not a regex; it matches its device name only", path.name, match)
                match = ""
        if not any(pages.values()) or not (device or match):
            continue
        out.append({"id": path.stem, "device": device, "match": match, "label": str(j.get("label") or device or path.stem)[:80],
                    "profile": str(j.get("profile") or "generic")[:32], "port": str(j.get("port") or device)[:96],
                    "saved": str(j.get("saved") or ""), "pages": pages})
    return out


def preset_for(name: str, presets: list[dict] | None = None) -> dict | None:
    """The first shipped preset for a port name: its regex matches the name, or it was saved from that device."""
    for p in load_presets() if presets is None else presets:
        if p.get("match") and re.search(p["match"], name, re.I):
            return p
        if p.get("device") and same_device(p["device"], name):
            return p
    return None


def save_preset(body: dict) -> dict:
    """Write a device's map as a shipped preset (configs/midi_presets/<device>.json), for the repository: the next
    clean install with that controller plugged in starts from it."""
    body = body if isinstance(body, dict) else {}
    device = clean_device(body.get("device"))
    pages = _pages(body.get("pages"))
    if not any(pages.values()):
        raise ValueError("The map is empty: there is nothing to ship.")
    match = str(body.get("match") or default_match(device))
    try:
        re.compile(match, re.I)
    except re.error as exc:
        raise ValueError(f"The match {match!r} is not a regex: {exc}") from exc
    slug = re.sub(r"[^a-z0-9]+", "-", bare(device).lower()).strip("-")[:48] or "controller"
    preset = {"kind": "xenoform-midi-preset", "version": 1, "device": bare(device), "port": str(body.get("port") or device)[:96],
              "match": match, "label": str(body.get("label") or bare(device))[:80], "profile": str(body.get("profile") or "generic")[:32],
              "saved": time.strftime("%Y-%m-%dT%H:%M:%S"), "pages": pages}
    path = presets_dir() / f"{slug}.json"
    with _LOCK:
        _write(path, json.dumps(preset, indent=1) + "\n")
    return {"id": slug, "path": str(path), "preset": preset}


# ---------------------------------------------------------------- routes
router = APIRouter()


@router.get("/api/midi/maps")
def midi_maps() -> dict:
    data = load_maps()
    return {"file": str(maps_path()), "devices": data["devices"], "unreadable": bool(data.get("unreadable")),
            "presets": load_presets(), "presets_dir": str(presets_dir())}


@router.get("/api/midi/maps/{device:path}")
def midi_map(device: str) -> dict:
    try:
        name = clean_device(device)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"device": name, "map": get_map(name), "preset": preset_for(name)}


@router.put("/api/midi/maps/{device:path}")
def midi_map_put(device: str, body: dict | None = None) -> dict:
    try:
        entry = put_map(device, body or {})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"The map could not be saved in {maps_path()}: {exc}") from exc
    return {"ok": True, "device": entry["device"], "map": entry, "file": str(maps_path())}


@router.delete("/api/midi/maps/{device:path}")
def midi_map_delete(device: str, page: str = "") -> dict:
    if page and not page_ok(page):
        raise HTTPException(400, f"{page!r} is not a page name.")
    try:
        removed = delete_map(device, page)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "removed": removed}


@router.get("/api/midi/presets")
def midi_presets() -> dict:
    return {"dir": str(presets_dir()), "presets": load_presets()}


@router.post("/api/midi/presets")
def midi_preset_save(body: dict | None = None) -> dict:
    try:
        saved = save_preset(body or {})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"The preset could not be written in {presets_dir()}: {exc}") from exc
    return {"ok": True, **saved}
