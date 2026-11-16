"""What a composed mp4 looks like, for a test that compares one across ffmpeg builds.

A byte-for-byte check of a composed file holds only on the ffmpeg build that wrote the fixture (x264 of another
version, or another platform's build, writes other bytes for the same frames). Decoding, though, is bit-exact for
H.264, so a frame-by-frame measure of the decoded picture is the same wherever the same frames were encoded, within
the encoder's own loss. ``luma_signature`` is that measure: the mean grey level of every frame, with the size and
frame count; ``same_picture`` compares two within a tolerance; ``ffmpeg_build`` names the build that made a file.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np


def ffmpeg_build() -> str:
    """The first line of ``ffmpeg -version`` ("ffmpeg version 8.1.1-full_build-www.gyan.dev ...", up to the copyright)."""
    exe = shutil.which("ffmpeg") or "ffmpeg"
    out = subprocess.run([exe, "-version"], capture_output=True, text=True, check=False).stdout
    first = out.splitlines()[0] if out else ""
    return first.split(" Copyright", 1)[0].strip()


def luma_signature(path: str | Path, size: tuple[int, int] = (48, 27)) -> dict:
    """The decoded picture, small: ``frames``, the mean grey level of each frame (0 to 255, two decimals) and the
    file's own width, height and frame rate from ffprobe."""
    exe = shutil.which("ffmpeg") or "ffmpeg"
    probe = shutil.which("ffprobe") or "ffprobe"
    w, h = size
    raw = subprocess.run([exe, "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8)
    n = len(frames) // (w * h)
    means = frames[: n * w * h].reshape(n, w * h).mean(axis=1)
    info = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                           "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    parts = info.split(",") if info else []
    return {"frames": int(n), "width": int(parts[0]) if len(parts) > 0 else 0, "height": int(parts[1]) if len(parts) > 1 else 0,
            "fps": parts[2] if len(parts) > 2 else "", "luma": [round(float(m), 2) for m in means]}


def same_picture(got: dict, want: dict, *, max_diff: float = 6.0, mean_diff: float = 2.0, frames_off: int = 1) -> str:
    """"" when ``got`` shows the same picture as ``want``: the same size and frame rate, the frame count within
    ``frames_off``, and every frame's mean grey level within ``max_diff`` levels with the average gap under
    ``mean_diff``; else one line saying what differs."""
    for key in ("width", "height", "fps"):
        if got.get(key) != want.get(key):
            return f"{key}: {got.get(key)} against the fixture's {want.get(key)}"
    a, b = list(got.get("luma") or []), list(want.get("luma") or [])
    if abs(len(a) - len(b)) > frames_off:
        return f"frames: {len(a)} against the fixture's {len(b)}"
    n = min(len(a), len(b))
    if n == 0:
        return "no frames decoded"
    gaps = np.abs(np.asarray(a[:n]) - np.asarray(b[:n]))
    if gaps.max() > max_diff or gaps.mean() > mean_diff:
        k = int(gaps.argmax())
        return f"frame {k}: grey {a[k]} against the fixture's {b[k]} (largest gap {gaps.max():.2f}, mean {gaps.mean():.2f})"
    return ""
