"""Morphs land on downbeats. Breakdowns stay sparse. The hit is one frame."""

import numpy as np

from xenoform.assemble import hit_frames
from xenoform.eligibility import audit_default_workflows
from xenoform.morph.lock import downbeats_from, land_time
from xenoform.morph.plan import plan_board


def _beats():
    return [index * 0.5 for index in range(8)]


def _scenes(starts, label):
    rows = []
    for index, start in enumerate(starts):
        rows.append(
            {
                "action": "the fox waits" if index == 0 else "the fox becomes a horse",
                "form": "fox" if index == 0 else "horse",
                "protagonist": "the fox",
                "start": start,
                "signature": True,
                "section": label,
            }
        )
    return rows


def test_downbeats_are_every_fourth_beat_and_drops_use_them():
    assert downbeats_from(_beats()) == [0.0, 2.0]
    at, kind = land_time(1.9, _beats(), section="drop", drops=[{"start": 1.8, "end": 4.0}])
    assert kind == "drop"
    assert at == 2.0
    calm, calm_kind = land_time(0.6, _beats(), section="calm")
    assert calm_kind == "downbeat"
    assert calm == 0.0


def test_breakdowns_keep_one_morph_and_drops_chain():
    calm = _scenes([0, 1, 2, 3], "calm")
    sections = [{"label": "calm", "start": 0, "end": 8}]
    board = plan_board(calm, _beats(), "keyframe-blend", lock=True, sections=sections, hit=True)
    assert board["kept"] == 1
    assert board["joins"][0]["pace"] == "sparse"
    assert board["joins"][0]["hit"] is True
    assert board["joins"][0]["downbeat"] in downbeats_from(_beats())

    drop = _scenes([0, 1.9, 2.4, 3.1], "drop")
    hot = [{"label": "drop", "start": 0, "end": 8}]
    chained = plan_board(
        drop,
        _beats(),
        "keyframe-blend",
        brief="A fox waits and becomes a horse",
        lock=True,
        sections=hot,
        drops=[{"start": 1.8, "end": 4}],
        hit=True,
    )
    assert chained["kept"] == 3
    assert {join["pace"] for join in chained["joins"]} == {"chain"}
    assert {join["at"] for join in chained["joins"]} == {2.0}
    assert all(join["hit"] and join["qa"]["pass"] for join in chained["joins"])

    sampled = plan_board(drop, _beats(), "v2v-ramp", lock=True, sections=hot, hit=False)
    assert sampled["kept"] == 2
    assert sampled["dropped"] == 1
    assert all(join["hit"] is False for join in sampled["joins"])
    assert audit_default_workflows() == []


def test_hit_flash_changes_one_frame():
    frames = np.zeros((4, 2, 2, 3), dtype=np.uint8)
    flashed = hit_frames(frames, 1.0, [2.0], amount=1.0)
    assert flashed.shape == frames.shape
    assert int(flashed[2, 0, 0, 0]) == 255
    assert int(flashed[1, 0, 0, 0]) == 0
    assert int(flashed[3, 0, 0, 0]) == 0


def test_hit_control_stays_off_the_simple_desk():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = (root / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    css = (root / "src" / "xenoform" / "ui_static" / "app.css").read_text(encoding="utf-8")
    assert "morph-hit" in script
    assert "Hit flash" in script
    easy = script.split("function renderEasy()", 1)[1].split("function placeKey", 1)[0]
    assert "morph-hit" not in easy
    assert "shimmer" not in css
