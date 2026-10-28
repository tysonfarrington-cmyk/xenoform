"""Honest job timing: the phase mapper, the plan-weighted overall fraction and ETA, the per-phase breakdown and
took.json, the preview that no longer restarts on every compose shot, and the seconds My videos shows for older
cuts (took.json, then turbo.json, simple.json, the file's age)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import job_timing as jt
from xenoform import ui
from xenoform.config import load_config

PLAN = {"analyze": 3.0, "draft": 6.0, "morphs": 90.0, "performer": 0.0, "cut": 30.0, "card": 4.0, "save": 1.0, "qa": 10.0}
TOTAL = 144.0

# (seconds into the run, stage, frac, detail): a Draft Simple cut that runs exactly to plan, as the pipeline reports
# it (turbo.py, dense.run_simple, cloud_morph._local_clips, beatfx.compose, ui._run_job, post_qa.run).
RUN = [
    (0.5, "analyze", 0.05, "Reading the track"),
    (3.0, "analyze", 1.0, "Track already analyzed"),
    (3.0, "animatic", 0.1, "Cutting the stills to the beat"),
    (6.0, "animatic", 0.5, "Scene 1 of 2"),
    (9.0, "assemble", 1.0, "Animatic locked to the track"),
    (9.0, "restyle", 0.1, "GPU morphs, LTX 0.9.5 at 512x288. The draft stays up while this runs."),
    (9.0, "restyle", 0.05, "12 shots on the beat over a loop of 6 morphs (2 s each)"),
    (9.0, "restyle", 0.1, "6 Draft (LTX 0.9.5) morphs - 12 shots - flow - 9:16"),
    (54.0, "restyle", 0.325, "Morph 3 of 6 - about 45 s left"),
    (99.0, "restyle", 0.55, "Morph 6 of 6"),
    (99.0, "assemble", 0.6, "Cutting to the beat with beat FX"),
    (99.0, "assemble", 0.6, "House look: dance_fx house, stem_orbit on, stems from the mix"),
    (114.0, "assemble", 0.775, "Cutting shot 6 of 12 to the beat"),
    (129.0, "assemble", 0.95, "Cutting shot 12 of 12 to the beat"),
    (129.0, "assemble", 0.96, "Burning the end card"),
    (133.0, "assemble", 0.98, "Saving the video"),
    (134.0, "restyle", 1.0, "GPU morphs locked to the beat"),
    (134.0, "assemble", 1.0, "Cut ready in 125.0s"),
    (134.0, "qa", 0.05, "Checking for lag, artifacts and off-beat cuts"),
    (134.0, "qa", 0.2, "Checking for lag"),
    (139.0, "qa", 0.5, "Scanning for artifacts"),
    (141.0, "qa", 0.7, "Checking the cuts against the beat"),
]


def _job(plan=PLAN, body=None) -> dict:
    return {"id": "t", "status": "running", "detail": "", **jt.start_fields(plan, body or {"quality_tier": "draft"})}


# ------------------------------------------------------------------ mapper

def test_phase_mapper_follows_the_fixed_order_and_never_goes_back():
    assert list(jt.PHASES) == ["analyze", "draft", "morphs", "performer", "cut", "card", "save", "qa", "done"]
    assert jt.phase_for("analyze", "Reading the track") == "analyze"
    assert jt.phase_for("animatic", "Scene 1 of 2", "analyze") == "draft"
    assert jt.phase_for("assemble", "Animatic locked to the track", None) == "draft"  # the stills draft...
    assert jt.phase_for("assemble", "Animatic locked to the track", "draft") == "draft"
    assert jt.phase_for("restyle", "Morph 1 of 6", "draft") == "morphs"
    assert jt.phase_for("restyle", "Final: morph 1 of 6", "morphs") == "morphs"
    assert jt.phase_for("restyle", "Performer shot 1 of 2: drums (5.0 s)", "morphs") == "performer"
    assert jt.phase_for("restyle", "Your clip 1 of 1: me.mp4 (3.0 s)", "performer") == "cut"
    assert jt.phase_for("assemble", "Cutting shot 1 of 12 to the beat", "morphs") == "cut"  # ...and after the morphs, the cut
    assert jt.phase_for("assemble", "Burning the end card", "cut") == "card"
    assert jt.phase_for("assemble", "Saving the video", "card") == "save"
    assert jt.phase_for("restyle", "GPU morphs locked to the beat", "save") == "save"  # never backwards
    assert jt.phase_for("assemble", "Cut ready in 9.0s", "save") == "save"
    assert jt.phase_for("restyle", "Performer shot 2 of 2", "cut") == "cut"
    assert jt.phase_for("qa", "Checking for lag", "save") == "qa"
    assert jt.phase_for("done", "Ready", "qa") == "done"
    assert jt.phase_for("render", "Frame 1 / 2", "analyze") == "morphs"  # the full desk's beauty pass is GPU time too
    assert jt.phase_for("something-new", "", "cut") == "cut"  # an unknown stage stays where the run is


def test_stage_frac_normalises_each_phase_to_its_raw_range():
    assert jt.stage_frac("morphs", 0.1) == 0.0 and jt.stage_frac("morphs", 0.55) == 1.0
    assert jt.stage_frac("morphs", 0.325) == pytest.approx(0.5)
    assert jt.stage_frac("morphs", 0.495, "final") == pytest.approx(0.5)
    assert jt.stage_frac("morphs", 0.495, "draft", "Final: morph 3 of 6") == pytest.approx(0.5)
    assert jt.stage_frac("morphs", 0.47, "cloud") == pytest.approx(0.5)  # Cloud Final reports 0.12-0.82
    assert jt.stage_frac("morphs", 0.55, "cloud") < 1.0 and jt.stage_frac("morphs", 0.82, "cloud") == 1.0
    assert jt.stage_frac("morphs", 0.34, "fast") == pytest.approx(0.5)  # Fast Final: the Draft morphs, then the upscale to 0.58
    assert jt.stage_frac("morphs", 0.325, "odd-tier") == pytest.approx(0.5)  # an unknown tier reads as a Draft
    assert jt.stage_frac("performer", 0.55) == pytest.approx(0.5)
    assert jt.stage_frac("cut", 0.775) == pytest.approx(0.5)
    assert jt.stage_frac("cut", 1.0) == 1.0 and jt.stage_frac("morphs", 0.05) == 0.0  # clamped
    assert jt.stage_frac("card", 0.96) == 0.0 and jt.stage_frac("save", 0.98) == 0.0  # one report each, as they start
    assert jt.stage_frac("qa", 0.7) == pytest.approx(0.7) and jt.stage_frac("done", 0.0) == 1.0


# ------------------------------------------------------------------ overall / eta / breakdown

def test_overall_and_eta_track_a_run_that_matches_its_plan():
    job = _job()
    assert job["eta_s"] == TOTAL and job["overall"] == 0.0 and job["stages"] == [] and job["elapsed_s"] == 0.0
    assert job["started"] > 0 and job["t0"] > 0 and sum(job["timing"]["weights"].values()) == pytest.approx(1.0)
    overalls, etas = [], []
    for now, stage, frac, detail in RUN:
        jt.tick(job, stage, frac, detail, now)
        overalls.append(job["overall"])
        etas.append(job["eta_s"])
        assert job["elapsed_s"] == now
        # to plan, the weighted fraction is the share of the planned time spent, and the ETA what is left of it
        assert job["overall"] == pytest.approx(now / TOTAL, abs=0.03), (stage, detail)
        assert abs(job["eta_s"] - (TOTAL - now)) <= 2.5, (stage, detail)
    assert overalls == sorted(overalls)  # never goes backwards
    assert etas == sorted(etas, reverse=True) and etas[-1] < etas[0]  # shrinks
    assert overalls[-1] < 1.0
    record = jt.finish(job, TOTAL)
    assert job["overall"] == 1.0 and job["eta_s"] == 0.0 and job["took_s"] == TOTAL and job["elapsed_s"] == TOTAL
    assert [s["phase"] for s in job["stages"]] == ["analyze", "draft", "morphs", "cut", "card", "save", "qa", "done"]
    assert job["stages"][0] == {"phase": "analyze", "at": 0.5} and job["stages"][-1] == {"phase": "done", "at": TOTAL}
    assert job["breakdown"] == {"analyze": 3.0, "draft": 6.0, "morphs": 90.0, "cut": 30.0, "card": 4.0, "save": 1.0, "qa": 10.0}
    assert sum(job["breakdown"].values()) == pytest.approx(job["took_s"], abs=0.5)
    assert record == {"took_s": TOTAL, "breakdown": job["breakdown"], "stages": job["stages"], "started": job["started"]}


def test_eta_switches_to_the_measured_pace_within_the_clamp():
    assert jt.eta(PLAN, "morphs", 0.05, 100.0) == pytest.approx(45.0 + 0.95 * 90.0)  # under a tenth in: the plan
    assert jt.eta(PLAN, "morphs", 0.5, 45.0) == pytest.approx(45.0 + 45.0)  # on plan
    assert jt.eta(PLAN, "morphs", 0.5, 180.0) == pytest.approx(45.0 + 0.5 * 360.0)  # slow, held to 4x the plan
    assert jt.eta(PLAN, "morphs", 0.5, 400.0) == pytest.approx(45.0 + 0.5 * 360.0)
    assert jt.eta(PLAN, "morphs", 0.5, 10.0) == pytest.approx(45.0 + 0.5 * 45.0)  # fast, held to half the plan
    assert jt.eta(PLAN, "performer", 0.5, 10.0) == pytest.approx(45.0)  # a phase the plan gave no seconds
    assert jt.eta(None, "morphs", 0.5, 10.0) is None and jt.eta(None, "done", 1.0, 0.0) == 0.0


def test_a_phase_fraction_never_decreases_and_a_late_report_cannot_pull_overall_back():
    job = _job()
    jt.tick(job, "restyle", 0.325, "Morph 3 of 6", 54.0)
    half = job["overall"]
    jt.tick(job, "restyle", 0.2, "Morph 1 of 6 (re-rolled)", 55.0)
    assert job["overall"] == half and job["timing"]["stage_frac"] == pytest.approx(0.5)
    jt.tick(job, "assemble", 0.6, "Cutting to the beat", 99.0)
    cut = job["overall"]
    jt.tick(job, "analyze", 0.05, "Reading the track", 100.0)  # a stray early stage: stays in the cut
    assert job["timing"]["phase"] == "cut" and job["overall"] == cut
    assert [s["phase"] for s in job["stages"]] == ["morphs", "cut"]


def test_a_cloud_or_fast_make_reads_its_own_morph_range():
    # Cloud Final's morphs report 0.12-0.82: on the Draft range the bar said 100 % with a third of them still to come
    job = _job(PLAN, {"quality_tier": "cloud"})
    assert job["timing"]["tier"] == "cloud"
    jt.tick(job, "restyle", 0.12 + 0.7 * 8 / 16, "Cloud Final: morph 8 of 16 back from Comfy Cloud (LTX-2.5, open weights)", 54.0)
    assert job["timing"]["stage_frac"] == pytest.approx(0.5) and job["overall"] == pytest.approx(54.0 / TOTAL, abs=1e-3)
    jt.tick(job, "restyle", 0.55, "Cloud Final: morph 10 of 16 back from Comfy Cloud (LTX-2.5, open weights)", 66.0)
    assert job["timing"]["stage_frac"] == pytest.approx(0.43 / 0.7) and job["overall"] < 0.5
    # Fast Final: the last Draft morph is not the end of the phase, the upscale (to 0.58) still follows
    fast = _job(PLAN, {"quality_tier": "fast"})
    jt.tick(fast, "restyle", 0.55, "Morph 6 of 6", 90.0)
    assert fast["timing"]["stage_frac"] == pytest.approx(0.45 / 0.48)
    jt.tick(fast, "restyle", 0.5 + 0.08 * 5 / 6, "Fast Final: upscaling morph 6 of 6 to 1080x1920", 95.0)
    assert fast["timing"]["stage_frac"] == pytest.approx((0.4 + 0.08 * 5 / 6) / 0.48)


def test_without_a_plan_the_fallback_weights_move_the_bar_and_the_eta_is_none():
    job = _job(None, {"quality_tier": "draft", "performer": 0})
    weights = job["timing"]["weights"]
    assert job["eta_s"] is None and weights["performer"] == 0.0 and sum(weights.values()) == pytest.approx(1.0)
    assert weights["morphs"] == pytest.approx(0.45 / 0.75, abs=1e-3)
    for now, stage, frac, detail in RUN:
        jt.tick(job, stage, frac, detail, now)
        assert job["eta_s"] is None
    assert 0.9 < job["overall"] < 1.0
    jt.finish(job, 150.0)
    assert job["overall"] == 1.0 and job["eta_s"] == 0.0 and job["took_s"] == 150.0
    with_performer = jt.weights_for(None, performer=True)
    assert with_performer["performer"] == pytest.approx(0.25) and sum(with_performer.values()) == pytest.approx(1.0)
    assert jt.start_fields(None, {"performer": 2})["timing"]["weights"]["performer"] == pytest.approx(0.25)


def test_breakdown_gives_the_first_phase_the_run_up_and_the_last_the_rest():
    stages = [{"phase": "analyze", "at": 0.4}, {"phase": "morphs", "at": 2.0}, {"phase": "cut", "at": 12.0}, {"phase": "done", "at": 20.0}]
    assert jt.breakdown(stages, 20.0) == {"analyze": 2.0, "morphs": 10.0, "cut": 8.0}
    assert jt.breakdown([], 5.0) == {}


def test_plan_for_uses_the_make_and_the_song(monkeypatch):
    from xenoform import dense

    feats = {"duration": 120.0, "beats": [i * 0.5 for i in range(240)]}
    plan = jt.plan_for(feats, {"energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16", "end_card": True})
    assert set(plan) == set(jt.PHASES) - {"done"}
    assert plan["morphs"] > 0 and plan["cut"] > 0 and plan["card"] == 4.0 and plan["performer"] == 0.0
    assert plan["qa"] == pytest.approx(4.0 + 0.12 * 120.0)
    # a Fast or Cloud Make is planned at its own tier (options() folds both into "draft" with a flag), not as a Draft
    seen, real = [], dense.plan_summary
    monkeypatch.setattr(dense, "plan_summary", lambda *a, **k: seen.append(a[3]) or real(*a, **k))
    by_tier = {t: jt.plan_for(feats, {"energy_preset": "dense", "quality_tier": t, "aspect": "9:16"}) for t in ("draft", "fast", "final", "cloud")}
    assert seen == ["draft", "fast", "final", "cloud"]
    assert by_tier["fast"]["morphs"] == pytest.approx(plan["morphs"] * dense.COST["fast"]["s"] / dense.COST["draft"]["s"], rel=0.01)
    assert by_tier["cloud"]["morphs"] > 0 and by_tier["cloud"]["morphs"] != plan["morphs"]  # its own cost and cap of 16
    with_performer = jt.plan_for(feats, {"energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16", "performer": 2})
    assert with_performer["performer"] > 0 and with_performer["card"] == 0.0
    short = jt.plan_for(feats, {"energy_preset": "dense", "length_s": 30})  # the cut, not the whole song
    assert short["qa"] == pytest.approx(4.0 + 0.12 * 30.0) and short["morphs"] > 0
    assert jt.plan_for({}, {}) is None and jt.plan_for(None, None) is None


# ------------------------------------------------------------------ the desk

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path)
    return TestClient(ui.create_app(load_config(None)))


def _fake_job(root: Path, job_id: str, meta: dict, files: dict | None = None) -> Path:
    folder = root / "jobs" / job_id
    folder.mkdir(parents=True)
    (folder / "xenoform.mp4").write_bytes(b"\x00" * 64)
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    for rel, data in (files or {}).items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    return folder


def test_my_videos_seconds_fall_back_from_took_json_to_the_older_manifests(client, tmp_path, monkeypatch):
    created = "2026-10-19T22:00:00+11:00"
    _fake_job(tmp_path, "aaaa1111", {"simple": True, "created": created}, {"turbo.json": {"seconds": 83.4, "mode": "turbo"}})
    _fake_job(tmp_path, "bbbb2222", {"simple": True, "created": created}, {"took.json": {"took_s": 120.5}, "turbo.json": {"seconds": 83.4}})
    _fake_job(tmp_path, "cccc3333", {"simple": True, "created": created}, {"simple/simple.json": {"seconds": 41.4}})
    old = _fake_job(tmp_path, "dddd4444", {"simple": True, "created": created})
    mtime = datetime.fromisoformat(created).timestamp() + 90.0
    os.utime(old / "xenoform.mp4", (mtime, mtime))
    _fake_job(tmp_path, "eeee5555", {"simple": True, "created": created}, {"turbo.json": {"seconds": 83.4}})
    monkeypatch.setitem(ui._JOBS, "eeee5555", {"id": "eeee5555", "status": "done", "took_s": 7.5})
    _fake_job(tmp_path, "ffff6666", {"simple": True})
    rows = {r["id"]: r for r in client.get("/api/videos").json()["videos"]}
    assert rows["aaaa1111"]["seconds"] == 83.4 and rows["aaaa1111"]["created"] == created
    assert rows["bbbb2222"]["seconds"] == 120.5  # took.json wins over the older manifest
    assert rows["cccc3333"]["seconds"] == 41.4
    assert rows["dddd4444"]["seconds"] == pytest.approx(90.0, abs=1.0)  # meta created vs the file's mtime
    assert rows["eeee5555"]["seconds"] == 7.5  # the live job wins over everything on disk
    assert rows["ffff6666"]["seconds"] is None and rows["ffff6666"]["created"] == ""


def test_generate_job_keeps_honest_timing_and_writes_took_json(client, tmp_path, monkeypatch):
    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        on_progress("analyze", 1.0, "Track already analyzed")
        out.write_bytes(b"the stills draft")
        on_progress("animatic", 0.5, "Scene 1 of 2")
        on_progress("assemble", 1.0, "Animatic locked to the track")
        on_progress("restyle", 0.325, "Morph 3 of 6")
        on_progress("assemble", 0.775, "Cutting shot 6 of 12 to the beat")  # the draft is still up: no new version
        on_progress("assemble", 0.96, "Burning the end card")
        on_progress("assemble", 0.98, "Saving the video")
        time.sleep(0.05)
        out.write_bytes(b"the finished cut")  # the file changed: the next report re-points the player
        on_progress("restyle", 1.0, "GPU morphs locked to the beat")
        on_progress("assemble", 1.0, "Cut ready in 9.0s")
        return {"mode": "turbo", "seconds": 9.0}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    demo = client.get("/api/demo").json()
    started = client.post("/api/generate", json={**demo, "end_card": True, "tiny": True})
    assert started.status_code == 200
    job_id = started.json()["id"]
    job = None
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done" and job["detail"] == "Cut ready in 9.0s"
    assert job["timing"]["plan"]["morphs"] > 0 and job["timing"]["plan"]["card"] == 4.0
    assert [s["phase"] for s in job["stages"]] == ["analyze", "draft", "morphs", "cut", "card", "save", "done"]
    assert job["overall"] == 1.0 and job["eta_s"] == 0.0 and job["took_s"] > 0 and job["elapsed_s"] == job["took_s"]
    assert set(job["breakdown"]) == {"analyze", "draft", "morphs", "cut", "card", "save"}
    assert sum(job["breakdown"].values()) == pytest.approx(job["took_s"], abs=0.5)
    assert job["video_version"] == 3 and job["video"].endswith("?v=3")  # the draft, the finished file, done
    took = json.loads((tmp_path / "jobs" / job_id / "took.json").read_text(encoding="utf-8"))
    assert took["took_s"] == job["took_s"] and took["breakdown"] == job["breakdown"] and took["started"] == job["started"]
    assert took["stages"] == job["stages"]
    assert jt.seconds_for(tmp_path / "jobs" / job_id) == job["took_s"]
