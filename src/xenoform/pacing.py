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
# Breathe (plan section 3, the montage's numbers): a bar a shot almost everywhere (the montage played 9 to 10 morphs per 8
# bars in every passage but the intro); what breathes is the timing, the effects, the chaos and the rests, not the cut
BREATHE = {"intro": 4, "calm": 4, "sustain": 4, "build": 4, "release": 4, "drop": 4, "drop_late": 4, "outro": 8}
BREATHE_FIRST = 2          # the intro's first shot is this many of its steps (two bars)
BUILD_END_BARS = 2         # Breathe: a build's last two bars cut on the half bar
REST_BEATS = 4             # the arrived object held this long at the intro's last shot and a calm passage's end
REST_MAX = 8               # a rest is never longer
REST_ROLES = ("intro", "calm", "sustain", "release")  # never in a drop
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
# the drop treatment (plan section 3): what every drop run gets, scaled by its heat
ENTRY_BARS = 2      # a hot run's first bars cut on the half bar (the only 2-beat shots a run has)
ENTRY_HEAT = 0.8    # ...from this heat
RAMP_BARS = 4       # the bars before a run that ramp into it: shots halved, Intensity up, dither in, a longer foreshadow
EVENT_BARS = 8      # a long run plants an event (a style change or a boundary kind) every this many bars
HIT_SNAP_S = 0.09   # a drum hit this close to a beat makes it a ramp's cut (stem_react's drum_strong)


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


def given_roles(sections: list[dict]) -> bool:
    """True when the sections already carry the song's own roles (a Length window cut from them): not refined again."""
    return bool(sections) and all(str(s.get("role") or "") for s in sections)


def song_roles(features: dict, drop: float | None = None) -> list[dict]:
    """The whole song's story roles as ``song_plan`` derives them (the passages, refined for the drops, the run that
    holds ``drop`` split there), for a Length window to keep: cut to the window (``ui._window_features``) they say what
    the song is doing there, where roles judged inside 30 s would call its loudest stretch a build, its first an intro
    and its last an outro. ``[]`` when the song has fewer than two sections."""
    from xenoform import dense

    duration = float(features.get("duration") or 0.0)
    sections = dense._analysis_sections(features)
    if duration <= 0 or len(sections) < 2:
        return []
    grid = grid_for(list(features.get("beats") or []), duration, features.get("tempo"))
    period = _median_gap(grid) or 0.5
    rows = dense._story_roles(sections, duration, min_len=max(6.0, 8 * period))
    return split_at_drop(refine_roles(rows, sections, period=period), drop, period)


# ------------------------------------------------------------------------------------------------ the plan


def _role_steps(table: dict, scale: float = 1.0) -> dict:
    return {k: max(MIN_BEATS, int(round(v * scale))) for k, v in table.items()}


def song_plan(duration: float, beats: list, sections: list[dict], drop: float | None = None, *,
              max_shots: int | None = None, target: int | None = None, breathe: bool = False,
              drop_mode: str = DROP_MODE_DEFAULT, pace: str = "viscous", tempo: float | None = None,
              hits: list | None = None) -> dict:
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
        rows = split_at_drop(rows if given_roles(sections) else refine_roles(rows, sections, period=period), drop, period)
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

    for pi, p in enumerate(passages):  # the passages that ramp into a drop run (the drop treatment)
        p["into_run"] = bool(per_run and pi + 1 < len(passages) and "drop_run" in passages[pi + 1] and "drop_run" not in p)
    hit_times = sorted(float(h) for h in hits or [])
    squeeze = {"on": False}  # a cap under the passages' own count: the half-bar parts give their cuts back

    def zone(p: dict, k: int) -> tuple[str, str]:
        """(role, part). The drop treatment's parts: "entry", a hot run's first bars on the half bar; "ramp", the bars
        before a run, on the half bar. Breathe's: "end", a build's last bars on the half bar."""
        role = zone_role(p, k)
        if squeeze["on"]:
            return role, ""
        if per_run and "drop_run" in p and p["heat"] >= ENTRY_HEAT and k < p["i0"] + ENTRY_BARS * 4 and role == "drop":
            return role, "entry"
        if p["into_run"] and k >= p["i1"] - RAMP_BARS * 4:
            return role, "ramp"
        if breathe and role == "build" and k >= p["i1"] - BUILD_END_BARS * 4:
            return role, "end"
        return role, ""

    def on_hit(j: int) -> bool:
        if not hit_times or not 0 <= j < len(grid):
            return False
        t = grid[j]
        lo, hi = 0, len(hit_times)
        while lo < hi:
            mid = (lo + hi) // 2
            if hit_times[mid] < t:
                lo = mid + 1
            else:
                hi = mid
        return any(abs(hit_times[q] - t) <= HIT_SNAP_S for q in (lo - 1, lo) if 0 <= q < len(hit_times))

    def rest_of(pi: int, p: dict) -> int:
        """Breathe: the beats the passage's last shot holds its arrived object (the intro's last shot, a calm passage's
        end), never in a drop and never where the build ramps into a drop run."""
        if not breathe or p["role"] not in REST_ROLES:
            return 0
        q = passages[pi + 1] if pi + 1 < len(passages) else None
        if per_run and q is not None and "drop_run" in q:
            return 0
        return REST_BEATS if p["i1"] - p["i0"] >= REST_BEATS + 4 else 0  # a bar of morph before the rest, at least

    def cut(steps: dict) -> list[tuple[int, str, bool, int, int]]:
        """(grid index, role, starts a passage, passage index, rest beats) for every shot."""
        out: list[tuple[int, str, bool, int, int]] = []
        for pi, p in enumerate(passages):
            rest = rest_of(pi, p)
            k, first = p["i0"], True
            end = p["i1"] - rest
            mine: list[list] = []
            while k < end and grid[k] < duration - 0.3:
                role, part = zone(p, k)
                mine.append([k, role, first, pi, 0])
                step = steps[role]
                if part in ("end", "entry", "ramp"):  # half the passage's step, never under two beats
                    step = max(MIN_BEATS, step // 2)
                elif breathe and role == "intro" and first:
                    step *= BREATHE_FIRST  # the intro opens on one long shot
                nxt = k + step
                # land the next cut on a bar line (the montage cut on beat 1); a drop run counts its bars from its own
                # first beat, pinned where the drop hits
                if step % 4 == 0 and (nxt - phase) % 4 and not (per_run and "drop_run" in p):
                    bar = nxt - ((nxt - phase) % 4)
                    nxt = bar if bar >= k + MIN_BEATS else bar + 4
                if part == "ramp" and hit_times and not on_hit(nxt):
                    # a ramp cuts on the drum's strong hits where the stems have them (stem_react drum_strong)
                    near = [j for j in (nxt - 1, nxt + 1) if k + MIN_BEATS <= j < end and on_hit(j)]
                    if near:
                        nxt = near[0]
                # a change of zone inside the passage (the drop's late bars, a build's last ones) starts on its own beat,
                # unless that would leave a sliver of a shot before it
                change = next((j for j in range(k + 1, min(nxt, end)) if zone(p, j) != (role, part)), None)
                if change is not None and change - k >= MIN_BEATS:
                    nxt = change
                # a sliver at the passage end folds into the shot before it (before a rest, the morph keeps a bar)
                if nxt < end and end - nxt < (4 if rest else MIN_BEATS):
                    nxt = end
                k, first = nxt, False
            if mine and rest:
                mine[-1][4] = rest  # the last shot runs on over the rest
            out.extend(tuple(x) for x in mine)
        return out

    table = dict(BREATHE) if breathe else table
    steps = _role_steps(table)
    present = sorted({zone_role(p, k) for p in passages for k in range(p["i0"], max(p["i0"] + 1, p["i1"]))
                      if k < len(grid)})
    if len(cut({r: MAX_BEATS for r in steps})) > limit:
        squeeze["on"] = True  # a cap under what the passages and the treatment's parts need: the parts give way first
    cuts = cut(steps)
    base = dict(steps)
    for _ in range(96):  # the budget, spent by role: the calm passages give up morphs first
        if len(cuts) <= limit:
            break
        cands = [r for r in present if steps.get(r, 0) < MAX_BEATS]
        if not cands:
            if not squeeze["on"]:  # still over: the half-bar parts (entries, ramps, build ends) give their cuts back
                squeeze["on"] = True
                cuts = cut(steps)
                continue
            break
        r = min(cands, key=lambda x: (PRIORITY.get(x, 1.0) + math.log2(steps[x] / max(1, base[x])), PRIORITY.get(x, 1.0)))
        steps[r] *= 2
        cuts = cut(steps)
    # a doubling halves a whole role's shots at once, so the loop can land well under the budget (a whole Glitch Out on
    # Draft: 45 shots of the 60 it may have): give back what still fits, the role that wants it most first
    for _ in range(96):
        if len(cuts) >= limit:
            break
        back = sorted((r for r in present if steps.get(r, 0) > base.get(r, 0)),
                      key=lambda x: (PRIORITY.get(x, 1.0) - math.log2(steps[x] / max(1, base[x])), PRIORITY.get(x, 1.0)),
                      reverse=True)
        given = False
        for r in back:
            trial = dict(steps)
            trial[r] = max(base[r], trial[r] // 2)
            more = cut(trial)
            if len(cuts) < len(more) <= limit:
                steps, cuts, given = trial, more, True
                break
        if not given:
            break
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
    # the end of the song (or of a Length window, cut where the window stops) leaves no sliver under two beats: the
    # last cut folds into the shot before it (a 0.9 s last shot on the 1:45 window read as a flash cut)
    while len(cuts) > 1 and duration - grid[cuts[-1][0]] < MIN_BEATS * period - 1e-6:
        cuts = cuts[:-1]
    times = [grid[k] if n else 0.0 for n, (k, *_rest) in enumerate(cuts)] + [duration]
    shots = []
    for n, ((k, role, starts, pi, rest), b) in enumerate(zip(cuts, times[1:])):
        a = times[n]
        seconds = b - a
        if seconds < 0.3:
            continue
        p = passages[pi]
        rest_s = 0.0
        if rest:
            j = p["i1"] - rest
            rest_s = b - grid[j] if 0 <= j < len(grid) and grid[j] > a else 0.0
            if seconds - rest_s < MIN_BEATS * period * 0.9:  # no room for the morph: no rest
                rest, rest_s = 0, 0.0
        render_s = dense._render_s(seconds, SPEED.get(role, 1.25))
        effects = []
        on_beat = abs(grid[k] - a) < 1e-3
        entry = per_run and starts and "drop_run" in p  # a drop run's first beat: its event
        part = zone(p, k)[1]
        ramp = None
        if part == "ramp":  # how far into the four bars before the run (0 at their start)
            r0 = p["i1"] - RAMP_BARS * 4
            ramp = round(max(0.0, min(0.999, (k - r0) / float(RAMP_BARS * 4))), 3)
        if entry:  # the punch and the stutter on every run's first beat, as hard as the run is hot
            heat = float(p["heat"])
            effects.append({"type": "punch", "t": a, "strength": round(1.0 if heat >= ENTRY_HEAT else 0.6 + 0.4 * heat, 3)})
            if heat >= 0.5:
                effects.append({"type": "stutter", "t": a, "frames": 2, "repeat": 4})
        elif drop is not None and abs(a - drop) < 1e-3:
            effects += [{"type": "punch", "t": a, "strength": 1.0}, {"type": "stutter", "t": a, "frames": 2, "repeat": 4}]
        elif ramp is not None and on_beat:  # the ramp hits harder as it nears the drop
            effects.append({"type": "punch", "t": a, "strength": round(0.4 + 0.4 * ramp, 3)})
        elif role in ("drop", "drop_late", "build") and on_beat:
            effects.append({"type": "punch", "t": a, "strength": 0.6 if role != "build" else 0.4})
        shot = {"start": round(a, 4), "end": round(b, 4), "render_s": render_s, "speed": round(render_s / seconds, 3),
                "effects": effects, "section": role, "passage": pi}
        if "drop_run" in p:
            shot.update({"drop_run": p["drop_run"], "heat": p["heat"]})
        if ramp is not None:
            shot["ramp"] = ramp
        if entry:
            shot["event"] = "drop"
        elif per_run and "drop_run" in p:  # a long run does not go flat: an event every EVENT_BARS bars of it
            bars = (a - p["start"]) / (4 * period)
            prev_bars = (times[n - 1] - p["start"]) / (4 * period) if n > 0 and cuts[n - 1][3] == pi else -1.0
            mark = math.floor(bars / EVENT_BARS + 1e-6)
            if mark >= 1 and math.floor(prev_bars / EVENT_BARS + 1e-6) < mark:
                shot["event"] = "style" if mark % 2 else "kind"
        if rest:  # Breathe: the morph plays over the first part, then the arrived object dwells (pacing.rest_indices)
            shot.update({"rest": int(rest), "rest_s": round(rest_s, 4)})
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
            "drop_mode": drop_mode, "breathe": bool(breathe), "period": round(period, 4)}


# ------------------------------------------------------------------------------------------------ the profile
#
# One table drives Breathe and the drops (plan section 3; montage_rules.md section 5, what survived eleven rounds of
# Tys's notes): a passage's timing, morph style, its one effect, the Look, a Chaos cap, its Intensity, the share of its
# handoffs that take a boundary kind and its flash budget. Written into the shots as fields the timeline already reads
# (``timing``, ``fx_names``, ``dance_fx``, ``fx_intensity``, ``chaos``), after the plan and before the timeline's own
# overrides, by ``shape``, which ``dense.run_simple`` and ``dense.recut_from_cache`` both call: a re-cut changes Breathe
# and the Drops with no GPU wherever the shot lengths stay (the morph styles are rendered, so they wait for a Make).

FLASH_LOOKS = ("cyan-flash", "negative-rush")   # flash looks: none before the first drop (the montage's F4)
CALM_LOOK = "cool-echo"                          # the house VJ look, what a flash look stands down to
DROP_CHAOS = 0.45                                # a drop's Chaos cap; a run's heat lifts the knob toward it
PROFILE: dict[str, dict] = {
    # role: timing, styles in turn, its one effect, Chaos cap, Intensity (the knob's 0.5 maps to it), boundary kinds,
    # flash frames per 8 bars the tame lets through
    "intro": {"timing": "smooth", "styles": ("bloom", "melt"), "effect": None, "chaos": 0.15, "intensity": 0.5,
              "kinds": False, "flash": 0},
    "calm": {"timing": "beat", "styles": ("melt", "bloom"), "effect": "third", "chaos": 0.4, "intensity": 0.8,
             "kinds": True, "flash": 16},
    "sustain": {"timing": "beat", "styles": ("melt", "bloom"), "effect": "third", "chaos": 0.4, "intensity": 0.8,
                "kinds": True, "flash": 16},
    "build": {"timing": "beat", "styles": ("fold", "bloom"), "effect": "dither-end", "chaos": 0.4, "intensity": 0.6,
              "kinds": False, "flash": 24},
    "drop": {"timing": "snap", "styles": ("shatter", "spin", "bloom"), "effect": "dither-feedback", "chaos": DROP_CHAOS,
             "intensity": 1.0, "kinds": True, "flash": 40},
    "drop_late": {"timing": "beat", "styles": ("melt", "spin"), "effect": "slitscan", "chaos": 0.4, "intensity": 0.9,
                  "kinds": True, "flash": 40},
    "release": {"timing": "beat", "styles": ("melt",), "effect": "dither", "chaos": 0.4, "intensity": 0.9,
                "kinds": True, "flash": 40},
    "outro": {"timing": "smooth", "styles": ("melt",), "effect": None, "chaos": 0.4, "intensity": 1.0, "kinds": False,
              "flash": 0},
}
BUILD_TOP = 1.0          # a build's Intensity ramps to this by its end
# Breathe holds a morph style for a look of whole bars (montage_rules.md 5.4: "a look is a bundle ... held for whole
# bars", the intro's 4.4 to 6.2 bars, a groove's 1 to 4, a drop's median of two, a breakdown's 2 to 3, the outro one
# look; about 4 looks a minute in the intro and the outro, 10 to 11 in the grooves, the builds and the drops): the bars
# a look lasts by role, counted from the passage's start (0: the whole passage is one look)
LOOK_BARS = {"intro": 5, "calm": 2, "sustain": 2, "build": 2, "release": 2, "drop": 2, "drop_late": 2, "outro": 0}
DITHER_BARS = 2          # a drop's first bars hit with dither (the ramp's last two lead in); feedback trails the rest
THIRD_EFFECTS = ("slitscan", "dither")  # one calm passage in three takes one of these, in turn


def paced_shots(shots: list[dict]) -> bool:
    """True when the shots came from the pacing engine (they carry their passage)."""
    return any(s.get("passage") is not None for s in shots or [])


def passage_of(shots: list[dict]) -> list[int]:
    """Each shot's passage: the plan's own, else a run of one section (a record from before the pacing engine)."""
    out: list[int] = []
    for i, s in enumerate(shots):
        if s.get("passage") is not None:
            out.append(int(s["passage"]))
        elif i and s.get("section") == shots[i - 1].get("section") and not s.get("boundary"):
            out.append(out[-1])
        else:
            out.append((out[-1] + 1) if out else 0)
    return out


def _heat(s: dict) -> float:
    if s.get("heat") is not None:
        return float(s["heat"])
    return 1.0 if str(s.get("section") or "") == "drop" else 0.0  # an older story plan: its one drop is the main one


def _knob(m: dict, key: str, default: float) -> float:
    try:
        return max(0.0, min(1.0, float((m or {}).get(key, default))))
    except (TypeError, ValueError):
        return default


CALM_KNOB = 0.15  # Chaos at or under this is a calm cut by choice (boundary_fx.ON_CHAOS): no lift, the drops included


def shot_chaos(s: dict, chaos: float, breathe: bool, drops: bool) -> float:
    """The Chaos a shot runs at: the knob, capped by its passage under Breathe, and in a drop run lifted toward the drop's
    cap by the run's heat (the drop is the most active part; never past the cap unless the knob already is, and not
    at all when the knob asks for a calm cut)."""
    role = str(s.get("section") or "")
    c = float(chaos)
    if breathe and role in PROFILE:
        c = min(c, PROFILE[role]["chaos"])
    if drops and role in ("drop", "drop_late") and float(chaos) > CALM_KNOB:
        cap = PROFILE[role]["chaos"] if breathe else DROP_CHAOS
        if c < cap:
            c = c + (cap - c) * _heat(s)
    return round(max(0.0, min(1.0, c)), 3)


def shot_intensity(s: dict, intensity: float, breathe: bool, drops: bool, pos: float = 0.0) -> float:
    """A shot's beat-FX intensity (``fx_intensity``): Breathe maps the knob's 0.5 to its passage's Intensity (a build
    ramping from its own to ``BUILD_TOP`` by ``pos``, 0..1 through the passage); without Breathe it is the knob's
    (x1.6) and a drop run lifts it toward full by its heat."""
    role = str(s.get("section") or "")
    if breathe and role in PROFILE:
        base = PROFILE[role]["intensity"]
        if role == "build":
            base = base + (BUILD_TOP - base) * max(0.0, min(1.0, pos))
        fx = base * 2.0 * float(intensity)
    else:
        fx = 1.6 * float(intensity)
        if drops and role in ("drop", "drop_late"):
            fx = fx + (1.0 - min(1.0, fx)) * _heat(s)
    return round(max(0.0, min(1.0, fx)), 3)


def shape(shots: list[dict], macros: dict, *, breathe: bool, drop_mode: str, house: dict | None = None,
          look: str = "", look_auto: bool = True, effects: list | None = None, timing: str = "smooth",
          beats: list | None = None) -> dict:
    """Lay the profile over the cut's shots, in place (a deep copy of the plan's): the work ``dense.apply_macros`` did
    for the whole cut, a shot at a time (its Chaos and Intensity, the punches and stutters by its Chaos, its wobble),
    then Breathe's per-passage timing (``timing`` {"mode"}: ``morph_timing.plan`` keeps it where the timeline says
    nothing), its one effect (``fx_names``) and, with the Look on Auto, no flash look before the first drop
    (``dance_fx``). The cut's own Timing and Effects win when they are set. Returns what it did, for the record."""
    m = macros or {}
    chaos, intensity = _knob(m, "chaos", 0.3), _knob(m, "intensity", 0.5)
    drops = drop_mode in ("auto", "max")
    wob_off = bool(house and ((house.get("look") or {}).get("character_wobble") is False))
    period = _median_gap(sorted(float(b) for b in beats or [])) if beats and len(beats) > 2 else _period_of(shots)
    passages = passage_of(shots)
    starts: dict[int, float] = {}
    ends: dict[int, float] = {}
    for s, p in zip(shots, passages):
        starts.setdefault(p, float(s.get("start") or 0.0))
        ends[p] = float(s.get("end") or 0.0)
    first_drop = min((float(s.get("start") or 0.0) for s in shots if s.get("section") in ("drop", "drop_late")), default=None)
    user_effects = [e for e in (effects or []) if e != "smear"]
    third = {}
    calm_seen = 0
    for p in sorted(set(passages)):
        role = next((str(s.get("section") or "") for s, q in zip(shots, passages) if q == p), "")
        if role in ("calm", "sustain"):  # the second calm passage of every three takes one, the first stays plain
            third[p] = THIRD_EFFECTS[(calm_seen // 3) % len(THIRD_EFFECTS)] if calm_seen % 3 == 1 else None
            calm_seen += 1
    order = {p: k for k, p in enumerate(sorted(set(passages)))}
    counts: dict[str, dict] = {"timing": {}, "effects": {}, "looks": 0}
    for i, (s, p) in enumerate(zip(shots, passages)):
        role = str(s.get("section") or "")
        prof = PROFILE.get(role) if breathe else None
        if not breathe:  # a rest is Breathe's: without it the shot plays its morph over its whole length
            s.pop("rest", None)
            s.pop("rest_s", None)
        span = max(1e-6, ends[p] - starts[p])
        pos = (float(s.get("start") or 0.0) - starts[p]) / span
        c = shot_chaos(s, chaos, breathe, drops)
        s["fx_intensity"] = round(min(1.0, float(s.get("fx_intensity", 1.0)) * shot_intensity(s, intensity, breathe, drops, pos)), 3)
        s["chaos"] = c
        wob = 0.0 if wob_off else max(0.0, c - 0.4)
        if wob:
            s["wobble"] = round(max(float(s.get("wobble") or 0.0), wob), 3)
        kept = []
        for fx in s.get("effects") or []:  # the knob's rules (apply_macros), at this shot's Chaos
            kind = fx.get("type")
            if kind == "punch":
                kept.append({**fx, "strength": round(min(1.0, float(fx.get("strength", 0.5)) * (0.2 + 1.4 * c)), 3)})
            elif kind in ("stutter", "hold", "skip", "reverse"):
                if c < 0.2:
                    continue
                if kind == "stutter" and c > 0.6:
                    fx = {**fx, "repeat": min(8, int(fx.get("repeat", 3)) + (4 if c > 0.85 else 2))}
                kept.append(fx)
            else:
                kept.append(fx)
        s["effects"] = kept
        if prof is not None:
            if timing == "smooth":  # the cut's Timing left on its default: the passage times its morphs
                mode = prof["timing"]
                if role == "drop" and _heat(s) < 0.5:
                    mode = "beat"
                if mode != "smooth":
                    s["timing"] = {"mode": mode}
                counts["timing"][mode] = counts["timing"].get(mode, 0) + 1
            if user_effects:  # the cut's own effects, one at a time, a passage each in turn
                pick = user_effects[order[p] % len(user_effects)]
            else:
                rule = prof["effect"]
                if rule == "third":
                    pick = third.get(p)
                elif rule == "dither-feedback":  # a drop's first 4 bars hit with dither, the rest trail feedback
                    pick = "dither" if pos * span < DITHER_BARS * 4 * period - 1e-6 else "feedback"
                elif rule == "dither-end":  # a build dithers as it ends (its last two bars)
                    pick = "dither" if (1.0 - pos) * span <= BUILD_END_BARS * 4 * period + 1e-6 else None
                else:
                    pick = rule
            s["fx_names"] = [pick] if pick else []
            if pick:
                counts["effects"][pick] = counts["effects"].get(pick, 0) + 1
            if look_auto and (first_drop is None or float(s.get("start") or 0.0) < first_drop - 1e-6):
                calm = _calm_look(look, i, house)
                if calm:
                    s["dance_fx"] = calm
                    counts["looks"] += 1
            if role not in ("drop", "drop_late") and _fit_rest(s, period):
                counts["long_rests"] = counts.get("long_rests", 0) + 1
        if drops:  # the drop treatment, over the profile: the entries and the ramps into them
            _treat(s, timing=timing, user_effects=user_effects, intensity=intensity, breathe=prof is not None, counts=counts,
                   period=period)
    return counts


def _treat(s: dict, *, timing: str, user_effects: list, intensity: float, breathe: bool, counts: dict,
           period: float = 0.5) -> None:
    """The drop treatment on one shot, in place (plan section 3). A run's first shot snaps (its punch and stutter are
    the plan's). The four bars before a run ramp: their beat-FX Intensity rises to the knob's full by the drop, dither
    comes in (unless the cut chose its own effects), and under Breathe the last bar snaps."""
    if s.get("event") == "drop":
        if timing == "smooth":
            s["timing"] = {"mode": "snap"}
            counts["timing"]["snap"] = counts["timing"].get("snap", 0) + 1
        counts["entries"] = counts.get("entries", 0) + 1
    ramp = s.get("ramp")
    if ramp is None:
        return
    r = max(0.0, min(1.0, float(ramp)))
    # how far up the ramp the shot ends (its last frames meet the drop at 1)
    r_end = min(1.0, r + float(s.get("seconds") or 0.0) / max(1e-3, RAMP_BARS * 4 * float(period)))
    r_end = 1.0 if r_end > 0.95 else r_end  # the shot that meets the drop
    top = min(1.0, 2.0 * float(intensity))  # the knob's full: 1 at its default, none at 0
    fx = float(s.get("fx_intensity") or 0.0)
    if fx < top:
        s["fx_intensity"] = round(fx + (top - fx) * r_end, 3)
    if not user_effects and r >= 0.5:  # dither comes in over the ramp's last two bars, into the drop's first two
        s["fx_names"] = ["dither"]
    if breathe and timing == "smooth" and r >= 0.75:
        s["timing"] = {"mode": "snap"}
    counts["ramp"] = counts.get("ramp", 0) + 1


MIN_PLAY = 0.6   # Breathe never plays a morph slower than this; a longer shot is the morph and then a rest
CLIP_MAX_S = 5.0  # a morph clip is at most 5 s (cloud_morph._local_clips)


def _fit_rest(s: dict, period: float) -> bool:
    """Breathe: a shot longer than its morph can fill at ``MIN_PLAY`` plays the morph at that speed and rests on the
    object for the rest (at most ``REST_MAX`` beats; past that the morph slows, as before). True when it set one."""
    try:
        clip = min(CLIP_MAX_S, float(s.get("render_s") or 0.0))
        seconds = float(s.get("seconds") or (float(s.get("end") or 0.0) - float(s.get("start") or 0.0)))
    except (TypeError, ValueError):
        return False
    if clip <= 0 or seconds <= 0:
        return False
    need = seconds - clip / MIN_PLAY
    have = float(s.get("rest_s") or 0.0)
    if need <= have + 1e-3:
        return False
    rest_s = min(need, REST_MAX * float(period))
    s["rest_s"] = round(rest_s, 4)
    s["rest"] = max(1, int(round(rest_s / float(period))))
    return True


def _period_of(shots: list[dict]) -> float:
    """The beat period a plan's shots were cut on (their rests say it), else 120 bpm's."""
    for s in shots:
        if s.get("rest") and s.get("rest_s"):
            return float(s["rest_s"]) / float(s["rest"])
    return 0.5


def _calm_look(look: str, index: int, house: dict | None) -> str:
    """The look a shot before the first drop takes instead of a flash look, or "" to keep the cut's: a flash preset
    stands down to the house VJ look, and the house look's own opening role (the cyan flash on a cut's first shot) to
    its VJ preset."""
    look = str(look or "")
    if look in FLASH_LOOKS:
        return CALM_LOOK
    if look == "house" and index == 0:
        vj = str((((house or {}).get("dance_fx") or {}).get("vj") or {}).get("preset") or CALM_LOOK)
        return vj if vj not in FLASH_LOOKS else CALM_LOOK
    return ""


def styles(shots: list[dict], state: dict, drop: float | None = None, *, period: float | None = None) -> list[str] | None:
    """The morph style a shot for a paced cut with the Morph row on Auto (None: ``morph_style.for_cut`` decides, as
    before). Breathe takes its passage's styles in turn, a look at a time (``LOOK_BARS``: two bars in the grooves, the
    builds and the drops, the intro's five, the outro one look; ``period`` the beat the plan was cut on): bloom and melt
    in the intro, melt and bloom in the grooves, fold and bloom in a build, shatter, spin and bloom in a drop (from the
    style its first beat opened on), melt in the outro. Without it the Auto rules stand."""
    from xenoform import morph_style as MS

    state = state or {}
    given = state.get("morph_styles")
    if isinstance(given, list) and given and len(given) == len(shots):
        return None
    if MS.normal(state.get("morph_style") or "auto") != "auto" or not paced_shots(shots):
        return None
    breathe = breathe_of(state)
    drops = drop_mode_of(state) in ("auto", "max")
    if not breathe and not drops:
        return None
    # every run opens on a Shatter, a Spin when the run before it shattered (the main run always shatters)
    entries = [i for i, s in enumerate(shots) if s.get("event") == "drop"] if drops else []
    main = next((k for k, i in enumerate(entries) if drop is not None and abs(float(shots[i].get("start") or 0.0) - float(drop)) < 0.06), 0)
    opens = {i: ("shatter" if (k - main) % 2 == 0 else "spin") for k, i in enumerate(entries)}
    if breathe:
        passages = passage_of(shots)
        beat = float(period) if period else _period_of(shots)
        starts: dict[int, float] = {}
        offset: dict[int, int] = {}
        for i, (s, p) in enumerate(zip(shots, passages)):
            starts.setdefault(p, float(s.get("start") or 0.0))
            cycle = (PROFILE.get(str(s.get("section") or "")) or {}).get("styles") or ("melt",)
            if i in opens and p not in offset and opens[i] in cycle:  # a drop's looks turn on from the style it opened on
                offset[p] = cycle.index(opens[i])
        out: list[str] = []
        for s, p in zip(shots, passages):
            role = str(s.get("section") or "")
            cycle = (PROFILE.get(role) or {}).get("styles") or ("melt",)
            bars = LOOK_BARS.get(role, 2)
            k = int((float(s.get("start") or 0.0) - starts[p] + 1e-3) // (bars * 4 * beat)) if bars and beat > 0 else 0
            out.append(cycle[(k + offset.get(p, 0)) % len(cycle)])
    else:
        m = state.get("macros") if isinstance(state.get("macros"), dict) else {}
        out = MS.auto(shots, drop, _knob(m, "chaos", 0.3))
    if drops:
        for i, st in opens.items():
            out[i] = st
        for i, s in enumerate(shots):  # a long run's planted style event: a style its neighbours do not have
            if s.get("event") == "style":
                near = {out[i - 1] if i else "", out[i + 1] if i + 1 < len(out) else "", out[i]}
                out[i] = next((st for st in ("spin", "bloom", "fold", "shatter") if st not in near), "spin")
    return out


def fresh_at_drops(stills: list[dict], shots: list[dict], assign: list | None = None) -> tuple[list[dict], int]:
    """A new look on every drop run's first beat (7 of the montage's 9 drops opened on a new look): the still a run's
    first shot lands on comes from an object family the cut has not just shown; a later still of a fresh family swaps
    into its slot, so no still repeats, and pinned stills, your images and scenes stay where they are. Returns the
    stills and how many moved."""
    from xenoform import stills as S

    out = list(stills or [])

    def fam(r: dict) -> str:
        return str(r.get("family") or S.family_of(str(r.get("noun") or "")))

    landing = []
    for i, s in enumerate(shots or []):
        if s.get("event") != "drop":
            continue
        m = int(assign[i]) if assign and i < len(assign) else int(s.get("clip", i))
        landing.append(m + 1)
    locked = set(landing)
    moved = 0
    for k in landing:
        if not 0 < k < len(out):
            continue
        r = out[k]
        if r.get("pinned") or r.get("user") or str(r.get("kind") or "") == "scene" or not fam(r):
            continue
        seen = {fam(out[j]) for j in range(max(0, k - 3), k)}
        if fam(r) not in seen:
            continue
        j = next((j for j in range(k + 1, len(out)) if j not in locked and not out[j].get("pinned") and not out[j].get("user")
                  and str(out[j].get("kind") or "") != "scene" and fam(out[j]) and fam(out[j]) not in seen), None)
        if j is None:
            continue
        out[k], out[j] = out[j], out[k]
        moved += 1
    return out, moved


FLASH_BARS = 8   # the tame's window: flash frames per 8 bars (the montage measured them so)


def flash_rules(shots: list[dict], fps: int, beats: list | None = None) -> list[tuple | None]:
    """The flash tame's rule a frame (``deflash.Tame``), from the passage each composed frame sits in: ``(keep, budget,
    window)``, the share of a flash kept and the flash frames an 8-bar window may hold (the profile's ``flash``: none in
    the intro and the outro, 16 in the calm, a build rising from 24 to 40 as it ramps, 40 in the drops); a frame of a
    shot with no role gets the drops' cap."""
    from xenoform import deflash as DF

    b = sorted(float(x) for x in beats or [])
    period = _median_gap(b) if len(b) > 2 else 0.5
    window = max(1, int(round(FLASH_BARS * 4 * period * int(fps))))
    out: list[tuple | None] = []
    for s in shots:
        role = str(s.get("section") or "")
        budget = int((PROFILE.get(role) or PROFILE["drop"])["flash"])
        if role == "build" or s.get("ramp") is not None:
            budget = int(round(24 + 16 * float(s.get("ramp") or 0.0)))
        keep = DF.KEEP if budget > 0 else 0.0
        out.extend([(keep, budget, window)] * int(s.get("frames") or 0))
    return out


# ------------------------------------------------------------------------------------------------ the record


def clock(seconds: float) -> str:
    """1:59 for 119.8 s."""
    s = int(round(max(0.0, float(seconds))))
    return f"{s // 60}:{s % 60:02d}"


def summary_line(shots: list[dict], *, breathe: bool, song_start: float = 0.0, drop: float | None = None) -> str:
    """What the plan did, in a line for the Make's report: "3 drops, the main at 1:59; 6 passages; 4 rests" (song
    time: a Length cut counts from where it sits in the song; the main drop is the run that opens at ``drop``, the
    plan's)."""
    entries = [s for i, s in enumerate(shots) if str(s.get("boundary") or "") == "drop" or (
        s.get("drop_run") is not None and (i == 0 or shots[i - 1].get("drop_run") != s.get("drop_run")))]
    runs = {s.get("drop_run") for s in shots if s.get("drop_run") is not None}
    n = len(runs) or len(entries)
    main = None
    if drop is not None:
        main = next((s for s in entries if abs(float(s.get("start") or 0.0) - float(drop)) < 0.06), None)
    main = main or next((s for s in entries if float(s.get("heat") or 0.0) >= 1.0), None) or (entries[0] if entries else None)
    parts = []
    if n:
        parts.append(f"{n} drop{'s' if n != 1 else ''}, the main at {clock(song_start + float(main['start']))}" if main else
                     f"{n} drop{'s' if n != 1 else ''}")
    else:
        parts.append("no drop")
    parts.append(f"{len(set(passage_of(shots)))} passages")
    if breathe:
        rests = sum(1 for s in shots if s.get("rest"))
        parts.append(f"{rests} rest{'s' if rests != 1 else ''}")
    return "; ".join(parts)


def record(plan: dict, shots: list[dict], state: dict, window: dict | None = None) -> dict:
    """The record's ``pacing`` block: the shape the cut was made in, its passages and drop runs, the rests and the line
    the Make reported."""
    out = {"breathe": breathe_of(state), "drop_mode": drop_mode_of(state)}
    if not paced_shots(shots):
        return out
    start = float((window or {}).get("song_start") or 0.0)
    out.update({"passages": list(plan.get("passages") or []), "runs": list(plan.get("runs") or []),
                "rests": sum(1 for s in shots if s.get("rest")), "steps": dict(plan.get("steps") or {}),
                "line": summary_line(shots, breathe=out["breathe"], song_start=start, drop=plan.get("drop"))})
    return out
