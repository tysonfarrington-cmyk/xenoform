"""Continuity bible, cast lock, story logic, and the post-render critic."""

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from xenoform.analyze import read_features
from xenoform.continuity import (
    cast_lock,
    compare_element,
    continuity_bible,
    ensure_stills,
    rerender_ids,
    similarity,
    stamp_continuity,
    story_logic,
)
from xenoform.lessons import BUILTIN, catalog
from xenoform.storyboard import DEMO_BRIEF, plan_storyboard, scene_prompt
from xenoform.ui import create_app

PHONE = "The phone is one handset, the same shape and size in every shot."
HERO = "The hero is the caller, the same silhouette in every shot."
PLACE = "The place is Jupiter, the same ground in every shot."


def _voicemail():
    return [
        {
            "index": 0,
            "beat": "setup",
            "start": 0.0,
            "end": 2.0,
            "shot": "close",
            "form": "handset",
            "protagonist": "the caller",
            "verb": "dials",
            "action": "a flip phone sits on the dash",
            "guide": "a flip phone sits on the dash",
        },
        {
            "index": 1,
            "beat": "rising",
            "start": 2.0,
            "end": 4.0,
            "shot": "close",
            "form": "handset",
            "protagonist": "the caller",
            "verb": "speaks",
            "action": "a smartphone glows in the caller's hand",
            "guide": "a smartphone glows in the caller's hand",
        },
        {
            "index": 2,
            "beat": "release",
            "start": 4.0,
            "end": 6.0,
            "shot": "wide",
            "form": "haze",
            "protagonist": "",
            "verb": "",
            "action": "neon haze fills the frame",
            "guide": "neon haze fills the frame",
        },
    ]


def test_voicemail_locks_one_phone_and_one_hero():
    brief = "A voicemail to Jupiter, left on one phone."
    scenes = _voicemail()
    actions = [scene["action"] for scene in scenes]
    bible = continuity_bible(brief, scenes)
    assert bible["cast"]["lock"] == "cast"
    assert bible["cast"]["sentence"] == HERO
    assert "liquid chrome" not in HERO
    names = [element["name"] for element in bible["elements"]]
    assert names.count("phone") == 1
    assert "Jupiter" in names
    stamped = stamp_continuity(scenes, brief)
    assert [scene["action"] for scene in stamped] == actions
    logic = story_logic(brief, stamped)
    assert logic["ok"] is False
    assert logic["what"] == brief
    plains = [flag["plain"] for flag in logic["flags"]]
    assert any("new phone" in plain for plain in plains)
    assert any("only atmosphere" in plain for plain in plains)
    opening = scene_prompt(stamped[0], "base")
    assert opening.count(PHONE) == 1
    assert opening.count(HERO) == 1
    assert opening.count(PLACE) == 1
    assert "flip phone" not in opening.lower()
    assert "smartphone" not in opening.lower()
    assert "does not morph" in opening
    assert "liquid chrome" not in opening.lower()
    haze = scene_prompt(stamped[2], "base")
    assert PHONE not in haze
    assert HERO not in haze


def test_two_phones_are_allowed_when_the_story_says_so():
    brief = "Two phones share one table."
    scenes = [
        {"index": 0, "beat": "setup", "protagonist": "the caller", "action": "a flip phone and a smartphone sit together", "verb": "sets"},
        {"index": 1, "beat": "rising", "protagonist": "the caller", "action": "the caller picks one up", "verb": "picks"},
    ]
    bible = continuity_bible(brief, scenes)
    assert all(element["name"] != "phone" for element in bible["elements"])
    logic = story_logic(brief, scenes)
    assert all("new phone" not in flag["plain"] for flag in logic["flags"])
    assert logic["ok"] is True


def test_demo_story_still_holds_in_one_line():
    features = read_features(Path("examples/demo_features.json"))
    scenes = plan_storyboard(features, "pynchon", DEMO_BRIEF)
    actions = [scene["action"] for scene in scenes]
    stamped = stamp_continuity(scenes, DEMO_BRIEF)
    assert [scene["action"] for scene in stamped] == actions
    logic = story_logic(DEMO_BRIEF, stamped)
    assert logic["ok"] is True, logic["flags"]
    prompt = scene_prompt(stamped[0], "base")
    sentence = cast_lock(stamped[0]["protagonist"])["sentence"]
    assert prompt.count(sentence) == 1
    assert "does not morph" in prompt
    assert "liquid chrome" not in prompt.lower()


def test_reference_still_is_painted_once(tmp_path):
    element = cast_lock("the caller")
    first = ensure_stills([element], tmp_path)[0]
    second = ensure_stills([element], tmp_path)[0]
    assert first["still_name"] == second["still_name"]
    assert Path(first["still"]).is_file()
    assert first["url"].endswith(first["still_name"])


def test_critic_flags_a_phone_that_changes_shape():
    reference = np.zeros((48, 48, 3), dtype=np.uint8)
    reference[4:44, 18:26] = (200, 30, 30)
    other = np.zeros((48, 48, 3), dtype=np.uint8)
    other[18:28, 4:44] = (30, 40, 200)
    assert similarity(reference, reference)["pass"] is True
    assert similarity(reference, other)["pass"] is False
    shots = [
        {"index": index, "start": float(index) * 2, "image": other}
        for index in range(3)
    ]
    flag = compare_element("phone", reference, shots, sentence=PHONE, still_name="phone.png")
    assert flag["plain"] == "phone differs, shots 1-3"
    assert flag["t"] == 0.0
    assert flag["kind"] == "rerender"
    assert flag["op"]["shots"] == ["s0", "s1", "s2"]
    assert rerender_ids([flag]) == ["s0", "s1", "s2"]


def test_review_fix_rerenders_only_the_offending_shots():
    client = TestClient(create_app())
    finding = compare_element(
        "phone",
        np.zeros((8, 8, 3), dtype=np.uint8),
        [
            {"index": 0, "start": 0.0, "image": np.full((8, 8, 3), 255, dtype=np.uint8)},
            {"index": 2, "start": 4.0, "image": np.full((8, 8, 3), 255, dtype=np.uint8)},
        ],
        sentence=PHONE,
        still_name="phone.png",
    )
    scenes = [
        {"index": 0, "action": "a flip phone", "guide": "a flip phone", "start": 0, "end": 2},
        {"index": 1, "action": "the caller waits", "guide": "the caller waits", "start": 2, "end": 4},
        {"index": 2, "action": "a smartphone", "guide": "a smartphone", "start": 4, "end": 6},
    ]
    response = client.post(
        "/api/v1/review/apply",
        json={"quality": "live", "audio_id": "demo", "scenes": scenes, "findings": [finding]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["rerender"] == ["s0", "s2"]
    assert body["queued"] is False
    assert PHONE in body["scenes"][0]["guide"]
    assert PHONE not in body["scenes"][1]["guide"]
    assert PHONE in body["scenes"][2]["guide"]
    assert body["scenes"][0]["still_name"] == "phone.png"
    assert body["scenes"][0]["guide_from"] == "reference"


def test_continuity_is_a_default_lesson():
    assert any(item["id"] == "continuity" for item in catalog())
    lesson = next(item["lesson"] for item in BUILTIN if item["id"] == "continuity")
    assert "phone changed shape" in lesson
    assert lesson in Path("docs/LESSONS.md").read_text(encoding="utf-8")
