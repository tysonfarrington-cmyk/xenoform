"""The whole song's run and its record (docs/SONG.md).

A whole song is one folder, ``work/ui/jobs/<song id>/``, so My videos lists it once it is laid together: ``song.json`` is
the record (the plan's passages with their looks and objects, every window with its Make body, its job and its status,
and later the assembly's decisions), and ``song_assemble`` writes ``xenoform.mp4`` and ``simple/simple.json`` beside it.

The windows run through the Variations machinery (``batch.Runner``): one batch, ``vary`` "song", an item a window, run one
at a time on an idle desk and an idle ComfyUI queue by the desk that queued it (its owner token). A window that fails is
queued again once; Resume queues every window not done and keeps the done ones; Stop cancels the whole. The morph cache
(``morph_cache``) answers a re-run's morphs, so a window run again renders only what it had not rendered.
"""
from __future__ import annotations

import copy
import json
import time
from datetime import datetime
from pathlib import Path

FILE = "song.json"
VERSION = 1
# the body keys the record keeps of the desk's own (the rest are the Director desk's and the other modes')
BODY_KEEP = ("audio_id", "vibe", "idea", "quality_tier", "aspect", "breathe", "drop_mode", "macros", "morph_style",
             "morph_timing", "effects", "dance_fx", "foreshadow", "backdrop", "scene_stills", "seed", "song",
             "song_morph_cap", "song_title", "song_vibes", "chain_pins", "cloud_final_ok", "beat_fx", "stem_orbit",
             "stems_path", "morph_source", "own_folder")


def path(folder: Path) -> Path:
    return Path(folder) / FILE


def load(folder: Path) -> dict | None:
    try:
        rec = json.loads(path(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) and rec.get("kind") == "song" else None


def save(folder: Path, rec: dict) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (FILE + ".part")
    tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    tmp.replace(path(folder))


def new(song: dict, *, song_id: str, body: dict, audio_id: str, audio_path: Path | str, label: str,
        beats: list | None = None) -> dict:
    """The record of a whole song about to be queued, from its plan (``song_plan.plan`` with ``pick``); ``beats`` the
    song's own, which the assembly cuts on."""
    from xenoform import taste

    windows = []
    for w in song["windows"]:
        row = {k: copy.deepcopy(v) for k, v in w.items() if k not in ("plan", "context")}
        row.update({"job_id": "", "status": "queued", "detail": "", "progress": 0.0, "attempts": 0})
        windows.append(row)
    return {
        "kind": "song", "version": VERSION, "id": song_id,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "song": {"label": label, "audio_id": audio_id, "path": str(audio_path), "duration": song["duration"],
                 "tempo": song.get("tempo"), "drop": song.get("drop"), "first_drop": song.get("first_drop"),
                 "beats": [round(float(b), 4) for b in beats or []]},
        "tier": song["tier"], "aspect": song["aspect"], "breathe": song["breathe"], "drop_mode": song["drop_mode"],
        "cap": song["cap"], "window_cap": song["window_cap"], "taste": taste.active(),
        "vibes": copy.deepcopy(song.get("vibes") or {"choice": "auto"}),
        "plan": {"morphs": song["morphs"], "shots": song["shots"], "line": song["line"], "steps": song.get("steps"),
                 "bar_phase": song.get("bar_phase"), "period": song.get("period")},
        "title": dict(song.get("title") or {}), "estimate": song.get("estimate") or {},
        "passages": copy.deepcopy(song["passages"]), "windows": windows,
        "body": {k: copy.deepcopy(body.get(k)) for k in BODY_KEEP if k in body},
        "batch": "", "status": "queued", "assembly": None,
    }


def items(rec: dict) -> list[dict]:
    """The record's windows as the batch's items: a label the Variations page shows, the Make body, the window."""
    out = []
    for w in rec["windows"]:
        p = rec["passages"][w["passage"]]
        look = p.get("look") or {}
        part = f" (part {w['part'] + 1} of {w['parts']})" if w.get("parts", 1) > 1 else ""
        label = (f"The whole song in your clips: {len(rec['passages'])} passages" if w.get("whole") else
                 f"Passage {p['index'] + 1} of {len(rec['passages'])}{part}: {p['role']}, {look.get('name') or look.get('vibe') or ''}")
        out.append({"label": label, "body": copy.deepcopy(w["body"]), "kind": "window", "window": w["index"]})
    return out


def sync(rec: dict, batch: dict | None) -> dict:
    """The windows' jobs, statuses and progress from the batch (the queue's truth), in place; returns ``rec``."""
    if not batch:
        return rec
    by = {int(i.get("window", i.get("k", -1))): i for i in batch.get("items") or []}
    for w in rec["windows"]:
        item = by.get(int(w["index"]))
        if item is None:
            continue
        for key in ("job_id", "status", "detail", "progress", "took_s", "eta_s", "attempts", "failed", "started_at",
                    "finished_at"):
            if key in item:
                w[key] = copy.deepcopy(item[key])
    return rec


def counts(rec: dict) -> dict:
    wins = rec["windows"]
    done = [w for w in wins if w.get("status") == "done"]
    return {"done": len(done), "of": len(wins), "morphs": sum(int(w.get("morphs") or 0) for w in wins),
            "morphs_done": sum(int(w.get("morphs") or 0) for w in done),
            "open": sum(1 for w in wins if w.get("status") in ("queued", "waiting", "running")),
            "failed": sum(1 for w in wins if w.get("status") == "error"),
            "stopped": sum(1 for w in wins if w.get("status") in ("stopped", "cancelled"))}


def status_of(rec: dict, assembling: bool = False) -> str:
    """queued (nothing started yet), running (a window renders or waits its turn), assembling, done (laid together),
    ready (every window done, not laid together yet), stopped (stopped before the end), failed (a window failed twice,
    or the assembly failed)."""
    c = counts(rec)
    if assembling:
        return "assembling"
    if (rec.get("assembly") or {}).get("video") and c["done"] == c["of"]:
        return "done"
    if c["open"]:
        return "running" if any(w.get("status") in ("running", "waiting") or w.get("job_id") for w in rec["windows"]) \
            or c["done"] else "queued"
    if c["done"] == c["of"]:
        return "failed" if (rec.get("assembly") or {}).get("error") else "ready"
    if c["failed"]:
        return "failed"
    return "stopped"


def ready(rec: dict) -> bool:
    c = counts(rec)
    return c["of"] > 0 and c["done"] == c["of"]


def view(rec: dict, *, assembling: dict | None = None, elsewhere: bool = False) -> dict:
    """The song as the desk shows it: where the run is (n of m windows, the one rendering), the passages with their
    looks, objects and jobs, the estimate, and the video once it is laid together."""
    c = counts(rec)
    st = status_of(rec, bool(assembling))
    running = next((w for w in rec["windows"] if w.get("status") == "running"), None) or \
        next((w for w in rec["windows"] if w.get("status") == "waiting"), None)
    passages = []
    for p in rec["passages"]:
        look = p.get("look") or {}
        wins = [rec["windows"][k] for k in p.get("windows") or []]
        passages.append({"index": p["index"], "role": p["role"], "start": p["start"], "end": p["end"],
                         "seconds": p.get("seconds"), "heat": p.get("heat"), "main": bool(p.get("main")),
                         "vibe": look.get("vibe") or "", "name": look.get("name") or look.get("vibe") or "",
                         "preset": look.get("preset") or "", "why": look.get("why") or "", "objects": p.get("objects") or [],
                         "morphs": p.get("morphs"),
                         "windows": [{"index": w["index"], "job_id": w.get("job_id") or "", "status": w.get("status") or "queued",
                                      "progress": w.get("progress"), "detail": w.get("detail") or "",
                                      "took_s": w.get("took_s"), "morphs": w.get("morphs")} for w in wins]})
    assembly = rec.get("assembly") or {}
    out = {"id": rec["id"], "status": st, "label": (rec.get("song") or {}).get("label") or "", "line": (rec.get("plan") or {}).get("line"),
           "tier": rec.get("tier"), "aspect": rec.get("aspect"), "breathe": rec.get("breathe"), "drop_mode": rec.get("drop_mode"),
           "vibes": rec.get("vibes") or {"choice": "auto"},
           "created": rec.get("created"), "batch": rec.get("batch") or "", "elsewhere": bool(elsewhere),
           **c, "passages": passages, "estimate": rec.get("estimate") or {}, "title": rec.get("title") or {},
           "assembly": {k: assembly.get(k) for k in ("video", "seconds", "made", "error", "cuts", "loudness", "tame", "qa")
                        if assembly.get(k) is not None}}
    if running is not None:
        p = rec["passages"][running["passage"]]
        out["running"] = {"window": running["index"], "passage": p["index"],
                          "role": "the whole song" if running.get("whole") else p["role"],
                          "vibe": (p.get("look") or {}).get("vibe") or "", "status": running.get("status"),
                          "progress": running.get("progress"), "detail": running.get("detail") or "",
                          "eta_s": running.get("eta_s"), "job_id": running.get("job_id") or ""}
    if assembling:
        out["assembling"] = {k: assembling.get(k) for k in ("progress", "detail", "started") if k in assembling}
    if st == "done":
        out["video"] = f"/api/videos/{rec['id']}/video"
    left = [w for w in rec["windows"] if w.get("status") not in ("done",)]
    morphs_left = sum(int(w.get("morphs") or 0) for w in left)
    done = [w for w in rec["windows"] if w.get("status") == "done" and w.get("took_s")]
    if done:  # the pace this song has kept so far (each window's own time over its morphs), then the assembly
        per = sum(float(w["took_s"]) for w in done) / max(1, sum(int(w.get("morphs") or 0) for w in done))
        out["left_s"] = round(per * morphs_left + (90.0 if morphs_left else 0.0), 1)
    else:
        est = ((rec.get("estimate") or {}).get("tiers") or {}).get(rec.get("tier") or "draft") or {}
        total = float(est.get("seconds") or 0.0)
        if total and c["morphs"]:
            out["left_s"] = round(total * morphs_left / max(1, c["morphs"]), 1)
    return out


def stamp(rec: dict, **fields) -> dict:
    rec.update(fields)
    rec["updated"] = time.time()
    return rec
