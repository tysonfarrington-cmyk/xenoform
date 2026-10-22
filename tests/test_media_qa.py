import numpy as np
from xenoform import media_qa as Q
from xenoform.config import DEFAULTS


def test_house_profile_is_default():
    h = DEFAULTS["house"]
    assert h["dance_fx"]["intro"] == {"preset": "cyan-flash", "intensity": 1.25}
    assert h["transitions"]["max_uses_per_type"] == 2 and "kaleidoscope" in h["transitions"]["banned"]
    assert h["audio"]["target_lufs"] == -14.0 and h["audio"]["limiter"]["attack_ms"] == 5


def test_click_scan_finds_a_step_not_a_sine():
    sr = 48000; t = np.arange(sr) / sr; x = 0.3 * np.sin(2 * np.pi * 220 * t)
    assert Q.click_scan(x, sr) == []
    y = x.copy(); y[24000:] += 0.4
    assert any(abs(f["t"] - 0.5) < 0.01 for f in Q.click_scan(y, sr))


def test_loudness_of_sine():
    sr = 48000; t = np.arange(sr * 3) / sr; x = 10 ** (-20 / 20) * np.sqrt(2) * np.sin(2 * np.pi * 1000 * t)
    m = Q.loudness(x, sr)
    assert -21.5 < m["lufs"] < -18.5 and -18 < m["true_peak_dbtp"] < -15


def test_transition_rules():
    assert Q.check_transitions(["flow-morph", "flow-morph", "lens-breath"]) == []
    bad = {f["check"] for f in Q.check_transitions(["wipe", "echo-trail"] + ["flow-morph"] * 3)}
    assert {"transition_banned", "transition_overuse"} <= bad
    # structural transitions are exempt from the cap and always allowed; banned names match the id by substring
    assert Q.check_transitions(["cut"] * 8 + ["scene-morph"] * 3 + ["black-hold"]) == []
    assert [f["check"] for f in Q.check_transitions(["luma-wipe"])] == ["transition_banned"]
    assert [f["check"] for f in Q.check_transitions(["stutter-cut", "stutter-cut"])] == ["transition_banned"]


def test_static_and_opening_cuts():
    rng = np.random.RandomState(0); still = np.full((60, 20, 12), 80.0)
    assert Q.check_static_shots(still, 12, [])[0]["check"] == "static_shot"
    moving = rng.rand(60, 20, 12) * 255
    assert Q.check_static_shots(moving, 12, []) == []
    assert Q.check_opening_cuts([24, 48, 72, 96], 24) and not Q.check_opening_cuts([24, 400], 24)


def test_vo_double_word_and_contrast():
    f = Q.check_vo_transcript([{"start": 1.0, "end": 2.0, "text": "Every every stem"}], ["Every stem, its own signal"])
    assert f and f[0]["check"] == "vo_double_word"
    assert Q.contrast_ratio((255, 255, 255), (0, 0, 0)) > 20
    img = np.full((40, 40, 3), 120, np.uint8); m = np.zeros((40, 40), bool); m[18:22, 10:30] = True; img[m] = 130
    assert Q.check_text_legibility(img, m)


def test_loudness_is_k_weighted_and_matches_ffmpeg(tmp_path):
    """BS.1770: a stereo 997 Hz sine at -20 dBFS reads -20.0 LUFS; K-weighting lifts 4 kHz by about 3 dB."""
    import shutil, subprocess
    import numpy as np
    from xenoform import media_qa as Q

    sr = 48000
    t = np.arange(sr * 3) / sr
    s1 = np.repeat((0.1 * np.sin(2 * np.pi * 997 * t))[:, None], 2, axis=1)
    s4 = np.repeat((0.1 * np.sin(2 * np.pi * 4000 * t))[:, None], 2, axis=1)
    l1, l4 = Q.loudness(s1, sr)["lufs"], Q.loudness(s4, sr)["lufs"]
    assert abs(l1 - (-20.0)) < 0.2, l1
    assert 2.5 < l4 - l1 < 4.5, (l1, l4)
    assert abs(Q.loudness(s1[:, 0], sr)["lufs"] - (-23.0)) < 0.2  # one channel: -3 dB
    assert abs(Q.loudness(s1[::1], 44100)["lufs"] - Q.loudness(s1, sr)["lufs"]) < 0.5  # other rates are resampled
    if not shutil.which("ffmpeg"):
        return
    wav = tmp_path / "n.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=c=pink:r=48000:a=0.3:d=4", "-ac", "2", str(wav)], check=True)
    import soundfile as sf

    x, fs = sf.read(str(wav))
    ref = Q.loudness_ffmpeg(str(wav))
    assert ref and abs(Q.loudness(x, fs)["lufs"] - ref["lufs"]) < 0.3, (Q.loudness(x, fs), ref)


def test_click_scan_skips_drum_hits_but_flags_a_splice():
    import numpy as np
    from xenoform import media_qa as Q

    sr = 48000
    t = np.arange(sr * 2) / sr
    rng = np.random.default_rng(3)
    y = 0.05 * np.sin(2 * np.pi * 110 * t)
    for hit in (0.5, 1.0, 1.5):  # kick-like bursts: an attack, then a 60 ms decay
        i = int(hit * sr); n = int(0.06 * sr)
        y[i:i + n] += 0.6 * np.exp(-np.arange(n) / (0.01 * sr)) * np.sign(rng.standard_normal(n))
    assert Q.click_scan(y, sr) == []  # transients are music, not clicks
    y[int(1.25 * sr):] += 0.4  # a DC step between hits: a bad splice
    found = Q.click_scan(y, sr)
    assert found and abs(found[0]["t"] - 1.25) < 0.01
    assert Q.click_scan(y, sr, music_onsets=[1.25]) == []  # a declared drum hit at that time is honoured
