"""Shot review, lyric offset, the test-clip gate, lettering, and the share cut."""

import numpy as np
from fastapi.testclient import TestClient

from xenoform.craft import (
    apply_lead,
    lettering,
    paint_review_png,
    pick_take,
    remake,
    share_cut,
    shift_lyrics,
    song_timing,
    strip_onscreen,
    clip_gate,
    text_only_shots,
)
from xenoform.storyboard import scene_prompt, stamp_treatment
from xenoform.ui import create_app
from xenoform.video import overlay_text, probe_video, write_mp4

LEAD = "The lead is one figure, the same silhouette in every shot."


def _scene(**extra):
    row = {
        "index": 0,
        "action": "the rocket is born",
        "form": "rocket",
        "shot": "wide",
        "move": "pull back",
        "edit": "hard cut",
        "mood": "cold",
        "bars": 2,
        "guide": "the rocket is born",
        "retime": "",
        "guide_strengths": None,
        "fade_frames": 0,
    }
    row.update(extra)
    return row


def test_same_seed_repeats_and_a_new_seed_is_kept():
    take, takes = remake([], scene=0, prompt="born", seed=2727)
    assert take["id"] == "s0-2727"
    assert take["repeated"] is False
    again, takes = remake(takes, scene=0, prompt="born", seed=2727)
    assert again["repeated"] is True
    assert len(takes) == 1
    fresh, takes = remake(takes, scene=0, prompt="born again", seed=2728)
    assert fresh["repeated"] is False
    assert [item["seed"] for item in takes] == [2727, 2728]
    picked = pick_take(takes, scene=0, seed=2727)
    assert [item["picked"] for item in picked] == [True, False]


def test_text_only_change_is_one_shot():
    before = [_scene(index=0), _scene(index=1, action="climbs", guide="climbs")]
    words = [_scene(index=0, action="the rocket waits", guide="the rocket waits", prompt="the rocket waits"), before[1]]
    assert text_only_shots(before, words) == [0]
    grammar = [_scene(index=0, shot="close"), before[1]]
    assert text_only_shots(before, grammar) is None


def test_gate_wants_one_or_two_clips():
    assert clip_gate([])["ok"] is False
    assert clip_gate(["s0"])["ok"] is True
    assert clip_gate(["s0", "s1"])["ok"] is True
    assert clip_gate(["s0", "s0", "s1"])["count"] == 2
    assert clip_gate(["s0", "s1", "s2"])["ok"] is False
    assert "1 or 2" in clip_gate([])["detail"]


def test_lead_sentence_is_inserted_once_and_the_action_stays():
    scenes = [
        {"index": 0, "beat": "setup", "action": "the rocket is born, cold and paranoid", "form": "rocket"},
        {"index": 1, "beat": "climax", "action": "the rocket hits", "form": "rocket", "signature": True},
        {"index": 2, "beat": "release", "action": "the rocket falls back", "form": "rocket"},
    ]
    actions = [scene["action"] for scene in scenes]
    stamp_treatment(scenes, "life")
    assert actions == [scene["action"] for scene in scenes]
    assert {scene["lead"] for scene in scenes} == {LEAD}
    assert "liquid chrome" not in LEAD
    prompt = scene_prompt(scenes[0], "base")
    assert prompt.count(LEAD) == 1
    assert "does not morph" in prompt
    assert "liquid chrome" not in prompt.lower()
    titled = apply_lead("a subtitle across the sky", LEAD)
    assert "subtitle" not in titled.lower()
    cleaned = strip_onscreen("burned-in text on a title card")
    assert "title card" not in cleaned
    assert "burned" not in cleaned


def test_lyric_offset_moves_words_later_and_stays_off():
    shifted = shift_lyrics([{"word": "born", "start": 1.0, "end": 1.4}], 0.9)
    assert shifted[0]["start"] == 1.9
    early = shift_lyrics([{"word": "born", "start": 1.0, "end": 1.2}], 0.2)
    assert early[0]["start"] == 1.3
    late = shift_lyrics([{"word": "born", "start": 1.0, "end": 1.2}], 2)
    assert late[0]["start"] == 2.5
    features = {
        "beats": [0.5, 1.0],
        "duration": 4,
        "sections": [{"label": "drop", "start": 0, "end": 4}],
        "frames": [{"high": 0.4, "mid": 0.4}] * 10,
    }
    quiet = song_timing(features, [{"word": "born", "start": 1.0, "end": 1.2}], enabled=False, offset=0.9)
    assert quiet["lyrics"] == []
    assert quiet["asr"] == "off"
    assert quiet["enabled"] is False
    spoken = song_timing(features, [{"word": "born", "start": 1.0, "end": 1.2}], enabled=True, offset=0.9)
    assert spoken["asr"] == "off"
    assert spoken["lyrics"][0]["start"] == 1.9
    silent = song_timing({**features, "frames": [{"high": 0.0, "mid": 0.0}]}, [{"word": "born", "start": 1, "end": 1.2}], enabled=True)
    assert silent["lyrics"] == []
    assert "No vocals" in silent["note"]


def test_lettering_misses_faces_and_bands_a_pale_ground():
    frame = np.zeros((100, 80, 3), dtype=np.uint8)
    frame[10:30, 10:40] = (180, 90, 60)
    high = lettering(frame)
    assert high["faces"] is True
    assert high["pass"] is True
    low = frame.copy()
    low[90:99, 10:40] = (180, 90, 60)
    assert lettering(low)["faces"] is False
    pale = np.full((100, 80, 3), 220, dtype=np.uint8)
    bare = lettering(pale, faces=[])
    assert bare["pale"] is True
    assert bare["band"] is False
    assert bare["pass"] is False
    covered = lettering(pale, faces=[], band=True)
    assert covered["band"] is True
    assert covered["pass"] is True


def test_share_cut_is_720p_h264_under_16mb(tmp_path):
    frames = [np.full((36, 64, 3), 40, dtype=np.uint8) for _ in range(4)]
    src = tmp_path / "src.mp4"
    write_mp4(src, frames, 12)
    dest = tmp_path / "share.mp4"
    result = share_cut(src, dest, duration=4 / 12)
    assert result["under"] is True
    assert result["bytes"] < 16 * 1024 * 1024
    probed = probe_video(dest)
    assert probed["width"] == 1280
    assert probed["height"] == 720
    import json
    import subprocess

    from xenoform.video import ffprobe_bin

    raw = subprocess.check_output(
        [ffprobe_bin(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "json", str(dest)],
        text=True,
    )
    assert json.loads(raw)["streams"][0]["codec_name"] == "h264"
    overlay_text(dest, [{"text": "Birth", "start": 0.0, "end": 0.2}])
    assert dest.exists()
    assert probe_video(dest)["width"] == 1280


def test_review_routes_stay_local(tmp_path):
    still = paint_review_png(tmp_path, seed=2727, shot="wide", prompt="born", index=0)
    again = paint_review_png(tmp_path, seed=2727, shot="wide", prompt="born", index=0)
    assert still == again
    assert still.stat().st_size > 32
    client = TestClient(create_app())
    remade = client.post("/api/review/remake", json={"scene": 1, "seed": 2727, "prompt": "the climb", "takes": []})
    assert remade.status_code == 200
    body = remade.json()
    assert body["text_only"] is True
    assert body["only_scenes"] == ["s1"]
    assert body["takes"][0]["seed"] == 2727
    timing = client.post("/api/timing", json={"audio_id": "demo", "lyrics": False, "offset": 0.2, "words": [{"word": "born", "start": 1, "end": 1.2}]})
    assert timing.status_code == 200
    clock = timing.json()
    assert clock["asr"] == "off"
    assert clock["lyrics"] == []
    assert clock["beats"]
    shared = client.get("/api/share")
    assert shared.status_code == 200
    assert shared.headers["content-type"].startswith("video/mp4")
    assert len(shared.content) < 16 * 1024 * 1024
