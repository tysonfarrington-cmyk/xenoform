"""The node pack's demo workflow (comfy_pack/workflows/xenoform_demo.json and _api.json) against the node definitions.

The stock nodes' definitions are ComfyUI 0.33's own (tests/fixtures/comfy_object_info_ltx095.json, read from the
machine's ComfyUI), the pack's come from its classes. The UI file is checked as the frontend loads it (types, slots,
widget values, every required input linked), the API file as ComfyUI validates a prompt, and the API graph is run with
the pack's nodes for real and the LTX nodes as stand-ins that check what they are given, so every value a Morph Pair
hands on lands on a stock input of its type and the Assemble writes the cut. Nothing is queued on a ComfyUI.
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "comfy_pack" / "tools"))
import build_demo_workflow as W  # noqa: E402

from comfy_pack.nodes import NODE_CLASS_MAPPINGS as PACK  # noqa: E402

UI = json.loads((ROOT / "comfy_pack" / "workflows" / "xenoform_demo.json").read_text(encoding="utf-8"))
API = json.loads((ROOT / "comfy_pack" / "workflows" / "xenoform_demo_api.json").read_text(encoding="utf-8"))
DEFS = W.all_defs()
DESK_GRAPH = json.loads((ROOT / "workflows" / "xenoform_morph.json").read_text(encoding="utf-8"))


def _widget_specs(kind: str) -> list[tuple[str, object]]:
    return [(name, spec) for name, spec, _req in W.inputs_of(DEFS[kind]) if W.is_widget(spec)]


def _options(spec) -> list | None:
    if isinstance(spec[0], list):
        return spec[0]
    if len(spec) > 1 and isinstance(spec[1], dict) and isinstance(spec[1].get("options"), list):
        return spec[1]["options"]
    return None


def test_the_files_are_what_the_builder_writes():
    got = subprocess.run([sys.executable, str(ROOT / "comfy_pack" / "tools" / "build_demo_workflow.py"), "--check"],
                         capture_output=True, text=True)
    assert got.returncode == 0, got.stdout + got.stderr


def test_every_node_is_one_comfyui_or_the_pack_defines():
    kinds = {n["type"] for n in UI["nodes"]}
    assert kinds <= set(DEFS) | set(W.FRONTEND_ONLY)
    assert {k for k in kinds if k.startswith("Xenoform")} == set(PACK)
    assert UI["version"] == 0.4 and UI["last_node_id"] == max(n["id"] for n in UI["nodes"])
    assert UI["last_link_id"] == max(link[0] for link in UI["links"])


def test_the_widget_values_fit_the_definitions():
    for node in UI["nodes"]:
        if node["type"] in W.FRONTEND_ONLY:
            continue
        specs = _widget_specs(node["type"])
        values = list(node["widgets_values"])
        k = 0
        for name, spec in specs:
            value = values[k]
            k += 1
            opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
            choices = _options(spec)
            if choices is not None and choices:
                assert value in choices, (node["type"], name, value)
            kind = W.spec_type(spec)
            if kind in ("INT", "FLOAT"):
                assert isinstance(value, (int, float)) and not isinstance(value, bool), (node["type"], name)
                assert opts.get("min", -1e18) <= value <= opts.get("max", 1e18), (node["type"], name, value)
            if kind == "BOOLEAN":
                assert isinstance(value, bool)
            if W.has_control(name, spec):
                assert values[k] in ("fixed", "increment", "decrement", "randomize")
                k += 1
        assert k == len(values), (node["type"], len(values), k)


def test_every_link_joins_matching_types_and_every_required_input_is_linked():
    by_id = {n["id"]: n for n in UI["nodes"]}
    for lid, src, out, dst, slot, typ in UI["links"]:
        a, b = by_id[src], by_id[dst]
        assert DEFS[a["type"]]["output"][out] == typ == a["outputs"][out]["type"]
        assert lid in (a["outputs"][out]["links"] or [])
        inp = b["inputs"][slot]
        assert inp["link"] == lid and inp["type"] == typ, (b["type"], inp["name"], typ)
    for node in UI["nodes"]:
        if node["type"] in W.FRONTEND_ONLY:
            continue
        linked = {i["name"] for i in node["inputs"] if i.get("link") is not None}
        for name, spec, req in W.inputs_of(DEFS[node["type"]]):
            if req and not W.is_widget(spec):
                assert name in linked, (node["type"], name)


def test_the_api_copy_is_a_prompt_comfyui_accepts():
    """ComfyUI's validate_inputs, in short: every node a known class, every required input given, every link to an
    output that exists and has the input's type, every combo value one it lists."""
    for nid, node in API.items():
        d = DEFS[node["class_type"]]
        for name, spec, req in W.inputs_of(d):
            if name not in node["inputs"]:
                assert not req, (node["class_type"], name)
                continue
            value = node["inputs"][name]
            if isinstance(value, list):
                src = API[value[0]]
                out_type = DEFS[src["class_type"]]["output"][value[1]]
                assert out_type == W.spec_type(spec) or W.spec_type(spec) == "*", (node["class_type"], name, out_type)
            elif _options(spec):
                assert value in _options(spec), (node["class_type"], name, value)
    assert {n["class_type"] for n in API.values()} == {n["type"] for n in UI["nodes"]} - set(W.FRONTEND_ONLY)


def test_each_morph_is_the_desks_ltx_graph_with_the_pairs_values():
    """Each Morph Pair feeds a copy of workflows/xenoform_morph.json: the same nodes (its LoadImage pair, CreateVideo and
    SaveVideo replaced by the pair's images and the Assemble; the loaders shared), the same fixed values, and the pair's
    outputs exactly where the desk calls set_input."""
    pairs = {nid: n for nid, n in API.items() if n["class_type"] == "XenoformMorphPair"}
    assert sorted(n["inputs"]["index"] for n in pairs.values()) == [0, 1]
    desk_kinds = sorted(n["class_type"] for n in DESK_GRAPH.values()
                        if n["class_type"] not in ("LoadImage", "CreateVideo", "SaveVideo", "CheckpointLoaderSimple", "CLIPLoader", "KSamplerSelect"))
    fed = {"CLIPTextEncode": {"text"}, "LTXVConditioning": {"frame_rate"}, "LTXVPreprocess": {"img_compression", "image"},
           "EmptyLTXVLatentVideo": {"width", "height", "length"}, "LTXVAddGuide": {"strength"}, "LTXVScheduler": {"steps"},
           "RandomNoise": {"noise_seed"}, "CFGGuider": {"cfg"}}
    for pid in pairs:
        group = {pid}
        changed = True
        while changed:  # everything downstream of this pair up to the Assemble
            changed = False
            for nid, n in API.items():
                if nid not in group and n["class_type"] != "XenoformAssemble" and any(
                        isinstance(v, list) and v[0] in group for v in n["inputs"].values()):
                    group.add(nid)
                    changed = True
        kinds = sorted(API[n]["class_type"] for n in group if n != pid)
        assert kinds == desk_kinds
        for nid in group - {pid}:
            n = API[nid]
            desk = next(d for d in DESK_GRAPH.values() if d["class_type"] == n["class_type"])
            for name, value in n["inputs"].items():
                from_pair = isinstance(value, list) and value[0] == pid
                if from_pair:
                    assert name in fed[n["class_type"]], (n["class_type"], name)
                elif not isinstance(value, list) and name in desk["inputs"] and not isinstance(desk["inputs"][name], list) \
                        and n["class_type"] not in ("CLIPTextEncode", "LTXVAddGuide", "EmptyLTXVLatentVideo", "LTXVPreprocess",
                                                    "RandomNoise", "CFGGuider", "LTXVScheduler", "LTXVConditioning"):
                    assert value == desk["inputs"][name], (n["class_type"], name)
            if n["class_type"] == "LTXVAddGuide":
                assert n["inputs"]["frame_idx"] in (0, -1)
            if n["class_type"] in ("LTXVScheduler", "ModelSamplingLTXV"):
                assert (n["inputs"]["max_shift"], n["inputs"]["base_shift"]) == (2.05, 0.95)
    loaders = {n["class_type"]: n["inputs"] for n in API.values() if n["class_type"] in ("CheckpointLoaderSimple", "CLIPLoader")}
    assert loaders["CheckpointLoaderSimple"]["ckpt_name"] == DESK_GRAPH["1"]["inputs"]["ckpt_name"]
    assert {k: loaders["CLIPLoader"][k] for k in ("clip_name", "type", "device")} == DESK_GRAPH["2"]["inputs"]


# ------------------------------------------------------------------------------------------------ running the API graph


class Stock:
    """Stand-ins for ComfyUI's LTX nodes: each checks the Python value it gets, as the real node would use it."""

    def __init__(self):
        self.seen: dict[str, list] = {}

    def __call__(self, kind: str, inputs: dict):
        import torch

        self.seen.setdefault(kind, []).append(inputs)
        if kind == "CheckpointLoaderSimple":
            return ("MODEL", "CLIP", "VAE")
        if kind == "CLIPLoader":
            return ("CLIP",)
        if kind == "KSamplerSelect":
            return ("SAMPLER",)
        if kind == "CLIPTextEncode":
            assert isinstance(inputs["text"], str) and len(inputs["text"]) > 40 and inputs["clip"] == "CLIP"
            return ({"cond": inputs["text"]},)
        if kind == "LTXVConditioning":
            assert inputs["frame_rate"] == 24.0 and isinstance(inputs["frame_rate"], float)
            return (inputs["positive"], inputs["negative"])
        if kind == "LTXVPreprocess":
            image = inputs["image"]
            assert isinstance(image, torch.Tensor) and image.ndim == 4 and image.shape[0] == 1 and image.shape[-1] == 3
            assert image.dtype == torch.float32 and 0.0 <= float(image.min()) and float(image.max()) <= 1.0
            assert isinstance(inputs["img_compression"], int) and 0 <= inputs["img_compression"] <= 100
            return (image,)
        if kind == "EmptyLTXVLatentVideo":
            n = inputs["length"]
            assert isinstance(n, int) and n % 8 == 1 and 25 <= n <= 121
            assert (inputs["width"], inputs["height"]) == (512, 288) and inputs["batch_size"] == 1
            return ({"length": n, "w": inputs["width"], "h": inputs["height"]},)
        if kind == "LTXVAddGuide":
            assert isinstance(inputs["image"], torch.Tensor) and inputs["frame_idx"] in (0, -1)
            assert isinstance(inputs["strength"], float) and 0.0 <= inputs["strength"] <= 10.0
            return (inputs["positive"], inputs["negative"], inputs["latent"])
        if kind == "LTXVScheduler":
            assert isinstance(inputs["steps"], int) and 1 <= inputs["steps"] <= 100
            return ("SIGMAS",)
        if kind == "RandomNoise":
            assert isinstance(inputs["noise_seed"], int) and inputs["noise_seed"] >= 0
            return ("NOISE",)
        if kind == "ModelSamplingLTXV":
            return ("MODEL",)
        if kind == "CFGGuider":
            assert isinstance(inputs["cfg"], float) and 0.0 <= inputs["cfg"] <= 100.0
            return ("GUIDER",)
        if kind == "SamplerCustomAdvanced":
            return (inputs["latent_image"], inputs["latent_image"])
        if kind == "LTXVCropGuides":
            return (inputs["positive"], inputs["negative"], inputs["latent"])
        if kind == "VAEDecodeTiled":
            lat = inputs["samples"]
            ramp = torch.linspace(0, 1, lat["length"]).view(-1, 1, 1, 1)
            return (ramp.expand(lat["length"], lat["h"], lat["w"], 3).contiguous(),)
        raise AssertionError(f"no stand-in for {kind}")


def run_api(prompt: dict, stock: Stock) -> dict:
    done: dict[str, tuple] = {}
    ui: dict[str, dict] = {}
    pending = dict(prompt)
    while pending:
        ready = [nid for nid, n in pending.items() if all(not isinstance(v, list) or v[0] in done for v in n["inputs"].values())]
        assert ready, "the API graph has a cycle or a dangling link"
        for nid in sorted(ready, key=int):
            n = pending.pop(nid)
            inputs = {k: (done[v[0]][v[1]] if isinstance(v, list) else v) for k, v in n["inputs"].items()}
            if n["class_type"] in PACK:
                cls = PACK[n["class_type"]]
                out = getattr(cls(), cls.FUNCTION)(**inputs)
                done[nid] = tuple(out["result"])
                ui[nid] = out.get("ui") or {}
            else:
                done[nid] = stock(n["class_type"], inputs)
    return {"outputs": done, "ui": ui}


def test_the_api_graph_runs_end_to_end_with_stand_in_ltx_nodes(tmp_path, monkeypatch):
    monkeypatch.setenv("XENO_PACK_OUT", str(tmp_path))
    stock = Stock()
    got = run_api(API, stock)
    assert len(stock.seen["EmptyLTXVLatentVideo"]) == 2 and len(stock.seen["VAEDecodeTiled"]) == 2
    prompts = [i["text"] for i in stock.seen["CLIPTextEncode"]]
    assert sum("blooming flower" in p for p in prompts) == 1 and sum("shatters" in p for p in prompts) == 1  # Bloom, then Shatter
    assert [i["noise_seed"] for i in stock.seen["RandomNoise"]] == [2727, 2728]
    assemble = next(nid for nid, n in API.items() if n["class_type"] == "XenoformAssemble")
    path = Path(got["outputs"][assemble][0])
    assert path.is_file() and path.stat().st_size > 10_000
    text = got["ui"][assemble]["text"][0]
    assert text.startswith("2 of 2 shots, 12.00 s (2 morphs)"), text
    timeline = next(nid for nid, n in API.items() if n["class_type"] == "XenoformMorphTimeline")
    view = json.loads(got["ui"][timeline]["xenoform_board"][0])
    assert len(view["board"]["shots"]) == 2 and view["board"]["vibe"] == "chrome-mercury"
