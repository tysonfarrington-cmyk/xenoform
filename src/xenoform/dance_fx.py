"""Subject-safe, stem-reactive in-scene effects for character / dance shots.

Every pass here is a pure per-pixel colour or light operation (plus a temporal echo). Nothing moves
pixels: no warp, displacement, scale or channel offset, so a dancer's silhouette, hands and pose stay
exactly where the model put them. Stems drive the amounts through ``stem_react.drive``-style values.

Routing (all 0..1):
    bass   -> halation (highlight bloom with a warm film fringe) and grade contrast
    drums  -> edge tint (colour on the edges, no offset) and the beat light leak
    other  -> frame echo (light ghost trail) and split-tone warmth
    vocals -> tint drift and highlight glow

Scene (non-character) presets such as ``bloom-rush`` add two more colour-only passes:
    wash   -> two-colour gradient wash (screen blend) that drifts with vocals/other and swells on bass/beat
    bleed  -> chroma bleed: colour spreads past edges like wet ink while luma (all structure) stays put
"""
from __future__ import annotations

import numpy as np

try:
    import cv2  # optional; numpy fallbacks below keep the module importable
except ImportError:  # pragma: no cover
    cv2 = None

PASSES = ("grade", "halation", "echo", "edge_tint", "light_leak", "glass", "wash", "bleed", "invert", "flash", "sweep", "depth_bloom", "breath", "blue_morph", "fade")

PRESETS: dict[str, dict] = {
    # name: per-pass amount (0 = off). Kept low on purpose: tasteful, never distorting.
    "warm-leak": {"grade": 0.8, "halation": 0.9, "echo": 0.0, "edge_tint": 0.25, "light_leak": 0.8, "glass": 0.0,
                  "shadow": (0.95, 0.98, 1.06), "high": (1.06, 1.0, 0.92), "edge": (255, 170, 90)},
    "cool-echo": {"grade": 0.7, "halation": 0.5, "echo": 0.8, "edge_tint": 0.7, "light_leak": 0.0, "glass": 0.15,
                  "shadow": (0.92, 0.98, 1.10), "high": (0.98, 1.02, 1.06), "edge": (90, 210, 255)},
    "noir-glow": {"grade": 0.9, "halation": 0.7, "echo": 0.35, "edge_tint": 0.35, "light_leak": 0.5, "glass": 0.2,
                  "shadow": (0.96, 0.94, 1.08), "high": (1.04, 1.0, 1.02), "edge": (200, 140, 255)},
    # aggressive scene preset for hero / morph shots (flowers, objects): long trails, heavy bloom, leaks, washes, bleed
    "bloom-rush": {"grade": 0.8, "halation": 1.0, "echo": 1.0, "edge_tint": 0.45, "light_leak": 1.0, "glass": 0.1,
                   "wash": 0.9, "bleed": 0.85, "echo_decay": 0.86,
                   "shadow": (0.90, 0.97, 1.12), "high": (1.08, 1.0, 0.94), "edge": (120, 220, 255),
                   "wash_a": (40, 210, 255), "wash_b": (255, 70, 170)},
    # bloom-rush plus a stem-driven negative: luma flips on the bass/beat (hue kept), eased in and out
    "negative-rush": {"grade": 0.7, "halation": 0.9, "echo": 0.9, "edge_tint": 0.4, "light_leak": 0.8, "glass": 0.0,
                      "wash": 0.5, "bleed": 0.6, "invert": 0.9, "echo_decay": 0.84,
                      "shadow": (0.92, 0.97, 1.10), "high": (1.06, 1.0, 0.96), "edge": (140, 200, 255),
                      "wash_a": (40, 210, 255), "wash_b": (190, 90, 255)},
    # electric-blue flashes on the beat over bloom-rush, negative pulse only on big hits, slow diagonal light sweep,
    # depth bloom on the bass, a rhythmic exposure breath, and an in-shape blue morph (same subject, crystal-blue variant)
    "cyan-flash": {"grade": 1.0, "halation": 0.55, "echo": 0.9, "edge_tint": 0.45, "light_leak": 0.35, "glass": 0.0,
                   "wash": 0.18, "bleed": 0.5, "echo_decay": 0.80, "flash": 0.55, "sweep": 0.35, "depth_bloom": 0.22,
                   "breath": 0.3, "invert_hits": 0.7, "blue_morph": 0.0,
                   "shadow": (0.55, 0.68, 0.90), "high": (1.0, 1.02, 1.06), "edge": (90, 200, 255),
                   "wash_a": (30, 200, 255), "wash_b": (90, 110, 255), "flash_rgb": (70, 200, 255)},
}

PRESET_NOTES = {  # one line each, for list_looks / the desk
    "warm-leak": "warm split-tone grade, film halation on the bass and a corner light leak on the beat; no echo",
    "cool-echo": "cool blue grade, light ghost trail on 'other', cyan edge tint on the drums, frosted glass (the house VJ look)",
    "noir-glow": "high-contrast noir grade, violet edges, moderate halation and leak, a touch of glass",
    "bloom-rush": "hero / flower preset: long trails, heavy bloom, cyan-magenta gradient wash and chroma bleed (colour only)",
    "negative-rush": "bloom-rush plus a stem-driven negative: luma flips on the bass/beat with the hue kept, eased",
    "cyan-flash": "electric-blue beat flashes, negative pulse on big hits, slow light sweep, depth bloom and exposure breath",
}
ROLES = ("intro", "vj", "flower", "into_card")  # DEMO_HOUSE["dance_fx"] roles; "vj" is the default
DEFAULT_ROLE = "vj"

POST_EFFECTS = {
    "dance-grade": "stem-driven split-tone grade (bass contrast, other warmth, vocals tint)",
    "dance-halation": "highlight bloom with a warm film-halation fringe on the bass",
    "dance-echo": "light ghosted frame echo / motion trail on the 'other' stem",
    "dance-edge-tint": "colour on the subject's edges on the drums, no channel offset",
    "dance-light-leak": "soft corner light leak that blooms on strong beats",
    "dance-glass": "static frosted-glass texture and lens falloff (fixed per shot, never flickers)",
    "dance-fade": "soft fade in/out from black at scene heads and tails",
    "dance-wash": "stem-driven two-colour gradient wash that drifts with the vocals and swells on the bass",
    "dance-bleed": "chroma bleed: colour spreads past edges like wet ink, structure stays put",
    "dance-flash": "beat-synced cyan/electric-blue flash on the subject, with a light sweep, depth bloom and exposure breath",
    "dance-invert": "stem-driven negative look: luma inverts on the bass/beat with the hue kept, eased",
}


def _house(section: str) -> dict:
    """The house profile block (config.house), or {} when config is not importable (loose checkout)."""
    try:
        from xenoform.config import house
    except ImportError:  # pragma: no cover
        try:
            from config import house
        except ImportError:
            return {}
    return house(section)


def resolve(preset: str | None = None, intensity: float | None = None, role: str | None = None,
            house: dict | None = None) -> tuple[str, float, dict]:
    """(preset, intensity, role_cfg): explicit values win, else the house ``dance_fx`` entry for ``role``
    (default "vj"). ``house`` is the ``dance_fx`` block (``{"vj": {"preset":..., "intensity":...}, ...}``)."""
    table = house if isinstance(house, dict) else _house("dance_fx")
    role = role or DEFAULT_ROLE
    cfg = table.get(role) if isinstance(table.get(role), dict) else (table.get(DEFAULT_ROLE) or {})
    if preset is None:
        preset = str(cfg.get("preset") or "warm-leak")
    if intensity is None:
        intensity = float(cfg.get("intensity", 1.0))
    return preset, float(intensity), dict(cfg)


def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    if cv2 is not None:
        return cv2.GaussianBlur(img, (0, 0), sigma)
    from scipy.ndimage import gaussian_filter, zoom  # pragma: no cover
    k = int(sigma / 3)
    if k < 2 or img.ndim != 3 or min(img.shape[:2]) < 4 * k:
        return gaussian_filter(img, (sigma, sigma, 0) if img.ndim == 3 else sigma)
    # wide blurs: block-average down by k, blur there, bilinear back up (6-8x faster, visually the same)
    h, w = img.shape[:2]
    hh, ww = h // k * k, w // k * k
    small = img[:hh, :ww].reshape(hh // k, k, ww // k, k, img.shape[2]).mean(axis=(1, 3))
    small = gaussian_filter(small, (sigma / k, sigma / k, 0))
    return zoom(small, (h / small.shape[0], w / small.shape[1], 1), order=1).astype(np.float32)


class DanceFX:
    """Stateful per-shot effect chain (the echo needs the previous frames)."""

    def __init__(self, preset: str | None = None, *, seed: int = 0, intensity: float | None = None,
                 role: str | None = None, house: dict | None = None):
        """``preset`` / ``intensity`` None fall back to the house ``dance_fx`` entry for ``role``
        (intro / vj / flower / into_card; default vj). The preset table is copied, never aliased."""
        preset, intensity, cfg = resolve(preset, intensity, role, house)
        if preset not in PRESETS:
            raise ValueError(f"unknown dance preset {preset!r}; one of {', '.join(PRESETS)}")
        self.preset = preset; self.role = role or DEFAULT_ROLE
        self.p = dict(PRESETS[preset]); self.k = float(np.clip(intensity, 0, 1.5)); self.seed = seed
        self.invert_floor_ramp_frames = int(cfg.get("invert_floor_ramp_frames") or 0)
        self._acc = None; self._glass = None; self._leak = None; self._phase = 0.0; self._inv = 0.0; self._fl = 0.0; self._ih = 0.0; self._sw = 0.0; self._br = 1.0

    def _static(self, h: int, w: int):
        if self._glass is None:
            rng = np.random.default_rng(self.seed)
            g = rng.standard_normal((max(2, -(-h // 24)), max(2, -(-w // 24)))).astype(np.float32)
            g = cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) if cv2 is not None else _blur(np.kron(g, np.ones((24, 24), np.float32))[:h, :w], 8)
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            fall = 1 - 0.18 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
            self._glass = (1 + 0.035 * g) * fall
            self._leak = np.clip(1 - np.hypot((xx - w * 0.95) / w, (yy - h * 0.08) / h) * 1.5, 0, 1) ** 2
        return self._glass, self._leak

    def apply(self, frame: np.ndarray, d: dict, *, fade: float = 1.0) -> np.ndarray:
        """frame: HxWx3 uint8 RGB. d: {"drums","bass","other","vocals","beat"} in 0..1 (None or missing = 0)."""
        p, k = self.p, self.k
        f = frame.astype(np.float32)
        h, w = f.shape[:2]
        d = d or {}
        dr, ba, ot, vo = (float(np.clip(d.get(s) or 0.0, 0, 1)) for s in ("drums", "bass", "other", "vocals"))
        beat = float(np.clip(d.get("beat") or 0.0, 0, 1))
        if p["echo"] > 0:  # light ghost trail: only brighter-than-now remnants, decaying fast
            dec = p.get("echo_decay", 0.70) + 0.12 * ot
            self._acc = f.copy() if self._acc is None else np.maximum(self._acc * dec, f)
            f = f + (self._acc - f) * (0.18 + 0.22 * ot) * p["echo"] * k
        lum = f.mean(axis=2, keepdims=True) / 255.0
        if p["grade"] > 0:  # split-tone: shadows and highlights get their own tint; bass adds a touch of contrast
            sh, hi = np.array(p["shadow"], np.float32), np.array(p["high"], np.float32)
            warm = 1 + 0.05 * ot * np.array([1, 0.3, -1], np.float32) + 0.04 * vo * np.array([0.4, -0.6, 0.6], np.float32)
            tint = (sh * (1 - lum) + hi * lum) * warm
            g = 1 + (tint - 1) * p["grade"] * k
            c = 1 + 0.10 * ba * p["grade"] * k
            f = ((f / 255.0 - 0.5) * c + 0.5) * 255.0 * g
        if p["halation"] > 0:  # bloom from highlights only, with a warm red-orange fringe like film halation
            hl = np.clip((f.mean(axis=2, keepdims=True) - 170) / 85, 0, 1) * f
            s = max(1.0, w / 1080)
            bl = _blur(hl, 18 * s); fr = _blur(hl, 42 * s) * np.array([1.0, 0.45, 0.2], np.float32)
            amt = (0.18 + 0.45 * max(ba, vo)) * p["halation"] * k
            f = f + bl * amt * 0.6 + fr * amt * 0.5
        if p["edge_tint"] > 0:  # colour on the edges, in place (no offset)
            g = f.mean(axis=2)
            if cv2 is not None:
                gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
            else:  # pragma: no cover
                gy, gx = np.gradient(g)
            e = _blur(np.clip(np.hypot(gx, gy) / 360.0, 0, 1).astype(np.float32), 1.2)[..., None]
            f = f + e * np.array(p["edge"], np.float32) * (0.10 + 0.35 * dr) * p["edge_tint"] * k
        if p.get("bleed", 0) > 0:  # colour bleeds outward; luma untouched, so nothing moves
            L = f.mean(axis=2, keepdims=True); C = f - L
            s_ = max(1.0, w / 1080) * (10 + 26 * max(ot, vo))
            Cb = _blur(C, s_) * (1.25 + 0.6 * ba)
            a = float(np.clip((0.35 + 0.45 * max(ba, beat)) * p["bleed"] * k, 0, 0.95))
            f = L + C * (1 - a) + Cb * a
        if p.get("wash", 0) > 0:  # gradient wash, screen-blended; direction drifts slowly with the vocals/other
            ang = 0.9 * self._phase + 1.2 * vo; self._phase += 0.01 + 0.03 * ot
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            g = np.clip(0.5 + ((xx / w - 0.5) * np.cos(ang) + (yy / h - 0.5) * np.sin(ang)), 0, 1)[..., None]
            col = np.array(p.get("wash_a", (40, 210, 255)), np.float32) * (1 - g) + np.array(p.get("wash_b", (255, 70, 170)), np.float32) * g
            amt = float(np.clip((0.06 + 0.28 * max(ba, beat) + 0.08 * vo) * p["wash"] * k, 0, 0.6))
            f = 255 - (255 - f) * (255 - col * amt) / 255
        if p.get("invert", 0) > 0 or p.get("invert_floor", 0) > 0:  # negative: flip luma only (hue/chroma kept); amount eased through a follower
            tgt = float(np.clip(max(p.get("invert_floor", 0.0), p.get("invert", 0) * k * (0.15 + 0.85 * max(ba, beat))), 0, 1))
            self._inv += (tgt - self._inv) * 0.25
            if self._inv > 1e-3:
                L = f.mean(axis=2, keepdims=True)
                f = f + (255.0 - 2.0 * L) * self._inv
        if p.get("blue_morph", 0) > 0:  # same subject, crystal-blue variant: luma kept, chroma pulled to electric blue
            L = f.mean(axis=2, keepdims=True); bm = float(np.clip(p["blue_morph"], 0, 1))
            blue = L * np.array([0.55, 0.92, 1.35], np.float32) + (f - L) * 0.25
            f = f * (1 - bm) + blue * bm
        if p.get("flash", 0) > 0:  # beat flash: electric blue lands on the subject (bright areas), with a soft halo
            self._fl = max(self._fl * 0.72, beat)
            if self._fl > 1e-3:
                m = np.clip((f.mean(axis=2, keepdims=True) - 40) / 160, 0, 1)
                s = max(1.0, w / 1080)
                halo = (_blur(np.ascontiguousarray(m[..., 0] * 255.0), 30 * s) / 255.0).reshape(h, w, 1)
                f = f + (m * 0.8 + halo * 0.5) * np.array(p.get("flash_rgb", (70, 200, 255)), np.float32) * self._fl * p["flash"] * k * (0.5 + 0.5 * dr)
        if p.get("invert_hits", 0) > 0:  # negative pulse on the big hits only, eased out fast
            self._ih = max(self._ih * 0.70, float(beat > 0.85) * (0.5 + 0.5 * ba) * p["invert_hits"])
            if self._ih > 1e-3:
                L = f.mean(axis=2, keepdims=True); f = f + (255.0 - 2.0 * L) * min(self._ih, 1.0)
        if p.get("sweep", 0) > 0:  # slow diagonal light band, screen-blended
            self._sw += 0.012 + 0.02 * ot
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            u = (xx / w * 0.6 + yy / h) - ((self._sw % 2.2) - 0.4)
            band = np.exp(-(u / 0.09) ** 2)[..., None] * (0.35 + 0.65 * max(vo, ot))
            f = 255 - (255 - f) * (1 - band * 0.45 * p["sweep"] * k)
        if p.get("depth_bloom", 0) > 0:  # wide soft bloom, deepens on the bass
            s = max(1.0, w / 1080)
            f = f + _blur(f, 60 * s) * (0.10 + 0.30 * ba) * p["depth_bloom"] * k
        if p.get("breath", 0) > 0:  # rhythmic exposure breath following the bass, eased
            self._br += ((1.0 + 0.22 * ba) - self._br) * 0.15
            f = f * (1 + (self._br - 1) * p["breath"] * k * 2)
        glass, leak = self._static(h, w)
        if p["light_leak"] > 0:
            f = f + leak[..., None] * np.array([255, 150, 70], np.float32) * (0.05 + 0.30 * beat) * p["light_leak"] * k
        if p["glass"] > 0:
            f = f * (1 + (glass[..., None] - 1) * p["glass"] * k)
        if fade < 1.0:
            f = f * float(np.clip(fade, 0, 1))
        return np.clip(f, 0, 255).astype(np.uint8)


def drive_from_env(env: dict, t: float, beats: list[float] | None = None, gains: dict | None = None) -> dict:
    """Stem values at time t (``stem_react`` envelope format) plus a decaying beat pulse. ``gains``
    ({stem name: 0..1}, the Simple ``macros.stems`` knob) weights each named stem before it feeds its role."""
    try:
        from xenoform.stem_react import role_levels
    except ImportError:  # loose checkout
        from stem_react import role_levels
    env = env or {}
    d = {s: float(v or 0.0) for s, v in role_levels(env, t, gains or None).items()}
    hits = beats if beats is not None else (env.get("drum_strong") or [])
    past = [t - h for h in hits if 0 <= t - h < 0.6]
    d["beat"] = float(np.exp(-min(past) / 0.14)) if past else 0.0
    return d


def render_shot(frames, env: dict, t0: float, preset: str | None = None, *, fps: int | None = None, fade_in: int = 0,
                fade_out: int = 0, seed: int = 0, intensity: float | None = None, beats: list[float] | None = None,
                role: str | None = None, invert_floor_ramp_frames: int | None = None, gains: dict | None = None,
                house: dict | None = None):
    """Run one shot through a preset. Yields processed frames.

    ``preset`` / ``intensity`` None: the house entry for ``role`` (default vj). ``fps`` None: the house format fps.
    ``invert_floor_ramp_frames`` (None: the role's value, 14 for into_card): over the last N frames the preset's
    ``invert_floor`` ramps 0 -> 1, so the shot lands fully inverted on the card."""
    fx = DanceFX(preset, seed=seed, intensity=intensity, role=role, house=(house or {}).get("dance_fx") if house else None)
    if fps is None:
        fps = int(((house or {}).get("format") or _house("format")).get("fps") or 24)
    ramp = fx.invert_floor_ramp_frames if invert_floor_ramp_frames is None else int(invert_floor_ramp_frames)
    frames = list(frames); n = len(frames)
    for i, fr in enumerate(frames):
        fd = 1.0
        if fade_in and i < fade_in:
            fd = (i + 1) / (fade_in + 1)
        if fade_out and i >= n - fade_out:
            fd = min(fd, (n - i) / (fade_out + 1))
        if ramp > 0 and i >= n - ramp:
            fx.p["invert_floor"] = float(np.clip((i - (n - ramp) + 1) / ramp, 0.0, 1.0))
        yield fx.apply(fr, drive_from_env(env, t0 + i / fps, beats, gains), fade=fd)
