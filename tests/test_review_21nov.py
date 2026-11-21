"""The 21 Nov review of integrate-4nov (docs/notes/review-21nov.md): one test for each bug the review fixed on the desk
client, the VJ page and the server. The node pack's are in test_comfy_pack_nodes.py, the strip's in test_song_strip.py.

The desk halves are string pins on the scripts, as the rest of the suite pins them, with node where a function can run
alone."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
HOOD = (STATIC / "hood.js").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _fn(start: str, end: str = "\n}\n") -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def _node(script: str) -> dict:
    if not NODE:
        pytest.skip("node is not on this machine")
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# ---------------------------------------------------------------- the desk: an edit kept on the cut's screen
def test_an_in_place_edit_is_not_a_making_screen_and_a_make_does_not_cancel_it():
    # Back, Forward or a step click while a shot rendered again in place turned the phase to "making": poll() then
    # skipped the in-place branch and the block and the panel stayed "rendering" until a reload
    route = _fn("function easyPhaseFromHash() {")
    assert "const inPlace = !!(state.job && state.easy.shotEdit && state.easy.shotEdit.id === state.job.id);" in route
    assert 'const running = !!(state.job && state.job.status === "running") && !inPlace;' in route
    ended = _fn("function editEnded(job) {")
    assert "if (easy.shotEdit) dropShotEdit(easy.shotEdit);" in ended
    drop = _fn("function dropShotEdit(edit) {")
    assert "window.XenoHood.progress(edit.id, null);" in drop and "window.XenoHood.invalidate(edit.id);" in drop
    # a Make pressed meanwhile cancelled the edit and left the cut's id in ignoreJob, so every later edit of it hung
    make = _fn("async function easyMake() {")
    assert "if (state.easy.shotEdit) {" in make and make.index("if (state.easy.shotEdit) {") < make.index("await generate();")
    assert "is rendering again on this cut" in make
    assert "if (ignoreJob === id) ignoreJob = null;" in _fn("async function postCutEdit(id, route, body, detail, at, stage, title, opts) {")
    assert "if (ignoreJob === row.id) ignoreJob = null;" in _fn("function reopenRow(row, keepNote) {")


def test_another_cut_opened_during_an_in_place_edit_does_not_take_the_edits_job():
    poll = _fn("async function poll(id) {")
    guard = poll.split("const away = state.easy && state.easy.shotEdit;")[1].split("state.job = job;")[0]
    assert 'if (away && away.id === id && state.easy.phase !== "making" && easyVideoId() !== id) {' in guard
    assert "dropShotEdit(away);" in guard and "return;" in guard  # before the job is written over the open cut's
    if not NODE:
        pytest.skip("node is not on this machine")
    # easyVideoId with the pieces of state poll() sees: cut A's edit runs, then cut B is reopened
    script = "function easyVideoId(" + APP.split("function easyVideoId(")[1].split("\n}\n")[0] + "\n}\n" + """
let state = { easy: { reopenId: "", recutting: true, shotEdit: { id: "A", shot: 2 } }, job: { id: "A", status: "running" } };
const during = easyVideoId();
state.easy.reopenId = "B"; state.job = { id: "B", status: "done" };
console.log(JSON.stringify({ during, after: easyVideoId() }));
"""
    assert _node(script) == {"during": "A", "after": "B"}  # the guard holds only once the desk is on another cut


def test_a_reload_after_a_stopped_edit_reopens_the_cut_and_its_waiting_edits_survive_the_song():
    # the kept record is dropped when the edit ends, so the job's own ``edit`` says it was an edit of a cut
    resume = _fn("async function resumeMaking(id, kept, quiet) {")
    assert "if (k.recut || job.edit) {" in resume
    from xenoform import ui

    src = Path(ui.__file__).read_text(encoding="utf-8")
    assert '"edit": name, "edit_from": int(job.get("video_version") or 0)' in src  # the field the desk reads
    # the cut's lane, and a read of it on its way, outlive the cut's own song loading: a second read of the lane
    # dropped the edits waiting for Apply that the first had given back
    assert "return { lane: state.lane, stemsLane: state.stemsLane, laneLoading: state.laneLoading };" in _fn("function keepLane() {")
    bundled = APP.split("async function useBundledSong(")[1].split("async function useDemoSong(")[0]
    demo = APP.split("async function useDemoSong(")[1].split("\n}\n")[0]
    for body in (bundled, demo):
        assert "const lane = keepStep ? keepLane() : null;" in body and "if (lane) Object.assign(state, lane);" in body
    assert "const keep = Object.assign(keepLane(), { videos: state.videos, wholeSongs: state.wholeSongs });" in APP


def test_the_strings_that_pointed_at_removed_places_name_the_steps():
    assert "tick the box under Model to run it" not in APP and "choose it again on the first screen" not in APP
    assert "choose it again on Source, then Make." in APP


# ---------------------------------------------------------------- Under the hood
def test_a_running_edit_leaves_the_other_shots_panels_alone_between_its_ticks():
    assert "${esc(s.noun)}${f ?" in HOOD  # a still's name is a file's: escaped like the file beside it
    assert "if (entry.edits && entry.edits.style != null && entry.edits.style !== style) return;" in HOOD
    recipe = {"used": {"prompt": "p", "negative": "n", "seed": 1, "steps": 12, "cfg": 3.0, "frames": 97, "guide_start": 1.0,
                       "guide_end": 1.0, "compression": [18, 18], "style": "melt", "lora": None},
              "preset": {"prompt": "p", "negative": "n", "seed": 1, "steps": 12, "cfg": 3.0, "frames": 97, "guide_start": 1.0,
                         "guide_end": 1.0, "compression": [18, 18], "style": "melt"},
              "differs": {"prompt": False}, "next_seed": 2, "rerender": {"ok": True}, "kind": "morph",
              "cost": {"gpu_s": 60, "recut_s": 30}, "choices": {}, "takes": [], "source": "record", "workflow": "/w.json"}
    script = "\n".join([
        f"const recipe = {json.dumps(recipe)};",
        "global.window = { fetch: async () => ({ ok: true, json: async () => recipe }) };",
        "global.document = { activeElement: null, querySelectorAll: () => [], dispatchEvent: () => {} }; global.CustomEvent = function () {}; global.navigator = {};",
        f"require({json.dumps(str(STATIC / 'hood.js'))});",
        "const mk = () => { const h = { isConnected: true, draws: 0, _html: '', classList: { add() {} }, addEventListener() {}, contains: () => true,",
        "  querySelector: () => null, querySelectorAll: () => [] };",
        "  Object.defineProperty(h, 'innerHTML', { get() { return h._html; }, set(v) { h._html = v; h.draws += 1; } }); return h; };",
        "const other = mk();",
        "(async () => {",
        "  window.XenoHood.mount(other, { jobId: 'c1', shotIndex: 5 });",
        "  await new Promise((r) => setTimeout(r, 30));",
        "  const idle = other.draws;",
        "  window.XenoHood.progress('c1', { shot: 6, progress: 0.1, detail: 'Re-rendering shot 7', status: 'running' });",
        "  const started = other.draws;",
        "  for (let i = 2; i < 9; i += 1) window.XenoHood.progress('c1', { shot: 6, progress: i / 10, detail: 'Re-rendering shot 7', status: 'running' });",
        "  const ticking = other.draws;",
        "  window.XenoHood.progress('c1', null);",
        "  process.stdout.write(JSON.stringify({ idle, started, ticking, ended: other.draws }));",
        "})();",
    ])
    got = _node(script)
    assert got["started"] == got["idle"] + 1  # the edit starting disables its buttons: drawn once
    assert got["ticking"] == got["started"]   # seven more ticks: the panel, a caret in it and an open select are left alone
    assert got["ended"] == got["ticking"] + 1  # and once more when it ends


# ---------------------------------------------------------------- the VJ page
def test_the_vj_pages_knob_pad_recorder_and_dock_fixes():
    ctl = (STATIC / "vj_control.js").read_text(encoding="utf-8")
    vj = (STATIC / "vj.html").read_text(encoding="utf-8")
    face = (STATIC / "midi_map.js").read_text(encoding="utf-8")
    # Switch rate is five steps: with a value to read, soft takeover dropped its knob after 3% of travel, for good
    read = ctl.split("readTarget(t) {")[1].split("targetName(t) {")[0]
    assert 'if (t === "every")' not in read and 'if (t === "intensity") return S.inten;' in read
    # a held look or Blackout is a hold but not a pad's: it no longer lands the transition and seeks the clip again
    assert "H.on((id) => {" in ctl and "if (id != null && padNum(id) == null) return;" in ctl
    # "Saving the take…" is asked before "on", which stays true until the desk has the mp4
    rec = ctl.split('const b = $("recb");')[1].split('$("rec-time").textContent = line;')[0]
    assert rec.index('r.status === "saving" || r.status === "remuxing"') < rec.index("else if (on) line =")
    # the dock is made at load, as t1's page made it, and the button carries its state
    assert 'id="midib" title="L: the MIDI map and Learn" data-xm-toggle data-xm-state="dot" aria-expanded="false"' in vj
    assert "if(!OUT&&XenoMidi.dock)XenoMidi.dock();" in vj
    assert vj.index("if(XenoMidi.dock){const mp=$('midi-panel');if(mp)mp.remove()}") < vj.index("if(!OUT&&XenoMidi.dock)XenoMidi.dock();")
    # an imported map's source type is a string from a file: escaped where it becomes an attribute
    assert 'data-type="${esc(c.type)}"' in face and 'data-type="${esc(e.source.type)}"' in face
    assert 'data-type="${c.type}"' not in face and 'data-type="${e.source.type}"' not in face


def test_soft_takeover_never_holds_a_knob_whose_target_has_no_value_to_read():
    if not NODE:
        pytest.skip("node is not on this machine")
    script = f"const C = require({json.dumps(str(STATIC / 'midi.js'))});" + """
const sweep = (read) => { const tk = new C.Takeover(); let applied = 0, v = 0;
  for (let i = 0; i <= 127; i += 1) { const c = i / 127; const d = tk.decide("k", c, read(v), 0, 1); if (d.apply) { applied += 1; v = c; } }
  return applied; };
const step = (v) => Math.round(v * 4) / 4;  // what the screen showed for Switch rate: one of five steps
console.log(JSON.stringify({ stepped: sweep(step), unread: sweep(() => null) }));
"""
    got = _node(script)
    assert got["stepped"] < 20 and got["unread"] == 128  # the bug, and the fix: no value to read, every move applies


# ---------------------------------------------------------------- the server
def test_an_osc_value_past_float32_is_clamped_and_cannot_silence_the_output():
    pytest.importorskip("pythonosc")
    from pythonosc.osc_message_builder import OscMessageBuilder

    from xenoform import osc_relay

    assert osc_relay._num(1e39) == osc_relay.FLOAT32_MAX and osc_relay._num(-1e300) == -osc_relay.FLOAT32_MAX
    assert osc_relay._num(0.25) == 0.25 and osc_relay._num(float("nan")) is None and osc_relay._num(True) == 1.0
    for value in (1e39, -1e300):  # what python-osc refused, raising at every later update
        b = OscMessageBuilder(address="/xenoform/x")
        b.add_arg(osc_relay._num(value), "f")
        assert b.build().dgram
    relay = Path(osc_relay.__file__).read_text(encoding="utf-8")
    assert "except (ValueError, OverflowError) as exc:" in relay


def test_a_length_set_in_frames_survives_the_next_edit_of_the_shot():
    from xenoform import dense, final_tier

    assert dense._source_seconds(4) == 4 and isinstance(dense._source_seconds(4.0), int) and dense._source_seconds("3") == 3
    for frames in (33, 41, 57, 65, 81):  # a hand-set frame count is 8k + 1; its seconds of source are not whole
        render_s = round((frames - 1) / dense.FPS, 3)
        kept = dense._source_seconds(render_s)
        assert kept == render_s
        assert final_tier.gen_length(float(kept)) == frames  # and the next swap renders the same count, not the 25 or 49 below
        assert final_tier.gen_length(float(int(render_s))) < frames  # what int() made of it
    src = Path(dense.__file__).read_text(encoding="utf-8")
    assert 'int(s.get("render_s") or' not in src and 'int(shot.get("render_s") or' not in src


def test_a_pasted_codes_bad_seed_is_dropped_and_a_negative_shot_has_no_workflow(tmp_path):
    from xenoform import shot_recipe as sr

    got = sr.clean_shot_renders({"0": {"seed": float("nan"), "steps": 12}, "1": {"seed": float("inf")}, "2": {"seed": 7.0}})
    assert got == {"0": {"steps": 12}, "2": {"seed": 7}}  # NaN and infinity raised from int(): a 500 on /api/recipe/decode
    assert math.isnan(float("nan"))
    rec = {"renders": [None, None], "clips": [str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")]}
    assert sr.workflow_of(tmp_path, rec, -1) is None  # shots/-1 answered with the last shot's graph
