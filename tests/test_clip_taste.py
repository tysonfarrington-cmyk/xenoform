"""The taste file on a clips cut (docs/TASTE.md; 1 Nov): no clip twice in a cut, the kaleido stepping aside a shot at a time
on a clip of a living thing, one effect at a time, wipes at most a quarter of the handoffs, no flash look before the first
drop, and black-and-white film a [taste] note on the cut, never a ban, because the user chose the clips."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx, boundary_fx, clip_cut, dense, guardrails, pacing, taste

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "tests" / "fixtures" / "analyses"  # frozen, so a rebuilt song moves no plan here
DEMO = ROOT / "examples" / "demo.wav"
SHIPPED = ROOT / "configs" / "taste.json"
FILMS = ("metropolis", "moon", "nosferatu", "general", "caligari", "phantom")


@pytest.fixture()
def shipped(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    return taste.load()


def _whole(song: str) -> dict:
    f = json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))
    return {"duration": float(f["duration"]), "beats": [float(b) for b in f["beats"]], "sections": list(f["sections"])}


def _pack(n: int, seconds: float = 14.0, labels: list[str] | None = None) -> list[dict]:
    return [{"path": f"C:/pack/{k + 1:02d}_{FILMS[k % len(FILMS)]}_{k}.mp4", "seconds": seconds,
             "label": (labels[k] if labels and k < len(labels) else f"{FILMS[k % len(FILMS)]} {k}"), "family": FILMS[k % len(FILMS)]}
            for k in range(n)]


def _lay(directed: dict, clips: list[dict], drop: float, **shape) -> dict:
    state = {"energy_preset": "dense", "morph_source": "clips", "own_clips": clips, **shape}
    state, _ = guardrails.apply(state, duration=directed["duration"], beats=directed["beats"])
    shots, plan = dense.shots_for(state, directed, None, drop=drop)
    return clip_cut.fit(shots, plan, clips, state, beats=directed["beats"], duration=directed["duration"])


def _roles(lay: dict) -> dict:
    out: dict = {}
    for s, sl in zip(lay["shots"], lay["slots"]):
        if sl["kind"] == "clip" and not sl.get("cont"):
            out[str(s.get("section"))] = out.get(str(s.get("section")), 0) + 1
    return out


@pytest.mark.parametrize("breathe", [True, False])
def test_no_clip_twice_plays_fewer_longer_clips_the_drops_last(shipped, breathe, monkeypatch):
    song = _whole("glitch-out")
    period = float(np.median(np.diff(song["beats"])))
    with taste.collecting() as lines:
        lay = _lay(song, _pack(24, seconds=24.0), 139.71, breathe=breathe, drop_mode="auto")
    used = [sl["clip"] for sl in lay["slots"] if sl["kind"] == "clip" and not sl.get("cont")]
    assert len(used) == len(set(used)) == 24  # every clip once
    assert any("no-clip-twice" in x["ids"] for x in lines)
    for s, sl in zip(lay["shots"], lay["slots"]):
        if sl["kind"] == "clip":
            assert s["seconds"] <= 24.0 + 1e-3  # never longer than the folder's longer clips
    monkeypatch.setattr(taste, "clips_once", lambda: False)
    plain = _lay(song, _pack(24, seconds=24.0), 139.71, breathe=breathe, drop_mode="auto")
    before, after = _roles(plain), _roles(lay)
    assert sum(before.values()) > 24 and all(after.get(r, 0) <= n for r, n in before.items())
    # the drops keep the cut each run opens on and their half-bar entries: the other passages gave first
    entries = [s for s in lay["shots"] if s.get("event") == "drop"]
    assert entries and len(entries) == len([s for s in plain["shots"] if s.get("event") == "drop"])
    hot_before, hot_after = len(clip_cut.hot_entries(plain["shots"], period)), len(clip_cut.hot_entries(lay["shots"], period))
    assert hot_after >= 0.85 * hot_before


def test_thin_takes_from_the_calm_first_keeps_the_cuts_and_minds_the_clip_length():
    period = 0.5
    rows = []
    t = 0.0

    def add(n, beats, **kw):
        nonlocal t
        for k in range(n):
            rows.append({"start": t, "end": t + beats * period, "effects": [], **kw, **({"boundary": "switch"} if k == 0 and t else {})})
            t += beats * period

    add(6, 8, section="calm", passage=0)
    add(6, 4, section="drop", passage=1, drop_run=0, heat=0.5)
    rows[6]["event"] = "drop"
    shots = clip_cut._frames(rows)
    kind = ["clip", "morph", "clip", "morph", "clip", "morph", "clip", "morph", "clip", "morph", "clip", "morph"]
    out, kd = clip_cut.thin(shots, kind, 5, period, longest_s=13.0)
    clips = [s for s, k in zip(out, kd) if k == "clip"]
    assert len(clips) == 5
    calm = [s for s, k in zip(out, kd) if k == "clip" and s["section"] == "calm"]
    assert len(calm) == 2 and all(s["seconds"] <= 13.0 for s in calm)  # the calm gave first, as far as a clip goes
    assert out[[s.get("event") for s in out].index("drop")]["start"] == 24.0  # the drop still opens on its cut
    assert kd[0] == "clip" and all(not (a == b == "morph") for a, b in zip(kd, kd[1:]))


def test_a_folder_too_small_lets_a_clip_come_back_and_says_so(shipped):
    song = _whole("glitch-out")
    with taste.collecting() as lines:
        lay = _lay(song, _pack(4), 139.71, breathe=True, drop_mode="auto")
    used = [sl for sl in lay["slots"] if sl["kind"] == "clip" and not sl.get("cont")]
    assert len(used) > 4 and max(sl["turn"] for sl in used) >= 1  # returns, each a later stretch
    assert len(lay["shots"]) >= song["duration"] / clip_cut.MEAN_SHOT_MAX_S - 1  # never one clip for half a minute
    assert any("come back with a later stretch" in x["line"] for x in lines)


def test_the_kaleido_steps_aside_on_a_clip_of_a_living_thing_one_effect_at_a_time(shipped):
    song = _whole("glitch-out")
    names = ["Nosferatu rising", "Atomic blast", "Phantom unmasked", "Futurama city"] * 6
    clips = _pack(24, labels=names)
    state = {"energy_preset": "dense", "morph_source": "clips", "own_clips": clips, "breathe": False, "drop_mode": "auto",
             "effects": ["kaleido", "dither"]}
    lay = _lay(song, clips, 139.71, breathe=False, drop_mode="auto")
    shots = copy.deepcopy(lay["shots"])
    for s, sl in zip(shots, lay["slots"]):  # as run() marks them before the cut is shaped
        if sl["kind"] == "clip":
            s.update({"own": True, "label": clips[sl["clip"]]["label"]})
        else:
            s["clip_morph"] = {"from": clips[sl["a"]]["label"], "to": clips[sl["b"]]["label"]}
    with taste.collecting() as lines:
        dense.shape_shots(shots, state, {"chaos": 0.3, "intensity": 0.5}, None, look="", beats=song["beats"],
                          stills=clip_cut.nouns(shots), drop=139.71)
    nouns = clip_cut.nouns(shots)
    for i, s in enumerate(shots):
        assert len(s.get("fx_names") or []) <= 1  # one effect at a time
        living = taste.living(nouns[i]["noun"]) or taste.living(nouns[i + 1]["noun"])
        if living:
            assert "kaleido" not in (s.get("fx_names") or [])
    assert any(taste.living(n["noun"]) for n in nouns) and taste.living("Nosferatu rising") and not taste.living("Atomic blast")
    assert any("no-kaleido-on-living" in x["ids"] for x in lines)


def test_wipes_stay_under_a_quarter_and_no_flash_look_before_the_first_drop(shipped):
    song = _whole("glitch-out")
    state = {"energy_preset": "dense", "morph_source": "clips", "breathe": False, "drop_mode": "auto",
             "macros": {"chaos": 0.95, "intensity": 0.5}, "dance_fx": "cyan-flash"}
    lay = _lay(song, _pack(24), 139.71, breathe=False, drop_mode="auto", macros={"chaos": 0.95})
    shots = copy.deepcopy(lay["shots"])
    m = taste.cap_macros(dense.macros(state), state)
    dense.shape_shots(shots, state, m, None, look="cyan-flash", beats=song["beats"], stills=clip_cut.nouns(shots), drop=139.71)
    picks = boundary_fx.pick(shots, m, song["beats"], 24, seed=2727, drop=139.71, paced=dense.paced_kinds(state, shots))
    wipes = sum(1 for p in picks if p and p.get("kind") == "wipe")
    assert wipes <= 0.25 * (len(shots) - 1)
    first = taste.first_drop(shots, 139.71)
    before = [s for s in shots if float(s["start"]) < first - 1e-6]
    assert before and all(s.get("dance_fx") not in ("cyan-flash", "negative-rush") for s in before)


def _film(path: Path, colour: bool) -> Path:
    from xenoform.video import write_mp4

    rng = np.random.default_rng(7)
    frames = []
    for k in range(48):
        g = rng.integers(20, 230, size=(36, 64)).astype(np.uint8)
        f = np.stack([g, g, g], axis=2)
        if colour:
            f[:, :32, 0] = 230
            f[:, 32:, 2] = 230
        frames.append(f)
    write_mp4(path, frames, 24)
    return path


def test_black_and_white_film_is_a_note_never_a_ban(tmp_path, monkeypatch, shipped):
    grey = _film(tmp_path / "01_old_reel.mp4", False)
    hue = _film(tmp_path / "02_new_reel.mp4", True)
    assert clip_cut.mono(grey) is True and clip_cut.mono(hue) is False
    with taste.collecting() as lines:
        assert clip_cut.film_note([{"path": str(grey)}, {"path": str(hue)}]) == 1
    assert lines and lines[0]["ids"] == ["no-film-clips"] and "1 of the 2 clips" in lines[0]["line"]
    assert "never a ban" not in lines[0]["line"] and "they stay" in lines[0]["line"]
    monkeypatch.setenv("XENO_TASTE", str(tmp_path / "none.json"))
    with taste.collecting() as lines:
        assert clip_cut.film_note([{"path": str(grey)}]) == 0
    assert not lines


def test_a_clips_make_carries_its_taste_lines(tmp_path, monkeypatch, shipped):
    song = _whole("morphing-wobble-20s")
    clips = [{"path": str(_film(tmp_path / f"0{k}_reel{k}.mp4", bool(k % 2))), "seconds": 2.0, "label": f"reel {k}"}
             for k in range(3)]
    body = {"vibe": "none", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple",
            "morph_source": "clips", "own_clips": clips, "breathe": True, "drop_mode": "auto"}
    body, _ = guardrails.apply(body, duration=song["duration"], beats=song["beats"])
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: 12.79)

    def spy(clips_, shots, audio, out, **kw):
        Path(out).write_bytes(b"mp4")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"],
                "fx": True, "overlay": False, "centres": [], "fps": 24, "look": {}, "boundary_fx": {}, "effects": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    job = tmp_path / "job"
    job.mkdir()
    dense.run_simple(song, DEMO, job / "xenoform.mp4", job, {}, dict(body), lambda *a: None, engine="mock")
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert "no-film-clips" in rec["taste"]["fired"] and rec["source"] == "clips"
    assert len(rec["clips"]) == len(rec["shots"])  # nothing was left out: a note, never a ban


def test_the_taste_file_carries_the_clip_rules(shipped):
    assert taste.clips_once() and taste.rule("no-clip-twice")["since"] == "2026-11-01"
    assert taste.rule("no-film-clips")["demote"] == "note"
    for name in ("Nosferatu rising", "Phantom unmasked", "Jekyll and Hyde", "Keaton cannon", "Lost World dinosaurs",
                 "Metropolis face", "Haxan sabbath", "a dancer"):
        assert taste.living(name), name
    for name in ("Atomic blast", "Lumiere train", "Futurama city", "torus knot", "snowman"):
        assert not taste.living(name), name
