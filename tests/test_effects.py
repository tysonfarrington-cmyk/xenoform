"""TouchDesigner-style effects (xenoform.effects, 28 Oct): the blue-noise dither (a Look and a beat effect), feedback,
kaleido and slit-scan, run after the look in the compose and set by a re-cut; the blocky smear made opt-in."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from test_timeline import _cut, _rec
from xenoform import beatfx, boundary_fx as B, dense, effects as E, simple_recipe

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
DEMO = ROOT / "examples" / "demo.wav"
TONES = np.asarray(E.DEFAULT_TONES, np.float32)


def test_the_blue_noise_is_a_threshold_map_with_no_low_frequencies():
    bn = E.blue_noise()
    assert bn.shape == (64, 64) and 0 < float(bn.min()) and float(bn.max()) < 1
    assert len(np.unique(bn)) == 64 * 64  # every threshold once: a flat grey dithers to exactly its share of dots
    spec = np.abs(np.fft.fft2(bn - bn.mean()))
    low = spec[:4, :4].sum() + spec[-3:, :4].sum() + spec[:4, -3:].sum() + spec[-3:, -3:].sum()
    assert low / spec.sum() < 0.01  # blue: the energy sits in the high frequencies, so no clumps and no grid
    white = np.random.default_rng(0).random((64, 64))
    wspec = np.abs(np.fft.fft2(white - white.mean()))
    wlow = wspec[:4, :4].sum() + wspec[-3:, :4].sum() + wspec[:4, -3:].sum() + wspec[-3:, -3:].sum()
    assert low / spec.sum() < 0.2 * (wlow / wspec.sum())
    assert np.array_equal(E.blue_noise(), bn)  # cached and deterministic


def test_the_dither_maps_light_onto_the_tones_in_dots():
    ramp = np.repeat(np.repeat(np.linspace(0, 255, 256, dtype=np.float32)[None, :, None], 128, axis=0), 3, axis=2).astype(np.uint8)
    out = E.dither(ramp, TONES, contrast=1.0)
    colours = {tuple(int(v) for v in px) for px in out.reshape(-1, 3)}
    assert colours <= {tuple(int(v) for v in t) for t in TONES}  # only the palette's tones
    idx = np.argmin(np.abs(out[..., 1:2].astype(np.int32) - TONES[None, None, :, 1].astype(np.int32)), axis=2)
    cols = idx.mean(axis=0) / (len(TONES) - 1)
    assert abs(float(cols[10]) - 10 / 255) < 0.08 and abs(float(cols[128]) - 0.5) < 0.08 and float(cols[-1]) > 0.97  # light kept
    big = E.dither(ramp, TONES, dot=2, contrast=1.0)
    assert (big[0::2, 0::2] == big[1::2, 0::2]).all()  # a dot of 2 is 2 x 2 pixels
    assert not np.array_equal(E.dither(ramp, TONES, shift=(5, 9), contrast=1.0), out)  # a new grain
    assert E.dither(ramp, TONES, amount=0.0) is ramp
    assert E.dot_for((540, 960)) == 2 and E.dot_for((1080, 1920)) == 4
    assert E.shift_for(0.6, [0.0, 0.5, 1.0]) == E.shift_for(0.9, [0.0, 0.5, 1.0]) != E.shift_for(1.1, [0.0, 0.5, 1.0])


def test_the_tones_come_from_the_vibes_still(tmp_path):
    from PIL import Image

    img = np.zeros((64, 64, 3), np.uint8)
    img[:, 16:32] = (40, 10, 90)
    img[:, 32:48] = (20, 160, 200)
    img[:, 48:] = (250, 200, 230)
    Image.fromarray(img).save(tmp_path / "still.png")
    tones = E.palette_from_image(tmp_path / "still.png")
    lum = tones @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    assert len(tones) == 4 and np.all(np.diff(lum) > 0) and tones[0].max() < 20 and lum[-1] > 180
    assert np.array_equal(E.palette_from_image(None), TONES) and np.array_equal(E.palette_from_image(tmp_path / "none.png"), TONES)


def test_kaleido_feedback_and_slitscan():
    rng = np.random.default_rng(1)
    frame = (rng.random((96, 64, 3)) * 255).astype(np.uint8)
    k = E.kaleido(frame, amount=1.0, segments=6, angle=0.0)
    assert k.shape == frame.shape and float((k != k[::-1]).any(axis=2).mean()) < 0.05  # folded: mirrored about the middle
    assert E.kaleido(frame, amount=0.0) is frame
    fb = E.Feedback()
    dot = np.zeros((96, 64, 3), np.uint8)
    dot[44:52, 28:36] = 255
    assert fb(dot, amount=0.8, loud=0.5, t=0.0) is dot  # the first frame passes
    after = fb(np.zeros_like(dot), amount=0.8, loud=0.5, t=0.04)
    assert after[40:56, 24:40].max() > 100  # the dot leaves its trail on a black frame
    s = E.SlitScan(depth=8)
    for v in range(8):
        got = s(np.full((32, 8, 3), v * 20, np.uint8), amount=1.0, loud=1.0)
    assert int(got[0, 0, 0]) == 140 and int(got[-1, 0, 0]) < 140  # the top row is now, the bottom row further back


def test_the_chain_and_the_plan():
    assert E.plan([], {}) is None and E.plan(["nonsense"], {}) is None
    cfg = E.plan(["kaleido", "dither", "smear"], {"intensity": 1.0, "chaos": 0.8}, None, (540, 960))
    assert cfg["names"] == ["dither", "kaleido"] and cfg["amount"] == 1.0 and cfg["segments"] == 8 and cfg["dot"] == 2
    assert len(cfg["tones"]) == 4
    assert E.names_of({"effects": ["slitscan", "smear", "x"]}) == ["slitscan", "smear"] and E.names_of({"effects": "feedback, kaleido"}) == ["feedback", "kaleido"]
    assert E.smear_setting({}) == "off" and E.smear_setting({"effects": ["smear"]}) == "sparing"
    assert E.smear_setting({"effects": ["smear"], "boundary_smear": "on"}) == "on"
    chain = E.Chain(cfg, [0.0, 0.5, 1.0])
    frame = np.full((96, 64, 3), 128, np.uint8)
    quiet = chain(frame.copy(), 0.2, kick=0.0, loud=0.0)
    hit = chain(frame.copy(), 0.5, kick=1.0, loud=1.0)
    hit_colours = {tuple(int(v) for v in px) for px in hit.reshape(-1, 3)}
    assert hit_colours <= {tuple(int(v) for v in t) for t in np.asarray(cfg["tones"])}  # dithered on the kick
    assert len({tuple(int(v) for v in px) for px in quiet.reshape(-1, 3)}) <= 2  # no kick, no dither: still flat grey
    assert E.Chain(cfg, [], look_mode="dither").names == ["kaleido"]  # the Dither look already dithers


def test_the_dither_look_and_its_name():
    look = beatfx.LookPass(dance_fx="dither", stem_orbit=False, beats=[0.0, 0.5], fps=24)
    look.start_shot(0, 4, 0.0)
    frame = (np.random.default_rng(2).random((96, 64, 3)) * 255).astype(np.uint8)
    out = look.frame(frame, 0, 0.1)
    assert {tuple(int(v) for v in px) for px in out.reshape(-1, 3)} <= {tuple(int(v) for v in t) for t in TONES}
    assert look.active and look.info()["roles"] == ["0:intro:dither"]
    assert beatfx.resolve_dance_preset("dither") == "dither" and dense.options({"dance_fx": "dither"})["dance_fx"] == "dither"
    with pytest.raises(ValueError):
        beatfx.resolve_dance_preset("nonsense")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg makes the clips")
def test_the_compose_runs_the_effects_after_the_look(tmp_path):
    clips = []
    for i, colour in enumerate(("red", "blue")):
        p = tmp_path / f"c{i}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x112:rate=24:duration=1",
                        "-vf", f"drawbox=x=8:y=8:w=20:h=20:color={colour}:t=fill", "-pix_fmt", "yuv420p", str(p)], check=True)
        clips.append(p)
    shots = [{"start": 0.0, "end": 1.0, "frames": 24, "effects": []}, {"start": 1.0, "end": 2.0, "frames": 24, "effects": []}]
    made = beatfx.compose(clips, shots, DEMO, tmp_path / "out.mp4", aspect="9:16", size=(64, 112), fx=False, dance_fx="off",
                          stem_orbit=False, beats=[0.0, 0.5, 1.0, 1.5], effects=["kaleido", "feedback", "slitscan", "dither"],
                          macros={"intensity": 0.8})
    assert made["frames"] == 48 and made["effects"] == ["dither", "feedback", "kaleido", "slitscan"] and (tmp_path / "out.mp4").stat().st_size > 0


def test_the_smear_and_the_datamosh_are_opt_in(tmp_path, monkeypatch):
    shots = [{"start": float(i), "end": float(i + 1), "frames": 24, **({"boundary": "drop"} if i == 2 else {})} for i in range(4)]
    plain = dense.boundary_transitions(shots, "odd-machine")  # this vibe's drop pick is a datamosh
    assert plain[2]["kind"] == "chroma-split"
    assert dense.boundary_transitions(shots, "odd-machine", smear="sparing")[2]["kind"] == "datamosh"
    seen = {}
    job = _cut(tmp_path, monkeypatch, seen)
    out = dense.recut_from_cache(job, {"effects": ["feedback", "smear"], "macros": {"chaos": 1.0}})
    assert seen["kw"]["effects"] == ["feedback", "smear"] and out["effects"] == ["feedback", "smear"] and out["smear"] == "sparing"
    dense.recut_from_cache(job, {"effects": [], "macros": {"chaos": 1.0}})
    assert not any(e and e.get("kind") == "smear" for e in seen["kw"]["boundary_fx"] or []) and _rec(job)["smear"] == "off"


def test_the_recipe_carries_the_effects():
    code = simple_recipe.encode({"vibe": "cosmic", "effects": ["kaleido", "dither"]})
    assert simple_recipe.decode(code)["effects"] == ["dither", "kaleido"]
    assert "effects" not in simple_recipe.decode(simple_recipe.encode({"vibe": "cosmic"}))


def test_the_desk_has_the_effects_row_and_the_dither_look():
    assert 'const EFFECTS = ["dither", "feedback", "kaleido", "slitscan", "smear"];' in APP and list(E.NAMES) + ["smear"] == ["dither", "feedback", "kaleido", "slitscan", "smear"]
    notes = APP.split("const EFFECT_NOTES = {", 1)[1].split("};", 1)[0]
    for key, text in E.NOTES.items():
        assert f'"{key}": {json.dumps(text)}' in notes, key
    assert '"dither"' in APP.split("const LOOK_PRESETS = [", 1)[1].split("];", 1)[0]
    assert f'"dither": {json.dumps(E.LOOK_NOTES["dither"])}' in APP
    desk = APP.split("simple-knobs-panel", 1)[1].split("</section>", 1)[0]
    assert '${effectsRow(easy.effects, "easy-effect")}' in desk
    result = APP.split('if (easy.phase === "result" || easy.phase === "showcase") {', 1)[1].split("const preview = easy.vibe", 1)[0]
    assert '${effectsRow(easy.effects, "easy-effect")}' in result
    assert "effects: (state.easy && state.easy.effects) || []," in APP
    assert "effects: state.easy.effects || []," in APP.split("async function recutWithKnobs()", 1)[1].split("try {", 1)[0]
    assert '"effects"' in APP.split("const EASY_SAVED_KEYS = [", 1)[1].split("];", 1)[0] and 'act === "easy-effect"' in APP
    assert "the blocky smear too, sparingly, when Effects asks for it" in APP
