"""Rule-based briefs: subject, verb, object, setting, and a story check that means it."""

from xenoform.analyze import read_features
from xenoform.continuity import story_logic
from xenoform.storyboard import brief_cast, hero_has_verb, parse_brief, plan_storyboard, plan_with_hook

BRIEFS = (
    ("A lighthouse keeper rescues a fox from a storm.", "lighthouse keeper", "rescues", "fox", "lighthouse"),
    ("A lighthouse keeper and a fox wait out the storm.", "lighthouse keeper", "wait", "fox", "lighthouse"),
    ("An archivist carries a glass key into the stacks.", "archivist", "carries", "glass key", "stacks"),
    ("A ferry pilot hides a paper bird under the dock.", "ferry pilot", "hides", "paper bird", "dock"),
    ("The night guard follows a red balloon across the yard.", "night guard", "follows", "red balloon", "yard"),
    ("A baker loses a gold ring in the kitchen.", "baker", "loses", "gold ring", "kitchen"),
    ("An astronaut returns a seed to the station.", "astronaut", "returns", "seed", "station"),
    ("A diver finds a bell on the reef.", "diver", "finds", "bell", "reef"),
    ("A conductor opens a violin case in the hall.", "conductor", "opens", "violin case", "hall"),
    ("A shepherd leads a lamb through the forest.", "shepherd", "leads", "lamb", "forest"),
)


def _features():
    return read_features("examples/demo_features.json")


def test_ten_briefs_keep_the_verb_and_the_nouns():
    features = _features()
    for brief, hero, verb, prop, place in BRIEFS:
        cast = brief_cast(brief)
        assert cast["hero"] == hero, brief
        assert cast["prop"] == prop, brief
        assert cast["place"] == place, brief
        if "storm" in brief:
            assert cast["threat"] == "storm", brief
        else:
            assert cast["threat"] == "", brief
        assert hero_has_verb(cast["hero"]) is False
        parsed = parse_brief(brief)
        assert parsed["base"], brief
        scenes = plan_storyboard(features, "pynchon", brief)
        assert scenes[0]["protagonist"] == f"the {hero}", brief
        assert hero_has_verb(scenes[0]["protagonist"]) is False
        actions = [scene["action"] for scene in scenes]
        verbs = [scene["verb"] for scene in scenes]
        assert len(set(actions)) == len(actions), brief
        assert len(set(verbs)) >= 3, brief
        blob = " ".join(actions).lower()
        for word in prop.split():
            assert word in blob, brief
        for word in place.split():
            assert word in blob, brief
        for word in str(cast["threat"]).split():
            assert word in blob, brief
        assert "with the fox at the storm" not in blob, brief
        climax = next(scene for scene in scenes if scene["beat"] == "climax")
        assert parsed["third"] in climax["action"], brief
        assert parsed["base"] in scenes[0]["action"], brief
        assert parsed["base"] in scenes[-1]["action"], brief
        if parsed["verb"] == "rescues":
            assert "rescues the fox from the storm" in climax["action"]
            assert scenes[0]["place"] == "lighthouse"
        if parsed["base"] == "wait":
            assert "waits out the storm" in climax["action"]
            assert "fox" in scenes[0]["action"]
            assert "at the lighthouse" in scenes[0]["action"]
        assert verb in {parsed["verb"], parsed["base"], parsed["third"]}
        logic = story_logic(brief, scenes)
        assert logic["ok"] is True, (brief, logic["flags"])
        assert logic["detail"] == "The story holds in one line."


def test_story_check_fails_when_the_hero_contains_a_verb():
    brief = "A lighthouse keeper rescues a fox from a storm."
    scenes = plan_storyboard(_features(), "pynchon", brief)
    for scene in scenes:
        scene["protagonist"] = "the lighthouse keeper rescues"
    logic = story_logic(brief, scenes)
    assert logic["ok"] is False
    assert any(flag["plain"] == "The hero contains a verb." for flag in logic["flags"])
    assert logic["detail"] != "The story holds in one line."


def test_story_check_fails_when_a_brief_noun_is_missing():
    brief = "A lighthouse keeper rescues a fox from a storm."
    scenes = plan_storyboard(_features(), "pynchon", brief)
    for scene in scenes:
        scene["protagonist"] = "the lighthouse keeper"
        scene["action"] = scene["action"].replace("fox", "shape")
        scene["verb"] = scene["verb"].replace("fox", "")
        scene["prompt"] = ""
    logic = story_logic(brief, scenes)
    assert logic["ok"] is False
    assert any("fox" in flag["plain"] and "missing" in flag["plain"] for flag in logic["flags"])


def test_ollama_rephrase_keeps_the_nouns(monkeypatch):
    monkeypatch.delenv("XENO_LLM_URL", raising=False)

    def fake(brief, scenes, cast, allow_cloud=False):
        return [
            {"action": f"the lighthouse keeper rescues the fox from the storm, pass {index}", "verb": f"move-{index}"}
            for index, _scene in enumerate(scenes)
        ]

    monkeypatch.setattr("xenoform.storyboard._ollama_story", fake)
    monkeypatch.setattr("xenoform.storyboard._comfy_story", lambda *args, **kwargs: None)
    scenes, source = plan_with_hook(_features(), "pynchon", "A lighthouse keeper rescues a fox from a storm.")
    assert source == "llm"
    assert all("fox" in scene["action"] and "storm" in scene["action"] for scene in scenes)
    assert hero_has_verb(scenes[0]["protagonist"]) is False


def test_a_rewrite_that_drops_the_fox_is_ignored(monkeypatch):
    monkeypatch.delenv("XENO_LLM_URL", raising=False)

    def fake(brief, scenes, cast, allow_cloud=False):
        return [{"action": "the lighthouse keeper rescues", "verb": f"move-{index}"} for index, _scene in enumerate(scenes)]

    monkeypatch.setattr("xenoform.storyboard._ollama_story", fake)
    monkeypatch.setattr("xenoform.storyboard._comfy_story", lambda *args, **kwargs: None)
    scenes, source = plan_with_hook(_features(), "pynchon", "A lighthouse keeper rescues a fox from a storm.")
    assert source == "template"
    assert "fox" in scenes[0]["action"]
    assert scenes[0]["protagonist"] == "the lighthouse keeper"
