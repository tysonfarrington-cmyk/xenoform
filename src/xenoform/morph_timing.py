"""When the change happens inside a morph: Smooth, On the beat, Snap (docs/MORPH_ENGINE_PLAN.md E2).

The cut lands every handoff on the beat, but inside a shot the morph plays at the model's own pace: the object starts to
change whenever LTX happened to start changing it. Timing re-times the cached clip so the change itself is on the music.
It measures how much each source frame differs from the one before (``progress``: the clip's cumulative change, 0 at
still A, 1 at still B), sets how far along the change each output frame should be (``target``), and plays the source
frame that is that far along. No GPU: a re-cut applies it to the morphs a cut already has.

- **Smooth**: as before, the clip at an even speed (the change wherever the model put it).
- **On the beat**: the change moves in steps, fastest on each beat inside the shot, nearly still between them.
- **Snap**: the object holds, then the whole change happens in about a beat on the shot's downbeat; on the drop it
  snaps a quarter beat in, and harder.

Every shot still starts on still A and ends on still B, so the chain stays continuous across handoffs, and the in-shot
effects (stutter, hold, skip, reverse) act on the re-timed frames as they did on the even ones. A held shot, Polly's and
your own clips are left alone. The cut has one setting (``morph_timing``); the timeline's shot overrides can give a
shot its own (``shot_overrides[i]["timing"]``).

- ``MODES``, ``LABELS``, ``NOTES``; ``normal(value)``
- ``plan(shots, mode, beats, drop, overrides)``: puts ``timing`` on each shot it applies to (the hit times, the width,
  the drift), in place; returns the count by mode
- ``progress(frames)``: the clip's cumulative change per source frame
- ``target(shot, count, fps)``: how far along the change each output frame should be
- ``indices(shot, count, progress, fps)``: the source frame (float) each output frame plays
"""
from __future__ import annotations

import numpy as np

MODES = ("smooth", "beat", "snap")
LABELS = {"smooth": "Smooth", "beat": "On the beat", "snap": "Snap"}
NOTES = {
    "smooth": "The morph plays at an even speed: the change happens wherever the model put it.",
    "beat": "The change moves in steps, fastest on every beat inside the shot, nearly still between them.",
    "snap": "The object holds, then changes in about a beat on the shot's downbeat; the drop snaps hardest.",
}
DRIFT = {"beat": 0.3, "snap": 0.12}   # the share of the travel that stays even, so a hold still breathes
WIDTH = {"beat": 0.16, "snap": 0.2}   # the logistic width of a hit, in beat periods
DROP_WIDTH = 0.1                      # the drop's snap, sharper
DROP_LAG = 0.25                       # beats after the drop before its snap (the punch lands first)


def normal(value) -> str:
    v = str(value or "").strip().lower().replace(" ", "")
    v = {"onthebeat": "beat", "beats": "beat", "even": "smooth"}.get(v, v)
    return v if v in MODES else "smooth"


def _period(beats: list[float]) -> float:
    b = sorted(float(x) for x in beats or [])
    gaps = [y - x for x, y in zip(b, b[1:]) if y - x > 0.05]
    return float(np.median(gaps)) if gaps else 0.5


def _skip(shot: dict) -> bool:
    return bool(shot.get("hold") or shot.get("performer") or shot.get("own") or shot.get("dream"))  # a dream is no morph


def plan(shots: list[dict], mode: str, beats: list[float], drop: float | None = None,
         overrides: dict | None = None) -> dict:
    """Put ``timing`` on the shots it applies to, in place: ``{"mode", "hits": [song seconds], "width": s, "drift"}``.
    ``overrides`` is the timeline's ``{index: {"timing": mode}}``. Returns ``{mode: shots}`` for the record's notes."""
    mode = normal(mode)
    beats = sorted(float(b) for b in beats or [])
    period = _period(beats)
    downbeats = beats[::4]
    counts: dict[str, int] = {}
    for i, s in enumerate(shots):
        prior = s.pop("timing", None)
        own = (overrides or {}).get(i) or (overrides or {}).get(str(i)) or {}
        # the pacing engine's per-passage timing (pacing.shape: ``{"mode"}`` alone) stands where the timeline says nothing
        preset = prior.get("mode") if isinstance(prior, dict) and not prior.get("hits") else None
        m = normal(own.get("timing")) if own.get("timing") else normal(preset) if preset else mode
        if m == "smooth" or _skip(s):
            continue
        a, b = float(s.get("start") or 0.0), float(s.get("end") or 0.0)
        dur = b - a
        if dur <= 0.2:
            continue
        width = WIDTH[m] * period
        if m == "beat":
            hits = [t for t in beats if a + 0.12 * dur < t < b - 0.08 * dur] or [a + dur / 2]
        elif (drop is not None and abs(a - float(drop)) < 0.05) or s.get("event") == "drop":
            # the drop, and with the pacing engine every drop run's first shot: a quarter beat in, and sharper
            hits, width = [a + DROP_LAG * period], DROP_WIDTH * period
        else:
            inside = [t for t in downbeats if a + 0.1 * dur < t < b - 0.1 * dur]
            near = [t for t in beats if a + 0.1 * dur < t < b - 0.1 * dur]
            hits = inside[:1] or sorted(near, key=lambda t: abs(t - (a + dur / 2)))[:1] or [a + dur / 2]
        s["timing"] = {"mode": m, "hits": [round(t, 4) for t in hits], "width": round(width, 4), "drift": DRIFT[m]}
        counts[m] = counts.get(m, 0) + 1
    return counts


def progress(frames: np.ndarray, step: int = 4) -> np.ndarray:
    """How far along its change each source frame is, 0 at the first and 1 at the last: the cumulative mean absolute
    difference from frame to frame (grey, every ``step``th pixel), kept strictly rising."""
    n = len(frames)
    if n < 2:
        return np.zeros(n, np.float64)
    grey = np.asarray(frames)[:, ::step, ::step].astype(np.float32).mean(axis=3)
    d = np.abs(np.diff(grey, axis=0)).mean(axis=(1, 2)).astype(np.float64)
    d += max(float(d.mean()) * 1e-3, 1e-6)  # a frozen stretch still counts a little, so the inverse is defined
    cum = np.concatenate([[0.0], np.cumsum(d)])
    return cum / cum[-1]


def target(shot: dict, count: int, fps: float = 24.0) -> np.ndarray | None:
    """How far along the change output frame k should be (0 at the first, 1 at the last), or None for an even play."""
    timing = shot.get("timing") or {}
    if timing.get("mode") not in ("beat", "snap") or count < 2:
        return None
    a, b = float(shot.get("start") or 0.0), float(shot.get("end") or 0.0)
    s = np.linspace(0.0, 1.0, count)
    t = a + s * (b - a)
    width = max(float(timing.get("width") or 0.08), 1.0 / float(fps))
    hits = [float(h) for h in timing.get("hits") or []] or [a + (b - a) / 2]
    steps = np.mean([1.0 / (1.0 + np.exp(-(t - h) / width)) for h in hits], axis=0)
    lo, hi = float(steps[0]), float(steps[-1])
    stepped = (steps - lo) / (hi - lo) if hi - lo > 1e-6 else s
    drift = float(timing.get("drift", 0.2))
    return drift * s + (1.0 - drift) * stepped


def indices(shot: dict, count: int, prog: np.ndarray, fps: float = 24.0) -> np.ndarray | None:
    """The source frame (float) each output frame plays so the change follows ``target``; None for an even play."""
    want = target(shot, count, fps)
    if want is None or prog is None or len(prog) < 2:
        return None
    return np.interp(want, prog, np.arange(len(prog), dtype=np.float64))
