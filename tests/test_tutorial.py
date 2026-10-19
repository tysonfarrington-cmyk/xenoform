import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
ORDER = [
    "song",
    "beats",
    "live",
    "brief",
    "chips",
    "continuity",
    "treatment",
    "energy",
    "looks",
    "gate",
    "generate",
    "review",
    "share",
    "weights",
]


def test_tutorial_catalog_and_page():
    data = json.loads((ROOT / "src/xenoform/ui_static/tutorial.json").read_text(encoding="utf-8"))
    tours = {tour["id"]: tour for tour in data["tours"]}
    assert tours["first-video"]["name"] == "Make your first video"
    assert tours["continuity"]["name"] == "Continuity & cast lock"
    assert tours["energy"]["name"] == "Energy & re-cut"
    assert tours["first-video"]["steps"] == ORDER
    assert tours["continuity"]["steps"] == ["brief", "continuity", "treatment"]
    assert tours["energy"]["steps"] == ["beats", "energy", "looks"]
    for step_id in ORDER:
        step = data["steps"][step_id]
        assert step["title"].strip()
        body = step["body"]
        assert 1 <= len(body) <= 3
        for line in body:
            assert line.strip().endswith(".")
            assert "\n" not in line
    assert data["steps"]["weights"]["title"] == "Open weights"
    assert "Open weights" in data["steps"]["weights"]["body"][-1]
    assert "Open weights only" not in data["steps"]["weights"]["body"][-1]
    assert data["steps"]["generate"]["sim"] == "Simulated. No GPU job was started. The bundled demo stands in."
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert "Tutorial" in page.text
    assert "Reset tutorial" in page.text
    assert "/static/tutorial.js" in page.text
    raw = client.get("/static/tutorial.json")
    assert raw.status_code == 200
    assert [tour["id"] for tour in raw.json()["tours"]] == ["simple", "first-video", "continuity", "energy"]
    assert tours["simple"]["name"] == "Simple mode in 30 seconds"
    assert tours["simple"]["steps"] == ["easy-song", "easy-vibe", "easy-make"]
    script = client.get("/static/app.js")
    assert script.status_code == 200
    assert "Guided tours" in script.text
    assert 'data-tour="song"' in script.text
