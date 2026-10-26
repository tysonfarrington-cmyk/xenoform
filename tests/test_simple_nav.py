"""Simple mode navigation (24 Oct 2026): one phase setter with the phase in the URL, a Back button first on the
result and showcase screens, the showcase as its own phase, the Song > Vibe > Make > Video strip, Fine-tune in
the main column, rows that wrap instead of crushing, the VJ link carrying the song, and the Desk link back."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
VJ = (STATIC / "vj.html").read_text(encoding="utf-8")


def test_one_phase_setter_keeps_the_url():
    assert "function setEasyPhase(" in APP and "function easyPhaseFromHash(" in APP
    assert 'history.pushState(null, "", want)' in APP and 'history.replaceState(null, "", want)' in APP
    # every phase write goes through the setter: only the two "vibe" writes on the choose screen remain literal
    literal = [line for line in APP.splitlines() if "state.easy.phase = " in line]
    assert len(literal) == 7, literal
    assert sum(1 for line in literal if '"vibe"' in line) == 2
    assert 'easyPhaseFromHash();' in APP  # on hashchange (Back / Forward) and at boot


def test_back_button_and_showcase_phase():
    head = APP.split('<div class="easy-result-actions">')[1].split("</div>")[0]
    assert 'data-act="easy-again"' in head.split("\n")[1]  # Back is the first action in the result head
    assert "Showcase · made earlier" in APP and 'setEasyPhase("showcase")' in APP
    assert "function showcaseAside(" in APP and "Make your own" in APP
    assert 'easy.phase === "result" || easy.phase === "showcase"' in APP
    assert "cuts your own in about 1 minute" not in APP  # the stale promise is gone


def test_breadcrumb_on_every_simple_screen():
    assert "function easyCrumbs(" in APP
    # since 27 Oct the strip lives in the toolbar (index.html #stage-slot), painted by render() on every screen
    render = APP.split("function render() {", 1)[1].split("function renderTool(", 1)[0]
    assert 'document.getElementById("stage-slot")' in render and "easyCrumbs(" in render
    assert APP.count("${easyCrumbs(easy)}") == 0
    assert 'data-act="easy-crumb"' in APP and 'act === "easy-crumb"' in APP
    assert ".easy-crumbs" in CSS


def test_fine_tune_in_the_main_column_and_rows_that_wrap():
    main = APP.split('<section class="easy-main">')[1].split("</section>\n    <aside")[0]
    assert "${fineTune(easy)}" in main
    assert ".simple-seg .toggle button { flex: 1 1 auto; min-width: max-content; white-space: nowrap; }" in CSS
    assert ".look-row .toggle .chip {" in CSS and ".simple-opts .look-row .toggle .chip" not in CSS
    assert ".easy-result-actions, .easy-make-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }" in CSS
    assert "@media (max-width: 1000px)" in CSS
    assert '[["draft", "Draft"], ["final", "Final"]]' in APP  # short tier chips; the model names live in the note


def test_honest_clock_and_took():
    assert "function easyPlanEta(" in APP and "easyPlanEta() || easyEtaGuess()" in APP
    assert "job.overall" in APP and "job.eta_s" in APP and "elapsed ·" in APP
    assert "function tookBreakdown(" in APP and "Took ${clockText(took)}" in APP
    assert "Math.min(0.95, elapsed / easyEtaLive())" not in APP  # the 95 % pin is gone


def test_vj_links_both_ways_and_state_persists():
    assert 'href="${esc(vjUrl())}" target="_blank" rel="noopener">VJ mode' in APP
    assert 'id="desk-link" href="/#simple"' in VJ
    assert 'localStorage.setItem("xeno-easy"' in APP and "loadEasy()" in APP
    assert 'body[data-advanced="0"] #open-about' not in CSS  # About is reachable in Simple
