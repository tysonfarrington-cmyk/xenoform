"""Local director desk. `xenoform ui` serves this app."""

from __future__ import annotations

import logging
import math
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import File, HTTPException, Request, UploadFile

from xenoform.analyze import read_features
from xenoform.config import load_config
from xenoform.director import (
    RecipeError,
    decode_recipe,
    encode_recipe,
    public_forms,
    public_presets,
    public_transitions,
    register_by_id,
    session_payload,
)
from xenoform.storyboard import (
    blocks_from_scenes,
    pick_treatment,
    pitch_treatments,
    plan_with_hook,
    stamp_treatment,
    style_bible,
)

log = logging.getLogger("xenoform")

_JOBS: dict[str, dict[str, Any]] = {}
_ANIMATICS: dict[str, Path] = {}
_CANCEL: dict[str, threading.Event] = {}
_AUDIO: dict[str, Path] = {}
_FEATURES: dict[str, dict] = {}
_FORMS: dict[str, Path] = {}
_NOTES: dict[str, dict[str, Any]] = {}
_GUIDES: dict[str, Path] = {}
_HEROES: dict[str, Path] = {}
_JUDGE_HITS: dict[str, list[float]] = {}
_JUDGE_LIMIT = 6
_JUDGE_WINDOW = 60.0
_LOCK = threading.Lock()
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_BASE_RE = re.compile(r"/[A-Za-z0-9._/-]{0,120}")
# A six-minute 48 kHz stereo 24-bit wav is about 99 MB. 120 MB leaves headroom.
_MAX_UPLOAD_BYTES = 120 * 1024 * 1024
_MAX_RUNNING_JOBS = 2
_MAX_JUDGE_SECONDS = 1200.0
_MAX_JUDGE_BEATS = 8000
_MAX_JUDGE_SCENES = 80


def _judge_allowed(ip: str) -> bool:
    now = time.monotonic()
    with _LOCK:
        hits = [stamp for stamp in _JUDGE_HITS.get(ip, []) if now - stamp < _JUDGE_WINDOW]
        if len(hits) >= _JUDGE_LIMIT:
            _JUDGE_HITS[ip] = hits
            return False
        hits.append(now)
        _JUDGE_HITS[ip] = hits
        return True


def repo_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parents[2], Path.cwd(), here.parents[1]]
    for candidate in candidates:
        if (candidate / "examples" / "demo_features.json").exists():
            return candidate
    return Path.cwd()


def work_dir() -> Path:
    path = repo_root() / "work" / "ui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lessons_file() -> Path:
    return repo_root() / "lessons.json"


def lessons_log() -> Path:
    return repo_root() / "docs" / "LESSONS.md"


def storage_id(value: str, *, fallback: str = "demo") -> str:
    """A name safe to use as one path segment under work/ui."""
    text = str(value or "").strip() or fallback
    if not _ID_RE.fullmatch(text):
        raise HTTPException(400, "That id is not a name this desk can store.")
    return text


def coerce_storage_id(value: str) -> str:
    """Turn a filename stem into a storage id. A bad stem gets a fresh id."""
    text = re.sub(r"[^A-Za-z0-9_-]", "", str(value or ""))[:64]
    if _ID_RE.fullmatch(text or ""):
        return text
    return uuid.uuid4().hex[:10]


def desk_base(value: str) -> str:
    """A path prefix for the Comfy proxy. Anything else is ignored."""
    text = str(value or "").strip()
    if not text or ".." in text or not _BASE_RE.fullmatch(text):
        return ""
    return text.rstrip("/")


async def read_upload(file: UploadFile) -> bytes:
    cap = int(_MAX_UPLOAD_BYTES)
    payload = await file.read(cap + 1)
    if len(payload) > cap:
        raise HTTPException(413, "That file is larger than this desk will store. A six-minute wav still fits.")
    return payload


def resolve_video(url: str) -> Path | None:
    """Demo mp4, or a job file that already lives under work/ui/jobs."""
    raw = str(url or "").split("?", 1)[0]
    if raw in {"", "/media/demo"}:
        path = repo_root() / "examples" / "demo_base.mp4"
        return path if path.exists() else None
    marker = "/api/jobs/"
    if marker not in raw:
        return None
    job_id = raw.split(marker, 1)[1].split("/", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9]{1,64}", job_id):
        return None
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job or not job.get("path"):
        return None
    path = Path(job["path"]).resolve()
    root = (work_dir() / "jobs").resolve()
    if path != root and root not in path.parents:
        return None
    return path


def _inline_markdown(text: str) -> str:
    import html as html_lib
    import re

    escaped = html_lib.escape(text)

    def link(match: re.Match) -> str:
        label = match.group(1)
        href = html_lib.escape(match.group(2), quote=True)
        return f'<a href="{href}">{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _render_markdown(text: str) -> str:
    """Enough of Markdown for the licence and credits notes. No raw HTML."""
    lines = text.splitlines()
    parts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and set(lines[index + 1].replace("|", "").replace("-", "").replace(":", "").strip()) <= {""}:
            rows = []
            while index < len(lines) and lines[index].startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                rows.append(cells)
                index += 1
            head, body = rows[0], rows[2:]
            parts.append("<table><thead><tr>" + "".join(f"<th>{_inline_markdown(cell)}</th>" for cell in head) + "</tr></thead><tbody>")
            for row in body:
                parts.append("<tr>" + "".join(f"<td>{_inline_markdown(cell)}</td>" for cell in row) + "</tr>")
            parts.append("</tbody></table>")
            continue
        if line.startswith("### "):
            parts.append(f"<h3>{_inline_markdown(line[4:])}</h3>")
        elif line.startswith("## "):
            parts.append(f"<h2>{_inline_markdown(line[3:])}</h2>")
        elif line.startswith("# "):
            parts.append(f"<h1>{_inline_markdown(line[2:])}</h1>")
        elif line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(f"<li>{_inline_markdown(lines[index][2:])}</li>")
                index += 1
            parts.append("<ul>" + "".join(items) + "</ul>")
            continue
        else:
            paragraph = [line.strip()]
            index += 1
            while index < len(lines) and lines[index].strip() and not lines[index].startswith(("#", "-", "|")):
                paragraph.append(lines[index].strip())
                index += 1
            parts.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            continue
        index += 1
    return "\n".join(parts)


def critic_notes_for(scenes: list, features: dict, saved: list) -> list:
    """Board and lesson flags, without sampling frames."""
    from xenoform.notes import critic_notes

    return critic_notes(None, features, scenes, fps=float(features.get("fps") or 24), lessons=saved).get("notes") or []


def load_desk_config(path: str | None = None) -> dict:
    if path:
        return load_config(path)
    example = repo_root() / "configs" / "example.json"
    if example.exists():
        return load_config(example)
    return load_config(None)


def _demo_features() -> dict:
    return read_features(repo_root() / "examples" / "demo_features.json")


def create_app(cfg: dict | None = None):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    cfg = cfg or load_desk_config()
    try:
        from xenoform.demo_assets import ensure_demo_assets

        ensure_demo_assets()
    except Exception:
        log.exception("demo assets")
    static = Path(__file__).resolve().parent / "ui_static"
    app = FastAPI(title="Xenoform", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=static), name="static")

    def _desk_html(base: str) -> str:
        html = (static / "index.html").read_text(encoding="utf-8")
        html = html.replace('window.XENO_BASE=""', f'window.XENO_BASE="{base}"', 1)
        if base:
            html = html.replace('href="/static/', f'href="{base}/static/')
            html = html.replace('src="/static/', f'src="{base}/static/')
            html = html.replace('href="/judges"', f'href="{base}/judges"')
            html = html.replace('href="/licences"', f'href="{base}/licences"')
            html = html.replace('href="/credits"', f'href="{base}/credits"')
        return html

    @app.get("/")
    def index(request: Request):
        from fastapi.responses import HTMLResponse

        base = desk_base(request.headers.get("x-xeno-base", ""))
        return HTMLResponse(_desk_html(base))

    @app.get("/judges")
    def judges(request: Request):
        from fastapi.responses import HTMLResponse

        base = desk_base(request.headers.get("x-xeno-base", ""))
        html = (static / "judges.html").read_text(encoding="utf-8")
        prefix = f"{base}/static/" if base else "/static/"
        html = html.replace("<head>", f'<head><base href="{prefix}">', 1)
        if base:
            html = html.replace('href="/licences"', f'href="{base}/licences"')
            html = html.replace('href="/credits"', f'href="{base}/credits"')
        return HTMLResponse(html)

    def _markdown_page(request: Request, title: str, path: Path) -> HTMLResponse:
        from fastapi.responses import HTMLResponse
        import html as html_lib

        base = desk_base(request.headers.get("x-xeno-base", ""))
        text = path.read_text(encoding="utf-8") if path.is_file() else "This note is missing."
        body = _render_markdown(text)
        static_href = f"{base}/static/" if base else "/static/"
        home = f"{base}/" if base else "/"
        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html_lib.escape(title)}</title>
  <link rel="stylesheet" href="{static_href}theme.css" />
  <link rel="stylesheet" href="{static_href}app.css" />
</head>
<body>
  <header class="top">
    <a class="brand" href="{home}"><strong>Xenoform</strong></a>
    <a class="ow-badge" href="{base}/licences">Open weights</a>
    <a href="{base}/credits">Picture credits</a>
  </header>
  <main class="judges"><article class="panel doc">{body}</article></main>
</body>
</html>"""
        return HTMLResponse(page)

    @app.get("/licences")
    def licences_page(request: Request):
        return _markdown_page(request, "Xenoform licences", repo_root() / "docs" / "LICENCES.md")

    @app.get("/credits")
    def credits_page(request: Request):
        return _markdown_page(request, "Xenoform credits", repo_root() / "CREDITS.md")

    @app.get("/media/audio/{audio_id}")
    def media_audio(audio_id: str) -> FileResponse:
        if audio_id == "demo":
            path = repo_root() / "examples" / "demo.wav"
        else:
            with _LOCK:
                path = _AUDIO.get(audio_id)
        if path is None or not Path(path).exists():
            raise HTTPException(404, "That song is not loaded.")
        return FileResponse(path)

    def _music_file(audio_id: str) -> FileResponse:
        from xenoform.timing import export_music

        audio_id = storage_id(audio_id)
        if audio_id == "demo" or not audio_id:
            source = repo_root() / "examples" / "demo.wav"
        else:
            with _LOCK:
                source = _AUDIO.get(audio_id)
        if source is None or not Path(source).exists():
            raise HTTPException(404, "That song is not loaded.")
        dest = work_dir() / "exports" / f"{audio_id}-music.m4a"
        export_music(Path(source), dest)
        return FileResponse(dest, media_type="audio/mp4", filename=dest.name)

    @app.get("/api/v1/music")
    def music_get(audio_id: str = "demo") -> FileResponse:
        return _music_file(audio_id)

    @app.post("/api/v1/export/music")
    def music_post(body: dict | None = None) -> FileResponse:
        audio_id = str((body or {}).get("audio_id") or "demo")
        return _music_file(audio_id)

    @app.get("/media/guides/{guide_id}")
    def guide_media(guide_id: str) -> FileResponse:
        with _LOCK:
            path = _GUIDES.get(guide_id)
        if path is None or not Path(path).exists():
            raise HTTPException(404, "That recording is gone.")
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/live/record")
    async def live_record(file: UploadFile = File(...)) -> dict:
        from xenoform.errors import plain_error
        from xenoform.live_mode import webm_to_mp4

        payload = await read_upload(file)
        if not payload:
            raise HTTPException(400, "The recording was empty.")
        guide_id = uuid.uuid4().hex[:10]
        folder = work_dir() / "guides"
        folder.mkdir(parents=True, exist_ok=True)
        raw = folder / f"{guide_id}.webm"
        dest = folder / f"{guide_id}.mp4"
        raw.write_bytes(payload)
        try:
            webm_to_mp4(raw, dest)
        except Exception as exc:
            raise HTTPException(400, f"The recording did not become an mp4. {plain_error(exc)}") from exc
        with _LOCK:
            _GUIDES[guide_id] = dest
        return {
            "id": guide_id,
            "url": f"/media/guides/{guide_id}",
            "detail": "Recorded. This mp4 is the shareable Live cut, and a motion guide for Turbo, Draft, and Final.",
        }

    @app.get("/media/demo")
    def demo_video() -> FileResponse:
        path = repo_root() / "examples" / "demo_base.mp4"
        if not path.exists():
            raise HTTPException(404, "examples/demo_base.mp4 is missing")
        return FileResponse(path, media_type="video/mp4")

    @app.get("/media/poster")
    def poster() -> FileResponse:
        path = static / "poster.jpg"
        if not path.exists():
            raise HTTPException(404, "poster missing")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/media/forms/{form_id}")
    def form_image(form_id: str) -> FileResponse:
        path = _FORMS.get(form_id)
        if path is None or not path.exists():
            raise HTTPException(404, "No image for that form")
        return FileResponse(path)

    @app.get("/api/demo")
    def demo() -> dict:
        features = _demo_features()
        payload = session_payload(
            features,
            audio_id="demo",
            title="Demo assembly",
            video="/media/demo",
            endpoint=str(cfg["comfy"].get("base_url") or "http://127.0.0.1:8188"),
        )
        payload["reference"] = "examples/demo_base.mp4"
        return payload

    @app.get("/api/catalog")
    def catalog() -> dict:
        return {
            "forms": public_forms(),
            "presets": public_presets(),
            "transitions": public_transitions(),
        }

    @app.post("/api/analyze")
    async def analyze(file: UploadFile = File(...)) -> dict:
        import librosa

        from xenoform.analyze import analyze_audio

        suffix = Path(file.filename or "song.wav").suffix.lower() or ".wav"
        if suffix not in {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}:
            suffix = ".wav"
        audio_id = uuid.uuid4().hex[:10]
        dest = work_dir() / "uploads" / f"{audio_id}{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await read_upload(file))
        try:
            audio, sr = librosa.load(dest, sr=None, mono=True)
            features = analyze_audio(
                audio,
                int(sr),
                fps=float(cfg["fps"]),
                onset_tau=float(cfg["analyze"]["onset_tau"]),
                beat_tau=float(cfg["analyze"]["beat_tau"]),
                section_min_seconds=float(cfg["analyze"]["section_min_seconds"]),
            )
        except Exception as exc:
            from xenoform.errors import audio_read_error

            log.exception("analyze failed")
            raise HTTPException(400, audio_read_error(exc)) from exc
        with _LOCK:
            _AUDIO[audio_id] = dest
            _FEATURES[audio_id] = features
        title = Path(file.filename or "Song").stem
        payload = session_payload(
            features,
            audio_id=audio_id,
            title=title,
            video="",
            endpoint=str(cfg["comfy"].get("base_url") or ""),
        )
        payload["video_label"] = "No picture yet — generate a cut"
        payload["reference"] = ""
        return payload

    @app.post("/api/forms")
    async def add_form(file: UploadFile = File(...)) -> dict:
        suffix = Path(file.filename or "form.png").suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            raise HTTPException(400, "Use a png, jpg, or webp.")
        form_id = "img" + uuid.uuid4().hex[:8]
        dest = work_dir() / "forms" / f"{form_id}{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await read_upload(file))
        with _LOCK:
            _FORMS[form_id] = dest
        noun = Path(file.filename or "photo").stem.replace("_", " ").replace("-", " ")
        return {
            "id": form_id,
            "noun": noun,
            "name": noun,
            "kind": "image",
            "image": f"/media/forms/{form_id}",
            "blurb": "Pinned from a photo on this machine.",
            "accent": "#e7d7c3",
        }

    def _features_for(audio_id: str) -> dict:
        if audio_id == "demo" or not audio_id:
            return _demo_features()
        with _LOCK:
            cached = _FEATURES.get(audio_id)
        if cached is None:
            raise HTTPException(400, "Load a song before rewriting the storyboard.")
        return cached

    @app.post("/api/story")
    def story(body: dict) -> dict:
        """Turn a brief and the current song into scene cards. Offline unless XENO_LLM_URL is set."""
        features = _features_for(str(body.get("audio_id") or "demo"))
        register = register_by_id(str(body.get("register") or "pynchon"))
        climax = body.get("climax")
        if climax is None or climax == "":
            climax = None
        else:
            climax = int(climax)
        rolls = int(body.get("rolls") or 1)
        brief = str(body.get("brief") or "")
        scenes, source = plan_with_hook(
            features,
            register,
            brief,
            customs=list(body.get("customs") or []),
            climax=climax,
            motif=str(body.get("motif") or ""),
            callback=str(body.get("callback") or ""),
            previous=list(body.get("scenes") or []) or None,
            rolls=rolls,
            allow_cloud=bool(body.get("addons")),
        )
        treatment = pick_treatment(brief, str(body.get("treatment") or ""))
        scenes = stamp_treatment(scenes, treatment)
        from xenoform.continuity import continuity_bible, stamp_continuity, story_logic

        scenes = stamp_continuity(scenes, brief)
        treatments = pitch_treatments(brief)
        moments = next(item["moments"] for item in treatments if item["id"] == treatment)
        bible = style_bible(register, str(body.get("preset") or ""), moments=moments)
        return {
            "scenes": scenes,
            "blocks": blocks_from_scenes(scenes),
            "planner": source,
            "climax": next((scene["index"] for scene in scenes if scene.get("beat") == "climax"), None),
            "rolls": rolls,
            "treatments": treatments,
            "treatment": treatment,
            "bible": bible,
            "continuity": continuity_bible(brief, scenes),
            "logic": story_logic(brief, scenes),
        }

    @app.post("/api/recut")
    def recut_route(body: dict) -> dict:
        from xenoform.cutdesk import desk_pass
        from xenoform.turbo import eta_table

        features = _features_for(str(body.get("audio_id") or "demo"))
        cap = body.get("morph_cap", None)
        if cap is not None and cap != "":
            cap = max(0, min(2, int(cap)))
        return desk_pass(
            list(body.get("scenes") or []),
            features,
            energy=body.get("energy") or 0,
            continuous=bool(body.get("continuous")),
            hero_image=str(body.get("hero_image") or ""),
            hero_name=str(body.get("hero_name") or ""),
            flash=str(body.get("flash") or "normal"),
            brief=str(body.get("brief") or ""),
            quality=str(body.get("quality") or "live"),
            etas=eta_table(),
            morph_cap=cap,
        )

    @app.post("/api/morph/board")
    def morph_board(body: dict) -> dict:
        from xenoform.morph import plan_board

        report = plan_board(
            list(body.get("scenes") or []),
            list(body.get("beats") or []),
            str(body.get("method") or "keyframe-blend"),
            brief=str(body.get("brief") or ""),
            fast=bool(body.get("fast")),
            lock=bool(body.get("lock")),
            sections=list(body.get("sections") or []),
            drops=list(body.get("drops") or []),
            hit=bool(body.get("hit")),
        )
        for join in report.get("joins") or []:
            join.pop("workflow", None)
        return report

    def _library_folder_arg(body: dict | None = None, folder: str = "") -> str:
        if body:
            return str(body.get("library_folder") or body.get("folder") or folder or "")
        return str(folder or "")

    @app.get("/api/library")
    def library_index(folder: str = "", exclude_faces: str = "true", allow_pd_us: str = "false") -> dict:
        from xenoform.source_library import item_allowed, load_library, poster_path, public_item

        library = load_library(_library_folder_arg(folder=folder), repo_root())
        shown = []
        for item in library.items:
            if not item_allowed(
                item,
                exclude_faces=exclude_faces.strip().lower() not in {"0", "false", "no", "off"},
                allow_pd_us=allow_pd_us.strip().lower() in {"1", "true", "yes", "on"},
            ):
                continue
            row = public_item(item)
            if poster_path(library, item) is not None:
                from urllib.parse import quote

                row["thumb"] = (
                    "/api/library/thumb?id="
                    + quote(str(item["id"]))
                    + "&folder="
                    + quote(str(library.folder))
                )
            else:
                row["thumb"] = ""
            shown.append(row)
        tags = sorted({tag for row in shown for tag in row.get("tags") or []})
        return {
            "folder": str(library.folder),
            "count": len(library.items),
            "shown": len(shown),
            "missing_index": library.missing_index,
            "note": library.note,
            "categories": sorted(category for category in library.categories if category),
            "tags": tags[:80],
            "items": shown[:500],
        }

    @app.get("/api/library/thumb")
    def library_thumb(id: str = "", folder: str = ""):
        from xenoform.source_library import load_library, poster_path

        library = load_library(_library_folder_arg(folder=folder), repo_root())
        item = library.by_id.get(id)
        path = poster_path(library, item) if item else None
        if path is None:
            raise HTTPException(404, "No thumbnail for that item")
        kind = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=kind, headers={"Cache-Control": "no-store"})

    @app.post("/api/library/pick")
    def library_pick(body: dict) -> dict:
        from xenoform.source_library import library_filters, load_library, pick_pair

        library = load_library(_library_folder_arg(body), repo_root())
        picked = pick_pair(library, **library_filters(body))
        picked["note"] = library.note
        picked["count"] = len(library.items)
        picked["missing_index"] = library.missing_index
        return picked

    @app.post("/api/score")
    def score(body: dict) -> dict:
        from xenoform.score import directors_score
        from xenoform.source_library import _exclude_faces, _flag, load_library

        audio_id = str(body.get("audio_id") or "")
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        library = load_library(_library_folder_arg(body), repo_root())
        rows = directors_score(
            features,
            vibe=str(body.get("vibe") or ""),
            library=library,
            pinned=body.get("library_pins") or [],
            banned=body.get("library_bans") or [],
            exclude_faces=_exclude_faces(body.get("exclude_faces", True)),
            allow_pd_us=_flag(body.get("allow_pd_us", False)),
        )
        return {"segments": rows, "count": len(rows)}

    @app.post("/api/opener")
    def opener_route(body: dict) -> dict:
        from xenoform.opener import first_drop
        from xenoform.score import directors_score
        from xenoform.source_library import _exclude_faces, _flag, load_library

        audio_id = str(body.get("audio_id") or "demo")
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        library = load_library(_library_folder_arg(body), repo_root())
        rows = directors_score(
            features,
            vibe=str(body.get("vibe") or ""),
            library=library,
            pinned=body.get("library_pins") or [],
            banned=body.get("library_bans") or [],
            exclude_faces=_exclude_faces(body.get("exclude_faces", True)),
            allow_pd_us=_flag(body.get("allow_pd_us", False)),
        )
        opened = first_drop(features, rows)
        opened.pop("downbeats", None)
        return opened

    @app.post("/api/story/sheet")
    def story_sheet_route(body: dict) -> dict:
        from xenoform.cutdesk import story_sheet
        from xenoform.turbo import eta_table

        return story_sheet(
            str(body.get("brief") or ""),
            list(body.get("scenes") or []),
            str(body.get("quality") or "live"),
            eta_table(),
        )

    @app.post("/api/conform")
    def conform_route(body: dict) -> dict:
        from xenoform.cutdesk import conform_story

        features = _features_for(str(body.get("audio_id") or "demo"))
        scenes = conform_story(list(body.get("scenes") or []), features)
        return {"scenes": scenes, "blocks": blocks_from_scenes(scenes)}

    @app.post("/api/qa")
    def qa_route(body: dict) -> dict:
        from xenoform.cutdesk import qa_report

        features = _features_for(str(body.get("audio_id") or "demo"))
        return qa_report(
            list(body.get("scenes") or []),
            features,
            body.get("energy") or 0,
            str(body.get("flash") or "normal"),
        )

    @app.post("/api/hero")
    async def add_hero(file: UploadFile = File(...)) -> dict:
        suffix = Path(file.filename or "hero.png").suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise HTTPException(400, "Use a png, jpg, or webp.")
        hero_id = uuid.uuid4().hex[:10]
        dest = work_dir() / "heroes" / f"{hero_id}{suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(await read_upload(file))
        with _LOCK:
            _HEROES[hero_id] = dest
        return {
            "id": hero_id,
            "url": f"/media/heroes/{hero_id}",
            "detail": "This picture is the first frame of every shot.",
        }

    @app.get("/media/heroes/{hero_id}")
    def hero_media(hero_id: str) -> FileResponse:
        with _LOCK:
            path = _HEROES.get(hero_id)
        if path is None or not Path(path).exists():
            raise HTTPException(404, "That hero reference is gone.")
        return FileResponse(path)

    @app.post("/api/review/remake")
    def review_remake(body: dict) -> dict:
        from xenoform.craft import pick_take, remake, text_only_shots

        takes = list(body.get("takes") or [])
        scene = int(body.get("scene") or 0)
        seed = int(body.get("seed") or 2727)
        prompt = str(body.get("prompt") or "")
        take, kept = remake(takes, scene=scene, prompt=prompt, seed=seed)
        kept = pick_take(kept, scene=scene, seed=seed)
        before = list(body.get("before") or [])
        after = list(body.get("after") or [])
        if not before and not after:
            only = [f"s{scene}"]
            text_only = True
        else:
            scope = text_only_shots(before, after)
            text_only = scope is not None
            only = [f"s{index}" for index in scope] if text_only else []
        return {"take": take, "takes": kept, "only_scenes": only, "text_only": text_only}

    @app.post("/api/review/frame")
    def review_frame(body: dict) -> FileResponse:
        from xenoform.craft import paint_review_png

        dest = paint_review_png(
            work_dir() / "frames",
            seed=int(body.get("seed") or 2727),
            shot=str(body.get("shot") or "wide"),
            prompt=str(body.get("prompt") or ""),
            index=int(body.get("scene") or 0),
        )
        return FileResponse(dest, media_type="image/png")

    @app.post("/api/timing")
    def timing_route(body: dict) -> dict:
        from xenoform.craft import song_timing

        features = _features_for(str(body.get("audio_id") or "demo"))
        return song_timing(
            features,
            list(body.get("words") or []),
            enabled=bool(body.get("lyrics")),
            offset=float(body.get("offset") or 0.9),
        )

    @app.post("/api/continuity/stills")
    def continuity_stills(body: dict) -> dict:
        from xenoform.continuity import attach_stills, ensure_stills

        elements = ensure_stills(list(body.get("elements") or []), work_dir() / "continuity")
        scenes = attach_stills(list(body.get("scenes") or []), elements)
        public = [
            {
                "id": row.get("id"),
                "kind": row.get("kind"),
                "name": row.get("name"),
                "sentence": row.get("sentence"),
                "still_name": row.get("still_name") or "",
                "url": row.get("url") or "",
                "lock": row.get("lock") or "",
            }
            for row in elements
        ]
        return {"elements": public, "scenes": scenes}

    @app.get("/media/continuity/{name}")
    def continuity_media(name: str) -> FileResponse:
        path = work_dir() / "continuity" / Path(name).name
        if not path.is_file():
            raise HTTPException(404, "That reference still is not painted yet.")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/share")
    def share_route(job: str = "") -> FileResponse:
        from xenoform.craft import share_cut

        source = _share_source(job)
        dest = work_dir() / "share" / "xenoform-720.mp4"
        result = share_cut(source, dest)
        if not result["under"]:
            raise HTTPException(500, "The share file did not fit in 16MB.")
        return FileResponse(dest, media_type="video/mp4", filename="xenoform-720.mp4")

    def _share_source(job: str) -> Path:
        if job:
            with _LOCK:
                record = _JOBS.get(job)
            path = Path(record["path"]) if record and record.get("path") else None
            if path is not None and path.exists():
                return path
        demo = repo_root() / "examples" / "demo_base.mp4"
        if demo.exists():
            return demo
        raise HTTPException(404, "Record or generate a cut before sharing.")

    def _judge_library() -> list[dict]:
        return [
            {"id": "wide", "shot": "wide", "move": "pull back", "action": "Wide shot, the camera pulls back."},
            {"id": "medium", "shot": "medium", "move": "follow", "action": "Medium shot, the camera follows."},
            {"id": "close", "shot": "close", "move": "push in", "action": "Close shot, the camera pushes in."},
            {"id": "reveal", "shot": "reveal", "move": "pull back", "action": "Reveal, the camera pulls back."},
        ]

    @app.post("/api/judges/analyze")
    def judges_analyze(request: Request, body: dict) -> dict:
        from xenoform.cutdesk import desk_pass

        ip = request.client.host if request.client else "local"
        if not _judge_allowed(ip):
            raise HTTPException(429, "The judges desk is busy. Try again in a minute.")
        payload = body or {}
        beats = []
        for beat in payload.get("beats") or []:
            try:
                beats.append(float(beat))
            except (TypeError, ValueError):
                continue
        if len(beats) > _MAX_JUDGE_BEATS:
            raise HTTPException(400, "That song has more beats than this desk will chart.")
        raw_duration = payload.get("duration")
        if raw_duration in (None, ""):
            duration = beats[-1] + 0.5 if beats else 12.0
        else:
            try:
                duration = float(raw_duration)
            except (TypeError, ValueError):
                raise HTTPException(400, "Duration has to be a number of seconds.") from None
        if not math.isfinite(duration):
            raise HTTPException(400, "Duration has to be a finite number of seconds.")
        duration = min(max(duration, 0.5), _MAX_JUDGE_SECONDS)
        incoming = list(payload.get("scenes") or _judge_library())
        if len(incoming) > _MAX_JUDGE_SCENES:
            raise HTTPException(400, "The judges desk takes at most 80 shots.")
        try:
            tempo = float(payload.get("tempo") or 120)
        except (TypeError, ValueError):
            tempo = 120.0
        if not math.isfinite(tempo):
            tempo = 120.0
        width = 4.0
        sections = []
        start = 0.0
        while start < duration - 0.05:
            sections.append({"start": start, "end": min(duration, start + width)})
            start += width
        if not sections:
            sections = [{"start": 0.0, "end": duration}]
        features = {
            "beats": beats,
            "duration": duration,
            "tempo": tempo,
            "sections": sections,
            "drops": payload.get("drops") or ([{"start": beats[len(beats) // 2]}] if beats else []),
        }
        scenes = incoming
        for scene in scenes:
            scene.setdefault("edit", "hard cut")
            scene.setdefault("form", "sphere")
        return desk_pass(scenes, features, energy=payload.get("energy") or 0, quality="live")

    @app.post("/api/recipe/encode")
    def recipe_encode(body: dict) -> dict:
        try:
            code = encode_recipe(body)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"recipe": code}

    @app.post("/api/recipe/decode")
    def recipe_decode(body: dict) -> dict:
        try:
            state = decode_recipe(str(body.get("recipe") or ""))
        except RecipeError as exc:
            raise HTTPException(400, str(exc)) from exc
        state["recipe"] = encode_recipe(state)
        state["forms"] = public_forms(state.get("customs"))
        return state

    def _start_job(body: dict) -> dict:
        audio_id = str(body.get("audio_id") or "demo")
        if audio_id == "demo":
            audio_path = repo_root() / "examples" / "demo.wav"
        else:
            with _LOCK:
                audio_path = _AUDIO.get(audio_id)
        if audio_path is None or not Path(audio_path).exists():
            raise HTTPException(400, "Load a song before generating.")
        guide_id = str(body.get("guide_id") or "")
        if guide_id:
            with _LOCK:
                guide = _GUIDES.get(guide_id)
            if guide is not None and Path(guide).exists():
                body["guide_path"] = str(guide)
        hero_id = str(body.get("hero_id") or "")
        if hero_id:
            with _LOCK:
                hero = _HEROES.get(hero_id)
            if hero is not None and Path(hero).exists():
                body["hero_path"] = str(hero)
        stills = work_dir() / "continuity"
        for scene in body.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            name = Path(str(scene.get("still_name") or "")).name
            if name and (stills / name).is_file():
                scene["reference_still"] = str(stills / name)
        job_id = uuid.uuid4().hex[:8]
        out = work_dir() / "jobs" / job_id / "xenoform.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        cancel_event = threading.Event()
        only = [str(item) for item in (body.get("only_scenes") or []) if str(item)]
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        try:
            from xenoform.source_library import attach_library_credits

            library_info = attach_library_credits(out.parent, body, features, repo_root())
        except Exception:
            log.exception("library credits")
            library_info = {"credits": [], "credits_file": "", "pairs": []}
        job = {
            "id": job_id,
            "status": "running",
            "stage": "analyze",
            "progress": 0.0,
            "detail": "Queued " + ", ".join(only) if only else "Starting",
            "mode": "live" if body.get("live") else "dry-run",
            "quality": str(body.get("quality") or "turbo"),
            "only_scenes": only,
            "video": None,
            "video_version": 0,
            "error": None,
            "path": str(out),
            "credits": library_info.get("credits") or [],
            "credits_file": library_info.get("credits_file") or "",
            "library_pairs": library_info.get("pairs") or [],
        }
        with _LOCK:
            running = sum(1 for item in _JOBS.values() if item.get("status") == "running")
            if running >= _MAX_RUNNING_JOBS:
                raise HTTPException(429, "Two cuts are already rendering. Cancel one, or wait.")
            _JOBS[job_id] = job
            _CANCEL[job_id] = cancel_event
        thread = threading.Thread(
            target=_run_job,
            args=(job_id, Path(audio_path), body, cfg, out, cancel_event),
            daemon=True,
            name=f"xenoform-{job_id}",
        )
        thread.start()
        return {"id": job_id, "only_scenes": only}

    @app.post("/api/animatic")
    def animatic_route(body: dict) -> dict:
        from xenoform.animatic import render_animatic

        audio_id = str(body.get("audio_id") or "demo")
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        anim_id = uuid.uuid4().hex[:10]
        dest = work_dir() / "animatics" / f"{anim_id}.mp4"
        audio = None
        with _LOCK:
            candidate = _AUDIO.get(audio_id)
        if audio_id in {"", "demo"}:
            demo_audio = repo_root() / "examples" / "demo.wav"
            audio = demo_audio if demo_audio.is_file() else None
        elif candidate is not None and Path(candidate).is_file():
            audio = Path(candidate)
        info = render_animatic(list(body.get("scenes") or []), features, dest, audio_path=audio)
        with _LOCK:
            _ANIMATICS[anim_id] = dest
        return {
            "id": anim_id,
            "url": f"/media/animatic/{anim_id}",
            "frames": info["frames"],
            "seconds": info["seconds"],
            "width": info["width"],
            "height": info["height"],
            "cuts": info["cuts"],
        }

    @app.get("/media/animatic/{anim_id}")
    def animatic_file(anim_id: str) -> FileResponse:
        path = _ANIMATICS.get(anim_id)
        if path is None or not Path(path).is_file():
            raise HTTPException(404, "That preview is gone")
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    @app.post("/api/workflow")
    def workflow_route(body: dict) -> dict:
        from xenoform.workflow_export import storyboard_workflow

        return storyboard_workflow(body)

    @app.post("/api/generate")
    def generate(body: dict) -> dict:
        return _start_job(body)

    @app.post("/api/cloud/estimate")
    def cloud_estimate(body: dict) -> dict:
        """Cloud quality (PAID, off by default): the plan, its exact cost, and a confirm token.

        Read only. Nothing is queued or uploaded. The token is what the explicit
        confirm click sends back with /api/generate; without it no paid node runs.
        """
        from xenoform.cloud_morph import mint_token, plan_for

        features = _features_for(str(body.get("audio_id") or "demo"))
        state = {key: body.get(key) for key in ("vibe", "palette", "preset", "brief", "scenes", "customs", "seed")}
        plan = plan_for(float(features.get("duration") or 0.0), list(features.get("beats") or []), state, cfg)
        est = plan["estimate"]
        plan["token"] = "" if est["over_cap"] else mint_token(est)
        plan["can_submit"] = bool(plan["token"]) and plan["node_installed"] and (plan["key_present"] or plan["dry_run"])
        return plan

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                raise HTTPException(404, "No such cut")
            return {key: value for key, value in job.items() if key != "path"}

    @app.post("/api/jobs/{job_id}/cancel")
    def job_cancel(job_id: str) -> dict:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                raise HTTPException(404, "No such cut")
            event = _CANCEL.get(job_id)
            if event is not None:
                event.set()
            if job.get("status") == "running":
                job["status"] = "cancelled"
                job["detail"] = "Cancelled. The card changed."
            return {key: value for key, value in job.items() if key != "path"}

    @app.get("/api/jobs/{job_id}/video")
    def job_video(job_id: str) -> FileResponse:
        with _LOCK:
            job = _JOBS.get(job_id)
        path = Path(job["path"]) if job and job.get("path") else None
        if path is None or not path.exists():
            raise HTTPException(404, "That cut is not ready")
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    def _job_dir(job_id: str) -> Path:
        with _LOCK:
            job = _JOBS.get(job_id)
        path = Path(job["path"]) if job and job.get("path") else None
        if path is None:
            raise HTTPException(404, "No such cut")
        return path.parent

    @app.get("/api/jobs/{job_id}/notes")
    def job_notes(job_id: str) -> FileResponse:
        path = _job_dir(job_id) / "SHOTS.md"
        if not path.is_file():
            raise HTTPException(404, "No shot list for that cut yet")
        return FileResponse(path, media_type="text/markdown", headers={"Cache-Control": "no-store"})

    @app.get("/api/jobs/{job_id}/seed")
    def job_seed(job_id: str) -> FileResponse:
        path = _job_dir(job_id) / "seed.json"
        if not path.is_file():
            raise HTTPException(404, "No seed file for that cut yet")
        return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})

    def _video_for(audio_id: str) -> str:
        if audio_id == "demo" or not audio_id:
            return "/media/demo"
        return ""

    def _notebook(audio_id: str, scenes: list, video: str) -> dict:
        from xenoform.notes import new_notebook

        with _LOCK:
            book = _NOTES.get(audio_id)
            if book is None:
                book = new_notebook(scenes, video)
                _NOTES[audio_id] = book
            return book

    def _save_notebook(audio_id: str, book: dict) -> None:
        import json

        audio_id = storage_id(audio_id)
        path = work_dir() / "notes" / f"{audio_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        stored = {
            "current": book.get("current"),
            "seed": book.get("seed"),
            "versions": [
                {key: value for key, value in version.items() if key != "scenes"}
                | {"scenes": version.get("scenes")}
                for version in book.get("versions") or []
            ],
            "cache": book.get("cache"),
        }
        path.write_text(json.dumps(stored, indent=2), encoding="utf-8")

    @app.post("/api/notes/interpret")
    def notes_interpret(body: dict) -> dict:
        from xenoform.notes import classify, diff_text, identity, interpret_note, plan_sentence

        from xenoform.lessons import load_saved, offer_for

        scenes = list(body.get("scenes") or [])
        if not scenes:
            raise HTTPException(400, "The storyboard is empty.")
        audio_id = str(body.get("audio_id") or "demo")
        features = _features_for(audio_id)
        video = _video_for(audio_id)
        book = _notebook(audio_id, scenes, video)
        saved = load_saved(lessons_file())
        result = interpret_note(
            str(body.get("note") or ""),
            scenes,
            features,
            try_local=bool(body.get("llm", True)),
            lessons=saved,
            allow_cloud=bool(body.get("addons")),
        )
        quality = str(body.get("quality") or "draft")
        model, resolution = identity(quality)
        plan = classify(
            scenes,
            result["scenes"],
            book.get("cache") or {},
            int(book.get("seed") or 2727),
            model,
            resolution,
        )
        result["hits"] = plan["hits"]
        result["misses"] = plan["misses"]
        result["changed"] = plan["changed"]
        result["rerender"] = plan["misses"]
        result["seed"] = int(book.get("seed") or 2727)
        result["cache_line"] = plan_sentence(plan, quality=quality, seed=result["seed"])
        result["text"] = diff_text(result["diff"], result.get("rationale") or "", plan)
        preview = critic_notes_for(scenes, features, saved)
        offer = offer_for(
            str(body.get("note") or ""),
            scenes,
            result.get("scenes") or scenes,
            preview,
            saved,
        )
        if offer:
            offer["patch"] = result.get("patch")
        result["lesson_offer"] = offer
        result.pop("scenes", None)
        return result

    @app.post("/api/notes/apply")
    def notes_apply(body: dict) -> dict:
        from xenoform.notes import apply_to_notebook, render_manifest, version_summary

        scenes = list(body.get("scenes") or [])
        patch = body.get("patch")
        if not scenes or not isinstance(patch, dict):
            raise HTTPException(400, "Confirm needs the storyboard and the patch.")
        audio_id = storage_id(str(body.get("audio_id") or "demo"))
        features = _features_for(audio_id)
        video = str(body.get("video") or _video_for(audio_id))
        book = _notebook(audio_id, scenes, video)
        quality = str(body.get("quality") or "draft")
        out = work_dir() / "notes" / audio_id / "segments"
        try:
            applied = apply_to_notebook(
                book,
                str(body.get("note") or ""),
                scenes,
                patch,
                features,
                render_manifest,
                out,
                quality=quality,
                video=video,
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        _save_notebook(audio_id, book)
        version = applied["version"]
        from xenoform.lessons import load_saved, offer_for

        saved = load_saved(lessons_file())
        offer = offer_for(str(body.get("note") or ""), scenes, applied["scenes"], critic_notes_for(scenes, features, saved), saved)
        if offer:
            offer["patch"] = patch
        return {
            "version": version_summary(version),
            "versions": [version_summary(item) for item in book["versions"]],
            "current": book["current"],
            "scenes": applied["scenes"],
            "blocks": blocks_from_scenes(applied["scenes"]),
            "hits": applied["plan"]["hits"],
            "misses": applied["plan"]["misses"],
            "rerender": applied["plan"]["misses"],
            "cache_line": applied["cache_line"],
            "video": version.get("video") or video,
            "detail": applied["cache_line"],
            "seed": book.get("seed"),
            "lesson_offer": offer,
        }

    @app.post("/api/notes/critic")
    def notes_critic(body: dict) -> dict:
        from xenoform.notes import critic_notes

        audio_id = str(body.get("audio_id") or "demo")
        scenes = list(body.get("scenes") or [])
        features = _features_for(audio_id)
        frames = None
        if body.get("sample", True):
            from xenoform.beatlock import sample_video

            path = repo_root() / "examples" / "demo_base.mp4" if audio_id == "demo" else None
            if path is not None and path.exists():
                try:
                    frames = sample_video(str(path))
                except (OSError, RuntimeError):
                    frames = None
        from xenoform.director import PRESETS
        from xenoform.lessons import load_saved

        looks = [{"id": item["id"], "name": item["name"], "note": item["note"]} for item in PRESETS]
        saved = load_saved(lessons_file())
        return critic_notes(
            frames,
            features,
            scenes,
            fps=float(features.get("fps") or 24),
            lessons=saved,
            looks=looks,
        )

    @app.get("/api/lessons")
    def lessons_index() -> dict:
        from xenoform.lessons import catalog, load_saved

        return {"builtin": catalog(), "saved": load_saved(lessons_file())}

    @app.post("/api/lessons")
    def lessons_save(body: dict) -> dict:
        from xenoform.lessons import save_learned

        note = " ".join(str(body.get("note") or body.get("lesson") or "").split())
        if not note:
            raise HTTPException(400, "A lesson needs the note.")
        stored = save_learned(lessons_file(), body, lessons_log())
        return {"lesson": stored}

    @app.get("/api/notes/versions")
    def notes_versions(audio_id: str = "demo") -> dict:
        from xenoform.notes import version_summary

        with _LOCK:
            book = _NOTES.get(audio_id)
        if book is None:
            return {"versions": [], "current": None}
        return {
            "versions": [version_summary(item) for item in book.get("versions") or []],
            "current": book.get("current"),
        }

    @app.post("/api/notes/revert")
    def notes_revert(body: dict) -> dict:
        from xenoform.notes import revert_notebook, version_summary

        audio_id = str(body.get("audio_id") or "demo")
        version_id = str(body.get("version_id") or "")
        with _LOCK:
            book = _NOTES.get(audio_id)
        if book is None:
            raise HTTPException(404, "No versions yet.")
        try:
            restored = revert_notebook(book, version_id, video=_video_for(audio_id))
        except KeyError as exc:
            raise HTTPException(404, "No such version") from exc
        _save_notebook(audio_id, book)
        return {
            "version": version_summary(restored["version"]),
            "versions": [version_summary(item) for item in book["versions"]],
            "current": book["current"],
            "scenes": restored["scenes"],
            "blocks": blocks_from_scenes(restored["scenes"]),
            "video": restored["version"].get("video") or _video_for(audio_id),
        }

    @app.get("/api/comfy")
    def comfy_status(url: str = "") -> dict:
        from xenoform.comfy_health import DEFAULT_COMFY, ping

        target = url or str(cfg["comfy"].get("base_url") or DEFAULT_COMFY)
        return ping(target)

    @app.post("/api/setup/pick")
    def setup_pick(body: dict) -> dict:
        from xenoform.errors import PlainError, plain_error
        from xenoform.models_setup import choose_file

        try:
            return choose_file(str(body.get("id") or ""), str(body.get("file") or ""))
        except PlainError as exc:
            raise HTTPException(400, plain_error(exc)) from exc

    @app.get("/api/setup")
    def setup_index() -> dict:
        from xenoform.live_mode import interpolator_name, live_ai_status, tensorrt_status
        from xenoform.models_setup import inspect_setup

        payload = inspect_setup()
        payload["extras"] = [live_ai_status(), tensorrt_status()]
        payload["interpolate"] = interpolator_name()
        return payload

    @app.post("/api/setup/download")
    def setup_download(body: dict) -> dict:
        from xenoform.errors import PlainError, plain_error
        from xenoform.models_setup import start_download

        model_id = str(body.get("id") or "")
        try:
            return start_download(model_id)
        except PlainError as exc:
            raise HTTPException(400, plain_error(exc)) from exc

    @app.get("/api/setup/download/{model_id}")
    def setup_download_status(model_id: str) -> dict:
        from xenoform.models_setup import download_status

        return download_status(model_id)

    @app.get("/api/diagnostics")
    def diagnostics_text() -> dict:
        from xenoform.errors import diagnostics
        from xenoform.hardware import detect_tier
        from xenoform.models_setup import inspect_setup

        setup = inspect_setup()
        tier = detect_tier()
        text = diagnostics(
            extra={
                "tier": tier.get("label"),
                "models_dir": setup.get("models_dir"),
                "stems": (setup.get("stems") or {}).get("engine"),
                "missing": ", ".join(setup.get("missing_required") or []) or "none",
            },
            include_trace=False,
        )
        return {"diagnostics": text}

    def _job_snapshot(job_id: str) -> dict | None:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                return None
            return {key: value for key, value in job.items() if key != "path"}

    from xenoform.agent_routes import mount as mount_agent

    mount_agent(
        app,
        lock=_LOCK,
        session={},
        features_for=_features_for,
        start_job=_start_job,
        notebook=_notebook,
        save_notebook=_save_notebook,
        video_for=_video_for,
        lessons_file=lessons_file,
        repo_root=repo_root,
        job_snapshot=_job_snapshot,
        resolve_video=resolve_video,
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        from xenoform.errors import diagnostics, plain_error

        if isinstance(exc, HTTPException):
            detail = exc.detail if isinstance(exc.detail, str) else "That request could not be done."
            return JSONResponse(status_code=exc.status_code, content={"detail": detail, "diagnostics": diagnostics(exc, include_trace=False)})
        log.exception("desk error")
        return JSONResponse(
            status_code=500,
            content={"detail": plain_error(exc), "diagnostics": diagnostics(exc)},
        )

    return app


def _run_job(job_id: str, audio_path: Path, body: dict, cfg: dict, out: Path, cancel_event: threading.Event | None = None) -> None:
    from xenoform.director import run_directed
    from xenoform.turbo import JobCancelled

    work = out.parent
    if cancel_event is None:
        cancel_event = _CANCEL.get(job_id) or threading.Event()

    def on_progress(stage: str, frac: float, detail: str) -> None:
        if cancel_event.is_set():
            raise JobCancelled("Cancelled. The card changed.")
        with _LOCK:
            job = _JOBS[job_id]
            job["stage"] = stage
            job["progress"] = round(float(frac), 4)
            job["detail"] = detail
            watchable = stage in {"animatic", "assemble", "done"} and out.exists()
            if watchable:
                version = int(job.get("video_version") or 0) + 1
                job["video_version"] = version
                job["video"] = f"/api/jobs/{job_id}/video?v={version}"
            if stage == "done":
                job["status"] = "done"

    from xenoform.errors import diagnostics, plain_error
    from xenoform.hardware import detect_tier, run_resilient

    def once(tier_id: str):
        return run_directed(
            cfg,
            audio_path,
            body,
            out,
            work,
            on_progress=on_progress,
            tier_id=tier_id,
            cancel=cancel_event.is_set,
        )

    try:
        result, tier_id, note = run_resilient(once, detect_tier())
        with _LOCK:
            job = _JOBS[job_id]
            if cancel_event.is_set():
                job["status"] = "cancelled"
                job["detail"] = "Cancelled. The card changed."
                return
            job["status"] = "done"
            job["stage"] = "done"
            job["progress"] = 1.0
            version = int(job.get("video_version") or 0) + 1
            job["video_version"] = version
            job["video"] = f"/api/jobs/{job_id}/video?v={version}"
            job["path"] = str(out)
            job["tier"] = tier_id
            if isinstance(result, dict) and result.get("seconds"):
                kind = "Animatic" if result.get("mode") == "animatic" else "Cut"
                job["detail"] = f"{kind} ready in {result['seconds']:.1f}s"
                if result.get("cached_keyframes"):
                    job["detail"] += f" · {result['cached_keyframes']} cached"
                job["seconds"] = result["seconds"]
            if isinstance(result, dict) and result.get("warning"):
                job["detail"] = result["warning"]
            if note:
                job["detail"] = f"{note} {job.get('detail') or ''}".strip()
                job["tier_note"] = note
    except JobCancelled:
        with _LOCK:
            job = _JOBS[job_id]
            job["status"] = "cancelled"
            job["detail"] = "Cancelled. The card changed."
            job["error"] = None
        return
    except Exception as exc:
        log.exception("job %s failed", job_id)
        sentence = plain_error(exc)
        with _LOCK:
            job = _JOBS[job_id]
            job["status"] = "error"
            job["error"] = sentence
            job["detail"] = sentence
            job["diagnostics"] = diagnostics(exc, extra={"job": job_id})


def serve(host: str = "127.0.0.1", port: int = 47317, cfg: dict | None = None) -> None:
    import uvicorn

    app = create_app(cfg)
    log.info("Xenoform desk at http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
