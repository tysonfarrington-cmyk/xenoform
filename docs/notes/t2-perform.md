# T2 Perform: the control view, the output window, REC (branch t2-perform)

Worktree `C:\Projects\xf-t2-perform`, branch `t2-perform`, cut from `ui-review-4nov` (574c1fc). Built to
docs/UI_REVIEW.md 6.5 and 4.7 and T2 of docs/HANDOFF_4NOV.md. Closes V1, V2, V4, V5, V6, V7, V8, V10, V11, S3 and the
Perform half of N7. Not merged, not pushed.

## What landed

- **Two windows from one page.** `vj.html` without flags is the control view; `/vj?out=1` is the output window: the
  canvas and nothing else (no bar, HUD, toast or cursor; no keys but Esc, which focuses the control view; double-click
  for fullscreen). **Open output window** places it on the second screen with the Window Management API
  (`getScreenDetails`) and opens a plain window otherwise. A `BroadcastChannel` ("xeno-rig") carries the state (scenes,
  the song's analysis, look, knobs, held pad, REC) one way and the output's size, fps and REC state back. The control
  view's monitor shows the output's live canvas (its `captureStream`, handed across the window boundary). Close the
  output and the picture comes back to the control view. `/vj` folds into Perform; `/vj?out=1` is the output's URL.
- **The sound lives in the control view**, the window you click in, because Chrome may not let a popup start audio. The
  song plays from its decoded buffer on the AudioContext clock. The output reads that clock, the analyser and the take's
  audio track straight from `window.opener` (probed first: cross-window MediaStreams and tracks record fine in Chrome).
  The picture follows the sound as heard (`AudioContext.getOutputTimestamp`), drawn one frame ahead.
- **One design choice differs from the brief's wording.** The beat-locked switching (which scene, which transition, on
  which beat) runs in the window that draws, against the song's clock read directly, so a switch lands on its frame with
  no message in between. The control view therefore sends intent: the transition choice, the switch grid, manual
  next/previous, pads, knobs, looks, the source and the song's analysis. It reads the current scene and transition back
  from the output's reports, rather than sending them. Everything else the brief lists is sent as state.
- **REC done right.** The dot and the timer are in the control view only. The take is the drawing canvas (the output's,
  or the control view's with no output) at its size, held while recording (V10), with the song's sound or the mic's
  (V6). Chunks go to the desk every second (`POST /api/perform/takes/<id>/chunk`, in order, retries taken once). On Stop
  the desk remuxes to an H.264/AAC mp4 beside the webm in `work/ui/takes/<id>/`, and the take shows in `/api/videos` and
  My videos as a take card (Play, Download). Leaving the page during a take asks first (V7). A take cut short by a crash
  is finished into an mp4 the next time Perform opens. If the H.264 encoder never starts, the take restarts on VP8.
- **The control view (S3, V2, V4, V5, V11).** On the desk's tokens and components (`button.ghost/generate/text`,
  `.toggle`, `.chip`, `.xf-knob`, `.xf-lane`, `.panel`; no `!important`):
  - the transport: play/pause, back to the start, the clock, Cue next drop, landing on the next bar;
  - the song strip, drawn from the desk's analysis: sections coloured by role, drop runs by heat, the main one outlined,
    an energy lane from the stems envelopes (or the desk's waveform), beats and bars, the cut's shots, the pads' holds
    as blocks, the playhead. Click a section to cue it, click the beat row to jump there;
  - now/next ("next drop in 8 beats") and the held pad ("let go and it snaps back to the song at 2:23");
  - the source in groups (Pictures: this cut, library loops, Add loops; Sound: the song, mic/line-in, the input);
  - eight pads, the cut's own objects first and then looks. Hold = show, release = snap back, last-in-wins; drag a
    scene, a still of the cut or a look onto a pad;
  - Blackout, Master fade, and knobs for Intensity, Speed, Glow and Chaos;
  - Load track as the primary on the empty monitor; Help as a docked sheet that closes on Load track and Rec.

  The fifteen pills are grouped into Source, Look and Output. The keyboard shortcuts stay. Space is now play/pause
  (V5); → is the next scene. New keys: Shift+1–8 hold pads, D cue drop, B blackout, O output, Home. The strip uses the
  desk's analysis, not the browser's BPM guess: `/api/simple/strip` when T5 has landed, else `/api/perform/song/<id>`
  (same shape). The browser's grid only fills in until the desk answers.
- **From the cut to Perform (V1, N7).** `/vj?job=<id>` loads that cut's clips as the first scenes, its song (or its own
  soundtrack when the song file is gone) and its stems (`GET /api/perform/job/<id>`). It reads the cut's sections,
  beats, bars and drop from `lane.build`. **Follow the song** plays each shot's clip on the song's clock at the speed it
  was cut at. `vjUrl()` passes the job, and the cut's screen has one **Perform it** link beside Download.
- **Pad holds and T1.** Pads go through `XenoMidi.holds` (press, release, top, clear, on). `vj.html` defines a local one
  only when `midi.js` has none, and I proposed these names to the T1 session. Learnable targets: `pad:1`–`pad:8`,
  `blackout`, `master`, `glow`, `speed`, `chaos`, `play`, `cue:drop`, `output`. `midi.js` is untouched.

## How it was verified

- **Playwright** (`docs/ui_review/tools/perform_check.js`, my desk on 47356, headless Chrome) passes every check:
  - the output window shows only the canvas, and the monitor shows it;
  - takes from the output window and from the control view alone are saved as mp4 and webm at the canvas's size;
  - the reddest corner pixel across every frame is 0: no overlay;
  - the output canvas holds 1280×720 while its window is resized mid-take, then follows the window again;
  - a mic take carries the input's sound (max 0 dB);
  - a refused microphone says how to allow it;
  - closing the control view mid-take asks first, and staying keeps recording.
- **The sync measurement** (acceptance: within one frame). A click track (a 3 ms burst every 0.5 s) was loaded with Load
  track and the song's beats set to the clicks. With `?sync=1` the picture turns white for 50 ms from each beat of the
  song's clock. Ten seconds were recorded at 60 fps. `perform_sync.py` then finds each click in the take's sound and the
  rise of each flash in its picture, both on the file's own timeline. The final run on the committed code is shown
  first; the two runs before it are in brackets. Each had 20 of 20 clicks paired:

  | take | file | picture − sound, median | range | drift of the clicks |
  | --- | --- | --- | --- | --- |
  | output window | webm | −2.0 ms (−2.9, −3.2) | −6.5 to +2.5 ms (worst of three: −7.9 to +2.5) | 0.0 ms |
  | output window | mp4 | −4.5 ms (+3.5, −3.2) | −4.5 ms (worst of three: −13.2 to +3.5) | 0.0 ms |
  | control view alone | webm | −8.2 ms (−2.4, −1.4) | −12.2 to +3.8 ms (worst of three: −12.2 to +17.1) | 0.0 ms |
  | control view alone | mp4 | −12.2 ms (−4.9, +2.1) | −12.2 to +4.5 ms (worst of three: −12.2 to +18.8) | 0.0 ms |

  One frame of a 30 fps take is 33.3 ms; every click lands inside one 60 fps frame (16.7 ms), give or take the
  capture's own frame quantisation. The take's sound sits 80 to 190 ms into the take: that is when the check pressed
  Play after REC, and it stays constant (drift 0), so the sound neither slips nor runs fast against the source.
  Measured latencies while recording (headless Chrome): base 10 ms, output 32 to 40 ms, the heard time 40 to 53 ms
  behind the rendered.

  How it got there:
  - The first build drew the picture on the AudioContext's rendered time, and the picture led the sound by 34 to 38 ms.
    That is just over a frame; the take's sound is stamped as heard.
  - Following `getOutputTimestamp` made the picture trail by about 18 ms. Drawing one frame ahead centres it.
  - VP9 dropped frames at 1366×900 / 60 fps on this shared machine. H.264 in webm keeps up.
  - ffmpeg's `-r 60` put every frame a slot late in the mp4 (+15 ms against its webm). `fps=60:round=near` keeps it
    where the browser stamped it.
- **Pytest**: `tests/test_perform.py` (10 tests) covers chunks in order (a duplicate taken once, a gap refused), finish
  and remux (h264/aac), interrupted takes, id checks, `/api/videos` with takes, `/vj?job=` and the cut payload, a copied
  cut playing its own clips, the soundtrack fallback, the song strip, and the `app.js` links. The pinned `vj.html` tests
  pass unchanged.
- **Full suite**, before the last commit (`PYTHONPATH` on this worktree, the timing test
  `test_demo_animatic_is_the_fast_path` deselected): 1706 passed, 2 skipped, 1 failed. The one failure,
  `test_midi.py::test_websocket_fan_out_and_http_ingest`, fails the same way on the untouched base commit: the shared
  venv's MIDI bridge reports available. `test_stems_api.py::test_background_split_reports_a_failed_split_and_tries_again_next_time`
  failed in an earlier targeted run and on the base commit, then passed in the full run, so it is flaky.
- Also checked in Playwright:
  - every-beat switching on the demo;
  - Cue next drop landing at 5.6 s (the drop is 5.5 s);
  - follow-the-song switching clip 4 to clip 5 at the drop (14.0 s);
  - the pad hold stack (look, then scene on top, release, release);
  - blackout by click and by B;
  - dragging a look onto a pad;
  - the help sheet closing on Load track;
  - 1366 and 375 px (no sideways scroll).

## Not verified, or left

- **A real second screen.** Window Management placement, the permission prompt and fullscreen on screen 2 need Tys's
  machine. `window.open` uses up the click's activation, so going fullscreen on open may not take. **Fullscreen output**
  (F) in the control view lends a fresh click and is the reliable path.
- Real speakers or an audio interface: the latencies above are headless Chrome's. The clock follows
  `getOutputTimestamp`, so it should adapt, but it was not measured on hardware.
- MIDI hardware with the hold pads (T1). The MiniLab profile still maps pads A to transitions; pads hold only when
  learned onto `pad:N` or when T1's profiles map them.
- A whole song or a stems cut opens in Perform with its song and strip, but plays the library loops: its clips live in
  its passages' cuts.
- Firefox: no Window Management, no H.264 MediaRecorder (VP8 is used). The output reads its opener the same way.
- Not built: **Keep take → keys** (a take's knob rides into keyframe lanes; it needs T5's keyframes), strip zoom for
  long songs, badges on controls (T1).

## Steps for Tys (second screen)

1. Start a desk from this branch (any free port), open a finished cut, and press **Perform it** beside Download. Or open
   `http://127.0.0.1:<port>/vj?job=<cut id>`.
2. Press **Open output window**. Chrome asks once about window management: allow it, then press again if no window
   appeared. The window lands on your second screen.
3. Press **Fullscreen output** (or F) in the control view. The output fills screen 2 with the canvas alone.
4. Press **Play** (Space). The cut plays itself ("Follow the song"). Hold pads 1–8 (mouse, or Shift+1–8) and let go;
   try Cue next drop (D), Blackout (B) and the knobs.
5. Press **Rec**, play a while, then press **Stop**. Watch the timer in the control view's header; nothing appears on
   screen 2. The take turns up in My videos on the desk, as an mp4, with the webm in `work/ui/takes/<id>/`.
6. With a mic or line-in: Sound → Mic / line-in. The input drives the beats and goes into the take, not to the speakers.

## Merge notes

- `vj.html` is rewritten. Round 0's V9 keydown line (`addEventListener('keydown',e=>{if(e.target.tagName==='SELECT')return;const k=e.key;`)
  is kept byte-identical, but its neighbours changed, so expect a small conflict there.
- `app.js` changes three things only: `vjUrl()` gets the job, the result actions line gets Perform it, and
  `galleryPanel` uses `takeCard`.
- `ui.py` changes two lines: the router include and `with_takes` in `/api/videos`.
- T5's Perform placeholder on `#perform/<job>` should open `/vj?job=<id>` (it does, per its note).
