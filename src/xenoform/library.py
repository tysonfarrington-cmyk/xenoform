"""Pre-render the judges shot library. CPU only, small frames, committed once."""

from __future__ import annotations

import math
from pathlib import Path

from xenoform.render_cpu import form_from_frame, render_frame
from xenoform.video import write_mp4

SHOTS = (
    ("wide", "wide", "pull back", "wide", 0.32, 0.28, 0.18),
    ("medium", "medium", "follow", "studio", 0.5, 0.48, 0.34),
    ("close", "close", "push in", "studio", 0.78, 0.72, 0.55),
    ("reveal", "reveal", "pull back", "wide", 0.4, 0.3, 0.22),
)

LIBRARY_W = 160
LIBRARY_H = 90
LIBRARY_FPS = 12
LIBRARY_FRAMES = 14


def bake_shot_library(folder: str | Path, *, force: bool = False) -> list[Path]:
    """Write wide, medium, close, and reveal clips. Existing files are kept."""
    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for shot_id, shot, move, lens, energy, push, mutate in SHOTS:
        path = dest / f"{shot_id}.mp4"
        if path.exists() and path.stat().st_size > 500 and not force:
            written.append(path)
            continue
        frames = []
        for index in range(LIBRARY_FRAMES):
            t = index / LIBRARY_FPS
            row = {
                "bass": 0.32 + 0.2 * math.sin(t * 3.0 + mutate),
                "sub": 0.18 + 0.08 * mutate,
                "mid": 0.36 + 0.12 * math.sin(t * 1.4),
                "high": 0.22 + 0.2 * mutate,
                "mutate": mutate,
                "onset_env": 0.62 if index % 6 == 0 else 0.12,
                "t": t,
                "beat_env": 0.85 if index % 6 == 0 else 0.08,
                "shot": shot,
                "move": move,
                "lens": lens,
                "camera_energy": energy + 0.08 * math.sin(t * 2.0),
                "camera_push": push,
            }
            form = form_from_frame(row)
            rgb, _depth, _mask = render_frame(form, LIBRARY_W, LIBRARY_H, max_steps=6)
            frames.append(rgb)
        write_mp4(path, frames, LIBRARY_FPS, crf=28)
        written.append(path)
    return written
