import json
from pathlib import Path

from xenoform.config import load_config
from xenoform.restyle import _validate_workflow

ROOT = Path(__file__).resolve().parents[1]


def test_default_workflow_is_linked_and_matches_config():
    cfg = load_config(ROOT / "configs" / "example.json")
    path = ROOT / cfg["comfy"]["workflow"]
    _validate_workflow(path, cfg["comfy"])
    graph = json.loads(path.read_text(encoding="utf-8"))
    types = {node["class_type"] for node in graph.values()}
    for required in (
        "CheckpointLoaderSimple",
        "CLIPLoader",
        "LTXVConditioning",
        "LoadVideo",
        "GetVideoComponents",
        "LTXVPreprocess",
        "EmptyLTXVLatentVideo",
        "LTXVImgToVideoInplace",
        "LTXVScheduler",
        "KSamplerSelect",
        "RandomNoise",
        "CFGGuider",
        "ModelSamplingLTXV",
        "SamplerCustomAdvanced",
        "VAEDecode",
        "CreateVideo",
        "SaveVideo",
    ):
        assert required in types
    assert graph["2"]["inputs"]["type"] == "ltxv"
    assert graph["10"]["inputs"]["strength"] == 0.75


def test_guide_workflow_uses_the_same_node_ids():
    cfg = load_config(ROOT / "configs" / "example.json")
    cfg["comfy"]["workflow"] = "workflows/ltx_v2v_guide_api.json"
    path = ROOT / "workflows" / "ltx_v2v_guide_api.json"
    _validate_workflow(path, cfg["comfy"])
    graph = json.loads(path.read_text(encoding="utf-8"))
    assert graph["10"]["class_type"] == "LTXVAddGuide"
    assert graph["16"]["class_type"] == "LTXVCropGuides"
