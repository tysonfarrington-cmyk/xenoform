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
    """A to B morph: shot A guides frame 0, shot B guides the last frame.

    LTX 0.9.5 by default (about 9 s for 49 frames at 512x288 on a 3080 Ti),
    LTX-2.3 when the plan names that file. ``strength`` is the guide weight on
    both ends; 1.0 pins the first and last frames to the two shots.
    """
    values = plan.get("strength") or [1.0]
    strength = max(0.35, min(1.0, float(values[-1]) if values else 1.0))
    checkpoint = str(plan.get("checkpoint") or CHECKPOINT)
    title = "LTX-2.3" if "2.3" in checkpoint else "LTX 0.9.5"
    width = int(plan.get("width") or 512) // 32 * 32 or 512
    height = int(plan.get("height") or 288) // 32 * 32 or 288
    length = int(plan.get("length") or 49)
    length = max(9, (length - 1) // 8 * 8 + 1)
    fps = float(plan.get("fps") or 24.0)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}, "_meta": {"title": title}},
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "ltxv", "device": "cpu"},
            # On the CPU: T5 on the card took the 3080 Ti to 11.9 GB. ComfyUI caches the
            # encode, so a run that keeps one prompt pays for it once.
            "_meta": {"title": "Local text encoder"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": str(plan.get("prompt") or "the shot"), "clip": ["2", 0]},
            "_meta": {"title": "Only the nouns already in the shots"},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "text, watermark, flicker, cut, blurry", "clip": ["2", 0]},
            "_meta": {"title": "Negative"},
        },
        "5": {
            "class_type": "LTXVConditioning",
            "inputs": {"positive": ["3", 0], "negative": ["4", 0], "frame_rate": fps},
            "_meta": {"title": "Frame rate"},
        },
        "6": {"class_type": "LoadImage", "inputs": {"image": "shot-a.png"}, "_meta": {"title": "Shot A (first frame)"}},
        "7": {"class_type": "LoadImage", "inputs": {"image": "shot-b.png"}, "_meta": {"title": "Shot B (last frame)"}},
        "8": {"class_type": "LTXVPreprocess", "inputs": {"image": ["6", 0], "img_compression": 18}},
        "21": {"class_type": "LTXVPreprocess", "inputs": {"image": ["7", 0], "img_compression": 18}},
        "9": {
            "class_type": "EmptyLTXVLatentVideo",
            "inputs": {"width": width, "height": height, "length": length, "batch_size": 1},
            "_meta": {"title": "Latent"},
        },
        "10": {
            "class_type": "LTXVAddGuide",
            "inputs": {
                "positive": ["5", 0], "negative": ["5", 1], "vae": ["1", 2], "latent": ["9", 0],
                "image": ["8", 0], "frame_idx": 0, "strength": strength,
            },
            "_meta": {"title": "Guide A at frame 0"},
        },
        "22": {
            "class_type": "LTXVAddGuide",
            "inputs": {
                "positive": ["10", 0], "negative": ["10", 1], "vae": ["1", 2], "latent": ["10", 2],
                "image": ["21", 0], "frame_idx": -1, "strength": strength,
            },
            "_meta": {"title": "Guide B at the last frame"},
        },
        "11": {
            "class_type": "LTXVScheduler",
            "inputs": {"steps": int(plan.get("steps") or 20), "max_shift": 2.05, "base_shift": 0.95,
                       "stretch": True, "terminal": 0.1, "latent": ["22", 2]},
        },
        "12": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}, "_meta": {"title": f"Seed {SEED}"}},
        "20": {
            "class_type": "ModelSamplingLTXV",
            "inputs": {"model": ["1", 0], "max_shift": 2.05, "base_shift": 0.95, "latent": ["22", 2]},
        },
        "14": {
            "class_type": "CFGGuider",
            "inputs": {"model": ["20", 0], "positive": ["22", 0], "negative": ["22", 1], "cfg": 3.0},
        },
        "15": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {"noise": ["13", 0], "guider": ["14", 0], "sampler": ["12", 0],
                       "sigmas": ["11", 0], "latent_image": ["22", 2]},
            "_meta": {"title": "Sample"},
        },
        "16": {"class_type": "LTXVCropGuides", "inputs": {"positive": ["22", 0], "negative": ["22", 1], "latent": ["15", 0]}},
        # Tiled in time: a 73-frame plain decode pushed the card to 11.9 GB.
        "17": {
            "class_type": "VAEDecodeTiled",
            "inputs": {"samples": ["16", 2], "vae": ["1", 2], "tile_size": 512, "overlap": 64, "temporal_size": 32, "temporal_overlap": 8},
        },
        "18": {"class_type": "CreateVideo", "inputs": {"images": ["17", 0], "fps": fps}},
        "19": {
            "class_type": "SaveVideo",
            "inputs": {"video": ["18", 0], "filename_prefix": "xenoform/morph", "format": "auto", "codec": "auto"},
            "_meta": {"title": "Save morph"},
        },
    }
