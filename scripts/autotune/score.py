"""Cheap local quality scores for one morph clip (no GPU, no network after the first CLIP fetch).

Runs under ComfyUI's own venv (it has torch, transformers and OpenCV); the
autotune runner talks to it as a worker over stdin/stdout JSON lines:

    python score.py --worker                     # one JSON request per line
    python score.py clip.mp4 [--a A.jpg --b B.jpg --na "sand dollar" --nb "manta ray"]

Every metric compares the middle of the morph with the two guide stills, so a
dark vibe is not punished for being dark; only the morph getting darker, hazier,
noisier or jumpier than its own endpoints is. Without stills, the first and
last frames stand in for them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

W, H = 512, 288
CLIP_ID = os.environ.get("XENO_SCORE_CLIP", "openai/clip-vit-base-patch32")
WEIGHTS = {  # sum 1.0
    "exposure": 0.12, "contrast": 0.10, "haze": 0.14, "crosshatch": 0.16,
    "smooth": 0.14, "ends": 0.08, "clip_object": 0.14, "clip_quality": 0.12,
}
GOOD = ["a sharp, clean, high quality studio photo of a glossy sculptural object"]
BAD = ["a blurry, hazy, smeared, low quality image",
       "a noisy image covered in crosshatch lines and digital artifacts",
       "a dark, murky, underexposed photo"]


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def read_frames(path: str) -> np.ndarray:
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if f.shape[1] != W or f.shape[0] != H:
            f = cv2.resize(f, (W, H), interpolation=cv2.INTER_AREA)
        frames.append(f)
    cap.release()
    if not frames:
        raise ValueError(f"no frames in {path}")
    return np.stack(frames)  # N,H,W,3 BGR uint8


def read_still(path: str) -> np.ndarray:
    im = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    return cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)


_R = None


def _radius() -> np.ndarray:
    global _R
    if _R is None:
        fy = np.fft.fftfreq(H)[:, None] * 2
        fx = np.fft.fftfreq(W)[None, :] * 2
        _R = np.sqrt(fx ** 2 + fy ** 2)  # 1.0 = Nyquist on an axis
    return _R


_WIN = np.outer(np.hanning(H), np.hanning(W)).astype(np.float32)


def spectrum(img: np.ndarray) -> dict:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    g = (g - g.mean()) * _WIN
    p = np.abs(np.fft.fft2(g)) ** 2
    r = _radius()
    low = p[(r > 0.02) & (r <= 0.10)].sum()
    mid = p[(r > 0.10) & (r <= 0.35)].sum()
    hi_mask = (r > 0.35) & (r <= 0.95)
    hi = p[hi_mask].sum()
    hv = np.log(p[hi_mask] + 1e-6)
    peaks = float(np.percentile(hv, 99.9) - np.median(hv))  # regular texture -> sharp spectral peaks
    return {"low": float(low), "mid": float(mid), "hi": float(hi), "peaks": peaks}


def dark_channel(img: np.ndarray) -> float:
    dc = cv2.erode(img.min(axis=2), np.ones((15, 15), np.uint8))
    return float(dc.mean())


def frame_stats(img: np.ndarray) -> dict:
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    s = spectrum(img)
    return {"luma": float(g.mean()), "std": float(g.std()), "dc": dark_channel(img),
            "lap": float(cv2.Laplacian(g, cv2.CV_32F).var()),
            "hf_ratio": s["hi"] / (s["mid"] + 1e-6), "detail": s["mid"] / (s["low"] + 1e-6),
            "peaks": s["peaks"]}


def _avg(stats: list[dict]) -> dict:
    return {k: float(np.mean([s[k] for s in stats])) for k in stats[0]}


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    a = cv2.resize(a, (128, 72), interpolation=cv2.INTER_AREA).astype(np.float32)
    b = cv2.resize(b, (128, 72), interpolation=cv2.INTER_AREA).astype(np.float32)
    mse = float(((a - b) ** 2).mean())
    return 99.0 if mse < 1e-6 else 10 * np.log10(255 ** 2 / mse)


class Clip:
    def __init__(self):
        self.model = None

    def load(self):
        if self.model is None:
            import torch
            from transformers import CLIPModel, CLIPProcessor
            torch.set_num_threads(int(os.environ.get("XENO_SCORE_THREADS", "4")))
            self.torch = torch
            self.model = CLIPModel.from_pretrained(CLIP_ID).eval()
            self.proc = CLIPProcessor.from_pretrained(CLIP_ID)
        return self

    def probs(self, frames_bgr: list[np.ndarray], texts: list[str]) -> np.ndarray:
        rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames_bgr]
        inp = self.proc(text=texts, images=rgb, return_tensors="pt", padding=True)
        with self.torch.no_grad():
            out = self.model(**inp)
        return out.logits_per_image.softmax(dim=-1).numpy()


CLIP = Clip()


def score(clip: str, a: str | None = None, b: str | None = None, na: str | None = None,
          nb: str | None = None, use_clip: bool = True) -> dict:
    t0 = time.time()
    fr = read_frames(clip)
    n = len(fr)
    sa = read_still(a) if a else fr[0]
    sb = read_still(b) if b else fr[-1]
    lo, hi = int(n * 0.2), max(int(n * 0.8), int(n * 0.2) + 1)
    mid_idx = np.linspace(lo, hi - 1, 9).astype(int)
    mid = _avg([frame_stats(fr[i]) for i in mid_idx])
    # Reference = the clip's own first and last frames (the guided endpoints), so the
    # codec and the decode treat both sides alike; the stills only check the endpoints.
    st = _avg([frame_stats(fr[min(1, n - 1)]), frame_stats(fr[max(n - 2, 0)])])

    # temporal
    small = np.stack([cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (128, 72), interpolation=cv2.INTER_AREA)
                      for f in fr]).astype(np.float32)
    d = np.abs(np.diff(small, axis=0)).mean(axis=(1, 2)) if n > 1 else np.zeros(1)
    pop = float(d.max() / (np.median(d) + 0.5))
    lm = small.mean(axis=(1, 2))
    jitter = float(np.abs(np.diff(lm, 2)).mean()) if n > 2 else 0.0

    m = {
        "frames": n,
        "luma_mid": mid["luma"], "luma_still": st["luma"],
        "contrast_ratio": mid["std"] / (st["std"] + 1e-6),
        "detail_ratio": mid["detail"] / (st["detail"] + 1e-6),
        "lap_ratio": mid["lap"] / (st["lap"] + 1e-6),
        "haze_dc": mid["dc"] - st["dc"],
        "hf_ratio": mid["hf_ratio"] / (st["hf_ratio"] + 1e-9),
        "peaks_delta": mid["peaks"] - st["peaks"],
        "pop": pop, "jitter": jitter,
        "psnr_ends": (psnr(fr[0], sa) + psnr(fr[-1], sb)) / 2,
    }
    s = {}
    dark_drop = max(0.0, 0.9 * m["luma_still"] - m["luma_mid"])
    s["exposure"] = _clip01(1 - dark_drop / max(20.0, 0.5 * m["luma_still"])) * _clip01((m["luma_mid"] - 18) / 30)
    s["contrast"] = _clip01(m["contrast_ratio"] / 0.85)
    s["haze"] = _clip01(m["detail_ratio"] / 0.7) * _clip01(1 - max(0.0, m["haze_dc"]) / 40)
    s["crosshatch"] = _clip01(1 - (m["hf_ratio"] - 1.2) / 1.5) * _clip01(1 - max(0.0, m["peaks_delta"] - 0.5) / 2.5)
    s["smooth"] = _clip01(1 - (pop - 3) / 7) * _clip01(1 - jitter / 3)
    s["ends"] = _clip01((m["psnr_ends"] - 14) / 10)

    if use_clip:
        c = CLIP.load()
        pick = [fr[i] for i in np.linspace(lo, hi - 1, 5).astype(int)]
        q = c.probs(pick, GOOD + BAD)
        s["clip_quality"] = float(q[:, 0].mean())
        m["clip_quality_raw"] = s["clip_quality"]
        if na and nb:
            texts = [f"a photo of a {na}", f"a photo of a {nb}", "a photo of a shapeless blob",
                     "a photo of abstract noise", "a photo of two separate objects", "an empty backdrop"]
            p = c.probs(pick, texts)
            s["clip_object"] = float(p[:, :2].sum(axis=1).mean())
        else:
            s["clip_object"] = s["clip_quality"]
    w = {k: v for k, v in WEIGHTS.items() if k in s}
    total = 100 * sum(s[k] * w[k] for k in w) / sum(w.values())
    return {"score": round(total, 2), "sub": {k: round(v, 3) for k, v in s.items()},
            "metrics": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()},
            "score_s": round(time.time() - t0, 2)}


def worker():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = score(req["clip"], req.get("a"), req.get("b"), req.get("na"), req.get("nb"),
                        req.get("use_clip", True))
            res["ok"] = True
        except Exception as exc:  # report and keep serving
            res = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        res["id"] = req.get("id") if isinstance(req, dict) else None
        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip", nargs="*")
    ap.add_argument("--worker", action="store_true")
    ap.add_argument("--a"); ap.add_argument("--b"); ap.add_argument("--na"); ap.add_argument("--nb")
    ap.add_argument("--no-clip", action="store_true")
    o = ap.parse_args()
    if o.worker:
        worker()
    else:
        for c in o.clip:
            r = score(c, o.a, o.b, o.na, o.nb, not o.no_clip)
            print(json.dumps({"clip": os.path.basename(c), **r}))
