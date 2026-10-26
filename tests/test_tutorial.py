import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
# one desk, one tour (26 Oct): the Director desk's tours (first video, continuity, energy) went with it
ORDER = ["easy-song", "easy-vibe", "easy-macros", "easy-make", "weights"]


def test_tutorial_catalog_and_page():
    data = json.loads((ROOT / "src/xenoform/ui_static/tutorial.json").read_text(encoding="utf-8"))
    tours = {tour["id"]: tour for tour in data["tours"]}
    assert list(tours) == ["simple"]
    assert tours["simple"]["name"] == "The desk in a minute"
    assert tours["simple"]["steps"] == ORDER
    for step_id in ORDER:
        step = data["steps"][step_id]
        assert step["title"].strip()
        body = step["body"]
        assert 1 <= len(body) <= 3
        for line in body:
            assert line.strip().endswith(".")
            assert "\n" not in line
    assert set(data["steps"]) == set(ORDER)  # no orphan steps from the old tours
    assert data["steps"]["weights"]["title"] == "Open weights"
    assert "Open weights" in data["steps"]["weights"]["body"][-1]
    assert "Open weights only" not in data["steps"]["weights"]["body"][-1]
    assert data["steps"]["easy-make"]["sim"] == "Simulated. No GPU job was started. The bundled demo stands in."
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert "Tutorial" in page.text
    assert "Reset tutorial" in page.text
    assert "/static/tutorial.js" in page.text
    raw = client.get("/static/tutorial.json")
    assert raw.status_code == 200
    assert [tour["id"] for tour in raw.json()["tours"]] == ["simple"]
    script = client.get("/static/app.js")
    assert script.status_code == 200
    for target in ORDER[:-1]:
        assert f'data-tour="{target}"' in script.text, target
    tour_js = (ROOT / "src/xenoform/ui_static/tutorial.js").read_text(encoding="utf-8")
    assert "first-video" not in tour_js and "dataset.advanced" not in tour_js
