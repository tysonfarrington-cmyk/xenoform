"""Simple mode's GPU pass: per-scene stills chained as A->B guided morphs.

Each scene is one LTX 0.9.5 morph from still i to still i+1 through
``workflows/xenoform_morph.json`` (two LTXVAddGuide endpoints, 512x288),
submitted with comfy-sdk through comfy-api-proxy. Morph i ends on the exact
still morph i+1 starts from, so every handoff is continuous, and every handoff
sits on a scene boundary snapped to the beat grid.

The stills are a curated set per vibe in ``ui_static/objects`` (library
objects regraded per vibe; paper-summer was made once with Z-Image Turbo).
Nothing is generated at run time except the morphs.
"""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import os

import numpy as np

log = logging.getLogger("xenoform.morph_pass")

OBJECTS = Path(__file__).resolve().parent / "ui_static" / "objects"
GRAPH = Path(__file__).resolve().parents[2] / "workflows" / "xenoform_morph.json"
FPS = 24
_size = os.environ.get("XENO_MORPH_SIZE", "512x288").lower().split("x")
WIDTH, HEIGHT = int(_size[0]), int(_size[1])
STEPS = int(os.environ.get("XENO_MORPH_STEPS", "20"))
MIN_LEN, MAX_LEN = 25, 121
OUT_W, OUT_H = max(768, WIDTH), max(432, HEIGHT)  # lanczos upscale for playback; the render is WIDTH x HEIGHT

GRAPH25 = GRAPH.with_name("ltx25_morph_api.json")
# Files the LTX-2.5 morph needs (the official ComfyUI FLF2V template's low-VRAM set,
# from the gated Hugging Face repo Lightricks/LTX-2.5).
LTX25_FILES = (
    ("diffusion_models", "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"),
    ("text_encoders", "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"),
    ("vae", "ltx-2.5-video-vae-bf16.safetensors"),
    ("vae", "ltx-2.5-audio-vae-bf16.safetensors"),
)

VIBE_LOOK = {
    "liquid-gold": "molten gold and liquid mercury, warm amber studio glow, dark umber backdrop",
    "bloom": "iridescent petals and pearly glass, soft magenta rim light, fresh spring-green backdrop",
    "neon-night": "black glass and oil-slick metal, hot magenta glow, deep crimson-black backdrop",
    "ocean": "iridescent shell and chrome, aqua caustic light, deep teal water backdrop",
    "cosmic": "iridescent glass and pearl, cobalt and violet glow, deep indigo backdrop",
    "paper-summer": "folded white paper and glazed porcelain, warm morning sunlight, soft cream backdrop",
}
PALETTE_VIBE = {"gold": "liquid-gold", "violet": "cosmic", "grey-green": "ocean", "bronze": "bloom", "neutral": "paper-summer"}
NEGATIVE = "text, letters, watermark, logo, two objects, cut, flicker, blurry, low quality, cartoon, people, hands"


def manifest() -> dict[str, list[dict]]:
    return json.loads((OBJECTS / "objects.json").read_text(encoding="utf-8"))


def vibe_for(state: dict) -> str:
    vibe = str(state.get("vibe") or "")
    pools = manifest()
    if vibe in pools:
        return vibe
    if str(state.get("preset") or "") == "liquid-metal":
        return "liquid-gold"
    return PALETTE_VIBE.get(str(state.get("palette") or ""), "liquid-gold")


def _story_words(state: dict) -> list[str]:
    bits = [str(state.get("brief") or ""), str(state.get("story") or "")]
    for scene in state.get("scenes") or []:
        bits += [str(scene.get(key) or "") for key in ("form", "action", "guide", "text")]
    for custom in state.get("customs") or []:
        bits.append(str(custom.get("noun") or custom.get("name") or ""))
    return re.findall(r"[a-z]+", " ".join(bits).lower().replace("_", " ").replace("-", " "))


AUTOTUNE = Path(__file__).resolve().parents[2] / "configs" / "autotune.json"


def autotune() -> dict:
    """Reviewed output of scripts/autotune (per-vibe settings and a bad-pair list), if installed."""
    path = Path(os.environ.get("XENO_AUTOTUNE", str(AUTOTUNE)))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tuned(vibe: str) -> dict:
    """Per-vibe morph settings from autotune; an explicit XENO_MORPH_STEPS still wins for steps."""
    got = dict((autotune().get("vibes") or {}).get(vibe) or {})
    if "XENO_MORPH_STEPS" in os.environ:
        got.pop("steps", None)
    return got


def _drop_bad_pairs(pool: list[dict], bad: set) -> list[dict]:
    """Reorder so no adjacent pair is on the autotune blocklist, when a reorder can do it."""
    if not bad:
        return pool
    out, rest = [pool[0]], list(pool[1:])
    while rest:
        nxt = next((o for o in rest if (out[-1]["file"], o["file"]) not in bad), rest[0])
        rest.remove(nxt)
        out.append(nxt)
    return out


def pick_stills(state: dict, count: int) -> tuple[str, list[dict]]:
    """``count`` stills for the vibe. A story noun that names a pool object leads."""
    vibe = vibe_for(state)
    pool = list(manifest()[vibe])
    words = set(_story_words(state))
    lead = next((i for i, item in enumerate(pool) if set(item["noun"].split()) & words), None)
    if lead:
        pool = pool[lead:] + pool[:lead]
    pool = _drop_bad_pairs(pool, {tuple(p) for p in autotune().get("bad_pairs") or []})
    # Twelve objects a vibe: a 20 s clip (up to 11 handoffs) never repeats one. Longer
    # songs cycle forward, so a repeat is always a new pairing, never a ping-pong back.
    picked = [pool[i % len(pool)] for i in range(count)]
    return vibe, [{**item, "path": str(OBJECTS / item["file"])} for item in picked]


def handoffs(scenes: list[dict], beats: list, duration: float) -> list[float]:
    """Scene boundaries, each snapped to the nearest beat within 0.25s."""
    grid = [float(b) for b in beats or []]
    bounds = [0.0]
    for scene in scenes[:-1]:
        t = float(scene.get("end") or 0.0)
        if grid:
            near = min(grid, key=lambda b: abs(b - t))
            if abs(near - t) <= 0.25:
                t = near
        if t - bounds[-1] >= 0.5:
            bounds.append(t)
    end = float(scenes[-1].get("end") or duration) if scenes else duration
    bounds.append(max(end, bounds[-1] + 0.5))
    return bounds


def gen_length(frames: int) -> int:
    n = 8 * math.ceil(max(frames - 1, 0) / 8) + 1
    return int(min(MAX_LEN, max(MIN_LEN, n)))


def prompt_for(vibe: str, engine: str = "ltx095") -> str:
    """One prompt per vibe, not per pair: the two guide stills carry the objects.

    The text encoder runs on the CPU (it is what pushed the card past 11.5 GB),
    so the prompt must stay identical across a run's morphs for ComfyUI to
    encode it once and reuse it for every morph.
    """
    look = VIBE_LOOK.get(vibe, VIBE_LOOK["liquid-gold"])
    lead = "Use the provided start image as the first frame and the provided end image as the final frame anchor. " if engine == "ltx25" else ""
    return lead + (
        "One single sculptural object slowly melts and flows into another, one continuous liquid "
        f"transformation, the object stays centred, gentle slow camera drift, {look}, "
        "macro product photography, crisp, clean, high detail"
    )


def ltx25_present(root: Path | None = None) -> bool:
    if root is None:
        try:
            from xenoform.models_setup import models_dir

            root = Path(models_dir() or "")
        except Exception:
            return False
    return all((Path(root) / folder / name).is_file() for folder, name in LTX25_FILES)


def pick_engine() -> str:
    """``ltx25`` when its four files are on disk (or ``XENO_MORPH_ENGINE`` asks), else ``ltx095``."""
    forced = os.environ.get("XENO_MORPH_ENGINE", "").strip().lower()
    if forced in ("ltx25", "ltx095"):
        return forced
    return "ltx25" if ltx25_present() and GRAPH25.exists() else "ltx095"


def _graph_path(work: Path, engine: str = "ltx095") -> Path:
    if engine == "ltx25":
        return GRAPH25
    if GRAPH.exists():
        return GRAPH
    from xenoform.morph.workflow import graph

    dest = work / "xenoform_morph.json"
    dest.write_text(json.dumps(graph(), indent=1), encoding="utf-8")
    return dest


def _ffmpeg() -> str:
    try:
        from xenoform.video import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _read_frames(path: Path, w: int, h: int) -> np.ndarray:
    raw = subprocess.run(
        [_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True,
        capture_output=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8)
    return frames.reshape(-1, h, w, 3)


def _fit(frames: np.ndarray, count: int) -> np.ndarray:
    """Exactly ``count`` frames, first and last kept, so handoffs stay on the grid."""
    if len(frames) == 0:
        raise RuntimeError("A morph came back with no frames.")
    pick = np.round(np.linspace(0, len(frames) - 1, count)).astype(int)
    return frames[pick]


def _result(client, job, index: int, failed):
    """``job.result()``, riding out the proxy's transient "expired".

    comfy-api-proxy 0.1.6 reports a job that is between ComfyUI's queue and its
    history as ``expired`` (a terminal state), then ``succeeded`` a moment later.
    Seen once in seven morphs on the 3080 Ti; re-reading the job recovers it.
    """
    for attempt in range(6):
        try:
            return job.result()
        except failed as exc:
            if "expired" not in str(exc) or attempt == 5:
                raise RuntimeError(f"Comfy job failed for morph {index + 1}: {exc}") from exc
            log.info("morph %d read as expired; re-reading job %s", index + 1, job.id)
            time.sleep(0.5 + attempt * 0.5)
            job = client.jobs.get(job.id)


def run_morph_pass(
    directed: dict,
    scenes: list[dict],
    audio_path: Path,
    out_path: Path,
    work: Path,
    cfg: dict,
    state: dict,
    report: Callable[[str, float, str], None],
) -> dict[str, Any]:
    """LTX-2.5 when it is installed, LTX 0.9.5 otherwise, and 0.9.5 again if 2.5 fails."""
    engine = pick_engine()
    if engine == "ltx25":
        try:
            return _render(directed, scenes, audio_path, out_path, work, cfg, state, report, "ltx25")
        except Exception as exc:
            from xenoform.turbo import JobCancelled

            if isinstance(exc, JobCancelled):
                raise
            log.exception("LTX-2.5 morph pass failed; falling back to LTX 0.9.5")
            report("restyle", 0.1, "LTX-2.5 did not run here. Falling back to LTX 0.9.5 morphs.")
            info = _render(directed, scenes, audio_path, out_path, work, cfg, state, report, "ltx095")
            info["fallback_from"] = f"ltx25: {exc}"[:300]
            return info
    return _render(directed, scenes, audio_path, out_path, work, cfg, state, report, engine)


def _render(
    directed: dict,
    scenes: list[dict],
    audio_path: Path,
    out_path: Path,
    work: Path,
    cfg: dict,
    state: dict,
    report: Callable[[str, float, str], None],
    engine: str = "ltx095",
) -> dict[str, Any]:
    from xenoform.restyle import _make_client

    started = time.perf_counter()
    work = Path(work) / "morphs"
    work.mkdir(parents=True, exist_ok=True)
    duration = float(directed.get("duration") or (scenes[-1].get("end") if scenes else 0) or 0)
    bounds = handoffs(scenes, list(directed.get("beats") or []), duration)
    shots = len(bounds) - 1
    vibe, stills = pick_stills(state, shots + 1)
    marks = [int(round(t * FPS)) for t in bounds]
    counts = [max(2, marks[i + 1] - marks[i]) for i in range(shots)]
    seed = int(state.get("seed") or 2727)

    client = _make_client(cfg)
    graph = _graph_path(work, engine)
    tune = tuned(vibe) if engine != "ltx25" else {}
    assets: dict[str, Any] = {}

    def asset(path: str):
        if path not in assets:
            assets[path] = client.assets.from_file(path)
        return assets[path]

    jobs = []
    for i in range(shots):
        a, b = stills[i], stills[i + 1]
        wf = client.workflows.from_file(str(graph))
        wf.set_input("6", "image", asset(a["path"]))
        wf.set_input("7", "image", asset(b["path"]))
        wf.set_input("3", "text", prompt_for(vibe, engine))
        wf.set_input("4", "text", NEGATIVE)
        wf.set_input("9", "width", WIDTH)
        wf.set_input("9", "height", HEIGHT)
        wf.set_input("9", "length", gen_length(counts[i]))
        if engine == "ltx25":
            # Distilled: the fixed 8-sigma schedule in the graph, CFG 1; audio latent sized to match.
            wf.set_input("25", "frames_number", gen_length(counts[i]))
        else:
            wf.set_input("11", "steps", int(tune.get("steps", STEPS)))
            if "cfg" in tune:
                wf.set_input("14", "cfg", float(tune["cfg"]))
            if "img_compression" in tune:
                wf.set_input("8", "img_compression", int(tune["img_compression"]))
                wf.set_input("21", "img_compression", int(tune["img_compression"]))
            if "guide_end_strength" in tune:
                wf.set_input("22", "strength", float(tune["guide_end_strength"]))
        wf.set_input("13", "noise_seed", seed + i)
        wf.set_input("18", "fps", float(FPS))
        jobs.append(client.submit(wf))
        log.info("morph %d/%d %s -> %s submitted as %s", i + 1, shots, a["noun"], b["noun"], jobs[-1].id)
    submitted = time.perf_counter() - started
    report("restyle", 0.12, f"{shots} morphs queued on the GPU · {vibe}")

    from comfy_sdk import JobFailed

    clips = []
    timings = []
    for i, job in enumerate(jobs):
        result = _result(client, job, i, JobFailed)
        outputs = list(result.get_outputs("19")) or list(result.outputs)
        if not outputs:
            raise RuntimeError(f"Morph {i + 1} finished with no video.")
        chosen = next((o for o in outputs if getattr(o, "type", None) == "video"), outputs[0])
        dest = work / f"m{i:02d}.mp4"
        chosen.to_file(str(dest))
        clips.append(dest)
        timings.append(round(time.perf_counter() - started, 2))
        report(
            "restyle",
            0.12 + 0.8 * (i + 1) / shots,
            f"Morph {i + 1} of {shots} · {stills[i]['noun']} into {stills[i + 1]['noun']}",
        )

    report("assemble", 0.6, "Locking the morphs to the beat")
    gpu_path = Path(out_path).with_name(Path(out_path).stem + "-gpu.mp4")
    enc = subprocess.Popen(
        [
            _ffmpeg(), "-v", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-",
            "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
            str(gpu_path),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        for clip, count in zip(clips, counts):
            enc.stdin.write(_fit(_read_frames(clip, OUT_W, OUT_H), count).tobytes())
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not write the morph cut (exit {code}).")
    try:
        from xenoform.video import overlay_text

        overlay_text(gpu_path, directed.get("text_cards") or [])
    except Exception:
        log.exception("text cards on the morph cut")
    gpu_path.replace(out_path)
    info = {
        "engine": ("ltx-2.5 22B distilled int8" if engine == "ltx25" else "ltx-095") + " A->B morph chain (comfy-sdk -> comfy-api-proxy)",
        "workflow": str(graph),
        "vibe": vibe,
        "render": f"{WIDTH}x{HEIGHT}",
        "output": f"{OUT_W}x{OUT_H}",
        "steps": 8 if engine == "ltx25" else int(tune.get("steps", STEPS)),
        "autotune": tune or None,
        "fps": FPS,
        "handoffs_s": [round(t, 3) for t in bounds],
        "frames": counts,
        "stills": [s["file"] for s in stills],
        "submitted_s": round(submitted, 2),
        "done_s": timings,
        "seconds": round(time.perf_counter() - started, 2),
    }
    (work / "morph_pass.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info
