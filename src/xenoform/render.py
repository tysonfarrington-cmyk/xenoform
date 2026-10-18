"""Dispatch the base-form render to the CPU marcher, or moderngl when it starts."""

from __future__ import annotations

import logging
from pathlib import Path

from xenoform.render_cpu import form_from_frame, render_frame
from xenoform.video import write_mp4

log = logging.getLogger("xenoform")


def smooth_mutate(features: dict, seconds: float = 0.28) -> None:
    """Soften section-to-section mutation so the body morphs instead of popping.

    Updates frames in place. The original section label is kept for prompts.
    """
    frames = features["frames"]
    if not frames:
        return
    fps = float(features["fps"])
    win = max(1, int(round(seconds * fps)))
    values = [float(frame["mutate"]) for frame in frames]
    if win <= 1:
        return
    smoothed = []
    for i in range(len(values)):
        lo = max(0, i - win // 2)
        hi = min(len(values), i + win // 2 + 1)
        smoothed.append(sum(values[lo:hi]) / (hi - lo))
    for frame, value in zip(frames, smoothed):
        frame["mutate"] = round(float(value), 6)


def render_sequence(
    features: dict,
    out_path: str | Path,
    width: int,
    height: int,
    max_steps: int = 40,
    backend: str = "cpu",
    crf: int = 20,
    audio_path: str | Path | None = None,
    depth_path: str | Path | None = None,
    mask_path: str | Path | None = None,
    png_dir: str | Path | None = None,
    on_progress=None,
) -> None:
    if width % 2 or height % 2:
        raise ValueError("Render width and height must be even (yuv420).")
    smooth_mutate(features)
    frames = features["frames"]
    fps = float(features["fps"])
    use_gpu = backend in {"gpu", "auto"}
    gpu_render = None
    if use_gpu:
        gpu_render = _try_gpu(width, height, max_steps)
        if gpu_render is None and backend == "gpu":
            log.warning("moderngl context unavailable; falling back to the CPU marcher")
    beauty = []
    depth_frames = [] if depth_path else None
    mask_frames = [] if mask_path else None
    if png_dir:
        Path(png_dir).mkdir(parents=True, exist_ok=True)

    log.info("rendering %s frames at %sx%s (%s)", len(frames), width, height, "gpu" if gpu_render else "cpu")
    for index, frame in enumerate(frames):
        form = form_from_frame(frame)
        if gpu_render is not None:
            rgb, depth, mask = gpu_render(form)
        else:
            rgb, depth, mask = render_frame(form, width, height, max_steps=max_steps)
        beauty.append(rgb)
        if depth_frames is not None:
            depth_frames.append(_gray_rgb(depth))
        if mask_frames is not None:
            mask_frames.append(_gray_rgb(mask))
        if png_dir:
            _write_png(Path(png_dir) / f"frame_{index:05d}.png", rgb)
        if index == 0 or (index + 1) % 12 == 0 or index + 1 == len(frames):
            log.info("frame %s/%s", index + 1, len(frames))
        if on_progress and (index % 4 == 0 or index + 1 == len(frames)):
            on_progress(index + 1, len(frames))

    write_mp4(out_path, beauty, fps, audio_path=audio_path, crf=crf)
    if depth_path and depth_frames is not None:
        write_mp4(depth_path, depth_frames, fps, crf=crf)
    if mask_path and mask_frames is not None:
        write_mp4(mask_path, mask_frames, fps, crf=crf)
    log.info("wrote %s", out_path)


def _gray_rgb(plane) -> "object":
    import numpy as np

    return np.repeat(plane[:, :, None], 3, axis=2)


def _write_png(path: Path, rgb) -> None:
    # Avoid a hard Pillow dependency: ffmpeg can encode a single frame, but a
    # tiny PPM plus no extra package is simpler and lossless.
    height, width = rgb.shape[:2]
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    ppm = path.with_suffix(".ppm")
    ppm.write_bytes(header + rgb.tobytes())
    # Keep the extension the caller asked for when it is ppm; otherwise try
    # ffmpeg to png and drop the ppm.
    if path.suffix.lower() == ".ppm":
        return
    from xenoform.video import ffmpeg_bin
    import subprocess

    subprocess.check_call(
        [ffmpeg_bin(), "-y", "-loglevel", "error", "-i", str(ppm), str(path)],
    )
    ppm.unlink(missing_ok=True)


def _try_gpu(width: int, height: int, max_steps: int):
    try:
        from xenoform.render_gpu import GpuRenderer
    except Exception as exc:  # pragma: no cover - import guard
        log.info("GPU renderer import failed: %s", exc)
        return None
    try:
        renderer = GpuRenderer(width, height, max_steps)
        renderer.render  # touch
    except Exception as exc:
        log.info("GPU context failed: %s", exc)
        return None

    def _call(form):
        return renderer.render(form)

    return _call
