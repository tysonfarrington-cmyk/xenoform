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


def test_b_setup_and_connect_are_reachable_from_simple():
    assert "function renderTool(" in APP
    render = APP.split("function render()", 1)[1].split("function renderTool(", 1)[0]
    assert "renderTool(state.view)" in render  # #setup and #connect draw inside the Simple shell, no Director tools needed
    menu = INDEX.split('class="more-menu"', 1)[1].split("</details>", 1)[0]
    assert 'data-act="go" data-hash="setup">Setup &amp; models</button>' in menu
    assert 'data-act="go" data-hash="connect">Connect an AI</button>' in menu
    aside = APP.split('<aside class="panel easy-side" data-tour="easy-make">', 1)[1].split("</aside>", 1)[0]
    assert 'data-hash="setup"' in aside and 'data-hash="connect"' in aside
    assert 'act === "go"' in APP
    assert ".easy-tool {" in CSS
    reproduce = (ROOT / "docs" / "REPRODUCE.md").read_text(encoding="utf-8")
    assert "Open **Setup & models** from the" in reproduce and "Open **Setup** in the desk header" not in reproduce


def test_c1_guardrail_lines_fold_on_the_client():
    assert "function guardLines(" in APP
    paint = APP.split("function paintJob()", 1)[1].split("function guardLines(", 1)[0]
    assert "guardLines((job.guardrails && job.guardrails.messages) || [])" in paint
    fold = APP.split("function guardLines(messages)", 1)[1].split("\n}\n", 1)[0]
    assert "(× ${n})" in fold  # identical lines once, with a count
    assert "/^\\[qa\\] ([a-z][a-z -]*?) at ([\\d.]+s)$/" in fold  # "[qa] glitch at 1.5s" x N folds into one line a kind
    assert "flag${at.length === 1" in fold


def test_e_the_morph_panel_reads():
    panel = APP.split("function morphPanel()", 1)[1].split("function morphReportHtml()", 1)[0]
    # four separate pills (the Look row's chip markup), a label, and a sentence on what the board is and when it applies
    assert 'class="toggle chips morph-methods" role="group" aria-label="Morph method"' in panel
    assert 'class="chip${on}" data-act="morph-method"' in panel
    assert "A pick here applies on the next Generate; nothing on screen changes now." in panel
    # the source library says what it is, and that it is not the vibe's stills library
    assert "Partners for this scene" not in panel
    assert "<h3>Clips and shapes the storyboard may pair with this shot</h3>" in panel
    assert "This is not the vibe's objects; those are Fine-tune → Library in Simple." in panel
    assert "#morph-panel .toggle.morph-methods {" in CSS and "background: none !important" in CSS


def test_d_open_in_advanced_tells_the_truth():
    assert "Open in Advanced" not in APP
    assert APP.count('data-act="easy-advanced" title=') == 2  # the result aside and the showcase aside
    assert "Director tools: storyboard, notes, export</button>" in APP
    handler = APP.split('act === "easy-advanced") {', 1)[1].split("} else if", 1)[0]
    assert 'enterAdvanced("export");' in handler  # lands on the step whose actions work on the finished cut, not the Song step


def test_f1_no_surprise_dry_run():
    comfy = APP.split("async function refreshComfy()", 1)[1].split("const brandLink", 1)[0]
    # the first time ComfyUI answers, Live goes on, once, unless Settings chose by hand
    assert "if (ok && !state.live && !state.liveChosen && !state.liveAuto) {" in comfy
    assert "state.live = true;" in comfy and "state.liveAuto = true;" in comfy
    save = APP.split('document.getElementById("save-settings").addEventListener("click"', 1)[1].split("});", 1)[0]
    assert "state.liveChosen = true;" in save
    assert "liveChosen: previous ? !!previous.liveChosen : false," in APP
    # and a dry run says what it is wherever the monitor names it
    assert "Dry run: Generate draws coloured blocks on the beat, no pictures (Settings → Live ComfyUI renders)" in APP
    assert "Dry-run animatic (coloured blocks on the beat, no pictures)" in APP
    assert "Dry run when you generate: coloured blocks, no pictures" in APP
    assert '"Dry-run cut"' not in APP and "Dry run is the default" not in APP
