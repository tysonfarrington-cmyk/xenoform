"""Energy recut, story sheet, hero lock, conform, chain, QA, titles, judges."""

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from xenoform.analyze import read_features
from xenoform.cutdesk import (
    chain_take,
    conform_story,
    desk_pass,
    is_morph,
    lock_hero,
    morph_budget,
    qa_report,
    recut,
    title_cards,
)
from xenoform.director import text_card_cues
from xenoform.storyboard import plan_storyboard
from xenoform.ui import create_app, repo_root
from xenoform.video import read_all_frames, write_mp4


def _demo():
    features = read_features(repo_root() / "examples" / "demo_features.json")
    scenes = plan_storyboard(features, "pynchon", "a rocket's life from a spark to the dark")
    return features, scenes


def _morphs(scenes):
    return [scene for scene in scenes if is_morph(scene.get("edit"))]


def test_calm_is_the_default_and_strips_morphs():
    features, scenes = _demo()
    assert _morphs(scenes), "the planner still places a signature morph"
    calm = recut(scenes, features, 0)
    assert morph_budget(0) == 0
    assert _morphs(calm) == []
    assert len(calm) == len(features["sections"])
    assert calm[0]["action"] == scenes[0]["action"]
    assert calm[0]["edit"] == "hard cut"


def test_hype_caps_morphs_at_two_and_adds_cuts():
    features, scenes = _demo()
    for energy in (0, 0.2, 0.5, 0.75, 1, 4):
        assert morph_budget(energy) <= 2
    hyped = recut(scenes, features, 1)
    assert len(_morphs(hyped)) == 2
    assert len(hyped) > len(features["sections"])
    assert all(scene["action"] for scene in hyped)


def test_conform_keeps_the_action_and_remaps_time():
    scenes = [
        {"action": "the rocket climbs", "start": 0.0, "end": 2.0, "shot": "wide", "move": "pull back", "edit": "hard cut"},
        {"action": "the rocket breaks open", "start": 2.0, "end": 4.0, "shot": "close", "move": "push in", "edit": "ribbon"},
    ]
    features = {
        "duration": 8.0,
        "tempo": 120.0,
        "sections": [
            {"start": 0.0, "end": 3.0},
            {"start": 3.0, "end": 8.0},
        ],
    }
    laid = conform_story(scenes, features)
    assert laid[0]["action"] == "the rocket climbs"
    assert laid[1]["action"] == "the rocket breaks open"
    assert laid[0]["start"] == 0.0
    assert laid[0]["end"] == 3.0
    assert laid[1]["end"] == 8.0
    scaled = conform_story(scenes, {"duration": 10.0, "tempo": 120.0, "sections": [{"start": 0.0, "end": 10.0}]})
    assert scaled[0]["action"] == "the rocket climbs"
    assert scaled[1]["end"] == 10.0


def test_chain_links_frames_and_snaps_the_hit_to_a_beat():
    scenes = [
        {"start": 0.0, "end": 2.0, "edit": "hard cut", "action": "opens"},
        {"start": 2.0, "end": 4.0, "edit": "hard cut", "action": "hits"},
    ]
    chained = chain_take(scenes, [0.5, 3.5])
    assert chained[0]["guide_from"] == "hero"
    assert chained[0]["action"] == "opens"
    assert chained[1]["guide_from"] == "previous-last"
    assert chained[1]["chain_from"] == 0
    assert chained[1]["edit"] == "continuous"
    assert chained[1]["retime"]["anchors_s"] == [[3.6, 3.5]]
    assert _morphs(chained) == []


def test_hero_lock_does_not_rewrite_the_action():
    scenes = [{"action": "the rocket waits", "conditioning": "signature", "guide": "First frame only."}]
    locked = lock_hero(scenes, "/media/heroes/ada.png", "Ada")
    assert locked[0]["action"] == "the rocket waits"
    assert locked[0]["hero_image"] == "/media/heroes/ada.png"
    assert locked[0]["conditioning"] == "first-frame"
    assert "Hero reference" in locked[0]["guide"]


def test_qa_names_every_gate():
    features, scenes = _demo()
    report = qa_report(recut(scenes, features, 0), features, 0, "minimal")
    assert set(report) == {"sync", "motion", "morph", "flash", "energy"}
    assert report["morph"]["pass"] is True
    assert report["morph"]["count"] == 0
    assert report["flash"]["pass"] is True
    held = qa_report(
        [{"move": "hold", "edit": "hard cut", "start": 0}, {"move": "hold", "edit": "hard cut", "start": 1}],
        {"duration": 2, "beats": [], "sections": []},
        0,
        "minimal",
    )
    assert held["motion"]["pass"] is False
    assert "No beat clock" in held["sync"]["detail"]
    flashing = qa_report(
        [{"move": "follow", "edit": "hard cut", "start": 0}],
        {"duration": 1, "beats": [0.1, 0.2, 0.3, 0.4], "sections": [{"start": 0, "end": 1}]},
        0,
        "hard",
    )
    assert flashing["flash"]["pass"] is False


def test_title_cards_are_separate_from_drop_cards():
    cues = title_cards("The rocket", "Changed", 12)
    assert [cue["at"] for cue in cues] == ["title", "end"]
    assert cues[0]["start"] == 0.35
    assert cues[1]["end"] == 12
    laid = [{"energy": "drop", "start": 4.0, "end": 8.0}]
    mixed = text_card_cues(
        laid,
        [
            {"at": "drop", "text": "Drop line"},
            cues[0],
            cues[1],
        ],
        12,
    )
    assert [cue["at"] for cue in mixed] == ["drop", "title", "end"]
    assert title_cards("", "", 12) == []


def test_frame_guides_keep_the_hero_on_shot_one_and_chain_the_rest(tmp_path):
    frames = [np.full((8, 8, 3), fill, dtype=np.uint8) for fill in range(10, 90, 10)]
    path = tmp_path / "clip.mp4"
    write_mp4(path, frames, 4)
    hero = tmp_path / "hero.png"
    red = np.zeros((4, 4, 3), dtype=np.uint8)
    red[:, :, 0] = 255
    from xenoform.video import ffmpeg_bin
    import subprocess

    proc = subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "4x4",
            "-i",
            "pipe:0",
            str(hero),
        ],
        input=red.tobytes(),
        check=True,
    )
    assert proc.returncode == 0
    from xenoform.cutdesk import apply_frame_guides

    apply_frame_guides(
        path,
        [
            {"start": 0.0, "end": 1.0, "guide_from": "hero"},
            {"start": 1.0, "end": 2.0, "guide_from": "previous-last", "chain_from": 0},
        ],
        4,
        hero,
        continuous=True,
    )
    read = read_all_frames(path)
    assert int(read[0, 0, 0, 0]) > 200
    assert int(read[0, 0, 0, 1]) < 40
    # Frame 3 is the last frame of the first second. The chain copies it onto frame 4.
    assert int(read[4, 0, 0, 0]) == int(read[3, 0, 0, 0])
    assert int(read[4, 0, 0, 0]) < 80


def test_desk_routes_recut_conform_qa_and_judges(tmp_path):
    client = TestClient(create_app())
    demo = client.get("/api/demo").json()
    calm = client.post(
        "/api/recut",
        json={"audio_id": "demo", "energy": 0, "scenes": demo["scenes"], "brief": demo["brief"], "quality": "live"},
    )
    assert calm.status_code == 200
    body = calm.json()
    assert body["qa"]["morph"]["count"] == 0
    assert body["grid"]["beats"]
    assert body["story"]["hero"]
    assert body["story"]["gpu"]["line"] == "no GPU"
    hyped = client.post(
        "/api/recut",
        json={"audio_id": "demo", "energy": 1, "scenes": demo["scenes"], "quality": "turbo", "continuous": True},
    )
    assert hyped.status_code == 200
    assert hyped.json()["qa"]["morph"]["count"] <= 2
    assert hyped.json()["scenes"][1]["guide_from"] == "previous-last"
    conformed = client.post("/api/conform", json={"audio_id": "demo", "scenes": demo["scenes"]})
    assert conformed.status_code == 200
    assert conformed.json()["scenes"][0]["action"] == demo["scenes"][0]["action"]
    sheet = client.post(
        "/api/story/sheet",
        json={"brief": demo["brief"], "scenes": demo["scenes"], "quality": "turbo"},
    )
    assert sheet.status_code == 200
    assert sheet.json()["gpu"]["seconds"] > 0
    assert sheet.json()["journey"]
    qa = client.post("/api/qa", json={"audio_id": "demo", "scenes": body["scenes"], "energy": 0, "flash": "minimal"})
    assert qa.status_code == 200
    assert set(qa.json()) == {"sync", "motion", "morph", "flash", "energy"}

    png = tmp_path / "hero.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x03\x00\x01\x00\x05\xfe\xd4\xef\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    uploaded = client.post("/api/hero", files={"file": ("hero.png", png.read_bytes(), "image/png")})
    assert uploaded.status_code == 200
    hero = uploaded.json()
    assert hero["url"].startswith("/media/heroes/")
    media = client.get(hero["url"])
    assert media.status_code == 200

    page = client.get("/judges")
    assert page.status_code == 200
    assert "Drop a song" in page.text
    assert 'base href="/static/"' in page.text
    script = (Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "judges.js").read_text()
    assert "/api/judges" not in script
    library = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "library"
    for name in ("wide.mp4", "medium.mp4", "close.mp4", "reveal.mp4"):
        assert (library / name).stat().st_size > 500


def test_judges_analyze_is_rate_limited():
    from xenoform import ui as ui_mod

    ui_mod._JUDGE_HITS.clear()
    client = TestClient(create_app())
    payload = {"beats": [0.5, 1.5, 2.5], "duration": 4, "energy": 1}
    for _ in range(6):
        response = client.post("/api/judges/analyze", json=payload)
        assert response.status_code == 200
        assert response.json()["qa"]["morph"]["count"] <= 2
    blocked = client.post("/api/judges/analyze", json=payload)
    assert blocked.status_code == 429
    ui_mod._JUDGE_HITS.clear()


def test_passed_cut_still_carries_the_story():
    features, scenes = _demo()
    passed = desk_pass(scenes, features, energy=0, brief="a rocket's life from a spark to the dark", quality="live")
    assert passed["story"]["logline"].startswith("a rocket")
    assert passed["scenes"][0]["protagonist"] == scenes[0]["protagonist"]
    assert passed["blocks"]
