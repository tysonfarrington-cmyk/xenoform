"""A low-resolution animatic. Stills and crossfades, cut to the beat.

No checkpoint is loaded. The picture is a flat colour per section so a person
can see the cut before spending GPU time.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from xenoform.video import write_mp4

WIDTH = 192
HEIGHT = 96
FPS = 8
FADE = 4

_COLOURS = {
    "calm": (36, 44, 54),
    "build": (62, 74, 112),
    "drop": (176, 62, 40),
    "release": (46, 78, 62),
    "sustain": (88, 88, 94),
    "hold": (36, 44, 54),
    "climax": (176, 62, 40),
}


def _colour(label: str) -> tuple[int, int, int]:
    return _COLOURS.get(str(label or "").lower(), (72, 68, 64))


def _section(features: dict | None, when: float, scene: dict) -> str:
    for section in (features or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        start = float(section.get("start") or 0)
        end = float(section.get("end") or start)
        if start <= when < end:
            return str(section.get("label") or "")
    return str(scene.get("beat") or scene.get("section") or "sustain")


def _nearest_beat(when: float, beats: list, window: float = 0.45) -> float:
    best = None
    gap = window
    for beat in beats or []:
        try:
            stamp = float(beat)
        except (TypeError, ValueError):
            continue
        delta = abs(stamp - when)
        if delta <= gap:
            best = stamp
            gap = delta
    return when if best is None else best


def render_animatic(
    scenes: list | None,
    features: dict | None,
    out_path: str | Path,
    audio_path: str | Path | None = None,
) -> dict[str, Any]:
    """Write the preview mp4. Returns timing so a caller can prove it was fast."""
    started = time.perf_counter()
    features = features or {}
    rows = [scene for scene in (scenes or []) if isinstance(scene, dict)]
    duration = float(features.get("duration") or 0)
    if rows:
        duration = max(duration, max(float(scene.get("end") or 0) for scene in rows))
    if duration <= 0:
        duration = 2.0
    count = max(FADE + 1, int(round(duration * FPS)))
    frames = np.zeros((count, HEIGHT, WIDTH, 3), dtype=np.uint8)
    beats = list(features.get("beats") or [])
    cuts: list[int] = []
    if not rows:
        rows = [{"start": 0.0, "end": duration, "beat": "sustain"}]
    for scene in rows:
        start = float(scene.get("start") or 0)
        end = float(scene.get("end") or duration)
        landed = _nearest_beat(start, beats)
        colour = np.array(_colour(_section(features, start, scene)), dtype=np.uint8)
        begin = max(0, min(count, int(round(landed * FPS))))
        finish = max(begin + 1, min(count, int(round(end * FPS))))
        frames[begin:finish] = colour
        if begin > 0:
            cuts.append(begin)
    for cut in cuts:
        for offset in range(1, FADE + 1):
            left = cut - offset
            right = cut + offset - 1
            if left < 0 or right >= count:
                continue
            mix = offset / (FADE + 1)
            frames[left] = (frames[left].astype(np.float32) * mix + frames[right].astype(np.float32) * (1 - mix)).astype(np.uint8)
            frames[right] = (frames[right].astype(np.float32) * mix + frames[left].astype(np.float32) * (1 - mix)).astype(np.uint8)
    write_mp4(out_path, frames, FPS, audio_path=audio_path, crf=28)
    elapsed = time.perf_counter() - started
    return {
        "path": str(out_path),
        "frames": count,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "seconds": round(elapsed, 3),
        "cuts": len(cuts),
        "duration": round(count / FPS, 3),
    }
