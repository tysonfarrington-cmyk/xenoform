# Handoff: the demo glow-up, part 2 (Fri 30 Oct 2026, 7:30 am AEDT)

For the session that keeps working on the contest video, its 9:16 cut, the long walkthrough and the montage. Tys's
cut-off is **today, Fri 30 Oct, 9 pm AEDT** (the Typeform closes Sat 31 Oct 3 am). He pushes, uploads, posts and submits
himself; nothing is pushed or posted by an agent. Spending Comfy Cloud credits on renders is allowed (Tys: "use the best
quality we can"); never print or paste the key. Tys, 7:30 am: "it could use a bit more work".

Read first: this page, `docs/demo/HANDOFF_GLOWUP.md` (the brief this work started from: Tys's words, the deliverables,
the rules), `docs/demo/walkthrough.md` (Made: "The glow-up and the montage"), `docs/demo/tools/README.md`, and the
memory notes `xenoform-montage-taste.md` and `xenoform-walkthrough-videos.md` in
`C:\Users\tyson\.claude\projects\C--Projects\memory\`.

## Where things are (v15, built 30 Oct 2:55 am, all measured)

`C:\Users\tyson\Desktop\xeno_walkthrough_29oct\`:

| File | What | Length |
| --- | --- | --- |
| `xenoform_demo_video.mp4` | the contest demo: the montage's first 24 s, then the walkthrough re-paced | 1:59.0 (limit 2:00) |
| `xenoform_demo_video_9x16.mp4` | the same for the post, 9:16 | 1:59.0 |
| `xenoform_montage.mp4`, `xenoform_montage_9x16.mp4` | the montage on Tys's Glitch Out, 24 looks, none twice | 2:02.4 |
| `xenoform_long_walkthrough.mp4` | the long, opening on the whole montage (Tys chose it) | 9:44 |
| `xenoform_long_walkthrough_chapters.txt` | its chapters | |
| `review720_*`, `review540_*` | review copies (a file over 30 MB does not reach Tys's phone through SendUserFile: use 540p) | |

All -16 LUFS, true peak -2.9 to -5.8 dBFS, the voice measured in sync. The older files in that folder from the morning
(`xenoform_walkthrough_short_*`, `*_am_michael`, `*_bm_george`, `review720_short_*`, `review720_long_af_heart.mp4`) are
earlier versions; the am_michael and bm_george voices were not rebuilt.

## The toolchain

It runs from `C:\Users\tyson\AppData\Local\Temp\claude\C--Projects\7d414e75-aaf9-49cf-88fc-dcf26694d380\scratchpad\wt\`
(`wt`), copied into `docs/demo/tools/` at each commit (`wt/glow_to_repo.sh`). Python: `C:\Projects\xenoform-rc2\.venv\
Scripts\python.exe`; Kokoro (the voice, af_heart) in `C:\Projects\kokoro-tts`.

- **Rebuild everything**: `bash wt/glow_rebuild.sh v16` (about 20 min): both montages, the demo intros, the long's
  intro (the whole montage up to its title), the plan filled with the renders (`glow_plan.py`), the demo 16:9 and 9:16,
  the long, QA (`qa_cut.py`), the Desktop copies and the review copies. Bump the version each time.
- **The montage**: `wt/montage.py <plan> <out> [--excerpt <song s>]`; plans in `wt/montage/`: `plan_169.json` /
  `plan_916.json` (the montage), `plan_intro_169.json` / `plan_intro_916.json` (the demo's intro, 117.17 s to the
  title on the hit at 141.0). A slot is `[label, end song s, "pin" or "", shift in whole beats]`: "pin" keeps the cut
  exactly on that beat, the shift takes another stretch of the same render (whole beats keep its beat FX on the beat).
  Every slot is checked against its render's real window.
- **Renders** (Cloud Final, LTX-2.5 on Comfy Cloud, about 6 min and 50-60 credits each, one at a time): add a config to
  `CUTS` in `wt/montage_renders.py` and run `python montage_renders.py 16:9 <label> ...` (then `9:16`). It uses desk
  **47325**, the only desk with the Cloud key in its environment. `montage/skip.txt` and `montage/priority.txt` are read
  before each cut: **empty priority.txt before starting a run** (a stale entry made a run render the wrong cut).
  `pins` in a config pin chain slots to library stills (`black/029_orchid.jpg`); the opener's two bars are shot 1.
  Logs: `montage/renders_169.json`, `renders_916.json` (job, window, look), offsets measured into `offsets.json`.
- **Re-cut a finished cut with a new look and effects, no GPU**: `POST http://127.0.0.1:<desk>/api/jobs/<id>/recut` with
  `{"dance_fx", "effects", "macros"}` on the desk that made it (the film-pack cut ed2796a2 was re-cut on 47326 with
  bloom-rush, feedback and slit-scan; its original is `xenoform_before_colour.mp4` in its job folder).
- **The demo's plan**: `wt/plan_short.json` (scenes, leads and breaths, `land` with `period` so outputs end on a shot
  boundary by whole beats, `shift_beats` on the clips part, the card's `under` morph); voice copy
  `docs/demo/short_voice.json` (one sentence a row; `say` is what the voice reads), read in
  `kokoro-tts/reads/short2_af_heart` (`reread_line.py` re-reads one line). The long: `wt/make_plan_long.py`,
  `docs/demo/long_voice.json`, read `long2_af_heart`.

## The review gauntlet with Owly (unfinished)

Owly is Tys's Grok Bot assistant; it cannot message a session, it reads and writes files (`OneDrive\Desktop\
FOR_CLAUDE_from_Owly.md` is its note file). Each round: `python wt/gauntlet_round.py <n> <version>` makes
`OneDrive\Desktop\xenoform_review_gauntlet\round<n>\` (the review copies, contact sheets with the time on every frame,
shot lists, and `REVIEW_REQUEST.md`, which starts with `wt/montage/response_round<n-1>.md`: what was done with the
last notes and what was not and why); Tys tells Owly; Owly writes `OWLY_NOTES.md` there (`video | m:ss | what is wrong |
what to do instead`). Tys's instruction: "do its recommendations from the review", except where they cut across his
own choices (say so in the next response).

- **Round 1** (notes in `round1/OWLY_NOTES.md`) found the real fault: the demo's and the long's voice 5.9 s early and
  their last 2.5 s cut (loudnorm's dynamic fallback). Fixed (cutlib levels with a gain and a delay-compensated
  limiter) and measured in sync. Its other notes were taken (see `wt/montage/response_round1.md`).
- **Round 2 is posted** (`round2/`, the v15 cuts) and **not yet answered**. Watch for `round2/OWLY_NOTES.md`
  (`until [ -s .../round2/OWLY_NOTES.md ]; do sleep 15; done` in the background), apply what holds up, rebuild, write
  `response_round2.md`, post round 3.

## Known weak spots (mine; Owly will likely find more)

- Montage: the ocean cut holds on a crown for about 6 s (1:43 to 1:49); a pair of binoculars still shows for a beat at
  1:33; the gold finale behind the title is hazy and abstract; the botanical stretch is soft under bloom and feedback;
  Y2K chrome and glass are pale and abstract; thermal and ink-water came out gold (no still library on 47325's code).
- Demo: the How it's built card is 18.5 s of four sentences (the contest asks for how it is built); the MCP screen is
  dark as the 9:16 strip; the intro is 24 s of song before the first word (Tys's choice; Owly suggested 10-12 s).
- Long: the desk recordings' small UI text (Owly: record with a bigger app scale, no zoom: every desk shot would need
  re-recording on 47326, `wt/shots.py`, `wt/long_shots.py`, on the polished desk); Make and the timeline both show the
  one Make filmed (None "underwater"); Under the hood and How it's built run about 2 min.

## Rules (Tys's)

- Commit with `git -c user.name=Owly -c user.email=owly@local commit -F <file>`, the message ending
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never push. Stage only your own files by path (shared
  checkout: never stash, reset or switch branches). Another session owns `src/` and the top-level docs: ask it with
  SendMessage for code changes; your files are `docs/demo/*`.
- Never restart ComfyUI (8188), the proxy (8189), or Tys's desks 47320/47321; 47324 is the polish session's and Tys's.
  47326 is the recorder's (restarted 29 Oct 4:44 pm on the polished code; no Cloud key); 47325 renders Cloud Finals.
- No zoom or shake on the app screens; the voice pauses between sentences; every cut on a beat; outputs long enough to
  see; nothing shown twice in the montage; no wet paint, odd machine, Polly, cups or jugs, wheels, guitars or the
  piano/guitar "musical" run; kaleido only where it reads; interesting, unique objects; the first 20 s the best.
- Plain words everywhere; no em dashes.

## Traps found

- Git Bash heredocs and `printf` mangle backslashes and apostrophes: write scripts with the Write tool, run by path.
- PowerShell scripts are blocked: `powershell -ExecutionPolicy Bypass -File ...`, or run inline.
- Two assembler builds at once must not share a build folder (each output now builds in `build_<out stem>`).
- loudnorm's second pass can fall back to dynamic mode and shift the audio: `cutlib.loudnorm` is a gain and a limiter now;
  check sync after any change to the mix: `wt/sync_check.py <final mp4> <build folder>/voice.wav` finds where the
  body's voice sits in the final (the intro's length means in sync), `wt/montage_sync.py <montage> <song> <start>`
  checks a montage's sound against the song; and compare the audio and video stream lengths with ffprobe.
- A long-run ffmpeg concat filter over many inputs crawls: `cutlib.join_exact` re-cuts only the off segments and joins
  by stream copy.
- Desk 47325 runs code from 29 Oct 6:25 am: no `/api/songs/load` (upload the mp3 to `/api/analyze`); a vibe without a
  still library renders in a gold look there.
- Credits so far: 73 finished Cloud Final cuts (44 at 16:9, 29 at 9:16), 1,121 morphs, about 4,100 credits by the
  3.6-a-morph measure, plus a few cancelled starts; the dashboard was not read.

Commits so far: 3ecb8f9, 39382f9, d27e834 (all docs/demo and docs/HANDOFF_29OCT.md item 5).
