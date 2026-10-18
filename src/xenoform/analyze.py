"""Per-frame audio features at the render fps.

Bands are robust-normalized to 0–1 (99th percentile) so one clap cannot
flatten the rest of the track. Section labels are calm, build, drop, release,
or sustain. The loudest sustained region is forced to ``drop`` when it sits
clearly above the track mean — that is the mutation the renderer and the
LTX prompts key off.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

BANDS_HZ = {
    "sub": (20.0, 60.0),
    "bass": (60.0, 250.0),
    "mid": (250.0, 2000.0),
    "high": (2000.0, 8000.0),
}

SECTION_MUTATE = {
    "calm": 0.0,
    "build": 0.35,
    "drop": 1.0,
    "release": 0.45,
    "sustain": 0.2,
}


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
    """Split the track where smoothed energy changes quickly, then label each span."""
    if len(times) == 0:
        return []
    smooth = _smooth(energy, fps, 0.4)
    grad = np.gradient(smooth, times) if len(times) > 1 else np.zeros(1, dtype=np.float32)
    mag = np.abs(grad)
    thresh = float(np.percentile(mag, 82)) if len(mag) else 0.0
    min_gap = max(1, int(round(min_seconds * fps)))
    boundaries = [0]
    # A flat line has no peaks. Treating every sample as a peak slices silence
    # into one shot per minimum section, which is a storyboard per minute of quiet.
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
        # `end` is the first frame of the next span, except for the last boundary
        # which is the final frame index. Use an inclusive slice for the last one.
        stop = end if end == len(times) - 1 else end
        region = smooth[start : stop + 1] if stop == len(times) - 1 and end == start else smooth[start:end]
        if region.size == 0:
            region = smooth[start : start + 1]
        level = float(np.mean(region))
        slope = float(region[-1] - region[0])
        spans.append(
            {
                "start_frame": int(start),
                "end_frame": int(end if end > start else start + 1),
                "start": float(times[start]),
                "end": float(times[min(end, len(times) - 1)]),
                "level": level,
                "slope": slope,
                "label": "sustain",
            }
        )
    if not spans:
        return spans

    levels = [span["level"] for span in spans]
    mean_level = float(np.mean(levels))
    peak_index = int(np.argmax(levels))
    peak = levels[peak_index]
    for i, span in enumerate(spans):
        # A quiet span is calm even when a gentle slope is left over from the smoother.
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
    # The mutation moment is the loudest span, when it actually rises above the track.
    # Spans that stay nearly that loud are the same drop, not a new "sustain".
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


def analyze_audio(
    audio: np.ndarray,
    sr: int,
    fps: float,
    onset_tau: float = 0.085,
    beat_tau: float = 0.05,
    section_min_seconds: float = 1.4,
) -> dict[str, Any]:
    import librosa

    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    duration = float(len(audio) / sr) if sr else 0.0
    n_frames = max(1, int(round(duration * fps)))
    times = (np.arange(n_frames, dtype=np.float64) + 0.5) / fps
    # Keep frame centers inside the file.
    times = np.clip(times, 0.0, max(duration - 1.0 / sr, 0.0))

    hop = max(1, int(round(sr / fps)))
    rms = librosa.feature.rms(y=audio, frame_length=max(hop * 2, 512), hop_length=hop)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    rms_f = _robust_norm(_resample(rms, rms_times, times))

    onset_env = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop)
    onset_times_env = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=hop)
    onset_strength = _robust_norm(_resample(onset_env, onset_times_env, times))

    stft = np.abs(librosa.stft(audio, hop_length=hop, n_fft=2048))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    stft_times = librosa.frames_to_time(np.arange(stft.shape[1]), sr=sr, hop_length=hop)
    bands: dict[str, np.ndarray] = {}
    for name, (lo, hi) in BANDS_HZ.items():
        mask = (freqs >= lo) & (freqs < hi)
        if not np.any(mask):
            series = np.zeros(stft.shape[1], dtype=np.float32)
        else:
            series = stft[mask].mean(axis=0)
        bands[name] = _robust_norm(_resample(series, stft_times, times))

    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=sr, hop_length=hop, units="frames")
    beat_times = librosa.frames_to_time(np.atleast_1d(beat_frames), sr=sr, hop_length=hop)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=hop, units="frames")
    onset_times = librosa.frames_to_time(np.atleast_1d(onset_frames), sr=sr, hop_length=hop)

    is_beat = np.zeros(n_frames, dtype=bool)
    is_onset = np.zeros(n_frames, dtype=bool)
    for stamp in np.atleast_1d(beat_times):
        index = int(np.clip(np.floor(float(stamp) * fps), 0, n_frames - 1))
        is_beat[index] = True
    for stamp in np.atleast_1d(onset_times):
        index = int(np.clip(np.floor(float(stamp) * fps), 0, n_frames - 1))
        is_onset[index] = True

    onset_decay = _decay_env(is_onset, fps, onset_tau)
    beat_decay = _decay_env(is_beat, fps, beat_tau)

    energy = (
        0.30 * bands["sub"]
        + 0.40 * bands["bass"]
        + 0.20 * bands["mid"]
        + 0.10 * bands["high"]
    ).astype(np.float32)
    energy = _robust_norm(_smooth(energy, fps, 0.08))

    sections = detect_sections(times, energy, fps, section_min_seconds)
    # Fix end stamps so sections tile [0, duration].
    if sections:
        sections[0]["start"] = 0.0
        sections[0]["start_frame"] = 0
        sections[-1]["end"] = duration
        sections[-1]["end_frame"] = n_frames

    frames = []
    for i in range(n_frames):
        section = _section_at(sections, i) if sections else {
            "label": "sustain",
            "mutate": 0.2,
        }
        label = section["label"]
        frames.append(
            {
                "i": i,
                "t": round(float(i / fps), 6),
                "rms": round(float(rms_f[i]), 6),
                "sub": round(float(bands["sub"][i]), 6),
                "bass": round(float(bands["bass"][i]), 6),
                "mid": round(float(bands["mid"][i]), 6),
                "high": round(float(bands["high"][i]), 6),
                "onset_strength": round(float(onset_strength[i]), 6),
                "onset_env": round(float(onset_decay[i]), 6),
                "beat_env": round(float(beat_decay[i]), 6),
                "is_onset": bool(is_onset[i]),
                "is_beat": bool(is_beat[i]),
                "energy": round(float(energy[i]), 6),
                "section": label,
                "mutate": float(section.get("mutate", SECTION_MUTATE.get(label, 0.2))),
                "is_drop": label == "drop",
            }
        )

    tempo_value = tempo
    if isinstance(tempo_value, np.ndarray):
        tempo_value = float(tempo_value.reshape(-1)[0]) if tempo_value.size else 0.0
    else:
        tempo_value = float(tempo_value)

    public_sections = []
    for index, section in enumerate(sections):
        public_sections.append(
            {
                "index": index,
                "label": section["label"],
                "start": round(float(section["start"]), 6),
                "end": round(float(section["end"]), 6),
                "start_frame": int(section["start_frame"]),
                "end_frame": int(section["end_frame"]),
                "level": round(float(section["level"]), 6),
                "slope": round(float(section["slope"]), 6),
                "mutate": float(section["mutate"]),
            }
        )

    return {
        "sr": int(sr),
        "fps": float(fps),
        "duration": round(duration, 6),
        "n_frames": n_frames,
        "tempo": round(tempo_value, 3),
        "bands_hz": {name: list(pair) for name, pair in BANDS_HZ.items()},
        "beats": [round(float(stamp), 6) for stamp in np.atleast_1d(beat_times)],
        "onsets": [round(float(stamp), 6) for stamp in np.atleast_1d(onset_times)],
        "sections": public_sections,
        "frames": frames,
    }


def write_features(path: str | Path, features: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(features, indent=2), encoding="utf-8")


def read_features(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
