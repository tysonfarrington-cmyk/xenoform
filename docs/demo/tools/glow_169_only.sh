#!/usr/bin/env bash
# The 16:9 half of glow_rebuild.sh (30 Oct, while the 9:16 cuts render): the demo intro and the long's opening from
# the full-song plan (glow_derive.py), then the demo and the long at 16:9.
#   bash glow_169_only.sh <version>
set -e
V="${1:-v16}"
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
M="$W/montage"
PY=/c/Projects/xenoform-rc2/.venv/Scripts/python.exe
READ_S=C:/Projects/kokoro-tts/reads/short2_af_heart
READ_L=C:/Projects/kokoro-tts/reads/long2_af_heart
cd "$W"
echo "== intros $(date +%H:%M:%S)"
$PY -X utf8 -u montage.py "$M/plan_intro_169.json" "$M/intro_169.mp4" --excerpt 117.17
$PY -X utf8 -u montage.py "$M/plan_long_intro_169.json" "$M/intro_long.mp4"
echo "== short $(date +%H:%M:%S)"
$PY -X utf8 -u glow_plan.py
$PY -X utf8 -u assemble.py plan_short.json $READ_S "$W/short_af_heart_${V}.mp4" > "$W/glow_short_${V}.log" 2>&1
tail -1 "$W/glow_short_${V}.log"
echo "== long $(date +%H:%M:%S)"
$PY -X utf8 make_plan_long.py
$PY -X utf8 -u assemble.py plan_long.json $READ_L "$W/long_af_heart_${V}.mp4" > "$W/glow_long_${V}.log" 2>&1
tail -1 "$W/glow_long_${V}.log"
echo "== done $(date +%H:%M:%S)"
