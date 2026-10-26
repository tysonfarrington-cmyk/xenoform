"""One desk (docs/WORKFLOW_AUDIT.md, the before-deadline list, 26 Oct): a way out of Director tools (A), Setup and
Connect reachable from Simple (B), the guardrail lines grouped (C1), the Morph panel that reads (E), "Open in Advanced"
telling the truth (D), no surprise dry run (F1), and Simple's small ones (G). String pins against the desk files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def test_a_director_tools_has_a_way_out():
    # the toggle is relabelled and reads as the exit while it is on
    assert 'id="advanced-toggle" aria-pressed="false">Director tools</button>' in INDEX
    assert 'Back to Simple" : "Director tools";' in APP
    # Advanced lives at its own URLs, so Back leaves it and a reload lands in Simple unless the URL says desk
    assert 'return "#simple/desk";' in APP
    assert "function advancedHash(" in APP and "function enterAdvanced(" in APP and "function leaveAdvanced(" in APP
    assert "syncAdvanced(advancedHash());" in APP  # boot derives the mode from the URL, not from localStorage
    hashchange = APP.split('window.addEventListener("hashchange"', 1)[1].split("});", 1)[0]
    assert "if (advancedHash() && !advancedOn) syncAdvanced(true);" in hashchange
    assert 'viewFromHash() === "simple") syncAdvanced(false);' in hashchange
    # the logo goes home from Advanced too; the rail's first item and the button return to the screen you left
    brand = APP.split('const brandLink = document.querySelector(".brand");', 1)[1].split("const viewNav", 1)[0]
    assert 'document.body.dataset.advanced === "1") return;' not in brand
    assert "leaveAdvanced(true);" in brand
    rail = APP.split("function railHtml(current)", 1)[1].split("function songStep()", 1)[0]
    assert 'data-act="leave-advanced">&larr; Back to Simple</button>' in rail
    assert rail.index("rail-exit") < rail.index("<h2>Your video</h2>")
    assert 'act === "leave-advanced"' in APP
    assert ".rail .rail-exit {" in CSS
    # a finished cut stays on its result when you come back through the button (home only through the logo)
    leave = APP.split("function leaveAdvanced(home)", 1)[1].split("async function boot()", 1)[0]
    assert '(phase === "result" || phase === "showcase")) setEasyPhase(phase);' in leave
