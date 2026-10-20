"""Automated hallucination / quality check for rendered shots.

Two checks, cheapest first:

- temporal: frame-to-frame luma pops and flicker (numpy only, always on);
- semantic (optional, when torch + transformers + a cached CLIP are present):
  CLIP ViT-B/32 compares sampled frames against a good-shot prompt and a list of
  failure prompts ("duplicated features", "cartoon", "warped melted shape"...).

``check()`` returns ``{"ok", "score", "reasons", ...}``; ``morph_pass`` rerolls a
failed shot once with a new seed and less freedom.
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

FAIL_PROMPTS = (
    "an image with duplicated repeated features",
    "a cartoon illustration",
    "a warped melted deformed blob",
    "a blurry noisy smeared image",
    "an image with text and watermark",
)
FLICKER_MAX = float(os.environ.get("XENO_QA_FLICKER", "0.09"))
POP_MAX = float(os.environ.get("XENO_QA_POP", "0.22"))
CLIP_MARGIN = float(os.environ.get("XENO_QA_CLIP_MARGIN", "-0.5"))


def temporal(frames: np.ndarray) -> dict:
    """``frames``: N x H x W x 3 uint8. Flicker = mean |d luma mean|; pop = worst frame diff."""
    if frames is None or len(frames) < 3:
        return {"flicker": 0.0, "pop": 0.0}
    f = frames.astype(np.float32) / 255.0
    luma = f @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    means = luma.reshape(len(luma), -1).mean(1)
    dm = np.abs(np.diff(means))
    # flicker: luma means that bounce up/down (second difference), not a smooth fade
    flick = float(np.abs(np.diff(means, 2)).mean()) * 10 if len(means) > 3 else float(dm.mean())
    diffs = np.abs(np.diff(luma, axis=0)).reshape(len(luma) - 1, -1).mean(1)
    med = float(np.median(diffs)) + 1e-4
    pop = float(diffs.max() - med)
    return {"flicker": round(flick, 4), "pop": round(pop, 4)}


@lru_cache(maxsize=1)
def _clip():
    try:
        import torch  # noqa: F401
        from transformers import CLIPModel, CLIPProcessor

        name = os.environ.get("XENO_QA_CLIP", "openai/clip-vit-base-patch32")
        return CLIPModel.from_pretrained(name).eval(), CLIPProcessor.from_pretrained(name)
    except Exception:
        return None


def semantic(frames: np.ndarray, good: str) -> dict | None:
    got = _clip()
    if got is None or frames is None or not len(frames):
        return None
    import torch

    model, proc = got
    idx = np.linspace(0, len(frames) - 1, num=min(5, len(frames))).astype(int)
    texts = [good, *FAIL_PROMPTS]
    with torch.no_grad():
        inp = proc(text=texts, images=[frames[i] for i in idx], return_tensors="pt", padding=True)
        probs = model(**inp).logits_per_image.softmax(-1).mean(0).tolist()
    worst = int(np.argmax(probs[1:])) + 1
    return {"good": round(probs[0], 3), "worst": texts[worst], "worst_p": round(probs[worst], 3),
            "margin": round(probs[0] - probs[worst], 3)}


def planet_spots(frame: np.ndarray) -> int:
    """Saturated red storm ovals on a planet disk. A real Jupiter shows at most one
    (the Great Red Spot is pale in true colour); painted ones often grow two or more."""
    f = frame.astype(np.float32) / 255.0
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    mx, mn = f.max(-1), f.min(-1)
    disk = mx > 0.16
    sat = np.where(mx > 0, (mx - mn) / (mx + 1e-6), 0)
    red = disk & (r >= mx - 1e-6) & (g < r * 0.75) & (b < r * 0.75) & (sat > 0.35) & (mx > 0.24)
    if red.sum() == 0:
        return 0
    try:
        import cv2  # type: ignore

        n, _, stats, _ = cv2.connectedComponentsWithStats(red.astype(np.uint8))
        areas = stats[1:, 4]
    except Exception:
        areas = _component_areas(red)
    return int((np.asarray(areas) > 0.002 * (disk.sum() + 1)).sum())


def _component_areas(mask: np.ndarray) -> list[int]:
    """4-connected component sizes without OpenCV (masks here are small)."""
    seen = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    out = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack, n = [(y, x)], 0
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            n += 1
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        out.append(n)
    return out


def planet_check(frames: np.ndarray, subject: str) -> list[str]:
    """Duplicate-feature check for real subjects (see anchors.py)."""
    if subject != "jupiter" or frames is None or not len(frames):
        return []
    idx = sorted({0, len(frames) // 2, len(frames) - 1})
    worst = max(planet_spots(frames[i]) for i in idx)
    return [f"duplicated storm spots ({worst})"] if worst > 1 else []


def check(frames: np.ndarray, good: str = "a clean photoreal single sculptural object", subject: str = "") -> dict:
    t = temporal(frames)
    reasons = planet_check(frames, subject)
    if t["flicker"] > FLICKER_MAX:
        reasons.append(f"flicker {t['flicker']:.3f}")
    if t["pop"] > POP_MAX:
        reasons.append(f"pop {t['pop']:.3f}")
    s = semantic(frames, good) if os.environ.get("XENO_QA_CLIP_OFF") != "1" else None
    if s and s["margin"] < CLIP_MARGIN:
        reasons.append(f"looks like: {s['worst']}")
    score = 100 - 300 * max(0.0, t["flicker"] - 0.02) - 150 * max(0.0, t["pop"] - 0.05)
    if s:
        score = 0.6 * score + 40 * max(0.0, min(1.0, s["good"] * 2))
    return {"ok": not reasons, "score": round(max(0.0, score), 1), "reasons": reasons, **t, "clip": s}
