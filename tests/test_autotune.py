import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "autotune"))


def test_autotune_space_targets_real_graph_nodes():
    import autotune
    graph = json.loads(autotune.GRAPH.read_text(encoding="utf-8"))
    for node in ("3", "4", "8", "9", "11", "13", "14", "19", "21", "22"):
        assert node in graph
    assert graph["14"]["class_type"] == "CFGGuider" and "cfg" in graph["14"]["inputs"]
    assert graph["22"]["class_type"] == "LTXVAddGuide" and graph["22"]["inputs"]["frame_idx"] == -1
    assert autotune.DEFAULT["steps"] in autotune.SPACE["steps"]
    assert all(autotune.DEFAULT[k] in v for k, v in autotune.SPACE.items())
    assert autotune.key(autotune.DEFAULT) == "s20_c3_k18_vibe_512x288_g1"


def test_app_reads_autotune_settings_and_blocklist(tmp_path, monkeypatch):
    from xenoform import morph_pass as mp
    pool = mp.manifest()["neon-night"]
    first, second = pool[0]["file"], pool[1]["file"]
    cfg = {"vibes": {"neon-night": {"steps": 16, "cfg": 2.0, "img_compression": 0}}, "bad_pairs": [[first, second]]}
    path = tmp_path / "autotune.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("XENO_AUTOTUNE", str(path))
    monkeypatch.delenv("XENO_MORPH_STEPS", raising=False)
    assert mp.tuned("neon-night") == {"steps": 16, "cfg": 2.0, "img_compression": 0}
    assert mp.tuned("ocean") == {}
    vibe, stills = mp.pick_stills({"vibe": "neon-night"}, 10)
    files = [s["file"] for s in stills]
    assert files[0] == first and files[1] != second
    assert len(set(files)) == 10
    pairs = list(zip(files, files[1:]))
    assert (first, second) not in pairs


def test_without_autotune_file_nothing_changes(tmp_path, monkeypatch):
    from xenoform import morph_pass as mp
    monkeypatch.setenv("XENO_AUTOTUNE", str(tmp_path / "missing.json"))
    assert mp.tuned("bloom") == {}
    _, stills = mp.pick_stills({"vibe": "bloom"}, 12)
    assert [s["file"] for s in stills] == [o["file"] for o in mp.manifest()["bloom"]]
