"""The whole song laid together (docs/SONG.md): the windows' cuts end to end by song time on the song's own beats (a
passage's start pinned, the cut inside a passage where the outgoing morph lands), the window checked, the tame and the QA
once over the whole, the title on the last hit, the song at -16 LUFS, the composite record the timeline and Edit in
Resolve read, and a re-assemble with no GPU."""
from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from xenoform import edit_export, lane, song_assemble, song_run

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "examples" / "songs" / "glitch_out.mp3"
FEATURES = json.loads((ROOT / "tests" / "fixtures" / "analyses" / "glitch-out.features.json").read_text(encoding="utf-8"))
AT = 120.0      # the stretch of Glitch Out the mini song is cut from
LENGTH = 24.0
COLOURS = ("red", "green", "blue")


def _clip(path: Path, colour: str, seconds: float, sound: float | None = None) -> None:
    """A finished window's cut: ``seconds`` of picture in one colour, with ``sound`` seconds of sound when given (a
    window's own sound runs its passage's whole length even when its picture came out short)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = ["-f", "lavfi", "-i", f"sine=frequency=330:duration={sound}"] if sound else []
    maps = ["-map", "0:v", "-map", "1:a", "-c:a", "aac"] if sound else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=320x180:r=24:d={seconds}", *audio,
                    *maps, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture()
def mini(tmp_path):
    """A 24 s song of three windows (passage 1, then passage 2 cut in two), each a finished cut in a colour of its own."""
    song = tmp_path / "song.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(AT), "-t", str(LENGTH), "-i", str(AUDIO), "-ar", "48000", "-ac", "2",
                    str(song)], check=True)
    beats = [round(b - AT, 4) for b in FEATURES["beats"] if AT <= b < AT + LENGTH]
    jobs = tmp_path / "jobs"
    cut_at = [0.0] + [min(beats, key=lambda b: abs(b - t)) for t in (8.0, 16.0)] + [LENGTH]
    windows, passages = [], [{"index": 0, "role": "build", "start": 0.0, "end": cut_at[1], "windows": [0],
                              "look": {"vibe": "cosmic", "name": "Cosmic"}, "objects": ["orb", "pearl", "comet"], "morphs": 2},
                             {"index": 1, "role": "drop", "start": cut_at[1], "end": LENGTH, "windows": [1, 2], "heat": 1.0,
                              "main": True, "look": {"vibe": "liquid-gold", "name": "Liquid gold"},
                              "objects": ["phoenix", "lion head", "dragon", "eagle"], "morphs": 4}]
    for k in range(3):
        a, b = cut_at[k], cut_at[k + 1]
        job = f"job{k}aaaa"
        _clip(jobs / job / "xenoform.mp4", COLOURS[k], b - a)
        mid = round((b - a) / 2, 4)
        rec = {"window": {"song_start": a, "length_s": round(b - a, 4)}, "vibe": passages[0 if k == 0 else 1]["look"]["vibe"],
               "stills": [f"v/{k}_a.jpg", f"v/{k}_b.jpg", f"v/{k}_c.jpg"], "morph_styles": ["melt", "bloom"],
               "shots": [{"start": 0.0, "end": mid, "section": passages[0 if k == 0 else 1]["role"], "passage": 0, "morph": 0},
                         {"start": mid, "end": round(b - a, 4), "section": passages[0 if k == 0 else 1]["role"], "passage": 0, "morph": 1}],
               "beats": [round(x - a, 4) for x in beats if a <= x < b], "clips": [f"c{k}0.mp4", f"c{k}1.mp4"], "fps": 24}
        (jobs / job / "simple").mkdir(parents=True, exist_ok=True)
        (jobs / job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
        windows.append({"index": k, "passage": 0 if k == 0 else 1, "part": max(0, k - 1), "parts": 1 if k == 0 else 2,
                        "role": passages[0 if k == 0 else 1]["role"], "start": a, "end": b, "length_s": round(b - a, 4),
                        "morphs": 2, "status": "done", "job_id": job, "took_s": 30.0, "body": {}})
    folder = jobs / "s0ng1234"
    record = {"kind": "song", "version": 1, "id": "s0ng1234", "created": "2026-11-01T10:00:00+10:00",
              "song": {"label": "Mini", "audio_id": "", "path": str(song), "duration": LENGTH, "tempo": 90.0, "drop": cut_at[1],
                       "beats": beats},
              "tier": "draft", "aspect": "16:9", "breathe": 1.0, "drop_mode": "auto", "plan": {"line": "2 passages", "bar_phase": 0},
              "title": {"text": "Xenoform", "at": cut_at[2] + 2.0}, "passages": passages, "windows": windows, "batch": "",
              "status": "ready", "assembly": None}
    song_run.save(folder, record)
    return {"folder": folder, "jobs": jobs, "cuts": cut_at, "beats": beats}


def _frame(path: Path, t: float) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(180, 320, 3).astype(float)


def test_the_windows_are_laid_on_the_songs_beats_with_the_title_and_the_song(mini):
    rec = song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    out = mini["folder"] / "xenoform.mp4"
    info = song_assemble.probe(out)
    assert abs(info["seconds"] - LENGTH) < 0.1 and (info["width"], info["height"]) == (320, 180)
    a, b = mini["cuts"][1], mini["cuts"][2]
    red, green, blue = _frame(out, a / 2), _frame(out, (a + b) / 2), _frame(out, b + 1.0)
    assert red[..., 0].mean() > 150 > red[..., 1].mean()  # each window plays over its own seconds of the song
    assert green[..., 1].mean() > 80 > green[..., 0].mean() and blue[..., 2].mean() > 150
    cuts = rec["assembly"]["cuts"]
    assert [c["at"] for c in cuts] == [round(a, 4), round(b, 4)]
    assert cuts[0]["pinned"] and cuts[0]["why"] == "a passage starts: pinned on its beat"
    assert not cuts[1]["pinned"] and cuts[1]["why"] == "the outgoing morph lands"  # inside the passage: where it landed
    assert all(min(abs(x - c["at"]) for x in mini["beats"]) < 1e-3 for c in cuts)  # every cut on one of the song's beats
    loud = rec["assembly"]["loudness"]
    assert abs(loud["lufs"] - (-16.0)) < 1.0 and loud["true_peak_db"] <= -1.0
    titled = _frame(out, rec["title"]["at"] + 1.0)
    assert titled.max() > 230 and (mini["folder"] / "assembly" / "title.png").is_file()  # the word over the dimmed shot
    assert rec["status"] == "done" and rec["assembly"]["video"] == "xenoform.mp4" and rec["assembly"]["tame"]["frames"] == 576
    meta = json.loads((mini["folder"] / "meta.json").read_text(encoding="utf-8"))
    assert meta["whole_song"] and meta["song"] == "Mini · whole song" and meta["simple"]
    assert json.loads((mini["folder"] / "took.json").read_text(encoding="utf-8"))["windows_s"] == 90.0


def test_the_composite_is_what_the_timeline_and_edit_in_resolve_read(mini):
    song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    comp = json.loads((mini["folder"] / "simple" / "simple.json").read_text(encoding="utf-8"))
    shots = comp["shots"]
    assert comp["mode"] == "song" and len(shots) == 6 and shots[0]["start"] == 0.0 and abs(shots[-1]["end"] - LENGTH) < 1e-3
    assert [s.get("cut_in", False) for s in shots] == [False, False, True, False, True, False]
    assert shots[2]["boundary"] == "passage" and "boundary" not in shots[4]  # a passage's start; a passage's second window
    assert [s["morph"] for s in shots] == [0, 1, 3, 4, 6, 7] and len(comp["stills"]) == 9 and len(comp["clips"]) == 6
    assert [s["job"] for s in shots[::2]] == ["job0aaaa", "job1aaaa", "job2aaaa"] and shots[2]["vibe"] == "liquid-gold"
    view = lane.build(comp, "s0ng1234")
    assert view["mode"] == "song" and not view["editable"] and not view["swappable"] and not view["rerenderable"]
    assert view["shots"][2]["handoff"] == "cut" and view["shots"][1]["handoff"] == "morph"
    assert [p["jobs"] for p in view["song"]["passages"]] == [["job0aaaa"], ["job1aaaa", "job2aaaa"]]
    marks = edit_export.markers(comp, 576, Fraction(24))
    names = [m["name"] for m in marks]
    assert any("Passage 2 · drop · Liquid gold" in n for n in names) and any("Passage 1" in n for n in names)


def test_a_window_a_few_frames_short_does_not_pull_the_song_early(mini):
    """A window's cut can come out a frame or three short (a QA lag fix drops its trailing held frames): its own last
    frame fills the gap, so the windows after it still play over their own seconds of the song and the song keeps every
    frame (the first Glitch Out drifted 10 frames by its end before this)."""
    a, b = mini["cuts"][1], mini["cuts"][2]
    job = mini["jobs"] / "job1aaaa" / "xenoform.mp4"
    _clip(job, "green", (b - a) - 3 / 24.0)  # three frames short
    rec = song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    out = mini["folder"] / "xenoform.mp4"
    assert song_assemble.probe(out)["frames"] == 576 and rec["assembly"]["frames"] == 576
    assert [w["padded_frames"] for w in rec["assembly"]["windows"]] == [0, 3, 0]
    just_before, just_after = _frame(out, b - 1.5 / 24), _frame(out, b + 1.5 / 24)
    assert just_before[..., 1].mean() > 80 > just_before[..., 2].mean()  # the green window's last frame, held
    assert just_after[..., 2].mean() > 150 > just_after[..., 1].mean()   # the blue window on its own first frame


def test_a_window_49_frames_short_is_held_and_the_song_stays_in_sync(mini):
    """A ZedsDead intro (1 Nov) closed on a rest its QA lag fix cut away: 243 frames of picture against its 12.16 s of
    sound, and the file's length read as the sound's, so the windows after it played 1.8 s early. Its own frames are what
    counts: the picture is held on its last frame for all 49, and every window after it is on its own seconds."""
    a, b = mini["cuts"][1], mini["cuts"][2]
    job = mini["jobs"] / "job1aaaa" / "xenoform.mp4"
    _clip(job, "green", (b - a) - 49 / 24.0, sound=b - a)  # 49 frames short; its sound runs the whole passage
    info = song_assemble.probe(job)
    assert abs(info["seconds"] - (b - a)) < 0.05 and info["frames"] == int(round((b - a) * 24)) - 49
    rec = song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    out = mini["folder"] / "xenoform.mp4"
    assert song_assemble.probe(out)["frames"] == 576 and rec["assembly"]["frames"] == 576
    assert [w["padded_frames"] for w in rec["assembly"]["windows"]] == [0, 49, 0]
    assert [c["at"] for c in rec["assembly"]["cuts"]] == [round(a, 4), round(b, 4)]  # no cut moved early
    held, after = _frame(out, b - 1.0), _frame(out, b + 1.5 / 24)
    assert held[..., 1].mean() > 80 > held[..., 2].mean()  # the green window's last frame, held to its passage's end
    assert after[..., 2].mean() > 150 > after[..., 1].mean()  # the blue window on its own first frame, on time


def test_a_window_ending_on_its_planned_rest_is_held_past_a_bar(mini):
    """The ZedsDead intro (1 Nov): 49 frames short at 144 BPM, where a bar is 40 frames, its plan ending on a 2 s rest
    an older QA pass cut away. The limit is the larger of a bar and that rest plus a beat, so it is held and the song
    stays in sync; the same window with no rest in its plan is refused, as a window really broken."""
    period = 60.0 / 144.0
    rec = song_run.load(mini["folder"])
    rec["song"].update({"tempo": 144.0, "beats": [round(k * period, 4) for k in range(int(LENGTH / period) + 1)]})
    song_run.save(mini["folder"], rec)
    a, b = mini["cuts"][1], mini["cuts"][2]
    job = mini["jobs"] / "job1aaaa"
    _clip(job / "xenoform.mp4", "green", (b - a) - 49 / 24.0, sound=b - a)  # 49 frames short; its sound whole
    bare = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    rested = json.loads(json.dumps(bare))
    rested["shots"][-1].update({"rest": 5, "rest_s": round(5 * period, 4)})  # the 2.08 s rest its plan ends on
    (job / "simple" / "simple.json").write_text(json.dumps(rested), encoding="utf-8")
    got = song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    assert [w["padded_frames"] for w in got["assembly"]["windows"]] == [0, 49, 0] and got["assembly"]["frames"] == 576
    after = _frame(mini["folder"] / "xenoform.mp4", b + 1.5 / 24)
    assert after[..., 2].mean() > 150 > after[..., 1].mean()  # the blue window on its own first frame, on time
    (job / "simple" / "simple.json").write_text(json.dumps(bare), encoding="utf-8")  # no rest planned: a bar is the limit
    with pytest.raises(song_assemble.AssemblyError,
                       match=r"49 short \(2\.04 s\), more than the 1\.67 s it may be held on its last frame \(a bar; its plan "
                             r"ends on no rest\); make that passage again"):
        song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)


def test_a_window_more_than_a_bar_short_is_refused_with_a_clear_line(mini):
    """70 frames short at 90 BPM (a bar is 64) with no rest in its plan: a window really broken, refused with its limit."""
    a, b = mini["cuts"][1], mini["cuts"][2]
    _clip(mini["jobs"] / "job1aaaa" / "xenoform.mp4", "green", (b - a) - 70 / 24.0, sound=b - a)
    with pytest.raises(song_assemble.AssemblyError,
                       match=r"70 short \(2\.92 s\), more than the 2\.67 s it may be held on its last frame \(a bar; its plan "
                             r"ends on no rest\); make that passage again"):
        song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    error = song_run.load(mini["folder"])["assembly"]["error"]
    assert "window 2 (drop, passage 2)" in error and not (mini["folder"] / "xenoform.mp4").exists()


def test_a_shifted_stretch_is_checked_against_its_window(mini):
    rec = song_run.load(mini["folder"])
    rec["windows"][1]["shift_beats"] = 4  # four beats later in a cut that has no picture after its slot
    song_run.save(mini["folder"], rec)
    with pytest.raises(song_assemble.AssemblyError, match="its slot asks"):
        song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)
    assert "does not cover its slot" in song_run.load(mini["folder"])["assembly"]["error"]
    assert not (mini["folder"] / "xenoform.mp4").exists()


def test_a_missing_window_is_said_and_nothing_is_written(mini):
    rec = song_run.load(mini["folder"])
    rec["windows"][2]["status"] = "error"
    song_run.save(mini["folder"], rec)
    with pytest.raises(song_assemble.AssemblyError, match="Window 3 has no finished cut"):
        song_assemble.assemble(mini["folder"], mini["jobs"], qa=False)


def test_place_keeps_to_the_montage_rules():
    beats = [i * 0.5 for i in range(64)]
    a = {"offset": 0.0, "end": 12.0, "bounds": [0.0, 4.0, 8.0, 10.5], "shift_beats": 0}
    b = {"offset": 7.0, "end": 20.0, "bounds": [7.0, 9.0, 13.0], "shift_beats": 0}
    landed = song_assemble.place(a, b, 10.2, beats, pin=False, period=0.5)
    assert landed["at"] == 10.5 and landed["why"] == "the outgoing morph lands"
    pinned = song_assemble.place(a, b, 10.2, beats, pin=True, period=0.5)
    assert pinned["at"] == 10.0 and pinned["pinned"]
    bare = {"offset": 0.0, "end": 12.0, "bounds": [], "shift_beats": 0}
    nothing = {"offset": 7.0, "end": 20.0, "bounds": [], "shift_beats": 0}
    assert song_assemble.place(bare, nothing, 9.6, beats, pin=False, period=0.5)["why"] == "beat 1"  # 10.0: a bar line
    met = song_assemble.place({**bare, "end": 8.0}, {**nothing, "offset": 8.0}, 8.0, beats, pin=False, period=0.5)
    assert met["at"] == 8.0 and met["met"]


def test_the_shareable_copy_is_under_25_mib(tmp_path):
    src = tmp_path / "big.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=24:d=6", "-f", "lavfi", "-i",
                    "sine=f=220:d=6", "-c:v", "libx264", "-crf", "10", "-c:a", "aac", "-shortest", str(src)], check=True)
    small = song_assemble.small_copy(src, tmp_path / "small.mp4", max_mib=1.0, height=360)
    assert small.stat().st_size <= 1.0 * 1024 * 1024 and song_assemble.probe(small)["height"] == 360


def test_the_desk_lays_the_song_together_when_its_last_window_is_done(tmp_path, monkeypatch, mini):
    """The queue's close starts the assembly (no GPU) once every window is done; the route lays it together again on
    demand, and a re-cut of the song itself is refused: it re-cuts a passage at a time."""
    from fastapi.testclient import TestClient

    from xenoform import batch
    from xenoform import ui as _ui

    monkeypatch.setattr(_ui, "work_dir", lambda: mini["jobs"].parent)
    monkeypatch.setattr(batch.Runner, "wake", lambda self: None)
    ran = []
    monkeypatch.setattr(song_assemble, "assemble", lambda folder, jobs, report=None, qa=True: ran.append(Path(folder).name))
    client = TestClient(_ui.create_app())
    rec = song_run.load(mini["folder"])
    runner_rows = [{"label": f"w{k}", "body": {}, "kind": "window", "window": k} for k in range(3)]
    r = client.get("/api/song")  # the desk's queue is made on first use
    assert r.status_code == 200
    app_runner = batch.Runner(mini["jobs"].parent / "batches", start=None, job_of=None, busy=None)
    b = app_runner.add_items(runner_rows, vary=batch.SONG, song_id="s0ng1234")
    rec["batch"] = b["id"]
    song_run.save(mini["folder"], rec)
    stored = app_runner._all()[b["id"]]
    for item in stored["items"]:
        item.update({"status": "done", "job_id": f"job{item['window']}aaaa"})
    stored["beat"] -= batch.STALE_S + 5
    app_runner.save(stored)
    got = client.post("/api/song/s0ng1234/assemble")
    assert got.status_code == 200, got.text
    import time as _time

    for _ in range(50):
        if ran:
            break
        _time.sleep(0.05)
    assert ran == ["s0ng1234"]
    (mini["folder"] / "xenoform.mp4").write_bytes(b"x")
    (mini["folder"] / "simple").mkdir(exist_ok=True)
    (mini["folder"] / "simple" / "simple.json").write_text(json.dumps({"mode": "song"}), encoding="utf-8")
    refused = client.post("/api/jobs/s0ng1234/recut", json={"macros": {"intensity": 0.6}})
    assert refused.status_code == 409 and "a passage at a time" in refused.json()["detail"]
