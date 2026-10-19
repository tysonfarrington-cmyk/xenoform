import os

from xenoform.analyze import read_features
from xenoform.director import apply_director, decode_recipe, empty_state, encode_recipe, prompts_for_state
from xenoform.storyboard import (
    DEMO_BRIEF,
    blocks_from_scenes,
    climax_index,
    parse_brief,
    plan_storyboard,
    plan_with_hook,
    roll_storyboards,
    snap_bars,
)


def _features():
    return read_features("examples/demo_features.json")


def test_brief_becomes_a_life_with_a_climax_on_the_drop():
    features = _features()
    scenes = plan_storyboard(features, "pynchon", DEMO_BRIEF)
    assert len(scenes) == len(features["sections"])
    assert scenes[0]["beat"] == "setup"
    assert "born" in scenes[0]["action"]
    assert "cold" in scenes[0]["action"]
    assert scenes[-1]["beat"] == "release"
    assert "earth" in scenes[-1]["action"]
    assert "changed" in scenes[-1]["action"]
    peak = climax_index(features["sections"])
    assert scenes[peak]["beat"] == "climax"
    assert scenes[peak]["form"] in {"tower", "scream"}
    assert scenes[0]["shot"] == "wide"
    assert scenes[0]["protagonist"] == "the rocket"
    assert "birth" in scenes[0]["goal"]
    assert "earth" in scenes[0]["payoff"]
    assert scenes[peak]["shot"] == "close"
    assert scenes[-1]["shot"] == "reveal"
    signatures = [scene for scene in scenes if scene["signature"]]
    assert len(signatures) == 1
    assert signatures[0]["index"] == peak
    assert signatures[0]["conditioning"] == "signature"
    for scene in scenes:
        assert scene["bars"] == snap_bars(scene["seconds"], scene["bar_seconds"])
        assert scene["bars"] >= 1
        assert scene["verb"]
        if scene["signature"]:
            assert "Signature transition" in scene["guide"]
        else:
            assert scene["edit"] == "hard cut"
            assert scene["conditioning"] == "first-frame"
            assert "First frame" in scene["guide"]
            assert "Hard cut" in scene["guide"]


def test_callback_and_motif_and_a_dragged_climax():
    features = _features()
    scenes = plan_storyboard(
        features,
        "pynchon",
        DEMO_BRIEF,
        motif="bulb",
        callback="the sphere returns at the end, changed",
    )
    assert scenes[-1]["form"] == "sphere"
    assert scenes[-1]["action"].startswith("the sphere returns")
    assert any(scene["form"] == "bulb" and scene["index"] not in (0,) for scene in scenes)
    moved = plan_storyboard(features, "pynchon", DEMO_BRIEF, climax=1)
    assert moved[1]["beat"] == "climax"
    assert moved[0]["beat"] == "setup"
    assert all(scene["beat"] == "release" for scene in moved[2:])


def test_roll_keeps_the_best_and_penalises_loops():
    features = _features()
    rolled = roll_storyboards(features, "pynchon", DEMO_BRIEF, rolls=6)
    assert rolled["score"]["loops"] == 0
    assert rolled["score"]["hook"] is True
    assert rolled["score"]["climax_on_peak"] is True
    forms = [scene["form"] for scene in rolled["scenes"]]
    assert all(left != right for left, right in zip(forms, forms[1:]))


def test_llm_hook_is_optional_and_offline(monkeypatch):
    features = _features()
    monkeypatch.delenv("XENO_LLM_URL", raising=False)
    monkeypatch.setattr("xenoform.storyboard._ollama_story", lambda *args, **kwargs: None)
    monkeypatch.setattr("xenoform.storyboard._comfy_story", lambda *args, **kwargs: None)
    scenes, source = plan_with_hook(features, "lecarre", "a quiet exchange, from the lamp to the latch")
    assert source == "template"
    assert scenes[0]["form"] == "dead-drop"
    monkeypatch.setenv("XENO_LLM_URL", "http://127.0.0.1:9")
    again, source = plan_with_hook(features, "lecarre", "a quiet exchange, from the lamp to the latch")
    assert source == "template"
    assert again[0]["action"]
    assert os.environ["XENO_LLM_URL"].startswith("http")


def test_recipe_roundtrips_the_storyboard_and_the_cards_compile():
    features = _features()
    state = empty_state()
    state["brief"] = DEMO_BRIEF
    state["mode"] = "director"
    state["register"] = "pynchon"
    state["scenes"] = plan_storyboard(features, "pynchon", DEMO_BRIEF)
    state["blocks"] = blocks_from_scenes(state["scenes"])
    state["climax"] = next(scene["index"] for scene in state["scenes"] if scene["beat"] == "climax")
    state["callback"] = ""
    code = encode_recipe(state)
    restored = decode_recipe(code)
    assert restored["brief"] == DEMO_BRIEF
    assert restored["mode"] == "director"
    assert len(restored["scenes"]) == len(state["scenes"])
    assert restored["scenes"][0]["action"] == state["scenes"][0]["action"]
    assert restored["scenes"][0]["shot"] == "wide"
    assert restored["scenes"][0]["protagonist"] == state["scenes"][0]["protagonist"]
    assert restored["scenes"][0]["verb"] == state["scenes"][0]["verb"]
    assert restored["scenes"][0]["goal"] == state["scenes"][0]["goal"]
    assert restored["scenes"][0]["payoff"] == state["scenes"][0]["payoff"]
    assert restored["climax"] == state["climax"]
    peak = next(scene for scene in restored["scenes"] if scene["beat"] == "climax")
    assert peak["signature"] is True
    assert encode_recipe(restored) == code

    directed = apply_director(features, state)
    assert directed["frames"][0]["section"] == "s0"
    assert directed["frames"][0]["guide"]
    assert directed["frames"][0]["lens"] == "wide"
    prompts = prompts_for_state(state)
    assert "born" in prompts["s0"].lower()
    assert "liquid chrome" not in prompts["s0"].lower()
    assert "does not morph" in prompts["s0"].lower()
    state["preset"] = "liquid-metal"
    liquid = prompts_for_state(state)
    assert "liquid" in liquid["s0"].lower()
    drop = next(frame for frame in directed["frames"] if frame["section"] == f"s{state['climax']}")
    assert drop["shot"] == "close"


def test_empty_brief_still_seeds_from_the_register():
    features = _features()
    parsed = parse_brief("")
    assert parsed["subject"] == ""
    scenes = plan_storyboard(features, "rome", "")
    assert scenes[0]["form"] == "coin"
    assert scenes[0]["mood"] == "marble"
