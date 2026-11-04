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


# ------------------------------------------------------------------------------------------------ the recipe Under the hood shows

ENGINE_LABELS = {"ltx095": "LTX-Video 0.9.5 (Draft)", "ltx23": "LTX-2.3 22B (Final)", "ltx25": "LTX-2.5 22B (Final)",
                 "ltx25cloud": "LTX-2.5 22B on Comfy Cloud", "ltx23cloud": "LTX-2.3 22B on Comfy Cloud", "mock": "mock cross-fade (test)"}
TIER_LABELS = {"draft": "Draft", "fast": "Fast Final", "final": "Final", "cloud": "Cloud Final"}
# one line a row, shown when the row has focus: what the value does to a morph
HINTS = {
    "model": "The weights that drew this morph. Draft is LTX-Video 0.9.5 (2B, seconds a morph); Final is LTX-2.3 or 2.5 "
             "(22B, sharper, minutes a morph).",
    "prompt": "What the morph is asked to show between the two stills. The stills carry the objects; the words carry the "
              "change, the light and the look.",
    "negative": "What the model is steered away from: text, a second object, a cut, flicker.",
    "from": "The still the morph starts on. Swap it on the Shot tab.",
    "to": "The still the morph lands on, and the next shot starts from. Swap it on the Shot tab.",
    "seed": "The noise the morph grows from. Another seed is another take of the same request; the same seed and values "
            "give the same clip back.",
    "steps": "How many denoising passes. More is finer and slower, about in proportion; under 10 gets mushy, past 30 "
             "gains little.",
    "cfg": "How hard the words pull against the guide stills. Around 3 is the Draft's own; higher follows the prompt more "
           "and can burn or flicker.",
    "frames": "How long the morph is rendered (LTX takes 8k + 1 frames). The shot keeps its beats: a longer morph plays "
              "faster in it, a shorter one slower.",
    "size": "The size the morph renders at; the cut scales it to its own size afterwards.",
    "guide_start": "How firmly the first frame holds the start still, 0 to 1.",
    "guide_end": "How firmly the last frame lands on the end still, 0 to 1. Lower lets the morph wander before it "
                 "arrives; 1 pins it.",
    "compression": "How much each guide still is softened before it steers the morph, 0 to 100 (start, end). More gives "
                   "the morph freedom; a scene stays at 0 or it loses its texture.",
    "style": "How the object changes: Melt, Shatter, Bloom, Spin or Fold. It rewrites the prompt's opening.",
    "lora": "A LoRA trained for LTX-Video 0.9.5 nudges the model's look; strength around 0.5 to 1. One made for another "
            "model fails or does nothing.",
}
EDITABLE = ("prompt", "negative", "seed", "steps", "cfg", "frames", "guide_start", "guide_end", "compression", "style", "lora")
COMPARED = ("model", "prompt", "negative", "seed", "steps", "cfg", "frames", "width", "height", "guide_start", "guide_end",
            "compression", "style", "lora")
DEFAULT_MORPH_S = 25.0  # a Draft morph on a 12 GB card when the cut measured none (docs/MORPH_ENGINE_PLAN.md)
DEFAULT_RECUT_S = 30.0


def frame_choices() -> list[int]:
    """The lengths a morph may render at: every 8k + 1 frames from 25 (about 1 s) to 121 (5 s)."""
    return list(range(FRAMES_RANGE[0], FRAMES_RANGE[1] + 1, 8))


def _shots(rec: dict) -> list[dict]:
    return [s for s in (rec.get("plan_shots") or rec.get("shots") or []) if isinstance(s, dict)]


def _kind_of(rec: dict, f: str) -> str:
    return "scene" if f in set(rec.get("scene_files") or []) else "setting" if f in set(rec.get("setting_files") or []) else "object"


def morph_of(rec: dict, i: int) -> int | None:
    """The chain morph shot ``i`` plays (its render index), None for a shot that plays none."""
    shots = _shots(rec)
    if not 0 <= i < len(shots):
        return None
    s = shots[i]
    if s.get("performer") or s.get("own") or s.get("generated") or s.get("dream"):
        return None
    m = s.get("morph", s.get("clip"))
    n = len(rec.get("stills") or [])
    if m is None and len(rec.get("clips") or []) == n - 1:  # a record from before the morph index: one morph a shot
        m = i
    return int(m) if m is not None and 0 <= int(m) < max(0, n - 1) else None


def shot_kind(rec: dict, i: int) -> tuple[str, str]:
    """What shot ``i`` plays, in a word and a sentence: a morph of the chain, a morph of a generated run, Polly, your
    clip, or a dream over it."""
    s = _shots(rec)[i]
    now_shots = rec.get("shots") or []
    cur = now_shots[i] if i < len(now_shots) and isinstance(now_shots[i], dict) else s
    if s.get("performer") or cur.get("performer"):
        return "performer", "Polly's shot: MiniMax H3 sings or plays to the song here. It is not a morph, so there is no morph request to show."
    if s.get("own") or cur.get("own"):
        return "own", "One of your clips plays here, trimmed to the beat. Nothing was generated for it."
    if s.get("dream") or cur.get("dream"):
        return "dream", ("Dreamed over: Z-Image Turbo re-dreamed this span frame by frame from the morph under it. The "
                         "values below are the morph's, as it was before the dream.")
    if s.get("generated") or cur.get("generated"):
        return "generated", "A generated run (Generate here): its own chain of morphs, rendered over this span."
    return "morph", ""


def preset_of(rec: dict, i: int, style: str | None = None) -> dict | None:
    """What the vibe's preset gives shot ``i`` today: the Draft request a Make would send for its morph (the prompt for
    its pair and style with the guardrails' hint, the tuned steps, cfg, compression and end guide, the cut's seed for
    that morph, the length from its seconds of source, the cut's render size), built from the same settings the Draft
    loop sends (``cloud_morph.draft_settings``) and read back with ``named``. None for a shot that plays no chain morph."""
    from xenoform import morph_pass as mp
    from xenoform.cloud_morph import draft_settings

    m = morph_of(rec, i)
    if m is None:
        return None
    files = [str(f) for f in rec.get("stills") or []]
    kinds = mp.pair_kinds({"kind": _kind_of(rec, files[m])}, {"kind": _kind_of(rec, files[m + 1])})
    styles = [str(x) for x in rec.get("morph_styles") or []]
    style = (style or (styles[i] if i < len(styles) else "") or "melt").strip().lower()
    vibe = str(rec.get("vibe") or "")
    prep = rec.get("prep") if isinstance(rec.get("prep"), dict) else {}
    state = dict(rec.get("recut_state") or {})  # the Make's own (its still_background is the prompt hint's), as a re-render reads it
    size =tuple(prep.get("draft_size") or (mp.WIDTH, mp.HEIGHT)) if prep.get("native_draft") else (mp.WIDTH, mp.HEIGHT)
    s = _shots(rec)[i]
    render_s = s.get("plan_render_s") or s.get("render_s") or (rec.get("chain") or {}).get("clip_s") \
        or max(2, int(round(float(s.get("seconds") or 2.0))))  # the Make's own length, before any re-render moved it
    graph = json.loads(mp.GRAPH.read_text(encoding="utf-8"))
    for node, field, value in draft_settings({"render_s": render_s, "seconds": float(s.get("seconds") or 2.0)}, kinds,
                                             seed=int(rec.get("seed") or 2727) + m, vibe=vibe, style=style, size=size,
                                             state=state):
        graph.setdefault(node, {}).setdefault("inputs", {})[field] = value
    out = {"engine": "ltx095", **named(graph, ("6", "7")), "style": style, "kinds": list(kinds), "render_s": render_s}
    out["seed_rule"] = f"the cut's seed {int(rec.get('seed') or 2727)} + {m}"
    return out


def _round(v: Any) -> Any:
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    if isinstance(v, (list, tuple)):
        return [_round(x) for x in v]
    if isinstance(v, dict):
        return {k: _round(x) for k, x in sorted(v.items())}
    return str(v).strip()


def differs(used: dict, preset: dict | None) -> dict:
    """Per compared field, whether the used value differs from the preset's (False everywhere without a preset)."""
    if not preset:
        return {k: False for k in COMPARED}
    return {k: _round(used.get(k)) != _round(preset.get(k)) for k in COMPARED}


def _legacy(job_dir: Path, rec: dict, i: int) -> tuple[dict | None, str]:
    """A shot rendered before the record existed: the graph ComfyUI wrote into its clip, read as a recorded request
    would be ("clip"), else nothing ("none")."""
    from xenoform import morph_cache as mc
    from xenoform.lane import noun_of

    clips = list(rec.get("clips") or [])
    clip = Path(str(clips[i])) if i < len(clips) else None
    graph = mc.embedded_graph(clip) if clip and clip.is_file() else None
    if not graph:
        return None, "none"
    m = morph_of(rec, i)
    files = [str(f) for f in rec.get("stills") or []]
    styles = [str(x) for x in rec.get("morph_styles") or []]

    def row(k: int | None) -> dict:
        if k is None or not 0 <= k < len(files):
            return still_of(None)
        return {"file": files[k], "path": "", "noun": noun_of(files[k]), "kind": _kind_of(rec, files[k])}

    nodes = ("6", "7") if "6" in graph and "7" in graph else ("100", "101") if "100" in graph else None
    shots = _shots(rec)
    got = mc.key_from_clip(clip)
    used = {"engine": mc.engine_of(graph, clip.name) or ("ltx095" if "ltx-video-2b" in json.dumps(graph) else ""),
            **named(graph, nodes), "from": row(m), "to": row(None if m is None else m + 1),
            "style": styles[i] if i < len(styles) else None, "render_s": shots[i].get("render_s") if i < len(shots) else None,
            "key": got[0] if got else None}
    return used, "clip"


def cost_of(job_dir: Path, rec: dict) -> dict:
    """What a re-render of one shot costs on this machine: the cut's own measured seconds a Draft morph (the renders'
    times, else took.json's morph phase over its morphs), then the re-cut (took.json's cut phase), else the defaults."""
    measured = [r for r in list(rec.get("renders") or []) + [x.get("request") for x in rec.get("rerenders") or [] if isinstance(x, dict)]
                if isinstance(r, dict) and not r.get("cached") and r.get("engine") == "ltx095" and float(r.get("seconds") or 0) > 1]
    times = sorted(float(r["seconds"]) for r in measured)
    basis = "measured on this cut"
    try:
        took = json.loads((Path(job_dir) / "took.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        took = {}
    parts = took.get("breakdown") if isinstance(took.get("breakdown"), dict) else {}
    morphs = len({str(c) for c in rec.get("clips") or []}) or 1
    draft = str(rec.get("tier") or "draft") == "draft" and not rec.get("fast") and not rec.get("cloud")
    if times:
        gpu = times[len(times) // 2]
    elif float(parts.get("morphs") or 0) > 0 and draft:
        gpu = float(parts["morphs"]) / morphs
        basis = "this cut's morph time over its morphs"
    else:
        gpu, basis = DEFAULT_MORPH_S, "a Draft morph on a 12 GB card"
    recut = float(parts.get("cut") or 0) or DEFAULT_RECUT_S
    return {"gpu_s": int(round(gpu)), "recut_s": int(round(recut)), "basis": basis}


def rerender_gate(rec: dict, i: int) -> tuple[bool, str]:
    """Whether shot ``i`` can be re-rendered from Under the hood, and why not in a sentence (L8)."""
    if str(rec.get("mode") or "") == "song":
        return False, "A whole song is laid together from its passages: open the passage and re-render the shot there."
    if str(rec.get("source") or "") == "clips":
        return False, "A clips cut morphs between your clips; its shots are made again with a new Make."
    tier = "cloud" if rec.get("cloud") else "fast" if rec.get("fast") else str(rec.get("tier") or "draft")
    if tier in ("final", "fast", "cloud"):
        return False, (f"This cut is {TIER_LABELS.get(tier, tier)}: a shot re-renders as a Draft morph, which would be the one "
                       "soft shot in a sharp cut. Make the cut again to change it.")
    kind, _ = shot_kind(rec, i)
    if kind in ("performer", "own"):
        return False, "This shot plays no morph of the chain, so there is nothing to re-render."
    if kind in ("generated", "dream"):
        return False, ("This shot is part of a " + ("generated run" if kind == "generated" else "dream")
                       + ": make the run again from the Shot tab.")
    if morph_of(rec, i) is None:
        return False, "This shot plays no morph of the chain, so there is nothing to re-render."
    return True, ""


def _seed_file(job_dir: Path) -> dict | None:
    try:
        seed = json.loads((Path(job_dir) / "seed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {k: seed.get(k) for k in ("seed", "video_model", "quality", "fps", "width", "height") if k in seed} or None


def recipe(job_dir: Path, rec: dict, i: int, *, style: str | None = None, check: bool = True) -> dict:
    """Under the hood for shot ``i``: the values its morph was rendered with (``used``: the record's request, else the
    graph ComfyUI wrote into the clip, said so in ``source`` and ``note``), the preset's (``preset_of``) and per field
    whether they differ, whether the clip's own graph confirms the record (``verified``), whether it can be re-rendered
    and what that costs, and the choices the editable rows offer."""
    from xenoform import morph_cache as mc
    from xenoform import morph_style as ms

    shots = _shots(rec)
    if not 0 <= i < len(shots):
        raise ValueError(f"This cut has {len(shots)} shots; shot {i} is not one of them.")
    s = shots[i]
    out: dict[str, Any] = {"shot": i, "shots": len(shots), "start": s.get("start"), "end": s.get("end"),
                           "seconds": s.get("seconds"), "section": s.get("section") or ""}
    kind, sentence = shot_kind(rec, i)
    out.update({"kind": kind, "note": sentence})
    plays = ((rec.get("shot_overrides") or {}).get(str(i)) or {}).get("source")
    if plays is not None and str(plays).lstrip("-").isdigit() and int(plays) != i and 0 <= int(plays) < len(shots):
        out["plays"] = int(plays)  # Move or Duplicate: the slot shows another shot's morph
    renders = list(rec.get("renders") or [])
    used = renders[i] if i < len(renders) and isinstance(renders[i], dict) else None
    source = "record"
    if used is None and kind in ("morph", "dream"):
        used, source = _legacy(job_dir, rec, i)
        if used is not None:
            out["note"] = (out["note"] + " " if out["note"] else "") + (
                "Read from the clip itself: this cut was made before the desk kept each morph's request, and ComfyUI "
                "wrote the graph it ran into the clip.")
    if used is None:
        source = "none"
        if kind in ("morph", "dream", "generated"):
            out["note"] = (out["note"] + " " if out["note"] else "") + (
                "Not recorded: this cut was made before the desk kept each morph's request, and its clip carries no "
                "graph. The preset below is what the vibe gives this shot today.")
            sf = _seed_file(job_dir)
            if sf:
                out["seed_file"] = sf
    used = dict(used or {})
    tier = "cloud" if rec.get("cloud") else "fast" if rec.get("fast") else str(rec.get("tier") or "draft")
    engine = str(used.get("engine") or ("ltx095" if tier in ("draft", "fast") else ""))
    preset = preset_of(rec, i, style=style) if kind == "morph" and engine == "ltx095" else None
    out.update({"recorded": source == "record", "source": source, "engine": engine,
                "engine_label": ENGINE_LABELS.get(engine, engine or "unknown"), "tier": tier,
                "tier_label": TIER_LABELS.get(tier, tier), "used": used, "preset": preset,
                "differs": differs(used, preset) if used else {k: False for k in COMPARED},
                "edited": sorted((used.get("overrides") or {}).keys()) if isinstance(used.get("overrides"), dict) else []})
    verified = None
    clips = list(rec.get("clips") or [])
    if check and source == "record" and used.get("key") and not used.get("finish") and i < len(clips):
        clip = Path(str(clips[i]))
        got = mc.key_from_clip(clip, engine) if clip.is_file() else None
        verified = None if got is None else got[0] == used["key"]
    out["verified"] = verified
    ok, why = rerender_gate(rec, i)
    out["rerender"] = {"ok": ok, "why": why}
    out["cost"] = cost_of(job_dir, rec)
    tries = sum(1 for r in rec.get("rerenders") or [] if isinstance(r, dict) and r.get("shot") == i)
    m = morph_of(rec, i)
    if m is not None:  # what a re-render with no seed given takes: the next in the shot's own sequence
        out["next_seed"] = int(rec.get("seed") or 2727) + m + 1009 * (tries + 1)
    out["choices"] = {"styles": [{"id": k, "label": ms.LABELS[k], "note": ms.NOTES[k]} for k in ms.STYLES],
                      "frames": frame_choices(), "steps": list(STEPS_RANGE), "cfg": list(CFG_RANGE),
                      "compression": list(COMPRESSION_RANGE), "guide": [0.0, 1.0], "lora_strength": list(LORA_STRENGTH_RANGE),
                      "loras": lora_files(), "fps": FPS}
    out["hints"] = dict(HINTS)
    return out


def workflow_of(job_dir: Path, rec: dict, i: int) -> dict | None:
    """The API graph shot ``i``'s morph ran, as ComfyUI loads it: the stored request's graph, else the one the clip
    carries (its LoadImage names are the names the stills were uploaded under), each guide still's node titled."""
    from xenoform import morph_cache as mc

    renders = list(rec.get("renders") or [])
    req = renders[i] if i < len(renders) and isinstance(renders[i], dict) else None
    graph = graph_of(Path(job_dir) / "simple", req) if req else None
    if graph is None:
        clips = list(rec.get("clips") or [])
        clip = Path(str(clips[i])) if i < len(clips) else None
        graph = mc.embedded_graph(clip) if clip and clip.is_file() else None
        if graph:
            for node in graph.values():
                if isinstance(node, dict):
                    node.pop("is_changed", None)  # ComfyUI's own note on the run, not an input
    if not graph:
        return None
    files = [str(f) for f in rec.get("stills") or []]
    m = morph_of(rec, i)
    from xenoform.lane import noun_of

    nouns = {"start": (req or {}).get("from", {}).get("noun") or (noun_of(files[m]) if m is not None and m < len(files) else ""),
             "end": (req or {}).get("to", {}).get("noun") or (noun_of(files[m + 1]) if m is not None and m + 1 < len(files) else "")}
    for nid, node in graph.items():
        if isinstance(node, dict) and node.get("class_type") == "LoadImage":
            end = "start" if nid in ("6", "100") else "end" if nid in ("7", "101") else ""
            title = ("Start still" if end == "start" else "End still" if end == "end" else "Still")
            node.setdefault("_meta", {})["title"] = f"{title}: {nouns[end]}" if end and nouns[end] else title
    return graph


OVERRIDES = ("prompt", "negative", "steps", "cfg", "frames", "guide_start", "guide_end", "compression", "lora", "lora_strength")


def _number(raw: Any, name: str, lo: float, hi: float, *, whole: bool = False) -> float | int:
    try:
        v = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"The {name} is a number, {lo:g} to {hi:g}.") from exc
    if v != v or not lo <= v <= hi:
        raise ValueError(f"The {name} is {lo:g} to {hi:g}; {raw} is outside that.")
    if whole:
        if not float(v).is_integer():
            raise ValueError(f"The {name} is a whole number, {lo:g} to {hi:g}.")
        return int(v)
    return round(v, 4)


def clean_overrides(raw: dict | None, *, loras: list[str] | None = None) -> dict:
    """A re-render's own values, checked and in the form the Draft graph takes (``cloud_morph.draft_settings``):
    ``prompt`` and ``negative`` (text; an empty prompt is no override, an empty negative is no negative), ``steps`` (1 to
    100), ``cfg`` (1 to 20), ``frames`` (8k + 1, 25 to 121), ``guide_start`` and ``guide_end`` (0 to 1), ``compression``
    (one number or a start and end pair, 0 to 100), ``lora`` (a file of this machine's LoRA folder, ``lora_files``) with
    ``lora_strength`` (-2 to 2, 1 when not given). Keys not given or None are left to the preset. ValueError in plain
    words for anything else."""
    raw = dict(raw or {})
    out: dict[str, Any] = {}
    for key in ("prompt", "negative"):
        if raw.get(key) is None:
            continue
        text = str(raw[key]).strip()
        if len(text) > TEXT_MAX:
            raise ValueError(f"The {key} is {len(text)} characters; keep it under {TEXT_MAX}.")
        if key == "prompt" and not text:
            continue  # an empty prompt asks for nothing: the preset's stands
        out[key] = text
    if raw.get("steps") not in (None, ""):
        out["steps"] = _number(raw["steps"], "steps", *STEPS_RANGE, whole=True)
    if raw.get("cfg") not in (None, ""):
        out["cfg"] = _number(raw["cfg"], "CFG", *CFG_RANGE)
    if raw.get("frames") not in (None, ""):
        frames = _number(raw["frames"], "length in frames", *FRAMES_RANGE, whole=True)
        if (frames - 1) % 8:
            raise ValueError(f"A morph is 8k + 1 frames long (25, 33, 41 ... 121); {frames} is not one of them.")
        out["frames"] = frames
    for key, name in (("guide_start", "first guide's strength"), ("guide_end", "last guide's strength")):
        if raw.get(key) not in (None, ""):
            out[key] = _number(raw[key], name, 0.0, 1.0)
    if raw.get("compression") not in (None, ""):
        comp = raw["compression"]
        pair = list(comp) if isinstance(comp, (list, tuple)) else [comp, comp]
        if len(pair) != 2:
            raise ValueError("The compression is one number, or two: the start still's and the end still's.")
        out["compression"] = [_number(v, "compression", *COMPRESSION_RANGE, whole=True) for v in pair]
    name = str(raw.get("lora") or "").strip()
    if name and name.lower() not in ("none", "off"):
        have = lora_files() if loras is None else list(loras)
        if name not in have:
            raise ValueError(f"No LoRA called {name} in this machine's loras folder."
                             + (f" It has {', '.join(have[:6])}{' ...' if len(have) > 6 else ''}." if have else " It has none."))
        out["lora"] = name
        out["lora_strength"] = _number(raw.get("lora_strength", 1.0), "LoRA strength", *LORA_STRENGTH_RANGE) \
            if raw.get("lora_strength") not in (None, "") else 1.0
    return out


def lora_files() -> list[str]:
    """The LoRA files this machine has (``<models>/loras``), the names a re-render may give; [] when there is no folder."""
    try:
        from xenoform.models_setup import models_root

        folder = Path(models_root()) / "loras"
        return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".safetensors", ".pt", ".ckpt"))
    except Exception:  # noqa: BLE001 - no models folder: no LoRA to offer
        return []
