"""The desk's design system (v8, 27 Oct 2026; Tys: "its feeling a bit dated and make sure the buttons look and feel good
to touch and that it actually feels like a bit of software and not just some browser toy").

One stylesheet (desk.css) after theme.css (the tokens) and app.css (the layout) replaces the two layers that fought
(ui_v4.css dark, ui_v6.css light glass, nearly every rule !important). String pins: the links, the tokens, the toolbar
with the stage strip in it, the three control heights with 44 px on touch, hover only with a mouse, the press, the focus
ring, the panels, and the narrow-screen grid that cannot overflow."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
DESK = (STATIC / "desk.css").read_text(encoding="utf-8")
THEME = (STATIC / "theme.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")


def test_one_design_layer_is_linked_where_the_old_two_were():
    assert not (STATIC / "ui_v4.css").exists() and not (STATIC / "ui_v6.css").exists()
    links = re.findall(r'href="(/static/[^"]+\.css)"', INDEX)
    assert links == ["/static/theme.css", "/static/app.css", "/static/desk.css"]
    for page in ("judges.html", "moves.html"):
        assert "desk.css" in (STATIC / page).read_text(encoding="utf-8"), page
    rules = re.sub(r"/\*.*?\*/", "", DESK, flags=re.S)  # the comments may name the old layers' habit
    rules = rules.replace(".xf-strip-empty { display: none !important; }", "").replace("width: 100% !important", "")
    assert "!important" not in rules


def test_the_tokens_are_one_dark_palette_with_one_accent():
    assert "color-scheme: dark;" in THEME
    for token in ("--x-bg:", "--x-surface:", "--x-surface-2:", "--x-text:", "--x-text-2:", "--x-accent:", "--x-accent-soft:",
                  "--x-r-md: 8px;", "--x-h-sm: 30px;", "--x-h-md: 36px;", "--x-h-lg: 44px;", "--x-bar: 56px;", "--x-font-ui:"):
        assert token in THEME, token
    # the older names map onto it, so app.css follows
    assert "--panel: var(--x-surface);" in THEME and "--text: var(--x-text);" in THEME and "--line: var(--x-line);" in THEME
    assert "border-radius: var(--radius-pill);\n}" not in THEME.split("input,\nselect,\ntextarea")[0]  # no pill buttons


def test_a_toolbar_with_the_stages_in_it():
    assert '<nav class="stagebar" id="stage-slot" aria-label="Where you are"></nav>' in INDEX
    render = APP.split("function render() {", 1)[1].split("function renderTool(", 1)[0]
    assert 'document.getElementById("stage-slot")' in render
    assert ".top {" in DESK and "height: var(--x-bar);" in DESK
    assert ".stagebar .easy-crumbs {" in DESK and "counter-increment: stage;" in DESK
    assert '.easy-crumbs .crumb.done::before { content: "\\2713";' in DESK
    assert '<span>${proto ? `Make a ${esc(String(easyLength(easy)))} s prototype` : "Make my video"}</span><kbd>${esc(shortcutLabel())}</kbd>' in APP


def test_buttons_feel_like_controls():
    # three heights, a press that moves 1 px and darkens, hover only with a mouse, a ring for the keyboard
    assert "button:active:not(:disabled), .upload:active, a.ghost:active { transform: translateY(1px); }" in DESK
    assert "button.generate:active:not(:disabled), .upload.solid:active {" in DESK
    assert DESK.count("@media (hover: hover)") >= 10
    assert re.search(r"button:focus-visible[^{]*\{\s*outline: 2px solid var\(--x-accent\); outline-offset: 2px;", DESK)
    assert "-webkit-tap-highlight-color: transparent; touch-action: manipulation;" in DESK
    coarse = DESK.split("@media (pointer: coarse) {", 1)[1].split("\n}\n", 1)[0]
    for sel in ("body[data-desk] button.ghost", "body[data-desk] button.generate", "body[data-desk] .toggle button",
                "body[data-desk] .chips .chip", "body[data-desk] .easy-crumbs button.crumb", "body[data-desk] .more-panel button"):
        assert sel in coarse, sel
    assert "min-height: var(--x-h-lg);" in coarse
    # a segmented control is as wide as its choices; chips are separate rectangles, the chosen one in the accent
    assert ".toggle:not(.chips), .simple-seg .toggle:not(.chips) { width: fit-content; max-width: 100%; }" in DESK
    assert ".chips .chip.on, .toggle .chip.on {" in DESK


def test_panels_menus_and_the_narrow_screen():
    assert ".panel, .easy-step, .fine-tune, .gallery, #my-videos, .easy-share, .easy-make-grid > aside, .drop-open {" in DESK
    assert "backdrop-filter: none;" in DESK  # no frosted glass on the panels
    assert ".more-panel {" in DESK and "box-shadow: var(--x-shadow-pop);" in DESK
    assert ".player:has(video[controls]) > .play-toggle { display: none; }" in DESK
    narrow = DESK.split("@media (max-width: 1000px) {", 1)[1].split("\n}\n", 1)[0]
    assert "grid-template-columns: minmax(0, 1fr);" in narrow  # 1fr grew to the timeline and clipped the phone screen
    assert "#app { width: auto; max-width: none; margin: 0;" in DESK  # the workspace fills the window
