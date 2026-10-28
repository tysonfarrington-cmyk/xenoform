"""Cloud Final: the open-weights morph on Comfy Cloud, for a sharper cut than this GPU makes in good time, or for a
machine without the GPU (Tys, 29 Oct: "we have access to ltx 2.5 though ?? and a comfyui sub thing ?? surely there can
at least be an option for that if the competition is by comfyui").

Each shot is one first/last-frame morph run on Comfy Cloud by ``cloud_backend``, at most three at once (the Creator
plan's API concurrency), at 576x1024 from the portrait stills (1024x576 for 16:9), on Comfy's 96 GB GPUs. Two graphs:

* ``ltx25`` (the default): ``workflows/ltx25_morph_api.json``, the distilled 22B LTX-2.5, with ``LOOSE`` guides and the
  ``LEAD`` sentence on the prompt. With the graph's own guides (strength 1.0, img_compression 18) it held the first
  object for most of the clip and switched to the second near the end, a cut and not a morph, on Comfy Cloud and on
  this card alike (29 Oct, nautilus -> owl, 3 s). With the end guide at 0.6, img_compression 30 and a prompt that asks
  for the change across the whole clip, the shell folds open and the owl grows out of it, half and half mid-clip: the
  best morph of the four tried. A mid-clip guide (a 50/50 blend of the stills at frame 40) gave a double exposure.
* ``ltx23`` (``XENO_CLOUD_MODEL=ltx23``): the local Final's two-stage LTX-2.3 graph (``final_tier.graph``) without its
  upscaler; it turns one object into the other in mid-clip, more a quick change than a morph.

This machine then scales each clip to the cut's full size (Comfy Cloud keeps upscalers local) and composes the cut as
ever. It stays open weights: the same open models, only the hardware is Comfy's; ``cloud_backend.guard`` refuses a
partner or API node before anything is sent. It spends the account's Comfy Cloud credits, so a Make asks for it with
``cloud_final_ok`` (the desk's tick), nothing is sent without ``COMFY_ORG_API_KEY`` in the desk's environment, and a cut
takes at most ``MAX_MORPHS`` morphs. A shot that fails on Cloud falls back to its local Draft morph; the notes say which.
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
MODEL = os.environ.get("XENO_CLOUD_MODEL", "").strip().lower() or "ltx25"
MODELS = {"ltx23": "LTX-2.3", "ltx25": "LTX-2.5"}
# LTX-2.5 morphs only with room to move: the end guide at 0.6 (1.0 pins the last frame so hard the model holds the first
# object and cuts), the guide stills compressed to 30 (18 keeps them too exact), and the prompt opening on the change
LOOSE = {"img_compression": 30, "end_strength": 0.6}
LEAD = ("The first object slowly and continuously transforms into the second over the whole clip: by the middle of the "
        "clip it is half one and half the other, every part of it changing, one continuous transformation, never a cut. ")


def lead(a: str | None, b: str | None) -> str:
    """The lead sentence with the two objects named. Naming them is what drives the change: with "the first object" and
    "the second" (29 Oct, the same pair and guides) the shell only tumbled and switched to the owl at the end."""
    a, b = (str(a or "").strip(), str(b or "").strip())
    if not a or not b or a == b:
        return LEAD
    return (f"The {a} slowly and continuously transforms into the {b} over the whole clip: by the middle of the clip it is "
            f"half {a} and half {b}, every part of it changing, one continuous transformation, never a cut. ")
INPUT_NODES = {"ltx23": ("100", "101"), "ltx25": ("6", "7")}  # where each graph takes its two stills
RENDER_916 = (576, 1024)  # portrait 9:16; multiples of 64, so LTX-2.3's first stage (half size) still fits
RENDER_169 = (1024, 576)
FPS = 24
MAX_MORPHS = 16  # a 30 s cut is about twelve: the cap keeps a long song from spending a month of credits
# Wall time for one morph job on Comfy Cloud, upload to download: 58 s for the 3 s LTX-2.5 test clip (29 Oct); three run
# at once, and the scale to full size here comes on top
SECONDS_PER_MORPH = 60.0
MEASURED = True
NEGATIVE = "text, letters, watermark, logo, two objects, duplicated features, cut, flicker, blurry, low quality, cartoon, people, hands"
KEY_HINT = ("Cloud Final needs your Comfy Cloud API key as COMFY_ORG_API_KEY in the environment the desk starts in "
            "(set it yourself, never paste it into the desk), then restart the desk.")


def model() -> str:
    return MODEL if MODEL in MODELS else "ltx25"


def label() -> str:
    return MODELS[model()]


def ready() -> dict:
    """Whether a Cloud Final can be sent: the key in the environment and the graph on disk. Never reads the key out."""
    from xenoform.cloud_backend import KEY_ENV

    if model() == "ltx25" and not GRAPH.is_file():
        return {"ready": False, "why": f"{GRAPH.name} is missing."}
    if not os.environ.get(KEY_ENV, "").strip():
        return {"ready": False, "why": KEY_HINT}
    return {"ready": True, "why": ""}


def estimate(morphs: int, parallel: int = 3, scale_s: float = 3.0) -> dict:
    """Rough wall time for ``morphs`` Cloud morphs (``parallel`` at once) and their scale to full size here."""
    n = max(0, min(int(morphs), MAX_MORPHS))
    rounds = -(-n // max(1, parallel))
    secs = int(round(rounds * SECONDS_PER_MORPH + n * scale_s))
    return {"morphs": n, "seconds": secs, "jobs": n, "parallel": parallel, "measured": MEASURED, "model": label(),
            "basis": "Comfy Cloud, three morphs at once, then the scale to full size on this machine"}


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


def graph_for(name: str, prompt: str, *, length: int, seed: int, width: int, height: int, negative: str | None = None,
              img_compression: int = 18, end_strength: float = 1.0, prefix: str = "xenoform/cloud") -> dict:
    """The Cloud graph for ``name``: LTX-2.3's two-stage Final without its upscaler, or the LTX-2.5 morph graph."""
    if name == "ltx25":
        return graph(prompt, length=length, seed=seed, width=width, height=height, negative=negative,
                     img_compression=img_compression, end_strength=end_strength, prefix=prefix)
    from xenoform import final_tier

    return final_tier.graph(prompt, length=length, seed=seed, upscale=False, prefix=prefix, width=width, height=height,
                            out_w=width, out_h=height, img_compression=img_compression, end_strength=end_strength,
                            negative=negative)


def to_full_size(clips: list[Path], work: Path, out: tuple[int, int], cfg: dict, *, fallbacks: list[int] = (), client=None,
                 cancel: Callable[[], bool] | None = None, report: Callable[[str, float, str], None] | None = None,
                 fps: float = 24.0) -> tuple[list[Path], list[dict]]:
    """The clips at the cut's size. A Cloud clip is scaled here with Lanczos: a 576x1024 render is sharp, and a 4x model
    would make it 2304x4096, too big for this card and no better. A Draft fallback (320x576) goes through Fast Final's
    upscaler like any Draft."""
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
                state: dict | None = None, styles: list[str] | None = None, backend=None,
                name: str | None = None) -> tuple[list[Path], list[dict]]:
    """Render every shot's morph on Comfy Cloud. Returns the clips (at the render size; the caller scales them) and
    one note per shot that fell back to its Draft morph. ``name`` picks the graph (``model()`` when not given)."""
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
    name = name or model()
    a_node, b_node = INPUT_NODES[name]
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
        knobs = {**tune, **LOOSE} if name == "ltx25" else tune
        if name == "ltx25":
            text = lead(stills[i].get("noun"), stills[i + 1].get("noun")) + text
        g = graph_for(name, guard_prompt(text, state), negative=negative, length=length, seed=int(seed) + i, width=w,
                      height=h, prefix=f"xenoform/cloud{i:02d}", **knobs)
        return {"graph": g, "out_dir": work / "cloud" / f"{i:02d}",
                "inputs": {a_node: Path(stills[i]["path"]), b_node: Path(stills[i + 1]["path"])}}

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
                           f"Cloud Final: morph {done} of {len(jobs)} back from Comfy Cloud ({MODELS[name]}, open weights)")
    if cancel and cancel():
        raise JobCancelled("Cancelled. The morphs already running on Comfy Cloud finished; nothing new was sent.")
    if failed:
        if draft is None:
            raise RuntimeError("Cloud Final failed and no Draft fallback was given.")
        clips.update(draft(sorted(failed)))
    return [clips[i] for i in range(len(shots))], notes
