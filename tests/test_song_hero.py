"""A hero object opens the main drop (docs/SONG.md): the main drop run's first shot lands on the hero of its look, the
first object your pins hold, else the vibe's card object (configs/vibe_heroes.json), else its first still; pinned into
that passage's chain, shown by no other passage, and in the record."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenoform import dense, morph_pass, pacing, song_plan, song_run, taste

ROOT = Path(__file__).resolve().parents[1]
FEATURES = json.loads((ROOT / "tests" / "fixtures" / "analyses" / "glitch-out.features.json").read_text(encoding="utf-8"))
AUDIO = ROOT / "examples" / "songs" / "glitch_out.mp3"
SHIPPED_TASTE = ROOT / "configs" / "taste.json"


@pytest.fixture(scope="module")
def drop() -> float:
    return dense.find_drop(AUDIO, FEATURES["beats"], FEATURES["duration"])


def _state(**extra) -> dict:
    state = {"vibe": "cosmic", "breathe": 1.0, "drop_mode": "auto", "quality_tier": "draft", "aspect": "16:9",
             "energy_preset": "dense", "seed": 2727, "audio_id": "song-glitch-out", "song": "Glitch Out",
             "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}, "morph_style": "auto",
             "morph_timing": "smooth", "effects": [], "dance_fx": "auto"}
    state.update(extra)
    return state


def _main_window(song: dict) -> dict:
    main = next(p for p in song["passages"] if p.get("main"))
    return song["windows"][main["windows"][0]]


def test_every_card_hero_is_a_still_of_its_vibes_library_the_taste_file_allows(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED_TASTE))
    heroes = song_plan.heroes()
    assert {"ferrofluid", "black", "cosmic", "liquid-gold", "neon-noir"} <= set(heroes)
    cat = morph_pass.catalogue()
    for vibe, h in heroes.items():
        rows = list(cat.get(morph_pass.vibe_for({"vibe": vibe})) or []) + list(cat.get(vibe) or [])
        row = next((r for r in rows if r.get("file") == h["still"]), None)
        assert row is not None and taste.usable([row]), vibe
        assert song_plan.hero_still(vibe)[0] == h["still"] and "card object" in song_plan.hero_still(vibe)[2]
    assert song_plan.hero_still("ferrofluid")[1] == "ferrofluid phoenix"


def test_a_vibe_with_no_card_hero_opens_on_its_first_still(monkeypatch, tmp_path):
    monkeypatch.setenv("XENO_HEROES", str(tmp_path / "none.json"))
    assert song_plan.heroes() == {}
    still, noun, why = song_plan.hero_still("cosmic")
    assert why == "the vibe's first still" and still.startswith("cosmic/") and noun


def test_the_main_drop_opens_on_the_vibes_card_object(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, song_id="abc12345", label="Glitch Out")
    w = _main_window(song)
    assert w["body"]["chain_pins"]["1"] == w["stills"][1] == "cosmic/078_radio_telescope.jpg"
    assert w["plan"]["shots"][0]["event"] == "drop"  # its first shot is the drop's hit, morphing from slot 0 into slot 1
    hero = song["hero"]
    assert hero["still"] == "cosmic/078_radio_telescope.jpg" and hero["noun"] == "radio telescope" and hero["slot"] == 1
    assert "card object" in hero["why"] and hero["window"] == w["index"] and song["passages"][hero["passage"]]["main"]
    others = [n for v in song["windows"] if v is not w for n in v["nouns"]]
    assert "radio telescope" not in others  # no other passage shows it
    rec = song_run.new(song, song_id="abc12345", body=_state(), audio_id="song-glitch-out", audio_path=AUDIO, label="Glitch Out")
    assert rec["hero"]["still"] == hero["still"] and song_run.view(rec)["hero"]["noun"] == "radio telescope"


def test_your_first_pin_is_the_hero_and_your_pins_keep_their_order(drop):
    files = [r["file"] for r in morph_pass.catalogue()["cosmic"] if r.get("file")]
    a, b = files[3], files[5]
    song = song_plan.plan(FEATURES, _state(chain_pins={"0": a, "2": b}), drop=drop, label="Glitch Out")
    w = _main_window(song)
    assert w["body"]["chain_pins"]["1"] == a and w["body"]["chain_pins"]["3"] == b  # moved along, in your order
    assert w["stills"][1] == a and w["stills"][3] == b
    assert song["hero"]["still"] == a and song["hero"]["why"] == "your first pinned object"
    late = song_plan.plan(FEATURES, _state(chain_pins={"4": a}), drop=drop, label="Glitch Out")
    assert _main_window(late)["stills"][1] == a  # a pin further on comes forward to the drop's first landing


def test_a_hero_under_the_taste_file_and_a_song_kept_to_one_vibe(drop, monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED_TASTE))
    song = song_plan.plan(FEATURES, _state(vibe="ferrofluid", song_vibes=1), drop=drop, label="Glitch Out")
    w = _main_window(song)
    assert w["stills"][1] == "ferrofluid/063_ferrofluid_phoenix.jpg" and song["hero"]["noun"] == "ferrofluid phoenix"
    assert all("ferrofluid phoenix" not in [n.strip().lower() for n in v["nouns"]] for v in song["windows"] if v is not w)


def test_the_hero_holds_a_bar_on_the_main_drops_opening_shot(drop):
    """The hero showed for a quarter of a second (1 Nov: the main drop opened on a two-beat shot): the main drop run
    opens on one shot of a whole bar, the one the hero lands on, its event, punch and stutter on its first beat, and
    the hot run's two-beat entry shots start from its second bar; no other window has such a shot."""
    song = song_plan.plan(FEATURES, _state(), drop=drop, song_id="abc12345", label="Glitch Out")
    shots = _main_window(song)["plan"]["shots"]
    bar = 4 * float(song["period"])
    first = shots[0]
    assert first.get("hero_bar") and first.get("event") == "drop"
    assert abs((first["end"] - first["start"]) - bar) < 0.1 * bar
    assert [fx["type"] for fx in first["effects"]] == ["punch", "stutter"] and first["effects"][0]["t"] == 0.0
    main = next(p for p in song["passages"] if p.get("main"))
    assert float(main["heat"]) >= pacing.ENTRY_HEAT  # Glitch Out's main run is hot: its second bar on the half bar
    assert all(abs((s["end"] - s["start"]) - bar / 2) < 0.2 * bar for s in shots[1:3])
    assert song["hero"]["hold_s"] == round(first["end"] - first["start"], 3)
    assert sum(1 for w in song["windows"] for s in w["plan"]["shots"] if s.get("hero_bar")) == 1
    clips = song_plan.whole(FEATURES, {**_state(), "morph_source": "clips"}, drop)  # a clips song has no hero to hold
    assert song_plan.clips_song({"morph_source": "clips"}) and not any(s.get("hero_bar") for s in clips["shots"])


def test_a_song_with_no_drop_run_has_no_hero(drop):
    passages = [{"index": 0, "role": "intro", "start": 0.0, "end": 10.0, "seconds": 10.0, "windows": [0]}]
    assert song_plan.place_hero({"passages": passages, "windows": [{"index": 0, "morphs": 3, "body": {}}]}) is None


def test_the_estimate_names_the_hero_for_the_desk():
    assert song_plan.hero_preview({"vibe": "black"})["still"] == "black/05_lotus_black_glass.jpg"
    assert song_plan.hero_preview({"vibe": "black", "chain_pins": {"2": "black/00_rose_black_glass.jpg"}})["why"] == "your first pinned object"
    app = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    facts = app.split("function songPlanFacts(")[1].split("\n}\n")[0]
    assert '"Hero"' in facts and "opens the main drop" in facts
