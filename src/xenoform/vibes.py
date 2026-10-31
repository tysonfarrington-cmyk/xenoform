"""The vibe registry: the extended vibes in ``configs/vibes.json``.

The seven original vibes keep their hand-tuned entries in ``morph_pass`` and
``configs/autotune.json``; this module adds the rest. Each entry carries the
morph look (prompt fragment), a negative, palette, lighting, material, motion
notes, LTX 0.9.5 morph settings and recommended transitions per boundary kind.
Autotune results still win over the registry's ``ltx`` block.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[2] / "configs" / "vibes.json"
OBJECTS = Path(__file__).resolve().parent / "ui_static" / "objects" / "objects.json"
ORIGINAL = ("liquid-gold", "paper-summer", "bloom", "neon-night", "ocean", "cosmic", "black")
LIBRARY = Path(__file__).resolve().parent / "ui_static" / "library"
STILLS = Path(__file__).resolve().parent / "ui_static" / "vibes"
CUTS = Path(__file__).resolve().parents[2] / "examples" / "cuts"  # the example cuts: cuts.json and one mp4 a vibe

# The seven originals' desk metadata (name, one line, palette, register, tone). The server owns this table;
# app.js keeps a copy only as the offline fallback. The look prompts stay in morph_pass / configs/autotune.json.
ORIGINAL_META: tuple[dict, ...] = (
    {"id": "liquid-gold", "name": "Liquid gold", "line": "A gold pour becomes a ring in a dark forge.",
     "palette": "gold", "register": "pynchon", "morph": True, "dark": False, "tone": "bright"},
    {"id": "paper-summer", "name": "Paper summer", "line": "A paper boat crosses a bright kitchen.",
     "palette": "neutral", "register": "rome", "morph": False, "dark": False, "tone": "bright"},
    {"id": "bloom", "name": "Bloom", "line": "A flower opens on a green hill.",
     "palette": "bronze", "register": "tolkien", "morph": False, "dark": False, "tone": "soft"},
    {"id": "neon-night", "name": "Neon night", "line": "A neon sign holds one quiet street.",
     "palette": "violet", "register": "lecarre", "morph": False, "dark": True, "tone": "dark"},
    {"id": "ocean", "name": "Ocean", "line": "A swimmer crosses a calm harbour.",
     "palette": "grey-green", "register": "tolkien", "morph": False, "dark": False, "tone": "bright"},
    {"id": "cosmic", "name": "Cosmic", "line": "A star field turns over a dark shore.",
     "palette": "violet", "register": "pynchon", "morph": True, "dark": True, "tone": "dark"},
    {"id": "black", "name": "Black", "line": "Black glass grows from one living form into the next.",
     "palette": "violet", "register": "pynchon", "morph": True, "dark": True, "tone": "dark"},
)


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"vibes": []}


def registry() -> dict:
    return _load(os.environ.get("XENO_VIBES", str(REGISTRY)))


def every() -> list[dict]:
    """Every registry entry, including ones whose assets are still being made."""
    return list(registry().get("vibes") or [])


def extended() -> list[dict]:
    """The registry vibes that ship assets (``ready`` is not false), in display order."""
    return [v for v in every() if v.get("ready", True)]


def featured() -> list[dict]:
    """The Simple-mode vibes (``featured`` > 0), in their featured order."""
    return sorted((v for v in extended() if int(v.get("featured") or 0) > 0), key=lambda v: int(v["featured"]))


def get(vibe: str) -> dict:
    return next((v for v in extended() if v.get("id") == vibe), {})


def pools() -> set[str]:
    """The vibes that ship their own object stills (keys of ``objects.json``)."""
    try:
        return set(json.loads(OBJECTS.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def pool(vibe: str) -> str:
    """The object pool a vibe's morph stills come from: its own when it ships one,
    else the registry's explicit ``pool`` (a vibe whose stills suit the look), else ``""``.
    The look prompt still comes from the vibe itself; only the guide stills are borrowed."""
    have = pools()
    if vibe in have:
        return vibe
    borrowed = str(get(vibe).get("pool") or "")
    return borrowed if borrowed in have else ""


def ids() -> list[str]:
    return list(ORIGINAL) + [v["id"] for v in extended() if v["id"] not in ORIGINAL]


def look(vibe: str) -> str:
    return str(get(vibe).get("look") or "")


def negative(vibe: str) -> str:
    return str(get(vibe).get("negative") or "")


def ltx(vibe: str) -> dict:
    return dict(get(vibe).get("ltx") or {})


def transitions(vibe: str) -> dict:
    return dict(get(vibe).get("transitions") or {})


def tags(vibe: str) -> tuple[str, ...]:
    return tuple(get(vibe).get("tags") or ())


def has_library(vibe: str) -> bool:
    """True when the vibe ships its own 4-shot library strip (``ui_static/library/<id>/wide.mp4``)."""
    return (LIBRARY / vibe / "wide.mp4").is_file()


def library_for(vibe: str) -> str:
    """The library folder a vibe's strip and preview clips come from: its own, else its ``pool``'s, else ``""``."""
    if has_library(vibe):
        return vibe
    borrowed = pool(vibe)
    return borrowed if borrowed and has_library(borrowed) else ""


def cuts_dir() -> Path:
    """The folder of example cuts: ``examples/cuts`` beside the repo's configs, or ``XENO_CUTS`` (tests point it at a temp dir)."""
    return Path(os.environ.get("XENO_CUTS") or CUTS)


@lru_cache(maxsize=4)
def _load_cuts(folder: str, stamp: tuple) -> tuple:
    try:
        data = json.loads((Path(folder) / "cuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(row for row in (data.get("cuts") or []) if isinstance(row, dict) and row.get("vibe") and row.get("file"))


def examples() -> list[dict]:
    """The example cuts whose file is on disk, each a manifest row plus ``url`` (what ``ui.py`` serves it under), in
    manifest order. A missing or bad ``cuts.json`` means none; one a vibe is the manifest's business, the first row wins."""
    folder = cuts_dir()
    try:
        st = (folder / "cuts.json").stat()
    except OSError:
        return []
    stamp = (st.st_mtime_ns, st.st_size)
    out, seen = [], set()
    for row in _load_cuts(str(folder), stamp):
        name = str(row["file"])
        if row["vibe"] in seen or "/" in name or "\\" in name or not (folder / name).is_file():
            continue
        seen.add(row["vibe"])
        out.append({**row, "url": f"/examples/cuts/{name}"})
    return out


def example(vibe: str) -> dict:
    """The example cut of ``vibe`` (``examples()`` row), or ``{}``."""
    return next((row for row in examples() if row["vibe"] == vibe), {})


def _row(meta: dict, *, featured: int, legacy: bool, eg: dict[str, str] | None = None) -> dict:
    vid = str(meta["id"])
    eg = {row["vibe"]: row["url"] for row in examples()} if eg is None else eg
    return {
        "id": vid,
        "name": str(meta.get("name") or vid),
        "line": str(meta.get("line") or ""),
        "palette": str(meta.get("palette") or "neutral"),
        "register": str(meta.get("register") or "pynchon"),
        "morph": bool(meta.get("morph", True)),
        "dark": bool(meta.get("dark", False)),
        "tone": str(meta.get("tone") or ("dark" if meta.get("dark") else "bright")),
        "still": f"/static/vibes/{vid}.jpg",
        "has_still": (STILLS / f"{vid}.jpg").is_file(),
        "featured": int(featured or 0),
        "pool": pool(vid),
        "has_library": has_library(vid),
        "library": library_for(vid),
        "example": str(eg.get(vid) or ""),  # a finished 15 s cut in this vibe (examples/cuts), "" when it has none
        "legacy": bool(legacy),
        "tags": list(meta.get("tags") or ()),
    }


def catalog() -> list[dict]:
    """Every vibe the desk can pick, one source of truth for ``GET /api/vibes``: the featured registry vibes
    in their featured order, then the originals that are not featured, then the rest of the ready registry.
    Non-featured rows carry ``legacy: true`` (Simple shows them behind "More vibes")."""
    rows: list[dict] = []
    seen: set[str] = set()
    eg = {row["vibe"]: row["url"] for row in examples()}
    for v in featured():
        rows.append(_row(v, featured=int(v.get("featured") or 0), legacy=False, eg=eg))
        seen.add(v["id"])
    for meta in ORIGINAL_META:
        if meta["id"] not in seen:
            rows.append(_row(meta, featured=0, legacy=True, eg=eg))
            seen.add(meta["id"])
    for v in extended():
        if v["id"] not in seen:
            rows.append(_row(v, featured=0, legacy=True, eg=eg))
            seen.add(v["id"])
    return rows
