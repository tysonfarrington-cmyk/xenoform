#!/usr/bin/env bash
# Copy the demo toolchain as it stands into the repo (docs/demo/tools/), the way docs/demo/v4/ keeps the v4 tools: a
# record of how the cuts were made. The scripts point at this scratchpad; treat them as reference.
set -e
W="C:/Users/tyson/AppData/Local/Temp/claude/C--Projects/7d414e75-aaf9-49cf-88fc-dcf26694d380/scratchpad/wt"
T=/c/Projects/xenoform-rc2/docs/demo/tools
mkdir -p "$T/cards" "$T/plans"
for f in sync_check.py montage_sync.py gauntlet_round.py cutlib.py assemble.py assemble_v.py montage.py montage_renders.py clips_glitch.py song_offset.py bed.py split_copy.py \
         glow_plan.py make_plan_long.py record_cards.py record_cards_v.py record_underhood.py title_png.py qa_cut.py to_mp4.py \
         shots.py long_shots.py glow_rebuild.sh; do
  cp -f "$W/$f" "$T/$f"
done
cp -f "$W/cards/title.html" "$W/cards/cards.html" "$W/cards/cards_v.html" "$T/cards/"
cp -f "$W/plan_short.json" "$T/plans/plan_short.json"
cp -f "$W/montage/plan_169.json" "$T/plans/montage_169.json"
cp -f "$W/montage/plan_916.json" "$T/plans/montage_916.json"
cp -f "$W/montage/plan_intro_169.json" "$T/plans/intro_169.json"
cp -f "$W/montage/plan_intro_916.json" "$T/plans/intro_916.json"
cp -f "$W/montage/renders_169.json" "$T/plans/renders_169.json"
cp -f "$W/montage/renders_916.json" "$T/plans/renders_916.json"
cp -f "$W/montage/clips_glitch.json" "$T/plans/clips_glitch.json"
cp -f "$W/montage/offsets.json" "$T/plans/offsets.json"
ls -R "$T" | head -60
