"""Fast Final: the Draft's morphs upscaled to the Final's size.

A Final spends its time in LTX-2.3, a 22B model that does not fit this 12 GB card with 32 GB of RAM and is read again
on every step (28 Oct: 340 s a 2-3 s shot, 5.5 min a morph, 1:33:59 for a 20 s cut of 15). Rendering smaller does not
help it: the pixels are cheap, the weights are not. Fast Final keeps the Draft's model (LTX 0.9.5, 320x576 portrait
morphs, about 21 s each) and runs each finished clip through an image upscaler on ComfyUI to 1080x1920, then the cut
composes at that size like a Final. The motion is the Draft's; the picture is sharp at full size.

One ComfyUI job a clip: LoadVideo, its frames through ``MODEL`` (4x), Lanczos to the output size, SaveVideo. A clip
that fails to upscale keeps its Draft file (the compositor scales it), with a note.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

log = logging.getLogger("xenoform")

TIER = "fast"
LABEL = "Fast Final"
# Measured 28 Oct on a 320x576 Draft clip of 97 frames to 1080x1920, ComfyUI to itself, load and encode included:
# realesr-animevideov3 (Real-ESRGAN's compact video model, BSD-3) 19.6 s, a little painterly at 1:1 but clean;
# RealESRGAN_x4plus (the Final's) 106.9 s, finer texture; Lanczos alone 8.6 s, soft. XENO_FAST_UPSCALER picks another.
MODEL = os.environ.get("XENO_FAST_UPSCALER", "").strip() or "realesr-animevideov3.pth"
OUT_916 = (1080, 1920)
OUT_169 = (1920, 1080)
SECONDS_PER_CLIP = 20.0  # the upscale of one Draft clip with MODEL, measured as above


def out_size(aspect: str) -> tuple[int, int]:
    """The Fast Final's output: 1080x1920 for 9:16, 1920x1080 for 16:9, 1080x1080 for 1:1."""
    if aspect == "9:16":
        return OUT_916
    if aspect == "1:1":
        return (1080, 1080)
    return OUT_169


def graph(out_w: int, out_h: int, *, model: str = MODEL, fps: float = 24.0, prefix: str = "xenoform/fast") -> dict:
    """ComfyUI API graph for one clip: node 1 takes the video (``set_input("1", "file", ...)``), node 9 saves it."""
    g = {
        "1": {"class_type": "LoadVideo", "inputs": {"file": "clip.mp4"}},
        "2": {"class_type": "GetVideoComponents", "inputs": {"video": ["1", 0]}},
        "5": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": model}},
        "6": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["5", 0], "image": ["2", 0]}},
        "7": {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "upscale_method": "lanczos", "width": int(out_w),
                                                     "height": int(out_h), "crop": "center"}},
        "8": {"class_type": "CreateVideo", "inputs": {"images": ["7", 0], "fps": float(fps)}},
        "9": {"class_type": "SaveVideo", "inputs": {"video": ["8", 0], "filename_prefix": prefix, "format": "auto", "codec": "auto"}},
    }
    return g


def upscale_clips(clips: list[Path], work: Path, size: tuple[int, int], cfg: dict, *, client=None,
                  cancel: Callable[[], bool] | None = None, report: Callable[[str, float, str], None] | None = None,
                  span: tuple[float, float] = (0.5, 0.58), fps: float = 24.0) -> tuple[list[Path], list[dict]]:
    """Each Draft clip upscaled to ``size`` (``fast00.mp4``...). Returns the clips (a failed one keeps its Draft file)
    and one note per failure."""
    from xenoform import morph_pass as mp
    from xenoform.cloud_morph import _client, _job_result

    client = client or _client(cfg)
    out: list[Path] = []
    notes: list[dict] = []
    lo, hi = span
    for k, clip in enumerate(clips):
        mp.stop_queued([], cancel)
        if report:
            report("restyle", lo + (hi - lo) * k / max(1, len(clips)), f"Fast Final: upscaling morph {k + 1} of {len(clips)} to {size[0]}x{size[1]}")
        dest = Path(work) / f"fast{k:02d}.mp4"
        try:
            wf = client.workflows.from_json(graph(size[0], size[1], fps=fps))
            wf.set_input("1", "file", client.assets.from_file(str(clip)))
            job = client.submit(wf)
            mp.wait_or_cancel(job, [job], cancel)
            result = _job_result(client, job)
            outs = list(result.get_outputs("9")) or list(result.outputs)
            if not outs:
                raise RuntimeError("the upscale finished with no video")
            next((o for o in outs if getattr(o, "type", None) == "video"), outs[0]).to_file(str(dest))
            out.append(dest)
        except Exception as exc:  # one clip that does not upscale stays a Draft clip, the cut goes on
            from xenoform.turbo import JobCancelled

            if isinstance(exc, JobCancelled):
                raise
            log.warning("fast final: clip %d kept at Draft size: %s", k, exc)
            notes.append({"shot": k, "fallback": "draft-size", "why": str(exc)[:200]})
            out.append(Path(clip))
    return out, notes
