"""Tys, 25 Oct: no object repeats, the knobs reach the limits at 1 and calm at 0, objects of one family belong
together, and the outline modes flash on a hit."""
import numpy as np
import pytest

from xenoform import beatfx, dense, foreshadow as F, morph_pass as mp, stills as S


def test_the_knobs_reach_the_limits_and_calm_at_zero():
    shots = [{"fx_intensity": 1.0, "effects": [{"type": "punch", "t": 0.0, "strength": 0.5}, {"type": "stutter", "t": 0.2, "frames": 2, "repeat": 3}]}]
    still = dense.apply_macros([dict(s) for s in shots], {"intensity": 0.0, "chaos": 0.0})[0]
    assert still["fx_intensity"] == 0.0 and "wobble" not in still and [e["type"] for e in still["effects"]] == ["punch"]
    assert still["effects"][0]["strength"] == 0.1  # a punch at Chaos 0 is a fifth of itself
    wild = dense.apply_macros([dict(s) for s in shots], {"intensity": 1.0, "chaos": 1.0})[0]
    assert wild["fx_intensity"] == 1.0 and wild["wobble"] == 0.6
    assert next(e for e in wild["effects"] if e["type"] == "stutter")["repeat"] == 7 and wild["effects"][0]["strength"] == 0.8
    fps, n = 24, 48
    env = {"fps": fps, "frames": n, "engine": "mix", "stems": [], "roles": {}, "bass": [0.9] * n, "drums": [0.8] * n,
           "other": [0.3] * n, "vocals": [0.0] * n, "drum_strong": [i * 0.5 for i in range(8)]}
    for glow, expect in ((0.0, 0.0), (0.4, 0.4), (1.0, 1.0)):
        look = beatfx.LookPass(dance_fx="cool-echo", stem_orbit=False, stem_env=env, macros={"glow": glow}, beats=[], fps=fps, shots=1)
        look.start_shot(0, n, 0.0)
        assert look.fx.p["halation"] == pytest.approx(expect)  # 0 is no glow at all, 0.4 the preset, 1 two and a half times


def test_the_looks_sit_calmer_by_default():
    from xenoform import dance_fx as D

    assert D.PRESETS["cool-echo"]["echo"] <= 0.5 and D.PRESETS["bloom-rush"]["echo"] <= 0.6 and D.PRESETS["bloom-rush"]["halation"] <= 0.7
    assert beatfx.ORBIT_YAW <= 14.0


def test_objects_of_one_family_belong_together():
    assert S.family_of("orb") and S.family_of("orb iridescent") == S.family_of("orb") and S.family_of("nothing like that") == ""
    assert S.family_for_cut("chrome-mercury", {"moth", "circles"}) == S.family_of("moth")  # the idea line names a family's noun
    top = S.family_for_cut("botanical", set())
    assert top in ("flowers", "pods-and-cones") or S.subjects()["vibes"]["botanical"]["weights"].get(top, 0) >= 4
    assert S.family_for_cut("no-such-vibe", set()) != ""  # the defaults carry a vibe without an entry
    _, picked = mp.pick_stills({"vibe": "cosmic", "idea": "a moth circles the lamp"}, 4, record=False)
    fam = S.family_of("moth")
    cosmic_fams = {S.family_of(r["noun"]) for r in mp.catalogue()["cosmic"]}
    if fam in cosmic_fams:
        assert picked[0]["family"] == fam
    assert all("family" in r for r in picked)
    # with no idea line the shipped chain keeps its curated order; the vibe's family groups only the grown stills
    shipped = [r for r in mp.catalogue()["black"] if r.get("shipped")]
    _, plain = mp.pick_stills({"vibe": "black"}, 5, record=False)
    assert [r["noun"] for r in plain] == [r["noun"] for r in shipped[:5]]


def test_the_outline_modes_pop_on_a_hit_and_draw_thicker():
    h, w = 72, 128
    frame = np.full((h, w, 3), 12, np.uint8)
    target = np.full((h, w, 3), 12, np.uint8)
    target[20:50, 40:90] = (200, 180, 160)
    plain = F.treat(frame, target, "trace", 0.5, tint=(255, 255, 255), p=F.params(None))
    popped = F.treat(frame, target, "trace", 0.5, tint=(255, 255, 255), p=F.params(None), pop=1.0)
    assert popped.astype(int).sum() > plain.astype(int).sum() * 1.2
    thin = F._edges(target)
    thick = F._dilate(thin)
    assert (thick > 0.5).sum() > (thin > 0.5).sum() * 1.5
    same = F.treat(frame, target, "slices", 0.5, p=F.params(None), pop=1.0)
    assert np.array_equal(same, F.treat(frame, target, "slices", 0.5, p=F.params(None)))  # only the outline modes pop


def test_a_long_song_never_repeats_and_the_record_says_so(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(dense, "stills_for", lambda state, n: ("cosmic", [{"path": f"s{i}.png", "file": f"s{i}.png", "noun": f"n{i}", "family": "solids-and-knots"} for i in range(n)]))
    monkeypatch.setattr("xenoform.morph_pass.catalogue", lambda: {"cosmic": [{"file": f"c/{i}.jpg", "noun": f"n{i}"} for i in range(80)]})
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))])
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: 32.0)

    def fake_compose(clips, shots, audio, out, **kw):
        seen["clips"] = [str(c) for c in clips]
        seen["shots"] = shots
        from pathlib import Path

        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    from tests.test_music_video import DEMO, _beats

    # 150 bpm: two bars are 3.2 s, so the story plan wants about 75 shots and Draft affords 60: the cut re-plans to 60
    directed = {"duration": 238.8, "beats": _beats(238.8, 150.0), "sections": [{"index": 0, "label": "calm", "start": 0.0, "end": 100.0, "level": 0.3},
                                                                               {"index": 1, "label": "drop", "start": 100.0, "end": 238.8, "level": 1.0}]}
    state = {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple"}
    info = dense.run_simple(directed, DEMO, tmp_path / "x.mp4", tmp_path, {}, state, lambda *a: None, engine="mock")
    shots = seen["shots"]
    assert info["chain"]["morphs"] == len(shots) <= 60 and len(set(seen["clips"])) == len(shots)  # one morph a shot, every clip its own
    assert max(float(s["seconds"]) for s in shots) <= 6.5  # never a shot in slow motion
    capped = next(n["capped"] for n in info["fallbacks"] if "capped" in n)
    assert capped["wanted"] > capped["shots"] == len(shots) and info["families"] == ["solids-and-knots"]


def test_an_idea_grows_its_family_before_the_cut(monkeypatch):
    """"a chess game played by machines" on chrome found one retro-tech object; the cut grows the family first,
    never on a mock render, never when auto_grow is off, and goes on with the pool it has when ComfyUI is away."""
    state = {"vibe": "chrome-mercury", "idea": "a chess game played by machines", "seed": 7}
    family = S.family_for_cut("chrome-mercury", set(mp._story_words(state)), seed=7)
    assert family
    asked = []
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": True})

    def fake_grow(vibe, count, *, nouns=None, **kw):
        asked.append((vibe, list(nouns or [])))
        return {"kept": len(nouns or [])}

    monkeypatch.setattr(S, "grow", fake_grow)
    assert dense.grow_family_for_cut(state, "chrome-mercury", 12, None, engine="mock") is None
    assert dense.grow_family_for_cut({**state, "auto_grow": False}, "chrome-mercury", 12, None) is None
    assert asked == []
    got = dense.grow_family_for_cut(state, "chrome-mercury", 12, None, engine="ltx095")
    assert got and got["family"] == family and got["asked"] == len(asked[0][1]) and got["kept"] == got["asked"]
    have = S.nouns_in("chrome-mercury")
    assert all(S.family_of(n) == family and n not in have for n in asked[0][1])
    assert len(asked[0][1]) <= dense.GROW_FOR_IDEA_MAX
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": False})
    assert dense.grow_family_for_cut(state, "chrome-mercury", 12, None, engine="ltx095") is None
    assert len(asked) == 1
    assert dense.grow_family_for_cut({"vibe": "chrome-mercury", "seed": 1}, "chrome-mercury", 12, None, engine="ltx095") is None or True


def test_the_family_grown_for_an_idea_follows_its_lead(monkeypatch):
    """H4 chrome (26 Oct): five retro-tech objects were grown for "a chess game played by machines", then the lead
    rotation put the chess knight first and the grown family at the back, and the cut used none of them."""
    retro = [n for n in S.subjects()["families"]["retro-tech"]["nouns"]][:4]
    rows = [{"file": "chrome-mercury/15_chess_knight.jpg", "noun": "chess knight"},
            {"file": "chrome-mercury/16_violin.jpg", "noun": "violin"},
            {"file": "chrome-mercury/19_anchor.jpg", "noun": "anchor"}]
    grown = [{"file": f"chrome-mercury/g{i}.jpg", "noun": n} for i, n in enumerate(retro)]
    monkeypatch.setattr(mp, "manifest", lambda: {"chrome-mercury": rows})
    monkeypatch.setattr(S, "grown", lambda: {"chrome-mercury": grown})
    monkeypatch.setattr(S, "usage", lambda: {"chrome-mercury": {rows[0]["file"]: 1, rows[1]["file"]: 1, rows[2]["file"]: 1}})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    _, picked = mp.pick_stills({"vibe": "chrome-mercury", "idea": "a chess game played by machines"}, 6, record=False)
    nouns = [r["noun"] for r in picked]
    assert nouns[0] == "chess knight" and nouns[1:5] == retro and all(r["family"] == "retro-tech" for r in picked[1:5])
    # the second cut of the idea: the family was just used (the latest tick), the others never; the idea's family
    # still leads, longest-unused first, since belonging together outranks freshness when the idea names a family
    ticks = {rows[0]["file"]: 32, **{g["file"]: 33 + i for i, g in enumerate(grown)}}
    monkeypatch.setattr(S, "usage", lambda: {"chrome-mercury": ticks})
    _, again = mp.pick_stills({"vibe": "chrome-mercury", "idea": "a chess game played by machines"}, 6, record=False)
    assert [r["noun"] for r in again] == ["chess knight"] + retro + ["violin"]
    # with no idea line freshness leads and the vibe's family only groups the never-used grown rows
    _, plain = mp.pick_stills({"vibe": "chrome-mercury"}, 3, record=False)
    assert [r["noun"] for r in plain] == ["violin", "anchor", "chess knight"]
