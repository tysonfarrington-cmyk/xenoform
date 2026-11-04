# Round 0 fixes (branch r0-fixes, 4 Nov 2026)

Round 0 of [UI_REVIEW.md](../UI_REVIEW.md) section 7: the fixes that stand whatever the redesign, as small diffs that move
no control and touch no CSS. Six commits on `ui-review-4nov` (574c1fc), one a cluster, each with its tests; the
behaviour tests are in `tests/test_r0_fixes.py` (they run the desk's own functions, cut out of app.js, in node).

## What landed

| Commit | Closes | In short |
| --- | --- | --- |
| Navigation | N1 N3 N4 N12 | Escape on the making screen clicks its Stop (the "…" menu takes its own Escape first). The URL carries the job and the cut (`#simple/making/<job>`, `#simple/result/<cut>`) and localStorage keeps a running job: a reload asks the desk and comes back to the making screen with its own clock, or to the cut, or says the job is gone. A cut's URL reopens it as its My videos row does, also for cuts the gallery does not list, and gives back the edits waiting for Apply. Change keeps the song until another loads (Cancel keeps it). |
| Feedback | N2 F1 F2 F3 F4 F5 F6 F7 F9 | Edits end as what they were: error with the reason, cancelled when Stop reached them, done with a new version; the cut's screen says which, never "Your cut is ready" over the old cut. Every edit has its own clock, title and two steps. Stop cancels an edit at its next safe point (the GPU wait of re-render, Generate here and swap; between a dream's frames; anywhere in a re-cut) and the desk waits for the verdict. A grow is a timed phase with its own estimate; "morph n of m" bounds the morph phase; the job route serves a bar that moves through silent steps. One clock on the Making screen. `poll()` retries with backoff, then says it lost the desk and stops the clock. A refused Make says why. A finished Make keeps the desk's warning beside Took. GPU edits wait while timeline edits are pending Apply. |
| Player | P1 | `render()` keeps the cut's `<video id=player>` node when the new markup plays the same file: a shot click seeks without stopping or re-buffering. |
| Words | W1 | Length: 15 s · 30 s · 60 s · Whole song, one cut · Whole song, by passages; the notes, comments and docs/SONG.md follow. |
| Timeline | L3 L5 | A Morph style chip only picks the style ("Re-render this morph as Shatter" spends the GPU). Reset the timeline is an edit for Apply, with Undo the reset. |
| vj | V9 | A select picked with the pointer on `/vj` gives the keys back; a keyboard step keeps its focus. |

V6 (the mic and the recording's audio) is the perform-window session's; `vj.html`'s `record()` is untouched.

## How it was verified

My own desk on 47350 (`PYTHONPATH` on this worktree), cut 31680167 copied in, no GPU work (ComfyUI's queue idle
throughout; the GPU routes were blocked in the page whenever a click could have reached one).

- In the browser: the result URL reopened with its facts and a pending Hold survived a reload (N4); a reload during a
  re-cut came back with its own clock (N3); after stopping the desk mid re-cut the screen said "Lost contact with the
  desk" and stopped its clock (F4), and after the restart the reload landed on the cut with "The desk restarted before
  the edit finished" (N3); Escape on a re-cut's making screen went to "stopping" and the cut came back with "Stopped:
  the re-cut did not land" (N1, F7); a re-cut showed "Re-cutting.", its two steps, "0:03 elapsed", then "Re-cut ready.
  It took 1:26." (F6); a 429 stubbed for /api/generate showed its reason (F5); Re-render with a pending edit was refused
  with no request (N2); shots clicked while playing kept the same playing node (P1); Change, Cancel and a new pick
  (N12); the Length row at 1366 and 375 px (W1); a Morph chip and Reset with Undo sent nothing (L3, L5); `/vj` gave the
  keys back after a pointer pick (V9).
- By tests only (a live check needs a GPU Make or a GPU edit): F1's error status on every edit route, F2's grow phase and
  live bar, F3, F9, the GPU side of F7 (fakes that wait on the cancel; `_render_pairs` raising on the mock path), N2 on
  swap, Generate here and Dream here.
- Full suite at 5ab54e7 (run while three other sessions ran theirs): 1 726 tests, 1 723 passed. The three failures:
  `test_stems_own::test_the_song_step_has_the_stems_line_with_its_two_controls` was a pin of the song block N12 moved
  (fixed in the next commit, its file green); `test_stems_api::test_background_split_reports_a_failed_split_and_tries_
  again_next_time` passes on its own (a timing flake under that load); `test_midi::test_websocket_fan_out_and_http_
  ingest` asserts the MIDI bridge is unavailable, and the shared venv now has `mido`, `python-rtmidi` and `websockets`
  installed (decision 8), so it fails on any branch; nothing MIDI is touched here.

## What is left, and the edges

- F2: the grow's estimate is its own "(about N s)"; one that overruns sits at 95 % of its share while the clock shows the
  rest of the plan. The monitor caption "Shot 1 of 103" (W4) is the strip session's.
- F7: once an edit's GPU work is done its re-compose runs on, and the line says Stop came too late. The Stems re-lay
  (no GPU, seconds) has no cancel.
- N2 refuses while edits are pending instead of carrying them (carrying needs the edit routes to take the overrides).
- N4: a passage opened from its song reopens from its URL as a plain cut (no "Back to the whole song").
- `applyTimeline()` has no caller since L5 (Apply goes through the bar's re-cut); it stays, pinned by two tests.
- A fresh desk shows the tutorial offer, which takes the first Escape (as before).

## For the merge (nothing pushed or merged)

- T5 (the strip): the URL is parsed in one place, `urlTarget()`, which already accepts `#render/<job>`; the entry points
  are `resumeMaking(id, kept, quiet)` and `reopenCut(id, {fromUrl, note, missing})`. This branch still writes
  `#simple/making/<job>` and `#simple/result/<cut>`.
- T4 (Under the hood): `dense.rerender_morph`, `insert_generated` and `swap_still` take `cancel=`; `postCutEdit` takes a
  last `title` argument; the edit routes start through `_edit_start` in ui.py.
- T2 (perform): two lines before the `/vj` key handler; the handler and `record()` as they were.
- CHANGELOG.md is not touched, to keep the merge simple.

Nothing needs Tys before the merge.
