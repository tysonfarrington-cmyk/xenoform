"""Performer shots in the Simple cut: slot picking in the story plan, merging rendered slots 1:1 into the
shots and clips, the run_simple hook (with a stub renderer), the options route and the desk row."""
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import beatfx, dense

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
        {"index": 3, "label": "calm", "start": 64.0, "end": 96.0, "level": 0.25},
        {"index": 4, "label": "release", "start": 96.0, "end": 120.0, "level": 0.3},
    ]


def _story_shots():
    directed = {"duration": 120.0, "beats": _beats(120.0), "sections": _sections()}
    shots, plan = dense.shots_for({"energy_preset": "dense", "aspect": "9:16"}, directed, None)
    assert plan["name"] == "story"
    return shots


def test_performer_choice_snaps_to_off_two_or_four():
    assert dense.performer_choice({}) == 0 and dense.performer_choice({"performer": "2"}) == 2
    assert dense.performer_choice({"performer": 3}) in (2, 4) and dense.performer_choice({"performer": 9}) == 4
    assert dense.performer_choice({"performer": "x"}) == 0


def test_performer_slots_take_the_intro_then_the_drop_and_never_touch():
    shots = _story_shots()
    two = dense.performer_slots(shots, 2)
    assert len(two) == 2
    assert two[0]["section"] == "intro" and two[0]["instrument"] == "keys" and two[0]["first"] == 0  # no stems: no fake lip-sync
    assert two[1]["section"] == "drop" and two[1]["instrument"] == "drums"
    # with a vocal stem that sings in the intro she sings (lip-synced to the real vocal); silent elsewhere stays keys/drums
    n = int(120 * 24)
    vocals = [1.0 if t < 16 * 24 else 0.02 for t in range(n)]
    env = {"fps": 24, "frames": n, "engine": "demucs:htdemucs", "vocals": vocals, "drums": [0.5] * n, "bass": [0.5] * n, "other": [0.3] * n}
    sung = dense.performer_slots(shots, 2, env)
    assert sung[0]["instrument"] == "voice" and sung[0]["vocal"] > 0.9 and sung[1]["instrument"] == "drums"
    assert all(sl["instrument"] == "guitar" for sl in dense.performer_slots(shots, 2, env, style="guitar"))
    assert dense.performer_slots(shots, 2, env, style="sing")[1]["instrument"] == "voice"
    for sl in two:
        assert dense.PERFORMER_MIN_S <= sl["seconds"] <= dense.PERFORMER_MAX_S + 1e-6
        assert all(shots[i].get("section") == sl["section"] for i in range(sl["first"], sl["last"] + 1))
    four = dense.performer_slots(shots, 4)
    assert 2 <= len(four) <= 4 and four == sorted(four, key=lambda c: c["first"])
    for a, b in zip(four, four[1:]):
        assert b["first"] > a["last"] + 1  # a morph shot between performer slots
    assert dense.performer_slots(shots, 0) == []
    assert dense.performer_slots([{"start": 0.0, "end": 2.0, "seconds": 2.0, "frames": 48, "section": "calm"}], 2) == []


def test_performer_slots_auto_mix_drums_on_the_drop_and_dance_elsewhere():
    shots = _story_shots()
    four = dense.performer_slots(shots, 4)
    assert len(four) == 4
    by = {sl["section"]: sl["instrument"] for sl in four}
    kinds = [sl["instrument"] for sl in four]
    assert by["intro"] == "keys" and by["drop"] == "drums"  # the opening on keys, the drop on the kit, whatever comes first in time
    assert by.get("build") == "dance" and kinds.count("dance") >= 2  # the other loud passage dances; the next quiet one too
    assert all(sl["instrument"] == "dance" for sl in dense.performer_slots(shots, 4, style="dance"))


def test_apply_performer_slots_merges_the_run_into_one_shot_playing_the_clip():
    shots = _story_shots()
    clips = [Path(f"m{i:02d}.mp4") for i in range(len(shots))]
    slots = dense.performer_slots(shots, 2)
    rendered = {sl["first"]: {"clip": Path(f"perf{sl['first']}.mp4")} for sl in slots}
    merged, mclips = dense.apply_performer_slots(shots, clips, slots, rendered)
    removed = sum(sl["last"] - sl["first"] for sl in slots)
    assert len(merged) == len(shots) - removed and len(mclips) == len(merged)
    assert sum(s["frames"] for s in merged) == sum(s["frames"] for s in shots)
    perf = [s for s in merged if s.get("performer")]
    assert len(perf) == 2 and all(s["speed"] == 1.0 and s["render_s"] is None for s in perf)
    assert perf[0]["start"] == shots[0]["start"] and perf[0]["end"] == shots[slots[0]["last"]]["end"]
    assert mclips[0] == Path(f"perf{slots[0]['first']}.mp4") and mclips[1] == clips[slots[0]["last"] + 1]
    assert all(e["type"] == "punch" for s in perf for e in s["effects"])
    # a slot that failed to render leaves its shots alone
    half = {slots[0]["first"]: rendered[slots[0]["first"]]}
    m2, c2 = dense.apply_performer_slots(shots, clips, slots, half)
    assert sum(1 for s in m2 if s.get("performer")) == 1


def _tiny_clip(path: Path, seconds: float, colour: str = "green") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=64x112:r=24:d={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_run_simple_renders_performer_slots_and_hands_merged_shots_to_compose(tmp_path, monkeypatch):
    seen = {}
    calls = []
    monkeypatch.setattr(dense, "stills_for", lambda state, n: ("ocean", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(n)]))
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    import xenoform.cloud_morph as cm
    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))])

    def fake_render(audio_path, slot, vibe, still, work, cfg, *, seed, report=None, beats=None):
        calls.append((slot["section"], slot["instrument"], round(slot["seconds"], 2), seed, Path(still).name))
        clip = _tiny_clip(Path(work) / f"perf_{slot['first']}.mp4", slot["seconds"])
        return {"clip": clip, "frames": int(round(slot["seconds"] * 24)), "seconds": slot["seconds"], "sync": 0.8, "tries": 1}

    monkeypatch.setattr(dense, "_render_performer", fake_render)
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: 32.0)  # the demo wav is 12 s; the plan is the story's

    def fake_compose(clips, shots, audio, out, **kw):
        seen["clips"] = [Path(c).name for c in clips]
        seen["shots"] = shots
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    directed = {"duration": 120.0, "beats": _beats(120.0), "analysis_sections": _sections(), "sections": [{"label": "sphere", "start": 0.0, "end": 120.0}]}
    state = {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "performer": 2}
    info = dense.run_simple(directed, DEMO, tmp_path / "x.mp4", tmp_path, {}, state, lambda *a: None, engine="mock")
    assert len(calls) == 2 and calls[0][0] == "intro" and calls[0][1] == "keys" and calls[1][1] == "drums"
    assert calls[0][4].startswith("polly") and calls[0][4].endswith(".png")  # the bundled reference, posed for the instrument when that still ships
    perf = [s for s in seen["shots"] if s.get("performer")]
    assert len(perf) == 2 and sum(1 for c in seen["clips"] if c.startswith("perf_")) == 2
    assert info["performer"]["shots"] == 2 and len(info["performer"]["slots"]) == 2 and info["performer"]["slots"][0]["sync"] == 0.8
    assert json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))["performer"]["shots"] == 2
    # a failing renderer skips the slot and the cut still happens
    calls.clear()

    def boom(*a, **k):
        raise RuntimeError("no H3 here")

    monkeypatch.setattr(dense, "_render_performer", boom)
    info2 = dense.run_simple(directed, DEMO, tmp_path / "y.mp4", tmp_path / "y", {}, state, lambda *a: None, engine="mock")
    assert info2["performer"]["shots"] == 0 and len(info2["performer"]["notes"]) == 2
    assert not any(s.get("performer") for s in seen["shots"])


def test_plan_summary_adds_the_performer_time():
    base = dense.plan_summary(120.0, _beats(120.0), "dense", "draft", "9:16")
    with_perf = dense.plan_summary(120.0, _beats(120.0), "dense", "draft", "9:16", performer=2)
    assert with_perf["performer"] == 2 and with_perf["estimate"]["performer_seconds"] > 0
    assert with_perf["estimate"]["seconds"] > base["estimate"]["seconds"]
    assert dense.plan_summary(20.0, _beats(20.0), "dense", "draft", "9:16", performer=2)["performer"] == 0  # clips: no slots


@pytest.fixture(scope="module")
def client():
    from xenoform.ui import create_app

    return TestClient(create_app())


def test_options_route_reports_the_performer_status(client):
    r = client.get("/api/simple/options?duration=120&energy=dense&tier=draft&bpm=120&aspect=9:16&performer=2")
    body = r.json()
    assert body["performer"]["choices"] == [0, 2, 4] and "ok" in body["performer"]
    assert body["plan"]["performer"] == 2 and body["plan"]["estimate"]["performer_seconds"] > 0


def test_desk_has_the_performer_row_and_payload_key():
    assert "function performerRow" in APP and 'simpleSeg("easy-performer"' in APP
    assert 'act === "easy-performer"' in APP and "performer: Number((state.easy && state.easy.performer) || 0)" in APP
    assert "MiniMax H3" in APP and "polly" in APP.lower()
    assert (ROOT / "src" / "xenoform" / "ui_static" / "performer" / "polly.png").stat().st_size > 100_000
