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
