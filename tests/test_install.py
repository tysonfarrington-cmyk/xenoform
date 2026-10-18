"""Zero-friction install: nodes, /xenoform, tiers, downloads, a tiny dry-run."""

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform.comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from xenoform.errors import PlainError, plain_error
from xenoform.hardware import apply_tier, run_resilient, tier_for_gb
from xenoform.models_setup import download_file, inspect_setup
from xenoform.stems import stem_status
from xenoform.workflow_embed import png_with_workflow, read_workflow_png


def test_node_pack_registers_from_the_repo_root():
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("xenoform_comfy_entry", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "XenoformTryIt" in module.NODE_CLASS_MAPPINGS
    assert module.NODE_DISPLAY_NAME_MAPPINGS["XenoformTryIt"] == "Xenoform Try It"
    assert module.WEB_DIRECTORY == "./web"
    assert set(NODE_CLASS_MAPPINGS) == {"XenoformTryIt", "XenoformSetup"}
    assert "Xenoform Setup Check" in NODE_DISPLAY_NAME_MAPPINGS.values()


def test_xenoform_route_serves_the_desk():
    aiohttp = pytest.importorskip("aiohttp")
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    from xenoform.comfy_server import mount

    async def run():
        app = web.Application()
        mount(app)
        client = TestClient(TestServer(app))
        await client.start_server()
        try:
            page = await client.get("/xenoform")
            text = await page.text()
            assert page.status == 200
            assert "Xenoform" in text
            assert 'window.XENO_BASE="/xenoform"' in text
            demo = await client.get("/xenoform/api/demo")
            body = await demo.json()
            assert demo.status == 200
            assert body["audio_id"] == "demo"
            script = await client.get("/xenoform/static/app.js")
            assert script.status == 200
            assert b"Try the demo" in await script.read()
        finally:
            await client.close()

    asyncio.run(run())
    assert aiohttp.__name__ == "aiohttp"


def test_tiers_drop_on_oom_and_cpu_keeps_the_desk_size():
    cpu = tier_for_gb(None)
    assert cpu["id"] == "cpu"
    assert tier_for_gb(8)["id"] == "8gb"
    assert tier_for_gb(16)["id"] == "12gb"
    assert tier_for_gb(24)["id"] == "24gb"
    cfg = {"fps": 12, "render": {"width": 480, "height": 270, "max_steps": 10, "backend": "cpu"}, "comfy": {}}
    kept = apply_tier(cfg, cpu, quality="draft")
    assert kept["render"]["width"] == 480
    small = apply_tier(cfg, tier_for_gb(8), quality="final")
    assert small["render"]["width"] == 512
    assert small["comfy"]["offload"] is True
    assert small["comfy"]["checkpoint_name"] == "ltx-video-2b-v0.9.5.safetensors"

    calls = []

    def attempt(tier_id):
        calls.append(tier_id)
        if tier_id != "8gb":
            raise MemoryError("CUDA out of memory")
        return "ok"

    value, used, note = run_resilient(attempt, tier_for_gb(24))
    assert value == "ok"
    assert used == "8gb"
    assert calls == ["24gb", "12gb", "8gb"]
    assert "ran out of memory" in note
    assert "Traceback" not in note
    with pytest.raises(PlainError) as caught:
        run_resilient(lambda _tier: (_ for _ in ()).throw(MemoryError("oom")), tier_for_gb(8))
    assert "smallest" in str(caught.value)
    assert "Traceback" not in plain_error(RuntimeError("Traceback (most recent call last)"))


def test_download_resumes_and_rejects_a_bad_checksum(tmp_path):
    payload = b"xenoform-weights-0123456789"
    digest = hashlib.sha256(payload).hexdigest()
    seen = {}

    def opener(url, headers):
        seen["url"] = url
        seen["headers"] = dict(headers)
        start = 0
        if "Range" in headers:
            start = int(headers["Range"].split("=")[1].split("-")[0])
        data = payload[start:]
        chunks = [data]

        def read():
            return chunks.pop(0) if chunks else b""

        return (206 if start else 200), read, len(data)

    dest = tmp_path / "checkpoints" / "ltx.safetensors"
    part = dest.with_suffix(".safetensors.part")
    part.parent.mkdir(parents=True)
    part.write_bytes(payload[:8])
    download_file("https://example.test/ltx", dest, sha256=digest, expected_bytes=len(payload), opener=opener)
    assert dest.read_bytes() == payload
    assert seen["headers"]["Range"] == "bytes=8-"
    assert not part.exists()

    def bad_opener(url, headers):
        chunks = [payload]

        def read():
            return chunks.pop(0) if chunks else b""

        return 200, read, len(payload)

    other = tmp_path / "bad.safetensors"
    with pytest.raises(PlainError) as caught:
        download_file("https://example.test/bad", other, sha256="0" * 64, expected_bytes=len(payload), opener=bad_opener)
    assert "checksum" in str(caught.value)
    assert not other.exists()


def test_setup_api_and_workflow_png(monkeypatch, tmp_path):
    monkeypatch.setenv("XENO_MODELS", str(tmp_path))
    setup = inspect_setup(tmp_path)
    assert "LTX 0.9.5 fast" in setup["missing_required"]
    names = [item["name"] for item in setup["models"]]
    assert "Wan 2.2 TI2V 5B" in names
    assert "Wan 2.2 I2V 14B" in names
    assert "Wan 2.2 TI2V 5B" not in setup["missing_required"]
    from xenoform.models_setup import wan_ready

    assert wan_ready(tmp_path) is False
    assert setup["stems"]["engine"] == stem_status()["engine"]
    assert setup["ableton"] is False
    assert setup["disk"]["free_bytes"] > 0

    from xenoform.ui import create_app

    client = TestClient(create_app())
    page = client.get("/api/setup")
    assert page.status_code == 200
    assert page.json()["try_it"]
    diag = client.get("/api/diagnostics")
    assert diag.status_code == 200
    assert "Xenoform" in diag.json()["diagnostics"]
    assert "Traceback" not in diag.json()["diagnostics"]
    missing = client.post("/api/setup/download", json={"id": "nope"})
    assert missing.status_code == 400
    assert "Traceback" not in missing.json()["detail"]

    workflow = json.loads(Path("workflows/xenoform_draft.json").read_text(encoding="utf-8"))
    png = png_with_workflow(workflow)
    assert read_workflow_png(png)["extra"]["xenoform"]["quality"] == "draft"
    final = json.loads(Path("workflows/xenoform_final.json").read_text(encoding="utf-8"))
    assert final["nodes"][0]["widgets_values"][0] == "final"


def test_tiny_dry_run_needs_no_weights(tmp_path, monkeypatch):
    monkeypatch.setenv("XENO_MODELS", str(tmp_path))
    from xenoform.try_it import try_demo

    result = try_demo(tiny=True, work=tmp_path / "work", out=tmp_path / "cut.mp4")
    assert Path(result["path"]).exists()
    assert Path(result["path"]).stat().st_size > 100
    assert "dry run" in result["message"]
    assert "Traceback" not in result["message"]
