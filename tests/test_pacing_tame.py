"""The flash tame (docs/MUSIC_VIDEO_PLAN.md section 3; Tys, 30 Oct: "tone down the white flashing light ... sparingly and
subtly"): the demo's deflash in the compose path as the last pass, each passage's own budget (none in the intro), and
post_qa reporting the flash frames per 8 bars by the same test."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

from xenoform import beatfx, deflash as DF, pacing, post_qa
from xenoform.cloud_morph import custom_shots


def test_the_test_finds_a_flash_and_leaves_a_cut():
    y = [60.0] * 12 + [133, 117, 104, 82] + [60.0] * 12  # a flash rising in a frame and decaying over four
    flags = DF.flash_frames(y)
    assert flags[12:16].tolist() == [True, True, True, True] and flags.sum() == 4
    step = [40.0] * 15 + [140.0] * 15  # a cut into a brighter shot: level with what follows, not a flash
    assert DF.flash_frames(step).sum() == 0


def _frames(lumas):
    return [np.full((8, 8, 3), int(v), np.uint8) for v in lumas]


def _run(tame: DF.Tame, frames, rule):
    out = []
    for f in frames:
        out += tame.push(f, rule)
    out += tame.flush()
    return [DF.luma(f) for f in out]


def test_the_tame_lifts_the_veil_and_keeps_a_share_of_it():
    lumas = [60] * 12 + [200] + [60] * 12
    kept = _run(DF.Tame(), _frames(lumas), (DF.KEEP, 99, 1000))
    base, top = DF.luma(_frames([60])[0]), DF.luma(_frames([200])[0])
    assert len(kept) == len(lumas) and abs(kept[12] - (base + DF.KEEP * (top - base))) < 1.0  # 35 % of the rise laid back
    assert kept[:12] == [base] * 12  # the frames around it untouched
    none = _run(DF.Tame(), _frames(lumas), (0.0, 0, 1000))
    assert abs(none[12] - base) < 1.0 and DF.flash_frames(none).sum() == 0  # the intro's budget: no flash at all
    raw = _run(DF.Tame(), _frames(lumas), None)
    assert raw == [DF.luma(f) for f in _frames(lumas)]  # no rule, no tame


def test_a_window_holds_its_budget():
    lumas = []
    for _ in range(8):
        lumas += [50] * 6 + [220]
    lumas += [50] * 6
    out = _run(DF.Tame(), _frames(lumas), (DF.KEEP, 3, 1000))
    assert DF.flash_frames(lumas).sum() == 8 and DF.flash_frames(out).sum() <= 3  # three kept, the rest under the line


def test_the_rules_follow_the_passages():
    shots = [{"section": "intro", "frames": 10}, {"section": "calm", "frames": 10}, {"section": "build", "frames": 10, "ramp": 0.5},
             {"section": "drop", "frames": 10}, {"section": "outro", "frames": 10}]
    rules = pacing.flash_rules(shots, 24, [i * 0.5 for i in range(20)])
    assert len(rules) == 50 and rules[0] == (0.0, 0, 384)  # 8 bars at 120 bpm, 24 fps
    assert rules[10][1] == 16 and rules[20][1] == 32 and rules[30][1] == 40 and rules[40][:2] == (0.0, 0)


def _flash_clip(path: Path, seconds: float) -> Path:
    """A dark clip with one beat flash in it, rising in a frame and decaying over three (as the montage measured)."""
    boxes = ",".join(f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{v:02x}{v:02x}{v:02x}:t=fill:enable='eq(n,{n})'"
                     for n, v in ((24, 0xE0), (25, 0xB0), (26, 0x80), (27, 0x58)))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x202020:s=64x112:r=24:d={seconds}",
                    "-vf", boxes, "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _wav(path: Path, seconds: float, sr: int = 22050) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.zeros(int(seconds * sr), "<i2").tobytes())
    return path


def test_the_compose_path_tames_a_white_flash(tmp_path):
    clip = _flash_clip(tmp_path / "f.mp4", 2.0)
    audio = _wav(tmp_path / "s.wav", 2.0)
    shots = custom_shots({"shots": [{"start": 0.0, "end": 2.0, "render_s": 2}]}, 2.0)
    kw = dict(aspect="9:16", fx=False, dance_fx="off", stem_orbit=False, size=(64, 112))
    beatfx.compose([clip], shots, audio, tmp_path / "raw.mp4", **kw)
    beats = [i * 0.5 for i in range(8)]
    intro = pacing.flash_rules([{"section": "intro", "frames": 48}], 24, beats)
    made = beatfx.compose([clip], shots, audio, tmp_path / "tamed.mp4", tame=intro, **kw)
    drop = pacing.flash_rules([{"section": "drop", "frames": 48}], 24, beats)
    beatfx.compose([clip], shots, audio, tmp_path / "drop.mp4", tame=drop, **kw)
    raw = post_qa._grey_lumas(tmp_path / "raw.mp4")
    tamed = post_qa._grey_lumas(tmp_path / "tamed.mp4")
    kept = post_qa._grey_lumas(tmp_path / "drop.mp4")
    assert DF.flash_frames(raw).sum() == 4 and made["frames"] == 48 and made["tame"]["tamed"] == 4
    assert DF.flash_frames(tamed).sum() == 0  # the intro: no flash at all
    rise_raw, rise_kept = raw[24] - raw[20], kept[24] - kept[20]
    assert 0.25 * rise_raw < rise_kept < 0.45 * rise_raw  # a drop keeps 35 % of it: the beat still pulses, subtly
    rep = post_qa.veil_report(tmp_path / "raw.mp4", 24.0, beats)
    assert rep["flash_frames"] == 4 and rep["max_8_bars"] == 4 and rep["windows"] == [4]


def test_breathe_turns_the_tame_on(tmp_path, monkeypatch):
    from xenoform import dense

    seen = {}

    def spy(clips, shots, audio, out, **kw):
        seen["tame"] = kw.get("tame")
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "transitions": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    monkeypatch.setattr(dense, "stills_for", lambda state, n, **kw: ("black", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(n)]))
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i}.mp4" for i in range(len(shots))])
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo.wav"
    beats = [i * 0.5 for i in range(40)]
    dense.run_simple({"duration": 20.0, "beats": beats}, demo, tmp_path / "a.mp4", tmp_path / "a", {},
                     {"vibe": "black", "aspect": "16:9", "energy_preset": "dense", "breathe": True}, lambda *a: None, engine="mock")
    assert seen["tame"] and len(seen["tame"]) == 480
    dense.run_simple({"duration": 20.0, "beats": beats}, demo, tmp_path / "b.mp4", tmp_path / "b", {},
                     {"vibe": "black", "aspect": "16:9", "energy_preset": "dense"}, lambda *a: None, engine="mock")
    assert seen["tame"] is None  # Breathe off (the default): the frames as they come
