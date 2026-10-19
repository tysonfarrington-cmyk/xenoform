"""Fresh-eyes critic, treatments, the ledger, and a music export that does not stretch."""

import numpy as np
import pytest

from xenoform.critic import _parse_loudness, delivery_spec, measure, next_fix
from xenoform.ledger import append_round, board_metrics, load_ledger, record_after
from xenoform.review import apply_findings, audit
from xenoform.seeded import unit
from xenoform.storyboard import DEMO_BRIEF, pick_treatment, pitch_treatments, stamp_treatment, style_bible
from xenoform.timing import export_music, music_command, timing_document


def _clock(count, step=0.2):
    return np.arange(count, dtype=np.float64) * step


def _picture(count=8, value=80):
    frames = []
    for index in range(count):
        frame = np.full((48, 64, 3), value, dtype=np.uint8)
        frame[:, :] = np.clip(value + index * 18, 0, 255)
        frame[10:30, 12:40] = (40 + index * 10) % 255
        frames.append(frame)
    return np.stack(frames)


def _spec():
    return {"quality": "turbo", "width": 64, "height": 48, "fps": 12.0, "duration": 1.4}


def _actual():
    return {"width": 64, "height": 48, "fps": 12.0, "duration": 1.4}


def test_loudness_summary_reads_the_true_peak():
    integrated, peak = _parse_loudness(
        "I: -14.0 LUFS\nSummary:\n  Integrated loudness:\n    I:         -14.2 LUFS\n  True peak:\n    Peak:       -1.4 dBFS\n"
    )
    assert integrated == -14.2
    assert peak == -1.4


def test_seed_and_frame_repeat():
    assert unit(2727, 4, salt=7) == unit(2727, 4, salt=7)
    assert unit(2727, 4, salt=7) != unit(2727, 5, salt=7)
    assert 0.0 <= unit(2727, 0) < 1.0


def test_no_picture_asks_for_another_pass():
    report = measure(None, spec=delivery_spec("turbo", duration=4), actual={}, beats=[])
    ids = {row["id"] for row in report["problems"]}
    assert "no-picture" in ids
    assert "story-unclear" in ids
    assert report["verdict"] == "one more pass"
    assert all(row["pass"] for row in report["bar"] if not row["measured"])


def test_sound_off_and_the_measured_bar():
    frames = _picture()
    held = np.stack([frames[0]] * 6)
    times = _clock(6, 0.2)
    dull = measure(held, times, spec=_spec(), actual={"width": 64, "height": 48, "fps": 12, "duration": 1.0}, beats=[])
    assert dull["verdict"] == "one more pass"
    assert any(row["id"] == "still-stretch" for row in dull["problems"])
    assert any(row["id"] == "story-unclear" for row in dull["problems"])
    assert dull["sound_off"]["readable"] is False

    moving = measure(
        frames,
        _clock(len(frames)),
        spec=_spec(),
        actual=_actual(),
        beats=[0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4],
        loudness={"measured": True, "integrated": -14.0, "true_peak": -1.4, "sample_peak": 0.5},
    )
    assert moving["sound_off"]["readable"] is True
    assert "opens" in moving["retelling"]
    assert not any(row["id"] == "story-unclear" for row in moving["problems"])
    loud = measure(
        frames,
        _clock(len(frames)),
        spec=_spec(),
        actual=_actual(),
        beats=[],
        loudness={"measured": True, "integrated": -8.0, "true_peak": -0.2, "sample_peak": 1.0},
    )
    ids = {row["id"] for row in loud["problems"]}
    assert {"loudness", "peak", "clipping"} <= ids
    skipped = next(row for row in loud["bar"] if row["id"] == "cut-beat")
    assert skipped["pass"] is True
    assert "not scored" in skipped["detail"]


def test_frame_one_size_and_a_cut_off_the_beat():
    black = np.zeros((4, 32, 32, 3), dtype=np.uint8)
    report = measure(black, _clock(4), spec={"width": 16, "height": 16, "fps": 24, "duration": 2}, actual={"width": 32, "height": 32, "fps": 12, "duration": 3})
    ids = {row["id"] for row in report["problems"]}
    assert "frame-one" in ids
    assert "size" in ids
    assert "fps" in ids
    assert "duration" in ids
    jump = _picture(6)
    jump[3:] = 20
    late = measure(jump, _clock(6), spec=_spec(), actual=_actual(), beats=[0.0])
    assert any(row["id"] == "cut-beat" and row["t"] > 0 for row in late["problems"])


def test_text_contrast_margins_and_recheck():
    frame = np.random.default_rng(2727).integers(0, 255, size=(100, 200, 3), dtype=np.uint8)
    quiet = np.full((100, 200, 3), 210, dtype=np.uint8)
    quiet[84:92, 20:160] = 10
    frame[82:] = quiet[82:]
    other = frame.copy()
    other[:70] = np.clip(other[:70].astype(np.int16) + 50, 0, 255).astype(np.uint8)
    frames = np.stack([frame, other])
    report = measure(frames, np.array([0.0, 0.5]), spec={"width": 200, "height": 100, "fps": 12, "duration": 0.5}, actual={"width": 200, "height": 100, "fps": 12, "duration": 0.5}, beats=[], prior_ids=["still-stretch", "contrast"])
    contrast = next(row for row in report["bar"] if row["id"] == "contrast")
    margins = next(row for row in report["bar"] if row["id"] == "margins")
    assert contrast["pass"] is True
    assert margins["pass"] is True
    cleared = {row["id"]: row["status"] for row in report["rechecked"]}
    assert cleared["still-stretch"] == "cleared"

    edge = frame.copy()
    edge[90:, 0:8] = 0
    edge[82:90, :] = 210
    edged = measure(np.stack([edge, edge]), np.array([0.0, 0.5]), spec={"width": 200, "height": 100, "fps": 12}, actual={"width": 200, "height": 100, "fps": 12}, beats=[])
    assert any(row["id"] == "margins" for row in edged["problems"])


def test_next_fix_picks_the_board_problem_with_an_op():
    picked = next_fix(
        [
            {"id": "loudness", "rank": 1, "op": {}},
            {"id": "low-motion-s1", "rank": 4, "op": {"op": "motion"}},
            {"id": "missing-story-board", "rank": 3, "op": {"op": "story"}},
        ]
    )
    assert picked["id"] == "missing-story-board"


def test_treatments_name_three_moments_and_leave_the_action():
    pitched = pitch_treatments(DEMO_BRIEF)
    assert 2 <= len(pitched) <= 3
    assert all(len(item["moments"]) == 3 for item in pitched)
    assert pick_treatment(DEMO_BRIEF) == "life"
    assert pick_treatment("a room") == "cut"
    scenes = [
        {"index": 0, "beat": "setup", "action": "the rocket is born, cold and paranoid"},
        {"index": 1, "beat": "climax", "action": "the rocket hits"},
        {"index": 2, "beat": "release", "action": "the rocket falls back to earth, changed"},
    ]
    stamp_treatment(scenes, "life")
    assert scenes[0]["moment"] == "Birth"
    assert scenes[1]["signature_moment"] == "The climb"
    assert scenes[2]["moment"] == "The return"
    assert "born" in scenes[0]["action"]
    bible = style_bible("pynchon", "liquid-metal", moments=["Birth", "The climb", "The return"])
    assert bible["look"] == "Liquid Metal"
    assert len(bible["frames"]) == 3
    assert bible["frames"][0]["swatch"].startswith("#")
    plain = style_bible("pynchon", "action-cut", moments=["Birth", "The climb", "The return"])
    assert plain["look"] == "Action Cut"


def test_ledger_appends_before_and_after(tmp_path):
    metrics = board_metrics([{"edit": "hard cut", "shot": "wide", "move": "pull back", "protagonist": "the rocket"}])
    append_round(tmp_path, verdict="one more pass", before=metrics, problems=[{"id": "still-stretch", "t": 1.2, "plain": "held"}], rechecked=[])
    record_after(tmp_path, {"verdict": "applied", "scenes": 1})
    rounds = load_ledger(tmp_path)
    assert rounds[0]["before"]["protagonist"] == "the rocket"
    assert rounds[0]["after"]["verdict"] == "applied"
    text = (tmp_path / "ledger.md").read_text(encoding="utf-8")
    assert "Review ledger" in text
    assert "one more pass" in text


def test_music_command_does_not_stretch(tmp_path):
    command = music_command(tmp_path / "song.wav", tmp_path / "song.m4a")
    assert "-vn" in command
    assert not any(part == "atempo" or str(part).startswith("atempo") for part in command)
    document = timing_document({"beats": [0.5], "tempo": 120, "duration": 4, "fps": 24}, [{"index": 0, "start": 0, "end": 4, "beat": "setup", "verb": "is born", "moment": "Birth"}])
    assert document["rule"].startswith("The picture locks")
    assert document["actions"][0]["moment"] == "Birth"

    def bent(audio, dest):
        return ["ffmpeg", "-i", str(audio), "atempo=1.2", str(dest)]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("xenoform.timing.music_command", bent)
    with pytest.raises(RuntimeError):
        export_music(tmp_path / "song.wav", tmp_path / "out.m4a")
    monkeypatch.undo()


def test_craft_rules_flag_a_second_subject_and_leave_the_old_board():
    board = [
        {"index": 0, "start": 0, "end": 4, "edit": "hard cut", "shot": "wide", "move": "pull back", "verb": "climbs", "protagonist": "the rocket", "goal": "up", "payoff": "down", "action": "the rocket climbs", "beat": "setup"},
        {"index": 1, "start": 4, "end": 8, "edit": "hard cut", "shot": "macro", "move": "push in", "verb": "climbs", "protagonist": "the bulb", "goal": "up", "payoff": "down", "action": "particles drift", "beat": "rising"},
        {"index": 2, "start": 8, "end": 12, "edit": "hard cut", "shot": "wide", "move": "pull back", "verb": "sits", "protagonist": "the rocket", "goal": "up", "payoff": "down", "action": "the rocket waits", "beat": "climax"},
        {"index": 3, "start": 12, "end": 16, "edit": "hard cut", "shot": "reveal", "move": "hold", "verb": "climbs", "protagonist": "the rocket", "goal": "up", "payoff": "down", "action": "the rocket lands", "beat": "release"},
    ]
    report = audit(board, {"beats": [0, 4, 8, 12], "duration": 16, "fps": 24})
    checks = {row["check"] for row in report["findings"]}
    assert "one-subject" in checks
    assert "repeated-layout" in checks
    assert "decorative" in checks
    assert "follow-through" in checks
    fixed = apply_findings(board, [row for row in report["findings"] if row["check"] == "one-subject"])
    assert all(scene["protagonist"] == "the rocket" for scene in fixed["scenes"])
    assert fixed["scenes"][0]["goal"] == "up"
    stripped = apply_findings(board, [row for row in report["findings"] if row["check"] == "decorative"])
    assert "particle" not in stripped["scenes"][1]["action"]
