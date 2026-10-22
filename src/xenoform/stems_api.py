"""Stems and MIDI routes for the desk (``xenoform.ui`` includes ``router``).

Stems are split only when asked for (the desk's "Stem reactions" drawer or the VJ page), never on
every Make. Results are cached under ``work/ui/stems/<song_hash>/`` so a second request is instant:

    POST /api/stems            {"audio_id": "demo"} | {"path": "song.wav"}  -> {"id", "status", ...}
    GET  /api/stems/<id>       status, stem names, engine, envelope URL
    GET  /api/stems/<id>/envelopes.json   stem_react.save_envelopes output (vj.html ``?stems=``)

``stems_path_for(song)`` gives other code (dense.run_simple via ``state["stems_path"]``) the
cached ``stems.json`` for an audio file, or None when that song has not been split.

MIDI: the Python bridge (``xenoform midi serve``) posts normalised events to ``POST /api/midi/event``
(or sends them over ``/ws/midi``); every browser page on ``/ws/midi`` (or the SSE stream
``GET /api/midi/stream`` for a server without a websocket library) receives them.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from xenoform import stem_react
from xenoform.midi_bridge import normalise

log = logging.getLogger("xenoform")
router = APIRouter()

_ID_RE = re.compile(r"[0-9a-f]{16}")
_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}
_JOBS: dict[str, dict] = {}  # song hash -> {"status", "engine", "stems", "error", "dir", "song"}
_LOCK = threading.Lock()


# ---------------------------------------------------------------- stems
def stems_root() -> Path:
    from xenoform.ui import work_dir

    p = work_dir() / "stems"
    p.mkdir(parents=True, exist_ok=True)
    return p


def song_hash(song: str | Path) -> str:
    """16 hex chars from the audio bytes, so the same file (any name) shares one cache folder."""
    h = hashlib.blake2b(digest_size=8)
    with open(song, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stems_json_path(song: str | Path) -> Path:
    return stems_root() / song_hash(song) / "stems.json"


def stems_path_for(song: str | Path | None, *, build: bool = False, engine: str = "auto", fps: int = 24) -> Path | None:
    """The cached ``stems.json`` (envelopes + stem wav paths) for ``song``, or None when it has not
    been split. With ``build=True`` the split runs now (blocking) and the path is returned."""
    if not song:
        return None
    p = Path(song)
    if not p.is_file():
        return None
    out = stems_json_path(p)
    if out.is_file():
        return out
    if build:
        return Path(run_split(p, engine=engine, fps=fps)["path"])
    return None


def run_split(song: Path, *, engine: str = "auto", fps: int = 24) -> dict:
    """Split ``song`` and write ``work/ui/stems/<hash>/{stems.json, *.wav}``. Cached by song hash."""
    song = Path(song)
    sid = song_hash(song)
    folder = stems_root() / sid
    out = folder / "stems.json"
    if out.is_file():
        rec = json.loads(out.read_text(encoding="utf-8"))
        return {"id": sid, "status": "done", "cached": True, "path": str(out), "engine": rec.get("engine"),
                "stems": rec.get("stems") or [], "frames": rec.get("frames", 0), "fps": rec.get("fps", fps)}
    t0 = time.monotonic()
    stems = stem_react.split(song, folder, engine=engine)
    env = stem_react.envelopes(stems, fps=fps)
    env["song"] = str(song)
    env["files"] = {k: str(v) for k, v in stems.items() if k != "engine"}
    env["seconds"] = round(time.monotonic() - t0, 2)
    stem_react.save_envelopes(env, out)
    return {"id": sid, "status": "done", "cached": False, "path": str(out), "engine": env.get("engine"),
            "stems": env.get("stems") or [], "frames": env.get("frames", 0), "fps": fps, "seconds": env["seconds"]}


def resolve_song(body: dict) -> Path:
    """The audio file a desk request means: ``audio_id`` (as /api/analyze hands out; "demo" is the
    bundled track) or an explicit ``path`` on this machine."""
    from xenoform import ui

    audio_id = str(body.get("audio_id") or body.get("audio") or body.get("job") or "").strip()
    path = str(body.get("path") or "").strip()
    if path:
        p = Path(path)
        if not p.is_file() or p.suffix.lower() not in _AUDIO_SUFFIXES:
            raise HTTPException(400, "That path is not an audio file on this machine.")
        return p
    if not audio_id or audio_id == "demo":
        p = ui.repo_root() / "examples" / "demo.wav"
    else:
        with ui._LOCK:
            p = ui._AUDIO.get(audio_id)
    if p is None or not Path(p).is_file():
        raise HTTPException(404, "That song is not loaded. Choose a song (or the bundled demo) first.")
    return Path(p)


def _job_public(sid: str) -> dict:
    with _LOCK:
        job = dict(_JOBS.get(sid) or {})
    if not job:
        out = stems_root() / sid / "stems.json"
        if out.is_file():
            rec = json.loads(out.read_text(encoding="utf-8"))
            job = {"status": "done", "engine": rec.get("engine"), "stems": rec.get("stems") or [],
                   "frames": rec.get("frames", 0), "fps": rec.get("fps", 24), "roles": rec.get("roles") or {}}
        else:
            raise HTTPException(404, "No stems with that id.")
    job["id"] = sid
    if job.get("status") == "done":
        job["envelopes"] = f"/api/stems/{sid}/envelopes.json"
        job["count"] = len(job.get("stems") or [])
    job.pop("dir", None)
    return job


def _run_job(sid: str, song: Path, engine: str, fps: int) -> None:
    try:
        rec = run_split(song, engine=engine, fps=fps)
        env = json.loads(Path(rec["path"]).read_text(encoding="utf-8"))
        with _LOCK:
            _JOBS[sid].update({"status": "done", "engine": rec["engine"], "stems": rec["stems"], "frames": rec["frames"],
                               "fps": rec["fps"], "roles": env.get("roles") or {}, "seconds": rec.get("seconds")})
    except Exception as exc:
        log.exception("stems %s failed", sid)
        with _LOCK:
            _JOBS[sid].update({"status": "error", "error": str(exc) or exc.__class__.__name__})


@router.post("/api/stems")
def stems_start(body: dict | None = None) -> dict:
    body = body or {}
    song = resolve_song(body)
    engine = str(body.get("engine") or "auto")
    if engine == "librosa":
        engine = "bands"
    if engine not in stem_react.ENGINES:
        raise HTTPException(400, f"engine must be one of {', '.join(stem_react.ENGINES)}")
    try:
        fps = max(1, min(120, int(body.get("fps") or 24)))
    except (TypeError, ValueError):
        fps = 24
    sid = song_hash(song)
    if (stems_root() / sid / "stems.json").is_file():
        with _LOCK:
            _JOBS.pop(sid, None)
        return {**_job_public(sid), "cached": True}
    with _LOCK:
        job = _JOBS.get(sid)
        if job and job.get("status") == "running":
            return {**job, "id": sid}
        _JOBS[sid] = {"status": "running", "engine": engine, "stems": [], "song": song.name, "started": time.time()}
    threading.Thread(target=_run_job, args=(sid, song, engine, fps), daemon=True, name=f"stems-{sid}").start()
    return {"id": sid, "status": "running", "engine": engine, "song": song.name,
            "engines": stem_react.engines_available()}


@router.get("/api/stems/{sid}")
def stems_status(sid: str) -> dict:
    if not _ID_RE.fullmatch(sid):
        raise HTTPException(400, "bad stems id")
    return _job_public(sid)


@router.get("/api/stems/{sid}/envelopes.json")
def stems_envelopes(sid: str) -> FileResponse:
    if not _ID_RE.fullmatch(sid):
        raise HTTPException(400, "bad stems id")
    out = stems_root() / sid / "stems.json"
    if not out.is_file():
        raise HTTPException(404, "Those stems are not ready yet.")
    return FileResponse(out, media_type="application/json")


@router.get("/api/stems/{sid}/{name}.wav")
def stems_wav(sid: str, name: str) -> FileResponse:
    """One separated stem, for listening or for the VJ page to play."""
    if not _ID_RE.fullmatch(sid) or not re.fullmatch(r"[A-Za-z0-9 _.-]{1,64}", name):
        raise HTTPException(400, "bad stems id")
    out = stems_root() / sid / "stems.json"
    if not out.is_file():
        raise HTTPException(404, "Those stems are not ready yet.")
    files = (json.loads(out.read_text(encoding="utf-8")) or {}).get("files") or {}
    p = Path(files.get(name) or "")
    if not p.is_file():
        raise HTTPException(404, "No stem with that name.")
    return FileResponse(p, media_type="audio/wav")


# ---------------------------------------------------------------- MIDI hub
class MidiHub:
    """Fans every normalised MIDI event out to the connected pages (websocket and SSE listeners).
    Keeps the last 256 events so a late listener can catch up with ``since=<seq>``."""

    def __init__(self, keep: int = 256) -> None:
        self.seq = 0
        self.recent: deque = deque(maxlen=keep)
        self.listeners: dict[int, asyncio.Queue] = {}
        self._next = 1
        self.sources: dict[str, float] = {}

    def subscribe(self) -> tuple[int, asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        k, self._next = self._next, self._next + 1
        self.listeners[k] = q
        return k, q

    def unsubscribe(self, k: int) -> None:
        self.listeners.pop(k, None)

    def publish(self, ev: dict, *, source: str = "http", skip: int | None = None) -> dict:
        self.seq += 1
        ev = {**ev, "seq": self.seq, "src": source}
        self.recent.append(ev)
        self.sources[source] = time.time()
        for k, q in list(self.listeners.items()):
            if k == skip:
                continue
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:  # a stalled page: drop its oldest
                try:
                    q.get_nowait()
                    q.put_nowait(ev)
                except Exception:
                    pass
        return ev

    def since(self, seq: int) -> list[dict]:
        return [e for e in self.recent if e["seq"] > seq]

    def status(self) -> dict:
        return {"listeners": len(self.listeners), "seq": self.seq, "sources": dict(self.sources),
                "last": self.recent[-1] if self.recent else None}


hub = MidiHub()


def _events_from(body) -> list[dict]:
    raw = body.get("events") if isinstance(body, dict) and "events" in body else body
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise HTTPException(400, "Send one event or {\"events\": [...]}.")
    out = []
    for item in raw[:256]:
        ev = normalise(item)
        if ev:
            out.append(ev)
    return out


@router.post("/api/midi/event")
async def midi_event(request: Request) -> dict:
    """The Python bridge (or any script) posts events here; they reach every open page."""
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Send JSON.") from exc
    src = str(request.headers.get("x-xeno-midi-source") or (body.get("source") if isinstance(body, dict) else "") or "http")[:32]
    evs = _events_from(body)
    for ev in evs:
        hub.publish(ev, source=src)
    return {"ok": True, "sent": len(evs), "seq": hub.seq, "listeners": len(hub.listeners)}


@router.get("/api/midi/status")
def midi_status() -> dict:
    from xenoform.midi_bridge import backend_available

    return {**hub.status(), "bridge": backend_available()}


@router.get("/api/midi/stream")
async def midi_stream(since: int = -1, limit: int = 0, timeout: float = 0.0) -> StreamingResponse:
    """Server-sent events for browsers without a websocket (or a server without a websocket library).
    ``since`` replays buffered events after that seq; ``limit``/``timeout`` end the stream (scripts, tests)."""
    k, q = hub.subscribe()

    async def gen():
        n = 0
        t_end = time.monotonic() + timeout if timeout > 0 else None
        try:
            yield "retry: 1000\n\n"
            if since >= 0:
                for ev in hub.since(since):
                    n += 1
                    yield f"data: {json.dumps(ev)}\n\n"
                    if limit and n >= limit:
                        return
            while True:
                wait = None if t_end is None else max(0.0, t_end - time.monotonic())
                if wait is not None and wait <= 0:
                    return
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=wait if wait is not None else 15.0)
                except asyncio.TimeoutError:
                    if t_end is not None:
                        return
                    yield ": keep-alive\n\n"
                    continue
                n += 1
                yield f"data: {json.dumps(ev)}\n\n"
                if limit and n >= limit:
                    return
        finally:
            hub.unsubscribe(k)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.websocket("/ws/midi")
async def midi_ws(ws: WebSocket) -> None:
    """Two-way: anything a client sends is normalised and fanned out to every other client;
    everything published (bridge posts, other pages) is pushed to this client."""
    await ws.accept()
    k, q = hub.subscribe()
    name = str(ws.query_params.get("name") or ws.client.host if ws.client else "ws")[:32]

    async def pump():
        while True:
            ev = await q.get()
            await ws.send_json(ev)

    sender = asyncio.ensure_future(pump())
    try:
        await ws.send_json({"type": "hello", "seq": hub.seq, "listeners": len(hub.listeners)})
        while True:
            data = await ws.receive_text()
            try:
                body = json.loads(data)
            except ValueError:
                continue
            for ev in _events_from(body) if isinstance(body, (dict, list)) else []:
                hub.publish(ev, source=name, skip=k)
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        log.debug("midi ws closed", exc_info=True)
    finally:
        sender.cancel()
        hub.unsubscribe(k)
