"""The timeline (26 Oct 2026, docs/TIMELINE.md): a cut edited shot by shot and boundary by boundary on top of the cached
morphs. Per shot a hold, a look and an FX intensity; per boundary a cut (a hold on the shot before) and the dressing (a
premium transition or a boundary kind); ``recut_from_cache`` takes and persists the overrides, the pair renderer makes
one morph again with another seed (``rerender_morph``); ``lane.build`` reads it all back; the route beside ``swap``; the
desk's Timeline panel. The generated run is in test_timeline_insert.py."""
import json
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from xenoform import beatfx, boundary_fx as B, dense, foreshadow as F, lane, stills as S
from xenoform.cloud_morph import custom_shots, shot_indices

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "src/xenoform/ui_static/app.css").read_text(encoding="utf-8")
DEMO = ROOT / "examples" / "demo.wav"
W, H = 512, 288


# ---------------------------------------------------------------------------------------------- fixtures


def _object(path: Path, *, cx=0.5, cy=0.5, r=0.2, noise=3) -> Path:
    im = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(im)
    rr = r * H
    d.ellipse((cx * W - rr, cy * H - rr, cx * W + rr, cy * H + rr), fill=(170, 175, 180))
    a = np.asarray(im).astype(np.int16)
    rng = np.random.default_rng(int(cx * 1000 + cy * 100 + r * 10))
    a = np.clip(a + rng.integers(-noise, noise + 1, a.shape), 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path)
    return path


def _grown(vibe: str, name: str, noun: str, *, kind: str = "object", cx: float = 0.5) -> str:
    """A grown still on disk and in stills.json (the conftest points XENO_STILLS at a temp dir)."""
    _object(S.root() / vibe / name, cx=cx)
    idx = S._read_json(S.index_path(), {})
    row = {"file": f"{vibe}/{name}", "noun": noun}
    if kind == "scene":
        row["kind"] = "scene"
    idx.setdefault(vibe, []).append(row)
    S._write_json(S.index_path(), idx)
    return row["file"]


def _fake_compose(seen):
    def compose(clips, shots, audio, out, **kw):
        seen["clips"] = [str(c) for c in clips]
        seen["shots"] = [dict(s) for s in shots]
        seen["kw"] = kw
        seen["calls"] = seen.get("calls", 0) + 1
        Path(out).write_bytes(b"new")
        return {"frames": 1, "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": [t["kind"] for t in (kw.get("transitions") or []) if t]}

    return compose


def _cut(tmp_path, monkeypatch, seen, *, story: bool = False) -> Path:
    """A Simple cut on the mock engine over the shipped cosmic pool (real jpgs), the morph clips stubbed, the compose spied."""
    import xenoform.cloud_morph as cm

    def fake_mock(shots, stills, work, w, h):
        out = []
        for i in range(len(shots)):
            p = Path(work) / f"mock{i:02d}.mp4"
            p.write_bytes(b"mp4")
            out.append(p)
        return out

    real = cm._mock_clips
    monkeypatch.setattr(cm, "_mock_clips", fake_mock)
    monkeypatch.setattr(beatfx, "compose", _fake_compose(seen))
    monkeypatch.setattr(S, "usage", lambda: {})
    job = tmp_path / "jobs" / "cut"
    job.mkdir(parents=True)
    state = {"vibe": "cosmic", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense"}
    dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, DEMO, job / "xenoform.mp4", job, {}, state,
                     lambda *a: None, engine="mock")
    monkeypatch.setattr(cm, "_mock_clips", real)  # the pair renderer cross-fades the real stills through ffmpeg
    seen.clear()
    return job


def _rec(job: Path) -> dict:
    return json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))


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


# ---------------------------------------------------------------------------------------------- the overrides


def test_the_override_maps_normalise_and_a_cut_is_a_hold_on_the_shot_before():
    so = dense.shot_overrides_of({"0": {"play": "hold", "look": "auto"}, "1": {"play": "morph", "look": "Noir-Glow", "fx_intensity": "1.7"},
                                  "2": {}, "9": {"play": "hold"}, "x": {"play": "hold"}, "3": {"fx_intensity": 0.33333}}, 5)
    assert so == {0: {"play": "hold"}, 1: {"look": "noir-glow", "fx_intensity": 1.0}, 3: {"fx_intensity": 0.333}}
    assert dense.shot_overrides_of([{"play": "hold"}, None, {"look": "off"}], 3) == {0: {"play": "hold"}, 2: {"look": "off"}}
    bo = dense.boundary_overrides_of({"0": {"fx": "smear"}, "1": {"fx": "SMEAR"}, "2": {"fx": "match-cut", "handoff": "cut"},
                                      "3": {"fx": "scene-morph"}, "4": {"fx": "auto"}, "5": {"handoff": "morph"}, "6": {"fx": "none"}}, 7)
    assert bo == {1: {"fx": "smear"}, 2: {"fx": "match-cut", "handoff": "cut"}, 5: {"handoff": "morph"}, 6: {"fx": "none"}}
    so2, bo2 = dense.fold_handoffs({4: {"play": "hold", "look": "off"}}, bo)
    assert so2 == {1: {"play": "hold"}, 4: {"look": "off"}} and bo2 == {1: {"fx": "smear"}, 2: {"fx": "match-cut"}, 6: {"fx": "none"}}


def test_a_held_shot_plays_its_first_frame_and_the_layers_know_the_join_after_it_is_a_cut(tmp_path):
    shot = {"start": 0.0, "end": 1.0, "frames": 24, "render_s": 2, "speed": 2.0, "effects": [{"type": "stutter", "t": 0.5}]}
    assert shot_indices(shot, 49).tolist() != [0] * 24
    held = dict(shot, hold=True)
    assert shot_indices(held, 49).tolist() == [0] * 24
    # the boundary plan and the foreshadow plan: out of a held shot the next picture is the next shot's first frame, and the
    # held shot's own edge is its first frame, not the clip's last
    reads = []

    def read_edge(clip, which):
        reads.append((Path(clip).name, which))
        return np.full((4, 4, 3), {"first": 10, "last": 200}[which], dtype=np.uint8)

    shots = [{"start": 0.0, "end": 1.0, "frames": 24, "hold": True, "cut_out": True}, {"start": 1.0, "end": 2.0, "frames": 24},
             {"start": 2.0, "end": 3.0, "frames": 24}]
    clips = [Path("a.mp4"), Path("b.mp4"), Path("c.mp4")]
    picks = [None, B.make(shots, 1, "rip", [0.5 * i for i in range(8)], 24), B.make(shots, 2, "wipe", [0.5 * i for i in range(8)], 24)]
    assert picks[1]["kind"] == "rip" and picks[1]["user"] is True and picks[2]["variant"] == "strips"
    entries = B.plan(picks, shots, clips, read_edge=read_edge)
    assert int(entries[0]["tail"]["other"][0, 0, 0]) == 10  # into shot 1 across the cut: shot 1's first frame arrives
    assert int(entries[1]["head"]["other"][0, 0, 0]) == 10  # the object that left: the held shot's first frame
    assert int(entries[1]["tail"]["other"][0, 0, 0]) == 200 and int(entries[2]["head"]["other"][0, 0, 0]) == 200  # a morph landing as before
    fs = F.plan(shots, clips, [0.5 * i for i in range(8)], 24, "trace", F.params({}), read_edge=read_edge)
    assert fs[0]["which"] == "first" and int(fs[1]["prev"][0, 0, 0]) == 10 and fs[1]["echo"] > 0  # the echo rides out of the hold
    assert fs[1]["which"] == "last"
    assert B.make(shots, 0, "rip", [], 24) is None and B.make(shots, 1, "nope", [], 24) is None
    assert B.make([{"frames": 2}, {"frames": 40}], 1, "smear", [], 24) is None  # too short for a window


def test_compose_holds_a_shot_and_grades_one_shot_with_its_own_look(tmp_path):
    a = _tiny_clip(tmp_path / "a.mp4", 1.0, "red")
    b = _tiny_clip(tmp_path / "b.mp4", 1.0, "blue")
    audio = _wav(tmp_path / "song.wav", 2.0)
    shots = custom_shots({"shots": [{"start": 0.0, "end": 1.0, "render_s": 2}, {"start": 1.0, "end": 2.0, "render_s": 2}]}, 2.0)
    # a fade clip: red to blue over its length, so a held shot shows red throughout and a played one ends blue
    fade = tmp_path / "fade.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a), "-i", str(b), "-filter_complex", "[0:v][1:v]xfade=transition=fade:duration=0.9:offset=0.05,format=yuv420p",
                    "-t", "1.0", str(fade)], check=True)
    shots[0]["hold"] = True
    shots[1]["dance_fx"] = "noir-glow"
    out = tmp_path / "cut.mp4"
    made = beatfx.compose([fade, fade], shots, audio, out, aspect="9:16", fx=False, dance_fx="off", stem_orbit=False, size=(64, 112))
    frames = beatfx.read_frames(out)
    assert made["frames"] == 48 and len(frames) == 48
    first_half = frames[:24].astype(int)
    assert first_half.std(axis=0).max() < 6  # held: the same frame throughout
    assert first_half[0, :, :, 0].mean() > 150 and first_half[0, :, :, 2].mean() < 90  # red, the clip's first frame
    assert frames[47, :, :, 2].mean() > 100  # the second shot played the morph through to blue
    assert any(role.startswith("1:") and "noir-glow" in role for role in made["look"]["roles"])  # the shot's own look ran
    assert not any(role.startswith("0:") for role in made["look"]["roles"])  # the cut's look stayed off


def test_recut_takes_the_overrides_persists_them_and_a_later_recut_keeps_them(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    before = _rec(job)
    n = len(before["shots"])
    assert n >= 5
    out = dense.recut_from_cache(job, {"shot_overrides": {"1": {"play": "hold"}, "2": {"look": "noir-glow", "fx_intensity": 0.2}},
                                       "boundary_overrides": {"3": {"fx": "rip"}, "4": {"fx": "lens-breath"}, "2": {"handoff": "cut"}}})
    shots = seen["shots"]
    assert shots[1]["hold"] is True and shots[1]["cut_out"] is True and "hold" not in shots[0] and "hold" not in shots[3]
    assert shots[2]["dance_fx"] == "noir-glow" and shots[2]["fx_intensity"] == 0.2 and "dance_fx" not in shots[3]
    assert shots[3]["fx_intensity"] != 0.2  # the knob's value elsewhere
    bx, tr = seen["kw"]["boundary_fx"], seen["kw"]["transitions"]
    assert bx[3]["kind"] == "rip" and bx[3]["user"] is True and bx[4] is None
    assert tr[4] == {"kind": "lens-breath", "frames": tr[4]["frames"], "boundary": "timeline", "user": True} and tr[3] is None
    assert out["shot_overrides"] == {"1": {"play": "hold"}, "2": {"look": "noir-glow", "fx_intensity": 0.2}}  # the cut folded onto shot 1
    assert out["boundary_overrides"] == {"3": {"fx": "rip"}, "4": {"fx": "lens-breath"}} and out["timeline"]["shots"] == 2
    on_disk = _rec(job)
    assert on_disk["shot_overrides"] == out["shot_overrides"] and on_disk["shots"][1]["hold"] is True
    # a plain knob re-cut keeps them; an empty map clears them; "none" clears what the pickers chose
    seen.clear()
    again = dense.recut_from_cache(job, {"macros": {"chaos": 1.0}})
    assert seen["shots"][1]["hold"] is True and seen["kw"]["boundary_fx"][3]["kind"] == "rip" and again["shot_overrides"] == out["shot_overrides"]
    assert any(seen["kw"]["boundary_fx"][i] for i in range(n) if i != 3)  # Chaos 1 gives the other boundaries kinds
    seen.clear()
    dense.recut_from_cache(job, {"shot_overrides": {}, "boundary_overrides": {"5": {"fx": "none"}}})  # Chaos 1 stays in the record
    assert "hold" not in seen["shots"][1] and seen["kw"]["boundary_fx"][5] is None
    assert not (seen["kw"]["boundary_fx"][3] or {}).get("user")  # the hand-picked rip is gone; the picker may still give it one
    assert _rec(job)["shot_overrides"] == {} and _rec(job)["boundary_overrides"] == {"5": {"fx": "none"}}
    # an unknown look is a note, not a crash; a premium kind past the cap is kept and noted
    seen.clear()
    out = dense.recut_from_cache(job, {"shot_overrides": {"0": {"look": "glitter"}}, "boundary_overrides": {str(i): {"fx": "match-cut"} for i in range(1, 4)}})
    assert any("glitter" in note for note in out["timeline"]["notes"]) and "dance_fx" not in seen["shots"][0]
    assert [t["kind"] for t in seen["kw"]["transitions"] if t] == ["match-cut"] * 3 and any("past the house cap" in note for note in out["timeline"]["notes"])


# ---------------------------------------------------------------------------------------------- the pair renderer


def test_a_rerender_replaces_one_clip_with_a_new_seed_and_logs_it(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    before = _rec(job)
    old_clips = list(before["clips"])
    seeds = []
    import xenoform.cloud_morph as cm

    real = cm._mock_clips

    def spy(shots, stills, work, w, h):
        seeds.append([s.get("kind") for s in stills])
        return real(shots, stills, work, w, h)

    monkeypatch.setattr(cm, "_mock_clips", spy)
    reports = []
    rec = dense.rerender_morph(job, 3, report=lambda stage, frac, detail: reports.append(detail))
    assert rec["clips"][3] != old_clips[3] and [c for i, c in enumerate(rec["clips"]) if i != 3] == [c for i, c in enumerate(old_clips) if i != 3]
    assert Path(rec["clips"][3]).parent == job / "simple" / "rerenders" / "00" and Path(rec["clips"][3]).name == "morph03.mp4"
    assert Path(rec["clips"][3]).stat().st_size > 1000
    log = rec["rerenders"]
    assert len(log) == 1 and log[0]["shot"] == 3 and log[0]["morph"] == 3 and log[0]["seed"] == before["seed"] + 3 + 1009
    assert log[0]["variant"] == "auto" and log[0]["render_s"] == before["plan_shots"][3]["render_s"] and rec["recuts"] == 1
    assert seen["calls"] == 1 and seen["clips"] == rec["clips"] and any("Re-rendering shot 4" in d for d in reports)
    assert seeds == [[None, None]]  # auto: the stills' own kinds
    # again: the next seed in the shot's sequence; a given seed, a length and a variant are honoured
    rec = dense.rerender_morph(job, 3)
    assert rec["rerenders"][1]["seed"] == before["seed"] + 3 + 2 * 1009 and Path(rec["clips"][3]).parent.name == "01"
    seconds = float(before["plan_shots"][3]["seconds"])
    rec = dense.rerender_morph(job, 3, seed=77, render_s=5, variant="scene-object")
    assert rec["rerenders"][2]["seed"] == 77 and rec["rerenders"][2]["render_s"] == 5 and seeds[-1] == ["scene", "object"]
    assert rec["plan_shots"][3]["render_s"] == 5 and rec["plan_shots"][3]["speed"] == round(5 / seconds, 3) and rec["shots"][3]["render_s"] == 5
    assert rec["shots"][3]["frames"] == before["plan_shots"][3]["frames"]  # the beat timing never moves
    # the refusals
    with pytest.raises(ValueError, match="not one of them"):
        dense.rerender_morph(job, 99)
    with pytest.raises(ValueError, match="2 to 5"):
        dense.rerender_morph(job, 2, render_s=9)
    with pytest.raises(ValueError, match="variant"):
        dense.rerender_morph(job, 2, variant="wild")
    rec_path = job / "simple" / "simple.json"
    polly = dict(rec["plan_shots"][2], performer=True)
    rec["plan_shots"][2] = polly
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(ValueError, match="Polly"):
        dense.rerender_morph(job, 2)
    rec_path.write_text(json.dumps(dict(rec, tier="final")), encoding="utf-8")
    with pytest.raises(ValueError, match="Final"):
        dense.rerender_morph(job, 3)
    with pytest.raises(FileNotFoundError):
        dense.rerender_morph(tmp_path / "jobs" / "none", 0)


def test_a_rerender_on_the_real_engine_goes_through_the_pair_renderer_with_the_seed(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec_path = job / "simple" / "simple.json"
    rec = _rec(job)
    rec["engine"] = "LTX 0.9.5 (Draft)"
    rec["seed"] = 4242
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    wfs = []

    class WF:
        def __init__(self):
            self.inputs = {}

        def set_input(self, node, key, value):
            self.inputs[(node, key)] = value

    class Out:
        type = "video"

        def to_file(self, path):
            Path(path).write_bytes(b"pair")

    class Job:
        def result(self):
            class R:
                outputs = [Out()]

                def get_outputs(self, node):
                    return [Out()]

            return R()

    class Client:
        class assets:
            @staticmethod
            def from_file(path):
                return path

        class workflows:
            @staticmethod
            def from_file(path):
                wf = WF()
                wfs.append(wf)
                return wf

        def submit(self, wf):
            return Job()

    out = dense.rerender_morph(job, 2, seed=9000, cfg={}, client=Client())
    assert len(wfs) == 1 and wfs[0].inputs[("13", "noise_seed")] == 9000
    assert Path(wfs[0].inputs[("6", "image")]).name == Path(rec["stills"][2]).name and Path(wfs[0].inputs[("7", "image")]).name == Path(rec["stills"][3]).name
    assert Path(out["clips"][2]).read_bytes() == b"pair"
    out = dense.rerender_morph(job, 2, variant="object-scene", cfg={}, client=Client())
    assert "wide landscape scene" in wfs[1].inputs[("3", "text")] and wfs[1].inputs[("13", "noise_seed")] == 4242 + 2 + 2 * 1009


# ---------------------------------------------------------------------------------------------- the lane


def test_the_lane_reads_the_overrides_the_handoffs_and_the_choices():
    info = {"shots": [{"start": 0.0, "end": 2.0, "morph": 0, "section": "intro"}, {"start": 2.0, "end": 4.0, "morph": 1, "section": "drop", "boundary": "drop"},
                      {"start": 4.0, "end": 6.0, "morph": 2, "section": "drop", "hold": True}, {"start": 6.0, "end": 8.0, "morph": 3, "section": "drop"},
                      {"start": 8.0, "end": 10.0, "performer": True, "section": "outro"}],
            "stills": ["v/00_a.jpg", "v/01_b.jpg", "v/02_c.jpg", "v/03_d.jpg", "v/04_e.jpg"], "clips": ["a", "b", "c", "d", "e"], "tier": "draft",
            "shot_overrides": {"2": {"play": "hold", "look": "off", "fx_intensity": 0.5}}, "boundary_overrides": {"1": {"fx": "rip"}, "3": {"fx": "none"}},
            "boundary_fx": [None, {"kind": "rip", "variant": "", "user": True}, None, None, None],
            "transitions": [None, None, {"kind": "match-cut", "frames": 8}, None, None], "rerenders": [{"shot": 3}, {"shot": 3}],
            "performer": {"slots": [{"first": 4, "last": 4, "instrument": "drums"}]}, "drop": 2.0, "beats": [0.5, 1.0]}
    out = lane.build(info, "x")
    rows = out["shots"]
    assert rows[2]["hold"] is True and rows[2]["look"] == "off" and rows[2]["fx_intensity"] == 0.5 and "hold" not in rows[1]
    assert rows[1]["fx_override"] == "rip" and rows[1]["transition"] == "chromatic rip" and rows[1]["transition_id"] == "rip" and rows[1]["kind"] == "rip"
    assert rows[2]["transition"] == "match-cut" and rows[2]["transition_id"] == "match-cut" and rows[3]["fx_override"] == "none"
    assert rows[3]["rerendered"] == 2 and "rerendered" not in rows[2]
    assert [r.get("handoff") for r in rows] == [None, "morph", "morph", "cut", "cut"]  # out of the hold, and into Polly
    assert rows[0]["morph"] == 0 and rows[4].get("performer") is True and "still" not in rows[4]
    assert out["shot_overrides"] == info["shot_overrides"] and out["boundary_overrides"] == info["boundary_overrides"]
    assert out["rerenders"] == 2 and out["inserts"] == 0 and out["editable"] is True and out["rerenderable"] is True
    assert out["drop"] == 2.0 and out["beats"] == [0.5, 1.0]
    kinds = out["choices"]["transition_kinds"]
    ids = [k["id"] for k in kinds]
    assert "scene-morph" not in ids and {"match-cut", "lens-breath", "black-hold", "cut", "smear", "strobe", "wipe", "rip"} <= set(ids)
    assert [k["group"] for k in kinds if k["id"] in ("match-cut", "smear")] == ["premium", "boundary"] and kinds[0]["group"] == "premium"
    assert all(k["label"] and k["note"] for k in kinds) and next(k for k in kinds if k["id"] == "strobe")["label"] == "strobe cut"
    assert out["choices"]["plays"] == ["morph", "hold"] and out["choices"]["insert_seconds"] == [5, 10, 15] and out["choices"]["render_s"] == [2, 5]
    assert lane.build({**info, "tier": "final"})["rerenderable"] is False and lane.build({})["choices"] == {} and lane.build({})["editable"] is False


# ---------------------------------------------------------------------------------------------- the desk


def test_the_recut_route_passes_the_override_maps_through(tmp_path, monkeypatch):
    from xenoform import dense as dense_mod, ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / "tl-recut"
    (folder / "simple").mkdir(parents=True)
    (folder / "simple" / "simple.json").write_text("{}", encoding="utf-8")
    with ui_mod._LOCK:
        ui_mod._JOBS["tl-recut"] = {"id": "tl-recut", "status": "done", "stage": "done", "progress": 1.0, "video_version": 1,
                                    "video": "/api/jobs/tl-recut/video?v=1", "detail": "Cut ready"}
    got = {}
    done = threading.Event()

    def fake_recut(job_dir, overrides=None, report=None, cfg=None):
        got.update(overrides or {})
        done.set()
        return {"look": {}, "recuts": 2}

    monkeypatch.setattr(dense_mod, "recut_from_cache", fake_recut)
    try:
        r = client.post("/api/jobs/tl-recut/recut", json={"shot_overrides": {"1": {"play": "hold"}}, "boundary_overrides": {"2": {"fx": "smear"}}, "macros": {"glow": 1}})
        assert r.status_code == 200 and done.wait(10)
        assert got["shot_overrides"] == {"1": {"play": "hold"}} and got["boundary_overrides"] == {"2": {"fx": "smear"}} and got["macros"] == {"glow": 1}
        for _ in range(50):
            if client.get("/api/jobs/tl-recut").json().get("video_version") == 2:
                break
            time.sleep(0.1)
        assert client.get("/api/jobs/tl-recut").json()["video_version"] == 2
        got.clear(); done.clear()
        client.post("/api/jobs/tl-recut/recut", json={"dance_fx": "auto", "shot_overrides": "junk"})
        assert done.wait(10) and "shot_overrides" not in got  # a knob re-cut keeps the record's maps
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("tl-recut", None)


def test_the_rerender_route_runs_the_edit_and_refuses_plainly(tmp_path, monkeypatch):
    from xenoform import dense as dense_mod, ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / "tl-edit"
    (folder / "simple").mkdir(parents=True)
    shots = [{"start": i * 2.0, "end": (i + 1) * 2.0, "seconds": 2.0, "morph": i} for i in range(5)]
    shots[4] = {**shots[4], "performer": True}
    shots[4].pop("morph")
    (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "shots": shots, "clips": ["c"] * 5, "stills": ["v/0.jpg"] * 6,
                                                                "tier": "draft"}), encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"old")
    calls = []
    done = threading.Event()

    def fake_rerender(job_dir, shot, *, seed=None, render_s=None, variant="auto", style=None, cfg=None, report=None, client=None):
        calls.append(("rerender", Path(job_dir).name, shot, seed, render_s, variant) + ((style,) if style else ()))
        if report:
            report("restyle", 0.3, "Re-rendering shot 2")
        done.set()
        return {"look": {}, "recuts": 1, "rerenders": [{"shot": shot}]}

    monkeypatch.setattr(dense_mod, "rerender_morph", fake_rerender)
    try:
        assert client.post("/api/jobs/no-such/rerender", json={"shot": 0}).status_code == 404
        assert client.post("/api/jobs/tl-edit/rerender", json={}).status_code == 400
        assert client.post("/api/jobs/tl-edit/rerender", json={"shot": 9}).status_code == 400
        assert "Polly" in client.post("/api/jobs/tl-edit/rerender", json={"shot": 4}).json()["detail"]
        assert client.post("/api/jobs/tl-edit/rerender", json={"shot": 1, "render_s": 9}).status_code == 400
        assert client.post("/api/jobs/tl-edit/rerender", json={"shot": 1, "variant": "wild"}).status_code == 400
        assert client.post("/api/jobs/tl-edit/rerender", json={"shot": 1, "seed": "abc"}).status_code == 400
        assert "morph style" in client.post("/api/jobs/tl-edit/rerender", json={"shot": 1, "style": "smoke"}).json()["detail"]
        r = client.post("/api/jobs/tl-edit/rerender", json={"shot": 1, "seed": 7, "render_s": 3, "variant": "scene-object"})
        assert r.status_code == 200 and r.json() == {"id": "tl-edit", "status": "running", "shot": 1, "seed": 7, "render_s": 3,
                                                     "variant": "scene-object", "style": None}
        assert done.wait(10) and calls[-1] == ("rerender", "tl-edit", 1, 7, 3, "scene-object")
        for _ in range(50):
            job = client.get("/api/jobs/tl-edit").json()
            if job["status"] == "done" and job.get("video_version") == 1:
                break
            time.sleep(0.1)
        assert job["video_version"] == 1 and job["detail"] == "Re-render ready" and job["rerenders"] == 1
        with ui_mod._LOCK:
            ui_mod._JOBS["tl-edit"]["status"] = "running"
        with ui_mod._LOCK:
            ui_mod._JOBS["tl-edit"]["status"] = "done"
        (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "clips": ["c"] * 5, "tier": "final"}), encoding="utf-8")
        assert "Final" in client.post("/api/jobs/tl-edit/rerender", json={"shot": 0}).json()["detail"]
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("tl-edit", None)


def test_the_desk_draws_the_timeline_panel_and_posts_the_edits():
    fn = APP.split("function shotsLane(easy)")[1].split("async function loadLane")[0]
    assert 'aria-label="Timeline"' in fn and 'data-act="easy-tl-shot"' in fn and 'data-act="easy-tl-bound"' in fn and 'class="lane-joins"' in fn
    assert 'class="lane-song"' in fn and 'data-act="easy-seek"' in fn and "drop-mark" in fn
    assert 'data-act="easy-tl-reset"' in fn and "timelineDirty" in fn and 'id="lane-playhead"' in fn
    # one Apply for the timeline and the knobs: the bar at the bottom of the window (28 Oct)
    bar = APP.split("function pendingBar(easy)")[1].split("function paintPending")[0]
    assert 'data-act="easy-apply"' in bar and "timeline edit" in bar
    assert "function timelineDrawer" in fn and 'data-act="easy-tl-play"' in fn and 'data-act="easy-tl-handoff"' in fn and 'id="tl-dress"' in fn
    assert 'lookRow(o.look || "auto", "easy-tl-look", s.index)' in fn and 'id="tl-fx"' in fn and 'data-act="easy-tl-fx-clear"' in fn
    assert 'data-act="easy-tl-swap"' in fn and 'data-act="easy-tl-rerender"' in fn
    assert 'id="tl-seed"' in fn and 'id="tl-render-s"' in fn and 'id="tl-variant"' in fn
    # one drawer for a shot in four tabs, a seam opens its Join tab, and a step between shots (28 Oct timeline pass)
    assert 'const TL_TABS = [["shot", "Shot"], ["look", "Look"], ["join", "Join"], ["gpu", "Regenerate"]];' in fn
    assert 'data-act="easy-tl-tab"' in fn and 'data-act="easy-tl-step"' in fn and "/frame.jpg?t=" in fn
    assert 'if (act === "easy-tl-bound") state.easy.tlTab = "join";' in APP
    assert "async function postCutEdit" in fn and "/${route}`" in fn and "tlSeek" in fn
    assert "async function applyTimeline" in fn and "shot_overrides: tl.shots, boundary_overrides: tl.bounds" in fn
    assert "async function rerenderShot" in fn and '"rerender"' in fn
    for act in ("easy-tl-shot", "easy-tl-bound", "easy-tl-close", "easy-tl-play", "easy-tl-look", "easy-tl-fx-clear", "easy-tl-handoff",
                "easy-tl-apply", "easy-tl-reset", "easy-tl-swap", "easy-tl-rerender"):
        assert f'act === "{act}"' in APP, act
    assert 'target.id === "tl-fx"' in APP and 'target.id === "tl-dress"' in APP
    knobs = APP.split("async function recutWithKnobs")[1].split("async function easyMake")[0]
    assert "body.shot_overrides = state.easy.tl.shots" in knobs  # the edits waiting for Apply ride along with the knobs
    load = APP.split("async function loadLane")[1].split("\n}\n")[0]
    assert "state.easy.tl = null" in load and "loadedmetadata" in load
    # the swap's strings the earlier test pins are still there, inside the same panel
    assert 'data-act="easy-swap-mode"' in fn and 'class="lane-open"' in fn
    desk_css = (Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "desk.css").read_text(encoding="utf-8")
    assert ".shots-lane .lane-joins .join" in desk_css and ".tl-tabs" in desk_css and "var(--thumb, none)" in desk_css
    for rule in (".shots-lane .shot.held", ".shots-lane .lane-song", ".shots-lane .tl-drawer", ".shots-lane .overlay.generated",
                 ".shots-lane .shot.rerendered::after", ".shots-lane .lane-apply-row"):
        assert rule in CSS, rule


def test_the_timeline_is_in_the_public_docs():
    doc = (ROOT / "docs" / "TIMELINE.md").read_text(encoding="utf-8")
    for key in ("shot_overrides", "boundary_overrides", "rerenders", "/api/jobs/{id}/rerender", "Cut sets the shot before to Hold"):
        assert key in doc, key
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Timeline" in readme and "docs/TIMELINE.md" in readme
    unreleased = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 0.3.3")[1].split("## 0.3.2")[0]
    assert "shot_overrides" in unreleased and "/api/jobs/{id}/rerender" in unreleased
