"""Assemble a walkthrough from a plan (plan_short.json): one segment a scene, sized to its lines of the read with room
to breathe and ending on a beat of the bed (cutlib.timeline), each segment's picture made to that length, the voice
placed in each segment, the music bed ducked under it, captions burned in, the intro (the montage) in front.

    python assemble.py <plan.json> <voice read dir> <out.mp4>

Segment kinds ("pic"):
  screen   pieces of a recorded shot: [[in, out, speed, badge?], ...], times in the shot's own seconds or "mark+0.5";
           played still and full frame (no push-in: Tys, 29 Oct, "a bit of a shake and zoom on the app parts which we
           shouldnt do"), retimed a little to fill its segment rather than cut off mid-action
  three    three 9:16 videos side by side: [[path, in], ...]
  one      one 9:16 video over a blurred fill of itself: [path, in]
  wide     one 16:9 cut full frame: [path, in]; "land": true moves the in point so the segment ends on one of the
           cut's own shot boundaries (the last morph finishes its handoff as the segment cuts)
  grid     clips side by side with a label each: [[path, label], ...], played at "rate"
  card     a recorded card: [path, in]
  chain    several pics one after another: [[seconds or null, pic], ...] (null takes what is left)
  still    an image on the dark ground
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import cutlib

HERE = Path(__file__).parent
W, H, FPS = 1920, 1080, 30
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"
plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
read = Path(sys.argv[2])
out = Path(sys.argv[3])
work = HERE / f"build_{out.stem}"  # one folder an output: two builds at once must not share picture.mp4
work.mkdir(exist_ok=True)
lines = {r["id"]: r for r in json.loads((read / "lines.json").read_text(encoding="utf-8"))["lines"]}
copy = {r["id"]: r for r in json.loads(Path(plan["copy"]).read_text(encoding="utf-8"))["lines"]}


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def probe_len(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True).stdout.strip())


ENC = ["-an", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def at(value, marks):
    """A time in a shot: a number, or "mark", or "mark+0.5"."""
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"(.+?)([+-]\d+(?:\.\d+)?)?", value)  # mark names may hold hyphens (easy-copy-recipe-0.2)
    return marks[m.group(1)] + (float(m.group(2)) if m.group(2) else 0.0)


def retime(src, dur):
    """The setpts factor that makes a recording fill ``dur``: up to 1.5x faster rather than cut it off mid-action,
    down to 0.8x slower before its last frame is held (the screen at rest once the action is done)."""
    have = probe_len(src)
    return max(0.8, min(1.5, have / dur)) if have > 0 else 1.0


def badge(text):
    return (f"drawbox=x=(iw-360)/2:y=34:w=360:h=58:color=0x0c0b14@0.88:t=fill,"
            f"drawtext=fontfile='{FONT}':text='{text}':fontcolor=0xa99cff:fontsize=30:x=(w-tw)/2:y=50")


def pic_screen(spec, dur, dest):
    shot = HERE / "rec" / f"{spec['shot']}.mp4"
    marks = json.loads((HERE / "rec" / f"{spec['shot']}.json").read_text())["marks"]
    parts = []
    for k, piece in enumerate(spec["pieces"]):
        t0, t1, speed = at(piece[0], marks), at(piece[1], marks), float(piece[2])
        if t1 <= t0:
            continue
        vf = f"setpts=(PTS-STARTPTS)/{speed}"
        if len(piece) > 3 and piece[3]:
            vf += "," + badge(piece[3])
        p = work / f"{dest.stem}_p{k}.mp4"
        run(["-ss", f"{t0:.3f}", "-t", f"{t1 - t0:.3f}", "-i", str(shot), "-vf", vf + f",fps={FPS}", *ENC, str(p)])
        parts.append(p)
    joined = work / f"{dest.stem}_joined.mp4"
    concat(parts, joined)
    # a still, full-frame recording: no push-in (the per-frame scale jittered a pixel as it eased, and the push-ins
    # themselves are what Tys did not want)
    fit(joined, dur, dest, f"setpts=PTS/{retime(joined, dur):.4f},scale={W}:{H}:flags=lanczos")


def fit(src, dur, dest, vf="null"):
    """src to exactly dur seconds: trimmed, or its last frame held."""
    have = probe_len(src)
    pad = max(0.0, dur - have) + 1.0  # generous: a retimed source is shorter than its file says; trim cuts the rest
    run(["-i", str(src), "-vf", f"{vf},tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS",
         *ENC, str(dest)])


def concat(parts, dest):
    lst = work / f"{dest.stem}.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)])


def tall(path, t0, dur, w, h, label=None):
    """One 9:16 input chain scaled to w x h (inputs are added by the caller)."""
    return f"trim=start={t0:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},fps={FPS}"


def pic_three(spec, dur, dest):
    w, h, gap = 560, 996, 60
    x0 = (W - 3 * w - 2 * gap) // 2
    ins, fc = [], [f"color=c=0x0b0b0f:s={W}x{H}:d={dur:.3f}:r={FPS}[bg]"]
    for k, (path, t0) in enumerate(spec["videos"]):
        ins += ["-i", path]
        fc.append(f"[{k}:v]{tall(path, t0, dur, w, h)}[v{k}]")
    fc.append(f"[bg][v0]overlay={x0}:{(H - h) // 2}[a];[a][v1]overlay={x0 + w + gap}:{(H - h) // 2}[b];"
              f"[b][v2]overlay={x0 + 2 * (w + gap)}:{(H - h) // 2},trim=duration={dur:.3f}[out]")
    run([*ins, "-filter_complex", ";".join(fc), "-map", "[out]", *ENC, str(dest)])


def pic_one(spec, dur, dest):
    path, t0 = spec["video"]
    w, h = 608, 1080
    fc = (f"[0:v]trim=start={t0:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS,fps={FPS},split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=38,eq=brightness=-0.18:saturation=0.8[bg];"
          f"[b]scale={w}:{h}:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:0,trim=duration={dur:.3f}[out]")
    run(["-i", path, "-filter_complex", fc, "-map", "[out]", *ENC, str(dest)])


def pic_grid(spec, dur, dest):
    clips = spec["clips"]
    n = len(clips)
    gap = 28
    w = min(560, (W - 120 - gap * (n - 1)) // n) // 2 * 2
    h = int(w * 16 / 9) // 2 * 2
    x0 = (W - n * w - (n - 1) * gap) // 2
    y0 = (H - h - 70) // 2
    rate = float(spec.get("rate", 1.0))
    ins, fc = [], [f"color=c=0x0b0b0f:s={W}x{H}:d={dur:.3f}:r={FPS}[bg0]"]
    for k, (path, label) in enumerate(clips):
        ins += ["-i", path]
        t0 = float(spec.get("start", 0.0))
        fc.append(f"[{k}:v]trim=start={t0:.3f},setpts=(PTS-STARTPTS)/{rate},fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={w}:{h},tpad=stop_mode=clone:stop_duration={dur:.3f}[v{k}]")
    prev = "bg0"
    for k, (path, label) in enumerate(clips):
        x = x0 + k * (w + gap)
        fc.append(f"[{prev}][v{k}]overlay={x}:{y0}:shortest=0,drawtext=fontfile='{FONT}':text='{label}':fontcolor=0xececf1:fontsize=34:"
                  f"x={x}+({w}-tw)/2:y={y0 + h + 22}[bg{k + 1}]")
        prev = f"bg{k + 1}"
    fc.append(f"[{prev}]trim=duration={dur:.3f}[out]")
    run([*ins, "-filter_complex", ";".join(fc), "-map", "[out]", *ENC, str(dest)])


def pic_card(spec, dur, dest):
    path, t0 = spec["video"]
    src = work / f"{dest.stem}_src.mp4"
    run(["-ss", f"{t0:.3f}", "-i", path, "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}", *ENC, str(src)])
    fit(src, dur, dest)


def pic_chain(spec, dur, dest):
    parts, used = [], 0.0
    fixed = sum(s for s, _ in spec["parts"] if s)
    for k, (secs, sub) in enumerate(spec["parts"]):
        d = secs if secs else max(0.5, dur - fixed)
        p = work / f"{dest.stem}_c{k}.mp4"
        PICS[sub["pic"]](sub, d, p)
        parts.append(p)
        used += d
    concat(parts, dest)


def pic_still(spec, dur, dest):
    """A still image on the dark ground, fitted to "width" pixels, held still, with an optional label under it."""
    if spec.get("full"):  # the image is the whole frame (the montage's last frame with its title)
        run(["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-i", spec["image"], "-vf",
             f"scale={W}:{H}:flags=lanczos,fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS", *ENC, str(dest)])
        return
    w = int(spec.get("width", 1800))
    label = spec.get("label", "")
    text = (f",drawtext=fontfile='{FONT}':text='{label}':fontcolor=0x9a9aab:fontsize=32:x=(w-tw)/2:y=h/2+190" if label else "")
    fc = (f"color=c=0x0b0b0f:s={W}x{H}:d={dur:.3f}:r={FPS}[bg];[0:v]scale={w}:-2:flags=lanczos,format=rgba[im];"
          f"[bg][im]overlay=(W-w)/2:(H-h)/2-40{text},trim=duration={dur:.3f}[out]")
    run(["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-i", spec["image"], "-filter_complex", fc, "-map", "[out]", *ENC, str(dest)])


def pic_wide(spec, dur, dest):
    """A 16:9 cut full frame from t0, cover-cropped; "fade" seconds fade it to black at the end (a dip into the next screen)."""
    path, t0 = spec["video"]
    if spec.get("land"):
        t0 = cutlib.land(path, t0, dur, spec.get("period"))
    fade = float(spec.get("fade", 0.0))
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={dur + 0.2:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS")
    if spec.get("label"):  # what the cut shows off, as a chip at the top ("Shatter · Snap")
        vf += "," + badge(spec["label"])
    if fade > 0:
        vf += f",fade=t=out:st={max(0.0, dur - fade):.3f}:d={fade:.3f}"
    run(["-ss", f"{t0:.3f}", "-t", f"{dur + 0.3:.3f}", "-i", path, "-vf", vf, *ENC, str(dest)])


PICS = {"screen": pic_screen, "three": pic_three, "one": pic_one, "grid": pic_grid, "card": pic_card, "chain": pic_chain,
        "still": pic_still, "wide": pic_wide}


def captions(segs):
    """ASS captions: each line split at its clauses into chunks of about 64 characters, timed by their share of the line."""
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,Segoe UI Semibold,44,&H00F1ECEC,&H00FFFFFF,&H28140B0C,&H28140B0C,0,0,0,0,100,100,0,0,3,14,0,2,200,200,54,1\n"
            "Style: Chap,Segoe UI Semibold,38,&H00FF8894,&H00FFFFFF,&H14140B0C,&H14140B0C,0,0,0,0,100,100,1,0,3,14,0,8,56,56,74,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

    def ts(t):
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    rows, chapters = [], []
    for s in segs:
        # a chapter label, top left, as each new chapter starts (the long walkthrough's copy names them)
        chapter = copy[s["id"]].get("chapter")
        if chapter and chapter not in chapters and chapter != "End":
            chapters.append(chapter)
            rows.append(f"Dialogue: 1,{ts(s['start'] + 0.2)},{ts(s['start'] + 3.6)},Chap,,0,0,0,,{{\\fad(250,450)}}{len(chapters)} · {chapter}")
        for i, start in s["voices"]:
            text, spoken = copy[i]["text"], lines[i]["seconds"]
            chunks = blocks(text)
            total = sum(len(c) for c in chunks)
            t = start
            for c in chunks:
                d = spoken * len(c) / total
                # no overlap: a caption that starts while the last one shows is stacked a line higher by libass for its
                # whole life (seen in the 9:16 cut, into a grid and the card's chips)
                rows.append(f"Dialogue: 0,{ts(t)},{ts(t + d - 0.02)},Cap,,0,0,0,,{two_lines(c)}")
                t += d
    return head + "\n".join(rows) + "\n"


BLOCK = 96  # characters a caption holds, on two lines


def pieces(text, marks):
    """Split after any of the marks (". ", ": ", ", "), keeping them."""
    out, cur = [], ""
    for word in text.split(" "):
        cur = f"{cur} {word}".strip()
        if cur.endswith(marks):
            out.append(cur)
            cur = ""
    return out + ([cur] if cur else [])


def blocks(text):
    """Captions for one line: whole sentences merged up to BLOCK characters; a longer sentence split at its commas."""
    units = []
    for sentence in pieces(text, (".", ":", "?", "!")):
        if len(sentence) <= BLOCK:
            units.append(sentence)
            continue
        cur = ""
        for clause in pieces(sentence, (",",)):
            if cur and len(cur) + 1 + len(clause) > BLOCK:
                units.append(cur)
                cur = clause
            else:
                cur = f"{cur} {clause}".strip()
        units.append(cur)
    out = []
    for u in units:
        if out and (len(out[-1]) + 1 + len(u) <= BLOCK or len(out[-1]) < 24):
            out[-1] = f"{out[-1]} {u}"
        else:
            out.append(u)
    return out


def two_lines(text):
    """One line up to 52 characters, else two balanced lines, breaking after a comma near the middle when there is one."""
    text = re.sub(r"(\d) (GB|MB|s)\b", lambda m: m.group(1) + "\u00a0" + m.group(2), text)  # a number keeps its unit
    if len(text) <= 56:
        return text
    words = text.split(" ")
    best, best_cost = 1, 1e9
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        cost = abs(len(a) - len(b)) - (20 if a.endswith((",", ":", ".")) else 0)
        if cost < best_cost:
            best, best_cost = k, cost
    return " ".join(words[:best]) + "\\N" + " ".join(words[best:])


def main():
    segs, total = cutlib.timeline(plan, lines)
    print(f"{len(segs)} segments, {total:.1f} s", flush=True)
    parts = []
    for k, s in enumerate(segs):
        dest = work / f"seg{k:02d}_{s['id']}.mp4"
        PICS[s["pic"]["pic"]](s["pic"], s["dur"], dest)
        got = probe_len(dest)
        print(f"  {s['id']:9} {s['start']:6.2f} +{s['dur']:5.2f} s (made {got:.2f})", flush=True)
        parts.append(dest)
    picture = work / "picture.mp4"
    cutlib.join_exact(parts, [s["dur"] for s in segs], picture)
    mix, af = cutlib.mix(plan, segs, total, read, work)
    ass = work / "captions.ass"
    ass.write_text(captions(segs), encoding="utf-8")
    intro = cutlib.finish(plan, picture, mix, af, ass, out, work, (W, H))
    (out.with_suffix(".json")).write_text(json.dumps({"seconds": round(intro + total, 2), "intro": round(intro, 2), "segments": [
        {**{k: s[k] for k in ("id", "dur")}, "start": round(intro + s["start"], 3), "voice_at": round(intro + s["voice_at"], 3)}
        for s in segs]}, indent=1), encoding="utf-8")
    print("wrote", out, round(intro + total, 1), "s", flush=True)


main()
