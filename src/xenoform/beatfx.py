"""Beat-reactive finishing for Simple mode: reframe, beat FX, overlay, end card, 15 s hook.

Everything here is free CPU post-processing (numpy + ffmpeg), so it runs the same on
the open-weights path and on any other source of clips. Ported from the demo1 dense
cut script that made the Facebook demo:

* kick pulse      the frame scales up a few percent on each kick
* edge flash      transients light the edges, alternating teal and violet each beat
* bloom           big punches from the cut plan add a soft glow
* loudness lift   overall exposure follows the song's RMS

Aspect: 16:9 is the render (Final 9:16 can also render natively in portrait, see
final_tier; then ``size`` is the portrait output and the crop below is a no-op).
9:16 and 1:1 crop each shot around the morph's centre
(the brightness-weighted centre of mass, which is the object on the black or plain
backgrounds the vibes use), eased between the shot's first and last frame so the
crop follows the object as it transforms.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

FPS = 24
ASPECTS = ("16:9", "9:16", "1:1")
TEAL = np.array([90, 225, 215], np.float32)
VIOLET = np.array([190, 110, 255], np.float32)


def repo_url() -> str:
    """The end card's repo line: ``XENO_REPO_URL`` once the public repo exists, else the pyproject URL."""
    env = os.environ.get("XENO_REPO_URL", "").strip()
    if env:
        return env.replace("https://", "")
    return "github.com/PLACEHOLDER/xenoform"



def out_size(aspect: str, quality: str = "draft") -> tuple[int, int]:
    """Output frame size for an aspect. Even numbers only (yuv420p)."""
    long = 1280 if quality == "final" else 768
    short = 720 if quality == "final" else 432
    if aspect == "9:16":
        return short, long
    if aspect == "1:1":
        return short, short
    return long, short


def norm_aspect(value) -> str:
    text = str(value or "16:9").strip().replace("x", ":").replace("/", ":")
    return {"vertical": "9:16", "square": "1:1", "wide": "16:9"}.get(text, text if text in ASPECTS else "16:9")


# ------------------------------------------------------------------ envelopes


def load_audio(path: Path, sr: int = 22050, offset: float = 0.0, duration: float | None = None) -> np.ndarray:
    """Mono float32 samples from any file ffmpeg reads (wav, mp3, or the audio track of an mp4)."""
    cmd = [_ffmpeg(), "-v", "error"]
    if offset:
        cmd += ["-ss", f"{offset:.3f}"]
    cmd += ["-i", str(path)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def envelopes(audio_path: Path | None, frames: int, start: float = 0.0) -> dict[str, np.ndarray]:
    """kick, transient and loudness, one value per output frame, 0..1."""
    zero = np.zeros(frames, np.float32)
    if audio_path is None or not Path(audio_path).is_file() or frames <= 0:
        return {"kick": zero, "trans": zero, "loud": zero + 0.6}
    import librosa

    sr = 22050
    y = load_audio(Path(audio_path), sr, float(start), frames / FPS + 0.5)
    if len(y) < 4096:
        return {"kick": zero, "trans": zero, "loud": zero + 0.6}
    hop = 512
    spec = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    t_spec = librosa.frames_to_time(np.arange(spec.shape[1]), sr=sr, hop_length=hop)
    tf = np.arange(frames) / FPS

    def flux(band) -> np.ndarray:
        d = np.maximum(0, np.diff(np.log1p(spec[band] * 50), axis=1)).sum(0)
        d = np.concatenate([[0.0], d])
        return d / (np.percentile(d, 99.5) + 1e-9)

    def env(x: np.ndarray, decay_s: float) -> np.ndarray:
        x = np.clip(np.interp(tf, t_spec, x), 0, 1.5)
        out = np.zeros_like(x)
        k = math.exp(-1 / (decay_s * FPS))
        for i, v in enumerate(x):
            out[i] = max(v, (out[i - 1] if i else 0.0) * k)
        return out

    kick = np.clip((env(flux(freqs < 150), 0.12) - 0.25) / 0.75, 0, 1)
    trans = np.clip((env(flux(freqs >= 2500), 0.08) - 0.3) / 0.7, 0, 1)
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    loud = np.interp(tf, t_spec, (rms / (rms.max() + 1e-9)) ** 0.7)
    return {"kick": kick.astype(np.float32), "trans": trans.astype(np.float32), "loud": loud.astype(np.float32)}


# ------------------------------------------------------------------ reframing


def centroid(frame: np.ndarray) -> tuple[float, float]:
    """Brightness-weighted centre of the subject, as fractions of width and height."""
    g = frame.astype(np.float32).mean(axis=2)
    small = g[::4, ::4]
    base = np.percentile(small, 40)
    w = np.clip(small - base, 0, None) ** 1.5
    total = float(w.sum())
    if total <= 1e-6:
        return 0.5, 0.5
    ys, xs = np.indices(w.shape)
    return float((w * xs).sum() / total / max(w.shape[1] - 1, 1)), float((w * ys).sum() / total / max(w.shape[0] - 1, 1))


def crop_box(src_w: int, src_h: int, aspect: str, cx: float, cy: float) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the largest window of ``aspect`` centred as near (cx, cy) as fits."""
    a = norm_aspect(aspect)
    ratio = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}[a]
    if src_w / src_h > ratio:
        h = src_h
        w = int(round(h * ratio))
    else:
        w = src_w
        h = int(round(w / ratio))
    x = int(round(cx * src_w - w / 2))
    y = int(round(cy * src_h - h / 2))
    return max(0, min(src_w - w, x)), max(0, min(src_h - h, y)), w, h


def shot_centres(frames: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]]:
    """Subject centre at the start and end of a clip (averaged over a few frames each)."""
    n = len(frames)
    if n == 0:
        return (0.5, 0.5), (0.5, 0.5)
    k = max(1, n // 6)
    head = np.mean([centroid(f) for f in frames[:k:max(1, k // 3)]], axis=0)
    tail = np.mean([centroid(f) for f in frames[-k::max(1, k // 3)]], axis=0)
    return (float(head[0]), float(head[1])), (float(tail[0]), float(tail[1]))


def resize(frame: np.ndarray, w: int, h: int) -> np.ndarray:
    """Bilinear resize, numpy only."""
    sh, sw = frame.shape[:2]
    if (sw, sh) == (w, h):
        return frame
    ys = (np.arange(h) + 0.5) * sh / h - 0.5
    xs = (np.arange(w) + 0.5) * sw / w - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, sh - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, sw - 1)
    y1 = np.clip(y0 + 1, 0, sh - 1)
    x1 = np.clip(x0 + 1, 0, sw - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None, None]
    fx = np.clip(xs - x0, 0, 1)[None, :, None]
    f = frame.astype(np.float32)
    top = f[y0][:, x0] * (1 - fx) + f[y0][:, x1] * fx
    bot = f[y1][:, x0] * (1 - fx) + f[y1][:, x1] * fx
    return np.clip(top * (1 - fy) + bot * fy, 0, 255).astype(np.uint8)


def reframe(frame: np.ndarray, aspect: str, centre: tuple[float, float], w: int, h: int) -> np.ndarray:
    x, y, cw, ch = crop_box(frame.shape[1], frame.shape[0], aspect, centre[0], centre[1])
    return resize(frame[y:y + ch, x:x + cw], w, h)


# ------------------------------------------------------------------ beat FX


def _blur(img: np.ndarray, factor: int = 8) -> np.ndarray:
    h, w = img.shape[:2]
    sh, sw = max(1, h // factor), max(1, w // factor)
    small = img[: sh * factor, : sw * factor].reshape(sh, factor, sw, factor, -1).mean(axis=(1, 3))
    return resize(np.clip(small, 0, 255).astype(np.uint8), w, h).astype(np.float32)


def _edges(img: np.ndarray) -> np.ndarray:
    g = img.mean(axis=2)
    gx = np.zeros_like(g)
    gy = np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1] = g[2:] - g[:-2]
    return np.clip(np.hypot(gx, gy) / 90.0, 0, 1)[..., None]


def _zoom(img: np.ndarray, scale: float) -> np.ndarray:
    if scale <= 1.001:
        return img
    h, w = img.shape[:2]
    cw, ch = int(round(w / scale)), int(round(h / scale))
    x, y = (w - cw) // 2, (h - ch) // 2
    return resize(img[y:y + ch, x:x + cw].astype(np.uint8), w, h).astype(np.float32)


def beat_fx(frame: np.ndarray, *, kick: float, trans: float, punch: float, loud: float, beat_index: int,
            zoom_scale: float = 1.0) -> np.ndarray:
    """The demo1 look on one frame. ``zoom_scale`` < 1 softens the zoom (vertical uses 0.5)."""
    img = frame.astype(np.float32)
    s = 1.0 + (0.035 * kick + 0.09 * punch) * zoom_scale
    img = _zoom(img, s)
    e = trans * 0.9 + punch * 0.8
    if e > 0.02:
        col = TEAL if beat_index % 2 else VIOLET
        img = img + _edges(img) * col * e
    if punch > 0.05:
        img = img + _blur(img) * (0.55 * punch)
    img = img * (0.92 + 0.12 * loud)
    return np.clip(img, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ compositor


def _ffmpeg() -> str:
    from xenoform.cloud_morph import _ffmpeg as find

    return find()


def read_frames(path: Path) -> np.ndarray:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        w, h = (int(v) for v in probe.stdout.strip().split(",")[:2])
    except ValueError:
        w, h = 768, 432
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


def compose(clips: list[Path], shots: list[dict], audio_path: Path, out_path: Path, *, aspect: str = "16:9",
            quality: str = "draft", fx: bool = True, overlay: bool = False, beats: Iterable[float] = (),
            label: str | None = None, report: Callable[[str, float, str], None] | None = None,
            size: tuple[int, int] | None = None) -> dict:
    """Retime every clip to its shot (speed, ease, hold, stutter, skip, reverse), reframe, add beat FX, mux.

    ``size`` overrides the output frame size (native vertical Final: 1080x1920). Clips that
    already have the target aspect pass through whole; any other clip is cropped around its object.
    """
    from xenoform.cloud_morph import BeatOverlay, audio_envelope, punch_curve, shot_indices

    aspect = norm_aspect(aspect)
    w, h = size or out_size(aspect, quality)
    total = sum(int(s["frames"]) for s in shots)
    beats = [float(b) for b in beats]
    env = envelopes(audio_path, total) if fx else None
    punch = punch_curve(shots)
    over = None
    if overlay:
        marks = [s["start"] for s in shots[1:]]
        over = BeatOverlay(w, h, total / FPS, audio_envelope(audio_path, 0.0, total / FPS, 512), beats, marks)
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".compose.mp4")
    cmd = [_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS),
           "-i", "-", "-i", str(audio_path), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
           "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart"]
    if label:
        cmd += ["-metadata", f"comment={label}"]
    cmd.append(str(tmp))
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    zoom_scale = 0.5 if aspect == "9:16" else 1.0
    centres = []
    try:
        for si, (clip, shot) in enumerate(zip(clips, shots)):
            frames = read_frames(Path(clip))
            if len(frames) == 0:
                raise RuntimeError(f"Shot {si + 1} came back with no frames.")
            a, b = shot_centres(frames) if aspect != "16:9" else ((0.5, 0.5), (0.5, 0.5))
            centres.append([a, b])
            idx = shot_indices(shot, len(frames))
            count = max(len(idx) - 1, 1)
            for k, j in enumerate(idx):
                u = k / count
                u = u * u * (3 - 2 * u)
                c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
                frame = reframe(frames[j], aspect, c, w, h)
                if fx and env is not None:
                    bi = int(np.searchsorted(beats, n / FPS)) if beats else 0
                    frame = beat_fx(frame, kick=float(env["kick"][min(n, total - 1)]),
                                    trans=float(env["trans"][min(n, total - 1)]),
                                    punch=float(punch[n]) if n < len(punch) else 0.0,
                                    loud=float(env["loud"][min(n, total - 1)]), beat_index=bi, zoom_scale=zoom_scale)
                if over is not None:
                    frame = over.draw(frame, n / FPS)
                enc.stdin.write(np.ascontiguousarray(frame).tobytes())
                n += 1
            if report:
                report("assemble", 0.6 + 0.35 * (si + 1) / len(shots), f"Cutting shot {si + 1} of {len(shots)} to the beat")
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not write the cut (exit {code}).")
    tmp.replace(out_path)
    return {"frames": n, "seconds": round(n / FPS, 3), "size": f"{w}x{h}", "aspect": aspect, "fx": bool(fx),
            "overlay": over is not None, "centres": centres}


def reframe_file(src: Path, dest: Path, aspect: str, *, quality: str = "draft", shots: list[dict] | None = None) -> dict:
    """Reframe a finished 16:9 cut to 9:16 or 1:1 following the subject (no FX change)."""
    aspect = norm_aspect(aspect)
    frames = read_frames(Path(src))
    w, h = out_size(aspect, quality)
    n = len(frames)
    if shots:
        edges = [round(float(s["start"]) * FPS) for s in shots] + [n]
    else:
        edges = list(range(0, n, FPS * 2)) + [n]
    edges = sorted({max(0, min(n, e)) for e in edges})
    tmp = Path(dest).with_name(Path(dest).stem + ".reframe.mp4")
    enc = subprocess.Popen([_ffmpeg(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-i", str(src), "-map", "0:v", "-map", "1:a?", "-c:v", "libx264",
                            "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
                            "-movflags", "+faststart", str(tmp)], stdin=subprocess.PIPE)
    try:
        for a, b in zip(edges[:-1], edges[1:]):
            seg = frames[a:b]
            c0, c1 = shot_centres(seg)
            for k, frame in enumerate(seg):
                u = k / max(len(seg) - 1, 1)
                c = (c0[0] + (c1[0] - c0[0]) * u, c0[1] + (c1[1] - c0[1]) * u)
                enc.stdin.write(np.ascontiguousarray(reframe(frame, aspect, c, w, h)).tobytes())
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not reframe the cut (exit {code}).")
    tmp.replace(dest)
    return {"aspect": aspect, "size": f"{w}x{h}", "frames": n}


# ------------------------------------------------------------------ end card


def _font() -> str | None:
    from xenoform.cloud_morph import _font as find

    return find()


def end_card(path: Path, recipe: str, repo: str | None = None, seconds: float = 2.0) -> bool:
    """Burn the recipe code and repo URL into the last ``seconds`` of the cut (in place)."""
    from xenoform.cloud_morph import _drawtext_font

    font = _font()
    if not font:
        return False
    path = Path(path)
    dur = probe_duration(path)
    if dur <= 0:
        return False
    start = max(0.0, dur - seconds)
    safe = lambda s: str(s).replace("\\", "").replace(":", "\\:").replace("'", "").replace("%", "")[:96]
    ff = _drawtext_font(font)
    common = f"fontfile='{ff}':fontcolor=white:enable='gte(t,{start:.2f})':x=(w-text_w)/2"
    vf = (f"drawbox=x=0:y=ih*0.62:w=iw:h=ih*0.26:color=black@0.55:t=fill:enable='gte(t,{start:.2f})',"
          f"drawtext={common}:text='Every drop is a transformation':fontsize='min(h/26,w/22)':y=h*0.645,"
          f"drawtext={common}:text='recipe {safe(recipe)}':fontsize='min(h/30,w/26)':y=h*0.72,"
          f"drawtext={common}:text='Xenoform · {safe(repo or repo_url())}':fontsize='min(h/30,w/26)':y=h*0.79")
    tmp = path.with_name(path.stem + ".card.mp4")
    done = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(path), "-vf", vf, "-c:v", "libx264", "-preset",
                           "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart",
                           str(tmp)])
    if done.returncode:
        return False
    tmp.replace(path)
    return True


def probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ 15 s hook


def pick_hook(audio_path: Path, length: float = 15.0, beats: Iterable[float] = (), lead_in: float = 3.0) -> dict:
    """The window of ``length`` seconds around the strongest drop: lead in a few beats, then the hit.

    The drop is the biggest one-bar jump in loudness. The window starts ``lead_in`` seconds
    before it (snapped to the nearest beat) and is clamped to the song.
    """
    import librosa

    sr = 22050
    y = load_audio(Path(audio_path), sr)
    dur = len(y) / sr
    if dur <= length + 0.05:
        return {"start": 0.0, "end": round(dur, 3), "drop": 0.0, "whole_song": True}
    beats = [float(b) for b in beats]
    drop = drop_time(Path(audio_path), beats, lo=0.1, hi=max(0.15, 1 - (length - lead_in) / dur * 0.6))
    start = drop - lead_in
    if beats:
        start = min(beats, key=lambda b: abs(b - start)) if start > 0 else 0.0
    start = max(0.0, min(dur - length, start))
    return {"start": round(start, 3), "end": round(start + length, 3), "drop": round(drop, 3), "whole_song": False}


def export_hook(src: Path, dest: Path, start: float, length: float = 15.0) -> dict:
    """Cut [start, start+length] from a finished video with short audio fades. Re-encodes for frame accuracy."""
    fade = 0.25
    done = subprocess.run([_ffmpeg(), "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{length:.3f}",
                           "-af", f"afade=t=in:d={fade},afade=t=out:st={max(0.0, length - fade - 0.05):.3f}:d={fade}",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac",
                           "-b:a", "192k", "-movflags", "+faststart", str(dest)], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("ffmpeg could not cut the hook: " + done.stderr[-300:])
    return {"file": str(dest), "start": start, "seconds": round(probe_duration(Path(dest)), 3)}


def write_meta(path: Path, meta: dict) -> None:
    Path(path).write_text(json.dumps(meta, indent=1, default=str), encoding="utf-8")


def drop_time(audio_path: Path, beats: Iterable[float] = (), lo: float = 0.25, hi: float = 0.85) -> float:
    """The song's main drop: the biggest one-bar jump in loudness between ``lo`` and ``hi`` of the song."""
    import librosa

    sr = 22050
    y = load_audio(Path(audio_path), sr)
    dur = len(y) / sr
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    t = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    beats = [float(b) for b in beats]
    bar = 4 * float(np.median(np.diff(beats))) if len(beats) >= 2 else 2.0
    win = max(1, int(round(bar * sr / hop)))
    half, two = max(1, win // 2), 2 * win
    smooth = np.convolve(rms, np.ones(half) / half, mode="full")[: len(rms)]  # the half bar before (the dip)
    ahead = np.convolve(rms[::-1], np.ones(two) / two, mode="full")[: len(rms)][::-1]  # the two bars after (sustained)
    score = np.where((t >= dur * lo) & (t <= dur * hi), ahead - smooth, -1e9)
    drop = float(t[int(np.argmax(score))])
    return float(min(beats, key=lambda b: abs(b - drop))) if beats else drop
