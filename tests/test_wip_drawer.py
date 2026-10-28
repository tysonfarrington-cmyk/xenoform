"""The morph engine first (docs/MORPH_ENGINE_PLAN.md, 28 Oct): the Work in progress drawer that takes Polly, your clips,
paid cloud, Moves, VJ and MIDI and Connect an AI off the main desk, and the desk truths beside it (the chain the render
made on the making screen, the Scenes row the line turned on, the measured Final time, the clock past an hour)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from xenoform import dense, ui

STATIC = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static"
APP = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "desk.css").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def _fn(start: str, end: str) -> str:
    return APP.split(start, 1)[1].split(end, 1)[0]


def test_the_drawer_holds_everything_that_is_not_the_engine():
    wip = _fn("function wipDrawer(easy) {", "const LOOK_PRESETS")
    assert '<details class="fine-tune wip-drawer" id="wip-drawer"' in wip and "<summary>Work in progress" in wip
    for part in ("performerRow(easy)", 'simpleSeg("easy-clips"', "cloudRows(easy)", 'href="/moves"', "vjUrl()",
                 'data-act="easy-midi"', 'data-hash="connect"'):
        assert part in wip, part
    assert 'readDrawer("xeno-wip")' in wip and '"wip-drawer": "xeno-wip"' in APP  # closed by default, remembered
    desk = _fn("function renderEasy() {", "// Variations (xenoform.batch")
    assert "${fineTune(easy)}\n      ${wipDrawer(easy)}" in desk
    side = desk.split('<aside class="panel easy-side" data-tour="easy-make">', 1)[1]
    for gone in ('href="/moves"', "VJ mode: live visuals", 'data-act="easy-midi"', 'data-hash="connect"'):
        assert gone not in side, gone
    assert "performerRow(easy)" not in _fn("function simpleOptions(easy) {", "// Morph count")
    assert 'data-act="easy-paid-cloud"' not in _fn("function machineRows(easy) {", "function simpleOptions(easy)")
    assert 'data-hash="connect"' not in INDEX.split('class="more-menu"', 1)[1].split("</details>", 1)[0]
    assert ".wip-item {" in CSS and ".wip-drawer" in CSS


def test_your_images_stay_in_the_engine_and_your_clips_wait_for_the_switch():
    own = _fn("function ownRow(easy) {", "// The stills library")
    assert "<span>Your images</span>" in own and "Work in progress > Your clips" in own
    body = _fn("function payload() {", "function vjUrl()")
    assert "cut_in_clips: !!(state.easy && state.easy.clipsOn)" in body
    assert 'act === "easy-clips"' in APP and '"clipsOn"' in APP.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg makes the clip")
def test_the_make_body_drops_your_clips_unless_they_are_switched_on(tmp_path):
    folder = tmp_path / "own"
    folder.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(folder / "b_clip.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=orange:size=64x64", "-frames:v", "1",
                    str(folder / "a_still.png")], check=True)
    off = ui._apply_own({"own_folder": str(folder), "cut_in_clips": False})
    assert off["own_clips"] == [] and [Path(p).name for p in off["morph_targets"]] == ["a_still.png"]
    on = ui._apply_own({"own_folder": str(folder), "cut_in_clips": True})
    assert len(on["own_clips"]) == 1 and Path(on["own_clips"][0]["path"]).name == "b_clip.mp4"
    assert len(ui._apply_own({"own_folder": str(folder)})["own_clips"]) == 1  # MCP and the CLI keep the old behaviour


def test_the_idea_line_names_things_to_morph_and_leaves_polly_off():
    note = APP.split('${ideaReadingLine(easy)}', 1)[1].split("</details>", 1)[0]  # the folded "How the line works"
    assert "brings Polly in" not in note and "Things become the objects the morphs travel between" in note


def test_the_making_screen_shows_the_chain_the_render_made(tmp_path):
    stills = [{"noun": "car rally race", "path": "x/066_car_rally_racing_black.png"},
              {"file": "024_hot_air_balloon_black.png", "kind": "object"}, {"noun": "a dark shore", "kind": "scene"}]
    (tmp_path / "simple").mkdir()
    dense.write_chain(tmp_path / "simple", stills)
    assert ui._read_chain(tmp_path) == [{"noun": "car rally race", "kind": "object"},
                                        {"noun": "hot air balloon black", "kind": "object"},
                                        {"noun": "a dark shore", "kind": "scene"}]
    assert ui._read_chain(tmp_path / "nothing") is None
    (tmp_path / "simple" / "chain.json").write_text("not json", encoding="utf-8")
    assert ui._read_chain(tmp_path) is None
    making = _fn('if (easy.phase === "making") {', 'if (easy.phase === "result"')
    assert "state.job.chain" in making and "preview: Make may grow more for your line" in making


def test_run_simple_writes_the_chain_before_the_morphs(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(dense, "stills_for", lambda state, n, **kw: ("cosmic", [{"path": f"s{i}.png", "file": f"s{i}.png", "noun": f"thing {i}"} for i in range(n)]))
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    import xenoform.cloud_morph as cm

    def fake_clips(shots, stills, work, w, h):
        seen["chain"] = json.loads((Path(work) / "chain.json").read_text(encoding="utf-8"))  # written before any morph
        return [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))]

    monkeypatch.setattr(cm, "_mock_clips", fake_clips)

    def fake_compose(clips, shots, audio, out, **kw):
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    from xenoform import beatfx

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo.wav"
    step = 0.5
    directed = {"duration": 12.0, "beats": [round(i * step, 4) for i in range(24)]}
    state = {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple"}
    dense.run_simple(directed, demo, tmp_path / "x.mp4", tmp_path, {}, state, lambda *a: None, engine="mock")
    assert seen["chain"][0] == {"noun": "thing 0", "kind": "object"} and len(seen["chain"]) >= 2


def test_the_scenes_row_shows_what_the_line_turned_on():
    row = _fn("function scenesRow(easy) {", "function machineRows(easy)")
    assert "reading.scenes" in row and "!easy.scenesChosen" in row and "pick Off to keep objects only" in row
    handler = APP.split('act === "easy-scenes") {', 1)[1].split("} else if", 1)[0]
    assert "state.easy.scenesChosen = true;" in handler
    assert "scenes_chosen: !!(state.easy && state.easy.scenesChosen)" in _fn("function payload() {", "function vjUrl()")


def test_the_final_time_is_measured_and_the_clock_reads_hours():
    render_row = _fn("function renderRow(easy) {", "function renderEasy()")
    assert "roughly 90 s of GPU" not in render_row and "fin.per_s" in render_row and "Final cut" in render_row
    clock = _fn("function clockText(seconds) {", "function easySongSeconds()")
    assert "s >= 3600" in clock and "Math.floor(s / 3600)" in clock
