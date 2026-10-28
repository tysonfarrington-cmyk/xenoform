"""A theme word grows its things (idea.THEMES, 28 Oct; Tys: "make a theme word like 'car rally racing' grow four or five
related things on its own, with a small built-in theme list")."""
from pathlib import Path

from xenoform import idea

APP = (Path(__file__).resolve().parents[1] / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")


def test_the_theme_list_is_small_clean_and_never_steals_a_place_or_the_song():
    assert 30 <= len(idea.THEMES) <= 40
    for name, t in idea.THEMES.items():
        assert len(t["things"]) == idea.THEME_THINGS == 15, name  # enough for a whole cut on the theme (28 Oct)
        assert all(thing == thing.lower() and not thing.startswith(("a ", "an ", "the ")) for thing in t["things"]), name
    words = [w for t in idea.THEMES.values() for w in t["words"].split()]
    assert len(words) == len(set(words))  # a word names one theme
    clash = set(words) & (idea.PLACES | idea.SKIES | idea.MUSIC | idea.PARTY | idea.PEOPLE | idea.STOP)
    assert not clash, clash  # a place is a scene, the song is the song, a person is Polly
    assert idea.MAX_OWN >= idea.THEME_THINGS and idea.SHAPES_MAX >= idea.THEME_THINGS


def test_a_theme_word_grows_its_things_and_a_thing_stays_a_thing():
    r = idea.read("car rally racing", "neon-noir", llm=False)
    assert r["theme"] == "racing" and r["own"][:5] == ["rally car", "racing helmet", "trophy", "chequered flag", "steering wheel"]
    assert len(r["theme_things"]) == 15 and set(r["objects"]) | set(r["own"]) >= set(idea.THEMES["racing"]["things"])
    assert "car rally racing" not in r["own"] and "(the racing theme)" in r["summary"]
    assert idea.grow_plan(r, "neon-noir")["count"] == 15
    thing = idea.read("a rally car", "neon-noir", llm=False)
    assert thing["theme"] == "" and thing["own"] == ["rally car"]  # it ends on the car: a thing, not the theme
    assert idea.read("a racing theme", "neon-noir", llm=False)["theme"] == "racing"  # a trailing "theme" is dropped
    typed = idea.read("a rally car, a trophy", "neon-noir", llm=False)
    assert typed["theme"] == "" and typed["own"] == ["rally car", "trophy"]


def test_themes_sit_beside_places_feels_and_the_library():
    r = idea.read("car rally racing in a desert at dusk", "neon-noir", llm=False)
    assert r["scenes"] == ["a desert at dusk"] and r["theme"] == "racing" and len(r["theme_things"]) == 15
    felt = idea.read("halloween, slow and dreamy", "neon-noir", llm=False)
    assert felt["theme"] == "halloween" and felt["feel"]["words"] == ["slow", "dreamy"]
    nouns, _labels = idea._catalogue()
    known = [t for t in idea.THEMES["halloween"]["things"] if nouns.get(t) is not None]
    assert all(t in felt["objects"] for t in known) and all(t not in felt["own"] for t in known)  # the library's own are objects
    assert idea.read("chrome moth", "neon-noir", llm=False)["theme"] == ""
    assert idea.read("girl dancing to rave music in a cyberpunk city", "neon-noir", llm=False)["theme"] == ""
    assert idea.read("", "neon-noir", llm=False) == idea.EMPTY and idea.EMPTY["theme"] == ""


def test_the_chips_name_the_theme():
    assert 'if (have.theme) extra.thing = `<span class="ir-note">the ${esc(have.theme)} theme</span>`;' in APP
    assert "A theme (racing, pirates, halloween, astronauts, gaming and about thirty more) brings fifteen things" in APP
