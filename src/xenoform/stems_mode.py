"""Stems mode: each stem its own layer, cut by the same planner on the stem's drive, composited by prominence.

Tys, 31 Oct: "a mode where i can apply a certain object/clip to a individual stems, and have them maybe overlap ... it
should follow the same rules but ... opacity may have to be adjusted or that can be a setting for how dominant or
prominent the stem is so if theres two scenes/stems running for example you can see both" (docs/STEMS_MODE.md; the
music-video plan's Stage 6; decision 10: an objects layer and a clips layer may run at once, never mixed within one).

A Make whose body says ``mode: "stems"`` carries ``layers``, up to ``MAX_LAYERS``, each
``{stem, kind, vibe, pins | clips, prominence, blend, lead}``:

- ``stem``: a stem of the song's split (drums, bass, vocals, other from Demucs; the band split's names; your own);
- ``kind``: "objects" (the vibe's stills, ``pins`` on the Chain row's slots) or "clips" (``clips``, ``clips_folder`` or
  ``own_id``: your clips, each morphing into the next as ``clip_cut`` cuts them); never both in one layer;
- ``prominence`` 0..1, how dominant the layer is, and ``blend`` (screen, normal, add, lighten, multiply), for the
  compositor (``stems_composite``);
- ``lead``: the layer whose stem sets the passages (its entrances and exits split the mix's sections); without one the
  mix's sections are the passages.

Each layer is its own cut (``dense.run_simple``, or ``clip_cut.run`` for clips) with the whole Make's knobs, Shape and
rules, on the song's shared passages; inside them the planner's shots are reshaped by the stem's drive (``drive``,
hooked into ``dense.shots_for`` by the ``stem_drive`` key): a stretch where the stem is silent becomes one invisible shot
(no morphs spent where nothing shows), a quiet stretch cuts half as often, a drop run's heat follows how hard the stem
plays it, and a drop's event stays only on a layer whose stem carries the drop. No still repeats across layers
(``avoid_stills``). The layers are laid together by ``stems_composite`` and the record is ``simple/simple.json`` with
``mode``, ``layers`` (each its own record under ``layers/<stem>/``), ``stems`` and ``composite``.
"""

from __future__ import annotations

import copy
import json
import logging
import math
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np
from fastapi import APIRouter, HTTPException

from xenoform import stems as _stems
from xenoform import stems_composite as SC

log = logging.getLogger("xenoform")

MODE = "stems"
MAX_LAYERS = 4
KINDS = ("objects", "clips")
STEM_NAMES = ("drums", "bass", "vocals", "other", "sub", "mid", "high")  # Demucs' four, the band split's
PROMINENCE_DEFAULT = 0.7
DRIVE_KEY = "stem_drive"     # the layer body's drive: {stem, fps, period, activity, onsets} (dense.shots_for reads it)
AVOID_KEY = "avoid_stills"   # the stills earlier layers used (morph_pass.pick_stills leaves them out)
AVOID_NOUNS_KEY = "avoid_nouns"  # ...and their objects by name: no orb in gold on one layer and an orb in glow on the next
LAYER_KEY = "stem_layer"
LAYERS_DIR = "layers"
SEED_STEP = 97               # each layer rolls its own dice
# the drive (plan section 7b): a shot's mean activity under SILENT (and its peak under SILENT_PEAK) is silence; under
# QUIET it is quiet (two quiet shots of a passage become one, at most QUIET_MAX_BEATS long); a drop's first beat with
# the stem at CARRY or more keeps the event; a drop run's heat is the run's times how hard the stem plays it (full at
# HEAT_FULL)
SILENT = 0.12
SILENT_PEAK = 0.3
QUIET = 0.4
QUIET_MAX_BEATS = 16
SPLIT_MIN_BEATS = 4          # the stem out this long (a bar, after its two-beat release) inside a shot: the layer cuts
                             # where it goes and where it comes back
CARRY = 0.35
HEAT_FULL = 0.8
HEAT_FLOOR = 0.2
LEAD_ACTIVE = 0.25           # a lead stem under this is out
LEAD_GAP_BARS = 2            # ...for at least this many bars: a passage of its own
COMPOSITE_BASE_S, COMPOSITE_S_PER_S = 4.0, 0.4  # the composite's ffmpeg pass, about, for job_timing's clock


# ------------------------------------------------------------------------------------------------ the body


def wants(state: dict | None) -> bool:
    """Whether this Make is a Stems cut."""
    return str((state or {}).get("mode") or "").strip().lower() == MODE


def _pins(raw) -> dict[str, str]:
    from xenoform import morph_pass as _mp

    return {str(k): v for k, v in _mp.pins_of({"chain_pins": raw}).items()}


def _clips(raw) -> list[str]:
    out = []
    for c in raw if isinstance(raw, (list, tuple)) else []:
        p = c.get("path") if isinstance(c, dict) else c
        if p:
            out.append(str(p))
    return out


def layers_of(raw, *, names: list[str] | None = None, vibe: str = "") -> tuple[list[dict], list[str]]:
    """The body's ``layers`` normalised: the rows that are on, one a stem, at most ``MAX_LAYERS``, each with its kind,
    vibe (the cut's when it names none: one palette), prominence, blend and at most one lead; objects keep their pins and
    clips their clips, never both. Returns the layers and the notes on what was changed or left out."""
    rows = raw if isinstance(raw, (list, tuple)) else []
    allowed = [str(n) for n in names] if names else list(STEM_NAMES)
    out: list[dict] = []
    notes: list[str] = []
    seen: set[str] = set()
    lead_taken = False
    for k, row in enumerate(rows):
        if not isinstance(row, dict):
            notes.append(f"layer {k + 1} is not a layer: left out")
            continue
        if row.get("on") is False or row.get("off") is True:
            continue
        stem = str(row.get("stem") or "").strip()
        if stem not in allowed:
            notes.append(f"layer {k + 1}: this song's stems are {', '.join(allowed)}, not {stem or 'nothing'}: left out")
            continue
        if stem in seen:
            notes.append(f"a second {stem} layer: one layer a stem, the first kept")
            continue
        if len(out) >= MAX_LAYERS:
            notes.append(f"the {stem} layer: {MAX_LAYERS} layers at most, left out")
            continue
        kind = str(row.get("kind") or "objects").strip().lower()
        if kind in ("clip", "your clips", "own"):
            kind = "clips"
        if kind not in KINDS:
            notes.append(f"the {stem} layer: no kind called {kind}; objects")
            kind = "objects"
        layer = {"stem": stem, "kind": kind, "vibe": str(row.get("vibe") or vibe or "").strip(),
                 "prominence": SC.prominence_of(row.get("prominence"), PROMINENCE_DEFAULT),
                 "blend": SC.blend_of(row.get("blend")), "lead": False}
        if row.get("lead"):
            if lead_taken:
                notes.append(f"the {stem} layer: one lead a cut, the first kept")
            else:
                layer["lead"] = lead_taken = True
        if kind == "objects":
            layer["pins"] = _pins(row.get("pins"))
            if row.get("clips") or row.get("clips_folder") or row.get("own_id"):
                notes.append(f"the {stem} layer is objects: its clips were left out (clips and objects never mix in a layer)")
        else:
            layer["clips"] = _clips(row.get("clips"))
            layer["clips_folder"] = str(row.get("clips_folder") or "").strip()
            layer["own_id"] = str(row.get("own_id") or "").strip()
            if row.get("pins"):
                notes.append(f"the {stem} layer is clips: its pinned stills were left out (clips and objects never mix in a layer)")
            if not (layer["clips"] or layer["clips_folder"] or layer["own_id"]):
                notes.append(f"the {stem} layer is clips but has none: choose its clips, or make it objects; left out")
                continue
        seen.add(stem)
        out.append(layer)
    return out, notes


def split_names(body: dict) -> list[str] | None:
    """The stems of the song's split when the body knows it (``stems_path``), else None."""
    raw = body.get("stems_path")
    if not raw:
        return None
    try:
        rec = json.loads(Path(str(raw)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    names = [str(n) for n in (rec.get("stems") or [])] if isinstance(rec, dict) else []
    return names or None


def describe(layers: list[dict]) -> str:
    """The layers in a line: "2 layers: drums as objects of liquid-gold (prominence 0.8, screen), ...; the passages are
    the mix's sections"."""
    bits = []
    for layer in layers:
        what = f"{layer['stem']} as {'your clips' if layer['kind'] == 'clips' else 'objects'}"
        if layer["kind"] == "objects" and layer.get("vibe"):
            what += f" of {layer['vibe']}"
        bits.append(f"{what} (prominence {layer['prominence']:g}, {layer['blend']})")
    lead = next((l["stem"] for l in layers if l.get("lead")), None)
    tail = f"the passages follow the {lead}" if lead else "the passages are the mix's sections"
    return f"{len(layers)} layer{'s' if len(layers) != 1 else ''}: {', '.join(bits)}; {tail}"


def guard(body: dict, rep) -> None:
    """``guardrails.apply``'s Stems check, in place: the layers validated (``layers_of``: structure, so even Expert keeps
    no broken layer), each refusal a ``[stems]`` line, then the layers in a line. A body that is not a Stems Make keeps no
    layers."""
    if not wants(body):
        body.pop("layers", None)
        return
    layers, notes = layers_of(body.get("layers"), names=split_names(body), vibe=str(body.get("vibe") or ""))
    for note in notes:
        rep.clamp("stems", note, hard=True)
    body["layers"] = layers
    if not layers:
        rep.warn("stems", "no layer is on: turn a stem on in the Stems step (the Make stops before it renders)")
        return
    if str(body.get("quality_tier") or "").lower() == "cloud" and any(l["kind"] == "clips" for l in layers):
        rep.warn("stems", "Cloud Final has no clips path: a clips layer stops this Make before anything is sent")
    rep.warn("stems", describe(layers))


def layer_body(parent: dict, layer: dict, k: int, *, avoid=(), avoid_nouns=(), drive: dict | None = None,
               own_images: bool = True, clips: list[dict] | None = None) -> dict:
    """The Make body of one layer: the whole Make's knobs, Shape and rules, with the layer's vibe, pins or clips (``clips``
    when the caller found them already), its own seed, no end card (the composite is the cut), no performer, the stem's
    drive and the stills (``avoid``) and objects (``avoid_nouns``) earlier layers took."""
    body = {key: copy.deepcopy(v) for key, v in parent.items()
            if key not in ("layers", "guardrails", DRIVE_KEY, AVOID_KEY, AVOID_NOUNS_KEY)}
    body["mode"] = "simple"
    body["vibe"] = layer.get("vibe") or str(parent.get("vibe") or "")
    body["seed"] = int(parent.get("seed") or 2727) + SEED_STEP * int(k)
    body["end_card"] = False
    body["beat_overlay"] = False
    body["performer"] = 0
    body[LAYER_KEY] = layer["stem"]
    if drive is not None:
        body[DRIVE_KEY] = drive
    if layer["kind"] == "clips":
        body["morph_source"] = "clips"
        body["own_clips"] = list(clips) if clips is not None else clips_for(layer)
        body["morph_targets"] = []
        body.pop("chain_pins", None)
    else:
        body["morph_source"] = "objects"
        body["own_clips"] = []
        body["chain_pins"] = dict(layer.get("pins") or {})
        body[AVOID_KEY] = sorted({str(f) for f in avoid if f})
        body[AVOID_NOUNS_KEY] = sorted({str(n).strip().lower() for n in avoid_nouns if str(n).strip()})
        if not own_images:  # your own images lead one layer's chain, not every layer's: no object twice
            body["morph_targets"] = []
    return body


def clips_for(layer: dict) -> list[dict]:
    """A clips layer's clips (``own_media.scan`` rows): its list, else its folder, else the files dropped on the desk."""
    from xenoform import own_media

    rows: list[dict] = []
    for p in layer.get("clips") or []:
        path = Path(str(p))
        if path.is_dir():
            rows.extend(own_media.scan(path)["clips"])
        elif path.is_file():
            try:
                from xenoform import footage

                rows.append({"path": str(path), "seconds": round(float(footage.probe_duration(str(path))), 3)})
            except Exception as exc:
                log.warning("clip %s unreadable: %s", path, exc)
    folder = str(layer.get("clips_folder") or "")
    if not rows and layer.get("own_id"):
        try:
            from xenoform import ui

            with ui._LOCK:
                dropped = ui._OWN.get(str(layer["own_id"]))
            folder = str(dropped) if dropped else folder
        except Exception:
            pass
    if not rows and folder:
        try:
            rows = own_media.scan(folder)["clips"]
        except FileNotFoundError:
            rows = []
    return rows


# ------------------------------------------------------------------------------------------------ the drive


def _span(curve: np.ndarray, a: float, b: float, fps: int) -> np.ndarray:
    i, j = int(round(a * fps)), int(round(b * fps))
    j = max(j, i + 1)
    part = curve[max(0, i):max(0, min(len(curve), j))]
    return part if part.size else np.zeros(1)


def _starts_passage(shots: list[dict], i: int) -> bool:
    return i == 0 or bool(shots[i].get("boundary")) or shots[i].get("passage") != shots[i - 1].get("passage") \
        or shots[i].get("section") != shots[i - 1].get("section")


def silences(curve: np.ndarray, fps: int, period: float, *, min_beats: float = SPLIT_MIN_BEATS) -> list[tuple[float, float]]:
    """The stretches (seconds) where the stem is out (activity under ``SILENT``) for ``min_beats`` beats or more."""
    out: list[tuple[float, float]] = []
    quiet = np.asarray(curve) < SILENT
    need = max(1, int(round(min_beats * period * fps)))
    k = 0
    while k < len(quiet):
        if not quiet[k]:
            k += 1
            continue
        j = k
        while j < len(quiet) and quiet[j]:
            j += 1
        if j - k >= need:
            out.append((k / fps, j / fps))
        k = j
    return out


def split_at_silences(shots: list[dict], cuts: list[float], period: float) -> list[dict]:
    """Shots cut where the stem goes out and where it comes back (``cuts``, on the beat): a piece under two beats folds
    back into its neighbour. A piece keeps the shot's passage and role; the first keeps its event and boundary and the
    effects before the next cut, the last its rest."""
    out: list[dict] = []
    least = 2.0 * period - 1e-6
    for s in shots:
        a, b = float(s["start"]), float(s["end"])
        inner = [c for c in cuts if a + least < c < b - least]
        if not inner:
            out.append(s)
            continue
        edges = [a] + inner + [b]
        for k, (x, y) in enumerate(zip(edges, edges[1:])):
            piece = copy.deepcopy(s)
            piece["start"], piece["end"], piece["seconds"] = round(x, 4), round(y, 4), round(y - x, 4)
            piece["_piece"] = True  # its render length is worked out again (drive)
            piece["effects"] = [fx for fx in (s.get("effects") or []) if x - 1e-6 <= float(fx.get("t", a)) < y - 1e-6]
            if k:
                for key in ("event", "boundary", "ease"):
                    piece.pop(key, None)
                piece["stem_cut"] = True  # a cut the stem made: where it went out or came back
            if k < len(edges) - 2:
                for key in ("rest", "rest_s"):
                    piece.pop(key, None)
                if piece.get("ease") == "out":
                    piece.pop("ease", None)
            out.append(piece)
    return out


def drive(got: tuple[list[dict], dict], state: dict, directed: dict | None = None) -> tuple[list[dict], dict]:
    """The planner's shots for a layer, reshaped by its stem's drive (``state["stem_drive"]``: the stem's activity a
    frame at ``fps`` and its onsets) inside the shared passages: silent stretches fold into one shot each
    (``stem_silent``, no effects, no event), two quiet shots of a passage become one (at most ``QUIET_MAX_BEATS``), a
    drop run's heat follows the stem, a drop's event and its punch stay only where the stem carries the drop. Every shot
    says how active its stem is (``stem_activity``). The plan gains ``stem_drive``, what the drive did."""
    shots, plan = got
    d = state.get(DRIVE_KEY) if isinstance(state.get(DRIVE_KEY), dict) else {}
    curve = np.asarray(d.get("activity") or [], dtype=np.float64)
    if not shots or not curve.size:
        return shots, plan
    from xenoform import dense
    from xenoform import pacing as _pc
    from xenoform.cloud_morph import FPS

    fps = int(d.get("fps") or 24)
    period = float(d.get("period") or 0.5)
    onsets = sorted(float(t) for t in d.get("onsets") or [])
    # where the stem goes out and comes back, on the song's beats: the layer cuts there (the silence becomes a shot
    # of its own, the return a fresh morph) whatever the planner's shots were
    beats = sorted(float(b) for b in ((directed or {}).get("beats") or []))
    out_runs = silences(curve, fps, period)

    def up(t: float) -> float:  # the first beat at or after t: the silent piece holds nothing but silence
        later = [x for x in beats if x >= t - 1e-6]
        return later[0] if later else math.ceil(t / period - 1e-9) * period

    def down(t: float) -> float:  # the last beat at or before t: the return starts on its beat
        earlier = [x for x in beats if x <= t + 1e-6]
        return earlier[-1] if earlier else math.floor(t / period + 1e-9) * period

    cuts = sorted({round(x, 4) for a, b in out_runs for x in (up(a), down(b)) if up(a) < down(b) - 1e-6})
    n_planned = len(shots)
    shots = split_at_silences(shots, cuts, period)
    n = len(shots)
    mean = [float(_span(curve, float(s["start"]), float(s["end"]), fps).mean()) for s in shots]
    peak = [float(_span(curve, float(s["start"]), float(s["end"]), fps).max()) for s in shots]
    entry = [float(_span(curve, float(s["start"]), float(s["start"]) + period, fps).mean()) for s in shots]
    silent = [m < SILENT and p < SILENT_PEAK for m, p in zip(mean, peak)]
    quiet = [not silent[i] and mean[i] < QUIET for i in range(n)]
    carries = [s.get("event") == "drop" and entry[i] >= CARRY for i, s in enumerate(shots)]
    groups: list[list[int]] = []
    i = 0
    while i < n:
        if silent[i]:
            j = i
            while j + 1 < n and silent[j + 1]:
                j += 1
            groups.append(list(range(i, j + 1)))
            i = j + 1
            continue
        if (quiet[i] and i + 1 < n and quiet[i + 1] and not _starts_passage(shots, i + 1) and not carries[i + 1]
                and not shots[i + 1].get("stem_cut")  # never across a cut the stem made (where it came back)
                and (float(shots[i + 1]["end"]) - float(shots[i]["start"])) <= QUIET_MAX_BEATS * period + 1e-6):
            groups.append([i, i + 1])
            i += 2
            continue
        groups.append([i])
        i += 1
    out: list[dict] = []
    kept = dropped = 0
    silent_s = 0.0
    for g in groups:
        a, b = shots[g[0]], shots[g[-1]]
        s = copy.deepcopy(a)
        start, end = float(a["start"]), float(b["end"])
        s["end"] = round(end, 4)
        s["seconds"] = round(end - start, 4)
        s["frames"] = int(sum(int(shots[x].get("frames") or 0) for x in g))
        s["effects"] = [fx for x in g for fx in (shots[x].get("effects") or [])]
        for key in ("rest", "rest_s"):  # a rest is the end of a shot: the merged shot rests where the later one did
            s.pop(key, None)
            if b.get(key) is not None:
                s[key] = b[key]
        if b.get("ease") == "out":
            s["ease"] = "out"
        act = float(_span(curve, start, end, fps).mean())
        s["stem_activity"] = round(act, 3)
        s["stem_onsets"] = sum(1 for t in onsets if start <= t < end)
        if all(silent[x] for x in g):
            s["stem_silent"] = True
            s["effects"] = []
            for key in ("event", "ramp", "rest", "rest_s"):
                s.pop(key, None)
            if s.get("heat") is not None:
                s["heat"] = 0.0
            if s.get("boundary") == "drop":
                s["boundary"] = "switch"
            silent_s += end - start
            if a.get("event") == "drop":
                dropped += 1
        else:
            if s.get("heat") is not None:
                s["heat"] = round(max(HEAT_FLOOR, min(1.0, float(s["heat"]) * min(1.0, act / HEAT_FULL))), 3)
            if a.get("event") == "drop":
                if carries[g[0]]:
                    kept += 1
                else:  # the stem does not carry this drop: the event and its punch belong to another layer
                    dropped += 1
                    s.pop("event", None)
                    t0 = float(a["start"])
                    s["effects"] = [fx for fx in s["effects"] if not (fx.get("type") in ("punch", "stutter") and abs(float(fx.get("t", -1)) - t0) < 1e-3)]
                    if s.get("boundary") == "drop":
                        s["boundary"] = "switch"
            elif s.get("event") in ("style", "kind") and act < QUIET:
                s.pop("event", None)
        if len(g) > 1 or any(shots[x].get("_piece") for x in g):
            render_s = dense._render_s(end - start, _pc.SPEED.get(str(s.get("section") or ""), 1.25))
            s["render_s"] = int(render_s)
            s["speed"] = round(render_s / max(end - start, 1e-3), 3)
        s.pop("_piece", None)
        out.append(s)
    edges = [int(round(float(s["start"]) * FPS)) for s in out] + [int(round(float(out[-1]["end"]) * FPS))]
    for k, s in enumerate(out):
        s["index"] = k
        s["frames"] = max(1, edges[k + 1] - edges[k])
    summary = {"stem": str(d.get("stem") or ""), "shots_in": n_planned, "shots_out": len(out), "silent_s": round(silent_s, 3),
               "drops_kept": kept, "drops_left": dropped, "cuts": cuts,
               "active": round(float((curve >= 0.25).mean()), 3)}
    plan = {**plan, "shots": [{k: v for k, v in s.items() if k not in ("index", "frames", "seconds")} for s in out],
            "stem_drive": summary}
    return out, plan


def lead_sections(directed: dict, curve, fps: int = 24) -> list[dict]:
    """The passages when a layer leads: the mix's roles (as the planner reads them), split where the lead stem goes out
    for ``LEAD_GAP_BARS`` bars or more (its edges on the nearest beat); a stretch it is out is a passage of its own, a
    release (the breakdown), and every section carries its role so the planner keeps them as they are."""
    from xenoform import dense
    from xenoform import pacing as _pc

    duration = float(directed.get("duration") or 0.0)
    beats = sorted(float(b) for b in directed.get("beats") or [])
    period = _stems.period_of(beats)
    sections = dense._analysis_sections(directed)
    rows = dense._story_roles(sections, duration, min_len=max(6.0, 8 * period)) if sections else \
        [{"start": 0.0, "end": duration, "label": "calm", "level": 0.5, "role": "calm"}]
    curve = np.asarray(curve or [], dtype=np.float64)
    out_runs: list[tuple[float, float]] = []
    if curve.size:
        quiet = curve < LEAD_ACTIVE
        k = 0
        need = LEAD_GAP_BARS * 4 * period * fps
        while k < len(quiet):
            if quiet[k]:
                j = k
                while j < len(quiet) and quiet[j]:
                    j += 1
                if j - k >= need:
                    out_runs.append((k / fps, min(duration, j / fps)))
                k = j
            else:
                k += 1

    def snap(t: float) -> float:
        return min(beats, key=lambda b: abs(b - t)) if beats else t

    cuts = sorted({round(snap(t), 4) for a, b in out_runs for t in (a, b) if 0.05 < snap(t) < duration - 0.05})
    pieces: list[dict] = []
    for r in rows:
        a, b = float(r["start"]), float(r["end"])
        inner = [c for c in cuts if a + 1e-6 < c < b - 1e-6]
        for x, y in zip([a] + inner, inner + [b]):
            pieces.append({**r, "start": round(x, 4), "end": round(y, 4)})
    out: list[dict] = []
    for p in pieces:
        mid = (float(p["start"]) + float(p["end"])) / 2.0
        if any(a - 1e-6 <= mid < b + 1e-6 for a, b in out_runs) and p["role"] not in ("intro", "outro"):
            p = {**p, "role": "release", "label": "release", "level": round(float(p.get("level") or 0.5) * 0.6, 4), "lead_out": True}
        if out and out[-1]["role"] == p["role"] and bool(out[-1].get("lead_out")) == bool(p.get("lead_out")):
            out[-1]["end"] = p["end"]
        else:
            out.append(dict(p))
    for p in out:
        p.setdefault("label", p["role"])
        if p["role"] not in _pc.PROFILE and p["role"] not in dense.STORY_BEATS:
            p["role"] = "calm"
    return out


# ------------------------------------------------------------------------------------------------ the run


def _label(stem: str) -> str:
    return str(stem)[:1].upper() + str(stem)[1:]


def _tier_of(opt: dict) -> str:
    return "cloud" if opt.get("cloud") else "fast" if opt.get("fast") else str(opt.get("tier") or "draft")


def layer_report(report: Callable[[str, float, str], None], k: int, n: int, stem: str, tier: str = "draft", *,
                 recut: bool = False) -> Callable:
    """A layer's progress folded into the Make's: every layer's morphs and its cut count as the morphs phase, layer by
    layer (job_timing's range for the tier), the detail naming the layer. A re-cut's layers are the assemble stage."""
    from xenoform import job_timing

    rng = job_timing.RANGES["morphs"]
    lo, hi = rng.get(tier, rng["draft"]) if isinstance(rng, dict) else rng
    stage_out = "restyle"
    if recut:
        stage_out, lo, hi = "assemble", 0.05, 0.6

    def sub(stage: str, frac: float, detail: str) -> None:
        f = max(0.0, min(1.0, float(frac or 0.0)))
        if recut:
            g = f
        else:
            g = 0.65 * f if stage == "restyle" else 0.65 + 0.35 * max(0.0, min(1.0, (f - 0.6) / 0.38)) if stage == "assemble" else 0.0
        overall = (k + min(1.0, g)) / max(1, n)
        text = str(detail or "").replace("your clip", "the clip")  # job_timing reads "your clip" as the cut phase
        report(stage_out, lo + (hi - lo) * overall, f"{_label(stem)} layer ({k + 1} of {n}): {text}")

    return sub


def _stems_json(state: dict, audio_path: Path, report: Callable, cancel: Callable[[], bool] | None) -> Path:
    """The song's split: the body's (the desk sets ``stems_path``), else the cached one, else split now (CPU) and waited for."""
    from xenoform import stems_api

    raw = state.get("stems_path")
    if raw and Path(str(raw)).is_file():
        return Path(str(raw))
    found = stems_api.stems_path_for(audio_path)
    if found is not None:
        return found
    engine = _stems.engine_of(state.get("stems_engine"))
    report("restyle", 0.0, "Splitting the stems first (on the CPU; no GPU, no queue)")
    st = _stems.start(audio_path, engine=engine, build=False)  # the Make works the curves out itself, next
    while st.get("status") in ("queued", "running") and st.get("stage") == "split":
        if cancel and cancel():
            from xenoform.turbo import JobCancelled

            raise JobCancelled("Cancelled. The card changed.")
        report("restyle", 0.0, f"Splitting the stems ({int(100 * float(st.get('progress') or 0.0))} %, about {int(st.get('eta_s') or 0)} s left)")
        time.sleep(1.0)
        st = _stems.status(audio_path, build=False)
    found = stems_api.stems_path_for(audio_path)
    if found is None:
        raise RuntimeError(f"The stems did not split ({st.get('error') or 'no stems file'}), so there are no layers to cut.")
    return found


def _chain_nouns(layer_dir: Path) -> list[str]:
    """The objects a layer's chain morphed through (its ``chain.json``; a clips layer's clips are not objects)."""
    try:
        rows = json.loads((Path(layer_dir) / "simple" / "chain.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(r.get("noun") or "").strip().lower() for r in rows if isinstance(r, dict) and r.get("kind") != "clip" and r.get("noun")]


def _size_of(info: dict) -> tuple[int, int]:
    if info.get("size"):
        return int(info["size"][0]), int(info["size"][1])
    w, h = str(info.get("render") or "540x960").split("x")
    return int(w), int(h)


def run(directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
        report: Callable[[str, float, str], None], *, cancel: Callable[[], bool] | None = None, client=None,
        engine: str | None = None) -> dict:
    """Render a Stems Make: each layer its own cut under ``<job>/layers/<stem>/`` (the planner on the stem's drive), then
    the composite into ``out_path``; writes and returns the record (``<job>/simple/simple.json``)."""
    from xenoform import dense
    from xenoform import guardrails as _guard
    from xenoform import pacing as _pc

    started = time.perf_counter()
    audio_path, out_path, job = Path(audio_path), Path(out_path), Path(work)
    layers, notes = layers_of(state.get("layers"), vibe=str(state.get("vibe") or ""))
    if not layers:
        raise RuntimeError("Stems mode needs a layer: turn at least one stem on in the Stems step, then Make. Nothing was rendered.")
    opt = dense.options(state)
    if opt["cloud"] and any(l["kind"] == "clips" for l in layers):
        raise RuntimeError("Cloud Final morphs the library's objects, not your clips yet: make the clips layer objects, or pick "
                           "Draft, Fast Final or Final. Nothing was sent.")
    clip_rows = {l["stem"]: clips_for(l) for l in layers if l["kind"] == "clips"}
    empty = [s for s, rows in clip_rows.items() if not rows]
    if empty:
        raise RuntimeError(f"The {', '.join(empty)} layer is clips but its clips were not found: choose its folder again. "
                           "Nothing was rendered.")
    stems_json = _stems_json(state, audio_path, report, cancel)
    split = json.loads(stems_json.read_text(encoding="utf-8"))
    beats = list(directed.get("beats") or [])
    period = _stems.period_of(beats)
    act = _stems.activity_for(stems_json, fps=24, period=period)
    missing = [l["stem"] for l in layers if l["stem"] not in (act.get("stems") or [])]
    if missing:
        raise RuntimeError(f"This song's split has no {', '.join(missing)} stem (it has {', '.join(act.get('stems') or [])}): "
                           "pick a stem it has. Nothing was rendered.")
    duration = float(directed.get("duration") or 0.0)
    lead = next((l for l in layers if l.get("lead")), None)
    layer_directed = directed
    if lead is not None:
        layer_directed = {k: v for k, v in directed.items() if k != "analysis_sections"}
        layer_directed["sections"] = lead_sections(directed, act["activity"][lead["stem"]], 24)
    n = len(layers)
    tier = _tier_of(opt)
    report("restyle", 0.05, f"{describe(layers)}. {n} cut{'s' if n != 1 else ''} to render, then laid together")
    used: list[str] = []
    used_nouns: list[str] = []
    first_objects = next((k for k, l in enumerate(layers) if l["kind"] == "objects"), None)
    made: list[dict] = []
    (job / "simple").mkdir(parents=True, exist_ok=True)
    for k, layer in enumerate(layers):
        stem = layer["stem"]
        drive_info = {"stem": stem, "fps": 24, "period": round(period, 4), "activity": act["activity"][stem],
                      "onsets": (act.get("onsets") or {}).get(stem) or []}
        body = layer_body(state, layer, k, avoid=used, avoid_nouns=used_nouns, drive=drive_info,
                          own_images=(k == first_objects), clips=clip_rows.get(stem))
        expert = bool((state.get("guardrails") or {}).get("expert")) if isinstance(state.get("guardrails"), dict) else False
        body, guard_rep = _guard.apply(body, expert=expert, duration=duration or None, beats=beats)
        body[DRIVE_KEY] = drive_info  # guardrails copies the body: the drive rides on unchanged
        ldir = job / LAYERS_DIR / stem
        ldir.mkdir(parents=True, exist_ok=True)
        info = dense.run_simple(layer_directed, audio_path, ldir / "xenoform.mp4", ldir, cfg, body,
                                layer_report(report, k, n, stem, tier), cancel=cancel, client=client, engine=engine)
        used.extend(str(f) for f in info.get("stills") or [])
        used_nouns.extend(_chain_nouns(ldir))
        if k == 0 and (ldir / "simple" / "chain.json").is_file():  # the making screen's chain: the first layer's
            shutil.copyfile(ldir / "simple" / "chain.json", job / "simple" / "chain.json")
        made.append({"layer": layer, "info": info, "guardrails": list(guard_rep.get("messages") or []), "dir": ldir})
    first = made[0]["info"]
    fps = int(first.get("fps") or 24)
    size = _size_of(first)
    frames = min(int(m["info"].get("frames") or 0) for m in made)
    comp_act = act if fps == 24 else _stems.activity_for(stems_json, fps=fps, period=period)
    SC.write_curves(job, {m["layer"]["stem"]: comp_act["activity"][m["layer"]["stem"]] for m in made}, fps=fps, frames=frames,
                    source={"stems_json": str(stems_json), "period": round(period, 4), "version": _stems.ACTIVITY_VERSION,
                            "split_engine": split.get("engine")})
    layers_rec = []
    for m in made:
        layer, info, ldir = m["layer"], m["info"], m["dir"]
        shots = info.get("shots") or []
        layers_rec.append({**layer, "vibe": str(info.get("vibe") or layer.get("vibe") or ""),
                           "folder": str(ldir), "record": str(ldir / "simple" / "simple.json"), "video": str(ldir / "xenoform.mp4"),
                           "engine": info.get("engine"), "shots": len(shots), "morphs": len({str(c) for c in info.get("clips") or []}),
                           "stills": list(info.get("stills") or []), "silent_s": round(sum(float(s.get("seconds") or 0.0) for s in shots if s.get("stem_silent")), 3),
                           "drops_kept": sum(1 for s in shots if s.get("event") == "drop"), "guardrails": m["guardrails"],
                           "plan_line": str(((info.get("pacing") or {}).get("line")) or "")})
    rec = {"mode": MODE, "folder": str(job), "engine": f"{n} layer{'s' if n != 1 else ''} ({first.get('engine')}), laid together here",
           "tier": opt["tier"], "fast": bool(opt["fast"]), "cloud": bool(opt["cloud"]), "open_weights": True,
           "energy": opt["energy"], "aspect": opt["aspect"], "fx": opt["fx"], "vibe": str(state.get("vibe") or layers[0].get("vibe") or ""),
           "plan_name": MODE, "audio_path": str(audio_path), "beats": [round(float(b), 4) for b in beats],
           "duration": round(duration, 3), "fps": fps, "size": list(size), "render": f"{size[0]}x{size[1]}", "steps": None,
           "stems": {"engine": split.get("engine"), "path": str(stems_json), "hash": stems_json.parent.name,
                     "names": list(act.get("stems") or []), "activity": str(stems_json.with_name(_stems.ACTIVITY_FILE)),
                     "period": round(period, 4), "sliced_from": split.get("sliced_from")},
           "layers": layers_rec, "lead": lead["stem"] if lead else None,
           "sections": list(layer_directed.get("sections") or []) if lead else None,
           "recut_state": dict((first.get("recut_state") or {})), "window": dense.window_of(state, duration),
           "fallbacks": [{"stems": n_} for n_ in notes], "recuts": 0, "composites": 0}
    rec["composite"] = SC.section(layers_rec, fps=fps, size=size, frames=frames, audio=str(audio_path))
    rec["composite"] = SC.build(job, rec, out=out_path, report=report)
    if opt["end_card"]:
        from xenoform import beatfx

        report("assemble", 0.96, "Burning the end card")
        rec["end_card"] = beatfx.end_card(out_path, opt["recipe"] or "(none)")
    lines = [f"{m['layer']['stem']} {len(m['info'].get('shots') or [])} shots" for m in made]
    pace = _pc.record({}, first.get("shots") or [], state, rec["window"])
    rec["pacing"] = {**pace, "line": f"{n} layers ({', '.join(lines)})" + (f"; {first['pacing']['line']}" if (first.get('pacing') or {}).get('line') else "")}
    rec["frames"] = int(rec["composite"].get("frames") or frames)
    rec["seconds"] = round(time.perf_counter() - started, 2)
    (job / "simple" / "simple.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    report("assemble", 0.98, "Saving the video")
    return rec


# ------------------------------------------------------------------------------------------------ the re-cut


def read_record(job_dir: Path) -> dict:
    path = Path(job_dir) / "simple" / "simple.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    if not wants(rec):
        raise ValueError("This cut is not a Stems cut.")
    return rec


def recut(job_dir: Path, overrides: dict | None = None, report: Callable[[str, float, str], None] | None = None,
          cfg: dict | None = None) -> dict:
    """Re-cut a Stems cut from its cached morphs (no GPU). The knobs (``macros``, ``breathe``, the look ...) are one
    setting for every layer; the timeline's maps (``shot_overrides``, ``boundary_overrides``) are the layer's that
    ``layer`` names (without a layer they are left out). Only the layers something changed for are re-cut: the named
    layer, and every layer when knobs came. ``prominence`` and ``blend`` ({stem: value}) change the composite. Then the
    layers are laid together again and the record written back."""
    from xenoform import dense

    job_dir = Path(job_dir)
    rec = read_record(job_dir)
    raw = dict(overrides or {})
    layer = raw.pop("layer", None)
    prominence = raw.pop("prominence", None)
    blend = raw.pop("blend", None)
    maps = {k: raw.pop(k) for k in ("shot_overrides", "boundary_overrides") if k in raw}
    by_stem = {str(l["stem"]): l for l in rec.get("layers") or []}
    if layer is not None and str(layer) not in by_stem:
        raise ValueError(f"This cut has no {layer} layer; its layers are {', '.join(by_stem)}.")
    work: list[tuple[dict, dict]] = []
    for stem, l in by_stem.items():
        if layer is not None and stem == str(layer):
            work.append((l, {**raw, **maps}))
        elif raw:
            work.append((l, dict(raw)))
    for k, (l, over) in enumerate(work):
        sub = layer_report(report, k, len(work), l["stem"], recut=True) if report else None
        dense.recut_from_cache(Path(str(l["folder"])), over, report=sub, cfg=cfg)
    comp = dict(rec.get("composite") or {})
    if isinstance(prominence, dict):
        comp["prominence"] = {**(comp.get("prominence") or {}), **{str(s): SC.prominence_of(v) for s, v in prominence.items() if str(s) in by_stem}}
    if isinstance(blend, dict):
        comp["blends"] = {**(comp.get("blends") or {}), **{str(s): SC.blend_of(v) for s, v in blend.items() if str(s) in by_stem}}
    rec["layers"] = [{**l, "prominence": (comp.get("prominence") or {}).get(str(l["stem"]), l.get("prominence")),
                      "blend": (comp.get("blends") or {}).get(str(l["stem"]), l.get("blend"))} for l in rec.get("layers") or []]
    comp["order"] = SC.order_of(rec["layers"])
    rec["composite"] = comp
    rec["composite"] = SC.build(job_dir, rec, report=report)
    for l in rec["layers"]:  # what each layer's record now says
        try:
            lrec = json.loads(Path(str(l["record"])).read_text(encoding="utf-8"))
            l["shots"] = len(lrec.get("shots") or [])
            l["recuts"] = int(lrec.get("recuts") or 0)
        except (OSError, ValueError):
            pass
    rec["recuts"] = int(rec.get("recuts") or 0) + 1
    if raw:
        rec["recut_state"] = {**(rec.get("recut_state") or {}), **{k: v for k, v in raw.items() if k not in ("shot_overrides", "boundary_overrides")}}
    (job_dir / "simple" / "simple.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


def timing(plan: dict, body: dict, duration: float) -> dict:
    """``job_timing.plan_for``'s phases for a Stems Make: every layer's morphs and cut in the morphs phase (one cut's worth
    a layer), the composite as the cut."""
    n = max(1, len([l for l in body.get("layers") or [] if isinstance(l, dict) and l.get("on") is not False]))
    out = dict(plan)
    out["morphs"] = round(n * (float(plan.get("morphs") or 0.0) + float(plan.get("cut") or 0.0)), 1)
    out["cut"] = round(COMPOSITE_BASE_S + COMPOSITE_S_PER_S * float(duration), 1)
    return out


# ------------------------------------------------------------------------------------------------ the lane


def lane(info: dict, video_id: str = "") -> dict:
    """The timeline of a Stems cut: every layer's own lane (``lane.build`` of its record; its own shot and boundary
    overrides, swaps and re-renders not yet), stacked with its stem's envelope and its alpha as drawn curves; the top
    level is the first layer's lane, so the timeline opens on it."""
    from xenoform import lane as _lane

    folder = Path(str(info.get("folder") or ""))
    try:
        curves = SC.read_curves(folder)
    except (OSError, ValueError):
        curves = {}
    comp = info.get("composite") or {}
    frames = int(comp.get("frames") or curves.get("frames") or 0)
    acts = curves.get("activity") or {}
    layers = [dict(l) for l in info.get("layers") or []]
    for l in layers:
        l["prominence"] = (comp.get("prominence") or {}).get(str(l["stem"]), l.get("prominence"))
        l["blend"] = (comp.get("blends") or {}).get(str(l["stem"]), l.get("blend"))
    lay = SC.alphas(layers, acts, frames, solo=bool(comp.get("solo", SC.SOLO))) if frames and layers else {}
    rows = []
    for l in layers:
        try:
            lrec = json.loads(Path(str(l.get("record") or "")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lrec = {}
        ln = _lane.build(lrec, video_id)
        ln.update({"swappable": False, "rerenderable": False, "layer": l["stem"], "mode": MODE,
                   "tl_key": f"{video_id}:{l['stem']}"})
        rows.append({"stem": l["stem"], "kind": l.get("kind"), "vibe": l.get("vibe"), "prominence": l.get("prominence"),
                     "blend": l.get("blend"), "lead": bool(l.get("lead")), "shots": len(ln.get("shots") or []),
                     "silent_s": l.get("silent_s"), "drops_kept": l.get("drops_kept"),
                     "envelope": _stems.envelope(acts.get(str(l["stem"])) or []),
                     "alpha": _stems.envelope(list(lay.get(str(l["stem"]), []))), "lane": ln})
    top = dict(rows[0]["lane"]) if rows else {"shots": [], "sections": [], "overlays": []}
    top.update({"id": video_id, "mode": MODE, "layers": rows, "layer": rows[0]["stem"] if rows else None,
                "order": list(comp.get("order") or []), "blends": dict(comp.get("blends") or {}),
                "prominence": dict(comp.get("prominence") or {}), "composite_sha256": comp.get("sha256"),
                "plan_line": str(((info.get("pacing") or {}).get("line")) or top.get("plan_line") or "")})
    return top


# ------------------------------------------------------------------------------------------------ the routes

router = APIRouter()


def _period_for(audio_id: str) -> float:
    try:
        from xenoform import ui

        with ui._LOCK:
            feats = ui._FEATURES.get(audio_id) or {}
        return _stems.period_of(feats.get("beats") or [])
    except Exception:
        return 0.5


def _public(st: dict) -> dict:
    return {k: v for k, v in st.items() if k not in ("path",)}


@router.post("/api/stems/split")
def split_route(body: dict | None = None) -> dict:
    """Split stems (the Stems step's button): starts the song's split on the CPU in the background (Demucs, else the
    band split; cached by song hash, one at a time) and its envelopes after it; answers the status at once (``status``
    queued / running / done / error, ``stage`` split then envelopes, ``progress`` and ``eta_s`` while it runs, ``stems``
    with an envelope a stem when done). ``{"audio_id"}`` or ``{"path"}``, optional ``engine``. No GPU, no queue."""
    from xenoform import stems_api

    body = body or {}
    song = stems_api.resolve_song(body)
    audio_id = str(body.get("audio_id") or "demo")
    st = _stems.start(song, engine=body.get("engine"), period=_period_for(audio_id))
    return {**_public(st), "audio_id": audio_id}


@router.get("/api/stems/status")
def status_route(audio_id: str = "", path: str = "") -> dict:
    """The Stems step's poll: ``split_route``'s answer without starting a split (the envelopes are built once the split
    is there)."""
    from xenoform import stems_api

    song = stems_api.resolve_song({"audio_id": audio_id, "path": path})
    st = _stems.status(song, period=_period_for(audio_id))
    return {**_public(st), "audio_id": audio_id or "demo"}


@router.post("/api/jobs/{job_id}/composite")
def composite_route(job_id: str, body: dict | None = None) -> dict:
    """Re-composite a finished Stems cut with new ``prominence`` and ``blend`` ({stem: value}): the layers are laid
    together again from their files and the curves (seconds, no GPU, no re-cut); the job runs like a re-cut."""
    from xenoform import ui

    body = body or {}
    folder = ui.work_dir() / "jobs" / ui.storage_id(job_id, fallback="")
    path = folder / "simple" / "simple.json"
    if not path.is_file() or not (folder / "xenoform.mp4").is_file():
        raise HTTPException(404, "No such video.")
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise HTTPException(400, "This cut's record did not read.") from None
    if not wants(rec):
        raise HTTPException(400, "This cut is not a Stems cut: it has one picture, not layers to lay again.")
    stems_in = {str(l["stem"]) for l in rec.get("layers") or []}
    prominence = body.get("prominence") if isinstance(body.get("prominence"), dict) else {}
    blend = body.get("blend") if isinstance(body.get("blend"), dict) else {}
    unknown = sorted({str(s) for s in list(prominence) + list(blend)} - stems_in)
    if unknown:
        raise HTTPException(400, f"This cut has no {', '.join(unknown)} layer; its layers are {', '.join(sorted(stems_in))}.")
    bad = [str(v) for v in blend.values() if str(v).strip().lower() not in SC.BLENDS]
    if bad:
        raise HTTPException(400, f"No blend called {bad[0]}; one of {', '.join(SC.BLENDS)}.")
    with ui._LOCK:
        job = ui._JOBS.get(job_id)
        if job is None:
            job = {"id": job_id, "status": "done", "stage": "done", "progress": 1.0, "detail": "Reopened", "video_version": 0,
                   "video": f"/api/jobs/{job_id}/video?v=0", "path": str(folder / "xenoform.mp4"), "error": None}
            ui._JOBS[job_id] = job
        if job.get("status") == "running":
            raise HTTPException(409, "That video is still rendering.")
        job.update({"status": "running", "stage": "assemble", "progress": 0.05, "error": None,
                    "detail": "Laying the layers together again (no GPU)"})

    def on_progress(stage: str, frac: float, detail: str) -> None:
        with ui._LOCK:
            job.update({"stage": stage, "progress": float(frac), "detail": detail})

    def go() -> None:
        try:
            out = SC.rebuild(folder, prominence=prominence, blend=blend, report=on_progress)
            with ui._LOCK:
                version = int(job.get("video_version") or 0) + 1
                job.update({"status": "done", "stage": "done", "progress": 1.0, "video_version": version,
                            "video": f"/api/jobs/{job_id}/video?v={version}", "detail": "Laid together again",
                            "composites": out.get("composites")})
        except Exception as exc:
            log.exception("composite %s", job_id)
            from xenoform.errors import plain_error

            with ui._LOCK:
                job.update({"status": "done", "stage": "done", "progress": 1.0, "error": None,
                            "detail": f"The layers were not laid again. {plain_error(exc)}"})

    threading.Thread(target=go, name=f"composite-{job_id}", daemon=True).start()
    return {"id": job_id, "status": "running"}
