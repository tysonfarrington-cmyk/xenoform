"""The shots lane: a finished cut as a read-only strip of shots (the seed of the timeline).

``build`` turns a cut's record (``simple/simple.json``, written by ``dense.run_simple``) into what the desk draws
under the result player: every shot with its length, section, the object it morphs from and the one it lands on,
the transition at each section boundary (the vibe's premium pick, or the boundary kind Chaos gave the handoff: a smear,
a strobe cut, a wipe, a chromatic rip), and the performer and own-footage slots laid over the shots. Nothing
here renders or edits; the lane shows what the cut did and lets a click seek the player.
"""
from __future__ import annotations

import re
from pathlib import Path

from xenoform import boundary_fx as _B

SECTION_ORDER = ("intro", "calm", "sustain", "build", "release", "drop", "drop_late", "outro")


def noun_of(still: str) -> str:
    """"cosmic/00_orb_iridescent.jpg" -> "orb iridescent"; an own still "cosmic/000_brass_astrolabe.jpg" -> "brass astrolabe"."""
    stem = Path(str(still)).stem
    return re.sub(r"^\d+[_\- ]*", "", stem).replace("_", " ").strip() or stem


def build(info: dict, video_id: str = "") -> dict:
    shots = list(info.get("shots") or [])
    stills = [noun_of(s) for s in (info.get("stills") or [])]
    chain = info.get("chain") or {}
    assign = list(chain.get("assign") or []) if isinstance(chain, dict) else []
    transitions = list(info.get("transitions") or [])
    boundary_fx = list(info.get("boundary_fx") or [])
    perf = info.get("performer") if isinstance(info.get("performer"), dict) else {}
    own = info.get("own") if isinstance(info.get("own"), dict) else {}
    perf_slots = {int(s["first"]): s for s in (perf.get("slots") or []) if isinstance(s, dict) and "first" in s}
    own_slots = {int(s["first"]): s for s in (own.get("slots") or []) if isinstance(s, dict) and "first" in s}
    rows = []
    for i, s in enumerate(shots):
        start, end = float(s.get("start") or 0.0), float(s.get("end") or 0.0)
        m = int(assign[i]) if i < len(assign) else i
        src = stills[m % len(stills)] if stills else ""
        dst = stills[(m + 1) % len(stills)] if stills else ""
        row = {"index": i, "start": round(start, 3), "end": round(end, 3), "seconds": round(end - start, 3),
               "section": str(s.get("section") or ""), "boundary": str(s.get("boundary") or ""), "from": src, "to": dst}
        t = transitions[i] if i < len(transitions) else None
        if isinstance(t, dict) and t.get("kind"):
            row["transition"] = str(t["kind"])
        b = boundary_fx[i] if i < len(boundary_fx) else None
        if isinstance(b, dict) and b.get("kind"):  # a boundary kind took this handoff (the premium pick stepped aside)
            row["transition"] = _B.label(b)
            row["kind"] = str(b["kind"])
        rows.append(row)
    overlays = []
    for first, slot in sorted(perf_slots.items()):
        last = int(slot.get("last", first))
        if first < len(shots):
            overlays.append({"kind": "performer", "first": first, "last": last, "start": rows[first]["start"],
                             "end": rows[min(last, len(rows) - 1)]["end"], "label": str(slot.get("instrument") or "Polly")})
    for first, slot in sorted(own_slots.items()):
        last = int(slot.get("last", first))
        if first < len(shots):
            overlays.append({"kind": "own", "first": first, "last": last, "start": rows[first]["start"],
                             "end": rows[min(last, len(rows) - 1)]["end"], "label": Path(str(slot.get("clip") or "clip")).name})
    duration = rows[-1]["end"] if rows else 0.0
    sections = []
    for r in rows:
        if r["section"] and (not sections or sections[-1]["section"] != r["section"]):
            sections.append({"section": r["section"], "start": r["start"], "end": r["end"]})
        elif sections and r["section"] == sections[-1]["section"]:
            sections[-1]["end"] = r["end"]
    return {"id": video_id, "duration": round(duration, 3), "shots": rows, "sections": sections, "overlays": overlays,
            "morphs": len(set(assign)) if assign else len(rows), "objects": len(set(stills)), "plan": str(info.get("plan_name") or ""),
            "pace": str(((info.get("recut_state") or {}).get("pace")) or ""), "engine": str(info.get("engine") or "")}
