"""Perform (docs/UI_REVIEW.md 6.5): what the live page needs from the desk.

``/vj`` is one page in two windows: the control view, and the output window (``/vj?out=1``) that renders and records.
This router gives the page

- a finished cut to play (``/vj?job=<id>``): the cut's clips as the first scenes, its song, its stems, and the song's
  passages, beats, bars and drop as the cut's record keeps them (``lane.build``), so the strip, the now/next readout and
  "follow the song" are the cut's own and not the browser's BPM guess (V1, V11);
- the strip of a track loaded on the page, in the shape of the desk's ``/api/simple/strip`` (the page asks that route
  first; this one stands in where the desk does not have it);
- the live takes (decision 12): a recording sent in chunks while it runs, so a crash loses seconds and not the set (V7),
  then remuxed to an mp4 beside its webm in ``work/ui/takes/<id>/``, where ``/api/videos`` and My videos list it.

Take ids are ten hex characters; a cut id is a job folder name (``ui.storage_id``). Nothing here touches the GPU.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

log = logging.getLogger(__name__)
router = APIRouter()

AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a", ".aac", ".opus"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv"}
STALE_S = 30.0         # a take still "recording" with no chunk for this long was cut short (a crash, a closed window)
MAX_CHUNK = 64 << 20   # one chunk; a second of 24 Mbps video is 3 MB
MAX_TAKES = 200        # how many takes a listing reads
_TAKE_RE = re.compile(r"[0-9a-f]{10}")
_TAKE_LOCK = threading.Lock()  # one writer per take file at a time (chunks arrive one by one, finish runs once)
_FINISHING: set[str] = set()


def _ui():
    from xenoform import ui

    return ui


# ---------------------------------------------------------------- the cut: /vj?job=<id>
def _job_folder(job_id: str) -> Path:
    ui = _ui()
    folder = ui.work_dir() / "jobs" / ui.storage_id(job_id, fallback="")
    if not (folder / "xenoform.mp4").is_file():
        raise HTTPException(404, "That cut is not on this machine.")
    return folder


def _record(folder: Path) -> dict:
    path = folder / "simple" / "simple.json"
    if not path.is_file():
        return {}
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


def _clip_path(folder: Path, raw) -> Path | None:
    """A clip of the cut: the file of that name in the cut's own ``simple/`` folder (a cut copied from another desk keeps
    its clips there), else the path the record names when it is a video on this machine."""
    text = str(raw or "")
    if not text:
        return None
    local = folder / "simple" / Path(text).name
    if local.is_file():
        return local
    path = Path(text)
    return path if path.suffix.lower() in VIDEO_SUFFIXES and path.is_file() else None


def _song_path(folder: Path, info: dict) -> Path | None:
    """The cut's song: the audio the record names (a Length cut's trimmed window), else the desk's file for the cut's
    audio id; None when neither is on this machine (the route then plays the cut's own soundtrack)."""
    raw = str(info.get("audio_path") or "")
    if raw:
        path = Path(raw)
        if path.suffix.lower() in AUDIO_SUFFIXES and path.is_file():
            return path
    ui = _ui()
    audio_id = str(ui._read_meta(folder).get("audio_id") or "")
    if audio_id and audio_id != "demo":
        with ui._LOCK:
            found = ui._AUDIO.get(audio_id)
        if found is not None and Path(found).is_file():
            return Path(found)
    return None


def _stems_file(info: dict, song: Path | None) -> Path | None:
    raw = str(info.get("stems_path") or "")
    if raw:
        path = Path(raw)
        if path.name == "stems.json" and path.is_file():
            return path
    if song is not None:
        try:
            from xenoform import stems_api

            return stems_api.stems_path_for(song)
        except Exception:  # an unreadable song or a stems cache that cannot be made: the page splits bands itself
            log.exception("stems for the cut")
    return None


def _bar_phase(beats: list[float], anchor: float | None) -> int:
    """Which beat of four is the downbeat: the drop lands on one, so the beat nearest the drop starts a bar."""
    if not beats or anchor is None:
        return 0
    k = min(range(len(beats)), key=lambda i: abs(beats[i] - float(anchor)))
    return k % 4


def _tempo(beats: list[float]) -> float:
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    return round(60.0 / gaps[len(gaps) // 2], 1) if gaps else 0.0


def _strip_passages(audio_id: str, window, duration: float) -> list[dict]:
    """The passages the desk's strip shows for the cut's song (``perform_song``), on the cut's clock: shifted by the
    window's start when the song is the whole one (an upload trimmed for the Make is analysed as its own stretch, from
    0) and clipped to the cut. Empty when the desk has not analysed that song."""
    if not audio_id or duration <= 0:
        return []
    try:
        strip = perform_song(audio_id, buckets=60)
    except Exception:  # an upload the desk forgot when it restarted: beats only, as before
        return []
    win = window if isinstance(window, dict) else {}
    try:
        start = float(win.get("song_start") or 0.0)
    except (TypeError, ValueError):
        start = 0.0
    if start + duration > float(strip.get("duration") or 0.0) + 0.5:  # the song held is the cut's own stretch
        start = 0.0
    out = []
    for row in strip.get("passages") or []:
        a, b = max(0.0, float(row["start"]) - start), min(duration, float(row["end"]) - start)
        if b - a < 0.05:
            continue
        p = {"role": str(row.get("role") or ""), "start": round(a, 3), "end": round(b, 3)}
        if row.get("drop_run") is not None:
            p.update({"drop_run": int(row["drop_run"]), "heat": float(row.get("heat") or 0.0)})
        out.append(p)
    return out


@router.get("/api/perform/job/{job_id}")
def perform_job(job_id: str) -> dict:
    """Everything ``/vj?job=<id>`` plays: the cut's clips (each with the object it lands on, for the pads), its shots on
    the song's clock with the clip each plays and the speed it plays at, the passages, beats, bars and drop, the stills,
    the song and the stems envelopes. Read-only."""
    from xenoform import lane

    ui = _ui()
    folder = _job_folder(job_id)
    info = _record(folder)
    meta = ui._read_meta(folder)
    base = f"/api/perform/job/{folder.name}"
    out: dict = {"id": folder.name, "title": str(meta.get("song") or ""), "vibe": str(meta.get("vibe") or info.get("vibe") or ""),
                 "aspect": str(meta.get("aspect") or info.get("aspect") or "16:9"), "video": f"/api/videos/{folder.name}/video",
                 "song": f"{base}/song", "stems": None, "duration": 0.0, "tempo": 0.0, "drop": None, "bar_phase": 0,
                 "clips": [], "shots": [], "passages": [], "beats": [], "bars": [], "stills": [], "note": ""}
    if not info:
        out["note"] = "This cut has no shot record, so Perform plays the library loops to its song."
        return out
    mode = str(info.get("mode") or "")
    try:
        built = lane.build(info, folder.name)
    except Exception:  # an older record lane.build cannot read: the song still plays, with the library loops
        log.exception("perform lane %s", folder.name)
        built = {}
    rows = list(built.get("shots") or [])
    raw_shots = [s for s in (info.get("shots") or []) if isinstance(s, dict)]
    clip_files = list(info.get("clips") or []) if mode not in ("stems", "song") else []
    clip_ok = [_clip_path(folder, c) is not None for c in clip_files]
    seconds = {}  # a clip's length in seconds, from the shot record (render_s) or 4 s, for a speed the record lacks
    clips = []
    for k in range(len(clip_files)):
        clips.append({"index": k, "url": f"{base}/clip/{k}" if clip_ok[k] else None, "name": f"clip {k + 1}", "to": "", "from": ""})
    shots = []
    for i, r in enumerate(rows):
        s = raw_shots[i] if i < len(raw_shots) else {}
        try:
            k = int(s.get("clip", i))
        except (TypeError, ValueError):
            k = i
        if not 0 <= k < len(clips):
            k = None
        span = max(0.04, float(r.get("end") or 0.0) - float(r.get("start") or 0.0))
        try:
            speed = float(s.get("speed") or 0.0)
        except (TypeError, ValueError):
            speed = 0.0
        if speed <= 0:
            speed = float(s.get("render_s") or seconds.get(k) or 4.0) / span
        row = {"index": i, "start": r.get("start", 0.0), "end": r.get("end", 0.0), "section": r.get("section", ""),
               "from": r.get("from", ""), "to": r.get("to", ""), "clip": k, "speed": round(max(0.05, min(8.0, speed)), 4),
               "handoff": r.get("handoff", "morph")}
        for key in ("drop_run", "heat", "dropped", "hold", "event"):
            if r.get(key) is not None:
                row[key] = r[key]
        shots.append(row)
        if k is not None and not clips[k]["to"]:  # a clip is named for the first shot that plays it
            clips[k].update({"name": " → ".join(x for x in (r.get("from"), r.get("to")) if x) or clips[k]["name"],
                             "to": r.get("to", ""), "from": r.get("from", "")})
    beats = [float(b) for b in (built.get("beats") or info.get("beats") or [])]
    drop = info.get("drop")
    try:
        drop = round(float(drop), 3) if drop is not None else None
    except (TypeError, ValueError):
        drop = None
    passages = []
    for sec in built.get("sections") or []:
        p = {"role": str(sec.get("section") or ""), "start": sec.get("start", 0.0), "end": sec.get("end", 0.0)}
        if sec.get("drop_run") is not None:
            p.update({"drop_run": int(sec["drop_run"]), "heat": float(sec.get("heat") or 0.0)})
        passages.append(p)
    if not passages and mode not in ("stems", "song"):  # a plan whose shots name no passage (the bundled demo's): the strip's
        passages = _strip_passages(str(meta.get("audio_id") or ""), info.get("window"), float(built.get("duration") or 0.0))
    runs = [p for p in passages if "drop_run" in p]
    if runs:  # the main run: the one the song's drop opens, else the hottest
        main = next((p for p in runs if drop is not None and float(p["start"]) - 0.01 <= drop < float(p["end"])), None) \
            or max(runs, key=lambda p: (p.get("heat") or 0.0, float(p["end"]) - float(p["start"])))
        main["main"] = True
    anchor = drop if drop is not None else (float(runs[0]["start"]) if runs else None)
    phase = _bar_phase(beats, anchor)
    song = _song_path(folder, info)
    stills = []
    for st in built.get("stills") or []:
        f = str(st.get("file") or "")
        if f and not Path(f).is_absolute():
            stills.append({"index": st.get("index"), "noun": st.get("noun", ""), "url": f"/api/stills/thumb?file={f}"})
    out.update({"duration": round(float(built.get("duration") or 0.0), 3), "tempo": _tempo(beats), "drop": drop,
                "bar_phase": phase, "beats": [round(b, 3) for b in beats], "bars": [round(b, 3) for b in beats[phase::4]],
                "clips": clips, "shots": shots, "passages": passages, "stills": stills,
                "stems": f"{base}/stems.json" if _stems_file(info, song) is not None else None,
                "window": info.get("window") if isinstance(info.get("window"), dict) else None})
    if not any(c["url"] for c in clips):
        out["note"] = ("A whole song or a stems cut keeps its clips in its passages' cuts, so Perform plays the library loops to it."
                       if mode in ("stems", "song") else "This cut's clips are not on this machine, so Perform plays the library loops to it.")
    return out


@router.get("/api/perform/job/{job_id}/clip/{n}")
def perform_clip(job_id: str, n: int) -> FileResponse:
    folder = _job_folder(job_id)
    clips = list(_record(folder).get("clips") or [])
    path = _clip_path(folder, clips[n]) if 0 <= n < len(clips) else None
    if path is None:
        raise HTTPException(404, "That clip is not on this machine.")
    return FileResponse(path, media_type="video/mp4")


@router.get("/api/perform/job/{job_id}/song")
def perform_song_file(job_id: str) -> FileResponse:
    """The cut's song; a cut whose song file is gone plays its own soundtrack, copied out of its mp4 once."""
    from xenoform.video import ffmpeg_bin

    folder = _job_folder(job_id)
    song = _song_path(folder, _record(folder))
    if song is not None:
        return FileResponse(song)
    dest = _ui().work_dir() / "perform" / f"{folder.name}-song.m4a"
    src = folder / "xenoform.mp4"
    if not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part.m4a")
        for codec in (["-c:a", "copy"], ["-c:a", "aac", "-b:a", "192k"]):
            try:
                subprocess.run([ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(src), "-vn", *codec, str(tmp)],
                               check=True, capture_output=True, timeout=120)
                tmp.replace(dest)
                break
            except (subprocess.SubprocessError, OSError):
                continue
        else:
            raise HTTPException(404, "This cut has no song on this machine.")
    return FileResponse(dest, media_type="audio/mp4")


@router.get("/api/perform/job/{job_id}/stems.json")
def perform_stems(job_id: str) -> FileResponse:
    folder = _job_folder(job_id)
    info = _record(folder)
    path = _stems_file(info, _song_path(folder, info))
    if path is None:
        raise HTTPException(404, "This cut's stems are not on this machine.")
    return FileResponse(path, media_type="application/json")


# ---------------------------------------------------------------- a track's strip (the desk's /api/simple/strip shape)
@router.get("/api/perform/song/{audio_id}")
def perform_song(audio_id: str, buckets: int = 600) -> dict:
    """The song strip of a track the desk has analysed (``/api/analyze``, a bundled song, the demo): its passages with
    roles, drop runs and heat as the whole-song planner reads them (``pacing.song_plan``), the beats on the planner's
    grid with the bar downbeats, a waveform and the drop. The same shape as ``/api/simple/strip``; read-only."""
    from xenoform import dense as _dense
    from xenoform import pacing as _pacing
    from xenoform.director import waveform_peaks

    ui = _ui()
    audio_id = ui.storage_id(audio_id)
    if audio_id == "demo":
        features, audio = ui._demo_features(), ui.repo_root() / "examples" / "demo.wav"
    else:
        with ui._LOCK:
            features, audio = ui._FEATURES.get(audio_id), ui._AUDIO.get(audio_id)
    if not features:
        raise HTTPException(404, "The desk has not analysed that song (it forgets uploads when it restarts). Load it again.")
    duration = float(features.get("duration") or 0.0)
    beats = sorted(float(b) for b in features.get("beats") or [])
    try:
        drop = _dense.find_drop(Path(audio), beats, duration) if audio is not None and Path(audio).is_file() else None
    except Exception:
        drop = None
    sections = _dense._analysis_sections(features)
    tempo = features.get("tempo")
    grid = _pacing.grid_for(beats, duration, tempo) if duration > 0 else []
    passages: list[dict] = []
    phase = 0
    if duration > 0 and len(sections) >= 2:
        try:
            plan = _pacing.song_plan(duration, beats, sections, drop, breathe=0.0, drop_mode="auto", tempo=tempo)
            phase = int(plan.get("bar_phase") or 0)
            for p in plan.get("passages") or []:
                row = {"role": str(p["role"]), "start": round(float(p["start"]), 3), "end": round(float(p["end"]), 3)}
                if "drop_run" in p:
                    row.update({"drop_run": int(p["drop_run"]), "heat": round(float(p.get("heat") or 0.0), 3), "opens": bool(p.get("main"))})
                passages.append(row)
        except Exception:
            log.exception("perform song strip")
            passages = []
    if not passages and duration > 0:
        passages = [{"role": "sustain", "start": 0.0, "end": round(duration, 3)}]
    runs = [p for p in passages if "drop_run" in p]
    k = _pacing.heaviest([{"heat": p.get("heat"), "start": p["start"], "end": p["end"], "opens": p.get("opens")} for p in runs])
    if k is not None:
        runs[k]["main"] = True
    return {"audio_id": audio_id, "duration": round(duration, 3), "tempo": round(float(tempo or 0.0), 1),
            "beats": [round(t, 3) for t in grid], "bars": [round(t, 3) for t in grid[phase::4]] if len(grid) >= 4 else [],
            "bar_phase": phase, "drop": round(float(drop), 3) if drop is not None else None, "passages": passages,
            "wave": waveform_peaks(features, max(60, min(4000, int(buckets or 600)))) if features.get("frames") else []}


# ---------------------------------------------------------------- live takes
def takes_root() -> Path:
    path = _ui().work_dir() / "takes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _take_dir(take_id: str) -> Path:
    if not _TAKE_RE.fullmatch(str(take_id or "")):
        raise HTTPException(400, "That is not a take this desk made.")
    folder = takes_root() / take_id
    if not (folder / "take.json").is_file():
        raise HTTPException(404, "No take with that id.")
    return folder


def _read_take(folder: Path) -> dict:
    try:
        rec = json.loads((folder / "take.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return rec if isinstance(rec, dict) else {}


def _write_take(folder: Path, rec: dict) -> None:
    tmp = folder / "take.json.part"
    tmp.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    tmp.replace(folder / "take.json")


def _status(rec: dict) -> str:
    st = str(rec.get("status") or "")
    if st == "recording" and time.time() - float(rec.get("last_chunk") or rec.get("started") or 0.0) > STALE_S:
        return "interrupted"
    return st


def _aspect(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "16:9"
    return "16:9" if w >= h * 1.2 else "9:16" if h >= w * 1.2 else "1:1"


def public_take(folder: Path, rec: dict | None = None) -> dict:
    """A take as the page and My videos read it: no local paths."""
    rec = rec if rec is not None else _read_take(folder)
    tid = folder.name
    st = _status(rec)
    mp4 = (folder / "take.mp4").is_file() and st == "done"
    w, h = int(rec.get("width") or 0), int(rec.get("height") or 0)
    title = rec.get("title") or "Live take"
    return {"id": tid, "kind": "take", "status": st, "created": rec.get("created") or "",
            # My videos reads a cut's song, vibe, aspect and tier: a take answers with its title and its own shape
            "title": title, "song": title, "vibe": "", "tier": "take", "aspect": _aspect(w, h),
            "seconds": round(float(rec.get("seconds") or 0.0), 2),
            "width": w, "height": h, "size": f"{w}x{h}" if w and h else "", "fps": rec.get("fps") or 0,
            "job": rec.get("job") or "", "audio_id": rec.get("audio_id") or "", "source": rec.get("source") or "",
            "audio": rec.get("audio", True), "chunks": int(rec.get("chunks") or 0), "bytes": int(rec.get("bytes") or 0),
            "start_pos": rec.get("start_pos"), "error": rec.get("error") or "",
            "url": f"/api/perform/takes/{tid}/video.mp4" if mp4 else f"/api/perform/takes/{tid}/take.webm",
            "mp4": f"/api/perform/takes/{tid}/video.mp4" if mp4 else "", "webm": f"/api/perform/takes/{tid}/take.webm"}


@router.post("/api/perform/takes")
def take_start(body: dict | None = None) -> dict:
    """Open a take before its first chunk: the size it is recorded at (the output window's, held while it runs), the fps,
    the song and where in it the take starts, so the take can be named and checked later."""
    body = body or {}

    def num(key: str, lo: float, hi: float, default: float) -> float:
        try:
            return max(lo, min(hi, float(body.get(key))))
        except (TypeError, ValueError):
            return default

    take_id = uuid.uuid4().hex[:10]
    folder = takes_root() / take_id
    folder.mkdir(parents=True, exist_ok=False)
    now = time.time()
    rec = {"id": take_id, "status": "recording", "created": datetime.now().astimezone().isoformat(timespec="seconds"),
           "started": now, "last_chunk": now, "chunks": 0, "bytes": 0,
           "width": int(num("width", 0, 16384, 0)), "height": int(num("height", 0, 16384, 0)), "fps": num("fps", 1, 240, 30),
           "mime": str(body.get("mime") or "video/webm")[:80], "title": str(body.get("title") or "Live take")[:160],
           "job": str(body.get("job") or "")[:64], "audio_id": str(body.get("audio_id") or "")[:64],
           "source": str(body.get("source") or "")[:32], "audio": bool(body.get("audio", True)),
           "start_pos": num("start_pos", 0, 1e6, 0.0) if body.get("start_pos") is not None else None}
    _write_take(folder, rec)
    (folder / "take.webm").write_bytes(b"")
    return public_take(folder, rec)


@router.post("/api/perform/takes/{take_id}/chunk")
async def take_chunk(take_id: str, request: Request, seq: int = 0) -> dict:
    """One chunk of a running take, in order (``seq`` from 0). A chunk sent twice (a retry after a lost answer) is taken
    once; a gap is refused, so the file on disk is always a playable prefix of the take."""
    folder = _take_dir(take_id)
    payload = await request.body()
    if len(payload) > MAX_CHUNK:
        raise HTTPException(413, "That chunk is larger than a take's chunk can be.")
    with _TAKE_LOCK:
        rec = _read_take(folder)
        if rec.get("status") not in ("recording",):
            raise HTTPException(409, "That take is finished.")
        have = int(rec.get("chunks") or 0)
        if seq < have:
            return {"id": take_id, "chunks": have, "bytes": rec.get("bytes", 0), "duplicate": True}
        if seq > have:
            raise HTTPException(409, f"Chunk {seq} came before chunk {have}.")
        if payload:
            with open(folder / "take.webm", "ab") as f:
                f.write(payload)
        rec.update({"chunks": have + 1, "bytes": int(rec.get("bytes") or 0) + len(payload), "last_chunk": time.time()})
        _write_take(folder, rec)
    return {"id": take_id, "chunks": rec["chunks"], "bytes": rec["bytes"]}


def remux(src: Path, dest: Path, fps: float = 30.0) -> None:
    """The take's webm as an mp4 that plays everywhere: H.264 and AAC at the size it was recorded, on a constant frame
    rate (the browser's frames come when the canvas is drawn), with the audio where the browser put it."""
    from xenoform.video import ffmpeg_bin

    tmp = dest.with_suffix(".part.mp4")
    rate = f"{max(1.0, min(240.0, float(fps or 30.0))):g}"
    # each frame to its nearest slot of the constant rate: "-r" alone rounds every frame a slot late (15 ms at 60 fps,
    # measured with docs/ui_review/tools/perform_sync.py), "round=near" keeps the picture where the browser stamped it
    cmd = [ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(src),
           "-map", "0:v:0", "-map", "0:a:0?", "-vf", f"scale=trunc(iw/2)*2:trunc(ih/2)*2,fps={rate}:round=near",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)
    tmp.replace(dest)


def _duration(path: Path) -> float:
    from xenoform.video import ffprobe_bin

    try:
        out = subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             check=True, capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out or 0.0)
    except (subprocess.SubprocessError, OSError, ValueError):
        return 0.0


def _finish(folder: Path) -> None:
    tid = folder.name
    try:
        rec = _read_take(folder)
        src = folder / "take.webm"
        if not src.is_file() or src.stat().st_size == 0:
            raise RuntimeError("the take has no picture: no chunk reached the desk")
        remux(src, folder / "take.mp4", float(rec.get("fps") or 30.0))
        with _TAKE_LOCK:
            rec = _read_take(folder)
            rec.update({"status": "done", "seconds": round(_duration(folder / "take.mp4"), 3), "finished": time.time(), "error": ""})
            _write_take(folder, rec)
    except Exception as exc:  # the webm stays; the page says the mp4 did not build
        log.exception("take %s remux", tid)
        reason = exc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else [str(exc)]
        with _TAKE_LOCK:
            rec = _read_take(folder)
            rec.update({"status": "error", "error": f"The mp4 did not build ({(reason or ['ffmpeg failed'])[0][:200]}); the webm is kept."})
            _write_take(folder, rec)
    finally:
        _FINISHING.discard(tid)


@router.post("/api/perform/takes/{take_id}/finish")
def take_finish(take_id: str, body: dict | None = None, wait: bool = False) -> dict:
    """Close a take (Stop, or a take cut short and found later) and remux it to an mp4 in the background; the answer
    says ``finishing`` until the mp4 is there (``wait=true`` blocks until it is, for scripts and tests). Asking again is
    harmless."""
    folder = _take_dir(take_id)
    body = body or {}
    with _TAKE_LOCK:
        rec = _read_take(folder)
        if rec.get("status") in ("recording", "error"):
            rec["status"] = "finishing"
            for key in ("end_pos", "seconds_played"):
                if body.get(key) is not None:
                    try:
                        rec[key] = round(float(body[key]), 3)
                    except (TypeError, ValueError):
                        pass
            _write_take(folder, rec)
        start = rec.get("status") == "finishing" and take_id not in _FINISHING
        if start:
            _FINISHING.add(take_id)
    if start:
        worker = threading.Thread(target=_finish, args=(folder,), daemon=True, name=f"take-{take_id}")
        worker.start()
        if wait:
            worker.join(timeout=3600)
    elif wait:
        for _ in range(36000):
            if _read_take(folder).get("status") != "finishing":
                break
            time.sleep(0.1)
    return public_take(folder)


def take_rows(limit: int = MAX_TAKES) -> list[dict]:
    """Every take, newest first (``/api/perform/takes`` and the takes in ``/api/videos``)."""
    root = takes_root()
    folders = [p for p in root.iterdir() if p.is_dir() and _TAKE_RE.fullmatch(p.name) and (p / "take.json").is_file()]
    folders.sort(key=lambda p: (p / "take.json").stat().st_mtime, reverse=True)
    rows = []
    for folder in folders[: max(1, min(int(limit), MAX_TAKES))]:
        rec = _read_take(folder)
        if rec:
            rows.append(public_take(folder, rec))
    return rows


def with_takes(videos: list[dict], limit: int = 24) -> list[dict]:
    """``/api/videos``: the cuts (newest first, as the desk sorts them) with the takes laid in by when they were made;
    each list keeps its own order. A takes folder that cannot be read leaves the cuts as they were."""
    try:
        takes = [t for t in take_rows(limit) if t["status"] != "recording"]
    except Exception:
        log.exception("takes for My videos")
        return videos
    out, i, j = [], 0, 0
    while i < len(videos) or j < len(takes):
        if j >= len(takes) or (i < len(videos) and str(videos[i].get("created") or "") >= str(takes[j].get("created") or "")):
            out.append(videos[i])
            i += 1
        else:
            out.append(takes[j])
            j += 1
    return out


@router.get("/api/perform/takes")
def takes_index(limit: int = 50) -> dict:
    return {"takes": take_rows(limit)}


@router.get("/api/perform/takes/{take_id}")
def take_get(take_id: str) -> dict:
    return public_take(_take_dir(take_id))


@router.get("/api/perform/takes/{take_id}/video.mp4")
def take_mp4(take_id: str) -> FileResponse:
    folder = _take_dir(take_id)
    path = folder / "take.mp4"
    if not path.is_file() or _status(_read_take(folder)) != "done":
        raise HTTPException(404, "The mp4 of that take is not ready.")
    return FileResponse(path, media_type="video/mp4", filename=f"xenoform-take-{take_id}.mp4", content_disposition_type="inline")


@router.get("/api/perform/takes/{take_id}/take.webm")
def take_webm(take_id: str) -> FileResponse:
    path = _take_dir(take_id) / "take.webm"
    if not path.is_file() or path.stat().st_size == 0:
        raise HTTPException(404, "That take has no picture yet.")
    return FileResponse(path, media_type="video/webm", filename=f"xenoform-take-{take_id}.webm", content_disposition_type="inline")
