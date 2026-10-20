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
