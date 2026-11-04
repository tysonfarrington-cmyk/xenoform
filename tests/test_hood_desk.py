"""Under the hood on the desk (docs/UI_REVIEW.md 6.4): the self-contained module (hood.js, hood.css) and how the desk
mounts it (the drawer's fourth tab, the cut's own rows with no shot open), the re-render kept on the cut's screen with its
progress on the shot's tile (L7), Swap, Generate here and Dream here naming and lighting the shots they replace (L6), the
guardrail notes as sentences that open their shot (F13), and the re-render body's round trip, run under node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
HOOD = (STATIC / "hood.js").read_text(encoding="utf-8")
CSS = (STATIC / "hood.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
NODE = shutil.which("node")


def _fn(start: str, end: str = "\n}\n") -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def test_the_module_is_self_contained_and_loaded_before_the_desk():
    assert INDEX.index('src="/static/hood.js"') < INDEX.index('src="/static/app.js"') and 'href="/static/hood.css"' in INDEX
    assert "window.XenoHood = { mount, progress, invalidate" in HOOD
    for leak in ("state.easy", "postCutEdit(", "render()", "getElementById(", "easyVideoId", "state.lane"):
        assert leak not in HOOD, leak  # nothing about where it is mounted: the host gives the job, the shot and the hooks
    for part in ('data-hood="rerender"', 'data-hood="copy"', 'data-hood="reset"', 'data-hood="take"', 'data-hood="queue"',
                 'data-hood="queue-yes"', "Open in ComfyUI", "download=", "/recipe", "/comfy", "class=\"generate\"", "class=\"ghost\"",
                 "hood-hint", "hood-preset", "preset:"):
        assert part in HOOD, part
    for field in ("prompt", "negative", "seed", "steps", "cfg", "frames", "guide_start", "guide_end", "compression", "style", "lora"):
        assert f'data-hood-in="{field}"' in HOOD, field
    # a host's answer is true, or the reason it did not start: the panel says the reason (a refused value, a busy cut)
    assert HOOD.count("if (started !== true) {") == 2 and 'typeof started === "string" && started ? started' in HOOD
    assert "return ok || state.easy.note || false;" in _fn("function mountHood() {")


def test_the_drawer_mounts_it_as_the_fourth_tab_and_the_cut_rows_with_no_shot_open():
    drawer = _fn("function timelineDrawer(easy, lane, tl, picked) {")
    assert 'id="hood-shot" data-inspector-tab="hood"' in drawer and "shotGpuRows(lane, s, choices, canGpu, dream)" in drawer
    assert 'morphStyleRow(s.style || "melt", "easy-tl-style"' not in drawer and 'id="tl-seed"' not in drawer  # out of Regenerate
    # the merge (integrate-4nov): the cut's own rows live in Tweak's Project panel (t5's #hood-project), not under the lane
    project_panel = _fn("function projectPanel(easy) {")
    assert 'id="hood-project"' in project_panel and 'id="hood-project-panel"' in project_panel
    mount = _fn("function mountHood() {")
    assert 'getElementById("hood-shot")' in mount and 'getElementById("hood-project")' in mount
    assert "{ inPlace: true, shot: index }" in mount and '"rerender"' in mount and "shots/${index}/take" in mount and "onSelect" in mount
    assert "mountHood();" in _fn("function render() {")
    project = _fn("function hoodProject() {")
    for key in ("aspect", "tier", "gpu", "endpoint", "forms", "fx", "orbit", "card", "overlay", "images", "library", "recipe", "performer",
                "paid", "connect"):
        assert f'key: "{key}"' in project, key
    assert project.count("where:") >= 15 and project.count("cost:") >= 15  # where each lives, what each costs (M4, C10)
    assert '"Subject sway"' in project and "touchKnob(HOOD_RECUT_ACTS[act])" in APP


def test_a_rerender_under_the_hood_keeps_the_cuts_screen_with_progress_on_its_tile():
    # the merge (integrate-4nov): Round 0's title is the 7th argument, opts the last; an edit not in place gets the making view
    post = _fn("async function postCutEdit(id, route, body, detail, at, stage, title, opts) {")
    assert "if (opts && opts.inPlace) state.easy.shotEdit" in post
    assert post.index("if (opts && opts.inPlace) state.easy.shotEdit") < post.index("else {") < post.index('setEasyPhase("making");')
    poll = _fn("async function poll(id) {")
    assert "shotEditTick(job);" in poll and poll.index("shotEditTick(job);") < poll.index('state.easy.phase === "making") {\n')
    tick = _fn("function shotEditTick(job) {")
    assert "XenoHood.invalidate(edit.id)" in tick and "state.lane = null" in tick and "video_version" in tick
    paint = _fn("function paintShotEdit(edit, job) {")
    # the merge (integrate-4nov): the cut's shots are the song strip's blocks (t5), so the tile is the strip's .xs-shot
    assert 'classList.add("is-rendering")' in paint and '"--p"' in paint and "XenoHood.progress" in paint
    assert '[data-song-strip="cut"] .xs-shot[data-index="${edit.shot}"]' in paint
    strip_shots = _fn("function cutShotsForStrip(easy, lane, off) {")
    assert 'easy.shotEdit && easy.shotEdit.id === lane.id && easy.shotEdit.shot === s.index ? "rendering"' in strip_shots
    assert '[data-song-strip="cut"] .xs-shot.is-rendering::before' in CSS


def test_swap_generate_and_dream_name_and_light_the_shots_they_replace():
    rows = _fn("function shotGpuRows(lane, s, choices, canGpu, dream) {")
    assert 'data-act="easy-tl-swap"' in rows and 'data-act="easy-tl-insert"' in rows and "data-span=" in rows
    assert "replacesText(ia, ib)" in rows and "gpuCost(lane" in rows and "re-renders shots" in rows
    dream = _fn("function dreamRow(lane, s, choices) {")
    assert 'data-span="${da}-${db}"' in dream and 'id="tl-dream-span"' in dream
    assert "function lightSpan(el, on)" in APP and '"span-lit"' in APP and '[data-song-strip="cut"] .xs-shot.span-lit' in CSS
    assert 'target.id === "tl-insert-s" || target.id === "tl-dream-s"' in APP


def test_the_guardrail_notes_read_as_sentences_that_open_their_shot():
    assert "<li>${guardSentence(m)}</li>" in _fn("function guardDetails(job) {")
    sentence = _fn("function guardSentence(line) {")
    assert 'data-act="easy-guard-shot"' in sentence and "The check after the render saw" in sentence and "Your taste file:" in sentence
    assert 'act === "easy-guard-shot"' in APP


def test_the_stylesheet_uses_the_desks_tokens_and_reads_on_a_phone():
    assert "!important" not in CSS and "--x-accent" in CSS and "--x-surface" in CSS and "@media (max-width: 560px)" in CSS
    assert ".hood-row.differs" in CSS and ".hood-row:focus-within .hood-hint" in CSS


# ---------------------------------------------------------------------------------------------- run under node


def _node(script: str) -> dict:
    if not NODE:
        pytest.skip("node is not on this machine")
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _recipe(**over) -> dict:
    used = {"prompt": "One single object melts", "negative": "text", "seed": 2733, "steps": 12, "cfg": 3.0, "frames": 97,
            "guide_start": 1.0, "guide_end": 1.0, "compression": [18, 18], "style": "melt", "lora": None}
    preset = {"prompt": "One single object melts", "negative": "text", "seed": 2727, "steps": 20, "cfg": 3.0, "frames": 97,
              "guide_start": 1.0, "guide_end": 1.0, "compression": [18, 18], "style": "melt"}
    return {"used": {**used, **over}, "preset": preset, "differs": {"prompt": False}, "next_seed": 3736}


def test_the_rerender_body_keeps_a_takes_own_values_and_sends_what_changed():
    hood = json.dumps(str(STATIC / "hood.js"))
    cases = {
        "untouched": ({}, True),                      # nothing changed: the take's own steps go again, the next seed
        "cfg": ({"cfg": 4.5}, True),                  # one change: the take's steps and seed stay, the cfg goes
        "style": ({"style": "shatter"}, True),        # a style: its own words (the prompt follows it)
        "words": ({"prompt": "a key folds into a moth"}, False),
        "lora": ({"lora": {"name": "x.safetensors", "strength": 0.6}}, True),
        "reset": ({"seed": 2727, "steps": 20, "cfg": 3.0, "frames": 97, "guide_start": 1.0, "guide_end": 1.0,
                   "compression": [18, 18], "negative": "text"}, True),
    }
    script = f"""
      global.window = {{}};
      require({hood});
      const v = window.XenoHood._values;
      const recipe = {json.dumps(_recipe())};
      const cases = {json.dumps(cases)};
      const out = {{}};
      for (const [name, [edits, follow]] of Object.entries(cases)) {{
        const entry = {{ recipe, preset: recipe.preset, edits, follow }};
        out[name] = v.bodyOf(entry, {{ shotIndex: 6 }});
      }}
      process.stdout.write(JSON.stringify(out));
    """
    got = _node(script)
    assert got["untouched"]["body"] == {"shot": 6, "steps": 12} and got["untouched"]["changed"] == []
    assert got["cfg"]["body"] == {"shot": 6, "steps": 12, "cfg": 4.5, "seed": 2733} and got["cfg"]["changed"] == ["cfg"]
    assert got["style"]["body"] == {"shot": 6, "steps": 12, "style": "shatter", "seed": 2733} and "prompt" not in got["style"]["body"]
    assert got["words"]["body"]["prompt"] == "a key folds into a moth" and got["words"]["body"]["seed"] == 2733
    assert got["lora"]["body"]["lora"] == "x.safetensors" and got["lora"]["body"]["lora_strength"] == 0.6
    # Reset to preset: the preset's own values, the cut's seed for the morph: the Make's request, which the cache answers
    assert got["reset"]["body"] == {"shot": 6, "seed": 2727}


def test_the_desks_span_rule_is_the_servers():
    from xenoform import dense, dream

    shots = [{"index": i, "start": i * 1.5, "end": (i + 1) * 1.5, "seconds": 1.5, "morph": i} for i in range(12)]
    shots[7] = {**shots[7], "performer": True}
    src = "function editSpan(shots, first, seconds, kind) {" + _fn("function editSpan(shots, first, seconds, kind) {")
    asks = [(first, secs, kind) for first in (0, 2, 5) for secs, kind in ((5, "insert"), (10, "insert"), (15, "insert"), (1, "dream"), (2, "dream"), (3, "dream"))]
    script = f"""{src}\n}}
      const shots = {json.dumps(shots)};
      process.stdout.write(JSON.stringify({json.dumps(asks)}.map(([f, s, k]) => editSpan(shots, f, s, k))));
    """
    got = _node(script)
    for (first, secs, kind), span in zip(asks, got):
        want = dense.insert_span(shots, first, secs) if kind == "insert" else dream.span(shots, first, secs)
        assert tuple(span) == want, (first, secs, kind)
