"""The node pack's nodes (comfy_pack/nodes.py), each on the demo song: inputs to outputs, and the morph request against
the one the desk itself fills in (cloud_morph._local_clips through workflows/xenoform_morph.json)."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfy_pack import assemble as A  # noqa: E402
from comfy_pack import song as S  # noqa: E402
from comfy_pack import stills  # noqa: E402
from comfy_pack import storyboard as SB  # noqa: E402
from comfy_pack.nodes import NODE_CLASS_MAPPINGS as NODES  # noqa: E402

DEMO = ROOT / "examples" / "demo.wav"


@pytest.fixture(scope="module")
def demo_song():
    out = NODES["XenoformSongAnalysis"]().analyse("demo.wav", 12, "numpy")
    return out["result"][0]


def _board(song, **kw):
    args = dict(vibe="chrome-mercury", idea="", energy="dense", forms=2, speed=0.5, chaos=0.3, intensity=0.5,
                morph_style="auto", morph_timing="smooth", pace="viscous", aspect="16:9", seed=2727)
    args.update(kw)
    return NODES["XenoformStoryboard"]().plan(song, **args)


def test_every_node_declares_what_comfyui_reads():
    for name, cls in NODES.items():
        spec = cls.INPUT_TYPES()
        assert set(spec) <= {"required", "optional", "hidden"}
        assert len(cls.RETURN_TYPES) == len(cls.RETURN_NAMES)
        assert callable(getattr(cls(), cls.FUNCTION)) and cls.CATEGORY == "Xenoform"
    assert NODES["XenoformMorphTimeline"].OUTPUT_NODE and NODES["XenoformAssemble"].OUTPUT_NODE
    assert NODES["XenoformStoryboard"].INPUT_TYPES()["required"]["seed"][1]["control_after_generate"] is False
    assert "demo.wav" in NODES["XenoformSongAnalysis"].INPUT_TYPES()["required"]["song"][0]


def test_song_analysis_reads_the_demo(demo_song):
    f = demo_song["features"]
    assert f["duration"] == pytest.approx(12.0) and f["tempo"] == pytest.approx(120.0, abs=0.1)
    assert len(f["beats"]) == 18 and demo_song["drop"] == pytest.approx(5.5015, abs=1e-3)
    assert [s["label"] for s in f["sections"]] == ["calm", "build", "drop", "release"]
    assert demo_song["path"].endswith("demo.wav") and demo_song["engine"] == "numpy"
    again = NODES["XenoformSongAnalysis"]().analyse("demo.wav", 12, "numpy", features_json=str(ROOT / "examples" / "demo_features.json"))
    assert again["result"][0]["engine"] == "features.json" and again["result"][3] == pytest.approx(12.0)
    assert NODES["XenoformSongAnalysis"].IS_CHANGED("demo.wav", 12, "numpy") == NODES["XenoformSongAnalysis"].IS_CHANGED("demo.wav", 12, "numpy")


def test_storyboard_plans_the_demo_on_the_beat(demo_song):
    out = _board(demo_song)
    board, text, morphs = out["result"]
    assert morphs == 2 and board["schema"] == SB.SCHEMA
    a, b = board["shots"]
    assert (a["start"], a["end"], b["end"]) == (0.0, pytest.approx(5.5015), 12.0)  # the drop is the cut
    assert (a["style"], b["style"]) == ("bloom", "shatter")
    assert [s["noun"] for s in board["stills"]] == ["orb", "nautilus", "lotus"]
    assert a["length"] == 121 and a["frames"] + b["frames"] == 288
    assert "2 shots on the beat" in text and out["ui"]["text"] == [text]
    beats = set(round(x, 4) for x in demo_song["features"]["beats"])
    auto = _board(demo_song, forms=0)["result"][0]
    assert len(auto["shots"]) == 9 and all(round(s["start"], 4) in beats for s in auto["shots"][1:])
    named = _board(demo_song, idea="a jellyfish in the dark")["result"][0]
    assert named["stills"][0]["noun"] == "jellyfish"
    wide = _board(demo_song, aspect="9:16")["result"][0]
    assert wide["size"] == [320, 576] and wide["out_size"] == [432, 768]


def test_a_long_song_is_one_morph_a_shot_and_no_object_twice():
    feats = json.loads((ROOT / "tests" / "fixtures" / "analyses" / "liquid-dnb.features.json").read_text(encoding="utf-8"))
    song = S.song_value(feats, name="liquid-dnb")
    board = SB.build(song, vibe="chrome-mercury", energy="dense")
    files = [s["file"] for s in board["stills"]]
    assert board["plan"]["long_song"] and len(files) == len(set(files)) == len(board["shots"]) + 1
    assert all(s["render_s"] == board["plan"]["clip_s"] for s in board["shots"])
    cuts = board["plan"]["cuts"]
    moved = SB.apply_edits(board, {**SB.empty_edits(board), "cuts": cuts[:5] + [round((cuts[4] + cuts[5]) / 2, 4)] + cuts[5:]}, song)
    assert len(moved["shots"]) == len(board["shots"]) + 1  # a cut added between two
    assert all(s["render_s"] == board["plan"]["clip_s"] for s in moved["shots"])  # the chain's length, as the desk renders it


def test_morph_pair_is_the_desks_request_value_for_value(demo_song, monkeypatch, tmp_path):
    from xenoform import cloud_morph
    from xenoform import morph_pass as mp

    board = _board(demo_song, forms=0, chaos=0.7)["result"][0]
    graphs = []

    class WF:
        def __init__(self):
            self.sets = {}
            graphs.append(self.sets)

        def set_input(self, node, key, value):
            self.sets[(node, key)] = value

    class Job:
        id = "job"

        def result(self):
            raise KeyboardInterrupt  # every graph is filled in and submitted: stop before any wait

        def refresh(self):
            pass

    class Client:
        class assets:
            @staticmethod
            def from_file(p):
                return p

        class workflows:
            @staticmethod
            def from_file(p):
                return WF()

        def submit(self, wf):
            return Job()

    monkeypatch.setattr(mp, "_graph_path", lambda work, engine="ltx095": tmp_path / "g.json")
    rows = [{**s, "path": s["path"]} for s in board["stills"]]
    shots = [{"seconds": s["seconds"], "render_s": s["render_s"]} for s in board["shots"]]
    with pytest.raises(KeyboardInterrupt):
        cloud_morph._local_clips(shots, rows, tmp_path, {}, board["seed"], board["vibe"], client=Client(),
                                 styles=[s["style"] for s in board["shots"]])
    assert len(graphs) == len(board["shots"])
    for i, sets in enumerate(graphs):
        out = NODES["XenoformMorphPair"]().pair(board, i)["result"]
        image_a, image_b, prompt, negative, fps, w, h, length, steps, seed, cfg, ca, cb, gb, frames, request = out
        assert prompt == sets[("3", "text")] and negative == sets[("4", "text")]
        assert (w, h, length) == (sets[("9", "width")], sets[("9", "height")], sets[("9", "length")])
        assert steps == sets[("11", "steps")] and seed == sets[("13", "noise_seed")] and fps == sets[("18", "fps")]
        assert cfg == sets.get(("14", "cfg"), 3.0) and gb == sets.get(("22", "strength"), 1.0)
        assert (ca, cb) == (sets.get(("8", "img_compression"), 18), sets.get(("21", "img_compression"), 18))
        assert sets[("6", "image")] == board["stills"][i]["path"] and sets[("7", "image")] == board["stills"][i + 1]["path"]
        assert frames == board["shots"][i]["frames"] and json.loads(request)["index"] == i
        assert tuple(image_a.shape[-1:]) == (3,) and image_a.shape[0] == 1 and float(image_a.max()) <= 1.0
        assert str(image_a.dtype) == "torch.float32" and image_b.shape == image_a.shape
    portrait = NODES["XenoformMorphPair"]().pair(_board(demo_song, aspect="9:16")["result"][0], 0)["result"]
    assert tuple(portrait[0].shape) == (1, 576, 320, 3) and (portrait[5], portrait[6]) == (320, 576)
    with pytest.raises(ValueError):
        NODES["XenoformMorphPair"]().pair(board, len(board["shots"]))


def test_the_timeline_lays_its_edits_over_the_plan(demo_song):
    board = _board(demo_song, forms=0)["result"][0]
    node = NODES["XenoformMorphTimeline"]()
    plain = node.edit(board, "")
    assert plain["result"][0] is board  # no edits: the plan as it came
    view = json.loads(plain["ui"]["xenoform_board"][0])
    assert view["edits"]["format"] == SB.EDITS and view["plan_cuts"] == board["plan"]["cuts"]
    cuts = board["plan"]["cuts"]
    edits = {"format": SB.EDITS, "song_key": board["song"]["key"], "cuts": cuts[:3] + [9.0],
             "shots": {"0.000": {"style": "spin", "timing": "snap", "seed": 99}, f"{cuts[1]:.3f}": {"hold": True}},
             "intensity": [[0.0, 0.2], [6.0, 1.0]], "pins": [[cuts[1], "chrome-mercury/11_butterfly.jpg"]]}
    out = node.edit(board, json.dumps(edits))["result"][0]
    starts = [round(s["start"], 4) for s in out["shots"]]
    assert starts == [0.0] + [round(c, 4) for c in cuts[:3]] + [9.0]
    first = out["shots"][0]
    assert (first["style"], first["timing_mode"], first["seed"], first["fx_intensity"]) == ("spin", "snap", 99, 0.2)
    assert first["timing"]["hits"] and out["shots"][2]["hold"] and out["shots"][2]["timing"] is None
    assert out["stills"][2]["file"] == "chrome-mercury/11_butterfly.jpg" and out["stills"][2]["pinned"]
    assert len({s["file"] for s in out["stills"]}) == len(out["stills"])  # the pin did not show a still twice
    assert out["shots"][-1]["fx_intensity"] == 1.0 and out["edits"] == edits
    other = node.edit(board, json.dumps({**edits, "song_key": "another-song"}))["result"][0]
    assert [s["start"] for s in other["shots"]] == [s["start"] for s in board["shots"]] and "another song" in other["notes"][-1]
    assert node.edit(board, "{not json")["result"][0] is board


def test_assemble_cuts_the_morphs_on_the_beat_with_the_song(demo_song, tmp_path, monkeypatch):
    board = _board(demo_song)["result"][0]
    monkeypatch.setenv("XENO_PACK_OUT", str(tmp_path))
    clips = {}
    for i, s in enumerate(board["shots"]):  # stand-in morphs: grey ramps the length LTX would render
        ramp = np.linspace(0.0, 1.0, s["length"], dtype=np.float32)[:, None, None, None]
        clips[f"morph_{i + 1}"] = np.broadcast_to(ramp, (s["length"], 288, 512, 3)).copy()
    out = NODES["XenoformAssemble"]().cut(board, "stop", True, "xenoform/test", **clips)
    path = Path(out["result"][0])
    assert path.is_file() and path.parent == tmp_path / "xenoform" and path.name == "test_00001.mp4"
    assert out["ui"]["images"] == [{"filename": path.name, "subfolder": "xenoform", "type": "output"}]
    assert out["ui"]["animated"] == (True,)
    import shutil

    if shutil.which("ffprobe"):
        probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                                "stream=codec_type,nb_read_frames,width,height", "-of", "json", str(path)],
                               capture_output=True, text=True, check=True)
        streams = {s["codec_type"]: s for s in json.loads(probe.stdout)["streams"]}
        assert int(streams["video"]["nb_read_frames"]) == 288 and "audio" in streams
        assert (streams["video"]["width"], streams["video"]["height"]) == (768, 432)
    one = NODES["XenoformAssemble"]().cut(board, "stop", False, "xenoform/test", morph_1=clips["morph_1"])
    assert "1 of 2 shots" in one["ui"]["text"][0] and one["result"][0].endswith("test_00002.mp4")
    sketch = NODES["XenoformAssemble"]().cut(board, "stills", False, "xenoform/test", morph_1=clips["morph_1"])
    assert "1 sketched from stills" in sketch["ui"]["text"][0]
    with pytest.raises(ValueError):
        NODES["XenoformAssemble"]().cut(board, "stop", True, "xenoform/test")


def test_shot_indices_keep_the_handoffs_on_the_stills():
    from xenoform import cloud_morph

    shot = {"start": 1.0, "end": 3.0, "frames": 48, "ease": "in",
            "effects": [{"type": "stutter", "t": 1.5, "frames": 2, "repeat": 3}, {"type": "hold", "t": 2.0, "len": 0.12},
                        {"type": "skip", "t": 2.2, "amount": 0.3}, {"type": "reverse", "t": 2.5, "len": 0.4}]}
    for n_src in (49, 73, 121):
        got = A.shot_indices(shot, n_src)
        assert got[0] == 0 and got[-1] == n_src - 1
        assert list(got) == list(cloud_morph.shot_indices(shot, n_src))
    assert list(A.shot_indices({**shot, "hold": True}, 49)) == [0] * 48


def test_routes_serve_only_the_catalogue_and_the_songs():
    from comfy_pack import routes

    assert routes.thumbnail("chrome-mercury/00_orb.jpg", 120)[:2] == b"\xff\xd8"
    assert routes.thumbnail("../../configs/vibes.json") is None
    assert routes.allowed_song(str(DEMO)) == DEMO.resolve()
    assert routes.allowed_song(str(ROOT / "pyproject.toml")) is None
    assert routes.allowed_song(str(ROOT / "src" / "xenoform" / "ui_static" / "nope.wav")) is None
    assert routes.info()["library"] == "repository"


def test_the_pack_imports_with_no_desk_on_the_path(tmp_path):
    """The pack folder alone, under another name, with only the standard library and site-packages on the path (no
    src/, no repository root), loaded the way ComfyUI 0.33 loads a custom node folder."""
    import shutil

    pack = tmp_path / "custom_nodes" / "xenoform-nodes"
    shutil.copytree(ROOT / "comfy_pack", pack, ignore=shutil.ignore_patterns("__pycache__"))
    script = tmp_path / "load.py"
    script.write_text(
        "import importlib.util, json, sys\n"
        "from pathlib import Path\n"
        "sys.path = [p for p in sys.path if Path(p).name != 'src' and p not in ('', '.')]\n"
        "class NoDesk:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'xenoform' or name.startswith('xenoform.'):\n"
        "            raise ImportError('no desk here')\n"
        "sys.meta_path.insert(0, NoDesk())\n"
        f"path = {str(pack)!r}\n"
        "name = path.replace('.', '_x_')\n"
        "spec = importlib.util.spec_from_file_location(name, path + '/__init__.py')\n"
        "mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)\n"
        "nodes = mod.NODE_CLASS_MAPPINGS\n"
        "song = nodes['XenoformSongAnalysis']().analyse('demo.wav', 12, 'numpy')['result'][0]\n"
        "board = nodes['XenoformStoryboard']().plan(song, 'neon-noir', '', 'dense', 2, 0.5, 0.3, 0.5, 'auto', 'smooth', 'viscous', '16:9', 2727)['result'][0]\n"
        "print(json.dumps({'nodes': sorted(nodes), 'web': mod.WEB_DIRECTORY, 'desk': 'xenoform' in sys.modules,\n"
        "  'stills': [s['file'] for s in board['stills']], 'pool': board['pool_vibe'], 'song': song['path'], 'drop': song['drop']}))\n",
        encoding="utf-8")
    got = subprocess.run([sys.executable, "-I", str(script)], capture_output=True, text=True, cwd=str(tmp_path))
    assert got.returncode == 0, got.stderr[-2000:]
    report = json.loads(got.stdout.strip().splitlines()[-1])
    assert report["nodes"] == sorted(NODES) and report["web"] == "./web" and report["desk"] is False
    assert report["pool"] == "chrome-mercury" and report["stills"][0] == "chrome-mercury/00_orb.jpg"  # neon noir borrows the bundled stills
    assert report["song"].startswith(str(pack)) and abs(report["drop"] - 5.5015) < 1e-3


COMFY_CANDIDATES = [Path.home() / "AI" / "ComfyUI", Path.home() / "ComfyUI", Path.home() / "ComfyUI_windows_portable" / "ComfyUI"]


def _comfy_python() -> Path | None:
    import os

    roots = [Path(os.environ["XENO_COMFYUI_DIR"])] if os.environ.get("XENO_COMFYUI_DIR") else COMFY_CANDIDATES
    for root in roots:
        for py in (root / ".venv" / "Scripts" / "python.exe", root / "venv" / "Scripts" / "python.exe", root.parent / "python_embeded" / "python.exe",
                   root / ".venv" / "bin" / "python", root / "venv" / "bin" / "python"):
            if py.is_file() and (root / "folder_paths.py").is_file():
                return py
    return None


@pytest.mark.skipif(_comfy_python() is None, reason="no ComfyUI folder with its own Python on this machine")
def test_a_dry_run_with_comfyuis_own_python(tmp_path):
    """ComfyUI's own Python (no librosa, its own numpy, torch and PyAV) imports the pack with folder_paths and the
    server stubbed and runs every node on the demo song. ComfyUI itself is not started."""
    got = subprocess.run([str(_comfy_python()), "-I", str(ROOT / "comfy_pack" / "tools" / "dry_import.py"), str(ROOT / "comfy_pack"),
                          str(tmp_path)], capture_output=True, text=True, timeout=600)
    assert got.returncode == 0, (got.stdout[-1500:], got.stderr[-1500:])
    report = json.loads((tmp_path / "dry_import.json").read_text(encoding="utf-8"))
    assert report["ok"], report
    assert report["python"].startswith("3.") and report["librosa"] is False and report["engine"] == "numpy"
    assert report["nodes"] == sorted(NODES) and report["beats"] == 18 and abs(report["drop"] - 5.5015) < 1e-3
    assert report["image_a"] == [1, 576, 1024, 3] and report["frames"] == 288 and report["routes"] is True
