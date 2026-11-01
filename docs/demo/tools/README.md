# The demo toolchain (29 Oct, the glow-up)

How the contest video, its 9:16 cut, the long walkthrough and the montage were made, kept beside the voice copies the
way `docs/demo/v4/` keeps the v4 tools. They ran from a session scratchpad (`...\scratchpad\wt\`), so their paths point
there: a record and a reference, not a package. The voice is Kokoro in `C:\Projects\kokoro-tts` (`read.py`,
`check.py`, `try_line.py`, `reread_line.py`, `join.py`); the screen is a headless Edge on `--remote-debugging-port=9341`
driven over the DevTools protocol (`shots.py`, `long_shots.py`, `to_mp4.py`, the cards).

| File | What it does |
| --- | --- |
| `cutlib.py` | What both assemblers share: segments sized to the read with a breath before, between and after the sentences, each segment's end snapped to a beat of the bed (`grid`), the bed ducked under the voice and levelled to -16 LUFS, the intro joined in front with its ring-out, `land` (an output ends on its own shot boundary), `join_exact` (segments to their exact frame counts). |
| `assemble.py`, `assemble_v.py` | The 16:9 and 9:16 cuts from a plan (`plans/plan_short.json`, `make_plan_long.py`): screen recordings still and full frame (no push-in), outputs full frame, grids, cards, captions burned in. |
| `split_copy.py` | A voice copy split into one row a sentence, so Kokoro (which runs a line's sentences together) pauses between them. |
| `montage_renders.py` | The montage's Cloud Final cuts, made through a desk like any Make, each on a 30 s window of Glitch Out (`plans/renders_*.json`: job, window, look). |
| `clips_glitch.py` | The film-pack clips cuts on Glitch Out (local Final), from a folder of chosen pack clips in play order. |
| `song_offset.py` | Where a cut's trimmed audio sits in the song (the desk snaps a window back to a beat and keeps no record). |
| `montage.py` | The montage by song time (`plans/montage_*.json`, `intro_*.json`): every cut on a beat of the song's own grid, moved to where the outgoing morph has finished, checked against each cut's window; the title over the last shot; the song as the sound. |
| `glow_plan.py` | Puts the renders and the intro into the short's plan, each output at the song time it plays over. |
| `bed.py` | A long bed from one song, played through and restarted, with a beat list that keeps the bar phase. |
| `record_cards*.py`, `record_underhood.py`, `cards/` | The How it's built, end and Under the hood cards, cued to the sentences; `title.html` + `title_png.py` the montage's title. |
| `qa_cut.py` | Length, black and frozen stretches, loudness and true peak, a contact sheet. |
| `pacing_proof.py` | The pacing proof of 31 Oct (docs/MUSIC_VIDEO_PLAN.md section 3): `table`, Glitch Out cut whole three ways on the mock engine (today, a plain Make, Breathe) against the profile table, looks a minute, morphs per 8 bars, timing, style and effect mix, handoff kinds and the flash frames per 8 bars on the composed cut; `sheets`, local Draft Makes through a desk of 30 s windows, a timed tile sheet each and the cuts side by side; `stacked` (round two), plain above Breathe at full width with the song and a cut-rhythm strip under each panel, the looks a minute of every passage. |
| `song_proof.py` | The whole-song proof of 1 Nov (docs/SONG.md): `make`, from a song made through a desk's Whole song button and laid together there, the mp4 with the song, a copy under 25 MiB, a tile sheet (a tile at each passage start and each drop event, and one at the title, labelled with the time, the passage, its vibe and its objects) and the passage table with the song's totals as JSON; `readme`, the folder's README.md from them. What `montage.py` did by hand is now `song_assemble.py` in the app. |
| `cloud_scene_pairs.py` | The backdrops set of the judged Cloud sets (docs/MUSIC_VIDEO_PLAN.md section 8, items 3 and 17): an old Cloud Final cut's scene pairs sent again through the desk's own Cloud Final path (`cloud_final.cloud_clips`, the morph cache first) with the cut's recorded stills, seeds and lengths and the scene handling as it is now, each graph checked against the one the old clip recorded in its mp4. It spends Comfy Cloud credits only behind its tick, `--spend`: without it nothing is sent (a dry run); with it a pair gets at most two sends, and a pair failing both stops the run. The key stays in the environment. |
| `cloud_scene_pairs_sheet.py` | The proof of a `cloud_scene_pairs.py` run: each pair's old clip above its new one at 0, 25, 50, 75 and 100 percent, labelled with full paths, the new clips copied beside the sheet. CPU only: it sends nothing and spends no credits. |
| `cloud_song_deliver.py` | A whole song made through a desk's Whole song button, delivered: the mp4, a copy under 25 MiB, a tile at each passage start and drop event (time, passage, vibe, the objects morphing), the passage table, and each window's morphs on Comfy Cloud, from the cache and fallen back to Draft (`sent.json`, read from the Cloud morph cache's sidecars). CPU only: it sends nothing and spends no credits; a Cloud song's spending is the desk's, behind its credits tick. |
| `glow_rebuild.sh` | The whole rebuild in order. |
