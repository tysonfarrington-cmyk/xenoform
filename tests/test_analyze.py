import numpy as np

from xenoform.analyze import analyze_audio
from xenoform.synth import synthesize


def test_synth_is_deterministic_and_twelve_seconds():
    a = synthesize(duration=12.0, sr=22050, bpm=120, seed=7)
    b = synthesize(duration=12.0, sr=22050, bpm=120, seed=7)
    assert a.shape == b.shape
    assert np.allclose(a, b)
    assert abs(len(a) / 22050 - 12.0) < 0.01
    # The drop is actually louder than the calm intro.
    intro = np.sqrt(np.mean(a[int(0.5 * 22050) : int(2.5 * 22050)] ** 2))
    drop = np.sqrt(np.mean(a[int(6.2 * 22050) : int(8.5 * 22050)] ** 2))
    assert drop > intro * 1.4


def test_analyze_frames_bands_and_drop():
    sr = 22050
    audio = synthesize(duration=12.0, sr=sr, bpm=120, seed=7)
    features = analyze_audio(audio, sr, fps=12)
    assert features["n_frames"] == 144
    assert abs(features["duration"] - 12.0) < 0.02
    assert features["beats"], "expected a beat grid from the kick"
    assert features["onsets"], "expected onsets"
    assert features["sections"]
    labels = {section["label"] for section in features["sections"]}
    assert "drop" in labels

    drop_energy = []
    calm_energy = []
    for frame in features["frames"]:
        for key in ("rms", "sub", "bass", "mid", "high", "energy", "onset_env"):
            value = frame[key]
            assert 0.0 <= value <= 1.0
        if frame["is_drop"]:
            drop_energy.append(frame["energy"])
        if frame["section"] == "calm":
            calm_energy.append(frame["energy"])
    assert drop_energy, "drop section should cover some frames"
    assert calm_energy
    assert float(np.mean(drop_energy)) > float(np.mean(calm_energy))

    # JSON-safe types: no numpy scalars.
    import json

    json.dumps(features)


def test_silence_is_one_section():
    sr = 22050
    features = analyze_audio(np.zeros(sr * 360, dtype=np.float32), sr, fps=24, section_min_seconds=1.4)
    assert abs(features["duration"] - 360.0) < 0.05
    assert len(features["sections"]) == 1
    assert features["tempo"] == 0.0


def test_beats_keep_their_own_clock_at_a_low_frame_rate():
    """Beats and tempo come from analyze.BEAT_FPS at the least: 12 fps frames find the same beats as 24 fps frames, and
    the frames themselves stay at the rate asked for."""
    from xenoform.analyze import BEAT_FPS, analyze_audio

    sr = 22050
    period = 60.0 / 130.909  # eleven 24 fps frames a beat; at 12 fps the tracker could only read 120 or 144 here
    audio = np.zeros(int(sr * 20), dtype=np.float32)
    click = np.exp(-np.linspace(0.0, 8.0, 800, dtype=np.float32)) * np.sin(np.linspace(0.0, 300.0, 800, dtype=np.float32))
    for k in range(int(20 / period)):
        at = int(k * period * sr)
        audio[at:at + len(click)] += click[: len(audio) - at]
    low, high = analyze_audio(audio, sr, fps=12.0), analyze_audio(audio, sr, fps=BEAT_FPS)
    assert low["fps"] == 12.0 and low["n_frames"] == 240 and high["n_frames"] == 480
    assert low["beats"] == high["beats"] and low["tempo"] == high["tempo"]
    assert abs(float(low["tempo"]) - 130.909) < 1.0
