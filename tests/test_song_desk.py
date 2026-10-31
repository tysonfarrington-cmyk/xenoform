"""Whole song on the desk (docs/SONG.md): the Length row's Whole song beside the 30 s window, the estimate (morphs,
minutes, credits by tier) in the facts, the Make handing the body to POST /api/song, the passage progress (n of m) with
Stop and Resume, the timeline's passages with their jobs and looks (a click opens the passage's own cut), the song's
aside (Lay it together again), and Cloud behind the usual credits tick."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "src" / "xenoform" / "ui_static" / "app.css").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    return APP.split(f"function {name}(")[1].split("\n}\n")[0]


def test_whole_song_sits_beside_the_30_s_window_in_the_length_row():
    row = APP.split('simpleSeg("easy-length"')[1].split('"Length")')[0]
    assert '["30", "30 s"], ["song", "Whole song"]' in row and 'wholeSong(easy) ? "song"' in row
    click = APP.split('act === "easy-length"')[1].split("} else if")[0]
    assert 'state.easy.wholeSong = el.dataset.value === "song";' in click and "loadSimpleOptions()" in click
    saved = APP.split("const EASY_SAVED_KEYS = [")[1].split("];")[0]
    assert '"wholeSong"' in saved and '"songCap"' in saved


def test_the_estimate_shows_morphs_minutes_and_credits_by_tier():
    options = APP.split("async function loadSimpleOptions()")[1].split("\n}\n")[0]
    assert 'whole_song: wholeSong(easy) ? "1" : "",' in options and "song_cap:" in options
    facts = _fn("songPlanFacts")
    for tier, label in (("draft", "Draft"), ("fast", "Fast Final"), ("final", "Final"), ("cloud", "Cloud Final")):
        assert f'["{tier}", "{label}"]' in facts
    assert "songTierText(s, tier)" in facts and "Morphs" in facts and "Passages" in facts
    tier_text = _fn("songTierText")
    assert "Comfy Cloud credits" in tier_text and "row.credits[0]" in tier_text and "measured here" in tier_text
    assert "if (wholeSong(easy)) return songPlanFacts(easy);" in _fn("easyPlanFacts")
    assert "${wholeSong(easy) ? songCapRow(easy) : morphControl(" in APP  # the song's morphs, not one Make's Forms


def test_the_make_hands_the_body_to_the_song_route_after_the_credits_tick():
    make = APP.split("async function easyMake()")[1].split("\nasync function ")[0]
    tick = make.index('"Cloud Final spends your Comfy Cloud credits: tick the box under Model to run it."')
    hand = make.index("await easySongMake();")
    assert tick < hand  # Cloud stays behind the usual tick, a whole song too
    song = _fn("easySongMake")
    assert 'api("/api/song", { method: "POST"' in song and "body: JSON.stringify({ body, song_cap: state.easy.songCap" in song
    assert "state.easy.cloudFinalOk = false;" in song and 'setEasyPhase("making")' in song and "pollSong(data.id)" in song
    assert "<span>Make the whole song</span>" in APP


def test_the_making_screen_says_n_of_m_and_stops_and_resumes_the_whole():
    making = _fn("songMaking")
    assert "passages done" in making and "${v.done || 0} of ${v.of || 0}" in making
    assert 'data-act="song-stop"' in making and 'data-act="song-resume"' in making and "songPassagesTrack(v, total, { open: false })" in making
    assert "if (easy.phase === \"making\" && easy.songRun && !easy.recutting) return songMaking(easy, chosen);" in APP
    poll = _fn("pollSong")
    assert "/api/song/" in poll and 'view.status === "done"' in poll and "openSongResult(view)" in poll
    for act in ("song-stop", "song-resume", "song-assemble", "song-open-passage", "song-back", "song-watch"):
        assert f'act === "{act}"' in APP
    assert 'songAct("stop")' in APP and 'songAct("resume")' in APP and 'songAct("assemble")' in APP


def test_the_timeline_shows_the_passages_with_their_jobs_and_looks():
    track = _fn("songPassagesTrack")
    assert 'data-act="song-open-passage" data-id="${esc(job)}"' in track and "p.name || p.vibe" in track and "job ${" in track
    lane = _fn("shotsLane")
    assert 'const songCut = lane.mode === "song";' in lane and "songPassagesTrack(songViewForLane(lane, easy), total, { open: true })" in lane
    assert "${songTrack}" in lane and "swapping || songCut ? \"\" : timelineDrawer(" in lane
    aside = _fn("songAside")
    assert 'data-act="song-assemble">Lay it together again' in aside and "song-open-passage" in aside
    assert ".song-passages .passage" in CSS and ".song-passages .passage.is-running" in CSS
    assert "songCut ? songAside(easy) :" in APP and 'data-act="song-back">&larr; Back to the whole song' in APP


def test_a_whole_song_still_being_made_shows_under_make_after_a_reload():
    videos = _fn("loadVideos")
    assert 'api("/api/song?limit=4")' in videos and "state.wholeSongs" in videos  # state.songs is the bundled songs
    assert "${songsLine()}" in APP and 'data-act="song-watch"' in _fn("songsLine")
