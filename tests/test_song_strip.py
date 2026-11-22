"""The song strip (docs/UI_REVIEW.md 6.1, round 1 of the Songline redesign): the song drawn as the desk's one canvas.

The server halves: GET /api/simple/strip reads a song's passages, drop runs, beats, bars, waveform and Draft window
from its analysis alone; the chain preview carries each planned shot's time and where the cut sits in the song; the
lane carries a cut's window and each shot's Intensity. The desk halves are string pins on strip.js and app.js."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import lane
from xenoform.config import load_config
from xenoform.ui import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
STRIP = (STATIC / "strip.js").read_text(encoding="utf-8")
CSS = (STATIC / "strip.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(load_config(None)))


def test_the_strip_reads_a_bundled_song_from_its_analysis(client):
    got = client.get("/api/simple/strip", params={"audio_id": "song-glitch-out"}).json()
    assert got["duration"] > 200 and got["tempo"] == 90.0
    roles = [p["role"] for p in got["passages"]]
    assert roles[0] == "intro" and roles[-1] == "outro" and "build" in roles
    runs = [p for p in got["passages"] if "drop_run" in p]
    assert len(runs) == 5 and [p["drop_run"] for p in runs] == list(range(5))
    main = [p for p in runs if p.get("main")]
    assert len(main) == 1 and 141 < main[0]["start"] < 143  # the heaviest run, the drop card's 2:22
    for a, b in zip(got["passages"], got["passages"][1:]):
        assert a["end"] == pytest.approx(b["start"], abs=1e-3)  # passages tile the song
    beats = set(got["beats"])
    assert got["bars"] and all(b in beats for b in got["bars"]) and len(got["bars"]) * 4 <= len(got["beats"]) + 4
    assert len(got["wave"]) == 1200 and max(got["wave"]) == 1.0
    win = got["window"]
    assert win["length_s"] == 30.0 and win["start"] < main[0]["start"] < win["end"]  # the Draft is cut round the main drop
    assert win["start"] in beats  # a window starts on a beat


def test_the_strip_answers_the_demo_and_refuses_an_unknown_song(client):
    demo = client.get("/api/simple/strip", params={"audio_id": "demo"}).json()
    assert demo["duration"] == 12.0 and demo["window"] is None and demo["passages"]  # the 12 s demo is made whole
    assert client.get("/api/simple/strip", params={"audio_id": "nope"}).status_code == 400


def test_the_chain_preview_lays_the_planned_shots_on_the_song(client):
    body = {"audio_id": "song-glitch-out", "vibe": "neon-noir", "length_s": 30, "mode": "simple", "energy_preset": "dense",
            "quality_tier": "draft", "aspect": "9:16", "macros": {"intensity": 0.5}, "drop_mode": "auto"}
    got = client.post("/api/simple/chain", json=body).json()
    strip = client.get("/api/simple/strip", params={"audio_id": "song-glitch-out"}).json()
    assert got["window_start"] == pytest.approx(strip["window"]["start"], abs=1e-3)
    times = got["times"]
    assert len(times) == got["shots"] == len(got["sections"]) == len(got["intensity"]) == len(got["assign"])
    assert times[0][0] == 0.0 and times[-1][1] == pytest.approx(30.0, abs=0.05)
    assert all(a[1] == pytest.approx(b[0], abs=1e-3) for a, b in zip(times, times[1:]))
    drops = [v for s, v in zip(got["sections"], got["intensity"]) if s == "drop"]
    assert drops and all(v == 1.0 for v in drops)  # a drop run lifts its shots' Intensity to full
    moved = client.post("/api/simple/chain", json={**body, "length_start": 60.0}).json()
    assert moved["window_start"] <= 60.0 and moved["window_start"] > 59.0  # a dragged window starts on the beat before


def test_the_lane_carries_the_cut_window_and_each_shot_intensity():
    info = {"stills": ["v/00_a.jpg", "v/01_b.jpg", "v/02_c.jpg"], "clips": ["c0", "c1"],
            "shots": [{"start": 0.0, "end": 2.0, "section": "build", "fx_intensity": 0.8},
                      {"start": 2.0, "end": 4.0, "section": "drop", "fx_intensity": 1.0}],
            "window": {"song_start": 127.667, "length_s": 4.0}}
    got = lane.build(info, "v1")
    assert got["window"] == {"song_start": 127.667, "length_s": 4.0}
    assert [s["intensity"] for s in got["shots"]] == [0.8, 1.0]
    assert lane.build({**info, "window": None})["window"] is None and lane.build({**info, "window": {"length_s": 0}})["window"] is None


def test_the_strip_component():
    assert '<script src="/static/strip.js"></script>' in INDEX and 'href="/static/strip.css"' in INDEX
    assert INDEX.index("strip.js") < INDEX.index("app.js")
    for lane_name in ('sections: "Sections"', 'wave: "Wave"', 'beats: "Beats"', 'shots: "Shots"', 'intensity: "Intensity"', 'objects: "Objects"'):
        assert lane_name in STRIP, lane_name
    # hatched = sketched, solid = rendered, ! = stale
    assert "is-${s.state || \"sketch\"}" in STRIP and 'class="xs-stale"' in STRIP
    for rule in (".xs-shot {", ".xs-shot.is-done", ".xs-shot.is-rendering", ".xs-shot.is-queued", ".xs-window", ".xs-grip", ".xs-overview"):
        assert rule in CSS, rule
    assert "!important" not in CSS
    # the window drags by whole beats; Shift a bar, Alt free; arrow keys a beat or a bar
    assert 'if (event && event.altKey) return "free";' in STRIP and 'if (event && event.shiftKey) return "bar";' in STRIP
    assert 'const grid = mode === "bar" ? model.bars : model.beats;' in STRIP
    assert 'event.key !== "ArrowLeft" && event.key !== "ArrowRight"' in STRIP
    # the wheel zooms round the pointer, a sideways swipe pans, Shift + wheel pans
    assert 'viewEl.addEventListener("wheel"' in STRIP and "zoomAt(host, model, v, Math.exp(" in STRIP
    # zoom, scroll and snap survive render() rebuilding the desk: they are kept by model.id
    assert "const VIEWS = new Map();" in STRIP and "window.XenoStrip = {" in STRIP


def test_the_desk_feeds_the_strip():
    model = APP.split("function stripModel(where) {")[1].split("\nfunction ")[0]
    assert "songStrip()" in model and "cutShotsForStrip(easy, lane, off)" in model and "draftWindow(song, easy)" in model
    assert 'state: "sketch"' in model and "chain.window_start" in model and "cutSongStart(easy, lane)" in model
    assert "/api/simple/strip?" in APP and "mountStrips();  // the song strip (strip.js)" in APP
    # the dragged window rides on the Make body and the estimate (the server already reads length_start)
    body = APP.split("function payload() {")[1].split("function vjUrl()")[0]
    assert "length_start: state.easy && easyLength(state.easy) > 0 && !wholeSong(state.easy) ? draggedStart(state.easy) : null," in body
    assert "length_start: draggedStart(easy) != null" in APP.split("async function loadSimpleOptions()")[1].split("\n}\n")[0]
    # a cut sits on the song only when it was made from the song on the desk
    assert 'state.easy.cutSongLabel = row.song || "";' in APP and 'state.easy.cutSongLabel = state.easy.songLabel || "";' in APP
    # the merge (integrate-4nov): where the cut starts on the song held is cutSongStart, its window's start, or 0 when the
    # desk holds only the cut's own stretch (Round 0's reopen loads a trimmed upload's 30 s, the window names the whole
    # song's 2:08): the shots, the seams, the playhead, a seek and the shot's head all read it, so no shot is laid past
    # the song's end under the last seam
    start = APP.split("function cutSongStart(easy, lane) {")[1].split("\n}\n")[0]
    assert "if (!lane || !lane.window || !cutOnSong(easy)) return 0;" in start
    assert "held > 0 && start + (Number(lane.duration) || 0) > held + 0.5 ? 0 : start" in start
    assert APP.count("Number(lane.window.song_start) || 0 : 0") == 0 and APP.count("state.lane.window.song_start") == 0
    assert APP.count("cutSongStart(") == 7  # and planLineFor, the Timeline header's clocks


def test_the_inspector_docks_under_the_strip_with_a_fourth_tab():
    # the drawer of a shot or a seam clicked on the strip docks under it on Tweak (Render keeps it in its timeline panel)
    tweak = APP.split("function renderTweak(easy, chosen) {")[1].split("\n}\n")[0]
    assert "${cut ? inspectorDock(easy) : planDock(easy)}" in tweak
    dock = APP.split("function inspectorDock(easy) {")[1].split("\n}\n")[0]
    assert "timelineDrawer(easy, lane, timelineState(easy, lane), picked)" in dock and "swapPicker(easy, lane)" in dock
    # the fourth tab's host for the Under the hood session (window.XenoHood.mount(host, {jobId, shotIndex}))
    drawer = APP.split("function timelineDrawer(easy, lane, tl, picked) {")[1].split("// Dream this span")[0]
    assert 'id="hood-shot" data-inspector-tab="hood"' in drawer and "hidden></div>" in drawer
    # the merge (integrate-4nov): t4's mountHood at the end of render() mounts both hosts (the project rows provider, the
    # re-render's progress on the shot's block); mountStrips no longer does
    mount = APP.split("function mountHood() {")[1].split("\n}\n")[0]
    assert 'getElementById("hood-shot")' in mount and "!shotHost.hidden" in mount and "window.XenoHood.mount(shotHost, {" in mount
    assert "onRerender:" in mount and "window.XenoHood.mount(projectHost, { jobId: id || \"\", shotIndex: null })" in mount
    assert "XenoHood.mount" not in APP.split("function mountStrips() {")[1].split("\n}\n")[0]
    # the head speaks song time, bar and beat as well as the clock (L9)
    when = APP.split("function shotWhen(lane, s) {")[1].split("\n}\n")[0]
    assert "in the song" in when and "barBeat(off + Number(s.start))" in when and "in the cut" in when and "beat${beats === 1" in when
    assert "${esc(shotWhen(lane, s))}" in drawer
    # the strip keeps its own place across a redraw (by song time, not the page's pixel restore)
    assert 'if (node.classList && node.classList.contains("xs-view")) continue;' in APP


def test_on_a_phone_the_strip_is_the_overview_and_the_step_bar_sticks():
    # decision 13 / C1: at phone width the strip is the section overview with the Draft window and a line saying where
    # it sits, the screens are one column with the strip right under the monitor, and the step bar sticks to the bottom
    line = APP.split("function overviewLine(model) {")[1].split("\n}\n")[0]
    assert "w.label" in line and "the main drop at" in line
    assert 'model.overview = window.matchMedia("(max-width: 560px)").matches;' in APP and "model.foot = overviewLine(model)" in APP
    css = (STATIC / "songline.css").read_text(encoding="utf-8")
    assert ".step-bar {\n  position: sticky; bottom: 0;" in css
    phone = css.split("@media (max-width: 560px) {")[-1].split("\n}\n")[0]  # the phones block, the last of them
    assert ".step-actions > * { flex: 1 1 auto; }" in phone and "env(safe-area-inset-bottom" in phone
    narrow = css.split("@media (max-width: 1000px) {")[-1].split("\n}\n")[0]  # the one-column block, the last of them
    assert ".sl-plan > .sl-strip, .sl-render > .sl-strip { order: 2; }" in narrow
    assert ".xs-overview .xs-body, .xs-overview .xs-tools { display: none; }" in CSS


def test_the_phone_desk_says_what_the_strip_gives_and_the_steps_fit():
    # the 4 Nov desk checks (integrate-4nov): at phone width the strip is the passages overview with no shot to click, so
    # the Timeline header's hint says a shot opens on a wider screen (decision 13: no inspector on a phone); the five
    # steps fit 375 px (the step you are on keeps its name, the others their number or tick) instead of a hidden
    # sideways scroll that cut Perform off; and the header's plan line reads the strip's clock
    import shutil
    import subprocess

    panel = APP.split('const songCut = lane.mode === "song";')[1].split("\nfunction ")[0]
    assert '<span class="hint-wide">click a shot, or the seam between two, to change it</span><span class="hint-phone">' in panel
    assert "planLineFor(easy, lane)" in panel and "lane.plan_line ||" not in panel
    assert '<span class="crumb-label">${STEP_LABELS[key]}</span></button>' in APP
    desk = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert desk.index(".lane-head .hint-phone { display: none; }") < desk.index("@media (max-width: 560px) {")
    phone = desk.split("@media (max-width: 560px) {")[1].split("\n}\n")[0]
    assert ".lane-head .hint-wide, .lane-apply-row .hint-wide { display: none; }" in phone and ".lane-head .hint-phone { display: inline; }" in phone
    # the desk walk: nothing is edited on a phone, so the apply row's "Edits wait for Apply" goes with the wide hint
    assert '<span class="note${pending ? "" : " hint-wide"}">' in panel
    assert ".stagebar .easy-crumbs .crumb:not(.now) .crumb-label {" in phone and "clip-path: inset(50%)" in phone
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    fn = "function planLineFor(" + APP.split("function planLineFor(")[1].split("\n}\n")[0] + "\n}\n"
    clock = "function clockText(" + APP.split("function clockText(")[1].split("\n}\n")[0] + "\n}\n"
    script = clock + fn + """
let held = 0;
let onSong = false;
const cutSongStart = () => held;
const cutOnSong = () => onSong;
const lane = { plan_line: "1 drop, the main at 2:22; 2 passages", window: { song_start: 127.667 } };
const out = [planLineFor({}, lane)];
held = 127.667; out.push(planLineFor({}, lane));
out.push(planLineFor({}, { plan_line: "passage 5 of 14 of the song, a drop at 1:32", window: null }));
held = 0; onSong = true; out.push(planLineFor({}, lane));
out.push(planLineFor({}, { plan_line: "3 drops, the main at 2:22; 6 passages; 4 rests", window: { song_start: 127.667 } }));
console.log(JSON.stringify(out));
"""
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    # the desk walk: the passage count is said once (the Timeline's own fact), and on the song held the drops are the
    # strip title's alone (the 30 s stretch's own analysis read "2 drops, the main at 0:13" under "1 drop ... 0:14")
    assert r.stdout.strip() == '["1 drop, the main at 0:14","1 drop, the main at 2:22",' \
                               '"passage 5 of 14 of the song, a drop at 1:32","","4 rests"]'


def test_a_rerendering_shot_keeps_its_fill_and_its_place_in_the_done_bar_on_every_redraw():
    # review, 21 Nov (integrate-4nov's leftovers): the re-render's fill was a style poll() set on the block, so any
    # render() between two polls drew the block at the CSS default (5%) until the next tick; and the overview's done bar
    # lost a shot while one rendered again, though the shot is still in the cut. Both are the model's now.
    import json
    import shutil
    import subprocess

    shots = APP.split("function cutShotsForStrip(easy, lane, off) {")[1].split("\n}\n")[0]
    assert "fill: rendering ? shotEditFill(state.job && state.job.id === lane.id ? state.job : null) : null, made: rendering," in shots
    paint = APP.split("function paintShotEdit(edit, job) {")[1].split("\n}\n")[0]
    assert 'tile.style.setProperty("--p", String(shotEditFill(job)));' in paint  # the poll and the model agree on the number
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = """
global.window = global; global.CSS = { escape: (s) => s };
global.document = { addEventListener() {}, querySelector: () => null, createElement: () => ({ dataset: {}, setAttribute() {}, innerHTML: "" }) };
require(%s);
let made = null;
const host = { replaceChildren: (el) => { made = el; }, querySelector: () => null, querySelectorAll: () => [] };
const shot = (i, over) => Object.assign({ index: i, n: i + 1, start: i * 2, end: i * 2 + 2, section: "build", state: "done", title: "Shot " + (i + 1), act: { "data-index": i } }, over || {});
const draw = (shots) => { window.XenoStrip.mount(host, { id: "cut", duration: 8, passages: [], beats: [], bars: [], wave: [], shots, overview: true }); return made.innerHTML; };
const block = (h, i) => (h.match(new RegExp('<button[^>]*data-index="' + i + '"[^>]*>')) || [""])[0];
const bar = (h) => (h.match(/<span class="xs-map-done" style="([^"]*)"/) || [])[1] || "";
const plain = draw([shot(0), shot(1), shot(2), shot(3)]);
const during = draw([shot(0), shot(1), shot(2), shot(3, { state: "rendering", fill: 0.42, made: true })]);
const making = draw([shot(0), shot(1, { state: "rendering" }), shot(2, { state: "queued" }), shot(3, { state: "queued" })]);
const odd = draw([shot(0, { state: "rendering", fill: "7; background: red", made: true })]);
console.log(JSON.stringify({ plain: [block(plain, 3), bar(plain)], during: [block(during, 3), bar(during)], making: [block(making, 1), bar(making)], odd: block(odd, 0) }));
""" % json.dumps(str(STATIC / "strip.js"))
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert "--p" not in got["plain"][0] and got["plain"][1] == "left:0.0000%;width:100.0000%"
    assert 'class="xs-shot is-rendering"' in got["during"][0] and ";--p:0.42\"" in got["during"][0]
    assert got["during"][1] == got["plain"][1]  # the bar keeps the shot that renders again
    # a Make's own rendering shot is not made yet: no fill from the model, and the bar stops before it
    assert "--p" not in got["making"][0] and got["making"][1] == "left:0.0000%;width:25.0000%"
    assert "--p" not in got["odd"] and "red" not in got["odd"]  # only a number reaches the style
