"""Moves library: animate a character still with a real dance clip (Wan Animate 2, open weights, local).

Continuous motion comes from the driving clip itself, frame by frame, so there is no keyframe
pose-snapping. The 15 driving clips (Pexels/Mixkit) are listed in ``configs/moves.json`` and
fetched by ``scripts/fetch_moves.py`` into ``library/moves/``: their licences forbid shipping the
unaltered mp4s, so the repo ships only the manifest. Each clip carries a ``fit`` rating
(best / good / ok / avoid) from review: fluid, natural, full-body clips first; fast jumps,
breaking and props are marked ``avoid``.

12 GB budget: 480x832, 81 frames (3.4 s at 24 fps), int8 Wan Animate 2 + lightx2v 6-step LoRA.
Measured peak 11.6 GB on the RTX 3080 Ti.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs" / "moves.json"
TEMPLATE = ROOT / "workflows" / "moves_wan_animate2.json"
LIBRARY = ROOT / "library" / "moves"
W, H, FRAMES, FPS = 480, 832, 81, 24
FIT_ORDER = {"best": 0, "good": 1, "ok": 2, "avoid": 3}
# Tys's notes on Polly v1: keep the mouth closed (open-mouth laughing reads badly) and the hands clean.
DEFAULT_STYLE = "closed-mouth smile, calm expression, detailed hands, natural relaxed fingers"
DEFAULT_BACKGROUND = ("Background description: Plain light grey seamless photo studio background, soft even lighting, "
                      "no decorations, static camera, full body in frame.")
EXTRA_NEGATIVE = "open mouth, laughing, teeth, blurry hands, fused fingers, extra fingers, motion blur"
MOTION = {
    "dance-hiphop": "A woman doing a relaxed freestyle hip-hop groove with smooth continuous steps, bouncing knees and fluid arm gestures",
    "dance-freestyle": "A woman dancing a smooth freestyle groove with big, flowing arm moves",
    "dance-contemporary": "A dancer moving through fluid contemporary dance, continuous and graceful",
    "dance-playful": "A woman doing a playful bouncy dance, smooth and continuous",
    "dance-ballet": "A dancer doing graceful ballet turns and arm movements",
    "dance-street": "A dancer doing energetic street dance",
    "dance-breaking": "A dancer breakdancing",
    "pose-model": "A model shifting smoothly between relaxed fashion poses",
    "walk-to-camera": "A woman walking confidently towards the camera",
}


class MovesError(RuntimeError):
    pass


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def moves(include_avoid: bool = False) -> list[dict]:
    """Clips best-first. ``avoid`` clips (jerky jumps, inverted poses) are hidden unless asked for."""
    out = []
    for c in manifest()["clips"]:
        if c["fit"] == "avoid" and not include_avoid:
            continue
        out.append({**c, "local": (LIBRARY / f"{c['id']}.mp4").is_file()})
    return sorted(out, key=lambda c: (FIT_ORDER.get(c["fit"], 9), c["id"]))


def clip(move_id: str) -> dict:
    found = next((c for c in manifest()["clips"] if c["id"] == move_id), None)
    if found is None:
        raise MovesError(f"No move called {move_id}.")
    return found


def appearance_prompt(appearance: str, style: str = DEFAULT_STYLE) -> str:
    text = appearance.strip() or "A person"
    if not text.lower().startswith("character appearance"):
        text = "Character appearance description: " + text
    return f"{text.rstrip('.')}. {style}.\n{DEFAULT_BACKGROUND}"


def motion_prompt(move: dict) -> str:
    return MOTION.get(move.get("category", ""), "A person dancing smoothly") + ", background stationary"


def graph(appearance: str, move: dict, *, seed: int = 712, style: str = DEFAULT_STYLE, frames: int = FRAMES) -> dict:
    """API graph for one Wan Animate 2 render. Inputs: ``character.png`` (node 9) and ``drive.mp4`` (node 10)."""
    if (frames - 1) % 4:
        raise MovesError("Wan frame counts are 4k+1.")
    g = copy.deepcopy(json.loads(TEMPLATE.read_text(encoding="utf-8")))
    g["4"]["inputs"]["text"] = appearance_prompt(appearance, style)
    g["6"]["inputs"]["text"] = motion_prompt(move)
    g["5"]["inputs"]["text"] = g["5"]["inputs"]["text"].rstrip("，, ") + ", " + EXTRA_NEGATIVE
    g["15"]["inputs"].update(width=W, height=H, length=int(frames))
    g["19"]["inputs"]["noise_seed"] = int(seed)
    return g


def _ffmpeg() -> str:
    from xenoform.cloud_morph import _ffmpeg as find

    return find()


def prepare_drive(move_id: str, dest: Path, *, start: float = 0.0, frames: int = FRAMES) -> Path:
    """Cut the driving clip to ``frames`` at 24 fps, cover-scaled and centre-cropped to 480x832."""
    src = LIBRARY / f"{move_id}.mp4"
    if not src.is_file():
        raise MovesError(f"{move_id} is not downloaded yet. Run: python scripts/fetch_moves.py {move_id}")
    vf = f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{float(start):.3f}", "-i", str(src), "-vf", vf,
                    "-frames:v", str(frames), "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(dest)],
                   check=True)
    return Path(dest)


def prepare_character(image: Path, dest: Path) -> Path:
    """The character still, cover-scaled and centre-cropped to 480x832 (full body should already fill it)."""
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1"
    subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(image), "-vf", vf, "-frames:v", "1", str(dest)], check=True)
    return Path(dest)


def render(image: Path, move_id: str, appearance: str, work: Path, cfg: dict, *, seed: int = 712, start: float = 0.0,
           client=None, style: str = DEFAULT_STYLE) -> Path:
    """Render one move for one character on the local ComfyUI. Returns the mp4."""
    from xenoform.cloud_morph import _client, _job_result

    move = clip(move_id)
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    char = prepare_character(Path(image), work / "character.png")
    drive = prepare_drive(move_id, work / "drive.mp4", start=start)
    client = client or _client(cfg)
    wf = client.workflows.from_json(graph(appearance, move, seed=seed, style=style))
    wf.set_input("9", "image", client.assets.from_file(str(char)))
    wf.set_input("10", "file", client.assets.from_file(str(drive)))
    job = client.submit(wf)
    job.wait()
    result = _job_result(client, job)
    outs = list(result.get_outputs("31")) or list(result.outputs)
    if not outs:
        raise MovesError("The move render finished with no video.")
    dest = work / f"move_{move_id}_{seed}.mp4"
    next((o for o in outs if getattr(o, "type", None) == "video"), outs[0]).to_file(str(dest))
    return dest
