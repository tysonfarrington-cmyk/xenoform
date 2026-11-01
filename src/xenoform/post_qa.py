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
import logging
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import numpy as np

log = logging.getLogger("xenoform")


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


def flash_counts(luma: list[float] | np.ndarray, jump: float = 40.0) -> dict:
    """Hard flashes in a per-frame mean-luma series: frame-to-frame jumps over ``jump`` of 255 (pure; tests feed it)."""
    ys = np.asarray(list(luma), dtype=np.float32)
    jumps = np.abs(np.diff(ys)) if len(ys) > 1 else np.zeros(0, dtype=np.float32)
    return {"frames": int(len(ys)), "flashes": int((jumps > jump).sum()), "max_jump": round(float(jumps.max()), 1) if len(jumps) else 0.0}


def flash_report(path: str | Path, fps: float = 24.0, *, jump: float = 40.0, max_per_s: float = 0.5) -> dict:
    """Hard flashes over the whole cut from a small grey decode: a frame-to-frame mean-luma jump over 40 of 255.
    A negative-rush look on a bright risograph page measured 38 in 15 s (25 Oct test drive); the looks on dark vibes
    measure under 0.25 a second. More than ``max_per_s`` a second is an issue."""
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-vf", "scale=64:36", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                         capture_output=True, check=False).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 36, 64).astype(np.float32)
    rep = flash_counts(frames.mean(axis=(1, 2)), jump)
    seconds = max(rep["frames"] / float(fps), 1e-6)
    rep["per_s"] = round(rep["flashes"] / seconds, 3)
    rep["issues"] = [f"{rep['flashes']} hard flashes ({rep['per_s']:.1f} a second)"] if rep["per_s"] > max_per_s else []
    return rep


def _grey_lumas(path: str | Path) -> np.ndarray:
    """Each frame's mean luma: the encoded Y plane as it is (limited range, the levels the montage's deflash read as
    YAVG and ``deflash.luma`` computes), shrunk; a plain grey decode would stretch it to full range, 1.16 x every rise."""
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-vf", "extractplanes=y,scale=64:36", "-pix_fmt", "gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=False).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, 36, 64).astype(np.float32).mean(axis=(1, 2))


def veil_counts(luma, fps: float = 24.0, beats: list[float] | None = None, bars: int = 8) -> dict:
    """The soft white flashes Tys asked to tame (deflash's test: a frame more than 6 luma levels above the darker of the
    darkest 5 frames either side), counted per ``bars`` bars of the song's beat (pure; tests feed it)."""
    from xenoform import deflash

    flags = deflash.flash_frames(luma)
    b = sorted(float(x) for x in beats or [])
    gaps = sorted(y - x for x, y in zip(b, b[1:]) if y > x)
    period = gaps[len(gaps) // 2] if gaps else 0.5
    window = max(1, int(round(bars * 4 * period * float(fps))))
    per = deflash.per_window(flags, window)
    seconds = max(len(flags) / float(fps), 1e-6)
    return {"flash_frames": int(flags.sum()), "per_8_bars": round(float(flags.sum()) * window / max(1, len(flags)), 1),
            "max_8_bars": max(per) if per else 0, "windows": per, "window_s": round(window / float(fps), 2),
            "seconds": round(seconds, 2)}


def veil_report(path: str | Path, fps: float = 24.0, beats: list[float] | None = None) -> dict:
    """``veil_counts`` on a finished cut: what the flash tame (Breathe) holds to its passages' budgets. A report only."""
    return veil_counts(_grey_lumas(path), fps, beats)


def held_end(freezes: list[tuple[float, float]], frames: int, fps: float) -> int:
    """How many frames a cut ends on a held picture: its last freeze when that runs to the picture's own end (a rest
    the cut closes on, held by design: Breathe holds a morph's landing), 0 when the cut ends moving (pure)."""
    if not freezes or frames <= 0 or fps <= 0:
        return 0
    a, b = freezes[-1]
    end = frames / float(fps)
    return max(0, min(frames, int(round((end - float(a)) * fps)))) if float(b) >= end - 1.5 / fps else 0


def rests_of(shots: list[dict] | None, fps: float = 24.0) -> list[tuple[int, int]]:
    """Every planned rest of a cut's shot plan as frames ``(first, end)`` (pure): a shot with a ``rest`` holds its
    arrived object for its last ``rest_s`` seconds (pacing: Breathe's rests, a scene's morph then its dwell), so those
    frames are held picture by design, wherever in the cut they sit."""
    out: list[tuple[int, int]] = []
    for s in shots or []:
        if not isinstance(s, dict) or not s.get("rest"):
            continue
        try:
            rest_s, end = float(s.get("rest_s") or 0.0), float(s.get("end") or 0.0)
        except (TypeError, ValueError):
            continue
        a, b = int(round((end - rest_s) * fps)), int(round(end * fps))
        if rest_s > 0 and b - a >= 2:
            out.append((max(0, a), b))
    return _merge_ranges(out)


def _merge_ranges(ranges) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for a, b in sorted((int(a), int(b)) for a, b in ranges if int(b) > int(a)):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def kept_times(path: str | Path) -> list[float]:
    """The times of the frames mpdecimate keeps (the ones that are not near-duplicates of the frame before)."""
    err = subprocess.run([_ffmpeg(), "-v", "info", "-i", str(path), "-map", "0:v:0", "-vf", "mpdecimate,showinfo",
                          "-f", "null", "-"], capture_output=True, text=True, timeout=600).stderr
    return [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]


def _in_holds(a: float, b: float, holds: list[tuple[int, int]], fps: float) -> bool:
    """A freeze from ``a`` to ``b`` seconds that lies mostly (half or more) inside the planned holds."""
    span = max(1e-6, b - a)
    inside = sum(max(0.0, min(b, hb / fps) - max(a, ha / fps)) for ha, hb in holds)
    return inside >= 0.5 * span


def lag_report(path: str | Path, fps: float = 24.0, rests: list[tuple[int, int]] | None = None) -> dict:
    """Lag in a finished cut: held or duplicate frames past ``max_dup_ratio`` (judder), several short freezes, an fps
    that is not the project's. A held picture the cut ends on is not lag (``held_end``: a window closing on a rest, the
    hold its design): its frames are left out of the duplicate count and its freeze out of the short ones. ``rests``
    (``rests_of`` the cut's shot plan) are every rest the plan holds, wherever it sits: their frames are left out of the
    duplicate count (the frames mpdecimate keeps are counted outside them) and a freeze lying in one is not a short one."""
    r = _rule("lag_qa")
    info = probe(path)
    freezes = freeze_ranges(path, float(r.get("freeze_noise", 0.003)), float(r.get("freeze_min_s", 0.25)))
    total = max(1, info["frames"])
    rate = info["fps"] or fps
    tail = held_end(freezes, total, rate)
    planned = _merge_ranges(list(rests or []) + ([(total - tail, total)] if tail else []))
    if rests:  # every planned hold out of the count: the frames kept outside them against the frames outside them
        times = kept_times(path)
        kept = len(times) or total
        outside = max(1, total - sum(b - a for a, b in planned))
        kept_out = sum(1 for t in times if not any(a <= int(round(t * rate)) < b for a, b in planned))
        dup = max(0.0, 1.0 - kept_out / outside)
    else:
        kept = kept_frames(path) or total
        counted = max(1, total - max(0, tail - 1))  # the hold keeps its first frame; the rest of it is not judder
        dup = max(0.0, 1.0 - kept / counted)
    frozen_s = sum(b - a for a, b in freezes)
    issues = []
    if abs(info["fps"] - fps) > 0.05:
        issues.append(f"fps {info['fps']} does not match the project's {fps}")
    if dup > float(r.get("max_dup_ratio", 0.15)):
        issues.append(f"{dup:.0%} duplicate/held frames (judder)")
    inner = freezes[:-1] if tail else freezes
    in_rests = [f for f in inner if rests and _in_holds(f[0], f[1], planned, rate)]
    short = [f for f in inner if f not in in_rests and f[1] - f[0] <= float(r.get("lag_freeze_max_s", 0.6))]
    if len(short) >= int(r.get("max_short_freezes", 3)):
        issues.append(f"{len(short)} short freezes read as lag")
    out = {"fps": info["fps"], "project_fps": fps, "frames": total, "kept": kept, "dup_ratio": round(dup, 4),
           "freezes": [[round(a, 3), round(b, 3)] for a, b in freezes], "frozen_s": round(frozen_s, 3),
           "held_end_frames": tail, "short_freezes": len(short), "issues": issues, "lag": bool(issues)}
    if rests:
        out.update({"rests": [list(h) for h in rests], "rest_frames": sum(b - a for a, b in rests),
                    "rest_freezes": len(in_rests)})
    return out


def conform(src: str | Path, dest: str | Path, fps: float = 24.0, interpolate: bool = False) -> Path:
    """Re-time to the project fps. ``interpolate`` fills held frames by motion interpolation
    (mpdecimate keeps the timestamps, minterpolate fills the gaps), so the length and sync stay. A held run at the very
    end has no later frame to be filled toward, so mpdecimate's drop would end the picture where the hold began (a
    window closing on a rest lost its last 2 s that way and its whole song drifted, 1 Nov): the ``fps`` after it holds
    the last frame on to the picture's own end, so it keeps every frame it had, and never runs past it."""
    vf = f"mpdecimate,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:vsbmc=1,fps={fps}" if interpolate else f"fps={fps}"
    keep: list[str] = []
    if interpolate:
        info = probe(src)
        frames = int(round(info["frames"] * float(fps) / info["fps"])) if info["fps"] else int(info["frames"])
        if frames > 0:
            keep = ["-frames:v", str(frames)]
    dest = Path(dest)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(src), "-map", "0:v:0", "-map", "0:a?", "-vf", vf, *keep,
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                    str(dest)], check=True, timeout=1800)
    return dest


def keep_holds(src: str | Path, fixed: str | Path, dest: str | Path, holds: list[tuple[int, int]], fps: float = 24.0) -> Path:
    """``fixed`` (the interpolated picture, frame for frame the source's at ``fps``) with every planned hold's frames
    taken back from ``src`` as they were: the picture laid from the two in turn, frame-exact (``trim`` on frames after an
    ``fps`` on each), the source's sound copied. So the lag fix smooths the judder and leaves every rest held."""
    frames = int(probe(fixed)["frames"])
    edges = sorted({0, frames} | {min(frames, max(0, a)) for a, _ in holds} | {min(frames, max(0, b)) for _, b in holds})
    spans = [(a, b, any(ha <= a and b <= hb for ha, hb in holds)) for a, b in zip(edges, edges[1:]) if b > a]
    if not any(held for *_, held in spans):
        shutil.copyfile(fixed, dest)
        return Path(dest)
    n_src, n_fix = sum(1 for *_, h in spans if h), sum(1 for *_, h in spans if not h)
    parts = [f"[0:v]fps={fps},split={max(1, n_src)}" + "".join(f"[s{k}]" for k in range(max(1, n_src))),
             f"[1:v]fps={fps},split={max(1, n_fix)}" + "".join(f"[f{k}]" for k in range(max(1, n_fix)))]
    ks = kf = 0
    labels = []
    for i, (a, b, held) in enumerate(spans):
        pad = f"s{ks}" if held else f"f{kf}"
        ks, kf = ks + int(held), kf + int(not held)
        parts.append(f"[{pad}]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[p{i}]")
        labels.append(f"[p{i}]")
    if n_src == 0:
        parts.append("[s0]nullsink")
    if n_fix == 0:
        parts.append("[f0]nullsink")
    parts.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[v]")
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(src), "-i", str(fixed), "-filter_complex", ";".join(parts),
                    "-map", "[v]", "-map", "0:a?", "-frames:v", str(frames), "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", str(dest)], check=True, timeout=1800)
    return Path(dest)


def fix_lag(path: str | Path, report: dict, fps: float = 24.0, rests: list[tuple[int, int]] | None = None) -> dict:
    """Fix in place. fps mismatch -> conform; judder / short freezes -> interpolate held frames. ``rests`` (the shot
    plan's, ``rests_of``): every planned rest keeps its held frames through an interpolation (``keep_holds``), not only
    the one the cut ends on, so a rest in the middle of a window is still a rest after the fix."""
    path = Path(path)
    if not report.get("lag"):
        return {"fixed": False}
    interp = report["dup_ratio"] > float(_rule("lag_qa").get("max_dup_ratio", 0.15)) or report["short_freezes"] >= int(
        _rule("lag_qa").get("max_short_freezes", 3))
    tmp = path.with_name(path.stem + ".qa.mp4")
    conform(path, tmp, fps, interpolate=interp)
    kept = 0
    if interp and rests:
        held = path.with_name(path.stem + ".qa.rests.mp4")
        keep_holds(path, tmp, held, rests, fps)
        held.replace(tmp)
        kept = len(rests)
    tmp.replace(path)
    out = {"fixed": True, "method": "interpolate held frames" if interp else f"conform to {fps} fps",
           "frames": [int(report.get("frames") or 0), int(probe(path)["frames"])]}
    if rests:
        out["rests_kept"] = kept
    return out


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
        fix: bool = True, report: Callable[[str, float, str], None] | None = None, shots: list[dict] | None = None) -> dict:
    """The post-render QA pass for the job report. Never raises; a failed check says so. ``report(stage, frac,
    detail)``, the pipeline's progress shape, hears each pass start (the desk's bar used to sit still through QA).
    ``shots``: the cut's shot plan (its record's), whose planned rests (``rests_of``) are held picture by design: the
    lag check leaves them out and a lag fix keeps every one of them."""
    rests = rests_of(shots, fps) if shots else []
    rep: dict[str, Any] = {"ok": True, "issues": []}

    def say(frac: float, detail: str) -> None:
        if report is None:
            return
        try:
            report("qa", frac, detail)
        except Exception:  # progress is a courtesy: a listener's error (a cancel, say) must not fail the QA
            log.debug("qa progress listener failed", exc_info=True)

    say(0.2, "Checking for lag")
    try:
        lag = lag_report(path, fps, rests=rests or None)
        rep["lag"] = lag
        if lag["lag"]:
            rep["issues"] += lag["issues"]
            if fix:
                say(0.35, "Fixing the lag")  # right after the measurement, so the scans below see the fixed file
                rep["lag_fix"] = fix_lag(path, lag, fps, rests=rests or None)
    except Exception as exc:
        rep["lag"] = {"error": str(exc)[:200]}
    say(0.5, "Scanning for artifacts")
    try:
        art = artifact_scan(path, vj=vj)
        rep["artifacts"] = art
        rep["issues"] += [f"{f['kind']} at {f['t']}s" for f in art.get("flags") or []]
    except Exception as exc:
        rep["artifacts"] = {"error": str(exc)[:200]}
    say(0.6, "Counting hard flashes")
    try:
        fl = flash_report(path, fps)
        rep["flashes"] = fl
        rep["issues"] += fl["issues"]
    except Exception as exc:
        rep["flashes"] = {"error": str(exc)[:200]}
    try:  # the soft white flashes per 8 bars (deflash's test), what Breathe's tame holds down: reported, never an issue
        rep["veil"] = veil_report(path, fps, beats)
    except Exception as exc:
        rep["veil"] = {"error": str(exc)[:200]}
    if beats:
        say(0.7, "Checking the cuts against the beat")
        try:
            br = beat_report(cut_times(path), beats)
            rep["beats"] = br
            if br["off_beat"]:
                rep["issues"].append(f"{len(br['off_beat'])} cut(s) more than {br['tolerance_ms']} ms off the beat")
        except Exception as exc:
            rep["beats"] = {"error": str(exc)[:200]}
    rep["ok"] = not rep["issues"]
    return rep
