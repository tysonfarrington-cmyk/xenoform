"""Your own clips and images in the Simple cut.

Point the desk at a folder (or drop files on it): the images lead the vibe's morph chain as morph
targets (``morph_pass.user_targets`` reads ``state["morph_targets"]``), and the clips are cut into the
story plan the way performer shots are. Each clip takes one run of consecutive shots at the start of a
passage (at least ``MIN_S`` seconds of it, never adjacent to a performer slot or another clip), is trimmed
to exactly that run's frames around its middle, cover-cropped to the cut's aspect and played 1:1, so the
cut in and the cut out land on the beat grid and the beat FX, the look and the transitions treat it like
any other shot (``dense.apply_performer_slots`` does the merge, marking the shot ``own``).

- ``scan(folder)``: the images and the clips (with their seconds) in a folder, sorted by name, capped.
- ``clip_slots(shots, clips, avoid)``: one slot per clip, in time order.
- ``window_start(clip_seconds, need_s)``: where in the clip the run is taken from (its middle).
- ``render_clip(src, start_s, frames, size, out)``: the trimmed, reframed, exact-length clip.
- ``size_for(aspect)``: the frame size the clip is rendered at (compose reframes it with the rest).
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from xenoform import footage

log = logging.getLogger("xenoform.own_media")

MIN_S = 2.0        # a clip's run is at least two seconds, so the clip is seen
MAX_S = 8.0        # and at most eight, so the morphs keep the cut moving
MIN_CLIP_S = 2.0   # clips shorter than this are skipped
MAX_ITEMS = 12     # images and clips each (twelve morph targets is the pool size)


def scan(folder: str | Path) -> dict:
    """The images and clips in ``folder`` (not recursive, sorted by name), each list capped at ``MAX_ITEMS``.

    ``{"folder", "images": [paths], "clips": [{"path", "seconds"}]}``; a clip shorter than ``MIN_CLIP_S``
    or one ffprobe cannot read is left out.
    """
    folder = Path(str(folder)).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(f"{folder} is not a folder")
    items = footage.scan_folder(folder)
    images = [str(i["path"]) for i in items if i["kind"] == "image"][:MAX_ITEMS]
    clips: list[dict] = []
    for item in items:
        if item["kind"] != "video" or len(clips) >= MAX_ITEMS:
            continue
        try:
            seconds = float(footage.probe_duration(str(item["path"])))
        except Exception as exc:  # unreadable: not a clip for the cut
            log.warning("own clip %s unreadable: %s", item["path"], exc)
            continue
        if seconds >= MIN_CLIP_S:
            clips.append({"path": str(item["path"]), "seconds": round(seconds, 3)})
    return {"folder": str(folder), "images": images, "clips": clips}


def clip_slots(shots: list[dict], clips: list[dict], avoid=(), *, min_s: float = MIN_S, max_s: float = MAX_S) -> list[dict]:
    """Where each clip goes: one run of consecutive shots per clip, in time order.

    A run starts a passage (a boundary or a section change, the first shot included), takes whole shots
    while it stays within the clip's length and ``max_s``, must reach ``min_s`` (so a clip shorter than
    the passage's shots does not fit there), and never touches a run in ``avoid`` (``(first, last)`` pairs
    or dicts with those keys, the performer slots) or another clip's run. Each passage takes the first
    unused clip, in folder order, that fits it; a passage no clip fits is left to the morphs, and clips
    left over when the passages run out are not used.
    """
    if not shots or not clips:
        return []
    taken: list[tuple[int, int]] = []
    for a in avoid or ():
        if isinstance(a, dict):
            taken.append((int(a["first"]), int(a["last"])))
        else:
            taken.append((int(a[0]), int(a[1])))
    starts = [i for i, s in enumerate(shots)
              if i == 0 or s.get("boundary") or (s.get("section") != shots[i - 1].get("section"))]
    out: list[dict] = []
    unused = [c for c in clips if float(c.get("seconds") or 0.0) >= min_s]
    for i in starts:
        if not unused:
            break
        if any(not (i < a - 1 or i > b + 1) for a, b in taken):
            continue  # the passage opens on, or right beside, a performer slot or another clip
        section = shots[i].get("section")
        for clip in unused:
            limit = min(float(max_s), float(clip.get("seconds") or 0.0))
            j, total = i, 0.0
            while j < len(shots) and shots[j].get("section", section) == section:
                s = float(shots[j].get("seconds") or (float(shots[j]["end"]) - float(shots[j]["start"])))
                if total + s > limit + 1e-6:
                    break
                total += s
                j += 1
            if total < min_s:
                continue  # this clip is shorter than the passage's shots: try the next clip here
            if any(not (j - 1 < a - 1 or i > b + 1) for a, b in taken):
                break  # the run would touch a taken run: leave the passage to the morphs
            out.append({"first": i, "last": j - 1, "seconds": round(total, 4), "section": section,
                        "start": float(shots[i]["start"]), "clip": str(clip["path"]),
                        "clip_seconds": float(clip.get("seconds") or 0.0)})
            taken.append((i, j - 1))
            unused.remove(clip)
            break
    return out


def window_start(clip_seconds: float, need_s: float) -> float:
    """The run is taken from the middle of the clip (the opening and the tail of a home clip are the shaky bits)."""
    return round(max(0.0, (float(clip_seconds) - float(need_s)) / 2.0), 3)


def size_for(aspect: str) -> tuple[int, int]:
    """The frame size an own clip is rendered at: the Draft compose size of that aspect (Final upscales with the rest)."""
    return {"9:16": (540, 960), "1:1": (720, 720)}.get(str(aspect or "16:9"), (960, 540))


def render_clip(src: str | Path, start_s: float, frames: int, size: tuple[int, int], out: str | Path, *, fps: float = 24) -> Path:
    """``frames`` frames of ``src`` from ``start_s``, cover-cropped to ``size`` at ``fps``, silent (the song is the
    audio), libx264; the last frame is cloned when the clip runs out, so the count is always exact."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = int(size[0]), int(size[1])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, float(start_s)):.3f}", "-i", str(src), "-an",
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},"
                           f"tpad=stop_mode=clone:stop_duration={max(1.0, int(frames) / float(fps)):.3f}",
                    "-frames:v", str(int(frames)), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True, capture_output=True)
    return out


__all__ = ["MIN_S", "MAX_S", "MIN_CLIP_S", "MAX_ITEMS", "scan", "clip_slots", "window_start", "size_for", "render_clip"]
