"""What a morph asks LTX for: the prompt, the negative, the length, the tuning, the style and the timing.

The desk's own rules (``xenoform.morph_pass``, ``xenoform.morph_style``, ``xenoform.morph_timing``), copied with no desk
import: the prompt is one a vibe and a style (the two guide stills carry the objects), a pair that touches a scene or a
setting gets that pair's prompt, the length is the next 8k + 1 frames LTX takes (25 to 121), and the tuning is the
vibe's ``ltx`` block with ``configs/autotune.json`` over it. tests/test_comfy_pack_plan.py holds these to the desk's.

The vibe registry and the autotune file are read from the repository's ``configs/`` when the pack sits in the whole
repository (``custom_nodes/xenoform/comfy_pack``), else from the copies in ``comfy_pack/data`` (a test keeps them equal).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

PACK = Path(__file__).resolve().parent
REPO_CONFIGS = PACK.parent / "configs"
DATA = PACK / "data"

FPS = 24
WIDTH, HEIGHT = 512, 288  # the Draft morph size (morph_pass: XENO_MORPH_SIZE's default)
PORTRAIT = (320, 576)  # Draft 9:16 renders natively in portrait (dense.DRAFT_916)
OUT_SIZE = {"16:9": (768, 432), "9:16": (432, 768)}  # the assembled cut's size (morph_pass.OUT_W x OUT_H)
STEPS = 20
MIN_LEN, MAX_LEN = 25, 121
GRAPH_DEFAULTS = {"cfg": 3.0, "img_compression": 18, "guide_end_strength": 1.0}  # workflows/xenoform_morph.json's own

VIBE_LOOK = {
    "liquid-gold": "molten gold and liquid mercury, warm amber studio glow, dark umber backdrop",
    "bloom": "iridescent petals and pearly glass, soft magenta rim light, fresh spring-green backdrop",
    "neon-night": "rain-slick black glass and smoked chrome, hot magenta and sodium-amber neon reflections, deep crimson-black backdrop",
    "ocean": "iridescent shell and chrome, aqua caustic light, deep teal water backdrop",
    "cosmic": "iridescent glass and pearl, cobalt and violet glow, deep indigo backdrop",
    "paper-summer": "folded white paper and glazed porcelain, warm morning sunlight, soft cream backdrop",
    "black": "black glass and iridescent liquid metal, violet and teal edge light, pure black void, no floor",
}
NEGATIVE = ("text, letters, watermark, logo, two objects, duplicated features, extra copies, cut, flicker, "
            "blurry, low quality, cartoon, cartoonish, warped, people, hands")
ORIGINAL_NAMES = {"liquid-gold": "Liquid gold", "paper-summer": "Paper summer", "bloom": "Bloom", "neon-night": "Neon night",
                  "ocean": "Ocean", "cosmic": "Cosmic", "black": "Black"}

SCENE_OPENINGS = {
    ("scene", "object"): "A wide landscape scene slowly melts and flows into one single sculptural object that forms at its centre",
    ("object", "scene"): "One single sculptural object slowly melts and spreads out into a wide landscape scene",
    ("scene", "scene"): "A wide landscape scene slowly melts and flows into another wide landscape scene",
    ("scene", "setting"): "A wide landscape scene slowly melts and gathers into one object standing in a place at its centre",
    ("setting", "scene"): "The object standing in its place slowly melts and spreads out into a wide landscape scene",
}
SETTING_OPENINGS = {
    ("object", "setting"): "One single sculptural object slowly transforms into another while a place slowly grows around it",
    ("setting", "object"): "The object standing in its place slowly transforms into another while the place slowly fades away around it",
}
SETTING_TAIL = ("the object stays large and whole in the middle of the frame, the camera steady, {look}, one single object, every "
                "feature appears once, cinematic photograph, crisp, clean, high detail")
# the clauses of a look that name its ground (stills.GROUND_WORDS): a pair in a place drops them
GROUND_WORDS = ("backdrop", "void", "no floor", "studio", "seamless", "on pure black", "black background")

# ---- morph_style: how A becomes B
STYLES = ("melt", "shatter", "bloom", "spin", "fold")
OPENINGS = {
    "melt": "One single sculptural object slowly melts and flows into another, one continuous liquid transformation",
    "shatter": "One single sculptural object cracks and shatters into hundreds of glittering shards that swirl and snap "
               "together into another object, one continuous transformation",
    "bloom": "One single sculptural object unfolds like a blooming flower, its petals opening and peeling back as another "
             "object grows out of its centre, one continuous organic transformation",
    "spin": "One single sculptural object spins fast on its axis and changes shape as it turns, slowing to reveal another "
            "object, one continuous transformation",
    "fold": "One single sculptural object folds and creases like paper origami, its flat planes flipping and refolding "
            "into another object, one continuous transformation",
}
STYLE_LABELS = {"auto": "Auto", "melt": "Melt", "shatter": "Shatter", "bloom": "Bloom", "spin": "Spin", "fold": "Fold"}
STYLE_NOTES = {
    "auto": "Melt through the verses, Shatter on the drop; the opening Blooms, or with Chaos past 0.6 the builds Fold and "
            "the loud shots after the drop Spin.",
    "melt": "The object melts and flows into the next: one continuous liquid change.",
    "shatter": "The object cracks into shards that swirl and snap together as the next.",
    "bloom": "The object opens like a flower, and the next grows out of its centre.",
    "spin": "The object spins and changes shape as it turns: the most motion.",
    "fold": "The object folds like paper, its planes flipping into the next.",
}
CALM_CHAOS, WILD_CHAOS = 0.15, 0.6
LOUD = ("drop", "drop_late", "build")

# ---- morph_timing: when the change happens inside the shot
TIMINGS = ("smooth", "beat", "snap")
TIMING_LABELS = {"smooth": "Smooth", "beat": "On the beat", "snap": "Snap"}
TIMING_NOTES = {
    "smooth": "The morph plays at an even speed: the change happens wherever the model put it.",
    "beat": "The change moves in steps, fastest on every beat inside the shot, nearly still between them.",
    "snap": "The object holds, then changes in about a beat on the shot's downbeat; the drop snaps hardest.",
}
DRIFT = {"beat": 0.3, "snap": 0.12}
TIMING_WIDTH = {"beat": 0.16, "snap": 0.2}
DROP_WIDTH = 0.1
DROP_LAG = 0.25


# ------------------------------------------------------------------------------------------------ the data files


def _read_json(*paths: Path) -> dict:
    for path in paths:
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


@lru_cache(maxsize=1)
def registry() -> dict:
    """The vibe registry: the repository's ``configs/vibes.json`` when the pack sits in the repository, else the copy."""
    return _read_json(REPO_CONFIGS / "vibes.json", DATA / "vibes.json") or {"vibes": []}


@lru_cache(maxsize=1)
def autotune() -> dict:
    return _read_json(REPO_CONFIGS / "autotune.json", DATA / "autotune.json")


def extended() -> list[dict]:
    """The registry vibes that ship assets (``vibes.extended``: ``ready`` is not false)."""
    return [v for v in registry().get("vibes") or [] if v.get("ready", True)]


def vibe_row(vibe: str) -> dict:
    return next((v for v in extended() if v.get("id") == vibe), {})


def looks() -> dict[str, str]:
    """``morph_pass.VIBE_LOOK`` as the desk has it: the seven originals, with the registry's looks over them."""
    return {**VIBE_LOOK, **{str(v["id"]): str(v["look"]) for v in extended() if v.get("id") and v.get("look")}}


def look_of(vibe: str) -> str:
    """The vibe's look words, or liquid gold's for a vibe the desk does not know (``VIBE_LOOK.get(vibe, liquid-gold)``)."""
    table = looks()
    return table.get(vibe, table["liquid-gold"])


def name_of(vibe: str) -> str:
    return ORIGINAL_NAMES.get(vibe) or str(vibe_row(vibe).get("name") or vibe)


def tuned(vibe: str) -> dict:
    """The vibe's LTX 0.9.5 settings: its registry ``ltx`` block with autotune over it (``morph_pass.tuned``)."""
    return {**dict(vibe_row(vibe).get("ltx") or {}), **dict((autotune().get("vibes") or {}).get(vibe) or {})}


def bad_pairs() -> set[tuple[str, str]]:
    return {tuple(p) for p in autotune().get("bad_pairs") or [] if isinstance(p, (list, tuple)) and len(p) == 2}


# ------------------------------------------------------------------------------------------------ the prompt


def place_look(look: str) -> str:
    parts = [p.strip() for p in str(look or "").split(",")]
    kept = [p for p in parts if p and not any(w in p.lower() for w in GROUND_WORDS)]
    return ", ".join(kept).strip().rstrip(".")


def pair_kinds(a: dict | None, b: dict | None) -> tuple[str, str]:
    out = []
    for row in (a, b):
        kind = str((row or {}).get("kind") or "")
        out.append(kind if kind in ("scene", "setting") else "object")
    return tuple(out)


def guide_compression(kinds: tuple[str, str] | None, value) -> tuple[int, int]:
    kinds = tuple(kinds) if kinds else ("object", "object")
    return tuple(0 if k == "scene" else int(value) for k in kinds[:2])


def normal_style(value, allow_auto: bool = True) -> str:
    v = str(value or "").strip().lower()
    if v == "auto" and allow_auto:
        return "auto"
    return v if v in STYLES else "melt"


def prompt_for(vibe: str, kinds: tuple[str, str] | None = None, style: str = "melt") -> str:
    """One prompt a vibe and style (``morph_pass.prompt_for`` for LTX 0.9.5); a pair that touches a scene or a setting
    gets that pair's prompt."""
    look = look_of(vibe)
    kinds = tuple(kinds) if kinds else ("object", "object")
    opening = SCENE_OPENINGS.get(kinds)
    if opening:
        return (f"{opening}, one continuous liquid transformation, the picture never cuts, the frame stays steady, "
                f"gentle slow camera drift, {look}, every feature appears once, cinematic, crisp, clean, high detail")
    if "setting" in kinds:
        tail = SETTING_TAIL.format(look=place_look(look) or "its own materials and light")
        if kinds == ("setting", "setting"):
            return f"{OPENINGS[normal_style(style, allow_auto=False)]}, while the place around it slowly shifts with it, {tail}"
        return f"{SETTING_OPENINGS[kinds]}, one continuous transformation, the picture never cuts, {tail}"
    return (f"{OPENINGS[normal_style(style, allow_auto=False)]}, the object stays centred, gentle slow camera drift, {look}, "
            "one single object, every feature appears once, macro product photography, crisp, clean, high detail")


def gen_length(frames: int) -> int:
    """The latent length LTX takes for ``frames``: the next 8k + 1, at least 25 and at most 121."""
    n = 8 * math.ceil(max(frames - 1, 0) / 8) + 1
    return int(min(MAX_LEN, max(MIN_LEN, n)))


def render_frames(shot: dict) -> int:
    """How many frames of source a shot's morph renders (``cloud_morph._local_clips``): its ``render_s``, at most 5 s."""
    return int(round(min(float(shot.get("render_s") or shot.get("seconds") or 2.0), 5.0) * FPS))


# ------------------------------------------------------------------------------------------------ styles


def drop_index(shots: list[dict], drop: float | None) -> int | None:
    if drop is None or not shots:
        return None
    d = float(drop)
    for i, s in enumerate(shots):
        if float(s.get("start") or 0.0) >= d - 0.05:
            return i
    return None


def _building(shot: dict, drop: float | None) -> bool:
    if str(shot.get("section") or "") == "build":
        return True
    return drop is not None and float(shot.get("start") or 0.0) < float(drop) and abs(float(shot.get("end") or 0.0) - float(drop)) < 0.05


def _loud(shot: dict, drop: float | None) -> bool:
    section = str(shot.get("section") or "")
    if section:
        return section in LOUD
    return drop is not None and float(shot.get("start") or 0.0) >= float(drop) - 1e-3


def auto_styles(shots: list[dict], drop: float | None = None, chaos: float = 0.3) -> list[str]:
    """Auto (``morph_style.auto``): Melt through the verses and Shatter on the drop; under Chaos 0.6 the opening Blooms;
    from 0.6 the builds Fold and every other loud shot after the drop Spins; at 0.15 or less every morph melts."""
    n = len(shots)
    styles = ["melt"] * n
    if not n or float(chaos) <= CALM_CHAOS:
        return styles
    d = drop_index(shots, drop)
    if d is not None:
        styles[d] = "shatter"
    if float(chaos) >= WILD_CHAOS:
        for i, s in enumerate(shots):
            if styles[i] != "melt":
                continue
            if (d is None or i < d) and _building(s, drop):
                styles[i] = "fold"
            elif d is not None and i > d and (i - d) % 2 == 0 and _loud(s, drop):
                styles[i] = "spin"
    elif n > 1 and styles[0] == "melt":
        styles[0] = "bloom"
    return styles


def styles_for(setting: str, shots: list[dict], drop: float | None, chaos: float) -> list[str]:
    setting = normal_style(setting)
    if setting != "auto":
        return [setting] * len(shots)
    return auto_styles(shots, drop, chaos)


# ------------------------------------------------------------------------------------------------ timing


def normal_timing(value) -> str:
    v = str(value or "").strip().lower().replace(" ", "")
    v = {"onthebeat": "beat", "beats": "beat", "even": "smooth"}.get(v, v)
    return v if v in TIMINGS else "smooth"


def _beat_period(beats: list[float]) -> float:
    b = sorted(float(x) for x in beats or [])
    gaps = [y - x for x, y in zip(b, b[1:]) if y - x > 0.05]
    return float(np.median(gaps)) if gaps else 0.5


def _skip_timing(shot: dict) -> bool:
    return bool(shot.get("hold") or shot.get("performer") or shot.get("own") or shot.get("dream"))


def plan_timing(shots: list[dict], mode: str, beats: list[float], drop: float | None = None,
                overrides: dict | None = None) -> dict:
    """``morph_timing.plan``: put ``timing`` (the hits in song seconds, the width, the drift) on the shots it applies to."""
    mode = normal_timing(mode)
    beats = sorted(float(b) for b in beats or [])
    period = _beat_period(beats)
    downbeats = beats[::4]
    counts: dict[str, int] = {}
    for i, s in enumerate(shots):
        prior = s.pop("timing", None)
        own = (overrides or {}).get(i) or (overrides or {}).get(str(i)) or {}
        preset = prior.get("mode") if isinstance(prior, dict) and not prior.get("hits") else None
        m = normal_timing(own.get("timing")) if own.get("timing") else normal_timing(preset) if preset else mode
        if m == "smooth" or _skip_timing(s):
            continue
        a, b = float(s.get("start") or 0.0), float(s.get("end") or 0.0)
        if s.get("rest_s"):
            b = max(a + 0.25, b - float(s["rest_s"]))
        dur = b - a
        if dur <= 0.2:
            continue
        width = TIMING_WIDTH[m] * period
        if m == "beat":
            hits = [t for t in beats if a + 0.12 * dur < t < b - 0.08 * dur] or [a + dur / 2]
        elif (drop is not None and abs(a - float(drop)) < 0.05) or s.get("event") == "drop":
            hits, width = [a + DROP_LAG * period], DROP_WIDTH * period
        else:
            inside = [t for t in downbeats if a + 0.1 * dur < t < b - 0.1 * dur]
            near = [t for t in beats if a + 0.1 * dur < t < b - 0.1 * dur]
            hits = inside[:1] or sorted(near, key=lambda t: abs(t - (a + dur / 2)))[:1] or [a + dur / 2]
        s["timing"] = {"mode": m, "hits": [round(t, 4) for t in hits], "width": round(width, 4), "drift": DRIFT[m]}
        counts[m] = counts.get(m, 0) + 1
    return counts


def progress(frames: np.ndarray, step: int = 4) -> np.ndarray:
    """How far along its change each source frame is (``morph_timing.progress``): the cumulative mean absolute
    difference from frame to frame, kept strictly rising, 0 at the first frame and 1 at the last."""
    n = len(frames)
    if n < 2:
        return np.zeros(n, np.float64)
    grey = np.asarray(frames)[:, ::step, ::step].astype(np.float32).mean(axis=3)
    d = np.abs(np.diff(grey, axis=0)).mean(axis=(1, 2)).astype(np.float64)
    d += max(float(d.mean()) * 1e-3, 1e-6)
    cum = np.concatenate([[0.0], np.cumsum(d)])
    return cum / cum[-1]


def timing_target(shot: dict, count: int, fps: float = 24.0) -> np.ndarray | None:
    timing = shot.get("timing") or {}
    if timing.get("mode") not in ("beat", "snap") or count < 2:
        return None
    a, b = float(shot.get("start") or 0.0), float(shot.get("end") or 0.0)
    s = np.linspace(0.0, 1.0, count)
    t = a + s * (b - a)
    width = max(float(timing.get("width") or 0.08), 1.0 / float(fps))
    hits = [float(h) for h in timing.get("hits") or []] or [a + (b - a) / 2]
    steps = np.mean([1.0 / (1.0 + np.exp(-(t - h) / width)) for h in hits], axis=0)
    lo, hi = float(steps[0]), float(steps[-1])
    stepped = (steps - lo) / (hi - lo) if hi - lo > 1e-6 else s
    drift = float(timing.get("drift", 0.2))
    return drift * s + (1.0 - drift) * stepped


def timing_indices(shot: dict, count: int, prog: np.ndarray, fps: float = 24.0) -> np.ndarray | None:
    want = timing_target(shot, count, fps)
    if want is None or prog is None or len(prog) < 2:
        return None
    return np.interp(want, prog, np.arange(len(prog), dtype=np.float64))
