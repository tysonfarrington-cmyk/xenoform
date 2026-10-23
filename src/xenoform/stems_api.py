"""Stems and MIDI routes for the desk (``xenoform.ui`` includes ``router``).

Stems split by default: ``xenoform.ui`` calls ``start_background_split(path)`` from /api/analyze and
/api/demo, so a song's stems are on their way (Demucs on the CPU when installed, the librosa band split
otherwise) the moment it loads and the first Make is stem-reactive. One thread per song hash, results
cached under ``work/ui/stems/<song_hash>/`` so a second request, or a second desk session, is instant:

    start_background_split(song)   -> {"id", "status": queued|running|done|error, "engine", "seconds", "path", "error"}
    split_status(song)             -> the same, or {"status": "none"} when nothing asked for this song yet
    GET  /api/stems/for/<audio_id> that status for a desk song id (the "Stem reactions" line polls it)
    POST /api/stems            {"audio_id": "demo"} | {"path": "song.wav"}  -> {"id", "status", ...} (starts it too)
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
import os
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
_SONG_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # a desk audio id: "demo" or what /api/analyze hands out
_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}
STATUSES = ("none", "queued", "running", "done", "error")
# The split registry, one entry per song hash whichever asked first (the desk's hook, POST /api/stems, the VJ page):
# {"id", "status": queued|running|done|error, "engine", "seconds", "path", "error", "song", "stems", "frames", "fps",
#  "roles", "started", "running_since"}. ``seconds`` is the elapsed time while it waits or runs, the wall time when done.
_JOBS: dict[str, dict] = {}
_THREADS: dict[str, threading.Thread] = {}
_LOCK = threading.Lock()
# One split at a time: Demucs on the CPU already uses every core, so two at once only thrash; the second waits "queued".
_SLOT = threading.Semaphore(1)
_HASHES: dict[str, tuple[int, int, str]] = {}  # path -> (size, mtime_ns, hash): status polls do not re-read the song
_PRIVATE = ("dir", "path", "song_path", "started", "running_since")  # registry keys the routes do not send


# ---------------------------------------------------------------- stems
def stems_root() -> Path:
    from xenoform.ui import work_dir

    p = work_dir() / "stems"
    p.mkdir(parents=True, exist_ok=True)
    return p


def song_hash(song: str | Path) -> str:
    """16 hex chars from the audio bytes, so the same file (any name) shares one cache folder. Remembered per
    path (size and mtime), so the desk's status polls do not read the song again."""
    p = Path(song)
    st = p.stat()
    key = str(p.resolve())
    hit = _HASHES.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    h = hashlib.blake2b(digest_size=8)
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _HASHES[key] = (st.st_size, st.st_mtime_ns, digest)
    return digest


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
    """Split ``song`` and write ``work/ui/stems/<hash>/{stems.json, *.wav}``. Cached by song hash. Blocking;
    the desk uses ``start_background_split`` instead."""
    song = Path(song)
    sid = song_hash(song)
    folder = stems_root() / sid
    out = folder / "stems.json"
    if out.is_file():
        rec = json.loads(out.read_text(encoding="utf-8"))
        return {"id": sid, "status": "done", "cached": True, "path": str(out), "engine": rec.get("engine"),
                "stems": rec.get("stems") or [], "frames": rec.get("frames", 0), "fps": rec.get("fps", fps),
                "seconds": rec.get("seconds")}
    t0 = time.monotonic()
    stems = stem_react.split(song, folder, engine=engine)
    env = stem_react.envelopes(stems, fps=fps)
    env["song"] = str(song)
    env["files"] = {k: str(v) for k, v in stems.items() if k != "engine"}
    env["seconds"] = round(time.monotonic() - t0, 2)
    tmp = out.with_suffix(".json.part")  # written whole, then moved into place, so a status poll never reads half a file
    stem_react.save_envelopes(env, tmp)
    os.replace(tmp, out)
    return {"id": sid, "status": "done", "cached": False, "path": str(out), "engine": env.get("engine"),
            "stems": env.get("stems") or [], "frames": env.get("frames", 0), "fps": fps, "seconds": env["seconds"]}


def _engine(value) -> str:
    engine = str(value or "auto")
    if engine == "librosa":
        engine = "bands"
    if engine not in stem_react.ENGINES:
        raise ValueError(f"engine must be one of {', '.join(stem_react.ENGINES)}")
    return engine


def _fps(value) -> int:
    try:
        return max(1, min(120, int(value or 24)))
    except (TypeError, ValueError):
        return 24


def _snapshot(job: dict) -> dict:
    """A copy of a registry entry, with the elapsed seconds filled in while it waits or runs."""
    j = dict(job)
    if j.get("status") in ("queued", "running"):
        j["seconds"] = round(time.time() - (j.get("running_since") or j.get("started") or time.time()), 1)
    return j


def _done_from_file(sid: str, out: Path) -> dict:
    rec = json.loads(out.read_text(encoding="utf-8"))
    return {"id": sid, "status": "done", "engine": rec.get("engine"), "stems": rec.get("stems") or [],
            "frames": rec.get("frames", 0), "fps": rec.get("fps", 24), "roles": rec.get("roles") or {},
            "seconds": rec.get("seconds"), "path": str(out), "error": None,
            "song": Path(str(rec.get("song") or "")).name}


def status_for_id(sid: str) -> dict:
    """The registry entry for a song hash (elapsed seconds filled in); ``done`` from the cache when an earlier
    session split it; ``{"status": "none"}`` when nothing has asked for this song yet."""
    out = stems_root() / sid / "stems.json"
    with _LOCK:
        job = _JOBS.get(sid)
        if job is not None:
            st = job.get("status")
            if st in ("queued", "running") or (st == "done") == out.is_file():
                return _snapshot(job)
    if out.is_file():
        try:
            done = _done_from_file(sid, out)
        except Exception as exc:  # a stale or half-written file from an older desk
            return {"id": sid, "status": "error", "engine": None, "seconds": None, "path": str(out),
                    "error": f"stems.json could not be read: {exc}"}
        with _LOCK:
            _JOBS[sid] = done
        return dict(done)
    return {"id": sid, "status": "none", "engine": None, "seconds": None, "path": None, "error": None}


def split_status(song: str | Path | None) -> dict:
    """The background split's status for an audio file (see ``start_background_split``): ``status`` is ``none``
    (nothing asked for yet), ``queued``, ``running`` (``seconds`` = elapsed so far), ``done`` (``path`` = its
    stems.json, ``stems``, ``engine``, ``seconds`` = the split's wall time) or ``error`` (``error`` = why)."""
    p = Path(song) if song else None
    if p is None or not p.is_file():
        return {"id": None, "status": "error", "engine": None, "seconds": None, "path": None,
                "error": "no such audio file", "song": p.name if p else ""}
    return status_for_id(song_hash(p))


def _update(sid: str, **fields) -> bool:
    """Merge ``fields`` into the registry entry for ``sid``; False when the entry is gone (a cleared registry)."""
    with _LOCK:
        job = _JOBS.get(sid)
        if job is None:
            return False
        job.update(fields)
        return True


def _run_job(sid: str, song: Path, engine: str, fps: int) -> None:
    with _SLOT:  # "queued" until the slot is free
        resolved = engine if engine != "auto" else ("demucs" if stem_react.demucs_available() else "bands")
        if not _update(sid, status="running", engine=resolved, running_since=time.time()):
            return
        t0 = time.monotonic()
        try:
            rec = run_split(song, engine=engine, fps=fps)
            env = json.loads(Path(rec["path"]).read_text(encoding="utf-8"))
            seconds = rec.get("seconds") or round(time.monotonic() - t0, 2)
            _update(sid, status="done", engine=rec["engine"], stems=rec["stems"], frames=rec["frames"], fps=rec["fps"],
                    roles=env.get("roles") or {}, seconds=seconds, path=rec["path"], error=None)
            log.info("stems %s: %d stems (%s) for %s in %.1f s", sid, len(rec["stems"]), rec["engine"], song.name, seconds)
        except Exception as exc:
            log.exception("stems %s failed", sid)
            _update(sid, status="error", error=str(exc) or exc.__class__.__name__, seconds=round(time.monotonic() - t0, 2))
        finally:
            _THREADS.pop(sid, None)


def start_background_split(song: str | Path, *, engine: str = "auto", fps: int = 24) -> dict:
    """Split ``song`` on a background thread and return the status at once (non-blocking). The desk's
    /api/analyze and /api/demo call ``stems_api.start_background_split(path)`` so the stems are ready, or on
    their way, by the first Make. Idempotent: one thread per song hash; while that is queued or running a second
    call returns the same status, and a song whose ``stems.json`` is cached is ``done`` without a thread. Never
    raises: a missing or unreadable file gives ``{"status": "error", ...}``, so the hook cannot fail an upload."""
    try:
        p = Path(song)
        engine = _engine(engine)
        fps = _fps(fps)
        if not p.is_file():
            raise FileNotFoundError(f"no audio file at {p}")
        sid = song_hash(p)
    except Exception as exc:
        log.warning("stems: cannot split %s: %s", song, exc)
        return {"id": None, "status": "error", "engine": engine, "seconds": None, "path": None,
                "error": str(exc) or exc.__class__.__name__, "song": Path(str(song)).name}
    st = status_for_id(sid)
    if st["status"] in ("queued", "running", "done"):
        return st
    with _LOCK:
        job = _JOBS.get(sid)
        if job and job.get("status") in ("queued", "running"):  # a race with another caller: theirs runs
            return _snapshot(job)
        _JOBS[sid] = job = {"id": sid, "status": "queued", "engine": engine, "seconds": 0.0, "path": None, "error": None,
                            "song": p.name, "song_path": str(p), "fps": fps, "stems": [], "started": time.time()}
        _THREADS[sid] = t = threading.Thread(target=_run_job, args=(sid, p, engine, fps), daemon=True, name=f"stems-{sid}")
    t.start()
    return _snapshot(job)


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


def _public(st: dict, *, legacy: bool = False) -> dict:
    """What the routes send: the status without local paths, plus ``envelopes`` and ``count`` when done.
    ``legacy`` reports ``queued`` as ``running`` (with ``"queued": true``) for POST /api/stems and
    GET /api/stems/<id>, whose older clients (vj.html) only keep polling while the status is ``running``."""
    j = {k: v for k, v in st.items() if k not in _PRIVATE}
    if j.get("status") == "done" and j.get("id"):
        j["envelopes"] = f"/api/stems/{j['id']}/envelopes.json"
        j["count"] = len(j.get("stems") or [])
    if legacy and j.get("status") == "queued":
        j["status"], j["queued"] = "running", True
    return j


def _job_public(sid: str) -> dict:
    st = status_for_id(sid)
    if st["status"] == "none":
        raise HTTPException(404, "No stems with that id.")
    return _public(st, legacy=True)


@router.post("/api/stems")
def stems_start(body: dict | None = None) -> dict:
    """Start (or find) the split for a song; the "Stem reactions" drawer and the VJ page call this. A song
    already split answers ``done`` at once with ``cached: true``."""
    body = body or {}
    song = resolve_song(body)
    try:
        engine = _engine(body.get("engine"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    fps = _fps(body.get("fps"))
    cached = (stems_root() / song_hash(song) / "stems.json").is_file()
    st = start_background_split(song, engine=engine, fps=fps)
    out = _public(st, legacy=True)
    out["cached"] = bool(cached and st.get("status") == "done")
    out["engines"] = stem_react.engines_available()
    return out


@router.get("/api/stems/for/{audio_id}")
def stems_for_song(audio_id: str) -> dict:
    """The background split's status for a desk song id ("demo" or the id /api/analyze handed out) without
    starting one: {"status": none|queued|running|done|error, "id", "engine", "seconds", "error", ...} and, when
    done, "stems", "count", "envelopes". The desk's "Stem reactions" line polls this every couple of seconds."""
    if not _SONG_ID_RE.fullmatch(audio_id):
        raise HTTPException(400, "bad song id")
    song = resolve_song({"audio_id": audio_id})
    return {**_public(split_status(song)), "audio_id": audio_id}


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
