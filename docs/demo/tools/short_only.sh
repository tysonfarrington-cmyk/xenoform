#!/usr/bin/env bash
# The demo alone at 16:9 (30 Oct 1:50 pm, Tys: the gold outro as its intro): glow_plan.py then assemble.py.
#   bash short_only.sh <version>
set -e
V="${1:-v17}"
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
PY=/c/Projects/xenoform-rc2/.venv/Scripts/python.exe
READ_S=C:/Projects/kokoro-tts/reads/short2_af_heart
cd "$W"
$PY -X utf8 -u glow_plan.py | tail -2
$PY -X utf8 -u assemble.py plan_short.json $READ_S "$W/short_af_heart_${V}.mp4" > "$W/glow_short_${V}.log" 2>&1
tail -1 "$W/glow_short_${V}.log"
echo "== short done $(date +%H:%M:%S)"
