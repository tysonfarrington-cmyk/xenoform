"""A draft animatic is a CPU stills pass. It does not load a checkpoint."""

from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.animatic import HEIGHT, WIDTH, render_animatic
from xenoform.eligibility import audit_default_workflows
from xenoform.ui import create_app
from xenoform.video import read_all_frames


def test_animatic_cuts_colour_on_the_beat_without_a_model(tmp_path):
    out = tmp_path / "animatic.mp4"
    info = render_animatic(
        [
            {"start": 0.0, "end": 2.0, "beat": "calm"},
            {"start": 2.0, "end": 4.0, "beat": "drop"},
        ],
        {"duration": 4.0, "beats": [0.0, 2.0], "sections": []},
        out,
    )
    assert info["seconds"] < 3
    assert info["width"] == WIDTH == 192
    assert info["height"] == HEIGHT == 96
    assert info["cuts"] == 1
    frames = read_all_frames(out)
    assert frames.shape[1:] == (96, 192, 3)
    calm = frames[0, 10, 10].astype(int)
    drop = frames[24, 10, 10].astype(int)
    assert abs(int(calm[0]) - 36) < 12 and abs(int(calm[2]) - 54) < 12
    assert int(drop[0]) > int(calm[0]) + 40
    assert int(drop[0]) > int(drop[1])
    source = Path(__file__).resolve().parents[1].joinpath("src/xenoform/animatic.py").read_text(encoding="utf-8")
    assert "Checkpoint" not in source
    assert "comfy" not in source.lower()


def test_animatic_route_serves_the_preview():
    client = TestClient(create_app())
    response = client.post(
        "/api/animatic",
        json={
            "audio_id": "missing",
            "scenes": [
                {"start": 0.0, "end": 1.0, "beat": "calm"},
                {"start": 1.0, "end": 2.0, "beat": "drop"},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["width"] == 192
    assert body["seconds"] < 3
    media = client.get(body["url"])
    assert media.status_code == 200
    assert media.headers["content-type"].startswith("video/mp4")
    assert client.get("/media/animatic/missing").status_code == 404


def test_preview_control_stays_off_the_simple_desk():
    root = Path(__file__).resolve().parents[1]
    script = (root / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    css = (root / "src" / "xenoform" / "ui_static" / "app.css").read_text(encoding="utf-8")
    assert 'data-act="preview"' in script
    easy = script.split("function renderEasy()", 1)[1].split("function placeKey", 1)[0]
    assert 'data-act="preview"' not in easy
    assert "morph-method" not in easy
    assert "shimmer" not in css
    assert audit_default_workflows() == []
