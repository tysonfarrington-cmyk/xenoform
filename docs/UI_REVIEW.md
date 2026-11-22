# UI / UX review of the Xenoform desk, 4 November 2026

Task 0 of the 4 Nov handoff ([HANDOFF_4NOV.md](HANDOFF_4NOV.md)): walk the whole app as a first-time user, screenshot
every screen and state, write down what is confusing, cluttered or slow, where the dead ends are, where the styling
drifts and where feedback is missing, then propose a redesigned flow in Xenoform's own music-first style that folds in
the Under the hood panel, the MIDI map and the perform window. Nothing in the UI was changed for this review. Tys
approves or amends this page before any UI code moves.

Branch `ui-review-4nov`, a local branch in the worktree `C:\Projects\xf-uireview`, cut from `contest-rc2` at fd7ce76;
nothing is pushed. Screenshots: [docs/ui_review/shots/](ui_review/shots/) (75 jpegs: 62 scripted states plus 13
captures of the browser pane during the hand walk; `manifest.json` has the URL, viewport and console errors of each,
`README.md` the rerun command; the scripts are in [docs/ui_review/tools/](ui_review/tools/)). Shot names below refer to
that folder.

**The one-line finding.** The desk is honest and capable underneath, but it is one 3 200-pixel page of 187 buttons and 19
paragraphs where the song is a stats line, the primary action competes with two others, a render reads 2 % for five
minutes, one key press or one reload can lose the cut, and the two things Tys cares most about (what made a shot, and
playing it live from the controller) are either not on the screen at all or two closed drawers deep under a label that
says "not finished".

## Contents

1. How the review was done
2. What the app is today: the screens
3. The walk, as a newcomer meets it
4. Findings (dead ends, feedback, clutter, naming, styling, timeline, live page, setup, keyboard, slowness)
5. What already works and must survive
6. The redesign: Songline
7. What to build first, and how it maps onto the handoff's tasks T1 to T6
8. Decisions for Tys

The handoff's tasks keep their names, **T1** (MIDI in `/vj`, with **T1b** the controller presets), **T2** (perform window
and REC), **T3** (TouchDesigner bridge), **T4** (Under the hood), **T5** (the flow overhaul with keyframes) and **T6** (the
node pack). Findings are numbered by theme: N (navigation), F (feedback), C (clutter), W (words), S (styling), L (the
lane and the timeline), V (the live page), M (the machine and setup), A (accessibility), P (performance).

## 1. How the review was done

- A **clean desk**: a fresh worktree with an empty `work/ui`, started on port 47340 (launch entry `xenoform-review-47340`
  in `C:\Projects\xenoform-rc2\.claude\launch.json` and `C:\Projects\.claude\launch.json`: `PYTHONPATH` on the worktree's
  `src`, so `repo_root()` and the work folder are the worktree's; the Python is the shared `.venv` of `xenoform-rc2`).
  Tys's desks 47330 and 47331, ComfyUI 8188 and the proxy were not touched; the one GPU job of the review (a 30 s Draft
  prototype of Glitch Out, Neon noir, job 31680167) was queued when the ComfyUI queue was idle, plus one CPU re-cut.
- **The walk**, by hand in a browser pane at 800×600 and 1280×720: the first visit and the five-step tutorial, a bundled
  song, a vibe, every drawer, Make, the Making screen minute by minute, the cut's screen, its timeline and drawer tabs,
  the Guardrails bar, a re-cut, `/vj` with the help, HUD, learn mode and Rec, the Setup, Connect, judges, variations and
  moves pages. Thirteen pane captures of the states the script could not reach (Making, the re-cut, the Guardrails bar,
  the live drawer tabs, `/vj`) are shots 60 to 65b. No MIDI controller was connected during the review: every MIDI
  observation is of the software with no hardware (see decision 6).
- **The capture**: a Playwright script (the installed Chrome, 1440×900, plus 1024×768 and 430×932) drove 62 states and
  saved a jpeg and the console of each; it uploaded a song (liquid_dnb.mp3) and a clip (demo_v5_preview.mp4), broke the
  ComfyUI URL on purpose to see the error state, and reopened the finished cut for the result screens.
- **The code**, read against what the screens showed: `src/xenoform/ui_static/app.js` (6 709 lines), `index.html`,
  `ui_v6.js`, `midi.js`, `live.js`, `vj.html`, `theme.css`, `app.css`, `desk.css`, `ui.py`, `job_timing.py`, `lane.py`,
  `morph_pass.py`, `stems_api.py`. Ten themed code audits and three themed screenshot audits ran as subagents; every
  finding was then checked by a second reader against the code and a third against "would a first-time user meet this".
  Of 207 candidate findings, 103 survived; the rest were overstated, duplicates, or real but too far from the path of a
  newcomer, and a few of those are kept below as "also real". Merged by theme, the survivors and the walk's own
  observations are the 89 numbered rows of section 4. Three more readers then checked this page itself (facts against
  code and shots, the redesign as a first-timer and as a VJ, coverage against the brief); their corrections are in.
- Line numbers are from fd7ce76. Severity: **high** = a newcomer gets stuck, misled or loses work; **medium** = confusing,
  cluttered or slow enough to notice; **low** = polish.

## 2. What the app is today: the screens

| Screen | Route | What is on it | Shots |
| --- | --- | --- | --- |
| The desk | `/#simple` | One scroll: Song, The drop, Vibe (12 cards + More vibes), Morph source, the idea line, Loved chains, Knobs (+ Stem reactions, MIDI controller), Morph, Timing, Shape, Effects, Look, Foreshadow, Scenes, Backdrop, Fine-tune (14 rows), Work in progress, My videos. Side column: sample, five facts, Make, Queue Drafts, Watch a finished one, Setup, Open weights. | 01 to 14, 29 to 31 |
| Making | `/#simple/making` | Draft stills playing, "What is happening", the chain, the clock, Stop. The same screen serves every edit. | 60 to 60e (a Make), 64, 64b (a re-cut) |
| The cut | `/#simple/result` | Player, Took line, Guardrails bar, the shots lane with a four-tab drawer a shot (Shot, Look, Join, Regenerate), Share row; side column: Knobs again, Timing, Shape, Effects, Look, Foreshadow, Scenes, Backdrop, Re-cut, Render (whole song, Final), Try another vibe (12 cards), Back to the song. | 40 to 49, 61 to 63b |
| Showcase | `/#simple/showcase` | A finished cut to watch, Make your own, Download. | 21, 21b |
| Setup & models | `/#setup` | The tier, disk, the model cards with Download buttons, the film pack. | 18 |
| Connect an AI | `/#connect` | MCP snippets, Test connection, Start on this machine. | 19 |
| Dialogs | | Tutorial (5 steps), Settings (Comfy URL, add-ons, paid cloud, library folder), About, the Ctrl+K palette, the "…" menu. | 02 to 02e, 15 to 17b, 20 |
| Live VJ | `/vj` | A canvas and one bar of 15 pills; help (?), HUD (P), MIDI learn (L) inside the help, Rec (R), Fullscreen (F). | 28 to 28f, 50, 65, 65b |
| Judges | `/judges` | A second, browser-only desk: Drop a song, Pick a look (28 cards), Make, Your cut. | 24 |
| Variations | `/variations` | The queued Drafts side by side (empty until Queue Drafts is used). | 23 |
| Moves | `/moves` | Wan Animate 2 dance transfer: a still, a description, 13 moves. | 25 |
| Licences, Credits | `/licences`, `/credits` | Static pages in the old shell. | 26, 27 |

**Not walked** (each would be its own session; none changes the findings below): a Whole-song Make (20 minutes of GPU
and its own making screen, `songMaking`), a Your-clips Make and a bad upload (video import got one upload, shot 08b;
formats, size limits and failures were not tried), Stems mode's layers after a Make, Final and Cloud Final (the Cloud
Final tick in Fine-tune), Queue Drafts and the Variations page with content, Polly (Performer), a Moves render, the Edit
in Resolve pack, the vibe cards' example-cut layer (A3 cites its markup), the desk's Live tier (`live.js`, the raymarch
browser preview that plays when ComfyUI is down), the error states F1, F4, F5 and F8 (read from code, not forced on the
desk), the legacy hashes `#director`, `#scene` and `#notes` (tidied to `#simple` by app.js:28), the dev page
`/static/live-smoke.html`, and the picture-attach `alert()` (app.js:6411).

### The handoff's status list, corrected

The handoff says MIDI input, recording and the REC dot are "not done (no code found)". That is not quite right, and the
plan for T1 and T2 should start from what exists:

- **MIDI exists**: `ui_static/midi.js` is one mapping layer for `/vj` and the desk, with Web MIDI (Chrome, Edge, Opera),
  an Arturia MiniLab 3 factory profile and a generic one (midi.js:14-34), Learn mode, per-row learn and remove, Export
  and Import JSON, persistence in `localStorage["xeno-midi"]`, and a Python bridge (`midi_bridge.py`, `xenoform midi
  serve|list|record`, cli.py:160-166) that fans the controller out over `/ws/midi` and `/api/midi/stream`
  (stems_api.py:858, 897). The desk's four macro knobs and the stem lanes are its desk targets (`macro:intensity|speed|
  chaos|glow`, `drums|bass|other|vocals`, `stem:N`; midi.js:29-31, mounted in the knob strip at ui_v6.js:88-94). What
  T1 asks for and is **not** there: pads as hold-to-override with snap-back, soft takeover on absolute knobs, a
  server-side `~/.xenoform/midi_map.json`, maps keyed by device name with an auto-loaded preset on connect, an on-screen
  map overlay, and a picture of the controller.
- **Recording exists** on `/vj`: `record()` (vj.html:283-289) captures the WebGL canvas with `cv.captureStream()` and a
  MediaRecorder, with the track's audio when a track is loaded, and downloads a webm on Stop. The bar, HUD and toast are
  DOM elements beside the canvas (vj.html:44-70), not drawn on it, so they never land in the clip. What T2 asks for and
  is **not** there: a second (perform) window, a REC dot that stays visible with a timer, a recording that survives Hide
  controls and `?clean=1`, mic audio in the recording, saving to the library instead of a download, and a locked frame
  size.
- **Not there at all**: the MIDI bridge's packages in this install (the `[midi]` extra in pyproject.toml:35 names `mido`,
  `python-rtmidi` and `websockets`, none of which is in the shared venv, so every page load logs a failed `/ws/midi`
  connection and falls back to SSE), any Under the hood view, any keyframes, any TouchDesigner template.

## 3. The walk, as a newcomer meets it

**First visit (01, 01b, 03).** The desk opens on a tutorial card over the vibe grid, with the song card's purple "Choose a
song" and the side column's purple "Make my video" both lit. The preview already plays a Deep-sea glow sample, the facts
say "0:12 (the whole song)" and the drop card says "The main drop: 0:06, 6 s", for a song nobody chose (the bundled
demo is loaded silently). Before anything is pressed the desk has split that demo's stems with Demucs (16 s of CPU) and
fetched NASA seed clips from the network; nothing says so. The page is 3 226 px tall at 1440 wide and holds 187 buttons;
the right column with the Make button only runs beside the top third, and the lower two thirds have the right third of
the page empty. At 430 px (29) it is 6 366 px tall and Make comes after My videos, about six screens down.

**The tutorial (02 to 02e).** Five steps: Song, Vibe, Knobs, Make ("Simulated. No GPU job was started." but nothing
visibly happens: it only highlights the side column), and "Open weights", a licence note. No step shows the cut's
screen, the timeline, Final, Share, MIDI or `/vj` (the Make step names the timeline and Final in one line). The header
strip stays on "1 Song" through all five steps.

**Choosing a song (04, 04b, 05, 05a).** The Glitch Out chip ticks Song and moves the strip to "2 Vibe". The card becomes
"Glitch Out · 3:58 · 90 BPM · 103 sections" with a thumbnail waveform in the middle third of a wide card, and a stems
line that counts up ("splitting with Demucs… 61 s"; 69 s in all). The drop card rewrites itself in prose: "The heaviest
of 5 drop runs by heat times length, 2:22 to 2:50 … The 30 s prototype is cut around it: 2:08 to 2:38." The facts update
honestly (0:30 around the drop, 13 morphs, about 6:20) and the button becomes "Make a 30 s prototype". While the split
runs the whole desk is rebuilt every two seconds (the accessibility tree went stale between two clicks three times).
"Change" throws the song away at once with no cancel (05a); a reload keeps the vibe, the knobs and Fine-tune but not the
song (31).

**Choosing a vibe (06, 07).** Neon noir ticks Vibe and lands the strip on "3 Prototype" with Make as the one lit button.
Good. Under the grid: More vibes (16 more), Morph source, the idea line with four example rows, nine Loved chains, the
Knobs panel with an 80-word paragraph, Stem reactions, the MIDI table, then nine chip rows, Fine-tune and Work in
progress.

**Make and the Making screen (60 to 60e).** The hash becomes `#simple/making`, the tab title "(2%) Making · Xenoform",
the header reads "Draft playing · 0:13 elapsed · morphs · about 6:07 left", the draft stills play, four steps tick. Then:

| Elapsed | Header | Percent | Status line |
| --- | --- | --- | --- |
| 0:13 | about 6:07 left | 2 % | Growing 13 flowers objects for this idea (about 98 s) |
| 1:13 | about 5:07 left | 2 % | the same line |
| 2:59 | about 3:21 left | 2 % | the same line |
| 5:28 | about 5:43 left | 9 % | Morph 1 of 13 · about 723 s left |
| 8:49 | | 100 % | Cut ready in 526 s |

The first five minutes were an unplanned step (the vibe's pool lacked the "flowers" family, so Z-Image grew 13 stills)
that the estimate never counted, shown at 2 % under a line that promised 98 s, while the header counted down the plan's
estimate, which never learns from the stage. At 5:28 two estimates sat on one screen, 5:43 and 723 s. The chain listed
on screen changed under the user after the grow (13 of 14 names different) with no word. The monitor caption said "Shot
1 of 103" throughout (the stills draft's count) beside "13 morphs" and "14 stills". The plan said 6:20; it took 8:49.

**The cut's screen (61, 40 to 49).** Player, "Your video is ready", "Took 8:49 · morphs 8:02 · cut 0:36 · check 0:03", an
amber Guardrails bar that opens into four log lines (62: `[taste] 1 neon-noir still left out of the pick; no-black-
heart-or-dna: dna helix …`, `[qa] 1 cut(s) more than 40 ms off the beat`), then the Timeline: 13 tiles with the passage
bar (build, drop 1.0), the drop mark and the seam diamonds, "click a shot, or the seam between two, to change it". A
tile opens a drawer with Shot, Look, Join and Regenerate tabs; a seam opens Join (63b: Handoff Flow or Cut, Move it by a
beat or half, a Transition select with 21 entries from "Chrome refraction carry" to "smear"). Regenerate (63) holds the
Morph style chips (a click starts a GPU re-render at once), Swap the object, Re-render this morph with an empty seed box
and a length, a prompt *variant* select, Generate here and Dream here. Nowhere on this screen is the prompt that made
the shot, its seed, steps, cfg, model or size; the closest thing is a raw JSON link, "Seed file", in the Share row (48).
The side column repeats the Knobs, Timing, Shape, Effects, Look, Foreshadow, Scenes and Backdrop rows of the first
screen, then Re-cut, Render the whole song, Render at Final, and twelve small vibe cards.

**A re-cut (64, 64b).** "Re-cut with these knobs" (CPU only, 36 s) replaces the whole screen with "Making the
prototype.", the header "11:34 elapsed · assemble" (the time since the original Make, frozen), no ETA, all four steps
ticked, and the line "Cutting shot 11 of 13 to the beat". The player, the timeline and the drawer are gone until it
lands, and the cut's screen then shows the original "Took 8:49" again.

**Live (28 to 28f, 50, 65, 65b).** `/vj` opens on a library loop already playing and one bar of fifteen identical pills;
nothing says what to do first. "?" shows a 12-row key table with the MIDI mapping table underneath it inside the same
modal; "L" opens that modal over the pills you are asked to click. The HUD knows BPM, beat and FPS and nothing of the
song's sections or drops. From a finished cut the only way to `/vj` is the first screen's Work in progress → Live (or
About); the link built from a reopened cut carried `track=demo` and no job (50), and the page plays stock loops, not the
cut. Output and controls are one window.

## 4. Findings

Each line: severity, what happens, where (shot, or file:line), and the smallest fix. Code lines are from fd7ce76.

### 4.1 Dead ends and lost work

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| N1 | high | **Escape cancels the render and freezes the Making screen.** Escape with no dialog open posts `/cancel` and sets `ignoreJob` but leaves the phase at making with no note; `poll()` stops, the logo and Back keep you there. Only Stop or a reload gets out. The "…" menu is a `<details>`, so Escape there kills the render. | app.js:5520-5527, 4529-4531, 5668-5671 | Make Escape do what Stop does, or ask first. |
| N2 | high | **A GPU shot edit throws away timeline edits waiting for Apply.** Re-render, a Morph chip, Generate here, Dream here and Swap post only their own fields; when the job lands the lane reloads from the record. Only Apply carries pending shot and seam edits. | app.js:2922-2930, 2879-2881, 4543-4545, 2985 | Send pending overrides with every GPU edit, or warn while edits are pending. |
| N3 | medium | **Reload during Making orphans the job while the page says "You can leave this page… waits for you".** `boot()` never asks for a running job; `#simple/making` falls back to `#simple`; `/api/videos` lists finished files only. Whole songs reattach, single Makes do not. | app.js:975, 6646-6660, 66-79; ui.py:2614 | Keep the job id in the URL or storage and resume `poll()` on boot. |
| N4 | medium | **Reload or a shared `#simple/result` URL loses the cut's screen and its unapplied edits**; the song is not restored either (`EASY_SAVED_KEYS` leaves out song, job, reopenUrl). The cut survives in My videos, so this is rework, not lost files. | app.js:70-79, 114-117 | `#simple/result/<id>`, reopened as the gallery row does. |
| N5 | medium | **"Back to the desk" from Setup, and the logo, drop the cut's screen**: they push a bare `#simple`, which turns result into choose. The browser's Back would have kept the cut. | app.js:3756, 5212-5217, 70-79 | `history.back()` when the previous entry is the desk, or keep the phase. |
| N6 | medium | **Same-tab links leave the desk and come back to a fresh boot**: header Open weights, the menu's Judges page, Moves, About's credits and judges links. The song is never saved and the result is not in the URL. | index.html:23, 33; app.js:1589; ui.py:322-338 | Open side pages in a new tab, or make the desk restorable from its URL. |
| N7 | medium | **Perform is reachable only from a closed drawer on the song screen.** VJ and MIDI live in Work in progress → Live, absent from the cut's screen; `vjUrl` sends track and stems but no vibe or job, so `/vj` plays stock loops; the WIP MIDI button opens Fine-tune for nothing on its way to the MIDI panel in Knobs. | app.js:1580-1591, 295-317; ui_v6.js:91; vj.html:164 | A Perform button on the cut's screen that opens `/vj` with this cut's clips. |
| N8 | medium | **A stopped or failed whole song leaves Resume as the only way off its screen**; the logo skips its reset while the phase is making and the strip draws no buttons. | app.js:1441-1454, 5145-5148, 5669 | A "Back to the song" on a stopped or failed song. |
| N9 | medium | **The stage strip's buttons do nothing on Setup and Connect** (no cut open): they scroll to a desk element that is not on the page. | app.js:100-104, 5198-5209 | Set `#simple` first, then scroll. |
| N10 | medium | **A reopened cut can inherit "A passage of the whole song"** from an earlier passage edit: `fromSong` is cleared only by a new Make; the reopened cut gets the passage label, the wrong Back and no Render row. | app.js:4998-5020, 5193-5196, 993-1002, 891 | Clear `fromSong` in video-open, easy-again and the showcase. |
| N11 | medium | **Tutorial opened on a cut or Making screen points at controls that are not there** (`contextReady` checks the view, not the phase); the card shows with no highlight. | tutorial.js:256-264, 457-470; app.js:5366 | Move the desk to the song screen for those steps, or disable Tutorial there. |
| N12 | medium | **"Change" forgets the song at once** with no cancel; an uploaded track has to be uploaded and analysed again; the drop card keeps showing the old song's drop with no name (05a). | app.js:1057, 5128-5134 | Keep the song until a new one is picked. |
| N13 | low | **My videos → Re-render overwrites the vibe, knobs and seed, then answers in the side column** ("Choose the song again, then Make"), far from the gallery at the foot. | app.js:5025-5034, 1103 | Note on the card, scroll to Song. |
| N14 | medium | **A reopened cut is a stub of the cut you made** (40, 46): Reopen from My videos shows "Took 8:49." with no breakdown, no Guardrails bar (the job in the page is `{id, status, stage, progress, video, reopened}`, though the record on disk holds the four notes), and "The song is not loaded in this window … choose it again on the first screen to render", so Render is off until the song is picked again, although the job folder knows its song. | app.js:4998-5020 (video-open); the reopened job stub | Reopen the record whole: song, notes, took breakdown, render. |

Also real, lower on a newcomer's path: the side pages ignore the proxy base path; a finished Make pulls you off Setup.

### 4.2 Feedback: progress, errors and honest numbers

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| F1 | high | **A failed timeline edit reports as success.** When a re-cut, swap, re-render, insert or dream throws, the server sets status done, error None, and "…did not run" in `detail`; `poll()` shows the old video and writes "Took X" or "Your cut is ready". | ui.py:797, 910, 955; app.js:4535-4553 | Status error with the reason; show `detail` when `video_version` did not change. |
| F2 | high | **The bar sits at 2 % through an unplanned step, and the morph stage reports coarsely.** `stage_frac` maps the restyle phase through RANGES so its first tenth reads 0; the grow step is not in the plan; the header's countdown is the server's plan-based `eta_s` counted down between ticks, so it never learns from the stage it is in. Seen live for five minutes (section 3, 60b to 60d). | job_timing.py:75-90, 207-216; app.js:3209-3223 (header), 3313-3317 (bar and tab title) | Count the grow step as a phase with its own estimate; drive the bar from "morph n of 13" (the queue knows). |
| F3 | medium | **Two ETAs on one screen** ("about 5:43 left" in the header, "about 723 s left" in the status) in two formats (60e). | app.js:3209-3223 (header); the job's `detail` line | One clock, one place, one format. |
| F4 | medium | **The Making screen hangs forever when the desk restarts or a poll fails**: `poll()` returns silently on a non-OK response and never retries; `tickEasy` keeps the clock moving. | app.js:4527-4530, 3301-3318; ui.py:2981 | Retry with backoff, then "lost contact with the desk". |
| F5 | medium | **Make refusals (429 "Two cuts are already rendering") are overwritten** by "Playing the pictures for this vibe", and `response.json()` is unguarded, so a 500 leaves Making stuck. | app.js:4517-4521, 3579-3584; ui.py:2875 | Show `state.job.error`; guard the fetch. |
| F6 | medium | **Edits reuse the old Make's clock, bar and steps** ("11:34 elapsed", four ticks, "Making the prototype" for a 36 s re-cut; 64, 64b). `postCutEdit` never resets `startedAt` or restarts `tickEasy`; `MAKING_STEP` has no restyle stage. The whole-screen swap itself is L7. | app.js:2886-2893, 3537-3541, 4032 | A timer per edit, a title per edit, progress on the shot's tile. |
| F7 | medium | **Stop during an edit says "cancelled" while the GPU keeps going**: `_run_edit` takes no cancel hook. | app.js:5157-5163; ui.py:934-955 | Pass the cancel hook, or keep the user on the cut and say the edit will finish. |
| F8 | medium | **Whole-song failure gives no reason** ("A passage did not render." even when only the assembly broke; rows say "failed"); the server sends the window detail and `assembly.error`, the UI shows neither. | app.js:1441-1449; song_run.py:131, 159, 167 | Show them. |
| F9 | medium | **A finished Make hides the server's warning** (cloud fell back, GPU out of memory dropped a tier, frame fill did not run): done replaces `job.detail` with "Took X". | app.js:4549-4553; ui.py:3475-3480 | Show `detail` beside Took when it differs from the plain line. |
| F10 | medium | **The time estimates do not add up** anywhere they appear: "About 3:06 (1:48 morphs, 0:58 look)" is 2:46; "6:20 (5:12, 0:48)" is 6:00; Fine-tune's Forms row says "120 forms: about 1:10:20" for the same 30 s the facts price at 6:20; the showcase says "a few minutes". | 01, 04, 05, 13, 21 | One estimate from one source, quoted everywhere, parts that sum. |
| F11 | medium | **The bad-endpoint state is one small amber pill** (16b): Make stays lit and the facts still promise "About 7:44 on this GPU". The Settings address only moves the health ping; renders go to the proxy on 8189 whatever it says, and the value is lost on reload. | app.js:5579, 4367; restyle.py:260-281; ui.py:457 | A banner with the failing address and the consequence; persist the address or say the proxy port is fixed. |
| F12 | medium | **Clip upload has no visible result** (08b): "1 clip here.", no name, no thumbnail, and the facts still say "17 morphs on the beat". | app.js (Your clips row) | List the clips; re-plan the facts. |
| F13 | medium | **The Guardrails bar opens into raw log lines** (62: `[taste] … (no-black-heart-or-dna)`, `[qa] 1 chromatic aberration flag at 16.5s`) with no link to the shot they mean, and it is gone after a Reopen (N14). | the walk; 62, 40 | Plain sentences, each a link to its shot on the timeline; keep them with the cut. |
| F14 | low | **My videos lists a cut while it is still rendering** with Reopen, Re-render and Copy recipe and no "rendering" state (03). | app.js:2396-2416 | A rendering state on the card. |

Also real: one failed stems poll turns into "split did not finish"; model and film-pack downloads freeze on "Downloading"
after one failed poll; a Cloud estimate failure drops the server's reason and turns Cloud off; Grow stills progress stops
after one failed poll; a failed model pick on Setup shows nothing; a running download disappears from Setup on reload.
F1, F4, F5 and F8 were read from the code and not forced on the review desk.

### 4.3 Clutter and the order of things

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| C1 | high | **At 430 px the Make button is 5 500 px down, after My videos** (29), with about 600 px of empty dark space under it. | desk.css layout | The Make card after Vibe on narrow widths, or a sticky bottom bar. |
| C2 | medium | **Three primaries compete on the first screen** (01, 03): the tour's Start, "Choose a song" and "Make my video" are all lit purple; about 35 targets sit above the fold at 1440×900 (the header, 2 song buttons, 6 chips, Play the drop, 10 vibe cards, 4 thumbs, Make, 7 Queue segments). Queue Drafts shows before any video exists. | app.js:1047-1115 | One purple button per state; Queue after the first Make. |
| C3 | medium | **Make is live and the preview shows a vibe before a song or a vibe is picked** (01, 03): "Deep-sea glow · sample", "0:12 (the whole song)", and the drop card's "The main drop: 0:06, 6 s" with a playable Play the drop, all for the silently loaded demo; no card is selected and the grid says "Pick one". | app.js:1060, 753-767, 6473-6476 | Empty preview, facts and drop card until a song is chosen, or name the demo. |
| C4 | medium | **19 help paragraphs on the first screen before a song is chosen**, the Knobs one 80 words of strobe rules; most repeat the chips' tooltips. At 1024 px (30) the rows wrap into broken groups and the text reads as a manual. | app.js:1045-1138, 1072, 2035, 2212-2260 | One short line a row; detail in tooltips or Under the hood. |
| C5 | medium | **Fine-tune mixes plumbing with creative choices**: about 44 controls and 7 notes (Energy, Aspect, Length, Model, GPU tier, a ComfyUI address field, Forms, Beat FX, Orbit, End card, Your images, Library Grow ×3 and Import, Chain, Beat overlay, recipe code); its summary lists Look, Scenes and Backdrop, which are in Knobs. | app.js:1559-1574, 2263-2318 | Split into Output (length, aspect, model) and Machine/Library; summary lists what is inside. |
| C6 | medium | **MIDI and VJ sit under "Work in progress … not finished"**, two drawers deep, and the MIDI table is a collapsed row inside Knobs: in a performance-first product nothing on the screen shows live play (the dead end itself is N7). | app.js:1583-1592, 306-317 | Promote Perform and the MIDI map to the top level (section 6). |
| C7 | medium | **The MIDI panel reads as a developer page** (12b): raw targets (`macro:intensity`, `stem:1`), a mode column of `abs`, "no Web MIDI input · bridge: sse · 0 events", a JSON textarea and a localStorage note take most of the space; the Knob 8 row is clipped by an inner scroll; nothing moves when a knob turns. | midi.js:120-150 | Plain names, an activity light a row, a connected state, JSON behind a link. |
| C8 | medium | **Two rows are both labelled "Morph"** (source: Objects / Your clips / Stems, and style: Auto / Melt / …) about 500 px apart (08, 09). | app.js:1066, 1882; 1598-1615 | "Made from" and "Morph style". |
| C9 | medium | **Three control styles for one kind of choice** (12, 09): Morph, Timing, Shape and Effects are wide borderless text buttons (unselected ones look like plain text); Look uses bordered chips; Foreshadow, Scenes and Backdrop use compact segments. The Shape row lights two options with no separator (Breathe off · Drops Auto) in what looks like one pick-one row; Effects has nothing selected and its note begins "None:" with no None option. | app.js:1545, 1666-1697, 1700 | One segmented style for pick-one rows, one chip style for pick-many; split Shape into Breathe and Drops. |
| C10 | medium | **Rows do not show what they cost** (10, 11, 13, 14): the idea line says "about 38 s" and a loved chain "starts no render", but Grow 36 more, Grow 8 scenes, Make them, Cloud Final, Look and the knobs say nothing about GPU minutes or credits. | app.js (the rows) | A consistent cost tag: instant, ~N min GPU, cloud. |
| C11 | medium | **The side column loses a control and shows an empty box** (09, 12, 22): in Stems mode "What changes" has no buttons; other states show an empty bordered strip under the segmented control; the open "…" menu covers the showcase's chips. | app.js:1122-1139 | Render or hide; close the menu on page change. |
| C12 | medium | **The palette's results lack context** (20): "look" returns Auto, Off, Warm leak tagged only CONTROL, though Auto and Off exist in four rows; the typed text is pale grey on white. | app.js (palette) | "Look → Auto"; darker input text. |
| C13 | low | **Duplicates**: Backdrop Scenes "is the same as Scenes Only" and sits next to it (the word itself is W2); a Dither in Look and Dither hits in Effects; a Knobs h3 above ui_v6's own Knobs header; "Back to the song" twice on the cut's screen; the showcase carries "Your video is ready." over a stock reel (21). | app.js:2236-2259, 1680, 1700, 1071, 1001, 1033; ui_v6.js:88 | Keep one of each. |
| C14 | low | **Help notes send users to controls inside closed drawers or on other screens** ("grow some on the Library row first" on the cut's screen, which has no Library row). | app.js:2228, 2256, 1571, 1024 | Put the action where the note is. |
| C15 | low | **About 25 jargon chips explain themselves only in hover tooltips** (Warm leak, Cool echo, Noir glow, Bloom rush, Negative rush, Cyan flash, Trace, Slices, Silhouette, Kaleido, Slit-scan, Blocky smear …); Foreshadow's segments have no titles at all; on touch there is nothing. | app.js:1700-1731, 1545 | A one-line description on focus, or a tiny preview. |

### 4.4 Copy and naming

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| W1 | medium | **Length offers "Full song" and "Whole song" as two different things** in a shuffled order (Full song · 60 s · 30 s · Whole song · 15 s): one is a single Make of the track, the other the passage queue with its own screen and hours of GPU; the notes use both. | app.js:2301, 3252, 1097, 4792-4797 | "The whole song, one cut" and "The whole song, by passages", ordered by length. |
| W2 | medium | **"Scenes" means three things** (wide-frame stills, Breathe's long holds, the library group), and Backdrop Scenes equals Scenes Only (the duplicate row is in C13). | app.js:2216-2245, 1645, 2143, 1819 | One control for wide stills; another word for Breathe's holds. |
| W3 | medium | **Notes of 60 to 85 words sit inside the controls** (Knobs, Shape, Dense, the Final note), with handoff, orbit, "the other stem", LUFS, QA pass. | app.js:1072, 1645-1677, 2313, 912 | One short line; detail elsewhere. |
| W4 | medium | **"103 sections" on the song card** (04, 05) is the segment count, not sections a musician would name; "Shot 1 of 103" on the Making monitor is the stills draft's count beside "13 morphs". | app.js (song card, monitor caption) | Say sections as intro, build, drop …; count morphs or shots, not both. |
| W5 | low | **Polly and Performer name one feature**, with changelog copy ("The idea line no longer brings her in", "as it always has"); Setup says "the Pynchon register", "Needed for a live restyle", "Live+AI and TensorRT stay off". | app.js:1584-1586, 1645, 5733-5806; models_setup.py:550 | Present tense, the user's words. |
| W6 | low | **The first render goes by three names** (Prototype on the strip, Draft in the hint, "Make a 30 s prototype" on the button, "Your video" on the cut's screen); "Model" lists quality tiers; three things are called "cloud" (Cloud Final, Paid cloud, Comfy Cloud). | app.js:90-94; index.html:52-56 | One word a thing. |

### 4.5 Styling

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| S1 | medium | **The side pages do not share one shell** (23, 24, 25, 26, 27, 18): Variations and Moves have no header and a blue text link back; Judges has a slim header with "Desk"; Licences and Credits use the old orange wordmark and skip `desk.css`; Setup and Connect use the stepper header; Back is a boxed button on some pages and a link on others. | ui.py:322-338; variations.html; moves.html; judges.html | One header, one back control, `desk.css` everywhere. |
| S2 | medium | **The judges page's prompt is dark text on black**: `.screen .empty` is `var(--zinc-50)`, which the v8 tokens map to `--x-surface` #141419 on #050507; the energy slider uses `--ink`. | judges.html:14-32; theme.css:103-115 | `--x-text-2` and `--x-accent`. |
| S3 | medium | **`/vj` has a design system of its own**: only `theme.css`, its own `--line` and `--grad`, 13 px Space Grotesk controls, pill buttons with a white "on" state against the desk's violet; the MIDI panel hardcodes its own colours inside the desk. | vj.html:6-12; midi.js:122-127 | Move `/vj` and the MIDI panel onto the desk's tokens and components. |
| S4 | low | **No type scale**: 18 pixel sizes plus rem ones, 10 px fifteen times, 9 px on timeline badges; `theme.css` has no font-size tokens though `desk.css` promises 13 to 14 px. | desk.css:5, 620, 625; app.css:35, 1227 | Four or five size tokens with an 11 px floor. |
| S5 | low | **Off-palette colour**: 61 distinct hex values across the front end; about ten status and timeline colours bypass the tokens; the brand gradient is defined twice with different stops and used on `/vj` only; the tutorial ring still pulses the old orange. | theme.css:154; desk.css:617, 676; app.css:755 | Tokens for status colours; one gradient. |

Also real: desk.css uses the control-height and radius scales in ten places only; label casing switches between uppercase
eyebrows and sentence case; Moves and Variations dim text with opacity.

### 4.6 The lane, the timeline and the missing Under the hood

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| L1 | medium | **No Under the hood view.** The drawer head shows time, length and two nouns; lane rows carry no prompt, seed, model, steps, cfg, size or guide settings; the only place they exist is the whole cut's "Seed file" JSON (48). Tys's ask (one click from a shot to what made it) exists nowhere. | app.js:2789-2796, 873; lane.py:108-129 | Section 6.4. |
| L2 | medium | **Prompt, negative, steps, cfg and guide strength cannot be edited** and the record does not keep them per morph: `simple.json` holds per shot the look, effects, intensity, speed and timing, but the prompt text, steps, cfg, seed used, compression and model file live only in the request (the morph cache keys on them, so they exist at render time). | app.js:2839-2840; ui.py:990-992; morph_pass.py:883-893; morph_cache.py:122-162 | Write the morph request beside each clip; widen `/rerender`. |
| L3 | medium | **A Morph style chip starts a GPU re-render on a single click** (42d, 63): the chips look like the Look tab's toggles that wait for Apply. | app.js:2835, 4804-4805, 1610-1615 | A selection, rendered on "Re-render this morph". |
| L4 | medium | **Re-render replaces the take with no undo and no list of earlier takes**; the seed used is not shown (the seed box is blank, placeholder "next"). | dense.py:2717-2728; lane.py:88-91, 164-165; app.js:2837-2838 | Takes with their seeds and "use this take". |
| L5 | medium | **Reset the timeline starts a re-cut at once and wipes every saved edit**, with no confirm and no undo. | app.js:4737-4745, 2713 | A pending edit, or a confirm with undo. |
| L6 | medium | **Generate here and Dream here overwrite "this shot and the next ones"** without naming or marking the range before the GPU runs. | app.js:2841-2860, 2932-2940 | Highlight the span and say "replaces shots 4 to 7". |
| L7 | medium | **Every GPU edit replaces the cut's screen with the Making screen** (64); the player, lane and drawer are gone until it lands, then the lane reloads from scratch (the stale clock on that screen is F6). | app.js:2887-2891, 4539-4545, 922 | Progress on the tile; the timeline stays usable. |
| L8 | low | **A Final, Fast Final or Cloud cut has no Regenerate tab** and no line says why. | lane.py:226-247; app.js:2779-2789 | Greyed with a reason, or allow one Final shot. |
| L9 | low | **The beat grid is sent to the lane but never drawn** (only the drop has a mark, app.js:2674-2675); the beats serve only "Move it a beat"; the drawer speaks clock seconds, not bars and beats; section and transition are hover-only. | lane.py:248; app.js:2554, 2793 | Section 6.3. |
| L10 | low | **No keyframes**: intensity, colour and morph target are one value per shot. | app.js:2809, 2737-2746 | Section 6.3. |

### 4.7 The live page and MIDI

All of this was seen with no controller plugged in; the MiniLab profile, hold latency and learn with real hardware are
untested (decision 6).

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| V1 | medium | **`/vj` plays stock library loops, not this song's shots**: `vjUrl` sends track and stems; the page loads ten hard-coded vibes (40 loops) plus footage. The link is labelled "live visuals to this song's stems". | vj.html:162-166; app.js:295-303, 1590 | Load the cut's clips first (section 6.5). |
| V2 | medium | **No first step and no hierarchy** (28, 65): fifteen identical pills in three rows, no empty state, two unlabelled selects, no MIDI state visible. | vj.html:44-70 | Load track as the primary; group source, look, output; a MIDI dot. |
| V3 | medium | **The MIDI map and Learn are inside the "?" modal** under 12 rows of key help (65b); L opens that modal over the pills it asks you to click, so learning takes two clicks; the box has no max-height, so on a laptop the import button sits off screen. | vj.html:26-27, 69, 84, 302, 312; midi.js:154-155 | A docked panel, never a modal, with the map first. |
| V4 | medium | **The help sheet stays open through Load track and Rec** (28e, 28f) and clips the HUD. | vj.html | Close on load or Rec; a visible close. |
| V5 | medium | **No player**: Load track plays at once, Space means Next after the first press; there is no pause, seek, time or cue-to-drop. | vj.html:215-216, 305 | A transport strip. |
| V6 | medium | **A blocked mic fails silently** (no try/catch) **and mic-mode recordings have no sound** (the mic feeds the analyser only; help promises audio). | vj.html:196-197, 214, 284, 81 | Catch and explain; route the mic to the recorder or say video only. |
| V7 | medium | **No REC sign while performing**: the Rec pill fades with the bar after 3.5 s and is hidden under `?clean=1`; there is no timer; the whole take stays in RAM (24 Mbps, about 700 MB for four minutes) and downloads only on Stop; Stems or Desk mid-take loses it with no warning. | vj.html:31, 245, 282-289, 331 | A REC dot with a timer outside the canvas; stream chunks to the desk; block navigation while recording. |
| V8 | medium | **No perform window**: Fullscreen and Hide controls apply to the one window; any mouse move brings the bar back over the picture; `?clean=1` is reachable only by editing the URL. | vj.html:303-311, 330-331 | Section 6.5. |
| V9 | medium | **After using a dropdown every shortcut goes dead** (the key handler skips SELECT targets and the selects keep focus). | vj.html:304 | Blur on change. |
| V10 | medium | **The recording's frame size follows the window**, so Fullscreen mid-take changes it; the audio input menu does nothing once the mic is live, and Mic connects a second source on top of the first. | vj.html:146-149, 51, 195-197 | Lock the size while recording; handle the input change. |
| V11 | low | **The page knows BPM, not the song**: it re-detects tempo in the browser (80 to 170 BPM) and ignores the desk's sections and drops. | vj.html:198-211 | Section 6.5. |

Also real: typing in the MIDI import box fires live shortcuts; intensity, dance presets, tap tempo and stem gains have no
on-screen control; "MIDI: bridge" shows whenever the desk is up; Kaleido and Classic need hidden URL flags.

### 4.8 Setup, Settings and the machine

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| M1 | medium | **The desk never steers a newcomer to Setup before a Make with missing models**: `/api/setup` returns `missing_required`, nothing reads it; Make checks only that ComfyUI answers; Setup is a text link under Make and a menu item. | app.js:6656, 3555-3563, 1104; models_setup.py:532 | Block Make, or a "Get the 11.5 GB model" card beside it. |
| M2 | medium | **Final's Download fetches the 46 GB full LTX-2.3 file**, not the fp8 a 12 GB card uses, and not Gemma 3 or the upscaler the card's own text says Final needs; there is no LTX-2.5 card though About names it as the Final. | models_setup.py:58-73, 637-666; hardware.py:33 | Pick the file by tier; list the parts; one total. |
| M3 | medium | **Setup offers a 28.6 GB download with 4.6 GB free** two paragraphs apart (18); "12 GB" does not say VRAM or disk; the header said "not connected" while the card said "checked against ComfyUI". | 18; models_setup.py:642-647 | Disable or warn when size exceeds free space; title the tier. |
| M4 | medium | **Settings and About are long paragraphs of jargon** (16, 17): port 8189, the partner node, MCP, `xenoform osc`; "How the cut is made" sits over a URL field; half the settings live per browser, half on the server, and nothing says which. | index.html:56-96; app.js:6563-6646 | Short bullets; detail behind a link; say where each setting lives. |
| M5 | low | **Tier text contradicts About** (12 GB says Final is LTX-2.3; About says LTX-2.5 when installed); only NVIDIA is detected, so other GPUs read "No GPU". | hardware.py:31-63; index.html:54-57 | Generate the text from the resolved model; "GPU not recognised". |
| M6 | low | **Moves** (25): raw Pexels and Mixkit URLs as card text, a native file input, "Render this move" ghosted with no reason; its move names (push in, pull back, orbit, follow) are camera words in a music-first app. | moves.html | Thumbnails; credits behind a link; say what enables Render. |

### 4.9 Keyboard and accessibility

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| A1 | low | Make, Choose a song and Apply are white 13.5 px text on #7c6cff, about 3.9:1 (2.9:1 on hover): the weakest contrast on the desk is the primary button. | desk.css:144-154; theme.css:64-65 | A darker fill or dark text on hover. |
| A2 | low | The tutorial's arrow keys also turn the focused knob (both document handlers fire); the "Turn the knobs" step invites exactly this. | tutorial.js:606-616; ui_v6.js:114 | Ignore arrows from `[role=slider]`. |
| A3 | low | Each vibe card nests a role=button play badge inside a role=radio button: 12 hidden Tab stops; the example layer claims aria-modal but traps nothing and returns focus nowhere. | app.js:710-713, 782-806; desk.css:818-823 | Badge as a sibling; a native `<dialog>`. |
| A4 | low | Song passage buttons show no focus ring; arrowing the mini vibe cards on the cut's screen gets stuck after one step. | app.css:1483-1487; app.js:4599-4605 | Keep the outline; focus after render. |
| A5 | low | MIDI rows have anonymous learn and × buttons, × deletes at once, "Learn mode (L)" on the desk where L is not bound; the stem toggle is named only On or Off. | midi.js:137-154; app.js:6177 | Named buttons, undo, fixed labels. |

### 4.10 Slowness

| # | Sev | Finding | Where | Fix |
| --- | --- | --- | --- | --- |
| P1 | high | **Every click rebuilds the cut's screen, player included**: `render()` swaps `#app`'s innerHTML; the timeline handlers seek the player and then throw it away, so clicking a shot stops the video, jumps to 0 and re-buffers the no-store file. Every tab, look or FX chip does the same. | app.js:3730, 694, 1007, 4696-4728; ui.py:2612 | Keep the player node across renders; patch regions. |
| P2 | low | The whole-song making screen re-renders the desk every 3 s for hours, with a session POST each time; the desk rebuilds every 2 s while stems split. | app.js:1368-1373, 5958 | Patch the lines in place. |
| P3 | low | Polls never stop (agent session every 3 s, ComfyUI every 8 s, the job every 400 ms); library pickers load full 1024×576 stills as thumbnails; `/api/stills` rebuilds the catalogue about 30 times a call; `/vj` preloads 48 videos before the first beat. | app.js:6655-6659, 4574; ui.py:1521-1529; vj.html:160-166 | Backoff, real thumbs, a cached catalogue, lazy loops. |

## 5. What already works and must survive

- **The music-first seeds are there**: the drop card puts the song's key moment first; the facts (Video, Shots, Cut, Shape,
  Time) say in plain words what Make will render; the button says "Make a 30 s prototype"; the stage strip ticks as you go;
  the Making screen has a clock from the server's plan, a Stop, a tab-title percent and "You can leave this page".
- **Loved chains** say exactly what a click does and that it spends nothing. That is the model for every row.
- **The idea line** turns words into tagged chips and states the still cost. The vibe cards are big, image-led, tagged
  DARK and BRIGHT, with a clear selected state. A vibe picked from More vibes joins the grid and survives reload.
- **The timeline** exists with the right primitives: shot tiles with the cut's own frames, the passage bar, the drop mark,
  seams you can click, Flow or Cut, move by a beat, a transition a seam, Hold or Morph, per-shot look and intensity, swap,
  re-render, generate, dream, and the rule that every edit is a no-GPU re-cut except two. `lane.py` already carries
  sections, beats, the drop and heat.
- **The tour** is short, honest about simulating, with Back, Skip and Next. **Connect an AI** is a clean page. **Setup**
  states real numbers. **Credits** cites a source for every asset. The **Variations** empty state names the steps.
- **`midi.js`** is a sound mapping layer (profiles, learn, bind, export, import, bridge). **`/vj`'s** shader, the premium
  transitions, the recorder and the HUD are good bones. The Open weights badge and licence table are a credibility asset.

## 6. The redesign: Songline

Three independent designs were drafted from three angles (the song as the canvas, the performer's rig, a five-step rail
with progressive disclosure) and scored by three judges (a first-timer, a working VJ, the engineer with two weeks). The
song-as-canvas design won two of three; the rail won the first-timer on clarity; the rig won on live feel but lost on
feasibility. What follows takes the strip-everywhere layout of the first, the step bar and plain-word buttons of the
third, and the on-screen controller, hold pads and take lane of the second. None of it is a camera or 3D workflow, and
nothing here copies another editor's layout: the canvas is the song.

### 6.1 The principle, the steps and the lanes

**The song strip is the one surface.** Waveform, sections colour-coded, beat ticks, the drops flagged. Shots are blocks
on it snapped to beats; keyframes are points on it; the inspector, Under the hood, the MIDI map and the perform transport
all hang off it. You choose a vibe, make, refine and perform without leaving the music. Five steps in a bar, one violet
button a step, feel presets first, a sketch before any GPU, and everything else under the hood.

```
 1 SOURCE  >  2 PLAN  >  3 TWEAK  >  4 RENDER  >  5 PERFORM
 a bundled    a vibe;     feel, knobs,  spend GPU:   play it live,
 song or      shots on    MIDI badges   Draft (30 s  pads, knobs,
 your file    the beats;  (no GPU, a    round the    record a take
              sketch      re-cut)       drop), song,
                                        Final, Cloud
```

The word "Draft" is today's prototype: the 30 s around the main drop at the Draft tier. The desk keeps its dark studio
palette, the one violet accent, Space Grotesk titles, the vibe cards, the knobs and the chip vocabulary. What changes is
where things sit, and that the song is drawn, not described.

The strip's lanes, defined once:

| Lane | What it shows | On which steps |
| --- | --- | --- |
| SECTIONS | the song's passages, colour-coded, with the drops flagged (`lane.build`'s sections and `drop_run`; the colours are app.js's `SECTION_HUES`) | all five |
| WAVE | the waveform | all five |
| BEATS | beat ticks on the 24 fps clock (`lane.beats`); bars heavier | Plan, Tweak, Render |
| SHOTS | one block a shot, snapped to beats: hatched = sketched from stills, solid = rendered, ! = stale after an edit | all five |
| INTENSITY | a keyframe lane: points on beats that scale each shot's intensity | Plan, Tweak, Perform (as the take lane) |
| OBJECTS | a keyframe lane: a still pinned at a beat (the object the chain lands on there) | Plan, Tweak |
| PADS | what a held pad showed, and when | Perform |

One example runs through every picture below: the review's own cut of Glitch Out, Neon noir, 14 objects from dragon
scale shield to feather, whose drop is at 2:22.

### 6.2 Source and Plan: the main screen

Source is the same screen, ghosted, with one action: drop a song or press a bundled chip. The strip fills in as the
analysis lands and the desk moves to Plan by itself, so the newcomer sees the instrument before it plays. If the models
are not installed, the step bar's button reads "Get the 11.5 GB model" and goes to Setup (M1).

```
+-[HEADER]--------------------------------------------------------------------+
| o Xenoform   (1 Source) (2 PLAN) (3 Tweak) (4 Render) (5 Perform)  GPU ready |
+-[MONITOR: the sketch, no GPU]---------------+-[VIBE + idea]-----------------+
|                                             | [Liquid chrome] [Neon noir]   |
|     dragon scale shield -> elven crown      | [Porcelain]  [Deep-sea glow]  |
|     SKETCH: the vibe's stills on the beat   | [Risograph]  [Iridescent]     |
|                                             | [Molten gold] [Ink & paper]   |
| > 2:08 / 3:58   90 BPM   drop 1 in 7 bars   | more v   idea [ a moth, a key]|
+-[THE SONG STRIP: the canvas; wheel zooms; snap = beat, Shift = bar]----------+
| SECTIONS |intro |verse     |build   |vDROP 1 ######|release|vDROP 2 ####|out|
| WAVE     |.:|:.|.::..::.:|::|||||||||||||||||||||||:..::.|||||||||||||||:.  |
| BEATS    |''''|''''|''''|''''|''''|''''|''''|''''|''''|''''|''''|''''|''''  |
| SHOTS    |////|//////////|/////[1][2][3][4][5][6][7][8][9][a][b][c][d]////  |
| INTENSITY|____/''''\________/'''''''''''''''''\__/'''''''''''''\_____        |
| OBJECTS  |      * shield          * jellyfish        * butterfly   * feather |
|                          [== DRAFT WINDOW 30 s: 2:08 to 2:38 ==]   ^ now     |
+-[STEP BAR: one primary]-----------------------------------------------------+
| 13 shots on the beat, 13 morphs, about 6 min on this GPU   [ Tweak the feel >]|
|                                                   or Render Draft now (GPU)   |
+-----------------------------------------------------------------------------+
  / = sketched from stills, [n] = a shot block, * = an object pin. Click a
  shot: the inspector docks under the strip. Click a seam: the Join tab. Drag
  the window to prototype another passage. Keyframes: click a lane to add a
  point, drag it along the beats, Delete removes it, double-click types it.
```

What this replaces: the drop card (the strip shows the drops), the Song card's stats line (the strip's header shows
length, BPM and the next drop), the Chain row (the OBJECTS lane), the facts (the step bar line), the Length row (drag the
Draft window, or press Whole song on Render), and today's passage bar and seam diamonds. Shots keep their tiles.

Keyframes are saved in the project (`simple.json` as `keyframes {intensity, targets}`, and in the recipe code). Intensity
points on beats become each shot's `fx_intensity` at re-cut time (no GPU). Object pins (a still at a beat) set
`stills[slot]` through the swap path (two morphs). Colour keyframes stay per shot (the Look tab) in this round. Snap is
beat by default, bar with Shift, free with Alt.

### 6.3 Tweak

The same strip with the feel under it. A **Feel** row first (House, Dreamy, Hard glitch, Warm haze, Clean, Custom), then
the four knobs, then the chip rows. Each knob and chip wears a small badge of the controller element bound to it when a
controller is present (6.5). Before a Draft exists the primary renders it; after, the primary is a re-cut and the render
lives on step 4.

```
+-[HEADER]  (1 Source) (2 Plan) (3 TWEAK) (4 Render) (5 Perform)  controller: ----+
+-[STRIP, short: SECTIONS, SHOTS, INTENSITY]----------------------------------+
| SECTIONS |intro |verse     |build   |vDROP 1 ######|release|vDROP 2 ####|out|
| SHOTS    |////|//////////|/////[1][2][3][4][5][6][7][8][9][a][b][c][d]////  |
| INTENSITY|____/''''\________/'''''''''''''''''\__/'''''''''''''\_____        |
+-[FEEL]----------------------------------------------------------------------+
| (House*) (Dreamy) (Hard glitch) (Warm haze) (Clean) (Custom)                 |
+-[KNOBS, each with its controller badge when one is plugged in]---------------+
|   (o) K1        (o) K2        (o) K3        (o) K4       stems: drums (o) K5 |
|  Intensity 50   Speed 50      Chaos 30      Glow 40             bass  (o) K6 |
+-[CHIPS]---------------------------------------------------------------------+
| Morph style (Auto)(Melt)(Shatter)(Bloom)(Spin)(Fold)  Timing (Smooth)(Beat)(Snap)|
| Breathe (off)(on)   Drops (Auto)(Max)(off)   Effects [Dither][Feedback][Kaleido]|
| Look (Auto)(Off)(Warm leak)(Cool echo)(Noir glow)(Bloom rush)(Negative)(Cyan)  |
+-[MIDI: the map lives here]  Arturia MiniLab 3 (its own map)  [Map] [Learn]---+
+-[STEP BAR]------------------------------------------------------------------+
| no Draft yet: about 6 min on this GPU                       [ Render Draft > ]|
| with a Draft: re-cut from the cached morphs, no GPU, ~30 s  [ Re-cut ]  Render>|
+-----------------------------------------------------------------------------+
```

The chip rows keep their words but gain a one-line hint each on focus (C15), one segmented style for pick-one rows and
one chip style for pick-many (C9), and a cost tag wherever a choice spends GPU (C10).

### 6.4 The shot inspector with Under the hood

Clicking a shot on the strip docks the inspector under it on every step. It keeps the Shot, Look and Join tabs; Under
the hood is the fourth. Swap the object, Generate here and Dream here stay on the Shot tab, each with the span it
replaces lit on the strip ("replaces shots 7 to 10", L6).

```
+-[STRIP, shot 6 selected, its beats lit]-------------------------------------+
| SHOTS   [4 ][5 ]{[6 iron crown -> jellyfish]}[7 ][8 ]   build  vDROP 1       |
|                 '-- 2:22 in the song, bar 54 beat 1 . 1.3 s . 2 beats        |
+-[INSPECTOR]-----------------------------------------------------------------+
| < Shot 6 of 13 >   [Shot] [Look] [Join] [UNDER THE HOOD]            [Close] |
+-[UNDER THE HOOD: the real render; * = changed, = as the vibe's preset]-------+
| Model      LTX-Video 0.9.5 (Draft)  ltx-video-2b-v0.9.5.safetensors       = |
| Prompt     [a neon noir iron crown of thorns melts into a jellyfish, dark  * |
|             studio                                                        ] |
| Negative   [text, watermark, flicker, cut, blurry                         ] = |
| From still iron_crown_of_thorns.png [swap]   To still jellyfish.png [swap] = |
| Seed       [ 2733 ] [dice]   preset: the cut's seed 2727 + 6                = |
| Steps      [ 20 ]   CFG [ 3.0 ]   Frames 49 = 2.0 s at 24 (the shot plays   = |
|                                   1.3 s of it)                              |
| Size       512 x 288 (portrait Draft: 320 x 576, composed at 540 x 960)    = |
| Guides     first 1.0 . last 1.0 . compression 0                            = |
| Morph style [Melt v]   Timing [Smooth v]   LoRA [none v] (Final adds one)  = |
| Cost       1 morph, about 25 s on this GPU, then a 30 s re-cut               |
+-[ACTIONS]-------------------------------------------------------------------+
| [ Re-render this shot ]   [Copy recipe]   [Reset to preset]                  |
| Takes: #1 seed 2733 (this one) . #0 seed 2727 [use]     Open in ComfyUI (link)|
+-----------------------------------------------------------------------------+
  Every row has a one-line hint on focus (what steps, cfg and guides do to a
  morph). Values are the ones the render used; the preset is ghosted beside a
  change. Re-render is the only button that spends GPU, and it says so first.
```

Rules: the style chips become a select (L3); Open in ComfyUI is a text link that POSTs the graph to `:8188/prompt` or
downloads the `.json` (decision 7); Copy recipe copies the shot's recipe. Scope is one shot at first; section or song
scope comes once `/rerender` takes the new fields. With no shot selected the same panel holds the project's own
under-the-hood rows: aspect, model tier, GPU tier, the ComfyUI address, Forms, Beat FX, Subject sway (today "Subject
orbit"), End card, the library tools and the recipe code, which is where Fine-tune and Work in progress go.

**What the back end needs first**: write each morph's request (`morph_cache.parts_of`: engine, stills, prompt, negative,
seed, frames, size, steps, cfg, guides) into the record beside `clips[i]` at render time; a `GET /api/jobs/{id}/shots/{i}
/recipe` that returns it with the preset's values; `/rerender` widened from seed, length, variant and style to prompt,
negative, steps, cfg, guides and LoRA; a takes list per shot (the files already stay under `rerenders/`).

### 6.5 Perform: the control view, the output window and the MIDI map

```
+-[5 PERFORM]  output: Screen 2 1920x1080 [Open]   (*) REC 02:14 [Stop]  ------+
+-[MONITOR: a small preview of the output]--+-[NOW / NEXT]-----------------------+
|                                           | now   DROP 1 . shot 7 jellyfish    |
|        iron crown -> jellyfish            | next  release . in 8 beats          |
|                                           | held  pad A2 -> lotus: release      |
|                                           |       snaps back to 2:23            |
+-[SONG STRIP: playhead live]---------------+-[SOURCE]---------------------------+
| SECTIONS |intro|verse|build|vDROP1###|rel|vDR| (*) this cut   ( ) library loops |
| SHOTS    |     |     |     |[5][6][7]|   |   | ( ) mic / line-in                 |
| PADS     |                  [A2 held 2:21-2:23]                                  |
|                              ^ now                                               |
+-[PADS: hold = show it, release = back to the song]--+-[KNOBS, live, badged]----+
| [A1 shield][A2 lotus ][A3 jellyfish][A4 moon   ]    | Int (o)K1   Spd (o)K2   |
| [A5 strobe][A6 mirror][A7 freeze   ][A8 blackout]   | Cha (o)K3   Glw (o)K4   |
| the cut's own objects first, then looks; drag a     | master fade (o) F1      |
| still or a look onto a pad to change it             |                         |
+-[TRANSPORT]-----------------------------------------+-------------------------+
| [|<] [ > Play ] [Tap]  follow the song (on)  switch on (beat)(bar)(phrase)       |
| click a section on the strip to cue it   [Keep take -> keys]   PANIC: black      |
| MIDI: Arturia MiniLab 3 . its own map (*)  [Map] [Learn]   K1 armed, writing    |
+----------------------------------------------------------------------------------+

+-[OUTPUT WINDOW: screen 2, /vj?out=1]------------------------------------------+
|                                                                               |
|                  the canvas, full bleed, and nothing else:                    |
|                  no bar, no HUD, no REC dot, no cursor, no toast              |
|                                                                               |
+-------------------------------------------------------------------------------+
```

- **Which window does what.** The output window renders and records: it is `vj.html` in an out mode (`/vj?out=1`), the
  canvas and nothing else, opened on the second screen with the Window Management API where it exists (Chromium) and as
  a window you drag elsewhere otherwise. The control view sends state (song position, pads, knobs, looks) over a
  BroadcastChannel; it renders a small copy as the monitor. `captureStream` records the output canvas only, so the REC
  dot, which lives in the control view with a timer, can never be in the clip. The recording streams chunks to the desk
  and is saved to the library (decision 12).
- **One rig, two states.** Perform is the same strip with the transport rolling. Plan and Perform share the pads, knobs
  and map; a planned cut plays by itself, pads override it while held. "Follow the song" means the picture advances with
  the song's own shots; off, it switches on the chosen grid (beat, bar, phrase) as `/vj` does today.
- **Pads are temporary overriders.** Note-on shows the pad's scene or look; note-off snaps back to the shot under the
  playhead; the transport never stops; last-in-wins when several are held. A pad's hold draws as a block on the PADS
  lane. Pads default to the cut's own objects, then the looks; drag a still or a look onto a pad to change it. **Keep
  take** writes a take's knob rides and holds into the keyframe lanes (`midi_bridge.automation_to_envelopes` exists for
  the render side).
- **Live controls a VJ needs** (V5): cue by clicking a section on the strip (quantised to the switch setting), a master
  fade, a blackout pad as the panic, tap tempo, and a transport with pause and position.
- **The MIDI map lives where the controls are.** Each knob and chip wears its badge (K1, A2 …); **Map** draws the
  controller over the controls with its targets; clicking a badge opens Learn in a popover anchored there, never a modal.
  On connect the Web MIDI port name picks the map (MiniLab 3 by name; Tys's own layout shipped as the first map once his
  port name is read; unknown ports get the generic map: pads in note order to scenes, knobs in CC order to intensity,
  speed, chaos, glow and the stem gains, sliders to master levels). Maps are saved per device name on the server
  (`~/.xenoform/midi_map.json`) and mirrored in localStorage; Reset to default, Export and Import stay, as a link. Knobs
  are absolute with soft takeover (the value moves only once the hardware passes it).
- **The page knows the song**: sections, beats and drops come from the desk's analysis (`lane.beats` on its 24 fps clock,
  the sections, `drop_run`), so the strip, the now/next readout, "next drop in 8 beats" and switch-on-phrase are real,
  and the cut's own clips are the first source.

### 6.6 Render and export

```
+-[4 RENDER]------------------------------------------------------------------+
| Draft ready: 30 s around drop 1 . took 8:49 (the plan said 6:20)   [>] [dl]  |
+-[PLAYER]----------------------------------+-[NEXT, one button]---------------+
|          the Draft, playing               | [ Render the whole song > ]      |
|                                           |  Quality: (Draft, one cut ~20 min)|
|                                           |  (by passages) (Final) (Cloud)   |
+-[STRIP: rendered solid, sketched /, stale !]-----------------------------------+
| |intro|verse|build|vDROP 1 #############|release|vDROP 2 //////|outro ///     |
| morph 7 of 13 . about 2:10 left . 6 queued on this GPU            [Stop]      |
+-[EXPORT]--------------------------------------------------------------------+
| [MP4 1080p] [9:16] [15 s hook] [Edit in Resolve] [Copy recipe] [Perform it >] |
+-----------------------------------------------------------------------------+
```

Rendering fills the strip shot by shot (the ComfyUI queue knows "morph n of m", so the bar says that), an unplanned step
such as growing stills is a named phase with its own estimate, one clock in one place, the warning the server knows is
shown beside Took, and a single-shot re-render shows progress on its tile while the timeline stays usable. Draft, by
passages, Final and Cloud are **Quality** choices with one honest time each; aspect, model files, GPU tier and the end
card are under the hood. The Making screen as a separate page goes; the strip is the progress.

### 6.7 The first-time path

0. If the models are missing, the only button says "Get the 11.5 GB model" and the first Make cannot fail for that (M1).
1. Press a bundled song chip (or drop a file). The strip fills with sections, beats and drops; a default plan lays shots
   on the beats; the sketch plays around the first drop at no cost; the desk is on Plan.
2. Press a vibe card. The plan re-chains with its stills; the sketch follows.
3. Press "Tweak the feel". The House feel is already set, so there is nothing to change; the newcomer sees where the
   knobs and the controller live.
4. Press "Render Draft". The 30 s around the drop renders; the step bar says "about 6 minutes, you can leave this page";
   blocks turn solid as they land.
5. Press Play (or Download). A rendered clip in five clicks, none of them a guess; "Render Draft now" on Plan makes it
   four.

### 6.8 What each existing piece becomes

| Today | In Songline |
| --- | --- |
| The 3 200 px desk (`renderEasy`) | Five step renderers over one strip; `renderEasy` splits, the stage-slot nav becomes the step bar |
| Song card + drop card + facts + Chain row | The strip and its header line |
| Vibe cards, idea line, Loved chains | The vibe rail on Source and Plan (chains as **Chains** on the rail, one click each as today) |
| Knobs, Stem reactions, chip rows | Tweak, with controller badges |
| Fine-tune (14 rows) and Work in progress | Under the hood with no shot selected; Perform; Setup |
| The shots lane and drawer (`shotsLane`, `timelineDrawer`, Shot / Look / Join / Regenerate) | The strip's SHOTS lane and the docked inspector; Regenerate's style and seed go to Under the hood, its Swap, Generate here and Dream here to the Shot tab |
| The MIDI table (`midi.js` panel) | Badges, the Map overlay and the Learn popover on the same `midi.js` |
| `/vj`'s 15-pill bar, help modal, HUD | The Perform control view; `vj.html`'s renderer, transitions and recorder become the output window (decision 11) |
| Queue Drafts, Variations | A Quality choice ("a few Drafts overnight") with Variations as its result view |
| Share row | The Export row on Render, with Edit in Resolve and the recipe code as they are |
| Setup & models, Settings, About | One Setup page in the desk shell (M2, M3, M4); the "…" menu keeps Setup, About, Copy diagnostics |
| Judges page | Retired, or the Source step with a `?judges=1` flag (decision 4) |
| Moves, Polly, the Live tier | Not on the main flow: Moves and Polly behind Setup as optional extras, the Live tier as the "GPU not answering" state of the sketch (decision 14) |
| The tutorial | Five steps that follow the bar: the song, a vibe, Render Draft, the shot inspector, Perform |

### 6.9 Risks and what to prove early

- A four-minute strip must read on a laptop: it needs zoom, a section overview and the Draft window. Prove it with the
  real `lane.build` data for Glitch Out before any other screen.
- People may take the sketch for the render: the SKETCH label, hatched blocks and the cost line are not optional.
- Raw prompt, cfg and steps can break the house look: Reset to preset is always one click away and the preset marks stay.
- Hold pads need low latency: Web MIDI in Chrome is fine; the SSE fallback is not, so the bridge packages must be in the
  install when the bridge is advertised.
- The Window Management API is Chromium-only; Firefox gets a window to drag.
- Rewriting `renderEasy` is the big refactor; `render()` must stop rebuilding the player on every click first (P1), or
  the strip inherits the same problem.
- At 430 px the strip becomes a section overview with the Draft window, and the step bar sticks to the bottom (C1);
  the full lanes are a laptop feature (decision 13).

## 7. What to build first, and how it maps onto T1 to T6

| Round | Size | Closes | Needs from Tys |
| --- | --- | --- | --- |
| **0. Fixes that stand whatever the redesign** (each a small commit in `app.js` and `ui.py`, no layout change) | 1 to 2 days | N1, N2, N3, N4, N12, F1, F2, F3, F4, F5, F6, F7, F9, P1, W1, L3, L5, V6, V9 | decision 5; decision 8 for the `[midi]` install |
| **1. The strip** (T5): the song strip drawn from `lane.build` with sections, beats, drops and the Draft window; the step bar; Source, Plan and Tweak over it; shots as blocks; the inspector docked under the strip with today's four tabs; the side-page shell | about a week | C1, C2, C3, C4, C5, C6, C8, C9, C11, C13, C14, C15, W2, W4, W6, N5, N6, N9, N11, L9, P2, S1, S2, S4, S5, F10, F12 | decisions 1, 2, 4, 9, 10, 13 |
| **2. Under the hood** (T4): the morph request written beside each clip, `GET …/shots/{i}/recipe`, the panel as the inspector's fourth tab, Re-render with the widened body, Open in ComfyUI, Copy recipe, the takes list, and the project scope that retires Fine-tune and Work in progress | 3 to 4 days | L1, L2, L4, L6, L7, L8, F13, N14, N10, N13, C10, M4 | decisions 3, 7 |
| **3. MIDI on the same screen** (T1 and T1b): badges, Map, the Learn popover, hold pads with snap-back, soft takeover, device-name maps (Tys's controller first), server-side maps, Reset, Export, Import | 3 to 4 days | C7, V3, A5, and the T1 acceptance list | decision 6 |
| **4. Perform** (T2): the control view on the strip, `/vj?out=1` as the output window, the REC dot and timer outside the canvas, chunked recording to the library, mic audio in the take, the cut's clips as the first source, sections and drops from the desk | about a week | N7, V1, V2, V4, V5, V7, V8, V10, V11, S3, P3, and the T2 acceptance list | decisions 11, 12 |
| **5. Keyframes** (the rest of T5), then the OSC relay and the TD template (T3), then the node pack (T6) | a week, then as scoped | L10; T3 and T6 acceptance lists | T3 and T6 scope |
| **Setup and the machine**, alongside rounds 1 and 2 | 2 days | M1, M2, M3, M5, M6, N8, F8, F11, F14, A1 to A4, W3, W5 | decision 14 |

Round 0 also installs the `[midi]` extra, but that is a change to the shared `.venv` of `xenoform-rc2`, which Tys's desks
47330 and 47331 run on (they keep SSE until they are restarted), so it is a separate ask (decision 8), not a commit.

## 8. Decisions for Tys

1. **The canvas.** The song strip as the one surface on every step (section 6), or keep today's long desk and bolt the
   panel, the map and the perform window onto it? This page recommends the strip.
2. **The first screen.** Source as an empty, ghosted strip with one action, with the demo named rather than silently
   loaded, moving to Plan by itself once a song is in. Agreed?
3. **Under the hood's scope.** One shot at first (recommended), with section and whole-song scope later when `/rerender`
   takes the new fields.
4. **What goes.** The judges page, the Variations page as a separate page, the Fine-tune and Work in progress drawers,
   the MIDI table, the drop prose card, the Making screen as its own page, the 15-pill bar on `/vj`. Anything on that
   list to keep?
5. **Round 0 now?** The fixes in section 7 can land on this branch before the strip work starts; they touch no layout.
   Yes or wait?
6. **Your controller.** For the first shipped map I need its port name and your current mapping: open the desk's MIDI
   panel once with it plugged in, or run `xenoform midi list` once the `[midi]` extra is installed. Nothing MIDI in this
   review was tried with hardware; the first MIDI session should be one with you and the controller.
7. **Open in ComfyUI.** Queue the shot's graph on your shared ComfyUI at :8188 (it spends GPU there), or only download
   the `.json`? This page recommends download by default, queue as an option.
8. **The `[midi]` extra** (`mido`, `python-rtmidi`, `websockets`) installed into the shared `xenoform-rc2` venv: it fixes
   the `/ws/midi` 404 on every page load and enables the bridge, and your desks pick it up when they are next restarted.
   Install it, or leave the venv alone until the MIDI round?
9. **Feel presets.** House, Dreamy, Hard glitch, Warm haze, Clean (each a knob set plus a Look and a Morph style) as the
   first row of Tweak: these names, or yours?
10. **The sketch.** A no-GPU preview that cuts the vibe's stills (and later the library loops) on the song's beats before
    any render, labelled SKETCH, hatched on the strip. Worth building first, or render-only until the strip exists?
11. **`/vj`.** Fold it into Perform (recommended; `/vj?out=1` stays as the output window's URL), or keep `/vj` as a
    standalone page too?
12. **Recordings.** Save takes to the library as webm, remuxed to mp4 by ffmpeg beside the cut (`work/ui/takes/`), in
    the output window's size. Agreed?
13. **Mobile.** A phone layout is not a target beyond a sticky step bar and a section overview (C1). Agreed?
14. **Moves, Polly and the Live tier.** Out of the main flow: Moves and Polly as optional extras behind Setup, the Live
    tier as the state the sketch shows when ComfyUI is down. Keep, hide, or retire any of them?
