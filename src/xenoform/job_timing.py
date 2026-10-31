"""Honest job timing for the desk.

The pipeline reports raw ``(stage, frac, detail)`` triples on scales of their own (the Draft morphs run 0.1-0.55,
compose 0.6-0.95, and the end card and the save said nothing), so the desk's bar sat at 95 % for minutes and the
whole-run time never survived a restart. This module folds those reports onto one fixed order of canonical phases,
weights each phase by the seconds ``dense.plan_summary`` planned for it, keeps an overall fraction that never goes
backwards and an ETA that trusts the measured pace once a phase is a tenth in, and at the end writes the per-phase
breakdown to ``took.json`` beside the cut. Pure functions over the job dict, so the desk (ui._start_job,
ui._run_job) and the tests share one set of arithmetic."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("xenoform")

PHASES = ("analyze", "draft", "morphs", "performer", "cut", "card", "save", "qa", "done")
_ORDER = {p: i for i, p in enumerate(PHASES)}

# The raw progress range each phase's reports span (cloud_morph._local_clips and final_tier.final_clips for the
# morphs, upscale_pass after the Draft morphs for Fast Final, cloud_final.cloud_clips for Cloud Final, dense.run_simple's
# performer slots, beatfx.compose for the cut); ``stage_frac`` normalises into it, picking the morphs range by the Make's tier.
RANGES: dict[str, Any] = {"morphs": {"draft": (0.1, 0.55), "fast": (0.1, 0.58), "final": (0.12, 0.87), "cloud": (0.12, 0.82)},
                          "performer": (0.5, 0.6), "cut": (0.6, 0.95)}
# The end card burn and the save report once, as they start: each is 0 % done until the next phase begins.
_SINGLE_SHOT = {"card", "save"}
# The bar still moves on these shares when plan_summary could not run (no features yet, an odd body).
FALLBACK_WEIGHTS = {"analyze": 0.03, "draft": 0.02, "morphs": 0.45, "performer": 0.25, "cut": 0.20,
                    "card": 0.01, "save": 0.01, "qa": 0.03}
# Seconds for the phases the GPU plan does not cover, on the 12 GB desk: the song is usually analysed already (the
# desk did it on load), the stills draft is one 12 fps ffmpeg pass, the end card re-encodes the last two seconds, the
# save is a copy, and QA decodes the finished cut three times (lag, artifacts, cut times).
FIXED_S = {"analyze": 3.0, "draft": 6.0, "card": 4.0, "save": 1.0}
QA_BASE_S, QA_S_PER_SONG_S = 4.0, 0.12
RATE_AFTER = 0.1         # once a phase is this far in, its measured pace replaces the plan...
RATE_CLAMP = (0.5, 4.0)  # ...within this range of the plan, so one slow morph cannot swing the ETA by an hour


# ------------------------------------------------------------------ mapping
def phase_for(stage: str, detail: str = "", current: str | None = None) -> str:
    """The canonical phase a raw report belongs to, never earlier than ``current`` (turbo says "restyle 1.0" after
    the whole cut is composed; that stays in whatever phase the cut had reached)."""
    s, d = str(stage or "").lower(), str(detail or "").lower()
    if s == "done":
        phase = "done"
    elif s == "qa":
        phase = "qa"
    elif s == "analyze":
        phase = "analyze"
    elif s == "animatic":
        phase = "draft"
    elif s == "restyle":
        phase = "performer" if "performer" in d else "cut" if "your clip" in d else "morphs"
    elif s == "assemble":
        if "burning the end card" in d:
            phase = "card"
        elif "saving the video" in d:
            phase = "save"
        else:  # the stills draft locks with an "assemble" before any morph; after the morphs an assemble is the cut
            phase = "draft" if current is None or _ORDER[current] < _ORDER["morphs"] else "cut"
    elif s in {"render", "cloud"}:  # the full desk's beauty pass and the paid cloud pass: GPU time, like the morphs
        phase = "morphs"
    else:
        phase = current or "analyze"
    if current is not None and _ORDER[phase] < _ORDER[current]:
        phase = current
    return phase


def stage_frac(phase: str, frac: float, tier: str = "draft", detail: str = "") -> float:
    """The raw fraction normalised to the phase's own range and clamped to [0, 1]."""
    if phase == "done":
        return 1.0
    if phase in _SINGLE_SHOT:
        return 0.0
    rng = RANGES.get(phase)
    if isinstance(rng, dict):  # the Make's tier picks the range; a "Final: ..." report is the Final's whatever the tier says
        key = "final" if str(detail).lower().startswith("final") else str(tier or "draft").lower()
        rng = rng.get(key, rng["draft"])
    value = float(frac or 0.0)
    if rng:
        lo, hi = rng
        value = (value - lo) / (hi - lo)
    return max(0.0, min(1.0, value))


# ------------------------------------------------------------------ plan
def plan_for(features: dict | None, body: dict | None, audio_path=None) -> dict[str, float] | None:
    """Planned seconds per phase for this Make from ``dense.plan_summary`` (the same estimate /api/simple/options
    shows), or None when the song or the body cannot be planned. With the song's sections the plan is the Make's own
    (``dense.shots_for`` and its chain), and ``audio_path`` gives it the song's drop, so the clock counts the morphs
    the cut will render."""
    body, features = body or {}, features or {}
    try:
        from xenoform import dense

        duration = float(features.get("duration") or body.get("duration") or 0.0)
        length_s = float(body.get("length_s") or 0.0)
        if length_s > 0 and duration > 0:
            duration = min(duration, length_s)  # the cut, not the whole song, is what renders
        if duration <= 0:
            return None
        opt = dense.options(body)
        beats = [float(b) for b in (features.get("beats") or []) if float(b) < duration]
        sections = dense._analysis_sections(features) if float(features.get("duration") or 0.0) <= duration + 0.5 else []
        drop = dense.find_drop(audio_path, beats, duration) if audio_path and sections else None
        pool = None
        try:  # the vibe's pool caps the morphs (no object twice), so the estimate counts it
            from xenoform import morph_pass as _mp
            from xenoform import taste as _taste

            cat = _mp.catalogue()
            pool_vibe, asked = _mp.vibe_for(body), str(body.get("vibe") or "")
            rows = list(cat.get(pool_vibe) or []) + (list(cat.get(asked) or []) if asked and asked != pool_vibe else [])
            pool = len(_taste.usable(rows))  # as the Make counts it: the taste file's bans off first
        except Exception:
            pool = None
        # options() folds Fast and Cloud into tier "draft" with a flag; the plan wants the real tier (its cost and cap)
        tier = "cloud" if opt["cloud"] else "fast" if opt["fast"] else opt["tier"]
        summary = dense.plan_summary(duration, beats, opt["energy"], tier, opt["aspect"], opt["vertical"], drop=drop,
                                     performer=int(opt.get("performer") or 0), pool=pool,
                                     sections=sections or None, state=body if sections else None)
        est = summary.get("estimate") or {}
        plan = {"analyze": FIXED_S["analyze"], "draft": FIXED_S["draft"],
                "morphs": float(est.get("gpu_seconds") or 0.0),
                "performer": float(est.get("performer_seconds") or 0.0),
                "cut": float(est.get("look_seconds") or 0.0),
                "card": FIXED_S["card"] if opt.get("end_card") else 0.0,
                "save": FIXED_S["save"],
                "qa": QA_BASE_S + QA_S_PER_SONG_S * duration}
        if str(body.get("mode") or "") == "stems":  # every layer is a cut of its own, then the composite
            from xenoform import stems_mode

            plan = stems_mode.timing(plan, body, duration)
    except Exception as exc:  # a plan is a courtesy; the fallback weights still move the bar
        log.debug("job plan skipped: %s", exc)
        return None
    return {k: round(max(0.0, v), 1) for k, v in plan.items()}


def weights_for(plan: dict[str, float] | None, *, performer: bool = False) -> dict[str, float]:
    """Each phase's share of the run (they sum to 1): the planned seconds, else the fixed fallback shares with the
    performer phase only when performer shots are on."""
    if plan:
        secs = {p: max(0.0, float(plan.get(p) or 0.0)) for p in PHASES if p != "done"}
    else:
        secs = {p: w for p, w in FALLBACK_WEIGHTS.items() if p != "performer" or performer}
    total = sum(secs.values()) or 1.0
    out = {p: secs.get(p, 0.0) / total for p in PHASES if p != "done"}  # exact, so the shares sum to one
    out["done"] = 0.0
    return out


def start_fields(plan: dict[str, float] | None, body: dict | None = None) -> dict[str, Any]:
    """The timing fields a new job dict carries. ``eta_s`` opens on the planned total so the desk can say "about
    12 min" before the first report; it is None when nothing could be planned."""
    body = body or {}
    try:
        performer = int(float(body.get("performer") or 0)) > 0
    except (TypeError, ValueError):
        performer = False
    tier = str(body.get("quality_tier") or "draft").lower()
    return {"t0": time.monotonic(), "started": time.time(), "stages": [], "elapsed_s": 0.0, "overall": 0.0,
            "eta_s": round(sum(plan.values()), 1) if plan else None,
            "timing": {"plan": plan, "weights": weights_for(plan, performer=performer), "tier": tier,
                       "phase": None, "phase_at": 0.0, "stage_frac": 0.0}}


def elapsed(job: dict) -> float:
    """Seconds since the job dict was made (0 for a job without ``t0``, such as a re-cut record)."""
    t0 = job.get("t0")
    return max(0.0, time.monotonic() - float(t0)) if t0 else 0.0


# ------------------------------------------------------------------ progress
def eta(plan: dict[str, float] | None, phase: str, frac: float, in_phase: float) -> float | None:
    """Seconds left: the phases still to come at plan, plus the rest of this one at the plan's pace or, once the
    phase is ``RATE_AFTER`` in, at the measured pace (``in_phase / frac``, clamped to ``RATE_CLAMP`` of plan).
    None without a plan, 0 at done."""
    if phase == "done":
        return 0.0
    if not plan:
        return None
    cur = float(plan.get(phase) or 0.0)
    if cur > 0 and frac >= RATE_AFTER and in_phase > 0:
        cur = max(RATE_CLAMP[0] * cur, min(RATE_CLAMP[1] * cur, in_phase / frac))
    rest = sum(float(plan.get(p) or 0.0) for p in PHASES[_ORDER[phase] + 1:])
    return round(rest + (1.0 - frac) * cur, 1)


def tick(job: dict, stage: str, frac: float, detail: str, now: float) -> dict:
    """Fold one raw progress report, ``now`` seconds into the run, into the job's timing fields (``elapsed_s``,
    ``stages``, ``overall``, ``eta_s``). ``overall`` never goes backwards; a phase's fraction never does either."""
    t = job.get("timing")
    if not isinstance(t, dict):
        t = job["timing"] = {"plan": None, "weights": weights_for(None), "tier": "draft", "phase": None, "phase_at": 0.0,
                             "stage_frac": 0.0}
    now = max(0.0, float(now))
    job["elapsed_s"] = round(now, 1)
    prev = t.get("phase")
    phase = phase_for(stage, detail, prev)
    frac_now = stage_frac(phase, frac, str(t.get("tier") or "draft"), detail)
    if phase != prev:
        t["phase"], t["phase_at"], t["stage_frac"] = phase, now, frac_now
        job.setdefault("stages", []).append({"phase": phase, "at": round(now, 1)})
    else:
        frac_now = max(float(t.get("stage_frac") or 0.0), frac_now)
        t["stage_frac"] = frac_now
    weights = t.get("weights") or weights_for(None)
    before = sum(float(weights.get(p, 0.0)) for p in PHASES[: _ORDER[phase]])
    overall = 1.0 if phase == "done" else before + float(weights.get(phase, 0.0)) * frac_now
    job["overall"] = round(max(float(job.get("overall") or 0.0), min(1.0, overall)), 4)
    job["eta_s"] = eta(t.get("plan"), phase, frac_now, now - float(t.get("phase_at") or 0.0))
    return job


def breakdown(stages: list[dict], took_s: float) -> dict[str, float]:
    """Seconds per phase from the stage boundaries: the first phase owns the run-up before its first report, the
    last runs to ``took_s``, so the parts sum to the whole (within rounding)."""
    out: dict[str, float] = {}
    real = [s for s in stages if s.get("phase") != "done"]
    for i, s in enumerate(real):
        start = 0.0 if i == 0 else float(s.get("at") or 0.0)
        end = float(real[i + 1].get("at") or 0.0) if i + 1 < len(real) else float(took_s)
        out[str(s["phase"])] = round(out.get(str(s["phase"]), 0.0) + max(0.0, end - start), 1)
    return out


def finish(job: dict, now: float) -> dict[str, Any]:
    """Close the run ``now`` seconds in: the done phase, overall 1.0, ``took_s`` (the whole run, QA included) and the
    per-phase ``breakdown``. Returns the record ``write_took`` saves."""
    tick(job, "done", 1.0, str(job.get("detail") or ""), now)
    took = round(max(0.0, float(now)), 1)
    job["took_s"] = took
    job["breakdown"] = breakdown(job.get("stages") or [], took)
    return {"took_s": took, "breakdown": job["breakdown"], "stages": list(job.get("stages") or []),
            "started": job.get("started")}


# ------------------------------------------------------------------ on disk
def write_took(folder: Path, record: dict) -> Path | None:
    """``took.json`` beside the cut, so My videos keeps the numbers after a desk restart."""
    path = Path(folder) / "took.json"
    try:
        path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    except OSError as exc:
        log.warning("took.json not written: %s", exc)
        return None
    return path


def seconds_for(folder: Path, job: dict | None = None) -> float | None:
    """How long the cut in ``folder`` took: the live job, then took.json, then the older manifests (turbo.json,
    simple/simple.json), then the file's age against meta.json's ``created``; None when nothing says."""
    if job and job.get("took_s"):
        return round(float(job["took_s"]), 1)
    folder = Path(folder)
    for rel, key in (("took.json", "took_s"), ("turbo.json", "seconds"), ("simple/simple.json", "seconds")):
        try:
            value = (json.loads((folder / rel).read_text(encoding="utf-8")) or {}).get(key)
        except (OSError, ValueError, AttributeError):
            continue
        if value:
            return round(float(value), 1)
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8")) or {}
        created = datetime.fromisoformat(str(meta.get("created"))).timestamp()
        delta = (folder / "xenoform.mp4").stat().st_mtime - created
    except (OSError, ValueError, TypeError, AttributeError):
        return None
    return round(delta, 1) if delta > 0 else None
