"""Local agent API and the MCP tool list."""

import pytest
from fastapi.testclient import TestClient

from xenoform.ui import create_app


def _client():
    return TestClient(create_app())


def test_health_registers_and_storyboard_roundtrip():
    client = _client()
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["auth"] == "none"
    registers = client.get("/api/v1/registers")
    assert [row["id"] for row in registers.json()["registers"]] == [
        "pynchon",
        "lecarre",
        "tolkien",
        "rome",
        "custom",
    ]
    board = client.post("/api/v1/storyboard", json={"brief": "a rocket falls back, cold and paranoid"})
    assert board.status_code == 200
    scenes = board.json()["scenes"]
    assert scenes
    edited = client.post(f"/api/v1/scenes/0", json={"action": "the hull splits on the beat"})
    assert edited.status_code == 200
    assert edited.json()["scene"]["action"] == "the hull splits on the beat"
    transitions = client.get("/api/v1/transitions")
    assert any(row["id"] == "dive-splash" for row in transitions.json()["transitions"])
    lessons = client.get("/api/v1/lessons")
    assert len(lessons.json()["builtin"]) >= 10
    exported = client.post("/api/v1/export", json={})
    assert exported.status_code == 200
    assert exported.json()["recipe"].startswith("XF-")
    sheet = client.get("/api/v1/frames.png")
    assert sheet.status_code == 200
    assert sheet.content[:8] == b"\x89PNG\r\n\x1a\n"
    live = client.post("/api/v1/render", json={"tier": "live"})
    assert live.status_code == 200
    assert live.json()["job_id"] is None


def test_review_apply_versions_and_revert():
    client = _client()
    scenes = [
        {
            "index": 0,
            "start": 0.0,
            "end": 4.0,
            "edit": "dissolve",
            "move": "push in",
            "form": "sphere",
            "action": "the hull turns in the light",
            "beat": "setup",
            "fade_frames": 20,
        }
    ]
    audit = client.post("/api/v1/review", json={"scenes": scenes, "flash": "hard", "quality": "live", "audio_id": "demo"})
    assert audit.status_code == 200
    body = audit.json()
    assert any(row["check"] == "ghosting-dissolve" for row in body["findings"])
    applied = client.post(
        "/api/v1/review/apply",
        json={"scenes": scenes, "flash": "hard", "quality": "live", "audio_id": "demo", "findings": body["findings"]},
    )
    assert applied.status_code == 200
    done = applied.json()
    assert done["flash"] == "soft"
    assert done["scenes"][0]["fade_frames"] == 8
    assert done["undo"]
    assert done["queued"] is False
    versions = client.get("/api/v1/versions")
    labels = [row["label"] for row in versions.json()["versions"]]
    assert "Before review" in labels
    assert "Review & fix" in labels
    reverted = client.post("/api/v1/revert", json={"version_id": done["undo"]})
    assert reverted.status_code == 200
    assert reverted.json()["flash"] == "hard"
    assert reverted.json()["scenes"][0]["fade_frames"] == 20


def test_render_queues_only_named_scenes(monkeypatch):
    monkeypatch.setattr("xenoform.ui._run_job", lambda *args, **kwargs: None)
    client = _client()
    client.post("/api/v1/storyboard", json={"brief": "a rocket falls back"})
    response = client.post("/api/v1/render", json={"tier": "turbo", "scenes": ["s1", "s3"]})
    assert response.status_code == 200
    body = response.json()
    assert body["scenes"] == ["s1", "s3"]
    status = client.get(f"/api/v1/render/{body['job_id']}")
    assert status.status_code == 200
    assert status.json()["only_scenes"] == ["s1", "s3"]
    assert status.json()["quality"] == "turbo"


def test_mcp_status_route_is_localhost():
    client = _client()
    status = client.get("/api/v1/mcp/status")
    assert status.status_code == 200
    body = status.json()
    assert body["url"] == "http://127.0.0.1:47319/mcp"
    assert "localhost" in body["detail"] or "agent port" in body["detail"]


def test_mcp_lists_the_director_tools():
    pytest.importorskip("mcp")
    from xenoform.mcp_server import build_server, serve

    server = build_server("http://127.0.0.1:9")
    tools = getattr(server, "_tool_manager", None)
    names = set()
    if tools is not None and hasattr(tools, "list_tools"):
        names = {tool.name for tool in tools.list_tools()}
    else:
        registered = getattr(server, "_tools", None) or getattr(server, "tools", None) or {}
        if isinstance(registered, dict):
            names = set(registered)
    assert {
        "list_registers",
        "get_register",
        "set_register",
        "list_presets",
        "set_preset",
        "analyse_track",
        "create_storyboard",
        "edit_scene_card",
        "set_params",
        "apply_note",
        "run_review",
        "render",
        "get_render_status",
        "get_frames",
        "list_versions",
        "revert",
        "export",
    } <= names
    with pytest.raises(RuntimeError, match="127.0.0.1"):
        serve("streamable-http", host="0.0.0.0", port=1)


def test_mcp_cli_refuses_a_public_host():
    from xenoform.cli import main

    with pytest.raises(SystemExit, match="127.0.0.1"):
        main(["mcp", "--http", "--host", "0.0.0.0", "--port", "1"])
