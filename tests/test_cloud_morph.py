"""Cloud quality (LTX-2.5 partner node): planning, price, gates, dry run. Nothing here can spend."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import cloud_morph as cm

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "ltx25_partner_object_info.json"
HAS_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture(autouse=True)
def _never_spend(monkeypatch):
    monkeypatch.setenv("XENO_CLOUD_NEVER", "1")
    monkeypatch.delenv("COMFY_ORG_API_KEY", raising=False)
    monkeypatch.delenv("XENO_CLOUD_CAP_USD", raising=False)
    monkeypatch.delenv("XENO_CLOUD_DRY_RUN", raising=False)
    info = json.loads(FIXTURE.read_text(encoding="utf-8"))[cm.PARTNER_NODE]
    monkeypatch.setattr(cm, "prices", lambda url=None, timeout=5.0: (cm.FALLBACK_USD_PER_S, info, "fixture"))
    yield


def beats(duration=20.0, step=0.5):
    return [round(i * step, 3) for i in range(1, int(duration / step))]


def test_snap_to_allowed_durations():
    assert [cm.snap_duration(x) for x in (0.4, 2, 2.4, 2.5, 3.6, 4.9, 5, 5.6, 7, 9.2, 14)] == [2, 2, 2, 3, 4, 5, 5, 6, 8, 10, 10]


def test_twenty_seconds_is_four_five_second_shots_on_the_beat():
    shots = cm.plan_shots(20.0, beats())
    assert [s["render_s"] for s in shots] == [5, 5, 5, 5]
    assert [s["start"] for s in shots] == [0.0, 5.0, 10.0, 15.0]
    assert sum(s["frames"] for s in shots) == 480
    odd = cm.plan_shots(13.0, [4.6, 9.9])
    assert [round(s["start"], 1) for s in odd] == [0.0, 4.6, 9.9]
    assert all(2 <= s["seconds"] <= 7 for s in odd)
    assert all(s["render_s"] in cm.ALLOWED_S for s in odd)


def test_price_per_twenty_second_clip_and_cap():
    est = cm.estimate(cm.plan_shots(20.0, beats()))
    assert est["render_seconds"] == 20
    assert est["usd"] == pytest.approx(2.574)
    assert est["credits"] == pytest.approx(543.1, abs=0.1)
    assert est["aud"] == pytest.approx(3.71)
    assert not est["over_cap"]
    assert cm.estimate(cm.plan_shots(30.0, beats(30)))["over_cap"]


def test_confirm_token_covers_only_what_was_shown():
    est = cm.estimate(cm.plan_shots(20.0, beats()))
    token = cm.mint_token(est, now=1000)
    assert cm.check_token(token, est, now=1100) is None
    assert "expired" in cm.check_token(token, est, now=1000 + cm.TOKEN_TTL_S + 5)
    assert "not from this desk" in cm.check_token(token[:-1] + ("0" if token[-1] != "0" else "1"), est, now=1100)
    dearer = dict(est, usd=est["usd"] + 0.5)
    assert "more than" in cm.check_token(token, dearer, now=1100)
    assert "confirm click" in cm.check_token("", est)


def test_graph_chains_stills_and_validates_against_the_installed_node():
    shots = cm.plan_shots(20.0, beats())
    stills = [{"path": f"/x/s{j}.jpg", "noun": str(j)} for j in range(5)]
    graph = cm.build_graph(shots, stills, prompt=cm.DEFAULT_PROMPT, seed=2727)
    info = json.loads(FIXTURE.read_text(encoding="utf-8"))[cm.PARTNER_NODE]
    assert cm.validate_partner(graph, info) == []
    for i in range(4):
        node = graph[str(100 + i)]["inputs"]
        assert node["image"] == [str(10 + i), 0] and node["last_frame"] == [str(11 + i), 0]
        assert node["model.duration"] == "5" and node["model.resolution"] == "1280x720"
        assert node["model.fps"] == "24" and node["model.generate_audio"] is False
    bad = json.loads(json.dumps(graph))
    bad["100"]["inputs"]["model.duration"] = "7"
    assert cm.validate_partner(bad, info)


def test_black_vibe_pool_and_demo_chain():
    pools = json.loads((ROOT / "src/xenoform/ui_static/objects/objects.json").read_text(encoding="utf-8"))
    black = pools["black"]
    assert len(black) == 12
    assert tuple(item["noun"] for item in black[:5]) == cm.BLACK_CHAIN
    for item in black:
        assert (ROOT / "src/xenoform/ui_static/objects" / item["file"]).is_file()
    vibe, stills = cm.chain_stills({"vibe": "black"}, 5)
    assert vibe == "black" and [s["noun"] for s in stills] == list(cm.BLACK_CHAIN)
    app = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    assert 'id: "black"' in app and "/static/vibes/black.jpg" in app
    assert "Confirm and render" in app and "cloud_confirm" in app and "beat_overlay" in app
    assert "/api/cloud/estimate" in app


def test_default_path_stays_open_weights():
    from xenoform.eligibility import DEFAULT_WORKFLOWS, audit_default_workflows

    assert audit_default_workflows() == []
    assert not any("partner" in rel for rel in DEFAULT_WORKFLOWS)


class _Out:
    def __init__(self, src: Path):
        self.type = "video"
        self.src = src

    def to_file(self, dest: str):
        shutil.copyfile(self.src, dest)


class FakeClient:
    """Records what would be sent. Never touches a network."""

    def __init__(self, clip: Path):
        self.clip = clip
        self.submits = []
        self.assets = self
        self.workflows = self
        self.jobs = self

    def from_file(self, path):
        return f"asset:{Path(path).name}"

    def from_json(self, graph):
        return _Wf(graph)

    def submit(self, wf, api_key=None):
        self.submits.append({"graph": wf.graph, "api_key": api_key})
        return _Job(self.clip, wf.graph)


class _Wf:
    def __init__(self, graph):
        self.graph = graph

    def set_input(self, nid, field, value):
        self.graph[nid]["inputs"][field] = value


class _Job:
    id = "fake"

    def __init__(self, clip, graph):
        self.clip, self.graph = clip, graph

    def result(self):
        clip = self.clip

        class R:
            outputs = []

            def get_outputs(self, nid):
                return [_Out(clip)]

        return R()


def _audio(path: Path, seconds=20.0):
    sr = 22050
    t = np.arange(int(sr * seconds)) / sr
    tone = (0.3 * np.sin(2 * np.pi * 110 * t) * (0.5 + 0.5 * (np.sin(2 * np.pi * 2 * t) > 0))).astype(np.float32)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-", str(path)],
                   input=tone.tobytes(), check=True)
    return path


def _report(*_a):
    return None


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_dry_run_end_to_end_mock_stitches_on_the_grid_with_overlay(tmp_path):
    audio = _audio(tmp_path / "a.wav")
    out = tmp_path / "out.mp4"
    directed = {"duration": 20.0, "beats": beats()}
    state = {"vibe": "black", "beat_overlay": True, "cloud_quality": True}
    info = cm.run_chain("mock", directed, audio, out, tmp_path, {}, state, _report)
    assert out.is_file() and info["frames"] == 480 and info["overlay"]
    assert info["spent_usd"] == 0.0 and info["label"].startswith("DRY RUN")
    assert info["handoffs_s"] == [0.0, 5.0, 10.0, 15.0, 20.0]
    plan = json.loads((tmp_path / "cloud" / "plan_mock.json").read_text())
    assert plan["graph_errors"] == [] and plan["estimate"]["usd"] == pytest.approx(2.574)
    assert "api_key" not in json.dumps(plan).lower()


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_cloud_gates_refuse_before_anything_is_sent(tmp_path, monkeypatch):
    audio = _audio(tmp_path / "a.wav", 6)
    clip = tmp_path / "c.mp4"
    shutil.copyfile(audio, tmp_path / "x.wav")
    directed = {"duration": 20.0, "beats": beats()}
    fake = FakeClient(clip)
    base = {"vibe": "black", "cloud_quality": True}
    with pytest.raises(cm.CloudRefused, match="confirm"):
        cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, base, _report, client=fake)
    est = cm.estimate(cm.plan_shots(20.0, beats()))
    token = cm.mint_token(est)
    with pytest.raises(cm.CloudRefused, match="API key"):
        cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, {**base, "cloud_confirm": token}, _report, client=fake)
    monkeypatch.setenv("COMFY_ORG_API_KEY", "test-not-a-key")
    with pytest.raises(cm.CloudRefused, match="XENO_CLOUD_NEVER"):
        cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, {**base, "cloud_confirm": cm.mint_token(est)}, _report, client=fake)
    monkeypatch.setenv("XENO_CLOUD_CAP_USD", "1.00")
    with pytest.raises(cm.CloudRefused, match="cap"):
        cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, {**base, "cloud_confirm": cm.mint_token(est)}, _report, client=fake)
    assert fake.submits == []


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_all_gates_open_sends_one_parallel_prompt_with_the_key(tmp_path, monkeypatch):
    """Fake client only: proves the paid path's shape without a network."""
    audio = _audio(tmp_path / "a.wav")
    clip = tmp_path / "shot.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x180:r=24:d=5", str(clip)], check=True)
    monkeypatch.delenv("XENO_CLOUD_NEVER", raising=False)
    monkeypatch.setenv("COMFY_ORG_API_KEY", "test-not-a-key")
    directed = {"duration": 20.0, "beats": beats()}
    est = cm.estimate(cm.plan_shots(20.0, beats()))
    token = cm.mint_token(est)
    fake = FakeClient(clip)
    state = {"vibe": "black", "cloud_quality": True, "cloud_confirm": token}
    info = cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, state, _report, client=fake)
    assert len(fake.submits) == 1
    sent = fake.submits[0]
    assert sent["api_key"] == "test-not-a-key"
    assert sum(1 for n in sent["graph"].values() if n["class_type"] == cm.PARTNER_NODE) == 4
    assert info["label"] == cm.LABEL and info["spent_usd"] == pytest.approx(2.574)
    assert "test-not-a-key" not in (tmp_path / "cloud" / "plan_cloud.json").read_text()
    assert "test-not-a-key" not in (tmp_path / "cloud" / "result_cloud.json").read_text()
    with pytest.raises(cm.CloudRefused, match="already used"):
        cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, state, _report, client=fake)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_cloud_failure_falls_back_to_the_local_cut(tmp_path, monkeypatch):
    audio = _audio(tmp_path / "a.wav")
    out = tmp_path / "out.mp4"
    local = tmp_path / "local.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x180:r=24:d=1", str(local)], check=True)

    def fake_chain(engine, directed, audio_path, out_path, work, cfg, state, report, **kw):
        if engine == "local":
            shutil.copyfile(local, out_path)
            return {"file": str(local)}
        raise cm.CloudRefused("No Comfy API key in COMFY_ORG_API_KEY. Nothing was sent.")

    monkeypatch.setattr(cm, "run_chain", fake_chain)
    info, warning = cm.run_cloud_quality({"duration": 20.0}, audio, out, tmp_path, {}, {"vibe": "black"}, _report)
    assert "Cloud quality did not run" in warning
    assert out.read_bytes() == local.read_bytes()
    assert "cloud_error" in info


def test_estimate_route_is_read_only_and_mints_a_token(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app())
    plan = client.post("/api/cloud/estimate", json={"audio_id": "demo", "vibe": "black"}).json()
    assert plan["estimate"]["usd"] > 0 and plan["token"]
    assert plan["label"] == cm.LABEL
    assert plan["key_present"] is False
    assert plan["stills"][0].startswith("black/")


def test_story_words_do_not_rotate_the_black_chain():
    state = {"vibe": "black", "brief": "a swarm of drops on the drop", "scenes": [{"form": "lotus of light"}]}
    vibe, stills = cm.chain_stills(state, 5)
    assert [s["noun"] for s in stills] == list(cm.BLACK_CHAIN)
