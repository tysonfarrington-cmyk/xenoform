#!/usr/bin/env bash
# montage916_build.sh (30 Oct pm): the 9:16 full-song montage from plan_169.json once every slot has its 9:16 render
# (Tys: "finish the 9:16 full-song montage when the renders land and send me the 540p copy"): plan, range check,
# build, deflash, then the Desktop copy, the capped 540p review copy and the gold outro as its own 9:16 clip.
set -e
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
PY=/c/Projects/xenoform-rc2/.venv/Scripts/python.exe
D=/c/Users/tyson/Desktop/xeno_walkthrough_29oct
cd "$W"
$PY -X utf8 make_plan_916.py
$PY -X utf8 montage_check.py montage/plan_916.json | tee montage/check_916.txt
grep -q "problems: 0" montage/check_916.txt
[ -f montage/xenoform_montage_9x16.mp4 ] && cp montage/xenoform_montage_9x16.mp4 montage/xenoform_montage_9x16_v15.mp4
$PY -X utf8 -u montage.py montage/plan_916.json montage/xenoform_montage_9x16_raw.mp4
$PY -X utf8 -u deflash.py montage/xenoform_montage_9x16_raw.mp4 montage/xenoform_montage_9x16.mp4
cp montage/xenoform_montage_9x16.mp4 "$D/xenoform_montage_9x16.mp4"
ffmpeg -nostdin -v error -y -i "$D/xenoform_montage_9x16.mp4" -vf scale=540:-2 -c:v libx264 -preset medium -crf 23 \
  -maxrate 1.6M -bufsize 3.2M -c:a aac -b:a 160k -movflags +faststart "$D/review540_montage_9x16.mp4"
# the gold outro on its own (the 16:9 clip is the same cut: 226.08 s to the end)
ffmpeg -nostdin -v error -y -ss 226.08 -i "$D/xenoform_montage_9x16.mp4" -c:v libx264 -crf 16 -preset slow -c:a aac -b:a 256k \
  -movflags +faststart "$D/clips/xenoform_gold_outro_9x16.mp4"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$D/xenoform_montage_9x16.mp4" "$D/clips/xenoform_gold_outro_9x16.mp4"
echo "montage916 done $(date +%H:%M:%S)"
