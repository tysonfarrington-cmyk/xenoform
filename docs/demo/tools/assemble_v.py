"""The 9:16 cut of a walkthrough for the post (Tys, 29 Oct: "May as well do a 9:16 cut as well"), from the same plan and
read as assemble.py, laid out for a phone: the 9:16 cuts play full frame; the three opening cuts play one after
another full frame; the desk recordings (still, no push-in) sit as a 1080x608 strip high in the frame over their own
blur, the captions large beneath them; grids go two columns; the cards use their vertical recordings
(rec/<name>_v.mp4) when they exist. Same timeline (cutlib: the breaths, the ends on the bed's beats), voice, bed,
ducking, loudness and intro as the 16:9 cut.

    python assemble_v.py <plan.json> <voice read dir> <out.mp4>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import cutlib

HERE = Path(__file__).parent
W, H, FPS = 1080, 1920, 30
SW, SH = 1920, 1080  # the recordings' own size
STRIP_W, STRIP_H = 1080, 608
STRIP_Y = 420  # the strip's top: the captions sit under it, the lower third stays clear
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"
plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
read = Path(sys.argv[2])
out = Path(sys.argv[3])
work = HERE / f"build_v_{out.stem}"
work.mkdir(exist_ok=True)
lines = {r["id"]: r for r in json.loads((read / "lines.json").read_text(encoding="utf-8"))["lines"]}
copy = {r["id"]: r for r in json.loads(Path(plan["copy"]).read_text(encoding="utf-8"))["lines"]}


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def probe_len(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True).stdout.strip())


ENC = ["-an", "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS)]
GROUND = f"color=c=0x0b0b0f:s={W}x{H}:d={{dur:.3f}}:r={FPS}"


def at(value, marks):
    if isinstance(value, (int, float)):
        return float(value)
    m = re.fullmatch(r"(.+?)([+-]\d+(?:\.\d+)?)?", value)
    return marks[m.group(1)] + (float(m.group(2)) if m.group(2) else 0.0)


def retime(src, dur):
    """As assemble.py: up to 1.5x faster to fill the segment rather than cut off mid-action, down to 0.8x slower."""
    have = probe_len(src)
    return max(0.8, min(1.5, have / dur)) if have > 0 else 1.0


def badge(text):
    return (f"drawbox=x=(iw-360)/2:y=34:w=360:h=58:color=0x0c0b14@0.88:t=fill,"
            f"drawtext=fontfile='{FONT}':text='{text}':fontcolor=0xa99cff:fontsize=30:x=(w-tw)/2:y=50")


def strip(src, dur, dest, fade=0.0):
    """A 16:9 picture as a 1080x608 strip high in the 9:16 frame, over its own blur; "fade" seconds to black at the end."""
    tail = f",fade=t=out:st={max(0.0, dur - fade):.3f}:d={fade:.3f}" if fade > 0 else ""
    fc = (f"[0:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,fps={FPS},split[a][b];"
          f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=44,eq=brightness=-0.22:saturation=0.7[bg];"
          f"[b]scale={STRIP_W}:{STRIP_H}:flags=lanczos[fg];[bg][fg]overlay=0:{STRIP_Y},trim=duration={dur:.3f}{tail}[out]")
    run(["-i", str(src), "-filter_complex", fc, "-map", "[out]", *ENC, str(dest)])


def pic_wide(spec, dur, dest):
    """A 16:9 cut as the strip, from t0, with an optional fade to black at the end; or, when the plan names the same
    cut made at 9:16 ("video_v"), that one full frame."""
    if spec.get("video_v"):
        path, t0 = spec["video_v"]
        if spec.get("land"):
            t0 = cutlib.land(path, t0, dur, spec.get("period"))
        run(["-ss", f"{t0:.3f}", "-t", f"{dur + 0.3:.3f}", "-i", path, "-vf",
             f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},"
             f"tpad=stop_mode=clone:stop_duration={dur + 0.2:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS"
             + ("," + badge(spec["label"]) if spec.get("label") else ""), *ENC, str(dest)])
        return
    path, t0 = spec["video"]
    if spec.get("land"):
        t0 = cutlib.land(path, t0, dur, spec.get("period"))
    wide = work / f"{dest.stem}_wide.mp4"
    run(["-ss", f"{t0:.3f}", "-t", f"{dur + 0.3:.3f}", "-i", path, "-vf",
         f"scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,fps={FPS},"
         f"tpad=stop_mode=clone:stop_duration={dur + 0.2:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS"
         + ("," + badge(spec["label"]) if spec.get("label") else ""), *ENC, str(wide)])
    strip(wide, dur, dest, fade=float(spec.get("fade", 0.0)))


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
    wide = work / f"{dest.stem}_wide.mp4"
    fit(joined, dur, wide, f"setpts=PTS/{retime(joined, dur):.4f},scale={SW}:{SH}:flags=lanczos")
    strip(wide, dur, dest)


def fit(src, dur, dest, vf="null"):
    have = probe_len(src)
    pad = max(0.0, dur - have) + 1.0
    run(["-i", str(src), "-vf", f"{vf},tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={dur:.3f},setpts=PTS-STARTPTS",
         *ENC, str(dest)])


def concat(parts, dest):
    lst = work / f"{dest.stem}.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)])


def full(path, t0, dur, dest):
    """A 9:16 cut full frame."""
    run(["-ss", f"{t0:.3f}", "-t", f"{dur + 0.2:.3f}", "-i", path, "-vf",
         f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS",
         *ENC, str(dest)])


def pic_three(spec, dur, dest):
    """The three cuts one after another, full frame, the segment split evenly."""
    n = len(spec["videos"])
    each = round(dur / n * FPS) / FPS
    parts = []
    for k, (path, t0) in enumerate(spec["videos"]):
        d = each if k < n - 1 else dur - each * (n - 1)
        p = work / f"{dest.stem}_t{k}.mp4"
        full(path, t0, d, p)
        parts.append(p)
    concat(parts, dest)


def pic_one(spec, dur, dest):
    path, t0 = spec["video"]
    full(path, t0, dur, dest)


TOP, CAPTION_BAND = 120, 420  # a grid keeps out of the top margin and the caption band at the foot (two lines plus their box)


def pic_grid(spec, dur, dest):
    """9:16 tiles with a label under each: two columns, three from five tiles; each row centred; the caption band clear."""
    clips = spec["clips"]
    n = len(clips)
    cols = 3 if n >= 5 else 2
    rows = (n + cols - 1) // cols
    gap, label_h = 36, 70
    avail = H - TOP - CAPTION_BAND
    h = min(820, (avail - rows * label_h - (rows - 1) * gap) // rows) // 2 * 2
    w = int(h * 9 / 16) // 2 * 2
    used = rows * (h + label_h) + (rows - 1) * gap
    y0 = TOP + (avail - used) // 2
    rate = float(spec.get("rate", 1.0))
    ins, fc = [], [GROUND.format(dur=dur) + "[bg0]"]
    for k, (path, label) in enumerate(clips):
        ins += ["-i", path]
        t0 = float(spec.get("start", 0.0))
        fc.append(f"[{k}:v]trim=start={t0:.3f},setpts=(PTS-STARTPTS)/{rate},fps={FPS},scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
                  f"crop={w}:{h},tpad=stop_mode=clone:stop_duration={dur:.3f}[v{k}]")
    prev = "bg0"
    for k, (path, label) in enumerate(clips):
        r, c = divmod(k, cols)
        in_row = min(cols, n - r * cols)
        x = (W - in_row * w - (in_row - 1) * gap) // 2 + c * (w + gap)
        y = y0 + r * (h + label_h + gap)
        fc.append(f"[{prev}][v{k}]overlay={x}:{y}:shortest=0,drawtext=fontfile='{FONT}':text='{label}':fontcolor=0xececf1:fontsize=38:"
                  f"x={x}+({w}-tw)/2:y={y + h + 20}[bg{k + 1}]")
        prev = f"bg{k + 1}"
    fc.append(f"[{prev}]trim=duration={dur:.3f}[out]")
    run([*ins, "-filter_complex", ";".join(fc), "-map", "[out]", *ENC, str(dest)])


def pic_card(spec, dur, dest):
    """A card: its vertical recording (rec/<name>_v.mp4, 1080x1920) when there is one, else the 16:9 one as a strip."""
    path, t0 = spec["video"]
    vertical = Path(path).with_name(Path(path).stem + "_v.mp4")
    if vertical.is_file():
        src = work / f"{dest.stem}_src.mp4"
        run(["-ss", f"{t0:.3f}", "-i", str(vertical), "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}", *ENC, str(src)])
        fit(src, dur, dest)
        return
    wide = work / f"{dest.stem}_wide.mp4"
    run(["-ss", f"{t0:.3f}", "-i", path, "-vf", f"scale={SW}:{SH}:flags=lanczos,fps={FPS}", *ENC, str(wide)])
    held = work / f"{dest.stem}_held.mp4"
    fit(wide, dur, held)
    strip(held, dur, dest)


def pic_chain(spec, dur, dest):
    parts = []
    fixed = sum(s for s, _ in spec["parts"] if s)
    for k, (secs, sub) in enumerate(spec["parts"]):
        d = secs if secs else max(0.5, dur - fixed)
        p = work / f"{dest.stem}_c{k}.mp4"
        PICS[sub["pic"]](sub, d, p)
        parts.append(p)
    concat(parts, dest)


def pic_still(spec, dur, dest):
    if spec.get("full"):  # the image is the whole frame (the montage's last frame with its title)
        run(["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-i", spec.get("image_v") or spec["image"], "-vf",
             f"scale={W}:{H}:flags=lanczos,fps={FPS},trim=duration={dur:.3f},setpts=PTS-STARTPTS", *ENC, str(dest)])
        return
    w = min(int(spec.get("width", 1800)), W - 60)
    label = spec.get("label", "")
    text = (f",drawtext=fontfile='{FONT}':text='{label}':fontcolor=0x9a9aab:fontsize=34:x=(w-tw)/2:y=h/2+400" if label else "")
    fc = (GROUND.format(dur=dur) + f"[bg];[0:v]scale={w}:-2:flags=lanczos,format=rgba[im];"
          f"[bg][im]overlay=(W-w)/2:(H-h)/2-120{text},trim=duration={dur:.3f}[out]")
    run(["-loop", "1", "-t", f"{dur + 0.2:.3f}", "-i", spec["image"], "-filter_complex", fc, "-map", "[out]", *ENC, str(dest)])


PICS = {"screen": pic_screen, "three": pic_three, "one": pic_one, "grid": pic_grid, "card": pic_card, "chain": pic_chain,
        "still": pic_still, "wide": pic_wide}


def captions(segs):
    """ASS captions for the phone: shorter chunks, two lines of about 30 characters, under the strip."""
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,Segoe UI Semibold,54,&H00F1ECEC,&H00FFFFFF,&H28140B0C,&H28140B0C,0,0,0,0,100,100,0,0,3,16,0,2,70,70,560,1\n"
            "Style: CapLow,Segoe UI Semibold,54,&H00F1ECEC,&H00FFFFFF,&H28140B0C,&H28140B0C,0,0,0,0,100,100,0,0,3,16,0,2,70,70,150,1\n"
            "Style: Chap,Segoe UI Semibold,40,&H00FF8894,&H00FFFFFF,&H14140B0C,&H14140B0C,0,0,0,0,100,100,1,0,3,14,0,8,56,56,120,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

    def ts(t):
        return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"

    def style(pic):
        """Under the strip for a desk recording; at the foot for a full-frame cut, a grid or a card (a chain goes by
        what it ends on)."""
        kind = pic["pic"]
        if kind == "chain":
            kind = pic["parts"][-1][1]["pic"]
        return "Cap" if kind == "screen" else "CapLow"

    rows, chapters = [], []
    for s in segs:
        chapter = copy[s["id"]].get("chapter")
        if chapter and chapter not in chapters and chapter != "End":
            chapters.append(chapter)
            rows.append(f"Dialogue: 1,{ts(s['start'] + 0.2)},{ts(s['start'] + 3.6)},Chap,,0,0,0,,{{\\fad(250,450)}}{len(chapters)} · {chapter}")
        st = style(s["pic"])
        for i, start in s["voices"]:
            text, spoken = copy[i]["text"], lines[i]["seconds"]
            chunks = blocks(text)
            total = sum(len(c) for c in chunks)
            t = start
            for c in chunks:
                d = spoken * len(c) / total
                # no overlap at all: a caption that starts while the last one shows is stacked above it by libass and
                # stays there for its whole life (a line too high, into a grid or a card's chips)
                rows.append(f"Dialogue: 0,{ts(t)},{ts(t + d - 0.02)},{st},,0,0,0,,{two_lines(c)}")
                t += d
    return head + "\n".join(rows) + "\n"


BLOCK = 60  # characters a caption holds, on two lines of the narrow frame
LINE = 32


def pieces(text, marks):
    out, cur = [], ""
    for word in text.split(" "):
        cur = f"{cur} {word}".strip()
        if cur.endswith(marks):
            out.append(cur)
            cur = ""
    return out + ([cur] if cur else [])


def blocks(text):
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
        if out and (len(out[-1]) + 1 + len(u) <= BLOCK or len(out[-1]) < 16):
            out[-1] = f"{out[-1]} {u}"
        else:
            out.append(u)
    # a unit still over the block (a long clause) breaks at the word nearest its middle
    final = []
    for u in out:
        while len(u) > BLOCK + 8:
            words = u.split(" ")
            k = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(u) / 2))
            final.append(" ".join(words[:k]))
            u = " ".join(words[k:])
        final.append(u)
    return final


def two_lines(text):
    text = re.sub(r"(\d) (GB|MB|s)\b", lambda m: m.group(1) + "\u00a0" + m.group(2), text)
    if len(text) <= LINE:
        return text
    words = text.split(" ")
    best, best_cost = 1, 1e9
    for k in range(1, len(words)):
        a, b = " ".join(words[:k]), " ".join(words[k:])
        cost = abs(len(a) - len(b)) - (12 if a.endswith((",", ":", ".")) else 0)
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
    plan_v = {**plan, "intro": plan.get("intro_v") or None}  # the 9:16 montage, when there is one
    intro = cutlib.finish(plan_v, picture, mix, af, ass, out, work, (W, H))
    (out.with_suffix(".json")).write_text(json.dumps({"seconds": round(intro + total, 2), "intro": round(intro, 2), "segments": [
        {**{k: s[k] for k in ("id", "dur")}, "start": round(intro + s["start"], 3), "voice_at": round(intro + s["voice_at"], 3)}
        for s in segs]}, indent=1), encoding="utf-8")
    print("wrote", out, round(intro + total, 1), "s", flush=True)


main()
