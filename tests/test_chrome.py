"""Simple copy, the Overview tab, keyboard, and the 13px type floor."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"


def test_simple_ideas_show_the_dice_and_two_chips():
    script = (STATIC / "ideas.js").read_text(encoding="utf-8")
    assert 'input.id === "easy-idea"' in script
    assert "return 2" in script
    assert "#note-text" not in script
    assert "[data-card]" not in script
    assert "Shift replaces" in script
    plain = script.split("if (plain) meta.append(dice);", 1)[1].split("ideas.forEach", 1)[0]
    assert "Shuffle" not in plain
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".easy .kicker { display: none; }" in css


def test_overview_tab_and_overflow_menu():
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'data-view="simple">Overview</a>' in page
    assert 'class="more-menu"' in page
    menu = page.split('class="more-menu"', 1)[1].split("</details>", 1)[0]
    assert "Copy diagnostics" in menu
    assert "About" in menu
    assert "Reset tutorial" in menu
    assert "Tutorial" in page
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'class="kicker">Overview</p>' in script
    assert "Make my video" in script
    assert 'data-act="easy-stop"' in script
    assert "Try another vibe" in script


def test_keyboard_and_tour_focus_the_button():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'event.key === "Enter"' in app
    assert "/cancel" in app
    assert "[data-act=expand]" in app
    tour = (STATIC / "tutorial.js").read_text(encoding="utf-8")
    assert "tutorial-start" in tour
    assert 'getElementById("tour-next")' in tour
    assert "title.focus" not in tour
    assert 'tabindex="-1"' not in tour


def test_body_copy_floor_keeps_mono_on_time_and_recipe():
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    floor = css.split(".meta,", 1)[1]
    assert "font-size: 13px;" in floor
    assert ".when," in floor
    assert ".recipe-code" in floor
    assert "font-family: var(--mono);" in floor
