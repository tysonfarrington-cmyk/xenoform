# Under the hood (T4, branch t4-under-the-hood, 4 Nov 2026)

docs/UI_REVIEW.md 6.4 and its back end, cut from `ui-review-4nov` (574c1fc). Closes L1, L2, L4, L6, L7 (the tile progress
in the drawer), L8, F13, N14, N10, N13, C10 (on the rows touched) and M4 (the project scope). Nothing pushed or merged.

## What landed

| Commit | What |
| --- | --- |
| 4f7af53 | **The record.** The Draft, Final and Cloud loops (`cloud_morph._local_clips`, `final_tier.final_clips`, `cloud_final.cloud_clips`) fill a `requests` list when given one (`shot_recipe.request`: the graph as queued, before the stills go up, the stills, the cache key, the time it took, cached or not). `simple.json` keeps `renders`, one a shot beside `clips`, each graph once under `simple/requests/<key>.json`; a re-render, a swap and a generated run keep them in step. |
| 7a2163d | **The recipe.** `GET /api/jobs/{id}/shots/{i}/recipe`: the values used beside the preset (what `prompt_for`, the autotune and the tier give the shot today, built from the same `cloud_morph.draft_settings` the Draft loop sends) with `differs` a field, `verified` (the clip's own graph gives the recorded key), the re-render gate with its reason (L8), the cost. A cut from before reads the graph ComfyUI wrote into each clip (`source: "clip"`), else says "Not recorded" with the Seed file's data. `GET .../workflow.json` downloads the API graph. |
| bb477a8 | **The widened re-render.** `POST /api/jobs/{id}/rerender` takes prompt, negative, steps, cfg, frames, both guides' strengths, compression, a LoRA (a `LoraLoaderModelOnly` goes into the Draft graph only when one is given), the seed and the shot's timing, checked in plain words (`shot_recipe.clean_overrides`). Each try logs its full request and the take it replaced under `rerenders`; a changed value is a new request, so a new cache key. |
| 9db75a5 | **Takes.** `GET .../shots/{i}/takes` (the Make's, each re-render's, what a swap put there; whether each can come back; each take's own clip) and `POST .../shots/{i}/take` (no render, a re-cut: `dense.use_take`). |
| a3ca849 | **Reopen whole.** A finished Make keeps its guardrail notes in `notes.json`; `GET /api/videos/{id}/reopen` gives the job back with the notes, the took breakdown, the tier and its stretch of the song, and registers it; `POST .../song` loads the cut's own song again (Render works without choosing it). `fromSong` is cleared on Reopen, the showcase and Back to the song (N10); My videos' Re-render answers on its card after loading the cut's song (N13). |
| 47584d2 | **Copy recipe for a shot.** The recipe code carries `shots` (morph index to a shot's own values; old codes read as before); the recipe route gives the cut's code with this shot's values; a Draft Make of a pasted code renders those morphs with them. |
| 8f2ff3d | **Open in ComfyUI, the queue option** (`POST .../shots/{i}/comfy` with `confirm: true`): the stills uploaded, the graph queued on the desk's own ComfyUI. The download is the default (decision 7). |
| c525f2d | A landed request takes the still names ComfyUI gave its guides (it renames a taken name; found on the GPU test). |
| 560d8ec | **The module on the desk.** `ui_static/hood.js` + `hood.css` (`window.XenoHood.mount(host, {jobId, shotIndex \| null, layer, onRerender, onTake, onSelect, project})`, nothing assumed about where it sits); the drawer's fourth tab "Under the hood" replaces Regenerate; Swap, Generate here and Dream here move to the Shot tab, each naming and lighting the shots it replaces (L6) with a cost tag; a re-render keeps the cut's screen, its progress on the shot's tile (L7); with no shot open, "Under the hood" under the timeline holds the cut's own rows, each with where it lives and what it costs (M4, C10); guardrail notes read as sentences whose times open their shot (F13). |

## How it was verified

- Tests: `tests/test_shot_recipe.py` (20), `tests/test_reopen.py` (5), `tests/test_hood_desk.py` (8, two of them run
  hood.js and the span rule under node: the re-render body's round trip, and the desk's span rule equals
  `dense.insert_span` and `dream.span`). Pinned tests changed in the same commit where the Regenerate tab's strings moved
  (test_timeline, test_morph_style, test_stems_edits, test_dream, test_desk_design, test_guardrails_consumed). Full
  suite (1733 tests): four failed on the full run. Three were pins this branch moved (the Draft prompt's guard now in
  `draft_settings`, the lane's drawer expression, the desk's first click listener); they are fixed and green on a re-run.
  The fourth, `test_midi.py::test_websocket_fan_out_and_http_ingest`, fails the same way on `ui-review-4nov`: the `[midi]`
  extra is now installed in the shared venv, so the bridge reads as available.
- My desk on 47352 (started with Bash, opened with preview_start `url`: `preview_start {name}` reads the rc2 checkout's
  launch.json, which is off limits) with the copied cut 31680167. The recipe read every value from the clips' own
  graphs, and today's preset matched them field for field (all `differs` false, the prompt word for word). Reopen gave
  back "Took 8:49 · morphs 8:02 · cut 0:36 · check 0:03", the two taste notes and the song. Edits, the violet marks,
  Reset to preset, the project rows, F13's links and L6's lit span were checked in the page, at 1366 and 375 px.
- **The one GPU render** (queue idle first): shot 6 re-rendered from the panel with seed 4242 and a shorter prompt, one
  Draft morph, 60.7 s of GPU, then the re-cut. The recorded graph equals the graph in ComfyUI's history node for node
  (prompt bd5ebd5d), apart from one LoadImage name ComfyUI renamed on upload (fixed in c525f2d). The clip's own graph
  gives the recorded key (`verified: true`), and the cache sidecar says `verified: true`. The tile showed the progress,
  and the screen stayed. Then take #0 came back with no GPU (the queue stayed empty).

## What is left

- A Final, Fast Final or Cloud shot shows its values read-only with the reason (L8); no single Final shot re-render, and
  no preset compare for those tiers (their `differs` stay false). Section and song scope wait (decision 3).
- The project rows for Forms, Renders on, Your images and Library are read-only here (set on the first screen); the
  strip session's Project panel is where they move.
- The LoRA picker lists every file in the loras folder: their model is not written in the file name.
- A cut made before `notes.json` reopens with its taste lines only (its QA flags were never written to disk).
- A dream does not update `renders` (the recipe says the shot is dreamed over); a Stems layer's takes and the
  standalone mount (no host hooks, as the strip will mount it) were checked by tests and reading, not on a real desk.
- The download is API format (ComfyUI lays it out on load), not a UI workflow with positions.

## For the merge

- **Round 0** (`r0-fixes`): `postCutEdit` gains a 7th `title` there and a 7th `opts` here: keep both (`opts` last) and
  pass `{ inPlace: true, shot }` from `mountHood`. `poll()` gets my `shotEditTick` branch before the making screen's.
  R0's `reopenRow(row)` should end by calling `reopenWhole(row)`. The Regenerate tab is gone here: R0's L3 change to its
  Morph chips is superseded by the select in hood.js. `rerender_morph` takes R0's `cancel=` and my `overrides=`,
  `timing=`; the rerender route's `more` kwargs go through R0's `_edit_start`. Once F1 lands, `shotEditTick` can drop its
  "did not run" text check.
- **The strip** (`t5-strip`): its inspector host `data-inspector-tab="hood"` mounts `{jobId, shotIndex}` and works with no
  hooks (the panel posts the edit and follows the job itself); pass `onRerender` to get the tile progress. A project mount
  with no `project` provider leaves the host's own rows. `GET /api/videos/{id}/shots` now carries `cost`.

## What needs Tys

- Whether "or queue it there…" (the POST to ComfyUI) should stay on the shared GPU, or the download only.
- Whether the LoRA picker should show only LoRAs made for LTX-Video 0.9.5 (needs a name rule or a list).
