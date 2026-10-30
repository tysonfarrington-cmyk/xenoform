"""Check a montage plan against the measured cut offsets before building: for every slot, the stretch of its cut it
will play (cut in and out, in the cut's own seconds) and whether the cut covers it.

    python montage_check.py <plan json>
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
M = HERE / "montage"
JOBS = Path(r"C:\Projects\xenoform-rc2\work\ui\jobs")
sys.path.insert(0, str(HERE))
from song_offset import offset  # noqa: E402

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
aspect = plan.get("aspect", "16:9")
rows = {}
for name in (f"renders_{'169' if aspect == '16:9' else '916'}.json", "renders_169.json", "clips_glitch.json"):
    p = M / name
    if p.exists():
        for r in json.loads(p.read_text(encoding="utf-8")):
            if r.get("status") == "done" and r["label"] not in rows:
                rows[r["label"]] = r
            if name == "renders_169.json" and r.get("status") == "done":
                rows.setdefault(r["label"] + "@169", r)  # montage.py: the 16:9 render as a strip in a 9:16 plan
known = json.loads((M / "offsets.json").read_text(encoding="utf-8"))
beats = json.loads(Path(r"C:\Projects\xenoform-rc2\examples\songs\glitch-out.features.json").read_text(encoding="utf-8"))["beats"]
steps = sorted(b - a for a, b in zip(beats, beats[1:]))
period = steps[len(steps) // 2]
prev = float(plan["start"])
bad = 0
for k, row in enumerate(plan["slots"]):
    lab = row[0]
    end = float(row[1]) if k < len(plan["slots"]) - 1 else float(plan["title"]) + float(plan.get("tail", 3.0))
    r = rows.get(lab)
    if not r:
        print(f"{lab:26} NOT RENDERED")
        bad += 1
        prev = end
        continue
    if r["job"] not in known:
        known[r["job"]] = offset(r["job"], float(r["window"]))[0]
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(JOBS / r["job"] / "xenoform.mp4")], capture_output=True, text=True).stdout.strip())
    shift = float(row[3]) if len(row) > 3 and row[3] else 0.0
    off = known[r["job"]] - shift * period
    a, b = prev - off, end - off
    ok = a >= -0.01 and b <= secs + 0.01
    bad += not ok
    print(f"{lab:26} {prev:7.2f}-{end:7.2f}  plays cut {a:5.2f}-{b:5.2f} of {secs:4.1f}  shift {shift:+.0f}  {'ok' if ok else 'OUT OF RANGE'}")
    prev = end
(M / "offsets.json").write_text(json.dumps(known, indent=1), encoding="utf-8")
print("problems:", bad)
