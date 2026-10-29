"""Local director desk. `xenoform ui` serves this app."""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import File, HTTPException, Request, UploadFile

from xenoform import job_timing, songs_api
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
_AUDIO: dict[str, Path] = songs_api.audio_registry()  # a bundled song ("song-<id>") is found on first sight, after a restart too
_FEATURES: dict[str, dict] = songs_api.features_registry()
_FORMS: dict[str, Path] = {}
_NOTES: dict[str, dict[str, Any]] = {}
_GUIDES: dict[str, Path] = {}
_HEROES: dict[str, Path] = {}
_OWN: dict[str, Path] = {}  # own_id -> folder of the user's own clips and images (POST /api/own)
_STILLS_JOB: dict[str, Any] = {}  # the one stills-library grow at a time (POST /api/stills/grow): status, vibe, done, kept
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
    app = FastAPI(title="Xenoform", docs_url=None, redoc_url=None, openapi_url=None)  # the schema route was a 500 (FileResponse is imported inside create_app)

    class _FreshCode(StaticFiles):
        """The desk's own scripts and styles revalidate on every load (an ETag check, a 304 when unchanged), so a desk
        restarted on new code is new in the browser without Ctrl+Shift+R; so do the vibe tiles (their pictures change
        with the library: 29 Oct, one frame of each vibe's Cloud Final cut); other pictures keep the browser's usual
        cache."""

        def file_response(self, full_path, *args, **kwargs):
            response = super().file_response(full_path, *args, **kwargs)
            path = str(full_path).replace("\\", "/")
            if path.endswith((".js", ".css", ".html")) or "/vibes/" in path:
                response.headers["Cache-Control"] = "no-cache"
            return response

    app.mount("/static", _FreshCode(directory=static), name="static")
    from xenoform.stems_api import router as stems_router  # /api/stems, /api/midi/*, /ws/midi

    app.include_router(stems_router)
    from xenoform.film_pack import router as film_pack_router  # /api/film_pack (the free film pack's status)

    app.include_router(film_pack_router)
    app.include_router(songs_api.router)  # /api/songs, /api/songs/load: the bundled songs
    app.state.cfg = cfg  # the desk's config for the routers (songs_api answers its comfy.base_url, as /api/analyze does)

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
        try:  # stems by default, the demo song too
            from xenoform.stems_api import start_background_split

            start_background_split(repo_root() / "examples" / "demo.wav")
        except Exception:
            log.exception("background stem split (demo)")
        payload = session_payload(
            features,
            audio_id="demo",
            title="Demo assembly",
            video="/media/demo",
            endpoint=str(cfg["comfy"].get("base_url") or "http://127.0.0.1:8188"),
        )
        payload["reference"] = "examples/demo_base.mp4"
        from xenoform.cloud_morph import OPT_IN_LABEL, paid_env_state

        # Paid cloud renders are opt-in. The desk shows the env override so it can lock the setting.
        payload["paid_cloud"] = {"env": paid_env_state(), "config": bool(cfg["comfy"].get("paid_cloud", False)), "label": OPT_IN_LABEL}
        return payload

    @app.get("/api/catalog")
    def catalog() -> dict:
        return {
            "forms": public_forms(),
            "presets": public_presets(),
            "transitions": public_transitions(),
        }

    @app.get("/api/vibes")
    def vibes_route() -> dict:
        """The vibe picker, one source of truth: the featured registry vibes in order, then the originals,
        then the rest. Each row carries its still URL, object ``pool``, ``has_library`` (its own 4-shot strip)
        and ``library`` (the folder its strip resolves to, through ``pool`` when it has none of its own)."""
        from xenoform import dance_fx as _dance
        from xenoform import vibes as _vibes

        return {
            "vibes": _vibes.catalog(),
            "featured": [v["id"] for v in _vibes.featured()],
            "original": list(_vibes.ORIGINAL),
            "looks": [{"id": k, "note": v} for k, v in {**_dance.PRESET_NOTES, **_effects_looks()}.items()],
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
        try:  # stems by default: split in the background now, so the first Make is already stem-reactive
            from xenoform import stems_api as _stems

            starter = getattr(_stems, "start_background_split", None)
            if starter:
                starter(dest)
        except Exception:
            log.exception("background stem split")
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

    @app.post("/api/jobs/{job_id}/recut")
    def recut_job(job_id: str, body: dict | None = None) -> dict:
        """Re-compose a finished Simple video from its cached morphs with new knobs / look / orbit (no GPU)."""
        from xenoform.dense import recut_from_cache

        body = body or {}
        # a cut reopened after a desk restart is registered from its folder, as the timeline's edits are (it used to
        # answer "No such video." to Re-cut with these knobs on any cut made before the restart, 28 Oct)
        job, folder = _cut_job_for_edit(job_id, "re-cut")
        overrides = {k: body.get(k) for k in ("macros", "dance_fx", "stem_orbit", "beat_fx", "end_card", "beat_overlay", "foreshadow",
                                              "morph_timing", "effects", "boundary_smear") if k in body}
        # the timeline's per-shot and per-boundary overrides (docs/TIMELINE.md): whole maps, each replacing the record's
        for key in ("shot_overrides", "boundary_overrides"):
            if key in body and isinstance(body.get(key), (dict, list)):
                overrides[key] = body[key]
        with _LOCK:
            job.update({"status": "running", "stage": "assemble", "progress": 0.05, "detail": "Re-cutting from the cached morphs",
                        "error": None})

        def on_progress(stage: str, frac: float, detail: str) -> None:
            with _LOCK:
                job.update({"stage": stage, "progress": float(frac), "detail": detail})

        def run() -> None:
            try:
                rec = recut_from_cache(folder, overrides, report=on_progress, cfg=cfg)
                with _LOCK:
                    version = int(job.get("video_version") or 0) + 1
                    job.update({"status": "done", "stage": "done", "progress": 1.0, "video_version": version,
                                "video": f"/api/jobs/{job_id}/video?v={version}", "detail": "Re-cut ready",
                                "look": rec.get("look"), "recuts": rec.get("recuts")})
            except Exception as exc:
                log.exception("recut %s", job_id)
                from xenoform.errors import plain_error

                with _LOCK:
                    job.update({"status": "done", "stage": "done", "progress": 1.0, "detail": f"Re-cut did not run. {plain_error(exc)}",
                                "error": None})

        threading.Thread(target=run, name=f"recut-{job_id}", daemon=True).start()
        return {"id": job_id, "status": "running"}

    @app.post("/api/jobs/{job_id}/swap")
    def swap_job(job_id: str, body: dict | None = None) -> dict:
        """Swap one still of a finished Simple cut (``dense.swap_still``): the two morphs that touch it are re-rendered
        on the GPU (Draft, about a minute a pair), the rest kept, and the cut re-composed. Body: ``slot`` (the chain
        index the lane names as ``still``) and ``file`` (a library row's file). A cut reopened after a desk restart
        is registered from its folder."""
        from xenoform.dense import swap_still

        body = body or {}
        folder = work_dir() / "jobs" / storage_id(job_id, fallback="")
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None and (folder / "simple" / "simple.json").is_file() and (folder / "xenoform.mp4").is_file():
                job = {"id": job_id, "status": "done", "stage": "done", "progress": 1.0, "detail": "Reopened",
                       "video_version": 0, "video": f"/api/jobs/{job_id}/video?v=0", "path": str(folder / "xenoform.mp4"), "error": None}
                _JOBS[job_id] = job
        if job is None:
            raise HTTPException(404, "No such video.")
        if job.get("status") == "running":
            raise HTTPException(409, "That video is still rendering.")
        if not (folder / "simple" / "simple.json").is_file():
            raise HTTPException(400, "This video has no cached morphs to swap into.")
        try:
            slot = int(body.get("slot"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Which slot? The lane names the still a shot lands on.")
        file = str(body.get("file") or "").strip()
        if not file:
            raise HTTPException(400, "Which still? Pick one from the library.")
        try:  # the cheap refusals (a Final cut, a still already in the chain, no such file) answer at once
            rec = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
        except ValueError:
            raise HTTPException(400, "This cut's record did not read.")
        from xenoform.dense import library_row

        files = [str(f) for f in rec.get("stills") or []]
        if not 0 <= slot < len(files):
            raise HTTPException(400, f"This cut has {len(files)} stills; slot {slot} is not one of them.")
        if str(rec.get("tier") or "draft") == "final":
            raise HTTPException(400, "A swap re-renders a Draft morph pair; this cut is Final. Make it again with the Chain row instead.")
        if library_row(file) is None:
            raise HTTPException(400, f"{file} is not in the stills library.")
        if file in files:
            raise HTTPException(400, f"{file.split('/')[-1]} is already in this cut; a still appears once.")
        with _LOCK:
            job.update({"status": "running", "stage": "restyle", "progress": 0.05, "detail": f"Swapping still {slot + 1}: re-rendering the morphs that touch it",
                        "error": None})

        def on_progress(stage: str, frac: float, detail: str) -> None:
            with _LOCK:
                job.update({"stage": stage, "progress": float(frac), "detail": detail})

        def run() -> None:
            try:
                rec = swap_still(folder, slot, file, cfg=cfg, report=on_progress)
                with _LOCK:
                    version = int(job.get("video_version") or 0) + 1
                    job.update({"status": "done", "stage": "done", "progress": 1.0, "video_version": version,
                                "video": f"/api/jobs/{job_id}/video?v={version}", "detail": "Swap ready",
                                "look": rec.get("look"), "recuts": rec.get("recuts"), "swaps": len(rec.get("swaps") or [])})
            except Exception as exc:
                log.exception("swap %s", job_id)
                from xenoform.errors import plain_error

                with _LOCK:
                    job.update({"status": "done", "stage": "done", "progress": 1.0, "detail": f"The swap did not run. {plain_error(exc)}",
                                "error": None})

        threading.Thread(target=run, name=f"swap-{job_id}", daemon=True).start()
        return {"id": job_id, "status": "running", "slot": slot, "file": file}

    def _cut_job_for_edit(job_id: str, verb: str) -> tuple[dict, Path]:
        """The job and folder of a finished Simple cut a timeline edit may act on; a cut reopened after a desk restart
        is registered from its folder. Raises the plain-words refusals (404, 409, 400)."""
        folder = work_dir() / "jobs" / storage_id(job_id, fallback="")
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None and (folder / "simple" / "simple.json").is_file() and (folder / "xenoform.mp4").is_file():
                job = {"id": job_id, "status": "done", "stage": "done", "progress": 1.0, "detail": "Reopened",
                       "video_version": 0, "video": f"/api/jobs/{job_id}/video?v=0", "path": str(folder / "xenoform.mp4"), "error": None}
                _JOBS[job_id] = job
        if job is None:
            raise HTTPException(404, "No such video.")
        if job.get("status") == "running":
            raise HTTPException(409, "That video is still rendering.")
        if not (folder / "simple" / "simple.json").is_file():
            raise HTTPException(400, f"This video has no cached morphs to {verb}.")
        return job, folder

    def _run_edit(job: dict, job_id: str, name: str, ready: str, failed: str, fn) -> None:
        """Run a timeline edit (a GPU pair render and the re-compose) on a thread, the job showing its progress and
        bumping its video version when the re-cut lands, as the swap does."""
        def on_progress(stage: str, frac: float, detail: str) -> None:
            with _LOCK:
                job.update({"stage": stage, "progress": float(frac), "detail": detail})

        def run() -> None:
            try:
                rec = fn(on_progress)
                with _LOCK:
                    version = int(job.get("video_version") or 0) + 1
                    job.update({"status": "done", "stage": "done", "progress": 1.0, "video_version": version,
                                "video": f"/api/jobs/{job_id}/video?v={version}", "detail": ready,
                                "look": rec.get("look"), "recuts": rec.get("recuts"), "swaps": len(rec.get("swaps") or []),
                                "rerenders": len(rec.get("rerenders") or []), "inserts": len(rec.get("inserts") or [])})
            except Exception as exc:
                log.exception("%s %s", name, job_id)
                from xenoform.errors import plain_error

                with _LOCK:
                    job.update({"status": "done", "stage": "done", "progress": 1.0, "detail": f"{failed} {plain_error(exc)}", "error": None})

        threading.Thread(target=run, name=f"{name}-{job_id}", daemon=True).start()

    @app.post("/api/jobs/{job_id}/rerender")
    def rerender_job(job_id: str, body: dict | None = None) -> dict:
        """Re-render the morph one shot plays (``dense.rerender_morph``, docs/TIMELINE.md 1.5): another seed, length (2 to
        5 s of source) or prompt variant, one Draft morph on the GPU, then the re-compose with the timeline as it stands.
        Body: ``shot``; optional ``seed``, ``render_s``, ``variant``, ``style`` (``morph_style``: melt, shatter, bloom, spin,
        fold; the shot's own when not given)."""
        from xenoform.dense import RERENDER_VARIANTS, RENDER_S_RANGE, rerender_morph

        body = body or {}
        job, folder = _cut_job_for_edit(job_id, "re-render")
        try:
            shot = int(body.get("shot"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Which shot? The timeline names each shot by its index.")
        seed = body.get("seed")
        if seed not in (None, ""):
            try:
                seed = int(seed)
            except (TypeError, ValueError):
                raise HTTPException(400, "The seed is a whole number.")
        else:
            seed = None
        render_s = body.get("render_s")
        if render_s not in (None, ""):
            try:
                render_s = int(round(float(render_s)))
            except (TypeError, ValueError):
                raise HTTPException(400, "The morph's length is a number of seconds, 2 to 5.")
            if not RENDER_S_RANGE[0] <= render_s <= RENDER_S_RANGE[1]:
                raise HTTPException(400, f"The morph's length is {RENDER_S_RANGE[0]} to {RENDER_S_RANGE[1]} s of source.")
        else:
            render_s = None
        variant = str(body.get("variant") or "auto").strip().lower()
        if variant not in RERENDER_VARIANTS:
            raise HTTPException(400, f"No prompt variant called {variant}; one of {', '.join(RERENDER_VARIANTS)}.")
        from xenoform.morph_style import STYLES

        style = str(body.get("style") or "").strip().lower() or None  # how the object changes; the shot's own when not given
        if style is not None and style not in STYLES:
            raise HTTPException(400, f"No morph style called {style}; one of {', '.join(STYLES)}.")
        try:  # the cheap refusals answer at once
            rec = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
        except ValueError:
            raise HTTPException(400, "This cut's record did not read.")
        shots = list(rec.get("plan_shots") or rec.get("shots") or [])
        if not 0 <= shot < len(shots):
            raise HTTPException(400, f"This cut has {len(shots)} shots; shot {shot} is not one of them.")
        if str(rec.get("tier") or "draft") == "final":
            raise HTTPException(400, "A re-render makes a Draft morph; this cut is Final. Make it again instead.")
        from xenoform.dense import _under_insert

        under = _under_insert(shots[shot])
        if under:
            raise HTTPException(400, f"Shot {shot + 1} is {under}: it plays no morph of the chain to re-render.")
        with _LOCK:
            job.update({"status": "running", "stage": "restyle", "progress": 0.05, "detail": f"Re-rendering shot {shot + 1}'s morph", "error": None})
        _run_edit(job, job_id, "rerender", "Re-render ready", "The re-render did not run.",
                  lambda report: rerender_morph(folder, shot, seed=seed, render_s=render_s, variant=variant, style=style, cfg=cfg,
                                                report=report))
        return {"id": job_id, "status": "running", "shot": shot, "seed": seed, "render_s": render_s, "variant": variant, "style": style}

    @app.post("/api/jobs/{job_id}/insert")
    def insert_job(job_id: str, body: dict | None = None) -> dict:
        """"Generate 10 s here" (``dense.insert_generated``, docs/TIMELINE.md 1.6): a fresh Draft chain over the span from
        shot ``first`` (about ``seconds`` long, 5, 10 or 15), the Chain row's ``pins`` honoured, inserted as a run of shots
        and the cut re-composed. One Draft morph a shot on the GPU."""
        from xenoform.dense import INSERT_RANGE, INSERT_SECONDS, insert_generated, insert_span

        body = body or {}
        job, folder = _cut_job_for_edit(job_id, "generate into")
        try:
            first = int(body.get("first"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Where? The run starts on a shot of the cut, named by its index.")
        try:
            seconds = float(body.get("seconds") or INSERT_SECONDS[1])
        except (TypeError, ValueError):
            raise HTTPException(400, "The run's length is a number of seconds.")
        if not INSERT_RANGE[0] <= seconds <= INSERT_RANGE[1]:
            raise HTTPException(400, f"A run is {int(INSERT_RANGE[0])} to {int(INSERT_RANGE[1])} s long.")
        pins = body.get("pins") if isinstance(body.get("pins"), (dict, list)) else None
        seed = body.get("seed")
        if seed not in (None, ""):
            try:
                seed = int(seed)
            except (TypeError, ValueError):
                raise HTTPException(400, "The seed is a whole number.")
        else:
            seed = None
        try:  # the cheap refusals answer at once
            rec = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
        except ValueError:
            raise HTTPException(400, "This cut's record did not read.")
        if str(rec.get("tier") or "draft") == "final":
            raise HTTPException(400, "A generated run is made of Draft morphs; this cut is Final. Make it again instead.")
        shots = list(rec.get("plan_shots") or rec.get("shots") or [])
        try:
            first, last = insert_span(shots, first, seconds)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        with _LOCK:
            job.update({"status": "running", "stage": "restyle", "progress": 0.05,
                        "detail": f"Generating {last - first + 1} morph{'s' if last != first else ''} over shots {first + 1} to {last + 1}", "error": None})
        _run_edit(job, job_id, "insert", "Generated run ready", "The generated run did not run.",
                  lambda report: insert_generated(folder, first, seconds=seconds, pins=pins, seed=seed, cfg=cfg, report=report))
        return {"id": job_id, "status": "running", "first": first, "last": last, "seconds": seconds}

    @app.post("/api/jobs/{job_id}/dream")
    def dream_job(job_id: str, body: dict | None = None) -> dict:
        """"Dream this span" (``xenoform.dream``): Z-Image Turbo img2img over 1 to 3 s of the cut from shot ``first``,
        12 dreamed frames a second, cut in like a generated run, the cut re-composed. Body: ``first``, ``seconds`` (1, 2
        or 3), ``depth`` ("light" or "deep"), optional ``seed``. About 2.6 s of GPU a dreamed frame once warm."""
        from xenoform import dream as _dream

        body = body or {}
        job, folder = _cut_job_for_edit(job_id, "dream over")
        try:
            first = int(body.get("first"))
        except (TypeError, ValueError):
            raise HTTPException(400, "Where? The dream starts on a shot of the cut, named by its index.")
        try:
            seconds = float(body.get("seconds") or _dream.SECONDS[1])
        except (TypeError, ValueError):
            raise HTTPException(400, "The dream's length is a number of seconds.")
        if not _dream.RANGE[0] <= seconds <= _dream.RANGE[1]:
            raise HTTPException(400, f"A dream is {int(_dream.RANGE[0])} to {int(_dream.RANGE[1])} s long.")
        depth = str(body.get("depth") or "light").strip().lower()
        if depth not in _dream.DEPTHS:
            raise HTTPException(400, f"A dream is {' or '.join(_dream.DEPTHS)}.")
        seed = body.get("seed")
        if seed not in (None, ""):
            try:
                seed = int(seed)
            except (TypeError, ValueError):
                raise HTTPException(400, "The seed is a whole number.")
        else:
            seed = None
        try:
            rec = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
        except ValueError:
            raise HTTPException(400, "This cut's record did not read.")
        shots = list(rec.get("plan_shots") or rec.get("shots") or [])
        try:
            first, last = _dream.span(shots, first, seconds)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        with _LOCK:
            job.update({"status": "running", "stage": "restyle", "progress": 0.05,
                        "detail": f"Dreaming over shots {first + 1} to {last + 1}", "error": None})
        _run_edit(job, job_id, "dream", "Dream ready", "The dream did not run.",
                  lambda report: _dream.dream_span(folder, first, seconds=seconds, depth=depth, seed=seed, cfg=cfg, report=report))
        return {"id": job_id, "status": "running", "first": first, "last": last, "seconds": seconds, "depth": depth}

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

    # ---------------------------------------------------------------- Moves library (Wan Animate 2)
    _MOVE_JOBS: dict = {}

    @app.get("/vj")
    def vj_page() -> FileResponse:
        """Live VJ mode: mic/line-in reactive playback of morph loops (WebAudio + WebGL)."""
        return FileResponse(Path(__file__).parent / "ui_static" / "vj.html")

    @app.get("/api/footage")
    def footage_list(vibe: str = "", kind: str = "") -> dict:
        from xenoform import footage

        data = footage.load_manifest()
        items = []
        for it in data["items"]:
            if (vibe and vibe not in it["vibes"]) or (kind and it["kind"] != kind):
                continue
            have = footage.local_path(it).is_file()
            items.append({**it, "available": have, "url": f"/library-media/{it['id']}" if have else None})
        return {"items": items}

    @app.get("/library-media/{item_id}")
    def footage_media(item_id: str) -> FileResponse:
        from fastapi import HTTPException
        from xenoform import footage

        for it in footage.load_manifest()["items"]:
            if it["id"] == item_id and footage.local_path(it).is_file():
                return FileResponse(footage.local_path(it))
        raise HTTPException(status_code=404, detail="not in the library (run scripts/fetch_library.py)")

    @app.get("/moves")
    def moves_page() -> FileResponse:
        return FileResponse(Path(__file__).parent / "ui_static" / "moves.html")

    @app.get("/api/moves")
    def moves_list(all: bool = False) -> dict:
        from xenoform import moves as mv

        return {"moves": mv.moves(include_avoid=all), "style": mv.DEFAULT_STYLE,
                "size": f"{mv.W}x{mv.H}", "frames": mv.FRAMES}

    @app.post("/api/moves/render")
    async def moves_render(request: Request) -> dict:
        from xenoform import moves as mv

        form = await request.form()
        upload, move_id = form.get("file"), str(form.get("move") or "")
        appearance = str(form.get("appearance") or "")
        if upload is None or not move_id:
            raise HTTPException(400, "Send a character picture and a move.")
        try:
            mv.clip(move_id)
        except mv.MovesError as exc:
            raise HTTPException(404, str(exc)) from exc
        if not (mv.LIBRARY / f"{move_id}.mp4").is_file():
            raise HTTPException(409, f"{move_id} is not downloaded yet. Run: python scripts/fetch_moves.py {move_id}")
        job_id = uuid.uuid4().hex[:10]
        folder = work_dir() / "moves" / job_id
        folder.mkdir(parents=True, exist_ok=True)
        suffix = Path(getattr(upload, "filename", "") or "character.png").suffix.lower() or ".png"
        image = folder / f"upload{suffix}"
        image.write_bytes(await upload.read())
        _MOVE_JOBS[job_id] = {"status": "rendering"}

        def run() -> None:
            try:
                out = mv.render(image, move_id, appearance, folder, cfg)
                _MOVE_JOBS[job_id] = {"status": "done", "path": str(out), "url": f"/media/moves/{job_id}"}
            except Exception as exc:  # noqa: BLE001 - shown to the user
                _MOVE_JOBS[job_id] = {"status": "error", "error": str(exc)[:300]}

        threading.Thread(target=run, daemon=True, name=f"moves-{job_id}").start()
        return {"id": job_id, "status": "rendering"}

    @app.get("/api/moves/jobs/{job_id}")
    def moves_job(job_id: str) -> dict:
        job = _MOVE_JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "No such move render.")
        return {k: v for k, v in job.items() if k != "path"}

    @app.get("/media/moves/{job_id}")
    def moves_media(job_id: str) -> FileResponse:
        job = _MOVE_JOBS.get(job_id) or {}
        if not job.get("path") or not Path(job["path"]).is_file():
            raise HTTPException(404, "That move render is gone.")
        return FileResponse(job["path"], media_type="video/mp4")

    @app.post("/api/own")
    async def add_own(files: list[UploadFile] = File(...)) -> dict:
        """Your own clips and images for the Simple cut, dropped on the desk: saved under work/ui/own/<id>/ and
        scanned (``own_media.scan``). The Make body then carries ``own_id``."""
        from xenoform import own_media

        own_id = uuid.uuid4().hex[:10]
        dest = work_dir() / "own" / own_id
        dest.mkdir(parents=True, exist_ok=True)
        kept = 0
        for f in files:
            name = re.sub(r"[^\w.\- ]", "_", Path(f.filename or "").name)
            ext = Path(name).suffix.lower()
            if ext not in own_media.footage.VIDEO_EXT | own_media.footage.IMAGE_EXT:
                continue
            (dest / (name or f"file{kept}{ext}")).write_bytes(await read_upload(f))
            kept += 1
        found = own_media.scan(dest)
        with _LOCK:
            _OWN[own_id] = dest
        n_img, n_clip = len(found["images"]), len(found["clips"])
        on_disk = [p.suffix.lower() for p in dest.iterdir() if p.is_file()]
        img_left = max(0, sum(s in own_media.footage.IMAGE_EXT for s in on_disk) - n_img)
        clip_left = max(0, sum(s in own_media.footage.VIDEO_EXT for s in on_disk) - n_clip)
        # an object cut takes the images, a clips cut the clips, never both (Tys, 28 Oct): the desk words the note for
        # the Morph row in use from these counts; the detail is for scripts and says the same without a mode
        detail = (f"{n_img} image{'s' if n_img != 1 else ''} for an object cut, {n_clip} clip{'s' if n_clip != 1 else ''} for a clips cut."
                  + (f" Left out: {img_left} image{'s' if img_left != 1 else ''} past {own_media.MAX_ITEMS}." if img_left else "")
                  + (f" Left out: {clip_left} clip{'s' if clip_left != 1 else ''} past {own_media.MAX_CLIPS}." if clip_left else ""))
        return {"id": own_id, "folder": str(dest), "images": n_img, "clips": n_clip, "images_left": img_left, "clips_left": clip_left,
                "max_images": own_media.MAX_ITEMS, "max_clips": own_media.MAX_CLIPS, "detail": detail}

    @app.get("/api/stills")
    def stills_route(vibe: str = "") -> dict:
        """The stills library (xenoform.stills): per-vibe counts (shipped, grown here, your own), the running grow if any, and for
        ``vibe`` how many catalogue subjects it has not rendered yet."""
        from xenoform import stills

        with _LOCK:
            job = {k: v for k, v in _STILLS_JOB.items() if k != "result"}
        out = {"counts": stills.counts(), "job": job, "seconds_per_still": stills.SECONDS_PER_STILL,
               "default_grow": stills.DEFAULT_GROW, "default_grow_scenes": stills.DEFAULT_GROW_SCENES, "max_own": stills.MAX_OWN,
               "folder": str(stills.root())}
        if vibe:
            out["vibe"] = vibe
            out["have"] = stills.counts(vibe)
            out["subjects_left"] = len(stills.nouns_for(vibe, 10_000, have=stills.nouns_in(vibe)))
            out["scene_subjects"] = len(stills.scene_list(vibe))
            out["rows"] = _library_rows(vibe)  # what the Chain row and the lane's swap pick from
        return out

    def _library_rows(vibe: str) -> list[dict]:
        """The vibe's library as the pickers show it: its own rows, then the pool it borrows when it has too few of its
        own (``morph_pass.vibe_for``), each with its thumbnail url, objects before scenes."""
        from xenoform import morph_pass as _mp
        from xenoform import stills

        cat = _mp.catalogue()
        pool = _mp.vibe_for({"vibe": vibe}) if vibe else ""
        rows = []
        for under in [vibe] + ([pool] if pool and pool != vibe else []):
            for r in cat.get(under) or []:
                rows.append({"file": str(r.get("file") or ""), "noun": str(r.get("noun") or ""), "kind": stills.kind_of(r),
                             "own": bool(r.get("own")), "shipped": bool(r.get("shipped")), "vibe": under,
                             "thumb": "/api/stills/thumb?file=" + quote(str(r.get("file") or ""), safe="/")})
        rows.sort(key=lambda r: (r["kind"] != "object", 0))  # stable: objects first, each pool's order kept
        return rows

    @app.get("/api/stills/thumb")
    def stills_thumb(file: str = ""):
        """A still of the library by its file (``cosmic/042_wolf_skull.jpg``): the shipped pool, else the work folder."""
        from xenoform import morph_pass as _mp
        from xenoform import stills

        rel = str(file or "").strip().replace("\\", "/")
        if not rel or rel.startswith("/") or ".." in rel.split("/") or ":" in rel:
            raise HTTPException(404, "No such still")
        for base in (_mp.OBJECTS, stills.root()):
            path = (base / rel)
            try:
                path.resolve().relative_to(Path(base).resolve())
            except ValueError:
                continue
            if path.is_file():
                kind = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower(), "application/octet-stream")
                return FileResponse(path, media_type=kind, headers={"Cache-Control": "max-age=600"})
        raise HTTPException(404, "No such still")

    @app.post("/api/stills/grow")
    def library_grow(body: dict) -> dict:
        """Grow a vibe's stills on this GPU in the background: ``count`` catalogue subjects, or the user's own
        ``nouns`` (comma-separated, ``own`` true) rendered in the vibe's material, or scenes (``kind: "scene"``:
        wide frames from configs/scenes.json, ``count`` of them, 8 by default). One grow at a time; each still
        is checked against the vibe's pool and kept or set aside. Poll GET /api/stills for progress."""
        from xenoform import stills

        vibe = str(body.get("vibe") or "").strip()
        if not vibe:
            raise HTTPException(400, "Pick a vibe first.")
        kind = "scene" if str(body.get("kind") or "object").strip().lower() == "scene" else "object"
        own = bool(body.get("own")) and kind != "scene"
        nouns = stills.own_nouns(body.get("nouns") or "") if own else None
        if own and not nouns:
            raise HTTPException(400, "Type a shape or two first (a brass astrolabe, a wolf skull).")
        try:
            count = int(body.get("count") or (stills.DEFAULT_GROW_SCENES if kind == "scene" else stills.DEFAULT_GROW))
        except (TypeError, ValueError):
            count = stills.DEFAULT_GROW_SCENES if kind == "scene" else stills.DEFAULT_GROW
        with _LOCK:  # the slot is taken here, before the ComfyUI probe, so a second click cannot start a second grow
            if _STILLS_JOB.get("status") in ("running", "starting"):
                raise HTTPException(409, "The library is already growing; wait for it to finish or stop it.")
            _STILLS_JOB.clear()
            _STILLS_JOB.update({"status": "starting", "vibe": vibe, "own": own, "kind": kind, "asked": 0, "done": 0, "kept": 0,
                                "started": time.time(), "eta_s": 0.0, "note": "", "cancel": False})
        try:
            avail = stills.available(cfg)
            if not avail.get("ok"):
                raise HTTPException(503, avail.get("note") or "ComfyUI is not ready to render stills.")
            plan = stills.plan(vibe, count, nouns=nouns, own=own, kind=kind)
            if not plan["nouns"]:
                raise HTTPException(400, "Nothing left to render for this vibe: every catalogue subject is in its library.")
        except HTTPException as exc:
            with _LOCK:
                _STILLS_JOB.update({"status": "error", "note": str(exc.detail)})
            raise
        except Exception as exc:
            with _LOCK:
                _STILLS_JOB.update({"status": "error", "note": str(exc)[:300]})
            raise HTTPException(500, str(exc)[:300]) from exc
        planned = list(plan["nouns"])  # the thread renders exactly these, so the reply lists what will be made
        with _LOCK:
            _STILLS_JOB.update({"status": "running", "asked": len(planned), "eta_s": plan["seconds"]})

        def progress(done: int, total: int, kept: int) -> None:
            with _LOCK:
                _STILLS_JOB.update({"done": int(done), "asked": int(total), "kept": int(kept)})

        def cancelled() -> bool:
            with _LOCK:
                return bool(_STILLS_JOB.get("cancel"))

        def run() -> None:
            try:
                extra = {"kind": kind} if kind == "scene" else {}  # an object grow calls grow() as before
                result = stills.grow(vibe, count, nouns=planned, own=own, cfg=cfg, progress=progress, cancel=cancelled, **extra)
                with _LOCK:
                    _STILLS_JOB.update({"status": "done", "result": result, "note": stills.summary_line(result),
                                         "done": result.get("made", 0), "kept": result.get("kept", 0), "took_s": result.get("seconds")})
            except Exception as exc:  # the desk shows the reason; the library keeps whatever was kept before it
                log.exception("stills grow %s failed", vibe)
                with _LOCK:
                    _STILLS_JOB.update({"status": "error", "note": str(exc)[:300]})

        threading.Thread(target=run, name=f"stills-{vibe}", daemon=True).start()
        return {"ok": True, "vibe": vibe, "kind": kind, "asked": len(plan["nouns"]), "nouns": plan["nouns"], "eta_s": plan["seconds"]}

    @app.post("/api/stills/stop")
    def library_stop() -> dict:
        """Stop collecting the running grow (renders already queued finish on the GPU unused)."""
        with _LOCK:
            running = _STILLS_JOB.get("status") in ("running", "starting")
            if running:
                _STILLS_JOB["cancel"] = True
        return {"ok": True, "stopping": running}

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
            # A reopened cut from My videos: the job may predate this desk process.
            saved = work_dir() / "jobs" / storage_id(job, fallback="") / "xenoform.mp4"
            if storage_id(job, fallback="") and saved.is_file():
                return saved
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

    # ---------------------------------------------------------- Simple: recipe codes, options, hook, My videos

    @app.post("/api/simple/recipe/encode")
    def simple_recipe_encode(body: dict) -> dict:
        from xenoform.simple_recipe import encode

        return {"recipe": encode(body or {})}

    @app.post("/api/simple/recipe/decode")
    def simple_recipe_decode(body: dict) -> dict:
        from xenoform.simple_recipe import RecipeError, decode, encode

        try:
            state = decode(str((body or {}).get("recipe") or ""))
        except RecipeError as exc:
            raise HTTPException(400, str(exc)) from exc
        state["recipe"] = encode(state)
        return state

    @app.get("/api/simple/options")
    def simple_options(duration: float = 20.0, energy: str = "flow", tier: str = "draft", bpm: float = 120.0,
                       aspect: str = "16:9", vertical: str = "native", morphs: str = "auto", length: float = 0.0,
                       performer: int = 0) -> dict:
        from xenoform import cloud_final as _cloud_final
        from xenoform import dance_fx as _dance
        from xenoform import dense as _dense
        from xenoform import final_tier
        from xenoform.cloud_morph import plan_shots
        from xenoform.dense import dense_plan

        duration = max(1.0, min(float(duration or 20.0), 600.0))
        step = 60.0 / max(40.0, min(float(bpm or 120.0), 240.0))
        beats = [i * step for i in range(int(duration / step))]
        auto = _dense.auto_morph_count(duration, beats, energy)
        chosen = _dense.morph_count({"morph_count": morphs})
        count = auto if chosen == "auto" else chosen
        if energy == "dense":
            shots = dense_plan(duration, beats, drop=duration * 0.6)["shots"]
        else:
            shots = plan_shots(duration, beats)
        files = final_tier.present()
        video_s = min(duration, float(length)) if length and float(length) > 0 else duration
        plan = _dense.plan_summary(video_s, [b for b in beats if b < video_s], energy, tier, aspect, vertical, performer=int(performer or 0))
        # What a cut this long took on this machine (took.json beside every cut, batch.measured) beats the COST and
        # final_tier.ETA constants: those said about 16 min for the 12 s demo's Final, which took 2:00:32 (27 Oct).
        from xenoform import batch

        rates = batch.measured(work_dir() / "jobs", video_s)
        fin = rates.get("final") or {}
        mine = (rates.get(tier) if tier in ("draft", "fast", "final", "cloud") else {}) or {}
        est = plan.get("estimate") or {}
        n_morphs = int(est.get("morphs") or len(shots))
        cloud_est = _cloud_final.estimate(n_morphs)
        if tier == "cloud":
            # Cloud Final renders on Comfy Cloud, not this GPU: its time is the cloud estimate plus the look pass here,
            # the same figure the Cloud Final tick shows
            gpu = int(cloud_est["seconds"])
            secs = gpu + int(est.get("look_seconds") or 0) + int(est.get("performer_seconds") or 0)
            est.update({"seconds": secs, "minutes": round(secs / 60, 1), "gpu_seconds": gpu, "measured": False,
                        "basis": cloud_est["basis"]})
        elif mine.get("eta_s") and est.get("seconds"):
            ratio = float(mine["eta_s"]) / max(1.0, float(est["seconds"]))
            est.update({"seconds": int(round(mine["eta_s"])), "minutes": round(float(mine["eta_s"]) / 60, 1),
                        "gpu_seconds": int(round(float(est.get("gpu_seconds") or 0) * ratio)), "measured": True,
                        "cuts": int(mine.get("cuts") or 0), "basis": "measured on this machine"})
        try:
            from xenoform import performer as _perf

            performer_status = _perf.available(cfg)
        except Exception as exc:
            performer_status = {"ok": False, "note": f"performer module unavailable: {exc}"}
        from xenoform.hardware import TIERS as _tiers, detect_tier as _detect

        try:
            detected = _detect()
        except Exception:
            detected = {"id": "cpu", "label": "CPU"}
        # Cloud Final: LTX-2.5 open weights on Comfy Cloud (cloud_final); "ready" says whether the key is in this desk's
        # environment, never the key. A plan with more morphs than the cap is not ready: cloud_clips would refuse it.
        cloud = {**_cloud_final.ready(), "max_morphs": _cloud_final.MAX_MORPHS, "model": _cloud_final.label(),
                 "render": "x".join(map(str, _cloud_final.RENDER_916 if aspect == "9:16" else _cloud_final.RENDER_169)),
                 "estimate": cloud_est}
        if n_morphs > _cloud_final.MAX_MORPHS:
            cloud.update({"ready": False, "why": f"Cloud Final takes at most {_cloud_final.MAX_MORPHS} morphs; "
                                                 "choose Length 60 s or fewer Forms."})
        return {
            "plan": plan,
            "lengths": [0, 60, 30, 15],
            "performer": {"choices": list(_dense.PERFORMER_CHOICES), **(performer_status or {})},
            "hardware": {"detected": {"id": detected.get("id"), "label": detected.get("label")},
                         "tiers": [{"id": t["id"], "label": t["label"]} for t in _tiers.values()]},
            "energies": ["flow", "dense"],
            "aspects": ["16:9", "9:16", "1:1"],
            "tiers": ["draft", "fast", "final", "cloud"],
            "shots": len(shots),
            "cloud_final": cloud,
            "final": {"ready": files["ready"], "upscale": files["upscale"], "files": files["files"],
                      "eta_s": int(round(fin["eta_s"])) if fin.get("eta_s") else final_tier.eta_seconds(shots, upscale=files["upscale"]),
                      "eta_measured": bool(fin.get("eta_s")), "per_s": fin.get("per_s"), "cuts": int(fin.get("cuts") or 0),
                      "render": f"{final_tier.RENDER_W}x{final_tier.RENDER_H}",
                      "output": f"{final_tier.OUT_W}x{final_tier.OUT_H}",
                      "render_916": "x".join(map(str, final_tier.RENDER_916)),
                      "output_916": "x".join(map(str, final_tier.out_916()))},
            "vertical": ["native", "crop"],
            "morphs": {"slider": list(_dense.MORPH_SLIDER), "max": _dense.MORPH_MAX, "auto": auto, "count": count,
                       "estimate": _dense.estimate(count, tier, aspect, vertical), "cost": _dense.COST},
            "looks": [{"id": k, "note": v} for k, v in {**_dance.PRESET_NOTES, **_effects_looks()}.items()],
            "house": {"aspect": "9:16", "energy": "dense", "tier": "draft", "dance_fx": "auto", "stem_orbit": True,
                      "beat_fx": True, "end_card": False},
        }

    def _chain_for(body: dict) -> dict:
        """The stills a Make of ``body`` will morph through, in order, as the stills animatic previews them
        (``dense.chain_preview``): nothing rendered, nothing marked used. A Length cut is previewed on the window the
        Make will trim (the same maths as ``_trim_audio``, without the trim), so its count may differ by a still."""
        from xenoform import morph_pass as _mp
        from xenoform import idea as _idea
        from xenoform.dense import chain_preview
        from xenoform.director import apply_director

        state = dict(body or {})
        if isinstance(state.get("scenes"), str):
            state["scene_stills"] = state.pop("scenes")
        state = _idea.shape_state(state)  # the idea line's Scenes choice, so scene_mode below says what the preview drew
        if not isinstance(state.get("cut_plan"), dict):
            state.pop("cut_plan", None)
        audio_id = str(state.get("audio_id") or "demo")
        try:
            features = dict(_features_for(audio_id))
        except HTTPException:
            raise HTTPException(400, "Load a song to see its chain.")
        if audio_id in {"", "demo"}:
            audio = repo_root() / "examples" / "demo.wav"
        else:
            with _LOCK:
                audio = _AUDIO.get(audio_id)
        if audio is None or not Path(audio).is_file():
            raise HTTPException(400, "Load a song to see its chain.")
        try:
            length_s = float(state.get("length_s") or 0)
        except (TypeError, ValueError):
            length_s = 0.0
        dur = float(features.get("duration") or 0.0)
        if str(state.get("morph_count") or "auto").strip().lower() not in {"", "auto", "0"}:
            try:  # a count set by hand gets the clamp Make gives it, so the preview counts what renders (40 in 20 s: 15)
                from xenoform import guardrails as _guard

                state, _ = _guard.apply(state, duration=dur or None, beats=features.get("beats"))
            except Exception:
                pass
        if length_s > 0 and dur > length_s + 1.0:
            beats = [float(b) for b in (features.get("beats") or [])]
            try:
                from xenoform.beatfx import drop_time

                drop = float(drop_time(Path(audio), beats))
            except Exception:
                drop = dur * 0.6
            start = max(0.0, min(drop - length_s * 0.45, dur - length_s))
            if state.get("length_start") not in (None, ""):
                try:
                    start = max(0.0, min(float(state["length_start"]), dur - length_s))
                except (TypeError, ValueError):
                    pass
            earlier = [b for b in beats if b <= start + 1e-6]
            if earlier:
                start = max(earlier)
            end = start + length_s
            features["beats"] = [round(b - start, 4) for b in beats if start <= b < end]
            features["duration"] = length_s
            features["sections"] = [{**s, "start": round(max(0.0, float(s.get("start") or 0.0) - start), 4),
                                     "end": round(min(length_s, float(s.get("end") or 0.0) - start), 4)}
                                    for s in (features.get("sections") or [])
                                    if float(s.get("end") or 0.0) > start and float(s.get("start") or 0.0) < end]
        own_folder = str(state.get("own_folder") or "").strip()
        own_id = str(state.get("own_id") or "")
        if own_id:
            with _LOCK:
                dropped = _OWN.get(own_id)
            if dropped is not None and Path(dropped).is_dir():
                own_folder = str(dropped)
        if own_folder:
            try:
                from xenoform import own_media

                found = own_media.scan(own_folder)
                state["morph_targets"] = list(found["images"]) + [str(p) for p in (state.get("morph_targets") or []) if str(p) not in found["images"]]
            except Exception:
                pass
        try:
            directed = apply_director(features, state)
        except Exception:
            directed = features
        from xenoform.cloud_morph import CutPlanError

        try:
            pre = chain_preview(directed, state, Path(audio))
        except CutPlanError as exc:
            raise HTTPException(400, str(exc)) from exc
        pins = _mp.pins_of(state)
        rows = [{"index": k, "file": str(s.get("file") or ""), "noun": str(s.get("noun") or ""),
                 "kind": "scene" if str(s.get("kind") or "") == "scene" else "object", "own": bool(s.get("own")),
                 "user": bool(s.get("user")), "pinned": bool(s.get("pinned")),
                 "thumb": "/api/stills/thumb?file=" + quote(str(s.get("file") or ""), safe="/") if not s.get("user") else ""}
                for k, s in enumerate(pre["stills"])]
        dropped_pins = sorted(k for k in pins if k < len(rows) and not rows[k]["pinned"])
        return {"vibe": pre["vibe"], "pool_vibe": _mp.vibe_for(state), "count": len(rows), "morphs": max(0, len(rows) - 1),
                "shots": len(pre["shots"]), "long_song": bool(pre["long_song"]), "scene_mode": _mp.scenes_choice(state),
                "stills": rows, "pinned": [r["index"] for r in rows if r["pinned"]], "dropped_pins": dropped_pins,
                "length_s": length_s if length_s > 0 and dur > length_s + 1.0 else 0}

    @app.get("/api/simple/chain")
    def simple_chain_get(audio_id: str = "demo", vibe: str = "", idea: str = "", scene_stills: str = "off", energy_preset: str = "dense",
                         quality_tier: str = "draft", aspect: str = "9:16", length_s: float = 0.0, morph_count: str = "auto",
                         chain_pins: str = "", seed: int = 0) -> dict:
        """The chain a Make with these choices will morph through (``chain_pins``: a JSON object of slot to file)."""
        pins = {}
        if chain_pins:
            try:
                pins = json.loads(chain_pins)
            except ValueError:
                raise HTTPException(400, "chain_pins is a JSON object of slot to still file.")
        return _chain_for({"audio_id": audio_id, "vibe": vibe, "idea": idea, "scene_stills": scene_stills, "energy_preset": energy_preset,
                           "quality_tier": quality_tier, "aspect": aspect, "length_s": length_s, "morph_count": morph_count,
                           "chain_pins": pins, "seed": seed, "mode": "simple"})

    @app.post("/api/simple/chain")
    def simple_chain(body: dict) -> dict:
        """The same, for the whole make body the desk sends (the idea line, Length, Your footage, the pins, every knob)."""
        return _chain_for(body or {})

    @app.post("/api/simple/idea")
    def simple_idea(body: dict) -> dict:
        """What the idea line was read as (``xenoform.idea.read``: ``scenes`` to grow as wide frames, ``objects`` the
        catalogue knows, ``own`` shapes to grow, ``family``, ``performer``, one ``summary`` line) and what a Make will
        grow for it first (``grow``, under ``pool_vibe``), so the desk says so under the line before Make."""
        from xenoform import idea as _idea
        from xenoform import morph_pass as _mp

        line = str((body or {}).get("idea") or "")
        vibe = str((body or {}).get("vibe") or "")
        reading = _idea.read(line, vibe)
        pool_vibe = _mp.vibe_for({"vibe": vibe}) if vibe else ""
        return {**reading, "grow": _idea.grow_plan(reading, pool_vibe), "pool_vibe": pool_vibe}

    def _video_dir(video_id: str) -> Path:
        folder = work_dir() / "jobs" / storage_id(video_id, fallback="")
        if not (folder / "xenoform.mp4").is_file():
            raise HTTPException(404, "That video is not on this machine.")
        return folder

    @app.get("/api/videos/{video_id}/shots")
    def video_shots(video_id: str) -> dict:
        """The cut's shots lane, read-only (``lane.build``): every shot with its object, section and boundary, the
        transitions, the performer and own-footage slots, from the job's simple.json. The seed of the timeline."""
        from xenoform import lane

        folder = _video_dir(video_id)
        path = folder / "simple" / "simple.json"
        if not path.is_file():
            return {"id": video_id, "duration": 0.0, "shots": [], "sections": [], "overlays": [], "note": "This cut has no shot record."}
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return {"id": video_id, "duration": 0.0, "shots": [], "sections": [], "overlays": [], "note": "This cut's shot record did not read."}
        out = lane.build(info, video_id)
        out["version"] = (folder / "xenoform.mp4").stat().st_mtime_ns  # the tiles' frame pictures change with the video
        return out

    @app.post("/api/videos/{video_id}/hook")
    def video_hook(video_id: str, body: dict | None = None) -> dict:
        from xenoform.beatfx import export_hook, pick_hook

        folder = _video_dir(video_id)
        length = max(5.0, min(float((body or {}).get("length") or 15.0), 60.0))
        src = folder / "xenoform.mp4"
        meta = _read_meta(folder)
        beats = []
        try:
            beats = list(_features_for(str(meta.get("audio_id") or "demo")).get("beats") or [])
        except HTTPException:
            pass
        window = pick_hook(src, length=length, beats=beats)
        made = export_hook(src, folder / "hook.mp4", window["start"], min(length, window["end"] - window["start"]))
        return {**window, "seconds": made["seconds"], "url": f"/api/videos/{video_id}/hook.mp4"}

    @app.get("/api/videos/{video_id}/hook.mp4")
    def video_hook_file(video_id: str) -> FileResponse:
        path = _video_dir(video_id) / "hook.mp4"
        if not path.is_file():
            raise HTTPException(404, "Make the 15 s hook first.")
        return FileResponse(path, media_type="video/mp4", filename=f"xenoform-hook-{video_id}.mp4",
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/videos/{video_id}/edit")
    def video_edit(video_id: str) -> dict:
        """Share › Edit in Resolve (``edit_export.build``): the cut as a timeline for Resolve, Premiere or Final Cut,
        a clip a shot on V1, the song on A1, markers at the drop and the dressed handoffs, zipped with its media."""
        from xenoform import edit_export

        folder = _video_dir(video_id)
        try:
            pack = edit_export.build(folder, video_id)
        except Exception as exc:  # ffmpeg or the disk: say so on the desk instead of a bare 500
            log.exception("edit pack for %s", video_id)
            raise HTTPException(500, f"The edit pack did not build: {exc}") from exc
        return {**{k: v for k, v in pack.items() if k != "signature"}, "url": f"/api/videos/{video_id}/edit.zip"}

    @app.post("/api/videos/{video_id}/edit/reveal")
    def video_edit_reveal(video_id: str) -> dict:
        """Opens the unzipped edit pack in the file manager with the timeline file selected, so Edit in Resolve visibly
        does something on this machine (it used to add one line of small print under Share). Windows Explorer, else
        the platform's opener on the folder; ``opened`` is false where there is none (a desk reached from elsewhere)."""
        import subprocess
        import sys

        from xenoform import edit_export

        pack = edit_export.build(_video_dir(video_id), video_id)
        folder = Path(pack["folder"])
        target = folder / pack["timeline"]
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", f"/select,{target if target.is_file() else folder}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(target if target.is_file() else folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError:
            return {"opened": False, "folder": str(folder), "timeline": pack["timeline"]}
        return {"opened": True, "folder": str(folder), "timeline": pack["timeline"]}

    @app.get("/api/videos/{video_id}/edit.zip")
    def video_edit_zip(video_id: str) -> FileResponse:
        from xenoform import edit_export

        pack = edit_export.build(_video_dir(video_id), video_id)  # the pack made for this cut, or a new one if it changed
        return FileResponse(pack["zip"], media_type="application/zip", filename=pack["zip_name"], headers={"Cache-Control": "no-store"})

    @app.get("/api/videos/{video_id}/frame.jpg")
    def video_frame(video_id: str, t: float = 0.0, w: int = 160) -> FileResponse:
        """One frame of the cut at ``t`` seconds, ``w`` pixels wide: the timeline's tiles show each shot as it looks in
        the cut (the shot's middle), for an object cut and a clips cut alike. Cached per version of the video."""
        from xenoform.video import ffmpeg_bin

        folder = _video_dir(video_id)
        src = folder / "xenoform.mp4"
        width = max(48, min(480, int(w)))
        t = max(0.0, float(t))
        dest = folder / "thumbs" / f"{src.stat().st_mtime_ns}_{t:.2f}_{width}.jpg"
        if not dest.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            import subprocess

            subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                            "-vf", f"scale={width}:-2", "-q:v", "4", str(dest)], check=False, capture_output=True)
            if not dest.is_file():
                raise HTTPException(404, "No frame there.")
        return FileResponse(dest, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    @app.get("/api/videos/{video_id}/poster.jpg")
    def video_poster(video_id: str) -> FileResponse:
        """A frame of the cut for the Variations page: just after the drop the record names, else two fifths in."""
        from xenoform.video import ffmpeg_bin, probe_video

        folder = _video_dir(video_id)
        src, dest = folder / "xenoform.mp4", folder / "poster.jpg"
        if not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime:
            info = probe_video(src)
            seconds = info["frames"] / info["fps"] if info["fps"] else 0.0
            try:
                drop = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8")).get("drop")
            except (OSError, ValueError):
                drop = None
            at = float(drop) + 0.4 if drop is not None and float(drop) + 0.4 < seconds else 0.4 * seconds
            subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1",
                            "-vf", "scale=360:-2", "-q:v", "4", str(dest)], check=True)
        return FileResponse(dest, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    # Variations (xenoform.batch): several Drafts of one idea queued for the night, one at a time on a free GPU, and
    # compared in the morning on /variations, where any of them can be queued again at Final.
    _batch: dict[str, Any] = {}

    def _gpu_busy() -> str:
        from xenoform import batch

        with _LOCK:
            if any(item.get("status") == "running" for item in _JOBS.values()):
                return "A cut is rendering on this desk: the next variation waits for it."
        return batch.comfy_busy(str(cfg["comfy"].get("base_url") or "http://127.0.0.1:8188"))

    def _job_of(job_id: str) -> dict | None:
        with _LOCK:
            job = _JOBS.get(job_id)
            return dict(job) if job is not None else None

    def _cancel_job(job_id: str) -> None:
        with _LOCK:
            event = _CANCEL.get(job_id)
        if event is not None:
            event.set()

    def _batches():
        """The one queue of this desk, made on first use (no thread runs until a batch is queued or resumed)."""
        from xenoform import batch

        if "runner" not in _batch:
            _batch["runner"] = batch.Runner(work_dir() / "batches", start=lambda body: _start_job(body)["id"],
                                            job_of=_job_of, busy=_gpu_busy, cancel=_cancel_job)
        return _batch["runner"]

    def _batch_view(b: dict) -> dict:
        """A batch as the page shows it: each item without its make body, what it varied, its cut, poster and time,
        and the measured time of what is still to run."""
        from xenoform import batch

        rates = batch.measured(work_dir() / "jobs", float(b.get("seconds") or 0.0) or None)
        items, left = [], 0.0
        for it in b.get("items") or []:
            body = it.get("body") or {}
            row = {k: it.get(k) for k in ("k", "label", "vary", "kind", "of", "status", "detail", "job_id", "progress", "took_s", "eta_s")}
            row.update({"vibe": body.get("vibe") or "", "seed": body.get("seed"), "idea": body.get("idea") or "",
                        "look": body.get("dance_fx") or "auto",
                        "knobs": {k: v for k, v in (body.get("macros") or {}).items() if k in ("intensity", "speed", "chaos", "glow")}})
            if it.get("status") == "done" and it.get("job_id"):
                row.update({"video": f"/api/videos/{it['job_id']}/video", "poster": f"/api/videos/{it['job_id']}/poster.jpg"})
            if it.get("status") == "running" and it.get("eta_s") is not None:
                left += float(it["eta_s"] or 0.0)
            elif it.get("status") in ("queued", "waiting"):
                left += float((rates.get(it.get("kind") or "draft") or {}).get("eta_s") or 0.0)
            items.append(row)
        return {**{k: b.get(k) for k in ("id", "created", "vary", "count", "song", "idea", "vibe", "length_s", "seconds")},
                "items": items, "left_s": round(left, 1), "measured": rates}

    @app.get("/variations")
    def variations_page() -> FileResponse:
        return FileResponse(Path(__file__).parent / "ui_static" / "variations.html")

    @app.get("/api/batches")
    def batches_index(seconds: float = 0.0) -> dict:
        """Every batch, newest first, and what a cut ``seconds`` long takes here (``batch.measured``)."""
        from xenoform import batch

        return {"batches": [_batch_view(b) for b in _batches().batches()], "counts": list(batch.COUNTS),
                "vary": list(batch.VARY), "measured": batch.measured(work_dir() / "jobs", seconds or None)}

    @app.post("/api/batches")
    def batches_add(body: dict) -> dict:
        """Queue ``count`` Drafts of the make body ``body``, varying ``vary`` (seed, vibe or feel)."""
        make = dict(body.get("body") or {})
        audio_id = str(make.get("audio_id") or "demo")
        with _LOCK:
            known = audio_id == "demo" or audio_id in _AUDIO
        if not known:
            raise HTTPException(400, "Load a song before queueing variations.")
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        # the cut's length, for the measured estimate: the Length picked, else the whole song
        seconds = float(make.get("length_s") or 0.0) or float(features.get("duration") or 0.0)
        try:
            count = int(body.get("count") or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, "How many must be a whole number: 1, 3, 5 or 10.") from None
        try:
            b = _batches().add(make, count, str(body.get("vary") or ""), seconds=seconds)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return _batch_view(b)

    @app.get("/api/batches/{batch_id}")
    def batch_get(batch_id: str) -> dict:
        b = _batches().get(batch_id)
        if b is None:
            raise HTTPException(404, "No such batch.")
        return _batch_view(b)

    @app.post("/api/batches/{batch_id}/cancel")
    def batch_cancel(batch_id: str) -> dict:
        from xenoform import batch

        try:
            return _batch_view(_batches().cancel(batch_id))
        except KeyError as exc:
            raise HTTPException(404, "No such batch.") from exc
        except batch.Elsewhere as exc:  # another desk on this work folder is running it
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/batches/{batch_id}/resume")
    def batch_resume(batch_id: str) -> dict:
        from xenoform import batch

        try:
            return _batch_view(_batches().resume(batch_id))
        except KeyError as exc:
            raise HTTPException(404, "No such batch.") from exc
        except batch.Elsewhere as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/batches/{batch_id}/items/{k}/final")
    def batch_final(batch_id: str, k: int) -> dict:
        """Render this one at Final: the variation's own body at Final, its chain pinned from the cut it made."""
        from xenoform import batch

        runner = _batches()
        b = runner.get(batch_id)
        src = next((i for i in (b or {}).get("items") or [] if i.get("k") == k and i.get("kind") == "draft"), None)
        if b is None or src is None:
            raise HTTPException(404, "No such variation.")
        if src.get("status") != "done" or not src.get("job_id"):
            raise HTTPException(409, "This variation has not made its Draft yet.")
        pins = {}
        try:
            rec = json.loads((work_dir() / "jobs" / storage_id(src["job_id"]) / "simple" / "simple.json").read_text(encoding="utf-8"))
            pins = {str(i): str(f) for i, f in enumerate(rec.get("stills") or [])}
        except (OSError, ValueError):
            pass
        try:
            runner.add_final(batch_id, k, pins)
        except batch.Elsewhere as exc:
            raise HTTPException(409, str(exc)) from exc
        return _batch_view(runner.get(batch_id) or b)

    @app.get("/api/videos/{video_id}/video")
    def video_file(video_id: str) -> FileResponse:
        return FileResponse(_video_dir(video_id) / "xenoform.mp4", media_type="video/mp4", headers={"Cache-Control": "no-store"})

    @app.get("/api/videos")
    def videos_index(limit: int = 24) -> dict:
        rows = []
        root = work_dir() / "jobs"
        folders = sorted((p for p in root.glob("*") if (p / "xenoform.mp4").is_file()) if root.is_dir() else [],
                         key=lambda p: (p / "xenoform.mp4").stat().st_mtime, reverse=True)
        for folder in folders[: max(1, min(int(limit), 200))]:
            meta = _read_meta(folder)
            if not meta.get("simple"):
                continue
            simple = {}
            simple_file = folder / "simple" / "simple.json"
            if simple_file.is_file():
                try:
                    simple = json.loads(simple_file.read_text(encoding="utf-8"))
                except ValueError:
                    simple = {}
            with _LOCK:
                live = _JOBS.get(folder.name)
            rows.append({
                "id": folder.name,
                "created": meta.get("created") or "",
                # How long the cut took: the live job, took.json, the older manifests, else the file's age (job_timing)
                "seconds": job_timing.seconds_for(folder, live),
                "vibe": meta.get("vibe") or "",
                "song": meta.get("song") or "",
                "recipe": meta.get("recipe") or "",
                "energy": meta.get("energy_preset") or "flow",
                "aspect": meta.get("aspect") or "16:9",
                "tier": meta.get("quality_tier") or "draft",
                "engine": simple.get("engine") or "",
                "url": f"/api/videos/{folder.name}/video",
                "hook": (folder / "hook.mp4").is_file(),
            })
        return {"videos": rows}

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

    def _analyze_file(path: Path) -> dict:
        """The same analysis /api/analyze runs on an upload."""
        import librosa

        from xenoform.analyze import analyze_audio

        audio, sr = librosa.load(path, sr=None, mono=True)
        return analyze_audio(audio, int(sr), fps=float(cfg["fps"]), onset_tau=float(cfg["analyze"]["onset_tau"]),
                             beat_tau=float(cfg["analyze"]["beat_tau"]),
                             section_min_seconds=float(cfg["analyze"]["section_min_seconds"]))

    def _trim_audio(audio_id: str, audio_path: Path, length_s: float, start_s: float | None = None) -> tuple[str, Path] | None:
        """A ``length_s`` cut of the song centred a little before its drop (or from ``start_s`` when the Make body
        names a window), snapped back to a beat, with short fades, registered as its own audio id (analysed like
        an upload). None when the song is already short."""
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        dur = float(features.get("duration") or 0.0)
        if length_s <= 0 or dur <= 0 or dur <= length_s + 1.0:
            return None
        beats = [float(b) for b in (features.get("beats") or [])]
        try:
            from xenoform.beatfx import drop_time

            drop = float(drop_time(Path(audio_path), beats))
        except Exception:
            drop = dur * 0.6
        start = max(0.0, min(drop - length_s * 0.45, dur - length_s))
        if start_s is not None:
            start = max(0.0, min(float(start_s), dur - length_s))
        earlier = [b for b in beats if b <= start + 1e-6]
        if earlier:
            start = max(earlier)  # start on a beat
        new_id = uuid.uuid4().hex[:10]
        dest = work_dir() / "uploads" / f"{new_id}.wav"
        dest.parent.mkdir(parents=True, exist_ok=True)
        from xenoform.video import ffmpeg_bin

        fade_out = max(0.0, length_s - 0.4)
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{length_s:.3f}", "-i", str(audio_path),
                        "-af", f"afade=t=in:d=0.3,afade=t=out:st={fade_out:.3f}:d=0.4", "-ar", "48000", "-ac", "2", str(dest)],
                       check=True)
        features = _analyze_file(dest)
        features["trimmed_from"] = {"audio_id": audio_id, "start": round(start, 3), "length_s": float(length_s),
                                    "drop": round(drop, 3), "song_duration": round(dur, 3)}
        try:  # the cut inherits the song's stems (sliced), or gets its own split in the background
            from xenoform.stems_api import slice_stems, start_background_split, stems_path_for

            full = stems_path_for(Path(audio_path))
            if full is None or slice_stems(full, start, length_s, dest) is None:
                start_background_split(dest)
        except Exception:
            log.exception("stems for the cut")
        with _LOCK:
            _AUDIO[new_id] = dest
            _FEATURES[new_id] = features
        return new_id, dest

    def _start_job(body: dict) -> dict:
        if isinstance(body.get("scenes"), str):  # the Simple scenes choice sent as ``scenes``: the list form is the Advanced scene list
            body["scene_stills"] = body.pop("scenes")
        audio_id = str(body.get("audio_id") or "demo")
        if audio_id == "demo":
            audio_path = repo_root() / "examples" / "demo.wav"
        else:
            with _LOCK:
                audio_path = _AUDIO.get(audio_id)
        if audio_path is None or not Path(audio_path).exists():
            raise HTTPException(400, "Load a song before generating.")
        try:
            length_s = float(body.get("length_s") or 0)
        except (TypeError, ValueError):
            length_s = 0.0
        if length_s > 0:
            try:  # ``length_start``: where the cut begins (seconds into the song); by default a little before the drop
                start_s = float(body["length_start"]) if body.get("length_start") not in (None, "") else None
            except (TypeError, ValueError):
                start_s = None
            trimmed = _trim_audio(audio_id, Path(audio_path), length_s, start_s)
            if trimmed is not None:
                source_path = Path(audio_path)
                audio_id, audio_path = trimmed
                body["audio_id"] = audio_id
                with _LOCK:
                    cut_from = (_FEATURES.get(audio_id) or {}).get("trimmed_from") or {}
                # the full song and where the cut starts in it: the performer's pre-roll reaches before the cut
                body["song_source"] = {"path": str(source_path), "offset": float(cut_from.get("start") or 0.0)}
                body["song"] = (str(body.get("song") or "").strip() + f" ({int(length_s)} s cut)").strip()
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
        _apply_own(body)
        stills = work_dir() / "continuity"
        for scene in body.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            name = Path(str(scene.get("still_name") or "")).name
            if name and (stills / name).is_file():
                scene["reference_still"] = str(stills / name)
        # Real stems when the user split them (POST /api/stems caches stems.json by song hash): the house look
        # (stem_orbit, dance_fx) then follows the song's own kick/bass/vocal envelopes instead of the mixdown.
        if not body.get("stems_path"):
            try:
                from xenoform.stems_api import stems_path_for

                cached = stems_path_for(audio_path)
            except Exception:
                cached = None
            if cached is not None:
                body.setdefault("stems_path", str(cached))
        job_id = uuid.uuid4().hex[:8]
        out = work_dir() / "jobs" / job_id / "xenoform.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        recipe = _write_meta(out.parent, body, audio_id)
        if recipe and not body.get("simple_recipe"):
            body["simple_recipe"] = recipe
        cancel_event = threading.Event()
        only = [str(item) for item in (body.get("only_scenes") or []) if str(item)]
        try:
            features = _features_for(audio_id)
        except HTTPException:
            features = {}
        from xenoform import guardrails as _guard
        _gb = _guard.cached_vram()
        guarded, guard_report = _guard.apply(body, duration=(features or {}).get("duration") or body.get("duration"),
                                             beats=(features or {}).get("beats"), vram_gb=_gb, cfg=cfg)
        body.clear()
        body.update(guarded)
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
            "guardrails": guard_report,
            # Advanced desk, per-boundary scene transitions (after the max-2-per-type guard) and per-shot
            # Look overrides. Forwarded with the body into the job state; see docs/transitions.md.
            "scene_transitions": [t.get("kind") if isinstance(t, dict) else t for t in (body.get("scene_transitions") or [])],
            "shot_looks": [str(s.get("dance_fx") or "") for s in (body.get("scenes") or []) if isinstance(s, dict)],
            "stems_path": str(body.get("stems_path") or ""),
            # Honest timing (job_timing): t0 / started, the planned seconds per phase for this song and Make, and the
            # overall fraction, ETA and phase boundaries _run_job's on_progress keeps up to date.
            **job_timing.start_fields(job_timing.plan_for(features, body), body),
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
        return {"id": job_id, "only_scenes": only, "guardrails": guard_report}

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

    @app.get("/api/guardrails")
    def guardrails_list() -> dict:
        from xenoform import guardrails as _guard

        return {"guardrails": _guard.summary()}

    @app.post("/api/guardrails/check")
    def guardrails_check(body: dict) -> dict:
        """Dry run: what the guardrails would change in these settings. Nothing renders."""
        from xenoform import guardrails as _guard

        clean, report = _guard.apply(body, duration=body.get("duration"), vram_gb=body.get("vram_gb"))
        clean.pop("guardrails", None)
        return {"report": report, "settings": clean}

    @app.post("/api/generate")
    def generate(body: dict) -> dict:
        return _start_job(body)

    @app.post("/api/cloud/estimate")
    def cloud_estimate(body: dict) -> dict:
        """Cloud quality (PAID, opt-in only): the plan, its exact cost, and a confirm token.

        Read only. Nothing is queued or uploaded. The token is what the explicit
        confirm click sends back with /api/generate; without it no paid node runs.
        """
        from xenoform.cloud_morph import OFF_MESSAGE, CutPlanError, mint_token, paid_cloud_enabled, plan_for

        if not paid_cloud_enabled(cfg, bool(body.get("paid_cloud"))):
            raise HTTPException(status_code=403, detail=OFF_MESSAGE)
        features = _features_for(str(body.get("audio_id") or "demo"))
        state = {key: body.get(key) for key in ("vibe", "palette", "preset", "brief", "scenes", "customs", "seed", "cut_plan")}
        try:
            plan = plan_for(float(features.get("duration") or 0.0), list(features.get("beats") or []), state, cfg)
        except CutPlanError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        est = plan["estimate"]
        plan["token"] = "" if est["over_cap"] else mint_token(est)
        plan["can_submit"] = bool(plan["token"]) and plan["node_installed"] and (plan["key_present"] or plan["dry_run"])
        return plan

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                raise HTTPException(404, "No such cut. It may be from before the desk restarted.")
            return {key: value for key, value in job.items() if key != "path"}

    @app.post("/api/jobs/{job_id}/cancel")
    def job_cancel(job_id: str) -> dict:
        with _LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                raise HTTPException(404, "No such cut. It may be from before the desk restarted.")
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
            raise HTTPException(404, "That cut is not ready yet.")
        return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    def _job_dir(job_id: str) -> Path:
        with _LOCK:
            job = _JOBS.get(job_id)
        path = Path(job["path"]) if job and job.get("path") else None
        if path is None:
            raise HTTPException(404, "No such cut. It may be from before the desk restarted.")
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

        payload = inspect_setup(comfy_url=str(cfg["comfy"].get("base_url") or ""))
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

        setup = inspect_setup(comfy_url=str(cfg["comfy"].get("base_url") or ""))
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

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def bad_shape(request: Request, exc: RequestValidationError):
        # a body that is a list, a string or nothing, or a missing upload: one sentence instead of FastAPI's field list
        # (the stress pass found the list on thirty routes the desk calls); the list stays in the diagnostics
        fields = ", ".join(str(err.get("loc", [""])[-1]) for err in exc.errors()[:4] if err.get("loc"))
        return JSONResponse(status_code=422, content={
            "detail": "That request was not in the shape the desk expects. Reload the page and try again.",
            "diagnostics": f"{request.method} {request.url.path}: {fields or 'body'}"})

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
        try:
            mtime = out.stat().st_mtime_ns  # outside the lock: a stat while ffmpeg may be writing
        except OSError:
            mtime = None
        # the chain the render picked, once dense.write_chain has written it: the making screen shows it
        chain = None if (_JOBS.get(job_id) or {}).get("chain") else _read_chain(work)
        with _LOCK:
            job = _JOBS[job_id]
            job["stage"] = stage
            job["progress"] = round(float(frac), 4)
            job["detail"] = detail
            if chain:
                job["chain"] = chain
            job_timing.tick(job, stage, frac, detail, job_timing.elapsed(job))
            # The draft stays up while the morphs render and the cut composes: the player is only re-pointed when the
            # file itself changed (every "Cutting shot k of N" used to bump the version and restart the preview).
            if mtime is not None and (stage in {"animatic", "done"} or mtime != job.get("video_mtime_ns")):
                version = int(job.get("video_version") or 0) + 1
                job["video_version"] = version
                job["video"] = f"/api/jobs/{job_id}/video?v={version}"
                job["video_mtime_ns"] = mtime
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
        from xenoform.hardware import TIERS as _tiers

        chosen = str(body.get("hardware_tier") or "auto").strip().lower()
        start = dict(_tiers[chosen]) if chosen in _tiers else detect_tier()  # Fine-tune -> GPU, else the detected card
        result, tier_id, note = run_resilient(once, start)
        qa_report = None
        if not cancel_event.is_set() and Path(out).is_file() and not body.get("tiny"):
            on_progress("qa", 0.05, "Checking for lag, artifacts and off-beat cuts")  # post_qa reports each pass from 0.2
            try:
                from xenoform import post_qa

                beats = []
                fpath = work / "features.json"
                if fpath.is_file():
                    beats = list((json.loads(fpath.read_text(encoding="utf-8")) or {}).get("beats") or [])
                fix = bool((post_qa._rule("lag_qa") or {}).get("auto_fix", True))
                qa_report = post_qa.run(out, fps=24.0, beats=beats, vj=bool(body.get("vj")), fix=fix, report=on_progress)
            except Exception:
                log.exception("post QA")
        with _LOCK:
            job = _JOBS[job_id]
            if qa_report is not None:
                job["qa"] = qa_report
                gr = job.setdefault("guardrails", {"applied": [], "warnings": [], "messages": []})
                for line in qa_report.get("issues") or []:
                    gr.setdefault("messages", []).append(f"[qa] {line}")
                if (qa_report.get("lag_fix") or {}).get("fixed"):
                    gr.setdefault("messages", []).append(f"[qa] lag fixed: {qa_report['lag_fix']['method']}")
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
            took = job_timing.finish(job, job_timing.elapsed(job))  # took_s (QA included), breakdown, the done stage
        job_timing.write_took(work, took)  # beside the cut, so My videos keeps the numbers after a desk restart
    except JobCancelled as exc:
        with _LOCK:
            job = _JOBS[job_id]
            job["status"] = "cancelled"
            job["detail"] = str(exc) or "Cancelled. The card changed."
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


def _effects_looks() -> dict:
    """The Looks that live in effects.py (the Dither look), with their notes, beside dance_fx's presets."""
    from xenoform import effects

    return dict(effects.LOOK_NOTES)


def _apply_own(body: dict) -> dict:
    """Your own clips and images (Simple), into the make body in place: a folder path typed in, or the files dropped on
    the desk (POST /api/own). The images lead the morph chain (``morph_targets``); the clips are cut in on the beat
    (``own_clips``, dense.run_simple) unless the body says ``cut_in_clips: false`` (the desk's Work in progress > Your
    clips, off by default; a caller that does not send it keeps the clips, as before)."""
    own_folder = str(body.get("own_folder") or "").strip()
    own_id = str(body.get("own_id") or "")
    if own_id:
        with _LOCK:
            dropped = _OWN.get(own_id)
        if dropped is not None and Path(dropped).is_dir():
            own_folder = str(dropped)
    if own_folder:
        try:
            from xenoform import own_media

            found = own_media.scan(own_folder)
            extra = [str(p) for p in (body.get("morph_targets") or []) if str(p) not in found["images"]]
            # clips and objects never share a cut (Tys, 28 Oct): a clips cut takes only the clips, an object cut only
            # the images (they lead the chain) and leaves the clips out, whatever cut_in_clips says
            if str(body.get("morph_source") or "").strip().lower() == "clips":
                body["morph_targets"] = []
                body["own_clips"] = found["clips"]
            else:
                body["morph_targets"] = list(found["images"]) + extra
                body["own_clips"] = []
            body["own_folder"] = found["folder"]
        except Exception as exc:
            log.warning("own folder %s skipped: %s", own_folder, exc)
            body["own_folder"] = ""
    return body


def _read_chain(folder: Path) -> list[dict] | None:
    """The render's chain (``dense.write_chain``: ``simple/chain.json``, a ``noun`` and ``kind`` per still), or None
    until the render has picked its stills."""
    path = Path(folder) / "simple" / "chain.json"
    try:
        rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) and rows else None


def _read_meta(folder: Path) -> dict:
    path = Path(folder) / "meta.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        return {}


def _write_meta(folder: Path, body: dict, audio_id: str) -> str:
    """What My videos needs to list, reopen and re-render a Simple cut."""
    try:
        from datetime import datetime

        from xenoform.simple_recipe import encode

        simple = str(body.get("mode") or "") == "simple" or bool(body.get("vibe"))
        meta = {
            "created": datetime.now().astimezone().isoformat(timespec="seconds"),
            "simple": simple,
            "audio_id": audio_id,
            "song": str(body.get("song") or body.get("song_label") or "")[:80],
            "vibe": str(body.get("vibe") or ""),
            "energy_preset": str(body.get("energy_preset") or "flow"),
            "aspect": str(body.get("aspect") or "16:9"),
            "quality_tier": str(body.get("quality_tier") or "draft"),
            "recipe": encode({**body, "idea": body.get("idea") or body.get("brief") or ""}) if simple else "",
        }
        (Path(folder) / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        return meta["recipe"]
    except Exception:
        log.exception("job meta")
        return ""


def serve(host: str = "127.0.0.1", port: int = 47317, cfg: dict | None = None) -> None:
    import uvicorn

    app = create_app(cfg)
    log.info("Xenoform desk at http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
