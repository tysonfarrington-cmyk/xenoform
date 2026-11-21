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
    """The repository cloned into custom_nodes: the node pack's five nodes and the desk's two, one web folder (the
    pack's, which holds the Morph Timeline editor and the desk's tab)."""
    import sys

    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = importlib.util.spec_from_file_location("xenoform_comfy_entry", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # as ComfyUI registers it, so the entry's relative import of comfy_pack resolves
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    assert "XenoformTryIt" in module.NODE_CLASS_MAPPINGS
    assert module.NODE_DISPLAY_NAME_MAPPINGS["XenoformTryIt"] == "Xenoform Try It"
    for name in ("XenoformSongAnalysis", "XenoformStoryboard", "XenoformMorphTimeline", "XenoformMorphPair", "XenoformAssemble"):
        assert name in module.NODE_CLASS_MAPPINGS
    assert module.WEB_DIRECTORY == "./comfy_pack/web"
    web = (path.parent / module.WEB_DIRECTORY).resolve()
    assert (web / "morph_timeline.js").is_file() and (web / "xenoform_desk.js").is_file()
    assert set(NODE_CLASS_MAPPINGS) == {"XenoformTryIt", "XenoformSetup"}
    assert "Xenoform Setup Check" in NODE_DISPLAY_NAME_MAPPINGS.values()


def test_the_desk_block_stays_out_of_a_comfyui_that_has_no_desk_install(monkeypatch, capsys):
    """The 21 Nov review: with the root requirements.txt empty, ComfyUI's own Python has no fastapi. The desk's two
    nodes and /xenoform used to register all the same (their imports are lazy), then fail at every queue and answer
    every ComfyUI page load's GET /xenoform with a 500. Without the desk's install only the pack's nodes register."""
    import importlib.util as iu
    import sys

    from xenoform import comfy_server

    real = iu.find_spec
    monkeypatch.setattr(iu, "find_spec", lambda name, *a, **k: None if name == "fastapi" else real(name, *a, **k))
    mounted = []
    monkeypatch.setattr(comfy_server, "mount_prompt_server", lambda: mounted.append(1))
    path = Path(__file__).resolve().parents[1] / "__init__.py"
    spec = iu.spec_from_file_location("xenoform_comfy_entry_bare", path)
    module = iu.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    assert not mounted and "XenoformTryIt" not in module.NODE_CLASS_MAPPINGS and "XenoformSetup" not in module.NODE_CLASS_MAPPINGS
    assert "XenoformStoryboard" in module.NODE_CLASS_MAPPINGS and "XenoformAssemble" in module.NODE_CLASS_MAPPINGS
    assert "Run the desk's installer" in capsys.readouterr().out


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
            assert b"Make a music video." in await script.read()
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


def test_defaults_demo_json_lives_in_configs_and_mirrors_the_house_profile():
    from xenoform.config import load_config
    from xenoform.demo_house import DEMO_HOUSE

    root = Path(__file__).resolve().parents[1]
    assert not (root / "config").exists(), "config/ was folded into configs/"
    data = json.loads((root / "configs" / "defaults_demo.json").read_text(encoding="utf-8"))
    assert data["house"] == DEMO_HOUSE == load_config()["house"]


def test_installers_ship_demucs_by_default_with_an_opt_out():
    """Stems by default: install.ps1 / install.sh add the `stems` extra (Demucs, a CPU torch wheel) after the package
    unless told not to; install.bat passes the switch through; CI stays light."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    ps1 = (root / "install.ps1").read_text(encoding="utf-8")
    sh = (root / "install.sh").read_text(encoding="utf-8")
    bat = (root / "install.bat").read_text(encoding="utf-8")
    assert "[switch]$NoStems" in ps1 and "[stems]" in ps1 and "--no-deps -e $Pack" in ps1
    assert ps1.index("--no-deps -e $Pack") < ps1.index("[stems]")
    assert "--no-stems" in sh and "[stems]" in sh and "download.pytorch.org/whl/cpu" in sh and "--link-nodes" in sh
    assert sh.index("--no-deps -e") < sh.index("[stems]")
    assert "%*" in bat
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    extras = project["optional-dependencies"]
    assert extras["stems"] == ["demucs>=4.0"]
    # stills.py imports PIL at module level, so Pillow must be a plain dependency in both files.
    assert any(dep.startswith("pillow") for dep in project["dependencies"])
    assert "pillow" in (root / "requirements-desk.txt").read_text(encoding="utf-8")
    ci = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "stems" not in ci and "demucs" not in ci


# ---------------------------------------------------------------- the one-click install (review-21nov.md, the audit)


def test_the_scripts_keep_the_line_endings_their_shells_need():
    """A Windows clone checks install.sh out with CRLF and bash stops at "set: pipefail: invalid option name" (run
    under WSL on 21 Nov); a downloaded ZIP has the .bat files with LF. .gitattributes pins both, for clones and ZIPs."""
    import os

    root = Path(__file__).resolve().parents[1]
    rules = {}
    for line in (root / ".gitattributes").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            pattern, *attrs = line.split()
            rules[pattern] = set(attrs)
    for pattern in ("*.bat", "*.cmd", "*.ps1"):
        assert rules[pattern] == {"text", "eol=crlf"}, pattern
    assert rules["*.sh"] == {"text", "eol=lf"}
    assert set(rules) == {"*.bat", "*.cmd", "*.ps1", "*.sh"}  # nothing else changes how it is checked out
    if os.name != "nt":  # the mode git keeps: ./install.sh runs without `bash` in front, and has no carriage return
        assert os.access(root / "install.sh", os.X_OK)
        assert bytes([13]) not in (root / "install.sh").read_bytes()


def test_the_shell_installer_makes_a_half_made_venv_again_and_says_what_is_missing():
    """Ubuntu's python3 has no ensurepip until python3-venv is installed: `python3 -m venv` fails but leaves
    .venv/bin/python behind, and the next run skipped the creation and stopped at "No module named pip"."""
    sh = (Path(__file__).resolve().parents[1] / "install.sh").read_text(encoding="utf-8")
    assert "venv_ok()" in sh and "-m pip --version" in sh and "if ! venv_ok; then" in sh
    made = sh.index('"$PY312" -m venv "$PACK/.venv"')
    assert sh.index('rm -rf "$PACK/.venv"') < made < sh.index("The virtual environment was not created.")
    assert sh.count('rm -rf "$PACK/.venv"') == 2  # before it is made again, and after a creation that failed
    assert "sudo apt install python3-venv" in sh and "brew install python@3.12" in sh
    assert "brew install ffmpeg" in sh and "sudo apt install ffmpeg" in sh and "command -v ffprobe" in sh
    assert sh.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in sh


def test_the_windows_installer_says_ffmpeg_is_missing_at_the_end_too():
    """The first warning is a few hundred lines of pip up the window by the time the install is done."""
    ps1 = (Path(__file__).resolve().parents[1] / "install.ps1").read_text(encoding="utf-8")
    assert "$NoFfmpeg = " in ps1 and "Get-Command ffprobe" in ps1
    first, again = ps1.index("if ($NoFfmpeg)"), ps1.rindex("if ($NoFfmpeg)")
    assert first < ps1.index("requirements-desk.txt") < again < ps1.index('Write-Host "Done.')
    assert ps1.count("winget install Gyan.FFmpeg") == 2 and "winget install Python.Python.3.12" in ps1


def test_setup_says_when_ffmpeg_is_not_on_the_path(monkeypatch, tmp_path):
    """The installers do not install ffmpeg, and without it the desk opens but reads no song and writes no video.
    The Setup page says so, first, until it is there."""
    import shutil

    from xenoform import models_setup

    monkeypatch.setenv("XENO_MODELS", str(tmp_path))
    real = shutil.which
    there = models_setup.ffmpeg_status()
    assert there["found"] is (real("ffmpeg") is not None and real("ffprobe") is not None)

    def without(*names):
        return lambda name, *a, **k: None if name in names else (real(name, *a, **k) or name)

    monkeypatch.setattr(shutil, "which", without("ffprobe"))
    assert models_setup.ffmpeg_status()["line"] == "ffprobe is not on this machine's PATH"
    monkeypatch.setattr(shutil, "which", without("ffmpeg", "ffprobe"))
    gone = models_setup.ffmpeg_status()
    assert gone["found"] is False and gone["missing"] == ["ffmpeg", "ffprobe"]
    assert gone["line"] == "ffmpeg and ffprobe are not on this machine's PATH"
    assert "read songs and write videos" in gone["how"] and "start it again" in gone["how"]

    from xenoform.ui import create_app

    assert TestClient(create_app()).get("/api/setup").json()["ffmpeg"] == gone
    app = (Path(__file__).resolve().parents[1] / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    page = app.split("const noFfmpeg = ", 1)[1].split("setup-head", 1)[0]
    assert "setup.ffmpeg.found === false" in page and 'id="setup-ffmpeg"' in page
    assert page.index('id="setup-ffmpeg"') < page.index("gate ?")  # above the model gate: it comes first
    assert "esc(noFfmpeg.line" in page and "esc(noFfmpeg.how" in page


def test_the_build_backend_is_capped_while_the_licence_is_a_table():
    """setuptools 84 warns that `license = { file = ... }` stops being supported after 18 Feb 2027; an uncapped
    `setuptools>=68` would then fail `pip install -e .`, which every installer runs."""
    import tomllib

    data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
    requires = data["build-system"]["requires"]
    if isinstance(data["project"].get("license"), dict):
        assert requires == ["setuptools>=68,<85"]
    else:  # an SPDX string with license-files needs setuptools 77, and no cap
        assert any(r.startswith("setuptools>=77") for r in requires)
