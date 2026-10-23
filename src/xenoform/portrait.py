"""Native vertical (9:16) for the Final tier: the morph stills reframed for portrait.

The vibe stills are 16:9: one object on a plain (mostly black) ground. For a native
vertical render each still is re-laid on a portrait canvas of its own background with
the whole object centred, scaled to fit (wide shapes fit the width, tall ones the
height), edges feathered into the ground. A still that is a full-frame scene rather than
an object on a ground is centre-cropped instead. numpy + ffmpeg only, CPU, free.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

PROMPT_SUFFIX = (" Vertical 9:16 portrait framing: one object centred in the frame, whole and fully in view, "
                 "empty background above and below it, locked-off camera.")
FILL_W, FILL_H = 0.95, 0.72  # the padded object box fills at most this share; min() of the two keeps it whole
STILL_W, STILL_H = 720, 1280


def _ffmpeg() -> str:
    from xenoform.cloud_morph import _ffmpeg as find

    return find()


def load_rgb(path: Path) -> np.ndarray:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    w, h = (int(v) for v in probe.stdout.strip().split(",")[:2])
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8)[: w * h * 3].reshape(h, w, 3)


def save_png(img: np.ndarray, path: Path) -> Path:
    h, w = img.shape[:2]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
                    "-frames:v", "1", str(path)], input=np.ascontiguousarray(img).tobytes(), check=True)
    return Path(path)


def background(img: np.ndarray) -> np.ndarray:
    b = max(2, min(img.shape[:2]) // 100)
    edge = np.concatenate([img[:b].reshape(-1, 3), img[-b:].reshape(-1, 3), img[:, :b].reshape(-1, 3),
                           img[:, -b:].reshape(-1, 3)])
    return np.median(edge, axis=0).astype(np.float32)


def subject_box(img: np.ndarray, bg: np.ndarray, thresh: float = 28.0) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1) of what differs from the ground; specks under 0.4 % of a row/column are ignored.

    The ground may carry a smooth glow or gradient (cosmic's indigo halo, liquid-gold's umber pool), so a pixel
    counts as subject only when it also differs from its own neighbourhood (a wide box blur): the object's
    edges and texture do, a smooth halo does not."""
    f = img.astype(np.float32)
    mask = np.abs(f - bg).max(axis=2) > thresh
    try:
        from scipy.ndimage import uniform_filter

        k = max(9, int(round(min(img.shape[:2]) / 8)) | 1)
        local = uniform_filter(f, size=(k, k, 1), mode="nearest")
        mask &= np.abs(f - local).max(axis=2) > 0.6 * thresh
    except ImportError:  # pragma: no cover
        pass
    rows = np.flatnonzero(mask.mean(axis=1) > 0.004)
    cols = np.flatnonzero(mask.mean(axis=0) > 0.004)
    if rows.size == 0 or cols.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def frame_portrait(img: np.ndarray, w: int = STILL_W, h: int = STILL_H) -> np.ndarray:
    from xenoform.beatfx import crop_box, resize

    sh, sw = img.shape[:2]
    bg = background(img)
    box = subject_box(img, bg)
    if box is None or ((box[2] - box[0]) > 0.92 * sw and (box[3] - box[1]) > 0.92 * sh):
        x, y, cw, ch = crop_box(sw, sh, "9:16", 0.5, 0.5)  # a scene, not an object on a ground
        return resize(img[y:y + ch, x:x + cw], w, h)
    x0, y0, x1, y1 = box
    pad = int(round(0.06 * max(x1 - x0, y1 - y0)))
    x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(sw, x1 + pad), min(sh, y1 + pad)
    bw, bh = x1 - x0, y1 - y0
    scale = min(FILL_W * w / bw, FILL_H * h / bh)
    nw, nh = max(2, int(round(bw * scale))), max(2, int(round(bh * scale)))
    sub = resize(img[y0:y1, x0:x1], nw, nh).astype(np.float32)
    # feather the pasted box into the ground so its edge never shows
    f = max(2, int(round(0.16 * min(nw, nh))))  # a wide feather: a glow ground brighter than the border never shows a box
    ax = np.clip(np.minimum(np.arange(nw), np.arange(nw)[::-1]) / f, 0, 1)
    ay = np.clip(np.minimum(np.arange(nh), np.arange(nh)[::-1]) / f, 0, 1)
    alpha = (ay[:, None] * ax[None, :])[..., None]
    canvas = np.empty((h, w, 3), np.float32)
    canvas[:] = bg
    ox, oy = (w - nw) // 2, (h - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = sub * alpha + bg * (1 - alpha)
    return np.clip(canvas, 0, 255).astype(np.uint8)


def black_ground(img: np.ndarray, thresh: float = 24.0) -> np.ndarray:
    """Crush a dark morph-still ground to pure black (guardrail morph_background).

    Only a ground that is already dark (median edge under 70) is touched, so a vibe with a
    deliberate light ground is never blackened by mistake.
    """
    bg = background(img)
    if float(bg.mean()) > 70.0:
        return img
    f = img.astype(np.float32)
    near = np.abs(f - bg).max(axis=2) < thresh
    dark = f.max(axis=2) < 18.0
    out = img.copy()
    out[near | dark] = 0
    return out


def black_stills(stills: list[dict], work: Path) -> list[dict]:
    """The stills with their ground forced to pure black (cached in ``work/black``)."""
    out, done = [], {}
    for s in stills:
        src = Path(s["path"])
        if src not in done:
            dest = Path(work) / "black" / f"{src.stem}_black.png"
            if not dest.is_file():
                save_png(black_ground(load_rgb(src)), dest)
            done[src] = dest
        out.append({**s, "path": str(done[src]), "black_ground": True})
    return out


def portrait_stills(stills: list[dict], work: Path, w: int = STILL_W, h: int = STILL_H,
                    background: str | None = None) -> list[dict]:
    """The same stills, re-laid for portrait (cached in ``work/portrait``). background="black" crushes the ground first."""
    if background == "black" and not all(s.get("black_ground") for s in stills):
        stills = black_stills(stills, work)
    out, done = [], {}
    for s in stills:
        src = Path(s["path"])
        if src not in done:
            dest = Path(work) / "portrait" / f"{src.stem}_{w}x{h}.png"
            if not dest.is_file():
                save_png(frame_portrait(load_rgb(src), w, h), dest)
            done[src] = dest
        out.append({**s, "path": str(done[src]), "portrait": True})
    return out
