"""Post-render and source QA: lag, low resolution, artifacts, beat alignment.

Everything here is ffmpeg + numpy on the CPU (no GPU, no ComfyUI). Thresholds live in
``configs/guardrails.json`` (lag_qa, source_quality, artifact_qa, beat_alignment).

- ``lag_report``      freezedetect + mpdecimate (held / duplicate frames) + fps mismatch
- ``fix_lag``         conform to the project fps, or retime held frames with motion interpolation
- ``source_quality``  native size + Laplacian-variance sharpness -> ok / upscale / reject
- ``artifact_scan``   heavy chromatic aberration or glitch rows (non-VJ shots only)
- ``beat_report``     cuts more than ~40 ms off the beat grid; ``snap_cuts`` fixes a cut list
- ``run``             all of it on a finished render, for the job report
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np


def _rules() -> dict:
    from xenoform.guardrails import rules
    return rules()


def _rule(name: str) -> dict:
    return _rules().get(name) or {}


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"


# ------------------------------------------------------------------ probing
def probe(path: str | Path) -> dict:
    out = subprocess.run([_ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    data = json.loads(out.stdout or "{}")
    st = (data.get("streams") or [{}])[0]
    def rate(v):
        try:
            return float(Fraction(str(v)))
        except (ValueError, ZeroDivisionError):
            return 0.0
    fps = rate(st.get("avg_frame_rate")) or rate(st.get("r_frame_rate"))
    dur = float((data.get("format") or {}).get("duration") or 0.0)
    try:
        nb = int(st.get("nb_frames") or 0)
    except ValueError:
        nb = 0
    return {"width": int(st.get("width") or 0), "height": int(st.get("height") or 0), "fps": round(fps, 3),
            "duration": dur, "frames": nb or int(round(dur * fps))}


def frames_at(path: str | Path, times: list[float], short: int = 360) -> list[np.ndarray]:
    """RGB frames at the given times, scaled so the short side is ``short`` (never upscaled)."""
    info = probe(path)
    w, h = info["width"] or 640, info["height"] or 360
    s = min(1.0, short / max(1, min(w, h)))
    tw, th = max(2, int(w * s) // 2 * 2), max(2, int(h * s) // 2 * 2)
    out = []
    for t in times:
        seek = ["-ss", f"{t:.3f}"] if t > 0.001 else []  # -ss 0 on a still image yields no frame
        raw = subprocess.run([_ffmpeg(), "-v", "error", *seek, "-i", str(path), "-frames:v", "1",
                              "-vf", f"scale={tw}:{th}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, timeout=60).stdout
        if len(raw) >= tw * th * 3:
            out.append(np.frombuffer(raw[:tw * th * 3], np.uint8).reshape(th, tw, 3))
    return out


def _sample_times(dur: float, n: int) -> list[float]:
    if dur <= 0:
        return [0.0]
    return [dur * (i + 0.5) / n for i in range(n)]


# ------------------------------------------------------------------ lag
def freeze_ranges(path: str | Path, noise: float = 0.003, min_s: float = 0.25) -> list[tuple[float, float]]:
    err = subprocess.run([_ffmpeg(), "-v", "info", "-i", str(path), "-map", "0:v:0", "-vf",
                          f"freezedetect=n={noise}:d={min_s}", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=600).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    dur = probe(path)["duration"]
    return [(a, ends[i] if i < len(ends) else dur) for i, a in enumerate(starts)]


def kept_frames(path: str | Path) -> int:
    """Frames left after mpdecimate drops near-duplicates."""
    err = subprocess.run([_ffmpeg(), "-v", "info", "-i", str(path), "-map", "0:v:0", "-vf", "mpdecimate",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=600).stderr
    got = re.findall(r"frame=\s*(\d+)", err)
    return int(got[-1]) if got else 0


def lag_report(path: str | Path, fps: float = 24.0) -> dict:
    r = _rule("lag_qa")
    info = probe(path)
    freezes = freeze_ranges(path, float(r.get("freeze_noise", 0.003)), float(r.get("freeze_min_s", 0.25)))
    total = max(1, info["frames"])
    kept = kept_frames(path) or total
    dup = max(0.0, 1.0 - kept / total)
    frozen_s = sum(b - a for a, b in freezes)
    issues = []
    if abs(info["fps"] - fps) > 0.05:
        issues.append(f"fps {info['fps']} does not match the project's {fps}")
    if dup > float(r.get("max_dup_ratio", 0.15)):
        issues.append(f"{dup:.0%} duplicate/held frames (judder)")
    short = [f for f in freezes if f[1] - f[0] <= float(r.get("lag_freeze_max_s", 0.6))]
    if len(short) >= int(r.get("max_short_freezes", 3)):
        issues.append(f"{len(short)} short freezes read as lag")
    return {"fps": info["fps"], "project_fps": fps, "frames": total, "kept": kept, "dup_ratio": round(dup, 4),
            "freezes": [[round(a, 3), round(b, 3)] for a, b in freezes], "frozen_s": round(frozen_s, 3),
            "short_freezes": len(short), "issues": issues, "lag": bool(issues)}


def conform(src: str | Path, dest: str | Path, fps: float = 24.0, interpolate: bool = False) -> Path:
    """Re-time to the project fps. ``interpolate`` fills held frames by motion interpolation
    (mpdecimate keeps the timestamps, minterpolate fills the gaps), so the length and sync stay."""
    vf = f"mpdecimate,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1" if interpolate else f"fps={fps}"
    dest = Path(dest)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                    str(dest)], check=True, timeout=1800)
    return dest


def fix_lag(path: str | Path, report: dict, fps: float = 24.0) -> dict:
    """Fix in place. fps mismatch -> conform; judder / short freezes -> interpolate held frames."""
    path = Path(path)
    if not report.get("lag"):
        return {"fixed": False}
    interp = report["dup_ratio"] > float(_rule("lag_qa").get("max_dup_ratio", 0.15)) or report["short_freezes"] >= int(
        _rule("lag_qa").get("max_short_freezes", 3))
    tmp = path.with_name(path.stem + ".qa.mp4")
    conform(path, tmp, fps, interpolate=interp)
    tmp.replace(path)
    return {"fixed": True, "method": "interpolate held frames" if interp else f"conform to {fps} fps"}


# ------------------------------------------------------------------ sources
def laplacian_var(img: np.ndarray) -> float:
    g = img.astype(np.float32)
    if g.ndim == 3:
        g = g @ np.array([0.299, 0.587, 0.114], np.float32)
    lap = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] - 4 * g[1:-1, 1:-1]
    return float(lap.var()) if lap.size else 0.0


def motion_score(frames: list[np.ndarray]) -> float:
    """0..1: mean absolute change between sampled frames (0 = frozen)."""
    if len(frames) < 2:
        return 0.0
    d = [np.abs(a.astype(np.float32) - b.astype(np.float32)).mean() for a, b in zip(frames, frames[1:])]
    return round(float(min(1.0, np.mean(d) / 12.0)), 4)


def source_quality(path: str | Path, out_w: int = 1080, out_h: int = 1920, *, video: bool | None = None) -> dict:
    r = _rule("source_quality")
    info = probe(path)
    w, h = info["width"], info["height"]
    dur = info["duration"]
    is_video = (dur > 0.2) if video is None else video
    frames = frames_at(path, _sample_times(dur, 3) if is_video else [0.0], short=360)
    sharp = float(np.median([laplacian_var(f) for f in frames])) if frames else 0.0
    short, out_short = min(w, h), min(out_w, out_h)
    min_sharp = float(r.get("min_sharpness", 60.0))
    up = float(r.get("upscale_factor", 4))
    if short >= out_short and sharp >= min_sharp:
        verdict = "ok"
    elif short * up >= out_short and short >= int(r.get("min_short_side", 360)) and sharp >= min_sharp * 0.5:
        verdict = "upscale"
    else:
        verdict = "reject"
    out = {"width": w, "height": h, "sharpness": round(sharp, 1), "verdict": verdict,
           "soft": sharp < min_sharp or short < int(r.get("min_short_side", 360))}
    if is_video:
        mf = frames_at(path, _sample_times(dur, 6), short=180)
        out["motion_score"] = motion_score(mf)
    return out


# ------------------------------------------------------------------ artifacts
def chroma_shift_px(img: np.ndarray, max_shift: int = 6) -> int:
    """Horizontal R-vs-B edge misalignment in pixels (0 on a clean frame)."""
    f = img.astype(np.float32)
    rx = np.abs(np.diff(f[..., 0], axis=1))
    bx = np.abs(np.diff(f[..., 2], axis=1))
    if rx.mean() < 1.0:
        return 0
    best, score = 0, -1.0
    for s in range(-max_shift, max_shift + 1):
        a = rx[:, max(0, s):rx.shape[1] + min(0, s)]
        b = bx[:, max(0, -s):bx.shape[1] + min(0, -s)]
        c = float((a * b).mean())
        if c > score:
            best, score = s, c
    return abs(best)


def glitch_rows(img: np.ndarray) -> float:
    """Fraction of rows that jump hard from the row above (tearing / datamosh bands)."""
    g = img.astype(np.float32).mean(axis=2)
    d = np.abs(np.diff(g, axis=0)).mean(axis=1)
    med = float(np.median(d)) + 1.0
    return float((d > 8.0 * med).mean())


def artifact_scan(path: str | Path, *, vj: bool = False, samples: int = 10) -> dict:
    r = _rule("artifact_qa")
    if vj:
        return {"skipped": "VJ shots may glitch on purpose", "flags": []}
    dur = probe(path)["duration"]
    flags = []
    times = _sample_times(dur, samples)
    for t, f in zip(times, frames_at(path, times, short=360)):
        ca, gl = chroma_shift_px(f), glitch_rows(f)
        if ca >= int(r.get("max_chroma_px", 3)):
            flags.append({"t": round(t, 2), "kind": "chromatic aberration", "px": ca})
        if gl >= float(r.get("max_glitch_rows", 0.03)):
            flags.append({"t": round(t, 2), "kind": "glitch", "rows": round(gl, 3)})
    return {"flags": flags}


# ------------------------------------------------------------------ beats
def cut_times(path: str | Path, threshold: float = 0.3) -> list[float]:
    err = subprocess.run([_ffmpeg(), "-v", "info", "-i", str(path), "-map", "0:v:0", "-vf",
                          f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                         capture_output=True, text=True, timeout=600).stderr
    return [round(float(x), 3) for x in re.findall(r"pts_time:([\d.]+)", err)]


def beat_report(cuts: list[float], beats: list[float], tol: float | None = None) -> dict:
    tol = float(_rule("beat_alignment").get("tolerance_s", 0.04)) if tol is None else tol
    grid = np.asarray(sorted(float(b) for b in beats or []), dtype=float)
    off = []
    for c in cuts:
        if not grid.size:
            break
        g = float(grid[np.argmin(np.abs(grid - c))])
        if abs(g - c) > tol:
            off.append({"cut": round(c, 3), "beat": round(g, 3), "off_ms": round((c - g) * 1000)})
    return {"cuts": len(cuts), "off_beat": off, "tolerance_ms": round(tol * 1000)}


def snap_cuts(cuts: list[float], beats: list[float], tol: float | None = None, max_shift: float | None = None) -> list[float]:
    """Move each cut that is more than ``tol`` off the grid onto its nearest beat (if within max_shift)."""
    r = _rule("beat_alignment")
    tol = float(r.get("tolerance_s", 0.04)) if tol is None else tol
    max_shift = float(r.get("max_snap_s", 0.25)) if max_shift is None else max_shift
    grid = np.asarray(sorted(float(b) for b in beats or []), dtype=float)
    out = []
    for c in cuts:
        c = float(c)
        if grid.size:
            g = float(grid[np.argmin(np.abs(grid - c))])
            if tol < abs(g - c) <= max_shift:
                c = g
        out.append(round(c, 4))
    return out


# ------------------------------------------------------------------ all
def run(path: str | Path, *, fps: float = 24.0, beats: list[float] | None = None, vj: bool = False,
        fix: bool = True) -> dict:
    """The post-render QA pass for the job report. Never raises; a failed check says so."""
    rep: dict[str, Any] = {"ok": True, "issues": []}
    try:
        lag = lag_report(path, fps)
        rep["lag"] = lag
        if lag["lag"]:
            rep["issues"] += lag["issues"]
            if fix:
                rep["lag_fix"] = fix_lag(path, lag, fps)
    except Exception as exc:
        rep["lag"] = {"error": str(exc)[:200]}
    try:
        art = artifact_scan(path, vj=vj)
        rep["artifacts"] = art
        rep["issues"] += [f"{f['kind']} at {f['t']}s" for f in art.get("flags") or []]
    except Exception as exc:
        rep["artifacts"] = {"error": str(exc)[:200]}
    if beats:
        try:
            br = beat_report(cut_times(path), beats)
            rep["beats"] = br
            if br["off_beat"]:
                rep["issues"].append(f"{len(br['off_beat'])} cut(s) more than {br['tolerance_ms']} ms off the beat")
        except Exception as exc:
            rep["beats"] = {"error": str(exc)[:200]}
    rep["ok"] = not rep["issues"]
    return rep
