"""Browser Live tier helpers: drive curves, the optional Live+AI note, and frame fill.

Live itself is the WebGL march in the desk. Nothing here imports a video model.
Live+AI is optional and, when it is missing, the only result is a sentence.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from xenoform.video import ffmpeg_bin


def live_drive(features: dict | None) -> dict[str, Any]:
    """About 20 samples a second of the bands the marcher listens to."""
    features = features or {}
    frames = list(features.get("frames") or [])
    fps = float(features.get("fps") or 12) or 12.0
    if not frames:
        beats = [float(beat) for beat in features.get("beats") or []]
        duration = float(features.get("duration") or (beats[-1] if beats else 1.0))
        rate = 20.0
        count = max(1, int(round(duration * rate)))
        onset = []
        for index in range(count):
            t = index / rate
            onset.append(1.0 if any(abs(t - beat) < 0.04 for beat in beats) else 0.0)
        return {"fps": rate, "bass": onset, "mid": onset, "high": [0.0] * count, "onset": onset, "stems": "beats"}
    step = max(1, int(round(fps / 20.0)))
    picked = frames[::step]

    def column(key: str) -> list[float]:
        return [round(float(frame.get(key) or 0.0), 4) for frame in picked]

    loud_key = "energy" if "energy" in picked[0] else "rms"
    return {
        "fps": round(fps / step, 4),
        "bass": column("bass"),
        "mid": column("mid"),
        "high": column("high"),
        "onset": column("onset_env"),
        "loud": column(loud_key),
        "stems": "librosa",
    }


def live_ai_status() -> dict[str, Any]:
    """StreamDiffusion is optional. A missing install leaves Live running."""
    present = False
    try:
        import streamdiffusion  # noqa: F401

        present = True
    except Exception:
        present = False
    if present:
        detail = "Live+AI is installed. The desk still draws Live until that pass is pointed at this machine."
    else:
        detail = "Live+AI is not installed. Live is playing. Nothing else was changed."
    return {
        "id": "live-ai",
        "name": "Live+AI",
        "required": False,
        "present": present,
        "detail": detail,
        "size_label": "optional",
    }


def tensorrt_status() -> dict[str, Any]:
    present = False
    try:
        import tensorrt  # noqa: F401

        present = True
    except Exception:
        present = False
    if present:
        detail = "TensorRT is installed. Turbo, Draft, and Final still run without an engine file."
    else:
        detail = "TensorRT is optional and is not installed. The regular checkpoint is used."
    return {"id": "tensorrt", "name": "TensorRT", "required": False, "present": present, "detail": detail, "size_label": "optional"}


def interpolator_name() -> str:
    for name in ("rife-ncnn-vulkan", "rife", "film"):
        if shutil.which(name):
            return name
    return "minterpolate"


def fill_frames(path: Path, src_fps: float, dst_fps: float = 24.0) -> str:
    """Raise the frame rate. ffmpeg minterpolate is the path that needs no extra model."""
    path = Path(path)
    if dst_fps <= float(src_fps) + 0.5 or not path.exists():
        return interpolator_name()
    tool = interpolator_name()
    dest = path.with_suffix(".filled.mp4")
    # RIFE and FILM, when present, are named in Setup. The fill that always runs
    # is ffmpeg's motion interpolation, so a missing engine cannot break the cut.
    subprocess.check_call(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-vf",
            f"minterpolate=fps={int(dst_fps)}:mi_mode=blend",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            str(dest),
        ]
    )
    dest.replace(path)
    return tool


def fit_guide(src: Path, dest: Path, width: int, height: int, fps: float) -> None:
    """Scale a Live recording onto the beauty-pass frame grid."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vf",
            f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=increase,crop={int(width)}:{int(height)},fps={float(fps)}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "20",
            str(dest),
        ]
    )


def webm_to_mp4(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )
