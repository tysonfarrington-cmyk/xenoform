"""VRAM tiers. A GPU that runs out of memory drops a tier and retries."""

from __future__ import annotations

import shutil
import subprocess
from copy import deepcopy
from typing import Any, Callable

from xenoform.errors import PlainError, is_oom

# Resolution, steps, and offload for a live restyle. CPU leaves the desk's own sizes.
# Turbo is 384×224 (multiples of 32) at 4 steps on LTX 0.9.5. Never LTX-2.3.
_TURBO = {
    "8gb": {"width": 384, "height": 224, "steps": 4, "max_steps": 8, "fps": 12, "offload": True},
    "12gb": {"width": 384, "height": 224, "steps": 4, "max_steps": 8, "fps": 12, "offload": True},
    "24gb": {"width": 384, "height": 224, "steps": 4, "max_steps": 8, "fps": 12, "offload": False},
}
_DRAFT = {
    "8gb": {"width": 512, "height": 288, "steps": 8, "max_steps": 24, "fps": 12, "offload": True},
    "12gb": {"width": 512, "height": 288, "steps": 12, "max_steps": 28, "fps": 12, "offload": True},
    "24gb": {"width": 640, "height": 360, "steps": 20, "max_steps": 32, "fps": 12, "offload": False},
}
_FINAL = {
    "8gb": {"width": 512, "height": 288, "steps": 12, "max_steps": 28, "fps": 12, "offload": True},
    "12gb": {"width": 640, "height": 360, "steps": 20, "max_steps": 40, "fps": 24, "offload": True},
    "24gb": {"width": 768, "height": 432, "steps": 30, "max_steps": 48, "fps": 24, "offload": False},
}

TIERS: dict[str, dict[str, Any]] = {
    "cpu": {"id": "cpu", "label": "CPU", "gb": None, "clamp": False, "detail": "No GPU was found. The draft still renders on the CPU."},
    "8gb": {"id": "8gb", "label": "8 GB", "gb": 8, "clamp": True, "detail": "8 GB preset: 512×288, LTX 0.9.5, weights offloaded. LTX-2.3 needs a larger card."},
    "12gb": {"id": "12gb", "label": "12 GB", "gb": 12, "clamp": True, "detail": "12 GB preset: Turbo at 384×224 in 4 steps on LTX 0.9.5. Draft and Final use LTX-2.3 when an fp8 or int8 file is present, about 210 seconds a 704×384 shot. Otherwise they stay on LTX 0.9.5. Turbo never loads LTX-2.3."},
    "24gb": {"id": "24gb", "label": "24 GB+", "gb": 24, "clamp": True, "detail": "24 GB preset: Draft and Final action shots use LTX-2.3, the core model, when that file is installed. Morph restyles use it too. LTX 0.9.5 is the fast morph. Turbo stays on LTX 0.9.5."},
}

_LADDER = ("24gb", "12gb", "8gb")
FAST_CHECKPOINT = "ltx-video-2b-v0.9.5.safetensors"
LARGE_CHECKPOINT = "ltx-2.3-22b-distilled.safetensors"


def detect_vram_gb() -> float | None:
    """Total GPU memory in gigabytes, or None when this machine has no CUDA device."""
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.get_device_properties(0).total_memory) / (1024**3)
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        )
        line = out.strip().splitlines()[0]
        return float(line.split()[0]) / 1024.0
    except Exception:
        return None


def tier_for_gb(gb: float | None) -> dict[str, Any]:
    if gb is None:
        return dict(TIERS["cpu"])
    if gb >= 20:
        found = dict(TIERS["24gb"])
    elif gb >= 11:
        found = dict(TIERS["12gb"])
    else:
        found = dict(TIERS["8gb"])
    found["gb"] = round(gb, 1)
    return found


def detect_tier() -> dict[str, Any]:
    return tier_for_gb(detect_vram_gb())


def resolve_tier(tier_id: str | None) -> dict[str, Any]:
    if tier_id and tier_id in TIERS:
        return dict(TIERS[tier_id])
    return detect_tier()


def drop_ladder(tier_id: str) -> list[str]:
    if tier_id not in _LADDER:
        return [tier_id or "cpu"]
    start = _LADDER.index(tier_id)
    return list(_LADDER[start:])


def apply_tier(cfg: dict, tier: dict, *, quality: str = "draft") -> dict:
    """Stamp the tier onto a config. CPU keeps the sizes the desk already chose."""
    out = deepcopy(cfg)
    chosen = dict(tier)
    out["hardware"] = {
        "tier": chosen.get("id") or "cpu",
        "label": chosen.get("label") or "CPU",
        "vram_gb": chosen.get("gb"),
        "offload": False,
    }
    if not chosen.get("clamp"):
        return out
    if quality == "final":
        table = _FINAL
    elif quality == "turbo":
        table = _TURBO
    else:
        table = _DRAFT
    preset = table.get(chosen["id"]) or table["8gb"]
    out["fps"] = int(preset["fps"])
    out["render"]["width"] = int(preset["width"])
    out["render"]["height"] = int(preset["height"])
    out["render"]["max_steps"] = int(preset["max_steps"])
    out["render"]["backend"] = "cpu"
    out["comfy"]["width"] = int(preset["width"])
    out["comfy"]["height"] = int(preset["height"])
    out["comfy"]["steps"] = int(preset["steps"])
    out["comfy"]["offload"] = bool(preset["offload"])
    out["hardware"]["offload"] = bool(preset["offload"])
    asked = str(out["comfy"].get("video_model") or "ltx").lower()
    wants_wan = asked in {"wan", "wan2.2", "wan22", "wan22-ti2v"}
    wants_25 = asked in {"ltx-25", "ltx2.5", "ltx25", "2.5"}
    checkpoint = FAST_CHECKPOINT
    video_model = "ltx-095"
    if quality != "turbo" and wants_25:
        video_model = "ltx-25"
    elif quality != "turbo" and wants_wan:
        video_model = "wan"
    elif quality != "turbo":
        large = _ltx23_for(str(chosen.get("id") or ""))
        if large:
            checkpoint = large
            video_model = "ltx-23"
            if chosen["id"] == "12gb":
                out["render"]["width"] = 704
                out["render"]["height"] = 384
                out["comfy"]["width"] = 704
                out["comfy"]["height"] = 384
    out["comfy"]["checkpoint_name"] = checkpoint
    out["comfy"]["video_model"] = video_model
    return out


def _large_model_installed() -> bool:
    try:
        from xenoform.models_setup import model_present

        return model_present("ltx-23")
    except Exception:
        return False


def _ltx23_for(tier_id: str) -> str:
    """The LTX-2.3 filename for this card, or empty when that card should stay on 0.9.5.

    24 GB uses the file the user picked, or the canonical weights. 12 GB uses an
    fp8 or int8 file only. Turbo never calls this.
    """
    try:
        from xenoform.models_setup import chosen_filename, model_present, quantised_file
    except Exception:
        return ""
    if tier_id == "24gb" and (_large_model_installed() or model_present("ltx-23")):
        return chosen_filename("ltx-23") or LARGE_CHECKPOINT
    if tier_id == "12gb":
        return quantised_file("ltx-23")
    return ""


def run_resilient(fn: Callable[[str], Any], tier: dict | None = None) -> tuple[Any, str, str]:
    """Call fn(tier_id). On an out-of-memory error, drop a tier and try again.

    The returned note is empty when the first tier succeeded. Otherwise it is
    the sentence the desk should show.
    """
    start = tier or detect_tier()
    ladder = drop_ladder(str(start.get("id") or "cpu"))
    notes: list[str] = []
    last: BaseException | None = None
    for tier_id in ladder:
        try:
            return fn(tier_id), tier_id, " ".join(notes)
        except Exception as exc:
            last = exc
            if not is_oom(exc):
                raise
            label = TIERS.get(tier_id, {}).get("label", tier_id)
            if tier_id == ladder[-1]:
                raise PlainError(
                    f"The GPU ran out of memory on the {label} preset, which is the smallest. "
                    "Close other programs and run the draft again."
                ) from exc
            notes.append(f"The GPU ran out of memory on the {label} preset. Xenoform dropped a tier and tried again.")
    raise PlainError("The cut did not start.") from last


def disk_free(path) -> int:
    target = path
    while not target.exists():
        parent = target.parent
        if parent == target:
            break
        target = parent
    return int(shutil.disk_usage(target).free)
