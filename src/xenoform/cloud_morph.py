"""Cloud quality: an optional, off-by-default LTX-2.5 morph chain for Simple mode.

PAID ADD-ON. The ``LtxApi25ImageToVideo`` partner node renders on Lightricks'
servers and bills Comfy credits to the account whose API key rides with the job.
The default path stays open weights: this module only spends when every gate
below is open, and the result is labelled ``cloud-rendered (LTX-2.5 partner node)``.

The planner splits the song into beat-aligned shots of about 5 s. Each shot's
render length is snapped to a duration the node accepts (2/3/4/5/6/8/10 s) and
retimed to the exact scene length afterwards, so every handoff lands on the
beat grid. Stills chain A->B->C: shot i ends on the still shot i+1 starts from.

Engines, same plan and stills for all three:

* ``local``  LTX 0.9.5 morph graph on this GPU (free). The draft that plays while
             the cloud renders, and the fallback when it fails.
* ``cloud``  every shot as one ``LtxApi25ImageToVideo`` node inside ONE ComfyUI
             prompt, so ComfyUI awaits them concurrently (async API nodes).
* ``mock``   dry run: the cloud graph is built and validated against
             ``/object_info`` (read only) and the clips are cross-fades of the
             stills. Nothing is submitted.

OFF BY DEFAULT, OPT-IN ONLY. Nothing in this module is reachable unless paid cloud
renders were switched on: the desk setting "Paid cloud renders (partner node, not
open weights)" or ``XENO_PAID_CLOUD=1``. ``XENO_PAID_CLOUD=0`` forces it off even
when the desk asks. With it off, the estimate route answers 403, the Simple mode
toggle is hidden, and a Make that still says ``cloud_quality`` runs the open-weights
morph pass instead.

Gates before a paid submit (all required): paid cloud renders switched on;
``state.cloud_quality``; not dry run;
a confirm token minted by ``/api/cloud/estimate`` and clicked by the user whose
confirmed price covers the real plan; the plan under the per-clip cap
(``XENO_CLOUD_CAP_USD``, default US$5); the key in ``COMFY_ORG_API_KEY``; the
graph valid against the installed node; and ``XENO_CLOUD_NEVER`` unset.
The key is never logged, stored, or written to the plan file.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import secrets
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

import numpy as np

log = logging.getLogger("xenoform.cloud_morph")

ROOT = Path(__file__).resolve().parents[2]
PARTNER_NODE = "LtxApi25ImageToVideo"
PARTNER_GRAPH = ROOT / "workflows" / "ltx25_partner_flf_api.json"
LABEL = "cloud-rendered (LTX-2.5 partner node)"
KEY_ENV = "COMFY_ORG_API_KEY"
PAID_ENV = "XENO_PAID_CLOUD"
OPT_IN_LABEL = "Paid cloud renders (partner node, not open weights)"
OFF_MESSAGE = (
    f"Paid cloud renders are off. The default path is open weights only. Turn on "
    f"\"{OPT_IN_LABEL}\" in Settings, or start the desk with {PAID_ENV}=1."
)
_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off"}
ALLOWED_S = (2, 3, 4, 5, 6, 8, 10)
MODELS = {"fast": "LTX-2.5 (Fast)", "pro": "LTX-2.5 (Pro)"}
RESOLUTION = "1280x720"
FPS = 24
SHOT_TARGET_S = 5.0
CREDITS_PER_USD = 211.0  # Comfy partner pricing
AUD_PER_USD = 1.44
FALLBACK_USD_PER_S = {"fast": {"1280x720": 0.1287}, "pro": {"1280x720": 0.1716}}
DEFAULT_CAP_USD = 5.0
TOKEN_TTL_S = 30 * 60
DEFAULT_PROMPT = (
    "Black-glass and liquid-metal organism on pure black void, iridescent violet and teal edge light, "
    "the form melts and regrows as one continuous fluid transformation, surface tension, ferrofluid "
    "ripples, grown not built, slow graceful motion that surges on the beat, macro lens, crisp detail, "
    "no cuts, no text"
)
# rose -> jellyfish -> butterfly -> swallow -> a swarm of drops: the first five of the black pool.
BLACK_CHAIN = ("rose", "jellyfish", "butterfly", "swallow", "drop swarm")
_SECRET = secrets.token_bytes(32)
_USED: set[str] = set()  # a confirm token pays for one clip, once


class CloudRefused(RuntimeError):
    """A gate is closed. Nothing was submitted and nothing was spent."""


# ---------------------------------------------------------------- planning


def snap_duration(seconds: float) -> int:
    """Nearest render length the node accepts; ties go up so a morph never runs short."""
    s = max(float(seconds), ALLOWED_S[0])
    return min(ALLOWED_S, key=lambda a: (abs(a - s), -a))


def plan_shots(duration: float, beats: list | None = None, target: float = SHOT_TARGET_S) -> list[dict]:
    """Beat-aligned shots of about ``target`` seconds covering ``[0, duration]``.

    A cut lands on the nearest beat within 1 s of every ``target`` mark; the last
    shot takes the remainder (never under 2 s, never over 7 s before snapping).
    """
    duration = max(float(duration or 0.0), 0.5)
    grid = sorted(float(b) for b in (beats or []) if 0.0 < float(b) < duration)
    bounds = [0.0]
    while duration - bounds[-1] > target * 1.4:
        want = bounds[-1] + target
        if grid:
            near = min(grid, key=lambda b: abs(b - want))
            if abs(near - want) <= 1.0 and near - bounds[-1] >= 2.0:
                want = near
        bounds.append(round(want, 4))
    bounds.append(round(duration, 4))
    shots = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        shots.append({"index": i, "start": a, "end": b, "seconds": round(b - a, 4),
                      "frames": max(2, int(round(b * FPS)) - int(round(a * FPS))),
                      "render_s": snap_duration(b - a)})
    return shots


# ---------------------------------------------------------------- custom cut points
#
# A cut plan (``state["cut_plan"]``) replaces the even ~5 s grid with hand-placed shots:
#   {"stills": ["rose", "jellyfish", ...],            # optional, len(shots) + 1, nouns from the vibe pool
#    "shots": [{"start": 0.0, "end": 3.275,           # seconds on the song
#               "render_s": 3,                         # optional: an allowed partner duration, 2 s minimum
#               "speed": 0.92,                         # optional: playback factor (render_s / slot)
#               "ease": "in",                          # optional: "in" accelerates into the end (a speed ramp)
#               "effects": [{"type": "punch", "t": 1.216, "strength": 1.0},
#                           {"type": "stutter", "t": 1.216, "frames": 2, "repeat": 3},
#                           {"type": "hold", "t": 13.77, "len": 0.12},
#                           {"type": "skip", "t": 13.9, "amount": 0.25},
#                           {"type": "reverse", "t": 19.2, "len": 0.405}]}, ...]}
# Only render_s costs money (it is what the partner node renders). Speed, ease and every
# effect are free post-processing in ``stitch``.

EFFECT_TYPES = ("punch", "stutter", "hold", "skip", "reverse")
SPEED_TOLERANCE = 0.2


class CutPlanError(ValueError):
    """A cut plan that cannot be rendered as written."""


def snap_up(seconds: float) -> int:
    """The shortest allowed partner duration that covers ``seconds`` (2 s minimum)."""
    return next((d for d in ALLOWED_S if d >= seconds - 1e-6), ALLOWED_S[-1])


def custom_shots(plan: dict, duration: float | None = None) -> list[dict]:
    """Validate a cut plan and return shots in the same shape ``plan_shots`` gives, plus speed/ease/effects."""
    raw = list((plan or {}).get("shots") or [])
    if not raw:
        raise CutPlanError("The cut plan has no shots.")
    shots: list[dict] = []
    prev_end = 0.0
    for i, item in enumerate(raw):
        start, end = float(item["start"]), float(item["end"])
        if abs(start - prev_end) > 0.5 / FPS:
            raise CutPlanError(f"Shot {i + 1} starts at {start:.3f}s but the previous one ends at {prev_end:.3f}s.")
        seconds = end - start
        if seconds < 0.25:
            raise CutPlanError(f"Shot {i + 1} is {seconds:.3f}s; the shortest slot is 0.25s.")
        want = item.get("speed")
        if item.get("render_s") is not None:
            render_s = int(item["render_s"])
            if render_s not in ALLOWED_S:
                raise CutPlanError(f"Shot {i + 1}: render_s {render_s} is not an allowed duration {ALLOWED_S}.")
        else:
            render_s = snap_up(float(want) * seconds if want else seconds)
        speed = render_s / seconds
        if want is not None and abs(speed - float(want)) > SPEED_TOLERANCE * float(want):
            raise CutPlanError(f"Shot {i + 1}: {render_s}s rendered into a {seconds:.3f}s slot plays at {speed:.2f}x, "
                               f"not the {float(want):.2f}x asked for.")
        ease = str(item.get("ease") or "")
        if ease not in ("", "in", "out"):
            raise CutPlanError(f"Shot {i + 1}: ease must be 'in', 'out' or empty.")
        effects = []
        for fx in item.get("effects") or []:
            kind = str(fx.get("type") or "")
            if kind not in EFFECT_TYPES:
                raise CutPlanError(f"Shot {i + 1}: unknown effect {kind!r}; use one of {EFFECT_TYPES}.")
            t = float(fx.get("t", start))
            if not start - 1e-6 <= t < end:
                raise CutPlanError(f"Shot {i + 1}: {kind} at {t:.3f}s is outside {start:.3f}-{end:.3f}s.")
            effects.append({**fx, "type": kind, "t": round(t, 4)})
        shots.append({"index": i, "start": round(start, 4), "end": round(end, 4), "seconds": round(seconds, 4),
                      "render_s": render_s, "speed": round(speed, 3), "ease": ease, "effects": effects})
        prev_end = end
    if duration and prev_end > float(duration) + 0.05:
        raise CutPlanError(f"The cut plan ends at {prev_end:.3f}s, past the {float(duration):.3f}s song.")
    edges = [round(s["start"] * FPS) for s in shots] + [round(shots[-1]["end"] * FPS)]
    for shot, a, b in zip(shots, edges[:-1], edges[1:]):
        shot["frames"] = int(b - a)
    return shots


def shot_indices(shot: dict, n_src: int) -> np.ndarray:
    """Which source frame plays on each output frame: speed (linear), ease, then the in-shot effects.

    The shot always starts on frame 0 (still A) and ends on the last frame (still B), so the
    chain stays continuous across handoffs whatever the effects do in between.
    """
    count = int(shot["frames"])
    last = max(n_src - 1, 0)
    u = np.linspace(0.0, 1.0, count) if count > 1 else np.zeros(count)
    if shot.get("ease") == "in":
        u = u ** 1.6
    elif shot.get("ease") == "out":
        u = 1 - (1 - u) ** 1.6
    idx = u * last
    step = last / max(count - 1, 1)
    for fx in shot.get("effects") or []:
        k0 = int(round((float(fx["t"]) - float(shot["start"])) * FPS))
        if not 0 <= k0 < count:
            continue
        kind = fx["type"]
        if kind == "hold":
            n = max(1, int(round(float(fx.get("len", 0.12)) * FPS)))
            idx[k0:min(count - 1, k0 + n)] = idx[k0]
        elif kind == "stutter":
            size, rep = max(1, int(fx.get("frames", 2))), max(2, int(fx.get("repeat", 3)))
            for k in range(k0, min(count - 1, k0 + size * rep)):
                idx[k] = idx[k0 + (k - k0) % size]
        elif kind == "skip":
            jump = float(fx.get("amount", 0.25)) * FPS  # source frames to lurch ahead
            tail = np.arange(count - k0)
            idx[k0:] = idx[k0:] + jump * (1 - tail / max(count - k0 - 1, 1))
        elif kind == "reverse":
            n = max(2, int(round(float(fx.get("len", 0.4)) * FPS)))
            n = min(n, count - 1 - k0)
            half = n // 2
            if half < 1:
                continue
            back = idx[k0] - np.arange(half) * step
            fwd = np.linspace(back[-1], idx[min(count - 1, k0 + n)], n - half + 1)[:-1]
            idx[k0:k0 + n] = np.concatenate([back, fwd])
    idx = np.clip(np.round(idx), 0, last).astype(int)
    if count:
        idx[0], idx[-1] = 0, last
    return idx


def punch_curve(shots: list[dict]) -> np.ndarray:
    """Per output frame, 0..1: the decaying punch from every ``punch`` effect in the plan."""
    total = sum(int(s["frames"]) for s in shots)
    curve = np.zeros(total, np.float32)
    for fx in (fx for s in shots for fx in s.get("effects") or [] if fx["type"] == "punch"):
        k0 = int(round(float(fx["t"]) * FPS))
        strength = float(fx.get("strength", 1.0))
        for k in range(max(0, k0), min(total, k0 + 16)):
            curve[k] = max(curve[k], strength * np.exp(-(k - k0) / 3.5))
    return curve


def apply_punch(frame: np.ndarray, amount: float) -> np.ndarray:
    """A free zoom punch and exposure flash; numpy only (nearest-neighbour crop, no extra deps)."""
    if amount <= 0.01:
        return frame
    h, w = frame.shape[:2]
    scale = 1.0 + 0.09 * amount
    ys = np.clip(((np.arange(h) - h / 2) / scale + h / 2).astype(int), 0, h - 1)
    xs = np.clip(((np.arange(w) - w / 2) / scale + w / 2).astype(int), 0, w - 1)
    out = frame[ys][:, xs].astype(np.float32)
    out = out * (1.0 + 0.45 * amount) + 18.0 * amount
    return np.clip(out, 0, 255).astype(np.uint8)


def stills_for(state: dict, count: int) -> tuple[str, list[dict]]:
    """The cut plan's own stills when it names them, else the vibe chain."""
    nouns = list(((state.get("cut_plan") or {}).get("stills")) or [])
    if not nouns:
        return chain_stills(state, count)
    from xenoform.morph_pass import OBJECTS, manifest, vibe_for

    vibe = vibe_for(state)
    pool = {item["noun"]: item for item in manifest()[vibe]}
    missing = [n for n in nouns if n not in pool]
    if missing:
        raise CutPlanError(f"Not in the {vibe} pool: {', '.join(missing)}.")
    if len(nouns) < count:
        raise CutPlanError(f"The cut plan names {len(nouns)} stills; {count} shots need {count}.")
    return vibe, [{**pool[n], "path": str(OBJECTS / pool[n]["file"])} for n in nouns[:count]]


def shots_for(state: dict, duration: float, beats: list) -> list[dict]:
    plan = state.get("cut_plan")
    return custom_shots(plan, duration) if plan else plan_shots(duration, beats)


def prices(comfy_url: str | None = None, timeout: float = 5.0) -> tuple[dict, dict | None, str]:
    """USD/s table from the node's own price badge, plus its object_info (or None)."""
    info = None
    if comfy_url:
        try:
            with urllib.request.urlopen(f"{comfy_url.rstrip('/')}/object_info/{PARTNER_NODE}", timeout=timeout) as r:
                info = json.loads(r.read().decode("utf-8")).get(PARTNER_NODE)
        except Exception:
            info = None
    if info:
        import re

        expr = ((info.get("price_badge") or {}).get("expr")) or ""
        table: dict = {}
        for model, body in re.findall(r'"ltx-2\.5 \((fast|pro)\)"\s*:\s*\{([^}]*)\}', expr):
            table[model] = {res: float(v) for res, v in re.findall(r'"(\d+x\d+)"\s*:\s*([0-9.]+)', body)}
        if table:
            return table, info, "live price badge"
    return FALLBACK_USD_PER_S, info, "fallback table"


def cap_usd() -> float:
    try:
        return float(os.environ.get("XENO_CLOUD_CAP_USD") or DEFAULT_CAP_USD)
    except ValueError:
        return DEFAULT_CAP_USD


def estimate(shots: list[dict], model: str = "fast", resolution: str = RESOLUTION, table: dict | None = None) -> dict:
    pps = (table or FALLBACK_USD_PER_S)[model][resolution]
    seconds = sum(int(s["render_s"]) for s in shots)
    usd = round(pps * seconds, 4)
    cap = cap_usd()
    return {"shots": len(shots), "render_seconds": seconds, "usd_per_s": pps, "model": MODELS[model],
            "resolution": resolution, "fps": FPS, "usd": usd, "credits": round(usd * CREDITS_PER_USD, 1),
            "aud": round(usd * AUD_PER_USD, 2), "cap_usd": cap, "over_cap": usd > cap + 1e-9}


# ---------------------------------------------------------------- confirm token


def mint_token(est: dict, now: float | None = None) -> str:
    """What the confirm click sends back: the price the user saw, signed, short-lived."""
    stamp = int(now if now is not None else time.time())
    body = f"{est['usd']:.4f}:{est['render_seconds']}:{stamp}:{secrets.token_hex(4)}"
    sig = hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}:{sig}"


def check_token(token: str, est: dict, now: float | None = None) -> str | None:
    """None when the token covers ``est``; otherwise the reason it does not."""
    try:
        usd_s, secs_s, stamp_s, nonce, sig = str(token or "").split(":")
    except ValueError:
        return "Cloud quality needs the confirm click first."
    body = f"{usd_s}:{secs_s}:{stamp_s}:{nonce}"
    good = hmac.new(_SECRET, body.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(good, sig):
        return "That confirmation is not from this desk. Confirm the price again."
    if (now if now is not None else time.time()) - int(stamp_s) > TOKEN_TTL_S:
        return "That confirmation expired. Confirm the price again."
    if token in _USED:
        return "That confirmation was already used. Confirm the price again."
    if est["usd"] > float(usd_s) + 1e-6:
        return f"The plan now costs US${est['usd']:.2f}, more than the US${float(usd_s):.2f} you confirmed."
    return None


# ---------------------------------------------------------------- stills and graph


def chain_stills(state: dict, count: int) -> tuple[str, list[dict]]:
    from xenoform.morph_pass import pick_stills, vibe_for

    if vibe_for(state) == "black":
        # The black chain is curated (rose -> jellyfish -> butterfly -> swallow -> drops), so a
        # story word must not rotate it. Every paid shot then starts from a still Tys has seen.
        return pick_stills({key: state.get(key) for key in ("vibe", "palette", "preset")}, count)
    return pick_stills(state, count)


def build_graph(shots: list[dict], stills: list[dict], *, prompt: str, seed: int, model: str = "fast",
                resolution: str = RESOLUTION) -> dict:
    """One prompt: a LoadImage per still, one partner node and one SaveVideo per shot."""
    graph: dict[str, Any] = {}
    for j, still in enumerate(stills[: len(shots) + 1]):
        graph[str(10 + j)] = {"class_type": "LoadImage", "inputs": {"image": Path(still["path"]).name},
                              "_meta": {"title": f"Still {j}: {still.get('noun', '')}"}}
    for i, shot in enumerate(shots):
        graph[str(100 + i)] = {
            "class_type": PARTNER_NODE,
            "inputs": {
                "image": [str(10 + i), 0],
                "last_frame": [str(11 + i), 0],
                "model": MODELS[model],
                "model.duration": str(int(shot["render_s"])),
                "model.resolution": resolution,
                "model.fps": str(FPS),
                "model.generate_audio": False,
                "prompt": prompt,
                "seed": int(seed) + i,
            },
            "_meta": {"title": f"PAID LTX-2.5 shot {i + 1}"},
        }
        graph[str(200 + i)] = {"class_type": "SaveVideo", "inputs": {
            "video": [str(100 + i), 0], "filename_prefix": f"xenoform/cloud/shot{i:02d}",
            "format": "auto", "format.codec": "auto"}}
    return graph


def _check_value(label: str, spec, value, errors: list[str]) -> None:
    kind, opts = spec[0], (spec[1] if len(spec) > 1 else {}) or {}
    if isinstance(kind, list):
        kind, opts = "COMBO", {"options": kind}
    if kind == "COMBO":
        options = [str(o) for o in opts.get("options", [])]
        if options and str(value) not in options:
            errors.append(f"{label}: {value!r} not in {options}")
    elif kind == "INT" and (not isinstance(value, int) or not (opts.get("min", value) <= value <= opts.get("max", value))):
        errors.append(f"{label}: bad INT {value!r}")
    elif kind == "BOOLEAN" and not isinstance(value, bool):
        errors.append(f"{label}: expected BOOLEAN")
    elif kind == "STRING" and not isinstance(value, str):
        errors.append(f"{label}: expected STRING")


def validate_partner(graph: dict, node_info: dict) -> list[str]:
    """The partner nodes against the installed schema (required inputs, combos, the dynamic model combo)."""
    errors: list[str] = []
    req = node_info["input"]["required"]
    for nid, node in graph.items():
        if node["class_type"] != PARTNER_NODE:
            continue
        inputs = node["inputs"]
        for name, spec in req.items():
            if name not in inputs:
                errors.append(f"node {nid}: missing {name}")
            elif spec[0] == "COMFY_DYNAMICCOMBO_V3":
                options = {o["key"]: o for o in spec[1]["options"]}
                if inputs[name] not in options:
                    errors.append(f"node {nid}: model {inputs[name]!r} not offered")
                    continue
                for sub, subspec in options[inputs[name]]["inputs"].get("required", {}).items():
                    key = f"{name}.{sub}"
                    if key not in inputs:
                        errors.append(f"node {nid}: missing {key}")
                    else:
                        _check_value(f"node {nid} {key}", subspec, inputs[key], errors)
            elif not (isinstance(inputs[name], list) and len(inputs[name]) == 2):
                _check_value(f"node {nid} {name}", spec, inputs[name], errors)
    return errors


# ---------------------------------------------------------------- media helpers


def _ffmpeg() -> str:
    try:
        from xenoform.video import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _read_frames(path: Path, w: int, h: int) -> np.ndarray:
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}:flags=lanczos",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def _fit(frames: np.ndarray, count: int) -> np.ndarray:
    if len(frames) == 0:
        raise RuntimeError("A shot came back with no frames.")
    return frames[np.round(np.linspace(0, len(frames) - 1, count)).astype(int)]


def _font() -> str | None:
    for cand in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(cand).is_file():
            return cand
    return None


def _drawtext_font(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:")


def audio_envelope(audio_path: Path, start: float, duration: float, columns: int) -> np.ndarray:
    """RMS per column across ``[start, start+duration]``, normalised to 0..1."""
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(audio_path),
                          "-ac", "1", "-ar", "8000", "-f", "f32le", "-"], check=True, capture_output=True).stdout
    pcm = np.frombuffer(raw, np.float32)
    if pcm.size == 0:
        return np.zeros(columns, np.float32)
    edges = np.linspace(0, pcm.size, columns + 1).astype(int)
    rms = np.array([math.sqrt(float(np.mean(pcm[a:b] ** 2))) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])], np.float32)
    peak = float(np.percentile(rms, 98)) or 1.0
    return np.clip(rms / peak, 0.0, 1.0)


class BeatOverlay:
    """Waveform strip, beat ticks, and morph-handoff markers burnt into the bottom of each frame."""

    TEAL = np.array([90, 225, 215], np.float32)
    DIM = np.array([85, 80, 110], np.float32)
    VIOLET = np.array([190, 110, 255], np.float32)

    def __init__(self, w: int, h: int, duration: float, envelope: np.ndarray, beats: list, handoffs: list):
        self.w, self.h, self.duration = w, h, max(duration, 1e-3)
        self.band = max(24, int(h * 0.13))
        self.top = h - self.band
        self.beats = [float(b) for b in beats if 0 <= float(b) <= duration]
        self.handoffs = [float(t) for t in handoffs if 0 < float(t) < duration]
        env = np.interp(np.linspace(0, len(envelope) - 1, w), np.arange(len(envelope)), envelope) if len(envelope) else np.zeros(w)
        mid = self.band // 2
        heights = np.maximum(1, (env * (self.band * 0.42)).astype(int))
        ys = np.arange(self.band)[:, None]
        self.mask = (np.abs(ys - mid) <= heights[None, :]).astype(np.float32)  # band x w

    def _x(self, t: float) -> int:
        return int(round(t / self.duration * (self.w - 1)))

    def draw(self, frame: np.ndarray, t: float) -> np.ndarray:
        out = frame.astype(np.float32)
        band = out[self.top:]
        band *= 0.45
        head = self._x(t)
        m = self.mask[:, :, None]
        played = np.zeros((1, self.w, 1), np.float32)
        played[:, : head + 1] = 1.0
        colour = self.TEAL * played + self.DIM * (1.0 - played)
        band[:] = band * (1 - m * 0.85) + colour * m * 0.85
        for b in self.beats:
            x = self._x(b)
            hot = abs(t - b) < 0.07
            band[: max(3, self.band // 6), max(0, x - 1): x + 1] = 255.0 if hot else 170.0
        for hnd in self.handoffs:
            x = self._x(hnd)
            near = abs(t - hnd) < 0.15
            band[:, max(0, x - (2 if near else 1)): x + (2 if near else 1)] = self.VIOLET * (1.25 if near else 1.0)
            if near:
                out[max(0, self.top - 3): self.top, :] = self.VIOLET
        band[:, max(0, head - 1): head + 1] = 255.0
        return np.clip(out, 0, 255).astype(np.uint8)


def stitch(clips: list[Path], shots: list[dict], audio_path: Path, out_path: Path, *, width: int, height: int,
           audio_start: float = 0.0, overlay: dict | None = None, label: str | None = None) -> dict:
    """Each clip retimed to its shot's exact frame count, joined on the grid, song muxed in."""
    total = sum(s["frames"] for s in shots)
    over = None
    if overlay is not None:
        env = audio_envelope(audio_path, audio_start, total / FPS, 512)
        over = BeatOverlay(width, height, total / FPS, env, overlay.get("beats") or [], overlay.get("handoffs") or [])
    vf = []
    font = _font()
    if label and font:
        vf.append(f"drawtext=fontfile='{_drawtext_font(font)}':text='{label}':x=16:y=14:fontsize={max(14, height // 34)}:"
                  "fontcolor=white@0.85:box=1:boxcolor=black@0.45:boxborderw=6")
    tmp = out_path.with_name(out_path.stem + ".stitch.mp4")
    cmd = [_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(FPS),
           "-i", "-", "-ss", f"{audio_start:.3f}", "-i", str(audio_path), "-map", "0:v", "-map", "1:a"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-shortest", "-movflags", "+faststart"]
    if label:
        cmd += ["-metadata", f"comment={label}"]
    cmd.append(str(tmp))
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frame_no = 0
    punch = punch_curve(shots)
    try:
        for clip, shot in zip(clips, shots):
            frames = _read_frames(clip, width, height)
            if len(frames) == 0:
                raise RuntimeError("A shot came back with no frames.")
            for frame in frames[shot_indices(shot, len(frames))]:
                if frame_no < len(punch) and punch[frame_no] > 0.01:
                    frame = apply_punch(frame, float(punch[frame_no]))
                if over is not None:
                    frame = over.draw(frame, frame_no / FPS)
                enc.stdin.write(np.ascontiguousarray(frame).tobytes())
                frame_no += 1
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not write the cloud cut (exit {code}).")
    tmp.replace(out_path)
    return {"frames": frame_no, "seconds": round(frame_no / FPS, 3), "label_burnt": bool(label and font), "overlay": over is not None}


# ---------------------------------------------------------------- engines


def _mock_clips(shots: list[dict], stills: list[dict], work: Path, w: int, h: int) -> list[Path]:
    """Dry run: a cross-fade per shot at its render length. No model, no network."""
    clips = []
    for i, shot in enumerate(shots):
        d = float(shot["render_s"])
        dest = work / f"mock{i:02d}.mp4"
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-loop", "1", "-t", f"{d}", "-i", stills[i]["path"],
                        "-loop", "1", "-t", f"{d}", "-i", stills[i + 1]["path"], "-filter_complex",
                        f"[0:v]scale={w}:{h},setsar=1,fps={FPS}[a];[1:v]scale={w}:{h},setsar=1,fps={FPS}[b];"
                        f"[a][b]xfade=transition=fade:duration={max(0.5, d - 0.4):.2f}:offset=0.2,format=yuv420p",
                        "-t", f"{d}", str(dest)], check=True)
        clips.append(dest)
    return clips


def _client(cfg: dict):
    from xenoform.restyle import _make_client

    return _make_client(cfg)


def _job_result(client, job):
    from comfy_sdk import JobFailed

    for attempt in range(6):
        try:
            return job.result()
        except JobFailed as exc:  # comfy-api-proxy 0.1.6 transient "expired"
            if "expired" not in str(exc) or attempt == 5:
                raise
            time.sleep(0.5 + attempt * 0.5)
            job = client.jobs.get(job.id)


def _local_clips(shots, stills, work: Path, cfg: dict, seed: int, vibe: str, client=None, cancel=None) -> list[Path]:
    """Free: one LTX 0.9.5 A->B morph per shot through the existing morph graph."""
    from xenoform import morph_pass as mp

    client = client or _client(cfg)
    graph = mp._graph_path(work, "ltx095")
    tune = mp.tuned(vibe)
    assets: dict = {}

    def asset(path: str):
        if path not in assets:
            assets[path] = client.assets.from_file(path)
        return assets[path]

    jobs = []
    for i, shot in enumerate(shots):
        wf = client.workflows.from_file(str(graph))
        wf.set_input("6", "image", asset(stills[i]["path"]))
        wf.set_input("7", "image", asset(stills[i + 1]["path"]))
        wf.set_input("3", "text", mp.prompt_for(vibe))
        wf.set_input("4", "text", mp.NEGATIVE)
        wf.set_input("9", "width", mp.WIDTH)
        wf.set_input("9", "height", mp.HEIGHT)
        wf.set_input("9", "length", mp.gen_length(int(round(min(float(shot.get("render_s") or shot["seconds"]), 5.0) * FPS))))
        wf.set_input("11", "steps", int(tune.get("steps", mp.STEPS)))
        if "cfg" in tune:
            wf.set_input("14", "cfg", float(tune["cfg"]))
        wf.set_input("13", "noise_seed", int(seed) + i)
        wf.set_input("18", "fps", float(FPS))
        mp.stop_queued(jobs, cancel)
        jobs.append(client.submit(wf))
    clips = []
    for i, job in enumerate(jobs):
        mp.wait_or_cancel(job, jobs, cancel)
        result = _job_result(client, job)
        outs = list(result.get_outputs("19")) or list(result.outputs)
        dest = work / f"local{i:02d}.mp4"
        next((o for o in outs if getattr(o, "type", None) == "video"), outs[0]).to_file(str(dest))
        clips.append(dest)
    return clips


def _cloud_clips(graph: dict, shots, stills, work: Path, cfg: dict, key: str, client=None) -> list[Path]:
    """PAID. Only reached through ``run_chain`` with every gate open."""
    if os.environ.get("XENO_CLOUD_NEVER"):
        raise CloudRefused("XENO_CLOUD_NEVER is set; paid submits are disabled on this machine.")
    client = client or _client(cfg)
    wf = client.workflows.from_json(json.loads(json.dumps(graph)))
    for j in range(len(shots) + 1):
        wf.set_input(str(10 + j), "image", client.assets.from_file(stills[j]["path"]))
    job = client.submit(wf, api_key=key)
    result = _job_result(client, job)
    clips = []
    for i in range(len(shots)):
        outs = list(result.get_outputs(str(200 + i)))
        if not outs:
            raise RuntimeError(f"Cloud shot {i + 1} came back with no video.")
        dest = work / f"cloud{i:02d}.mp4"
        next((o for o in outs if getattr(o, "type", None) == "video"), outs[0]).to_file(str(dest))
        clips.append(dest)
    return clips


def dry_run_default(cfg: dict | None = None) -> bool:
    flag = os.environ.get("XENO_CLOUD_DRY_RUN", "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    return bool(((cfg or {}).get("comfy") or {}).get("cloud_dry_run", False))


def comfy_url(cfg: dict | None) -> str:
    return str(((cfg or {}).get("comfy") or {}).get("base_url") or "http://127.0.0.1:8188")


def plan_for(duration: float, beats: list, state: dict, cfg: dict | None = None, *, probe: bool = True) -> dict:
    """The whole plan the confirm card shows: shots, stills, cost, gates."""
    shots = shots_for(state, duration, beats)
    vibe, stills = stills_for(state, len(shots) + 1)
    table, info, source = prices(comfy_url(cfg) if probe else None)
    est = estimate(shots, table=table)
    return {"shots": shots, "vibe": vibe, "stills": [s["file"] for s in stills], "estimate": est,
            "price_source": source, "node_installed": info is not None,
            "key_present": bool(os.environ.get(KEY_ENV, "").strip()), "dry_run": dry_run_default(cfg),
            "label": LABEL, "prompt": DEFAULT_PROMPT, "custom_cut": bool(state.get("cut_plan"))}


def paid_env_state() -> str:
    """``on``, ``off`` or empty: what ``XENO_PAID_CLOUD`` forces, if anything."""
    flag = os.environ.get(PAID_ENV, "").strip().lower()
    if flag in _ON:
        return "on"
    if flag in _OFF:
        return "off"
    return ""


def paid_cloud_enabled(cfg: dict | None = None, requested: bool = False) -> bool:
    """True only after an explicit opt-in. Off by default.

    ``XENO_PAID_CLOUD=1`` turns it on, ``XENO_PAID_CLOUD=0`` forces it off. Otherwise
    the desk setting (sent as ``paid_cloud``) or ``comfy.paid_cloud`` in a local
    config decides. Nothing else (Add-ons, a key in the environment) turns it on.
    """
    forced = paid_env_state()
    if forced:
        return forced == "on"
    return bool(requested) or bool(((cfg or {}).get("comfy") or {}).get("paid_cloud", False))


def run_chain(engine: str, directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
              report: Callable[[str, float, str], None], *, client=None, now: float | None = None) -> dict:
    """Render the cloud plan with ``engine`` (local, cloud, mock) and write the stitched, muxed cut."""
    started = time.perf_counter()
    work = Path(work) / "cloud"
    work.mkdir(parents=True, exist_ok=True)
    duration = float(directed.get("duration") or 0.0)
    beats = list(directed.get("beats") or [])
    shots = shots_for(state, duration, beats)
    vibe, stills = stills_for(state, len(shots) + 1)
    seed = int(state.get("seed") or 2727)
    prompt = str(state.get("cloud_prompt") or DEFAULT_PROMPT)
    table, info, source = prices(comfy_url(cfg))
    est = estimate(shots, table=table)
    graph = build_graph(shots, stills, prompt=prompt, seed=seed)
    errors = validate_partner(graph, info) if info else ["LtxApi25ImageToVideo is not installed in this ComfyUI."]
    plan = {"engine": engine, "vibe": vibe, "shots": shots, "stills": [s["file"] for s in stills], "estimate": est,
            "price_source": source, "graph_errors": errors, "prompt": prompt}
    (work / f"plan_{engine}.json").write_text(json.dumps({**plan, "graph": graph}, indent=1), encoding="utf-8")
    if engine == "cloud":
        if not paid_cloud_enabled(cfg, bool(state.get("paid_cloud"))):
            raise CloudRefused(OFF_MESSAGE)
        if est["over_cap"]:
            raise CloudRefused(f"US${est['usd']:.2f} is over the US${est['cap_usd']:.2f} cap for one clip.")
        why = check_token(str(state.get("cloud_confirm") or ""), est, now=now)
        if why:
            raise CloudRefused(why)
        key = os.environ.get(KEY_ENV, "").strip()
        if not key:
            raise CloudRefused(f"No Comfy API key in {KEY_ENV}. Nothing was sent.")
        if errors:
            raise CloudRefused("The LTX-2.5 graph did not validate: " + "; ".join(errors[:3]))
        _USED.add(str(state.get("cloud_confirm")))
        report("cloud", 0.2, f"Cloud quality: {len(shots)} LTX-2.5 shots rendering in parallel · US${est['usd']:.2f}")
        clips = _cloud_clips(graph, shots, stills, work, cfg, key, client=client)
        w, h = 1280, 720
    elif engine == "mock":
        report("cloud", 0.2, f"Dry run: {len(shots)} LTX-2.5 shots planned · US${est['usd']:.2f} not spent")
        clips = _mock_clips(shots, stills, work, 1280, 720)
        w, h = 1280, 720
    elif engine == "local":
        report("restyle", 0.2, f"Free local draft: {len(shots)} LTX 0.9.5 morphs on this GPU")
        clips = _local_clips(shots, stills, work, cfg, seed, vibe, client=client, cancel=state.get("_cancel"))
        w, h = 768, 432
    else:
        raise ValueError(engine)
    marks = [s["start"] for s in shots[1:]]
    overlay = {"beats": beats, "handoffs": marks} if state.get("beat_overlay") else None
    label = LABEL if engine == "cloud" else ("DRY RUN mock of " + LABEL if engine == "mock" else None)
    tmp_out = Path(out_path).with_name(Path(out_path).stem + f".{engine}.mp4")
    made = stitch(clips, shots, Path(audio_path), tmp_out, width=w, height=h, overlay=overlay, label=label)
    shutil.copyfile(tmp_out, out_path)
    info_out = {**plan, "engine": engine, "label": label or "", "render": f"{w}x{h}", "fps": FPS,
                "handoffs_s": [0.0] + marks + [shots[-1]["end"]], "frames": [s["frames"] for s in shots],
                "spent_usd": est["usd"] if engine == "cloud" else 0.0, "file": str(tmp_out), **made,
                "seconds_total": round(time.perf_counter() - started, 2)}
    (work / f"result_{engine}.json").write_text(json.dumps(info_out, indent=1), encoding="utf-8")
    return info_out


def run_cloud_quality(directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
                      report: Callable[[str, float, str], None], *, local_ok: bool = True,
                      cancel: Callable[[], bool] | None = None) -> tuple[dict, str]:
    """Simple mode's Cloud quality: free local draft first (it plays), then the cloud pass.

    Returns ``(info, warning)``. Any cloud failure keeps the local cut and says why.
    """
    info: dict = {}
    warning = ""
    if local_ok:
        try:
            info["local"] = run_chain("local", directed, audio_path, out_path, work, cfg, {**state, "_cancel": cancel}, report)
            report("assemble", 0.7, "Free local draft playing. Cloud quality is rendering on LTX-2.5.")
        except Exception as exc:
            from xenoform.turbo import JobCancelled

            if isinstance(exc, JobCancelled):
                raise
            log.exception("local draft")
            info["local_error"] = str(exc)[:300]
    if cancel and cancel():
        from xenoform.turbo import JobCancelled

        raise JobCancelled("Cancelled before the cloud pass. Nothing was sent.")
    engine = "mock" if dry_run_default(cfg) else "cloud"
    try:
        info["cloud"] = run_chain(engine, directed, audio_path, out_path, work, cfg, state, report)
        if engine == "mock" and "local" in info and Path(info["local"]["file"]).is_file():
            # A dry run never replaces the real local cut with cross-fades; the mock stays beside it.
            shutil.copyfile(info["local"]["file"], out_path)
        report("assemble", 0.95, "Cloud quality cut locked to the beat" if engine == "cloud" else
               "Dry run: cloud plan validated, mock cut stitched beside the local one. Nothing was spent.")
    except Exception as exc:
        from xenoform.errors import plain_error

        log.warning("cloud quality fell back: %s", exc)
        info["cloud_error"] = str(exc)[:300]
        if "local" in info:
            local_file = Path(info["local"]["file"])
            if local_file.is_file():
                shutil.copyfile(local_file, out_path)
        warning = f"Cloud quality did not run, so this is the free local cut. {plain_error(exc)}"
    return info, warning
