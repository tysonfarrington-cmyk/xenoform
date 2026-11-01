"""The proof of a cloud_scene_pairs.py run: each scene pair's old Cloud clip above its new one, frames at 0, 25, 50, 75
and 100 percent, each row labelled with its clip's full path; the new clips copied beside the sheet. CPU only: it reads
the run's report and the clips and sends nothing, so it spends no credits.

    python docs/demo/tools/cloud_scene_pairs_sheet.py --report <run folder>/report.json \
        --old-root <the old job folder whose clips the labels name> --dest <output folder>
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

COLS = (0.0, 0.25, 0.5, 0.75, 1.0)
TW, TH = 216, 384          # a 576x1024 portrait frame at 0.375
GUT = 10
BG = (18, 18, 20)
FG = (235, 235, 235)
DIM = (160, 160, 165)
OLD_C = (255, 170, 90)
NEW_C = (120, 220, 140)


def font(size: int, bold: bool = False):
    for name in (("consolab.ttf" if bold else "consola.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def frames(clip: Path) -> tuple[np.ndarray, float]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height,r_frame_rate",
                            "-of", "json", str(clip)], capture_output=True, text=True, check=True).stdout
    st = json.loads(probe)["streams"][0]
    w, h = int(st["width"]), int(st["height"])
    num, den = (int(x) for x in st["r_frame_rate"].split("/"))
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3), num / max(den, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--old-root", required=True, help="the old job folder whose clips the labels name (read only)")
    ap.add_argument("--dest", required=True)
    args = ap.parse_args()
    rep = json.loads(Path(args.report).read_text(encoding="utf-8"))
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    old_root = Path(args.old_root)

    rows = []
    for r in rep["results"]:
        if not r.get("clip"):
            continue
        i = int(r["pair"])
        new_clip = dest / f"pair{i:02d}_new.mp4"
        shutil.copy2(r["clip"], new_clip)
        old_clip = old_root / "simple" / f"cloud{i:02d}.mp4"
        rows.append((r, old_clip, new_clip))

    f_title, f_head, f_lab, f_col = font(22, True), font(17, True), font(15), font(13)
    head_h, lab_h, col_h, gap = 50, 24, 18, 26
    width = len(COLS) * TW + (len(COLS) + 1) * GUT
    pair_h = head_h + 2 * (lab_h + col_h + TH + 6) + gap
    title_h = 92
    sheet = Image.new("RGB", (width, title_h + pair_h * len(rows)), BG)
    d = ImageDraw.Draw(sheet)
    d.text((GUT, 10), f"The {len(rows)} scene pairs of job {Path(rep['job']).name} ({rep['vibe']}) again on Cloud Final",
           font=f_title, fill=FG)
    d.text((GUT, 42), "Each pair: OLD (the clip the cut recorded) above NEW (sent again with the scene handling as it is now:",
           font=f_col, fill=DIM)
    d.text((GUT, 60), "the same stills, seed and length). Columns: 0 / 25 / 50 / 75 / 100 % of the clip.", font=f_col, fill=DIM)
    y = title_h
    for r, old_clip, new_clip in rows:
        a, b = r["stills"]
        new = r["tries"][-1]["new"] or {}
        d.text((GUT, y + 4), f"Pair {r['pair']:02d} (shot {r['pair']}): {a['noun']} ({a['kind']}) -> {b['noun']} ({b['kind']})",
               font=f_head, fill=FG)
        d.text((GUT, y + 26), f"seed {r['seed']}  ·  {r['style']}  ·  img_compression start/end: old {r['old']['img_compression']}, "
                              f"new {new.get('img_compression')}  ·  end guide {new.get('end_strength')}", font=f_lab, fill=DIM)
        y += head_h
        for tag, clip, colour in (("OLD", old_clip, OLD_C), ("NEW", new_clip, NEW_C)):
            arr, fps = frames(clip)
            n = len(arr)
            d.text((GUT, y + 3), f"{tag}  {clip}  ({n} frames, {n / fps:.2f} s)", font=f_lab, fill=colour)
            y += lab_h
            for c, p in enumerate(COLS):
                k = int(round(p * (n - 1)))
                x = GUT + c * (TW + GUT)
                d.text((x, y + 1), f"{int(p * 100)} %  frame {k}", font=f_col, fill=DIM)
                tile = Image.fromarray(arr[k]).resize((TW, TH), Image.LANCZOS)
                sheet.paste(tile, (x, y + col_h))
            y += col_h + TH + 6
        y += gap
    out = dest / "scene_pairs_old_vs_new_sheet.jpg"
    sheet.save(out, quality=90)
    print(out, sheet.size)
    for _, o, nclip in rows:
        print(o, "->", nclip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
