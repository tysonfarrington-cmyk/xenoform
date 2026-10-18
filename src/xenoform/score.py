"""Director's Score. Existing bands decide what a section becomes.

Drop or a high-dominant window is impact (splash, crystal). A bass-dominant
window is mass (liquid, metal). Everything else holds as organic. The source
library, when it is loaded, names the morph pair. Re-rendering one segment
uses the desk's existing scene filter.
"""

from __future__ import annotations

from typing import Any

_ROLES = {
    "impact": {"stem": "high", "becomes": "splash / crystal"},
    "mass": {"stem": "bass", "becomes": "liquid / metal"},
    "hold": {"stem": "mid", "becomes": "organic"},
}


def stem_role(label: str, bass: float, mid: float, high: float) -> str:
    if str(label or "") == "drop" or (high > bass and high > mid):
        return "impact"
    if bass >= mid and bass >= high:
        return "mass"
    return "hold"


def _mean(frames: list, key: str) -> float:
    if not frames:
        return 0.0
    total = 0.0
    for frame in frames:
        try:
            total += float(frame.get(key) or 0.0)
        except (TypeError, ValueError, AttributeError):
            continue
    return total / len(frames)


def _window(features: dict, section: dict) -> list:
    frames = features.get("frames") or []
    if not frames:
        return []
    fps = float(features.get("fps") or 12) or 12.0
    if "start_frame" in section or "end_frame" in section:
        start = int(section.get("start_frame") or 0)
        end = int(section.get("end_frame") or 0)
    else:
        start = int(round(float(section.get("start") or 0) * fps))
        end = int(round(float(section.get("end") or 0) * fps))
    start = max(0, start)
    end = max(start, min(len(frames), end))
    return frames[start:end] or frames[start : start + 1]


def directors_score(
    features: dict | None,
    *,
    vibe: str = "",
    library: Any = None,
    pinned: Any = None,
    banned: Any = None,
    exclude_faces: bool = True,
    allow_pd_us: bool = False,
) -> list[dict[str, Any]]:
    """One row per section. Library pairs are optional."""
    features = features or {}
    rows: list[dict[str, Any]] = []
    for index, section in enumerate(features.get("sections") or []):
        if not isinstance(section, dict):
            continue
        window = _window(features, section)
        bass = _mean(window, "bass")
        mid = _mean(window, "mid")
        high = _mean(window, "high")
        label = str(section.get("label") or "")
        role = stem_role(label, bass, mid, high)
        spec = _ROLES[role]
        pair: dict[str, Any] = {"source": None, "target": None, "chain": False, "reason": spec["becomes"]}
        if library is not None and getattr(library, "items", None):
            from xenoform.source_library import pick_pair

            energy = section.get("level")
            if energy is None:
                energy = _mean(window, "energy")
            pair = pick_pair(
                library,
                vibe=vibe,
                mood=spec["becomes"],
                energy=energy or 0,
                beat="drop" if role == "impact" else "",
                section=label,
                pinned=pinned,
                banned=banned,
                exclude_faces=exclude_faces,
                allow_pd_us=allow_pd_us,
            )
        source = pair.get("source") or {}
        target = pair.get("target") or {}
        rows.append(
            {
                "index": int(section.get("index") if section.get("index") is not None else index),
                "label": label,
                "start": round(float(section.get("start") or 0), 4),
                "end": round(float(section.get("end") or 0), 4),
                "role": role,
                "stem": spec["stem"],
                "becomes": spec["becomes"],
                "bass": round(bass, 4),
                "mid": round(mid, 4),
                "high": round(high, 4),
                "source": source.get("id") or "",
                "target": target.get("id") or "",
                "chain": bool(pair.get("chain")),
                "reason": pair.get("reason") or spec["becomes"],
            }
        )
    return rows
