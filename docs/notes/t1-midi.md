# T1 + T1b, MIDI on the same screen (branch t1-midi, 4 Nov 2026)

Cut from `ui-review-4nov` (574c1fc). Commits, in order: the bridge packages (bba37b4), hold pads (eb27fbd), soft
takeover (0e06f07), maps by device name (bb4ffe9), the map on the same screen (12ff321), the tests and this note.
Closes C7, V3 and A5 of `docs/UI_REVIEW.md`; the user-facing description is `docs/midi.md`.

## What landed

- **The `[midi]` extra is in the shared venv** (`mido` 1.3.3, `python-rtmidi` 1.5.8, `websockets` 17.4, installed by
  name so the editable install still points at rc2's `src`). `/ws/midi` now upgrades; `/api/midi/status` says whether
  it can (`websocket`) and which port the bridge reads (`devices`); a desk without the extra goes straight to SSE with
  no failed websocket in the console. **Tys's desks on 47330 and 47331 pick this up when they are next restarted.**
- **Hold pads**: mode `hold`; `XenoMidi.holds` (press, release, top, clear, on) is a last-in-wins stack; a release lets
  go even if the map changed meanwhile, an unplugged controller lets go of its pads. MiniLab pads A1-A8 (and the
  generic notes 36-43) are `pad:1..8`. On `/vj` a held pad shows scene N (the cut's shot N with `/vj?job=<id>`) over
  the song; S.cur, the switcher, the beat clock and the track never stop. Looks (dance, strobe, mirror) can be held too.
- **Soft takeover** for absolute knobs and faders (3 % window or passing the value), with a ▲/▼ catch-up arrow a row.
- **Maps by device name**: `~/.xenoform/midi_map.json` (`XENO_HOME` moves it) via `GET/PUT/DELETE /api/midi/maps/{device}`,
  mirrored in localStorage, newer copy wins; your map > a shipped preset (`configs/midi_presets/`) > the MiniLab 3 by
  name > generic; hot-plug re-picks; each controller plays its own map; Reset, Export, Import, "Save as the shipped
  preset" (`POST /api/midi/presets`). A table of the user's own from the old `midi.js` is taken over by the MiniLab.
- **The map on the screen** (`midi_map.js`, `midi_map.css`): badges (K1, A2, F3) on every mappable control, Map (the
  controller drawn with plain-word targets) and List, Learn as a popover anchored to the control, lights, Remove with
  Undo, named buttons. It replaces the desk's MIDI table (Knobs panel, MIDI controller row) and leaves `/vj`'s `?` modal
  for a docked panel opened by a MIDI button.

## How it was verified

- Tests: `tests/test_midi.py`, `tests/test_midi_maps.py` (routes, restart, presets), `tests/js/midi_test.js` under node
  (hold stack, takeover, profile by name, and the runtime's event pipeline in a vm sandbox; `tests/test_midi_js.py` runs
  it in the suite). Full suite before the last commit: 1710 passed, 2 skipped, none failed (it ran alongside three
  other sessions' suites and ComfyUI); the last small edits were re-run with every suite that touches the MIDI files.
- In the browser pane on a desk of my own (47377, `XENO_HOME` in my worktree), with no hardware: events posted to
  `POST /api/midi/event` with `X-Xeno-Midi-Device: Minilab3 0`, i.e. the bridge path. The pane was hidden, so rAF never
  ran: `/vj`'s frames were driven by script. Checked: `/ws/midi` upgrades; the same 7 s of song with and without pads
  held gives the same switches and transitions (the hidden pane stalls the clock now and then, with or without holds);
  holds stack and release to the song's scene; takeover on both pages; 8 knobs + 16 pads learned, desk restarted,
  browser copy wiped, another song loaded, all 24 still fire; Reset, Export/Import, a second controller, the legacy
  cases, the shipped preset (written, picked, then deleted: it held a test layout); the map, badges, popover, Undo at
  1366 and 375 px on `/vj` and the desk; `?clean=1` hides all of it.

## Not verified without hardware

Real Web MIDI with the MiniLab 3 (Chrome's permission prompt, the names Chrome gives its ports, hold latency), the
main encoder (assumed relative CC 28), DAW mode, the extra ports `MIDIIN2..4 (Minilab3)`, and anything drawn by rAF in a
visible window. The MiniLab **is** plugged into this PC (rtmidi lists `Minilab3 0`, `MIDIIN2 (Minilab3) 1`,
`MIDIIN3 (Minilab3) 2`, `MIDIIN4 (Minilab3) 3`); I only listed it and never opened it, because an open input on Windows
is exclusive and another app may need it.

## For Tys: test with the MiniLab 3 (10 minutes)

1. After merging, restart your desk so it has the `[midi]` extra. Leave the MiniLab on its Arturia program.
2. Open `/vj` in Chrome or Edge and allow MIDI. Expect "Minilab3 connected · Arturia MiniLab 3" and a green dot on the
   MIDI button; press it: the map docks on the right with the MiniLab drawn.
3. Load a track (or `/vj?track=demo`), Space to play. Hold pad A1: scene 1 shows. Hold A2 too: scene 2. Let go of A2:
   scene 1. Let go of A1: the picture is the song's own scene, and the switching on the beat never paused.
4. Turn knob 1: intensity moves only once the knob reaches the value on screen (List shows ▲/▼ until then).
5. Press L, click Strobe, hit pad B2: B2 is now strobe (the popover says what it heard). Done.
6. Restart the desk, reload `/vj`, load another song: the map is still yours. On the desk, the knobs wear K1-K4 and the
   Knobs panel's MIDI controller row shows the same controller. More → Reset to default brings the factory map back.
7. Tell me what the main encoder does (it should step the transitions) and whether pads feel instant.

## For Tys: save your layout as the first shipped preset

Map the controller the way you play it on `/vj` and on the desk (or keep the defaults), then in the map open **More →
Save as the shipped preset**. The desk writes `configs/midi_presets/minilab3.json` (both pages, the port name it saw,
`match` = the MiniLab pattern) and says where; commit that file. `configs/midi_presets/README.md` has the format.

## What is left (other sessions)

- T2 (perform): its `/vj` rewrite gets the map with `XenoMidi.dock()` (or `XenoMidi.panel(el)`), soft takeover with
  `init({read})` for its knob targets, and holds through `XenoMidi.holds` (the `pad:N` targets already match).
- T5 (strip): `data-midi-slot` controls get badges and Learn as they are; a marked group of chips is played by the
  map's fallback (a knob picks along it, a pad steps). The desk has no pad targets yet: Perform on the strip should
  press and release through `XenoMidi.holds`.
- Keep take (holds into keyframe lanes): `midi_bridge.automation_to_envelopes` now returns each held pad's spans.
- Until this branch is merged, every other branch's full suite sees one failure,
  `tests/test_midi.py::test_websocket_fan_out_and_http_ingest` (it assumed mido absent; the venv has it now).
