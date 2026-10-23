"""Stems by default: the background split (start_background_split / split_status / GET /api/stems/for/<id>),
POST /api/stems (cached by song hash), status, envelopes JSON, the CLI, and the JS hooks."""
import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from xenoform import stem_react, stems_api
from xenoform.cli import main
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"


def _song(tmp_path, name="song.wav", sec=2.0, sr=22050):
    t = np.arange(int(sr * sec)) / sr
    y = 0.4 * np.sin(2 * np.pi * 55 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
    for k in range(4):
        i = int(k * 0.5 * sr)
        y[i:i + 300] += np.random.default_rng(k).normal(0, 0.8, 300)
    p = tmp_path / name
    sf.write(str(p), y.astype(np.float32), sr)
    return p


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    stems_api._JOBS.clear()
    return create_app()


def _wait(client, sid, timeout=60):
    for _ in range(int(timeout * 4)):
        j = client.get(f"/api/stems/{sid}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.25)
    raise AssertionError("stems never finished")


def test_split_endpoint_bands_engine_and_cache(app, tmp_path):
    c = TestClient(app)
    song = _song(tmp_path)
    r = c.post("/api/stems", json={"path": str(song), "engine": "bands"})
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["status"] in {"running", "done"} and len(first["id"]) == 16
    assert first.get("engines", {}).get("bands") is True
    j = _wait(c, first["id"])
    assert j["status"] == "done", j
    assert j["engine"] == "librosa" and set(j["stems"]) == set(stem_react.STEMS) and j["count"] == 4
    assert j["envelopes"] == f"/api/stems/{first['id']}/envelopes.json"
    env = c.get(j["envelopes"]).json()
    assert env["fps"] == 24 and env["frames"] > 30 and env["stems"] == j["stems"] and len(env["bass"]) == env["frames"]
    assert env["roles"]["drums"] == "drums" and "drum_hits" in env and env["files"]["bass"].endswith("bass.wav")
    assert c.get(f"/api/stems/{first['id']}/bass.wav").status_code == 200
    # cached: the second request is done at once, and a renamed copy of the same audio shares the cache
    again = c.post("/api/stems", json={"path": str(song)}).json()
    assert again["status"] == "done" and again["cached"] is True and again["id"] == first["id"]
    copy = tmp_path / "renamed.wav"
    copy.write_bytes(song.read_bytes())
    assert c.post("/api/stems", json={"path": str(copy)}).json()["id"] == first["id"]
    assert stems_api.stems_path_for(song) == tmp_path / "stems" / first["id"] / "stems.json"
    assert stems_api.stems_path_for(tmp_path / "missing.wav") is None


def test_bad_requests(app, tmp_path):
    c = TestClient(app)
    assert c.post("/api/stems", json={"path": str(tmp_path / "nope.wav")}).status_code == 400
    assert c.post("/api/stems", json={"audio_id": "not-loaded-xyz"}).status_code == 404
    assert c.post("/api/stems", json={"path": str(_song(tmp_path)), "engine": "magic"}).status_code == 400
    assert c.get("/api/stems/zzzz").status_code == 400
    assert c.get("/api/stems/0123456789abcdef").status_code == 404
    assert c.get("/api/stems/0123456789abcdef/envelopes.json").status_code == 404


def test_demo_song_resolves_to_bundled_track(app, monkeypatch):
    seen = {}
    monkeypatch.setattr(stems_api, "run_split", lambda song, engine="auto", fps=24: seen.update(song=song) or {
        "id": "0" * 16, "status": "done", "cached": False, "path": str(song), "engine": "x", "stems": [], "frames": 0, "fps": fps})
    c = TestClient(app)
    r = c.post("/api/stems", json={"audio_id": "demo"})
    assert r.status_code == 200
    _wait(c, r.json()["id"], timeout=10)
    assert Path(seen["song"]).name == "demo.wav"


def test_cli_stems_writes_the_same_files(tmp_path, capsys):
    song = _song(tmp_path)
    out = tmp_path / "out"
    assert main(["stems", str(song), "--out", str(out), "--engine", "bands"]) == 0
    text = capsys.readouterr().out
    assert "4 stems (librosa)" in text and (out / "stems.json").is_file() and (out / "drums.wav").is_file()
    env = json.loads((out / "stems.json").read_text(encoding="utf-8"))
    assert env["stems"] == list(stem_react.STEMS) and env["song"] == str(song)
    assert main(["stems", str(tmp_path / "nope.wav")]) == 1


def test_split_engine_aliases(tmp_path):
    song = _song(tmp_path)
    assert stem_react.split(song, tmp_path / "a", engine="bands")["engine"] == "librosa"
    with pytest.raises(ValueError):
        stem_react.split(song, tmp_path / "b", engine="magic")
    assert stem_react.engines_available()["bands"] is True


def test_desk_js_hooks():
    js = (STATIC / "ui_v6.js").read_text(encoding="utf-8")
    for needle in ("window.XENO_MACRO_SET", "/api/stems", "XENO_SET_STEMS(STEMS.names)", "splitting stems…", "xf-stems-status",
                   "XENO_STATE", "XENO_CURRENT_SONG", "data-song" if "dataset.song" not in js else "dataset.song", "/static/midi.js",
                   'page:"desk"', "macro:*"):
        assert needle in js, needle
    vj = (STATIC / "vj.html").read_text(encoding="utf-8")
    for needle in ("Use this song's stems", "/api/stems", "useStems", "searchParams.set('stems'", "/media/audio/", "midi.js",
                   "XenoMidi.init", "S.dance", "S.gain", "setStemGain", 'data-midi="strobe"', "midi-panel"):
        assert needle in vj, needle
    midi = (STATIC / "midi.js").read_text(encoding="utf-8")
    for needle in ("minilab3", "xeno-midi", "/ws/midi", "/api/midi/stream", "learn(", "exportJSON", "importJSON", "74,71,76,77,93,18,19,16",
                   "82,83,85,17", "num:28", "num:36+i", "num:44+i", "macro:intensity", "dance:1", "fx:step"):
        assert needle in midi, needle


# ---------------------------------------------------------------- stems by default: the background split
def _wait_bg(song, timeout=60):
    for _ in range(int(timeout * 10)):
        st = stems_api.split_status(song)
        if st["status"] not in ("queued", "running"):
            return st
        time.sleep(0.1)
    raise AssertionError("background split never finished")


def test_background_split_is_idempotent_and_walks_queued_running_done(app, tmp_path, monkeypatch):
    monkeypatch.setattr(stem_react, "demucs_available", lambda *a, **k: False)  # the band split, for speed
    c = TestClient(app)
    song = _song(tmp_path, sec=5.0)
    assert stems_api.split_status(song)["status"] == "none"
    stems_api._SLOT.acquire()  # hold the one split slot, so the job stays "queued" while we look at it
    try:
        first = stems_api.start_background_split(song)
        assert first["status"] == "queued" and len(first["id"]) == 16 and first["path"] is None and first["error"] is None
        assert first["engine"] == "auto" and first["song"] == "song.wav"
        thread = stems_api._THREADS[first["id"]]
        second = stems_api.start_background_split(song)  # idempotent: the same job, no second thread
        assert second["id"] == first["id"] and second["status"] == "queued"
        assert sum(1 for t in threading.enumerate() if t.name == f"stems-{first['id']}") == 1
        live = stems_api.split_status(song)
        assert live["status"] == "queued" and live["seconds"] >= 0
        legacy = c.get(f"/api/stems/{first['id']}").json()  # older pages (vj.html) only keep polling on "running"
        assert legacy["status"] == "running" and legacy["queued"] is True and "path" not in legacy
    finally:
        stems_api._SLOT.release()
    done = _wait_bg(song)
    assert done["status"] == "done" and done["engine"] == "librosa" and done["seconds"] > 0 and done["error"] is None
    assert Path(done["path"]).is_file() and done["path"] == str(stems_api.stems_path_for(song))
    assert done["stems"] == list(stem_react.STEMS) and done["roles"]["bass"] == "bass"
    thread.join(10)
    assert not thread.is_alive()
    again = stems_api.start_background_split(song)  # cached: done at once, no thread
    assert again["status"] == "done" and again["path"] == done["path"]
    assert not any(t.name == f"stems-{first['id']}" for t in threading.enumerate())
    stems_api._JOBS.clear()  # a new desk process reads the cache
    assert stems_api.split_status(song)["status"] == "done"
    assert c.get(f"/api/stems/{first['id']}").json()["count"] == 4
    # problems are reported, never raised (the hook sits inside /api/analyze)
    missing = stems_api.start_background_split(tmp_path / "nope.wav")
    assert missing["status"] == "error" and "nope.wav" in missing["error"] and missing["id"] is None
    assert stems_api.split_status(tmp_path / "nope.wav")["status"] == "error"
    assert stems_api.start_background_split(song, engine="magic")["status"] == "error"


def test_background_split_reports_a_failed_split_and_tries_again_next_time(app, tmp_path, monkeypatch):
    monkeypatch.setattr(stem_react, "demucs_available", lambda *a, **k: False)

    def boom(song, engine="auto", fps=24):
        raise RuntimeError("no stems today")

    monkeypatch.setattr(stems_api, "run_split", boom)
    song = _song(tmp_path, "bad.wav")
    assert stems_api.start_background_split(song)["status"] in ("queued", "running")
    st = _wait_bg(song)
    assert st["status"] == "error" and st["error"] == "no stems today" and st["seconds"] >= 0
    assert stems_api.start_background_split(song)["status"] in ("queued", "running")  # the next request retries
    assert _wait_bg(song)["status"] == "error"


def test_stems_for_route_follows_a_loaded_song(app, tmp_path, monkeypatch):
    """GET /api/stems/for/<audio id>: the desk's status line polls it; the id is what /api/analyze handed out."""
    monkeypatch.setattr(stem_react, "demucs_available", lambda *a, **k: False)
    from xenoform import ui

    c = TestClient(app)
    wav = _song(tmp_path, sec=5.0)
    up = c.post("/api/analyze", files={"file": ("five.wav", wav.read_bytes(), "audio/wav")})
    assert up.status_code == 200, up.text
    audio_id = up.json()["audio_id"]
    with ui._LOCK:
        path = ui._AUDIO[audio_id]
    r = c.get(f"/api/stems/for/{audio_id}")
    assert r.status_code == 200, r.text
    assert r.json()["status"] in ("none", "queued", "running", "done")  # "none" until ui.py's hook starts it
    stems_api.start_background_split(path)  # the hook's call (ui.py makes it from /api/analyze and /api/demo)
    j = c.get(f"/api/stems/for/{audio_id}").json()
    assert j["status"] in ("queued", "running", "done") and j["audio_id"] == audio_id and "path" not in j
    _wait_bg(path)
    j = c.get(f"/api/stems/for/{audio_id}").json()
    assert j["status"] == "done" and j["count"] == 4 and j["engine"] == "librosa" and j["seconds"] > 0
    assert j["envelopes"] == f"/api/stems/{j['id']}/envelopes.json" and j["stems"] == list(stem_react.STEMS)
    assert c.get(j["envelopes"]).status_code == 200
    assert c.get(f"/api/stems/{j['id']}").json()["status"] == "done"
    again = c.post("/api/stems", json={"audio_id": audio_id}).json()  # the drawer's fallback finds the same split
    assert again["id"] == j["id"] and again["status"] == "done" and again["cached"] is True
    assert c.get("/api/stems/for/demo").status_code == 200  # the bundled demo resolves too
    assert c.get("/api/stems/for/not-loaded-xyz").status_code == 404
    assert c.get("/api/stems/for/..%2F..").status_code in (400, 404)


def test_desk_status_line_polls_the_background_split():
    js = (STATIC / "ui_v6.js").read_text(encoding="utf-8")
    for needle in ("/api/stems/for/", "XENO_STATE", "splitting stems (", "XENO_SET_STEMS(STEMS.names)", "setInterval(pollStems",
                   "XENO_POLL_STEMS", 'STEMS.open?" open":""', "statusText()", "XENO_REQUEST_STEMS"):
        assert needle in js, needle
    assert 'STEMS.status?" open"' not in js  # the drawer no longer springs open because a split happens to be running
