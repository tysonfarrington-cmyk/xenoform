"""Cut the example excerpts in ``examples/cuts/``: about 15 s of a finished 30 s cut, 540x960, silent, 1 to 1.5 MB.

    python scripts/cut_examples.py [--jobs work/ui/jobs] [--only chrome-mercury wet-paint] [--check]

``examples/cuts/cuts.json`` has one row per cut; its ``source`` names the job folder (``<jobs>/<job>/xenoform.mp4``,
the 1080x1920 Cloud Final cut) and the window (``from_s`` to ``to_s``, on shot boundaries of the cut's own plan, so a
loop of the excerpt starts and ends on a still). The settings, the same for every cut:

    ffmpeg -ss FROM -t LENGTH -i xenoform.mp4 -an -vf scale=540:960:flags=lanczos,format=yuv420p
           -c:v libx264 -preset slow -profile:v high -crf N -movflags +faststart <id>.mp4

No audio: seven of the ten example cuts were made on Suno demos that are not bundled (and not credited in this repo),
so the song is not in the file; ``song`` and ``song_label`` in the manifest say what it was. ``N`` is the lowest CRF
from ``START_CRF`` whose file is at most ``MAX_BYTES`` (the first guess is corrected by the size, a few tries); the
CRF and the size are written back to ``cuts.json``.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUTS = ROOT / "examples" / "cuts"
SIZE = (540, 960)
START_CRF = 27
MIN_CRF, MAX_CRF = 22, 38
MIN_BYTES, MAX_BYTES = 1_000_000, 1_500_000
TRIES = 6


def encode(src: Path, start: float, length: float, crf: int, dest: Path) -> int:
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(src), "-an",
        "-vf", f"scale={SIZE[0]}:{SIZE[1]}:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "slow",
        "-profile:v", "high", "-crf", str(crf), "-movflags", "+faststart", str(dest),
    ], check=True)
    return dest.stat().st_size


def cut(src: Path, start: float, length: float, dest: Path) -> tuple[int, int]:
    """(crf, bytes) of the encode that is the lowest CRF at most MAX_BYTES (else the smallest tried)."""
    tmp = Path(tempfile.mkdtemp(prefix="cut_examples_"))
    crf, tried, best = START_CRF, {}, None
    for _ in range(TRIES):
        part = tmp / f"crf{crf}.mp4"
        size = tried[crf] = encode(src, start, length, crf, part)
        if size <= MAX_BYTES and (best is None or crf < best[0]):
            best = (crf, size, part)
        if size > MAX_BYTES:
            nxt = crf + max(1, math.ceil(6 * math.log2(size / (MAX_BYTES * 0.94))))
        elif size < MIN_BYTES and crf > MIN_CRF:
            nxt = crf - max(1, math.floor(6 * math.log2(MIN_BYTES * 1.1 / size)))
        else:
            break
        nxt = max(MIN_CRF, min(MAX_CRF, nxt))
        if nxt in tried or (best and nxt >= best[0] and size <= MAX_BYTES):
            break
        crf = nxt
    if best is None:  # nothing fit: the smallest of what was tried
        crf = max(tried)
        best = (crf, tried[crf], tmp / f"crf{crf}.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(best[2].read_bytes())
    return best[0], best[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jobs", default=str(ROOT / "work" / "ui" / "jobs"))
    ap.add_argument("--only", nargs="*", default=[], help="cut ids to (re)make")
    ap.add_argument("--check", action="store_true", help="only report each file's size against the manifest")
    args = ap.parse_args(argv)
    path = CUTS / "cuts.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in manifest["cuts"] if not args.only or r["id"] in args.only]
    for row in rows:
        dest = CUTS / row["file"]
        if args.check:
            size = dest.stat().st_size if dest.is_file() else 0
            print(f"{row['id']:22s} {size / 1e6:5.2f} MB  manifest {row.get('bytes', 0) / 1e6:5.2f} MB  crf {row.get('crf')}")
            continue
        src = Path(args.jobs) / row["source"]["job"] / "xenoform.mp4"
        if not src.is_file():
            print(f"{row['id']}: {src} is missing", file=sys.stderr)
            return 1
        a, b = float(row["source"]["from_s"]), float(row["source"]["to_s"])
        crf, size = cut(src, a, b - a, dest)
        row["crf"], row["bytes"] = crf, size
        print(f"{row['id']:22s} {a:5.2f}-{b:5.2f} s  crf {crf}  {size / 1e6:5.2f} MB", flush=True)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
