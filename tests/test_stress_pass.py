"""The stress pass of 29 Oct (Tys: "lets do a few polish passes and stress tests, make sure all the buttons are working
correctly and nothing is broken"): what the API and code sweeps broke, pinned so it stays fixed. Back to Demucs while
a pick of your own stems is still saving, a stems.json that is JSON but no record, a Python error's text on the Stems
line, FastAPI's field list for a malformed body, and the note after dropping clips, worded for the Morph row in use."""
import json
import os
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from xenoform import own_media, stem_react, stems_api, ui

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
SONG_ID = "stresspass1"


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """A fresh app, the stems cache in tmp, a 3 s song registered as a desk song, two stems of its length."""
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    monkeypatch.setattr(stem_react, "demucs_available", lambda *a, **k: False)
    monkeypatch.setattr(stems_api, "start_background_split", lambda song, **kw: {"id": None, "status": "queued", "engine": "auto",
                                                                                  "seconds": 0.0, "path": None, "error": None})
    stems_api._JOBS.clear()
    sr = 22050
    t = np.arange(sr * 3) / sr
    song = tmp_path / "song.wav"
    sf.write(str(song), (0.3 * np.sin(2 * np.pi * 110 * t)).astype(np.float32), sr)
    stems = {}
    for name, hz in (("kick.wav", 60), ("pad.wav", 440)):
        stems[name] = tmp_path / name
        sf.write(str(stems[name]), (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32), sr)
    with ui._LOCK:
        ui._AUDIO[SONG_ID] = song
    yield {"client": TestClient(ui.create_app(), raise_server_exceptions=False), "song": song, "stems": stems,
           "folder": tmp_path / "stems" / stems_api.song_hash(song)}
    with ui._LOCK:
        ui._AUDIO.pop(SONG_ID, None)
    stems_api._JOBS.clear()


def _files(stems):
    return [("files", (name, path.read_bytes(), "audio/wav")) for name, path in stems.items()]


def test_back_to_demucs_leaves_a_pick_that_is_still_saving_alone(desk):
    # the API sweep: a clear while a pick saved its files took the pick's folder from under it, a 500 on 16 of 20 tries
    c, folder = desk["client"], desk["folder"]
    folder.mkdir(parents=True)
    saving = folder / "own.abcd1234.part"
    saving.mkdir()
    (saving / "kick.wav").write_bytes(b"half")
    left = folder / "own.dead0000.part"  # a pick's folder from a desk that stopped mid-upload, long ago
    left.mkdir()
    old = time.time() - stems_api._OWN_PART_STALE_S - 60
    os.utime(left, (old, old))
    r = c.post("/api/stems/own/clear", json={"audio_id": SONG_ID})
    assert r.status_code == 200, r.text
    assert saving.is_dir() and (saving / "kick.wav").is_file() and not left.exists()


def test_a_stems_json_that_is_no_record_is_no_500(desk):
    c, folder = desk["client"], desk["folder"]
    folder.mkdir(parents=True)
    (folder / "stems.json").write_text("[1]", encoding="utf-8")
    sid = stems_api.song_hash(desk["song"])
    assert c.get(f"/api/stems/{sid}/kick.wav").status_code == 404
    st = c.get(f"/api/stems/for/{SONG_ID}").json()
    assert st["status"] == "error" and st["error"] == "its saved stems file could not be read"
    assert c.post("/api/stems/own/clear", json={"audio_id": SONG_ID}).status_code == 200
    (folder / "stems.json").write_text("[1]", encoding="utf-8")
    stems_api._JOBS.clear()
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"]))
    assert r.status_code == 200, r.text
    for _ in range(300):
        st = c.get(f"/api/stems/for/{SONG_ID}").json()
        if st["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert st["status"] == "done" and st["own"] is True and sorted(st["stems"]) == ["kick", "pad"], st


def test_the_stems_line_gets_a_reason_in_plain_words():
    reason = stems_api._reason
    assert reason(FileNotFoundError(2, "No such file", r"C:\Users\x\.cache\torch\hub\checkpoints\htdemucs.th")) == "htdemucs.th could not be read"
    assert reason(KeyError("vocals")) == reason(AttributeError("'list' object has no attribute 'get'"))
    assert "log" in reason(KeyError("vocals")) and "vocals" not in reason(KeyError("vocals"))
    assert reason(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")) == "it ran out of memory"
    assert reason(RuntimeError("no stems today")) == "no stems today"  # a sentence of our own goes through
    assert reason(ValueError(r"C:\a\b.wav is broken")) != r"C:\a\b.wav is broken"
    assert stems_api.own_stem_name("e\u0301clair.wav") == "\u00e9clair"  # a Mac's decomposed accent stays one letter


def test_a_malformed_body_gets_a_sentence_not_a_field_list():
    c = TestClient(ui.create_app())
    for r in (c.post("/api/songs/load", json=[]), c.post("/api/setup/download", json="film-pack"), c.post("/api/analyze", data={"x": "y"})):
        assert r.status_code == 422 and isinstance(r.json()["detail"], str) and r.json()["detail"].endswith("."), r.text
    assert c.get("/openapi.json").status_code == 404  # it was a 500 with a traceback
    bad = c.post("/api/batches", json={"body": {"audio_id": "demo"}, "count": "x"})
    assert bad.status_code == 400 and bad.json()["detail"].endswith(".")
    assert c.get("/api/jobs/nope12345").json()["detail"].startswith("No such cut.")  # mcp_tools reads the start


def test_dropped_files_are_counted_for_the_row_in_use(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path)
    files = []
    for i in range(own_media.MAX_ITEMS + 1):
        p = tmp_path / f"im{i:02d}.png"
        Image.new("RGB", (8, 8), (i, 0, 0)).save(p)
        files.append(("files", (p.name, p.read_bytes(), "image/png")))
    got = TestClient(ui.create_app()).post("/api/own", files=files).json()
    assert got["images"] == own_media.MAX_ITEMS and got["images_left"] == 1 and got["clips"] == 0 and got["max_clips"] == own_media.MAX_CLIPS
    assert "cut in on the beat" not in got["detail"]  # clips are never cut into an object cut (Tys, 28 Oct)
    up = APP.split("async function uploadOwn(files)", 1)[1].split("\n}\n", 1)[0]
    assert 'morphSource(state.easy) === "clips"' in up and "left out: a cut takes" in up


def test_the_docs_counts_match_the_code():
    # the docs sweep found counts that had drifted; these are the ones a reader checks first
    from xenoform import film_pack, songs_api

    man = film_pack.load_manifest()
    said = f"{len(man['clips'])} short clips from {film_pack._films(man)} public-domain films"
    assert said in (ROOT / "README.md").read_text(encoding="utf-8") and said in (ROOT / "docs" / "footage.md").read_text(encoding="utf-8")
    assert len(songs_api.manifest()) == 6 and "the six bundled songs" in (ROOT / "docs" / "CONTEST.md").read_text(encoding="utf-8")
    assert f"up to {own_media.MAX_CLIPS} clips" in (ROOT / "docs" / "footage.md").read_text(encoding="utf-8")


def test_the_morph_row_keeps_a_folder_for_each_kind_and_a_partial_pack_still_cuts():
    src = APP.split('act === "easy-source"', 1)[1].split("} else if (act ===", 1)[0]
    assert "ownBySource" in src and "kept[from]" in src and "state.easy.ownFolder = back.folder" in src
    pick = APP.split("async function pickFilmPack()", 1)[1].split("\n}\n", 1)[0]
    assert "!pack.present && count < 2" in pick and "of its ${pack.total} clips are here" in pick
