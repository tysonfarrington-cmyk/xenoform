"""When the change happens inside a morph (xenoform.morph_timing, docs/MORPH_ENGINE_PLAN.md E2, 28 Oct): Smooth, On
the beat, Snap. The hits a shot gets, the clip's measured progress, the re-timed positions (ends kept, the change on the
hit), the blended frames, the compose and the re-cut, the timeline's per-shot timing, the recipe and the desk."""
import json
from pathlib import Path

import numpy as np

from test_timeline import _cut, _rec
from xenoform import beatfx, dense, lane, morph_timing as mt, simple_recipe
from xenoform.cloud_morph import shot_indices

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
BEATS = [i * 0.5 for i in range(24)]  # 120 BPM, a downbeat every 2 s


def _clip(n=73, change=(30, 42)):
    """A synthetic morph: still for most of it, the whole change between ``change`` frames (like a model that
    morphs late)."""
    frames = np.zeros((n, 16, 16, 3), np.uint8)
    a, b = change
    for k in range(n):
        v = 0 if k < a else 255 if k >= b else int(255 * (k - a) / (b - a))
        frames[k] = v
    return frames


def test_plan_puts_the_hits_where_the_music_is():
    shots = [{"start": 0.0, "end": 3.0}, {"start": 3.0, "end": 4.0}, {"start": 4.0, "end": 5.0, "hold": True},
             {"start": 6.0, "end": 7.0}, {"start": 7.0, "end": 8.0, "performer": True}]
    assert mt.plan(shots, "smooth", BEATS, 6.0) == {} and not any("timing" in s for s in shots)
    got = mt.plan(shots, "beat", BEATS, 6.0)
    assert got == {"beat": 3} and shots[0]["timing"]["hits"] == [0.5, 1.0, 1.5, 2.0, 2.5] and shots[1]["timing"]["hits"] == [3.5]
    assert "timing" not in shots[2] and "timing" not in shots[4]  # a held shot and Polly are left alone
    mt.plan(shots, "snap", BEATS, 6.0)
    assert shots[0]["timing"]["hits"] == [2.0]  # the downbeat inside the shot
    assert shots[1]["timing"]["hits"] == [3.5]  # no downbeat inside: the beat nearest the middle
    assert shots[3]["timing"]["hits"] == [6.125] and shots[3]["timing"]["width"] < shots[0]["timing"]["width"]  # the drop: sharper, a quarter beat in
    mt.plan(shots, "smooth", BEATS, 6.0, overrides={0: {"timing": "snap"}, "1": {"timing": "beat"}})
    assert shots[0]["timing"]["mode"] == "snap" and shots[1]["timing"]["mode"] == "beat" and "timing" not in shots[3]
    assert mt.normal("On the beat") == "beat" and mt.normal("wild") == "smooth" and mt.normal(None) == "smooth"


def test_progress_and_the_positions_move_the_change_onto_the_hit():
    frames = _clip()
    prog = mt.progress(frames)
    assert prog[0] == 0 and abs(prog[-1] - 1) < 1e-9 and np.all(np.diff(prog) > 0)
    assert prog[29] < 0.05 and prog[42] > 0.95  # the measured change is where the clip changes
    shot = {"start": 0.0, "end": 3.0, "frames": 72}
    plain = shot_indices(shot, len(frames))
    assert plain[0] == 0 and plain[-1] == 72 and abs(int(np.argmax(np.diff(prog[plain]))) - 36) <= 6  # the even play: change near 1.5 s
    mt.plan([shot], "snap", BEATS, None)
    shot["timing"]["hits"] = [2.5]  # put the hit late to see it move
    pos = shot_indices(shot, len(frames), progress=prog, exact=True)
    assert pos[0] == 0.0 and pos[-1] == 72.0 and np.all(np.diff(pos) >= -1e-9)  # the ends kept, never backwards
    played = np.interp(pos, np.arange(len(prog)), prog)
    k = int(np.argmax(np.diff(played)))
    assert abs(k / 24.0 - 2.5) <= 0.15  # the change now lands on the hit
    ints = shot_indices(shot, len(frames), progress=prog)
    assert ints.dtype.kind == "i" and ints[0] == 0 and ints[-1] == 72
    assert mt.target({"start": 0, "end": 1, "frames": 24}, 24) is None and mt.indices({"start": 0, "end": 1}, 24, prog) is None


def test_blending_a_slow_stretch_instead_of_repeating_frames():
    frames = _clip(n=3, change=(0, 2))  # 0, 127, 255
    assert int(beatfx._blend_at(frames, 0.5)[0, 0, 0]) == 64 and (beatfx._blend_at(frames, 1.02) == frames[1]).all()
    assert (beatfx._blend_at(frames, 2.0) == frames[2]).all() and (beatfx._blend_at(frames, 0.97) == frames[1]).all()


def test_a_recut_retimes_the_cached_morphs_and_the_timeline_sets_a_shots_own(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec = _rec(job)
    assert rec["morph_timing"] == "smooth" and not any(s.get("timing") for s in rec["shots"])
    out = dense.recut_from_cache(job, {"morph_timing": "snap"})
    timed = [s for s in seen["shots"] if s.get("timing")]
    assert timed and all(s["timing"]["mode"] == "snap" for s in timed) and out["morph_timing"] == "snap"
    assert out["timed"] == {"snap": len(timed)} and out["recut_state"]["morph_timing"] == "snap"
    # a shot's own timing from the timeline beats the cut's; the lane reads it back
    out = dense.recut_from_cache(job, {"morph_timing": "smooth", "shot_overrides": {"2": {"timing": "beat"}, "3": {"timing": "auto"}}})
    modes = [(s.get("timing") or {}).get("mode") for s in seen["shots"]]
    assert modes[2] == "beat" and modes.count(None) == len(modes) - 1 and out["shot_overrides"] == {"2": {"timing": "beat"}}
    built = lane.build(out, "cut")
    assert built["shots"][2]["timing"] == "beat" and built["morph_timing"] == "smooth"
    assert dense.shot_overrides_of({"1": {"timing": "wild"}}, 4) == {}


def test_a_make_records_the_timing(tmp_path, monkeypatch):
    seen = {}
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [Path(work) / f"m{i}.mp4" for i in range(len(shots))])
    def compose(clips, shots, audio, out, **kw):
        seen["shots"] = shots
        Path(out).write_bytes(b"x")
        return {"frames": 1, "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", compose)
    state = {"vibe": "cosmic", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense", "morph_timing": "beat"}
    job = tmp_path / "j"
    info = dense.run_simple({"duration": 20.0, "beats": BEATS + [12 + i * 0.5 for i in range(16)]}, ROOT / "examples" / "demo.wav",
                            job / "x.mp4", job, {}, state, lambda *a: None, engine="mock")
    assert info["morph_timing"] == "beat" and info["recut_state"]["morph_timing"] == "beat"
    assert any(s.get("timing", {}).get("mode") == "beat" for s in seen["shots"])
    assert any("morph_timing" in n for n in info["fallbacks"] if isinstance(n, dict))


def test_the_recipe_and_the_recut_route_carry_the_timing():
    assert simple_recipe.decode(simple_recipe.encode({"vibe": "cosmic", "morph_timing": "snap"}))["morph_timing"] == "snap"
    assert "morph_timing" not in simple_recipe.decode(simple_recipe.encode({"vibe": "cosmic"}))
    ui = (ROOT / "src/xenoform/ui.py").read_text(encoding="utf-8")
    route = ui.split('def recut_job(job_id: str', 1)[1].split("for key in", 1)[0]
    assert '"morph_timing"' in route


def test_a_recut_after_a_desk_restart_finds_the_cut_in_its_folder(tmp_path, monkeypatch):
    """Re-cut with these knobs answered "No such video." on any cut made before the desk restarted (the timeline's edits
    registered it from its folder; the re-cut did not), found re-cutting the proof cut with the new Timing row."""
    import threading

    from fastapi.testclient import TestClient

    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / "reopened"
    (folder / "simple").mkdir(parents=True)
    (folder / "simple" / "simple.json").write_text("{}", encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"mp4")
    got, done = {}, threading.Event()

    def fake_recut(job_dir, overrides=None, report=None, cfg=None):
        got.update(overrides or {})
        done.set()
        return {"look": {}, "recuts": 1}

    monkeypatch.setattr(dense, "recut_from_cache", fake_recut)
    try:
        r = client.post("/api/jobs/reopened/recut", json={"morph_timing": "snap"})
        assert r.status_code == 200 and done.wait(10) and got == {"morph_timing": "snap"}
        assert client.post("/api/jobs/never-made/recut", json={}).status_code == 404
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("reopened", None)


def test_the_desk_has_the_timing_rows():
    assert 'const MORPH_TIMINGS = ["smooth", "beat", "snap"];' in APP
    notes = APP.split("const MORPH_TIMING_NOTES = {", 1)[1].split("};", 1)[0]
    for key, text in mt.NOTES.items():
        assert f'"{key}": {json.dumps(text)}' in notes, key
    desk = APP.split("simple-knobs-panel", 1)[1].split("</section>", 1)[0]
    assert '${timingRow(easy.morphTiming || "smooth", "easy-morph-timing")}' in desk
    result = APP.split('if (easy.phase === "result" || easy.phase === "showcase") {', 1)[1].split("const preview = easy.vibe", 1)[0]
    assert '${timingRow(easy.morphTiming || "smooth", "easy-morph-timing")}' in result  # beside Re-cut: no GPU
    assert 'morph_timing: (state.easy && state.easy.morphTiming) || "smooth"' in APP
    assert 'morph_timing: state.easy.morphTiming || "smooth",' in APP.split("async function recutWithKnobs()", 1)[1].split("try {", 1)[0]
    assert '"morphTiming"' in APP.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0]
    drawer = APP.split("function timelineDrawer(easy, lane, tl, picked) {", 1)[1].split("// Dream this span", 1)[0]
    assert 'timingRow(o.timing || "auto", "easy-tl-timing", s.index, lane.morph_timing || "smooth")' in drawer
    assert 'setShotOverride(state.easy, state.lane, Number(el.dataset.index), "timing", el.dataset.value);' in APP
    assert "easy.morphTiming = recipe.morph_timing" in APP
