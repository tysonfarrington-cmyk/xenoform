"""The plans cut from the full-song montage (Tys, 30 Oct 8 am: the montage is its own music video on the whole song):
the long's opening (the two minutes from 1:56 to the title it opened on before, plan_long_intro_169.json) and the
demo's intro (117.17 s to the drop at 141.0, plan_intro_169.json), both opening on the black glass orchid (the full
song opens on its own orchid cut at 0:00) and taking the rest slot for slot from plan_169.json, so a fix there is a
fix in all three. The 9:16 plans the same way from plan_916.json when it exists.

    python glow_derive.py
"""
import json
from pathlib import Path

M = Path(__file__).parent / "montage"
ORCHID = ["black_orchid_open", 119.79, "pin"]  # the demo intro's opener since 30 Oct 3 am (shot 1 of its pinned chain)
# Tys, 30 Oct 12:30 pm: "lets cut the first 1:35 out" of the long; 12:45 pm: "use the gold edit ending from our montage
# video instead ... the last 5-10 seconds": it opens on the gold finale at the release (226.1 s) and runs to the title
LONG_START = 229.375  # 1:10 pm: "can we cut the first 3.5 seconds?": the beat 3.3 s in, three beats before the title


def derive(tag):
    src = M / f"plan_{tag}.json"
    if not src.exists():
        return
    full = json.loads(src.read_text(encoding="utf-8"))
    labels = [s[0] for s in full["slots"]]
    k = labels.index("chrome_beasts_shatter")
    rest = full["slots"][k:]
    long_intro = {**full, "start": LONG_START, "slots": [s for s in full["slots"] if float(s[1]) > LONG_START + 0.01]}
    drop = next(i for i, s in enumerate(rest) if float(s[1]) >= 141.0 - 0.01)
    demo_intro = {"aspect": full["aspect"], "start": 117.17, "title": 141.0, "tail": 0, "slots": [ORCHID] + rest[:drop + 1]}
    # the long's opening and, since 30 Oct 1:50 pm, the demo's: the gold outro from LONG_START, title and all
    (M / f"plan_long_intro_{tag}.json").write_text(json.dumps(long_intro, indent=1), encoding="utf-8")
    (M / f"plan_intro_{tag}.json").write_text(json.dumps(demo_intro, indent=1), encoding="utf-8")
    print(tag, "demo intro:", [s[0] for s in demo_intro["slots"]])


derive("169")
derive("916")
