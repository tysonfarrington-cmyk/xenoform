"""Per-run drops (docs/MUSIC_VIDEO_PLAN.md section 2): every drop-labelled run of the song's roles is its own passage
with ``drop_run`` and ``heat`` (the run holding the song's drop at 1.0), ``drop_late`` is only the tail of a long run,
the quiet ending is an outro, and a cut that must lose shots loses its calm ones first."""
from __future__ import annotations

import json
from pathlib import Path

from xenoform import dense, guardrails, pacing

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
GLITCH_DROP = 139.71  # beatfx.drop_time on the bundled mp3: the build two beats before the long drop at 2:21


def _song(song: str = "glitch-out") -> dict:
    f = json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))
    return {"duration": float(f["duration"]), "beats": list(f["beats"]), "sections": list(f["sections"])}


def _plan(song: dict, drop: float | None = GLITCH_DROP, **extra) -> tuple[list[dict], dict]:
    body = {"energy_preset": "dense", "aspect": "9:16", "quality_tier": "draft", **extra}
    body, _ = guardrails.apply(body, duration=song["duration"], beats=song["beats"])
    return dense.shots_for(body, song, None, drop=drop)


def _entries(shots: list[dict]) -> list[dict]:
    return [s for s in shots if s.get("boundary") == "drop"]


def test_every_drop_run_is_its_own_passage_with_heat():
    shots, plan = _plan(_song())
    entries = _entries(shots)
    # Glitch Out's drop runs, each on the beat the analysis put it (1:32, 1:59, 2:21, 3:02, 3:30)
    starts = [round(s["start"], 1) for s in entries]
    assert len(starts) == 5 and all(abs(a - b) < 0.4 for a, b in zip(starts, (92.0, 119.8, 141.1, 182.3, 210.3)))
    assert [s["drop_run"] for s in entries] == [0, 1, 2, 3, 4]
    heat = {s["drop_run"]: s["heat"] for s in entries}
    assert heat[2] == 1.0  # the run that holds the song's drop
    assert heat[1] >= 0.8  # Tys's "drop around 1:59ish", as loud as the main one
    assert 0.2 <= heat[0] < 0.8  # the first, quieter drop at 1:32
    assert plan["drop"] == entries[2]["start"]  # the record's drop is the main run's first beat, not the riser before it
    for s in shots:
        if s["section"] in ("drop", "drop_late"):
            assert s.get("drop_run") is not None and 0.2 <= s["heat"] <= 1.0
        else:
            assert "drop_run" not in s and "heat" not in s
    roles = [p["role"] for p in plan["passages"]]
    assert roles[-1] == "outro" and roles.count("drop") == 5  # the quiet last minute is the outro, not a sixth drop


def test_drop_late_is_only_the_tail_of_a_long_run():
    shots, _ = _plan(_song())
    assert not [s for s in shots if s["section"] == "drop_late"]  # every Glitch Out drop is under 16 bars
    beats = [round(i * 0.5, 4) for i in range(int(120 / 0.5))]  # 120 bpm: 16 bars are 32 s
    secs = [{"label": "calm", "start": 0.0, "end": 30.0, "level": 0.3}, {"label": "drop", "start": 30.0, "end": 90.0, "level": 1.0},
            {"label": "calm", "start": 90.0, "end": 120.0, "level": 0.3}]
    song = {"duration": 120.0, "beats": beats, "sections": secs}
    shots, plan = _plan(song, drop=30.0)
    late = [s for s in shots if s["section"] == "drop_late"]
    drop = [s for s in shots if s["section"] == "drop"]
    assert late and min(s["start"] for s in late) >= 30.0 + 32.0 - 1e-6 and max(s["end"] for s in drop) <= 62.0 + 1e-6
    assert {s["drop_run"] for s in late} == {0} and all(s["heat"] == 1.0 for s in late)
    old = dense.story_plan(120.0, beats, secs, 30.0)["shots"]  # the old plan: late from 8 bars after the one drop
    assert min(s["start"] for s in old if s["section"] == "drop_late") < 62.0 and not any("drop_run" in s for s in old)
    off, _ = _plan(song, drop=30.0, drop_mode="off", breathe=True)  # Breathe on, Drops off: one drop as before
    assert min(s["start"] for s in off if s["section"] == "drop_late") < 62.0 and not any("drop_run" in s for s in off)


def test_drops_max_heats_every_run_and_off_keeps_one_drop():
    shots, _ = _plan(_song(), drop_mode="max")
    assert {s["heat"] for s in _entries(shots)} == {1.0} and len(_entries(shots)) == 5
    old, plan = _plan(_song(), drop_mode="off")  # Breathe and Drops are separate keys: Drops off is one drop, as before
    assert len(_entries(old)) == 1 and not any("heat" in s for s in old)
    assert abs(plan["drop"] - GLITCH_DROP) < 0.4  # the song's drop time, the riser included, as the old plan kept it


def test_a_short_pool_merges_the_calm_shots_first(monkeypatch):
    rows = [{"file": f"cosmic/{i:02d}.jpg", "noun": f"thing {i}"} for i in range(12)]
    monkeypatch.setattr("xenoform.morph_pass.catalogue", lambda: {"cosmic": rows})
    song = _song()
    state = {"vibe": "cosmic", "energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16"}
    state, _ = guardrails.apply(state, duration=song["duration"], beats=song["beats"])
    shots, plan = dense.shots_for(state, song, None, drop=GLITCH_DROP)
    chain = dense.clip_plan(shots, song["duration"], song["beats"], pool=12)
    merged, _, chain = dense.fit_chain(state, song, None, chain, 12, "draft", drop=GLITCH_DROP)
    assert len(merged) == 11 and chain["fits"]
    entries = _entries(merged)
    assert len(entries) == 5  # every drop run still opens on its own shot
    assert abs(sum(float(s["seconds"]) for s in merged) - song["duration"]) < 0.05
    # 14 passages over 11 shots: the calm ones (intro, calm, release, outro: 5 of them) folded first, the drops kept
    calm_passages = {s["passage"] for s in shots if s["section"] in ("calm", "intro", "outro", "release")}
    assert len(calm_passages) == 5 and sum(1 for s in merged if s["section"] in ("calm", "intro", "outro", "release")) <= 2
    assert sum(1 for s in merged if s["section"] in ("drop", "drop_late")) >= 5


def test_merge_to_protected_keeps_the_drops():
    shots = [{"index": i, "start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24, "effects": [], "section": sec}
             for i, sec in enumerate(["calm", "calm", "build", "drop", "drop", "calm", "calm"])]
    shots[3]["boundary"] = "drop"
    shots[3]["drop_run"], shots[4]["drop_run"] = 0, 0
    out = dense._merge_to(shots, 4, protected=True)
    assert [s["section"] for s in out] == ["calm", "build", "drop", "calm"] or [s["section"] for s in out].count("drop") == 2
    assert any(s.get("boundary") == "drop" for s in out) and sum(s["frames"] for s in out) == 7 * 24
    plain = dense._merge_to(shots, 4)  # the old rule: the shortest first, whatever its role
    assert len(plain) == 4


def test_the_prototype_window_holds_the_main_drop():
    """The default prototype is cut around the drop; the drop time alone can sit on a build (Ambient: 120 s against the
    drop the analysis puts at 143 s), so a paced Make centres it on the main drop run."""
    ambient = json.loads((SONGS / "ambient.features.json").read_text(encoding="utf-8"))
    assert abs(pacing.main_drop(ambient, 120.12) - 142.94) < 0.6
    glitch = json.loads((SONGS / "glitch-out.features.json").read_text(encoding="utf-8"))
    assert abs(pacing.main_drop(glitch, GLITCH_DROP) - 141.15) < 0.6
    wobble = json.loads((SONGS / "morphing-wobble.features.json").read_text(encoding="utf-8"))
    assert abs(pacing.main_drop(wobble, 84.42) - 84.42) < 0.6  # a run the drop sits inside is split on it
    from xenoform import ui

    win, start, drop = ui._window_features(ambient, None, 30.0, paced=True)
    assert win["duration"] == 30.0  # no audio, no drop time: the old anchor (60 % in)
    assert pacing.main_drop({"duration": 30.0, "beats": [], "sections": []}, 12.0) == 12.0


def test_a_drop_inside_a_run_splits_it_into_a_build_and_the_drop():
    beats = [round(i * 0.5, 4) for i in range(60)]
    secs = [{"label": "drop", "start": 0.0, "end": 30.0, "level": 1.0}, {"label": "calm", "start": 30.0, "end": 30.0, "level": 0.2}]
    song = {"duration": 30.0, "beats": beats, "sections": secs + [{"label": "calm", "start": 29.0, "end": 30.0, "level": 0.2}]}
    shots, plan = _plan({**song, "sections": [secs[0], {"label": "calm", "start": 22.0, "end": 30.0, "level": 0.2}]}, drop=13.5)
    roles = [p["role"] for p in plan["passages"]]
    assert roles[:2] == ["build", "drop"] and abs(plan["drop"] - 13.5) < 0.3
    entry = next(s for s in shots if s.get("boundary") == "drop")
    assert abs(entry["start"] - 13.5) < 0.3 and entry["heat"] == 1.0


def test_refine_roles_moves_a_drop_onto_its_drop_and_ends_on_an_outro():
    song = _song()
    rows = dense._story_roles(dense._analysis_sections(song), song["duration"], min_len=max(6.0, 8 * dense._period(song["beats"])))
    assert rows[-1]["role"] == "drop" and round(rows[4]["start"], 2) == 87.31  # the analysis as it was
    refined = pacing.refine_roles(rows, dense._analysis_sections(song), period=dense._period(song["beats"]))
    assert refined[-1]["role"] == "outro"
    first = next(r for r in refined if r["role"] == "drop")
    assert round(first["start"], 2) == 91.98 and refined[refined.index(first) - 1]["end"] == first["start"]
