import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
# one desk, one tour (26 Oct): the Director desk's tours (first video, continuity, energy) went with it. The Songline
# redesign (docs/UI_REVIEW.md 6.9) re-points its five steps along the step bar: the song, a vibe, Render Draft, a shot
# on the strip (the inspector), Perform
ORDER = ["easy-song", "easy-vibe", "easy-make", "easy-strip", "easy-perform"]


def test_tutorial_catalog_and_page():
    data = json.loads((ROOT / "src/xenoform/ui_static/tutorial.json").read_text(encoding="utf-8"))
    tours = {tour["id"]: tour for tour in data["tours"]}
    assert list(tours) == ["simple"]
    assert tours["simple"]["name"] == "The desk in a minute"
    assert tours["simple"]["steps"] == ORDER
    for step_id in ORDER:
        step = data["steps"][step_id]
        assert step["title"].strip()
        body = step["body"]
        assert 1 <= len(body) <= 3
        for line in body:
            assert line.strip().endswith(".")
            assert "\n" not in line
    assert set(data["steps"]) == set(ORDER)  # no orphan steps from the old tours
    # Open weights rides on the Render Draft step, its badge linking the licence page
    make = data["steps"]["easy-make"]
    assert make["badge"] is True and "open weights" in make["body"][0]
    assert make["simulate"] == "[data-act=easy-make]" and make["sim"] == "Simulated. No GPU job was started."
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert "Tutorial" in page.text
    assert "Reset tutorial" in page.text
    assert "/static/tutorial.js" in page.text
    raw = client.get("/static/tutorial.json")
    assert raw.status_code == 200
    assert [tour["id"] for tour in raw.json()["tours"]] == ["simple"]
    script = client.get("/static/app.js")
    assert script.status_code == 200
    for target in ORDER:
        assert f'data-tour="{target}"' in script.text, target
    tour_js = (ROOT / "src/xenoform/ui_static/tutorial.js").read_text(encoding="utf-8")
    assert "first-video" not in tour_js and "dataset.advanced" not in tour_js
    # the offer names the five steps, and its Start is a ghost: the step bar's button is the first screen's one violet
    # button (C2: the tour's Start, Choose a song and Make were all lit)
    assert 'class="ghost" id="tutorial-start"' in tour_js and 'class="generate" id="tutorial-start"' not in tour_js
    assert tour_js.count("A song, a vibe, a Draft, a shot on the strip, then Perform.") == 2  # the markup and showOffer()


def test_each_step_moves_the_desk_to_the_step_holding_its_target():
    # N11: opened on a cut or a Make, the tour pointed at controls that were not on screen. Each step names its desk
    # step; the tour passes it on and the desk goes there (with no song, the bundled demo stands in, by name)
    data = json.loads((ROOT / "src/xenoform/ui_static/tutorial.json").read_text(encoding="utf-8"))
    desks = {key: step.get("desk", "") for key, step in data["steps"].items()}
    assert desks == {"easy-song": "source", "easy-vibe": "plan", "easy-make": "plan", "easy-strip": "plan", "easy-perform": ""}
    assert "the bundled demo stands in" in data["steps"]["easy-vibe"]["body"][-1]
    # Render Draft is the step bar on Plan or Tweak, not the bar's Choose a song on Source
    assert data["steps"]["easy-make"]["target"] == "[data-tour=easy-make][data-step=plan], [data-tour=easy-make][data-step=tweak]"
    tour_js = (ROOT / "src/xenoform/ui_static/tutorial.js").read_text(encoding="utf-8")
    assert 'detail: { target: step.target, desk: step.desk || "" }' in tour_js
    app = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    hook = app.split('document.addEventListener("xeno-tour-step", (event) => {')[1].split("\n});")[0]
    assert "stepReach(state.easy)[want]" in hook and "goStep(want);" in hook and "useDemoSong();" in hook
    # the strip carries the inspector's target on Plan, Tweak and a cut's Render; Perform is the step bar's last step
    assert app.count('data-tour="easy-strip"') == 3
    assert "const tour = key === \"perform\" ? ' data-tour=\"easy-perform\"' : \"\";" in app
