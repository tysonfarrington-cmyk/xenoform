import time
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.ui import create_app


def test_demo_session_and_recipe_roundtrip():
    client = TestClient(create_app())
    demo = client.get("/api/demo")
    assert demo.status_code == 200
    body = demo.json()
    assert body["audio_id"] == "demo"
    assert body["waveform"]
    assert len(body["forms"]) == 18
    assert len(body["presets"]) == 10
    assert body["scenes"][0]["protagonist"] == "the rocket"
    assert body["scenes"][0]["conditioning"] == "first-frame"
    assert [item["id"] for item in body["registers"]] == ["pynchon", "lecarre", "tolkien", "rome", "custom"]
    assert body["register"] == "pynchon"
    assert body["cards"][0]["text"].startswith("The arc")
    assert {item["id"] for item in body["transitions"]} >= {
        "pour-harden",
        "droplet-burst",
        "ribbon",
        "snap",
        "grow-out",
        "dive-splash",
        "bolt-strike",
        "swim",
    }
    assert body["recipe"].startswith("XF-")
    assert body["quality"] == "live"
    assert set(body["etas"]) >= {"live", "turbo", "draft", "final"}
    assert body["etas"]["live"]["first_s"] == 0
    assert body["etas"]["turbo"]["first_s"] <= 90
    assert body["audio_url"] == "/media/audio/demo"
    assert body["drive"]["bass"]
    audio = client.get("/media/audio/demo")
    assert audio.status_code == 200
    assert audio.content[:4] == b"RIFF"
    page = client.get("/")
    assert page.status_code == 200
    assert "music video director" in page.text
    encoded = client.post("/api/recipe/encode", json=body)
    assert encoded.status_code == 200
    restored = client.post("/api/recipe/decode", json={"recipe": encoded.json()["recipe"]})
    assert restored.status_code == 200
    assert restored.json()["blocks"][0]["form"] == body["blocks"][0]["form"]
    bad = client.post("/api/recipe/decode", json={"recipe": "nope"})
    assert bad.status_code == 400


def test_generate_job_uses_the_pipeline(monkeypatch, tmp_path):
    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"not-a-real-mp4")
        if on_progress:
            on_progress("render", 0.5, "Frame 1 / 2")
            on_progress("done", 1.0, "Ready")
        return {"mode": "dry-run", "chunks": 1, "fades": []}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    client = TestClient(create_app())
    demo = client.get("/api/demo").json()
    started = client.post("/api/generate", json=demo)
    assert started.status_code == 200
    job_id = started.json()["id"]
    job = None
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "done"
    assert job["mode"] == "dry-run"
    video = client.get(f"/api/jobs/{job_id}/video")
    assert video.status_code == 200
    assert video.content == b"not-a-real-mp4"