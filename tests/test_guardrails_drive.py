"""Guard rails from the 25 Oct test drive: a Simple cut always takes the beat-cut compose, the negative pulse is
softened on a bright frame, and the QA pass counts hard flashes."""
import subprocess

import numpy as np
import pytest

from xenoform import dance_fx, dense, post_qa


def test_a_simple_cut_always_finishes_even_flow_at_16_9():
    flow_wide = {"energy_preset": "flow", "aspect": "16:9", "quality_tier": "draft", "end_card": False, "morph_count": "auto"}
    assert dense.wants_finishing(flow_wide) is False  # Advanced may still take the plain morph pass
    assert dense.wants_finishing({**flow_wide, "mode": "simple"}) is True
    assert dense.wants_finishing({**flow_wide, "aspect": "9:16"}) is True


def test_the_negative_pulse_is_softer_on_a_bright_frame():
    dark = np.full((36, 64, 3), 30, np.uint8)
    bright = np.full((36, 64, 3), 220, np.uint8)
    out = {}
    for name, frame in (("dark", dark), ("bright", bright)):
        fx = dance_fx.DanceFX("negative-rush", intensity=1.0)
        hit = {"drums": 1.0, "bass": 1.0, "other": 0.0, "vocals": 0.0, "beat": 1.0}
        for _ in range(16):  # the follower eases in; hold the beat high for a few frames
            res = fx.apply(frame.copy(), hit)
        out[name] = abs(float(res.astype(np.float32).mean()) - float(frame.mean()))
    assert out["dark"] > 40 and out["bright"] < out["dark"] * 0.6  # a bright page flips a quarter as far


def test_flash_counts_and_the_qa_issue(tmp_path):
    steady = [20.0 + (i % 3) for i in range(48)]
    assert post_qa.flash_counts(steady) == {"frames": 48, "flashes": 0, "max_jump": 2.0}
    strobing = [20.0 if i % 2 else 200.0 for i in range(48)]
    assert post_qa.flash_counts(strobing)["flashes"] == 47
    # a two-second clip that strobes black / white every frame: the QA pass flags it; a steady one passes
    strobe = tmp_path / "strobe.mp4"
    subprocess.run([post_qa._ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x36:r=24:d=2",
                    "-vf", "geq=lum='if(mod(N,2),255,0)':cb=128:cr=128", "-pix_fmt", "yuv420p", str(strobe)], check=True)
    rep = post_qa.flash_report(strobe, 24.0)
    assert rep["frames"] == 48 and rep["flashes"] >= 40 and rep["issues"] and "hard flashes" in rep["issues"][0]
    calm = tmp_path / "calm.mp4"
    subprocess.run([post_qa._ffmpeg(), "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=64x36:r=24:d=2", "-pix_fmt", "yuv420p", str(calm)], check=True)
    assert post_qa.flash_report(calm, 24.0)["issues"] == []
    full = post_qa.run(strobe, fps=24.0, beats=None, fix=False)
    assert "flashes" in full and any("hard flashes" in i for i in full["issues"]) and full["ok"] is False
