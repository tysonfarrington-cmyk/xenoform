"""The song, read the way the desk reads it (``xenoform.analyze``), inside ComfyUI's own Python.

``analyze`` returns the desk's features dict (the same keys ``xenoform.analyze.analyze_audio`` writes, so a desk's
``features.json`` loads here as it is): per-frame bands and envelopes, the beats, the onsets, the sections labelled calm,
build, drop, release or sustain, plus three keys of the pack's own: ``drop`` (the song's main drop in seconds, the
desk's ``beatfx.drop_time``), ``engine`` and ``source``.

Two engines. ``librosa`` is the desk's analysis line for line, used when ComfyUI's Python has librosa. ``numpy`` is the
same steps without it (ComfyUI does not ship librosa): an STFT, a Slaney mel bank and the log-power flux for the onset
envelope, the autocorrelation tempogram with the log-normal tempo prior around 120 BPM, and Ellis' dynamic-programming
beat tracker, as librosa does them. The bands, the sections and the drop are the desk's own code, which needs numpy alone.
The two agree on the bundled demo (tests/test_comfy_pack_song.py measures it); on any song the numpy engine is the one
to doubt first.

Audio comes from a WAV through the standard library, anything else through PyAV (ComfyUI ships it) or the ffmpeg binary,
or from ComfyUI's AUDIO value (``LoadAudio``).
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np

BANDS_HZ = {"sub": (20.0, 60.0), "bass": (60.0, 250.0), "mid": (250.0, 2000.0), "high": (2000.0, 8000.0)}
SECTION_MUTATE = {"calm": 0.0, "build": 0.35, "drop": 1.0, "release": 0.45, "sustain": 0.2}
BEAT_FPS = 24.0  # beats keep a clock of at least 24 fps whatever the frames' rate (xenoform.analyze.BEAT_FPS)
FPS = 12.0  # the desk analyses a song at 12 fps (configs: fps 12, songs_api.SHIPPED_FPS)
ONSET_TAU, BEAT_TAU, SECTION_MIN_S = 0.085, 0.05, 1.4  # the desk's analyze settings (xenoform.config)
ENGINES = ("auto", "numpy", "librosa")
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".aif", ".opus", ".mp4", ".webm")


class SongError(ValueError):
    """A song that cannot be read or analysed, said plainly."""


# ------------------------------------------------------------------------------------------------ the desk's own code
# (xenoform.analyze: these need numpy alone and are kept word for word)


def _resample(values: np.ndarray, src_times: np.ndarray, dst_times: np.ndarray) -> np.ndarray:
    if len(values) == 0:
        return np.zeros(len(dst_times), dtype=np.float32)
    if len(values) == 1:
        return np.full(len(dst_times), float(values[0]), dtype=np.float32)
    return np.interp(dst_times, src_times, values).astype(np.float32)


def _robust_norm(values: np.ndarray) -> np.ndarray:
    peak = float(np.percentile(values, 99))
    floor = float(np.min(values))
    span = peak - floor
    if span < 1e-8:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - floor) / span, 0.0, 1.0).astype(np.float32)


def _decay_env(flags: np.ndarray, fps: float, tau: float) -> np.ndarray:
    out = np.zeros(len(flags), dtype=np.float32)
    coeff = float(np.exp(-1.0 / (tau * fps))) if tau > 0 else 0.0
    prev = 0.0
    for i, flag in enumerate(flags):
        prev = max(1.0 if flag else 0.0, prev * coeff)
        out[i] = prev
    return out


def _smooth(values: np.ndarray, fps: float, seconds: float) -> np.ndarray:
    win = max(1, int(round(seconds * fps)))
    if win <= 1:
        return values.astype(np.float32)
    kernel = np.ones(win, dtype=np.float32) / win
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def detect_sections(times: np.ndarray, energy: np.ndarray, fps: float, min_seconds: float) -> list[dict[str, Any]]:
    """Split the track where smoothed energy changes quickly, then label each span (``xenoform.analyze``)."""
    if len(times) == 0:
        return []
    smooth = _smooth(energy, fps, 0.4)
    grad = np.gradient(smooth, times) if len(times) > 1 else np.zeros(1, dtype=np.float32)
    mag = np.abs(grad)
    thresh = float(np.percentile(mag, 82)) if len(mag) else 0.0
    min_gap = max(1, int(round(min_seconds * fps)))
    boundaries = [0]
    if float(np.max(mag)) < 1e-8:
        boundaries = [0, len(times) - 1]
    for i in range(1, len(times) - 1):
        if len(boundaries) > 1 and boundaries[-1] == len(times) - 1:
            break
        if mag[i] < thresh:
            continue
        if mag[i] < mag[i - 1] or mag[i] < mag[i + 1]:
            continue
        if i - boundaries[-1] < min_gap:
            continue
        boundaries.append(i)
    if len(times) - 1 - boundaries[-1] < min_gap and len(boundaries) > 1:
        boundaries.pop()
    boundaries.append(len(times) - 1)

    spans: list[dict[str, Any]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        stop = end if end == len(times) - 1 else end
        region = smooth[start : stop + 1] if stop == len(times) - 1 and end == start else smooth[start:end]
        if region.size == 0:
            region = smooth[start : start + 1]
        level = float(np.mean(region))
        slope = float(region[-1] - region[0])
        spans.append({"start_frame": int(start), "end_frame": int(end if end > start else start + 1),
                      "start": float(times[start]), "end": float(times[min(end, len(times) - 1)]),
                      "level": level, "slope": slope, "label": "sustain"})
    if not spans:
        return spans
    levels = [span["level"] for span in spans]
    mean_level = float(np.mean(levels))
    peak = levels[int(np.argmax(levels))]
    for span in spans:
        if span["level"] < peak * 0.45 and span["slope"] < 0.28:
            label = "calm"
        elif span["slope"] > 0.12:
            label = "build"
        elif span["slope"] < -0.10:
            label = "release"
        elif span["level"] < mean_level:
            label = "calm"
        else:
            label = "sustain"
        span["label"] = label
    if peak > mean_level + 0.08 or peak > 0.62:
        for span in spans:
            if span["level"] >= peak * 0.82:
                span["label"] = "drop"
    for index, span in enumerate(spans):
        if span["label"] != "drop" or index == 0:
            continue
        previous = spans[index - 1]
        if previous["label"] in {"calm", "sustain"} and previous["level"] > spans[0]["level"] * 1.35:
            previous["label"] = "build"
    for span in spans:
        span["mutate"] = SECTION_MUTATE[span["label"]]
    return spans


def _section_at(sections: list[dict[str, Any]], frame: int) -> dict[str, Any]:
    for section in sections:
        if section["start_frame"] <= frame < section["end_frame"]:
            return section
    return sections[-1]


# ------------------------------------------------------------------------------------------------ librosa's steps in numpy


def _hann(n: int) -> np.ndarray:
    """The periodic Hann window librosa takes (``scipy.signal.get_window("hann", n, fftbins=True)``)."""
    return (0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n) / n)).astype(np.float64)


def _stft_mag(y: np.ndarray, n_fft: int, hop: int) -> np.ndarray:
    """``abs(librosa.stft(y, n_fft, hop, center=True, pad_mode="constant"))``: (1 + n_fft // 2, 1 + len(y) // hop)."""
    pad = n_fft // 2
    padded = np.pad(np.asarray(y, dtype=np.float64), (pad, pad), mode="constant")
    n_frames = 1 + (len(padded) - n_fft) // hop
    win = _hann(n_fft)
    out = np.empty((1 + n_fft // 2, max(n_frames, 0)), dtype=np.float32)
    block = 256
    for b0 in range(0, n_frames, block):
        b1 = min(n_frames, b0 + block)
        idx = (np.arange(b0, b1) * hop)[:, None] + np.arange(n_fft)[None, :]
        frames = padded[idx] * win[None, :]
        out[:, b0:b1] = np.abs(np.fft.rfft(frames, axis=1)).T.astype(np.float32)
    return out


def _mel_bank(sr: int, n_fft: int, n_mels: int = 128) -> np.ndarray:
    """``librosa.filters.mel(sr, n_fft, n_mels)`` with its defaults: the Slaney scale and Slaney area norm."""
    f_sp, min_log_hz, logstep = 200.0 / 3, 1000.0, math.log(6.4) / 27.0
    min_log_mel = min_log_hz / f_sp

    def hz_to_mel(f: np.ndarray) -> np.ndarray:
        f = np.asarray(f, dtype=np.float64)
        return np.where(f >= min_log_hz, min_log_mel + np.log(np.maximum(f, 1e-10) / min_log_hz) / logstep, f / f_sp)

    def mel_to_hz(m: np.ndarray) -> np.ndarray:
        m = np.asarray(m, dtype=np.float64)
        return np.where(m >= min_log_mel, min_log_hz * np.exp(logstep * (m - min_log_mel)), f_sp * m)

    fft_freqs = np.linspace(0.0, sr / 2.0, 1 + n_fft // 2)
    mel_f = mel_to_hz(np.linspace(hz_to_mel(0.0), hz_to_mel(sr / 2.0), n_mels + 2))
    fdiff = np.diff(mel_f)
    ramps = mel_f[:, None] - fft_freqs[None, :]
    lower = -ramps[:-2] / fdiff[:-1, None]
    upper = ramps[2:] / fdiff[1:, None]
    weights = np.maximum(0.0, np.minimum(lower, upper))
    weights *= (2.0 / (mel_f[2 : n_mels + 2] - mel_f[:n_mels]))[:, None]
    return weights.astype(np.float32)


def _onset_strength(mag: np.ndarray, sr: int, n_fft: int, hop: int, aggregate=np.mean) -> np.ndarray:
    """``librosa.onset.onset_strength``: the mel power in dB (top 80 dB), its rectified first difference, aggregated over
    the bands and shifted back by the centring lag. ``mag`` is the STFT magnitude at ``hop``."""
    mel = _mel_bank(sr, n_fft) @ (mag.astype(np.float64) ** 2)
    db = 10.0 * np.log10(np.maximum(1e-10, mel))
    db = np.maximum(db, db.max() - 80.0) if db.size else db
    flux = np.maximum(0.0, db[:, 1:] - db[:, :-1])
    env = aggregate(flux, axis=0) if flux.size else np.zeros(0)
    pad = 1 + n_fft // (2 * hop)
    env = np.pad(env, (pad, 0), mode="constant")[: mag.shape[1]]
    return env.astype(np.float64)


def _rms(y: np.ndarray, frame_length: int, hop: int) -> np.ndarray:
    """``librosa.feature.rms(y, frame_length, hop_length, center=True)``."""
    pad = frame_length // 2
    padded = np.pad(np.asarray(y, dtype=np.float64), (pad, pad), mode="constant")
    n = 1 + max(0, (len(padded) - frame_length) // hop)
    sq = np.concatenate([[0.0], np.cumsum(padded ** 2)])
    starts = np.arange(n) * hop
    ends = np.minimum(starts + frame_length, len(padded))
    return np.sqrt(np.maximum(0.0, (sq[ends] - sq[starts]) / frame_length)).astype(np.float32)


def _tempo(env: np.ndarray, frame_rate: float, start_bpm: float = 120.0, std_bpm: float = 1.0,
           ac_size: float = 8.0, max_tempo: float = 320.0) -> float:
    """``librosa.feature.tempo`` (rhythm.tempo): the mean autocorrelation tempogram under a log-normal prior."""
    n = len(env)
    win = max(2, int(round(ac_size * frame_rate)))
    padded = np.pad(env, (win // 2, win // 2), mode="linear_ramp", end_values=(0, 0))
    window = _hann(win)
    acc = np.zeros(win, dtype=np.float64)
    fft_n = 1 << int(math.ceil(math.log2(2 * win)))
    block = 512
    for b0 in range(0, n, block):
        b1 = min(n, b0 + block)
        idx = np.arange(b0, b1)[:, None] + np.arange(win)[None, :]
        frames = padded[np.clip(idx, 0, len(padded) - 1)] * window[None, :]
        spec = np.fft.rfft(frames, n=fft_n, axis=1)
        ac = np.fft.irfft(spec * np.conj(spec), n=fft_n, axis=1)[:, :win]
        peak = np.max(np.abs(ac), axis=1, keepdims=True)
        acc += (ac / np.where(peak > 0, peak, 1.0)).sum(axis=0)
    tg = acc / max(n, 1)
    with np.errstate(divide="ignore"):
        bpms = 60.0 * frame_rate / np.arange(win, dtype=np.float64)
        logprior = -0.5 * ((np.log2(bpms) - np.log2(start_bpm)) / std_bpm) ** 2
    logprior[~np.isfinite(bpms)] = -np.inf
    below = np.flatnonzero(bpms < max_tempo)
    if below.size:
        logprior[: below[0]] = -np.inf
    score = np.log1p(1e6 * np.maximum(tg, 0.0)) + logprior
    return float(bpms[int(np.argmax(score))])


def _beat_frames(env: np.ndarray, bpm: float, frame_rate: float, tightness: float = 100.0) -> np.ndarray:
    """librosa's beat tracker (``librosa.beat.__beat_tracker``, Ellis 2007) step for step: the local score (its same-mode
    loop, which leaves out the envelope's first sample), the dynamic programme over the predecessors half a beat to two
    beats back (nearest first, so a tie keeps the nearer), the last local maximum of the cumulative score at least half
    their median, the backtrack, and the trim of the leading and trailing frames whose local score is under half the
    RMS of the smoothed score at the beats."""
    env = np.asarray(env, dtype=np.float64)
    n = len(env)
    if n == 0 or not np.any(env) or bpm <= 0:
        return np.zeros(0, dtype=int)
    fpb = float(np.round(frame_rate * 60.0 / bpm))
    if fpb < 1:
        return np.zeros(0, dtype=int)
    norm = env / (env.std(ddof=1) + np.finfo(np.float64).tiny) if n > 1 else env
    window = np.exp(-0.5 * (np.arange(-fpb, fpb + 1) * 32.0 / fpb) ** 2)
    half_k = len(window) // 2
    local = np.convolve(norm, window, mode="full")[half_k : half_k + n].copy()
    early = np.arange(min(n, len(window) - half_k))  # where librosa's loop skips the envelope's first sample
    local[early] -= window[early + half_k] * norm[0]
    cumscore = np.zeros(n, dtype=np.float64)
    backlink = np.full(n, -1, dtype=int)
    thresh = 0.01 * float(local.max())
    first = True
    near = int(round(fpb / 2))
    far = int(2 * fpb)
    log_fpb = math.log(fpb)
    for i in range(n):
        best, where = -np.inf, -1
        top = i - near
        if top >= 0:
            locs = np.arange(top, max(i - far, 0) - 1, -1)
            scores = cumscore[locs] - tightness * (np.log(i - locs) - log_fpb) ** 2
            k = int(np.argmax(scores))
            best, where = float(scores[k]), int(locs[k])
        cumscore[i] = local[i] + best if where >= 0 else local[i]
        if first and local[i] < thresh:
            backlink[i] = -1
        else:
            backlink[i] = where
            first = False
    padded = np.pad(cumscore, (1, 1), mode="edge")
    is_max = (cumscore > padded[:-2]) & (cumscore >= padded[2:])
    threshold_tail = 0.5 * float(np.median(cumscore[is_max])) if np.any(is_max) else 0.0
    tail = n - 1
    for k in range(n - 1, -1, -1):
        if is_max[k] and cumscore[k] >= threshold_tail:
            tail = k
            break
    marks = np.zeros(n, dtype=bool)
    k = tail
    while k >= 0:
        marks[k] = True
        k = int(backlink[k])
    hann5 = np.hanning(5)
    smooth = np.convolve(local[marks], hann5)[len(hann5) // 2 : n + len(hann5) // 2]
    threshold = 0.5 * float(np.sqrt(np.mean(smooth ** 2))) if smooth.size else 0.0
    k = 0
    while k < n and local[k] <= threshold:
        marks[k] = False
        k += 1
    k = n - 1
    while k >= 0 and local[k] <= threshold:
        marks[k] = False
        k -= 1
    return np.flatnonzero(marks)


def _peak_pick(x: np.ndarray, pre_max: int, post_max: int, pre_avg: int, post_avg: int, delta: float, wait: int) -> np.ndarray:
    """``librosa.util.peak_pick``: a sample that is the window's maximum and ``delta`` over its moving average."""
    n = len(x)
    if n == 0:
        return np.zeros(0, dtype=int)
    floor = float(x.min())
    pad_x = np.concatenate([np.full(pre_max, floor), x, np.full(post_max, floor)])
    mov_max = np.array([pad_x[i : i + pre_max + post_max + 1].max() for i in range(n)])
    mov_avg = np.array([x[max(0, i - pre_avg) : min(n, i + post_avg)].mean() for i in range(n)])
    detect = (x == mov_max) & (x >= mov_avg + delta)
    peaks, last = [], -np.inf
    for i in np.flatnonzero(detect):
        if i > last + wait:
            peaks.append(int(i))
            last = i
    return np.array(peaks, dtype=int)


def _onset_frames(env: np.ndarray, sr: int, hop: int) -> np.ndarray:
    """``librosa.onset.onset_detect(onset_envelope=env)`` with its default peak picking."""
    if len(env) == 0 or float(env.max()) <= float(env.min()):
        return np.zeros(0, dtype=int)
    x = (env - env.min()) / (env.max() - env.min())
    rate = sr / hop
    return _peak_pick(x, pre_max=int(0.03 * rate), post_max=int(0.00 * rate) + 1, pre_avg=int(0.10 * rate),
                      post_avg=int(0.10 * rate) + 1, delta=0.07, wait=int(0.03 * rate))


# ------------------------------------------------------------------------------------------------ the analysis


def librosa_available() -> bool:
    try:
        import librosa  # noqa: F401
    except Exception:
        return False
    return True


def engine_for(asked: str = "auto") -> str:
    asked = str(asked or "auto").strip().lower()
    if asked == "librosa" and not librosa_available():
        raise SongError("librosa is not installed in this Python. Use the numpy engine, or pip install librosa.")
    if asked in ("numpy", "librosa"):
        return asked
    return "librosa" if librosa_available() else "numpy"


def analyze(audio: np.ndarray, sr: int, fps: float = FPS, engine: str = "auto", onset_tau: float = ONSET_TAU,
            beat_tau: float = BEAT_TAU, section_min_seconds: float = SECTION_MIN_S) -> dict[str, Any]:
    """The desk's features for mono samples ``audio`` at ``sr``; ``engine`` "auto" takes librosa when it is there."""
    engine = engine_for(engine)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    sr = int(sr)
    if sr <= 0 or len(audio) < max(2048, sr // 4):
        raise SongError("The song is shorter than a quarter of a second, or has no samples.")
    duration = float(len(audio) / sr)
    n_frames = max(1, int(round(duration * fps)))
    times = (np.arange(n_frames, dtype=np.float64) + 0.5) / fps
    times = np.clip(times, 0.0, max(duration - 1.0 / sr, 0.0))
    hop = max(1, int(round(sr / fps)))
    beat_hop = max(1, int(round(sr / max(float(fps), BEAT_FPS))))
    if engine == "librosa":
        import librosa

        rms = librosa.feature.rms(y=audio, frame_length=max(hop * 2, 512), hop_length=hop)[0]
        onset_env = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop)
        stft = np.abs(librosa.stft(audio, hop_length=hop, n_fft=2048))
        freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
        tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sr, hop_length=beat_hop, units="frames")
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop, units="frames")
        tempo = float(np.asarray(tempo).reshape(-1)[0]) if np.asarray(tempo).size else 0.0
    else:
        rms = _rms(audio, max(hop * 2, 512), hop)
        stft = _stft_mag(audio, 2048, hop)
        onset_env = _onset_strength(stft, sr, 2048, hop)
        freqs = np.linspace(0.0, sr / 2.0, 1 + 2048 // 2)
        beat_mag = stft if beat_hop == hop else _stft_mag(audio, 2048, beat_hop)
        beat_env = _onset_strength(beat_mag, sr, 2048, beat_hop, aggregate=np.median)  # librosa's beat_track takes the median
        rate = sr / beat_hop
        tempo = _tempo(beat_env, rate) if np.any(beat_env) else 0.0
        beat_frames = _beat_frames(beat_env, tempo, rate)
        onset_frames = _onset_frames(onset_env, sr, hop)
    rms_times = np.arange(len(rms)) * hop / sr
    rms_f = _robust_norm(_resample(np.asarray(rms), rms_times, times))
    onset_times_env = np.arange(len(onset_env)) * hop / sr
    onset_strength = _robust_norm(_resample(np.asarray(onset_env), onset_times_env, times))
    stft_times = np.arange(stft.shape[1]) * hop / sr
    bands: dict[str, np.ndarray] = {}
    for name, (lo, hi) in BANDS_HZ.items():
        mask = (freqs >= lo) & (freqs < hi)
        series = stft[mask].mean(axis=0) if np.any(mask) else np.zeros(stft.shape[1], dtype=np.float32)
        bands[name] = _robust_norm(_resample(series, stft_times, times))
    beat_times = np.atleast_1d(beat_frames) * beat_hop / sr
    onset_times = np.atleast_1d(onset_frames) * hop / sr
    is_beat = np.zeros(n_frames, dtype=bool)
    is_onset = np.zeros(n_frames, dtype=bool)
    for stamp in beat_times:
        is_beat[int(np.clip(np.floor(float(stamp) * fps), 0, n_frames - 1))] = True
    for stamp in onset_times:
        is_onset[int(np.clip(np.floor(float(stamp) * fps), 0, n_frames - 1))] = True
    onset_decay = _decay_env(is_onset, fps, onset_tau)
    beat_decay = _decay_env(is_beat, fps, beat_tau)
    energy = (0.30 * bands["sub"] + 0.40 * bands["bass"] + 0.20 * bands["mid"] + 0.10 * bands["high"]).astype(np.float32)
    energy = _robust_norm(_smooth(energy, fps, 0.08))
    sections = detect_sections(times, energy, fps, section_min_seconds)
    if sections:
        sections[0]["start"] = 0.0
        sections[0]["start_frame"] = 0
        sections[-1]["end"] = duration
        sections[-1]["end_frame"] = n_frames
    frames = []
    for i in range(n_frames):
        section = _section_at(sections, i) if sections else {"label": "sustain", "mutate": 0.2}
        label = section["label"]
        frames.append({"i": i, "t": round(float(i / fps), 6), "rms": round(float(rms_f[i]), 6),
                       "sub": round(float(bands["sub"][i]), 6), "bass": round(float(bands["bass"][i]), 6),
                       "mid": round(float(bands["mid"][i]), 6), "high": round(float(bands["high"][i]), 6),
                       "onset_strength": round(float(onset_strength[i]), 6), "onset_env": round(float(onset_decay[i]), 6),
                       "beat_env": round(float(beat_decay[i]), 6), "is_onset": bool(is_onset[i]),
                       "is_beat": bool(is_beat[i]), "energy": round(float(energy[i]), 6), "section": label,
                       "mutate": float(section.get("mutate", SECTION_MUTATE.get(label, 0.2))), "is_drop": label == "drop"})
    public_sections = [{"index": k, "label": s["label"], "start": round(float(s["start"]), 6), "end": round(float(s["end"]), 6),
                        "start_frame": int(s["start_frame"]), "end_frame": int(s["end_frame"]),
                        "level": round(float(s["level"]), 6), "slope": round(float(s["slope"]), 6),
                        "mutate": float(s["mutate"])} for k, s in enumerate(sections)]
    beats = [round(float(stamp), 6) for stamp in beat_times]
    features = {"sr": sr, "fps": float(fps), "duration": round(duration, 6), "n_frames": n_frames, "tempo": round(float(tempo), 3),
                "bands_hz": {name: list(pair) for name, pair in BANDS_HZ.items()}, "beats": beats,
                "onsets": [round(float(stamp), 6) for stamp in onset_times], "sections": public_sections, "frames": frames}
    features["drop"] = drop_from_audio(audio, sr, beats)
    features["engine"] = engine
    return features


# ------------------------------------------------------------------------------------------------ the drop


def drop_time(rms: np.ndarray, step_s: float, beats: list, duration: float, lo: float = 0.25, hi: float = 0.85) -> float | None:
    """``xenoform.beatfx.drop_time`` on a loudness series ``rms`` (one value every ``step_s`` seconds): the biggest jump
    from the half bar before to the two bars after, between ``lo`` and ``hi`` of the song, snapped to the nearest beat."""
    rms = np.asarray(rms, dtype=np.float64)
    if len(rms) < 4 or duration <= 0:
        return None
    t = np.arange(len(rms)) * step_s
    beats = [float(b) for b in beats or []]
    bar = 4 * float(np.median(np.diff(beats))) if len(beats) >= 2 else 2.0
    win = max(1, int(round(bar / step_s)))
    half, two = max(1, win // 2), 2 * win
    smooth = np.convolve(rms, np.ones(half) / half, mode="full")[: len(rms)]
    ahead = np.convolve(rms[::-1], np.ones(two) / two, mode="full")[: len(rms)][::-1]
    score = np.where((t >= duration * lo) & (t <= duration * hi), ahead - smooth, -1e9)
    drop = float(t[int(np.argmax(score))])
    return float(min(beats, key=lambda b: abs(b - drop))) if beats else drop


def drop_from_audio(audio: np.ndarray, sr: int, beats: list) -> float | None:
    """The desk's drop: RMS at 22.05 kHz with a 512-sample hop (here the same 23 ms hop at the song's own rate)."""
    hop = max(1, int(round(sr * 512 / 22050)))
    # librosa.feature.rms's default frame is 2048 samples at 22.05 kHz: four hops
    rms = _rms(np.asarray(audio, dtype=np.float32), 4 * hop, hop) if len(audio) else np.zeros(0)
    return drop_time(rms, hop / sr, beats, len(audio) / float(sr))


def drop_from_features(features: dict) -> float | None:
    """The drop of a features dict that came without its audio: the same rule on its per-frame ``rms``."""
    frames = features.get("frames") or []
    fps = float(features.get("fps") or 0.0)
    if not frames or fps <= 0:
        return None
    return drop_time(np.array([float(f.get("rms") or 0.0) for f in frames]), 1.0 / fps, list(features.get("beats") or []),
                     float(features.get("duration") or len(frames) / fps))


# ------------------------------------------------------------------------------------------------ reading audio


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        n_ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        data = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        val = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        data = (np.where(val >= 1 << 23, val - (1 << 24), val)).astype(np.float32) / float(1 << 23)
    elif width == 4:
        data = np.frombuffer(raw, "<i4").astype(np.float32) / float(1 << 31)
    else:
        raise SongError(f"{path.name}: a {8 * width}-bit WAV is not one this reader knows.")
    return data.reshape(-1, n_ch).mean(axis=1).astype(np.float32), int(sr)


def _read_av(path: Path) -> tuple[np.ndarray, int]:
    import av  # ComfyUI ships PyAV (comfy_api reads and writes video with it)

    chunks, sr = [], 0
    with av.open(str(path)) as box:
        stream = next((s for s in box.streams if s.type == "audio"), None)
        if stream is None:
            raise SongError(f"{path.name} has no audio track.")
        sr = int(stream.rate or stream.codec_context.sample_rate or 0)
        resampler = av.AudioResampler(format="flt", layout="mono", rate=sr)
        for frame in box.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks or sr <= 0:
        raise SongError(f"{path.name} decoded to no samples.")
    return np.concatenate(chunks).astype(np.float32), sr


def ffmpeg_exe() -> str | None:
    """The ffmpeg binary: on PATH, else the one imageio-ffmpeg carries (ComfyUI installs often have it)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _read_ffmpeg(path: Path, sr: int = 44100) -> tuple[np.ndarray, int]:
    exe = ffmpeg_exe()
    if not exe:
        raise SongError(f"{path.name}: neither PyAV nor ffmpeg is here to read it. Use a WAV, or install ffmpeg.")
    raw = subprocess.run([exe, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=False).stdout
    data = np.frombuffer(raw, np.float32).copy()
    if not data.size:
        raise SongError(f"ffmpeg could not read {path.name}.")
    return data, sr


def load_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Mono float32 samples and their rate, at the file's own rate (as ``librosa.load(path, sr=None, mono=True)``)."""
    path = Path(path)
    if not path.is_file():
        raise SongError(f"There is no song at {path}.")
    if path.suffix.lower() == ".wav":
        try:
            return _read_wav(path)
        except (wave.Error, EOFError, SongError):
            pass  # a float or compressed WAV: the decoders below read it
    if librosa_available():  # the desk's own reader, where there is one: the same samples the desk analyses
        try:
            import librosa

            y, sr = librosa.load(str(path), sr=None, mono=True)
            return np.asarray(y, dtype=np.float32), int(sr)
        except Exception:
            pass
    try:
        return _read_av(path)
    except SongError:
        raise
    except Exception:
        return _read_ffmpeg(path)


def from_comfy_audio(audio: dict) -> tuple[np.ndarray, int]:
    """ComfyUI's AUDIO value (``{"waveform": tensor [batch, channels, samples], "sample_rate": int}``) as mono samples."""
    wave_ = audio.get("waveform") if isinstance(audio, dict) else None
    sr = int((audio or {}).get("sample_rate") or 0) if isinstance(audio, dict) else 0
    if wave_ is None or sr <= 0:
        raise SongError("The AUDIO input carries no waveform.")
    data = wave_.detach().cpu().float().numpy() if hasattr(wave_, "detach") else np.asarray(wave_, dtype=np.float32)
    data = np.asarray(data, dtype=np.float32)
    while data.ndim > 2:
        data = data[0]
    if data.ndim == 2:
        data = data.mean(axis=0)
    return data.astype(np.float32), sr


def write_wav(path: str | Path, audio: np.ndarray, sr: int) -> Path:
    """Mono 16-bit PCM, for an AUDIO input that came with no file (the assemble muxes a file)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm.tobytes())
    return path


# ------------------------------------------------------------------------------------------------ the song value


def file_key(path: str | Path) -> str:
    """A short key for a song file: its name, size and modification time (what makes ComfyUI analyse it again)."""
    p = Path(path)
    try:
        st = p.stat()
        text = f"{p.resolve()}|{st.st_size}|{st.st_mtime_ns}"
    except OSError:
        text = str(p)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def read_features(path: str | Path) -> dict:
    """A desk ``features.json`` (``xenoform.analyze.write_features``), checked for the keys the planner reads."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SongError(f"{path.name} is not a features file the desk wrote: {exc}") from exc
    if not isinstance(data, dict) or "duration" not in data or "beats" not in data:
        raise SongError(f"{path.name} has no duration or beats: it is not a features file the desk wrote.")
    return data


def song_value(features: dict, *, path: str | Path | None = None, name: str = "", engine: str = "") -> dict:
    """What the Song analysis node hands on: the features, the file the Assemble muxes, the drop, a key for the song."""
    feats = dict(features)
    drop = feats.get("drop")
    if drop is None:
        drop = drop_from_features(feats)
        feats["drop"] = drop
    beats = [float(b) for b in feats.get("beats") or []]
    key_text = f"{float(feats.get('duration') or 0.0):.3f}|{len(beats)}|{beats[0] if beats else 0:.3f}|{beats[-1] if beats else 0:.3f}"
    return {"features": feats, "path": str(path) if path else "", "name": name or (Path(path).name if path else "song"),
            "drop": drop, "engine": engine or str(feats.get("engine") or "desk"),
            "key": hashlib.sha1(key_text.encode("utf-8")).hexdigest()[:12]}


def describe(song: dict) -> str:
    """One line: the song's length, tempo, beats, sections and drop."""
    f = song.get("features") or {}
    secs = f.get("sections") or []
    labels = ", ".join(f"{s['label']} {float(s['start']):.1f}s" for s in secs[:12])
    drop = song.get("drop")
    return (f"{song.get('name') or 'song'}: {float(f.get('duration') or 0):.1f} s, {float(f.get('tempo') or 0):.0f} BPM, "
            f"{len(f.get('beats') or [])} beats, {len(secs)} sections ({labels}), "
            f"drop {'at ' + format(float(drop), '.2f') + ' s' if drop is not None else 'none found'} · {song.get('engine')}")
