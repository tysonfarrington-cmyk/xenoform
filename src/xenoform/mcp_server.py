"""MCP server for the desk. Stdio by default, streamable HTTP on localhost only.

The tools call the desk's REST API, which is the same API the browser uses.
Nothing here holds an auth secret. The process does not bind a public address.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def desk_url(explicit: str | None = None) -> str:
    raw = (explicit or os.environ.get("XENO_DESK") or "http://127.0.0.1:47317").strip()
    return raw.rstrip("/")


def _request(base: str, method: str, path: str, body: dict | None = None, timeout: float = 60.0) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            parsed = {"detail": detail[:400] or f"The desk answered {exc.code}."}
        parsed.setdefault("detail", f"The desk answered {exc.code}.")
        return parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "detail": "Open the Xenoform desk on this machine. The agent talks to it over localhost and does not start a model on its own.",
            "error": str(exc),
        }
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"detail": raw[:400]}


def build_server(desk: str | None = None):
    """Register the director tools. Import of the MCP SDK happens here."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:
        raise RuntimeError(
            "The agent extra is not installed. Run: pip install 'xenoform[agent]'. The desk itself is unchanged."
        ) from exc

    from xenoform.mcp_tools import INSTRUCTIONS, App, Desk, register

    base = desk_url(desk)
    server = MCPServer(
        "Xenoform",
        instructions=INSTRUCTIONS,
    )

    def call(method: str, path: str, body: dict | None = None, timeout: float = 120.0) -> dict:
        return _request(base, method, path, body, timeout)

    @server.tool()
    def list_registers() -> dict:
        """List the story registers: Pynchon, le Carré, Tolkien, Rome, Custom."""
        return call("GET", "/api/v1/registers")

    @server.tool()
    def get_register(register_id: str) -> dict:
        """Fetch one register, including its forms, palette, and original on-screen lines."""
        return call("GET", f"/api/v1/registers/{register_id}")

    @server.tool()
    def set_register(register_id: str) -> dict:
        """Switch the desk to a register and rebuild the storyboard in that voice."""
        return call("POST", "/api/v1/register", {"id": register_id})

    @server.tool()
    def list_presets() -> dict:
        """List the named looks. Shimmer is not among them."""
        return call("GET", "/api/v1/presets")

    @server.tool()
    def set_preset(preset_id: str) -> dict:
        """Apply a named look: sliders, quality, and palette."""
        return call("POST", "/api/v1/preset", {"id": preset_id})

    @server.tool()
    def analyse_track(path: str) -> dict:
        """Analyse a local audio file and store it as the current song. Accepts wav, mp3, flac, ogg."""
        return call("POST", "/api/v1/analyze", {"path": path}, timeout=180.0)

    @server.tool()
    def create_storyboard(brief: str, register: str = "") -> dict:
        """Turn a one-line brief into scene cards for the current song."""
        return call("POST", "/api/v1/storyboard", {"brief": brief, "register": register})

    @server.tool()
    def edit_scene_card(
        index: int,
        action: str = "",
        form: str = "",
        shot: str = "",
        move: str = "",
        edit: str = "",
        mood: str = "",
        bars: int = 0,
    ) -> dict:
        """Edit one scene card. Empty fields stay as they are. Index is zero-based."""
        fields: dict[str, Any] = {}
        for key, value in (
            ("action", action),
            ("form", form),
            ("shot", shot),
            ("move", move),
            ("edit", edit),
            ("mood", mood),
        ):
            if str(value).strip():
                fields[key] = value
        if bars:
            fields["bars"] = int(bars)
        return call("POST", f"/api/v1/scenes/{int(index)}", fields)

    @server.tool()
    def set_params(
        quality: str = "",
        palette: str = "",
        flash: str = "",
        liquidity: float = -1,
        chaos: float = -1,
        material: float = -1,
        camera: float = -1,
    ) -> dict:
        """Set the tier (live, turbo, draft, final), palette, flash, and any fader you pass. Omit a fader with -1."""
        sliders = {}
        for key, value in (("liquidity", liquidity), ("chaos", chaos), ("material", material), ("camera", camera)):
            if value >= 0:
                sliders[key] = value
        return call(
            "POST",
            "/api/v1/params",
            {"quality": quality, "palette": palette, "flash": flash, "sliders": sliders},
        )

    @server.tool()
    def apply_note(text: str) -> dict:
        """Apply a plain-English director's note. The patch is stored as a version you can revert."""
        return call("POST", "/api/v1/notes", {"text": text})

    @server.tool()
    def run_review(apply: bool = False) -> dict:
        """Audit the storyboard and the current picture. Set apply true to write every fix and queue only the scenes that need a new picture."""
        if apply:
            return call("POST", "/api/v1/review/apply", {"use_session": True})
        return call("POST", "/api/v1/review", {"use_session": True})

    @server.tool()
    def render(tier: str = "live", scenes: list[str] | None = None) -> dict:
        """Render a tier. Live plays in the browser and does not start a model. Other tiers queue a job. scenes limits the queue to those ids, such as s1."""
        return call("POST", "/api/v1/render", {"tier": tier, "scenes": list(scenes or [])}, timeout=30.0)

    @server.tool()
    def get_render_status(job_id: str) -> dict:
        """Read a render job: stage, progress, and the video URL when a frame is ready."""
        return call("GET", f"/api/v1/render/{job_id}")

    @server.tool()
    def get_frames() -> dict:
        """Contact sheet for the current board. The url is a PNG on the local desk."""
        return call("GET", "/api/v1/frames")

    @server.tool()
    def list_versions() -> dict:
        """List storyboard versions, newest last. Revert with the id."""
        return call("GET", "/api/v1/versions")

    @server.tool()
    def revert(version_id: str) -> dict:
        """Restore a stored version of the storyboard."""
        return call("POST", "/api/v1/revert", {"version_id": version_id})

    @server.tool()
    def export() -> dict:
        """Export the recipe code and the current video URL."""
        return call("POST", "/api/v1/export", {})

    @server.resource("xenoform://storyboard", mime_type="application/json", description="The current storyboard.")
    def storyboard_resource() -> str:
        return json.dumps(call("GET", "/api/v1/session"))

    @server.resource("xenoform://lessons", mime_type="application/json", description="Render lessons the review watches.")
    def lessons_resource() -> str:
        return json.dumps(call("GET", "/api/v1/lessons"))

    @server.resource("xenoform://transitions", mime_type="application/json", description="Transition catalogue.")
    def transitions_resource() -> str:
        return json.dumps(call("GET", "/api/v1/transitions"))

    register(server, App(Desk(base)))
    return server


def serve(transport: str = "stdio", host: str = "127.0.0.1", port: int = 47319, desk: str | None = None) -> None:
    """Run MCP. HTTP binds to localhost only."""
    if transport == "streamable-http" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The agent port stays on this machine. Use 127.0.0.1.")
    server = build_server(desk)
    if transport == "streamable-http":
        from mcp.server.transport_security import TransportSecuritySettings

        server.run(
            "streamable-http",
            host="127.0.0.1" if host == "localhost" else host,
            port=int(port),
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            transport_security=TransportSecuritySettings(
                allowed_hosts=[f"127.0.0.1:{int(port)}", f"localhost:{int(port)}"],
                allowed_origins=[f"http://127.0.0.1:{int(port)}", f"http://localhost:{int(port)}"],
            ),
        )
        return
    server.run("stdio")
