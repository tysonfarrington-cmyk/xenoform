"""Ship stills grown on this machine into the repo's seed set, so a fresh clone can reproduce a chain that pins them.

The grown set (``work/ui/objects``, git-ignored) holds every still the app has rendered; the stills that are on
screen in a finished cut, a pinned chain or a loved morph are copied byte for byte (same file name, so a pin, a
recipe or a chain preset names the same file on both sides) into ``ui_static/objects/<vibe>/`` and get one row
each in ``objects.json``: ``file``, ``noun``, ``finish``, ``source`` (model, seed, prompt file, date) and, for a
wide frame, ``kind: "scene"``. Rows are appended after the vibe's existing ones, so ``00_orb`` and ``01_nautilus``
(which ``make_library.py`` reads) stay first. On a machine that has the same file in its grown set,
``stills.catalogue`` lists the grown copy and hides the shipped twin.

    python scripts/vibe_objects/ship_grown.py --list scripts/vibe_objects/shipped_31oct.txt --grown work/ui/objects \
        [--v2 ~/Desktop/xeno_vibe_stills_v2] [--dry]

``--list`` is one ``<vibe>/<name>.jpg`` per line (``#`` starts a comment). ``--v2`` is the 24 Oct hand-made sets
(``<vibe>/NN_noun.png``, ComfyUI's metadata inside): the seed of a still the desk imported from there (its grown row
has none) is read from the png. Running it twice changes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OBJECTS = ROOT / "src" / "xenoform" / "ui_static" / "objects"
SIZE = (1024, 576)
MIN_BYTES = 8_000  # tests/test_vibe_registry.py: every shipped jpg is over 8 KB
BANNED = ("rocket", "sputnik", "satellite", "film reel", "rotary", "vintage", "vinyl", "ringed planet", "gear", "clock", "phone")
MODEL = "Z-Image Turbo (Apache 2.0)"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def slug(noun: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", noun.lower()).strip("_")


def v2_seed(v2: Path | None, vibe: str, noun: str) -> int | None:
    """The seed in the 24 Oct png this still was imported from (``<vibe>/NN_<noun slug>.png``), else None."""
    if not v2 or not (v2 / vibe).is_dir():
        return None
    for png in sorted((v2 / vibe).glob("*.png")):
        if re.sub(r"^\d+_", "", png.stem) != slug(noun):
            continue
        try:
            graph = json.loads(Image.open(png).info.get("prompt") or "{}")
        except (OSError, ValueError):
            return None
        for node in graph.values():
            seed = (node.get("inputs") or {}).get("seed")
            if node.get("class_type") == "KSampler" and isinstance(seed, int):
                return seed
    return None


def source_of(vibe: str, row: dict, v2: Path | None) -> str:
    made = str(row.get("made") or "")
    scene = row.get("kind") == "scene"
    seed = row.get("seed")
    imported = str(row.get("source") or "").startswith(f"{MODEL}, imported from")
    if imported:
        seed = v2_seed(v2, vibe, str(row.get("noun") or ""))
        text = f"{MODEL}, seed {seed}, " if seed is not None else f"{MODEL}, seed unrecorded, "
        return text + (f"{SIZE[0]}x{SIZE[1]}, scripts/vibe_objects/gen_v2.py (the vibe's featured_prompts.json prefix and subject "
                       f"sentence), made 2026-10-24, imported into the grown set {made}")
    text = f"{MODEL}, seed {seed}, " if seed is not None else f"{MODEL}, seed unrecorded, "
    prompt = f"configs/still_prompts.json {vibe}" + (" scene prefix" if scene else " prefix and subject sentence")
    own = ", typed in the desk as an own shape" if row.get("own") else ""
    return f"{text}{SIZE[0]}x{SIZE[1]}, prompt {prompt}{own}, grown {made}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--list", required=True, help="text file: one <vibe>/<name>.jpg per line")
    ap.add_argument("--grown", required=True, help="the grown set's folder (work/ui/objects), with its stills.json")
    ap.add_argument("--v2", default="", help="the 24 Oct xeno_vibe_stills_v2 folder, for the seeds of imported stills")
    ap.add_argument("--dry", action="store_true", help="check and print, copy and write nothing")
    args = ap.parse_args(argv)

    grown = Path(args.grown)
    v2 = Path(args.v2) if args.v2 else None
    wanted = [ln.split("#")[0].strip() for ln in Path(args.list).read_text(encoding="utf-8").splitlines()]
    wanted = [w.replace("\\", "/") for w in wanted if w]
    index = read_json(grown / "stills.json")
    rows_by_file = {r["file"]: r for rows in index.values() for r in rows}
    manifest_path = OBJECTS / "objects.json"
    manifest: dict[str, list[dict]] = read_json(manifest_path)
    listed = {r["file"] for rows in manifest.values() for r in rows}
    finish = {v: Counter(r["finish"] for r in rows).most_common(1)[0][0] for v, rows in manifest.items() if rows}

    added, copied, skipped = 0, 0, 0
    problems: list[str] = []
    for f in wanted:
        vibe, _, name = f.partition("/")
        src, dest = grown / f, OBJECTS / f
        row = rows_by_file.get(f)
        if row is None or not src.is_file():
            problems.append(f"{f}: not in the grown set")
            continue
        noun = str(row.get("noun") or "")
        if any(b in noun.lower() for b in BANNED):
            problems.append(f"{f}: banned noun {noun!r}")
            continue
        if vibe not in finish:
            problems.append(f"{f}: {vibe} has no shipped pool to join")
            continue
        try:
            with Image.open(src) as im:
                ok = im.format == "JPEG" and im.size == SIZE
        except OSError:
            ok = False
        if not ok or src.stat().st_size <= MIN_BYTES:
            problems.append(f"{f}: not a {SIZE[0]}x{SIZE[1]} jpg over {MIN_BYTES} bytes")
            continue
        if f in listed:
            skipped += 1
            continue
        new = {"file": f, "noun": noun, "finish": finish[vibe], "source": source_of(vibe, row, v2)}
        if row.get("kind") == "scene":
            new["kind"] = "scene"
        if not args.dry:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.is_file():
                shutil.copyfile(src, dest)
                copied += 1
        manifest[vibe].append(new)
        listed.add(f)
        added += 1
    for p in problems:
        print("PROBLEM", p, file=sys.stderr)
    if not args.dry and added:
        manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(rows) for rows in manifest.values())
    print(f"{added} rows added, {copied} files copied, {skipped} already shipped, {len(problems)} problems; {total} rows in all")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
