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
