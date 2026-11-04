# The 4 Nov integration (branch integrate-4nov, 4 Nov 2026)

One local branch that holds the eight task branches of the 4 Nov UI review, so they can be tested together. Built in the
worktree `C:\Projects\xf-integrate` from `ui-review-4nov` (574c1fc). Each branch's own note is beside this one.

## What this branch is

- Eight branches, merged in this order, one `--no-ff` merge commit each (their commits are kept, nothing squashed):

| order | branch | head | merge |
| --- | --- | --- | --- |
| 1 | `r0-fixes` | 14c0002 | ef97e80 |
| 2 | `t5-strip` | b400dbe | 9e9706d |
| 3 | `t4-under-the-hood` | 6645c90 | 8033bbb |
| 4-6 | `vj-cluster` (t1-midi 97d4f9e, t2-perform 06e9042, t3-td-bridge f50da5c) | 286a6a1 | 55f4af5 |
| 7 | `setup-shell` | 1121761 | 77cb311 |
| 8 | `t6-node-pack` | 287832c | 5c4fa6a |

- `vj-cluster` is a local branch that took t2-perform first, then merged t1-midi (1582d4d) and t3-td-bridge (286a6a1)
  into it, since all three meet in `vj.html`. It went into integrate-4nov as one merge.
- Fix commits follow the merges they belong to (next sections). All commits are by Owly with a Co-Authored-By line.
- Nothing is pushed. `contest-rc2` and `main` are untouched, and so is the shared checkout `C:\Projects\xenoform-rc2`.
- Tys's rule (4 Nov): all Xenoform work stays local until he says the contest is officially closed. This branch is not
  merged anywhere until then.
- `CHANGELOG.md` is unchanged. t3's note asks for a 0.3.3 entry on Live OSC at merge; it waits for the real merge.

## The seams and how each was resolved

| seam | resolution | commit |
| --- | --- | --- |
| r0 + t5: URLs | t5's step hashes (`#source #plan #tweak #render/<job> #perform/<job>`). Round 0 no longer writes `#simple/making/<job>` or `#simple/result/<cut>`; the old hashes are still read. | 9e9706d |
| r0 + t5: reopen | t5's `reopenRoute()` hands a job to Round 0's `resumeMaking(id, keptMaking(), false)` and a cut to Round 0's `reopenCut(id, opts)`. | 9e9706d |
| r0 + t5: making screen | `setEasyPhase()` keeps both bodies. `renderMaking()` is t5's Render progress view; Round 0's title, one clock, two steps per edit, Stop and "lost the desk" live in the step bar's making branch. | 9e9706d |
| r0 + t5: N12 song change | Round 0's Change/Cancel is gone with t5's Source step. A bundled song that fails to load falls back only to a song the desk holds (`songHeld`), never to one still loading. The dead `easy-step` / `easy-song-keep` handlers went later. | b494bc3, aa9c38b, bc80a4f |
| r0 + t4: edit routes | `dense.rerender_morph` takes `cancel=`, `overrides=` and `timing=`; `insert_generated` and `swap_still` take `cancel=`. The rerender route's extra kwargs go through `_edit_start`. t4's new take route (`POST shots/{i}/take`) also starts through `_edit_start` with a cancel. | 8033bbb |
| r0 + t4: client | `poll()`: `shotEditTick` before the making branch. `postCutEdit(id, route, body, detail, at, stage, title, opts)`: Round 0's title 7th, t4's opts last. `reopenRow` ends in `reopenWhole(row)`. | 8033bbb |
| r0 + t4: Regenerate | Tab gone: `TL_TABS` = shot, look, join, hood. Round 0's L3 Morph chip code removed, its pins moved to hood.js's style select and Re-render this shot. Round 0's L5 Reset with Undo kept. | 8033bbb, 1d07e48 |
| t4 + t5: reopen song | t4's `loadCutSong(id, info)` (asks the server; demo, bundled or uploaded) replaces t5's. Decision: the cut's own song loads on reopen even when another song is on the desk. It keeps the step on Render and reads the song list first. | 8033bbb, 484b1af, 1d07e48 |
| t4 + t5: hosts | `#hood-shot` in the drawer, `#hood-project` in Tweak's "Project · under the hood". t4's `mountHood()` at the end of `render()` mounts both; t5's two mounts dropped. Decision: the project scope mounts with no provider, so t5's editable rows stay; t4's `hoodProject` is gone. | 8033bbb, 484b1af |
| t4 + t5: progress | The re-render's progress and span lighting draw on the strip's `.xs-shot` block, not the old lane tile. | 8033bbb |
| t4 + t5: tabs | Under the hood shows for every shot, including Polly's, your clips and generated runs (t4's filter). | 484b1af |
| t1 + t2 + t3 + r0: `vj.html` | t2's page whole. t1's `midi.js`, `midi_map.js`, `midi_map.css`, presets; t1's held looks ported onto `XenoMidi.holds`. t3's `osc_out.js` after `midi.js` and the `XenoOsc` block after `XenoMidi.init`, no sender in `?out=1`. Round 0's V9 select-blur lines put back. | 1582d4d, 286a6a1, 55f4af5 |
| t2 + desk | The cut screen has one ghost Download with t2's Perform it link beside it; the Perform step opens `/vj?job=`. | 55f4af5 |
| setup-shell: step bar | t5's step bar reads `/api/setup`'s gate and draws the Get-the-model button and its line itself; `paintMakeGate` renames only the other Make buttons. | 77cb311, db33100, 88eb2f6 |
| setup-shell: F14 / N3 | My videos Open on a rendering cut uses Round 0's `resumeMaking`; `followRunningCut` dropped. | 77cb311, db33100 |
| setup-shell: tour | t5's `tutorial.js` with setup-shell's A2 (arrow keys leave a focused slider, tab, menu or radio alone). | 77cb311 |
| setup-shell: `/api/videos` | Status and progress per row, through t2's `with_takes`. A Make only: a running edit lists its cut as done. | 77cb311, 7549be6 |
| t6 | Root `requirements.txt` lists nothing; pins in `requirements-desk.txt` (no earlier pin needed moving). `[midi]` and `[osc]` extras both kept. README takes both setup-shell's and t6's hunks. | 5c4fa6a |

## Fix commits after verification

Each merge was checked by verifier rounds that read the diff against both sides. What they found and what was done:

- **daa1553 (t5).** README, REPRODUCE and SONG.md pointed at the Fine-tune drawer and its Length row, both removed by t5.
  They now name the five steps, Tweak's rows, the Project panel and Render's Quality. `test_docs` keeps them there.
- **484b1af (t4, round 0).** Three blockers: `mountHood` replaced t5's editable Project rows with t4's read-only ones;
  a reopened cut jumped from Render to Plan once its song loaded. Also: the hood re-render skipped Round 0's wait for
  pending Apply edits (N2); a lost desk during an in-place edit left the block rendering; `reopenWhole` overwrote
  Round 0's stop/fail note with "Took". All fixed. TIMELINE.md and README follow.
- **1d07e48 (t4, round 1).** A reload on `#render/<id>` of a bundled song's cut never loaded its song (the song list
  was not read yet). Fixed, with a node test. Round 0's dead L3 chip code removed.
- **b8cb921 (t4, round 2).** A failed, stopped or lost in-place edit dropped the cut's id from the desk; it now leaves
  the job as the cut, status done, as Round 0's `editEnded` does. The running edit's panel has a Stop. Tweak's project
  rows end with t4's where-it-lives and what-it-costs words (M4, C10).
- **db33100, 2b6406c, 88eb2f6, bc80a4f (setup-shell).** About, Settings, Setup, the idea line and the Make notes named
  removed drawers; they point at Tweak's Project panel now. The gate line survived no step bar repaint; the bar draws it.
- **7549be6.** My videos showed a cut as rendering while an in-place edit ran on it, so Open sent the edit to the making
  path. A running edit now lists its cut as done.
- **27637f3.** A stored Knobs-fold flag hid the cut's whole side column with no way back; the fold goes whole. The
  `/licences` page and `docs/performer.md` point at Performer (Polly).
- **8a2d935.** A reopened cut of a trimmed upload laid every shot past the strip's end (the strip offset shots by the
  window start while the desk held only the 30 s stretch). `cutSongStart` fixes the strip, playhead, seek and head.
  `capture_shell.js` updated for the merged markup.

Declined or only half done:

- Resuming an in-place Under the hood edit after a reload: not done. It needs a new `keepMaking` path, beyond a merge
  fix. The lost-contact half is fixed.
- Escape does not stop an in-place edit. Decision: on the cut's screen Escape also leaves a field or closes the menu;
  the panel's Stop is the way.
- `hoodProject`'s Fine-tune hints: not reworded, because `hoodProject` was removed.

## Tests

- Full suite on the merged tree (about 8a2d935): **1971 passed, 2 skipped, 0 failed** in 12:48. A second full run after
  the last fix showed no failures (its summary line was cut off). No flaky reruns were needed in these runs.
- Per merge: t4 152 passed; vj-cluster 189; setup-shell 156 (157 results, 1 skipped); t6 127; the t5 rounds 66, 105
  and 201 (1 skipped). `test_midi::test_websocket_fan_out_and_http_ingest` passes now that t1 is in.
- Playwright (Chrome channel) against a desk from this worktree: `capture_after.js` (t5's five steps at 1440 and
  375 px), `capture_shell.js` (setup-shell; fixed in 8a2d935), `perform_check.js` (t2: takes saved as mp4 from the
  control view, the output window and the mic). The Make gate was checked on a mocked `/api/setup` only.
- Static checks: `node --check` on the changed scripts and the inline scripts of `vj.html`, `index.html`, `moves.html`,
  `variations.html`; no conflict markers in `src`, `tests` or `pyproject.toml`; scans for `data-act` handlers and
  element ids that no markup produces; `xenoform.ui` imports; every route imports.

## What the critic found and what is left

The final pass found the trimmed-upload strip bug and the stale `capture_shell.js` (8a2d935). Left, all small:

- A re-render's `--p` fill on the strip block falls back to its default on any `render()` until the next 400 ms poll.
- The strip's overview "done" bar shrinks by one shot while a shot re-renders (`mapHtml` counts done and stale only).
- hood.js's project-scope renderer and hood.css's `.hood-project` rules are unused (no host passes a provider).
- Dead lookups from t5: `#fine-tune` in `openMidiDrawer`, `#lane-playhead` / `#lane-track` in `paintPlayhead`, the
  `easy-length` handler, `morphStyleRow`. All guarded, none reachable.
- Some app.js comments and tooltips still say Fine-tune or Work in progress. Polly's "off (Work in progress)" string
  is kept on purpose (`test_docs` pins it).
- docs/TIMELINE.md section 5 and its table still name "Re-render this morph"; the 4 Nov paragraph is current.
- Not on a real desk: the strip's live progress during a GPU re-render, the take route's step bar, MIDI badges and Learn
  (midi.js loads midi_map.js at runtime), a held look on a pad, Perform it opening `/vj?job=<id>`.
- `/api/opener` and `applyTimeline()` have no desk caller (t5 and Round 0 notes).

## For Tys

- **MiniLab 3.** Follow t1's note, "For Tys: test with the MiniLab 3": pads hold scenes, soft takeover on the knobs,
  Learn, the map after a restart. Then save your layout with More → Save as the shipped preset and commit
  `configs/midi_presets/minilab3.json`.
- **Restart your desks on 47330 and 47331** when you want the `[midi]` and `[osc]` extras there (mido, python-rtmidi,
  websockets, python-osc). That is your call; nothing here restarted them.
- **Second screen.** t2's "Steps for Tys": Perform it, Open output window, allow window management, Fullscreen output
  (F), Rec. Real placement and fullscreen on screen 2 were never checked.
- **TouchDesigner.** Run t3's two lines inside TouchDesigner, fix what the Textport says, save and commit
  `td/xenoform_bridge.tox`.
- **Node pack.** Install through the Manager (Install via Git URL), restart ComfyUI, load
  `comfy_pack/workflows/xenoform_demo.json`, Queue, open the Morph Timeline. ComfyUI has never loaded the pack.
  `PublisherId` is still empty.
- **Final download.** The Final's Download is the fp8 set (40.0 GB) on every card. Should a 24 GB card still get the
  46 GB weights?
- **Under the hood, two calls.** Should "or queue it there" (the POST to ComfyUI) stay on the shared GPU, or the
  download only? Should the LoRA picker list only LoRAs made for LTX-Video 0.9.5?
- **Review decisions still open (t5).** Decision 9, the Feel presets' names and values. Decision 10, Plan's sketch as
  stills crossfading in the browser. Decision 13, the phone strip as an overview only. The tour borrowing the bundled
  demo when Next is pressed with no song.
- **Merge decisions to confirm.** A reopened cut always loads its own song, replacing the one on the desk. Tweak's
  Project panel keeps t5's editable rows with t4's where/cost words, not t4's read-only rows.
- A 30 s Draft on a free GPU would confirm the strip's blocks follow "Morph n of m" live and that a hood re-render
  lights its block.

## How to run it

The desk on 47380 from this worktree. The launch entry is `xenoform-integrate-47380` in
`C:\Projects\xenoform-rc2\.claude\launch.json`. By hand (no space before each `&&`: cmd's `set` keeps it):

```
cmd /c "cd /d C:\Projects\xf-integrate&& set XENO_ADDONS=0&& set XENO_MODELS=C:\Users\tyson\AI\ComfyUI\models&& set XENO_HOME=C:\Projects\xf-integrate\work\home&& set PYTHONPATH=C:\Projects\xf-integrate\src&& C:\Projects\xenoform-rc2\.venv\Scripts\python.exe -m xenoform ui --host 127.0.0.1 --port 47380"
```

- `PYTHONPATH` is needed on every run: the venv's editable install points at the rc2 checkout.
- The work folder is `work\ui` (gitignored); the finished 30 s Draft `31680167` is in `work\ui\jobs\`.
- Tests: `PYTHONPATH=C:\Projects\xf-integrate\src C:\Projects\xenoform-rc2\.venv\Scripts\python.exe -m pytest -q`.
- Playwright: `NODE_PATH=C:\Projects\xf-uiaudit\node_modules`, `channel: 'chrome'`, scripts in `docs/ui_review/tools/`.
