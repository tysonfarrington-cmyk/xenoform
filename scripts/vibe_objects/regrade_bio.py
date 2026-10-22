"""Bioluminescent stills: shift the Z-Image cyan-green glow toward the registry look (teal and violet),
compositions untouched. Greens (hue 70..165) pull to teal (~182); cyans stay teal and deeper blues
(180..235) ramp up to +80 deg into violet. usage: regrade_bio.py <raw stills dir> <out dir>  (needs Pillow + numpy)"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
dst.mkdir(exist_ok=True)
for f in sorted(src.glob("*.jpg")):
    im = Image.open(f).convert("RGB")
    hsv = np.asarray(im.convert("HSV")).astype(np.float32)
    h, s = hsv[..., 0] * 360 / 255, hsv[..., 1]
    green = (h >= 70) & (h < 165) & (s > 25)
    blue = (h >= 165) & (h <= 235) & (s > 25)
    nh = h.copy()
    nh[green] = 182 + (h[green] - 165) * 0.15
    nh[blue] = h[blue] + 80 * np.clip((h[blue] - 180) / 40, 0, 1)
    hsv[..., 0] = (nh % 360) * 255 / 360
    hsv[..., 1] = np.clip(s * 1.05, 0, 255)
    Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB").save(dst / f.name, quality=93)
    print(f.name)
