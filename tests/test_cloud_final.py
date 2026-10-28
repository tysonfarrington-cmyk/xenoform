"""Cloud Final (Tys, 29 Oct: "we have access to ltx 2.5 though ?? and a comfyui sub thing ?? surely there can at least be an
option for that"): the open-weights LTX-2.5 morph on Comfy Cloud, three at a time, scaled to full size here. Nothing here
talks to Comfy Cloud: a fake backend stands in, and no key is ever needed or read out."""

import json
import threading
from pathlib import Path

import pytest

from xenoform import cloud_backend, cloud_final, dense

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")


def test_the_graph_is_the_open_weights_ltx25_morph_at_the_shots_size():
    g = cloud_final.graph("a morph", length=73, seed=31, width=576, height=1024)
    assert g["1"]["inputs"]["unet_name"].startswith("ltx-2.5-22b-distilled")
    assert g["9"]["inputs"] == {**g["9"]["inputs"], "width": 576, "height": 1024, "length": 73}
    assert g["25"]["inputs"]["frames_number"] == 73 and g["13"]["inputs"]["noise_seed"] == 31 and g["3"]["inputs"]["text"] == "a morph"
    assert cloud_backend.guard(g) == []  # no partner or API node: it stays open weights on Comfy's GPUs
    with pytest.raises(ValueError):
        cloud_final.graph("x", length=73, seed=1, width=720, height=1280)  # LTX wants multiples of 32


def test_the_default_is_ltx25_with_loose_guides_and_ltx23_stays_available():
    # 29 Oct, nautilus -> owl: LTX-2.5 with its graph's guides (1.0, compression 18) cut near the end; with the end guide at
    # 0.6, compression 30 and a prompt asking for the change across the clip it morphed, half and half mid-clip
    assert cloud_final.model() == "ltx25" and cloud_final.label() == "LTX-2.5"
    assert cloud_final.LOOSE == {"img_compression": 30, "end_strength": 0.6} and "never a cut" in cloud_final.LEAD
    g = cloud_final.graph_for("ltx23", "a morph", length=73, seed=5, width=576, height=1024)
    assert cloud_backend.guard(g) == []  # no upscale model and no partner node goes to Cloud
    assert g["100"]["class_type"] == "LoadImage" and g["101"]["class_type"] == "LoadImage"
    assert g["7"]["inputs"]["width"] == 288 and g["7"]["inputs"]["height"] == 512  # stage one at half size
    assert cloud_final.INPUT_NODES["ltx23"] == ("100", "101") and cloud_final.INPUT_NODES["ltx25"] == ("6", "7")


def test_it_is_ready_only_with_the_key_in_the_environment_and_never_shows_it(monkeypatch):
    monkeypatch.delenv(cloud_backend.KEY_ENV, raising=False)
    off = cloud_final.ready()
    assert off["ready"] is False and "COMFY_ORG_API_KEY" in off["why"] and "restart the desk" in off["why"]
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    on = cloud_final.ready()
    assert on["ready"] is True and "sk-test" not in json.dumps(on)


class FakeCloud:
    """Stands in for cloud_backend.CloudBackend: writes a small file per job, fails the shots asked to fail."""

    max_parallel = 3

    def __init__(self, fail=()):
        self.fail = set(fail)
        self.graphs = []
        self.prepared = 0
        self.live = 0
        self.peak = 0
        self.lock = threading.Lock()

    def prepare(self, graph, open_weights=True):
        self.prepared += 1
        assert cloud_backend.guard(graph) == []
        return graph

    def run(self, graph, out_dir, inputs=None, open_weights=True):
        with self.lock:
            self.live += 1
            self.graphs.append(graph)
            self.peak = max(self.peak, self.live)
        try:
            save = next(n for n in graph.values() if n["class_type"] == "SaveVideo")
            i = int(save["inputs"]["filename_prefix"][-2:])
            assert len(inputs) == 2 and all(graph[nid]["class_type"] == "LoadImage" for nid in inputs)
            if i in self.fail:
                raise cloud_backend.CloudJobFailed("job ended error")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            out = Path(out_dir) / f"morph25_{i:02d}.mp4"
            out.write_bytes(b"mp4")
            return [out]
        finally:
            with self.lock:
                self.live -= 1


def test_every_shot_goes_to_cloud_three_at_a_time_and_a_failed_one_falls_back_to_its_draft(tmp_path, monkeypatch):
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    shots = [{"seconds": 2.0} for _ in range(5)]
    stills = [{"path": str(tmp_path / f"s{i}.png"), "kind": "object"} for i in range(6)]
    fake = FakeCloud(fail={2})
    drafted = []
    monkeypatch.setattr(cloud_final, "MODEL", "ltx23")  # this run: the LTX-2.3 graph, named below for LTX-2.5

    def draft(indices):
        drafted.extend(indices)
        out = {}
        for i in indices:
            out[i] = tmp_path / f"draft{i}.mp4"
            out[i].write_bytes(b"d")
        return out

    seen = []
    clips, notes = cloud_final.cloud_clips(shots, stills, tmp_path, {}, 2727, "none", vertical=False, backend=fake,
                                           draft=draft, report=lambda stage, frac, detail: seen.append(detail), name="ltx23")
    cloud25 = FakeCloud()
    clips25, _ = cloud_final.cloud_clips(shots[:1], stills[:2], tmp_path / "25", {}, 2727, "none", vertical=False,
                                         backend=cloud25, name="ltx25")
    assert clips25[0].name == "cloud00.mp4"
    g25 = cloud25.graphs[0]  # the loose guides and the lead sentence, every time LTX-2.5 is sent
    assert g25["22"]["inputs"]["strength"] == 0.6 and g25["8"]["inputs"]["img_compression"] == 30
    assert g25["3"]["inputs"]["text"].startswith(cloud_final.LEAD)
    g23 = fake.graphs[0]  # the LTX-2.3 graph keeps its own tune (the vibe's autotune, else the graph's defaults)
    assert g23["102"]["inputs"]["img_compression"] == 18 and not g23["4"]["inputs"]["text"].startswith(cloud_final.LEAD)
    assert len(clips) == 5 and clips[2].name == "draft2.mp4" and clips[0].name == "cloud00.mp4" and drafted == [2]
    assert notes == [{"shot": 2, "fallback": "ltx095-draft", "why": "job ended error"}]
    assert fake.prepared == 5 and fake.peak <= 3 and "Comfy Cloud" in seen[-1]


def test_it_refuses_without_the_key_or_past_its_cap_before_sending_anything(tmp_path, monkeypatch):
    monkeypatch.delenv(cloud_backend.KEY_ENV, raising=False)
    fake = FakeCloud()
    with pytest.raises(cloud_backend.CloudRefused):
        cloud_final.cloud_clips([{"seconds": 2}], [{"path": "a"}, {"path": "b"}], tmp_path, {}, 1, "none", vertical=False, backend=fake)
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    many = [{"seconds": 2}] * (cloud_final.MAX_MORPHS + 1)
    with pytest.raises(cloud_backend.CloudRefused, match="at most"):
        cloud_final.cloud_clips(many, [{"path": "a"}] * (len(many) + 1), tmp_path, {}, 1, "none", vertical=False, backend=fake)
    assert fake.prepared == 0


def test_a_make_runs_it_only_with_the_tick(tmp_path):
    opt = dense.options({"quality_tier": "cloud"})
    assert opt["cloud"] is True and opt["fast"] is False and dense.MORPH_CAP["cloud"] == cloud_final.MAX_MORPHS
    assert dense.estimate(12, "cloud", "9:16")["seconds"] > 0
    with pytest.raises(RuntimeError, match="spends Comfy Cloud credits"):
        dense.run_simple({"duration": 12.0}, tmp_path / "song.wav", tmp_path / "out.mp4", tmp_path, {}, {"quality_tier": "cloud"},
                         lambda *a: None)


def test_the_desk_offers_it_under_model_with_a_tick_that_is_asked_for_afresh():
    assert '["cloud", "Cloud Final"]]' in APP and "cloudFinalRow(easy)" in APP
    assert 'cloud_final_ok: !!(state.easy && state.easy.tier === "cloud" && state.easy.cloudFinalOk)' in APP
    tier = APP.split('} else if (act === "easy-tier") {', 1)[1].split("} else if", 1)[0]
    assert '"cloud"' in tier and "state.easy.cloudFinalOk = false" in tier
    make = APP.split("async function easyMake() {", 1)[1].split("\n}\n", 1)[0]
    assert '=== "cloud" && !state.easy.cloudFinalOk' in make


def test_the_options_say_whether_cloud_final_can_run_without_the_key(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    res = TestClient(create_app()).get("/api/simple/options", params={"duration": 30, "tier": "cloud", "aspect": "9:16"})
    info = res.json()["cloud_final"]
    assert info["ready"] is True and info["render"] == "576x1024" and info["max_morphs"] == cloud_final.MAX_MORPHS
    assert "sk-test" not in res.text
