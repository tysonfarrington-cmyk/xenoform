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
ORIGINAL = ("liquid-gold", "paper-summer", "bloom", "neon-night", "ocean", "cosmic", "black")


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"vibes": []}


def registry() -> dict:
    return _load(os.environ.get("XENO_VIBES", str(REGISTRY)))


def extended() -> list[dict]:
    """The registry vibes, in display order."""
    return list(registry().get("vibes") or [])


def get(vibe: str) -> dict:
    return next((v for v in extended() if v.get("id") == vibe), {})


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
