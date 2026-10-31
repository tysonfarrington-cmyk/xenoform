"""Clips follow the whole pacing engine (Tys, 1 Nov: "build it", with rests that never freeze film; docs/MUSIC_VIDEO_PLAN.md
section 8, item 15). A paced clips cut is laid out from the plan an object cut gets (clip_cut.arrange): no shot under a
bar but in a hot drop run's first two bars, every drop run opening on a cut on its first beat to a fresh film (and every
style event of a long run), a rest that is film playing (a clip plays on, a morph hands over to the clip it lands on),
a Breathe scene that holds one film; then shaped as an object cut is (each passage's profile, the boundary kinds by
passage, the flash tame under Breathe), with the pacing block in its record and a re-cut by the same rules."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx, clip_cut, cloud_morph, dense, guardrails, pacing

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
DEMO = ROOT / "examples" / "demo.wav"
FILMS = ("metropolis", "moon", "nosferatu", "general", "caligari", "phantom")


def _features(song: str) -> dict:
    return json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))


def _whole(song: str) -> dict:
    f = _features(song)
    return {"duration": float(f["duration"]), "beats": [float(b) for b in f["beats"]], "sections": list(f["sections"])}


def _window(song: str, start: float, length: float) -> dict:
    f = _features(song)
    beats = [float(b) for b in f["beats"]]
    start = max(b for b in beats if b <= start + 1e-6)
    end = start + length
    return {"duration": length, "beats": [round(b - start, 4) for b in beats if start <= b < end],
            "sections": [{**s, "start": round(max(0.0, float(s["start"]) - start), 4), "end": round(min(length, float(s["end"]) - start), 4)}
                         for s in f["sections"] if float(s["end"]) > start and float(s["start"]) < end]}


def _pack(n: int = 24, seconds: float = 16.0) -> list[dict]:
    """A film pack's rows as own_media.scan lists them: the films in turn, a family each (no files: the layout reads none)."""
    return [{"path": f"C:/pack/{k + 1:02d}_{FILMS[k % len(FILMS)]}_{k}.mp4", "seconds": seconds, "label": f"{FILMS[k % len(FILMS)]} {k}",
             "family": FILMS[k % len(FILMS)]} for k in range(n)]


def _lay(directed: dict, clips: list[dict], drop: float, **shape) -> dict:
    state = {"energy_preset": "dense", "morph_source": "clips", "own_clips": clips, **shape}
    state, _ = guardrails.apply(state, duration=directed["duration"], beats=directed["beats"])
    return clip_cut.fit(lambda cap: dense.shots_for({**state, "max_shots": cap} if cap else state, directed, None, drop=drop),
                        clips, state, beats=directed["beats"], duration=directed["duration"])


def _period(directed: dict) -> float:
    b = directed["beats"]
    return float(np.median(np.diff(b)))


def _contiguous(shots: list[dict], duration: float) -> None:
    assert shots[0]["start"] == 0.0 and shots[-1]["end"] == pytest.approx(duration, abs=1e-3)
    for a, b in zip(shots, shots[1:]):
        assert b["start"] == pytest.approx(a["end"], abs=1e-4)
    edges = [round(s["start"] * 24) for s in shots] + [round(shots[-1]["end"] * 24)]
    assert [s["frames"] for s in shots] == [b - a for a, b in zip(edges, edges[1:])]


@pytest.mark.parametrize("breathe", [True, False])
def test_a_paced_clips_cut_is_clips_and_morphs_between_them(breathe):
    song = _whole("glitch-out")
    lay = _lay(song, _pack(), 139.71, breathe=breathe, drop_mode="auto")
    shots, slots = lay["shots"], lay["slots"]
    assert lay["paced"] and len(shots) == len(slots)
    _contiguous(shots, song["duration"])
    assert slots[0]["kind"] == "clip" and slots[-1]["kind"] == "clip"
    for i, sl in enumerate(slots):
        if sl["kind"] == "morph":  # a morph only ever runs between two clips: the last frame shown into the first
            assert slots[i - 1]["kind"] == slots[i + 1]["kind"] == "clip"
            assert (sl["a"], sl["b"]) == (slots[i - 1]["clip"], slots[i + 1]["clip"])
    assert all("rest_s" not in s for s in shots)  # nothing holds: no rest is a held frame


def test_a_rest_is_film_playing_never_a_held_frame():
    song = _whole("glitch-out")
    raw, plan = dense.shots_for({"energy_preset": "dense", "breathe": True, "drop_mode": "auto"}, song, None, drop=139.71)
    assert any(s.get("rest_s") for s in raw)  # Breathe's plan rests after every scene morph
    lay = _lay(song, _pack(), 139.71, breathe=True, drop_mode="auto")
    shots, slots = lay["shots"], lay["slots"]
    rests = [i for i, s in enumerate(shots) if s.get("rest")]
    assert rests and all(slots[i]["kind"] == "clip" for i in rests)  # the rests went to clips, which play on
    longest = clip_cut.MORPH_RENDER_S[1] / pacing.MIN_PLAY
    for s, sl in zip(shots, slots):
        if sl["kind"] == "morph":
            assert not s.get("rest") and s["seconds"] <= longest + 1e-3  # never on its soft last frame, never slow motion
    # a clip shot plays its stretch 1:1 from first frame to last: no frame twice (the compositor's own mapping)
    for s, sl in zip(shots, slots):
        if sl["kind"] == "clip":
            idx = cloud_morph.shot_indices({**s, "own": True, "effects": [], "ease": ""}, int(s["frames"]))  # run() drops the ease
            assert (np.diff(idx) == 1).all()


def test_a_morph_that_rests_hands_over_to_the_clip_it_lands_on():
    period = 0.5
    shots = [{"start": 0.0, "end": 6.0, "section": "calm", "passage": 0, "effects": [], "rest": 4, "rest_s": 2.0},
             {"start": 6.0, "end": 12.0, "section": "calm", "passage": 0, "effects": [], "rest": 4, "rest_s": 2.0},
             {"start": 12.0, "end": 18.0, "section": "calm", "passage": 0, "effects": [], "rest": 4, "rest_s": 2.0},
             {"start": 18.0, "end": 24.0, "section": "calm", "passage": 0, "effects": [{"type": "punch", "t": 22.5}],
              "rest": 4, "rest_s": 2.0},
             {"start": 24.0, "end": 30.0, "section": "build", "passage": 1, "boundary": "switch", "effects": []}]
    kind = ["clip", "morph", "clip", "morph", "clip"]
    out, kd = clip_cut.hand_over(shots, kind, period, [k * period for k in range(61)])
    assert out[1]["end"] == 10.0 and out[2]["start"] == 10.0 and out[2]["rest"] == 8  # landed where its rest began
    assert out[0]["rest"] == 4 and all("rest_s" not in s for s in out)  # the clip plays on over its own rest
    # the last morph's clip opens the next passage: it starts in this passage and carries on into its own
    assert kd == ["clip", "morph", "clip", "morph", "clip", "clip"]
    assert out[3]["end"] == 22.0 and (out[4]["start"], out[4]["end"]) == (22.0, 24.0) and out[4]["passage"] == 0
    assert out[5].get("cont") and out[5]["start"] == 24.0 and out[5]["section"] == "build"
    assert out[4]["effects"] == [{"type": "punch", "t": 22.5}] and out[3]["effects"] == []
    sl = clip_cut.assign(out, kd, _pack(4))
    assert sl[5]["clip"] == sl[4]["clip"] and sl[5]["cont"] and not sl[5]["cut"]  # the same film: no cut


def test_no_morph_plays_slower_than_min_play():
    period = 60.0 / 90.0  # a slow song: two bars are 5.3 s
    shots = [{"start": 0.0, "end": 8 * period, "section": "calm", "passage": 0, "effects": []},
             {"start": 8 * period, "end": 16 * period, "section": "calm", "passage": 0, "effects": []},
             {"start": 16 * period, "end": 24 * period, "section": "calm", "passage": 0, "effects": []}]
    out, _ = clip_cut.hand_over(shots, ["clip", "morph", "clip"], period, [k * period for k in range(30)])
    longest = clip_cut.MORPH_RENDER_S[1] / pacing.MIN_PLAY
    assert out[1]["seconds"] <= longest + 1e-6 and out[1]["end"] == pytest.approx(15 * period, abs=1e-3)  # on a beat
    assert out[2]["start"] == out[1]["end"] and out[2]["rest"] == 1


@pytest.mark.parametrize("breathe", [True, False])
def test_two_beat_cuts_only_in_a_hot_runs_first_two_bars(breathe):
    song = _whole("glitch-out")
    lay = _lay(song, _pack(), 139.71, breathe=breathe, drop_mode="auto")
    shots = lay["shots"]
    period = _period(song)
    hot = clip_cut.hot_entries(shots, period)
    short = [i for i, s in enumerate(shots) if s["seconds"] < (clip_cut.CUT_BEATS - 0.5) * period]
    assert short and set(short) <= hot  # the drops' half-bar entries are the only shots under a bar
    raw, _ = dense.shots_for({"energy_preset": "dense", "breathe": breathe, "drop_mode": "auto"}, song, None, drop=139.71)
    slivers = [s for i, s in enumerate(raw) if s["seconds"] < 3.5 * period and i not in clip_cut.hot_entries(raw, period)]
    assert slivers  # the plan itself has two-beat slivers elsewhere: the layout folds them


@pytest.mark.parametrize("mode", ["auto", "max"])
def test_every_drop_run_opens_on_a_cut_to_a_fresh_film(mode):
    song = _whole("glitch-out")
    lay = _lay(song, _pack(), 139.71, breathe=True, drop_mode=mode)
    shots, slots = lay["shots"], lay["slots"]
    entries = [i for i, s in enumerate(shots) if s.get("event") == "drop"]
    runs = {s.get("drop_run") for s in shots if s.get("drop_run") is not None}
    assert entries and len(entries) == len(runs)
    shown: list[str] = []
    for i, (s, sl) in enumerate(zip(shots, slots)):
        if sl["kind"] == "clip" and not sl.get("cont"):
            if i in entries or s.get("event") == "cut":
                assert slots[i - 1]["kind"] == "clip" and sl["cut"]  # a cut on the beat, not a morph
                assert sl["family"] not in shown[-clip_cut.FRESH_BACK:]  # to a film none of the last three were
            shown.append(sl["family"])
    for i in entries:  # the drop's own hit: the punch and the stutter on the clip it opens on
        kinds_at = {fx["type"] for fx in shots[i]["effects"]}
        assert "punch" in kinds_at and (shots[i].get("heat", 1.0) < 0.5 or "stutter" in kinds_at)
    if mode == "max":
        assert all(float(s.get("heat") or 0.0) == 1.0 for s in shots if s.get("drop_run") is not None)
    assert not any(s.get("event") == "style" for s in shots)  # a style event on film is the cut


def test_drops_off_is_one_drop_and_no_cuts():
    song = _whole("glitch-out")
    lay = _lay(song, _pack(), 139.71, breathe=True, drop_mode="off")
    assert lay["paced"]
    assert not any(s.get("event") for s in lay["shots"]) and not any(sl.get("cut") for sl in lay["slots"])


def test_a_breathe_scene_holds_one_film():
    song = _whole("glitch-out")
    lay = _lay(song, _pack(), 139.71, breathe=True, drop_mode="auto")
    shots, slots = lay["shots"], lay["slots"]
    films: dict[int, list[str]] = {}
    for s, sl in zip(shots, slots):
        if sl["kind"] == "clip" and str(s.get("section")) in pacing.SCENE_ROLES and s.get("drop_run") is None:
            films.setdefault(s["passage"], []).append(sl["family"])
    held = [f for f in films.values() if len(f) > 1]
    assert held and all(len(set(f[:4])) == 1 for f in held)  # four clips a film in the pack: one film a scene


def test_a_clip_is_never_shown_twice_while_others_wait():
    song = _whole("glitch-out")
    lay = _lay(song, _pack(60), 139.71, breathe=False, drop_mode="auto")
    used = [sl["clip"] for sl in lay["slots"] if sl["kind"] == "clip" and not sl.get("cont")]
    assert len(used) <= 60 and len(used) == len(set(used))
    few = _lay(song, _pack(8), 139.71, breathe=False, drop_mode="auto")
    used = [sl for sl in few["slots"] if sl["kind"] == "clip" and not sl.get("cont")]
    assert len({sl["clip"] for sl in used[:8]}) == 8 and max(sl["turn"] for sl in used) >= 1  # all eight, then returns


def test_a_legacy_shape_is_laid_out_as_before():
    song = _window("glitch-out", 125.0, 30.0)
    lay = _lay(song, _pack(4), 14.71, breathe=False, drop_mode="off")
    assert not lay["paced"] and [sl["kind"] for sl in lay["slots"]][:3] == ["clip", "morph", "clip"]
    raw, _ = dense.shots_for({"energy_preset": "dense", "breathe": False, "drop_mode": "off"}, song, None, drop=14.71)
    assert lay["shots"] == clip_cut.merge_first([dict(s) for s in raw])


# ------------------------------------------------------------------------------------------------ the Make and the re-cut


def _clip_file(path: Path, seconds: float, value: int) -> Path:
    from xenoform.video import write_mp4

    rng = np.random.default_rng(value)
    frames = []
    n = int(seconds * 24)
    for k in range(n):  # a picture that moves every frame, so a held frame would show
        f = np.clip(rng.normal(value, 25, (54, 96, 3)), 0, 255).astype(np.uint8)
        f[:, (k * 3) % 90:(k * 3) % 90 + 6] = 255
        frames.append(f)
    write_mp4(path, frames, 24)
    return path


def _make(tmp_path, monkeypatch, *, breathe=True, drop_mode="auto", effects=()):
    song = _window("glitch-out", 125.0, 30.0)
    clips = [{"path": str(_clip_file(tmp_path / f"{k + 1:02d}_{FILMS[k % 3]}_{k}.mp4", 8.0, 50 + 30 * k)), "seconds": 8.0,
              "family": FILMS[k % 3]} for k in range(9)]
    body = {"vibe": "none", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "seed": 2727,
            "morph_source": "clips", "own_clips": clips, "breathe": breathe, "drop_mode": drop_mode, "effects": list(effects)}
    body, _ = guardrails.apply(body, duration=song["duration"], beats=song["beats"])
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: 14.71)
    seen: list[dict] = []

    def spy(clips_, shots, audio, out, **kw):
        seen.append({"clips": [Path(c) for c in clips_], "shots": copy.deepcopy(shots), **kw})
        Path(out).write_bytes(b"mp4")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"],
                "fx": True, "overlay": False, "centres": [], "fps": 24, "look": {}, "boundary_fx": {}, "effects": [],
                "tame": {"frames": 10, "flashes": 0} if kw.get("tame") else None}

    monkeypatch.setattr(beatfx, "compose", spy)
    job = tmp_path / "job"
    job.mkdir()
    rec = dense.run_simple(song, DEMO, job / "xenoform.mp4", job, {}, dict(body), lambda *a: None, engine="mock")
    return song, rec, seen, job


def test_a_clips_make_is_shaped_as_an_object_cut_is(tmp_path, monkeypatch):
    song, rec, seen, job = _make(tmp_path, monkeypatch, breathe=True)
    got = seen[-1]
    shots = got["shots"]
    assert rec["source"] == "clips" and rec["plan_name"] == "story"
    assert any(s.get("passage") is not None for s in shots)
    assert got["tame"] is not None and len(got["tame"]) == sum(int(s["frames"]) for s in shots)  # the flash tame, Breathe on
    for s in shots:  # every shot carries its passage's profile
        assert "chaos" in s and "fx_intensity" in s
        if str(s.get("section")) in pacing.SCENE_ROLES:
            assert s.get("fx_names") == [] and s["chaos"] <= pacing.BOLD_CHAOS + 1e-9  # a scene: no effect, a still camera
    for s, b in zip(shots, got["boundary_fx"]):
        if b and str(s.get("section")) in pacing.SCENE_ROLES:
            pytest.fail(f"a boundary kind in a Breathe scene: {b}")  # no wipe, no rip in a calm passage
    drops = [s for s in shots if s.get("drop_run") is not None and not s.get("own")]
    assert drops and all((s.get("timing") or {}).get("mode") in ("snap", "beat") for s in drops)  # the drop's morphs snap
    entry = next(s for s in shots if s.get("event") == "drop")
    assert entry.get("own") and entry.get("cut_in") and {"punch", "stutter"} <= {fx["type"] for fx in entry["effects"]}
    # no film freezes: every clip stretch plays 1:1, and no morph sits on its last frame
    for s, c in zip(shots, got["clips"]):
        assert not s.get("rest_s")
        if s.get("own"):
            n = int(s["frames"])
            idx = cloud_morph.shot_indices({**s, "effects": []}, n)
            assert (np.diff(idx) == 1).all()
    stored = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert stored["pacing"]["breathe"] == 1.0 and stored["pacing"]["drop_mode"] == "auto" and stored["pacing"]["line"]
    assert stored["pacing"]["passages"] and stored["recut_state"]["breathe"] == 1.0
    assert stored["recut_state"]["drop_mode"] == "auto" and stored["recut_state"]["morph_source"] == "clips"


def test_the_timeline_recut_of_a_clips_cut_obeys_the_same_rules(tmp_path, monkeypatch):
    song, rec, seen, job = _make(tmp_path, monkeypatch, breathe=True)
    made = seen[-1]
    again = dense.recut_from_cache(job, {"macros": {"chaos": 0.3, "intensity": 0.5}})
    cut = seen[-1]
    assert cut is not made and cut["transitions"] is None  # a clips cut takes no premium transitions in a re-cut either
    assert cut["tame"] is not None
    assert [s.get("fx_names") for s in cut["shots"]] == [s.get("fx_names") for s in made["shots"]]
    assert [(s.get("timing") or {}).get("mode") for s in cut["shots"]] == [(s.get("timing") or {}).get("mode") for s in made["shots"]]
    assert not any(s.get("rest_s") for s in cut["shots"])  # still no held frame
    assert again["pacing"]["breathe"] == 1.0 and again["recuts"] == 1
    plain = dense.recut_from_cache(job, {"breathe": False})  # Breathe off on the timeline: the same shots, plain profile
    assert seen[-1]["tame"] is None and plain["pacing"]["breathe"] == 0.0
    assert [s["start"] for s in seen[-1]["shots"]] == [s["start"] for s in made["shots"]]


def test_a_rest_never_fits_on_film():
    s = {"start": 0.0, "end": 10.0, "seconds": 10.0, "frames": 240, "render_s": 2, "section": "calm", "own": True, "effects": []}
    m = {**s, "own": False, "clip_morph": {"from": "a", "to": "b"}}
    o = {**s, "own": False}
    pacing.shape([s, m, o], {"chaos": 0.3, "intensity": 0.5}, breathe=True, drop_mode="auto", beats=[k * 0.5 for k in range(21)])
    assert "rest_s" not in s and "rest_s" not in m  # film plays on; a clip morph hands over instead
    assert o.get("rest_s")  # an object's morph still rests on what it arrived at


def test_the_shape_row_reaches_a_clips_cut():
    app = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    assert "function shapeRow(easy)" in app and "SHAPE_NOTES_CLIPS" in app
