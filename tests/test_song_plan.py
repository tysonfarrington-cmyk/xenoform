"""The whole song as passages (docs/MUSIC_VIDEO_PLAN.md section 7, docs/SONG.md): song_plan cuts Glitch Out into the
pacing engine's passages, each a window Make of at most 16 morphs on its tier whose budget is the profile table's, so the
song's total is the sum of its passages (the per-Make cap of 60 does not cap it); draws a look a passage by taste (no
vibe twice, the loved chains where they fit, the vibe you chose on the main drop) and picks the objects each window
morphs through (no object twice across passages, pinned); and a window Make plays its own stretch of the song plan."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from xenoform import dense, pacing, song_plan, taste

ROOT = Path(__file__).resolve().parents[1]
FEATURES = json.loads((ROOT / "examples" / "songs" / "glitch-out.features.json").read_text(encoding="utf-8"))
AUDIO = ROOT / "examples" / "songs" / "glitch_out.mp3"
SHIPPED_TASTE = ROOT / "configs" / "taste.json"


@pytest.fixture(scope="module")
def drop() -> float:
    return dense.find_drop(AUDIO, FEATURES["beats"], FEATURES["duration"])


@pytest.fixture()
def tasted(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED_TASTE))
    assert taste.active()


def _state(**extra) -> dict:
    state = {"vibe": "cosmic", "breathe": 1.0, "drop_mode": "auto", "quality_tier": "draft", "aspect": "16:9",
             "energy_preset": "dense", "seed": 2727, "audio_id": "song-glitch-out", "song": "Glitch Out",
             "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}, "morph_style": "auto",
             "morph_timing": "smooth", "effects": [], "dance_fx": "auto"}
    state.update(extra)
    return state


# ------------------------------------------------------------------------------------------------ the passages


def test_the_song_is_its_passages_and_the_per_make_cap_does_not_cap_it(drop):
    """Glitch Out whole: 14 passages (the pacing engine's own), each window at most 16 morphs, the total the sum of the
    windows; Breathe off plans 86 morphs, past the 60 one Make of the song may hold (dense.clip_plan's cap)."""
    for breathe, total in ((1.0, 78), (0.0, 86)):
        song = song_plan.plan(FEATURES, _state(breathe=breathe), drop=drop, pick=False)
        assert len(song["passages"]) == 14 and song["morphs"] == total
        assert song["morphs"] == sum(w["morphs"] for w in song["windows"]) == sum(p["morphs"] for p in song["passages"])
        assert all(1 <= w["morphs"] <= song_plan.PASSAGE_MAX for w in song["windows"])
    one_make = dense.clip_plan([{}] * 86, FEATURES["duration"], FEATURES["beats"], tier="draft")
    assert one_make["cap"] == 60 and song["morphs"] > one_make["cap"]
    roles = [p["role"] for p in song["passages"]]
    assert roles[0] == "intro" and roles[-1] == "outro" and roles.count("drop") == 5
    main = [p for p in song["passages"] if p.get("main")]
    assert len(main) == 1 and pacing.clock(main[0]["start"]) == "2:21" and main[0]["heat"] == 1.0
    assert song["line"] == "14 passages, 86 morphs; 5 drops, the main at 2:21"


def test_the_windows_tile_the_song_on_its_own_beats(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    wins = song["windows"]
    assert wins[0]["start"] == 0.0 and abs(wins[-1]["end"] - FEATURES["duration"]) < 1e-3
    for a, b in zip(wins, wins[1:]):
        assert abs(a["end"] - b["start"]) < 1e-3  # no gap and no overlap: the windows are the song
    beats = FEATURES["beats"]
    # every window after the beatless intro starts on one of the song's beats (or its tempo grid in a gap)
    grid = pacing.grid_for(beats, FEATURES["duration"], FEATURES["tempo"])
    assert all(min(abs(g - w["start"]) for g in grid) < 1e-3 for w in wins[1:])


def test_a_cap_spends_the_song_by_role_calm_first(drop):
    """song_morph_cap is the planner's budget for the whole song: a cap a little under the profile's count is taken from
    the calm passages and the drops keep every morph; a deep one squeezes everything, the planner's own order."""
    full = song_plan.plan(FEATURES, _state(breathe=0.0), drop=drop, pick=False)
    by = lambda song, roles: sum(p["morphs"] for p in song["passages"] if p["role"] in roles)  # noqa: E731
    mild = song_plan.plan(FEATURES, _state(breathe=0.0, song_morph_cap=80), drop=drop, pick=False)
    assert mild["morphs"] <= 80 < full["morphs"] and mild["cap"] == 80
    assert by(mild, ("drop",)) == by(full, ("drop",)) and by(mild, ("calm",)) < by(full, ("calm",))
    deep = song_plan.plan(FEATURES, _state(breathe=0.0, song_morph_cap=50), drop=drop, pick=False)
    assert deep["morphs"] <= 50 and len(deep["passages"]) == 14  # every passage keeps a shot
    assert song_plan.cap_of({"song_morph_cap": "auto"}) is None and song_plan.cap_of({"song_morph_cap": "40"}) == 40


def test_a_passage_past_the_tiers_cap_is_cut_on_a_bar_line(drop):
    """Final takes 12 morphs a Make (dense.MORPH_CAP): the two 13-morph drops become two windows each, cut where a shot
    starts on a bar line, and the song's total does not change."""
    assert song_plan.window_cap("draft") == 16 and song_plan.window_cap("cloud") == 16 and song_plan.window_cap("final") == 12
    draft = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    final = song_plan.plan(FEATURES, _state(quality_tier="final"), drop=drop, pick=False)
    assert final["morphs"] == draft["morphs"] and len(final["windows"]) == len(draft["windows"]) + 2
    assert all(w["morphs"] <= 12 for w in final["windows"])
    split = [w for w in final["windows"] if w["parts"] == 2]
    assert len(split) == 4 and {w["role"] for w in split} == {"drop"}
    full = song_plan.whole(FEATURES, _state(quality_tier="final"), drop)
    for w in split:
        if w["part"] == 1:
            assert song_plan._on_bar(w["start"], full["grid_times"], full["bar_phase"])


def test_each_window_carries_its_stretch_of_the_song_plan(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    full = song_plan.whole(FEATURES, _state(), drop)
    for w in song["windows"]:
        plan = w["plan"]
        shots = plan["shots"]
        assert shots[0]["start"] == 0.0 and abs(shots[-1]["end"] - w["length_s"]) < 1e-3 and "boundary" not in shots[0]
        assert len(shots) == w["morphs"] and all(s["passage"] == song["passages"][w["passage"]]["plan_passage"] for s in shots)
        song_shots = [s for s in full["shots"] if w["start"] - 1e-6 <= s["start"] < w["end"] - 1e-6]
        assert [round(s["end"] - s["start"], 3) for s in shots] == [round(s["end"] - s["start"], 3) for s in song_shots]
        assert all(s["start"] <= fx["t"] < s["end"] for s in shots for fx in s.get("effects") or [])
    main = next(w for w in song["windows"] if song["passages"][w["passage"]].get("main"))
    assert main["plan"]["drop"] == 0.0 and main["plan"]["shots"][0]["event"] == "drop"
    assert all(w["plan"]["drop"] is None for w in song["windows"] if w is not main)
    ramp = [w for w in song["windows"] if any(s.get("ramp") is not None for s in w["plan"]["shots"])]
    assert ramp and all(w["role"] == "build" for w in ramp)  # the builds ramp into the drop after their window ends


def test_each_window_knows_its_place_in_the_song(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    ctx = [w["context"] for w in song["windows"]]
    assert [c["opener"] for c in ctx].count(True) == 1 and ctx[0]["opener"]
    assert all(abs(c["first_drop"] - 91.958) < 0.01 for c in ctx)
    calm = [c for c in ctx if c["role"] == "calm"]
    assert [c["calm_seen"] for c in calm] == [0, 1]
    opens = [c["opens"] for c in ctx if c["opens"]]
    main = next(c for c in ctx if song["passages"][c["passage"]].get("main"))
    assert main["opens"] == "shatter" and len(opens) == 5 and set(opens) == {"shatter", "spin"}
    assert [c["turn"] for c in ctx] == list(range(14))


# ------------------------------------------------------------------------------------------------ the looks


def test_the_looks_take_the_loved_chains_where_they_fit_and_no_vibe_twice(drop, tasted):
    from xenoform import presets

    song = song_plan.plan(FEATURES, _state(), drop=drop, label="Glitch Out")
    looks = [p["look"] for p in song["passages"]]
    vibes = [lk["vibe"] for lk in looks]
    assert len(set(vibes)) == len(vibes) == 14  # no vibe twice in the song
    assert looks[0]["preset"] == "glow-sea" and looks[-1]["preset"] == "gold-finale"  # the opener, the finale
    main = next(p for p in song["passages"] if p.get("main"))
    assert main["look"]["vibe"] == "cosmic" and "main drop" in main["look"]["why"]
    loved = {p["id"]: p for p in presets.load()}
    for p in song["passages"]:
        if p["look"]["preset"]:
            assert song_plan.preset_fit(loved[p["look"]["preset"]], p["role"], 1.0) >= 2.0
    assert not any(taste.demoted_vibe(v) for v in vibes)  # wet paint and the pink odd-machine stay out


def test_a_preset_chosen_on_the_desk_goes_where_it_fits(drop):
    from xenoform import presets

    rose = presets.get("black-rose")
    state = _state(**presets.body(rose))
    looks = song_plan.looks(song_plan.plan(FEATURES, state, drop=drop, pick=False)["passages"], state)
    mine = [i for i, lk in enumerate(looks) if lk["preset"] == "black-rose"]
    assert len(mine) == 1 and looks[mine[0]]["why"] == "the loved chain you chose"
    assert song_plan.plan(FEATURES, state, drop=drop, pick=False)["passages"][mine[0]]["role"] in pacing.SCENE_ROLES


def test_the_fresh_vibes_lean_quiet_on_scenes_and_loud_on_drops():
    rows = {"ink": {"tags": ["ink", "paper", "calm"]}, "neon": {"tags": ["neon", "noir", "wet"]}}
    assert song_plan.affinity(rows["ink"], "calm") == 1 and song_plan.affinity(rows["ink"], "drop") == -1
    assert song_plan.affinity(rows["neon"], "drop") == 1 and song_plan.affinity(rows["neon"], "calm") == -1


def test_without_the_loved_chains_the_song_still_draws_one_look_a_passage(drop, monkeypatch, tmp_path):
    monkeypatch.setenv("XENO_PRESETS", str(tmp_path / "none.json"))
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    looks = song_plan.looks(song["passages"], _state())
    assert len(looks) == 14 and not any(lk["preset"] for lk in looks) and len({lk["vibe"] for lk in looks}) == 14


# ------------------------------------------------------------------------------------------------ the objects and bodies


def test_no_object_twice_across_passages_and_every_slot_pinned(drop, tasted):
    song = song_plan.plan(FEATURES, _state(quality_tier="final"), drop=drop, label="Glitch Out")
    seen: Counter = Counter()
    for w in song["windows"]:
        b = w["body"]
        assert len(b["chain_pins"]) == w["morphs"] + 1 == len(w["stills"])
        nouns = [taste.words_of(n) for n in w["nouns"]]
        assert len(set(nouns)) == len(nouns)  # none twice inside a window
        mine = nouns[1:] if w["part"] else nouns  # a passage's second window opens on the still the first landed on
        seen.update(set(mine))
        if w["part"]:
            assert w["stills"][0] == song["windows"][w["index"] - 1]["stills"][-1]
        assert not set(nouns[1 if w["part"] else 0:]) & set(b["avoid_nouns"])
    assert [n for n, k in seen.items() if k > 1] == []


def test_the_window_bodies_are_exact_draft_objects_cuts(drop):
    song = song_plan.plan(FEATURES, _state(end_card=True, performer=2, length_s=30, morph_count=24, auto_grow=True,
                                          morph_source="objects", own_clips=[{"path": "x.mp4"}]),
                          drop=drop, song_id="abc12345", label="Glitch Out")
    for w in song["windows"]:
        b = w["body"]
        assert b["length_start"] == w["start"] and b["length_s"] == w["length_s"] and b["length_exact"] is True
        assert (b["energy_preset"], b["end_card"], b["performer"], b["auto_grow"], b["morph_count"]) == ("dense", False, 0, False, "auto")
        assert "own_clips" not in b and b["breathe"] == 1.0 and b["drop_mode"] == "auto"
        assert b[song_plan.KEY]["song"] == "abc12345" and b[song_plan.KEY]["plan"]["shots"]
        assert b["song"].startswith("Glitch Out · passage ")
    seeds = [w["body"]["seed"] for w in song["windows"] if not song["passages"][w["passage"]]["look"]["preset"]]
    assert len(set(seeds)) == len(seeds)


def test_clips_and_stems_are_not_a_whole_song(drop):
    with pytest.raises(song_plan.SongError):
        song_plan.plan(FEATURES, _state(morph_source="clips"), drop=drop)
    with pytest.raises(song_plan.SongError):
        song_plan.plan(FEATURES, _state(mode="stems", layers=[{"stem": "drums", "kind": "objects"}]), drop=drop)
    short = {**FEATURES, "duration": 15.0, "beats": [b for b in FEATURES["beats"] if b < 15.0]}
    with pytest.raises(song_plan.SongError):
        song_plan.plan(short, _state(), drop=None)


# ------------------------------------------------------------------------------------------------ the title and the estimate


def test_the_title_lands_on_the_last_hit_as_the_hand_made_video_had_it(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    assert song["title"] == {"text": "Xenoform", "at": 231.3333}  # the montage's plan put it at 231.33
    assert song_plan.title_of({"song_title": ""}) == "" and song_plan.title_of({"song_title": "Glitch Out"}) == "Glitch Out"


def test_the_estimate_says_the_morphs_the_minutes_and_what_cloud_would_cost(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    est = song["estimate"]
    assert est["morphs"] == 78 and set(est["tiers"]) == set(song_plan.TIERS)
    draft, final, cloud = est["tiers"]["draft"], est["tiers"]["final"], est["tiers"]["cloud"]
    assert 20 < draft["minutes"] < final["minutes"] and not draft["measured"]
    assert cloud["credits"] == [round(78 * 3.6), round(78 * 6.0)]
    measured = song_plan.estimate({**song, "beats": FEATURES["beats"]}, rates={"draft": {"per_s": 10.0}})
    assert measured["tiers"]["draft"]["measured"] and measured["tiers"]["draft"]["seconds"] >= 2388


# ------------------------------------------------------------------------------------------------ the window Make


def test_a_window_make_plays_its_stretch_of_the_song_plan(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    w = song["windows"][0]  # the intro, 7 s: under dense.LONG_SONG_S, still the song's passage
    body = {**_state(), song_plan.KEY: {**w["context"], "plan": w["plan"]}}
    directed = song_plan.directed_for(FEATURES, w)
    assert directed["duration"] < dense.LONG_SONG_S
    assert dense.paced(body, directed) and dense.long_cut(body, directed["duration"])
    shots, plan = dense.shots_for(body, {**directed, "duration": directed["duration"] - 0.02}, None)
    assert plan["song"] and len(shots) == w["morphs"] and abs(shots[-1]["end"] - (w["length_s"] - 0.02)) < 1e-3
    assert shots[0].get("passage") is not None and shots[0]["section"] == "intro"
    assert not dense.paced(_state(), directed) and not dense.long_cut(_state(), directed["duration"])


def test_the_song_context_shapes_a_window_as_the_songs_passage(drop):
    """Before the song's first drop no flash look; after it, the look as chosen; a window that is not the opener takes no
    opener; a drop run opens on the style the song gives it."""
    song = song_plan.plan(FEATURES, _state(), drop=drop, pick=False)
    by_role = {}
    for w in song["windows"]:
        by_role.setdefault(w["role"], []).append(w)
    early, late = by_role["build"][0], by_role["build"][-1]

    def shaped(w, look="cyan-flash"):
        import copy

        shots = copy.deepcopy(w["plan"]["shots"])
        ctx = {**w["context"]}
        pacing.shape(shots, {"chaos": 0.3, "intensity": 0.5}, breathe=1.0, drop_mode="auto", look=look, look_auto=True,
                     beats=directed_beats(w), song=ctx)
        return shots

    def directed_beats(w):
        return song_plan.directed_for(FEATURES, w)["beats"]

    assert all(s.get("dance_fx") == pacing.CALM_LOOK for s in shaped(early))  # 0:55, before the first drop at 1:32
    assert not any(s.get("dance_fx") for s in shaped(late))  # 2:50, after it
    spin = next(w for w in song["windows"] if w["context"]["opens"] == "spin")
    state = {**_state(), song_plan.KEY: spin["context"]}
    styles = pacing.styles(spin["plan"]["shots"], state, spin["plan"]["drop"], period=spin["plan"]["period"])
    assert styles[0] == "spin"
