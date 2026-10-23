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
CLIP_BUDGET = (12, 30)        # unique morph renders in a music-video cut (min, max)
CLIP_SECONDS_PER = 10.0       # one unique morph per ten seconds of song
LONG_SONG_S = 45.0            # above this the chain reuse kicks in (the no-repeat guardrail is for short clips)
COMPOSE_S_PER_FRAME = {"draft": 0.2, "final": 0.3}  # measured: 1440 frames at 540x960 composed in 285 s (look pass 155 s)

# ---- morph count: "auto" (from clip length + BPM) or a fixed number of forms
MORPH_SLIDER = (1, 40)      # the desk slider; the number box allows up to MORPH_MAX
MORPH_MAX = 120
MIN_SLOT_S = 0.3            # a morph never gets less screen time than this
# measured on an RTX 3080 Ti 12 GB (ComfyUI shared, 2 s renders): seconds per morph and peak VRAM
# draft: measured 23 Oct 2026, 12 four-second morphs in 122 s warm on a 3080 Ti (about 10 s each); 12 s per 2 s morph keeps a margin
COST = {"draft": {"s": 12.0, "vram_gb": 7.5}, "final": {"s": 110.0, "vram_gb": 11.2},
        "final_916": {"s": 140.0, "vram_gb": 11.4}, "preview": {"s": 0.5, "vram_gb": 0.0}}


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
    return text if text in D.PRESETS else DANCE_FX_DEFAULT


def stem_orbit_choice(state: dict | None) -> bool:
    raw = (state or {}).get("stem_orbit", None)
    if raw is None or raw == "":
        return STEM_ORBIT_DEFAULT
    if isinstance(raw, str):
        return raw.strip().lower() not in ("off", "false", "0", "no", "none")
    return bool(raw)


def options(state: dict) -> dict:
    """The Simple finishing options from a desk state, normalised."""
    energy = str(state.get("energy_preset") or "flow").lower()
    tier = str(state.get("quality_tier") or "draft").lower()
    return {
        "energy": energy if energy in ENERGY else "flow",
        "aspect": beatfx.norm_aspect(state.get("aspect")),
        "tier": tier if tier in TIERS else "draft",
        "vertical": vertical_mode(state),
        "fx": bool(state.get("beat_fx", True)),
        "overlay": bool(state.get("beat_overlay")) and not bool(state.get("clean")),
        "end_card": bool(state.get("end_card")),
        "recipe": str(state.get("simple_recipe") or ""),
        "morph_count": morph_count(state),
        "dance_fx": dance_fx_choice(state),
        "stem_orbit": stem_orbit_choice(state),
    }


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
    gain = 0.4 + 1.2 * m.get("intensity", 0.5)
    chaos = float(min(1.0, max(0.0, m.get("chaos", 0.3))))
    wob = max(0.0, (chaos - 0.5) * 0.6)
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
                effects.append({**fx, "strength": round(min(1.0, float(fx.get("strength", 0.5)) * (0.4 + 1.2 * chaos)), 3)})
            elif kind in ("stutter", "hold", "skip", "reverse"):
                if chaos < 0.25:
                    continue
                if kind == "stutter" and chaos > 0.75:
                    fx = {**fx, "repeat": min(6, int(fx.get("repeat", 3)) + 2)}
                effects.append(fx)
            else:
                effects.append(fx)
        s["effects"] = effects
    return shots


def wants_finishing(state: dict) -> bool:
    """True when the plain morph pass cannot do what was asked (anything beyond flow/draft/16:9)."""
    opt = options(state)
    return opt["energy"] == "dense" or opt["tier"] == "final" or opt["aspect"] != "16:9" or opt["end_card"] \
        or bool(state.get("cut_plan")) or morph_count(state) != "auto"


def demo1_plan() -> dict:
    return json.loads(DEMO1_PLAN.read_text(encoding="utf-8"))


def _render_s(seconds: float, speed: float) -> int:
    return snap_up(max(2.0, seconds * speed - 0.15))


def shot_budget(duration: float) -> int:
    """How many shots a Dense cut may have: 15 for a demo clip, a shot per 1.6 s for a full song (cap 240)."""
    return max(MAX_SHOTS, min(SHOT_BUDGET_MAX, int(round(float(duration) / SHOT_SECONDS_TARGET))))


def clip_plan(shots: list[dict], duration: float, beats: list) -> dict:
    """The morph chain for a long song: ``morphs`` unique renders of ``clip_s`` seconds each, closed into a
    loop (the last morph lands on the first still), and ``assign[i]`` the chain link shot ``i`` plays.

    Walking the loop in order keeps every handoff continuous (shot i ends on the still shot i+1 starts
    on); the chain simply comes round again after ``morphs`` shots, as a chorus does."""
    duration = float(duration)
    bar = 4.0 * _period(beats) if beats else 2.0
    clip_s = snap_up(min(5.0, max(2.0, bar * 1.15)))
    morphs = max(CLIP_BUDGET[0], min(CLIP_BUDGET[1], int(round(duration / CLIP_SECONDS_PER))))
    morphs = max(1, min(morphs, len(shots)))
    assign = [i % morphs for i in range(len(shots))]
    return {"clip_s": int(clip_s), "morphs": morphs, "assign": assign, "reuse": len(shots) > morphs}


def plan_summary(duration: float, beats: list, energy: str = "dense", tier: str = "draft", aspect: str = "9:16",
                 vertical: str = "native", drop: float | None = None) -> dict:
    """What a Make will do for this song: shots, unique morphs, clip length and a time estimate (GPU + look)."""
    duration = float(duration)
    if energy == "dense":
        shots = dense_plan(duration, beats, drop if drop is not None else duration * 0.6)["shots"]
    else:
        shots = plan_shots(duration, beats)
    long_song = duration > LONG_SONG_S
    cp = clip_plan(shots, duration, beats) if long_song else {"clip_s": 2, "morphs": len(shots), "assign": list(range(len(shots))), "reuse": False}
    fps = 24
    compose_s = duration * fps * COMPOSE_S_PER_FRAME["final" if tier == "final" else "draft"]
    est = estimate(cp["morphs"], tier, aspect, vertical, clip_s=cp["clip_s"], compose_s=compose_s)
    return {"duration": round(duration, 2), "shots": len(shots), "morphs": cp["morphs"], "clip_s": cp["clip_s"],
            "reuse": cp["reuse"], "long_song": long_song, "estimate": est}


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
STORY_BEATS = {  # beats per shot by section label; the drop's first bars run at half bars
    "intro": 8, "calm": 8, "sustain": 8, "build": 4, "release": 4, "drop": 2, "drop_late": 4, "outro": 8,
}
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


def story_plan(duration: float, beats: list, sections: list[dict], drop: float | None = None,
               max_shots: int | None = None) -> dict:
    """The music-video cut for a whole song. Verses breathe (two bars a shot, real-time morphs, no tricks),
    builds and choruses drive (a bar a shot, light punches on the downbeats), the drop punches and cuts on
    the half bar for its first bars, the outro eases out. Every section switch starts a shot and is marked
    as a boundary for a transition. When the shot budget is exceeded, every section's shots get longer."""
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
                step = STORY_BEATS[here] * stretch
                i = grid.index(nearest(t))
                t = grid[i + step] if i + step < len(grid) else duration
        if drop is not None and all(abs(c[0] - drop) > 1e-6 for c in cuts):
            cuts.append((round(drop, 4), "drop", True))
        cuts = sorted({c[0]: c for c in cuts}.values())
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
            elif k > 0 and STORY_BEATS.get(role, 4) > STORY_BEATS.get(cuts[k - 1][1], 4):
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


def boundary_transitions(shots: list[dict], vibe: str, *, seed: int = 0) -> list[dict | None]:
    """One premium transition per section boundary (the vibe's recommendation for drop / switch / silence),
    capped at two uses per type by the guardrail; everything else is a clean handoff. One entry per shot."""
    from xenoform import transitions_fx as T

    idx = [i for i, s in enumerate(shots) if i > 0 and s.get("boundary")]
    if not idx:
        return [None] * len(shots)
    kinds = [T.recommend(vibe, str(shots[i]["boundary"])) for i in idx]
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


def find_drop(audio_path: Path | None, beats: list, duration: float) -> float | None:
    if audio_path is None or not Path(audio_path).is_file():
        return None
    try:
        return beatfx.drop_time(Path(audio_path), beats)
    except Exception:
        log.exception("drop detection")
        return None


def shots_for(state: dict, directed: dict, audio_path: Path | None) -> tuple[list[dict], dict]:
    """Validated shots plus the plan they came from."""
    duration = float(directed.get("duration") or 0.0)
    beats = list(directed.get("beats") or [])
    opt = options(state)
    n = morph_count(state)
    speed = macros(state)["speed"]
    if n == "auto" and abs(speed - 0.5) > 0.05 and not state.get("cut_plan"):
        n = speed_count(duration, beats, opt["energy"], speed)  # the speed macro biases the cut density
    if state.get("cut_plan"):
        plan = state["cut_plan"]
    elif opt["energy"] == "dense" and n == "auto" and duration > LONG_SONG_S and len(directed.get("sections") or []) >= 2:
        drop = find_drop(audio_path, beats, duration)
        plan = story_plan(duration, beats, list(directed.get("sections") or []), drop)
    elif opt["energy"] == "dense":
        drop = find_drop(audio_path, beats, duration)
        plan = dense_plan(duration, beats, drop, count=None if n == "auto" else n)
    elif n != "auto":
        plan = flow_plan(duration, beats, n)
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


def _draft_clips(shots, stills, work, cfg, seed, vibe, client, cancel, state=None, report=None, size=None):
    from xenoform.cloud_morph import _local_clips

    return _local_clips(shots, stills, work, cfg, seed, vibe, client=client, cancel=cancel, state=state, report=report,
                        size=size)


def run_simple(directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
               report: Callable[[str, float, str], None], *, cancel: Callable[[], bool] | None = None,
               client=None, engine: str | None = None) -> dict:
    """Plan, render on open weights, then compose with the beat FX at the chosen aspect."""
    started = time.perf_counter()
    opt = options(state)
    work = Path(work) / "simple"
    work.mkdir(parents=True, exist_ok=True)
    shots, plan = shots_for(state, directed, Path(audio_path))
    duration = float(directed.get("duration") or 0.0)
    long_song = duration > LONG_SONG_S and not plan.get("stills") and not state.get("cut_plan")
    chain: dict = {}
    if long_song:
        # Music-video mode: a closed chain of reusable morphs; shots walk the loop in order (see clip_plan).
        chain = clip_plan(shots, duration, list(directed.get("beats") or []))
        vibe, stills = stills_for({**state, "cut_plan": None}, chain["morphs"])
        stills = stills + [stills[0]]  # the loop closes on the first still
        for shot, ci in zip(shots, chain["assign"]):
            shot["clip"] = int(ci)
            shot["render_s"] = int(chain["clip_s"])
            shot["speed"] = round(chain["clip_s"] / max(float(shot.get("seconds") or 0.1), 0.1), 3)
        render_shots = [{"index": i, "start": round(i * chain["clip_s"], 4), "end": round((i + 1) * chain["clip_s"], 4),
                         "seconds": float(chain["clip_s"]), "render_s": int(chain["clip_s"]),
                         "frames": int(chain["clip_s"] * FPS), "effects": []} for i in range(chain["morphs"])]
        report("restyle", 0.05, f"{len(shots)} shots on the beat over a loop of {chain['morphs']} morphs "
                                f"({chain['clip_s']} s each)")
    else:
        render_shots = shots
    vibe, stills = (vibe, stills) if long_song else stills_for({**state, "cut_plan": plan if plan.get("stills") else None}, len(shots) + 1)
    repeat_note = ""
    unique = len({str(s.get("path")) for s in stills})
    if unique < len(stills) and not plan.get("stills") and not long_song:
        # guardrail no_repeat: the still pool wrapped. Use fewer, longer morphs so no still repeats.
        n = max(1, unique - 1)
        shots, plan = shots_for({**state, "morph_count": n}, directed, Path(audio_path))
        if len(shots) > n:  # a planner that ignores the count: keep the first n shots, stretched to fill
            shots = _stretch(shots[:n], float(directed.get("duration") or 0.0))
        vibe, stills = stills_for({**state, "cut_plan": None}, len(shots) + 1)
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
    engine = engine or ("ltx23" if opt["tier"] == "final" else "ltx095")
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
    notes: list[dict] = []
    report("restyle", 0.1, f"{len(render_shots)} {'Final (LTX-2.3)' if engine == 'ltx23' else 'Draft (LTX 0.9.5)'} morphs Â· "
                           f"{len(shots)} shots Â· {opt['energy']} Â· {opt['aspect']}")
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
                got[i] = _draft_clips([render_shots[i]], [stills[i], stills[i + 1]], work, cfg, seed + i, vibe, client, cancel, state)[0]
                renamed = work / f"draft_fallback{i:02d}.mp4"
                shutil.move(str(got[i]), renamed)
                got[i] = renamed
            return got

        clips, notes = final_clips(render_shots, stills, work, cfg, seed, vibe, client=client, cancel=cancel, report=report,
                                   draft=draft, vertical=native, state=state)
    else:
        clips = _draft_clips(render_shots, stills, work, cfg, seed, vibe, client, cancel, state, report=report,
                             size=DRAFT_916 if native_draft else None)
    if long_song:
        clips = [clips[ci] for ci in chain["assign"]]  # one entry per shot, walking the loop
    if opt["tier"] != "final" and size is None and opt["aspect"] == "9:16":
        size = (540, 960)  # Draft: the morphs are 512x288 upscales anyway; the look pass runs 4x faster here
    report("assemble", 0.6, "Cutting to the beat" + (" with beat FX" if opt["fx"] else ""))
    tmp = Path(out_path).with_name(Path(out_path).stem + ".simple.mp4")
    m = macros(state)
    import copy as _copy

    plan_shots = _copy.deepcopy(shots)  # before the macros: a re-cut starts from here
    apply_macros(shots, m, hp if vertical_house else None)
    transitions = boundary_transitions(shots, vibe, seed=seed) if plan.get("name") == "story" else None
    look_preset = beatfx.resolve_dance_preset(opt["dance_fx"], vibe, hp)
    stem_env = stem_env_for(state)
    report("assemble", 0.6, f"House look: dance_fx {look_preset}, stem_orbit {'on' if opt['stem_orbit'] else 'off'}, "
                            f"stems {'split' if stem_env else 'from the mix'}")
    if chain:
        notes.append({"chain": {"morphs": chain["morphs"], "clip_s": chain["clip_s"], "shots": len(shots)}})
    made = beatfx.compose(clips, shots, Path(audio_path), tmp, aspect=opt["aspect"],
                          quality="final" if engine == "ltx23" else "draft", fx=opt["fx"], overlay=opt["overlay"],
                          beats=directed.get("beats") or [], report=report, size=size, fps=fps,
                          dance_fx=look_preset, stem_orbit=opt["stem_orbit"], stem_env=stem_env, macros=m,
                          house=hp, end_card=opt["end_card"], seed=seed,
                          palette_image=str(stills[0]["path"]) if stills else None,
                          adaptive=str(opt.get("dance_fx") or "auto").strip().lower() == "auto",
                          transitions=transitions)
    if made.get("look", {}).get("seconds"):
        log.info("house look took %.1fs for %d frames", made["look"]["seconds"], made["look"]["frames"])
    card = False
    if opt["end_card"]:
        card = beatfx.end_card(tmp, opt["recipe"] or "(none)")
    shutil.copyfile(tmp, out_path)
    info = {"engine": {"ltx23": "LTX-2.3 22B distilled fp8 + 4x upscale (Final)", "ltx095": "LTX 0.9.5 (Draft)",
                       "mock": "mock cross-fades (test)"}[engine],
            "open_weights": True, "energy": opt["energy"], "aspect": opt["aspect"], "tier": opt["tier"],
            "vertical": ("native" if native else "crop") if opt["aspect"] == "9:16" else None,
            "fx": opt["fx"], "overlay": made["overlay"], "end_card": card, "vibe": vibe,
            "stills": [s["file"] for s in stills], "shots": shots, "plan_name": plan.get("name", ""), "chain": chain or None,
            "plan_shots": plan_shots, "clips": [str(c) for c in clips], "audio_path": str(audio_path),
            "transitions": transitions, "size": list(size) if size else None, "fps": fps, "seed": seed,
            "palette_image": str(stills[0]["path"]) if stills else None, "vertical_house": vertical_house,
            "recut_state": {k: state.get(k) for k in ("vibe", "aspect", "quality_tier", "energy_preset", "dance_fx", "stem_orbit",
                                                      "beat_fx", "beat_overlay", "end_card", "stems_path", "macros", "still_background")},
            "roles": plan.get("roles"),
            "handoffs_s": [s["start"] for s in shots] + [shots[-1]["end"]], "fallbacks": notes,
            "render": made["size"], "frames": made["frames"], "seconds": round(time.perf_counter() - started, 2),
            "steps": 8 if engine == "ltx23" else None,
            "fps": made.get("fps", beatfx.FPS), "look": made.get("look") or {}, "macros": m,
            "house": str(hp.get("name") or ""), "stems_path": str(state.get("stems_path") or "")}
    (work / "simple.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
    return info


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


def stills_animatic(directed: dict, state: dict, audio_path: Path, out_path: Path, work: Path, *,
                    size: tuple[int, int] = (216, 384), fps: int = 12) -> dict:
    """The Simple-mode draft: the vibe's stills hard-cut on the planned shots with the song, in a few
    seconds, so the first thing on screen is the real cut's skeleton (not the CPU blob animatic)."""
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    shots, plan = shots_for(state, directed, Path(audio_path))
    duration = float(directed.get("duration") or shots[-1]["end"])
    long_song = duration > LONG_SONG_S and not plan.get("stills")
    if long_song:
        chain = clip_plan(shots, duration, list(directed.get("beats") or []))
        vibe, pool = stills_for({**state, "cut_plan": None}, chain["morphs"])
        picks = [pool[ci] for ci in chain["assign"]]
    else:
        vibe, pool = stills_for({**state, "cut_plan": plan if plan.get("stills") else None}, len(shots) + 1)
        picks = pool[:len(shots)]
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
    lines.append(f"file '{str(picks[-1]['path']).replace(chr(92), '/')}'")  # the concat demuxer needs the last file twice
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
    """Re-compose a finished Simple job from its cached morphs with new knobs, look, orbit or beat FX.

    No GPU: the morph clips, the plan and the song are read from ``<job>/simple/simple.json``. The job's
    ``xenoform.mp4`` is replaced (``publish_file``) and the updated record returned."""
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
    state = dict(rec.get("recut_state") or {})
    state.update({k: v for k, v in (overrides or {}).items() if v is not None})
    opt = options(state)
    hp = house(state, cfg)
    import copy as _copy

    shots = _copy.deepcopy(shots)
    m = macros(state)
    apply_macros(shots, m, hp if rec.get("vertical_house") else None)
    vibe = str(rec.get("vibe") or state.get("vibe") or "")
    transitions = boundary_transitions(shots, vibe, seed=int(rec.get("seed") or 0)) if rec.get("plan_name") == "story" else None
    look_preset = beatfx.resolve_dance_preset(opt["dance_fx"], vibe, hp)
    stem_env = stem_env_for(state)
    size = tuple(rec["size"]) if rec.get("size") else None
    engine = str(rec.get("tier") or "draft")
    tmp = job_dir / "xenoform.recut.mp4"
    if report:
        report("assemble", 0.1, "Re-cutting from the cached morphs (no GPU)")
    made = beatfx.compose(clips, shots, audio, tmp, aspect=opt["aspect"], quality="final" if engine == "final" else "draft",
                          fx=opt["fx"], overlay=opt["overlay"], beats=[], report=report, size=size, fps=int(rec.get("fps") or 24),
                          dance_fx=look_preset, stem_orbit=opt["stem_orbit"], stem_env=stem_env, macros=m, house=hp,
                          end_card=opt["end_card"], seed=int(rec.get("seed") or 0), palette_image=rec.get("palette_image"),
                          adaptive=str(opt.get("dance_fx") or "auto").strip().lower() == "auto", transitions=transitions)
    if opt["end_card"]:
        beatfx.end_card(tmp, str(opt.get("recipe") or "(none)"))
    from xenoform.turbo import publish_file

    publish_file(tmp, job_dir / "xenoform.mp4")
    rec.update({"shots": shots, "look": made.get("look"), "macros": m, "recut_state": state, "transitions": transitions,
                "recuts": int(rec.get("recuts") or 0) + 1})
    rec_path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    return rec
