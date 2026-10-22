"""The house profile (demo_house) is wired into dance_fx / transitions_fx / stem_orbit / beatfx / dense.
CPU only, tiny synthetic frames, no ComfyUI."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx, dense
from xenoform import dance_fx as D
from xenoform import stem_orbit as O
from xenoform import transitions_fx as T
from xenoform.config import house, load_config
from xenoform.demo_house import DEMO_HOUSE

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _frame(h=48, w=32, v=40):
    f = np.full((h, w, 3), v, np.uint8)
    f[14:36, 10:22] = 230
    return f


def _env(n=48, fps=24):
    return {"fps": fps, "drums": [0.8] * n, "bass": [0.5] * n, "other": [0.3] * n, "vocals": [0.1] * n,
            "drum_strong": [0.0, 0.5, 1.0]}


# ---------------------------------------------------------------- config.house
def test_config_house_is_the_demo_profile_and_a_copy():
    assert house()["name"] == "demo_house" and house() == DEMO_HOUSE == load_config()["house"]
    h = house("dance_fx")
    h["vj"]["preset"] = "noir-glow"
    assert DEMO_HOUSE["dance_fx"]["vj"]["preset"] == "cool-echo"
    assert house("nope") == {}
    assert house("format", cfg={"house": {"format": {"fps": 30}}})["fps"] == 30
    assert house("format", cfg={})["fps"] == 24
    assert "TODO" not in __import__("xenoform.demo_house", fromlist=["x"]).__doc__


# ---------------------------------------------------------------- dance_fx
def test_dance_fx_falls_back_to_the_house_role():
    fx = D.DanceFX()
    assert (fx.preset, fx.k, fx.role) == ("cool-echo", 1.4, "vj")
    for role, want in DEMO_HOUSE["dance_fx"].items():
        fx = D.DanceFX(role=role)
        assert fx.preset == want["preset"] and fx.k == pytest.approx(min(1.5, want["intensity"]))
    assert D.DanceFX(role="into_card").invert_floor_ramp_frames == 14
    assert D.DanceFX(role="vj").invert_floor_ramp_frames == 0
    fx = D.DanceFX("warm-leak", role="intro")  # explicit preset wins, intensity still from the role
    assert fx.preset == "warm-leak" and fx.k == 1.25
    assert D.DanceFX(intensity=0.3, role="intro").k == 0.3
    assert D.resolve(None, None, "flower") == ("bloom-rush", 1.5, DEMO_HOUSE["dance_fx"]["flower"])
    custom = {"vj": {"preset": "noir-glow", "intensity": 0.7}}
    assert D.DanceFX(house=custom).preset == "noir-glow"
    with pytest.raises(ValueError):
        D.DanceFX("auto")


def test_dance_fx_copies_the_preset_table():
    fx = D.DanceFX("cool-echo")
    fx.p["echo_decay"] = 0.1
    fx.p["invert_floor"] = 1.0
    assert "invert_floor" not in D.PRESETS["cool-echo"] and D.PRESETS["cool-echo"].get("echo_decay") is None
    assert fx.p is not D.PRESETS["cool-echo"]


def test_none_drive_values_are_zero():
    f = _frame()
    fx = D.DanceFX("warm-leak")
    a = fx.apply(f, {"drums": None, "bass": None, "other": None, "vocals": None, "beat": None})
    b = D.DanceFX("warm-leak").apply(f, {})
    c = D.DanceFX("warm-leak").apply(f, None)
    assert np.array_equal(a, b) and np.array_equal(a, c)


def test_into_card_ramps_the_invert_floor_over_the_last_frames():
    env = dict(_env(), drum_strong=[])  # no beat pulses: the preset's own negative stays at a steady level
    frames = [_frame()] * 30
    out = list(D.render_shot(frames, env, 0.0, role="into_card", invert_floor_ramp_frames=10))
    assert len(out) == 30
    bright = [float(o[14:36, 10:22].mean()) for o in out]  # the subject (bright) gets darker as the negative lands
    assert bright[-1] < bright[10] - 20
    # the ramp is monotone over its last frames
    tail = bright[-10:]
    assert all(b2 <= b1 + 1e-6 for b1, b2 in zip(tail, tail[1:]))
    # the house value (14) is used when not given; explicit 0 means no ramp
    fx = D.DanceFX(role="into_card")
    assert fx.invert_floor_ramp_frames == 14
    plain = list(D.render_shot(frames, env, 0.0, role="into_card", invert_floor_ramp_frames=0))
    assert np.array_equal(plain[5], out[5])  # frames before the ramp are untouched by it
    assert float(plain[-1][14:36, 10:22].mean()) > bright[-1] + 20


def test_render_shot_fps_defaults_to_the_house_format():
    env = _env()
    a = list(D.render_shot([_frame()] * 4, env, 0.0, "warm-leak"))
    b = list(D.render_shot([_frame()] * 4, env, 0.0, "warm-leak", fps=24))
    assert all(np.array_equal(x, y) for x, y in zip(a, b))


def test_stem_gains_weight_named_stems_before_the_roles():
    env = {"fps": 24, "stems": ["kick", "pad"], "roles": {"kick": "drums", "pad": "other"},
           "kick": [1.0] * 10, "pad": [1.0] * 10, "drums": [1.0] * 10, "other": [1.0] * 10, "drum_strong": []}
    full = D.drive_from_env(env, 0.1)
    muted = D.drive_from_env(env, 0.1, gains={"kick": 0.0, "pad": 0.5})
    assert full["drums"] == 1.0 and muted["drums"] == 0.0 and muted["other"] == 0.5
    assert D.drive_from_env({}, 0.0)["beat"] == 0.0


# ---------------------------------------------------------------- transitions_fx
def test_transitions_fall_back_to_the_house_rules():
    assert T.recommend("black", "beat") == "cut" and T.recommend("black", "drop", classic=True) == "scene-morph"
    rules = DEMO_HOUSE["transitions"]
    cap, allowed, banned = T._resolve_rules(None, None, None)
    assert (cap, allowed, banned) == (rules["max_uses_per_type"], rules["allowed"], rules["banned"])
    assert T._resolve_rules(3, [], ["x"]) == (3, [], ["x"])
    picks = T.plan([{"section": True}] * 12, seed=1)
    premium = [p for p in picks if p != "cut"]
    assert premium and set(premium) <= set(rules["allowed"])
    assert max(premium.count(p) for p in set(premium)) <= rules["max_uses_per_type"]
    wide = T.plan([{"section": True}] * 12, seed=1, allowed=[], cap=1)
    assert len({p for p in wide if p != "cut"}) >= 3  # no whitelist: the whole premium pool, one each
    out, msgs = T.guard(["datamosh", "echo-trail", "kaleidoscope"] if "kaleidoscope" in T.TRANSITIONS else ["echo-trail"])
    assert "echo-trail" in out
    out, msgs = T.guard(["luma-wipe", "match-cut"], banned=["match"], allowed=["echo-trail"])
    assert out[1] != "match-cut" and any("banned" in m for m in msgs)
    keep, msgs = T.guard(["match-cut"], banned=["match"], expert=True)
    assert keep == ["match-cut"] and any("kept: expert" in m for m in msgs)


def test_transition_apply_intensity_falls_back_to_the_house():
    a = [np.full((16, 12, 3), 30, np.uint8)] * 4
    b = [np.full((16, 12, 3), 200, np.uint8)] * 4
    assert T.DEFAULT_INTENSITY == 0.5
    x = T.apply("liquid-melt", a, b)
    y = T.apply("liquid-melt", a, b, 0.5)
    assert all(np.array_equal(p, q) for p, q in zip(x, y))


# ---------------------------------------------------------------- stem_orbit
def test_stem_orbit_falls_back_to_the_house():
    env = _env()
    assert O.house_fps() == DEMO_HOUSE["format"]["fps"] and O.house_fps(30) == 30
    p = O.params(max_yaw=None, focal=None, spin=3.0)
    assert p["max_yaw"] == DEMO_HOUSE["stem_orbit"]["max_yaw"] and p["focal"] == DEMO_HOUSE["stem_orbit"]["focal"] and p["spin"] == 3.0
    a = O.plan(env, 0.0, 20)
    b = O.plan(env, 0.0, 20, fps=None, max_yaw=None, bass=None)
    assert np.array_equal(a["yaw"], b["yaw"])
    H1 = O.homography(32, 48, 10.0, focal=DEMO_HOUSE["stem_orbit"]["focal"])
    if O.cv2 is None:
        with pytest.raises(RuntimeError):
            O.apply(_frame(), 10.0, focal=None)
    else:
        assert O.apply(_frame(), 10.0, focal=None).shape == (48, 32, 3)
    assert H1.shape == (3, 3)


# ---------------------------------------------------------------- beatfx.LookPass + dense keys
def test_dense_options_carry_the_look_keys():
    assert dense.options({})["dance_fx"] == "auto" and dense.options({})["stem_orbit"] is True
    assert dense.options({"dance_fx": "off"})["dance_fx"] == "off"
    assert dense.options({"dance_fx": "Cyan-Flash"})["dance_fx"] == "cyan-flash"
    assert dense.options({"dance_fx": "bogus"})["dance_fx"] == "auto"
    assert dense.options({"dance_fx": False})["dance_fx"] == "off"
    for raw, want in ((False, False), ("off", False), ("0", False), (True, True), ("yes", True), (None, True), ("", True)):
        assert dense.options({"stem_orbit": raw})["stem_orbit"] is want
    assert beatfx.resolve_dance_preset("auto", "black") == "house"
    assert beatfx.resolve_dance_preset("off") == "off" and beatfx.resolve_dance_preset(None) == "house"
    assert beatfx.resolve_dance_preset("noir-glow") == "noir-glow"
    with pytest.raises(ValueError):
        beatfx.resolve_dance_preset("bogus")


def test_resolve_dance_preset_honours_a_vibe_fx_default(monkeypatch):
    from xenoform import vibes as V

    monkeypatch.setattr(V, "extended", lambda: [{"id": "neon-night", "fx_defaults": {"dance_fx": "cyan-flash"}}])
    assert beatfx.resolve_dance_preset("auto", "neon-night") == "cyan-flash"
    assert beatfx.resolve_dance_preset("auto", "black") == "house"
    assert beatfx.resolve_dance_preset("off", "neon-night") == "off"


def test_stem_env_for_reads_the_job_stems_or_none(tmp_path):
    assert dense.stem_env_for({}) is None and dense.stem_env_for({"stems_path": str(tmp_path / "nope.json")}) is None
    p = tmp_path / "stems.json"
    p.write_text(json.dumps(_env()), encoding="utf-8")
    env = dense.stem_env_for({"stems_path": str(p)})
    assert env and env["fps"] == 24 and len(env["drums"]) == 48
    p.write_text(json.dumps({"fps": 24}), encoding="utf-8")
    assert dense.stem_env_for({"stems_path": str(p)}) is None


def test_mix_stem_env_derives_four_roles_from_the_beat_fx_envelopes():
    env = {"kick": np.array([0.0, 1.0]), "trans": np.array([0.5, 0.5]), "loud": np.array([1.0, 1.0])}
    se = beatfx.mix_stem_env(env, [0.0, 0.5], 24)
    assert se["bass"] == [0.0, 1.0] and se["drums"] == [0.5, 0.5] and se["vocals"] == [0.0, 0.0]
    assert se["drum_strong"] == [0.0, 0.5] and se["engine"] == "mix" and se["fps"] == 24
    assert beatfx.mix_stem_env(None)["frames"] == 0


def test_look_pass_roles_macros_and_no_cv2_fallback():
    env = _env()
    lp = beatfx.LookPass(dance_fx="house", stem_orbit=True, stem_env=env, macros={"speed": 1.0, "glow": 1.0, "stems": {"kick": 0.2}},
                         beats=[0.0, 0.5], fps=24, shots=3, end_card=True)
    assert lp.active and lp.gains() == {"kick": 0.2}
    assert [lp.role_for(i) for i in range(3)] == ["intro", "vj", "into_card"]
    lp.start_shot(1, 6, 0.0)
    assert lp.fx.preset == "cool-echo" and lp.fx.p["echo_decay"] == pytest.approx(0.70 - 0.12)
    assert lp.fx.p["halation"] == pytest.approx(min(1.5, D.PRESETS["cool-echo"]["halation"] * 1.6))
    f = _frame()
    outs = [lp.frame(f, k, k / 24) for k in range(6)]
    assert all(o.shape == f.shape and o.dtype == np.uint8 for o in outs) and not np.array_equal(outs[3], f)
    info = lp.info()
    assert info["frames"] == 6 and info["seconds"] >= 0 and info["roles"] == ["1:vj:cool-echo"]
    if O.cv2 is None:
        assert info["stem_orbit"] is False and any("OpenCV" in n for n in info["notes"])
    else:
        assert info["stem_orbit"] is True and lp.plan is not None
    off = beatfx.LookPass(dance_fx="off", stem_orbit=False, stem_env=env, fps=24)
    assert not off.active
    off.start_shot(0, 2, 0.0)
    assert np.array_equal(off.frame(f, 0, 0.0), f)
    preset = beatfx.LookPass(dance_fx="noir-glow", stem_env=env, fps=24, shots=2, end_card=True)
    preset.start_shot(1, 4, 0.0)
    assert preset.fx.preset == "noir-glow" and preset.roles == ["1:into_card:noir-glow"]


def test_look_pass_works_at_a_reduced_size_for_big_frames():
    env = _env()
    big = np.zeros((640, 360, 3), np.uint8)
    big[200:400, 100:260] = 220
    lp = beatfx.LookPass(dance_fx="cool-echo", stem_orbit=False, stem_env=env, fps=24, shots=1)
    lp.start_shot(0, 2, 0.0)
    out = lp.frame(big, 0, 0.0)
    assert out.shape == big.shape and out.dtype == np.uint8
    # structure stays at full resolution: the subject's edge is still sharp at the same place
    col = out.astype(np.float32).mean(2)[:, 180]
    edge = int(np.argmax(np.abs(np.diff(col))))
    assert abs(edge - 199) <= 1 or abs(edge - 399) <= 1


def test_beat_fx_bloom_gain_scales_the_punch_glow():
    frame = np.full((36, 64, 3), 80, np.uint8)
    frame[10:26, 20:44] = 200
    a = beatfx.beat_fx(frame, kick=0, trans=0, punch=1, loud=2 / 3, beat_index=0, bloom=0.6)
    b = beatfx.beat_fx(frame, kick=0, trans=0, punch=1, loud=2 / 3, beat_index=0, bloom=1.6)
    assert b.mean() > a.mean() + 3
    assert np.array_equal(beatfx.beat_fx(frame, kick=0, trans=0, punch=1, loud=2 / 3, beat_index=0),
                          beatfx.beat_fx(frame, kick=0, trans=0, punch=1, loud=2 / 3, beat_index=0, bloom=1.0))


def test_speed_macro_biases_the_auto_morph_count():
    beats = [i * 0.5 for i in range(40)]
    base = dense.auto_morph_count(20.0, beats, "flow")
    assert dense.speed_count(20.0, beats, "flow", 0.5) == base
    assert dense.speed_count(20.0, beats, "flow", 1.0) >= base and dense.speed_count(20.0, beats, "flow", 0.0) <= base
    assert dense.speed_count(20.0, beats, "dense", 1.0) > dense.speed_count(20.0, beats, "dense", 0.0)
    directed = {"duration": 20.0, "beats": beats}
    slow, _ = dense.shots_for({"energy_preset": "dense", "macros": {"speed": 0.0}}, directed, None)
    fast, _ = dense.shots_for({"energy_preset": "dense", "macros": {"speed": 1.0}}, directed, None)
    assert len(fast) > len(slow)
    plain, _ = dense.shots_for({"energy_preset": "dense"}, directed, None)
    neutral, _ = dense.shots_for({"energy_preset": "dense", "macros": {"speed": 0.5}}, directed, None)
    assert len(plain) == len(neutral)


def test_house_look_blocks_wobble_but_plain_macros_keep_it():
    shots = [{"fx_intensity": 1.0}]
    assert dense.apply_macros([dict(s) for s in shots], {"chaos": 1.0})[0]["wobble"] == 0.3
    assert "wobble" not in dense.apply_macros([dict(s) for s in shots], {"chaos": 1.0}, DEMO_HOUSE)[0]


@pytest.mark.skipif(not HAS_FFMPEG, reason="needs ffmpeg")
def test_compose_applies_the_house_look_on_tiny_mock_clips(tmp_path):
    """Two tiny clips through compose with dance_fx on: frames come out, the look info is reported and the
    into_card role lands on the last shot. No audio analysis: a silent wav keeps librosa quick."""
    import soundfile as sf

    sr = 22050
    wav = tmp_path / "a.wav"
    t = np.arange(int(sr * 1.0)) / sr
    sf.write(str(wav), (0.3 * np.sin(2 * np.pi * 110 * t) * (t % 0.5 < 0.05)).astype(np.float32), sr)
    clips = []
    for i, v in enumerate((40, 200)):
        clip = tmp_path / f"c{i}.mp4"
        frame = np.full((36, 64, 3), v, np.uint8)
        frame[10:26, 20:44] = 255 - v
        raw = b"".join(frame.tobytes() for _ in range(12))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "64x36", "-r", "24",
                        "-i", "-", "-pix_fmt", "yuv420p", str(clip)], input=raw, check=True)
        clips.append(clip)
    shots = [{"start": 0.0, "seconds": 0.5, "frames": 12, "effects": []}, {"start": 0.5, "seconds": 0.5, "frames": 12, "effects": []}]
    out = tmp_path / "out.mp4"
    made = beatfx.compose(clips, shots, wav, out, aspect="16:9", quality="draft", fx=True, beats=[0.0, 0.5],
                          size=(64, 36), dance_fx="house", stem_orbit=True, macros={"glow": 0.9, "speed": 0.7},
                          end_card=True)
    assert out.is_file() and made["frames"] == 24 and made["fps"] == 24
    look = made["look"]
    assert look["dance_fx"] == "house" and look["roles"] == ["0:intro:cyan-flash", "1:into_card:negative-rush"]
    assert look["frames"] == 24 and look["stems"] == "mix" and look["macros"]["glow"] == 0.9
    if O.cv2 is None:
        assert look["stem_orbit"] is False and look["notes"]
    plain = beatfx.compose(clips, shots, wav, tmp_path / "plain.mp4", aspect="16:9", fx=False, dance_fx="off", stem_orbit=False)
    assert plain["look"]["dance_fx"] == "off" and plain["look"]["frames"] == 0 and not plain["look"]["stem_orbit"]
