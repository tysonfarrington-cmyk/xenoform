"""Full-length songs in Simple mode: a shot a bar for the whole song over a closed loop of reusable morphs,
a stills animatic instead of the CPU blob, a lock-safe publish, and the Length control."""
import io
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from xenoform import beatfx, dense
from xenoform.cloud_morph import ALLOWED_S

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo.wav"
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")


def _beats(duration: float, bpm: float = 90.0) -> list[float]:
    step = 60.0 / bpm
    return [round(i * step, 4) for i in range(int(duration / step))]


def test_shot_budget_scales_with_the_song():
    assert dense.shot_budget(20) == dense.MAX_SHOTS
    assert 120 <= dense.shot_budget(239) <= 160
    assert dense.shot_budget(3600) == dense.SHOT_BUDGET_MAX


def test_dense_plan_keeps_a_shot_a_bar_for_a_four_minute_song():
    beats = _beats(238.8)
    plan = dense.dense_plan(238.8, beats, drop=120.0)
    shots = plan["shots"]
    assert 60 <= len(shots) <= dense.shot_budget(238.8)
    seconds = [s["end"] - s["start"] for s in shots]
    assert max(seconds) < 12.0  # no 40 s slideshow slots
    assert abs(shots[-1]["end"] - 238.8) < 1e-3 and shots[0]["start"] == 0.0
    # the old behaviour stays for a demo clip
    assert len(dense.dense_plan(20.0, _beats(20.0, 120), drop=12.0)["shots"]) <= dense.MAX_SHOTS


def test_clip_plan_is_a_closed_loop_within_budget():
    beats = _beats(238.8)
    shots = dense.dense_plan(238.8, beats, drop=120.0)["shots"]
    cp = dense.clip_plan(shots, 238.8, beats)
    assert dense.CLIP_BUDGET[0] <= cp["morphs"] <= dense.CLIP_BUDGET[1] < len(shots)
    assert cp["clip_s"] in ALLOWED_S and 2 <= cp["clip_s"] <= 5
    assert cp["reuse"] and len(cp["assign"]) == len(shots)
    for a, b in zip(cp["assign"], cp["assign"][1:]):
        assert b == (a + 1) % cp["morphs"]  # walking the loop keeps every handoff continuous
    small = dense.clip_plan(shots[:5], 20.0, beats)
    assert small["morphs"] == 5 and not small["reuse"]


def test_plan_summary_and_estimate_include_the_look_pass():
    summary = dense.plan_summary(238.8, _beats(238.8), "dense", "draft", "9:16")
    assert summary["long_song"] and summary["reuse"] and summary["shots"] > summary["morphs"] >= 12
    est = summary["estimate"]
    assert est["look_seconds"] > 0 and est["gpu_seconds"] > 0 and est["seconds"] >= est["gpu_seconds"] + est["look_seconds"]
    assert est["clip_s"] == summary["clip_s"]
    short = dense.plan_summary(20.0, _beats(20.0, 120), "dense", "draft", "9:16")
    assert not short["long_song"] and short["morphs"] == short["shots"]
    assert dense.estimate(10, "draft", clip_s=4.0)["gpu_seconds"] == 2 * dense.estimate(10, "draft", clip_s=2.0)["gpu_seconds"]


def test_run_simple_reuses_a_morph_loop_for_a_long_song(tmp_path, monkeypatch):
    seen = {}
    rendered = {}

    def fake_compose(clips, shots, audio, out, **kw):
        seen["clips"] = [Path(c).name for c in clips]
        seen["shots"] = shots
        seen.update(kw)
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": kw.get("fps"), "look": {"dance_fx": kw.get("dance_fx"), "frames": 1, "seconds": 0.1}}

    pool = [{"path": f"s{i}.png", "file": f"s{i}.png", "noun": f"n{i}"} for i in range(12)]
    monkeypatch.setattr(dense, "stills_for", lambda state, n: ("ocean", [pool[i % 12] for i in range(n)]))

    def fake_mock_clips(shots, stills, work, w, h):
        rendered["shots"] = shots
        rendered["stills"] = stills
        return [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))]

    import xenoform.cloud_morph as cm
    monkeypatch.setattr(cm, "_mock_clips", fake_mock_clips)
    monkeypatch.setattr(beatfx, "compose", fake_compose)
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    duration = 120.0
    directed = {"duration": duration, "beats": _beats(duration, 100)}
    state = {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple"}
    info = dense.run_simple(directed, DEMO, tmp_path / "x.mp4", tmp_path, {}, state, lambda *a: None, engine="mock")
    shots = seen["shots"]
    morphs = len(rendered["shots"])
    assert len(shots) > morphs >= dense.CLIP_BUDGET[0]
    assert len(rendered["stills"]) == morphs + 1 and rendered["stills"][-1] is rendered["stills"][0]  # closed loop
    assert len(seen["clips"]) == len(shots)
    assert all(int(s["render_s"]) == int(rendered["shots"][0]["render_s"]) and "clip" in s for s in shots)
    assert [int(s["clip"]) for s in shots] == [i % morphs for i in range(len(shots))]
    assert seen["size"] == (540, 960)  # Draft composes at half size (the look pass runs 4x faster)
    assert info["chain"]["morphs"] == morphs and len(info["chain"]["assign"]) == len(shots)


def test_short_clip_keeps_one_morph_per_shot(tmp_path, monkeypatch):
    rendered = {}
    monkeypatch.setattr(dense, "stills_for", lambda state, n: ("black", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(n)]))
    import xenoform.cloud_morph as cm
    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: rendered.setdefault("n", len(shots)) and [tmp_path / f"m{i}.mp4" for i in range(len(shots))])
    def fake_compose(clips, shots, audio, out, **kw):
        Path(out).write_bytes(b"x")
        return {"frames": 1, "seconds": 1.0, "size": "", "aspect": "16:9", "fx": True, "overlay": False, "centres": [], "fps": 24, "look": {}}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    dense.run_simple({"duration": 20.0, "beats": _beats(20.0, 120)}, DEMO, tmp_path / "s.mp4", tmp_path, {},
                     {"vibe": "black", "aspect": "16:9", "energy_preset": "dense"}, lambda *a: None, engine="mock")
    assert 1 <= rendered["n"] <= dense.MAX_SHOTS


def _wav(path: Path, seconds: float, sr: int = 22050) -> Path:
    t = np.arange(int(seconds * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sign(np.sin(2 * np.pi * 1.5 * t)))  # a 90 bpm pulse
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return path


def test_stills_animatic_cuts_real_stills_on_the_plan(tmp_path):
    wav = _wav(tmp_path / "song.wav", 30.0)
    directed = {"duration": 30.0, "beats": _beats(30.0, 90)}
    out = tmp_path / "xenoform.mp4"
    info = dense.stills_animatic(directed, {"vibe": "black", "energy_preset": "dense", "aspect": "9:16", "mode": "simple"},
                                 wav, out, tmp_path / "work", size=(108, 192))
    assert out.is_file() and out.stat().st_size > 1000 and info["shots"] >= 8 and info["vibe"] == "black"
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(out)],
                           capture_output=True, text=True, check=True)
    meta = json.loads(probe.stdout)
    assert abs(float(meta["format"]["duration"]) - 30.0) < 0.6
    assert {s.get("width") for s in meta["streams"] if s.get("width")} == {108}


def test_publish_file_survives_a_locked_destination(tmp_path, monkeypatch):
    from xenoform import turbo

    dest = tmp_path / "xenoform.mp4"
    dest.write_bytes(b"old")
    calls = {"n": 0}
    real = Path.replace

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Access is denied")
        return real(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    tmp = tmp_path / "xenoform.part.mp4"
    tmp.write_bytes(b"new")
    turbo.publish_file(tmp, dest, pause=0.0)
    assert dest.read_bytes() == b"new" and not tmp.exists() and calls["n"] == 3
    monkeypatch.setattr(Path, "replace", lambda self, target: (_ for _ in ()).throw(PermissionError(5, "locked")))
    tmp.write_bytes(b"newer")
    turbo.publish_file(tmp, dest, tries=2, pause=0.0)  # always locked: the bytes are copied into place instead
    assert dest.read_bytes() == b"newer" and not tmp.exists()


def test_simple_jobs_skip_the_painted_animatic():
    src = (ROOT / "src" / "xenoform" / "turbo.py").read_text(encoding="utf-8")
    assert "stills_animatic(directed, state" in src and "def _painted_animatic(" in src
    assert 'str(state.get("mode") or "") == "simple"' in src


@pytest.fixture(scope="module")
def client():
    from xenoform.ui import create_app

    return TestClient(create_app())


def test_length_trims_the_song_around_the_drop(client, tmp_path, monkeypatch):
    from xenoform import ui as ui_mod

    wav = _wav(tmp_path / "long.wav", 24.0)
    up = client.post("/api/analyze", files={"file": ("long.wav", wav.read_bytes(), "audio/wav")})
    assert up.status_code == 200, up.text
    audio_id = up.json()["audio_id"]
    assert abs(float(up.json()["duration"]) - 24.0) < 0.5
    captured = {}

    def fake_run_job(job_id, audio_path, body, cfg, out, cancel_event=None):
        captured["body"] = dict(body)
        captured["audio_path"] = Path(audio_path)
        with ui_mod._LOCK:
            ui_mod._JOBS[job_id]["status"] = "done"

    monkeypatch.setattr(ui_mod, "_run_job", fake_run_job)
    started = client.post("/api/generate", json={"audio_id": audio_id, "quality": "turbo", "mode": "simple", "vibe": "ocean",
                                                 "length_s": 8, "song": "Long"})
    assert started.status_code == 200, started.text
    body = captured["body"]
    assert body["audio_id"] != audio_id and body["song"].endswith("(8 s cut)")
    cut = ui_mod._FEATURES[body["audio_id"]]
    assert abs(float(cut["duration"]) - 8.0) < 0.3
    assert cut["trimmed_from"]["audio_id"] == audio_id and 0 <= cut["trimmed_from"]["start"] <= 16.0
    # the whole song when it is already shorter than the cut
    client.post("/api/generate", json={"audio_id": audio_id, "quality": "turbo", "mode": "simple", "vibe": "ocean", "length_s": 60})
    assert captured["body"]["audio_id"] == audio_id


def test_simple_options_describe_the_plan(client):
    r = client.get("/api/simple/options?duration=239&energy=dense&tier=draft&bpm=90&aspect=9:16&vertical=native&length=0")
    plan = r.json()["plan"]
    assert plan["long_song"] and plan["shots"] > plan["morphs"] and plan["estimate"]["minutes"] > 5
    r = client.get("/api/simple/options?duration=239&energy=dense&tier=draft&bpm=90&aspect=9:16&vertical=native&length=60")
    assert r.json()["plan"]["duration"] == 60 and r.json()["lengths"] == [0, 60, 30, 15]


def test_desk_has_the_length_control_and_the_plan_facts():
    assert 'simpleSeg("easy-length"' in APP and 'act === "easy-length"' in APP
    assert "length_s: Number(" in APP and "length: String(easy.lengthS || 0)" in APP
    assert "function easyPlanFacts" in APP and "over a loop of" in APP
    assert "up to 15 morphs" not in APP


def test_simple_mode_turbo_run_cuts_stills_instead_of_painting(tmp_path):
    from xenoform.config import load_config
    from xenoform.director import empty_state
    from xenoform.turbo import run_turbo

    state = empty_state()
    state.update({"quality": "turbo", "live": False, "scenes": [], "mode": "simple", "vibe": "ocean", "energy_preset": "dense",
                  "aspect": "9:16"})
    work = tmp_path / "jobs" / "one"
    out = work / "xenoform.mp4"
    info = run_turbo(load_config(), DEMO, state, out, work)
    assert info["mode"] == "animatic" and info["rendered_keyframes"] == 0 and info["seconds"] < 30
    assert out.is_file() and not (work / "proof.mp4").exists()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "json", str(out)],
                           capture_output=True, text=True, check=True)
    meta = json.loads(probe.stdout)
    assert abs(float(meta["format"]["duration"]) - 12.0) < 1.0
    w = next(s["width"] for s in meta["streams"] if s.get("width"))
    h = next(s["height"] for s in meta["streams"] if s.get("height"))
    assert h > w  # the 9:16 animatic size
    manifest = json.loads((work / "turbo.json").read_text(encoding="utf-8"))
    assert manifest["proof"]["verdict"] == "stills"


def test_apply_director_without_a_story_lays_one_block_across_the_song():
    from xenoform.director import apply_director, empty_state

    features = json.loads((ROOT / "examples" / "demo_features.json").read_text(encoding="utf-8"))
    state = empty_state()
    state["blocks"] = []
    directed = apply_director(features, state)
    assert len(directed["sections"]) == 1 and abs(directed["sections"][0]["end"] - float(features["duration"])) < 1e-6
