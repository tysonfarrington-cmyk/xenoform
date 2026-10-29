"""Where the body's voice track sits in a finished demo: the voice wav (body-relative) against the final mix, by
cross-correlating loudness envelopes in windows; prints the offset found in each window (intro length = in sync)."""
import subprocess
import sys

import numpy as np

final, voice = sys.argv[1], sys.argv[2]
RATE = 1000


def env(path, start=0.0, dur=None):
    args = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + ["-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    x = np.frombuffer(subprocess.run(args, capture_output=True).stdout, np.float32)
    h = 16000 // RATE
    e = np.sqrt(np.convolve(x[: len(x) // h * h] ** 2, np.ones(h) / h, "same")[::h])
    return np.log(e + 1e-4)


v = env(voice)
f = env(final)
for t0 in (5, 15, 30, 45, 60, 75, 88):  # body-relative windows of the voice, 8 s each
    seg = v[t0 * RATE:(t0 + 8) * RATE]
    seg = seg - seg.mean()
    best, lag = -1e9, None
    for off in np.arange(10.0, 35.0, 0.01):
        a = int((t0 + off) * RATE)
        w = f[a:a + len(seg)]
        if len(w) < len(seg):
            break
        c = float(np.dot(w - w.mean(), seg))
        if c > best:
            best, lag = c, off
    print(f"voice at body {t0:3d}s found at final offset {lag:.2f}")
