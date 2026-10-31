"""YouTube thumbnails for the two Xenoform videos (30 Oct): a montage frame moved aside on its own mirrored ground, a
soft dark field, and the product's own type: the Xenoform wordmark in Space Grotesk Bold (tight, as the desk's title
card sets it), a line in Space Grotesk Regular and a small spaced-caps label, no outlines (Tys: "make it more sleek as
this isnt a sort of clip naily sort of video more of a product demo"). The demo has the gold scarab from the outro
(gold cut 45b4eb51 at 11.0 s, Tys: "use the beetle"), the long the dragon in smoke (b90b9735 at 0.4 s). 1280x720 JPEG.

    python make_thumbs_xf.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
F = HERE / "fonts"  # Space Grotesk from src/xenoform/ui_static/fonts, woff2 to ttf (fontTools)
WHITE, GREY, ACCENT = (255, 255, 255), (196, 200, 210), (178, 148, 255)


def spaced(img, xy, s, size, weight, fill, track=0.0, anchor="l"):
    """Text with tracking (em), drawn a glyph at a time; anchor l or r on the baseline-ish top."""
    f = ImageFont.truetype(str(F / f"space-grotesk-{weight}.ttf"), size)
    gap = track * size
    width = sum(f.getlength(c) for c in s) + gap * (len(s) - 1)
    x = xy[0] - width if anchor == "r" else xy[0]
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd, d = ImageDraw.Draw(glow), ImageDraw.Draw(img)
    for c in s:
        gd.text((x, xy[1] + 3), c, font=f, fill=(0, 0, 0, 150))
        x += f.getlength(c) + gap
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    x = xy[0] - width if anchor == "r" else xy[0]
    for c in s:
        d.text((x, xy[1]), c, font=f, fill=fill)
        x += f.getlength(c) + gap
    return width


def shade(img, fn):
    w, h = img.size
    small = Image.new("L", (w // 8, h // 8))
    px = small.load()
    for y in range(h // 8):
        for x in range(w // 8):
            px[x, y] = int(255 * max(0.0, min(1.0, fn(x / (w // 8), y / (h // 8)))))
    m = small.resize((w, h), Image.BILINEAR).filter(ImageFilter.GaussianBlur(14))
    img.alpha_composite(Image.composite(Image.new("RGBA", (w, h), (6, 6, 10, 255)), Image.new("RGBA", (w, h), (0, 0, 0, 0)), m))


def moved(frame, dx):
    img = Image.open(frame).convert("RGBA").resize((1280, 720), Image.LANCZOS)
    out = Image.new("RGBA", (1280, 720), (0, 0, 0, 255))
    if dx > 0:
        out.alpha_composite(img.crop((0, 0, dx, 720)).transpose(Image.FLIP_LEFT_RIGHT), (0, 0))
        out.alpha_composite(img, (dx, 0))
    else:
        out.alpha_composite(img, (dx, 0))
        out.alpha_composite(img.crop((1280 + dx, 0, 1280, 720)).transpose(Image.FLIP_LEFT_RIGHT), (1280 + dx, 0))
    return out


def rule(img, x, y, w, anchor="l"):
    d = ImageDraw.Draw(img)
    x0 = x - w if anchor == "r" else x
    d.rounded_rectangle((x0, y, x0 + w, y + 4), radius=2, fill=ACCENT)


def demo():
    img = moved(HERE / "frames" / "scarab_11.0.png", 360)
    shade(img, lambda x, y: (0.56 - x) / 0.56 * 0.92)
    spaced(img, (70, 190), "OPEN SOURCE  ·  COMFYUI", 26, 500, GREY, 0.18)
    spaced(img, (64, 232), "Xenoform", 140, 700, WHITE, -0.045)
    rule(img, 72, 418, 64)
    spaced(img, (70, 446), "Song in.", 50, 400, WHITE, -0.01)
    spaced(img, (70, 506), "Music video out.", 50, 400, GREY, -0.01)
    img.convert("RGB").save(HERE / "thumb_demo.jpg", quality=92)


def long():
    img = moved(HERE / "frames" / "dragon_0.4.png", -330)
    shade(img, lambda x, y: (x - 0.45) / 0.4 * 0.97)
    spaced(img, (1212, 190), "FULL WALKTHROUGH", 26, 500, GREY, 0.18, "r")
    spaced(img, (1216, 244), "Xenoform", 118, 700, WHITE, -0.045, "r")
    rule(img, 1210, 400, 64, "r")
    spaced(img, (1212, 430), "How it works,", 44, 400, WHITE, -0.01, "r")
    spaced(img, (1212, 482), "how it's built.", 44, 400, GREY, -0.01, "r")
    img.convert("RGB").save(HERE / "thumb_long.jpg", quality=92)


if __name__ == "__main__":
    demo()
    long()
    for n in ("thumb_demo.jpg", "thumb_long.jpg"):
        print(n, (HERE / n).stat().st_size)
