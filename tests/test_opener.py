"""The desk opens on the drop, before a checkpoint is loaded."""

from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.analyze import read_features
from xenoform.eligibility import audit_default_workflows
from xenoform.morph.lock import downbeats_from
from xenoform.opener import first_drop
from xenoform.score import directors_score
from xenoform.source_library import load_library
from xenoform.ui import create_app


def test_first_drop_lands_on_a_downbeat():
    root = Path(__file__).resolve().parents[1]
    features = read_features(root / "examples" / "demo_features.json")
    library = load_library(root / "library", root)
    rows = directors_score(features, library=library, exclude_faces=True)
    opened = first_drop(features, rows)
    assert opened["ready"] is True
    assert opened["kind"] == "drop"
    downs = downbeats_from(features["beats"])
    assert min(abs(opened["at"] - beat) for beat in downs) < 0.001
    assert opened["source"] and opened["target"]
    assert "→" in opened["line"]
    assert "downbeat" in opened["line"]
    assert "api_key" not in opened


def test_a_song_without_a_drop_stays_quiet():
    opened = first_drop({"sections": [{"label": "calm", "start": 0, "end": 2}], "beats": [0.0, 0.5]})
    assert opened["ready"] is False
    assert opened["source"] == ""


def test_opener_route_is_ready_for_the_demo():
    client = TestClient(create_app())
    response = client.post("/api/opener", json={"audio_id": "demo", "exclude_faces": True})
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["at"] > 0
    assert body["source"] and body["target"]
    assert "LtxApi" not in str(body)


def test_drop_card_is_on_the_simple_desk_without_morph_controls():
    root = Path(__file__).resolve().parents[1]
    script = (root / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    css = (root / "src" / "xenoform" / "ui_static" / "app.css").read_text(encoding="utf-8")
    easy = script.split("function renderEasy()", 1)[1].split("function placeKey", 1)[0]
    assert "dropCard()" in easy
    assert 'data-act="open-drop"' in script
    assert "morph-method" not in easy
    assert "morph-source" not in easy
    assert "morph-hit" not in easy
    assert "shimmer" not in css
    assert "animation" not in css.split(".drop-open", 1)[1].split(".facts", 1)[0]
    assert audit_default_workflows() == []
