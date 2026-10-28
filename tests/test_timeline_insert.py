"""Generate 10 s here (26 Oct 2026, docs/TIMELINE.md 1.6): a fresh Draft chain over a span of a finished Simple cut,
picked for the vibe with the Chain row's pins and the cut's own stills left out, inserted as a run of shots that keep
their beat timing (``dense.insert_generated``, ``insert_span``), drawn on the lane as a bar like your own clip, run
by ``POST /api/jobs/{id}/insert``; the desk's Generate here row."""
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import dense, lane

from test_timeline import APP, CSS, ROOT, _cut, _grown, _rec


def test_insert_span_covers_about_the_seconds_asked_in_whole_shots():
    shots = [{"start": i * 2.5, "end": (i + 1) * 2.5, "seconds": 2.5} for i in range(8)]
    assert dense.insert_span(shots, 1, 10.0) == (1, 4)
    assert dense.insert_span(shots, 6, 10.0) == (6, 7)  # never past the end
    assert dense.insert_span(shots, 0, 5.0) == (0, 1)
    assert dense.insert_span(shots, 0, 6.0) == (0, 1) and dense.insert_span(shots, 0, 6.5) == (0, 2)  # whole shots, the nearer total
    shots[3]["performer"] = True
    assert dense.insert_span(shots, 1, 10.0) == (1, 2)  # never into Polly
    with pytest.raises(ValueError, match="Polly"):
        dense.insert_span(shots, 3, 10.0)
    with pytest.raises(ValueError, match="not one of them"):
        dense.insert_span(shots, 8, 10.0)


def test_a_generated_run_renders_fresh_morphs_over_the_span_and_the_lane_draws_it(tmp_path, monkeypatch):
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    fresh = [_grown("cosmic", f"{200 + i}_thing_{i}.jpg", f"thing {i}", cx=0.3 + 0.05 * i) for i in range(6)]
    before = _rec(job)
    old_clips = list(before["clips"])
    n = len(before["plan_shots"])
    pairs = []
    import xenoform.cloud_morph as cm

    real = cm._mock_clips

    def spy(shots, stills, work, w, h):
        pairs.append([s["file"] for s in stills])
        return real(shots, stills, work, w, h)

    monkeypatch.setattr(cm, "_mock_clips", spy)
    reports = []
    rec = dense.insert_generated(job, 2, seconds=6.0, pins={"1": fresh[4]}, report=lambda stage, frac, detail: reports.append(detail))
    ins = rec["inserts"][0]
    first, last = ins["first"], ins["last"]
    k = last - first + 1
    assert first == 2 and k >= 2 and len(ins["stills"]) == k + 1 and len(ins["clips"]) == k
    assert ins["stills"][1] == fresh[4] and ins["pins"] == {"1": fresh[4]}  # the pin held its slot
    assert all(f not in before["stills"] for f in ins["stills"])  # new objects, none of the cut's own
    assert len(set(ins["stills"])) == k + 1 and pairs == [ins["stills"]]
    for q in range(k):
        j = first + q
        assert rec["clips"][j] == ins["clips"][q] and Path(rec["clips"][j]).parent == job / "simple" / "inserts" / "00"
        assert rec["plan_shots"][j]["generated"] == {"insert": 0, "index": q} and "morph" not in rec["plan_shots"][j]
        assert rec["shots"][j]["generated"] == {"insert": 0, "index": q}
        assert rec["plan_shots"][j]["frames"] == before["plan_shots"][j]["frames"]
    assert [c for i, c in enumerate(rec["clips"]) if not first <= i <= last] == [c for i, c in enumerate(old_clips) if not first <= i <= last]
    assert rec["stills"] == before["stills"] and rec["recuts"] == 1 and seen["clips"] == rec["clips"]
    assert any("Generating" in d and "thing" in d for d in reports)
    out = lane.build(rec, "x")
    gen = [r for r in out["shots"] if r.get("generated") == 0]
    assert len(gen) == k and gen[0]["from"] == lane.noun_of(ins["stills"][0]) and gen[0]["to"] == lane.noun_of(ins["stills"][1])
    assert "still" not in gen[0] and gen[0]["handoff"] == "cut" and (gen[1]["handoff"] == "morph" if k > 1 else True)
    assert out["shots"][last + 1]["handoff"] == "cut" if last + 1 < n else True
    bar = [o for o in out["overlays"] if o["kind"] == "generated"]
    assert bar == [{"kind": "generated", "first": first, "last": last, "start": out["shots"][first]["start"], "end": out["shots"][last]["end"],
                    "label": f"Generated · {k} morphs", "insert": 0}]
    assert out["inserts"] == 1
    # a swap and a re-render inside the run are refused; a second run lands in its own folder and skips the first run's stills
    with pytest.raises(ValueError, match="generated run"):
        dense.rerender_morph(job, first)
    with pytest.raises(ValueError, match="generated run"):
        dense.insert_generated(job, first)
    rec2 = dense.insert_generated(job, 0, seconds=3.0)
    assert len(rec2["inserts"]) == 2 and Path(rec2["inserts"][1]["clips"][0]).parent.name == "01"
    assert not set(rec2["inserts"][1]["stills"]) & set(ins["stills"])
    # the record's boundary kinds and the foreshadow treat the run's edges as hard cuts: the recut composed through
    seen.clear()
    dense.recut_from_cache(job, {"boundary_overrides": {str(last + 1): {"fx": "smear"}}} if last + 1 < n else {})
    assert seen["calls"] == 1




def test_the_insert_route_runs_the_run_and_refuses_plainly(tmp_path, monkeypatch):
    from xenoform import dense as dense_mod, ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / "tl-edit"
    (folder / "simple").mkdir(parents=True)
    shots = [{"start": i * 2.0, "end": (i + 1) * 2.0, "seconds": 2.0, "morph": i} for i in range(5)]
    shots[4] = {**shots[4], "performer": True}
    shots[4].pop("morph")
    (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "shots": shots, "clips": ["c"] * 5, "stills": ["v/0.jpg"] * 6,
                                                                "tier": "draft"}), encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"old")
    calls = []
    done = threading.Event()

    def fake_insert(job_dir, first, *, seconds=10.0, pins=None, seed=None, cfg=None, report=None, client=None):
        calls.append(("insert", Path(job_dir).name, first, seconds, pins, seed))
        done.set()
        return {"look": {}, "recuts": 2, "inserts": [{"first": first}]}

    monkeypatch.setattr(dense_mod, "insert_generated", fake_insert)
    try:
        assert client.post("/api/jobs/no-such/insert", json={"first": 0}).status_code == 404
        assert client.post("/api/jobs/tl-edit/insert", json={}).status_code == 400
        assert client.post("/api/jobs/tl-edit/insert", json={"first": 1, "seconds": 99}).status_code == 400
        assert "Polly" in client.post("/api/jobs/tl-edit/insert", json={"first": 4}).json()["detail"]
        r = client.post("/api/jobs/tl-edit/insert", json={"first": 1, "seconds": 5, "pins": {"0": "v/9.jpg"}})
        assert r.status_code == 200 and r.json() == {"id": "tl-edit", "status": "running", "first": 1, "last": 2, "seconds": 5.0}
        assert done.wait(10) and calls[-1] == ("insert", "tl-edit", 1, 5.0, {"0": "v/9.jpg"}, None)
        for _ in range(50):
            job = client.get("/api/jobs/tl-edit").json()
            if job["status"] == "done" and job.get("video_version") == 1:
                break
            time.sleep(0.1)
        assert job["video_version"] == 1 and job["detail"] == "Generated run ready" and job["inserts"] == 1
        with ui_mod._LOCK:
            ui_mod._JOBS["tl-edit"]["status"] = "running"
        assert client.post("/api/jobs/tl-edit/insert", json={"first": 0}).status_code == 409
        with ui_mod._LOCK:
            ui_mod._JOBS["tl-edit"]["status"] = "done"
        (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "clips": ["c"] * 5, "tier": "final"}), encoding="utf-8")
        assert "Final" in client.post("/api/jobs/tl-edit/insert", json={"first": 0}).json()["detail"]
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("tl-edit", None)


def test_the_desk_offers_generate_here_and_the_docs_name_it():
    fn = APP.split("function shotsLane(easy)")[1].split("async function loadLane")[0]
    assert 'data-act="easy-tl-insert"' in fn and 'id="tl-insert-s"' in fn and "async function insertRun" in fn and '"insert"' in fn
    assert "Generate here" in fn and 'act === "easy-tl-insert"' in APP  # in the drawer's Regenerate tab (29 Oct)
    assert ".shots-lane .overlay.generated" in CSS and ".shots-lane .shot.generated" in CSS
    doc = (ROOT / "docs" / "TIMELINE.md").read_text(encoding="utf-8")
    assert "inserts" in doc and "/api/jobs/{id}/insert" in doc and "Generate 10 s here" in doc
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Generate here" in readme and "/api/jobs/{id}/insert" in readme
    unreleased = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 0.3.3")[1].split("## 0.3.2")[0]
    assert "/api/jobs/{id}/insert" in unreleased and "insert_generated" in unreleased
