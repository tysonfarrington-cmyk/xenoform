"""Serve the director desk inside ComfyUI at /xenoform.

The FastAPI app stays the implementation. This module forwards HTTP from
ComfyUI's aiohttp server onto that app, under one origin and one port.
"""

from __future__ import annotations

from typing import Any

_APP = None
_MOUNTED = False


def desk_app():
    global _APP
    if _APP is None:
        from xenoform.ui import create_app

        _APP = create_app()
    return _APP


async def _call_asgi(method: str, path: str, query: bytes, headers: list[tuple[bytes, bytes]], body: bytes) -> dict[str, Any]:
    sent: dict[str, Any] = {"body": b""}
    delivered = False

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.5"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path or "/",
        "raw_path": (path or "/").encode("utf-8"),
        "query_string": query,
        "headers": headers,
        "client": ("127.0.0.1", 0),
        "server": ("127.0.0.1", 80),
    }

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]
            sent["headers"] = message.get("headers") or []
        elif message["type"] == "http.response.body":
            sent["body"] += message.get("body") or b""

    await desk_app()(scope, receive, send)
    sent.setdefault("status", 500)
    sent.setdefault("headers", [])
    return sent


def _forward_headers(request) -> list[tuple[bytes, bytes]]:
    headers = []
    for key, value in request.headers.items():
        headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    headers.append((b"x-xeno-base", b"/xenoform"))
    return headers


async def handle(request):
    from aiohttp import web

    suffix = request.path[len("/xenoform") :] or "/"
    if not suffix.startswith("/"):
        suffix = "/" + suffix
    body = await request.read()
    query = request.query_string.encode("latin-1")
    sent = await _call_asgi(request.method, suffix, query, _forward_headers(request), body)
    response = web.Response(status=int(sent["status"]), body=sent["body"])
    for key, value in sent["headers"]:
        name = key.decode("latin-1")
        if name.lower() in {"content-length", "transfer-encoding", "content-encoding"}:
            continue
        response.headers[name] = value.decode("latin-1")
    return response


def mount(app) -> None:
    """Attach /xenoform to an aiohttp application. Safe to call once."""
    global _MOUNTED
    if _MOUNTED:
        return
    app.router.add_route("*", "/xenoform", handle)
    app.router.add_route("*", "/xenoform/{tail:.*}", handle)
    _MOUNTED = True


def mount_prompt_server() -> None:
    """Attach to a running ComfyUI, if this process is one."""
    try:
        from server import PromptServer
    except Exception:
        return
    server = PromptServer.instance
    app = getattr(server, "app", None)
    if app is None:
        return
    mount(app)
