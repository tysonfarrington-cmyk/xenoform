# The 21 Nov review of integrate-4nov (21 Nov 2026)

A code review of `integrate-4nov` against `origin/main` (94 commits, 321 files, about 34,800 lines added), the small
leftovers of `integrate-4nov.md` and `ci-fixes-17nov.md`, and the bugs the review found. Everything is committed
locally on `integrate-4nov`, on top of 24f8036. Nothing is pushed, merged or rebased, and no PR is open.

## What was reviewed

Four reviewers read the diff in parallel, each with the two notes first, and reported only what they could trace
through the code (some findings were also run as a snippet). I checked each finding against the code before fixing it.

| slice | read | not read |
| --- | --- | --- |
| The desk client | all of `hood.js` and `strip.js`; the `tutorial.js`, `ui_v6.js`, `index.html` diffs; in `app.js` the routing, reopen, poll and edits, step bar, strip model, Source, Plan and Tweak, `easyMake`, the Make gate and boot | the three CSS diffs beyond grep, the stems and whole-song code, the Setup page, most of the click dispatcher |
| The server | the diffs of `ui.py`, `dense.py`, `cloud_morph.py`, `job_timing.py`, `stems_api.py`, `models_setup.py`, `hardware.py`, `final_tier.py`, `moves.py`, `lane.py`, `simple_recipe.py`, `dream.py`, `cli.py`, `stems_mode.py`, all of `shot_recipe.py`, the root files and CI | `idea.py`, `presets.py`, `song_plan.py` (2 to 4 lines each); no GPU, no ComfyUI, no model download |
| The VJ cluster | `vj.html`, `vj_control.js`, `midi.js`, `midi_map.js`, `osc_out.js`, `perform_api.py`, `osc_relay.py`, `midi_maps.py`, `midi_bridge.py`, `td/xenoform_bridge.py`, their routes | the two CSS files, the two READMEs; nothing run in a browser or in TouchDesigner |
| The node pack and side pages | all of `comfy_pack/*.py`, both web scripts, `sync_bundle.py`, `build_demo_workflow.py`, the root `__init__.py`, requirements and pyproject, `moves.py`, `moves.html`; traced against the local ComfyUI checkout and its frontend 1.49.6 | `plan.py`'s planners line by line, `dry_import.py`, `editor_harness.py`, the workflow JSONs by eye, `variations.html` and `judges.html` beyond links |

Found sound, and worth knowing: every job, cut, take and audio id from a URL goes through `storage_id` or
`_video_dir` before a path is built; the edit lifecycle (`_edit_start`, `_edit_failed`, `_edit_stopped`) and cancel
hold for re-render, swap, insert, dream and take; `renders` stays in step with `clips` in every writer;
`clean_overrides` refuses bad types and ranges; the `vj.html` three-way merge has the right script order and no OSC
sender in `?out=1`; the websocket fan-out isolates a bad client; `td/xenoform_bridge.py` matches the relay's addresses;
the pack's import path, node signatures and demo workflow agree with ComfyUI's loader.

## The leftovers the notes listed

| commit | what |
| --- | --- |
| b036f33 | The dead lookups from t5 are gone from `app.js`: `openMidiDrawer` with its `#fine-tune` lookup (and its `easy-midi` act, which no button carried), the `easy-length` handler, `morphStyleRow`, `#lane-playhead` and `#lane-track` in `paintPlayhead`, and the old playhead's two CSS rules. `test_ui_v7`, `test_desk_steady` and `test_r0_fixes` pin their absence. |
| 6729257 | The re-render's `--p` fill and the overview's done bar. The fill is the strip model's now (`fill` on the shot, written into the block's style by `strip.js`), so a `render()` between two polls draws it where the edit is. The shot that renders again carries `made`, so the done bar keeps it. `test_song_strip` draws both in node. |
| ef0020c | `docs/TIMELINE.md` section 5 rewritten to the desk as it is: the cut's shots are the song strip's blocks, the four-tab drawer, Apply and Reset with Undo, which GPU edits take the making screen and which keep the cut's screen. The routes paragraph follows, and the "not on the timeline" line no longer denies Order and Move it. |
| 85d2d54 | The comments, tooltips and strings that named Fine-tune, the Work in progress drawer, the Chain row or "Morph > Your clips" name what is on the desk: "Made from > Your clips on Plan" (two user-visible notes), the Stems row's "The plan's pins" chip and tooltip, `docs/STEMS_MODE.md`. `_apply_own`'s docstring now says what the code does (clips and objects never share a cut; the desk no longer sends `cut_in_clips`). |

Left as they are, on purpose:

- Polly's "off (Work in progress)" string (`test_docs` pins it), and README's "Work in progress" paragraph, which
  still names a real grouping (the last rows of the Project panel).
- "Chain row" in `app.js` comments: `test_stems_desk` splits on one of them, and `test_chain` says the Chain row is
  the strip's Objects lane.
- hood.js's project-scope renderer with `.hood-project`, `/api/opener` and `applyTimeline()`: unused, but each hangs
  on a decision that is still Tys's (below).
- The dead `.fine-tune`, `.wip-item` and `.wip-drawer` selectors in `app.css` (1397 to 1404) and `desk.css` (310, 516
  to 533, 538 to 544, 733), with their comments. No markup emits those classes. `test_desk_design` pins one of the
  selector lists, so removing them is a small job of its own; nothing depends on them.

## The bugs found and fixed

Each has a test. The desk, VJ and server ones are in `tests/test_review_21nov.py`; the pack's are in
`tests/test_comfy_pack_nodes.py` and `tests/test_install.py`.

**7a16354, the desk (`app.js`, `hood.js`).** All of these are about an edit kept on the cut's screen (Under the hood's
re-render and takes), which t4 added and the merge joined to Round 0's poll and reopen:

- A hash change during the edit (a step click, Back, Setup and back) turned the phase to "making". `poll()` then
  skipped its in-place branch, and the block and the panel stayed "rendering" with Re-render disabled on every shot
  until a reload. `easyPhaseFromHash` no longer counts an in-place edit as a running Make, and `editEnded` clears it.
- A Make pressed during the edit (Render, or Ctrl+Enter from the hood prompt) cancelled the edit and left the cut's id
  in `ignoreJob` for good, so every later Apply, swap or re-render of that cut hung. `easyMake` now refuses with a
  line naming the shot; `ignoreJob` is cleared when the cut is reopened or an edit of it starts.
- Another cut opened during the edit took the edit's job: its notes, its Share cut and its "ready" line were the
  first cut's. `poll()` drops the in-place edit quietly once the desk is on another cut.
- A reload on `#render/<cut>` after a stopped or failed edit landed on Plan with "The render was stopped." though the
  cut was whole. `resumeMaking` reads the job's own `edit` field.
- Edits waiting for Apply were lost on reload for a cut whose bundled or demo song had to load: the new session
  started with no lane, the lane was read twice, and the second read dropped what the first had given back. The lane
  and a read on its way are carried over the adoption by the three callers, as the upload branch already carried
  the lane. (00d773b moved this out of a helper and made two test harnesses and a pin follow the fixes.)
- Under the hood redrew the panels of the cut's other shots at every 400 ms tick, so a prompt typed there lost its
  caret and an open select closed. They are drawn when the edit starts, ends, moves or is stopped.
- Smaller: a still's name is escaped in the hood panel; a style's preset answer that lands after a later pick is
  dropped; two notes that pointed at "the box under Model" and "the first screen" name the Project panel and Source.

**aba8d88, the VJ page.**

- The Switch rate knob (K2 in both default maps) did nothing under soft takeover: the screen holds one of five steps,
  the knob sends a continuous value, and takeover dropped the knob after 3% of travel. `readTarget("every")` answers
  null again, as t1's did (t2's merge had given it a value).
- A held look or a held Blackout with no pad down landed the transition in flight and re-seeked the programme clip,
  on press and on release. The pads' hold listener ignores holds that are not a pad's.
- "Saving the take…" was never shown: the recorder stays "on" until the mp4 is in, and "on" was asked first.
- The merge dropped t1's `XenoMidi.dock()` at load and the MIDI button's state attributes. A dock left open came back
  closed and swallowed the first press; a connected controller showed no badges or dot until that press. Restored.
  Not checked in a browser.
- An imported map file's `source.type` went into markup unescaped. Escaped.
- One finite value past float32 in a posted OSC frame made python-osc raise at every later update, with the value
  kept to be sent again: no OSC until the desk restarted, and `errors` stayed 0. `_num` clamps to float32 and
  `_maybe_emit` counts an `OverflowError`.

**197eea2, the server.**

- A morph length set in frames Under the hood (33 frames is 1.333 s) was cut to the whole second below by the next
  swap, re-render or insert that touched the shot (`int()` on `render_s`): 33 frames became 25, 65 became 49, while
  the shot's `render_s` and `speed` kept the old value. `dense._source_seconds` keeps it in all three places.
- A NaN or infinite seed in a pasted recipe code raised from `int()`: a 500 on `/api/recipe/decode`, and a Make that
  lost its `meta.json`. It is dropped like any other damaged value.
- `GET shots/-1/workflow.json` answered with the last shot's graph, and `POST shots/-1/comfy` queued it. No workflow.

**4fbd2b7, the whole-song queue (`batch.py`, on main before this branch).** Found by the suite, not by the review:
`test_song_run`'s "a failed window goes again at the back" failed in the full run here, and at 24f8036 too (twice of
three runs of its file; it passes alone). A failed window is queued again with `time.time()`; when that is the same
clock tick as the windows still waiting (Windows ticks every 15 ms), the tie went to the failed window and it ran
again first. `_again` puts it after the batch's latest `queued_at`. A test with a clock that never moves pins it.

**8ebb4a9, the node pack.** ComfyUI has never loaded the pack, so these are the ones that would have shown first:

- With the root `requirements.txt` empty, ComfyUI's Python has no fastapi, but the desk's two nodes and `/xenoform`
  registered anyway (their imports are lazy). Every ComfyUI page load's `fetch("/xenoform")` would have been a 500,
  and both nodes failed when queued. The root `__init__.py` asks for fastapi before registering the desk block.
- `/xenoform_nodes/song` resolved and opened any path before checking it was under a song root, so a UNC path made
  ComfyUI reach for a network share. The path is checked as text first. A thumbnail width that is not a number is
  the default, not a 500.
- Assemble's `filename_prefix` could write outside the output folder (`../../x/cut`). Refused, as ComfyUI's own save
  nodes refuse it.
- An ffmpeg that left early surfaced as "Broken pipe" instead of ffmpeg's own message.
- **1361bdb.** Assemble read ffmpeg's stderr from a pipe only after writing every frame. An ffmpeg with more to say
  than the pipe holds stopped on it, the frames then filled its stdin, and both sides waited for good: a queued
  workflow that never ends. The test for the line above met this in the first full-suite run here (the suite stood
  still for 46 minutes and was stopped). ffmpeg's words go to a temporary file now; the test makes the stand-in
  say more than a pipe holds and passes three runs in a row.
- The Morph Timeline editor adopted edits made for another song (the node ignored them, the editor drew them, and
  the first change stamped them with the new song's key).
- `sync_bundle.py --check` compared bytes, so a fresh Windows clone with `core.autocrlf` (the repo has no
  `.gitattributes`) reads the bundle as stale and `test_the_pack_data_is_the_repositorys` fails there. It compares
  the JSON copies with newlines normalised.

## Bigger, left for Tys

Found, confirmed by trace, and not fixed because each is a behaviour or scope decision (1 and 2 are fixed since: see
"The two Stems Stop bugs, fixed" below):

1. **Stop during a Stems re-cut says "the cut is as it was" after the cut changed** (`ui.py` 813 to 817,
   `stems_composite.py` 234 to 238, `stems_mode.py` 795 to 797). The re-cut's progress callback raises on any report
   once Stop is set, and one report comes after `publish_file` has replaced `xenoform.mp4`. The job ends cancelled
   with no `video_version` bump, the file on disk is the new composite and the top record is not written. On a knob
   re-cut, layer 1 can be published before Stop lands on layer 2. Either Stop is honoured only before the first
   publish, or a late Stop lands with the "Stop came too late" line. This is the most serious open item.
2. **Stop on a Stems "lay together again" cannot stop** (`stems_mode.py` 1024 to 1029): it registers no cancel event,
   the desk says "Stopping the edit", and the composite lands without saying Stop was too late.
3. **Assemble takes 16 morphs, a whole song plans 19 to 23** (`comfy_pack/nodes.py` 30, `morph_timeline.js` 19). On
   every bundled long song the cut ends at shot 16 with `fill="stop"`. Raise `MAX_MORPHS` to 24 in both files, or say
   so in the pack's "Honest limits".
4. **A pinned "your image" in the node pack is silently dropped** (`comfy_pack/stills.py` 176 to 180): pins resolve
   through the catalogue only, and `/xenoform_nodes/still` has no thumbnail for a user image. Resolve pins against
   the user rows, or leave user rows out of the picker.
5. **Requests another page can make the desk send.** `GET /api/setup?comfy=<any http url>` makes the desk fetch nine
   paths from that host, with an unbounded cache (`ui.py` 3770 to 3778). `POST /api/osc/frame` accepts a body with no
   JSON content type and `/ws/osc` checks no Origin, so a page in the same browser can post OSC frames. Both are low
   impact on a desk bound to 127.0.0.1; the fix (loopback or configured host only; require `application/json`) is a
   policy call.
6. **The VJ nits**, each confirmed by trace: Speed is applied only to scenes that exist when the knob moves, so an
   output window opened later plays at 1× (`vj.html` 407); the MIDI hub never forgets a bridge port, so a controller
   reads as connected after `xenoform midi serve` exits (`stems_api.py` 861); Cancel or Esc on a Learn popover saves,
   which turns an untouched preset into "your map" (`midi_map.js` 167); `_push` sends the active device's profile for
   every device it uploads (`midi.js` 250); a failed first chunk writes the take's header twice into the local copy
   (`vj.html` 355).
7. **The desk nits**: `loadCutSong` has no guard against an older answer landing after another cut was opened (timing
   dependent, plausible); each Open click on a rendering row in My videos starts another poll loop.
8. **The decisions `integrate-4nov.md` already lists** still hold up the last dead code: Tweak's Project panel keeping
   t5's editable rows (then hood.js's project-scope renderer and `.hood-project` can go), and whether `/api/opener`
   and `applyTimeline()` get a caller or are removed.

## The two Stems Stop bugs, fixed

Tys asked for items 1 and 2 above to be fixed (21 Nov, after the review). Both are, in two commits on top of b81cd4e.
Nothing is pushed, merged or rebased, and no PR is open. The rule both follow: Stop either ends the edit with every
file and record of the cut as it was, or it is told it came too late. There is no state between the two.

**5531c66, Stop during a Stems re-cut.** Nothing of the cut is replaced until all of it is made.

- `stems_mode.recut` composes each layer's re-cut beside its cut (`layers/<stem>/xenoform.recut.mp4`), lays the
  composite from those files beside the cut (`composite/composite.mp4`), and only then puts the layers' cuts and
  records, the composite and the cut's record in place, in one step that reports nothing and looks at nothing.
- A Stop before that step ends the work at once, in a layer's re-cut or while ffmpeg lays the layers (ffmpeg is
  ended; it used to run to its end), and removes what was made beside the cut. The job ends `cancelled`, no new video
  version: "Stopped: the re-cut did not land, and the cut is as it was." That is now true of the cut's file, its
  record, and every layer's file and record.
- A Stop during the step lands: `done`, the new version, "Re-cut ready. Stop came too late to undo it, so the edit
  landed."
- Under it: `stems_composite.build` is `compose` (made beside the cut, Stop looked at) and then the file replaced,
  with its last report said before the replace and none after; `dense.recut_from_cache` replaces a cut's file and
  record together, last (`land_recut`). A plain cut's re-cut built its record after the file was already replaced;
  it does not any more.

**3c3970a, Stop on "Lay them again".** The route makes its own cancel event, as every other edit does, and hands it
to the composite. Stop while ffmpeg lays the layers ends ffmpeg: `cancelled`, no new version, "Stopped: the layers
were not laid again, and the cut is as it was." A Stop once the file is replaced lands with "Laid together again.
Stop came too late to undo it, so the edit landed." `docs/STEMS_MODE.md` says both.

**Tests**, `tests/test_stems_stop.py`, 12 of them. Stop is tried at every report of a knob re-cut and of a
re-composite in turn, and each must leave every file and record byte for byte; Stop arrives while a stand-in ffmpeg
that would run a minute lays the layers, and the stand-in must be ended; both desk routes end `cancelled` with the
cut whole; a Stop after the cut landed is told it was too late; a stale event from an earlier edit is left alone.
On the code before the fixes 11 of the 12 fail. Five of those fail on an argument that did not exist yet, and two
because the old code cannot run the stand-in ffmpeg, so those seven show only that the tests need the new code. The
four that show the bugs themselves: "Stop at report 2 (Other layer (2 of 2) ...) changed the cut", "Stop at report 2
(The layers are laid together) changed the cut", a report that found the cut's file already replaced, and Lay them
again holding no cancel event of its own. The one that passes is the late Stop on a re-cut, which was already told so.

**The suite**, run as the Tests section below says (a `git archive` snapshot, here of 3c3970a, `XENO_OFFLINE=1`,
`pytest -o addopts= -q -rfE`, Windows, Python 3.12.13): **1988 passed, 2 skipped, 0 failed** in 12:27, exit 0. That
is the 1976 of the review and these 12. `test_install.py` and `test_eligibility.py` after it: 17 passed, exit 0. One
run; no earlier run failed. No script changed, so `node --check` was not run again.

Not covered, and worth knowing:

- The step that puts a re-cut in place is several renames and small writes. A failure inside it (a full disk, a file
  that will not be replaced) can still leave a Stems cut part old and part new, and the desk adds "The cut is as it
  was" to every failed edit. The same holds for a swap or re-render on a layer whose composite then fails. That is the
  error path, not Stop, and it was so before.
- Nothing was run on a desk with a real re-cut in a browser: the routes were driven by the test client, the layers'
  cuts were the suite's fakes, and the composite was the real ffmpeg.

Not fixed and not a decision, only untested here: the in-place edit fixes were proved by reading and by node on the
functions that run alone, not on a desk with a GPU re-render running. A walk worth doing: start Re-render this shot,
click Tweak and press Back, press Render, reopen another cut from My videos, then reload.

## Tests

Run here on Windows with ffmpeg 8.1.1, on a `git archive` snapshot of 00d773b (the last code commit), as CI runs
it: `XENO_OFFLINE=1`, `pytest -o addopts= -q -rfE`, the two files CI runs as their own steps run after the rest.

- **The suite: 1976 passed, 2 skipped, 0 failed** in 12:03, exit 0 (`--ignore` on `test_install.py` and
  `test_eligibility.py`). It was 1960 passed at the 17 Nov run; the 16 more are this review's tests.
- **`test_install.py` and `test_eligibility.py`: 17 passed**, exit 0.
- `node --check` passes on every script in `ui_static`, `comfy_pack/web` and `tests/js`.

Two earlier runs did not pass, and both led to a fix above:

- The first stood still at `test_comfy_pack_nodes.py` for 46 minutes and was stopped: the Assemble deadlock (1361bdb).
- The second ended 1970 passed, 5 failed. Four were mine: three node harnesses that lacked a global or a helper the
  desk fixes had added, and a pin on a note I had reworded (00d773b). The fifth was the queue's clock tie (4fbd2b7).

Only CI can show: everything `ci-fixes-17nov.md` lists still stands (the tones and picture tolerances on Ubuntu's
x264, the stems retry, the pinned runner and actions). This review changed none of it. The new tests use no encoder
output, except the Assemble one, which asserts only that a failing stand-in is reported.

## How the work was done

- Commits are by "Owly <owly@local>", the identity the branch's other commits carry, passed on the command line
  (this checkout has no git identity configured; no config was changed), each with a Co-Authored-By line.
- The full suite ran on a `git archive` snapshot of HEAD in a scratch folder, so nothing in the worktree could move
  under it.
- `.claude_review_prompt.txt` and `claude_review_21nov.log` in the worktree root are untracked and were left alone.
