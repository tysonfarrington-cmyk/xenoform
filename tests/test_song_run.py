"""The whole song's run (docs/SONG.md): its windows queued one at a time through the Variations queue (an idle desk, an
idle ComfyUI queue, the owner token), a failed window queued again once, Resume keeping the done ones, Stop ending the
whole, the record and its view (n of m), the desk's routes and estimate, and a window Make on the mock engine playing its
stretch of the song plan."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from xenoform import batch, dense, song_plan, song_run

ROOT = Path(__file__).resolve().parents[1]
FEATURES = json.loads((ROOT / "examples" / "songs" / "glitch-out.features.json").read_text(encoding="utf-8"))
AUDIO = ROOT / "examples" / "songs" / "glitch_out.mp3"


def _state(**extra) -> dict:
    state = {"vibe": "cosmic", "breathe": 1.0, "drop_mode": "auto", "quality_tier": "draft", "aspect": "16:9",
             "energy_preset": "dense", "seed": 2727, "audio_id": "song-glitch-out", "song": "Glitch Out",
             "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}, "morph_style": "auto",
             "morph_timing": "smooth", "effects": [], "dance_fx": "auto"}
    state.update(extra)
    return state


@pytest.fixture(scope="module")
def drop() -> float:
    return dense.find_drop(AUDIO, FEATURES["beats"], FEATURES["duration"])


class Fake:
    """A desk: the jobs it starts run until the test finishes them; ``gpu`` is what busy() says."""

    def __init__(self):
        self.jobs, self.started, self.gpu = {}, [], ""

    def start(self, body):
        jid = f"job{len(self.started)}"
        self.started.append((jid, body))
        self.jobs[jid] = {"status": "running", "overall": 0.3, "detail": "Morph 1 of 3", "eta_s": 60}
        return jid

    def finish(self, jid, status="done", took=60.0, error=""):
        self.jobs[jid].update({"status": status, "took_s": took, "detail": "Cut ready", "error": error or None})


def _runner(tmp_path, fake, closed):
    r = batch.Runner(tmp_path / "batches", start=fake.start, job_of=fake.jobs.get, busy=lambda: fake.gpu,
                     cancel=lambda jid: fake.jobs[jid].update({"status": "cancelled"}), on_closed=closed.append)
    r.wake = lambda: None  # the tests step by hand
    return r


def _rows(n: int) -> list[dict]:
    return [{"label": f"Passage {k + 1}", "body": {"vibe": "cosmic", "length_s": 7.0, "length_start": 7.0 * k}, "kind": "window",
             "window": k} for k in range(n)]


def test_the_windows_queue_one_at_a_time_and_a_failed_one_goes_again_at_the_back(tmp_path):
    fake, closed = Fake(), []
    r = _runner(tmp_path, fake, closed)
    b = r.add_items(_rows(3), vary=batch.SONG, song_id="s1", song="Glitch Out")
    assert b["vary"] == "song" and b["song_id"] == "s1" and [i["status"] for i in b["items"]] == ["queued"] * 3
    assert [i["window"] for i in b["items"]] == [0, 1, 2]
    fake.gpu = "ComfyUI is busy with 1 job from elsewhere: waiting for the GPU."
    assert r.step() == "waiting" and fake.started == []  # never ahead of another desk's render
    fake.gpu = ""
    assert r.step() == "started" and r.step() == "running" and len(fake.started) == 1
    fake.finish("job0", "error", error="ComfyUI went away")
    assert r.step() == "finished"
    first = r.get(b["id"])["items"][0]
    assert first["status"] == "queued" and first["attempts"] == 1 and first["failed"][0]["job_id"] == "job0"
    assert r.step() == "started" and fake.started[-1][1]["length_start"] == 7.0  # window 1 first: the failed one waits
    fake.finish("job1")
    assert r.step() == "finished" and r.step() == "started" and fake.started[-1][1]["length_start"] == 14.0
    fake.finish("job2")
    assert r.step() == "finished" and r.step() == "started" and fake.started[-1][1]["length_start"] == 0.0  # window 0 again
    fake.finish("job3", "error", error="out of memory")
    assert r.step() == "finished" and closed and closed[-1]["id"] == b["id"]  # twice failed: it waits for Resume
    assert [i["status"] for i in r.get(b["id"])["items"]] == ["error", "done", "done"]
    assert r.step() == "idle" and len(closed) == 1  # told once
    again = r.resume(b["id"])
    assert [i["status"] for i in again["items"]] == ["queued", "done", "done"]  # the done ones are kept
    assert r.step() == "started" and fake.started[-1][1]["length_start"] == 0.0
    fake.finish("job4")
    assert r.step() == "finished" and len(closed) == 2 and all(i["status"] == "done" for i in closed[-1]["items"])


def test_stop_ends_the_whole_and_resume_queues_what_was_not_done(tmp_path):
    fake, closed = Fake(), []
    r = _runner(tmp_path, fake, closed)
    b = r.add_items(_rows(3), vary=batch.SONG, song_id="s2")
    r.step()
    fake.finish("job0")
    r.step()
    r.step()  # window 1 renders
    stopped = r.cancel(b["id"])
    assert [i["status"] for i in stopped["items"]] == ["done", "running", "cancelled"]
    assert fake.jobs["job1"]["status"] == "cancelled"
    assert r.step() == "finished" and [i["status"] for i in r.get(b["id"])["items"]] == ["done", "cancelled", "cancelled"]
    assert r.get(b["id"])["items"][1].get("attempts") == 0  # a stop is not a failure: nothing goes again by itself
    assert [i["status"] for i in r.resume(b["id"])["items"]] == ["done", "queued", "queued"]
    # a batch of variations keeps its old resume: only what a restart stopped goes again
    v = r.add(dict(vibe="cosmic"), 3, "seed")
    rec = r._all()[v["id"]]
    rec["items"][0]["status"], rec["items"][1]["status"] = "error", "stopped"
    assert [i["status"] for i in r.resume(v["id"])["items"]] == ["error", "queued", "queued"]


def test_the_record_and_its_view_say_n_of_m(drop):
    song = song_plan.plan(FEATURES, _state(), drop=drop, song_id="ab12cd34", label="Glitch Out")
    rec = song_run.new(song, song_id="ab12cd34", body=_state(scenes=[{"x": 1}]), audio_id="song-glitch-out",
                       audio_path=AUDIO, label="Glitch Out")
    assert rec["kind"] == "song" and len(rec["windows"]) == 14 and "scenes" not in rec["body"]
    assert all("plan" not in w and w["body"][song_plan.KEY]["plan"]["shots"] for w in rec["windows"])
    items = song_run.items(rec)
    assert items[0]["label"].startswith("Passage 1 of 14: intro") and items[0]["window"] == 0
    v = song_run.view(rec)
    assert (v["status"], v["done"], v["of"], v["morphs"]) == ("queued", 0, 14, 78) and v["left_s"] > 0
    fake_batch = {"items": [{"window": k, "status": "done", "job_id": f"j{k}", "took_s": 60.0} for k in range(5)]
                  + [{"window": 5, "status": "running", "job_id": "j5", "progress": 0.4, "detail": "Morph 2 of 3"}]}
    song_run.sync(rec, fake_batch)
    v = song_run.view(rec)
    assert (v["status"], v["done"], v["running"]["window"], v["running"]["passage"]) == ("running", 5, 5, 5)
    assert v["passages"][0]["windows"][0]["job_id"] == "j0" and v["passages"][0]["vibe"] == rec["passages"][0]["look"]["vibe"]
    for w in rec["windows"]:
        w["status"] = "done"
    assert song_run.status_of(rec) == "ready" and song_run.ready(rec)
    rec["assembly"] = {"video": "xenoform.mp4"}
    assert song_run.view(rec)["status"] == "done" and song_run.view(rec)["video"] == "/api/videos/ab12cd34/video"
    rec["windows"][3]["status"] = "error"
    rec["assembly"] = None
    assert song_run.status_of(rec) == "failed"


def _client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    monkeypatch.setattr(_ui, "work_dir", lambda: tmp_path)
    monkeypatch.setattr(batch.Runner, "wake", lambda self: None)  # nothing renders in a test
    return TestClient(_ui.create_app())


def test_the_desk_plans_queues_stops_and_resumes_a_whole_song(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    opts = client.get("/api/simple/options", params={"duration": 239, "energy": "dense", "tier": "draft", "aspect": "16:9",
                                                       "audio_id": "song-glitch-out", "breathe": "1", "drop_mode": "auto",
                                                       "whole_song": "1"}).json()
    whole = opts["song"]
    assert whole["morphs"] == 78 and whole["passages"] == 14 and whole["windows"] == 14
    assert whole["estimate"]["tiers"]["cloud"]["credits"] == [281, 468] and whole["title"]["at"] == pytest.approx(231.33, abs=0.01)
    assert opts["cloud_final"]["estimate"]["morphs"] == 78
    assert client.get("/api/simple/options", params={"audio_id": "song-glitch-out", "duration": 239}).json()["song"] is None
    assert client.post("/api/song", json={"body": _state(audio_id="gone")}).status_code == 400
    assert client.post("/api/song", json={"body": _state(quality_tier="cloud")}).status_code == 400  # no credits tick
    assert client.post("/api/song", json={"body": _state(morph_source="clips")}).status_code == 400
    r = client.post("/api/song", json={"body": _state(), "song_cap": "auto"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert (v["status"], v["done"], v["of"], v["morphs"]) == ("queued", 0, 14, 78) and v["batch"]
    rec = json.loads((tmp_path / "jobs" / v["id"] / "song.json").read_text(encoding="utf-8"))
    saved = json.loads((tmp_path / "batches" / f"{v['batch']}.json").read_text(encoding="utf-8"))
    assert saved["vary"] == "song" and saved["song_id"] == v["id"] and len(saved["items"]) == 14
    assert saved["items"][3]["body"]["length_exact"] and saved["items"][3]["body"][song_plan.KEY]["song"] == v["id"]
    assert rec["windows"][3]["body"]["chain_pins"] == saved["items"][3]["body"]["chain_pins"]
    assert client.get(f"/api/song/{v['id']}").json()["of"] == 14
    assert client.get("/api/song").json()["songs"][0]["id"] == v["id"]
    stopped = client.post(f"/api/song/{v['id']}/stop").json()
    assert stopped["status"] == "stopped" and stopped["stopped"] == 14
    back = client.post(f"/api/song/{v['id']}/resume").json()
    assert back["status"] == "queued" and back["open"] == 14
    assert client.get("/api/song/nope").status_code == 404


def test_cloud_is_queued_only_behind_the_credits_tick_and_each_window_holds_its_gate(tmp_path, monkeypatch, drop):
    """A whole song on Cloud Final queues only with the tick, every window a Make of at most 16 morphs carrying the tier
    and the tick; a window body without the tick is refused by the Make before anything is sent (nothing renders here:
    the queue never runs in a test)."""
    client = _client(tmp_path, monkeypatch)
    assert client.post("/api/song", json={"body": _state(quality_tier="cloud")}).status_code == 400
    v = client.post("/api/song", json={"body": _state(quality_tier="cloud", cloud_final_ok=True)}).json()
    saved = json.loads((tmp_path / "batches" / f"{v['batch']}.json").read_text(encoding="utf-8"))
    bodies = [i["body"] for i in saved["items"]]
    assert all(b["quality_tier"] == "cloud" and b["cloud_final_ok"] is True for b in bodies)
    assert all(len(b[song_plan.KEY]["plan"]["shots"]) <= 16 for b in bodies) and v["morphs"] == 78
    rec = json.loads((tmp_path / "jobs" / v["id"] / "song.json").read_text(encoding="utf-8"))
    assert rec["estimate"]["tiers"]["cloud"]["credits"] == [281, 468]
    w = rec["windows"][0]
    with pytest.raises(RuntimeError, match="Cloud Final spends Comfy Cloud credits"):
        dense.run_simple(song_plan.directed_for(FEATURES, w), AUDIO, tmp_path / "x.mp4", tmp_path, {},
                         {**w["body"], "cloud_final_ok": False}, lambda *a: None)


def test_a_window_is_trimmed_where_it_says_and_hidden_from_my_videos(tmp_path, monkeypatch, drop):
    """The desk trims a window exactly at its passage's start (no snap back to a beat, a hundredth of a second of fade),
    writes the song's beats and roles beside it, and its job is listed under its song, not in My videos."""
    from xenoform import ui as _ui

    client = _client(tmp_path, monkeypatch)
    song = song_plan.plan(FEATURES, _state(), drop=drop, song_id="feed1234", label="Glitch Out")
    w = song["windows"][7]  # the drop at 1:59.8, heat 1.0
    started = {}

    def fake_run(job_id, audio_path, body, cfg, out, cancel_event=None):  # the Make itself is not run here: what
        started.update({"body": body, "audio": audio_path})  # _start_job hands it is the point

    monkeypatch.setattr(_ui, "_run_job", fake_run)
    r = client.post("/api/generate", json=w["body"])
    assert r.status_code == 200, r.text
    body, audio = started["body"], Path(started["audio"])
    assert body["song_source"]["offset"] == pytest.approx(w["start"], abs=1e-3)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)],
                           capture_output=True, text=True).stdout.strip()
    assert float(probe) == pytest.approx(w["length_s"], abs=0.03)
    side = json.loads(audio.with_name(audio.stem + ".window.json").read_text(encoding="utf-8"))
    assert side["start"] == pytest.approx(w["start"], abs=1e-3) and side["sections"][0]["role"] == "drop"
    meta = json.loads((tmp_path / "jobs" / r.json()["id"] / "meta.json").read_text(encoding="utf-8"))
    assert meta["part_of"] == "feed1234"
    (tmp_path / "jobs" / r.json()["id"] / "xenoform.mp4").write_bytes(b"x")
    assert all(row["id"] != r.json()["id"] for row in client.get("/api/videos").json()["videos"])


def test_a_window_make_on_the_mock_engine_is_the_songs_passage(tmp_path, drop):
    """The drop at 1:59.8 made as its window on the mock engine: the cut is the song plan's five shots, opens on the drop's
    event with the style the song gives it, keeps its place in the song for a re-cut, and says where it sits."""
    song = song_plan.plan(FEATURES, _state(), drop=drop, song_id="feed1234", label="Glitch Out")
    w = song["windows"][7]
    wav = tmp_path / "window.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{w['start']:.4f}", "-t", f"{w['length_s']:.4f}", "-i", str(AUDIO),
                    "-ar", "48000", "-ac", "2", str(wav)], check=True)
    assert w["context"]["opens"] == "spin" and w["body"]["morph_style"] == "bloom"  # the glass hand keeps its loved Bloom
    # on Auto the window opens on the style the song gives its run (the second run spins: the main one shatters)
    body = {**w["body"], "morph_style": "auto", "song_source": {"path": str(AUDIO), "offset": w["start"]}}
    directed = song_plan.directed_for(FEATURES, w)
    job = tmp_path / "job"
    job.mkdir()
    info = dense.run_simple(directed, wav, job / "xenoform.mp4", job, {}, body, lambda *a: None, engine="mock")
    assert len(info["shots"]) == w["morphs"] == 5 and info["plan_name"] == "story"
    assert info["shots"][0]["event"] == "drop" and info["morph_styles"][0] == w["context"]["opens"]
    assert info["window"]["song_start"] == pytest.approx(w["start"], abs=1e-3)
    assert info["stills"] == w["stills"]  # the pins the plan picked, every slot
    assert info["recut_state"][song_plan.KEY]["passage"] == w["passage"] and "plan" not in info["recut_state"][song_plan.KEY]
    assert [round(s["end"] - s["start"], 2) for s in info["shots"]] == [round(s["end"] - s["start"], 2) for s in w["plan"]["shots"]]
    assert info["pacing"]["line"].startswith("passage 8 of 14 of the song, a drop at 2:00 (heat 1.00)")  # not "the main"
    again = dense.recut_from_cache(job, {"macros": {"intensity": 0.7, "chaos": 0.4, "glow": 0.5}})
    assert again["drop"] == info["drop"] and len(again["shots"]) == 5
    assert again["pacing"]["line"].startswith("passage 8 of 14 of the song")
