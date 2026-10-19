"""Dense energy preset and the open-weights finishing pass. CPU only; no ComfyUI, nothing spent."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx, dense
from xenoform.cloud_morph import PARTNER_NODE, custom_shots

ROOT = Path(__file__).resolve().parents[1]
HAS_FFMPEG = shutil.which("ffmpeg") is not None
DEMO = ROOT / "examples" / "demo.wav"
FEATURES = json.loads((ROOT / "examples" / "demo_features.json").read_text(encoding="utf-8"))


def _demo1_beats() -> list[float]:
    plan = dense.demo1_plan()
    starts = [s["start"] for s in plan["shots"][1:]]
    period = 60 / 148
    first = starts[0] % period
    return [round(first + i * period, 4) for i in range(int(20 / period))]


def test_demo1_plan_ships_and_validates_with_15_morphs():
    plan = dense.demo1_plan()
    shots = custom_shots(plan, 20.0)
    assert len(shots) == 15 and len(plan["stills"]) == 16
    kinds = {fx["type"] for s in shots for fx in s["effects"]}
    assert {"punch", "stutter", "hold", "skip", "reverse"} <= kinds
    assert "usd" not in plan and "LTX-2.5" not in plan["model"]


def test_dense_plan_matches_the_demo1_shape():
    beats = _demo1_beats()
    plan = dense.dense_plan(20.0, beats, drop=12.8)
    shots = custom_shots(plan, 20.0)
    assert len(shots) <= dense.MAX_SHOTS
    starts = [s["start"] for s in shots]
    drop_i = min(range(len(starts)), key=lambda i: abs(starts[i] - plan["drop"]))
    assert abs(starts[drop_i] - 12.8) < 0.3
    before = [s["seconds"] for s in shots[:drop_i]]
    after = [s["seconds"] for s in shots[drop_i:-1]]
    assert min(before[1:]) > max(after)  # a shot a bar before the drop, half a bar after
    drop_fx = {fx["type"] for fx in shots[drop_i]["effects"]}
    assert {"punch", "stutter"} <= drop_fx
    assert {"hold", "punch", "skip"} <= {fx["type"] for fx in shots[drop_i + 1]["effects"]}
    assert shots[drop_i - 1]["ease"] == "in"


@pytest.mark.parametrize("duration", [8.0, 12.0, 30.0, 60.0, 180.0])
def test_dense_plan_fits_any_length(duration):
    beats = [i * 0.5 for i in range(int(duration / 0.5))]
    shots = custom_shots(dense.dense_plan(duration, beats, drop=duration * 0.5), duration)
    assert 2 <= len(shots) <= dense.MAX_SHOTS
    assert shots[-1]["end"] == pytest.approx(duration, abs=0.01)
    assert sum(s["frames"] for s in shots) == round(duration * 24)


def test_dense_plan_without_beats_still_plans():
    shots = custom_shots(dense.dense_plan(10.0, []), 10.0)
    assert shots and shots[-1]["end"] == pytest.approx(10.0)


def test_options_default_to_flow_draft_wide_and_open_weights():
    opt = dense.options({})
    assert opt == {"energy": "flow", "aspect": "16:9", "tier": "draft", "fx": True, "overlay": False,
                   "end_card": False, "recipe": ""}
    assert not dense.wants_finishing({})
    assert dense.wants_finishing({"energy_preset": "dense"})
    assert dense.wants_finishing({"aspect": "9:16"})
    assert dense.wants_finishing({"quality_tier": "final"})
    assert dense.options({"beat_overlay": True, "clean": True})["overlay"] is False


def test_dense_module_never_names_the_partner_node():
    for name in ("dense.py", "beatfx.py", "final_tier.py"):
        assert PARTNER_NODE not in (ROOT / "src" / "xenoform" / name).read_text(encoding="utf-8")


def test_crop_box_follows_the_subject_and_stays_inside():
    assert beatfx.crop_box(768, 432, "9:16", 0.5, 0.5) == (262, 0, 243, 432)
    x, y, w, h = beatfx.crop_box(768, 432, "9:16", 0.95, 0.5)
    assert x + w == 768 and w == 243
    x, y, w, h = beatfx.crop_box(768, 432, "1:1", 0.1, 0.5)
    assert (x, w, h) == (0, 432, 432)
    assert beatfx.crop_box(768, 432, "16:9", 0.2, 0.2) == (0, 0, 768, 432)


def test_centroid_finds_a_bright_object_on_black():
    frame = np.zeros((432, 768, 3), np.uint8)
    frame[150:250, 560:660] = 230
    cx, cy = beatfx.centroid(frame)
    assert 0.72 < cx < 0.82 and 0.38 < cy < 0.5


def test_out_sizes_per_aspect_and_tier():
    assert beatfx.out_size("9:16") == (432, 768)
    assert beatfx.out_size("1:1", "final") == (720, 720)
    assert beatfx.out_size("16:9", "final") == (1280, 720)
    assert beatfx.norm_aspect("vertical") == "9:16" and beatfx.norm_aspect("bogus") == "16:9"


def test_beat_fx_brightens_on_a_punch_and_is_neutral_when_quiet():
    frame = np.full((72, 128, 3), 80, np.uint8)
    frame[20:50, 40:90] = 200
    quiet = beatfx.beat_fx(frame, kick=0, trans=0, punch=0, loud=2 / 3, beat_index=0)
    assert abs(int(quiet.mean()) - int(frame.mean())) <= 2
    hit = beatfx.beat_fx(frame, kick=1, trans=1, punch=1, loud=1, beat_index=1)
    assert hit.mean() > frame.mean() + 10


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_pick_hook_lands_on_the_drop():
    hook = beatfx.pick_hook(DEMO, length=6.0, beats=FEATURES["beats"])
    assert hook["end"] - hook["start"] == pytest.approx(6.0)
    assert hook["start"] <= hook["drop"] <= hook["end"]
    whole = beatfx.pick_hook(DEMO, length=30.0, beats=FEATURES["beats"])
    assert whole["whole_song"] and whole["start"] == 0.0


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_dense_mock_run_writes_a_vertical_fx_cut_with_an_end_card(tmp_path):
    directed = {"duration": FEATURES["duration"], "beats": FEATURES["beats"]}
    out = tmp_path / "xenoform.mp4"
    stages = []
    info = dense.run_simple(directed, DEMO, out, tmp_path, {}, {"vibe": "black", "energy_preset": "dense", "aspect": "9:16",
                            "end_card": True, "simple_recipe": "xf1.test"}, lambda *a: stages.append(a), engine="mock")
    assert out.is_file() and info["render"] == "432x768" and info["open_weights"]
    assert info["energy"] == "dense" and len(info["shots"]) >= 6
    assert info["frames"] == round(FEATURES["duration"] * 24)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert probe == "432,768"
    assert json.loads((tmp_path / "simple" / "simple.json").read_text())["aspect"] == "9:16"
    hook = beatfx.export_hook(out, tmp_path / "hook.mp4", 2.0, 4.0)
    assert hook["seconds"] == pytest.approx(4.0, abs=0.1)
