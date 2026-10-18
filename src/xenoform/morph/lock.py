"""Land morphs on downbeats and drops. Breakdowns stay sparse.

Downbeats are every fourth detected beat, counting from the first beat.
A drop lands on the downbeat nearest that drop. A breakdown keeps one morph.
The hit is one frame, not a trail.
"""

from __future__ import annotations

from typing import Any

_HOT = {"drop", "climax"}
_SPARSE = {"calm", "release", "sustain", "breakdown", "break"}
_FRAME_MIX = {"keyframe-blend", "cross-clip"}


def _clock(beats: list | None) -> list[float]:
    found: list[float] = []
    for beat in beats or []:
        try:
            found.append(round(float(beat), 6))
        except (TypeError, ValueError):
            continue
    return sorted(set(found))


def downbeats_from(beats: list | None, per_bar: int = 4) -> list[float]:
    """Beat 1 of each bar. The analyzer's beat list is the only source."""
    clock = _clock(beats)
    step = max(1, int(per_bar))
    return [clock[index] for index in range(0, len(clock), step)]


def _nearest(clock: list[float], when: float) -> float:
    return min(clock, key=lambda stamp: (abs(stamp - when), stamp))


def _drop_anchor(when: float, drops: list | None) -> float | None:
    for span in drops or []:
        if isinstance(span, dict):
            try:
                start = float(span.get("start") or 0.0)
                end = float(span.get("end") or start)
            except (TypeError, ValueError):
                continue
        else:
            try:
                start = end = float(span)
            except (TypeError, ValueError):
                continue
        if start - 0.05 <= when <= max(end, start) + 0.05:
            return start
    return None


def land_time(
    when: float,
    beats: list | None,
    *,
    section: str = "",
    drops: list | None = None,
) -> tuple[float, str]:
    """The time a morph should hit, and whether that time is a drop or a downbeat."""
    clock = _clock(beats)
    downs = downbeats_from(clock)
    grid = downs or clock
    if not grid:
        return float(when), "beat"
    label = str(section or "").lower()
    anchor = _drop_anchor(float(when), drops)
    if label in _HOT or anchor is not None:
        return _nearest(grid, anchor if anchor is not None else float(when)), "drop"
    if downs:
        return _nearest(downs, float(when)), "downbeat"
    return _nearest(clock, float(when)), "beat"


def section_at(when: float, sections: list | None, scene: dict | None = None) -> str:
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        try:
            start = float(section.get("start") or 0.0)
            end = float(section.get("end") or start)
        except (TypeError, ValueError):
            continue
        if start <= float(when) < end or (end == start and abs(start - float(when)) < 1e-6):
            return str(section.get("label") or "")
    if scene:
        return str(scene.get("section") or scene.get("beat") or "")
    return ""


def choose_joins(
    scenes: list[dict] | None,
    sections: list | None,
    method: str,
) -> tuple[list[dict[str, Any]], int]:
    """Which boundaries morph. Drops chain. A breakdown keeps one."""
    rows: list[dict[str, Any]] = []
    sparse_used = False
    for index, scene in enumerate(scenes or []):
        if index == 0 or not isinstance(scene, dict):
            continue
        when = float(scene.get("start") or 0.0)
        label = section_at(when, sections, scene).lower()
        hot = label in _HOT or bool(scene.get("is_drop"))
        if hot:
            rows.append(
                {
                    "index": index,
                    "section": label or "drop",
                    "pace": "chain",
                    "reason": "Drop. The morph chain lands on the downbeat.",
                }
            )
            continue
        if label in _SPARSE or not sections:
            if scene.get("signature") and not sparse_used:
                sparse_used = True
                rows.append(
                    {
                        "index": index,
                        "section": label or "breakdown",
                        "pace": "sparse",
                        "reason": "Breakdown. One morph, then hard cuts.",
                    }
                )
    cap = 4 if str(method or "") in _FRAME_MIX else 2
    kept = rows[:cap]
    return kept, max(0, len(rows) - cap)
