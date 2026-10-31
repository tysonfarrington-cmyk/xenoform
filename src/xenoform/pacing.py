"""The pacing engine: song roles that are true, Breathe and the drops (docs/MUSIC_VIDEO_PLAN.md sections 2 and 3).

The story plan (``dense.story_plan``) was the only planner with section roles, and it mostly never ran: the
``morph_density`` guardrail rewrote Forms "auto" to a count for most songs, a Forms count or an off-centre Speed did the
same, and the default 30 s prototype went through ``dense_plan`` with no roles at all (research 31 Oct, pipeline map
2.1). ``song_plan`` here is the planner a Make uses whenever the song is over ``dense.LONG_SONG_S`` and has sections:
a requested count, an off-centre Speed and the guardrail's budget scale its tables instead of replacing it, and the
budget is spent by role, the drops first and the calm passages last.

Two body keys choose how a cut is shaped (both re-cut-able where the shot lengths stay):

- ``breathe`` (default False until Tys has judged the sheets): the music-video shape, the profile table of plan
  section 3 (calm passages calm, a hero object given airtime);
- ``drop_mode``: "auto" (default), "max" (every drop run at full heat) or "off" (one drop, as before).

``breathe: False`` with ``drop_mode: "off"`` is the cut as it was made before this module (``legacy``): the guardrail's
rewrite, ``dense_plan`` where it ran and the viscous story plan with one drop, so every record made before re-cuts the
same. A record that has neither key in its ``recut_state`` is such a record (``recut_modes``).
"""
from __future__ import annotations

import math

BREATHE_DEFAULT = False   # Tys, 31 Oct: off until he has judged the Draft sheets of today's cut against Breathe
DROP_MODES = ("auto", "max", "off")
DROP_MODE_DEFAULT = "auto"
FORM_BUDGET_KEY = "form_budget"   # forms per 20 s the morph_density guardrail hands the planner (configs/guardrails.json)
MIN_BEATS = 2                     # nothing under two beats (a morph you can follow)
MAX_BEATS = 64                    # the longest step the budget may stretch a role to
GAP_BARS = 2.0                    # a stretch with no tracked beat longer than this gets a tempo grid
DROP_HALF_BARS = 8                # one drop (drop_mode "off"): the bars after the drop that are "drop", then "drop_late"

# beats a shot by role (a bar is four beats). Viscous is the Simple default since the 24 Oct A/B (dense.STORY_BEATS_VISCOUS),
# tight the denser plan (dense.STORY_BEATS); both are copied here so the legacy story plan keeps its own tables.
VISCOUS = {"intro": 8, "calm": 8, "sustain": 8, "build": 8, "release": 8, "drop": 4, "drop_late": 8, "outro": 8}
TIGHT = {"intro": 8, "calm": 8, "sustain": 8, "build": 4, "release": 4, "drop": 2, "drop_late": 4, "outro": 8}
# what gives up morphs first when the budget is short (lowest first) and gets them first when there are more to spend:
# the calm passages breathe, the drops are the event. A role's step doubles when its priority plus the doublings it has
# had is the lowest, so a tight budget lengthens the calm shots about a doubling and a half before the drops' first
# (the gaps are small on purpose: a 27 s calm shot over one 4 s morph is a slideshow, not breathing)
PRIORITY = {"calm": 0.0, "sustain": 0.0, "intro": 0.25, "outro": 0.25, "release": 0.5, "build": 0.75, "drop_late": 1.0,
            "drop": 1.5}
SPEED = {"intro": 1.0, "calm": 1.0, "sustain": 1.1, "build": 1.25, "release": 1.25, "drop": 2.5, "drop_late": 1.6, "outro": 1.0}


# ------------------------------------------------------------------------------------------------ the two keys


def _flag(raw, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    if isinstance(raw, str):
        return raw.strip().lower() not in ("off", "false", "0", "no", "none")
    return bool(raw)


def breathe_of(state: dict | None, default: bool = BREATHE_DEFAULT) -> bool:
    """The body's ``breathe`` (on / off); missing is ``default``."""
    return _flag((state or {}).get("breathe"), default)


def drop_mode_of(state: dict | None, default: str = DROP_MODE_DEFAULT) -> str:
    """The body's ``drop_mode``: "auto", "max" or "off"; anything else is ``default``."""
    raw = (state or {}).get("drop_mode")
    text = str(raw if raw is not None else default).strip().lower()
    return text if text in DROP_MODES else default


def legacy(state: dict | None) -> bool:
    """True when the cut is shaped as it was before the pacing engine: Breathe off and Drops off."""
    return not breathe_of(state) and drop_mode_of(state) == "off"


def recut_modes(recut_state: dict | None) -> dict:
    """The two keys a re-cut starts from: the record's own, and for a record made before them (neither key in its
    ``recut_state``) Breathe off and Drops off, so it re-cuts as it was made."""
    rs = recut_state or {}
    return {"breathe": breathe_of(rs, False), "drop_mode": drop_mode_of(rs, "off")}


# ------------------------------------------------------------------------------------------------ the beat grid


def _median_gap(beats: list[float]) -> float:
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    return float(gaps[len(gaps) // 2]) if gaps else 0.0


def grid_for(beats, duration: float, tempo: float | None = None) -> list[float]:
    """The song's beats with a tempo grid laid over every stretch the tracker left beatless (the bundled Ambient song
    has no beat before 72 s, and the story plan made one 72 s shot of it): before the first beat, after the last, and
    inside any gap over ``GAP_BARS`` bars, at the song's own beat step (its median, else ``tempo``). Tracked beats are
    kept where they are."""
    duration = float(duration)
    b = sorted({round(float(x), 4) for x in beats or [] if 0.0 <= float(x) < duration})
    period = _median_gap(b) if len(b) >= 3 else 0.0
    if period <= 0.05 and tempo:
        period = 60.0 / max(30.0, min(300.0, float(tempo)))
    if period <= 0.05:
        return b
    if not b:
        return [round(i * period, 4) for i in range(int(duration / period) + 1) if i * period < duration]
    out: list[float] = []
    t = b[0] - period
    head = []
    while t > 0.05:
        head.append(round(t, 4))
        t -= period
    out.extend(reversed(head))
    gap = GAP_BARS * 4 * period
    for x, y in zip(b, b[1:]):
        out.append(x)
        if y - x > gap:
            n = max(1, int(round((y - x) / period)))
            out.extend(round(x + k * (y - x) / n, 4) for k in range(1, n))
    out.append(b[-1])
    t = b[-1] + period
    while t < duration - 0.05:
        out.append(round(t, 4))
        t += period
    return out


def bar_phase(grid: list[float], anchors: list[tuple[float, float]], first_beat: float | None = None) -> int:
    """Which grid index starts a bar (0..3): the phase that puts the most weight of ``anchors`` (time, weight: section
    starts, drops heaviest) on a bar line, the first tracked beat's phase breaking a tie."""
    if len(grid) < 4:
        return 0
    k0 = min(range(len(grid)), key=lambda i: abs(grid[i] - first_beat)) % 4 if first_beat is not None else 0
    score = [0.0] * 4
    for t, w in anchors:
        i = min(range(len(grid)), key=lambda j: abs(grid[j] - t))
        if abs(grid[i] - t) < 0.35:
            score[i % 4] += float(w)
    best = max(score)
    if best <= 0:
        return k0
    return k0 if score[k0] >= best - 1e-9 else score.index(best)


# ------------------------------------------------------------------------------------------------ the drops


LATE_BARS = 16      # a drop run's bars before its tail is drop_late (the role used to start 8 bars after ONE drop time)
HEAT_FLOOR = 0.2    # the quietest drop run still runs a little hot
QUIET_END = 0.6     # a last passage under this share of the loudest is the outro, whatever its label


def refine_roles(rows: list[dict], sections: list[dict], *, period: float) -> list[dict]:
    """The story roles made true for the drops (research 31 Oct, the montage's G16). A drop passage the fold started early
    (Glitch Out's first drop at 87.3 s: a sustain and a build before the drop at 92.0) starts on its first span the
    analysis labelled drop, the passage before it running up to it; and a quiet last passage is the outro (Glitch Out's
    last 13 s, at half the loudest level, were a sixth drop)."""
    rows = [dict(r) for r in rows]
    raw = sorted((float(s["start"]), float(s["end"])) for s in sections or [] if str(s.get("label") or "") == "drop")
    bar = 4 * float(period)
    top = max((float(r.get("level") or 0.0) for r in rows), default=0.0) or 1.0
    if len(rows) > 1 and rows[-1]["role"] in ("drop", "build") and float(rows[-1].get("level") or 0.0) < QUIET_END * top:
        rows[-1]["role"] = "outro"
    for i in range(1, len(rows)):
        r = rows[i]
        if r["role"] != "drop":
            continue
        inside = [a for a, b in raw if float(r["start"]) - 1e-6 <= a < float(r["end"])]
        if inside and inside[0] - float(r["start"]) >= bar / 2 - 1e-6 and inside[0] <= float(r["end"]) - 2 * bar:
            rows[i - 1]["end"] = inside[0]
            r["start"] = inside[0]
    return rows


def split_at_drop(rows: list[dict], drop: float | None, period: float) -> list[dict]:
    """A drop run that holds the song's drop well inside it (a window cut a little before the drop, its run-up folded
    into the run by the analysis) is split there: the stretch before is the build, the run starts on the drop."""
    if drop is None:
        return rows
    bar = 4 * float(period)
    d = float(drop)
    out: list[dict] = []
    for r in rows:
        a, b = float(r["start"]), float(r["end"])
        if r["role"] == "drop" and a + 2 * bar <= d <= b - 2 * bar:
            out.append({**r, "end": d, "role": "build", "label": "build"})
            out.append({**r, "start": d})
        else:
            out.append(r)
    return out


def _weighted_median(rows: list[dict]) -> float:
    pairs = sorted((float(r.get("level") or 0.0), max(0.0, float(r["end"]) - float(r["start"]))) for r in rows)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for level, w in pairs:
        acc += w
        if acc >= total / 2:
            return level
    return pairs[-1][0] if pairs else 0.0


def drop_runs(rows: list[dict], drop: float | None, period: float, mode: str = DROP_MODE_DEFAULT) -> dict | None:
    """Every drop row of the roles numbered as a run (``drop_run``) with its ``heat``, 0..1 by its level between the
    song's median level and the main run's: the main run, the one the song's drop (``beatfx.drop_time``) opens (its start
    within a bar before the drop or two after it: the drop time can sit on the riser), else the one that holds it, else
    the loudest, is 1.0, and so is every run under ``mode`` "max". The rows are annotated in place; returns the main row
    (None: no drop)."""
    runs = [r for r in rows if r["role"] == "drop"]
    if not runs:
        return None
    main = None
    if drop is not None:
        d = float(drop)
        # a run that starts on the drop (a bar either side, two after for a long riser) is it, before one that holds
        # it in its last beats
        near = [r for r in runs if -4 * period - 1e-6 <= float(r["start"]) - d <= 8 * period + 1e-6]
        main = min(near, key=lambda r: abs(float(r["start"]) - d)) if near else None
        if main is None:
            main = next((r for r in runs if float(r["start"]) <= d < float(r["end"])), None)
    if main is None:
        main = max(runs, key=lambda r: float(r.get("level") or 0.0))
    floor = _weighted_median(rows)
    top = float(main.get("level") or 0.0)
    span = max(0.05, top - floor)
    for k, r in enumerate(runs):
        r["drop_run"] = k
        r["main"] = r is main
        if mode == "max" or r is main:
            r["heat"] = 1.0
        else:
            r["heat"] = round(max(HEAT_FLOOR, min(1.0, (float(r.get("level") or 0.0) - floor) / span)), 3)
    return main


def main_drop(features: dict, drop: float | None) -> float | None:
    """The first beat of the song's main drop run (``drop_runs`` on its own analysis), which a prototype window is cut
    around: the drop time alone can sit on a riser or on a build well before the drop (Ambient: 120 s, against the drop
    the analysis puts at 143 s, so its 30 s prototype held no drop at all). ``drop`` when the song has no drop run."""
    from xenoform import dense

    duration = float(features.get("duration") or 0.0)
    sections = dense._analysis_sections(features)
    if duration <= 0 or len(sections) < 2:
        return drop
    grid = grid_for(list(features.get("beats") or []), duration, features.get("tempo"))
    period = _median_gap(grid) or 0.5
    rows = dense._story_roles(sections, duration, min_len=max(6.0, 8 * period))
    rows = split_at_drop(refine_roles(rows, sections, period=period), drop, period)
    main = drop_runs(rows, drop, period)
    return round(float(main["start"]), 4) if main is not None else drop


# ------------------------------------------------------------------------------------------------ the plan


def _role_steps(table: dict, scale: float = 1.0) -> dict:
    return {k: max(MIN_BEATS, int(round(v * scale))) for k, v in table.items()}


def song_plan(duration: float, beats: list, sections: list[dict], drop: float | None = None, *,
              max_shots: int | None = None, target: int | None = None, breathe: bool = False,
              drop_mode: str = DROP_MODE_DEFAULT, pace: str = "viscous", tempo: float | None = None) -> dict:
    """The music-video cut for a whole song or a window of one, with roles, on the beat grid (``grid_for``).

    Every passage (a run of one role, its start pinned on the beat the analysis put it) cuts on the bar lines at its
    role's beats a shot; a section switch starts a shot and is a boundary for a transition. ``max_shots`` (the tier's
    or the pool's cap, the guardrail's budget) and ``target`` (a requested Forms count, or the Speed knob's scaling of
    the plan's own count) are met by changing the beats a shot by role: the calm passages give up morphs first and get
    them last, the drops the other way round. Returns ``dense.story_plan``'s shape (``name`` "story", ``drop``,
    ``shots`` with ``section`` and ``boundary``, ``roles``) plus ``passages``."""
    from xenoform import dense

    duration = float(duration)
    grid = grid_for(beats, duration, tempo)
    if len(grid) < 4:
        return dense.dense_plan(duration, beats, drop, max_shots)
    period = _median_gap(grid) or 0.5
    rows = dense._story_roles(sections, duration, min_len=max(6.0, 8 * period))  # a passage is at least two bars
    per_run = drop_mode in ("auto", "max")
    runs: list[dict] = []
    if per_run:
        # every drop run is its own passage with its heat; the song's drop (beatfx.drop_time, the biggest rise, which can
        # sit on the riser two beats early) only says which run is the main one, and the record's drop is that run's
        # first beat, where the analysis put the drop
        rows = split_at_drop(refine_roles(rows, sections, period=period), drop, period)
        main = drop_runs(rows, drop, period, drop_mode)
        runs = [r for r in rows if r["role"] == "drop"]
        drop = min(grid, key=lambda b: abs(b - float(main["start"]))) if main is not None else None
    else:
        if drop is None:
            firsts = [r for r in rows if r["role"] == "drop"]
            drop = float(firsts[0]["start"]) if firsts else None
        if drop is not None:
            drop = min(grid, key=lambda b: abs(b - drop))
            for r in rows:  # the drop section starts on the drop itself when the analysis put it within a bar
                if r["role"] == "drop" and abs(float(r["start"]) - drop) <= 4 * period + 1e-6 and float(r["start"]) != drop:
                    r["start"] = drop
    first_beat = min((float(b) for b in beats or [] if 0 <= float(b) < duration), default=None)
    anchors = [(float(r["start"]), 3.0 if r["role"] == "drop" else 1.0) for r in rows if float(r["start"]) > 0]
    if drop is not None:
        anchors.append((float(drop), 4.0))
    phase = bar_phase(grid, anchors, first_beat)
    table = dict(TIGHT if pace == "tight" else VISCOUS)
    hard = max(1, int(max_shots)) if max_shots else dense.shot_budget(duration)  # never more shots than this
    limit = min(hard, max(1, int(target))) if target else hard

    def index_of(t: float) -> int:
        return min(range(len(grid)), key=lambda i: abs(grid[i] - t))

    # the passages: each role row on its beat (the first from 0), in order, none empty
    passages: list[dict] = []
    for r in rows:
        i0 = 0 if not passages else index_of(float(r["start"]))
        if passages and i0 <= passages[-1]["i0"]:
            continue
        p = {"role": r["role"], "i0": i0, "start": 0.0 if not passages else grid[i0], "level": float(r.get("level") or 0.0)}
        if per_run and r["role"] == "drop":
            p.update({"drop_run": int(r["drop_run"]), "heat": float(r["heat"]), "main": bool(r.get("main"))})
        passages.append(p)
    for p, q in zip(passages, passages[1:] + [None]):
        p["i1"] = q["i0"] if q else len(grid)
        p["end"] = q["start"] if q else duration

    def zone_role(p: dict, k: int) -> str:
        if p["role"] != "drop":
            return p["role"]
        if per_run:  # the tail of a long run, after LATE_BARS of it
            return "drop_late" if grid[k] >= p["start"] + LATE_BARS * 4 * period - 1e-6 else "drop"
        if drop is not None and grid[k] >= drop + DROP_HALF_BARS * 4 * period - 1e-6:  # one drop, as before
            return "drop_late"
        return "drop"

    def cut(steps: dict) -> list[tuple[int, str, bool, int]]:
        """(grid index, role, starts a passage, passage index) for every shot."""
        out: list[tuple[int, str, bool, int]] = []
        for pi, p in enumerate(passages):
            k, first = p["i0"], True
            end = p["i1"]
            while k < end and grid[k] < duration - 0.3:
                role = zone_role(p, k)
                out.append((k, role, first, pi))
                step = steps[role]
                nxt = k + step
                if step % 4 == 0 and (nxt - phase) % 4:  # land the next cut on a bar line (the montage cut on beat 1)
                    bar = nxt - ((nxt - phase) % 4)
                    nxt = bar if bar >= k + MIN_BEATS else bar + 4
                # a change of zone inside the passage (the drop's late bars) starts on its own beat, unless that would
                # leave a sliver of a shot before it
                change = next((j for j in range(k + 1, min(nxt, end)) if zone_role(p, j) != role), None)
                if change is not None and change - k >= MIN_BEATS:
                    nxt = change
                if nxt < end and end - nxt < MIN_BEATS:
                    nxt = end  # a sliver at the passage end folds into the shot before it
                k, first = nxt, False
        return out

    steps = _role_steps(table)
    present = sorted({zone_role(p, k) for p in passages for k in range(p["i0"], max(p["i0"] + 1, p["i1"]))
                      if k < len(grid)})
    cuts = cut(steps)
    base = dict(steps)
    for _ in range(96):  # the budget, spent by role: the calm passages give up morphs first
        if len(cuts) <= limit:
            break
        cands = [r for r in present if steps.get(r, 0) < MAX_BEATS]
        if not cands:
            break
        r = min(cands, key=lambda x: (PRIORITY.get(x, 1.0) + math.log2(steps[x] / max(1, base[x])), PRIORITY.get(x, 1.0)))
        steps[r] *= 2
        cuts = cut(steps)
    if target and len(cuts) < min(hard, int(target)):  # more forms asked for than the plan makes: the drops get them first
        ceiling = min(hard, int(target) + max(1, int(target) // 10))
        for _ in range(96):
            cands = sorted((r for r in present if steps.get(r, 0) > MIN_BEATS),
                           key=lambda x: (PRIORITY.get(x, 1.0) - math.log2(max(1, base[x]) / steps[x]), PRIORITY.get(x, 1.0)),
                           reverse=True)
            taken = False
            for r in cands:  # the role that wants them most, else the next whose halving still fits under the ceiling
                trial = dict(steps)
                trial[r] = max(MIN_BEATS, trial[r] // 2)
                more = cut(trial)
                if len(cuts) < len(more) <= ceiling:
                    steps, cuts, taken = trial, more, True
                    break
            if not taken or len(cuts) >= int(target):
                break
    times = [grid[k] if n else 0.0 for n, (k, _, _, _) in enumerate(cuts)] + [duration]
    shots = []
    for n, ((k, role, starts, pi), b) in enumerate(zip(cuts, times[1:])):
        a = times[n]
        seconds = b - a
        if seconds < 0.3:
            continue
        p = passages[pi]
        render_s = dense._render_s(seconds, SPEED.get(role, 1.25))
        effects = []
        on_beat = abs(grid[k] - a) < 1e-3
        if drop is not None and abs(a - drop) < 1e-3:
            effects += [{"type": "punch", "t": a, "strength": 1.0}, {"type": "stutter", "t": a, "frames": 2, "repeat": 4}]
        elif role in ("drop", "drop_late", "build") and on_beat:
            effects.append({"type": "punch", "t": a, "strength": 0.6 if role != "build" else 0.4})
        shot = {"start": round(a, 4), "end": round(b, 4), "render_s": render_s, "speed": round(render_s / seconds, 3),
                "effects": effects, "section": role, "passage": pi}
        if "drop_run" in p:
            shot.update({"drop_run": p["drop_run"], "heat": p["heat"]})
        if starts and n > 0:
            if ("drop_run" in p) or (drop is not None and abs(a - drop) < 1e-3):
                kind = "drop"  # every drop run opens on a drop boundary (one drop, as before, with Drops off)
            elif steps.get(role, 4) > steps.get(cuts[n - 1][1], 4):
                kind = "silence"  # dropping into a quieter passage
            else:
                kind = "switch"
            shot["boundary"] = kind
        shots.append(shot)
    if shots:
        if shots[0]["section"] == "intro":
            shots[0]["ease"] = "in"
        if shots[-1]["section"] == "outro":
            shots[-1]["ease"] = "out"
        shots[-1]["end"] = round(duration, 4)
    return {"name": "story", "drop": round(drop, 4) if drop is not None else None, "shots": shots,
            "roles": [(r["role"], round(float(r["start"]), 2), round(float(r["end"]), 2)) for r in rows],
            "passages": [{"role": p["role"], "start": round(p["start"], 3), "end": round(p["end"], 3),
                          **({"drop_run": p["drop_run"], "heat": p["heat"], "main": p["main"]} if "drop_run" in p else {})}
                         for p in passages],
            "runs": [{"drop_run": int(r["drop_run"]), "start": round(float(r["start"]), 3), "end": round(float(r["end"]), 3),
                      "heat": float(r["heat"]), "level": round(float(r.get("level") or 0.0), 3), "main": bool(r.get("main"))}
                     for r in runs],
            "steps": {k: v for k, v in steps.items() if k in present}, "grid": len(grid), "bar_phase": phase,
            "drop_mode": drop_mode}
