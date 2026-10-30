"""Tame the white flashes in a finished video without touching its cuts (Tys, 30 Oct 3:15 pm: "we also need to tone
down the white flashing light. its already pretty intense so that has to be used sparingly and subtly").

A frame is a flash when its mean luma stands above the darkest of the five frames before it and of the five after by
more than THRESH (a cut from a dark shot to a bright one is a step, level with the frames after it, so
it is left alone). A flash is read as a white veil over the picture; the veil is lifted and KEEP of it laid back: the beat still pulses,
subtly. The sound is copied.

    python deflash.py <in mp4> <out mp4> [keep 0..1, default 0.35]
"""
import re
import subprocess
import sys

import numpy as np

src, out = sys.argv[1], sys.argv[2]
KEEP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.35
THRESH = 6.0  # luma levels (0..255) above the baseline before a frame counts as a flash
N = 5  # frames each side

probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                        "-of", "csv=p=0", src], capture_output=True, text=True).stdout.strip().split(",")
w, h = int(probe[0]), int(probe[1])
fps = probe[2]
# pass 1: each frame's mean luma (a quarter-size decode is enough)
import os
import tempfile

tmp = os.path.join(tempfile.gettempdir(), f"deflash_{os.getpid()}.txt")
subprocess.run(["ffmpeg", "-v", "error", "-i", os.path.abspath(src), "-vf",
                f"scale=480:-2,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file={os.path.basename(tmp)}",
                "-f", "null", "-"], check=True, cwd=os.path.dirname(tmp))
with open(tmp, encoding="utf-8") as fh:
    y = np.array([float(v) for v in re.findall(r"YAVG=([\d.]+)", fh.read())])
os.remove(tmp)
gain = np.ones(len(y))
base_of = np.zeros(len(y))
for i in range(N, len(y) - N):
    # a flash rises in a frame and decays over three or four (67 -> 133 -> 117 -> 104 -> 82 -> 66, measured): the
    # darkest frame on each side is the ground it rose from; a cut into a brighter shot stays level with the frames
    # after it, so the side it is level with sets the baseline and it is left alone
    before, after = y[i - N:i].min(), y[i + 1:i + 1 + N].min()
    base = max(before, after)
    if y[i] > base + THRESH and y[i] > 1:
        # the flash as a white veil over the picture: y = base * (1 - v) + 255 * v; ``gain`` carries v
        gain[i] = -min(0.6, (y[i] - base) / max(1.0, 255.0 - base))
        base_of[i] = base
flashes = int((gain < 0).sum())
print(f"{len(y)} frames, {flashes} flash frames tamed (keep {KEEP})", flush=True)
# pass 2: scale the flash frames, the rest pass through untouched
dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", fps, "-i", "-",
                        "-i", src, "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
size = w * h * 3
i = 0
while True:
    buf = dec.stdout.read(size)
    if len(buf) < size:
        break
    g = gain[i] if i < len(gain) else 1.0
    if g < 0:  # a flash: lift the veil, then lay back KEEP of it (plain darkening left a flat grey wash)
        v = -g
        orig = np.frombuffer(buf, np.uint8).astype(np.float32)
        clean = (orig - 255.0 * v) / (1.0 - v)
        lifted = np.clip(clean * (1.0 - KEEP * v) + 255.0 * KEEP * v, 0, 255)
        # the frame's brightness is pinned to its target (the ground plus KEEP of the rise): the veil model alone
        # over-darkened 63 frames of the full-song montage below the frames around them, a dark blink instead of a
        # flash; blending the lifted frame with the original hits the target and never goes under it
        want = (base_of[i] + KEEP * (y[i] - base_of[i])) / y[i]  # the share of the original brightness to keep
        o_l, c_l = orig.mean(), lifted.mean()
        if o_l - c_l > 1e-3:
            a = float(np.clip((o_l - want * o_l) / (o_l - c_l), 0.0, 1.0))
            lifted = a * lifted + (1.0 - a) * orig
        buf = np.clip(lifted, 0, 255).astype(np.uint8).tobytes()
    enc.stdin.write(buf)
    i += 1
enc.stdin.close()
enc.wait()
dec.wait()
print("wrote", out, i, "frames", flush=True)
