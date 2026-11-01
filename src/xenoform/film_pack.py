"""The free film pack: public-domain film clips for Morph: Your clips, pulled from archive.org and NASA on request.

Tys, 29 Oct: "lets include a bunch of those free domain clips in the app as an optional download". Nothing from the
films is shipped: a repo should not carry other people's footage even when it is public domain, and the windows add
up. The list is ``configs/film_pack.json`` (sources with their URLs, the derivative file taken and its size, and a
licence line; clips as a source, a start and a length). Setup & models has a **Free film pack** row with a Download
button; the desk's Your clips row has a **Free film pack** button that points the cut at the folder once it is there.

Version 2 of the list (Tys, 1 Nov: "about 40 clips, colour and action first, so every cut the plan wants shows a clip
once") gives each clip four more fields, which ``pack.json`` and ``labels.json`` carry beside the files for the cutter:
``colour`` (false for black-and-white film, by the taste file's measure, ``clip_cut.mono``), ``motion`` (0 to 1: the
clip's frame-to-frame change, ``clip_cut.motion``, over ``clip_cut.MOTION_FULL``), ``living`` (people or animals in it:
the kaleido steps aside on it) and ``mood`` (``calm``, ``build`` or ``drop``: the passages it suits). A clip's own
``crop`` (``w:h:x:y``, the letterbox or pillarbox bars of its window) wins over its source's. A version 1 list, with no
such fields and the crop on its sources, reads as it always did.

How a clip is made: ffmpeg reads the window straight from the source URL (``-ss <start> -i <url> -t <seconds>``; the http
demuxer does byte-range reads, so a 10 s window of a 1 GB film costs a few MB and about 5 s), scaled to square pixels
and at most 1280 wide at 24 fps (an MPEG-2 file's 720x480 at 8:9 comes out 640x480), silent, libx264 CRF 18, written to
``<name>.part.mp4`` and renamed. A source marked ``"whole": true`` is downloaded in full first
(``models_setup.download_file``, with resume) into ``<folder>/_src/`` and cut from disk: a file whose server will not
answer a seek, or a small one that costs less whole (version 2 has none). The folder is ``work/ui/film_pack/`` (``XENO_FILM_PACK`` moves it), one ``NN_<id>.mp4`` a clip so
the manifest's order is the folder's name order (``own_media.scan`` reads files in name order), plus ``CREDITS.md``
(title, year, maker, page, licence line and the file taken with its size a source; the clips with their times),
``pack.json`` (what was made, with the start, seconds, url and crop each clip was cut from, and its fields) and
``labels.json`` (a readable label a file, with the fields beside it when the list gives them, which ``own_media.scan``
hands to ``clip_cut`` for the chain, the morph lines and the cutter). The list is curated over time, and ``pack.json``
is how a run follows it: a clip whose window moved is
made again, a clip the list reordered is moved to its new name, a file the pack made for a clip that left the list is
removed (never a file of the user's), and a whole source is removed once every clip of it is in place.

    status()            the Setup row: present, count, total, stale, folder, bytes (on disk, else an estimate), detail, files
    start()             the download, on a background thread; ``PlainError`` when XENO_OFFLINE is set
    download_status()   {"status": idle|running|done|error, "progress": 0..1, "detail", "error"}
    remove()            deletes the pack's clips by name (tests)
    GET /api/film_pack  status() plus "download": download_status(), for the desk's clips row

``RUNNER`` (the ffmpeg call) and ``FETCHER`` (the whole-source download) are module attributes so tests can fake them.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from fastapi import APIRouter

from xenoform.errors import PlainError, plain_error

log = logging.getLogger("xenoform")
router = APIRouter()

ID = "film-pack"
BADGE = "Clips"
BYTES_PER_SECOND = 300_000     # the size estimate a clip before it is here: the real pack came to 257 KB a second
                               # (soft, dark, low-resolution scans at CRF 18; 91 MB for 356 s on 29 Oct), so 300 KB leaves room
ATTEMPTS = 3                   # ffmpeg tries a clip this many times
RETRY_WAIT_S = 3.0             # with this long between tries
MIN_CLIP_S = 1.0               # a clip on disk shorter than this is made again
ARCHIVE = "https://archive.org/download/"
NASA = "https://images-assets.nasa.gov/"  # NASA's own image and video library, the other place a source may come from
# Square pixels, at most 1280 wide, the height from the picture's shape: an MPEG-2 upload stores 720x480 at a pixel shape
# of 8:9 and plays 4:3; scaled by its stored size it would come out a ninth too wide in the cut (own_media.render_clip
# crops by pixels). A file of square pixels comes out as the old ``scale=w='min(1280,iw)':h=-2`` made it.
SCALE = "scale=w='trunc(min(1280,iw*sar)/2)*2':h='trunc(ow/dar/2)*2',setsar=1,fps=24,format=yuv420p"
# A source whose upload has black bars baked into its frame (a 4:3 film inside a 16:9 file) carries ``crop: "w:h:x:y"``
# in the manifest, or a clip does when only its window has them; the bars are cut off before the scale, so a clip is
# the picture and never a pillarbox.
CROP_RE = re.compile(r"\d{2,5}:\d{2,5}:\d{1,5}:\d{1,5}")
MOODS = ("calm", "build", "drop")  # version 2: the passages a clip suits (clip_cut prefers them there)
FIELDS = ("colour", "motion", "living", "mood")  # version 2: what pack.json and labels.json carry beside each file


# ---------------------------------------------------------------- the manifest and the folder
def manifest_path() -> Path:
    from xenoform.ui import repo_root

    return repo_root() / "configs" / "film_pack.json"


def load_manifest() -> dict:
    """``configs/film_pack.json`` with its keys filled in, so a short manifest still reads. A row that would break the
    pack (clips not a list, a clip without an id, a start or seconds that is not a number, a crop that is not w:h:x:y, a
    version 2 field of the wrong kind) is a ``ValueError`` that names it, so the Setup row and the download say which
    row rather than failing part-way. Every version 2 field may be missing: a version 1 list reads as it did."""
    data = json.loads(manifest_path().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("configs/film_pack.json is not a JSON object")
    data.setdefault("version", 1)
    data.setdefault("name", "Free film pack")
    data.setdefault("folder", "film_pack")
    data.setdefault("sources", {})
    data.setdefault("clips", [])
    if not isinstance(data["sources"], dict) or not isinstance(data["clips"], list):
        raise ValueError("configs/film_pack.json needs sources as an object and clips as a list")
    for i, clip in enumerate(data["clips"]):
        if not isinstance(clip, dict) or not str(clip.get("id") or "").strip():
            raise ValueError(f"Clip {i + 1} in configs/film_pack.json has no id")
        name = f"Clip {i + 1} ({clip['id']}) in configs/film_pack.json"
        try:
            float(clip.get("start") or 0.0), float(clip.get("seconds") or 0.0)
        except (TypeError, ValueError):
            raise ValueError(f"{name} has a start or seconds that is not a number") from None
        crop = str(clip.get("crop") or "")
        if crop and not CROP_RE.fullmatch(crop):
            raise ValueError(f"{name} has a crop that is not w:h:x:y in pixels: {crop!r}")
        for key in ("colour", "living"):
            if key in clip and not isinstance(clip[key], bool):
                raise ValueError(f"{name} has a {key} that is not true or false: {clip[key]!r}")
        if "motion" in clip:
            m = clip["motion"]
            if isinstance(m, bool) or not isinstance(m, (int, float)) or not 0.0 <= float(m) <= 1.0:
                raise ValueError(f"{name} has a motion that is not a number from 0 to 1: {m!r}")
        if "mood" in clip and clip["mood"] not in MOODS:
            raise ValueError(f"{name} has a mood that is not one of {', '.join(MOODS)}: {clip['mood']!r}")
    for key, src in data["sources"].items():
        crop = str((src or {}).get("crop") or "") if isinstance(src, dict) else ""
        if crop and not CROP_RE.fullmatch(crop):
            raise ValueError(f"Source {key} in configs/film_pack.json has a crop that is not w:h:x:y in pixels: {crop!r}")
    return data


def fields_of(clip: dict) -> dict:
    """The version 2 fields a clip gives (``FIELDS``), only those it has: what pack.json and labels.json carry."""
    return {k: clip[k] for k in FIELDS if k in (clip or {})}


def folder(manifest: dict | None = None, *, create: bool = True) -> Path:
    """The pack's folder: ``XENO_FILM_PACK``, else ``work/ui/<manifest folder>``. Made on demand when ``create`` (the
    download); a check only looks, so a Setup poll makes no folder. One that cannot be made is a ``PlainError``."""
    env = os.environ.get("XENO_FILM_PACK", "").strip().strip('"').strip()
    if env:
        path = Path(env)
    else:
        from xenoform.ui import work_dir

        manifest = manifest or load_manifest()
        path = work_dir() / str(manifest.get("folder") or "film_pack")
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PlainError(f"The film pack folder {path} could not be made ({exc.strerror or exc}). "
                             "Set XENO_FILM_PACK to a folder that can be written, or unset it.") from exc
    return path


def clip_name(clip: dict, index: int) -> str:
    return f"{int(index) + 1:02d}_{clip.get('id')}.mp4"


def clip_path(clip: dict, index: int, root: Path | None = None) -> Path:
    return (root if root is not None else folder()) / clip_name(clip, index)


def clip_label(clip: dict) -> str:
    """What the chain calls the clip: its ``label``, else its ``title``, else its id in words."""
    return str(clip.get("label") or clip.get("title") or str(clip.get("id") or "").replace("_", " ").replace("-", " ")).strip()


def offline() -> bool:
    return os.environ.get("XENO_OFFLINE", "").strip().lower() in {"1", "true", "yes"}


# ---------------------------------------------------------------- what is on disk
_PROBED: dict[str, tuple[int, int, float]] = {}  # path -> (size, mtime_ns, seconds): status polls do not re-probe


def probe_seconds(path: Path) -> float:
    """ffprobe's duration for a file, 0.0 when it cannot be read. Remembered by size and mtime."""
    path = Path(path)
    try:
        st = path.stat()
    except OSError:
        return 0.0
    key = str(path)
    hit = _PROBED.get(key)
    if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
        return hit[2]
    try:
        out = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=30).stdout.strip()
        seconds = float(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        seconds = 0.0
    _PROBED[key] = (st.st_size, st.st_mtime_ns, seconds)
    return seconds


def clip_ready(path: Path, *, probe: bool | None = None) -> bool:
    """A clip counts when its file is there and ffprobe says it is at least a second long. Without ffprobe on PATH
    (``probe`` False, or None and none found) the file's presence has to do; the download refuses to run then."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= 0:
        return False
    if probe is None:
        probe = shutil.which("ffprobe") is not None
    return True if not probe else probe_seconds(path) >= MIN_CLIP_S


def _tools_missing() -> str:
    """A sentence when ffmpeg or ffprobe is not on PATH (the pack cannot be made or checked without them), else ""."""
    gone = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if not gone:
        return ""
    return (f"{' and '.join(gone)} {'is' if len(gone) == 1 else 'are'} not on PATH (ffprobe ships with ffmpeg), so the pack "
            "cannot be made or checked. Install ffmpeg and press Download again.")


def _seconds(clip: dict) -> float:
    try:
        return max(0.0, float(clip.get("seconds") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _estimate(clips: list[dict]) -> int:
    return int(sum(_seconds(c) for c in clips) * BYTES_PER_SECOND)


def _where(sources: dict) -> str:
    """Where the list's clips come from, for the Setup row: archive.org, and NASA's library when a source is there."""
    nasa = any(str((s or {}).get("url") or "").startswith(NASA) for s in sources.values() if isinstance(s, dict))
    return "archive.org and NASA's video library" if nasa else "archive.org"


def _films(manifest: dict) -> int:
    return len({str(c.get("source")) for c in manifest.get("clips") or [] if c.get("source")})


def _url(sources: dict, clip: dict) -> str:
    return str((sources.get(str(clip.get("source") or "")) or {}).get("url") or "")


def _crop(sources: dict, clip: dict) -> str:
    """The bars a clip's window is cut free of: its own ``crop``, else its source's (a version 1 list), else none."""
    return str(clip.get("crop") or (sources.get(str(clip.get("source") or "")) or {}).get("crop") or "")


def previous_rows(root: Path) -> dict[str, dict]:
    """What the last run recorded in ``pack.json``, by file name ({} when there is none or it will not read): the start,
    seconds and url each clip was cut with, so a clip whose window the list has since moved is made again, and which
    files the pack made, so one that left the list is removed and a file of the user's never is."""
    try:
        data = json.loads((Path(root) / "pack.json").read_text(encoding="utf-8"))
        rows = (data.get("clips") or []) if isinstance(data, dict) else []
    except (OSError, ValueError):
        return {}
    return {str(r.get("file")): r for r in rows if isinstance(r, dict) and r.get("file")}


def _same_window(record: dict, clip: dict, url: str, crop: str = "") -> bool:
    """Whether a recorded clip was cut from the window the list names now (its start, its seconds, its source url and
    the source's crop)."""
    try:
        return (abs(float(record.get("start") or 0.0) - float(clip.get("start") or 0.0)) < 1e-3
                and abs(float(record.get("seconds") or 0.0) - float(clip.get("seconds") or 0.0)) < 1e-3
                and str(record.get("url") or "") == str(url or "")
                and str(record.get("crop") or "") == str(crop or ""))
    except (TypeError, ValueError):
        return False


def status() -> dict:
    """The Setup row, with the keys a model row has so the page draws it with the same code. Never raises: a list that
    will not read, or a folder that cannot be looked at, is a row whose detail says so. ``bytes`` is what is on disk for
    the clips that are here plus the estimate for the rest; ``stale`` counts clips cut with other times than the list
    has now (Download again remakes them)."""
    from xenoform.models_setup import size_label

    row = {"id": ID, "name": "Free film pack", "required": False, "badge": BADGE, "manual": False, "present": False,
           "count": 0, "total": 0, "films": 0, "stale": 0, "folder": "", "bytes": 0, "size_label": "0 B", "files": [], "detail": ""}
    try:
        manifest = load_manifest()
    except (OSError, ValueError) as exc:
        log.warning("film pack manifest unreadable: %s", exc)
        reason = plain_error(exc).rstrip(".")
        return {**row, "detail": f"The clip list (configs/film_pack.json) could not be read, so there is nothing to download. {reason}."}
    try:
        clips = list(manifest.get("clips") or [])
        sources = dict(manifest.get("sources") or {})
        root = folder(manifest, create=False)
        files = [clip_name(c, i) for i, c in enumerate(clips)]
        tools = _tools_missing()
        probe = shutil.which("ffprobe") is not None
        here = [name for name in files if clip_ready(root / name, probe=probe)]
        previous = previous_rows(root) if here else {}
        stale = [name for name, clip in zip(files, clips)
                 if name in here and name in previous and not _same_window(previous[name], clip, _url(sources, clip), _crop(sources, clip))]
        total, count, films = len(clips), len(here), _films(manifest)
        on_disk = sum((root / name).stat().st_size for name in here)
        nbytes = on_disk + _estimate([c for name, c in zip(files, clips) if name not in here])
        size = size_label(nbytes)
        where = _where(sources)
        present = total > 0 and count == total
        if total == 0:
            detail = "The clip list is empty, so there is nothing to download yet."
        elif present:
            detail = f"{count} clips from {films} public-domain films, {size}, in {root}. Each was pulled from {where}; CREDITS.md beside them names every film."
            if stale:
                detail += (f" {len(stale)} {'was' if len(stale) == 1 else 'were'} cut with older times than the list has now: "
                           f"Download again remakes {'it' if len(stale) == 1 else 'them'}.")
        elif count:
            detail = f"{count} of {total} clips from {films} public-domain films are in {root}. Download pulls the rest from {where} (about {size} in all)."
        else:
            detail = f"{total} clips from {films} public-domain films, about {size}, pulled from {where} when you press Download. Nothing is shipped in the repo. They go to {root}."
        if tools:
            detail = f"{tools} {detail}"
        return {**row, "name": str(manifest.get("name") or "Free film pack"), "present": present, "count": count, "total": total,
                "films": films, "stale": len(stale), "folder": str(root), "bytes": nbytes, "size_label": size, "detail": detail,
                "files": files, "version": manifest.get("version", 1)}
    except Exception as exc:  # a folder that cannot be looked at, a row the checks above did not foresee: a sentence, not a 500
        log.warning("film pack status: %s", exc)
        return {**row, "name": str(manifest.get("name") or "Free film pack"), "total": len(manifest.get("clips") or []),
                "detail": plain_error(exc)}


def remove(root: Path | None = None, manifest: dict | None = None) -> int:
    """Delete the pack's clips (the list's names and the names ``pack.json`` records), part files, sidecars and fetched
    sources. Other files in the folder are not touched. Returns how many clips went."""
    root = root if root is not None else folder()
    names: set[str] = set(previous_rows(root))
    try:
        manifest = manifest or load_manifest()
        names |= {clip_name(c, i) for i, c in enumerate(manifest.get("clips") or [])}
    except (OSError, ValueError):
        pass
    gone = 0
    for name in sorted(names):
        path = root / name
        if path.is_file():
            path.unlink()
            gone += 1
    for path in list(root.glob("*.part.mp4")):
        path.unlink(missing_ok=True)
    for name in ("CREDITS.md", "pack.json", "labels.json"):
        (root / name).unlink(missing_ok=True)
    shutil.rmtree(root / "_src", ignore_errors=True)
    _PROBED.clear()
    return gone


# ---------------------------------------------------------------- the download
_JOB: dict[str, Any] = {"status": "idle", "progress": 0, "detail": "", "error": None}
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None


def download_status() -> dict:
    with _LOCK:
        return dict(_JOB)


def _set(**fields: Any) -> None:
    with _LOCK:
        _JOB.update(fields)


def _reset_for_tests() -> None:
    wait(30)
    with _LOCK:
        _JOB.clear()
        _JOB.update({"status": "idle", "progress": 0, "detail": "", "error": None})
    _PROBED.clear()


def wait(timeout: float = 600.0) -> dict:
    """Join the running download (tests, scripts). Returns the status."""
    thread = _THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout)
    return download_status()


def start() -> dict:
    """Start the download on a background thread and answer at once. A second call while it runs answers the same."""
    global _THREAD
    if offline():
        raise PlainError("XENO_OFFLINE is set, so nothing is fetched from archive.org. Unset it and press Download again.")
    with _LOCK:
        if _JOB.get("status") == "running":
            return dict(_JOB)
        _JOB.update({"status": "running", "progress": 0.0, "detail": "Starting", "error": None})
    _THREAD = threading.Thread(target=_run, daemon=True, name="xenoform-film-pack")
    _THREAD.start()
    return download_status()


def _run_ffmpeg(cmd: list[str], *, timeout: float) -> None:
    """The ffmpeg call. Raises on a non-zero exit or a timeout (subprocess kills the child)."""
    from xenoform.video import ffmpeg_bin

    subprocess.run([ffmpeg_bin()] + list(cmd), check=True, capture_output=True, timeout=timeout)


def _fetch_whole(url: str, dest: Path, *, expected_bytes: int, on_progress: Callable[[float, str], None]) -> Path:
    """A whole source, with resume. The server's size wins over the manifest's estimate when it answers a HEAD."""
    from xenoform.models_setup import download_file

    size = _content_length(url) or int(expected_bytes or 0)
    return download_file(url, dest, sha256="", expected_bytes=size, on_progress=on_progress)


def _content_length(url: str) -> int:
    try:
        with urlopen(Request(url, method="HEAD"), timeout=30) as response:
            return int(response.headers.get("Content-Length") or 0)
    except (OSError, ValueError):
        return 0


RUNNER: Callable[..., None] = _run_ffmpeg
FETCHER: Callable[..., Path] = _fetch_whole


def ffmpeg_args(source: str, start: float, seconds: float, dest: Path, crop: str = "") -> list[str]:
    """The window cut: input seeking before ``-i`` (a byte-range read over http), silent, the source's baked-in bars
    cropped off when it has a ``crop``, at most 1280 wide, 24 fps."""
    vf = (f"crop={crop}," if crop else "") + SCALE
    return ["-y", "-v", "error", "-nostdin", "-ss", f"{max(0.0, float(start)):.3f}", "-i", str(source), "-t", f"{float(seconds):.3f}",
            "-an", "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-movflags", "+faststart", str(dest)]


def _cut(source: str, clip: dict, dest: Path, crop: str = "") -> None:
    """One clip, three tries with a short wait, a timeout an attempt. Raises the last error."""
    seconds = float(clip.get("seconds") or 0.0)
    timeout = seconds * 20 + 60
    part = dest.with_name(dest.stem + ".part.mp4")
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        part.unlink(missing_ok=True)
        try:
            RUNNER(ffmpeg_args(source, float(clip.get("start") or 0.0), seconds, part, crop), timeout=timeout)
            if not clip_ready(part):
                raise RuntimeError(f"{part.name} came back shorter than a second")
            part.replace(dest)
            _PROBED.pop(str(dest), None)
            return
        except Exception as exc:  # a dropped connection, a timeout, a bad window: try again
            last = exc
            err = getattr(exc, "stderr", b"") or b""
            tail = err.decode("utf-8", "replace").strip()[-300:] if isinstance(err, bytes) else str(err)[-300:]
            log.warning("film pack %s try %d failed: %s %s", clip.get("id"), attempt + 1, exc, tail)
            if attempt + 1 < ATTEMPTS:
                time.sleep(RETRY_WAIT_S)
    part.unlink(missing_ok=True)
    raise last or RuntimeError("ffmpeg did not run")


def _whole_name(url: str, key: str) -> str:
    return Path(url.split("?", 1)[0]).name or f"{key}.bin"


def _run() -> None:
    made: list[dict] = []
    failed: list[dict] = []
    removed: list[str] = []
    manifest: dict = {}
    root: Path | None = None
    ran = False  # sidecars are written only once the list was read, the tools were there and the clips were gone through
    try:
        manifest = load_manifest()
        root = folder(manifest)
        clips = list(manifest.get("clips") or [])
        sources = dict(manifest.get("sources") or {})
        total = len(clips)
        if not total:
            raise PlainError("The clip list (configs/film_pack.json) is empty, so there is nothing to download.")
        tools = _tools_missing()
        if tools:  # said once, before any clip, rather than three failed tries a clip
            raise PlainError(tools)
        ran = True
        previous = previous_rows(root)  # what the last run cut, by file name
        by_id = {str(r.get("id")): r for r in previous.values() if r.get("id")}
        expected = {clip_name(c, i) for i, c in enumerate(clips)}
        whole_here: dict[str, Path] = {}
        whole_failed: dict[str, Exception] = {}  # a whole source that would not come is not asked for again this run
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for i, clip in enumerate(clips):
            title = clip_label(clip)
            dest = clip_path(clip, i, root)
            src = sources.get(str(clip.get("source") or "")) or {}
            url = str(src.get("url") or "")
            crop = _crop(sources, clip)
            row = {"id": clip.get("id"), "file": dest.name, "source": clip.get("source"), "url": src.get("url"),
                   "start": clip.get("start"), "seconds": clip.get("seconds"), "title": clip.get("title"), "label": title}
            if crop:
                row["crop"] = crop
            row.update(fields_of(clip))  # version 2: what the cutter reads (own_media.scan hands it on)
            _set(status="running", progress=round(i / total, 4), detail=f"Clip {i + 1} of {total}: {title}", error=None)
            record = previous.get(dest.name)
            if clip_ready(dest) and (record is None or _same_window(record, clip, url, crop)):
                made.append({**row, "made_at": (record or {}).get("made_at"), "kept": True})
                continue
            old = by_id.get(str(clip.get("id")))
            if old and old.get("file") != dest.name and _same_window(old, clip, url, crop) and clip_ready(root / str(old["file"])):
                (root / str(old["file"])).replace(dest)  # the list was reordered: the clip moves to its new name, no pull
                _PROBED.pop(str(dest), None)
                _PROBED.pop(str(root / str(old["file"])), None)
                made.append({**row, "made_at": old.get("made_at"), "kept": True, "was": old["file"]})
                continue
            try:
                if not url:
                    raise PlainError(f"The clip list names no source for {title}.")
                source = url
                if src.get("whole"):
                    key = str(clip.get("source"))
                    if key in whole_failed:
                        raise whole_failed[key]
                    if key not in whole_here:
                        local = root / "_src" / _whole_name(url, key)

                        def on_progress(frac: float, detail: str, *, base=i, _title=title) -> None:
                            _set(status="running", progress=round((base + 0.9 * min(1.0, max(0.0, frac))) / total, 4),
                                 detail=f"Clip {base + 1} of {total}: {_title}. Fetching the whole film: {detail}", error=None)

                        try:
                            whole_here[key] = Path(FETCHER(url, local, expected_bytes=int(src.get("bytes") or 0), on_progress=on_progress))
                        except Exception as exc:
                            whole_failed[key] = exc
                            raise
                    source = str(whole_here[key])
                _cut(source, clip, dest, crop)
                made.append({**row, "made_at": now, "kept": False})
            except Exception as exc:
                log.warning("film pack %s not made: %s", clip.get("id"), exc)
                failed.append({**row, "error": plain_error(exc)})
                if record is not None and clip_ready(dest):  # the older cut stays on disk, and on record as what it is
                    made.append({**record, "kept": True, "stale": True})
        for name in sorted(previous):
            if name not in expected and (root / name).is_file():  # a file the pack made for a clip that has left the list
                (root / name).unlink()
                _PROBED.pop(str(root / name), None)
                removed.append(name)
        src_dir = root / "_src"
        if src_dir.is_dir():  # a whole film has served once its clips are in place; one a clip still needs stays for the retry
            keep = {_whole_name(_url(sources, f), str(f.get("source"))) for f in failed
                    if (sources.get(str(f.get("source"))) or {}).get("whole")}
            # only the whole films this list fetches: anything else in a _src of a folder of your own stays put
            ours = {_whole_name(_url(sources, c), str(c.get("source"))) for c in clips
                    if (sources.get(str(c.get("source"))) or {}).get("whole")}
            for path in list(src_dir.iterdir()):
                base = path.name.removesuffix(".part")
                if path.is_file() and base in ours and base not in keep:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as exc:  # held open by a player or a scanner: it goes on the next run
                        log.warning("film pack: %s not removed: %s", path.name, exc)
            try:
                if not any(src_dir.iterdir()):
                    src_dir.rmdir()
            except OSError:
                pass
        done = sum(1 for m in made if not m.get("stale"))
        gone = f" {len(removed)} that left the list {'was' if len(removed) == 1 else 'were'} removed." if removed else ""
        if failed:
            names = ", ".join(str(f.get("label") or f.get("id")) for f in failed)
            _set(status="error", progress=round(done / total, 4),
                 detail=f"{done} of {total} clips are in place. These did not come: {names}. Press Download to try them again.{gone}",
                 error=f"These clips did not come: {names}.")
        else:
            _set(status="done", progress=1.0, detail=f"{done} clips from {_films(manifest)} films are in place in {root}.{gone}", error=None)
    except Exception as exc:
        _set(status="error", progress=0, detail=plain_error(exc), error=plain_error(exc))
    finally:
        if ran and root is not None and manifest:
            try:
                write_sidecars(manifest, root, made, failed, removed)
            except OSError as exc:
                log.warning("film pack sidecars not written: %s", exc)


# ---------------------------------------------------------------- the sidecars
def item_url(source: dict) -> str:
    """The page a source is credited to: its ``page`` (a NASA library page), else its archive.org item's page, else its
    file's URL."""
    page = str(source.get("page") or "").strip()
    if page:
        return page
    item = str(source.get("item") or "").strip()
    if not item:
        url = str(source.get("url") or "")
        item = url[len(ARCHIVE):].split("/", 1)[0] if url.startswith(ARCHIVE) else ""
    return f"https://archive.org/details/{item}" if item else str(source.get("url") or "")


def _size_text(n: int) -> str:
    """A source file's size for the credits: megabytes to one place, and the bytes."""
    return f"{n / 1e6:.1f} MB ({n:,} bytes)" if n >= 100_000 else f"{n:,} bytes"


def credits_text(manifest: dict, made: list[dict], failed: list[dict] | None = None) -> str:
    """The pack's CREDITS.md: each source the clips use (its title, year, maker, page and licence line, and, when the list
    names it, the file taken and its size), then each clip with its window and, in version 2, its colour and mood."""
    sources = dict(manifest.get("sources") or {})
    used = []
    for key in [str(c.get("source")) for c in manifest.get("clips") or []]:
        if key in sources and key not in used:
            used.append(key)
    lines = ["# Free film pack", "",
             "Public-domain film clips pulled from archive.org (and NASA's own library) by Xenoform's Setup & models, for",
             f"Morph: Your clips. Nothing here is part of the Xenoform repository; the list is configs/film_pack.json (version "
             f"{manifest.get('version', 1)}).",
             f"Written {datetime.now(timezone.utc).strftime('%d %B %Y')}.", "", "## Sources", ""]
    for key in used:
        s = sources[key]
        line = f"- **{s.get('title', key)}** ({s.get('year', '')}), {s.get('maker', '')}. {item_url(s)}. {s.get('licence', '')}".replace(" ()", "")
        taken = str(s.get("file") or "").strip()
        try:
            size = int(s.get("bytes") or 0)
        except (TypeError, ValueError):
            size = 0
        if taken:  # version 2: the derivative each window was read from, and how big that file is
            line += f" File taken: {taken}" + (f", {_size_text(size)}" if size else "") + ("; downloaded whole." if s.get("whole") else ".")
        lines.append(line)
    rich = any(k in c for c in manifest.get("clips") or [] for k in FIELDS)
    if rich:
        lines += ["", "## Clips", "", "| File | Film | Start (s) | Seconds | Clip | Colour | Mood |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
    else:
        lines += ["", "## Clips", "", "| File | Film | Start (s) | Seconds | Clip |", "| --- | --- | --- | --- | --- |"]
    for i, c in enumerate(manifest.get("clips") or []):
        s = sources.get(str(c.get("source")), {})
        row = f"| {clip_name(c, i)} | {s.get('title', c.get('source'))} | {c.get('start')} | {c.get('seconds')} | {clip_label(c)} |"
        if rich:
            colour = {True: "colour", False: "black-and-white"}.get(c.get("colour"), "")
            row += f" {colour} | {c.get('mood') or ''} |"
        lines.append(row)
    if failed:
        lines += ["", "Not made on the last run: " + ", ".join(str(f.get("label") or f.get("id")) for f in failed) + "."]
    return "\n".join(lines) + "\n"


def label_entry(clip: dict) -> str | dict:
    """What labels.json says of a pack clip: its label, or with version 2 fields ``{"label", "colour", "motion", "living",
    "mood"}`` (``own_media.scan`` reads either)."""
    fields = fields_of(clip)
    return {"label": clip_label(clip), **fields} if fields else clip_label(clip)


def write_sidecars(manifest: dict, root: Path, made: list[dict], failed: list[dict], removed: list[str] | None = None) -> None:
    """``CREDITS.md``, ``pack.json`` and ``labels.json`` beside the clips, every run. ``pack.json``'s ``clips`` are the
    files on disk with the window each was cut from (``kept`` when a run found it there, ``was`` the name it moved from,
    ``stale`` when an older cut stays because the remake failed); ``removed`` names the files this run took away."""
    root = Path(root)
    credits = root / "CREDITS.md"
    try:  # a CREDITS.md of your own in a folder XENO_FILM_PACK points at is yours: only the pack's own is rewritten
        ours = not credits.is_file() or credits.read_text(encoding="utf-8", errors="replace").startswith("# Free film pack")
    except OSError:
        ours = False
    if ours:
        credits.write_text(credits_text(manifest, made, failed), encoding="utf-8")
    pack = {"made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "manifest_version": manifest.get("version", 1),
            "name": manifest.get("name"), "folder": str(root), "clips": made, "failed": failed, "removed": list(removed or [])}
    (root / "pack.json").write_text(json.dumps(pack, indent=1), encoding="utf-8")
    labels = {clip_name(c, i): label_entry(c) for i, c in enumerate(manifest.get("clips") or [])}
    try:  # the labels you gave your own clips stay; the pack's names are the pack's, a moved or removed clip's goes
        before = json.loads((root / "labels.json").read_text(encoding="utf-8"))
        before = {str(k): v for k, v in before.items() if str(k) not in labels and (root / str(k)).is_file()} if isinstance(before, dict) else {}
    except (OSError, ValueError):
        before = {}
    (root / "labels.json").write_text(json.dumps({**before, **labels}, indent=1, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- the route
@router.get("/api/film_pack")
def film_pack_status() -> dict:
    """The pack for the desk's Your clips row: ``status()`` with ``download`` (the running job, if any)."""
    return {**status(), "download": download_status()}


__all__ = ["ID", "BADGE", "load_manifest", "folder", "clip_path", "clip_name", "clip_label", "status", "start", "wait",
           "download_status", "remove", "clip_ready", "probe_seconds", "previous_rows", "ffmpeg_args", "credits_text",
           "write_sidecars", "fields_of", "label_entry", "FIELDS", "MOODS", "router"]
