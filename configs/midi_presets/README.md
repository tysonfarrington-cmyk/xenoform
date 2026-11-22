# Shipped MIDI presets

Each `*.json` here is a controller map that ships with Xenoform. When a controller is plugged in, the pages
(`/vj` and the desk) read its port name (Web MIDI's `MIDIInput.name`, or the bridge's port) and take the first preset
whose `match` (a regex, case ignored) finds that name, or whose `device` is that name. A preset beats the built-in
profiles (the Arturia MiniLab 3 factory map, the generic map); the user's own edits, kept per device name in
`~/.xenoform/midi_map.json`, sit on top of it, and **Reset to default** goes back to it.

```json
{"kind": "xenoform-midi-preset", "version": 1, "device": "Minilab3", "port": "Minilab3",
 "match": "mini\\s*lab\\s*3", "label": "Tys's MiniLab 3", "profile": "minilab3", "saved": "2026-11-05T10:00:00",
 "pages": {"vj":   [{"source": {"type": "note", "ch": 10, "num": 36}, "target": "pad:1", "mode": "hold", "min": 0, "max": 1}],
           "desk": [{"source": {"type": "cc", "ch": 1, "num": 74}, "target": "macro:intensity", "mode": "abs", "min": 0, "max": 1}]}}
```

`profile` names the built-in layout used to draw the controller and name its controls (K1, F2, A3); `pages` holds
midi.js's mapping rows for each page (see `docs/midi.md`). `XENO_MIDI_PRESETS` points the desk at another folder.

## Saving Tys's own layout as the first shipped preset

1. Plug the controller in (this PC lists the MiniLab 3 as **`Minilab3`**, with its extra ports `MIDIIN2 (Minilab3)`,
   `MIDIIN3 (Minilab3)` and `MIDIIN4 (Minilab3)`; the Python bridge adds a port number: `Minilab3 0`).
2. Open the desk (or `/vj`) in Chrome or Edge, allow MIDI, and open the MIDI map. Its header names the port it saw.
3. Map it the way you play it (Learn on any control, or keep the defaults), on `/vj` and on the desk.
4. Press **Save as the shipped preset** (under More in the map). The desk writes `configs/midi_presets/minilab3.json`
   here with both pages and the port name, and says where. Commit that file.
