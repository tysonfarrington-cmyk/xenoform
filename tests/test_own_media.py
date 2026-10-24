"""Your own clips and images in the Simple cut: the folder scan, the clip slots around the performer's, the
trimmed clip, and run_simple cutting a clip in 1:1 (stub renderer and compose, no GPU)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from xenoform import beatfx, dense, own_media

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo.wav"


def _clip(path: Path, seconds: float, size="320x180", fps: int = 24) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _image(path: Path) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=orange:size=64x64", "-frames:v", "1", str(path)], check=True)
    return path


def _count(path: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    return int(out.splitlines()[0])


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


def test_scan_lists_images_and_clips_long_enough(tmp_path):
    _image(tmp_path / "b.png")
    _image(tmp_path / "a.jpg")
    _clip(tmp_path / "walk.mp4", 3.0)
    _clip(tmp_path / "blink.mp4", 1.0)  # under MIN_CLIP_S: skipped
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    found = own_media.scan(tmp_path)
    assert [Path(p).name for p in found["images"]] == ["a.jpg", "b.png"]
    assert [Path(c["path"]).name for c in found["clips"]] == ["walk.mp4"] and found["clips"][0]["seconds"] == pytest.approx(3.0, abs=0.1)
    assert found["folder"] == str(tmp_path)
    with pytest.raises(FileNotFoundError):
        own_media.scan(tmp_path / "nope")


def test_clip_slots_fill_passages_around_the_performer_and_never_touch():
    shots = _story_shots()
    clips = [{"path": "a.mp4", "seconds": 5.0}, {"path": "b.mp4", "seconds": 3.0}, {"path": "c.mp4", "seconds": 30.0}]
    perf = dense.performer_slots(shots, 2)  # the intro and the drop
    slots = own_media.clip_slots(shots, clips, avoid=perf)
    # a (5 s) takes the build (one-bar shots); b (3 s) the next passage with shots short enough (the late drop);
    # c (30 s, capped at MAX_S) the calm after it
    assert [s["clip"] for s in slots] == ["a.mp4", "b.mp4", "c.mp4"]
    assert slots[0]["section"] == "build" and slots[1]["seconds"] <= 3.0 + 1e-6 and slots[2]["section"] == "calm"
    assert slots[2]["seconds"] <= own_media.MAX_S + 1e-6
    # a passage whose shots are longer than the next clip takes the first clip that fits instead: the intro has
    # two-bar shots that cannot hold b (3 s), so c opens the cut there and b waits for the build
    two = own_media.clip_slots(shots, [{"path": "b.mp4", "seconds": 3.0}, {"path": "c.mp4", "seconds": 30.0}])
    assert [s["clip"] for s in two[:2]] == ["c.mp4", "b.mp4"] and two[0]["first"] == 0 and two[1]["section"] == "build"
    for s in slots:
        assert own_media.MIN_S <= s["seconds"] <= min(own_media.MAX_S, s["clip_seconds"]) + 1e-6
        assert all(shots[i].get("section") == s["section"] for i in range(s["first"], s["last"] + 1))
        assert shots[s["first"]].get("boundary") or s["first"] == 0 or shots[s["first"]]["section"] != shots[s["first"] - 1]["section"]
    runs = sorted([(p["first"], p["last"]) for p in perf] + [(s["first"], s["last"]) for s in slots])
    for (a0, a1), (b0, b1) in zip(runs, runs[1:]):
        assert b0 > a1 + 1  # a morph shot between any two cut-in shots
    assert slots == sorted(slots, key=lambda s: s["first"])
    # without a performer the first clip opens the video; a clip too short for a shot is skipped
    first = own_media.clip_slots(shots, [{"path": "short.mp4", "seconds": 1.0}, {"path": "a.mp4", "seconds": 5.0}])
    assert first and first[0]["first"] == 0 and first[0]["clip"] == "a.mp4"
    assert own_media.clip_slots(shots, []) == [] and own_media.clip_slots([], clips) == []


def test_window_and_size():
    assert own_media.window_start(10.0, 4.0) == 3.0 and own_media.window_start(3.0, 4.0) == 0.0
    assert own_media.size_for("9:16") == (540, 960) and own_media.size_for("16:9") == (960, 540) and own_media.size_for("1:1") == (720, 720)


def test_render_clip_is_exact_and_reframed(tmp_path):
    src = _clip(tmp_path / "wide.mp4", 3.0)
    out = own_media.render_clip(src, 0.5, 48, (270, 480), tmp_path / "o" / "own.mp4")
    assert out.exists() and _count(out) == 48
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_streams",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout.strip()
    assert probe.startswith("270,480")
    # past the end of the clip the last frame is cloned: the count is still exact
    out2 = own_media.render_clip(src, 2.5, 48, (270, 480), tmp_path / "o" / "tail.mp4")
    assert _count(out2) == 48


def test_run_simple_cuts_own_clips_in_and_leads_with_own_images(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(dense, "stills_for", lambda state, n: ("ocean", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(n)]))
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    import xenoform.cloud_morph as cm
    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))])
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: 32.0)

    def fake_compose(clips, shots, audio, out, **kw):
        seen["clips"] = [Path(c).name for c in clips]
        seen["shots"] = shots
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    folder = tmp_path / "mine"
    folder.mkdir()
    _clip(folder / "skate.mp4", 6.0)
    _clip(folder / "sea.mp4", 4.0)
    found = own_media.scan(folder)
    directed = {"duration": 120.0, "beats": _beats(120.0), "analysis_sections": _sections(), "sections": [{"label": "sphere", "start": 0.0, "end": 120.0}]}
    state = {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple",
             "own_clips": found["clips"], "own_folder": found["folder"]}
    info = dense.run_simple(directed, DEMO, tmp_path / "x.mp4", tmp_path, {}, state, lambda *a: None, engine="mock")
    own = [s for s in seen["shots"] if s.get("own")]
    assert len(own) == 2 and [s["source"] for s in own] == ["sea.mp4", "skate.mp4"] and own[0]["index"] == 0  # folder order; the first clip opens the cut
    assert sum(1 for c in seen["clips"] if c.startswith("own_")) == 2
    for s in own:
        assert s["speed"] == 1.0 and s["frames"] == _count(Path(tmp_path / "simple" / "own" / f"own_{s['start']:.2f}.mp4"))
    assert info["own"]["clips"] == 2 and len(info["own"]["slots"]) == 2 and info["own"]["notes"] == []
    assert json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))["own"]["clips"] == 2
