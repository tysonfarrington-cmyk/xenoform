"""UI v7: Simple mode is song, vibe, Make (the rest under Fine-tune); /api/vibes is the one vibe list;
the judges page is generated from the registry; Advanced gets per-boundary transitions and per-shot looks."""

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import vibes
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
JUDGES = (STATIC / "judges.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app())


# ---------------------------------------------------------------- /api/vibes

def test_api_vibes_is_the_single_source_of_truth(client):
    body = client.get("/api/vibes").json()
    rows = body["vibes"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    featured = [v["id"] for v in vibes.featured()]
    assert ids[: len(featured)] == featured and body["featured"] == featured
    assert set(vibes.ORIGINAL) <= set(ids) and body["original"] == list(vibes.ORIGINAL)
    for row in rows:
        for key in ("id", "name", "line", "tone", "dark", "still", "pool", "has_library", "library", "legacy", "featured"):
            assert key in row, (row["id"], key)
        assert row["still"] == f"/static/vibes/{row['id']}.jpg"
        assert row["legacy"] == (row["featured"] == 0)
        if row["has_library"]:
            assert row["library"] == row["id"]
        elif row["library"]:
            assert row["library"] == row["pool"] and vibes.has_library(row["pool"])
    assert {l["id"] for l in body["looks"]} == {"warm-leak", "cool-echo", "noir-glow", "bloom-rush", "negative-rush", "cyan-flash"}


def test_original_meta_matches_the_fallback_arrays_in_app_js():
    for meta in vibes.ORIGINAL_META:
        assert f'id: "{meta["id"]}"' in APP or f'"id": "{meta["id"]}"' in APP
        assert meta["name"] in APP and meta["line"] in APP
    assert [m["id"] for m in vibes.ORIGINAL_META] == list(vibes.ORIGINAL)


def test_app_js_fetches_the_catalogue_and_resolves_strips_through_pool():
    assert 'api("/api/vibes")' in APP and "async function loadVibes" in APP
    assert "let VIBES = V6_VIBES.concat(" in APP  # the fallback stays
    assert "function libraryFolder(vibe)" in APP
    assert "/static/library/${libraryFolder(vibe)}/${shot}.mp4" in APP
    assert "/static/library/${libraryFolder(vibe)}/${shot}.jpg" in APP
    assert "loadVibes()" in APP.split("async function boot()")[1]


# ---------------------------------------------------------------- Simple mode: song, vibe, Make

def test_simple_first_screen_is_three_decisions_with_fine_tune_behind_a_drawer():
    easy = APP.split("function renderEasy()")[1].split("// ---------------------------------------------------------------- Simple finishing")[0]
    assert "A song, a vibe, Make." in easy
    assert '<details class="fine-tune" id="fine-tune"' in APP and "<summary>Fine-tune" in APP
    # the drawer holds the finishing options, the cloud toggles and the recipe box; the first screen shows Make
    tune = APP.split("function fineTune(easy)")[1].split("const LOOK_PRESETS")[0]
    for part in ("${simpleOptions(easy)}", "${cloudToggles(easy)}", "${remixBox(easy)}"):
        assert part in tune
    assert easy.count("${simpleOptions(easy)}") == 0 and "${fineTune(easy)}" in easy
    assert 'readDrawer("xeno-finetune")' in APP and '"fine-tune": "xeno-finetune"' in APP
    # ui_v6.js keeps mounting the macro strip (knobs, stem reactions, MIDI) into .simple-opts, now inside the drawer
    v6 = (STATIC / "ui_v6.js").read_text(encoding="utf-8")
    assert 'document.querySelector(".simple-opts")' in v6


def test_simple_house_defaults_and_the_look_row():
    assert 'energyPreset: "dense", aspect: "9:16", tier: "draft", fx: true, endCard: false, danceFx: "auto", stemOrbit: true' in APP
    assert 'energy_preset: (state.easy && state.easy.energyPreset) || "dense"' in APP
    assert 'aspect: (state.easy && state.easy.aspect) || "9:16"' in APP
    assert 'dance_fx: (state.easy && state.easy.danceFx) || "auto"' in APP
    assert "stem_orbit: !(state.easy && state.easy.stemOrbit === false)" in APP
    for preset in ("warm-leak", "cool-echo", "noir-glow", "bloom-rush", "negative-rush", "cyan-flash"):
        assert f'"{preset}"' in APP
    assert 'lookRow(easy.danceFx || "auto", "easy-look")' in APP
    assert 'simpleSeg("easy-orbit"' in APP and "Subject orbit" in APP
    assert 'act === "easy-look"' in APP and 'act === "easy-orbit"' in APP
    # every option that used to sit on the first screen is still reachable inside the drawer
    opts = APP.split("function simpleOptions(easy)")[1].split("// Morph count")[0]
    for act in ("easy-energy", "easy-aspect", "easy-tier", "easy-fx", "easy-card", "easy-orbit"):
        assert act in opts, act
    assert "easy-look" in APP.split("simple-knobs-panel")[1].split("</section>")[0]  # the Look row moved to the front (v7.1)
    assert '["16:9", "16:9"], ["9:16", "9:16"], ["1:1", "1:1"]' in opts


def test_more_vibes_drawer_lists_the_legacy_vibes_in_simple():
    assert '<details class="more-vibes" id="more-vibes"' in APP
    assert 'vibeCards(easy, false, "legacy")' in APP and 'vibeCards(easy, false, "featured")' in APP
    assert "${moreVibes(easy)}" in APP
    # the old filter made legacy vibes unreachable in Simple (data-advanced never co-exists with Simple)
    assert 'return !vibe.legacy || vibe.id === easy.vibe || document.body.dataset.advanced === "1";' not in APP


def test_comfy_pill_shows_in_simple_and_links_to_vj_and_midi():
    assert 'body[data-advanced="0"] .comfy-status,\n' not in CSS
    assert 'body[data-advanced="0"] .comfy-status {' in CSS
    assert '<a href="/vj">VJ mode' in APP and 'data-act="easy-midi"' in APP
    assert "function openMidiDrawer()" in APP
    export = APP.split("function exportStep()")[1].split("function inspectorFor")[0]
    assert "Open in VJ with this song's stems" in export and 'data-act="mcp-copy"' in export and 'data-act="easy-midi"' in export


def test_about_text_is_honest_about_osc_vj_and_midi():
    assert "TouchDesigner OSC are under Advanced" not in INDEX
    assert "xenoform osc" in INDEX and 'href="/vj"' in INDEX and "MIDI" in INDEX


# ---------------------------------------------------------------- options timing, share

def test_simple_options_are_asked_with_the_real_tier_and_duration():
    assert "tier=final" not in APP
    fn = APP.split("async function loadSimpleOptions()")[1].split("function easyVideoId")[0]
    assert 'tier: easy.tier || "draft"' in fn and "duration: String(duration)" in fn
    assert "if (!duration) {" in fn
    for caller in ("async function useDemoSong()", "async function uploadSong(file)"):
        body = APP.split(caller)[1].split("\n}\n")[0]
        assert "adoptSession(" in body and "loadSimpleOptions()" in body, caller
    boot = APP.split("async function boot()")[1].split("\n}\n")[0]
    assert boot.index('api("/api/demo")') < boot.index("loadSimpleOptions()")


def test_simple_options_route_serves_the_looks_and_the_house(client):
    body = client.get("/api/simple/options?duration=30&energy=dense&tier=draft&aspect=9:16").json()
    assert body["house"] == {"aspect": "9:16", "energy": "dense", "tier": "draft", "dance_fx": "auto",
                             "stem_orbit": True, "beat_fx": True, "end_card": False}
    assert len(body["looks"]) == 6 and all(l["note"] for l in body["looks"])


def test_download_on_a_reopened_video_shares_that_job(client, tmp_path, monkeypatch):
    share = APP.split("async function shareCut(button)")[1].split("\n}\n")[0]
    assert "state.easy.reopenId" in share and "?job=${encodeURIComponent(jobId)}" in share
    reopen = APP.split('act === "video-open"')[1].split("} else if")[0]
    assert "state.job = { id: row.id" in reopen
    # the server resolves a saved job folder even when the job record is gone (desk restarted)
    from xenoform import ui as ui_mod

    monkeypatch.setattr(ui_mod, "work_dir", lambda: tmp_path)
    app = create_app()
    c = TestClient(app)
    job = tmp_path / "jobs" / "abcd1234"
    job.mkdir(parents=True)
    demo = ROOT / "examples" / "demo_base.mp4"
    (job / "xenoform.mp4").write_bytes(demo.read_bytes())
    seen = {}

    def fake_share(source, dest):
        seen["source"] = Path(source)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(b"\x00" * 10)
        return {"under": True}

    import xenoform.craft as craft

    monkeypatch.setattr(craft, "share_cut", fake_share)
    assert c.get("/api/share?job=abcd1234").status_code == 200
    assert seen["source"] == job / "xenoform.mp4"
    assert c.get("/api/share?job=nothere").status_code == 200
    assert seen["source"] == demo


# ---------------------------------------------------------------- stems_path injection

def test_generate_injects_the_cached_stems_path(client, tmp_path, monkeypatch):
    from xenoform import stems_api, ui as ui_mod

    stems = tmp_path / "stems.json"
    stems.write_text("{}", encoding="utf-8")
    captured = {}

    def fake_run_job(job_id, audio_path, body, cfg, out, cancel_event=None):
        captured["body"] = dict(body)
        with ui_mod._LOCK:
            ui_mod._JOBS[job_id]["status"] = "done"

    monkeypatch.setattr(ui_mod, "_run_job", fake_run_job)
    monkeypatch.setattr(stems_api, "stems_path_for", lambda song, **kw: stems if Path(song).name == "demo.wav" else None)
    started = client.post("/api/generate", json={"audio_id": "demo", "quality": "turbo", "mode": "simple", "vibe": "ocean",
                                                 "scene_transitions": [{"kind": "match-cut", "boundary": "switch", "index": 0}],
                                                 "scenes": [{"index": 0, "dance_fx": "noir-glow"}, {"index": 1}]})
    assert started.status_code == 200, started.text
    assert captured["body"]["stems_path"] == str(stems)
    job = client.get(f"/api/jobs/{started.json()['id']}").json()
    assert job["stems_path"] == str(stems)
    assert job["scene_transitions"] == ["match-cut"] and job["shot_looks"] == ["noir-glow", ""]
    # an explicit stems_path is kept
    monkeypatch.setattr(stems_api, "stems_path_for", lambda song, **kw: stems)
    client.post("/api/generate", json={"audio_id": "demo", "quality": "turbo", "stems_path": "C:/elsewhere/stems.json"})
    assert captured["body"]["stems_path"] == "C:/elsewhere/stems.json"


# ---------------------------------------------------------------- Advanced: transitions and looks

def test_advanced_transition_select_markup_and_payload_keys():
    assert 'api("/api/v1/transitions")' in APP and "async function loadTransitions()" in APP
    rows = APP.split("function transitionRows()")[1].split("function vjUrl()")[0]
    assert 'data-act="scene-transition"' in rows and 'aria-label="Transition from shot' in rows
    assert 'row.tier !== "classic"' in rows and "xeno-guard-expert" in rows  # classic only under Expert
    assert "const TRANSITION_MAX = 2;" in APP and 'TRANSITION_EXEMPT = ["cut", "scene-morph", "black-hold"]' in APP
    assert "clean beat cut" in rows  # the over-the-cap warning
    assert "function boundaryKind(index)" in APP and "function recommendedTransition(kind)" in APP
    assert "${transitionRows()}" in APP.split("function shotsStep()")[1].split("function exportStep()")[0]
    # payload: the boundary list guardrails consume, and scenes[i].transition / scenes[i].dance_fx
    payload = APP.split("function payload()")[1].split("function renderSetup")[0]
    assert "scene_transitions: sceneTransitionPlan().map(" in payload
    assert 'dance_fx: scene.dance_fx || ""' in payload and "transition: (sceneTransitionPlan()[scene.index] || {}).kind" in payload
    assert 'data-act="scene-look"' in APP and "function lookOptions(current)" in APP
    assert 'target.dataset.act === "scene-transition"' in APP and 'target.dataset.act === "scene-look"' in APP


def test_guardrails_cap_the_boundary_list_the_desk_sends():
    from xenoform import guardrails

    body = {"scene_transitions": [{"kind": "echo-trail", "boundary": "switch", "index": i} for i in range(4)]}
    clean, report = guardrails.apply(body, duration=30.0)
    kinds = [t["kind"] for t in clean["scene_transitions"]]
    assert kinds.count("echo-trail") == 2 and kinds.count("cut") == 2


# ---------------------------------------------------------------- judges page from the registry

def test_judges_page_is_generated_from_the_registry_and_up_to_date():
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_judges_cards as gen

    assert "<!-- vibes:start -->" in JUDGES and "<!-- vibes:end -->" in JUDGES
    keep, _ = gen.listed()
    block = JUDGES.split("<!-- vibes:start -->")[1].split("<!-- vibes:end -->")[0]
    listed = re.findall(r'data-vibe="([^"]+)"', block)
    assert listed == [row["id"] for row in keep]
    featured = [v["id"] for v in vibes.featured() if gen.strip_complete(v["id"]) and gen.pool_backed(v["id"])]
    assert listed[: len(featured)] == featured
    assert gen.rewrite(JUDGES, gen.render(keep)) == JUDGES  # the page is current
    assert gen.main(["--check"]) == 0
    assert '<a href="/">Desk</a>' in JUDGES and 'href="index.html"' not in JUDGES
    import html

    for row in keep:
        assert f"vibes/{row['id']}.jpg" in block and html.escape(row["name"]) in block


def test_judges_generator_rewrites_only_the_block(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import gen_judges_cards as gen

    page = "<head></head>\n      <div>\n        <!-- vibes:start -->\n        old\n        <!-- vibes:end -->\n      </div>"
    out = gen.rewrite(page, gen.render([{"id": "ocean", "name": "Ocean", "line": "A swimmer.", "dark": False}]))
    assert out.startswith("<head></head>\n      <div>\n        <!-- vibes:start -->\n") and out.endswith("<!-- vibes:end -->\n      </div>")
    assert 'data-vibe="ocean"' in out and "old" not in out
