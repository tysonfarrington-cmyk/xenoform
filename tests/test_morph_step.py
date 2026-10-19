"""The Morph step shows a source clip, a beat mark, and a QA chip. Simple has no morph control."""

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "app.js"
CSS = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "app.css"


def test_morph_step_has_a_source_a_mark_and_a_qa_chip():
    script = APP.read_text(encoding="utf-8")
    assert "morph-source" in script
    assert "tl-mark" in script
    assert "QA · " in script
    assert "New ·" in script
    easy = script.split("function renderEasy()", 1)[1].split("function placeKey", 1)[0]
    assert "morph-method" not in easy
    assert "morph-source" not in easy
    css = CSS.read_text(encoding="utf-8")
    assert ".tl-mark" in css
    assert "shimmer" not in css
