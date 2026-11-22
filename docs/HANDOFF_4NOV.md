# Handoff, Wed 4 Nov 2026 (Tys's brief, as given)

Kept here so the review in [UI_REVIEW.md](UI_REVIEW.md) can be traced to what it answers. The text below is the brief
as it was handed to the session, unedited apart from this note.

---

# RUN WITH /orchestrate-plus (Fable as orchestrator)
- You are the orchestrator: plan, split into independent tasks, delegate, check results. Only do work yourself if it needs real judgment.
- Route by difficulty: explorer (haiku) to search/read code; builder (sonnet) for routine edits and tests; architect (opus) for hard problems/big refactors; deep (fable) only for system design, bugs Opus couldn't solve, or costly-if-wrong calls. Try cheaper first, escalate only on failure.
- Subagents report in under 150 words with file paths. No pasted files or full logs. Use a subagent to run tests and report only failures.
- Order: Task 0 (UI review) first, then STOP and wait for Tys's ok. Then plan remaining tasks, pick cheapest agent each, run in parallel, wait for Tys's ok before merging/pushing.
# Xenoform: Claude Code handoff (4 Nov 2026)

Rules: work on a branch and do not merge or push without Tys. Keep the core app free of hard TD/MIDI dependencies (optional extras only).
Code reference: `src/xenoform/` (desk server `ui.py`, front end `ui_static/`, VJ `live.js`, `/vj` route).

## 1. TouchDesigner/MIDI status
DONE
- `osc_export.py`: writes features.json, CSV and an address map, and can stream OSC (`/xenoform/rms|sub|bass|mid|high|onset_env|beat_env|energy|mutate|is_onset|is_beat|is_drop|frame|section|fps`). python-osc is optional.
- `/vj` live mode: WebAudio analysis, beat-switched morph loops, 5 WebGL transitions, keys (space, 1–5, F, H).
- ComfyUI pieces: `comfy_nodes.py` (Xenoform custom nodes), `workflow_export.py` (storyboard → ComfyUI UI-format workflow JSON), `workflow_embed.py`, `comfy_server.py`/`comfy_health.py`.

NOT DONE (no code found)
- MIDI input of any kind (no Web MIDI or python MIDI).
- A TouchDesigner .toe/.tox template, or docs for OSC In CHOP.
- Spout/NDI video out to TD.
- REC dot and perform-window recording.

## 2. Tasks (in priority order)
### T1 MIDI in /vj (Web MIDI API)
- `navigator.requestMIDIAccess()`, with a device picker. Hot-plug supported.
- **MIDI learn**: click any parameter (transition, intensity, bass gain, chroma, loop select, speed, etc.), then move a control to bind it. Every knob, pad and slider must be mappable.
- **Pads/keys are temporary overriders**: holding one shows its scene/loop, and on release it snaps back to the clip at the current song position, as if the pad was never pressed. Multiple holds work last-in-wins.
- Knobs/sliders are absolute 0–127, mapped to the param range with soft takeover.
- **Persistence**: store mappings in `~/.xenoform/midi_map.json` (server endpoint) plus localStorage, keyed by device name. They survive restarts and song/video changes. Add export/import buttons.
- Acceptance: map 8 knobs and 16 pads, restart the app, load another song, and every mapping still works. A pad-hold/release test shows the timeline unaffected.

### T2 Perform window + REC
- A clean output window (second screen). The REC dot is a small red dot drawn in the control UI/perform overlay layer only, never in the canvas being captured.
- Record via `canvas.captureStream()` + MediaRecorder with the audio track, saved to the library.
- Acceptance: a recorded file has no dot, and its audio stays in sync within 1 frame.

### T3 TouchDesigner bridge (optional extra)
- Stream OSC live from /vj (via a small WS→OSC relay in the desk server) in addition to the offline export.
- Ship `td/xenoform_bridge.tox` (or build instructions) containing an OSC In CHOP with named channels, a Movie File In for the loops, and an example feedback/displace network driven by bass/beat.
- Optional Spout (Win) / Syphon out from the perform window. The MIDI→param bindings must also be sendable as OSC so TD can be driven by the same controller.
- Acceptance: TD receives all channels at ≥30 Hz with the docs followed in under 10 minutes.

### T4 Parameter visibility panel ("Under the hood")
Xenoform already builds ComfyUI graphs (`workflow_export.py`) but hides them. Expose them:
- A collapsible right-hand panel per shot/render that lists the actual graph: nodes in order (checkpoint, prompt, FLF frames, sampler, steps, cfg, seed, length, LoRAs/strength, resolution).
- Fields are editable with "re-render this shot" support. Changed values are highlighted against the preset.
- Buttons: "Open in ComfyUI" (POSTs the workflow to the local Comfy at :8188, or downloads the .json) and "Copy recipe".
- Acceptance: every value the render used is visible and matches the queued prompt JSON. Edits round-trip.

### T5 UI flow overhaul (inspired by metamike's flow, not his look)
- One linear flow: **Source → Plan (storyboard/timeline) → Tweak (params panel) → Render → Perform/Export**, shown as a step bar with one primary action per step.
- Timeline with keyframes for morph targets and intensity (as his camera path is keyed on a timeline), saved in the project/workflow file.
- Presets as a starting point, then fine control. Have a live/cheap preview before any expensive render.
- Hide advanced options behind the panel instead of separate pages.
- Acceptance: a first-time user can go from song to rendered clip in ≤5 clicks without reading docs.

### T6 Ship as a ComfyUI node pack
- Polish `comfy_nodes.py` so Xenoform's storyboard/morph and a "Morph Timeline" editor node (full-screen editor inside ComfyUI, saved with the workflow) run inside ComfyUI, as metamike's Virtual Camera node does.
- Acceptance: installs via ComfyUI-Manager from a git URL and runs the demo workflow.

## 3. Recent discoveries / ideas
- metamike "Reshoot any video in 4D" (x.com/itsmetamike/status/2116076558750462361): 4 local ComfyUI nodes on a 3090, using 4D Gaussian splat capture, ReDirector and LTX 2.3 with the CrossView-Warp IC-LoRA. A browser editor is also offered. Code is AGPL, so **do not copy code**. Ideas only.
- Possible feature: a "new camera" pass on source clips (orbit/dolly the same moment) as a morph-target generator. Research only, because licence and VRAM need checking (12GB local; Comfy Cloud 96GB available).
- Honest-limitations sections and short demo clips per feature work well for credibility. Do the same in the README.

## Task 1b: MIDI auto-setup presets (do with Task 1)
- On first launch / device connect, detect the controller by its MIDI port name and auto-load a matching preset (pads, knobs, sliders already assigned). Tys's own controller layout is the reference default preset; read its port name on his PC and save his current mapping as the first shipped preset.
- Unknown controllers get a generic default: pads in note order map to scene overrides, knobs in CC order map to the main parameters (intensity, morph mix, speed, colour etc.), sliders to master levels.
- Show an on-screen map overlay of what every control does, so new users aren't confused.
- Remap anytime via MIDI learn; user edits save as a personal preset on top of the default. Add a 'Reset to default' button and preset import/export (JSON) so people can share layouts.
- Acceptance: plug in Tys's controller on a clean install and everything works with zero setup; remaps persist across restarts and song/video changes; reset restores the default.

## DESIGN RULE (applies to all tasks): do not copy itsmetamike
- The X post is reference for the *principle* only (power under the hood + a focused creative editor). Do not replicate his layout, camera-editor UI, node names, look, or feature set.
- Xenoform's identity: music-first and performance-first. Everything should be driven by the song (beats, drops, sections) and playable live by MIDI. Design the UI around that, not around a camera/3D workflow.
- Pitch original ideas before building any UI: e.g. song-timeline as the main canvas, sections colour-coded, shots and morphs snapped to beats, the MIDI map living on the same screen.

- Tys confirmed: the 'Under the hood' panel (Task 4) is a MUST, built into the main UI flow in Xenoform's own style: one click from any shot to see and tweak its real parameters, no need to open ComfyUI.

## Task 0 (do FIRST): Full UI / UX review
- Launch the app, screenshot every screen and state, walk the whole flow as a first-time user (import song + video, plan, render, perform).
- Write UI_REVIEW.md: what's confusing, cluttered or slow; dead ends; inconsistent styling; missing feedback (progress, errors, what's happening).
- Propose a redesigned flow with rough wireframes (ASCII or images) in Xenoform's own music-first style, folding in the Under the hood panel, MIDI map and perform window.
- Get Tys's approval on the review before changing any UI code.
