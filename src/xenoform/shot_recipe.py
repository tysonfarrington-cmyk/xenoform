"""Under the hood (docs/UI_REVIEW.md 6.4): every value a shot's morph was rendered with, kept beside its clip.

A morph is one request to ComfyUI: an API graph and its two guide stills. The three render loops
(``cloud_morph._local_clips`` the Draft, ``final_tier.final_clips`` the Final on this GPU, ``cloud_final.cloud_clips``
Cloud Final) fill a ``requests`` list when their caller passes one: per render shot, ``request``'s record of the graph as
it was queued (taken before the stills are uploaded), the stills it morphed between, the key the morph cache files it
under, and ``done``'s time it took. ``dense`` keeps those records in ``simple/simple.json`` as ``renders``, one a shot
beside ``clips`` (``per_shot``), each graph in its own file under ``simple/requests/`` (``store``), and every re-render's
under ``rerenders``. A cut made before the record existed still tells most of it: ComfyUI writes the graph it ran into
each clip (``morph_cache.embedded_graph``), and ``named`` reads that the same way.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

FPS = 24
FRAMES_RANGE = (25, 121)  # LTX lengths are 8k + 1 frames (morph_pass.MIN_LEN, MAX_LEN)
STEPS_RANGE = (1, 100)
CFG_RANGE = (1.0, 20.0)
COMPRESSION_RANGE = (0, 100)  # LTXVPreprocess's img_compression
LORA_STRENGTH_RANGE = (-2.0, 2.0)
TEXT_MAX = 2000
LORA_NODE = "30"  # the LoraLoaderModelOnly a re-render adds to the Draft graph when it is given a LoRA


def _src(value: Any) -> str | None:
    """The node a link input comes from (``["8", 0]`` -> "8"), or None for a plain value."""
    return str(value[0]) if isinstance(value, list) and len(value) == 2 and isinstance(value[0], (str, int)) else None


def _ordered(graph: dict) -> list[tuple[str, dict]]:
    return sorted(((str(k), v) for k, v in (graph or {}).items() if isinstance(v, dict)), key=lambda kv: (len(kv[0]), kv[0]))


def named(graph: dict, nodes: tuple[str, str] | None = None) -> dict:
    """The values a morph graph carries, read by node class so the Draft, the Final and the Cloud graphs read alike: the
    model files, the prompt and the negative (by the conditioning's wiring), the seed, the steps (the scheduler's, or
    the distilled sigmas'), the cfg, the frames and the size, the two guides' strengths and compressions (start and end,
    by which still each preprocess reads; ``nodes`` names the two LoadImage nodes when known), the fps, a LoRA, the
    output scale. Values a graph does not have are None."""
    nodes_in = _ordered(graph)
    by_id = dict(nodes_in)

    def of(cls: str) -> list[tuple[str, dict]]:
        return [(nid, dict(n.get("inputs") or {})) for nid, n in nodes_in if n.get("class_type") == cls]

    def first(cls: str, key: str):
        return next((ins.get(key) for _, ins in of(cls) if ins.get(key) is not None), None)

    texts = {nid: ins.get("text") for nid, ins in of("CLIPTextEncode")}
    prompt = negative = None
    cond = of("LTXVConditioning")
    if cond:
        prompt = texts.get(_src(cond[0][1].get("positive")) or "")
        negative = texts.get(_src(cond[0][1].get("negative")) or "")
    elif texts:
        vals = list(texts.values())
        prompt, negative = vals[0], (vals[1] if len(vals) > 1 else None)
    loads = [nid for nid, _ in of("LoadImage")]
    a_node, b_node = (str(nodes[0]), str(nodes[1])) if nodes else ((loads[0] if loads else ""), (loads[1] if len(loads) > 1 else ""))
    comp: dict[str, Any] = {}
    for _, ins in of("LTXVPreprocess"):
        comp.setdefault(_src(ins.get("image")) or "", ins.get("img_compression"))
    guides = of("LTXVAddGuide")
    g_start = next((ins.get("strength") for _, ins in guides if ins.get("frame_idx") == 0), None)
    g_end = next((ins.get("strength") for _, ins in guides if ins.get("frame_idx") == -1), None)
    latent = (of("EmptyLTXVLatentVideo") or [("", {})])[0][1]
    two_stage = bool(of("LTXVLatentUpsampler"))  # LTX-2.3's Final: stage one at half size, upsampled for stage two
    lw, lh = latent.get("width"), latent.get("height")
    size = [int(lw) * 2, int(lh) * 2] if two_stage and lw and lh else ([lw, lh] if lw and lh else None)
    seeds = [ins.get("noise_seed") for _, ins in of("RandomNoise")]
    sched = [ins.get("steps") for _, ins in of("LTXVScheduler")]
    sigmas = [str(ins.get("sigmas") or "") for _, ins in of("ManualSigmas")]
    steps_all = sched or [len([x for x in s.split(",") if x.strip()]) - 1 for s in sigmas if s]
    cfg_all = [ins.get("cfg") for _, ins in of("CFGGuider")] + [ins.get("video_cfg") for _, ins in of("LTXVDualCFGGuider")]
    out = None  # the scale that feeds the video: what the clip comes out at
    for _, ins in of("CreateVideo"):
        feed = by_id.get(_src(ins.get("images")) or "")
        if feed and feed.get("class_type") == "ImageScale":
            fi = feed.get("inputs") or {}
            out = [fi.get("width"), fi.get("height")]
    loras = [{"name": ins.get("lora_name"), "strength": ins.get("strength_model")} for _, ins in of("LoraLoaderModelOnly")]
    return {
        "model": first("CheckpointLoaderSimple", "ckpt_name") or first("UNETLoader", "unet_name"),
        "text_encoder": first("CLIPLoader", "clip_name") or first("LTXAVTextEncoderLoader", "text_encoder"),
        "prompt": prompt, "negative": negative,
        "seed": seeds[0] if seeds else None, "seeds": seeds,
        "steps": steps_all[0] if steps_all else None, "steps_all": steps_all,
        "cfg": cfg_all[0] if cfg_all else None, "cfg_all": cfg_all,
        "frames": latent.get("length"), "fps": first("CreateVideo", "fps"),
        "width": size[0] if size else None, "height": size[1] if size else None, "out": out,
        "guide_start": g_start, "guide_end": g_end,
        "compression": [comp.get(a_node), comp.get(b_node)] if comp else None,
        "lora": loras[0] if loras else None,
        "upscaler": first("UpscaleModelLoader", "model_name"),
        "sampler": first("KSamplerSelect", "sampler_name") or ("euler ancestral" if of("SamplerEulerAncestral") else None),
    }


def still_of(row: dict | None) -> dict:
    """A guide still as the record keeps it: the library file, the file actually sent (prepared: black ground, portrait
    re-lay), its noun and kind."""
    row = row or {}
    return {"file": str(row.get("file") or ""), "path": str(row.get("path") or ""), "noun": str(row.get("noun") or ""),
            "kind": str(row.get("kind") or "object") if str(row.get("kind") or "") in ("scene", "setting") else "object"}


def request(graph: dict, *, engine: str, stills: tuple[dict, dict], nodes: tuple[str, str], key: str | None = None,
            style: str | None = None, kinds: tuple[str, str] | None = None, render_s: float | None = None,
            overrides: dict | None = None) -> dict:
    """The record of one morph request, taken as it goes to ComfyUI and before the stills are uploaded: the values
    ``named`` reads, the stills, the engine, the morph style and the pair's kinds, the seconds of source asked for, the
    cache key, what a re-render set by hand (``overrides``), and ``graph``: a copy of the API graph with each guide's
    LoadImage named after the still's file (the name the upload gives it in ComfyUI's input folder)."""
    g = json.loads(json.dumps(graph, default=str))
    for nid, row in zip(nodes, stills):
        node = g.get(str(nid))
        if isinstance(node, dict) and row and row.get("path"):
            node.setdefault("inputs", {})["image"] = Path(str(row["path"])).name
    out = {"engine": str(engine), **named(g, nodes), "from": still_of(stills[0]), "to": still_of(stills[1]),
           "style": style, "kinds": list(kinds) if kinds else None, "render_s": render_s, "key": key, "graph": g}
    if overrides:
        out["overrides"] = dict(overrides)
    return out


def done(req: dict | None, *, seconds: float, cached: bool) -> dict | None:
    """The request with the time its clip took (0 when the morph cache answered) and when it landed."""
    if req is None:
        return None
    return {**req, "seconds": round(max(0.0, float(seconds)), 2), "cached": bool(cached),
            "at": datetime.now().astimezone().isoformat(timespec="seconds")}


def slots(requests: list | None, n: int) -> None:
    """Grow a caller's ``requests`` list to ``n`` entries (a loop fills them by index)."""
    if requests is not None:
        while len(requests) < n:
            requests.append(None)


def graph_name(req: dict) -> str:
    """The file a request's graph is kept in: its cache key, else a digest of the graph."""
    key = str(req.get("key") or "")
    if re.fullmatch(r"[0-9a-f]{64}", key):
        return f"{key}.json"
    blob = json.dumps(req.get("graph") or {}, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"g{hashlib.sha256(blob).hexdigest()[:40]}.json"


def store(simple_dir: Path, req: dict | None) -> dict | None:
    """The request as the record keeps it: its graph written once to ``simple/requests/<key>.json`` (immutable: a key
    names one graph) and the record pointing there. A request already stored passes through."""
    if not isinstance(req, dict):
        return None
    graph = req.get("graph")
    if not isinstance(graph, dict):
        return dict(req)
    name = graph_name(req)
    path = Path(simple_dir) / "requests" / name
    try:
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(name + ".tmp")
            tmp.write_text(json.dumps(graph, indent=1, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
    except OSError:
        return {**req, "graph": None}
    return {**req, "graph": f"requests/{name}"}


def graph_of(simple_dir: Path, req: dict | None) -> dict | None:
    """The API graph a stored request names, read back; None when it is not on disk."""
    ref = (req or {}).get("graph")
    if isinstance(ref, dict):
        return copy.deepcopy(ref)
    if not isinstance(ref, str) or not re.fullmatch(r"requests/[0-9a-zA-Z]+\.json", ref):
        return None
    try:
        got = json.loads((Path(simple_dir) / ref).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def per_shot(shots: list[dict], reqs: list) -> list:
    """One render a shot, beside ``clips``: the request of the morph the shot plays (``morph``, its render index), None
    for a shot that plays none (Polly, your clip)."""
    out = []
    for s in shots:
        m = s.get("morph") if isinstance(s, dict) else None
        ok = m is not None and not (s.get("performer") or s.get("own")) and 0 <= int(m) < len(reqs)
        out.append(reqs[int(m)] if ok else None)
    return out


def add_lora(graph: dict, name: str, strength: float, model_node: str = "1") -> dict:
    """``graph`` with a LoraLoaderModelOnly on the checkpoint's model: every input that read the model (``[model_node,
    0]``) reads the LoRA's instead. The Draft graph has none of its own; a re-render adds one only when given a LoRA."""
    nid = LORA_NODE if LORA_NODE not in graph else str(max(int(k) for k in graph if str(k).isdigit()) + 1)
    for key, node in graph.items():
        if not isinstance(node, dict):
            continue
        ins = node.get("inputs") or {}
        for field, value in list(ins.items()):
            if isinstance(value, list) and len(value) == 2 and str(value[0]) == str(model_node) and value[1] == 0:
                ins[field] = [nid, 0]
    graph[nid] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": [str(model_node), 0], "lora_name": str(name), "strength_model": float(strength)}}
    return graph


def now() -> float:
    return time.perf_counter()
