#!/usr/bin/env bash
# The glow-up, end to end (29 Oct pm): the montage (16:9 and 9:16), the demo intros, the short (16:9 and 9:16) and the
# long on Glitch Out, QA, the Desktop files and the review copies.
#   bash glow_rebuild.sh <version, e.g. v12>
set -e
V="${1:-v12}"
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
M="$W/montage"
PY=/c/Projects/xenoform-rc2/.venv/Scripts/python.exe
READ_S=C:/Projects/kokoro-tts/reads/short2_af_heart
READ_L=C:/Projects/kokoro-tts/reads/long2_af_heart
DEST="/c/Users/tyson/Desktop/xeno_walkthrough_29oct"
cd "$W"
echo "== montage $(date +%H:%M:%S)"
$PY -X utf8 -u montage.py "$M/plan_169.json" "$M/xenoform_montage.mp4"
$PY -X utf8 -u montage.py "$M/plan_916.json" "$M/xenoform_montage_9x16.mp4"
echo "== intros $(date +%H:%M:%S)"
$PY -X utf8 -u montage.py "$M/plan_intro_169.json" "$M/intro_169.mp4" --excerpt "$($PY -c "import json;print(json.load(open('$M/plan_intro_169.json'))['start'])")"
$PY -X utf8 -u montage.py "$M/plan_intro_916.json" "$M/intro_916.mp4" --excerpt "$($PY -c "import json;print(json.load(open('$M/plan_intro_916.json'))['start'])")"
# the long opens on the whole montage up to its title (Tys, 30 Oct)
$PY -X utf8 -u montage.py "$M/plan_169.json" "$M/intro_long.mp4" --excerpt "$($PY -c "import json;print(json.load(open('$M/plan_169.json'))['start'])")"
echo "== short $(date +%H:%M:%S)"
$PY -X utf8 -u glow_plan.py
$PY -X utf8 -u assemble.py plan_short.json $READ_S "$W/short_af_heart_${V}.mp4" > "$W/glow_short_${V}.log" 2>&1
tail -1 "$W/glow_short_${V}.log"
$PY -X utf8 -u assemble_v.py plan_short.json $READ_S "$W/short_af_heart_${V}_916.mp4" > "$W/glow_short916_${V}.log" 2>&1
tail -1 "$W/glow_short916_${V}.log"
echo "== long $(date +%H:%M:%S)"
$PY -X utf8 make_plan_long.py
$PY -X utf8 -u assemble.py plan_long.json $READ_L "$W/long_af_heart_${V}.mp4" > "$W/glow_long_${V}.log" 2>&1
tail -1 "$W/glow_long_${V}.log"
echo "== QA $(date +%H:%M:%S)"
for f in "$M/xenoform_montage.mp4" "$M/xenoform_montage_9x16.mp4" "$W/short_af_heart_${V}.mp4" "$W/short_af_heart_${V}_916.mp4"; do
  echo "-- $(basename "$f")"; $PY qa_cut.py "$f" "${f%.mp4}_qa.jpg" 2
done
echo "-- long"; $PY qa_cut.py "$W/long_af_heart_${V}.mp4" "$W/long_af_heart_${V}_qa.jpg" 6
echo "== Desktop $(date +%H:%M:%S)"
cp -f "$M/xenoform_montage.mp4" "$DEST/xenoform_montage.mp4"
cp -f "$M/xenoform_montage_9x16.mp4" "$DEST/xenoform_montage_9x16.mp4"
cp -f "$W/short_af_heart_${V}.mp4" "$DEST/xenoform_demo_video.mp4"
cp -f "$W/short_af_heart_${V}_916.mp4" "$DEST/xenoform_demo_video_9x16.mp4"
cp -f "$W/long_af_heart_${V}.mp4" "$DEST/xenoform_long_walkthrough.mp4"
R() { ffmpeg -v error -y -i "$1" -vf "scale=$3" -c:v libx264 -crf 23 -preset veryfast -c:a aac -b:a 128k -movflags +faststart "$2"; }
R "$DEST/xenoform_montage.mp4" "$DEST/review720_montage.mp4" 1280:720
R "$DEST/xenoform_montage_9x16.mp4" "$DEST/review540_montage_9x16.mp4" 540:960
R "$DEST/xenoform_demo_video.mp4" "$DEST/review720_demo.mp4" 1280:720
R "$DEST/xenoform_demo_video_9x16.mp4" "$DEST/review540_demo_9x16.mp4" 540:960
R "$DEST/xenoform_long_walkthrough.mp4" "$DEST/review540_long.mp4" 960:540
ls -la "$DEST" | grep -E "montage|demo_video|long_walk|review"
echo "== done $(date +%H:%M:%S)"
