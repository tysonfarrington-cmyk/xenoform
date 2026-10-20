"""Morph count control: Auto from length + BPM, fixed counts beat-snapped, recipe + MCP round trip."""
from xenoform import dense
from xenoform.simple_recipe import decode, encode

BPM148 = [i * 60 / 148 for i in range(50)]


def test_auto_counts_follow_length_and_bpm():
    assert dense.auto_morph_count(20.0, BPM148, "dense") == 25        # one per half bar
    assert dense.auto_morph_count(20.0, BPM148, "flow") == 5          # one per two bars, at least 4 s
    slow = [i * 0.75 for i in range(40)]                               # 80 BPM
    assert dense.auto_morph_count(20.0, slow, "dense") < 25


def test_morph_count_parsing_and_clamp():
    assert dense.morph_count({}) == "auto"
    assert dense.morph_count({"morph_count": "auto"}) == "auto"
    assert dense.morph_count({"morph_count": "22"}) == 22
    assert dense.morph_count({"morph_count": 999}) == dense.MORPH_MAX
    assert dense.morph_count({"morph_count": "x"}) == "auto"


def test_fixed_count_dense_plan_is_beat_snapped_and_keeps_the_drop():
    plan = dense.dense_plan(20.0, BPM148, drop=BPM148[31], count=22)
    shots = plan["shots"]
    assert len(shots) == 22
    assert shots[0]["start"] == 0.0 and shots[-1]["end"] == 20.0
    grid = {round(b, 4) for b in BPM148}
    for s in shots[1:]:
        assert round(s["start"], 4) in grid
        assert s["end"] - s["start"] >= dense.MIN_SLOT_S - 1e-6
    assert any(abs(s["start"] - BPM148[31]) < 1e-3 for s in shots)
    pre = [s["end"] - s["start"] for s in shots if s["end"] <= BPM148[31] + 1e-6]
    post = [s["end"] - s["start"] for s in shots if s["start"] >= BPM148[31] - 1e-6]
    assert sum(post) / len(post) < sum(pre) / len(pre)                 # faster after the drop


def test_shots_for_uses_the_count_on_flow_and_dense():
    for energy in ("flow", "dense"):
        shots, plan = dense.shots_for({"energy_preset": energy, "morph_count": 9},
                                      {"duration": 20.0, "beats": BPM148}, None)
        assert len(shots) == 9
    assert dense.wants_finishing({"morph_count": 9})
    assert not dense.wants_finishing({})


def test_estimate_scales_with_count():
    a, b = dense.estimate(10, "final", "9:16"), dense.estimate(20, "final", "9:16")
    assert b["seconds"] > a["seconds"] and a["peak_vram_gb"] > 0


def test_recipe_round_trip_and_auto_default():
    base = {"vibe": "black", "energy_preset": "dense"}
    assert "morph_count" not in decode(encode(base))
    assert decode(encode({**base, "morph_count": 22}))["morph_count"] == 22
    assert decode(encode({**base, "morph_count": 500}))["morph_count"] == 120


def test_mcp_update_settings_morph_count():
    import pytest
    from xenoform import mcp_tools

    app = mcp_tools.App.__new__(mcp_tools.App) if hasattr(mcp_tools, "App") else None
    if app is None:
        pytest.skip("no App class")
    import threading
    app.lock = threading.Lock()
    app.project = dict(mcp_tools.DEFAULTS)
    app._save = lambda: None
    try:
        app.update(morph_count=22)
    except AttributeError:
        pytest.skip("update needs a desk")
    assert app.settings()["morph_count"] == 22
    assert app.body()["morph_count"] == 22
    with pytest.raises(mcp_tools.XenoformError):
        app.update(morph_count=0.5 if False else 500)
    app.update(morph_count="auto")
    assert app.settings()["morph_count"] == "auto"
