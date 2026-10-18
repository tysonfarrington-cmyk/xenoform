"""Segment the base video and restyle each chunk with ComfyUI LTX.

Live mode uses the official Comfy Python SDK (``comfy-sdk`` / ``comfy_sdk``)
against ``comfy-api-proxy`` in front of a local ComfyUI. ``comfy.base_url``
stays the ComfyUI health address (port 8188). ``comfy.proxy_url`` is what
``COMFY_BASE_URL`` is set to for the client (port 8189). Dry-run is the
default: it writes the chunk mp4s and a manifest of the exact ``set_input``
calls that live mode would make, and it does not import the SDK or open a
socket.

The shipped graph is ``workflows/ltx_v2v_api.json``. It is core ComfyUI nodes
only (no custom-node pack). ``LTXVImgToVideoInplace.strength`` is a preserve
control — 1 keeps the rendered form, lower values let LTX mutate it — and
Xenoform drives that from chunk energy. Swap ``comfy.workflow`` and
``comfy.nodes`` if you settle on a different LTX checkpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from xenoform.config import resolve_path
from xenoform.prompting import chunk_drive, prompt_for
from xenoform.segment import plan_chunks
from xenoform.video import read_frame_range, write_mp4

log = logging.getLogger("xenoform")

_WAN_NAMES = {"wan", "wan2.2", "wan22", "wan22-ti2v"}


def _is_ltx23(name: str) -> bool:
    folded = str(name or "").lower()
    return "2.3" in folded or "ltx-23" in folded or "22b" in folded


def _action_model(cfg: dict, quality: str, conditioning: str, checkpoint: str) -> tuple[str, str]:
    """Pick the generator for one chunk.

    LTX-2.3 is the core model for action shots on Draft and Final when that
    checkpoint is the one the tier selected. A morph restyle uses LTX-2.3 too
    when it is present: fp8 or int8 on 12 GB, the full file on 24 GB. Otherwise
    the morph stays on LTX 0.9.5, which is also the fast option.
    Wan 2.2 runs only when the config asks for it on a first-frame shot.
    Turbo always stays on 0.9.5. Turbo never loads LTX-2.3.
    """
    from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT

    if quality == "turbo":
        return "ltx-095", FAST_CHECKPOINT
    if conditioning == "signature":
        if _is_ltx23(checkpoint):
            return "ltx-23", checkpoint
        from xenoform.morph.plan import restyle_checkpoint

        tier = str((cfg.get("hardware") or {}).get("tier") or "")
        name, _width, _height = restyle_checkpoint(False, tier or None)
        if _is_ltx23(name):
            return "ltx-23", name
        return "ltx-095", FAST_CHECKPOINT
    asked = str((cfg.get("comfy") or {}).get("video_model") or cfg.get("video_model") or "").lower()
    if quality in {"draft", "final"} and conditioning == "first-frame" and asked in _WAN_NAMES:
        from xenoform.models_setup import wan_ready

        if wan_ready():
            name = checkpoint or FAST_CHECKPOINT
            if "2.3" in name or "22b" in name.lower():
                name = FAST_CHECKPOINT
            return "wan2.2-ti2v", name
    if "2.3" in checkpoint or "22b" in checkpoint.lower() or asked in {"ltx-23", "ltx2.3", "2.3"}:
        name = checkpoint if ("2.3" in checkpoint or "22b" in checkpoint.lower()) else LARGE_CHECKPOINT
        return "ltx-23", name
    return "ltx-095", checkpoint or FAST_CHECKPOINT


def build_jobs(features: dict, cfg: dict) -> list[dict[str, Any]]:
    segment = cfg["segment"]
    chunks = plan_chunks(
        features,
        target_seconds=float(segment["target_seconds"]),
        min_seconds=float(segment["min_seconds"]),
        max_seconds=float(segment["max_seconds"]),
    )
    prompts = cfg["prompts"]
    comfy = cfg["comfy"]
    negative = prompts.get("negative", "")
    jobs = []
    for chunk in chunks:
        drive = chunk_drive(features["frames"], chunk)
        start = int(chunk["start_frame"])
        window = features["frames"][start : start + 1]
        conditioning = str((window[0].get("conditioning") if window else "") or "")
        if conditioning == "first-frame":
            drive = dict(drive)
            drive["preserve_strength"] = 0.08
            drive["denoise"] = 0.92
        quality = str(cfg.get("quality") or "")
        from xenoform.ltx25 import LTX25_CLIP, core_choice, snap64

        engine, checkpoint_name, model_note = core_choice(
            cfg, quality, conditioning, str(comfy.get("checkpoint_name") or "")
        )
        width = int(comfy["width"])
        height = int(comfy["height"])
        clip_name = comfy["clip_name"]
        if engine == "ltx-25":
            width = snap64(width)
            height = snap64(height)
            clip_name = LTX25_CLIP
        section = chunk["section"]
        prompt = prompt_for(section, prompts)
        length = int(chunk["length"])
        if (length - 1) % 8 != 0:
            raise RuntimeError(f"Chunk length {length} is not 8*k+1")
        jobs.append(
            {
                **chunk,
                **drive,
                "prompt": prompt,
                "negative": negative,
                "width": width,
                "height": height,
                "steps": int(comfy["steps"]),
                "cfg": float(comfy["cfg"]),
                "sampler_name": comfy["sampler_name"],
                "seed": int(cfg["seed"]) + int(chunk["index"]) * 997,
                "checkpoint_name": checkpoint_name,
                "engine": engine,
                "model_note": model_note,
                "conditioning": conditioning,
                "clip_name": clip_name,
                "max_shift": float(comfy["max_shift"]),
                "base_shift": float(comfy["base_shift"]),
                "terminal": float(comfy["terminal"]),
                "stretch": bool(comfy["stretch"]),
                "fps": float(features["fps"]),
            }
        )
    return jobs


def _apply_inputs(wf, job: dict, nodes: dict, asset) -> dict[str, Any]:
    """Push one chunk into the API-format graph. Returns the input record."""
    record = {
        "load_video.file": "<asset>",
        "positive_prompt.text": job["prompt"],
        "negative_prompt.text": job["negative"],
        "preserve_strength.strength": job["preserve_strength"],
        "seed.noise_seed": job["seed"],
        "latent.width": job["width"],
        "latent.height": job["height"],
        "latent.length": job["length"],
        "steps.steps": job["steps"],
        "cfg.cfg": job["cfg"],
        "checkpoint.ckpt_name": job["checkpoint_name"],
        "clip.clip_name": job["clip_name"],
        "frame_rate.frame_rate": job["fps"],
        "fps.fps": job["fps"],
        "preprocess.img_compression": int(job["img_compression"]),
        "sampler.sampler_name": job["sampler_name"],
    }
    wf.set_input(nodes["load_video"], "file", asset)
    wf.set_input(nodes["positive_prompt"], "text", job["prompt"])
    wf.set_input(nodes["negative_prompt"], "text", job["negative"])
    wf.set_input(nodes["preserve_strength"], "strength", job["preserve_strength"])
    wf.set_input(nodes["seed"], "noise_seed", int(job["seed"]))
    wf.set_input(nodes["latent"], "width", int(job["width"]))
    wf.set_input(nodes["latent"], "height", int(job["height"]))
    wf.set_input(nodes["latent"], "length", int(job["length"]))
    wf.set_input(nodes["steps"], "steps", int(job["steps"]))
    wf.set_input(nodes["steps"], "max_shift", float(job["max_shift"]))
    wf.set_input(nodes["steps"], "base_shift", float(job["base_shift"]))
    wf.set_input(nodes["steps"], "terminal", float(job["terminal"]))
    wf.set_input(nodes["steps"], "stretch", bool(job["stretch"]))
    wf.set_input(nodes["cfg"], "cfg", float(job["cfg"]))
    wf.set_input(nodes["checkpoint"], "ckpt_name", job["checkpoint_name"])
    wf.set_input(nodes["clip"], "clip_name", job["clip_name"])
    wf.set_input(nodes["frame_rate"], "frame_rate", float(job["fps"]))
    wf.set_input(nodes["fps"], "fps", float(job["fps"]))
    wf.set_input(nodes["preprocess"], "img_compression", int(job["img_compression"]))
    if "sampler" in nodes:
        wf.set_input(nodes["sampler"], "sampler_name", job["sampler_name"])
    if "model_sampling" in nodes:
        wf.set_input(nodes["model_sampling"], "max_shift", float(job["max_shift"]))
        wf.set_input(nodes["model_sampling"], "base_shift", float(job["base_shift"]))
    if "prompt_b" in nodes:
        text = str(job.get("prompt_b") or job["prompt"])
        wf.set_input(nodes["prompt_b"], "text", text)
        record["prompt_b.text"] = text
    return record


def _chunk_file(video_path: Path, job: dict, dest: Path, fps: float) -> None:
    frames = read_frame_range(video_path, int(job["start_frame"]), int(job["source_frames"]))
    if frames.shape[0] < job["source_frames"]:
        raise RuntimeError(
            f"Base video ended early at frame {job['start_frame']} "
            f"(got {frames.shape[0]}, wanted {job['source_frames']})"
        )
    sequence = [frames[i] for i in range(frames.shape[0])]
    if job["pad"]:
        sequence.extend([sequence[-1]] * int(job["pad"]))
    write_mp4(dest, sequence, fps, crf=18)


def _state_path(out_dir: Path) -> Path:
    return out_dir / "comfy_state.json"


def _load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _job_identity(job: dict, chunk_path: Path) -> str:
    digest = hashlib.sha256(chunk_path.read_bytes()).hexdigest()[:16]
    raw = f"{job['index']}:{digest}:{job['prompt']}:{job['preserve_strength']}:{job['seed']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def sdk_base_url(cfg: dict) -> str:
    """URL the SDK submits to. Health pings stay on ``comfy.base_url``.

    The local default is the proxy on port 8189. Cloud is only an empty
    proxy, an empty ComfyUI URL, and ``send_api_key``.
    """
    comfy = (cfg or {}).get("comfy") or {}
    if "proxy_url" in comfy:
        proxy = str(comfy.get("proxy_url") or "").strip()
    else:
        proxy = "http://127.0.0.1:8189"
    base = str(comfy.get("base_url") or "").strip()
    if bool(comfy.get("send_api_key")) and not base and not proxy:
        return ""
    return proxy or "http://127.0.0.1:8189"


def _make_client(cfg: dict):
    """Construct ``comfy_sdk.Comfy`` the way the current SDK documents it.

    The submit URL is ``COMFY_BASE_URL``, read at construction, and it is the
    proxy (``sdk_base_url``), not the ComfyUI health address. Cloud is an
    empty URL plus ``send_api_key``. A local proxy never inherits
    ``COMFY_API_KEY``. The key is never logged.
    """
    from comfy_sdk import Comfy, MissingApiKey

    comfy = cfg["comfy"]
    base_url = sdk_base_url(cfg)
    send_key = bool(comfy.get("send_api_key")) and not base_url
    key_env = comfy.get("api_key_env") or "COMFY_API_KEY"
    saved_base = os.environ.get("COMFY_BASE_URL")
    saved_key = os.environ.get("COMFY_API_KEY")
    try:
        if base_url:
            os.environ["COMFY_BASE_URL"] = base_url
        else:
            # Empty URL is Comfy Cloud, the SDK default.
            os.environ.pop("COMFY_BASE_URL", None)
        if send_key:
            key = os.environ.get(key_env) or saved_key
            if key:
                os.environ["COMFY_API_KEY"] = key
        else:
            # A local proxy must not inherit a cloud key that happens to be set.
            os.environ.pop("COMFY_API_KEY", None)
        # timeout=None: a video job's SSE stream and the chunk upload must
        # outlive the 30s default. Polling in result() is still authoritative.
        client = Comfy(client_info="xenoform", timeout=None)
    except MissingApiKey as exc:
        raise RuntimeError(
            "Comfy Cloud needs an API key. Set COMFY_API_KEY, or point comfy.proxy_url "
            "at a local comfy-api-proxy and leave send_api_key false. "
            f"SDK said: {exc}"
        ) from exc
    finally:
        if saved_base is None:
            os.environ.pop("COMFY_BASE_URL", None)
        else:
            os.environ["COMFY_BASE_URL"] = saved_base
        if saved_key is None:
            os.environ.pop("COMFY_API_KEY", None)
        else:
            os.environ["COMFY_API_KEY"] = saved_key
    return client


def _assets_unsupported(exc: BaseException) -> bool:
    """True when the server has no ``/api/v2/assets`` route.

    Stock ComfyUI answers that cloud route with 405. ``comfy-api-proxy`` in
    front of it serves the route, so this stays false on the proxy path.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        status = getattr(current, "http_status", None)
        response = getattr(current, "response", None)
        if status == 405 or getattr(response, "status_code", None) == 405:
            return True
        text = str(current).lower()
        if "405" in text and ("asset" in text or "method not allowed" in text or "/api/v2" in text):
            return True
        current = current.__cause__ or current.__context__
    return False


def _put_input(graph: dict, nodes: dict, key: str, field: str, value: Any) -> None:
    if key not in nodes:
        return
    node = graph.get(str(nodes[key]))
    if not isinstance(node, dict):
        return
    node.setdefault("inputs", {})[field] = value


def _stamp_graph(workflow_path: Path, job: dict, nodes: dict, filename: str) -> dict:
    """API-format graph with a plain filename on LoadVideo. No asset handle."""
    graph = json.loads(workflow_path.read_text(encoding="utf-8"))
    _put_input(graph, nodes, "load_video", "file", filename)
    _put_input(graph, nodes, "positive_prompt", "text", job["prompt"])
    _put_input(graph, nodes, "negative_prompt", "text", job["negative"])
    _put_input(graph, nodes, "preserve_strength", "strength", job["preserve_strength"])
    _put_input(graph, nodes, "seed", "noise_seed", int(job["seed"]))
    _put_input(graph, nodes, "latent", "width", int(job["width"]))
    _put_input(graph, nodes, "latent", "height", int(job["height"]))
    _put_input(graph, nodes, "latent", "length", int(job["length"]))
    _put_input(graph, nodes, "steps", "steps", int(job["steps"]))
    _put_input(graph, nodes, "steps", "max_shift", float(job["max_shift"]))
    _put_input(graph, nodes, "steps", "base_shift", float(job["base_shift"]))
    _put_input(graph, nodes, "steps", "terminal", float(job["terminal"]))
    _put_input(graph, nodes, "steps", "stretch", bool(job["stretch"]))
    _put_input(graph, nodes, "cfg", "cfg", float(job["cfg"]))
    _put_input(graph, nodes, "checkpoint", "ckpt_name", job["checkpoint_name"])
    _put_input(graph, nodes, "clip", "clip_name", job["clip_name"])
    _put_input(graph, nodes, "frame_rate", "frame_rate", float(job["fps"]))
    _put_input(graph, nodes, "fps", "fps", float(job["fps"]))
    _put_input(graph, nodes, "preprocess", "img_compression", int(job["img_compression"]))
    _put_input(graph, nodes, "sampler", "sampler_name", job["sampler_name"])
    _put_input(graph, nodes, "model_sampling", "max_shift", float(job["max_shift"]))
    _put_input(graph, nodes, "model_sampling", "base_shift", float(job["base_shift"]))
    if "prompt_b" in nodes:
        _put_input(graph, nodes, "prompt_b", "text", str(job.get("prompt_b") or job["prompt"]))
    return graph


def _stock_base(cfg: dict) -> str:
    base = str((cfg.get("comfy") or {}).get("base_url") or "http://127.0.0.1:8188").strip()
    return base.rstrip("/") or "http://127.0.0.1:8188"


def _pick_media(outputs: dict, save_id: str) -> dict | None:
    ordered: list[dict] = []
    primary = outputs.get(str(save_id))
    if isinstance(primary, dict):
        ordered.append(primary)
    for key, value in outputs.items():
        if str(key) != str(save_id) and isinstance(value, dict):
            ordered.append(value)
    for node in ordered:
        for key in ("videos", "gifs", "images", "animated"):
            rows = node.get(key) or []
            if isinstance(rows, list) and rows and isinstance(rows[0], dict) and rows[0].get("filename"):
                return rows[0]
    return None


def _run_stock(
    cfg: dict,
    workflow_path: Path,
    chunk_path: Path,
    dest: Path,
    job: dict,
    nodes: dict,
    *,
    http: Any = None,
    sleep: Any = None,
    attempts: int = 600,
) -> str:
    """Stock ComfyUI: ``POST /upload/image`` then ``POST /prompt``. No API key."""
    import httpx

    base = _stock_base(cfg)
    own = http is None
    client = http or httpx.Client(timeout=httpx.Timeout(120.0, read=None))
    pause = sleep or time.sleep
    try:
        with chunk_path.open("rb") as handle:
            uploaded = client.post(
                f"{base}/upload/image",
                files={"image": (chunk_path.name, handle, "video/mp4")},
                data={"type": "input", "overwrite": "true"},
            )
        uploaded.raise_for_status()
        body = uploaded.json()
        name = Path(str(body.get("name") or chunk_path.name)).name
        sub = str(body.get("subfolder") or "").replace("\\", "/").strip("/")
        if any(part == ".." for part in sub.split("/")):
            sub = ""
        filename = f"{sub}/{name}" if sub else name
        graph = _stamp_graph(workflow_path, job, nodes, filename)
        posted = client.post(
            f"{base}/prompt",
            json={"prompt": graph, "client_id": "xenoform"},
        )
        posted.raise_for_status()
        queued = posted.json()
        errors = queued.get("node_errors") or {}
        if errors:
            raise RuntimeError(f"ComfyUI rejected the prompt for chunk {job['index']}: {errors}")
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return a prompt id for chunk {job['index']}")
        save_id = str(nodes["save_video"])
        media = None
        for _ in range(max(1, int(attempts))):
            history = client.get(f"{base}/history/{prompt_id}")
            history.raise_for_status()
            entry = (history.json() or {}).get(prompt_id) or {}
            status = entry.get("status") or {}
            if str(status.get("status_str") or "") == "error":
                raise RuntimeError(f"ComfyUI prompt {prompt_id} failed for chunk {job['index']}")
            media = _pick_media(entry.get("outputs") or {}, save_id)
            if media and (status.get("completed") or entry.get("outputs")):
                break
            pause(0.5)
        else:
            raise RuntimeError(f"ComfyUI prompt {prompt_id} did not finish for chunk {job['index']}")
        if not media:
            raise RuntimeError(f"ComfyUI prompt {prompt_id} finished with no video for chunk {job['index']}")
        viewed = client.get(
            f"{base}/view",
            params={
                "filename": media.get("filename"),
                "subfolder": media.get("subfolder") or "",
                "type": media.get("type") or "output",
            },
        )
        viewed.raise_for_status()
        dest.write_bytes(viewed.content)
        job["submit_path"] = "stock"
        log.info("chunk %s submitted to stock ComfyUI as prompt %s", job["index"], prompt_id)
        return prompt_id
    finally:
        if own:
            client.close()


def _run_live(
    client,
    cfg: dict,
    workflow_path: Path,
    chunk_path: Path,
    dest: Path,
    job: dict,
    nodes: dict | None = None,
) -> str:
    from comfy_sdk import IdempotencyKeyReuse, JobFailed, Progress, StatusChange

    nodes = nodes or cfg["comfy"]["nodes"]
    wf = client.workflows.from_file(str(workflow_path))
    asset = client.assets.from_file(str(chunk_path))
    _apply_inputs(wf, job, nodes, asset)

    state_file = _state_path(dest.parent)
    state = _load_state(state_file)
    identity = _job_identity(job, chunk_path)
    entry = state.get(identity, {})
    idem = entry.get("key") or str(uuid.uuid4())
    entry["key"] = idem
    state[identity] = entry
    _save_state(state_file, state)

    submit_kwargs: dict[str, Any] = {"idempotency_key": idem}
    from xenoform.eligibility import partner_key

    # Partner key only when Add-ons is on. The open-weights path never sends it.
    key = partner_key(cfg)
    if key:
        submit_kwargs["api_key"] = key

    try:
        try:
            running = client.submit(wf, **submit_kwargs)
        except IdempotencyKeyReuse:
            job_id = entry.get("job_id")
            if not job_id:
                raise RuntimeError(
                    "Comfy rejected the idempotency key and no job id was stored for "
                    f"chunk {job['index']}. Not resubmitting. Delete {state_file} to force a new key."
                ) from None
            log.info("chunk %s reusing job %s after idempotency-key reuse", job["index"], job_id)
            running = client.jobs.get(job_id)
        else:
            entry["job_id"] = running.id
            _save_state(state_file, state)
            log.info("chunk %s submitted as job %s", job["index"], running.id)
            try:
                for event in running.events():
                    if isinstance(event, Progress):
                        message = event.message or ""
                        log.info("chunk %s  %3.0f%%  %s", job["index"], event.value * 100.0, message)
                    elif isinstance(event, StatusChange) and event.status == "succeeded":
                        break
            except Exception as exc:  # stream is not the source of truth
                log.info("chunk %s event stream closed (%s); polling the job", job["index"], exc)

        try:
            result = running.result()
        except JobFailed as exc:
            raise RuntimeError(f"Comfy job failed for chunk {job['index']}: {exc}") from exc

        save_id = nodes["save_video"]
        outputs = list(result.get_outputs(save_id))
        if not outputs:
            outputs = list(result.outputs)
        if not outputs:
            raise RuntimeError(f"Job {result.id} finished with no outputs at node {save_id}")
        chosen = next((item for item in outputs if getattr(item, "type", None) == "video"), outputs[0])
        chosen.to_file(str(dest))
        entry["status"] = "succeeded"
        entry["output"] = str(dest)
        _save_state(state_file, state)
        job["submit_path"] = "sdk"
        return str(result.id)
    except Exception as exc:
        if not _assets_unsupported(exc):
            raise
        log.info(
            "chunk %s v2 assets returned 405 (%s); using /upload/image and /prompt",
            job["index"],
            exc,
        )
        return _run_stock(cfg, workflow_path, chunk_path, dest, job, nodes)


def _chunk_workflow(cfg: dict, job: dict, features: dict) -> Path:
    """Default graph, or the LTX-2.5 graph this chunk asked for."""
    if job.get("engine") != "ltx-25":
        return resolve_path(cfg["comfy"]["workflow"], cfg)
    from xenoform.ltx25 import graph_kind, graph_path

    kind = graph_kind(job, features.get("frames"))
    job["graph"] = kind
    if kind == "multishot":
        start = int(job.get("start_frame") or 0)
        count = int(job.get("source_frames") or 0)
        labels: list[str] = []
        for frame in (features.get("frames") or [])[start : start + count]:
            label = str(frame.get("section") or "")
            if label and (not labels or labels[-1] != label):
                labels.append(label)
        second = labels[1] if len(labels) > 1 else str(job.get("section") or "")
        job["prompt_b"] = prompt_for(second, cfg.get("prompts") or {})
    return resolve_path(graph_path(kind), cfg)


def _nodes_for(cfg: dict, job: dict) -> dict:
    nodes = dict(cfg["comfy"]["nodes"])
    if job.get("graph") == "multishot":
        nodes["prompt_b"] = "36"
    return nodes


def restyle(
    features: dict,
    video_path: str | Path,
    out_dir: str | Path,
    cfg: dict,
    mode: str | None = None,
) -> dict[str, Any]:
    video_path = Path(video_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = mode or cfg["comfy"]["mode"]
    if mode not in {"dry-run", "live"}:
        raise ValueError(f"Unknown comfy mode {mode!r}. Use 'dry-run' or 'live'.")

    workflow_path = resolve_path(cfg["comfy"]["workflow"], cfg)
    if not workflow_path.exists():
        raise FileNotFoundError(f"Workflow JSON not found: {workflow_path}")
    _validate_workflow(workflow_path, cfg["comfy"])

    jobs = build_jobs(features, cfg)
    resident = bool(cfg.get("comfy", {}).get("resident"))
    if resident:
        # One checkpoint runs straight through so the weights stay loaded.
        jobs = sorted(jobs, key=lambda job: (str(job.get("checkpoint_name") or ""), int(job["index"])))
    fps = float(features["fps"])
    client = None
    if mode == "live":
        client = _make_client(cfg)

    manifest_jobs = []
    for job in jobs:
        chunk_path = out_dir / f"chunk_{job['index']:03d}_base.mp4"
        styled_path = out_dir / f"chunk_{job['index']:03d}.mp4"
        log.info(
            "chunk %s  %s  frames %s+%s pad  preserve %.2f  denoise %.2f",
            job["index"],
            job["section"],
            job["source_frames"],
            job["pad"],
            job["preserve_strength"],
            job["denoise"],
        )
        _chunk_file(video_path, job, chunk_path, fps)
        chunk_workflow = _chunk_workflow(cfg, job, features)
        if not chunk_workflow.exists():
            raise FileNotFoundError(f"Workflow JSON not found: {chunk_workflow}")
        check = dict(cfg["comfy"])
        check["width"] = int(job["width"])
        check["height"] = int(job["height"])
        _validate_workflow(chunk_workflow, check, multiple=64 if job.get("engine") == "ltx-25" else 32)
        nodes = _nodes_for(cfg, job)
        record = {
            "index": job["index"],
            "section": job["section"],
            "engine": job.get("engine") or "",
            "workflow": str(chunk_workflow),
            "graph": job.get("graph") or "",
            "start_frame": job["start_frame"],
            "source_frames": job["source_frames"],
            "length": job["length"],
            "pad": job["pad"],
            "prompt": job["prompt"],
            "negative": job["negative"],
            "denoise": job["denoise"],
            "preserve_strength": job["preserve_strength"],
            "img_compression": job["img_compression"],
            "seed": job["seed"],
            "width": job["width"],
            "height": job["height"],
            "steps": job["steps"],
            "cfg": job["cfg"],
            "base": str(chunk_path),
            "output": str(styled_path if mode == "live" else chunk_path),
            "inputs": {
                f"{nodes['positive_prompt']}.text": job["prompt"],
                f"{nodes['negative_prompt']}.text": job["negative"],
                f"{nodes['preserve_strength']}.strength": job["preserve_strength"],
                f"{nodes['seed']}.noise_seed": job["seed"],
                f"{nodes['latent']}.width": job["width"],
                f"{nodes['latent']}.height": job["height"],
                f"{nodes['latent']}.length": job["length"],
                f"{nodes['steps']}.steps": job["steps"],
                f"{nodes['cfg']}.cfg": job["cfg"],
                f"{nodes['checkpoint']}.ckpt_name": job["checkpoint_name"],
                f"{nodes['clip']}.clip_name": job["clip_name"],
                f"{nodes['frame_rate']}.frame_rate": job["fps"],
                f"{nodes['fps']}.fps": job["fps"],
                f"{nodes['preprocess']}.img_compression": job["img_compression"],
            },
        }
        if "prompt_b" in nodes:
            record["inputs"][f"{nodes['prompt_b']}.text"] = job.get("prompt_b") or job["prompt"]
        if mode == "dry-run":
            # Passthrough: assemble still has a real picture, and the manifest
            # records the graph edits live mode would submit.
            record["passthrough"] = True
            styled_path = chunk_path
        else:
            assert client is not None
            record["comfy_job_id"] = _run_live(
                client, cfg, chunk_workflow, chunk_path, styled_path, job, nodes
            )
            record["submit"] = job.get("submit_path") or "sdk"
            record["output"] = str(styled_path)
        manifest_jobs.append(record)

    manifest = {
        "mode": mode,
        "workflow": str(workflow_path),
        "base_video": str(video_path),
        "fps": fps,
        "note": (
            "dry-run did not call ComfyUI; chunk outputs are the base-form slices"
            if mode == "dry-run"
            else (
                "chunks were submitted to stock ComfyUI via /upload/image and /prompt"
                if any(chunk.get("submit") == "stock" for chunk in manifest_jobs)
                else "chunks were submitted with comfy_sdk.Comfy through comfy-api-proxy"
            )
        ),
        "chunks": manifest_jobs,
    }
    fallback = next((str(job.get("model_note") or "") for job in jobs if job.get("model_note")), "")
    if fallback:
        manifest["note"] = manifest["note"] + " " + fallback
    if resident:
        manifest["resident"] = True
        manifest["llm"] = "unloaded"
        manifest["checkpoints"] = sorted({str(job.get("checkpoint_name") or "") for job in jobs})
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("wrote %s (%s)", manifest_path, mode)
    return manifest


def _validate_workflow(path: Path, comfy: dict, multiple: int = 32) -> None:
    graph = json.loads(path.read_text(encoding="utf-8"))
    width = int(comfy["width"])
    height = int(comfy["height"])
    if width % multiple or height % multiple:
        raise ValueError(
            f"LTX width and height must be multiples of {multiple} (got {width}x{height})"
        )
    missing = [name for name, node_id in comfy["nodes"].items() if str(node_id) not in graph]
    if missing:
        raise ValueError(
            f"Workflow {path.name} has no node for config keys: {', '.join(missing)}. "
            "Update comfy.nodes to the ids in this workflow."
        )
    for node_id, node in graph.items():
        if not isinstance(node, dict) or "class_type" not in node:
            raise ValueError(f"Node {node_id} is not an API-format node")
        for value in node.get("inputs", {}).values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                if value[0] not in graph:
                    raise ValueError(f"Node {node_id} links to missing node {value[0]}")
