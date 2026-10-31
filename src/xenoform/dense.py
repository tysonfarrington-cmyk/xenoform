"""Simple mode's open-weights finishing pass: energy presets, aspect, Final tier, clean export.

``flow``  (default) one morph per ~5 s on the beat grid, the Simple cut people know.
``dense`` the demo1 cut, ported from the agent script into the app: a shot per bar
          before the drop and a shot per half bar after it, up to 15 morphs, with
          holds, stutters, punches and beat-reactive FX. Everything after the
          renders is free CPU post-processing.

Same cut-plan format as Cloud quality (``cloud_morph.custom_shots``), so a plan made
for one engine renders on the other, but this module never touches a partner node:
clips come from LTX 0.9.5 (Draft) or LTX-2.3 fp8 (Final) on this machine.
"""

from __future__ import annotations

import json
import math
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from xenoform import beatfx
from xenoform.cloud_morph import (FPS, ALLOWED_S, CutPlanError, custom_shots, plan_shots, snap_up, stills_for)

log = logging.getLogger("xenoform.dense")

ROOT = Path(__file__).resolve().parents[2]
DEMO1_PLAN = ROOT / "configs" / "dense_demo1.json"
ENERGY = ("flow", "dense")
TIERS = ("draft", "final")
VERTICAL = ("native", "crop")


def vertical_mode(state: dict) -> str:
    """9:16 on Final renders natively unless the crop is asked for. (Draft 9:16 re-lays the stills and renders
    portrait too, see ``native_draft`` in run_simple; this flag only feeds the Final tier's sizes.)"""
    tier = str(state.get("quality_tier") or "draft").lower()
    asked = str(state.get("vertical_mode") or "auto").lower()
    if tier != "final":
        return "crop"
    return asked if asked in VERTICAL else "native"
MAX_SHOTS = 15  # the short-clip plan (demo1): 16 stills, the black pool holds 17, the other vibes 12
# Full-length songs: the cut keeps a shot a bar (a half bar after the drop) however long the song is, and
# plays a closed chain of reusable morphs instead of one morph per shot. A 4-minute song is about 100 shots
# over 24 morphs; every handoff is still one continuous morph because the chain loops back to its first still.
SHOT_SECONDS_TARGET = 1.6     # shot budget: about one shot per 1.6 s on average
SHOT_BUDGET_MAX = 240
CLIP_BUDGET = (1, 64)         # unique morph renders in a music-video cut (min, max)
MAX_SHOT_S = 4.0              # a morph is rendered at 2 to 5 s; a shot much longer than that would play it in slow motion
# No object repeats inside a cut (Tys, 25 Oct: "a rule we have to build in"): every shot gets its own morph, up to what
# the tier can afford on a 3080 Ti (Draft about 11 s a morph, Final about 7 min); past the cap the cut gets fewer,
# longer shots rather than a loop. The pool caps it too: a vibe with twelve stills gives eleven morphs.
MORPH_CAP = {"draft": 48, "final": 12, "cloud": 16}  # cloud: cloud_final.MAX_MORPHS, its credits
LONG_SONG_S = 20.0            # above this the story plan, the chain reuse and performer slots apply (the demo clip stays on the demo1 plan)
COMPOSE_S_PER_FRAME = {"draft": 0.2, "final": 0.3}
FAST_UPSCALE_S = 20.0  # Fast Final: one Draft clip through its upscaler (upscale_pass.SECONDS_PER_CLIP, measured 28 Oct)  # measured: 1440 frames at 540x960 composed in 285 s (look pass 155 s)

# ---- morph count: "auto" (from clip length + BPM) or a fixed number of forms
MORPH_SLIDER = (1, 40)      # the desk slider; the number box allows up to MORPH_MAX
MORPH_MAX = 120
MIN_SLOT_S = 0.3            # a morph never gets less screen time than this
# measured on an RTX 3080 Ti 12 GB (ComfyUI shared, 2 s renders): seconds per morph and peak VRAM
# draft: measured 23 Oct 2026, 12 four-second morphs in 122 s warm on a 3080 Ti (about 10 s each); 12 s per 2 s morph keeps a margin
# final: 340 s a 2-3 s native 9:16 morph measured 28 Oct (ComfyUI's log of a 1:33:59 Final), less the text encoder read
# once a prompt (about 45 s on most shots) and the quarter-size upscale (about 30 s); a cut that has its own measured
# Finals uses those instead (batch.measured)
COST = {"draft": {"s": 12.0, "vram_gb": 7.5}, "final": {"s": 230.0, "vram_gb": 11.2},
        "final_916": {"s": 270.0, "vram_gb": 11.4}, "preview": {"s": 0.5, "vram_gb": 0.0},
        "fast": {"s": 12.0 + FAST_UPSCALE_S, "vram_gb": 7.5},  # Fast Final: a Draft morph, then its upscale
        # Cloud Final: three LTX-2.5 morphs at once on Comfy Cloud (cloud_final.SECONDS_PER_MORPH each), then the upscale here
        "cloud": {"s": 75.0 / 3 + FAST_UPSCALE_S, "vram_gb": 2.0}}


def _period(beats: list) -> float:
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    return float(gaps[len(gaps) // 2]) if gaps else 0.5


def morph_count(state: dict) -> int | str:
    """``state["morph_count"]``: "auto" (default) or an int clamped to 1..MORPH_MAX."""
    raw = (state or {}).get("morph_count")
    if raw in (None, "", "auto", 0, "0"):
        return "auto"
    try:
        return max(1, min(MORPH_MAX, int(raw)))
    except (TypeError, ValueError):
        return "auto"


def auto_morph_count(duration: float, beats: list, energy: str = "flow") -> int:
    """Auto: dense gives one form per half bar, flow one per two bars (about 5 s at 100 BPM)."""
    duration = float(duration or 0.0)
    beats = [float(b) for b in beats or [] if 0.0 <= float(b) < duration]
    bar = 4 * _period(beats) if len(beats) > 2 else 2.0
    per = bar / 2 if energy == "dense" else max(bar * 2, 4.0)
    return max(1, min(MORPH_MAX, int(round(duration / per))))


def resolve_morph_count(state: dict, duration: float, beats: list) -> int:
    n = morph_count(state)
    return auto_morph_count(duration, beats, options(state)["energy"]) if n == "auto" else int(n)


def estimate(count: int, tier: str = "draft", aspect: str = "16:9", vertical: str = "native", *,
             clip_s: float = 2.0, compose_s: float = 0.0) -> dict:
    """Rough render time and VRAM for ``count`` morphs of ``clip_s`` seconds on this tier, plus the look pass."""
    key = "final_916" if tier == "final" and aspect == "9:16" and vertical == "native" else tier
    c = COST.get(key, COST["draft"])
    gpu = c["s"] * int(count) * max(0.5, float(clip_s) / 2.0)
    secs = int(round(gpu + float(compose_s) + (20 if tier != "preview" else 0)))
    return {"morphs": int(count), "seconds": secs, "minutes": round(secs / 60, 1), "peak_vram_gb": c["vram_gb"],
            "gpu_seconds": int(round(gpu)), "look_seconds": int(round(float(compose_s))), "clip_s": float(clip_s),
            "basis": "RTX 3080 Ti 12 GB, ComfyUI shared"}


def count_cuts(duration: float, beats: list, count: int, drop: float | None = None) -> list[float]:
    """``count`` + 1 cut points from 0 to the end, snapped to beats. After the drop forms come twice as fast."""
    duration = float(duration)
    count = max(1, int(count))
    grid = sorted({round(float(b), 4) for b in beats or [] if 0.0 < float(b) < duration - MIN_SLOT_S})
    if len(grid) < count * 2:  # add half-beats so dense counts still land on the grid
        half = [round((a + b) / 2, 4) for a, b in zip(grid, grid[1:])]
        grid = sorted(set(grid + half))
    d = drop if drop is not None and 0 < drop < duration else None
    def weight(t):  # time measured in "form units": post-drop seconds count double
        return t if d is None or t <= d else d + 2 * (t - d)
    total = weight(duration)
    def inv(w):
        return w if d is None or w <= d else d + (w - d) / 2
    cuts = [0.0]
    for k in range(1, count):
        want = inv(total * k / count)
        cand = [g for g in grid if g > cuts[-1] + MIN_SLOT_S - 1e-6
                and g < duration - MIN_SLOT_S * (count - k)]
        best = min(cand, key=lambda g: abs(g - want)) if cand else None
        if best is None or abs(best - want) > 0.6 * (duration / count) + 0.25:
            best = max(cuts[-1] + MIN_SLOT_S, min(want, duration - MIN_SLOT_S * (count - k)))
        cuts.append(round(best, 4))
    if d is not None and count > 1:  # the drop is always a cut
        k = min(range(1, count), key=lambda i: abs(cuts[i] - d))
        lo = cuts[k - 1] + MIN_SLOT_S
        hi = (cuts[k + 1] if k + 1 < count else duration) - MIN_SLOT_S
        if lo <= d <= hi:
            cuts[k] = round(d, 4)
    return cuts + [round(duration, 4)]


# the house look in the Simple payload: ``dance_fx`` ("auto" | "off" | a dance_fx.PRESETS name) and ``stem_orbit`` (bool)
DANCE_FX_DEFAULT = "auto"
STEM_ORBIT_DEFAULT = True


def house(state: dict | None = None, cfg: dict | None = None) -> dict:
    """The house profile for a render (cfg["house"] when the loaded config carries one, else demo_house)."""
    from xenoform.config import house as _house

    return _house(cfg=cfg)


def dance_fx_choice(state: dict | None) -> str:
    """The raw ``dance_fx`` payload key, normalised: "auto" (default), "off" or a known preset name."""
    from xenoform import dance_fx as D

    raw = (state or {}).get("dance_fx", DANCE_FX_DEFAULT)
    if raw is None or raw is True:
        return DANCE_FX_DEFAULT
    if raw is False:
        return "off"
    text = str(raw).strip().lower()
    if text in ("", "auto", "house", "default", "on"):
        return "auto"
    if text in ("off", "none", "false", "0", "no"):
        return "off"
    from xenoform.effects import LOOKS as _EXTRA  # the Dither look

    return text if text in D.PRESETS or text in _EXTRA else DANCE_FX_DEFAULT


def stem_orbit_choice(state: dict | None) -> bool:
    raw = (state or {}).get("stem_orbit", None)
    if raw is None or raw == "":
        return STEM_ORBIT_DEFAULT
    if isinstance(raw, str):
        return raw.strip().lower() not in ("off", "false", "0", "no", "none")
    return bool(raw)


PERFORMER_CHOICES = (0, 2, 4)           # performer shots per video: off, two, four
PERFORMER_SECONDS = 470.0               # per 5 s shot (175 frames with the two-second pre-roll) on a 12 GB card, measured 23-24 Oct 2026 (the turbo LoRA does not help when the weights stream from RAM)
PERFORMER_MIN_S = 124 / 24.0            # H3's shortest clip (17k+5 frames at 24 fps)
PERFORMER_MAX_S = 8.0
PERFORMER_REFERENCE = Path(__file__).resolve().parent / "ui_static" / "performer" / "polly.png"  # the bundled reference still


def performer_choice(state: dict | None) -> int:
    """How many performer shots the cut gets (0, 2 or 4); anything else snaps to the nearest choice."""
    try:
        n = int(float((state or {}).get("performer") or 0))
    except (TypeError, ValueError):
        n = 0
    return min(PERFORMER_CHOICES, key=lambda c: abs(c - n))


def performer_reference(instrument: str | None = None, pick: int = 0) -> Path | None:
    """The bundled Polly still for ``instrument`` (``performer.default_reference``: at the kit, the mic, the keys,
    with a guitar or dancing when that still ships, standing otherwise; ``pick`` rotates a pose's numbered
    variants), or None when nothing is bundled."""
    try:
        from xenoform import performer as P

        ref = Path(P.default_reference(instrument, pick))
    except Exception:
        ref = PERFORMER_REFERENCE
    return ref if ref.is_file() else None


PERFORMER_STYLES = ("auto", "sing", "drums", "keys", "guitar", "dance")
PERFORMER_QUIET_CYCLE = ("keys", "dance", "guitar", "dance")  # auto: quiet passages without a vocal, in slot order (more dance than instruments after the opening)
VOCAL_PRESENT = 0.2  # a slot sings when its vocal-stem level is above this fraction of the song's loudest vocal moment


def performer_style(state: dict | None) -> str:
    key = str((state or {}).get("performer_style") or "auto").strip().lower()
    return key if key in PERFORMER_STYLES else "auto"


def _vocals_in(stem_env: dict | None, t0: float, t1: float) -> float | None:
    """The vocal stem's mean level over [t0, t1] as a fraction of the song's peak vocal level, or None without stems."""
    if not stem_env or not stem_env.get("vocals") or str(stem_env.get("engine") or "").startswith("mix"):
        return None
    v = [float(x) for x in stem_env["vocals"]]
    fps = float(stem_env.get("fps") or 24)
    peak = max(v) if v else 0.0
    if peak <= 1e-6:
        return 0.0
    a, b = int(max(0, t0 * fps)), int(min(len(v), t1 * fps))
    if b <= a:
        return 0.0
    return float(sum(v[a:b]) / (b - a)) / peak


def performer_slots(shots: list[dict], count: int, stem_env: dict | None = None, style: str = "auto", *,
                    max_s: float = PERFORMER_MAX_S) -> list[dict]:
    """Where the performer appears: runs of consecutive shots, each at least ``PERFORMER_MIN_S`` long,
    starting a passage. Priority: the intro first, then the first drop (drums), then each further passage
    in order; never two slots back to back, at most ``count``. A run takes whole shots up to ``max_s`` (the
    longest clip H3 makes; a short clip the idea line brought her into passes half its length, so the morphs
    keep the other half). What she does: ``style`` when set; else she
    sings where the song's vocal stem sings (real lip-sync to the vocal), drums on the first drop, dances on
    the other loud passages, and on the quiet ones plays keys, then dances, then guitar (``PERFORMER_QUIET_CYCLE``)."""
    count = int(count)
    max_s = max(float(max_s), PERFORMER_MIN_S)
    if count <= 0 or not shots:
        return []
    style = str(style or "auto").lower()
    starts = [i for i, s in enumerate(shots) if i == 0 or s.get("boundary") or (s.get("section") != shots[i - 1].get("section"))]
    cands = []
    for i in starts:
        section = str(shots[i].get("section") or "")
        j, total = i, 0.0
        while j < len(shots) and shots[j].get("section", section) == section and total < PERFORMER_MIN_S:
            total += float(shots[j].get("seconds") or (shots[j]["end"] - shots[j]["start"]))
            j += 1
        if total < PERFORMER_MIN_S:
            continue
        while j < len(shots) and shots[j].get("section", section) == section and total + float(shots[j].get("seconds") or 0) <= max_s:
            total += float(shots[j].get("seconds") or 0)  # take whole shots up to the longest clip H3 makes
            j += 1
        t0, t1 = float(shots[i]["start"]), float(shots[j - 1]["end"])
        vocal = _vocals_in(stem_env, t0, t1)
        cands.append({"first": i, "last": j - 1, "seconds": round(total, 4), "section": section,
                      "vocal": None if vocal is None else round(vocal, 3), "start": t0})
    if not cands:
        return []
    order = sorted(cands, key=lambda c: (0 if c["section"] == "intro" else 1 if c["section"] == "drop" else 2, c["start"]))
    picked: list[dict] = []
    for c in order:
        if len(picked) >= count:
            break
        if any(not (c["last"] < q["first"] - 1 or c["first"] > q["last"] + 1) for q in picked):
            continue  # never adjacent to another performer slot
        picked.append(c)
    picked.sort(key=lambda c: c["first"])
    # what she does, in the order the slots come: a set style everywhere; else she sings where the vocal stem
    # sings (real lip-sync), drums on the first drop (or the first loud passage when there is no drop), dances
    # on the other loud passages, and the quiet ones open on keys then alternate dance and guitar
    loud = {"drop", "drop_late", "build"}
    drums_at = next((c["first"] for c in picked if c["section"] == "drop"),
                    next((c["first"] for c in picked if c["section"] in loud), None))
    quiet = 0
    for c in picked:
        if style != "auto":
            c["instrument"] = {"sing": "voice"}.get(style, style)
        elif c["vocal"] is not None and c["vocal"] >= VOCAL_PRESENT:
            c["instrument"] = "voice"
        elif c["section"] in loud:
            c["instrument"] = "drums" if c["first"] == drums_at else "dance"
        else:
            c["instrument"] = PERFORMER_QUIET_CYCLE[quiet % len(PERFORMER_QUIET_CYCLE)]
            quiet += 1
    return picked


def _render_performer(audio_path: Path, slot: dict, vibe: str, still: Path, work: Path, cfg: dict, *, seed: int,
                      report=None, beats: list[float] | None = None, source: dict | None = None) -> dict:
    """One H3 performer shot for ``slot`` (the module is optional: ImportError means the feature is off). ``source``
    is the Length cut's ``song_source`` (the full song and the cut's offset in it), for the pre-roll."""
    from xenoform import performer as P
    from xenoform.morph_pass import VIBE_LOOK

    prompt = P.prompt_for(str(slot.get("section") or "calm"), VIBE_LOOK.get(vibe, ""), slot.get("instrument"))
    source = source if isinstance(source, dict) and source.get("path") else None
    return P.render_slot(Path(audio_path), float(slot["start"]), float(slot["seconds"]), Path(still), prompt, Path(work), cfg,
                         seed=int(seed), report=report, beats=beats,
                         source_path=source.get("path") if source else None, source_offset=float(source.get("offset") or 0.0) if source else 0.0)


def _clip_morphs(body: Path, dest: Path, slot: dict, shots: list[dict], stills: list[dict], n_in: int, n_out: int,
                 work: Path, cfg: dict, seed: int, vibe: str, client, cancel, state: dict, opt: dict, native_draft: bool,
                 fps: float) -> Path:
    """An own clip's slot with a morph in and a morph out (``own_media.splice``): from the object the shot before the
    slot lands on into the clip's first frame, and from its last frame into the object the shot after starts from.
    Both render on the Draft model (``cloud_morph._local_clips``, in their own folder so the cut's ``localNN`` clips are
    untouched), the clip's frames as the scene end of each pair."""
    from xenoform import own_media
    from xenoform.cloud_morph import _local_clips

    size = DRAFT_916 if opt["aspect"] == "9:16" else None
    render = size or (512, 288)
    folder = Path(work) / "own" / f"morph_{slot['start']:.2f}"
    first_png, last_png = own_media.first_last(body, folder, render)
    ends = []
    if n_in:
        ends.append(stills[int(shots[slot["first"] - 1].get("morph", slot["first"] - 1)) + 1])
    if n_out:
        ends.append(stills[int(shots[slot["last"] + 1].get("morph", slot["last"] + 1))])
    if opt["aspect"] == "9:16" and not native_draft:  # a Final's stills are still square-on: lay them on the portrait canvas
        from xenoform.portrait import portrait_stills

        ends = portrait_stills(ends, folder, DRAFT_916[0], DRAFT_916[1], background=state.get("still_background"))
    frame = lambda p: {"path": str(p), "noun": "your clip", "kind": "scene", "file": Path(p).name}  # noqa: E731
    pairs: list[tuple[dict, dict]] = []
    if n_in:
        pairs.append((ends[0], frame(first_png)))
    if n_out:
        pairs.append((frame(last_png), ends[-1]))
    made = []
    for j, (a, b) in enumerate(pairs):  # one pair at a time: each is its own two-still chain
        sub = folder / f"pair{j}"
        sub.mkdir(parents=True, exist_ok=True)
        made.append(_local_clips([{"seconds": 1.0, "render_s": 1.0}], [a, b], sub, cfg, seed + j, vibe, client=client, cancel=cancel,
                                 state=state, size=size, styles=["melt"])[0])
    morph_in = made[0] if n_in else None
    morph_out = made[-1] if n_out else None
    return own_media.splice(morph_in, body, morph_out, dest, n_in=n_in, n_out=n_out, size=own_media.size_for(opt["aspect"]), fps=fps)


def apply_performer_slots(shots: list[dict], clips: list, slots: list[dict], rendered: dict, mark: str = "performer") -> tuple[list[dict], list]:
    """Merge each rendered slot's shots into one shot playing its clip 1:1 (marked ``mark``: a performer shot, or
    ``own`` for one of the user's own clips, which also carries its ``source`` file name); the rest unchanged."""
    out_shots, out_clips = [], []
    i = 0
    by_first = {sl["first"]: sl for sl in slots if sl["first"] in rendered}
    while i < len(shots):
        sl = by_first.get(i)
        if sl is None:
            out_shots.append(shots[i])
            out_clips.append(clips[i])
            i += 1
            continue
        run = shots[sl["first"]:sl["last"] + 1]
        frames = int(sum(int(s.get("frames") or 0) for s in run))
        effects = [e for s in run for e in (s.get("effects") or []) if e.get("type") == "punch"]
        merged = {**run[0], "start": run[0]["start"], "end": run[-1]["end"], "seconds": round(float(run[-1]["end"]) - float(run[0]["start"]), 4),
                  "frames": frames, "render_s": None, "speed": 1.0, "effects": effects, mark: True,
                  "instrument": sl.get("instrument"), "index": len(out_shots)}
        if sl.get("clip"):
            merged["source"] = Path(str(sl["clip"])).name
        merged.pop("ease", None)
        merged.pop("clip", None)
        merged.pop("morph", None)  # a slot plays its own clip, no morph
        out_shots.append(merged)
        out_clips.append(Path(rendered[sl["first"]]["clip"]))
        i = sl["last"] + 1
    return out_shots, out_clips


def options(state: dict) -> dict:
    """The Simple finishing options from a desk state, normalised."""
    energy = str(state.get("energy_preset") or "flow").lower()
    tier = str(state.get("quality_tier") or "draft").lower()
    return {
        "energy": energy if energy in ENERGY else "flow",
        "aspect": beatfx.norm_aspect(state.get("aspect")),
        "tier": tier if tier in TIERS else "draft",
        "fast": tier == "fast",  # Fast Final: the Draft's morphs upscaled to full size (upscale_pass); a draft otherwise
        "cloud": tier == "cloud",  # Cloud Final: LTX-2.5 morphs on Comfy Cloud (cloud_final), upscaled here
        "vertical": vertical_mode(state),
        "fx": bool(state.get("beat_fx", True)),
        "overlay": bool(state.get("beat_overlay")) and not bool(state.get("clean")),
        "end_card": bool(state.get("end_card")),
        "recipe": str(state.get("simple_recipe") or ""),
        "morph_count": morph_count(state),
        "dance_fx": dance_fx_choice(state),
        "stem_orbit": stem_orbit_choice(state),
        "performer": performer_choice(state),
        "performer_style": performer_style(state),
        "foreshadow": _foreshadow_choice(state),
    }


def _foreshadow_choice(state: dict) -> str:
    from xenoform import foreshadow as _fs

    return _fs.choice(state)


def stem_env_for(state: dict | None) -> dict | None:
    """The job's stem envelopes (``stem_react.envelopes`` JSON at ``state["stems_path"]``), or None so
    the compositor derives a 4-role envelope from the mix."""
    raw = (state or {}).get("stems_path")
    if not raw:
        return None
    try:
        env = json.loads(Path(str(raw)).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("stems_path %s unreadable (%s); using the mix envelope", raw, exc)
        return None
    return env if isinstance(env, dict) and any(env.get(k) for k in ("drums", "bass", "other", "vocals")) else None


def macros(state: dict) -> dict:
    """The Simple macro knobs (0..1 each, 0.5 neutral) from the desk, clamped; missing keys are neutral."""
    raw = state.get("macros") or {}
    out = {}
    for k, d in (("intensity", 0.5), ("speed", 0.5), ("chaos", 0.3), ("glow", 0.4)):
        try:
            out[k] = max(0.0, min(1.0, float(raw.get(k, d))))
        except (TypeError, ValueError, AttributeError):
            out[k] = d
    st = raw.get("stems") if isinstance(raw, dict) else None
    if isinstance(st, dict):  # per-stem reaction gains, any stem names, up to stem_react.MAX_STEMS
        from xenoform.stem_react import MAX_STEMS
        g = {}
        for name, v in list(st.items())[:MAX_STEMS]:
            try:
                g[str(name)[:64]] = max(0.0, min(1.0, float(v)))
            except (TypeError, ValueError):
                continue
        out["stems"] = g
    return out


def speed_count(duration: float, beats: list, energy: str, speed: float) -> int:
    """The auto morph count biased by the Simple ``speed`` macro: x0.6 at 0, as planned at 0.5, x1.4 at 1."""
    base = auto_morph_count(duration, beats, energy)
    return max(1, min(MORPH_MAX, int(round(base * (0.6 + 0.8 * max(0.0, min(1.0, float(speed))))))))


def apply_macros(shots: list[dict], m: dict, house: dict | None = None) -> list[dict]:
    """Intensity scales each shot's beat-FX intensity (0.5 = as planned); Chaos above 0.5 adds wobble
    (never when the ``house`` look says character_wobble is off)."""
    gain = 1.6 * float(m.get("intensity", 0.5))  # 0 = no beat FX at all, 0.5 = four fifths, 1 = everything
    chaos = float(min(1.0, max(0.0, m.get("chaos", 0.3))))
    wob = max(0.0, (chaos - 0.4) * 1.0)
    if house and ((house.get("look") or {}).get("character_wobble") is False):
        wob = 0.0
    for s in shots:
        s["fx_intensity"] = round(min(1.0, float(s.get("fx_intensity", 1.0)) * gain), 3)
        s["chaos"] = round(chaos, 3)
        if wob:
            s["wobble"] = round(max(float(s.get("wobble") or 0.0), wob), 3)
        # Chaos shapes the cut itself: punches scale with it, stutters / holds / skips vanish when calm and
        # double up when wild; the subject's orbit swing follows it too (see beatfx.LookPass).
        effects = []
        for fx in s.get("effects") or []:
            kind = fx.get("type")
            if kind == "punch":
                effects.append({**fx, "strength": round(min(1.0, float(fx.get("strength", 0.5)) * (0.2 + 1.4 * chaos)), 3)})
            elif kind in ("stutter", "hold", "skip", "reverse"):
                if chaos < 0.2:
                    continue
                if kind == "stutter" and chaos > 0.6:
                    fx = {**fx, "repeat": min(8, int(fx.get("repeat", 3)) + (4 if chaos > 0.85 else 2))}
                effects.append(fx)
            else:
                effects.append(fx)
        s["effects"] = effects
    return shots


GROW_FOR_IDEA_MAX = 16  # stills grown for an idea's family before a cut, about 6 s each on a 3080 Ti


def grow_family_for_cut(state: dict, vibe: str, need: int, cfg: dict | None, report: Callable | None = None, *,
                        engine: str | None = None) -> dict | None:
    """The idea line's family grown before the cut when the vibe's pool lacks it, so the cut's objects belong
    together: "a chess game played by machines" on chrome found one toy in the pool and fell through to six
    families (26 Oct). Up to ``GROW_FOR_IDEA_MAX`` stills, only when ComfyUI has Z-Image, never for a mock render;
    ``state["auto_grow"]`` False turns it off. Returns the tally, or None when nothing was grown."""
    from xenoform import morph_pass as _mp
    from xenoform import stills as _stills

    if engine == "mock" or state.get("auto_grow") is False or _mp.scenes_choice(state) == "only":
        return None  # a scenes-only cut draws on no object family
    # the family exactly as pick_stills will sort on it: looked up under the asked vibe (a vibe that borrows a pool
    # keeps its own weights), the idea's named family first, else the vibe's own with the seed turning a tie
    asked = str(state.get("vibe") or "") or vibe
    words = _stills.content_words(_mp._story_words(state))
    from xenoform import idea as _idea

    typed = _stills.content_words(_mp._idea_words(state))  # the idea line first, as pick_stills reads it
    family = str(_idea.reading_for(state).get("family") or "") or _stills.family_named(asked, typed) \
        or _stills.family_named(asked, words) or _stills.family_for_cut(asked, set(), seed=int(state.get("seed") or 0))
    if not family:
        return None
    cat = _mp.catalogue()
    rows = list(cat.get(vibe) or []) + (list(cat.get(asked) or []) if asked != vibe else [])  # what the cut draws on
    in_family = [r for r in rows if _stills.family_of(str(r.get("noun") or "")) == family]
    want = min(int(need), GROW_FOR_IDEA_MAX)
    if len(in_family) >= want:
        return None
    have = _stills.nouns_in(vibe) | (_stills.nouns_in(asked) if asked != vibe else set())
    nouns = _stills.family_nouns(vibe, family, want - len(in_family), have=have)
    if not nouns:
        return None
    try:
        if not _stills.available(cfg).get("ok"):
            return None
        if report:
            report("restyle", 0.03, f"Growing {len(nouns)} {family.replace('-', ' ')} objects for this idea (about {int(_stills.estimate_seconds(len(nouns)))} s)")
        result = _stills.grow(vibe, len(nouns), nouns=nouns, cfg=cfg, sheet=False)
        return {"family": family, "asked": len(nouns), "kept": result.get("kept", 0)}
    except Exception as exc:  # the cut goes on with the pool it has
        log.warning("grow for idea skipped: %s", exc)
        return None


def grow_for_idea(state: dict, vibe: str, cfg: dict | None, report: Callable | None = None, *, engine: str | None = None,
                  reading: dict | None = None) -> dict | None:
    """The scenes and shapes the idea line asks for, grown before the cut under the pool vibe ``vibe`` the way
    ``grow_family_for_cut`` grows a family: the typed scene subjects as wide frames (``idea.SCENES_PER_SUBJECT`` seeds
    each), the things the catalogue lacks as the user's own shapes, the named catalogue nouns the pool lacks as
    objects (``idea.grow_plan``). Only when ComfyUI has Z-Image, never for a mock render, ``state["auto_grow"]`` False
    turns it off. Returns the tally (``scenes`` / ``own`` / ``nouns`` asked and kept), or None when nothing grew."""
    from xenoform import idea as _idea
    from xenoform import stills as _stills

    if engine == "mock" or state.get("auto_grow") is False:
        return None
    reading = reading if reading is not None else _idea.reading_for(state)
    plan = _idea.grow_plan(reading, vibe)
    if not plan["count"]:
        return None
    try:
        if not _stills.available(cfg).get("ok"):
            return None
        bits = []
        if plan["scenes"]:
            bits.append(f"{len(plan['scenes'])} scene{'s' if len(plan['scenes']) != 1 else ''} ({'; '.join(dict.fromkeys(plan['scenes']))})")
        shapes = plan["own"] + plan["nouns"]
        if shapes:
            bits.append(f"{len(shapes)} shape{'s' if len(shapes) != 1 else ''} ({', '.join(shapes)})")
        if report:
            report("restyle", 0.03, f"Growing {' and '.join(bits)} for your line (about {plan['seconds']} s)")
        out: dict = {"asked": plan["count"], "kept": 0}
        if plan["scenes"]:
            got = _stills.grow(vibe, len(plan["scenes"]), nouns=plan["scenes"], cfg=cfg, sheet=False, kind="scene")
            out["scenes"] = {"asked": len(plan["scenes"]), "kept": int(got.get("kept", 0)), "files": list(got.get("files") or [])}
            out["kept"] += int(got.get("kept", 0))
        if plan["own"]:
            got = _stills.grow(vibe, len(plan["own"]), nouns=plan["own"], own=True, cfg=cfg, sheet=False)
            out["own"] = {"asked": len(plan["own"]), "kept": int(got.get("kept", 0)), "files": list(got.get("files") or [])}
            out["kept"] += int(got.get("kept", 0))
        if plan["nouns"]:
            got = _stills.grow(vibe, len(plan["nouns"]), nouns=plan["nouns"], cfg=cfg, sheet=False)
            out["nouns"] = {"asked": len(plan["nouns"]), "kept": int(got.get("kept", 0)), "files": list(got.get("files") or [])}
            out["kept"] += int(got.get("kept", 0))
        return out
    except Exception as exc:  # the cut goes on with the pool it has
        log.warning("grow for the idea line skipped: %s", exc)
        return None


def _scene_kw(state: dict, shots: list[dict], count: int, assign: list | None = None) -> dict:
    """``scene_at`` for ``stills_for`` (``morph_pass.scene_slots``: the stills of the chain that are scenes), only when
    the scenes choice is on, so an object cut calls ``stills_for(state, count)`` exactly as before."""
    from xenoform import morph_pass as _mp

    choice = _mp.scenes_choice(state)
    return {"scene_at": _mp.scene_slots(shots, count, choice, assign=assign)} if choice != "off" else {}


def _merge_to(shots: list[dict], n: int) -> list[dict]:
    """``shots`` folded into ``n`` by merging the shortest into its shorter neighbour, the timeline untouched. The
    story planner keeps a cut at every role start, so ``max_shots`` alone left 16 shots for 11 morphs on a shipped
    12-still pool and the compose crashed (26 Oct review); the chain's count is enforced here."""
    shots = [dict(s) for s in shots]
    n = max(1, int(n))
    while len(shots) > n:
        i = min(range(len(shots)), key=lambda k: float(shots[k].get("seconds") or 0.0))
        if i == 0:
            j = 1
        elif i == len(shots) - 1:
            j = i - 1
        else:
            j = i - 1 if float(shots[i - 1].get("seconds") or 0.0) <= float(shots[i + 1].get("seconds") or 0.0) else i + 1
        a, b = (shots[i], shots[j]) if i < j else (shots[j], shots[i])
        merged = {**a, "seconds": round(float(a.get("seconds") or 0.0) + float(b.get("seconds") or 0.0), 4),
                  "effects": list(a.get("effects") or []) + list(b.get("effects") or [])}
        if "end" in a or "end" in b:
            merged["end"] = b.get("end", a.get("end"))
        if "frames" in a or "frames" in b:
            merged["frames"] = int(a.get("frames") or 0) + int(b.get("frames") or 0)
        lo = min(i, j)
        shots[lo:lo + 2] = [merged]
    for k, s in enumerate(shots):
        if "index" in s:
            s["index"] = k
    return shots


def long_song_chain(state: dict, directed: dict, audio_path: Path, shots: list[dict], plan: dict, opt: dict, *,
                    cfg: dict | None = None, report: Callable | None = None, engine: str | None = None,
                    grow: bool = True) -> tuple[list[dict], dict, dict, list[dict]]:
    """The music-video chain for a long song, the same for the render and the stills animatic: one morph a shot and
    no object twice (``clip_plan``), the pool (the asked vibe's own stills plus the pool it draws on) and the tier
    capping it; the idea's family grown first when ``grow``; past the cap the song is re-planned with fewer, longer
    shots on the bars and merged down to the count when the planner's roles still outnumber it. Returns
    ``(shots, plan, chain, notes)``."""
    from xenoform.morph_pass import catalogue as _catalogue, rows_of_kind as _rows_of_kind, scenes_choice as _scenes_choice
    from xenoform.morph_pass import vibe_for as _vibe_for

    notes: list[dict] = []
    duration = float(directed.get("duration") or 0.0)
    beats_list = list(directed.get("beats") or [])
    pool_vibe = _vibe_for(state)
    asked = str(state.get("vibe") or "")
    choice = _scenes_choice(state)

    def pool_count() -> int:
        # the rows the scenes choice lets the cut draw on (objects alone, scenes alone, both); a vibe asked for scenes
        # it has none of falls back to its objects, as the pick does
        cat = _catalogue()
        rows = list(cat.get(pool_vibe) or []) + (list(cat.get(asked) or []) if asked and asked != pool_vibe else [])
        return len(_rows_of_kind(rows, choice)) or len(rows)

    pool_n = pool_count()
    tier = "cloud" if opt["cloud"] else opt["tier"]
    chain = clip_plan(shots, duration, beats_list, pool=pool_n or None, tier=tier)
    if grow:
        grown = grow_family_for_cut(state, pool_vibe, chain["morphs"] + 1, cfg, report, engine=engine)
        if grown:  # the idea's family now in the pool: count again, the chain may afford more
            notes.append({"grown": grown})
            pool_n = pool_count()
            chain = clip_plan(shots, duration, beats_list, pool=pool_n or None, tier=tier)
    if not chain["fits"]:
        wanted = chain["wanted"]
        shots, plan, chain = fit_chain(state, directed, audio_path, chain, pool_n, tier)
        notes.append({"capped": {"wanted": wanted, "shots": len(shots), "cap": chain.get("cap"), "pool": pool_n}})
        if report:
            report("restyle", 0.04, f"{wanted} shots re-planned as {len(shots)} longer ones: no object repeats, and {opt['tier']} "
                                    f"affords {chain.get('cap')} morphs" + (f" over a pool of {pool_n}" if pool_n else ""))
    return shots, plan, chain, notes


def fit_chain(state: dict, directed: dict, audio_path: Path | None, chain: dict, pool_n: int | None, tier: str, *,
              drop: float | None = None) -> tuple[list[dict], dict, dict]:
    """A plan the chain cannot afford, made again with ``max_shots`` at the morphs it can (fewer, longer shots on the
    bars), merged down to that count when the planner's roles still outnumber it; the Make and the desk's estimate
    (``plan_summary``) both come here, so the count the desk shows is the count the cut gets."""
    duration = float(directed.get("duration") or 0.0)
    beats_list = list(directed.get("beats") or [])
    capped = {**state, "max_shots": chain["morphs"]}
    shots, plan = shots_for(capped, directed, Path(audio_path) if audio_path else None, drop=drop)
    if len(shots) > chain["morphs"]:
        shots = _merge_to(shots, chain["morphs"])
    return shots, plan, clip_plan(shots, duration, beats_list, pool=pool_n or None, tier=tier)


def _cloud_fits(chain: dict) -> None:
    """Refuse a Cloud Final chain of more morphs than Comfy Cloud takes (``cloud_final.MAX_MORPHS``)."""
    from xenoform.cloud_final import MAX_MORPHS

    n = int(chain.get("morphs") or 0)
    if n > MAX_MORPHS:
        raise RuntimeError(f"Cloud Final takes at most {MAX_MORPHS} morphs; this cut plans {n}. Choose Length 60 s or fewer "
                           "Forms. Nothing was sent.")


def wants_finishing(state: dict) -> bool:
    """True when the plain morph pass cannot do what was asked (anything beyond flow/draft/16:9), and always for a
    Simple-mode cut: Flow at 16:9 on a short song once went through the plain pass and came out as one morph held
    over fifteen seconds (66 % duplicate frames, 25 Oct test drive); the Simple cut is the beat-cut compose."""
    opt = options(state)
    return str(state.get("mode") or "") == "simple" or opt["energy"] == "dense" or opt["tier"] == "final" \
        or opt["aspect"] != "16:9" or opt["end_card"] or bool(state.get("cut_plan")) or morph_count(state) != "auto"


def demo1_plan() -> dict:
    return json.loads(DEMO1_PLAN.read_text(encoding="utf-8"))


def _render_s(seconds: float, speed: float) -> int:
    return snap_up(max(2.0, seconds * speed - 0.15))


def shot_budget(duration: float) -> int:
    """How many shots a Dense cut may have: 15 for a demo clip, a shot per 1.6 s for a full song (cap 240)."""
    return max(MAX_SHOTS, min(SHOT_BUDGET_MAX, int(round(float(duration) / SHOT_SECONDS_TARGET))))


def clip_plan(shots: list[dict], duration: float, beats: list, *, pool: int | None = None, tier: str = "draft") -> dict:
    """The morphs for a long song: one unique render of ``clip_s`` seconds per shot, ``assign[i]`` the render shot
    ``i`` plays. No object ever repeats: when the shots outnumber what the tier (``MORPH_CAP``) or the pool can
    afford, the shots are merged into that many longer ones (``merge_shots``) and the plan carries them as
    ``shots`` with ``merged`` True. Every handoff stays continuous: shot i ends on the still shot i+1 starts on."""
    duration = float(duration)
    bar = 4.0 * _period(beats) if beats else 2.0
    clip_s = snap_up(min(5.0, max(2.0, bar * 1.15)))
    # the tier's cap, but never shots longer than MAX_SHOT_S: a 2 to 5 s morph played over a 15 s shot is slow motion
    # and held frames, so a long song on Final asks for more morphs (the estimate says how long) rather than that
    cap = max(int(MORPH_CAP.get(str(tier or "draft"), MORPH_CAP["draft"])), int(math.ceil(duration / MAX_SHOT_S)))
    morphs = min(len(shots), cap, CLIP_BUDGET[1])
    if pool:
        morphs = min(morphs, max(1, int(pool) - 1))  # a chain of n morphs needs n + 1 distinct stills
    morphs = max(CLIP_BUDGET[0], morphs)
    # ``fits`` False: the cut wants more morphs than the tier or the pool affords; the caller re-plans the song with
    # ``max_shots`` = morphs, so the planner itself makes fewer, longer shots on the bars, and no object repeats
    return {"clip_s": int(clip_s), "morphs": morphs, "assign": list(range(morphs)), "reuse": False, "cap": cap,
            "fits": morphs >= len(shots), "wanted": len(shots)}


def plan_summary(duration: float, beats: list, energy: str = "dense", tier: str = "draft", aspect: str = "9:16",
                 vertical: str = "native", drop: float | None = None, performer: int = 0, pool: int | None = None, *,
                 sections: list[dict] | None = None, state: dict | None = None) -> dict:
    """What a Make will do for this song: shots, unique morphs, clip length and a time estimate (GPU + look).
    ``pool`` is the vibe's still count when known: the chain never repeats an object, so it caps the morphs too.

    With the song's ``sections`` and the Make body (``state``) it plans with the Make's own planner and chain
    (``shots_for``, ``clip_plan``, ``fit_chain``), so the count and the clock the desk shows are the cut's; without
    them it is the older estimate on the demo1 plan."""
    duration = float(duration)
    long_song = duration > LONG_SONG_S
    plan: dict = {}
    if state is not None and sections:
        body = {**state, "energy_preset": energy, "quality_tier": tier}
        directed = {"duration": duration, "beats": list(beats or []), "sections": list(sections)}
        shots, plan = shots_for(body, directed, None, drop=drop)
        if long_song and not plan.get("stills"):
            cp = clip_plan(shots, duration, beats, pool=pool or None, tier=tier)
            if not cp["fits"]:
                shots, plan, cp = fit_chain(body, directed, None, cp, pool, tier, drop=drop)
        else:
            cp = {"clip_s": 2, "morphs": len(shots), "assign": list(range(len(shots))), "reuse": False}
    else:
        if energy == "dense":
            shots = dense_plan(duration, beats, drop if drop is not None else duration * 0.6)["shots"]
        else:
            shots = plan_shots(duration, beats)
        cp = clip_plan(shots, duration, beats, pool=pool or None, tier=tier) if long_song else {"clip_s": 2, "morphs": len(shots), "assign": list(range(len(shots))), "reuse": False}
    fps = 24
    frames_total = int(round(duration * fps))
    compose_s = frames_total * COMPOSE_S_PER_FRAME["final" if tier in ("final", "fast", "cloud") else "draft"] / beatfx.look_speedup(frames_total)
    est = estimate(cp["morphs"], tier, aspect, vertical, clip_s=cp["clip_s"], compose_s=compose_s)
    n_perf = performer_choice({"performer": performer}) if long_song else 0
    if n_perf:
        secs = PERFORMER_SECONDS
        try:
            from xenoform import performer as P

            secs = float(P.estimate_seconds(PERFORMER_MIN_S, None) or secs)
        except Exception:
            pass
        est["performer_seconds"] = int(round(secs * n_perf))
        est["seconds"] = int(est["seconds"] + est["performer_seconds"])
        est["minutes"] = round(est["seconds"] / 60, 1)
    return {"duration": round(duration, 2), "shots": min(len(shots), cp["morphs"]) if long_song else len(shots), "morphs": cp["morphs"],
            "clip_s": cp["clip_s"], "reuse": cp["reuse"], "long_song": long_song, "estimate": est, "performer": n_perf,
            "plan_name": str(plan.get("name") or ("dense (auto)" if energy == "dense" else "flow"))}


def dense_plan(duration: float, beats: list, drop: float | None = None, max_shots: int | None = None,
               count: int | None = None) -> dict:
    """A demo1-style cut plan for any song.

    Before the drop: a shot per bar (4 beats), morphs a little faster than real time.
    The bar before the drop eases in. On the drop: punch + 4x2 stutter, then a shot per
    half bar (2 beats) at ~2.5x, with a punch on every downbeat, a 120 ms hold just
    before the hardest hit one bar in, and a short reverse on the last hit. When that
    is more than ``max_shots`` shots, the bars get longer until it fits.
    """
    duration = float(duration)
    if max_shots is None:
        max_shots = shot_budget(duration)
    beats = sorted(float(b) for b in beats if 0.0 <= float(b) < duration)
    if len(beats) < 4:
        step = 0.5
        beats = [i * step for i in range(int(duration / step))]
    period = float(sorted(b - a for a, b in zip(beats, beats[1:]))[len(beats) // 2 - 1]) if len(beats) > 2 else 0.5
    if drop is None:
        drop = beats[len(beats) // 2] if beats else duration / 2
    drop = min(beats, key=lambda b: abs(b - drop)) if beats else drop
    di = beats.index(drop) if drop in beats else 0
    cuts: list[float] = []
    for calm, hype in ((4, 2), (8, 2), (8, 4), (16, 4), (16, 8), (32, 8), (32, 16), (64, 32)) if not count else ():
        pre = [beats[j] for j in range(di, -1, -calm) if beats[j] > 0.25] + [0.0]
        post = [beats[j] for j in range(di, len(beats), hype)]
        cuts = sorted(set(round(c, 4) for c in pre + post if c < duration - 0.3)) + [round(duration, 4)]
        for _ in range(2):  # demo1 opens on one long intro shot: merge up to two intro bars first
            if len(cuts) - 1 > max_shots and len([c for c in cuts if 0 < c < drop - 1e-6]) >= 3:
                cuts.remove(next(c for c in cuts if c > 0))
        if len(cuts) - 1 <= max_shots:
            break
    if count:
        cuts = count_cuts(duration, beats, count, drop)
    shots = []
    downbeats = beats[::4]
    last_hit = None
    for k, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        seconds = b - a
        hype = a >= drop - 1e-6
        speed = 2.5 if hype else 1.25
        render_s = _render_s(seconds, speed)
        effects = []
        if abs(a - drop) < 1e-3:
            effects += [{"type": "punch", "t": a, "strength": 1.0}, {"type": "stutter", "t": a, "frames": 2, "repeat": 4}]
        elif hype and int(round((a - drop) / period)) % 4 == 0:
            effects.append({"type": "punch", "t": a, "strength": 0.5})
            last_hit = k
        if k == 0 and len(beats) > 1 and beats[0] < b - 0.1:
            first = next((d for d in downbeats if a + 0.1 <= d < b - 0.15), None)
            if first is not None:
                effects += [{"type": "punch", "t": first, "strength": 1.0}, {"type": "stutter", "t": first, "frames": 2, "repeat": 3}]
        if hype and k > 0 and abs(shots[-1]["start"] - drop) < 1e-3 and seconds > 0.5:
            # demo1's 60 ms dead stop, then the hardest hit, a third of the way in
            hold_t, hit_t = a + seconds * 0.2, a + seconds * 0.36
            effects = [e for e in effects if e["type"] != "punch"]
            effects += [{"type": "hold", "t": round(hold_t, 4), "len": 0.12},
                        {"type": "punch", "t": round(hit_t, 4), "strength": 1.0},
                        {"type": "skip", "t": round(hit_t, 4), "amount": 0.3}]
        shot = {"start": round(a, 4), "end": round(b, 4), "render_s": render_s, "speed": round(render_s / seconds, 3),
                "effects": effects}
        if not hype and abs(b - drop) < 1e-3:
            shot["ease"] = "in"
        shots.append(shot)
    if last_hit is not None and last_hit == len(shots) - 1:
        s = shots[last_hit]
        if s["end"] - s["start"] > 0.6:
            s["effects"].append({"type": "reverse", "t": s["start"], "len": 0.4})
    for s in shots:
        s["effects"] = sorted({(e["type"], e["t"]): e for e in s["effects"]}.values(), key=lambda e: e["t"])
    return {"name": f"dense ({count} forms)" if count else "dense (auto)", "drop": round(drop, 4), "shots": shots}


# ---- the story plan: a full song has verses that breathe, choruses that drive and one drop that punches
# "viscous" (the Simple default since the 24 Oct A/B, judged on pour tempo, the drop transition and colour): the
# demo's pour. Shots run two bars in the loud passages too and a bar on the drop, so a 3 s morph plays at or under
# real time instead of being compressed into half-bar cuts (the long-song chain plays clip_s / shot).
STORY_BEATS_VISCOUS = {"intro": 8, "calm": 8, "sustain": 8, "build": 8, "release": 8, "drop": 4, "drop_late": 8, "outro": 8}
# "tight" (``pace: "tight"``): the denser story plan; builds and choruses cut on the bar, the drop's first bars on the half bar.
STORY_BEATS = {"intro": 8, "calm": 8, "sustain": 8, "build": 4, "release": 4, "drop": 2, "drop_late": 4, "outro": 8}
STORY_PACES = ("viscous", "tight")
STORY_PACE_DEFAULT = "viscous"
STORY_SPEED = {"intro": 1.0, "calm": 1.0, "sustain": 1.1, "build": 1.25, "release": 1.25, "drop": 2.5, "drop_late": 1.6, "outro": 1.0}
DROP_HALF_BARS = 8  # bars after the drop that cut on the half bar


def _story_roles(sections: list[dict], duration: float, min_len: float = 6.0) -> list[dict]:
    """Sections with a story role: intro / calm / sustain / build / drop / release / outro, from the
    analysis labels and each section's level against the song's loudest."""
    rows = [dict(sec) for sec in sections if float(sec.get("end", 0)) > float(sec.get("start", 0))]
    if not rows:
        return [{"start": 0.0, "end": float(duration), "label": "calm", "level": 0.5, "role": "calm"}]
    # The analyser slices finely (a run of 2 s "drop" spans): merge same-label neighbours, then fold anything
    # shorter than ``min_len`` into the neighbour whose level is closer, so a section is a passage, not a bar.
    top0 = max(float(r.get("level") or 0.0) for r in rows) or 1.0
    merged: list[dict] = []
    for r in rows:
        same = merged and merged[-1]["label"] == r.get("label")             and abs(float(merged[-1]["level"]) - float(r.get("level") or 0.0)) < 0.3 * top0  # a quiet and a loud verse differ
        if same:
            prev = merged[-1]
            wa, wb = prev["end"] - prev["start"], float(r["end"]) - float(r["start"])
            prev["level"] = (float(prev.get("level") or 0) * wa + float(r.get("level") or 0) * wb) / max(wa + wb, 1e-6)
            prev["end"] = float(r["end"])
        else:
            merged.append({"label": str(r.get("label") or "calm"), "start": float(r["start"]), "end": float(r["end"]),
                           "level": float(r.get("level") or 0.0)})
    changed = True
    while changed and len(merged) > 1:
        changed = False
        for i, r in enumerate(merged):
            if r["end"] - r["start"] >= min_len:
                continue
            nb = [j for j in (i - 1, i + 1) if 0 <= j < len(merged)]
            j = min(nb, key=lambda j: abs(merged[j]["level"] - r["level"]))
            a, b = (merged[j], r) if j < i else (r, merged[j])
            wa, wb = a["end"] - a["start"], b["end"] - b["start"]
            keep = merged[j]
            keep["level"] = (a["level"] * wa + b["level"] * wb) / max(wa + wb, 1e-6)
            keep["start"], keep["end"] = min(a["start"], b["start"]), max(a["end"], b["end"])
            del merged[i]
            changed = True
            break
    rows = merged
    top = max(float(r.get("level") or 0.0) for r in rows) or 1.0
    for i, r in enumerate(rows):
        label = str(r.get("label") or "calm")
        level = float(r.get("level") or 0.0) / top
        role = label if label in STORY_BEATS else "calm"
        if role in ("calm", "sustain") and level > 0.72:
            role = "build"  # a loud "calm" section is a chorus that drives
        if i == 0 and role in ("calm", "sustain", "build"):
            role = "intro"
        if i == len(rows) - 1 and role in ("calm", "sustain", "release") and len(rows) > 1:
            role = "outro"
        r["role"] = role
    return rows


def story_pace(state: dict | None) -> str:
    """The cut's pace from ``state["pace"]``: "viscous" (the demo's pour, the default) or "tight" (the denser
    story plan). Anything else is the default."""
    pace = str((state or {}).get("pace") or STORY_PACE_DEFAULT).strip().lower()
    return pace if pace in STORY_PACES else STORY_PACE_DEFAULT


def story_plan(duration: float, beats: list, sections: list[dict], drop: float | None = None,
               max_shots: int | None = None, pace: str = STORY_PACE_DEFAULT) -> dict:
    """The music-video cut for a whole song. Every passage breathes (two bars a shot, so a morph plays at or
    under real time; light punches on the downbeats of builds and choruses), the drop punches and cuts on the
    bar for its first bars, the outro eases out. ``pace="tight"`` is the denser plan: a bar a shot on builds
    and choruses, half bars on the drop. Every section switch starts a shot and is marked as a boundary for a
    transition. When the shot budget is exceeded, every section's shots get longer."""
    table = STORY_BEATS if pace == "tight" else STORY_BEATS_VISCOUS
    duration = float(duration)
    max_shots = shot_budget(duration) if max_shots is None else int(max_shots)
    grid = sorted(float(b) for b in beats if 0.0 <= float(b) < duration)
    if len(grid) < 4:
        return dense_plan(duration, beats, drop, max_shots)
    period = _period(grid)
    roles = _story_roles(sections, duration, min_len=max(6.0, 8 * period))  # a passage is at least two bars
    if drop is None:
        drops = [r for r in roles if r["role"] == "drop"]
        drop = float(drops[0]["start"]) if drops else None
    if drop is not None:
        drop = min(grid, key=lambda b: abs(b - drop))
        for r in roles:  # the drop section starts on the drop itself when the analysis put it within a bar
            if r["role"] == "drop" and abs(float(r["start"]) - drop) <= 4 * period + 1e-6 and float(r["start"]) != drop:
                r["start"] = drop

    def nearest(t: float) -> float:
        return min(grid, key=lambda b: abs(b - t))

    for stretch in (1, 2, 4, 8):
        cuts: list[tuple[float, str, bool]] = []  # (time, role, section_start)
        for r in roles:
            a, b = (0.0 if not cuts else nearest(float(r["start"]))), float(r["end"])
            if cuts and a <= cuts[-1][0] + 0.25:
                a = cuts[-1][0]
            role = r["role"]
            t = a
            first = True
            while t < b - 0.3 and t < duration - 0.3:
                here = role
                if role == "drop" and drop is not None and t >= drop + DROP_HALF_BARS * 4 * period - 1e-6:
                    here = "drop_late"
                if not cuts or t > cuts[-1][0] + 0.25:
                    cuts.append((round(t, 4), here, first))
                first = False
                step = table[here] * stretch
                i = grid.index(nearest(t))
                t = grid[i + step] if i + step < len(grid) else duration
        if drop is not None and all(abs(c[0] - drop) > 1e-6 for c in cuts):
            cuts.append((round(drop, 4), "drop", True))
        best: dict[float, tuple] = {}
        for c in cuts:  # one cut per time; a section start (or the drop itself) outranks a plain beat cut there
            prev = best.get(c[0])
            if prev is None or (c[2] and not prev[2]) or (c[1] == "drop" and prev[1] != "drop"):
                best[c[0]] = c
        cuts = sorted(best.values())
        if len(cuts) <= max_shots:
            break
    times = [c[0] for c in cuts] + [round(duration, 4)]
    shots = []
    for k, ((a, role, starts), b) in enumerate(zip(cuts, times[1:])):
        seconds = b - a
        if seconds < 0.3:
            continue
        speed = STORY_SPEED.get(role, 1.25)
        render_s = _render_s(seconds, speed)
        effects = []
        downbeat = nearest(a)
        if drop is not None and abs(a - drop) < 1e-3:
            effects += [{"type": "punch", "t": a, "strength": 1.0}, {"type": "stutter", "t": a, "frames": 2, "repeat": 4}]
        elif role in ("drop", "drop_late", "build") and abs(downbeat - a) < 1e-3:
            effects.append({"type": "punch", "t": a, "strength": 0.6 if role != "build" else 0.4})
        shot = {"start": round(a, 4), "end": round(b, 4), "render_s": render_s, "speed": round(render_s / seconds, 3),
                "effects": effects, "section": role}
        if starts:
            if drop is not None and abs(a - drop) < 1e-3:
                kind = "drop"
            elif k > 0 and table.get(role, 4) > table.get(cuts[k - 1][1], 4):
                kind = "silence"  # dropping into a quieter section
            else:
                kind = "switch"
            if k > 0:
                shot["boundary"] = kind
        if role == "intro" and k == 0:
            shot["ease"] = "in"
        if role == "outro" and k == len(cuts) - 1:
            shot["ease"] = "out"
        shots.append(shot)
    if shots:
        shots[-1]["end"] = round(duration, 4)
    return {"name": "story", "drop": round(drop, 4) if drop is not None else None, "shots": shots,
            "roles": [(r["role"], round(float(r["start"]), 2), round(float(r["end"]), 2)) for r in roles]}


BLOCKY = {"datamosh": "chroma-split"}  # the blocky transitions and what stands in for them while the smear is off


def boundary_transitions(shots: list[dict], vibe: str, *, seed: int = 0, smear: str = "off") -> list[dict | None]:
    """One premium transition per section boundary (the vibe's recommendation for drop / switch / silence),
    capped at two uses per type by the guardrail; everything else is a clean handoff. One entry per shot. With the
    blocky smear off (``smear``, boundary_fx.SMEAR; the default), a vibe's datamosh is a chromatic split instead."""
    from xenoform import boundary_fx as _B
    from xenoform import transitions_fx as T

    idx = [i for i, s in enumerate(shots) if i > 0 and s.get("boundary")]
    if not idx:
        return [None] * len(shots)
    kinds = [T.recommend(vibe, str(shots[i]["boundary"])) for i in idx]
    # the Simple cut renders no GPU scene morph, so a vibe's scene-morph drop was a plain handoff: match-cut instead
    kinds = ["match-cut" if k == "scene-morph" else k for k in kinds]
    if _B.smear_of(smear) == "off":
        kinds = [BLOCKY.get(k, k) for k in kinds]
    kinds, _msgs = T.guard(kinds, seed=seed)
    out: list[dict | None] = [None] * len(shots)
    for i, kind in zip(idx, kinds):
        if kind in T.EXEMPT_FROM_CAP:
            continue
        frames = int(min(12, max(4, int(shots[i].get("frames") or 24) // 3, 4), (int(shots[i - 1].get("frames") or 24) // 2)))
        out[i] = {"kind": kind, "frames": frames, "boundary": shots[i]["boundary"]}
    return out


def flow_plan(duration: float, beats: list, count: int) -> dict:
    """Flow energy with a fixed count: even, beat-snapped shots, no effects."""
    cuts = count_cuts(duration, beats, count, None)
    shots = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        render_s = _render_s(b - a, 1.0)
        shots.append({"start": a, "end": b, "render_s": render_s, "speed": round(render_s / (b - a), 3), "effects": []})
    return {"name": f"flow ({count} forms)", "shots": shots}


_DROPS: dict[tuple, float | None] = {}  # (path, size, mtime, beats) -> drop time: one decode a song, not one a plan


def find_drop(audio_path: Path | None, beats: list, duration: float) -> float | None:
    if audio_path is None or not Path(audio_path).is_file():
        return None
    try:
        st = Path(audio_path).stat()
        key = (str(Path(audio_path).resolve()), st.st_size, st.st_mtime_ns, len(beats or []),
               round(float(beats[0]), 3) if beats else 0.0, round(float(beats[-1]), 3) if beats else 0.0)
    except OSError:
        key = None
    if key is not None and key in _DROPS:
        return _DROPS[key]
    try:
        got = beatfx.drop_time(Path(audio_path), beats)
    except Exception:
        log.exception("drop detection")
        return None
    if key is not None:
        if len(_DROPS) > 64:
            _DROPS.clear()
        _DROPS[key] = got
    return got


def _analysis_sections(directed: dict) -> list[dict]:
    """The analyser's sections (apply_director keeps them as ``analysis_sections`` when its blocks replace
    ``sections``); a raw analysis dict carries them as ``sections``."""
    rows = directed.get("analysis_sections")
    if rows is None:
        rows = directed.get("sections")
    return [r for r in (rows or []) if r.get("label")]


PLAN_KEYS = ("section", "boundary", "heat", "drop_run", "passage", "rest", "event", "ramp")  # what custom_shots does not carry


def paced(state: dict, directed: dict) -> bool:
    """True when the Make is planned by the pacing engine (``pacing.song_plan``): a Dense cut of a song over
    ``LONG_SONG_S`` with sections, unless it is shaped as before (``pacing.legacy``) or carries its own cut plan."""
    from xenoform import pacing as _pc

    return (not _pc.legacy(state) and not state.get("cut_plan") and options(state)["energy"] == "dense"
            and float(directed.get("duration") or 0.0) > LONG_SONG_S and len(_analysis_sections(directed)) >= 2)


def song_plan_for(state: dict, directed: dict, drop: float | None) -> dict:
    """The pacing engine's plan for this Make: the roles always run, and a requested Forms count, an off-centre Speed
    and the guardrail's budget (``form_budget``, forms per 20 s) scale it by role instead of replacing it."""
    from xenoform import pacing as _pc

    duration = float(directed.get("duration") or 0.0)
    beats = list(directed.get("beats") or [])
    sections = _analysis_sections(directed)
    try:
        cap = int(state.get("max_shots") or 0) or None
    except (TypeError, ValueError):
        cap = None
    try:
        budget = float(state.get(_pc.FORM_BUDGET_KEY) or 0.0)
    except (TypeError, ValueError):
        budget = 0.0
    if budget > 0:  # the morph_density guardrail's budget, spent by role inside the planner
        allowed = max(1, int(round(duration / 20.0 * budget)))
        cap = min(cap, allowed) if cap else allowed
    kw = dict(max_shots=cap, breathe=_pc.breathe_of(state), drop_mode=_pc.drop_mode_of(state), pace=story_pace(state),
              tempo=directed.get("tempo"))
    plan = _pc.song_plan(duration, beats, sections, drop, **kw)
    n = morph_count(state)
    speed = macros(state)["speed"]
    target = None
    if n != "auto":
        target = int(n)
    elif abs(speed - 0.5) > 0.05:  # the Speed knob scales the plan's own count: x0.6 at 0, x1.4 at 1
        target = max(1, int(round(len(plan["shots"]) * (0.6 + 0.8 * max(0.0, min(1.0, float(speed)))))))
    if target and target != len(plan["shots"]):
        plan = _pc.song_plan(duration, beats, sections, drop, target=target, **kw)
        plan["target"] = target
    return plan


def shots_for(state: dict, directed: dict, audio_path: Path | None, *, drop: float | None = None) -> tuple[list[dict], dict]:
    """Validated shots plus the plan they came from. ``drop`` (seconds) stands in for the song's own when the caller
    has it and no audio (the desk's estimate)."""
    duration = float(directed.get("duration") or 0.0)
    beats = list(directed.get("beats") or [])
    if paced(state, directed):
        plan = song_plan_for(state, directed, drop if drop is not None else find_drop(audio_path, beats, duration))
        shots = custom_shots(plan, duration)
        for shot, raw in zip(shots, plan.get("shots") or []):
            for key in PLAN_KEYS:
                if raw.get(key) is not None and raw.get(key) != "":
                    shot[key] = raw[key]
        return shots, plan
    opt = options(state)
    n = morph_count(state)
    speed = macros(state)["speed"]
    if n == "auto" and abs(speed - 0.5) > 0.05 and not state.get("cut_plan"):
        n = speed_count(duration, beats, opt["energy"], speed)  # the speed macro biases the cut density
    # ``max_shots``: the cap a long cut re-plans to when the tier or the pool affords fewer morphs than shots (no
    # object repeats): the planners make fewer, longer shots on the bars rather than the cut folding them afterwards
    try:
        max_shots = int(state.get("max_shots") or 0) or None
    except (TypeError, ValueError):
        max_shots = None
    if state.get("cut_plan"):
        plan = state["cut_plan"]
    elif opt["energy"] == "dense" and n == "auto" and duration > LONG_SONG_S and len(_analysis_sections(directed)) >= 2:
        drop = drop if drop is not None else find_drop(audio_path, beats, duration)
        plan = story_plan(duration, beats, _analysis_sections(directed), drop, max_shots=max_shots, pace=story_pace(state))
    elif opt["energy"] == "dense":
        drop = drop if drop is not None else find_drop(audio_path, beats, duration)
        count = None if n == "auto" else n
        if max_shots and (count is None or count > max_shots):
            count = max_shots
        plan = dense_plan(duration, beats, drop, max_shots=max_shots, count=count)
    elif n != "auto" or max_shots:
        plan = flow_plan(duration, beats, min(n, max_shots) if (n != "auto" and max_shots) else (max_shots if n == "auto" else n))
    else:
        return plan_shots(duration, beats), {"name": "flow", "shots": []}
    shots = custom_shots(plan, duration)
    for shot, raw in zip(shots, plan.get("shots") or []):  # custom_shots keeps the timing; carry the story keys
        for key in ("section", "boundary"):
            if raw.get(key):
                shot[key] = raw[key]
    return shots, plan


def _stretch(shots: list[dict], duration: float) -> list[dict]:
    """Scale shot lengths so they still fill ``duration`` after dropping some."""
    total = sum(float(s.get("seconds") or 0.0) for s in shots)
    if not shots or total <= 0 or duration <= 0:
        return shots
    k = duration / total
    out, t = [], 0.0
    for s in shots:
        sec = float(s.get("seconds") or 0.0) * k
        row = {**s, "seconds": round(sec, 4)}
        if "start" in row:
            row["start"] = round(t, 4)
        if "frames" in row:
            row["frames"] = max(1, int(round(sec * 24)))
        out.append(row)
        t += sec
    return out


DRAFT_916 = (320, 576)  # Draft 9:16 morphs render natively in portrait (same pixel budget as 512x288)


CHAIN_FILE = "chain.json"


def write_chain(work: Path, stills: list[dict]) -> Path | None:
    """``<work>/chain.json``: the stills this render morphs through, in order (``noun``, ``kind``), written once the
    line's stills are grown and picked, so the desk's making screen shows the chain Make made rather than the Chain
    row's pre-Make preview (which never has the rally car "car rally race" grows, 28 Oct). Never breaks a render."""
    rows = [{"noun": str(s.get("noun") or Path(str(s.get("file") or s.get("path") or "")).stem.split("_", 1)[-1].replace("_", " ")),
             "kind": str(s.get("kind")) if str(s.get("kind") or "") in ("scene", "clip") else "object"} for s in stills or []]
    try:
        path = Path(work) / CHAIN_FILE
        path.write_text(json.dumps(rows), encoding="utf-8")
        return path
    except OSError:
        return None


def _draft_clips(shots, stills, work, cfg, seed, vibe, client, cancel, state=None, report=None, size=None, styles=None,
                 prompt=None, negative=None):
    from xenoform.cloud_morph import _local_clips

    return _local_clips(shots, stills, work, cfg, seed, vibe, client=client, cancel=cancel, state=state, report=report,
                        size=size, styles=styles, prompt=prompt, negative=negative)


def run_simple(directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
               report: Callable[[str, float, str], None], *, cancel: Callable[[], bool] | None = None,
               client=None, engine: str | None = None) -> dict:
    """Plan, render on open weights, then compose with the beat FX at the chosen aspect."""
    from xenoform import idea as _idea
    from xenoform import morph_pass as _mp

    from xenoform import clip_cut

    if options(state)["cloud"] and not state.get("cloud_final_ok"):
        # it spends the account's Comfy Cloud credits: only a Make that says so (the desk's tick) runs it; cloud_confirm is
        # the paid partner path's token, a different thing. Checked before the clips cut too, so no tier slips past it.
        raise RuntimeError("Cloud Final spends Comfy Cloud credits: tick \"Spend my Comfy Cloud credits\" to run it. Nothing was sent.")
    if clip_cut.wants(state):  # Clips mode: only the user's clips, each morphing into the next (Tys, 28 Oct)
        return clip_cut.run(directed, Path(audio_path), Path(out_path), Path(work), cfg, state, report, cancel=cancel,
                            client=client, engine=engine)
    started = time.perf_counter()
    # the idea line shapes a Simple cut (xenoform.idea): Scenes to Mix when it names a place, Polly on when it names a
    # dancer or singer, the reading kept for the pick and the record; the model refines it when XENO_LLM_URL is set
    reading: dict | None = None
    if _idea.applies(state) and str(state.get("idea") or "").strip():
        reading = state["idea_reading"] if isinstance(state.get("idea_reading"), dict) \
            else _idea.read(str(state["idea"]), str(state.get("vibe") or ""))
        state = _idea.shape_state(state, reading)
    opt = options(state)
    scene_choice = _mp.scenes_choice(state)  # off / mix / only: whether the chain morphs scenes as well as objects
    work = Path(work) / "simple"
    work.mkdir(parents=True, exist_ok=True)
    shots, plan = shots_for(state, directed, Path(audio_path))
    duration = float(directed.get("duration") or 0.0)
    long_song = duration > LONG_SONG_S and not plan.get("stills") and not state.get("cut_plan")
    pre_notes: list[dict] = []  # what the plan decided before the render; folded into the record's notes below
    chain: dict = {}
    line_notes: list[dict] = []
    if reading:
        # the scenes and shapes the line asks for, grown first so the pick below finds them (a few stills, about six
        # seconds each, only when ComfyUI has Z-Image; auto_grow False turns it off, as for the family grow)
        grown_line = grow_for_idea(state, _mp.vibe_for(state), cfg, report, engine=engine, reading=reading)
        if grown_line:
            line_notes.append({"grown_for_line": grown_line})
    if long_song:
        # Music-video mode: one morph a shot, no object twice (see clip_plan); the pool and the tier cap it, and
        # a cut past the cap gets fewer, longer shots instead of a loop (long_song_chain, shared with the animatic)
        if opt["cloud"]:
            # a cut past 64 s plans more morphs than Cloud Final takes: say so now, before the family grows and the
            # stills are picked, not after (cloud_clips refuses the same count late)
            _cloud_fits(long_song_chain(state, directed, Path(audio_path), shots, plan, opt, grow=False)[2])
        shots, plan, chain, pre_notes = long_song_chain(state, directed, Path(audio_path), shots, plan, opt, cfg=cfg,
                                                        report=report, engine=engine)
        if opt["cloud"]:
            _cloud_fits(chain)  # the grown family may have let the chain afford more
        vibe, stills = stills_for({**state, "cut_plan": None}, chain["morphs"] + 1,  # n morphs need n + 1 distinct stills
                                  **_scene_kw(state, shots, chain["morphs"] + 1, chain["assign"]))
        for shot, ci in zip(shots, chain["assign"]):
            shot["clip"] = int(ci)
            shot["render_s"] = int(chain["clip_s"])
            shot["speed"] = round(chain["clip_s"] / max(float(shot.get("seconds") or 0.1), 0.1), 3)
        render_shots = [{"index": i, "start": round(i * chain["clip_s"], 4), "end": round((i + 1) * chain["clip_s"], 4),
                         "seconds": float(chain["clip_s"]), "render_s": int(chain["clip_s"]),
                         "frames": int(chain["clip_s"] * FPS), "effects": []} for i in range(chain["morphs"])]
        report("restyle", 0.05, f"{len(shots)} shots on the beat, {chain['morphs']} morphs ({chain['clip_s']} s each), "
                                f"no object twice")
    else:
        render_shots = shots
    vibe, stills = (vibe, stills) if long_song else stills_for({**state, "cut_plan": plan if plan.get("stills") else None}, len(shots) + 1,
                                                                **_scene_kw(state, shots, len(shots) + 1))
    repeat_note = ""
    unique = len({str(s.get("path")) for s in stills})
    if unique < len(stills) and not plan.get("stills") and not long_song:
        # guardrail no_repeat: the still pool wrapped. Use fewer, longer morphs so no still repeats.
        n = max(1, unique - 1)
        shots, plan = shots_for({**state, "morph_count": n}, directed, Path(audio_path))
        if len(shots) > n:  # a planner that ignores the count: keep the first n shots, stretched to fill
            shots = _stretch(shots[:n], float(directed.get("duration") or 0.0))
        vibe, stills = stills_for({**state, "cut_plan": None}, len(shots) + 1, **_scene_kw(state, shots, len(shots) + 1))
        render_shots = shots
        repeat_note = (f"Only {unique} distinct stills in the {vibe} pool: {len(shots)} longer morphs instead of "
                       f"repeating stills. Add stills (or pick a bigger vibe) for faster morphing.")
        report("restyle", 0.05, repeat_note)
    from xenoform import guardrails as _guard

    hp = house(state, cfg)
    vertical_house = opt["aspect"] == "9:16" and str((hp.get("format") or {}).get("aspect") or "") == "9:16"
    background = state.get("still_background")
    if background is None and vertical_house and (hp.get("look") or {}).get("morph_background") == "black":
        # The house look wants morphs on black, but crushing a gradient ground (cosmic's indigo glow, liquid-gold's
        # umber) to black cuts the glow into a dome on a flat floor. Only stills whose ground already is black get
        # the crush; the others keep their own ground, which the portrait canvas extends.
        background = "black" if ground_is_black(stills) else None
    if background == "black":
        from xenoform.portrait import black_stills

        stills = black_stills(stills, work)
    shots = _guard.carry_block_fx(shots, state)
    seed = int(state.get("seed") or 2727)
    engine = engine or ("ltx23" if opt["tier"] == "final" else "ltx25cloud" if opt["cloud"] else "ltx095")
    native = opt["aspect"] == "9:16" and opt["vertical"] == "native" and engine in {"ltx23", "mock"} \
        and opt["tier"] == "final"
    # Draft 9:16: re-lay every still whole on a portrait canvas and render the morphs in portrait, so a wide object
    # (a ribbon, a helix) is never cropped; the old path cut a 9:16 window out of a 16:9 render.
    native_draft = (opt["aspect"] == "9:16" and opt["tier"] != "final" and engine in {"ltx095", "mock"}
                    and str(state.get("vertical_mode") or "").strip().lower() != "crop")  # an explicit Crop keeps the old window
    from xenoform import final_tier

    size = final_tier.sizes(True)["out"] if native else None
    fmt = hp.get("format") or {}
    if native and vertical_house and fmt.get("native_vertical") and not os.environ.get("XENO_FINAL_916_OUT", "").strip():
        size = (int(fmt.get("width") or size[0]), int(fmt.get("height") or size[1]))  # the house output size (1080x1920)
    fps = int(fmt.get("fps") or beatfx.FPS) if vertical_house else beatfx.FPS
    notes: list[dict] = list(line_notes) + list(pre_notes)
    scene_files = [s["file"] for s in stills if s.get("kind") == "scene"]  # which stills of the chain are scenes
    if scene_choice != "off" and not scene_files:
        notes.append({"scenes": f"{scene_choice} asked, but the {vibe} pool has no scenes yet: objects only "
                                f"(Fine-tune > Library > Grow scenes, or xenoform stills grow {vibe} --kind scene)"})
    elif scene_files:
        report("restyle", 0.08, f"{len(scene_files)} scene{'s' if len(scene_files) != 1 else ''} in the chain ({scene_choice})")
    # how each morph changes (morph_style): the shot list a Final carries over from its prototype, the setting, or Auto
    # (Melt in the verses, Shatter on the drop, Bloom / Fold / Spin by the Chaos knob); a long song's chain morph takes
    # the style of the first shot that plays it
    from xenoform import morph_style as _ms

    shot_styles = _ms.for_cut({**state, "macros": macros(state)}, shots, plan.get("drop"))
    if long_song:
        firsts: dict[int, str] = {}
        for k, ci in enumerate(chain["assign"]):
            firsts.setdefault(int(ci), shot_styles[k] if k < len(shot_styles) else "melt")
        render_styles = [firsts.get(i, "melt") for i in range(len(render_shots))]
    else:
        render_styles = list(shot_styles)
    if any(s != "melt" for s in render_styles):
        notes.append({"morph_styles": _ms.info(render_styles)})
    write_chain(work, stills)  # the making screen's "The chain:" line, now with what the line grew (ui._run_job)
    if engine == "ltx25cloud":
        from xenoform import cloud_final as _cf

        label = f"Cloud Final ({_cf.label()} on Comfy Cloud)"
    else:
        label = f"Final ({final_tier.label()})" if engine == "ltx23" else "Draft (LTX 0.9.5)"
    report("restyle", 0.1, f"{len(render_shots)} {label} morphs · "
                           f"{len(shots)} shots · {opt['energy']} · {opt['aspect']}")
    if native_draft:
        from xenoform.portrait import portrait_stills

        stills = portrait_stills(stills, work, DRAFT_916[0], DRAFT_916[1], background=background)
        notes.append({"native_draft": f"{DRAFT_916[0]}x{DRAFT_916[1]} portrait morphs from re-laid stills"})
    if engine == "mock":
        from xenoform.cloud_morph import _mock_clips

        if native:
            from xenoform.portrait import portrait_stills

            clips = _mock_clips(render_shots, portrait_stills(stills, work, background=state.get("still_background")), work,
                                *final_tier.RENDER_916)
        elif native_draft:
            clips = _mock_clips(render_shots, stills, work, *DRAFT_916)
        else:
            clips = _mock_clips(render_shots, stills, work, 768, 432)
    elif engine == "ltx23":
        from xenoform.final_tier import final_clips

        def draft(indices: list[int]) -> dict[int, Path]:
            got = {}
            for k, i in enumerate(indices):
                got[i] = _draft_clips([render_shots[i]], [stills[i], stills[i + 1]], work, cfg, seed + i, vibe, client, cancel, state,
                                      styles=[render_styles[i]])[0]
                renamed = work / f"draft_fallback{i:02d}.mp4"
                shutil.move(str(got[i]), renamed)
                got[i] = renamed
            return got

        # its fallback notes join the cut's (they used to replace them: a Final lost its grown-for-the-line note)
        clips, final_notes = final_clips(render_shots, stills, work, cfg, seed, vibe, client=client, cancel=cancel, report=report,
                                         draft=draft, vertical=native, state=state, styles=render_styles)
        notes.extend(final_notes)
    elif engine == "ltx25cloud":
        from xenoform import cloud_final, upscale_pass

        vertical = opt["aspect"] == "9:16"

        def draft(indices: list[int]) -> dict[int, Path]:  # a shot that fails on Cloud: its Draft morph, here
            from xenoform.portrait import portrait_stills

            got = {}
            for i in indices:
                pair = [stills[i], stills[i + 1]]
                if vertical:
                    pair = portrait_stills(pair, work, DRAFT_916[0], DRAFT_916[1], background=background)
                clip = _draft_clips([render_shots[i]], pair, work, cfg, seed + i, vibe, client, cancel, state,
                                    size=DRAFT_916 if vertical else None, styles=[render_styles[i]])[0]
                got[i] = work / f"draft_fallback{i:02d}.mp4"
                shutil.move(str(clip), got[i])
            return got

        clips, cloud_notes = cloud_final.cloud_clips(render_shots, stills, work, cfg, seed, vibe, cancel=cancel, report=report,
                                                     draft=draft, vertical=vertical, state=state, styles=render_styles)
        notes.extend(cloud_notes)
        # the clips go to full size at their own aspect (as Fast Final's do); the cut composes at the aspect's size, so a
        # 1:1 cut is cropped around the object rather than squashed to a square
        full = upscale_pass.OUT_916 if vertical else upscale_pass.OUT_169
        clips, up_notes = cloud_final.to_full_size(clips, work, full, cfg, fallbacks=[n["shot"] for n in cloud_notes],
                                                   client=client, cancel=cancel, report=report, fps=fps)
        size = upscale_pass.out_size(opt["aspect"])
        notes.append({"cloud_final": f"{len(clips) - len(cloud_notes)} of {len(clips)} morphs rendered with {cloud_final.label()} on "
                                     f"Comfy Cloud (open weights), scaled here to {full[0]}x{full[1]}"})
        notes.extend(up_notes)
    else:
        clips = _draft_clips(render_shots, stills, work, cfg, seed, vibe, client, cancel, state, report=report,
                             size=DRAFT_916 if native_draft else None, styles=render_styles)
        if opt["fast"] and engine == "ltx095":
            from xenoform import upscale_pass

            # portrait Draft clips go to 1080x1920, landscape ones to 1920x1080; the cut composes at the aspect's size
            clips, fast_notes = upscale_pass.upscale_clips(clips, work, upscale_pass.OUT_916 if native_draft else upscale_pass.OUT_169,
                                                           cfg, client=client, cancel=cancel, report=report, fps=fps)
            size = upscale_pass.out_size(opt["aspect"])
            notes.append({"fast_final": f"{len(clips)} Draft morphs upscaled to {size[0]}x{size[1]} ({upscale_pass.MODEL})"})
            notes.extend(fast_notes)
    if long_song:
        clips = [clips[ci] for ci in chain["assign"]]  # one entry per shot, walking the loop
        shot_styles = [render_styles[int(ci)] for ci in chain["assign"]]  # what each shot's morph was rendered as
    else:
        shot_styles = list(render_styles)
    for i, s in enumerate(shots):  # which morph each shot plays: a swap after the cut finds the two that touch a still
        s["morph"] = int(s.get("clip", i))
    performer_info: dict = {"shots": 0, "slots": [], "notes": []}
    n_perf = opt.get("performer") or 0
    # a long song gets its slots as before; a short clip gets one only when the idea line asked for her ("girl
    # dancing" on the 12 s demo: one slot of the first passage, the morphs after it)
    if n_perf and (long_song or bool((reading or {}).get("performer"))):
        # Performer shots: MiniMax H3 (open weights, local) has the reference character sing or drum to the
        # song segment; each slot replaces a run of morph shots with one clip played 1:1 (a hard cut in and out).
        slots = performer_slots(shots, n_perf, stem_env_for(state), performer_style(state),
                                max_s=PERFORMER_MAX_S if long_song else max(PERFORMER_MIN_S, duration * 0.5))
        custom = Path(str(state.get("performer_ref") or state.get("hero_path") or "")) if (state.get("performer_ref") or state.get("hero_path")) else None
        if custom is not None and not custom.is_file():
            custom = None
        rendered: dict = {}
        for k, sl in enumerate(slots):
            still = custom or performer_reference(sl.get("instrument"), k)  # Polly, bundled: posed for the instrument when that still ships
            if still is None:
                break
            report("restyle", 0.5 + 0.08 * k / max(1, len(slots)),
                   f"Performer shot {k + 1} of {len(slots)}: {sl['instrument']} ({sl['seconds']:.1f} s)")
            lo, hi = 0.5 + 0.1 * k / max(1, len(slots)), 0.5 + 0.1 * (k + 1) / max(1, len(slots))

            def slot_report(stage: str, frac: float, detail: str, _lo=lo, _hi=hi) -> None:
                report("restyle", _lo + (_hi - _lo) * float(max(0.0, min(1.0, frac))), detail)  # the job bar keeps moving forward

            try:
                got = _render_performer(Path(audio_path), sl, vibe, still, work / "performer", cfg, seed=seed + 100 + k,
                                        report=slot_report, beats=list(directed.get("beats") or []), source=state.get("song_source"))
                rendered[sl["first"]] = got
                performer_info["slots"].append({**sl, "clip": str(got.get("clip")), "sync": got.get("sync"),
                                                "tries": got.get("tries"), "render_s": got.get("render_s")})
            except Exception as exc:  # a missing model or a failed shot must never break the cut
                log.warning("performer slot %s skipped: %s", sl, exc)
                performer_info["notes"].append(f"performer shot at {sl['start']:.1f}s skipped: {exc}")
        if rendered:
            shots, clips = apply_performer_slots(shots, clips, slots, rendered)
            performer_info["shots"] = len(rendered)
            notes.append({"performer": performer_info})
    # Your own clips (own_media): each takes a run of shots at the start of a passage, trimmed to the run's frames
    # and played 1:1 like a performer shot. The own images already lead the morph chain (state["morph_targets"]).
    own_info: dict = {"clips": 0, "images": len([p for p in (state.get("morph_targets") or []) if p]), "slots": [], "notes": []}
    own_clips = [c for c in (state.get("own_clips") or []) if isinstance(c, dict) and c.get("path")]
    if own_clips:
        from xenoform import own_media

        oslots = own_media.clip_slots(shots, own_clips, avoid=[(i, i) for i, s in enumerate(shots) if s.get("performer")])
        rendered_own: dict = {}
        # clip morphs: the slot opens on a morph from the object before into the clip and closes on one into the object
        # after (own_media.MORPH_S each), rendered on the Draft model; "clip_morph": "off" keeps plain cuts
        clip_morph = engine in {"ltx095", "ltx23"} and opt["aspect"] in {"9:16", "16:9"} \
            and str(state.get("clip_morph", "on")).strip().lower() not in {"off", "0", "false", "no"}
        for k, sl in enumerate(oslots):
            run = shots[sl["first"]:sl["last"] + 1]
            frames_needed = int(sum(int(s.get("frames") or 0) for s in run)) or int(round(float(sl["seconds"]) * fps))
            report("restyle", 0.58 + 0.02 * k / max(1, len(oslots)),
                   f"Your clip {k + 1} of {len(oslots)}: {Path(sl['clip']).name} ({sl['seconds']:.1f} s)")
            n_in, n_out = own_media.morph_frames(frames_needed, fps, into=sl["first"] > 0, out_of=sl["last"] < len(shots) - 1) \
                if clip_morph else (0, 0)
            try:
                start_s = own_media.busiest_start(sl["clip"], sl["clip_seconds"], sl["seconds"])  # the stretch with the most picture
                dest = work / "own" / f"own_{sl['start']:.2f}.mp4"
                made_clip = own_media.render_clip(sl["clip"], start_s, frames_needed - n_in - n_out, own_media.size_for(opt["aspect"]),
                                                  dest.with_name(dest.stem + "_body.mp4") if (n_in or n_out) else dest, fps=fps)
                if n_in or n_out:
                    try:
                        made_clip = _clip_morphs(made_clip, dest, sl, shots, stills, n_in, n_out, work, cfg, seed + 900 + 2 * k, vibe,
                                                 client, cancel, state, opt, native_draft, fps)
                        own_info.setdefault("morphs", 0)
                        own_info["morphs"] += int(bool(n_in)) + int(bool(n_out))
                    except Exception as exc:  # the clip still plays, cut in hard, when its morphs do not render
                        from xenoform.turbo import JobCancelled

                        if isinstance(exc, JobCancelled):
                            raise
                        log.warning("clip morphs for %s skipped: %s", sl.get("clip"), exc)
                        own_info["notes"].append(f"the morphs into and out of {Path(str(sl.get('clip'))).name} were skipped: {exc}")
                        made_clip = own_media.render_clip(sl["clip"], start_s, frames_needed, own_media.size_for(opt["aspect"]), dest, fps=fps)
                rendered_own[sl["first"]] = {"clip": made_clip}
                own_info["slots"].append({**sl, "frames": frames_needed, "file": str(made_clip), "morph_in": n_in, "morph_out": n_out})
            except Exception as exc:  # an unreadable clip must never break the cut
                log.warning("own clip %s skipped: %s", sl.get("clip"), exc)
                own_info["notes"].append(f"your clip {Path(str(sl.get('clip'))).name} at {sl['start']:.1f}s skipped: {exc}")
        if rendered_own:
            shots, clips = apply_performer_slots(shots, clips, oslots, rendered_own, mark="own")
            own_info["clips"] = len(rendered_own)
        notes.append({"own": own_info})
    if opt["tier"] != "final" and size is None and opt["aspect"] == "9:16":
        size = (540, 960)  # Draft: the morphs are 512x288 upscales anyway; the look pass runs 4x faster here
    report("assemble", 0.6, "Cutting to the beat" + (" with beat FX" if opt["fx"] else ""))
    tmp = Path(out_path).with_name(Path(out_path).stem + ".simple.mp4")
    m = macros(state)
    import copy as _copy

    plan_shots = _copy.deepcopy(shots)  # before the macros: a re-cut starts from here
    apply_macros(shots, m, hp if vertical_house else None)
    # when the change happens inside each morph (morph_timing): Smooth as the model made it, On the beat, or Snap
    from xenoform import morph_timing as _mt

    timing_mode = _mt.normal(state.get("morph_timing"))
    timed = _mt.plan(shots, timing_mode, directed.get("beats") or [], plan.get("drop"))
    if timed:
        notes.append({"morph_timing": timed})
    # the effects (xenoform.effects) and the blocky smear, off unless the effects ask for it
    from xenoform import effects as _E

    effect_names = _E.names_of(state)
    smear = _E.smear_setting(state)
    transitions = boundary_transitions(shots, vibe, seed=seed, smear=smear) if plan.get("name") == "story" else None
    # the boundary kinds (boundary_fx): Chaos decides how many handoffs smear, strobe, wipe or rip their colours apart;
    # the vibe's premium picks keep their boundaries, except the drop past Chaos 0.7, which the strobe takes
    from xenoform import boundary_fx as _B

    boundary_fx = _B.pick(shots, m, directed.get("beats") or [], fps, seed=seed, premium=transitions, drop=plan.get("drop"),
                          smear=smear)
    transitions = _B.clear_premium(transitions, boundary_fx)
    if any(boundary_fx):
        notes.append({"boundary_fx": _B.info(boundary_fx)})
    look_preset = beatfx.resolve_dance_preset(opt["dance_fx"], vibe, hp)
    if look_preset == "off" and not opt["stem_orbit"]:
        # with no look and no orbit a held still is four identical frames (dead air, 25 Oct judge panel): the orbit stays
        opt["stem_orbit"] = True
        notes.append({"orbit": "kept on: with the look off, the orbit is what keeps a held still moving"})
    stem_env = stem_env_for(state)
    report("assemble", 0.6, f"House look: dance_fx {look_preset}, stem_orbit {'on' if opt['stem_orbit'] else 'off'}, "
                            f"stems {'split' if stem_env else 'from the mix'}")
    if chain:
        notes.append({"chain": {"morphs": chain["morphs"], "clip_s": chain["clip_s"], "shots": len(shots)}})
    from xenoform import foreshadow as _fs

    fs_mode = _fs.mode_for(opt["foreshadow"], vibe)  # the next object traced, negative, sliced or silhouetted in before its shot
    if fs_mode:
        notes.append({"foreshadow": fs_mode})
    made = beatfx.compose(clips, shots, Path(audio_path), tmp, aspect=opt["aspect"],
                          quality="final" if engine == "ltx23" else "draft", fx=opt["fx"], overlay=opt["overlay"],
                          beats=directed.get("beats") or [], report=report, size=size, fps=fps,
                          dance_fx=look_preset, stem_orbit=opt["stem_orbit"], stem_env=stem_env, macros=m,
                          house=hp, end_card=opt["end_card"], seed=seed,
                          palette_image=str(stills[0]["path"]) if stills else None,
                          adaptive=str(opt.get("dance_fx") or "auto").strip().lower() == "auto",
                          transitions=transitions, foreshadow=fs_mode, boundary_fx=boundary_fx, effects=effect_names,
                          tones=_E.palette_from_clips(clips).tolist() if _E.wants_tones(look_preset, effect_names, shots) else None)
    if made.get("effects"):
        notes.append({"effects": made["effects"]})
    if made.get("look", {}).get("seconds"):
        log.info("house look took %.1fs for %d frames", made["look"]["seconds"], made["look"]["frames"])
    card = False
    if opt["end_card"]:
        report("assemble", 0.96, "Burning the end card")  # the desk's bar used to sit at 95 % through these two
        card = beatfx.end_card(tmp, opt["recipe"] or "(none)")
    report("assemble", 0.98, "Saving the video")
    shutil.copyfile(tmp, out_path)
    info = {"engine": {"ltx23": f"{final_tier.label()} 22B distilled" + (" + 4x upscale" if final_tier.model() == "ltx23" else ", scaled to full size") + " (Final)",
                       "ltx095": "LTX 0.9.5 + 4x upscale (Fast Final)" if opt["fast"] else "LTX 0.9.5 (Draft)",
                       "ltx25cloud": "Cloud Final on Comfy Cloud (open weights), scaled to full size here",
                       "mock": "mock cross-fades (test)"}[engine],
            "fast": bool(opt["fast"]), "cloud": bool(opt["cloud"]),
            "open_weights": True, "energy": opt["energy"], "aspect": opt["aspect"], "tier": opt["tier"],
            "vertical": ("native" if native else "crop") if opt["aspect"] == "9:16" else None,
            "fx": opt["fx"], "overlay": made["overlay"], "end_card": card, "vibe": vibe,
            "stills": [s["file"] for s in stills], "shots": shots, "plan_name": plan.get("name", ""), "chain": chain or None,
            "scene_mode": scene_choice, "scene_files": scene_files,  # the scenes choice and which stills were scenes
            "idea": reading,  # what the idea line was read as (xenoform.idea), or None
            # the Chain row's pins (which slots the user chose), the still preparation a swap must repeat, the swaps so far
            "pins": {str(i): s["file"] for i, s in enumerate(stills) if s.get("pinned")},
            "pinned": [i for i, s in enumerate(stills) if s.get("pinned")],
            "prep": {"background": background, "native_draft": bool(native_draft), "native": bool(native),
                     "draft_size": list(DRAFT_916) if native_draft else None},
            "swaps": [],
            "families": sorted({_fam for _fam in (s.get("family") or "" for s in stills) if _fam}),
            "plan_shots": plan_shots, "clips": [str(c) for c in clips], "audio_path": str(audio_path),
            "transitions": transitions, "boundary_fx": boundary_fx, "drop": plan.get("drop"), "size": list(size) if size else None,
            "fps": fps, "seed": seed,
            # how each shot's morph changes: the setting (auto or a style) and the style a shot was rendered in
            "morph_style": _ms.normal(state.get("morph_style") or "auto"), "morph_styles": shot_styles,
            "morph_timing": timing_mode, "effects": effect_names, "smear": smear,
            "palette_image": str(stills[0]["path"]) if stills else None, "vertical_house": vertical_house,
            "recut_state": {k: state.get(k) for k in ("vibe", "aspect", "quality_tier", "energy_preset", "dance_fx", "stem_orbit", "pace",
                                                      "beat_fx", "beat_overlay", "end_card", "stems_path", "macros", "still_background",
                                                      "performer", "performer_style", "foreshadow", "scene_stills", "chain_pins",
                                                      "morph_style", "morph_timing", "effects", "boundary_smear")},
            "roles": plan.get("roles"), "performer": performer_info, "own": own_info,
            "handoffs_s": [s["start"] for s in shots] + [shots[-1]["end"]], "fallbacks": notes,
            "beats": [round(float(b), 4) for b in (directed.get("beats") or [])],
            "render": made["size"], "frames": made["frames"], "seconds": round(time.perf_counter() - started, 2),
            "steps": 8 if engine == "ltx23" else None,
            "fps": made.get("fps", beatfx.FPS), "look": made.get("look") or {}, "foreshadow": made.get("foreshadow"), "macros": m,
            "handoffs": made.get("boundary_fx"),
            "house": str(hp.get("name") or ""), "stems_path": str(state.get("stems_path") or ""),
            # where the cut sits in the song (a Length cut is trimmed from it): the Resolve export and any later assembly
            # read it instead of finding the offset by cross-correlating the audio (the montage had to, 30 Oct)
            "window": window_of(state, duration)}
    (work / "simple.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
    return info


def window_of(state: dict, duration: float) -> dict:
    """``{"song_start", "length_s"}``: the cut's start in the song it was trimmed from (``song_source``, set by the desk
    when Length trims the song; 0 for the whole song) and its length."""
    src = state.get("song_source") if isinstance(state.get("song_source"), dict) else {}
    try:
        start = float(src.get("offset") or 0.0)
    except (TypeError, ValueError):
        start = 0.0
    return {"song_start": round(start, 3), "length_s": round(float(duration or 0.0), 3)}


def ground_is_black(stills: list[dict], *, luma: float = 16.0) -> bool:
    """True when the first still's border (the ground the morph sits on) is already near black."""
    try:
        from xenoform.portrait import load_rgb

        img = load_rgb(Path(stills[0]["path"]))
    except Exception:
        return False
    h, w = img.shape[:2]
    b = max(2, int(round(0.04 * min(h, w))))
    border = [img[:b], img[-b:], img[:, :b], img[:, -b:]]
    return float(sum(float(part.mean()) * part.size for part in border) / sum(part.size for part in border)) < luma


def chain_preview(directed: dict, state: dict, audio_path: Path) -> dict:
    """The chain a Make of ``state`` will morph through, without rendering or marking a still used: the planned shots,
    the stills in order (``stills``, n morphs over n + 1 stills) and the still each shot plays (``picks``). The stills
    animatic cuts these to the song; the Chain row shows them before Make, pins and all (``morph_pass.pins_of``)."""
    from xenoform import idea as _idea

    state = _idea.shape_state(state)  # the idea line's Scenes and Polly choices, read by the rules (no model here)
    shots, plan = shots_for(state, directed, Path(audio_path))
    duration = float(directed.get("duration") or shots[-1]["end"])
    long_song = duration > LONG_SONG_S and not plan.get("stills")
    chain: dict = {}
    # record=False: the preview shows the picks the render will make; only the render marks them used
    if long_song:
        # the same chain the render will make (pool cap, re-plan, merge), so the preview shows the same cut; it
        # does not grow the library, so a cut that grows its family may afford a few more morphs than previewed
        shots, plan, chain, _ = long_song_chain(state, directed, Path(audio_path), shots, plan, options(state), grow=False)
        vibe, pool = stills_for({**state, "cut_plan": None}, chain["morphs"] + 1, record=False,
                                **_scene_kw(state, shots, chain["morphs"] + 1, chain["assign"]))
        picks = [pool[ci] for ci in chain["assign"]]
    else:
        vibe, pool = stills_for({**state, "cut_plan": plan if plan.get("stills") else None}, len(shots) + 1, record=False,
                                **_scene_kw(state, shots, len(shots) + 1))
        picks = pool[:len(shots)]
    return {"shots": shots, "plan": plan, "long_song": long_song, "chain": chain, "vibe": vibe, "stills": pool, "picks": picks,
            "duration": duration}


def stills_animatic(directed: dict, state: dict, audio_path: Path, out_path: Path, work: Path, *,
                    size: tuple[int, int] = (216, 384), fps: int = 12) -> dict:
    """The Simple-mode draft: the vibe's stills hard-cut on the planned shots with the song, in a few
    seconds, so the first thing on screen is the real cut's skeleton (not the CPU blob animatic)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    pre = chain_preview(directed, state, Path(audio_path))  # the one chain the render makes and the Chain row shows
    shots, duration, long_song, vibe, picks = pre["shots"], pre["duration"], pre["long_song"], pre["vibe"], pre["picks"]
    w, h = int(size[0]), int(size[1])
    if h > w:  # portrait: the whole object re-laid on the house ground, as the render will be
        from xenoform.portrait import portrait_stills

        hp = house(state)
        background = state.get("still_background")
        if background is None and (hp.get("look") or {}).get("morph_background") == "black"                 and str((hp.get("format") or {}).get("aspect") or "") == "9:16":
            background = "black" if ground_is_black(picks) else None  # same rule as run_simple
        uniq = {}
        for still in picks:
            uniq.setdefault(str(still["path"]), still)
        laid = {k: v for k, v in zip(uniq, portrait_stills(list(uniq.values()), work / "portrait_draft", w, h, background=background))}
        picks = [laid[str(still["path"])] for still in picks]
    lines = []
    for shot, still in zip(shots, picks):
        path = str(still["path"]).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{path}'\nduration {max(0.05, float(shot['end']) - float(shot['start'])):.4f}")
    lines.append("file '" + str(picks[-1]["path"]).replace(chr(92), "/").replace("'", "'\\''") + "'")  # the concat demuxer needs the last file twice
    listing = work / "animatic_stills.txt"
    listing.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.mp4")
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=yuv420p,fps={fps}")
    from xenoform.video import ffmpeg_bin

    cmd = [ffmpeg_bin(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio_path),
           "-map", "0:v", "-map", "1:a", "-vf", vf, "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True)
    from xenoform.turbo import publish_file

    publish_file(tmp, out_path)
    return {"shots": len(shots), "vibe": vibe, "seconds": round(duration, 3), "long_song": long_song,
            "size": f"{w}x{h}", "fps": fps}


def recut_from_cache(job_dir: Path, overrides: dict | None = None, report: Callable[[str, float, str], None] | None = None,
                     cfg: dict | None = None) -> dict:
    """Re-compose a finished Simple job from its cached morphs with new knobs, look, orbit or beat FX, and with the
    timeline's per-shot and per-boundary overrides (docs/TIMELINE.md).

    No GPU: the morph clips, the plan and the song are read from ``<job>/simple/simple.json``. ``overrides`` carries
    the knob keys (``macros``, ``dance_fx``, ...) and, when the timeline sends them, ``shot_overrides`` and
    ``boundary_overrides`` (whole maps: each replaces the record's; absent, the record's are kept, so a re-cut with new
    knobs keeps every timeline edit). The job's ``xenoform.mp4`` is replaced (``publish_file``) and the updated record
    returned."""
    job_dir = Path(job_dir)
    work = job_dir / "simple"
    rec_path = work / "simple.json"
    if not rec_path.is_file():
        raise FileNotFoundError("This video has no cached morphs to re-cut (it was not made by Simple mode).")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    clips = [Path(c) for c in rec.get("clips") or []]
    shots = rec.get("plan_shots") or rec.get("shots") or []
    if not clips or not shots or len(clips) != len(shots) or not all(c.is_file() for c in clips):
        raise FileNotFoundError("The cached morphs for this video are gone; render it again.")
    audio = Path(rec.get("audio_path") or "")
    if not audio.is_file():
        raise FileNotFoundError("The song file for this video is gone; load it again and render.")
    raw = dict(overrides or {})
    so_raw = raw.pop("shot_overrides", None)
    bo_raw = raw.pop("boundary_overrides", None)
    state = dict(rec.get("recut_state") or {})
    state.update({k: v for k, v in raw.items() if v is not None})
    opt = options(state)
    hp = house(state, cfg)
    import copy as _copy

    shots = _copy.deepcopy(shots)
    n = len(shots)
    m = macros(state)
    apply_macros(shots, m, hp if rec.get("vertical_house") else None)
    vibe = str(rec.get("vibe") or state.get("vibe") or "")
    from xenoform import effects as _E

    effect_names = _E.names_of(state)
    smear = _E.smear_setting(state)
    transitions = boundary_transitions(shots, vibe, seed=int(rec.get("seed") or 0), smear=smear) if rec.get("plan_name") == "story" else None
    from xenoform import boundary_fx as _B

    drop = rec.get("drop")
    if drop is None and shots:  # a record from before the drop was written down: the song's own drop, as the dense plan finds it
        try:
            drop = find_drop(audio, list(rec.get("beats") or []), float(shots[-1].get("end") or 0.0))
        except Exception:
            drop = None
    fps = int(rec.get("fps") or 24)
    beats = list(rec.get("beats") or [])
    boundary_fx = _B.pick(shots, m, beats, fps, seed=int(rec.get("seed") or 0),
                          premium=transitions, drop=drop, smear=smear)  # re-picked from the knobs as they are now: the same knobs give the same kinds
    transitions = _B.clear_premium(transitions, boundary_fx)
    # the timeline: the maps sent replace the record's, the record's hold otherwise; a Cut handoff is a hold on the shot before
    so = shot_overrides_of(so_raw if so_raw is not None else rec.get("shot_overrides"), n)
    bo = boundary_overrides_of(bo_raw if bo_raw is not None else rec.get("boundary_overrides"), n)
    so, bo = fold_handoffs(so, bo)
    transitions, boundary_fx, tl_notes = apply_timeline(shots, so, bo, vibe=vibe, house=hp, transitions=transitions,
                                                        boundary_fx=boundary_fx, beats=beats, fps=fps, drop=drop)
    # the order edits: a slot playing another shot's morph, a moved cut, a dropped shot (arrange_shots)
    laid = arrange_shots(shots, clips, so, bo, fps, transitions=transitions, boundary_fx=boundary_fx)
    shots, clips, transitions, boundary_fx = laid["shots"], laid["clips"], laid["transitions"], laid["boundary_fx"]
    kept = laid["kept"]  # plan index of each composed shot: the timeline's maps are keyed by plan index
    so_laid = {k: so[i] for k, i in enumerate(kept) if i in so}
    # the morph timing (morph_timing) on the cached clips: the cut's setting, a shot's own from the timeline
    from xenoform import morph_timing as _mt

    timing_mode = _mt.normal(state.get("morph_timing"))
    timed = _mt.plan(shots, timing_mode, beats, drop, so_laid)
    look_preset = beatfx.resolve_dance_preset(opt["dance_fx"], vibe, hp)
    if look_preset == "off" and not opt["stem_orbit"]:
        opt["stem_orbit"] = True  # as in run_simple: no look and no orbit would leave held stills dead
    stem_env = stem_env_for(state)
    size = tuple(rec["size"]) if rec.get("size") else None
    engine = str(rec.get("tier") or "draft")
    tmp = job_dir / "xenoform.recut.mp4"
    if report:
        report("assemble", 0.1, "Re-cutting from the cached morphs (no GPU)" + (f" with {len(so) + len(bo)} timeline edits" if (so or bo) else ""))
    from xenoform import foreshadow as _fs

    fs_mode = _fs.mode_for(opt["foreshadow"], vibe)
    made = beatfx.compose(clips, shots, audio, tmp, aspect=opt["aspect"], quality="final" if engine == "final" else "draft",
                          fx=opt["fx"], overlay=opt["overlay"], beats=beats, report=report, size=size, fps=fps,
                          dance_fx=look_preset, stem_orbit=opt["stem_orbit"], stem_env=stem_env, macros=m, house=hp,
                          end_card=opt["end_card"], seed=int(rec.get("seed") or 0), palette_image=rec.get("palette_image"),
                          adaptive=str(opt.get("dance_fx") or "auto").strip().lower() == "auto", transitions=transitions,
                          foreshadow=fs_mode, boundary_fx=boundary_fx, effects=effect_names,
                          tones=_E.palette_from_clips(clips).tolist() if _E.wants_tones(look_preset, effect_names, shots) else None)
    if opt["end_card"]:
        beatfx.end_card(tmp, str(opt.get("recipe") or "(none)"))
    from xenoform.turbo import publish_file

    publish_file(tmp, job_dir / "xenoform.mp4")
    record_shots = list(laid["record"])  # one a plan shot: the composed ones as they were cut, a dropped one at zero length
    for k, i in enumerate(kept):
        record_shots[i] = shots[k]
    rec.update({"shots": record_shots, "look": made.get("look"), "macros": m, "recut_state": state, "transitions": transitions,
                "boundary_fx": boundary_fx, "handoffs": made.get("boundary_fx"), "drop": drop,
                "shot_overrides": {str(k): v for k, v in sorted(so.items())},
                "boundary_overrides": {str(k): v for k, v in sorted(bo.items())},
                "timeline": {"shots": len(so), "boundaries": len(bo), "notes": tl_notes},
                "morph_timing": timing_mode, "timed": timed, "effects": effect_names, "smear": smear,
                "recuts": int(rec.get("recuts") or 0) + 1})
    rec_path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec


# ---------------------------------------------------------------- the timeline (docs/TIMELINE.md)

PLAY = ("morph", "hold")
LOOK_AUTO = ("", "auto", "default")


def _premium_kinds() -> set[str]:
    """The transition kinds a boundary may be dressed with by hand: every CPU kind of ``transitions_fx`` (the GPU scene
    morph is not a Simple-cut transition)."""
    from xenoform import transitions_fx as T

    return {k for k, v in T.TRANSITIONS.items() if not v.get("gpu")}


def shot_overrides_of(raw, n: int) -> dict[int, dict]:
    """The timeline's per-shot overrides, normalised: ``{index: {"play": "hold", "look": preset | "off",
    "fx_intensity": 0..1, "timing": "smooth" | "beat" | "snap"}}`` with only the keys that change something (Morph and
    Auto are the defaults and are dropped),
    indices inside the cut. Accepts a dict keyed by index (``"3"``) or a list with one entry a shot."""
    pairs: list = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        pairs = list(enumerate(raw))
    out: dict[int, dict] = {}
    for k, v in pairs:
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        if not 0 <= i < n or not isinstance(v, dict):
            continue
        o: dict = {}
        play = str(v.get("play") or "").strip().lower()
        if play == "hold":
            o["play"] = "hold"
        if "look" in v and v.get("look") is not None:
            look = str(v.get("look") or "").strip().lower()
            if look not in LOOK_AUTO:
                o["look"] = look
        if v.get("fx_intensity") is not None:
            try:
                o["fx_intensity"] = round(max(0.0, min(1.0, float(v["fx_intensity"]))), 3)
            except (TypeError, ValueError):
                pass
        timing = str(v.get("timing") or "").strip().lower()
        if timing in ("smooth", "beat", "snap"):  # the shot's own morph timing (morph_timing); Auto is the cut's
            o["timing"] = timing
        from xenoform import effects as _E

        g = _E.grade_of(v.get("grade"))  # the shot's own colour: hue, saturation, brightness, contrast, warmth
        if g:
            o["grade"] = g
        if isinstance(v.get("effects"), (list, tuple)):  # the shot's own effects ([] is none on this shot)
            o["effects"] = [n for n in _E.NAMES if n in {str(x).strip().lower() for x in v["effects"]}]
        try:  # the slot plays another shot's morph (Move left / right, Duplicate)
            src = int(v["source"]) if v.get("source") is not None else None
        except (TypeError, ValueError):
            src = None
        if src is not None and 0 <= src < n and src != i:
            o["source"] = src
        if v.get("drop") is True:  # the shot goes; the one before plays on through its time
            o["drop"] = True
        if o:
            out[i] = o
    return out


def boundary_overrides_of(raw, n: int) -> dict[int, dict]:
    """The timeline's per-boundary overrides, normalised: ``{index: {"handoff": "cut" | "morph", "fx": "none" |
    premium kind | boundary kind}}`` for the boundary into shot ``index`` (1 up); Auto is dropped, an unknown kind too."""
    from xenoform import boundary_fx as _B

    pairs: list = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        pairs = list(enumerate(raw))
    premium = _premium_kinds()
    out: dict[int, dict] = {}
    for k, v in pairs:
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        if not 1 <= i < n or not isinstance(v, dict):
            continue
        o: dict = {}
        hand = str(v.get("handoff") or "").strip().lower()
        if hand in ("cut", "morph"):
            o["handoff"] = hand
        fx = str(v.get("fx") or "").strip().lower()
        if fx == "none" or fx in premium or fx in _B.KINDS:
            o["fx"] = fx
        try:  # the cut moves this many seconds (later is plus), a beat at a time on the desk
            shift = round(max(-SHIFT_MAX_S, min(SHIFT_MAX_S, float(v.get("shift") or 0.0))), 3)
        except (TypeError, ValueError):
            shift = 0.0
        if abs(shift) >= 0.01:
            o["shift"] = shift
        if o:
            out[i] = o
    return out


SHIFT_MAX_S = 4.0      # a cut moves at most this far either way
MIN_SHOT_FRAMES = 6    # and never leaves a shot shorter than this


def arrange_shots(shots: list[dict], clips: list, so: dict[int, dict], bo: dict[int, dict], fps: int,
                  transitions: list | None = None, boundary_fx: list | None = None) -> dict:
    """The timeline's order edits on a re-cut (Tys, 28 Oct: "trim and move cuts", "reorder, delete, duplicate"): a slot
    that plays another shot's morph (``source``: Move left and right swap two, Duplicate gives the next slot this one's),
    a cut moved by ``shift`` seconds (the shot before grows, the one after shrinks, neither under ``MIN_SHOT_FRAMES``),
    and a dropped shot (``drop``: the nearest kept shot before it, else after, plays on through its time). Starts and ends
    follow the frames. Returns the lists the compositor takes (``shots``, ``clips``, ``transitions``, ``boundary_fx``) and
    ``record``, one entry a plan shot, a dropped one at zero length, so the timeline's indices hold through the edit."""
    n = len(shots)
    out_clips = list(clips)
    morphs = [s.get("morph") for s in shots]
    for i, o in sorted(so.items()):
        j = o.get("source")
        if j is not None and 0 <= i < n and 0 <= j < n:
            out_clips[i] = clips[j]
            shots[i]["morph"] = morphs[j] if morphs[j] is not None else j
            shots[i]["plays"] = j  # not "source": an own clip slot names its file there
    for i, o in sorted(bo.items()):
        if o.get("shift") and 1 <= i < n:
            d = int(round(float(o["shift"]) * fps))
            d = max(-(int(shots[i - 1]["frames"]) - MIN_SHOT_FRAMES), min(int(shots[i]["frames"]) - MIN_SHOT_FRAMES, d))
            shots[i - 1]["frames"] = int(shots[i - 1]["frames"]) + d
            shots[i]["frames"] = int(shots[i]["frames"]) - d
    keep = [True] * n
    for i in sorted((i for i, o in so.items() if o.get("drop") and 0 <= i < n), reverse=True):
        if sum(keep) <= 1:
            break
        k = next((j for j in range(i - 1, -1, -1) if keep[j]), None)
        if k is None:
            k = next(j for j in range(i + 1, n) if keep[j])
        shots[k]["frames"] = int(shots[k]["frames"]) + int(shots[i]["frames"])
        keep[i] = False
    t = 0
    for i, s in enumerate(shots):
        frames = int(s["frames"]) if keep[i] else 0
        s["start"], s["end"] = round(t / fps, 4), round((t + frames) / fps, 4)
        s["seconds"] = round(frames / fps, 4)
        if not keep[i]:
            s["dropped"] = True
        t += frames
    pick = lambda xs: [x for x, k in zip(xs, keep) if k] if xs is not None else None  # noqa: E731
    return {"shots": pick(shots), "clips": pick(out_clips), "transitions": pick(list(transitions) + [None] * (n - len(transitions)))
            if transitions is not None else None,
            "boundary_fx": pick(list(boundary_fx) + [None] * (n - len(boundary_fx))) if boundary_fx is not None else None,
            "record": [dict(s, frames=int(s["frames"]) if keep[i] else 0) for i, s in enumerate(shots)],
            "kept": [i for i in range(n) if keep[i]]}


def fold_handoffs(so: dict[int, dict], bo: dict[int, dict]) -> tuple[dict[int, dict], dict[int, dict]]:
    """A Cut at the boundary into shot i is a Hold on shot i - 1 (the only visible cut in a chain of morphs; see
    docs/TIMELINE.md 1.3): the handoff keys move onto the shot overrides, and a boundary left with nothing goes."""
    so = {k: dict(v) for k, v in so.items()}
    bo = {k: dict(v) for k, v in bo.items()}
    for i in sorted(bo):
        hand = bo[i].pop("handoff", None)
        if hand == "cut":
            so.setdefault(i - 1, {})["play"] = "hold"
        elif hand == "morph" and i - 1 in so:
            so[i - 1].pop("play", None)
            if not so[i - 1]:
                del so[i - 1]
        if not bo[i]:
            del bo[i]
    return so, bo


def _premium_window(shots: list[dict], i: int, kind: str) -> dict:
    """A premium transition entry for the boundary into shot ``i``, its window sized as ``boundary_transitions`` sizes one."""
    frames = int(min(12, max(4, int(shots[i].get("frames") or 24) // 3, 4), (int(shots[i - 1].get("frames") or 24) // 2)))
    return {"kind": kind, "frames": max(2, frames), "boundary": str(shots[i].get("boundary") or "") or "timeline", "user": True}


def apply_timeline(shots: list[dict], so: dict[int, dict], bo: dict[int, dict], *, vibe: str, house: dict | None,
                   transitions: list | None, boundary_fx: list, beats: list, fps: int, drop: float | None) -> tuple[list | None, list, list[str]]:
    """Lay the timeline's overrides over the composed shots and the pickers' lists, in place for the shots.

    Per shot: Hold marks ``hold`` (and ``cut_out``: the join after it is a cut), Look sets ``dance_fx`` to the resolved
    preset for that shot alone, FX intensity replaces the knob's value. Per boundary: ``none`` clears the premium window
    and the kind, a premium kind sets the window and clears the kind, a boundary kind sets the kind and clears the
    window; what the pickers chose stays where nothing was said. Returns the two lists and the notes (an unknown look,
    a kind a short shot could not take, a hand-picked premium type past the house cap, which is kept as picked)."""
    from xenoform import boundary_fx as _B
    from xenoform import transitions_fx as T

    notes: list[str] = []
    n = len(shots)
    for i, o in sorted(so.items()):
        if not 0 <= i < n:
            continue
        s = shots[i]
        if o.get("play") == "hold":
            s["hold"] = True
            s["cut_out"] = True
        if "look" in o:
            try:
                s["dance_fx"] = beatfx.resolve_dance_preset(o["look"], vibe, house)
            except ValueError:
                notes.append(f"shot {i + 1}: no look called {o['look']!r}; the cut's look stays")
        if "fx_intensity" in o:
            s["fx_intensity"] = float(o["fx_intensity"])
        if "grade" in o:
            s["grade"] = dict(o["grade"])
        if "effects" in o:
            s["fx_names"] = list(o["effects"])  # not "effects": a shot carries its beat FX (punches, stutters) there
    bx = list(boundary_fx or [])[:n] + [None] * max(0, n - len(boundary_fx or []))
    tr = list(transitions)[:n] + [None] * max(0, n - len(transitions)) if transitions is not None else None
    premium = _premium_kinds()
    for i, o in sorted(bo.items()):
        if not 1 <= i < n or "fx" not in o:
            continue
        fx = o["fx"]
        if fx == "none":
            bx[i] = None
            if tr is not None:
                tr[i] = None
        elif fx in _B.KINDS:
            entry = _B.make(shots, i, fx, beats, fps, drop=drop)
            if entry is None:
                notes.append(f"boundary {i}: the shots beside it are too short for a {_B.LABELS.get(fx, fx)}; left as the pickers had it")
                continue
            bx[i] = entry
            if tr is not None:
                tr[i] = None
        elif fx in premium:
            if tr is None:
                tr = [None] * n
            tr[i] = _premium_window(shots, i, fx)
            bx[i] = None
    if tr is not None:
        cap = T._resolve_rules(None, None, None)[0]
        uses: dict[str, int] = {}
        for t in tr:
            if isinstance(t, dict) and t.get("kind") and t["kind"] not in T.EXEMPT_FROM_CAP:
                uses[t["kind"]] = uses.get(t["kind"], 0) + 1
        for kind, count in sorted(uses.items()):
            if count > cap and any(isinstance(t, dict) and t.get("kind") == kind and t.get("user") for t in tr):
                notes.append(f"{kind} is on {count} boundaries, past the house cap of {cap}; kept as picked on the timeline")
    return tr, bx, notes


# ---------------------------------------------------------------- the pair renderer on the timeline

RERENDER_VARIANTS = {"auto": None, "object": ("object", "object"), "scene-object": ("scene", "object"),
                     "object-scene": ("object", "scene"), "scene": ("scene", "scene")}
RENDER_S_RANGE = (2, 5)
INSERT_SECONDS = (5.0, 10.0, 15.0)
INSERT_RANGE = (3.0, 20.0)


def _prep_of(rec: dict) -> dict:
    """How the cut prepared its stills, so a pair rendered after it is prepared the same way: ``native_draft`` (portrait
    re-lay at ``draft_size``), ``background`` (black ground), ``mock`` (the test engine)."""
    prep = rec.get("prep") if isinstance(rec.get("prep"), dict) else None
    if prep is not None:
        native_draft, background = bool(prep.get("native_draft")), prep.get("background")
    else:  # a record from before ``prep``: the note the Draft 9:16 path leaves
        native_draft = any("native_draft" in note for note in rec.get("fallbacks") or [] if isinstance(note, dict))
        background = None
    draft_size = tuple(int(v) for v in ((prep or {}).get("draft_size") or DRAFT_916)) if native_draft else None
    return {"native_draft": native_draft, "background": background, "draft_size": draft_size,
            "mock": str(rec.get("engine") or "").startswith("mock")}


def _prepare_rows(rows: list[dict], prep: dict, work: Path) -> list[dict]:
    """The still rows prepared as the cut prepared its stills (black ground, then the portrait re-lay)."""
    prepared = [dict(r) for r in rows]
    if prep.get("background") == "black":
        from xenoform.portrait import black_stills

        prepared = black_stills(prepared, work)
    if prep.get("native_draft"):
        from xenoform.portrait import portrait_stills

        prepared = portrait_stills(prepared, work, prep["draft_size"][0], prep["draft_size"][1], background=prep.get("background"))
    return prepared


def _render_pairs(render_shots: list[dict], rows: list[dict], dest_dir: Path, prep: dict, *, seed: int, vibe: str, cfg: dict | None,
                  state: dict, client=None, report=None, styles: list[str] | None = None) -> list[Path]:
    """``len(render_shots)`` morphs over ``rows`` (one more still than shots) through the Draft path, the cut's engine,
    each in its ``styles`` entry (``morph_style``; Melt when not given)."""
    if prep.get("mock"):
        from xenoform.cloud_morph import _mock_clips

        return _mock_clips(render_shots, rows, dest_dir, *(prep.get("draft_size") or (768, 432)))
    return _draft_clips(render_shots, rows, dest_dir, cfg or {}, seed, vibe, client, None, state, report=report,
                        size=prep.get("draft_size"), styles=styles)


def _styles_of(rec: dict) -> list[str]:
    """The record's style a shot (``morph_styles``), Melt for a record from before the styles."""
    from xenoform.morph_style import normal

    shots = list(rec.get("plan_shots") or rec.get("shots") or [])
    got = [normal(s, allow_auto=False) for s in (rec.get("morph_styles") or [])]
    return (got + ["melt"] * len(shots))[:len(shots)] if shots else got


def _load_cut(job_dir: Path, verb: str) -> tuple[Path, Path, dict]:
    """The record of a finished Simple cut, or the plain-words refusal."""
    job_dir = Path(job_dir)
    work = job_dir / "simple"
    rec_path = work / "simple.json"
    if not rec_path.is_file():
        raise FileNotFoundError(f"This video has no cached morphs to {verb} (it was not made by Simple mode).")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    shots = list(rec.get("plan_shots") or rec.get("shots") or [])
    clips = [str(c) for c in rec.get("clips") or []]
    if not shots or not clips or len(clips) != len(shots):
        raise FileNotFoundError("The cached morphs for this video are gone; render it again.")
    if str(rec.get("tier") or "draft") == "final":
        raise ValueError(f"A {verb} renders Draft morphs; this cut is Final. Make it again instead.")
    if rec.get("fast") or rec.get("cloud"):  # the record's tier is "draft" for both; a Draft-size morph would be spliced in
        raise ValueError(f"A {verb} renders Draft morphs; this cut is {'Fast Final' if rec.get('fast') else 'Cloud Final'}. "
                         "Make it again instead.")
    return job_dir, work, rec


def _under_insert(shot: dict) -> str:
    """Why a shot has no morph of the chain: Polly, your clip, a dream or a generated run; "" when it plays a chain
    morph."""
    if shot.get("performer"):
        return "Polly"
    if shot.get("own"):
        return "one of your clips"
    if shot.get("dream"):
        return "a dream"
    if shot.get("generated"):
        return "a generated run"
    return ""


def rerender_morph(job_dir: Path, shot: int, *, seed: int | None = None, render_s: int | None = None, variant: str = "auto",
                   style: str | None = None, cfg: dict | None = None, report: Callable[[str, float, str], None] | None = None,
                   client=None) -> dict:
    """Re-render the morph one shot of a finished Simple cut plays, with another seed, length, prompt variant or style
    (docs/TIMELINE.md 1.5; ``style`` is how the object changes, ``morph_style``, the shot's own when not given), and
    re-compose.

    The pair is the two chain stills the shot's morph runs between, prepared as the cut prepared them; the seed is the
    one given, else the next in the shot's own sequence (the cut's seed for that morph, then 1009 further each time);
    ``render_s`` (2 to 5) changes how many seconds of source the morph has (the shot's frames stay on the beat, its
    ``speed`` follows); ``variant`` forces the pair's prompt (``RERENDER_VARIANTS``: by the stills' kinds, object to
    object, scene to object, object to scene, scene to scene). The new clip replaces ``clips[shot]``, the record logs it
    under ``rerenders`` and the cut re-composes through ``recut_from_cache`` with the timeline as it stands. A Final cut
    and a shot under Polly, your clip or a generated run are refused."""
    job_dir, work, rec = _load_cut(job_dir, "re-render")
    shots = list(rec.get("plan_shots") or rec.get("shots") or [])
    clips = [str(c) for c in rec.get("clips") or []]
    files = [str(f) for f in rec.get("stills") or []]
    n = len(files)
    try:
        j = int(shot)
    except (TypeError, ValueError) as exc:
        raise ValueError("Which shot? A re-render names a shot of the cut by its index.") from exc
    if not 0 <= j < len(shots):
        raise ValueError(f"This cut has {len(shots)} shots; shot {j} is not one of them.")
    s = shots[j]
    under = _under_insert(s)
    if under:
        raise ValueError(f"Shot {j + 1} is {under}: it plays no morph of the chain to re-render.")
    m = s.get("morph", s.get("clip"))
    if m is None and len(clips) == n - 1:  # a record from before the morph index: one morph a shot
        m = j
    if m is None or not 0 <= int(m) < n - 1:
        raise ValueError(f"Shot {j + 1} plays no morph of the chain to re-render.")
    m = int(m)
    variant = str(variant or "auto").strip().lower()
    if variant not in RERENDER_VARIANTS:
        raise ValueError(f"No prompt variant called {variant!r}; one of {', '.join(RERENDER_VARIANTS)}.")
    from xenoform import morph_style as _ms

    styles = _styles_of(rec)
    if style is not None and str(style).strip().lower() not in _ms.STYLES:
        raise ValueError(f"No morph style called {style!r}; one of {', '.join(_ms.STYLES)}.")
    style = str(style).strip().lower() if style is not None else styles[j]
    scene_files = {str(f) for f in rec.get("scene_files") or []}
    rows = _still_rows(files, scene_files)
    pair = [dict(rows[m]), dict(rows[m + 1])]
    kinds = RERENDER_VARIANTS[variant]
    if kinds:
        for row, kind in zip(pair, kinds):
            row["kind"] = kind  # ``_local_clips`` reads the pair's kinds for the prompt and the guide compression
    seconds = float(s.get("seconds") or (float(s.get("end") or 0.0) - float(s.get("start") or 0.0)) or 1.0)
    old_render_s = int(s.get("render_s") or (rec.get("chain") or {}).get("clip_s") or max(2, int(round(seconds))))
    if render_s is not None:
        try:
            render_s = int(round(float(render_s)))
        except (TypeError, ValueError) as exc:
            raise ValueError("The morph's length is a number of seconds, 2 to 5.") from exc
        if not RENDER_S_RANGE[0] <= render_s <= RENDER_S_RANGE[1]:
            raise ValueError(f"The morph's length is {RENDER_S_RANGE[0]} to {RENDER_S_RANGE[1]} s of source; {render_s} is outside that.")
    else:
        render_s = old_render_s
    rerenders = list(rec.get("rerenders") or [])
    tries = sum(1 for r in rerenders if isinstance(r, dict) and r.get("shot") == j)
    base_seed = int(rec.get("seed") or 2727)
    seed = int(seed) if seed is not None else base_seed + m + 1009 * (tries + 1)
    prep = _prep_of(rec)
    vibe = str(rec.get("vibe") or "")
    state = dict(rec.get("recut_state") or {})
    dest_dir = work / "rerenders" / f"{len(rerenders):02d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ready = _prepare_rows(pair, prep, work)
    render_shot = {"index": m, "seconds": float(render_s), "render_s": render_s, "frames": int(render_s * FPS), "effects": []}
    if report:
        report("restyle", 0.1, f"Re-rendering shot {j + 1}: {pair[0].get('noun') or '?'} -> {pair[1].get('noun') or '?'} "
                               f"({_ms.LABELS[style]}, seed {seed}, {render_s} s{'' if variant == 'auto' else ', ' + variant})")
    started = time.perf_counter()
    got = _render_pairs([render_shot], ready, dest_dir, prep, seed=seed, vibe=vibe, cfg=cfg, state=state, client=client,
                        styles=[style])[0]
    dest = dest_dir / f"morph{m:02d}.mp4"
    shutil.move(str(got), dest)
    clips[j] = str(dest)
    styles[j] = style
    if render_s != old_render_s:  # the shot keeps its frames on the beat; the source length and the play speed move
        for lst in (rec.get("plan_shots") or [], rec.get("shots") or []):
            if j < len(lst) and isinstance(lst[j], dict):
                lst[j]["render_s"] = render_s
                lst[j]["speed"] = round(render_s / max(seconds, 0.1), 3)
    from datetime import datetime

    rec.update({"clips": clips, "morph_styles": styles,
                "rerenders": rerenders + [{"shot": j, "morph": m, "seed": seed, "render_s": render_s, "variant": variant, "style": style,
                                           "clip": str(dest), "seconds": round(time.perf_counter() - started, 2),
                                           "at": datetime.now().astimezone().isoformat(timespec="seconds")}]})
    (work / "simple.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    if report:
        report("assemble", 0.55, "Re-cutting with the new morph (no GPU)")
    return recut_from_cache(job_dir, {}, report=report, cfg=cfg)


def insert_span(shots: list[dict], first: int, seconds: float) -> tuple[int, int]:
    """The run "Generate here" covers: shot ``first`` and the ones after it until ``seconds`` are covered (whole shots,
    never past the end, never into Polly or an own clip or another run). ``(first, last)``."""
    n = len(shots)
    if not 0 <= first < n:
        raise ValueError(f"This cut has {n} shots; shot {first} is not one of them.")
    under = _under_insert(shots[first])
    if under:
        raise ValueError(f"Shot {first + 1} is {under}; start the run on a shot that plays a morph of the chain.")
    want = max(INSERT_RANGE[0], min(INSERT_RANGE[1], float(seconds or INSERT_SECONDS[1])))
    total, last = 0.0, first
    for j in range(first, n):
        if _under_insert(shots[j]):
            break
        length = float(shots[j].get("seconds") or (float(shots[j].get("end") or 0.0) - float(shots[j].get("start") or 0.0)))
        if j > first and abs(total + length - want) >= abs(total - want) - 1e-6:
            break  # the next shot would not bring the run nearer the length asked (a tie keeps the shorter run)
        total += length
        last = j
        if total >= want - 1e-6:
            break
    return first, last


def insert_generated(job_dir: Path, first: int, *, seconds: float = 10.0, pins: dict | list | None = None, seed: int | None = None,
                     cfg: dict | None = None, report: Callable[[str, float, str], None] | None = None, client=None) -> dict:
    """"Generate 10 s here": a fresh Draft chain over a span of a finished Simple cut, inserted as a run of shots, and
    the cut re-composed (docs/TIMELINE.md 1.6).

    The span is ``insert_span``; k shots take k morphs over k + 1 stills picked by ``morph_pass.pick_stills`` for the
    cut's vibe and idea with ``pins`` (slot -> still file) honoured and the stills already in the cut left out, each
    morph rendered at its shot's ``render_s`` through the Draft path and prepared as the cut prepared its stills. The
    shots of the run keep their timing, effects, look and FX; they carry ``generated: {insert, index}`` and no chain
    ``morph`` (the chain's ``stills`` are untouched), ``clips`` point at the new morphs, and ``inserts`` logs the run."""
    from xenoform import morph_pass as _mp
    from xenoform import stills as _stills

    job_dir, work, rec = _load_cut(job_dir, "generate into")
    shots = list(rec.get("plan_shots") or rec.get("shots") or [])
    clips = [str(c) for c in rec.get("clips") or []]
    try:
        first = int(first)
    except (TypeError, ValueError) as exc:
        raise ValueError("Where? A generated run starts on a shot of the cut, named by its index.") from exc
    first, last = insert_span(shots, first, float(seconds or INSERT_SECONDS[1]))
    span = shots[first:last + 1]
    k = len(span)
    inserts = list(rec.get("inserts") or [])
    vibe = str(rec.get("vibe") or "")
    state = dict(rec.get("recut_state") or {})
    state.setdefault("vibe", vibe)
    pins_map = _mp.pins_of({"chain_pins": pins}) if pins is not None else {}
    used = {str(f) for f in rec.get("stills") or []}
    for ins in inserts:
        used.update(str(f) for f in (ins.get("stills") or []))
    scene_kw = _scene_kw(state, span, k + 1)
    _look_vibe, picked = _mp.pick_stills(state, k + 1 + len(used), record=False, pins=pins_map, **scene_kw)
    held = {i: row for i, row in enumerate(picked[:k + 1]) if row.get("pinned")}
    fresh = [row for row in picked if not row.get("pinned") and str(row.get("file")) not in used]
    spare = [row for row in picked if not row.get("pinned") and str(row.get("file")) in used]  # a small pool: the cut's own stills again
    rows: list[dict] = []
    for slot in range(k + 1):
        if slot in held:
            rows.append(dict(held[slot]))
        elif fresh:
            rows.append(dict(fresh.pop(0)))
        elif spare:
            rows.append(dict(spare.pop(0)))
        else:
            raise ValueError(f"The {vibe} library has no still left for a run of {k} morphs; grow some first.")
    prep = _prep_of(rec)
    ready = _prepare_rows(rows, prep, work)
    render_shots = []
    for q, s in enumerate(span):
        seconds_q = float(s.get("seconds") or (float(s.get("end") or 0.0) - float(s.get("start") or 0.0)) or 1.0)
        render_s = int(s.get("render_s") or (rec.get("chain") or {}).get("clip_s") or max(2, int(round(seconds_q))))
        render_shots.append({"index": q, "seconds": float(render_s), "render_s": render_s, "frames": int(render_s * FPS), "effects": []})
    seed = int(seed) if seed is not None else int(rec.get("seed") or 2727) + 5000 * (len(inserts) + 1)
    dest_dir = work / "inserts" / f"{len(inserts):02d}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    nouns = [str(r.get("noun") or "") for r in rows]
    if report:
        report("restyle", 0.1, f"Generating {k} morph{'s' if k != 1 else ''} over shots {first + 1} to {last + 1}: " + " -> ".join(nouns))

    def pair_report(stage: str, frac: float, detail: str) -> None:
        if report:
            report(stage, frac, detail)

    # the run's morphs take the cut's setting: one style for all, or Auto over the span's own shots (no drop in a span
    # unless the cut's drop falls in it)
    from xenoform import morph_style as _ms

    run_styles = _ms.for_cut({**state, "morph_styles": None, "macros": macros(state)}, span, rec.get("drop"))
    started = time.perf_counter()
    got = _render_pairs(render_shots, ready, dest_dir, prep, seed=seed, vibe=vibe, cfg=cfg, state=state, client=client, report=pair_report,
                        styles=run_styles)
    styles = _styles_of(rec)
    new_clips = []
    for q, path in enumerate(got):
        dest = dest_dir / f"morph{q:02d}.mp4"
        shutil.move(str(path), dest)
        new_clips.append(str(dest))
        clips[first + q] = str(dest)
        if first + q < len(styles):
            styles[first + q] = run_styles[q]
    idx = len(inserts)
    for lst in (rec.get("plan_shots") or [], rec.get("shots") or []):
        for q in range(k):
            j = first + q
            if j < len(lst) and isinstance(lst[j], dict):
                lst[j].pop("morph", None)
                lst[j].pop("clip", None)
                lst[j]["generated"] = {"insert": idx, "index": q}
    from datetime import datetime

    entry = {"first": first, "last": last, "start": float(span[0].get("start") or 0.0), "end": float(span[-1].get("end") or 0.0),
             "seconds": round(sum(float(s.get("seconds") or 0.0) for s in span), 4), "stills": [str(r.get("file")) for r in rows],
             "nouns": nouns, "kinds": [_stills.kind_of(r) for r in rows], "clips": new_clips, "pins": {str(a): b for a, b in pins_map.items()},
             "seed": seed, "render_s": [r["render_s"] for r in render_shots], "styles": run_styles,
             "took_s": round(time.perf_counter() - started, 2), "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    rec.update({"clips": clips, "inserts": inserts + [entry], "morph_styles": styles})
    (work / "simple.json").write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    try:
        _stills.mark_used(vibe, [str(r.get("file")) for r in rows if not r.get("user")])
    except Exception:  # usage is a preference, never a failure
        log.debug("usage for the generated run", exc_info=True)
    if report:
        report("assemble", 0.55, "Re-cutting with the generated run (no GPU)")
    return recut_from_cache(job_dir, {}, report=report, cfg=cfg)


# ---------------------------------------------------------------- swapping a still after the cut


def library_row(file: str) -> dict | None:
    """A still file (``cosmic/042_wolf_skull.jpg``) as its catalogue row with ``path``, under whichever vibe lists it;
    None when no library has it."""
    from xenoform import morph_pass as _mp

    file = str(file or "").strip().replace("\\", "/")
    for vibe, rows in _mp.catalogue().items():
        for r in rows:
            if str(r.get("file") or "") == file:
                return {**r, "vibe": vibe}
    return None


def _still_rows(files: list[str], scene_files: set) -> list[dict]:
    """The cut's stills as rows with paths: the library's row, else the file where the pools keep it (a still culled
    from the library since the cut still morphs); a still gone from the machine is an error."""
    from xenoform import morph_pass as _mp
    from xenoform import stills as _stills
    from xenoform.lane import noun_of

    rows = []
    for f in files:
        r = library_row(f)
        if r is None:
            for base in (_mp.OBJECTS, _stills.root()):
                if (base / f).is_file():
                    r = {"file": f, "noun": noun_of(f), "path": str(base / f)}
                    break
        if r is None:
            raise FileNotFoundError(f"The still {f} is no longer on this machine.")
        if f in scene_files:
            r = {**r, "kind": "scene"}
        rows.append(r)
    return rows


def swap_still(job_dir: Path, slot: int, file: str, *, cfg: dict | None = None,
               report: Callable[[str, float, str], None] | None = None, client=None) -> dict:
    """Swap one still of a finished Simple cut (the shots lane's swap) and re-render only the morphs that touch it.

    Still ``slot`` of the record's chain becomes ``file`` (a library row: an object or a scene of any vibe). The two
    morphs that land on and leave that still (one at either end of the chain) are rendered again through the Draft
    path (``cloud_morph._local_clips``, two morphs' worth of the cut's render time, about 40 s on a 12 GB card; the same
    noise seed the cut used for those morphs), with the still prepared as the cut prepared its stills (black ground, portrait re-lay). Every
    other clip is kept, the record is updated in place (``stills``, ``scene_files``, ``clips``, a ``swaps`` log) and
    the cut is re-composed through ``recut_from_cache`` with the knobs as they stand. A Final cut, a still already in
    the chain, a slot under a performer or own clip, and a library file that does not exist are refused."""
    from xenoform import stills as _stills

    job_dir = Path(job_dir)
    work = job_dir / "simple"
    rec_path = work / "simple.json"
    if not rec_path.is_file():
        raise FileNotFoundError("This video has no cached morphs to swap into (it was not made by Simple mode).")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    files = [str(f) for f in rec.get("stills") or []]
    n = len(files)
    try:
        slot = int(slot)
    except (TypeError, ValueError) as exc:
        raise ValueError("Which slot? A swap names a still of the chain by its index.") from exc
    if not files or not 0 <= slot < n:
        raise ValueError(f"This cut has {n} stills; slot {slot} is not one of them.")
    if str(rec.get("tier") or "draft") == "final":
        raise ValueError("A swap re-renders a Draft morph pair; this cut is Final. Make it again with the Chain row instead.")
    if rec.get("fast") or rec.get("cloud"):
        raise ValueError(f"A swap re-renders a Draft morph pair; this cut is {'Fast Final' if rec.get('fast') else 'Cloud Final'}. "
                         "Make it again instead.")
    file = str(file or "").strip().replace("\\", "/")
    new = library_row(file)
    if new is None:
        raise ValueError(f"{file or '(nothing)'} is not in the stills library.")
    if file == files[slot]:
        raise ValueError(f"{new.get('noun') or file} is the still already in slot {slot}.")
    if file in files:
        raise ValueError(f"{new.get('noun') or file} is already in this cut (slot {files.index(file)}); a still appears once.")
    shots = list(rec.get("plan_shots") or rec.get("shots") or [])
    clips = [str(c) for c in rec.get("clips") or []]
    if not shots or not clips or len(clips) != len(shots):
        raise FileNotFoundError("The cached morphs for this video are gone; render it again.")
    scene_files = {str(f) for f in rec.get("scene_files") or []}
    shot_styles = _styles_of(rec)
    old = files[slot]
    rows = _still_rows(files, scene_files)
    rows[slot] = dict(new)
    # the morphs that touch the slot: the one landing on it and the one leaving it, and the shots that play them
    touch = [m for m in (slot - 1, slot) if 0 <= m < n - 1]

    def shot_for(m: int) -> int | None:
        for j, s in enumerate(shots):
            if s.get("performer") or s.get("own") or s.get("generated") or s.get("dream"):  # a dream keeps its picture
                continue
            mm = s.get("morph", s.get("clip"))
            if mm is None and len(clips) == n - 1:  # a record from before the morph index: one morph a shot
                mm = j
            if mm is not None and int(mm) == m:
                return j
        return None

    targets = {m: j for m, j in ((m, shot_for(m)) for m in touch) if j is not None}
    if not targets:
        raise ValueError("That still sits under Polly, one of your clips or a generated run: no morph of the cut lands on it.")
    prep = _prep_of(rec)
    native_draft, background, draft_size, mock = prep["native_draft"], prep["background"], prep["draft_size"], prep["mock"]
    vibe = str(rec.get("vibe") or new.get("vibe") or "")
    seed = int(rec.get("seed") or 2727)
    state = dict(rec.get("recut_state") or {})
    swaps = list(rec.get("swaps") or [])
    swap_dir = work / "swaps" / f"{len(swaps):02d}"
    swap_dir.mkdir(parents=True, exist_ok=True)
    need = sorted({k for m in targets for k in (m, m + 1)})
    prepared = [dict(rows[k]) for k in need]
    if background == "black":
        from xenoform.portrait import black_stills

        prepared = black_stills(prepared, work)
    if native_draft:
        from xenoform.portrait import portrait_stills

        prepared = portrait_stills(prepared, work, draft_size[0], draft_size[1], background=background)
    ready = dict(zip(need, prepared))
    started = time.perf_counter()
    new_clips: dict[int, str] = {}
    for m, j in sorted(targets.items()):
        shot = shots[j]
        render_s = int(shot.get("render_s") or (rec.get("chain") or {}).get("clip_s") or max(2, int(round(float(shot.get("seconds") or 2.0)))))
        render_shot = {"index": m, "seconds": float(render_s), "render_s": render_s, "frames": int(render_s * FPS), "effects": []}
        pair = [ready[m], ready[m + 1]]
        if report:
            report("restyle", 0.1 + 0.4 * len(new_clips) / len(targets),
                   f"Re-rendering morph {m + 1} of {n - 1}: {pair[0].get('noun') or '?'} -> {pair[1].get('noun') or '?'}")
        if mock:
            from xenoform.cloud_morph import _mock_clips

            got = _mock_clips([render_shot], pair, swap_dir, *(draft_size or (768, 432)))[0]
        else:
            got = _draft_clips([render_shot], pair, swap_dir, cfg or {}, seed + m, vibe, client, None, state, size=draft_size,
                               styles=[shot_styles[j] if j < len(shot_styles) else "melt"])[0]  # the shot keeps its style
        dest = swap_dir / f"morph{m:02d}.mp4"
        shutil.move(str(got), dest)
        new_clips[j] = str(dest)
    files[slot] = file
    scene_files.discard(old)
    if _stills.kind_of(new) == "scene":
        scene_files.add(file)
    for j, path in new_clips.items():
        clips[j] = path
    from datetime import datetime

    rec.update({"stills": files, "scene_files": [f for f in files if f in scene_files], "clips": clips,
                "families": sorted({fam for fam in (_stills.family_of(str(r.get("noun") or "")) for r in rows) if fam}),
                "swaps": swaps + [{"slot": slot, "from": old, "to": file, "morphs": sorted(targets), "shots": sorted(targets.values()),
                                   "clips": {str(j): p for j, p in new_clips.items()}, "seconds": round(time.perf_counter() - started, 2),
                                   "at": datetime.now().astimezone().isoformat(timespec="seconds")}]})
    if slot == 0:
        rec["palette_image"] = str(ready[0]["path"])  # the look's palette still is the chain's first
    rec_path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    try:
        _stills.mark_used(str(new.get("vibe") or vibe), [file])
    except Exception:  # usage is a preference, never a failure
        log.debug("usage for the swapped still", exc_info=True)
    if report:
        report("assemble", 0.55, "Re-cutting with the new morphs (no GPU)")
    return recut_from_cache(job_dir, {}, report=report, cfg=cfg)
