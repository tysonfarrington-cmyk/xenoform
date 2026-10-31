"""YouTube thumbnails for the full-song montage as its own music video (30 Oct, Tys: "the 16.9 version, I guess that
would be good to upload to YouTube as a song"): the same product type as the demo and walkthrough thumbnails
(make_thumbs_xf.py), the song's name as the wordmark. Two variants to choose from: the glowing jellyfish that opens
the video (2.5 s) and the gold bird of the outro (229.6 s). 1280x720 JPEG.

    python make_thumb_song.py
"""
from make_thumbs_xf import GREY, HERE, WHITE, moved, shade, spaced
from PIL import ImageDraw

CYAN, GOLD = (120, 228, 255), (255, 196, 92)


def rule(img, x, y, w, fill, anchor="l"):
    x0 = x - w if anchor == "r" else x
    ImageDraw.Draw(img).rounded_rectangle((x0, y, x0 + w, y + 4), radius=2, fill=fill)


def jelly():
    img = moved(HERE / "frames" / "song_jelly_2.5.png", 400)
    shade(img, lambda x, y: (0.56 - x) / 0.56 * 0.92)
    spaced(img, (70, 196), "MUSIC VIDEO  ·  XENOFORM", 26, 500, GREY, 0.18)
    spaced(img, (64, 238), "Glitch Out", 132, 700, WHITE, -0.045)
    rule(img, 72, 418, 64, CYAN)
    spaced(img, (70, 446), "Every beat,", 50, 400, WHITE, -0.01)
    spaced(img, (70, 506), "a new form.", 50, 400, GREY, -0.01)
    img.convert("RGB").save(HERE / "thumb_song_jelly.jpg", quality=92)


def gold():
    img = moved(HERE / "frames" / "song_gold_229.6.png", -400)
    shade(img, lambda x, y: (x - 0.45) / 0.4 * 0.97)
    spaced(img, (1212, 196), "MUSIC VIDEO  ·  XENOFORM", 26, 500, GREY, 0.18, "r")
    spaced(img, (1216, 238), "Glitch Out", 132, 700, WHITE, -0.045, "r")
    rule(img, 1210, 418, 64, GOLD, "r")
    spaced(img, (1212, 446), "Every beat,", 50, 400, WHITE, -0.01, "r")
    spaced(img, (1212, 506), "a new form.", 50, 400, GREY, -0.01, "r")
    img.convert("RGB").save(HERE / "thumb_song_gold.jpg", quality=92)


if __name__ == "__main__":
    jelly()
    gold()
    for n in ("thumb_song_jelly.jpg", "thumb_song_gold.jpg"):
        print(n, (HERE / n).stat().st_size)
