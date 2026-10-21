"""Automated QA on a finished render (file level). Complements review.py, which audits the scene plan.

Each check returns a list of findings: {"check", "severity" ("fail"|"warn"), "msg", "t"?}.
Numeric cores are pure numpy so they can be tested without ffmpeg; the *_file helpers shell out to ffmpeg.
"""
from __future__ import annotations
import json, re, subprocess
import numpy as np

try:
    from xenoform.demo_house import DEMO_HOUSE as _H
except ImportError:  # loose checkout
    from demo_house import DEMO_HOUSE as _H


def _f(check, sev, msg, t=None):
    d = {"check": check, "severity": sev, "msg": msg}
    if t is not None:
        d["t"] = round(float(t), 3)
    return d


# ---- clicks: sample-level discontinuities that stand out from the local signal ----
def click_scan(x: np.ndarray, sr: int, ratio: float = 8.0, music_onsets: list[float] | None = None, tol: float = 0.03):
    x = np.asarray(x, np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    d2 = np.abs(np.diff(x, 2))
    w = max(8, int(sr * 0.005))
    loc = np.convolve(d2, np.ones(w) / w, "same") + 1e-6
    r = d2 / loc
    idx = np.nonzero(r > ratio)[0]
    out, last = [], -1e9
    for i in idx:
        t = (i + 1) / sr
        if t - last < 0.02:
            continue
        last = t
        if music_onsets and min(abs(t - m) for m in music_onsets) < tol:
            continue  # a real drum transient, not a click
        out.append(_f("click", "fail", f"discontinuity x{r[i]:.1f}", t))
    return out


# ---- loudness: simplified BS.1770 (K-weighting approximated by a high-pass), plus 4x true peak ----
def loudness(x: np.ndarray, sr: int) -> dict:
    x = np.asarray(x, np.float64)
    if x.ndim == 1:
        x = x[:, None]
    from scipy.signal import butter, sosfilt, resample_poly
    y = sosfilt(butter(2, 100, "highpass", fs=sr, output="sos"), x, axis=0)
    blk, hop = int(0.4 * sr), int(0.1 * sr)
    ms = np.array([np.mean(y[i:i + blk] ** 2, axis=0).sum() for i in range(0, max(1, len(y) - blk), hop)])
    l = -0.691 + 10 * np.log10(ms + 1e-12)
    g = ms[l > -70]
    rel = -0.691 + 10 * np.log10(g.mean() + 1e-12) - 10
    g2 = g[(-0.691 + 10 * np.log10(g + 1e-12)) > rel]
    lufs = -0.691 + 10 * np.log10(g2.mean() + 1e-12) if len(g2) else -70.0
    tp = 20 * np.log10(np.abs(resample_poly(x, 4, 1, axis=0)).max() + 1e-12)
    return {"lufs": float(lufs), "true_peak_dbtp": float(tp)}


def check_loudness(x, sr, target=_H["audio"]["target_lufs"], tp_max=_H["audio"]["true_peak_dbtp"], tol=0.5):
    m = loudness(x, sr); out = []
    if abs(m["lufs"] - target) > tol:
        out.append(_f("lufs", "fail", f"{m['lufs']:.1f} LUFS (target {target})"))
    if m["true_peak_dbtp"] > tp_max + 0.3:
        out.append(_f("true_peak", "fail", f"{m['true_peak_dbtp']:.1f} dBTP > {tp_max}"))
    return out


# ---- video: motion, black, freeze, cuts ----
def motion_series(frames: np.ndarray) -> np.ndarray:
    """Mean abs luma change per frame (0..255). frames: N x H x W (x3)."""
    f = np.asarray(frames, np.float32)
    if f.ndim == 4:
        f = f.mean(axis=3)
    return np.concatenate([[0.0], np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))])


def cuts(frames: np.ndarray, thresh: float = 30.0) -> list[int]:
    m = motion_series(frames)
    return [int(i) for i in np.nonzero(m > thresh)[0]]


def check_black_freeze(frames, fps, black_luma=12.0, min_s=0.2, freeze_eps=0.15, freeze_s=0.6, allow=((0.0, 1.5),)):
    f = np.asarray(frames, np.float32)
    lum = (f.mean(axis=3) if f.ndim == 4 else f).mean(axis=(1, 2)); m = motion_series(f); out = []
    def runs(mask):
        i = 0
        while i < len(mask):
            if mask[i]:
                j = i
                while j < len(mask) and mask[j]:
                    j += 1
                yield i, j
                i = j
            else:
                i += 1
    ok = lambda t: any(a <= t <= b for a, b in allow)
    for a, b in runs(lum < black_luma):
        if (b - a) / fps >= min_s and not ok(a / fps):
            out.append(_f("black", "warn", f"black {(b - a) / fps:.2f}s", a / fps))
    for a, b in runs(m < freeze_eps):
        if (b - a) / fps >= freeze_s and not ok(a / fps):
            out.append(_f("freeze", "warn", f"frozen {(b - a) / fps:.2f}s", a / fps))
    return out


def check_static_shots(frames, fps, shot_bounds: list[int] | None = None, min_motion=0.8, min_s=1.5):
    """Flag near-static ('boring') shots: low mean motion over a whole shot."""
    m = motion_series(frames); n = len(m)
    b = sorted(set([0] + list(shot_bounds if shot_bounds is not None else cuts(frames)) + [n]))
    out = []
    for a, c in zip(b, b[1:]):
        if (c - a) / fps >= min_s and float(np.median(m[a + 1:c] if c - a > 1 else m[a:c])) < min_motion:
            out.append(_f("static_shot", "warn", f"near-static shot {(c - a) / fps:.1f}s (boring)", a / fps))
    return out


def check_opening_cuts(cut_frames: list[int], fps, window_s=15.0, max_shots=_H["transitions"]["max_shots_first_15s"]):
    shots = 1 + sum(1 for c in cut_frames if c / fps < window_s)
    return [_f("opening_cuts", "warn", f"{shots} shots in first {window_s:.0f}s (max {max_shots})")] if shots > max_shots else []


def check_duration(seconds: float, cap=_H["duration_cap_s"]):
    return [_f("duration", "fail", f"{seconds:.2f}s > cap {cap}s")] if seconds > cap else []


# ---- transitions vs the house rules ----
def check_transitions(used: list[str], rules: dict = _H["transitions"]):
    out = []
    for t in sorted(set(used)):
        k = used.count(t)
        if t in rules["banned"]:
            out.append(_f("transition_banned", "fail", f"banned transition '{t}' used {k}x"))
        elif t not in rules["allowed"]:
            out.append(_f("transition_unknown", "warn", f"transition '{t}' not in allowed list"))
        if k > rules["max_uses_per_type"]:
            out.append(_f("transition_overuse", "fail", f"'{t}' used {k}x (max {rules['max_uses_per_type']})"))
    return out


# ---- VO transcript: stutters / doubled words ----
def check_vo_transcript(segments: list[dict], expected: list[str] | None = None):
    """segments: [{"start","end","text"}] e.g. from faster-whisper."""
    out = []
    for s in segments:
        w = re.findall(r"[a-z0-9']+", s["text"].lower())
        for a, b in zip(w, w[1:]):
            if a == b and len(a) > 1:
                out.append(_f("vo_double_word", "warn", f"'{a} {b}' in: {s['text'].strip()}", s["start"]))
    if expected:
        allt = " ".join(s["text"].lower() for s in segments)
        for line in expected:
            key = re.findall(r"[a-z0-9']+", line.lower())[:3]
            if key and " ".join(key) not in re.sub(r"[^a-z0-9' ]", "", allt):
                out.append(_f("vo_missing", "warn", f"line not found in transcript: {line}"))
    return out


# ---- text legibility ----
def contrast_ratio(fg_rgb, bg_rgb) -> float:
    def L(c):
        c = np.asarray(c, np.float64) / 255.0
        c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]
    a, b = float(np.mean(L(np.asarray(fg_rgb)[None]))), float(np.mean(L(np.asarray(bg_rgb)[None])))
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def check_text_legibility(frame: np.ndarray, text_mask: np.ndarray, min_ratio=4.5, t=None):
    """text_mask: bool HxW of glyph pixels (TODO: derive from the overlay renderer instead of passing it in)."""
    fg = frame[text_mask].reshape(-1, 3).mean(0)
    import numpy as _np
    ring = _np.zeros_like(text_mask)
    ys, xs = _np.nonzero(text_mask)
    if len(ys):
        ring[max(0, ys.min() - 8):ys.max() + 8, max(0, xs.min() - 8):xs.max() + 8] = True
    ring &= ~text_mask
    bg = frame[ring].reshape(-1, 3).mean(0) if ring.any() else _np.zeros(3)
    r = contrast_ratio(fg, bg)
    return [_f("text_contrast", "warn", f"contrast {r:.1f}:1 < {min_ratio}:1", t)] if r < min_ratio else []


# ---- file-level runner (ffmpeg) ----
def run_file(path: str, transitions_used: list[str] | None = None, transcript: list[dict] | None = None,
             expected_lines: list[str] | None = None) -> dict:
    """TODO: music_onsets for click_scan should come from the stem drums track; reuse stem_react envelopes."""
    import soundfile as sf, tempfile, os
    tmp = tempfile.mkdtemp(); wav = os.path.join(tmp, "a.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ar", "48000", wav], check=True)
    x, sr = sf.read(wav)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", "fps=12,scale=96:170,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 170, 96).astype(np.float32); fps = 12.0
    dur = len(x) / sr; cf = cuts(fr)
    found = (click_scan(x, sr) + check_loudness(x, sr) + check_black_freeze(fr, fps) + check_static_shots(fr, fps, cf)
             + check_opening_cuts(cf, fps) + check_duration(dur) + check_transitions(transitions_used or [])
             + (check_vo_transcript(transcript, expected_lines) if transcript else []))
    return {"path": path, "duration": dur, "findings": found, "pass": not any(f["severity"] == "fail" for f in found)}


if __name__ == "__main__":  # python -m xenoform.media_qa video.mp4
    import sys
    print(json.dumps(run_file(sys.argv[1]), indent=2))
