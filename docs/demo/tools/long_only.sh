#!/usr/bin/env bash
# The long alone (30 Oct 12:30 pm, Tys: cut the first 1:35 of xenoform_long_walkthrough): its opening from the drop at
# 210.4 s to the title, then the walkthrough.
#   bash long_only.sh <version>
set -e
V="${1:-v16b}"
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
M="$W/montage"
PY=/c/Projects/xenoform-rc2/.venv/Scripts/python.exe
READ_L=C:/Projects/kokoro-tts/reads/long2_af_heart
cd "$W"
$PY -X utf8 -u - <<'EOF'
import runpy
from pathlib import Path
src = Path('glow_derive.py').read_text(encoding='utf-8').replace('derive("916")', '')
exec(compile(src, 'glow_derive.py', 'exec'), {'__file__': str(Path('glow_derive.py').resolve()), '__name__': '__main__'})
EOF
$PY -X utf8 -u montage.py "$M/plan_long_intro_169.json" "$M/intro_long.mp4"
$PY -X utf8 make_plan_long.py
$PY -X utf8 -u assemble.py plan_long.json $READ_L "$W/long_af_heart_${V}.mp4" > "$W/glow_long_${V}.log" 2>&1
tail -1 "$W/glow_long_${V}.log"
echo "== long done $(date +%H:%M:%S)"
