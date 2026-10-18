"""Synthesize a short royalty-free test track with a clear drop.

The arrangement is deterministic for a given seed:

* 0–3s calm pulse
* 3–6s build (riser, opening hats)
* 6–9s drop (loud sub, harder kicks, a hit on the downbeat)
* 9–12s release
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def synthesize(
    duration: float = 12.0,
    sr: int = 44100,
    bpm: float = 120.0,
    seed: int = 7,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    audio = np.zeros(n, dtype=np.float64)

    beat = 60.0 / bpm
    kick_times = np.arange(0.0, duration - 0.05, beat)

    def section_gain(time: float) -> float:
        if time < 3.0:
            return 0.45
        if time < 5.5:
            return 0.55 + 0.35 * ((time - 3.0) / 2.5)
        if time < 6.0:
            return 0.18  # pre-drop dip so the hit reads as a section change
        if time < 9.0:
            return 1.35
        return 0.7

    for kt in kick_times:
        start = int(kt * sr)
        length = int(0.18 * sr)
        if start >= n:
            break
        length = min(length, n - start)
        env_t = np.arange(length) / sr
        env = np.exp(-env_t * 28.0)
        # Pitch-dropping sine plus a click.
        freq = 140.0 * np.exp(-env_t * 18.0) + 42.0
        phase = 2.0 * np.pi * np.cumsum(freq) / sr
        click = np.exp(-env_t * 180.0)
        body = np.sin(phase) * env + click * 0.8
        audio[start : start + length] += body * section_gain(float(kt))

    # Sub bass follows the kick grid and opens up on the drop.
    sub_freq = np.where(t >= 6.0, 46.0, np.where(t >= 3.0, 40.0, 0.0))
    sub_amp = np.where((t >= 6.0) & (t < 9.0), 0.55, np.where(t >= 3.0, 0.16, 0.0))
    # Retrigger a soft envelope every beat during the drop and build.
    sub = np.zeros(n, dtype=np.float64)
    phase = 0.0
    for i in range(n):
        f = sub_freq[i]
        if f <= 0.0:
            continue
        phase += 2.0 * np.pi * f / sr
        sub[i] = np.sin(phase)
    beat_env = np.zeros(n, dtype=np.float64)
    for kt in kick_times:
        if kt < 3.0:
            continue
        start = int(kt * sr)
        length = min(int(beat * sr), n - start)
        if length <= 0:
            continue
        beat_env[start : start + length] = np.linspace(1.0, 0.25, length)
    audio += sub * sub_amp * np.maximum(beat_env, 0.15)

    # Noise hats on the off-beat, brighter as the build progresses.
    hat = rng.uniform(-1.0, 1.0, n)
    hat_env = np.zeros(n, dtype=np.float64)
    offbeats = kick_times + beat * 0.5
    for ht in offbeats:
        if ht >= duration:
            break
        start = int(ht * sr)
        length = min(int(0.04 * sr), n - start)
        if length <= 0:
            continue
        brightness = 0.04 if ht < 3.0 else (0.08 + 0.12 * min(1.0, (ht - 3.0) / 3.0))
        if 6.0 <= ht < 9.0:
            brightness = 0.16
        hat_env[start : start + length] = brightness * np.linspace(1.0, 0.0, length)
    audio += hat * hat_env

    # Riser from 3s to 6s, then a noise impact on the drop.
    rise_mask = (t >= 3.0) & (t < 6.0)
    rise = (t - 3.0) / 3.0
    rise_freq = 220.0 + rise * 1800.0
    audio[rise_mask] += 0.08 * rise[rise_mask] * np.sin(2.0 * np.pi * rise_freq[rise_mask] * t[rise_mask])

    impact_len = int(0.35 * sr)
    impact_at = int(6.0 * sr)
    if impact_at < n:
        length = min(impact_len, n - impact_at)
        env = np.exp(-np.arange(length) / sr * 10.0)
        audio[impact_at : impact_at + length] += rng.uniform(-1.0, 1.0, length) * env * 0.55

    # Gentle release tail.
    release = (t >= 9.0).astype(np.float64)
    audio += 0.05 * release * np.sin(2.0 * np.pi * 196.0 * t) * np.exp(-(t - 9.0) * 0.6)

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio *= 0.89 / peak
    return audio.astype(np.float32)


def write_wav(path: str | Path, audio: np.ndarray, sr: int) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sr)
        handle.writeframes(pcm.tobytes())


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a wav written by this package, or any wav librosa can open."""
    path = Path(path)
    try:
        import librosa

        audio, sr = librosa.load(path, sr=None, mono=True)
        return audio.astype(np.float32), int(sr)
    except Exception:
        with wave.open(str(path), "rb") as handle:
            sr = handle.getframerate()
            channels = handle.getnchannels()
            frames = handle.readframes(handle.getnframes())
            width = handle.getsampwidth()
        if width != 2:
            raise RuntimeError(f"Unsupported wav sample width in {path}")
        pcm = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1)
        return pcm, int(sr)
