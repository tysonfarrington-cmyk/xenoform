import numpy as np, pytest
from xenoform import dance_fx as D


def _frame(h=192, w=108):
    f = np.full((h, w, 3), 40, np.uint8)
    f[60:150, 40:70] = 230  # a bright "dancer"
    return f


@pytest.mark.parametrize("preset", list(D.PRESETS))
def test_shape_and_dtype(preset):
    fx = D.DanceFX(preset)
    out = fx.apply(_frame(), {"drums": 1, "bass": 1, "other": 1, "vocals": 1, "beat": 1})
    assert out.shape == (192, 108, 3) and out.dtype == np.uint8


@pytest.mark.parametrize("preset", list(D.PRESETS))
def test_no_geometry_change(preset):
    """The subject's silhouette must not move: no warp, scale or channel offset."""
    f = _frame(); fx = D.DanceFX(preset)
    for _ in range(4):
        out = fx.apply(f, {"drums": 1, "bass": 1, "other": 1, "vocals": 1, "beat": 1})
    for c in range(3):  # every channel keeps the same brightest region
        col = out[..., c].astype(float)
        if D.PRESETS[preset].get("invert"):  # a negative flips luma: the subject becomes the darkest region, in place
            ys, xs = np.nonzero(col <= np.percentile(col, 1))
        else:
            ys, xs = np.nonzero(col >= np.percentile(col, 99))
        assert 60 <= ys.mean() < 150 and 40 <= xs.mean() < 70


def test_quiet_is_gentle():
    f = _frame(); out = D.DanceFX("warm-leak").apply(f, {})
    assert np.abs(out.astype(int) - f).mean() < 25


def test_stems_drive_amount():
    f = _frame()
    lo = D.DanceFX("cool-echo").apply(f, {"drums": 0}); hi = D.DanceFX("cool-echo").apply(f, {"drums": 1})
    assert np.abs(hi.astype(int) - f).mean() > np.abs(lo.astype(int) - f).mean()


def test_glass_static_no_flicker():
    f = _frame(); fx = D.DanceFX("cool-echo", seed=3)
    a = fx.apply(f, {}); fx._acc = None; b = fx.apply(f, {})
    assert np.array_equal(a, b)


def test_render_shot_fades_and_env():
    env = {"fps": 24, "drums": [1.0] * 10, "bass": [0.5] * 10, "other": [0.2] * 10, "vocals": [0.0] * 10, "drum_strong": [0.0]}
    out = list(D.render_shot([_frame()] * 10, env, 0.0, "noir-glow", fade_in=3, fade_out=3))
    assert len(out) == 10 and out[0].mean() < out[5].mean() and out[-1].mean() < out[5].mean()


def test_bloom_rush_wash_and_bleed_are_colour_only():
    import numpy as np
    from xenoform import dance_fx as D
    assert "bloom-rush" in D.PRESETS and {"wash", "bleed"} <= set(D.PASSES)
    assert "dance-wash" in D.POST_EFFECTS and "dance-bleed" in D.POST_EFFECTS
    rng = np.random.default_rng(1); f = np.zeros((96, 64, 3), np.uint8); f[30:60, 20:40] = (230, 40, 60)
    f = (f + rng.integers(0, 8, f.shape)).astype(np.uint8)
    fx = D.DanceFX("bloom-rush", intensity=1.5)
    out = fx.apply(f, {"drums": 1, "bass": 1, "other": 1, "vocals": 1, "beat": 1})
    assert out.shape == f.shape and out.dtype == np.uint8
    assert not np.array_equal(out, f)
    # structure stays put: the luma edge of the block is still at the same place
    lum = out.astype(np.float32).mean(2); col = lum[:, 30]
    assert abs(int(np.argmax(np.abs(np.diff(col)))) - 29) <= 2 or abs(int(np.argmax(np.abs(np.diff(col)))) - 59) <= 2


def test_bloom_rush_is_deterministic_and_old_presets_unchanged():
    import numpy as np
    from xenoform import dance_fx as D
    f = (np.random.default_rng(3).random((48, 32, 3)) * 255).astype(np.uint8)
    d = {"drums": 0.5, "bass": 0.7, "other": 0.2, "vocals": 0.4, "beat": 0.6}
    a = D.DanceFX("bloom-rush", seed=2).apply(f, d); b = D.DanceFX("bloom-rush", seed=2).apply(f, d)
    assert np.array_equal(a, b)
    for name in ("warm-leak", "cool-echo", "noir-glow"):
        assert "wash" not in D.PRESETS[name] and "bleed" not in D.PRESETS[name]


def test_negative_rush_inverts_luma_and_eases():
    import numpy as np
    from xenoform import dance_fx as D
    assert "negative-rush" in D.PRESETS and "invert" in D.PASSES and "dance-invert" in D.POST_EFFECTS
    f = np.full((32, 24, 3), 40, np.uint8); f[:, 12:] = 220
    fx = D.DanceFX("negative-rush", intensity=1.0); d = {"drums": 0, "bass": 1, "other": 0, "vocals": 0, "beat": 1}
    outs = [fx.apply(f, d).astype(float).mean(2) for _ in range(12)]
    # eased: the flip grows over frames rather than snapping in one
    c = [o[:, :12].mean() - o[:, 12:].mean() for o in outs]
    assert c[0] < c[-1]
    assert c[-1] > 0  # dark side is now brighter than the bright side: negative
