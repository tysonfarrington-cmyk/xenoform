"""The MCP server through the real client SDK: in-memory, stdio and streamable HTTP, against a fake desk."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("mcp")
from mcp.client import Client  # noqa: E402
from mcp.client.stdio import StdioServerParameters  # noqa: E402

from xenoform.mcp_server import build_server  # noqa: E402

EXPECTED = {"get_status", "list_vibes", "list_shapes", "list_transitions", "get_autotune_recipe", "get_settings",
            "create_project", "update_settings", "load_audio", "attach_image", "start_render", "get_render_progress",
            "wait_for_render", "cancel_render", "list_videos", "get_output", "list_presets", "render", "encode_recipe", "decode_recipe", "remix_recipe", "get_audio_analysis", "get_cut_timeline", "apply_edit_list", "get_frames", "run_review"}


class _Desk(BaseHTTPRequestHandler):
    jobs: dict = {}

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        p = self.path
        if p == "/api/demo":
            return self._send(200, {"blocks": [{"form": "rocket"}], "scenes": []})
        if p == "/api/v1/health":
            return self._send(200, {"ok": True})
        if p == "/api/v1/transitions":
            return self._send(200, {"transitions": [{"id": "snap"}]})
        if p.startswith("/api/jobs/") and p.endswith("/video"):
            raw = b"fakemp4"
            self.send_response(200)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            return self.wfile.write(raw)
        if p.startswith("/api/jobs/"):
            jid = p.split("/")[3]
            if jid not in self.jobs:
                return self._send(404, {"detail": "No such cut"})
            return self._send(200, self.jobs[jid])
        return self._send(200, {})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/generate":
            jid = f"t{len(self.jobs)}"
            self.jobs[jid] = {"id": jid, "status": "done", "stage": "done", "progress": 1.0, "video": f"/api/jobs/{jid}/video?v=1",
                              "body_vibe": body.get("vibe")}
            return self._send(200, {"id": jid})
        if self.path.endswith("/cancel"):
            return self._send(200, {"status": "cancelled"})
        return self._send(404, {"detail": "nope"})


@pytest.fixture(scope="module")
def desk():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Desk)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def env(tmp_path, desk, monkeypatch):
    monkeypatch.setenv("XENO_MCP_STATE", str(tmp_path / "state.json"))
    e = dict(os.environ, XENO_DESK=desk, XENO_MCP_STATE=str(tmp_path / "state.json"))
    src = str(Path(__file__).resolve().parents[1] / "src")
    e["PYTHONPATH"] = src + os.pathsep + e.get("PYTHONPATH", "")
    return e


def _data(result):
    if result.structured_content:
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


async def _flow(client):
    assert "Connected to Xenoform" in (client.instructions or "")
    names = {t.name for t in (await client.list_tools()).tools}
    assert EXPECTED <= names, EXPECTED - names
    prompts = {p.name for p in (await client.list_prompts()).prompts}
    assert {"get_started", "make_music_video", "review_cut"} <= prompts
    got = await client.get_prompt("get_started", {})
    assert "get_status" in got.messages[0].content.text
    uris = {str(r.uri) for r in (await client.list_resources()).resources}
    assert {"xenoform://guide", "xenoform://examples"} <= uris
    guide = await client.read_resource("xenoform://guide")
    assert "Xenoform" in guide.contents[0].text
    bad = await client.call_tool("update_settings", {"vibe": "pink"})
    assert bad.is_error and "Unknown vibe" in bad.content[0].text
    spend = await client.call_tool("start_render", {"cloud": True})
    assert spend.is_error and "confirm_spend" in spend.content[0].text
    made = await client.call_tool("create_project", {"prompt": "chrome", "vibe": "ocean"})
    assert not made.is_error
    started = await client.call_tool("start_render", {})
    assert not started.is_error, started.content[0].text
    job = _data(started)["job_id"]
    done = await client.call_tool("wait_for_render", {"job_id": job, "timeout_s": 10})
    assert _data(done)["status"] == "done"
    assert _data(done)["output"]["path"].endswith(".mp4")
    return names


def test_in_memory_client(env, desk):
    async def go():
        async with Client(build_server(desk)) as client:
            await _flow(client)
    asyncio.run(go())


def test_stdio_client(env):
    params = StdioServerParameters(command=sys.executable, args=["-m", "xenoform.mcp"], env=env)

    async def go():
        async with Client(params) as client:
            await _flow(client)
        async with Client(params) as client:  # restart: settings survive
            s = await client.call_tool("get_settings", {})
            assert _data(s)["vibe"] == "ocean"
    asyncio.run(go())


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_http_client_localhost_only(env):
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "xenoform.mcp", "--http", "--port", str(port)], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        async def go():
            async with Client(f"http://127.0.0.1:{port}/mcp") as client:
                await _flow(client)
        asyncio.run(go())
    finally:
        proc.terminate()
        proc.wait(10)
    bad = subprocess.run([sys.executable, "-m", "xenoform.mcp", "--http", "--host", "0.0.0.0", "--port", "1"],
                         env=env, capture_output=True, text=True, timeout=60)
    assert bad.returncode != 0 and "127.0.0.1" in bad.stderr
