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
