# T6: Xenoform as a ComfyUI node pack (branch `t6-node-pack`)

Cut from `ui-review-4nov` (574c1fc) in the worktree `C:\Projects\xf-t6-nodes`. Five commits, nothing pushed or merged.
The brief is T6 of [HANDOFF_4NOV.md](../HANDOFF_4NOV.md); the pack's own README is [comfy_pack/README.md](../../comfy_pack/README.md).

## What landed

1. **The layout** (`b60ec2a`). `comfy_pack/` is the pack: relative imports (any folder name works), `pyproject.toml`
   with `[tool.comfy]` (`PublisherId` empty for Tys; no `web` key, or ComfyUI 0.33 loads the editor twice), a
   `requirements.txt` that lists nothing, the README. For an install without the repository it carries the Liquid
   chrome chain (12 stills at 768x432), the vibe registry's looks and tuning, `autotune.json` and the demo song
   (`tools/sync_bundle.py` writes them; `--check`). The repository's `__init__.py` registers the pack, then the desk's
   two nodes, and serves `comfy_pack/web`; the desk's sidebar tab moved there and shows itself only when `/xenoform`
   answers. **Outside the pack:** the root `requirements.txt` is what ComfyUI-Manager pip-installs into ComfyUI's
   Python; it pinned numpy 2.5.4 and librosa 1.0 (3.12 only: Tys's ComfyUI is 3.11), aiohttp 3.11 (under ComfyUI's
   3.14), Pillow 13 and opencv-python-headless, so it now lists nothing and the desk's pins moved unchanged to
   `requirements-desk.txt` (install.ps1, install.sh, CI, test_install and test_sdk_proxy follow; README lines too).
2. **The nodes** (`9b7b288`): Song Analysis (the desk's analysis; librosa if present, else the same steps in numpy),
   Storyboard (the desk's planners copied: Dense, Flow, the story plan for a song over 20 s, the knobs, the long-song
   chain, styles, timing, the chain of objects), Morph Timeline, Morph Pair (16 outputs for the stock LTX nodes),
   Assemble (each morph in its beat slot with `shot_indices` and the punches, muxed by ffmpeg).
3. **The Morph Timeline editor** (`bccc886`): `web/morph_timeline.js`, the song strip full window (sections, wave,
   beats, shots, intensity, objects), edits saved in a hidden widget, "Plan the edits" queues the node alone;
   `routes.py` (thumbnails, the song); `tools/editor_harness.py` (the editor on a stand-in ComfyUI).
4. **The demo workflow** (`1ade72c`): `workflows/xenoform_demo.json` and `_api.json`, written by
   `tools/build_demo_workflow.py` from the node definitions (the stock ones read from Tys's ComfyUI into
   `tests/fixtures/comfy_object_info_ltx095.json`).
5. **Tests and the dry run** (last commit): `tests/test_comfy_pack_{song,plan,nodes,workflow}.py`, `tools/dry_import.py`,
   this note, CREDITS rows for the copies, the CONTEST.md line.

## How it was verified

- The numpy analysis equals the desk's `analyze_audio` on the demo and the 20 s bundled song (beats, onsets, tempo,
  sections, flags exact; floats within 2e-6) and on `liquid_dnb.mp3` by hand; the drop equals `beatfx.drop_time`.
- The planner equals `dense.shots_for` (pacing engine off) on all six frozen analyses x six knob sets, and the chain,
  merge, knobs, styles, timing, prompts (every vibe x kind x style), tuning and length equal the desk's.
- Each Morph Pair output equals what `cloud_morph._local_clips` sets on the stock graph (captured with a fake client).
- The demo workflow is checked against the definitions (types, slots, widget values, required links, the API prompt
  as ComfyUI validates it) and run end to end with the pack's nodes for real and stand-in LTX nodes: a 12 s mp4.
- ComfyUI's own Python (3.11.15, numpy 2.4.4, torch 2.11, no librosa) imported the pack with `folder_paths` and the
  server stubbed and ran every node on the demo song, writing the mp4 (`test_a_dry_run_with_comfyuis_own_python`).
- The pack folder alone, copied under another name with the desk blocked from import, loads and plans.
- The editor was driven in a browser on the harness: drawing, cut drag, split, join, undo, chips, hold, seed,
  intensity points, pins, save and reload, the plan round trip, playback, the empty state, the Assemble's sockets.
- Full suite (before the last commit): 1,771 passed, 2 skipped, 1 failed. The failure is
  `tests/test_midi.py::test_websocket_fan_out_and_http_ingest`, which asserts the MIDI backend is absent: mido and
  python-rtmidi went into the shared `.venv` at 12:37 today (another round's install) and the Minilab3 is plugged in,
  so it reports available. This branch touches nothing MIDI. The pack, install, docs and asset tests (129) were run
  again after the last fixes, all passing.

## What is not verified (needs a ComfyUI restart, which is Tys's)

- The pack has never been loaded by a running ComfyUI: no restart was allowed. So: the Manager's install from the
  git URL, the nodes in the real node library, the editor and the button in the real frontend 1.49.6 (the hidden
  widget, the node's mini strip, `app.queuePrompt(0, 1, [id])` for one node, the routes on PromptServer, the video
  preview on the Assemble), and the Assemble's dynamic sockets in real LiteGraph.
- No morph was rendered. The demo cannot run before the restart, and a stock-only stand-in would only repeat what the
  desk renders daily through the same graph with the same values (pinned by test); the shared GPU was left alone.
- The "about a minute" for the demo's two morphs is the desk's Draft estimate, not a timing.

## What needs Tys

- Install through the Manager (Install via Git URL, `https://github.com/tysonfarrington-cmyk/xenoform`), restart
  ComfyUI, load `comfy_pack/workflows/xenoform_demo.json`, Queue; open the Morph Timeline. Report what breaks.
- Fill in `PublisherId` (in `comfy_pack/pyproject.toml` to publish the pack alone, or the root one for the whole
  repository) and `comfy node publish`.
- At merge: the root `requirements.txt` / `requirements-desk.txt` split touches install.ps1, install.sh and ci.yml;
  a branch that adds a pin to `requirements.txt` must move it to `requirements-desk.txt`. No CHANGELOG entry was
  written (to keep the merge with the other rounds simple).

## Left out on purpose

The desk's pacing engine (Breathe, drop runs), taste file, object families and usage history; beat FX, transitions,
the look pass and the end card in the Assemble; Final and Cloud tiers. The pack is the Draft path, honestly labelled.
