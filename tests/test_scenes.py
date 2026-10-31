"""Scenes (26 Oct 2026): a second kind of still beside the single-object pools, so a Simple cut can morph scenes and not
only objects. The catalogue (configs/scenes.json, the ``scene`` prefix), the relaxed checks, the grow with kind, the pick
under "mix" and "only", the record, the desk route and the front end."""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from xenoform import dense, morph_pass as mp, stills as S

W, H = 512, 288
FEATURED = ["chrome-mercury", "neon-noir", "porcelain-kintsugi", "bioluminescent", "risograph", "iridescent-glass", "liquid-gold",
            "ink-wash", "cyberspace-95", "wet-paint", "shadow-self", "botanical", "cosmic"]


def _object(path: Path, *, cx=0.5, cy=0.5, r=0.2, noise=3) -> Path:
    """A synthetic object still: a disc on a plain dark backdrop, a little noise so sharpness is not zero."""
    im = Image.new("RGB", (W, H), (8, 8, 10))
    d = ImageDraw.Draw(im)
    rr = r * H
    d.ellipse((cx * W - rr, cy * H - rr, cx * W + rr, cy * H + rr), fill=(170, 175, 180))
    a = np.asarray(im).astype(np.int16)
    rng = np.random.default_rng(int(cx * 1000 + cy * 100 + r * 10))
    a = np.clip(a + rng.integers(-noise, noise + 1, a.shape), 0, 255).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path)
    return path


def _scene(path: Path, *, seed: int = 0, blur: float = 0.0) -> Path:
    """A synthetic scene: a gradient sky over a textured ground, shapes reaching every edge, no centred subject."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    horizon = 0.3 + 0.4 * ((seed * 0.618) % 1.0)  # the horizon and the light move with the seed, so two scenes differ
    bright = 0.6 + 0.8 * ((seed * 0.371) % 1.0)
    sky = np.stack([20 + 40 * yy / H, 10 + 20 * yy / H, 60 + 90 * yy / H], axis=-1) * bright
    ground = (yy > H * (horizon + 0.05 * np.sin(xx / (30.0 + seed))))[..., None]
    a = np.where(ground, np.array([30, 40, 70]) * bright + 50 * rng.random((H, W, 1)), sky)
    for _ in range(12):  # rocks and ridges, some touching the edges
        x0, y0 = int(rng.integers(0, W)), int(rng.integers(int(H * horizon), H + 40))
        w, h = int(rng.integers(40, 220)), int(rng.integers(30, 140))
        a[max(0, y0 - h):y0, x0:x0 + w] = [20 + rng.integers(0, 140)] * 3
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def _grown(vibe: str, name: str, noun: str, *, kind: str = "object", scene_seed: int = 0) -> Path:
    """A grown still on disk and in stills.json (the conftest points XENO_STILLS at a temp dir)."""
    path = S.root() / vibe / name
    (_scene(path, seed=scene_seed) if kind == "scene" else _object(path))
    idx = S._read_json(S.index_path(), {})
    row = {"file": f"{vibe}/{name}", "noun": noun}
    if kind == "scene":
        row["kind"] = "scene"
    idx.setdefault(vibe, []).append(row)
    S._write_json(S.index_path(), idx)
    return path


# ---------------------------------------------------------------------------------------------- the catalogue


def test_every_featured_vibe_has_scene_subjects_and_a_scene_prefix():
    data = json.loads(S.SCENES.read_text(encoding="utf-8"))
    prompts = S.prompts()
    bad_words = ("person", "people", "woman", "man ", "face", "text", "letters", "logo")
    for vibe in FEATURED:
        subjects = data["vibes"][vibe]
        assert 4 <= len(subjects) <= 8, vibe
        assert len(set(subjects)) == len(subjects), vibe
        assert all(not any(w in s.lower() for w in bad_words) for s in subjects), vibe
        prefix = prompts[vibe]["scene"]
        assert "no people" in prefix and "no text" in prefix and "no single centred object" in prefix, vibe
        assert "wide" in prefix.lower(), vibe
    assert 4 <= len(data["default"]) <= 8
    assert S.scene_list("some-new-vibe") == [S.clean_noun(n, S.SCENE_NOUN_LIMIT) for n in data["default"]]


def test_scene_prompts_are_wide_and_fall_back_to_the_look():
    cosmic = S.prompt_for("cosmic", "dark shore under a star field", "scene")
    assert cosmic.startswith(S.prompts()["cosmic"]["scene"]) and cosmic.endswith("Dark shore under a star field, seen wide.")
    assert "one single" not in cosmic.lower()
    # a registry vibe with no scene prefix: its look in front of the wide-frame tail
    other = S.prompt_for("ferrofluid", "black dunes", "scene")
    assert other.startswith("Cinematic wide establishing shot, ") and S.SCENE_TAIL in other and other.endswith("Black dunes, seen wide.")
    assert S.prompt_for("cosmic", "orb") == S.prompt_for("cosmic", "orb", "object")  # objects as before


def test_scene_nouns_skip_the_rendered_ones_then_go_round_again():
    rows = S.scene_list("cosmic")
    assert S.scene_nouns_for("cosmic", 2) == rows[:2]
    assert S.scene_nouns_for("cosmic", 3, have={rows[0]}) == rows[1:4]
    again = S.scene_nouns_for("cosmic", len(rows) + 2)
    assert again[:len(rows)] == rows and again[len(rows):] == rows[:2]  # a second pass on a new seed, never empty
    assert sorted(S.scene_nouns_for("cosmic", len(rows), seed=3)) == sorted(rows)
    assert S.plan("cosmic", kind="scene")["nouns"] == S.scene_nouns_for("cosmic", S.DEFAULT_GROW_SCENES)
    assert S.plan("cosmic", kind="scene")["kind"] == "scene" and S.plan("cosmic", 5)["kind"] == "object"


def test_counts_and_catalogue_tell_scenes_from_objects():
    _grown("cosmic", "000_shore.jpg", "dark shore under a star field", kind="scene")
    _grown("cosmic", "001_astrolabe.jpg", "astrolabe")
    n = len(S.shipped()["cosmic"])
    assert S.counts("cosmic") == {"shipped": n, "grown": 1, "own": 0, "scenes": 1, "settings": 0, "total": n + 2}
    assert S.scene_nouns_in("cosmic") == {"dark shore under a star field"} and "dark shore under a star field" not in S.nouns_in("cosmic")
    rows = S.catalogue()["cosmic"]
    assert [S.kind_of(r) for r in rows].count("scene") == 1 and S.kind_of(rows[0]) == "object"


# ---------------------------------------------------------------------------------------------- the relaxed checks


def test_a_scene_fails_the_object_checks_and_passes_the_scene_checks(tmp_path):
    pool = [_object(tmp_path / f"p{i}.png", cx=0.35 + 0.06 * i, r=0.2 + 0.012 * i) for i in range(6)]
    prof = S.profile(pool)
    scene = _scene(tmp_path / "scene.png", seed=1)
    as_object = S.check(scene, prof)
    assert not as_object["ok"] and set(as_object["why"]) and set(as_object["why"]) <= {"backdrop", "size", "cropped"}
    as_scene = S.check(scene, prof, kind="scene")
    assert as_scene["ok"] and as_scene["why"] == [] and as_scene["backdrop"] == 0.0
    soft = S.check(_scene(tmp_path / "soft.png", seed=1, blur=9.0), prof, kind="scene")
    assert soft["why"] == ["soft"]
    twice = S.check(_scene(tmp_path / "again.png", seed=1), prof, kind="scene", extra_greys=[as_scene["grey"]])
    assert twice["why"] == ["duplicate"]


def test_ingest_keeps_a_scene_unzoomed_and_marks_the_row(tmp_path, monkeypatch):
    zoomed = []
    monkeypatch.setattr(S, "normalise_scale", lambda im: (zoomed.append(1), im)[1])
    src = _scene(tmp_path / "shore.png", seed=4)
    v = S.ingest("cosmic", src, "dark shore under a star field", kind="scene")
    assert v["kept"] and v["file"].startswith("cosmic/000_dark_shore") and not zoomed  # no zoom on a scene
    row = S.grown()["cosmic"][0]
    assert row["kind"] == "scene" and row["noun"] == "dark shore under a star field"
    again = S.ingest("cosmic", src, "dark shore under a star field", kind="scene")
    assert not again["kept"] and again["why"] == ["duplicate"]  # the second copy is a duplicate of the first scene
    obj = S.ingest("cosmic", _object(tmp_path / "orb.png", r=0.22), "orb")
    assert obj["kept"] and zoomed and "kind" not in S.grown()["cosmic"][-1]  # an object still zooms and carries no kind
    assert S.counts("cosmic")["scenes"] == 1


class _FakeClient:
    """A comfy-sdk client that renders a synthetic scene per prompt (the shape test_stills.py's fake uses)."""

    def __init__(self):
        self.prompts, self.seeds = [], []

    class _WF:
        def __init__(self, outer):
            self.inputs = {}

        def set_input(self, node, name, value):
            self.inputs[(node, name)] = value

    class _Out:
        def __init__(self, k):
            self.k = k

        def to_file(self, path):
            _scene(Path(path), seed=10 + self.k)

    class _Job:
        def __init__(self, k):
            self.k = k

        def result(self):
            job = self

            class R:
                outputs = []

                def get_outputs(self, node):
                    return [_FakeClient._Out(job.k)]

            return R()

    @property
    def workflows(self):
        outer = self

        class WFs:
            def from_file(self, path):
                assert Path(path).name == "zimage_t2i_api.json"
                return _FakeClient._WF(outer)

        return WFs()

    def submit(self, wf):
        self.prompts.append(wf.inputs[(S.N_TEXT, "text")])
        self.seeds.append(wf.inputs[(S.N_SEED, "seed")])
        return _FakeClient._Job(len(self.prompts) - 1)


def test_grow_with_kind_scene_renders_the_scene_prompts_and_lists_scenes():
    fake = _FakeClient()
    res = S.grow("cosmic", 3, client=fake, seed=7, kind="scene", sheet=True)
    assert res["kind"] == "scene" and res["asked"] == 3 and res["kept"] == 3 and res["rejected"] == {}
    assert len(set(res["nouns"])) == 3 and set(res["nouns"]) <= set(S.scene_list("cosmic"))  # a seeded grow shuffles the fresh list
    assert all(p.startswith(S.prompts()["cosmic"]["scene"]) and p.endswith(", seen wide.") for p in fake.prompts)
    rows = S.grown()["cosmic"]
    assert [r["kind"] for r in rows] == ["scene"] * 3 and Path(res["sheet"]).name == "scenes.jpg"
    n = len(S.shipped()["cosmic"])
    assert S.counts("cosmic") == {"shipped": n, "grown": 0, "own": 0, "scenes": 3, "settings": 0, "total": n + 3}
    # the next scene grow moves on to the subjects not rendered yet, in list order
    assert S.plan("cosmic", 2, kind="scene")["nouns"] == [n for n in S.scene_list("cosmic") if n not in res["nouns"]][:2]


# ---------------------------------------------------------------------------------------------- the pick


def _mock_pool(monkeypatch, n_objects=12, n_scenes=4, vibe="cosmic"):
    objects = [{"file": f"{vibe}/{i:02d}_thing{i}.jpg", "noun": f"thing{i}"} for i in range(n_objects)]
    scenes = [{"file": f"{vibe}/{100 + i:03d}_scene{i}.jpg", "noun": f"scene {i}", "kind": "scene"} for i in range(n_scenes)]
    monkeypatch.setattr(mp, "manifest", lambda: {vibe: objects})
    monkeypatch.setattr(S, "grown", lambda: {vibe: scenes} if n_scenes else {})
    monkeypatch.setattr(S, "usage", lambda: {})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    return objects, scenes


def test_the_choice_reads_scene_stills_or_a_string_scenes_key():
    assert mp.scenes_choice({}) == "off" and mp.scenes_choice(None) == "off"
    assert mp.scenes_choice({"scene_stills": "MIX"}) == "mix" and mp.scenes_choice({"scene_stills": "weird"}) == "off"
    assert mp.scenes_choice({"scenes": "only"}) == "only"  # the make body key as a string
    assert mp.scenes_choice({"scenes": [{"index": 0, "end": 2.0}]}) == "off"  # the Advanced desk's scene list is not a choice
    assert mp._story_words({"scenes": "mix", "idea": "a moth"}) == ["a", "moth"]  # a string scenes key breaks no reader


def test_scene_slots_follow_the_passage_changes_else_every_fourth():
    shots = [{"section": "intro"}, {"section": "intro"}, {"section": "build", "boundary": "switch"}, {"section": "build"},
             {"section": "drop", "boundary": "drop"}, {"section": "drop"}, {"section": "outro"}]
    assert mp.scene_slots(shots, 8, "mix") == [0, 2, 4, 6]
    assert mp.scene_slots(shots, 8, "mix", assign=[0, 1, 2, 3, 4, 5, 6]) == [0, 2, 4, 6]
    assert mp.scene_slots(shots, 5, "mix") == [0, 2, 4]  # past the chain's end, a slot is dropped
    plain = [{"start": float(i)} for i in range(9)]
    assert mp.scene_slots(plain, 10, "mix") == [0, 4, 8] and mp.scene_slots([], 6, "mix") == [0, 4]
    assert mp.scene_slots(shots, 4, "only") == [0, 1, 2, 3] and mp.scene_slots(shots, 4, "off") == []


def test_mix_puts_scenes_on_the_slots_and_objects_between_with_no_repeats(monkeypatch):
    _mock_pool(monkeypatch)
    state = {"vibe": "cosmic", "scene_stills": "mix"}
    _, picked = mp.pick_stills(state, 9, record=False, scene_at=[0, 3, 6])
    kinds = [S.kind_of(p) for p in picked]
    assert kinds == ["scene", "object", "object", "scene", "object", "object", "scene", "object", "object"]
    assert len({p["file"] for p in picked}) == 9
    # more slots than scenes: the extra slots are objects, no scene twice
    _, picked = mp.pick_stills(state, 12, record=False, scene_at=[0, 2, 4, 6, 8, 10])
    assert [S.kind_of(p) for p in picked].count("scene") == 4 and len({p["file"] for p in picked}) == 12
    assert [S.kind_of(p) for p in picked][:8] == ["scene", "object"] * 4
    # no slots given: the every-fourth default
    _, picked = mp.pick_stills(state, 9, record=False)
    assert [i for i, p in enumerate(picked) if S.kind_of(p) == "scene"] == [0, 4, 8]


def test_only_draws_on_scene_rows_and_off_never_draws_a_scene(monkeypatch):
    _mock_pool(monkeypatch)
    _, only = mp.pick_stills({"vibe": "cosmic", "scene_stills": "only"}, 4, record=False)
    assert all(S.kind_of(p) == "scene" for p in only) and len({p["file"] for p in only}) == 4
    _, off = mp.pick_stills({"vibe": "cosmic"}, 13, record=False)
    assert all(S.kind_of(p) == "object" for p in off)  # thirteen stills over twelve objects: the walk repeats, no scene leaks in
    _, off2 = mp.pick_stills({"vibe": "cosmic", "scene_stills": "off"}, 6, record=False)
    assert all(S.kind_of(p) == "object" for p in off2)


def test_a_pool_with_no_scenes_cuts_objects_only(monkeypatch):
    _mock_pool(monkeypatch, n_scenes=0)
    _, picked = mp.pick_stills({"vibe": "cosmic", "scene_stills": "mix"}, 6, record=False, scene_at=[0, 3])
    assert all(S.kind_of(p) == "object" for p in picked) and len({p["file"] for p in picked}) == 6
    _, only = mp.pick_stills({"vibe": "cosmic", "scene_stills": "only"}, 6, record=False)
    assert all(S.kind_of(p) == "object" for p in only)


def test_the_long_song_chain_lands_a_scene_on_each_passage_change(monkeypatch, tmp_path):
    _mock_pool(monkeypatch, n_objects=30, n_scenes=6)
    labels = ["intro", "calm", "build", "drop", "calm", "build", "drop", "outro"]
    duration, period = 238.8, 0.4
    step = duration / len(labels)
    sections = [{"label": lab, "start": round(i * step, 3), "end": round((i + 1) * step, 3)} for i, lab in enumerate(labels)]
    beats = [round(i * period, 4) for i in range(int(duration / period))]
    directed = {"duration": duration, "beats": beats, "sections": sections, "drop": 119.6}
    state = {"vibe": "cosmic", "energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16", "scene_stills": "mix"}
    shots, plan = dense.shots_for(state, directed, tmp_path / "song.wav")
    shots, plan, chain, notes = dense.long_song_chain(state, directed, tmp_path / "song.wav", shots, plan, dense.options(state), engine="mock")
    slots = mp.scene_slots(shots, chain["morphs"] + 1, "mix", assign=chain["assign"])
    changes = [int(chain["assign"][i]) for i, s in enumerate(shots) if i and s.get("boundary")]
    assert slots and set(changes) <= set(slots) and 0 in slots
    _, picked = mp.pick_stills(state, chain["morphs"] + 1, record=False, scene_at=slots)
    scene_idx = [i for i, p in enumerate(picked) if S.kind_of(p) == "scene"]
    assert scene_idx == slots[:6] and len({p["file"] for p in picked}) == chain["morphs"] + 1
    # "only" counts the scene rows as the pool, so the chain is capped to what the six scenes afford
    only = {**state, "scene_stills": "only"}
    shots_o, plan_o = dense.shots_for(only, directed, tmp_path / "song.wav")
    _, _, chain_o, _ = dense.long_song_chain(only, directed, tmp_path / "song.wav", shots_o, plan_o, dense.options(only), engine="mock")
    assert chain_o["morphs"] == 5


def test_only_skips_the_grow_for_an_idea(monkeypatch):
    asked = []
    monkeypatch.setattr(S, "available", lambda cfg: {"ok": True})
    monkeypatch.setattr(S, "grow", lambda *a, **kw: (asked.append(1), {"kept": 0})[1])
    assert dense.grow_family_for_cut({"vibe": "chrome-mercury", "idea": "a moth", "scene_stills": "only"}, "chrome-mercury", 12, None,
                                     engine="ltx095") is None
    assert not asked


# ---------------------------------------------------------------------------------------------- the morph prompt


def test_a_pair_that_touches_a_scene_gets_the_scene_prompt_and_the_plain_chain_keeps_its_own():
    plain = mp.prompt_for("cosmic")
    assert plain == mp.prompt_for("cosmic", kinds=("object", "object")) and "the object stays centred" in plain
    look = mp.VIBE_LOOK["cosmic"]
    for kinds in (("scene", "object"), ("object", "scene"), ("scene", "scene")):
        text = mp.prompt_for("cosmic", kinds=kinds)
        assert "wide landscape scene" in text and look in text and "the picture never cuts" in text
        assert "the object stays centred" not in text and "macro product photography" not in text
    assert mp.prompt_for("cosmic", "ltx25", ("scene", "object")).startswith("Use the provided start image")
    assert mp.pair_kinds({"kind": "scene"}, {}) == ("scene", "object") and mp.pair_kinds(None, {"kind": "scene"}) == ("object", "scene")


def test_the_draft_path_gives_scene_morphs_their_prompt_and_an_uncompressed_guide(tmp_path, monkeypatch):
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(mp, "autotune", lambda: {"vibes": {"cosmic": {"steps": 12, "img_compression": 18}}})
    wfs = []

    class WF:
        def __init__(self):
            self.inputs = {}

        def set_input(self, node, key, value):
            self.inputs[(node, key)] = value

    class Stop(Exception):
        pass

    class Job:
        def result(self):
            raise Stop()

    class Client:
        class assets:
            @staticmethod
            def from_file(path):
                return path

        class workflows:
            @staticmethod
            def from_file(path):
                wf = WF()
                wfs.append(wf)
                return wf

        def submit(self, wf):
            return Job()

    stills = [{"path": "a.png", "kind": "scene"}, {"path": "b.png"}, {"path": "c.png"}, {"path": "d.png", "kind": "scene"}]
    shots = [{"seconds": 2.0, "render_s": 2} for _ in range(3)]
    try:
        cm._local_clips(shots, stills, tmp_path, {}, 1, "cosmic", client=Client())
    except Stop:
        pass
    assert len(wfs) == 3
    texts = [wf.inputs[("3", "text")] for wf in wfs]
    assert "wide landscape scene" in texts[0] and "wide landscape scene" not in texts[1] and "wide landscape scene" in texts[2]
    assert [wf.inputs[("8", "img_compression")] for wf in wfs] == [0, 18, 18]   # the start guide: a scene stays uncompressed
    assert [wf.inputs[("21", "img_compression")] for wf in wfs] == [18, 18, 0]  # the end guide


# ---------------------------------------------------------------------------------------------- the record


def test_run_simple_records_which_stills_were_scenes_and_the_recut_keeps_the_choice(tmp_path, monkeypatch):
    from xenoform import beatfx
    import xenoform.cloud_morph as cm

    scene_names = {f"ocean/{100 + i:03d}_scene{i}.jpg" for i in range(3)}
    for i in range(3):
        _grown("ocean", f"{100 + i:03d}_scene{i}.jpg", f"scene {i}", kind="scene", scene_seed=20 + i)
    rendered: dict = {}

    def fake_mock(shots, stills, work, w, h):
        rendered["stills"] = stills
        return [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))]

    def fake_compose(clips, shots, audio, out, **kw):
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}}

    monkeypatch.setattr(cm, "_mock_clips", fake_mock)
    monkeypatch.setattr(beatfx, "compose", fake_compose)
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo.wav"
    info = dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, demo, tmp_path / "x.mp4", tmp_path, {},
                            {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "scene_stills": "mix"},
                            lambda *a: None, engine="mock")
    assert info["scene_mode"] == "mix" and info["scene_files"] and set(info["scene_files"]) <= set(info["stills"])
    assert set(info["scene_files"]) <= scene_names and info["recut_state"]["scene_stills"] == "mix"
    assert len(set(info["stills"])) == len(info["stills"])
    idx = [i for i, f in enumerate(info["stills"]) if f in info["scene_files"]]
    assert idx[0] == 0 and all(b - a >= 2 for a, b in zip(idx, idx[1:]))  # a scene opens the cut, objects between
    rec = json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert rec["scene_mode"] == "mix" and rec["scene_files"] == info["scene_files"]
    # off: the scenes stay out of the chain, and the record says so
    plain = dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, demo, tmp_path / "y.mp4", tmp_path / "y", {},
                             {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense"},
                             lambda *a: None, engine="mock")
    assert plain["scene_mode"] == "off" and plain["scene_files"] == [] and not scene_names & set(plain["stills"])
    # mix on a vibe with no scenes: objects only, with a note
    bare = dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, demo, tmp_path / "z.mp4", tmp_path / "z", {},
                            {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "scene_stills": "mix"},
                            lambda *a: None, engine="mock")
    assert bare["scene_files"] == [] and any("scenes" in n for n in bare["fallbacks"])


# ---------------------------------------------------------------------------------------------- the desk


def test_desk_routes_grow_scenes_and_count_them(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())
    got = client.get("/api/stills?vibe=cosmic").json()
    assert got["default_grow_scenes"] == S.DEFAULT_GROW_SCENES and got["scene_subjects"] == len(S.scene_list("cosmic"))
    assert got["have"]["scenes"] == 0
    monkeypatch.setattr(S, "available", lambda cfg=None, **kw: {"ok": True, "note": ""})
    calls = {}

    def fake_grow(vibe, count=36, *, nouns=None, own=False, cfg=None, seed=None, progress=None, cancel=None, client=None, sheet=True,
                  kind="object"):
        calls.update({"vibe": vibe, "count": count, "nouns": nouns, "own": own, "kind": kind})
        progress(1, 1, 1)
        return {"vibe": vibe, "kind": kind, "asked": 1, "made": 1, "kept": 1, "rejected": {}, "files": [], "seconds": 1.0, "nouns": nouns}

    monkeypatch.setattr(S, "grow", fake_grow)
    try:
        started = client.post("/api/stills/grow", json={"vibe": "cosmic", "kind": "scene"}).json()
        # eight asked of a six-scene list: the six, then the list again on new seeds
        assert started["ok"] and started["kind"] == "scene" and started["nouns"] == S.scene_nouns_for("cosmic", S.DEFAULT_GROW_SCENES)
        import time as _t

        for _ in range(50):
            job = client.get("/api/stills").json()["job"]
            if job.get("status") == "done":
                break
            _t.sleep(0.05)
        assert job["status"] == "done" and job["kind"] == "scene" and job["kept"] == 1
        assert calls["kind"] == "scene" and calls["count"] == S.DEFAULT_GROW_SCENES and calls["own"] is False
    finally:
        with _ui._LOCK:
            _ui._STILLS_JOB.clear()


def test_the_job_body_takes_scenes_as_a_string_alias(monkeypatch):
    """The make body's ``scenes`` is the Advanced desk's scene list; a string there is the Simple choice."""
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    seen = {}
    monkeypatch.setattr(_ui, "_run_job", lambda job_id, audio_path, body, cfg, out, cancel_event=None: seen.update(body))
    client = TestClient(_ui.create_app())
    r = client.post("/api/generate", json={"audio_id": "demo", "vibe": "cosmic", "mode": "simple", "scenes": "mix", "tiny": True})
    assert r.status_code == 200, r.text
    assert seen.get("scene_stills") == "mix" and "scenes" not in seen
    with _ui._LOCK:
        _ui._JOBS.clear()


def test_front_end_has_the_scenes_chip_and_choice():
    js = (Path(mp.OBJECTS).parents[0] / "app.js").read_text(encoding="utf-8")
    assert 'data-act="easy-grow-scenes"' in js and "Grow ${growScenes} scenes" in js and 'kind: scenes ? "scene" : "object"' in js
    assert "function scenesRow(easy)" in js and js.count("${scenesRow(easy)}") == 2 and 'simpleSeg("easy-scenes"' in js
    assert 'act === "easy-scenes"' in js
    payload = js.split("function payload()")[1].split("function renderSetup")[0]
    assert 'scene_stills: (state.easy && state.easy.scenes) || "off"' in payload
    assert '"scenes"' in js.split("const EASY_SAVED_KEYS")[1].split("\n")[0]
