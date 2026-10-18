"""Shot review, song timing, the test-clip gate, and on-screen lettering.

Open weights only. Lyric alignment is optional and off. It never calls a
cloud model. Whisper, when a local transcript is supplied, runs early, so
words are moved later by an offset between 0.3s and 1.5s.
"""

from __future__ import annotations

import re
from typing import Any

from xenoform.notes import HASH_FIELDS

WHISPER_EARLY = (0.3, 1.5)
DEFAULT_LYRIC_OFFSET = 0.9
SHARE_BYTES = 16 * 1024 * 1024

_TEXT_FIELDS = {"action", "guide", "prompt"}
_ONSCREEN = (
    "on-screen text",
    "onscreen text",
    "on screen text",
    "subtitles",
    "subtitle",
    "captions",
    "caption",
    "lyrics",
    "lyric",
    "title card",
    "end card",
    "words on screen",
    "text overlay",
    "burned-in text",
    "burned in text",
)


def remake(takes: list[dict], *, scene: int, prompt: str, seed: int) -> tuple[dict, list[dict]]:
    """Same seed returns the take already kept. A new seed appends a take."""
    scene = int(scene)
    seed = int(seed)
    prompt = " ".join(str(prompt or "").split())
    kept = list(takes or [])
    for take in kept:
        if int(take.get("scene") or 0) == scene and int(take.get("seed") or 0) == seed:
            take["repeated"] = True
            return take, kept
    take = {
        "id": f"s{scene}-{seed}",
        "scene": scene,
        "seed": seed,
        "prompt": prompt,
        "picked": False,
        "repeated": False,
    }
    kept.append(take)
    return take, kept


def pick_take(takes: list[dict], *, scene: int, seed: int) -> list[dict]:
    scene = int(scene)
    seed = int(seed)
    for take in takes or []:
        if int(take.get("scene") or 0) == scene:
            take["picked"] = int(take.get("seed") or 0) == seed
    return takes


def text_only_shots(before: list[dict], after: list[dict]) -> list[int] | None:
    """Indices whose words changed. None when the shot grammar changed too."""
    if len(before) != len(after):
        return None
    shots: list[int] = []
    for old, new in zip(before, after):
        structural = False
        textual = False
        for key in HASH_FIELDS:
            if old.get(key) == new.get(key):
                continue
            if key in _TEXT_FIELDS:
                textual = True
            else:
                structural = True
        if (old.get("prompt") or "") != (new.get("prompt") or ""):
            textual = True
        if structural:
            return None
        if textual:
            shots.append(int(new.get("index") if new.get("index") is not None else old.get("index") or 0))
    return shots


def clip_gate(approved: list) -> dict[str, Any]:
    """A full batch needs one or two approved test clips."""
    ids = []
    for item in approved or []:
        text = str(item)
        if text and text not in ids:
            ids.append(text)
    count = len(ids)
    if count < 1 or count > 2:
        return {"ok": False, "count": count, "detail": "Approve 1 or 2 test clips before the full batch."}
    noun = "clip" if count == 1 else "clips"
    return {"ok": True, "count": count, "detail": f"{count} test {noun} approved."}


def clip_name(shot: str) -> str:
    name = str(shot or "wide").lower()
    if name in {"close", "macro"}:
        return "close"
    if name in {"medium", "tracking"}:
        return "medium"
    if name in {"reveal", "overhead"}:
        return "reveal"
    return "wide"


def strip_onscreen(prompt: str) -> str:
    """Prompts describe the picture. Titles and lyrics are drawn later, in code."""
    text = str(prompt or "")
    for phrase in _ONSCREEN:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def apply_lead(prompt: str, lead: str) -> str:
    """Insert the treatment's one lead sentence, once."""
    sentence = " ".join(str(lead or "").split())
    body = strip_onscreen(prompt)
    if not sentence:
        return body
    if sentence in body:
        return body
    return f"{sentence} {body}".strip()


def _clamp_offset(offset: float) -> float:
    low, high = WHISPER_EARLY
    return float(min(high, max(low, float(offset))))


def vocals_present(features: dict) -> bool:
    frames = features.get("frames") or []
    if not frames:
        return False
    hot = 0
    for frame in frames:
        level = float(frame.get("high") or 0) + float(frame.get("mid") or 0)
        if level > 0.35:
            hot += 1
    return hot / len(frames) > 0.15


def section_map(features: dict) -> list[dict[str, Any]]:
    rows = []
    for section in features.get("sections") or []:
        rows.append(
            {
                "label": str(section.get("label") or "sustain"),
                "start": round(float(section.get("start") or 0), 4),
                "end": round(float(section.get("end") or 0), 4),
            }
        )
    return rows


def shift_lyrics(words: list[dict], offset: float) -> list[dict[str, Any]]:
    """Move each word later. Whisper timestamps land 0.3–1.5s early."""
    shift = _clamp_offset(offset)
    shifted = []
    for word in words or []:
        start = float(word.get("start") or 0) + shift
        end = float(word.get("end") or start) + shift
        if end < start:
            end = start
        shifted.append({"word": str(word.get("word") or "").strip(), "start": round(start, 4), "end": round(end, 4)})
    return [row for row in shifted if row["word"]]


def song_timing(
    features: dict,
    words: list[dict] | None = None,
    *,
    enabled: bool = False,
    offset: float = DEFAULT_LYRIC_OFFSET,
) -> dict[str, Any]:
    """Beat grid, section map, and optional local lyric words.

    ``enabled`` is off unless the desk asks. No ASR process is started here.
    """
    beats = [round(float(beat), 4) for beat in (features.get("beats") or [])]
    lyrics_on = bool(enabled) and vocals_present(features)
    shifted = shift_lyrics(words or [], offset) if lyrics_on else []
    note = "Lyric align is off."
    if enabled and not vocals_present(features):
        note = "No vocals on this track, so the lyric line stays empty."
    elif lyrics_on and not shifted:
        note = "Local open weights only. Paste a transcript from this machine. Nothing is sent out."
    elif lyrics_on:
        note = f"Words moved later by {_clamp_offset(offset):.2f}s. Whisper runs early."
    return {
        "beats": beats,
        "sections": section_map(features),
        "duration": round(float(features.get("duration") or 0), 4),
        "lyrics": shifted,
        "offset": _clamp_offset(offset) if lyrics_on else float(offset),
        "enabled": lyrics_on,
        "asr": "off",
        "note": note,
    }


def lettering(frame, *, faces: list[dict] | None = None, band: bool = False) -> dict[str, Any]:
    """Text sits in the bottom band. It misses faces. Pale grounds get a dark band."""
    import numpy as np

    image = np.asarray(frame)
    height, width = image.shape[:2]
    text_top = 0.82 * height
    face_hit = False
    for box in faces if faces is not None else face_boxes(image):
        bottom = (float(box.get("y") or 0) + float(box.get("h") or 0)) * height
        top = float(box.get("y") or 0) * height
        if bottom > text_top and top < height:
            face_hit = True
    y0 = int(text_top)
    band_px = image[y0:] if y0 < height else image
    luma = float(band_px.astype(np.float64).mean()) / 255.0 if band_px.size else 0.0
    pale = luma >= 0.62
    band_ok = (not pale) or bool(band)
    return {
        "faces": not face_hit,
        "band": band_ok,
        "pale": pale,
        "pass": (not face_hit) and band_ok,
    }


def face_boxes(frame) -> list[dict[str, float]]:
    """A local skin-tone box. No network, no detector weights."""
    import numpy as np

    image = np.asarray(frame)
    if image.ndim != 3 or image.shape[2] < 3:
        return []
    red = image[..., 0].astype(np.int16)
    green = image[..., 1].astype(np.int16)
    blue = image[..., 2].astype(np.int16)
    skin = (red > 95) & (green > 40) & (blue > 20) & (red > green) & (red > blue) & (np.abs(red - green) > 15)
    if int(skin.sum()) < 12:
        return []
    ys, xs = np.where(skin)
    height, width = skin.shape
    return [
        {
            "x": float(xs.min()) / width,
            "y": float(ys.min()) / height,
            "w": float(xs.max() - xs.min() + 1) / width,
            "h": float(ys.max() - ys.min() + 1) / height,
        }
    ]


def paint_review_png(folder, *, seed: int, shot: str, prompt: str, index: int = 0):
    """One local keyframe. The seed repeats the same file. A new seed paints again."""
    import hashlib
    import subprocess
    from pathlib import Path

    import numpy as np

    from xenoform.render_cpu import form_from_frame, render_frame
    from xenoform.seeded import unit
    from xenoform.video import ffmpeg_bin

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{int(seed)}:{shot}:{prompt}:{int(index)}".encode("utf-8")).hexdigest()[:16]
    dest = folder / f"{digest}.png"
    if dest.exists() and dest.stat().st_size > 32:
        return dest
    sample = {
        "bass": 0.35 + 0.4 * unit(int(seed), int(index), salt=1),
        "sub": 0.2,
        "mid": 0.3,
        "high": 0.15,
        "onset_env": 0.1,
        "mutate": 0.25,
        "t": unit(int(seed), int(index), salt=3),
        "beat_env": 0.2,
        "shot": shot,
        "move": "hold",
    }
    form = form_from_frame(sample)
    rgb, _depth, _mask = render_frame(form, 96, 54, max_steps=3)
    raw = np.ascontiguousarray(rgb.astype(np.uint8)).tobytes()
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "96x54",
            "-i",
            "pipe:0",
            str(dest),
        ],
        input=raw,
        check=True,
    )
    return dest


def share_bitrate(duration: float, *, audio_kbps: int = 96) -> int:
    """Video bits per second that keep a 720p file under 16MB."""
    seconds = max(float(duration), 0.5)
    audio_bytes = int(audio_kbps * 1000 / 8 * seconds)
    overhead = 64 * 1024
    video_bytes = SHARE_BYTES - audio_bytes - overhead
    if video_bytes < 40_000:
        video_bytes = 40_000
    return max(80_000, int(video_bytes * 8 / seconds))


def share_command(src, dest, duration: float) -> list[str]:
    from xenoform.video import ffmpeg_bin

    bitrate = share_bitrate(duration)
    return [
        ffmpeg_bin(),
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        str(bitrate),
        "-maxrate",
        str(bitrate),
        "-bufsize",
        str(bitrate * 2),
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(dest),
    ]


def share_cut(src, dest, *, duration: float | None = None) -> dict[str, Any]:
    """720p H.264, under 16MB."""
    import subprocess
    from pathlib import Path

    from xenoform.video import probe_video

    source = Path(src)
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    info = probe_video(source)
    seconds = float(duration or 0) or (info["frames"] / float(info["fps"] or 24))
    subprocess.check_call(share_command(source, target, seconds))
    size = target.stat().st_size
    if size >= SHARE_BYTES:
        tighter = max(80_000, share_bitrate(seconds) // 2)
        subprocess.check_call(_with_bitrate(source, target, tighter))
        size = target.stat().st_size
    probed = probe_video(target)
    return {"path": str(target), "bytes": size, "width": probed["width"], "height": probed["height"], "under": size < SHARE_BYTES}


def _with_bitrate(src, dest, bitrate: int) -> list[str]:
    command = share_command(src, dest, 1.0)
    for flag in ("-b:v", "-maxrate"):
        index = command.index(flag)
        command[index + 1] = str(bitrate)
    buf = command.index("-bufsize")
    command[buf + 1] = str(bitrate * 2)
    return command
