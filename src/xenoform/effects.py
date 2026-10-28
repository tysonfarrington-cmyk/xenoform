"""TouchDesigner-style effects on the cut, all CPU and all riding the music (docs/MORPH_ENGINE_PLAN.md E4; Tys, 28 Oct:
"a proper dither effect ... high quality ... some more touch designer type effects").

- **Dither** (a Look, and a beat effect): the picture's light mapped onto a few tones of the vibe's own palette, the
  steps between tones broken up by a blue-noise threshold. Blue noise (``blue_noise``: void-and-cluster, Ulichney 1993)
  has no low frequencies, so the dots never clump into worms or show a grid the way Bayer or error diffusion do, and it
  is a per-pixel comparison, fast enough for every frame. As a Look the whole cut is dithered and the grain jumps on
  each beat; as an effect it hits on the kicks and lets go between them.
- **Feedback** (``Feedback``): the picture over a zoomed, turned copy of the frame before it, lighten-blended, so a
  bright object on black leaves a tunnel of itself; the zoom swells with the loudness.
- **Kaleido** (``kaleido``): the frame folded into mirrored wedges round its centre, mixed in with the loudness, the
  wedges turning slowly and jumping a step on each beat.
- **Slit-scan** (``SlitScan``): each row of the frame taken from a moment a little further back the lower it sits, so
  motion smears into a curve, deepening with the loudness.

``plan(names, macros, palette_image, size)`` says which effects a cut runs and how hard (the Intensity knob); ``Chain``
runs them per shot on each frame, after the Look (``beatfx._shot_frames``), so they see the graded picture.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

NAMES = ("dither", "feedback", "kaleido", "slitscan")
LABELS = {"dither": "Dither hits", "feedback": "Feedback", "kaleido": "Kaleido", "slitscan": "Slit-scan", "smear": "Blocky smear"}
NOTES = {
    "dither": "On each kick the picture drops to a few tones of the vibe's palette in fine blue-noise dots, then lets go.",
    "feedback": "The picture over a zoomed, turned copy of the frame before: bright objects leave a tunnel; it swells with the loudness.",
    "kaleido": "The frame folded into mirrored wedges, mixed in with the loudness, turning a step on each beat.",
    "slitscan": "Each row from a moment further back the lower it sits: motion bends into curves as the song gets loud.",
    "smear": "The blocky datamosh smear at a few handoffs (one in six at most, never the drop); off, those handoffs wipe or rip instead.",
}
LOOKS = ("dither",)  # Looks served here rather than by dance_fx (a whole-cut look, not an effect over one)
LOOK_NOTES = {"dither": "the vibe's palette in a few tones, broken up by fine blue-noise dots that jump on the beat (a print, "
                        "a screen, a 1-bit game)"}
DEFAULT_TONES = ((6, 6, 10), (64, 36, 112), (60, 196, 230), (246, 242, 255))


@lru_cache(maxsize=4)
def blue_noise(n: int = 64, sigma: float = 1.5, seed: int = 7) -> np.ndarray:
    """A tileable ``n``x``n`` blue-noise threshold map in (0, 1), every value once (void-and-cluster): the dither matrix.
    Deterministic, built once per process (about half a second at 64)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(n) * n
    kern = np.fft.fft2(np.exp(-(f[:, None] ** 2 + f[None, :] ** 2) / (2.0 * sigma ** 2)))

    def energy(b: np.ndarray) -> np.ndarray:
        return np.real(np.fft.ifft2(np.fft.fft2(b.astype(np.float64)) * kern))

    m = n * n
    ones = max(1, m // 10)
    proto = np.zeros(m, bool)
    proto[rng.choice(m, ones, replace=False)] = True
    proto = proto.reshape(n, n)
    for _ in range(m):  # relax: move the tightest cluster's point into the largest void until it lands where it was
        e = energy(proto)
        c = int(np.argmax(np.where(proto, e, -np.inf)))
        proto.flat[c] = False
        e = energy(proto)
        v = int(np.argmin(np.where(proto, np.inf, e)))
        proto.flat[v] = True
        if v == c:
            break
    rank = np.zeros(m, np.int64)
    b = proto.copy()
    for r in range(ones - 1, -1, -1):  # phase 1: the prototype's points, tightest cluster last
        e = energy(b)
        c = int(np.argmax(np.where(b, e, -np.inf)))
        b.flat[c] = False
        rank[c] = r
    b = proto.copy()
    for r in range(ones, m):  # phases 2 and 3: fill the largest void (the tightest cluster of the minority past half)
        if r < m // 2:
            e = energy(b)
            v = int(np.argmin(np.where(b, np.inf, e)))
        else:
            e = energy(~b)
            v = int(np.argmax(np.where(~b, e, -np.inf)))
        b.flat[v] = True
        rank[v] = r
    return ((rank.reshape(n, n) + 0.5) / m).astype(np.float32)


def palette_from_image(path: str | Path | None, n: int = 4) -> np.ndarray:
    """``n`` tones from dark to light for the dither, from a still of the vibe (``palette_from_pixels``);
    ``DEFAULT_TONES`` when the still is missing or unreadable."""
    if not path:
        return np.asarray(DEFAULT_TONES, np.float32)
    try:
        from xenoform.portrait import load_rgb

        img = np.asarray(load_rgb(Path(path)), np.float32)[..., :3].reshape(-1, 3)
    except Exception:
        return np.asarray(DEFAULT_TONES, np.float32)
    return palette_from_pixels(img, n)


def palette_from_clips(clips, n: int = 4, most: int = 8) -> np.ndarray:
    """The dither's tones from the cut itself: the middle frame of up to ``most`` of its clips, small, pooled
    (``palette_from_pixels``). The first still alone can be a dark object that misses the vibe's neon."""
    import subprocess

    picked = list(clips or [])
    if len(picked) > most:
        picked = [picked[int(round(k * (len(picked) - 1) / (most - 1)))] for k in range(most)]
    pools = []
    for clip in picked:
        try:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-sseof", "-1.5", "-i", str(clip), "-frames:v", "1",
                                  "-vf", "scale=96:96", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, check=True).stdout
            if len(raw) >= 96 * 96 * 3:
                pools.append(np.frombuffer(raw[:96 * 96 * 3], np.uint8).reshape(-1, 3).astype(np.float32))
        except Exception:
            continue
    if not pools:
        return np.asarray(DEFAULT_TONES, np.float32)
    return palette_from_pixels(np.concatenate(pools), n)


def palette_from_pixels(img: np.ndarray, n: int = 4) -> np.ndarray:
    """``n`` tones from dark to light: near black, then the colours of the lit pixels at rising light (each band's
    most saturated pixels, pushed further from grey, so the dither keeps a vibe's neon instead of a muddy mean), the
    last lifted towards white. ``DEFAULT_TONES`` when the pixels are grey or too few."""
    tones = np.asarray(DEFAULT_TONES, np.float32)
    img = np.asarray(img, np.float32).reshape(-1, 3)
    weights = np.array([0.2126, 0.7152, 0.0722], np.float32)
    lum = img @ weights
    lit = img[lum > 18.0]
    if len(lit) < 256:
        return tones
    ll = lit @ weights
    sat = lit.max(axis=1) - lit.min(axis=1)
    if float(np.percentile(sat, 90)) < 18.0:
        return tones  # a grey still: the default tones read better than four greys
    # each band of light gives its tone from its most saturated pixels (a band's plain mean is a muddy grey), pushed
    # further from grey, so the dither keeps the vibe's neon instead of fading it
    edges = np.percentile(ll, np.linspace(15, 100, n))
    out = [np.array([6.0, 6.0, 10.0], np.float32)]
    lo = float(np.percentile(ll, 5))
    for k in range(1, n):
        inside = ((ll >= lo) if k == 1 else (ll > lo)) & (ll <= edges[k])
        lo = float(edges[k])
        band, bsat = lit[inside], sat[inside]
        if len(band) < 8:
            out.append(np.clip(out[-1] + 60.0, 0, 255))
            continue
        col = band[bsat >= np.percentile(bsat, 80)].mean(axis=0)
        grey = float(col @ weights)
        out.append(np.clip(grey + (col - grey) * 1.6, 0, 255))
    out = np.clip(np.stack(out), 0, 255)
    out[-1] = np.clip(out[-1] * 0.5 + 255.0 * 0.5, 0, 255)  # the top tone towards white: the dots need a light
    out = out[np.argsort(out @ weights)]
    for k in range(1, n):  # tones a step apart in light, or two of them dither as one
        gap = float(out[k] @ weights) - float(out[k - 1] @ weights)
        if gap < 24.0:
            out[k] = np.clip(out[k] + (24.0 - gap), 0, 255)
    return out.astype(np.float32)


class Levels:
    """The light a frame spans (its 1st and 99.5th percentile), eased from frame to frame, so a dark neon picture
    still uses every tone of the dither without the range pumping on each cut."""

    def __init__(self, ease: float = 0.25) -> None:
        self.ease = float(ease)
        self.lo: float | None = None
        self.hi: float | None = None

    def __call__(self, frame: np.ndarray) -> tuple[float, float]:
        sample = frame[::4, ::4].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        lo, hi = (float(v) / 255.0 for v in np.percentile(sample, [1.0, 99.5]))
        hi = max(hi, lo + 0.15)
        if self.lo is None:
            self.lo, self.hi = lo, hi
        else:
            self.lo += (lo - self.lo) * self.ease
            self.hi += (hi - self.hi) * self.ease
        return self.lo, self.hi


def dither(frame: np.ndarray, tones: np.ndarray, *, amount: float = 1.0, dot: int = 2, shift: tuple[int, int] = (0, 0),
           contrast: float = 1.15, levels: tuple[float, float] | None = None) -> np.ndarray:
    """``frame`` mapped onto ``tones`` (dark to light) by its light, each pixel between two tones choosing by the blue
    noise threshold under it; ``dot`` is the size of a dither dot in pixels, ``shift`` moves the noise (a new grain),
    ``levels`` (``Levels``) stretches the light the frame spans over every tone, ``amount`` mixes it over the picture."""
    if amount <= 0.01:
        return frame
    h, w = frame.shape[:2]
    f = frame.astype(np.float32) / 255.0
    lum = f @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    if levels is not None:
        lo, hi = float(levels[0]), float(levels[1])
        lum = (lum - lo) / max(hi - lo, 1e-3)
    lum = np.clip((lum - 0.5) * contrast + 0.5, 0.0, 1.0)
    bn = blue_noise()
    size = bn.shape[0]
    d = max(1, int(dot))
    ys = (np.arange(h) // d + int(shift[0])) % size
    xs = (np.arange(w) // d + int(shift[1])) % size
    thr = bn[ys[:, None], xs[None, :]]
    n = len(tones)
    idx = np.clip(np.floor(lum * (n - 1) + thr), 0, n - 1).astype(np.int64)
    out = np.asarray(tones, np.float32)[idx]
    if amount < 0.99:
        out = frame.astype(np.float32) * (1.0 - amount) + out * amount
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def dot_for(size: tuple[int, int]) -> int:
    """The dither dot for a frame size: two pixels at 540x960, four at 1080x1920 (the same on a phone screen)."""
    return max(1, int(round(min(size) / 270.0)))


def shift_for(t: float, beats: list[float]) -> tuple[int, int]:
    """A new grain on each beat: the noise moved by an offset seeded from the beat's index."""
    k = int(np.searchsorted(np.asarray(beats or [], np.float64), float(t), side="right"))
    rng = np.random.default_rng(1009 + k)
    return int(rng.integers(0, 64)), int(rng.integers(0, 64))


@lru_cache(maxsize=8)
def _polar(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    y -= (h - 1) / 2.0
    x -= (w - 1) / 2.0
    return np.hypot(x, y), np.arctan2(y, x)


def kaleido(frame: np.ndarray, *, amount: float, segments: int = 6, angle: float = 0.0) -> np.ndarray:
    """The frame folded into ``segments`` mirrored wedges round its centre, turned by ``angle``, mixed in by
    ``amount``. Nearest-neighbour: a fold has hard seams anyway, and it costs a gather."""
    if amount <= 0.01:
        return frame
    h, w = frame.shape[:2]
    r, th = _polar(h, w)
    seg = 2.0 * np.pi / max(2, int(segments))
    a = np.mod(th - angle, seg)
    a = np.minimum(a, seg - a) + angle
    sx = np.clip(np.rint((w - 1) / 2.0 + r * np.cos(a)), 0, w - 1).astype(np.int64)
    sy = np.clip(np.rint((h - 1) / 2.0 + r * np.sin(a)), 0, h - 1).astype(np.int64)
    folded = frame[sy, sx]
    if amount >= 0.99:
        return folded
    return np.clip(frame.astype(np.float32) * (1.0 - amount) + folded.astype(np.float32) * amount + 0.5, 0, 255).astype(np.uint8)


def _zoom_turn(frame: np.ndarray, zoom: float, turn: float) -> np.ndarray:
    h, w = frame.shape[:2]
    r, th = _polar(h, w)
    rr = r / max(zoom, 1e-3)
    a = th - turn
    sx = np.clip(np.rint((w - 1) / 2.0 + rr * np.cos(a)), 0, w - 1).astype(np.int64)
    sy = np.clip(np.rint((h - 1) / 2.0 + rr * np.sin(a)), 0, h - 1).astype(np.int64)
    return frame[sy, sx]


class Feedback:
    """The picture over a zoomed, turned copy of the last output frame, lighten-blended and fading: a tunnel."""

    def __init__(self) -> None:
        self.prev: np.ndarray | None = None

    def __call__(self, frame: np.ndarray, *, amount: float, loud: float, t: float) -> np.ndarray:
        if amount <= 0.01:
            self.prev = frame
            return frame
        if self.prev is None or self.prev.shape != frame.shape:
            self.prev = frame
            return frame
        zoom = 1.015 + 0.05 * float(loud) * amount
        turn = 0.012 * np.sin(0.7 * t) * amount
        trail = _zoom_turn(self.prev, zoom, turn).astype(np.float32) * (0.55 + 0.35 * amount)
        out = np.maximum(frame.astype(np.float32), trail)
        out = np.clip(out + 0.5, 0, 255).astype(np.uint8)
        self.prev = out
        return out


class SlitScan:
    """Each row from a frame further back the lower it sits (a ring of the last ``depth`` frames), so motion bends."""

    def __init__(self, depth: int = 16) -> None:
        self.depth = int(depth)
        self.ring: np.ndarray | None = None
        self.count = 0

    def __call__(self, frame: np.ndarray, *, amount: float, loud: float) -> np.ndarray:
        h = frame.shape[0]
        if self.ring is None or self.ring.shape[1:] != frame.shape:
            self.ring = np.empty((self.depth,) + frame.shape, frame.dtype)
            self.count = 0
        i = self.count % self.depth
        self.ring[i] = frame
        self.count += 1
        reach = min(self.count - 1, self.depth - 1)
        if amount <= 0.01 or reach < 1:
            return frame
        # a fractional lag a row, the two frames either side blended: a smooth bend, not bands torn at each frame step
        lag = np.linspace(0.0, 1.0, h) ** 1.5 * reach * min(1.0, amount * (0.35 + 0.65 * float(loud)))
        lo = np.floor(lag).astype(np.int64)
        frac = (lag - lo).astype(np.float32)[:, None, None]
        hi = np.minimum(lo + 1, reach)
        rows = np.arange(h)
        a = self.ring[(i - lo) % self.depth, rows].astype(np.float32)
        b = self.ring[(i - hi) % self.depth, rows].astype(np.float32)
        return np.clip(a * (1.0 - frac) + b * frac + 0.5, 0, 255).astype(np.uint8)


def names_of(state: dict | None) -> list[str]:
    """The effects a make body or a re-cut asks for (``effects``), known ones only, plus "smear" when it asks for the
    blocky smear (the desk's Effects row carries it beside the effects)."""
    raw = (state or {}).get("effects") or []
    if isinstance(raw, str):
        raw = [x for x in raw.replace(",", " ").split()]
    asked = {str(x).strip().lower() for x in raw}
    return [n for n in NAMES + ("smear",) if n in asked]


def smear_setting(state: dict | None) -> str:
    """The blocky smear (boundary_fx.SMEAR): ``boundary_smear`` when the body names one, else "sparing" when its effects
    ask for "smear", else "off" (the default since 28 Oct)."""
    explicit = str((state or {}).get("boundary_smear") or "").strip().lower()
    if explicit in ("off", "sparing", "on"):
        return explicit
    return "sparing" if "smear" in names_of(state) else "off"


def plan(names, macros: dict | None, palette_image: str | None = None, size: tuple[int, int] | None = None,
         tones=None) -> dict | None:
    """What a cut's effects run as: the names it asked for (known ones, in ``NAMES`` order), the Intensity amount, the
    dither tones (``tones`` when the cut measured its own, ``palette_from_clips``; else from the palette still) and
    dot. None when there are none."""
    asked = [n for n in NAMES if n in {str(x).strip().lower() for x in (names or [])}]
    if not asked:
        return None
    m = macros or {}
    try:
        intensity = max(0.0, min(1.0, float(m.get("intensity", 0.5))))
    except (TypeError, ValueError):
        intensity = 0.5
    try:
        chaos = max(0.0, min(1.0, float(m.get("chaos", 0.3))))
    except (TypeError, ValueError):
        chaos = 0.3
    out = {"names": asked, "amount": round(0.45 + 0.55 * intensity, 3), "segments": 8 if chaos >= 0.6 else 6}
    if "dither" in asked:
        out["tones"] = [list(map(float, t)) for t in tones] if tones is not None and len(tones) else palette_from_image(palette_image).tolist()
        out["dot"] = dot_for(size) if size else 2
    return out


def wants_tones(look: str, names, shots: list[dict] | None = None) -> bool:
    """Whether a cut dithers anywhere (the Dither look, the dither hits, a shot's own Dither look), so it is worth
    measuring its tones from its clips."""
    return str(look or "") == "dither" or "dither" in [str(x) for x in (names or [])] or \
        any(str(s.get("dance_fx") or "") == "dither" for s in shots or [])


class Chain:
    """One shot's effects, frame by frame (the feedback and the slit-scan keep the shot's last frames)."""

    def __init__(self, cfg: dict | None, beats: list[float], look_mode: str = "") -> None:
        self.cfg = cfg or {}
        self.names = [n for n in self.cfg.get("names") or [] if n in NAMES]
        if look_mode == "dither":  # the Look dithers the whole cut already
            self.names = [n for n in self.names if n != "dither"]
        self.beats = [float(b) for b in beats or []]
        self.amount = float(self.cfg.get("amount", 0.7))
        self.tones = np.asarray(self.cfg.get("tones") or DEFAULT_TONES, np.float32)
        self.dot = int(self.cfg.get("dot") or 2)
        self.feedback = Feedback() if "feedback" in self.names else None
        self.slit = SlitScan() if "slitscan" in self.names else None
        self.levels = Levels()

    @property
    def active(self) -> bool:
        return bool(self.names)

    def __call__(self, frame: np.ndarray, t: float, *, kick: float = 0.0, loud: float = 0.0) -> np.ndarray:
        if not self.names:
            return frame
        if self.feedback is not None:
            frame = self.feedback(frame, amount=self.amount, loud=loud, t=t)
        if "kaleido" in self.names:
            k = int(np.searchsorted(np.asarray(self.beats, np.float64), t, side="right")) if self.beats else 0
            angle = 0.15 * t + k * (np.pi / int(self.cfg.get("segments", 6)) / 2.0)
            frame = kaleido(frame, amount=self.amount * min(1.0, 0.25 + 0.85 * float(loud)), segments=int(self.cfg.get("segments", 6)),
                            angle=angle)
        if self.slit is not None:
            frame = self.slit(frame, amount=self.amount, loud=loud)
        if "dither" in self.names:
            levels = self.levels(frame)  # every frame, so the range is eased by the time a kick comes
            hit = min(1.0, 1.4 * float(kick)) * self.amount
            if hit > 0.05:
                frame = dither(frame, self.tones, amount=hit, dot=self.dot, shift=shift_for(t, self.beats), levels=levels)
        return frame
