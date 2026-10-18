"""Section prompts and the energy → denoise map for the LTX restyle."""

from __future__ import annotations

from typing import Any


def prompt_for(section: str, prompts: dict[str, str]) -> str:
    if section in prompts:
        return prompts[section]
    return prompts.get("sustain") or prompts.get("calm") or ""


def chunk_drive(frames: list[dict[str, Any]], chunk: dict[str, Any]) -> dict[str, float]:
    """Map a chunk's energy onto LTX preserve-strength and preprocess compression.

    ``LTXVImgToVideoInplace.strength`` is a preserve control: 1 keeps the
    encoded video, 0 lets the sampler replace it. Denoise here is the
    complement, so a drop (high energy) mutates harder than a calm section.
    """
    start = int(chunk["start_frame"])
    count = int(chunk["source_frames"])
    window = frames[start : start + max(count, 1)] or frames[start : start + 1]
    energy = sum(float(frame["energy"]) for frame in window) / len(window)
    onset = sum(float(frame["onset_env"]) for frame in window) / len(window)
    drop = any(frame["is_drop"] for frame in window)
    denoise = 0.16 + 0.42 * energy + 0.12 * onset
    if drop:
        denoise += 0.18
    denoise = float(min(0.85, max(0.12, denoise)))
    preserve = 1.0 - denoise
    compression = int(round(10 + 28 * denoise))
    return {
        "energy": round(energy, 6),
        "onset": round(onset, 6),
        "denoise": round(denoise, 6),
        "preserve_strength": round(preserve, 6),
        "img_compression": compression,
        "is_drop": drop,
    }
