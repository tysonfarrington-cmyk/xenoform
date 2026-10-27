"""Variations (27 Oct, from Pause's "Thirty nights. Thirty uploads."): several Drafts of one idea, each varying the
seed, the vibe or the feel, queued one at a time on a free GPU and compared on /variations, any of them at Final after."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from xenoform import batch, idea

ROOT = Path(__file__).resolve().parents[1]
LINE = "a moth, a lantern, a wet street at night, moody and punchy"


def _body(**extra):
    body = {"audio_id": "demo", "vibe": "neon-noir", "idea": LINE, "quality_tier": "final", "paid_cloud": True,
            "cloud_quality": True, "cloud_confirm": "tok", "macros": {"intensity": 0.8, "speed": 0.5, "chaos": 0.3, "glow": 0.25, "stems": {"bass": 0.7}},
            "dance_fx": "noir-glow", "chain_pins": {"0": "neon-noir/061_wet_street.jpg"}, "length_s": 0}
    body.update(extra)
    return body


def test_the_line_splits_into_what_it_shows_and_how_it_feels():
    assert idea.split_feel(LINE) == ("a moth, a lantern, a wet street at night", "moody and punchy")
    assert idea.split_feel("slow and dreamy") == ("", "slow and dreamy")
    assert idea.split_feel("a dark lake, a hard hat") == ("a dark lake, a hard hat", "")  # places and things stay


def test_every_variation_is_a_draft_without_paid_cloud_and_the_first_is_as_set():
    for vary in batch.VARY:
        made = batch.variations(_body(), 3, vary)
        assert [m["k"] for m in made] == [0, 1, 2] and all(m["vary"] == vary and m["kind"] == "draft" for m in made)
        assert all(m["body"]["quality_tier"] == "draft" and not m["body"]["paid_cloud"] and not m["body"]["cloud_quality"]
                   and m["body"]["cloud_confirm"] == "" for m in made)
        first = made[0]["body"]
        assert (first["vibe"], first["idea"], first["macros"], first["dance_fx"]) == ("neon-noir", LINE, _body()["macros"], "noir-glow")
    with pytest.raises(ValueError):
        batch.variations(_body(), 4, "seed")
    with pytest.raises(ValueError):
        batch.variations(_body(), 3, "colour")


def test_seed_variations_are_fresh_rolls_of_the_same_settings():
    made = batch.variations(_body(), 5, "seed")
    assert [m["body"]["seed"] for m in made] == [2727, 3736, 4745, 5754, 6763]
    assert made[0]["label"] == "Seed 2727 (as set)" and made[1]["label"] == "Seed 3736"
    assert all(m["body"]["idea"] == LINE and m["body"]["chain_pins"] == _body()["chain_pins"] for m in made)
    assert batch.variations(_body(seed=11), 3, "seed")[1]["body"]["seed"] == 1020


def test_vibe_variations_walk_the_featured_vibes_and_leave_the_pins_behind():
    from xenoform import vibes

    featured = [v["id"] for v in vibes.featured()]
    made = batch.variations(_body(), 10, "vibe")
    ids = [m["body"]["vibe"] for m in made]
    at = featured.index("neon-noir")
    assert ids[0] == "neon-noir" and ids[1:] == [v for v in featured[at + 1:] + featured[:at]][:9] and len(set(ids)) == 10
    assert made[0]["body"]["chain_pins"] == _body()["chain_pins"] and all(m["body"]["chain_pins"] == {} for m in made[1:])
    assert made[0]["label"].endswith("(as set)") and all(m["body"]["idea"] == LINE for m in made)


def test_feel_variations_swap_the_feel_clause_its_knobs_and_its_look():
    made = batch.variations(_body(), 5, "feel")
    assert [m["label"] for m in made] == ["moody and punchy (your line)", "slow and dreamy", "hard and glitchy", "warm and hazy", "cold and sharp"]
    dreamy, glitchy, warm = made[1]["body"], made[2]["body"], made[3]["body"]
    assert dreamy["idea"] == "a moth, a lantern, a wet street at night, slow and dreamy"
    # the line's own feel moved intensity and glow: back to neutral, then the new feel; the stem gains stay
    assert dreamy["macros"] == {"intensity": 0.5, "speed": 0.25, "chaos": 0.1, "glow": 0.75, "stems": {"bass": 0.7}}
    assert dreamy["dance_fx"] == "auto" and warm["dance_fx"] == "warm-leak" and glitchy["macros"]["chaos"] == 0.75
    # the server reads each line as the desk would: its feel is the clause
    assert idea.read(dreamy["idea"], "neon-noir", llm=False)["feel"]["words"] == ["slow", "dreamy"]
    plain = batch.variations(_body(idea="a moth"), 3, "feel")
    assert plain[0]["label"].startswith("Your line, no feel words") and plain[1]["body"]["idea"] == "a moth, slow and dreamy"
    assert all(idea.read(c, llm=False)["feel"] for c in batch.FEELS)  # every clause is made of feel words


class Fake:
    """A desk: jobs it starts run until the test finishes them; ``gpu`` is what busy() says."""

    def __init__(self):
        self.jobs, self.started, self.gpu, self.refuse = {}, [], "", None

    def start(self, body):
        if self.refuse:
            raise RuntimeError(self.refuse)
        jid = f"job{len(self.started)}"
        self.started.append((jid, body))
        self.jobs[jid] = {"status": "running", "overall": 0.0, "detail": "Morph 1 of 9", "eta_s": 300}
        return jid

    def finish(self, jid, status="done", took=360.0):
        self.jobs[jid].update({"status": status, "took_s": took, "detail": "Cut ready"})


def _runner(tmp_path, fake):
    r = batch.Runner(tmp_path / "batches", start=fake.start, job_of=fake.jobs.get, busy=lambda: fake.gpu,
                     cancel=lambda jid: fake.jobs[jid].update({"status": "cancelled"}))
    r.wake = lambda: None  # the tests step by hand
    return r


def test_the_queue_runs_one_at_a_time_and_only_on_a_free_gpu(tmp_path):
    fake = Fake()
    r = _runner(tmp_path, fake)
    b = r.add(_body(), 3, "seed", seconds=12.0)
    assert b["seconds"] == 12.0 and [i["status"] for i in b["items"]] == ["queued"] * 3
    fake.gpu = "ComfyUI is busy with 1 job from elsewhere: waiting for the GPU."
    assert r.step() == "waiting" and fake.started == []
    assert r.get(b["id"])["items"][0]["status"] == "waiting"
    fake.gpu = ""
    assert r.step() == "started" and len(fake.started) == 1 and fake.started[0][1]["seed"] == 2727
    assert r.step() == "running" and len(fake.started) == 1  # never a second while the first renders
    fake.jobs["job0"].update({"status": "done"})  # the pipeline said done; the QA pass has not written the time yet
    assert r.step() == "running"
    fake.finish("job0")
    assert r.step() == "finished"
    first = r.get(b["id"])["items"][0]
    assert first["status"] == "done" and first["took_s"] == 360.0 and first["job_id"] == "job0"
    assert r.step() == "started" and fake.started[1][1]["seed"] == 3736
    fake.finish("job1", status="error")
    assert r.step() == "finished" and r.get(b["id"])["items"][1]["status"] == "error"
    fake.refuse = "Load a song before generating."
    assert r.step() == "refused" and r.get(b["id"])["items"][2]["detail"] == "Load a song before generating."
    assert r.step() == "idle"
    on_disk = json.loads((tmp_path / "batches" / f"{b['id']}.json").read_text(encoding="utf-8"))
    assert [i["status"] for i in on_disk["items"]] == ["done", "error", "error"]


def test_a_final_queues_after_the_drafts_with_the_chain_pinned(tmp_path):
    fake = Fake()
    r = _runner(tmp_path, fake)
    b = r.add(_body(), 3, "feel")
    r.step()
    fake.finish("job0")
    r.step()
    item = r.add_final(b["id"], 0, {"0": "neon-noir/061.jpg", "1": "neon-noir/064_moth.jpg"})
    assert item["kind"] == "final" and item["of"] == 0 and item["label"] == "Final of moody and punchy (your line)"
    assert item["body"]["quality_tier"] == "final" and item["body"]["chain_pins"] == {"0": "neon-noir/061.jpg", "1": "neon-noir/064_moth.jpg"}
    started = []
    while (what := r.step()) != "idle":
        if what == "started":
            started.append(fake.started[-1][1])
            fake.finish(fake.started[-1][0])
    assert [s["quality_tier"] for s in started] == ["draft", "draft", "final"]  # the Drafts first, then the Final
    with pytest.raises(KeyError):
        r.add_final(b["id"], 9)


def test_cancel_stops_the_rest_and_a_restart_leaves_the_batch_to_resume(tmp_path):
    fake = Fake()
    r = _runner(tmp_path, fake)
    b = r.add(_body(), 3, "seed")
    r.step()
    r.cancel(b["id"])
    assert fake.jobs["job0"]["status"] == "cancelled"
    assert r.step() == "finished"
    assert [i["status"] for i in r.get(b["id"])["items"]] == ["cancelled"] * 3
    b2 = r.add(_body(), 3, "vibe")
    r.step()  # one running when the desk goes down
    again = _runner(tmp_path, Fake())
    items = again.get(b2["id"])["items"]
    assert [i["status"] for i in items] == ["stopped"] * 3 and "Resume" in items[0]["detail"]
    assert again.step() == "idle"  # nothing runs on its own after a restart
    assert [i["status"] for i in again.resume(b2["id"])["items"]] == ["queued"] * 3
    assert again.step() == "started"


def _job(root, name, tier, seconds, took):
    folder = root / name
    (folder / "simple").mkdir(parents=True)
    (folder / "simple" / "simple.json").write_text(json.dumps({"tier": tier, "shots": [{"end": seconds / 2}, {"end": seconds}]}), encoding="utf-8")
    (folder / "took.json").write_text(json.dumps({"took_s": took}), encoding="utf-8")


def test_measured_times_come_from_the_cuts_on_this_machine(tmp_path):
    for i, (s, t) in enumerate([(12, 120), (12, 400), (12, 180), (30, 300), (60, 600)]):
        _job(tmp_path, f"d{i}", "draft", s, t)
    _job(tmp_path, "f0", "final", 12, 7231.9)
    m = batch.measured(tmp_path, 12)
    assert m["draft"]["cuts"] == 5 and m["draft"]["per_s"] == 10.0  # median of 10, 33.3, 15, 10, 10
    assert m["draft"]["eta_s"] == 180  # the cuts near 12 s, not the rate times 12: a short cut has the same fixed costs
    assert batch.measured(tmp_path, 200)["draft"]["eta_s"] == 2000.0  # none near: the rate
    assert m["final"]["latest"] == {"seconds": 12.0, "took_s": 7231.9}
    assert batch.measured(tmp_path / "nothing") == {}


def test_comfy_busy_reads_the_queue_and_waits_when_it_does_not_answer():
    state = {"queue": {"queue_running": [], "queue_pending": []}}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            data = json.dumps(state["queue"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert batch.comfy_busy(url) == ""
        state["queue"] = {"queue_running": [["1"]], "queue_pending": [["2"], ["3"]]}
        assert batch.comfy_busy(url).startswith("ComfyUI is busy with 3 jobs")
    finally:
        server.shutdown()
    assert "not answering" in batch.comfy_busy(url, timeout=0.5)


def test_the_desk_queues_lists_and_finals_variations(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    monkeypatch.setattr(_ui, "work_dir", lambda: tmp_path)
    monkeypatch.setattr(batch.Runner, "wake", lambda self: None)  # nothing renders in a test
    client = TestClient(_ui.create_app())
    assert client.get("/variations").status_code == 200 and "Render this one at Final" in client.get("/variations").text
    assert client.get("/api/batches").json()["batches"] == []
    assert client.post("/api/batches", json={"body": _body(), "count": 4, "vary": "seed"}).status_code == 400
    assert client.post("/api/batches", json={"body": _body(audio_id="gone"), "count": 3, "vary": "seed"}).status_code == 400
    r = client.post("/api/batches", json={"body": _body(), "count": 3, "vary": "feel"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["seconds"] == 12.0 and [i["label"] for i in b["items"]] == ["moody and punchy (your line)", "slow and dreamy", "hard and glitchy"]
    assert all("body" not in i for i in b["items"]) and b["items"][1]["look"] == "auto" and b["items"][1]["knobs"]["glow"] == 0.75
    assert client.get("/api/batches").json()["batches"][0]["id"] == b["id"]
    assert client.post(f"/api/batches/{b['id']}/items/0/final").status_code == 409  # no Draft yet
    # the first Draft lands: its record's stills become the Final's pins
    folder = tmp_path / "jobs" / "aa11bb22"
    (folder / "simple").mkdir(parents=True)
    (folder / "xenoform.mp4").write_bytes(b"")
    (folder / "simple" / "simple.json").write_text(json.dumps({"stills": ["neon-noir/a.jpg", "neon-noir/b.jpg"]}), encoding="utf-8")
    runner = batch.Runner(tmp_path / "batches", start=None, job_of=None, busy=None)
    rec = runner._all()[b["id"]]
    rec["items"][0].update({"status": "done", "job_id": "aa11bb22"})
    runner.save(rec)
    client = TestClient(_ui.create_app())  # a fresh desk reads the batch from disk
    got = client.post(f"/api/batches/{b['id']}/items/0/final")
    assert got.status_code == 200, got.text
    final = got.json()["items"][-1]
    assert final["kind"] == "final" and final["of"] == 0 and final["status"] == "queued"
    saved = json.loads((tmp_path / "batches" / f"{b['id']}.json").read_text(encoding="utf-8"))
    assert saved["items"][-1]["body"]["chain_pins"] == {"0": "neon-noir/a.jpg", "1": "neon-noir/b.jpg"}
    assert client.get(f"/api/batches/{b['id']}").json()["items"][0]["video"] == "/api/videos/aa11bb22/video"
    assert client.post(f"/api/batches/{b['id']}/cancel").json()["items"][-1]["status"] == "cancelled"
    assert client.get("/api/batches/nope").status_code == 404


def test_the_prototype_stage_offers_variations_and_the_page_compares_them():
    js = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    assert "${variationsRow(easy)}" in js
    row = js.split("function variationsRow(easy)")[1].split("async function loadBatchRates")[0]
    assert '"easy-batch-n"' in row and '"easy-batch-vary"' in row and 'data-act="easy-batch"' in row and 'href="/variations"' in row
    fn = js.split("async function easyBatch(button)")[1].split("// ---------------------------------------------------------------- Simple finishing")[0]
    assert '"/api/batches"' in fn and "payload()" in fn and 'state.easy.tier = "draft"' in fn and "await planStory()" in fn
    assert 'act === "easy-batch"' in js and '"batchN", "batchVary"' in js
    page = (ROOT / "src/xenoform/ui_static/variations.html").read_text(encoding="utf-8")
    assert "/api/batches" in page and "/items/${k}/final" in page and "poster" in page and "Measured on this machine" in page
