"""rc2 Simple mode: recipe codes, finishing options routing, hook, My videos. CPU only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import simple_recipe as sr
from xenoform import ui
from xenoform.config import load_config

ROOT = Path(__file__).resolve().parents[1]
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def test_recipe_roundtrip_is_short_and_keeps_every_choice():
    state = {"vibe": "black", "idea": "glass bloom", "seed": 99, "energy_preset": "dense", "aspect": "9:16",
             "quality_tier": "final", "beat_fx": False, "beat_overlay": True, "end_card": True}
    code = sr.encode(state)
    assert code.startswith("xf1.") and len(code) < 160
    back = sr.decode(code)
    for key, value in state.items():
        assert back[key] == value
    assert len(sr.encode({"vibe": "black"})) < 40


def test_recipe_clamps_unknown_values_and_rejects_junk():
    back = sr.decode(sr.encode({"vibe": "ocean", "aspect": "4:3", "energy_preset": "turbo", "quality_tier": "ultra"}))
    assert (back["aspect"], back["energy_preset"], back["quality_tier"]) == ("16:9", "flow", "draft")
    for bad in ("", "hello", "xf1.!!!", "xf1." + "A" * 10):
        with pytest.raises(sr.RecipeError):
            sr.decode(bad)


def test_recipe_carries_a_cut_plan_and_validates_it():
    from xenoform.dense import demo1_plan

    plan = demo1_plan()
    back = sr.decode(sr.encode({"vibe": "black", "cut_plan": plan}))
    assert len(back["cut_plan"]["shots"]) == 15 and back["cut_plan"]["stills"][0] == "rose"
    broken = {"shots": [{"start": 0, "end": 0.1}]}
    with pytest.raises(sr.RecipeError):
        sr.decode(sr.encode({"cut_plan": broken}))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path)
    return TestClient(ui.create_app(load_config(None)))


def test_recipe_routes(client):
    code = client.post("/api/simple/recipe/encode", json={"vibe": "black", "aspect": "1:1"}).json()["recipe"]
    back = client.post("/api/simple/recipe/decode", json={"recipe": code})
    assert back.status_code == 200 and back.json()["aspect"] == "1:1" and back.json()["recipe"] == code
    assert client.post("/api/simple/recipe/decode", json={"recipe": "nope"}).status_code == 400


def test_options_route_reports_final_files_and_an_honest_eta(client):
    body = client.get("/api/simple/options?duration=20&energy=dense").json()
    assert body["aspects"] == ["16:9", "9:16", "1:1"] and body["tiers"] == ["draft", "final"]
    assert 8 <= body["shots"] <= 15
    assert body["final"]["eta_measured"] is False and body["final"]["eta_s"] > 600
    assert body["final"]["output"] == "1280x720"
    flow = client.get("/api/simple/options?duration=20&energy=flow").json()
    assert flow["shots"] < body["shots"]


def _fake_job(root: Path, job_id: str, meta: dict) -> Path:
    folder = root / "jobs" / job_id
    folder.mkdir(parents=True)
    shutil.copyfile(ROOT / "examples" / "demo_base.mp4", folder / "xenoform.mp4")
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return folder


def test_my_videos_lists_simple_cuts_with_recipes(client, tmp_path):
    code = sr.encode({"vibe": "black", "energy_preset": "dense", "aspect": "9:16"})
    _fake_job(tmp_path, "aaaa1111", {"simple": True, "vibe": "black", "energy_preset": "dense", "aspect": "9:16",
                                     "quality_tier": "draft", "recipe": code, "created": "2026-10-19T22:00:00+11:00"})
    _fake_job(tmp_path, "bbbb2222", {"simple": False})
    rows = client.get("/api/videos").json()["videos"]
    assert [r["id"] for r in rows] == ["aaaa1111"]
    assert rows[0]["recipe"] == code and rows[0]["aspect"] == "9:16" and rows[0]["energy"] == "dense"
    assert client.get(rows[0]["url"]).status_code == 200
    assert client.get("/api/videos/nothere1/video").status_code == 404
    assert client.get("/api/videos/..%2Fetc/video").status_code in (400, 404)


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_hook_route_cuts_around_the_drop(client, tmp_path):
    _fake_job(tmp_path, "cccc3333", {"simple": True, "audio_id": "demo", "recipe": "xf1.x"})
    res = client.post("/api/videos/cccc3333/hook", json={"length": 6})
    assert res.status_code == 200
    body = res.json()
    assert body["seconds"] == pytest.approx(6.0, abs=0.15) and body["start"] <= body["drop"] <= body["end"]
    got = client.get(body["url"])
    assert got.status_code == 200 and len(got.content) > 1000


def test_job_meta_writes_a_recipe_for_simple_mode(tmp_path):
    recipe = ui._write_meta(tmp_path, {"mode": "simple", "vibe": "black", "energy_preset": "dense", "aspect": "9:16",
                                       "song": "Morphing Wobble"}, "demo")
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["simple"] and meta["recipe"] == recipe and sr.decode(recipe)["energy_preset"] == "dense"
    assert meta["song"] == "Morphing Wobble"
    assert ui._write_meta(tmp_path, {"mode": "director"}, "demo") == ""


def test_turbo_routes_finishing_requests_to_the_open_weights_pass():
    """Dense / 9:16 / Final go through dense.run_simple; the plain Simple make keeps the old morph pass."""
    from xenoform import dense

    src = (ROOT / "src" / "xenoform" / "turbo.py").read_text(encoding="utf-8")
    assert "if wants_finishing(state):" in src and "run_simple(directed" in src
    assert "run_morph_pass(directed, scenes, Path(audio_path), out_path, work, tuned, state, report, cancel=cancel)" in src
    assert dense.wants_finishing({"energy_preset": "dense"}) and not dense.wants_finishing({"vibe": "black"})


def test_paid_cloud_still_off_by_default():
    from xenoform.cloud_morph import paid_cloud_enabled

    assert paid_cloud_enabled({}, False) is False
