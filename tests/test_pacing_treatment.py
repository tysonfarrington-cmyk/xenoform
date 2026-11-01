"""The drop treatment (docs/MUSIC_VIDEO_PLAN.md section 3): every drop run opens with an event (the punch and the
stutter, Snap, a Shatter or a Spin, the vibe's drop transition or a boundary kind, a fresh object family), the four bars
before it ramp, a long run plants an event every 8 bars, and only a hot run's first two bars cut on the half bar."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np

from xenoform import boundary_fx as B, dense, foreshadow as F, guardrails, morph_timing as MT, pacing

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "tests" / "fixtures" / "analyses"  # frozen, so a rebuilt song moves no plan here
GLITCH_DROP = 139.71
BEAT = 60.0 / 90.0


def _song() -> dict:
    f = json.loads((SONGS / "glitch-out.features.json").read_text(encoding="utf-8"))
    return {"duration": float(f["duration"]), "beats": list(f["beats"]), "sections": list(f["sections"])}


def _plan(song=None, drop=GLITCH_DROP, **extra):
    song = song or _song()
    body = {"energy_preset": "dense", "aspect": "9:16", "quality_tier": "draft", **extra}
    body, _ = guardrails.apply(body, duration=song["duration"], beats=song["beats"])
    shots, plan = dense.shots_for(body, song, None, drop=drop)
    return shots, plan, body


def _shaped(shots, body, **kw):
    work = copy.deepcopy(shots)
    for s in work:
        s["frames"] = int(round(float(s["seconds"]) * 24))
    pacing.shape(work, {"intensity": 0.5, "chaos": 0.3}, breathe=pacing.breathe_amount(body), drop_mode=pacing.drop_mode_of(body),
                 beats=_song()["beats"], look="house", **kw)
    return work


def test_every_drop_run_opens_with_an_event():
    for extra in ({}, {"breathe": 0.5}):  # a plain Make, and Breathe
        shots, plan, body = _plan(**extra)
        entries = [i for i, s in enumerate(shots) if s.get("event") == "drop"]
        assert len(entries) == 5 and all(shots[i].get("boundary") == "drop" for i in entries)
        for i in entries:
            types = {e["type"] for e in shots[i]["effects"]}
            assert "punch" in types and ("stutter" in types or shots[i]["heat"] < 0.5)
        work = _shaped(shots, body)
        assert all(work[i]["timing"] == {"mode": "snap"} for i in entries)  # Snap on every run's first beat
        styles = pacing.styles(shots, {**body, "morph_style": "auto"}, plan["drop"])
        assert all(styles[i] in ("shatter", "spin") for i in entries)
        main = next(i for i in entries if abs(shots[i]["start"] - plan["drop"]) < 0.06)
        assert styles[main] == "shatter"  # the main run always shatters; the runs either side of it spin
        assert [styles[i] for i in entries] == ["shatter", "spin", "shatter", "spin", "shatter"]
        # the vibe's drop transition opens every run (the guard counts its cap a run), else a boundary kind
        trans = dense.boundary_transitions(work, "chrome-mercury", seed=1, per_run=True)
        capped = dense.boundary_transitions(work, "chrome-mercury", seed=1)
        assert sum(1 for i in entries if trans[i]) == 5 and sum(1 for i in entries if capped[i]) <= 2
        picks = B.pick(work, {"intensity": 0.5, "chaos": 0.3}, _song()["beats"], 24, seed=2, premium=trans,
                       paced={"breathe": pacing.breathe_amount(body)})
        for i in entries:  # the run's next handoff takes its kind, the drop transition holding its first
            assert picks[i] is None and picks[i + 1] is not None
        bare = B.pick(work, {"intensity": 0.5, "chaos": 0.3}, _song()["beats"], 24, seed=2, paced={"breathe": False})
        assert all(bare[i] for i in entries)  # with no premium transition the run's first handoff takes the kind


def test_the_four_bars_before_a_run_ramp():
    for extra, step in (({}, 4.0), ({"breathe": 0.5}, 2.0)):
        shots, plan, body = _plan(**extra)
        ramps = [s for s in shots if s.get("ramp") is not None]
        assert ramps and all(s["section"] not in ("drop", "drop_late") for s in ramps)
        for s in ramps:
            assert float(s["seconds"]) / BEAT <= step + 0.6  # the shots halved
        nxt = {i: shots[i + 1] for i, s in enumerate(shots[:-1]) if s.get("ramp") is not None}
        assert all(n.get("ramp") is not None or n.get("event") == "drop" for n in nxt.values())  # a ramp runs into its drop
        work = _shaped(shots, body)
        by_run: list[list[dict]] = []
        for s in work:
            if s.get("ramp") is None:
                if by_run and by_run[-1]:
                    by_run.append([])
                continue
            if not by_run:
                by_run.append([])
            by_run[-1].append(s)
        for run in [r for r in by_run if len(r) > 1]:
            assert run[-1]["fx_intensity"] >= run[0]["fx_intensity"]  # rising to the drop
            assert run[-1]["fx_intensity"] == 1.0
            assert run[-1].get("fx_names") == ["dither"]  # dither comes in
        if body.get("breathe"):
            assert any(s.get("timing") == {"mode": "snap"} for s in work if (s.get("ramp") or 0) >= 0.75)


def test_hot_runs_cut_their_first_two_bars_on_the_half_bar_and_nothing_is_shorter():
    shots, plan, body = _plan()
    for i, s in enumerate(shots):
        assert float(s["seconds"]) / BEAT >= 1.85  # nothing under two beats
        last_of_run = i + 1 == len(shots) or shots[i + 1].get("passage") != s.get("passage")
        if s["section"] in ("drop", "drop_late") and float(s["seconds"]) / BEAT < 2.5 and not last_of_run:
            run_start = next(t["start"] for t in shots if t.get("event") == "drop" and t["drop_run"] == s["drop_run"])
            assert s["heat"] >= pacing.ENTRY_HEAT and s["start"] - run_start < pacing.ENTRY_BARS * 4 * BEAT + 0.1
    cool = [s for s in shots if s.get("drop_run") == 0]  # Glitch Out's first drop, heat 0.57: a bar a shot
    assert cool[0]["heat"] < pacing.ENTRY_HEAT and all(float(s["seconds"]) / BEAT >= 3.9 for s in cool[:-1])
    hot, _, _ = _plan(drop_mode="max")
    hot_first = [s for s in hot if s.get("drop_run") == 0]
    assert hot_first[0]["heat"] == 1.0 and float(hot_first[0]["seconds"]) / BEAT < 2.5


def test_a_whole_songs_main_run_opens_on_a_whole_bar_for_its_hero():
    """The hero holds a bar (1 Nov): with ``hold_main`` (a whole song's plan) the heaviest run opens on one shot of a
    whole bar, its event, punch and stutter on its first beat, and its half-bar entry shots start from its second bar;
    the other runs open as before, and a plan without it is unchanged."""
    song = _song()
    args = (song["duration"], song["beats"], song["sections"], GLITCH_DROP)
    plain = pacing.song_plan(*args, breathe=0.5)
    held = pacing.song_plan(*args, breathe=0.5, hold_main=True)
    assert not any(s.get("hero_bar") for s in plain["shots"])
    runs = [p for p in held["passages"] if "drop_run" in p]
    k = pacing.heaviest([{"heat": p["heat"], "seconds": p["end"] - p["start"], "opens": p["main"]} for p in runs])
    main = runs[k]["drop_run"]
    bar = 4 * held["period"]

    def run_shots(plan, run):
        return [s for s in plan["shots"] if s.get("drop_run") == run]

    first = run_shots(held, main)
    assert first[0]["hero_bar"] and first[0]["event"] == "drop" and abs((first[0]["end"] - first[0]["start"]) - bar) < 0.1 * bar
    assert [fx["type"] for fx in first[0]["effects"]] == ["punch", "stutter"] and first[0]["effects"][0]["t"] == first[0]["start"]
    assert runs[k]["heat"] >= pacing.ENTRY_HEAT and all(abs((s["end"] - s["start"]) - bar / 2) < 0.2 * bar for s in first[1:3])
    before = run_shots(plain, main)
    assert abs((before[0]["end"] - before[0]["start"]) - bar / 2) < 0.2 * bar  # it opened on two beats
    assert first[0]["start"] == before[0]["start"] and first[0]["end"] == before[1]["end"]  # its first two shots, one bar
    assert sum(1 for s in held["shots"] if s.get("hero_bar")) == 1
    for p in runs:
        if p["drop_run"] != main:
            assert run_shots(held, p["drop_run"])[0]["end"] == run_shots(plain, p["drop_run"])[0]["end"]


def test_a_long_run_plants_an_event_every_eight_bars():
    beats = [round(i * 0.5, 4) for i in range(int(240 / 0.5))]  # 120 bpm: a bar is 2 s, 8 bars 16 s
    secs = [{"label": "calm", "start": 0.0, "end": 40.0, "level": 0.3}, {"label": "drop", "start": 40.0, "end": 200.0, "level": 1.0},
            {"label": "calm", "start": 200.0, "end": 240.0, "level": 0.3}]
    song = {"duration": 240.0, "beats": beats, "sections": secs}
    shots, plan, body = _plan(song, drop=40.0)
    events = [(round(s["start"]), s["event"]) for s in shots if s.get("event")]
    assert events[0] == (40, "drop")
    marks = [t for t, _ in events[1:]]
    assert marks == [56, 72, 88, 104, 120, 136, 152, 168, 184]  # every 8 bars of the run
    assert [e for _, e in events[1:5]] == ["style", "kind", "style", "kind"]
    assert any(s["section"] == "drop_late" for s in shots) and all(s.get("event") in (None, "style", "kind", "drop") for s in shots)
    styles = pacing.styles(shots, {**body, "morph_style": "auto"}, plan["drop"])
    for i, s in enumerate(shots):
        if s.get("event") == "style":
            assert styles[i] not in (styles[i - 1], styles[i + 1])
    work = _shaped(shots, body)
    picks = B.pick(work, {"intensity": 0.5, "chaos": 0.3}, beats, 24, seed=1, paced={"breathe": False})
    for i, s in enumerate(shots):
        if s.get("event") == "kind":
            assert picks[i] is not None


def test_the_drop_snaps_hardest_on_every_run():
    shots, plan, body = _plan()
    work = _shaped(shots, body)
    MT.plan(work, "smooth", _song()["beats"], plan["drop"])
    period = MT._period(_song()["beats"])
    for s in work:
        if s.get("event") == "drop":
            assert s["timing"]["mode"] == "snap" and abs(s["timing"]["hits"][0] - (s["start"] + MT.DROP_LAG * period)) < 1e-3
            assert abs(s["timing"]["width"] - MT.DROP_WIDTH * period) < 1e-3


def test_a_drop_lands_on_a_fresh_family():
    shots = [{"start": float(i), "end": float(i + 1), "event": "drop" if i == 3 else None, "drop_run": 0 if i >= 3 else None}
             for i in range(6)]
    stills = [{"noun": n, "family": fam, "file": f"{k}.jpg"} for k, (n, fam) in
              enumerate([("rose", "flowers"), ("tulip", "flowers"), ("lily", "flowers"), ("orchid", "flowers"),
                         ("peony", "flowers"), ("owl", "birds"), ("lotus", "flowers")])]
    out, moved = pacing.fresh_at_drops(stills, shots)
    assert moved == 1 and out[4]["noun"] == "owl" and sorted(r["noun"] for r in out) == sorted(r["noun"] for r in stills)
    pinned = [dict(r) for r in stills]
    pinned[4]["pinned"] = True
    assert pacing.fresh_at_drops(pinned, shots)[1] == 0  # a pinned still holds its slot
    same, n = pacing.fresh_at_drops([dict(r, family="flowers") for r in stills], shots)
    assert n == 0  # one family all through (a theme): nothing to swap in


def test_a_ramp_cuts_on_the_drums_strong_hits():
    beats = [round(i * 0.5, 4) for i in range(int(64 / 0.5))]
    secs = [{"label": "calm", "start": 0.0, "end": 32.0, "level": 0.3}, {"label": "drop", "start": 32.0, "end": 64.0, "level": 1.0}]
    plain = pacing.song_plan(64.0, beats, secs, 32.0, breathe=0.5)
    hits = [24.5, 26.5, 28.5, 30.5]  # odd beats of the ramp (24 to 32 s)
    on = pacing.song_plan(64.0, beats, secs, 32.0, breathe=0.5, hits=hits)
    cuts = lambda p: sorted(round(s["start"], 2) for s in p["shots"] if 24.0 <= s["start"] < 32.0)  # noqa: E731
    assert set(cuts(on)) & set(hits) and not set(cuts(plain)) & set(hits)


def test_the_foreshadow_comes_earlier_in_a_ramp():
    frame = np.zeros((8, 8, 3), np.uint8)
    shots = [{"frames": 48}, {"frames": 48, "ramp": 0.9}, {"frames": 48}]
    plan = F.plan(shots, ["a", "b", "c"], [i * 0.5 for i in range(16)], 24, "trace", {"lead_beats": 2.0},
                  read_edge=lambda clip, which: frame)
    assert plan[1]["lead"] > plan[0]["lead"]


def _window(start: float, length: float = 30.0) -> dict:
    """A Length window as the desk trims it: from the beat at or before ``start``, beats and sections shifted."""
    f = json.loads((SONGS / "glitch-out.features.json").read_text(encoding="utf-8"))
    beats = [float(b) for b in f["beats"]]
    s0 = max([b for b in beats if b <= start + 1e-6] or [0.0])
    return {"duration": length, "beats": [round(b - s0, 4) for b in beats if s0 <= b < s0 + length],
            "sections": [{**s, "start": round(max(0.0, s["start"] - s0), 4), "end": round(min(length, s["end"] - s0), 4)}
                         for s in f["sections"] if s["end"] > s0 and s["start"] < s0 + length]}


def test_a_window_end_leaves_no_sliver():
    """Nothing under two beats, the last shot included: the 1:45 window of Glitch Out under Breathe stopped 0.9 s into
    its last ramp shot (the window ends where it ends, mid-bar); the end now folds into the shot before it."""
    for start in (105.0, 0.0, 60.0):
        for extra in ({"breathe": True}, {"breathe": 0.5}, {}, {"drop_mode": "max"}):
            win = _window(start)
            shots, plan, _ = _plan(song=win, drop=None, **extra)
            assert plan["name"] == "story" and shots[-1]["end"] == 30.0
            assert all(float(s["seconds"]) / BEAT >= 1.85 for s in shots), (start, extra, [round(s["seconds"], 2) for s in shots])
