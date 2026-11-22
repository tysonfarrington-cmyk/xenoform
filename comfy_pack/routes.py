"""Two read-only routes on ComfyUI's own server for the Morph Timeline: a still's thumbnail and the song to play.

``GET /xenoform_nodes/still?file=vibe/name.jpg&w=176`` serves a still from the catalogue (no other file), scaled down.
``GET /xenoform_nodes/song?path=...`` serves a song the storyboard names, only from the folders songs are taken from
(the pack's and the repository's examples, ComfyUI's input folder, its temp folder). ``GET /xenoform_nodes/info`` says
which library and analysis engine this install has. Registered only when ComfyUI's server is running.
"""

from __future__ import annotations

import io
from pathlib import Path

from . import song as S
from . import stills

ROUTE = "/xenoform_nodes"


def song_roots() -> list[Path]:
    roots = [stills.PACK / "examples", stills.PACK.parent / "examples"]
    try:
        import folder_paths

        roots += [Path(folder_paths.get_input_directory()), Path(folder_paths.get_temp_directory()) / "xenoform"]
    except Exception:
        pass
    return [r.resolve() for r in roots if r.exists()]


def allowed_song(raw: str) -> Path | None:
    """The song at ``raw`` when it is an audio file under one of the song roots, else None. The path is checked as
    text first (no network share, an audio suffix, under a root once made absolute), so a path that is not ours is
    never opened, resolved or asked of another machine."""
    import os

    text = str(raw or "")
    if not text or text.replace("/", "\\").startswith("\\\\") or Path(text).suffix.lower() not in S.AUDIO_EXTS:
        return None
    roots = song_roots()
    try:
        lexical = Path(os.path.abspath(text))
        if not any(lexical.is_relative_to(root) for root in roots):
            return None
        path = lexical.resolve()
    except (OSError, ValueError):
        return None
    if not path.is_file():
        return None
    return path if any(path.is_relative_to(root) for root in roots) else None


def thumb_width(raw) -> int:
    """The ``w`` of a thumbnail request as a number; anything else is the default, not a 500."""
    try:
        return int(raw or 176)
    except (TypeError, ValueError):
        return 176


def thumbnail(file: str, width: int = 176) -> bytes | None:
    row = stills.find(file)
    if row is None:
        return None
    from PIL import Image

    width = max(32, min(int(width or 176), 640))
    with Image.open(row["path"]) as im:
        im = im.convert("RGB")
        im.thumbnail((width, width), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def info() -> dict:
    roots = [str(r) for r in stills.roots()]
    return {"library": "repository" if stills.REPO_OBJECTS.is_dir() and str(stills.REPO_OBJECTS) in roots else "bundled",
            "vibes_with_stills": len(stills.catalogue()), "librosa": S.librosa_available(), "ffmpeg": bool(S.ffmpeg_exe())}


def register() -> bool:
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:
        return False
    instance = getattr(PromptServer, "instance", None)
    routes = getattr(instance, "routes", None)
    if routes is None:
        return False

    @routes.get(f"{ROUTE}/still")
    async def _still(request):
        data = thumbnail(request.query.get("file", ""), thumb_width(request.query.get("w", "")))
        if data is None:
            return web.Response(status=404, text="No such still in the Xenoform catalogue.")
        return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @routes.get(f"{ROUTE}/song")
    async def _song(request):
        path = allowed_song(request.query.get("path", ""))
        if path is None:
            return web.Response(status=404, text="That song is not one the Xenoform nodes opened.")
        return web.FileResponse(path)

    @routes.get(f"{ROUTE}/info")
    async def _info(request):
        return web.json_response(info())

    return True
