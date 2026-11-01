"""Anchors and places match whole nouns (the follow-ups of 1 Nov): an idea line that opened on "moon jellyfish" (the Glow
sea loved chain's) sent the NASA moon anchor into every intro prompt of a Cloud whole song. A real subject or a place
counts only as the head of its noun phrase, never inside a word or as the first word of a longer noun: moon jellyfish
is a jellyfish, moon rocks are rocks, a sea angel is an angel; the moon, a jellyfish under the moon, the moon rising
are the moon."""
from __future__ import annotations

import pytest

from xenoform import anchors, cloud_final, guardrails, idea, presets
from xenoform import morph_pass as mp


@pytest.mark.parametrize("text,subject", [
    ("moon jellyfish", ""), ("Moon jellyfish, comb jelly, manta ray", ""), ("moon rocks", ""), ("the moon's surface", ""),
    ("moon-jellyfish", ""), ("honeymoon", ""), ("earth tones", ""), ("a mars rover", ""),
    ("the moon", "moon"), ("a jellyfish under the moon", "moon"), ("a full moon", "moon"), ("the moon rises over the sea", "moon"),
    ("moons", "moon"), ("Jupiter and its moons", "jupiter"), ("the red planet, mars", "mars"), ("Saturn.", "saturn"),
    ("a giant Jupiter storm", "jupiter"), ("Saturn's rings", "saturn"),  # the subject with its own feature, as anchored
])
def test_a_real_subject_is_named_only_as_a_whole_noun(text, subject):
    assert anchors.subject_in(text) == subject


def test_the_noun_rule_reads_plurals_hyphens_and_what_follows():
    assert anchors.named("moon", "two moons over a lake") and anchors.named("galaxy", "spiral galaxies")
    assert not anchors.named("moon", "moonlit sea") and not anchors.named("moon", "moon-lit water")
    assert anchors.named("moon", "the moon glowing") and not anchors.named("moon", "moon landing")
    assert anchors.head_follower("") and anchors.head_follower(",") and anchors.head_follower("over")
    assert not anchors.head_follower("jellyfish")
    assert anchors.anchor_for("moon jellyfish") == {}


@pytest.mark.parametrize("line,anchored", [("moon jellyfish", False), ("a jellyfish under the moon", True), ("the moon", True),
                                           ("moon rocks", False), ("a gold sun disk", False), ("a spiral galaxy", True)])
def test_the_guardrail_anchors_only_a_named_real_subject(line, anchored):
    body, rep = guardrails.apply({"idea": line, "vibe": "cosmic"}, duration=16.0)
    assert (body.get("anchor") == "nasa") is anchored
    assert any(m.startswith("[duplicate_features]") for m in rep["messages"]) is anchored


def test_the_glow_sea_chain_makes_its_own_prompts_with_no_moon_in_them():
    """The Glow sea chain's idea line opens on "moon jellyfish": its Cloud prompts name its creatures and the vibe, and
    carry no NASA moon (the photograph, black space, the NASA hint) and its negative none of the planets' terms."""
    p = presets.get("glow-sea")
    assert p["idea"].startswith("moon jellyfish")
    body, rep = guardrails.apply({**presets.body(p), "quality_tier": "cloud"}, duration=16.0)
    assert body.get("anchor") is None and not any("duplicate_features" in m for m in rep["messages"])
    cat = {r["file"]: r for rows in mp.catalogue().values() for r in rows}
    stills = [cat[p["pins"][str(k)]] for k in range(4)]  # comb jelly, siphonophore, jellyfish, sea turtle: the intro
    prompts = []
    for a, b in zip(stills, stills[1:]):
        text = cloud_final.lead(a.get("noun"), b.get("noun")) + mp.prompt_for(body["vibe"], "ltx25", mp.pair_kinds(a, b), style="bloom")
        prompts.append(guardrails.guard_prompt(text, body))
    assert [x.split(" slowly")[0] for x in prompts] == ["The comb jelly", "The siphonophore", "The jellyfish"]
    for x in prompts:
        low = x.lower()
        assert "moon" not in low and "nasa" not in low and "black space" not in low and "bioluminescent" in low
    neg = guardrails.negative_for(cloud_final.NEGATIVE, body)
    assert neg == cloud_final.NEGATIVE and "multiple storms" not in neg
    moon, _ = guardrails.apply({"idea": "a jellyfish under the moon", "vibe": "bioluminescent"}, duration=16.0)
    assert "photoreal moon exactly as in the reference photograph" in guardrails.guard_prompt("a prompt", moon)


def test_the_idea_reader_reads_a_place_or_a_sky_only_as_a_whole_noun():
    glow = idea.read("moon jellyfish, comb jelly, manta ray, sea angel, nautilus", "bioluminescent", llm=False)
    assert glow["scenes"] == [] and "sea angel" in glow["own"] and "jellyfish" in glow["objects"]  # a sea angel is a creature
    assert idea.read("the moon", "cosmic", llm=False)["scenes"] == ["the moon"]
    assert idea.read("a jellyfish under the moon", "cosmic", llm=False)["objects"] == ["jellyfish"]
    assert idea.read("jellyfish under the sea", "ocean", llm=False)["scenes"] == ["the sea"]
    assert idea.read("cold-blue dusk over a flooded car park", "cosmic", llm=False)["scenes"]  # the car park is a park
    assert idea.read("a beach ball", "cosmic", llm=False)["scenes"] == []  # a beach ball is a ball
