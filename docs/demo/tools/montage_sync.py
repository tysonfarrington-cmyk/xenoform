"""Is a montage's sound the song at its start time? Envelope cross-correlation of the montage audio against the song."""
import subprocess
import sys

import numpy as np

mont, song, start = sys.argv[1], sys.argv[2], float(sys.argv[3])
RATE = 1000


def env(path, s=0.0, d=None):
    args = ["ffmpeg", "-v", "error", "-ss", f"{s:.3f}"] + (["-t", f"{d:.3f}"] if d else []) + ["-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(args, capture_output=True).stdout, np.float32)
    h = 16000 // RATE
    return np.log(np.sqrt(np.convolve(x[: len(x) // h * h] ** 2, np.ones(h) / h, "same")[::h]) + 1e-4)


m = env(mont)
for t0 in (5, 30, 60, 90):
    seg = m[t0 * RATE:(t0 + 6) * RATE]
    seg = seg - seg.mean()
    s = env(song, start + t0 - 8, 22)
    best, lag = -1e9, None
    for k in range(0, len(s) - len(seg)):
        w = s[k:k + len(seg)]
        c = float(np.dot(w - w.mean(), seg))
        if c > best:
            best, lag = c, k / RATE - 8
    print(f"montage at {t0:3d}s matches the song {lag:+.3f} s from where it should")
