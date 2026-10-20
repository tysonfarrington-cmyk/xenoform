"""Model and text encoder must match for every tier (regression: LTX-2.3 + T5 failed 4096 vs 2048 in ComfyUI)."""

import json
from pathlib import Path

import pytest

from xenoform.config import load_config, resolve_path
from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT
from xenoform.restyle import _nodes_for, _stamp_graph, build_jobs, encoder_compatible

ROOT = Path(__file__).resolve().parents[1]


def _features(n=36, fps=12, conditioning=""):
    import importlib.util

    spec = importlib.util.spec_from_file_location("_rd", Path(__file__).with_name("test_restyle_dry.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    feats = mod._features(n, fps)
    for frame in feats["frames"]:
        frame["conditioning"] = conditioning
    return feats


def _pairs(graph: dict) -> tuple[str, str, str]:
    ckpt = clip = loader = ""
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if "ckpt_name" in inputs and node.get("class_type") in {"CheckpointLoaderSimple", "LTXAVTextEncoderLoader"}:
            ckpt = ckpt or str(inputs["ckpt_name"])
        if node.get("class_type") in {"CLIPLoader", "LTXAVTextEncoderLoader"}:
            loader = node["class_type"]
            clip = str(inputs.get("clip_name") or inputs.get("text_encoder") or "")
    return ckpt, clip, loader


def test_encoder_rules():
    assert encoder_compatible(FAST_CHECKPOINT, "t5xxl_fp8_e4m3fn_scaled.safetensors", "ltx-095")
    assert not encoder_compatible(LARGE_CHECKPOINT, "t5xxl_fp8_e4m3fn_scaled.safetensors", "ltx-23")
    assert encoder_compatible("ltx-2.3-22b-distilled-fp8.safetensors", "gemma_3_12B_it_fp4_mixed.safetensors", "ltx-23")
    assert not encoder_compatible(FAST_CHECKPOINT, "gemma_3_12B_it_fp4_mixed.safetensors", "ltx-095")


@pytest.mark.parametrize("quality", ["turbo", "draft", "final"])
@pytest.mark.parametrize("conditioning", ["", "first-frame", "signature"])
@pytest.mark.parametrize("asked", ["", "ltx-23"])
@pytest.mark.parametrize("ckpt", [FAST_CHECKPOINT, LARGE_CHECKPOINT, "ltx-2.3-22b-distilled-fp8.safetensors"])
def test_every_restyle_job_and_stamped_graph_is_compatible(quality, conditioning, asked, ckpt, tmp_path, monkeypatch):
    monkeypatch.setattr("xenoform.ltx25.wants_ltx25", lambda cfg: False)
    cfg = load_config()
    cfg["quality"] = quality
    cfg["segment"] = {"target_seconds": 1.0, "min_seconds": 0.7, "max_seconds": 1.6}
    cfg["comfy"]["checkpoint_name"] = ckpt
    cfg["comfy"]["video_model"] = asked
    jobs = build_jobs(_features(conditioning=conditioning), cfg)
    assert jobs
    workflow = resolve_path(cfg["comfy"]["workflow"], cfg)
    for job in jobs:
        assert encoder_compatible(job["checkpoint_name"], job["clip_name"], job["engine"]), job
        job.setdefault("img_compression", 18)
        graph = _stamp_graph(workflow, job, _nodes_for(cfg, job), "chunk.mp4")
        g_ckpt, g_clip, _loader = _pairs(graph)
        assert encoder_compatible(g_ckpt, g_clip, job["engine"]), (g_ckpt, g_clip)


def test_final_tier_graph_pairs_ltx23_with_its_encoder():
    from xenoform import final_tier

    assert encoder_compatible(final_tier.CKPT, final_tier.TEXT_ENCODER, "ltx-23")


def test_shipped_graphs_pair_model_and_encoder():
    for path in sorted((ROOT / "workflows").glob("*.json")):
        try:
            graph = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(graph, dict) or not all(isinstance(v, dict) for v in graph.values()):
            continue
        ckpt, clip, loader = _pairs(graph)
        if ckpt and clip and "ltx" in ckpt.lower():
            assert encoder_compatible(ckpt, clip), (path.name, ckpt, clip)
