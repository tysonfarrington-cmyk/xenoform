"""Comfy graphs for a morph. The key field stays empty.

A restyle loads LTX-2.3 when the plan names that file, and LTX 0.9.5 for the
fast option. Turbo never loads LTX-2.3.
"""

from __future__ import annotations

from xenoform.hardware import FAST_CHECKPOINT

CHECKPOINT = FAST_CHECKPOINT
SEED = 2727


def graph(plan: dict) -> dict:
    method = str(plan.get("method") or "")
    if method in ("keyframe-blend", "cross-clip"):
        return _mix(plan)
    return _ramp(plan)


def _mix(plan: dict) -> dict:
    """Mix two existing frames. No sampler, so nothing new is drawn."""
    return {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": "shot-a.png"},
            "_meta": {"title": "Shot A last frame"},
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": "shot-b.png"},
            "_meta": {"title": "Shot B first frame"},
        },
        "3": {
            "class_type": "ImageBlend",
            "inputs": {"image1": ["1", 0], "image2": ["2", 0], "blend_factor": 0.5},
            "_meta": {"title": "Frame mix"},
        },
        "4": {
            "class_type": "SaveImage",
            "inputs": {"images": ["3", 0], "filename_prefix": "xenoform/morph"},
            "_meta": {"title": "Save mix"},
        },
    }


def _ramp(plan: dict) -> dict:
    """Low-strength restyle. LTX-2.3 when the plan asks for it, else LTX 0.9.5."""
    strength = 0.35
    values = plan.get("strength") or [0.35]
    if values:
        strength = min(0.35, float(values[-1]))
    checkpoint = str(plan.get("checkpoint") or CHECKPOINT)
    title = "LTX-2.3" if "2.3" in checkpoint else "LTX 0.9.5"
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
            "_meta": {"title": title},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "ltxv"},
            "_meta": {"title": "Local text encoder"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": str(plan.get("prompt") or "the shot"), "clip": ["2", 0]},
            "_meta": {"title": "Only the nouns already in the shots"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "text, watermark, flicker", "clip": ["2", 0]},
            "_meta": {"title": "Negative"},
        },
        "5": {
            "class_type": "LTXVConditioning",
            "inputs": {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": 24.0},
            "_meta": {"title": "Frame rate"},
        },
        "6": {
            "class_type": "LoadImage",
            "inputs": {"image": "shot-a.png"},
            "_meta": {"title": "Guide frame"},
        },
        "9": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {
                "width": int(plan.get("width") or 384),
                "height": int(plan.get("height") or 224),
                "length": 17,
                "batch_size": 1,
            },
            "_meta": {"title": "Latent"},
        },
        "10": {
            "class_type": "LTXVImgToVideoInplace",
            "inputs": {
                "vae": ["1", 2],
                "image": ["6", 0],
                "latent": ["9", 0],
                "strength": strength,
                "bypass": False,
            },
            "_meta": {"title": "Keep the source frame"},
        },
        "13": {
            "class_type": "RandomNoise",
            "inputs": {"noise_seed": SEED},
            "_meta": {"title": "Seed 2727"},
        },
        "15": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["13", 0],
                "guider": ["5", 0],
                "sampler": ["13", 0],
                "sigmas": ["10", 0],
                "latent_image": ["10", 0],
            },
            "_meta": {"title": "Sample"},
        },
    }
