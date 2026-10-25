"""Beat-reactive finishing for Simple mode: reframe, beat FX, overlay, end card, 15 s hook.

Everything here is free CPU post-processing (numpy + ffmpeg), so it runs the same on
the open-weights path and on any other source of clips. Ported from the demo1 dense
cut script that made the Facebook demo:

* kick pulse      the frame scales up a few percent on each kick
* edge flash      transients light the edges, alternating teal and violet each beat
* bloom           big punches from the cut plan add a soft glow
* loudness lift   overall exposure follows the song's RMS

Aspect: 16:9 is the render (Final 9:16 can also render natively in portrait, see
final_tier; then ``size`` is the portrait output and the crop below is a no-op).
9:16 and 1:1 crop each shot around the morph's centre
(the brightness-weighted centre of mass, which is the object on the black or plain
backgrounds the vibes use), eased between the shot's first and last frame so the
crop follows the object as it transforms.
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

try:  # OpenCV is a dependency since 0.3.0; the numpy paths below stay as the fallback
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

log = logging.getLogger("xenoform.beatfx")

FPS = 24
ASPECTS = ("16:9", "9:16", "1:1")
TEAL = np.array([90, 225, 215], np.float32)
VIOLET = np.array([190, 110, 255], np.float32)


def _strip_scheme(url: str) -> str:
    url = url.strip()
    for scheme in ("https://", "http://"):
        if url.lower().startswith(scheme):
            url = url[len(scheme):]
    return url.rstrip("/")


def _pyproject_repo_url() -> str:
    """[project.urls] Repository from the checkout's pyproject.toml, else the installed package metadata."""
    try:
        import tomllib

        pp = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pp.is_file():
            with pp.open("rb") as fh:
                urls = tomllib.load(fh).get("project", {}).get("urls", {})
            return str(urls.get("Repository") or "")
    except Exception:
        pass
    try:
        from importlib.metadata import metadata

        for line in metadata("xenoform").get_all("Project-URL") or []:
            label, _, url = line.partition(",")
            if label.strip().lower() == "repository":
                return url.strip()
    except Exception:
        pass
    return ""


def repo_url() -> str:
    """The end card's repo line, without the scheme: ``XENO_REPO_URL`` when set, else the pyproject
    ``[project.urls] Repository`` unless it is still the PLACEHOLDER, else "" (the card omits the line)."""
    env = os.environ.get("XENO_REPO_URL", "").strip()
    if env:
        return _strip_scheme(env)
    url = _pyproject_repo_url()
    if not url or "PLACEHOLDER" in url.upper():
        return ""
    return _strip_scheme(url)



def out_size(aspect: str, quality: str = "draft") -> tuple[int, int]:
    """Output frame size for an aspect. Even numbers only (yuv420p)."""
    long = 1280 if quality == "final" else 768
    short = 720 if quality == "final" else 432
    if aspect == "9:16":
        return short, long
    if aspect == "1:1":
        return short, short
    return long, short


def norm_aspect(value) -> str:
    text = str(value or "16:9").strip().replace("x", ":").replace("/", ":")
    return {"vertical": "9:16", "square": "1:1", "wide": "16:9"}.get(text, text if text in ASPECTS else "16:9")


# ------------------------------------------------------------------ envelopes


def load_audio(path: Path, sr: int = 22050, offset: float = 0.0, duration: float | None = None) -> np.ndarray:
    """Mono float32 samples from any file ffmpeg reads (wav, mp3, or the audio track of an mp4)."""
    cmd = [_ffmpeg(), "-v", "error"]
    if offset:
        cmd += ["-ss", f"{offset:.3f}"]
    cmd += ["-i", str(path)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def envelopes(audio_path: Path | None, frames: int, start: float = 0.0, fps: int | None = None) -> dict[str, np.ndarray]:
    """kick, transient and loudness, one value per output frame, 0..1. ``fps`` None: the module FPS (house: 24)."""
    fps = int(fps or FPS)
    zero = np.zeros(frames, np.float32)
    if audio_path is None or not Path(audio_path).is_file() or frames <= 0:
        return {"kick": zero, "trans": zero, "loud": zero + 0.6}
    import librosa

    sr = 22050
    y = load_audio(Path(audio_path), sr, float(start), frames / fps + 0.5)
    if len(y) < 4096:
        return {"kick": zero, "trans": zero, "loud": zero + 0.6}
    hop = 512
    spec = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    t_spec = librosa.frames_to_time(np.arange(spec.shape[1]), sr=sr, hop_length=hop)
    tf = np.arange(frames) / fps

    def flux(band) -> np.ndarray:
        d = np.maximum(0, np.diff(np.log1p(spec[band] * 50), axis=1)).sum(0)
        d = np.concatenate([[0.0], d])
        return d / (np.percentile(d, 99.5) + 1e-9)

    def env(x: np.ndarray, decay_s: float) -> np.ndarray:
        x = np.clip(np.interp(tf, t_spec, x), 0, 1.5)
        out = np.zeros_like(x)
        k = math.exp(-1 / (decay_s * fps))
        for i, v in enumerate(x):
            out[i] = max(v, (out[i - 1] if i else 0.0) * k)
        return out

    kick = np.clip((env(flux(freqs < 150), 0.12) - 0.25) / 0.75, 0, 1)
    trans = np.clip((env(flux(freqs >= 2500), 0.08) - 0.3) / 0.7, 0, 1)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    loud = np.interp(tf, t_spec, (rms / (rms.max() + 1e-9)) ** 0.7)
    return {"kick": kick.astype(np.float32), "trans": trans.astype(np.float32), "loud": loud.astype(np.float32)}


# ------------------------------------------------------------------ reframing


def centroid(frame: np.ndarray) -> tuple[float, float]:
    """Brightness-weighted centre of the subject, as fractions of width and height."""
    g = frame.astype(np.float32).mean(axis=2)
    small = g[::4, ::4]
    base = np.percentile(small, 40)
    w = np.clip(small - base, 0, None) ** 1.5
    total = float(w.sum())
    if total <= 1e-6:
        return 0.5, 0.5
    ys, xs = np.indices(w.shape)
    return float((w * xs).sum() / total / max(w.shape[1] - 1, 1)), float((w * ys).sum() / total / max(w.shape[0] - 1, 1))


def crop_box(src_w: int, src_h: int, aspect: str, cx: float, cy: float) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the largest window of ``aspect`` centred as near (cx, cy) as fits."""
    a = norm_aspect(aspect)
    ratio = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}[a]
    if src_w / src_h > ratio:
        h = src_h
        w = int(round(h * ratio))
    else:
        w = src_w
        h = int(round(w / ratio))
    x = int(round(cx * src_w - w / 2))
    y = int(round(cy * src_h - h / 2))
    return max(0, min(src_w - w, x)), max(0, min(src_h - h, y)), w, h


def shot_centres(frames: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]]:
    """Subject centre at the start and end of a clip (averaged over a few frames each)."""
    n = len(frames)
    if n == 0:
        return (0.5, 0.5), (0.5, 0.5)
    k = max(1, n // 6)
    head = np.mean([centroid(f) for f in frames[:k:max(1, k // 3)]], axis=0)
    tail = np.mean([centroid(f) for f in frames[-k::max(1, k // 3)]], axis=0)
    return (float(head[0]), float(head[1])), (float(tail[0]), float(tail[1]))


def resize(frame: np.ndarray, w: int, h: int) -> np.ndarray:
    """Bilinear resize, numpy only."""
    sh, sw = frame.shape[:2]
    if (sw, sh) == (w, h):
        return frame
    return np.clip(_resize_f(frame, w, h), 0, 255).astype(np.uint8)


def _resize_f(frame: np.ndarray, w: int, h: int) -> np.ndarray:
    """Bilinear resize to float32 (no clipping: also used for signed deltas)."""
    sh, sw = frame.shape[:2]
    if (sw, sh) == (w, h):
        return frame.astype(np.float32)
    if cv2 is not None:  # 20-40x the numpy path; area when shrinking, bilinear when growing
        inter = cv2.INTER_AREA if w * h < sw * sh else cv2.INTER_LINEAR
        out = cv2.resize(np.ascontiguousarray(frame, dtype=np.float32), (int(w), int(h)), interpolation=inter)
        return out.reshape(h, w, *frame.shape[2:]) if frame.ndim == 3 and out.ndim == 2 else out
    if frame.ndim == 3 and sh * sw > 300_000:  # big frames: the C implementation when scipy is around
        try:
            from scipy.ndimage import zoom

            return zoom(frame.astype(np.float32), (h / sh, w / sw, 1), order=1).astype(np.float32)
        except ImportError:  # pragma: no cover
            pass
    ys = (np.arange(h) + 0.5) * sh / h - 0.5
    xs = (np.arange(w) + 0.5) * sw / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, sh - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, sw - 1)
    y1 = np.clip(y0 + 1, 0, sh - 1)
    x1 = np.clip(x0 + 1, 0, sw - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None, None]
    fx = np.clip(xs - x0, 0, 1)[None, :, None]
    f = frame.astype(np.float32)
    top = f[y0][:, x0] * (1 - fx) + f[y0][:, x1] * fx
    bot = f[y1][:, x0] * (1 - fx) + f[y1][:, x1] * fx
    return (top * (1 - fy) + bot * fy).astype(np.float32)


def reframe(frame: np.ndarray, aspect: str, centre: tuple[float, float], w: int, h: int) -> np.ndarray:
    x, y, cw, ch = crop_box(frame.shape[1], frame.shape[0], aspect, centre[0], centre[1])
    return resize(frame[y:y + ch, x:x + cw], w, h)


# ------------------------------------------------------------------ beat FX


def _blur(img: np.ndarray, factor: int = 8) -> np.ndarray:
    h, w = img.shape[:2]
    sh, sw = max(1, h // factor), max(1, w // factor)
    if cv2 is not None:
        f = np.ascontiguousarray(img, dtype=np.float32)
        small = cv2.resize(f, (sw, sh), interpolation=cv2.INTER_AREA)
        out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
        return out.reshape(h, w, *img.shape[2:]) if img.ndim == 3 and out.ndim == 2 else out
    small = img[: sh * factor, : sw * factor].reshape(sh, factor, sw, factor, -1).mean(axis=(1, 3))
    return resize(np.clip(small, 0, 255).astype(np.uint8), w, h).astype(np.float32)


def _edges(img: np.ndarray) -> np.ndarray:
    g = img.mean(axis=2)
    if cv2 is not None:  # Sobel 3x3 is 4x the central difference the numpy path takes
        g32 = np.ascontiguousarray(g, dtype=np.float32)
        gx = cv2.Sobel(g32, cv2.CV_32F, 1, 0, ksize=3) * 0.25
        gy = cv2.Sobel(g32, cv2.CV_32F, 0, 1, ksize=3) * 0.25
        return np.clip(np.hypot(gx, gy) / 90.0, 0, 1)[..., None]
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1] = g[2:] - g[:-2]
    return np.clip(np.hypot(gx, gy) / 90.0, 0, 1)[..., None]


def _zoom(img: np.ndarray, scale: float) -> np.ndarray:
    if scale <= 1.001:
        return img
    h, w = img.shape[:2]
    cw, ch = int(round(w / scale)), int(round(h / scale))
    x, y = (w - cw) // 2, (h - ch) // 2
    return resize(img[y:y + ch, x:x + cw].astype(np.uint8), w, h).astype(np.float32)


def beat_fx(frame: np.ndarray, *, kick: float, trans: float, punch: float, loud: float, beat_index: int,
            zoom_scale: float = 1.0, intensity: float = 1.0, wobble: float = 0.0, t: float = 0.0,
            bloom: float = 1.0) -> np.ndarray:
    """The demo1 look on one frame. ``zoom_scale`` < 1 softens the zoom (vertical uses 0.5).

    ``intensity`` (0..1, the shot's fx_intensity) scales every beat effect; ``wobble`` (0..1)
    adds a subtle sideways sway of up to 2 % of the width, driven by the kick; ``bloom`` scales
    the punch glow (the Simple ``glow`` macro: 0.6 + glow, 1.0 at the neutral 0.4).
    """
    intensity = max(0.0, min(1.0, float(intensity)))
    kick, trans, punch = kick * intensity, trans * intensity, punch * intensity
    img = frame.astype(np.float32)
    if wobble > 0:
        shift = int(round(float(wobble) * 0.02 * img.shape[1] * math.sin(2 * math.pi * 2.0 * t) * (0.5 + 0.5 * min(1.0, kick * 4))))
        if shift:
            img = np.roll(img, shift, axis=1)
    s = 1.0 + (0.035 * kick + 0.09 * punch) * zoom_scale
    img = _zoom(img, s)
    e = trans * 0.9 + punch * 0.8
    if e > 0.02:
        col = TEAL if beat_index % 2 else VIOLET
        img = img + _edges(img) * col * e
    if punch > 0.05:
        img = img + _blur(img) * (0.55 * punch * max(0.0, float(bloom)))
    img = img * (1.0 + (0.12 * loud - 0.08) * intensity)  # the loudness ride is a beat effect too: none at Intensity 0
    return np.clip(img, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ house look (dance_fx + stem_orbit)


def house_profile(house: dict | None = None) -> dict:
    """``house`` when given, else config.house() (demo_house merged into the config defaults)."""
    if isinstance(house, dict) and house:
        return house
    from xenoform.config import house as _house

    return _house()


def mix_stem_env(env: dict | None, beats: Iterable[float] = (), fps: int | None = None) -> dict:
    """A 4-role stem envelope (``stem_react`` format) from the mix when no stems were split: the kick
    flux drives bass, the transient flux drives drums, loudness drives other, vocals stay 0 and the beat
    grid is the drum-hit list."""
    fps = int(fps or FPS)
    env = env or {}
    kick = np.asarray(env.get("kick", []), np.float32); trans = np.asarray(env.get("trans", []), np.float32)
    loud = np.asarray(env.get("loud", []), np.float32)
    n = len(kick)
    return {"fps": fps, "frames": n, "engine": "mix", "stems": [], "roles": {},
            "bass": kick.tolist(), "drums": trans.tolist(), "other": (loud * 0.8).tolist(), "vocals": [0.0] * n,
            "drum_strong": [round(float(b), 3) for b in beats]}


def resolve_dance_preset(choice, vibe: str | None = None, house: dict | None = None) -> str:
    """The Simple ``dance_fx`` key -> "off", "house" (per-role house presets) or a preset name.
    "auto": the vibe's configs/vibes.json ``fx_defaults.dance_fx`` when present, else the house vj preset."""
    from xenoform import dance_fx as D

    text = str(choice if choice is not None else "auto").strip().lower()
    if text in ("", "off", "none", "false", "0", "no"):
        return "off"
    if text in ("auto", "house", "default", "true", "on", "1", "yes"):
        if text == "auto" and vibe:
            try:
                from xenoform import vibes as _vibes

                row = next((r for r in _vibes.extended() if r.get("id") == vibe), None)
                pick = str(((row or {}).get("fx_defaults") or {}).get("dance_fx") or "").strip().lower()
                if pick in D.PRESETS or pick == "off":  # a print vibe may name "off": a page is a page, no grade
                    return pick
            except Exception:
                pass
        return "house"
    if text not in D.PRESETS:
        raise ValueError(f"unknown dance_fx preset {text!r}; one of auto, off, {', '.join(D.PRESETS)}")
    return text


LOOK_SHORT_SIDE = 432        # dance_fx working size (short side) with OpenCV: Final 1080x1920 runs at 540x960
LOOK_SHORT_SIDE_NUMPY = 240  # without OpenCV the scipy path is slower: 432x768 works at 216x384, 1080x1920 at 270x480
# The look is low-frequency (glows, grades, trails), so Draft runs it at a quarter of the frame (540x960 -> 270x480)
# and Final at a ninth (1080x1920 -> 360x640); the structure stays at full resolution (see _apply_at_working_size).
LOOK_CAP = {"draft": 270, "final": 360}


def _apply_at_working_size(fx, frame: np.ndarray, d: dict, cap: int) -> np.ndarray:
    """Run a colour-and-light pass at an integer fraction of the frame size and add the delta back at full
    size. The passes are low-frequency (glows, washes, grades, trails), so the look is the same while the
    structure (luma edges) stays at full resolution; Final 1080x1920 then costs about what the draft size does."""
    h, w = frame.shape[:2]
    short = min(h, w)
    k = int(round(short / cap)) if short > cap * 1.25 else 1
    if k <= 1:
        return fx.apply(frame, d)
    hh, ww = h // k * k, w // k * k
    lo = frame[:hh, :ww].reshape(hh // k, k, ww // k, k, 3).mean(axis=(1, 3)).astype(np.float32)
    delta = fx.apply(np.clip(lo, 0, 255).astype(np.uint8), d).astype(np.float32) - lo
    up = np.repeat(np.repeat(delta, k, axis=0), k, axis=1)
    try:  # smooth the k x k blocks (a separable box = bilinear-ish), C speed when scipy is around
        from scipy.ndimage import uniform_filter1d

        up = uniform_filter1d(uniform_filter1d(up, k, axis=0, mode="nearest"), k, axis=1, mode="nearest")
    except ImportError:  # pragma: no cover
        pass
    if (hh, ww) != (h, w):
        up = np.pad(up, ((0, h - hh), (0, w - ww), (0, 0)), mode="edge")
    return np.clip(frame.astype(np.float32) + up, 0, 255).astype(np.uint8)


def bloom_gain(glow) -> float:
    """The beat-FX punch bloom for the Glow knob: 0 is none at all (the look's halation is 0 there too), 0.4 the
    house as written, 1 is 1.6 times it."""
    return 1.6 * float(np.clip(float(glow if glow is not None else 0.4), 0.0, 1.0))


ORBIT_YAW = 14.0
ORBIT_DRIFT_LOOK_OFF = 0.15  # the orbit's least swing with the look off: a held still must not be four identical frames  # degrees of yaw at Chaos 0.5; the house profile's 28 is reached at Chaos 1


class LookPass:
    """The house look on top of the beat FX, per shot: stem_orbit (a rigid camera orbit; needs OpenCV, a
    logged no-op without it) and then dance_fx (colour and light only). ``dance_fx`` is "off", "house"
    (intro / vj / into_card presets from the house profile per shot) or a preset name. ``macros`` (the
    Simple knobs) feed echo_decay (speed), halation / depth bloom (glow) and per-stem gains (stems)."""

    def __init__(self, *, dance_fx: str | None = None, stem_orbit: bool | None = None, stem_env: dict | None = None,
                 macros: dict | None = None, house: dict | None = None, beats: Iterable[float] = (), fps: int | None = None,
                 shots: int = 1, end_card: bool = False, seed: int = 0, palette_image: str | None = None,
                 adaptive: bool = False, quality: str = "draft"):
        self.house = house_profile(house)
        self.cap = LOOK_CAP.get(str(quality or "draft"), LOOK_CAP["draft"])
        # Auto: the preset's colours follow the vibe's own palette (palette_image is one of its stills).
        self.adaptive = bool(adaptive)
        self.tints: dict = {}
        if self.adaptive and palette_image:
            from xenoform import dance_fx as D

            self.tints = D.palette_tints(palette_image)
        self.fps = int(fps or (self.house.get("format") or {}).get("fps") or FPS)
        self.beats = [float(b) for b in beats]
        self.env = stem_env or {}
        self.macros = macros or {}
        self.mode = str(dance_fx or "off")
        self.orbit = bool(stem_orbit)
        self.shots = max(1, int(shots)); self.end_card = bool(end_card); self.seed = int(seed)
        self.notes: list[str] = []
        self.seconds = 0.0; self.frames = 0
        self.fx = None; self.plan = None; self.roles: list[str] = []
        self._orbit_ok = self.orbit
        if self.orbit:
            try:
                from xenoform import stem_orbit as O

                self._orbit_ok = O.cv2 is not None
            except Exception:
                self._orbit_ok = False
            if not self._orbit_ok:
                self.notes.append("stem_orbit skipped: OpenCV (cv2) is not installed; frames pass through unchanged")
                log.warning("stem_orbit skipped: OpenCV (cv2) is not installed")

    @property
    def active(self) -> bool:
        return self.mode != "off" or self._orbit_ok

    def gains(self) -> dict | None:
        g = self.macros.get("stems")
        return g if isinstance(g, dict) and g else None

    def role_for(self, si: int) -> str:
        if self.end_card and si == self.shots - 1:
            return "into_card"
        return "intro" if si == 0 else "vj"

    def start_shot(self, si: int, n_frames: int, t0: float) -> None:
        """New dance_fx state (the echo is per shot) and the orbit plan for this shot."""
        self.fx = None; self.plan = None; self.n = int(n_frames); self.t0 = float(t0)
        if self.mode != "off":
            from xenoform import dance_fx as D

            role = self.role_for(si)
            preset = None if self.mode == "house" else self.mode
            fx = D.DanceFX(preset, seed=self.seed + si, role=role, house=self.house.get("dance_fx"))
            if self.tints:
                fx.p.update(self.tints)  # the vibe's palette, not the preset's fixed cast
            speed = float(self.macros.get("speed", 0.5)); glow = float(self.macros.get("glow", 0.4))
            if fx.p.get("echo", 0) > 0:  # speed: faster cuts, shorter trails
                fx.p["echo_decay"] = float(np.clip(fx.p.get("echo_decay", 0.70) - 0.24 * (speed - 0.5), 0.5, 0.95))
            gain = glow / 0.4  # glow: 0 is no halation or bloom at all, 0.4 the preset as written, 1 two and a half times
            for key in ("halation", "depth_bloom", "light_leak"):
                if fx.p.get(key, 0) > 0:
                    fx.p[key] = float(min(1.5, fx.p[key] * gain))
            self.fx = fx; self.roles.append(f"{si}:{role}:{fx.preset}")
        if self._orbit_ok and self.n > 0:
            from xenoform import stem_orbit as O

            # Chaos: 0 is a camera that does not move, 0.3 (the default) a gentle drift, 1 a swing twice the old default.
            # The old 28 degrees at every setting read as a handycam (Tys, 25 Oct), with the zoom that hides the edges.
            swing = 2.0 * float(np.clip(float(self.macros.get("chaos", 0.3) or 0.0), 0.0, 1.0))
            if self.mode == "off":  # with no look the orbit is all that keeps a held still alive: a slow drift at least
                swing = max(swing, ORBIT_DRIFT_LOOK_OFF)
            if swing < 0.05:
                self.plan = None
            else:
                self.plan = O.plan(self.env, self.t0, self.n, fps=self.fps, max_yaw=ORBIT_YAW * swing)

    def frame(self, frame: np.ndarray, k: int, t: float) -> np.ndarray:
        """Output frame ``k`` of the current shot at song time ``t``."""
        if self.fx is None and self.plan is None:
            return frame
        from xenoform import dance_fx as D

        t_start = time.perf_counter()
        if self.plan is not None and k < self.n:
            from xenoform import stem_orbit as O

            frame = O.apply(frame, float(self.plan["yaw"][k]), float(self.plan["pitch"][k]), float(self.plan["roll"][k]))
        if self.fx is not None:
            ramp = self.fx.invert_floor_ramp_frames
            if ramp > 0 and k >= self.n - ramp:
                self.fx.p["invert_floor"] = float(np.clip((k - (self.n - ramp) + 1) / ramp, 0.0, 1.0))
            d = D.drive_from_env(self.env, t, self.beats, self.gains())
            frame = _apply_at_working_size(self.fx, frame, d, self.cap if D.cv2 is not None else LOOK_SHORT_SIDE_NUMPY)
        self.seconds += time.perf_counter() - t_start; self.frames += 1
        return frame

    def info(self) -> dict:
        return {"dance_fx": self.mode, "stem_orbit": bool(self._orbit_ok), "stem_orbit_requested": self.orbit,
                "stems": str(self.env.get("engine") or ("none" if not self.env else "?")), "roles": self.roles,
                "frames": self.frames, "seconds": round(self.seconds, 2), "notes": list(self.notes),
                "macros": {k: self.macros.get(k) for k in ("speed", "glow", "stems") if k in self.macros},
                "adaptive": self.adaptive, "tints": {k: list(v) for k, v in self.tints.items()} if self.tints else {}}


# ------------------------------------------------------------------ compositor


def _ffmpeg() -> str:
    from xenoform.cloud_morph import _ffmpeg as find

    return find()


def _conformed(clip: Path, out_path: Path) -> Path:
    """A clip at the project fps (guardrail lag_qa): mismatched clips are re-timed first."""
    try:
        from xenoform.post_qa import conform, probe

        got = probe(clip)["fps"]
        if got and abs(got - FPS) > 0.05:
            dest = Path(out_path).with_name(f"{Path(clip).stem}.{FPS}fps.mp4")
            if not dest.is_file():
                conform(clip, dest, FPS)
            return dest
    except Exception:
        pass
    return clip


def read_frames(path: Path) -> np.ndarray:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        w, h = (int(v) for v in probe.stdout.strip().split(",")[:2])
    except ValueError:
        w, h = 768, 432
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


LOOK_WORKERS_ENV = "XENO_LOOK_WORKERS"
PARALLEL_MIN_FRAMES = 480  # under 20 s of picture the pool's start-up costs more than it saves


def look_workers(total: int, heavy: bool = True) -> int:
    """How many processes ``compose`` spreads the shots over: ``XENO_LOOK_WORKERS`` when set, else up to six of the
    spare cores; one (the serial path) for short cuts or when neither the beat FX nor the look is on."""
    raw = os.environ.get(LOOK_WORKERS_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    if not heavy or int(total) < PARALLEL_MIN_FRAMES:
        return 1
    return max(1, min(6, (os.cpu_count() or 2) - 2))


def look_speedup(total: int) -> float:
    """How much faster the look pass runs with the workers ``look_workers`` would give a cut of ``total`` frames
    (measured 24 Oct 2026: six workers took a 720-frame 540x960 cut from 85 s to 30 s while a render ran alongside),
    for the plan estimate."""
    return max(1.0, min(3.0, 0.5 * look_workers(int(total), heavy=True)))


def _shot_frames(clip: Path, shot: dict, si: int, n0: int, total: int, *, aspect: str, w: int, h: int, fx: bool,
                 env: dict | None, beats: list, punch, zoom_scale: float, glow_gain: float, fps: int, look_kwargs: dict,
                 foreshadow: dict | None = None, boundary: dict | None = None) -> dict:
    """One shot's finished frames: reframed around the subject, the beat FX, then the house look. This is the
    work the compose loop used to do inline, as plain data in and out so it can run in a worker process: the
    look state is rebuilt here from ``look_kwargs`` and seeded per shot (``LookPass.start_shot``), so the
    frames are the same whichever process makes them. ``n0`` is the first output frame's index (song time)."""
    from xenoform.cloud_morph import shot_indices
    from xenoform.guardrails import shot_fx

    frames = read_frames(Path(clip))
    if len(frames) == 0:
        raise RuntimeError(f"Shot {si + 1} came back with no frames.")
    a, b = shot_centres(frames) if aspect != "16:9" else ((0.5, 0.5), (0.5, 0.5))
    idx = shot_indices(shot, len(frames))
    count = max(len(idx) - 1, 1)
    look = LookPass(**look_kwargs)
    look.start_shot(si, len(idx), n0 / fps)
    out = np.empty((len(idx), h, w, 3), dtype=np.uint8)
    n = int(n0)
    fs_level = 0.0  # the foreshadow layer's eased stem level, carried frame to frame within the shot
    for k, j in enumerate(idx):
        u = k / count
        u = u * u * (3 - 2 * u)
        c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
        frame = reframe(frames[j], aspect, c, w, h)
        if fx and env is not None:
            bi = int(np.searchsorted(beats, n / fps)) if beats else 0
            s_int, s_wob = shot_fx(shot)
            frame = beat_fx(frame, intensity=s_int, wobble=s_wob, t=n / fps,
                            kick=float(env["kick"][min(n, total - 1)]),
                            trans=float(env["trans"][min(n, total - 1)]),
                            punch=float(punch[n]) if n < len(punch) else 0.0,
                            loud=float(env["loud"][min(n, total - 1)]), beat_index=bi, zoom_scale=zoom_scale,
                            bloom=glow_gain)
        if foreshadow:
            # the next object arrives before its shot (foreshadow.treat), the amount riding the "other" stem (else the
            # beat) under the Intensity cap; across a hard cut the object that just left echoes out for a beat
            from xenoform import dance_fx as _D
            from xenoform import foreshadow as _F

            fs = foreshadow
            fcap = float(fs.get("cap") or 0.5)
            base = _F.ramp(k, len(idx), int(fs.get("lead") or 0)) if fs.get("target") is not None else 0.0
            echo = _F.echo_ramp(k, int(fs.get("echo") or 0)) if fs.get("prev") is not None else 0.0
            if base > 0 or echo > 0:
                if look.env:
                    d = _D.drive_from_env(look.env, n / fps, look.beats, look.gains())
                    raw_stem = float(d.get("other", 0.0)) if float(d.get("other", 0.0)) > 0.02 else float(d.get("beat", 0.0))
                else:
                    raw_stem = 0.6
                fs_level += (raw_stem - fs_level) * _F.FOLLOW  # eased: a spiky lane breathes the layer, it does not strobe it
                stem = fs_level
                pop = float(d.get("beat", 0.0)) if look.env else 0.0
                if base > 0:
                    tgt = reframe(fs["target"], aspect, c, w, h)
                    frame = _F.treat(frame, tgt, str(fs["mode"]), _F.amount(base, stem, fcap), tint=fs.get("tint") or (255, 255, 255),
                                     p=fs.get("params"), si=si, k=k, seed=int(fs.get("seed") or 0), pop=pop)
                if echo > 0:  # continues the tail it follows, so it rides the same eased stem instead of starting at the cap
                    prv = reframe(fs["prev"], aspect, c, w, h)
                    frame = _F.treat(frame, prv, str(fs["mode"]), _F.amount(1.0, stem, fcap) * echo,
                                     tint=fs.get("tint") or (255, 255, 255), p=fs.get("params"), si=si, k=k,
                                     seed=int(fs.get("seed") or 0))
        if boundary:
            # a boundary kind (boundary_fx: smear, strobe cut, wipe, chromatic rip): the window of the handoff, half in this
            # shot's head and half in the previous shot's tail, rides its stem and brings the second picture in here,
            # before the look, so the look grades the handoff as part of the picture
            from xenoform import boundary_fx as _B
            from xenoform import dance_fx as _D

            hit = _B.at(boundary, k, len(idx))
            if hit:
                half, u, j = hit
                bp = boundary.get("params") or {}
                lane = str(half.get("stem") or "drums")
                if look.env:
                    d = _D.drive_from_env(look.env, n / fps, look.beats, look.gains())
                    stem = float(d.get(lane, 0.0))
                    if stem < 0.02 and lane != "drums":
                        stem = float(d.get("drums", 0.0))  # a flat lane (no vocals, say) rides the drums instead
                else:
                    stem = 0.6
                oth = reframe(half["other"], aspect, c, w, h)
                frame = _B.treat(frame, oth, str(half["kind"]), u, amount=float(bp.get("amount", 0.7)), stem=stem, p=bp, j=j,
                                 seed=int(boundary.get("seed") or 0) * 7919 + int(half.get("index") or 0),
                                 variant=str(half.get("variant") or ""))
        frame = look.frame(frame, k, n / fps)
        if frame.shape[0] != h or frame.shape[1] != w:
            frame = resize(frame, w, h)
        out[k] = frame if frame.dtype == np.uint8 else np.clip(frame, 0, 255).astype(np.uint8)
        n += 1
    return {"frames": out, "centres": [a, b],
            "look": {"frames": look.frames, "seconds": look.seconds, "roles": list(look.roles), "notes": list(look.notes)}}


def _shot_results(clips: list, shots: list[dict], out_path: Path, workers: int, total: int, common: dict, fs: list | None = None,
                  bx: list | None = None):
    """Yields ``(si, result)`` in shot order: inline when ``workers`` is 1, else from a bounded window of worker
    processes (``workers + 2`` shots in flight, so a four-minute song never holds all its frames at once).
    Clips are conformed to the project fps here, in the parent, before any worker sees them."""
    starts, n0 = [], 0
    for shot in shots:
        starts.append(n0)
        n0 += int(shot["frames"])
    if workers <= 1:
        for si, (clip, shot) in enumerate(zip(clips, shots)):
            yield si, _shot_frames(_conformed(Path(clip), out_path), shot, si, starts[si], total, foreshadow=(fs[si] if fs else None),
                                   boundary=(bx[si] if bx else None), **common)
        return
    from collections import deque
    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=int(workers)) as pool:
        pending: deque = deque()
        nxt = 0

        def submit() -> None:
            nonlocal nxt
            clip = _conformed(Path(clips[nxt]), out_path)
            pending.append(pool.submit(_shot_frames, clip, shots[nxt], nxt, starts[nxt], total, foreshadow=(fs[nxt] if fs else None),
                                       boundary=(bx[nxt] if bx else None), **common))
            nxt += 1

        while nxt < len(shots) and len(pending) < int(workers) + 2:
            submit()
        si = 0
        while pending:
            result = pending.popleft().result()
            if nxt < len(shots):
                submit()
            yield si, result
            si += 1


def compose(clips: list[Path], shots: list[dict], audio_path: Path, out_path: Path, *, aspect: str = "16:9",
            quality: str = "draft", fx: bool = True, overlay: bool = False, beats: Iterable[float] = (),
            label: str | None = None, report: Callable[[str, float, str], None] | None = None,
            size: tuple[int, int] | None = None, fps: int | None = None, dance_fx: str | None = None,
            stem_orbit: bool | None = None, stem_env: dict | None = None, macros: dict | None = None,
            house: dict | None = None, end_card: bool = False, seed: int = 0, palette_image: str | None = None,
            adaptive: bool = False, transitions: list | None = None, foreshadow: str | None = None,
            boundary_fx: list | None = None) -> dict:
    """Retime every clip to its shot (speed, ease, hold, stutter, skip, reverse), reframe, add beat FX, mux.

    ``transitions``: one entry per shot, ``{"kind", "frames"}`` or None; a premium transition (transitions_fx)
    replaces the window centred on that shot's first frame (half from the previous shot's tail, half from
    this shot's head), so the frame count and the beat sync do not move.

    ``boundary_fx``: one entry per shot from ``boundary_fx.pick`` (a smear, strobe cut, wipe or chromatic rip at
    the boundary into that shot, with its window) or None. These run inside the look pass, before the house look,
    riding a stem; a boundary they take gets no premium window. ``foreshadow`` is the layer's mode ("" for off).

    ``size`` overrides the output frame size (native vertical Final: 1080x1920). Clips that
    already have the target aspect pass through whole; any other clip is cropped around its object.

    House look (see ``LookPass``): ``dance_fx`` "off" / "house" / a preset name, ``stem_orbit`` on/off,
    ``stem_env`` a ``stem_react`` envelope (else one is derived from the mix), ``macros`` the Simple knobs
    (speed -> echo decay, glow -> halation + beat-FX bloom, stems -> per-stem gains). ``fps`` None is the
    house format fps (24). ``end_card`` marks the last shot as the into_card role (inverted ramp).
    """
    from xenoform.cloud_morph import BeatOverlay, audio_envelope, punch_curve, shot_indices
    from xenoform.guardrails import shot_fx

    aspect = norm_aspect(aspect)
    house = house_profile(house)
    fps = int(fps or (house.get("format") or {}).get("fps") or FPS)
    w, h = size or out_size(aspect, quality)
    total = sum(int(s["frames"]) for s in shots)
    beats = [float(b) for b in beats]
    look = LookPass(dance_fx=dance_fx, stem_orbit=stem_orbit, stem_env=stem_env, macros=macros, house=house,
                    beats=beats, fps=fps, shots=len(shots), end_card=end_card, seed=seed, palette_image=palette_image,
                    adaptive=adaptive, quality=quality)
    env = envelopes(audio_path, total, fps=fps) if (fx or look.active) else None
    if look.active and not look.env:
        look.env = mix_stem_env(env, beats, fps)
    glow_gain = bloom_gain((macros or {}).get("glow", 0.4))  # the beat FX bloom: none at Glow 0, 1.6 at 1
    punch = punch_curve(shots)
    over = None
    if overlay:
        marks = [s["start"] for s in shots[1:]]
        over = BeatOverlay(w, h, total / fps, audio_envelope(audio_path, 0.0, total / fps, 512), beats, marks)
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".compose.mp4")
    cmd = [_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-i", str(audio_path), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart"]
    if label:
        cmd += ["-metadata", f"comment={label}"]
    cmd.append(str(tmp))
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    zoom_scale = 0.5 if aspect == "9:16" else 1.0
    centres = []
    trans = list(transitions or [])
    held: list[np.ndarray] = []  # the previous shot's last frames, withheld for the transition into the next shot
    used_transitions: list[str] = []
    t_intensity = float((house.get("transitions") or {}).get("intensity") or 0.5)

    def write(frame: np.ndarray) -> None:
        # ffmpeg reads fixed-size raw frames and silently drops everything after a short one, so a frame of
        # the wrong size (a slipped resize, a transition that returned a small picture) is corrected here
        if frame.shape[0] != h or frame.shape[1] != w:
            log.warning("compose: a %dx%d frame where %dx%d was expected; resized", frame.shape[1], frame.shape[0], w, h)
            frame = resize(frame, w, h)
        enc.stdin.write(np.ascontiguousarray(frame).tobytes())

    # The per-shot work runs in _shot_frames, here or in worker processes (look_workers): a full song's look pass
    # used to take 0.2 s a frame on one core, about nineteen minutes for four minutes of picture.
    common = dict(aspect=aspect, w=w, h=h, fx=fx, env=env, beats=beats, punch=punch, zoom_scale=zoom_scale,
                  glow_gain=glow_gain, fps=fps,
                  look_kwargs=dict(dance_fx=dance_fx, stem_orbit=stem_orbit, stem_env=look.env, macros=macros, house=house,
                                   beats=beats, fps=fps, shots=len(shots), end_card=end_card, seed=seed,
                                   palette_image=palette_image, adaptive=adaptive, quality=quality))
    workers = look_workers(total, heavy=bool(fx or look.active))
    if workers > 1:
        log.info("compose: %d shots over %d worker processes", len(shots), workers)
    # the foreshadow layer: the next object brought into each shot's tail (foreshadow.plan reads the edge frames here,
    # once each, and the entries travel to the workers as arrays); "" or None leaves it off
    from xenoform import dance_fx as _D
    from xenoform import foreshadow as _F

    fs_mode = str(foreshadow or "").strip().lower()
    fs_mode = fs_mode if fs_mode in _F.MODES else ""
    fs_params = _F.params(macros)
    fs_entries: list = [None] * len(shots)
    edge_cache: dict = {}

    def read_edge(clip: Path, which: str) -> np.ndarray:  # one decode per edge frame, shared by the foreshadow layer and the boundary kinds
        key = (str(clip), which)
        if key not in edge_cache:
            edge_cache[key] = _F.edge_frame(Path(clip), which)
        return edge_cache[key]

    if fs_mode:
        house_vj = str((((look.house.get("dance_fx") or {}).get("vj")) or {}).get("preset") or "") if isinstance(look.house, dict) else ""
        tint = (look.tints.get("edge") or (_D.PRESETS.get(look.mode) or {}).get("edge")
                or (_D.PRESETS.get(house_vj) or {}).get("edge") or (255, 255, 255))
        fs_entries = _F.plan(shots, list(clips), list(beats), fps, fs_mode, fs_params, read_edge=read_edge)
        for entry in fs_entries:
            if entry:
                entry.update({"cap": fs_params["cap"], "params": fs_params, "tint": [int(x) for x in tint], "seed": int(seed)})
        log.info("foreshadow %s: %d shots, %d echoes, lead %s beats", fs_mode, sum(1 for e in fs_entries if e and e.get("target") is not None),
                 sum(1 for e in fs_entries if e and e.get("prev") is not None), fs_params["lead_beats"])
    # the boundary kinds (boundary_fx.pick, one entry per shot): the halves of their windows and the second pictures,
    # read here once and sent to the workers as arrays; a handoff a kind took gets no premium window drawn over it
    from xenoform import boundary_fx as _B

    bx_picks = list(boundary_fx or [])[: len(shots)]
    bx_picks += [None] * (len(shots) - len(bx_picks))
    bx_params = _B.params(macros)
    bx_entries: list = [None] * len(shots)
    if any(bx_picks):
        bx_entries = _B.plan(bx_picks, shots, list(clips), read_edge=read_edge)
        for entry in bx_entries:
            if entry:
                entry.update({"params": bx_params, "seed": int(seed)})
        trans = [None if (i < len(bx_picks) and bx_picks[i]) else t for i, t in enumerate(trans)]
        log.info("boundary kinds: %s", _B.info(bx_picks)["kinds"])
    try:
        for si, res in _shot_results(clips, shots, out_path, workers, total, common, fs_entries if fs_mode else None,
                                     bx_entries if any(bx_picks) else None):
            shot = shots[si]
            a, b = res["centres"]
            centres.append([a, b])
            stats = res["look"]
            look.frames += int(stats["frames"]); look.seconds += float(stats["seconds"])
            look.roles.extend(stats["roles"]); look.notes.extend(stats["notes"])
            out: list[np.ndarray] = [res["frames"][k] for k in range(len(res["frames"]))]
            if over is not None:
                out = [over.draw(frame, (n + k) / fps) for k, frame in enumerate(out)]
            n += len(out)
            tr = trans[si] if si < len(trans) else None
            if tr and held and tr.get("kind") and int(tr.get("frames") or 0) >= 2:
                from xenoform import transitions_fx as T

                win = int(min(int(tr["frames"]), len(held), len(out)))
                half = max(1, win // 2)  # not ``h``: that is the output height, and every frame after the window is reframed to it
                a_tail = list(held[-half:]) + [held[-1]] * (win - half)
                b_head = [out[0]] * (win - half) + list(out[:half])
                try:
                    blended = T.apply(str(tr["kind"]), a_tail, b_head, t_intensity)
                    for frame in held[:-half]:
                        write(frame)
                    for frame in blended:
                        write(frame)
                    out = out[half:]
                    used_transitions.append(str(tr["kind"]))
                except Exception as exc:  # a transition must never break a render: plain handoff instead
                    log.warning("transition %s skipped: %s", tr.get("kind"), exc)
                    for frame in held:
                        write(frame)
            else:
                for frame in held:
                    write(frame)
            held = []
            nxt = trans[si + 1] if si + 1 < len(trans) else None
            keep = int(nxt.get("frames") or 0) if nxt and nxt.get("kind") else 0
            keep = max(0, min(keep, len(out) - 1))
            if keep:
                held = out[-keep:]
                out = out[:-keep]
            for frame in out:
                write(frame)
            if report:
                report("assemble", 0.6 + 0.35 * (si + 1) / len(shots), f"Cutting shot {si + 1} of {len(shots)} to the beat")
        for frame in held:
            write(frame)
        held = []
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not write the cut (exit {code}).")
    tmp.replace(out_path)
    if look.active:
        log.info("house look: dance_fx=%s stem_orbit=%s stems=%s %d frames in %.1fs", look.mode, look._orbit_ok,
                 look.env.get("engine"), look.frames, look.seconds)
    return {"frames": n, "seconds": round(n / fps, 3), "size": f"{w}x{h}", "aspect": aspect, "fx": bool(fx),
            "overlay": over is not None, "centres": centres, "fps": fps, "look": look.info(),
            "transitions": used_transitions, "workers": int(workers), "foreshadow": _F.info(fs_entries, fs_mode, fs_params, fps),
            "boundary_fx": _B.info(bx_picks, bx_params)}


def reframe_file(src: Path, dest: Path, aspect: str, *, quality: str = "draft", shots: list[dict] | None = None) -> dict:
    """Reframe a finished 16:9 cut to 9:16 or 1:1 following the subject (no FX change)."""
    aspect = norm_aspect(aspect)
    frames = read_frames(Path(src))
    w, h = out_size(aspect, quality)
    n = len(frames)
    if shots:
        edges = [round(float(s["start"]) * FPS) for s in shots] + [n]
    else:
        edges = list(range(0, n, FPS * 2)) + [n]
    edges = sorted({max(0, min(n, e)) for e in edges})
    tmp = Path(dest).with_name(Path(dest).stem + ".reframe.mp4")
    enc = subprocess.Popen([_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
                            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
                            "-movflags", "+faststart", str(tmp)], stdin=subprocess.PIPE)
    try:
        for a, b in zip(edges[:-1], edges[1:]):
            seg = frames[a:b]
            c0, c1 = shot_centres(seg)
            for k, frame in enumerate(seg):
                u = k / max(len(seg) - 1, 1)
                c = (c0[0] + (c1[0] - c0[0]) * u, c0[1] + (c1[1] - c0[1]) * u)
                enc.stdin.write(np.ascontiguousarray(reframe(frame, aspect, c, w, h)).tobytes())
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not reframe the cut (exit {code}).")
    tmp.replace(dest)
    return {"aspect": aspect, "size": f"{w}x{h}", "frames": n}


# ------------------------------------------------------------------ end card


def _font() -> str | None:
    from xenoform.cloud_morph import _font as find

    return find()


def end_card(path: Path, recipe: str, repo: str | None = None, seconds: float = 2.0) -> bool:
    """Burn the recipe code and repo URL into the last ``seconds`` of the cut (in place)."""
    from xenoform.cloud_morph import _drawtext_font

    font = _font()
    if not font:
        return False
    path = Path(path)
    dur = probe_duration(path)
    if dur <= 0:
        return False
    start = max(0.0, dur - seconds)
    safe = lambda s: str(s).replace("\\", "").replace(":", "\\:").replace("'", "").replace("%", "")[:96]
    ff = _drawtext_font(font)
    common = f"fontfile='{ff}':fontcolor=white:enable='gte(t,{start:.2f})':x=(w-text_w)/2"
    url = safe(repo if repo is not None else repo_url())
    brand = f"Xenoform · {url}" if url else "Xenoform"  # no repo line while the URL is unset / a placeholder
    vf = (f"drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.26:color=black@0.55:t=fill:enable='gte(t,{start:.2f})',"
          f"drawtext={common}:text='Every drop is a transformation':fontsize='min(h/26,w/22)':y=h*0.645,"
          f"drawtext={common}:text='recipe {safe(recipe)}':fontsize='min(h/30,w/26)':y=h*0.72,"
          f"drawtext={common}:text='{brand}':fontsize='min(h/30,w/26)':y=h*0.79")
    tmp = path.with_name(path.stem + ".card.mp4")
    done = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(path), "-vf", vf, "-c:v", "libx264", "-preset",
                           "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                           str(tmp)])
    if done.returncode:
        return False
    tmp.replace(path)
    return True


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ 15 s hook


def pick_hook(audio_path: Path, length: float = 15.0, beats: Iterable[float] = (), lead_in: float = 3.0) -> dict:
    """The window of ``length`` seconds around the strongest drop: lead in a few beats, then the hit.

    The drop is the biggest one-bar jump in loudness. The window starts ``lead_in`` seconds
    before it (snapped to the nearest beat) and is clamped to the song.
    """
    import librosa

    sr = 22050
    y = load_audio(Path(audio_path), sr)
    dur = len(y) / sr
    if dur <= length + 0.05:
        return {"start": 0.0, "end": round(dur, 3), "drop": 0.0, "whole_song": True}
    beats = [float(b) for b in beats]
    drop = drop_time(Path(audio_path), beats, lo=0.1, hi=max(0.15, 1 - (length - lead_in) / dur * 0.6))
    start = drop - lead_in
    if beats:
        start = min(beats, key=lambda b: abs(b - start)) if start > 0 else 0.0
    start = max(0.0, min(dur - length, start))
    return {"start": round(start, 3), "end": round(start + length, 3), "drop": round(drop, 3), "whole_song": False}


def export_hook(src: Path, dest: Path, start: float, length: float = 15.0) -> dict:
    """Cut [start, start+length] from a finished video with short audio fades. Re-encodes for frame accuracy."""
    fade = 0.25
    done = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{length:.3f}",
                           "-af", f"afade=t=in:d={fade},afade=t=out:st={max(0.0, length - fade - 0.05):.3f}:d={fade}",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                           "-b:a", "192k", "-movflags", "+faststart", str(dest)], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("ffmpeg could not cut the hook: " + done.stderr[-300:])
    return {"file": str(dest), "start": start, "seconds": round(probe_duration(Path(dest)), 3)}


def write_meta(path: Path, meta: dict) -> None:
    Path(path).write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")


def drop_time(audio_path: Path, beats: Iterable[float] = (), lo: float = 0.25, hi: float = 0.85) -> float:
    """The song's main drop: the biggest one-bar jump in loudness between ``lo`` and ``hi`` of the song."""
    import librosa

    sr = 22050
    y = load_audio(Path(audio_path), sr)
    dur = len(y) / sr
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    beats = [float(b) for b in beats]
    bar = 4 * float(np.median(np.diff(beats))) if len(beats) >= 2 else 2.0
    win = max(1, int(round(bar * sr / hop)))
    half, two = max(1, win // 2), 2 * win
    smooth = np.convolve(rms, np.ones(half) / half, mode="full")[: len(rms)]  # the half bar before (the dip)
    ahead = np.convolve(rms[::-1], np.ones(two) / two, mode="full")[: len(rms)][::-1]  # the two bars after (sustained)
    score = np.where((t >= dur * lo) & (t <= dur * hi), ahead - smooth, -1e9)
    drop = float(t[int(np.argmax(score))])
    return float(min(beats, key=lambda b: abs(b - drop))) if beats else drop
