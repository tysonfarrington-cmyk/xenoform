"""Review & fix: rule audit, zero-GPU apply, frame checks."""

import numpy as np

from xenoform.review import apply_findings, audit, contact_sheet


def _board():
    return [
        {
            "index": 0,
            "start": 0.0,
            "end": 4.0,
            "edit": "dissolve",
            "move": "hold",
            "shot": "wide",
            "form": "sphere",
            "action": "it",
            "beat": "setup",
            "fade_frames": 20,
        },
        {
            "index": 1,
            "start": 4.0,
            "end": 8.0,
            "edit": "hard cut",
            "move": "hold",
            "form": "sphere",
            "action": "again",
            "beat": "rising",
            "guide_strengths": {"bolt": 0.9, "guide": 0.9},
        },
        {
            "index": 2,
            "start": 8.0,
            "end": 12.0,
            "edit": "pour-harden",
            "move": "hold",
            "form": "bulb",
            "action": "waits",
            "beat": "climax",
            "retime": {"speed": "slow", "anchors_s": [[0.0, 0.0], [1.0, 2.2]]},
        },
    ]


def _features():
    return {"beats": [], "duration": 12.0, "fps": 24}


def test_audit_names_board_fixes_and_rerenders():
    report = audit(_board(), _features(), flash="hard", register_forms=["sphere", "rocket", "bulb"])
    checks = {row["check"] for row in report["findings"]}
    assert "ghosting-dissolve" in checks
    assert "stacked-accents" in checks
    assert "slow-into-impact" in checks
    assert "harding-flash" in checks
    assert "hard-cut-in-morph" in checks
    assert "missing-hook" in checks
    assert "loop" in checks
    assert "still-as-motion" in checks
    for absent in ("one-subject", "repeated-layout", "unmotivated-cut", "follow-through", "decorative", "unmotivated-camera"):
        assert absent not in checks
    kinds = {row["check"]: row["kind"] for row in report["findings"]}
    assert kinds["ghosting-dissolve"] == "cpu"
    assert kinds["hard-cut-in-morph"] == "rerender"
    assert report["rerender"]
    for row in report["findings"]:
        assert row["plain"]
        assert "before" in row and "after" in row


def test_apply_clears_the_same_checks():
    board = _board()
    first = audit(board, _features(), flash="hard", register_forms=["sphere", "rocket", "bulb"])
    fixed = apply_findings(board, first["findings"], sliders={"material": 0.5}, flash="hard")
    assert fixed["flash"] == "soft"
    again = audit(
        fixed["scenes"],
        _features(),
        flash=fixed["flash"],
        sliders=fixed["sliders"],
        register_forms=["sphere", "rocket", "bulb"],
    )
    checks = {row["check"] for row in again["findings"]}
    for gone in (
        "ghosting-dissolve",
        "stacked-accents",
        "slow-into-impact",
        "harding-flash",
        "hard-cut-in-morph",
        "missing-hook",
        "loop",
        "still-as-motion",
    ):
        assert gone not in checks
    assert fixed["scenes"][0]["fade_frames"] == 8
    assert fixed["scenes"][0]["edit"] == "droplet-burst"
    assert fixed["scenes"][1]["edit"] == "ribbon"
    assert fixed["scenes"][2]["retime"]["speed"] == "trim"


def test_grade_and_frozen_frames_are_classified():
    frames = np.full((8, 12, 12, 3), 230, dtype=np.uint8)
    scenes = [
        {
            "index": 0,
            "start": 0.0,
            "end": 4.0,
            "edit": "ribbon",
            "move": "push in",
            "form": "sphere",
            "action": "the body turns in the light",
            "beat": "climax",
        }
    ]
    report = audit(scenes, _features(), frames=frames, fps=4, sliders={"material": 0.8}, flash="normal")
    checks = {row["check"]: row["kind"] for row in report["findings"]}
    assert checks["exposure-high"] == "cpu"
    assert checks["frozen-frames"] == "rerender"


def test_shots_review_flags_morphs_stillness_and_a_missing_spine():
    board = []
    edits = ["dissolve", "ribbon", "pour-harden", "grow-out"]
    beats = ["setup", "rising", "climax", "release"]
    forms = ["sphere", "rocket", "bulb", "tower"]
    for index, edit in enumerate(edits):
        board.append(
            {
                "index": index,
                "start": index * 4.0,
                "end": (index + 1) * 4.0,
                "edit": edit,
                "move": "hold" if index == 1 else "follow",
                "verb": "waits" if index == 1 else "climbs",
                "shot": "wide",
                "form": forms[index],
                "action": "the figure crosses the room",
                "beat": beats[index],
            }
        )
    report = audit(board, {"beats": [], "duration": 16.0, "fps": 24})
    checks = {row["check"] for row in report["findings"]}
    assert "low-motion" in checks
    assert "morph-heavy" in checks
    assert "missing-story" in checks
    fixed = apply_findings(board, report["findings"])
    morphs = [scene for scene in fixed["scenes"] if scene["edit"] not in {"hard cut", "snap"}]
    assert len(morphs) <= 2
    assert fixed["scenes"][2]["edit"] == "pour-harden"
    assert fixed["scenes"][1]["move"] != "hold"
    assert fixed["scenes"][1]["verb"] != "waits"
    assert all(scene.get("protagonist") and scene.get("goal") and scene.get("payoff") for scene in fixed["scenes"])
    assert fixed["scenes"][0]["conditioning"] == "first-frame"
    assert fixed["scenes"][0]["signature"] is False


def test_contact_sheet_is_a_png():
    blob = contact_sheet(_board(), "violet")
    assert blob[:8] == b"\x89PNG\r\n\x1a\n"
