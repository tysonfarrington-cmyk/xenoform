import json
from pathlib import Path

import numpy as np
import pytest

from xenoform import transitions_fx as T
from xenoform.scene_edit import snap_segments

ROOT = Path(__file__).resolve().parents[1]


def _clips(n=10, h=64, w=36):
    a = [np.full((h, w, 3), 30, np.uint8) for _ in range(n)]
    b = [np.full((h, w, 3), 210, np.uint8) for _ in range(n)]
    return a, b


def test_catalogue_has_scene_morph_and_fallback():
    ids = [t["id"] for t in T.public_list()]
    assert ids[0] == "scene-morph" and "flow-morph" in ids
    assert len(ids) >= 10
    for t in T.public_list():
        assert t["label"] and t["note"] and t["beats"] >= 1


@pytest.mark.parametrize("kind", list(T.TRANSITIONS))
def test_every_transition_keeps_length_shape_and_lands_on_b(kind):
    a, b = _clips()
    out = T.apply(kind, a, b, 0.7)
    assert len(out) == len(a)
    assert all(f.shape == a[0].shape and f.dtype == np.uint8 for f in out)
    assert abs(float(out[-1].mean()) - 210) < 25  # ends on (or very near) clip B


def test_unknown_kind_and_bad_lengths_raise():
    a, b = _clips()
    with pytest.raises(ValueError):
        T.apply("shimmer", a, b)
    with pytest.raises(ValueError):
        T.apply("luma-wipe", a, b[:-1])


def test_scene_morph_uses_rendered_frames_when_given():
    a, b = _clips(8)
    morph = [np.full_like(a[0], v) for v in range(0, 250, 10)]
    out = T.apply("scene-morph", a, b, morph_frames=morph)
    assert len(out) == 8 and out[0].mean() == 0 and out[-1].mean() == 240


def test_splice_scene_morph_length():
    a, b = _clips(10)
    morph = [np.full_like(a[0], 120)] * 12
    assert len(T.splice_scene_morph(a, morph, b, blend=3)) == 10 + 12 + 10 - 6


def test_beat_snap():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    assert T.snap_to_beats([0.9, 2.2], beats) == [1.0, 2.0]
    assert T.snap_to_beats([1.1], beats, every=4) == [1.1]  # too far from a bar line, left alone
    assert T.snap_to_beats([1.9], beats, every=4) == [2.0]
    segs = snap_segments([{"dur": 0.9}, {"dur": 1.3}, {"dur": 0.8}], beats)
    assert [s["dur"] for s in segs] == [1.0, 1.0, 1.0]


def test_recommendations_are_valid_and_scene_morph_is_a_default():
    kinds = set(T.TRANSITIONS)
    for vibe, table in T.RECOMMENDED.items():
        assert set(table.values()) <= kinds, vibe
        assert table["silence"] == "black-hold"
    assert T.recommend("liquid-gold", "drop") == "scene-morph"
    assert T.recommend("unknown-vibe", "nope") in kinds


def test_config_matches_catalogue():
    cfg = json.loads((ROOT / "configs" / "transitions.json").read_text(encoding="utf-8"))
    assert set(cfg["types"]) == set(T.TRANSITIONS)
    assert cfg["beat_snap"]["every"] in (1, 2, 4)
    for vibe, table in cfg["recommended"].items():
        assert set(table.values()) <= set(T.TRANSITIONS)


def test_scene_morph_graph_is_native_portrait():
    g = T.scene_morph_graph("a.png", "b.png", seconds=2.0)
    assert g["100"]["inputs"]["image"] == "a.png" and g["101"]["inputs"]["image"] == "b.png"
    assert (g["7"]["inputs"]["width"], g["7"]["inputs"]["height"]) == (224, 384)
    assert g["7"]["inputs"]["length"] == 49
    assert (g["42"]["inputs"]["width"], g["42"]["inputs"]["height"]) == (1080, 1920)
    assert "melts and flows" in g["4"]["inputs"]["text"]


def test_bass_pulse_keeps_shape():
    a, _ = _clips(1)
    assert T.bass_pulse(a[0], 1.0, 1.0).shape == a[0].shape


def test_docs_list_every_type():
    doc = (ROOT / "docs" / "transitions.md").read_text(encoding="utf-8")
    for k in T.TRANSITIONS:
        assert f"`{k}`" in doc


def test_ui_segments_get_no_fx_and_pulse_moments_are_sparse():
    import json
    from pathlib import Path
    from xenoform import scene_edit as SE
    spec = {"_fxk": [1.0, 0.0, 1.0], "pulse_moments": [[0.0, 0.05]]}
    assert SE.fx_scale(spec, 0, 30) == 1.0
    assert SE.fx_scale(spec, 1, 30) == 0.0          # UI capture frame: clean
    assert SE.fx_scale(spec, 2, 30) == 0.0          # outside the key moment
    cfg = json.loads(Path("configs/transitions.json").read_text())
    assert cfg["post_effects"]["bass-pulse"]["depth"] <= 0.01
    assert cfg["intensity"]["ceiling"] <= 0.6


def test_v5_classic_is_expert_only_and_cap_two_per_type():
    kinds = ["luma-wipe", "match-cut", "match-cut", "match-cut", "stutter-cut", "cut", "scene-morph", "scene-morph", "scene-morph"]
    out, msgs = T.guard(kinds)
    assert not set(out) & set(T.CLASSIC)
    from collections import Counter
    c = Counter(k for k in out if k not in T.EXEMPT_FROM_CAP)
    assert max(c.values()) <= 2 and msgs
    assert out[-3:] == ["scene-morph"] * 3
    keep, _ = T.guard(kinds, expert=True)
    assert keep[0] == "luma-wipe"
    assert {t["id"]: t["tier"] for t in T.public_list()}["luma-wipe"] == "classic"


def test_v5_plan_mostly_clean_cuts_and_favours_match_and_flow():
    bds = [{"section": k % 4 == 0} for k in range(40)]
    picks = T.plan(bds, seed=3)
    assert picks.count("cut") / len(picks) >= 0.6
    from collections import Counter
    c = Counter(p for p in picks if p != "cut")
    assert c and max(c.values()) <= 2
    assert T.AUTO_WEIGHTS["match-cut"] >= max(T.AUTO_WEIGHTS.values()) and T.AUTO_WEIGHTS["flow-carry"] >= max(T.AUTO_WEIGHTS.values())
    for vibe in T.RECOMMENDED:
        assert T.recommend(vibe, "beat") not in T.CLASSIC


def test_v5_premium_on_real_texture_ends_on_b():
    rng = np.random.default_rng(1)
    a = [np.clip(rng.normal(60, 40, (96, 54, 3)), 0, 255).astype(np.uint8) for _ in range(10)]
    b = [np.clip(rng.normal(180, 30, (96, 54, 3)), 0, 255).astype(np.uint8) for _ in range(10)]
    for k in T.PREMIUM:
        out = T.apply(k, a, b, 0.6)
        assert abs(float(out[-1].astype(float).mean()) - float(b[-1].mean())) < 20, k
        assert T.depth_proxy(a[0]).shape == (96, 54)


def test_v5_scene_edit_and_guardrails_apply_the_variety_rule():
    from xenoform import guardrails as G
    body = {"scene_transitions": ["luma-wipe"] + ["echo-trail"] * 4}
    clean, rep = G.apply(body)
    ks = clean["scene_transitions"]
    assert "luma-wipe" not in ks and ks.count("echo-trail") <= 2
    assert any("transition_variety" in m for m in rep["messages"])
