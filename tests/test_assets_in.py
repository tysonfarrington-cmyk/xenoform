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
