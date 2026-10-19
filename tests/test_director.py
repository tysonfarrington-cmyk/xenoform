import copy

import pytest

from xenoform.analyze import read_features
from xenoform.director import (
    RecipeError,
    apply_director,
    decode_recipe,
    empty_state,
    encode_recipe,
    fades_for_cuts,
    script_from_sections,
)
from xenoform.render_cpu import camera_distance, form_from_frame


def _frame(**overrides):
    base = {
        "t": 1.25,
        "bass": 0.7,
        "sub": 0.4,
        "mid": 0.3,
        "high": 0.55,
        "onset_env": 0.8,
        "beat_env": 0.2,
        "mutate": 0.2,
        "energy": 0.5,
    }
    base.update(overrides)
    return base


def test_recipe_roundtrip_includes_custom_noun_and_locks():
    state = empty_state()
    state["quality"] = "final"
    state["preset"] = ""
    state["sliders"]["kick"] = 0.25
    state["sliders"]["camera"] = 1.0
    state["locks"]["kick"] = True
    state["locks"]["script"] = True
    state["customs"] = [{"id": "c0", "noun": "glass harmonica", "kind": "noun"}]
    state["blocks"] = [
        {"form": "rocket", "hold": 2.4, "transition": "snap"},
        {"form": "c0", "hold": 1.5, "transition": "pour-harden"},
        {"form": "scream", "hold": 3.0, "transition": "droplet-burst"},
    ]
    code = encode_recipe(state)
    assert code.startswith("XF-")
    assert "-I" not in code and "-O" not in code
    restored = decode_recipe(code)
    assert restored["quality"] == "final"
    assert restored["preset"] == ""
    assert restored["locks"]["kick"] is True
    assert restored["locks"]["script"] is True
    assert restored["locks"]["bass"] is False
    assert restored["customs"][0]["noun"] == "glass harmonica"
    assert restored["customs"][0]["kind"] == "noun"
    assert restored["blocks"][0]["form"] == "rocket"
    assert restored["blocks"][0]["transition"] == "snap"
    assert restored["blocks"][1]["form"] == "c0"
    assert encode_recipe(restored) == code


def test_recipe_rejects_garbage():
    with pytest.raises(RecipeError):
        decode_recipe("XF-!!!!")


def test_script_and_sliders_stamp_the_features():
    features = read_features("examples/demo_features.json")
    original = copy.deepcopy(features)
    state = empty_state()
    state["blocks"] = script_from_sections(features)
    state["sliders"]["kick"] = 1.0
    state["sliders"]["bass"] = 0.9
    directed = apply_director(features, state)
    assert features["frames"][0]["section"] == original["frames"][0]["section"]
    drop = next(frame for frame in directed["frames"] if 6.2 < frame["t"] < 6.6)
    assert drop["section"] == "tower"
    assert drop["form"] == "tower"
    assert drop["analyzed_section"] == "drop"
    assert drop["camera_push"] == pytest.approx(0.9)
    source = original["frames"][drop["i"]]
    assert drop["onset_env"] >= source["onset_env"]
    assert drop["bass"] > source["bass"] or source["bass"] >= 1.5
    assert directed["director_fades"][0]["transition"] == state["blocks"][0]["transition"]
    fades = fades_for_cuts(directed, [directed["director_fades"][3]["frame"]])
    assert fades == [2]


def test_registers_fill_the_song_in_their_own_voice():
    from xenoform.director import script_for_register, text_card_cues, layout_blocks, REGISTERS

    features = read_features("examples/demo_features.json")
    pynchon = script_for_register(features, "pynchon")
    assert pynchon[0]["form"] == "rocket"
    drops = [block for block in pynchon if block["energy"] == "drop"]
    assert [block["form"] for block in drops] == ["tower", "scream"]
    assert {block["transition"] for block in drops} == {"droplet-burst"}

    lecarre = script_for_register(features, "lecarre")
    assert [block["form"] for block in lecarre] == ["dead-drop", "streetlamp", "typewriter", "briefcase"]
    assert len(lecarre) < len(features["sections"])
    assert {block["transition"] for block in lecarre} == {"pour-harden"}

    tolkien = script_for_register(features, "tolkien")
    assert [block["form"] for block in tolkien] == ["ring", "forge", "tree", "mountain"]
    assert {block["transition"] for block in tolkien} == {"grow-out"}

    rome = script_for_register(features, "rome")
    assert rome[0]["form"] == "coin"
    assert {block["transition"] for block in rome if block["energy"] == "drop"} == {"snap"}

    custom = script_for_register(features, "custom", [])
    assert custom[0]["form"] == ""
    named = script_for_register(features, "custom", [{"id": "c0"}, {"id": "c1"}])
    assert {block["form"] for block in named} <= {"c0", "c1"}

    state = empty_state()
    state["blocks"] = pynchon
    state["cards"] = [dict(card) for card in REGISTERS[0]["cards"]]
    cues = text_card_cues(layout_blocks(pynchon, features["duration"]), state["cards"], features["duration"])
    texts = " ".join(cue["text"] for cue in cues).lower()
    assert "arc completes" in texts
    for banned in ("screaming comes across the sky", "one ring to rule", "not all those who wander"):
        assert banned not in texts
    code = encode_recipe(state)
    restored = decode_recipe(code)
    assert restored["register"] == "pynchon"
    assert restored["palette"] == "violet"
    assert restored["cards"][0]["text"].startswith("The arc")
    assert restored["locks"]["register"] is False


def test_camera_distance_stays_put_unless_the_desk_asks():
    plain = form_from_frame(_frame())
    assert camera_distance(plain) == pytest.approx(2.45)
    neutral = form_from_frame(_frame(camera_energy=0.5, camera_push=0.5))
    assert camera_distance(neutral) == pytest.approx(2.45)
    pushed = form_from_frame(_frame(camera_energy=1.0, camera_push=1.0))
    assert camera_distance(pushed) < 2.0
