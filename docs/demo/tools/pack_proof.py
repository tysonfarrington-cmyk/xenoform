"""The curated film pack's proof (docs/MUSIC_VIDEO_PLAN.md section 8, item 16): the pack's contact sheet, and a song made
whole in clips on the new pack stacked against the same song on the first pack.

    python pack_proof.py sheet <pack folder> <out.jpg> [--manifest configs/film_pack.json]
    python pack_proof.py stack <out dir> --jobs <the desk's work/ui/jobs> --old <the first pack's clips_proof dir>

``sheet``: one tile a clip, the frame 40 percent in, cover-cropped to 16:9 as a cut frames it, labelled with the clip's
label, the film and its year, colour or black-and-white, its mood and seconds, and the clip's full path.

``stack``: after ``clips_proof.py make <out dir> --modes breathe`` on the new pack, ``clips_proof.proof`` on it (the cut with
the song, a copy under 25 MiB, the tile sheet, the strip, the shot table, the still picture of this cut and of the old
one), then the first pack's Breathe cut above the new pack's at full width, the song under them, a cut-rhythm strip under
each panel with a playhead (``pacing_proof.stacked_video``), with a copy under 25 MiB, and ``pack_proof.json``: both
cuts' totals and shot tables side by side.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SMALL_MIB = 24.5


def _frame(path: Path, t: float, w: int, h: int):
    from PIL import Image

    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                          f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=rgb24", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    if len(raw) < w * h * 3:
        return Image.new("RGB", (w, h), (60, 0, 0))
    return Image.frombytes("RGB", (w, h), raw[: w * h * 3])


def sheet(folder: Path, dest: Path, manifest: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    from xenoform import film_pack

    data = json.loads(manifest.read_text(encoding="utf-8"))
    fonts = "C:/Windows/Fonts/"

    def font(size: int, bold: bool = False):
        try:
            return ImageFont.truetype(fonts + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)
        except OSError:
            return ImageFont.load_default()

    try:
        mono = ImageFont.truetype(fonts + "consola.ttf", 12)
    except OSError:
        mono = ImageFont.load_default()
    clips = data["clips"]
    cols, tw, th, lab, head = 5, 384, 216, 112, 70
    rows = (len(clips) + cols - 1) // cols
    img = Image.new("RGB", (cols * tw, head + rows * (th + lab)), (12, 12, 16))
    d = ImageDraw.Draw(img)
    colour = sum(1 for c in clips if c.get("colour"))
    d.text((14, 10), f"The free film pack, version {data.get('version', 1)}: {len(clips)} clips ({colour} colour, "
                     f"{len(clips) - colour} black-and-white) from {len({c['source'] for c in clips})} sources",
           font=font(24, True), fill=(245, 243, 255))
    d.text((14, 42), f"{folder}  (each tile the frame 40 percent in, cover-cropped to 16:9 as a cut frames it)",
           font=font(15), fill=(190, 188, 210))
    for k, c in enumerate(clips):
        path = folder / film_pack.clip_name(c, k)
        s = data["sources"][c["source"]]
        x, y = (k % cols) * tw, head + (k // cols) * (th + lab)
        img.paste(_frame(path, film_pack.probe_seconds(path) * 0.4, tw, th), (x, y))
        year = f" ({s['year']})" if s.get("year") else ""
        tone = "colour" if c.get("colour") else "black-and-white"
        d.text((x + 8, y + th + 4), f"{k + 1:02d}  {c.get('label') or c['id']}", font=font(17, True), fill=(250, 248, 255))
        d.text((x + 8, y + th + 28), f"{s.get('title', c['source'])}{year}"[:52], font=font(14), fill=(215, 212, 235))
        d.text((x + 8, y + th + 48), f"{tone} · {c.get('mood', '')} · {c['seconds']} s" + (" · living" if c.get("living") else ""),
               font=font(14, True), fill=(255, 190, 90) if tone == "colour" else (190, 190, 190))
        for j, line in enumerate(textwrap.wrap(str(path), 52)[:3]):  # the full path, a tile wide
            d.text((x + 8, y + th + 66 + j * 14), line, font=mono, fill=(150, 148, 170))
    img.save(dest, quality=88)
    return dest


def stack(out: Path, *, jobs: Path, old: Path) -> dict:
    from xenoform import song_assemble

    import clips_proof
    from pacing_proof import stacked_video

    old_mp4 = old / "clips_breathe.mp4"
    summary = clips_proof.proof(out, jobs=jobs, demos=[(old_mp4, "24-clip pack, Breathe 1.0 (Desktop/xeno_clips_1nov)")])
    new = summary["songs"]["breathe"]
    before = json.loads((old / "clips_proof_summary.json").read_text(encoding="utf-8"))["songs"]["breathe"]
    length = min(float(new["seconds"]), float(before["seconds"]))
    stacked = out / "clips_24_over_40.mp4"
    stacked_video(old_mp4, old / "clips_breathe_strip.png", out / "clips_breathe.mp4", out / "clips_breathe_strip.png", stacked,
                  length, labels=("The first pack, 24 clips", "The curated pack, 40 clips"))
    song_assemble.small_copy(stacked, out / "clips_24_over_40_small.mp4", max_mib=SMALL_MIB, height=720)
    side = {"old": {"totals": before["totals"], "table": before["table"], "still": before["still"], "file": str(old_mp4)},
            "new": {"totals": new["totals"], "table": new["table"], "still": new["still"], "file": str(out / "clips_breathe.mp4")},
            "length_s": round(length, 2)}
    (out / "pack_proof.json").write_text(json.dumps(side, indent=1), encoding="utf-8")
    print("stacked", stacked, flush=True)
    return side


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("sheet", "stack"))
    ap.add_argument("where", type=Path, help="sheet: the pack folder; stack: the out dir")
    ap.add_argument("dest", type=Path, nargs="?", help="sheet: the jpg to write")
    ap.add_argument("--manifest", type=Path, default=ROOT / "configs" / "film_pack.json")
    ap.add_argument("--jobs", type=Path)
    ap.add_argument("--old", type=Path)
    a = ap.parse_args()
    if a.what == "sheet":
        print(sheet(a.where, a.dest, a.manifest))
    else:
        stack(a.where, jobs=a.jobs, old=a.old)


if __name__ == "__main__":
    main()
