"""The idea line shapes the cut (26 Oct, ``xenoform.idea``): the rule parser (scenes, objects, own shapes, Polly), the
model's refinement, the make-body shaping, what a Make grows for the line, the pick's lead, Polly on the short demo, the
route and the desk. The still pools are mocked the way tests/test_scenes.py and tests/test_review_26oct.py mock them."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from xenoform import beatfx, dense, idea, morph_pass as mp, stills as S
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo.wav"
RAVE = "girl dancing to rave music in a cyber punk city outside wearhouse, lazers"
CITY = "cyberpunk city outside a warehouse with lasers"


def _row(vibe: str, name: str, noun: str, **extra) -> Path:
    """A grown still on disk and in stills.json (the conftest points XENO_STILLS at a temp dir)."""
    path = S.root() / vibe / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), (20, 20, 30)).save(path)
    idx = S._read_json(S.index_path(), {})
    idx.setdefault(vibe, []).append({"file": f"{vibe}/{name}", "noun": noun, **extra})
    S._write_json(S.index_path(), idx)
    return path


# ---------------------------------------------------------------------------------------------- the parser


def test_the_rave_line_reads_as_a_scene_a_shape_and_polly_dancing():
    r = idea.read(RAVE, "cosmic", llm=False)
    assert r["scenes"] == ["a " + CITY]
    assert r["own"] == ["laser"] and r["objects"] == [] and r["family"] == ""  # "rave music" names no music box
    assert r["performer"] == {"style": "dance", "cue": "girl dancing"}
    assert r["summary"] == f"Scenes: a {CITY}. Objects: laser (new shape). Polly: dancing."
    assert r["source"] == "rules" and r["line"] == RAVE


def test_catalogue_words_still_open_the_cut_and_name_the_family():
    r = idea.read("a chrome moth circles a neon sign", "chrome-mercury", llm=False)
    assert r["objects"] == ["moth"] and r["family"] == S.family_of("moth") and not r["scenes"] and r["performer"] is None
    assert idea.read("lanterns", "cosmic", llm=False)["objects"] == ["lantern"]  # a plural names its noun
    fam = idea.read("sea creatures", "cosmic", llm=False)
    assert fam["family"] == "sea-creatures" and fam["scenes"] == [] and fam["own"] == []  # a family's label is not the sea
    assert fam["summary"] == "Objects: sea creatures (the family)."
    chess = idea.read("a chess game played by machines", "chrome-mercury", llm=False)
    assert chess["family"] == S.family_named("chrome-mercury", {"chess", "game", "machines"})  # the pick's own lookup
    assert idea.read("jellyfish, octopus and a nautilus under the sea", "ocean", llm=False)["objects"] == ["jellyfish", "octopus", "nautilus"]


def test_places_and_their_light_become_scene_subjects():
    r = idea.read("singing in the rain on a rooftop", "neon-noir", llm=False)
    assert r["scenes"] == ["a rooftop in the rain"] and r["performer"]["style"] == "sing"
    assert idea.read("a pyramid in the desert at dusk", "cosmic", llm=False)["scenes"] == ["the desert at dusk"]
    assert idea.read("under a red moon", "cosmic", llm=False)["scenes"] == ["a red moon"]
    two = idea.read("a neon alley, a rooftop in the rain", "neon-noir", llm=False)
    assert two["scenes"] == ["a neon alley", "a rooftop in the rain"]
    kept = idea.read("cold-blue dusk over a flooded car park, a vintage car", "cosmic", llm=False)
    assert kept["scenes"] == ["cold-blue dusk over a flooded car park"] and kept["objects"] == ["vintage car"]
    assert idea.read("a heron over the marsh", "cosmic", llm=False)["scenes"] == ["the marsh"]


def test_typed_things_the_catalogue_lacks_are_shapes_and_instruments_alone_are_not_polly():
    r = idea.read("a brass astrolabe, a wolf skull", "cosmic", llm=False)
    assert r["objects"] == ["astrolabe"] and r["own"] == ["wolf skull"]
    assert idea.read("a grand piano", "cosmic", llm=False)["performer"] is None
    assert idea.read("drums on a rooftop", "cosmic", llm=False)["performer"] is None
    assert idea.read("a girl", "cosmic", llm=False)["performer"] == {"style": "auto", "cue": "girl"}
    assert idea.read("a woman playing keys in an empty cathedral", "cosmic", llm=False)["performer"]["style"] == "keys"
    assert idea.read("a dancer in a neon alley, strobes", "cosmic", llm=False)["own"] == ["strobe light"]
    assert idea.read("", "cosmic", llm=False) == idea.EMPTY and idea.read("   ", "cosmic", llm=False)["summary"] == ""
    assert idea.singular("butterflies") == "butterfly" and idea.singular("glass") == "glass" and idea.singular("lasers") == "laser"


def test_the_model_refines_the_reading_when_asked(monkeypatch):
    from xenoform import llm

    answer = {"scenes": ["a cyberpunk city street outside a warehouse, lasers"], "objects": ["laser", "moth", "a girl"],
              "performer": {"style": "dance"}}
    monkeypatch.setattr(llm, "chat", lambda system, user, schema=None, **kw: json.dumps(answer))
    r = idea.read(RAVE, "cosmic", llm=True)
    assert r["source"] == "llm" and r["scenes"] == ["a cyberpunk city street outside a warehouse, lasers"]
    assert r["objects"] == ["moth"] and r["own"] == ["laser"]  # the catalogue's words are objects; a person is never a shape
    assert r["family"] == S.family_of("moth") and r["performer"]["style"] == "dance"
    monkeypatch.setattr(llm, "chat", lambda *a, **k: None)
    assert idea.read(RAVE, "cosmic", llm=True)["source"] == "rules"  # the model down: the rules reading

    def boom(*a, **k):
        raise RuntimeError("no model")

    monkeypatch.setattr(llm, "chat", boom)
    assert idea.read(RAVE, "cosmic", llm=True)["source"] == "rules"
    monkeypatch.delenv("XENO_LLM_URL", raising=False)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: json.dumps(answer))
    assert idea.read(RAVE, "cosmic")["source"] == "rules"  # not asked unless XENO_LLM_URL is set
    monkeypatch.setenv("XENO_LLM_URL", "http://127.0.0.1:1/v1")
    assert idea.read(RAVE, "cosmic")["source"] == "llm"


# ---------------------------------------------------------------------------------------------- the make


def test_shape_state_turns_scenes_and_polly_on_without_overriding_a_choice():
    r = idea.read(RAVE, "cosmic", llm=False)
    base = {"vibe": "cosmic", "idea": RAVE, "mode": "simple"}
    got = idea.shape_state(base, r)
    assert got["scene_stills"] == "mix" and got["performer"] == idea.PERFORMER_DEFAULT and got["performer_style"] == "dance"
    assert got["idea_reading"] == r and "scene_stills" not in base  # a copy
    chosen = idea.shape_state({**base, "scene_stills": "only", "performer": 4, "performer_style": "keys"}, r)
    assert chosen["scene_stills"] == "only" and chosen["performer"] == 4 and chosen["performer_style"] == "keys"
    auto = idea.shape_state({**base, "performer": 4}, r)
    assert auto["performer"] == 4 and auto["performer_style"] == "dance"  # Auto takes the cue
    director = idea.shape_state({**base, "mode": "director"}, r)
    assert "idea_reading" not in director and "performer" not in director
    sung = idea.shape_state({"vibe": "cosmic", "idea": "singing in the rain on a rooftop"})
    assert sung["performer_style"] == "sing" and sung["scene_stills"] == "mix" and sung["performer"] == idea.PERFORMER_DEFAULT
    plain = idea.shape_state({"vibe": "cosmic", "idea": "a chrome moth"})
    assert "performer" not in plain and "scene_stills" not in plain
    assert idea.reading_for({"vibe": "cosmic", "scenes": [{"action": "the rocket climbs"}]}) == idea.EMPTY  # no line, nothing read
    assert idea.reading_for(got) is r  # the make body carries its reading


def test_the_grow_plan_asks_for_the_typed_scenes_and_shapes_the_pool_lacks():
    r = idea.read(RAVE, "cosmic", llm=False)
    plan = idea.grow_plan(r, "cosmic")
    assert plan["scenes"] == [CITY] * idea.SCENES_PER_SUBJECT
    assert plan["own"] == ["laser"] and plan["nouns"] == [] and plan["count"] == idea.SCENES_PER_SUBJECT + 1
    assert plan["seconds"] == int(S.estimate_seconds(plan["count"]))
    _row("cosmic", "090_scene.jpg", CITY, kind="scene")
    _row("cosmic", "091_laser.jpg", "laser", own=True)
    assert idea.grow_plan(r, "cosmic")["count"] == 0  # the pool has both now
    noun = next(n for n in ("moth", "astrolabe", "orrery", "teapot") if n not in S.nouns_in("cosmic"))
    one = idea.grow_plan(idea.read(f"a chrome {noun}", "cosmic", llm=False), "cosmic")
    assert one["nouns"] == [noun] and one["scenes"] == [] and one["own"] == []
    assert idea.grow_plan(idea.EMPTY, "cosmic")["count"] == 0 and idea.grow_plan(r, "")["count"] == 0


def test_run_simple_grows_for_the_line_the_way_it_grows_a_family(monkeypatch):
    asked = []
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": True})
    monkeypatch.setattr(S, "grow", lambda vibe, count, *, nouns=None, own=False, kind="object", **kw:
                        (asked.append((vibe, kind, own, list(nouns or []))), {"kept": len(nouns or []), "files": []})[1])
    r = idea.read(RAVE, "cosmic", llm=False)
    state = {"vibe": "cosmic", "idea": RAVE, "mode": "simple"}
    got = dense.grow_for_idea(state, "cosmic", None, engine="ltx095", reading=r)
    assert got["asked"] == idea.SCENES_PER_SUBJECT + 1 and got["kept"] == got["asked"]
    assert asked[0] == ("cosmic", "scene", False, [CITY] * idea.SCENES_PER_SUBJECT)
    assert asked[1] == ("cosmic", "object", True, ["laser"])
    assert got["scenes"]["kept"] == idea.SCENES_PER_SUBJECT and got["own"]["kept"] == 1
    assert dense.grow_for_idea(state, "cosmic", None, engine="mock", reading=r) is None
    assert dense.grow_for_idea({**state, "auto_grow": False}, "cosmic", None, engine="ltx095", reading=r) is None
    assert dense.grow_for_idea({"vibe": "cosmic", "idea": ""}, "cosmic", None, engine="ltx095") is None
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": False})
    assert dense.grow_for_idea(state, "cosmic", None, engine="ltx095", reading=r) is None
    # the family grow reads the line's family first ("a chrome moth": insects), as the pick does
    assert S.family_of("moth") == idea.read("a chrome moth", "cosmic", llm=False)["family"]


def test_the_pick_opens_on_the_typed_scene_and_leads_with_the_typed_shape(monkeypatch):
    rows = [{"file": f"cosmic/{i:02d}_{n.replace(' ', '_')}.jpg", "noun": n} for i, n in enumerate(["orb", "comet", "heron", "moth", "pear", "swan"])]
    monkeypatch.setattr(mp, "manifest", lambda: {"cosmic": rows})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    _row("cosmic", "050_shore.jpg", "dark shore under a star field", kind="scene")
    _row("cosmic", "051_city.jpg", CITY, kind="scene")
    _row("cosmic", "052_astrolabe.jpg", "brass astrolabe", own=True)
    _row("cosmic", "053_laser.jpg", "laser", own=True)
    state = idea.shape_state({"vibe": "cosmic", "idea": RAVE, "mode": "simple"})
    assert state["scene_stills"] == "mix"
    _, picked = mp.pick_stills(state, 6, record=False)
    assert picked[0]["noun"] == CITY  # the typed place opens the cut
    assert picked[1]["noun"] == "laser" and picked[2]["noun"] == "brass astrolabe"  # the typed shape leads your own shapes
    # without the line the older scene opens and the astrolabe leads, as before
    _, plain = mp.pick_stills({"vibe": "cosmic", "scene_stills": "mix", "mode": "simple"}, 6, record=False)
    assert plain[0]["noun"] == "dark shore under a star field" and plain[1]["noun"] == "brass astrolabe"


def test_run_simple_on_the_short_demo_lets_polly_in_when_the_line_asks(monkeypatch, tmp_path):
    seen, calls = {}, []
    monkeypatch.delenv("XENO_LLM_URL", raising=False)
    monkeypatch.setattr(dense, "stills_for", lambda state, n, **kw: ("cosmic", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(n)]))
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))])

    def fake_render(audio_path, slot, vibe, still, work, cfg, *, seed, report=None, beats=None, source=None):
        calls.append((slot["instrument"], round(slot["seconds"], 2), Path(still).name))
        clip = Path(work) / f"perf_{slot['first']}.mp4"
        clip.parent.mkdir(parents=True, exist_ok=True)
        clip.write_bytes(b"mp4")
        return {"clip": clip, "frames": int(round(slot["seconds"] * 24)), "seconds": slot["seconds"], "sync": 0.8, "tries": 1}

    monkeypatch.setattr(dense, "_render_performer", fake_render)

    def fake_compose(clips, shots, audio, out, **kw):
        seen["clips"] = [Path(c).name for c in clips]
        seen["shots"] = shots
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    step = 60.0 / 148.0
    directed = {"duration": 12.0, "beats": [round(i * step, 4) for i in range(int(12.0 / step))]}
    state = {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "idea": RAVE}
    info = dense.run_simple(directed, DEMO, tmp_path / "x.mp4", tmp_path, {}, state, lambda *a: None, engine="mock")
    assert len(calls) == 1 and calls[0][0] == "dance" and calls[0][2].startswith("polly")  # one slot, the first passage
    assert dense.PERFORMER_MIN_S <= calls[0][1] < 7.0  # about half the clip (whole shots): the morphs keep the other half
    assert len(dense.performer_slots(dense.shots_for(state, directed, DEMO)[0], 2, None, "dance")) == 1  # the long-song cap stays 8 s
    assert dense.performer_slots(dense.shots_for(state, directed, DEMO)[0], 2, None, "dance")[0]["seconds"] > 6.0
    assert info["performer"]["shots"] == 1 and info["idea"]["performer"]["style"] == "dance"
    assert info["scene_mode"] == "mix" and info["recut_state"]["performer"] == idea.PERFORMER_DEFAULT
    assert info["recut_state"]["performer_style"] == "dance" and info["recut_state"]["scene_stills"] == "mix"
    assert sum(1 for s in seen["shots"] if s.get("performer")) == 1 and seen["clips"][0] == "perf_0.mp4"
    record = json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert record["idea"]["summary"].startswith("Scenes: a cyberpunk city") and record["idea"]["own"] == ["laser"]
    assert not any("grown_for_line" in n for n in record["fallbacks"])  # a mock render grows nothing
    # the same clip with no line: no performer (a short clip never had one), nothing read
    calls.clear()
    info2 = dense.run_simple(directed, DEMO, tmp_path / "y.mp4", tmp_path / "y", {}, {**state, "idea": ""}, lambda *a: None, engine="mock")
    assert not calls and info2["idea"] is None and info2["performer"]["shots"] == 0 and info2["scene_mode"] == "off"
    # a Director render carries the Simple desk's line without having been typed for it: untouched
    calls.clear()
    info3 = dense.run_simple(directed, DEMO, tmp_path / "z.mp4", tmp_path / "z", {}, {**state, "mode": "director"}, lambda *a: None, engine="mock")
    assert not calls and info3["idea"] is None


# ---------------------------------------------------------------------------------------------- the desk


def test_the_desk_route_reads_the_line_and_says_what_make_grows(monkeypatch):
    monkeypatch.delenv("XENO_LLM_URL", raising=False)
    client = TestClient(create_app())
    r = client.post("/api/simple/idea", json={"idea": RAVE, "vibe": "cosmic"})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"].startswith(f"Scenes: a {CITY}.")
    assert body["performer"]["style"] == "dance" and body["grow"]["own"] == ["laser"] and body["grow"]["count"] >= 2
    assert body["pool_vibe"] == "cosmic" and body["grow"]["seconds"] > 0
    empty = client.post("/api/simple/idea", json={"idea": "", "vibe": "cosmic"}).json()
    assert empty["summary"] == "" and empty["grow"]["count"] == 0
    chain = client.post("/api/simple/chain", json={"audio_id": "demo", "vibe": "cosmic", "idea": RAVE, "mode": "simple",
                                                   "scene_stills": "off", "energy_preset": "dense", "aspect": "9:16"})
    assert chain.status_code == 200 and chain.json()["scene_mode"] == "mix"  # the preview follows the line


def test_the_desk_shows_the_reading_under_the_line_and_on_the_making_screen():
    app = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    assert 'id="easy-idea-reading"' in app and "/api/simple/idea" in app and "function scheduleIdea" in app
    assert 'placeholder="A place, an object, a dancer:' in app and "The line shapes the cut" in app
    assert "Your line, read:" in app and "Read as: ${have.summary}" in app
    handler = app.split('target.id === "easy-idea"')[1].split("} else if")[0]
    assert "scheduleIdea()" in handler
    css = (ROOT / "src/xenoform/ui_static/app.css").read_text(encoding="utf-8")
    assert ".idea-reading" in css


def test_a_feel_group_sets_the_knobs_and_the_look():
    # 27 Oct (Pause's demo: "Then say how it should feel"): a comma group of feel words is the cut's feel, not a thing
    from xenoform import idea

    r = idea.read("a moth, a wet street at night, slow and dreamy", "neon-noir", llm=False)
    assert r["feel"]["words"] == ["slow", "dreamy"] and r["feel"]["macros"]["speed"] < 0.3 and r["feel"]["macros"]["glow"] > 0.7
    assert "dreamy" not in " ".join(r["own"] + r["objects"] + r["scenes"]) and "Feel: slow, dreamy" in r["summary"]
    hard = idea.read("hard and glitchy, electric", "neon-noir", llm=False)["feel"]
    assert hard["macros"]["chaos"] > 0.7 and hard["macros"]["intensity"] > 0.8 and hard["look"] == "cyan-flash"
    assert idea.read("very fast", "", llm=False)["feel"]["macros"]["speed"] > idea.read("fast", "", llm=False)["feel"]["macros"]["speed"]
    # only a whole group of feel words counts: a dark lake is a place, a hard hat is a thing
    assert idea.read("a moth on a dark lake", "neon-noir", llm=False)["feel"] is None
    assert idea.read("a hard hat", "neon-noir", llm=False)["feel"] is None
    # a call with no knobs (MCP, the CLI) takes the line's; the desk's own knobs and a picked Look are kept
    st = idea.shape_state({"idea": "a moth, hard and glitchy, electric", "vibe": "neon-noir"})
    assert st["macros"]["chaos"] > 0.7 and st["dance_fx"] == "cyan-flash"
    st = idea.shape_state({"idea": "a moth, hard and glitchy", "vibe": "neon-noir", "macros": {"chaos": 0.1}, "dance_fx": "warm-leak"})
    assert st["macros"] == {"chaos": 0.1} and st["dance_fx"] == "warm-leak"


def test_the_desk_moves_the_knobs_once_for_a_feel():
    app = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    apply = app.split("function applyFeel(data) {", 1)[1].split("\n}\n", 1)[0]
    assert "state.easy.feelSig === sig" in apply and "window.XENO_MACRO_SET(k, Number(v))" in apply
    assert "render()" not in apply  # painted in place: a render would take the caret out of the line
    saved = app.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0]
    assert '"feelSig"' in saved and "applyFeel(data);" in app and "Then how it should feel: slow and dreamy." in app
