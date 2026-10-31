"""The whole song laid together (docs/MUSIC_VIDEO_PLAN.md section 7; docs/SONG.md).

What ``docs/demo/tools/montage.py`` did by hand for the Glitch Out video of 29 Oct, done from the song's record: every
window's cut laid end to end by song time, so its picture plays over the very seconds it was made on (its beat FX land
on the song's own hits), each cut between two windows on a beat of the song's own grid (``place``: a passage's start is
pinned, the cut inside a passage goes where the outgoing morph has landed, then on beat 1, then on beat 3, and only
where both windows have picture), a window that plays a stretch shifted by whole beats checked against its picture
(``check``), the flash tame once over the whole when Breathe is on (``deflash.Tame`` with each passage's rule), the title
on the song's last hit (the hand-made video's "Xenoform" at 3:51), the song itself as the sound at -16 LUFS, and the QA
pass once over the whole.

No GPU: ``assemble`` reads the windows' finished cuts and their records, so a passage re-cut on its own timeline (or a
morph re-rendered there) is laid in again by assembling once more. It writes ``xenoform.mp4``, ``simple/simple.json``
(every shot in song time, each with its passage, its window's job and its vibe: the desk's timeline and Edit in Resolve
read it), ``meta.json`` (My videos) and the record's ``assembly`` block: the cuts and why each fell where it did, the
loudness, the tame and the QA.
"""
from __future__ import annotations

import copy
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("xenoform.song")

FPS = 24
TARGET_LUFS = -16.0
CEILING_DB = -3.0          # the limiter's ceiling after the gain (the montage's: cutlib.loudnorm)
NEAR_S = 1.4               # a cut moves at most this far from where the plan wanted it (montage.place)
TITLE_DIM_S = 0.3          # the shot dims under the title over this long, the title fades in a quarter second
TITLE_IN_S = 0.25
END_FADE_S = 1.2           # the picture fades out over the song's last 1.2 s, the sound over its last 2.2
SOUND_FADE_S = 2.2
SMALL_MIB = 24.5           # the shareable copy stays under 25 MiB
SMALL_HEIGHT = 720
CRF = 16


class AssemblyError(RuntimeError):
    """A window's cut is missing, or a slot asks for picture its window does not have."""


def _ffmpeg() -> str:
    from xenoform.video import ffmpeg_bin

    return ffmpeg_bin()


def _ffprobe() -> str:
    from xenoform.video import ffprobe_bin

    return ffprobe_bin()


def _run(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run([_ffmpeg(), "-v", "error", "-y", *args], check=True, **kw)


def probe(path: Path) -> dict:
    """A cut's picture size, rate, frame count and length."""
    raw = subprocess.run([_ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    data = json.loads(raw)
    s = (data.get("streams") or [{}])[0]
    num, _, den = str(s.get("r_frame_rate") or "24/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    dur = float((data.get("format") or {}).get("duration") or 0.0)
    nb = str(s.get("nb_frames") or "")
    return {"width": int(s.get("width") or 0), "height": int(s.get("height") or 0), "fps": fps,
            "frames": int(nb) if nb.isdigit() else int(round(dur * fps)), "seconds": dur}


# ------------------------------------------------------------------------------------------------ the slots


def slots(rec: dict, jobs: Path) -> list[dict]:
    """Each window's cut as the assembly lays it: its job folder, where its picture sits in the song (its record's
    ``window``, else the plan's), its length, its shot boundaries in song time and the beats it may be shifted by."""
    out = []
    for w in rec["windows"]:
        job = str(w.get("job_id") or "")
        if w.get("status") != "done" or not job:
            raise AssemblyError(f"Window {w['index'] + 1} has no finished cut yet ({w.get('status') or 'queued'}).")
        folder = Path(jobs) / job
        mp4 = folder / "xenoform.mp4"
        try:
            cut = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AssemblyError(f"Window {w['index'] + 1}'s cut ({job}) has no record: render it again.") from exc
        if not mp4.is_file():
            raise AssemblyError(f"Window {w['index'] + 1}'s cut ({job}) is not on this machine.")
        info = probe(mp4)
        win = cut.get("window") if isinstance(cut.get("window"), dict) else {}
        offset = float(win.get("song_start") if win.get("song_start") is not None else w["start"])
        shift = float(w.get("shift_beats") or 0.0)
        shots = list(cut.get("shots") or [])
        bounds = sorted({round(offset + float(s.get("start") or 0.0), 4) for s in shots}
                        | {round(offset + float(s.get("end") or 0.0), 4) for s in shots})
        out.append({"window": w["index"], "passage": w["passage"], "part": int(w.get("part") or 0), "job": job,
                    "mp4": mp4, "record": cut, "info": info, "offset": offset, "seconds": info["seconds"],
                    "end": offset + info["seconds"], "bounds": bounds, "shift_beats": shift, "start": float(w["start"]),
                    "want_end": float(w["end"])})
    return out


def _period(beats: list[float]) -> float:
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    return float(gaps[len(gaps) // 2]) if gaps else 0.5


def shifted(slot: dict, period: float) -> tuple[float, float]:
    """The song time a slot's cut starts and runs out at, its shift in whole beats applied (a later stretch of the cut
    plays for a positive shift: its offset moves earlier, so its beat FX still land on the song's beats)."""
    s = float(slot.get("shift_beats") or 0.0) * period
    return slot["offset"] - s, slot["end"] - s


def place(a: dict, b: dict, want: float, beats: list[float], *, pin: bool, period: float, phase: int = 0) -> dict:
    """The cut from slot ``a`` into slot ``b`` (montage.place): always on a beat of the song's own grid, within ``NEAR_S``
    of where the plan wanted it, only where ``a``'s picture still runs and ``b``'s has begun. ``pin`` (a passage's start,
    a section start): the beat nearest the plan's. Else a beat where ``a``'s morph has just landed scores best (it ends
    its handoff), then one where ``b``'s starts, then beat 1, then beat 3. Where the two windows only meet (they were
    made end to end), the cut is where they meet. Returns the time and why."""
    a0, a1 = shifted(a, period)
    b0, b1 = shifted(b, period)
    lo, hi = b0 + 0.05, a1 - 0.05
    near = [t for t in beats if abs(t - want) <= NEAR_S and lo <= t <= hi]

    def bar_pos(t: float) -> int:
        if not beats:
            return 0
        i = min(range(len(beats)), key=lambda j: abs(beats[j] - t))
        return (i - phase) % 4 + 1 if abs(beats[i] - t) < 0.06 else 0

    def hit(t: float, xs: list[float], tol: float = 0.2) -> bool:
        return any(abs(t - x) <= tol for x in xs)

    def reason(t: float) -> str:
        if pin:
            return "a passage starts: pinned on its beat"
        if hit(t, a["bounds"], 0.05):
            return "the outgoing morph lands"
        if hit(t, b["bounds"], 0.05):
            return "the incoming morph starts"
        pos = bar_pos(t)
        return "beat 1" if pos == 1 else "beat 3" if pos == 3 else "the nearest beat"

    if not near:  # the two windows were made end to end: the cut is where they meet, on the plan's own beat (an outgoing
        meet = min(max(want, b0), a1 + PAD_S)  # window a few frames short is padded to it, not cut early)
        return {"at": round(meet, 4), "want": round(want, 4), "why": reason(meet), "beat": bar_pos(meet), "pinned": pin,
                "met": True}
    if pin:
        t = min(near, key=lambda x: abs(x - want))
        return {"at": round(t, 4), "want": round(want, 4), "why": reason(t), "beat": bar_pos(t), "pinned": True}

    def score(t: float) -> float:
        s = 2.5 * hit(t, a["bounds"]) + 1.5 * hit(t, b["bounds"]) - 1.0 * abs(t - want)
        pos = bar_pos(t)
        return s + (1.5 if pos == 1 else 0.7 if pos == 3 else 0.0)

    t = max(near, key=score)
    return {"at": round(t, 4), "want": round(want, 4), "why": reason(t), "beat": bar_pos(t), "pinned": False}


def check(order: list[dict], cuts: list[float], period: float) -> list[str]:
    """The window checked (montage_check): each slot plays a stretch its cut has, its shift applied (a cut that came out
    up to ``PAD_S`` short at its end is held on its last frame); the problems as sentences ([] when every slot is
    covered)."""
    bad = []
    for k, s in enumerate(order):
        a, b = cuts[k], cuts[k + 1]
        c0, c1 = shifted(s, period)
        if a < c0 - 0.01 or b > c1 + PAD_S + 0.01:
            shift = f", shifted {s['shift_beats']:+.0f} beats" if s.get("shift_beats") else ""
            bad.append(f"window {s['window'] + 1} runs {c0:.2f} to {c1:.2f} in the song{shift}; its slot asks {a:.2f} to {b:.2f}")
    return bad


# ------------------------------------------------------------------------------------------------ the composite record


def song_shots(order: list[dict], cuts: list[float], rec: dict, period: float) -> tuple[list[dict], list[str], list[str]]:
    """Every shot the song plays, in song time: each window's shots clipped to the stretch its slot plays, with its
    passage, window, job and vibe, its morph pointing into the song's stills (each window's in turn), the first shot of
    every window after the first a hard cut (``cut_in``). Returns the shots, the stills and the styles a shot."""
    shots, stills, styles = [], [], []
    for k, s in enumerate(order):
        cut = s["record"]
        c0, _ = shifted(s, period)
        a, b = cuts[k], cuts[k + 1]
        base = len(stills)
        mine = [str(f) for f in cut.get("stills") or []]
        stills += mine
        style_of = list(cut.get("morph_styles") or [])
        p = rec["passages"][s["passage"]]
        look = p.get("look") or {}
        first = True
        for i, sh in enumerate(cut.get("shots") or []):
            t0, t1 = c0 + float(sh.get("start") or 0.0), c0 + float(sh.get("end") or 0.0)
            if t1 <= a + 1e-6 or t0 >= b - 1e-6:
                continue
            row = copy.deepcopy(sh)
            row["start"], row["end"] = round(max(t0, a), 4), round(min(t1, b), 4)
            row["seconds"] = round(row["end"] - row["start"], 4)
            row["frames"] = int(round(row["end"] * FPS)) - int(round(row["start"] * FPS))
            m = int(sh.get("morph", sh.get("clip", i)) or 0)
            row["morph"] = base + m
            row.update({"window": s["window"], "song_passage": s["passage"], "job": s["job"], "vibe": look.get("vibe") or cut.get("vibe") or "",
                        "look_name": look.get("name") or "", "shot_in_window": i})
            row.pop("clip", None)
            if first and k > 0:
                row["cut_in"] = True  # a new window: a hard cut on the song's beat
                if not s["part"]:
                    row["boundary"] = "passage"
            first = False
            shots.append(row)
            styles.append(style_of[i] if i < len(style_of) else "melt")
    return shots, stills, styles


def composite(rec: dict, order: list[dict], cuts: list[float], *, video_s: float, size: tuple[int, int], period: float,
              beats: list[float]) -> dict:
    """``simple/simple.json`` for the song: what the timeline (``lane.build``), Edit in Resolve (``edit_export``) and My
    videos read. ``mode`` "song": a re-cut goes passage by passage (each window's own timeline), then a re-assemble."""
    shots, stills, styles = song_shots(order, cuts, rec, period)
    clips = []
    for s in order:
        cut = s["record"]
        for sh_clip in cut.get("clips") or []:
            clips.append(str(sh_clip))
    first = order[0]["record"] if order else {}
    return {"mode": "song", "song_id": rec["id"], "engine": first.get("engine") or "", "tier": first.get("tier") or rec.get("tier"),
            "aspect": first.get("aspect") or rec.get("aspect"), "fast": bool(first.get("fast")), "cloud": bool(first.get("cloud")),
            "vibe": "", "vibes": [(p.get("look") or {}).get("vibe") or "" for p in rec["passages"]],
            "stills": stills, "shots": shots, "plan_shots": copy.deepcopy(shots), "morph_styles": styles,
            "clips": clips if len(clips) == len(shots) else [], "plan_name": "song",
            "transitions": [None] * len(shots), "boundary_fx": [None] * len(shots),
            "audio_path": (rec.get("song") or {}).get("path") or "", "beats": beats, "drop": (rec.get("song") or {}).get("drop"),
            "fps": FPS, "size": list(size), "frames": int(round(video_s * FPS)), "seconds": round(video_s, 3),
            "window": {"song_start": 0.0, "length_s": round(video_s, 3)},
            "pacing": {"breathe": rec.get("breathe"), "drop_mode": rec.get("drop_mode"), "line": (rec.get("plan") or {}).get("line")},
            "recut_state": {"breathe": rec.get("breathe"), "drop_mode": rec.get("drop_mode")},
            "song": {"id": rec["id"], "passages": [{"index": p["index"], "role": p["role"], "start": p["start"], "end": p["end"],
                                                   "vibe": (p.get("look") or {}).get("vibe") or "", "name": (p.get("look") or {}).get("name") or "",
                                                   "preset": (p.get("look") or {}).get("preset") or "",
                                                   "objects": p.get("objects") or [], "windows": p.get("windows") or [],
                                                   "jobs": [rec["windows"][k].get("job_id") or "" for k in p.get("windows") or []]}
                                                  for p in rec["passages"]]}}


# ------------------------------------------------------------------------------------------------ the title


def title_png(text: str, size: tuple[int, int], dest: Path) -> Path | None:
    """The hand-made video's title card (docs/demo/tools/cards/title.html: the word in Space Grotesk 700 with a violet
    glow and a soft shadow) as a transparent PNG the size of the picture; None for no title."""
    text = str(text or "").strip()
    if not text:
        return None
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    w, h = int(size[0]), int(size[1])
    scale = min(w / 1920.0, h / 1080.0) if w >= h else w / 1080.0
    px = max(24, int(round((156 if w >= h else 132) * scale)))
    font_file = Path(__file__).resolve().parent / "ui_static" / "fonts" / "space-grotesk-700.woff2"
    try:
        font = ImageFont.truetype(str(font_file), px)
    except OSError:
        font = ImageFont.load_default()
    box = font.getbbox(text)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = (w - tw) // 2 - box[0], (h - th) // 2 - box[1]
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glow).text((x, y), text, font=font, fill=(124, 108, 255, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(max(4, px // 4)))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x, y + max(2, px // 40)), text, font=font, fill=(0, 0, 0, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(3, px // 7)))
    card = Image.alpha_composite(glow, shadow)
    ImageDraw.Draw(card).text((x, y), text, font=font, fill=(244, 242, 255, 255))
    dest.parent.mkdir(parents=True, exist_ok=True)
    card.save(dest)
    return dest


# ------------------------------------------------------------------------------------------------ the sound


def loudness(path: Path, target: float = TARGET_LUFS) -> dict:
    """``loudnorm``'s measurement of a file (integrated loudness, true peak)."""
    err = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path), "-af", f"loudnorm=I={target}:TP=-2.5:LRA=11:print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    return json.loads(err[err.rindex("{"):err.rindex("}") + 1])


def level_filter(path: Path, target: float = TARGET_LUFS) -> tuple[str, float]:
    """The filter that levels the song to ``target`` LUFS with its peaks under ``CEILING_DB``: a fixed gain from the
    measured loudness, then a delay-compensated peak limiter (cutlib.loudnorm: loudnorm's own second pass drifts the
    sound when it leaves linear mode). Returns the filter and the gain."""
    m = loudness(path, target)
    gain = target - float(m["input_i"])
    return (f"volume={gain:.2f}dB,alimiter=limit={10 ** (CEILING_DB / 20):.4f}:attack=2:release=60:level=false:latency=true,"
            f"aresample=48000"), gain


def measured_lufs(path: Path) -> dict:
    """The finished file's integrated loudness and true peak (ebur128), to check the target was met."""
    err = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    tail = err[err.rfind("Integrated loudness"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    p = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return {"lufs": float(i.group(1)) if i else None, "true_peak_db": float(p.group(1)) if p else None}


# ------------------------------------------------------------------------------------------------ the picture


def _flash_rules(shots: list[dict], rec: dict, beats: list[float]) -> list | None:
    """The tame's rule a frame over the whole song (``pacing.flash_rules`` on the song's shots), Breathe on only."""
    from xenoform import pacing

    if not pacing.breathe_of({"breathe": rec.get("breathe")}):
        return None
    return pacing.flash_rules(shots, FPS, beats, breathe=pacing.amount_of(rec.get("breathe")))


PAD_S = 0.25  # a window cut up to this short (a QA lag fix drops trailing held frames) is padded with its last frame


def lay_picture(order: list[dict], cuts: list[float], size: tuple[int, int], dest: Path, period: float) -> int:
    """The windows' stretches end to end, silent, at ``FPS`` and ``size``, each frame-exact: ``trim`` on exactly the
    frames the slot plays, a window that came out a frame or three short padded with its own last frame first (else
    every window after it would play that much early against the song). Returns the frame count."""
    w, h = size
    frames = [int(round(c * FPS)) for c in cuts]
    args: list[str] = []
    parts = []
    for k, s in enumerate(order):
        n = frames[k + 1] - frames[k]
        if n <= 0:
            continue
        c0, _ = shifted(s, period)
        f0 = int(round((cuts[k] - c0) * FPS))
        args += ["-i", str(s["mp4"])]
        idx = len(parts)
        parts.append(f"[{idx}:v]fps={FPS},tpad=stop_mode=clone:stop_duration={PAD_S},trim=start_frame={f0}:end_frame={f0 + n},"
                     f"setpts=PTS-STARTPTS,"
                     f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1,format=yuv420p[v{idx}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[pic]"
    _run([*args, "-filter_complex", graph, "-map", "[pic]", "-an", "-c:v", "libx264", "-crf", "12", "-preset", "veryfast",
          "-r", str(FPS), "-pix_fmt", "yuv420p", str(dest)])
    return frames[-1] - frames[0]


def finish(picture: Path, song: Path, dest: Path, *, size: tuple[int, int], video_s: float, title_at: float | None,
           title: Path | None, rules: list | None, report: Callable | None = None) -> dict:
    """The picture through the flash tame (frame by frame, when ``rules``), the title over the shot from its hit, the end
    faded out, the song under it from its first second levelled to -16 LUFS. Returns what the tame did and the gain."""
    from xenoform import deflash

    w, h = size
    total = float(video_s)
    work = dest.parent
    wav = work / "song.wav"
    _run(["-ss", "0", "-t", f"{total:.4f}", "-i", str(song), "-af",
          f"afade=t=in:d=0.03,afade=t=out:st={max(0.0, total - SOUND_FADE_S):.3f}:d={SOUND_FADE_S}", "-ar", "48000", "-ac", "2",
          str(wav)])
    af, gain = level_filter(wav)
    fc = []
    inputs = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-"]
    if title is not None and title_at is not None and 0 < title_at < total:
        t = float(title_at)
        inputs += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(title)]
        fc.append(f"[0:v]eq=brightness='-0.42*clip((t-{t:.3f})/{TITLE_DIM_S},0,1)':saturation='1-0.4*clip((t-{t:.3f})/{TITLE_DIM_S},0,1)'"
                  f":eval=frame[d];[1:v]format=rgba,fade=t=in:st={t:.3f}:d={TITLE_IN_S}:alpha=1[t];"
                  f"[d][t]overlay=0:0:enable='gte(t,{t:.3f})',fade=t=out:st={max(0.0, total - END_FADE_S):.3f}:d={END_FADE_S},format=yuv420p[v]")
        audio_in = 2
    else:
        fc.append(f"[0:v]fade=t=out:st={max(0.0, total - END_FADE_S):.3f}:d={END_FADE_S},format=yuv420p[v]")
        audio_in = 1
    inputs += ["-i", str(wav)]
    fc.append(f"[{audio_in}:a]{af}[a]")
    enc = subprocess.Popen([_ffmpeg(), "-v", "error", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                            "-c:v", "libx264", "-crf", str(CRF), "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS),
                            "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(dest)],
                           stdin=subprocess.PIPE)
    dec = subprocess.Popen([_ffmpeg(), "-v", "error", "-i", str(picture), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    tame = deflash.Tame() if rules else None
    frame_bytes = w * h * 3
    i = 0
    total_frames = int(round(total * FPS))
    try:
        while True:
            buf = dec.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            if tame is None:
                enc.stdin.write(buf)
            else:
                frame = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
                for out in tame.push(frame, rules[i] if i < len(rules) else None):
                    enc.stdin.write(np.ascontiguousarray(out).tobytes())
            i += 1
            if report and i % (FPS * 10) == 0:
                report("assemble", 0.55 + 0.35 * i / max(1, total_frames), f"Laying the song together: {i // FPS} s of {int(total)} s")
        if tame is not None:
            for out in tame.flush():
                enc.stdin.write(np.ascontiguousarray(out).tobytes())
    finally:
        enc.stdin.close()
        enc.wait()
        dec.wait()
    if enc.returncode:
        raise AssemblyError("The song's encode failed.")
    return {"frames": i, "gain_db": round(gain, 2), "tame": tame.info() if tame is not None else None}


def small_copy(src: Path, dest: Path, *, max_mib: float = SMALL_MIB, height: int = SMALL_HEIGHT) -> Path:
    """A copy to share, under ``max_mib`` (25 MiB: a post or a message takes it) at ``height`` lines: a bitrate from the
    length, checked after and made again a fifth smaller if it came out over."""
    info = probe(src)
    secs = max(1.0, float(info["seconds"]))
    audio_k = 128
    for factor in (0.92, 0.75, 0.6):
        video_k = max(300, int((max_mib * 8 * 1024 * 1024 / secs / 1000.0 - audio_k) * factor))
        _run(["-i", str(src), "-vf", f"scale=-2:{int(height)}:flags=lanczos", "-c:v", "libx264", "-b:v", f"{video_k}k",
              "-maxrate", f"{int(video_k * 1.3)}k", "-bufsize", f"{int(video_k * 2)}k", "-preset", "medium", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", f"{audio_k}k", "-movflags", "+faststart", str(dest)])
        if dest.stat().st_size <= max_mib * 1024 * 1024:
            return dest
    return dest


# ------------------------------------------------------------------------------------------------ the whole


def assemble(folder: Path, jobs: Path, *, report: Callable[[str, float, str], None] | None = None, qa: bool = True) -> dict:
    """Lay the song together from its record (``song_run``) and its windows' finished cuts: the cuts placed and checked,
    the picture, the tame, the title, the sound, the QA, the composite record and My videos' meta. Returns the record
    with its ``assembly`` block (``error`` and nothing written when a window is missing or a slot runs out of picture)."""
    from xenoform import job_timing, post_qa, song_run
    from xenoform.turbo import publish_file

    folder, jobs = Path(folder), Path(jobs)
    rec = song_run.load(folder)
    if rec is None:
        raise AssemblyError("No song record here.")
    say = report or (lambda *a: None)
    started = time.time()
    say("assemble", 0.02, "Reading the passages' cuts")
    order = slots(rec, jobs)
    song_path = Path((rec.get("song") or {}).get("path") or "")
    if not song_path.is_file():
        raise AssemblyError("The song file is gone: load it again.")
    duration = float((rec.get("song") or {}).get("duration") or order[-1]["end"])
    from xenoform import pacing

    song_beats = _song_beats(rec, order)
    period = _period(song_beats)
    phase = int((rec.get("plan") or {}).get("bar_phase") or 0)
    grid = pacing.grid_for(song_beats, duration, (rec.get("song") or {}).get("tempo"))
    # the cuts: the song's start, each boundary placed on the grid, the song's end
    cuts_info = []
    cuts = [0.0]
    for a, b in zip(order, order[1:]):
        got = place(a, b, b["start"], grid, pin=not b["part"], period=period, phase=phase)
        got.update({"into_window": b["window"], "into_passage": b["passage"]})
        cuts_info.append(got)
        cuts.append(float(got["at"]))
    video_s = min(duration, max(shifted(order[-1], period)[1], cuts[-1] + 0.5))
    cuts.append(round(video_s, 4))
    problems = check(order, cuts, period)
    if problems:
        rec["assembly"] = {"error": "A window does not cover its slot: " + "; ".join(problems), "cuts": cuts_info,
                           "made": datetime_now()}
        song_run.save(folder, rec)
        raise AssemblyError(rec["assembly"]["error"])
    size = (order[0]["info"]["width"], order[0]["info"]["height"])
    say("assemble", 0.1, f"Laying {len(order)} windows end to end on the song's beats")
    work = folder / "assembly"
    work.mkdir(parents=True, exist_ok=True)
    picture = work / "picture.mp4"
    lay_picture(order, cuts, size, picture, period)
    shots, _, _ = song_shots(order, cuts, rec, period)
    rules = _flash_rules(shots, rec, song_beats)
    title = rec.get("title") or {}
    card = title_png(str(title.get("text") or ""), size, work / "title.png")
    tmp = work / "song.mp4"
    say("assemble", 0.55, "The flash tame, the title and the song" if rules else "The title and the song")
    made = finish(picture, song_path, tmp, size=size, video_s=video_s, title_at=title.get("at"), title=card, rules=rules,
                  report=say)
    publish_file(tmp, folder / "xenoform.mp4")
    out = folder / "xenoform.mp4"
    say("assemble", 0.92, "Checking the loudness and the QA")
    level = measured_lufs(out)
    qa_rep = None
    if qa:
        try:
            qa_rep = post_qa.run(out, fps=float(FPS), beats=song_beats, fix=False)
        except Exception as exc:  # the QA is a report: a failed check never loses the song
            qa_rep = {"error": str(exc)[:200]}
    comp = composite(rec, order, cuts, video_s=video_s, size=size, period=period, beats=[round(b, 4) for b in song_beats])
    (folder / "simple").mkdir(exist_ok=True)
    (folder / "simple" / "simple.json").write_text(json.dumps(comp, indent=1, default=str), encoding="utf-8")
    _write_meta(folder, rec)
    took = round(time.time() - started, 1)
    renders = round(sum(float(w.get("took_s") or 0.0) for w in rec["windows"]), 1)
    job_timing.write_took(folder, {"took_s": round(renders + took, 1), "assembly_s": took, "windows_s": renders})
    rec["assembly"] = {"video": "xenoform.mp4", "made": datetime_now(), "seconds": round(video_s, 3), "took_s": took,
                       "size": list(size), "fps": FPS, "cuts": cuts_info, "frames": made["frames"],
                       "loudness": {"target": TARGET_LUFS, "gain_db": made["gain_db"], **level},
                       "tame": made["tame"], "title": {"text": title.get("text"), "at": title.get("at")},
                       "qa": _qa_summary(qa_rep), "windows": [{"window": s["window"], "job": s["job"], "song_start": s["offset"],
                                                                "seconds": round(s["seconds"], 3), "shift_beats": s["shift_beats"],
                                                                "padded_frames": _short(s, cuts, k, period)}
                                                               for k, s in enumerate(order)]}
    song_run.save(folder, song_run.stamp(rec, status="done"))
    say("done", 1.0, f"The whole song is laid together: {int(video_s // 60)}:{int(video_s % 60):02d}")
    return rec


def _short(slot: dict, cuts: list[float], k: int, period: float) -> int:
    """How many frames the slot's window lacked at its end (padded with its last frame by ``lay_picture``)."""
    c0, _ = shifted(slot, period)
    f0 = int(round((cuts[k] - c0) * FPS))
    n = int(round(cuts[k + 1] * FPS)) - int(round(cuts[k] * FPS))
    return max(0, f0 + n - int(slot["info"]["frames"]))


def _song_beats(rec: dict, order: list[dict]) -> list[float]:
    """The song's own beats: the record's (written when the song was queued), else every window's laid back where it
    sits in the song."""
    beats = [float(b) for b in (rec.get("song") or {}).get("beats") or []]
    if beats:
        return beats
    out = {round(float(s["offset"]) + float(b), 4) for s in order for b in s["record"].get("beats") or []}
    return sorted(out)


def _qa_summary(rep: dict | None) -> dict | None:
    if not isinstance(rep, dict):
        return None
    veil = rep.get("veil") or {}
    beats = rep.get("beats") or {}
    return {"issues": list(rep.get("issues") or [])[:12], "flash_frames": veil.get("flash_frames"),
            "max_flash_8_bars": veil.get("max_8_bars"), "per_8_bars": veil.get("per_8_bars"),
            "off_beat": len(beats.get("off_beat") or []) if isinstance(beats, dict) else None,
            "hard_flashes": (rep.get("flashes") or {}).get("flashes")}


def _write_meta(folder: Path, rec: dict) -> None:
    meta = {"created": rec.get("created") or datetime_now(), "simple": True, "whole_song": True, "song_id": rec["id"],
            "audio_id": (rec.get("song") or {}).get("audio_id") or "",
            "song": f"{(rec.get('song') or {}).get('label') or 'Song'} · whole song", "vibe": "",
            "energy_preset": "dense", "aspect": rec.get("aspect") or "16:9", "quality_tier": rec.get("tier") or "draft", "recipe": ""}
    (Path(folder) / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


def datetime_now() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")
