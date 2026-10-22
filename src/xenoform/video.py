"""FFmpeg helpers for raw frames and mp4 muxing.

Requires the ``ffmpeg`` binary. The base renderer never links libav directly.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

log = logging.getLogger("xenoform")


def ffmpeg_bin() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("ffmpeg is not on PATH. Install ffmpeg and try again.")
    return binary


def ffprobe_bin() -> str:
    binary = shutil.which("ffprobe")
    if not binary:
        raise RuntimeError("ffprobe is not on PATH. It ships with ffmpeg.")
    return binary


def probe_video(path: str | Path) -> dict:
    cmd = [
        ffprobe_bin(),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,nb_frames,r_frame_rate,duration",
        "-of",
        "json",
        str(path),
    ]
    raw = subprocess.check_output(cmd, text=True)
    stream = json.loads(raw)["streams"][0]
    rate = stream.get("r_frame_rate", "0/1")
    num, den = rate.split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    nb = stream.get("nb_frames")
    frames = int(nb) if nb not in (None, "N/A") else 0
    if frames <= 0 and stream.get("duration") and fps:
        frames = int(round(float(stream["duration"]) * fps))
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": fps,
        "frames": frames,
    }


def write_mp4(
    path: str | Path,
    frames,
    fps: float,
    audio_path: str | Path | None = None,
    crf: int = 18,
) -> None:
    """Write an RGB uint8 frame iterable to an h264 mp4, optionally muxing audio."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    iterator = iter(frames)
    try:
        first = next(iterator)
    except StopIteration as exc:
        raise RuntimeError("No frames to encode") from exc
    first = np.asarray(first, dtype=np.uint8)
    height, width = first.shape[:2]
    cmd = [
        ffmpeg_bin(),
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
    ]
    if audio_path:
        cmd += ["-i", str(audio_path)]
    cmd += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        str(crf),
        "-preset",
        "veryfast",
        "-movflags",
        "+faststart",
    ]
    if audio_path:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]
    cmd.append(str(path))
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        proc.stdin.write(np.ascontiguousarray(first).tobytes())
        for frame in iterator:
            proc.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg exited {code} while writing {path}")


def read_frame_range(path: str | Path, start: int, count: int) -> np.ndarray:
    """Decode ``count`` frames starting at ``start`` (inclusive) as uint8 RGB."""
    if count <= 0:
        raise RuntimeError("count must be positive")
    info = probe_video(path)
    width, height = info["width"], info["height"]
    end = start + count - 1
    # Commas inside between() have to be escaped so ffmpeg does not split filters.
    select = f"select=between(n\\,{start}\\,{end}),setpts=N/FRAME_RATE/TB"
    cmd = [
        ffmpeg_bin(),
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        select,
        "-frames:v",
        str(count),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    raw = subprocess.check_output(cmd)
    frame_size = width * height * 3
    got = len(raw) // frame_size
    if got == 0:
        raise RuntimeError(f"ffmpeg returned no frames for {path} [{start}, {end}]")
    frames = np.frombuffer(raw[: got * frame_size], dtype=np.uint8).reshape(got, height, width, 3)
    return np.array(frames, copy=True)


def read_all_frames(path: str | Path) -> np.ndarray:
    info = probe_video(path)
    count = info["frames"]
    if count <= 0:
        # Decode until ffmpeg stops.
        cmd = [
            ffmpeg_bin(),
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
        raw = subprocess.check_output(cmd)
        frame_size = info["width"] * info["height"] * 3
        got = len(raw) // frame_size
        return np.frombuffer(raw[: got * frame_size], dtype=np.uint8).reshape(
            got, info["height"], info["width"], 3
        ).copy()
    return read_frame_range(path, 0, count)


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


# Candidate TTF/OTF files for ffmpeg drawtext, in order. The repo's bundled ui_static/fonts are woff2,
# which libfreetype in ffmpeg does not load, so they are deliberately not listed.
FONT_CANDIDATES: tuple[str, ...] = (
    # Windows
    "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Georgia.ttf", "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Georgia.ttf",
    # Linux (dejavu, liberation)
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
)


def find_font(prefer: tuple[str, ...] | list[str] | None = None) -> str | None:
    """First usable TrueType/OpenType font for ffmpeg drawtext / PIL: ``XENO_FONT`` (env) first, then
    ``prefer`` (extra candidates), then the platform list. Returns the path with forward slashes, or None."""
    import os

    cands: list[str] = []
    env = (os.environ.get("XENO_FONT") or "").strip()
    if env:
        cands.append(env)
    cands += [str(p) for p in (prefer or ())]
    cands += list(FONT_CANDIDATES)
    for cand in cands:
        if not cand or cand.lower().endswith(".woff2"):
            continue
        p = Path(cand)
        if p.is_file():
            return str(p).replace("\\", "/")
    return None


def drawtext_fontfile(path: str | Path) -> str:
    """Escape a font path for an ffmpeg drawtext ``fontfile=`` option: backslashes become ``/`` and the
    colon after a Windows drive letter is escaped as ``\\:`` so the filter parser does not split on it."""
    return str(path).replace("\\", "/").replace(":", "\\:")


def overlay_text(path: str | Path, cues: list[dict]) -> None:
    """Burn register cards onto the finished cut. Missing cues leave the file alone."""
    lines = [cue for cue in cues if str(cue.get("text") or "").strip()]
    if not lines:
        return
    font_path = find_font()
    if not font_path:
        log.warning("text cards skipped: no TrueType font found (set XENO_FONT to a .ttf)")
        return
    font = drawtext_fontfile(font_path)
    filters = []
    for cue in lines:
        text = _escape_drawtext(str(cue["text"])[:90])
        start = max(0.0, float(cue["start"]))
        end = max(start + 0.2, float(cue["end"]))
        window = f"enable='between(t,{start:.3f},{end:.3f})'"
        filters.append(
            "drawbox="
            "x=0:y=ih*0.74:w=iw:h=ih*0.26:"
            "color=0x12100E@0.72:t=fill:"
            f"{window}"
        )
        filters.append(
            "drawtext="
            f"fontfile='{font}':"
            f"text='{text}':"
            "fontsize=28:"
            "fontcolor=0xF3EADC:"
            "x=(w-text_w)/2:"
            "y=h*0.82:"
            f"{window}"
        )
    src = Path(path)
    tmp = src.with_suffix(".cards.mp4")
    try:
        subprocess.check_call(
            [
                ffmpeg_bin(),
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(src),
                "-vf",
                ",".join(filters),
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                str(tmp),
            ]
        )
        tmp.replace(src)
    except Exception:
        log.exception("text cards were not burned")
        tmp.unlink(missing_ok=True)
