"""Ctrl+K lists the desk's controls as they are drawn, searchable by their words.

The Director desk's list of MCP tool names (which only jumped to the Connect step) left with it on 26 Oct; the MCP
server and its tools are unchanged, and Connect an AI is in the "..." menu."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "xenoform" / "ui_static" / "app.js"
PAGE = ROOT / "src" / "xenoform" / "ui_static" / "index.html"


def test_palette_lists_the_controls_on_the_desk():
    script = APP.read_text(encoding="utf-8")
    controls = script.split("function paletteControls()", 1)[1].split("function paintPalette()", 1)[0]
    assert 'document.querySelectorAll("button[data-act], a.ghost[href], .more-panel button")' in controls
    assert "MCP_TOOLS" not in script and "goRail" not in script
    run = script.split("function runPalette(row)", 1)[1].split('document.addEventListener("keydown"', 1)[0]
    assert "node.click()" in run and "row.value" in run
    assert 'id="command-palette"' in PAGE.read_text(encoding="utf-8")
    assert 'event.key.toLowerCase() === "k"' in script
    assert 'act === "palette-run"' in script
    assert "shimmer" not in controls
