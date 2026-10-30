"""The long walkthrough's chapter list for the YouTube description, from a build's segment record and the copy's
chapter names (each chapter at its first segment; the opening montage at 0:00).

    python long_chapters.py <long json> <out txt>
"""
import json
import sys
from pathlib import Path

rec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
copy = {r["id"]: r for r in json.loads(Path(r"C:\Projects\xenoform-rc2\docs\demo\long_voice.json").read_text(encoding="utf-8"))["lines"]}
rows, seen = ["0:00 Montage"], set()
for s in rec["segments"]:
    ch = (copy.get(s["id"]) or {}).get("chapter")
    if ch and ch not in seen and ch != "End":
        seen.add(ch)
        t = int(float(s["start"]))
        rows.append(f"{t // 60}:{t % 60:02d} {ch}")
Path(sys.argv[2]).write_text("\n".join(rows) + "\n", encoding="utf-8")
print("\n".join(rows))
