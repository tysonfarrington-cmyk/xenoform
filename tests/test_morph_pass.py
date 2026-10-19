import json
from pathlib import Path

from xenoform import morph_pass as mp

ROOT = Path(__file__).resolve().parents[1]


def test_every_vibe_has_its_own_stills_on_disk():
    pools = mp.manifest()
    assert {"liquid-gold", "paper-summer", "bloom", "neon-night", "ocean", "cosmic"} <= set(pools)
    seen = set()
    for vibe, items in pools.items():
        assert len(items) >= 12
        for item in items:
            assert (mp.OBJECTS / item["file"]).is_file()
            assert item["file"] not in seen
            seen.add(item["file"])
        assert vibe in mp.VIBE_LOOK


def test_no_retro_or_sci_fi_props():
    banned = ("rocket", "sputnik", "satellite", "film reel", "rotary", "vintage", "vinyl", "ringed planet", "gear", "clock", "phone")
    for items in mp.manifest().values():
        for item in items:
            assert not any(word in item["noun"] for word in banned), item


def test_vibe_falls_back_to_palette():
    assert mp.vibe_for({"vibe": "ocean"}) == "ocean"
    assert mp.vibe_for({"palette": "gold"}) == "liquid-gold"
    assert mp.vibe_for({"vibe": "nope", "palette": "neutral"}) == "paper-summer"


def test_story_noun_leads_the_chain():
    vibe, stills = mp.pick_stills({"vibe": "ocean", "brief": "A manta ray glides"}, 8)
    assert vibe == "ocean" and stills[0]["noun"] == "manta ray"
    _, long = mp.pick_stills({"vibe": "cosmic"}, 20)
    assert len(long) == 20
    assert all(a["file"] != b["file"] for a, b in zip(long, long[1:]))
    _, clip = mp.pick_stills({"vibe": "neon-night"}, 10)
    assert len({s["file"] for s in clip}) == 10  # 9 shots, no repeats


def test_ltx25_is_picked_only_when_its_files_exist(tmp_path, monkeypatch):
    monkeypatch.delenv("XENO_MORPH_ENGINE", raising=False)
    assert mp.ltx25_present(tmp_path) is False
    for folder, name in mp.LTX25_FILES:
        (tmp_path / folder).mkdir(exist_ok=True)
        (tmp_path / folder / name).write_bytes(b"")
    assert mp.ltx25_present(tmp_path) is True
    monkeypatch.setenv("XENO_MORPH_ENGINE", "ltx095")
    assert mp.pick_engine() == "ltx095"


def test_ltx25_graph_mirrors_the_morph_node_ids():
    graph = json.loads((ROOT / "workflows" / "ltx25_morph_api.json").read_text(encoding="utf-8"))
    assert graph["1"]["class_type"] == "UNETLoader" and "ltx-2.5" in graph["1"]["inputs"]["unet_name"]
    assert graph["6"]["class_type"] == graph["7"]["class_type"] == "LoadImage"
    assert sorted(graph[k]["inputs"]["frame_idx"] for k in ("10", "22")) == [-1, 0]
    assert graph["19"]["class_type"] == "SaveVideo" and graph["25"]["class_type"] == "LTXVEmptyLatentAudio"


def test_handoffs_snap_to_beats_and_cover_the_clip():
    scenes = [{"start": 0, "end": 2.9}, {"start": 2.9, "end": 6.1}, {"start": 6.1, "end": 10.0}]
    beats = [0.0, 1.5, 3.0, 4.5, 6.0, 7.5, 9.0]
    assert mp.handoffs(scenes, beats, 10.0) == [0.0, 3.0, 6.0, 10.0]


def test_gen_length_is_8k_plus_1_and_capped():
    for n in (2, 25, 49, 68, 69, 200):
        L = mp.gen_length(n)
        assert (L - 1) % 8 == 0 and mp.MIN_LEN <= L <= mp.MAX_LEN
        assert L >= min(n, mp.MAX_LEN)


def test_morph_graph_guides_both_ends_and_saves():
    graph = json.loads((ROOT / "workflows" / "xenoform_morph.json").read_text(encoding="utf-8"))
    guides = [n for n in graph.values() if isinstance(n, dict) and n.get("class_type") == "LTXVAddGuide"]
    assert sorted(g["inputs"]["frame_idx"] for g in guides) == [-1, 0]
    assert graph["6"]["class_type"] == graph["7"]["class_type"] == "LoadImage"
    assert graph["19"]["class_type"] == "SaveVideo"
    assert graph["9"]["class_type"] == "EmptyLTXVLatentVideo"


def test_fit_keeps_both_endpoints():
    import numpy as np

    frames = np.arange(73)[:, None, None, None] * np.ones((1, 2, 2, 3), np.uint8)
    out = mp._fit(frames, 69)
    assert len(out) == 69 and out[0, 0, 0, 0] == 0 and out[-1, 0, 0, 0] == 72
