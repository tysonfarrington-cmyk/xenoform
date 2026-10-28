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


@pytest.mark.parametrize("line,kind", [("racing", "theme"), ("a wet street at night", "Scenes:"), ("slow and dreamy", "Feel:")])
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
