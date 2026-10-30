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
# the demo intro and the long's opening are cut from the full-song plan (30 Oct: the montage is the whole song)
$PY -X utf8 -u make_plan_916.py
$PY -X utf8 -u glow_derive.py
$PY -X utf8 -u montage.py "$M/plan_169.json" "$M/xenoform_montage.mp4"
$PY -X utf8 -u montage.py "$M/plan_916.json" "$M/xenoform_montage_9x16.mp4"
echo "== intros $(date +%H:%M:%S)"
$PY -X utf8 -u montage.py "$M/plan_intro_169.json" "$M/intro_169.mp4" --excerpt "$($PY -c "import json;print(json.load(open('$M/plan_intro_169.json'))['start'])")"
$PY -X utf8 -u montage.py "$M/plan_intro_916.json" "$M/intro_916.mp4" --excerpt "$($PY -c "import json;print(json.load(open('$M/plan_intro_916.json'))['start'])")"
# the long opens on the 2-min montage it had (1:56 to the title, plan_long_intro_169.json); the full-song montage is its own video (Tys, 30 Oct 8 am)
$PY -X utf8 -u montage.py "$M/plan_long_intro_169.json" "$M/intro_long.mp4"  # the full gold outro, title and all (Tys, 30 Oct 1 pm)
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
# the montage runs the whole song (3:58): a capped bitrate keeps its 540p copies under 30 MB for Tys's phone
RC() { ffmpeg -v error -y -i "$1" -vf "scale=$3" -c:v libx264 -preset slow -b:v 850k -maxrate 1100k -bufsize 2200k -c:a aac -b:a 96k -movflags +faststart "$2"; }
RC "$DEST/xenoform_montage_9x16.mp4" "$DEST/review540_montage_9x16.mp4" 540:960
RC "$DEST/xenoform_montage.mp4" "$DEST/review540_montage.mp4" 960:540
R "$DEST/xenoform_demo_video.mp4" "$DEST/review720_demo.mp4" 1280:720
R "$DEST/xenoform_demo_video_9x16.mp4" "$DEST/review540_demo_9x16.mp4" 540:960
R "$DEST/xenoform_long_walkthrough.mp4" "$DEST/review540_long.mp4" 960:540
ls -la "$DEST" | grep -E "montage|demo_video|long_walk|review"
echo "== done $(date +%H:%M:%S)"
