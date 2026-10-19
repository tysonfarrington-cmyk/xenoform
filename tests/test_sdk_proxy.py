"""Live renders go through comfy-sdk and the local proxy. LTX-2.5 falls back to 2.3."""

import json
import os
from pathlib import Path

import numpy as np

from xenoform.config import load_config
from xenoform.eligibility import VIDEO_CORE, VIDEO_MORPH, audit_default_workflows, ltx25_allowed, repo_root
from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT
from xenoform.ltx25 import (
    LTX25_CHECKPOINT,
    LTX25_CLIP,
    core_choice,
    graph_kind,
    graph_path,
    licence_summary,
)
from xenoform.restyle import _make_client, build_jobs, restyle, sdk_base_url
from xenoform.video import write_mp4


def test_requirements_pin_sdk_and_proxy():
    text = (repo_root() / "requirements.txt").read_text(encoding="utf-8")
    assert "comfy-sdk==0.5.0" in text
    assert "comfy-api-proxy==0.1.6" in text


def test_default_graphs_stay_open_weights():
    assert VIDEO_CORE == "LTX-2.3"
    assert VIDEO_MORPH == "LTX 0.9.5"
    assert audit_default_workflows() == []
    assert ltx25_allowed() is True
    summary = licence_summary()
    assert "LTX-2.x Community License Agreement" in summary
    assert "partner" in summary
    for name in ("ltx25_a2v_api.json", "ltx25_multishot_api.json", "ltx25_layout_api.json"):
        graph = json.loads((repo_root() / "workflows" / name).read_text(encoding="utf-8"))
        kinds = [node["class_type"] for node in graph.values()]
        assert "CLIPLoader" in kinds
        assert not any("LtxApi" in kind or "GemmaAPI" in kind for kind in kinds)


def test_sdk_url_is_the_proxy_and_drops_the_cloud_key(monkeypatch):
    captured = {}

    class FakeComfy:
        def __init__(self, client_info="", timeout=None):
            captured["base"] = os.environ.get("COMFY_BASE_URL")
            captured["key"] = os.environ.get("COMFY_API_KEY")
            captured["info"] = client_info
            captured["timeout"] = timeout

    monkeypatch.setattr("comfy_sdk.Comfy", FakeComfy)
    monkeypatch.setenv("COMFY_API_KEY", "secret-cloud")
    cfg = load_config()
    cfg["comfy"]["base_url"] = "http://127.0.0.1:8188"
    cfg["comfy"]["proxy_url"] = "http://127.0.0.1:8189"
    cfg["comfy"]["send_api_key"] = False
    _make_client(cfg)
    assert captured["base"] == "http://127.0.0.1:8189"
    assert captured["key"] is None
    assert captured["info"] == "xenoform"
    assert os.environ.get("COMFY_API_KEY") == "secret-cloud"
    assert sdk_base_url(cfg) == "http://127.0.0.1:8189"


def test_cloud_is_empty_proxy_and_sends_the_key(monkeypatch):
    captured = {}

    class FakeComfy:
        def __init__(self, client_info="", timeout=None):
            captured["base"] = os.environ.get("COMFY_BASE_URL")
            captured["key"] = os.environ.get("COMFY_API_KEY")

    monkeypatch.setattr("comfy_sdk.Comfy", FakeComfy)
    monkeypatch.setenv("COMFY_API_KEY", "secret-cloud")
    cfg = load_config()
    cfg["comfy"]["base_url"] = ""
    cfg["comfy"]["proxy_url"] = ""
    cfg["comfy"]["send_api_key"] = True
    _make_client(cfg)
    assert captured["base"] is None
    assert captured["key"] == "secret-cloud"


def test_endpoint_does_not_replace_the_proxy():
    from xenoform.director import apply_endpoint

    cfg = load_config()
    out = apply_endpoint(
        cfg,
        {"endpoint": "http://10.0.0.8:8188", "live": False, "video_model": "ltx-25"},
    )
    assert out["comfy"]["base_url"] == "http://10.0.0.8:8188"
    assert out["comfy"]["proxy_url"] == "http://127.0.0.1:8189"
    assert out["comfy"]["video_model"] == "ltx-25"


def test_core_choice_turbo_and_fallback():
    turbo = {"comfy": {"video_model": "ltx-25", "ltx25_present": True, "checkpoint_name": LARGE_CHECKPOINT}}
    engine, name, _note = core_choice(turbo, "turbo", "first-frame", LARGE_CHECKPOINT)
    assert engine == "ltx-095"
    assert name == FAST_CHECKPOINT
    assert "2.3" not in name and "2.5" not in name

    missing = {"comfy": {"video_model": "ltx-25", "ltx25_present": False}}
    engine, name, note = core_choice(missing, "draft", "", FAST_CHECKPOINT)
    assert engine == "ltx-23"
    assert name == LARGE_CHECKPOINT
    assert "2.3" in note

    present = {"comfy": {"video_model": "ltx-25", "ltx25_present": True}}
    engine, name, note = core_choice(present, "draft", "", FAST_CHECKPOINT)
    assert engine == "ltx-25"
    assert name == LTX25_CHECKPOINT
    assert note == ""


def test_licence_failure_stays_on_23(monkeypatch):
    monkeypatch.setattr("xenoform.ltx25.ltx25_allowed", lambda: False)
    cfg = {"comfy": {"video_model": "ltx-25", "ltx25_present": True}}
    engine, name, note = core_choice(cfg, "final", "", FAST_CHECKPOINT)
    assert engine == "ltx-23"
    assert name == LARGE_CHECKPOINT
    assert "open-weights" in note


def test_graph_kind_layout_a2v_and_multishot():
    calm = {"start_frame": 0, "source_frames": 4, "section": "calm", "conditioning": ""}
    drop = {"start_frame": 4, "source_frames": 4, "section": "drop", "conditioning": ""}
    frames = [{"section": "calm"}] * 4 + [{"section": "drop"}] * 4
    assert graph_kind(calm, frames) == "a2v"
    assert graph_kind(drop, frames) == "layout"
    crossed = {"start_frame": 2, "source_frames": 4, "section": "calm", "conditioning": ""}
    assert graph_kind(crossed, frames) == "multishot"
    assert graph_path("layout").endswith("ltx25_layout_api.json")


def _features(n_frames, fps):
    frames = []
    for i in range(n_frames):
        section = "drop" if i >= n_frames // 2 else "calm"
        frames.append(
            {
                "i": i,
                "t": i / fps,
                "energy": 0.9 if section == "drop" else 0.2,
                "onset_env": 0.0,
                "section": section,
                "is_drop": section == "drop",
                "is_beat": False,
                "beat_env": 0.0,
            }
        )
    return {
        "fps": fps,
        "n_frames": n_frames,
        "duration": n_frames / fps,
        "beats": [],
        "sections": [
            {"start_frame": 0, "end_frame": n_frames // 2, "label": "calm"},
            {"start_frame": n_frames // 2, "end_frame": n_frames, "label": "drop"},
        ],
        "frames": frames,
    }


def test_dry_run_records_ltx25_graphs_without_a_client(tmp_path: Path, monkeypatch):
    constructed = {"n": 0}

    class FakeComfy:
        def __init__(self, *args, **kwargs):
            constructed["n"] += 1

    monkeypatch.setattr("comfy_sdk.Comfy", FakeComfy)
    fps = 12
    n = 36
    frames = [np.zeros((32, 32, 3), dtype=np.uint8) for _ in range(n)]
    video = tmp_path / "base.mp4"
    write_mp4(video, frames, fps, crf=23)
    cfg = load_config()
    cfg["quality"] = "draft"
    cfg["segment"] = {"target_seconds": 1.0, "min_seconds": 0.7, "max_seconds": 1.6}
    cfg["comfy"]["mode"] = "dry-run"
    cfg["comfy"]["width"] = 512
    cfg["comfy"]["height"] = 320
    cfg["comfy"]["video_model"] = "ltx-25"
    cfg["comfy"]["ltx25_present"] = True
    manifest = restyle(_features(n, fps), video, tmp_path / "chunks", cfg, mode="dry-run")
    assert constructed["n"] == 0
    assert manifest["note"].startswith("dry-run")
    kinds = {chunk["graph"] for chunk in manifest["chunks"]}
    assert "a2v" in kinds
    assert "layout" in kinds
    for chunk in manifest["chunks"]:
        assert chunk["engine"] == "ltx-25"
        assert chunk["width"] % 64 == 0 and chunk["height"] % 64 == 0
        assert LTX25_CLIP in chunk["inputs"]["2.clip_name"]
        assert "LtxApi" not in chunk["workflow"]
        if chunk["graph"] == "layout":
            assert chunk["workflow"].endswith("ltx25_layout_api.json")
        if chunk["graph"] == "a2v":
            assert chunk["workflow"].endswith("ltx25_a2v_api.json")
        if chunk["graph"] == "multishot":
            assert "36.text" in chunk["inputs"]


def test_build_jobs_snaps_25_and_leaves_turbo_on_095():
    features = _features(36, 12)
    cfg = load_config()
    cfg["quality"] = "draft"
    cfg["segment"] = {"target_seconds": 1.0, "min_seconds": 0.7, "max_seconds": 1.6}
    cfg["comfy"]["width"] = 512
    cfg["comfy"]["height"] = 288
    cfg["comfy"]["video_model"] = "ltx-25"
    cfg["comfy"]["ltx25_present"] = True
    jobs = build_jobs(features, cfg)
    assert jobs
    assert {job["engine"] for job in jobs} == {"ltx-25"}
    assert all(job["height"] == 256 for job in jobs)
    assert all(job["clip_name"] == LTX25_CLIP for job in jobs)

    cfg["quality"] = "turbo"
    turbo = build_jobs(features, cfg)
    assert {job["engine"] for job in turbo} == {"ltx-095"}
    assert all(job["checkpoint_name"] == FAST_CHECKPOINT for job in turbo)
    assert all(job["height"] == 288 for job in turbo)
