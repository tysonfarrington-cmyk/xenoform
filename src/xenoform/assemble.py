"""Stitch restyle chunks, blend the cuts, mux the original audio.

The blend is in place: a few frames on either side of a cut are mixed, and the
frame count stays equal to the feature timeline so the audio lock is unchanged.
Beat flashes are a short additive lift on frames the analyzer marked as beats.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from xenoform.video import read_all_frames, write_mp4

log = logging.getLogger("xenoform")


def _load_manifest_chunks(manifest: dict) -> list[np.ndarray]:
    sequences = []
    for chunk in manifest["chunks"]:
        frames = read_all_frames(chunk["output"])
        source = int(chunk["source_frames"])
        # Drop the latent-padding frames so the timeline matches the analysis.
        if frames.shape[0] > source:
            frames = frames[:source]
        if frames.shape[0] != source:
            raise RuntimeError(
                f"Chunk {chunk['index']} has {frames.shape[0]} frames, expected {source}"
            )
        sequences.append(frames)
    return sequences


def _fade_list(cuts: list[int], fade: int | list[int]) -> list[int]:
    if isinstance(fade, int):
        return [int(fade)] * len(cuts)
    fades = [int(v) for v in fade]
    if len(fades) < len(cuts):
        pad = fades[-1] if fades else 0
        fades.extend([pad] * (len(cuts) - len(fades)))
    return fades[: len(cuts)]


def _boundary_blend(frames: np.ndarray, cuts: list[int], fade: int | list[int]) -> np.ndarray:
    fades = _fade_list(cuts, fade)
    if not cuts or all(n <= 0 for n in fades):
        return frames
    out = frames.astype(np.float32)
    for cut, fade_n in zip(cuts, fades):
        if fade_n <= 0:
            continue
        for offset in range(1, fade_n + 1):
            left = cut - offset
            right = cut + offset - 1
            if left < 0 or right >= len(out):
                continue
            # Weight toward the cut so the seam eases instead of ghosting the whole shot.
            alpha = offset / (fade_n + 1)
            mix_l = out[left] * (1.0 - 0.5 * (1.0 - alpha)) + out[right] * (0.5 * (1.0 - alpha))
            mix_r = out[right] * (1.0 - 0.5 * (1.0 - alpha)) + out[left] * (0.5 * (1.0 - alpha))
            out[left] = mix_l
            out[right] = mix_r
    return np.clip(out, 0, 255)


def _beat_flashes(frames: np.ndarray, features: dict | None, amount: float) -> np.ndarray:
    if features is None or amount <= 0:
        return frames
    out = frames.astype(np.float32)
    limit = min(len(out), len(features["frames"]))
    lift = np.array([236, 244, 255], dtype=np.float32)
    for i in range(limit):
        env = float(features["frames"][i].get("beat_env", 0.0))
        if env <= 0.05:
            continue
        strength = amount * env
        out[i] = out[i] * (1.0 - strength) + lift * strength
    return np.clip(out, 0, 255)


def hit_frames(frames: np.ndarray, fps: float, times: list | None, amount: float = 0.72) -> np.ndarray:
    """Lift exactly one frame at each morph hit. No trail."""
    if frames is None or not len(frames) or not times or amount <= 0 or fps <= 0:
        return frames
    out = frames.astype(np.float32)
    lift = np.array([255, 255, 255], dtype=np.float32)
    strength = max(0.0, min(1.0, float(amount)))
    for stamp in times:
        try:
            index = int(round(float(stamp) * float(fps)))
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(out):
            out[index] = out[index] * (1.0 - strength) + lift * strength
    return np.clip(out, 0, 255)


def assemble(
    manifest: dict,
    audio_path: str | Path,
    out_path: str | Path,
    features: dict | None = None,
    crossfade_frames: int | list[int] = 4,
    beat_flashes: bool = True,
    flash_amount: float = 0.22,
    crf: int = 18,
    hit_times: list | None = None,
    hit_amount: float = 0.72,
) -> None:
    sequences = _load_manifest_chunks(manifest)
    if not sequences:
        raise RuntimeError("Manifest has no chunks")
    fps = float(manifest["fps"])
    cuts = []
    cursor = 0
    for sequence in sequences[:-1]:
        cursor += len(sequence)
        cuts.append(cursor)
    stacked = np.concatenate(sequences, axis=0)
    blended = _boundary_blend(stacked, cuts, crossfade_frames)
    if beat_flashes:
        blended = _beat_flashes(blended, features, float(flash_amount))
    if hit_times:
        blended = hit_frames(blended, fps, hit_times, float(hit_amount))
    frames = blended.astype(np.uint8)
    write_mp4(out_path, frames, fps, audio_path=audio_path, crf=crf)
    log.info("assembled %s frames -> %s", len(frames), out_path)
