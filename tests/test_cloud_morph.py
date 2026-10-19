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
    assert not est["over_cap"] and est["cap_usd"] == 5.0
    assert not cm.estimate(cm.plan_shots(30.0, beats(30)))["over_cap"]  # US$3.86
    assert cm.estimate(cm.plan_shots(40.0, beats(40)))["over_cap"]  # US$5.15


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
    assert len(black) == 17 and len({item["noun"] for item in black}) == 17
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


# ---------------------------------------------------------------- custom cut points


def dense_plan():
    """The shape of demo1's dense cut: calm shots on downbeats, the drop on half-bars at 2.5x."""
    p = lambda t, s=1.0: {"type": "punch", "t": t, "strength": s}
    return {
        "stills": ["rose", "jellyfish", "butterfly", "swallow", "dragonfly", "drop swarm", "mobius", "sea urchin"],
        "shots": [
            {"start": 0.0, "end": 3.275, "render_s": 3, "speed": 0.92,
             "effects": [p(1.216), {"type": "stutter", "t": 1.216, "frames": 2, "repeat": 3}]},
            {"start": 3.275, "end": 4.864, "render_s": 2},
            {"start": 4.864, "end": 6.453, "render_s": 2},
            {"start": 6.453, "end": 12.8, "speed": 0.9},  # render_s chosen from the speed: snap_up(5.71) = 6
            {"start": 12.8, "end": 13.6, "render_s": 2, "speed": 2.5, "effects": [p(12.8), {"type": "stutter", "t": 12.8}]},
            {"start": 13.6, "end": 14.432, "render_s": 2, "speed": 2.4,
             "effects": [{"type": "hold", "t": 13.77, "len": 0.12}, p(13.899), {"type": "skip", "t": 13.899, "amount": 0.3}]},
            {"start": 14.432, "end": 20.0, "render_s": 6, "ease": "in",
             "effects": [p(19.2), {"type": "reverse", "t": 19.2, "len": 0.405}]},
        ],
    }


def test_custom_cut_points_shape_render_seconds_and_cost():
    shots = cm.custom_shots(dense_plan(), 20.0)
    assert [s["render_s"] for s in shots] == [3, 2, 2, 6, 2, 2, 6]
    assert sum(s["frames"] for s in shots) == 480
    assert shots[4]["speed"] == pytest.approx(2.5) and shots[0]["speed"] == pytest.approx(0.916, abs=1e-3)
    est = cm.estimate(shots)
    assert est["render_seconds"] == 23 and est["usd"] == pytest.approx(23 * 0.1287)
    assert est["aud"] == pytest.approx(round(23 * 0.1287 * 1.44, 2)) and not est["over_cap"]
    assert cm.snap_up(0.8) == 2 and cm.snap_up(2.01) == 3 and cm.snap_up(6.5) == 8


@pytest.mark.parametrize("change, why", [
    (lambda p: p["shots"][1].update(render_s=7), "not an allowed duration"),
    (lambda p: p["shots"][1].update(render_s=1), "not an allowed duration"),
    (lambda p: p["shots"][2].update(start=5.0), "previous one ends"),
    (lambda p: p["shots"][4].update(speed=1.5), "plays at 2.50x"),
    (lambda p: p["shots"][1]["effects"].append({"type": "punch", "t": 9.0}) if p["shots"][1].setdefault("effects", []) is not None else None, "outside"),
    (lambda p: p["shots"][1].update(effects=[{"type": "glitch", "t": 3.5}]), "unknown effect"),
    (lambda p: p["shots"][-1].update(end=25.0), "past the"),
])
def test_bad_cut_plans_are_refused(change, why):
    plan = dense_plan()
    change(plan)
    with pytest.raises(cm.CutPlanError, match=why):
        cm.custom_shots(plan, 20.0)


def test_effects_change_only_which_frame_plays_and_keep_the_chain_continuous():
    shots = {s["index"]: s for s in cm.custom_shots(dense_plan(), 20.0)}
    for shot in shots.values():
        idx = cm.shot_indices(shot, 49)
        assert len(idx) == shot["frames"] and idx[0] == 0 and idx[-1] == 48 and idx.min() >= 0 and idx.max() <= 48
    plain = cm.shot_indices(shots[1], 49)
    assert (np.diff(plain) >= 0).all()  # no effects: monotonic, a plain retime
    first = cm.shot_indices(shots[0], 73)
    k = round(1.216 * cm.FPS)
    assert list(first[k:k + 6]) == [first[k], first[k + 1]] * 3  # stutter: a 2-frame slice three times
    hold = cm.shot_indices(shots[5], 49)
    k = round((13.77 - 13.6) * cm.FPS)
    assert len(set(hold[k:k + 2])) == 1  # 60 ms freeze before the slam
    k = round((13.899 - 13.6) * cm.FPS)
    assert hold[k] - hold[k - 1] > 2  # skip: lurches ahead on the hit
    rev = cm.shot_indices(shots[6], 145)
    k = round((19.2 - 14.432) * cm.FPS)
    assert rev[k + 3] < rev[k]  # reverse for a beat
    ramp = cm.shot_indices(shots[6], 145)
    assert ramp[10] - ramp[0] < ramp[-1] - ramp[-11]  # ease in: accelerates into the end
    punch = cm.punch_curve(list(shots.values()))
    assert punch[round(12.8 * cm.FPS)] == pytest.approx(1.0) and punch[round(10.0 * cm.FPS)] == 0
    frame = np.full((36, 64, 3), 100, np.uint8)
    assert cm.apply_punch(frame, 1.0).mean() > frame.mean() and cm.apply_punch(frame, 0.0) is frame


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_custom_cut_dry_run_end_to_end_and_paid_gates(tmp_path, monkeypatch):
    audio = _audio(tmp_path / "a.wav")
    directed = {"duration": 20.0, "beats": beats()}
    state = {"vibe": "black", "beat_overlay": True, "cloud_quality": True, "cut_plan": dense_plan()}
    info = cm.run_chain("mock", directed, audio, tmp_path / "o.mp4", tmp_path, {}, state, _report)
    assert info["frames"] == 480 and info["spent_usd"] == 0.0
    assert info["handoffs_s"] == [0.0, 3.275, 4.864, 6.453, 12.8, 13.6, 14.432, 20.0]
    assert info["stills"][4] == "black/13_dragonfly_gr.jpg"
    plan = json.loads((tmp_path / "cloud" / "plan_mock.json").read_text())
    durations = [n["inputs"]["model.duration"] for n in plan["graph"].values() if n["class_type"] == cm.PARTNER_NODE]
    assert durations == ["3", "2", "2", "6", "2", "2", "6"] and plan["graph_errors"] == []
    assert plan["estimate"]["render_seconds"] == 23
    # the confirm token must cover THIS plan: a token for the cheaper auto plan is refused
    cheap = cm.mint_token(cm.estimate(cm.plan_shots(20.0, beats())))
    monkeypatch.setenv("COMFY_ORG_API_KEY", "test-not-a-key")
    fake = FakeClient(tmp_path / "c.mp4")
    with pytest.raises(cm.CloudRefused):
        cm.run_chain("cloud", directed, audio, tmp_path / "o.mp4", tmp_path, {}, {**state, "cloud_confirm": cheap}, _report, client=fake)
    assert fake.submits == []


def test_estimate_route_prices_a_cut_plan_and_rejects_a_bad_one():
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app())
    short = dense_plan()  # the bundled demo song is 12 s: the first three shots fit
    short["shots"] = short["shots"][:3]
    plan = client.post("/api/cloud/estimate", json={"audio_id": "demo", "vibe": "black", "cut_plan": short}).json()
    assert plan["custom_cut"] is True and plan["estimate"]["render_seconds"] == 7 and plan["token"]
    assert [s["render_s"] for s in plan["shots"]] == [3, 2, 2] and plan["stills"][3] == "black/03_swallow_gr.jpg"
    too_long = client.post("/api/cloud/estimate", json={"audio_id": "demo", "vibe": "black", "cut_plan": dense_plan()})
    assert too_long.status_code == 400 and "past the" in too_long.json()["detail"]
    bad = dict(short, shots=[dict(x) for x in short["shots"]])
    bad["shots"][1]["render_s"] = 7
    res = client.post("/api/cloud/estimate", json={"audio_id": "demo", "vibe": "black", "cut_plan": bad})
    assert res.status_code == 400 and "allowed duration" in res.json()["detail"]
