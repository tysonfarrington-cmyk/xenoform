from xenoform.dense import macros, apply_macros
def test_macros_neutral_and_clamped():
    m = macros({"macros": {"intensity": 2, "chaos": "x"}})
    assert m["intensity"] == 1.0 and m["chaos"] == 0.3
    assert macros({})["intensity"] == 0.5
def test_apply_macros_scales_fx():
    s = apply_macros([{"fx_intensity": 0.5}], {"intensity": 0.0, "chaos": 1.0})
    assert s[0]["fx_intensity"] == 0.2 and s[0]["wobble"] == 0.3
    assert apply_macros([{}], {"intensity": 1.0, "chaos": 0.3})[0]["fx_intensity"] == 1.0
