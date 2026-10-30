"""Re-cut the montage's kept cuts on the desk that made them (no GPU, the same morphs and timing) with Chaos at 0.45 or
under and no slices foreshadow (Tys, 30 Oct 12:15 pm: "too much shaking ... filmed with a handycam", "overusing that
transition with the bars"); the build into the 119.8 s drop and the drop itself also get the cyan-flash look and dither
hits ("the build up around 1:50ish ... doesn't feel very audio reactive", "the drop around 1:59 ... needs to be the
coolest and most active part"). Each cut's first picture is kept as xenoform_v16.mp4 beside it.

    python recut_calm.py [label ...]   (default: every kept label, both aspects)
"""
import json
import shutil
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).parent
M = HERE / "montage"
JOBS = Path(r"C:\Projects\xenoform-rc2\work\ui\jobs")
DESK = "http://127.0.0.1:47325"
src = (HERE / "montage_renders.py").read_text(encoding="utf-8")
ns = {"__file__": str(HERE / "montage_renders.py")}
exec(compile(src[: src.index("\n\ndef make(")], "montage_renders.py", "exec"), ns)  # CUTS and the macros it uses
CUTS = {c["label"]: c for c in ns["CUTS"]}
KEEP = ["a06_chrome_relics", "a10_brutalist_wonders", "a12_botanical_myth", "a13_cosmic_clear", "a14_neon_beasts",
        "a15_ferro_symbols", "a16_kintsugi_masks", "a17_ocean_clear", "chrome_beasts_shatter", "deepsea_fish_clear",
        "shadow_magic_melt", "origami_fold_smooth", "b_neon_tarot", "botanical_clear_bloom", "cosmic_bloom_beat",
        "riso_fold_snap", "b_kintsugi_symbols", "b_y2k_symbols", "b_cyber_beasts", "b_shadow_mythic", "b_marble_icons",
        "glass_space_bloom", "ocean_bloom_beat"]
LOUD = {"a17_ocean_clear", "chrome_beasts_shatter"}  # the build into the 119.8 s drop and the drop


def body(cut, label):
    macros = {**cut["macros"], "chaos": min(float(cut["macros"].get("chaos", 0.3)), 0.45)}
    b = {"macros": macros, "foreshadow": "trace" if cut.get("foreshadow") == "slices" else cut.get("foreshadow", "auto")}
    if label in LOUD:
        b.update({"dance_fx": "cyan-flash", "effects": sorted(set(cut.get("effects") or []) | {"dither"}),
                  "macros": {**macros, "intensity": 1.0, "chaos": 0.5}})
    return b


def recut(job, b):
    mp4 = JOBS / job / "xenoform.mp4"
    keep = JOBS / job / "xenoform_v16.mp4"
    if not keep.exists():
        shutil.copy2(mp4, keep)
    r = requests.post(f"{DESK}/api/jobs/{job}/recut", json=b, timeout=120)
    if r.status_code != 200:
        return f"refused {r.status_code}: {r.text[:200]}"
    t0 = time.perf_counter()
    while True:
        time.sleep(5)
        try:
            j = requests.get(f"{DESK}/api/jobs/{job}", timeout=60).json()
        except Exception:
            continue
        if j.get("status") == "done":
            return f"{j.get('detail')} in {time.perf_counter() - t0:.0f} s"


labels = sys.argv[1:] or KEEP
rows = []
for name in ("renders_169.json", "renders_916.json"):
    for r in json.loads((M / name).read_text(encoding="utf-8")):
        if r.get("status") == "done" and r["label"] in labels:
            rows.append(r)
done = set()
log = M / "recut_calm.json"
prev = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
done = {(p["job"], p["body"].get("dance_fx", ""), p["body"]["macros"]["chaos"]) for p in prev if "Re-cut ready" in p.get("result", "")}
for r in rows:
    cut = CUTS.get(r["label"])
    if not cut:
        continue
    b = body(cut, r["label"])
    if (r["job"], b.get("dance_fx", ""), b["macros"]["chaos"]) in done:
        continue
    res = recut(r["job"], b)
    print(f"{r['label']:26} {r['aspect']:5} {r['job']}  {res}", flush=True)
    prev.append({"label": r["label"], "aspect": r["aspect"], "job": r["job"], "body": b, "result": res})
    log.write_text(json.dumps(prev, indent=1), encoding="utf-8")
print("recut_calm done", flush=True)
