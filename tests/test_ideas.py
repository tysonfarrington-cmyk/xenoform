import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
PROP = re.compile(r"\band an?\b", re.I)
BANNED = (
    "mickey",
    "disney",
    "marvel",
    "batman",
    "superman",
    "potter",
    "skywalker",
    "beatles",
    "taylor swift",
    "elvis",
    "picasso",
    "einstein",
    "pokemon",
    "mario",
    "zelda",
    "totoro",
    "mozart",
    "beethoven",
    "shakespeare",
)
BRIGHT = ("sun", "joy", "laugh", "bloom", "dawn", "gold", "parade", "bright")
DARK = ("night", "ash", "storm", "dark", "eclipse", "soot", "ember", "hush")


def test_idea_catalog_and_page():
    data = json.loads((ROOT / "src/xenoform/ui_static/ideas.json").read_text(encoding="utf-8"))
    fields = data["fields"]
    assert list(fields) == ["brief", "style", "shot", "transition"]
    blob = json.dumps(data).lower()
    for word in BANNED:
        assert word not in blob
    for name, field in fields.items():
        cats = field["categories"]
        assert len(cats) == 8
        ideas = [idea for cat in cats for idea in cat["ideas"]]
        assert len(ideas) == 80
        assert len(set(ideas)) == 80
        low = " ".join(ideas).lower()
        assert any(word in low for word in BRIGHT)
        assert any(word in low for word in DARK)
        for idea in ideas:
            assert idea.endswith(".")
            assert "\n" not in idea
            if name == "brief":
                assert len(PROP.findall(idea)) == 1
                assert len(idea) <= 170
            if name == "style":
                assert len(idea) <= 80
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert "/static/ideas.js" in page.text
    raw = client.get("/static/ideas.json")
    assert raw.status_code == 200
    assert raw.json()["fields"]["brief"]["categories"][0]["ideas"]
    script = client.get("/static/app.js")
    assert 'id="style-note"' in script.text
    assert 'id="transition-note"' in script.text
