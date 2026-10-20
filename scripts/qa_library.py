"""Mark library footage quality in assets/library/manifest.json (size, sharpness, motion, soft).

    python scripts/qa_library.py          # report only
    python scripts/qa_library.py --write  # also write "qa" into each local item
CPU only (ffmpeg + numpy). Items that are not downloaded are skipped.
"""
from __future__ import annotations

import argparse
import json

from xenoform import footage


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    data = footage.load_manifest()
    soft = 0
    for item in data.get("items") or []:
        path = footage.local_path(item)
        if not path.is_file():
            continue
        try:
            q = footage.qa_item(item)
        except Exception as exc:
            print(f"{item['id']}: {exc}")
            continue
        soft += bool(q.get("soft"))
        print(f"{item['id']}: {q['width']}x{q['height']} sharp {q['sharpness']} motion {q.get('motion_score', '-')} "
              f"{q['verdict']}{' SOFT' if q.get('soft') else ''}")
        if args.write:
            item["qa"] = q
    if args.write:
        footage.MANIFEST.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(f"{soft} soft item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
