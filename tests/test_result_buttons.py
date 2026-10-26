"""The Simple result screen's buttons do what they say (26 Oct): Re-cut posts its knobs, and the review the old
"Make it better" ran no longer crashes on the continuity bible the desk sends."""
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_the_recut_posts_its_knobs_and_the_dead_button_is_gone():
    app = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    fn = app.split("async function recutWithKnobs")[1].split("async function easyMake")[0]
    assert 'method: "POST"' in fn and "JSON.stringify(body)" in fn and "poll(id);" in fn
    assert 'data-act="easy-better"' not in app and 'act === "easy-better"' not in app
    assert 'data-act="easy-recut-knobs"' in app


def test_the_recut_route_takes_a_post_and_refuses_a_get():
    from xenoform.ui import create_app

    client = TestClient(create_app())
    assert client.get("/api/jobs/nope/recut").status_code == 405
    assert client.post("/api/jobs/nope/recut", json={"dance_fx": "auto"}).status_code == 404


def test_the_review_takes_the_continuity_bible_without_crashing(tmp_path):
    from xenoform import continuity

    # the helper skips rows that are not dicts instead of dict()-ing a string (the bible's keys, 26 Oct)
    assert continuity.ensure_stills(["elements", {"id": "x", "sentence": ""}], tmp_path) == [{"id": "x", "sentence": ""}]
    from xenoform.ui import create_app

    client = TestClient(create_app())
    body = {"audio_id": "demo", "quality": "live", "scenes": [], "continuity": {"elements": ["a", "b"], "bible": "two lines"}}
    r = client.post("/api/v1/review", json=body)
    assert r.status_code == 200, r.text
    assert "findings" in r.json()
