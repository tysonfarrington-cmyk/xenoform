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

DEFAULTS = {"max_yaw": 24.0, "max_pitch": 4.0, "max_roll": 1.5, "bass": 1.0, "drums": 0.7, "other": 0.4,
            "spin": 0.0, "stiffness": 6.0, "focal": 1.6}


def _spring(target: np.ndarray, fps: int, stiffness: float) -> np.ndarray:
    """Critically damped spring follower: smooth position *and* velocity, so nothing ever snaps."""
    w = float(stiffness); dt = 1.0 / fps; x = float(target[0]); v = 0.0; out = np.empty_like(target, dtype=np.float64)
    for i, g in enumerate(target):
        a = w * w * (g - x) - 2.0 * w * v
        v += a * dt; x += v * dt; out[i] = x
    return out


def plan(env: dict, t0: float, n: int, *, fps: int = 24, **kw) -> dict:
    """Per-frame yaw/pitch/roll in degrees for frames t0 .. t0 + (n-1)/fps."""
    p = dict(DEFAULTS, **kw)
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
    roll = np.clip(-0.06 * np.gradient(yaw) * fps, -p["max_roll"], p["max_roll"])
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


def apply(frame: np.ndarray, yaw: float, pitch: float = 0.0, roll: float = 0.0, *, cx: float | None = None,
          focal: float = 1.6, zoom: float | None = None) -> np.ndarray:
    h, w = frame.shape[:2]
    if zoom is None:  # push in just enough that the rotated frame still covers the canvas (no black corners)
        zoom = 1.0 + 0.02 * abs(pitch) + 0.01 * abs(roll)
    H = homography(w, h, yaw, pitch, roll, cx=cx, focal=focal, zoom=zoom)
    if cv2 is None:  # pragma: no cover
        raise RuntimeError("stem_orbit.apply needs OpenCV")
    return cv2.warpPerspective(frame, H, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)  # black: never mirror a second subject in


def render_shot(frames, env: dict, t0: float, *, fps: int = 24, cx: float | None = None, **kw):
    frames = list(frames); pl = plan(env, t0, len(frames), fps=fps, **kw)
    for i, f in enumerate(frames):
        yield apply(f, pl["yaw"][i], pl["pitch"][i], pl["roll"][i], cx=cx, focal=kw.get("focal", DEFAULTS["focal"]))
