"""Perform (docs/UI_REVIEW.md 6.5, perform_api): the cut a control view opens (/vj?job=), the song strip it falls back
to, and the live takes: chunks taken in order, a take finished into an mp4 beside its webm, the listings that show it.
Nothing here needs a browser or a GPU; the remux needs ffmpeg."""
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")


@pytest.fixture
def desk(tmp_path, monkeypatch):
    import xenoform.ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    return TestClient(ui_mod.create_app()), tmp_path


def _webm(path: Path, seconds: float = 1.0) -> Path:
    """A webm like a browser's take: VP8 picture, Opus sound."""
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=160x90:d={seconds}:r=30",
                           "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
                           "-c:v", "libvpx", "-b:v", "300k", "-c:a", "libopus", str(path)])
    return path


def _start(client, **body) -> dict:
    r = client.post("/api/perform/takes", json={"width": 160, "height": 90, "fps": 30, "title": "Glitch Out", **body})
    assert r.status_code == 200, r.text
    return r.json()


def _chunk(client, tid: str, seq: int, data: bytes):
    return client.post(f"/api/perform/takes/{tid}/chunk?seq={seq}", content=data, headers={"Content-Type": "application/octet-stream"})


@needs_ffmpeg
def test_take_chunks_in_order_then_an_mp4_beside_the_webm(desk, tmp_path):
    client, work = desk
    data = _webm(tmp_path / "src.webm").read_bytes()
    t = _start(client, job="31680167", start_pos=12.5)
    assert t["status"] == "recording" and t["kind"] == "take" and t["start_pos"] == 12.5
    parts = [data[: len(data) // 3], data[len(data) // 3: 2 * len(data) // 3], data[2 * len(data) // 3:]]
    for seq, part in enumerate(parts):
        r = _chunk(client, t["id"], seq, part)
        assert r.status_code == 200 and r.json()["chunks"] == seq + 1
    again = _chunk(client, t["id"], 1, parts[1])  # a retry after a lost answer is taken once
    assert again.status_code == 200 and again.json().get("duplicate") is True
    assert _chunk(client, t["id"], 5, b"x").status_code == 409  # a gap is refused: the file stays a playable prefix
    folder = work / "takes" / t["id"]
    assert (folder / "take.webm").read_bytes() == data
    done = client.post(f"/api/perform/takes/{t['id']}/finish?wait=true", json={"end_pos": 13.5}).json()
    assert done["status"] == "done", done
    assert done["mp4"] and 0.8 < done["seconds"] < 1.3 and done["size"] == "160x90"
    mp4 = client.get(done["mp4"])
    assert mp4.status_code == 200 and mp4.content[4:8] == b"ftyp"
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "csv=p=0", str(folder / "take.mp4")],
                           capture_output=True, text=True).stdout
    assert "h264,video" in probe and "aac,audio" in probe
    assert client.get(done["webm"]).status_code == 200
    assert _chunk(client, t["id"], 3, b"late").status_code == 409  # a finished take takes no more
    assert client.post(f"/api/perform/takes/{t['id']}/finish?wait=true").json()["status"] == "done"  # asking twice is harmless


@needs_ffmpeg
def test_takes_are_listed_and_sit_among_the_cuts_in_my_videos(desk, tmp_path):
    client, work = desk
    data = _webm(tmp_path / "src.webm").read_bytes()
    done = _start(client)
    _chunk(client, done["id"], 0, data)
    client.post(f"/api/perform/takes/{done['id']}/finish?wait=true")
    running = _start(client, title="Still going")
    _chunk(client, running["id"], 0, data[:500])
    takes = {t["id"]: t for t in client.get("/api/perform/takes").json()["takes"]}
    assert takes[done["id"]]["status"] == "done" and takes[running["id"]]["status"] == "recording"
    videos = client.get("/api/videos").json()["videos"]
    rows = [v for v in videos if v.get("kind") == "take"]
    assert [r["id"] for r in rows] == [done["id"]]  # a take still recording is not a video yet
    row = rows[0]
    assert row["song"] == "Glitch Out" and row["url"].endswith("/video.mp4") and row["aspect"] == "16:9" and row["tier"] == "take"
    assert client.get(row["url"]).status_code == 200


@needs_ffmpeg
def test_a_take_cut_short_is_found_and_finished(desk, tmp_path, monkeypatch):
    client, work = desk
    import xenoform.perform_api as P

    data = _webm(tmp_path / "src.webm", seconds=1.5).read_bytes()
    t = _start(client)
    _chunk(client, t["id"], 0, data[: len(data) * 2 // 3])  # the browser crashed after this chunk
    monkeypatch.setattr(P, "STALE_S", 0.0)
    time.sleep(0.05)
    listed = {x["id"]: x for x in client.get("/api/perform/takes").json()["takes"]}
    assert listed[t["id"]]["status"] == "interrupted"
    assert listed[t["id"]]["url"].endswith("/take.webm")
    done = client.post(f"/api/perform/takes/{t['id']}/finish?wait=true").json()
    assert done["status"] == "done" and done["seconds"] > 0.3  # what reached the desk is kept


def test_take_routes_check_their_ids(desk):
    client, _ = desk
    assert client.get("/api/perform/takes/NOTAHEXID").status_code == 400
    assert client.get("/api/perform/takes/0123456789").status_code == 404
    assert _chunk(client, "0123456789", 0, b"x").status_code == 404
    assert client.get("/api/perform/takes/0123456789/video.mp4").status_code == 404
    t = _start(client)
    assert client.get(f"/api/perform/takes/{t['id']}/video.mp4").status_code == 404  # no mp4 before Stop
    assert client.get(f"/api/perform/takes/{t['id']}/take.webm").status_code == 404  # no picture before a chunk
    r = client.post(f"/api/perform/takes/{t['id']}/finish?wait=true").json()
    assert r["status"] == "error" and "webm is kept" in r["error"]


def test_vj_serves_both_views(desk):
    client, _ = desk
    for url in ("/vj", "/vj?out=1", "/vj?job=31680167", "/vj?job=../../etc"):
        r = client.get(url)
        assert r.status_code == 200 and "vj_control.js" in r.text and "xeno-rig" in r.text
    assert client.get("/static/vj_control.js").status_code == 200 and client.get("/static/vj_control.css").status_code == 200


def _job(work: Path, job_id: str = "abc123", *, audio: Path | None = None, clips_elsewhere: bool = False) -> Path:
    """A finished cut as the desk leaves it: xenoform.mp4, meta.json, simple/simple.json and its clips."""
    folder = work / "jobs" / job_id
    (folder / "simple").mkdir(parents=True)
    (folder / "xenoform.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
    (folder / "meta.json").write_text(json.dumps({"simple": True, "song": "Test song", "vibe": "cosmic", "aspect": "16:9"}), encoding="utf-8")
    clips = []
    for k in range(3):
        (folder / "simple" / f"local{k:02d}.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42clip%d" % k)
        clips.append(f"C:/somewhere/else/local{k:02d}.mp4" if clips_elsewhere else str(folder / "simple" / f"local{k:02d}.mp4"))
    beats = [round(0.5 * i, 3) for i in range(13)]
    info = {"shots": [{"index": 0, "start": 0.0, "end": 2.0, "section": "build", "speed": 2.0, "clip": 0},
                      {"index": 1, "start": 2.0, "end": 4.0, "section": "drop", "drop_run": 0, "heat": 1.0, "clip": 1},
                      {"index": 2, "start": 4.0, "end": 6.0, "section": "drop", "drop_run": 0, "heat": 1.0, "clip": 2}],
            "stills": ["cosmic/00_orb_iridescent.jpg", "cosmic/01_moon.jpg", "cosmic/02_star.jpg", "cosmic/03_comet.jpg"],
            "clips": clips, "beats": beats, "drop": 2.0, "audio_path": str(audio) if audio else ""}
    (folder / "simple" / "simple.json").write_text(json.dumps(info), encoding="utf-8")
    return folder


def test_perform_job_gives_the_cuts_clips_song_and_sections(desk, tmp_path):
    client, work = desk
    song = tmp_path / "song.wav"
    song.write_bytes(b"RIFF....WAVEfmt ")
    _job(work, audio=song)
    j = client.get("/api/perform/job/abc123").json()
    assert j["title"] == "Test song" and j["vibe"] == "cosmic" and j["duration"] == 6.0 and j["drop"] == 2.0
    assert [c["url"] for c in j["clips"]] == [f"/api/perform/job/abc123/clip/{k}" for k in range(3)]
    assert j["clips"][0]["to"] == "moon" and j["clips"][0]["name"] == "orb iridescent → moon"  # a pad is named for its object
    assert [(s["clip"], s["speed"]) for s in j["shots"]] == [(0, 2.0), (1, 4.0 / 2.0), (2, 4.0 / 2.0)]
    assert [p["role"] for p in j["passages"]] == ["build", "drop"] and j["passages"][1].get("main") is True
    assert j["beats"][:3] == [0.0, 0.5, 1.0] and j["bars"][0] == 0.0 and 2.0 in j["bars"]  # the drop starts a bar
    assert j["tempo"] == 120.0 and j["stills"][0]["url"] == "/api/stills/thumb?file=cosmic/00_orb_iridescent.jpg"
    assert j["stems"] is None and j["note"] == ""
    clip = client.get(j["clips"][1]["url"])
    assert clip.status_code == 200 and clip.content.endswith(b"clip1")
    assert client.get(j["song"]).content == song.read_bytes()
    assert client.get("/api/perform/job/abc123/clip/9").status_code == 404
    assert client.get("/api/perform/job/abc123/stems.json").status_code == 404
    assert client.get("/api/perform/job/nope").status_code == 404
    assert client.get("/api/perform/job/..%2F..%2Fx").status_code in (400, 404)


def test_a_cut_copied_from_another_desk_plays_its_own_clips(desk):
    client, work = desk
    _job(work, "copied1", clips_elsewhere=True)  # the record names another desk's paths; the files sit in simple/
    j = client.get("/api/perform/job/copied1").json()
    assert all(c["url"] for c in j["clips"])
    assert client.get(j["clips"][2]["url"]).content.endswith(b"clip2")


@needs_ffmpeg
def test_a_cut_without_its_song_file_plays_its_own_soundtrack(desk, tmp_path):
    client, work = desk
    folder = _job(work, "nosong1")
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=64x36:d=1", "-f", "lavfi",
                           "-i", "sine=frequency=330:duration=1", "-shortest", "-c:v", "libx264", "-c:a", "aac", str(folder / "xenoform.mp4")])
    r = client.get("/api/perform/job/nosong1/song")
    assert r.status_code == 200 and r.headers["content-type"].startswith("audio/") and r.content[4:8] == b"ftyp"


def test_perform_song_strip_for_a_track_the_desk_knows(desk):
    client, _ = desk
    j = client.get("/api/perform/song/demo").json()
    assert j["duration"] > 0 and j["beats"] and j["passages"]
    assert all({"role", "start", "end"} <= set(p) for p in j["passages"])
    assert j["bars"] and set(j["bars"]) <= set(j["beats"])
    assert client.get("/api/perform/song/unknownsong").status_code == 404


def test_vj_url_carries_the_cut_and_the_cut_screen_links_to_perform():
    app = (Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    vj = app.split("function vjUrl()")[1].split("\n}\n")[0]
    assert 'params.set("job", job)' in vj and "easyVideoId()" in vj
    actions = app.split("function renderCut(easy, chosen) {")[1].split("const proto")[0]  # t5's Render step holds the cut screen
    assert ">Perform it</a>" in actions and 'href="${esc(vjUrl())}"' in actions
    assert "function takeCard(row)" in app and 'row.kind === "take" ? takeCard(row)' in app
