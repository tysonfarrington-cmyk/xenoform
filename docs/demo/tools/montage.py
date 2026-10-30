"""The montage (Tys, 29 Oct: "a 1 min montage intro of different styles and themes, make it look slick, show off all the
effects and capabilities, push it to the limit max it out"): Cloud Final cuts on Glitch Out laid end to end by song
time, so every cut's picture plays over the very seconds of the song it was made on (its beat FX land on the song's
hits), each cut between two of them moved to a shot boundary the two share near a beat (the outgoing morph finishes its
handoff, the next one starts fresh), the song itself as the sound, and one title, "Xenoform", over the last shot on the
downbeat where the song falls to its calm.

    python montage.py <plan json> <out mp4> [--excerpt <song seconds>]   (--excerpt: the demo's intro, from that song
                                                                          time to the title, without it)

The plan: {"aspect": "16:9"|"9:16", "start": song s, "title": song s, "tail": s, "slots": [[label, end song s(, "pin")], ...]};
labels name rows of montage/renders_<169|916>.json or clips_glitch.json (a 16:9 cut in a 9:16 montage plays as a strip
over its own blur). Writes <out>.json (the slots as cut, with jobs and in points).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
M = HERE / "montage"
JOBS = Path(r"C:\Projects\xenoform-rc2\work\ui\jobs")
SONG = Path(r"C:\Projects\xenoform-rc2\examples\songs\glitch_out.mp3")
FEATURES = Path(r"C:\Projects\xenoform-rc2\examples\songs\glitch-out.features.json")
FPS = 24
sys.path.insert(0, str(HERE))
from song_offset import offset  # noqa: E402


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def sources(aspect):
    """label -> {job, window, aspect} for the done renders: this aspect's first, the clips cuts (16:9) after."""
    rows = {}
    for name in (f"renders_{'169' if aspect == '16:9' else '916'}.json", "renders_169.json", "clips_glitch.json"):
        p = M / name
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            if r.get("status") == "done" and r["label"] not in rows:
                rows[r["label"]] = {"job": r["job"], "window": float(r["window"]), "aspect": r.get("aspect", "16:9")}
    # "<label>@169" in a 9:16 plan: the 16:9 render as a strip over its blur even when a 9:16 one exists (30 Oct: some
    # 9:16 renders came out smeared or on plain objects where the 16:9 stretch is good)
    p = M / "renders_169.json"
    if p.exists():
        for r in json.loads(p.read_text(encoding="utf-8")):
            if r.get("status") == "done":
                rows.setdefault(r["label"] + "@169", {"job": r["job"], "window": float(r["window"]), "aspect": "16:9"})
    return rows


def offsets(rows):
    """Each cut's start in the song, measured once (montage/offsets.json)."""
    path = M / "offsets.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for r in rows.values():
        if r["job"] not in known:
            known[r["job"]] = offset(r["job"], r["window"])[0]
        r["offset"] = known[r["job"]]
        mp4 = JOBS / r["job"] / "xenoform.mp4"
        secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                                    capture_output=True, text=True).stdout.strip())
        r["end"] = r["offset"] + secs  # the song time the cut runs out
    path.write_text(json.dumps(known, indent=1), encoding="utf-8")


def bounds(r):
    """A cut's shot boundaries in song seconds."""
    shots = json.loads((JOBS / r["job"] / "simple" / "simple.json").read_text(encoding="utf-8"))["shots"]
    return sorted({round(r["offset"] + float(s["start"]), 3) for s in shots} | {round(r["offset"] + float(s["end"]), 3) for s in shots})


def place(a, b, want, beats, pin=False):
    """The cut from cut a into cut b: always on a beat of the song (the full song's grid: it sits on the hits; a cut's
    own grid, from the re-analysis of its trimmed audio, runs about 0.1 s late), within a bar of where the plan wanted
    it; a beat where a's morph has just finished scores best (it ends its handoff), then one where b's starts, then a
    downbeat, then a half bar. ``pin``: exactly the plan's beat (the drops)."""
    # only where both cuts have picture: a's window still running, b's begun
    near_beats = [t for t in beats if abs(t - want) <= 1.4 and b["offset"] + 0.05 <= t <= a["end"] - 0.05] or [want]
    if pin:
        return min(near_beats, key=lambda t: abs(t - want))
    ba, bb = bounds(a), bounds(b)

    def near(t, xs, tol=0.2):
        return any(abs(t - x) <= tol for x in xs)

    def score(t):
        i = beats.index(t) if t in beats else -1
        s = 2.5 * near(t, ba) + 1.5 * near(t, bb) - 1.0 * abs(t - want)
        if i >= 0:
            s += 1.5 if i % 4 == 0 else 0.7 if i % 2 == 0 else 0.0
        return s
    return max(near_beats, key=score)


def main():
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    excerpt = float(sys.argv[sys.argv.index("--excerpt") + 1]) if "--excerpt" in sys.argv else None
    aspect = plan.get("aspect", "16:9")
    w, h = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    rows = sources(aspect)
    offsets(rows)
    beats = json.loads(FEATURES.read_text(encoding="utf-8"))["beats"]
    slots = [(row[0], float(row[1])) for row in plan["slots"]]
    pins = [len(row) > 2 and row[2] == "pin" for row in plan["slots"]]
    missing = [lab for lab, _ in slots if lab not in rows]
    if missing:
        raise SystemExit(f"not rendered yet: {missing}")
    # a slot may take another stretch of its cut (a 4th entry: whole beats later, or earlier when negative): the
    # cut's offset moves by whole beats, so its beat FX still land on the song's beats (Owly, round 1: the
    # binoculars held too long, the lotus too samey, the vase-to-face smeared)
    steps = sorted(b - a for a, b in zip(beats, beats[1:]))
    period = steps[len(steps) // 2]
    srows = []
    for row in plan["slots"]:
        r = dict(rows[row[0]])
        shift = float(row[3]) * period if len(row) > 3 and row[3] else 0.0
        r["offset"] -= shift
        r["end"] -= shift
        r["shift_beats"] = float(row[3]) if len(row) > 3 and row[3] else 0.0
        srows.append(r)
    prev = float(plan["start"])
    for k, (lab, end) in enumerate(slots[:-1] + [(slots[-1][0], float(plan["title"]) + float(plan.get("tail", 3.0)))]):
        r = srows[k]
        if prev < r["offset"] - 0.01 or end > r["end"] + 0.01:
            raise SystemExit(f"{lab} runs {r['offset']:.2f} to {r['end']:.2f} in the song; its slot asks {prev:.2f} to {end:.2f}")
        prev = end
    start, title = float(plan["start"]), float(plan["title"])
    tail = float(plan.get("tail", 3.0)) if excerpt is None else 0.0
    end = title + tail
    # the cut times: the plan's start, each slot's end placed on a shared boundary, the last running to the end
    cuts = [start]
    for k, (lab, want) in enumerate(slots[:-1]):
        cuts.append(place(srows[k], srows[k + 1], want, beats, pins[k]))
    cuts.append(end)
    if excerpt is not None:  # the demo's intro: from song time ``excerpt`` (inside whichever slot holds it) to the title
        k = max(i for i in range(len(slots)) if cuts[i] <= excerpt + 0.05)
        cuts, slots, srows = [excerpt] + cuts[k + 1:], slots[k:], srows[k:]
        start = excerpt
    frames = [round((c - start) * FPS) for c in cuts]
    work = M / ("build_" + out.stem)
    work.mkdir(exist_ok=True)
    parts, record = [], []
    for k, (lab, _) in enumerate(slots):
        r = srows[k]
        n = frames[k + 1] - frames[k]
        if n <= 0:
            continue
        f0 = round((cuts[k] - r["offset"]) * FPS)
        src = JOBS / r["job"] / "xenoform.mp4"
        if aspect == "9:16" and r["aspect"] == "16:9":  # a 16:9 cut as a strip high in the frame over its own blur
            vf = (f"trim=start_frame={f0}:end_frame={f0 + n},setpts=PTS-STARTPTS,split[a][b];"
                  f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=44,eq=brightness=-0.22:saturation=0.75[bg];"
                  f"[b]scale=1080:608:flags=lanczos[fg];[bg][fg]overlay=0:(H-h)/2-180")
        else:
            vf = (f"trim=start_frame={f0}:end_frame={f0 + n},setpts=PTS-STARTPTS,"
                  f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}")
        p = work / f"s{k:02d}_{lab}.mp4"
        run(["-i", str(src), "-filter_complex", f"[0:v]fps={FPS},{vf},format=yuv420p[v]", "-map", "[v]", "-an",
             "-c:v", "libx264", "-crf", "12", "-preset", "medium", "-r", str(FPS), str(p)])
        parts.append(p)
        record.append({"label": lab, "job": r["job"], "song_in": round(cuts[k], 3), "song_out": round(cuts[k + 1], 3),
                       "cut_in": round(f0 / FPS, 3), "frames": n})
        print(f"  {lab:24} {cuts[k]:7.2f} -> {cuts[k + 1]:7.2f}  ({n / FPS:4.2f} s, cut at {f0 / FPS:5.2f})", flush=True)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    picture = work / "picture.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(picture)])
    total = frames[-1] / FPS
    # the title on the downbeat: the shot dims under it, the mark and word come up in a quarter second, the end fades out
    t_title = (title - start)
    png = HERE / "cards" / ("title_169.png" if aspect == "16:9" else "title_916.png")
    if excerpt is None:
        fc = (f"[0:v]eq=brightness='-0.42*clip((t-{t_title:.3f})/0.3,0,1)':saturation='1-0.4*clip((t-{t_title:.3f})/0.3,0,1)':eval=frame[d];"
              f"[1:v]format=rgba,fade=t=in:st={t_title:.3f}:d=0.25:alpha=1[t];"
              f"[d][t]overlay=0:0:enable='gte(t,{t_title:.3f})',fade=t=out:st={total - 1.2:.3f}:d=1.2,format=yuv420p[v]")
        a_fade = f",afade=t=out:st={total - 2.2:.3f}:d=2.2"
    else:  # the intro stops on the title's downbeat; the body rings it out (cutlib: intro_tail)
        fc = "[0:v]null,format=yuv420p[v]"
        a_fade = ""
    audio = work / "song.wav"
    run(["-ss", f"{start:.4f}", "-t", f"{total:.4f}", "-i", str(SONG), "-af", f"afade=t=in:d=0.03{a_fade}", "-ar", "48000", "-ac", "2", str(audio)])
    # a fixed gain to -16 LUFS and a delay-compensated peak limiter (cutlib.loudnorm: loudnorm's dynamic fallback shifts)
    sys.path.insert(0, str(HERE))
    import cutlib
    m = cutlib.measure(audio)
    af = cutlib.loudnorm(audio)
    run(["-i", str(picture), "-loop", "1", "-t", f"{total:.3f}", "-i", str(png), "-i", str(audio), "-filter_complex",
         f"{fc};[2:a]{af}[a]", "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)])
    out.with_suffix(".json").write_text(json.dumps({"aspect": aspect, "song_start": start, "title": title, "seconds": round(total, 3),
                                                    "gain_db": round(-16.0 - float(m["input_i"]), 2), "slots": record}, indent=1),
                                        encoding="utf-8")
    print("wrote", out, round(total, 2), "s", flush=True)


main()
