"""Clean anchor stills for real-world subjects (planets, the Moon).

Letting a model invent Jupiter gives two Great Red Spots and cartoon bands.
When a shot names a subject in ``configs/anchors.json`` the desk uses the
manifest's public-domain photograph (also listed as a kind=image item in assets/library/manifest.json) as the first/last keyframe instead of a
painted still, with a hardened prompt and negative and a lower freedom (the
guide strength stays high and the morph's end guide is not relaxed).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs" / "anchors.json"
STATIC = Path(__file__).resolve().parent / "ui_static"
HARDEN = "photoreal, one single subject, every feature appears once, accurate real-world detail, no duplicated features"
HARD_NEGATIVE = "duplicate features, repeated features, extra copies, cartoon, illustration, warped, melted, deformed"
# Anchored shots get less freedom: the end guide stays at full strength and no
# compression, so the model interpolates the photograph rather than repainting it.
ANCHOR_TUNE = {"guide_end_strength": 1.0, "img_compression": 0, "cfg": 3.0}


@lru_cache(maxsize=2)
def _manifest(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def manifest() -> dict:
    return _manifest(str(MANIFEST))


def subject_in(text: str) -> str:
    """The first manifest subject named as a whole word in ``text``, or ''."""
    low = str(text or "").lower()
    for name in manifest():
        if re.search(rf"\b{re.escape(name)}\b", low):
            return name
    return ""


def anchor_for(text: str) -> dict:
    """``{"name", "path", "prompt", "negative", ...}`` for a named real subject, else {}."""
    name = subject_in(text)
    if not name:
        return {}
    row = dict(manifest()[name])
    path = ROOT / row["file"]
    if not path.is_file():
        return {}
    row["name"] = name
    row["path"] = str(path)
    return row


def harden(prompt: str, text: str = "") -> str:
    """Add single-feature, photoreal constraints when the shot names a real subject."""
    row = anchor_for(text or prompt)
    if not row:
        return prompt
    return f"{prompt}, {row.get('prompt', '')}, {HARDEN}".strip(", ")


def harden_negative(negative: str, text: str) -> str:
    row = anchor_for(text)
    if not row:
        return negative
    return ", ".join(x for x in (negative, row.get("negative", ""), HARD_NEGATIVE) if x)
