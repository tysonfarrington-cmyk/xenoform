"""The taste file (configs/taste.json) and its loader (xenoform.taste): Tys's standing rules as data, every rule with an id,
a kind, its data and a one-line reason; read again when the file changes; a missing or broken file is no rules and one
warning, never an error (docs/MUSIC_VIDEO_PLAN.md section 4, docs/TASTE.md)."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import pytest

from xenoform import taste

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "configs" / "taste.json"


@pytest.fixture()
def shipped(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    return taste.load()


def test_every_rule_has_an_id_a_kind_its_data_and_a_one_line_reason(shipped):
    raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
    assert len(shipped["rules"]) == len(raw["rules"]), "a shipped rule was dropped as invalid"
    ids = [r["id"] for r in raw["rules"]]
    assert len(ids) == len(set(ids))
    data_keys = {"subject": ("words",), "family": ("families",), "run": ("max",), "look": ("demote",), "limit": (),
                 "weight": ("weights",)}
    for r in raw["rules"]:
        assert re.fullmatch(r"[a-z0-9-]+", r["id"]), r["id"]
        assert r["kind"] in taste.KINDS
        assert r["reason"].strip() and "\n" not in r["reason"] and len(r["reason"]) < 200, r["id"]
        assert re.fullmatch(r"2026-1[01]-\d\d", r["since"]), r["id"]  # October's notes, and November's (no-clip-twice)
        for key in data_keys[r["kind"]]:
            assert r.get(key), f"{r['id']} has no {key}"
        assert set(r) - {"id", "kind", "reason", "since", "off"}, f"{r['id']} carries no data"
        if r["kind"] == "look":
            assert r["demote"] in taste.DEMOTES


def test_no_quotes_from_the_sessions_in_the_file():
    text = SHIPPED.read_text(encoding="utf-8")
    assert "Tys, " not in text and "msg " not in text
    for phrase in ("pretty terrible", "sparingly and subtly", "looks off", "too random", "handycam", "ugly",
                   "the more natural stuff", "ruins the consistency", "i really dont like"):
        assert phrase not in text.lower(), phrase


BANNED = ["teacup", "pitcher", "coffee mug", "ship wheel", "steering wheel", "valve wheel", "flywheel", "racing tyre",
          "acoustic guitar", "golden fleece", "racing helmet", "winged helm", "dented knight's helm", "hay bale",
          "t-rex skull", "triceratops", "dinosaur egg", "pirate hat", "pirate ship in full sail", "galleon", "cutlass",
          "flintlock pistol", "cannon", "ship in a bottle", "parrot", "binoculars", "spyglass", "hermit crab",
          "taj mahal", "statue liberty", "parthenon", "colosseum", "sphinx head", "origami snake", "ram golden horn",
          "ram horn", "lightning bolt", "dna helix", "anatomical heart", "glass anatomical heart", "top hat",
          "pendulum clock", "wine glass", "kettle", "cocktail shaker"]
SPARED = ["pitcher plant", "buttercup", "unicorn horn", "starry wizard hat", "lightning-struck tower", "horned demon skull",
          "dragon skull with curling horns", "mechanical heart with pistons", "mended heart",
          "scarab beetle", "serpent", "moai head", "stonehenge", "jellyfish", "rose", "lotus", "nautilus", "phoenix",
          "dragon", "koi", "manta ray", "orchid", "pocket watch", "chess knight", "cupola", "wheelbarrow"]


@pytest.mark.parametrize("noun", BANNED)
def test_the_plans_banned_subjects_are_out(shipped, noun):
    assert taste.ban_for(noun) is not None, noun
    assert not taste.noun_ok(noun)


@pytest.mark.parametrize("noun", SPARED)
def test_what_he_loves_and_the_near_misses_stay(shipped, noun):
    assert taste.ban_for(noun) is None, (noun, (taste.ban_for(noun) or {}).get("id"))


def test_whole_words_only():
    assert taste.words_of("T-Rex  Skull!") == "t rex skull"
    assert taste._has("cup", "coffee cup") and not taste._has("cup", "cupola") and not taste._has("cup", "buttercup")


def test_the_musical_run_is_a_run_not_a_ban(shipped):
    for noun in ("grand piano", "electric guitar", "violin", "french horn", "drum kit"):
        assert taste.run_for(noun) is not None, noun
        assert taste.ban_for(noun) is None or noun == "acoustic guitar"
    assert taste.run_for("jellyfish") is None
    assert taste.rule("no-musical-run")["max"] == 1


def test_the_demoted_looks_are_notes_and_never_deletions(shipped):
    vibes = {v["id"]: v for v in json.loads((ROOT / "configs" / "vibes.json").read_text(encoding="utf-8"))["vibes"]}
    for vid in ("wet-paint", "odd-machine"):
        assert taste.demoted_vibe(vid) is not None
        assert vid in vibes and not vibes[vid].get("featured"), f"{vid} is still a registry vibe, off the featured cards"
    assert taste.demoted_vibe("liquid-gold") is None
    chess = taste.rule("plain-marble-chess")
    assert chess["vibe"] == "porcelain-marble" and chess["demote"] == "stills"
    assert taste.rule("no-film-clips")["demote"] == "note"
    assert taste.living("koi") and taste.living("manta ray") and taste.living("barn owl") and not taste.living("torus knot")


def test_the_limits_carry_the_plans_numbers(shipped):
    assert taste.breathe_chaos() == 0.5
    assert taste.opener() == (0.6, 20.0)
    assert taste.flash_looks() == (("cyan-flash", "negative-rush"), "cool-echo")
    assert taste.slices_instead() == "trace"
    assert taste.kind_limits() == {"wipe_share": 0.25, "strobe_heat": 1.0, "no_repeat": True}
    assert taste.one_effect() == 1
    assert taste.no_mix() and taste.vibes_once()
    for rid in ("no-object-twice", "one-palette"):
        assert taste.rule(rid)["kind"] == "limit"


def test_natural_or_iconic_families_weigh_first(shipped):
    assert taste.weight("sea-creatures") > taste.weight("solids-and-knots") > taste.weight("machine-parts")
    assert taste.tier("living-things") == 0 and taste.tier("big-iconic") == 0
    assert taste.tier("retro-tech") == 1 and taste.tier("vessels-and-tableware") == 1
    assert taste.weight("a family nobody knows") == 1.0
    w = taste.family_weights({"solids-and-knots": 4, "sea-creatures": 3, "vessels-and-tableware": 2})
    assert "vessels-and-tableware" not in w and w["sea-creatures"] > w["solids-and-knots"]


def test_a_missing_file_is_no_rules_and_one_warning(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("XENO_TASTE", str(tmp_path / "gone.json"))
    with caplog.at_level(logging.WARNING, logger="xenoform"):
        for _ in range(3):
            assert taste.load() is taste.EMPTY
            assert taste.rules() == [] and not taste.active() and taste.ban_for("teacup") is None
    warned = [r for r in caplog.records if "taste file" in r.getMessage()]
    assert len(warned) == 1 and "not found" in warned[0].getMessage()


def test_a_broken_file_is_no_rules_and_one_warning(tmp_path, monkeypatch, caplog):
    bad = tmp_path / "taste.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setenv("XENO_TASTE", str(bad))
    with caplog.at_level(logging.WARNING, logger="xenoform"):
        assert taste.load() is taste.EMPTY
        assert taste.load() is taste.EMPTY
        assert taste.kind_limits() == {"wipe_share": None, "strobe_heat": None, "no_repeat": False}
    assert len([r for r in caplog.records if "unreadable" in r.getMessage()]) == 1
    bad.write_text(json.dumps({"rules": "not a list"}), encoding="utf-8")
    assert taste.load() is taste.EMPTY


def test_the_file_is_read_again_when_it_changes(tmp_path, monkeypatch):
    f = tmp_path / "taste.json"
    one = {"rules": [{"id": "no-cups", "kind": "subject", "words": ["cup"], "reason": "one"}]}
    f.write_text(json.dumps(one), encoding="utf-8")
    monkeypatch.setenv("XENO_TASTE", str(f))
    first = taste.load()
    assert taste.ban_for("cup") and not taste.ban_for("wheel")
    assert taste.load() is first, "an unchanged file is not read twice"
    two = {"rules": one["rules"] + [{"id": "no-wheels", "kind": "subject", "words": ["wheel"], "reason": "two"}]}
    f.write_text(json.dumps(two), encoding="utf-8")
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))  # a later time, as an editor's save would give
    assert taste.ban_for("wheel")["id"] == "no-wheels"


def test_a_bad_rule_is_dropped_and_the_others_hold(tmp_path, monkeypatch, caplog):
    f = tmp_path / "taste.json"
    f.write_text(json.dumps({"rules": [
        {"id": "ok", "kind": "subject", "words": ["cup"], "reason": "kept"},
        {"id": "no-reason", "kind": "subject", "words": ["wheel"]},
        {"id": "odd-kind", "kind": "mystery", "words": ["hat"], "reason": "x"},
        {"id": "off", "kind": "subject", "words": ["parrot"], "reason": "switched off", "off": True},
        {"id": "ok", "kind": "subject", "words": ["helmet"], "reason": "a second row with the same id"},
        "not a rule"]}), encoding="utf-8")
    monkeypatch.setenv("XENO_TASTE", str(f))
    with caplog.at_level(logging.WARNING, logger="xenoform"):
        got = taste.load()
    assert [r["id"] for r in got["rules"]] == ["ok"]
    assert taste.ban_for("cup") and not taste.ban_for("wheel") and not taste.ban_for("parrot") and not taste.ban_for("helmet")
    assert any("left out" in r.getMessage() for r in caplog.records)


def test_the_lines_a_make_gathers(shipped):
    assert taste.note("no-pirates", "outside a Make nothing is kept") is None
    with taste.collecting() as got:
        taste.note("no-pirates", "two pirate stills left out")
        taste.note("no-pirates", "two pirate stills left out")
        taste.note(["no-wheels", "no-parrots"], "a wheel and a parrot left out")
    assert taste.lines(got) == ["[taste] two pirate stills left out (no-pirates)",
                                "[taste] a wheel and a parrot left out (no-wheels, no-parrots)"]
    rec = taste.record(got)
    assert rec["fired"] == ["no-pirates", "no-wheels", "no-parrots"] and rec["rules"] == len(taste.rules())


def test_the_tests_run_without_a_taste_file_unless_they_ask():
    # tests/conftest.py points XENO_TASTE at no file, as it points XENO_STILLS at an empty library: the suite pins the cut
    # as it is with no rules, and the taste tests load the shipped file themselves
    assert not taste.active()
    assert os.environ.get("XENO_TASTE")
