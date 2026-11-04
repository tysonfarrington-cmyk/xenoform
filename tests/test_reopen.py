"""A saved cut reopened whole (docs/UI_REVIEW.md N14, N10, N13): a finished Make keeps its guardrail notes beside the cut
(``notes.json``), ``GET /api/videos/{id}/reopen`` gives the job back as the cut's own screen read it (the notes, how long it
took and its breakdown, its tier, the stretch of the song) and registers it with the desk, and ``POST .../song`` loads the
cut's song again so Render works without choosing it; the desk clears a passage's label on a reopen."""
import json
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from xenoform import ui as ui_mod

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")


def _wav(path: Path, seconds: float, sr: int = 22050) -> Path:
    t = np.arange(int(seconds * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t) * (1 + np.sign(np.sin(2 * np.pi * 2 * t))) / 2  # a pulse twice a second
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    yield TestClient(ui_mod.create_app())
    with ui_mod._LOCK:
        for key in [k for k in ui_mod._JOBS if str(k).startswith("re")]:
            ui_mod._JOBS.pop(key, None)
        for key in [k for k in list(dict.keys(ui_mod._AUDIO)) if str(k).startswith("up")]:
            dict.pop(ui_mod._AUDIO, key, None)
        for key in [k for k in list(dict.keys(ui_mod._FEATURES)) if str(k).startswith("up")]:
            dict.pop(ui_mod._FEATURES, key, None)


def _saved_cut(tmp_path: Path, job_id: str = "re1", *, notes: bool = True, audio_id: str = "up1a2b3c4d") -> Path:
    folder = tmp_path / "jobs" / job_id
    (folder / "simple").mkdir(parents=True)
    (folder / "xenoform.mp4").write_bytes(b"cut")
    song = _wav(tmp_path / "uploads" / f"{audio_id}.wav", 8.0)
    (folder / "meta.json").write_text(json.dumps({"simple": True, "audio_id": audio_id, "song": "Glitch Out (30 s cut)",
                                                  "vibe": "neon-noir", "quality_tier": "draft", "aspect": "9:16",
                                                  "recipe": "xf1.abc"}), encoding="utf-8")
    (folder / "simple" / "simple.json").write_text(json.dumps({
        "audio_path": str(song), "window": {"song_start": 2.0, "length_s": 4.0}, "vibe": "neon-noir",
        "taste": {"lines": ["[taste] 1 neon-noir still left out of the pick (no-black-heart-or-dna)"]}}), encoding="utf-8")
    (folder / "took.json").write_text(json.dumps({"took_s": 528.9, "breakdown": {"morphs": 481.5, "cut": 35.7}}), encoding="utf-8")
    if notes:
        ui_mod._write_notes(folder, {"guardrails": {"applied": ["x"], "warnings": [], "messages": [
            "[taste] 1 neon-noir still left out of the pick (no-black-heart-or-dna)", "[qa] 1 chromatic aberration flag at 16.5s"]},
            "detail": "Cut ready in 528.9s"})
    return folder


def test_a_finished_make_keeps_its_guardrail_notes_beside_the_cut(desk, tmp_path, monkeypatch):
    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"the cut")
        on_progress("assemble", 1.0, "Cut ready in 3.0s")
        return {"mode": "simple", "seconds": 3.0, "taste_lines": ["[taste] the opener stays quiet (quiet-opener)"]}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    demo = desk.get("/api/demo").json()
    job_id = desk.post("/api/generate", json={**demo, "tiny": True}).json()["id"]
    for _ in range(200):
        job = desk.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done"
    kept = json.loads((tmp_path / "jobs" / job_id / ui_mod.NOTES_FILE).read_text(encoding="utf-8"))
    assert "[taste] the opener stays quiet (quiet-opener)" in kept["guardrails"]["messages"]
    assert kept["guardrails"]["messages"] == job["guardrails"]["messages"] and kept["detail"] == job["detail"]
    with ui_mod._LOCK:
        ui_mod._JOBS.pop(job_id, None)


def test_reopen_gives_the_cut_back_whole_and_registers_it_with_the_desk(desk, tmp_path):
    _saved_cut(tmp_path)
    got = desk.get("/api/videos/re1/reopen").json()
    job = got["job"]
    assert job["reopened"] is True and job["status"] == "done" and job["took_s"] == 528.9
    assert job["breakdown"] == {"morphs": 481.5, "cut": 35.7} and job["tier"] == "draft" and "path" not in job
    assert job["guardrails"]["messages"][1] == "[qa] 1 chromatic aberration flag at 16.5s"
    song = got["song"]
    assert song == {"audio_id": "up1a2b3c4d", "label": "Glitch Out (30 s cut)", "loaded": False, "bundled": None, "file": True,
                    "window": {"song_start": 2.0, "length_s": 4.0}, "seconds": 8.0}
    assert got["recipe"] == "xf1.abc" and got["vibe"] == "neon-noir" and got["detail"] == "Cut ready in 528.9s"
    # the desk knows the job now: the poll and the timeline's edits find it after a restart
    polled = desk.get("/api/jobs/re1").json()
    assert polled["guardrails"] == job["guardrails"] and polled["breakdown"] == job["breakdown"]
    assert desk.get("/api/videos/nope/reopen").status_code == 404


def test_a_cut_from_before_the_notes_file_reopens_with_its_taste_lines(desk, tmp_path):
    _saved_cut(tmp_path, "re2", notes=False)
    got = desk.get("/api/videos/re2/reopen").json()
    assert got["job"]["guardrails"]["messages"] == ["[taste] 1 neon-noir still left out of the pick (no-black-heart-or-dna)"]


def test_the_cuts_song_loads_again_from_its_record(desk, tmp_path):
    _saved_cut(tmp_path)
    r = desk.post("/api/videos/re1/song")
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["audio_id"] == "up1a2b3c4d" and payload["title"] == "Glitch Out (30 s cut)" and payload["duration"] > 7
    with ui_mod._LOCK:
        assert Path(ui_mod._AUDIO["up1a2b3c4d"]).name == "up1a2b3c4d.wav" and "up1a2b3c4d" in ui_mod._FEATURES
    assert desk.get("/api/videos/re1/reopen").json()["song"]["loaded"] is True
    # a song gone from the machine is said plainly; a shipped song is the chip's to load
    gone = _saved_cut(tmp_path, "re3", audio_id="up9z9z9z9z")
    for p in (tmp_path / "uploads").glob("up9z9z9z9z.*"):
        p.unlink()
    r = desk.post("/api/videos/re3/song")
    assert r.status_code == 404 and "no longer on this machine" in r.json()["detail"]
    meta = json.loads((gone / "meta.json").read_text(encoding="utf-8"))
    (gone / "meta.json").write_text(json.dumps({**meta, "audio_id": "song-glitch-out"}), encoding="utf-8")
    assert desk.post("/api/videos/re3/song").status_code == 409
    assert desk.get("/api/videos/re3/reopen").json()["song"]["bundled"] == "glitch-out"


def test_the_desk_reopens_whole_and_clears_a_passages_label():
    # the merge (integrate-4nov): My videos' Reopen goes through Round 0's reopenCut, whose reopenRow clears the
    # passage label and ends by reopening the cut whole
    opened = APP.split('} else if (act === "video-open") {')[1].split("} else if (act ===")[0]
    assert "reopenCut(row.id);" in opened
    row = APP.split("function reopenRow(row, keepNote) {")[1].split("\n}\n")[0]
    assert 'state.easy.fromSong = "";' in row and row.rstrip().splitlines()[-1].strip().startswith("reopenWhole(row, keepNote);")
    for act in ("easy-showcase", "easy-again"):
        block = APP.split(f'}} else if (act === "{act}") {{')[1].split("} else if (act ===")[0]
        assert 'state.easy.fromSong = "";' in block, act
    fn = APP.split("async function reopenWhole(row, keepNote)")[1].split("async function loadVideos")[0]
    assert "/reopen`" in fn and "tookBreakdown(data.job && data.job.breakdown)" in fn and "loadCutSong(id, data)" in fn
    assert "/song`, { method: \"POST\" }" in fn and "useBundledSong(song.bundled, true)" in fn and "useDemoSong(true)" in fn and "adoptSession(payload)" in fn
    rerender = APP.split('} else if (act === "video-rerender") {')[1].split("} else if (act ===")[0]
    assert "loadCutSong(id)" in rerender and "cardNote" in rerender and "easyMake()" in rerender
    assert "card-note" in APP.split("function galleryPanel()")[1].split("async function loadVideos")[0]


SONG_HARNESS = r"""
// The desk's real loadCutSong, loadSongs, songsRow, songHeld and useBundledSong against a stand-in for the rest of the
// desk: a cut reopened from its URL (#render/<id>) whose song is a bundled one, before the Source step ever read the song
// list (cold), and while that list's fetch is still in flight (the Source step drew its row first).
const fs = require("fs");
const src = fs.readFileSync(__APP__, "utf8").replace(/\r\n/g, "\n");
function fn(start) { const rest = src.slice(src.indexOf(start)); return rest.slice(0, rest.indexOf("\n}\n", 1) + 3); }
const code = [fn("async function loadCutSong(id, info) {"), src.slice(src.indexOf("let songsAsking"), src.indexOf("function songClock(seconds)")),
  fn("function songClock(seconds) {"), fn("function songsRow(easy) {"), fn("function songHeld(easy) {"), fn("async function useBundledSong(id, keepStep) {")].join("\n");
const desk = new Function(code + "\nreturn { loadCutSong, songsRow };")();
const SONGS = [{ id: "ambient", title: "Ambient", seconds: 225.0, feel: "Slow and open" }];
const tick = () => new Promise((r) => setTimeout(r, 1));
let calls = [];
global.api = async (path, init) => {
  calls.push(path);
  await tick();
  if (path === "/api/songs") return { ok: true, json: async () => ({ songs: SONGS }) };
  if (path === "/api/songs/load") { const id = JSON.parse(init.body).id; return { ok: true, json: async () => ({ audio_id: `song-${id}`, title: id }) }; }
  throw new Error("unexpected " + path);
};
global.esc = (s) => String(s);
global.window = { CSS: null };
global.document = { querySelector: () => null, getElementById: () => null };
global.render = () => {};
global.setEasyPhase = (p) => { global.state.easy.phase = p; };
global.adoptSession = (data) => { const previous = global.state; global.state = { audioId: data.audio_id, easy: previous.easy, songs: previous.songs }; };
global.settleCut = async () => {};
global.loadSimpleOptions = async () => {};
global.useDemoSong = async () => {};
const fresh = () => ({ songs: null, audioId: "demo", easy: { song: "", songLabel: "", phase: "result", step: "render", note: "" } });
const info = { song: { audio_id: "song-ambient", bundled: "ambient", label: "Ambient" } };
const end = (ready) => ({ ready, calls: calls.slice(), audioId: global.state.audioId, song: global.state.easy.song, step: global.state.easy.step });
(async () => {
  const out = {};
  global.state = fresh(); calls = [];
  out.cold = end(await desk.loadCutSong("c1", info));
  global.state = fresh(); calls = [];
  desk.songsRow(global.state.easy);  // the Source step drew its row first: the list's fetch is in flight
  out.inFlight = end(await desk.loadCutSong("c1", info));
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the desk's song functions")
def test_a_reopened_cuts_bundled_song_loads_before_the_song_list_was_read(tmp_path):
    """The merge (integrate-4nov, t5 N5/N9): a reload or a link on #render/<id> reopens the cut on Render, where the
    bundled songs' list (loadSongs, read by the Source step's row alone) is still unread, so useBundledSong found no song
    and the cut's song never loaded, its shots off the strip and Render unable to re-render; the same when the row's
    fetch was still in flight. loadCutSong reads the list first, and loadSongs shares the fetch in flight."""
    script = tmp_path / "song.js"
    script.write_text(SONG_HARNESS.replace("__APP__", json.dumps(str(ROOT / "src/xenoform/ui_static/app.js"))), encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    for case in ("cold", "inFlight"):
        got = out[case]
        assert got["calls"] == ["/api/songs", "/api/songs/load"], case  # the list once, then the cut's song
        assert got["ready"] is True and got["audioId"] == "song-ambient" and got["song"] == "ambient", case
        assert got["step"] == "render", case  # a reopened cut's own song keeps Render


RESUME_HARNESS = r"""
// The desk's real resumeMaking, resumeSong, loadCutSong, useBundledSong, useDemoSong, songHeld, cutOnSong and poll (its
// done branch) against a stand-in for the rest of the desk: a reload or a link on #render/<job> while the Make runs.
const fs = require("fs");
const src = fs.readFileSync(__APP__, "utf8").replace(/\r\n/g, "\n");
function fn(start) { const rest = src.slice(src.indexOf(start)); return rest.slice(0, rest.indexOf("\n}\n", 1) + 3); }
const code = ["let easyTimer = null; let ignoreJob = null; const pollMisses = {}; const POLL_RETRY_MS = [];",
  fn("async function resumeMaking(id, kept, quiet) {"), fn("async function resumeSong(id, job) {"), fn("async function loadCutSong(id, info) {"),
  src.slice(src.indexOf("let songsAsking"), src.indexOf("function songClock(seconds)")), fn("function songHeld(easy) {"),
  fn("async function useBundledSong(id, keepStep) {"), fn("async function useDemoSong(keepStep) {"), fn("function cutOnSong(easy) {"),
  fn("async function poll(id) {").replace("async function poll(", "async function realPoll(")].join("\n");
const desk = new Function(code + "\nreturn { resumeMaking, realPoll };")();
const tick = () => new Promise((r) => setTimeout(r, 1));
let calls = [];
let jobAnswer = null;
let songsLoad = true;
let fileSong = false;
let reopenSong = null;
const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const no = (status) => ({ ok: false, status, json: async () => ({ detail: "no" }) });
global.api = async (path, init) => {
  calls.push(path);
  await tick();
  if (path.startsWith("/api/jobs/")) return ok(jobAnswer);
  if (path === "/api/songs") return ok({ songs: [{ id: "ambient", title: "Ambient" }, { id: "other", title: "Other" }] });
  if (path === "/api/songs/load") return songsLoad ? ok({ audio_id: `song-${JSON.parse(init.body).id}`, title: "x" }) : no(500);
  if (path === "/api/demo") return ok({ audio_id: "demo", title: "demo" });
  if (path.endsWith("/reopen")) return ok({ song: reopenSong });
  if (path.endsWith("/song")) return fileSong ? ok({ audio_id: "up1", title: "Glitch Out (30 s cut)" }) : no(404);
  throw new Error("unexpected " + path);
};
global.setInterval = () => 7;
global.clearInterval = () => {};
global.tickEasy = () => {};
global.dropMaking = () => {};
global.easyProgressText = (job) => `progress ${job.stage || ""}`;
global.esc = (s) => String(s);
global.window = { CSS: null };
global.document = { querySelector: () => null, getElementById: () => null };
let draws = 0;
global.render = () => { draws += 1; };
global.setEasyPhase = (p) => { global.state.easy.phase = p; };
global.poll = (id) => calls.push(`poll ${id}`);
global.adoptSession = (data) => { const previous = global.state; global.state = Object.assign({}, previous, { audioId: data.audio_id }); };
global.settleCut = async () => {};
global.loadSimpleOptions = async () => {};
global.watchJob = () => {};
global.notifyReady = () => {};
global.showEasyPreview = () => {};
global.clockText = (s) => `${Math.round(s)}s`;
global.tookBreakdown = () => "";
global.paintMaking = () => {};
global.paintJob = () => {};
global.lostContact = () => {};
const fresh = (audioId, song, label) => ({ songs: null, audioId, job: null, lane: null,
  easy: { song, songLabel: label, phase: "choose", step: "render", note: "", cutSongLabel: "" } });
const view = (extra) => Object.assign({ phase: state.easy.phase, song: state.easy.song, label: state.easy.songLabel, audioId: state.audioId,
  step: state.easy.step, onSong: global.cutOnSongNow(), note: state.easy.note, startedAt: state.easy.startedAt, calls: calls.slice() }, extra || {});
(async () => {
  const out = {};
  global.cutOnSongNow = () => new Function(fn("function cutOnSong(easy) {") + "\nreturn cutOnSong;")()(state.easy);
  const running = (song) => ({ id: "j1", status: "running", stage: "morphs", started: 1000, song });
  const demo = { audio_id: "demo", label: "Bundled demo", bundled: null, file: false };
  const ambient = { audio_id: "song-ambient", label: "Ambient", bundled: "ambient", file: false };
  const upload = { audio_id: "up1", label: "Glitch Out (30 s cut)", bundled: null, file: true };
  // a reload mid-render of a Draft of the bundled demo: the desk boots on the demo's analysis, no song chosen
  global.state = fresh("demo", "", ""); calls = []; jobAnswer = running(demo);
  await desk.resumeMaking("j1", null, false);
  out.empty = view();
  // a link on #render/<job> while another bundled song is on the desk: the job's own song replaces it
  global.state = fresh("song-other", "other", "Other"); calls = []; jobAnswer = running(ambient); songsLoad = true;
  await desk.resumeMaking("j1", null, false);
  out.other = view();
  jobAnswer = { id: "j1", status: "done", took_s: 226, video: "/v" };
  await desk.realPoll("j1");
  out.otherDone = view();
  // an upload whose cut is not on disk yet: its song waits, and the end of the job brings it with the cut
  global.state = fresh("demo", "", ""); calls = []; jobAnswer = running(upload); fileSong = false;
  await desk.resumeMaking("j1", null, false);
  out.uploadRunning = view();
  fileSong = true; reopenSong = upload; jobAnswer = { id: "j1", status: "done", took_s: 226, video: "/v" };
  await desk.realPoll("j1");
  out.uploadDone = view();
  // a bundled song that fails to load: the making screen still runs; the cut later says its song is not on the desk
  global.state = fresh("demo", "", ""); calls = []; jobAnswer = running(ambient); songsLoad = false; reopenSong = ambient;
  await desk.resumeMaking("j1", null, false);
  out.failRunning = view();
  jobAnswer = { id: "j1", status: "done", took_s: 226, video: "/v" };
  await desk.realPoll("j1");
  out.failDone = view();
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the desk's song functions")
def test_a_reload_while_the_make_runs_brings_the_jobs_song_back(tmp_path):
    """The desk walk after the merge (integrate-4nov, gap A): a reload or a link on #render/<job> mid-render came back to
    the making screen with its clock but an empty desk (no song, the strip empty, the head "· the song"), and the cut it
    finished into said "its song is not on the desk" for the bundled demo. GET /api/jobs/<id> now names the job's song and
    resumeMaking loads it as a reopened cut's (loadCutSong), keeping the making screen; poll's done branch brings it when
    it could not load earlier."""
    script = tmp_path / "resume.js"
    script.write_text(RESUME_HARNESS.replace("__APP__", json.dumps(str(ROOT / "src/xenoform/ui_static/app.js"))), encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    e = out["empty"]
    assert e["phase"] == "making" and e["song"] == "demo" and e["label"] == "Bundled demo" and e["audioId"] == "demo"
    assert e["startedAt"] == 1000000 and e["onSong"] is True and e["step"] == "render" and "poll j1" in e["calls"]
    o = out["other"]
    assert o["phase"] == "making" and o["song"] == "ambient" and o["audioId"] == "song-ambient" and o["onSong"] is True
    assert out["otherDone"]["phase"] == "result" and out["otherDone"]["onSong"] is True
    assert not any(c.endswith("/reopen") for c in out["otherDone"]["calls"])  # its song was on the desk already
    u = out["uploadRunning"]
    assert u["phase"] == "making" and u["song"] == "" and u["calls"][-1] == "/api/videos/j1/song"
    ud = out["uploadDone"]
    assert ud["phase"] == "result" and ud["song"] == "file" and ud["audioId"] == "up1" and ud["onSong"] is True
    assert ud["calls"][-2:] == ["/api/videos/j1/reopen", "/api/videos/j1/song"]
    f = out["failRunning"]
    assert f["phase"] == "making" and f["song"] == "" and "did not load" not in f["note"]
    fd = out["failDone"]
    assert fd["phase"] == "result" and fd["onSong"] is False and "did not load" not in fd["note"]
    assert fd["calls"].count("/api/songs/load") == 1  # tried once: the cut's bar then says its song is not on the desk


def test_a_running_jobs_route_names_its_song_and_its_upload_loads_before_the_cut_is_on_disk(desk, tmp_path):
    folder = tmp_path / "jobs" / "re5"
    folder.mkdir(parents=True)
    _wav(tmp_path / "uploads" / "up5a5a5a5a.wav", 6.0)
    (folder / "meta.json").write_text(json.dumps({"simple": True, "audio_id": "up5a5a5a5a", "song": "Glitch Out (30 s cut)"}), encoding="utf-8")
    with ui_mod._LOCK:
        ui_mod._JOBS["re5"] = {"id": "re5", "status": "running", "stage": "morphs", "progress": 0.4,
                               "song": {"audio_id": "up5a5a5a5a", "label": "Glitch Out (30 s cut)", "bundled": None, "file": True}}
    assert desk.get("/api/jobs/re5").json()["song"]["audio_id"] == "up5a5a5a5a"
    r = desk.post("/api/videos/re5/song")
    assert r.status_code == 200, r.text
    assert r.json()["audio_id"] == "up5a5a5a5a"
    with ui_mod._LOCK:
        ui_mod._JOBS["re5"]["status"] = "error"
    assert desk.post("/api/videos/re5/song").status_code == 404  # not running and no cut on disk: not on this machine


def test_a_make_records_its_song_in_the_job(desk, tmp_path, monkeypatch):
    gate = threading.Event()

    def fake(cfg, audio_path, state, out_path, work, on_progress=None, tier_id=None, cancel=None):
        gate.wait(5)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"the cut")
        return {"mode": "simple", "seconds": 1.0}

    monkeypatch.setattr("xenoform.director.run_directed", fake)
    demo = desk.get("/api/demo").json()
    job_id = desk.post("/api/generate", json={**demo, "tiny": True, "song_label": "Bundled demo", "vibe": "none"}).json()["id"]
    try:
        job = desk.get(f"/api/jobs/{job_id}").json()
        assert job["song"] == {"audio_id": "demo", "label": "Bundled demo", "bundled": None, "file": False}
        assert job["vibe"] == "none"  # a resumed Make in a fresh browser ticks Plan (resumeMaking)
    finally:
        gate.set()
        for _ in range(200):
            if desk.get(f"/api/jobs/{job_id}").json()["status"] != "running":
                break
            time.sleep(0.05)
        with ui_mod._LOCK:
            ui_mod._JOBS.pop(job_id, None)
