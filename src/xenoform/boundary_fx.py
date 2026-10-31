"""Boundary kinds: what a handoff does at the cut when Chaos asks for more than a plain one.

Four kinds, each a different picture on a one-tile-a-second sheet and each riding a stem: a **smear** (datamosh-style
block displacement of the outgoing picture along the drums for half a bar), a **strobe cut** (the two objects alternate
frame by frame for a beat, luma-matched so the QA flash check never counts it; only past Chaos 0.7 and never two in two
seconds), a **wipe** on the bar (the next object enters as strips or a radial iris on the bass, the strip count from
Chaos) and a **chromatic rip** (the two pictures' RGB channels offset and crossed on the other stem, the offset from
Intensity).

The second picture at a handoff is the object that is new there. A cut is a chain of morphs, each landing on the
object the next one starts from, so at a morph landing the outgoing and incoming frames show the same object and the
new one is where the next morph lands (its last frame); across a hard cut into Polly or an own clip it is that clip's
first frame, and out of it the object that left. ``pick`` chooses a kind per boundary from Chaos and the section role
(Chaos 0 is the plain handoff everywhere, 1 gives every boundary a kind, never the same twice in a row, the drop the
loudest); ``plan`` reads the edge frames the workers need; ``treat`` is the per-frame function ``beatfx._shot_frames``
runs before the house look, so the look grades the handoff as part of the picture; ``clear_premium`` keeps the vibe's
premium picks off the boundaries this layer takes. Pure numpy; no model, no GPU, and it runs inside the parallel look
pass like the foreshadow layer.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np

KINDS = ("smear", "strobe", "wipe", "rip")
LABELS = {"smear": "smear", "strobe": "strobe cut", "wipe": "wipe", "rip": "chromatic rip"}
BEATS = {"smear": 2.0, "strobe": 1.0, "wipe": 4.0, "rip": 2.0}  # the window in beats, centred on the cut: half a bar, a beat, a bar
STEM = {"smear": "drums", "strobe": "drums", "wipe": "bass", "rip": "other"}
ON_CHAOS = 0.15          # at or under this every handoff is plain (apply_macros drops the stutters under 0.2 too)
FULL_CHAOS = 0.85        # from here every boundary gets a kind
STROBE_MIN_CHAOS = 0.7
STROBE_GAP_S = 2.0       # the QA flash budget is one hard flash in two seconds: a strobe is luma-matched, and spaced like one anyway
PREFER = {               # per section role, what the role likes first; the loud roles like the loud kinds
    "drop": ("strobe", "rip", "smear", "wipe"),
    "drop_late": ("rip", "strobe", "smear", "wipe"),
    "build": ("rip", "wipe", "smear", "strobe"),
    "release": ("wipe", "rip", "smear", "strobe"),
}
PREFER_DEFAULT = ("wipe", "smear", "rip", "strobe")  # intro, calm, sustain, outro, or a plan with no sections
IRIS_ROLES = ("drop", "drop_late", "build")          # the wipe is an iris where the song is loud, strips elsewhere
MIN_HALF = 2             # frames: the least either half of a window may be


# ------------------------------------------------------------------------------------------------ the knobs


def params(macros: dict | None) -> dict:
    """The knobs as the kinds read them: Intensity sets how hard a kind hits (a ghost at 0, the full thing at 1) and
    the rip's channel offset; Chaos sets the strip count (and, in ``pick``, how many boundaries get a kind at all)."""
    m = macros or {}

    def knob(key: str, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(m.get(key, default))))
        except (TypeError, ValueError):
            return default

    intensity, chaos = knob("intensity", 0.5), knob("chaos", 0.3)
    return {"amount": round(0.4 + 0.6 * intensity, 3), "offset": round(0.004 + 0.036 * intensity, 4),
            "strips": int(2 + round(14 * chaos)), "chaos": round(chaos, 3), "intensity": round(intensity, 3)}


def share(chaos: float) -> float:
    """The share of boundaries that get a kind: none at or under ``ON_CHAOS``, all from ``FULL_CHAOS``."""
    c = max(0.0, min(1.0, float(chaos)))
    if c <= ON_CHAOS:
        return 0.0
    return min(1.0, (c - ON_CHAOS) / (FULL_CHAOS - ON_CHAOS))


def _beat_period(beats, fallback: float = 0.5) -> float:
    b = [float(x) for x in (beats or [])]
    if len(b) < 2:
        return fallback
    d = np.diff(np.asarray(b))
    d = d[(d > 0.15) & (d < 2.0)]
    return float(np.median(d)) if len(d) else fallback


# ------------------------------------------------------------------------------------------------ the picker


SMEAR = ("off", "sparing", "on")  # the blocky smear: off unless asked (Tys, 28 Oct: "optional or used sparingly")
SMEAR_SHARE = 6                   # sparing: at most one handoff in this many takes the smear, never the drop


def smear_of(value) -> str:
    v = str(value or "").strip().lower()
    return v if v in SMEAR else "off"


WIPE_SHARE = 0.25        # a paced cut: wipes at most a quarter of its handoffs (the repeated strip-wipe "bar", Tys 30 Oct)
NO_KIND_ROLES = ("intro", "build", "outro")  # Breathe: plain handoffs here (the montage's intro, builds and outro had none)


def _pick_paced(shots: list[dict], macros: dict | None, beats, fps: int, *, seed: int, premium: list | None, smear: str,
                breathe: bool, limits: dict | None = None) -> list[dict | None]:
    """``pick`` for a cut the pacing engine shaped (``pacing.shape``): each passage takes the share of its handoffs its
    own Chaos asks for (a shot's ``chaos``: the knob, capped by the passage under Breathe, lifted in a drop by its heat;
    none in an intro, a build or an outro under Breathe); a drop run's first handoff and every planted ``event`` come
    first; wipes stay at most ``WIPE_SHARE`` of all the handoffs; the strobe only in a run at full heat and two seconds
    from the last one; never the kind just used; the premium transitions keep their boundaries."""
    n = len(shots)
    out: list[dict | None] = [None] * n
    if n < 2:
        return out
    p = params(macros)
    period = _beat_period(beats)
    prem = list(premium or [])

    def role(i: int) -> str:
        return str(shots[i].get("section") or "")

    def heat(i: int) -> float:
        try:
            return float(shots[i].get("heat") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def entry(i: int) -> bool:
        return str(shots[i].get("boundary") or "") == "drop"

    def held(i: int) -> bool:
        return i < len(prem) and isinstance(prem[i], dict) and bool(prem[i].get("kind"))

    # a run whose first handoff carries the vibe's premium drop transition takes its boundary kind on the next one
    follow = {i + 1 for i in range(1, n - 1) if entry(i) and held(i) and shots[i + 1].get("drop_run") is not None
              and shots[i + 1].get("drop_run") == shots[i].get("drop_run")}

    def event(i: int) -> bool:  # a drop run's first handoff (or the next one), or a long run's planted kind
        return entry(i) or i in follow or str(shots[i].get("event") or "") == "kind"

    def share_at(i: int) -> float:
        if breathe and role(i) in NO_KIND_ROLES:
            return 0.0
        try:
            c = float(shots[i].get("chaos", p["chaos"]))
        except (TypeError, ValueError):
            c = p["chaos"]
        return share(c)

    cand = []
    for i in range(1, n):
        if i < len(prem) and isinstance(prem[i], dict) and bool(prem[i].get("kind")):
            continue  # the vibe's premium transition keeps its boundary
        if int(shots[i].get("frames") or 0) < 2 * MIN_HALF or int(shots[i - 1].get("frames") or 0) < 2 * MIN_HALF:
            continue
        cand.append(i)
    if not cand:
        return out
    chosen = [i for i in cand if event(i) and share_at(i) > 0]  # an event dressed first, unless Chaos asks for none
    groups: dict = {}
    for i in cand:
        groups.setdefault(shots[i].get("passage", role(i)), []).append(i)
    for idx in groups.values():
        want = int(round(max(share_at(i) for i in idx) * len(idx)))
        have = [i for i in idx if i in chosen]
        rest = [i for i in idx if i not in chosen]
        need = want - len(have)
        if need > 0 and rest:
            take = sorted({int(round(x)) for x in np.linspace(0, len(rest) - 1, min(need, len(rest)))})
            chosen += [rest[j] for j in take]
    chosen = sorted(set(chosen))
    smear = smear_of(smear)
    smear_cap = 0 if smear == "off" else max(1, len(chosen) // SMEAR_SHARE) if smear == "sparing" else len(chosen)
    lim = limits or {}
    # the taste file's numbers when it gives them (wipes-a-quarter, strobe-at-full-heat), the pacing engine's own otherwise
    wipe_cap = int((WIPE_SHARE if lim.get("wipe_share") is None else float(lim["wipe_share"])) * (n - 1))
    strobe_heat = 1.0 if lim.get("strobe_heat") is None else float(lim["strobe_heat"])
    rot = int(seed) % len(KINDS)
    uses = {k: 0 for k in KINDS}
    assigned: dict[int, str] = {}
    strobe_times: list[float] = []

    def allowed_for(i: int, exclude: set) -> list[str]:
        t = float(shots[i].get("start") or 0.0)
        prefer = PREFER["drop"] if entry(i) else PREFER.get(role(i), PREFER_DEFAULT)
        return [k for k in prefer if k not in exclude
                and (k != "strobe" or (heat(i) >= strobe_heat and event(i) and all(abs(t - ts) >= STROBE_GAP_S for ts in strobe_times)))
                and (k != "wipe" or uses["wipe"] < wipe_cap)
                and (k != "smear" or (uses["smear"] < smear_cap and not entry(i)))]

    last = None
    for i in chosen:  # left to right: the strobe's two seconds and "never the kind just used" read in time
        opts = allowed_for(i, {last} if last else set())
        if not opts:
            continue
        prefer = PREFER["drop"] if entry(i) else PREFER.get(role(i), PREFER_DEFAULT)
        kind = opts[0] if event(i) else min(opts, key=lambda k: (uses[k], (prefer.index(k) + rot) % len(KINDS)))
        assigned[i] = kind
        uses[kind] += 1
        last = kind
        if kind == "strobe":
            strobe_times.append(float(shots[i].get("start") or 0.0))
    for i in sorted(assigned):
        kind = assigned[i]
        t = float(shots[i].get("start") or 0.0)
        win = max(2 * MIN_HALF, int(round(BEATS[kind] * period * fps)))
        tail = max(MIN_HALF, min(win // 2, int(shots[i - 1]["frames"]) // 2))
        head = max(MIN_HALF, min(win - win // 2, int(shots[i]["frames"]) // 2))
        variant = ("iris" if role(i) in IRIS_ROLES else "strips") if kind == "wipe" else ""
        out[i] = {"kind": kind, "frames": tail + head, "tail": tail, "head": head, "section": role(i),
                  "boundary": str(shots[i].get("boundary") or ""), "stem": STEM[kind], "variant": variant, "t": round(t, 3)}
    return out


def pick(shots: list[dict], macros: dict | None, beats, fps: int, *, seed: int = 0, premium: list | None = None,
         drop: float | None = None, smear: str = "off", paced: dict | None = None) -> list[dict | None]:
    """One entry per shot (None for a plain handoff): the kind at the boundary into that shot and its window.

    Chaos decides how many boundaries take a kind (``share``): the drop first, then the section switches, then an
    even spread of the rest. Each chosen boundary gets the kind its section role likes that was used least so far,
    never the kind just used, with the seed rotating the role's order; the drop takes the loudest it may have. The
    strobe needs Chaos above ``STROBE_MIN_CHAOS`` and two seconds since the last one. A boundary that carries the
    vibe's premium transition (``premium``, from ``dense.boundary_transitions``) keeps it, except the drop past 0.7,
    where the strobe takes the loudest handoff of the song. Shots too short for a window are left plain. ``drop`` (the
    plan's drop time) marks the boundary nearest it as the drop when no shot carries a ``boundary`` key (the dense plan
    of a short cut), and on such a plan the wipes from the drop on are irises. ``smear`` (``SMEAR``) is the blocky smear:
    "off" (the default since 28 Oct) leaves it to the timeline, "sparing" allows one handoff in ``SMEAR_SHARE`` and
    never the drop, "on" lets it in like the other kinds. ``paced`` (``{"breathe": bool}``, a cut the pacing engine
    shaped) picks by passage instead (``_pick_paced``).

    The taste file's limits on the kinds (``taste.kind_limits``) apply to both: wipes at most a share of the handoffs
    (``wipes-a-quarter``), the strobe only on a boundary at full heat (``strobe-at-full-heat``: the main drop; a shot's
    ``heat``, else 1 for the drop boundary), and never the kind just used, which both pickers already keep. What they
    changed is said as a ``[taste]`` line; the kinds are as before with no taste file."""
    from xenoform import taste as _taste

    lim = _taste.kind_limits() if _taste.active() else None
    if not lim or (lim.get("wipe_share") is None and lim.get("strobe_heat") is None):
        lim = None

    def run(limits: dict | None) -> list[dict | None]:
        if paced is not None:
            return _pick_paced(shots, macros, beats, fps, seed=seed, premium=premium, smear=smear,
                               breathe=bool(paced.get("breathe")), limits=limits)
        return _pick(shots, macros, beats, fps, seed=seed, premium=premium, drop=drop, smear=smear, limits=limits)

    out = run(lim)
    if lim is not None:
        plain = run(None)
        if plain != out:
            def count(picks: list, kind: str) -> int:
                return sum(1 for p in picks if p and p.get("kind") == kind)

            bits = []
            if count(plain, "wipe") > count(out, "wipe"):
                bits.append(f"wipes {count(plain, 'wipe')} to {count(out, 'wipe')} of {max(0, len(shots) - 1)} handoffs")
            if count(plain, "strobe") > count(out, "strobe"):
                bits.append(f"strobes {count(plain, 'strobe')} to {count(out, 'strobe')}, only at full heat")
            ids = (["wipes-a-quarter"] if any(b.startswith("wipes") for b in bits) else []) + \
                  (["strobe-at-full-heat"] if any(b.startswith("strobes") for b in bits) else [])
            if bits:
                _taste.note(ids, "handoff kinds: " + "; ".join(bits))
    return out


def _pick(shots: list[dict], macros: dict | None, beats, fps: int, *, seed: int = 0, premium: list | None = None,
          drop: float | None = None, smear: str = "off", limits: dict | None = None) -> list[dict | None]:
    smear = smear_of(smear)
    n = len(shots)
    out: list[dict | None] = [None] * n
    if n < 2:
        return out
    p = params(macros)
    chaos = p["chaos"]
    sh = share(chaos)
    if sh <= 0:
        return out
    period = _beat_period(beats)
    prem = list(premium or [])
    drop_i = None
    if drop is not None and not any(str(s.get("boundary") or "") == "drop" for s in shots):
        near = min(range(1, n), key=lambda i: abs(float(shots[i].get("start") or 0.0) - float(drop)))
        if abs(float(shots[near].get("start") or 0.0) - float(drop)) <= 2 * period + 1e-6:
            drop_i = near

    def kind_of(i: int) -> str:
        return str(shots[i].get("boundary") or "") or ("drop" if i == drop_i else "")

    cand = []
    for i in range(1, n):
        has_prem = i < len(prem) and isinstance(prem[i], dict) and bool(prem[i].get("kind"))
        if has_prem and not (kind_of(i) == "drop" and chaos > STROBE_MIN_CHAOS):
            continue
        if int(shots[i].get("frames") or 0) < 2 * MIN_HALF or int(shots[i - 1].get("frames") or 0) < 2 * MIN_HALF:
            continue
        cand.append(i)
    if not cand:
        return out
    want = len(cand) if sh >= 1.0 else max(1, int(round(sh * len(cand))))
    first = [i for i in cand if kind_of(i) == "drop"] + [i for i in cand if kind_of(i) and kind_of(i) != "drop"]
    chosen = first[:want]
    rest = [i for i in cand if i not in chosen]
    need = want - len(chosen)
    if need > 0 and rest:
        take = sorted({int(round(x)) for x in np.linspace(0, len(rest) - 1, min(need, len(rest)))})
        chosen += [rest[j] for j in take]
    chosen.sort()
    rot = int(seed) % len(KINDS)
    uses = {k: 0 for k in KINDS}
    assigned: dict[int, str] = {}
    strobe_times: list[float] = []

    def prefer_for(i: int) -> tuple:
        if kind_of(i) == "drop":  # the drop wants the loudest whatever its shot's role says (the dense plan has none)
            return PREFER["drop"]
        return PREFER.get(str(shots[i].get("section") or ""), PREFER_DEFAULT)

    smear_cap = 0 if smear == "off" else max(1, len(chosen) // SMEAR_SHARE) if smear == "sparing" else len(chosen)
    lim = limits or {}
    wipe_cap = None if lim.get("wipe_share") is None else int(float(lim["wipe_share"]) * (n - 1))
    strobe_heat = lim.get("strobe_heat")

    def heat_at(i: int) -> float:  # a shot's own heat (a paced plan), else the drop boundary is the main drop's
        try:
            return float(shots[i]["heat"]) if shots[i].get("heat") is not None else (1.0 if kind_of(i) == "drop" else 0.0)
        except (TypeError, ValueError):
            return 0.0

    def allowed_for(i: int, exclude: set) -> list[str]:
        t = float(shots[i].get("start") or 0.0)
        prefer = prefer_for(i)
        return [k for k in prefer if k not in exclude
                and (k != "strobe" or (chaos > STROBE_MIN_CHAOS and all(abs(t - ts) >= STROBE_GAP_S for ts in strobe_times)
                                       and (strobe_heat is None or heat_at(i) >= float(strobe_heat))))
                and (k != "wipe" or wipe_cap is None or uses["wipe"] < wipe_cap)
                and (k != "smear" or (uses["smear"] < smear_cap and not (smear == "sparing" and kind_of(i) == "drop")))]

    def take(i: int, kind: str) -> None:
        assigned[i] = kind
        uses[kind] += 1
        if kind == "strobe":
            strobe_times.append(float(shots[i].get("start") or 0.0))

    for i in chosen:  # the drop first: the loudest handoff of the song gets the loudest kind it may have
        if kind_of(i) == "drop":
            opts = allowed_for(i, set())
            if opts:
                take(i, opts[0])
    for pos, i in enumerate(chosen):  # then the rest in order: the least-used kind the role likes, never a neighbour's
        if i in assigned:
            continue
        neighbours = {assigned.get(chosen[pos - 1]) if pos > 0 else None, assigned.get(chosen[pos + 1]) if pos + 1 < len(chosen) else None}
        opts = allowed_for(i, {k for k in neighbours if k})
        if not opts:  # with the smear off, two neighbours can hold the only two kinds left: a plain handoff
            continue
        prefer = prefer_for(i)
        take(i, min(opts, key=lambda k: (uses[k], (prefer.index(k) + rot) % len(KINDS))))
    for i in sorted(assigned):
        kind = assigned[i]
        role = str(shots[i].get("section") or "")
        t = float(shots[i].get("start") or 0.0)
        win = max(2 * MIN_HALF, int(round(BEATS[kind] * period * fps)))
        tail = max(MIN_HALF, min(win // 2, int(shots[i - 1]["frames"]) // 2))
        head = max(MIN_HALF, min(win - win // 2, int(shots[i]["frames"]) // 2))
        loud = role in IRIS_ROLES or (not role and drop is not None and t >= float(drop) - 1e-6)  # no roles: loud from the drop on
        variant = ("iris" if loud else "strips") if kind == "wipe" else ""
        out[i] = {"kind": kind, "frames": tail + head, "tail": tail, "head": head, "section": role, "boundary": kind_of(i),
                  "stem": STEM[kind], "variant": variant, "t": round(t, 3)}
    return out


def clear_premium(premium: list | None, picks: list) -> list | None:
    """The premium list with None where a boundary kind took the handoff, so the two never draw over one window."""
    if premium is None:
        return None
    return [None if (i < len(picks) and picks[i]) else t for i, t in enumerate(premium)]


def make(shots: list[dict], i: int, kind: str, beats, fps: int, *, variant: str | None = None,
         drop: float | None = None) -> dict | None:
    """One entry for the boundary into shot ``i`` with ``kind``, shaped as ``pick`` shapes one (the window in beats
    centred on the cut, the stem, the wipe's iris on a loud role or from the drop on): the timeline's hand-picked
    boundary kind (docs/TIMELINE.md). None when the kind is unknown, ``i`` is not a boundary or a shot beside it is
    too short for a window."""
    kind = str(kind or "").strip().lower()
    n = len(shots)
    if kind not in KINDS or not 1 <= i < n:
        return None
    if int(shots[i].get("frames") or 0) < 2 * MIN_HALF or int(shots[i - 1].get("frames") or 0) < 2 * MIN_HALF:
        return None
    period = _beat_period(beats)
    role = str(shots[i].get("section") or "")
    t = float(shots[i].get("start") or 0.0)
    win = max(2 * MIN_HALF, int(round(BEATS[kind] * period * fps)))
    tail = max(MIN_HALF, min(win // 2, int(shots[i - 1]["frames"]) // 2))
    head = max(MIN_HALF, min(win - win // 2, int(shots[i]["frames"]) // 2))
    loud = role in IRIS_ROLES or (not role and drop is not None and t >= float(drop) - 1e-6)
    if kind == "wipe":
        variant = variant if variant in ("iris", "strips") else ("iris" if loud else "strips")
    else:
        variant = ""
    return {"kind": kind, "frames": tail + head, "tail": tail, "head": head, "section": role,
            "boundary": str(shots[i].get("boundary") or ""), "stem": STEM[kind], "variant": variant, "t": round(t, 3),
            "user": True}


def label(entry: dict | None) -> str:
    """What the lane calls it: "smear", "strobe cut", "iris wipe" / "strip wipe", "chromatic rip"."""
    if not isinstance(entry, dict) or not entry.get("kind"):
        return ""
    kind = str(entry["kind"])
    if kind == "wipe":
        return f"{'iris' if entry.get('variant') == 'iris' else 'strip'} wipe"
    return LABELS.get(kind, kind)


def info(picks: list, p: dict | None = None) -> dict:
    """What the record says about the layer."""
    used = [e for e in (picks or []) if isinstance(e, dict) and e.get("kind")]
    kinds: dict[str, int] = {}
    for e in used:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    return {"boundaries": len(used), "kinds": kinds, "labels": [label(e) for e in used], "params": dict(p or {})}


# ------------------------------------------------------------------------------------------------ the plan


def plan(picks: list, shots: list[dict], clips: list, *, read_edge: Callable[[Path, str], np.ndarray] | None = None,
         marks: tuple[str, ...] = ("performer", "own")) -> list[dict | None]:
    """One entry per shot (or None) with the halves of the windows that fall in it: ``head`` (the kind into this
    shot, over its first frames) and ``tail`` (the kind into the next shot, over its last frames), each with the
    second picture as an array. At a morph landing both halves show where this shot lands (its last frame); across
    a hard cut the tail shows the clip arriving (its first frame) and the head the object that left (the previous
    shot's last frame). Frames are read once each here, in the parent, and travel to the workers as arrays."""
    from xenoform.foreshadow import edge_frame

    read_edge = read_edge or edge_frame
    n = len(shots)
    out: list[dict | None] = [None] * n
    cache: dict[tuple[str, str], np.ndarray] = {}

    def frame(i: int, which: str) -> np.ndarray | None:
        if not 0 <= i < len(clips):
            return None
        key = (str(clips[i]), which)
        if key not in cache:
            try:
                cache[key] = np.ascontiguousarray(read_edge(Path(str(clips[i])), which))
            except Exception:
                return None
        return cache[key]

    def hard(i: int) -> bool:
        return 0 <= i < n and any(bool(shots[i].get(m)) for m in marks)

    def held(i: int) -> bool:  # a held shot (the timeline's Hold / Cut) shows its first frame throughout
        return 0 <= i < n and bool(shots[i].get("hold"))

    def visible(i: int, which: str):  # the edge frame the shot really shows: a held shot's last frame is its first
        return frame(i, "first" if held(i) else which)

    for i, pk in enumerate(picks or []):
        if not isinstance(pk, dict) or not pk.get("kind") or i < 1 or i >= n:
            continue
        across_hard = hard(i) or hard(i - 1) or held(i - 1)  # out of a held shot the join is a cut (docs/TIMELINE.md)
        other_head = visible(i - 1, "last") if across_hard else visible(i, "last")
        other_tail = visible(i, "first") if across_hard else visible(i, "last")
        common = {"kind": str(pk["kind"]), "stem": str(pk.get("stem") or STEM[str(pk["kind"])]), "variant": str(pk.get("variant") or ""),
                  "index": i}
        if other_head is not None and int(pk.get("head") or 0) > 0:
            out[i] = {**(out[i] or {}), "head": {**common, "frames": int(pk["head"]), "offset": int(pk.get("tail") or 0), "other": other_head}}
        if other_tail is not None and int(pk.get("tail") or 0) > 0:
            out[i - 1] = {**(out[i - 1] or {}), "tail": {**common, "frames": int(pk["tail"]), "other": other_tail}}
    return out


def at(entry: dict | None, k: int, n: int):
    """Which half frame ``k`` of an ``n``-frame shot falls in: ``(half, u, j)`` with ``u`` in (-1, 0) over the tail and
    (0, 1) over the head (0 is the cut) and ``j`` the frame's index within the whole window, or None."""
    if not entry:
        return None
    head = entry.get("head")
    if head and k < int(head["frames"]):
        return head, (k + 0.5) / float(head["frames"]), int(head.get("offset") or 0) + k
    tail = entry.get("tail")
    if tail and k >= n - int(tail["frames"]):
        j = k - (n - int(tail["frames"]))
        return tail, -((int(tail["frames"]) - j) - 0.5) / float(tail["frames"]), j
    return None


# ------------------------------------------------------------------------------------------------ the kinds


def envelope(u: float) -> float:
    """0 at the window's edges, 1 at the cut, smooth in between."""
    v = 1.0 - min(1.0, abs(float(u)))
    return v * v * (3 - 2 * v)


def _shift(ch: np.ndarray, px: int) -> np.ndarray:
    """A channel pushed sideways by ``px`` (right when positive), the edge pixel repeated: no wrap-around."""
    if px == 0:
        return ch
    w = ch.shape[1]
    px = int(max(-w + 1, min(w - 1, px)))
    out = np.empty_like(ch)
    if px > 0:
        out[:, px:] = ch[:, :-px]
        out[:, :px] = ch[:, :1]
    else:
        out[:, :px] = ch[:, -px:]
        out[:, px:] = ch[:, -1:]
    return out


def _smear(f: np.ndarray, o: np.ndarray, strength: float, stem: float, seed: int) -> np.ndarray:
    """Blocks of the picture slide along seeded vectors, the drums pushing them; a share of the moving blocks are
    pulled from the other picture, so the next object pushes through the smear. The block order is seeded per
    boundary, so the smear grows and decays instead of flickering."""
    h, w = f.shape[:2]
    bs = max(6, min(h, w) // 40)
    gh, gw = -(-h // bs), -(-w // bs)
    rng = np.random.default_rng(int(seed) & 0x7FFFFFFF)
    score = rng.random((gh, gw))
    vec = rng.integers(-3, 4, size=(gh, gw, 2))
    k = float(strength) * (0.35 + 0.65 * float(stem))
    frac = min(1.0, 0.85 * k)
    moving = score < frac
    mag = k * 2.5 * bs / 3.0
    dy = np.where(moving, np.round(vec[..., 0] * mag), 0).astype(np.intp)
    dx = np.where(moving, np.round(vec[..., 1] * mag), 0).astype(np.intp)
    from_other = moving & (score < frac * 0.5)
    DY = np.repeat(np.repeat(dy, bs, 0), bs, 1)[:h, :w]
    DX = np.repeat(np.repeat(dx, bs, 0), bs, 1)[:h, :w]
    FO = np.repeat(np.repeat(from_other, bs, 0), bs, 1)[:h, :w]
    yy, xx = np.mgrid[0:h, 0:w]
    sy = np.clip(yy + DY, 0, h - 1)
    sx = np.clip(xx + DX, 0, w - 1)
    src = np.where(FO[..., None], o, f)
    return src[sy, sx]


def _strobe(f: np.ndarray, o: np.ndarray, a: float, stem: float, j: int) -> np.ndarray:
    """Odd frames of the window show the other picture, luma-matched to the live one (gain and offset on its mean),
    so the swap changes the content and not the brightness: the flash check (a mean-luma jump over 40) never sees it."""
    if j % 2 == 0:
        return f
    lf, lo = float(f.mean()), float(o.mean())
    g = float(np.clip(lf / max(lo, 1.0), 0.5, 2.0))
    om = np.clip(o * g + (lf - lo * g), 0, 255)
    k = float(a) * (0.7 + 0.3 * float(stem))
    return f * (1.0 - k) + om * k


def _wipe(f: np.ndarray, o: np.ndarray, env: float, amount: float, stem: float, strips: int, variant: str) -> np.ndarray:
    """The other picture enters as horizontal strips (even ones from the left, odd from the right) or a radial iris
    from the centre; the bass pushes the wipe ahead of its ramp."""
    h, w = f.shape[:2]
    pr = float(env)
    pr = min(1.0, pr + 0.25 * float(stem) * (1.0 - pr))
    yy, xx = np.mgrid[0:h, 0:w]
    if variant == "iris":
        r = np.hypot((yy - h / 2.0) / (h / 2.0), (xx - w / 2.0) / (w / 2.0)) / np.sqrt(2.0)
        m = np.clip((pr - r) / 0.06 + 0.5, 0.0, 1.0)
    else:
        n = max(2, int(strips))
        band = (yy * n) // h
        x = xx / float(max(1, w - 1))
        cover = np.where(band % 2 == 0, x, 1.0 - x)
        m = np.clip((pr - cover) / 0.02 + 0.5, 0.0, 1.0)
    m = (m * float(amount))[..., None].astype(np.float32)
    return f * (1.0 - m) + o * m


def _rip(f: np.ndarray, o: np.ndarray, env: float, amount: float, stem: float, offset: float) -> np.ndarray:
    """Red of the live picture pushed right, blue of the other pushed left, green crossed between the two; the
    offset from Intensity (``offset``, a fraction of the width), peaking at the cut and shivering with the stem."""
    w = f.shape[1]
    px = int(round(float(offset) * w * float(env) * (0.5 + 0.5 * float(stem))))
    mix = float(env) * float(amount)
    out = np.empty_like(f)
    out[..., 0] = _shift(f[..., 0], px)
    out[..., 1] = f[..., 1] * (1.0 - 0.6 * mix) + o[..., 1] * (0.6 * mix)
    out[..., 2] = _shift(f[..., 2] * (1.0 - mix) + o[..., 2] * mix, -px)
    return out


def treat(frame: np.ndarray, other: np.ndarray, kind: str, u: float, *, amount: float, stem: float = 0.5, p: dict | None = None,
          j: int = 0, seed: int = 0, variant: str = "") -> np.ndarray:
    """One frame of a boundary window: the live ``frame`` with ``other`` (the second picture) brought in by ``kind`` at
    window position ``u`` (-1 start of the tail, 0 the cut, 1 end of the head). ``amount`` 0 returns the frame
    untouched, as do the window's edges; ``stem`` (0..1) is the kind's lane; ``j`` is the frame's index within the
    window (the strobe's parity); ``seed`` fixes the smear's block field per boundary. Both HxWx3 uint8, same size."""
    if amount <= 1e-3 or kind not in KINDS or frame.shape != other.shape or frame.ndim != 3:
        return frame
    env = envelope(u)
    if env <= 1e-3:
        return frame
    p = p or {}
    s = float(np.clip(stem, 0.0, 1.0))
    f = frame.astype(np.float32)
    o = other.astype(np.float32)
    if kind == "smear":
        out = _smear(f, o, env * float(amount), s, seed)
    elif kind == "strobe":
        out = _strobe(f, o, env * float(amount), s, j)
    elif kind == "wipe":
        out = _wipe(f, o, env, float(amount), s, int(p.get("strips", 8)), variant)
    else:
        out = _rip(f, o, env, float(amount), s, float(p.get("offset", 0.02)))
    return np.clip(out, 0, 255).astype(np.uint8)
