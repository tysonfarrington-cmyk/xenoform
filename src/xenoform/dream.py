"""Dream this span: a StreamDiffusion-style pass over 1 to 3 seconds of a finished cut, on the timeline
(docs/MORPH_ENGINE_PLAN.md; Tys, 28 Oct: "Build Dream this span on the timeline: Z-Image Turbo img2img over a chosen 1 to
3 s, at 12 fps, cut in like a generated run").

StreamDiffusion itself is not on this machine (no SD-Turbo-class model, no nodes), so this is the nearest thing made of
what is: Z-Image Turbo img2img (``workflows/zimage_i2i_api.json``, 8 steps, the vibe's look in the prompt) over the
frames the span plays, every other frame (12 a second) and each held for two output frames with the second a half
blend into the next, so it reads as a hand-drawn 12 fps dream rather than a strobe. Each frame is re-dreamed from its
own picture with one seed for the run, so the object keeps its place while its surface and its meaning drift: the
flicker is the effect. About 2.6 s a dreamed frame on the 3080 Ti once the model is loaded (46 s for the first), so two
seconds is about a minute.

The span is whole shots from the one clicked (``span``: Polly's and your clips stop it). Each shot's clip is replaced by
its dream, played 1:1 (the record's shots carry ``dream``), the cut re-composes through ``dense.recut_from_cache`` with
the knobs, the look and the effects on top, and the joins into and out of the span are cuts, as at a generated run's
edges. Draft and Final cuts both dream (Final at a larger size, about twice the time).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "workflows" / "zimage_i2i_api.json"
N_IMAGE, N_TEXT, N_SAMPLER, N_SAVE = "20", "5", "10", "12"
RANGE = (1.0, 3.0)
SECONDS = (1.0, 2.0, 3.0)
DEPTHS = {"light": 0.35, "deep": 0.55}
SECONDS_PER_FRAME = 2.6   # measured 28 Oct: Z-Image Turbo img2img at 432x768 on the 3080 Ti, warm
COLD_S = 46.0             # the first frame loads the model
SEED = 2727
EVERY = 2                 # one dreamed frame every other output frame: 12 a second at 24


def size_for(tier: str, w: int, h: int) -> tuple[int, int]:
    """The dream's frame size: the clip's aspect at a short side of 432 (Draft) or 576 (Final), multiples of 16."""
    short = 576 if str(tier) == "final" else 432
    if w <= h:
        dw, dh = short, int(round(short * h / max(w, 1) / 16.0)) * 16
    else:
        dh, dw = short, int(round(short * w / max(h, 1) / 16.0)) * 16
    return int(dw), int(dh)


def prompt_for(vibe: str) -> str:
    from xenoform.morph_pass import VIBE_LOOK

    look = VIBE_LOOK.get(vibe, "")
    return ("a dreamlike painterly vision of the same picture, the same composition, the same object, luminous brush "
            f"strokes, {look}").rstrip(", ")


def estimate(frames: int, warm: bool = False) -> float:
    """Seconds of GPU for a span of ``frames`` output frames (one dream every ``EVERY``)."""
    return round((0.0 if warm else COLD_S) + SECONDS_PER_FRAME * ((int(frames) + EVERY - 1) // EVERY), 1)


def span(shots: list[dict], first: int, seconds: float) -> tuple[int, int]:
    """The shots a dream of about ``seconds`` covers from shot ``first``: whole shots, never past the end and never
    into Polly or your own clip; the next shot is taken only while it brings the span nearer the length asked."""
    from xenoform.dense import _under_insert

    n = len(shots)
    if not 0 <= first < n:
        raise ValueError(f"This cut has {n} shots; shot {first} is not one of them.")
    under = _under_insert(shots[first])
    if under in ("Polly", "one of your clips"):
        raise ValueError(f"Shot {first + 1} is {under}; dream over shots that play morphs.")
    want = max(RANGE[0], min(RANGE[1], float(seconds or SECONDS[1])))
    total, last = 0.0, first
    for j in range(first, n):
        if _under_insert(shots[j]) in ("Polly", "one of your clips"):
            break
        length = float(shots[j].get("seconds") or (float(shots[j].get("end") or 0.0) - float(shots[j].get("start") or 0.0)))
        if j > first and abs(total + length - want) >= abs(total - want) - 1e-6:
            break
        total += length
        last = j
        if total >= want - 1e-6:
            break
    return first, last


def _client(cfg: dict | None):
    from xenoform.restyle import _make_client

    return _make_client(cfg or {"comfy": {"proxy_url": "http://127.0.0.1:8189"}})


def dream_frames(pictures: list[np.ndarray], work: Path, *, vibe: str, size: tuple[int, int], denoise: float,
                 seed: int = SEED, cfg: dict | None = None, client=None,
                 report: Callable[[int, int], None] | None = None) -> list[np.ndarray]:
    """Each picture dreamed through Z-Image Turbo img2img at ``size``, in order, one job at a time."""
    from PIL import Image

    from xenoform.cloud_morph import _job_result

    client = client or _client(cfg)
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    graph[N_TEXT]["inputs"]["text"] = prompt_for(vibe)
    graph[N_SAMPLER]["inputs"].update({"denoise": float(denoise), "seed": int(seed)})
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    out: list[np.ndarray] = []
    for k, pic in enumerate(pictures):
        src = work / f"in{k:03d}.png"
        Image.fromarray(np.asarray(pic, np.uint8)).resize(size, Image.LANCZOS).save(src)
        wf = client.workflows.from_json(json.loads(json.dumps(graph)))
        wf.set_input(N_IMAGE, "image", client.assets.from_file(str(src)))
        result = _job_result(client, client.submit(wf))
        outs = list(result.get_outputs(N_SAVE)) or list(result.outputs)
        dest = work / f"dream{k:03d}.png"
        outs[0].to_file(str(dest))
        out.append(np.asarray(Image.open(dest).convert("RGB").resize(size, Image.LANCZOS), np.uint8))
        if report:
            report(k + 1, len(pictures))
    return out


def held(dreams: list[np.ndarray], count: int) -> list[np.ndarray]:
    """``count`` output frames from dreams made every ``EVERY`` frames: each dream on its own frame, the frame after
    it a half blend into the next dream (the last dream held)."""
    frames = []
    for k in range(int(count)):
        i = min(k // EVERY, len(dreams) - 1)
        if k % EVERY == 0 or i + 1 >= len(dreams):
            frames.append(dreams[i])
        else:
            frames.append(((dreams[i].astype(np.float32) + dreams[i + 1].astype(np.float32)) * 0.5 + 0.5).astype(np.uint8))
    return frames


def write_clip(frames: list[np.ndarray], dest: Path, fps: int = 24) -> Path:
    from xenoform.video import ffmpeg_bin

    h, w = frames[0].shape[:2]
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    enc = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", str(int(fps)), "-i", "-", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(dest)],
                           stdin=subprocess.PIPE)
    for f in frames:
        enc.stdin.write(np.ascontiguousarray(f).tobytes())
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError("The dream's clip did not encode.")
    return dest


def dream_span(job_dir: Path, first: int, *, seconds: float = 2.0, depth: str = "light", seed: int | None = None,
               cfg: dict | None = None, report: Callable[[str, float, str], None] | None = None, client=None) -> dict:
    """Dream ``seconds`` (1 to 3) of a finished cut from shot ``first`` and re-compose it; returns the record."""
    from xenoform import dense
    from xenoform.beatfx import read_frames
    from xenoform.cloud_morph import shot_indices

    job_dir = Path(job_dir)
    work = job_dir / "simple"
    rec_path = work / "simple.json"
    if not rec_path.is_file():
        raise FileNotFoundError("This video has no cached morphs to dream over (it was not made by Simple mode).")
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    plan_shots = list(rec.get("plan_shots") or rec.get("shots") or [])
    played = list(rec.get("shots") or plan_shots)
    clips = [str(c) for c in rec.get("clips") or []]
    if not plan_shots or len(clips) != len(plan_shots):
        raise FileNotFoundError("The cached morphs for this video are gone; render it again.")
    depth = str(depth or "light").strip().lower()
    if depth not in DEPTHS:
        raise ValueError(f"A dream is {' or '.join(DEPTHS)}; {depth!r} is neither.")
    first, last = span(plan_shots, int(first), float(seconds))
    fps = int(rec.get("fps") or 24)
    tier = str(rec.get("tier") or "draft")
    vibe = str(rec.get("vibe") or "")
    dreams_log = list(rec.get("dreams") or [])
    seed = int(seed) if seed is not None else int(rec.get("seed") or SEED) + 7000 * (len(dreams_log) + 1)
    run_dir = work / "dreams" / f"{len(dreams_log):02d}"
    # the pictures the span plays: every other output frame of each shot, as the shot plays its clip
    plan = []
    for j in range(first, last + 1):
        s = played[j] if j < len(played) else plan_shots[j]
        count = int(s.get("frames") or round((float(s.get("end") or 0.0) - float(s.get("start") or 0.0)) * fps))
        src = read_frames(Path(clips[j]))
        idx = shot_indices({"frames": count, "start": s.get("start"), "end": s.get("end"), "effects": []}, len(src))
        plan.append((j, count, [src[int(idx[k])] for k in range(0, count, EVERY)]))
    pictures = [p for _, _, pics in plan for p in pics]
    h0, w0 = pictures[0].shape[:2]
    size = size_for(tier, w0, h0)
    total_s = sum(c for _, c, _ in plan) / fps
    if report:
        report("restyle", 0.08, f"Dreaming {total_s:.1f} s over shots {first + 1} to {last + 1}: {len(pictures)} frames "
                                f"({depth}), about {int(estimate(sum(c for _, c, _ in plan)))} s on the GPU")
    started = time.perf_counter()

    def step(k: int, n: int) -> None:
        if report:
            report("restyle", 0.1 + 0.45 * k / max(n, 1), f"Dreaming frame {k} of {n}")

    dreamed = dream_frames(pictures, run_dir / "frames", vibe=vibe, size=size, denoise=DEPTHS[depth], seed=seed,
                           cfg=cfg, client=client, report=step)
    new_clips, at = {}, 0
    for q, (j, count, pics) in enumerate(plan):
        mine = dreamed[at:at + len(pics)]
        at += len(pics)
        dest = write_clip(held(mine, count), run_dir / f"shot{j:03d}.mp4", fps=fps)
        new_clips[j] = str(dest)
        clips[j] = str(dest)
        for lst in (rec.get("plan_shots") or [], rec.get("shots") or []):
            if j < len(lst) and isinstance(lst[j], dict):
                lst[j]["dream"] = {"run": len(dreams_log), "index": q}
    from datetime import datetime

    entry = {"first": first, "last": last, "start": float(plan_shots[first].get("start") or 0.0),
             "end": float(plan_shots[last].get("end") or 0.0), "seconds": round(total_s, 3), "depth": depth,
             "denoise": DEPTHS[depth], "seed": seed, "frames": len(pictures), "size": list(size),
             "clips": {str(j): p for j, p in new_clips.items()}, "took_s": round(time.perf_counter() - started, 2),
             "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    rec.update({"clips": clips, "dreams": dreams_log + [entry]})
    rec_path.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    shutil.rmtree(run_dir / "frames", ignore_errors=True)  # the dreams live in the clips; the pngs were the way there
    if report:
        report("assemble", 0.55, "Re-cutting with the dream (no GPU)")
    return dense.recut_from_cache(job_dir, {}, report=report, cfg=cfg)
