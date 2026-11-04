"""A saved cut reopened whole (docs/UI_REVIEW.md N14, N10, N13): a finished Make keeps its guardrail notes beside the cut
(``notes.json``), ``GET /api/videos/{id}/reopen`` gives the job back as the cut's own screen read it (the notes, how long it
took and its breakdown, its tier, the stretch of the song) and registers it with the desk, and ``POST .../song`` loads the
cut's song again so Render works without choosing it; the desk clears a passage's label on a reopen."""
import json
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from xenoform import ui as ui_mod

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")


def _wav(path: Path, seconds: float, sr: int = 22050) -> Path:
    t = np.arange(int(seconds * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t) * (1 + np.sign(np.sin(2 * np.pi * 2 * t))) / 2  # a pulse twice a second
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    yield TestClient(ui_mod.create_app())
    with ui_mod._LOCK:
        for key in [k for k in ui_mod._JOBS if str(k).startswith("re")]:
            ui_mod._JOBS.pop(key, None)
        for key in [k for k in list(dict.keys(ui_mod._AUDIO)) if str(k).startswith("up")]:
            dict.pop(ui_mod._AUDIO, key, None)
        for key in [k for k in list(dict.keys(ui_mod._FEATURES)) if str(k).startswith("up")]:
            dict.pop(ui_mod._FEATURES, key, None)


def _saved_cut(tmp_path: Path, job_id: str = "re1", *, notes: bool = True, audio_id: str = "up1a2b3c4d") -> Path:
    folder = tmp_path / "jobs" / job_id
    (folder / "simple").mkdir(parents=True)
    (folder / "xenoform.mp4").write_bytes(b"cut")
    song = _wav(tmp_path / "uploads" / f"{audio_id}.wav", 8.0)
    (folder / "meta.json").write_text(json.dumps({"simple": True, "audio_id": audio_id, "song": "Glitch Out (30 s cut)",
                                                  "vibe": "neon-noir", "quality_tier": "draft", "aspect": "9:16",
                                                  "recipe": "xf1.abc"}), encoding="utf-8")
    (folder / "simple" / "simple.json").write_text(json.dumps({
        "audio_path": str(song), "window": {"song_start": 2.0, "length_s": 4.0}, "vibe": "neon-noir",
        "taste": {"lines": ["[taste] 1 neon-noir still left out of the pick (no-black-heart-or-dna)"]}}), encoding="utf-8")
    (folder / "took.json").write_text(json.dumps({"took_s": 528.9, "breakdown": {"morphs": 481.5, "cut": 35.7}}), encoding="utf-8")
    if notes:
        ui_mod._write_notes(folder, {"guardrails": {"applied": ["x"], "warnings": [], "messages": [
            "[taste] 1 neon-noir still left out of the pick (no-black-heart-or-dna)", "[qa] 1 chromatic aberration flag at 16.5s"]},
            "detail": "Cut ready in 528.9s"})
    return folder


def test_a_finished_make_keeps_its_guardrail_notes_beside_the_cut(desk, tmp_path, monkeypatch):
    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"the cut")
        on_progress("assemble", 1.0, "Cut ready in 3.0s")
        return {"mode": "simple", "seconds": 3.0, "taste_lines": ["[taste] the opener stays quiet (quiet-opener)"]}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    demo = desk.get("/api/demo").json()
    job_id = desk.post("/api/generate", json={**demo, "tiny": True}).json()["id"]
    for _ in range(200):
        job = desk.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done"
    kept = json.loads((tmp_path / "jobs" / job_id / ui_mod.NOTES_FILE).read_text(encoding="utf-8"))
    assert "[taste] the opener stays quiet (quiet-opener)" in kept["guardrails"]["messages"]
    assert kept["guardrails"]["messages"] == job["guardrails"]["messages"] and kept["detail"] == job["detail"]
    with ui_mod._LOCK:
        ui_mod._JOBS.pop(job_id, None)


def test_reopen_gives_the_cut_back_whole_and_registers_it_with_the_desk(desk, tmp_path):
    _saved_cut(tmp_path)
    got = desk.get("/api/videos/re1/reopen").json()
    job = got["job"]
    assert job["reopened"] is True and job["status"] == "done" and job["took_s"] == 528.9
    assert job["breakdown"] == {"morphs": 481.5, "cut": 35.7} and job["tier"] == "draft" and "path" not in job
    assert job["guardrails"]["messages"][1] == "[qa] 1 chromatic aberration flag at 16.5s"
    song = got["song"]
    assert song == {"audio_id": "up1a2b3c4d", "label": "Glitch Out (30 s cut)", "loaded": False, "bundled": None, "file": True,
                    "window": {"song_start": 2.0, "length_s": 4.0}, "seconds": 8.0}
    assert got["recipe"] == "xf1.abc" and got["vibe"] == "neon-noir" and got["detail"] == "Cut ready in 528.9s"
    # the desk knows the job now: the poll and the timeline's edits find it after a restart
    polled = desk.get("/api/jobs/re1").json()
    assert polled["guardrails"] == job["guardrails"] and polled["breakdown"] == job["breakdown"]
    assert desk.get("/api/videos/nope/reopen").status_code == 404


def test_a_cut_from_before_the_notes_file_reopens_with_its_taste_lines(desk, tmp_path):
    _saved_cut(tmp_path, "re2", notes=False)
    got = desk.get("/api/videos/re2/reopen").json()
    assert got["job"]["guardrails"]["messages"] == ["[taste] 1 neon-noir still left out of the pick (no-black-heart-or-dna)"]


def test_the_cuts_song_loads_again_from_its_record(desk, tmp_path):
    _saved_cut(tmp_path)
    r = desk.post("/api/videos/re1/song")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["audio_id"] == "up1a2b3c4d" and payload["title"] == "Glitch Out (30 s cut)" and payload["duration"] > 7
    with ui_mod._LOCK:
        assert Path(ui_mod._AUDIO["up1a2b3c4d"]).name == "up1a2b3c4d.wav" and "up1a2b3c4d" in ui_mod._FEATURES
    assert desk.get("/api/videos/re1/reopen").json()["song"]["loaded"] is True
    # a song gone from the machine is said plainly; a shipped song is the chip's to load
    gone = _saved_cut(tmp_path, "re3", audio_id="up9z9z9z9z")
    for p in (tmp_path / "uploads").glob("up9z9z9z9z.*"):
        p.unlink()
    r = desk.post("/api/videos/re3/song")
    assert r.status_code == 404 and "no longer on this machine" in r.json()["detail"]
    meta = json.loads((gone / "meta.json").read_text(encoding="utf-8"))
    (gone / "meta.json").write_text(json.dumps({**meta, "audio_id": "song-glitch-out"}), encoding="utf-8")
    assert desk.post("/api/videos/re3/song").status_code == 409
    assert desk.get("/api/videos/re3/reopen").json()["song"]["bundled"] == "glitch-out"


def test_the_desk_reopens_whole_and_clears_a_passages_label():
    opened = APP.split('} else if (act === "video-open") {')[1].split("} else if (act ===")[0]
    assert 'state.easy.fromSong = "";' in opened and "reopenWhole(row);" in opened
    for act in ("easy-showcase", "easy-again"):
        block = APP.split(f'}} else if (act === "{act}") {{')[1].split("} else if (act ===")[0]
        assert 'state.easy.fromSong = "";' in block, act
    fn = APP.split("async function reopenWhole(row)")[1].split("async function loadVideos")[0]
    assert "/reopen`" in fn and "tookBreakdown(data.job && data.job.breakdown)" in fn and "loadCutSong(id, data)" in fn
    assert "/song`, { method: \"POST\" }" in fn and "useBundledSong(song.bundled)" in fn and "adoptSession(payload)" in fn
    rerender = APP.split('} else if (act === "video-rerender") {')[1].split("} else if (act ===")[0]
    assert "loadCutSong(id)" in rerender and "cardNote" in rerender and "easyMake()" in rerender
    assert "card-note" in APP.split("function galleryPanel()")[1].split("async function loadVideos")[0]
