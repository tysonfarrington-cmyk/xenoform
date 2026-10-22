"""Regenerate the vibe cards on the judges page from the registry.

``judges.html`` cuts a pre-rendered 4-shot library (``ui_static/library/<id>/{wide,medium,close,reveal}.mp4``)
in the browser, so it lists exactly the vibes that ship their own strip and object pool: the featured
vibes first (in their featured order), then the rest. The block between ``<!-- vibes:start -->`` and
``<!-- vibes:end -->`` is rewritten in place; everything else on the page is left alone.

    python scripts/gen_judges_cards.py            # rewrite
    python scripts/gen_judges_cards.py --check    # exit 1 when the page is stale
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xenoform import vibes  # noqa: E402

STATIC = Path(vibes.__file__).resolve().parent / "ui_static"
PAGE = STATIC / "judges.html"
START, END = "<!-- vibes:start -->", "<!-- vibes:end -->"
SHOTS = ("wide", "medium", "close", "reveal")


def strip_complete(vid: str) -> bool:
    folder = STATIC / "library" / vid
    return all((folder / f"{shot}.mp4").is_file() for shot in SHOTS)


def pool_backed(vid: str) -> bool:
    return (STATIC / "objects" / vid).is_dir()


def listed() -> tuple[list[dict], list[dict]]:
    """(rows to list, rows skipped): featured first, then the rest; a vibe needs its own strip and pool."""
    keep, skipped = [], []
    for row in vibes.catalog():
        if strip_complete(row["id"]) and pool_backed(row["id"]):
            keep.append(row)
        else:
            skipped.append(row)
    return keep, skipped


def card(row: dict) -> str:
    vid = html.escape(row["id"], quote=True)
    dark = " is-dark" if row.get("dark") else ""
    name = html.escape(str(row.get("name") or row["id"]))
    line = html.escape(str(row.get("line") or ""), quote=True)
    return (f'        <button type="button" class="vibe-card{dark}" data-vibe="{vid}" role="radio" aria-checked="false"'
            f' title="{line}"><span class="vibe-thumb" style="background-image:url(vibes/{vid}.jpg)"></span>'
            f"<strong>{name}</strong></button>")


def render(rows: list[dict]) -> str:
    return "\n".join(card(row) for row in rows)


def rewrite(text: str, block: str) -> str:
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    if not rest or END not in rest:
        raise SystemExit(f"{PAGE} has no {START} / {END} markers")
    indent = head[head.rfind("\n") + 1:]
    return f"{head}{START}\n{block}\n{indent}{END}{tail}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when judges.html is stale")
    args = parser.parse_args(argv)
    keep, skipped = listed()
    current = PAGE.read_text(encoding="utf-8")
    updated = rewrite(current, render(keep))
    names = ", ".join(row["id"] for row in keep)
    print(f"{len(keep)} vibes with a library strip: {names}")
    for row in skipped:
        why = "no library strip" if not strip_complete(row["id"]) else "no object pool"
        print(f"  skipped {row['id']}: {why}")
    if updated == current:
        print("judges.html is up to date")
        return 0
    if args.check:
        print("judges.html is stale; run scripts/gen_judges_cards.py")
        return 1
    PAGE.write_text(updated, encoding="utf-8")
    print(f"rewrote {PAGE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
