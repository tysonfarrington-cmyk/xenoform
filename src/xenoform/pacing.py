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
        passages.append({"role": r["role"], "i0": i0, "start": 0.0 if not passages else grid[i0], "level": float(r.get("level") or 0.0)})
    for p, q in zip(passages, passages[1:] + [None]):
        p["i1"] = q["i0"] if q else len(grid)
        p["end"] = q["start"] if q else duration

    def zone_role(p: dict, k: int) -> str:
        if p["role"] == "drop" and drop is not None and grid[k] >= drop + DROP_HALF_BARS * 4 * period - 1e-6:
            return "drop_late"
        return p["role"]

    def cut(steps: dict) -> list[tuple[int, str, bool]]:
        """(grid index, role, starts a passage) for every shot."""
        out: list[tuple[int, str, bool]] = []
        for p in passages:
            k, first = p["i0"], True
            end = p["i1"]
            while k < end and grid[k] < duration - 0.3:
                role = zone_role(p, k)
                out.append((k, role, first))
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
        for _ in range(96):
            cands = [r for r in present if steps.get(r, 0) > MIN_BEATS]
            if not cands:
                break
            r = max(cands, key=lambda x: (PRIORITY.get(x, 1.0) - math.log2(max(1, base[x]) / steps[x]), PRIORITY.get(x, 1.0)))
            trial = dict(steps)
            trial[r] = max(MIN_BEATS, trial[r] // 2)
            more = cut(trial)
            if len(more) > min(hard, int(target) + max(1, int(target) // 10)):
                break
            steps, cuts = trial, more
            if len(cuts) >= int(target):
                break
    times = [grid[k] if n else 0.0 for n, (k, _, _) in enumerate(cuts)] + [duration]
    shots = []
    for n, ((k, role, starts), b) in enumerate(zip(cuts, times[1:])):
        a = times[n]
        seconds = b - a
        if seconds < 0.3:
            continue
        render_s = dense._render_s(seconds, SPEED.get(role, 1.25))
        effects = []
        on_beat = abs(grid[k] - a) < 1e-3
        if drop is not None and abs(a - drop) < 1e-3:
            effects += [{"type": "punch", "t": a, "strength": 1.0}, {"type": "stutter", "t": a, "frames": 2, "repeat": 4}]
        elif role in ("drop", "drop_late", "build") and on_beat:
            effects.append({"type": "punch", "t": a, "strength": 0.6 if role != "build" else 0.4})
        shot = {"start": round(a, 4), "end": round(b, 4), "render_s": render_s, "speed": round(render_s / seconds, 3),
                "effects": effects, "section": role}
        if starts and n > 0:
            if drop is not None and abs(a - drop) < 1e-3:
                kind = "drop"
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
            "passages": [{"role": p["role"], "start": round(p["start"], 3), "end": round(p["end"], 3)} for p in passages],
            "steps": {k: v for k, v in steps.items() if k in present}, "grid": len(grid), "bar_phase": phase}
