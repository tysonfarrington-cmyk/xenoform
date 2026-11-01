"""Share › Edit in Resolve (27 Oct): a cut becomes an editor's timeline, a clip a shot on V1 with the song on A1 and
markers at the drop and the dressed handoffs, as FCPXML, FCP7 XML and an EDL zipped with the media."""
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest

from xenoform import edit_export as E

ROOT = Path(__file__).resolve().parents[1]
FPS = Fraction(24)


def _rec(**extra):
    times = [(0.0, 3.0), (3.0, 4.0), (4.0, 5.5), (5.5, 7.0)]
    shots = [{"index": i, "start": a, "end": b, "seconds": b - a, "morph": i} for i, (a, b) in enumerate(times)]
    rec = {"shots": shots, "stills": ["neon-noir/061_wet_street.jpg", "neon-noir/064_moth.jpg", "neon-noir/028_grasshopper.jpg",
                                      "neon-noir/013_chameleon.jpg", "neon-noir/026_railway_lantern.jpg"],
           "boundary_fx": [None, {"kind": "smear", "t": 3.0}, None, {"kind": "strobe", "t": 5.5, "user": True}],
           "boundary_overrides": {"3": {"fx": "strobe"}}, "drop": 5.5, "tier": "final", "vibe": "neon-noir", "fps": 24}
    rec.update(extra)
    return rec


def test_the_cut_splits_into_a_clip_a_shot_named_for_its_objects():
    segs = E.segments(_rec(), 168, FPS)
    assert [(s["start"], s["end"]) for s in segs] == [(0, 72), (72, 96), (96, 132), (132, 168)]
    assert segs[0]["name"] == "01 wet street → moth" and segs[3]["name"] == "04 chameleon → railway lantern"
    assert E.file_name(segs[0]["name"]) == "01 wet street to moth" and E.file_name('05 a: b/c "d" (held)') == "05 a b c d (held)"
    # frames past the last shot (an end card) are their own clip; no record is one clip of the whole cut
    tail = E.segments(_rec(), 216, FPS)
    assert tail[-1] == {"shot": None, "name": "05 end card", "start": 168, "end": 216} and len(tail) == 5
    assert E.segments({}, 100, FPS) == [{"shot": None, "name": "the cut", "start": 0, "end": 100}]
    # a shot under a frame folds into its neighbour, and the clips stay contiguous
    rec = _rec(shots=[{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 1.01}, {"start": 1.01, "end": 2.0}])
    segs = E.segments(rec, 48, FPS)
    assert [(s["start"], s["end"]) for s in segs] == [(0, 24), (24, 48)]


def _clips_rec(tmp_path, pack: bool = True):
    """A clips cut's record (clip_cut): clip shots that name their clip in ``source``, morphs between them carrying the
    clips' names, the clips in a folder with the free film pack's pack.json and labels.json beside them."""
    folder = tmp_path / "film_pack"
    folder.mkdir(parents=True)
    for name in ("01_metropolis_robot.mp4", "02_trip_moon_face.mp4", "03_holiday.mp4"):
        (folder / name).write_bytes(b"x")
    if pack:
        (folder / "pack.json").write_text(json.dumps({"clips": [
            {"file": "01_metropolis_robot.mp4", "source": "metropolis", "label": "Metropolis robot",
             "title": "Metropolis: the Machine-Man wakes"}]}), encoding="utf-8")
    (folder / "labels.json").write_text(json.dumps({"01_metropolis_robot.mp4": "metropolis label",
                                                    "02_trip_moon_face.mp4": "Trip to the Moon"}), encoding="utf-8")
    own = [{"path": str(folder / n), "seconds": 10.0} for n in ("01_metropolis_robot.mp4", "02_trip_moon_face.mp4", "03_holiday.mp4")]
    times = [(0.0, 3.0), (3.0, 4.0), (4.0, 6.0), (6.0, 7.0), (7.0, 9.0)]
    shots = [{"index": i, "start": a, "end": b, "seconds": b - a} for i, (a, b) in enumerate(times)]
    shots[0].update({"own": True, "source": "01_metropolis_robot.mp4", "label": "metropolis robot"})
    shots[1]["clip_morph"] = {"from": "Metropolis robot", "to": "Trip to the Moon"}
    shots[2].update({"own": True, "source": "02_trip_moon_face.mp4", "label": "Trip to the Moon"})
    shots[3]["clip_morph"] = {"from": "Trip to the Moon", "to": "holiday"}
    shots[4].update({"own": True, "source": "03_holiday.mp4", "label": "holiday"})
    return {"shots": shots, "stills": [], "source": "clips", "own_clips": own, "tier": "draft", "fps": 24}


def test_clip_shots_are_named_after_the_film_and_the_morphs_stay_a_to_b(tmp_path):
    """Edit in Resolve named every clip shot "your clip" (1 Nov): a clip shot is named for its film, the label its
    folder's pack.json gives it, else its labels.json's, else its file name; a morph between two stays "A → B"."""
    rec = _clips_rec(tmp_path)
    segs = E.segments(rec, 9 * 24, FPS)
    assert [s["name"] for s in segs] == ["01 Metropolis robot", "02 Metropolis robot → Trip to the Moon", "03 Trip to the Moon",
                                         "04 Trip to the Moon → holiday", "05 03_holiday"]
    assert E.file_name(segs[1]["name"]) == "02 Metropolis robot to Trip to the Moon"
    bare = _clips_rec(tmp_path / "b", pack=False)  # no pack.json: the folder's labels.json names it
    assert E.segments(bare, 9 * 24, FPS)[0]["name"] == "01 metropolis label"
    gone = _clips_rec(tmp_path / "c")
    gone["own_clips"] = [{**c, "path": str(tmp_path / "moved" / Path(c["path"]).name)} for c in gone["own_clips"]]
    gone["own_clips"][1]["label"] = "Trip to the Moon"  # the label the clip was cut with, its folder since moved
    assert [s["name"] for s in E.segments(gone, 9 * 24, FPS)][::2] == ["01 01_metropolis_robot", "03 Trip to the Moon", "05 03_holiday"]
    assert E.folder_labels(tmp_path / "film_pack") == {"01_metropolis_robot.mp4": "Metropolis robot",
                                                       "02_trip_moon_face.mp4": "Trip to the Moon"}


def test_own_footage_in_an_objects_cut_is_named_after_its_clip(tmp_path):
    folder = tmp_path / "mine"
    folder.mkdir()
    (folder / "labels.json").write_text(json.dumps({"beach.mp4": "the beach at dusk"}), encoding="utf-8")
    rec = _rec(own={"slots": [{"first": 1, "last": 2, "clip": str(folder / "beach.mp4")}]})
    rec["shots"][1]["own"] = rec["shots"][2]["own"] = True
    names = [s["name"] for s in E.segments(rec, 168, FPS)]
    assert names[1] == "02 the beach at dusk" and names[2] == "03 the beach at dusk" and names[0] == "01 wet street → moth"


def test_markers_name_the_drop_and_the_dressed_handoffs_one_a_frame():
    marks = E.markers(_rec(), 168, FPS)
    assert marks == [
        {"frame": 72, "name": "smear", "note": "handoff into shot 2"},
        {"frame": 132, "name": "Drop · strobe cut", "note": "the drop the cut is built on; handoff into shot 4, set on the timeline"},
    ]
    assert E.markers(_rec(drop=None, boundary_fx=[]), 168, FPS) == []


def _plan(tmp_path, frames=168, song=True):
    wav = tmp_path / "media" / "xenoform-abc-song.wav"
    rec = _rec()
    segs = E.segments(rec, frames, FPS)
    for s in segs:
        s["path"] = tmp_path / "media" / "shots" / f"{E.file_name(s['name'])}.mp4"
    return {"title": "Xenoform abc · neon-noir Final", "base": "xenoform-abc", "width": 1080, "height": 1920,
            "fps": FPS, "frames": frames, "segments": segs, "markers": E.markers(rec, frames, FPS),
            "morphs": [], "song": {"path": wav, "rate": 44100, "channels": 1, "samples": 44100 * 7, "frames": frames} if song else None}


def test_fcpxml_lays_a_file_a_shot_end_to_end_with_the_song_under_them(tmp_path):
    root = ET.fromstring(E.fcpxml(_plan(tmp_path)).encode("utf-8"))
    assert root.get("version") == "1.10"
    fmt = root.find("resources/format")
    assert (fmt.get("frameDuration"), fmt.get("width"), fmt.get("height")) == ("1/24s", "1080", "1920")
    shots = root.findall("resources/asset[@hasVideo='1']")
    assert len(shots) == 4 and all(a.get("hasAudio") is None for a in shots)  # picture only
    assert shots[1].find("media-rep").get("src").endswith("/media/shots/02%20moth%20to%20grasshopper.mp4")
    seq = root.find("library/event/project/sequence")
    assert seq.get("tcStart") == "86400/24s"  # 01:00:00:00
    clips = seq.findall("spine/asset-clip")
    assert [c.get("name") for c in clips][:2] == ["01 wet street → moth", "02 moth → grasshopper"]
    assert [c.get("ref") for c in clips] == ["s1", "s2", "s3", "s4"]
    t = lambda v: Fraction(v[:-1]) if v != "0s" else Fraction(0)  # noqa: E731
    at = Fraction(86400, 24)
    for c in clips:  # each clip starts where the last ended, from its own file's first frame
        assert t(c.get("offset")) == at and c.get("start") == "0s"
        at += t(c.get("duration"))
    assert at - 3600 == 7
    song = clips[0].find("asset-clip")
    assert song.get("lane") == "-1" and song.get("ref") == "a1" and song.get("duration") == "168/24s"
    marks = [(c.get("name")[:2], m.get("value"), m.get("start")) for c in clips for m in c.findall("marker")]
    assert marks == [("02", "smear", "0s"), ("04", "Drop · strobe cut", "0s")]  # each on the first frame of its clip


def test_fcp7_xml_and_edl_say_the_same_cut(tmp_path):
    p = _plan(tmp_path)
    seq = ET.fromstring(E.xmeml(p).encode("utf-8")).find("sequence")
    items = seq.findall("media/video/track/clipitem")
    assert [(int(i.find("start").text), int(i.find("end").text)) for i in items] == [(0, 72), (72, 96), (96, 132), (132, 168)]
    assert [(i.find("in").text, i.find("out").text) for i in items][:2] == [("0", "72"), ("0", "24")]
    assert items[0].find("file/pathurl").text.startswith("file://localhost/") and items[1].find("file/name").text == "02 moth to grasshopper.mp4"
    assert seq.find("timecode/string").text == "01:00:00:00"
    assert seq.find("media/audio/track/clipitem/end").text == "168"
    assert [(m.find("name").text, m.find("in").text) for m in seq.findall("marker")] == [("smear", "72"), ("Drop · strobe cut", "132")]
    edl = E.edl(p)
    events = [line for line in edl.split("\r\n") if line[:3].isdigit()]
    assert events[1].split()[1:] == ["AX", "V", "C", "00:00:00:00", "00:00:01:00", "01:00:03:00", "01:00:04:00"]
    assert events[3].split()[-1] == "01:00:07:00" and events[-1].split()[2] == "A"
    assert "* FROM CLIP NAME: 01 wet street to moth.mp4" in edl and "* FROM CLIP NAME: xenoform-abc-song.wav" in edl
    edl.encode("ascii")  # an EDL is plain ASCII
    assert E.timecode(86400 + 132, FPS) == "01:00:05:12"


def _ffmpeg(*args):
    from xenoform.video import ffmpeg_bin

    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", *args], check=True)


@pytest.fixture
def job(tmp_path):
    """A finished job folder as Simple mode leaves it: a 7 s cut with sound, the song, two morphs, the record."""
    folder = tmp_path / "jobs" / "abc123"
    (folder / "simple").mkdir(parents=True)
    song = tmp_path / "song.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=7", "-ac", "1", "-ar", "44100", str(song))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x160:rate=24:duration=7", "-i", str(song), "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(folder / "xenoform.mp4"))
    for i in range(2):
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x160:rate=24:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(folder / "simple" / f"final0{i}.mp4"))
    rec = _rec(audio_path=str(song), clips=[str(folder / "simple" / f"final0{i}.mp4") for i in range(2)])
    (folder / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    return folder


def test_the_pack_holds_the_timelines_and_the_media_and_is_made_once_a_cut(job):
    pack = E.build(job)
    assert (pack["shots"], pack["markers"], pack["song"], pack["morphs"], pack["size"], pack["fps"]) == (4, 2, True, 2, [96, 160], 24.0)
    folder = Path(pack["folder"])
    with zipfile.ZipFile(pack["zip"]) as z:
        names = set(z.namelist())
    top = "xenoform-abc123-edit/"
    shots = [f"media/shots/{c['file']}" for c in pack["clips"]]
    assert shots[0] == "media/shots/01 wet street to moth.mp4"
    assert {top + n for n in ("xenoform-abc123.fcpxml", "xenoform-abc123.xml", "xenoform-abc123.edl", "README.txt",
                              "media/xenoform-abc123-song.wav", *shots)} <= names
    assert sorted(n for n in names if "/morphs/" in n) == [top + "media/morphs/01 wet street to moth (morph).mp4",
                                                            top + "media/morphs/02 moth to grasshopper (morph).mp4"]
    # a file a shot, frame-exact, picture alone (the song is A1)
    made = [E._probe(folder / s) for s in shots]
    assert all("audio" not in m for m in made) and [m["video"]["frames"] for m in made] == [72, 24, 36, 36]
    from xenoform.video import ffprobe_bin

    starts = [subprocess.check_output([ffprobe_bin(), "-v", "error", "-show_entries", "stream=start_pts", "-of", "csv=p=0",
                                       str(folder / s)], text=True).strip() for s in shots]
    assert starts == ["0"] * 4  # every file opens on its first frame (B-frames would start the first two frames late)
    src = ET.fromstring((folder / "xenoform-abc123.fcpxml").read_bytes()).find("resources/asset/media-rep").get("src")
    assert src == (folder / shots[0]).as_uri()  # opens on this machine with nothing to relink
    assert "Premiere Pro: File > Import" in (folder / "README.txt").read_text(encoding="utf-8")
    # the same cut: the same pack; a re-cut: a new version, and the old one cleared away
    assert E.build(job) == pack
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=96x160:rate=24:duration=7", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(job / "xenoform.part.mp4"))
    (job / "xenoform.part.mp4").replace(job / "xenoform.mp4")
    import os
    import time

    later = time.time() + 5
    os.utime(job / "xenoform.mp4", (later, later))
    again = E.build(job)
    assert again["version"] != pack["version"] and not Path(pack["zip"]).exists()
    assert again["song"]  # the record's song, not the new cut's (silent) sound


def test_a_cut_whose_song_is_gone_takes_its_own_sound(job):
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    rec["audio_path"] = str(job / "no-such-song.wav")
    (job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    pack = E.build(job)
    assert pack["song"] and (Path(pack["folder"]) / "media" / "xenoform-abc123-song.wav").is_file()


def test_the_desk_serves_the_pack_and_the_share_row_offers_it(job, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    monkeypatch.setattr(_ui, "work_dir", lambda: job.parents[1])
    client = TestClient(_ui.create_app())
    r = client.post("/api/videos/abc123/edit")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == "/api/videos/abc123/edit.zip" and body["timeline"] == "xenoform-abc123.xml" and "signature" not in body
    z = client.get(body["url"])
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert 'filename="xenoform-abc123-edit.zip"' in z.headers["content-disposition"] and z.content[:2] == b"PK"
    assert client.post("/api/videos/nope/edit").status_code == 404
    js = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    share = js.split("function shareRow(easy)")[1].split("function renderRow")[0]
    assert 'data-act="easy-edit"' in share and ">Edit in Resolve</button>" in share and "easy.editUrl" in share
    fn = js.split("async function easyEdit()")[1].split("async function easyRecipeFor")[0]
    assert "/api/videos/${id}/edit`" in fn and 'method: "POST"' in fn and "body.timeline" in fn and "body.fcpxml" in fn and "body.folder" in fn
    assert 'act === "easy-edit"' in js
