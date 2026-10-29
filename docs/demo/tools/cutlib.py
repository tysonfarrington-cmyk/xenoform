"""What assemble.py (16:9) and assemble_v.py (9:16) share, so the two cuts keep one timeline: the segments sized to the
read with room to breathe, every segment's end snapped to a beat of the bed, the voice and the bed (ducked, levelled),
and the intro joined in front (Tys, 29 Oct: "need some pauses and let scenes breathe a little more", "it should
pretty much be on beat ... but let scenes finish properly").

Plan keys read here:
  lead, gap, tail   seconds before a segment's first line, between its lines, after its last (defaults 0.5, 0.7, 0.8;
                    a segment may set its own)
  music             the bed; music_start: where in it the body starts (seconds); music_gain_db
  grid              {"features": <the bed's analysis json>, "bar_phase": 0, "bar_slack": 1.0, "half_slack": 0.45}:
                    a segment ends on the next downbeat when it is within bar_slack, else the next half bar within
                    half_slack, else the next beat
  intro             an mp4 with its own sound (the montage) played before the body, its audio as it is
  intro_tail        {"song": mp3, "start": song s, "seconds": 1.6, "gain_db": the intro's loudnorm gain}: the intro stops
                    on its title's downbeat; this rings the song on from there under the body's first seconds, fading,
                    at the intro's level
"""
import json
import subprocess
import sys
from pathlib import Path

FPS = 30


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def probe_len(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True).stdout.strip())


def grid(plan, total_guess=600.0):
    """The bed's beats in body seconds as (time, index) pairs, extended before the first tracked beat at the median
    spacing (Glitch Out's first 13.8 s have no tracked beat); index % 4 == bar_phase is a downbeat."""
    g = plan.get("grid")
    if not g:
        return []
    data = json.loads(Path(g["features"]).read_text(encoding="utf-8"))
    beats = [float(b) for b in data["beats"]]
    index = data.get("index") or list(range(len(beats)))  # a bed of several passes (bed.py) keeps each beat's own index
    start = float(plan.get("music_start", 0.0))
    steps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    p = steps[len(steps) // 2]
    out = [(b - start, i) for i, b in zip(index, beats)]
    k, t = -1, beats[0] - p
    while t - start > -p:
        out.append((t - start, k))
        k, t = k - 1, t - p
    last_i, t = index[-1], beats[-1] + p
    while t - start < total_guess:  # past the song's end (a looped bed) the grid runs on at the same pulse
        last_i += 1
        out.append((t - start, last_i))
        t += p
    out.sort()
    filled = out[:1]
    for t, i in out[1:]:  # a beatless stretch inside the bed (a pass restarting on its quiet opening) keeps the pulse
        pt, pi = filled[-1]
        while t - pt > 1.6 * p:
            pt, pi = pt + p, pi + 1
            filled.append((pt, pi))
        filled.append((t, i))
    return [x for x in filled if x[0] > 0]


def snap(end, beats, plan):
    """The first beat at or after ``end``, preferring a downbeat or a half bar when one is close."""
    if not beats:
        return end
    g = plan.get("grid") or {}
    phase = int(g.get("bar_phase", 0))
    after = [(t, i) for t, i in beats if t >= end - 0.02]
    if not after:
        return end
    for slack, every in ((float(g.get("bar_slack", 1.0)), 4), (float(g.get("half_slack", 0.45)), 2)):
        for t, i in after:
            if t - end > slack:
                break
            if (i - phase) % every == 0:
                return t
    return after[0][0]


def timeline(plan, lines):
    """Segments with their voice starts, each ending on a beat of the bed (at a frame)."""
    beats = grid(plan)
    d_lead, d_gap, d_tail = (float(plan.get(k, v)) for k, v in (("lead", 0.5), ("gap", 0.7), ("tail", 0.8)))
    segs, frame = [], 0
    for s in plan["segments"]:
        ids = s.get("ids") or [s["id"]]
        lead, gap, tail = (float(s.get(k, d)) for k, d in (("lead", d_lead), ("gap", d_gap), ("tail", d_tail)))
        t = frame / FPS
        voices, at = [], t + lead
        for i in ids:
            voices.append((i, at))
            at += lines[i]["seconds"] + gap
        spoken = at - gap - (t + lead)
        want = max(float(s.get("min", 0)), lead + spoken + tail)
        end = snap(t + want, beats, plan) if s.get("snap", True) else t + want
        end_frame = max(frame + 1, round(end * FPS))
        dur = (end_frame - frame) / FPS
        segs.append({**s, "id": ids[0], "voices": voices, "dur": dur, "start": t, "voice_at": t + lead})
        frame = end_frame
    return segs, frame / FPS


def mix(plan, segs, total, read, work):
    """The voice at its places, the bed under it from music_start, ducked by the voice (and the intro's ring-out at
    the start); returns the mix and the two-pass loudnorm filter that levels it to -16 LUFS."""
    starts = {i: at for s in segs for i, at in s["voices"]}
    (work / "starts.json").write_text(json.dumps(starts), encoding="utf-8")
    voice = work / "voice.wav"
    subprocess.run([sys.executable.replace("xenoform-rc2\\.venv", "kokoro-tts\\.venv"), str(Path(r"C:\Projects\kokoro-tts\join.py")),
                    str(read), str(voice), "--starts", str(work / "starts.json")], check=True)
    start = float(plan.get("music_start", 0.0))
    fade_out = total - 2.5
    out = work / "mix.wav"
    fc = (f"[1:a]atrim=start={start:.3f}:end={start + total:.3f},asetpts=PTS-STARTPTS,volume={plan.get('music_gain_db', -10)}dB,"
          f"afade=t=in:d={float(plan.get('music_fade_in', 0.6)):.2f},afade=t=out:st={fade_out:.3f}:d=2.5,"
          f"aformat=sample_rates=48000:channel_layouts=stereo[m];"
          f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={total:.3f},asplit[v][sc];"
          f"[m][sc]sidechaincompress=threshold=0.03:ratio=6:attack=25:release=450:makeup=1[md];"
          f"[v][md]amix=inputs=2:duration=first:normalize=0[a]")
    run(["-i", str(voice), "-stream_loop", "-1", "-i", plan["music"], "-filter_complex", fc, "-map", "[a]", "-c:a", "pcm_s16le", str(out)])
    tail = plan.get("intro_tail")
    if not tail:
        return out, loudnorm(out)
    # the ring-out at the intro's own level: the body is levelled by g_body after this, so it goes in at gain - g_body
    g_body = -16.0 - float(measure(out)["input_i"])
    secs = float(tail.get("seconds", 1.6))
    rung = work / "mix_tail.wav"
    run(["-i", str(out), "-ss", f"{float(tail['start']):.4f}", "-t", f"{secs:.3f}", "-i", tail["song"], "-filter_complex",
         f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={float(tail['gain_db']) - g_body:.2f}dB,"
         f"afade=t=out:st=0:d={secs:.3f}:curve=qsin[t];[0:a][t]amix=inputs=2:duration=first:normalize=0[a]",
         "-map", "[a]", "-c:a", "pcm_s16le", str(rung)])
    return rung, loudnorm(rung)


def measure(path, target=-16):
    probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"loudnorm=I={target}:TP=-2.5:LRA=11:print_format=json",
                            "-f", "null", "-"], capture_output=True, text=True).stderr
    return json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])


def loudnorm(path, target=-16):
    m = measure(path, target)
    return (f"loudnorm=I={target}:TP=-2.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
            f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,aresample=48000")


def finish(plan, picture, mix_wav, af, ass, out, work, size):
    """Captions burned into the body; then the intro, when the plan has one, joined in front with its own sound."""
    sub = ass.as_posix().replace(":", "\\:")
    body = out if not plan.get("intro") else work / "body.mp4"
    run(["-i", str(picture), "-i", str(mix_wav), "-filter_complex", f"[0:v]subtitles='{sub}'[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-pix_fmt", "yuv420p",
         *(["-c:a", "pcm_s16le"] if plan.get("intro") else ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]), "-shortest",
         str(body.with_suffix(".mkv") if plan.get("intro") else body)])
    if not plan.get("intro"):
        return 0.0
    body = body.with_suffix(".mkv")
    intro = plan["intro"]
    w, h = size
    fc = (f"[0:v]fps={FPS},scale={w}:{h}:flags=lanczos,setsar=1,format=yuv420p[iv];[0:a]aformat=sample_rates=48000:channel_layouts=stereo[ia];"
          f"[1:v]setsar=1,format=yuv420p[bv];[1:a]aformat=sample_rates=48000:channel_layouts=stereo[ba];"
          f"[iv][ia][bv][ba]concat=n=2:v=1:a=1[v][a]")
    run(["-i", intro, "-i", str(body), "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out)])
    return probe_len(intro)


def land(path, t0, dur, period=None):
    """The in point that ends a cut's stretch on one of its shot boundaries (simple/simple.json beside the cut), so the
    last morph on screen finishes its handoff as the segment cuts; t0 itself when the cut has no record. With
    ``period`` (the bed's beat, for a cut made on the bed's own seconds) the in point only moves by whole beats, up to
    a bar and a half, so the cut's beat FX stay on the bed's beats; it stays put when no such move reaches a boundary."""
    rec = Path(path).parent / "simple" / "simple.json"
    if not rec.is_file():
        return t0
    shots = json.loads(rec.read_text(encoding="utf-8")).get("shots") or []
    bounds = sorted({round(float(s["end"]), 4) for s in shots})
    if period:
        for k in range(0, 7):
            end = t0 + k * period + dur
            if any(abs(end - b) <= 0.2 for b in bounds):
                return t0 + k * period
        return t0
    for b in bounds:
        if b >= t0 + dur - 0.04:
            return max(0.0, b - dur)
    return t0


def frames(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries", "stream=nb_read_packets",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def join_exact(parts, durs, dest):
    """The segments end to end, each exactly its own frame count: an encode that comes out a frame or two long (a
    retimed recording resampled to 30 fps) would otherwise push everything after it off the voice and the beat. Only a
    segment that is off is re-cut (its last frame held or its tail trimmed); then one stream copy joins them (a single
    filter over 39 inputs decodes them all at once and crawled for an hour on the long)."""
    fixed = []
    for p, d in zip(parts, durs):
        p, n = Path(p), round(d * FPS)
        if frames(p) != n:
            q = p.with_name(p.stem + "_x.mp4")
            run(["-i", str(p), "-vf", f"tpad=stop_mode=clone:stop_duration=2,trim=end_frame={n},setpts=PTS-STARTPTS", "-an",
                 "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS), str(q)])
            p = q
        fixed.append(p)
    lst = Path(dest).with_suffix(".txt")
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in fixed), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)])
