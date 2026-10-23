"""Simple mode v7.1: the knobs and the Look on the first screen, Chaos shapes the cut, the auto look rides the
vibe's palette, Draft 9:16 renders portrait, and the Machine rows (model, GPU, where it renders) in Fine-tune."""
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from xenoform import beatfx, dense
from xenoform import dance_fx as D

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
V6 = (STATIC / "ui_v6.js").read_text(encoding="utf-8")
DEMO = ROOT / "examples" / "demo.wav"


def test_knobs_and_look_sit_on_the_first_screen():
    assert 'class="panel span simple-knobs-panel"' in APP and '<div class="simple-knobs"></div>' in APP
    assert APP.count('lookRow(easy.danceFx || "auto", "easy-look")') == 1  # once, on the front, not in the drawer
    assert 'document.querySelector(".simple-knobs")' in V6 and "<span>Knobs</span>" in V6
    assert 'title="${hint||l}"' in V6 and "punches, stutters and orbit swing" in V6


def test_machine_rows_in_fine_tune_and_the_payload():
    assert "function machineRows" in APP and 'simpleSeg("easy-gpu"' in APP and 'id="easy-endpoint"' in APP
    assert 'data-act="easy-paid-cloud"' in APP and "Draft · LTX-Video 0.9.5" in APP and "Final · LTX-2.3 22B" in APP
    assert 'hardware_tier: (state.easy && state.easy.gpuTier) || "auto"' in APP
    assert 'act === "easy-gpu"' in APP and 'act === "easy-paid-cloud"' in APP


@pytest.fixture(scope="module")
def client():
    from xenoform.ui import create_app

    return TestClient(create_app())


def test_simple_options_report_the_detected_gpu_and_the_tiers(client):
    r = client.get("/api/simple/options?duration=20&energy=dense&tier=draft&bpm=120&aspect=9:16")
    hw = r.json()["hardware"]
    assert hw["detected"]["id"] in {"cpu", "8gb", "12gb", "24gb"} and hw["detected"]["label"]
    assert [t["id"] for t in hw["tiers"]] == ["cpu", "8gb", "12gb", "24gb"]


def test_generate_honours_the_chosen_gpu_tier(client, monkeypatch):
    from xenoform import hardware, ui as ui_mod

    seen = {}
    done = threading.Event()

    def fake_run_resilient(fn, tier=None):
        seen["tier"] = dict(tier or {})
        done.set()
        raise RuntimeError("stop here")

    monkeypatch.setattr(hardware, "run_resilient", fake_run_resilient)
    r = client.post("/api/generate", json={"audio_id": "demo", "quality": "turbo", "mode": "simple", "vibe": "ocean",
                                           "hardware_tier": "8gb", "tiny": True})
    assert r.status_code == 200, r.text
    assert done.wait(20)
    assert seen["tier"]["id"] == "8gb"
    done.clear()
    client.post("/api/generate", json={"audio_id": "demo", "quality": "turbo", "mode": "simple", "vibe": "ocean",
                                       "hardware_tier": "auto", "tiny": True})
    assert done.wait(20) and seen["tier"]["id"] in {"cpu", "8gb", "12gb", "24gb"}


def test_chaos_shapes_the_cut():
    shots = [{"start": 0.0, "end": 1.0, "seconds": 1.0, "frames": 24, "effects": [
        {"type": "punch", "t": 0.0, "strength": 0.5}, {"type": "stutter", "t": 0.2, "frames": 2, "repeat": 3},
        {"type": "hold", "t": 0.5, "len": 0.12}]}]
    calm = dense.apply_macros(json.loads(json.dumps(shots)), {"chaos": 0.1})
    assert [e["type"] for e in calm[0]["effects"]] == ["punch"] and calm[0]["effects"][0]["strength"] < 0.3
    wild = dense.apply_macros(json.loads(json.dumps(shots)), {"chaos": 0.95})
    assert {e["type"] for e in wild[0]["effects"]} == {"punch", "stutter", "hold"}
    assert wild[0]["effects"][0]["strength"] == 0.5 * min(2.0, 0.4 + 1.2 * 0.95) or wild[0]["effects"][0]["strength"] <= 1.0
    assert next(e for e in wild[0]["effects"] if e["type"] == "stutter")["repeat"] == 5
    assert wild[0]["chaos"] == 0.95 and calm[0]["chaos"] == 0.1


def test_orbit_swing_follows_chaos():
    pytest.importorskip("cv2")
    fps, n = 24, 48
    beats = [i * 0.5 for i in range(8)]
    env = {"fps": fps, "frames": n, "engine": "mix", "stems": [], "roles": {}, "bass": [0.9] * n, "drums": [0.8] * n,
           "other": [0.3] * n, "vocals": [0.0] * n, "drum_strong": beats}
    yaw = {}
    for chaos in (0.0, 1.0):
        look = beatfx.LookPass(dance_fx="off", stem_orbit=True, stem_env=env, macros={"chaos": chaos}, beats=beats, fps=fps, shots=1)
        look.start_shot(0, n, 0.0)
        yaw[chaos] = float(np.abs(look.plan["yaw"]).max())
    assert yaw[1.0] > yaw[0.0] * 1.5


def test_palette_tints_follow_the_still(tmp_path):
    from xenoform.portrait import save_png

    h, w = 64, 96
    blue = np.zeros((h, w, 3), np.uint8)
    blue[..., 2] = np.linspace(40, 255, w).astype(np.uint8)[None, :]
    blue[..., 1] = (blue[..., 2] * 0.5).astype(np.uint8)
    save_png(blue, tmp_path / "blue.png")
    tints = D.palette_tints(tmp_path / "blue.png")
    assert tints and tints["shadow"][2] > tints["shadow"][0] and tints["edge"][2] == 255
    grey = np.full((h, w, 3), 120, np.uint8)
    grey[:, : w // 2] = 40
    save_png(grey, tmp_path / "grey.png")
    assert D.palette_tints(tmp_path / "grey.png") == {}  # a grey still leaves the preset's colours alone
    assert D.palette_tints(tmp_path / "missing.png") == {}


def test_adaptive_look_overrides_the_preset_colours(tmp_path):
    from xenoform.portrait import save_png

    gold = np.zeros((64, 96, 3), np.uint8)
    gold[..., 0] = 230
    gold[..., 1] = 170
    gold[..., 2] = 60
    gold[:32] //= 3
    save_png(gold, tmp_path / "gold.png")
    beats = [0.0, 0.5]
    env = beatfx.mix_stem_env({"kick": [0.5] * 12, "trans": [0.5] * 12, "loud": [0.5] * 12}, beats, 24)
    fixed = beatfx.LookPass(dance_fx="cool-echo", stem_env=env, beats=beats, fps=24, shots=1, palette_image=str(tmp_path / "gold.png"))
    fixed.start_shot(0, 12, 0.0)
    assert tuple(fixed.fx.p["edge"]) == D.PRESETS["cool-echo"]["edge"]  # a named preset keeps its cast
    auto = beatfx.LookPass(dance_fx="cool-echo", stem_env=env, beats=beats, fps=24, shots=1, palette_image=str(tmp_path / "gold.png"),
                           adaptive=True)
    auto.start_shot(0, 12, 0.0)
    assert auto.fx.p["edge"][0] > auto.fx.p["edge"][2] and auto.fx.p["shadow"][0] > auto.fx.p["shadow"][2]
    assert auto.info()["adaptive"] and "edge" in auto.info()["tints"]


def test_draft_916_renders_portrait_from_relaid_stills(tmp_path, monkeypatch):
    seen = {}
    rendered = {}
    monkeypatch.setattr(dense, "stills_for", lambda state, n: ("ocean", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(n)]))
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: [{**s, "black_ground": True} for s in stills])
    monkeypatch.setattr("xenoform.portrait.portrait_stills",
                        lambda stills, work, w=720, h=1280, background=None: [{**s, "portrait": (w, h)} for s in stills])

    def fake_mock(shots, stills, work, w, h):
        rendered["size"] = (w, h)
        rendered["stills"] = stills
        return [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))]

    import xenoform.cloud_morph as cm
    monkeypatch.setattr(cm, "_mock_clips", fake_mock)

    def fake_compose(clips, shots, audio, out, **kw):
        seen.update(kw)
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, DEMO, tmp_path / "x.mp4", tmp_path, {},
                     {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "dance_fx": "auto"},
                     lambda *a: None, engine="mock")
    assert rendered["size"] == dense.DRAFT_916 and all(s.get("portrait") == dense.DRAFT_916 for s in rendered["stills"])
    assert seen["adaptive"] is True and seen["palette_image"]
    seen.clear()
    dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, DEMO, tmp_path / "y.mp4", tmp_path / "y", {},
                     {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "dance_fx": "noir-glow"},
                     lambda *a: None, engine="mock")
    assert seen["adaptive"] is False  # a named look is fixed
