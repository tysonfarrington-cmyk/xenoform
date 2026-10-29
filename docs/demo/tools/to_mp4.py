"""A recorded shot (rec/<name>/frames.txt, screencast jpegs with their wall-clock times) to rec/<name>.mp4 at a constant
30 fps from the shot's start mark to its end mark, and an 8-frame contact sheet rec/<name>_sheet.jpg. Prints the marks as
seconds into the clip.

    python to_mp4.py vibe idea ...
"""
import json
import subprocess
import sys
from pathlib import Path

REC = Path(__file__).parent / "rec"
FPS = 30

for name in sys.argv[1:]:
    d = REC / name
    frames = sorted((float(ts), f) for f, ts in (line.split() for line in (d / "frames.txt").read_text().splitlines() if line.strip()))
    marks = [(n, float(ts)) for n, ts in (line.split() for line in (d / "marks.txt").read_text().splitlines() if line.strip())]
    t0 = next(ts for n, ts in marks if n == f"{name}_start")
    t1 = next(ts for n, ts in marks if n == f"{name}_end")
    # the frame showing at each output tick (the last one received at or before it)
    lines, k = [], 0
    n_out = int((t1 - t0) * FPS)
    for i in range(n_out):
        t = t0 + i / FPS
        while k + 1 < len(frames) and frames[k + 1][0] <= t:
            k += 1
        lines.append(f"file '{(d / frames[k][1]).as_posix()}'\nduration {1 / FPS:.6f}")
    lines.append(f"file '{(d / frames[k][1]).as_posix()}'")
    (d / "list.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = REC / f"{name}.mp4"
    # a shot recorded for the phone (a 9:16 card) keeps its orientation
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                            str(d / frames[0][1])], capture_output=True, text=True).stdout.strip().split(",")
    tall = len(probe) == 2 and int(probe[1]) > int(probe[0])
    size, sheet = ("1080:1920", "270:480") if tall else ("1920:1080", "480:270")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(d / "list.txt"), "-vf",
                    f"scale={size}:flags=lanczos,fps={FPS},format=yuv420p", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                    str(out)], check=True)
    dur = n_out / FPS
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-vf", f"fps=8/{dur:.3f},scale={sheet},tile=4x2",
                    "-frames:v", "1", str(REC / f"{name}_sheet.jpg")], check=True)
    rel = {n: round(ts - t0, 2) for n, ts in marks if t0 <= ts <= t1}
    (REC / f"{name}.json").write_text(json.dumps({"seconds": round(dur, 2), "marks": rel}, indent=1), encoding="utf-8")
    print(name, round(dur, 1), "s", rel, flush=True)
