"""One desk (26 Oct, Tys: "get rid of the simple/advanced and combine it into one; the simple can be kept as a
prototyping stage"). The Director desk is gone from the page: one flow of stages (Song, Vibe, Prototype, Refine, Share),
the few Director pieces that changed a cut folded in (the per-shot edits are the timeline's, Polly's own still is in
Fine-tune, the shot list and seed file are in Share, Setup and Connect are tool pages), and the rest removed. These are
string pins against the desk files; tests/test_one_desk_server.py has the server halves."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def _fn(name, until):
    return APP.split(name, 1)[1].split(until, 1)[0]


def test_there_is_no_second_desk():
    for gone in ('id="advanced-toggle"', 'class="views"', 'id="generate"', 'id="review-fix"', 'id="generate-gate"',
                 'id="register-slot"', 'id="reviewslot"', 'id="jobslot"', "data-advanced", 'id="mode-dry"', 'id="mode-live"'):
        assert gone not in INDEX, gone
    assert '<body data-desk="1">' in INDEX
    for gone in ("syncAdvanced", "enterAdvanced", "leaveAdvanced", "renderAdvanced", "railHtml", "renderDirector",
                 "renderNotes", "notesPanel", "morphPanel", "treatmentPanel", "paintRegisters", "runReview",
                 "dataset.advanced", "Director tools", "Xenoform · Simple"):
        assert gone not in APP, gone
    render = _fn("function render() {", "function renderTool(")
    assert 'renderTool(state.view) : renderEasy()' in render
    assert "data-advanced" not in CSS and 'body[data-desk] .comfy-status {' in CSS


def test_old_director_urls_land_on_the_desk():
    view = _fn("function viewFromHash() {", "function setEasyPhase(")
    assert 'if (name === "setup" || name === "connect") return name;' in view and 'return "simple";' in view
    # #director, #notes, #scene, #simple/desk ... are tidied to #simple (Back and the logo then agree)
    assert 'history.replaceState(null, "", "#simple")' in _fn("function easyPhaseFromHash()", "function easyCrumbs(")
    brand = _fn('const brandLink = document.querySelector(".brand");', 'window.addEventListener("hashchange"')
    assert brand.index("history.pushState") < brand.index('setEasyPhase("choose")')  # Back returns to a tool page


def test_the_stage_strip():
    crumbs = _fn("function easyCrumbs(easy) {", "const EASY_SAVED_KEYS")
    assert 'const order = ["song", "vibe", "make", "refine", "share"];' in crumbs
    assert 'make: "Prototype"' in crumbs and 'share: "Share"' in crumbs and '"Refine"' in crumbs
    handler = APP.split('act === "easy-crumb") {', 1)[1].split("} else if", 1)[0]
    assert 'share: "#easy-share"' in handler and 'refine: ".shots-lane, .tl-panel"' in handler


def test_the_prototype_stage():
    assert "const PROTO_S = 30;" in APP and "const PROTO_MAX_S = 45;" in APP
    length = _fn("function easyLength(easy) {", "function easyLengthIsProto(")
    assert "return easySongSeconds() > PROTO_MAX_S ? PROTO_S : 0;" in length
    assert "length_s: easyLength(state.easy)," in APP
    assert "Make a ${esc(String(easyLength(easy)))} s prototype" in APP
    make = _fn("async function easyMake() {", "function placeKey(")
    assert "state.easy.madeLength = easyLength(state.easy);" in make and 'state.easy.madeTier = state.easy.tier || "draft";' in make


def test_the_cut_screen_is_refine_and_share():
    result = APP.split('if (easy.phase === "result" || easy.phase === "showcase") {', 1)[1].split("const preview = easy.vibe", 1)[0]
    assert "${shotsLane(easy)}" in result and "${renderRow(easy)}" in result and "shareRow(easy)" in result
    assert 'id="easy-guard"' in result and "guardDetails(state.job)" in result
    assert 'id="energy"' not in result  # the Energy slider re-cut the Director storyboard, never the video
    assert 'data-act="easy-advanced"' not in APP
    share = _fn("function shareRow(easy) {", "function renderRow(easy)")
    for item in ("Share cut · 720p", "15 s hook", "Copy recipe code", "/api/jobs/${job}/notes", "/api/jobs/${job}/seed", "vjUrl()"):
        assert item in share, item
    render_row = _fn("function renderRow(easy) {", "function renderEasy()")
    assert 'data-act="easy-render-full"' in render_row and 'data-act="easy-render-final"' in render_row
    handler = APP.split('act === "easy-render-full" || act === "easy-render-final") {', 1)[1].split("} else if", 1)[0]
    assert "state.easy.lengthS = 0;" in handler and 'state.easy.tier = "final";' in handler and "easyMake()" in handler
    # Download is the file at full size; Share cut is the 720p copy (Download used to be that copy too)
    download = APP.split('act === "easy-download") {', 1)[1].split("} else if", 1)[0]
    assert "/api/videos/${encodeURIComponent(id)}/video" in download and "shareCut(" not in download


def test_the_make_body():
    body = _fn("function payload() {", "function vjUrl()")
    assert "scene_transitions:" not in body  # the engine never read them; the guard reported a line a boundary from them
    assert len(re.findall(r"\bend_card:", body)) == 1  # the Director's text copy overwrote the End card switch
    assert 'mode: "simple",' in body and 'hero_id: state.heroId || ""' in body
    generate = _fn("async function generate() {", "async function poll(")
    assert "showGate" not in generate and "storyApproved" not in generate


def test_the_menu_and_settings():
    menu = INDEX.split('class="more-menu"', 1)[1].split("</details>", 1)[0]
    for item in ('data-hash="setup"', 'data-hash="connect"', 'id="open-settings"', 'id="guard-expert"',
                 'id="copy-diagnostics"', 'href="/judges"', 'id="open-about"', 'id="reset-tutorial"'):
        assert item in menu, item
    assert "Dry run" not in INDEX.split('<dialog id="settings">', 1)[1].split("</dialog>", 1)[0]


def test_polly_takes_your_own_still_in_fine_tune():
    row = _fn("function performerRow(easy) {", "function ownRow(easy)")
    assert 'id="hero-file"' in row and 'data-act="easy-hero-clear"' in row
    assert "Cast lock" not in row
    assert 'act === "easy-hero-clear"' in APP and "uploadHero(target.files[0])" in APP


def test_guardrail_lines_fold():
    paint = _fn("function guardDetails(job) {", "function guardLines(")
    assert "guardLines(" in paint and 'id="easy-guard"' in APP
    fold = APP.split("function guardLines(messages)", 1)[1].split("\n}\n", 1)[0]
    assert "(× ${n})" in fold and "flag${at.length === 1" in fold


def test_duplicate_names_are_gone():
    # a second kindLabel (the review panel's) overrode the timeline's, so every hand-picked boundary read "Board fix";
    # a second copyText returned nothing, so "Copy recipe code" never said it had copied
    assert len(re.findall(r"^function kindLabel\(", APP, re.M)) == 1 and "function kindLabel(lane, id)" in APP
    assert len(re.findall(r"^async function copyText\(", APP, re.M)) == 1
    names = re.findall(r"^(?:async )?function ([A-Za-z_$][\w$]*)\(", APP, re.M)
    assert len(names) == len(set(names)), sorted({n for n in names if names.count(n) > 1})


def test_a_failed_render_says_why_and_the_side_column_scrolls():
    poll = _fn("async function poll(id) {", 'document.addEventListener("click"')
    assert "The render stopped: ${why}" in poll
    assert "body[data-desk] .easy-side { max-height: calc(100vh - 32px); overflow-y: auto;" in CSS


def test_render_at_final_keeps_the_prototypes_chain():
    # the pick favours the least-used stills, so a fresh Final could morph through other objects than the prototype
    # you approved (27 Oct, found making the tutorial): Final pins every slot of the cut's chain first
    handler = APP.split('act === "easy-render-full" || act === "easy-render-final") {', 1)[1].split("} else if", 1)[0]
    assert "lane.stills.filter((s) => s && s.file && s.index != null)" in handler
    assert "state.easy.pins[String(s.index)] = s.file;" in handler
    assert handler.index("state.easy.pins") > handler.index('state.easy.tier = "final";')  # the whole song is not pinned
    assert "Final keeps this cut's objects in the same order" in APP
