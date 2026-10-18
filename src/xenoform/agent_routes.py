"""Local REST API the desk and the MCP server share.

Every route is meant for localhost. There is no token. The browser already
sends the storyboard here, and an agent process on this machine calls the
same paths.
"""

from __future__ import annotations

import copy
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException, Request
from fastapi.responses import Response


_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}
_QUALITIES = {"live", "turbo", "draft", "final"}
_MCP_PORT = 47319
_MCP_PROC: dict[str, Any] = {"proc": None}


def empty_session() -> dict[str, Any]:
    return {
        "revision": 0,
        "source": "empty",
        "audio_id": "demo",
        "title": "Demo assembly",
        "brief": "",
        "register": "pynchon",
        "preset": "",
        "quality": "live",
        "palette": "violet",
        "flash": "normal",
        "sliders": {},
        "scenes": [],
        "blocks": [],
        "cards": [],
        "motif": "",
        "callback": "",
        "video": "",
        "recipe": "",
        "job_id": "",
    }


def _bump(session: dict, source: str, **fields: Any) -> dict:
    data = session.setdefault("data", empty_session())
    for key, value in fields.items():
        if value is not None:
            data[key] = value
    data["revision"] = int(data.get("revision") or 0) + 1
    data["source"] = source
    return data


def public_session(data: dict) -> dict:
    kept = dict(data)
    kept.pop("path", None)
    return kept


def mount(
    app,
    *,
    lock: threading.Lock,
    session: dict,
    features_for: Callable[[str], dict],
    start_job: Callable[[dict], dict],
    notebook: Callable[[str, list, str], dict],
    save_notebook: Callable[[str, dict], None],
    video_for: Callable[[str], str],
    lessons_file: Callable[[], Path],
    repo_root: Callable[[], Path],
    job_snapshot: Callable[[str], dict | None],
    resolve_video: Callable[[str], Path | None],
) -> None:
    if "data" not in session:
        session["data"] = empty_session()

    def current() -> dict:
        with lock:
            return copy.deepcopy(session["data"])

    def store(source: str, **fields: Any) -> dict:
        with lock:
            data = _bump(session, source, **fields)
            return copy.deepcopy(data)

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"ok": True, "service": "xenoform", "bind": "localhost", "auth": "none"}

    @app.get("/api/v1/session")
    def read_session() -> dict:
        return public_session(current())

    @app.post("/api/v1/session")
    def write_session(body: dict) -> dict:
        fields = {key: body.get(key) for key in empty_session() if key in body and key not in {"revision", "source"}}
        data = store("ui" if body.get("source") != "agent" else "agent", **fields)
        return public_session(data)

    @app.get("/api/v1/registers")
    def registers() -> dict:
        from xenoform.director import public_registers

        rows = [
            {"id": item["id"], "name": item["name"], "voice": item["voice"], "palette": item["palette"]}
            for item in public_registers()
        ]
        return {"registers": rows}

    @app.get("/api/v1/registers/{register_id}")
    def register_one(register_id: str) -> dict:
        from xenoform.director import public_registers

        found = next((item for item in public_registers() if item["id"] == register_id), None)
        if found is None:
            raise HTTPException(404, "No such register.")
        return found

    @app.post("/api/v1/register")
    def set_register(body: dict) -> dict:
        from xenoform.director import register_by_id
        from xenoform.storyboard import blocks_from_scenes, plan_with_hook

        data = current()
        voice = register_by_id(str(body.get("id") or body.get("register") or "pynchon"))
        features = features_for(str(data.get("audio_id") or "demo"))
        scenes, planner = plan_with_hook(features, voice, str(data.get("brief") or ""))
        stored = store(
            "agent",
            register=voice["id"],
            palette=voice["palette"],
            flash=voice["flash"],
            sliders=dict(voice["sliders"]),
            cards=[dict(card) for card in voice["cards"]],
            scenes=scenes,
            blocks=blocks_from_scenes(scenes),
        )
        stored["planner"] = planner
        return public_session(stored)

    @app.get("/api/v1/presets")
    def presets() -> dict:
        from xenoform.director import public_presets

        return {"presets": public_presets()}

    @app.post("/api/v1/preset")
    def set_preset(body: dict) -> dict:
        from xenoform.director import public_presets

        preset_id = str(body.get("id") or "")
        found = next((item for item in public_presets() if item["id"] == preset_id), None)
        if found is None:
            raise HTTPException(404, "No such look.")
        stored = store(
            "agent",
            preset=found["id"],
            quality=found.get("quality") or "live",
            sliders=dict(found.get("sliders") or {}),
        )
        return public_session(stored)

    @app.post("/api/v1/analyze")
    def analyze(body: dict) -> dict:
        import librosa

        from xenoform.analyze import analyze_audio
        from xenoform.config import load_config

        path = Path(str(body.get("path") or "")).expanduser()
        if path.suffix.lower() not in _AUDIO_SUFFIXES or not path.is_file():
            raise HTTPException(400, "Point this at a wav, mp3, flac, or ogg on this machine.")
        cfg = load_config(None)
        try:
            audio, sr = librosa.load(path, sr=None, mono=True)
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

            raise HTTPException(400, audio_read_error(exc)) from exc
        from xenoform.ui import _AUDIO, _FEATURES, coerce_storage_id

        audio_id = coerce_storage_id(path.stem[:24])
        with lock:
            _AUDIO[audio_id] = path
            _FEATURES[audio_id] = features
        stored = store("agent", audio_id=audio_id, title=path.stem, video="")
        return {
            "audio_id": audio_id,
            "title": path.stem,
            "duration": round(float(features.get("duration") or 0), 3),
            "tempo": round(float(features.get("tempo") or 0), 2),
            "sections": len(features.get("sections") or []),
            "revision": stored["revision"],
        }

    @app.post("/api/v1/storyboard")
    def storyboard(body: dict) -> dict:
        from xenoform.director import register_by_id
        from xenoform.storyboard import blocks_from_scenes, plan_with_hook

        data = current()
        register_id = str(body.get("register") or data.get("register") or "pynchon")
        voice = register_by_id(register_id)
        brief = str(body.get("brief") or data.get("brief") or "")
        features = features_for(str(data.get("audio_id") or "demo"))
        scenes, planner = plan_with_hook(
            features,
            voice,
            brief,
            motif=str(data.get("motif") or ""),
            callback=str(body.get("callback") or data.get("callback") or ""),
        )
        stored = store(
            "agent",
            brief=brief,
            register=voice["id"],
            scenes=scenes,
            blocks=blocks_from_scenes(scenes),
            callback=str(body.get("callback") or data.get("callback") or ""),
        )
        return {"planner": planner, "scenes": scenes, "blocks": stored["blocks"], "revision": stored["revision"]}

    @app.post("/api/v1/scenes/{index}")
    def edit_scene(index: int, body: dict) -> dict:
        from xenoform.storyboard import blocks_from_scenes

        data = current()
        scenes = list(data.get("scenes") or [])
        if index < 0 or index >= len(scenes):
            raise HTTPException(404, "That scene is not on the board.")
        allowed = {
            "action",
            "form",
            "shot",
            "move",
            "edit",
            "mood",
            "bars",
            "fade_frames",
            "verb",
            "protagonist",
            "goal",
            "payoff",
        }
        scene = dict(scenes[index])
        for key, value in body.items():
            if key in allowed and value not in ("", None):
                scene[key] = value
        if str(scene.get("edit") or "") in {"hard cut", "snap"}:
            scene["signature"] = False
            scene["conditioning"] = "first-frame"
        scene["edited"] = True
        scenes[index] = scene
        stored = store("agent", scenes=scenes, blocks=blocks_from_scenes(scenes))
        return {"scene": scene, "revision": stored["revision"]}

    @app.post("/api/v1/params")
    def params(body: dict) -> dict:
        data = current()
        quality = str(body.get("quality") or data.get("quality") or "live")
        if quality not in _QUALITIES:
            raise HTTPException(400, "Tier is live, turbo, draft, or final.")
        sliders = dict(data.get("sliders") or {})
        incoming = body.get("sliders") or {}
        if isinstance(incoming, dict):
            for key, value in incoming.items():
                try:
                    sliders[key] = max(0.0, min(1.0, float(value)))
                except (TypeError, ValueError):
                    continue
        stored = store(
            "agent",
            quality=quality,
            palette=str(body.get("palette") or data.get("palette") or "violet"),
            flash=str(body.get("flash") or data.get("flash") or "normal"),
            sliders=sliders,
            preset=str(body.get("preset") if body.get("preset") is not None else data.get("preset") or ""),
        )
        return public_session(stored)

    @app.post("/api/v1/notes")
    def apply_note(body: dict) -> dict:
        from xenoform.lessons import load_saved
        from xenoform.notes import apply_to_notebook, interpret_note, render_manifest, version_summary
        from xenoform.storyboard import blocks_from_scenes

        data = current()
        text = str(body.get("text") or body.get("note") or "").strip()
        if not text:
            raise HTTPException(400, "Write the note first.")
        scenes = list(body.get("scenes") or data.get("scenes") or [])
        from xenoform.ui import storage_id, work_dir

        audio_id = storage_id(str(data.get("audio_id") or "demo"))
        features = features_for(audio_id)
        saved = load_saved(lessons_file())
        try:
            interpreted = interpret_note(text, scenes, features, try_local=False, lessons=saved)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        patch = interpreted.get("patch")
        if not isinstance(patch, dict):
            raise HTTPException(400, interpreted.get("detail") or "That note did not become a patch.")
        video = str(data.get("video") or video_for(audio_id))
        book = notebook(audio_id, scenes, video)
        out = work_dir() / "notes" / audio_id / "segments"
        try:
            applied = apply_to_notebook(
                book,
                text,
                scenes,
                patch,
                features,
                render_manifest,
                out,
                quality=str(data.get("quality") or "live"),
                video=video,
            )
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        save_notebook(audio_id, book)
        scenes_after = applied["scenes"]
        stored = store("agent", scenes=scenes_after, blocks=blocks_from_scenes(scenes_after))
        return {
            "diff": interpreted.get("diff") or interpreted.get("text") or "",
            "rationale": interpreted.get("rationale") or "",
            "scenes": scenes_after,
            "version": version_summary(applied["version"]),
            "revision": stored["revision"],
            "detail": applied.get("cache_line") or "Note applied.",
        }

    def _review_inputs(body: dict) -> tuple[dict, list, dict]:
        data = current()
        if body.get("scenes"):
            data = {**data, "scenes": body.get("scenes")}
        for key in ("flash", "sliders", "quality", "palette", "preset", "register", "motif", "video", "audio_id"):
            if body.get(key) not in (None, ""):
                data[key] = body.get(key)
        features = features_for(str(data.get("audio_id") or "demo"))
        return data, list(data.get("scenes") or []), features

    def _ledger_dir() -> Path:
        folder = repo_root() / "work" / "ui"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _shot_frames(video: Path, scenes: list) -> dict:
        from xenoform.video import probe_video, read_frame_range

        info = probe_video(video)
        rate = float(info.get("fps") or 12) or 12.0
        total = int(info.get("frames") or 0)
        frames: dict = {}
        if total <= 0:
            return frames
        for scene in scenes:
            index = int(scene.get("index") or 0)
            frame_index = max(0, min(total - 1, int(round(float(scene.get("start") or 0) * rate))))
            try:
                frames[index] = read_frame_range(str(video), frame_index, 1)[0]
            except Exception:
                continue
        return frames

    def _run_audit(body: dict) -> dict:
        from xenoform.critic import delivery_spec, fresh_eyes
        from xenoform.director import register_by_id
        from xenoform.ledger import append_round, board_metrics, load_ledger, open_ids
        from xenoform.review import audit, sample_video

        data, scenes, features = _review_inputs(body)
        voice = register_by_id(str(data.get("register") or "pynchon"))
        frames = None
        video_duration = None
        path = resolve_video(str(data.get("video") or ""))
        jobs_video = path if path is not None and path.exists() and "jobs" in path.parts else None
        if jobs_video is not None:
            frames = sample_video(str(jobs_video))
            video_duration = _media_duration(jobs_video)
        report = audit(
            scenes,
            features,
            frames=frames,
            fps=float(features.get("fps") or 24),
            flash=str(data.get("flash") or "normal"),
            sliders=dict(data.get("sliders") or {}),
            register_forms=list(voice.get("forms") or []),
            motif=str(data.get("motif") or ""),
            audio_duration=float(features.get("duration") or 0) or None,
            video_duration=video_duration,
            ask_model=bool(body.get("ask_model")),
        )
        elements = list(body.get("continuity") or data.get("continuity") or [])
        if jobs_video is not None and elements and any(scene.get("element_ids") for scene in scenes):
            from xenoform.continuity import critique, ensure_stills, rerender_ids

            folder = _ledger_dir() / "continuity"
            ready = ensure_stills(elements, folder)
            shot_frames = _shot_frames(jobs_video, scenes)
            report["findings"].extend(critique(scenes, shot_frames, ready))
            report["rerender"] = rerender_ids(report["findings"])
        quality = str(data.get("quality") or "live")
        audio_id = str(data.get("audio_id") or "demo")
        audio = repo_root() / "examples" / "demo.wav" if audio_id in {"", "demo"} else None
        prior = open_ids(load_ledger(_ledger_dir()))
        spec = delivery_spec(quality, duration=float(features.get("duration") or 0) or None)
        eyes = fresh_eyes(jobs_video, audio, spec, beats=list(features.get("beats") or []), prior_ids=prior)
        current = {item["id"] for item in eyes.get("problems") or []} | {row["id"] for row in report["findings"]}
        rechecked = [{"id": item, "status": "open" if item in current else "cleared"} for item in prior]
        ranked = list(eyes.get("problems") or [])
        for row in report["findings"]:
            if row.get("kind") == "note":
                continue
            ranked.append({"id": row["id"], "t": None, "plain": row.get("plain") or "", "rank": row.get("rank") or 50, "op": row.get("op") or {}})
        ranked.sort(key=lambda row: (int(row.get("rank") or 50), str(row.get("id") or "")))
        before = board_metrics(scenes)
        before["verdict"] = eyes.get("verdict")
        before["failed"] = ",".join(item["id"] for item in eyes.get("bar") or [] if item.get("measured") and not item.get("pass"))
        append_round(_ledger_dir(), verdict=str(eyes.get("verdict") or ""), before=before, problems=ranked, rechecked=rechecked)
        report["quality"] = quality
        report["verdict"] = eyes.get("verdict")
        report["ranked"] = ranked
        report["bar"] = eyes.get("bar") or []
        report["sound_off"] = eyes.get("sound_off") or {}
        report["retelling"] = eyes.get("retelling") or ""
        report["rechecked"] = rechecked
        report["ledger"] = load_ledger(_ledger_dir())
        return report

    @app.post("/api/v1/review")
    def review(body: dict) -> dict:
        return _run_audit(body or {})

    @app.post("/api/v1/review/apply")
    def review_apply(body: dict) -> dict:
        from xenoform.notes import make_version, version_summary
        from xenoform.review import apply_findings
        from xenoform.storyboard import blocks_from_scenes

        from xenoform.critic import next_fix
        from xenoform.ledger import board_metrics, load_ledger, record_after

        data, scenes, _features = _review_inputs(body or {})
        findings = list(body.get("findings") or [])
        if body.get("use_session") or not findings:
            findings = _run_audit(body or {}).get("findings") or []
        if body.get("biggest"):
            picked = next_fix(findings)
            findings = [picked] if picked else []
        before_scenes = copy.deepcopy(scenes)
        before_flash = str(data.get("flash") or "normal")
        before_sliders = dict(data.get("sliders") or {})
        result = apply_findings(
            scenes,
            findings,
            sliders=before_sliders,
            flash=before_flash,
            preset=str(data.get("preset") or ""),
        )
        audio_id = str(data.get("audio_id") or "demo")
        video = str(data.get("video") or video_for(audio_id))
        book = notebook(audio_id, before_scenes, video)
        parent = book.get("current")
        snap = make_version(
            note="Before review",
            patch={"review": "before", "flash": before_flash, "sliders": before_sliders},
            scenes=before_scenes,
            renders={},
            parent=parent,
            seed=int(book.get("seed") or 2727),
            quality=str(data.get("quality") or "live"),
            video=video,
        )
        applied_version = make_version(
            note="Review & fix",
            patch={
                "review": "apply",
                "flash": result["flash"],
                "sliders": result["sliders"],
                "rerender": [row["scene"] for row in findings if row.get("kind") == "rerender"],
            },
            scenes=result["scenes"],
            renders={},
            parent=snap["id"],
            seed=int(book.get("seed") or 2727),
            quality=str(data.get("quality") or "live"),
            video=video,
        )
        book.setdefault("versions", []).extend([snap, applied_version])
        book["current"] = applied_version["id"]
        save_notebook(audio_id, book)
        from xenoform.continuity import rerender_ids

        rerender = rerender_ids(findings)
        blocks = blocks_from_scenes(result["scenes"])
        stored = store(
            "agent",
            scenes=result["scenes"],
            blocks=blocks,
            flash=result["flash"],
            sliders=result["sliders"],
            preset=result["preset"],
        )
        record_after(_ledger_dir(), {**board_metrics(result["scenes"]), "verdict": "applied"})
        job = None
        quality = str(data.get("quality") or "live")
        if rerender and quality != "live":
            payload = dict(stored)
            payload["live"] = False
            payload["only_scenes"] = rerender
            job = start_job(payload)
        return {
            "summary": _applied_summary(findings, rerender, quality, job),
            "findings": findings,
            "scenes": result["scenes"],
            "blocks": blocks,
            "flash": result["flash"],
            "sliders": result["sliders"],
            "preset": result["preset"],
            "rerender": rerender,
            "queued": bool(job),
            "job": job,
            "undo": snap["id"],
            "version": version_summary(applied_version),
            "versions": [version_summary(item) for item in book.get("versions") or []],
            "revision": stored["revision"],
            "ledger": load_ledger(_ledger_dir()),
        }

    @app.get("/api/v1/ledger")
    def ledger_view() -> dict:
        from xenoform.ledger import ledger_paths, load_ledger

        folder = _ledger_dir()
        _json_path, markdown_path = ledger_paths(folder)
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
        return {"rounds": load_ledger(folder), "markdown": markdown}

    @app.get("/api/v1/timing")
    def timing_view() -> dict:
        from xenoform.timing import timing_document, write_timing

        data = current()
        features = features_for(str(data.get("audio_id") or "demo"))
        document = timing_document(features, list(data.get("scenes") or []), seed=int(data.get("seed") or 2727))
        write_timing(_ledger_dir() / "timing.json", document)
        return document

    @app.post("/api/v1/render")
    def render(body: dict) -> dict:
        data = current()
        tier = str(body.get("tier") or body.get("quality") or data.get("quality") or "live")
        if tier not in _QUALITIES:
            raise HTTPException(400, "Tier is live, turbo, draft, or final.")
        store("agent", quality=tier)
        if tier == "live":
            return {
                "tier": "live",
                "job_id": None,
                "detail": "Live plays in the desk. No model was started.",
            }
        payload = current()
        payload["quality"] = tier
        payload["live"] = False
        only = [str(item) for item in (body.get("scenes") or []) if item]
        if only:
            payload["only_scenes"] = only
        if not payload.get("scenes"):
            raise HTTPException(400, "The board is empty. Make a storyboard first.")
        job = start_job(payload)
        store("agent", job_id=job.get("id") or "")
        return {"tier": tier, "job_id": job.get("id"), "scenes": only, "detail": "Queued."}

    @app.get("/api/v1/render/{job_id}")
    def render_status(job_id: str) -> dict:
        snap = job_snapshot(job_id)
        if snap is None:
            raise HTTPException(404, "No such render.")
        return snap

    @app.get("/api/v1/frames")
    def frames_meta() -> dict:
        return {"url": "/api/v1/frames.png", "detail": "Contact sheet of the current board."}

    @app.get("/api/v1/frames.png")
    def frames_png() -> Response:
        from xenoform.review import contact_sheet

        data = current()
        blob = contact_sheet(list(data.get("scenes") or []), str(data.get("palette") or "violet"))
        return Response(content=blob, media_type="image/png")

    @app.get("/api/v1/versions")
    def versions() -> dict:
        from xenoform.notes import version_summary

        data = current()
        audio_id = str(data.get("audio_id") or "demo")
        book = notebook(audio_id, list(data.get("scenes") or []), str(data.get("video") or video_for(audio_id)))
        return {
            "current": book.get("current"),
            "versions": [version_summary(item) for item in book.get("versions") or []],
        }

    @app.post("/api/v1/revert")
    def revert(body: dict) -> dict:
        from xenoform.notes import revert_notebook, version_summary
        from xenoform.storyboard import blocks_from_scenes

        data = current()
        audio_id = str(data.get("audio_id") or "demo")
        book = notebook(audio_id, list(data.get("scenes") or []), str(data.get("video") or video_for(audio_id)))
        version_id = str(body.get("version_id") or "")
        try:
            restored = revert_notebook(book, version_id, video=str(data.get("video") or ""))
        except KeyError as exc:
            raise HTTPException(404, "No such version.") from exc
        save_notebook(audio_id, book)
        scenes = restored["scenes"]
        target = next((item for item in book.get("versions") or [] if item.get("id") == version_id), {})
        patch = target.get("patch") if isinstance(target.get("patch"), dict) else {}
        fields: dict[str, Any] = {"scenes": scenes, "blocks": blocks_from_scenes(scenes)}
        if isinstance(patch, dict) and patch.get("flash"):
            fields["flash"] = patch["flash"]
        if isinstance(patch, dict) and isinstance(patch.get("sliders"), dict):
            fields["sliders"] = patch["sliders"]
        stored = store("agent", **fields)
        return {
            "version": version_summary(restored["version"]),
            "scenes": scenes,
            "blocks": fields["blocks"],
            "flash": stored.get("flash"),
            "sliders": stored.get("sliders"),
            "revision": stored["revision"],
        }

    @app.post("/api/v1/export")
    def export(body: dict | None = None) -> dict:
        from xenoform.director import encode_recipe

        data = current()
        body = body or {}
        state = {
            "quality": data.get("quality") or "live",
            "preset": data.get("preset") or "",
            "sliders": data.get("sliders") or {},
            "locks": body.get("locks") or {},
            "blocks": data.get("blocks") or [],
            "customs": body.get("customs") or [],
            "register": data.get("register") or "",
            "palette": data.get("palette") or "neutral",
            "flash": data.get("flash") or "normal",
            "cards": data.get("cards") or [],
            "scenes": data.get("scenes") or [],
            "brief": data.get("brief") or "",
            "motif": data.get("motif") or "",
            "callback": data.get("callback") or "",
        }
        try:
            recipe = encode_recipe(state)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc
        store("agent", recipe=recipe)
        return {
            "recipe": recipe,
            "video": data.get("video") or "",
            "quality": state["quality"],
            "register": state["register"],
        }

    @app.get("/api/v1/lessons")
    def lessons() -> dict:
        from xenoform.lessons import catalog, load_saved

        return {"builtin": catalog(), "saved": load_saved(lessons_file())}

    @app.get("/api/v1/transitions")
    def transitions() -> dict:
        from xenoform.director import public_transitions

        return {"transitions": public_transitions()}

    @app.get("/api/v1/mcp/status")
    def mcp_status(request: Request) -> dict:
        running = _port_open(_MCP_PORT)
        return {
            "running": running,
            "url": f"http://127.0.0.1:{_MCP_PORT}/mcp",
            "desk": str(request.base_url).rstrip("/"),
            "detail": "The agent port is answering on this machine."
            if running
            else "The desk API is up. The agent port is off until you start it.",
        }

    @app.post("/api/v1/mcp/start")
    def mcp_start(request: Request) -> dict:
        if _port_open(_MCP_PORT):
            return {
                "running": True,
                "url": f"http://127.0.0.1:{_MCP_PORT}/mcp",
                "detail": "The agent port is already answering on this machine.",
            }
        desk = str(request.base_url).rstrip("/")
        log_path = repo_root() / "work" / "ui" / "mcp.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "ab")
        proc = subprocess.Popen(
            [sys.executable, "-m", "xenoform", "mcp", "--http", "--host", "127.0.0.1", "--port", str(_MCP_PORT), "--desk", desk],
            cwd=str(repo_root()),
            stdout=log_file,
            stderr=log_file,
        )
        _MCP_PROC["proc"] = proc
        deadline = time.time() + 3
        while time.time() < deadline:
            if _port_open(_MCP_PORT):
                return {
                    "running": True,
                    "pid": proc.pid,
                    "url": f"http://127.0.0.1:{_MCP_PORT}/mcp",
                    "detail": "The agent port is answering on this machine.",
                }
            if proc.poll() is not None:
                return {
                    "running": False,
                    "url": f"http://127.0.0.1:{_MCP_PORT}/mcp",
                    "detail": "The agent port did not start. Install the agent extra with pip install 'xenoform[agent]'.",
                }
            time.sleep(0.15)
        answering = _port_open(_MCP_PORT)
        return {
            "running": answering,
            "pid": proc.pid,
            "url": f"http://127.0.0.1:{_MCP_PORT}/mcp",
            "detail": "The agent port is answering on this machine."
            if answering
            else "The agent port is still starting on this machine. It only listens on localhost.",
        }


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _media_duration(path: Path) -> float | None:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None


def _applied_summary(findings: list[dict], rerender: list[str], quality: str, job: dict | None) -> str:
    n = len([row for row in findings if (row.get("op") or {}).get("op")])
    if not n and not rerender:
        return "Nothing to change. The board already holds."
    sentence = f"Applied {n} fix{'es' if n != 1 else ''}."
    if quality == "live":
        sentence += " Live is already showing the board."
    elif rerender and job:
        listed = ", ".join(rerender)
        sentence += f" Queued a {quality} picture for {listed}."
    elif rerender:
        sentence += " Those scenes still need a picture."
    return sentence
