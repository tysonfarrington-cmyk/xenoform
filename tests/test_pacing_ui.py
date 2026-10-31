"""The Shape row and the record (docs/MUSIC_VIDEO_PLAN.md section 3): Breathe and the Drops beside Timing in both knob
blocks, plumbed as morph_timing was (the payload, the saved keys, the click, the pending re-cut, the re-cut body, a
recipe), the lane showing the passages by role with a drop's heat and a rest badge, and the Make's line."""
from __future__ import annotations

from pathlib import Path

from xenoform import lane

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")


def test_the_shape_row_sits_beside_timing_in_both_knob_blocks():
    assert APP.count("${shapeRow(easy)}") == 2
    result = APP.split('<div class="energy-head"><h3>Knobs</h3>')[1].split("easy-recut-knobs")[0]
    front = APP.split('<section class="panel span simple-knobs-panel"')[1].split("</section>")[0]
    for block in (result, front):
        assert block.index("timingRow(") < block.index("${shapeRow(easy)}") < block.index("effectsRow(")
    row = APP.split("function shapeRow(easy)")[1].split("\n}\n")[0]
    assert 'chip("easy-breathe", "on", "Breathe"' in row and '"easy-drops"' in row and "DROP_MODES.map" in row
    assert 'const DROP_MODES = ["auto", "max", "off"];' in APP


def test_the_shape_is_plumbed_like_the_timing():
    assert "breathe: breatheValue(state.easy)," in APP and "function breatheValue(easy)" in APP and 'drop_mode: (state.easy && state.easy.dropMode) || "auto",' in APP
    saved = APP.split("const EASY_SAVED_KEYS = [")[1].split("];")[0]
    assert '"breathe"' in saved and '"dropMode"' in saved
    assert 'act === "easy-breathe"' in APP and 'act === "easy-drops"' in APP
    knobs = APP.split("const KNOB_ACTS = {")[1].split("};")[0]
    assert '"easy-breathe": "Breathe"' in knobs and '"easy-drops": "Drops"' in knobs
    recut = APP.split("async function recutWithKnobs()")[1].split("async function easyMake")[0]
    assert "breathe: breatheValue(state.easy)" in recut and 'drop_mode: state.easy.dropMode || "auto"' in recut
    recipe = APP.split("function applySimpleRecipe(recipe)")[1].split("\n}\n")[0]
    assert "easy.breathe = breatheValue({ breathe: recipe.breathe });" in recipe and "easy.dropMode" in recipe
    options = APP.split("async function loadSimpleOptions()")[1].split("\n}\n")[0]
    assert 'breathe: (() => { const b = breatheValue(easy); return b === true ? "on" : b ? String(b) : "off"; })(),' in options and "drop_mode: easy.dropMode" in options
    assert 'stemOrbit: true,\n          // the shape (xenoform.pacing): Breathe off until Tys has judged the sheets, the Drops on Auto\n          breathe: false, dropMode: "auto" },' in APP


def test_the_lane_shows_the_passages_the_heat_and_the_rests():
    shots = [
        {"start": 0.0, "end": 4.0, "section": "intro", "passage": 0},
        {"start": 4.0, "end": 8.0, "section": "intro", "passage": 0, "rest": 4, "rest_s": 2.0},
        {"start": 8.0, "end": 9.0, "section": "drop", "passage": 1, "boundary": "drop", "event": "drop", "drop_run": 0, "heat": 1.0},
        {"start": 9.0, "end": 11.0, "section": "drop", "passage": 1, "drop_run": 0, "heat": 1.0},
        {"start": 11.0, "end": 13.0, "section": "drop", "passage": 2, "boundary": "drop", "event": "drop", "drop_run": 1, "heat": 0.5},
    ]
    info = {"shots": shots, "stills": [f"cosmic/{i:02d}_thing.jpg" for i in range(6)], "clips": ["c"] * 5,
            "pacing": {"breathe": True, "drop_mode": "auto", "line": "2 drops, the main at 0:08; 3 passages; 1 rest"}}
    got = lane.build(info, "v1")
    rows = got["shots"]
    assert rows[1]["rest"] == 4 and rows[1]["rest_s"] == 2.0 and "rest" not in rows[0]
    assert rows[2]["event"] == "drop" and rows[2]["heat"] == 1.0 and rows[4]["drop_run"] == 1
    secs = got["sections"]
    assert [(s["section"], s.get("drop_run")) for s in secs] == [("intro", None), ("drop", 0), ("drop", 1)]  # two runs, two passages
    assert secs[0]["rests"] == 1 and secs[1]["heat"] == 1.0 and secs[2]["heat"] == 0.5
    assert got["plan_line"].startswith("2 drops") and got["breathe"] == 1.0 and got["drop_mode"] == "auto" and got["rests"] == 1
    old = lane.build({"shots": [{"start": 0.0, "end": 2.0, "section": "calm"}, {"start": 2.0, "end": 4.0, "section": "calm"}],
                      "stills": ["a/0_x.jpg", "a/1_y.jpg", "a/2_z.jpg"], "clips": ["c", "c"]}, "v2")
    assert [s["section"] for s in old["sections"]] == ["calm"] and old["breathe"] == 0 and old["drop_mode"] == "off"
    assert old["plan_line"] == ""
    timeline = APP.split("function shotsLane(easy)")[1].split("\nfunction ")[0]
    assert 'class="tl-rest"' in timeline and "lane.plan_line" in timeline and "sec.heat" in timeline


def test_the_make_reports_what_the_plan_did():
    from xenoform import turbo, ui
    import inspect

    assert '"plan_line"' in inspect.getsource(turbo._run_turbo)
    assert 'result.get("plan_line")' in inspect.getsource(ui)


def test_a_loved_chain_comes_back_in_the_shape_it_was_cut_in(tmp_path, monkeypatch):
    """The loved chains (configs/chain_presets.json) were all cut before the Shape row: a preset carries Breathe off with
    Drops off, the legacy cut, so re-made later it comes out as it was; a row may say otherwise, a bad value is off."""
    import json

    from xenoform import pacing, presets

    loved = presets.load()
    assert loved and all((p["breathe"], p["drop_mode"]) == (False, "off") for p in loved)
    assert all(pacing.legacy(presets.body(p)) for p in loved)
    f = tmp_path / "presets.json"
    f.write_text(json.dumps({"presets": [
        {"id": "said", "name": "Said", "vibe": "black", "breathe": True, "drop_mode": "MAX"},
        {"id": "silent", "name": "Silent", "vibe": "black"},
        {"id": "odd", "name": "Odd", "vibe": "black", "breathe": "yes", "drop_mode": "loud"}]}), encoding="utf-8")
    monkeypatch.setenv("XENO_PRESETS", str(f))
    got = {p["id"]: (presets.body(p)["breathe"], presets.body(p)["drop_mode"]) for p in presets.load()}
    assert got == {"said": (True, "max"), "silent": (False, "off"), "odd": (False, "off")}
    apply = APP.split("function applyPreset(id) {", 1)[1].split("function ideaReadingLine(", 1)[0]
    assert "easy.breathe = breatheValue({ breathe: body.breathe });" in apply and 'DROP_MODES.includes(body.drop_mode) ? body.drop_mode : "off"' in apply
    assert "loadSimpleOptions().then(render)" in apply  # the Shape moves the plan: the count and the clock are asked again
