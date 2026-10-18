"""The first thing a judge should see: the drop, already decided.

The song picks a source and a target. The morph time is the downbeat of
that drop. Nothing here loads a checkpoint.
"""

from __future__ import annotations

from typing import Any

from xenoform.morph.lock import downbeats_from, land_time


def _clock(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    return f"{minutes}:{rest:04.1f}"


def _first_section(features: dict) -> dict | None:
    for section in features.get("sections") or []:
        if isinstance(section, dict) and str(section.get("label") or "") == "drop":
            return section
    drops = features.get("drops") or []
    if drops:
        span = drops[0]
        if isinstance(span, dict):
            return {"label": "drop", "start": span.get("start") or 0, "end": span.get("end") or 0}
        try:
            return {"label": "drop", "start": float(span), "end": float(span)}
        except (TypeError, ValueError):
            return None
    return None


def _row_for(rows: list | None) -> dict:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("label") or "") == "drop" or row.get("role") == "impact":
            return row
    return {}


def first_drop(features: dict | None, rows: list | None = None) -> dict[str, Any]:
    """The opening claim. `ready` is false when the song has no drop."""
    features = features or {}
    section = _first_section(features)
    if section is None:
        return {
            "ready": False,
            "at": 0.0,
            "label": "",
            "kind": "",
            "source": "",
            "target": "",
            "becomes": "",
            "line": "This song has no drop. The desk will hold the object.",
        }
    when = float(section.get("start") or 0)
    at, kind = land_time(
        when,
        features.get("beats"),
        section="drop",
        drops=features.get("drops"),
    )
    row = _row_for(rows)
    source = str(row.get("source") or "")
    target = str(row.get("target") or "")
    becomes = str(row.get("becomes") or "splash / crystal")
    if source and target:
        pair = f"{source} → {target}"
        why = "The drop picks the pair. The morph lands on the downbeat."
    else:
        pair = becomes
        why = "The drop is impact. The morph lands on the downbeat."
    return {
        "ready": True,
        "at": round(float(at), 4),
        "label": "drop",
        "kind": kind,
        "source": source,
        "target": target,
        "becomes": becomes,
        "line": f"{_clock(at)}. {pair}. {why}",
        "downbeats": downbeats_from(features.get("beats")),
    }
