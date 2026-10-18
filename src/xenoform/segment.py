"""Cut a feature timeline into LTX-friendly chunks.

LTX video latents want a frame count of ``8*k + 1`` (9, 17, …, 97). Cuts prefer
section boundaries, then beats, and stay inside the configured duration window.
The last chunk may repeat its final frame a few times so the count lands on
``8*k + 1`` without dropping audio sync on the frames that were really rendered.
"""

from __future__ import annotations

from typing import Any


def snap_8n1(n: int) -> int:
    """Nearest frame count of the form 8*k+1, minimum 9."""
    n = max(9, int(n))
    k = int(round((n - 1) / 8.0))
    return max(1, k) * 8 + 1


def plan_chunks(
    features: dict[str, Any],
    target_seconds: float = 4.0,
    min_seconds: float = 2.8,
    max_seconds: float = 5.2,
) -> list[dict[str, Any]]:
    fps = float(features["fps"])
    n_frames = int(features["n_frames"])
    if n_frames <= 0 or fps <= 0:
        return []

    target = snap_8n1(int(round(target_seconds * fps)))
    min_f = snap_8n1(int(round(min_seconds * fps)))
    max_f = snap_8n1(int(round(max_seconds * fps)))
    if min_f > max_f:
        min_f, max_f = max_f, min_f
    target = min(max(target, min_f), max_f)
    candidates = list(range(min_f, max_f + 1, 8))

    beat_frames = []
    for stamp in features.get("beats", []):
        beat_frames.append(int(np_floor(float(stamp) * fps)))
    section_frames = []
    for section in features.get("sections", []):
        section_frames.append(int(section["start_frame"]))
        section_frames.append(int(section["end_frame"]))

    chunks: list[dict[str, Any]] = []
    cursor = 0
    while cursor < n_frames:
        remain = n_frames - cursor
        if remain <= max_f or not candidates:
            # Round to a legal latent length that covers every remaining frame.
            # snap_8n1 can round down; step up one quantum rather than drop frames.
            length = snap_8n1(remain)
            if length < remain:
                length += 8
            if length < min_f:
                length = min_f
            chunks.append(_chunk(len(chunks), cursor, remain, length, fps, features))
            break

        best = target
        best_score = 1e9
        for length in candidates:
            end = cursor + length
            if end >= n_frames:
                continue
            score = abs(length - target) * 0.2
            if section_frames:
                dist_s = min(abs(end - frame) for frame in section_frames)
                window = max(1.0, 0.4 * fps)
                if dist_s <= window:
                    score -= (1.0 - dist_s / window) * 8.0
            if beat_frames:
                dist_b = min(abs(end - frame) for frame in beat_frames)
                if dist_b <= 3:
                    score -= 2.5
            tail = n_frames - end
            if 0 < tail < min_f:
                score += 5.0
            if score < best_score:
                best_score = score
                best = length
        chunks.append(_chunk(len(chunks), cursor, best, best, fps, features))
        cursor += best
    return chunks


def _chunk(index: int, start: int, source_frames: int, length: int, fps: float, features: dict) -> dict[str, Any]:
    pad = max(0, length - source_frames)
    mid = min(start + max(source_frames // 2, 0), int(features["n_frames"]) - 1)
    frame = features["frames"][mid]
    return {
        "index": index,
        "start_frame": int(start),
        "source_frames": int(source_frames),
        "length": int(length),
        "pad": int(pad),
        "start": round(start / fps, 6),
        "duration": round(source_frames / fps, 6),
        "section": frame["section"],
        "is_drop": bool(frame["is_drop"]),
        "energy": float(frame["energy"]),
    }


def np_floor(value: float) -> int:
    import math

    return int(math.floor(value))
