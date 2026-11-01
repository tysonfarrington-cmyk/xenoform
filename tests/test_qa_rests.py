"""Rests inside a window (the follow-ups of 1 Nov): the QA lag fix skips every rest the shot plan holds, not only the one
a window ends on, so a rest in the middle of a window keeps its held frames (docs/SONG.md). Before, a window's mid rest
counted as duplicates, the lag fix ran, and minterpolate smoothed the held object into the next shot."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import post_qa as q

FF = shutil.which("ffmpeg")
needs_ff = pytest.mark.skipif(not FF, reason="ffmpeg missing")

# the plan of a 5.5 s window: a morph of 2 s then its rest held 1.5 s, then a 2 s shot
SHOTS = [{"start": 0.0, "end": 3.5, "rest": 3, "rest_s": 1.5}, {"start": 3.5, "end": 5.5}]


def _mid_rest(path: Path, judder_after: bool) -> Path:
    """2 s of picture, its last frame held 1.5 s (the planned rest, in the middle), then 2 s more picture: smooth, or
    with judder (8 fps shown at 24) that a lag fix must still smooth. 5.5 s of sound under it."""
    after = "testsrc2=size=320x180:rate=24:duration=2" + (",fps=8,fps=24" if judder_after else "")
    graph = (f"testsrc2=size=320x180:rate=24:duration=2,hue=h=90,tpad=stop_mode=clone:stop_duration=1.5[a];{after}[b];"
             "[a][b]concat=n=2:v=1:a=0[v]")
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=330:duration=5.5", "-filter_complex", graph,
                    "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)
    return path


def _grey(path: Path, frame: int) -> np.ndarray:
    raw = subprocess.run([FF, "-v", "error", "-i", str(path), "-vf", f"select=eq(n\\,{frame}),scale=64:36", "-frames:v", "1",
                          "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).astype(float)


def test_the_shot_plan_says_where_every_rest_is_held():
    assert q.rests_of(SHOTS, 24) == [(48, 84)]
    two = SHOTS + [{"start": 5.5, "end": 9.5, "rest": 4, "rest_s": 2.0}]
    assert q.rests_of(two, 24) == [(48, 84), (180, 228)]
    assert q.rests_of([{"start": 0, "end": 2, "rest": 0, "rest_s": 1.0}, {"end": 4, "rest": 2}], 24) == []
    assert q.rests_of(None) == [] and q._merge_ranges([(0, 10), (5, 20), (30, 31)]) == [(0, 20), (30, 31)]


@needs_ff
def test_a_rest_in_the_middle_is_not_lag(tmp_path):
    """A window whose only held picture is its planned mid rest: the old check read it as judder and fixed it; read
    against the plan it is no lag, so no fix runs and the rest stays held."""
    v = _mid_rest(tmp_path / "mid.mp4", judder_after=False)
    old = q.lag_report(v, 24)
    assert old["lag"] and old["dup_ratio"] > 0.15 and old["held_end_frames"] == 0  # a rest mid-window, not at its end
    rests = q.rests_of(SHOTS, 24)
    rep = q.lag_report(v, 24, rests=rests)
    assert not rep["lag"] and rep["dup_ratio"] < 0.05 and rep["rest_frames"] == 36
    before = _grey(v, 80)
    got = q.run(v, fps=24, beats=None, fix=True, shots=SHOTS)
    assert not got["lag"]["lag"] and "lag_fix" not in got
    assert np.abs(_grey(v, 80) - before).mean() == 0  # untouched


@needs_ff
def test_the_lag_fix_keeps_a_mid_window_rest_held_and_smooths_the_judder_around_it(tmp_path):
    v = _mid_rest(tmp_path / "judder.mp4", judder_after=True)
    plain = _mid_rest(tmp_path / "plain.mp4", judder_after=True)
    held = _grey(v, 60)  # the rest's held picture
    rests = q.rests_of(SHOTS, 24)
    rep = q.lag_report(v, 24, rests=rests)
    assert rep["lag"] and rep["dup_ratio"] > 0.3  # the judder after the rest is real lag: the fix still runs
    fix = q.fix_lag(v, rep, 24, rests=rests)
    assert fix["fixed"] and fix["method"].startswith("interpolate") and fix["rests_kept"] == 1
    assert fix["frames"] == [132, 132] and q.probe(v)["frames"] == 132
    for f in (49, 60, 70, 83):  # the rest, every frame of it, is the held picture still
        assert np.abs(_grey(v, f) - held).mean() < 2.0, f
    assert np.abs(_grey(v, 84) - held).mean() > 5.0  # the next shot comes in on its beat, not smeared into the hold
    after = [_grey(v, f) for f in range(96, 108)]
    moving = sum(np.abs(a - b).mean() > 0.5 for a, b in zip(after, after[1:]))
    assert moving >= 9  # the judder around it is smoothed: the 8 fps run now moves nearly every frame
    old = q.fix_lag(plain, q.lag_report(plain, 24), 24)  # the old fix, with no plan: the rest is smoothed away
    assert old["fixed"] and np.abs(_grey(plain, 80) - held).mean() > 2.0


def test_the_desk_and_the_song_pass_the_plan_to_the_qa():
    src = (Path(__file__).resolve().parents[1] / "src" / "xenoform")
    ui = (src / "ui.py").read_text(encoding="utf-8")
    assert "post_qa.run(out, fps=24.0, beats=beats, vj=bool(body.get(\"vj\")), fix=fix, report=on_progress,\n" in ui
    assert "shots=planned)" in ui and '(work / "simple" / "simple.json")' in ui
    song = (src / "song_assemble.py").read_text(encoding="utf-8")
    assert "post_qa.run(out, fps=float(FPS), beats=song_beats, fix=False, shots=shots)" in song
