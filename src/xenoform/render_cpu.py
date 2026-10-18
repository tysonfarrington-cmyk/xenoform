"""CPU raymarch of a chrome-flesh metaball organism.

Bass swells the body, highs brighten the surface, onsets throw tendrils, and a
drop lerps the blob layout into a second, more erratic arrangement. Shading is
a fresnel mix of wet flesh and a fake studio chrome, so the beauty pass stands
on its own before any LTX restyle.
"""

from __future__ import annotations

import math

import numpy as np

# xyz + radius. Both layouts share a count so a drop can morph rather than pop.
_BASE = np.array(
    [
        [0.00, 0.02, 0.00, 0.50],
        [0.40, 0.20, 0.06, 0.28],
        [-0.36, 0.14, 0.16, 0.26],
        [0.06, -0.34, -0.04, 0.27],
        [0.16, 0.40, -0.20, 0.18],
        [-0.14, -0.12, 0.34, 0.16],
    ],
    dtype=np.float32,
)
_ALT = np.array(
    [
        [0.02, -0.02, 0.02, 0.36],
        [0.52, 0.02, -0.08, 0.20],
        [-0.48, 0.08, 0.02, 0.20],
        [0.02, 0.46, 0.12, 0.22],
        [0.22, -0.08, 0.42, 0.15],
        [-0.18, -0.40, -0.16, 0.18],
    ],
    dtype=np.float32,
)
_TENDRIL_DIRS = np.array(
    [
        [0.15, 0.95, 0.10],
        [0.85, 0.25, 0.20],
        [-0.80, 0.30, 0.15],
        [0.20, -0.75, 0.35],
        [-0.25, -0.20, 0.90],
        [0.55, 0.55, -0.55],
    ],
    dtype=np.float32,
)
_TENDRIL_DIRS /= np.linalg.norm(_TENDRIL_DIRS, axis=1, keepdims=True)


def _rot_y(points: np.ndarray, angle: float) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    x = points[:, 0] * c + points[:, 2] * s
    z = -points[:, 0] * s + points[:, 2] * c
    out = points.copy()
    out[:, 0] = x
    out[:, 2] = z
    return out


def form_from_frame(frame: dict) -> dict:
    """Turn one feature row into SDF parameters."""
    bass = float(frame["bass"])
    sub = float(frame["sub"])
    mid = float(frame["mid"])
    high = float(frame["high"])
    onset = float(frame["onset_env"])
    mutate = float(frame["mutate"])
    t = float(frame["t"])
    scale = 0.82 + 0.62 * bass + 0.22 * sub
    spin = t * (0.45 + 1.6 * mid) + onset * 0.35
    # Optional director sliders. Absent keys leave the beauty pass unchanged.
    if "chaos" in frame:
        chaos = float(frame["chaos"])
        mutate = float(min(1.0, mutate * (0.4 + 1.2 * chaos)))
        onset = float(min(1.5, onset * (0.55 + 0.9 * chaos)))
    noise_amp = 0.015 + 0.07 * high + 0.10 * onset + 0.08 * mutate
    noise_freq = 3.2 + 5.5 * high + 2.0 * mutate
    if "liquidity" in frame:
        noise_amp *= 0.4 + 1.2 * float(frame["liquidity"])
    if "surface" in frame:
        noise_amp *= 0.4 + 1.2 * float(frame["surface"])
    tendril = (0.06 + 0.95 * onset + 0.40 * mutate) * scale
    spec = 0.35 + 0.85 * high + 0.25 * float(frame["beat_env"])
    hue = 0.52 + 0.45 * mutate
    if "material" in frame:
        material = float(frame["material"])
        spec *= 0.4 + 1.2 * material
        hue += (material - 0.5) * 0.25
    if "camera_energy" in frame:
        spin *= 0.4 + 1.2 * float(frame["camera_energy"])
    mix = np.clip(mutate, 0.0, 1.0)
    balls = _BASE * (1.0 - mix) + _ALT * mix
    balls = balls.copy()
    balls[:, :3] = _rot_y(balls[:, :3], spin)
    wobble = (0.03 + 0.05 * bass) * math.sin(t * 5.0 + mutate)
    balls[:, 1] += wobble
    balls[:, :3] *= scale
    balls[:, 3] *= scale
    dirs = _rot_y(_TENDRIL_DIRS, spin * 1.35 + onset)
    origin = balls[0, :3]
    radius = np.float32(0.045 * scale / (1.0 + tendril))
    tendrils = np.zeros((len(dirs), 7), dtype=np.float32)
    tendrils[:, 0:3] = origin + dirs * (balls[0, 3] * 0.55)
    tendrils[:, 3:6] = origin + dirs * (balls[0, 3] * 0.55 + tendril)
    tendrils[:, 6] = radius
    bound = float(np.max(np.linalg.norm(balls[:, :3], axis=1) + balls[:, 3]) + tendril + 0.15)
    result = {
        "balls": balls,
        "tendrils": tendrils,
        "noise_amp": np.float32(noise_amp),
        "noise_freq": np.float32(noise_freq),
        "phase": np.float32(t * (2.0 + 4.0 * high) + onset),
        "bound": bound,
        "scale": scale,
        "spin": spin,
        "spec": np.float32(spec),
        "hue": np.float32(hue),
        "mutate": np.float32(mutate),
        "high": np.float32(high),
        "t": t,
    }
    if "camera_energy" in frame or "camera_push" in frame:
        result["camera_energy"] = float(frame.get("camera_energy", 0.5))
        result["camera_push"] = float(frame.get("camera_push", 0.5))
    if frame.get("palette"):
        result["palette"] = str(frame["palette"])
    if frame.get("lens"):
        result["lens"] = str(frame["lens"])
    if frame.get("shot"):
        result["shot"] = str(frame["shot"])
    if frame.get("move"):
        result["move"] = str(frame["move"])
    if frame.get("exposure") not in (None, ""):
        result["exposure"] = float(frame["exposure"])
    return result


def camera_distance(form: dict) -> float:
    """Studio distance. Director fields pull the camera; otherwise this stays 2.45."""
    if "camera_energy" not in form and "camera_push" not in form:
        return 2.45
    energy = float(form.get("camera_energy", 0.5))
    push = float(form.get("camera_push", 0.5))
    dist = 2.45 - (energy - 0.5) * 0.7 - (push - 0.5) * 0.55
    return float(max(1.55, min(3.4, dist)))


def _smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def _capsule(points: np.ndarray, a: np.ndarray, b: np.ndarray, radius: float) -> np.ndarray:
    pa = points - a
    ba = b - a
    denom = float(np.dot(ba, ba)) + 1e-8
    h = np.clip((pa @ ba) / denom, 0.0, 1.0)
    return np.linalg.norm(pa - ba * h[:, None], axis=1) - radius


def sdf(points: np.ndarray, form: dict) -> np.ndarray:
    d = np.full(points.shape[0], 1e5, dtype=np.float32)
    balls = form["balls"]
    for i in range(balls.shape[0]):
        di = np.linalg.norm(points - balls[i, :3], axis=1) - balls[i, 3]
        d = _smin(d, di, 0.42)
    tendrils = form["tendrils"]
    for i in range(tendrils.shape[0]):
        di = _capsule(points, tendrils[i, 0:3], tendrils[i, 3:6], float(tendrils[i, 6]))
        d = _smin(d, di.astype(np.float32), 0.2)
    amp = float(form["noise_amp"])
    if amp > 1e-5:
        freq = float(form["noise_freq"])
        phase = float(form["phase"])
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        disp = (
            np.sin(x * freq + phase)
            * np.sin(y * freq * 1.37 + phase * 1.7)
            * np.sin(z * freq * 0.81 + 2.1)
        )
        d = d - amp * disp.astype(np.float32)
    return d


def _normalize(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-8)


def _normals(points: np.ndarray, form: dict) -> np.ndarray:
    eps = np.float32(0.003)
    axes = np.eye(3, dtype=np.float32) * eps
    grad = np.stack(
        [sdf(points + axes[i], form) - sdf(points - axes[i], form) for i in range(3)],
        axis=1,
    )
    return _normalize(grad)


_PALETTE_RGB = {
    "violet": (np.array([0.20, 0.16, 0.34], dtype=np.float32), np.array([0.62, 0.58, 0.98], dtype=np.float32)),
    "grey-green": (np.array([0.26, 0.30, 0.27], dtype=np.float32), np.array([0.70, 0.76, 0.68], dtype=np.float32)),
    "gold": (np.array([0.46, 0.24, 0.08], dtype=np.float32), np.array([0.98, 0.74, 0.28], dtype=np.float32)),
    "bronze": (np.array([0.40, 0.28, 0.18], dtype=np.float32), np.array([0.86, 0.74, 0.56], dtype=np.float32)),
}


def _palette(hue: float, mutate: float, palette: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    tint = np.array(
        [
            0.55 + 0.45 * math.sin(hue * math.tau),
            0.48 + 0.35 * math.sin(hue * math.tau + 2.1),
            0.58 + 0.40 * math.sin(hue * math.tau + 4.0),
        ],
        dtype=np.float32,
    )
    tint = tint / max(float(tint.max()), 1e-3)
    flesh_calm = np.array([0.62, 0.22, 0.24], dtype=np.float32)
    flesh_drop = np.array([0.28, 0.62, 0.30], dtype=np.float32)
    flesh = flesh_calm * (1.0 - mutate) + flesh_drop * mutate
    if palette in _PALETTE_RGB:
        flesh_p, tint_p = _PALETTE_RGB[palette]
        flesh = flesh_p
        tint = tint_p
    return flesh, tint


def _shade(hit_p, rd, form) -> np.ndarray:
    n = _normals(hit_p, form)
    v = -rd
    ndotv = np.clip(np.sum(n * v, axis=1), 0.0, 1.0)
    fres = (1.0 - ndotv) ** 2.3
    key = _normalize(np.array([[0.32, 0.86, 0.38]], dtype=np.float32))[0]
    fill = _normalize(np.array([[-0.7, 0.15, -0.25]], dtype=np.float32))[0]
    diff = np.clip(n @ key, 0.0, 1.0) ** 0.85
    fill_l = np.clip(n @ fill, 0.0, 1.0)
    half = _normalize(key + v)
    spec = np.clip(np.sum(n * half, axis=1), 0.0, 1.0) ** (40.0 + 70.0 * float(form["high"]))
    # Incident ray is rd; reflect it about the normal for a studio lookup.
    ndotr = np.sum(rd * n, axis=1, keepdims=True)
    refl = rd - 2.0 * ndotr * n
    env_y = np.clip(refl[:, 1] * 0.5 + 0.5, 0.0, 1.0)
    sky = np.array([0.015, 0.02, 0.045], dtype=np.float32)
    mid = np.array([0.22, 0.16, 0.18], dtype=np.float32)
    floor = np.array([0.05, 0.035, 0.03], dtype=np.float32)
    env = mid * (1.0 - np.abs(env_y - 0.5) * 2.0)[:, None]
    upper = env_y >= 0.5
    env = np.where(upper[:, None], sky * (env_y[:, None] * 1.4) + mid * (1.0 - env_y[:, None]), env)
    env = np.where((~upper)[:, None], floor * (1.0 - env_y[:, None]) + mid * env_y[:, None], env)
    irid = 0.5 + 0.5 * np.sin(refl[:, 0] * 4.2 + float(form["hue"]) * math.tau)
    flesh, tint = _palette(float(form["hue"]), float(form["mutate"]), form.get("palette"))
    chrome = env * (0.35 + 0.75 * tint) * (0.72 + 0.28 * irid[:, None])
    flesh_lit = flesh * (0.16 + 0.9 * diff)[:, None] + flesh * (0.12 * fill_l)[:, None]
    color = flesh_lit * (1.0 - fres)[:, None] + chrome * (0.22 + 0.78 * fres)[:, None]
    color += spec[:, None] * np.array([1.0, 0.97, 0.92], dtype=np.float32) * float(form["spec"])
    color += fres[:, None] * tint * (0.12 + 0.4 * float(form["mutate"]))
    ao_p = hit_p + n * np.float32(0.09)
    ao = np.clip(sdf(ao_p, form) / np.float32(0.09), 0.0, 1.0)
    color *= (0.38 + 0.62 * ao)[:, None]
    return np.clip(color, 0.0, 4.0).astype(np.float32)


def _box_blur(image: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return image

    def blur_axis(arr: np.ndarray) -> np.ndarray:
        pad = np.pad(arr, ((radius, radius), (0, 0), (0, 0)), mode="edge")
        csum = np.cumsum(pad, axis=0, dtype=np.float32)
        window = csum[2 * radius :] - csum[: -2 * radius]
        return window / float(2 * radius)

    blurred = blur_axis(image)
    blurred = np.transpose(blurred, (1, 0, 2))
    blurred = blur_axis(blurred)
    return np.transpose(blurred, (1, 0, 2))


def render_frame(form: dict, width: int, height: int, max_steps: int = 40) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return beauty RGB uint8, depth uint8, mask uint8."""
    aspect = width / height
    lens = form.get("lens")
    if lens == "macro":
        fov = 0.55
    elif lens == "wide":
        fov = 1.05
    else:
        fov = 0.82
    ys, xs = np.mgrid[0:height, 0:width]
    uvx = ((xs + 0.5) / width * 2.0 - 1.0) * aspect * fov
    uvy = (1.0 - (ys + 0.5) / height * 2.0) * fov
    spin = float(form["spin"]) * 0.35
    if form.get("move") == "orbit":
        spin *= 1.45
    elif form.get("move") == "follow":
        spin *= 1.15
    dist = camera_distance(form)
    if form.get("shot") == "overhead":
        eye = np.array([0.08 * dist, dist * 0.92, 0.12 * dist], dtype=np.float32)
    else:
        eye = np.array(
            [math.sin(spin * 0.4) * dist, 0.42 + 0.06 * math.sin(float(form["t"]) * 0.6), math.cos(spin * 0.4) * dist],
            dtype=np.float32,
        )
    target = np.array([0.0, 0.02, 0.0], dtype=np.float32)
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0], dtype=np.float32))
    right = right / np.linalg.norm(right)
    up = np.cross(right, forward)
    rd = _normalize(forward + right * uvx[..., None] + up * uvy[..., None]).astype(np.float32)

    # Ray/bounding-sphere so background pixels never march.
    b = rd @ eye
    c = float(np.dot(eye, eye) - form["bound"] ** 2)
    disc = b * b - c
    miss = disc <= 0.0
    sqrt_disc = np.sqrt(np.maximum(disc, 0.0)).astype(np.float32)
    t_near = (-b - sqrt_disc).astype(np.float32)
    t_far = (-b + sqrt_disc).astype(np.float32)
    alive = (~miss) & (t_far > 0.0)
    t = np.maximum(t_near, 0.0).astype(np.float32)
    hit = np.zeros((height, width), dtype=bool)
    eps = np.float32(0.012)

    flat_rd = rd.reshape(-1, 3)
    for _ in range(max_steps):
        if not np.any(alive):
            break
        idx = np.flatnonzero(alive)
        t_idx = t.reshape(-1)
        points = eye + flat_rd[idx] * t_idx[idx, None]
        dist_s = sdf(points.astype(np.float32), form)
        arrived = dist_s < eps
        step = np.maximum(dist_s, np.float32(0.008))
        step[arrived] = 0.0
        t_idx[idx] = t_idx[idx] + step
        far = t_idx[idx] > t_far.reshape(-1)[idx]
        hit.reshape(-1)[idx[arrived]] = True
        alive.reshape(-1)[idx[arrived | far]] = False

    beauty = np.zeros((height, width, 3), dtype=np.float32)
    yy = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    bg = np.array([0.012, 0.013, 0.02], dtype=np.float32) * (1.0 - yy) + np.array(
        [0.025, 0.016, 0.018], dtype=np.float32
    ) * yy
    beauty[:] = bg
    vig = 1.0 - 0.55 * (uvx ** 2 + uvy ** 2) / (aspect * aspect + 1.0)
    beauty *= np.clip(vig, 0.25, 1.0)[..., None]

    if np.any(hit):
        hp = eye + rd[hit] * t[hit, None]
        shaded = _shade(hp.astype(np.float32), rd[hit], form)
        beauty[hit] = shaded

    # Soft bloom on the specular peaks. Cheap, and it sells the chrome.
    highlights = np.clip(beauty - 0.55, 0.0, 2.0)
    beauty += _box_blur(highlights, radius=max(2, width // 160)) * 0.55
    if form.get("exposure") not in (None, ""):
        beauty *= float(form["exposure"])
    beauty = np.clip(beauty, 0.0, 1.0) ** (1.0 / 2.2)

    depth = np.zeros((height, width), dtype=np.float32)
    if np.any(hit):
        near = float(np.min(t[hit]))
        far = float(np.percentile(t[hit], 95))
        span = max(far - near, 1e-3)
        depth[hit] = 1.0 - np.clip((t[hit] - near) / span, 0.0, 1.0)
    mask = hit.astype(np.float32)

    rgb = np.clip(beauty * 255.0 + 0.5, 0, 255).astype(np.uint8)
    depth_u8 = np.clip(depth * 255.0 + 0.5, 0, 255).astype(np.uint8)
    mask_u8 = np.clip(mask * 255.0, 0, 255).astype(np.uint8)
    return rgb, depth_u8, mask_u8
