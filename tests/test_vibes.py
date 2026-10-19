"""Each vibe has its own still and library. Simple falls back to those shots."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
VIBES = ("liquid-gold", "paper-summer", "bloom", "neon-night", "ocean", "cosmic")
SHOTS = ("wide", "medium", "close", "reveal")


def test_each_vibe_has_a_still_and_four_library_shots():
    for vibe in VIBES:
        still = STATIC / "vibes" / f"{vibe}.jpg"
        assert still.is_file()
        assert still.stat().st_size > 20_000
        for shot in SHOTS:
            clip = STATIC / "library" / vibe / f"{shot}.mp4"
            size = clip.stat().st_size
            assert size > 500
            assert size < 1_200_000
            assert (STATIC / "library" / vibe / f"{shot}.jpg").stat().st_size > 4_000
    for name in SHOTS:
        assert (STATIC / "library" / f"{name}.mp4").stat().st_size > 10_000


def test_simple_fallback_cuts_the_library_instead_of_the_blob():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "/static/vibes/" in app
    assert "startLibraryCut" in app
    assert "Playing the pictures for this vibe." in app
    make = app.split("async function easyMake", 1)[1].split("async function easyBetter", 1)[0]
    assert "playLive" not in make
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert "background-size: cover" in css
    assert "shimmer" not in css


def test_judges_page_uses_real_stills_and_keeps_the_badge():
    page = (STATIC / "judges.html").read_text(encoding="utf-8")
    assert "Drop a song" in page
    assert "Open weights" in page
    assert "Open weights only" not in page
    assert 'href="/licences"' in page
    assert 'href="/credits"' in page
    assert "hue-rotate" not in page
    assert "linear-gradient" not in page
    for vibe in VIBES:
        assert f"vibes/{vibe}.jpg" in page
    script = (STATIC / "judges.js").read_text(encoding="utf-8")
    assert "/api/judges" not in script
    assert "library/${id}/${shot}.mp4" in script
    assert "XENO_CUT" in script


def test_badge_opens_the_licence_page_and_credits_stay_uninvented():
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app())
    desk = client.get("/")
    assert desk.status_code == 200
    assert ">Open weights</a>" in desk.text
    assert "Open weights only" not in desk.text
    assert 'href="/licences"' in desk.text
    licences = client.get("/licences")
    assert licences.status_code == 200
    text = licences.text
    assert "about $10M annual revenue" in text
    assert "FLUX Non-Commercial License" in text
    assert "flux-2-klein-4b-fp8.safetensors" in text
    assert "Apache 2.0" in text
    credits = client.get("/credits")
    assert credits.status_code == 200
    body = credits.text
    assert "No CC BY credit is stated" in body
    for name in ("liquid-gold.jpg", "paper-summer.jpg", "bloom.jpg", "neon-night.jpg", "ocean.jpg", "cosmic.jpg"):
        assert name in body
        assert "TODO" in body
    assert "Wikimedia" in body
    proxied = client.get("/licences", headers={"x-xeno-base": "/xenoform"})
    assert 'href="/xenoform/static/theme.css"' in proxied.text
    assert 'href="/xenoform/licences"' in proxied.text
