"""Morphs blend two existing shots and do not invent a third subject."""

from fastapi.testclient import TestClient

from xenoform.eligibility import audit_default_workflows, audit_graph
from xenoform.morph import plan_board, plan_join
from xenoform.morph.gate import review
from xenoform.morph.workflow import graph
from xenoform.ui import create_app


def _pair():
    before = {"action": "the fox waits in the lighthouse", "form": "fox", "protagonist": "the fox", "start": 0, "end": 2}
    after = {"action": "the fox crosses the lighthouse stair", "form": "fox", "protagonist": "the fox", "start": 2.0, "end": 4, "signature": True}
    return before, after


def test_the_cheetah_prompt_names_the_horse_and_drops_the_register():
    before = {
        "action": "again changed cheetah follow lands last looks octopus run runs shot song through tower",
        "form": "octopus",
        "protagonist": "the tower",
        "verb": "looks",
        "goal": "song",
        "payoff": "through the tower",
        "start": 0,
    }
    after = {
        "action": "the octopus lands",
        "form": "tower",
        "protagonist": "the song",
        "start": 2.0,
        "signature": True,
    }
    brief = "A cheetah runs along a beach and becomes a horse"
    plan = plan_join(before, after, "v2v-ramp", [2.0], brief=brief)
    assert plan["subject_a"] == "cheetah"
    assert plan["subject_b"] == "horse"
    assert plan["prompt"] == (
        "A photoreal cheetah running side-on along a beach, "
        "its body smoothly reshaping into a horse mid-stride; "
        "same camera, same lighting, continuous run"
    )
    for leaked in ("octopus", "tower", "song", "follow", "lands"):
        assert leaked not in plan["prompt"]
    assert plan["qa"]["pass"]
    missing = dict(plan)
    missing["prompt"] = plan["prompt"].replace("horse", "beast")
    assert review(missing, [2.0])["pass"] is False
    foreign = dict(plan)
    foreign["prompt"] = plan["prompt"] + " octopus"
    checked = review(foreign, [2.0])
    assert checked["pass"] is False
    assert any("neither shot" in reason for reason in checked["reasons"])


def test_restyle_prefers_fp8_ltx23_and_fast_stays_on_095(monkeypatch):
    monkeypatch.setattr("xenoform.hardware.detect_tier", lambda: {"id": "12gb"})
    monkeypatch.setattr(
        "xenoform.models_setup.quantised_file",
        lambda model_id, root=None: "ltx-2.3-22b-distilled-fp8.safetensors",
    )
    before, after = _pair()
    plan = plan_join(before, after, "v2v-ramp", [2.0], brief="A fox waits and becomes a horse")
    assert plan["checkpoint"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    assert (plan["width"], plan["height"]) == (704, 384)
    assert plan["workflow"]["1"]["inputs"]["ckpt_name"] == plan["checkpoint"]
    assert plan["qa"]["pass"]
    fast = plan_join(before, after, "v2v-ramp", [2.0], brief="A fox waits and becomes a horse", fast=True)
    assert fast["checkpoint"] == "ltx-video-2b-v0.9.5.safetensors"
    assert "2.3" not in fast["workflow"]["1"]["inputs"]["ckpt_name"]
    assert fast["qa"]["pass"]


def test_a_morph_cannot_name_a_new_subject():
    before, after = _pair()
    plan = plan_join(before, after, "v2v-ramp", [2.0])
    assert plan["qa"]["pass"]
    assert "dragon" not in plan["prompt"]
    assert plan["seed"] == 2727
    assert plan["width"] % 32 == 0 and plan["height"] % 32 == 0
    assert plan["checkpoint"] == "ltx-video-2b-v0.9.5.safetensors"
    assert max(plan["strength"]) <= 0.35
    plan["prompt"] = "the fox meets a dragon"
    plan["qa"] = review(plan, [2.0])
    assert plan["qa"]["pass"] is False


def test_frame_mixes_do_not_sample_and_restyles_stay_local():
    before, after = _pair()
    mix = plan_join(before, after, "keyframe-blend", [2.0])
    assert mix["samples"] == 0
    assert mix["qa"]["pass"]
    assert "SamplerCustomAdvanced" not in {node["class_type"] for node in mix["workflow"].values()}
    ramp = graph({"method": "v2v-ramp", "prompt": "fox lighthouse", "width": 384, "height": 224, "strength": [0.15, 0.35]})
    assert audit_graph(ramp, "morph") == []
    assert ramp["1"]["inputs"]["ckpt_name"] == "ltx-video-2b-v0.9.5.safetensors"
    assert ramp["13"]["inputs"]["noise_seed"] == 2727
    assert audit_default_workflows() == []


def test_an_off_beat_join_fails_and_the_board_keeps_two():
    before, after = _pair()
    missed = plan_join(before, after, "cross-clip", [0.2], when=2.0)
    assert missed["qa"]["pass"] is False
    scenes = [
        {"action": "the fox waits", "form": "fox", "start": 0, "signature": False},
        {"action": "the fox climbs", "form": "fox", "start": 1, "signature": True},
        {"action": "the fox turns", "form": "fox", "start": 2, "signature": True},
        {"action": "the fox settles", "form": "fox", "start": 3, "signature": True},
    ]
    board = plan_board(scenes, [1, 2, 3], "keyframe-blend")
    assert board["kept"] == 2
    assert board["dropped"] == 1
    assert "hard cuts" in board["note"]
    client = TestClient(create_app())
    response = client.post("/api/morph/board", json={"scenes": scenes, "beats": [1, 2, 3], "method": "region-staged"})
    assert response.status_code == 200
    body = response.json()
    assert body["kept"] == 2
    assert "workflow" not in body["joins"][0]
    assert body["joins"][0]["qa"]["pass"] is True
