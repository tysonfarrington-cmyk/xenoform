"""The Director desk's Morph step (a method board, a source clip, a QA chip) left the desk with it on 26 Oct.

Every morph a Make renders is the Simple engine's (still to still on the beat); the timeline on the cut's screen
re-renders one with another seed. The /api/morph/board route stays for MCP."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "xenoform" / "ui_static" / "app.js"
CSS = ROOT / "src" / "xenoform" / "ui_static" / "app.css"


def test_the_morph_board_is_gone_from_the_desk():
    script = APP.read_text(encoding="utf-8")
    for gone in ("morph-source", "morph-method", 'id="morph-panel"', "Partners for this scene", "function loadMorph("):
        assert gone not in script, gone
    hood = (ROOT / "src" / "xenoform" / "ui_static" / "hood.js").read_text(encoding="utf-8")
    assert 'data-hood="rerender"' in hood and 'start("rerender", body' in script  # one morph re-rendered, Under the hood on the cut's own screen
    assert "shimmer" not in CSS.read_text(encoding="utf-8")
