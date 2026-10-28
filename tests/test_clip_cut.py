"""Clips mode (Tys, 28 Oct): "if we are going to morph movie clips, make it so its just movie clips, and if we are
doing objects just objects". A clips cut alternates your clips and morphs between them; an object cut never takes a
clip."""

import json
from pathlib import Path

import numpy as np

from xenoform import beatfx, clip_cut, dense, lane
from xenoform.video import probe_video, write_mp4

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "demo.wav"


def _clip(path: Path, seconds: float, value: int) -> Path:
    rng = np.random.default_rng(value)
    frames = [np.clip(rng.normal(value, 40, (96, 160, 3)), 0, 255).astype(np.uint8) for _ in range(int(seconds * 24))]
    write_mp4(path, frames, 24)
    return path


def test_slots_alternate_clip_and_morph_and_end_on_a_clip():
    s = clip_cut.slots(5, 2)
    assert [x["kind"] for x in s] == ["clip", "morph", "clip", "morph", "clip"]
    assert [x.get("clip") for x in s if x["kind"] == "clip"] == [0, 1, 0] and s[4]["turn"] == 1
    assert (s[1]["a"], s[1]["b"], s[3]["a"], s[3]["b"]) == (0, 1, 1, 0)
    shots = [{"start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24} for i in range(6)]
    merged = clip_cut.merge_first(shots)
    assert len(merged) == 5 and merged[0]["frames"] == 48 and merged[0]["end"] == 2.0
    assert clip_cut.wants({"morph_source": "clips"}) and not clip_cut.wants({"morph_source": "objects"}) and not clip_cut.wants({})


def test_a_clips_cut_is_only_clips_and_the_morphs_between_them(tmp_path, monkeypatch):
    clips = [{"path": str(_clip(tmp_path / f"0{k}_reel{k}.mp4", 4.0, 60 + 70 * k)), "seconds": 4.0} for k in range(2)]
    plan = [{"start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24, "render_s": 2, "speed": 2.0, "ease": "in",
             "effects": [{"type": "punch", "t": float(i)}, {"type": "stutter", "t": float(i) + 0.2}]} for i in range(5)]
    monkeypatch.setattr(dense, "shots_for", lambda state, directed, audio: ([dict(s) for s in plan], {"name": "t", "shots": []}))
    seen = {}

    def fake_compose(clips_, shots, audio, out, **kw):
        seen.update({"clips": [Path(c) for c in clips_], "shots": shots, **kw})
        Path(out).write_bytes(b"mp4")
        return {"frames": 120, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False, "centres": [],
                "fps": 24, "look": {}, "boundary_fx": {}}

    monkeypatch.setattr(beatfx, "compose", fake_compose)
    state = {"vibe": "neon-noir", "aspect": "9:16", "morph_source": "clips", "own_clips": clips, "dance_fx": "off"}
    rec = dense.run_simple({"duration": 5.0, "beats": [i * 0.5 for i in range(10)]}, DEMO, tmp_path / "x.mp4", tmp_path, {}, state,
                           lambda *a: None, engine="mock")
    assert rec["source"] == "clips" and rec["stills"] == [] and len(rec["clips"]) == 5
    shots = seen["shots"]
    assert [bool(s.get("own")) for s in shots] == [True, False, True, False, True]
    assert all(s["speed"] == 1.0 and "ease" not in s and [e["type"] for e in s["effects"]] == ["punch"] for s in shots[::2])
    assert shots[1]["clip_morph"] == {"from": "reel0", "to": "reel1"} and shots[3]["clip_morph"] == {"from": "reel1", "to": "reel0"}
    for i in (0, 2, 4):  # each clip stretch is exactly its shot, at the cut's size
        info = probe_video(seen["clips"][i])
        assert info["frames"] == 24 and (info["width"], info["height"]) == (540, 960)
    assert seen["foreshadow"] is None and seen["transitions"] is None
    stored = json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert stored["recut_state"]["morph_source"] == "clips" and stored["recut_state"]["foreshadow"] == "off"
    out = lane.build(stored, "c1")
    assert out["rerenderable"] is False and out["swappable"] is False and out["source"] == "clips"
    assert out["shots"][0]["own"] and out["shots"][0]["from"] == "reel0"
    assert out["shots"][1]["clip_morph"] and (out["shots"][1]["from"], out["shots"][1]["to"]) == ("reel0", "reel1")
    chain = json.loads((tmp_path / "simple" / "chain.json").read_text(encoding="utf-8"))
    assert [c["noun"] for c in chain] == ["reel0", "reel1", "reel0"]


def test_an_object_cut_never_takes_a_clip_and_a_clips_cut_takes_no_image(tmp_path):
    from PIL import Image

    from xenoform import ui

    _clip(tmp_path / "01_reel.mp4", 3.0, 100)
    Image.new("RGB", (64, 64), (200, 10, 10)).save(tmp_path / "02_rose.png")
    objects = ui._apply_own({"own_folder": str(tmp_path), "cut_in_clips": True})
    assert objects["own_clips"] == [] and len(objects["morph_targets"]) == 1
    clips = ui._apply_own({"own_folder": str(tmp_path), "morph_source": "clips"})
    assert len(clips["own_clips"]) == 1 and clips["morph_targets"] == []


def test_clips_mode_needs_clips(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(dense, "shots_for", lambda state, directed, audio: ([], {"name": "t"}))
    with pytest.raises(ValueError, match="needs your clips"):
        dense.run_simple({"duration": 5.0, "beats": []}, DEMO, tmp_path / "x.mp4", tmp_path, {}, {"morph_source": "clips"},
                         lambda *a: None, engine="mock")


def test_a_clips_cut_drafts_with_its_clips_never_the_vibes_stills(tmp_path, monkeypatch):
    clips = [{"path": str(_clip(tmp_path / f"0{k}_reel{k}.mp4", 3.0, 80 + 90 * k)), "seconds": 3.0} for k in range(2)]
    plan = [{"start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24} for i in range(3)]
    monkeypatch.setattr(dense, "shots_for", lambda state, directed, audio: ([dict(s) for s in plan], {"name": "t"}))
    monkeypatch.setattr(dense, "chain_preview", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no object chain")))
    info = clip_cut.animatic({"duration": 3.0}, {"own_clips": clips}, DEMO, tmp_path / "draft.mp4", tmp_path / "w")
    assert info["source"] == "clips" and info["shots"] == 3 and (tmp_path / "draft.mp4").is_file()
    turbo = (ROOT / "src" / "xenoform" / "turbo.py").read_text(encoding="utf-8")
    assert "info = clip_cut.animatic(directed, state" in turbo and "clips_cut = clip_cut.wants(state)" in turbo
