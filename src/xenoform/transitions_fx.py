"""Scene transitions for Xenoform edits: whole-scene morphs plus a curated set of
audio-reactive post transitions (numpy, optional OpenCV for optical flow).

Every transition takes the tail frames of clip A and the head frames of clip B
(uint8 HxWx3 arrays, equal length N) plus an ``intensity`` in 0..1 (drive it from
the bass/onset envelope) and returns N output frames. ``scene-morph`` is special:
the in-between frames are rendered on LTX-2.3 from A's last frame and B's first
frame (see ``scene_morph_graph``) and spliced with ``splice_scene_morph``; when the
GPU is unavailable it falls back to ``flow-morph``.
"""
from __future__ import annotations

from typing import Callable, Iterable, Sequence

import numpy as np

try:  # optional: better flow-morph
    import cv2  # type: ignore
except Exception:  # pragma: no cover - depends on the machine
    cv2 = None

Frame = np.ndarray

TRANSITIONS: dict[str, dict] = {
    "scene-morph": {"label": "Scene morph", "beats": 4, "gpu": True,
                    "note": "LTX-2.3 first/last-frame morph: the whole frame melts into the next clip"},
    "flow-morph": {"label": "Flow morph", "beats": 2, "gpu": False,
                   "note": "optical-flow warp + blend; the CPU fallback for scene-morph"},
    "liquid-melt": {"label": "Liquid chrome melt", "beats": 2, "gpu": False,
                    "note": "the frame ripples like molten chrome, then sets as the next scene"},
    "luma-wipe": {"label": "Luma matte wipe", "beats": 2, "gpu": False,
                  "note": "darks of A open first, revealing B through its shadows"},
    "stutter-cut": {"label": "Beat cut + stutter", "beats": 1, "gpu": False,
                    "note": "hard cut on the beat, B's first frames stutter like a Prodigy break"},
    "tape-stop": {"label": "Tape-stop warp", "beats": 2, "gpu": False,
                  "note": "A slows, sags and freezes like a tape stop, then B drops in"},
    "datamosh": {"label": "Datamosh burst", "beats": 1, "gpu": False,
                 "note": "short block-smear burst; B's motion pushes through A's pixels"},
    "chroma-split": {"label": "Chromatic split", "beats": 1, "gpu": False,
                     "note": "RGB channels tear apart on the transient and snap back on B"},
    "zoom-through": {"label": "Zoom-through", "beats": 1, "gpu": False,
                     "note": "push into the centre of A and land inside B"},
    "black-hold": {"label": "Silence = black", "beats": 2, "gpu": False,
                   "note": "drop to black for the gap in the music, B returns on the hit"},
    "cut": {"label": "Clean beat cut", "beats": 1, "gpu": False, "tier": "core",
             "note": "a straight cut on the beat; most boundaries should be this"},
    "match-cut": {"label": "Match-cut", "beats": 2, "gpu": False, "tier": "premium",
             "note": "B's dominant subject is aligned onto A's silhouette (position + scale) at the cut, then glides home"},
    "flow-carry": {"label": "Flow carry", "beats": 2, "gpu": False, "tier": "premium",
             "note": "A's optical-flow motion pushes through the cut and B arrives already moving the same way"},
    "depth-parallax": {"label": "Depth parallax dissolve", "beats": 2, "gpu": False, "tier": "premium",
             "note": "near layers drift further than far ones (depth estimate); B resolves near-first"},
    "lens-breath": {"label": "Lens breath", "beats": 2, "gpu": False, "tier": "premium",
             "note": "rack-defocus with real disc bokeh in linear light, swap hidden at peak defocus, faint warm leak"},
    "chrome-refract": {"label": "Chrome refraction carry", "beats": 2, "gpu": False, "tier": "premium",
             "note": "B is seen through A's surface normals like liquid chrome glass, relaxing as B takes over"},
    "echo-trail": {"label": "Echo trail", "beats": 2, "gpu": False, "tier": "premium",
             "note": "A leaves a decaying ghost trail, the cut lands on the beat and the afterimage fades off B"},
}
for _k, _v in TRANSITIONS.items():
    _v.setdefault("tier", "classic" if _k in ("luma-wipe", "stutter-cut", "zoom-through") else "core")
# a continuous effect, not a boundary transition
POST_EFFECTS = {"bass-pulse": "scale breathes with the bass; chroma kick on onsets"}

RECOMMENDED: dict[str, dict[str, str]] = {
    # section boundary kind -> transition, per vibe. Most on-beat boundaries are clean cuts (v5).
    "liquid-gold": {"drop": "scene-morph", "switch": "chrome-refract", "beat": "cut", "silence": "black-hold"},
    "neon-night": {"drop": "flow-carry", "switch": "echo-trail", "beat": "cut", "silence": "black-hold"},
    "paper-summer": {"drop": "scene-morph", "switch": "depth-parallax", "beat": "cut", "silence": "black-hold"},
    "ocean": {"drop": "scene-morph", "switch": "flow-carry", "beat": "cut", "silence": "black-hold"},
    "cosmic": {"drop": "match-cut", "switch": "scene-morph", "beat": "cut", "silence": "black-hold"},
    "black": {"drop": "scene-morph", "switch": "match-cut", "beat": "cut", "silence": "black-hold"},
    "bloom": {"drop": "scene-morph", "switch": "lens-breath", "beat": "cut", "silence": "black-hold"},
}


def _registry_recommendations() -> None:
    """Extended vibes carry their own picks in configs/vibes.json."""
    try:
        from xenoform import vibes as _vibes
    except Exception:  # pragma: no cover
        return
    for row in _vibes.extended():
        picks = {k: v for k, v in (row.get("transitions") or {}).items() if v in TRANSITIONS}
        if picks:
            RECOMMENDED.setdefault(row["id"], picks)


_registry_recommendations()


_REMAP = {"luma-wipe": "depth-parallax", "stutter-cut": "cut", "zoom-through": "match-cut"}


def _house_rules() -> dict:
    """The house ``transitions`` block (allowed / banned / max_uses_per_type / intensity / classic), or {}."""
    try:
        from xenoform.config import house
    except ImportError:  # pragma: no cover - loose checkout
        try:
            from config import house
        except ImportError:
            return {}
    return house("transitions")


def _is_banned(kind: str, banned: Sequence[str]) -> bool:
    k = str(kind).lower()
    return any(str(b).lower() in k for b in banned or ())


def recommend(vibe: str, boundary: str = "drop", *, classic: bool | None = None) -> str:
    """``classic`` None falls back to the house rule (False: classic wipes are remapped to premium picks)."""
    if classic is None:
        classic = bool(_house_rules().get("classic", False))
    table = RECOMMENDED.get(vibe, RECOMMENDED["black"])
    k = table.get(boundary, table["switch"])
    return k if classic else _REMAP.get(k, k)


def public_list() -> list[dict]:
    return [{"id": k, "label": v["label"], "note": v["note"], "gpu": v["gpu"], "beats": v["beats"], "tier": v["tier"]}
            for k, v in TRANSITIONS.items()]


# ---------------------------------------------------------------- timing
def snap_to_beats(times: Iterable[float], beats: Sequence[float], *, every: int = 1, max_shift: float = 0.35) -> list[float]:
    """Move each cut to the nearest beat (every=4 snaps to bars when beats start on a downbeat)."""
    grid = np.asarray(beats, dtype=float)[::max(1, int(every))]
    out = []
    for t in times:
        if grid.size == 0:
            out.append(float(t)); continue
        g = float(grid[np.argmin(np.abs(grid - t))])
        out.append(g if abs(g - t) <= max_shift else float(t))
    return out


def envelope_at(t: float, env_t: Sequence[float], env_v: Sequence[float]) -> float:
    if not len(env_t):
        return 0.0
    return float(np.interp(t, env_t, env_v))


# ---------------------------------------------------------------- helpers
def _ease(x: np.ndarray | float) -> np.ndarray | float:
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(x, 0.0, 1.0))


def _mix(a: Frame, b: Frame, w: float | np.ndarray) -> Frame:
    w = np.asarray(w, dtype=np.float32)
    if w.ndim == 2:
        w = w[..., None]
    return np.clip(a.astype(np.float32) * (1 - w) + b.astype(np.float32) * w, 0, 255).astype(np.uint8)


def _remap(img: Frame, mx: np.ndarray, my: np.ndarray) -> Frame:
    h, w = img.shape[:2]
    if cv2 is not None:
        return cv2.remap(img, mx.astype(np.float32), my.astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    xi = np.clip(np.rint(mx), 0, w - 1).astype(np.intp)
    yi = np.clip(np.rint(my), 0, h - 1).astype(np.intp)
    return img[yi, xi]


def _grid(h: int, w: int):
    return np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))


def scale_frame(img: Frame, s: float) -> Frame:
    """Zoom about the centre (s>1 zooms in)."""
    if abs(s - 1.0) < 1e-4:
        return img
    h, w = img.shape[:2]
    gx, gy = _grid(h, w)
    return _remap(img, (gx - w / 2) / s + w / 2, (gy - h / 2) / s + h / 2)


def chroma_shift(img: Frame, px: int) -> Frame:
    if px <= 0:
        return img
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], px, axis=1)
    out[..., 2] = np.roll(img[..., 2], -px, axis=1)
    return out


def _luma(img: Frame) -> np.ndarray:
    return (img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114).astype(np.float32) / 255.0


# ---------------------------------------------------------------- transitions
def _flow_morph(a, b, i):
    n = len(a); out = []
    A, B = a[-1], b[0]
    h, w = A.shape[:2]
    gx, gy = _grid(h, w)
    flow = None
    if cv2 is not None:
        sm = 0.25
        ga = cv2.resize(cv2.cvtColor(A, cv2.COLOR_RGB2GRAY), None, fx=sm, fy=sm)
        gb = cv2.resize(cv2.cvtColor(B, cv2.COLOR_RGB2GRAY), None, fx=sm, fy=sm)
        f = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 5, 41, 5, 7, 1.5, 0)
        flow = cv2.resize(f, (w, h)) / sm
    for k in range(n):
        t = float(_ease((k + 1) / (n + 1)))
        if flow is None:
            out.append(_liquid_frame(a[k], b[k], t, i)); continue
        wa = _remap(a[k], gx - flow[..., 0] * t, gy - flow[..., 1] * t)
        wb = _remap(b[k], gx + flow[..., 0] * (1 - t), gy + flow[..., 1] * (1 - t))
        out.append(_mix(wa, wb, t))
    return out


def _liquid_frame(fa, fb, t, i):
    h, w = fa.shape[:2]
    gx, gy = _grid(h, w)
    amp = (8 + 30 * i) * np.sin(np.pi * t) * (w / 1080)
    ph = t * 6.0
    dx = amp * np.sin(gy / (h / 9.0) + ph) * np.cos(gx / (w / 5.0) - ph * 0.7)
    dy = amp * np.cos(gx / (w / 7.0) + ph * 1.3)
    wa = _remap(fa, gx + dx, gy + dy)
    wb = _remap(fb, gx - dx, gy - dy)
    # chrome: a soft specular lift on the ripple crests at mid-transition
    spec = np.clip(np.sin(gy / (h / 9.0) + ph) * np.sin(np.pi * t), 0, 1) ** 4 * 40 * (0.5 + 0.5 * i)
    m = _mix(wa, wb, float(_ease(t))).astype(np.float32) + spec[..., None]
    return np.clip(m, 0, 255).astype(np.uint8)


def _liquid(a, b, i):
    n = len(a)
    return [_liquid_frame(a[k], b[k], (k + 1) / (n + 1), i) for k in range(n)]


def _luma_wipe(a, b, i):
    n = len(a); out = []
    for k in range(n):
        t = (k + 1) / (n + 1)
        L = _luma(a[k])
        soft = 0.08
        w = np.clip((t * (1 + soft) - L) / soft, 0, 1)
        out.append(_mix(a[k], b[k], w))
    return out


def _stutter(a, b, i):
    n = len(a); out = []
    step = 2 if i < 0.5 else 3
    for k in range(n):
        src = b[min(n - 1, (k // step) * step // 2)]
        fr = chroma_shift(src, int(6 * i)) if (k // step) % 2 == 0 and k < n // 2 else src
        out.append(fr)
    return out


def _tape_stop(a, b, i):
    n = len(a); out = []
    half = max(1, int(n * 0.65))
    pos = 0.0
    for k in range(n):
        if k < half:
            t = k / half
            pos += (1 - t) ** 2
            fr = a[min(n - 1, int(pos))]
            h, w = fr.shape[:2]
            gx, gy = _grid(h, w)
            sag = (t ** 2) * (40 + 60 * i) * (h / 1920) * np.sin(np.pi * gx / w)
            fr = _remap(fr, gx, gy - sag)
            fr = (fr.astype(np.float32) * (1 - 0.6 * t)).astype(np.uint8)
            out.append(fr)
        else:
            out.append(b[k - half])
    return out


def _datamosh(a, b, i):
    n = len(a); out = []
    rng = np.random.default_rng(7)
    h, w = a[0].shape[:2]
    bs = max(8, w // 40)
    base = a[-1].copy()
    for k in range(n):
        t = (k + 1) / (n + 1)
        if t > 0.75:
            out.append(_mix(base, b[k], (t - 0.75) / 0.25)); continue
        mv = b[k].astype(np.int16) - b[max(0, k - 1)].astype(np.int16)
        motion = np.abs(mv).mean(axis=2)
        gh, gw = h // bs, w // bs
        mblk = motion[:gh * bs, :gw * bs].reshape(gh, bs, gw, bs).mean(axis=(1, 3))
        thr = np.quantile(mblk, 1 - (0.2 + 0.5 * i) * min(1, t * 2))
        sel = np.argwhere(mblk >= thr)
        for (y, x) in sel:
            dy, dx = rng.integers(-2, 3, size=2) * bs // 2
            ys, xs = slice(y * bs, (y + 1) * bs), slice(x * bs, (x + 1) * bs)
            y2 = int(np.clip(y * bs + dy, 0, h - bs)); x2 = int(np.clip(x * bs + dx, 0, w - bs))
            base[ys, xs] = b[k][y2:y2 + bs, x2:x2 + bs]
        out.append(base.copy())
    return out


def _chroma(a, b, i):
    n = len(a); out = []
    mid = n // 2
    for k in range(n):
        if k < mid:
            px = int((4 + 26 * i) * ((k + 1) / mid) ** 2)
            out.append(chroma_shift(a[k], px))
        else:
            px = int((4 + 26 * i) * (1 - (k - mid) / max(1, n - mid)) ** 2)
            out.append(chroma_shift(b[k], px))
    return out


def _zoom(a, b, i):
    n = len(a); out = []
    mid = n // 2
    for k in range(n):
        if k < mid:
            t = (k + 1) / mid
            out.append(scale_frame(a[k], 1 + (1.2 + i) * t ** 2))
        else:
            t = (k - mid + 1) / max(1, n - mid)
            out.append(scale_frame(b[k], 1 + 0.35 * (1 - t) ** 2))
    return out


def _black(a, b, i):
    n = len(a); out = []
    q = max(1, n // 4)
    for k in range(n):
        if k < q:
            out.append((a[k].astype(np.float32) * (1 - (k + 1) / q)).astype(np.uint8))
        elif k >= n - 1:
            out.append(b[k])
        else:
            out.append(np.zeros_like(a[k]))
    return out


_FUNCS: dict[str, Callable] = {
    "flow-morph": _flow_morph, "liquid-melt": _liquid, "luma-wipe": _luma_wipe, "stutter-cut": _stutter,
    "tape-stop": _tape_stop, "datamosh": _datamosh, "chroma-split": _chroma, "zoom-through": _zoom,
    "black-hold": _black,
}


# ---------------------------------------------------------------- premium "new spells" (v5)
# Subtle, beat-aware, no shimmer: every displacement is a single smooth bump (sin(pi t)), never an
# oscillation in time, and every one ends exactly on clip B.
def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0.3:
        return img
    if cv2 is not None:
        return cv2.GaussianBlur(img, (0, 0), sigma)
    k = max(1, int(sigma))
    out = img.astype(np.float32)
    for ax in (0, 1):
        out = sum(np.roll(out, s, axis=ax) for s in range(-k, k + 1)) / (2 * k + 1)
    return out


def depth_proxy(img: Frame) -> np.ndarray:
    """Cheap monocular depth estimate in 0..1 (1 = near): soft luma + local sharpness + a floor prior.
    Xenoform shots are mostly a lit subject on a dark ground, which is where this proxy is reliable."""
    L = _luma(img)
    h, w = L.shape
    s = max(1.0, w / 270)
    lum = _blur(L, 6 * s)
    if cv2 is not None:
        sharp = _blur(np.abs(cv2.Laplacian(L, cv2.CV_32F)), 8 * s)
    else:
        sharp = _blur(np.abs(L - _blur(L, 2 * s)), 8 * s)
    sharp = sharp / (float(sharp.max()) + 1e-6)
    floor = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None] * np.ones((1, w), np.float32)
    d = 0.5 * lum / (float(lum.max()) + 1e-6) + 0.35 * sharp + 0.15 * floor
    return np.clip(_blur(d.astype(np.float32), 4 * s), 0, 1).astype(np.float32)


def subject_box(img: Frame) -> tuple[float, float, float]:
    """Dominant subject (cx, cy, size) from a soft luma mask against the ground."""
    L = _blur(_luma(img), max(1.0, img.shape[1] / 360))
    h, w = L.shape
    thr = max(0.1, float(np.percentile(L, 70)))
    m = L > thr
    if m.mean() < 0.005 or m.mean() > 0.95:
        m = L > float(L.mean())
    ys, xs = np.nonzero(m)
    if len(xs) < 8:
        return w / 2, h / 2, 1.0
    return float(xs.mean()), float(ys.mean()), float(np.sqrt(m.mean()))


def _match_cut(a, b, i):
    """Match-cut: B's dominant subject is aligned onto A's (position + scale) at the cut, then glides home."""
    n = len(a); out = []
    h, w = a[0].shape[:2]
    gx, gy = _grid(h, w)
    ax, ay, asz = subject_box(a[-1])
    bx, by, bsz = subject_box(b[0])
    k0 = float(np.clip(asz / max(bsz, 1e-3), 0.6, 1.6))
    for k in range(n):
        t = (k + 1) / (n + 1)
        e = float(_ease(t))
        kk = k0 ** (1 - e)
        cx, cy = ax * (1 - e) + bx * e, ay * (1 - e) + by * e
        wb = _remap(b[k], bx + (gx - cx) / kk, by + (gy - cy) / kk)
        mix = float(_ease(min(1.0, t / 0.3)))  # the cut itself is fast: a 30% soft dissolve
        out.append(_mix(a[k], wb, mix))
    return out


def _flow_carry(a, b, i):
    """Optical-flow carry: A's own motion (flow of its last two frames) pushes through the cut and
    B arrives already moving the same way, so the motion reads as one continuous take."""
    n = len(a); out = []
    h, w = a[0].shape[:2]
    gx, gy = _grid(h, w)
    vx = np.zeros((h, w), np.float32); vy = np.zeros((h, w), np.float32)
    if cv2 is not None and n >= 2:
        sm = 0.25
        g0 = cv2.resize(cv2.cvtColor(a[-2], cv2.COLOR_RGB2GRAY), None, fx=sm, fy=sm)
        g1 = cv2.resize(cv2.cvtColor(a[-1], cv2.COLOR_RGB2GRAY), None, fx=sm, fy=sm)
        f = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 4, 31, 4, 7, 1.5, 0)
        f = cv2.GaussianBlur(f, (0, 0), 6)
        f = cv2.resize(f, (w, h)) / sm
        vx, vy = f[..., 0], f[..., 1]
    # global carry plus a gentle push-in so a static shot still flows
    gm = float(np.hypot(vx.mean(), vy.mean()))
    cap = 0.02 * w
    sc = min(1.0, cap / (gm + 1e-6)) if gm > 0 else 1.0
    vx, vy = vx * sc, vy * sc
    span = n * (0.6 + 0.6 * i)
    for k in range(n):
        t = (k + 1) / (n + 1)
        e = float(_ease(t))
        push = 1 + 0.025 * (0.5 + i) * np.sin(np.pi * t)
        wa = _remap(a[k], (gx - vx * span * t - w / 2) / push + w / 2, (gy - vy * span * t - h / 2) / push + h / 2)
        wb = _remap(b[k], (gx + vx * span * (1 - t) - w / 2) / push + w / 2, (gy + vy * span * (1 - t) - h / 2) / push + h / 2)
        out.append(_mix(wa, wb, e))
    return out


def _depth_parallax(a, b, i):
    """Depth-aware parallax dissolve: near layers drift further than far ones, and B resolves near-first."""
    n = len(a); out = []
    h, w = a[0].shape[:2]
    gx, gy = _grid(h, w)
    da, db = depth_proxy(a[-1]), depth_proxy(b[0])
    amp = (0.015 + 0.02 * i) * w
    for k in range(n):
        t = (k + 1) / (n + 1)
        wa = _remap(a[k], gx - da * amp * t, gy - da * amp * 0.25 * t)
        wb = _remap(b[k], gx + db * amp * (1 - t), gy + db * amp * 0.25 * (1 - t))
        m = np.clip((t - 0.35 * (1 - db)) / 0.65, 0, 1)
        out.append(_mix(wa, wb, _ease(m)))
    return out


def _disk(r: int) -> np.ndarray:
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    k = ((x * x + y * y) <= r * r).astype(np.float32)
    return k / k.sum()


def _bokeh(img: Frame, r: float) -> np.ndarray:
    f = (img.astype(np.float32) / 255.0) ** 2.2  # linear light, so highlights bloom into discs
    if r < 1:
        return f
    if cv2 is not None:
        sm = 0.5 if img.shape[1] > 720 else 1.0
        small = cv2.resize(f, None, fx=sm, fy=sm, interpolation=cv2.INTER_AREA) if sm < 1 else f
        small = cv2.filter2D(small, -1, _disk(max(1, int(r * sm))), borderType=cv2.BORDER_REFLECT)
        return cv2.resize(small, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_LINEAR) if sm < 1 else small
    return _blur(f, r / 2)


def _lens_breath(a, b, i):
    """Lens breath: a rack-defocus with real disc bokeh in linear light, the swap hidden at peak
    defocus, a 1.5% focus-breathing scale and a faint warm leak. Refocuses on B."""
    n = len(a); out = []
    h, w = a[0].shape[:2]
    gx, gy = _grid(h, w)
    R = (0.008 + 0.01 * i) * w
    leak = np.clip(1 - np.hypot((gx - w * 0.9) / w, (gy - h * 0.1) / h) * 1.6, 0, 1) ** 2
    warm = np.stack([leak, leak * 0.55, leak * 0.25], -1).astype(np.float32)
    for k in range(n):
        t = (k + 1) / (n + 1)
        bump = float(np.sin(np.pi * t))
        s = 1 + 0.015 * bump
        src = a[k] if t < 0.5 else b[k]
        fr = scale_frame(src, s)
        lin = _bokeh(fr, R * bump)
        if 0.35 < t < 0.65:  # cross the swap inside the defocus
            other = _bokeh(scale_frame(b[k] if t < 0.5 else a[k], s), R * bump)
            q = (t - 0.35) / 0.3
            lin = lin * (1 - q) + other * q if t < 0.5 else other * (1 - q) + lin * q
        lin = lin + warm * (0.10 * bump * (0.4 + i))
        out.append(np.clip((np.clip(lin, 0, 1) ** (1 / 2.2)) * 255, 0, 255).astype(np.uint8))
    return out


def _chrome_refract(a, b, i):
    """Liquid-chrome refraction carry-through: B is seen through A's surface normals (as if A were
    glass), the refraction relaxes as B takes over. One smooth bump, no ripple in time."""
    n = len(a); out = []
    h, w = a[0].shape[:2]
    gx, gy = _grid(h, w)
    s = max(1.0, w / 360)
    La, Lb = _blur(_luma(a[-1]), 3 * s), _blur(_luma(b[0]), 3 * s)
    ny_a, nx_a = np.gradient(La); ny_b, nx_b = np.gradient(Lb)
    norm = max(float(np.abs(nx_a).max()), float(np.abs(ny_a).max()), 1e-6)
    nx_a, ny_a = nx_a / norm, ny_a / norm
    normb = max(float(np.abs(nx_b).max()), float(np.abs(ny_b).max()), 1e-6)
    nx_b, ny_b = nx_b / normb, ny_b / normb
    amp = (0.02 + 0.03 * i) * w
    spec = np.clip(np.hypot(nx_a, ny_a), 0, 1) ** 3
    for k in range(n):
        t = (k + 1) / (n + 1)
        bump = float(np.sin(np.pi * t))
        e = float(_ease(t))
        wb = _remap(b[k], gx + nx_a * amp * bump * (1 - e), gy + ny_a * amp * bump * (1 - e))
        wa = _remap(a[k], gx - nx_b * amp * bump * e, gy - ny_b * amp * bump * e)
        m = _mix(wa, wb, e).astype(np.float32) + (spec * 28 * bump * (0.5 + i))[..., None]
        out.append(np.clip(m, 0, 255).astype(np.uint8))
    return out


def _echo_trail(a, b, i):
    """Temporal echo on the beat: A leaves a decaying ghost trail, the cut lands on the beat (the
    middle of the window) and A's afterimage fades off B by the end."""
    n = len(a); out = []
    mid = n // 2
    acc = a[0].astype(np.float32)
    decay = 0.6 + 0.25 * i
    for k in range(n):
        if k < mid:
            acc = acc * decay + a[k].astype(np.float32) * (1 - decay)
            fr = a[k].astype(np.float32)
            out.append(np.clip(fr + np.maximum(0, acc - fr) * 0.55, 0, 255).astype(np.uint8))
        else:
            g = 0.5 * (1 - (k - mid + 1) / max(1, n - mid)) ** 2
            fr = b[k].astype(np.float32)
            out.append(np.clip(fr + np.maximum(0, acc - fr) * g, 0, 255).astype(np.uint8))
    return out


def _cut(a, b, i):
    return [f.copy() for f in b]


# ---------------------------------------------------------------- auto-pick (v5)
CLASSIC = ("luma-wipe", "stutter-cut", "zoom-through")
PREMIUM = ("match-cut", "flow-carry", "depth-parallax", "lens-breath", "chrome-refract", "echo-trail")
# favour match-cut and flow; scene-morph stays the signature on drops when a morph is rendered
AUTO_WEIGHTS = {"match-cut": 3.0, "flow-carry": 3.0, "depth-parallax": 1.5, "lens-breath": 1.2,
                "chrome-refract": 1.0, "echo-trail": 0.8}
EXEMPT_FROM_CAP = ("cut", "scene-morph", "black-hold")


def _cfg_rules() -> dict:
    try:
        import json as _json
        from pathlib import Path as _P
        p = _P(__file__).resolve().parents[2] / "configs" / "guardrails.json"
        return _json.loads(p.read_text(encoding="utf-8"))["rules"].get("transition_variety", {})
    except Exception:
        return {}


def _resolve_rules(cap: int | None, allowed: Sequence[str] | None, banned: Sequence[str] | None) -> tuple[int, list[str], list[str]]:
    """Explicit values win; None falls back to the house ``transitions`` block, then configs/guardrails.json.
    ``allowed`` [] (or any empty sequence) means no whitelist; None means the house list."""
    h = _house_rules(); r = _cfg_rules()
    if cap is None:
        cap = h.get("max_uses_per_type", r.get("max_per_type", 2))
    if allowed is None:
        allowed = h.get("allowed") or []
    if banned is None:
        banned = h.get("banned") or []
    return max(1, int(cap)), [str(a) for a in allowed], [str(b) for b in banned]


def pick_premium(used: dict[str, int], rng: np.random.Generator, *, max_per_type: int = 2,
                 allowed: Sequence[str] | None = None, banned: Sequence[str] | None = None) -> str:
    """A weighted premium pick under the per-type cap. ``allowed`` (a non-empty whitelist) and ``banned``
    (substrings) narrow the pool; None falls back to the house rules. "cut" when nothing is left."""
    _, allowed, banned = _resolve_rules(max_per_type, allowed, banned)
    pool = {k: w for k, w in AUTO_WEIGHTS.items() if used.get(k, 0) < max_per_type
            and (not allowed or k in allowed) and not _is_banned(k, banned)}
    if not pool:
        return "cut"
    keys = list(pool); p = np.asarray([pool[k] for k in keys], float); p /= p.sum()
    return str(rng.choice(keys, p=p))


def plan(boundaries: Sequence[dict], *, seed: int = 0, classic: bool | None = None, cap: int | None = None,
         allowed: Sequence[str] | None = None, banned: Sequence[str] | None = None) -> list[str]:
    """Pick a transition per boundary. boundaries: [{"section": bool, "morph": bool, "silence": bool}].
    Most boundaries are clean beat cuts; section changes get one premium spell, each type at most
    ``cap`` times per video, and premium moments stay under max_fx_share of all boundaries.
    ``cap`` / ``allowed`` / ``banned`` / ``classic`` None fall back to the house transitions rules."""
    r = _cfg_rules()
    cap, allowed, banned = _resolve_rules(cap, allowed, banned)
    share = float(r.get("max_fx_share", 0.35))
    rng = np.random.default_rng(seed)
    used: dict[str, int] = {}
    out: list[str] = []
    budget = max(1, int(round(share * max(1, len(boundaries)))))
    for bd in boundaries:
        if bd.get("morph"):
            out.append("scene-morph"); continue
        if bd.get("silence"):
            out.append("black-hold"); continue
        if bd.get("section") and budget > 0:
            k = pick_premium(used, rng, max_per_type=cap, allowed=allowed, banned=banned)
            if k != "cut":
                used[k] = used.get(k, 0) + 1; budget -= 1
            out.append(k); continue
        out.append("cut")
    return out


def guard(kinds: Sequence[str], *, expert: bool = False, seed: int = 0, cap: int | None = None,
          allowed: Sequence[str] | None = None, banned: Sequence[str] | None = None) -> tuple[list[str], list[str]]:
    """Guardrail: classic wipes are expert-only, house-banned kinds (substring match, e.g. "wipe", "stutter")
    are re-picked, and no one transition type appears more than ``cap`` times. Overflow becomes a clean
    cut. ``expert`` keeps the user's values and only warns. ``cap`` / ``allowed`` / ``banned`` None fall back
    to the house rules. Returns (kinds, messages)."""
    r = _cfg_rules()
    cap, allowed, banned = _resolve_rules(cap, allowed, banned)
    classic_ok = expert or not r.get("classic_expert_only", True)
    rng = np.random.default_rng(seed)
    used: dict[str, int] = {}
    out, msgs = [], []
    for k in kinds:
        nk = k
        if k in CLASSIC and not classic_ok:
            nk = pick_premium(used, rng, max_per_type=cap, allowed=allowed, banned=banned)
            msgs.append(f"{k} is a Classic transition (expert only); using {nk}")
        elif nk in TRANSITIONS and nk not in EXEMPT_FROM_CAP and _is_banned(nk, banned):
            if expert:
                msgs.append(f"{nk} is banned by the house rules (kept: expert)")
            else:
                nk = pick_premium(used, rng, max_per_type=cap, allowed=allowed, banned=banned)
                msgs.append(f"{k} is banned by the house rules; using {nk}")
        if nk in TRANSITIONS and nk not in EXEMPT_FROM_CAP:
            if used.get(nk, 0) >= cap and not expert:
                msgs.append(f"{nk} already used {cap}x; this boundary is a clean beat cut")
                nk = "cut"
            used[nk] = used.get(nk, 0) + 1
        out.append(nk)
    return out, msgs


_FUNCS.update({"cut": _cut, "match-cut": _match_cut, "flow-carry": _flow_carry, "depth-parallax": _depth_parallax,
               "lens-breath": _lens_breath, "chrome-refract": _chrome_refract, "echo-trail": _echo_trail})



DEFAULT_INTENSITY = 0.5


def apply(kind: str, a_tail: Sequence[Frame], b_head: Sequence[Frame], intensity: float | None = None,
          morph_frames: Sequence[Frame] | None = None) -> list[Frame]:
    """Render the frames that replace the boundary window. Length = len(a_tail).
    ``intensity`` None falls back to the house ``transitions.intensity`` (else 0.5)."""
    if kind not in TRANSITIONS:
        raise ValueError(f"unknown transition {kind!r}; one of {', '.join(TRANSITIONS)}")
    if len(a_tail) != len(b_head) or not len(a_tail):
        raise ValueError("a_tail and b_head must be the same non-zero length")
    if intensity is None:
        intensity = float(_house_rules().get("intensity", DEFAULT_INTENSITY))
    i = float(np.clip(intensity, 0, 1))
    if kind == "scene-morph":
        if morph_frames:
            return resample(list(morph_frames), len(a_tail))
        kind = "flow-morph"
    return _FUNCS[kind](list(a_tail), list(b_head), i)


def resample(frames: list[Frame], n: int) -> list[Frame]:
    idx = np.linspace(0, len(frames) - 1, n).round().astype(int)
    return [frames[j] for j in idx]


def bass_pulse(frame: Frame, bass: float, onset: float = 0.0, *, depth: float = 0.01) -> Frame:
    """Continuous post effect: tasteful scale breath on bass, small chroma kick on onsets."""
    fr = scale_frame(frame, 1.0 + depth * float(np.clip(bass, 0, 1)) ** 2)
    if onset > 0.6:
        fr = chroma_shift(fr, int(3 * (onset - 0.6) / 0.4))
    return fr


# ---------------------------------------------------------------- scene-morph on LTX
SCENE_MORPH_PROMPT = (
    "Use the provided start image as the first frame and the provided end image as the final frame anchor. "
    "The entire scene melts and flows as one continuous liquid chrome transformation into the next scene, "
    "every shape reshapes smoothly into the matching shape of the next image, seamless morph, no cut, no fade, "
    "elegant slow motion, deep black background, crisp, clean, high detail. Vertical 9:16 portrait framing, locked-off camera.")


def scene_morph_graph(a_png: str, b_png: str, *, seconds: float = 2.0, seed: int = 4242, vertical: bool = True,
                      prefix: str = "xenoform/scenemorph") -> dict:
    """ComfyUI graph: LTX-2.3 two-stage first/last-frame morph (448x768 native 9:16 -> 1080x1920)."""
    from xenoform import final_tier as ft

    rw, rh = (448, 768) if vertical else (768, 448)
    ow, oh = (1080, 1920) if vertical else (1920, 1080)
    prompt = SCENE_MORPH_PROMPT if vertical else SCENE_MORPH_PROMPT.replace("Vertical 9:16 portrait framing", "Wide 16:9 framing")
    g = ft.graph(prompt, length=ft.gen_length(seconds), seed=seed, prefix=prefix, width=rw, height=rh, out_w=ow, out_h=oh)
    g["100"]["inputs"]["image"] = a_png
    g["101"]["inputs"]["image"] = b_png
    return g


def splice_scene_morph(a: Sequence[Frame], morph: Sequence[Frame], b: Sequence[Frame], *, blend: int = 3) -> list[Frame]:
    """A (ending on the frame the morph started from) -> morph -> B. Short blends hide the encoder seam."""
    a, morph, b = list(a), list(morph), list(b)
    k = max(0, min(blend, len(morph) // 3, len(a), len(b)))
    head = [_mix(a[len(a) - k + j], morph[j], (j + 1) / (k + 1)) for j in range(k)]
    tail = [_mix(morph[len(morph) - k + j], b[j], (j + 1) / (k + 1)) for j in range(k)]
    return a[:len(a) - k] + head + morph[k:len(morph) - k] + tail + b[k:]
