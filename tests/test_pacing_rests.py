"""Rests (docs/MUSIC_VIDEO_PLAN.md section 3; Tys: "let it breathe", "linger with the effects like burn in"): a shot with
a rest plays its morph over its first part at no slower than 0.6x, then holds the object it arrived at for the rest with
the beat FX alive (a feedback trail in the intro and the grooves); the join after it is a morph, not a cut."""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx, cloud_morph, dense, foreshadow as F, guardrails, morph_timing as MT, pacing

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"


def _shot(seconds=4.0, rest_s=0.0, **extra):
    s = {"start": 10.0, "end": 10.0 + seconds, "seconds": seconds, "frames": int(round(seconds * 24)), "effects": [], **extra}
    if rest_s:
        s.update({"rest": 4, "rest_s": rest_s})
    return s


def test_a_rest_plays_the_morph_then_holds_what_it_arrived_at():
    plain = cloud_morph.shot_indices(_shot(4.0), 73)
    rested = cloud_morph.shot_indices(_shot(4.0, rest_s=1.5), 73)
    assert len(rested) == len(plain) == 96 and plain[0] == rested[0] == 0 and plain[-1] == rested[-1] == 72
    hold = int(round(1.5 * 24))
    assert (rested[-hold:] == 72).all() and rested[-hold - 1] == 72  # the morph is done when the rest begins
    assert rested[len(rested) - hold - 2] < 72  # and was still changing just before
    moving = np.diff(rested[: len(rested) - hold])
    assert (moving >= 0).all() and moving.mean() > np.diff(plain).mean()  # the morph plays faster, over its part only
    exact = cloud_morph.shot_indices(_shot(4.0, rest_s=1.5), 73, exact=True)
    assert exact[-1] == 72.0 and np.allclose(exact[-hold:], 72.0)


def test_timing_lands_the_change_inside_the_morph_part():
    s = _shot(4.0, rest_s=2.0)
    MT.plan([s], "snap", [10.0 + 0.5 * i for i in range(9)], None)
    hits = s["timing"]["hits"]
    assert hits and all(10.0 < h < 12.0 for h in hits)  # before the rest at 12.0
    prog = np.linspace(0.0, 1.0, 73)
    idx = cloud_morph.shot_indices(s, 73, progress=prog)
    assert (idx[-48:] == 72).all() and idx[0] == 0


def test_a_long_breathe_shot_is_a_morph_and_a_rest_never_slow_motion():
    period = 60.0 / 90.0
    s = _shot(16 * period, render_s=4, section="calm")
    assert pacing._fit_rest(s, period)
    assert s["rest_s"] == pytest.approx(16 * period - 4 / pacing.MIN_PLAY, abs=1e-3) and s["rest"] <= pacing.REST_MAX
    long = _shot(40 * period, render_s=4, section="calm")
    pacing._fit_rest(long, period)
    assert long["rest_s"] == pytest.approx(pacing.REST_MAX * period, abs=1e-3)  # a rest is never longer than 8 beats
    fine = _shot(6 * period, render_s=4, section="calm")
    assert not pacing._fit_rest(fine, period) and "rest_s" not in fine  # 0.6x and faster: no rest


def test_breathe_rests_in_the_plan():
    f = json.loads((SONGS / "glitch-out.features.json").read_text(encoding="utf-8"))
    song = {"duration": float(f["duration"]), "beats": list(f["beats"]), "sections": list(f["sections"])}
    body, _ = guardrails.apply({"energy_preset": "dense", "breathe": True, "macros": {"speed": 0.15}},
                               duration=song["duration"], beats=song["beats"])
    shots, plan = dense.shots_for(body, song, None, drop=139.71)
    for s in shots:
        s["render_s"] = 4  # Glitch Out's chain clip (a bar x 1.15, snapped up)
    work = copy.deepcopy(shots)
    pacing.shape(work, {"intensity": 0.5, "chaos": 0.3}, breathe=True, drop_mode="auto", beats=song["beats"])
    period = 60.0 / 90.0
    for s in work:
        if s.get("rest_s"):
            assert s["section"] not in ("drop", "drop_late") and s["rest"] <= pacing.REST_MAX
            assert s["rest_s"] <= pacing.REST_MAX * period + 1e-6
        play = float(s["seconds"]) - float(s.get("rest_s") or 0.0)
        if s["section"] not in ("drop", "drop_late") and float(s.get("rest") or 0) < pacing.REST_MAX:
            assert 4.0 / play >= pacing.MIN_PLAY - 1e-3  # never slower than 0.6x
    assert any(s.get("rest") for s in work)


def test_the_join_after_a_rest_is_a_morph():
    frame = np.zeros((8, 8, 3), np.uint8)
    reads = []

    def read_edge(clip, which):
        reads.append((clip, which))
        return frame

    shots = [_shot(4.0, rest_s=1.0, section="calm"), _shot(4.0, section="calm")]
    shots[1]["start"], shots[1]["end"] = 14.0, 18.0
    entries = F.plan(shots, ["a", "b"], [10 + i * 0.5 for i in range(16)], 24, "trace", {"lead_beats": 2.0}, read_edge=read_edge)
    assert entries[0]["which"] == "last"  # the next morph's landing, as across any morph handoff (a Hold's join is a cut)


def _clip(path: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s=64x112:r=24:d={seconds}", "-pix_fmt", "yuv420p",
                    str(path)], check=True)
    return path


def test_a_rest_in_a_groove_burns_in_with_a_trail(tmp_path):
    clip = _clip(tmp_path / "c.mp4", 2.0)
    common = dict(aspect="9:16", w=64, h=112, fx=False, env=None, beats=[i * 0.5 for i in range(16)], punch=np.zeros(200),
                  zoom_scale=0.5, glow_gain=0.64, fps=24, look_kwargs=dict(dance_fx="off", stem_orbit=False, shots=1))
    calm = _shot(3.0, rest_s=1.5, section="calm")
    calm["start"], calm["end"] = 0.0, 3.0
    drop = dict(calm, section="drop")
    a = beatfx._shot_frames(clip, calm, 0, 0, 200, **common)["frames"]
    b = beatfx._shot_frames(clip, drop, 0, 0, 200, **common)["frames"]
    assert a.shape == b.shape == (72, 112, 64, 3)
    rest_from = 72 - 36
    assert np.array_equal(a[: rest_from - beatfx.REST_TRAIL_LEAD], b[: rest_from - beatfx.REST_TRAIL_LEAD])  # the morph alike
    assert not np.array_equal(a[rest_from:], b[rest_from:])  # the trail over the calm rest only
    assert np.array_equal(b[rest_from], b[-1])  # the rest holds the arrived frame (no effects on it here)
