"""Load and merge the Xenoform JSON config."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

# Fallbacks used when a key is omitted. configs/example.json is the documented config.
DEFAULTS: dict[str, Any] = {
    "fps": 12,
    "sr": 44100,
    "seed": 7,
    "audio": {
        "duration": 12.0,
        "bpm": 120,
    },
    "analyze": {
        "onset_tau": 0.085,
        "beat_tau": 0.05,
        "section_min_seconds": 1.4,
    },
    "render": {
        "backend": "cpu",
        "width": 480,
        "height": 270,
        "max_steps": 40,
        "crf": 20,
        "write_png": False,
        "write_depth": False,
        "write_mask": False,
    },
    "segment": {
        "target_seconds": 4.0,
        "min_seconds": 2.8,
        "max_seconds": 5.2,
    },
    "prompts": {
        "calm": (
            "Macro cinematic shot of one liquid alien-biotech organism in a black studio. "
            "Glossy liquid chrome fused with wet translucent flesh, calm viscous surface, "
            "slow continuous morph, soft specular highlights, faint internal filaments, "
            "physically based reflections, no text, no logos, no people."
        ),
        "build": (
            "Macro cinematic shot of a liquid chrome biotech organism swelling before a drop. "
            "Wet metallic flesh, surface tension rising, faint alien circuitry waking under the skin, "
            "dark void, continuous motion, no text, no logos."
        ),
        "drop": (
            "Macro cinematic shot of a liquid alien-biotech organism mutating on a bass drop. "
            "Grotesque organic circuitry tearing through glossy chrome flesh, wet biomechanical "
            "tendrils, iridescent veins, violent but continuous morph, black background, "
            "no text, no logos, no people."
        ),
        "release": (
            "Macro cinematic shot of a liquid chrome biotech organism settling after a mutation. "
            "Glossy membrane, residual alien filaments retracting, wet specular flesh, "
            "dark studio, slow viscous motion, no text, no logos."
        ),
        "sustain": (
            "Macro cinematic shot of a glossy liquid-chrome alien organism hovering in darkness. "
            "Wet biotech flesh, steady specular highlights, no text."
        ),
        "negative": (
            "text, watermark, logo, subtitles, human, face, hands, cartoon, low detail, "
            "flicker, cut, jump cut, static frame, overexposed, jpeg artifacts"
        ),
    },
    "comfy": {
        "mode": "dry-run",
        "backend": "local",  # local | cloud (comfy.cloud_url, cloud_parallel<=3; key in COMFY_ORG_API_KEY)
        "base_url": "http://127.0.0.1:8188",
        "proxy_url": "http://127.0.0.1:8189",
        "send_api_key": False,
        "api_key_env": "COMFY_API_KEY",
        "partner_api_key_env": "",
        "addons": False,
        "workflow": "workflows/ltx_v2v_api.json",
        "checkpoint_name": "ltx-video-2b-v0.9.5.safetensors",
        "video_model": "ltx",
        "clip_name": "t5xxl_fp8_e4m3fn_scaled.safetensors",
        "clip_type": "ltxv",
        "width": 512,
        "height": 320,
        "steps": 20,
        "cfg": 3.0,
        "sampler_name": "euler",
        "max_shift": 2.05,
        "base_shift": 0.95,
        "terminal": 0.1,
        "stretch": True,
        "nodes": {
            "checkpoint": "1",
            "clip": "2",
            "positive_prompt": "3",
            "negative_prompt": "4",
            "frame_rate": "5",
            "load_video": "6",
            "preprocess": "8",
            "latent": "9",
            "preserve_strength": "10",
            "steps": "11",
            "sampler": "12",
            "seed": "13",
            "cfg": "14",
            "model_sampling": "20",
            "save_video": "19",
            "fps": "18",
        },
    },
    "assemble": {
        "crossfade_frames": 4,
        "beat_flashes": True,
        "flash_amount": 0.22,
        "crf": 18,
    },
    "osc": {
        "host": "127.0.0.1",
        "port": 7000,
    },
}


def _merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg = deepcopy(DEFAULTS)
    config_path: Path | None = None
    if path:
        config_path = Path(path).expanduser().resolve()
        overlay = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(overlay, dict):
            raise ValueError(f"Config must be a JSON object: {config_path}")
        _merge(cfg, overlay)
    cfg["_config_path"] = str(config_path) if config_path else None
    return cfg


def resolve_path(path: str | Path, cfg: dict | None = None) -> Path:
    """Resolve a path against the config file's directory, then the cwd."""
    raw = Path(path)
    if raw.is_absolute():
        return raw
    if cfg and cfg.get("_config_path"):
        sibling = Path(cfg["_config_path"]).parent / raw
        if sibling.exists():
            return sibling
        # Configs live in configs/, repo files live one level up.
        parent = Path(cfg["_config_path"]).parent.parent / raw
        if parent.exists():
            return parent
    cwd = Path.cwd() / raw
    return cwd


# demo_house: the contest demo's look/mix is the default profile (see demo_house.py; config/defaults_demo.json mirrors it)
from xenoform.demo_house import DEMO_HOUSE as _DEMO_HOUSE  # noqa: E402
DEFAULTS.setdefault("house", deepcopy(_DEMO_HOUSE))

