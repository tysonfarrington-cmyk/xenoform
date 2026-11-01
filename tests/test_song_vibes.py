"""Vibes per song (docs/SONG.md, Tys's word of 1 Nov: fourteen vibes is fine, and a song may use as few as one): the body
key song_vibes keeps a whole song to at most N vibes. Auto and All are the look a passage of before; 1 is the vibe you
chose over the whole song; 2 is yours on the main drop and the rest, one more drawn by taste for contrast on the other
drops; N shares the calm passages and the outro first and the drops last, the loved chains counting toward N. The
estimate does not change, a vibe's library lets objects come round only as it must, and the record keeps the choice."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from xenoform import dense, song_plan, song_run, taste

ROOT = Path(__file__).resolve().parents[1]
FEATURES = json.loads((ROOT / "examples" / "songs" / "glitch-out.features.json").read_text(encoding="utf-8"))
AUDIO = ROOT / "examples" / "songs" / "glitch_out.mp3"
SHIPPED_TASTE = ROOT / "configs" / "taste.json"
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def drop() -> float:
    return dense.find_drop(AUDIO, FEATURES["beats"], FEATURES["duration"])


@pytest.fixture()
def tasted(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED_TASTE))
    assert taste.active()


@pytest.fixture()
def no_chains(monkeypatch, tmp_path):
    monkeypatch.setenv("XENO_PRESETS", str(tmp_path / "none.json"))


def _state(**extra) -> dict:
    state = {"vibe": "cosmic", "breathe": 1.0, "drop_mode": "auto", "quality_tier": "draft", "aspect": "16:9",
             "energy_preset": "dense", "seed": 2727, "audio_id": "song-glitch-out", "song": "Glitch Out",
             "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}, "morph_style": "auto",
             "morph_timing": "smooth", "effects": [], "dance_fx": "auto"}
    state.update(extra)
    return state


def _passages(drop, **extra) -> list[dict]:
    return song_plan.plan(FEATURES, _state(**extra), drop=drop, pick=False)["passages"]


def test_the_key_reads_auto_all_or_a_count():
    assert song_plan.vibes_of({}) is None and song_plan.vibes_of({"song_vibes": "auto"}) is None
    assert song_plan.vibes_of({"song_vibes": "All"}) is None and song_plan.vibes_of({"song_vibes": "x"}) is None
    assert song_plan.vibes_of({"song_vibes": 2}) == 2 and song_plan.vibes_of({"song_vibes": "5"}) == 5
    assert song_plan.vibes_of({"song_vibes": "0"}) is None and song_plan.vibes_of({"song_vibes": -3}) == 1
    assert song_plan.vibes_choice({"song_vibes": "all"}) == "all" and song_plan.vibes_choice({}) == "auto"
    assert song_plan.vibes_choice({"song_vibes": "3"}) == 3
    assert song_plan.VIBES_CHOICES == ("auto", 1, 2, 3, 5, 8, "all")


def test_auto_and_all_are_the_look_a_passage_of_before(drop):
    """Auto (the default), All, and a count no smaller than the passages draw exactly the looks the song drew before."""
    passages = _passages(drop)
    before = song_plan._looks_each(passages, _state())
    for key in (None, "auto", "all", "14", 20):
        state = _state() if key is None else _state(song_vibes=key)
        assert song_plan.looks(passages, state) == before
    assert len({lk["vibe"] for lk in before}) == 14


def test_one_vibe_carries_the_whole_song(drop, no_chains):
    passages = _passages(drop)
    looks = song_plan.looks(passages, _state(song_vibes=1))
    assert {lk["vibe"] for lk in looks} == {"cosmic"} and len(looks) == len(passages)
    main = next(i for i, p in enumerate(passages) if p.get("main"))
    assert "main drop" in looks[main]["why"]
    assert all("carries the whole song" in lk["why"] for i, lk in enumerate(looks) if i != main)


def test_one_vibe_keeps_a_loved_chain_only_of_that_vibe(drop):
    """The loved chains count toward N: with one vibe only a chain of the vibe you chose may take a passage (the gold
    finale on the outro of a Liquid gold song); no other chain's vibe comes in."""
    from xenoform import presets

    gold = presets.get("gold-finale")
    passages = _passages(drop)
    looks = song_plan.looks(passages, _state(vibe=gold["vibe"], song_vibes=1))
    assert {lk["vibe"] for lk in looks} == {gold["vibe"]}
    assert looks[-1]["preset"] == "gold-finale" and passages[-1]["role"] == "outro"
    assert not any(lk["preset"] and lk["preset"] != "gold-finale" for lk in looks)


def test_two_vibes_are_yours_on_the_main_drop_and_the_rest_and_one_more_on_the_other_drops(drop, no_chains):
    passages = _passages(drop)
    looks = song_plan.looks(passages, _state(song_vibes=2))
    drops = [i for i, p in enumerate(passages) if p.get("drop_run") is not None and not p.get("main")]
    rest = [i for i in range(len(passages)) if i not in drops]
    assert len(drops) == 4 and all(looks[i]["vibe"] == "cosmic" for i in rest)
    other = {looks[i]["vibe"] for i in drops}
    assert len(other) == 1 and other != {"cosmic"}
    lead = min(drops, key=lambda i: song_plan._importance(passages).index(i))
    assert looks[lead]["why"] == "drawn by taste for contrast on the other drops"
    # the contrast: of the vibes that pull as hard toward a drop, the one sharing the fewest tags with yours
    from xenoform import vibes

    rows = {r["id"]: r for r in vibes.catalog()}
    pick = rows[next(iter(other))]
    assert song_plan.affinity(pick, "drop") == 1


def test_n_vibes_share_the_calm_passages_and_the_outro_first_and_the_drops_last(drop):
    passages = _passages(drop)
    kind = [song_plan._kind(p) for p in passages]
    for n in (8, 5, 3, 2, 1):
        groups = song_plan.share(passages, n)
        assert len(groups) <= n and sorted(i for g in groups for i in g) == list(range(len(passages)))
        main = next(i for i, p in enumerate(passages) if p.get("main"))
        assert main in groups[0]  # the vibe you chose, on the main drop
        drop_groups = [g for g in groups if any(kind[i] == "drop" for i in g)]
        if n >= 5:  # room for every drop's own look: no two drops share, the scenes already do
            assert all(sum(kind[i] == "drop" for i in g) == 1 for g in drop_groups)
            scenes = [i for i in range(len(passages)) if kind[i] == "scene"]
            assert len({next(k for k, g in enumerate(groups) if i in g) for i in scenes}) == 1
    # the cost order on a song of each kind: calm and the outro share before the intro, the builds after, drops last
    def p(i, role, start, heat=None, main=False):
        row = {"index": i, "role": role, "start": start, "end": start + 10.0, "seconds": 10.0, "morphs": 4}
        if heat is not None:
            row.update({"drop_run": i, "heat": heat})
        if main:
            row["main"] = True
        return row

    song = [p(0, "intro", 0), p(1, "calm", 10), p(2, "build", 20), p(3, "drop", 30, 1.0, True), p(4, "calm", 40),
            p(5, "build", 50), p(6, "drop", 60, 0.6), p(7, "drop", 70, 0.9), p(8, "outro", 80)]
    groups = {n: sorted(map(sorted, song_plan.share(song, n))) for n in range(1, 10)}
    assert groups[9] == [[i] for i in range(9)]
    assert groups[8] == sorted([[3], [0], [1, 4], [8], [2], [5], [6], [7]])  # the two calm passages share first
    assert [1, 4, 8] in groups[7] and [0] in groups[7]  # then the outro joins them, before the intro does
    assert [0, 1, 4, 8] in groups[6] and [2] in groups[6] and [5] in groups[6]  # then the intro; the builds their own
    assert [2, 5] in groups[5] and [6] in groups[5] and [7] in groups[5]  # the builds share before any drop does
    assert [0, 1, 3, 4, 8] in groups[4] and [2, 5] in groups[4]  # the scenes take the vibe you chose
    assert song_plan.share(song, 3) == [[0, 1, 2, 3, 4, 5, 8], [7], [6]]  # then the builds; the drops their own
    assert song_plan.share(song, 2) == [[0, 1, 2, 3, 4, 5, 8], [6, 7]]  # the coolest drop shares the other's look
    assert song_plan.share(song, 1) == [list(range(9))]


def test_the_loved_chains_count_toward_n(drop):
    passages = _passages(drop)
    for n in (2, 3, 5):
        looks = song_plan.looks(passages, _state(song_vibes=n))
        assert len({lk["vibe"] for lk in looks}) <= n
        groups = Counter(lk["group"] for lk in looks)
        assert len(groups) <= n
        for g in groups:  # one vibe a group, a chain's included
            assert len({lk["vibe"] for lk in looks if lk["group"] == g}) == 1


def test_one_vibe_keeps_every_window_whole_and_lets_objects_come_round_only_as_it_must(drop, tasted):
    """One vibe's library is smaller than a whole song: the windows keep the morphs the pacing planned (the estimate's),
    no object twice inside a window, and the record names what came round again."""
    estimate = song_plan.plan(FEATURES, _state(song_vibes=1), drop=drop, pick=False)
    song = song_plan.plan(FEATURES, _state(song_vibes=1), drop=drop, label="Glitch Out")
    assert song["morphs"] == estimate["morphs"] == 78 and song["estimate"]["morphs"] == 78
    assert {p["look"]["vibe"] for p in song["passages"]} == {"cosmic"}
    for w in song["windows"]:
        nouns = [taste.words_of(n) for n in w["nouns"]]
        assert len(set(nouns)) == len(nouns) and len(w["body"]["chain_pins"]) == w["morphs"] + 1
        assert set(w.get("again") or []) <= {n.strip().lower() for n in w["nouns"]}
        assert song_plan.VIBES_KEY not in w["body"]
    assert song["vibes"]["choice"] == 1 and song["vibes"]["count"] == 1 and song["vibes"]["vibes"] == ["cosmic"]
    assert song["vibes"]["again"]  # cosmic's library holds fewer objects than the song shows
    seen = Counter(n for w in song["windows"] for n in {taste.words_of(x) for x in w["nouns"][1 if w["part"] else 0:]})
    assert max(seen.values()) <= 4  # spread: an object comes round as few times as the library makes it


def test_auto_never_lets_an_object_come_round(drop, tasted):
    song = song_plan.plan(FEATURES, _state(), drop=drop, label="Glitch Out")
    assert not any(w.get("again") for w in song["windows"]) and "again" not in song["vibes"]
    assert song["vibes"]["choice"] == "auto" and song["vibes"]["count"] == 14


def test_the_record_keeps_the_choice_and_the_estimate_does_not_change(drop):
    for n in ("auto", 1, 2):
        est = song_plan.plan(FEATURES, _state(song_vibes=n), drop=drop, pick=False)
        assert est["morphs"] == 78 and est["vibes"] == {"choice": n if n != "auto" else "auto"}
    song = song_plan.plan(FEATURES, _state(song_vibes=2), drop=drop, song_id="abc12345", label="Glitch Out")
    rec = song_run.new(song, song_id="abc12345", body=_state(song_vibes=2), audio_id="song-glitch-out", audio_path=AUDIO,
                       label="Glitch Out", beats=FEATURES["beats"])
    assert rec["vibes"]["choice"] == 2 and rec["vibes"]["count"] == 2 and rec["body"]["song_vibes"] == 2
    assert song_run.view(rec)["vibes"]["count"] == 2
    assert all(p["look"].get("group") in (0, 1) for p in rec["passages"])


def test_the_desk_has_a_vibes_control_under_whole_song():
    row = APP.split("function songVibesRow(")[1].split("\n}\n")[0]
    assert 'simpleSeg("easy-song-vibes", songVibesValue(easy), SONG_VIBES, "Vibes")' in row
    assert 'const SONG_VIBES = [["auto", "Auto"], ["1", "1"], ["2", "2"], ["3", "3"], ["5", "5"], ["8", "8"], ["all", "All"]];' in APP
    assert '${wholeSong(easy) && morphSource(easy) !== "clips" ? songVibesRow(easy) : ""}' in APP
    assert 'act === "easy-song-vibes"' in APP and '"songVibes"' in APP.split("const EASY_SAVED_KEYS = [")[1].split("];")[0]
    make = APP.split("async function easySongMake()")[1].split("\n}\n")[0]
    assert "body.song_vibes = songVibesValue(state.easy);" in make
    facts = APP.split("function songPlanFacts(")[1].split("\n}\n")[0]
    assert '"Vibes"' in facts
