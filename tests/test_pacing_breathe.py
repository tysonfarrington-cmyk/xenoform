"""Breathe (docs/MUSIC_VIDEO_PLAN.md section 3): one profile table a passage, written into the shots as fields the
timeline already reads, by one helper the Make and the re-cut both call, so Breathe and the Drops re-cut with no GPU."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from xenoform import beatfx, boundary_fx as B, dense, guardrails, pacing, simple_recipe as sr

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
GLITCH_DROP = 139.71
BEAT = 60.0 / 90.0  # Glitch Out


def _song() -> dict:
    f = json.loads((SONGS / "glitch-out.features.json").read_text(encoding="utf-8"))
    return {"duration": float(f["duration"]), "beats": list(f["beats"]), "sections": list(f["sections"])}


def _plan(**extra) -> tuple[list[dict], dict]:
    song = _song()
    body = {"energy_preset": "dense", "aspect": "9:16", "quality_tier": "draft", "breathe": True, **extra}
    body, _ = guardrails.apply(body, duration=song["duration"], beats=song["beats"])
    return dense.shots_for(body, song, None, drop=GLITCH_DROP)


def _beats_of(s: dict) -> float:
    return round(float(s["seconds"]) / BEAT, 1)


def test_breathe_cuts_a_bar_a_shot_and_rests_at_the_passage_ends():
    shots, plan = _plan()
    assert plan["name"] == "story" and plan["breathe"] is True
    by = {}
    for s in shots:
        by.setdefault(s["section"], []).append(s)
    intro = by["intro"]
    assert _beats_of(intro[0]) >= 7.0  # the intro opens on one long shot
    rested = [s for s in shots if s.get("rest")]
    assert rested and all(s["rest"] == pacing.REST_BEATS and s["section"] in pacing.REST_ROLES for s in rested)
    assert not any(s.get("rest") for s in by["drop"])  # never in a drop
    assert intro[-1].get("rest") == 4 or len(intro) == 1 and intro[0].get("rest") == 4  # the intro's last shot dwells
    for s in rested:
        assert 0.0 < s["rest_s"] < s["seconds"] and s["seconds"] - s["rest_s"] >= 1.9 * BEAT  # room for the morph
        nxt = shots[shots.index(s) + 1] if shots.index(s) + 1 < len(shots) else None
        assert nxt is None or nxt.get("passage") != s.get("passage")  # a passage's end
    calm = [s for s in by["calm"] if not s.get("rest")]
    assert sorted(_beats_of(s) for s in calm)[len(calm) // 2] == pytest.approx(4.0, abs=0.6)  # a bar a shot
    ends = [s for s in by["build"] if _beats_of(s) <= 2.2]
    assert ends  # a build's last two bars cut on the half bar
    assert all(_beats_of(s) >= 1.9 for s in shots)  # nothing under two beats
    old, _ = _plan(breathe=False)
    assert not any(s.get("rest") for s in old)


def _shape(shots, *, breathe=True, drop_mode="auto", macros=None, **kw):
    shots = copy.deepcopy(shots)
    info = pacing.shape(shots, macros or {"intensity": 0.5, "chaos": 0.3}, breathe=breathe, drop_mode=drop_mode,
                        beats=_song()["beats"], **kw)
    return shots, info


def test_each_passage_takes_its_profile():
    plan_shots, _ = _plan()
    shots, info = _shape(plan_shots, look="house")
    first_drop = min(s["start"] for s in shots if s["section"] == "drop")
    for s in shots:
        role = s["section"]
        if role == "intro":
            assert s["chaos"] <= 0.15 and s["fx_intensity"] == 0.5 and "timing" not in s and s["fx_names"] == []
        if role in ("calm", "sustain"):
            assert s["chaos"] <= 0.3 and s["timing"] == {"mode": "beat"} and s["fx_intensity"] == 0.8
        if role == "drop":
            assert s["fx_intensity"] == 1.0 and s["chaos"] > 0.3  # the drop lifted toward its cap by its heat
            assert s["timing"] == {"mode": "snap" if s["heat"] >= 0.5 else "beat"}
            assert s["fx_names"] in (["dither"], ["feedback"])
        if role == "build":
            assert s["fx_names"] == ["dither"] and 0.6 <= s["fx_intensity"] <= 1.0
        if role == "outro":
            assert s["fx_names"] == [] and "timing" not in s
        assert len(s.get("fx_names") or []) <= 1  # one effect at a time
        if s["start"] < first_drop:
            assert s.get("dance_fx") in (None, "cool-echo")  # no flash look before the first drop
    assert shots[0].get("dance_fx") == "cool-echo"  # the house's cyan-flash opener stands down
    calm_fx = [s["fx_names"] for s in shots if s["section"] == "calm"]
    assert [] in calm_fx and any(x in (["slitscan"], ["dither"]) for x in calm_fx)  # one calm passage in three
    builds = [s for s in shots if s["section"] == "build"]
    assert builds[-1]["fx_intensity"] >= builds[0]["fx_intensity"]  # a build ramps
    assert info["timing"] and info["effects"]
    flashy, _ = _shape(plan_shots, look="cyan-flash")
    assert all(s.get("dance_fx") == "cool-echo" for s in flashy if s["start"] < first_drop)
    assert all(not s.get("dance_fx") for s in flashy if s["start"] >= first_drop)


def test_the_cut_s_own_choices_win():
    plan_shots, _ = _plan()
    shots, _ = _shape(plan_shots, effects=["kaleido", "feedback"], timing="snap", look_auto=False, look="cyan-flash")
    assert all(len(s["fx_names"]) == 1 and s["fx_names"][0] in ("kaleido", "feedback") for s in shots)
    assert not any("timing" in s for s in shots)  # the cut's Timing (morph_timing.plan) times every shot
    assert not any(s.get("dance_fx") for s in shots)  # a Look chosen by hand is the cut's look


def test_without_breathe_only_the_drops_change():
    plan_shots, _ = _plan(breathe=False)
    shots, _ = _shape(plan_shots, breathe=False)
    knob = dense.apply_macros(copy.deepcopy(plan_shots), {"intensity": 0.5, "chaos": 0.3})
    for s, k in zip(shots, knob):
        if s["section"] in ("drop", "drop_late"):
            assert s["fx_intensity"] >= k["fx_intensity"] and s["chaos"] >= k["chaos"]
        else:
            assert (s["fx_intensity"], s["chaos"], s["effects"]) == (k["fx_intensity"], k["chaos"], k["effects"])
        assert "timing" not in s and "fx_names" not in s and "rest" not in s


def test_the_handoff_kinds_follow_the_passages():
    plan_shots, _ = _plan()
    for s in plan_shots:
        s["frames"] = int(round(float(s["seconds"]) * 24))
    shots, _ = _shape(plan_shots, macros={"intensity": 0.5, "chaos": 0.5})
    picks = B.pick(shots, {"intensity": 0.5, "chaos": 0.5}, _song()["beats"], 24, seed=3, paced={"breathe": True})
    kinds = [(i, p["kind"]) for i, p in enumerate(picks) if p]
    assert kinds
    assert not any(shots[i]["section"] in ("intro", "build", "outro") and not shots[i].get("boundary") for i, _ in kinds)
    assert sum(1 for _, k in kinds if k == "wipe") <= B.WIPE_SHARE * (len(shots) - 1)
    assert all(a[1] != b[1] for a, b in zip(kinds, kinds[1:]))  # never the kind just used
    for i, k in kinds:
        if k == "strobe":
            assert shots[i].get("heat") == 1.0 and shots[i].get("boundary") == "drop"
    strobes = [shots[i]["start"] for i, k in kinds if k == "strobe"]
    assert all(b - a >= B.STROBE_GAP_S for a, b in zip(strobes, strobes[1:]))
    entries = [i for i, s in enumerate(shots) if s.get("boundary") == "drop"]
    assert all(picks[i] for i in entries)  # every drop run opens with a kind (no premium transitions given here)


def test_the_plan_line_names_the_main_drop():
    shots, plan = _plan()
    line = pacing.summary_line(shots, breathe=True, drop=plan["drop"])
    assert line == "5 drops, the main at 2:21; 14 passages; 3 rests"
    assert pacing.summary_line(shots, breathe=True, drop=plan["drop"], song_start=60.0).startswith("5 drops, the main at 3:21")
    off, plan_off = _plan(breathe=False)
    assert pacing.summary_line(off, breathe=False, drop=plan_off["drop"]) == "5 drops, the main at 2:21; 14 passages"
    rec = pacing.record(plan, shots, {"breathe": True}, {"song_start": 0.0, "length_s": 238.8})
    assert rec["line"] == line and rec["rests"] == 3 and len(rec["runs"]) == 5 and rec["breathe"] is True


def test_breathe_styles_by_passage():
    shots, _ = _plan()
    styles = pacing.styles(shots, {"breathe": True, "morph_style": "auto"})
    by = {}
    for s, st in zip(shots, styles):
        by.setdefault(s["section"], set()).add(st)
    assert by["intro"] <= {"bloom", "melt"} and by["drop"] <= {"shatter", "spin", "bloom"} and by["outro"] == {"melt"}
    assert styles[0] == "bloom"
    assert pacing.styles(shots, {"breathe": True, "morph_style": "spin"}) is None  # a style chosen by hand
    assert pacing.styles(shots, {"breathe": False}) is None  # Auto's own rules


def test_the_recipe_carries_the_shape_and_an_old_code_is_the_old_cut():
    code = sr.encode({"vibe": "ocean", "breathe": True, "drop_mode": "max"})
    back = sr.decode(code)
    assert back["breathe"] is True and back["drop_mode"] == "max"
    plain = sr.decode(sr.encode({"vibe": "ocean"}))  # a plain Make today: Breathe off, the Drops on auto
    assert plain["breathe"] is False and plain["drop_mode"] == "auto"
    old = "xf1." + __import__("base64").urlsafe_b64encode(__import__("zlib").compress(b'{"v":"ocean"}')).decode().rstrip("=")
    assert sr.decode(old)["breathe"] is False and sr.decode(old)["drop_mode"] == "off"  # made before the keys: the old cut


def _tiny_record(tmp_path: Path, shots: list[dict], breathe: bool) -> Path:
    job = tmp_path / "job"
    work = job / "simple"
    work.mkdir(parents=True)
    clips = []
    for i in range(len(shots)):
        p = work / f"local{i:02d}.mp4"
        p.write_bytes(b"clip")
        clips.append(str(p))
    rec = {"plan_shots": shots, "shots": shots, "clips": clips, "audio_path": str(ROOT / "examples" / "demo.wav"), "vibe": "cosmic",
           "tier": "draft", "size": [64, 112], "fps": 24, "seed": 3, "plan_name": "story", "vertical_house": True,
           "beats": _song()["beats"], "drop": 141.0,
           "recut_state": {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "dance_fx": "auto",
                           "stem_orbit": False, "beat_fx": True, "macros": {"intensity": 0.5, "chaos": 0.3}, "breathe": breathe,
                           "drop_mode": "auto"}}
    (work / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    (job / "xenoform.mp4").write_bytes(b"old")
    return job


def test_breathe_re_cuts_with_no_gpu(tmp_path, monkeypatch):
    plan_shots, _ = _plan()
    from xenoform.cloud_morph import custom_shots

    shots = custom_shots({"shots": plan_shots}, _song()["duration"])
    for s, raw in zip(shots, plan_shots):
        s.update({k: raw[k] for k in dense.PLAN_KEYS if k in raw})
    job = _tiny_record(tmp_path, shots, breathe=True)
    seen = []

    def spy(clips, shots_, audio, out, **kw):
        seen.append(copy.deepcopy(shots_))
        Path(out).write_bytes(b"new")
        return {"frames": 1, "seconds": 1.0, "size": "64x112", "aspect": "9:16", "fx": True, "overlay": False, "centres": [],
                "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    rec = dense.recut_from_cache(job, {"macros": {"intensity": 0.5, "chaos": 0.3}})
    assert any(s.get("rest") for s in seen[-1]) and any(s.get("fx_names") for s in seen[-1])
    assert rec["recut_state"]["breathe"] is True and "rest" in rec["pacing"]["line"]
    rec = dense.recut_from_cache(job, {"breathe": False})  # Breathe off on the same morphs
    assert not any(s.get("rest") for s in seen[-1]) and not any(s.get("fx_names") for s in seen[-1])
    assert rec["recut_state"]["breathe"] is False and rec["pacing"]["breathe"] is False
    rec = dense.recut_from_cache(job, {"breathe": True, "drop_mode": "off"})
    assert any(s.get("rest") for s in seen[-1]) and rec["recut_state"]["drop_mode"] == "off"


def test_the_recut_route_passes_the_shape(monkeypatch):
    import threading

    from fastapi.testclient import TestClient

    from xenoform import ui

    folder = ui.work_dir() / "jobs" / "shape-recut"
    (folder / "simple").mkdir(parents=True, exist_ok=True)
    (folder / "simple" / "simple.json").write_text("{}", encoding="utf-8")
    with ui._LOCK:
        ui._JOBS["shape-recut"] = {"id": "shape-recut", "status": "done", "stage": "done", "progress": 1.0, "video_version": 1}
    got = {}
    done = threading.Event()

    def fake(job_dir, overrides=None, report=None, cfg=None):
        got.update(overrides or {})
        done.set()
        return {"look": {}, "recuts": 1}

    monkeypatch.setattr(dense, "recut_from_cache", fake)
    client = TestClient(ui.create_app())
    assert client.post("/api/jobs/shape-recut/recut", json={"breathe": True, "drop_mode": "max"}).status_code == 200
    assert done.wait(10) and got["breathe"] is True and got["drop_mode"] == "max"
