"""The bundled songs: six of the author's own Suno instrumentals in ``examples/songs/``, shipped with their analyses so
the desk loads one at once, with no librosa pass (``xenoform.ui`` includes ``router``).

    GET  /api/songs        -> {"songs": [{"id", "title", "seconds", "bpm", "feel", "credit", "file", "audio_id"}],
                               "demo": {"id": "demo", ...}}
    POST /api/songs/load   {"id": "morphing-wobble-20s"} -> the session payload /api/analyze returns for an upload,
                            with the song registered under the audio id "song-<id>" and its stem split started

The manifest is ``examples/songs/songs.json`` (``manifest()``); the analyses are ``examples/songs/<id>.features.json``,
built by ``scripts/analyse_bundled_songs.py`` the way ``/api/analyze`` builds an upload's (``analyse(path)``). A song
whose shipped analysis is missing is analysed on first load and cached under ``work/ui/songs/<id>.features.json``.
The shipped analyses are at the default desk's frame rate (``configs/example.json``, 24 fps), as the demo's is.

A desk restart forgets ``ui._AUDIO`` and ``ui._FEATURES``, and a job's recipe, a bookmarked page or a poll may still
name ``song-<id>``. ``audio_registry()`` and ``features_registry()`` are those two dicts: a lookup of ``song-<id>``
that misses fills itself from the manifest (``Registry``), so ``/media/audio/song-<id>``,
``/api/stems/for/song-<id>`` and every "Load a song before..." check in ``ui`` know a bundled song on first sight.
For any other id they are plain dicts. The fill only reads what is on disk (the shipped analysis or the work cache):
it runs under the desk's lock, so it never analyses; a song with neither file misses until its chip is clicked, which
analyses outside the lock and caches.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger("xenoform")
router = APIRouter()

PREFIX = "song-"  # a bundled song's desk audio id is "song-<id>" (it matches ui._ID_RE and stems_api._SONG_ID_RE)
PUBLIC = ("id", "title", "seconds", "bpm", "feel", "credit", "file")
_MANIFEST: tuple[Path, int, list[dict]] | None = None  # (path, mtime_ns, rows): re-read when the file changes
_ANALYSE_LOCK = threading.Lock()  # one analysis of a song without its shipped file at a time


# ---------------------------------------------------------------- the manifest
def songs_dir() -> Path:
    from xenoform.ui import repo_root

    return repo_root() / "examples" / "songs"


def manifest() -> list[dict]:
    """The rows of ``examples/songs/songs.json`` in their order; ``[]`` without the file or with a broken one."""
    global _MANIFEST
    path = songs_dir() / "songs.json"
    try:
        stamp = path.stat().st_mtime_ns
    except OSError:
        return []
    cached = _MANIFEST
    if cached and cached[0] == path and cached[1] == stamp:
        return cached[2]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("bundled songs: songs.json")
        return []
    rows = data.get("songs") if isinstance(data, dict) else data
    rows = [dict(row) for row in (rows or []) if isinstance(row, dict) and row.get("id")]
    _MANIFEST = (path, stamp, rows)
    return rows


def find(song_id: str) -> dict | None:
    """The manifest row with that id, or None."""
    wanted = str(song_id or "").strip()
    return next((row for row in manifest() if row["id"] == wanted), None)


def song_path(row: dict) -> Path:
    return songs_dir() / str(row.get("file") or f"{row['id']}.mp3")


def audio_id_for(row: dict) -> str:
    return PREFIX + str(row["id"])


def song_id_of(audio_id: str) -> str | None:
    """The bundled song id behind a desk audio id (``song-<id>``), or None when it is not one."""
    text = str(audio_id or "")
    if not text.startswith(PREFIX):
        return None
    return text[len(PREFIX):] or None


def public(row: dict) -> dict:
    """What the routes send for one song: the manifest's public fields, the repo path and the desk audio id."""
    out: dict[str, Any] = {key: row.get(key) for key in PUBLIC}
    out["file"] = f"examples/songs/{row.get('file') or row['id'] + '.mp3'}"
    out["audio_id"] = audio_id_for(row)
    return out


def demo_row() -> dict:
    """The Bundled demo as a row of the same shape (``examples/demo.wav``, loaded by ``GET /api/demo``)."""
    from xenoform import ui

    try:
        features = ui._demo_features()
        seconds = round(float(features.get("duration") or 0.0), 1)
        bpm = int(round(float(features.get("tempo") or 0.0)))
    except Exception:  # the demo's features file is part of the repo; a broken one only loses the two numbers
        seconds, bpm = 12.0, 120
    return {"id": "demo", "title": "Bundled demo", "seconds": seconds, "bpm": bpm,
            "feel": "12 s synthesised by xenoform synth; the quickest first Make",
            "credit": "Synthesised by xenoform synth; part of this MIT repo.",
            "file": "examples/demo.wav", "audio_id": "demo"}


# ---------------------------------------------------------------- the analyses
def analyse(path: Path) -> dict:
    """The same analysis ``/api/analyze`` runs on an upload, with the desk's config (``fps`` and ``analyze``)."""
    import librosa

    from xenoform.analyze import analyze_audio
    from xenoform.ui import load_desk_config

    cfg = load_desk_config()
    audio, sr = librosa.load(path, sr=None, mono=True)
    return analyze_audio(
        audio,
        int(sr),
        fps=float(cfg["fps"]),
        onset_tau=float(cfg["analyze"]["onset_tau"]),
        beat_tau=float(cfg["analyze"]["beat_tau"]),
        section_min_seconds=float(cfg["analyze"]["section_min_seconds"]),
    )


def shipped_features_path(row: dict) -> Path:
    return songs_dir() / f"{row['id']}.features.json"


def cached_features_path(row: dict) -> Path:
    from xenoform.ui import work_dir

    return work_dir() / "songs" / f"{row['id']}.features.json"


def _read(path: Path) -> dict | None:
    from xenoform.analyze import read_features

    try:
        data = read_features(path)
    except (OSError, ValueError):
        log.warning("bundled songs: %s could not be read", path)
        return None
    return data if isinstance(data, dict) and data.get("frames") else None


def features_on_disk(row: dict) -> dict | None:
    """The song's analysis as it is on disk: the shipped file, else the work cache, else None. Cheap: no librosa."""
    for path in (shipped_features_path(row), cached_features_path(row)):
        if path.is_file():
            data = _read(path)
            if data is not None:
                return data
    return None


def features_for(row: dict) -> dict:
    """The song's analysis: the shipped file, else the work cache, else analysed now (the ``/api/analyze`` way) and
    cached under ``work/ui/songs/``."""
    data = features_on_disk(row)
    if data is not None:
        return data
    with _ANALYSE_LOCK:
        cache = cached_features_path(row)
        if cache.is_file():  # another request analysed it while this one waited
            data = _read(cache)
            if data is not None:
                return data
        log.info("bundled song %s: no shipped analysis, analysing %s", row["id"], song_path(row).name)
        features = analyse(song_path(row))
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".json.part")
            tmp.write_text(json.dumps(features, separators=(",", ":")), encoding="utf-8")
            tmp.replace(cache)
        except OSError:
            log.exception("bundled song %s: cache", row["id"])
        return features


# ---------------------------------------------------------------- the self-healing registries
class Registry(dict):
    """A desk registry (audio id -> value) that finds a bundled song on first sight. A lookup of ``song-<id>`` that
    misses asks ``fill(song_id)`` (the value, or None when the id is not a bundled song) and keeps the answer, so a
    restarted desk knows the bundled songs without a load; for every other key it is a plain dict. ``fill`` runs
    inside whatever lock the caller holds (``ui._LOCK`` at most call sites), so it never takes ``ui._LOCK`` itself
    and never does slow work: it reads files, it does not analyse."""

    def __init__(self, fill: Callable[[str], Any]):
        super().__init__()
        self._fill = fill

    def _heal(self, key: Any) -> Any:
        song_id = song_id_of(key) if isinstance(key, str) else None
        if song_id is None:
            return None
        try:
            value = self._fill(song_id)
        except Exception:  # a song file gone or an analysis that fails: the lookup misses, as for an unknown id
            log.exception("bundled song %s", song_id)
            return None
        if value is not None:
            dict.__setitem__(self, key, value)
        return value

    def __missing__(self, key: Any) -> Any:
        value = self._heal(key)
        if value is None:
            raise KeyError(key)
        return value

    def get(self, key: Any, default: Any = None) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        value = self._heal(key)
        return default if value is None else value

    def __contains__(self, key: Any) -> bool:
        return dict.__contains__(self, key) or self._heal(key) is not None


def _audio_fill(song_id: str) -> Path | None:
    row = find(song_id)
    if row is None:
        return None
    path = song_path(row)
    return path if path.is_file() else None


def _features_fill(song_id: str) -> dict | None:
    """Only what is on disk: a librosa pass here would run under ``ui._LOCK`` and stall every other request (the media
    route, the stems poll, a Make) for the length of the analysis. Without a file the lookup misses, as for an unknown
    id, until ``POST /api/songs/load`` analyses the song outside the lock and caches it."""
    row = find(song_id)
    if row is None or not song_path(row).is_file():
        return None
    return features_on_disk(row)


def audio_registry() -> Registry:
    """``ui._AUDIO``: audio id -> the song file."""
    return Registry(_audio_fill)


def features_registry() -> Registry:
    """``ui._FEATURES``: audio id -> the song's analysis."""
    return Registry(_features_fill)


# ---------------------------------------------------------------- loading one
UNREADABLE = "That song could not be read or analysed. Run scripts/analyse_bundled_songs.py to rebuild its analysis."


def load(row: dict, cfg: dict | None = None) -> dict:
    """Register the song under ``song-<id>`` (idempotent: the same id every time), start its stem split as an upload's
    is started, and answer the session payload ``/api/analyze`` returns. ``cfg`` is the desk's config (the one
    ``create_app`` was given, kept on ``app.state.cfg``), for the Comfy endpoint; the default desk's without it."""
    from xenoform import stems_api, ui

    audio_id = audio_id_for(row)
    path = song_path(row)
    try:
        features = features_for(row)
    except Exception as exc:  # the shipped file broken and the analysis failing too: one plain sentence, the rest in the log
        log.exception("bundled song %s", row["id"])
        raise HTTPException(400, UNREADABLE) from exc
    with ui._LOCK:
        ui._AUDIO[audio_id] = path
        ui._FEATURES[audio_id] = features
    try:  # stems by default, as /api/analyze does; a failed start never fails the load
        stems_api.start_background_split(path)
    except Exception:
        log.exception("background stem split (%s)", audio_id)
    cfg = cfg or ui.load_desk_config()
    payload = ui.session_payload(
        features,
        audio_id=audio_id,
        title=str(row.get("title") or row["id"]),
        video="",
        endpoint=str(cfg["comfy"].get("base_url") or ""),
    )
    payload["video_label"] = "No picture yet — generate a cut"  # as /api/analyze sets it
    payload["reference"] = ""
    payload["song"] = public(row)
    return payload


# ---------------------------------------------------------------- routes
@router.get("/api/songs")
def songs_list() -> dict:
    """The bundled songs in the manifest's order (only those whose file is present) and the Bundled demo."""
    return {"songs": [public(row) for row in manifest() if song_path(row).is_file()], "demo": demo_row()}


@router.post("/api/songs/load")
def songs_load(request: Request, body: dict | None = None) -> dict:
    """Load a bundled song by its manifest id. 404 for a name that is not one."""
    row = find(str((body or {}).get("id") or ""))
    if row is None or not song_path(row).is_file():
        raise HTTPException(404, "No bundled song with that name. GET /api/songs lists them.")
    return load(row, getattr(request.app.state, "cfg", None))
