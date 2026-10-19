"""A form change survives the desk path: /api/story, then /api/morph/board."""

import re

from fastapi.testclient import TestClient

from xenoform.analyze import read_features
from xenoform.morph.gate import _content
from xenoform.ui import create_app

# Subject A, subject B, the place, and the action verb when the brief has one.
BRIEFS = (
    ("A cheetah runs along a beach and becomes a horse.", "cheetah", "horse", "beach", "run"),
    ("A drop of milk turns into a flower in the kitchen.", "drop of milk", "flower", "kitchen", ""),
    ("A paper boat turns into birds over the harbour.", "paper boat", "birds", "harbour", ""),
    ("A glass bottle transforms into a lighthouse on the cliff.", "glass bottle", "lighthouse", "cliff", ""),
    ("A red balloon morphs into a bird above the pier.", "red balloon", "bird", "pier", ""),
    ("A candle melts into a pool on the dock.", "candle", "pool", "dock", ""),
    ("A seed grows into a tree in the forest.", "seed", "tree", "forest", ""),
    ("A fox runs through the alley and becomes a shadow.", "fox", "shadow", "alley", "run"),
    ("An astronaut walks across the station and transforms into a star.", "astronaut", "star", "station", "walk"),
    ("A coin on the shore morphs into a shell.", "coin", "shell", "shore", ""),
)

_LEAKS = ("octopus", "tower", "song", "rocket", "sphere", "scream")


def _features():
    return read_features("examples/demo_features.json")


def _foreign(prompt: str, allowed: list[str]) -> set[str]:
    return _content(prompt) - set(allowed)


def test_ten_changes_survive_story_then_the_morph_board():
    features = _features()
    client = TestClient(create_app())
    for brief, subject_a, subject_b, place, motion in BRIEFS:
        story = client.post(
            "/api/story",
            json={"brief": brief, "audio_id": "demo", "register": "pynchon", "rolls": 1},
        )
        assert story.status_code == 200, brief
        scenes = story.json()["scenes"]
        climax = next(scene for scene in scenes if scene["beat"] == "climax")
        before = [scene for scene in scenes if scene["index"] < climax["index"]]
        after = [scene for scene in scenes if scene["index"] > climax["index"]]
        assert before and after, brief
        for scene in before:
            assert scene["protagonist"] == f"the {subject_a}", (brief, scene["action"])
            assert subject_b not in scene["action"], (brief, scene["action"])
            assert scene["form"] == subject_a.replace(" ", "-"), brief
        assert climax["becomes"] == subject_b, (brief, climax["action"])
        assert subject_a in climax["action"] and subject_b in climax["action"], climax["action"]
        assert place in climax["action"], climax["action"]
        for scene in after:
            assert scene["protagonist"] == f"the {subject_b}", (brief, scene["action"])
            assert scene["form"] == subject_b.replace(" ", "-"), brief
        blob = " ".join(scene["action"] for scene in scenes).lower()
        assert place in blob, brief
        assert f"the {motion}" not in blob if motion else "the turn" not in blob
        if motion:
            assert re.search(rf"\bthe {motion}\b", blob) is None, blob
            assert motion in blob or motion + "s" in blob or motion + "ing" in blob
        assert "looking at the" not in blob, blob
        logic = story.json()["logic"]
        assert logic["ok"] is True, (brief, logic["flags"])

        for sent_brief in (brief, ""):
            board = client.post(
                "/api/morph/board",
                json={
                    "scenes": scenes,
                    "beats": features["beats"],
                    "method": "v2v-ramp",
                    "brief": sent_brief,
                },
            )
            assert board.status_code == 200, brief
            body = board.json()
            assert body["joins"], (brief, body)
            join = body["joins"][0]
            prompt = str(join["prompt"])
            low = prompt.lower()
            assert join["subject_a"] == subject_a, (brief, sent_brief, prompt)
            assert join["subject_b"] == subject_b, (brief, sent_brief, prompt)
            for word in subject_a.split():
                assert re.search(rf"\b{re.escape(word)}\b", low), (brief, prompt)
            for word in subject_b.split():
                assert re.search(rf"\b{re.escape(word)}\b", low), (brief, prompt)
            assert re.search(rf"\b{re.escape(place)}\b", low), (brief, prompt)
            for leak in _LEAKS:
                assert leak not in low, (brief, prompt)
            extra = _foreign(prompt, join["cast"])
            assert not extra, (brief, sent_brief, sorted(extra), prompt)
            assert join["qa"]["pass"] is True, (brief, sent_brief, join["qa"], prompt)
