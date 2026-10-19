"""Advanced mode is a step rail. Simple mode stays the one-screen desk."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "xenoform" / "ui_static" / "app.js"
CSS = ROOT / "src" / "xenoform" / "ui_static" / "app.css"


def test_advanced_render_is_a_rail_and_simple_stays_easy():
    script = APP.read_text(encoding="utf-8")
    render = script.split("function render()", 1)[1].split("function mountLive()", 1)[0]
    assert "renderAdvanced()" in render
    assert "renderEasy()" in render
    assert 'data-act="rail"' in script
    for label in ("1 Song", "2 Story", "3 Cast lock", "4 Look", "5 Shots", "6 Morph", "7 Notes & review", "8 Export"):
        assert label in script
    assert "New ·" in script
    assert "on the drop" in script
    assert 'id="morph-panel"' in script
    assert "Guided tours" in script
    assert 'data-tour="song"' in script
    assert "shimmer" not in script


def test_register_band_shows_on_the_look_step():
    css = CSS.read_text(encoding="utf-8")
    assert 'body[data-advanced="1"] #register-slot { display: none; }' in css
    assert 'body[data-advanced="1"][data-step="look"] #register-slot { display: block; }' in css
    assert "shimmer" not in css
