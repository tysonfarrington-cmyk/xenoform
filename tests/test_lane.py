"""The shots lane (25 Oct 2026): a cut's record becomes a read-only strip of shots with objects, sections, transitions
and slots; the desk serves it per video and draws it under the result player; the browser tier says what it is."""
from pathlib import Path

from xenoform import lane

ROOT = Path(__file__).resolve().parents[1]


def _info():
    shots = [
        {"index": 0, "start": 0.0, "end": 4.0, "section": "intro"},
        {"index": 1, "start": 4.0, "end": 6.0, "section": "drop", "boundary": "drop"},
        {"index": 2, "start": 6.0, "end": 8.0, "section": "drop"},
        {"index": 3, "start": 8.0, "end": 12.0, "section": "outro", "boundary": "switch"},
    ]
    return {
        "shots": shots,
        "stills": ["cosmic/00_orb_iridescent.jpg", "cosmic/01_crescent_moon_oil_slick.jpg", "cosmic/000_brass_astrolabe.jpg"],
        "chain": {"morphs": 3, "assign": [0, 1, 2, 0], "reuse": True},
        "transitions": [None, {"kind": "match-cut", "frames": 12, "boundary": "drop"}, None, {"kind": "lens-breath", "frames": 10, "boundary": "switch"}],
        "performer": {"shots": 1, "slots": [{"first": 1, "last": 2, "instrument": "drums", "seconds": 4.0}], "notes": []},
        "own": {"clips": 1, "images": 0, "slots": [{"first": 3, "last": 3, "clip": "C:/footage/walk.mp4", "seconds": 4.0}], "notes": []},
        "plan_name": "story", "recut_state": {"pace": "viscous"}, "engine": "LTX 0.9.5 (Draft)",
    }


def test_build_lays_the_cut_out_shot_by_shot():
    out = lane.build(_info(), "abc123")
    assert out["id"] == "abc123" and out["duration"] == 12.0 and out["morphs"] == 3 and out["objects"] == 3
    rows = out["shots"]
    assert [r["seconds"] for r in rows] == [4.0, 2.0, 2.0, 4.0]
    assert rows[0]["from"] == "orb iridescent" and rows[0]["to"] == "crescent moon oil slick"
    assert rows[2]["from"] == "brass astrolabe" and rows[2]["to"] == "orb iridescent"  # the chain comes round
    assert rows[3]["from"] == "orb iridescent"  # assign 0 again
    assert rows[1]["boundary"] == "drop" and rows[1]["transition"] == "match-cut" and "transition" not in rows[0]
    assert [s["section"] for s in out["sections"]] == ["intro", "drop", "outro"] and out["sections"][1] == {"section": "drop", "start": 4.0, "end": 8.0}
    assert out["overlays"] == [
        {"kind": "performer", "first": 1, "last": 2, "start": 4.0, "end": 8.0, "label": "drums"},
        {"kind": "own", "first": 3, "last": 3, "start": 8.0, "end": 12.0, "label": "walk.mp4"},
    ]
    assert out["pace"] == "viscous" and out["plan"] == "story" and out["engine"].startswith("LTX")


def test_build_copes_with_a_short_cut_and_an_empty_record():
    info = {"shots": [{"start": 0.0, "end": 2.0}, {"start": 2.0, "end": 4.0}], "stills": ["v/00_a.jpg", "v/01_b.jpg", "v/02_c.jpg"]}
    out = lane.build(info)
    assert [(r["from"], r["to"]) for r in out["shots"]] == [("a", "b"), ("b", "c")]  # one morph a shot: still i -> i+1
    assert out["morphs"] == 2 and out["overlays"] == [] and out["sections"] == []
    empty = lane.build({})
    assert empty["shots"] == [] and empty["duration"] == 0.0


def test_desk_serves_the_lane_per_video_and_refuses_an_unknown_one():
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())
    assert client.get("/api/videos/no-such-video/shots").status_code == 404


def test_front_end_draws_the_lane_and_names_the_browser_tier():
    js = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "src/xenoform/ui_static/app.css").read_text(encoding="utf-8")
    assert "function shotsLane(easy)" in js and "${shotsLane(easy)}" in js and 'data-act="easy-seek"' in js
    assert "/api/videos/${encodeURIComponent(id)}/shots" in js and ".shots-lane .shot" in css
    assert "ComfyUI is not answering at ${" in js and "not answering: Make will play the vibe's pictures in the browser, no render" in js
    assert "Seconds, in the browser" not in js  # the silent fallback wording is gone


def test_featured_vibes_carry_a_default_look():
    from xenoform import beatfx, vibes

    picks = {row["id"]: beatfx.resolve_dance_preset("auto", row["id"]) for row in vibes.featured()}
    assert picks["chrome-mercury"] == "cool-echo" and picks["neon-noir"] == "noir-glow" and picks["botanical"] == "bloom-rush"
    assert picks["ink-wash"] == "house"  # ink on paper keeps the house look
    assert sum(1 for v in picks.values() if v != "house") >= 10
