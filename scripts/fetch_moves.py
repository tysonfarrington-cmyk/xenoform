"""Download the Moves library driving clips listed in configs/moves.json into library/moves/.

The clips are free to use (Pexels / Mixkit licences) but may not be redistributed as standalone
files, so the repo ships this script instead of the mp4s. Usage:
    python scripts/fetch_moves.py            # every clip not marked "avoid"
    python scripts/fetch_moves.py px_8688817 # just these
    python scripts/fetch_moves.py --all      # include "avoid" clips
"""
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "configs" / "moves.json").read_text(encoding="utf-8"))
dest_dir = ROOT / "library" / "moves"
dest_dir.mkdir(parents=True, exist_ok=True)
want = [a for a in sys.argv[1:] if not a.startswith("--")]
for clip in data["clips"]:
    if want and clip["id"] not in want:
        continue
    if not want and clip["fit"] == "avoid" and "--all" not in sys.argv:
        continue
    dest = dest_dir / f"{clip['id']}.mp4"
    if dest.is_file() and dest.stat().st_size > 100_000:
        print("have", clip["id"])
        continue
    req = urllib.request.Request(clip["download"], headers={"User-Agent": "Mozilla/5.0 (Xenoform moves fetch)"})
    print("get ", clip["id"], clip["download"], flush=True)
    with urllib.request.urlopen(req, timeout=120) as r, open(dest.with_suffix(".part"), "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    dest.with_suffix(".part").replace(dest)
    print("  ->", dest, dest.stat().st_size, "bytes;", clip["attribution"])
