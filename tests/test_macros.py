from xenoform.dense import macros, apply_macros
def test_macros_neutral_and_clamped():
    m = macros({"macros": {"intensity": 2, "chaos": "x"}})
    assert m["intensity"] == 1.0 and m["chaos"] == 0.3
    assert macros({})["intensity"] == 0.5
def test_apply_macros_scales_fx():
    s = apply_macros([{"fx_intensity": 0.5}], {"intensity": 0.0, "chaos": 1.0})
    assert s[0]["fx_intensity"] == 0.2 and s[0]["wobble"] == 0.3
    assert apply_macros([{}], {"intensity": 1.0, "chaos": 0.3})[0]["fx_intensity"] == 1.0


def test_macros_stems_and_speed_glow_reach_the_look():
    from xenoform import beatfx
    from xenoform.dense import speed_count
    m = macros({"macros": {"speed": 1.0, "glow": 1.0, "stems": {"kick": 0.2, "pad": 2}}})
    assert m["stems"] == {"kick": 0.2, "pad": 1.0}
    lp = beatfx.LookPass(dance_fx="cool-echo", stem_orbit=False, stem_env={"fps": 24}, macros=m, fps=24)
    lp.start_shot(0, 4, 0.0)
    assert lp.fx.p["echo_decay"] < 0.70 and lp.fx.p["halation"] > 0.5 and lp.gains() == m["stems"]
    assert speed_count(20.0, [i * 0.5 for i in range(40)], "flow", 1.0) >= speed_count(20.0, [i * 0.5 for i in range(40)], "flow", 0.0)
