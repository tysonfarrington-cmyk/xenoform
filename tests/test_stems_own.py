"""Your own stems (Tys, 29 Oct: "there should also be a place where you can upload your own stems if you have them").
POST /api/stems/own saves them, builds the envelopes through the split registry (engine "user", own: true), and
POST /api/stems/own/clear goes back to the split; the desk's Stems line under the song shows it all."""
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from xenoform import stem_react, stems_api, ui

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
SONG_ID = "ownstems1"


def _tone(sec, freq, sr, gate=2.0):
    t = np.arange(int(sr * sec)) / sr
    return 0.3 * np.sin(2 * np.pi * freq * t) * (np.sin(2 * np.pi * gate * t) > 0)


def _kick(sec, sr):
    y = np.zeros(int(sr * sec))
    for k in range(int(sec * 2)):
        i = int(k * 0.5 * sr)
        y[i:i + 400] += np.random.default_rng(k).normal(0, 0.8, 400) * np.linspace(1, 0, 400)
    return y


def _write(path, y, sr):
    sf.write(str(path), y.astype(np.float32), sr)
    return path


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """A fresh app, the stems cache in tmp, a 3 s synthetic song registered as a desk song, and its three stems
    (a kick at 22050 Hz, an 808 at 44100 Hz to prove mixed rates are fine, a pad)."""
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    monkeypatch.setattr(stem_react, "demucs_available", lambda *a, **k: False)
    stems_api._JOBS.clear()
    sr = 22050
    kick, bass, pad = _kick(3.0, sr), _tone(3.0, 55, sr), _tone(3.0, 440, sr, gate=0.5)
    song = _write(tmp_path / "song.wav", kick + bass + pad, sr)
    stems = {"1 kick.wav": _write(tmp_path / "1 kick.wav", kick, sr),
             "02_808.wav": _write(tmp_path / "02_808.wav", np.repeat(bass, 2), 44100),
             "pad.wav": _write(tmp_path / "pad.wav", pad, sr)}
    with ui._LOCK:
        ui._AUDIO[SONG_ID] = song
    app = ui.create_app()
    yield {"client": TestClient(app), "song": song, "stems": stems, "sid": stems_api.song_hash(song), "root": tmp_path / "stems"}
    with ui._LOCK:
        ui._AUDIO.pop(SONG_ID, None)
    stems_api._JOBS.clear()


def _files(stems, names=None):
    return [("files", (name, path.read_bytes(), "audio/wav")) for name, path in stems.items() if names is None or name in names]


def _wait(client, audio_id=SONG_ID, timeout=60):
    for _ in range(int(timeout * 10)):
        j = client.get(f"/api/stems/for/{audio_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.1)
    raise AssertionError("the stems never finished")


def test_own_stems_take_the_splits_place(desk):
    c, song, sid = desk["client"], desk["song"], desk["sid"]
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"]))
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["own"] is True and first["engine"] == "user" and first["status"] in ("queued", "running", "done")
    assert first["stems"] == ["kick", "808", "pad"]  # the leading index and its separators dropped, the order kept
    assert first["roles"] == {"kick": "drums", "808": "bass", "pad": "other"}
    assert "path" not in first and "own_token" not in first
    j = _wait(c)
    assert j["status"] == "done", j
    assert j["own"] is True and j["engine"] == "user" and j["count"] == 3 and j["stems"] == ["kick", "808", "pad"]
    assert j["roles"]["808"] == "bass" and j["seconds"] > 0 and j["audio_id"] == SONG_ID
    out = desk["root"] / sid / "stems.json"
    assert out.is_file() and stems_api.stems_path_for(song) == out  # what the Make reads
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["own"] is True and env["engine"] == "user" and env["stems"] == ["kick", "808", "pad"]
    assert len(env["kick"]) == env["frames"] == len(env["808"]) and env["frames"] >= 24 * 2
    assert "drum_hits" in env and "drums" in env and "bass" in env and "other" in env
    assert sorted(p.name for p in (desk["root"] / sid / "own").iterdir()) == ["808.wav", "kick.wav", "pad.wav"]
    assert env["files"]["808"].endswith("808.wav")
    assert c.get(f"/api/stems/{sid}/kick.wav").status_code == 200
    assert c.get(j["envelopes"]).json()["own"] is True
    stems_api._JOBS.clear()  # a desk restart reads the file: still the user's stems
    again = c.get(f"/api/stems/for/{SONG_ID}").json()
    assert again["status"] == "done" and again["own"] is True and again["engine"] == "user"
    assert stems_api.start_background_split(song)["status"] == "done"  # a reload of the song does not split over them


def test_a_second_set_replaces_the_first_and_names_stay_unique(desk):
    c, sid = desk["client"], desk["sid"]
    assert c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"])).status_code == 200
    _wait(c)
    kick = desk["stems"]["1 kick.wav"].read_bytes()
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID},
               files=[("files", ("3 Kick.wav", kick, "audio/wav")), ("files", ("kick.wav", kick, "audio/wav")),
                      ("files", ("song.wav", kick, "audio/wav"))])
    assert r.status_code == 200, r.text
    assert r.json()["stems"] == ["Kick", "kick 2", "song stem"]  # no two alike, no stems.json key
    j = _wait(c)
    assert j["stems"] == ["Kick", "kick 2", "song stem"] and j["roles"]["song stem"] == "other"
    assert sorted(p.name for p in (desk["root"] / sid / "own").iterdir()) == ["Kick.wav", "kick 2.wav", "song stem.wav"]
    env = json.loads((desk["root"] / sid / "stems.json").read_text(encoding="utf-8"))
    assert env["song"] == str(desk["song"]) and len(env["song stem"]) == env["frames"]  # the song path survived the name


def test_a_wrong_length_stem_is_refused_by_name(desk, tmp_path):
    c = desk["client"]
    long = _write(tmp_path / "7 strings.wav", _tone(6.0, 220, 22050), 22050)
    files = _files(desk["stems"], ["1 kick.wav"]) + [("files", ("7 strings.wav", long.read_bytes(), "audio/wav"))]
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=files)
    assert r.status_code == 400
    assert "strings.wav" in r.json()["detail"] and "6.0 s" in r.json()["detail"] and "3.0 s" in r.json()["detail"]
    assert not (desk["root"] / desk["sid"] / "own").exists() and not (desk["root"] / desk["sid"] / "own.part").exists()
    assert c.get(f"/api/stems/for/{SONG_ID}").json()["status"] == "none"  # nothing changed hands


def test_the_other_refusals_name_the_file_and_the_count(desk):
    c = desk["client"]
    kick = desk["stems"]["1 kick.wav"].read_bytes()
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert r.status_code == 400 and "notes.txt" in r.json()["detail"]
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=[("files", ("broken.wav", b"RIFF not audio at all", "audio/wav"))])
    assert r.status_code == 400 and "broken.wav" in r.json()["detail"] and "decode" in r.json()["detail"]
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=[("files", (f"{i} s.wav", kick, "audio/wav")) for i in range(33)])
    assert r.status_code == 400 and "33" in r.json()["detail"] and "32" in r.json()["detail"]
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID})
    assert r.status_code == 400 and "No audio files" in r.json()["detail"]
    r = c.post("/api/stems/own", data={"audio_id": "not-loaded-xyz"}, files=[("files", ("1 kick.wav", kick, "audio/wav"))])
    assert r.status_code == 404
    assert c.get(f"/api/stems/for/{SONG_ID}").json()["status"] == "none"


def test_the_size_cap_names_the_file(desk, monkeypatch):
    c = desk["client"]
    monkeypatch.setattr(ui, "_MAX_UPLOAD_BYTES", 1024)
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"], ["pad.wav"]))
    assert r.status_code == 413 and "pad.wav" in r.json()["detail"]


def _fake_split(folder, engine="demucs:htdemucs"):
    n = 72
    rec = {"fps": 24, "engine": engine, "frames": n, "stems": ["drums", "bass", "other", "vocals"],
           "roles": {s: s for s in ("drums", "bass", "other", "vocals")}, "seconds": 9.0, "song": "song.wav", "files": {},
           **{s: [0.5] * n for s in ("drums", "bass", "other", "vocals")}, "drum_hits": [0.5], "drum_strong": []}
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "stems.json").write_text(json.dumps(rec), encoding="utf-8")
    return rec


def test_clear_restores_the_split_kept_aside(desk):
    c, sid = desk["client"], desk["sid"]
    folder = desk["root"] / sid
    _fake_split(folder)  # Demucs got there first
    before = c.get(f"/api/stems/for/{SONG_ID}").json()
    assert before["status"] == "done" and before["own"] is False and before["engine"] == "demucs:htdemucs"
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"]))
    assert r.status_code == 200, r.text
    assert (folder / "stems.split.json").is_file() and not (folder / "stems.json").is_file()
    j = _wait(c)
    assert j["own"] is True and j["split_engine"] == "demucs:htdemucs"  # the desk's Back button knows where back is
    assert json.loads((folder / "stems.json").read_text(encoding="utf-8"))["own"] is True
    r = c.post("/api/stems/own/clear", json={"audio_id": SONG_ID})
    assert r.status_code == 200, r.text
    back = r.json()
    assert back["status"] == "done" and back["own"] is False and back["engine"] == "demucs:htdemucs" and back["count"] == 4
    assert not (folder / "own").exists() and not (folder / "stems.split.json").exists()
    assert json.loads((folder / "stems.json").read_text(encoding="utf-8"))["stems"] == ["drums", "bass", "other", "vocals"]
    assert c.get(f"/api/stems/for/{SONG_ID}").json()["own"] is False
    assert stems_api.stems_path_for(desk["song"]) == folder / "stems.json"


def test_clear_with_nothing_kept_queues_the_split_again(desk, monkeypatch):
    c, sid = desk["client"], desk["sid"]
    assert c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"])).status_code == 200
    _wait(c)
    asked = []
    monkeypatch.setattr(stems_api, "start_background_split", lambda song, **kw: asked.append(Path(song)) or {
        "id": sid, "status": "queued", "engine": "auto", "seconds": 0.0, "path": None, "error": None, "song": Path(song).name})
    r = c.post("/api/stems/own/clear", json={"audio_id": SONG_ID})
    assert r.status_code == 200 and r.json()["status"] == "queued" and r.json()["own"] is False
    assert asked == [desk["song"]] and not (desk["root"] / sid / "stems.json").exists()
    # clearing when nothing of the user's is in place touches nothing and still answers
    r = c.post("/api/stems/own/clear", json={"audio_id": SONG_ID})
    assert r.status_code == 200 and len(asked) == 2


def test_a_split_that_finishes_after_own_stems_is_kept_aside(desk):
    """The race: Demucs is running for the song when the user's stems arrive. The split's thread finishes on its
    own, writes stems.split.json instead of over the user's file, and leaves the registry entry to the own stems."""
    song, sid = desk["song"], desk["sid"]
    with stems_api._LOCK:
        stems_api._JOBS[sid] = {"id": sid, "status": "done", "own": True, "own_token": "t", "engine": "user", "stems": ["kick"]}
    rec = stems_api.run_split(song, engine="bands")
    assert rec["kept_aside"] is True and Path(rec["path"]).name == "stems.split.json" and Path(rec["path"]).is_file()
    assert not (desk["root"] / sid / "stems.json").exists()
    assert stems_api._update_split(sid, status="done", engine="librosa") is False
    assert stems_api._JOBS[sid]["engine"] == "user" and stems_api._JOBS[sid]["status"] == "done"
    assert stems_api._update_own(sid, "wrong-token", status="error") is False and stems_api._update_own(sid, "t", seconds=1) is True


def test_own_stem_names_are_cleaned():
    n = stems_api.own_stem_name
    assert n("1 Drums.wav") == "Drums" and n("02_bass.wav") == "bass" and n("Lead Vocals.wav") == "Lead Vocals"
    assert n("0 Lead Vocals.wav") == "Lead Vocals" and n("10 Woodwinds.wav") == "Woodwinds" and n("3) Guitar.flac") == "Guitar"
    assert n("808.wav") == "808" and n("song.wav") == "song stem" and n("frames.mp3") == "frames stem"
    assert n(" .wav") == "stem" and n("a/b?c.wav") == "b c"
    # a DAW in another language keeps its names; a leading 808 is a name, not an index; a Windows device name is not a file name
    assert n("Батарея.wav") == "Батарея" and n("ドラム.wav") == "ドラム" and n("Batería.wav") == "Batería" and n("808 Bass.wav") == "808 Bass"
    assert n("con.wav") == "con stem" and n("C:\\Users\\tyson\\My Stems\\1 Drums.wav") == "Drums"
    long_pair = stems_api.own_names(["x" * 70 + ".wav", "x" * 70 + "y.wav"])
    assert long_pair[0] != long_pair[1] and all(len(name) <= 64 for name in long_pair)  # both within the wav route's rule
    assert stems_api.own_names(["1 kick.wav", "kick.wav", "song.wav"]) == ["kick", "kick 2", "song stem"]
    assert all(stem_react.role(n(f)) == r for f, r in (("0 Lead Vocals.wav", "vocals"), ("1 Drums.wav", "drums"),
                                                      ("5 Percussion.wav", "drums"), ("2 Bass.wav", "bass"), ("3 Guitar.wav", "other")))


def test_slice_keeps_any_number_of_named_stems(tmp_path):
    n = 24 * 4
    src = {"fps": 24, "engine": "user", "own": True, "frames": n, "stems": ["Kick", "808", "Lead Vocals"],
           "roles": {"Kick": "drums", "808": "bass", "Lead Vocals": "vocals"}, "Kick": [0.1] * n, "808": [0.2] * n,
           "Lead Vocals": [0.3] * n, "drums": [0.1] * n, "bass": [0.2] * n, "vocals": [0.3] * n, "drum_hits": [0.5, 2.5],
           "drum_strong": [2.5], "song": "C:/full.wav", "files": {"Kick": "k.wav"}, "seconds": 1.0}
    p = tmp_path / "stems.json"
    p.write_text(json.dumps(src), encoding="utf-8")
    cut = tmp_path / "cut.wav"
    cut.write_bytes(b"RIFF....WAVE")
    d = json.loads(stems_api.slice_stems(p, 2.0, 1.0, cut).read_text(encoding="utf-8"))
    assert d["frames"] == 24 and len(d["Lead Vocals"]) == 24 == len(d["808"]) and d["stems"] == src["stems"]
    assert d["roles"] == src["roles"] and d["own"] is True and d["engine"] == "user" and d["drum_hits"] == [0.5]


def test_cli_stems_takes_your_own(tmp_path, capsys):
    from xenoform.cli import main

    sr = 22050
    song = _write(tmp_path / "song.wav", _kick(2.0, sr) + _tone(2.0, 55, sr), sr)
    a = _write(tmp_path / "1 kick.wav", _kick(2.0, sr), sr)
    b = _write(tmp_path / "2 sub.wav", _tone(2.0, 55, sr), sr)
    out = tmp_path / "out"
    assert main(["stems", str(song), "--own", str(a), str(b), "--out", str(out)]) == 0
    assert "2 stems (user)" in capsys.readouterr().out
    env = json.loads((out / "stems.json").read_text(encoding="utf-8"))
    assert env["stems"] == ["kick", "sub"] and env["roles"] == {"kick": "drums", "sub": "bass"} and env["own"] is True
    assert main(["stems", str(song), "--own", str(tmp_path / "nope.wav")]) == 1


def test_cli_own_keeps_the_routes_rules(tmp_path, monkeypatch, capsys):
    """The command line refuses what the route refuses (a stem of the wrong length), numbers a repeated name, and
    without --out keeps a split's file aside in the cache folder the way the route does."""
    from xenoform.cli import main

    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    sr = 22050
    song = _write(tmp_path / "song.wav", _kick(2.0, sr) + _tone(2.0, 55, sr), sr)
    a = _write(tmp_path / "1 kick.wav", _kick(2.0, sr), sr)
    b = _write(tmp_path / "kick.wav", _tone(2.0, 55, sr), sr)
    long = _write(tmp_path / "long.wav", _tone(9.0, 55, sr), sr)
    assert main(["stems", str(song), "--own", str(a), str(long), "--out", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out" / "stems.json").exists()
    folder = tmp_path / "stems" / stems_api.song_hash(song)
    _fake_split(folder)  # a Demucs file in the cache
    assert main(["stems", str(song), "--own", str(a), str(b)]) == 0
    assert "2 stems (user)" in capsys.readouterr().out
    env = json.loads((folder / "stems.json").read_text(encoding="utf-8"))
    assert env["stems"] == ["kick", "kick 2"] and env["own"] is True and env["split_engine"] == "demucs:htdemucs"
    assert json.loads((folder / "stems.split.json").read_text(encoding="utf-8"))["engine"] == "demucs:htdemucs"


# ------------------------------------------------------------------------------------------------ two picks, a clear, a split at once


def _slow_envelopes(monkeypatch, hold):
    """stem_react.envelopes that holds the first stem open for ``hold`` s first, as librosa does while it decodes
    (on Windows the file cannot be deleted meanwhile)."""
    orig = stem_react.envelopes

    def slow(stems, **kw):
        first = next(v for k, v in stems.items() if k != "engine")
        with open(first, "rb"):
            time.sleep(hold)
        return orig(stems, **kw)

    monkeypatch.setattr(stem_react, "envelopes", slow)


def _leftovers(folder):
    return sorted(p.name for p in folder.iterdir() if p.name.startswith("own") or p.suffix == ".part")


def test_a_second_pick_while_the_first_is_still_read_takes_its_turn(desk, monkeypatch):
    """The user picked the wrong files and picks again while the first set is being read: no 500, no lost set.
    The second request saves into a folder of its own, its build waits for the first to let go, and the first
    writes nothing."""
    c, sid = desk["client"], desk["sid"]
    _slow_envelopes(monkeypatch, 1.0)
    first = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"], ["1 kick.wav", "02_808.wav"]))
    assert first.status_code == 200, first.text
    time.sleep(0.3)
    second = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"], ["pad.wav"]))
    assert second.status_code == 200, second.text
    assert second.json()["stems"] == ["pad"] and second.json()["status"] in ("queued", "running")
    j = _wait(c)
    assert j["status"] == "done" and j["own"] is True and j["stems"] == ["pad"], j
    folder = desk["root"] / sid
    env = json.loads((folder / "stems.json").read_text(encoding="utf-8"))
    assert env["stems"] == ["pad"] and sorted(p.name for p in (folder / "own").iterdir()) == ["pad.wav"]
    assert _leftovers(folder) == ["own"]  # no own.*.part, no stems.own.json.part
    assert sid not in stems_api._OWN_THREADS


def test_two_picks_at_the_same_moment_both_answer(desk):
    import threading

    c, sid = desk["client"], desk["sid"]
    kick = desk["stems"]["1 kick.wav"].read_bytes()
    results = {}

    def post(tag):
        results[tag] = c.post("/api/stems/own", data={"audio_id": SONG_ID},
                              files=[("files", (f"{tag}{i}.wav", kick, "audio/wav")) for i in range(1, 4)])

    threads = [threading.Thread(target=post, args=(tag,)) for tag in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results["a"].status_code == 200 and results["b"].status_code == 200, (results["a"].text, results["b"].text)
    j = _wait(c)
    assert j["status"] == "done" and j["stems"] in (["a1", "a2", "a3"], ["b1", "b2", "b3"]), j
    folder = desk["root"] / sid
    assert sorted(p.stem for p in (folder / "own").iterdir()) == j["stems"]  # one set, whole
    assert _leftovers(folder) == ["own"]


def test_back_to_the_split_during_a_build_leaves_nothing_behind(desk, monkeypatch):
    c, sid = desk["client"], desk["sid"]
    _slow_envelopes(monkeypatch, 1.0)
    asked = []
    monkeypatch.setattr(stems_api, "start_background_split", lambda song, **kw: asked.append(Path(song)) or {
        "id": sid, "status": "queued", "engine": "auto", "seconds": 0.0, "path": None, "error": None, "song": Path(song).name})
    assert c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"])).status_code == 200
    time.sleep(0.3)
    r = c.post("/api/stems/own/clear", json={"audio_id": SONG_ID})
    assert r.status_code == 200 and r.json()["status"] == "queued" and asked == [desk["song"]]
    folder = desk["root"] / sid
    assert not (folder / "own").exists() and not (folder / "stems.json").exists() and _leftovers(folder) == []
    time.sleep(0.5)  # the build's thread has long let go: still nothing written
    assert not (folder / "stems.json").exists() and sid not in stems_api._OWN_THREADS


def test_the_split_and_the_own_build_do_not_share_a_part_file(desk, monkeypatch):
    """The split finishing in the same instant as the own build: each writes its own temporary file, the split
    goes to stems.split.json and the user's stems.json lands."""
    c, song, sid = desk["client"], desk["song"], desk["sid"]
    orig = stem_react.save_envelopes

    def slow_save(env, path):
        p = orig(env, path)
        if env.get("own"):
            time.sleep(1.0)  # the own thread between writing its part file and moving it into place
        return p

    monkeypatch.setattr(stem_react, "save_envelopes", slow_save)
    assert c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=_files(desk["stems"], ["1 kick.wav"])).status_code == 200
    time.sleep(0.4)
    rec = stems_api.run_split(song, engine="bands")
    assert rec["kept_aside"] is True and Path(rec["path"]).name == "stems.split.json"
    j = _wait(c)
    assert j["status"] == "done" and j["own"] is True and j["stems"] == ["kick"], j
    folder = desk["root"] / sid
    assert json.loads((folder / "stems.json").read_text(encoding="utf-8"))["own"] is True and (folder / "stems.split.json").is_file()
    assert not list(folder.glob("*.part"))


def test_a_stem_named_in_another_alphabet_keeps_its_name_and_its_wav_route(desk):
    c, sid = desk["client"], desk["sid"]
    kick = desk["stems"]["1 kick.wav"].read_bytes()
    r = c.post("/api/stems/own", data={"audio_id": SONG_ID}, files=[("files", ("1 Батарея.wav", kick, "audio/wav")), ("files", ("Batería.wav", kick, "audio/wav"))])
    assert r.status_code == 200, r.text
    assert r.json()["stems"] == ["Батарея", "Batería"]
    j = _wait(c)
    assert j["status"] == "done" and j["stems"] == ["Батарея", "Batería"]
    assert c.get(f"/api/stems/{sid}/Батарея.wav").status_code == 200
    assert sorted(p.name for p in (desk["root"] / sid / "own").iterdir()) == ["Batería.wav", "Батарея.wav"]


# ------------------------------------------------------------------------------------------------ the desk


def _fn(start, end):
    return APP.split(start, 1)[1].split(end, 1)[0]


def test_the_song_step_has_the_stems_line_with_its_two_controls():
    row = _fn("const songBlock = songSet", "const proto = easyLengthIsProto(easy);")
    assert "${stemsLine()}" in row and 'data-act="easy-demo"' in row  # inside the songrow; the Bundled demo button untouched
    line = _fn("function stemsLine()", "function paintStemsText(")
    assert 'id="stems-line"' in line and 'class="note stems-line"' in line
    assert 'data-act="easy-own-stems"' in line and "Use your own stems" in line and "type=\"file\" multiple" in line
    assert 'data-act="easy-own-stems-clear"' in line and "Back to Demucs" in line and "Back to the split" in line
    for text in ("Stems: splitting with Demucs…", "Stems: splitting (band split)…", "of your own:", "from ${engine.startsWith(\"demucs\") ? \"Demucs\" : \"the band split\"}",
                 "Stems: not split ("):
        assert text in _fn("function stemsText(st)", "function stemsLine()"), text


def test_the_stems_line_polls_by_id_and_redraws_only_on_a_new_shape():
    load = _fn("async function loadStems(force)", "async function uploadOwnStems(")
    assert "/api/stems/for/" in load and "2000" in load and "if (!state || !state.audioId || !state.easy || !state.easy.song) return;" in load
    assert "stemsShape(before) === stemsShape(st)" in load and "paintStemsText(stemsText(st))" in load and "if (line) render();" in load
    assert "state.audioId !== id) return;" in load  # a poll for the song before is dropped
    assert "stemsBusy(st) && line" in load  # the poll stops when the line leaves the screen
    paint = _fn("function paintStemsText(text)", "async function loadStems(")
    assert 'getElementById("stems-line")' in paint and 'querySelector(".stems-text")' in paint and "textContent" in paint
    up = _fn("async function uploadOwnStems(files)", "async function clearOwnStems(")
    assert '"/api/stems/own"' in up and 'body.append("audio_id", id)' in up and "Stems: reading your ${files.length} file" in up
    assert "note: data.detail" in up  # the route's words go into the line
    assert "noteAt: Date.now()" in up and "stemsBusy(was) ? 2000 : STEMS_NOTE_MS" in up  # a refusal keeps the split's poll going under it
    assert up.count("loadStems(true)") == 1 and "stemsSeq += 1" in up  # one poll chain after a pick (stemsLine() starts it), older answers dropped
    assert "stemsPending" in load and "seq !== stemsSeq) return;" in load and "before.noteAt" in load
    assert "!stemsTimer && !stemsPending" in _fn("function stemsLine()", "function paintStemsText(")  # a redraw mid-poll starts no second chain
    assert '"/api/stems/own/clear"' in _fn("async function clearOwnStems()", "// The library counts")


def test_the_fine_tune_lanes_follow_the_stems_in_use():
    """ui_v6.js draws the Stem reactions lanes; they must follow Use your own stems and Back to Demucs, not only
    the first split, and the knob strip must not poll the route a second time beside the Stems line."""
    v6 = (STATIC / "ui_v6.js").read_text(encoding="utf-8")
    assert "window.XENO_STEMS_UPDATE=" in v6 and "window.XENO_STEMS_FOR" in v6 and "STEMS.key!==key" in v6
    assert "XENO_SET_STEMS(STEMS.names)" in v6 and "your own" in v6
    assert "window.XENO_STEMS_FOR = (id) => stemsFor(id);" in APP
    for fn in ("async function loadStems(force)", "async function uploadOwnStems(files)", "async function clearOwnStems()"):
        assert "tellKnobsStems(" in _fn(fn, "\n}\n"), fn
    assert 'act === "easy-own-stems-clear"' in APP and 'target.dataset.act === "easy-own-stems"' in APP and "uploadOwnStems(Array.from(target.files" in APP
    css = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert ".stems-line label.text" in css


def test_the_docs_say_where_your_own_stems_go():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "your own stems" in readme and "Stems line under the song" in readme
    stems_doc = (ROOT / "docs" / "stems.md").read_text(encoding="utf-8")
    assert "## Your own stems" in stems_doc and "/api/stems/own/clear" in stems_doc and "1.5 s" in stems_doc
    unreleased = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 0.3.3")[1].split("## 0.3.2")[0]
    assert "**Your own stems**" in unreleased and "/api/stems/own" in unreleased and "tests/test_stems_own.py" in unreleased
