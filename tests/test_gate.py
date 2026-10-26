"""Generate stays put, and a redraw keeps the place on the page."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "xenoform" / "ui_static" / "app.js"


def test_generate_shows_a_checklist_instead_of_scrolling():
    script = APP.read_text(encoding="utf-8")
    generate = script.split("async function generate()", 1)[1].split("async function ", 1)[0]
    assert "scrollIntoView" not in generate
    # one desk (26 Oct): the Director desk's gates (approve the shot list, 1 or 2 test clips) went with it; a Make
    # is the Simple cut, which never rendered the storyboard they guarded
    assert "showGate" not in script and "Story approved" not in script and "Approve 1 or 2 test clips" not in script
    page = (ROOT / "src/xenoform/ui_static/index.html").read_text(encoding="utf-8")
    assert 'id="generate-gate"' not in page and 'id="generate"' not in page


def test_render_restores_focus_and_scroll():
    script = APP.read_text(encoding="utf-8")
    render = script.split("function render()", 1)[1].split("function mountLive()", 1)[0]
    assert "rememberPlace()" in render
    assert "restorePlace(place)" in render
    assert "preventScroll: true" in script
