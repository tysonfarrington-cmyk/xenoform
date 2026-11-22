"""Measure a Perform take (docs/ui_review/tools/perform_check.js runs this; it also runs alone).

The take was recorded with /vj?sync=1 over a click track: the picture is black and turns white for 50 ms from each
beat of the song's clock, and the song's beats are the clicks themselves. So in a take whose picture and sound share one
clock, each click in the sound and the rise of each white flash in the picture land together. This finds both and pairs
them:

- ``av``: the picture's flash minus the sound's click, per click (ms): the sync the acceptance asks for (within a frame);
- ``drift``: the click spacing in the take's sound against the source's (ms): the sound neither runs fast nor slips;
- ``source``: where each click sits in the take against where it sits in the song, given where the take started
  (``--start-pos``), so the offset of the take's sound against the source is a number too;
- ``corner``: the reddest pixel in the top corners (where a REC dot or a HUD would sit) across every frame: a take is the
  canvas and nothing else, so this stays at the picture's own level;
- ``size`` and ``fps`` of the file.

Usage: python perform_sync.py TAKE [--period 0.5] [--first 0.25] [--start-pos 0] [--json]
Needs ffmpeg and ffprobe on PATH, and numpy.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

import numpy as np

SR = 48000
W, H = 64, 36  # every frame, scaled down: enough for a mean and the corners


def _run(cmd: list[str]) -> bytes:
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def probe(path: str) -> dict:
    out = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
                "-of", "json", path])
    st = (json.loads(out).get("streams") or [{}])[0]
    num, _, den = str(st.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {"width": int(st.get("width") or 0), "height": int(st.get("height") or 0), "fps": round(fps, 3)}


def audio(path: str) -> np.ndarray:
    """The sound on the file's own timeline: raw samples lose the stream's start time (a webm's sound may start 30 ms
    after its picture, an mp4's AAC a priming frame earlier), so silence pads it out to where the container puts it."""
    raw = _run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-af", f"aresample={SR}:async=1:first_pts=0", "-ac", "1", "-f", "f32le", "-"])
    return np.frombuffer(raw, dtype=np.float32)


def clicks(x: np.ndarray, quiet_ms: float = 30.0) -> list[float]:
    """Onsets of short bursts: the first sample over half the peak after at least ``quiet_ms`` under a tenth of it."""
    if not len(x):
        return []
    a = np.abs(x)
    peak = float(np.percentile(a, 99.99)) or float(a.max())
    hi, lo = 0.5 * peak, 0.1 * peak
    quiet = int(SR * quiet_ms / 1000)
    out, last_loud, start = [], -10 * quiet, None
    for i in np.flatnonzero(a > lo):
        if i - last_loud > quiet:
            start = i  # a new burst: its first sample over a tenth of the peak
        if start is not None and a[i] > hi:
            out.append(start / SR)
            start = None
        last_loud = i
    return out


def frames(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Every decoded frame (no frame made up or dropped) as a small RGB image, with its presentation time."""
    times = _run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time,best_effort_timestamp_time",
                  "-of", "csv=p=0", path]).decode().split()
    ts = []
    for row in times:
        vals = [v for v in row.split(",") if v not in ("", "N/A")]
        ts.append(float(vals[0]) if vals else float("nan"))
    raw = _run(["ffmpeg", "-v", "error", "-i", path, "-fps_mode", "passthrough", "-vf", f"scale={W}:{H}:flags=area", "-pix_fmt", "rgb24",
                "-f", "rawvideo", "-"])
    pix = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W, 3)
    n = min(len(ts), len(pix))
    return np.asarray(ts[:n], dtype=float), pix[:n]


def flashes(ts: np.ndarray, pix: np.ndarray) -> list[float]:
    """Where the picture rises to white: the first frame of each run over half way between dark and white."""
    luma = pix.astype(np.float32).mean(axis=(1, 2, 3))
    lo, hi = float(np.percentile(luma, 5)), float(np.percentile(luma, 99.5))
    thr = lo + 0.5 * (hi - lo)
    up = luma > thr
    return [float(ts[i]) for i in range(len(up)) if up[i] and (i == 0 or not up[i - 1])]


def corner_red(pix: np.ndarray) -> int:
    """The reddest pixel in the top-left and top-right corners over every frame: red minus the larger of green and blue."""
    k = 6
    corners = np.concatenate([pix[:, :k, :k, :], pix[:, :k, -k:, :]], axis=2).astype(np.int16)
    red = corners[..., 0] - np.maximum(corners[..., 1], corners[..., 2])
    return int(red.max()) if red.size else 0


def pair(a: list[float], v: list[float], within: float = 0.2) -> list[float]:
    out = []
    for t in a:
        if not v:
            break
        k = int(np.argmin([abs(x - t) for x in v]))
        if abs(v[k] - t) <= within:
            out.append(v[k] - t)
    return out


def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    arr = np.asarray(xs) * 1000.0
    return {"n": int(len(arr)), "median_ms": round(float(np.median(arr)), 1), "mean_ms": round(float(arr.mean()), 1),
            "min_ms": round(float(arr.min()), 1), "max_ms": round(float(arr.max()), 1), "max_abs_ms": round(float(np.abs(arr).max()), 1)}


def measure(path: str, period: float = 0.5, first: float = 0.25, start_pos: float | None = None) -> dict:
    info = probe(path)
    snd = clicks(audio(path))
    ts, pix = frames(path)
    pic = flashes(ts, pix)
    av = pair(snd, pic)
    out = {"file": path, **info, "frames": int(len(ts)), "clicks": len(snd), "flashes": len(pic), "av": stats(av),
           "frame_ms": round(1000.0 / info["fps"], 1) if info["fps"] else None, "corner_red": corner_red(pix)}
    if len(snd) >= 2:  # the take's clicks against the source's grid: spacing (drift) and, given the start, the offset
        k = np.round((np.asarray(snd) - snd[0]) / period)
        out["drift"] = stats(list((np.asarray(snd) - snd[0]) - k * period))
        if start_pos is not None:
            src_k = np.round((np.asarray(snd) + start_pos - first) / period)
            out["source"] = stats(list(np.asarray(snd) - (first + src_k * period - start_pos)))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("take")
    ap.add_argument("--period", type=float, default=0.5)
    ap.add_argument("--first", type=float, default=0.25)
    ap.add_argument("--start-pos", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("ffmpeg and ffprobe must be on PATH", file=sys.stderr)
        return 2
    res = measure(a.take, a.period, a.first, a.start_pos)
    print(json.dumps(res, indent=None if a.json else 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
