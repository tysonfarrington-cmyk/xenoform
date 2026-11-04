"""Round 0 of the UI review (docs/UI_REVIEW.md, section 7): the fixes that stand whatever the redesign. Each test names
the finding it closes. The behaviour tests run the desk's own functions, cut out of app.js by name, in node against
small stand-ins for the DOM, the URL and the desk's API."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")

NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node runs the desk's functions")


def _fn(name: str) -> str:
    """One function of app.js by name, from its keyword to the closing brace at the start of a line."""
    for prefix in (f"async function {name}(", f"function {name}("):
        if prefix in APP:
            return prefix + APP.split(prefix, 1)[1].split("\n}\n", 1)[0] + "\n}"
    raise AssertionError(f"app.js has no function {name}")


def _const(name: str) -> str:
    """One top-level ``const`` line of app.js."""
    return f"const {name} = " + APP.split(f"\nconst {name} = ", 1)[1].split("\n", 1)[0]


def _obj(name: str) -> str:
    """One top-level ``const`` object of app.js that spans lines (to its closing brace at the start of a line)."""
    return f"const {name} = " + APP.split(f"\nconst {name} = ", 1)[1].split("\n}", 1)[0] + "\n};"


def _run(tmp_path: Path, code: str) -> dict:
    script = tmp_path / "harness.js"
    script.write_text(code, encoding="utf-8")
    done = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


# A browser's URL, history and localStorage, and the desk's state, for the functions under test.
STAGE = r"""
let store = {};
const localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; } };
const location = { hash: "" };
const moves = [];
const history = {
  pushState: (_a, _b, h) => { location.hash = h; moves.push(["push", h]); },
  replaceState: (_a, _b, h) => { location.hash = h; moves.push(["replace", h]); },
};
let state = null;
let easyTimer = null;
const setInterval = () => 1;
const clearInterval = () => {};
const calls = [];
const render = () => calls.push(["render"]);
const tickEasy = () => {};
const esc = (s) => String(s);
const media = (s) => s;
const clockText = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const vibeById = (id) => (id ? { id, name: id } : null);
const easyProgressText = (job) => String((job && job.detail) || "");
"""


# ---------------------------------------------------------------- N3, N4: the URL names the job and the cut
def test_the_url_names_the_job_and_the_cut():
    setter = _fn("setEasyPhase")
    assert "#simple/${phase}${id ? `/${encodeURIComponent(id)}` : \"\"}" in setter
    assert 'history.pushState(null, "", want)' in setter and 'history.replaceState(null, "", want)' in setter
    assert "keepMaking(id)" in setter and "dropMaking()" in setter
    assert 'reopenCut(cut, { fromUrl: true })' in _fn("easyPhaseFromHash")
    boot = _fn("boot")
    assert boot.index("urlTarget()") < boot.index("await loadSetup()")  # the job is asked about before the first full draw
    assert "await resumeMaking(target.id || kept.id, kept, false)" in boot and "await resumeMaking(kept.id, kept, true)" in boot
    gen = _fn("generate")
    assert gen.index("state.job.id = data.id;") < gen.index('setEasyPhase("making")') < gen.index("poll(data.id)")
    # video-open and a cut's URL open a cut the one way
    assert "reopenRow(row);" in APP.split('act === "video-open"')[1].split("} else if")[0]


@NODE
def test_set_easy_phase_keeps_the_job_and_the_cut_in_the_url(tmp_path):
    code = STAGE + "\n".join([_fn("setEasyPhase"), _fn("easyVideoId"), _const("MAKING_KEY"), _fn("keepMaking"), _fn("keptMaking"),
                              _fn("dropMaking")]) + r"""
const out = {};
state = { job: { id: "j1", status: "running" }, easy: { phase: "result", startedAt: 1000, recutting: true, making: { title: "Re-cutting" } } };
setEasyPhase("making");
out.making = { hash: location.hash, kept: JSON.parse(store["xeno-making"] || "null") };
state.job = { id: "j1", status: "done" };
setEasyPhase("result");
out.result = { hash: location.hash, kept: store["xeno-making"] || null, move: moves[moves.length - 1][0] };
state.job = { id: "old", status: "done" };
state.easy.reopenId = "";
setEasyPhase("making");  // a Make before its job has an id: the old cut's id never rides in the URL
out.before = { hash: location.hash, kept: store["xeno-making"] || null };
state.easy.reopenId = "cut9";
setEasyPhase("result");
out.reopened = location.hash;
setEasyPhase("choose");
out.choose = location.hash;
console.log(JSON.stringify(out));
"""
    got = _run(tmp_path, code)
    assert got["making"]["hash"] == "#simple/making/j1"
    kept = got["making"]["kept"]
    assert kept["id"] == "j1" and kept["at"] == 1000 and kept["recut"] is True and kept["making"] == {"title": "Re-cutting"}
    assert got["result"] == {"hash": "#simple/result/j1", "kept": None, "move": "push"}
    assert got["before"] == {"hash": "#simple/making", "kept": None}
    assert got["reopened"] == "#simple/result/cut9" and got["choose"] == "#simple"


@NODE
def test_a_reload_of_the_making_screen_takes_the_job_up_again(tmp_path):
    """N3: the page said "You can leave this page", and a reload orphaned the job; now boot asks the desk about it."""
    code = STAGE + "\n".join([_fn("setEasyPhase"), _fn("easyVideoId"), _const("MAKING_KEY"), _fn("keepMaking"), _fn("keptMaking"),
                              _fn("dropMaking"), _fn("resumeMaking")]) + r"""
let answer = null;
const api = async (path) => { calls.push(["api", path]); return answer; };
const poll = (id) => calls.push(["poll", id]);
const reopenCut = (id, opts) => calls.push(["reopen", id, opts || {}]);
const easyPhaseFromHash = () => { state.easy.phase = "choose"; calls.push(["fromHash"]); };
const fresh = () => { calls.length = 0; store = {}; state = { job: null, easy: { phase: "song", note: "" } }; };
const kept = { id: "j1", at: 5000, recut: true, making: { title: "Re-rendering shot 4" }, reopenId: "j1", reopenUrl: "/api/videos/j1/video", madeTier: "draft" };
const out = {};
(async () => {
  fresh();
  answer = { ok: true, status: 200, json: async () => ({ id: "j1", status: "running", stage: "restyle", detail: "Morph 1 of 2" }) };
  await resumeMaking("j1", kept, false);
  out.running = { phase: state.easy.phase, hash: location.hash, job: state.job.id, at: state.easy.startedAt, recut: state.easy.recutting,
                  title: state.easy.making.title, reopenId: state.easy.reopenId, note: state.easy.note, polled: calls.filter((c) => c[0] === "poll"),
                  kept: JSON.parse(store["xeno-making"]).id };
  fresh();
  answer = { ok: true, status: 200, json: async () => ({ id: "j1", status: "done" }) };
  await resumeMaking("j1", kept, false);
  out.done = calls.filter((c) => c[0] === "reopen");
  fresh();
  answer = { ok: false, status: 404, json: async () => ({ detail: "No such cut." }) };
  await resumeMaking("j1", kept, false);
  out.gone = calls.filter((c) => c[0] === "reopen");
  fresh();
  answer = { ok: true, status: 200, json: async () => ({ id: "m2", status: "error", error: "GPU out of memory." }) };
  await resumeMaking("m2", { id: "m2", at: 1 }, false);
  out.failed = { phase: state.easy.phase, note: state.easy.note, hash: location.hash };
  fresh();
  answer = { ok: true, status: 200, json: async () => ({ id: "j1", status: "error", error: "The re-render did not run." }) };
  await resumeMaking("j1", kept, false);
  out.editFailed = calls.filter((c) => c[0] === "reopen");
  fresh();
  answer = { ok: true, status: 200, json: async () => ({ id: "j1", status: "done" }) };
  await resumeMaking("j1", kept, true);  // the desk opened at #simple: only a running job comes back
  out.quiet = { calls: calls.map((c) => c[0]), phase: state.easy.phase };
  console.log(JSON.stringify(out));
})();
"""
    got = _run(tmp_path, code)
    r = got["running"]
    assert r["phase"] == "making" and r["hash"] == "#simple/making/j1" and r["job"] == "j1" and r["at"] == 5000 and r["recut"] is True
    assert r["title"] == "Re-rendering shot 4" and r["reopenId"] == "j1" and r["note"] == "Morph 1 of 2" and r["polled"] == [["poll", "j1"]]
    assert r["kept"] == "j1"
    assert got["done"] == [["reopen", "j1", {"fromUrl": True}]]  # finished meanwhile: its cut
    assert got["gone"][0][1] == "j1" and "the desk restarted" in got["gone"][0][2]["missing"]
    assert got["gone"][0][2]["note"] == "The desk restarted before the edit finished: the cut is as it was."
    assert got["failed"] == {"phase": "choose", "note": "The render stopped: GPU out of memory.", "hash": "#simple"}
    assert got["editFailed"][0][2]["note"] == "The edit stopped: The re-render did not run."  # an edit: back to its cut
    assert got["quiet"] == {"calls": ["api", "fromHash"], "phase": "choose"}


@NODE
def test_a_cuts_url_reopens_it_with_its_facts_and_its_waiting_edits(tmp_path):
    """N4: #simple/result/<id> on a reload or a shared link opens that cut as its My videos row does, never Choose a
    song; a cut the gallery does not list opens from its folder; one that is not on this desk says so; the edits that
    waited for Apply come back."""
    code = STAGE + "\n".join([_fn("setEasyPhase"), _fn("easyVideoId"), _const("MAKING_KEY"), _fn("keepMaking"), _fn("keptMaking"),
                              _fn("dropMaking"), _fn("reopenRow"), _fn("rowFacts"), _fn("reopenCut"), _const("EDITS_KEY"),
                              _fn("keptEdits"), _fn("easyPhaseFromHash"), _fn("hashId")]) + r"""
let shots = {};
const api = async (path) => { calls.push(["api", path]); const id = path.split("/")[3]; return { ok: !!shots[id], status: shots[id] ? 200 : 404 }; };
let gallery = [];
const loadVideos = async () => { calls.push(["loadVideos"]); state.videos = gallery; };
const fresh = (hash) => { calls.length = 0; location.hash = hash; state = { job: null, videos: null, easy: { phase: "song", note: "", vibe: "" } }; };
const out = {};
(async () => {
  fresh("#simple/result/abc");
  shots = { abc: true };
  gallery = [{ id: "abc", url: "/api/videos/abc/video", vibe: "ferrofluid", tier: "draft", seconds: 529, recipe: "XF1-abc", hook: false }];
  store["xeno-cut-edits"] = JSON.stringify({ id: "abc", tl: { id: "abc", shots: { "3": { play: "hold" } }, bounds: {} }, knobs: { Look: 1 } });
  easyPhaseFromHash();
  out.atOnce = { phase: state.easy.phase, url: state.easy.reopenUrl, job: state.job, restore: state.easy.restoreEdits, knobs: state.easy.knobsTouched };
  await new Promise((r) => setTimeout(r, 0));
  out.facts = { vibe: state.easy.resultVibe, note: state.easy.note, recipe: state.easy.recipe, hash: location.hash };
  fresh("#simple/result/song7");
  shots = { song7: true };
  gallery = [];
  easyPhaseFromHash();
  await new Promise((r) => setTimeout(r, 0));
  out.unlisted = { phase: state.easy.phase, id: state.easy.reopenId, url: state.easy.reopenUrl };
  fresh("#simple/result/nope");
  shots = {};
  easyPhaseFromHash();
  await new Promise((r) => setTimeout(r, 0));
  out.missing = { phase: state.easy.phase, note: state.easy.note, job: state.job, hash: location.hash };
  console.log(JSON.stringify(out));
})();
"""
    got = _run(tmp_path, code)
    a = got["atOnce"]
    assert a["phase"] == "result" and a["url"] == "/api/videos/abc/video" and a["job"]["id"] == "abc" and a["job"]["status"] == "done"
    assert a["restore"] == "abc" and a["knobs"] == {"Look": 1}
    assert got["facts"] == {"vibe": "ferrofluid", "note": "Took 8:49.", "recipe": "XF1-abc", "hash": "#simple/result/abc"}
    assert got["unlisted"] == {"phase": "result", "id": "song7", "url": "/api/videos/song7/video"}
    m = got["missing"]
    assert m["phase"] == "choose" and m["job"] is None and m["hash"] == "#simple" and "not on this desk" in m["note"]


def test_the_lane_gives_back_the_edits_a_reloaded_cut_had_waiting():
    load = _fn("loadLane")
    assert 'state.easy.restoreEdits === id ? keptEdits(id) : null' in load
    assert "kept.tl.id === (state.lane.tl_key || state.lane.id) ? kept.tl : null" in load  # the edits start again otherwise
    keep = _fn("keepEdits")
    assert "timelineDirty(easy, lane) || knobs" in keep and "easy.restoreEdits" in keep  # never written over before the restore
    assert "keepEdits();" in _fn("saveEasy")


# ---------------------------------------------------------------- N1: Escape on the making screen is Stop
def test_escape_on_the_making_screen_is_its_stop_button():
    keys = APP.split('if (event.key === "Escape") {\n    if (touring) return;', 1)[1].split("\n  if (keyTyping(event) || touring) return;", 1)[0]
    assert 'document.querySelector("details.more-menu[open]")' in keys and "menu.open = false;" in keys
    assert "document.querySelector('#app [data-act=\"easy-stop\"]')" in keys and "stop.click();" in keys
    assert "ignoreJob" not in keys and "/cancel" not in keys  # no silent cancel that leaves the screen at making
    assert keys.index("menu.open = false;") < keys.index("stop.click();")  # the menu's own Escape never stops a render


# ---------------------------------------------------------------- N12: Change keeps the song until another is picked
def test_change_keeps_the_song_until_another_is_picked():
    desk = APP.split("function renderEasy() {", 1)[1].split("\nfunction ", 1)[0]
    assert "const changing = songSet && !!easy.changingSong;" in desk
    assert "${changing ? picker : \"\"}`" in desk and ": picker;" in desk  # the row stays, the picker opens under it
    assert 'data-act="easy-song-keep">Cancel</button>' in desk and 'data-act="easy-step" data-step="song">Change</button>' in desk
    change = APP.split('act === "easy-step"')[1].split("} else if")[0]
    assert "state.easy.changingSong = { song: state.easy.song, label: state.easy.songLabel };" in change
    assert 'state.easy.song = ""' not in change  # the song is no longer forgotten at the first click
    assert "state.easy.changingSong = null;" in APP.split('act === "easy-song-keep"')[1].split("} else if")[0]
    for loader in ("useBundledSong", "useDemoSong", "uploadSong"):
        assert "state.easy.changingSong = null;" in _fn(loader), loader
    chip = _fn("useBundledSong")
    assert "state.easy.song = was ? was.song : \"\";" in chip  # a song that fails to load gives the kept one back


# ---------------------------------------------------------------- F1, F7: an edit ends as what it was, on the desk
def _edit_cut(tmp_path, monkeypatch, name="r0-edit"):
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    folder = tmp_path / "jobs" / name
    (folder / "simple").mkdir(parents=True)
    shots = [{"start": i * 2.0, "end": (i + 1) * 2.0, "seconds": 2.0, "morph": i} for i in range(4)]
    (folder / "simple" / "simple.json").write_text(json.dumps({"plan_shots": shots, "shots": shots, "clips": ["c"] * 4,
                                                                "stills": ["v/0.jpg"] * 5, "tier": "draft"}), encoding="utf-8")
    (folder / "xenoform.mp4").write_bytes(b"old")
    return client, ui_mod, folder


def _settle(client, job_id, until, tries=200):
    job = {}
    for _ in range(tries):
        job = client.get(f"/api/jobs/{job_id}").json()
        if until(job):
            return job
        time.sleep(0.02)
    return job


def test_a_failed_edit_is_an_error_with_its_reason_and_the_cut_as_it_was(tmp_path, monkeypatch):
    """F1: a re-cut, swap, re-render, insert or dream that threw came back as done with "...did not run" in its detail,
    so the desk said "Your cut is ready" over the old cut."""
    from xenoform import dense as dense_mod

    client, ui_mod, folder = _edit_cut(tmp_path, monkeypatch)

    def boom(job_dir, shot, **_kw):
        raise RuntimeError("the GPU queue refused the morph")

    def recut_boom(job_dir, overrides=None, report=None, cfg=None):
        raise FileNotFoundError("The cached morphs for this video are gone; render it again.")

    monkeypatch.setattr(dense_mod, "rerender_morph", boom)
    monkeypatch.setattr(dense_mod, "recut_from_cache", recut_boom)
    try:
        assert client.post("/api/jobs/r0-edit/rerender", json={"shot": 1}).status_code == 200
        job = _settle(client, "r0-edit", lambda j: j["status"] != "running")
        assert job["status"] == "error" and job["detail"].startswith("The re-render did not run.") and job["error"] == job["detail"]
        assert job["edit"] == "rerender" and job["edit_from"] == 0 and job["video_version"] == 0  # no new version
        assert job["overall"] is None and job["eta_s"] is None  # none of a Make's clock rides along with an edit (F6)
        assert client.post("/api/jobs/r0-edit/recut", json={}).status_code == 200  # an error is not "still rendering"
        job = _settle(client, "r0-edit", lambda j: j["status"] != "running")
        assert job["status"] == "error" and job["detail"].startswith("Re-cut did not run. ") and job["error"] == job["detail"]
        assert (folder / "xenoform.mp4").read_bytes() == b"old"
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("r0-edit", None)


def test_stop_during_an_edit_takes_its_gpu_work_off_and_never_says_cancelled_early(tmp_path, monkeypatch):
    """F7: Stop during an edit said "cancelled" while the GPU went on and the edit landed anyway. Now the cancel reaches
    the edit's GPU wait (the queued morphs come off ComfyUI, nothing is written) and the job says what really became of it."""
    from xenoform import dense as dense_mod
    from xenoform.turbo import JobCancelled

    client, ui_mod, folder = _edit_cut(tmp_path, monkeypatch)
    waiting, release = threading.Event(), threading.Event()

    def waits_for_stop(job_dir, shot, *, cancel=None, report=None, **_kw):
        waiting.set()
        for _ in range(500):
            if cancel and cancel():
                raise JobCancelled("Cancelled. 1 queued morph removed from the GPU queue.")
            time.sleep(0.01)
        return {}

    def lands_anyway(job_dir, shot, *, cancel=None, report=None, **_kw):
        waiting.set()
        release.wait(5)  # Stop arrives here, after the GPU work: the re-compose goes on
        return {"rerenders": [{"shot": shot}]}

    try:
        monkeypatch.setattr(dense_mod, "rerender_morph", waits_for_stop)
        assert client.post("/api/jobs/r0-edit/rerender", json={"shot": 2}).status_code == 200 and waiting.wait(5)
        answer = client.post("/api/jobs/r0-edit/cancel").json()
        assert answer["status"] == "running" and answer["detail"].startswith("Stopping")  # never "cancelled" while it runs
        job = _settle(client, "r0-edit", lambda j: j["status"] != "running")
        assert job["status"] == "cancelled" and job["detail"] == "Stopped: the re-render did not land, and the cut is as it was."
        assert job["video_version"] == 0 and (folder / "xenoform.mp4").read_bytes() == b"old"
        waiting.clear()
        monkeypatch.setattr(dense_mod, "rerender_morph", lands_anyway)
        assert client.post("/api/jobs/r0-edit/rerender", json={"shot": 2}).status_code == 200 and waiting.wait(5)
        client.post("/api/jobs/r0-edit/cancel")
        release.set()
        job = _settle(client, "r0-edit", lambda j: j["status"] != "running")
        assert job["status"] == "done" and job["video_version"] == 1 and job["edit_from"] == 0
        assert job["detail"] == "Re-render ready. Stop came too late to undo it, so the edit landed."

        def recut(job_dir, overrides=None, report=None, cfg=None):  # a re-cut (no GPU) stops at its next report
            waiting.set()
            for k in range(500):
                report("assemble", 0.6, f"Cutting shot {k % 4 + 1} of 4 to the beat")
                time.sleep(0.01)
            return {}

        waiting.clear()
        monkeypatch.setattr(dense_mod, "recut_from_cache", recut)
        assert client.post("/api/jobs/r0-edit/recut", json={}).status_code == 200 and waiting.wait(5)
        client.post("/api/jobs/r0-edit/cancel")
        job = _settle(client, "r0-edit", lambda j: j["status"] != "running")
        assert job["status"] == "cancelled" and "the re-cut did not land" in job["detail"] and job["video_version"] == 1
    finally:
        release.set()
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("r0-edit", None)


def test_the_cancel_reaches_the_gpu_wait_of_every_edit():
    """The desk's cancel is passed to the Draft pair render (cloud_morph._local_clips takes the queued morphs off
    ComfyUI) by the re-render, the generated run and the swap, and the dream asks it before each frame."""
    from xenoform import dense
    from xenoform.turbo import JobCancelled

    with pytest.raises(JobCancelled):
        dense._render_pairs([{"index": 0, "seconds": 2.0, "render_s": 2, "frames": 48}], [{}, {}], Path("."), {"mock": True},
                            seed=1, vibe="", cfg=None, state={}, cancel=lambda: True)
    src = (ROOT / "src" / "xenoform" / "dense.py").read_text(encoding="utf-8")
    rerender = src.split("def rerender_morph(", 1)[1].split("\ndef ", 1)[0]
    insert = src.split("def insert_generated(", 1)[1].split("\ndef ", 1)[0]
    swap = src.split("def swap_still(", 1)[1].split("\ndef ", 1)[0]
    assert "cancel=cancel)[0]" in rerender and "styles=run_styles, cancel=cancel)" in insert
    assert "seed + m, vibe, client, cancel, state" in swap and swap.index("if cancel and cancel():") < swap.index("rec_path.write_text")
    assert rerender.index("cancel=cancel") < rerender.index('(work / "simple.json").write_text')  # nothing is written first
    dream = (ROOT / "src" / "xenoform" / "dream.py").read_text(encoding="utf-8")
    frames = dream.split("def dream_frames(", 1)[1].split("\ndef ", 1)[0]
    assert "if cancel and cancel():" in frames and "cancel=cancel)" in dream.split("def dream_span(", 1)[1]


# ---------------------------------------------------------------- F2: the grow is a phase, the bar moves through it
PLAN = {"analyze": 3.0, "draft": 6.0, "grow": 0.0, "morphs": 90.0, "performer": 0.0, "cut": 30.0, "card": 0.0, "save": 1.0, "qa": 10.0}


def _timed(plan=None):
    from xenoform import job_timing as jt

    return {"id": "t", "status": "running", "detail": "", **jt.start_fields(dict(plan or PLAN), {"quality_tier": "draft"})}


def test_a_grow_is_a_phase_with_its_own_estimate_and_the_bar_moves_through_it():
    """F2: five minutes of "Growing 13 flowers objects (about 98 s)" sat at 2 % under a countdown that never counted it."""
    from xenoform import job_timing as jt

    job = _timed()
    jt.tick(job, "analyze", 1.0, "Track already analyzed", 3.0)
    jt.tick(job, "animatic", 1.0, "Animatic locked to the track", 9.0)
    jt.tick(job, "restyle", 0.03, "Growing 13 flowers objects for this idea (about 98 s)", 9.0)
    t = job["timing"]
    assert t["phase"] == "grow" and t["plan"]["grow"] == 98.0 and sum(t["weights"].values()) == pytest.approx(1.0)
    assert job["eta_s"] == pytest.approx(98.0 + 90.0 + 30.0 + 1.0 + 10.0, abs=1.0)  # the clock counts the grow
    at_start = job["overall"]
    half = jt.live(job, 9.0 + 49.0)  # half the grow in, and nothing reported
    assert half["overall"] > at_start + 0.15 and half["eta_s"] == pytest.approx(job["eta_s"] - 49.0, abs=2.0)
    grow_end = sum(t["weights"][p] for p in ("analyze", "draft", "grow"))
    late = jt.live(job, 9.0 + 900.0)  # a grow that overruns sits short of its end, never past it
    assert late["overall"] < grow_end and late["overall"] == pytest.approx(grow_end - 0.05 * t["weights"]["grow"], abs=1e-3)
    jt.tick(job, "restyle", 0.05, "14 shots on the beat, 13 morphs (2 s each), no object twice", 120.0)
    assert t["phase"] == "morphs" and job["overall"] >= late["overall"] - 1e-6
    jt.finish(job, 250.0)
    assert [s["phase"] for s in job["stages"]][:4] == ["analyze", "draft", "grow", "morphs"] and job["breakdown"]["grow"] == 111.0
    assert jt.live(job, 300.0) == {}  # nothing to add once done (and an edit, which keeps no timing of its own)


def test_morph_n_of_m_bounds_the_bar_and_a_silent_morph_moves_it_one_step_at_most():
    from xenoform import job_timing as jt

    # morph_pass reports 0.12 + 0.8 n/m: on the Draft range the bar said 100 % at the seventh of 13 morphs
    assert jt.stage_frac("morphs", 0.12 + 0.8 * 7 / 13, "draft", "Morph 7 of 13 · a nautilus into a jellyfish") == pytest.approx(7 / 13)
    assert jt.morph_count("Final: morph 3 of 6 on LTX-2.5") == (3, 6) and jt.morph_count("13 morphs queued on the GPU") is None
    job = _timed()
    jt.tick(job, "restyle", 0.1 + 0.45 * 3 / 13, "Morph 3 of 13 · about 300 s left", 60.0)
    t = job["timing"]
    assert t["stage_frac"] == pytest.approx(3 / 13) and t["step"] == pytest.approx(1 / 13)
    w = t["weights"]
    before = w["analyze"] + w["draft"] + w["grow"]
    moved = jt.live(job, 60.0 + 3.0)  # a few seconds into the fourth morph: the bar moves on
    assert moved["overall"] > job["overall"]
    stuck = jt.live(job, 60.0 + 3000.0)  # a morph that never ends never passes the next morph's mark
    assert stuck["overall"] <= before + w["morphs"] * (4 / 13) + 1e-6


def test_the_job_route_serves_the_moving_bar(tmp_path, monkeypatch):
    from xenoform import job_timing as jt
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    client = TestClient(ui_mod.create_app())
    job = _timed()
    job["t0"] = time.monotonic() - 60.0
    jt.tick(job, "restyle", 0.03, "Growing 2 scenes (a moonlit shore) for your line (about 40 s)", 10.0)
    stored = job["overall"]
    with ui_mod._LOCK:
        ui_mod._JOBS["r0-live"] = job
    try:
        got = client.get("/api/jobs/r0-live").json()
        assert got["overall"] > stored and got["eta_s"] < 40.0 + 90.0 + 30.0 + 1.0 + 10.0
        assert job["overall"] == got["overall"]  # kept, so the next report cannot pull the bar back
    finally:
        with ui_mod._LOCK:
            ui_mod._JOBS.pop("r0-live", None)


# ---------------------------------------------------------------- the client: poll, the edit's end, the refusals
POLL_STAGE = STAGE + r"""
let timers = [];
const setTimeout = (fn) => timers.push(fn);
const drain = async () => { for (let i = 0; i < 50 && timers.length; i++) { const fn = timers.shift(); await fn(); await new Promise((r) => Promise.resolve().then(r)); } };
let ignoreJob = null;
const watchJob = () => {};
const showEasyPreview = () => {};
const paintMaking = () => {};
const paintJob = () => {};
let title = "";
const tabTitle = (t) => { title = t || ""; };
const notifyReady = () => { title = "ready"; };
const document = { getElementById: () => null, querySelector: () => null };
let answers = [];
const api = async (path) => { calls.push(["api", path]); const a = answers.length > 1 ? answers.shift() : answers[0]; if (a === "throw") throw new Error("offline"); return a; };
const reply = (status, body) => ({ ok: status === 200, status, json: async () => body });
"""


def _poll_code(scenario: str) -> str:
    return POLL_STAGE + "\n".join([_fn("setEasyPhase"), _fn("easyVideoId"), _const("MAKING_KEY"), _fn("keepMaking"), _fn("dropMaking"),
                                   _fn("tookBreakdown"), _const("POLL_RETRY_MS"), "const pollMisses = {};",
                                   _fn("poll"), _fn("editEnded"), _fn("lostContact")]) + scenario


@NODE
def test_poll_asks_again_then_says_it_lost_contact_and_stops_the_clock(tmp_path):
    """F4: a non-OK answer or a thrown fetch made poll() return silently; the making screen hung with its clock going."""
    code = _poll_code(r"""
(async () => {
  const out = {};
  state = { job: { id: "j1", status: "running" }, easy: { phase: "making", note: "", making: { kind: "make" } } };
  easyTimer = 7;
  answers = ["throw", reply(500, {}), reply(404, { detail: "No such cut. It may be from before the desk restarted." })];
  await poll("j1");
  await drain();
  out.lost = { lost: state.easy.lost, note: state.easy.note, timer: easyTimer, phase: state.easy.phase, title, asks: calls.filter((c) => c[0] === "api").length };
  state = { job: { id: "j2", status: "running" }, easy: { phase: "making", note: "", making: { kind: "make" } } };
  calls.length = 0;
  answers = ["throw", reply(200, { id: "j2", status: "running", detail: "Morph 1 of 3 · about 70 s left" })];
  await poll("j2");
  await drain();
  out.recovered = { lost: state.easy.lost || null, job: state.job.detail, asks: calls.filter((c) => c[0] === "api").length };
  console.log(JSON.stringify(out));
})();
""")
    got = _run(tmp_path, code)
    lost = got["lost"]
    assert lost["lost"]["id"] == "j1" and lost["timer"] is None and lost["phase"] == "making" and lost["title"] == "Lost contact · Xenoform"
    assert lost["note"].startswith("Lost contact with the desk: No such cut. It may be from before the desk restarted.")
    assert lost["asks"] == 6  # the first ask and five more, with backoff
    assert got["recovered"]["lost"] is None and got["recovered"]["job"].startswith("Morph 1 of 3")


@NODE
def test_an_edit_comes_back_to_the_cut_saying_how_it_ended(tmp_path):
    """F1, F6, F7: a landed edit says so in its own time; a failed or stopped one says why and keeps the cut open."""
    code = _poll_code(r"""
const fresh = () => ({ job: { id: "c1", status: "running" }, lane: { id: "c1" }, easy: { phase: "making", note: "", recutting: true,
  making: { kind: "gpu", title: "Re-rendering shot 2" }, startedAt: Date.now() - 36000, reopenId: "", reopenUrl: "" } });
const end = () => ({ note: state.easy.note, phase: state.easy.phase, status: state.job.status, cut: easyVideoId(), lane: state.lane,
                     recutting: state.easy.recutting, making: state.easy.making, hash: location.hash });
(async () => {
  const out = {};
  state = fresh();
  answers = [reply(200, { id: "c1", status: "done", video_version: 2, edit_from: 1, detail: "Re-render ready" })];
  await poll("c1");
  out.landed = end();
  state = fresh();
  answers = [reply(200, { id: "c1", status: "error", video_version: 1, edit_from: 1, error: "The re-render did not run. ComfyUI is not answering." })];
  await poll("c1");
  out.failed = end();
  state = fresh();
  answers = [reply(200, { id: "c1", status: "cancelled", video_version: 1, edit_from: 1, detail: "Stopped: the re-render did not land, and the cut is as it was." })];
  await poll("c1");
  out.stopped = end();
  state = fresh();  // an older desk reports a failed edit as done with its old version
  answers = [reply(200, { id: "c1", status: "done", video_version: 1, edit_from: 1, detail: "Re-cut did not run. The song file is gone." })];
  await poll("c1");
  out.olderDesk = end();
  console.log(JSON.stringify(out));
})();
""")
    got = _run(tmp_path, code)
    landed = got["landed"]
    assert landed["note"] == "Re-render ready. It took 0:36." and landed["phase"] == "result" and landed["lane"] is None
    assert landed["cut"] == "c1" and landed["hash"] == "#simple/result/c1" and landed["recutting"] is False and landed["making"] is None
    failed = got["failed"]
    assert failed["note"] == "The re-render did not run. ComfyUI is not answering. The cut is as it was."
    assert failed["status"] == "done" and failed["cut"] == "c1" and failed["lane"] == {"id": "c1"}  # the cut stays open, as it was
    assert got["stopped"]["note"] == "Stopped: the re-render did not land, and the cut is as it was." and got["stopped"]["cut"] == "c1"
    assert got["olderDesk"]["note"] == "Re-cut did not run. The song file is gone. The cut is as it was."
    assert "Your cut is ready" not in json.dumps(got)


@NODE
def test_a_finished_make_keeps_the_desks_warning_beside_took(tmp_path):
    """F9: a tier dropped for memory, the cloud fell back: the done line used to replace it with "Took X"."""
    code = _poll_code(r"""
(async () => {
  const out = {};
  for (const [key, detail] of [["tier", "GPU memory: dropped to the 8 GB tier. Cut ready in 526.0s · 13 morphs over 14 objects"],
                               ["plain", "Cut ready in 526.0s · 13 morphs over 14 objects"],
                               ["warning", "Cloud quality did not run (no credits). The free local draft is the cut."]]) {
    state = { job: { id: "m1", status: "running" }, easy: { phase: "making", note: "", making: { kind: "make" } } };
    answers = [reply(200, { id: "m1", status: "done", took_s: 529, breakdown: { morphs: 482, cut: 36 }, detail })];
    await poll("m1");
    out[key] = state.easy.note;
  }
  console.log(JSON.stringify(out));
})();
""")
    got = _run(tmp_path, code)
    assert got["plain"] == "Took 8:49 · morphs 8:02 · cut 0:36."
    assert got["tier"] == "Took 8:49 · morphs 8:02 · cut 0:36. GPU memory: dropped to the 8 GB tier."
    assert got["warning"] == "Took 8:49 · morphs 8:02 · cut 0:36. Cloud quality did not run (no credits). The free local draft is the cut."


@NODE
def test_a_refused_make_says_the_desks_reason(tmp_path):
    """F5: a 429 ("Two cuts are already rendering") was written over by "Playing the pictures", and an unread 500 or a
    thrown fetch left the making screen stuck."""
    code = STAGE + r"""
let answer = null;
const api = async () => { if (answer === "throw") throw new Error("offline"); return answer; };
const paintJob = () => {};
const payload = () => ({});
const poll = () => calls.push(["poll"]);
const setEasyPhase = () => {};
""" + _fn("generate") + r"""
(async () => {
  const out = {};
  for (const [key, a] of [["refused", { ok: false, status: 429, json: async () => ({ detail: "Two cuts are already rendering. Cancel one, or wait." }) }],
                          ["broken", { ok: false, status: 500, json: async () => { throw new Error("not json"); } }],
                          ["offline", "throw"]]) {
    state = { job: null, live: true, quality: "turbo", easy: { phase: "making" } };
    answer = a;
    await generate();
    out[key] = state.job;
  }
  console.log(JSON.stringify(out));
})();
"""
    got = _run(tmp_path, code)
    assert got["refused"]["status"] == "error" and got["refused"]["error"] == "Two cuts are already rendering. Cancel one, or wait."
    assert got["broken"]["error"] == "The desk refused it (HTTP 500)." and got["offline"]["error"] == "The desk did not answer."
    make = APP.split("async function easyMake()")[1].split("\nfunction ")[0]
    assert "The render did not start: ${why}" in make and "const why = String(state.job.error" in make


@NODE
def test_an_edit_has_its_own_clock_title_and_steps_and_one_eta_on_screen(tmp_path):
    """F6: an edit showed the Make's "11:34 elapsed", four ticked steps and "Making the prototype."; F3: two clocks."""
    code = STAGE + "\n".join([_fn("startMaking"), _fn("makingKind"), _fn("makingTitle"), _obj("EDIT_STEPS"), _fn("editStep"),
                              _fn("easyEtaText"), _fn("easyStageWord")]) + r"""
const easyEtaLive = () => 0;
const out = {};
state = { job: { id: "c1", status: "running", stage: "assemble", detail: "Re-cutting from the cached morphs (no GPU)", eta_s: 0, overall: 1 },
          easy: { startedAt: Date.now() - 694000, madeLength: 30 } };
out.makeTitle = makingTitle(state.easy);
startMaking("recut", "Re-cutting");
state.easy.startedAt -= 5000;
out.recut = { title: makingTitle(state.easy), eta: easyEtaText(), step: editStep("recut", state.job) };
state.job.detail = "Cutting shot 11 of 13 to the beat";
out.recutLater = { eta: easyEtaText(), step: editStep("recut", state.job) };
startMaking("gpu", "Re-rendering shot 4");
state.job = { status: "running", stage: "restyle", detail: "Re-rendering shot 4's morph" };
out.gpu = { title: makingTitle(state.easy), eta: easyEtaText(), step: editStep("gpu", state.job) };
console.log(JSON.stringify(out));
"""
    got = _run(tmp_path, code)
    assert got["makeTitle"] == "Making the prototype"
    assert got["recut"] == {"title": "Re-cutting", "eta": "0:05 elapsed · reading the morphs", "step": 0}  # its own clock, never 11:34
    assert got["recutLater"] == {"eta": "0:05 elapsed · cutting to the beat", "step": 1}
    assert got["gpu"] == {"title": "Re-rendering shot 4", "eta": "0:00 elapsed · on the GPU", "step": 0}
    making = APP.split("function renderEasy() {", 1)[1].split("\nfunction ", 1)[0]
    assert "<h2>${esc(makingTitle(easy))}.</h2>" in making and "EDIT_STEPS[makingKind(easy)].map(" in making
    assert "kind !== \"make\" ? editStep(kind, job) :" in _fn("paintMaking")
    for fn in ("postCutEdit", "recutWithKnobs", "swapStill", "easyMake"):
        assert "startMaking(" in _fn(fn), fn
    tick = _fn("tickEasy")
    assert "Number(edit ? job.progress : job.overall)" in tick and "if (state.easy.lost) return;" in tick


def test_the_status_line_keeps_one_clock():
    """F3: the header said "about 5:43 left" and the status line "about 723 s left"."""
    code_fn = _fn("easyProgressText")
    assert "about \\d+ s left" in code_fn
    import re

    pattern = re.compile(r"[\s,·-]*about \d+ s left", re.I)
    assert pattern.sub("", "Morph 3 of 13 · about 723 s left").strip() == "Morph 3 of 13"
    assert pattern.sub("", "Splitting the stems (40 %, about 120 s left)").strip() == "Splitting the stems (40 %)"
    assert pattern.sub("", "Polly drums - about 30 s left").strip() == "Polly drums"
    assert pattern.sub("", "Growing 13 flowers objects for this idea (about 98 s)") == "Growing 13 flowers objects for this idea (about 98 s)"


@NODE
def test_a_gpu_edit_waits_for_the_timeline_edits_pending_apply(tmp_path):
    """N2: a re-render, a morph style, Generate here, Dream here or a swap re-composed from the record and the lane
    then read it again, so the edits waiting for Apply were gone."""
    code = STAGE + _fn("gpuEditWaits") + r"""
let dirty = 0;
const timelineDirty = () => dirty;
const easyVideoId = () => "c1";
state = { lane: { id: "c1" }, easy: { note: "" } };
const out = { clean: gpuEditWaits() };
dirty = 2;
out.waiting = gpuEditWaits();
out.note = state.easy.note;
console.log(JSON.stringify(out));
"""
    got = _run(tmp_path, code)
    assert got["clean"] is False and got["waiting"] is True
    assert got["note"] == ("Apply the 2 timeline edits waiting first (the bar at the bottom): this renders on the GPU from the "
                           "cut as it stands, and would drop them.")
    for fn, call in (("rerenderShot", 'postCutEdit(id, "rerender"'), ("insertRun", 'postCutEdit(id, "insert"'),
                     ("dreamRun", 'postCutEdit(id, "dream"'), ("swapStill", "/swap`")):
        body = _fn(fn)
        assert "if (gpuEditWaits()) return;" in body and body.index("gpuEditWaits()") < body.index(call), fn


def test_stop_during_an_edit_waits_for_the_desk_and_a_make_stops_as_before():
    stop = APP.split('act === "easy-stop") {', 1)[1].split("} else if (act ===", 1)[0]
    edit = stop.split("if (state.easy.recutting && job.status === \"running\" && job.id) {", 1)[1].split("\n    }\n", 1)[0]
    assert "state.easy.stopping = true;" in edit and "/cancel`" in edit and "ignoreJob" not in edit and "setEasyPhase" not in edit
    assert "ignoreJob = job.id;" in stop and 'state.easy.note = "Stopped. Anything still queued on the GPU was cancelled.";' in stop
    assert "state.easy.stopping ? state.easy.note : easyProgressText(job)" in _fn("poll")


# ---------------------------------------------------------------- P1: the player outlives the redraw
@NODE
def test_the_cuts_player_outlives_a_redraw_that_plays_the_same_file(tmp_path):
    """P1: every click rebuilt the cut's screen with its <video>, so a shot click stopped the video, jumped it to 0 and
    buffered the file again."""
    draw = _fn("render")
    assert draw.index("const player = keepPlayer(app);") < draw.index("app.innerHTML") < draw.index("putPlayerBack(app, player);")
    code = _fn("keepPlayer") + _fn("putPlayerBack") + r"""
const video = (src) => ({ src, removed: false, replacedBy: null, getAttribute(k) { return k === "src" ? this.src : null; },
                          remove() { this.removed = true; }, replaceWith(n) { this.replacedBy = n; } });
const app = { node: null, querySelector() { return this.node; } };
const out = {};
const playing = video("/api/videos/abc/video");
app.node = playing;
let kept = keepPlayer(app);
const sameFile = video("/api/videos/abc/video");
app.node = sameFile;
putPlayerBack(app, kept);
out.same = { taken: playing.removed, back: sameFile.replacedBy === playing };
app.node = playing;
kept = keepPlayer(app);
const newVersion = video("/api/videos/abc/video?v=3");
app.node = newVersion;
putPlayerBack(app, kept);
out.other = newVersion.replacedBy;
app.node = null;
out.none = keepPlayer(app);
console.log(JSON.stringify(out));
"""
    got = _run(tmp_path, code)
    assert got["same"] == {"taken": True, "back": True}  # the playing node goes back in the new markup's place
    assert got["other"] is None and got["none"] is None  # another file gets the new node; no player, nothing kept


# ---------------------------------------------------------------- W1: the two whole songs say which they are
def test_the_length_chips_say_which_whole_song_and_run_by_length():
    """W1: "Full song" and "Whole song" were two different things (one Make of the track; the passage queue with its own
    screen and hours of GPU) in a shuffled order (Full song · 60 s · 30 s · Whole song · 15 s)."""
    row = APP.split('simpleSeg("easy-length"', 1)[1].split('"Length")', 1)[0]
    assert '[["15", "15 s"], ["30", "30 s"], ["60", "60 s"], ["0", "Whole song, one cut"], ["song", "Whole song, by passages"]]' in row
    assert '"Full song"' not in APP and "pick Full song" not in APP
    assert "or pick Whole song, one cut here." in _fn("lengthNote") and "The whole song as one cut" in _fn("lengthNote")
    assert all(line.startswith("Whole song, by passages (") for line in
               [part.split("`", 1)[1] for part in _fn("songLengthNote").split("return ")[1:] if "`" in part][:1])
    assert "Fine-tune → Length → Whole song makes it all now, as one cut or by passages." in APP
    song_md = (ROOT / "docs" / "SONG.md").read_text(encoding="utf-8")
    assert "Length → Whole song, by passages" in song_md and "Length Full song" not in song_md


# ---------------------------------------------------------------- L3, L5: nothing on the timeline spends at one click
def _branch(act: str) -> str:
    """The body of one ``act`` branch of the desk's click handler."""
    return APP.split(f'}} else if (act === "{act}") {{', 1)[1].split("\n  } else if (act ===", 1)[0]


def test_a_morph_style_chip_picks_and_only_re_render_spends_gpu():
    """L3: a Morph chip in the Regenerate tab started a GPU re-render on one click."""
    chip = _branch("easy-tl-style")
    assert "rerenderShot" not in chip and "postCutEdit" not in chip and "state.easy.tlStyle = " in chip and "render();" in chip
    button = _branch("easy-tl-rerender")
    assert "state.easy.tlStyle.style" in button and "rerenderShot(i, pick);" in button
    drawer = APP.split("function timelineDrawer(easy, lane, tl, picked) {", 1)[1].split("// Dream this span", 1)[0]
    assert "easy.tlStyle.index === s.index && easy.tlStyle.for === lane.id ? easy.tlStyle.style : ownStyle" in drawer
    assert "Re-render this morph${wantStyle !== ownStyle ? ` as ${esc(morphStyleLabel(wantStyle))}` : \"\"}" in drawer
    assert "state.easy.tlStyle = null;" in _fn("loadLane")  # a pick belongs to the lane it was made on


@NODE
def test_reset_the_timeline_waits_for_apply_and_can_be_undone(tmp_path):
    """L5: Reset the timeline re-cut at once and wiped every saved edit, with no confirm and no undo."""
    reset = _branch("easy-tl-reset")
    assert "applyTimeline" not in reset and "recutWithKnobs" not in reset and "postCutEdit" not in reset
    code = "\n".join([_fn("timelineState"), _fn("canonOverride"), _fn("timelineDirty")]) + r"""
let state = null;
const calls = [];
const render = () => calls.push("render");
const api = () => calls.push("api");
function reset(el) {""" + reset + r"""}
function undo(el) {""" + _branch("easy-tl-reset-undo") + r"""}
state = { lane: { id: "c1", shot_overrides: { "2": { play: "hold" } }, boundary_overrides: {} }, easy: {} };
const tl = timelineState(state.easy, state.lane);
tl.shots["4"] = { look: "noir-glow" };  // an edit waiting for Apply, beside the hold the cut already has
const out = { before: timelineDirty(state.easy, state.lane) };
reset({ dataset: {} });
out.reset = { dirty: timelineDirty(state.easy, state.lane), shots: state.easy.tl.shots, kept: state.easy.tlBeforeReset.shots };
undo({ dataset: {} });
out.undone = { dirty: timelineDirty(state.easy, state.lane), shots: state.easy.tl.shots, kept: state.easy.tlBeforeReset };
out.calls = calls;
console.log(JSON.stringify(out));
"""
    got = _run(tmp_path, code)
    assert got["before"] == 1
    assert got["reset"] == {"dirty": 1, "shots": {}, "kept": {"2": {"play": "hold"}, "4": {"look": "noir-glow"}}}  # the hold's removal waits
    assert got["undone"] == {"dirty": 1, "shots": {"2": {"play": "hold"}, "4": {"look": "noir-glow"}}, "kept": None}
    assert "api" not in got["calls"]  # nothing went to the desk
    lane = _fn("shotsLane")
    assert 'data-act="easy-tl-reset-undo">Undo the reset</button>' in lane and "Apply takes every edit off the cut" in lane
    assert "state.easy.tlBeforeReset = null;" in _fn("loadLane")


# ---------------------------------------------------------------- V9: /vj's shortcuts after a dropdown
@NODE
def test_a_dropdown_picked_with_the_mouse_gives_the_keys_back_on_vj(tmp_path):
    """V9: the key handler skips a focused select and the selects kept the focus, so after one pick every shortcut on
    /vj went dead. A pointer pick now blurs the select; a keyboard step keeps it focused (Chrome fires change on each
    arrow of a closed select, so a plain blur-on-change would break stepping it)."""
    vj = (STATIC / "vj.html").read_text(encoding="utf-8")
    script = vj.split("let pickedSelect=null;", 1)[1].split("\n", 2)
    lines = "let pickedSelect=null;" + script[0] + "\n" + script[1]
    assert "addEventListener('keydown',e=>{if(e.target.tagName==='SELECT')return;" in vj  # the handler is as it was
    code = r"""
const handlers = {};
const addEventListener = (type, fn) => { handlers[type] = fn; };
const select = (id) => ({ id, tagName: "SELECT", blurred: 0, blur() { this.blurred += 1; } });
""" + lines + r"""
const fx = select("fx"), every = select("every");
handlers.pointerdown({ target: fx });
handlers.change({ target: fx });
handlers.change({ target: every });  // stepped with the arrow keys, no pointer
handlers.pointerdown({ target: { tagName: "CANVAS" } });
handlers.change({ target: fx });  // a change after the pointer went elsewhere
console.log(JSON.stringify({ fx: fx.blurred, every: every.blurred }));
"""
    got = _run(tmp_path, code)
    assert got == {"fx": 1, "every": 0}
    record = vj.split("function record(", 1)[1].split("\nfunction ", 1)[0] if "function record(" in vj else ""
    assert "pickedSelect" not in record  # V6 and the recording are the perform-window session's
