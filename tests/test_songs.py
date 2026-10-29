"""The bundled songs (29 Oct, Tys: "the bundled songs, lets include ... the wobble morph, the hip hop beat, the liquid
dubstep and ambient ... oh include the song glitch out as well"): the manifest matches the files, the shipped analyses
load and match what the desk would compute, GET /api/songs lists them in order, POST /api/songs/load answers an
upload's payload under a stable id, the song registries find a bundled song after a desk restart, the desk has the
chips and the docs name the songs."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import songs_api, stems_api, ui

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
STATIC = ROOT / "src" / "xenoform" / "ui_static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
IDS = ["morphing-wobble-20s", "morphing-wobble", "hip-hop-boom-bap", "liquid-dnb", "ambient", "glitch-out"]
QUICK = "morphing-wobble-20s"
QUICK_AUDIO = "song-morphing-wobble-20s"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _fn(start: str, end: str) -> str:
    return APP_JS.split(start, 1)[1].split(end, 1)[0]


def _ffprobe_seconds(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=False)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def _forget(*audio_ids: str) -> None:
    """What a desk restart does to the registries: the ids are gone until something looks them up."""
    with ui._LOCK:
        for audio_id in audio_ids:
            ui._AUDIO.pop(audio_id, None)
            ui._FEATURES.pop(audio_id, None)


@pytest.fixture
def quiet_split(monkeypatch):
    """No real stem split in tests: the hook only records which file it was asked to split."""
    calls: list[Path] = []

    def stub(song, **kwargs):
        calls.append(Path(song))
        return {"id": None, "status": "queued", "engine": "auto", "seconds": 0.0, "path": None, "error": None}

    monkeypatch.setattr(stems_api, "start_background_split", stub)
    return calls


@pytest.fixture
def client(quiet_split, tmp_path, monkeypatch):
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")  # no cached split from another run
    return TestClient(ui.create_app())


# ---------------------------------------------------------------- the files
def test_manifest_rows_match_the_files_and_their_analyses():
    rows = songs_api.manifest()
    assert [row["id"] for row in rows] == IDS  # the 20 s Wobble first (the quick one), then the whole Wobble, then the rest
    fps = float(ui.load_desk_config()["fps"])
    for row in rows:
        path = SONGS / row["file"]
        assert path.is_file(), row["id"]
        assert row["title"] and row["feel"] and "Suno" in row["credit"], row["id"]
        assert float(row["bpm"]) > 0 and float(row["seconds"]) > 0, row["id"]
        measured = _ffprobe_seconds(path)
        if measured is not None:
            assert abs(measured - float(row["seconds"])) <= 0.3, (row["id"], measured)
        features_path = SONGS / f"{row['id']}.features.json"
        assert features_path.is_file(), row["id"]
        features = json.loads(features_path.read_text(encoding="utf-8"))
        assert float(features["fps"]) == fps, row["id"]  # the desk's own frame rate, so a Make needs no re-analysis
        assert abs(float(features["duration"]) - float(row["seconds"])) <= 0.3, row["id"]
        assert features["n_frames"] == len(features["frames"]) == round(float(features["duration"]) * fps), row["id"]
        assert int(round(float(features["tempo"]))) == int(row["bpm"]), row["id"]
        assert features["beats"] and features["sections"], row["id"]
        assert features_path.stat().st_size <= 1_600_000, row["id"]  # the brief's ceiling, about 1.5 MB


def test_the_shipped_analysis_is_what_the_desk_would_compute():
    """The 20 s Wobble analysed now, the /api/analyze way, against its shipped file (about three seconds of CPU)."""
    row = songs_api.find(QUICK)
    fresh = songs_api.analyse(songs_api.song_path(row))
    shipped = json.loads(songs_api.shipped_features_path(row).read_text(encoding="utf-8"))
    assert fresh["n_frames"] == shipped["n_frames"] and fresh["fps"] == shipped["fps"]
    assert abs(float(fresh["tempo"]) - float(shipped["tempo"])) < 0.01
    assert len(fresh["beats"]) == len(shipped["beats"]) and len(fresh["sections"]) == len(shipped["sections"])


def test_the_script_that_builds_them_is_in_the_repo():
    script = _read("scripts/analyse_bundled_songs.py")
    assert "from xenoform.songs_api import analyse" in script and "songs.json" in script


# ---------------------------------------------------------------- the routes
def test_api_songs_lists_them_in_order_with_the_demo(client):
    data = client.get("/api/songs").json()
    assert [song["id"] for song in data["songs"]] == IDS
    quick = data["songs"][0]
    assert quick["title"] == "Morphing Wobble (20 s)" and quick["file"] == "examples/songs/morphing_wobble_20s.mp3"
    assert quick["audio_id"] == QUICK_AUDIO and quick["seconds"] == 20.0 and quick["bpm"] > 0
    assert quick["feel"] and "Suno" in quick["credit"]
    assert data["demo"]["id"] == "demo" and data["demo"]["file"] == "examples/demo.wav" and data["demo"]["seconds"] == 12.0


def test_load_registers_the_quick_wobble_and_answers_an_uploads_payload(client, quiet_split):
    _forget(QUICK_AUDIO)
    response = client.post("/api/songs/load", json={"id": QUICK})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["audio_id"] == QUICK_AUDIO and payload["title"] == "Morphing Wobble (20 s)"
    assert abs(payload["duration"] - 20.0) <= 0.3 and payload["tempo"] > 0 and payload["fps"] == 24.0
    assert payload["audio_url"] == f"/media/audio/{QUICK_AUDIO}" and payload["video"] == "" and payload["reference"] == ""
    assert payload["video_label"].startswith("No picture yet") and payload["blocks"] and payload["sections"]
    assert payload["song"]["id"] == QUICK and payload["song"]["audio_id"] == QUICK_AUDIO
    with ui._LOCK:
        assert ui._AUDIO[QUICK_AUDIO] == SONGS / "morphing_wobble_20s.mp3"
        assert ui._FEATURES[QUICK_AUDIO]["n_frames"] == 480
    assert quiet_split == [SONGS / "morphing_wobble_20s.mp3"]  # stems by default, like an upload
    again = client.post("/api/songs/load", json={"id": QUICK}).json()
    assert again["audio_id"] == QUICK_AUDIO  # idempotent: the same id, the split asked for again (its registry dedupes)
    assert len(quiet_split) == 2


def test_an_unknown_song_is_404_with_a_plain_message(client):
    response = client.post("/api/songs/load", json={"id": "nope"})
    assert response.status_code == 404
    assert response.json()["detail"] == "No bundled song with that name. GET /api/songs lists them."
    assert client.post("/api/songs/load", json={}).status_code == 404


def test_media_audio_serves_a_bundled_song(client):
    client.post("/api/songs/load", json={"id": QUICK})
    response = client.get(f"/media/audio/{QUICK_AUDIO}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert len(response.content) == (SONGS / "morphing_wobble_20s.mp3").stat().st_size


def test_a_fresh_desk_knows_a_bundled_song_without_a_load(quiet_split, tmp_path, monkeypatch):
    """After a restart a recipe, a bookmarked page or the stems line may still name song-<id>: the registries find the
    bundled song on first sight, so the song plays, the stems line answers and the Make's checks pass."""
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    _forget(QUICK_AUDIO)
    client = TestClient(ui.create_app())
    status = client.get(f"/api/stems/for/{QUICK_AUDIO}")
    assert status.status_code == 200, status.text
    assert status.json()["status"] in stems_api.STATUSES and status.json()["audio_id"] == QUICK_AUDIO
    _forget(QUICK_AUDIO)
    assert client.get(f"/media/audio/{QUICK_AUDIO}").status_code == 200
    _forget(QUICK_AUDIO)
    with ui._LOCK:
        assert QUICK_AUDIO in ui._AUDIO  # the Make's "known" check
        assert ui._FEATURES.get(QUICK_AUDIO)["n_frames"] == 480  # _features_for's lookup
        assert ui._AUDIO[QUICK_AUDIO].name == "morphing_wobble_20s.mp3"
    # anything else is a plain dict: no file is touched for an unknown id, and nothing is invented
    with ui._LOCK:
        assert ui._AUDIO.get("song-nope") is None and "song-nope" not in ui._AUDIO
        assert ui._FEATURES.get("abc123") is None and "abc123" not in ui._FEATURES
        with pytest.raises(KeyError):
            ui._AUDIO["song-nope"]
    assert quiet_split == []  # the self-heal registers; it never starts a split by itself


def test_a_missing_shipped_analysis_is_made_once_and_cached(tmp_path, monkeypatch):
    row = songs_api.find(QUICK)
    monkeypatch.setattr(songs_api, "shipped_features_path", lambda r: tmp_path / "gone.json")
    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path / "work")
    made = []

    def fake_analyse(path):
        made.append(Path(path))
        return {"fps": 24.0, "duration": 1.0, "n_frames": 24, "tempo": 100.0, "beats": [0.5], "sections": [], "frames": [{"i": 0}]}

    monkeypatch.setattr(songs_api, "analyse", fake_analyse)
    first = songs_api.features_for(row)
    second = songs_api.features_for(row)
    assert first["tempo"] == 100.0 and second["tempo"] == 100.0
    assert made == [SONGS / "morphing_wobble_20s.mp3"]  # analysed once, then read from the cache
    assert (tmp_path / "work" / "songs" / f"{QUICK}.features.json").is_file()


def test_the_heal_reads_the_disk_and_never_analyses_under_the_lock(client, tmp_path, monkeypatch):
    """The registries fill under ui._LOCK, so a librosa pass there would stall every other request. With the shipped
    analysis and the cache both gone the features lookup misses (the song file is still found); the chip's load
    analyses outside the lock and caches, and from then on the heal reads the cache."""
    row = songs_api.find(QUICK)
    real = json.loads(songs_api.shipped_features_path(row).read_text(encoding="utf-8"))
    monkeypatch.setattr(songs_api, "shipped_features_path", lambda r: tmp_path / "gone.json")
    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path / "work")
    made = []

    def fake_analyse(path):  # the real analysis with a marker tempo, so the payload builds as it would
        made.append(Path(path))
        return {**real, "tempo": 100.0}

    monkeypatch.setattr(songs_api, "analyse", fake_analyse)
    _forget(QUICK_AUDIO)
    with ui._LOCK:
        assert ui._FEATURES.get(QUICK_AUDIO) is None and QUICK_AUDIO not in ui._FEATURES
        assert QUICK_AUDIO in ui._AUDIO
    assert made == []  # nothing analysed while the lock was held
    story = client.post("/api/story", json={"audio_id": QUICK_AUDIO})  # _features_for under the lock: a plain miss
    assert story.status_code == 400 and story.json()["detail"].startswith("Load a song before")
    assert made == []
    assert client.post("/api/songs/load", json={"id": QUICK}).status_code == 200  # the chip analyses, outside the lock
    assert made == [SONGS / "morphing_wobble_20s.mp3"]
    _forget(QUICK_AUDIO)
    with ui._LOCK:
        assert ui._FEATURES.get(QUICK_AUDIO)["tempo"] == 100.0  # healed from the cache
    assert made == [SONGS / "morphing_wobble_20s.mp3"]  # still one analysis
    _forget(QUICK_AUDIO)


def test_a_song_whose_analysis_fails_is_400_with_a_plain_sentence(client, monkeypatch):
    def boom(row):
        raise ImportError("No module named 'librosa'")

    monkeypatch.setattr(songs_api, "features_for", boom)
    _forget(QUICK_AUDIO)
    response = client.post("/api/songs/load", json={"id": QUICK})
    assert response.status_code == 400
    assert response.json()["detail"] == songs_api.UNREADABLE and "librosa" not in response.json()["detail"]
    assert client.get(f"/media/audio/{QUICK_AUDIO}").status_code == 200  # the song itself still plays


def test_a_song_whose_file_is_gone_misses_like_an_unknown_id(client, monkeypatch):
    """A manifest row whose mp3 is missing, and a fill that raises: the registries miss (logged), nothing raises into
    the media route, and the load is a 404."""
    _forget("song-ambient", "song-glitch-out")
    monkeypatch.setattr(songs_api, "song_path", lambda row: SONGS / "not-here.mp3")
    assert client.get("/media/audio/song-ambient").status_code == 404
    assert client.post("/api/songs/load", json={"id": "ambient"}).status_code == 404
    with ui._LOCK:
        assert "song-ambient" not in ui._AUDIO and ui._FEATURES.get("song-ambient") is None

    def broken(song_id):
        raise RuntimeError("the manifest exploded")

    monkeypatch.setattr(songs_api, "find", broken)
    assert client.get("/media/audio/song-glitch-out").status_code == 404  # swallowed and logged, not a 500
    with ui._LOCK:
        assert "song-glitch-out" not in ui._AUDIO


def test_load_answers_the_desks_comfy_endpoint_not_the_example_configs(quiet_split, tmp_path, monkeypatch):
    """A desk started with --config and another ComfyUI address: a chip's payload names that address, as /api/demo and
    /api/analyze do, so loading a bundled song never points the next Make back at the default one."""
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    cfg = ui.load_desk_config()
    cfg = {**cfg, "comfy": {**cfg["comfy"], "base_url": "http://127.0.0.1:9999"}}
    client = TestClient(ui.create_app(cfg))
    demo = client.get("/api/demo").json()
    song = client.post("/api/songs/load", json={"id": QUICK}).json()
    assert song["endpoint"] == demo["endpoint"] == "http://127.0.0.1:9999"
    plain = TestClient(ui.create_app()).post("/api/songs/load", json={"id": QUICK}).json()
    assert plain["endpoint"] == ui.load_desk_config()["comfy"]["base_url"]


# ---------------------------------------------------------------- the desk
def test_the_song_step_has_a_chip_for_every_bundled_song():
    block = _fn("const songBlock = songSet", "const proto = easyLengthIsProto(easy);")
    assert 'data-act="easy-demo">Bundled demo</button>' in block  # the demo button stays where it was
    assert '<div id="bundled-songs">${songsRow(easy)}</div>' in block  # the row lands under the actions, in its own slot
    row = _fn("function songsRow(easy)", "async function useBundledSong(id)")
    assert 'data-act="easy-song"' in row and 'data-id="${esc(song.id)}"' in row and "Bundled songs" in row
    assert 'title="${esc(song.feel || "")}"' in row and "<small>${songClock(song.seconds)}</small>" in row
    assert 'class="chip${easy.song === song.id ? " on" : ""}"' in row  # the loaded song's chip carries on, like the demo button
    assert "loadSongs();" in row  # fetched lazily, once
    load = _fn("async function loadSongs()", "function songClock(")
    assert 'api("/api/songs")' in load and "state.songs = []" in load  # a failed fetch shows nothing
    assert 'getElementById("bundled-songs")' in load and "slot.innerHTML = songsRow(state.easy)" in load  # no redraw for it


def test_a_chip_loads_the_song_the_way_the_demo_button_does():
    use = _fn("async function useBundledSong(id)", "async function useDemoSong()")
    assert 'chip.textContent = "Loading…"' in use and "render();" not in use.split("if (state.audioId")[0]  # its own text first
    assert "state.easy.song = song.id" in use and "state.easy.songLabel = song.title" in use
    assert 'setEasyPhase("vibe")' in use and 'state.easy.phase = "vibe"' not in use  # through the one phase setter (test_simple_nav)
    assert 'api("/api/songs/load", { method: "POST"' in use and "JSON.stringify({ id: song.id })" in use
    assert "adoptSession(data);" in use and "await settleCut({ full: true });" in use
    assert "loadSimpleOptions().then(() => render());" in use
    assert 'state.easy.song = "";' in use and 'setEasyPhase("choose");' in use  # a failed load falls back to the song step
    # two chips in quick succession: the answer of a chip that is no longer the chosen song is dropped, before both the
    # adopt and the fallback, so the desk never names one song and holds another; the demo button drops its answer too
    after = use.split('api("/api/songs/load"', 1)[1]
    assert "if (!state || !state.easy || state.easy.song !== song.id) return;" in after
    assert after.index("state.easy.song !== song.id) return;") < after.index("if (!data) {") < after.index("adoptSession(data);")
    demo = _fn("async function useDemoSong()", "async function uploadSong(file)")
    assert demo.index('api("/api/demo")') < demo.index('state.easy.song !== "demo") return;') < demo.index("adoptSession(")
    assert "Drop a file here, use the bundled demo, or pick one of the bundled songs." in APP_JS  # the note beside the chips
    assert "Drop a track, use the bundled demo or pick a bundled song." in APP_JS  # the tour's Song hint
    dispatch = _fn('document.addEventListener("click"', "async function")
    assert 'act === "easy-song"' in dispatch and 'useBundledSong(el.dataset.id || "")' in dispatch
    adopt = _fn("function adoptSession(data, options = {})", "\n}\n")
    assert "songs: previous ? previous.songs || null : null" in adopt  # the list outlives a new song
    assert "song" not in _fn("const EASY_SAVED_KEYS = [", "]").replace("songLabel", "").split(",")  # a reload falls back to the song step, as the demo does
    css = (STATIC / "desk.css").read_text(encoding="utf-8")
    assert ".song-chips .chip small" in css and ".song-shelf" in css


RACE_HARNESS = r"""
// The desk's real songClock, songsRow, useBundledSong and useDemoSong against a stand-in for the rest of the desk.
// adoptSession is reduced to what matters here: a new state whose audioId is the payload's and whose easy is the
// previous state's. Each scenario clicks, then lets the answers land in a chosen order, and reports the end state.
const fs = require("fs");
const src = fs.readFileSync(__APP__, "utf8");
const code = src.slice(src.indexOf("function songClock(seconds)"), src.indexOf("async function uploadSong(file)"));
const desk = new Function(code + "\nreturn { songsRow, useBundledSong, useDemoSong };")();
const SONGS = [{ id: "ambient", title: "Ambient", seconds: 225.0, feel: "Slow and open" },
               { id: "glitch-out", title: "Glitch Out", seconds: 238.8, feel: "Glitchy and broken up" }];
let chips = {};
let pending = {};
global.esc = (s) => String(s);
global.window = { CSS: null };
global.document = {
  querySelector: (sel) => { const m = /data-id="([^"]+)"/.exec(sel); return m ? chips[m[1]] || null : null; },
  getElementById: () => null,
};
global.loadSongs = () => {};
global.api = (path, init) => new Promise((resolve) => {
  const id = init ? JSON.parse(init.body).id : "demo";
  pending[id] = (ok) => resolve({ ok, json: async () => ({ audio_id: id === "demo" ? "demo" : `song-${id}`, title: id }) });
});
global.render = () => {};
global.setEasyPhase = (p) => { global.state.easy.phase = p; };
global.settleCut = async () => {};
global.loadSimpleOptions = async () => {};
global.adoptSession = (data) => { const previous = global.state; global.state = { audioId: data.audio_id, easy: previous.easy, songs: previous.songs }; };
const tick = () => new Promise((r) => setTimeout(r, 0));
function fresh() {
  chips = {}; pending = {};
  global.state = { audioId: "abc1234567", easy: { song: "", songLabel: "", note: "", phase: "song" }, songs: SONGS };
  for (const s of SONGS) chips[s.id] = { textContent: s.title, disabled: false };
}
function end() { return { audioId: global.state.audioId, song: global.state.easy.song, label: global.state.easy.songLabel, phase: global.state.easy.phase, note: global.state.easy.note }; }
(async () => {
  const out = {};
  fresh();
  out.row = desk.songsRow(global.state.easy);
  // A: two chips, the second answer lands first
  fresh();
  let a = desk.useBundledSong("ambient"), b = desk.useBundledSong("glitch-out");
  await tick(); out.loading = JSON.parse(JSON.stringify(chips));
  pending["glitch-out"](true); await b; await tick(); pending["ambient"](true); await a; await tick();
  out.secondFirst = end();
  // B: two chips, the answers land in click order
  fresh();
  a = desk.useBundledSong("ambient"); b = desk.useBundledSong("glitch-out"); await tick();
  pending["ambient"](true); await a; await tick(); pending["glitch-out"](true); await b; await tick();
  out.clickOrder = end();
  // C: a chip, then the Bundled demo
  fresh();
  a = desk.useBundledSong("ambient"); b = desk.useDemoSong(); await tick();
  pending["ambient"](true); await a; await tick(); pending["demo"](true); await b; await tick();
  out.thenDemo = end();
  // D: the Bundled demo, then a chip
  fresh();
  a = desk.useDemoSong(); b = desk.useBundledSong("ambient"); await tick();
  pending["demo"](true); await a; await tick(); pending["ambient"](true); await b; await tick();
  out.demoThenChip = end();
  // E: two chips, the second fails, then the first answers
  fresh();
  a = desk.useBundledSong("ambient"); b = desk.useBundledSong("glitch-out"); await tick();
  pending["glitch-out"](false); await b; await tick(); out.afterFailure = end();
  pending["ambient"](true); await a; await tick(); out.failedThenLate = end();
  console.log(JSON.stringify(out));
})();
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the desk's song functions")
def test_two_chips_in_quick_succession_leave_one_song_named_and_held(tmp_path):
    """The reviewer's race (29 Oct): Ambient then Glitch Out clicked while the first load is in flight. Whichever
    answer lands first, the desk ends up naming and holding the last song chosen; a chip and the demo in either order
    behave the same; and a failed second click leaves the desk at the song step, not on the first song's answer."""
    script = tmp_path / "race.js"
    script.write_text(RACE_HARNESS.replace("__APP__", json.dumps(str(STATIC / "app.js"))), encoding="utf-8")
    got = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert 'data-id="glitch-out"' in got["row"] and "Glitch Out<small>3:58</small>" in got["row"] and 'title="Slow and open"' in got["row"]
    assert got["loading"]["ambient"] == {"textContent": "Loading…", "disabled": True}
    for name in ("secondFirst", "clickOrder"):
        assert got[name]["audioId"] == "song-glitch-out" and got[name]["song"] == "glitch-out" and got[name]["label"] == "Glitch Out", (name, got[name])
    assert got["thenDemo"]["audioId"] == "demo" and got["thenDemo"]["song"] == "demo", got["thenDemo"]
    assert got["demoThenChip"]["audioId"] == "song-ambient" and got["demoThenChip"]["song"] == "ambient", got["demoThenChip"]
    assert got["afterFailure"]["song"] == "" and got["afterFailure"]["phase"] == "choose" and "did not load" in got["afterFailure"]["note"]
    assert got["failedThenLate"]["audioId"] == "abc1234567" and got["failedThenLate"]["song"] == ""  # the late answer is dropped


# ---------------------------------------------------------------- the docs
def test_the_docs_name_the_bundled_songs():
    readme = _read("README.md")
    assert "examples/songs/" in readme and "Glitch Out" in readme and "Suno" in readme
    assert "Morphing Wobble" in readme and "Liquid drum and bass" in readme
    tree_scripts = next(line for line in readme.splitlines() if line.startswith("scripts/"))
    assert "analyse_bundled_songs.py" in tree_scripts  # the tree names the script
    credits = _read("CREDITS.md")
    assert "## Bundled songs" in credits and "29 October 2026" in credits
    for row in songs_api.manifest():
        assert f"`{row['file']}`" in credits and row["title"] in credits, row["id"]
    assert "examples/songs/" in _read("docs/LICENCES.md")
    unreleased = _read("CHANGELOG.md").split("## 0.3.3")[1].split("## 0.3.2")[0]
    assert "Bundled songs" in unreleased and "/api/songs/load" in unreleased and "xenoform.songs_api" in unreleased
    hip = songs_api.find("hip-hop-boom-bap")["title"]  # one spelling everywhere: the manifest's, which the chip shows
    assert hip in readme and hip in unreleased and hip in credits and "Hip hop boom bap" not in readme + unreleased
    assert "bundled songs" in _read("docs/REPRODUCE.md") and "examples/demo.wav" in _read("docs/REPRODUCE.md")
    assert "/api/songs/load" in _read("docs/stems.md")
