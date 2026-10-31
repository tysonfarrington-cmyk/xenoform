"""The whole song as a music video: the plan (docs/MUSIC_VIDEO_PLAN.md section 7; docs/SONG.md).

What the montage did by hand on 29 Oct (``docs/demo/tools/montage.py``: 30 s window cuts of Glitch Out laid end to end
by song time, a look a stretch) becomes a Make. The song is cut into the pacing engine's own passages (``pacing.song_plan``
on the song's own analysis, the Shape row's Breathe and Drops over the whole song) and every passage is a window Make
of at most ``PASSAGE_MAX`` morphs on the chosen tier (a passage that holds more is split on a bar line), its budget the
profile table's: the beats a shot its role takes. The song's total is the sum of its passages. The per-Make caps (Draft's
60 on a four-minute song, ``dense.clip_plan``; Cloud's 16 a Make) guard one Make and do not cap the song; the body key
``song_morph_cap`` does, when it is a number ("auto", the default, is the profile's own count).

Every passage gets its own look, drawn by taste (``looks``):

- no vibe twice in the song (``taste.fresh_vibes``), the vibe you chose on the main drop (the moment the song is built
  on), the loved chains (``presets``) on the passages they fit (the opener on the intro, the finale on the outro, the
  calm ones on the grooves, the ones on the beat on the drops), the rest the featured vibes in their order, the quiet
  ones on the quiet passages and the loud ones on the drops and builds;
- the intro and the outro one long look each (one vibe, one family under full Breathe, a passage of their own);
- no object twice across passages, natural or iconic first (``objects``): the stills each window morphs through are
  picked here the way its Make picks them (``morph_pass.pick_stills`` under the taste file), each window leaving out the
  objects the windows before it took, and pinned slot by slot in its body, so the Make renders exactly them and a re-run
  asks the morph cache for the very same morphs.

A window Make plays its own stretch of the song plan (``KEY`` in its body: the shots in window time and its place in the
song: where the song's first drop is, whether it holds the opener, how many calm passages came before it), so the cut it
makes is the passage the whole-song plan made, the ramps into the drops, the bar lines and the looks included.

``plan`` is what the desk's estimate and the run use; ``estimate`` the morphs, the minutes on each tier and what Cloud
would cost. Nothing here renders.
"""
from __future__ import annotations

import copy
import math
from pathlib import Path

from xenoform import pacing

KEY = "song_passage"            # the body key a window Make carries: its stretch of the song plan and its place in the song
CAP_KEY = "song_morph_cap"      # the body key for the song's total: "auto" (the profile's own count) or a number of morphs
TITLE_KEY = "song_title"        # the title on the last hit: the hand-made video's "Xenoform" by default, "" for none
TITLE_DEFAULT = "Xenoform"
PASSAGE_MAX = 16                # morphs a window Make holds at most (cloud_final.MAX_MORPHS: one Cloud Make's cap)
TIERS = ("draft", "fast", "final", "cloud")
# Comfy Cloud credits a Cloud Final morph: 464 for 128 morphs and 135 for 37 measured on 29 Oct (3.6), about 6 for a
# single 3 s morph (docs/HANDOFF_29OCT.md); the plan's 400 to 650 for 110 morphs is the same range
CLOUD_CREDITS = (3.6, 6.0)
SEED_STEP = 1009                # a window's seed after the song's (batch.SEED_STEP: a fresh roll each)
WINDOW_FADE_S = 0.01            # the window's audio fades this little at its ends: no click, and the drop's hit stays whole
SCENE_ROLES = pacing.SCENE_ROLES
HOT_ROLES = ("build", "drop", "drop_late")
TITLE_TAIL_MIN = 3.0            # the title's hit leaves at least this much song after it
# what a vibe's tags say about it (vibes.json): the quiet ones take the quiet passages first, the loud ones the drops
QUIET_TAGS = {"organic", "glow", "water", "calm", "ink", "paper", "plant", "smoke", "figure", "natural", "plain", "noir",
              "clean", "stone", "still", "cold"}
LOUD_TAGS = {"neon", "metal", "chrome", "digital", "wireframe", "retro", "fire", "print", "graphic", "liquid", "abstract",
             "colour", "iridescent", "crystal", "wet", "gold"}
# the Make-body keys a window never carries: the Director desk's storyboard, the cut plans, the other modes' inputs, the
# Length of the desk (the window says its own) and the paid partner path
DROP_KEYS = ("scenes", "blocks", "customs", "cards", "cut_plan", "morph_styles", "own_clips", "morph_targets", "own_folder",
             "own_id", "performer_ref", "hero_id", "hero_path", "guide_id", "guide_path", "length_s", "length_start",
             "song_source", "layers", "stem_rows", "only_scenes", "simple_recipe", "recipe", CAP_KEY, "avoid_stills",
             "avoid_nouns", "chain_pins", "idea_reading")


class SongError(ValueError):
    """The song cannot be made whole (too short, no sections, a mode the maker does not take)."""


# ------------------------------------------------------------------------------------------------ the keys


def cap_of(state: dict | None) -> int | None:
    """``song_morph_cap`` as a number of morphs, or None for "auto" (the profile's own count)."""
    raw = (state or {}).get(CAP_KEY)
    if raw in (None, "", "auto", 0, "0"):
        return None
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return None


def window_cap(tier: str) -> int:
    """The most morphs one window Make holds on ``tier``: ``PASSAGE_MAX``, or the tier's own per-Make cap when it is
    lower (Final's 12, ``dense.MORPH_CAP``), so no window is merged down by the Make's own guard."""
    from xenoform import dense

    tier = str(tier or "draft").lower()
    own = dense.MORPH_CAP.get(tier, dense.MORPH_CAP["draft"])
    return max(1, min(PASSAGE_MAX, int(own)))


def tier_of(state: dict | None) -> str:
    tier = str((state or {}).get("quality_tier") or "draft").lower()
    return tier if tier in TIERS else "draft"


def title_of(state: dict | None) -> str:
    raw = (state or {}).get(TITLE_KEY)
    return TITLE_DEFAULT if raw is None else str(raw).strip()[:40]


def refuse(state: dict) -> str:
    """Why this body cannot be made as a whole song, or "" when it can."""
    from xenoform import stems_mode

    if str(state.get("morph_source") or "").strip().lower() == "clips":
        return "Whole song makes objects cuts: a clips cut is one Make (Length: Full song)."
    if stems_mode.wants(state):
        return "Whole song makes one picture: Stems mode layers its own cuts (Length: Full song)."
    if state.get("cut_plan"):
        return "A cut plan is one Make: clear it to make the whole song."
    return ""


def analysis(features: dict) -> dict:
    """The song's analysis as the plan reads it: length, beats, tempo, the analyser's sections."""
    from xenoform import dense

    return {"duration": float(features.get("duration") or 0.0),
            "beats": [float(b) for b in features.get("beats") or []],
            "tempo": features.get("tempo"),
            "sections": dense._analysis_sections(features)}


# ------------------------------------------------------------------------------------------------ the passages


def whole(features: dict, state: dict, drop: float | None) -> dict:
    """The whole song's plan, ``pacing.song_plan`` on its own analysis at the body's Shape, as one Make of the song would
    plan it but uncapped by the per-Make cap: the budget is the profile table's (``song_morph_cap`` caps it when set, the
    calm passages giving up morphs first), and the Speed knob scales it as it scales any Make. Adds ``grid_times``."""
    from xenoform import dense

    a = analysis(features)
    duration = a["duration"]
    if duration <= dense.LONG_SONG_S or len(a["sections"]) < 2:
        raise SongError(f"Whole song needs a song over {int(dense.LONG_SONG_S)} s with sections; this one is a clip: "
                        f"make it as one cut.")
    grid = pacing.grid_for(a["beats"], duration, a["tempo"])
    cap = cap_of(state)
    hard = cap or max(1, len(grid))  # auto: one shot a beat at most, so the profile's own steps stand
    env = dense.stem_env_for(state)  # the split stems' strong drum hits: a ramp into a drop cuts on them, as in a Make
    hits = list(env.get("drum_strong") or []) if env and not str(env.get("engine") or "").startswith("mix") else None
    kw = dict(breathe=pacing.breathe_amount(state), drop_mode=pacing.drop_mode_of(state), pace=dense.story_pace(state),
              tempo=a["tempo"], hits=hits)
    plan = pacing.song_plan(duration, a["beats"], a["sections"], drop, max_shots=hard, **kw)
    speed = dense.macros(state)["speed"]
    if abs(speed - 0.5) > 0.05:  # the Speed knob scales the song's own count, x0.6 at 0 and x1.4 at 1 (song_plan_for)
        target = max(1, int(round(len(plan["shots"]) * (0.6 + 0.8 * max(0.0, min(1.0, float(speed)))))))
        if target != len(plan["shots"]):
            plan = pacing.song_plan(duration, a["beats"], a["sections"], drop, max_shots=hard, target=target, **kw)
            plan["target"] = target
    plan["grid_times"] = grid
    plan["cap"] = cap
    return plan


def _passage_shots(plan: dict) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for i, s in enumerate(plan["shots"]):
        out.setdefault(int(s.get("passage") or 0), []).append(i)
    return out


def _on_bar(t: float, grid: list[float], phase: int) -> bool:
    if not grid:
        return True
    i = min(range(len(grid)), key=lambda j: abs(grid[j] - t))
    return abs(grid[i] - t) < 0.05 and (i - phase) % 4 == 0


def split(idx: list[int], shots: list[dict], cap: int, grid: list[float], phase: int) -> list[list[int]]:
    """A passage's shots (plan indices) as the fewest windows of at most ``cap``, each cut where a shot starts on a bar
    line nearest an even share (a shot is never cut in two)."""
    n = len(idx)
    k = max(1, math.ceil(n / max(1, cap)))
    if k == 1:
        return [list(idx)]
    cuts: list[int] = []
    lo = 0
    for j in range(1, k):
        want = round(n * j / k)
        first = max(lo + 1, n - cap * (k - j))
        last = min(n - 1, lo + cap)
        cands = list(range(first, last + 1)) or [min(n - 1, lo + cap)]
        best = min(cands, key=lambda c: (0 if _on_bar(float(shots[idx[c]]["start"]), grid, phase) else 1, abs(c - want)))
        cuts.append(best)
        lo = best
    bounds = [0] + cuts + [n]
    return [list(idx[a:b]) for a, b in zip(bounds, bounds[1:])]


def passages_of(plan: dict, tier: str) -> tuple[list[dict], list[dict]]:
    """The song's passages (role, span, heat, its morphs) and its windows: each passage as window Makes of at most
    ``window_cap(tier)`` morphs, in song order. A passage whose shots the plan folded away has no window."""
    shots = plan["shots"]
    grid = list(plan.get("grid_times") or [])
    phase = int(plan.get("bar_phase") or 0)
    cap = window_cap(tier)
    by = _passage_shots(plan)
    raw = list(plan.get("passages") or [])
    passages: list[dict] = []
    windows: list[dict] = []
    for pi, p in enumerate(raw):
        idx = by.get(pi) or []
        if not idx:
            continue
        start, end = float(shots[idx[0]]["start"]), float(shots[idx[-1]]["end"])
        row = {"index": len(passages), "plan_passage": pi, "role": str(p.get("role") or ""), "start": round(start, 4),
               "end": round(end, 4), "seconds": round(end - start, 3), "morphs": len(idx), "windows": []}
        for key in ("drop_run", "heat", "main"):
            if p.get(key) is not None:
                row[key] = p[key]
        parts = split(idx, shots, cap, grid, phase)
        for j, part in enumerate(parts):
            w0, w1 = float(shots[part[0]]["start"]), float(shots[part[-1]]["end"])
            row["windows"].append(len(windows))
            windows.append({"index": len(windows), "passage": row["index"], "part": j, "parts": len(parts), "role": row["role"],
                            "start": round(w0, 4), "end": round(w1, 4), "length_s": round(w1 - w0, 4),
                            "morphs": len(part), "shot_idx": part})
        passages.append(row)
    return passages, windows


def first_drop(plan: dict) -> float | None:
    """When the song's first drop starts (its first shot of a drop role, or the plan's drop), song time."""
    for s in plan["shots"]:
        if str(s.get("section") or "") in ("drop", "drop_late") or s.get("drop_run") is not None:
            return round(float(s["start"]), 4)
    return plan.get("drop")


def _entry_styles(plan: dict) -> dict[int, str]:
    """The style each drop run opens on in the song: a Shatter, a Spin when the run before it shattered, the main run
    always a Shatter (``pacing.styles``, counted over the whole song rather than a window)."""
    shots = plan["shots"]
    entries = [i for i, s in enumerate(shots) if s.get("event") == "drop"]
    drop = plan.get("drop")
    main = next((k for k, i in enumerate(entries) if drop is not None and abs(float(shots[i]["start"]) - float(drop)) < 0.06), 0)
    return {i: ("shatter" if (k - main) % 2 == 0 else "spin") for k, i in enumerate(entries)}


def window_plan(plan: dict, song: dict, w: dict) -> dict:
    """The window's stretch of the song plan in window time: ``pacing.song_plan``'s shape for one passage (the shots
    with their roles, heat, events, ramps and rests, its passage and run, the steps, the bar phase and the beat), the
    first shot without the boundary the assembly cuts on."""
    off = float(w["start"])
    length = float(w["length_s"])
    shots = []
    for n, i in enumerate(w["shot_idx"]):
        s = copy.deepcopy(plan["shots"][i])
        s["start"] = round(max(0.0, float(s["start"]) - off), 4)
        s["end"] = round(min(length, float(s["end"]) - off), 4)
        s["effects"] = [{**fx, "t": round(min(max(0.0, float(fx.get("t", 0.0)) - off), max(0.0, s["end"] - 0.01)), 4)}
                        for fx in s.get("effects") or []]
        if n == 0:
            s.pop("boundary", None)  # the cut into the passage is the assembly's, on the song's beat
            s["start"] = 0.0
        shots.append(s)
    if shots:
        shots[-1]["end"] = round(length, 4)
    p = song["passages"][w["passage"]]
    entry = {k: p[k] for k in ("drop_run", "heat", "main") if k in p}
    drop = plan.get("drop")
    inside = drop is not None and off - 1e-6 <= float(drop) < off + length - 1e-6
    return {"name": "story", "drop": round(float(drop) - off, 4) if inside else None, "shots": shots,
            "roles": [(w["role"], 0.0, round(length, 2))],
            "passages": [{"role": w["role"], "start": 0.0, "end": round(length, 3), **entry}],
            "runs": [{"drop_run": int(p["drop_run"]), "start": 0.0, "end": round(length, 3), "heat": float(p.get("heat") or 0.0),
                      "main": bool(p.get("main"))}] if "drop_run" in p else [],
            "steps": dict(plan.get("steps") or {}), "bar_phase": plan.get("bar_phase"), "period": plan.get("period"),
            "drop_mode": plan.get("drop_mode"), "breathe": plan.get("breathe"), "song": True}


def contexts(plan: dict, song: dict) -> list[dict]:
    """Each window's place in the song (the body's ``KEY`` without its plan): where it starts, where the song's first
    drop is, whether it holds the song's opener, the passage's span, how many calm passages and scenes of its role came
    before it, the style its drop run opens on and its turn in the effects."""
    entries = _entry_styles(plan)
    fd = first_drop(plan)
    calm_seen = 0
    role_seen: dict[str, int] = {}
    passage_ctx: dict[int, dict] = {}
    for p in song["passages"]:
        passage_ctx[p["index"]] = {"calm_seen": calm_seen, "role_seen": dict(role_seen)}
        if p["role"] in ("calm", "sustain"):
            calm_seen += 1
        if p["role"] in SCENE_ROLES:
            role_seen[p["role"]] = role_seen.get(p["role"], 0) + 1
    out = []
    for w in song["windows"]:
        p = song["passages"][w["passage"]]
        opens = next((entries[i] for i in w["shot_idx"] if i in entries), None)
        out.append({"index": w["index"], "of": len(song["windows"]), "passage": p["index"], "passages": len(song["passages"]),
                    "part": w["part"], "parts": w["parts"], "role": p["role"], "offset": float(w["start"]),
                    "length_s": float(w["length_s"]), "passage_start": float(p["start"]), "passage_end": float(p["end"]),
                    "first_drop": fd, "opener": w["index"] == 0, "turn": p["index"], "opens": opens,
                    **passage_ctx[p["index"]]})
    return out


# ------------------------------------------------------------------------------------------------ the looks


def _knob(raw: dict | None, key: str, default: float) -> float:
    try:
        return float((raw or {}).get(key, default))
    except (TypeError, ValueError):
        return default


def preset_fit(preset: dict, role: str, breathe: float) -> float:
    """How well a loved chain fits a passage of ``role`` (0: it does not): a calm chain (smooth, Chaos 0.2 or under) a
    calm passage, a chain on the beat or at Chaos 0.4 and over a build or a drop; its style one of the role's, its
    timing the role's; the opener only the intro, the finale only the outro."""
    text = " ".join(str(preset.get(k) or "") for k in ("name", "line", "note")).lower()
    timing = str(preset.get("morph_timing") or "smooth")
    chaos = _knob(preset.get("knobs"), "chaos", 0.3)
    calm = timing == "smooth" and chaos <= 0.2 + 1e-9
    hot = timing in ("beat", "snap") or chaos >= 0.4 - 1e-9
    finale = any(w in text for w in ("outro", "finale"))
    opener = any(w in text for w in ("opener", "opens glitch", "the opener"))
    if finale:
        return 4.0 + (1.0 if role == "outro" else 0.0) if role == "outro" else 0.0
    if opener and role not in ("intro", "calm", "sustain"):
        return 0.0
    score = 0.0
    if role in SCENE_ROLES and calm:
        score += 2.0
    elif role in HOT_ROLES and hot:
        score += 2.0
    else:
        return 0.0
    prof = pacing.profile_at(role, breathe) or pacing.PROFILE.get(role) or {}
    if str(preset.get("morph_style") or "") in (prof.get("styles") or ()):
        score += 1.0
    want = str(prof.get("timing") or "smooth")
    if (want == "smooth") == (timing == "smooth"):
        score += 0.5
    if opener and role == "intro":
        score += 3.0
    return score


def _importance(passages: list[dict]) -> list[int]:
    """The passages in the order their looks are drawn: the intro, the outro, the main drop, the other drop runs by
    heat, then the rest by length (the longest scene first)."""
    def key(p: dict) -> tuple:
        role = p["role"]
        if role == "intro" and p["index"] == 0:
            return (0, 0.0)
        if role == "outro" and p["index"] == len(passages) - 1:
            return (1, 0.0)
        if p.get("main"):
            return (2, 0.0)
        if p.get("drop_run") is not None:
            return (3, -float(p.get("heat") or 0.0), p["index"])
        return (4, -float(p["seconds"]), p["index"])
    return [p["index"] for p in sorted(passages, key=key)]


def _tags(row: dict) -> set[str]:
    return {str(t).lower() for t in row.get("tags") or []}


def affinity(row: dict, role: str) -> int:
    """A vibe's pull toward a passage, -1, 0 or 1: its quiet tags against its loud ones, for the scenes; the other way
    round for the builds and drops. Only the sign counts, so the featured order decides among the vibes that fit."""
    tags = _tags(row)
    quiet, loud = len(tags & QUIET_TAGS), len(tags & LOUD_TAGS)
    pull = quiet - loud if role in SCENE_ROLES else loud - quiet
    return (pull > 0) - (pull < 0)


def candidates(chosen: str) -> list[dict]:
    """The vibes a song may draw on, in order: the one chosen, then the featured ones in their order, then the rest that
    morph; under the taste file each once and the demoted ones out (``taste.fresh_vibes``)."""
    from xenoform import taste, vibes

    rows = [r for r in vibes.catalog() if r.get("morph", True)]
    by = {r["id"]: r for r in rows}
    order = ([chosen] if chosen in by else []) + [r["id"] for r in rows if r["id"] != chosen]
    order = taste.fresh_vibes(order, keep=1 if chosen in by else 0)
    seen: list[str] = []
    for v in order:
        if v not in seen:
            seen.append(v)
    return [by[v] for v in seen if v in by]


CAPACITY_MARGIN = 8  # objects a vibe keeps over a passage's chain for the song's other passages to take first


def capacity(vibe: str) -> int:
    """How many different objects a vibe's library holds (its own and the pool it borrows), the taste file's bans and its
    one-still-an-object off first: the most stills a chain in it shows once each."""
    from xenoform import morph_pass, stills, taste

    cat = morph_pass.catalogue()
    pool_vibe = morph_pass.vibe_for({"vibe": vibe})
    rows = list(cat.get(pool_vibe) or []) + (list(cat.get(vibe) or []) if vibe != pool_vibe else [])
    rows = [r for r in rows if stills.kind_of(r) == "object"]
    if taste.active():
        return len(taste.usable(rows))
    return len({taste.words_of(r.get("noun") or r.get("file")) for r in rows})


def _user_preset(state: dict, loaded: list[dict]) -> dict | None:
    """The loved chain the body was made from (a preset chip applied: its vibe and its pins), or None."""
    from xenoform import morph_pass

    pins = {int(k): v for k, v in morph_pass.pins_of(state).items()}
    if not pins:
        return None
    vibe = str(state.get("vibe") or "")
    for p in loaded:
        mine = {int(k): v for k, v in (p.get("pins") or {}).items()}
        if p["vibe"] == vibe and mine and all(mine.get(k) == v for k, v in pins.items()):
            return p
    return None


def look_of_preset(preset: dict, state: dict) -> dict:
    """A passage's look from a loved chain: its vibe, line, pins, style, timing, effects, look, foreshadow, backdrop and
    knobs (over the song's), its seed. The Shape stays the song's."""
    from xenoform import presets, vibes

    body = presets.body(preset)
    knobs = dict(state.get("macros") or {}) if isinstance(state.get("macros"), dict) else {}
    knobs.update(body["macros"])
    row = next((r for r in vibes.catalog() if r["id"] == body["vibe"]), {})
    return {"vibe": body["vibe"], "preset": preset["id"], "name": preset["name"], "idea": body["idea"],
            "pins": dict(body["chain_pins"]), "morph_style": body["morph_style"], "morph_timing": body["morph_timing"],
            "effects": list(body["effects"]), "dance_fx": body["dance_fx"], "foreshadow": body["foreshadow"],
            "backdrop": body["backdrop"], "macros": knobs, "seed": int(body["seed"]), "why": "a loved chain",
            "line": str(preset.get("line") or ""), "palette": str(row.get("palette") or ""),
            "register": str(row.get("register") or "")}


def look_of_vibe(row: dict, state: dict, *, why: str, pins: dict | None = None) -> dict:
    """A passage's look from a vibe and the desk's own settings (the line, the style, the timing, the effects, the
    look, the knobs as set)."""
    idea = str(state.get("idea") or "")
    return {"vibe": row["id"], "preset": "", "name": str(row.get("name") or row["id"]), "idea": idea,
            "pins": dict(pins or {}), "morph_style": str(state.get("morph_style") or "auto"),
            "morph_timing": str(state.get("morph_timing") or "smooth"), "effects": list(state.get("effects") or []),
            "dance_fx": str(state.get("dance_fx") or "auto"), "foreshadow": str(state.get("foreshadow") or "auto"),
            "backdrop": str(state.get("backdrop") or "auto"),
            "macros": dict(state.get("macros") or {}) if isinstance(state.get("macros"), dict) else {},
            "seed": None, "why": why, "palette": str(row.get("palette") or ""), "register": str(row.get("register") or ""),
            "line": str(row.get("line") or "")}


def looks(passages: list[dict], state: dict, *, loaded: list[dict] | None = None) -> list[dict]:
    """One look a passage (``looks`` of the module doc): the vibe you chose on the main drop (on the passage its loved
    chain fits, when the body is one), the loved chains where they fit and their vibe is free, then the candidate vibes
    with the best pull for each passage, each vibe once. Past the vibes there are, a vibe comes round again (said in
    the look's ``why``)."""
    from xenoform import morph_pass
    from xenoform import presets as _presets
    from xenoform import vibes

    loaded = _presets.load() if loaded is None else loaded
    breathe = pacing.breathe_amount(state)
    chosen = str(state.get("vibe") or "")
    cands = candidates(chosen)
    rows = {r["id"]: r for r in vibes.catalog()}
    free = [r["id"] for r in cands]
    out: list[dict | None] = [None] * len(passages)
    order = _importance(passages)
    used_presets: set[str] = set()

    def take(vibe: str) -> None:
        if vibe in free:
            free.remove(vibe)

    mine = _user_preset(state, loaded)
    if mine is not None:  # the body is a loved chain: its look on the passage it fits best
        best = max(order, key=lambda i: (preset_fit(mine, passages[i]["role"], breathe), -order.index(i)))
        at = best if preset_fit(mine, passages[best]["role"], breathe) > 0 else order[0]
        out[at] = {**look_of_preset(mine, state), "why": "the loved chain you chose"}
        used_presets.add(mine["id"])
        take(mine["vibe"])
    elif chosen in rows:
        main = next((p["index"] for p in passages if p.get("main")), None)
        at = main if main is not None else order[0]
        pins = {str(k): v for k, v in morph_pass.pins_of(state).items()}
        out[at] = look_of_vibe(rows[chosen], state, why="the vibe you chose, on the main drop" if main is not None
                               else "the vibe you chose", pins=pins)
        take(chosen)
    for i in order:  # the loved chains where they fit
        if out[i] is not None:
            continue
        role = passages[i]["role"]
        fits = sorted(((preset_fit(p, role, breathe), -k, p) for k, p in enumerate(loaded)
                       if p["id"] not in used_presets and p["vibe"] in free), key=lambda t: (t[0], t[1]), reverse=True)
        if fits and fits[0][0] >= 2.0:
            p = fits[0][2]
            out[i] = look_of_preset(p, state)
            used_presets.add(p["id"])
            take(p["vibe"])
    seen = [str(o["vibe"]) for o in out if o]
    room: dict[str, int] = {}

    def holds(vibe: str, morphs: int) -> bool:  # the vibe's library carries the passage, with room for the song's others
        if vibe not in room:
            room[vibe] = capacity(vibe)
        return room[vibe] >= int(morphs) + 1 + CAPACITY_MARGIN

    for i in order:  # the rest: the candidate with the best pull, the featured order breaking a tie
        if out[i] is not None:
            continue
        role = passages[i]["role"]
        pool = free or [r["id"] for r in cands if r["id"] not in seen[-3:]] or [r["id"] for r in cands]
        pool = [v for v in pool if holds(v, passages[i]["morphs"])] or pool
        why = "drawn by taste" if free else "a vibe again: the song has more passages than vibes"
        pick = max(pool, key=lambda v: (affinity(rows.get(v) or {}, role), -pool.index(v)))
        out[i] = look_of_vibe(rows[pick], state, why=why)
        take(pick)
        seen.append(pick)
    return [o for o in out if o is not None]


# ------------------------------------------------------------------------------------------------ the bodies


def base_body(state: dict) -> dict:
    """The song's Make body as every window starts from it: the desk's body without the keys a window never carries,
    a Dense objects cut with no end card, no performer and no grow (the looks are drawn from the library as it is)."""
    out = {k: copy.deepcopy(v) for k, v in state.items() if k not in DROP_KEYS}
    out.update({"energy_preset": "dense", "end_card": False, "performer": 0, "auto_grow": False, "morph_count": "auto",
                "cut_plan": None, "paid_cloud": False, "cloud_quality": False, "cloud_confirm": "", "mode": "simple",
                "morph_source": "objects", "chain_pins": {}})
    return out


def window_body(base: dict, look: dict, ctx: dict, plan: dict, w: dict, *, label: str, seed: int, song_id: str = "") -> dict:
    """One window's Make body: the song's, the passage's look over it, the window (``length_s``/``length_start``, exact:
    the desk trims it where it says), its stretch of the song plan and its place in the song (``KEY``)."""
    b = copy.deepcopy(base)
    for key in ("vibe", "idea", "morph_style", "morph_timing", "effects", "dance_fx", "foreshadow", "backdrop", "macros"):
        if look.get(key) is not None:
            b[key] = copy.deepcopy(look[key])
    if look.get("palette"):
        b["palette"] = look["palette"]
    if look.get("register"):
        b["register"] = look["register"]
    if not str(look.get("idea") or "").strip():
        b["brief"] = look.get("line") or b.get("brief") or ""
    b["chain_pins"] = dict(look.get("pins") or {})
    b["seed"] = int(look["seed"]) if look.get("seed") is not None else int(seed)
    b["length_s"] = round(float(w["length_s"]), 4)
    b["length_start"] = round(float(w["start"]), 4)
    b["length_exact"] = True
    b[KEY] = {**ctx, "song": song_id, "plan": plan}
    b["song"] = label
    return b


def directed_for(features: dict, w: dict) -> dict:
    """The window's analysis as its Make reads it from the window file (``ui._window_features``): the song's beats in
    it, its length, its one passage."""
    a = analysis(features)
    off, length = float(w["start"]), float(w["length_s"])
    beats = [round(b - off, 4) for b in a["beats"] if off - 1e-6 <= b < off + length]
    return {"duration": length, "beats": beats, "tempo": a["tempo"],
            "sections": [{"label": w["role"], "role": w["role"], "start": 0.0, "end": round(length, 4)}]}


def _repeats(rows: list[dict]) -> list[str]:
    """The objects a chain shows twice (by name, as the taste file's no-object-twice reads them)."""
    from xenoform import taste

    seen: set[str] = set()
    out: list[str] = []
    for r in rows:
        noun = taste.words_of(r.get("noun") or Path(str(r.get("file") or "")).stem)
        if noun in seen and noun not in out:
            out.append(noun)
        seen.add(noun)
    return out


def objects(song: dict, features: dict) -> None:
    """The stills each window morphs through, picked the way its Make picks them (the chain it plans, the pick under the
    taste file, a fresh family on a drop run's first beat, one family a scene under full Breathe), the objects of every
    window picked before it left out (no object twice across passages) and pinned slot by slot in its body. The windows
    pick in the order the looks are drawn (the intro, the outro, the main drop, the other drops, then the longest
    passages first), so the song's moments get first call on the library. A passage cut in two windows carries on: the
    second opens on the still the first landed on. In place: each window's ``stills``, ``nouns`` and body pins, and
    every body's ``avoid_nouns`` (the other windows' objects, for any slot left free)."""
    from xenoform import cloud_morph, dense, morph_pass

    noun_of = {str(r.get("file")): str(r.get("noun") or "").strip().lower()
               for rows in morph_pass.catalogue().values() for r in rows if r.get("file")}
    for w in song["windows"]:  # a loved chain's pins (and yours) are held: no window before them takes those objects
        slots = int(w["morphs"]) + 1  # a loved chain longer than the window: as many of its stills as the window holds
        pins = {k: v for k, v in (w["body"].get("chain_pins") or {}).items() if str(k).isdigit() and int(k) < slots}
        w["body"]["chain_pins"] = {} if w["part"] else pins
    reserved = {w["index"]: [noun_of.get(str(f), "") for f in w["body"]["chain_pins"].values()] for w in song["windows"]}
    taken_nouns: list[str] = []
    taken_files: list[str] = []
    order = [k for i in _importance(song["passages"]) for k in song["passages"][i]["windows"]]
    for w in (song["windows"][k] for k in order):
        body = w["body"]
        if w["part"] and w["index"] > 0:  # the passage's second window starts where the first landed
            prev = song["windows"][w["index"] - 1]
            if prev.get("stills"):
                body["chain_pins"] = {"0": prev["stills"][-1]}
        held = [n for k, nouns in reserved.items() if k != w["index"] for n in nouns if n]
        body["avoid_nouns"] = sorted(set(taken_nouns) | set(held))
        body["avoid_stills"] = list(dict.fromkeys(taken_files))
        directed = directed_for(features, w)
        shots, plan = dense.shots_for(body, directed, None, drop=w["plan"].get("drop"))
        shots, plan, chain, _ = dense.long_song_chain(body, directed, None, shots, plan, dense.options(body), grow=False)
        kw = dense._scene_kw(body, shots, chain["morphs"] + 1, chain["assign"])
        vibe, pool = cloud_morph.stills_for({**body, "cut_plan": None}, chain["morphs"] + 1, record=False, **kw)
        if _repeats(pool) and body.get("brief") and not str(body.get("idea") or "").strip():
            # the vibe's own line named a family too small for the passage (cosmic's "star field": eleven bodies for a
            # fourteen-still chain) and the chain lapped it: the pick without the line, which walks on instead
            vibe, again = cloud_morph.stills_for({**body, "brief": "", "cut_plan": None}, chain["morphs"] + 1, record=False, **kw)
            if len(_repeats(again)) < len(_repeats(pool)):
                body["brief"], pool = "", again
        if dense.drop_treated(body, shots):
            pool = pacing.fresh_at_drops(pool, shots, chain["assign"])[0]
        if pacing.boldness(pacing.breathe_amount(body)) >= 0.5 and pacing.paced_shots(shots):
            pool = pacing.scene_families(pool, shots, chain["assign"])[0]
        w["stills"] = [str(r.get("file")) for r in pool]
        w["nouns"] = [str(r.get("noun") or "") for r in pool]
        w["families"] = sorted({str(r.get("family") or "") for r in pool if r.get("family")})
        w["morphs"] = int(chain["morphs"])
        body["chain_pins"] = {str(i): f for i, f in enumerate(w["stills"])}
        taken_nouns += [n.strip().lower() for n in w["nouns"] if n.strip()]
        taken_files += w["stills"]
    for w in song["windows"]:
        others = {n.strip().lower() for v in song["windows"] if v is not w for n in v.get("nouns") or [] if n.strip()}
        w["body"]["avoid_nouns"] = sorted(others - {n.strip().lower() for n in w.get("nouns") or []})
        w["body"].pop("avoid_stills", None)
    for p in song["passages"]:
        nouns: list[str] = []
        for k in p["windows"]:
            nouns += [n for n in song["windows"][k].get("nouns") or [] if n not in nouns]
        p["objects"] = nouns
        p["morphs"] = sum(int(song["windows"][k]["morphs"]) for k in p["windows"])


# ------------------------------------------------------------------------------------------------ the title


def last_hit(features: dict, plan: dict) -> float | None:
    """The song's last hit, where the title lands (the hand-made video's 3:51 on Glitch Out): the last bar line of the
    song plan, with the song still running ``TITLE_TAIL_MIN`` after it, whose onset and level both stand with the song's
    loudest (its 95th percentile of each); else the last bar line with a strong onset; else the outro's first bar line;
    None for a song with no beat grid."""
    grid = list(plan.get("grid_times") or [])
    duration = float(features.get("duration") or 0.0)
    if len(grid) < 4 or duration <= 0:
        return None
    phase = int(plan.get("bar_phase") or 0)
    bars = [t for i, t in enumerate(grid) if (i - phase) % 4 == 0 and t <= duration - TITLE_TAIL_MIN]
    frames = [f for f in features.get("frames") or [] if isinstance(f, dict)]
    fps = float(features.get("fps") or 24.0)
    outro = next((p for p in reversed(plan.get("passages") or []) if p.get("role") == "outro"), None)
    late = float(outro["start"]) if outro else max(0.0, duration - 30.0)
    if frames:
        ons = sorted(float(f.get("onset_strength") or 0.0) for f in frames)
        lvl = sorted(float(f.get("rms") or 0.0) for f in frames)
        o95, r95 = ons[int(0.95 * (len(ons) - 1))] or 1.0, lvl[int(0.95 * (len(lvl) - 1))] or 1.0

        def at(t: float) -> tuple[float, float]:
            k = int(round(t * fps))
            near = frames[max(0, k - 1):k + 2] or [frames[min(len(frames) - 1, max(0, k))]]
            return (max(float(f.get("onset_strength") or 0.0) for f in near) / o95,
                    max(float(f.get("rms") or 0.0) for f in near) / r95)

        tail = [t for t in bars if t >= late - 1e-6]
        hit = next((t for t in reversed(tail) if at(t)[0] >= 1.0 and at(t)[1] >= 0.9), None)
        if hit is None:
            hit = next((t for t in reversed(tail) if at(t)[0] >= 0.8), None)
        if hit is not None:
            return round(hit, 4)
    after = [t for t in bars if t >= late - 1e-6]
    return round(after[0], 4) if after else (round(bars[-1], 4) if bars else None)


# ------------------------------------------------------------------------------------------------ the estimate


def _compose_s(seconds: float, tier: str) -> float:
    from xenoform import beatfx, dense

    frames = int(round(float(seconds) * 24))
    per = dense.COMPOSE_S_PER_FRAME["final" if tier in ("final", "fast", "cloud") else "draft"]
    return frames * per / beatfx.look_speedup(frames)


def estimate(song: dict, *, aspect: str = "16:9", rates: dict | None = None) -> dict:
    """The whole song on each tier before anything runs: the morphs (the sum of the windows'), the minutes (each window
    a Make: its morphs on the tier's measured cost, its look pass, the fixed steps and the QA, then the assembly once),
    and for Cloud the credits it would spend (``CLOUD_CREDITS`` a morph). ``rates``, when given, are this machine's
    measured seconds of render per second of video (``batch.measured``); the tier's figure then says so."""
    from xenoform import cloud_final, dense, job_timing

    wins = song["windows"]
    morphs = sum(int(w["morphs"]) for w in wins)
    seconds = float(song.get("duration") or sum(float(w["length_s"]) for w in wins))
    clip = []
    for w in wins:
        beats = [b for b in song.get("beats") or []]
        clip.append(int(dense.clip_plan([{}] * max(1, int(w["morphs"])), float(w["length_s"]), beats)["clip_s"]))
    fixed = sum(job_timing.FIXED_S["analyze"] + job_timing.FIXED_S["draft"] + job_timing.FIXED_S["save"]
                + job_timing.QA_BASE_S + job_timing.QA_S_PER_SONG_S * float(w["length_s"]) for w in wins)
    assembly_s = 30.0 + 0.12 * seconds * 24 / 10.0  # the picture laid end to end, the tame and the QA once (CPU)
    out: dict = {"morphs": morphs, "windows": len(wins), "passages": len(song["passages"]), "seconds": round(seconds, 1),
                 "tiers": {}}
    for tier in TIERS:
        gpu = look = 0.0
        for w, c in zip(wins, clip):
            if tier == "cloud":
                gpu += float(cloud_final.estimate(int(w["morphs"]))["seconds"])
            else:
                e = dense.estimate(int(w["morphs"]), tier, aspect, "native", clip_s=c, compose_s=0.0)
                gpu += float(e["gpu_seconds"])
            look += _compose_s(float(w["length_s"]), tier)
        total = gpu + look + fixed + assembly_s
        row = {"morphs": morphs, "gpu_s": int(round(gpu)), "look_s": int(round(look)), "seconds": int(round(total)),
               "minutes": round(total / 60.0, 1), "measured": False}
        rate = ((rates or {}).get(tier) or {}).get("per_s")
        if rate:
            measured = float(rate) * seconds + assembly_s
            row.update({"seconds": int(round(measured)), "minutes": round(measured / 60.0, 1), "measured": True,
                        "per_s": float(rate)})
        if tier == "cloud":
            row["credits"] = [int(round(morphs * CLOUD_CREDITS[0])), int(round(morphs * CLOUD_CREDITS[1]))]
            row["where"] = "Comfy Cloud, three morphs at once; the look and the assembly here"
        out["tiers"][tier] = row
    return out


# ------------------------------------------------------------------------------------------------ the plan


def summary_line(song: dict) -> str:
    """"14 passages, 78 morphs; 5 drops, the main at 2:21" for the desk and the record."""
    runs = [p for p in song["passages"] if p.get("drop_run") is not None]
    main = next((p for p in runs if p.get("main")), runs[0] if runs else None)
    bits = [f"{len(song['passages'])} passage{'s' if len(song['passages']) != 1 else ''}",
            f"{song['morphs']} morph{'s' if song['morphs'] != 1 else ''}"]
    if len(song["windows"]) != len(song["passages"]):
        bits[-1] += f" in {len(song['windows'])} Makes"
    drops = f"{len(runs)} drop{'s' if len(runs) != 1 else ''}" + (f", the main at {pacing.clock(main['start'])}" if main else "")
    return ", ".join(bits) + "; " + (drops if runs else "no drop")


def plan(features: dict, state: dict, *, drop: float | None, song_id: str = "", label: str = "", pick: bool = True,
         rates: dict | None = None) -> dict:
    """The whole song: its passages, its windows (each with its Make body when ``pick``: the looks drawn and the stills
    picked and pinned), the title's hit and the estimate. ``pick`` False is the desk's quick estimate (no stills read)."""
    why = refuse(state)
    if why:
        raise SongError(why)
    tier = tier_of(state)
    full = whole(features, state, drop)
    passages, windows = passages_of(full, tier)
    a = analysis(features)
    song = {"duration": round(a["duration"], 3), "tempo": a["tempo"], "drop": full.get("drop"), "first_drop": first_drop(full),
            "breathe": pacing.breathe_amount(state), "drop_mode": pacing.drop_mode_of(state), "tier": tier,
            "aspect": str(state.get("aspect") or "16:9"), "cap": full.get("cap") or "auto", "window_cap": window_cap(tier),
            "steps": dict(full.get("steps") or {}), "bar_phase": full.get("bar_phase"), "period": full.get("period"),
            "shots": len(full["shots"]), "passages": passages, "windows": windows, "beats": a["beats"],
            "title": {"text": title_of(state), "at": last_hit(features, full)}}
    song["morphs"] = sum(int(w["morphs"]) for w in windows)
    for w in windows:
        w["plan"] = window_plan(full, song, w)
    ctxs = contexts(full, song)
    for w, ctx in zip(windows, ctxs):
        w["context"] = ctx
    if pick:
        drawn = looks(passages, state)
        for p, look in zip(passages, drawn):
            p["look"] = look
        base = base_body(state)
        seed0 = int(state.get("seed") or 2727)
        name = label or str(state.get("song") or "the song")
        for w, ctx in zip(windows, ctxs):
            p = passages[w["passage"]]
            part = f", part {w['part'] + 1} of {w['parts']}" if w["parts"] > 1 else ""
            w["body"] = window_body(base, p["look"], ctx, w["plan"], w,
                                    label=f"{name} · passage {p['index'] + 1} of {len(passages)}{part}",
                                    seed=seed0 + SEED_STEP * w["index"], song_id=song_id)
        objects(song, features)
        song["morphs"] = sum(int(w["morphs"]) for w in windows)
    song["line"] = summary_line(song)
    song["estimate"] = estimate(song, aspect=song["aspect"], rates=rates)
    song.pop("beats", None)
    for w in windows:
        w.pop("shot_idx", None)
    return song


def table(song: dict) -> list[dict]:
    """The passage table (the proof's README, the record): passage, role, song seconds, vibe, morphs, looks a minute."""
    rows = []
    for p in song["passages"]:
        secs = max(1e-6, float(p["end"]) - float(p["start"]))
        look = p.get("look") or {}
        rows.append({"passage": p["index"] + 1, "role": p["role"], "start": round(float(p["start"]), 2),
                     "end": round(float(p["end"]), 2), "seconds": round(secs, 1), "vibe": look.get("vibe") or "",
                     "preset": look.get("preset") or "", "morphs": int(p.get("morphs") or 0),
                     "looks_a_minute": round(int(p.get("morphs") or 0) * 60.0 / secs, 1),
                     "objects": list(p.get("objects") or []), "heat": p.get("heat")})
    return rows


def song_path(features: dict) -> Path | None:
    raw = features.get("path") or features.get("audio_path")
    return Path(str(raw)) if raw else None
