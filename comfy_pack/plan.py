"""The cut on the beat: the desk's shot planners (``xenoform.dense``, ``xenoform.cloud_morph``), copied with no desk import.

Every function here is the desk's own, kept word for word where it can be, so the pack's storyboard is the shot list a
Make would plan for the same song and knobs. tests/test_comfy_pack_plan.py runs both on the frozen analyses and fails
when they part, so a change to the desk's planner shows up here as a failing test, not as a quiet difference.

What is the desk's and what is left out:

- Flow (``plan_shots``, ``flow_plan``) and Dense (``dense_plan``, ``count_cuts``) for any song, and the story plan
  (``story_plan``) for a Dense song over 20 s: the planners the desk runs when the pacing engine is off (Breathe and
  Drops off, ``pacing.legacy``). The pacing engine itself (``pacing.song_plan``: Breathe's rests, the drop runs and their
  heat) stays on the desk.
- The knobs (``macros``, ``apply_macros``, ``speed_count``) and the long song's chain (``clip_plan``, ``fit_chain``,
  ``merge_to``): one morph a shot and no object twice, the tier and the pool capping the count.
"""

from __future__ import annotations

import math

FPS = 24
ALLOWED_S = (2, 3, 4, 5, 6, 8, 10)
SHOT_TARGET_S = 5.0
EFFECT_TYPES = ("punch", "stutter", "hold", "skip", "reverse")
SPEED_TOLERANCE = 0.2

ENERGY = ("flow", "dense")
MAX_SHOTS = 15
SHOT_SECONDS_TARGET = 1.6
SHOT_BUDGET_MAX = 240
CLIP_BUDGET = (1, 64)
MAX_SHOT_S = 4.0
MORPH_CAP = {"draft": 48, "final": 12, "cloud": 16}
LONG_SONG_S = 20.0
MORPH_MAX = 120
MIN_SLOT_S = 0.3

STORY_BEATS_VISCOUS = {"intro": 8, "calm": 8, "sustain": 8, "build": 8, "release": 8, "drop": 4, "drop_late": 8, "outro": 8}
STORY_BEATS = {"intro": 8, "calm": 8, "sustain": 8, "build": 4, "release": 4, "drop": 2, "drop_late": 4, "outro": 8}
STORY_PACES = ("viscous", "tight")
STORY_PACE_DEFAULT = "viscous"
STORY_SPEED = {"intro": 1.0, "calm": 1.0, "sustain": 1.1, "build": 1.25, "release": 1.25, "drop": 2.5, "drop_late": 1.6, "outro": 1.0}
DROP_HALF_BARS = 8
MERGE_RANK = {"calm": 0, "sustain": 0, "intro": 1, "outro": 1, "release": 1, "drop_late": 2, "build": 3, "drop": 4}


class CutPlanError(ValueError):
    """A cut plan that cannot be rendered as written."""


# ------------------------------------------------------------------------------------------------ cloud_morph


def snap_duration(seconds: float) -> int:
    s = max(float(seconds), ALLOWED_S[0])
    return min(ALLOWED_S, key=lambda a: (abs(a - s), -a))


def plan_shots(duration: float, beats: list | None = None, target: float = SHOT_TARGET_S) -> list[dict]:
    """Beat-aligned shots of about ``target`` seconds covering ``[0, duration]`` (Flow)."""
    duration = max(float(duration or 0.0), 0.5)
    grid = sorted(float(b) for b in (beats or []) if 0.0 < float(b) < duration)
    bounds = [0.0]
    while duration - bounds[-1] > target * 1.4:
        want = bounds[-1] + target
        if grid:
            near = min(grid, key=lambda b: abs(b - want))
            if abs(near - want) <= 1.0 and near - bounds[-1] >= 2.0:
                want = near
        bounds.append(round(want, 4))
    bounds.append(round(duration, 4))
    shots = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        shots.append({"index": i, "start": a, "end": b, "seconds": round(b - a, 4),
                      "frames": max(2, int(round(b * FPS)) - int(round(a * FPS))), "render_s": snap_duration(b - a)})
    return shots


def snap_up(seconds: float) -> int:
    return next((d for d in ALLOWED_S if d >= seconds - 1e-6), ALLOWED_S[-1])


def custom_shots(plan: dict, duration: float | None = None) -> list[dict]:
    """Validate a cut plan and return shots in the shape ``plan_shots`` gives, plus speed, ease and effects."""
    raw = list((plan or {}).get("shots") or [])
    if not raw:
        raise CutPlanError("The cut plan has no shots.")
    shots: list[dict] = []
    prev_end = 0.0
    for i, item in enumerate(raw):
        start, end = float(item["start"]), float(item["end"])
        if abs(start - prev_end) > 0.5 / FPS:
            raise CutPlanError(f"Shot {i + 1} starts at {start:.3f}s but the previous one ends at {prev_end:.3f}s.")
        seconds = end - start
        if seconds < 0.25:
            raise CutPlanError(f"Shot {i + 1} is {seconds:.3f}s; the shortest slot is 0.25s.")
        want = item.get("speed")
        if item.get("render_s") is not None:
            render_s = int(item["render_s"])
            if render_s not in ALLOWED_S:
                raise CutPlanError(f"Shot {i + 1}: render_s {render_s} is not an allowed duration {ALLOWED_S}.")
        else:
            render_s = snap_up(float(want) * seconds if want else seconds)
        speed = render_s / seconds
        if want is not None and abs(speed - float(want)) > SPEED_TOLERANCE * float(want):
            raise CutPlanError(f"Shot {i + 1}: {render_s}s rendered into a {seconds:.3f}s slot plays at {speed:.2f}x, "
                               f"not the {float(want):.2f}x asked for.")
        ease = str(item.get("ease") or "")
        if ease not in ("", "in", "out"):
            raise CutPlanError(f"Shot {i + 1}: ease must be 'in', 'out' or empty.")
        effects = []
        for fx in item.get("effects") or []:
            kind = str(fx.get("type") or "")
            if kind not in EFFECT_TYPES:
                raise CutPlanError(f"Shot {i + 1}: unknown effect {kind!r}; use one of {EFFECT_TYPES}.")
            t = float(fx.get("t", start))
            if not start - 1e-6 <= t < end:
                raise CutPlanError(f"Shot {i + 1}: {kind} at {t:.3f}s is outside {start:.3f}-{end:.3f}s.")
            effects.append({**fx, "type": kind, "t": round(t, 4)})
        shots.append({"index": i, "start": round(start, 4), "end": round(end, 4), "seconds": round(seconds, 4),
                      "render_s": render_s, "speed": round(speed, 3), "ease": ease, "effects": effects})
        prev_end = end
    if duration and prev_end > float(duration) + 0.05:
        raise CutPlanError(f"The cut plan ends at {prev_end:.3f}s, past the {float(duration):.3f}s song.")
    edges = [round(s["start"] * FPS) for s in shots] + [round(shots[-1]["end"] * FPS)]
    for shot, a, b in zip(shots, edges[:-1], edges[1:]):
        shot["frames"] = int(b - a)
    return shots


# ------------------------------------------------------------------------------------------------ dense: counts and knobs


def _period(beats: list) -> float:
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    return float(gaps[len(gaps) // 2]) if gaps else 0.5


def morph_count(state: dict) -> int | str:
    raw = (state or {}).get("morph_count")
    if raw in (None, "", "auto", 0, "0"):
        return "auto"
    try:
        return max(1, min(MORPH_MAX, int(raw)))
    except (TypeError, ValueError):
        return "auto"


def auto_morph_count(duration: float, beats: list, energy: str = "flow") -> int:
    duration = float(duration or 0.0)
    beats = [float(b) for b in beats or [] if 0.0 <= float(b) < duration]
    bar = 4 * _period(beats) if len(beats) > 2 else 2.0
    per = bar / 2 if energy == "dense" else max(bar * 2, 4.0)
    return max(1, min(MORPH_MAX, int(round(duration / per))))


def count_cuts(duration: float, beats: list, count: int, drop: float | None = None) -> list[float]:
    duration = float(duration)
    count = max(1, int(count))
    grid = sorted({round(float(b), 4) for b in beats or [] if 0.0 < float(b) < duration - MIN_SLOT_S})
    if len(grid) < count * 2:
        half = [round((a + b) / 2, 4) for a, b in zip(grid, grid[1:])]
        grid = sorted(set(grid + half))
    d = drop if drop is not None and 0 < drop < duration else None

    def weight(t):
        return t if d is None or t <= d else d + 2 * (t - d)

    total = weight(duration)

    def inv(w):
        return w if d is None or w <= d else d + (w - d) / 2

    cuts = [0.0]
    for k in range(1, count):
        want = inv(total * k / count)
        cand = [g for g in grid if g > cuts[-1] + MIN_SLOT_S - 1e-6 and g < duration - MIN_SLOT_S * (count - k)]
        best = min(cand, key=lambda g: abs(g - want)) if cand else None
        if best is None or abs(best - want) > 0.6 * (duration / count) + 0.25:
            best = max(cuts[-1] + MIN_SLOT_S, min(want, duration - MIN_SLOT_S * (count - k)))
        cuts.append(round(best, 4))
    if d is not None and count > 1:
        k = min(range(1, count), key=lambda i: abs(cuts[i] - d))
        lo = cuts[k - 1] + MIN_SLOT_S
        hi = (cuts[k + 1] if k + 1 < count else duration) - MIN_SLOT_S
        if lo <= d <= hi:
            cuts[k] = round(d, 4)
    return cuts + [round(duration, 4)]


def options(state: dict) -> dict:
    """The part of ``dense.options`` the planners read: the energy preset."""
    energy = str((state or {}).get("energy_preset") or "flow").lower()
    return {"energy": energy if energy in ENERGY else "flow"}


def macros(state: dict) -> dict:
    """The Simple macro knobs (0..1 each, 0.5 neutral), clamped; missing keys are neutral (``dense.macros``)."""
    raw = (state or {}).get("macros") or {}
    out = {}
    for k, d in (("intensity", 0.5), ("speed", 0.5), ("chaos", 0.3), ("glow", 0.4)):
        try:
            out[k] = max(0.0, min(1.0, float(raw.get(k, d))))
        except (TypeError, ValueError, AttributeError):
            out[k] = d
    return out


def speed_count(duration: float, beats: list, energy: str, speed: float) -> int:
    base = auto_morph_count(duration, beats, energy)
    return max(1, min(MORPH_MAX, int(round(base * (0.6 + 0.8 * max(0.0, min(1.0, float(speed))))))))


def apply_macros(shots: list[dict], m: dict) -> list[dict]:
    """Intensity scales each shot's FX intensity (0.5 = four fifths); Chaos above 0.4 adds wobble and shapes the cut's
    own effects: punches scale with it, stutters, holds, skips and reverses vanish when calm and double when wild."""
    gain = 1.6 * float(m.get("intensity", 0.5))
    chaos = float(min(1.0, max(0.0, m.get("chaos", 0.3))))
    wob = max(0.0, (chaos - 0.4) * 1.0)
    for s in shots:
        s["fx_intensity"] = round(min(1.0, float(s.get("fx_intensity", 1.0)) * gain), 3)
        s["chaos"] = round(chaos, 3)
        if wob:
            s["wobble"] = round(max(float(s.get("wobble") or 0.0), wob), 3)
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


# ------------------------------------------------------------------------------------------------ dense: the chain


def merge_to(shots: list[dict], n: int, protected: bool = False) -> list[dict]:
    """``shots`` folded into ``n`` by merging the shortest into its shorter neighbour (``dense._merge_to``)."""
    shots = [dict(s) for s in shots]
    n = max(1, int(n))

    def secs(k: int) -> float:
        return float(shots[k].get("seconds") or 0.0)

    def entry(k: int) -> bool:
        return 0 <= k < len(shots) and str(shots[k].get("boundary") or "") == "drop"

    def rank(k: int) -> float:
        mean = max(1e-3, sum(secs(q) for q in range(len(shots))) / len(shots))
        return MERGE_RANK.get(str(shots[k].get("section") or ""), 1) + 2.0 * math.log2(max(secs(k), 0.05) / mean)

    def partners(i: int, keep_entries: bool) -> list[int]:
        opts = [k for k in (i - 1, i + 1) if 0 <= k < len(shots)]
        if keep_entries:
            opts = [k for k in opts if not (k == i + 1 and entry(i + 1)) and not (k == i - 1 and entry(i))]
        return opts

    while len(shots) > n:
        if protected:
            order = sorted(range(len(shots)), key=lambda k: (rank(k), secs(k)))
            i = next((k for k in order if partners(k, True)), order[0])
            opts = partners(i, True) or partners(i, False)
            same = [k for k in opts if shots[k].get("passage", -1) == shots[i].get("passage", -2)]
            j = min(same or opts, key=lambda k: (rank(k), secs(k)))
        elif (i := min(range(len(shots)), key=secs)) == 0:
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
        for key in ("rest", "rest_s"):
            merged.pop(key, None)
            if b.get(key) is not None:
                merged[key] = b[key]
        lo = min(i, j)
        shots[lo:lo + 2] = [merged]
    for k, s in enumerate(shots):
        if "index" in s:
            s["index"] = k
    return shots


def clip_plan(shots: list[dict], duration: float, beats: list, *, pool: int | None = None, tier: str = "draft") -> dict:
    """The morphs for a long song: one render a shot, no object twice; past the tier's cap or the pool, ``fits`` False
    and the caller plans the song again with fewer, longer shots (``fit_chain``)."""
    duration = float(duration)
    bar = 4.0 * _period(beats) if beats else 2.0
    clip_s = snap_up(min(5.0, max(2.0, bar * 1.15)))
    cap = max(int(MORPH_CAP.get(str(tier or "draft"), MORPH_CAP["draft"])), int(math.ceil(duration / MAX_SHOT_S)))
    morphs = min(len(shots), cap, CLIP_BUDGET[1])
    if pool:
        morphs = min(morphs, max(1, int(pool) - 1))
    morphs = max(CLIP_BUDGET[0], morphs)
    return {"clip_s": int(clip_s), "morphs": morphs, "assign": list(range(morphs)), "reuse": False, "cap": cap,
            "fits": morphs >= len(shots), "wanted": len(shots)}


def _render_s(seconds: float, speed: float) -> int:
    return snap_up(max(2.0, seconds * speed - 0.15))


def shot_budget(duration: float) -> int:
    return max(MAX_SHOTS, min(SHOT_BUDGET_MAX, int(round(float(duration) / SHOT_SECONDS_TARGET))))


def long_cut(duration: float) -> bool:
    """A music-video cut (one morph a shot from a chain, no object twice): a song over ``LONG_SONG_S``."""
    return float(duration or 0.0) > LONG_SONG_S


# ------------------------------------------------------------------------------------------------ dense: the planners


def dense_plan(duration: float, beats: list, drop: float | None = None, max_shots: int | None = None,
               count: int | None = None) -> dict:
    """The demo1 cut for any song: a shot a bar before the drop, a half bar after it, punches, stutters, a hold."""
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
        for _ in range(2):
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


def story_roles(sections: list[dict], duration: float, min_len: float = 6.0) -> list[dict]:
    """Sections with a story role (intro, calm, sustain, build, drop, release, outro), from the analysis labels and each
    passage's level against the song's loudest (``dense._story_roles``)."""
    rows = [dict(sec) for sec in sections if float(sec.get("end", 0)) > float(sec.get("start", 0))]
    if not rows:
        return [{"start": 0.0, "end": float(duration), "label": "calm", "level": 0.5, "role": "calm"}]
    if all(str(r.get("role") or "") in STORY_BEATS for r in rows):
        return [{"label": str(r.get("label") or r["role"]), "start": float(r["start"]), "end": float(r["end"]),
                 "level": float(r.get("level") or 0.0), "role": str(r["role"]),
                 **({"song_heat": float(r["song_heat"])} if r.get("song_heat") is not None else {})} for r in rows]
    top0 = max(float(r.get("level") or 0.0) for r in rows) or 1.0
    merged: list[dict] = []
    for r in rows:
        same = merged and merged[-1]["label"] == r.get("label") and abs(float(merged[-1]["level"]) - float(r.get("level") or 0.0)) < 0.3 * top0
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
            role = "build"
        if i == 0 and role in ("calm", "sustain", "build"):
            role = "intro"
        if i == len(rows) - 1 and role in ("calm", "sustain", "release") and len(rows) > 1:
            role = "outro"
        r["role"] = role
    return rows


def story_pace(state: dict | None) -> str:
    pace = str((state or {}).get("pace") or STORY_PACE_DEFAULT).strip().lower()
    return pace if pace in STORY_PACES else STORY_PACE_DEFAULT


def story_plan(duration: float, beats: list, sections: list[dict], drop: float | None = None,
               max_shots: int | None = None, pace: str = STORY_PACE_DEFAULT) -> dict:
    """The music-video cut for a whole song: every passage breathes, the drop punches, every section switch a boundary."""
    table = STORY_BEATS if pace == "tight" else STORY_BEATS_VISCOUS
    duration = float(duration)
    max_shots = shot_budget(duration) if max_shots is None else int(max_shots)
    grid = sorted(float(b) for b in beats if 0.0 <= float(b) < duration)
    if len(grid) < 4:
        return dense_plan(duration, beats, drop, max_shots)
    period = _period(grid)
    roles = story_roles(sections, duration, min_len=max(6.0, 8 * period))
    if drop is None:
        drops = [r for r in roles if r["role"] == "drop"]
        drop = float(drops[0]["start"]) if drops else None
    if drop is not None:
        drop = min(grid, key=lambda b: abs(b - drop))
        for r in roles:
            if r["role"] == "drop" and abs(float(r["start"]) - drop) <= 4 * period + 1e-6 and float(r["start"]) != drop:
                r["start"] = drop

    def nearest(t: float) -> float:
        return min(grid, key=lambda b: abs(b - t))

    for stretch in (1, 2, 4, 8):
        cuts: list[tuple[float, str, bool]] = []
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
        for c in cuts:
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
                kind = "silence"
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


def flow_plan(duration: float, beats: list, count: int) -> dict:
    """Flow energy with a fixed count: even, beat-snapped shots, no effects."""
    cuts = count_cuts(duration, beats, count, None)
    shots = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        render_s = _render_s(b - a, 1.0)
        shots.append({"start": a, "end": b, "render_s": render_s, "speed": round(render_s / (b - a), 3), "effects": []})
    return {"name": f"flow ({count} forms)", "shots": shots}


def _analysis_sections(song: dict) -> list[dict]:
    rows = song.get("analysis_sections")
    if rows is None:
        rows = song.get("sections")
    return [r for r in (rows or []) if r.get("label")]


def shots_for(state: dict, directed: dict, *, drop: float | None = None) -> tuple[list[dict], dict]:
    """Validated shots plus the plan they came from, as ``dense.shots_for`` plans them with the pacing engine off.
    ``directed`` is the song (``duration``, ``beats``, ``sections``); ``drop`` the song's main drop in seconds."""
    duration = float(directed.get("duration") or 0.0)
    beats = list(directed.get("beats") or [])
    opt = options(state)
    n = morph_count(state)
    speed = macros(state)["speed"]
    if n == "auto" and abs(speed - 0.5) > 0.05 and not state.get("cut_plan"):
        n = speed_count(duration, beats, opt["energy"], speed)
    try:
        max_shots = int(state.get("max_shots") or 0) or None
    except (TypeError, ValueError):
        max_shots = None
    if state.get("cut_plan"):
        plan = state["cut_plan"]
    elif opt["energy"] == "dense" and n == "auto" and duration > LONG_SONG_S and len(_analysis_sections(directed)) >= 2:
        plan = story_plan(duration, beats, _analysis_sections(directed), drop, max_shots=max_shots, pace=story_pace(state))
    elif opt["energy"] == "dense":
        count = None if n == "auto" else n
        if max_shots and (count is None or count > max_shots):
            count = max_shots
        plan = dense_plan(duration, beats, drop, max_shots=max_shots, count=count)
    elif n != "auto" or max_shots:
        plan = flow_plan(duration, beats, min(n, max_shots) if (n != "auto" and max_shots) else (max_shots if n == "auto" else n))
    else:
        return plan_shots(duration, beats), {"name": "flow", "shots": []}
    shots = custom_shots(plan, duration)
    for shot, raw in zip(shots, plan.get("shots") or []):
        for key in ("section", "boundary"):
            if raw.get(key):
                shot[key] = raw[key]
    return shots, plan


def fit_chain(state: dict, directed: dict, chain: dict, pool_n: int | None, tier: str, *,
              drop: float | None = None) -> tuple[list[dict], dict, dict]:
    """A plan the chain cannot afford, made again with ``max_shots`` at the morphs it can, merged down to that count."""
    duration = float(directed.get("duration") or 0.0)
    beats_list = list(directed.get("beats") or [])
    capped = {**state, "max_shots": chain["morphs"]}
    shots, plan = shots_for(capped, directed, drop=drop)
    if len(shots) > chain["morphs"]:
        shots = merge_to(shots, chain["morphs"], protected=False)
    return shots, plan, clip_plan(shots, duration, beats_list, pool=pool_n or None, tier=tier)


def stretch(shots: list[dict], duration: float) -> list[dict]:
    """Shot lengths scaled so they still fill ``duration`` after dropping some (``dense._stretch``)."""
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
