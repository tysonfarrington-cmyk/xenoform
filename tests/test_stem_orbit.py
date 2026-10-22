import numpy as np
import pytest
from xenoform import stem_orbit as O

FPS = 24


def _env(n=240, seed=0):
    rng = np.random.default_rng(seed); t = np.arange(n) / FPS
    bass = 0.5 + 0.5 * np.sin(2 * np.pi * t / 3); dr = (np.sin(2 * np.pi * t * 2.5) > 0.9).astype(float)
    return {"fps": FPS, "bass": bass.tolist(), "drums": dr.tolist(), "other": (0.5 + 0.2 * rng.random(n)).tolist(),
            "vocals": [0.0] * n, "drum_strong": [i / FPS for i in range(0, n, 19)]}


def test_plan_is_bounded_smooth_and_deterministic():
    env = _env(); a = O.plan(env, 0.0, 200); b = O.plan(env, 0.0, 200)
    assert np.array_equal(a["yaw"], b["yaw"])
    assert np.abs(a["yaw"]).max() <= O.DEFAULTS["max_yaw"] * 1.05
    assert np.abs(a["yaw"]).max() > 5  # it really turns
    step = np.abs(np.diff(a["yaw"])); acc = np.abs(np.diff(a["yaw"], 2))
    assert step.max() < 2.5 and acc.max() < 0.6  # eased: no snapping


def test_audio_drives_the_turn():
    env = _env(); flat = dict(env, bass=[0.5] * 240, drums=[0.0] * 240, drum_strong=[])
    assert np.abs(O.plan(flat, 0.0, 200)["yaw"]).max() < 0.5
    assert np.abs(O.plan(env, 0.0, 200)["yaw"]).max() > 5


def test_zero_angles_is_identity_and_rotation_is_rigid():
    cv2 = pytest.importorskip("cv2")
    H = O.homography(100, 200, 0.0, zoom=1.0); assert np.allclose(H / H[2, 2], np.eye(3), atol=1e-9)
    f = np.zeros((200, 100, 3), np.uint8); cv2.rectangle(f, (30, 60), (70, 140), (255, 255, 255), -1)
    out = O.apply(f, 15.0, zoom=1.0)
    # straight lines stay straight (homography): the warped square's rows remain single solid runs
    m = out[..., 0] > 128; rows = [np.nonzero(r)[0] for r in m if r.any()]
    assert all(r[-1] - r[0] + 1 == len(r) for r in rows)
    assert out.shape == f.shape


def test_render_shot_length_and_spin():
    pytest.importorskip("cv2")  # rendering needs OpenCV; planning does not
    env = _env(); frames = [np.full((64, 36, 3), 100, np.uint8)] * 30
    assert len(list(O.render_shot(frames, env, 0.0))) == 30
    sp = O.plan(env, 0.0, 48, spin=10.0)["yaw"]; assert sp[-1] > O.plan(env, 0.0, 48)["yaw"][-1]


def test_rotation_pivots_on_subject_axis():
    """Turning must not slide the subject sideways: the pivot column maps to itself."""
    for yaw in (-28, -10, 12, 28):
        H = O.homography(1080, 1920, yaw, cx=540)
        for y in (200, 960, 1700):
            p = H @ np.array([540.0, y, 1.0]); p = p[:2] / p[2]
            assert abs(p[0] - 540) < 1.0 and abs(p[1] - y) < 1.0


def test_defaults_match_the_house_profile():
    from xenoform.demo_house import DEMO_HOUSE
    house = DEMO_HOUSE["stem_orbit"]
    for k in set(house) & set(O.DEFAULTS):
        assert O.DEFAULTS[k] == house[k], k
    assert O.DEFAULTS["max_yaw"] == 28.0


def test_auto_zoom_covers_the_canvas_at_every_house_yaw():
    """No black wedge: with the automatic zoom every canvas corner pulls back to a point inside the source
    (numpy only; warpPerspective samples src at H^-1 * canvas)."""
    w, h = 1080, 1920
    my = O.DEFAULTS["max_yaw"]
    for yaw in np.linspace(-my, my, 15):
        for pitch, roll in ((0.0, 0.0), (O.DEFAULTS["max_pitch"], O.DEFAULTS["max_roll"]), (-4.0, -1.5)):
            z1 = O.canvas_overshoot(w, h, O.homography(w, h, yaw, pitch, roll, zoom=1.0))
            z = O.auto_zoom(w, h, yaw, pitch, roll)
            assert O.canvas_overshoot(w, h, O.homography(w, h, yaw, pitch, roll, zoom=z)) <= 0.0, (yaw, pitch, roll, z)
            if abs(yaw) > 1.0:
                assert z1 > 0.0 and 1.0 < z < 2.0, (yaw, z1, z)  # the old fixed formula (1.0 + 0.02*|pitch|) left a wedge
    assert O.auto_zoom(w, h, 0.0, 0.0, 0.0) == 1.0


def test_plan_handles_zero_and_one_frame():
    env = _env()
    z = O.plan(env, 0.0, 0)
    assert all(len(z[k]) == 0 for k in ("yaw", "pitch", "roll"))
    one = O.plan(env, 0.0, 1)
    assert all(len(one[k]) == 1 and np.isfinite(one[k]).all() for k in ("yaw", "pitch", "roll"))
    assert one["roll"][0] == 0.0
