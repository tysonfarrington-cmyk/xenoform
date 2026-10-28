"""Dream this span (xenoform.dream, 28 Oct): Z-Image Turbo img2img over 1 to 3 s of a finished cut at 12 dreamed
frames a second, cut in like a generated run. The span, the sizes, the held frames, a whole run through a fake ComfyUI
client on a mock-engine cut with real clips, the record, the lane, the route and the desk."""
import json
import shutil
import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest

from test_timeline import _cut, _rec
from xenoform import dense, dream, lane, morph_timing

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "src/xenoform/ui_static/desk.css").read_text(encoding="utf-8")
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg makes the clips")


def _shots(n=6, length=1.0, extra=None):
    extra = extra or {}
    return [{"start": i * length, "end": (i + 1) * length, "seconds": length, **(extra.get(i) or {})} for i in range(n)]


def test_the_span_is_whole_shots_of_about_the_length_asked():
    shots = _shots()
    assert dream.span(shots, 0, 2.0) == (0, 1) and dream.span(shots, 2, 3.0) == (2, 4)
    assert dream.span(shots, 5, 3.0) == (5, 5)  # never past the end
    assert dream.span(shots, 0, 9.0) == (0, 2) and dream.span(shots, 0, 0.2) == (0, 0)  # 1 to 3 s
    polly = _shots(extra={2: {"performer": True}})
    assert dream.span(polly, 0, 3.0) == (0, 1)  # Polly stops it
    with pytest.raises(ValueError, match="Polly"):
        dream.span(polly, 2, 2.0)
    with pytest.raises(ValueError, match="not one of them"):
        dream.span(shots, 9, 2.0)
    again = _shots(extra={1: {"dream": {"run": 0, "index": 0}}, 2: {"generated": {"insert": 0, "index": 0}}})
    assert dream.span(again, 1, 2.0) == (1, 2)  # a dream and a generated run can be dreamed over


def test_sizes_estimates_and_the_held_frames():
    assert dream.size_for("draft", 320, 576) == (432, 784) and dream.size_for("final", 1080, 1920) == (576, 1024)
    assert dream.size_for("draft", 768, 432) == (768, 432)
    assert all(v % 16 == 0 for v in dream.size_for("draft", 320, 576))
    assert dream.estimate(48) == round(dream.COLD_S + 24 * dream.SECONDS_PER_FRAME, 1) and dream.estimate(48, warm=True) < dream.estimate(48)
    d = [np.full((2, 2, 3), v, np.uint8) for v in (0, 100, 200)]
    got = [int(f[0, 0, 0]) for f in dream.held(d, 6)]
    assert got == [0, 50, 100, 150, 200, 200]  # each dream on its frame, the next a half blend, the last held
    assert "neon" in dream.prompt_for("neon-noir") or "magenta" in dream.prompt_for("neon-noir") or dream.prompt_for("neon-noir").startswith("a dreamlike")


def _real_clips(job: Path) -> None:
    """Swap the mock cut's stub clips for real ones (a moving test picture, 3 s each), as a render would leave."""
    rec_path = job / "simple" / "simple.json"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    out = []
    for i, _ in enumerate(rec["clips"]):
        p = job / "simple" / f"real{i:02d}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=64x112:rate=24:duration=3",
                        "-pix_fmt", "yuv420p", str(p)], check=True)
        out.append(str(p))
    rec["clips"] = out
    rec_path.write_text(json.dumps(rec), encoding="utf-8")


class _WF:
    def __init__(self, graph):
        self.graph = graph
        self.inputs = {}

    def set_input(self, node, key, value):
        self.inputs[(node, key)] = value


def _client(wfs):
    class Out:
        type = "image"

        def __init__(self, src):
            self.src = src

        def to_file(self, path):
            shutil.copyfile(self.src, path)  # the "dream" is the picture it was given

    class Job:
        def __init__(self, wf):
            self.wf = wf

        def result(self):
            src = self.wf.inputs[(dream.N_IMAGE, "image")]

            class R:
                outputs = [Out(src)]

                def get_outputs(self, node):
                    return [Out(src)]

            return R()

    class Client:
        class assets:
            @staticmethod
            def from_file(path):
                return path

        class workflows:
            @staticmethod
            def from_json(graph):
                wf = _WF(graph)
                wfs.append(wf)
                return wf

        def submit(self, wf):
            return Job(wf)

    return Client()


def test_a_dream_replaces_the_span_and_cuts_it_in_like_a_run(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    _real_clips(job)
    before = _rec(job)
    wfs, reports = [], []
    out = dream.dream_span(job, 2, seconds=2.0, depth="deep", client=_client(wfs), report=lambda st, fr, d: reports.append(d))
    entry = out["dreams"][-1]
    first, last = entry["first"], entry["last"]
    assert first == 2 and last >= 2 and entry["depth"] == "deep" and entry["denoise"] == dream.DEPTHS["deep"]
    span_frames = sum(int(before["shots"][j]["frames"]) for j in range(first, last + 1))
    assert entry["frames"] == sum((int(before["shots"][j]["frames"]) + 1) // 2 for j in range(first, last + 1)) == len(wfs)
    wf = wfs[0]
    assert wf.graph[dream.N_SAMPLER]["inputs"]["denoise"] == 0.55 and wf.graph[dream.N_SAMPLER]["inputs"]["seed"] == entry["seed"]
    assert "dreamlike" in wf.graph[dream.N_TEXT]["inputs"]["text"] and wf.graph[dream.N_IMAGE]["class_type"] == "LoadImage"
    for j in range(len(before["clips"])):
        if first <= j <= last:
            assert Path(out["clips"][j]).parent == job / "simple" / "dreams" / "00" and out["plan_shots"][j]["dream"]["run"] == 0
            probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                    "stream=nb_read_frames", "-of", "csv=p=0", out["clips"][j]], capture_output=True, text=True)
            assert int(probe.stdout.strip()) == int(before["shots"][j]["frames"])  # played 1:1
        else:
            assert out["clips"][j] == before["clips"][j] and "dream" not in out["plan_shots"][j]
    assert not (job / "simple" / "dreams" / "00" / "frames").exists() and out["recuts"] == int(before.get("recuts") or 0) + 1
    assert seen["calls"] == 1 and any("Dreaming frame" in r for r in reports) and span_frames > 0
    built = lane.build(out, "cut")
    rows = built["shots"]
    assert all(rows[j].get("dream") == 0 for j in range(first, last + 1)) and built["dreams"] == 1
    assert rows[first]["handoff"] == "cut" and (last + 1 >= len(rows) or rows[last + 1]["handoff"] == "cut")
    assert any(o["kind"] == "dream" and o["first"] == first for o in built["overlays"])
    assert dense._under_insert(out["plan_shots"][first]) == "a dream"
    with pytest.raises(ValueError, match="a dream"):
        dense.rerender_morph(job, first)
    timed = [dict(s) for s in out["shots"]]
    morph_timing.plan(timed, "snap", list(out.get("beats") or []), out.get("drop"))
    assert all("timing" not in timed[j] for j in range(first, last + 1))  # a dream is no morph to re-time
    with pytest.raises(ValueError, match="light or deep"):
        dream.dream_span(job, 0, depth="wild", client=_client([]))


def test_the_route_refuses_plainly_and_runs_the_dream(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / "dreamy"
    (folder / "simple").mkdir(parents=True)
    shots = _shots(6, 1.0, extra={4: {"performer": True}})
    (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "clips": ["c"] * 6}), encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"mp4")
    got, done = {}, threading.Event()

    def fake(job_dir, first, *, seconds=2.0, depth="light", seed=None, cfg=None, report=None, client=None):
        got.update(first=first, seconds=seconds, depth=depth)
        done.set()
        return {"look": {}, "recuts": 1}

    monkeypatch.setattr(dream, "dream_span", fake)
    try:
        assert client.post("/api/jobs/nope/dream", json={"first": 0}).status_code == 404
        assert client.post("/api/jobs/dreamy/dream", json={}).status_code == 400
        assert client.post("/api/jobs/dreamy/dream", json={"first": 0, "seconds": 5}).status_code == 400
        assert client.post("/api/jobs/dreamy/dream", json={"first": 0, "depth": "wild"}).status_code == 400
        assert "Polly" in client.post("/api/jobs/dreamy/dream", json={"first": 4}).json()["detail"]
        r = client.post("/api/jobs/dreamy/dream", json={"first": 1, "seconds": 2, "depth": "deep"})
        assert r.status_code == 200 and r.json()["first"] == 1 and r.json()["last"] == 2 and done.wait(10)
        assert got == {"first": 1, "seconds": 2.0, "depth": "deep"}
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("dreamy", None)


def test_the_desk_offers_dream_here_on_the_timeline():
    drawer = APP.split('if (picked.kind === "shot") {', 1)[1].split("if (s.index < 1)", 1)[0]
    assert "${dreamRow(lane, s, choices)}" in drawer
    row = APP.split("function dreamRow(lane, s, choices) {", 1)[1].split("async function dreamRun", 1)[0]
    assert 'data-act="easy-tl-dream"' in row and 'id="tl-dream-s"' in row and 'id="tl-dream-depth"' in row and "s.performer || s.own" in row
    assert 'postCutEdit(id, "dream", { first: Number(index), seconds, depth }' in APP and 'act === "easy-tl-dream"' in APP
    assert ".shots-lane .overlay.dream" in CSS and '" · dream"' in APP
    choices = lane.choices()
    assert choices["dream_seconds"] == [1, 2, 3] and choices["dream_depths"] == ["light", "deep"]
