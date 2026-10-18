"""Write a tiny procedural source library so the desk runs without the 500 MB pack.

    python scripts/fetch_sample_library.py
    python scripts/fetch_sample_library.py --out library
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xenoform.source_library import write_sample_library  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a few procedural morph shapes.")
    parser.add_argument("--out", default="library", help="Folder for library.json. Default: ./library")
    parser.add_argument("--force", action="store_true", help="Replace an index that already has many items.")
    args = parser.parse_args(argv)
    try:
        dest = write_sample_library(args.out, force=args.force)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
