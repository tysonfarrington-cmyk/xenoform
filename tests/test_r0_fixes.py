"""Round 0 of the UI review (docs/UI_REVIEW.md, section 7): the fixes that stand whatever the redesign. Each test names
the finding it closes. The behaviour tests run the desk's own functions, cut out of app.js by name, in node against
small stand-ins for the DOM, the URL and the desk's API."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

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
