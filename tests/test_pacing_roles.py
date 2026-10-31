"""Roles that are true (docs/MUSIC_VIDEO_PLAN.md section 2): the story plan runs whenever the song is over
``LONG_SONG_S`` and has sections, a Forms count or an off-centre Speed scales it by role instead of replacing it, the
morph_density guardrail hands the planner a budget instead of rewriting "auto", a beatless stretch gets a tempo grid,
the desk's estimate plans with the Make's own planner, and the record keeps the window."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenoform import dense, guardrails, job_timing, pacing

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"


def _features(song: str) -> dict:
    return json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))


def _window(song: str, start: float, length: float) -> dict:
    f = _features(song)
    beats = [float(b) for b in f["beats"]]
    start = max(b for b in beats if b <= start + 1e-6)
    end = start + length
    return {"duration": length, "beats": [round(b - start, 4) for b in beats if start <= b < end],
            "sections": [{**s, "start": round(max(0.0, s["start"] - start), 4), "end": round(min(length, s["end"] - start), 4)}
                         for s in f["sections"] if s["end"] > start and s["start"] < end]}


def _whole(song: str) -> dict:
    f = _features(song)
    return {"duration": float(f["duration"]), "beats": list(f["beats"]), "sections": list(f["sections"])}


def _make_body(directed: dict, **extra) -> dict:
    body = {"energy_preset": "dense", "aspect": "9:16", "quality_tier": "draft", **extra}
    body, _ = guardrails.apply(body, duration=directed["duration"], beats=directed["beats"])
    return body


def test_the_default_prototype_gets_roles():
    """The 30 s prototype of a song above 90 BPM went through dense_plan(22): no roles, no boundaries."""
    win = _window("morphing-wobble", 70.92, 30.0)  # 144 bpm, the window the desk trims around the drop
    legacy = _make_body(win, breathe=False, drop_mode="off")
    assert legacy["morph_count"] == 22 and "form_budget" not in legacy  # today's rewrite, kept for the old cut
    _, old = dense.shots_for(legacy, win, None, drop=13.5)
    assert old["name"] == "dense (22 forms)"
    body = _make_body(win)  # a plain Make: Breathe off, Drops auto
    assert body.get("morph_count", "auto") == "auto" and body["form_budget"] == 15.0
    shots, plan = dense.shots_for(body, win, None, drop=13.5)
    assert plan["name"] == "story" and all(s.get("section") for s in shots)
    assert len(shots) <= round(30.0 / 20.0 * 15)  # the budget, spent by the planner
    whole, plan_w = dense.shots_for(_make_body(_whole("glitch-out")), _whole("glitch-out"), None, drop=139.71)
    assert plan_w["name"] == "story" and {s["section"] for s in whole} >= {"intro", "calm", "build", "drop"}


def test_a_count_or_the_speed_scales_the_story_plan_by_role():
    song = _whole("glitch-out")
    base, plan = dense.shots_for(_make_body(song), song, None, drop=139.71)
    fast, plan_f = dense.shots_for(_make_body(song, macros={"speed": 0.9}), song, None, drop=139.71)
    slow, plan_s = dense.shots_for(_make_body(song, macros={"speed": 0.1}), song, None, drop=139.71)
    assert plan_f["name"] == plan_s["name"] == "story"  # Speed used to swap the plan for dense_plan
    assert len(slow) < len(base) < len(fast)
    forms, plan_n = dense.shots_for(_make_body(song, morph_count=30), song, None, drop=139.71)
    assert plan_n["name"] == "story" and 24 <= len(forms) <= 33
    # the calm passages gave up their morphs first: their shots are the longest
    by = {}
    for s in forms:
        by.setdefault(s["section"], []).append(float(s["seconds"]))
    assert max(by["calm"]) > max(by["drop"]) and sum(by["drop"]) / len(by["drop"]) < sum(by["calm"]) / len(by["calm"])
    capped, plan_c = dense.shots_for(_make_body(song, max_shots=20), song, None, drop=139.71)
    assert len(capped) <= 20 and plan_c["name"] == "story"
    # under the passages' own count only the chain's merge gets there (a cut at every role start), as before
    chain = dense.clip_plan(base, song["duration"], song["beats"], pool=12)
    merged, _, chain = dense.fit_chain(_make_body(song), song, None, chain, 12, "draft", drop=139.71)
    assert len(merged) == chain["morphs"] == 11 and chain["fits"]


def test_the_guardrail_hands_a_budget_and_expert_keeps_the_old_behaviour():
    body, rep = guardrails.apply({"morph_count": "auto", "energy_preset": "dense"}, duration=30.0, beats=[i * 0.4 for i in range(75)])
    assert body.get("morph_count", "auto") == "auto" and body["form_budget"] == 15.0 and "morph_density" not in {x["id"] for x in rep["applied"]}
    old, rep = guardrails.apply({"morph_count": "auto", "energy_preset": "dense", "breathe": False, "drop_mode": "off"},
                                duration=30.0, beats=[i * 0.4 for i in range(75)])
    assert old["morph_count"] == 22 and "morph_density" in {x["id"] for x in rep["applied"]}
    expert, rep = guardrails.apply({"morph_count": "auto", "energy_preset": "dense", "expert": True}, duration=30.0,
                                   beats=[i * 0.4 for i in range(75)])
    assert expert.get("morph_count", "auto") == "auto" and "form_budget" not in expert and rep["warnings"]
    hand, _ = guardrails.apply({"morph_count": 40, "energy_preset": "dense"}, duration=20.0)
    assert hand["morph_count"] == 15  # a count set by hand keeps its clamp


def test_a_beatless_stretch_gets_a_tempo_grid():
    ambient = _whole("ambient")  # no tracked beat before 72 s
    assert min(ambient["beats"]) > 70
    grid = pacing.grid_for(ambient["beats"], ambient["duration"])
    assert grid[0] < 0.6 and max(b - a for a, b in zip(grid, grid[1:])) < 1.0
    assert set(round(b, 4) for b in ambient["beats"]) <= set(round(g, 4) for g in grid)  # tracked beats stay put
    shots, plan = dense.shots_for(_make_body(ambient), ambient, None, drop=120.12)
    assert plan["name"] == "story" and max(float(s["seconds"]) for s in shots if s["end"] <= 72.0) < 10.0
    old, _ = dense.shots_for(_make_body(ambient, breathe=False, drop_mode="off"), ambient, None, drop=120.12)
    assert float(old[0]["seconds"]) > 70.0  # the old plan's 72 s first shot, kept for the old cut
    assert pacing.grid_for([], 4.0, tempo=120) == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]


def test_the_estimate_plans_with_the_makes_planner(monkeypatch):
    rows = [{"file": f"cosmic/{i:02d}.jpg", "noun": f"thing {i}"} for i in range(12)]
    monkeypatch.setattr("xenoform.morph_pass.catalogue", lambda: {"cosmic": rows})
    song = _whole("glitch-out")
    for pool, tier in ((12, "draft"), (None, "draft"), (None, "cloud")):
        body = _make_body(song, vibe="cosmic", quality_tier=tier)
        shots, plan = dense.shots_for(body, song, None, drop=139.71)
        chain = dense.clip_plan(shots, song["duration"], song["beats"], pool=pool, tier=tier)
        if not chain["fits"]:
            shots, plan, chain = dense.fit_chain(body, song, None, chain, pool, tier, drop=139.71)
        summary = dense.plan_summary(song["duration"], song["beats"], "dense", tier, "9:16", drop=139.71, pool=pool,
                                     sections=song["sections"], state=body)
        assert (summary["shots"], summary["morphs"], summary["plan_name"]) == (len(shots), chain["morphs"], "story")
    # the job clock plans the same cut (its features are the trimmed window's own analysis), on the same chain
    win = _window("glitch-out", 105.0, 30.0)
    body = _make_body(win, vibe="cosmic", length_s=30)
    timed = job_timing.plan_for(win, body)
    shots, chain = _fitted(body, win, None, 12, "draft")
    per = dense.estimate(chain["morphs"], "draft", clip_s=chain["clip_s"])["gpu_seconds"]
    assert timed["morphs"] == pytest.approx(per, abs=1)


def _fitted(body: dict, directed: dict, drop, pool, tier: str):
    """The shots and chain a Make of ``body`` gets (the planner, then the chain's cap and merge), as run_simple does."""
    shots, plan = dense.shots_for(body, directed, None, drop=drop)
    chain = dense.clip_plan(shots, directed["duration"], directed["beats"], pool=pool, tier=tier)
    if not chain["fits"]:
        shots, plan, chain = dense.fit_chain(body, directed, None, chain, pool, tier, drop=drop)
    return shots, chain


def test_the_desk_estimate_reads_the_loaded_song():
    """With a song loaded, /api/simple/options plans the window the Make will trim, on its own sections and drop."""
    from fastapi.testclient import TestClient

    from xenoform import ui

    client = TestClient(ui.create_app())
    q = "duration=239&energy=dense&tier=draft&bpm=90&aspect=9:16&length=30&audio_id=song-glitch-out&length_start=105"
    plan = client.get(f"/api/simple/options?{q}").json()["plan"]
    assert plan["plan_name"] == "story" and plan["duration"] == 30.0
    feats = ui._FEATURES["song-glitch-out"]
    win, start, drop = ui._window_features(feats, ui._AUDIO["song-glitch-out"], 30.0, 105)
    assert start == pytest.approx(104.4583, abs=0.01)
    body = _make_body(win)
    shots, chain = _fitted(body, win, drop, ui._pool_count(body), "draft")
    assert plan["shots"] == len(shots) and plan["morphs"] == chain["morphs"]
    grid = client.get("/api/simple/options?duration=239&energy=dense&tier=draft&bpm=90&aspect=9:16&length=30").json()["plan"]
    assert grid["plan_name"].startswith("dense")  # no song loaded: the BPM grid estimate, as before


def test_the_record_keeps_the_window():
    assert dense.window_of({"song_source": {"path": "x.mp3", "offset": 126.208}}, 30.0) == {"song_start": 126.208, "length_s": 30.0}
    assert dense.window_of({}, 238.8) == {"song_start": 0.0, "length_s": 238.8}
    from fractions import Fraction

    from xenoform import edit_export

    marks = edit_export.markers({"window": {"song_start": 126.2, "length_s": 30.0}, "shots": [], "drop": None}, 720, Fraction(24))
    assert marks and marks[0]["frame"] == 0 and marks[0]["name"] == "Song 2:06.2"
    assert edit_export.markers({"window": {"song_start": 0.0, "length_s": 30.0}, "shots": [], "drop": None}, 720, Fraction(24)) == []


def test_the_modes_and_an_old_record():
    assert pacing.breathe_of({}) is False and pacing.drop_mode_of({}) == "auto" and not pacing.legacy({})
    assert pacing.legacy({"breathe": False, "drop_mode": "off"}) and not pacing.legacy({"breathe": True, "drop_mode": "off"})
    assert pacing.drop_mode_of({"drop_mode": "MAX"}) == "max" and pacing.drop_mode_of({"drop_mode": "loud"}) == "auto"
    assert pacing.breathe_of({"breathe": "on"}) and not pacing.breathe_of({"breathe": "off"})
    assert pacing.recut_modes({}) == {"breathe": False, "drop_mode": "off"}  # a record from before the two keys
    assert pacing.recut_modes({"breathe": True, "drop_mode": "max"}) == {"breathe": True, "drop_mode": "max"}


def test_a_capped_plan_spends_its_budget_rather_than_landing_under_it():
    """The budget's doublings halve a whole role's shots at once, so they could land far under the cap (a whole Glitch
    Out on Draft, capped at the chain's 60 morphs, got 45 on a plain Make); what still fits is given back, the role
    that wants it most first, and the calm passages still give up their morphs first."""
    song = _whole("glitch-out")
    for extra in ({}, {"breathe": True}):
        shots, plan = dense.shots_for(_make_body(song, max_shots=60, **extra), song, None, drop=139.71)
        assert 57 <= len(shots) <= 60, (extra, len(shots))
        by: dict[str, list[float]] = {}
        for s in shots:
            by.setdefault(s["section"], []).append(float(s["seconds"]))
        assert max(by["calm"]) > max(by["drop"]) and sum(by["calm"]) / len(by["calm"]) > sum(by["drop"]) / len(by["drop"])
    small, _ = dense.shots_for(_make_body(song, max_shots=20), song, None, drop=139.71)
    assert len(small) <= 20


def test_a_paced_window_plans_on_the_songs_own_beats(tmp_path, monkeypatch):
    """A Length cut is analysed again on its own, and 30 s can hear double time (Glitch Out's 0:00 to 0:30, its first
    14 s without a beat, came back at 180 bpm and every plan ran twice as fast): a paced Make plans on the song's own
    beats, tempo and sections cut to the window, as the Chain row previews it; Breathe off with Drops off keeps the
    window's own analysis, as the old cut did."""
    import wave

    import numpy as np
    from fastapi.testclient import TestClient

    from xenoform import analyze, ui as ui_mod

    sr, seconds = 22050, 24.0
    t = np.arange(int(seconds * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t) * (1 + 0.5 * np.sign(np.sin(2 * np.pi * 1.5 * t)))
    path = tmp_path / "long.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    client = TestClient(ui_mod.create_app())
    audio_id = client.post("/api/analyze", files={"file": ("long.wav", path.read_bytes(), "audio/wav")}).json()["audio_id"]
    with ui_mod._LOCK:  # the song's own analysis: 120 bpm, a calm half and a drop
        song = dict(ui_mod._FEATURES[audio_id])
        song.update({"beats": [round(0.5 * i, 3) for i in range(48)], "tempo": 120.0, "sections": [
            {"index": 0, "label": "calm", "start": 0.0, "end": 12.0, "level": 0.3},
            {"index": 1, "label": "drop", "start": 12.0, "end": 24.0, "level": 1.0}]})
        song.pop("analysis_sections", None)
        ui_mod._FEATURES[audio_id] = song
    real = analyze.analyze_audio

    def doubled(*a, **kw):  # the window alone hears double time
        f = real(*a, **kw)
        f["beats"] = [round(0.25 * i, 3) for i in range(int(float(f["duration"]) / 0.25))]
        f["tempo"] = 240.0
        return f

    from xenoform import pipeline

    monkeypatch.setattr(analyze, "analyze_audio", doubled)  # the desk's analysis of a cut
    monkeypatch.setattr(pipeline, "analyze_audio", doubled)  # and the Make's own (turbo._analyze, pipeline.analyze_file)
    seen = {}

    def fake_run_job(job_id, audio_path, body, cfg, out, cancel_event=None):
        seen["body"] = dict(body)
        with ui_mod._LOCK:
            ui_mod._JOBS[job_id]["status"] = "done"

    monkeypatch.setattr(ui_mod, "_run_job", fake_run_job)
    for extra, paced in (({}, True), ({"breathe": False, "drop_mode": "off"}, False)):
        r = client.post("/api/generate", json={"audio_id": audio_id, "quality": "turbo", "mode": "simple", "vibe": "ocean",
                                               "length_s": 8, "length_start": 6.2, **extra})
        assert r.status_code == 200, r.text
        cut = ui_mod._FEATURES[seen["body"]["audio_id"]]
        assert cut["trimmed_from"]["start"] == 6.0 and abs(float(cut["duration"]) - 8.0) < 0.3
        # what the Make itself plans on: turbo analyses the cut file again, and takes the sidecar over its analysis
        from xenoform import turbo

        wav = ui_mod._AUDIO[seen["body"]["audio_id"]]
        made, _hit = turbo._analyze(Path(wav), {"fps": 12, "analyze": ui_mod.load_config(None)["analyze"]},
                                    tmp_path / f"features_{paced}.json", tmp_path / "cache")
        if paced:
            assert cut["beats"][:4] == [0.0, 0.5, 1.0, 1.5] and len(cut["beats"]) == 16 and cut["tempo"] == 120.0
            # the song's own roles where the window sits (the calm half is the song's intro), not judged inside 8 s
            assert [(s["role"], s["start"], s["end"]) for s in cut["sections"]][0] == ("intro", 0.0, 6.0)
            assert [s["start"] for s in cut["sections"]] == [0.0, 6.0] and cut["sections"][-1]["end"] == 8.0
            assert made["beats"] == cut["beats"] and made["tempo"] == 120.0 and made["sections"] == cut["sections"]
        else:
            assert cut["beats"][:3] == [0.0, 0.25, 0.5] and cut["tempo"] == 240.0  # the old cut: its own analysis
            assert not turbo.window_path(Path(wav)).exists() and made["tempo"] == 240.0


def test_a_window_keeps_the_songs_roles_where_it_sits():
    """Roles judged inside 30 s made Glitch Out's quiet opening a build (the loudest stretch inside the window) and
    opened every window on an intro and closed it on an outro, wherever it sat; a paced window keeps the whole song's
    roles, cut to it. Breathe off with Drops off keeps the analysis as it was."""
    from xenoform import ui as ui_mod

    f = _features("glitch-out")
    audio = SONGS / "glitch_out.mp3"
    win, at, _ = ui_mod._window_features(f, audio, 30.0, 0.0, paced=True)
    assert [s["role"] for s in win["sections"]] == ["intro", "calm", "calm"] and at == 0.0
    win, at, drop = ui_mod._window_features(f, audio, 30.0, 105.0, paced=True)
    assert [s["role"] for s in win["sections"]] == ["build", "release", "drop", "build"] and abs(at - 104.4583) < 1e-3
    shots, plan = dense.shots_for(_make_body(win, breathe=True), win, None, drop=drop)
    assert [p["role"] for p in plan["passages"]] == ["build", "release", "drop", "build"]
    assert next(s for s in shots if s.get("event") == "drop")["start"] == pytest.approx(119.79 - at, abs=0.05)  # 1:59.8
    old, _, _ = ui_mod._window_features(f, audio, 30.0, 105.0, paced=False)
    assert old["sections"] and not any("role" in s for s in old["sections"])
