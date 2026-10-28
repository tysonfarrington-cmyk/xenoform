"""Cloud Final: the open-weights LTX-2.5 morph on Comfy Cloud, for a sharper cut than this GPU makes in good time, or
for a machine without the GPU (Tys, 29 Oct: "we have access to ltx 2.5 though ?? and a comfyui sub thing ?? surely
there can at least be an option for that if the competition is by comfyui").

Each shot is one first/last-frame morph through ``workflows/ltx25_morph_api.json`` (the distilled 22B LTX-2.5
transformer, 8 steps, open weights under the LTX-2.x Community License), run on Comfy Cloud by ``cloud_backend``, at
most three at once, at 576x1024 from the portrait stills (1024x576 for 16:9). This machine then upscales each clip to
the cut's full size (``upscale_pass``: Comfy Cloud keeps upscalers local), and the cut is composed here as ever.

It stays open weights: the same open models, only the hardware is Comfy's; ``cloud_backend.guard`` refuses a partner
or API node before anything is sent. It spends the account's Comfy Cloud credits, so a Make asks for it with
``cloud_final_ok`` (the desk's tick), nothing is sent without ``COMFY_ORG_API_KEY`` in the desk's environment, and a cut takes at most
``MAX_MORPHS`` morphs. A shot that fails on Cloud falls back to its local Draft morph; the notes say which.
"""

from __future__ import annotations

import json
import os
import shutil
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "workflows" / "ltx25_morph_api.json"
RENDER_916 = (576, 1024)  # portrait 9:16; LTX wants multiples of 32
RENDER_169 = (1024, 576)
FPS = 24
MAX_MORPHS = 16  # a 30 s cut is about twelve: the cap keeps a long song from spending a month of credits
# Wall time for one morph job on Comfy Cloud, upload to download, before it is measured on the account (the one-clip
# test sets it); three run at once, and each clip's local upscale (upscale_pass) comes on top
SECONDS_PER_MORPH = 75.0
MEASURED = False
NEGATIVE = "text, letters, watermark, logo, two objects, duplicated features, cut, flicker, blurry, low quality, cartoon, people, hands"
KEY_HINT = ("Cloud Final needs your Comfy Cloud API key as COMFY_ORG_API_KEY in the environment the desk starts in "
            "(set it yourself, never paste it into the desk), then restart the desk.")


def ready() -> dict:
    """Whether a Cloud Final can be sent: the key in the environment and the graph on disk. Never reads the key out."""
    from xenoform.cloud_backend import KEY_ENV

    if not GRAPH.is_file():
        return {"ready": False, "why": f"{GRAPH.name} is missing."}
    if not os.environ.get(KEY_ENV, "").strip():
        return {"ready": False, "why": KEY_HINT}
    return {"ready": True, "why": ""}


def estimate(morphs: int, parallel: int = 3, upscale_s: float = 20.0) -> dict:
    """Rough wall time for ``morphs`` Cloud morphs (``parallel`` at once) and their local upscale."""
    n = max(0, min(int(morphs), MAX_MORPHS))
    rounds = -(-n // max(1, parallel))
    secs = int(round(rounds * SECONDS_PER_MORPH + n * upscale_s))
    return {"morphs": n, "seconds": secs, "jobs": n, "parallel": parallel, "measured": MEASURED,
            "basis": "Comfy Cloud, three morphs at once, then the upscale on this machine"}


def graph(prompt: str, *, length: int, seed: int, width: int, height: int, negative: str | None = None,
          img_compression: int = 18, end_strength: float = 1.0, prefix: str = "xenoform/cloud") -> dict:
    """The LTX-2.5 first/last-frame morph graph with this shot's prompt, size, length and seed. Images go in 6 and 7."""
    if width % 32 or height % 32:
        raise ValueError(f"LTX-2.5 needs multiples of 32; got {width}x{height}.")
    if (length - 1) % 8:
        raise ValueError(f"LTX frame counts are 8k+1; got {length}.")
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    g["3"]["inputs"]["text"] = prompt
    g["4"]["inputs"]["text"] = negative or NEGATIVE
    g["8"]["inputs"]["img_compression"] = int(img_compression)
    g["21"]["inputs"]["img_compression"] = int(img_compression)
    g["9"]["inputs"].update({"width": int(width), "height": int(height), "length": int(length)})
    g["25"]["inputs"]["frames_number"] = int(length)
    g["22"]["inputs"]["strength"] = float(end_strength)
    g["13"]["inputs"]["noise_seed"] = int(seed)
    g["18"]["inputs"]["fps"] = float(FPS)
    g["19"]["inputs"]["filename_prefix"] = prefix
    return g


def to_full_size(clips: list[Path], work: Path, out: tuple[int, int], cfg: dict, *, fallbacks: list[int] = (), client=None,
                 cancel: Callable[[], bool] | None = None, report: Callable[[str, float, str], None] | None = None,
                 fps: float = 24.0) -> tuple[list[Path], list[dict]]:
    """The clips at the cut's size. A Cloud clip is scaled here with Lanczos: a 576x1024 LTX-2.5 render is sharp, and a
    4x model would make it 2304x4096, too big for this card and no better. A Draft fallback (320x576) goes through Fast
    Final's upscaler like any Draft."""
    import subprocess

    from xenoform import upscale_pass
    from xenoform.cloud_morph import _ffmpeg

    work = Path(work)
    done = list(clips)
    notes: list[dict] = []
    low = [i for i in fallbacks if 0 <= i < len(clips)]
    if low:
        ups, notes = upscale_pass.upscale_clips([clips[i] for i in low], work, out, cfg, client=client, cancel=cancel,
                                                report=report, fps=fps)
        for i, clip in zip(low, ups):
            done[i] = Path(clip)
    for i, clip in enumerate(clips):
        if i in low:
            continue
        dest = work / f"cloud_full{i:02d}.mp4"
        subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(clip), "-vf", f"scale={out[0]}:{out[1]}:flags=lanczos,setsar=1",
                        "-an", "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", str(dest)], check=True)
        done[i] = dest
    return done, notes


def cloud_clips(shots: list[dict], stills: list[dict], work: Path, cfg: dict, seed: int, vibe: str, *,
                cancel: Callable[[], bool] | None = None, report: Callable[[str, float, str], None] | None = None,
                draft: Callable[[list[int]], dict[int, Path]] | None = None, vertical: bool = True,
                state: dict | None = None, styles: list[str] | None = None, backend=None) -> tuple[list[Path], list[dict]]:
    """Render every shot's morph on Comfy Cloud. Returns the clips (at the render size; the caller upscales them) and
    one note per shot that fell back to its Draft morph."""
    from xenoform import cloud_backend as cb
    from xenoform import final_tier
    from xenoform import morph_pass as mp
    from xenoform.guardrails import guard_prompt, negative_for
    from xenoform.turbo import JobCancelled

    gate = ready()
    if not gate["ready"]:
        raise cb.CloudRefused(gate["why"])
    if len(shots) > MAX_MORPHS:
        raise cb.CloudRefused(f"Cloud Final takes at most {MAX_MORPHS} morphs; this cut has {len(shots)}. "
                              "A shorter Length keeps it under.")
    backend = backend or cb.CloudBackend.from_config(cfg)
    work = Path(work)
    w, h = RENDER_916 if vertical else RENDER_169
    if vertical:
        from xenoform.portrait import PROMPT_SUFFIX, portrait_stills

        stills = portrait_stills(stills, work, w, h, background=(state or {}).get("still_background"))
    else:
        PROMPT_SUFFIX = ""
    tune = final_tier.tuned(vibe)
    negative = negative_for(NEGATIVE, state)

    def job(i: int) -> dict:
        style = styles[i] if styles and i < len(styles) else "melt"
        text = mp.prompt_for(vibe, "ltx25", mp.pair_kinds(stills[i], stills[i + 1]), style=style).rstrip() + PROMPT_SUFFIX
        length = final_tier.gen_length(float(shots[i].get("render_s") or shots[i]["seconds"]))
        g = graph(guard_prompt(text, state), negative=negative, length=length, seed=int(seed) + i, width=w, height=h,
                  prefix=f"xenoform/cloud{i:02d}", **tune)
        return {"graph": g, "out_dir": work / "cloud" / f"{i:02d}",
                "inputs": {"6": Path(stills[i]["path"]), "7": Path(stills[i + 1]["path"])}}

    jobs = [job(i) for i in range(len(shots))]
    for j in jobs:  # the whole batch is refused up front, before any upload, if one graph has a partner node
        backend.prepare(j["graph"])
    clips: dict[int, Path] = {}
    notes: list[dict] = []
    failed: list[int] = []
    pending = list(range(len(jobs)))
    done = 0
    with ThreadPoolExecutor(max_workers=backend.max_parallel) as pool:
        running = {}
        while pending or running:
            while pending and len(running) < backend.max_parallel and not (cancel and cancel()):
                i = pending.pop(0)
                j = jobs[i]
                running[pool.submit(backend.run, j["graph"], j["out_dir"], inputs=j["inputs"])] = i
            if not running:
                break  # cancelled with nothing left in flight
            finished, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for fut in finished:
                i = running.pop(fut)
                done += 1
                try:
                    videos = [p for p in fut.result() if p.suffix.lower() in {".mp4", ".webm", ".mov"}]
                    if not videos:
                        raise cb.CloudJobFailed("finished with no video")
                    dest = work / f"cloud{i:02d}.mp4"
                    shutil.move(str(videos[0]), dest)
                    clips[i] = dest
                except Exception as exc:  # noqa: BLE001 - a failed shot falls back to its Draft morph
                    failed.append(i)
                    notes.append({"shot": i, "fallback": "ltx095-draft", "why": str(exc)[:200]})
                if report:
                    report("restyle", 0.12 + 0.7 * done / max(len(jobs), 1),
                           f"Cloud Final: morph {done} of {len(jobs)} back from Comfy Cloud (LTX-2.5, open weights)")
    if cancel and cancel():
        raise JobCancelled("Cancelled. The morphs already running on Comfy Cloud finished; nothing new was sent.")
    if failed:
        if draft is None:
            raise RuntimeError("Cloud Final failed and no Draft fallback was given.")
        clips.update(draft(sorted(failed)))
    return [clips[i] for i in range(len(shots))], notes
