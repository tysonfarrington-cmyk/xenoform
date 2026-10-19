"""Final quality tier for Simple mode: LTX-2.3 fp8 morphs plus a 4x-ClearReality upscale.

Draft (the default) stays LTX 0.9.5 at 512x288. Final renders each A->B morph with
LTX-2.3 22B distilled fp8 in two stages (384x224 -> x2 latent upsample -> 768x448),
then upscales the decoded frames with 4x-ClearReality and scales them to 1280x720.
All open weights, all local.

Fallbacks, in order, when a shot fails (out of memory included):
  1. the same LTX-2.3 shot without the ClearReality pass (Lanczos to 1280x720)
  2. the LTX 0.9.5 Draft shot
The result says which shots fell back and why.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

CKPT = "ltx-2.3-22b-distilled-fp8.safetensors"
TEXT_ENCODER = "gemma_3_12B_it_fp4_mixed.safetensors"
LATENT_UPSCALER = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
UPSCALER = "4x-ClearRealityV1.safetensors"
FILES = (("checkpoints", CKPT), ("text_encoders", TEXT_ENCODER), ("latent_upscale_models", LATENT_UPSCALER),
         ("upscale_models", UPSCALER))
RENDER_W, RENDER_H = 768, 448  # multiples of 64, so stage 1 (half size) is still a multiple of 32
OUT_W, OUT_H = 1280, 720
FPS = 24
STAGE1_SIGMAS = "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"
STAGE2_SIGMAS = "0.85, 0.7250, 0.4219, 0.0"
NEGATIVE = "text, letters, watermark, logo, two objects, cut, flicker, blurry, low quality, cartoon, people, hands"
OOM_WORDS = ("out of memory", "outofmemory", "cuda error", "allocation", "oom")

# Honest planning figures, seconds. They are estimates until the overnight calibration
# run measures this card; the desk labels them that way.
ETA = {"load_s": 90.0, "per_shot_s": 55.0, "upscale_per_shot_s": 25.0, "per_second_extra_s": 6.0,
       "measured": False}


def present(root: Path | None = None) -> dict:
    """Which Final-tier files are on disk (by ComfyUI models folder)."""
    if root is None:
        try:
            from xenoform.models_setup import models_dir

            root = Path(models_dir() or "")
        except Exception:
            root = None
    found = {name: bool(root and (Path(root) / folder / name).is_file()) for folder, name in FILES}
    return {"files": found, "ready": all(found.values()), "upscale": found[UPSCALER]}


def eta_seconds(shots: list[dict], upscale: bool = True, warm: bool = False) -> int:
    total = 0.0 if warm else ETA["load_s"]
    for shot in shots:
        render = float(shot.get("render_s") or shot.get("seconds") or 2.0)
        total += ETA["per_shot_s"] + ETA["per_second_extra_s"] * max(0.0, render - 2.0)
        if upscale:
            total += ETA["upscale_per_shot_s"]
    return int(round(total))


def gen_length(seconds: float) -> int:
    frames = int(round(max(1.0, min(float(seconds), 5.0)) * FPS))
    n = 8 * ((max(frames - 1, 0) + 7) // 8) + 1
    return int(min(121, max(25, n)))


def graph(prompt: str, *, length: int, seed: int, upscale: bool = True, prefix: str = "xenoform/final") -> dict:
    """ComfyUI API graph for one LTX-2.3 first/last-frame morph. Images go in nodes 100 and 101."""
    g: dict = {}

    def n(i, cls, **inp):
        g[str(i)] = {"class_type": cls, "inputs": inp}

    n(1, "CheckpointLoaderSimple", ckpt_name=CKPT)
    n(2, "LTXAVTextEncoderLoader", text_encoder=TEXT_ENCODER, ckpt_name=CKPT, device="default")
    n(3, "LTXVAudioVAELoader", ckpt_name=CKPT)
    n(4, "CLIPTextEncode", clip=["2", 0], text=prompt)
    n(5, "CLIPTextEncode", clip=["2", 0], text=NEGATIVE)
    n(6, "LTXVConditioning", positive=["4", 0], negative=["5", 0], frame_rate=float(FPS))
    n(7, "EmptyLTXVLatentVideo", width=RENDER_W // 2, height=RENDER_H // 2, length=length, batch_size=1)
    n(100, "LoadImage", image="a.png")
    n(101, "LoadImage", image="b.png")
    n(102, "LTXVPreprocess", image=["100", 0], img_compression=18)
    n(103, "LTXVPreprocess", image=["101", 0], img_compression=18)

    def guides(base: int, pos, neg, lat):
        n(base, "LTXVAddGuide", positive=pos, negative=neg, vae=["1", 2], latent=lat, image=["102", 0], frame_idx=0, strength=1.0)
        n(base + 1, "LTXVAddGuide", positive=[str(base), 0], negative=[str(base), 1], vae=["1", 2], latent=[str(base), 2],
          image=["103", 0], frame_idx=-1, strength=1.0)
        return [str(base + 1), 0], [str(base + 1), 1], [str(base + 1), 2]

    p1, n1, l1 = guides(110, ["6", 0], ["6", 1], ["7", 0])
    n(9, "LTXVEmptyLatentAudio", frames_number=length, frame_rate=FPS, batch_size=1, audio_vae=["3", 0])
    n(10, "LTXVConcatAVLatent", video_latent=l1, audio_latent=["9", 0])
    n(11, "CFGGuider", model=["1", 0], positive=p1, negative=n1, cfg=1.0)
    n(12, "KSamplerSelect", sampler_name="euler")
    n(13, "ManualSigmas", sigmas=STAGE1_SIGMAS)
    n(14, "RandomNoise", noise_seed=int(seed))
    n(15, "SamplerCustomAdvanced", noise=["14", 0], guider=["11", 0], sampler=["12", 0], sigmas=["13", 0], latent_image=["10", 0])
    n(16, "LTXVSeparateAVLatent", av_latent=["15", 0])
    n(30, "LTXVCropGuides", positive=p1, negative=n1, latent=["16", 0])
    n(17, "LatentUpscaleModelLoader", model_name=LATENT_UPSCALER)
    n(18, "LTXVLatentUpsampler", samples=["30", 2], upscale_model=["17", 0], vae=["1", 2])
    p2, n2, l2 = guides(120, ["6", 0], ["6", 1], ["18", 0])
    n(20, "LTXVConcatAVLatent", video_latent=l2, audio_latent=["16", 1])
    n(31, "CFGGuider", model=["1", 0], positive=p2, negative=n2, cfg=1.0)
    n(21, "ManualSigmas", sigmas=STAGE2_SIGMAS)
    n(22, "RandomNoise", noise_seed=int(seed) + 1000)
    n(23, "SamplerCustomAdvanced", noise=["22", 0], guider=["31", 0], sampler=["12", 0], sigmas=["21", 0], latent_image=["20", 0])
    n(24, "LTXVSeparateAVLatent", av_latent=["23", 0])
    n(32, "LTXVCropGuides", positive=p2, negative=n2, latent=["24", 0])
    n(25, "VAEDecodeTiled", samples=["32", 2], vae=["1", 2], tile_size=512, overlap=64, temporal_size=64, temporal_overlap=8)
    frames = ["25", 0]
    if upscale:
        n(40, "UpscaleModelLoader", model_name=UPSCALER)
        n(41, "ImageUpscaleWithModel", upscale_model=["40", 0], image=frames)
        frames = ["41", 0]
    n(42, "ImageScale", image=frames, upscale_method="lanczos", width=OUT_W, height=OUT_H, crop="center")
    n(27, "CreateVideo", images=["42", 0], fps=float(FPS))
    n(28, "SaveVideo", video=["27", 0], filename_prefix=prefix, format="auto", codec="auto")
    return g


def is_oom(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(word in text for word in OOM_WORDS)


def final_clips(shots: list[dict], stills: list[dict], work: Path, cfg: dict, seed: int, vibe: str, *, client=None,
                cancel: Callable[[], bool] | None = None, report: Callable[[str, float, str], None] | None = None,
                draft: Callable[[list[int]], dict[int, Path]] | None = None) -> tuple[list[Path], list[dict]]:
    """Render every shot on LTX-2.3 (+ ClearReality). Returns clips and one note per fallback.

    ``draft(indices)`` renders the given shots on LTX 0.9.5 and returns {index: clip}; it is
    the last fallback. Shots are rendered one at a time so a failure costs one shot, not the run.
    """
    from xenoform import morph_pass as mp
    from xenoform.cloud_morph import _client, _job_result

    client = client or _client(cfg)
    prompt = mp.prompt_for(vibe, "ltx25")
    assets: dict = {}
    upscale = os.environ.get("XENO_FINAL_UPSCALE", "1").strip() not in {"0", "false", "off"}

    def asset(path: str):
        if path not in assets:
            assets[path] = client.assets.from_file(path)
        return assets[path]

    def one(i: int, shot: dict, with_upscale: bool) -> Path:
        wf = client.workflows.from_json(graph(prompt, length=gen_length(float(shot.get("render_s") or shot["seconds"])),
                                              seed=int(seed) + i, upscale=with_upscale))
        wf.set_input("100", "image", asset(stills[i]["path"]))
        wf.set_input("101", "image", asset(stills[i + 1]["path"]))
        job = client.submit(wf)
        mp.wait_or_cancel(job, [job], cancel)
        result = _job_result(client, job)
        outs = list(result.get_outputs("28")) or list(result.outputs)
        if not outs:
            raise RuntimeError(f"Final shot {i + 1} finished with no video.")
        dest = Path(work) / f"final{i:02d}.mp4"
        next((o for o in outs if getattr(o, "type", None) == "video"), outs[0]).to_file(str(dest))
        return dest

    clips: dict[int, Path] = {}
    notes: list[dict] = []
    need_draft: list[int] = []
    for i, shot in enumerate(shots):
        mp.stop_queued([], cancel)
        if report:
            report("restyle", 0.12 + 0.75 * i / max(len(shots), 1), f"Final: morph {i + 1} of {len(shots)} on LTX-2.3")
        try:
            clips[i] = one(i, shot, upscale)
            continue
        except Exception as exc:
            from xenoform.turbo import JobCancelled

            if isinstance(exc, JobCancelled):
                raise
            first = exc
        if upscale:
            try:
                clips[i] = one(i, shot, False)
                notes.append({"shot": i, "fallback": "ltx23-no-upscale", "why": str(first)[:200], "oom": is_oom(first)})
                continue
            except Exception as exc:  # noqa: BLE001 - fall through to Draft
                from xenoform.turbo import JobCancelled

                if isinstance(exc, JobCancelled):
                    raise
                first = exc
        need_draft.append(i)
        notes.append({"shot": i, "fallback": "ltx095-draft", "why": str(first)[:200], "oom": is_oom(first)})
    if need_draft:
        if draft is None:
            raise RuntimeError("Final tier failed and no Draft fallback was given.")
        clips.update(draft(need_draft))
    return [clips[i] for i in range(len(shots))], notes
