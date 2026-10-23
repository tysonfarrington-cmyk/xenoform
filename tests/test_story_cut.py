"""The story plan (verses breathe, choruses drive, the drop punches), premium transitions at section boundaries
inside compose, and re-cutting a finished Simple video from its cached morphs."""
import json
import subprocess
import threading
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from xenoform import beatfx, dense
from xenoform.cloud_morph import custom_shots

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo.wav"
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")


def _beats(duration: float, bpm: float = 120.0) -> list[float]:
    step = 60.0 / bpm
    return [round(i * step, 4) for i in range(int(duration / step))]


def _sections():
    return [
        {"index": 0, "label": "calm", "start": 0.0, "end": 16.0, "level": 0.2},
        {"index": 1, "label": "build", "start": 16.0, "end": 32.0, "level": 0.6},
        {"index": 2, "label": "drop", "start": 32.0, "end": 64.0, "level": 1.0},
        {"index": 3, "label": "calm", "start": 64.0, "end": 80.0, "level": 0.25},
        {"index": 4, "label": "calm", "start": 80.0, "end": 96.0, "level": 0.9},
        {"index": 5, "label": "release", "start": 96.0, "end": 120.0, "level": 0.3},
    ]


def test_story_plan_breathes_drives_and_punches():
    beats = _beats(120.0)  # 120 bpm: a bar is 2 s
    plan = dense.story_plan(120.0, beats, _sections(), drop=32.0)
    shots = custom_shots(plan, 120.0)
    assert plan["name"] == "story" and plan["drop"] == 32.0
    by = {}
    for raw in plan["shots"]:
        by.setdefault(raw["section"], []).append(raw["end"] - raw["start"])
    assert by["intro"] and min(by["intro"]) >= 3.9  # two bars a shot in the intro
    assert by["build"] and max(by["build"]) <= 2.1  # a bar a shot in the build
    assert by["drop"] and max(by["drop"]) <= 1.1  # half bars on the drop
    assert "drop_late" in by and min(by["drop_late"]) >= 1.9  # then back to bars
    assert "outro" in by and min(by["outro"]) >= 3.9
    roles = [r[0] for r in plan["roles"]]
    assert roles == ["intro", "build", "drop", "calm", "build", "outro"]  # a loud "calm" section drives
    first_drop = next(s for s in plan["shots"] if abs(s["start"] - 32.0) < 1e-3)
    assert first_drop["boundary"] == "drop" and {e["type"] for e in first_drop["effects"]} == {"punch", "stutter"}
    assert sum(1 for s in plan["shots"] if s.get("boundary")) == 5  # every section switch
    assert plan["shots"][0]["ease"] == "in" and plan["shots"][-1]["ease"] == "out"
    assert shots[-1]["end"] == pytest.approx(120.0) and len(shots) <= dense.shot_budget(120.0)


def test_story_plan_respects_the_shot_budget():
    beats = _beats(600.0, 160.0)
    secs = [{"index": i, "label": "drop", "start": i * 60.0, "end": (i + 1) * 60.0, "level": 1.0} for i in range(10)]
    plan = dense.story_plan(600.0, beats, secs, drop=0.0, max_shots=60)
    assert len(plan["shots"]) <= 60


def test_shots_for_uses_the_story_plan_for_long_songs_with_sections():
    directed = {"duration": 120.0, "beats": _beats(120.0), "sections": _sections()}
    shots, plan = dense.shots_for({"energy_preset": "dense", "aspect": "9:16"}, directed, None)
    assert plan["name"] == "story" and any(s.get("boundary") for s in shots) and all("section" in s for s in shots)
    short = {"duration": 20.0, "beats": _beats(20.0), "sections": _sections()[:2]}
    _, plan2 = dense.shots_for({"energy_preset": "dense"}, short, None)
    assert plan2["name"].startswith("dense")  # a clip keeps the demo1 plan


def test_boundary_transitions_follow_the_vibe_and_the_cap():
    from xenoform import transitions_fx as T

    shots = [{"frames": 48}] + [{"frames": 48, "boundary": "switch"}] * 5 + [{"frames": 48, "boundary": "drop"}]
    trans = dense.boundary_transitions(shots, "cosmic", seed=1)
    assert trans[0] is None and len(trans) == len(shots)
    kinds = [t["kind"] for t in trans if t]
    assert kinds and all(k in T.TRANSITIONS for k in kinds)
    assert all(kinds.count(k) <= 2 for k in set(kinds))  # the guardrail: never more than two of a type
    assert all(4 <= t["frames"] <= 12 for t in trans if t)


def _tiny_clip(path: Path, seconds: float, colour: str, w: int = 64, h: int = 112) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s={w}x{h}:r=24:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _wav(path: Path, seconds: float, sr: int = 22050) -> Path:
    t = np.arange(int(seconds * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return path


def test_compose_keeps_the_frame_count_through_a_transition(tmp_path):
    a = _tiny_clip(tmp_path / "a.mp4", 1.0, "red")
    b = _tiny_clip(tmp_path / "b.mp4", 1.0, "blue")
    audio = _wav(tmp_path / "s.wav", 2.0)
    shots = custom_shots({"shots": [{"start": 0.0, "end": 1.0, "render_s": 2}, {"start": 1.0, "end": 2.0, "render_s": 2}]}, 2.0)
    out = tmp_path / "out.mp4"
    made = beatfx.compose([a, b], shots, audio, out, aspect="9:16", fx=False, dance_fx="off", stem_orbit=False,
                          transitions=[None, {"kind": "lens-breath", "frames": 8}], size=(64, 112))
    assert made["frames"] == 48 and made["transitions"] == ["lens-breath"]
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True)
    assert int(probe.stdout.strip()) == 48
    plain = beatfx.compose([a, b], shots, audio, tmp_path / "plain.mp4", aspect="9:16", fx=False, dance_fx="off",
                           stem_orbit=False, size=(64, 112))
    assert plain["frames"] == 48 and plain["transitions"] == []


def test_recut_from_cache_recomposes_without_the_gpu(tmp_path, monkeypatch):
    job = tmp_path / "jobs" / "abc"
    work = job / "simple"
    work.mkdir(parents=True)
    a = _tiny_clip(work / "local00.mp4", 1.0, "red")
    b = _tiny_clip(work / "local01.mp4", 1.0, "blue")
    audio = _wav(tmp_path / "song.wav", 2.0)
    shots = custom_shots({"shots": [{"start": 0.0, "end": 1.0, "render_s": 2}, {"start": 1.0, "end": 2.0, "render_s": 2}]}, 2.0)
    rec = {"plan_shots": shots, "shots": shots, "clips": [str(a), str(b)], "audio_path": str(audio), "vibe": "black", "tier": "draft",
           "size": [64, 112], "fps": 24, "seed": 3, "plan_name": "dense (auto)", "vertical_house": True,
           "recut_state": {"vibe": "black", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense",
                           "dance_fx": "off", "stem_orbit": False, "beat_fx": False, "macros": {"intensity": 0.5}}}
    (work / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    (job / "xenoform.mp4").write_bytes(b"old")
    seen = {}

    def spy(clips, shots_, audio_, out, **kw):
        seen.update(kw)
        seen["clips"] = list(clips)
        Path(out).write_bytes(b"new")
        return {"frames": 48, "seconds": 2.0, "size": "64x112", "aspect": "9:16", "fx": False, "overlay": False, "centres": [],
                "fps": 24, "look": {"dance_fx": kw.get("dance_fx")}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    out = dense.recut_from_cache(job, {"macros": {"intensity": 1.0, "glow": 0.9}, "dance_fx": "noir-glow", "stem_orbit": True})
    assert seen["clips"] == [a, b] and seen["dance_fx"] == "noir-glow" and seen["stem_orbit"] is True
    assert seen["macros"]["glow"] == 0.9 and seen["adaptive"] is False and seen["size"] == (64, 112)
    assert (job / "xenoform.mp4").read_bytes() == b"new" and out["recuts"] == 1 and out["look"]["dance_fx"] == "noir-glow"
    assert json.loads((work / "simple.json").read_text(encoding="utf-8"))["recut_state"]["dance_fx"] == "noir-glow"
    with pytest.raises(FileNotFoundError):
        dense.recut_from_cache(tmp_path / "jobs" / "nope")


@pytest.fixture(scope="module")
def client():
    from xenoform.ui import create_app

    return TestClient(create_app())


def test_recut_route_bumps_the_video_version(client, monkeypatch):
    from xenoform import dense as dense_mod, ui as ui_mod

    folder = ui_mod.work_dir() / "jobs" / "recut-test"
    (folder / "simple").mkdir(parents=True, exist_ok=True)
    (folder / "simple" / "simple.json").write_text("{}", encoding="utf-8")
    with ui_mod._LOCK:
        ui_mod._JOBS["recut-test"] = {"id": "recut-test", "status": "done", "stage": "done", "progress": 1.0, "video_version": 3,
                                      "video": "/api/jobs/recut-test/video?v=3", "detail": "Cut ready"}
    done = threading.Event()

    def fake_recut(job_dir, overrides=None, report=None, cfg=None):
        assert Path(job_dir).name == "recut-test" and overrides["dance_fx"] == "warm-leak"
        if report:
            report("assemble", 0.5, "half")
        done.set()
        return {"look": {"dance_fx": "warm-leak"}, "recuts": 2}

    monkeypatch.setattr(dense_mod, "recut_from_cache", fake_recut)
    r = client.post("/api/jobs/recut-test/recut", json={"dance_fx": "warm-leak", "macros": {"glow": 1.0}})
    assert r.status_code == 200 and r.json()["status"] == "running"
    assert done.wait(10)
    for _ in range(50):
        job = client.get("/api/jobs/recut-test").json()
        if job["status"] == "done" and job.get("video_version") == 4:
            break
        import time

        time.sleep(0.1)
    assert job["video_version"] == 4 and job["video"].endswith("?v=4") and job["recuts"] == 2
    assert client.post("/api/jobs/nope/recut", json={}).status_code == 404


def test_desk_offers_the_re_cut_on_the_result_screen():
    assert 'data-act="easy-recut-knobs"' in APP and "async function recutWithKnobs" in APP
    assert APP.count('<div class="simple-knobs"></div>') == 2  # the first screen and the result screen
    assert "/recut`" in APP and "poll(id);" in APP.split("async function recutWithKnobs")[1].split("async function easyMake")[0]
