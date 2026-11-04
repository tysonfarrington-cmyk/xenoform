"""The node pack's song analysis (comfy_pack/song.py) against the desk's (xenoform.analyze, beatfx.drop_time).

ComfyUI ships no librosa, so the pack runs librosa's steps in numpy; these tests hold that copy to the desk's own
analysis on the bundled demo and the 20 s bundled song, key for key, and the librosa path to it line for line.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfy_pack import song as S  # noqa: E402

DEMO = ROOT / "examples" / "demo.wav"
SHORT = ROOT / "examples" / "songs" / "morphing_wobble_20s.mp3"
FROZEN = ROOT / "tests" / "fixtures" / "analyses"

librosa = pytest.importorskip("librosa")


def _desk(path: Path, fps: float = 12.0) -> dict:
    from xenoform.analyze import analyze_audio

    y, sr = librosa.load(path, sr=None, mono=True)
    return analyze_audio(y, int(sr), fps=fps)


def _same(a, b, where="") -> None:
    """Equal, but a float may differ in its last rounded digit (librosa's float32 STFT against numpy's float64)."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), where
        for k in a:
            _same(a[k], b[k], f"{where}.{k}")
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), where
        for k, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{where}[{k}]")
    elif isinstance(a, float) and not isinstance(a, bool):
        assert b == pytest.approx(a, abs=2e-6), where
    else:
        assert a == b, where


@pytest.mark.parametrize("path", [DEMO, SHORT], ids=["demo", "wobble-20s"])
def test_numpy_engine_is_the_desks_analysis(path):
    desk = _desk(path)
    y, sr = S.load_audio(path)
    pack = S.analyze(y, sr, fps=12.0, engine="numpy")
    assert pack["engine"] == "numpy"
    for key in ("beats", "onsets", "tempo", "n_frames", "duration", "sr"):
        assert pack[key] == desk[key], key  # the clock is exact
    assert [s["label"] for s in pack["sections"]] == [s["label"] for s in desk["sections"]]
    assert [(f["is_beat"], f["is_onset"], f["section"]) for f in pack["frames"]] == \
           [(f["is_beat"], f["is_onset"], f["section"]) for f in desk["frames"]]
    _same(desk, {k: pack[k] for k in desk})


def test_librosa_engine_is_the_desks_line_for_line():
    desk = _desk(DEMO, fps=24.0)
    y, sr = librosa.load(DEMO, sr=None, mono=True)
    pack = S.analyze(y, int(sr), fps=24.0, engine="librosa")
    assert {k: pack[k] for k in desk} == desk


def test_the_drop_is_the_desks():
    from xenoform import beatfx

    y, sr = S.load_audio(DEMO)
    feats = S.analyze(y, sr, fps=12.0, engine="numpy")
    assert feats["drop"] == pytest.approx(beatfx.drop_time(DEMO, feats["beats"]), abs=1e-6)
    assert feats["drop"] == pytest.approx(5.5015, abs=1e-3)
    assert S.drop_from_features(feats) == pytest.approx(feats["drop"], abs=1e-6)


def test_the_wav_reader_reads_what_librosa_reads():
    y, sr = S.load_audio(DEMO)
    ref, ref_sr = librosa.load(DEMO, sr=None, mono=True)
    assert sr == ref_sr == 44100
    assert np.array_equal(y, ref)


def test_a_desk_features_file_loads_as_a_song():
    feats = S.read_features(FROZEN / "morphing-wobble-20s.features.json")
    song = S.song_value(feats, path=SHORT, name=SHORT.name)
    assert song["drop"] is not None and 0 < song["drop"] < feats["duration"]
    assert song["key"] and song["path"].endswith("morphing_wobble_20s.mp3")
    assert "BPM" in S.describe(song) and "drop at" in S.describe(song)
    with pytest.raises(S.SongError):
        S.read_features(ROOT / "configs" / "vibes.json")


def test_comfy_audio_becomes_mono_samples(tmp_path):
    y, sr = S.load_audio(DEMO)
    stereo = np.stack([y, y])[None, ...]  # ComfyUI's AUDIO: [batch, channels, samples]
    mono, rate = S.from_comfy_audio({"waveform": stereo, "sample_rate": sr})
    assert rate == sr and mono.shape == y.shape and np.allclose(mono, y)
    out = S.write_wav(tmp_path / "a.wav", mono, rate)
    back, back_sr = S.load_audio(out)
    assert back_sr == sr and np.abs(back - y).max() < 1e-3
    with pytest.raises(S.SongError):
        S.from_comfy_audio({"waveform": None, "sample_rate": 0})


def test_a_missing_or_tiny_song_is_said_plainly(tmp_path):
    with pytest.raises(S.SongError):
        S.load_audio(tmp_path / "nope.wav")
    with pytest.raises(S.SongError):
        S.analyze(np.zeros(100, np.float32), 44100, engine="numpy")
