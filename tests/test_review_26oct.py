"""The 26 Oct review of the feedback batch: eleven findings that survived two refuters each, pinned here."""
from pathlib import Path

import numpy as np

from xenoform import beatfx, dense, foreshadow as F, morph_pass as mp, stills as S


def _sections(duration: float) -> list[dict]:
    labels = ["intro", "calm", "build", "drop", "calm", "build", "drop", "outro"]
    step = duration / len(labels)
    return [{"label": lab, "start": round(i * step, 3), "end": round((i + 1) * step, 3)} for i, lab in enumerate(labels)]


def test_a_story_that_outnumbers_the_morphs_is_merged_to_fit(monkeypatch, tmp_path):
    """A shipped 12-still pool and a four-minute song with eight passages: the story planner keeps a cut at every
    role start, so max_shots alone left 16 shots for 11 morphs and the compose crashed on clips[nxt]."""
    rows = [{"file": f"ocean/{i:02d}.jpg", "noun": f"thing{i}"} for i in range(12)]
    monkeypatch.setattr(mp, "manifest", lambda: {"ocean": rows})
    monkeypatch.setattr(S, "grown", lambda: {})
    monkeypatch.setattr(S, "usage", lambda: {})
    duration, period = 238.8, 0.4
    beats = [round(i * period, 4) for i in range(int(duration / period))]
    directed = {"duration": duration, "beats": beats, "sections": _sections(duration), "drop": 119.6}
    state = {"vibe": "ocean", "energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16"}
    shots, plan = dense.shots_for(state, directed, tmp_path / "song.wav")
    assert len(shots) > 11
    shots2, plan2, chain, notes = dense.long_song_chain(state, directed, tmp_path / "song.wav", shots, plan,
                                                        dense.options(state), engine="mock")
    assert chain["fits"] and chain["morphs"] == 11 and len(shots2) == 11 == len(chain["assign"])
    assert abs(float(shots2[0]["start"])) < 1e-6 and abs(float(shots2[-1]["end"]) - duration) < 1e-3
    assert all(abs(float(a["end"]) - float(b["start"])) < 1e-6 for a, b in zip(shots2, shots2[1:]))
    assert abs(sum(float(s["seconds"]) for s in shots2) - duration) < 0.05
    assert [list(n)[0] for n in notes] == ["capped"] and notes[0]["capped"]["pool"] == 12


def test_merge_to_keeps_the_timeline_and_the_effects():
    shots = [{"index": i, "start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24, "effects": [{"type": "punch", "t": i}]}
             for i in range(5)]
    shots[2]["seconds"] = 0.25  # the shortest folds into its shorter neighbour
    out = dense._merge_to(shots, 3)
    assert len(out) == 3 and [s["index"] for s in out] == [0, 1, 2]
    assert out[0]["start"] == 0.0 and out[-1]["end"] == 5.0
    assert sum(len(s["effects"]) for s in out) == 5 and sum(s["frames"] for s in out) == 120
    assert dense._merge_to(shots, 9) == shots  # nothing to fold


def test_stop_words_name_no_family_and_lead_no_object(monkeypatch):
    assert S.content_words(["a", "chess", "to", "the", "machines"]) == {"chess", "machines"}
    assert S.family_named("chrome-mercury", {"and"}) == "" and S.family_named("chrome-mercury", {"to"}) == ""
    assert S.family_named("chrome-mercury", {"lanterns"}) == S.family_of("lantern")
    assert S.family_for_cut("chrome-mercury", {"and", "to"}) == S.family_for_cut("chrome-mercury", set())
    rows = [{"file": "chrome-mercury/0_orb.jpg", "noun": "orb"}, {"file": "chrome-mercury/1_reel.jpg", "noun": "reel to reel"}]
    monkeypatch.setattr(mp, "manifest", lambda: {"chrome-mercury": rows})
    monkeypatch.setattr(S, "grown", lambda: {})
    monkeypatch.setattr(S, "usage", lambda: {})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    _, picked = mp.pick_stills({"vibe": "chrome-mercury", "idea": "a road to the sea"}, 2, record=False)
    assert picked[0]["noun"] == "orb"  # "to" does not make the reel-to-reel the lead


def test_the_grow_for_an_idea_looks_the_family_up_like_the_pick(monkeypatch):
    """A vibe that borrows a pool keeps its own family weights; the grow used to look the family up under the pool."""
    asked = []
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": True})
    monkeypatch.setattr(S, "grow", lambda vibe, count, *, nouns=None, **kw: (asked.append((vibe, list(nouns or []))), {"kept": len(nouns or [])})[1])
    state = {"vibe": "neon-noir", "idea": "a moth circles the lamp", "seed": 3}
    pool_vibe = mp.vibe_for(state)
    got = dense.grow_family_for_cut(state, pool_vibe, 12, None, engine="ltx095")
    fam = S.family_named("neon-noir", S.content_words(mp._story_words(state)))
    assert fam == S.family_of("moth")
    if got:
        assert got["family"] == fam and asked and asked[0][0] == pool_vibe
        assert all(S.family_of(n) == fam for n in asked[0][1])


def test_zero_knobs_reach_zero():
    assert beatfx.bloom_gain(0.0) == 0.0 and abs(beatfx.bloom_gain(1.0) - 1.6) < 1e-9 and abs(beatfx.bloom_gain(0.4) - 0.64) < 1e-9
    rng = np.random.default_rng(1)
    frame = rng.integers(0, 256, (72, 128, 3), dtype=np.uint8)
    still = beatfx.beat_fx(frame, kick=1.0, trans=1.0, punch=1.0, loud=1.0, beat_index=0, intensity=0.0, bloom=0.0)
    assert np.array_equal(still, frame)  # Intensity 0: no zoom, no edges, no bloom, no loudness ride
    moved = beatfx.beat_fx(frame, kick=1.0, trans=1.0, punch=1.0, loud=1.0, beat_index=0, intensity=1.0, bloom=1.0)
    assert not np.array_equal(moved, frame)


def test_auto_foreshadow_knows_the_originals_are_dark():
    assert F.mode_for("auto", "cosmic") == "trace" and F.mode_for("auto", "black") == "trace"
    assert F.mode_for("auto", "paper-summer") == "slices"


def test_the_estimate_counts_the_pool():
    duration, period = 238.8, 0.4
    beats = [round(i * period, 4) for i in range(int(duration / period))]
    with_pool = dense.plan_summary(duration, beats, "dense", "draft", pool=12)
    without = dense.plan_summary(duration, beats, "dense", "draft")
    assert with_pool["morphs"] == 11 and without["morphs"] > 11 and with_pool["shots"] == 11


def test_the_slices_grow_in_instead_of_popping():
    rng = np.random.default_rng(2)
    frame = rng.integers(0, 256, (64, 36, 3), dtype=np.uint8)
    target = np.full((64, 36, 3), 255, dtype=np.uint8)
    p = {"cap": 0.8, "slices": 8, "jitter": 0.0, "glow": 0.5}
    faint = F.treat(frame, target, "slices", 0.002, tint=(255, 255, 255), p=p, si=0, k=0, seed=1)
    strong = F.treat(frame, target, "slices", 0.8, tint=(255, 255, 255), p=p, si=0, k=0, seed=1)
    d_faint = float(np.abs(faint.astype(np.float32) - frame.astype(np.float32)).mean())
    d_strong = float(np.abs(strong.astype(np.float32) - frame.astype(np.float32)).mean())
    assert 0.0 < d_faint < 0.35 * d_strong
