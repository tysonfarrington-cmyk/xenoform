"""The storyboard: a song and a few knobs become shots on the beat, the chain of objects, and a request a morph.

``build`` plans the cut the way a desk Make does (``plan.shots_for``; for a song over 20 s the long-song chain, one morph
a shot and no object twice; for a short clip the desk's no-repeat guardrail), picks the chain of stills (``stills.pick``),
gives every shot its style (``looks.styles_for``), its intensity and effects (the Intensity, Speed and Chaos knobs,
``plan.apply_macros``) and its timing (``looks.plan_timing``). ``pair`` is what one morph asks LTX 0.9.5 for, value for
value what ``cloud_morph._local_clips`` sends through ``workflows/xenoform_morph.json``.

``apply_edits`` lays the Morph Timeline's edits over a plan: cuts moved, split or joined on the beats (rebuilt as the
desk's ``cut_plan``), a shot's own style, timing, hold or seed, the intensity keyframes, the object pins. The edits are
kept apart from the plan (they are what the Timeline node saves in the workflow), so a change upstream still flows
through and the edits land on it; edits made for another song are kept but not applied.

The storyboard is a plain dict (JSON all the way down) so it passes between nodes, into the editor and into a file.
"""

from __future__ import annotations

import copy
import hashlib
import json

import numpy as np

from . import looks
from . import plan as P
from . import stills

SCHEMA = "xenoform.storyboard/1"
EDITS = "xenoform.timeline/1"
ENERGIES = ("dense", "flow")
ASPECTS = ("16:9", "9:16")
TIERS = ("draft",)
WAVE_FPS = 12.0  # the strip's waveform rate


def _song_summary(song: dict) -> dict:
    """What the planner and the strip read from the song: its clock, sections, drop and a loudness lane."""
    f = song.get("features") or {}
    beats = [round(float(b), 4) for b in f.get("beats") or []]
    frames = f.get("frames") or []
    fps = float(f.get("fps") or 0.0) or WAVE_FPS
    wave = [float(x.get("rms") or 0.0) for x in frames]
    energy = [float(x.get("energy") or 0.0) for x in frames]
    if fps > WAVE_FPS and wave:  # thinned to the strip's rate
        step = fps / WAVE_FPS
        idx = np.clip(np.round(np.arange(0, len(wave), step)).astype(int), 0, len(wave) - 1)
        wave, energy = [wave[i] for i in idx], [energy[i] for i in idx]
        fps = WAVE_FPS
    sections = [{"label": str(s.get("label") or "calm"), "start": round(float(s.get("start") or 0.0), 4),
                 "end": round(float(s.get("end") or 0.0), 4), "level": round(float(s.get("level") or 0.0), 4)}
                for s in f.get("sections") or []]
    duration = float(f.get("duration") or 0.0)
    period = P._period(beats) if len(beats) > 1 else 0.5
    passages = [{"role": r["role"], "label": r["label"], "start": round(float(r["start"]), 4), "end": round(float(r["end"]), 4)}
                for r in P.story_roles(sections, duration, min_len=min(6.0, max(2.0, 4 * period)))] if sections else []
    return {"name": str(song.get("name") or "song"), "path": str(song.get("path") or ""), "key": str(song.get("key") or ""),
            "duration": round(duration, 4), "tempo": round(float(f.get("tempo") or 0.0), 3), "beats": beats,
            "downbeats": beats[::4], "beat_s": round(period, 4), "drop": song.get("drop"), "sections": sections,
            "passages": passages, "wave": [round(v, 3) for v in wave], "energy": [round(v, 3) for v in energy],
            "wave_fps": fps, "engine": str(song.get("engine") or "")}


def _section_at(sections: list[dict], t: float) -> str:
    for s in sections:
        if float(s["start"]) - 1e-6 <= t < float(s["end"]):
            return str(s["label"])
    return str(sections[-1]["label"]) if sections else ""


def _directed(summary: dict) -> dict:
    return {"duration": summary["duration"], "beats": list(summary["beats"]), "sections": list(summary["sections"])}


def build(song: dict, *, vibe: str = stills.BUNDLED_VIBE, idea: str = "", energy: str = "dense", forms: int = 0,
          speed: float = 0.5, chaos: float = 0.3, intensity: float = 0.5, morph_style: str = "auto",
          morph_timing: str = "smooth", pace: str = "viscous", aspect: str = "16:9", seed: int = 2727,
          tier: str = "draft", user_folder: str = "", pins: dict | None = None, cut_plan: dict | None = None) -> dict:
    """The storyboard for ``song`` (the Song analysis node's value: ``features``, ``path``, ``drop``, ``key``)."""
    summary = _song_summary(song)
    duration = summary["duration"]
    if duration <= 0:
        raise P.CutPlanError("The song has no length: analyse it first.")
    inputs = {"vibe": str(vibe), "idea": str(idea or ""), "energy": energy if energy in ENERGIES else "dense",
              "forms": max(0, int(forms or 0)), "speed": float(speed), "chaos": float(chaos), "intensity": float(intensity),
              "morph_style": looks.normal_style(morph_style), "morph_timing": looks.normal_timing(morph_timing),
              "pace": P.story_pace({"pace": pace}), "aspect": aspect if aspect in ASPECTS else "16:9", "seed": int(seed),
              "tier": tier if tier in TIERS else "draft", "user_folder": str(user_folder or "")}
    state = {"energy_preset": inputs["energy"], "morph_count": inputs["forms"] or "auto", "pace": inputs["pace"],
             "macros": {"intensity": inputs["intensity"], "speed": inputs["speed"], "chaos": inputs["chaos"]}}
    if cut_plan:
        state["cut_plan"] = cut_plan
    directed = _directed(summary)
    drop = summary["drop"]
    shots, plan = P.shots_for(state, directed, drop=drop)
    notes: list[str] = []
    pool_rows = stills.user_rows(inputs["user_folder"]) + stills.pool(inputs["vibe"])
    pool_n = stills.distinct(pool_rows)
    long_song = P.long_cut(duration)
    chain = None
    if long_song and not cut_plan:
        chain = P.clip_plan(shots, duration, summary["beats"], pool=pool_n or None, tier=inputs["tier"])
        if not chain["fits"]:
            wanted = chain["wanted"]
            shots, plan, chain = P.fit_chain(state, directed, chain, pool_n, inputs["tier"], drop=drop)
            notes.append(f"{wanted} shots planned again as {len(shots)} longer ones: no object twice, and a pool of "
                         f"{pool_n} stills affords {chain['morphs']} morphs.")
        for shot in shots:  # the long-song chain renders every morph at the chain's length (dense.run_simple)
            shot["render_s"] = int(chain["clip_s"])
            shot["speed"] = round(chain["clip_s"] / max(float(shot.get("seconds") or 0.1), 0.1), 3)
    elif not cut_plan and pool_n and pool_n < len(shots) + 1:
        n = max(1, pool_n - 1)  # the desk's no_repeat guardrail: fewer, longer morphs rather than a still twice
        wanted = len(shots)
        shots, plan = P.shots_for({**state, "morph_count": n}, directed, drop=drop)
        if len(shots) > n:
            shots = P.stretch(shots[:n], duration)
        notes.append(f"Only {pool_n} stills in the pool: {len(shots)} longer morphs instead of {wanted}, so no still repeats.")
    elif cut_plan and pool_n and pool_n < len(shots) + 1:
        notes.append(f"{len(shots)} shots over a pool of {pool_n} stills: some objects show twice.")
    plan_drop = plan.get("drop") if plan.get("drop") is not None else None
    raw_effects = [copy.deepcopy(fx) for s in shots for fx in s.get("effects") or []]
    m = P.macros(state)
    styles = looks.styles_for(inputs["morph_style"], shots, plan_drop, m["chaos"])
    P.apply_macros(shots, m)
    looks.plan_timing(shots, inputs["morph_timing"], summary["beats"], plan_drop)
    chain_stills = stills.pick(inputs["vibe"], len(shots) + 1, idea=inputs["idea"], pins=pins, user_folder=inputs["user_folder"])
    rows = []
    for i, s in enumerate(shots):
        a, b = chain_stills[i], chain_stills[i + 1]
        speed_of = s.get("speed") if s.get("speed") is not None else float(s["render_s"]) / max(float(s["seconds"]), 0.1)
        row = {"index": i, "start": float(s["start"]), "end": float(s["end"]), "seconds": float(s["seconds"]),
               "frames": int(s["frames"]), "render_s": int(s["render_s"]), "speed": round(float(speed_of), 3),
               "ease": str(s.get("ease") or ""), "effects": s.get("effects") or [], "section": str(s.get("section") or ""),
               "song_section": _section_at(summary["sections"], float(s["start"])), "boundary": str(s.get("boundary") or ""),
               "fx_intensity": float(s.get("fx_intensity", 0.8)), "chaos": float(s.get("chaos", m["chaos"])),
               "style": styles[i] if i < len(styles) else "melt", "timing": s.get("timing"),
               "timing_mode": (s.get("timing") or {}).get("mode", "smooth"), "seed": inputs["seed"] + i, "hold": False,
               "from": a["noun"], "to": b["noun"], "from_file": a["file"], "to_file": b["file"],
               "length": looks.gen_length(looks.render_frames(s))}
        if s.get("wobble"):
            row["wobble"] = float(s["wobble"])
        rows.append(row)
    w, h = looks.PORTRAIT if inputs["aspect"] == "9:16" else (looks.WIDTH, looks.HEIGHT)
    board = {"schema": SCHEMA, "song": summary, "inputs": inputs, "vibe": inputs["vibe"], "vibe_name": looks.name_of(inputs["vibe"]),
             "pool_vibe": stills.pool_vibe(inputs["vibe"]), "fps": P.FPS, "size": [w, h], "aspect": inputs["aspect"],
             "out_size": list(looks.OUT_SIZE[inputs["aspect"]]), "seed": inputs["seed"], "engine": "ltx095",
             "plan": {"name": str(plan.get("name") or ("cut plan" if cut_plan else "flow")), "drop": plan_drop,
                      "long_song": long_song, "clip_s": int(chain["clip_s"]) if chain else None,
                      "cuts": [r["start"] for r in rows[1:]], "raw_effects": raw_effects},
             "stills": [{"index": k, "file": r["file"], "noun": r["noun"], "kind": r.get("kind", "object"), "path": r["path"],
                         **({"pinned": True} if r.get("pinned") else {}), **({"user": True} if r.get("user") else {})}
                        for k, r in enumerate(chain_stills)],
             "pool": [{"file": r["file"], "noun": r["noun"]} for r in pool_rows],
             "shots": rows, "notes": notes, "edits": None}
    return board


# ------------------------------------------------------------------------------------------------ the request a morph


def pair(board: dict, index: int) -> dict:
    """Everything one morph sends LTX 0.9.5, value for value ``cloud_morph._local_clips`` through the stock graph."""
    shots = board.get("shots") or []
    if not shots:
        raise P.CutPlanError("The storyboard has no shots.")
    if not 0 <= int(index) < len(shots):
        raise P.CutPlanError(f"Morph {index} is past the storyboard's {len(shots)} morphs (0 is the first, {len(shots) - 1} the last).")
    shot = shots[int(index)]
    a, b = board["stills"][int(index)], board["stills"][int(index) + 1]
    kinds = looks.pair_kinds(a, b)
    vibe = str(board.get("vibe") or "")
    tune = looks.tuned(vibe)
    comp_a, comp_b = looks.guide_compression(kinds, int(tune.get("img_compression", looks.GRAPH_DEFAULTS["img_compression"])))
    w, h = board.get("size") or [looks.WIDTH, looks.HEIGHT]
    return {"index": int(index), "shot": int(index), "from": a["noun"], "to": b["noun"], "image_a": a["path"], "image_b": b["path"],
            "file_a": a["file"], "file_b": b["file"], "prompt": looks.prompt_for(vibe, kinds, shot.get("style") or "melt"),
            "negative": looks.NEGATIVE, "width": int(w), "height": int(h), "length": int(shot["length"]),
            "frames": int(shot["frames"]), "seed": int(shot.get("seed", int(board.get("seed") or 2727) + int(index))),
            "steps": int(tune.get("steps", looks.STEPS)), "cfg": float(tune.get("cfg", looks.GRAPH_DEFAULTS["cfg"])),
            "compression_a": int(comp_a), "compression_b": int(comp_b),
            "guide_strength_b": float(tune.get("guide_end_strength", looks.GRAPH_DEFAULTS["guide_end_strength"])),
            "frame_rate": float(looks.FPS), "style": str(shot.get("style") or "melt"), "timing": shot.get("timing_mode", "smooth"),
            "start": shot["start"], "end": shot["end"], "hold": bool(shot.get("hold")), "aspect": board.get("aspect", "16:9"),
            "vibe": vibe, "engine": "ltx095"}


def summary(board: dict) -> str:
    song = board.get("song") or {}
    shots = board.get("shots") or []
    chain = " > ".join(s["noun"] for s in (board.get("stills") or [])[:8]) + (" > ..." if len(board.get("stills") or []) > 8 else "")
    styles: dict[str, int] = {}
    for s in shots:
        styles[s["style"]] = styles.get(s["style"], 0) + 1
    lines = [f"{len(shots)} shots on the beat over {float(song.get('duration') or 0):.1f} s of {song.get('name')}, "
             f"{len(shots)} morphs, {board.get('vibe_name')} ({board.get('plan', {}).get('name')})",
             f"Chain: {chain}", "Styles: " + ", ".join(f"{k} {v}" for k, v in styles.items())]
    if board.get("edits"):
        lines.append("Edited on the Morph Timeline.")
    lines += list(board.get("notes") or [])
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ the Morph Timeline's edits


def empty_edits(board: dict | None = None) -> dict:
    song = (board or {}).get("song") or {}
    return {"format": EDITS, "song_key": str(song.get("key") or ""), "cuts": None, "shots": {}, "intensity": [], "pins": []}


def parse_edits(text: str | dict | None) -> dict | None:
    """The Timeline widget's JSON, or None when it holds nothing (or something that is not an edit list)."""
    if not text:
        return None
    try:
        data = json.loads(text) if isinstance(text, str) else dict(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("format") != EDITS:
        return None
    return data


def has_edits(edits: dict | None) -> bool:
    return bool(edits) and bool(edits.get("cuts") is not None or edits.get("shots") or edits.get("intensity") or edits.get("pins"))


def _key(t: float) -> str:
    return f"{float(t):.3f}"


def _clean_cuts(cuts, duration: float) -> list[float]:
    out: list[float] = []
    for t in sorted(float(c) for c in cuts or [] if isinstance(c, (int, float)) or str(c).replace(".", "", 1).isdigit()):
        if 0.25 <= t <= duration - 0.25 and (not out or t - out[-1] >= 0.25):
            out.append(round(t, 4))
    return out


def cut_plan_from(board: dict, cuts: list[float]) -> dict:
    """The edited cuts as the desk's ``cut_plan``: each new shot keeps the play speed of the planned shot it starts in
    (so its morph renders as long as the plan would), its ease where it starts where a planned shot did, and the
    planner's effects that fall inside it (the knobs shape them again)."""
    duration = float(board["song"]["duration"])
    bounds = [0.0] + _clean_cuts(cuts, duration) + [round(duration, 4)]
    base = board.get("shots") or []
    effects = list((board.get("plan") or {}).get("raw_effects") or [])
    chain_s = (board.get("plan") or {}).get("clip_s") if (board.get("plan") or {}).get("long_song") else None
    shots = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        home = next((s for s in base if float(s["start"]) - 1e-6 <= a < float(s["end"])), base[-1] if base else None)
        ratio = float(home["render_s"]) / max(float(home["seconds"]), 0.1) if home else 1.0
        # a long song's chain renders every morph at its own length (dense.run_simple); a short clip's shot keeps the
        # play speed of the planned shot it starts in
        render_s = int(chain_s) if chain_s else P.snap_up(max(2.0, (b - a) * ratio - 0.15))
        ease = str(home.get("ease") or "") if home and abs(float(home["start"]) - a) < 1e-3 else ""
        fx = [dict(e) for e in effects if a - 1e-6 <= float(e.get("t", a)) < b]
        shot = {"start": round(a, 4), "end": round(b, 4), "render_s": render_s, "effects": fx}
        if ease:
            shot["ease"] = ease
        if home and home.get("section"):
            shot["section"] = home["section"]
        shots.append(shot)
    return {"name": "edited on the Morph Timeline", "drop": (board.get("plan") or {}).get("drop"), "shots": shots}


def _pins_from(edits: dict, bounds: list[float]) -> dict[int, str]:
    out: dict[int, str] = {}
    for item in edits.get("pins") or []:
        try:
            t, file = float(item[0]), str(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        slot = int(np.argmin([abs(b - t) for b in bounds]))
        out[slot] = file
    return out


def apply_edits(board: dict, edits: dict | None, song: dict | None = None) -> dict:
    """``board`` with the Timeline's ``edits`` laid over it. ``song`` (the analysis value) rebuilds the plan when cuts
    or pins changed; without it the board's own summary stands in (its beats and sections are what the planner reads)."""
    if not has_edits(edits):
        return board
    key = str((board.get("song") or {}).get("key") or "")
    if edits.get("song_key") and key and edits["song_key"] != key:
        out = copy.deepcopy(board)
        out["notes"] = list(out.get("notes") or []) + [
            "The Morph Timeline's edits were made for another song, so the plan stands. Open the timeline to edit this one."]
        return out
    duration = float(board["song"]["duration"])
    cuts = _clean_cuts(edits["cuts"], duration) if edits.get("cuts") is not None else [float(c) for c in board["plan"]["cuts"]]
    bounds = [0.0] + cuts + [duration]
    pins = _pins_from(edits, bounds)
    changed_cuts = edits.get("cuts") is not None and cuts != [round(float(c), 4) for c in board["plan"]["cuts"]]
    out = board
    if changed_cuts or pins:
        src = song or {"features": {"duration": duration, "beats": board["song"]["beats"], "sections": board["song"]["sections"],
                                    "tempo": board["song"]["tempo"], "frames": []},
                       "path": board["song"]["path"], "name": board["song"]["name"], "drop": board["song"]["drop"],
                       "key": board["song"]["key"], "engine": board["song"].get("engine", "")}
        kwargs = dict(board["inputs"])
        out = build(src, **kwargs, pins=pins or None, cut_plan=cut_plan_from(board, cuts) if changed_cuts else None)
        if not song:  # the rebuilt board keeps the strip's lanes the summary had
            out["song"] = copy.deepcopy(board["song"])
    else:
        out = copy.deepcopy(board)
    shots = out["shots"]
    timing_over: dict[int, dict] = {}
    for k, o in (edits.get("shots") or {}).items():
        try:
            t = float(k)
        except (TypeError, ValueError):
            continue
        i = next((j for j, s in enumerate(shots) if abs(float(s["start"]) - t) < 0.5 / P.FPS), None)
        if i is None or not isinstance(o, dict):
            continue
        s = shots[i]
        if o.get("style"):
            s["style"] = looks.normal_style(o["style"], allow_auto=False)
            s["style_set"] = True
        if o.get("timing"):
            timing_over[i] = {"timing": looks.normal_timing(o["timing"])}
        if o.get("hold") is not None:
            s["hold"] = bool(o["hold"])
        if o.get("seed") is not None:
            try:
                s["seed"] = int(o["seed"])
            except (TypeError, ValueError):
                pass
    if timing_over:
        plain = [{"start": s["start"], "end": s["end"], "hold": s.get("hold"), "timing": s.get("timing")} for s in shots]
        looks.plan_timing(plain, out["inputs"]["morph_timing"], out["song"]["beats"], out["plan"].get("drop"), timing_over)
        for s, p in zip(shots, plain):
            s["timing"] = p.get("timing")
            s["timing_mode"] = (p.get("timing") or {}).get("mode", "smooth")
    points = sorted((float(t), float(v)) for t, v in (edits.get("intensity") or []) if 0 <= float(v) <= 1)
    if points:
        ts, vs = [p[0] for p in points], [p[1] for p in points]
        for s in shots:
            s["fx_intensity"] = round(float(np.interp(float(s["start"]), ts, vs)), 3)
            s["intensity_set"] = True
    for s in shots:
        if s.get("hold"):
            s["timing"], s["timing_mode"] = None, "smooth"
    out["edits"] = copy.deepcopy(edits)
    return out


def signature(board: dict) -> str:
    """A short hash of what the renders depend on (the pairs, their prompts and lengths), for a cache or a log."""
    rows = [(s["from_file"], s["to_file"], s["style"], s["length"], s["seed"]) for s in board.get("shots") or []]
    return hashlib.sha1(json.dumps([board.get("vibe"), board.get("size"), rows]).encode("utf-8")).hexdigest()[:12]
