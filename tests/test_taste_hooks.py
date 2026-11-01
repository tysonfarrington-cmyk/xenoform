"""The taste file at the hooks (docs/MUSIC_VIDEO_PLAN.md section 4): the guardrail every Make body passes, the pick (bans
before the walk, the pins and typed shapes kept, natural and iconic first, no object twice, the musical run, the demoted
stills, one palette), the kind pickers (the handoff kinds, the looks before the first drop, the effects one at a time,
the premium transitions, the house look's opening flash), the foreshadow, the knobs, and the re-cut through the same
helpers. With the file absent every hook is as it was (tests/test_taste_absent.py holds the mainline's cut to that)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from xenoform import batch, beatfx, boundary_fx as B, dense, guardrails, morph_pass as mp, pacing, stills, taste
from xenoform import transitions_fx as T

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "configs" / "taste.json"


@pytest.fixture()
def shipped(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    assert taste.active()


def _messages(body: dict, **kw) -> tuple[dict, list[str]]:
    clean, rep = guardrails.apply(body, **kw)
    return clean, [m for m in rep["messages"] if m.startswith("[taste]")]


# ------------------------------------------------------------------------------------------------ the guardrail


def test_the_guardrail_caps_chaos_under_breathe_and_says_so(shipped):
    clean, lines = _messages({"breathe": True, "macros": {"chaos": 0.9, "intensity": 0.5}})
    assert clean["macros"]["chaos"] == 0.5
    assert any("breathe-chaos-cap" in m and "0.90" in m for m in lines)
    clean, lines = _messages({"breathe": False, "macros": {"chaos": 0.9}})
    assert clean["macros"]["chaos"] == 0.9 and not any("breathe-chaos-cap" in m for m in lines)
    clean, rep = guardrails.apply({"breathe": True, "macros": {"chaos": 0.9}, "expert": True})
    assert clean["macros"]["chaos"] == 0.9 and any("breathe-chaos-cap" in w["message"] for w in rep["warnings"])


def test_the_guardrail_turns_slices_into_trace(shipped):
    clean, lines = _messages({"foreshadow": "slices"})
    assert clean["foreshadow"] == "trace" and any("no-slices" in m for m in lines)


def test_clips_and_objects_never_share_a_make_even_under_expert(shipped):
    clean, lines = _messages({"own_clips": [{"path": "a.mp4"}], "expert": True})
    assert clean["own_clips"] == [] and any("clips-or-objects" in m for m in lines)
    clean, lines = _messages({"morph_source": "clips", "morph_targets": ["a.png"], "chain_pins": {"0": "none/00_orb.jpg"},
                              "own_clips": [{"path": str(ROOT / "work" / "ui" / "film_pack" / "01_metropolis_robot.mp4")}]})
    assert clean["morph_targets"] == [] and clean["chain_pins"] == {}
    assert any("clips-or-objects" in m for m in lines) and any("no-film-clips" in m for m in lines)


def test_in_stems_mode_the_rule_holds_within_a_layer(shipped):
    # decision 10 (31 Oct): an objects layer and a clips layer may overlap; the layers are their own Makes
    body = {"mode": "stems", "own_clips": [{"path": "a.mp4"}], "chain_pins": {"0": "none/00_orb.jpg"},
            "layers": [{"stem": "drums", "kind": "objects"}, {"stem": "other", "kind": "clips"}]}
    clean, lines = _messages(body)
    assert clean["own_clips"] == [{"path": "a.mp4"}] and clean["chain_pins"] == {"0": "none/00_orb.jpg"}
    assert not any("clips-or-objects" in m for m in lines)
    assert taste.rule("clips-or-objects")["stems"] == "within a layer"


def test_the_guardrail_notes_what_the_make_will_do(shipped):
    _, lines = _messages({"vibe": "wet-paint", "macros": {"intensity": 0.9}, "dance_fx": "cyan-flash",
                          "effects": ["dither", "kaleido"], "idea": "a teacup and a ship wheel"})
    text = " ".join(lines)
    for rid in ("wet-paint-weak", "quiet-opener", "no-flash-before-drop", "one-effect", "no-kaleido-on-living",
                "no-cups-or-jugs", "no-wheels"):
        assert rid in text, rid


def test_with_no_taste_file_the_guardrail_is_as_it_was():
    body = {"breathe": True, "macros": {"chaos": 0.9}, "foreshadow": "slices", "own_clips": [{"path": "a.mp4"}],
            "vibe": "wet-paint", "effects": ["dither", "kaleido"]}
    clean, rep = guardrails.apply(copy.deepcopy(body))
    assert not any(m.startswith("[taste]") for m in rep["messages"])
    assert clean["macros"]["chaos"] == 0.9 and clean["foreshadow"] == "slices" and clean["own_clips"] == [{"path": "a.mp4"}]


def test_breathe_stays_off_by_default(shipped):
    assert pacing.BREATHE_DEFAULT is False
    clean, _ = guardrails.apply({"vibe": "none"})
    assert "breathe" not in clean and pacing.breathe_of(clean) is False


# ------------------------------------------------------------------------------------------------ the pick


def _nouns(picked: list[dict]) -> list[str]:
    return [str(r.get("noun") or "") for r in picked]


def test_the_pick_leaves_out_what_the_taste_file_bans(shipped):
    with taste.collecting() as got:
        _, picked = mp.pick_stills({"vibe": "liquid-gold", "seed": 2727}, 39, record=False)
    nouns = _nouns(picked)
    assert len(set(nouns)) == len(nouns) == 39
    assert all(taste.ban_for(n) is None for n in nouns), nouns
    assert not {"dna helix", "wine glass"} & set(nouns)
    # the horn rule reads the head: the dragon skull with curling horns is a skull, not a horn, and stays in the pool
    assert taste.ban_for("dragon skull with curling horns") is None and taste.ban_for("ram golden horn") is not None
    line = " ".join(taste.lines(got))
    assert "no-black-heart-or-dna" in line and "no-vessels-family" in line


def test_without_the_file_the_pick_still_takes_them(monkeypatch):
    _, picked = mp.pick_stills({"vibe": "cosmic", "seed": 2727}, 12, record=False)
    assert "dna helix" in _nouns(picked)  # the curated shipped chain, as it was
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    _, tasted = mp.pick_stills({"vibe": "cosmic", "seed": 2727}, 12, record=False)
    assert "dna helix" not in _nouns(tasted)
    assert set(_nouns(picked)) - {"dna helix"} < set(_nouns(tasted))  # the rest of the chain stays, one more still after it
    assert _nouns(tasted)[:6] == _nouns(picked)[:6]  # and it opens as it did (the autotune's bad pairs reorder the tail)


def test_what_you_type_or_pin_stays_yours(shipped):
    _, picked = mp.pick_stills({"vibe": "liquid-gold", "idea": "a wine glass", "seed": 1}, 8, record=False)
    assert "wine glass" in _nouns(picked)
    _, pinned = mp.pick_stills({"vibe": "liquid-gold", "chain_pins": {"0": "liquid-gold/05_dna_helix_chrome.jpg"}}, 6, record=False)
    assert pinned[0]["noun"] == "dna helix" and pinned[0]["pinned"]
    assert "dna helix" not in _nouns(pinned[1:])


def test_no_object_twice_counts_two_stills_of_one_object(shipped):
    rows = [r for r in mp.catalogue()["none"]]
    assert sum(1 for r in rows if r["noun"] == "seahorse") == 2  # the shipped None pool holds the seahorse twice
    _, picked = mp.pick_stills({"vibe": "none", "seed": 2727}, len(rows) - 1, record=False)
    assert _nouns(picked).count("seahorse") == 1
    assert taste.distinct([{"path": "a", "noun": "seahorse"}, {"path": "b", "noun": "seahorse"}]) == 1


def _grown(tmp_path: Path, vibe: str, nouns: list[str], colour=(120, 120, 120)) -> list[dict]:
    folder = tmp_path / vibe
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, noun in enumerate(nouns):
        path = folder / f"{k:03d}_{noun.replace(' ', '_')}.jpg"
        im = Image.new("RGB", (160, 90), (8, 8, 8))
        im.paste(Image.new("RGB", (60, 50), colour if not isinstance(colour, list) else colour[k]), (50, 20))
        im.save(path, quality=90)
        rows.append({"file": f"{vibe}/{path.name}", "noun": noun, "path": str(path), "shipped": False})
    return rows


@pytest.fixture()
def crafted(tmp_path, monkeypatch):
    """A made-up vibe's library (``testvibe``, no registry palette), the pick reading it alone, nothing used yet."""
    cat: dict[str, list[dict]] = {}
    monkeypatch.setattr(mp, "catalogue", lambda: cat)
    monkeypatch.setattr(stills, "usage", lambda: {})

    def fill(vibe: str, nouns: list[str], colour=(120, 120, 120)) -> list[dict]:
        cat[vibe] = _grown(tmp_path, vibe, nouns, colour)
        return cat[vibe]

    return fill


SEA = ["jellyfish", "koi", "manta ray", "seahorse", "octopus", "starfish", "sea turtle", "pufferfish", "anglerfish",
       "cuttlefish", "sea anemone", "betta fish", "nudibranch", "squid", "lobster", "humpback whale", "axolotl", "nautilus",
       "conch", "sea urchin", "scallop shell", "sand dollar"]
MACHINES = ["turbine", "propeller", "piston", "crankshaft", "coil spring", "ball bearing", "pulley", "chain link",
            "hex bolt", "spark plug", "jet engine", "drill bit", "clockwork movement", "electric motor", "anvil", "typewriter",
            "boombox", "speaker cone", "cassette tape", "joystick", "game controller", "crt monitor"]


def test_a_cut_with_no_line_draws_on_natural_families_first(shipped, crafted):
    crafted("testvibe", MACHINES + SEA)
    for seed in range(6):  # with no taste file the realm turns with the seed; with it the creatures come first every time
        with taste.collecting() as got:
            _, picked = mp.pick_stills({"vibe": "testvibe", "seed": seed}, 12, record=False)
        assert all(stills.realm_of(stills.family_of(n)) == "creatures" for n in _nouns(picked)), (seed, _nouns(picked))
        assert any("natural-first" in line for line in taste.lines(got))


def test_without_the_file_the_realm_still_turns_with_the_seed(crafted):
    crafted("testvibe", MACHINES + SEA)
    realms = set()
    for seed in range(6):
        _, picked = mp.pick_stills({"vibe": "testvibe", "seed": seed}, 12, record=False)
        realms.add(stills.realm_of(stills.family_of(picked[0]["noun"])))
    assert realms == {"creatures", "machines"}


def test_a_realm_too_small_walks_on_rather_than_repeat(shipped, crafted):
    crafted("testvibe", MACHINES + SEA)
    with taste.collecting() as got:
        _, picked = mp.pick_stills({"vibe": "testvibe", "seed": 0}, 40, record=False)
    nouns = _nouns(picked)
    assert len(set(nouns)) == len(nouns) == 40
    assert nouns[:22] and all(stills.realm_of(stills.family_of(n)) == "creatures" for n in nouns[:22])
    assert any("walks on" in line for line in taste.lines(got))


# with MACHINES, the machines' realm a test library leans on: 39 stills, none banned, none of them an instrument
MORE_MACHINES = ["hourglass", "pocket watch", "gyroscope", "compass", "sextant", "astrolabe", "telescope", "jukebox",
                 "steam locomotive", "gear", "rotary telephone", "vacuum tube", "transistor radio", "theodolite", "tesla coil",
                 "carburettor", "difference engine"]


def _realm(noun: str) -> str:
    return stills.realm_of(stills.family_of(noun))


def test_a_default_cut_never_laps_a_realm_smaller_than_its_chain(shipped, crafted):
    # the stems builder's case (31 Oct): no line, a pool of 40, the realm the pick lands on holds 9 stills and a default
    # ten-morph cut wants 11 (the mainline walked the 9 again: the orb and the mobius twice)
    rows = crafted("testvibe", SEA[:9] + MACHINES + MORE_MACHINES)
    assert len(rows) >= stills.REALM_LIBRARY and all(_realm(n) in ("creatures", "machines") for n in SEA[:9] + MORE_MACHINES)
    for seed in range(6):
        with taste.collecting() as got:
            _, picked = mp.pick_stills({"vibe": "testvibe", "seed": seed}, 11, record=False)
        nouns = _nouns(picked)
        assert len(set(nouns)) == len(nouns) == 11, (seed, nouns)
        assert all(_realm(n) == "creatures" for n in nouns[:9]) and all(_realm(n) == "machines" for n in nouns[9:]), nouns
        assert any("the creatures realm holds 9 different objects, fewer than the cut's 11" in line
                   for line in taste.lines(got)), taste.lines(got)


def test_a_second_still_of_one_object_does_not_fill_a_realm_out(shipped, crafted):
    # 11 stills in the creatures realm, the jellyfish twice: 10 objects for an 11-still cut, so it walks on
    crafted("testvibe", SEA[:10] + ["jellyfish"] + MACHINES + MORE_MACHINES)
    with taste.collecting() as got:
        _, picked = mp.pick_stills({"vibe": "testvibe", "seed": 0}, 11, record=False)
    nouns = _nouns(picked)
    assert len(set(nouns)) == len(nouns) == 11, nouns
    assert nouns.count("jellyfish") == 1 and _realm(nouns[-1]) == "machines"
    assert any("holds 10 different objects" in line for line in taste.lines(got))


DARK = ["staircase looping into itself", "snail with a castle shell", "moon in a birdcage", "chess knight made of smoke",
        "fish made of keys", "enchanted rose under glass", "runed elven crown", "jewelled dragon egg",
        "dragon claw holding a gem", "crystal orb on a claw stand"]


def test_the_bans_come_before_the_realm_is_chosen(shipped, crafted):
    # the bioluminescent case (31 Oct): its default pick reached the DNA helix. Here the DNA helix and the anatomical
    # heart open the dark fantasy realm the natural-first weight draws on; neither is ever picked, and nothing repeats
    crafted("testvibe", ["dna helix", "anatomical heart"] + DARK + MACHINES + MORE_MACHINES)
    for seed in range(6):
        with taste.collecting() as got:
            _, picked = mp.pick_stills({"vibe": "testvibe", "seed": seed}, 11, record=False)
        nouns = _nouns(picked)
        assert not {"dna helix", "anatomical heart"} & set(nouns), (seed, nouns)
        assert len(set(nouns)) == len(nouns) == 11 and all(_realm(n) == "dark fantasy" for n in nouns[:10]), nouns
        line = " ".join(taste.lines(got))
        assert "no-black-heart-or-dna: dna helix, anatomical heart" in line
    # a realm only its banned stills would fill out to a cut's worth (8 with them, 6 without) never carries the cut: the
    # realm is chosen on the pool after the bans, so this cut is the machines' alone (counted before the bans, the dark
    # fantasy realm would fit and, weighing more, come first)
    rows = crafted("testvibe", ["dna helix", "anatomical heart"] + DARK[:6] + MACHINES + MORE_MACHINES)
    dark = [r for r in rows if _realm(r["noun"]) == "dark fantasy"]
    assert len(dark) == mp.THEME_CHAIN_MIN and taste.realm_weight(dark) >= taste.first_at()
    for seed in range(4):
        _, picked = mp.pick_stills({"vibe": "testvibe", "seed": seed}, 11, record=False)
        nouns = _nouns(picked)
        assert all(_realm(n) == "machines" for n in nouns) and len(set(nouns)) == 11, (seed, nouns)


@pytest.mark.parametrize("vibe", ["liquid-gold", "bioluminescent"])
def test_the_shipped_pools_default_picks_repeat_nothing_and_ban_nothing(shipped, vibe):
    for count in (11, 13, 21):
        for seed in range(8):
            _, picked = mp.pick_stills({"vibe": vibe, "seed": seed}, count, record=False)
            nouns = _nouns(picked)
            assert len(set(nouns)) == len(nouns) == count, (vibe, count, seed, nouns)
            assert not [n for n in nouns if taste.ban_for(n, stills.family_of(n))], (vibe, count, seed, nouns)


def test_one_instrument_a_cut_no_musical_run(shipped, crafted):
    crafted("testvibe", ["grand piano", "violin", "electric guitar", "cello", "jellyfish", "koi", "owl", "lotus", "orchid",
                         "nautilus", "conch", "moth"])
    _, picked = mp.pick_stills({"vibe": "testvibe"}, 8, record=False)
    assert sum(1 for n in _nouns(picked) if taste.run_for(n)) == 1


def test_plain_marble_chess_goes_to_the_back(shipped, crafted):
    crafted("porcelain-marble", ["chess king", "chess queen", "chess rook", "orb", "nautilus", "lotus", "feather", "conch",
                                 "butterfly", "moth"])
    _, picked = mp.pick_stills({"vibe": "porcelain-marble"}, 7, record=False)
    assert not any("chess" in n for n in _nouns(picked))
    _, more = mp.pick_stills({"vibe": "porcelain-marble"}, 10, record=False)
    assert [n for n in _nouns(more) if "chess" in n] == ["chess king", "chess queen", "chess rook"]  # kept, at the back


def test_one_palette_sends_an_off_colour_still_to_the_back(shipped, crafted):
    gold = (230, 170, 40)
    rows = crafted("testvibe", ["orb", "nautilus", "lotus", "feather", "conch", "moth", "butterfly", "koi"],
                   colour=[gold] * 4 + [(40, 90, 230)] + [gold] * 3)
    for r in rows[:4]:
        r["shipped"] = True  # the vibe's palette is read from its shipped stills
    with taste.collecting() as got:
        _, picked = mp.pick_stills({"vibe": "testvibe"}, 7, record=False)
    assert "conch" not in _nouns(picked)  # the blue one
    assert any("one-palette" in line for line in taste.lines(got))
    assert taste.palette_check("none", rows) is None  # None's natural colours: the rule steps aside


def test_the_pool_count_plans_fewer_morphs_when_the_bans_shrink_it(shipped):
    rows = mp.catalogue()["liquid-gold"]
    assert len(taste.usable(rows)) == len(rows) - 2  # the dna helix and the wine glass


def test_the_grow_never_grows_what_the_taste_file_bans(shipped):
    nouns = stills.nouns_for("none", 600)
    assert nouns and all(taste.noun_ok(n) for n in nouns)
    assert not set(stills.family_nouns("none", "vessels-and-tableware", 20))
    assert stills.family_for_cut("none", set()) != "vessels-and-tableware"


# ------------------------------------------------------------------------------------------------ the kind pickers


def _shots(n: int, *, drop_at: int | None = None, section: str = "", seconds: float = 2.0) -> list[dict]:
    out = []
    for i in range(n):
        s = {"index": i, "start": i * seconds, "end": (i + 1) * seconds, "seconds": seconds, "frames": int(seconds * 24),
             "effects": [], "fx_intensity": 1.0}
        if section:
            s["section"] = section
        if drop_at is not None and i == drop_at:
            s["boundary"] = "drop"
        out.append(s)
    return out


def test_the_kinds_keep_wipes_to_a_quarter_and_the_strobe_to_full_heat(shipped):
    shots = _shots(25, drop_at=12)
    beats = [i * 0.5 for i in range(120)]
    with taste.collecting() as got:
        picks = B.pick(shots, {"chaos": 0.95, "intensity": 0.8}, beats, 24, seed=3)
    kinds = [p["kind"] if p else None for p in picks]
    assert kinds.count("wipe") <= int(0.25 * 24)
    assert [i for i, k in enumerate(kinds) if k == "strobe"] == [12]  # the drop boundary alone is at full heat
    assert all(a != b for a, b in zip(kinds, kinds[1:]) if a and b)
    assert any("wipes-a-quarter" in line or "strobe-at-full-heat" in line for line in taste.lines(got))


def test_without_the_file_the_kinds_are_as_they_were():
    shots = _shots(25, drop_at=12)
    beats = [i * 0.5 for i in range(120)]
    kinds = [p["kind"] if p else None for p in B.pick(shots, {"chaos": 0.95, "intensity": 0.8}, beats, 24, seed=3)]
    assert kinds.count("strobe") > 1


def test_the_paced_picker_already_keeps_the_taste_files_numbers(shipped, monkeypatch):
    shots = _shots(20, section="drop")
    for s in shots:
        s.update({"drop_run": 0, "heat": 1.0, "passage": 0, "chaos": 0.9})
    shots[0]["boundary"] = "drop"
    beats = [i * 0.5 for i in range(100)]
    with_file = B.pick(shots, {"chaos": 0.9}, beats, 24, seed=1, paced={"breathe": False})
    monkeypatch.setenv("XENO_TASTE", str(ROOT / "no_such_taste.json"))
    without = B.pick(shots, {"chaos": 0.9}, beats, 24, seed=1, paced={"breathe": False})
    assert with_file == without


def test_a_premium_transition_never_follows_itself(shipped):
    kinds, msgs = T.guard(["match-cut", "match-cut", "flow-carry", "flow-carry"], seed=2)
    assert all(a != b for a, b in zip(kinds, kinds[1:]) if a not in T.EXEMPT_FROM_CAP)
    assert any("taste" in m for m in msgs)


def test_without_the_file_the_guard_is_as_it_was():
    kinds, msgs = T.guard(["match-cut", "match-cut", "flow-carry", "flow-carry"], seed=2)
    assert kinds == ["match-cut", "match-cut", "flow-carry", "flow-carry"] and not msgs


def test_a_flash_look_resolves_calm_before_the_first_drop(shipped):
    house = dense.house()
    assert beatfx.resolve_dance_preset("cyan-flash", "cosmic", house) == "cyan-flash"
    assert beatfx.resolve_dance_preset("cyan-flash", "cosmic", house, before_drop=True) == "cool-echo"
    assert beatfx.resolve_dance_preset("house", "cosmic", house, before_drop=True, index=0) == house["dance_fx"]["vj"]["preset"]
    assert beatfx.resolve_dance_preset("house", "cosmic", house, before_drop=True, index=3) == "house"
    assert beatfx.resolve_dance_preset("warm-leak", "cosmic", house, before_drop=True) == "warm-leak"


def test_the_shots_obey_the_opener_the_looks_and_the_effects(shipped):
    shots = _shots(10, drop_at=6)
    for s in shots:
        s["morph"] = s["index"]
    stills_rows = [{"noun": n} for n in ("orb", "torus knot", "cube", "mobius", "gem", "koi", "manta ray", "cube", "orb",
                                         "gem", "torus", "pearl")]
    state = {"breathe": False, "drop_mode": "off", "effects": ["dither", "kaleido"], "dance_fx": "cyan-flash", "vibe": "cosmic"}
    with taste.collecting() as got:
        dense.shape_shots(shots, state, {"intensity": 0.9, "chaos": 0.3}, None, look="cyan-flash", beats=[], stills=stills_rows,
                          house=dense.house(), drop=12.0)
    assert [s.get("dance_fx") for s in shots] == ["cool-echo"] * 6 + [None] * 4
    assert all(s["fx_intensity"] <= 0.96 + 1e-9 for s in shots[:6]) and shots[7]["fx_intensity"] == 1.0
    assert all(len(s["fx_names"]) <= 1 for s in shots)
    assert "kaleido" not in shots[4]["fx_names"] + shots[5]["fx_names"] + shots[6]["fx_names"]  # the koi and the manta ray
    fired = taste.fired(got)
    for rid in ("quiet-opener", "no-flash-before-drop", "one-effect", "no-kaleido-on-living"):
        assert rid in fired, rid


def test_without_the_file_the_shots_are_shaped_as_before():
    shots = _shots(10, drop_at=6)
    plain = copy.deepcopy(shots)
    state = {"breathe": False, "drop_mode": "off", "effects": ["dither", "kaleido"]}
    dense.shape_shots(shots, state, {"intensity": 0.9, "chaos": 0.3}, None, look="cyan-flash", beats=[], stills=[], drop=12.0)
    dense.apply_macros(plain, {"intensity": 0.9, "chaos": 0.3}, None)
    assert shots == plain


def test_the_foreshadow_never_slices(shipped):
    opt = {"foreshadow": "slices"}
    assert dense.foreshadow_mode(opt, "paper-summer", {}) == "trace"


def test_the_knobs_cap_chaos_under_breathe_in_the_make_and_the_recut(shipped):
    assert taste.cap_macros({"chaos": 0.9, "intensity": 0.5}, {"breathe": True})["chaos"] == 0.5
    assert taste.cap_macros({"chaos": 0.9}, {"breathe": False})["chaos"] == 0.9


def test_the_batch_never_takes_a_vibe_twice_nor_a_demoted_one(shipped):
    assert taste.fresh_vibes(["none", "black", "none", "wet-paint", "cosmic"]) == ["none", "black", "cosmic"]
    assert taste.fresh_vibes(["wet-paint", "black"]) == ["wet-paint", "black"]  # the vibe you chose stays
    made = batch.variations({"vibe": "wet-paint", "idea": ""}, 5, "vibe")
    vibes = [v["body"]["vibe"] for v in made]
    assert vibes[0] == "wet-paint" and len(set(vibes)) == len(vibes) and "odd-machine" not in vibes


# ------------------------------------------------------------------------------------------------ a Make and its re-cut


def _make(tmp_path: Path, monkeypatch, body: dict, *, song: str = "morphing-wobble-20s", drop: float = 12.79) -> tuple[Path, list]:
    feats = json.loads((ROOT / "tests" / "fixtures" / "analyses" / f"{song}.features.json").read_text(encoding="utf-8"))
    directed = {"duration": float(feats["duration"]), "beats": [float(b) for b in feats["beats"]], "sections": feats["sections"]}
    guarded, _ = guardrails.apply(body, duration=directed["duration"], beats=directed["beats"])
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills_, work: stills_)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills_, work, w=720, h=1280, background=None: stills_)
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: drop)
    import xenoform.cloud_morph as cm

    def fake_clips(shots, stills_, work, w, h):
        out = []
        for i in range(len(shots)):
            p = Path(work) / f"m{i:02d}.mp4"
            p.write_bytes(b"clip")
            out.append(p)
        return out

    monkeypatch.setattr(cm, "_mock_clips", fake_clips)
    seen: list = []

    def spy(clips, shots, audio, out, **kw):
        seen.append({"shots": copy.deepcopy(shots), "kw": kw})
        Path(out).write_bytes(b"mp4")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"],
                "fx": True, "overlay": False, "centres": [], "fps": 24, "look": {}, "transitions": [], "boundary_fx": {},
                "foreshadow": {}, "effects": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    job = tmp_path / "job"
    job.mkdir(parents=True, exist_ok=True)
    dense.run_simple(directed, ROOT / "examples" / "demo.wav", job / "xenoform.mp4", job, {}, dict(guarded), lambda *a: None,
                     engine="mock")
    return job, seen


BASE = {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "seed": 2727,
        "breathe": False, "drop_mode": "off", "auto_grow": False}


def test_a_make_keeps_what_the_taste_file_did_in_its_record(shipped, tmp_path, monkeypatch):
    job, seen = _make(tmp_path, monkeypatch, {**BASE, "macros": {"chaos": 0.95, "intensity": 0.9}, "dance_fx": "cyan-flash",
                                              "effects": ["dither", "kaleido"], "foreshadow": "slices"})
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    block = rec["taste"]
    assert block["rules"] == len(taste.rules()) and block["lines"] and all(x.startswith("[taste] ") for x in block["lines"])
    for rid in ("no-black-heart-or-dna", "quiet-opener", "no-flash-before-drop", "one-effect", "strobe-at-full-heat"):
        assert rid in block["fired"], rid
    assert "dna helix" not in " ".join(rec["stills"])
    kw = seen[-1]["kw"]
    assert kw["foreshadow"] == "trace"
    kinds = [p["kind"] for p in kw["boundary_fx"] if p]
    assert kinds.count("strobe") <= 1


def test_no_taste_block_without_the_file(tmp_path, monkeypatch):
    job, _ = _make(tmp_path, monkeypatch, dict(BASE))
    assert "taste" not in json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))


def test_a_recut_obeys_the_same_rules_and_the_timeline_keeps_its_picks(tmp_path, monkeypatch):
    job, seen = _make(tmp_path, monkeypatch, dict(BASE))  # made with no taste file: a record from before it
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    rec = dense.recut_from_cache(job, {"macros": {"chaos": 0.95, "intensity": 0.9}, "dance_fx": "cyan-flash",
                                       "effects": ["dither", "kaleido"], "foreshadow": "slices",
                                       "shot_overrides": {"0": {"look": "negative-rush"}}})
    kw, shots = seen[-1]["kw"], seen[-1]["shots"]
    assert kw["foreshadow"] == "trace"
    assert shots[0]["dance_fx"] == "negative-rush"  # the timeline's own pick on shot 0 stays the user's
    first = taste.first_drop(shots, rec.get("drop"))
    assert all(s.get("dance_fx") == "cool-echo" for s in shots[1:] if float(s["start"]) < first - 1e-6)
    assert all(len(s.get("fx_names") or []) <= 1 for s in shots)
    assert [p["kind"] for p in kw["boundary_fx"] if p].count("strobe") <= 1
    assert rec["taste_recut"]["fired"] and "taste" not in rec  # the Make's record had no block; the re-cut says what it did


def test_the_make_and_the_desk_report_the_lines():
    import inspect

    from xenoform import turbo, ui

    assert '"taste_lines"' in inspect.getsource(turbo._run_turbo)
    assert 'result.get("taste_lines")' in inspect.getsource(ui)
    app = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    assert 'startsWith("[taste]")' in app and "taste note" in app


# ------------------------------------------------------------------------------------------------ the Stems mode's layers


from test_stems_mode import _stems_make, fake_render, stems_dir  # noqa: E402,F401  (a Stems Make on the mock engine)


def test_every_stems_layer_is_a_cut_the_taste_file_acts_in(shipped, tmp_path, fake_render):
    from xenoform import stems_mode

    layers = [{"stem": "drums", "kind": "objects", "prominence": 0.8}, {"stem": "bass", "kind": "objects", "prominence": 0.6},
              {"stem": "other", "kind": "objects", "prominence": 0.5}]
    job = tmp_path / "job"
    rec, rep, seen, song = _stems_make(tmp_path, job, layers)
    chains = {s: stems_mode._chain_nouns(job / "layers" / s) for s in ("drums", "bass", "other")}
    for stem, nouns in chains.items():
        assert nouns, stem
        assert not [n for n in nouns if taste.ban_for(n, stills.family_of(n))], (stem, nouns)  # the bans, in each layer
        assert len(set(nouns)) == len(nouns), (stem, nouns)  # no object twice inside the layer
        made = json.loads((job / "layers" / stem / "simple" / "simple.json").read_text(encoding="utf-8"))
        assert made["taste"]["fired"], stem  # each layer's own cut says what the file did in it
    every = [n for nouns in chains.values() for n in nouns]
    assert len(set(every)) == len(every)  # nor across the layers (the earlier layers' objects stay out of the later ones)
    saved = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert saved["taste"] == rec["taste"] and saved["taste"]["fired"]
    for stem in ("drums", "bass", "other"):  # the Make's notes name the layer each line comes from
        assert any(line.startswith(f"[taste] {stem} layer: ") for line in rec["taste"]["lines"]), rec["taste"]["lines"]
    assert all(line.startswith("[taste] ") and line.endswith(")") for line in rec["taste"]["lines"])


def test_a_stems_layer_counts_its_pool_without_what_the_layers_before_it_took(shipped, monkeypatch):
    rows = list(mp.catalogue()["liquid-gold"])
    gone, names = [r["file"] for r in rows[:12]], [rows[20]["noun"]]
    seen: dict = {}

    def fit(state, directed, audio_path, chain, pool_n, tier):  # the pool the chain was planned on
        seen[bool(state.get("avoid_stills"))] = pool_n
        return [], {}, chain

    monkeypatch.setattr(dense, "fit_chain", fit)
    shots = [{"start": i * 0.5, "end": (i + 1) * 0.5} for i in range(120)]  # more shots than the pool: it is re-planned
    directed = {"duration": 60.0, "beats": [i * 0.5 for i in range(120)]}
    body = {"vibe": "liquid-gold", "mode": "simple", "quality_tier": "draft", "seed": 5}
    dense.long_song_chain(body, directed, None, shots, {}, dense.options(body), grow=False)
    dense.long_song_chain({**body, "avoid_stills": gone, "avoid_nouns": names}, directed, None, shots, {}, dense.options(body),
                          grow=False)
    left = [r for r in rows if r["file"] not in gone and r["noun"] not in names]
    assert seen[False] == len(taste.usable(rows)) and seen[True] == len(taste.usable(left)) < seen[False]
