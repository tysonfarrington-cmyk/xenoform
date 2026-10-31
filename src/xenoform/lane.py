"""The shots lane, now the timeline's model for the desk (docs/TIMELINE.md).

``build`` turns a cut's record (``simple/simple.json``, written by ``dense.run_simple`` and updated by every edit) into
what the desk draws under the result player: every shot with its length, section, the object it morphs from and the
one it lands on, the transition at each boundary (the vibe's premium pick, the boundary kind Chaos gave the handoff, or
what the timeline chose by hand), the shot's own overrides (a hold, a look, an FX intensity), the performer, own-footage
and generated runs laid over the shots, and the choices the timeline panel offers (``choices``). Nothing here renders
or edits; the routes beside ``recut`` do that, and this is what they read back.
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


def choices() -> dict:
    """What a boundary and a shot on the timeline may be set to: the transition kinds (premium, core and classic, all
    CPU) and the boundary kinds with their labels and one-line notes, the plays, the FX intensity range, the re-render
    variants and lengths, the run lengths."""
    from xenoform import dense as _D
    from xenoform import transitions_fx as T

    kinds = [{"id": k, "label": str(v.get("label") or k), "note": str(v.get("note") or ""), "group": str(v.get("tier") or "core")}
             for k, v in T.TRANSITIONS.items() if not v.get("gpu")]
    kinds.sort(key=lambda r: ({"premium": 0, "core": 1, "classic": 2}.get(r["group"], 3), r["label"]))
    notes = {"smear": "datamosh-style block displacement along the drums for half a bar; the next object pushes through",
             "strobe": "the two objects alternate frame by frame for a beat, luma-matched",
             "wipe": "the next object enters as strips, or as an iris where the song is loud, on the bass over a bar",
             "rip": "the two pictures' colour channels offset and crossed on the other stem"}
    kinds += [{"id": k, "label": _B.LABELS.get(k, k), "note": notes.get(k, ""), "group": "boundary"} for k in _B.KINDS]
    from xenoform import dream as _DR
    from xenoform import morph_style as _MS

    return {"transition_kinds": kinds, "plays": list(_D.PLAY), "fx_intensity": [0.0, 1.0],
            "rerender_variants": list(_D.RERENDER_VARIANTS), "render_s": list(_D.RENDER_S_RANGE),
            "insert_seconds": [int(x) for x in _D.INSERT_SECONDS],
            "dream_seconds": [int(x) for x in _DR.SECONDS], "dream_depths": list(_DR.DEPTHS),
            "dream_s_per_frame": _DR.SECONDS_PER_FRAME,
            "morph_styles": [{"id": s, "label": _MS.LABELS[s], "note": _MS.NOTES[s]} for s in _MS.STYLES]}


def build(info: dict, video_id: str = "") -> dict:
    shots = list(info.get("shots") or [])
    files = [str(f) for f in (info.get("stills") or [])]
    stills = [noun_of(s) for s in files]
    scene_files = {str(f) for f in (info.get("scene_files") or [])}
    pinned = {int(k) for k in (info.get("pinned") or []) if str(k).lstrip("-").isdigit()}
    swapped = {int(s["slot"]) for s in (info.get("swaps") or []) if isinstance(s, dict) and "slot" in s}
    chain = info.get("chain") or {}
    assign = list(chain.get("assign") or []) if isinstance(chain, dict) else []
    transitions = list(info.get("transitions") or [])
    boundary_fx = list(info.get("boundary_fx") or [])
    perf = info.get("performer") if isinstance(info.get("performer"), dict) else {}
    own = info.get("own") if isinstance(info.get("own"), dict) else {}
    perf_slots = {int(s["first"]): s for s in (perf.get("slots") or []) if isinstance(s, dict) and "first" in s}
    own_slots = {int(s["first"]): s for s in (own.get("slots") or []) if isinstance(s, dict) and "first" in s}
    inserts = [x for x in (info.get("inserts") or []) if isinstance(x, dict)]
    styles = [str(s) for s in (info.get("morph_styles") or [])]  # how each shot's morph changes (morph_style)
    # the timeline's overrides as the record keeps them (string keys), and how often a shot's morph was re-rendered
    so = {int(k): v for k, v in (info.get("shot_overrides") or {}).items() if str(k).lstrip("-").isdigit() and isinstance(v, dict)}
    bo = {int(k): v for k, v in (info.get("boundary_overrides") or {}).items() if str(k).lstrip("-").isdigit() and isinstance(v, dict)}
    rerendered: dict[int, int] = {}
    for r in info.get("rerenders") or []:
        if isinstance(r, dict) and str(r.get("shot", "")).lstrip("-").isdigit():
            rerendered[int(r["shot"])] = rerendered.get(int(r["shot"]), 0) + 1
    rows = []
    for i, s in enumerate(shots):
        start, end = float(s.get("start") or 0.0), float(s.get("end") or 0.0)
        # the morph the shot plays: the record says (``morph``, since the swap), else the long-song chain's assign, else i
        m = int(s["morph"]) if s.get("morph") is not None else int(assign[i]) if i < len(assign) else i
        a, b = (m % len(stills), (m + 1) % len(stills)) if stills else (0, 0)
        src = stills[a] if stills else ""
        dst = stills[b] if stills else ""
        gen = s.get("generated") if isinstance(s.get("generated"), dict) else None
        if gen is not None:  # a generated run: its own stills, not the chain's
            gi = int(gen.get("insert", -1))
            ins = inserts[gi] if 0 <= gi < len(inserts) else {}
            run_nouns = [noun_of(f) for f in (ins.get("stills") or [])]
            q = int(gen.get("index") or 0)
            src = run_nouns[q] if q < len(run_nouns) else ""
            dst = run_nouns[q + 1] if q + 1 < len(run_nouns) else ""
        row = {"index": i, "start": round(start, 3), "end": round(end, 3), "seconds": round(end - start, 3),
               "section": str(s.get("section") or ""), "boundary": str(s.get("boundary") or ""), "from": src, "to": dst}
        if isinstance(s.get("dream"), dict):  # dreamed over (xenoform.dream): its own pictures, cut in like a run
            row["dream"] = int(s["dream"].get("run", 0))
        if gen is not None:
            row["generated"] = int(gen.get("insert", 0))
        elif s.get("performer"):
            row["performer"] = True
        elif s.get("own"):
            row["own"] = True
        if s.get("own") and s.get("label"):  # a clips cut's clip shot (clip_cut): its clip's name
            row["from"] = str(s["label"])
        if isinstance(s.get("clip_morph"), dict):  # a clips cut's morph: from one clip into the next
            row.update({"from": str(s["clip_morph"].get("from") or ""), "to": str(s["clip_morph"].get("to") or ""), "clip_morph": True})
        if s.get("dropped"):  # deleted on the timeline: zero length, the shot before plays on (dense.arrange_shots)
            row["dropped"] = True
        if s.get("plays") is not None:  # the slot plays another shot's morph (Move, Duplicate)
            row["plays"] = int(s["plays"])
        if stills and not (s.get("performer") or s.get("own") or gen or s.get("dream")):
            # the chain slots the shot's morph leaves and lands on: a swap on the lane names the landing still
            row.update({"from_still": a, "still": b, "to_file": files[b], "to_kind": "scene" if files[b] in scene_files else "object",
                        "pinned": b in pinned, "swapped": b in swapped, "morph": m})
        if not (s.get("performer") or s.get("own")):
            row["style"] = styles[i] if i < len(styles) and styles[i] else "melt"
        # the pacing engine's marks (xenoform.pacing): a drop run and its heat, its opening event, a rest's beats
        if s.get("drop_run") is not None:
            row.update({"drop_run": int(s["drop_run"]), "heat": float(s.get("heat") or 0.0)})
        if s.get("event"):
            row["event"] = str(s["event"])
        if s.get("rest"):
            row.update({"rest": int(s["rest"]), "rest_s": round(float(s.get("rest_s") or 0.0), 3)})
        t = transitions[i] if i < len(transitions) else None
        if isinstance(t, dict) and t.get("kind"):
            row["transition"] = str(t["kind"])
            row["transition_id"] = str(t["kind"])
        b = boundary_fx[i] if i < len(boundary_fx) else None
        if isinstance(b, dict) and b.get("kind"):  # a boundary kind took this handoff (the premium pick stepped aside)
            row["transition"] = _B.label(b)
            row["transition_id"] = str(b["kind"])
            row["kind"] = str(b["kind"])
        o = so.get(i) or {}
        if o.get("play") == "hold" or s.get("hold"):
            row["hold"] = True
        if o.get("look"):
            row["look"] = str(o["look"])
        if o.get("fx_intensity") is not None:
            row["fx_intensity"] = float(o["fx_intensity"])
        if o.get("timing"):
            row["timing"] = str(o["timing"])
        if i in bo and bo[i].get("fx"):
            row["fx_override"] = str(bo[i]["fx"])
        if i in rerendered:
            row["rerendered"] = rerendered[i]
        if i > 0:
            prev = rows[i - 1]
            hard = any(prev.get(k) for k in ("hold", "performer", "own")) or prev.get("generated") is not None \
                or any(row.get(k) for k in ("performer", "own")) or row.get("generated") is not None \
                or prev.get("dream") is not None or row.get("dream") is not None
            if row.get("generated") is not None and prev.get("generated") == row.get("generated"):
                hard = bool(prev.get("hold"))  # inside one run the joins are morph landings
            if row.get("dream") is not None and prev.get("dream") == row.get("dream"):
                hard = bool(prev.get("hold"))  # inside one dream the joins flow on
            row["handoff"] = "cut" if hard else "morph"  # a visible cut into this shot: out of a hold or across an insert's edge
        rows.append(row)
    overlays = []
    for gi, ins in enumerate(inserts):
        first, last = int(ins.get("first", 0)), int(ins.get("last", ins.get("first", 0)))
        if first < len(rows):
            count = len(ins.get("clips") or []) or (last - first + 1)
            overlays.append({"kind": "generated", "first": first, "last": last, "start": rows[first]["start"],
                             "end": rows[min(last, len(rows) - 1)]["end"], "label": f"Generated · {count} morph{'s' if count != 1 else ''}",
                             "insert": gi})
    for di, dr in enumerate(x for x in (info.get("dreams") or []) if isinstance(x, dict)):
        first, last = int(dr.get("first", 0)), int(dr.get("last", dr.get("first", 0)))
        if first < len(rows) and all(rows[j].get("dream") == di for j in range(first, min(last, len(rows) - 1) + 1)):
            overlays.append({"kind": "dream", "first": first, "last": last, "start": rows[first]["start"],
                             "end": rows[min(last, len(rows) - 1)]["end"], "label": f"Dream · {dr.get('depth', 'light')}", "dream": di})
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
        # a passage by role: a new one starts where the role changes and where a drop run opens (two runs side by side
        # stay two passages, each with its heat)
        opens = r.get("event") == "drop" or (r.get("drop_run") is not None and sections and sections[-1].get("drop_run") != r.get("drop_run"))
        if r["section"] and (not sections or sections[-1]["section"] != r["section"] or opens):
            sections.append({"section": r["section"], "start": r["start"], "end": r["end"],
                             **({"drop_run": r["drop_run"], "heat": r["heat"]} if r.get("drop_run") is not None else {})})
        elif sections and r["section"] == sections[-1]["section"]:
            sections[-1]["end"] = r["end"]
    for sec in sections:  # the rests a passage holds (Breathe)
        held = sum(1 for r in rows if r.get("rest") and sec["start"] - 1e-6 <= r["start"] < sec["end"] - 1e-6)
        if held:
            sec["rests"] = held
    pacing = info.get("pacing") if isinstance(info.get("pacing"), dict) else {}
    shape = info.get("recut_state") if isinstance(info.get("recut_state"), dict) else {}
    chain_rows = [{"index": k, "file": f, "noun": stills[k], "kind": "scene" if f in scene_files else "object",
                   "pinned": k in pinned, "swapped": k in swapped} for k, f in enumerate(files)]
    # only a Draft cut swaps and re-renders: a Fast Final or Cloud Final record says tier "draft" too, with its flag
    draft = str(info.get("tier") or "draft") != "final" and not info.get("fast") and not info.get("cloud")
    return {"id": video_id, "duration": round(duration, 3), "shots": rows, "sections": sections, "overlays": overlays,
            "morphs": len(set(assign)) if assign else len(rows), "objects": len(set(stills)), "plan": str(info.get("plan_name") or ""),
            "pace": str(((info.get("recut_state") or {}).get("pace")) or ""), "engine": str(info.get("engine") or ""),
            "vibe": str(info.get("vibe") or ""), "tier": str(info.get("tier") or ""), "stills": chain_rows,
            "opens_on": chain_rows[0] if chain_rows else None,  # the first still: no shot lands on it, the lane's opening tile does
            "swaps": len(swapped), "swappable": draft and bool(files) and info.get("source") != "clips",
            # the timeline: the overrides as persisted, the GPU edits so far, what may be edited, and the choices
            "shot_overrides": {str(k): v for k, v in sorted(so.items())}, "boundary_overrides": {str(k): v for k, v in sorted(bo.items())},
            "rerenders": sum(rerendered.values()), "inserts": len(inserts), "dreams": len(info.get("dreams") or []),
            "editable": bool(rows) and bool(info.get("clips")),
            "rerenderable": draft and bool(info.get("clips")) and info.get("source") != "clips",
            "source": str(info.get("source") or "objects"), "beats": [round(float(b), 3) for b in (info.get("beats") or [])],
            "drop": info.get("drop"), "morph_style": str(info.get("morph_style") or "auto"),
            "morph_timing": str(info.get("morph_timing") or "smooth"), "choices": choices() if rows else {},
            # the cut's shape (xenoform.pacing): what it was made or last re-cut in, and the line the Make reported
            "breathe": bool(pacing.get("breathe", shape.get("breathe", False))),
            "drop_mode": str(pacing.get("drop_mode") or shape.get("drop_mode") or "off"),
            "plan_line": str(pacing.get("line") or ""), "rests": sum(1 for r in rows if r.get("rest"))}
