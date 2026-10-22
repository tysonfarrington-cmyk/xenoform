"""Stem-driven orbit / turntable for a subject shot.

The camera swings around the subject (yaw, with a little pitch and roll) as a rigid perspective
rotation of the whole frame about a vertical axis through the subject, so the subject's shape never
bends: no warp, no mesh, no per-pixel displacement. The swing is driven by the stems:

    bass   -> slow, wide yaw push (the "turn")
    drums  -> short eased kicks on strong hits (never a snap: every change goes through a
              critically damped spring)
    other  -> a gentle pitch drift

``plan()`` returns the per-frame angles; ``apply()`` renders one frame; ``render_shot()`` does both.
"""
from __future__ import annotations

import math
import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

POST_EFFECTS = {"stem-orbit": "camera orbits the subject: yaw/turntable driven by bass and drums, spring-eased, rigid (no warp)"}

try:
    from xenoform.demo_house import DEMO_HOUSE as _DEMO_HOUSE
except ImportError:  # loose checkout
    from demo_house import DEMO_HOUSE as _DEMO_HOUSE

# The house profile is the single source of these numbers (demo_house.DEMO_HOUSE["stem_orbit"]).
DEFAULTS = dict(_DEMO_HOUSE["stem_orbit"])


def _spring(target: np.ndarray, fps: int, stiffness: float) -> np.ndarray:
    """Critically damped spring follower: smooth position *and* velocity, so nothing ever snaps."""
    w = float(stiffness); dt = 1.0 / fps; x = float(target[0]); v = 0.0; out = np.empty_like(target, dtype=np.float64)
    for i, g in enumerate(target):
        a = w * w * (g - x) - 2.0 * w * v
        v += a * dt; x += v * dt; out[i] = x
    return out


def house_fps(fps: int | None = None) -> int:
    """``fps`` when given, else the house format fps (demo_house: 24)."""
    if fps is not None:
        return int(fps)
    try:
        from xenoform.config import house
    except ImportError:  # pragma: no cover - loose checkout
        return 24
    return int((house("format") or {}).get("fps") or 24)


def params(**kw) -> dict:
    """DEFAULTS (the house stem_orbit block) with the given overrides; a None value falls back to the house."""
    return dict(DEFAULTS, **{k: v for k, v in kw.items() if v is not None})


def plan(env: dict, t0: float, n: int, *, fps: int | None = None, **kw) -> dict:
    """Per-frame yaw/pitch/roll in degrees for frames t0 .. t0 + (n-1)/fps.
    ``fps`` None and any None keyword fall back to the house profile (config.house)."""
    fps = house_fps(fps)
    p = params(**kw)
    n = int(max(0, n))
    if n == 0:
        z = np.zeros(0, dtype=np.float64)
        return {"yaw": z, "pitch": z.copy(), "roll": z.copy()}
    try:
        from xenoform.stem_react import at
    except ImportError:  # loose checkout
        from stem_react import at
    ts = t0 + np.arange(n) / fps
    ba = np.array([at(env, t, "bass") for t in ts]); dr = np.array([at(env, t, "drums") for t in ts]); ot = np.array([at(env, t, "other") for t in ts])
    hits = np.zeros(n)
    for h in env.get("drum_strong") or []:
        i = int(round((h - t0) * fps))
        if 0 <= i < n: hits[i] = 1.0
    kick = np.zeros(n); s = 1.0
    for i in range(n):  # alternate the kick direction so the orbit swings both ways
        if hits[i]:
            s = -s; kick[i:] = kick[i:] * 0.0 + s
    # bass slowly pushes the turn around; drums add an eased swing; 'spin' adds a constant turntable rate
    turn = np.cumsum(ba - ba.mean()) / fps
    turn = turn / (np.abs(turn).max() + 1e-6)
    tgt_yaw = p["max_yaw"] * np.clip(p["bass"] * 0.65 * turn + p["drums"] * 0.35 * kick * (0.4 + 0.6 * dr), -1, 1) + p["spin"] * np.arange(n) / fps
    tgt_pitch = p["max_pitch"] * np.clip(p["other"] * (ot - ot.mean()) * 4, -1, 1)
    yaw = _spring(tgt_yaw, fps, p["stiffness"]); pitch = _spring(tgt_pitch, fps, p["stiffness"] * 0.7)
    roll = np.clip(-0.06 * np.gradient(yaw) * fps, -p["max_roll"], p["max_roll"]) if n > 1 else np.zeros(n)
    return {"yaw": yaw, "pitch": pitch, "roll": roll}


def homography(w: int, h: int, yaw: float, pitch: float = 0.0, roll: float = 0.0, *, cx: float | None = None,
               focal: float = 1.6, zoom: float = 1.0) -> np.ndarray:
    """3x3 homography for a rigid rotation of the image plane about the subject's vertical axis."""
    cx = w / 2 if cx is None else cx; cy = h / 2; f = focal * max(w, h)
    a, b, c = (math.radians(v) for v in (yaw, pitch, roll))
    Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    R = Rz @ Rx @ Ry
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    S = np.diag([zoom, zoom, 1.0]); T = np.array([[1, 0, cx * (1 - zoom)], [0, 1, cy * (1 - zoom)], [0, 0, 1.0]])
    # rotate the image plane about its own axis through the subject (not a camera pan): X' = R(X - c) + c on the plane z = 1
    e3 = np.array([[0.0], [0.0], [1.0]])
    P = R + (np.eye(3) - R) @ e3 @ e3.T
    return T @ S @ K @ P @ np.linalg.inv(K)


def canvas_overshoot(w: int, h: int, H: np.ndarray) -> float:
    """How far the canvas corners land outside the source once pulled back through ``H`` (warpPerspective
    samples src at H^-1 * canvas). 0 means every canvas pixel maps inside the source; >0 is the largest
    overshoot in pixels (black would show there)."""
    Hi = np.linalg.inv(H)
    worst = 0.0
    for px, py in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
        q = Hi @ np.array([px, py, 1.0])
        if abs(q[2]) < 1e-9 or q[2] < 0:
            return float("inf")
        x, y = q[0] / q[2], q[1] / q[2]
        worst = max(worst, -x, x - w, -y, y - h)
    return float(worst)


def auto_zoom(w: int, h: int, yaw: float, pitch: float = 0.0, roll: float = 0.0, *, cx: float | None = None,
              focal: float = 1.6, margin: float = 1.01, zoom_max: float = 3.0) -> float:
    """Smallest push-in (times ``margin``) at which the rotated frame still covers the whole canvas, so no
    black wedge appears at any yaw/pitch/roll. Found by bisection on the inverse-mapped canvas corners."""
    if canvas_overshoot(w, h, homography(w, h, yaw, pitch, roll, cx=cx, focal=focal, zoom=1.0)) <= 0.0:
        return 1.0
    lo, hi = 1.0, float(zoom_max)
    if canvas_overshoot(w, h, homography(w, h, yaw, pitch, roll, cx=cx, focal=focal, zoom=hi)) > 0.0:
        return hi
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if canvas_overshoot(w, h, homography(w, h, yaw, pitch, roll, cx=cx, focal=focal, zoom=mid)) <= 0.0:
            hi = mid
        else:
            lo = mid
    return min(float(zoom_max), hi * margin)


def apply(frame: np.ndarray, yaw: float, pitch: float = 0.0, roll: float = 0.0, *, cx: float | None = None,
          focal: float | None = None, zoom: float | None = None) -> np.ndarray:
    """One frame at the given angles. ``focal`` None falls back to the house focal (DEFAULTS["focal"])."""
    if focal is None:
        focal = float(DEFAULTS["focal"])
    h, w = frame.shape[:2]
    if zoom is None:  # push in just enough that the rotated frame still covers the canvas (no black corners)
        zoom = auto_zoom(w, h, yaw, pitch, roll, cx=cx, focal=focal)
    H = homography(w, h, yaw, pitch, roll, cx=cx, focal=focal, zoom=zoom)
    if cv2 is None:  # pragma: no cover
        raise RuntimeError("stem_orbit.apply needs OpenCV")
    return cv2.warpPerspective(frame, H, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)  # black: never mirror a second subject in


def render_shot(frames, env: dict, t0: float, *, fps: int | None = None, cx: float | None = None, **kw):
    """Plan and render one shot. ``fps`` / ``focal`` / any None keyword fall back to the house profile."""
    fps = house_fps(fps)
    frames = list(frames); pl = plan(env, t0, len(frames), fps=fps, **kw)
    focal = params(**kw)["focal"]
    for i, f in enumerate(frames):
        yield apply(f, pl["yaw"][i], pl["pitch"][i], pl["roll"][i], cx=cx, focal=focal)
