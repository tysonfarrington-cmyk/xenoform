"""Ctrl+K lists the controls on screen and the MCP tool names."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "xenoform" / "ui_static" / "app.js"
PAGE = ROOT / "src" / "xenoform" / "ui_static" / "index.html"
MCP = ROOT / "src" / "xenoform" / "mcp_server.py"


def test_palette_lists_every_mcp_tool():
    script = APP.read_text(encoding="utf-8")
    block = script.split("const MCP_TOOLS = [", 1)[1].split("];", 1)[0]
    source = MCP.read_text(encoding="utf-8")
    names = re.findall(r"@server\.tool\(\)\s+def ([a-z_]+)\(", source)
    assert names
    for name in names:
        assert f'"{name}"' in block
    for resource in ("storyboard", "lessons", "transitions"):
        assert f'"{resource}"' in block
    assert 'id="command-palette"' in PAGE.read_text(encoding="utf-8")
    assert 'event.key.toLowerCase() === "k"' in script
    assert 'data-act="palette"' in script
    assert "shimmer" not in block
