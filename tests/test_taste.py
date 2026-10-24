"""Taste on long songs (24 Oct 2026): a long song's morphs are distinct pairs, the drop gets a real transition in the
Simple cut, every featured vibe's registry picks are premium, and the story plan has a viscous pace."""
from xenoform import dense, morph_pass, transitions_fx as T, vibes as V


def _beats(duration: float, bpm: float = 120.0) -> list[float]:
    step = 60.0 / bpm
    return [round(i * step, 4) for i in range(int(duration / step))]


def _sections():
    return [
        {"index": 0, "label": "calm", "start": 0.0, "end": 16.0, "level": 0.2},
        {"index": 1, "label": "build", "start": 16.0, "end": 32.0, "level": 0.6},
        {"index": 2, "label": "drop", "start": 32.0, "end": 64.0, "level": 1.0},
        {"index": 3, "label": "calm", "start": 64.0, "end": 96.0, "level": 0.25},
        {"index": 4, "label": "release", "start": 96.0, "end": 120.0, "level": 0.3},
    ]


def _pairs(stills):
    chain = stills + stills[:1]  # the chain closes on the first still
    return [(min(a["file"], b["file"]), max(a["file"], b["file"])) for a, b in zip(chain, chain[1:])]


def test_chain_walk_makes_distinct_pairs_on_a_long_song():
    pool = [{"noun": f"n{i}", "file": f"f{i}"} for i in range(12)]
    first = morph_pass.chain_walk(pool, 12)
    assert [x["file"] for x in first] == [p["file"] for p in pool]  # a short cut is the pool in order, as before
    walk = morph_pass.chain_walk(pool, 24)
    pairs = _pairs(walk)
    assert len(pairs) == 24 and len(set(pairs)) == 24  # 24 morphs over 12 objects: 24 different pairings
    assert all(a != b for a, b in pairs)  # never a still morphing into itself
    assert [x["file"] for x in walk[:12]] == [p["file"] for p in pool]  # the first lap is still the pool's order
    long = morph_pass.chain_walk(pool, 48)
    assert len(set(_pairs(long))) >= 44  # 66 pairs exist; a 48-morph walk repeats only a handful
    assert morph_pass.chain_walk(pool, 0) == [] and len(morph_pass.chain_walk(pool[:2], 5)) == 5


def test_the_drop_gets_a_real_transition_in_the_simple_cut():
    shots = dense.story_plan(120.0, _beats(120.0), _sections(), 32.0)["shots"]
    for s in shots:
        s["frames"] = int(round((s["end"] - s["start"]) * 24))
    trans = dense.boundary_transitions(shots, "chrome-mercury", seed=1)
    kinds = {t["boundary"]: t["kind"] for t in trans if t}
    assert kinds.get("drop") == "match-cut"  # no GPU scene morph in the Simple cut, so the drop is a match-cut
    assert "scene-morph" not in {t["kind"] for t in trans if t}


def test_featured_vibes_pick_premium_transitions_from_the_registry():
    for row in V.featured():
        picks = row["transitions"]
        assert picks["drop"] in T.PREMIUM, row["id"]
        assert picks["switch"] in T.PREMIUM, row["id"]
        assert T.recommend(row["id"], "drop") == picks["drop"] and T.recommend(row["id"], "switch") == picks["switch"]


def test_viscous_pace_cuts_the_drop_on_the_bar():
    beats = _beats(120.0)
    tight = dense.story_plan(120.0, beats, _sections(), 32.0)["shots"]
    viscous = dense.story_plan(120.0, beats, _sections(), 32.0, pace="viscous")["shots"]
    drop_t = [round(s["end"] - s["start"], 2) for s in tight if s.get("section") == "drop"]
    drop_v = [round(s["end"] - s["start"], 2) for s in viscous if s.get("section") == "drop"]
    assert drop_t[0] == 1.0 and drop_v[0] == 2.0  # half a bar against a bar at 120 bpm
    assert len(viscous) < len(tight)
    assert dense.story_pace({"pace": "viscous"}) == "viscous" and dense.story_pace({"pace": "weird"}) == "tight" and dense.story_pace(None) == "tight"
    directed = {"duration": 120.0, "beats": beats, "sections": _sections()}
    shots, plan = dense.shots_for({"energy_preset": "dense", "aspect": "9:16", "pace": "viscous"}, directed, None)
    assert plan["name"] == "story" and len(shots) == len(viscous)
