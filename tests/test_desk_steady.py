"""28 Oct, Tys's round on the desk: nothing moves under you, one Apply, Edit in Resolve opens the pack, Setup never
hangs, plain Variations with a single Draft, the Final reads its text encoder once a prompt, and the Fast Final."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")


def _fn(start: str, end: str) -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def test_a_redraw_keeps_every_scrolled_panel_and_the_row_you_are_on():
    remember = _fn("function rememberPlace()", "function restorePlace(")
    assert "rememberScrollers(app)" in remember and "rememberAnchor(app)" in remember
    restore = _fn("function restorePlace(place)", "function render()")
    assert "restoreScrollers(app, place.scrollers)" in restore and "restoreAnchor(app, place.anchor)" in restore
    # the anchor is the control clicked (Foreshadow's Trace), never the scrolled column it sits in
    key = _fn("function anchorKey(node)", "function scrollerKey(")
    assert "data-value" in key and "data-act" in key
    assert "if (box === node) return;" in _fn("function restoreAnchor(app, anchor)", "function rememberPlace()")


def test_a_redraw_never_fades_the_desk_only_a_new_screen_does():
    # found recording the walkthrough, 29 Oct: every click blanked the desk and slid it 4 px (the fade-in on #app's children)
    css = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert "#app > * { animation" not in css and "#app[data-enter] > * { animation: xd-in" in css
    draw = _fn("function render()", "function renderTool(")
    assert "if (screen !== lastScreen) app.dataset.enter" in draw and "delete app.dataset.enter" in draw
    assert draw.index("app.dataset.enter") < draw.index("app.innerHTML")


def test_a_running_grow_rewrites_its_line_instead_of_redrawing_the_desk():
    load = _fn("async function loadStills(force)", "async function growStills(")
    assert 'getElementById("library-status")' in load and "stillsStatus(state.easy)" in load and "return;" in load
    row = _fn("function stillsRow(easy)", "async function")
    assert 'id="library-status"' in row and "const note = status ||" not in row  # the note never swaps for the status


def test_setup_survives_a_new_song_and_never_waits_on_a_check_nobody_started():
    adopt = _fn("function adoptSession(data, options = {})", "\n}\n")
    assert "setup: previous ? previous.setup || null : null" in adopt
    setup = _fn("function renderSetup()", "const tier = setup.tier")
    assert "loadSetup().then(" in setup and "setup.failed" in setup and 'data-act="check-extra"' in setup


def test_the_making_screen_paints_the_renders_own_chain_and_step():
    paint = _fn("function paintMaking(job)", "function paintJob()")
    assert "job.chain" in paint and 'getElementById("easy-chain-label")' in paint and "#easy-happen li" in paint
    assert "paintMaking(job);" in _fn("async function poll(id)", 'document.addEventListener("click"')


def test_one_apply_for_the_knobs_and_the_timeline():
    assert '"easy-look": "Look"' in APP and '"easy-foreshadow": "Foreshadow"' in APP
    assert 'document.addEventListener("xeno-knobs"' in APP
    assert 'CustomEvent("xeno-knobs")' in (STATIC / "ui_v6.js").read_text(encoding="utf-8")
    assert 'act === "easy-tl-apply" || act === "easy-apply"' in APP
    assert 'id="pending-dock"' not in APP and 'dock.id = "pending-dock"' in APP  # docked on the body, never mid-page


def test_the_cut_column_never_runs_under_the_knobs_and_the_knobs_fold():
    css = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert ".easy-result { display: grid; grid-template-columns: minmax(0, 1fr);" in css
    assert 'body[data-knobs="folded"] .easy-done' in css and ".lane-playhead" in css
    assert 'data-act="easy-knobs-fold"' in APP and "paintPlayhead();" in _fn("function render()", "function renderTool(")


def test_edit_in_resolve_opens_the_pack_where_it_is(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import edit_export, ui

    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "xenoform-abc.xml").write_text("<xmeml/>")
    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path)
    job = tmp_path / "jobs" / "abc12345"
    job.mkdir(parents=True)
    (job / "xenoform.mp4").write_bytes(b"mp4")
    monkeypatch.setattr(edit_export, "build", lambda folder_, vid: {"folder": str(folder), "timeline": "xenoform-abc.xml"})
    opened = []
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: opened.append(args))
    got = TestClient(ui.create_app()).post("/api/videos/abc12345/edit/reveal").json()
    assert got["opened"] and got["timeline"] == "xenoform-abc.xml" and opened
    assert "easyEditOpen(id)" in APP and "Open the folder again" in APP and "File › Import › Timeline" in APP


def test_the_desk_code_revalidates_so_a_restart_needs_no_hard_reload():
    from fastapi.testclient import TestClient

    from xenoform import ui

    client = TestClient(ui.create_app())
    assert client.get("/static/app.js").headers.get("cache-control") == "no-cache"
    assert client.get("/static/desk.css").headers.get("cache-control") == "no-cache"
    assert client.get("/static/vibes/neon-noir.jpg").headers.get("cache-control") == "no-cache"  # the tiles change with the library


def test_variations_queue_one_draft_and_say_so_in_plain_words():
    from xenoform import batch

    assert batch.COUNTS == (1, 3, 5, 10)
    one = batch.variations({"vibe": "cosmic"}, 1, "seed")
    assert len(one) == 1 and one[0]["kind"] == "draft"
    row = _fn("function variationsRow(easy)", "async function loadBatchRates")
    assert '[["1", "1"], ["3", "3"], ["5", "5"], ["10", "10"]], "How many"' in row
    assert '[["seed", "New objects"], ["vibe", "Other vibes"], ["feel", "Other feels"]], "What changes"' in row
    assert "Make is not affected." in row


def test_scene_subjects_end_on_a_whole_word():
    from xenoform import idea, stills

    assert stills.clip_words("a canyon of birds until the thread holds", 30) == "a canyon of birds until the"
    assert stills.clip_words("x" * 50, 40) == "x" * 40
    r = idea.read("A bridge novice and a red thread cross from a kitchen into a canyon of birds until the thread holds.", "liquid-gold")
    assert all(not s.endswith(" unt") for s in r["scenes"])


def test_a_described_noun_names_its_family_by_its_head_only():
    from xenoform import stills

    assert stills.noun_keys("seashell holding a tiny city") == {"seashell"}
    assert stills.noun_keys("dragon skull with curling horns") == {"skull"}
    assert stills.noun_keys("sea turtle") == {"sea", "turtle"}
    assert stills.family_named("cosmic", {"city", "things"}) == ""


def test_the_library_grew_six_families_of_richer_subjects():
    fams = json.loads((ROOT / "configs" / "subjects.json").read_text(encoding="utf-8"))["families"]
    for key in ("high-fantasy", "grimdark", "intricate-machines", "strange-and-surreal", "living-things", "big-iconic"):
        nouns = fams[key]["nouns"]
        assert len(nouns) == 30 == len(set(nouns))
        assert all(len(n) <= 40 for n in nouns)


def test_the_chain_preview_counts_what_a_hand_set_count_renders():
    from fastapi.testclient import TestClient

    from xenoform import ui

    client = TestClient(ui.create_app())
    auto = client.get("/api/simple/chain?vibe=cosmic").json()
    forty = client.post("/api/simple/chain", json={"vibe": "cosmic", "morph_count": 40}).json()
    assert forty["count"] <= auto["count"] + 1 < 41


# --------------------------------------------------------------------------------------------- the Final, faster


def test_the_final_renders_shots_that_share_a_prompt_back_to_back(tmp_path, monkeypatch):
    from xenoform import final_tier as ft
    from xenoform import morph_pass as mp

    monkeypatch.setattr(mp, "wait_or_cancel", lambda job, jobs, cancel, poll_s=0.4: None)
    stills = []
    for i, kind in enumerate(["object", "object", "scene", "object", "object"]):
        p = tmp_path / f"s{i}.png"
        p.write_bytes(b"png")
        stills.append({"path": str(p), "noun": f"n{i}", "file": p.name, "kind": kind})
    seen = []

    class Out:
        type = "video"

        def to_file(self, dest):
            Path(dest).write_bytes(b"mp4")

    class Result:
        outputs = [Out()]

        def get_outputs(self, node):
            return self.outputs

    class Job:
        id = "j"
        status = "succeeded"

        def result(self):
            return Result()

    class WF:
        def __init__(self, g):
            self.g = g

        def set_input(self, *a):
            pass

    class Client:
        assets = type("A", (), {"from_file": staticmethod(lambda p: p)})()
        workflows = type("W", (), {"from_json": staticmethod(lambda g: WF(g))})()

        def submit(self, wf):
            seen.append((wf.g["4"]["inputs"]["text"], wf.g["14"]["inputs"]["noise_seed"]))
            return Job()

    shots = [{"render_s": 2, "seconds": 1.0} for _ in range(4)]
    clips, _ = ft.final_clips(shots, stills, tmp_path, {}, 100, "black", client=Client())
    texts = [t for t, _ in seen]
    assert len(set(texts)) == 3 and texts.index(texts[0]) == 0
    twice = next(t for t in texts if texts.count(t) == 2)
    same = [k for k, t in enumerate(texts) if t == twice]
    assert same == [same[0], same[0] + 1]  # shots 1 and 4, object to object, render one after the other
    assert sorted(s for _, s in seen) == [100, 101, 102, 103]  # each keeps its own seed
    assert [c.name for c in clips] == ["final00.mp4", "final01.mp4", "final02.mp4", "final03.mp4"]


def test_fast_final_is_a_draft_upscaled_to_full_size():
    from xenoform import batch, dense, upscale_pass

    opt = dense.options({"quality_tier": "fast"})
    assert opt["tier"] == "draft" and opt["fast"] is True
    assert dense.options({"quality_tier": "final"})["fast"] is False
    g = upscale_pass.graph(1080, 1920)
    assert g["1"]["class_type"] == "LoadVideo" and g["6"]["class_type"] == "ImageUpscaleWithModel"
    assert g["7"]["inputs"]["width"] == 1080 and g["7"]["inputs"]["height"] == 1920 and g["9"]["class_type"] == "SaveVideo"
    assert upscale_pass.out_size("9:16") == (1080, 1920) and upscale_pass.out_size("16:9") == (1920, 1080)
    assert dense.estimate(10, "fast")["seconds"] > dense.estimate(10, "draft")["seconds"]
    assert '["fast", "Fast Final"]' in APP


def test_fast_final_cuts_are_measured_apart_from_drafts(tmp_path):
    from xenoform import batch

    for name, rec in (("a", {"tier": "draft"}), ("b", {"tier": "draft", "fast": True})):
        d = tmp_path / name / "simple"
        d.mkdir(parents=True)
        (d / "simple.json").write_text(json.dumps({**rec, "shots": [{"end": 20.0}]}))
        (tmp_path / name / "took.json").write_text(json.dumps({"took_s": 300 if name == "a" else 900}))
    got = batch._measure(tmp_path, 20.0)
    assert got["draft"]["eta_s"] == 300 and got["fast"]["eta_s"] == 900


def test_an_upscale_that_fails_keeps_the_draft_clip(tmp_path, monkeypatch):
    from xenoform import morph_pass as mp
    from xenoform import upscale_pass

    monkeypatch.setattr(mp, "wait_or_cancel", lambda job, jobs, cancel, poll_s=0.4: None)

    class Client:
        assets = type("A", (), {"from_file": staticmethod(lambda p: p)})()
        workflows = type("W", (), {"from_json": staticmethod(lambda g: type("WF", (), {"set_input": lambda self, *a: None})())})()

        def submit(self, wf):
            raise RuntimeError("out of memory")

    clip = tmp_path / "local00.mp4"
    clip.write_bytes(b"mp4")
    out, notes = upscale_pass.upscale_clips([clip], tmp_path, (1080, 1920), {}, client=Client())
    assert out == [clip] and notes[0]["fallback"] == "draft-size"


@pytest.mark.parametrize("line,kind", [("underwater", "theme"), ("a wet street at night", "Scenes:"), ("slow and dreamy", "Feel:")])
def test_the_idea_lines_examples_read_as_their_kind(line, kind):
    from xenoform import idea

    assert kind in idea.read(line, "neon-noir")["summary"]


# ------------------------------------------------------------------------------------------------ clip morphs


def _clip(path, n, size, value):
    import numpy as np

    from xenoform.video import write_mp4

    write_mp4(path, [np.full((size[1], size[0], 3), value, np.uint8) for _ in range(n)], 24)
    return path


def test_a_clip_slot_opens_and_closes_on_a_morph(tmp_path, monkeypatch):
    from PIL import Image

    from xenoform import cloud_morph, dense, own_media
    from xenoform.video import probe_video, read_all_frames

    assert own_media.morph_frames(96, 24) == (18, 18) and own_media.morph_frames(30, 24) == (10, 10)
    assert own_media.morph_frames(96, 24, into=False) == (0, 18)
    body = _clip(tmp_path / "body.mp4", 60, (540, 960), 120)
    stills = []
    for i in range(4):
        p = tmp_path / f"s{i}.png"
        Image.new("RGB", (320, 576), (i * 40, 0, 0)).save(p)
        stills.append({"path": str(p), "noun": f"n{i}", "file": p.name})
    asked = []

    def fake_local(shots, pair, work, cfg, seed, vibe, **kw):
        asked.append([s.get("kind") or "object" for s in pair])
        return [_clip(Path(work) / "local00.mp4", 25, kw["size"], 200)]

    monkeypatch.setattr(cloud_morph, "_local_clips", fake_local)
    shots = [{"morph": i} for i in range(3)]
    slot = {"first": 1, "last": 1, "start": 2.0}
    out = dense._clip_morphs(body, tmp_path / "own.mp4", slot, shots, stills, 18, 18, tmp_path, {}, 1, "cosmic", None, None, {},
                             {"aspect": "9:16"}, True, 24)
    assert asked == [["object", "scene"], ["scene", "object"]]  # into the clip, then out of it
    assert probe_video(out)["frames"] == 18 + 60 + 18
    frames = read_all_frames(out)
    assert frames[5].mean() > 180 and abs(float(frames[40].mean()) - 120) < 10 and frames[-3].mean() > 180


def test_clip_morphs_are_on_for_your_clips_and_can_be_turned_off():
    src = (ROOT / "src" / "xenoform" / "dense.py").read_text(encoding="utf-8")
    block = src.split("clip_morph = engine in", 1)[1].split("notes.append({\"own\": own_info})", 1)[0]
    assert 'state.get("clip_morph", "on")' in block and "_clip_morphs(" in block
    assert "own_media.render_clip(sl[\"clip\"], start_s, frames_needed, " in block  # a failed morph falls back to the whole clip


# ------------------------------------------------------------------------------------- colour and effects per shot


def test_a_shot_takes_its_own_colour_and_effects_through_a_recut_override():
    import numpy as np

    from xenoform import dense
    from xenoform import effects as E

    f = np.full((2, 2, 3), [200, 100, 50], np.uint8)
    assert np.array_equal(E.grade(f, {}), f) and E.grade_of({"hue": 400, "contrast": 0}) == {"hue": 180.0}
    assert E.grade(f, {"saturation": -1})[0, 0].std() < 1  # no colour left
    warm = E.grade(np.full((2, 2, 3), 120, np.uint8), {"warmth": 1})[0, 0]
    assert warm[0] > 120 > warm[2]
    so = dense.shot_overrides_of({"2": {"grade": {"hue": 30, "warmth": 0}, "effects": ["kaleido", "nope"]}, "3": {"effects": []}}, 5)
    assert so == {2: {"grade": {"hue": 30.0}, "effects": ["kaleido"]}, 3: {"effects": []}}
    shots = [{"frames": 24, "effects": [{"type": "punch", "at": 0.0}]} for _ in range(5)]  # a shot's beat FX live in "effects"
    dense.apply_timeline(shots, so, {}, vibe="cosmic", house=None, transitions=None, boundary_fx=None, beats=[], fps=24, drop=None)
    assert shots[2]["grade"] == {"hue": 30.0} and shots[2]["fx_names"] == ["kaleido"] and shots[3]["fx_names"] == []
    assert shots[2]["effects"] == [{"type": "punch", "at": 0.0}]  # the beat FX untouched (28 Oct: they once clashed)
    assert E.wants_tones("auto", [], [{"fx_names": ["dither"]}])


def test_the_compositor_plans_every_shots_effects_and_runs_each_its_own():
    import inspect

    from xenoform import beatfx

    comp = inspect.getsource(beatfx.compose)
    assert 'shot_fx = sorted({str(x) for s in shots for x in (s.get("fx_names") or [])})' in comp and 'fx_cfg["cut"]' in comp
    frames = inspect.getsource(beatfx._shot_frames)
    assert '"fx_names" in shot' in frames and "_E.grade(" in frames


def test_the_drawer_has_colour_sliders_and_effects_chips():
    drawer = _fn("function timelineDrawer(easy, lane, tl, picked)", "// A shot's own colour")
    assert "${shotColourRows(o, s.index)}" in APP and "${shotEffectsRow(o, s.index)}" in APP
    rows = _fn("const GRADE_ROWS = ", "// The drawer under the timeline")
    assert '"hue", "Hue"' in rows and '"warmth", "Warmth"' in rows and 'data-act="easy-tl-effect"' in rows and "As the cut" in rows
    assert 'target.classList.contains("tl-grade-in")' in APP and 'act === "easy-tl-grade-clear"' in APP
    assert drawer is not None


# ------------------------------------------------------------------------------------------------ chains with a theme


def _grown_row(vibe, name, noun, **extra):
    from PIL import Image

    from xenoform import stills as S

    path = S.root() / vibe / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 36), (20, 20, 30)).save(path)
    idx = S._read_json(S.index_path(), {})
    idx.setdefault(vibe, []).append({"file": f"{vibe}/{name}", "noun": noun, **extra})
    S._write_json(S.index_path(), idx)


def test_a_theme_keeps_the_whole_chain_on_its_things(monkeypatch):
    from xenoform import idea
    from xenoform import morph_pass as mp

    racing = idea.THEMES["racing"]["things"]
    assert len(racing) == 15
    monkeypatch.setattr(mp, "manifest", lambda: {"cosmic": [{"file": f"cosmic/{i:02d}.jpg", "noun": n} for i, n in
                                                            enumerate(["orb", "comet", "heron", "moth", "pear", "swan", "peony", "kettle"])]})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    for i, thing in enumerate(racing):
        _grown_row("cosmic", f"1{i:02d}.jpg", thing, own=True)
    _grown_row("cosmic", "200_pearl.jpg", "pearl", own=True)  # grown for another line: never the opener of this one
    state = idea.shape_state({"vibe": "cosmic", "idea": "car rally racing", "mode": "simple"})
    _, picked = mp.pick_stills(state, 16, record=False)
    assert {p["noun"] for p in picked} <= set(racing)  # no peony, kettle or pearl among the racing things
    _, plain = mp.pick_stills({"vibe": "cosmic", "mode": "simple"}, 6, record=False)
    assert plain[0]["noun"] != "pearl"


def test_a_cut_with_no_line_stays_in_one_realm_of_a_big_library(monkeypatch):
    from xenoform import morph_pass as mp
    from xenoform import stills as S

    assert S.realm_of("grimdark") == "dark fantasy" and S.realm_of("flowers") == "garden" and S.realm_of("nope") == ""
    fams = S.subjects()["families"]
    monkeypatch.setattr(mp, "manifest", lambda: {"cosmic": []})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    k = 0
    for fam in ("grimdark", "high-fantasy", "flowers", "sea-creatures", "intricate-machines", "celestial-bodies"):
        for noun in fams[fam]["nouns"][:9]:
            _grown_row("cosmic", f"{k:03d}.jpg", noun)
            k += 1
    assert k >= S.REALM_LIBRARY
    _, picked = mp.pick_stills({"vibe": "cosmic", "mode": "simple", "seed": 3}, 10, record=False)
    realms = {S.realm_of(S.family_of(p["noun"])) for p in picked}
    assert len(realms) == 1 and "" not in realms


# ------------------------------------------------------------------------------------------------ order edits


def test_order_edits_move_duplicate_drop_and_trim_on_the_recut():
    from xenoform import dense

    def plan():
        return [{"frames": 24, "morph": i} for i in range(5)]

    clips = [f"c{i}.mp4" for i in range(5)]
    so = dense.shot_overrides_of({"1": {"source": 2}, "2": {"source": 1}, "4": {"drop": True}, "3": {"source": 3}}, 5)
    assert so == {1: {"source": 2}, 2: {"source": 1}, 4: {"drop": True}}  # its own index is no source
    bo = dense.boundary_overrides_of({"1": {"shift": 0.25}, "3": {"shift": 9}}, 5)
    assert bo == {1: {"shift": 0.25}, 3: {"shift": dense.SHIFT_MAX_S}}
    laid = dense.arrange_shots(plan(), clips, so, bo, 24, transitions=[None] * 5, boundary_fx=[None] * 5)
    assert laid["clips"] == ["c0.mp4", "c2.mp4", "c1.mp4", "c3.mp4"] and laid["kept"] == [0, 1, 2, 3]
    frames = [s["frames"] for s in laid["shots"]]
    assert frames[0] == 30 and frames[1] == 18  # the cut into shot 2 moved a quarter second later
    assert frames[2] == 24 + 18 and frames[3] == 6 + 24  # 4 s clamps at the shot's last 6 frames; shot 5's time went to 4
    assert sum(frames) == 120 and laid["shots"][1]["morph"] == 2 and len(laid["transitions"]) == 4
    rec = laid["record"]
    assert len(rec) == 5 and rec[4]["dropped"] and rec[4]["frames"] == 0 and rec[4]["start"] == rec[4]["end"] == 5.0
    dup = dense.arrange_shots(plan(), clips, {3: {"source": 2}}, {}, 24)
    assert dup["clips"][2] == dup["clips"][3] == "c2.mp4"
    first = dense.arrange_shots(plan(), clips, {0: {"drop": True}}, {}, 24)
    assert first["kept"] == [1, 2, 3, 4] and first["shots"][0]["frames"] == 48  # the first shot's time goes to the next


def test_the_drawer_offers_the_order_edits_and_the_lane_shows_a_deleted_shot():
    assert "${shotOrderRow(lane, tl, s)}" in APP and "${cutShiftRow(lane, tl, s)}" in APP
    for act in ("easy-tl-move", "easy-tl-dup", "easy-tl-drop", "easy-tl-shift", "easy-tl-source-clear"):
        assert f'act === "{act}"' in APP, act
    lane = (ROOT / "src" / "xenoform" / "lane.py").read_text(encoding="utf-8")
    assert 'row["dropped"] = True' in lane and 'row["plays"]' in lane
    assert "dropped" in _fn("function shotsLane(easy)", "async function loadLane")


def test_the_final_upscales_from_a_quarter_and_the_estimate_says_where_the_time_goes():
    from xenoform import dense
    from xenoform import final_tier as ft

    g = ft.graph("x", length=49, seed=1, width=448, height=768, out_w=1080, out_h=1920)
    assert g["43"]["inputs"]["width"] == 270 and g["43"]["inputs"]["height"] == 480 and g["41"]["inputs"]["image"] == ["43", 0]
    assert dense.COST["final_916"]["s"] == 270.0
    tip = _fn("const TIME_PARTS = {", "function morphEstimate(")
    assert "reading the prompt: 1 min" in tip and "the 4x upscale" in tip and "Fast Final" in tip
    assert 'class="note time-tip" title="${esc(timeTip(tier))}"' in APP


def test_the_lane_builds_for_a_cut_with_your_own_clip_and_a_moved_morph():
    from xenoform import lane

    info = {"stills": ["cosmic/00_orb.jpg", "cosmic/01_moth.jpg", "cosmic/02_pear.jpg"],
            "shots": [{"start": 0.0, "end": 2.0, "own": True, "source": "01_caligari_cesare.mp4"},  # an own clip's file name
                      {"start": 2.0, "end": 3.0, "morph": 0, "plays": 0},
                      {"start": 3.0, "end": 3.0, "morph": 1, "dropped": True}]}
    rows = lane.build(info)["shots"]
    assert rows[0].get("own") and "plays" not in rows[0] and rows[1]["plays"] == 0 and rows[2]["dropped"]


def test_your_clip_plays_its_busiest_stretch_not_blank_sky(tmp_path):
    import numpy as np

    from xenoform import own_media
    from xenoform.video import write_mp4

    rng = np.random.default_rng(0)
    flat = [np.full((72, 128, 3), 90, np.uint8) for _ in range(24 * 6)]  # six seconds of sky
    busy = [rng.integers(0, 255, (72, 128, 3)).astype(np.uint8) for _ in range(24 * 4)]  # then four of picture
    clip = tmp_path / "reel.mp4"
    write_mp4(clip, flat + busy, 24)
    assert own_media.window_start(10.0, 3.0) == 3.5
    assert own_media.busiest_start(clip, 10.0, 3.0) >= 6.0
    assert own_media.busiest_start(tmp_path / "missing.mp4", 10.0, 3.0) == 3.5  # unreadable: the middle, as before
