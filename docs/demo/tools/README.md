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
| `glow_rebuild.sh` | The whole rebuild in order. |
