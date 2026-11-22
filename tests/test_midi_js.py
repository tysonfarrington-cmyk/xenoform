"""The MIDI layer's own node test (tests/js/midi_test.js): the hold stack, soft takeover, the maps by device name and
the runtime's event pipeline in midi.js, run with node where it is installed (node is not a dependency of the desk)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).parent / "js" / "midi_test.js"


def test_midi_js_under_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    version = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    major = int((re.match(r"v(\d+)", version) or [0, 0])[1])
    if major < 18:
        pytest.skip(f"node {version} has no node:test (18 or later)")
    r = subprocess.run([node, str(JS)], capture_output=True, text=True, timeout=120, encoding="utf-8")
    assert r.returncode == 0 and "# fail 0" in r.stdout, r.stdout[-4000:] + r.stderr[-2000:]
