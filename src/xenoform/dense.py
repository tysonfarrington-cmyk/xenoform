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
import shutil
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
    """9:16 on Final renders natively unless the crop is asked for; Draft always crops (for now)."""
    tier = str(state.get("quality_tier") or "draft").lower()
    asked = str(state.get("vertical_mode") or "auto").lower()
    if tier != "final":
        return "crop"
    return asked if asked in VERTICAL else "native"
MAX_SHOTS = 15  # 16 stills: the black pool holds 17, the other vibes 12 (the chain wraps)

# ---- morph count: "auto" (from clip length + BPM) or a fixed number of forms
MORPH_SLIDER = (1, 40)      # the desk slider; the number box allows up to MORPH_MAX
MORPH_MAX = 120
MIN_SLOT_S = 0.3            # a morph never gets less screen time than this
# measured on an RTX 3080 Ti 12 GB (ComfyUI shared, 2 s renders): seconds per morph and peak VRAM
COST = {"draft": {"s": 35.0, "vram_gb": 7.5}, "final": {"s": 110.0, "vram_gb": 11.2},
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


def estimate(count: int, tier: str = "draft", aspect: str = "16:9", vertical: str = "native") -> dict:
    """Rough render time and VRAM for ``count`` morphs on this tier."""
    key = "final_916" if tier == "final" and aspect == "9:16" and vertical == "native" else tier
    c = COST.get(key, COST["draft"])
    secs = round(c["s"] * int(count) + (20 if tier != "preview" else 0))
    return {"morphs": int(count), "seconds": secs, "minutes": round(secs / 60, 1), "peak_vram_gb": c["vram_gb"],
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
    }


def wants_finishing(state: dict) -> bool:
    """True when the plain morph pass cannot do what was asked (anything beyond flow/draft/16:9)."""
    opt = options(state)
    return opt["energy"] == "dense" or opt["tier"] == "final" or opt["aspect"] != "16:9" or opt["end_card"] \
        or bool(state.get("cut_plan")) or morph_count(state) != "auto"


def demo1_plan() -> dict:
    return json.loads(DEMO1_PLAN.read_text(encoding="utf-8"))


def _render_s(seconds: float, speed: float) -> int:
    return snap_up(max(2.0, seconds * speed - 0.15))


def dense_plan(duration: float, beats: list, drop: float | None = None, max_shots: int = MAX_SHOTS,
               count: int | None = None) -> dict:
    """A demo1-style cut plan for any song.

    Before the drop: a shot per bar (4 beats), morphs a little faster than real time.
    The bar before the drop eases in. On the drop: punch + 4x2 stutter, then a shot per
    half bar (2 beats) at ~2.5x, with a punch on every downbeat, a 120 ms hold just
    before the hardest hit one bar in, and a short reverse on the last hit. When that
    is more than ``max_shots`` shots, the bars get longer until it fits.
    """
    duration = float(duration)
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
    if state.get("cut_plan"):
        plan = state["cut_plan"]
    elif opt["energy"] == "dense":
        drop = find_drop(audio_path, beats, duration)
        plan = dense_plan(duration, beats, drop, count=None if n == "auto" else n)
    elif n != "auto":
        plan = flow_plan(duration, beats, n)
    else:
        return plan_shots(duration, beats), {"name": "flow", "shots": []}
    return custom_shots(plan, duration), plan


def _draft_clips(shots, stills, work, cfg, seed, vibe, client, cancel):
    from xenoform.cloud_morph import _local_clips

    return _local_clips(shots, stills, work, cfg, seed, vibe, client=client, cancel=cancel)


def run_simple(directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
               report: Callable[[str, float, str], None], *, cancel: Callable[[], bool] | None = None,
               client=None, engine: str | None = None) -> dict:
    """Plan, render on open weights, then compose with the beat FX at the chosen aspect."""
    started = time.perf_counter()
    opt = options(state)
    work = Path(work) / "simple"
    work.mkdir(parents=True, exist_ok=True)
    shots, plan = shots_for(state, directed, Path(audio_path))
    vibe, stills = stills_for({**state, "cut_plan": plan if plan.get("stills") else None}, len(shots) + 1)
    seed = int(state.get("seed") or 2727)
    engine = engine or ("ltx23" if opt["tier"] == "final" else "ltx095")
    native = opt["aspect"] == "9:16" and opt["vertical"] == "native" and engine in {"ltx23", "mock"} \
        and opt["tier"] == "final"
    from xenoform import final_tier

    size = final_tier.sizes(True)["out"] if native else None
    notes: list[dict] = []
    report("restyle", 0.1, f"{len(shots)} {'Final (LTX-2.3)' if engine == 'ltx23' else 'Draft (LTX 0.9.5)'} morphs Â· "
                           f"{opt['energy']} Â· {opt['aspect']}")
    if engine == "mock":
        from xenoform.cloud_morph import _mock_clips

        if native:
            from xenoform.portrait import portrait_stills

            clips = _mock_clips(shots, portrait_stills(stills, work), work, *final_tier.RENDER_916)
        else:
            clips = _mock_clips(shots, stills, work, 768, 432)
    elif engine == "ltx23":
        from xenoform.final_tier import final_clips

        def draft(indices: list[int]) -> dict[int, Path]:
            sub = [shots[i] for i in indices]
            sub_stills = []
            for i in indices:
                sub_stills += [stills[i], stills[i + 1]]
            got = {}
            for k, i in enumerate(indices):
                got[i] = _draft_clips([shots[i]], [stills[i], stills[i + 1]], work, cfg, seed + i, vibe, client, cancel)[0]
                renamed = work / f"draft_fallback{i:02d}.mp4"
                shutil.move(str(got[i]), renamed)
                got[i] = renamed
            return got

        clips, notes = final_clips(shots, stills, work, cfg, seed, vibe, client=client, cancel=cancel, report=report, draft=draft,
                                   vertical=native)
    else:
        clips = _draft_clips(shots, stills, work, cfg, seed, vibe, client, cancel)
    report("assemble", 0.6, "Cutting to the beat" + (" with beat FX" if opt["fx"] else ""))
    tmp = Path(out_path).with_name(Path(out_path).stem + ".simple.mp4")
    made = beatfx.compose(clips, shots, Path(audio_path), tmp, aspect=opt["aspect"],
                          quality="final" if engine == "ltx23" else "draft", fx=opt["fx"], overlay=opt["overlay"],
                          beats=directed.get("beats") or [], report=report, size=size)
    card = False
    if opt["end_card"]:
        card = beatfx.end_card(tmp, opt["recipe"] or "(none)")
    shutil.copyfile(tmp, out_path)
    info = {"engine": {"ltx23": "LTX-2.3 22B distilled fp8 + 4x upscale (Final)", "ltx095": "LTX 0.9.5 (Draft)",
                       "mock": "mock cross-fades (test)"}[engine],
            "open_weights": True, "energy": opt["energy"], "aspect": opt["aspect"], "tier": opt["tier"],
            "vertical": ("native" if native else "crop") if opt["aspect"] == "9:16" else None,
            "fx": opt["fx"], "overlay": made["overlay"], "end_card": card, "vibe": vibe,
            "stills": [s["file"] for s in stills], "shots": shots, "plan_name": plan.get("name", ""),
            "handoffs_s": [s["start"] for s in shots] + [shots[-1]["end"]], "fallbacks": notes,
            "render": made["size"], "frames": made["frames"], "seconds": round(time.perf_counter() - started, 2),
            "steps": 8 if engine == "ltx23" else None}
    (work / "simple.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
    return info
