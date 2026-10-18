"""Snap a clip's key moments onto a beat grid.

Ported from the beatlock edit list: map, crossfade, and a zoom crossfade.
Source times are fractional frames. Retimes that must survive a draft-fps
to final-fps change are stored in seconds and expanded with
``anchors_at_fps``.
"""

from __future__ import annotations

import os
import re
import subprocess

import numpy as np

FF = os.environ.get("FF", "ffmpeg")


def probe_size(path: str) -> tuple[int, int]:
    out = subprocess.run([FF, "-i", path], capture_output=True, text=True).stderr
    match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", out)
    if not match:
        raise RuntimeError(f"no video size in {path}")
    return int(match.group(1)), int(match.group(2))


def load(path: str, size: tuple[int, int] | None = None) -> np.ndarray:
    width, height = size or probe_size(path)
    raw = subprocess.run(
        [
            FF,
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            f"scale={width}:{height}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width, 3)


def save(frames: np.ndarray, path: str, fps: float = 24, crf: int = 10) -> None:
    count, height, width, _ = frames.shape
    process = subprocess.Popen(
        [
            FF,
            "-y",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            path,
        ],
        stdin=subprocess.PIPE,
    )
    assert process.stdin is not None
    process.stdin.write(np.ascontiguousarray(frames).tobytes())
    process.stdin.close()
    process.wait()


def beat_frames(n: int, bpm: float = 120, fps: float = 24, offset: float = 0, div: int = 1) -> list[int]:
    """Beat (or 1/div-beat) frames in ``[0, n)``. ``offset`` may be negative."""
    step = fps * 60.0 / bpm / div
    k0 = int(np.ceil(-offset / step)) if step else 0
    frames = []
    for k in range(k0, k0 + int(n / step) + 2 if step else k0):
        frame = offset + k * step
        if 0 <= frame < n:
            frames.append(int(round(frame)))
    return frames


def snap(frame: float, bpm: float = 120, fps: float = 24, offset: float = 0, div: int = 1) -> int:
    """Nearest grid frame to ``frame``."""
    step = fps * 60.0 / bpm / div
    if step <= 0:
        return int(round(frame))
    return int(round(offset + round((frame - offset) / step) * step))


def anchors_at_fps(anchors_s: list[tuple[float, float]] | list[list[float]], fps: float) -> list[tuple[float, float]]:
    """Expand second-based ``(src, dst)`` anchors onto a frame rate."""
    rate = float(fps)
    return [(float(src) * rate, float(dst) * rate) for src, dst in anchors_s]


def detect(frames: np.ndarray, cut_k: float = 3.0) -> dict:
    """Motion curve plus peak, hard cuts, and frozen frames.

    A cut is a frame whose mean abs diff exceeds ``cut_k`` times the local
    median and 6 levels. A frozen frame diffs by less than 0.15.
    """
    grey = frames[..., :3].mean(-1)[:, ::4, ::4].astype(np.float32)
    delta = np.r_[0, np.abs(np.diff(grey, axis=0)).mean((1, 2))]
    smooth = np.convolve(delta, np.ones(5) / 5, "same")
    medians = []
    for i in range(len(delta)):
        if i == 0:
            window = delta[:9]
        else:
            window = np.r_[delta[max(0, i - 8) : max(0, i - 2)], delta[i + 3 : i + 9]]
        medians.append(float(np.median(window)) if window.size else 0.0)
    med = np.asarray(medians)
    cuts = [
        i
        for i in range(1, len(delta))
        if delta[i] > cut_k * max(med[i], 0.5) and delta[i] > 6
    ]
    return {
        "motion": delta.round(2).tolist(),
        "peak": int(np.argmax(smooth)) if len(smooth) else 0,
        "cuts": cuts,
        "frozen": [i for i in range(1, len(delta)) if delta[i] < 0.15],
    }


def _sample(frames: np.ndarray, t: float) -> np.ndarray:
    t = float(np.clip(t, 0, len(frames) - 1))
    index = int(np.floor(t))
    frac = t - index
    if frac < 1e-3 or index + 1 >= len(frames):
        return frames[index].astype(np.float32)
    return frames[index].astype(np.float32) * (1 - frac) + frames[index + 1].astype(np.float32) * frac


def _zoom(img: np.ndarray, z: float, cx: float, cy: float) -> np.ndarray:
    """Scale about a normalized point. ``z < 1`` shrinks onto that point."""
    img = np.asarray(img, dtype=np.float32)
    height, width = img.shape[:2]
    if abs(z - 1) < 1e-3:
        return img
    scaled_w = max(1, int(round(width * z)))
    scaled_h = max(1, int(round(height * z)))
    ys = (np.arange(scaled_h) + 0.5) * (height / scaled_h) - 0.5
    xs = (np.arange(scaled_w) + 0.5) * (width / scaled_w) - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, height - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    fy = (ys - np.floor(ys)).astype(np.float32)[:, None, None]
    fx = (xs - np.floor(xs)).astype(np.float32)[None, :, None]
    top = img[y0][:, x0] * (1 - fx) + img[y0][:, x1] * fx
    bot = img[y1][:, x0] * (1 - fx) + img[y1][:, x1] * fx
    scaled = top * (1 - fy) + bot * fy
    out = np.zeros_like(img)
    origin_x = int(round(cx * width - cx * scaled_w))
    origin_y = int(round(cy * height - cy * scaled_h))
    left, top_i = max(0, origin_x), max(0, origin_y)
    right, bottom = min(width, origin_x + scaled_w), min(height, origin_y + scaled_h)
    if right > left and bottom > top_i:
        out[top_i:bottom, left:right] = scaled[top_i - origin_y : bottom - origin_y, left - origin_x : right - origin_x]
    return out


def anchors_to_pieces(anchors: list[tuple[float, int] | tuple[float, float]]) -> list[tuple]:
    """``[(src, dst), ...]`` becomes map pieces. Output length follows the last dst."""
    ordered = sorted(anchors, key=lambda item: item[1])
    pieces = []
    pairs = list(zip(ordered, ordered[1:]))
    for index, ((src0, dst0), (src1, dst1)) in enumerate(pairs):
        count = int(dst1) - int(dst0)
        if count <= 0:
            continue
        if index == len(pairs) - 1:
            pieces.append(("map", float(src0), float(src1), count + 1))
        else:
            end = float(src0) + (float(src1) - float(src0)) * (count - 1) / count
            pieces.append(("map", float(src0), end, count))
    return pieces


def render(frames: np.ndarray, pieces: list[tuple]) -> np.ndarray:
    """Render an edit list. ``('map', s0, s1, n)`` samples ``s0..s1`` inclusive."""
    out = []
    for piece in pieces:
        kind = piece[0]
        if kind == "map":
            _, src0, src1, count = piece
            for j in range(int(count)):
                out.append(_sample(frames, src0 + (src1 - src0) * j / max(int(count) - 1, 1)))
        elif kind == "xfade":
            _, a0, a1, b0, b1, count = piece
            for j in range(int(count)):
                u = (j + 0.5) / int(count)
                alpha = u * u * (3 - 2 * u)
                stream_a = _sample(frames, a0 + (a1 - a0) * j / max(int(count) - 1, 1))
                stream_b = _sample(frames, b0 + (b1 - b0) * j / max(int(count) - 1, 1))
                out.append(stream_a * (1 - alpha) + stream_b * alpha)
        elif kind == "xfadez":
            _, a0, a1, b0, b1, count, cx, cy, z0 = piece
            for j in range(int(count)):
                u = (j + 0.5) / int(count)
                alpha = u * u * (3 - 2 * u)
                stream_a = _sample(frames, a0 + (a1 - a0) * j / max(int(count) - 1, 1))
                stream_b = _zoom(
                    _sample(frames, b0 + (b1 - b0) * j / max(int(count) - 1, 1)),
                    z0 + (1 - z0) * alpha,
                    cx,
                    cy,
                )
                out.append(stream_a * (1 - alpha) + stream_b * alpha)
        else:
            raise ValueError(piece)
    if not out:
        return np.zeros((0,) + frames.shape[1:], dtype=np.uint8)
    return np.clip(np.stack(out), 0, 255).astype(np.uint8)


def sample_video(path: str, step: int = 12, width: int = 96, height: int = 54) -> np.ndarray:
    """Every ``step``-th frame, scaled down, for the critic."""
    raw = subprocess.run(
        [
            FF,
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            f"select='not(mod(n\\,{int(step)}))',scale={int(width)}:{int(height)}",
            "-vsync",
            "vfr",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    frame_bytes = int(width) * int(height) * 3
    count = len(raw) // frame_bytes
    if count <= 0:
        return np.zeros((0, height, width, 3), dtype=np.uint8)
    return np.frombuffer(raw[: count * frame_bytes], np.uint8).reshape(count, height, width, 3)
