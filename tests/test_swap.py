"""A swap on the shots lane after the cut (26 Oct 2026): ``dense.swap_still`` re-renders only the two morphs that
touch a still (the Draft path, the cut's own seed, the still prepared as the cut prepared its stills), keeps the other
clips, updates the record in place (``stills``, ``clips``, ``scene_files``, a ``swaps`` log) and re-composes through
``recut_from_cache``; ``POST /api/jobs/{id}/swap`` runs it; ``lane.build`` names the slot each shot lands on."""
import json
import threading
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from xenoform import dense, lane, stills as S

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
DEMO = ROOT / "examples" / "demo.wav"
W, H = 512, 288


def _object(path: Path, *, cx=0.5, cy=0.5, r=0.2, noise=3) -> Path:
    im = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(im)
    rr = r * H
    d.ellipse((cx * W - rr, cy * H - rr, cx * W + rr, cy * H + rr), fill=(170, 175, 180))
    a = np.asarray(im).astype(np.int16)
    rng = np.random.default_rng(int(cx * 1000 + cy * 100 + r * 10))
    a = np.clip(a + rng.integers(-noise, noise + 1, a.shape), 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path)
    return path


def _grown(vibe: str, name: str, noun: str, *, kind: str = "object", cx: float = 0.5) -> str:
    """A grown still on disk and in stills.json (the conftest points XENO_STILLS at a temp dir)."""
    _object(S.root() / vibe / name, cx=cx)
    idx = S._read_json(S.index_path(), {})
    row = {"file": f"{vibe}/{name}", "noun": noun}
    if kind == "scene":
        row["kind"] = "scene"
    idx.setdefault(vibe, []).append(row)
    S._write_json(S.index_path(), idx)
    return row["file"]


def _fake_compose(seen):
    def compose(clips, shots, audio, out, **kw):
        seen["clips"] = [str(c) for c in clips]
        seen["kw"] = kw
        seen["calls"] = seen.get("calls", 0) + 1
        Path(out).write_bytes(b"new")
        return {"frames": 1, "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}}

    return compose


def _cut(tmp_path, monkeypatch, seen, *, aspect="16:9", scene_stills=None) -> Path:
    """A Simple cut on the mock engine over the shipped cosmic pool (real jpgs), the morph clips stubbed, the compose spied."""
    from xenoform import beatfx
    import xenoform.cloud_morph as cm

    def fake_mock(shots, stills, work, w, h):
        out = []
        for i in range(len(shots)):
            p = Path(work) / f"mock{i:02d}.mp4"
            p.write_bytes(b"mp4")
            out.append(p)
        return out

    real = cm._mock_clips
    monkeypatch.setattr(cm, "_mock_clips", fake_mock)
    monkeypatch.setattr(beatfx, "compose", _fake_compose(seen))
    monkeypatch.setattr(S, "usage", lambda: {})
    job = tmp_path / "jobs" / "cut"
    job.mkdir(parents=True)
    state = {"vibe": "cosmic", "aspect": aspect, "quality_tier": "draft", "energy_preset": "dense"}
    if scene_stills:
        state["scene_stills"] = scene_stills
    dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, DEMO, job / "xenoform.mp4", job, {}, state,
                     lambda *a: None, engine="mock")
    monkeypatch.setattr(cm, "_mock_clips", real)  # the swap itself cross-fades the real stills through ffmpeg
    seen.clear()
    return job


def test_a_swap_re_renders_the_two_morphs_that_touch_the_still_and_keeps_the_rest(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    before = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    old_files, old_clips = list(before["stills"]), list(before["clips"])
    n = len(old_files)
    reports = []
    rec = dense.swap_still(job, 3, new, report=lambda stage, frac, detail: reports.append((stage, detail)))
    assert rec["stills"][3] == new and rec["stills"][:3] == old_files[:3] and rec["stills"][4:] == old_files[4:]
    assert rec["clips"][2] != old_clips[2] and rec["clips"][3] != old_clips[3]
    assert [c for i, c in enumerate(rec["clips"]) if i not in (2, 3)] == [c for i, c in enumerate(old_clips) if i not in (2, 3)]
    assert all(Path(c).is_file() for c in rec["clips"]) and Path(rec["clips"][2]).parent == job / "simple" / "swaps" / "00"
    assert Path(rec["clips"][2]).name == "morph02.mp4" and Path(rec["clips"][3]).name == "morph03.mp4"
    assert Path(rec["clips"][2]).stat().st_size > 1000  # a real cross-fade of the shipped still and the new one
    assert len(rec["swaps"]) == 1 and rec["swaps"][0]["slot"] == 3 and rec["swaps"][0]["from"] == old_files[3]
    assert rec["swaps"][0]["to"] == new and rec["swaps"][0]["morphs"] == [2, 3] and rec["swaps"][0]["shots"] == [2, 3]
    assert rec["recuts"] == 1 and seen["calls"] == 1 and seen["clips"] == rec["clips"]  # re-composed through the re-cut path
    assert (job / "xenoform.mp4").read_bytes() == b"new"
    assert rec["scene_files"] == [] and "wolf skull" not in old_files and len(set(rec["stills"])) == n
    assert [s for s in reports if s[0] == "restyle"] and any("Re-rendering morph 3 of" in d for _, d in reports)
    on_disk = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert on_disk["stills"] == rec["stills"] and on_disk["clips"] == rec["clips"] and len(on_disk["swaps"]) == 1
    # the second swap lands in its own folder, the log grows, and the first swap's still may be swapped again
    other = _grown("cosmic", "001_brass_key.jpg", "brass key", cx=0.4)
    rec2 = dense.swap_still(job, 3, other)
    assert rec2["stills"][3] == other and len(rec2["swaps"]) == 2 and Path(rec2["clips"][3]).parent.name == "01" and rec2["recuts"] == 2


def test_a_swap_on_the_first_or_last_slot_re_renders_one_morph_and_a_scene_counts_as_a_scene(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    scene = _grown("cosmic", "100_shore.jpg", "dark shore under a star field", kind="scene")
    before = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    n = len(before["stills"])
    rec = dense.swap_still(job, 0, scene)
    assert rec["swaps"][0]["morphs"] == [0] and rec["clips"][1:] == before["clips"][1:] and rec["stills"][0] == scene
    assert rec["scene_files"] == [scene] and Path(rec["palette_image"]).name == "100_shore.jpg"
    last = _grown("cosmic", "002_fox.jpg", "fox", cx=0.6)
    rec = dense.swap_still(job, n - 1, last)
    assert rec["swaps"][1]["morphs"] == [n - 2] and rec["stills"][-1] == last and rec["scene_files"] == [scene]


def test_a_swap_refuses_a_final_cut_a_repeat_a_bad_slot_an_unknown_file_and_a_gone_record(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec_path = job / "simple" / "simple.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    with pytest.raises(ValueError, match="already in this cut"):
        dense.swap_still(job, 2, rec["stills"][5])
    with pytest.raises(ValueError, match="already in slot"):
        dense.swap_still(job, 2, rec["stills"][2])
    with pytest.raises(ValueError, match="not one of them"):
        dense.swap_still(job, len(rec["stills"]), new)
    with pytest.raises(ValueError, match="Which slot"):
        dense.swap_still(job, "x", new)
    with pytest.raises(ValueError, match="not in the stills library"):
        dense.swap_still(job, 2, "cosmic/nope.jpg")
    final = dict(rec, tier="final")
    rec_path.write_text(json.dumps(final), encoding="utf-8")
    with pytest.raises(ValueError, match="Final"):
        dense.swap_still(job, 2, new)
    rec_path.write_text(json.dumps(dict(rec, clips=rec["clips"][:-1])), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        dense.swap_still(job, 2, new)
    with pytest.raises(FileNotFoundError):
        dense.swap_still(tmp_path / "jobs" / "none", 0, new)
    assert seen.get("calls", 0) == 0


def test_a_swap_skips_a_morph_a_performer_slot_replaced(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec_path = job / "simple" / "simple.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    shots, clips = rec["plan_shots"], rec["clips"]
    # Polly took shots 2 and 3 (morphs 2 and 3): one merged shot playing her clip, no morph index
    polly = {**shots[2], "end": shots[3]["end"], "performer": True, "instrument": "drums"}
    polly.pop("morph", None)
    rec["plan_shots"] = rec["shots"] = shots[:2] + [polly] + shots[4:]
    rec["clips"] = clips[:2] + [clips[2]] + clips[4:]
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    out = dense.swap_still(job, 4, new)  # touches morphs 3 (gone with Polly) and 4 (shot index 3 now)
    assert out["swaps"][0]["morphs"] == [4] and out["swaps"][0]["shots"] == [3] and out["clips"][2] == clips[2]
    with pytest.raises(ValueError, match="Polly"):
        dense.swap_still(job, 3, _grown("cosmic", "001_fox.jpg", "fox", cx=0.6))  # both of slot 3's morphs are under her


def test_a_swap_prepares_the_still_as_a_portrait_draft_did(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=0, h=0, background=None: [{**s, "portrait": (w, h)} for s in stills])
    job = _cut(tmp_path, monkeypatch, seen, aspect="9:16")
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert rec["prep"]["native_draft"] is True and rec["prep"]["draft_size"] == [320, 576]
    sizes = []
    import xenoform.cloud_morph as cm

    real = cm._mock_clips

    def spy(shots, stills, work, w, h):
        sizes.append((w, h, [s.get("portrait") for s in stills]))
        return real(shots, stills, work, w, h)

    monkeypatch.setattr(cm, "_mock_clips", spy)
    out = dense.swap_still(job, 2, _grown("cosmic", "000_wolf_skull.jpg", "wolf skull"))
    assert sizes == [(320, 576, [(320, 576), (320, 576)])] * 2 and len(out["swaps"]) == 1
    # a record from before ``prep``: the Draft 9:16 note says the same
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    rec.pop("prep")
    (job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    sizes.clear()
    dense.swap_still(job, 5, _grown("cosmic", "001_fox.jpg", "fox", cx=0.6))
    assert sizes and sizes[0][:2] == (320, 576)


def test_the_draft_path_renders_the_pair_with_the_cut_seed(tmp_path, monkeypatch):
    """The real engine: the pair goes through ``cloud_morph._local_clips`` with the cut's seed for that morph."""
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    rec_path = job / "simple" / "simple.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    rec["engine"] = "LTX 0.9.5 (Draft)"
    rec["seed"] = 4242
    rec_path.write_text(json.dumps(rec), encoding="utf-8")
    wfs = []

    class WF:
        def __init__(self):
            self.inputs = {}

        def set_input(self, node, key, value):
            self.inputs[(node, key)] = value

    class Out:
        type = "video"

        def to_file(self, path):
            Path(path).write_bytes(b"pair")

    class Job:
        def result(self):
            class R:
                outputs = [Out()]

                def get_outputs(self, node):
                    return [Out()]

            return R()

    class Client:
        class assets:
            @staticmethod
            def from_file(path):
                return path

        class workflows:
            @staticmethod
            def from_file(path):
                wf = WF()
                wfs.append(wf)
                return wf

        def submit(self, wf):
            return Job()

    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    out = dense.swap_still(job, 3, new, cfg={}, client=Client())
    assert len(wfs) == 2
    assert [wf.inputs[("13", "noise_seed")] for wf in wfs] == [4242 + 2, 4242 + 3]
    assert Path(wfs[0].inputs[("7", "image")]).name == "000_wolf_skull.jpg" and Path(wfs[1].inputs[("6", "image")]).name == "000_wolf_skull.jpg"
    assert Path(wfs[0].inputs[("6", "image")]).name == Path(rec["stills"][2]).name and Path(wfs[1].inputs[("7", "image")]).name == Path(rec["stills"][4]).name
    from xenoform import morph_pass as mp

    assert [(wf.inputs[("9", "width")], wf.inputs[("9", "height")]) for wf in wfs] == [(mp.WIDTH, mp.HEIGHT)] * 2  # a 16:9 Draft: the morph size
    assert Path(out["clips"][2]).read_bytes() == b"pair" and Path(out["clips"][3]).read_bytes() == b"pair"


# ---------------------------------------------------------------------------------------------- the desk


def test_the_swap_route_runs_the_swap_and_bumps_the_video(tmp_path, monkeypatch):
    from xenoform import dense as dense_mod, ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / "swap-test"
    (folder / "simple").mkdir(parents=True)
    (folder / "simple" / "simple.json").write_text(json.dumps({"stills": ["cosmic/00_orb_iridescent.jpg", "cosmic/01_crescent_moon_oil_slick.jpg",
                                                                          "cosmic/02_pearl_iridescent.jpg"], "tier": "draft"}), encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"old")
    done = threading.Event()

    def fake_swap(job_dir, slot, file, *, cfg=None, report=None, client=None):
        assert Path(job_dir).name == "swap-test" and slot == 1 and file == "cosmic/05_mobius_iridescent.jpg"
        if report:
            report("restyle", 0.3, "Re-rendering morph 1 of 2")
        done.set()
        return {"look": {}, "recuts": 1, "swaps": [{"slot": 1}]}

    monkeypatch.setattr(dense_mod, "swap_still", fake_swap)
    try:
        assert client.post("/api/jobs/no-such/swap", json={"slot": 0, "file": "cosmic/05_mobius_iridescent.jpg"}).status_code == 404
        # a cut reopened after a desk restart is registered from its folder; the cheap refusals answer at once
        assert client.post("/api/jobs/swap-test/swap", json={"slot": 9, "file": "cosmic/05_mobius_iridescent.jpg"}).status_code == 400
        assert client.post("/api/jobs/swap-test/swap", json={"slot": 1, "file": "cosmic/00_orb_iridescent.jpg"}).status_code == 400
        assert client.post("/api/jobs/swap-test/swap", json={"slot": 1, "file": "cosmic/nope.jpg"}).status_code == 400
        assert client.post("/api/jobs/swap-test/swap", json={"slot": "x", "file": "cosmic/05_mobius_iridescent.jpg"}).status_code == 400
        assert client.post("/api/jobs/swap-test/swap", json={"slot": 1}).status_code == 400
        r = client.post("/api/jobs/swap-test/swap", json={"slot": 1, "file": "cosmic/05_mobius_iridescent.jpg"})
        assert r.status_code == 200 and r.json() == {"id": "swap-test", "status": "running", "slot": 1, "file": "cosmic/05_mobius_iridescent.jpg"}
        assert done.wait(10)
        import time

        for _ in range(50):
            job = client.get("/api/jobs/swap-test").json()
            if job["status"] == "done" and job.get("video_version") == 1:
                break
            time.sleep(0.1)
        assert job["video_version"] == 1 and job["video"].endswith("?v=1") and job["swaps"] == 1 and job["detail"] == "Swap ready"
        assert client.get("/api/jobs/swap-test/video").status_code == 200
        with ui_mod._LOCK:
            ui_mod._JOBS["swap-test"]["status"] = "running"
        assert client.post("/api/jobs/swap-test/swap", json={"slot": 1, "file": "cosmic/05_mobius_iridescent.jpg"}).status_code == 409
        with ui_mod._LOCK:
            ui_mod._JOBS["swap-test"]["status"] = "done"
        (folder / "simple" / "simple.json").write_text(json.dumps({"stills": ["cosmic/00_orb_iridescent.jpg"], "tier": "final"}), encoding="utf-8")
        assert "Final" in client.post("/api/jobs/swap-test/swap", json={"slot": 0, "file": "cosmic/05_mobius_iridescent.jpg"}).json()["detail"]
        assert client.get("/api/jobs/nope/swap").status_code == 405
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("swap-test", None)


def test_the_lane_names_the_slot_each_shot_lands_on_and_the_pinned_and_swapped_ones():
    info = {"shots": [{"start": 0.0, "end": 2.0, "morph": 0}, {"start": 2.0, "end": 4.0, "morph": 1},
                      {"start": 4.0, "end": 6.0, "performer": True}, {"start": 6.0, "end": 8.0, "morph": 3}],
            "stills": ["v/00_a.jpg", "v/01_b.jpg", "v/02_c.jpg", "v/03_d.jpg", "v/100_shore.jpg"], "scene_files": ["v/100_shore.jpg"],
            "pinned": [1], "swaps": [{"slot": 4, "from": "v/04_e.jpg", "to": "v/100_shore.jpg"}], "vibe": "v", "tier": "draft",
            "performer": {"slots": [{"first": 2, "last": 2, "instrument": "drums"}]}}
    out = lane.build(info, "x")
    rows = out["shots"]
    assert [(r["from"], r["to"]) for r in rows] == [("a", "b"), ("b", "c"), ("c", "d"), ("d", "shore")]
    assert [r.get("still") for r in rows] == [1, 2, None, 4] and rows[0]["from_still"] == 0 and rows[3]["to_file"] == "v/100_shore.jpg"
    assert rows[0]["pinned"] is True and rows[1]["pinned"] is False and rows[3]["swapped"] is True and rows[3]["to_kind"] == "scene"
    assert out["stills"][1] == {"index": 1, "file": "v/01_b.jpg", "noun": "b", "kind": "object", "pinned": True, "swapped": False}
    assert out["stills"][4]["swapped"] and out["stills"][4]["kind"] == "scene" and out["swaps"] == 1
    assert out["vibe"] == "v" and out["swappable"] is True
    assert lane.build({**info, "tier": "final"})["swappable"] is False and lane.build({})["swappable"] is False


def test_front_end_offers_the_swap_on_the_lane():
    fn = APP.split("function shotsLane(easy)")[1].split("async function loadLane")[0]
    assert 'data-act="easy-swap-mode"' in fn and 'data-act="easy-swap-pick"' in fn and "swappable" in fn
    assert "async function swapStill" in APP and "/swap`" in APP and '"easy-swap", slot.index' in fn and 'data-act="easy-swap-cancel"' in fn
    swap = APP.split("async function swapStill")[1].split("\n}\n")[0]
    assert 'method: "POST"' in swap and "JSON.stringify" in swap and "poll(id);" in swap
    assert 'act === "easy-swap-mode"' in APP and 'act === "easy-swap-pick"' in APP and 'act === "easy-swap"' in APP
