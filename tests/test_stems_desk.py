"""Stems mode on the desk (docs/STEMS_MODE.md): the Stems step beside Objects and Your clips, Split stems with its
progress, a row a stem, the estimate a layer at a time, the layers stacked over the timeline, Lay them again."""
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static"


def _js(start: str, end: str) -> str:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    return app.split(start, 1)[1].split(end, 1)[0]


def test_the_desk_offers_stems_beside_objects_and_clips():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    row = _js("function sourceRow(easy) {", "// The Chain row")
    assert '["objects", "Objects"], ["clips", "Your clips"], ["stems", "Stems"]' in row
    body = _js("function payload() {", "function vjUrl()")
    assert '...(stemsMode(state.easy) ? { mode: "stems", layers: stemLayers(state.easy) } : {})' in body
    assert 'mode: "simple",' in body  # every other Make is the Simple cut, as before
    assert '"stemRows"' in app.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0]
    assert "${stemsMode(easy) ? stemsStep(easy) : \"\"}" in app


def test_the_stems_step_splits_with_progress_and_has_a_row_a_stem():
    step = _js("function stemsStep(easy) {", "async function loadStemsMode(")
    assert 'data-act="easy-stems-split"' in step and "stems-progress" in step and "stemRowHtml(easy, r)" in step
    load = _js("async function loadStemsMode(start) {", "function stemsLaneView(")
    assert '"/api/stems/split"' in load and "/api/stems/status?audio_id=" in load and "setTimeout(" in load
    row = _js("function stemRowHtml(easy, r) {", "function stemsStep(easy) {")
    for bit in ('data-act="easy-stem-on"', 'data-act="easy-stem-kind"', 'data-value="clips"', 'class="stem-vibe"',
                'class="stem-folder"', 'class="stem-pro-in"', 'class="stem-blend"', 'data-act="easy-stem-lead"',
                'data-act="easy-stem-chainpins"', "stemSpark(r.envelope"):
        assert bit in row, bit
    layers = _js("function stemLayers(easy) {", "// Why a Stems Make")
    assert "STEM_LAYER_MAX" in layers and "clips_folder" in layers and "layer.pins" in layers
    block = _js("function stemsMakeBlock(easy) {", "// A stem's envelope")
    assert "Split stems" in block and "Cloud Final morphs the library's objects, not your clips yet" in block
    make = _js("async function easyMake() {", "async function easyCloudEstimate")
    assert "stemsMakeBlock(state.easy)" in make


def test_the_estimate_counts_the_layers_and_the_facts_name_them():
    facts = _js("function easyPlanFacts(easy) {", "function easyTimeFact() {")
    assert '"Layers"' in facts and "stemLayers(easy)" in facts
    clock = _js("function easyTimeFact() {", "function tickEasy() {")
    assert "const n = Math.max(1, stemLayers(state.easy).length);" in clock and "n * e.seconds" in clock
    cloud = _js("function cloudFinalRow(easy) {", "async function easyMake() {")  # Cloud's credits a layer at a time, behind the tick
    assert "stemsMode(easy) ? Math.max(1, stemLayers(easy).length) : 1" in cloud and "a layer x ${layers} layers" in cloud
    assert 'data-act="easy-cloud-final-ok"' in cloud


def test_the_cut_screen_stacks_the_layers_and_lays_them_again_without_a_render():
    lane = _js("function shotsLane(easy) {", "// A shot's own colour")
    assert 'lane.mode === "stems" ? stemsLaneBlock(easy, lane)' in lane
    block = _js("function stemsLaneBlock(easy, lane) {", "function stemsMixSet(")
    assert 'data-act="easy-stems-layer"' in block and 'class="stem-mix-pro"' in block and 'class="stem-mix-blend"' in block
    assert 'data-act="easy-stems-relay"' in block and "stemSpark(l.envelope, l.alpha" in block
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    relay = app.split('act === "easy-stems-relay") {', 1)[1].split("} else if", 1)[0]
    assert 'postCutEdit(id, "composite"' in relay
    apply = _js("async function applyTimeline() {", "// Re-render one shot's morph")
    assert 'if (lane.mode === "stems") body.layer = lane.layer;' in apply
    knobs = _js("async function recutWithKnobs() {", "// Cloud Final:")
    assert 'body.layer = cutLane.layer' in knobs
    tl = _js("function timelineState(easy, lane) {", "function canonOverride(")
    assert "lane.tl_key || lane.id" in tl
    assert 'lane.mode === "stems") return ""' in _js("function dreamRow(lane, s, choices) {", "async function dreamRun(")
    load = _js("async function loadLane(id) {", "function easyVideoId()")
    assert "stemsLaneView(state.stemsLane" in load
    css = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert ".stem-row {" in css and ".stem-lane-row {" in css and ".stems-progress span" in css


def test_the_recut_route_passes_a_layer_and_the_stems_routes_come_first():
    ui_src = (Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui.py").read_text(encoding="utf-8")
    assert '"layer", "prominence", "blend") if k in body}' in ui_src
    assert ui_src.index("app.include_router(stems_mode_router)") < ui_src.index("app.include_router(stems_router)")
