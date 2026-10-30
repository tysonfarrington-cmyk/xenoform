"""The 9:16 full-song montage's plan from the 16:9 one (30 Oct): the same slots and cut points; a slot whose 9:16 render
was made on that slot's own seconds (montage_renders.py's 9:16 pass, rows with a "length") plays it from its start (no
shift); the older 9:16 renders keep the stretches chosen for them on 29 Oct; a slot listed in STRIP plays its 16:9
render as a strip over its blur ("<label>@169": the 9:16 one came out smeared or on plain objects); the film pack has
no 9:16 cut and plays as a strip anyway.

    python make_plan_916.py
"""
import json
from pathlib import Path

M = Path(__file__).parent / "montage"
OLD_916 = {"deepsea_fish_clear": 0, "shadow_magic_melt": 15, "origami_fold_smooth": 0, "black_flowers_melt": 16,
           "none_pirates_beat": -8, "ocean_bloom_beat": 0}
# the 9:16 render is worse than the 16:9 stretch: cosmic smeared, risograph on a pretzel and seed pods, glass washed out
STRIP = {"cosmic_bloom_beat", "riso_fold_snap", "glass_space_bloom",
         # 30 Oct pm, from the 9:16 sheets: black glass goes near black for 1.5 s, the 9:16 ice brings a helmet and a
         # frog (Tys: helmets are boring), the 9:16 origami is a clutter of gold folds
         "s2_black_symbols", "a07_ice_norse", "n1_origami_icons"}
# 9:16 renders made on the full 30 s window (they went through priority.txt, so montage_renders gave them no slot
# window): their own stretch in whole beats, chosen from the 9:16 sheets
SHIFT_916 = {"chrome_beasts_shatter": 0, "b_neon_tarot": -10, "gold_finale_clear": -23}
STRIP |= set((M / "strip_916.txt").read_text(encoding="utf-8").split()) if (M / "strip_916.txt").exists() else set()

plan = json.loads((M / "plan_169.json").read_text(encoding="utf-8"))
short = {r["label"] for r in json.loads((M / "renders_916.json").read_text(encoding="utf-8"))
         if r.get("status") == "done" and r.get("length")}
slots = []
for row in plan["slots"]:
    lab, end = row[0], row[1]
    pin = row[2] if len(row) > 2 else ""
    shift = row[3] if len(row) > 3 else 0
    if lab in STRIP:
        slots.append([lab + "@169", end, pin, shift])
    elif lab in SHIFT_916:
        slots.append([lab, end, pin, SHIFT_916[lab]])
    elif lab in short:
        slots.append([lab, end, pin])
    elif lab in OLD_916:
        slots.append([lab, end, pin, OLD_916[lab]])
    else:  # no 9:16 render: the 16:9 one as a strip with its own stretch
        slots.append([lab, end, pin, shift])
out = {**plan, "aspect": "9:16", "slots": slots}
(M / "plan_916.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
missing = [s[0] for s in slots if s[0] not in short and s[0] not in OLD_916 and not s[0].endswith("@169") and not s[0].startswith("clips")]
print(len(slots), "slots;", "no 9:16 render yet:", missing)
