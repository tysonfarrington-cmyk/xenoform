"""Breathe round two (Tys, 31 Oct: "the settings you used for breathe may be too subtle"): an amount, and at full
Breathe (true, 1.0) the calm passages are scenes against drops left as the drop treatment makes them. A scene is one
look a passage, held 3 to 4 bars a shot: a morph of at most two bars, then a rest of a bar or more where nothing moves
but the music; no effect, no handoff kind, no flash, one object family. Builds tighten from two bars a shot to one.
On one song the looks a minute in the drops are at least three times the grooves'."""
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from xenoform import boundary_fx as B, dense, guardrails, lane, pacing, presets

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
GLITCH_DROP = 139.71
BEAT = 60.0 / 90.0  # Glitch Out
BAR = 4 * BEAT


def _song() -> dict:
    f = json.loads((SONGS / "glitch-out.features.json").read_text(encoding="utf-8"))
    return {"duration": float(f["duration"]), "beats": list(f["beats"]), "sections": list(f["sections"])}


def _plan(amount=True, **extra):
    song = _song()
    body = {"energy_preset": "dense", "aspect": "9:16", "quality_tier": "draft", "breathe": amount, **extra}
    body, _ = guardrails.apply(body, duration=song["duration"], beats=song["beats"])
    shots, plan = dense.shots_for(body, song, None, drop=GLITCH_DROP)
    return shots, plan, body


def _shaped(shots, amount=True, **kw):
    work = copy.deepcopy(shots)
    for s in work:
        s["frames"] = int(round(float(s["seconds"]) * 24))
    pacing.shape(work, kw.pop("macros", {"intensity": 0.5, "chaos": 0.3}), breathe=amount, drop_mode="auto",
                 beats=_song()["beats"], look="house", **kw)
    return work


def _scene(s: dict) -> bool:
    return s["section"] in pacing.SCENE_ROLES and s.get("ramp") is None


def test_the_amount_reads_true_numbers_and_words():
    A = pacing.amount_of
    assert (A(True), A(False), A(None), A(""), A(0.5), A(2), A(-1)) == (1.0, 0.0, 0.0, 0.0, 0.5, 1.0, 0.0)
    assert (A("on"), A("off"), A("0.75"), A("true"), A("0")) == (1.0, 0.0, 0.75, 1.0, 0.0)
    assert pacing.breathe_amount({}) == 0.0 and pacing.breathe_amount({"breathe": True}) == 1.0
    assert pacing.breathe_of({"breathe": 0.3}) and not pacing.breathe_of({"breathe": 0})
    assert (pacing.boldness(0.5), pacing.boldness(0.75), pacing.boldness(True), pacing.boldness(0.2)) == (0.0, 0.5, 1.0, 0.0)
    assert pacing.breathe_table(0.5) == pacing.BREATHE and pacing.breathe_table(1.0) == pacing.BOLD
    assert pacing.breathe_table(0.75)["calm"] == 8  # whole bars between
    assert pacing.profile_at("calm", 0.5) == pacing.PROFILE["calm"]  # 0.5 is the first round's profile
    bold = pacing.profile_at("calm", 1.0)
    assert (bold["timing"], bold["effect"], bold["kinds"], bold["flash"], bold["chaos"]) == ("smooth", None, False, 0, pacing.BOLD_CHAOS)
    assert pacing.profile_at("drop", 1.0) == pacing.PROFILE["drop"]  # the drops stay as the treatment makes them
    assert pacing.recut_modes({"breathe": True}) == {"breathe": 1.0, "drop_mode": "off"}
    assert pacing.legacy({"breathe": 0.0, "drop_mode": "off"}) and not pacing.legacy({"breathe": 0.5, "drop_mode": "off"})


def test_a_scene_is_a_morph_of_two_bars_and_a_rest_of_a_bar_or_more():
    shots, plan, _ = _plan()
    assert plan["breathe"] == 1.0 and plan["steps"]["calm"] == 12 and plan["steps"]["intro"] == 16
    scenes = [s for s in shots if _scene(s)]
    assert len(scenes) >= 6
    for s in scenes:
        beats = float(s["seconds"]) / BEAT
        assert 7.8 <= beats <= 4 * pacing.SCENE_MAX / 4 + 4.3, s  # two bars at least, a stretch of four with its rest
        assert s.get("rest") and 4 <= int(s["rest"]) <= pacing.REST_MAX, s  # a rest after every morph
        morph = float(s["seconds"]) - float(s["rest_s"])
        # the morph over two bars (the grid's own beats), longer only where a passage's last bars folded into its last shot
        # and the rest is already two bars; never played slower than 0.6x (a clip is at most 5 s)
        assert morph <= pacing.MORPH_BEATS * BEAT * 1.06 or int(s["rest"]) == pacing.REST_MAX, s
        assert morph * pacing.MIN_PLAY <= float(s["render_s"]) + 1e-6, s
    assert not any(s.get("rest") for s in shots if s["section"] in ("drop", "drop_late"))  # never in a drop
    # the first profile rested only at the passages' ends
    half, _, _ = _plan(0.5)
    assert sum(1 for s in half if s.get("rest")) < sum(1 for s in scenes)


def test_builds_tighten_from_two_bars_to_one_and_the_drops_stay():
    shots, plan, _ = _plan()
    builds = {}
    for s in shots:
        if s["section"] == "build" and s.get("ramp") is None:
            builds.setdefault(s["passage"], []).append(s)
    long_build = max(builds.values(), key=len)
    lengths = [round(float(s["seconds"]) / BEAT) for s in long_build]
    assert max(lengths[: len(lengths) // 3]) >= 8 and max(lengths[-3:]) <= 4  # two bars a shot, then one
    half, _, _ = _plan(0.5)
    drops = [(s["start"], s["end"]) for s in shots if s["section"] in ("drop", "drop_late")]
    drops_half = [(s["start"], s["end"]) for s in half if s["section"] in ("drop", "drop_late")]
    assert drops == drops_half  # the drops cut as the treatment cuts them, at every amount
    assert all(float(s["seconds"]) / BEAT >= 1.85 for s in shots)  # nothing under two beats


def test_a_scene_is_one_look_with_no_effect_no_kind_and_no_flash():
    shots, plan, body = _plan()
    work = _shaped(shots, effects=["feedback"])  # the cut asked for an effect: its builds and drops get it, never a scene
    for s in work:
        if _scene(s):
            assert s["fx_names"] == [] and "timing" not in s and s["chaos"] <= pacing.BOLD_CHAOS + 1e-9, s
            assert s["fx_intensity"] <= 0.36
    assert any(s["fx_names"] == ["feedback"] for s in work if s["section"] in ("drop", "build"))
    styles = pacing.styles(shots, {"breathe": True, "morph_style": "auto"}, plan["drop"], period=plan["period"])
    by_passage: dict[int, set] = {}
    for s, st in zip(shots, styles):
        if s["section"] in pacing.SCENE_ROLES:
            by_passage.setdefault(s["passage"], set()).add(st)
    assert by_passage and all(len(v) == 1 for v in by_passage.values())  # one style a scene passage
    calm = [next(iter(v)) for p, v in sorted(by_passage.items()) if shots[[s["passage"] for s in shots].index(p)]["section"] == "calm"]
    assert len(set(calm)) == len(calm) or len(calm) < 2  # the next calm passage the next style in turn
    picks = B.pick(work, {"intensity": 0.5, "chaos": 0.6}, _song()["beats"], 24, seed=3, paced={"breathe": 1.0})
    assert not any(picks[i] for i, s in enumerate(work) if i and s["section"] in pacing.SCENE_ROLES)  # plain handoffs
    assert any(picks[i] for i, s in enumerate(work) if s["section"] == "drop")  # the drops keep theirs
    rules = pacing.flash_rules(work, 24, _song()["beats"], breathe=1.0)
    k = 0
    for s in work:
        n = int(s["frames"])
        if _scene(s):
            assert all(r[0] == 0.0 and r[1] == 0 for r in rules[k:k + n])  # no flash at all in a scene
        k += n


def test_the_drops_play_three_times_the_looks_of_the_grooves():
    shots, plan, _ = _plan()
    work = _shaped(shots)
    styles = pacing.styles(shots, {"breathe": True, "morph_style": "auto"}, plan["drop"], period=plan["period"])
    passages = pacing.passage_of(shots)
    secs, looks = Counter(), Counter()
    for i, s in enumerate(shots):
        g = {"calm": "groove", "sustain": "groove"}.get(s["section"], s["section"])
        secs[g] += float(s["seconds"])
        key = (styles[i], (work[i].get("timing") or {}).get("mode"), tuple(work[i].get("fx_names") or []))
        prev = (styles[i - 1], (work[i - 1].get("timing") or {}).get("mode"), tuple(work[i - 1].get("fx_names") or [])) if i else None
        looks[g] += int(i == 0 or passages[i] != passages[i - 1] or key != prev)
    rate = {g: 60.0 * looks[g] / secs[g] for g in secs}
    assert rate["groove"] <= 4.0 and rate["drop"] >= 3.0 * rate["groove"], rate


def test_a_scene_does_not_ramp_into_a_drop():
    song = {"duration": 64.0, "beats": [i * 0.5 for i in range(128)],
            "sections": [{"index": 0, "label": "calm", "start": 0.0, "end": 32.0, "level": 0.3},
                         {"index": 1, "label": "drop", "start": 32.0, "end": 64.0, "level": 1.0}]}
    full = pacing.song_plan(64.0, song["beats"], song["sections"], 32.0, breathe=1.0)
    half = pacing.song_plan(64.0, song["beats"], song["sections"], 32.0, breathe=0.5)
    assert not any(s.get("ramp") is not None for s in full["shots"])  # the scene holds to the drop, the drop's event the change
    assert any(s.get("ramp") is not None for s in half["shots"])  # the first profile ramped into it
    entry = next(s for s in full["shots"] if s.get("event") == "drop")
    held = next(s for s in full["shots"] if s["end"] == 32.0)
    assert entry["start"] == 32.0 and held["end"] - held["start"] >= 3.9 and held.get("rest")  # a held scene meets it


def test_a_breathe_cut_may_spend_fewer_morphs_than_its_budget():
    song = _song()
    plain, _, _ = _plan(0.0)
    full, _, _ = _plan(True, max_shots=200)
    assert len(full) < len(plain) < 200  # the cap is a cap, not a target
    tight, plan, _ = _plan(True, max_shots=50)
    assert len(tight) <= 50 and all(v <= pacing.SCENE_MAX for r, v in plan["steps"].items() if r in pacing.SCENE_ROLES)
    del song


def test_one_object_family_a_scene():
    fam = ["sea-creatures", "shells-and-corals"]
    stills = [{"file": f"s{i}.jpg", "noun": f"n{i}", "family": fam[i % 2]} for i in range(14)]
    stills[5]["pinned"] = True
    shots = []
    t = 0.0
    for i, (role, p) in enumerate([("intro", 0), ("calm", 1), ("calm", 1), ("calm", 1), ("drop", 2), ("drop", 2),
                                   ("calm", 3), ("calm", 3), ("calm", 3), ("outro", 4)]):
        s = {"start": t, "end": t + 4.0, "section": role, "passage": p, "clip": i}
        if role == "drop" and (i == 0 or shots[-1]["section"] != "drop"):
            s["event"] = "drop"
        shots.append(s)
        t += 4.0
    out, moved = pacing.scene_families(stills, shots)
    assert moved > 0 and sorted(r["file"] for r in out) == sorted(r["file"] for r in stills)  # nothing repeats, nothing lost
    assert out[5] is stills[5] and out[5]["file"] == "s5.jpg"  # a pinned still stays
    assert out[5 + 0]["file"] == stills[5]["file"] and out[4 + 1] is stills[5]
    for p in (1, 3):
        landing = [int(s["clip"]) + 1 for s in shots if s["passage"] == p]
        families = {out[k]["family"] for k in landing if not out[k].get("pinned")}
        assert len(families) == 1, (p, families)
    entry = next(s for s in shots if s.get("event") == "drop")
    assert out[int(entry["clip"]) + 1] is stills[int(entry["clip"]) + 1]  # the drop's fresh landing stays


def test_the_lane_shows_each_passage_and_its_hold():
    shots, _, _ = _plan()
    beats = _song()["beats"]
    info = {"shots": shots[:12], "stills": [f"x/{i:02d}_thing.jpg" for i in range(13)], "clips": ["c"] * 12, "beats": beats,
            "pacing": {"breathe": 1.0, "drop_mode": "auto", "line": "5 drops"}}
    got = lane.build(info, "v1")
    assert got["breathe"] == 1.0
    calm = next(s for s in got["sections"] if s["section"] == "calm")
    assert calm["hold_bars"] >= 2.5 and calm["shots"] >= 2 and calm["rests"] == calm["shots"]
    app = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    assert "sec.hold_bars" in app.split("function shotsLane(easy)")[1].split("\nfunction ")[0]


def test_presets_still_carry_breathe_off(tmp_path, monkeypatch):
    for p in presets.load():
        assert presets.body(p)["breathe"] == 0 and presets.body(p)["drop_mode"] == "off"
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"presets": [{"id": "half", "name": "Half", "vibe": "black", "breathe": 0.5},
                                         {"id": "full", "name": "Full", "vibe": "black", "breathe": True},
                                         {"id": "word", "name": "Word", "vibe": "black", "breathe": "yes"}]}), encoding="utf-8")
    monkeypatch.setenv("XENO_PRESETS", str(f))
    assert {p["id"]: presets.body(p)["breathe"] for p in presets.load()} == {"half": 0.5, "full": 1.0, "word": 0.0}


def test_a_full_breathe_make_records_its_amount_and_its_scenes(tmp_path, monkeypatch):
    from xenoform import beatfx

    seen = {}

    def spy(clips, shots, audio, out, **kw):
        seen["shots"] = copy.deepcopy(shots)
        seen["tame"] = kw.get("tame")
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    pool = [{"path": f"s{i}.png", "file": f"s{i}.png", "noun": f"n{i}", "family": ("sea-creatures", "shells-and-corals")[i % 2]}
            for i in range(80)]
    monkeypatch.setattr(dense, "stills_for", lambda state, n, **kw: ("black", [dict(pool[i]) for i in range(n)]))
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i}.mp4" for i in range(len(shots))])
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: GLITCH_DROP)
    song = _song()
    demo = ROOT / "examples" / "demo.wav"
    body, _ = guardrails.apply({"vibe": "black", "aspect": "16:9", "energy_preset": "dense", "breathe": True},
                               duration=song["duration"], beats=song["beats"])
    dense.run_simple(song, demo, tmp_path / "a.mp4", tmp_path / "a", {}, body, lambda *a: None, engine="mock")
    rec = json.loads((tmp_path / "a" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert rec["pacing"]["breathe"] == 1.0 and rec["recut_state"]["breathe"] == 1.0
    assert "rests" in rec["pacing"]["line"]
    assert any(isinstance(n, dict) and n.get("scene_families") for n in rec.get("fallbacks") or [])  # one family a scene
    scenes = [s for s in seen["shots"] if _scene(s)]
    assert scenes and all(s.get("rest_s") for s in scenes if float(s["seconds"]) / BEAT >= 7.8)
    assert seen["tame"] and len(seen["tame"]) == sum(int(s["frames"]) for s in seen["shots"])
