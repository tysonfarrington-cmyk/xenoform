"""Turbo: an animatic in seconds, then a small LTX pass on the same seed.

The animatic never calls a video model. One keyframe per scene (4 steps at
384Ã—216) sits on the beat grid. Hard cuts join the shots. A signature scene
crossfades, with a zoom regather, and a beat flash rides the picture. Dry run
stops there. Live mode then replaces it with a chain of A->B guided morphs
between per-vibe stills (LTX 0.9.5 at 512x288, see ``morph_pass``), one per
scene with handoffs on the beat, and never loads Wan or LTX-2.3.

Cache keys are the scene card hash, the seed, the model, and the resolution.
Analysis is cached per track. Unchanged keyframes are reused, so a second pass
only repaints the card that changed. Retimes stay in seconds.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import logging
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT, apply_tier, resolve_tier
from xenoform.notes import DEFAULT_SEED, segment_key
from xenoform.render_cpu import form_from_frame, render_frame
from xenoform.video import overlay_text, write_mp4

ANIMATIC_W = 384
ANIMATIC_H = 216
VIDEO_W = 384
VIDEO_H = 224

import contextvars as _contextvars

# The animatic follows the cut's aspect: a portrait sketch for 9:16, square for 1:1.
_SIZE = _contextvars.ContextVar("xeno_animatic_size", default=(ANIMATIC_W, ANIMATIC_H))


def animatic_size(state: dict | None = None) -> tuple[int, int]:
    if not state or state.get("live"):
        return ANIMATIC_W, ANIMATIC_H  # live keyframes guide the 384x224 video model; keep them landscape
    aspect = str(state.get("aspect") or "")
    return {"9:16": (ANIMATIC_H, ANIMATIC_W), "1:1": (288, 288)}.get(aspect, (ANIMATIC_W, ANIMATIC_H))


def _aw() -> int:
    return _SIZE.get()[0]


def _ah() -> int:
    return _SIZE.get()[1]
KEY_STEPS = 4
VIDEO_STEPS = 4
log = logging.getLogger("xenoform.turbo")
FPS = 12
TURBO_MODEL = "ltx-095"
ANIMATIC_MODEL = "animatic"

# Estimates for a ~12s track on a 12 GB GPU. The animatic number is a CPU budget
# the desk can beat; tests print the measured time.
_ETA = {
    "live": {
        "label": "Live",
        "short": "now",
        "first_s": 0,
        "again_s": 0,
        "line": (
            "The picture is in the browser, on this GPU, with no install. "
            "It follows the beats, the register, and the scene cards, and a slider lands on the next frame. "
            "Record writes an mp4 with no model. That file can guide Turbo, Draft, and Final."
        ),
    },
    "turbo": {
        "label": "Turbo",
        "short": "~1 min",
        "first_s": 60,
        "again_s": 10,
        "animatic_s": 5,
        "line": (
            "Animatic in about 5 seconds: one 384px keyframe a scene, on the beat. "
            "For a 12-20 s song on a 12 GB RTX 3080 Ti the GPU morph pass takes about 1 minute on a first run "
            "with the GPU idle, about 2 minutes if ComfyUI just had another model loaded, and 45-65 s warm; "
            "the desk counts down from the real morph pace. "
            "A scene you change re-renders in seconds. A 4 second proof plays before the full animatic. "
            "Turbo never loads LTX-2.3. "
            "Seed 2727 and the retime in seconds carry to Final."
        ),
    },
    "draft": {
        "label": "Draft",
        "short": "~4 min",
        "first_s": 240,
        "again_s": 50,
        "line": "512Ã—288, 12 steps, or 704Ã—384 on a 12 GB card when an fp8 LTX-2.3 file is present, about 210 seconds a shot. LTX-2.3 is the core action model. LTX 0.9.5 covers morphs and Turbo. About 4 minutes the first time on LTX 0.9.5.",
    },
    "final": {
        "label": "Final",
        "short": "~10 min",
        "first_s": 600,
        "again_s": 160,
        "line": "640Ã—360 at 24 fps, or 768Ã—432 on 24 GB with LTX-2.3 as the core model. LTX 0.9.5 covers morphs. Same seed, same guides, same retime in seconds.",
    },
}

_TINT = {
    "violet": np.array([0.78, 0.62, 1.06], dtype=np.float32),
    "grey-green": np.array([0.72, 0.92, 0.78], dtype=np.float32),
    "gold": np.array([1.08, 0.90, 0.55], dtype=np.float32),
    "bronze": np.array([1.05, 0.72, 0.48], dtype=np.float32),
    "neutral": np.array([1.0, 1.0, 1.0], dtype=np.float32),
}


class JobCancelled(RuntimeError):
    """The desk replaced this cut because a card changed."""


def eta_table() -> dict[str, dict[str, Any]]:
    """ETA copy for the quality switch. Video times are 12 GB estimates."""
    return {key: dict(value) for key, value in _ETA.items()}


def guard_checkpoint(name: str | None) -> str:
    """Turbo stays on LTX 0.9.5. LTX-2.3 is the Draft and Final default on a 24 GB desk."""
    text = str(name or "")
    lowered = text.lower()
    if (not text) or ("2.3" in lowered) or ("22b" in lowered) or ("wan" in lowered):
        return FAST_CHECKPOINT
    if text == LARGE_CHECKPOINT:
        return FAST_CHECKPOINT
    return text


def batch_by_checkpoint(rows: list[dict]) -> list[dict]:
    """One model stays loaded. Rows are already guarded onto a single checkpoint."""
    batches: list[dict] = []
    for row in rows:
        name = guard_checkpoint(row.get("checkpoint"))
        if not batches or batches[-1]["checkpoint"] != name:
            batches.append({"checkpoint": name, "segments": []})
        batches[-1]["segments"].append(row.get("id"))
    return batches


def cache_root(work: Path) -> Path:
    """Share the cache across job folders so the next generate hits it."""
    work = Path(work)
    if work.parent.name == "jobs":
        root = work.parent / "cache"
    else:
        root = work / "cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _stop(cancel: Callable[[], bool] | None) -> None:
    if cancel and cancel():
        raise JobCancelled("Cancelled. The card changed.")


def _track_key(path: Path, fps: int) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime_ns)}|{int(fps)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _frame_at(features: dict, t: float) -> dict:
    frames = features.get("frames") or []
    if not frames:
        raise RuntimeError("The track has no frames to paint.")
    fps = float(features.get("fps") or FPS) or FPS
    index = int(round(float(t) * fps))
    index = max(0, min(index, len(frames) - 1))
    return frames[index]


def _lock_time(scene: dict, beats: list) -> float:
    """The keyframe sits on a beat inside the scene, or on the retime anchor."""
    start = float(scene.get("start") or 0.0)
    end = float(scene.get("end") or start)
    anchors = (scene.get("retime") or {}).get("anchors_s") or []
    if len(anchors) >= 2:
        try:
            src = float(anchors[1][0])
        except (TypeError, ValueError, IndexError):
            src = start
        if start <= src <= end:
            return src
    inside = [float(beat) for beat in beats if start <= float(beat) < end]
    if inside:
        return inside[len(inside) // 2]
    return (start + end) / 2.0


def _cut_time(scene: dict, beats: list, fps: float) -> tuple[float, float]:
    """Beat-lock a signature blend. Every other join is a hard cut."""
    start = float(scene.get("start") or 0.0)
    end = float(scene.get("end") or start)
    if not scene.get("signature"):
        return end, 0.0
    fade = min(8.0 / fps, max(1.0 / fps, (end - start) * 0.45))
    cut = end
    anchors = (scene.get("retime") or {}).get("anchors_s") or []
    if len(anchors) >= 2:
        try:
            dst = float(anchors[1][1])
        except (TypeError, ValueError, IndexError):
            dst = end
        if start < dst <= end:
            cut = dst
    else:
        inside = [float(beat) for beat in beats if start < float(beat) <= end]
        if inside:
            cut = inside[-1]
    cut = min(end, max(start + fade, cut))
    return cut, fade


def _zoom(frame: np.ndarray, amount: float) -> np.ndarray:
    """Zoom from the center through a dissolve so the blend does not ghost."""
    if amount <= 0.02:
        return frame
    height, width = frame.shape[:2]
    crop = int(round(amount * 0.08 * min(height, width)))
    if crop < 1 or crop * 2 >= height or crop * 2 >= width:
        return frame
    cut = frame[crop : height - crop, crop : width - crop]
    ys = np.linspace(0, cut.shape[0] - 1, height).astype(np.int32)
    xs = np.linspace(0, cut.shape[1] - 1, width).astype(np.int32)
    return cut[ys][:, xs]


def _tint(frame: np.ndarray, palette: str) -> np.ndarray:
    if palette in ("", "neutral"):
        return frame
    tint = _TINT.get(palette)
    if tint is None:
        return frame
    return np.clip(frame.astype(np.float32) * tint, 0, 255).astype(np.uint8)


def _keyframe_path(cache: Path, key: str) -> Path:
    safe = key.replace(":", "_").replace("/", "_")
    return cache / "keyframes" / f"{safe}.npy"


def _paint(features: dict, scene: dict, seed: int, palette: str) -> np.ndarray:
    from xenoform.seeded import unit

    beats = features.get("beats") or []
    fps = float(features.get("fps") or FPS) or FPS
    locked = _lock_time(scene, beats)
    frame_index = int(round(locked * fps))
    phase = unit(int(seed), frame_index, salt=7) / fps
    sample = _frame_at(features, locked + phase)
    form = form_from_frame(sample)
    rgb, _depth, _mask = render_frame(form, _aw(), _ah(), max_steps=KEY_STEPS)
    return _tint(rgb, palette)


def _load_keyframe(path: Path) -> np.ndarray | None:
    if not path.exists():
        return None
    try:
        frame = np.load(path)
    except Exception:
        return None
    if getattr(frame, "shape", None) != (_ah(), _aw(), 3) or frame.dtype != np.uint8:
        return None
    return frame


def keyframe_key(scene: dict, seed: int, palette: str) -> str:
    return segment_key(scene, seed, ANIMATIC_MODEL, f"{_aw()}x{_ah()}") + ":" + str(palette or "neutral")


def plan_segments(scenes: list[dict], seed: int) -> list[dict]:
    """The video pass these keyframes would become. Same seed, guides, and retimes."""
    from xenoform.continuity import render_guide

    rows = []
    base = int(seed)
    for scene in scenes:
        index = int(scene.get("index") or 0)
        anchors = (scene.get("retime") or {}).get("anchors_s") or []
        rows.append(
            {
                "id": f"s{index}",
                "index": index,
                "seed": base,
                "noise_seed": base + index * 997,
                "model": TURBO_MODEL,
                "checkpoint": guard_checkpoint(FAST_CHECKPOINT),
                "resolution": f"{VIDEO_W}x{VIDEO_H}",
                "animatic_resolution": f"{_aw()}x{_ah()}",
                "steps": VIDEO_STEPS,
                "guide": render_guide(scene) or scene.get("guide") or "",
                "guide_strengths": scene.get("guide_strengths"),
                "anchors_s": anchors,
                "key": segment_key(scene, base, TURBO_MODEL, f"{VIDEO_W}x{VIDEO_H}"),
            }
        )
    return rows


def _compose(
    scenes: list[dict],
    keyframes: list[np.ndarray],
    features: dict,
    upto: int,
    fps: float,
    flash: float,
) -> list[np.ndarray]:
    end = float(scenes[upto]["end"])
    start = float(scenes[0]["start"])
    count = max(1, int(round((end - start) * fps)))
    times = start + (np.arange(count, dtype=np.float64) / fps)
    beats = np.asarray([float(beat) for beat in (features.get("beats") or [])], dtype=np.float64)
    if beats.size:
        window = 1.0 / fps
        dist = np.abs(times[:, None] - beats[None, :]).min(axis=1)
        pulse = np.clip(1.0 - dist / window, 0.0, 1.0)
    else:
        pulse = np.zeros(count, dtype=np.float64)
    cuts = [_cut_time(scene, features.get("beats") or [], fps) for scene in scenes]
    frames: list[np.ndarray] = []
    last = min(upto, len(scenes) - 1)
    for index, t in enumerate(times):
        chosen = last
        for scene_index, scene in enumerate(scenes[: last + 1]):
            if float(scene["start"]) <= t < float(scene["end"]) or scene_index == last:
                chosen = scene_index
                if float(scene["start"]) <= t < float(scene["end"]):
                    break
        blend = 0.0
        if chosen < last:
            cut, fade = cuts[chosen]
            if fade > 0:
                begin = cut - fade
                if t > begin:
                    blend = float(np.clip((t - begin) / max(fade, 1e-3), 0.0, 1.0))
        base = keyframes[chosen]
        if blend > 0.0 and chosen + 1 < len(keyframes):
            other = keyframes[chosen + 1]
            mixed = base.astype(np.float32) * (1.0 - blend) + other.astype(np.float32) * blend
            frame = _zoom(np.clip(mixed + 0.5, 0, 255).astype(np.uint8), blend)
        else:
            frame = base
        if flash > 0.0 and pulse[index] > 0.2:
            gain = 1.0 + flash * float(pulse[index])
            frame = np.clip(frame.astype(np.float32) * gain, 0, 255).astype(np.uint8)
        frames.append(frame)
    return frames


def publish_file(tmp: Path, dest: Path, *, tries: int = 8, pause: float = 0.25) -> None:
    """Move ``tmp`` over ``dest`` even while the desk is streaming ``dest`` to a browser.

    On Windows a file that is open for reading cannot be renamed over, so the swap is retried for a
    couple of seconds and then falls back to copying the bytes into place (a write handle is allowed)."""
    tmp, dest = Path(tmp), Path(dest)
    for attempt in range(tries):
        try:
            tmp.replace(dest)
            return
        except PermissionError:
            if attempt == tries - 1:
                break
            time.sleep(pause)
    shutil.copyfile(tmp, dest)
    try:
        tmp.unlink()
    except OSError:
        pass


def _publish(frames: list[np.ndarray], dest: Path, fps: float, audio: Path | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".part.mp4")
    write_mp4(tmp, frames, fps, audio_path=audio, crf=23)
    publish_file(tmp, dest)


def _gather_keyframes(
    features: dict,
    scenes: list[dict],
    cache: Path,
    *,
    seed: int,
    palette: str,
    cancel: Callable[[], bool] | None = None,
) -> tuple[list[np.ndarray], int, int, float, list[dict]]:
    """Paint from the scene cards as given. Callers that clip a proof copy those cards first."""
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "keyframes").mkdir(parents=True, exist_ok=True)
    keyframes: list[np.ndarray] = []
    hits = 0
    misses = 0
    paint_s = 0.0
    segments = plan_segments(scenes, seed)
    for index, scene in enumerate(scenes):
        _stop(cancel)
        path = _keyframe_path(cache, keyframe_key(scene, seed, palette))
        cached = _load_keyframe(path)
        if cached is None:
            started = time.perf_counter()
            cached = _paint(features, scene, seed, palette)
            paint_s += time.perf_counter() - started
            np.save(path, cached)
            misses += 1
            segments[index]["keyframe_cached"] = False
        else:
            hits += 1
            segments[index]["keyframe_cached"] = True
        keyframes.append(cached)
    return keyframes, hits, misses, paint_s, segments


def render_animatic(
    features: dict,
    scenes: list[dict],
    audio_path: Path | None,
    dest: Path,
    cache: Path,
    *,
    seed: int = DEFAULT_SEED,
    palette: str = "neutral",
    flash: float = 0.18,
    on_scene: Callable[[int, int], None] | None = None,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Paint keyframes, hard-cut them on the bar, and mux the track."""
    if not scenes:
        raise RuntimeError("Turbo needs at least one scene.")
    fps = float(FPS)
    keyframes, hits, misses, paint_s, segments = _gather_keyframes(
        features, scenes, cache, seed=seed, palette=palette, cancel=cancel
    )
    for index in range(len(scenes)):
        _stop(cancel)
        frames = _compose(scenes, keyframes[: index + 1], features, index, fps, flash)
        _publish(frames, dest, fps, audio_path)
        if on_scene:
            on_scene(index, len(scenes))
    return {
        "hits": hits,
        "misses": misses,
        "paint_s": round(paint_s, 3),
        "segments": segments,
        "fps": fps,
        "width": _aw(),
        "height": _ah(),
        "steps": KEY_STEPS,
        "batches": batch_by_checkpoint(segments),
    }


def _scenes_for(directed: dict, state: dict) -> list[dict]:
    scenes = [dict(scene) for scene in (state.get("scenes") or []) if scene.get("end") is not None]
    if scenes:
        return scenes
    built = []
    for index, section in enumerate(directed.get("sections") or []):
        built.append(
            {
                "index": index,
                "start": float(section["start"]),
                "end": float(section["end"]),
                "form": section.get("label") or "sphere",
                "action": section.get("label") or "hold",
                "shot": "wide",
                "move": "hold",
                "edit": "ribbon",
                "mood": "void",
                "guide": "",
            }
        )
    return built


def _analyze(audio: Path, cfg: dict, dest: Path, cache: Path) -> tuple[dict, bool]:
    from xenoform.analyze import read_features, write_features
    from xenoform.pipeline import analyze_file

    key = _track_key(audio, int(round(float(cfg["fps"]))))
    cached = cache / "analysis" / f"{key}.json"
    if cached.exists():
        features = read_features(cached)
        write_features(dest, features)
        return features, True
    features = analyze_file(audio, cfg, dest)
    cached.parent.mkdir(parents=True, exist_ok=True)
    write_features(cached, features)
    return features, False


def keyframe_backend() -> str:
    """Z-Image Turbo when the weight file is on disk. The CPU marcher otherwise."""
    try:
        from xenoform.models_setup import models_dir

        root = Path(models_dir() or "")
    except Exception:
        return "cpu-keyframe"
    if not root.is_dir():
        return "cpu-keyframe"
    stills = ("z-image-turbo", "z_image_turbo", "zimage_turbo", "z-image")
    klein = ("flux-2-klein", "flux2-klein", "flux-2-klein-4b", "flux3-image-klein", "flux3_image_klein")

    def names() -> list[str]:
        found = []
        for path in root.iterdir():
            found.append(path.name.lower())
            if path.is_dir():
                for child in path.iterdir():
                    found.append(child.name.lower())
        return found

    try:
        listed = names()
    except OSError:
        return "cpu-keyframe"
    if any(any(token in name for token in stills) for name in listed):
        return "z-image-turbo"
    if any(any(token in name for token in klein) for name in listed):
        return "flux-klein"
    return "cpu-keyframe"



def _painted_animatic(directed: dict, scenes: list[dict], audio_path: Path, out_path: Path, cache, seed: int,
                      palette: str, flash: float, on_scene, cancel, report) -> dict[str, Any]:
    """The classic animatic (Advanced / Director mode): a 4 s painted proof, then the keyframe cut."""
    work = out_path.parent
    report("animatic", 0.04, "4 second proof")
    proof_src = [scene for scene in scenes if float(scene.get("start") or 0) < 4.0] or scenes[:1]
    proof_keys, _proof_hits, proof_misses, proof_paint, _proof_segments = _gather_keyframes(
        directed, proof_src, cache, seed=seed, palette=palette, cancel=cancel
    )
    proof_board = [dict(scene) for scene in proof_src]
    proof_board[-1]["end"] = min(float(proof_board[-1].get("end") or 0), 4.0)
    proof_frames = _compose(proof_board, proof_keys, directed, len(proof_board) - 1, float(FPS), float(flash))
    proof_path = work / "proof.mp4"
    _publish(proof_frames, proof_path, float(FPS), Path(audio_path))
    proof_verdict = "one more pass"
    try:
        from xenoform.critic import delivery_spec, measure, read_loudness

        step = max(1, int(round(0.2 * FPS)))
        sample = np.stack(proof_frames[::step])
        sample_times = np.arange(len(sample), dtype=np.float64) * (step / float(FPS))
        eyes = measure(
            sample,
            sample_times,
            spec=delivery_spec("turbo", duration=4.0),
            actual={
                "width": _aw(),
                "height": _ah(),
                "fps": float(FPS),
                "duration": len(proof_frames) / float(FPS),
            },
            beats=list(directed.get("beats") or []),
            loudness=read_loudness(proof_path),
        )
        proof_verdict = str(eyes.get("verdict") or proof_verdict)
    except Exception:
        proof_verdict = "one more pass"

    painted = render_animatic(
        directed,
        scenes,
        Path(audio_path),
        out_path,
        cache,
        seed=seed,
        palette=palette,
        flash=float(flash),
        on_scene=on_scene,
        cancel=cancel,
    )
    painted["misses"] = int(proof_misses) + int(painted["misses"])
    painted["paint_s"] = round(float(proof_paint) + float(painted["paint_s"]), 3)
    painted["proof_frames"] = proof_frames
    painted["proof_verdict"] = proof_verdict
    return painted


def _run_turbo(
    cfg: dict,
    audio_path: Path,
    state: dict,
    out_path: Path,
    work: Path,
    on_progress: Callable[[str, float, str], None] | None = None,
    tier_id: str | None = None,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Analyze (cached), play the animatic, and only then consider a video model."""
    from xenoform.analyze import write_features
    from xenoform.director import apply_director, apply_endpoint, apply_quality, resolve_flash
    from xenoform.llm import release_llm
    from xenoform.notes import stamp_retime

    started = time.perf_counter()

    def report(stage: str, frac: float, detail: str) -> None:
        _stop(cancel)
        if on_progress:
            on_progress(stage, frac, detail)

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _stop(cancel)
    release_llm()
    tuned = apply_endpoint(apply_quality(cfg, state), state)
    tuned = apply_tier(tuned, resolve_tier(tier_id), quality="turbo")
    seed = int(state.get("seed") or DEFAULT_SEED)
    tuned["seed"] = seed
    tuned.setdefault("comfy", {})
    tuned["comfy"]["checkpoint_name"] = guard_checkpoint(tuned["comfy"].get("checkpoint_name"))
    tuned["comfy"]["steps"] = min(int(tuned["comfy"].get("steps") or VIDEO_STEPS), 6)
    tuned["comfy"]["resident"] = True
    tuned["comfy"]["width"] = VIDEO_W
    tuned["comfy"]["height"] = VIDEO_H
    # The GPU pass has to see the vibe and the story, not the default section prompt.
    from xenoform.director import prompts_for_state

    tuned["prompts"] = {**(tuned.get("prompts") or {}), **prompts_for_state(state)}

    report("analyze", 0.05, "Reading the track")
    cache = cache_root(work)
    features, analysis_hit = _analyze(Path(audio_path), tuned, work / "features.json", cache)
    report("analyze", 1.0, "Track already analyzed" if analysis_hit else f"{features['n_frames']} frames")
    directed = apply_director(features, state)
    scenes = _scenes_for(directed, state)
    if not scenes:
        raise RuntimeError("Turbo needs a scene to put on the beat.")
    only = [str(item) for item in (state.get("only_scenes") or []) if str(item)]
    if only:
        report("animatic", 0.08, "Queued " + ", ".join(only))
    directed = stamp_retime(directed, scenes) or directed
    write_features(work / "features.json", directed)
    flash, flashes_on = resolve_flash(state, 0.18)
    if not flashes_on:
        flash = 0.0
    palette = str(state.get("palette") or "neutral")
    from xenoform.timing import apply_timing, timing_document, write_timing

    timing_path = write_timing(work / "timing.json", timing_document(directed, scenes, seed=seed))
    directed = apply_timing(directed, timing_path)

    def on_scene(index: int, total: int) -> None:
        report("animatic", (index + 1) / max(total, 1), f"Scene {index + 1} of {total}")

    simple_mode = str(state.get("mode") or "") == "simple"  # the Simple desk sends mode: "simple"
    painted: dict = {}
    if simple_mode:
        # Simple mode: the draft is the vibe's stills hard-cut on the planned shots (seconds, and it looks like the
        # real cut's skeleton), not the CPU blob animatic, which for a full song took minutes and looked like nothing.
        from xenoform.dense import stills_animatic

        report("animatic", 0.1, "Cutting the stills to the beat")
        try:
            # the stills draft follows the cut's aspect (the live-keyframe landscape rule is for the painted path)
            info = stills_animatic(directed, state, Path(audio_path), out_path, work, size=animatic_size({**state, "live": False}))
            painted = {"hits": 0, "misses": 0, "paint_s": 0.0, "segments": [], "batches": 0, "fps": float(FPS),
                       "stills": info, "proof_frames": [], "proof_verdict": "stills"}
        except Exception as exc:
            log.warning("stills animatic failed, falling back to the painted animatic: %s", exc)
            painted = {}
    if not painted:
        painted = _painted_animatic(directed, scenes, Path(audio_path), out_path, cache, seed, palette, float(flash),
                                    on_scene, cancel, report)
    proof_frames = painted.pop("proof_frames", [])
    proof_verdict = painted.pop("proof_verdict", "stills")
    filled_with = ""
    fill_warning = ""
    if state.get("interpolate"):
        from xenoform.live_mode import fill_frames

        try:
            filled_with = fill_frames(out_path, float(FPS), 24.0)
        except Exception as exc:
            from xenoform.errors import plain_error

            fill_warning = f"Frame fill did not run. {plain_error(exc)}"
    from xenoform.cutdesk import maybe_stamp

    maybe_stamp(out_path, state, float(FPS))
    overlay_text(out_path, directed.get("text_cards") or [])
    report("assemble", 1.0, "Animatic locked to the track")

    warning = fill_warning
    mode = "animatic"
    morph_info: dict = {}
    if state.get("live"):
        report("restyle", 0.1, "GPU morphs, LTX 0.9.5 at 512x288. The draft stays up while this runs.")
        try:
            _stop(cancel)
            from xenoform.cloud_morph import paid_cloud_enabled

            paid_ok = paid_cloud_enabled(tuned, bool(state.get("paid_cloud")))
            if state.get("cloud_quality") and paid_ok:
                # Opt-in only, PAID (see cloud_morph): free local draft first, then LTX-2.5.
                from xenoform.cloud_morph import run_cloud_quality

                morph_info, cloud_warning = run_cloud_quality(
                    directed, Path(audio_path), out_path, work, tuned, state, report, cancel=cancel
                )
                warning = cloud_warning or warning
            else:
                from xenoform.dense import run_simple, wants_finishing
                from xenoform.morph_pass import run_morph_pass

                if state.get("cloud_quality"):
                    warning = "Paid cloud renders are off, so this cut used the open-weights morphs on this machine."
                if wants_finishing(state):
                    # Dense energy, 9:16 / 1:1, Final tier, end card: the open-weights finishing pass.
                    morph_info = run_simple(directed, Path(audio_path), out_path, work, tuned, state, report, cancel=cancel)
                else:
                    morph_info = run_morph_pass(directed, scenes, Path(audio_path), out_path, work, tuned, state, report, cancel=cancel)
            mode = "turbo"
            report("restyle", 1.0, "GPU morphs locked to the beat")
        except JobCancelled:
            raise
        except Exception as exc:
            from xenoform.errors import plain_error

            warning = f"The animatic is ready. The Turbo video pass did not run. {plain_error(exc)}"
            mode = "animatic"

    elapsed = time.perf_counter() - started
    manifest = {
        "mode": mode,
        "quality": "turbo",
        "seed": seed,
        "checkpoint": tuned["comfy"]["checkpoint_name"],
        "steps": int(morph_info.get("steps") or tuned["comfy"]["steps"]),
        "resolution": morph_info.get("render") or f"{VIDEO_W}x{VIDEO_H}",
        "animatic_resolution": f"{_aw()}x{_ah()}",
        "keyframe_model": keyframe_backend(),
        "keyframe_steps": KEY_STEPS,
        "fps": FPS,
        "resident": True,
        "llm": "unloaded",
        "analysis_cached": analysis_hit,
        "keyframe_hits": painted["hits"],
        "keyframe_misses": painted["misses"],
        "paint_s": painted["paint_s"],
        "seconds": round(elapsed, 3),
        "batches": painted["batches"],
        "segments": painted["segments"],
        "warning": warning,
        "interpolate": filled_with,
        "motion_guide": str(state.get("guide_path") or ""),
        "only_scenes": only,
        "proof": {"path": "proof.mp4", "verdict": proof_verdict, "seconds": round(len(proof_frames) / float(FPS), 3)},
        "timing": "timing.json",
        "morph_pass": morph_info,
    }
    (work / "turbo.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    try:
        from xenoform.director_notes import write_director_notes

        write_director_notes(work, state, directed, tuned)
    except Exception:
        import logging

        logging.getLogger("xenoform").exception("director notes")
    detail = f"Animatic ready in {elapsed:.1f}s"
    if painted["hits"]:
        detail += f" Â· {painted['hits']} cached"
    if warning:
        detail = warning
    report("assemble", 1.0, detail)
    return {
        "mode": mode,
        "chunks": len(scenes),
        "fades": [],
        "seconds": round(elapsed, 3),
        "cached_keyframes": painted["hits"],
        "rendered_keyframes": painted["misses"],
        "paint_s": painted["paint_s"],
        "analysis_cached": analysis_hit,
        "seed": seed,
        "checkpoint": manifest["checkpoint"],
        "warning": warning,
        "quality": "turbo",
    }


def run_turbo(*args, **kwargs):
    """Turbo/animatic run, sized to the cut's aspect (see animatic_size)."""
    state = kwargs.get("state")
    if state is None:
        state = next((a for a in args if isinstance(a, dict) and ("aspect" in a or "scenes" in a or "blocks" in a)), None)
    token = _SIZE.set(animatic_size(state))
    try:
        return _run_turbo(*args, **kwargs)
    finally:
        _SIZE.reset(token)
