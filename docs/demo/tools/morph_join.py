"""Turn a hard cut in a finished demo into a morph with effects (Tys, 30 Oct 2 pm: the orchid opening should "morph into
the app demonstration part ... with effects"): over one beat either side of the cut the outgoing picture (taken on from
its own source, so it keeps moving) dissolves into the incoming one (its first frame held before the cut), with an RGB
split and a glow that peak at the cut and fall away by the next beat. No zoom (Tys: never on the app screens). The
sound is the finished file's, untouched.

    python morph_join.py <in mp4> <out mp4> <cut s> <outgoing source mp4> <source s at the cut> [half window s] [clean]

``clean`` (Tys, 30 Oct 2:15 pm: "the way it blurs isnt good.. lets just try a clean morph into the app"): a plain
dissolve, no RGB split or glow; with a short window (a sixth of a second either side) it reads as a clean change on the
beat. A real AI morph of the protea into the desk screen was tried (Cloud Final d74521c3, the two stills pinned): LTX
mutated the flower into a spiked skull and crossed to the screen in two frames, so it was not used.
"""
import subprocess
import sys

src, out, cut, a_src, a_at = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4], float(sys.argv[5])
half = float(sys.argv[6]) if len(sys.argv) > 6 else 0.6667
clean = len(sys.argv) > 7 and sys.argv[7] == "clean"
num, den = (int(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                                          "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip().split("/"))
FPS = round(num / den)  # the finished demo is 30 fps, the renders 24
w, h = (int(x) for x in subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                         "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip().split(","))
fc = round(cut * FPS)
n = round(half * FPS)
f0, f1 = fc - n, fc + n
dur = (f1 - f0) / FPS
a_start = a_at - n / FPS
k = f"{w / 1920 * 28:.1f}*sin(PI*min(T/{dur:.4f},1))"
s = f"0.35*sin(PI*min(T/{dur:.4f},1))"
fx = (f"geq=r='clip(r(X-{k},Y)*(1+{s}),0,255)':g='clip(g(X,Y)*(1+{s}),0,255)':b='clip(b(X+{k},Y)*(1+{s}),0,255)'")
graph = (
    f"[1:v]fps={FPS},trim=start={a_start:.4f}:duration={dur:.4f},setpts=PTS-STARTPTS,settb=1/{FPS},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=rgb24[a];"
    f"[0:v]trim=start_frame={fc}:end_frame={f1},setpts=PTS-STARTPTS,tpad=start={n}:start_mode=clone,settb=1/{FPS},format=rgb24[b];"
    f"[a][b]xfade=transition={'fade' if clean else 'dissolve'}:duration={dur:.4f}:offset=0{'' if clean else ',' + fx},format=yuv420p[t];"
    f"[0:v]trim=end_frame={f0},setpts=PTS-STARTPTS,settb=1/{FPS},format=yuv420p[p];"
    f"[0:v]trim=start_frame={f1},setpts=PTS-STARTPTS,settb=1/{FPS},format=yuv420p[q];"
    f"[p][t][q]concat=n=3:v=1:a=0[v]")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-i", a_src, "-filter_complex", graph, "-map", "[v]", "-map", "0:a",
                "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-r", str(FPS), "-c:a", "copy", "-movflags", "+faststart", out],
               check=True)
print("wrote", out, f"cut {cut:.3f} s, frames {f0}..{f1}")
