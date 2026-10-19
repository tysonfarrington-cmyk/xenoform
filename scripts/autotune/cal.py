"""Score the known-good / known-bad calibration clips and print a compact table.
usage (ComfyUI venv): python cal.py cal.json   where cal.json = [{"label","clip","a","b","na","nb"}...]"""
import json, sys
from score import score
rows = json.load(open(sys.argv[1]))
for r in rows:
    o = score(r["clip"], r.get("a"), r.get("b"), r.get("na"), r.get("nb"))
    m, s = o["metrics"], o["sub"]
    print(json.dumps({"label": r["label"], "score": o["score"], **{k: s[k] for k in s},
                      "hf": m["hf_ratio"], "peaks": m["peaks_delta"], "detail": m["detail_ratio"],
                      "lap": m["lap_ratio"], "dc": m["haze_dc"], "luma": m["luma_mid"], "pop": m["pop"]}))
