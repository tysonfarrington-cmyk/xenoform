"""Copy what the pack folder carries for an install without the repository: run from the repository after a change.

    python comfy_pack/tools/sync_bundle.py          (writes comfy_pack/data, comfy_pack/objects, comfy_pack/examples)
    python comfy_pack/tools/sync_bundle.py --check  (exits 1 when a copy differs from what it would write)

- ``data/vibes.json``: the registry's fields the pack reads (look, negative, LTX tuning, pool, name), from configs/vibes.json.
- ``data/autotune.json``: configs/autotune.json as it is (the per-vibe tuning and the bad pairs).
- ``objects/``: the Liquid chrome vibe's curated chain (its first twelve stills), at 768x432, with their manifest rows.
- ``examples/demo.wav``: the bundled demo song (synthesised by ``xenoform synth``; CREDITS.md).
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
REPO = PACK.parent
VIBE = "chrome-mercury"
COUNT = 12
SIZE = (768, 432)
FIELDS = ("id", "name", "line", "palette", "dark", "tone", "look", "negative", "ltx", "pool", "ready", "featured", "tags")


def vibes_json() -> str:
    reg = json.loads((REPO / "configs" / "vibes.json").read_text(encoding="utf-8"))
    rows = [{k: v[k] for k in FIELDS if k in v} for v in reg.get("vibes") or []]
    return json.dumps({"version": reg.get("version"), "source": "configs/vibes.json (comfy_pack/tools/sync_bundle.py)",
                       "vibes": rows}, indent=1, ensure_ascii=False) + "\n"


def autotune_json() -> str:
    return (REPO / "configs" / "autotune.json").read_text(encoding="utf-8")


def manifest_rows() -> list[dict]:
    manifest = json.loads((REPO / "src" / "xenoform" / "ui_static" / "objects" / "objects.json").read_text(encoding="utf-8"))
    return [r for r in manifest[VIBE] if not r.get("kind")][:COUNT]


def still_bytes(row: dict) -> bytes:
    from PIL import Image

    src = REPO / "src" / "xenoform" / "ui_static" / "objects" / row["file"]
    with Image.open(src) as im:
        im = im.convert("RGB").resize(SIZE, Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()


def plan() -> dict[Path, bytes]:
    rows = manifest_rows()
    out = {PACK / "data" / "vibes.json": vibes_json().encode("utf-8"),
           PACK / "data" / "autotune.json": autotune_json().encode("utf-8"),
           PACK / "objects" / "objects.json": (json.dumps({VIBE: rows}, indent=1, ensure_ascii=False) + "\n").encode("utf-8")}
    for row in rows:
        out[PACK / "objects" / row["file"]] = still_bytes(row)
    out[PACK / "examples" / "demo.wav"] = (REPO / "examples" / "demo.wav").read_bytes()
    return out


def same_copy(path: Path, data: bytes) -> bool:
    """True when the copy on disk is ``data``. A JSON copy is compared with its newlines normalised: a Windows clone
    with core.autocrlf checks it out with CRLF, which is the same bundle."""
    got = path.read_bytes()
    if got == data:
        return True
    return path.suffix == ".json" and got.replace(b"\r\n", b"\n") == data.replace(b"\r\n", b"\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="say what differs and exit 1, write nothing")
    args = ap.parse_args()
    files = plan()
    stale = [p for p, data in files.items() if not p.is_file() or (p.suffix != ".jpg" and not same_copy(p, data))]
    if args.check:
        for p in stale:
            print(f"stale: {p.relative_to(REPO)}")
        return 1 if stale else 0
    keep = {p for p in files if p.parent.name == VIBE}
    folder = PACK / "objects" / VIBE
    if folder.is_dir():
        for old in folder.iterdir():
            if old not in keep:
                old.unlink()
    for p, data in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    print(f"wrote {len(files)} files under {PACK.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
