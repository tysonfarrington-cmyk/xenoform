"""The idea line reads back as labelled chips (28 Oct, Tys: "is there a way we can make that more intuitive without
having to read a block of fine print"): a row a kind (what the morphs travel through, the places they pass through,
how it feels, who performs), "new" on what Make draws first, examples in dashed chips while the line is empty, and the
fine print folded behind "How the line works". The chips are built in the browser from POST /api/simple/idea."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "src/xenoform/ui_static/desk.css").read_text(encoding="utf-8")


def _fn(start: str, end: str) -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def test_the_field_is_short_and_the_fine_print_is_folded():
    vibe = _fn('<section class="easy-step" data-tour="easy-vibe">', "</section>") + _fn("function ideaBlock(easy) {", "\n}\n")
    assert "What it morphs through <small>optional · things, a theme, a place, a feel</small>" in vibe and "${ideaReadingLine(easy)}" in vibe
    assert '<details class="idea-help"><summary>How the line works</summary>' in vibe
    assert "Your idea in one line, if you have one." not in APP  # the old label and its paragraph are gone
    for cls in (".ir-row", ".ir-k", ".ir.thing", ".ir.place", ".ir.feel", ".ir.who", ".ir.example", ".idea-help > summary"):
        assert cls in CSS, cls


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the chip builder")
def test_the_chips_say_what_the_line_became(tmp_path):
    """The chip builder run in node on the route's real answer shape: the rows, the "new" tags (articles ignored), the
    family that fills the rest, the feel's knobs, Polly off, the count of stills Make draws, and the empty examples."""
    src = _fn("const IDEA_ROWS = ", "function ideaReadingLine(easy)")
    harness = f"""
const esc = (s) => String(s);
const lookLabel = (id) => id;
let state = {{ ideaReading: null, easy: {{}} }};
const ideaKey = () => "k";
const IDEA_ROWS = {src}
const reading = {{
  objects: [], own: ["rally car", "trophy"], family: "crystals-and-minerals", scenes: ["a desert at dusk"],
  performer: {{ style: "dance", cue: "girl dancing" }}, feel: {{ words: ["fast", "punchy"], macros: {{ speed: 0.85 }}, look: "cyan-flash" }},
  summary: "x", grow: {{ scenes: ["desert at dusk", "desert at dusk", "desert at dusk"], own: ["rally car", "trophy"], nouns: [], count: 5, seconds: 46 }}
}};
state.ideaReading = {{ key: "k", data: reading }};
const full = ideaReadingHtml({{ idea: "a rally car, a trophy, a desert at dusk, girl dancing, fast and punchy", performer: 0 }});
const empty = ideaReadingHtml({{ idea: "" }});
state.ideaReading = {{ key: "k", data: {{ summary: "", grow: {{}} }} }};
const nothing = ideaReadingHtml({{ idea: "zzz" }});
console.log(JSON.stringify({{ full, empty, nothing }}));
"""
    script = tmp_path / "chips.js"
    script.write_text(harness, encoding="utf-8")
    got = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    full = got["full"]
    assert full.index("Morphs through") < full.index("Passes through") < full.index("Feels") < full.index("Performer")
    assert '<span class="ir thing">rally car <i>new</i></span>' in full and '<span class="ir thing">trophy <i>new</i></span>' in full
    assert '<span class="ir thing">crystals and minerals <i>fills the rest</i></span>' in full
    assert '<span class="ir place">a desert at dusk <i>new</i></span>' in full  # "a desert" is the grow plan's "desert"
    assert '<span class="ir feel">fast, punchy</span>' in full and "Speed 85 · Look cyan-flash" in full
    assert '<span class="ir who">girl dancing</span>' in full and "Polly is off (Work in progress)" in full
    assert "Make draws 5 new stills first (2 things, 1 place), about 46 s." in full
    assert "ir thing example" in got["empty"] and "a rally car" in got["empty"] and "Empty, and the vibe decides." in got["empty"]
    assert "Nothing to morph between yet" in got["nothing"]
