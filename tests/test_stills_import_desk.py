"""Import a folder on the desk (docs/MUSIC_VIDEO_PLAN.md section 4): POST /api/stills/import runs ``stills.import_folder``
in the background, the Library row's slot shared with a grow, every picture through the usual checks (``stills.check``)
and kept as a thing, a scene or a place; the Library row has the folder field, the kind and the button."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import stills as L
from xenoform import ui as _ui

from test_stills import _grown, _still

APP = (Path(_ui.__file__).parent / "ui_static" / "app.js").read_text(encoding="utf-8")


@pytest.fixture()
def client():
    with _ui._LOCK:
        _ui._STILLS_JOB.clear()
    yield TestClient(_ui.create_app())
    with _ui._LOCK:
        _ui._STILLS_JOB.clear()


def _pool(vibe: str) -> None:
    for i in range(3):
        _grown(vibe, f"00{i}_p{i}.jpg", f"p{i}", r=0.28 + 0.02 * i)  # a pool the new ones are not twins of


def _wait(client: TestClient) -> dict:
    for _ in range(200):
        job = client.get("/api/stills").json()["job"]
        if job.get("status") in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("the import never finished")


def test_the_route_refuses_what_it_cannot_import(client, tmp_path, monkeypatch):
    _pool("synthetic3")
    folder = tmp_path / "pics"
    folder.mkdir()
    assert client.post("/api/stills/import", json={"folder": str(folder)}).status_code == 400  # no vibe
    assert client.post("/api/stills/import", json={"vibe": "no-such-vibe", "folder": str(folder)}).status_code == 400
    assert client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(folder), "kind": "video"}).status_code == 400
    assert client.post("/api/stills/import", json={"vibe": "synthetic3"}).status_code == 400  # no folder
    assert client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(tmp_path / "gone")}).status_code == 400
    r = client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(folder)})
    assert r.status_code == 400 and "No png" in r.json()["detail"]  # an empty folder
    r = client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(L.root())})
    assert r.status_code == 400 and "library itself" in r.json()["detail"]
    for i in range(3):
        _still(folder / f"{i:02d}_thing{i}.png", r=0.16)
    monkeypatch.setattr(_ui, "MAX_IMPORT", 2)
    r = client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(folder)})
    assert r.status_code == 400 and "at most 2" in r.json()["detail"]


def test_an_import_runs_the_checks_and_keeps_its_kind(client, tmp_path):
    _pool("synthetic3")
    folder = tmp_path / "batch"
    _still(folder / "00_astrolabe.png", cx=0.62, cy=0.45, r=0.27)
    _still(folder / "01_tiny_thing.png", r=0.02)  # fails the size check: set aside under rejected/
    _still(folder / "02_vinyl_record.png", cx=0.4, cy=0.5, r=0.15)  # a banned prop: skipped
    started = client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(folder)})
    assert started.status_code == 200, started.text
    assert started.json()["asked"] == 3 and started.json()["kind"] == "object"
    job = _wait(client)
    assert job["status"] == "done" and job["action"] == "import" and job["kept"] == 1
    assert "Kept 1 of 3" in job["note"] and "rejected 1 (size 1" in job["note"] and "skipped 1" in job["note"]
    rows = {r["noun"]: r for r in L.grown()["synthetic3"]}
    assert "astrolabe" in rows and L.kind_of(rows["astrolabe"]) == "object" and "imported on the desk" in rows["astrolabe"]["source"]
    assert list((L.root() / "synthetic3" / "rejected").glob("*_tiny_thing_*size*.jpg"))  # its reasons in its name
    # scenes and places keep their kind through the import
    scenes = tmp_path / "scenes"
    _still(scenes / "00_dark_shore.png", r=0.4, back=(30, 40, 60))
    assert client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(scenes), "kind": "scene"}).status_code == 200
    _wait(client)
    places = tmp_path / "places"
    _still(places / "00_lantern.png", r=0.3, back=(40, 30, 20))
    assert client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(places), "kind": "setting",
                                                    "origin": "made in Blender by me"}).status_code == 200
    _wait(client)
    rows = {r["noun"]: r for r in L.grown()["synthetic3"]}
    assert L.kind_of(rows["dark shore"]) == "scene" and L.kind_of(rows["lantern"]) == "setting"
    assert rows["lantern"]["source"] == "made in Blender by me"


def test_one_library_job_at_a_time(client, tmp_path, monkeypatch):
    _pool("synthetic3")
    folder = tmp_path / "pics"
    _still(folder / "00_astrolabe.png", r=0.16)
    with _ui._LOCK:
        _ui._STILLS_JOB.update({"status": "running", "vibe": "synthetic3"})
    r = client.post("/api/stills/import", json={"vibe": "synthetic3", "folder": str(folder)})
    assert r.status_code == 409


def test_the_files_dropped_on_the_desk_import_too(client, tmp_path):
    _pool("synthetic3")
    dropped = tmp_path / "dropped"
    _still(dropped / "00_astrolabe.png", cx=0.62, cy=0.45, r=0.27)
    with _ui._LOCK:
        _ui._OWN["drop1"] = dropped
    try:
        assert client.post("/api/stills/import", json={"vibe": "synthetic3", "own_id": "drop1"}).status_code == 200
        assert _wait(client)["kept"] == 1
    finally:
        with _ui._LOCK:
            _ui._OWN.pop("drop1", None)


def test_the_library_row_has_import_a_folder():
    row = APP.split("function stillsRow(easy)")[1].split("\nfunction ")[0]
    assert "${importRow(easy, running)}" in row
    imp = APP.split("function importRow(easy, running)")[1].split("\nasync function ")[0]
    assert 'id="easy-import-folder"' in imp and 'id="easy-import-kind"' in imp and 'data-act="easy-import-folder"' in imp
    assert '["object", "Things"], ["scene", "Scenes"], ["setting", "Places"]' in APP
    assert '"/api/stills/import"' in APP and 'act === "easy-import-folder"' in APP
    assert '"importFolder", "importKind"' in APP.split("const EASY_SAVED_KEYS")[1].split("\n")[0]
    assert 'job.action === "import"' in APP  # the status line says what the import is doing
