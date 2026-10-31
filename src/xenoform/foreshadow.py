"""The foreshadow layer: the next object arrives before its shot, the way a new sound is introduced before it
takes the song.

A cut is a chain of morphs, each landing on the object the next one starts from, so the thing that is actually
new at each handoff is the object the *next* morph lands on. In the tail of every shot that object is brought in
over the picture (``treat``): its edge trace glowing in the vibe's tint, its negative ghost, slices of it
interleaved and multiplying, or its silhouette filled with the tint. The amount ramps over the lead (a bar or so,
``params`` from the Speed knob), is capped by the Intensity knob, and follows a stem (the "other" lane, where
hats and melodic lines live, else the beat), so it breathes with the music. Where a shot hard-cuts into a
performer or one of the user's own clips, the object about to leave echoes out over the new shot for a beat.

``plan`` decides, per shot, which frame to foreshadow and whether to echo; ``beatfx._shot_frames`` applies
``treat`` frame by frame before the house look, so the look grades the layer as part of the picture. Pure numpy
(OpenCV when present, for the blur); no model, no GPU, and it runs inside the parallel look pass.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

import numpy as np

MODES = ("trace", "negative", "slices", "silhouette")
CHOICES = ("auto", "off") + MODES
DEFAULT = "auto"
ECHO_BEATS = 1.0
FADE_S = 0.3        # a morph landing fades the layer out over the head of the next shot instead of dropping it
MIN_LEAD_FRAMES = 6
FOLLOW = 0.3        # the stem is eased through a one-pole follower per frame, so a spiky lane cannot strobe the layer
MODE_GAIN = {"trace": 1.0, "negative": 0.6, "slices": 1.0, "silhouette": 0.85}  # a bright ghost on a dark vibe needs less
PLAIN_GROUND_MODES = ("trace", "silhouette")  # the modes that outline an object against its ground: none for a setting

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - OpenCV is a dependency; the numpy path stays as the fallback
    cv2 = None


# ------------------------------------------------------------------------------------------------ choices


def choice(state: dict | None) -> str:
    """The raw ``foreshadow`` payload key, normalised: "auto" (default), "off" or a mode name."""
    raw = str((state or {}).get("foreshadow", DEFAULT) or DEFAULT).strip().lower()
    return raw if raw in CHOICES else DEFAULT


def mode_for(choice_: str, vibe: str | None = None) -> str:
    """"auto" -> the vibe's ``fx_defaults.foreshadow`` when it names a mode, else by tone: a dark vibe traces (the
    glow reads on black), a bright one slices (a trace is lost on paper). "off" -> ""."""
    text = str(choice_ or DEFAULT).strip().lower()
    if text in ("off", "none", "false", "0", "no"):
        return ""
    if text in MODES:
        return text
    if vibe:
        try:
            from xenoform import vibes as _vibes

            row = (next((r for r in _vibes.extended() if r.get("id") == vibe), None)
                   or next((r for r in _vibes.ORIGINAL_META if r.get("id") == vibe), None) or {})  # cosmic, black are originals
            pick = str(((row.get("fx_defaults") or {}).get("foreshadow")) or "").strip().lower()
            if pick in MODES:
                return pick
            tone = str(row.get("tone") or ("dark" if row.get("dark") else "bright"))
            return "slices" if tone == "bright" else "trace"
        except Exception:
            pass
    return "trace"


def params(macros: dict | None) -> dict:
    """The knobs as the layer reads them: Intensity caps the opacity, Speed sets how early it starts, Chaos the
    slice count and jitter, Glow the trace's halo."""
    m = macros or {}

    def knob(key: str, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(m.get(key, default))))
        except (TypeError, ValueError):
            return default

    intensity, speed, chaos, glow = knob("intensity", 0.5), knob("speed", 0.5), knob("chaos", 0.3), knob("glow", 0.4)
    return {"cap": round(0.25 + 0.55 * intensity, 3), "lead_beats": round(2.0 + 4.0 * speed, 2),
            "slices": int(4 + round(12 * chaos)), "jitter": round(chaos, 3), "glow": round(0.4 + 0.6 * glow, 3)}


# ------------------------------------------------------------------------------------------------ the plan


def _beat_period(beats, fallback: float = 0.5) -> float:
    b = [float(x) for x in (beats or [])]
    if len(b) < 2:
        return fallback
    d = np.diff(np.asarray(b))
    d = d[(d > 0.15) & (d < 2.0)]
    return float(np.median(d)) if len(d) else fallback


def plan(shots: list[dict], clips: list, beats, fps: int, mode: str, p: dict, *,
         read_edge: Callable[[Path, str], np.ndarray] | None = None, marks: tuple[str, ...] = ("performer", "own")) -> list[dict | None]:
    """One entry per shot (or None): what to foreshadow in its tail and what to echo at its head.

    The target is the next shot's *last* frame when the handoff is a morph landing (the chain is continuous, so
    the next shot's first frame is where this one already ends) and its *first* frame when the next shot is a
    hard cut into a performer or own clip. The echo (the previous shot's last frame) happens only across a hard
    cut, into or out of such a clip. ``read_edge(clip, "first" | "last")`` reads one frame; frames are read
    once each here, in the parent, and travel to the worker as arrays."""
    if not mode or not shots:
        return [None] * len(shots)
    read_edge = read_edge or edge_frame
    period = _beat_period(beats)
    lead = max(MIN_LEAD_FRAMES, int(round(float(p.get("lead_beats", 4.0)) * period * fps)))
    echo = max(2, int(round(ECHO_BEATS * period * fps)))
    out: list[dict | None] = []
    cache: dict[tuple[str, str], np.ndarray] = {}

    def frame(i: int, which: str) -> np.ndarray | None:
        key = (str(clips[i]), which)
        if key not in cache:
            try:
                cache[key] = np.ascontiguousarray(read_edge(Path(str(clips[i])), which))
            except Exception:
                return None
        return cache[key]

    def hard(i: int) -> bool:
        return 0 <= i < len(shots) and any(bool(shots[i].get(m)) for m in marks)

    def held(i: int) -> bool:  # the timeline's Hold: the shot shows its first frame throughout, and the join after it is a cut
        return 0 <= i < len(shots) and bool(shots[i].get("hold"))

    def in_place(i: int, which: str) -> bool:
        # the trace and the silhouette outline an object against its ground; a setting's frame (an object standing in a
        # place, ``still_kinds`` from dense.stamp_still_kinds) has no ground to read, so its edges would trace the whole
        # place: that handoff stays plain
        if mode not in PLAIN_GROUND_MODES or not 0 <= i < len(shots):
            return False
        kinds = list(shots[i].get("still_kinds") or [])
        return bool(kinds) and kinds[0 if which == "first" else -1] == "setting"

    for si, shot in enumerate(shots):
        n = int(shot.get("frames") or 0)
        entry: dict = {"mode": mode, "lead": 0, "echo": 0, "target": None, "prev": None}
        if si + 1 < len(shots) and si + 1 < len(clips) and n > 0:
            which = "first" if (hard(si + 1) or held(si) or held(si + 1)) else "last"
            tgt = None if in_place(si + 1, which) else frame(si + 1, which)
            if tgt is not None:
                entry["target"] = tgt
                entry["lead"] = int(min(lead, max(MIN_LEAD_FRAMES, n // 2)))
                entry["which"] = which
        if si > 0 and si - 1 < len(clips) and n > 0 and (hard(si) or hard(si - 1) or held(si - 1)):
            which = "first" if held(si - 1) else "last"  # across a hard cut: the object that just left echoes out for a beat
            prev = None if in_place(si - 1, which) else frame(si - 1, which)
            if prev is not None:
                entry["prev"] = prev
                entry["echo"] = int(min(echo, max(2, n // 3)))
        elif si > 0 and si < len(clips) and n > 0:
            # a morph landing: the layer was showing where this shot will land, and it must not vanish on the frame
            # of the handoff, so it fades out over the head of the shot (a third of a second)
            prev = None if in_place(si, "last") else frame(si, "last")
            if prev is not None:
                entry["prev"] = prev
                entry["echo"] = int(min(max(2, int(round(FADE_S * fps))), max(2, n // 3)))
        out.append(entry if (entry["target"] is not None or entry["prev"] is not None) else None)
    return out


def edge_frame(clip: Path, which: str = "last") -> np.ndarray:
    """The first or last frame of a clip, as HxWx3 uint8 that owns its memory. ffmpeg decodes one frame (the
    first) or the last quarter second (the last) instead of the whole clip, so a four-minute Final cut's thirty
    clips do not sit decoded in the parent while the workers run; the whole-clip reader is the fallback."""
    import subprocess

    from xenoform.beatfx import _ffmpeg, read_frames

    clip = Path(clip)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(clip)], capture_output=True, text=True)
    try:
        w, h = (int(v) for v in probe.stdout.strip().split(",")[:2])
    except ValueError:
        w, h = 0, 0
    if w > 0 and h > 0:
        args = [_ffmpeg(), "-v", "error"] + ([] if which == "first" else ["-sseof", "-0.25"]) + ["-i", str(clip), "-f", "rawvideo", "-pix_fmt", "rgb24"]
        args += (["-frames:v", "1"] if which == "first" else []) + ["-"]
        raw = subprocess.run(args, capture_output=True).stdout
        n = len(raw) // (w * h * 3)
        if n >= 1:
            frames = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
            return np.array(frames[0] if which == "first" else frames[-1], dtype=np.uint8, copy=True)
    frames = read_frames(clip)
    if len(frames) == 0:
        raise RuntimeError(f"{clip} has no frames")
    return np.array(frames[0] if which == "first" else frames[-1], dtype=np.uint8, copy=True)


# ------------------------------------------------------------------------------------------------ the amount


def ramp(k: int, n: int, lead: int) -> float:
    """0 until the last ``lead`` frames of an ``n``-frame shot, then a smoothstep up to 1 at the handoff."""
    if lead <= 0 or n <= 0:
        return 0.0
    u = (k - (n - lead)) / float(lead)
    if u <= 0:
        return 0.0
    u = min(1.0, u)
    return u * u * (3 - 2 * u)


def echo_ramp(k: int, echo: int) -> float:
    """1 at the cut, down to 0 after ``echo`` frames."""
    if echo <= 0 or k >= echo:
        return 0.0
    u = 1.0 - k / float(echo)
    return u * u


def amount(base: float, stem: float, cap: float) -> float:
    """The opacity for a frame: the ramp (``base``), lifted by the stem (half floor, half stem), under the cap."""
    return float(np.clip(cap * base * (0.5 + 0.5 * float(np.clip(stem, 0.0, 1.0))), 0.0, 1.0))


# ------------------------------------------------------------------------------------------------ treatments


def _blur(a: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return a
    if cv2 is not None:
        k = 2 * radius + 1
        return cv2.GaussianBlur(np.ascontiguousarray(a, dtype=np.float32), (k, k), 0)
    out = a.astype(np.float32)  # a separable box blur, twice, as the fallback (close enough to a Gaussian)
    kernel = np.ones(2 * radius + 1, dtype=np.float32) / float(2 * radius + 1)
    for _ in range(2):
        for axis in (0, 1):
            out = np.apply_along_axis(lambda v: np.convolve(v, kernel, mode="same"), axis, out)
    return out


def _edges(img: np.ndarray) -> np.ndarray:
    g = img.astype(np.float32).mean(axis=2)
    if cv2 is not None:
        gx = cv2.Sobel(np.ascontiguousarray(g), cv2.CV_32F, 1, 0, ksize=3) * 0.25
        gy = cv2.Sobel(np.ascontiguousarray(g), cv2.CV_32F, 0, 1, ksize=3) * 0.25
    else:
        gx = np.zeros_like(g)
        gy = np.zeros_like(g)
        gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
        gy[1:-1] = g[2:] - g[:-2]
    return np.clip(np.hypot(gx, gy) / 90.0, 0, 1)


def _subject(img: np.ndarray) -> np.ndarray:
    """A soft 0..1 mask of the subject: distance from the frame's own border colour, blurred."""
    a = img.astype(np.float32)
    h, w = a.shape[:2]
    bh, bw = max(1, h // 16), max(1, w // 16)
    ring = np.concatenate([a[:bh].reshape(-1, 3), a[-bh:].reshape(-1, 3), a[:, :bw].reshape(-1, 3), a[:, -bw:].reshape(-1, 3)])
    border = ring.mean(axis=0)
    dist = np.abs(a - border[None, None, :]).mean(axis=2)
    mask = np.clip((dist - 20.0) / 40.0, 0, 1)
    return np.clip(_blur(mask, max(1, min(h, w) // 120)), 0, 1)


def _screen(base: np.ndarray, layer: np.ndarray, a: float) -> np.ndarray:
    return 255.0 - (255.0 - base) * (255.0 - layer * a) / 255.0


def _dilate(e: np.ndarray) -> np.ndarray:
    """A 3x3 max: the trace drawn a pixel thicker each side, so it reads as an outline, not a hairline."""
    out = e.copy()
    out[1:, :] = np.maximum(out[1:, :], e[:-1, :])
    out[:-1, :] = np.maximum(out[:-1, :], e[1:, :])
    out[:, 1:] = np.maximum(out[:, 1:], out[:, :-1])
    out[:, :-1] = np.maximum(out[:, :-1], out[:, 1:])
    return out


def treat(frame: np.ndarray, target: np.ndarray, mode: str, a: float, *, tint=(255, 255, 255), p: dict | None = None,
          si: int = 0, k: int = 0, seed: int = 0, pop: float = 0.0) -> np.ndarray:
    """``target`` brought into ``frame`` at opacity ``a`` (0..1) in ``mode``. Both HxWx3 uint8, same size. ``a`` 0
    returns the frame untouched. ``si`` and ``k`` seed the slices' order and jitter so they accumulate frame to
    frame instead of flickering. ``pop`` (the beat pulse, 0..1) flashes the outline modes brighter on a hit: an
    edge-only flash, so the frame's mean luma barely moves and the flash cap is safe."""
    if a <= 1e-3 or frame.shape != target.shape:
        return frame
    a = min(1.0, a * MODE_GAIN.get(mode, 1.0))
    if mode in ("trace", "silhouette") and pop > 0:
        a = min(1.0, a * (1.0 + 0.8 * float(np.clip(pop, 0.0, 1.0))))
    p = p or {}
    f = frame.astype(np.float32)
    t = target.astype(np.float32)
    col = np.asarray(tint, dtype=np.float32).reshape(1, 1, 3) / 255.0
    h, w = f.shape[:2]
    if mode == "trace":
        e = _dilate(_edges(target))
        halo = _blur(e, max(1, int(round(2 + 6 * float(p.get("glow", 0.6))))))
        layer = (np.clip(e * 1.4, 0, 1) + halo * float(p.get("glow", 0.6)))[..., None] * col * 255.0
        out = _screen(f, layer, a)
    elif mode == "negative":
        L = t.mean(axis=2, keepdims=True)
        ghost = np.clip(t + (255.0 - 2.0 * L), 0, 255)  # luma flipped, hue kept
        mask = _subject(target)[..., None]
        out = _screen(f, ghost * mask, a * 0.9)
    elif mode == "slices":
        n = max(2, int(p.get("slices", 8)))
        rng = np.random.default_rng(seed * 1000 + si)
        order = rng.permutation(n)
        horizontal = si % 2 == 0
        count = max(1, int(math.ceil(a / max(1e-6, float(p.get("cap", 0.8))) * n)))
        jitter = float(p.get("jitter", 0.3))
        out = f.copy()
        strength = min(1.0, 0.25 + 0.75 * a / max(1e-6, float(p.get("cap", 0.8))))  # no band pops in at 55 %: it grows with the amount
        for idx in order[:count]:
            if horizontal:
                y0, y1 = int(h * idx / n), int(h * (idx + 1) / n)
                shift = int(round((rng.random() - 0.5) * jitter * 0.12 * w)) if jitter > 0 else 0
                band = np.roll(t[y0:y1], shift, axis=1)
                out[y0:y1] = out[y0:y1] * (1 - strength) + band * strength
            else:
                x0, x1 = int(w * idx / n), int(w * (idx + 1) / n)
                shift = int(round((rng.random() - 0.5) * jitter * 0.12 * h)) if jitter > 0 else 0
                band = np.roll(t[:, x0:x1], shift, axis=0)
                out[:, x0:x1] = out[:, x0:x1] * (1 - strength) + band * strength
    elif mode == "silhouette":
        mask = _subject(target)[..., None]
        fill = mask * col * 255.0
        e = _dilate(_edges(target))[..., None] * col * 255.0
        out = _screen(f, fill * 0.75 + e, a)
    else:
        return frame
    return np.clip(out, 0, 255).astype(np.uint8)


def info(entries: list[dict | None], mode: str, p: dict, fps: int) -> dict:
    """What the record says about the layer."""
    applied = [e for e in entries if e]
    leads = [e["lead"] for e in applied if e.get("target") is not None]
    return {"mode": mode or "off", "shots": len(leads), "echoes": sum(1 for e in applied if e.get("prev") is not None),
            "lead_s": round(float(np.mean(leads)) / fps, 2) if leads else 0.0, "params": dict(p)}
