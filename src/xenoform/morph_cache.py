"""The morph cache: a rendered morph clip kept by what it was made from, so the same request is never rendered twice
(docs/MUSIC_VIDEO_PLAN.md section 4). The research found 31 identical requests rendered twice, about 120 to 200 Cloud
credits, and that a seed does not bring a clip back (10 of 30 reruns matched): clips are kept, not seeds.

Where: ``work/ui/morph_cache/<engine>/<key>.mp4`` with ``<key>.json`` beside it (``XENO_MORPH_CACHE`` moves it, "off"
turns it off). The engine is the loop's: ``ltx095`` the Draft, ``ltx23`` or ``ltx25`` the Final on this GPU,
``ltx25cloud`` or ``ltx23cloud`` the Cloud Final; one engine never answers for another.

The key is a sha256 over the engine and the graph exactly as it goes to ComfyUI, in one canonical form: each node's class
and inputs (its title and ComfyUI's own notes left out, a number written one way whether it came as 24 or 24.0), the two
guide stills as the sha256 of their bytes (the value ComfyUI's LoadImage reports as ``is_changed``), the output's file
name left out. So the key hashes both guide stills' bytes, the final prompt and negative, the seed, the frames, the
engine, the graph with its models and sizes, the img_compression, the end_strength, the steps and the cfg (``parts``
names each one in the sidecar); a change to any of them is a new key, and a pin or a swap that changes a still's bytes is
a miss, never a wrong clip.

The three loops (``cloud_morph._local_clips``, ``final_tier.final_clips``, ``cloud_final.cloud_clips``) ask ``get`` before a
render and ``put`` what they rendered. A hit copies the kept clip into the job: nothing is uploaded, queued or sent, so a
Cloud hit never spends a credit; a miss renders as it always did, behind the same gates (the Make's tick, the key, the cap).

``put`` reads the rendered clip's own record of what it ran (ComfyUI writes the graph into the mp4's ``prompt`` tag, with
each LoadImage's ``is_changed``) and notes in the sidecar whether that gives the same key (``verified``). ``seed`` fills
the cache from the jobs already on disk by the same reading, so nothing about an old clip is guessed: a clip whose graph
or still hashes are missing is skipped.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("xenoform")

ROOT = Path(__file__).resolve().parents[2]
ENV = "XENO_MORPH_CACHE"
ENGINES = ("ltx095", "ltx23", "ltx25", "ltx23cloud", "ltx25cloud")
# the raw morph clips a job keeps (simple/localNN.mp4 ...): what seeding reads; the scaled copies (cloud_full, fast) are not
# morphs of a request but of a clip, and stay out
CLIP_RE = re.compile(r"^(local|final|cloud|draft_fallback)(\d\d)\.mp4$")


def root() -> Path | None:
    """The cache folder, or None when ``XENO_MORPH_CACHE`` is "off"."""
    raw = os.environ.get(ENV, "").strip()
    if raw.lower() in ("off", "0", "false", "no", "none"):
        return None
    return Path(raw) if raw else ROOT / "work" / "ui" / "morph_cache"


def enabled() -> bool:
    return root() is not None


def sha256_file(path: Any) -> str | None:
    """The sha256 of a file's bytes (hex), or None when it cannot be read."""
    try:
        h = hashlib.sha256()
        with open(str(path), "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


# ------------------------------------------------------------------------------------------------ the key


def _norm(value: Any) -> Any:
    """A graph input in one written form: a whole number as an int (24 and 24.0 alike), lists and dicts the same way."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        f = float(value)
        if math.isfinite(f) and f.is_integer() and abs(f) < 2 ** 53:
            return int(f)
        return f
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in value.items()}
    raise TypeError(f"not a graph value: {type(value).__name__}")


def canonical(graph: dict, images: dict[str, str]) -> dict:
    """The graph as the key reads it: each node's ``class_type`` and ``inputs`` only, a LoadImage's ``image`` the sha256 of
    its bytes (``images``: node id -> hex; a LoadImage with no hash cannot be keyed: KeyError), a SaveVideo's file name out."""
    out: dict[str, dict] = {}
    for nid, node in (graph or {}).items():
        if not isinstance(node, dict):
            continue
        cls = str(node.get("class_type") or "")
        ins = dict(node.get("inputs") or {})
        if cls == "LoadImage" or str(nid) in images:
            digest = images.get(str(nid))
            if not digest:
                raise KeyError(f"no still hash for node {nid}")
            ins["image"] = "sha256:" + digest
        ins.pop("filename_prefix", None)  # where ComfyUI writes the clip: a name, not the picture
        out[str(nid)] = {"class_type": cls, "inputs": _norm(ins)}
    if not out:
        raise ValueError("an empty graph")
    return out


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def key_of(canon: dict, engine: str) -> str:
    return _digest({"engine": str(engine), "graph": canon})


NAMED = {"CLIPTextEncode": ("text",), "RandomNoise": ("noise_seed",), "EmptyLTXVLatentVideo": ("length", "width", "height"),
         "LTXVPreprocess": ("img_compression",), "LTXVAddGuide": ("strength",), "LTXVScheduler": ("steps",),
         "CFGGuider": ("cfg",), "LTXVDualCFGGuider": ("video_cfg",), "ManualSigmas": ("sigmas",), "LoadImage": ("image",)}


def _ordered(canon: dict) -> list[tuple[str, dict]]:
    return sorted(canon.items(), key=lambda kv: (len(kv[0]), kv[0]))


def parts_of(canon: dict, engine: str) -> dict:
    """The request a key stands for, named: the stills, the prompt and the negative, the seed, the frames and size, the
    guides' compression and end strength, the steps and the cfg, the engine, and ``graph``: the hash of everything else
    (the nodes, their wiring, the models)."""
    nodes = _ordered(canon)

    def ins(cls: str) -> list[dict]:
        return [n["inputs"] for _, n in nodes if n["class_type"] == cls]

    texts = {nid: n["inputs"].get("text") for nid, n in nodes if n["class_type"] == "CLIPTextEncode"}
    prompt = negative = None
    for _, n in nodes:  # the conditioning says which text is which
        if n["class_type"] == "LTXVConditioning":
            pos, neg = n["inputs"].get("positive"), n["inputs"].get("negative")
            prompt = texts.get(str(pos[0])) if isinstance(pos, list) and pos else None
            negative = texts.get(str(neg[0])) if isinstance(neg, list) and neg else None
            break
    if prompt is None and texts:
        ordered = list(texts.values())
        prompt, negative = ordered[0], (ordered[1] if len(ordered) > 1 else None)
    latent = (ins("EmptyLTXVLatentVideo") or [{}])[0]
    sigmas = (ins("ManualSigmas") or [{}])[0].get("sigmas")
    steps = [i.get("steps") for i in ins("LTXVScheduler")] or ([len(str(sigmas).split(",")) - 1] if sigmas else [])
    blank = {nid: {"class_type": n["class_type"],
                   "inputs": {k: v for k, v in n["inputs"].items() if k not in NAMED.get(n["class_type"], ())}}
             for nid, n in nodes}
    return {"engine": engine, "stills": [i.get("image") for i in ins("LoadImage")], "prompt": prompt, "negative": negative,
            "seed": [i.get("noise_seed") for i in ins("RandomNoise")], "frames": latent.get("length"),
            "width": latent.get("width"), "height": latent.get("height"),
            "img_compression": [i.get("img_compression") for i in ins("LTXVPreprocess")],
            "end_strength": [i.get("strength") for i in ins("LTXVAddGuide") if i.get("frame_idx") == -1],
            "steps": steps, "cfg": [i.get("cfg") for i in ins("CFGGuider")] + [i.get("video_cfg") for i in ins("LTXVDualCFGGuider")],
            "graph": _digest(blank)}


def key_for(graph: dict, stills: dict[str, Any], engine: str) -> tuple[str, dict] | None:
    """``(key, parts)`` for a request about to be sent: ``graph`` the API graph, ``stills`` the guide stills by node id
    (local paths; their bytes are hashed), ``engine`` the loop's. None when the cache is off or the request cannot be keyed
    (a still that cannot be read, a value that is not plain JSON): the loop then renders as it always did."""
    if root() is None:
        return None
    images = {}
    for nid, path in (stills or {}).items():
        digest = sha256_file(path)
        if not digest:
            return None
        images[str(nid)] = digest
    try:
        canon = canonical(graph, images)
    except (KeyError, TypeError, ValueError):
        return None
    return key_of(canon, engine), parts_of(canon, engine)


# ------------------------------------------------------------------------------------------------ the clips


def _paths(engine: str, key: str) -> tuple[Path, Path] | None:
    base = root()
    if base is None or not re.fullmatch(r"[0-9a-f]{64}", str(key or "")) or not re.fullmatch(r"[a-z0-9]+", str(engine or "")):
        return None
    clip = base / engine / f"{key}.mp4"
    return clip, clip.with_suffix(".json")


def lookup(engine: str, key: str) -> Path | None:
    """The kept clip for ``key``, or None: the clip and its sidecar there, the sidecar's key and engine the same, the clip's
    size and sha256 what the sidecar says (a clip cut short or overwritten is a miss, never a wrong picture)."""
    got = _paths(engine, key)
    if got is None:
        return None
    clip, side = got
    try:
        meta = json.loads(side.read_text(encoding="utf-8"))
        size = clip.stat().st_size
    except (OSError, ValueError):
        return None
    if meta.get("key") != key or meta.get("engine") != engine or int(meta.get("bytes") or -1) != size or size <= 0:
        return None
    if sha256_file(clip) != meta.get("sha256"):
        return None
    return clip


def get(engine: str, key_parts: tuple[str, dict] | None, dest: Path) -> bool:
    """Copy the kept clip for this request to ``dest``; True on a hit. Nothing is written on a miss."""
    if not key_parts:
        return False
    clip = lookup(engine, key_parts[0])
    if clip is None:
        return False
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".cache-tmp")
    try:
        shutil.copyfile(clip, tmp)
        os.replace(tmp, dest)
    except OSError as exc:
        log.warning("morph cache: %s could not be copied (%s); rendering it", clip, exc)
        tmp.unlink(missing_ok=True)
        return False
    return True


def put(engine: str, key_parts: tuple[str, dict] | None, clip: Path, *, source: Any = None,
        verify: bool = True) -> Path | None:
    """Keep a rendered clip under its request's key (``key_for``), with the sidecar: the key, the engine, the parts, the
    clip's size and sha256, where it came from and when, and ``verified``: whether the graph ComfyUI wrote into the clip
    gives the same key (None when the clip carries none). Atomic; a clip already kept is left as it is. Never raises."""
    if not key_parts:
        return None
    key, parts = key_parts
    got = _paths(engine, key)
    clip = Path(clip)
    try:
        if got is None or not clip.is_file() or clip.stat().st_size <= 0:
            return None
    except OSError:
        return None
    dest, side = got
    if lookup(engine, key) is not None:
        return dest
    verified = None
    if verify:
        read = key_from_clip(clip, engine)
        verified = None if read is None else read[0] == key
        if verified is False:
            log.warning("morph cache: %s carries a graph whose key differs from the request's; kept under the request's", clip)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".put-tmp")
        shutil.copyfile(clip, tmp)
        digest = sha256_file(tmp)
        size = tmp.stat().st_size
        os.replace(tmp, dest)
        meta = {"key": key, "engine": engine, "bytes": size, "sha256": digest, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": str(source or clip), "verified": verified, "parts": parts}
        stmp = side.with_name(side.name + ".put-tmp")
        stmp.write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(stmp, side)
        return dest
    except OSError as exc:
        log.warning("morph cache: %s not kept (%s)", clip, exc)
        return None


# ------------------------------------------------------------------------------------------------ a clip's own record


def embedded_graph(clip: Path) -> dict | None:
    """The API graph ComfyUI ran for a clip, from the mp4's ``prompt`` tag, or None."""
    try:
        out = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format_tags=prompt",
                              "-of", "json", str(clip)], capture_output=True, text=True, timeout=30)
        tags = (json.loads(out.stdout or "{}").get("format") or {}).get("tags") or {}
        raw = tags.get("prompt") or tags.get("PROMPT")
        graph = json.loads(raw) if raw else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return graph if isinstance(graph, dict) else None


def _images_of(graph: dict) -> dict[str, str] | None:
    """Each LoadImage's still hash from its ``is_changed`` (the sha256 ComfyUI took of the file), or None when one has none."""
    out = {}
    for nid, node in graph.items():
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        mark = node.get("is_changed")
        mark = mark[0] if isinstance(mark, list) and mark else mark
        if not (isinstance(mark, str) and re.fullmatch(r"[0-9a-f]{64}", mark)):
            return None
        out[str(nid)] = mark
    return out


def engine_of(graph: dict, name: str = "") -> str | None:
    """The loop a kept clip came from, by its file name and the models its graph loads; None when it cannot be told."""
    models = " ".join(str(v) for n in graph.values() if isinstance(n, dict) for v in (n.get("inputs") or {}).values()
                      if isinstance(v, str) and v.endswith(".safetensors")).lower()
    kind = (CLIP_RE.match(Path(name).name).group(1) if CLIP_RE.match(Path(name).name) else "")
    if "ltx-video-2b-v0.9.5" in models:
        return "ltx095" if kind in ("local", "draft_fallback", "") else None
    model = "ltx25" if "ltx-2.5" in models else "ltx23" if "ltx-2.3" in models else None
    if model is None or kind not in ("final", "cloud"):
        return None
    return model + ("cloud" if kind == "cloud" else "")


def key_from_clip(clip: Path, engine: str | None = None) -> tuple[str, str, dict] | None:
    """``(key, engine, parts)`` a rendered clip stands for, read from its own embedded graph and still hashes (``engine``
    given, else told by ``engine_of``); None when the clip does not say enough."""
    graph = embedded_graph(Path(clip))
    if not graph:
        return None
    images = _images_of(graph)
    eng = engine or engine_of(graph, Path(clip).name)
    if images is None or not eng:
        return None
    try:
        canon = canonical(graph, images)
    except (KeyError, TypeError, ValueError):
        return None
    return key_of(canon, eng), eng, parts_of(canon, eng)


# ------------------------------------------------------------------------------------------------ seeding


def seed(work_ui: Path, *, dry_run: bool = False, limit: int | None = None,
         report: Callable[[str], None] | None = None) -> dict:
    """Fill the cache from the jobs on disk under ``work_ui`` (``jobs/<id>/simple/``, with its ``rerenders`` and
    ``inserts``): every raw morph clip (localNN, finalNN, cloudNN, draft_fallbackNN) whose embedded graph and still hashes
    give its key and whose engine can be told is kept, the ones already kept counted, the rest skipped with a reason.
    ``dry_run`` reads and counts and writes nothing. Returns the tally."""
    jobs = Path(work_ui) / "jobs"
    out = {"seen": 0, "kept": 0, "had": 0, "skipped": {}, "engines": {}, "cache": str(root()), "dry_run": bool(dry_run)}
    if root() is None:
        out["skipped"]["cache off"] = 1
        return out

    def skip(why: str) -> None:
        out["skipped"][why] = out["skipped"].get(why, 0) + 1

    clips = []
    for job in sorted(p for p in jobs.iterdir() if p.is_dir()) if jobs.is_dir() else []:
        simple = job / "simple"
        if not simple.is_dir():
            continue
        clips += [p for p in sorted(simple.glob("*.mp4")) if CLIP_RE.match(p.name)]
    for clip in clips[: limit or None]:
        out["seen"] += 1
        got = key_from_clip(clip)
        if got is None:
            skip("no graph or still hashes in the clip, or an engine that cannot be told")
            continue
        key, eng, parts = got
        out["engines"][eng] = out["engines"].get(eng, 0) + 1
        if lookup(eng, key) is not None:
            out["had"] += 1
            continue
        if dry_run:
            out["kept"] += 1
            continue
        if put(eng, (key, parts), clip, source=clip, verify=False) is not None:
            out["kept"] += 1
            if report:
                report(f"{eng} {key[:12]} <- {clip}")
        else:
            skip("could not be copied")
    return out


def status() -> dict:
    """How many clips the cache keeps for each engine, and their size."""
    base = root()
    out = {"cache": str(base) if base else "off", "engines": {}}
    if base is None or not base.is_dir():
        return out
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        clips = list(folder.glob("*.mp4"))
        out["engines"][folder.name] = {"clips": len(clips), "mb": round(sum(c.stat().st_size for c in clips) / 1e6, 1)}
    return out
