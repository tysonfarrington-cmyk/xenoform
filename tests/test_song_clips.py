"""The whole song takes clips (docs/SONG.md, Clips; 1 Nov): a clips song is planned by its passages and made as one clips
Make of the whole song (Length: Full song) playing the song plan, so every passage stays in sync by the one picture's own
frames and the morphs between passages are the cut's own; then laid together as any whole song is, the title on the last
hit, the song at -16 LUFS, the composite record the timeline and Edit in Resolve read."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from xenoform import clip_cut, dense, edit_export, lane, pacing, song_assemble, song_plan, song_run

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "examples" / "songs" / "glitch_out.mp3"
FEATURES = json.loads((ROOT / "tests" / "fixtures" / "analyses" / "glitch-out.features.json").read_text(encoding="utf-8"))
FILMS = ("metropolis", "moon", "nosferatu", "general", "caligari", "phantom")


def _pack(n: int = 24) -> list[dict]:
    return [{"path": f"C:/pack/{k + 1:02d}_{FILMS[k % len(FILMS)]}_{k}.mp4", "seconds": 16.0, "label": f"{FILMS[k % len(FILMS)]} {k}",
             "family": FILMS[k % len(FILMS)]} for k in range(n)]


def _state(**kw) -> dict:
    return {"vibe": "none", "quality_tier": "draft", "aspect": "16:9", "breathe": True, "drop_mode": "auto", "seed": 2727,
            "morph_source": "clips", "own_clips": _pack(), "own_folder": "C:/pack", "audio_id": "abc", "song": "Glitch Out",
            "macros": {"intensity": 0.5, "chaos": 0.3, "speed": 0.5}, **kw}


@pytest.fixture()
def song():
    return song_plan.plan(FEATURES, _state(), drop=139.71, song_id="clip0001", label="Glitch Out")


def test_a_clips_song_is_planned_by_its_passages_as_one_make(song):
    assert song_plan.refuse(_state()) == "" and song["clips"] == 24
    assert len(song["windows"]) == 1 and len(song["passages"]) > 5
    w = song["windows"][0]
    assert w["whole"] and (w["start"], w["end"]) == (0.0, round(FEATURES["duration"], 4))
    assert all(p["windows"] == [0] for p in song["passages"])
    assert w["morphs"] == song["morphs"] == sum(p["morphs"] for p in song["passages"]) > 0
    assert "between your clips, one Make" in song["line"] and song["title"]["at"]
    b = w["body"]
    assert b["morph_source"] == "clips" and b["own_clips"] == _pack() and b["own_folder"] == "C:/pack"
    assert b["length_s"] == 0 and "length_start" not in b and not b.get("chain_pins")  # Full song, the song as it is
    ctx = b[song_plan.KEY]
    assert ctx["whole"] and "passage_start" not in ctx and ctx["song"] == "clip0001" and ctx["opener"]
    assert ctx["plan"]["shots"] and "grid_times" not in ctx["plan"]
    assert b["song"] == "Glitch Out · the whole song in your clips"
    looks = {(p["look"]["vibe"], p["look"]["why"]) for p in song["passages"]}
    assert looks == {("none", "your clips: one cut over the whole song")}  # one look: the vibe you chose over your clips
    with pytest.raises(song_plan.SongError, match="needs your clips"):
        song_plan.plan(FEATURES, _state(own_clips=[]), drop=139.71)


def test_the_window_plays_the_song_plan_shaped_passage_by_passage(song):
    w = song["windows"][0]
    b = w["body"]
    directed = {"duration": float(FEATURES["duration"]), "beats": [float(x) for x in FEATURES["beats"]],
                "sections": list(FEATURES["sections"])}
    assert dense.song_window(b) is not None and dense.paced(b, directed) and pacing.song_context(b) is None
    made = clip_cut.layout(b, directed, None, b["own_clips"])  # what the Make lays out, with no render
    full = song_plan.whole(FEATURES, _state(), 139.71)
    planned = clip_cut.fit(dense.shots_of(full, directed["duration"]), full, _pack(), _state(),
                           beats=directed["beats"], duration=directed["duration"])
    assert [(s["start"], s["end"]) for s in made["shots"]] == [(s["start"], s["end"]) for s in planned["shots"]]
    assert sum(1 for x in made["slots"] if x["kind"] == "morph") == w["morphs"]
    # every passage keeps the span the song gives it: its shots start where the plan's passage starts
    spans = {p["plan_passage"]: p["start"] for p in song["passages"]}
    firsts = {}
    for s in made["shots"]:
        firsts.setdefault(s["passage"], s["start"])
    for p, start in spans.items():
        assert firsts[p] == pytest.approx(start, abs=0.05)
    shots = [dict(s) for s in made["shots"]]
    shaped = dense.shape_shots(shots, b, {"chaos": 0.3, "intensity": 0.5}, None, beats=directed["beats"],
                               stills=clip_cut.nouns(shots), drop=139.71)
    assert shaped is not None and shaped["timing"]  # each passage its own profile (a scene's smooth, a drop's snap)
    roles = {str(s["section"]): s.get("fx_names") for s in shots}
    assert roles.get("calm") == [] and pacing.summary_line(shots, breathe=True, song=pacing.song_context(b)).count("passages")


def test_the_song_record_keeps_the_clips_and_labels_the_one_window(song):
    rec = song_run.new(song, song_id="clip0001", body=_state(), audio_id="abc", audio_path="C:/song.mp3", label="Glitch Out")
    assert rec["body"]["morph_source"] == "clips" and rec["windows"][0]["whole"]
    items = song_run.items(rec)
    assert len(items) == 1 and items[0]["label"].startswith("The whole song in your clips")
    rec["windows"][0]["status"] = "running"
    assert song_run.view(rec)["running"]["role"] == "the whole song"


def _clip(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r=24:d={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_the_desk_plans_and_queues_a_clips_song(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import batch
    from xenoform import ui as _ui

    monkeypatch.setattr(_ui, "work_dir", lambda: tmp_path)
    monkeypatch.setattr(batch.Runner, "wake", lambda self: None)  # nothing renders in a test
    client = TestClient(_ui.create_app())
    folder = tmp_path / "reels"
    for k in range(4):
        _clip(folder / f"0{k}_reel{k}.mp4", 3.0)
    params = {"duration": 239, "energy": "dense", "tier": "draft", "aspect": "16:9", "audio_id": "song-glitch-out",
              "breathe": "1", "drop_mode": "auto", "whole_song": "1", "source": "clips", "own_folder": str(folder)}
    whole = client.get("/api/simple/options", params=params).json()["song"]
    assert whole["windows"] == 1 and whole["morphs"] > 0 and "between your clips" in whole["line"]
    none = client.get("/api/simple/options", params={**params, "own_folder": ""}).json()["song"]
    assert "needs your clips" in none["error"]
    body = {**_state(own_clips=[], own_folder=str(folder), audio_id="song-glitch-out"), "energy_preset": "dense"}
    r = client.post("/api/song", json={"body": body})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["of"] == 1 and v["morphs"] == whole["morphs"]
    saved = json.loads((tmp_path / "batches" / f"{v['batch']}.json").read_text(encoding="utf-8"))
    b = saved["items"][0]["body"]
    assert len(saved["items"]) == 1 and b["morph_source"] == "clips" and len(b["own_clips"]) == 4 and b["length_s"] == 0


def test_a_clips_song_is_laid_together_with_its_title_and_opens_in_resolve(tmp_path):
    at, length = 120.0, 24.0
    wav = tmp_path / "song.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-t", str(length), "-i", str(AUDIO), "-ar", "48000", "-ac", "2",
                    str(wav)], check=True)
    beats = [round(b - at, 4) for b in FEATURES["beats"] if at <= b < at + length]
    jobs = tmp_path / "jobs"
    job = "clipjob1"
    _clip(jobs / job / "xenoform.mp4", length)
    cut = [0.0, 6.0, 9.0, 16.0, length]
    shots = [{"start": cut[0], "end": cut[1], "section": "calm", "passage": 0, "own": True, "label": "metropolis 0", "rest": 4},
             {"start": cut[1], "end": cut[2], "section": "calm", "passage": 0, "clip_morph": {"from": "metropolis 0", "to": "moon 1"}},
             {"start": cut[2], "end": cut[3], "section": "drop", "passage": 1, "own": True, "label": "moon 1", "event": "drop",
              "drop_run": 0, "heat": 1.0, "cut_in": True},
             {"start": cut[3], "end": cut[4], "section": "drop", "passage": 1, "own": True, "label": "nosferatu 2"}]
    rec = {"window": {"song_start": 0.0, "length_s": length}, "vibe": "none", "source": "clips", "stills": [],
           "own_clips": _pack(3), "shots": shots, "morph_styles": ["melt"] * 4, "beats": beats, "fps": 24,
           "clips": [str(jobs / job / "simple" / "clips" / f"c{k}.mp4") for k in range(4)],
           "pacing": {"breathe": 1.0, "drop_mode": "auto", "passages": [{"role": "calm"}, {"role": "drop"}], "rests": 1}}
    (jobs / job / "simple").mkdir(parents=True, exist_ok=True)
    (jobs / job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    passages = [{"index": 0, "plan_passage": 0, "role": "calm", "start": 0.0, "end": 9.0, "windows": [0], "morphs": 1,
                 "look": {"vibe": "none", "name": "None"}},
                {"index": 1, "plan_passage": 1, "role": "drop", "start": 9.0, "end": length, "windows": [0], "morphs": 0,
                 "drop_run": 0, "heat": 1.0, "main": True, "look": {"vibe": "none", "name": "None"}}]
    folder = jobs / "song0clp"
    song_run.save(folder, {"kind": "song", "version": 1, "id": "song0clp", "created": "2026-11-01T12:00:00+10:00",
                           "song": {"label": "Mini", "audio_id": "", "path": str(wav), "duration": length, "tempo": 90.0,
                                    "drop": 9.0, "beats": beats},
                           "tier": "draft", "aspect": "16:9", "breathe": 1.0, "drop_mode": "auto",
                           "plan": {"line": "2 passages, 1 morph between your clips, one Make", "bar_phase": 0},
                           "title": {"text": "Xenoform", "at": 18.0}, "passages": passages,
                           "windows": [{"index": 0, "passage": 0, "part": 0, "parts": 1, "role": "whole song", "start": 0.0,
                                        "end": length, "length_s": length, "morphs": 1, "whole": True, "clips": 3,
                                        "status": "done", "job_id": job, "took_s": 60.0, "body": {}}],
                           "batch": "", "status": "ready", "assembly": None})
    done = song_assemble.assemble(folder, jobs, qa=False)
    a = done["assembly"]
    assert a["video"] == "xenoform.mp4" and a["title"]["at"] == 18.0 and a["cuts"] == []
    assert a["windows"][0]["padded_frames"] == 0 and a["seconds"] == pytest.approx(length, abs=1 / 24)
    comp = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert comp["mode"] == "song" and comp["source"] == "clips" and comp["own_clips"] == _pack(3)
    assert [s["song_passage"] for s in comp["shots"]] == [0, 0, 1, 1]  # each shot in its own passage of the song
    assert comp["pacing"]["passages"] and comp["pacing"]["line"].endswith("one Make")
    view = lane.build(comp, "song0clp")
    assert view["mode"] == "song" and view["source"] == "clips" and view["shots"][0]["own"]
    pack = edit_export.build(folder, "song0clp")
    assert pack["shots"] == 4 and "your clip" in pack["clips"][0]["name"]
    assert any("Passage 2 · drop" in m["name"] for m in pack["marker_list"])  # the drop's own marker shares its frame
