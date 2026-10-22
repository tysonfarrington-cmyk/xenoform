"""Automated QA on a finished render (file level). Complements review.py, which audits the scene plan.

Each check returns a list of findings: {"check", "severity" ("fail"|"warn"), "msg", "t"?}.
Numeric cores are pure numpy so they can be tested without ffmpeg; the *_file helpers shell out to ffmpeg.
"""
from __future__ import annotations
import json, re, subprocess
import numpy as np
from pathlib import Path

try:
    from xenoform.demo_house import DEMO_HOUSE as _DEMO
except ImportError:  # loose checkout
    from demo_house import DEMO_HOUSE as _DEMO

# Transition ids that are structural (a plain cut, the scene morph, a black hold) and never count
# toward the per-type cap or the allowed list. Mirrors transitions_fx.EXEMPT_FROM_CAP.
try:
    from xenoform.transitions_fx import EXEMPT_FROM_CAP as _EXEMPT
except Exception:  # pragma: no cover - loose checkout / missing optional deps
    _EXEMPT = ("cut", "scene-morph", "black-hold")


def house(cfg: dict | None = None) -> dict:
    """The house profile, read at call time (not bound at import): a passed cfg["house"], then
    config.load_config()["house"], then demo_house.DEMO_HOUSE."""
    if isinstance(cfg, dict):
        h = cfg.get("house") if "house" in cfg else cfg
        if isinstance(h, dict) and "transitions" in h:
            return h
    try:
        from xenoform.config import load_config
        h = load_config().get("house")
        if isinstance(h, dict):
            return h
    except Exception:  # pragma: no cover - loose checkout
        pass
    return _DEMO


def _f(check, sev, msg, t=None):
    d = {"check": check, "severity": sev, "msg": msg}
    if t is not None:
        d["t"] = round(float(t), 3)
    return d


# ---- clicks: sample-level discontinuities that stand out from the local signal ----
def _is_musical_attack(hf: np.ndarray, i: int, sr: int) -> bool:
    """A drum hit keeps broadband energy for more than 10 ms after the attack; a click or a
    bad splice puts all of its high-frequency energy inside about a millisecond."""
    a, b, c = max(1, int(0.0005 * sr)), int(0.0015 * sr), int(0.012 * sr)
    spike = hf[max(0, i - a):i + a + 1]
    tail = hf[i + b:i + c]
    if not len(spike) or len(tail) < 8:
        return False
    rs = float(np.sqrt(np.mean(spike ** 2))) + 1e-9
    rt = float(np.sqrt(np.mean(tail ** 2)))
    return rt > 0.25 * rs


def click_scan(x: np.ndarray, sr: int, ratio: float = 12.0, music_onsets: list[float] | None = None, tol: float = 0.03,
               min_step: float = 0.005):
    """Audible sample-level discontinuities (clicks, bad splices), not musical transients.

    A candidate is a one-sample jump (first and second difference) at least ``min_step`` of full
    scale and ``ratio`` times (about 22 dB) above the surrounding 100 ms of high-frequency content, so
    the curvature of a loud bass tone is never a click and a step buried under hi-hats, which no
    one can hear, is not reported either. A candidate with a broadband tail longer than 10 ms is
    a drum hit (``_is_musical_attack``). ``music_onsets`` (the drum stem's hits from stems.json
    ``drum_hits``) are additionally excluded within ``tol`` seconds. Calibrated on the contest
    demo mix with injected 0.02..0.1 steps: steps in bass-led passages are caught, the mix's own
    attacks are not."""
    from scipy.signal import butter, sosfilt

    x = np.asarray(x, np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if len(x) < int(0.2 * sr):
        return []
    onsets = np.asarray(sorted(music_onsets or []), np.float64)
    hf = sosfilt(butter(2, min(2000.0, sr * 0.45), "highpass", fs=sr, output="sos"), x)
    win = max(16, int(0.1 * sr))
    floor = np.sqrt(np.convolve(hf ** 2, np.ones(win) / win, "same")) + 1e-6  # local HF level
    d1 = np.abs(np.diff(x))
    d2 = np.abs(np.diff(x, 2))
    jump = np.maximum(d1[:-1], d1[1:])  # the larger one-sample jump either side of sample i+1
    cand = np.nonzero((d2 > min_step) & (d2 > ratio * floor[1:-1]) & (jump > ratio * floor[1:-1]))[0]
    out, last = [], -1e9
    for i in cand:
        t = (i + 1) / sr
        if t - last < 0.02:
            continue
        last = t
        if len(onsets):
            j = int(np.searchsorted(onsets, t))
            near = min(abs(t - onsets[k]) for k in (j - 1, j) if 0 <= k < len(onsets))
            if near < tol:
                continue  # a declared drum hit
        if _is_musical_attack(hf, i + 1, sr):
            continue  # a real musical attack, not a click
        out.append(_f("click", "fail", f"discontinuity x{d2[i] / floor[i + 1]:.1f}", t))
    return out


# ---- loudness: ITU-R BS.1770-4 (K-weighting: high shelf + RLB high-pass, gated), plus 4x true peak ----
# Biquads are specified at 48 kHz, so other rates are resampled first. Channels are summed with
# weight 1.0 (L, R, C) and 1.41 for surrounds; the first five channels are taken in SMPTE order.
_K_SHELF_B = (1.53512485958697, -2.69169618940638, 1.19839281085285)
_K_SHELF_A = (1.0, -1.69065929318241, 0.73248077421585)
_K_HP_B = (1.0, -2.0, 1.0)
_K_HP_A = (1.0, -1.99004745483398, 0.99007225036621)
_CH_W = (1.0, 1.0, 1.0, 1.41, 1.41)


def k_weight(x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """K-weighted copy of ``x`` (samples x channels) at 48 kHz."""
    from scipy.signal import lfilter, resample_poly

    y = np.asarray(x, np.float64)
    if y.ndim == 1:
        y = y[:, None]
    if sr != 48000:
        from math import gcd

        g = gcd(48000, int(sr))
        y = resample_poly(y, 48000 // g, int(sr) // g, axis=0)
    y = lfilter(_K_SHELF_B, _K_SHELF_A, y, axis=0)
    y = lfilter(_K_HP_B, _K_HP_A, y, axis=0)
    return y, 48000


def loudness(x: np.ndarray, sr: int) -> dict:
    """Integrated loudness (LUFS, BS.1770-4 gating) and true peak (dBTP, 4x oversampled).

    Agrees with ffmpeg's ebur128 to about 0.1 LU on programme material."""
    from scipy.signal import resample_poly

    x = np.asarray(x, np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if not len(x):
        return {"lufs": -70.0, "true_peak_dbtp": -120.0}
    y, fs = k_weight(x[:, :5], sr)
    w = np.asarray(_CH_W[: y.shape[1]])
    blk, hop = int(0.4 * fs), int(0.1 * fs)
    starts = range(0, max(1, len(y) - blk + 1), hop)
    ms = np.array([(np.mean(y[i:i + blk] ** 2, axis=0) * w).sum() for i in starts])
    l = -0.691 + 10 * np.log10(ms + 1e-12)
    g = ms[l > -70]
    if not len(g):  # silence: every block is under the absolute gate
        return {"lufs": -70.0, "true_peak_dbtp": -120.0}
    rel = -0.691 + 10 * np.log10(g.mean() + 1e-12) - 10
    g2 = g[(-0.691 + 10 * np.log10(g + 1e-12)) > rel]
    lufs = -0.691 + 10 * np.log10(g2.mean() + 1e-12) if len(g2) else -70.0
    tp = 20 * np.log10(np.abs(resample_poly(x, 4, 1, axis=0)).max() + 1e-12)
    return {"lufs": float(lufs), "true_peak_dbtp": float(tp)}


def loudness_ffmpeg(path: str) -> dict | None:
    """The same two numbers from ffmpeg's ebur128 (the reference), or None when ffmpeg is missing."""
    try:
        res = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                             capture_output=True, text=True, errors="replace", timeout=600)
    except (OSError, subprocess.SubprocessError):
        return None
    lufs = tp = None
    for line in res.stderr.splitlines():
        t = line.strip()
        if t.startswith("I:") and "LUFS" in t:
            lufs = float(t.split()[1])
        elif t.startswith("Peak:") and "dBFS" in t:
            tp = float(t.split()[1])
    return None if lufs is None else {"lufs": lufs, "true_peak_dbtp": tp if tp is not None else -120.0}


def check_loudness(x, sr, target=None, tp_max=None, tol=0.5, cfg: dict | None = None):
    a = house(cfg)["audio"]
    target = a["target_lufs"] if target is None else target
    tp_max = a["true_peak_dbtp"] if tp_max is None else tp_max
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


def check_opening_cuts(cut_frames: list[int], fps, window_s=15.0, max_shots=None, cfg: dict | None = None):
    if max_shots is None:
        max_shots = house(cfg)["transitions"]["max_shots_first_15s"]
    shots = 1 + sum(1 for c in cut_frames if c / fps < window_s)
    return [_f("opening_cuts", "warn", f"{shots} shots in first {window_s:.0f}s (max {max_shots})")] if shots > max_shots else []


def check_duration(seconds: float, cap=None, cfg: dict | None = None):
    if cap is None:
        cap = house(cfg)["duration_cap_s"]
    return [_f("duration", "fail", f"{seconds:.2f}s > cap {cap}s")] if seconds > cap else []


# ---- transitions vs the house rules ----
def _banned(t: str, banned) -> str | None:
    """The banned name that matches transition id ``t`` (substring on the id, so 'wipe' catches
    'luma-wipe' and 'stutter' catches 'stutter-cut'), or None."""
    for b in banned:
        b = str(b).lower()
        if b and (b == t or b in t):
            return b
    return None


def check_transitions(used: list[str], rules: dict | None = None, cfg: dict | None = None):
    """Transition ids against the house rules. cut / scene-morph / black-hold are structural: they are
    always allowed and never count toward the per-type cap (transitions_fx.EXEMPT_FROM_CAP)."""
    rules = house(cfg)["transitions"] if rules is None else rules
    allowed = {str(a).lower() for a in rules.get("allowed", ())}
    cap = int(rules.get("max_uses_per_type", 2))
    out = []
    for t in sorted(set(str(u).lower() for u in used)):
        k = sum(1 for u in used if str(u).lower() == t)
        exempt = t in _EXEMPT
        b = None if exempt else _banned(t, rules.get("banned", ()))
        if b:
            out.append(_f("transition_banned", "fail", f"banned transition '{t}' used {k}x (matches '{b}')"))
        elif not exempt and t not in allowed:
            out.append(_f("transition_unknown", "warn", f"transition '{t}' not in allowed list"))
        if not exempt and k > cap:
            out.append(_f("transition_overuse", "fail", f"'{t}' used {k}x (max {cap})"))
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
    text_mask = np.asarray(text_mask, bool)
    ys, xs = np.nonzero(text_mask)
    if not len(ys):  # nothing to measure: say so instead of passing on a nan ratio
        return [_f("text_contrast", "warn", "no text mask (legibility not measured)", t)]
    fg = frame[text_mask].reshape(-1, 3).mean(0)
    ring = np.zeros_like(text_mask)
    ring[max(0, ys.min() - 8):ys.max() + 8, max(0, xs.min() - 8):xs.max() + 8] = True
    ring &= ~text_mask
    bg = frame[ring].reshape(-1, 3).mean(0) if ring.any() else np.zeros(3)
    r = contrast_ratio(fg, bg)
    return [_f("text_contrast", "warn", f"contrast {r:.1f}:1 < {min_ratio}:1", t)] if r < min_ratio else []


# ---- file-level runner (ffmpeg) ----
def probe_fps(path: str, default: float = 24.0) -> float:
    """The file's video frame rate via ffprobe (r_frame_rate), ``default`` when it cannot be read."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        num, _, den = out.partition("/")
        fps = float(num) / float(den or 1)
        return fps if 1.0 <= fps <= 240.0 else default
    except (OSError, ValueError, ZeroDivisionError, subprocess.SubprocessError):
        return default


def run_file(path: str, transitions_used: list[str] | None = None, transcript: list[dict] | None = None,
             expected_lines: list[str] | None = None, stems_path: str | None = None) -> dict:
    """Render-level QA of one file. ``stems_path`` (a stems.json from ``stem_react.save_envelopes``)
    lends its ``drum_hits`` to the click scan; otherwise onsets are detected from the mix."""
    import soundfile as sf, tempfile, os
    with tempfile.TemporaryDirectory(prefix="xeno_qa_") as tmp:
        wav = os.path.join(tmp, "a.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ar", "48000", wav], check=True)
        x, sr = sf.read(wav)
    onsets = None
    if stems_path:
        try:
            onsets = [float(t) for t in json.loads(Path(stems_path).read_text(encoding="utf-8")).get("drum_hits") or []]
        except (OSError, ValueError, TypeError):
            onsets = None
    fps = probe_fps(path)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"fps={fps:g},scale=96:170,format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 170, 96).astype(np.float32)
    dur = len(x) / sr; cf = cuts(fr)
    found = (click_scan(x, sr, music_onsets=onsets) + check_loudness(x, sr) + check_black_freeze(fr, fps) + check_static_shots(fr, fps, cf)
             + check_opening_cuts(cf, fps) + check_duration(dur) + check_transitions(transitions_used or [])
             + (check_vo_transcript(transcript, expected_lines) if transcript else []))
    return {"path": path, "duration": dur, "findings": found, "pass": not any(f["severity"] == "fail" for f in found)}


if __name__ == "__main__":  # python -m xenoform.media_qa video.mp4
    import sys
    print(json.dumps(run_file(sys.argv[1]), indent=2))
