"""The desk's drop card agrees with the planner (the follow-ups of 1 Nov): it names the main drop run as the whole-song
planner picks it, the heaviest by heat times length (pacing.heaviest, pacing.main_run), with its time and length, and the
30 s prototype window is cut around that very run (pacing.prototype_window, the rule the Make's trim and the estimate
use). One source of truth: the card, the window and song_plan.main_run choose by the same rule."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenoform import dense, pacing, song_plan

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"


def _features(name: str) -> dict:
    return json.loads((SONGS / f"{name}.features.json").read_text(encoding="utf-8"))


def test_the_heaviest_run_is_heat_times_length_a_tie_to_the_run_the_drop_opens():
    runs = [{"heat": 1.0, "seconds": 5.3, "opens": True}, {"heat": 1.0, "seconds": 23.7}, {"heat": 0.5, "seconds": 30.0}]
    assert pacing.heaviest(runs) == 1  # ZedsDead v1: the 23.7 s run after the drop's own 5.3 s
    assert pacing.heaviest([{"heat": 0.5, "seconds": 20.0}, {"heat": 1.0, "seconds": 10.0, "opens": True}]) == 1
    assert pacing.heaviest([{"heat": 1.0, "start": 0.0, "end": 10.0}, {"heat": 1.0, "start": 20.0, "end": 30.0}]) == 0
    assert pacing.heaviest([]) is None


def _zeds_like() -> dict:
    """A song shaped like ZedsDead v1: the drop's own run is short and loud, a long run follows it."""
    beats = [round(i * 0.5, 4) for i in range(240)]
    secs = [{"label": "calm", "start": 0.0, "end": 40.0, "level": 0.3}, {"label": "build", "start": 40.0, "end": 52.0, "level": 0.6},
            {"label": "drop", "start": 52.0, "end": 60.0, "level": 1.0}, {"label": "release", "start": 60.0, "end": 68.0, "level": 0.5},
            {"label": "drop", "start": 68.0, "end": 100.0, "level": 0.95}, {"label": "calm", "start": 100.0, "end": 120.0, "level": 0.4}]
    return {"duration": 120.0, "beats": beats, "tempo": 120.0, "sections": secs}


def test_the_main_run_is_the_planners_on_the_bundled_songs_and_a_long_run_after_a_short_drop():
    for name in ("glitch-out", "ambient", "liquid-dnb", "hip-hop-boom-bap"):
        f = _features(name)
        audio = next(SONGS.glob(name.replace("-", "_") + ".mp3"), None)
        drop = dense.find_drop(audio, f["beats"], f["duration"]) if audio else None
        main = pacing.main_run(f, drop)
        if f["duration"] <= dense.LONG_SONG_S or main is None:
            continue
        song = song_plan.plan(f, {"vibe": "cosmic", "breathe": 1.0, "drop_mode": "auto"}, drop=drop, pick=False)
        planned = next(p for p in song["passages"] if p.get("main"))
        assert abs(planned["start"] - main["start"]) < 1e-3 and abs(planned["end"] - main["end"]) < 1e-3, name
        assert pacing.main_drop(f, drop) == main["start"]
    glitch = _features("glitch-out")
    m = pacing.main_run(glitch, dense.find_drop(SONGS / "glitch_out.mp3", glitch["beats"], glitch["duration"]))
    assert pacing.clock(m["start"]) == "2:21" and m["heat"] == 1.0 and m["runs"] == 5 and m["opens"]
    z = _zeds_like()
    zm = pacing.main_run(z, 52.0)
    assert zm["start"] == 68.0 and zm["seconds"] == 32.0 and not zm["opens"] and zm["runs"] == 2  # the long run, not the hit
    assert pacing.main_drop(z, 52.0) == 68.0


def test_the_prototype_window_is_cut_around_the_main_run():
    z = _zeds_like()
    win = pacing.prototype_window(z, 52.0, 30.0)
    assert win["anchor"] == 68.0 and win["main"]["start"] == 68.0
    assert win["start"] == 54.5 and win["end"] == 84.5  # the run's first beat 45 % in, the window on a beat
    old = pacing.prototype_window(z, 52.0, 30.0, paced=False)  # Breathe and Drops off: around the drop time, as before
    assert old["anchor"] == 52.0 and old["main"] is None
    assert pacing.prototype_window(z, 52.0, 0.0) is None and pacing.prototype_window({**z, "duration": 20.0}, 5.0, 30.0) is None
    from xenoform import ui

    feats, start, drop = ui._window_features(z, None, 30.0, paced=True)
    assert start == win["start"]  # the estimate's window (and the Make's trim) is the card's


def test_the_drop_card_names_the_main_run_and_the_window(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui

    client = TestClient(ui.create_app())
    assert client.post("/api/songs/load", json={"id": "glitch-out"}).status_code == 200
    card = client.post("/api/opener", json={"audio_id": "song-glitch-out", "length_s": 30, "breathe": "on", "drop_mode": "auto"}).json()
    feats = ui._FEATURES["song-glitch-out"]
    drop = dense.find_drop(ui._AUDIO["song-glitch-out"], feats["beats"], feats["duration"])
    main = pacing.main_run(feats, drop)
    assert card["ready"] and card["main"] == main and card["at"] == main["start"]
    assert pacing.clock(card["main"]["start"]) == "2:21" and "The heaviest of 5 drop runs" in card["line"]
    win, start, _ = ui._window_features(feats, ui._AUDIO["song-glitch-out"], 30.0, paced=True)
    assert card["window"]["start"] == start and card["window"]["on_main"]
    assert "prototype is cut around it" in card["line"]
    assert card["first_at"] is not None and card["first_at"] < card["at"]  # the first drop (1:31) is not the main one
    plain = client.post("/api/opener", json={"audio_id": "song-glitch-out", "breathe": "off", "drop_mode": "off"}).json()
    assert plain["main"] == main and not plain["window"]["on_main"]  # unpaced: the window is the drop time's, said so
    demo = client.post("/api/opener", json={"audio_id": "demo"}).json()
    assert demo["ready"] is True and demo["at"] >= 0


def test_the_desk_card_shows_the_main_run_and_asks_with_the_shape():
    app = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    title = app.split("function dropCardTitle(opener) {", 1)[1].split("\n}\n", 1)[0]
    assert "The main drop: ${clockText(Number(main.start || 0))}, ${Math.round(Number(main.seconds || 0))} s" in title
    ask = app.split("function scheduleOpener() {", 1)[1].split("\nfunction paintOpener", 1)[0]
    assert "length_s:" in ask and "drop_mode: easy.dropMode" in ask and "body.key = ask;" in ask
    assert "opener.main ? dropCardTitle(opener)" in app.split("function paintOpener() {", 1)[1].split("\n}\n", 1)[0]
