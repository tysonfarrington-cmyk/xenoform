"""python-osc is optional: without it every /api/osc route answers one plain sentence and nothing else in the desk changes. These tests
hide the package whether or not it is installed, and import nothing from it, so they run on a clean install too (the rest of the OSC
tests skip there)."""
import builtins
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import osc_relay
from xenoform.cli import main
from xenoform.osc_relay import OscRelay
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _fresh_relay():
    osc_relay.reset()
    yield
    osc_relay.reset()


def _hide_python_osc(monkeypatch):
    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("pythonosc"):
            raise ImportError("no python-osc")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_without_python_osc_every_route_answers_the_one_sentence(monkeypatch):
    c = TestClient(create_app())
    _hide_python_osc(monkeypatch)
    assert osc_relay.osc_available() is False
    for method, path, kw in (("get", "/api/osc", {}), ("put", "/api/osc", {"json": {"on": True}}), ("post", "/api/osc/frame", {"json": {"bass": 1}}),
                             ("get", "/api/osc/status", {}), ("get", "/api/osc/addresses", {}), ("get", "/api/osc/stream", {"params": {"timeout": 0.05}})):
        r = getattr(c, method)(path, **kw)
        assert r.status_code == 503 and r.json()["detail"] == osc_relay.INSTALL_HINT, (method, path, r.status_code)
    assert "pip install" in osc_relay.INSTALL_HINT and "xenoform[osc]" in osc_relay.INSTALL_HINT and "\n" not in osc_relay.INSTALL_HINT
    with c.websocket_connect("/ws/osc") as ws:
        msg = ws.receive_json()
        assert msg == {"type": "error", "detail": osc_relay.INSTALL_HINT}
    assert c.get("/api/midi/status").status_code == 200, "nothing else in the desk notices"
    with pytest.raises(osc_relay.OscUnavailable, match="pip install"):
        OscRelay().configure({"on": True})
    assert main(["osc", "relay", "--seconds", "0.1"]) == 1, "the headless relay says so too and exits 1"


def test_importing_the_relay_needs_no_python_osc():
    """The core app imports osc_relay (the desk includes its router) with python-osc absent: nothing at import time touches it.
    A fresh interpreter with the package hidden imports the module and builds the desk."""
    code = (
        "import builtins\n"
        "real = builtins.__import__\n"
        "def fake(name, *a, **k):\n"
        "    if name.startswith('pythonosc'):\n"
        "        raise ImportError('no python-osc')\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = fake\n"
        "import xenoform.osc_relay as r\n"
        "from xenoform.ui import create_app\n"
        "create_app()\n"
        "assert r.osc_available() is False and r.router.routes\n"
        "print('imported without python-osc')\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env, cwd=str(ROOT))
    assert run.returncode == 0 and "imported without python-osc" in run.stdout, run.stdout + run.stderr


def test_the_offline_export_keeps_working_and_keeps_its_own_sentence(monkeypatch, tmp_path, caplog):
    from xenoform.ui import repo_root

    features = repo_root() / "examples" / "demo_features.json"
    assert main(["osc", str(features), "--out", str(tmp_path / "osc")]) == 0
    assert (tmp_path / "osc" / "osc_addresses.json").is_file() and (tmp_path / "osc" / "frames.csv").is_file()
    _hide_python_osc(monkeypatch)
    assert main(["osc", str(features), "--stream", "--fast"]) == 1
    assert "OSC streaming needs the optional python-osc package" in caplog.text
