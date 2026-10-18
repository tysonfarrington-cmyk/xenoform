"""LTX-2.5 local graphs. LTX-2.3 stays the fallback. Partner nodes stay out.

The three API graphs are open-weights ComfyUI graphs: Audio-to-Video,
a two-prompt multi-shot, and Layout-to-Render for a beat-landed morph.
Turbo never selects this stack.
"""

from __future__ import annotations

import os
from pathlib import Path

from xenoform.eligibility import ltx25_allowed, ltx25_licence
from xenoform.hardware import LARGE_CHECKPOINT

LTX25_CHECKPOINT = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"
LTX25_CLIP = "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"
LTX25_AUDIO_VAE = "ltx-2.5-audio-vae-bf16.safetensors"
LTX25_LAYOUT_LORA = "ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors"

GRAPHS = {
    "a2v": "workflows/ltx25_a2v_api.json",
    "multishot": "workflows/ltx25_multishot_api.json",
    "layout": "workflows/ltx25_layout_api.json",
}

_ASKED = {"ltx-25", "ltx2.5", "ltx25", "2.5"}


def wants_ltx25(cfg: dict | None) -> bool:
    comfy = (cfg or {}).get("comfy") or {}
    asked = str(comfy.get("video_model") or (cfg or {}).get("video_model") or "").lower().strip()
    return asked in _ASKED


def ltx25_file_present(cfg: dict | None) -> bool:
    """True when the distilled transformer is on disk, or the config says so."""
    flag = ((cfg or {}).get("comfy") or {}).get("ltx25_present")
    if flag is True or flag is False:
        return bool(flag)
    name = LTX25_CHECKPOINT
    roots = []
    env = os.environ.get("COMFYUI_DIR") or os.environ.get("COMFY_DIR") or ""
    if env:
        roots.append(Path(env) / "models" / "diffusion_models" / name)
    roots.append(Path.cwd() / "models" / "diffusion_models" / name)
    return any(path.is_file() for path in roots)


def core_choice(cfg: dict, quality: str, conditioning: str, checkpoint: str) -> tuple[str, str, str]:
    """Engine, checkpoint, and a short note. 2.5 falls back to 2.3."""
    from xenoform.restyle import _action_model

    if str(quality) == "turbo" or not wants_ltx25(cfg):
        engine, name = _action_model(cfg, quality, conditioning, checkpoint)
        return engine, name, ""
    if not ltx25_allowed():
        return "ltx-23", LARGE_CHECKPOINT, "LTX-2.5 did not pass the open-weights check. Staying on LTX-2.3."
    if not ltx25_file_present(cfg):
        return "ltx-23", LARGE_CHECKPOINT, "LTX-2.5 weights were not found. Staying on LTX-2.3."
    return "ltx-25", LTX25_CHECKPOINT, ""


def snap64(value: int) -> int:
    base = 64
    snapped = max(base, int(value) // base * base)
    return snapped


def graph_kind(job: dict, frames: list | None = None) -> str:
    """Layout on a drop, multi-shot when one chunk crosses a section, else audio-to-video."""
    start = int(job.get("start_frame") or 0)
    count = int(job.get("source_frames") or 0)
    labels: list[str] = []
    for frame in (frames or [])[start : start + count]:
        if not isinstance(frame, dict):
            continue
        label = str(frame.get("section") or "")
        if label and (not labels or labels[-1] != label):
            labels.append(label)
    if len(labels) > 1:
        return "multishot"
    section = str(job.get("section") or "")
    if section == "drop" or str(job.get("conditioning") or "") == "signature":
        return "layout"
    return "a2v"


def graph_path(kind: str) -> str:
    return GRAPHS.get(kind) or GRAPHS["a2v"]


def licence_summary() -> str:
    info = ltx25_licence()
    return (
        f"{info['model']} is local open weights under the {info['licence']} "
        f"dated {info['date']}. {info['revenue']} The desk graphs do not use an LTX partner node."
    )
