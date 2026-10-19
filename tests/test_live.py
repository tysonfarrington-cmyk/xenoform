"""Live is the browser picture. These checks stay off the video models."""

import shutil
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.director import decode_recipe, empty_state, encode_recipe, session_payload
from xenoform.analyze import read_features
from xenoform.live_mode import interpolator_name, live_ai_status, live_drive, tensorrt_status
from xenoform.notes import identity, plan_sentence
from xenoform.ui import repo_root


def test_live_drive_recipe_and_optional_status():
    features = read_features(repo_root() / "examples" / "demo_features.json")
    drive = live_drive(features)
    assert drive["bass"]
    assert len(drive["bass"]) == len(drive["mid"]) == len(drive["onset"])
    assert drive["fps"] > 0
    state = empty_state()
    state["quality"] = "live"
    restored = decode_recipe(encode_recipe(state))
    assert restored["quality"] == "live"
    assert encode_recipe(restored) == encode_recipe(state)
    assert identity("live") == ("live", "preview")
    sentence = plan_sentence({"misses": [], "hits": []}, quality="live", seed=2727)
    assert "browser" in sentence
    ai = live_ai_status()
    trt = tensorrt_status()
    assert ai["required"] is False
    assert trt["required"] is False
    if not ai["present"]:
        assert "not installed" in ai["detail"]
        assert "Nothing else was changed" in ai["detail"]
    if not trt["present"]:
        assert "regular checkpoint" in trt["detail"]
    assert interpolator_name()
    payload = session_payload(features, audio_id="demo", title="Demo", video="", endpoint="")
    assert payload["quality"] == "live"
    assert payload["drive"]["bass"]


def test_live_record_becomes_an_mp4(tmp_path, monkeypatch):
    webm = tmp_path / "live.webm"
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x221018:s=160x90:d=0.3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=220:duration=0.3",
            "-shortest",
            "-c:v",
            "libvpx",
            "-b:v",
            "200k",
            "-c:a",
            "libopus",
            str(webm),
        ]
    )
    import xenoform.ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    response = client.post("/api/live/record", files={"file": ("live.webm", webm.read_bytes(), "video/webm")})
    assert response.status_code == 200, response.text
    body = response.json()
    assert "Recorded" in body["detail"]
    media = client.get(body["url"])
    assert media.status_code == 200
    assert media.content[4:8] == b"ftyp"


def test_live_canvas_under_swiftshader():
    chrome = Path("/opt/google/chrome/chrome")
    if not chrome.exists():
        found = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
        if not found:
            return
        chrome = Path(found)
    page = repo_root() / "src" / "xenoform" / "ui_static" / "live-smoke.html"
    profile = Path("/tmp/xeno-live-smoke-profile")
    if profile.exists():
        shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--use-gl=angle",
            "--use-angle=swiftshader",
            f"--user-data-dir={profile}",
            "--virtual-time-budget=3000",
            "--timeout=15000",
            "--dump-dom",
            page.as_uri(),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=40,
    )
    text = proc.stdout or ""
    assert 'data-live-smoke="ok"' in text, (proc.returncode, text[-800:], (proc.stderr or "")[-400:])
