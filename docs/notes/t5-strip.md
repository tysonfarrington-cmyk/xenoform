# T5 round 1: the song strip (branch t5-strip)

Round 1 of the Songline redesign in [docs/UI_REVIEW.md](../UI_REVIEW.md) §6: the song strip as the desk's one canvas,
the five steps over it, the inspector docked under it, Render as progress, the phone layout and the tutorial. Branch
`t5-strip`, cut from `ui-review-4nov` (574c1fc), worktree `C:\Projects\xf-t5-strip`, desk on 127.0.0.1:47354. Local
commits only, nothing pushed or merged. Before and after pictures: [docs/ui_review/shots](../ui_review/shots/) and
[docs/ui_review/after](../ui_review/after/README.md).

## What landed, commit by commit

| Commit | What |
|---|---|
| 0849bd8 The song strip (6.1) | `strip.js` (`window.XenoStrip`: mount, setPlayhead, snapTime, view, reveal) and `strip.css`: lanes Sections (by role, drop runs flagged, the main one hottest), Wave, Beats (bars heavier), Shots (hatched = sketched, solid = rendered with the cut's frame, ! = stale), Intensity, Objects; an overview of the whole song; the Draft window dragged by whole beats (Shift a bar, Alt free, arrow keys too); a playhead; wheel zoom round the pointer; the view kept per strip across redraws. Server, additive: `GET /api/simple/strip` (passages, drop runs, beats, bars, waveform, window), the chain preview's `times`, `sections`, `intensity`, `assign`, `window_start`, and `lane.build`'s `window` and per-shot `intensity`. |
| c68a249 The step bar (6.1, 6.6, 6.7) | Source › Plan › Tweak › Render › Perform in the toolbar, a step a button once it can do something; the step in the URL (`#source #plan #tweak #render/<job> #perform/<job>`), a new step a history entry so Back walks the steps; the old `#simple…` hashes land where they meant; a reload or link on `#render/<job>` reopens that cut with its song (N5, N9). One violet button per step in the step bar at the bottom; Ctrl+Enter presses it. |
| 6ad886a Source (6.2, 6.7) | The strip ghosted until a song is in, the bundled songs with the demo by name, one action ("Choose a song", or "Get the 11.5 GB model" while the Draft model is missing), a file dropped anywhere loads, the desk moves to Plan by itself; My videos is this step's list (C2, C3). |
| dfb6960 Plan (6.2, decision 10) | The sketch monitor (the vibe's stills on the planned shots, crossfading on the beats with the song, labelled Sketch · no GPU, Space plays it), the vibe rail, the strip with the plan's shots inside the Draft window and the objects pinned where they land, the object a clicked shot lands on docked under the strip with the library to pick another; one estimate from one source (F10); "103 sections", the drop prose card, the Chain and Length rows and Queue Drafts left the first screen (W4). |
| d605b88 Tweak (6.3, decision 9) | The Feel row (House, Dreamy, Hard glitch, Warm haze, Clean, Custom), the four knobs, then pick-one rows as one segmented control and pick-many as chips (C9: Morph style, Timing, Breathe and Drops split from Shape, Effects with a None, Look, Foreshadow, Wide scenes, Backdrop), a cost tag on every row (re-cut, no GPU; or GPU for the next render), one hint line for the choice under the pointer or keyboard instead of nineteen paragraphs (C4, C15); the Project panel (`#hood-project`) with the plumbing rows that were Fine-tune and Work in progress (C5, C6). `data-midi-slot` on knobs, stem lanes and rows. |
| ca19070 The inspector (6.4, L9) | The shot or seam clicked on the strip opens today's drawer right under it on every step with a cut; a fourth tab, Under the hood, with its host `<div id="hood-shot" data-inspector-tab="hood" hidden>` and `window.XenoHood.mount(host, {jobId, shotIndex})`; the head in song time, bar and beat ("2:22 in the song, bar 54 beat 1 · 0:14 in the cut · 1.333 s, 2 beats"). |
| 62617c7 Render as progress (6.6) | The Making page is gone: a Make shows on Render as the monitor ("Morph 6 of 13 on the GPU", W4), what is happening, and the strip whose planned shots fill as the morphs land; the clock, bar and Stop in the step bar; an edit runs where it was started with the cut's player and strip on screen (`easyVideoId()` keeps naming the cut, L7); the whole song's queue repaints its counts in place (P2). poll(), tickEasy, postCutEdit and render() are called as before. |
| 3ad63be Phone (6.8, C1, decision 13) | One column with the strip right under the monitor; the strip is the section overview with its line ("This Draft · 2:08 to 2:38 · 13 shots · the main drop at 2:22"); the step bar edge to edge at the bottom with its button full width. |
| 7e599be Knob lines, four pins | The hint line speaks for each knob (the old knob paragraph, one knob at a time); four tests the Source and Tweak commits had left pinned to the old layout re-pointed (they failed from those commits until this one; the Tweak commit's full suite caught them). |
| e137066 The tutorial (6.9, N11) | Five steps along the step bar: the song, a vibe, Render Draft (simulated, with the Open weights badge), a shot on the strip, Perform; each names the desk step that holds its target and the desk goes there, so a tour opened on a cut or a Make lights its target; with no song chosen the bundled demo stands in, by name. |
| 4efa7cb Screenshots | [docs/ui_review/after](../ui_review/after/README.md): 19 shots at 1440 and 375 with a manifest, and `docs/ui_review/tools/capture_after.js` to retake them. |
| ce85a7d Your clips (F12) | `POST /api/own` also returns the names it kept (additive); the Your clips row lists them in the order they play, and the step bar counts the clips ("2 clips in turn, 1 morph between them") with no minutes, since the plan's clock is the objects'. |
| 40aacaa The tour's offer (C2) | The first visit's offer names the five steps and its Start is a ghost, so Choose a song is the first screen's one violet button. |
| c046c38 A late pin | The full suite's one failure: `test_story_cut` counted two knob strips. |

## The findings

| ID | Status | Where it stands |
|---|---|---|
| C1 | closed | Phone: the step's button is in the step bar stuck to the bottom of the screen. |
| C2 | closed | One violet button per screen (the step bar's), the tour's offer included; Queue Drafts waits for a cut. |
| C3 | closed | Nothing is chosen until it is picked; the demo is a chip by name; Render Draft is disabled with no vibe. |
| C4 | closed | Tweak has one hint line; the paragraphs are gone. |
| C5 | closed | The plumbing is the Project panel (a closed details on Tweak). |
| C6 | partly | Perform is the fifth step and the MIDI controller row sits under the knobs; the perform page itself is T2's. |
| C8 | closed | "Made from" (source) and "Morph style". |
| C9 | closed on Tweak | Segmented for pick-one, chips for pick-many. The inspector's tabs keep today's controls. |
| C11 | partly | The cut's side column is rebuilt (the sharp version, another vibe, Queue Drafts); the Stems-mode "What changes" row was not rechecked. |
| C13 | partly | Backdrop Scenes = Wide scenes Only is one control now; Look's Dither and Effects' Dither hits are still two (a look, a per-kick hit), each with its line. |
| C14 | partly | The library picker's empty note still says "grow some stills on the Library row first", a row of the Project panel on Tweak. |
| C15 | closed on Tweak | Every chip and knob has its line in the hint line (hover or focus); the inspector's Look chips still explain only in tooltips. |
| W2 | closed | Wide scenes (Off, Mix in, Only) and Backdrop (Plain, Places). |
| W4 | closed | No "103 sections"; the monitor says "Morph n of m". |
| W6 | partly | "Draft" throughout the steps; the cut's head still says "Your video", the Project panel's "Model tier" row still lists quality tiers, three things are still called cloud. |
| N5 | closed in effect | The cut stays on the desk: Render reaches it from any step, Setup's steps go back to that step; the logo and Back to the desk still land on Plan, not on the step you left. |
| N6 | partly | A cut's link or a reload on Render reopens it with its song; a song uploaded before a reload is still lost on the desk. |
| N9 | closed | The step bar works from Setup and Connect. |
| N11 | closed | Tour steps move the desk to their target. |
| L9 | closed | Beats and bars on the strip; the drawer speaks song time, bar and beat. |
| P2 | closed | The whole song's queue repaints in place (not run for hours: needs the GPU). |
| F10 | closed | One estimate, morphs + cut-and-finish, summing to its total, in the step bar. |
| F12 | closed | Names and order of the dropped clips; the step bar counts them. No thumbnails. |

## How it was verified

- Tests: `tests/test_song_strip.py` (new, 8 tests: the strip endpoint on Glitch Out and the demo, the chain's times,
  the lane window and Intensity, the component, the desk feed, the inspector docking, the phone layout),
  `tests/test_tutorial.py` (rewritten, 2), and the pins in about 30 test files moved in the commit that moved their
  code (five late: four in 7e599be, one in c046c38). Full suite on a snapshot of ce85a7d: 1,708 tests, 1,705 passed,
  2 skipped, 1 failed, with `test_midi.py::test_websocket_fan_out_and_http_ingest` deselected (it fails on every
  branch in the shared venv, see Round 0's note). The failure was a pin the Render commit had left
  (`test_story_cut.py` counted two knob strips; there is one now, on Tweak), fixed in c046c38. The offer commit
  40aacaa came after the run and was checked with the five test files that touch it.
- In a browser on the desk (1366 and 1440, then 375 and 430) on Glitch Out and the copied cut 31680167: the strip's
  15 passages, 5 drop runs and the main one at 2:22, the Draft window 2:08 to 2:38 with 13 planned shots; the cut's
  shots placed at 2:08; step routing, Back and a reload on `#render/31680167`; Source to Plan by itself; the sketch
  playing with the playhead following; the Plan dock; a Feel preset marking the 13 shots stale and "Apply 1 change ·
  re-cut"; the inspector's head; a real CPU re-cut from Tweak keeping the player and strip and landing back on Tweak;
  the five tour steps from a cut on Render, and from no song; two clips dropped on Your clips; no sideways scroll at
  375 and 430.
- Not verified: a real GPU Make (the progress view was checked with a simulated job in the desk's client state, and
  with the real CPU re-cut); the whole song's queue over hours; touch on a real phone (Chrome's emulated widths only);
  Firefox and Safari; MIDI badges with a controller attached (T1's midi.js is not on this branch); hood.js filling the
  hosts (T4's hood.js is not on this branch).

## What is left

- Editing on the lanes: Intensity and Objects are drawn from the per-shot values but not editable yet (keyframes are a
  later round); the strip has no audio scrub while dragging the window.
- The phone has no shot inspector: its strip is the overview, with no shots to tap. On a phone the first visit's tour
  offer covers the step bar until it is answered (as before this branch).
- The leftovers in the table above (C6, C11, C13, C14, C15 in the inspector, W6, N5's logo, N6's uploaded song).
- `/api/opener` (the drop card's opener) is no longer called by the desk, since the strip carries the drop; the route
  stays for scripts, a cleanup for later.
- F3 (two ETAs) and F6 (the edit clock) are Round 0's.

## For the merge

- **Round 0 (r0-fixes).** The URL: this branch writes `#source #plan #tweak #render/<job> #perform/<job>`;
  `easyPhaseFromHash()` reads the step and puts a job id in `state.easy.routeJob`, and `reopenRoute()` reopens it at
  boot and on hashchange. Round 0 parses the URL in one place, `urlTarget()`, which already accepts `#render/<job>`
  (it still writes `#simple/making/<job>` and `#simple/result/<cut>` so it stands alone). At the merge `reopenRoute()`
  hands `state.easy.routeJob` to Round 0: `resumeMaking(id, keptMaking(), false)` for a job (running: its progress
  with its own clock and poll; done: `reopenCut(id)`; gone: the cut if saved, else a plain note), or
  `reopenCut(id, {fromUrl: true})` for a cut; this branch's step routing keeps the rest (Round 0's r0-fixes notes
  have the details). Both branches define `reopenCut`: here
  `reopenCut(row)` (a My videos row with its bundled song), there `reopenCut(id, {fromUrl, note, missing})`; keep
  Round 0's and have `reopenRoute()` and the Source list call it. `setEasyPhase()` is step-aware here (`makeStep`,
  `syncStepHash()`) and keeps/drops `xeno-making` there: merge both bodies. `renderMaking()` is rewritten here as
  Render's progress view; Round 0's Making-screen edits belong in the step bar's making branch (ids `easy-eta` and
  `easy-progress` are kept). `easyVideoId()` here returns the running edit's job while `state.easy.recutting`.
- **T4 (Under the hood).** Hosts as agreed: `#hood-shot` (`data-inspector-tab="hood"`, `data-job`, `data-index`) in
  the drawer and `#hood-project` in Tweak's "Project · under the hood" details. `mountStrips()` here calls
  `XenoHood.mount` for both; T4's `mountHood()` at the end of render() does the same, so keep T4's (it passes the
  `project` rows provider) and drop the two calls here. T4 removes the Regenerate tab; `TL_TABS` here still has it.
- **T1 (MIDI).** `data-midi-slot="macro:<k>"` on the knobs, `"<lane key>"` on the stem lanes, and on each Tweak row
  (`feel`, `breathe`, `drops`, `scenes`, `backdrop`, `effects`, or the row's data-act where no short name is given).
- **T2 (Perform).** `/api/simple/strip` has the shape T2 reads first (passages, beats, bars, bar_phase, drop, wave);
  the Perform step's button opens `/vj?job=<id>`.
- Suggested order: Round 0, then this branch, then T4, T1, T2.

## What needs Tys

- Decision 9: the Feel presets are mine to start with. House = today's defaults (0.5, 0.5, 0.3, 0.4, Look and Morph
  style auto); Dreamy 0.35, 0.25, 0.1, 0.75 with Cool echo and Melt; Hard glitch 0.85, 0.7, 0.8, 0.3 with Cyan flash
  and Shatter; Warm haze 0.45, 0.4, 0.2, 0.7 with Warm leak and Bloom; Clean 0.4, 0.5, 0.05, 0.2 with no Look and
  Melt (Intensity, Speed, Chaos, Glow). Names and values are yours to change.
- Decision 10: Plan's sketch is the vibe's stills crossfading on the planned beats in the browser, never the GPU. Keep?
- Decision 13: on a phone the strip is an overview only, with no shot editing there. Keep?
- The tour borrows the bundled demo, by name, when Next is pressed on the song step with no song. Fine against C3?
- A 30 s Draft on a free GPU would confirm the strip's blocks follow "Morph n of m" live; this branch never ran one.
