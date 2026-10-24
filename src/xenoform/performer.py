"""Performer shots: the woman from the reference still performs the song on screen.

MiniMax H3 (33B, joint video+audio) is run image-to-video through ComfyUI with the song
segment anchored at frame 0 (``MiniMaxH3AddGuide``), so the picture is generated against the
real music rather than a soundtrack the model invents. The 8-step lightx2v turbo LoRA cuts a
5.17 s shot from ~6.5 minutes (20 steps) to a few minutes on a 16 GB card.

Contract used by the desk (dense.py / beatfx.py code against it):

- ``GRID``, ``FPS``, ``SIZE``, ``MIN_SECONDS``: the frame counts H3 accepts (17k+5 at 24 fps).
- ``grid_frames(seconds)``: smallest grid length covering ``seconds``.
- ``available(cfg)``: are the model files and the LoRA installed (ComfyUI ``/models`` lists, cached 60 s).
- ``default_reference(instrument=None, pick=0)``: the bundled Polly still, posed for the instrument when that still ships.
- ``prompt_for(role, vibe_look, instrument=None)``: drums on the drop, keys elsewhere, singing only when asked.
- ``render_slot(...)``: cut the song, render with a two-second pre-roll, start the clip where the
  performance has begun (past a held, dissolving or hard-cut reference still), trim to
  ``round(seconds*fps)`` frames, mux the song segment back, score stroke-to-beat sync, retry once
  with seed+1 when the still leaks into the slot or a drum shot froze and is off the beat.
- ``sync_score(clip, beats)``: 0..1, 1 = every beat has a motion stroke on it.
- ``estimate_seconds(seconds, steps)``: wall-time estimate from the measured runs.

Everything here is open weights running locally; see docs/performer.md for the licence.
"""
from __future__ import annotations

import json
import logging
import math
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("xenoform.performer")

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "workflows" / "minimax_h3_i2v_api.json"
GRAPH_TURBO = ROOT / "workflows" / "minimax_h3_i2v_turbo_api.json"
STILL = Path(__file__).resolve().parent / "ui_static" / "performer" / "polly.png"
STILL_FALLBACK = ROOT / "work" / "v4" / "in" / "polly_576.png"

# H3 accepts 17k+5 frames at 24 fps; the model was trained on ~124..362, the desk stops at 260 (10.8 s)
GRID = [124, 141, 158, 175, 192, 209, 226, 243, 260]
FPS = 24
SIZE = (480, 832)  # portrait; both sides must be multiples of 32
MIN_SECONDS = GRID[0] / FPS
AUDIO_SR = 32000  # the H3 audio VAE's rate
PAD_SECONDS = 0.5  # the anchored segment runs past the video so the last frames are not generated against silence

UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
TEXT_ENCODER = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VIDEO_VAE = "minimax_h3_video_vae_fp16.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
LORA = "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
STEPS_TURBO = 8  # the LoRA's NFE (lightx2v card: 8, or 4 in a pinch)
STEPS_BASE = 20
SHIFT_VIDEO, SHIFT_AUDIO = 12.0, 3.0  # lightx2v card, 544p-class LoRA; the 768p LoRAs want 6 / 3
SAMPLER_TURBO = "euler"

# node ids shared by both graphs (the turbo graph adds 18 LoraLoaderModelOnly and 19 MiniMaxH3SigmaShift)
N_UNET, N_I2V, N_GUIDER, N_SAMPLER, N_SCHED, N_NOISE = "1", "5", "6", "7", "8", "9"
N_MUX, N_SAVE, N_IMAGE, N_AUDIO, N_GUIDE, N_LORA, N_SHIFT = "13", "14", "15", "16", "17", "18", "19"

DRUM_ROLES = frozenset({"drop", "build", "drop_late"})
SING_ROLES = frozenset({"intro", "calm", "sustain", "release", "outro"})

# A drum shot is re-rolled once with seed+1 when it is "poor": its strokes are no better than chance
# against the beat grid (sync below POOR_SYNC; the real shots measured 0.0-0.1, so the score alone
# would re-roll every one of them) AND the picture shows one of the two failure modes seen on the
# model: it held the still for POOR_FREEZE_S or longer, or it hard-cut to another shot after the
# opening (a cut inside the first POOR_CUT_FRAMES is the model's own way into the performance).
POOR_SYNC = 0.05
POOR_FREEZE_S = 1.0
POOR_CUT_FRAMES = 12
# The song is fed two seconds early, and every spare frame of the grid length is pre-roll too: H3 holds the
# reference still, dissolves out of it or hard-cuts away 7 to 44 frames in (measured on the real shots) before
# the performance, and the clip starts where the performance has begun. The one-second pre-roll it replaced
# left only 7-30 spare frames, so the skip was clamped and up to half a second of the standing still leaked.
PRE_ROLL_S = 2.0
STILL_GONE = 0.9  # the still has left the picture once its correlation with the frame has fallen this share of the way from the opening frame to the settled scene (at 0.5 a ghost of it showed for four frames, at 0.8 for one)
STILL_STAYS = 0.6  # a settled scene still this correlated with the still is the performance in place (the posed stills): nothing to detect
SYNC_TOL_FRAMES = 2  # a stroke within +-2 frames (83 ms) of the beat counts
SYNC_LAGS = range(-1, 4)  # strokes may land a frame early or up to three late (picture lags the hit)

# wall-time model from the measured shots on a 12 GB card that streams the model from RAM (docs/performer.md
# has the table). With the turbo LoRA the real runs took 383 s for 124 frames, 442 s for 158 and 488 s for
# 192: linear in the frame count, about 1.5 s a frame over a 192 s floor (loads, decodes, and the LoRA's
# patches re-applied to the streamed weights). The base model measured 393 s for 124 frames at 20 steps.
_LOAD_S = 192.0
_PER_FRAME_STEP_S_BASE = 0.081  # (393 - 192) / (20 * 124)
_PER_FRAME_STEP_S_LORA = 0.193  # (383 - 192) / (8 * 124)

GB = 1024 ** 3
_CACHE: dict = {}


# --------------------------------------------------------------------------- grid, prompts, files

def grid_frames(seconds: float) -> int:
    """Smallest H3 frame count covering ``seconds`` at 24 fps, capped at the longest grid length."""
    need = int(round(max(0.0, float(seconds)) * FPS))  # nearest frame: 5.17 s means 124 frames, not 125
    for n in GRID:
        if n >= need:
            return n
    return GRID[-1]


def default_reference(instrument: str | None = None, pick: int = 0) -> Path:
    """The bundled Polly still: posed for ``instrument`` (``polly_<performance>.png`` beside ``polly.png``: at
    the kit, the microphone, the keys, with a guitar, dancing) when that still ships, else standing (falling
    back to the work/v4 original when the package copy is missing). Numbered variants of a pose
    (``polly_dance_2.png``) rotate with ``pick`` (the slot's index), so two dance slots get two poses."""
    if instrument:
        what = performance_for("", instrument)
        posed = sorted(p for p in STILL.parent.glob(f"polly_{what}*.png")
                       if p.stem == f"polly_{what}" or p.stem[len(what) + 7:].isdigit()) if STILL.parent.is_dir() else []
        if posed:
            return posed[int(pick) % len(posed)]
    if STILL.exists() or not STILL_FALLBACK.exists():
        return STILL
    return STILL_FALLBACK


def performance_for(role: str, instrument: str | None = None) -> str:
    """'drums' on the drop/build, 'vocals' elsewhere; ``instrument`` overrides ('drums', 'vocals', or any noun)."""
    if instrument:
        key = str(instrument).strip().lower()
        if key in {"drums", "drum", "drum kit", "kit", "percussion"}:
            return "drums"
        if key in {"mic", "microphone", "vocals", "vocal", "sing", "singing", "voice", "singer", "lipsync", "lip-sync"}:
            return "vocals"
        if key in {"keys", "key", "keyboard", "synth", "synthesizer", "piano"}:
            return "keys"
        if key in {"guitar", "electric guitar", "bass guitar", "bass"}:
            return "guitar"
        if key in {"dance", "dancing", "dancer"}:
            return "dance"
        return key
    # no instrument given: drums on the drop, keys elsewhere. Singing is chosen by the planner only where
    # the song's vocal stem actually sings (dense.performer_slots), so she never mouths words that are not there.
    return "drums" if str(role) in DRUM_ROLES else "keys"


# The bundled reference (Polly): the outfit is named so the model does not re-dress her for the venue.
OUTFIT = "silver-grey bob, white cropped bomber jacket with a teal zip over a white tee, light-blue straight jeans, white trainers"
_IDENTITY = ("One continuous unbroken take with no cuts and no scene change: the woman from the first frame, "
             f"with exactly the same face, hair and outfit ({OUTFIT}) from the first frame to the last, ")
_ACTION = {
    "drums": ("is already playing a drum kit when the clip starts and never pauses: both sticks hitting the "
              "snare, toms and cymbals on every beat of the music, the kick on every downbeat, head and "
              "shoulders driving with the groove. "),
    "vocals": ("is already singing into a studio microphone when the clip starts and keeps singing: lips "
               "shaping every word of the vocal line, eyes closing on the long notes, one hand on the mic "
               "stand, body swaying with the music. "),
    "keys": ("is already playing a synthesizer keyboard when the clip starts and never pauses: both hands on "
             "the keys, fingers landing on every chord of the music, her mouth closed, head nodding with the groove. "),
    "guitar": ("is already playing an electric guitar when the clip starts and never pauses: strumming and picking "
               "in time with the music, her mouth closed, eyes on the fretboard, body moving with the groove. "),
    "dance": ("is already dancing when the clip starts and never pauses: full-body moves locked to the beat, "
              "arms and hips on the downbeats, her mouth closed, feet planted in frame. "),
}
_CAMERA = ("The first frame flows straight into the performance and the camera never cuts away: medium shot, "
           "steady camera, she stays centred and fully in frame for the whole clip. "
           "Audio: the music track only, no speech.")


def prompt_for(role: str, vibe_look: str, instrument: str | None = None) -> str:
    """A prompt that keeps the referenced woman on screen from frame one and has her perform the music.

    Drums for the drop/build roles, singing into a microphone for the quiet roles, styled with the
    vibe's look (``morph_pass.VIBE_LOOK[vibe]``). The wording is tuned on the model: an earlier
    'the scene opens on the figure from the first frame' held the still for 4-5 s, 'is already
    playing ... when the clip starts' performs at once.
    """
    what = performance_for(role, instrument)
    action = _ACTION.get(what) or (f"is already playing the {what} when the clip starts and never pauses, "
                                   "every note in time with the music. ")
    look = str(vibe_look or "").strip().rstrip(".")
    style = f"Look: {look}. " if look else ""
    return _IDENTITY + action + style + _CAMERA


# --------------------------------------------------------------------------- availability

def _comfy_urls(cfg: dict | None) -> list[str]:
    comfy = (cfg or {}).get("comfy") or {}
    base = str(comfy.get("base_url") or "http://127.0.0.1:8188").rstrip("/")
    proxy = str(comfy.get("proxy_url", "http://127.0.0.1:8189") or "").rstrip("/")
    urls = [base]
    if proxy and proxy != base:
        urls.append(proxy)
    return urls


def _fetch_model_lists(cfg: dict | None, timeout: float = 4.0) -> dict[str, list[str]] | None:
    """ComfyUI's /models/<folder> lists (8188 first; the comfy-api-proxy on 8189 does not forward them)."""
    for url in _comfy_urls(cfg):
        try:
            lists = {}
            for folder in ("diffusion_models", "text_encoders", "vae", "loras"):
                with urllib.request.urlopen(f"{url}/models/{folder}", timeout=timeout) as r:
                    lists[folder] = [str(n) for n in json.load(r)]
            return lists
        except Exception as exc:  # unreachable, or a proxy without /models
            log.debug("no /models lists at %s: %s", url, exc)
    return None


def _has(lists: dict[str, list[str]], folder: str, name: str) -> bool:
    return any(Path(n.replace("\\", "/")).name == name for n in lists.get(folder) or [])


def _parse_available(lists: dict[str, list[str]] | None) -> dict:
    """Turn the /models lists into the availability dict (pure; tests feed it fake lists)."""
    if lists is None:
        return {"ok": False, "model": False, "text_encoder": False, "video_vae": False, "audio_vae": False,
                "lora": None, "steps": STEPS_BASE, "missing": [UNET, TEXT_ENCODER, VIDEO_VAE, AUDIO_VAE],
                "note": "ComfyUI is not answering /models; start it to render performer shots."}
    have = {
        "model": _has(lists, "diffusion_models", UNET),
        "text_encoder": _has(lists, "text_encoders", TEXT_ENCODER),
        "video_vae": _has(lists, "vae", VIDEO_VAE),
        "audio_vae": _has(lists, "vae", AUDIO_VAE),
    }
    lora = LORA if _has(lists, "loras", LORA) else None
    names = {"model": UNET, "text_encoder": TEXT_ENCODER, "video_vae": VIDEO_VAE, "audio_vae": AUDIO_VAE}
    missing = [names[k] for k, ok in have.items() if not ok]
    ok = not missing
    steps = STEPS_TURBO if lora else STEPS_BASE
    per_shot = estimate_seconds(MIN_SECONDS, steps)
    if ok and lora:
        note = f"MiniMax H3 ready with the 8-step turbo LoRA: about {per_shot:.0f} s per 5 s shot."
    elif ok:
        note = (f"MiniMax H3 ready without the turbo LoRA ({LORA} missing): 20 steps, "
                f"about {per_shot:.0f} s per 5 s shot.")
    else:
        note = "MiniMax H3 not installed: missing " + ", ".join(missing) + "."
    return {"ok": ok, **have, "lora": lora, "steps": steps, "missing": missing, "note": note}


def available(cfg: dict | None = None, *, fetch: Callable | None = None, max_age: float = 60.0) -> dict:
    """Whether the H3 model, text encoder, both VAEs and the turbo LoRA are installed.

    Probes ComfyUI's ``/models/...`` lists (cached ``max_age`` seconds). ``steps`` is 8 with the
    LoRA, 20 without; ``lora`` is the LoRA filename or None; ``note`` is one line for the desk.
    """
    key = tuple(_comfy_urls(cfg))
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < max_age and fetch is None:
        return dict(hit[1])
    lists = (fetch or _fetch_model_lists)(cfg)
    value = _parse_available(lists)
    value["checked"] = now
    _CACHE[key] = (now, value)
    return dict(value)


# --------------------------------------------------------------------------- timing

def estimate_seconds(seconds: float, steps: int | None) -> float:
    """Wall time of one shot of ``seconds`` at ``steps`` (model loads included, queue wait not).

    The render covers the slot plus the pre-roll (``render_slot`` picks the grid length the same way)
    and the measured runs are linear in that frame count. ``steps`` None means the turbo LoRA's 8.
    """
    frames = grid_frames(float(seconds) + PRE_ROLL_S)
    steps = int(steps or STEPS_TURBO)
    per = _PER_FRAME_STEP_S_LORA if steps <= STEPS_TURBO else _PER_FRAME_STEP_S_BASE
    return _LOAD_S + per * steps * frames


# --------------------------------------------------------------------------- ffmpeg helpers

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def cut_audio(song: Path, t0: float, seconds: float, out: Path, *, sr: int = AUDIO_SR) -> Path:
    """Cut [t0, t0+seconds] of the song to a stereo wav at the audio VAE's rate (sample-accurate)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t1 = float(t0) + float(seconds)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(song),
          "-af", f"atrim=start={t0:.6f}:end={t1:.6f},asetpts=PTS-STARTPTS,apad=whole_dur={seconds:.6f}",
          "-t", f"{seconds:.6f}", "-ac", "2", "-ar", str(sr), "-c:a", "pcm_s16le", str(out)])
    return out


def fit_still(still: Path, size: tuple[int, int], out: Path) -> Path:
    """Cover-crop the still to the render size so H3's stretch-to-canvas does not distort the face."""
    w, h = int(size[0]), int(size[1])
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(still),
          "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=rgb24",
          "-frames:v", "1", str(out)])
    return out


def finish_clip(raw: Path, song: Path, t0: float, frames: int, out: Path, *, fps: float = FPS, skip: int = 0) -> Path:
    """Trim the H3 render to exactly ``frames`` frames (starting ``skip`` frames in) and mux the original song
    segment [t0, t0 + frames/fps] over it, so the picture at the slot start plays against the slot's music."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seconds = frames / float(fps)
    t1 = float(t0) + seconds
    skip = max(0, int(skip))
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-i", str(song),
          "-filter_complex",
          f"[0:v]trim=start_frame={skip}:end_frame={skip + int(frames)},setpts=PTS-STARTPTS,fps={fps}[v];"
          f"[1:a]atrim=start={t0:.6f}:end={t1:.6f},asetpts=PTS-STARTPTS,apad=whole_dur={seconds:.6f}[a]",
          "-map", "[v]", "-map", "[a]", "-frames:v", str(int(frames)), "-t", f"{seconds:.6f}",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)])
    return out


def count_frames(clip: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(clip)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return int(out.splitlines()[0]) if out else 0


def grey_frames(clip: Path, width: int = 96, height: int | None = None) -> np.ndarray:
    """Every frame of ``clip`` (a video, or a still) as a small grey array: shape (frames, h, w), float32 0..255."""
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", str(clip)],
                           capture_output=True, text=True, check=True).stdout.strip().split(",")
    w0, h0 = int(probe[0]), int(probe[1])
    h = int(height) if height else max(2, int(round(h0 * width / w0 / 2)) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-vf", f"scale={width}:{h}", "-pix_fmt", "gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, width).astype(np.float32)


def motion_energy(clip: Path, width: int = 96) -> np.ndarray:
    """Mean absolute frame-to-frame difference of a small grey copy; entry i is frame i -> i+1."""
    frames = grey_frames(clip, width)
    if frames.shape[0] < 2:
        return np.zeros(0, dtype=np.float32)
    return np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))


def resemblance(clip: Path, still: Path, width: int = 96) -> np.ndarray:
    """How much each frame of ``clip`` still looks like ``still``: the normalised correlation of the two small
    grey pictures, 1 for the still itself and about 0 for an unrelated scene (a brightness or colour change
    does not count, a different composition does). The still is scaled to the clip's small frame."""
    frames = grey_frames(clip, width)
    if frames.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)
    ref = grey_frames(still, width, frames.shape[1])[0]
    ref = ref - ref.mean()
    norm_ref = float(np.sqrt((ref * ref).sum()))
    out = np.zeros(frames.shape[0], dtype=np.float32)
    for i, f in enumerate(frames):
        f = f - f.mean()
        d = float(np.sqrt((f * f).sum())) * norm_ref
        out[i] = float((f * ref).sum() / d) if d > 0 else 0.0
    return out


def still_gone(r: np.ndarray, *, share: float = STILL_GONE, hold: int = 3) -> int | None:
    """The first frame from which the picture no longer resembles the reference still, or None.

    ``r`` is ``resemblance``. The opening frame of an image-to-video shot is the still (r near 1) and the
    settled performance sits some way off it (the median of the clip's second half); the still has gone
    once the correlation has fallen ``share`` of the way between the two and stays there ``hold`` frames.
    This is the signal for a dissolve, which ``diagnose`` cannot see: no frame is a freeze or a hard cut.
    None when the opening frame is not the still (nothing to detect) or the settled scene still resembles
    it (above ``STILL_STAYS``: a hold, which ``diagnose`` reports, or the performance in place, which is
    what a posed still is for; the frames then wander around that level and would trip the test by noise).
    """
    r = np.asarray(r, dtype=np.float32)
    n = len(r)
    if n < hold + 1 or float(r[0]) < 0.5:
        return None
    far = float(np.median(r[n // 2:]))
    if far > STILL_STAYS:
        return None
    thr = far + (1.0 - float(share)) * (float(r[0]) - far)
    for i in range(n - hold + 1):
        if bool((r[i:i + hold] < thr).all()):
            return int(i)
    return None


# --------------------------------------------------------------------------- sync

HARD_CUT = 40.0  # mean |frame diff| (0..255) above this is a cut, not a stroke: the model left the still
FREEZE_MOTION = 1.5  # below this the picture is holding the still (a held still breathes at 0.3-1.1, play is 4-10)


def diagnose(motion: np.ndarray, *, fps: float = FPS) -> dict:
    """``freeze_s``: how long the opening holds the still; ``cuts``: frames where the picture hard-cuts.

    An H3 image-to-video shot can hold the reference for a while and then cut to a scene of its own
    (the earlier probe held 9 frames, then cut); both show in the motion curve, so the desk can
    tell a performer shot that lost Polly from one that kept her.
    """
    motion = np.asarray(motion, dtype=np.float32)
    held = 0
    for v in motion:
        if v >= FREEZE_MOTION:
            break
        held += 1
    cuts = [int(i) + 1 for i, v in enumerate(motion) if v >= HARD_CUT]
    return {"freeze_s": round(held / float(fps), 2), "cuts": cuts}


def _strokes(motion: np.ndarray, count: int, min_gap: int) -> list[int]:
    """The ``count`` strongest local maxima of the motion curve, at least ``min_gap`` frames apart."""
    n = len(motion)
    peaks = [i for i in range(n)
             if (i == 0 or motion[i] > motion[i - 1]) and (i == n - 1 or motion[i] >= motion[i + 1])]
    peaks.sort(key=lambda i: -float(motion[i]))
    chosen: list[int] = []
    for i in peaks:
        if all(abs(i - j) >= min_gap for j in chosen):
            chosen.append(i)
        if len(chosen) >= count:
            break
    return sorted(chosen)


def _hit_rate(beat_frames: np.ndarray, strokes: np.ndarray, n: int, tol: int, lags) -> float:
    if len(beat_frames) == 0 or len(strokes) == 0:
        return 0.0
    best = 0.0
    for lag in lags:
        b = beat_frames + lag
        keep = (b >= 0) & (b < n)
        if not keep.any():
            continue
        d = np.abs(b[keep][:, None] - strokes[None, :]).min(axis=1)
        best = max(best, float((d <= tol).mean()))
    return best


def sync_score(clip: Path, beats: list[float], *, fps: float = FPS, tol: int = SYNC_TOL_FRAMES,
               lags=SYNC_LAGS, permutations: int = 200) -> float:
    """How well the picture's strokes sit on the beats: 0..1, 1 = a motion stroke on every beat.

    Per-frame motion energy -> the N strongest strokes (N = beats inside the clip) -> the share of
    beats with a stroke within ``tol`` frames at the best lag, lifted above what a randomly shifted
    beat grid gets (the chance level with this many strokes), so a frozen or unrelated picture
    scores ~0 and a locked one 1.
    """
    return sync_from_motion(motion_energy(Path(clip)), beats, fps=fps, tol=tol, lags=lags, permutations=permutations)


def sync_from_motion(motion: np.ndarray, beats: list[float], *, fps: float = FPS, tol: int = SYNC_TOL_FRAMES,
                     lags=SYNC_LAGS, permutations: int = 200) -> float:
    """``sync_score`` on an already measured motion curve (see ``motion_energy``)."""
    motion = np.asarray(motion, dtype=np.float32)
    n = len(motion)
    if n < 4 or float(motion.std()) < 1e-6:
        return 0.0
    bf = np.array(sorted({int(round(float(b) * fps)) - 1 for b in beats
                          if 0 <= int(round(float(b) * fps)) - 1 < n}), dtype=int)
    if len(bf) == 0:
        return 0.0
    strokes = np.array(_strokes(motion, len(bf), tol + 1), dtype=int)
    observed = _hit_rate(bf, strokes, n, tol, lags)
    rng = np.random.default_rng(0)
    null = []
    for _ in range(int(permutations)):
        shift = int(rng.integers(tol + 2, max(tol + 3, n - tol - 2)))
        null.append(_hit_rate((bf + shift) % n, strokes, n, tol, lags))
    chance = float(np.mean(null)) if null else 0.0
    if chance >= 0.999:
        return 0.0
    return float(min(1.0, max(0.0, (observed - chance) / (1.0 - chance))))


# --------------------------------------------------------------------------- render

class _VramPoller(threading.Thread):
    """Samples ComfyUI's /system_stats while a job runs; ``peak_gb`` is the most VRAM in use."""

    def __init__(self, url: str, period: float = 2.0) -> None:
        super().__init__(daemon=True)
        self.url, self.period = url, period
        self.peak_gb: float | None = None
        self._halt = threading.Event()

    def sample(self) -> None:
        with urllib.request.urlopen(f"{self.url}/system_stats", timeout=3) as r:
            d = json.load(r)["devices"][0]
        used = (d["vram_total"] - d["vram_free"]) / GB
        self.peak_gb = round(max(self.peak_gb or 0.0, used), 2)

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                self.sample()
            except Exception:
                pass
            self._halt.wait(self.period)

    def stop(self) -> None:
        self._halt.set()


def _is_drums(prompt: str) -> bool:
    return "drum" in str(prompt).lower()


def _is_singing(prompt: str) -> bool:
    return "singing" in str(prompt).lower()


def _client_for(cfg: dict):
    from xenoform.cloud_morph import _client

    return _client(cfg)


_TERMINAL = {"completed", "success", "succeeded", "failed", "cancelled", "canceled", "expired", "error"}


def _wait(job, client, report, label: str, est_s: float, poll_s: float = 1.0):
    """Block until the job is terminal, reporting progress from the time estimate; returns the result."""
    from xenoform.cloud_morph import _job_result

    started = time.perf_counter()
    refresh = getattr(job, "refresh", None)
    while refresh is not None:
        try:
            refresh()
        except Exception:
            log.debug("refresh of %s failed; trying again", getattr(job, "id", "?"))
        if str(getattr(job, "status", "") or "").lower() in _TERMINAL:
            break
        if report:
            elapsed = time.perf_counter() - started
            left = max(0, int(round(est_s - elapsed)))
            report("restyle", min(0.95, elapsed / max(est_s, 1.0)), f"{label} - about {left} s left")
        time.sleep(poll_s)
    return _job_result(client, job)


def submit_shot(client, graph: Path, still: Path, segment: Path, prompt: str, frames: int, size: tuple[int, int],
                steps: int, seed: int, lora: str | None, out: Path, *, report=None, label: str = "Performer shot",
                est_s: float = 0.0, fps: float = FPS):
    """Submit one H3 image+audio-to-video job and save its mp4 to ``out``."""
    wf = client.workflows.from_file(str(graph))
    wf.set_input(N_IMAGE, "image", client.assets.from_file(str(still)))
    wf.set_input(N_AUDIO, "audio", client.assets.from_file(str(segment)))
    wf.set_input(N_I2V, "prompt", prompt)
    wf.set_input(N_I2V, "width", int(size[0]))
    wf.set_input(N_I2V, "height", int(size[1]))
    wf.set_input(N_I2V, "length", int(frames))
    wf.set_input(N_SCHED, "steps", int(steps))
    wf.set_input(N_NOISE, "noise_seed", int(seed))
    wf.set_input(N_MUX, "fps", float(fps))
    wf.set_input(N_SAVE, "filename_prefix", f"video/xenoform_performer_{out.stem}")
    if lora:
        wf.set_input(N_LORA, "lora_name", lora)
        wf.set_input(N_SHIFT, "shift_video", SHIFT_VIDEO)
        wf.set_input(N_SHIFT, "shift_audio", SHIFT_AUDIO)
    job = client.submit(wf)
    result = _wait(job, client, report, label, est_s)
    outs = list(result.get_outputs(N_SAVE)) or list(result.outputs)
    if not outs:
        raise RuntimeError("The performer shot came back with no video.")
    vid = next((o for o in outs if getattr(o, "type", None) == "video"), outs[0])
    out.parent.mkdir(parents=True, exist_ok=True)
    vid.to_file(str(out))
    return job


def render_slot(audio_path, t0: float, seconds: float, still: Path, prompt: str, work: Path, cfg: dict, *,
                seed: int = 0, steps: int | None = None, size=SIZE, fps: float = FPS, client=None, report=None,
                beats: list[float] | None = None, max_tries: int = 2, source_path=None, source_offset: float = 0.0) -> dict:
    """Render one performer shot of ``seconds`` seconds starting at song time ``t0``.

    ``source_path`` with ``source_offset``: the full song a Length cut was trimmed from and where the cut
    starts in it; the anchor segment (and so the pre-roll) is then cut from the full song, so a slot at the
    top of the cut still has real music before it. The clip's own audio stays the cut's.

    The song is fed early (``PRE_ROLL_S`` plus whatever the grid length spares, as far as the song's own
    start allows) and anchored at frame 0; H3 holds the reference still, dissolves out of it or hard-cuts
    away 7 to 44 frames in before the performance, so the clip starts ``skip`` frames in (the pre-roll, or
    where the still has gone when that came later), is trimmed to exactly ``round(seconds * fps)`` frames
    and gets the original song segment [t0, t0 + seconds] muxed over it (not the VAE round trip). A shot
    is re-rolled with seed+1 (up to ``max_tries`` renders) when the still would still leak more than half
    a second into the slot, when a singing shot would run that far ahead of the music (its lips off the
    words), or, with ``beats`` (song time), when a drum shot froze past the pre-roll and its ``sync_score``
    is below ``POOR_SYNC``. The whole shot wins over a leaking one, then the better beat.
    """
    if cfg is None:
        from xenoform.config import load_config

        cfg = load_config()
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    audio_path, still = Path(audio_path), Path(still)
    w = max(32, int(round(int(size[0]) / 32)) * 32)
    h = max(32, int(round(int(size[1]) / 32)) * 32)
    want = max(1, int(round(float(seconds) * fps)))
    pre_min = int(round(PRE_ROLL_S * fps))
    frames = next((g for g in GRID if g >= want + pre_min), GRID[-1])  # the grid length that covers the pre-roll too
    want = min(want, frames)  # the longest clip H3 makes: give up pre-roll rather than picture
    room = frames - want  # the most frames the clip can skip and still be whole
    # every spare frame is pre-roll (the song is fed that much earlier), as far as the song's own start allows;
    # at the top of a song there is no earlier music, so the spare frames stay as room past a held still
    src = Path(source_path) if source_path else audio_path
    off = float(source_offset or 0.0) if source_path else 0.0
    pre_frames = min(room, int(round((float(t0) + off) * fps)))
    t_in = max(0.0, float(t0) + off - pre_frames / float(fps))  # in the source song's time
    avail = available(cfg)
    lora = avail.get("lora")
    graph = GRAPH_TURBO if lora else GRAPH
    steps = int(steps or avail.get("steps") or STEPS_BASE)
    tag = f"{float(t0):.2f}"
    clip = work / f"performer_{tag}.mp4"
    segment = cut_audio(src, t_in, frames / float(fps) + PAD_SECONDS, work / f"performer_{tag}_seg.wav")
    fitted = fit_still(still, (w, h), work / f"performer_{tag}_still.png")
    client = client or _client_for(cfg)
    local = [float(b) - float(t0) for b in (beats or [])]
    est = estimate_seconds(seconds, steps)
    drums = _is_drums(prompt)
    singing = _is_singing(prompt)
    poller = _VramPoller(_comfy_urls(cfg)[0])
    poller.start()
    tries, best, scores = 0, None, []
    try:
        for attempt in range(max(1, int(max_tries))):
            s = int(seed) + attempt
            raw = work / f"performer_{tag}_h3_{attempt}.mp4"
            label = f"Performer shot at {float(t0):.1f} s" + (f" (retry {attempt})" if attempt else "")
            started = time.perf_counter()
            submit_shot(client, graph, fitted, segment, prompt, frames, (w, h), steps, s, lora, raw,
                        report=report, label=label, est_s=est, fps=fps)
            render_s = time.perf_counter() - started
            tries += 1
            candidate = work / f"performer_{tag}_try{attempt}.mp4"
            motion_raw = motion_energy(raw)
            diag = diagnose(motion_raw, fps=fps)
            gone = still_gone(resemblance(raw, fitted))
            # start where the performance has begun: at the pre-roll, or later when the still was held past it,
            # dissolved out (the frame stopped resembling the fitted still) or hard-cut away in the opening
            opening = pre_frames + POOR_CUT_FRAMES * 4
            first_cut = next((c for c in diag["cuts"] if c <= opening), None)
            while first_cut is not None and first_cut + 1 in diag["cuts"]:
                first_cut += 1  # a cut through a flash frame counts twice: start after the second
            held = int(round(float(diag["freeze_s"]) * fps))
            start = max(pre_frames, held, first_cut or 0, gone or 0)
            skip = min(start, max(0, min(len(motion_raw) + 1, frames) - want))
            leak = start - skip  # frames of the still (or its dissolve) the clip has to show: no room left to skip
            drift = max(0, skip - pre_frames)  # the picture runs this far ahead of the music (the hold ate the pre-roll)
            diag.update({"skip": int(skip), "gone": gone, "leak_frames": int(leak), "drift_frames": int(drift)})
            finish_clip(raw, audio_path, float(t0), want, candidate, fps=fps, skip=skip)
            motion = motion_raw[skip:skip + want] if len(motion_raw) > skip else motion_energy(candidate)
            score = sync_from_motion(motion, local, fps=fps) if local else None
            scores.append(score)
            got = count_frames(candidate)
            log.info("performer %s: try %d seed %d, %d frames, sync %s, held %.2f s, cuts %s, still gone %s, skip %d "
                     "(leak %d, drift %d), %.0f s", tag, attempt + 1, s, got, "n/a" if score is None else f"{score:.2f}",
                     diag["freeze_s"], diag["cuts"], gone, skip, leak, drift, render_s)
            # poor: the still leaks into the slot (no room left to skip it), a singing shot runs so far ahead of
            # the music that the lips would be off, or a drum shot froze past the pre-roll and is off the beat
            held_after = max(0, held - pre_frames)  # frames of the held still that the pre-roll could not hide
            leaking = leak > POOR_CUT_FRAMES
            late = singing and drift > POOR_CUT_FRAMES
            frozen = drums and held_after >= POOR_FREEZE_S * fps and score is not None and score < POOR_SYNC
            poor = leaking or late or frozen
            quality = (0 if poor else 1, -1.0 if score is None else float(score))  # a whole shot first, then the beat
            if best is None or quality > best["quality"]:
                best = {"path": candidate, "raw": raw, "sync": score, "seed": s, "render_s": render_s, "frames": got,
                        "quality": quality, **diag}
            if not poor:
                break
            if report:
                why = (f"the still leaks {leak / fps:.1f} s into the slot" if leaking
                       else f"the performance starts {drift / fps:.1f} s late" if late
                       else f"held the still {diag['freeze_s']:.1f} s, strokes off the beat (sync {score:.2f})")
                report("restyle", 0.95, f"{label}: {why}; re-rolling with seed {s + 1}")
    finally:
        poller.stop()
        poller.join(timeout=3)
    if clip.exists():
        clip.unlink()
    best["path"].replace(clip)
    if report:
        report("restyle", 1.0, f"Performer shot at {float(t0):.1f} s done")
    return {
        "clip": clip, "frames": int(best["frames"]), "seconds": best["frames"] / float(fps),
        "sync": best["sync"], "tries": tries, "steps": steps, "lora": lora,
        "render_s": round(best["render_s"], 1), "vram_gb": poller.peak_gb,
        "freeze_s": best["freeze_s"], "cuts": best["cuts"], "skip_frames": int(best.get("skip") or 0),
        "gone_frame": best.get("gone"), "leak_frames": int(best.get("leak_frames") or 0),
        "drift_frames": int(best.get("drift_frames") or 0), "room_frames": int(room),
        "pre_roll_s": round(pre_frames / float(fps), 3),
        "seed": best["seed"], "raw": best["raw"], "grid_frames": frames, "scores": scores, "prompt": prompt,
    }


__all__ = ["GRID", "FPS", "SIZE", "MIN_SECONDS", "POOR_SYNC", "LORA", "grid_frames", "available", "default_reference",
           "prompt_for", "performance_for", "render_slot", "sync_score", "estimate_seconds", "cut_audio", "fit_still",
           "finish_clip", "count_frames", "motion_energy", "grey_frames", "resemblance", "still_gone", "submit_shot"]
