"""The foreshadow layer (25 Oct 2026): the next object arrives before its shot. The treatments change a frame only
with an amount, the ramp climbs over the lead, the plan targets the next morph's landing (or a hard cut's first
frame) and echoes only across hard cuts, Auto picks by the vibe's tone, and a composed cut with the layer differs
from one without while keeping every frame."""
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import foreshadow as F


def _frame(h=72, w=128, back=(10, 10, 14), disc=(200, 180, 160), cx=0.5, cy=0.5, r=0.25):
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = back
    yy, xx = np.mgrid[0:h, 0:w]
    m = ((xx - cx * w) ** 2 + (yy - cy * h) ** 2) < (r * h) ** 2
    a[m] = disc
    return a


def test_choice_and_mode_follow_the_vibe():
    assert F.choice({}) == "auto" and F.choice({"foreshadow": "SLICES"}) == "slices" and F.choice({"foreshadow": "weird"}) == "auto"
    assert F.mode_for("off") == "" and F.mode_for("negative") == "negative"
    assert F.mode_for("auto", "chrome-mercury") == "trace"  # dark: the glow reads on black
    assert F.mode_for("auto", "risograph") == "slices"      # bright: a trace is lost on paper
    assert F.mode_for("auto", None) == "trace"


def test_params_follow_the_knobs():
    low = F.params({"intensity": 0.0, "speed": 0.0, "chaos": 0.0, "glow": 0.0})
    high = F.params({"intensity": 1.0, "speed": 1.0, "chaos": 1.0, "glow": 1.0})
    assert low["cap"] == 0.25 and high["cap"] == 0.8
    assert low["lead_beats"] == 2.0 and high["lead_beats"] == 6.0
    assert low["slices"] == 4 and high["slices"] == 16 and high["jitter"] == 1.0
    assert F.params(None)["cap"] == pytest.approx(0.525)


def test_ramps_and_amount():
    assert F.ramp(0, 48, 12) == 0.0 and F.ramp(36, 48, 12) == 0.0 and F.ramp(47, 48, 12) > 0.9 and F.ramp(42, 48, 12) == pytest.approx(0.5)
    assert F.echo_ramp(0, 12) == 1.0 and F.echo_ramp(11, 12) < 0.02 and F.echo_ramp(12, 12) == 0.0
    assert F.amount(1.0, 1.0, 0.8) == pytest.approx(0.8) and F.amount(1.0, 0.0, 0.8) == pytest.approx(0.4) and F.amount(0.0, 1.0, 0.8) == 0.0


@pytest.mark.parametrize("mode", F.MODES)
def test_each_treatment_changes_the_frame_only_with_an_amount(mode):
    frame = _frame()
    target = _frame(disc=(90, 200, 240), cx=0.7, cy=0.4, r=0.2)
    same = F.treat(frame, target, mode, 0.0)
    assert same is frame
    out = F.treat(frame, target, mode, 0.7, tint=(255, 120, 200), p=F.params({"chaos": 0.5}), si=1, k=3, seed=7)
    assert out.shape == frame.shape and out.dtype == np.uint8
    diff = np.abs(out.astype(int) - frame.astype(int)).mean()
    assert diff > 1.0, mode
    # the layer lands where the target's subject is, not everywhere: the corner far from both discs stays near black
    assert out[2, 2].max() < 60
    weak = F.treat(frame, target, mode, 0.15, tint=(255, 120, 200), p=F.params({"chaos": 0.5}), si=1, k=3, seed=7)
    assert np.abs(weak.astype(int) - frame.astype(int)).mean() < diff


def test_slices_accumulate_toward_the_cut_and_never_flicker():
    frame = _frame()
    target = _frame(disc=(90, 200, 240), cx=0.3, cy=0.6, r=0.2)
    p = F.params({"chaos": 1.0})
    a = F.treat(frame, target, "slices", 0.2, p=p, si=0, k=1, seed=3)
    b = F.treat(frame, target, "slices", 0.6, p=p, si=0, k=2, seed=3)
    changed_a = (np.abs(a.astype(int) - frame.astype(int)).sum(axis=2) > 0).mean(axis=1) > 0
    changed_b = (np.abs(b.astype(int) - frame.astype(int)).sum(axis=2) > 0).mean(axis=1) > 0
    assert changed_a.sum() < changed_b.sum()  # more strips as the amount climbs
    assert not (changed_a & ~changed_b).any()  # a strip that is in never drops out between frames


def test_plan_targets_the_next_landing_and_echoes_only_across_hard_cuts():
    shots = [{"frames": 48}, {"frames": 48}, {"frames": 60, "performer": True}, {"frames": 48}, {"frames": 24}]
    clips = ["c0.mp4", "c1.mp4", "polly.mp4", "c3.mp4", "c4.mp4"]
    reads = []

    def fake_read(clip, which):
        reads.append((clip.name, which))
        return _frame(disc=(len(reads) * 20 % 255, 100, 100))

    beats = [i * 0.5 for i in range(40)]  # 120 bpm
    out = F.plan(shots, clips, beats, 24, "trace", F.params({"speed": 0.5}), read_edge=fake_read)
    assert len(out) == 5
    assert out[0]["which"] == "last" and out[0]["lead"] == 24 and out[0]["prev"] is None  # a bar at 120 bpm, no echo
    assert out[1]["which"] == "first" and out[1]["prev"] is None  # into Polly: her first frame, no echo yet
    assert out[2]["which"] == "last" and out[2]["prev"] is not None and out[2]["echo"] == 12  # over Polly: the object that left echoes a beat
    assert out[3]["prev"] is not None and out[3]["which"] == "last"  # out of Polly: she echoes over the morph
    assert out[4] is None  # the last shot has nothing to foreshadow and no hard cut behind it
    assert ("c1.mp4", "last") in reads and ("polly.mp4", "first") in reads and ("polly.mp4", "last") in reads
    assert sum(1 for r in reads if r == ("c1.mp4", "last")) == 1  # each edge frame read once
    assert F.plan(shots, clips, beats, 24, "", F.params(None)) == [None] * 5
    assert F.info(out, "trace", F.params(None), 24)["shots"] == 4 and F.info(out, "trace", F.params(None), 24)["echoes"] == 2


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")
def test_a_composed_cut_carries_the_layer(tmp_path):
    from xenoform import beatfx

    def clip(path: Path, seconds: float, colour: str) -> Path:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:size=64x112:rate=24:duration={seconds}",
                        "-vf", "drawbox=x=20:y=30:w=24:h=40:color=white:t=fill", "-pix_fmt", "yuv420p", str(path)], check=True)
        return path

    audio = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100:duration=4", str(audio)], check=True)
    clips = [clip(tmp_path / f"c{i}.mp4", 2.0, c) for i, c in enumerate(("navy", "darkred"))]
    shots = [{"index": 0, "start": 0.0, "end": 2.0, "seconds": 2.0, "frames": 48, "speed": 1.0, "ease": "", "effects": []},
             {"index": 1, "start": 2.0, "end": 4.0, "seconds": 2.0, "frames": 48, "speed": 1.0, "ease": "", "effects": []}]
    beats = [i * 0.5 for i in range(8)]
    kw = dict(aspect="9:16", quality="draft", fx=False, overlay=False, beats=beats, size=(64, 112), fps=24, dance_fx="off", stem_orbit=False,
              macros={"intensity": 1.0, "speed": 0.5, "chaos": 0.5, "glow": 0.5}, seed=1)
    first, last = F.edge_frame(clips[0], "first"), F.edge_frame(clips[0], "last")
    whole = beatfx.read_frames(clips[0])
    assert first.shape == last.shape == whole[0].shape and first.flags.owndata and last.flags.owndata  # one frame, owned
    assert np.abs(first.astype(int) - whole[0].astype(int)).mean() < 2 and np.abs(last.astype(int) - whole[-1].astype(int)).mean() < 2
    plain = beatfx.compose(clips, shots, audio, tmp_path / "plain.mp4", **kw)
    traced = beatfx.compose(clips, shots, audio, tmp_path / "traced.mp4", foreshadow="trace", **kw)
    assert plain["frames"] == traced["frames"] == 96
    assert plain["foreshadow"]["mode"] == "off" and traced["foreshadow"]["mode"] == "trace" and traced["foreshadow"]["shots"] == 1
    a = beatfx.read_frames(tmp_path / "plain.mp4")
    b = beatfx.read_frames(tmp_path / "traced.mp4")
    early = np.abs(a[5].astype(int) - b[5].astype(int)).mean()
    late = np.abs(a[46].astype(int) - b[46].astype(int)).mean()
    assert early < 1.5 and late > early  # nothing at the shot's head, the next object traced in at its tail
