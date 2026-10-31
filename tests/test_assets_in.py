"""Assets into the app (31 Oct 2026, Stage 4 of docs/MUSIC_VIDEO_PLAN.md): the loved morphs, the gold outro clip and the
rebuilt showcase reel, then the example cuts and the vibe cards, the chain presets, the records and the library strips.
Each manifest is checked against the files it lists and the shipped stills it names."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
MORPHS = ROOT / "examples" / "morphs"
CLIPS = ROOT / "examples" / "clips"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _shipped_files() -> set[str]:
    return {row["file"] for rows in _json(STATIC / "objects" / "objects.json").values() for row in rows}


# ---------------------------------------------------------------------------------------------- the loved morphs


def test_every_loved_morph_is_a_file_with_its_record_and_names_two_shipped_stills():
    from xenoform import dance_fx, effects, morph_style, morph_timing, vibes

    manifest = _json(MORPHS / "morphs.json")
    shipped = _shipped_files()
    ids = [m["id"] for m in manifest["morphs"]]
    assert len(ids) == len(set(ids)) == 38
    assert sorted(p.name for p in MORPHS.glob("*.mp4")) == sorted(m["file"] for m in manifest["morphs"])
    groups = {g["id"]: g for g in manifest["groups"]}
    assert len(groups) == 8 and all(g["tys"] for g in groups.values())  # his words are on every group
    for m in manifest["morphs"]:
        path = MORPHS / m["file"]
        data = path.read_bytes()
        assert len(data) == m["bytes"] and 100_000 < len(data) < 2_000_000, m["id"]
        assert hashlib.sha1(data).hexdigest() == m["sha1"], m["id"]
        assert m["from"]["file"] in shipped and m["to"]["file"] in shipped and m["from"]["file"] != m["to"]["file"], m["id"]
        assert m["vibe"] in vibes.ids() and m["from"]["file"].startswith(m["vibe"] + "/"), m["id"]
        assert m["style"] in morph_style.STYLES and m["timing"] in morph_timing.MODES, m["id"]
        assert set(m["effects"]) <= set(effects.NAMES) and (m["look"] == "auto" or m["look"] in dance_fx.PRESETS), m["id"]
        assert set(m["knobs"]) == {"intensity", "speed", "chaos", "glow"} and all(0 <= v <= 1 for v in m["knobs"].values())
        assert isinstance(m["seed"], int) and m["tier"] == "cloud" and "LTX-2.5" in m["engine"] and m["credit"] and m["note"]
        assert m["fps"] == 24 and m["frames"] in (49, 73, 97) and m["groups"] and set(m["groups"]) <= set(groups)
        assert abs(m["seconds"] - m["frames"] / 24) < 0.01 and m["px"] in ([1024, 576], [576, 1024])
        assert (m["aspect"] == "9:16") == (m["px"] == [576, 1024])
    for g in groups.values():
        assert g["morphs"] and set(g["morphs"]) <= set(ids), g["id"]


def test_the_rose_into_the_lotus_and_the_fish_are_among_the_loved_morphs():
    """The two in no published video (the montage ships the orchid run and the feedback-only fish): the clips are the only copies."""
    by = {m["id"]: m for m in _json(MORPHS / "morphs.json")["morphs"]}
    rose = by["black-rose-to-lotus"]
    assert (rose["from"]["noun"], rose["to"]["noun"], rose["style"], rose["timing"], rose["effects"]) == ("rose", "lotus", "bloom", "smooth", [])
    assert rose["published"] == [] and any("it sort of opens up" in w for w in rose["tys"])
    fish = by["bioluminescent-seahorse-to-koi-fish"]
    assert fish["effects"] == ["feedback", "kaleido"] and fish["also_used_in"][0]["effects"] == ["feedback"]  # one clip, two cuts
    assert fish["also_used_in"][0]["published"], "the feedback-only version is in the published Glitch Out"
    # the koi -> hermit crab clip waits for Tys's word: its end still is a taste flag and is not shipped
    left = _json(MORPHS / "morphs.json")["left_out"]
    assert [(x["job"], x["shot"]) for x in left] == [("c71fcf69", 3)]
    assert not any(m["to"]["noun"] == "hermit crab" for m in by.values())


# ---------------------------------------------------------------------------------------------- clips and the showcase


def test_the_gold_outro_is_a_540p_copy_that_names_its_morphs():
    manifest = _json(CLIPS / "clips.json")
    clip = next(c for c in manifest["clips"] if c["id"] == "gold-outro")
    path = CLIPS / clip["file"]
    assert 1_000_000 < path.stat().st_size < 4_000_000
    morphs = {m["id"]: m for m in _json(MORPHS / "morphs.json")["morphs"]}
    chain = [morphs[i] for i in clip["morphs"]]
    assert [m["from"]["noun"] for m in chain] == ["phoenix", "lion head", "dragon", "eagle", "infinity knot", "scarab beetle", "koi"]
    assert all(a["to"]["file"] == b["from"]["file"] for a, b in zip(chain, chain[1:]))  # one continuous chain
    assert clip["px"] == [960, 540] and clip["song"] == "glitch-out" and clip["credit"] and clip["tys"]


def test_the_showcase_is_rebuilt_from_the_loved_morphs_on_glitch_outs_beats():
    rec = _json(STATIC / "showcase" / "showcase.json")
    morphs = {m["file"]: m for m in _json(MORPHS / "morphs.json")["morphs"]}
    shots = rec["shots"]
    assert [s["clip"] for s in shots][0] == "black-rose-to-lotus.mp4"  # it opens on the rose into the lotus
    assert morphs[shots[-1]["clip"]]["vibe"] == "liquid-gold"  # and ends on gold
    assert all(s["clip"] in morphs for s in shots)
    cuts = rec["cuts"]
    assert cuts[0] == 0.0 and cuts == sorted(cuts) and len(cuts) == len(shots) + 1 and abs(rec["seconds"] - cuts[-1]) < 1e-6
    assert 15 <= rec["seconds"] <= 24 and rec["track"] == "glitch_out.mp3" and rec["tempo"] == 90.0
    # every cut is on a beat of the bundled song's own analysis, six beats apart: the 1:59 drop lands on the second cut
    beats = _json(ROOT / "examples" / "songs" / "glitch-out.features.json")["beats"]
    at = [round(rec["track_start"] + c, 3) for c in cuts]
    assert all(min(abs(b - t) for b in beats) < 0.002 for t in at)
    assert abs(at[1] - 119.792) < 0.01 and rec["shot_beats"] == 6
    assert (STATIC / "showcase" / "showcase.mp4").stat().st_size < 6_000_000 and (STATIC / "showcase" / "showcase.jpg").stat().st_size > 5_000


def test_the_licence_lines_name_the_models_that_made_the_showcase():
    """The old reel was LTX-2.3 22B distilled (its record said LTX-Video 0.9.5); the new one is LTX-2.5 on Comfy Cloud."""
    rec = _json(STATIC / "showcase" / "showcase.json")
    assert "LTX-2.5" in rec["note"] and "0.9.5" not in rec["note"] and "LTX-2.5" in rec["credit"] and "Comfy Cloud" in rec["credit"]
    for name in ("CREDITS.md", "docs/LICENCES.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "showcase" in line.lower() and "LTX-2.5" in line)
        assert "LTX-2.3" in row and "11 August 2026" in row and "5 January 2026" in row and "Comfy Cloud" in row, name
        assert "finished local LTX morph clips" not in text, name


# ---------------------------------------------------------------------------------------------- example cuts and cards

CUTS = ROOT / "examples" / "cuts"
FEATURED = ("chrome-mercury", "neon-noir", "porcelain-kintsugi", "bioluminescent", "risograph", "iridescent-glass",
            "liquid-gold", "ink-wash", "cyberspace-95", "wet-paint", "shadow-self", "botanical", "none")
NOT_BUNDLED_NAMES = ("korn", "tool_", "prodigy", "zeds", "xf_")  # the not-bundled Suno demos' file names name artists: no record carries them


def test_every_example_cut_is_a_540p_silent_excerpt_with_its_record():
    from xenoform import simple_recipe, vibes

    manifest = _json(CUTS / "cuts.json")
    songs = {s["id"] for s in _json(ROOT / "examples" / "songs" / "songs.json")["songs"]}
    shipped = _shipped_files()
    rows = manifest["cuts"]
    assert sorted(r["vibe"] for r in rows) == sorted(FEATURED) and len({r["id"] for r in rows}) == 13
    assert sorted(p.name for p in CUTS.glob("*.mp4")) == sorted(r["file"] for r in rows)
    for r in rows:
        path = CUTS / r["file"]
        assert 900_000 < path.stat().st_size <= 1_500_000 and path.stat().st_size == r["bytes"], r["id"]
        assert r["px"] == [540, 960] and r["fps"] == 24 and r["tier"] == "cloud" and r["aspect"] == "9:16" and r["audio"] is False
        assert 13 <= r["seconds"] <= 17 and abs(r["seconds"] - (r["excerpt"]["to_s"] - r["excerpt"]["from_s"])) < 0.01
        assert r["source"]["from_s"] == r["excerpt"]["from_s"] and r["source"]["to_s"] == r["excerpt"]["to_s"] <= r["source"]["seconds"]
        assert r["excerpt"]["from_s"] <= r["excerpt"]["card_s"] <= r["excerpt"]["to_s"]  # the vibe card's frame is in the excerpt
        assert r["song"] is None or r["song"] in songs, r["id"]
        assert r["seed"] == 2727 and r["morphs"] >= 8 and len(r["chain"]) == len(r["chain_files"]) >= r["morphs"] and r["credit"]
        # the recipe reads back as this cut, with a song label that names no artist
        state = simple_recipe.decode(r["recipe"])
        assert state["vibe"] == r["vibe"] and state["quality_tier"] == "cloud" and state["aspect"] == "9:16"
        assert state["song"].endswith("(30 s cut)") and not any(w in state["song"].lower() + r["song_label"].lower() for w in NOT_BUNDLED_NAMES)
        assert r["vibe"] in vibes.ids()
        # every still of the chain is shipped but the taste-flagged ones, and none of those is inside the excerpt
        assert set(r["chain_files"]) - set(r["chain_not_shipped"]) <= shipped, r["id"]
    left_out = {f for r in rows for f in r["chain_not_shipped"]}
    assert left_out == {"none/113_hermit_crab.jpg", "ink-wash/078_piano_melting_into_a_puddle.jpg"}


def test_the_card_picks_agree_with_the_cuts_and_the_cards_are_the_size_of_a_tile():
    from PIL import Image

    cuts = {r["vibe"]: r for r in _json(CUTS / "cuts.json")["cuts"]}
    picks = _json(ROOT / "scripts" / "vibe_objects" / "picks_thumbs.json")
    assert [p["vibe"] for p in picks] and {p["vibe"] for p in picks} == set(cuts)
    for p in picks:  # the 29 Oct cards: one frame of the very cut the example excerpt is taken from
        assert p["job"] == cuts[p["vibe"]]["source"]["job"] and p["t"] == cuts[p["vibe"]]["excerpt"]["card_s"], p["vibe"]
    newer = _json(ROOT / "scripts" / "vibe_objects" / "picks_cards.json")
    assert len(newer) == 10 and not {p["vibe"] for p in newer} & set(cuts)  # the older vibes, none of them an example vibe
    from xenoform import vibes

    for p in picks + newer:
        assert p["vibe"] in vibes.ids() and (STATIC / "vibes" / f"{p['vibe']}.jpg").stat().st_size > 20_000
    for p in newer:  # re-cut on 31 Oct: 16:10, the size the tile wants
        with Image.open(STATIC / "vibes" / f"{p['vibe']}.jpg") as im:
            assert im.size == (1280, 800), p["vibe"]


def test_a_vibe_row_carries_its_example_and_the_desk_serves_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui
    from xenoform import vibes

    rows = {r["id"]: r for r in vibes.catalog()}
    with_example = {vid for vid, r in rows.items() if r["example"]}
    assert with_example == set(FEATURED)
    assert rows["chrome-mercury"]["example"] == "/examples/cuts/chrome-mercury.mp4" and rows["ocean"]["example"] == ""
    client = TestClient(_ui.create_app())
    served = client.get("/api/vibes").json()["vibes"]
    assert {v["id"] for v in served if v["example"]} == set(FEATURED)
    cuts = client.get("/api/examples/cuts").json()["cuts"]
    assert [c["vibe"] for c in cuts] == [r["vibe"] for r in _json(CUTS / "cuts.json")["cuts"]] and all(c["url"] and c["recipe"] for c in cuts)
    video = client.get("/examples/cuts/none.mp4")
    assert video.status_code == 200 and video.headers["content-type"] == "video/mp4" and len(video.content) == (CUTS / "none.mp4").stat().st_size
    assert client.get("/examples/cuts/cuts.json").status_code == 404  # only the cuts the manifest lists
    assert client.get("/examples/cuts/..%2Fsongs%2Fglitch_out.mp3").status_code == 404
    assert client.get("/examples/cuts/nope.mp4").status_code == 404
    # no manifest, no example: a bad or missing cuts.json means none, and a listed file that is gone is skipped
    (tmp_path / "cuts.json").write_text(json.dumps({"cuts": [{"vibe": "ocean", "file": "ocean.mp4"}, {"vibe": "cosmic", "file": "../x.mp4"}]}), encoding="utf-8")
    monkeypatch.setenv("XENO_CUTS", str(tmp_path))
    assert vibes.examples() == [] and {r["example"] for r in vibes.catalog()} == {""}
    (tmp_path / "ocean.mp4").write_bytes(b"mp4")
    assert [e["vibe"] for e in vibes.examples()] == ["ocean"] and vibes.example("ocean")["url"] == "/examples/cuts/ocean.mp4"
    (tmp_path / "cuts.json").write_text("{not json", encoding="utf-8")
    assert vibes.examples() == []
    monkeypatch.setenv("XENO_CUTS", str(tmp_path / "gone"))
    assert vibes.examples() == []


def test_the_desk_shows_the_example_on_the_card_and_in_the_showcase():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert 'data-act="vibe-example"' in app and "vibe.example && !compact" in app and ".vibe-eg" in css  # a badge on the card
    assert "function openExample(" in app and "function closeExample(" in app and 'act === "vibe-example"' in app and ".example-modal" in css
    # the showcase aside lists the finished cuts, swaps one into the player, and keeps what it said before
    aside = app.split("function showcaseAside() {", 1)[1].split("// Share, the last stage", 1)[0]
    assert 'data-act="easy-showcase-vibe"' in aside and "Make your own" in aside and "easy-again" in aside
    assert "function showcaseExample(" in app and "showcaseExample()" in app.split("function easyMedia() {", 1)[1].split("function vibeCards", 1)[0]
    assert 'act === "easy-showcase-vibe"' in app and 'act === "easy-showcase-use"' in app and "SHOWCASE_NOTE" in app
    assert "one RTX 3080 Ti" not in app  # the reel is a Cloud one now


def test_the_judges_page_lists_the_vibes_it_should():
    import importlib.util

    spec = importlib.util.spec_from_file_location("gen_judges_cards", ROOT / "scripts" / "gen_judges_cards.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, "judges.html is stale: python scripts/gen_judges_cards.py"
