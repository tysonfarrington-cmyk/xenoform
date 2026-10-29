# Handoff: the demo glow-up and the montage intro (Thu 29 Oct 2026, 3:30 pm AEDT)

For the Opus 5.5 session that takes the contest video from "fine" to "slick". Deadline: Tys's own cut-off is Fri 30
Oct 9 pm AEDT (the Typeform closes Sat 31 Oct 3 am). He pushes, uploads, posts and submits himself; nothing is
pushed or posted by an agent. Spending Comfy Cloud credits on renders is allowed (Tys, 29 Oct: "You may as well use
our credits as well", "use the best quality we can"); never print or paste the key.

## What Tys said (29 Oct, 3 pm, verbatim where it matters)

"theres a bit of a shake and zoom on the app parts which we shouldnt do. - also need some pauses and let scenes
breathe a little more, the script doesnt seem to stop for pauses so make sure voice sounds natural. i also think the
intro should probably a montage of a technical demonstration. in the demo you dont actually get to see the output for
very long in parts which is a missed opportunity to show it off. ... start pumping out of a bunch of different themes
and styles. i think we can use glitch out. maybe a 1 min montage intro of different styles and themes, make it look
slick, show off all the effects and capabilities, push it to the limit max it out, and use the best quality we can.
... fix the issues i listed and make the montage to add on as an intro for the demo and be its own stand alone thing.
the pacing of the actual app demo also needs a bit of work it feels disjointed, it should pretty much be on beat,
audio reactive but let scenes finish properly as well. we have a lot of cool footage to use from the clips and i feel
like you chose some kind of boring ones. i also dont love the skull turning into a crown of thorns, the one on the far
right. i think we can make a much cooler looking example in the part, the whole demo needs a glow up."

## Deliverables

1. **The montage** (about 60 s, on Glitch Out, `examples/songs/glitch_out.mp3`, 90 BPM, 3:59; its analysis is
   `examples/songs/glitch-out.features.json`: beats, sections, per-frame bands): a technical demonstration that shows
   off everything, cut on the beat, every shot a Cloud Final render (LTX-2.5 on Comfy Cloud, the best quality we
   have), different vibes and themes and all five morph styles, the three timings, every effect, Foreshadow, Scenes,
   the knobs pushed to the limit, and a stretch of the free film pack's clips morphing into each other. Standalone
   16:9 `xenoform_montage.mp4` and 9:16 `xenoform_montage_9x16.mp4` (one title card "Xenoform" at the end, nothing
   else; no voice), and the same montage (or its best 30 to 40 s) as the demo's new intro.
2. **The demo, fixed and re-paced** (`xenoform_demo_video.mp4`, under 2:00 with the intro; the 9:16 cut; the long one
   can follow the same fixes but is second): no zoom or shake on the screen recordings; pauses between sentences and
   a breath between scenes; the outputs on screen for long enough to be seen; the whole thing cut to the beat of its
   bed, every scene finishing before the next; the opening three-panel replaced (the far-right panel is the neon
   noir cut e649e412 whose skull turns into a crown of thorns: drop it); the clips segment made from the most
   striking windows of the pack; the best example cuts in the parts that show output.
3. Files in `Desktop\xeno_walkthrough_29oct` with 720p/540p review copies sent to Tys, `docs/demo/walkthrough.md`'s
   Made section updated (one bullet in its voice), docs/HANDOFF_29OCT.md's "What is left" touched, and Owly commits
   of the docs and the plan/tool changes (see the rules).

## Rules (Tys's, verbatim where it matters)

- Commit with `git -c user.name=Owly -c user.email=owly@local commit -F <file>` and end the message with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push. Stage only your own files by path, never
  `git add -A`; shared checkout: never stash, reset or switch branches. Another session ("Polish pass and stress
  tests on the Xenoform desk", Opus 5.5) is editing the app's code and docs in this checkout at the same time and
  commits its own work: do not edit `src/` or the top-level docs; your files are `docs/demo/*`, the demo toolchain
  (below) and `configs/film_pack.json` only if you add windows (tell the other session with SendMessage first).
- Never restart ComfyUI (8188), the proxy (8189) or Tys's desks 47320 and 47321. Desk **47326** is the recorder's and
  yours to restart (`Start-Process` of `C:\Projects\xenoform-rc2\.venv\Scripts\python.exe -m xenoform ui --host
  127.0.0.1 --port 47326` from the repo after killing the listener on that port); **47325** is free for Makes; 47324 is
  the polish session's and Tys's test desk, leave it. Check `GET http://127.0.0.1:8188/queue` is idle before any local
  GPU work; Cloud Final renders do not use the local GPU.
- Git Bash heredocs on this machine mangle apostrophes and backslashes: write scripts with the Write tool, run by path.
- Keep clips and objects separate: a Make is Objects or Your clips, never both.
- Plain words everywhere; no em dashes.

## The demo toolchain (all on disk, readable and writable; it lives in the previous session's scratchpad)

`C:\Users\tyson\AppData\Local\Temp\claude\C--Projects\7d414e75-aaf9-49cf-88fc-dcf26694d380\scratchpad\wt\` (call it `wt`)
and `...\scratchpad\rec\cdp.py` (the DevTools client). `docs/demo/walkthrough.md` ("How it gets made") and the memory
note `xenoform-walkthrough-videos.md` in `C:\Users\tyson\.claude\projects\C--Projects\memory\` describe the traps.

- **Voice**: Kokoro-82M in `C:\Projects\kokoro-tts` (`.venv/Scripts/python.exe`): `read.py <copy json> <out dir>
  <voice> [speed]` reads one wav a line (Xenoform is read ZEE-no-form); `check.py` measures (clipping, gaps, rising
  ends); `reread_line.py <copy> <read dir> <voice> <id>` re-reads one line in place; `join.py` lays the lines at
  the starts the assembler gives it. Voice **af_heart** (Tys's pick). The copies are `docs/demo/short_voice.json`
  and `long_voice.json` (`{"lines": [{"id", "text", "say"?}]}`); the reads are `kokoro-tts/reads/short_af_heart`,
  `long_af_heart` (also short_am_michael, short_bm_george). **Pauses**: Kokoro runs a line's sentences together; the
  only gaps today are the plan's `lead` (0.25 s), `gap` (0.45 s between lines of one segment) and `tail` (0.55 s).
  Make the voice breathe by splitting lines at sentence ends into separate ids read separately (one wav a sentence)
  with gaps of 0.6 to 0.9 s, and by giving each segment a lead of about 0.5 s and a tail of about 0.8 s; a line that
  ends up rising at the end gets a reword (`try_line.py`).
- **Screen recording**: headless Edge, `--remote-debugging-port=9341`, profile `scratchpad\edge-rec` (launch line in
  the memory note); `wt/shots.py <shot...>` records the short's desk shots from desk 47326 into `wt/rec/<shot>/`
  (frames + marks; `wt/to_mp4.py <shot...>` makes `rec/<shot>.mp4` + `.json` with the marks), `wt/long_shots.py`
  the long's, `wt/record_cards.py` / `record_cards_v.py` the two HTML cards (`wt/cards/cards.html`, `cards_v.html`),
  `wt/record_underhood.py` the Under the hood panels. The recording's Make on camera was Cloud Final (566cc4c8).
- **Assembly**: `wt/assemble.py <plan json> <read dir> <out mp4>` (16:9) and `wt/assemble_v.py` (9:16) build one
  segment a line from the plan: `pic` kinds `screen` (a recording's pieces by marks, optional `zoom`), `three`, `one`
  (a 9:16 cut on a blur), `wide` (a 16:9 cut full frame, optional `fade` out), `grid`, `card`, `chain` (parts), `still`.
  Segment length = max(`min`, lead + spoken + tail). Captions burned from the copy (chunks end 0.02 s before the next:
  libass stacks overlapping captions). The bed (`plan.music`, today `XF_HipHop_BoomBap_01.mp3` at -9 dB) is looped,
  ducked under the voice (sidechain) and the mix levelled to -16 LUFS. Plans: `wt/plan_short.json` (edit in place) and
  `wt/make_plan_long.py` -> `plan_long.json`. **The shake and zoom**: `zoom_filter` scales per frame with
  `trunc(W*z/2)*2`, which jitters by a pixel as z eases, and the push-ins themselves are what Tys does not want:
  remove every `zoom` from the screen segments (static recordings scaled to the frame) and delete or disable
  `zoom_filter`.
- **Pacing on the beat**: the bed's beat grid is in its analysis (`examples/songs/hip-hop-boom-bap.features.json`,
  or `glitch-out.features.json` if the demo's bed becomes Glitch Out: `beats` in seconds, `sections`). Snap every
  segment's end to the next bar (or two) of the bed so cuts land on the beat, and let a `wide`/`one` output run to
  its own shot boundary before the cut (the cut's `simple/simple.json` has the shots' starts). Make the picture react:
  the assembler can dip the bed and add a one-frame flash or a hard cut on the drops it lands on, but keep it
  tasteful; the renders are audio-reactive already.
- **Rebuilds and QA**: `wt/all_voices.sh <voices>` (cards re-cued, short per voice; versions short_<v>_v10), `wt/
  rebuild_all.sh` (all three shorts + the long v11, Desktop copies, 720p reviews), `wt/final_rebuild.sh` (both plus
  the 9:16 v11_916, review copies, `qa_cut.py` black/frozen/loudness + contact sheets). Bump the version numbers.
  Desktop: `xeno_walkthrough_29oct\xenoform_demo_video.mp4`, `xenoform_demo_video_9x16.mp4`,
  `xenoform_long_walkthrough.mp4`, `review720_*`, `review540_*`.
- **Makes through the desk API** (`wt/showcase.py`, `wt/examples.py`, `wt/make_clips_cut.py` are working examples):
  upload the song with `POST /api/analyze` (multipart) or load a bundled one with `POST /api/songs/load {"id"}`
  (ids: glitch-out, hip-hop-boom-bap, liquid-dnb, ambient, morphing-wobble, morphing-wobble-20s), then `POST
  /api/generate` with the body showcase.py sends: it MUST carry `quality: "turbo"`, `live: true`, `mode: "simple"`
  (without them the job is the old chunk render); `quality_tier: "cloud"` + `cloud_final_ok: true` for Cloud Final
  (at most 16 morphs a cut, about 3.6 credits a morph, 58 s a morph wall, three at a time; a 30 s dense cut was 9 to
  16 morphs and 4 to 6 minutes), `aspect` "16:9" or "9:16", `length_s` (a window around the drop) or `start_s`,
  `energy_preset` "dense"/"flow", `vibe`, `idea` (a theme line; feel words set the knobs: "moody and punchy"),
  `morph_style` melt/shatter/bloom/spin/fold/auto, `morph_timing` smooth/beat/snap, `effects` (a list: dither_hits,
  feedback, kaleido, slitscan, smear; check `app.js` `effectsRow` for the ids), `dance_fx` (the look), `foreshadow`,
  `scenes`, `macros` {intensity, speed, chaos, glow} 0..1 (the desk sends them as `window.XENO_MACROS()`; the Make
  body is built around app.js line 214, `makeBody`; the effect ids are `dither`, `feedback`, `kaleido`, `slitscan`,
  `smear`), and
  for clips `morph_source: "clips"`, `own_folder: "C:/Projects/xenoform-rc2/work/ui/film_pack"` (Cloud Final has no
  clips path: use `quality_tier: "final"` for the local LTX-2.5 Final, 5 to 7 min a morph, or "fast"). Poll `GET
  /api/jobs/<id>`; the file is `work/ui/jobs/<id>/xenoform.mp4`, the shots `simple/simple.json`, 24 fps. A cut's
  own picture is already audio-reactive (beat FX, effects riding the kick). Credits: about 11,300 on the dashboard
  at 10:30 am; the afternoon's renders were local.
- **What exists to reuse**: the three showcase Cloud Final cuts (0c3864af None "underwater" on the hip hop beat,
  e649e412 neon noir on liquid DnB (the skull -> crown of thorns, drop it), 7cdc5b35 liquid gold on ambient), ten
  example cuts, one per other vibe, in `Desktop\xeno_examples_29oct` (jobs in `examples.json`; Cloud Final, 9:16),
  the clips cut 1d376198 (Fast Final 16:9 on the pack), the Make on camera 566cc4c8 (None underwater, Cloud Final),
  b251df0c (its Fast Final). All 9:16 except the clips cut: a 16:9 montage wants new 16:9 renders; the 9:16 montage
  can reuse these.
- **The free film pack** (`configs/film_pack.json`, 24 windows, built to `work/ui/film_pack`, `CREDITS.md` and
  `labels.json` beside the clips; the full source films are in `...\scratchpad\pack\src\` with contact sheets in
  `pack\sheets\`): the most striking windows are Metropolis's Moloch and the robot's rings and face, the Moon's
  face, the Phantom's unmasking, the atomic cloud, Design for Dreaming's dance (colour), Häxan's sabbath, the
  Potemkin steps, The General's bridge, The Lost World's dinosaurs, Apollo 11's launch, Steamboat Willie, Un Chien
  Andalou's pianos. A clips cut plays the folder's clips in name order: to choose and order them, make a folder of
  copies (or symlinks) of the ones you want and point `own_folder` at it (labels come from the file names after the
  first underscore unless a `labels.json` sits beside them). To add windows, extend the manifest and run `Download
  again` (`film_pack.start()`); `own_media.MAX_CLIPS` is 24 (the polish session owns that code).

## A plan (adjust as you go; keep Tys's priorities: slick, on beat, show the output, let it breathe)

1. **Fix the assembler first** (an hour): no zoom; sentence-level pauses (split the copies, re-read what changes in
   af_heart; the other two voices can wait); lead/tail; segment ends snapped to the bed's bars; the output segments
   (`wide`/`one`) long enough to see a few handoffs and cut on a shot boundary; the opening three-panel gone. Rebuild
   the short once and look at it (contact sheet + `qa_cut.py`) before anything renders.
2. **Render the montage's shots on Cloud Final, 16:9, on Glitch Out** (a couple of hours of wall time, mostly waiting;
   run three at a time): pick the song's best 60 s (its drop and the section after), then one 12 to 16 s cut per vibe
   for six to eight vibes (neon noir, liquid gold, chrome, cyberspace 95, bioluminescent "underwater", shadow self, wet
   paint, None with a strong theme), each maxed: Intensity 1, Chaos 0.8 to 1, Glow high, a different morph style and
   timing each (Snap on the drop), every effect across the set, Foreshadow and Scenes where they read; plus one clips
   cut on the pack's best windows at Final (local) and one Fast Final as a fallback. Make the same set 9:16 if time
   allows, else lay the 16:9 renders into the 9:16 frame as strips over blur.
3. **Cut the montage** (the assembler or a new `wt/montage.py`): every cut on a beat or a bar of Glitch Out, each shot
   finishing its handoff, the drops landing on the strongest renders, the clips stretch in the middle or at the end,
   one "Xenoform" card to close (and the hashtag line is for the post, not the film); loudness -16 LUFS, true peak
   under -2; no black frames beyond a deliberate fade. Standalone files first, then as the demo's intro (the demo's
   first line follows it; drop or shorten "open" and the three-panel).
4. **Re-pace the demo on its bed** (consider Glitch Out as the bed too, so the intro and the demo share one pulse),
   show outputs longer (the result shot, the styles grid, the effects grid, the clips cut), replace the clips segment's
   footage with the striking windows, re-record any shot whose screen changed (the desk code is frozen but the polish
   session may touch the UI: record late), rebuild all cuts, QA, Desktop copies, review copies to Tys, docs, commit.
5. Report back: what rendered (jobs, credits spent from the dashboard if you can read it), the files, what you could
   not do.
