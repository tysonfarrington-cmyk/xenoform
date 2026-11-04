"""The cut: the rendered morphs laid on the beat with the song, written by ffmpeg into one mp4.

The simplest form of the desk's compose (``dense.run_simple``, ``cloud_morph.stitch``): each shot plays its morph in
its slot on the beat grid, first frame on still A and last on still B, so every handoff is continuous; the plan's speed,
ease and in-shot effects (stutter, hold, skip, reverse) and the shot's timing (Smooth, On the beat, Snap) re-time the
frames as the desk's ``shot_indices`` does; the plan's punches (a zoom and a flash) land on their hits, scaled by each
shot's intensity, when ``punch`` is on. No beat FX layer, no transitions, no look pass: those stay on the desk.

A shot with no morph rendered either ends the cut there (``fill="stop"``, the song trimmed to match) or plays a slow
crossfade of its two stills (``fill="stills"``), so the whole song plays with what has been rendered so far.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from . import looks
from . import plan as P
from . import song as S
from . import stills

FILLS = ("stop", "stills")
FPS = P.FPS


# ------------------------------------------------------------------------------------------------ the desk's re-timing


def shot_indices(shot: dict, n_src: int, progress: np.ndarray | None = None) -> np.ndarray:
    """Which source frame plays on each output frame (``cloud_morph.shot_indices``): speed, ease, timing, effects;
    the shot starts on frame 0 (still A) and ends on the last (still B) whatever happens between."""
    count = int(shot["frames"])
    last = max(n_src - 1, 0)
    if shot.get("hold"):
        return np.zeros(count, dtype=int)
    rest_n = int(round(float(shot.get("rest_s") or 0.0) * FPS)) if shot.get("rest_s") else 0
    rest_n = max(0, min(rest_n, count - 2))
    play = count - rest_n
    morph = shot if not rest_n else {**shot, "frames": play, "end": float(shot.get("start") or 0.0) + play / FPS}
    timed = None
    if shot.get("timing") and progress is not None and len(progress) == n_src:
        timed = looks.timing_indices(morph, play, progress, FPS)
    if timed is not None:
        idx = timed
    else:
        u = np.linspace(0.0, 1.0, play) if play > 1 else np.zeros(play)
        if shot.get("ease") == "in":
            u = u ** 1.6
        elif shot.get("ease") == "out":
            u = 1 - (1 - u) ** 1.6
        idx = u * last
    if rest_n:
        idx = np.concatenate([np.asarray(idx, dtype=np.float64), np.full(rest_n, float(last))])
    idx = np.asarray(idx, dtype=np.float64)
    step = last / max(count - 1, 1)
    for fx in shot.get("effects") or []:
        k0 = int(round((float(fx["t"]) - float(shot["start"])) * FPS))
        if not 0 <= k0 < count:
            continue
        kind = fx["type"]
        if kind == "hold":
            n = max(1, int(round(float(fx.get("len", 0.12)) * FPS)))
            idx[k0:min(count - 1, k0 + n)] = idx[k0]
        elif kind == "stutter":
            size, rep = max(1, int(fx.get("frames", 2))), max(2, int(fx.get("repeat", 3)))
            for k in range(k0, min(count - 1, k0 + size * rep)):
                idx[k] = idx[k0 + (k - k0) % size]
        elif kind == "skip":
            jump = float(fx.get("amount", 0.25)) * FPS
            tail = np.arange(count - k0)
            idx[k0:] = idx[k0:] + jump * (1 - tail / max(count - k0 - 1, 1))
        elif kind == "reverse":
            n = max(2, int(round(float(fx.get("len", 0.4)) * FPS)))
            n = min(n, count - 1 - k0)
            half = n // 2
            if half < 1:
                continue
            back = idx[k0] - np.arange(half) * step
            fwd = np.linspace(back[-1], idx[min(count - 1, k0 + n)], n - half + 1)[:-1]
            idx[k0:k0 + n] = np.concatenate([back, fwd])
    idx = np.clip(np.round(idx), 0, last).astype(int)
    if count:
        idx[0], idx[-1] = 0, last
    return idx


def punch_curve(shots: list[dict]) -> np.ndarray:
    """Per output frame, 0..1: the decaying punch of every ``punch`` effect (``cloud_morph.punch_curve``), each scaled
    by its shot's intensity (the desk scales the beat FX by it; here the punch is the one that is left)."""
    total = sum(int(s["frames"]) for s in shots)
    curve = np.zeros(total, np.float32)
    for s in shots:
        gain = float(s.get("fx_intensity", 0.8)) / 0.8  # 0.8 is the neutral knob's (Intensity 0.5: four fifths)
        for fx in s.get("effects") or []:
            if fx.get("type") != "punch":
                continue
            k0 = int(round(float(fx["t"]) * FPS))
            strength = min(1.0, float(fx.get("strength", 1.0)) * gain)
            for k in range(max(0, k0), min(total, k0 + 16)):
                curve[k] = max(curve[k], strength * np.exp(-(k - k0) / 3.5))
    return curve


def apply_punch(frame: np.ndarray, amount: float) -> np.ndarray:
    """A zoom punch and an exposure flash (``cloud_morph.apply_punch``)."""
    if amount <= 0.01:
        return frame
    h, w = frame.shape[:2]
    scale = 1.0 + 0.09 * amount
    ys = np.clip(((np.arange(h) - h / 2) / scale + h / 2).astype(int), 0, h - 1)
    xs = np.clip(((np.arange(w) - w / 2) / scale + w / 2).astype(int), 0, w - 1)
    out = frame[ys][:, xs].astype(np.float32)
    out = out * (1.0 + 0.45 * amount) + 18.0 * amount
    return np.clip(out, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------------------------------------ frames


def to_frames(clip) -> np.ndarray:
    """A morph as uint8 frames (n, height, width, 3): ComfyUI's IMAGE batch (float 0..1) or an array already."""
    if clip is None:
        return np.zeros((0, 1, 1, 3), np.uint8)
    data = clip.detach().cpu().numpy() if hasattr(clip, "detach") else np.asarray(clip)
    if data.ndim == 3:
        data = data[None, ...]
    if data.dtype != np.uint8:
        data = np.clip(np.asarray(data, dtype=np.float32) * 255.0 + 0.5, 0, 255).astype(np.uint8)
    if data.shape[-1] == 4:
        data = data[..., :3]
    return data


def _resize(frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    w, h = size
    if frame.shape[1] == w and frame.shape[0] == h:
        return frame
    from PIL import Image

    im = Image.fromarray(frame)
    scale = max(w / im.width, h / im.height)  # cover, centred: the morph fills the frame as the desk's lanczos scale does
    im = im.resize((max(w, round(im.width * scale)), max(h, round(im.height * scale))), Image.LANCZOS)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return np.asarray(im.crop((left, top, left + w, top + h)), dtype=np.uint8)


def crossfade(a: np.ndarray, b: np.ndarray, count: int) -> np.ndarray:
    """``count`` frames from still A to still B, eased: the sketch of a shot whose morph is not rendered yet."""
    u = np.linspace(0.0, 1.0, max(count, 1)) if count > 1 else np.zeros(1)
    u = (u * u * (3 - 2 * u))[:, None, None, None]
    return (a[None].astype(np.float32) * (1 - u) + b[None].astype(np.float32) * u).astype(np.uint8)


def ffmpeg_exe() -> str:
    exe = S.ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg was not found: put it on PATH (winget install Gyan.FFmpeg), or pip install imageio-ffmpeg.")
    return exe


def assemble(board: dict, clips: dict[int, object], out_path: str | Path, *, fill: str = "stop", punch: bool = True,
             song_path: str | Path | None = None, size: tuple[int, int] | None = None, crf: int = 20) -> dict:
    """Write the cut. ``clips`` maps a shot index to its rendered morph (frames). Returns what was written."""
    shots = board.get("shots") or []
    if not shots:
        raise ValueError("The storyboard has no shots to assemble.")
    fill = fill if fill in FILLS else "stop"
    size = tuple(size or board.get("out_size") or looks.OUT_SIZE.get(board.get("aspect", "16:9"), (768, 432)))
    played: list[dict] = []
    sources: list[tuple[str, np.ndarray]] = []
    for i, shot in enumerate(shots):
        frames = to_frames(clips.get(i)) if clips.get(i) is not None else None
        if frames is not None and len(frames):
            prog = looks.progress(frames) if shot.get("timing") else None
            idx = shot_indices(shot, len(frames), prog)
            sources.append(("morph", frames[idx]))
        elif fill == "stills":
            a = _resize(stills.load_rgb(board["stills"][i]["path"]), size)
            b = _resize(stills.load_rgb(board["stills"][i + 1]["path"]), size)
            hold = shot.get("hold")
            sources.append(("stills", np.repeat(a[None], int(shot["frames"]), axis=0) if hold else crossfade(a, b, int(shot["frames"]))))
        else:
            break
        played.append(shot)
    if not played:
        raise ValueError("No morph is rendered for the first shot: connect morph_1, or set fill to stills.")
    curve = punch_curve(played) if punch else np.zeros(sum(int(s["frames"]) for s in played), np.float32)
    seconds = sum(int(s["frames"]) for s in played) / float(FPS)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    song = Path(song_path or (board.get("song") or {}).get("path") or "")
    cmd = [ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-"]
    has_audio = song.is_file()
    if has_audio:
        cmd += ["-i", str(song), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k", "-t", f"{seconds:.4f}"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(int(crf)), "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    k = 0
    kinds = []
    try:
        for kind, frames in sources:
            kinds.append(kind)
            for frame in frames:
                frame = _resize(frame, size)
                if punch and curve[k] > 0.01:
                    frame = apply_punch(frame, float(curve[k]))
                proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
                k += 1
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
        code = proc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not write the cut (exit {code}): {err.strip()[-400:]}")
    return {"path": str(out_path), "frames": k, "seconds": round(seconds, 3), "shots": len(played), "of": len(shots),
            "morphs": kinds.count("morph"), "sketched": kinds.count("stills"), "size": [w, h], "audio": has_audio,
            "song_seconds": round(float((board.get("song") or {}).get("duration") or 0.0), 3)}
