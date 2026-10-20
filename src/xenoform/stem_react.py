"""Stem-reactive engine: drums drive cuts and stutters, bass drives warp, scale and displacement,
the rest (``other`` + vocals) drives texture and colour.

Stems come from Demucs (htdemucs, MIT) when it is installed (``pip install demucs``; it runs
on the CPU by default so it never competes with ComfyUI for VRAM). Without Demucs a librosa
split is used: HPSS percussive -> drums, <150 Hz -> bass, harmonic -> other.

    stems = split("song.wav", "work/stems")          # {"drums": path, "bass": path, ...}
    env = envelopes(stems, fps=24)                     # per-frame 0..1 curves + drum hits
    save_envelopes(env, "work/stems/env.json")         # scene_edit reads it via spec["stems"]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

STEMS = ("drums", "bass", "other", "vocals")


def demucs_available(python: str | None = None) -> bool:
    py = python or sys.executable
    try:
        return subprocess.run([py, "-c", "import demucs"], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def split(track: str | Path, out_dir: str | Path, *, model: str = "htdemucs", device: str = "cpu",
          python: str | None = None, engine: str = "auto") -> dict[str, str]:
    """Separate ``track`` into stems. Returns {stem: wav path, "engine": ...}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    py = python or sys.executable
    if engine in ("auto", "demucs") and demucs_available(py):
        cmd = [py, "-m", "demucs", "-n", model, "-d", device, "-j", "2", "-o", str(out), str(track)]
        subprocess.run(cmd, check=True)
        folder = out / model / Path(track).stem
        paths = {s: str(folder / f"{s}.wav") for s in STEMS if (folder / f"{s}.wav").exists()}
        if len(paths) == 4:
            return {**paths, "engine": f"demucs:{model}"}
    if engine == "demucs":
        raise RuntimeError("Demucs is not installed (pip install demucs)")
    return _librosa_split(track, out)


def _librosa_split(track, out: Path) -> dict[str, str]:
    import librosa
    import soundfile as sf

    y, sr = librosa.load(str(track), sr=44100, mono=True)
    H, P = librosa.effects.hpss(y)
    S = librosa.stft(y)
    f = librosa.fft_frequencies(sr=sr)
    S_b = S * (f[:, None] < 150)
    bass = librosa.istft(S_b, length=len(y))
    other = H - librosa.istft(librosa.stft(H) * (f[:, None] < 150), length=len(y))
    paths = {}
    for name, sig in (("drums", P), ("bass", bass), ("other", other), ("vocals", np.zeros_like(y))):
        p = out / f"{name}.wav"
        sf.write(str(p), sig.astype(np.float32), sr)
        paths[name] = str(p)
    return {**paths, "engine": "librosa"}


def _norm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    hi = float(np.percentile(x, 99)) if x.size else 0.0
    return np.clip(x / hi, 0, 1) if hi > 1e-9 else np.zeros_like(x)


def envelopes(stems: dict[str, str], *, fps: int = 24, sr: int = 22050) -> dict:
    """Per-frame 0..1 curves: drums (onset strength), bass/other/vocals (RMS), plus drum hit times."""
    import librosa

    hop = int(round(sr / fps))
    out: dict = {"fps": fps, "engine": stems.get("engine", "?")}
    n = None
    for s in STEMS:
        if s not in stems:
            continue
        y, _ = librosa.load(stems[s], sr=sr, mono=True)
        if s == "drums":
            v = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
            hits = librosa.onset.onset_detect(onset_envelope=v, sr=sr, hop_length=hop, units="time",
                                              delta=0.25, wait=max(1, fps // 8))
            strong = [float(t) for t in hits if v[min(len(v) - 1, int(round(t * fps)))] >= np.percentile(v, 90)]
            out["drum_hits"] = [round(float(t), 3) for t in hits]
            out["drum_strong"] = [round(t, 3) for t in strong]
        else:
            v = librosa.feature.rms(y=y, hop_length=hop)[0]
        v = _norm(v)
        n = len(v) if n is None else min(n, len(v))
        out[s] = v
    for s in STEMS:
        if s in out:
            out[s] = [round(float(x), 4) for x in out[s][:n]]
    out["frames"] = n or 0
    return out


def save_envelopes(env: dict, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(env), encoding="utf-8")
    return p


def at(env: dict, t: float, stem: str) -> float:
    v = env.get(stem) or []
    if not v:
        return 0.0
    k = int(round(t * env.get("fps", 24)))
    return float(v[min(max(k, 0), len(v) - 1)])


def drive(env: dict, t: float) -> dict:
    """What the picture does at time t: the stem-to-effect routing."""
    d, b, o = at(env, t, "drums"), at(env, t, "bass"), max(at(env, t, "other"), at(env, t, "vocals") * 0.5)
    return {
        "stutter": d if d > 0.75 else 0.0,  # drums: stutter/cut energy
        "chroma": d,                          # drums: transient RGB kick
        "scale": b,                           # bass: breath / scale
        "displace": b,                        # bass: liquid displacement
        "saturation": 0.85 + 0.35 * o,        # other: colour / texture
        "grain": o,
        "emission": max(o, at(env, t, "vocals")),  # other/vocals: glow on the bright parts
        "hue": at(env, t, "vocals"),               # vocals: colour drift
    }


def cut_points(env: dict, beats: list[float] | None = None, *, min_gap: float = 1.2, max_shift: float = 0.12) -> list[float]:
    """Strong drum hits as cut candidates, optionally snapped to the beat grid, at least ``min_gap`` apart."""
    pts, last = [], -1e9
    grid = np.asarray(beats or [], dtype=float)
    for t in env.get("drum_strong") or []:
        if grid.size:
            g = float(grid[np.argmin(np.abs(grid - t))])
            if abs(g - t) <= max_shift:
                t = g
        if t - last >= min_gap:
            pts.append(round(float(t), 3))
            last = t
    return pts


def apply_frame(frame: np.ndarray, env: dict, t: float, *, depth: float = 0.01) -> np.ndarray:
    """Stem-driven post effect for one frame (bass scale + displacement, drum chroma, other saturation)."""
    try:
        from xenoform import transitions_fx as T
    except ImportError:  # running from a loose checkout
        import transitions_fx as T

    p = drive(env, t)
    fr = T.scale_frame(frame, 1.0 + 3.0 * depth * p["scale"])  # bass: scale, linear so quiet bass still breathes
    h, w = fr.shape[:2]
    if p["displace"] > 0.05:  # bass: continuous liquid displacement (was only above 0.55)
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        amp = p["displace"] * 3.0 * max(1.0, w / 1080)
        fr = T._remap(fr, gx + amp * np.sin(gy / (h / 11.0) + t * 7.0), gy)
    if p["emission"] > 0.05:  # other/vocals: emission glow on the bright parts
        f = fr.astype(np.float32)
        lum = f.mean(axis=2, keepdims=True) / 255.0
        fr = np.clip(f + f * (lum ** 2) * 0.6 * p["emission"], 0, 255).astype(np.uint8)
    if p["hue"] > 0.05:  # vocals: warm colour drift
        f = fr.astype(np.float32)
        k = 0.12 * p["hue"]
        fr = np.clip(np.stack([f[..., 0] * (1 + k), f[..., 1], f[..., 2] * (1 - k)], axis=2), 0, 255).astype(np.uint8)
    if p["chroma"] > 0.6:
        fr = T.chroma_shift(fr, int(4 * (p["chroma"] - 0.6) / 0.4))
    s = p["saturation"]
    if abs(s - 1.0) > 0.02:
        g = fr.mean(axis=2, keepdims=True)
        fr = np.clip(g + (fr.astype(np.float32) - g) * s, 0, 255).astype(np.uint8)
    return fr
