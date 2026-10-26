"""The idea line (26 Oct): a Simple cut listens to the words the user typed, not to the Director storyboard the desk
sends with every Make; the making screen shows the chain, not that storyboard; the field says what it does."""
from pathlib import Path

from xenoform import dense, morph_pass as mp, stills as S

ROOT = Path(__file__).resolve().parents[1]
ROCKET = [{"index": 0, "action": "The rocket enters.", "text": "The rocket enters."},
          {"index": 1, "action": "The rocket climbs past the bulb.", "text": "The rocket climbs past the bulb."}]


def _pool(monkeypatch):
    rows = [{"file": f"cosmic/{i:02d}_{n.replace(' ', '_')}.jpg", "noun": n}
            for i, n in enumerate(["orb", "garlic bulb", "heron", "moth", "pear", "swan", "lantern", "comet"])]
    monkeypatch.setattr(mp, "manifest", lambda: {"cosmic": rows})
    monkeypatch.setattr(S, "grown", lambda: {})
    monkeypatch.setattr(S, "usage", lambda: {})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    return rows


def test_a_simple_cut_ignores_the_storyboard_words():
    director = mp._story_words({"idea": "", "scenes": ROCKET})
    simple = mp._story_words({"idea": "", "scenes": ROCKET, "mode": "simple"})
    assert "rocket" in director and "bulb" in director
    assert simple == []  # nothing typed, nothing read
    assert mp._idea_words({"idea": "A heron over the marsh", "brief": "cold-blue dusk", "scenes": ROCKET}) == ["a", "heron", "over", "the", "marsh", "cold", "blue", "dusk"]


def test_the_storyboard_no_longer_names_the_family_of_a_simple_cut(monkeypatch):
    _pool(monkeypatch)
    # Director mode as before: the storyboard's "bulb" names the fruit family and the garlic bulb leads
    _, director = mp.pick_stills({"vibe": "cosmic", "scenes": ROCKET}, 3, record=False)
    assert director[0]["noun"] == "garlic bulb"
    # Simple mode with nothing typed: the storyboard is not read, the vibe decides, no bulb at the front
    _, simple = mp.pick_stills({"vibe": "cosmic", "scenes": ROCKET, "mode": "simple"}, 3, record=False)
    assert simple[0]["noun"] != "garlic bulb"


def test_the_idea_line_outranks_the_storyboard_in_either_mode(monkeypatch):
    _pool(monkeypatch)
    for mode in ("simple", "director"):
        state = {"vibe": "cosmic", "idea": "a heron over the marsh", "scenes": ROCKET, "mode": mode}
        _, picked = mp.pick_stills(state, 3, record=False)
        assert picked[0]["noun"] == "heron", mode  # the typed word opens the cut, whatever the storyboard says
        words = S.content_words(mp._idea_words(state))
        assert S.family_named("cosmic", words) == S.family_of("heron")


def test_the_grow_for_an_idea_reads_the_typed_words_first(monkeypatch):
    asked = []
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": True})
    monkeypatch.setattr(S, "grow", lambda vibe, count, *, nouns=None, **kw: (asked.append((vibe, list(nouns or []))), {"kept": len(nouns or [])})[1])
    state = {"vibe": "cosmic", "idea": "a moth circles the lamp", "scenes": ROCKET, "mode": "simple", "seed": 1}
    got = dense.grow_family_for_cut(state, "cosmic", 12, None, engine="ltx095")
    if got:
        assert got["family"] == S.family_of("moth") and all(S.family_of(n) == S.family_of("moth") for n in asked[0][1])


def test_the_making_screen_shows_the_chain_and_the_field_says_what_it_does():
    app = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    making = app.split('if (easy.phase === "making")')[1].split("easy-make-grid")[0]
    assert "state.chain" in making and "storySentence(scene.action)" not in making
    assert 'eyebrow">${esc(storyLabel)}' in app and "The chain: ${chainStills.length} stills" in app
    assert 'placeholder="Name an object or a family: a chrome moth, lanterns, sea creatures. Empty, and the vibe decides."' in app
    assert "The line picks the objects" in app and "Other words change nothing yet" in app
