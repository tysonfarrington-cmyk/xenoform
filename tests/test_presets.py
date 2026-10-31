"""Chain presets (31 Oct 2026, Stage 4 of docs/MUSIC_VIDEO_PLAN.md): the loved chains as one click. The file
(configs/chain_presets.json), its loader (xenoform.presets), the route (GET /api/presets) and the chips beside the idea line."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform import morph_pass as mp
from xenoform import presets, vibes

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "configs" / "chain_presets.json"
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
IDS = ["black-rose", "black-flowers", "glow-sea", "deep-sea-fish", "smoke-dragon", "gold-finale", "origami-noir", "origami-icons", "glass-hand"]


def test_the_loved_chains_are_presets_whose_pins_are_shipped_stills():
    raw = json.loads(FILE.read_text(encoding="utf-8"))["presets"]
    got = presets.load()
    assert [p["id"] for p in got] == IDS == [r["id"] for r in raw]
    shipped = {r["file"] for rows in mp.manifest().values() for r in rows}
    for p, row in zip(got, raw):
        assert p["pins"] == row["pins"] and p["pins"], p["id"]  # the loader dropped no pin: every one is a shipped still
        assert set(p["pins"].values()) <= shipped and len(set(p["pins"].values())) == len(p["pins"]), p["id"]
        assert sorted(int(k) for k in p["pins"]) == list(range(len(p["pins"]))), p["id"]  # slots 0, 1, 2...
        assert all(f.startswith(p["vibe"] + "/") for f in p["pins"].values()) and p["vibe"] in vibes.ids()
        assert p["name"] and p["line"] and p["note"] and p["engine"] == "ltx25" and p["seed"] == 2727
        assert set(p["knobs"]) == set(presets.KNOBS)
        assert (p["morph_style"], p["morph_timing"], p["look"], p["foreshadow"], p["effects"]) == (
            row["morph_style"], row["morph_timing"], row["look"], row["foreshadow"], row["effects"]), p["id"]
        assert p["backdrop"] == row["backdrop"] == "plain", p["id"]  # made before places existed: always the studio ground
    by = {p["id"]: p for p in got}
    # what he loved: the rose opens into the lotus in Bloom, smooth, no effects; the smoke dragon is melt in noir-glow
    rose = by["black-rose"]
    assert [rose["pins"][str(i)].split("/")[1][:2] for i in range(4)] == ["11", "00", "05", "01"] and rose["morph_style"] == "bloom"
    assert rose["effects"] == [] and rose["knobs"]["chaos"] == 0.15 and any("it sort of opens up" in t for t in rose["tys"])
    assert (by["smoke-dragon"]["morph_style"], by["smoke-dragon"]["look"]) == ("melt", "noir-glow")
    assert by["deep-sea-fish"]["effects"] == ["feedback"] and "kaleido" not in by["deep-sea-fish"]["effects"]
    # a chain's loved clips are in examples/morphs
    clips = {m["id"] for m in json.loads((ROOT / "examples" / "morphs" / "morphs.json").read_text(encoding="utf-8"))["morphs"]}
    assert set(rose["morphs"]) == {"black-droplet-to-rose", "black-rose-to-lotus", "black-lotus-to-jellyfish"} <= clips
    assert all(set(p["morphs"]) <= clips for p in got)


def test_a_preset_body_is_the_make_body_and_pins_hold_their_slots():
    body = presets.body(presets.get("black-rose"))
    assert set(body) == {"vibe", "idea", "chain_pins", "morph_style", "morph_timing", "effects", "dance_fx", "foreshadow", "backdrop", "macros", "seed"}
    assert body["backdrop"] == "plain" and body["backdrop"] in mp.BACKDROPS  # every loved chain stood on the studio ground
    assert not {"quality_tier", "tier", "cloud_final_ok", "cloud_quality", "song", "audio_id", "length_s"} & set(body)  # it costs nothing
    assert body["vibe"] == "black" and body["dance_fx"] == "auto" and body["foreshadow"] == "off" and body["macros"]["glow"] == 0.6
    assert mp.pins_of(body) == {0: "black/11_droplet_black_glass.jpg", 1: "black/00_rose_black_glass.jpg",
                                2: "black/05_lotus_black_glass.jpg", 3: "black/01_jellyfish_black_glass.jpg"}
    look, picked = mp.pick_stills({**body, "mode": "simple"}, 6, record=False)
    assert look == "black" and [s["file"] for s in picked[:4]] == [body["chain_pins"][str(i)] for i in range(4)]
    assert all(s.get("pinned") for s in picked[:4]) and len({s["file"] for s in picked}) == 6
    flowers = presets.body(presets.get("black-flowers"))
    _, picked = mp.pick_stills({**flowers, "mode": "simple"}, 8, record=False)
    assert [s["noun"] for s in picked[:6]] == ["orchid", "passion flower", "protea", "magnolia", "peony", "dahlia"]


def test_a_missing_or_bad_file_means_none_and_a_bad_field_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("XENO_PRESETS", str(tmp_path / "nope.json"))
    assert presets.load() == [] and presets.get("black-rose") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("XENO_PRESETS", str(bad))
    assert presets.load() == []
    bad.write_text(json.dumps({"presets": "no"}), encoding="utf-8")
    assert presets.load() == []
    still = "black/00_rose_black_glass.jpg"
    rows = [
        {"id": "Fine One!", "name": "Fine", "vibe": "black", "pins": {"0": still, "1": "black/none.jpg", "x": still, "2": "../objects.json",
                                                                     "3": "C:/Windows/win.ini", "4": "/etc/passwd", "5": still},
         "morph_style": "wobble", "morph_timing": "fast", "effects": ["kaleido", "lasers"], "look": "plaid", "foreshadow": "slices?",
         "backdrop": "gardens", "knobs": {"chaos": "7", "glow": -2, "speed": "x"}, "seed": "abc", "tys": "not a list"},
        {"id": "fine-one", "name": "Duplicate id", "vibe": "black"},  # the first row of an id wins
        {"id": "in-places", "name": "In places", "vibe": "black", "backdrop": "Places"},
        {"id": "no-vibe", "name": "Unknown vibe", "vibe": "not-a-vibe"},
        {"id": "", "name": "No id", "vibe": "black"},
        {"id": "no-name", "vibe": "black"},
        "not a row",
    ]
    bad.write_text(json.dumps({"presets": rows}), encoding="utf-8")
    got = presets.load()
    assert [p["id"] for p in got] == ["fine-one", "in-places"]
    assert [q["backdrop"] for q in got] == ["plain", "places"]  # an unknown Backdrop falls back to Plain, a known one (any case) is kept
    p = got[0]
    assert p["pins"] == {"0": still, "5": still}  # a missing file, a path out of the folder, a drive and a slot that is no number are dropped
    assert (p["morph_style"], p["morph_timing"], p["effects"], p["look"], p["foreshadow"]) == ("auto", "smooth", ["kaleido"], "auto", "auto")
    assert p["knobs"] == {"chaos": 1.0, "glow": 0.0} and p["seed"] == 2727 and p["tys"] == []  # clamped to 0..1, the default seed
    assert presets.get("fine-one")["name"] == "Fine" and presets.body(p)["chain_pins"] == {"0": still, "5": still}


def test_the_desk_serves_the_presets_with_a_thumbnail_that_loads():
    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())
    got = client.get("/api/presets").json()["presets"]
    assert [p["id"] for p in got] == IDS
    for p in got:
        assert p["thumb"].startswith("/api/stills/thumb?file=") and p["body"]["vibe"] == p["vibe"]
        assert p["body"]["chain_pins"] == p["pins"] and p["body"]["macros"] == p["knobs"]
    thumb = client.get(got[0]["thumb"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg"
    # the rows /api/vibes serves know every preset's vibe (the chip names it)
    known = {v["id"] for v in client.get("/api/vibes").json()["vibes"]}
    assert {p["vibe"] for p in got} <= known


def test_a_chip_beside_the_idea_line_applies_a_preset_in_one_click_and_never_the_tier():
    idea = APP.split("function ideaBlock(easy) {", 1)[1].split("\n}\n", 1)[0]
    assert "${presetChips(easy)}" in idea and idea.index("${ideaReadingLine(easy)}") < idea.index("${presetChips(easy)}") < idea.index("idea-help")
    assert "async function loadPresets(" in APP and '"/api/presets"' in APP and "loadPresets()" in APP.split("async function boot()", 1)[1]
    chips = APP.split("function presetChips(easy) {", 1)[1].split("function applyPreset(", 1)[0]
    assert 'data-act="easy-preset"' in chips and "starts no render and spends no credits" in chips
    apply = APP.split("function applyPreset(id) {", 1)[1].split("function ideaReadingLine(", 1)[0]
    for key in ("easy.vibe", "easy.idea", "easy.pins", "easy.morphStyle", "easy.morphTiming", "easy.effects", "easy.danceFx", "easy.foreshadow",
                "easy.backdrop", "XENO_MACRO_SET", "saveEasy()", "render()"):
        assert key in apply, key
    assert not any(word in apply for word in ("easy.tier", "cloudFinalOk", "cloudToken", "easyMake", "easy.cloud")), "a preset never touches the tier or starts a Make"
    assert 'act === "easy-preset"' in APP and ".preset-chip" in (ROOT / "src" / "xenoform" / "ui_static" / "desk.css").read_text(encoding="utf-8")
