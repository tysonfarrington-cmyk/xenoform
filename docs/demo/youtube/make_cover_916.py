"""A 9:16 cover for the X post (Tys, 30 Oct: "is it possible to change that thumbnail it lands on to the beatle"): X has
no cover picker and shows the first frame, so the 9:16 demo opens on this for a tenth of a second. The gold scarab
(gold cut 45b4eb51 at 11.0 s) on its own blurred ground, the product's type above it as on the YouTube thumbnail.

    python make_cover_916.py
"""
from pathlib import Path

from PIL import Image, ImageFilter

import make_thumbs_xf as T

HERE = Path(__file__).parent
frame = Image.open(HERE / "frames" / "scarab_11.0.png").convert("RGBA")
W, H = 1080, 1920
bg = frame.resize((int(frame.width * H / frame.height), H), Image.LANCZOS)
bg = bg.crop(((bg.width - W) // 2, 0, (bg.width - W) // 2 + W, H)).filter(ImageFilter.GaussianBlur(40))
img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
img.alpha_composite(bg)
img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 120)))
fg = frame.resize((W + 520, int(frame.height * (W + 520) / frame.width)), Image.LANCZOS)
fg = fg.crop((260, 0, 260 + W, fg.height))
fade = 200  # the strip melts into its blurred ground top and bottom (no hard edge)
mask = Image.new("L", fg.size, 255)
px = mask.load()
for y in range(fg.height):
    a = int(255 * max(0.0, min(1.0, y / fade, (fg.height - 1 - y) / fade)))
    for x in range(fg.width):
        px[x, y] = a
fg.putalpha(mask)
img.alpha_composite(fg, (0, 760))
T.shade(img, lambda x, y: max(0.0, (0.42 - y) / 0.42) * 0.9)
T.spaced(img, (82, 300), "OPEN SOURCE  ·  COMFYUI", 34, 500, T.GREY, 0.18)
T.spaced(img, (74, 350), "Xenoform", 190, 700, T.WHITE, -0.045)
T.rule(img, 84, 600, 84)
T.spaced(img, (82, 636), "Song in. Music video out.", 62, 400, T.WHITE, -0.01)
img.convert("RGB").save(HERE / "cover_916.png")
print("cover_916.png")
