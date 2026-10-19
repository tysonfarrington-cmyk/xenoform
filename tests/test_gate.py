"""Generate stays put, and a redraw keeps the place on the page."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "xenoform" / "ui_static" / "app.js"


def test_generate_shows_a_checklist_instead_of_scrolling():
    script = APP.read_text(encoding="utf-8")
    generate = script.split("async function generate()", 1)[1].split("async function ", 1)[0]
    assert "scrollIntoView" not in generate
    assert "showGate" in generate
    assert "Story approved" in script
    assert "Test clips" in script
    assert "of 1–2" in script
    page = (ROOT / "src/xenoform/ui_static/index.html").read_text(encoding="utf-8")
    assert 'id="generate-gate"' in page


def test_render_restores_focus_and_scroll():
    script = APP.read_text(encoding="utf-8")
    render = script.split("function render()", 1)[1].split("function mountLive()", 1)[0]
    assert "rememberPlace()" in render
    assert "restorePlace(place)" in render
    assert "preventScroll: true" in script
