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

STEMS = ("drums", "bass", "other", "vocals")  # the four routing roles (and Demucs' default stems)
MAX_STEMS = 32  # any number of named stems up to this, each with its own reaction gain
_ROLE_WORDS = (("drums", ("drum", "kick", "snare", "hat", "perc", "beat", "cymbal", "tom", "clap")),
               ("bass", ("bass", "sub", "808")),
               ("vocals", ("vocal", "vox", "voice", "lead vox", "choir", "sing")))


def role(name: str) -> str:
    """Which routing role a stem name feeds: drums, bass, vocals or other (any unknown name)."""
    n = str(name).lower()
    for r, words in _ROLE_WORDS:
        if any(w in n for w in words):
            return r
    return "other"


def stem_names(stems: dict) -> list[str]:
    """Stem names in a split/envelope dict (everything that is not metadata), capped at MAX_STEMS."""
    meta = {"engine", "fps", "frames", "drum_hits", "drum_strong", "stems", "roles"}
    names = [k for k in stems if k not in meta]
    if len(names) > MAX_STEMS:
        raise ValueError(f"{len(names)} stems given; Xenoform handles up to {MAX_STEMS}")
    return names


def from_files(paths, *, engine: str = "user") -> dict[str, str]:
    """Use stems the user already has (a DAW export, any count up to MAX_STEMS). ``paths`` is a list of
    wav paths (named by file stem) or a {name: path} dict."""
    if not isinstance(paths, dict):
        paths = {Path(p).stem: str(p) for p in paths}
    if not paths:
        raise ValueError("no stems given")
    if len(paths) > MAX_STEMS:
        raise ValueError(f"{len(paths)} stems given; Xenoform handles up to {MAX_STEMS}")
    return {**{str(k): str(v) for k, v in paths.items()}, "engine": engine}


def demucs_available(python: str | None = None) -> bool:
    py = python or sys.executable
    try:
        return subprocess.run([py, "-c", "import demucs"], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


ENGINES = ("auto", "demucs", "bands")  # "bands" is the librosa HPSS/band fallback ("librosa" is accepted as an alias)


def engines_available(python: str | None = None) -> dict[str, bool]:
    """Which separation engines this machine can run right now."""
    return {"demucs": demucs_available(python), "bands": True}


def split(track: str | Path, out_dir: str | Path, *, model: str = "htdemucs", device: str = "cpu",
          python: str | None = None, engine: str = "auto") -> dict[str, str]:
    """Separate ``track`` into stems. Returns {stem: wav path, "engine": ...}.

    ``engine``: "auto" (Demucs when installed, else the band split), "demucs" (error if missing),
    or "bands"/"librosa" (the dependency-free fallback; reported as ``engine="librosa"``)."""
    if engine == "librosa":
        engine = "bands"
    if engine not in ENGINES:
        raise ValueError(f"unknown stem engine {engine!r}; use one of {', '.join(ENGINES)}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    py = python or sys.executable
    if engine in ("auto", "demucs") and demucs_available(py):
        cmd = [py, "-m", "demucs", "-n", model, "-d", device, "-j", "2", "-o", str(out), str(track)]
        subprocess.run(cmd, check=True)
        folder = out / model / Path(track).stem
        paths = {w.stem: str(w) for w in sorted(folder.glob("*.wav"))[:MAX_STEMS]}  # 4 for htdemucs, 6 for htdemucs_6s, ...
        if paths:
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
    """Per-frame 0..1 curves for every stem (any count up to MAX_STEMS): drum-role stems give onset
    strength, the rest RMS. Also the four role curves (drums/bass/other/vocals = max of their members)
    and drum hit times from the drum role."""
    import librosa

    hop = int(round(sr / fps))
    out: dict = {"fps": fps, "engine": stems.get("engine", "?")}
    names = stem_names(stems)
    curves: dict[str, np.ndarray] = {}
    onsets: list[np.ndarray] = []
    for s in names:
        y, _ = librosa.load(stems[s], sr=sr, mono=True)
        if role(s) == "drums":
            v = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
            onsets.append(v)
        else:
            v = librosa.feature.rms(y=y, hop_length=hop)[0]
        curves[s] = _norm(v)
    n = min((len(v) for v in curves.values()), default=0)
    if onsets:
        m = min(len(v) for v in onsets); v = np.max([o[:m] for o in onsets], axis=0)
        hits = librosa.onset.onset_detect(onset_envelope=v, sr=sr, hop_length=hop, units="time",
                                          delta=0.25, wait=max(1, fps // 8))
        strong = [float(t) for t in hits if v[min(len(v) - 1, int(round(t * fps)))] >= np.percentile(v, 90)]
        out["drum_hits"] = [round(float(t), 3) for t in hits]
        out["drum_strong"] = [round(t, 3) for t in strong]
    for s in names:
        out[s] = [round(float(x), 4) for x in curves[s][:n]]
    out["stems"] = names
    out["roles"] = {s: role(s) for s in names}
    for r in STEMS:  # role curves: the max over every stem mapped to that role (a stem literally named
        # "other"/"drums"/... is one member among the rest, so guitar/piano still drive "other").
        # Matches role_levels() with all gains at 1.0.
        mem = [curves[s][:n] for s in names if role(s) == r]
        if mem:
            out[r] = [round(float(x), 4) for x in np.max(mem, axis=0)]
    out["frames"] = n
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


def role_levels(env: dict, t: float, gains: dict | None = None) -> dict[str, float]:
    """Role energies at t. With per-stem ``gains`` (name -> 0..1, 1 = full reaction) each stem is
    weighted before it feeds its role; without gains the precomputed role curves are used."""
    names = env.get("stems")
    if not names or not gains:
        return {r: at(env, t, r) for r in STEMS}
    roles = env.get("roles") or {s: role(s) for s in names}
    lv = {r: 0.0 for r in STEMS}
    for s in names:
        g = float(np.clip(gains.get(s, 1.0), 0.0, 1.0))
        lv[roles.get(s, "other")] = max(lv[roles.get(s, "other")], at(env, t, s) * g)
    return lv


def drive(env: dict, t: float, gains: dict | None = None) -> dict:
    """What the picture does at time t: the stem-to-effect routing (any number of stems via roles)."""
    L = role_levels(env, t, gains)
    d, b, o = L["drums"], L["bass"], max(L["other"], L["vocals"] * 0.5)
    return {
        "stutter": d if d > 0.75 else 0.0,  # drums: stutter/cut energy
        "chroma": d,                          # drums: transient RGB kick
        "scale": b,                           # bass: breath / scale
        "displace": b,                        # bass: liquid displacement
        "saturation": 0.85 + 0.35 * o,        # other: colour / texture
        "grain": o,
        "emission": max(o, L["vocals"]),      # other/vocals: glow on the bright parts
        "hue": L["vocals"],                   # vocals: colour drift
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


def apply_frame(frame: np.ndarray, env: dict, t: float, *, depth: float = 0.01, gains: dict | None = None) -> np.ndarray:
    """Stem-driven post effect for one frame (bass scale + displacement, drum chroma, other saturation)."""
    try:
        from xenoform import transitions_fx as T
    except ImportError:  # running from a loose checkout
        import transitions_fx as T

    p = drive(env, t, gains)
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
