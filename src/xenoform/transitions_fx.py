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
}
# a continuous effect, not a boundary transition
POST_EFFECTS = {"bass-pulse": "scale breathes with the bass; chroma kick on onsets"}

RECOMMENDED: dict[str, dict[str, str]] = {
    # section boundary kind -> transition, per vibe
    "liquid-gold": {"drop": "scene-morph", "switch": "liquid-melt", "beat": "stutter-cut", "silence": "black-hold"},
    "neon-night": {"drop": "chroma-split", "switch": "datamosh", "beat": "stutter-cut", "silence": "black-hold"},
    "paper-summer": {"drop": "scene-morph", "switch": "luma-wipe", "beat": "zoom-through", "silence": "black-hold"},
    "ocean": {"drop": "scene-morph", "switch": "liquid-melt", "beat": "luma-wipe", "silence": "black-hold"},
    "cosmic": {"drop": "zoom-through", "switch": "scene-morph", "beat": "chroma-split", "silence": "black-hold"},
    "black": {"drop": "scene-morph", "switch": "tape-stop", "beat": "stutter-cut", "silence": "black-hold"},
    "bloom": {"drop": "scene-morph", "switch": "luma-wipe", "beat": "liquid-melt", "silence": "black-hold"},
}


def recommend(vibe: str, boundary: str = "drop") -> str:
    table = RECOMMENDED.get(vibe, RECOMMENDED["black"])
    return table.get(boundary, table["switch"])


def public_list() -> list[dict]:
    return [{"id": k, "label": v["label"], "note": v["note"], "gpu": v["gpu"], "beats": v["beats"]}
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


def apply(kind: str, a_tail: Sequence[Frame], b_head: Sequence[Frame], intensity: float = 0.5,
          morph_frames: Sequence[Frame] | None = None) -> list[Frame]:
    """Render the frames that replace the boundary window. Length = len(a_tail)."""
    if kind not in TRANSITIONS:
        raise ValueError(f"unknown transition {kind!r}; one of {', '.join(TRANSITIONS)}")
    if len(a_tail) != len(b_head) or not len(a_tail):
        raise ValueError("a_tail and b_head must be the same non-zero length")
    i = float(np.clip(intensity, 0, 1))
    if kind == "scene-morph":
        if morph_frames:
            return resample(list(morph_frames), len(a_tail))
        kind = "flow-morph"
    return _FUNCS[kind](list(a_tail), list(b_head), i)


def resample(frames: list[Frame], n: int) -> list[Frame]:
    idx = np.linspace(0, len(frames) - 1, n).round().astype(int)
    return [frames[j] for j in idx]


def bass_pulse(frame: Frame, bass: float, onset: float = 0.0, *, depth: float = 0.035) -> Frame:
    """Continuous post effect: tasteful scale breath on bass, small chroma kick on onsets."""
    fr = scale_frame(frame, 1.0 + depth * float(np.clip(bass, 0, 1)) ** 2)
    if onset > 0.6:
        fr = chroma_shift(fr, int(6 * (onset - 0.6) / 0.4))
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
