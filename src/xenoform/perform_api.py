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
