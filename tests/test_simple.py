"""Simple mode is the first screen. Advanced keeps the full desk."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.analyze import read_features
from xenoform.cutdesk import recut
from xenoform.storyboard import plan_storyboard
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
VIBES = ("Liquid gold", "Paper summer", "Bloom", "Neon night", "Ocean", "Cosmic")


def test_simple_copy_is_on_the_desk_and_the_judges_page():
    script = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    for name in VIBES:
        assert name in script
    assert "Open in Advanced" in script
    assert "Try another vibe" in script
    assert "Make it better" in script
    assert 'data-act="easy-make"' in script
    page = (ROOT / "src/xenoform/ui_static/index.html").read_text(encoding="utf-8")
    assert 'id="advanced-toggle"' in page
    assert 'data-advanced="0"' in page
    client = TestClient(create_app())
    home = client.get("/")
    assert home.status_code == 200
    assert "music video director" in home.text
    judges = client.get("/judges")
    assert judges.status_code == 200
    assert "Drop a song" in judges.text
    assert "Make" in judges.text
    # the judges cards come from the registry catalogue (scripts/gen_judges_cards.py), so a featured
    # original carries its featured name there (liquid-gold is "Molten gold" since UI v6)
    from xenoform import vibes

    for row in vibes.catalog():
        if row["id"] in vibes.ORIGINAL:
            assert row["name"] in judges.text, row["id"]
    tours = json.loads((ROOT / "src/xenoform/ui_static/tutorial.json").read_text(encoding="utf-8"))
    names = [tour["name"] for tour in tours["tours"]]
    assert names[0] == "Simple mode in 30 seconds"
    assert "Make your first video" in names


def test_a_vibe_can_keep_morphs_off_while_the_track_is_loud():
    features = read_features("examples/demo_features.json")
    scenes = plan_storyboard(features, "pynchon", "A paper boat crosses a bright kitchen.")
    quiet = recut(scenes, features, 1, morph_cap=0)
    assert quiet
    assert all(scene["edit"] == "hard cut" or not scene.get("signature") for scene in quiet)
    assert not any(scene.get("signature") for scene in quiet)
    loud = recut(scenes, features, 0, morph_cap=1)
    assert sum(1 for scene in loud if scene.get("signature")) == 1
