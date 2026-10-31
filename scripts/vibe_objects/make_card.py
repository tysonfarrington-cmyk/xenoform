"""Vibe cards from finished cuts (Tys, 29 Oct 2026: "update thumbnails for vibes"): one frame a vibe, the centre square of
the frame (the object sits in the middle) on a 1280x800 ground made of the same frame blurred, like the walkthrough's
one-clip picture. Writes src/xenoform/ui_static/vibes/<id>.jpg (the tile is 16:10, background-size cover) after copying
the old file to --old. The desk serves /static/vibes/* no-cache, so a reload shows the new card.

    python scripts/vibe_objects/make_card.py scripts/vibe_objects/picks_cards.json [--jobs work/ui/jobs] [--old DIR] [--dry]

``picks`` is a list of ``{"vibe": id, "job": <job id> | "video": <path>, "t": seconds, "side": px, "cy": px}``. A ``job`` is
``<jobs>/<job>/xenoform.mp4``. The square is ``side`` pixels of the source (default its short side: the 1080x1080 centre of
a 9:16 or a 16:9 frame; smaller zooms in on the object) centred on the line ``cy`` (default the middle). The 13 cards of
29 Oct came from the 9:16 example and showcase cuts (picks_thumbs.json beside this file); the 31 Oct cards are 16:9
frames of the montage renders (picks_cards.json). Both run with the same defaults.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIBES = ROOT / "src" / "xenoform" / "ui_static" / "vibes"
CARD = (1280, 800)
MIN_BYTES = 20_000  # tests/test_vibe_registry.py: every card is over 20 KB


def size_of(video: Path) -> tuple[int, int]:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                                   "-of", "csv=p=0", str(video)], text=True).strip().split(",")
    return int(out[0]), int(out[1])


def make(pick: dict, jobs: Path, old: Path, dry: bool) -> Path:
    video = Path(pick["video"]) if pick.get("video") else jobs / str(pick["job"]) / "xenoform.mp4"
    if not video.is_file():
        raise SystemExit(f"{pick['vibe']}: {video} is missing")
    w, h = size_of(video)
    side = int(pick.get("side") or min(w, h))
    cy = int(pick.get("cy") or h // 2)
    left, top = (w - side) // 2, min(max(cy - side // 2, 0), h - side)
    dest = VIBES / f"{pick['vibe']}.jpg"
    fc = (f"[0:v]split[a][b];[a]scale={CARD[0]}:{CARD[1]}:force_original_aspect_ratio=increase,crop={CARD[0]}:{CARD[1]},"
          f"gblur=sigma=40,eq=brightness=-0.12:saturation=0.85[bg];"
          f"[b]crop={side}:{side}:{left}:{top},scale={CARD[1]}:{CARD[1]}:flags=lanczos[fg];"
          f"[bg][fg]overlay={(CARD[0] - CARD[1]) // 2}:0[out]")
    print(f"{dest.name:22s} from {video.parent.name} at {float(pick['t']):.1f} s ({w}x{h}, square {side} at {left},{top})")
    if dry:
        return dest
    old.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and not (old / dest.name).is_file():
        shutil.copyfile(dest, old / dest.name)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{float(pick['t']):.3f}", "-i", str(video), "-frames:v", "1",
                    "-filter_complex", fc, "-map", "[out]", "-q:v", "3", str(dest)], check=True)
    if dest.stat().st_size <= MIN_BYTES:
        raise SystemExit(f"{dest} is {dest.stat().st_size} bytes: under the {MIN_BYTES} the registry test wants")
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("picks", help="a json list of picks")
    ap.add_argument("--jobs", default=str(ROOT / "work" / "ui" / "jobs"))
    ap.add_argument("--old", default=str(ROOT / "work" / "ui" / "cards_old"), help="where the replaced cards are copied first")
    ap.add_argument("--dry", action="store_true", help="print what would be cut and write nothing")
    args = ap.parse_args(argv)
    picks = json.loads(Path(args.picks).read_text(encoding="utf-8"))
    for pick in picks:
        make(pick, Path(args.jobs), Path(args.old), args.dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
