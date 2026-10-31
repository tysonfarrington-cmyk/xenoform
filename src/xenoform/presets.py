"""Chain presets: the loved chains as one click (``configs/chain_presets.json``; Stage 4 of docs/MUSIC_VIDEO_PLAN.md).

A preset is a vibe, an idea line, the stills pinned slot by slot (the Make body's ``chain_pins``) and the settings the
chain was loved with: morph style, timing, effects, look, foreshadow, the four knobs, the seed and the Backdrop (``plain``:
every loved chain stood on the vibe's own studio ground, so a vibe that has grown places does not change it) and the
Shape (``breathe`` and ``drop_mode``: every loved chain was cut before the Shape row, so a row that does not say is
Breathe off with Drops off, and a re-make comes out as it was). The desk shows them as chips beside the idea line (``GET /api/presets``); a click sets the vibe, the line, the pins and the Fine-tune rows in one
go, and never the tier (a preset made on Cloud Final does not tick the credits box: a Make is still the user's to start).

``load()`` reads the file (a missing or bad file means none; a bad row is dropped, a bad field falls back to the desk's
own default, a pin whose still is nowhere is dropped and the others hold), ``get(id)`` one preset, ``body(preset)`` the
Make-body keys it sets. Rules and bans (what a cut must never do) come with the taste file, not here.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

PATH = Path(__file__).resolve().parents[2] / "configs" / "chain_presets.json"
KNOBS = ("intensity", "speed", "chaos", "glow")
DEFAULT_SEED = 2727


def path() -> Path:
    return Path(os.environ.get("XENO_PRESETS") or PATH)


@lru_cache(maxsize=4)
def _read(file: str, stamp: tuple) -> tuple:
    try:
        data = json.loads(Path(file).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    rows = data.get("presets") if isinstance(data, dict) else None
    return tuple(r for r in rows or () if isinstance(r, dict))


def _looks() -> set[str]:
    from xenoform import dance_fx, effects

    return {"auto", "off", *dance_fx.PRESETS, *effects.LOOKS}


def _pin_exists(file: str) -> bool:
    """A pinned still is real when it is an image in the shipped folder or in this machine's stills folder."""
    from xenoform import stills

    for base in (stills.SHIPPED, stills.root()):
        try:
            target = (Path(base) / file).resolve()
            if target.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp") and target.is_file() and target.is_relative_to(Path(base).resolve()):
                return True
        except (OSError, ValueError):
            continue
    return False


def _breathe(raw) -> float:
    """A row's Breathe: true is the bold profile (1.0), a number its amount; anything else (a missing key, a word) is
    off, as every loved chain was cut."""
    from xenoform.pacing import amount_of

    return amount_of(raw) if isinstance(raw, (bool, int, float)) else 0.0


def clean(row: dict) -> dict | None:
    """One preset as the desk can use it, or None when it is not one (no id, no name, or a vibe the registry does not know)."""
    from xenoform import effects, morph_pass, morph_style, morph_timing, pacing, simple_recipe, vibes

    pid = re.sub(r"[^a-z0-9-]+", "-", str(row.get("id") or "").lower()).strip("-")
    name = str(row.get("name") or "").strip()[:60]
    vibe = str(row.get("vibe") or "")
    if not pid or not name or vibe not in vibes.ids():
        return None
    pins: dict[str, str] = {}
    raw = row.get("pins") if isinstance(row.get("pins"), dict) else {}
    for slot in sorted((s for s in raw if str(s).isdigit()), key=int):
        text = str(raw[slot] or "").strip().replace("\\", "/")
        if text and ".." not in text.split("/") and not text.startswith("/") and ":" not in text and _pin_exists(text):
            pins[str(int(slot))] = text
    style = str(row.get("morph_style") or "auto").lower()
    timing = str(row.get("morph_timing") or "smooth").lower()
    look = str(row.get("look") or "auto")
    foreshadow = str(row.get("foreshadow") or "auto").lower()
    backdrop = str(row.get("backdrop") or "plain").lower()  # every loved chain stood on the vibe's own studio ground
    drop_mode = str(row.get("drop_mode") or "off").lower()  # and was cut before the Shape row: Drops off, Breathe off
    knobs = {}
    for key in KNOBS:
        try:
            value = float((row.get("knobs") or {}).get(key))
        except (TypeError, ValueError):
            continue
        knobs[key] = round(min(1.0, max(0.0, value)), 3)
    try:
        seed = int(row.get("seed") or DEFAULT_SEED)
    except (TypeError, ValueError):
        seed = DEFAULT_SEED
    return {
        "id": pid,
        "name": name,
        "vibe": vibe,
        "line": str(row.get("line") or "")[:240],
        "idea": str(row.get("idea") or "")[:170],
        "pins": pins,
        "morph_style": style if style in morph_style.STYLES else "auto",
        "morph_timing": timing if timing in morph_timing.MODES else "smooth",
        "effects": [e for e in (row.get("effects") or []) if e in effects.NAMES] if isinstance(row.get("effects"), list) else [],
        "look": look if look in _looks() else "auto",
        "foreshadow": foreshadow if foreshadow in simple_recipe.FORESHADOW else "auto",
        "backdrop": backdrop if backdrop in morph_pass.BACKDROPS else "plain",
        "breathe": _breathe(row.get("breathe")),
        "drop_mode": drop_mode if drop_mode in pacing.DROP_MODES else "off",
        "knobs": knobs,
        "seed": seed,
        "engine": str(row.get("engine") or ""),
        "tys": [str(t) for t in row.get("tys") or [] if str(t).strip()] if isinstance(row.get("tys"), list) else [],
        "note": str(row.get("note") or ""),
        "morphs": [str(m) for m in row.get("morphs") or []] if isinstance(row.get("morphs"), list) else [],
        "source": dict(row["source"]) if isinstance(row.get("source"), dict) else {},
    }


def load() -> list[dict]:
    """Every preset in the file, cleaned, in file order (an id twice keeps its first row). ``[]`` for a missing or bad file."""
    file = path()
    try:
        st = file.stat()
    except OSError:
        return []
    out, seen = [], set()
    for row in _read(str(file), (st.st_mtime_ns, st.st_size)):
        preset = clean(row)
        if preset and preset["id"] not in seen:
            seen.add(preset["id"])
            out.append(preset)
    return out


def get(preset_id: str) -> dict:
    return next((p for p in load() if p["id"] == str(preset_id or "")), {})


def body(preset: dict) -> dict:
    """The Make-body keys a preset sets: ``vibe``, ``idea``, ``chain_pins`` (slot -> still), ``morph_style``, ``morph_timing``,
    ``effects``, ``dance_fx`` (the look), ``foreshadow``, ``backdrop``, the Shape (``breathe``, ``drop_mode``), ``macros`` (the
    four knobs) and ``seed``. Not the tier, not the song, not the length: a preset says what the cut is made of, not what it
    costs."""
    return {
        "vibe": preset["vibe"],
        "idea": preset["idea"],
        "chain_pins": dict(preset["pins"]),
        "morph_style": preset["morph_style"],
        "morph_timing": preset["morph_timing"],
        "effects": list(preset["effects"]),
        "dance_fx": preset["look"],
        "foreshadow": preset["foreshadow"],
        "backdrop": preset["backdrop"],
        "breathe": preset["breathe"],
        "drop_mode": preset["drop_mode"],
        "macros": dict(preset["knobs"]),
        "seed": preset["seed"],
    }


def public(preset: dict) -> dict:
    """The preset as ``GET /api/presets`` serves it: the cleaned row, a chip thumbnail (its first pinned still) and its Make body."""
    first = next(iter(sorted(preset["pins"].items(), key=lambda kv: int(kv[0]))), None)
    return {**preset, "thumb": ("/api/stills/thumb?file=" + quote(first[1], safe="/")) if first else "", "body": body(preset)}
