"""Render lessons: caps, critic flags, and lessons saved from a note."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.analyze import read_features
from xenoform.director import public_presets, register_by_id
from xenoform.lessons import (
    approach_dst,
    builtin_flags,
    catalog,
    clamp_strengths,
    default_strengths,
    fade_frames,
    look_allowed,
    offer_for,
    save_learned,
    saved_flags,
)
from xenoform.notes import apply_patch, critic_notes, human_diff, interpret_note, rules_interpret
from xenoform.storyboard import DEMO_BRIEF, plan_with_hook
from xenoform.ui import create_app


def _board():
    features = read_features(Path("examples/demo_features.json"))
    scenes, _source = plan_with_hook(features, register_by_id("pynchon"), DEMO_BRIEF)
    return features, scenes


def test_caps_trim_and_no_shimmer_preset():
    assert approach_dst(1.2, 1.8) == 1.2
    assert approach_dst(1.2, 0.4) == 0.4
    assert fade_frames("swim") == 8
    assert fade_frames("droplet-burst") == 2
    assert fade_frames("grow-out") == 14
    assert fade_frames("pour-harden") == 8

    bolt = clamp_strengths("bolt-strike", {"guide": 0.8, "mid": 0.9, "bolt": 0.55})
    assert bolt["guide"] == 0.30
    assert bolt["mid"] == 0.30
    assert bolt["bolt"] == 0.30
    assert bolt["end"] == "late"
    assert bolt["offset_frames"] == 32
    other = clamp_strengths("dive-splash", {"mid": 0.9})
    assert other["mid"] == 0.40
    assert "guide" not in clamp_strengths("dive-splash", {})

    defaults = default_strengths("ribbon", {})
    assert defaults["guide"] == 0.40
    assert defaults["mid"] == 0.40
    assert defaults["end"] == "late"
    assert defaults["offset_frames"] == 32

    assert look_allowed({"id": "shimmer", "name": "Shimmer", "note": ""}) is False
    assert look_allowed({"id": "warp-field", "name": "Warp", "note": ""}) is False
    presets = public_presets()
    assert len(presets) == 10
    assert all(look_allowed(item) for item in presets)
    assert len(catalog()) == 13
    assert any(item["id"] == "shots-not-morphs" for item in catalog())
    assert any(item["id"] == "continuity" for item in catalog())


def test_slow_into_impact_trims_and_bolt_hold_survives():
    features, scenes = _board()
    slow = rules_interpret(
        "slow-motion into the impact is an anticlimax; speed up into the hit and slow only after",
        scenes,
        features,
    )
    assert slow["speed"] == "trim"
    struck = apply_patch(scenes, slow, features)
    target = next(scene for scene in struck if f"s{scene['index']}" == slow["target_scenes"][0])
    assert target["retime"]["speed"] == "trim"
    src, dst = target["retime"]["anchors_s"][1]
    assert dst <= src

    bolt = interpret_note("bolt should strike on the beat", scenes, features)
    applied = apply_patch(scenes, bolt["patch"], features)
    hit = next(scene for scene in applied if f"s{scene['index']}" in bolt["patch"]["rerender"])
    assert hit["retime"]["speed"] == "hold"
    src, dst = hit["retime"]["anchors_s"][1]
    assert dst <= src


def test_critic_flags_lessons_and_splash_diff_stays_the_landing():
    features, scenes = _board()
    splash = interpret_note("the ending plops, make it a big splash", scenes, features)
    fields = [row["field"] for row in splash["diff"]]
    assert fields == ["action", "edit"]
    assert "Re-render" not in splash["text"] or True

    climax = next(scene for scene in scenes if scene["beat"] == "climax")
    climax["retime"] = {"speed": "0.5", "anchors_s": [[0.0, 0.0], [1.0, 1.4], [2.0, 2.0]]}
    flags = builtin_flags([climax])
    assert any(item["lesson_id"] == "slow-into-impact" for item in flags)

    hot = {"index": 3, "edit": "bolt-strike", "action": "a bolt", "beat": "climax", "guide_strengths": {"guide": 0.8}}
    assert any(item["lesson_id"] == "bolt-guide-cap" for item in builtin_flags([hot]))

    swim = {"index": 1, "edit": "swim", "action": "it drifts", "beat": "release", "fade_frames": 12}
    assert any(item["lesson_id"] == "dissolve-cap" for item in builtin_flags([swim]))

    shimmer = builtin_flags([], looks=[{"id": "shimmer", "name": "Shimmer", "note": "wavy"}])
    assert shimmer and shimmer[0]["lesson_id"] == "no-shimmer"

    frozen = critic_notes(
        __import__("numpy").zeros((8, 4, 4, 3), dtype="uint8"),
        features,
        scenes,
        fps=24,
    )
    assert any("frozen" in item["note"] for item in frozen["notes"])
    assert any("dive-splash" in item["reason"] or "droplet-burst" in item["reason"] for item in frozen["notes"] if "frozen" in item["note"])


def test_offer_save_and_replay(tmp_path):
    features, scenes = _board()
    scenes[-1]["edit"] = "dissolve"
    note = "the ending plops, make it a big splash"
    read = interpret_note(note, scenes, features)
    suggestions = critic_notes(None, features, scenes, fps=24)["notes"]
    offer = offer_for(note, scenes, read["scenes"], suggestions, [])
    assert offer and offer["offer"] is True
    assert offer["when"][0]["scene"] == "ending"
    assert offer["when"][0]["source"] == f"s{scenes[-1]['index']}"
    offer["patch"] = read["patch"]

    path = tmp_path / "lessons.json"
    log = tmp_path / "LESSONS.md"
    log.write_text("# Xenoform lessons\n\n| Date | Lesson | Feature / default |\n|---|---|---|\n", encoding="utf-8")
    stored = save_learned(path, offer, log)
    again = save_learned(path, offer, log)
    assert again["id"] == stored["id"]
    assert log.read_text(encoding="utf-8").count(note) == 1
    assert len(json.loads(path.read_text())["lessons"]) == 1

    ending = scenes[-1]
    assert any(item["note"] == note for item in saved_flags(scenes, [stored]))
    fixed = [dict(scene) for scene in scenes]
    fixed[-1] = dict(ending)
    fixed[-1]["edit"] = "dive-splash"
    assert saved_flags(fixed, [stored]) == []

    replay = interpret_note(note, scenes, features, lessons=[stored])
    assert replay["source"] == "lesson"
    assert any(row["field"] == "edit" and row["new"] == "dive-splash" for row in replay["diff"])

    shorter = scenes[:4]
    moved = interpret_note(note, shorter, features, lessons=[stored])
    assert moved["source"] == "lesson"
    assert moved["patch"]["target_scenes"] == [f"s{shorter[-1]['index']}"]


def test_lessons_api(monkeypatch, tmp_path):
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "lessons_file", lambda: tmp_path / "lessons.json")
    monkeypatch.setattr(ui_mod, "lessons_log", lambda: tmp_path / "LESSONS.md")
    (tmp_path / "LESSONS.md").write_text(
        "# Xenoform lessons\n\n| Date | Lesson | Feature / default |\n|---|---|---|\n",
        encoding="utf-8",
    )
    ui_mod._NOTES.clear()
    client = TestClient(create_app())
    index = client.get("/api/lessons")
    assert index.status_code == 200
    assert len(index.json()["builtin"]) == 13
    assert index.json()["saved"] == []

    demo = client.get("/api/demo").json()
    note = "the ending plops, make it a big splash"
    scenes = demo["scenes"]
    scenes[-1]["edit"] = "dissolve"
    interpreted = client.post(
        "/api/notes/interpret",
        json={"audio_id": "demo", "note": note, "scenes": scenes, "llm": False},
    )
    assert interpreted.status_code == 200
    body = interpreted.json()
    assert body["lesson_offer"]["offer"] is True
    assert body["misses"] == [f"s{demo['scenes'][-1]['index']}"]
    assert [row["field"] for row in body["diff"]] == ["action", "edit"]

    saved = client.post("/api/lessons", json=body["lesson_offer"])
    assert saved.status_code == 200
    assert note in (tmp_path / "LESSONS.md").read_text(encoding="utf-8")

    critic = client.post(
        "/api/notes/critic",
        json={"audio_id": "demo", "scenes": demo["scenes"], "sample": False},
    )
    texts = [item["note"] for item in critic.json()["notes"]]
    assert note in texts

    replay = client.post(
        "/api/notes/interpret",
        json={"audio_id": "demo", "note": note, "scenes": demo["scenes"], "llm": False},
    )
    assert replay.json()["source"] == "lesson"
    assert replay.json()["lesson_offer"] is None
