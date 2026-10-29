"""A long bed from one song: the song played through, then again from its start (Glitch Out ends on its calm and opens
quiet and beatless, so the restart sounds like the track coming round again), as many times as the length needs; and
its beat list with each pass's beats keeping their own index in the song, so cutlib's bar phase holds on every pass.

    python bed.py <song mp3> <features json> <seconds> <out wav>     (writes <out>.beats.json beside it)
"""
import json
import subprocess
import sys
from pathlib import Path

song, features, seconds, out = Path(sys.argv[1]), Path(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
f = json.loads(features.read_text(encoding="utf-8"))
length = float(f["duration"])
passes = int(seconds // length) + 1
subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", str(passes - 1), "-i", str(song), "-t", f"{passes * length:.3f}",
                "-ar", "48000", "-ac", "2", str(out)], check=True)
beats, index = [], []
for k in range(passes):
    for i, b in enumerate(f["beats"]):
        beats.append(round(k * length + float(b), 4))
        index.append(i)
out.with_suffix(".beats.json").write_text(json.dumps({"duration": passes * length, "beats": beats, "index": index}), encoding="utf-8")
print(out, passes, "passes", round(passes * length, 1), "s")
