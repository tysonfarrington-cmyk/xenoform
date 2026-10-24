"""Final quality tier: LTX-2.3 fp8 + 4x-ClearReality graph, honest ETA, and the fallbacks. No GPU."""

from __future__ import annotations

from pathlib import Path

import pytest

from xenoform import final_tier as ft
from xenoform.cloud_morph import PARTNER_NODE


def test_graph_is_open_weights_two_stage_with_upscale():
    g = ft.graph("p", length=49, seed=7)
    kinds = {node["class_type"] for node in g.values()}
    assert PARTNER_NODE not in kinds and not any("Api" in k for k in kinds)
    assert g["1"]["inputs"]["ckpt_name"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    assert g["40"]["inputs"]["model_name"] == "RealESRGAN_x4plus.pth"  # BSD-3 default; ClearReality is opt-in
    assert g["7"]["inputs"]["width"] == 384 and g["7"]["inputs"]["height"] == 224
    assert (g["42"]["inputs"]["width"], g["42"]["inputs"]["height"]) == (1280, 720)
    frames = [g[k]["inputs"]["frame_idx"] for k in ("110", "111", "120", "121")]
    assert frames == [0, -1, 0, -1]
    assert g["14"]["inputs"]["noise_seed"] == 7


def test_graph_without_upscale_scales_the_decode_directly():
    g = ft.graph("p", length=25, seed=1, upscale=False)
    assert "40" not in g and "41" not in g
    assert g["42"]["inputs"]["image"] == ["25", 0]


def test_lengths_are_8k_plus_1_and_capped():
    assert ft.gen_length(2) == 49 and ft.gen_length(0.5) == 25 and ft.gen_length(10) == 121


def test_eta_matches_the_measured_demo1_final_test():
    # 2 s shot warm with upscale: 93 s measured; 3 s shot cold: 238 s measured
    assert ft.eta_seconds([{"render_s": 2}], warm=True) == 93
    assert abs(ft.eta_seconds([{"render_s": 3}]) - 238) <= 30  # the 19 Oct 3 s shot was cold and on a shared card
    # 24 Oct: eleven 4-5 s morphs at native 9:16 took 3380 s with the compose; the estimate lands within 5 %
    run = [{"seconds": 2.67, "render_s": r} for r in (4, 4, 5, 2, 5, 4, 4, 4, 4, 4, 4)]
    assert 3100 <= ft.eta_seconds(run) <= 3400
    assert ft.eta_seconds([{"seconds": 2.67}]) == ft.eta_seconds([{"render_s": 3}])  # a planned slot counts at its snapped render length
    assert ft.eta_seconds([{"render_s": 2}] * 15, upscale=False, warm=True) == 15 * 70
    assert ft.ETA["measured"] is True


def test_present_reports_each_file(tmp_path):
    assert ft.present(tmp_path)["ready"] is False
    for folder, name in ft.FILES:
        (tmp_path / folder).mkdir(exist_ok=True)
        (tmp_path / folder / name).write_bytes(b"x")
    assert ft.present(tmp_path) == {"files": {n: True for _, n in ft.FILES}, "ready": True, "upscale": True}


class _Out:
    type = "video"

    def __init__(self, dest_log):
        self.dest_log = dest_log

    def to_file(self, dest):
        Path(dest).write_bytes(b"mp4")
        self.dest_log.append(dest)


class _Result:
    def __init__(self, log):
        self.outputs = [_Out(log)]

    def get_outputs(self, node):
        return self.outputs


class _Job:
    id = "j"

    def __init__(self, fail):
        self.fail = fail
        self.status = "succeeded"

    def result(self):
        if self.fail:
            raise RuntimeError(self.fail)
        return _Result([])


class _WF:
    def __init__(self, g):
        self.g = g

    def set_input(self, *a):
        pass


class _Client:
    def __init__(self, failures):
        self.failures = failures  # list of (has_upscale -> error or None) per submit
        self.submitted = []
        self.assets = type("A", (), {"from_file": staticmethod(lambda p: p)})()
        self.workflows = type("W", (), {"from_json": staticmethod(lambda g: _WF(g))})()
        self.jobs = None

    def submit(self, wf):
        upscale = "40" in wf.g
        self.submitted.append(upscale)
        return _Job(self.failures(len(self.submitted) - 1, upscale))


@pytest.fixture
def stills(tmp_path):
    out = []
    for i in range(4):
        p = tmp_path / f"s{i}.png"
        p.write_bytes(b"png")
        out.append({"path": str(p), "noun": f"n{i}", "file": p.name})
    return out


def _no_wait(monkeypatch):
    from xenoform import morph_pass as mp

    monkeypatch.setattr(mp, "wait_or_cancel", lambda job, jobs, cancel, poll_s=0.4: None)


def test_oom_falls_back_to_no_upscale_then_to_draft(tmp_path, stills, monkeypatch):
    _no_wait(monkeypatch)
    shots = [{"render_s": 2, "seconds": 1.0}] * 3

    def failures(i, upscale):
        if i == 0:  # shot 1: OOM with the upscale, fine without
            return "CUDA out of memory" if upscale else None
        if i in (2, 3):  # shot 2: fails both ways
            return "allocation failed"
        return None

    client = _Client(failures)
    drafted = []

    def draft(indices):
        drafted.extend(indices)
        return {i: tmp_path / f"d{i}.mp4" for i in indices}

    clips, notes = ft.final_clips(shots, stills, tmp_path, {}, 5, "black", client=client, draft=draft)
    assert len(clips) == 3 and drafted == [1]
    assert [n["fallback"] for n in notes] == ["ltx23-no-upscale", "ltx095-draft"]
    assert all(n["oom"] for n in notes)
    assert clips[1] == tmp_path / "d1.mp4"


def test_final_without_a_draft_fallback_raises(tmp_path, stills, monkeypatch):
    _no_wait(monkeypatch)
    client = _Client(lambda i, up: "boom")
    with pytest.raises(RuntimeError):
        ft.final_clips([{"render_s": 2, "seconds": 1}], stills, tmp_path, {}, 1, "black", client=client)


def test_upscale_can_be_switched_off(tmp_path, stills, monkeypatch):
    _no_wait(monkeypatch)
    monkeypatch.setenv("XENO_FINAL_UPSCALE", "0")
    client = _Client(lambda i, up: None)
    ft.final_clips([{"render_s": 2, "seconds": 1}], stills, tmp_path, {}, 1, "black", client=client)
    assert client.submitted == [False]


def test_present_defaults_to_the_comfy_models_root(tmp_path, monkeypatch):
    from xenoform import models_setup

    monkeypatch.setattr(models_setup, "models_root", lambda: tmp_path)
    (tmp_path / "upscale_models").mkdir()
    (tmp_path / "upscale_models" / ft.UPSCALER).write_bytes(b"x")
    assert ft.present()["upscale"] is True
