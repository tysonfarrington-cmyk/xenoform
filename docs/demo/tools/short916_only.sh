#!/usr/bin/env bash
# The demo at 9:16 (30 Oct 2:30 pm): the gold outro (plan_long_intro_916.json, from the full-song 9:16 plan) as its
# intro, the orchid under the open line, the clean join into the desk (morph_join.py ... clean).
#   bash short916_only.sh <version>
set -e
V="${1:-v18}"
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
M="$W/montage"
PY=/c/Projects/xenoform-rc2/.venv/Scripts/python.exe
READ_S=C:/Projects/kokoro-tts/reads/short2_af_heart
cd "$W"
$PY -X utf8 -u make_plan_916.py
$PY -X utf8 -u glow_derive.py
$PY -X utf8 -u montage.py "$M/plan_long_intro_916.json" "$M/intro_916.mp4"
$PY -X utf8 -u glow_plan.py | tail -1
$PY -X utf8 -u assemble_v.py plan_short.json $READ_S "$W/short_af_heart_${V}_916_raw.mp4" > "$W/glow_short916_${V}.log" 2>&1
tail -1 "$W/glow_short916_${V}.log"
CUT=$($PY -c "import json;d=json.load(open('$W/short_af_heart_${V}_916_raw.json'));print([s['start'] for s in d['segments'] if s['id']=='vibe'][0])")
OPEN=$($PY -c "import json;d=json.load(open('$W/short_af_heart_${V}_916_raw.json'));print([s['dur'] for s in d['segments'] if s['id']=='open'][0])")
$PY -X utf8 morph_join.py "$W/short_af_heart_${V}_916_raw.mp4" "$W/short_af_heart_${V}_916.mp4" "$CUT" \
    C:/Projects/xenoform-rc2/work/ui/jobs/28f7148d/xenoform.mp4 "$OPEN" 0.2 clean
echo "== short 9:16 done $(date +%H:%M:%S)"
