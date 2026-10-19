"""Stress and safety checks for the desk. Audio is real. ComfyUI is mocked or absent."""

from __future__ import annotations

import json
import math
import subprocess
import threading
import time
import tracemalloc
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform.ui import create_app

_RESULTS = Path("/tmp/xeno-stress-results.jsonl")


def _note(name: str, **fields) -> None:
    row = {"name": name, **fields}
    with _RESULTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _ffmpeg(*args: str, dest: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", *args, str(dest)],
        check=True,
        capture_output=True,
    )
    return dest


def _tone(dest: Path, *, rate: int, seconds: float, channels: int, gain: float = 1.0, freq: float = 440.0) -> Path:
    source = f"sine=frequency={freq}:sample_rate={rate}:duration={seconds}"
    filters = ["-ac", str(channels)]
    if gain != 1.0:
        filters = ["-filter:a", f"volume={gain}", *filters]
    return _ffmpeg("-f", "lavfi", "-i", source, *filters, dest=dest)


def _clicks(dest: Path, *, period: float, seconds: float) -> Path:
    gap = period - 0.08
    expr = f"sin(2*PI*880*t)*gt(mod(t\\,{period})\\,{gap})"
    return _ffmpeg("-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={seconds}", "-ac", "1", dest=dest)


def _post_audio(client: TestClient, path: Path) -> dict:
    started = time.perf_counter()
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    response = client.post(
        "/api/analyze",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
    )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    body = response.json()
    body["_elapsed"] = elapsed
    body["_peak_mb"] = peak / (1024 * 1024)
    _note(
        path.stem,
        seconds=round(elapsed, 3),
        peak_mb=round(body["_peak_mb"], 2),
        duration=body.get("duration"),
        tempo=body.get("tempo"),
        sections=len(body.get("sections") or []),
    )
    assert math.isfinite(float(body["duration"]))
    assert math.isfinite(float(body["tempo"]))
    return body


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    folder = tmp_path_factory.mktemp("clips")
    ten = _tone(folder / "ten48.wav", rate=48000, seconds=10, channels=2)
    _ffmpeg("-i", str(ten), "-ar", "44100", "-ac", "1", dest=folder / "ten441.wav")
    _ffmpeg("-i", str(folder / "ten441.wav"), "-b:a", "128k", dest=folder / "ten.mp3")
    _ffmpeg("-i", str(folder / "ten441.wav"), dest=folder / "ten.flac")
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "12", dest=folder / "silence.wav")
    _tone(folder / "quiet.wav", rate=48000, seconds=8, channels=1, gain=0.001, freq=330)
    _clicks(folder / "fast.wav", period=0.3, seconds=12)
    _clicks(folder / "slow.wav", period=1.5, seconds=15)
    _ffmpeg("-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "360", dest=folder / "sixmin.wav")
    return folder


@pytest.fixture()
def client():
    from xenoform import ui as ui_mod

    ui_mod._JUDGE_HITS.clear()
    return TestClient(create_app())


def _wait_idle(timeout: float = 5.0) -> None:
    from xenoform import ui as ui_mod

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with ui_mod._LOCK:
            running = [job for job in ui_mod._JOBS.values() if job.get("status") == "running"]
        if not running:
            return
        time.sleep(0.02)
    with ui_mod._LOCK:
        for job in ui_mod._JOBS.values():
            if job.get("status") == "running":
                job["status"] = "cancelled"


def test_storage_id_rejects_traversal(client, tmp_path, monkeypatch):
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    escaped = Path("/tmp/xeno-audit-pwn")
    if escaped.exists():
        escaped.unlink()
    demo = client.get("/api/demo").json()
    response = client.post(
        "/api/notes/apply",
        json={
            "audio_id": "../../../../tmp/xeno-audit-pwn",
            "scenes": demo["scenes"],
            "patch": {"transition_type": "dive-splash"},
            "note": "the ending plops",
        },
    )
    assert response.status_code == 400
    assert "not a name" in response.json()["detail"]
    assert not escaped.exists()
    assert not (tmp_path / "notes").exists() or escaped not in (tmp_path / "notes").rglob("*")
    nested = client.post(
        "/api/notes/apply",
        json={"audio_id": "..", "scenes": demo["scenes"], "patch": {"edit": "snap"}},
    )
    assert nested.status_code == 400


def test_resolve_video_stays_inside_jobs(tmp_path, monkeypatch):
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    secret = Path("/tmp/jobs/secret.mp4")
    ui_mod._JOBS["abcd1234"] = {"path": str(secret)}
    assert ui_mod.resolve_video("/etc/passwd") is None
    assert ui_mod.resolve_video("/tmp/jobs/secret.mp4") is None
    assert ui_mod.resolve_video("/api/jobs/abcd1234/video") is None
    owned = tmp_path / "jobs" / "abcd1234" / "xenoform.mp4"
    ui_mod._JOBS["abcd1234"] = {"path": str(owned)}
    assert ui_mod.resolve_video("/api/jobs/abcd1234/video") == owned.resolve()
    demo = ui_mod.resolve_video("/media/demo")
    assert demo is not None and demo.name == "demo_base.mp4"


def test_base_header_cannot_break_out(client):
    hostile = client.get("/", headers={"x-xeno-base": '"><script>alert(1)</script>'})
    assert hostile.status_code == 200
    assert "<script>alert" not in hostile.text
    assert 'window.XENO_BASE=""' in hostile.text
    judges = client.get("/judges", headers={"x-xeno-base": '"><script>'})
    assert "<script>" not in judges.text
    assert 'base href="/static/"' in judges.text
    proxied = client.get("/", headers={"x-xeno-base": "/xenoform"})
    assert 'window.XENO_BASE="/xenoform"' in proxied.text


def test_upload_cap_answers_413(client, monkeypatch):
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "_MAX_UPLOAD_BYTES", 32)
    blob = b"R" * 64
    for path in ("/api/analyze", "/api/hero", "/api/forms", "/api/live/record"):
        name = "song.wav" if "analyze" in path or "live" in path else "hero.png"
        response = client.post(path, files={"file": (name, blob, "application/octet-stream")})
        assert response.status_code == 413, path


def test_judge_duration_is_bounded(client):
    from xenoform import ui as ui_mod

    ui_mod._JUDGE_HITS.clear()
    started = time.perf_counter()
    huge = client.post("/api/judges/analyze", json={"duration": 1e12, "beats": [0.5, 1.0], "tempo": 120})
    elapsed = time.perf_counter() - started
    assert huge.status_code == 200
    assert elapsed < 1.5
    ends = [float(scene.get("end") or 0) for scene in huge.json()["scenes"]]
    assert ends
    assert max(ends) <= 1200.5
    _note("judges-1e12", seconds=round(elapsed, 3), end=max(ends), scenes=len(ends))
    infinite = client.post("/api/judges/analyze", json={"duration": "inf"})
    assert infinite.status_code == 400
    missing = client.post("/api/judges/analyze", json={"duration": "nan", "beats": []})
    assert missing.status_code == 400


def test_audio_shapes_and_story(client, clips):
    shapes = {}
    for name in ("ten48.wav", "ten441.wav", "ten.mp3", "ten.flac", "silence.wav", "quiet.wav", "fast.wav", "slow.wav"):
        shapes[name] = _post_audio(client, clips / name)
    assert shapes["ten48.wav"]["duration"] == pytest.approx(10, abs=0.4)
    assert shapes["ten441.wav"]["duration"] == pytest.approx(10, abs=0.4)
    assert shapes["silence.wav"]["duration"] == pytest.approx(12, abs=0.4)
    assert shapes["quiet.wav"]["duration"] == pytest.approx(8, abs=0.4)
    assert float(shapes["fast.wav"]["tempo"]) > float(shapes["slow.wav"]["tempo"])
    six = _post_audio(client, clips / "sixmin.wav")
    assert six["duration"] == pytest.approx(360, abs=2)
    assert six["_elapsed"] < 90
    assert six["_peak_mb"] < 1500
    for register in ("pynchon", "lecarre", "tolkien", "rome", "custom"):
        t0 = time.perf_counter()
        story = client.post(
            "/api/story",
            json={
                "audio_id": six["audio_id"],
                "register": register,
                "brief": "A rocket's life, from birth to falling back to earth, cold and paranoid.",
                "rolls": 1,
            },
        )
        spent = time.perf_counter() - t0
        assert story.status_code == 200, story.text
        assert story.json()["scenes"]
        _note(f"story-{register}", seconds=round(spent, 3), scenes=len(story.json()["scenes"]))


def test_huge_storyboard_stays_bounded(client):
    demo = client.get("/api/demo").json()
    seed = dict(demo["scenes"][0])
    scenes = [dict(seed, index=index, id=f"s{index}") for index in range(400)]
    started = time.perf_counter()
    qa = client.post("/api/qa", json={"audio_id": "demo", "scenes": scenes, "energy": 0, "flash": "normal"})
    qa_s = time.perf_counter() - started
    assert qa.status_code == 200
    started = time.perf_counter()
    recut = client.post("/api/recut", json={"audio_id": "demo", "scenes": scenes, "energy": 1, "quality": "live"})
    recut_s = time.perf_counter() - started
    assert recut.status_code == 200
    assert recut.json()["scenes"]
    _note(
        "huge-board",
        qa_seconds=round(qa_s, 3),
        recut_seconds=round(recut_s, 3),
        posted=400,
        recut_scenes=len(recut.json()["scenes"]),
    )
    assert qa_s < 5
    assert recut_s < 8


def test_live_generate_while_comfy_is_down(client):
    from xenoform.comfy_health import ping

    started = time.perf_counter()
    health = ping("http://127.0.0.1:9")
    health_s = time.perf_counter() - started
    assert health["ok"] is False
    assert health_s < 3
    demo = client.get("/api/demo").json()
    demo["quality"] = "live"
    demo["live"] = False
    started = time.perf_counter()
    response = client.post("/api/generate", json=demo)
    assert response.status_code == 200
    job_id = response.json()["id"]
    job = {}
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "done"
    _note("live-offline", health_seconds=round(health_s, 3), job_seconds=round(time.perf_counter() - started, 3))


def test_comfy_client_construct_is_bounded():
    from xenoform.config import load_config
    from xenoform.restyle import _make_client
    from xenoform.ui import repo_root

    cfg = load_config(repo_root() / "configs" / "example.json")
    cfg["comfy"]["base_url"] = "http://127.0.0.1:8188"
    cfg["comfy"]["proxy_url"] = "http://127.0.0.1:9"
    box: dict = {}

    def attempt() -> None:
        try:
            _make_client(cfg)
            box["ok"] = True
        except Exception as exc:
            box["error"] = type(exc).__name__

    thread = threading.Thread(target=attempt, daemon=True)
    thread.start()
    thread.join(3)
    hung = thread.is_alive()
    _note("comfy-client", hung=hung, **box)
    assert hung is False


def test_cancel_mid_render(client, monkeypatch):
    from xenoform.turbo import JobCancelled

    release = threading.Event()

    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        for _ in range(80):
            if cancel and cancel():
                raise JobCancelled("Cancelled. The card changed.")
            time.sleep(0.05)
        release.wait(1)
        return {"mode": "dry-run", "chunks": 0, "fades": []}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    demo = client.get("/api/demo").json()
    demo["quality"] = "draft"
    started = client.post("/api/generate", json=demo)
    assert started.status_code == 200
    job_id = started.json()["id"]
    time.sleep(0.05)
    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    deadline = time.monotonic() + 3
    job = cancelled.json()
    while time.monotonic() < deadline and job.get("status") == "running":
        job = client.get(f"/api/jobs/{job_id}").json()
        time.sleep(0.02)
    release.set()
    assert job["status"] == "cancelled"
    _wait_idle()


def test_two_jobs_then_the_third_waits(client, monkeypatch):
    hold = threading.Event()

    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        hold.wait(3)
        return {"mode": "dry-run", "chunks": 0, "fades": []}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    demo = client.get("/api/demo").json()
    demo["quality"] = "draft"
    try:
        first = client.post("/api/generate", json=demo)
        second = client.post("/api/generate", json=demo)
        third = client.post("/api/generate", json=demo)
        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429
    finally:
        hold.set()
        _wait_idle()


def test_rapid_live_clicks_do_not_crash(client):
    demo = client.get("/api/demo").json()
    demo["quality"] = "live"
    started = time.perf_counter()
    codes = []
    for _ in range(8):
        response = client.post("/api/generate", json=demo)
        codes.append(response.status_code)
    elapsed = time.perf_counter() - started
    assert set(codes) <= {200, 429}
    assert 500 not in codes
    assert elapsed < 8
    _wait_idle()
    _note("rapid-live", seconds=round(elapsed, 3), codes=codes)


def test_audio_errors_hide_paths():
    from xenoform.errors import audio_read_error

    sentence = audio_read_error(RuntimeError("Error opening '/tmp/secret/song.wav': format"))
    assert sentence == "Could not read that audio."
    assert "secret" not in sentence
    missing = audio_read_error(FileNotFoundError(2, "No such file", "/tmp/secret/song.wav"))
    assert "/" not in missing


def test_font_licence_is_shipped():
    text = (Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "fonts" / "OFL.txt").read_text()
    assert "SIL OPEN FONT LICENSE" in text
    assert "Space Grotesk Project Authors" in text
    assert "Reserved Font Name 'Share'" in text
    licences = (Path(__file__).resolve().parents[1] / "docs" / "LICENCES.md").read_text()
    assert "Open RAIL-M" in licences
    assert "Community License" in licences
    assert "Apache 2.0" in licences
    assert "not checked" in licences
