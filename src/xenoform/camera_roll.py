"""Camera-roll morph: point at a folder/album; score and pick the best frames, order them by
colour/shape similarity, and chain them with scene-morphs.

    picks = pick_best("~/Pictures/trip", k=8)          # scored, de-duplicated stills/frames
    chain = order_chain(picks)                          # nearest-neighbour by colour + shape
    pairs = morph_pairs(chain)                          # (a, b) per LTX scene-morph
    spec = edit_spec(chain, beats, duration)            # scene_edit spec, every boundary a scene-morph

Scoring is local and plain: sharpness (Laplacian variance), exposure (no crushed or blown
frames), colourfulness. Face detection is off by default and not needed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from xenoform import footage

THUMB = (96, 96)


def _decode(path: str, t: float | None = None, size=THUMB) -> np.ndarray | None:
    cmd = ["ffmpeg", "-v", "error"]
    if t is not None:
        cmd += ["-ss", f"{t:.3f}"]
    cmd += ["-i", path, "-frames:v", "1", "-vf", f"scale={size[0]}:{size[1]}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    r = subprocess.run(cmd, capture_output=True)
    n = size[0] * size[1] * 3
    if r.returncode or len(r.stdout) < n:
        return None
    return np.frombuffer(r.stdout[:n], np.uint8).reshape(size[1], size[0], 3)


def candidates(folder: str | Path, *, every_s: float = 2.0, max_per_clip: int = 6) -> list[dict]:
    out = []
    for it in footage.scan_folder(folder):
        if it["kind"] == "image":
            out.append({"path": it["path"], "t": None})
        else:
            d = footage.probe_duration(it["path"])
            n = max(1, min(max_per_clip, int(d // every_s)))
            for k in range(n):
                out.append({"path": it["path"], "t": round((k + 0.5) * d / n, 3)})
    return out


def score(img: np.ndarray) -> dict:
    g = img.astype(np.float32).mean(axis=2) / 255.0
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    sharp = float(lap.var() * 1000)
    mean = float(g.mean())
    clipped = float(((g < 0.02) | (g > 0.98)).mean())
    exposure = max(0.0, 1.0 - abs(mean - 0.45) * 2.2) * (1.0 - clipped)
    r, gg, b = (img[..., i].astype(np.float32) for i in range(3))
    rg, yb = r - gg, 0.5 * (r + gg) - b
    colour = float((np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean())) / 100.0)
    total = 0.5 * min(sharp / 4.0, 1.0) + 0.3 * exposure + 0.2 * min(colour, 1.0)
    return {"sharpness": round(sharp, 4), "exposure": round(exposure, 4), "colour": round(colour, 4), "score": round(total, 4)}


def features(img: np.ndarray) -> np.ndarray:
    """Colour (8x8x8 histogram) + shape (16x16 grey layout) vector, L2-normalised per part."""
    q = (img // 32).reshape(-1, 3).astype(np.int32)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(np.float32)
    h /= np.linalg.norm(h) + 1e-9
    g = img.astype(np.float32).mean(axis=2)
    s = g.reshape(16, g.shape[0] // 16, 16, g.shape[1] // 16).mean(axis=(1, 3)).ravel()
    if s.std() < 0.5:  # flat frame: no layout to match on
        s = np.zeros_like(s)
    else:
        s = (s - s.mean()) / s.std()
        s /= np.linalg.norm(s) + 1e-9
    return np.concatenate([h, s])


def pick_best(folder: str | Path, k: int = 8, *, dedupe: float = 0.97, min_score: float = 0.2) -> list[dict]:
    picks = []
    for c in candidates(folder):
        img = _decode(c["path"], c["t"])
        if img is None:
            continue
        c.update(score(img))
        c["_f"] = features(img)
        picks.append(c)
    picks.sort(key=lambda c: -c["score"])
    chosen: list[dict] = []
    for c in picks:
        if c["score"] < min_score:
            continue
        if any(float(c["_f"] @ o["_f"]) / 2 > dedupe for o in chosen):
            continue  # near-duplicate of a better frame
        chosen.append(c)
        if len(chosen) >= k:
            break
    return chosen


def order_chain(picks: list[dict]) -> list[dict]:
    """Greedy nearest-neighbour from the best frame, so each morph travels a short visual distance."""
    if not picks:
        return []
    left = list(picks)
    chain = [left.pop(0)]
    while left:
        f = chain[-1]["_f"]
        j = int(np.argmax([float(f @ o["_f"]) for o in left]))
        chain.append(left.pop(j))
    return chain


def morph_pairs(chain: list[dict]) -> list[tuple[dict, dict]]:
    return list(zip(chain, chain[1:]))


def edit_spec(chain: list[dict], beats: list[float], duration: float, *, bars_per_shot: int = 2) -> dict:
    items = [{"path": c["path"], "kind": "image" if c["t"] is None else "video",
              "scenes": [(c["t"] or 0.0, None)], "mode": "morph-into-next"} for c in chain]
    return footage.plan_edit(items, beats, duration, bars_per_shot=bars_per_shot)


def public(chain: list[dict]) -> list[dict]:
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in chain]
