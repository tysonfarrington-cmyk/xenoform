"""Assets into the app (31 Oct 2026, Stage 4 of docs/MUSIC_VIDEO_PLAN.md): the loved morphs, the gold outro clip and the
rebuilt showcase reel, then the example cuts and the vibe cards, the chain presets, the records and the library strips.
Each manifest is checked against the files it lists and the shipped stills it names."""
import argparse
import ast
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
MORPHS = ROOT / "examples" / "morphs"
CLIPS = ROOT / "examples" / "clips"
RECORDS = ROOT / "docs" / "demo" / "records"
YOUTUBE = ROOT / "docs" / "demo" / "youtube"
PROVENANCE = ROOT / "scripts" / "vibe_objects" / "provenance"


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
EXAMPLE_VIBES = ("chrome-mercury", "neon-noir", "porcelain-kintsugi", "bioluminescent", "risograph", "iridescent-glass",  # the 13 that were featured on 29 Oct
            "liquid-gold", "ink-wash", "cyberspace-95", "wet-paint", "shadow-self", "botanical", "none")
NOT_BUNDLED_NAMES = ("korn", "tool_", "prodigy", "zeds", "xf_")  # the not-bundled Suno demos' file names name artists: no record carries them


def test_every_example_cut_is_a_540p_silent_excerpt_with_its_record():
    from xenoform import simple_recipe, vibes

    manifest = _json(CUTS / "cuts.json")
    songs = {s["id"] for s in _json(ROOT / "examples" / "songs" / "songs.json")["songs"]}
    shipped = _shipped_files()
    rows = manifest["cuts"]
    assert sorted(r["vibe"] for r in rows) == sorted(EXAMPLE_VIBES) and len({r["id"] for r in rows}) == 13
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
    assert with_example == set(EXAMPLE_VIBES)  # wet paint left the featured row, and kept its example cut
    assert rows["chrome-mercury"]["example"] == "/examples/cuts/chrome-mercury.mp4" and rows["ocean"]["example"] == ""
    client = TestClient(_ui.create_app())
    served = client.get("/api/vibes").json()["vibes"]
    assert {v["id"] for v in served if v["example"]} == set(EXAMPLE_VIBES)
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


# ------------------------------------------------------------------------------- records, the YouTube kit, provenance


def _script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# what the records and the kit must not carry: an artist's name (the Suno demos' file names), a path on the author's machine
_LEAKS = re.compile(r"XF_|Korn|Prodigy|ZedsDead|Zeds Dead|Slipknot|System of a Down|\bTool\b|(?<![A-Za-z])[A-Za-z]:[\\/]|/Users/|tyson@|AppData|Desktop[\\/]|\.mp3\b")
_SECRETS = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|api[_-]?key\s*[:=]|token\s*[:=]|password|secret", re.I)


def _plain(text: str) -> str:
    """A records file without its recipe codes (base64 can spell anything)."""
    return re.sub(r"xf1\.[A-Za-z0-9_=-]+", "xf1.-", text)


def test_the_as_cut_records_name_the_published_slots_and_every_job_has_a_chain_record():
    from xenoform import simple_recipe

    cuts = {"169": _json(RECORDS / "as_cut_169.json"), "916": _json(RECORDS / "as_cut_916.json")}
    chains = _json(RECORDS / "chains.json")["jobs"]
    jobs = set()
    for key, cut in cuts.items():
        assert cut["aspect"] == ("16:9" if key == "169" else "9:16") and len(cut["slots"]) == 34
        plan = _json(ROOT / "docs" / "demo" / "tools" / "plans" / f"montage_{key}.json")
        assert [s["label"] for s in cut["slots"]] == [row[0] for row in plan["slots"]]  # the plan's slots, in order
        assert cut["slots"][0]["song_in"] == 0.0
        for a, b in zip(cut["slots"], cut["slots"][1:]):
            assert a["song_out"] == b["song_in"] and a["song_out"] > a["song_in"]  # the cuts tile the song
        jobs |= {s["job"] for s in cut["slots"]}
    assert len(jobs) == 62 and jobs <= set(chains)
    assert len(chains) == 98
    shipped = _shipped_files()
    for job, rec in chains.items():
        assert re.fullmatch(r"[0-9a-f]{8}", job) and rec["used_in"] and rec["vibe"] and rec["made"].startswith("2026-10-")
        assert rec["tier"] in ("cloud", "final", "fast", "draft") and rec["engine"] and rec["seconds"] > 0, job
        state = simple_recipe.decode(rec["recipe"])  # the code pastes into the desk
        assert state["vibe"] == rec["vibe"] and not _LEAKS.search(json.dumps(state, ensure_ascii=False)), job
        assert rec["song"]["label"] and (rec["song"]["id"] is None or rec["song"]["id"] in ("glitch-out", "hip-hop-boom-bap", "ambient", "liquid-dnb"))
        assert rec["shots"] and all(sh["end"] > sh["start"] for sh in rec["shots"]), job
        for a, b in zip(rec["shots"], rec["shots"][1:]):
            assert b["start"] >= a["end"] - 0.01, job
        if "clips" in rec:  # a film-pack cut: the clips it joined, by file name
            assert rec["clips"] and all("/" not in c["file"] and "\\" not in c["file"] for c in rec["clips"]), job
            continue
        for sh in rec["shots"]:
            m = sh.get("morph", sh["i"])
            assert (sh["from"], sh["to"]) == (rec["chain"][m], rec["chain"][m + 1]), (job, sh["i"])
        for f in (rec.get("pins") or {}).values():
            assert f in rec["chain"], job
    # a pin of a chain preset is a still of the job it was made on
    for p in _json(ROOT / "configs" / "chain_presets.json")["presets"]:
        job = (p.get("source") or {}).get("job")
        if job:
            assert set(p["pins"].values()) <= set(chains[job]["chain"]), p["id"]
    assert len({f for rec in chains.values() for f in rec.get("chain", [])} & shipped) > 400  # most of what the records name ships


def test_the_records_and_the_youtube_kit_carry_no_artist_no_path_no_secret():
    files = [p for d in (RECORDS, YOUTUBE) for p in d.iterdir() if p.suffix in (".json", ".md", ".txt")]
    files += [p for p in PROVENANCE.iterdir() if p.suffix in (".json", ".md")]
    assert len(files) >= 14
    for p in files:
        text = _plain(p.read_text(encoding="utf-8"))
        assert not _LEAKS.search(text), (p.name, _LEAKS.search(text).group(0))
        assert not _SECRETS.search(text), (p.name, _SECRETS.search(text).group(0))
    # in the cut records the song is a bundled one or neutral
    songs = {rec["song"]["label"] for rec in _json(RECORDS / "chains.json")["jobs"].values()}
    assert "Glitch Out" in songs and "Suno demo, heavy riff (not bundled)" in songs
    # records are small: no media came with them (the budget of the whole of item 5)
    total = sum(p.stat().st_size for d in (RECORDS, YOUTUBE, PROVENANCE) for p in d.iterdir() if p.is_file())
    assert total < 1_000_000
    assert not [p for d in (RECORDS, YOUTUBE, PROVENANCE) for p in d.iterdir() if p.suffix in (".mp4", ".jpg", ".png", ".wav", ".mp3")]


def test_the_youtube_kit_is_the_published_text_and_the_thumbnail_scripts():
    names = sorted(p.name for p in YOUTUBE.iterdir())
    assert names == ["README.md", "demo_description.txt", "long_description.txt", "make_cover_916.py", "make_thumb_song.py",
                     "make_thumbs_xf.py", "metadata.md", "song_description.txt"]
    for p in YOUTUBE.glob("*.py"):
        ast.parse(p.read_text(encoding="utf-8"))  # they run from a folder with frames/ and fonts/, but they parse
    meta = (YOUTUBE / "metadata.md").read_text(encoding="utf-8")
    assert "youtu.be/w6CTnHRR8U0" in meta and "Glitch Out" in meta and "#OpenSourceHiggsfield" in (YOUTUBE / "demo_description.txt").read_text(encoding="utf-8")
    song = (YOUTUBE / "song_description.txt").read_text(encoding="utf-8")
    assert "youtu.be/x_zMu29HfDA" in song and "youtu.be/xpUb5XcHtlQ" in song and "LTX-2.5" in song


def test_the_chain_record_exporter_names_no_song_no_path_and_pairs_each_shot(tmp_path):
    from xenoform import simple_recipe

    export = _script("export_records", ROOT / "scripts" / "export_records.py")
    assert export.neutral_song("Glitch Out (30 s cut)") == ("glitch-out", "Glitch Out", 30)
    assert export.neutral_song("XF_Riff_Korn_01 (30 s cut)") == (None, "Suno demo, heavy riff (not bundled)", 30)
    assert export.neutral_song("hip_hop_boom_bap (20 s cut)")[0] == "hip-hop-boom-bap"
    assert export.neutral_song("Some Band - Some Song.mp3 (30 s cut)")[:2] == (None, "a song that is not bundled")
    state = simple_recipe.decode(_json(ROOT / "examples" / "cuts" / "cuts.json")["cuts"][0]["recipe"])
    state["song"] = "XF_Riff_Korn_01 (30 s cut)"
    jobs = tmp_path / "jobs"
    (jobs / "abcd1234" / "simple").mkdir(parents=True)
    (jobs / "abcd1234" / "meta.json").write_text(json.dumps({
        "created": "2026-10-29T08:35:00+11:00", "song": "XF_Riff_Korn_01 (30 s cut)", "vibe": state["vibe"], "aspect": "9:16",
        "energy_preset": "dense", "quality_tier": "cloud", "recipe": simple_recipe.encode(state)}), encoding="utf-8")
    here = "C:\\Projects\\xenoform-rc2\\work\\ui\\jobs\\abcd1234\\simple\\"
    (jobs / "abcd1234" / "simple" / "simple.json").write_text(json.dumps({
        "engine": "Cloud Final", "open_weights": True, "vibe": state["vibe"], "frames": 72, "fps": 24, "size": [1080, 1920], "seed": 2727,
        "morph_style": "auto", "morph_styles": ["bloom", "melt"], "morph_timing": "smooth", "effects": ["feedback"],
        "look": {"dance_fx": "cool-echo", "stems_path": "C:\\Users\\someone\\stems.json"}, "foreshadow": {"mode": "trace"},
        "macros": {"intensity": 0.4, "speed": 0.5, "chaos": 0.15, "glow": 0.55, "drums": 0.6}, "idea": {"line": "moon jellyfish, comb jelly"},
        "stills": ["cosmic/a.jpg", "cosmic/b.jpg", "cosmic/c.jpg"], "scene_mode": "off", "pins": {"1": "cosmic/b.jpg"},
        "chain": {"morphs": 2, "assign": [0, 1], "reuse": False},
        "fallbacks": [{"capped": {}}, {"cloud_final": "2 of 2 morphs rendered with LTX-2.5 on Comfy Cloud"}],
        "clips": [here + "cloud_full00.mp4"], "audio_path": "C:\\Projects\\xenoform-rc2\\work\\ui\\uploads\\x.wav",
        "shots": [{"index": 0, "start": 0.0, "end": 1.5, "render_s": 2, "speed": 0.75, "morph": 0, "effects": []},
                  {"index": 1, "start": 1.5, "end": 3.0, "render_s": 2, "speed": 0.75, "ease": "in", "morph": 1,
                   "effects": [{"type": "punch", "t": 1.5, "strength": 0.6}]}]}), encoding="utf-8")
    rec = export.record("abcd1234", ["example cut"], jobs)
    text = json.dumps(rec)
    assert not _LEAKS.search(_plain(text)) and "Korn" not in json.dumps(simple_recipe.decode(rec["recipe"]))
    assert simple_recipe.decode(rec["recipe"])["song"] == "Suno demo, heavy riff (30 s cut)"
    assert rec["song"] == {"id": None, "label": "Suno demo, heavy riff (not bundled)", "window_s": 30} and rec["seconds"] == 3.0
    assert rec["look"] == "cool-echo" and rec["foreshadow"] == "trace" and rec["knobs"] == {"intensity": 0.4, "speed": 0.5, "chaos": 0.15, "glow": 0.55}
    assert rec["rendered"].startswith("2 of 2 morphs") and rec["idea"] == "moon jellyfish, comb jelly" and rec["pins"] == {"1": "cosmic/b.jpg"}
    assert [(s["from"], s["to"], s["style"]) for s in rec["shots"]] == [("cosmic/a.jpg", "cosmic/b.jpg", "bloom"), ("cosmic/b.jpg", "cosmic/c.jpg", "melt")]
    assert rec["shots"][1]["ease"] == "in" and rec["shots"][1]["effects"][0]["type"] == "punch" and rec["morph_styles"] == ["bloom", "melt"]
    # a cut of film clips lists the clips by file name
    film = json.loads((jobs / "abcd1234" / "simple" / "simple.json").read_text(encoding="utf-8"))
    film.update({"source": "clips", "stills": [], "own_clips": [{"path": "C:\\Projects\\own\\01_metropolis_robot.mp4", "seconds": 24.0, "label": "Metropolis robot"}],
                 "shots": [{"index": 0, "start": 0.0, "end": 2.0, "render_s": 3, "source": "01_metropolis_robot.mp4", "clip_start": 13.0, "effects": []}]})
    (jobs / "abcd1234" / "simple" / "simple.json").write_text(json.dumps(film), encoding="utf-8")
    frec = export.record("abcd1234", ["film"], jobs)
    assert frec["clips"] == [{"file": "01_metropolis_robot.mp4", "label": "Metropolis robot", "seconds": 24.0}] and "chain" not in frec
    assert not _LEAKS.search(_plain(json.dumps(frec)))
    # the writer keeps a shot on a line and parses back to the same object
    obj = {"a": 1, "b": [1, 2], "c": [{"x": 1}, {"y": [2]}], "d": {}, "e": []}
    assert json.loads(export.fmt(obj)) == obj and export.fmt({"s": [{"x": 1}, {"x": 2}]}).count("\n") == 5


def test_the_first_six_vibes_stills_are_traced_to_the_overnight_run():
    plan = _json(PROVENANCE / "plan.json")
    seeds = _json(PROVENANCE / "objects_seeds.json")["objects"]
    assert len(seeds) == 116 == len(plan["objects"]) + len(plan["textures"])
    assert sum(1 for s in seeds.values() if s["how"] == "reroll") == 12 and all(s["how"] != "other" for s in seeds.values())
    klein = _json(PROVENANCE / "klein_edits.json")
    assert len(klein["edits"]) == 117 and klein["seed"] == 77 and set(klein["prompts"]) == set(plan["materials"]) - {"gr"}
    assert all("{M}" not in text and "Change only its material" in text for text in klein["prompts"].values())
    clips = _json(PROVENANCE / "clips.json")
    assert len(clips["clips"]) == 93 and len(clips["not_rendered"]) == 4 and all("ltx-2.3" in c["model"] for c in clips["clips"])
    # the five clips the 19 October showcase reel was cut from are among them
    old = {"h08_rose_to_lotus_to_jellyfish_black_glass", "h02_droplet_swarm_to_butterfly_to_swallow_gr", "m02_tarot_card_to_orb_gr",
           "m13_torus_knot_to_mobius_chrome", "m22_lotus_to_jellyfish_iridescent"}
    assert old <= {c["id"] for c in clips["clips"]}
    # every one of the 77 original rows says which still, which seed and which models, and was matched to that still
    lineage = _json(PROVENANCE / "lineage.json")
    rows = {r["file"]: r for r in lineage["rows"]}
    objects = _json(STATIC / "objects" / "objects.json")
    originals = [(pool, r) for pool in ("liquid-gold", "bloom", "neon-night", "ocean", "cosmic", "black") for r in objects[pool]
                 if r["source"].startswith("library/gpu_objects/")]
    assert len(originals) == 77 == len(rows) and lineage["summary"]["rows"] == 77 and lineage["summary"]["graded_rows"] == 60
    build = _script("provenance_build", PROVENANCE / "build.py")
    for pool, r in originals:
        lin = rows[r["file"]]
        assert (STATIC / "objects" / r["file"]).is_file() and lin["pool"] == pool
        assert lin["seed"] == seeds[lin["object"]]["seed"] and f"seed {lin['seed']}," in r["source"], r["file"]
        assert "Z-Image Turbo" in r["source"] and "Apache 2.0" in r["source"] and "lineage.json" in r["source"], r["file"]
        assert (lin["material"] == "gr") == ("Klein" not in r["source"]), r["file"]
        assert (pool == "black") == ("cut out onto pure black" in r["source"]), r["file"]
        assert lin["match"]["inliers"] >= 12 and (lin["material"] == "gr" or lin["material"] in plan["materials"])
        if pool != "black":
            assert lin["grade_psnr_db"] >= 30, r["file"]  # grade.py applied to the run's still gives the shipped jpg
        name, mat = build.split_material(r["source"].split("library/gpu_objects/")[1].split(".png")[0], plan["materials"])
        assert (name, mat) == (lin["object"], lin["material"])
        assert build.source_text(pool, f"{name}_{mat}", name, mat, lin["seed"]) == r["source"], r["file"]  # `stamp` is idempotent
    assert len(lineage["summary"]["reframed"]) == 4 and all(f.startswith("black/") for f in lineage["summary"]["reframed"])


def test_the_provenance_compiler_reads_a_run_folder(tmp_path):
    build = _script("provenance_build2", PROVENANCE / "build.py")
    plan = {"objects": [{"name": "rose", "seed": 1057}, {"name": "horn", "seed": 3036}], "textures": [{"name": "tex_flow", "seed": 1201}],
            "materials": {"gr": "ferrofluid", "black_glass": "obsidian", "chrome": "chrome"}, "clips": [{"id": "m00_a_to_b_gr"}, {"id": "m01_c_to_d_gr"}],
            "heroes": []}
    (tmp_path / "objects").mkdir()
    (tmp_path / "klein").mkdir()
    (tmp_path / "clips").mkdir()
    (tmp_path / "cull.json").write_text(json.dumps({"reroll": {"horn": {"seed": 3037, "prompt_add": "Side view."}}}), encoding="utf-8")
    for name, rec in (("rose", {"seed": 1057}), ("horn", {"seed": 3037, "reroll": True}), ("tex_flow", {"seed": 2201})):
        (tmp_path / "objects" / f"{name}.png.json").write_text(json.dumps(rec), encoding="utf-8")
    got = build.compile_objects(tmp_path, plan)["objects"]
    assert got["rose"]["how"] == "planned" and got["horn"] == {"seed": 3037, "planned": 3036, "how": "reroll", "kind": "object", "prompt_add": "Side view."}
    assert got["tex_flow"]["how"] == "retry" and got["tex_flow"]["kind"] == "texture"  # the plan's seed + 1000
    for f in ("ov_rose_black_glass.png", "ov_mid_pour_chrome.png"):
        (tmp_path / "klein" / f).write_bytes(b"x")
    edits = build.compile_klein(tmp_path, plan)
    assert [(e["kind"], e["what"], e["material"], e["reference"]) for e in edits["edits"]] == [
        ("mid", "pour", "chrome", "g2_pour.png"), ("object", "rose", "black_glass", "ov_rose_gr.png")]
    assert "obsidian" in edits["prompts"]["black_glass"] and "gr" not in edits["prompts"]
    take = {"id": "m00_a_to_b_gr", "A": "a", "B": "b", "recipe": "ribbon", "material": "gr", "guide": None, "seed": 8000, "seed_used": 8500,
            "res": [768, 448], "fps": 24, "L": 121, "prompt": "p", "guides": [["ov_a_gr.png", 0, 1.0]], "model": "ltx-2.3-22b-distilled-fp8",
            "compute_s": 90.0, "gate": {"ok": True, "why": []}, "diffs": [1, 2, 3]}
    (tmp_path / "clips" / "m00_a_to_b_gr.mp4.json").write_text(json.dumps(take), encoding="utf-8")
    (tmp_path / "clips" / "m00_a_to_b_gr_s8000.mp4.json").write_text(json.dumps(dict(take, seed_used=8000, gate={"ok": False, "why": ["midcut"]})), encoding="utf-8")
    (tmp_path / "clips" / "m00_a_to_b_gr_s8500.mp4.json").write_text(json.dumps(take), encoding="utf-8")
    (tmp_path / "clips" / "m01_c_to_d_gr.mp4.failed").write_text("missing ov_c_gr.png", encoding="utf-8")
    out = build.compile_clips(tmp_path, plan)
    clip = out["clips"][0]
    assert len(out["clips"]) == 1 and clip["from"] == "a" and clip["to"] == "b" and clip["via"] is None and clip["seed_used"] == 8500
    assert clip["takes"] == [{"seed": 8000, "ok": False, "why": ["midcut"]}, {"seed": 8500, "ok": True, "why": []}] and "diffs" not in clip
    assert out["not_rendered"] == [{"id": "m01_c_to_d_gr", "why": "missing ov_c_gr.png"}]
    assert build.split_material("droplet_swarm_gr", plan["materials"]) == ("droplet_swarm", "gr")


def test_credits_and_licences_say_what_is_traced_and_what_is_not():
    credits = (ROOT / "CREDITS.md").read_text(encoding="utf-8")
    row = next(line for line in credits.splitlines() if line.startswith("| liquid-gold, bloom, neon-night, ocean, cosmic (12 each) and black (17)"))
    assert "scripts/vibe_objects/provenance/" in row and "unrecorded" not in row
    assert "Z-Image Turbo" in row and "FLUX.2 Klein 4B" in row and "lineage.json" in row and "18 and 19 October 2026" in row
    # what nothing traces still says so, and only that
    unrecorded = [line.split("|")[1].strip() for line in credits.splitlines() if "Origin unrecorded" in line]
    assert unrecorded == ["`neon-night.jpg`", "`src/xenoform/ui_static/poster.jpg`"]
    assert "origin unrecorded" in credits  # the policy sentence
    licences = (ROOT / "docs" / "LICENCES.md").read_text(encoding="utf-8")
    assert "scripts/vibe_objects/provenance/" in licences and "Only `neon-night.jpg`" in licences and "FLUX.2 Klein 4B" in licences
    readme = (ROOT / "scripts" / "vibe_objects" / "README.md").read_text(encoding="utf-8")
    assert "provenance/" in readme and "ship_grown.py" in readme and "make_card.py" in readme


# --------------------------------------------------------------------------------------------- the library strips

STRIPS = ("bioluminescent", "black", "botanical", "brutalist", "chrome-mercury", "cosmic", "cyberspace-95", "ferrofluid", "ice-crystal",
          "ink-wash", "iridescent-glass", "liquid-gold", "low-poly", "neon-noir", "none", "ocean", "origami-noir", "porcelain-kintsugi",
          "porcelain-marble", "risograph", "shadow-self", "y2k-chrome")
KEPT = ("lava-obsidian", "odd-machine", "wet-paint", "paper-summer", "bloom", "neon-night")  # orb to nautilus, or own-stills, as they were
SHOTS = ("wide", "medium", "close", "reveal")


def test_the_22_re_cut_strips_are_cloud_morphs_of_each_vibes_own_stills():
    pack = _json(ROOT / "configs" / "clip_pack.json")
    vibes, chains, shipped = pack["vibes"], _json(RECORDS / "chains.json")["jobs"], _shipped_files()
    assert len(STRIPS) == 22 and sorted(v for v, e in vibes.items() if "source_clip" in e) == sorted(STRIPS)
    assert set(vibes) == set(STRIPS) | set(KEPT) and "31 October 2026" in pack["note"] and "LTX-2.5" in pack["note"]
    for vibe in STRIPS:
        entry = vibes[vibe]
        assert list(entry) == ["clips", "source_morph", "source_clip", "qa", "checked"], vibe  # a fresh entry: no old autotune score
        assert entry["clips"] == [f"library/{vibe}/{shot}.mp4" for shot in SHOTS] and entry["qa"] is True
        src = entry["source_clip"]
        a, b = src["from"], src["to"]
        assert a in shipped and b in shipped and a != b and a.startswith(vibe + "/") and b.startswith(vibe + "/"), vibe
        assert entry["source_morph"] == f"{Path(a).stem} -> {Path(b).stem}", vibe
        assert "LTX-2.5" in src["engine"] and "Comfy Cloud" in src["engine"] and "2026-10-31" in entry["checked"], vibe
        rec = chains[src["job"]]  # the job's record has that shot, between those two stills, and says the strip was cut from it
        shot = next(s for s in rec["shots"] if s["i"] == src["shot"])
        assert (shot["from"], shot["to"]) == (a, b) and rec["vibe"] == vibe and rec["tier"] == "cloud", vibe
        assert any(u.startswith(f"library strip of {vibe}") for u in rec["used_in"]), vibe
        for name in SHOTS:
            mp4, jpg = STATIC / "library" / vibe / f"{name}.mp4", STATIC / "library" / vibe / f"{name}.jpg"
            assert 500 < mp4.stat().st_size <= 1_200_000 and jpg.stat().st_size > 4_000, (vibe, name)
    # lava-obsidian, odd-machine and wet-paint (un-featured or vetoed looks) and the three own-stills strips stay as they were
    for vibe in KEPT:
        assert "source_clip" not in vibes[vibe] and vibes[vibe]["source_morph"] and vibes[vibe]["clips"], vibe
    assert vibes["wet-paint"]["source_morph"] == "00_orb -> 01_nautilus" and vibes["bloom"]["source_morph"] == "00_dandelion_iridescent -> 01_lotus_iridescent"
    # the repo stays about as heavy as the strips it replaced (the 22 were 18 MB with posters): 4 s strips at CRF 30
    total = sum(p.stat().st_size for vibe in STRIPS for p in (STATIC / "library" / vibe).iterdir())
    assert 10_000_000 < total < 24_000_000, total


def test_each_re_cut_strip_is_four_768x432_cuts_of_one_clip_and_the_reveal_runs_backwards():
    if not shutil.which("ffprobe"):
        return  # sizes and posters are checked above; the picture format needs ffprobe

    def probe(path):
        out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
                                       "-of", "json", str(path)], text=True)
        s = json.loads(out)["streams"][0]
        return s["width"], s["height"], s["r_frame_rate"], int(s["nb_frames"])

    for vibe in STRIPS:
        got = {name: probe(STATIC / "library" / vibe / f"{name}.mp4") for name in SHOTS}
        assert {g[:3] for g in got.values()} == {(768, 432, "24/1")}, vibe
        assert len({g[3] for g in got.values()}) == 1 and got["wide"][3] in (49, 97), (vibe, got)  # 2 s or 4 s of the morph, the same four times


def test_the_strip_cutter_makes_four_cuts_a_poster_each_and_a_fresh_pack_entry(tmp_path, monkeypatch):
    strip = _script("strip_from_clip", ROOT / "scripts" / "vibe_objects" / "strip_from_clip.py")
    land, tall = {"w": 1024, "h": 576, "frames": 97}, {"w": 576, "h": 1024, "frames": 97}
    assert strip.vf_for(land, 1.0, False) == "scale=768:432:flags=lanczos,format=yuv420p"
    assert strip.vf_for(land, 1.5, True) == "crop=iw/1.5:ih/1.5,scale=768:432:flags=lanczos,format=yuv420p,reverse"
    assert strip.vf_for(tall, 1.0, False).startswith("crop=576:324:0:(ih-324)/2,scale=768:432")  # a portrait clip: its centre 16:9 band
    assert strip.CUTS["wide"] == (1.0, False) and strip.CUTS["reveal"] == (1.0, True) and strip.CRF_FROM >= 26
    pack = tmp_path / "clip_pack.json"
    pack.write_text(json.dumps({"version": 1, "note": "n", "vibes": {"x": {"clips": [], "source_morph": "00_orb -> 01_nautilus", "autotune_score": 74.0,
                                                                              "qa": True, "checked": "old"}, "y": {"clips": ["a"]}}}), encoding="utf-8")
    monkeypatch.setattr(strip, "PACK", pack)
    args = argparse.Namespace(src="a", dst="b", source=json.dumps({"job": "abcd1234", "shot": 3}), checked="re-cut", vibe="x")
    strip.update_pack("x", args, True)
    vibes = json.loads(pack.read_text(encoding="utf-8"))["vibes"]
    assert list(vibes["x"]) == ["clips", "source_morph", "source_clip", "qa", "checked"] and vibes["y"] == {"clips": ["a"]}  # only x changed
    assert vibes["x"]["source_morph"] == "a -> b" and vibes["x"]["source_clip"] == {"job": "abcd1234", "shot": 3} and "autotune_score" not in vibes["x"]
    assert vibes["x"]["clips"] == [f"library/x/{shot}.mp4" for shot in SHOTS] and vibes["x"]["checked"] == "re-cut"
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        return
    clip = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1024x576:rate=24:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(clip)], check=True)
    done = strip.cut(clip, tmp_path / "out")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted(f"{n}.{ext}" for n in SHOTS for ext in ("mp4", "jpg"))
    assert done["frames"] == 24 and done["size"] == [1024, 576] and set(done["crf"]) == set(SHOTS)
    for p in (tmp_path / "out").glob("*.mp4"):
        assert strip.MIN_BYTES < p.stat().st_size <= strip.MAX_BYTES, p.name
    for p in (tmp_path / "out").glob("*.jpg"):
        assert p.stat().st_size > strip.MIN_POSTER, p.name


def test_credits_and_docs_say_what_the_strips_are():
    credits = (ROOT / "CREDITS.md").read_text(encoding="utf-8")
    row = next(line for line in credits.splitlines() if line.startswith("| The 22 vibes "))
    assert all(vibe in row for vibe in STRIPS) and "strip_from_clip.py" in row and "LTX-2.5" in row and "11 August 2026" in row and "source_clip" in row
    kept = next(line for line in credits.splitlines() if line.startswith("| lava-obsidian, odd-machine, wet-paint |"))
    assert "LTX-Video 0.9.5" in kept and "orb to nautilus" in kept
    assert "| liquid-gold, paper-summer," not in credits  # liquid-gold, ocean and cosmic moved to the Cloud row
    licences = (ROOT / "docs" / "LICENCES.md").read_text(encoding="utf-8")
    assert "strip_from_clip.py" in licences and "22 vibes were re-cut on 31 October 2026" in licences and "Comfy Cloud" in licences
    assert "strip_from_clip.py" in (ROOT / "README.md").read_text(encoding="utf-8") and "strip_from_clip.py" in (ROOT / "docs" / "VIBES.md").read_text(encoding="utf-8")
    assert "strip_from_clip.py" in (ROOT / "scripts" / "vibe_objects" / "README.md").read_text(encoding="utf-8")
