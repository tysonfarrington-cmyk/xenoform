"""The page side of the live OSC: osc_out.js (its logic runs in node when node is installed), vj.html loading it and calling its
two functions, and midi.js left alone (the sender wraps XenoMidi, it does not edit it)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
VJ = (STATIC / "vj.html").read_text(encoding="utf-8")
SENDER = (STATIC / "osc_out.js").read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_sender_logic_passes_its_node_checks():
    """Derived channels, the section estimate, the audio helper, the XenoMidi hook and the fixed-rate scheduler (30/60/144/240 Hz
    screens, a 30 fps page, a hidden window, no websocket): tests/js/osc_out_check.js."""
    run = subprocess.run(["node", str(ROOT / "tests" / "js" / "osc_out_check.js")], capture_output=True, text=True, timeout=120, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "all osc_out checks passed" in run.stdout and run.stdout.count("ok  ") >= 9


def test_vj_loads_the_sender_after_midi_and_calls_its_two_functions():
    scripts = re.findall(r'<script src="(/static/[^"]+)"></script>', VJ)
    assert scripts.index("/static/midi.js") < scripts.index("/static/osc_out.js"), "the sender wraps XenoMidi, so it loads after it"
    init = VJ.index("XenoOsc.init(")
    assert VJ.index("XenoMidi.init(") < init, "after XenoMidi.init, so the wrapped fire and handle are the live ones"
    mount = VJ.index("XenoOsc.mount(")
    assert init < mount and "XenoOsc.mount($('midi-panel'),'before')" in VJ, "one control, above the MIDI panel, no layout change"
    frame = VJ[init:mount]
    for what in ("bassS", "highS", "beatPulse", "S.beats", "S.cur", "S.curFx", "S.inten", "S.bpm", "SE.drums", "XenoOsc.audio(an,buf,"):
        assert what in frame, f"the frame() the page gives the sender should carry {what} (the values the HUD and the picture use)"
    assert "toast" in VJ[init:init + 40]


def test_midi_js_is_not_edited_for_osc_and_the_sender_wraps_instead():
    midi = (STATIC / "midi.js").read_text(encoding="utf-8")
    assert "osc" not in midi.lower() or "XenoOsc" not in midi
    assert "M.fire = function" in SENDER and "M.handle = function" in SENDER and "__oscHooked" in SENDER
    assert "fire.apply(this, arguments)" in SENDER and "handle.apply(this, arguments)" in SENDER, "the original still runs, with its own arguments"


def test_the_desk_serves_the_sender_and_the_page_that_loads_it():
    c = TestClient(create_app())
    r = c.get("/static/osc_out.js")
    assert r.status_code == 200 and "XenoOsc" in r.text and r.headers["cache-control"] == "no-cache"
    assert 'src="/static/osc_out.js"' in c.get("/vj").text


def test_the_sender_only_asks_the_desk_after_the_control_is_seen_or_was_used_before():
    """A desk without python-osc answers 503: the page must not provoke it on every load, so the first GET /api/osc waits for the
    control to be seen (IntersectionObserver) or for localStorage to say the viewer used OSC before."""
    assert "IntersectionObserver" in SENDER and "if (s.used) this.refresh()" in SENDER
    init = SENDER[SENDER.index("  init(opts) {"):SENDER.index("  mount(ref, where)")]
    assert "this.refresh()" in init and init.count("this.refresh()") == 1 and "s.used" in init
    assert 'store.set({ used: true' in SENDER
    assert "this.cfg.websocket === false" in SENDER, "no websocket upgrade is tried on a desk that said it cannot"
