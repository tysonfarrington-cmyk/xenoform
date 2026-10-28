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


def busiest_start(src: str | Path, clip_seconds: float, need_s: float, *, rate: float = 2.0) -> float:
    """Where the run has the most picture in it: the window of ``need_s`` whose frames carry the most detail (grey
    spread plus edges, on a 64x36 copy two frames a second), the middle winning a tie. The middle of a Nosferatu reel is
    tinted sky with the ship arriving at 12 s (28 Oct). Falls back to ``window_start`` when the clip will not read."""
    import numpy as np

    middle = window_start(clip_seconds, need_s)
    if float(clip_seconds) <= float(need_s) + 0.5:
        return middle
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-an", "-vf", f"fps={rate},scale=64:36,format=gray",
                              "-f", "rawvideo", "-"], check=True, capture_output=True).stdout
        g = np.frombuffer(raw, np.uint8).reshape(-1, 36, 64).astype(np.float32)
    except Exception:
        return middle
    if len(g) < 2:
        return middle
    detail = g.std(axis=(1, 2)) + np.abs(np.diff(g, axis=2)).mean(axis=(1, 2)) + np.abs(np.diff(g, axis=1)).mean(axis=(1, 2))
    span = max(1, int(round(float(need_s) * rate)))
    if len(detail) <= span:
        return middle
    sums = np.convolve(detail, np.ones(span), mode="valid")  # sums[k]: the window starting at frame k
    starts = np.arange(len(sums)) / rate
    best = sums.max()
    near = [s for s, v in zip(starts, sums) if v >= best * 0.97]  # within 3 % of the best, the one nearest the middle
    pick = min(near, key=lambda s: abs(s - middle))
    return round(float(min(max(0.0, pick), max(0.0, float(clip_seconds) - float(need_s)))), 3)


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


# Clip morphs (Tys, 28 Oct: "i want to see if you can morph clips ... as a transition type"): a clip's slot opens on a
# generated morph from the object the shot before landed on into the clip's first frame, and closes on one from its
# last frame into the object the next shot starts from, so footage grows out of the chain and dissolves back into it.
MORPH_S = 0.75        # each morph in and out of a clip
MORPH_SHARE = 1 / 3   # and never more than this of the slot, so the clip itself is seen


def morph_frames(frames: int, fps: float, *, into: bool = True, out_of: bool = True) -> tuple[int, int]:
    """Frames of the morph into and out of a clip slot of ``frames`` frames (0 where the slot opens or ends the cut)."""
    each = max(0, min(int(round(MORPH_S * float(fps))), int(int(frames) * MORPH_SHARE)))
    return (each if into else 0), (each if out_of else 0)


def first_last(clip: str | Path, dest_dir: str | Path, size: tuple[int, int]) -> tuple[Path, Path]:
    """The clip's first and last frames as PNGs at ``size`` (the morph render's size), for the morphs' far ends."""
    from PIL import Image

    from xenoform.video import read_all_frames

    frames = read_all_frames(clip)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for name, frame in (("first", frames[0]), ("last", frames[-1])):
        p = dest / f"{Path(clip).stem}_{name}.png"
        Image.fromarray(frame).convert("RGB").resize((int(size[0]), int(size[1])), Image.LANCZOS).save(p)
        out.append(p)
    return out[0], out[1]


def _fit(frames, count: int, size: tuple[int, int]) -> list:
    """``frames`` resampled in time to ``count`` and scaled to ``size``."""
    import numpy as np
    from PIL import Image

    if count <= 0 or not len(frames):
        return []
    idx = np.linspace(0, len(frames) - 1, count).round().astype(int)
    w, h = int(size[0]), int(size[1])
    return [np.asarray(Image.fromarray(frames[i]).resize((w, h), Image.LANCZOS)) for i in idx]


def splice(morph_in: str | Path | None, clip: str | Path, morph_out: str | Path | None, out: str | Path, *,
           n_in: int, n_out: int, size: tuple[int, int], fps: float = 24) -> Path:
    """One slot's file: the morph into the clip (``n_in`` frames, ending on its first frame), the clip, the morph out
    of it (``n_out`` frames, from its last frame). A morph that is missing leaves the clip's own frames there."""
    from xenoform.video import read_all_frames, write_mp4

    body = list(read_all_frames(clip))
    head = _fit(read_all_frames(morph_in), n_in, size) if morph_in and n_in else []
    tail = _fit(read_all_frames(morph_out), n_out, size) if morph_out and n_out else []
    write_mp4(out, head + body + tail, fps, crf=17)
    return Path(out)


__all__ = ["MIN_S", "MAX_S", "MIN_CLIP_S", "MAX_ITEMS", "MORPH_S", "scan", "clip_slots", "window_start", "size_for",
           "render_clip", "morph_frames", "first_last", "splice"]
