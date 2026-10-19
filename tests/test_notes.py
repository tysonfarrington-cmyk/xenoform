"""Director's notes: interpreter, cache, critic, beat lock."""

import json
from pathlib import Path

import numpy as np
import pytest

from xenoform.analyze import read_features
from xenoform.beatlock import anchors_at_fps, detect, render
from xenoform.director import register_by_id
from xenoform.llm import release_llm
from xenoform.notes import (
    DEFAULT_SEED,
    SYSTEM_PROMPT,
    PatchError,
    apply_patch,
    apply_to_notebook,
    card_hash,
    classify,
    critic_notes,
    ground,
    harding_flash_rate,
    human_diff,
    identity,
    interpret_note,
    new_notebook,
    retime_for_scene,
    revert_notebook,
    rules_interpret,
    segment_key,
    stamp_retime,
    validate_patch,
    warm_cache,
)
from xenoform.storyboard import DEMO_BRIEF, plan_with_hook


def _board():
    features = read_features(Path("examples/demo_features.json"))
    scenes, _source = plan_with_hook(features, register_by_id("pynchon"), DEMO_BRIEF)
    return features, scenes


def test_three_notes_and_schema_prompt():
    features, scenes = _board()
    assert "dive-splash" in SYSTEM_PROMPT
    assert "bolt-strike hold" in SYSTEM_PROMPT
    assert "beat_grid" in ground("bolt should strike on the beat", scenes, features)

    splash = interpret_note("the ending plops, make it a big splash", scenes, features)
    last = scene_id_of(scenes[-1])
    assert splash["source"] == "rules"
    assert splash["patch"]["target_scenes"] == [last]
    assert splash["patch"]["transition_type"] == "dive-splash"
    assert splash["patch"]["rerender"] == [last]
    assert any(row["field"] == "edit" and row["new"] == "dive-splash" for row in splash["diff"])
    assert any(row["field"] == "action" and "big splash" in str(row["new"]) for row in splash["diff"])
    assert "rocket" in str(next(row["new"] for row in splash["diff"] if row["field"] == "action"))

    dark = interpret_note("scene 3 too dark", scenes, features)
    assert dark["patch"]["target_scenes"] == ["s2"]
    assert dark["patch"]["guide_strengths"]["exposure"] == 1.35
    assert any(row["scene"] == "s2" and row["field"] == "mood" and row["new"] == "dawn" for row in dark["diff"])

    bolt = interpret_note("bolt should strike on the beat", scenes, features)
    assert bolt["patch"]["speed"] == "hold"
    assert bolt["patch"]["transition_type"] == "bolt-strike hold"
    assert bolt["patch"]["retime"]["mode"] == "snap-peak"
    assert any(row["field"] == "edit" and row["new"] == "bolt-strike" for row in bolt["diff"])
    struck = apply_patch(scenes, bolt["patch"], features)
    target = next(scene for scene in struck if f"s{scene['index']}" in bolt["patch"]["rerender"])
    assert target["retime"]["anchors_s"]
    assert target["retime"]["speed"] == "hold"


def scene_id_of(scene):
    return f"s{scene['index']}"


def test_mocked_llm_patch_and_fallback():
    features, scenes = _board()
    last = scene_id_of(scenes[-1])

    def good(_system, _user):
        return json.dumps(
            {
                "target_scenes": [last],
                "changes": [
                    {
                        "scene": last,
                        "field": "mood",
                        "old": scenes[-1]["mood"],
                        "new": "storm",
                    }
                ],
                "transition_type": None,
                "speed": None,
                "retime": None,
                "guide_strengths": None,
                "recipe": None,
                "rerender": [last],
                "rationale": "The ending wants weather.",
            }
        )

    parsed = interpret_note("make the ending stormy", scenes, features, llm=good)
    assert parsed["source"] == "llm"
    assert parsed["model"] == "mock"
    assert any(row["field"] == "mood" and row["new"] == "storm" for row in parsed["diff"])
    assert "storm" in parsed["text"]

    def junk(_system, _user):
        return "sure, I would brighten scene three"

    fallen = interpret_note("the ending plops, make it a big splash", scenes, features, llm=junk)
    assert fallen["source"] == "rules-fallback"
    assert fallen["patch"]["transition_type"] == "dive-splash"

    def bad_recipe(_system, _user):
        return json.dumps(
            {
                "target_scenes": [last],
                "changes": [],
                "transition_type": "wiggle",
                "rerender": [last],
                "rationale": "no such recipe",
            }
        )

    rejected = interpret_note("the ending plops, make it a big splash", scenes, features, llm=bad_recipe)
    assert rejected["source"] == "rules-fallback"
    with pytest.raises(PatchError):
        validate_patch(json.loads(bad_recipe("", "")), scenes)


def test_cache_invalidation_and_retime_carry():
    features, scenes = _board()
    cache = warm_cache(scenes, "/media/demo")
    same = classify(scenes, scenes, cache, DEFAULT_SEED, "checkpoint", "512x288")
    assert same["misses"] == []
    assert len(same["hits"]) == len(scenes)

    dark = rules_interpret("scene 3 too dark", scenes, features)
    after = apply_patch(scenes, dark, features)
    plan = classify(scenes, after, cache, DEFAULT_SEED, "checkpoint", "512x288")
    assert plan["misses"] == ["s2"]
    assert "s0" in plan["hits"]
    assert segment_key(after[2], DEFAULT_SEED, "checkpoint", "512x288") != cache["s2"]["key"]
    assert card_hash(after[2]) != card_hash(scenes[2])

    final_model, final_res = identity("final")
    final = classify(scenes, scenes, cache, DEFAULT_SEED, final_model, final_res)
    assert final["hits"] == []
    assert len(final["misses"]) == len(scenes)

    bolt = rules_interpret("bolt should strike on the beat", scenes, features)
    stamped_scenes = apply_patch(scenes, bolt, features)
    stamped = stamp_retime(features, stamped_scenes)
    touched = [frame for frame in stamped["frames"] if frame.get("retime")]
    assert touched
    anchors = touched[0]["retime"]["anchors_s"]
    draft = anchors_at_fps(anchors, 12)
    final_anchors = anchors_at_fps(anchors, 24)
    assert final_anchors[0][0] == pytest.approx(draft[0][0] * 2)
    assert final_anchors[1][1] == pytest.approx(draft[1][1] * 2)
    built = retime_for_scene(stamped_scenes[0], {"fps": 12, "tempo": 120, "beats": []})
    assert built["anchors_s"][0] == [0.0, 0.0]


def test_apply_rerenders_only_the_miss_and_revert(monkeypatch, tmp_path):
    features, scenes = _board()
    unloaded = []
    monkeypatch.setattr("xenoform.llm.release_llm", lambda: unloaded.append("unload") or True)
    book = new_notebook(scenes, "/media/demo")
    patch = rules_interpret("the ending plops, make it a big splash", scenes, features)
    calls = []

    def render_one(scene, seed, resolution, out_dir):
        calls.append((scene["index"], scene["edit"], seed, resolution))
        return str(out_dir / f"s{scene['index']}.json")

    applied = apply_to_notebook(
        book,
        "the ending plops, make it a big splash",
        scenes,
        patch,
        features,
        render_one,
        tmp_path,
        video="/media/demo",
    )
    assert unloaded == ["unload"]
    assert calls == [(scenes[-1]["index"], "dive-splash", DEFAULT_SEED, "512x288")]
    assert applied["plan"]["misses"] == [f"s{scenes[-1]['index']}"]
    assert applied["scenes"][-1]["edit"] == "dive-splash"
    assert "big splash" in applied["scenes"][-1]["action"]

    again = []

    def render_again(scene, seed, resolution, out_dir):
        again.append(scene["index"])
        return str(out_dir / f"s{scene['index']}.json")

    quiet = rules_interpret("scene 3 too dark", applied["scenes"], features)
    apply_to_notebook(
        book,
        "scene 3 too dark",
        applied["scenes"],
        quiet,
        features,
        render_again,
        tmp_path,
        video="/media/demo",
    )
    assert again == [2]

    restored = revert_notebook(book, "draft", video="/media/demo")
    assert restored["scenes"][-1]["edit"] != "dive-splash"
    assert human_diff(scenes, restored["scenes"]) == []


def test_critic_and_beatlock_detectors():
    frozen = np.zeros((16, 8, 8, 3), dtype=np.uint8)
    frozen[8] = 255
    events = detect(frozen)
    assert events["peak"] in {7, 8, 9}
    assert 8 in events["cuts"] or 9 in events["cuts"]
    assert 3 in events["frozen"]

    notes = critic_notes(frozen, fps=24)
    assert any("frozen" in item["note"] or "blown" in item["note"] or "dark" in item["note"] for item in notes["notes"])

    white = np.full((8, 8, 8, 3), 250, dtype=np.uint8)
    blown = critic_notes(white, fps=24)
    assert any("blown" in item["note"] for item in blown["notes"])

    strobe = np.zeros((24, 8, 8, 3), dtype=np.uint8)
    strobe[::2] = 255
    assert harding_flash_rate(strobe, 24) > 3
    flashing = critic_notes(strobe, fps=24)
    assert any("flashes" in item["note"] for item in flashing["notes"])

    def vlm():
        return "the liquid looks tired in the middle"

    voiced = critic_notes(None, scenes=[], vlm=vlm)
    assert voiced["qualitative"].startswith("the liquid")
    assert voiced["notes"][0]["reason"] == "Local vision model."

    clip = np.zeros((4, 8, 8, 3), dtype=np.uint8)
    clip[:, :, :4] = 200
    out = render(clip, [("xfadez", 0, 1, 2, 3, 3, 0.5, 0.5, 0.4)])
    assert out.shape == (3, 8, 8, 3)
    assert out.dtype == np.uint8


def test_release_llm_unloads_and_swallows(monkeypatch):
    seen = {}

    def capture(url, payload, timeout):
        seen["url"] = url
        seen["payload"] = payload
        return {"ok": True}

    monkeypatch.delenv("XENO_VLM_MODEL", raising=False)
    monkeypatch.setattr("xenoform.llm._post", capture)
    assert release_llm("qwen2.5:7b-instruct") is True
    assert seen["url"].endswith("/api/generate")
    assert seen["payload"]["keep_alive"] == 0
    assert seen["payload"]["model"] == "qwen2.5:7b-instruct"

    monkeypatch.setattr("xenoform.llm._post", lambda *args, **kwargs: None)
    assert release_llm() is False


def test_notes_api_confirm_and_cache(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from xenoform import ui as ui_mod
    from xenoform.ui import create_app

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    ui_mod._NOTES.clear()
    unloaded = []
    monkeypatch.setattr("xenoform.llm.release_llm", lambda: unloaded.append(1) or True)
    client = TestClient(create_app())
    demo = client.get("/api/demo").json()
    interpreted = client.post(
        "/api/notes/interpret",
        json={"audio_id": "demo", "note": "the ending plops, make it a big splash", "scenes": demo["scenes"], "llm": False},
    )
    assert interpreted.status_code == 200
    body = interpreted.json()
    assert body["patch"]["transition_type"] == "dive-splash"
    assert body["misses"] == [f"s{demo['scenes'][-1]['index']}"]
    assert len(body["hits"]) == len(demo["scenes"]) - 1
    assert "→" in body["text"] or "->" in body["text"]
    applied = client.post(
        "/api/notes/apply",
        json={
            "audio_id": "demo",
            "note": "the ending plops, make it a big splash",
            "patch": body["patch"],
            "scenes": demo["scenes"],
            "quality": "draft",
        },
    )
    assert applied.status_code == 200
    cut = applied.json()
    assert unloaded
    assert cut["misses"] == body["misses"]
    assert cut["scenes"][-1]["edit"] == "dive-splash"
    assert len(cut["versions"]) >= 2
    listed = client.get("/api/notes/versions", params={"audio_id": "demo"})
    assert listed.status_code == 200
    assert listed.json()["current"] == cut["current"]
    reverted = client.post("/api/notes/revert", json={"audio_id": "demo", "version_id": "draft"})
    assert reverted.status_code == 200
    assert reverted.json()["scenes"][-1]["edit"] != "dive-splash"
    soft = [dict(scene) for scene in demo["scenes"]]
    soft[-1] = dict(soft[-1], edit="dissolve")
    critic = client.post(
        "/api/notes/critic",
        json={"audio_id": "demo", "scenes": soft, "sample": False},
    )
    assert critic.status_code == 200
    texts = [item["note"] for item in critic.json()["notes"]]
    assert any("splash" in text for text in texts)
