"""Fetch the real-footage library: python scripts/fetch_library.py [--vibe ocean] [--force]

Public-domain seeds (NASA) are committed already; this re-creates them and downloads any
non-redistributable items (Pexels/Mixkit) into assets/library/fetched/, which git ignores.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from xenoform import footage  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--vibe")
ap.add_argument("--force", action="store_true")
ap.add_argument("--only-missing", action="store_true", default=True)
a = ap.parse_args()
data = footage.load_manifest()
items = footage.by_vibe(a.vibe, data) if a.vibe else data["items"]
for it in items:
    try:
        p = footage.fetch_item(it, force=a.force)
        print("ok  ", it["id"], p)
    except Exception as exc:  # keep going; one dead link should not stop the rest
        print("FAIL", it["id"], exc)
