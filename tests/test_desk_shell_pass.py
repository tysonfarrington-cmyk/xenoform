"""4 Nov 2026, the Setup and machine half of docs/UI_REVIEW.md on the front end: M1 (the Make gate), M2 and M3 (the Setup
cards), M5 (the tier heading), A1 to A4 (the primary button's contrast, the tour's arrow keys, the vibe card's badge and the
example layer, the passages' focus ring), W3 and W5 (copy), N8 and F8 (a stopped or failed whole song), F11 (the bad
ComfyUI address) and F14 (a cut still rendering in My videos). String pins as the rest of the desk's tests; the server half
is in test_setup_final.py and the colours are computed from the CSS, not read off it."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
DESK = (STATIC / "desk.css").read_text(encoding="utf-8")
APPCSS = (STATIC / "app.css").read_text(encoding="utf-8")
THEME = (STATIC / "theme.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
TOUR = (STATIC / "tutorial.js").read_text(encoding="utf-8")
SONGLINE = (STATIC / "songline.css").read_text(encoding="utf-8")


def _fn(start: str, end: str) -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def _lin(c: int) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _lum(rgb) -> float:
    r, g, b = (_lin(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _rgb(hex_: str):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def _over_white(rgb, alpha: float):
    return tuple(round(c + alpha * (255 - c)) for c in rgb)


# ---------------------------------------------------------------- A1
def test_the_primary_button_reads_at_4_5_to_1_in_every_state_computed_from_the_css():
    tokens = dict(re.findall(r"--x-(primary(?:-hi|-lo)?):\s*(#[0-9a-fA-F]{6});", THEME))
    assert set(tokens) == {"primary", "primary-hi", "primary-lo"}
    rule = DESK.split("button.generate, .upload.solid, .easy .upload.solid {", 1)[1].split("\n}", 1)[0]
    fill = re.search(r"background:\s*var\(--x-(primary)\)\s+linear-gradient\(180deg,\s*rgba\(255, 255, 255, ([0-9.]+)\), rgba\(255, 255, 255, 0\) 60%\)", rule)
    assert fill and re.search(r"color:\s*#fff;", rule), "white text on the primary fill"
    highlight = float(fill.group(2))
    # the text sits in the middle of the button: its top edge is about 30 % down, where the highlight has faded to
    # highlight x (1 - 0.3 / 0.6); the very top edge carries all of it (no text there)
    under_text = highlight * (1 - 0.3 / 0.6)
    white = (255, 255, 255)
    rest = _contrast(white, _over_white(_rgb(tokens["primary"]), under_text))
    assert rest >= 4.5, rest
    hover = re.search(r"button\.generate:hover:not\(:disabled\), \.upload\.solid:hover \{ background-color: var\(--x-(primary-hi)\);", DESK)
    assert hover, "hover uses the lighter primary, not the accent's hover"
    assert _contrast(white, _over_white(_rgb(tokens["primary-hi"]), under_text)) >= 4.5
    pressed = re.search(r"button\.generate:active:not\(:disabled\), \.upload\.solid:active \{\s*background-color: var\(--x-(primary-lo)\);", DESK)
    assert pressed and _contrast(white, _over_white(_rgb(tokens["primary-lo"]), under_text)) >= 4.5
    # the review's numbers: the accent itself is the weak fill
    assert round(_contrast(white, _rgb("#7c6cff")), 1) == 3.9 and round(_contrast(white, _rgb("#9488ff")), 1) == 2.9
    assert "var(--x-accent) linear-gradient" not in DESK and "background-color: var(--x-accent-hi); filter" not in DESK


def test_every_place_a_generate_button_is_styled_uses_that_one_fill():
    # a rule that names .generate and sets its own colours would undo the contrast above; layout-only rules are fine
    rules = re.sub(r"/\*.*?\*/", "", DESK, flags=re.S)
    for match in re.finditer(r"([^{}]*\.generate[^{}]*)\{([^}]*)\}", rules):
        selector, body = match.group(1).strip(), match.group(2)
        if "background" in body:  # the states of the primary fill, and nothing else, set a background
            assert "var(--x-primary" in body, selector
        assert all(value == "#fff" for value in re.findall(r"(?:^|[;\s])color:\s*([^;]+);", body)), selector
    for selector in (".more-panel button:hover", "#palette-list button.on", ".easy-crumbs .crumb.now::before", ".drop-open.is-hit"):
        assert selector in DESK
    text_on_accent = re.findall(r"[^{}]*\{[^}]*background:\s*var\(--x-accent\)[^}]*color:\s*#fff[^}]*\}", DESK)
    assert not text_on_accent, text_on_accent  # white text on the accent itself (3.9:1) moved to --x-primary


# ---------------------------------------------------------------- A2
def test_the_tours_arrow_keys_leave_a_focused_knob_and_other_arrow_widgets_alone():
    assert "const ARROW_WIDGETS = '[role=\"slider\"]" in TOUR and 'input[type="radio"]' in TOUR and 'input[type="range"]' in TOUR
    assert '[role="radio"]' not in TOUR.split("const ARROW_WIDGETS =", 1)[1].split("\n", 1)[0]  # a vibe card keeps the tour's arrows
    handler = TOUR.split('if (typing) return;', 1)[1].split('if (event.key === "ArrowRight")', 1)[0]
    assert "closest(ARROW_WIDGETS)" in handler and "return;" in handler
    # the knob (ui_v6.js) turns on the same keys: the tour must not also step
    assert "role=\"slider\"" in (STATIC / "ui_v6.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- A3
def test_the_vibe_cards_play_badge_is_a_sibling_button_and_one_tab_stop():
    cards = _fn("function vibeCards(easy, compact, which) {", "// The originals and the non-featured")
    assert 'class="vibe-cell"' in cards and '<button type="button" class="vibe-eg"' in cards
    assert '<span class="vibe-eg"' not in cards and 'role="button"' not in cards
    assert "vibe.example && !compact" in cards and 'data-act="vibe-example"' in cards
    assert cards.count('tabindex="${rove ? "0" : "-1"}"') == 2  # the card and its badge tab as one: the group has one stop, not twelve
    # the badge sits over the card's corner and shows when the card has the focus
    assert ".vibe-cell { position: relative;" in DESK and ".vibe-cell:focus-within .vibe-eg" in DESK


def test_the_example_layer_is_a_native_modal_dialog_that_returns_the_focus():
    layer = _fn("function closeExample() {", "// Pick the vibe an example shows")
    assert 'document.createElement("dialog")' in layer and "box.showModal()" in layer
    assert "aria-modal" not in layer and 'setAttribute("role"' not in layer
    assert 'box.addEventListener("close"' in layer and "back.focus()" in layer and "from.isConnected" in layer
    assert 'id = "xeno-example"' in layer and 'class' in layer and 'className = "example-modal"' in layer
    assert 'openExample(el.dataset.vibe || "", el)' in APP
    assert "dialog.example-modal {" in DESK and ".example-modal::backdrop" in DESK
    # no hand-made keyboard layer any more: the dialog handles Escape and Tab itself, and keeps its Escape from the desk's own
    # (Escape on a running render stops it: it was meant for the layer)
    assert 'event.target.closest(".vibe-eg")' not in APP
    escape = layer.split('box.addEventListener("keydown"', 1)[1].split("});", 1)[0]
    assert 'event.key !== "Escape"' in escape and "event.stopPropagation()" in escape and "closeExample()" in escape


# ---------------------------------------------------------------- A4
def test_the_passage_buttons_keep_a_focus_ring_and_arrowing_the_mini_cards_follows_the_redraw():
    assert ".shots-lane .passage:focus-visible { outline: 2px solid" in APPCSS
    assert "passage:focus-visible { background: hsl(var(--hue, 260) 35% 40%); outline: none; }" not in APPCSS
    pick = _fn('} else if (act === "easy-vibe") {', '} else if (act === "easy-make") {')
    result_branch = pick.split('if (state.easy.phase === "result" || state.easy.phase === "showcase") {', 1)[1].split("return;", 1)[0]
    assert "render();" in result_branch and "chosen.focus()" in result_branch


# ---------------------------------------------------------------- M1
def test_make_leads_to_setup_while_a_required_model_is_missing():
    assert "function setupGate()" in APP and "gate.blocked" in _fn("function setupGate()", "function goToSetup()")
    make = _fn("async function easyMake() {", "const vibe = vibeById(state.easy.vibe);")
    assert "setupGate()" in make and "goToSetup();" in make and "await" not in make  # Setup opens at once, not after a check
    assert "loadSetup().then(" in _fn("function goToSetup() {", "function paintMakeGate() {")  # and looks again as it opens
    click = _fn('} else if (act === "easy-make") {', '} else if (act === "easy-cloud") {')
    assert click.index("setupGate()") < click.index("Choose a song.")  # Setup first, whether or not a song is picked
    paint = _fn("function paintMakeGate() {", "async function easyMake")
    assert "gate.button" in paint and "gate.line" in paint and 'data-act="go" data-hash="setup"' in paint and "Open Setup" in paint
    assert "button.dataset.makeLabel" in paint and 'delete button.dataset.gate;' in paint  # a gate that lifts gives the label back
    assert "paintMakeGate();" in _fn("function render() {", "function renderTool(")
    assert "`?comfy=${encodeURIComponent(state.endpoint)}`" in _fn("async function loadSetup() {", "function setupGate()")
    # the step bar draws the gate's line itself, so its in-place repaint (a knob or Quality touched, an estimate landing) keeps
    # it; paintMakeGate leaves the bar alone and puts its line under a Make button elsewhere on the page (integrate-4nov)
    bar = _fn("function stepBar(easy, step) {", "function paintStepBar() {")
    assert 'facts += `<span class="note make-gate" role="status">${esc(missing.line)}. ' in bar and "Open Setup" in bar
    assert "line: gate.line" in _fn("function missingModels() {", "function costTag(")
    assert '.filter((button) => !button.closest("#step-bar"))' in paint and 'if (!node.closest("#step-bar")) node.remove();' in paint
    assert ".step-facts .make-gate { flex-basis: 100%; }" in SONGLINE


# ---------------------------------------------------------------- M2, M3, M5 on the page
def test_the_setup_page_shows_each_models_files_the_reason_a_download_is_off_and_the_tier_heading():
    card = _fn("function modelCard(model) {", "function renderSetup() {")
    assert "model.parts" in card and 'class="model-parts"' in card and "Installed" in card and "Missing" in card
    assert "model.why_not" in card and "disabled" in card and "aria-describedby" in card and 'class="note why-not"' in card
    assert "need_label" in card and "Download the rest" in card and "<summary>Details</summary>" in card
    assert 'id="dl-status-' in card and 'id="dl-track-' in card  # pollDownload rewrites them in place
    page = _fn("function renderSetup() {", "\n}\n")
    assert "tier.heading" in page and "tier.vram_label" in page and "setup.checked" in page and "filmPackCard(setup.film_pack)" in page
    assert "Out of date: ComfyUI is not connected now." in page and "state.comfyOk === false && !!setup.comfy_answered" in page
    assert "setup.gate" in page and "gate.line" in page
    assert "Needed to make videos" in card and "Needed for a live restyle" not in APP
    flipped = _fn("async function refreshComfy() {", "// A ComfyUI that does not answer")
    assert "loadSetup().then(" in flipped and 'state.view === "setup"' in flipped


# ---------------------------------------------------------------- W3, W5
def test_setup_settings_and_about_say_where_a_setting_lives_in_short_lines_with_details_behind():
    words = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", APP)  # the words on the page, not the comments about them
    for old in ("Pynchon", "live restyle", "no longer", "as it always has", "as the cut was made before", "stay off the base install",
                "the QA pass finds judder", "Ableton is not part of this desk", "not the engine and not finished"):
        assert old not in words and old not in INDEX, old
    assert "Performer (Polly)" in APP
    settings = INDEX.split('<dialog id="settings">', 1)[1].split("</dialog>", 1)[0]
    assert settings.count('class="where"') + settings.count('class="where" id') >= 4 and "this browser" in settings
    assert "port 8189" in settings and "XENO_PROXY_URL" in settings and "<summary>Details</summary>" in settings
    assert "Paid cloud renders (partner node, not open weights)" in settings  # the label the older test pins
    about = INDEX.split('<dialog id="about"', 1)[1].split("</dialog>", 1)[0]
    assert 'class="about-points"' in about and "<summary>Details</summary>" in about and "what is not, yet" not in about
    assert 'document.getElementById("paid-cloud-where")' in APP


# ---------------------------------------------------------------- N8, F8
def test_a_stopped_or_failed_whole_song_has_a_way_back_and_says_why_it_failed():
    song = _fn("function songMaking(easy, chosen) {", "function songAside(easy) {")
    assert 'data-act="easy-again">Back to the song</button>' in song
    assert 'data-act="song-assemble">Lay it together again</button>' in song and "onlyAssembly" in song
    assert "assembly.error" in song and "w.detail" in song and "x.detail" in song and 'class="song-failed"' in song
    assert "The passages are done; laying them together failed." in song and "did not render." in song
    assert "makingIsIdle()" in _fn('const brandLink = document.querySelector(".brand");', 'window.addEventListener("hashchange"')
    idle = _fn("function makingIsIdle() {", "// The logo is the home button")
    assert "easy.songRun" in idle and '"queued", "running", "assembling", "ready"' in idle and "ignoreJob" in idle


# ---------------------------------------------------------------- F11
def test_a_bad_comfyui_address_says_so_with_the_address_and_survives_a_reload():
    banner = _fn("function paintComfyBanner() {", "// Setup & models and Connect")
    assert "ComfyUI is not answering at ${esc(address)}" in banner and 'data-act="comfy-settings"' in banner and "Open Settings" in banner
    assert "Make plays this vibe's pictures in the browser" in banner and 'setAttribute("role", "alert")' in banner
    assert 'act === "comfy-settings"' in APP and 'act === "comfy-banner-off"' in APP
    assert "paintComfyBanner();" in _fn("function render() {", "function renderTool(")
    assert 'localStorage.getItem("xeno-endpoint")' in APP and "writeEndpoint(state.endpoint);" in APP
    assert "endpoint: readEndpoint() || data.endpoint" in APP
    save = _fn('document.getElementById("save-settings").addEventListener("click"', 'document.addEventListener("change"')
    assert "refreshComfy().then(" in save  # the facts read the new answer, not the old one
    assert ".comfy-banner {" in DESK


# ---------------------------------------------------------------- F14
def test_my_videos_says_a_cut_is_still_rendering_and_offers_open_not_re_render():
    gallery = _fn("function galleryPanel() {", "// A saved cut reopened whole")
    assert 'row.status === "running"' in gallery and 'class="gallery-state"' in gallery and '"Open" : "Reopen"' in gallery
    assert gallery.count("${rendering ? \"\" : `") == 1 and "video-rerender" in gallery and "video-copy" in gallery
    # integrate-4nov: Round 0's resumeMaking follows the running job (its own clock and poll), standing in for followRunningCut
    follow = _fn("async function resumeMaking(id, kept, quiet) {", "// The five steps in the toolbar")
    assert 'setEasyPhase("making")' in follow and "poll(id)" in follow and "job.started" in follow
    opened = _fn('} else if (act === "video-open") {', '} else if (act === "video-copy") {')
    assert 'if (row.status === "running") {' in opened and "await resumeMaking(row.id, keptMaking(), false);" in opened
    assert ".gallery-state {" in DESK
