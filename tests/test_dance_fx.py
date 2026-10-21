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
