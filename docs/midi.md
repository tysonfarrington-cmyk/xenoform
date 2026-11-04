# MIDI controllers (`/vj`, the desk, and `xenoform midi`)

Plug a controller in and the picture is in your hands: hold a pad and its scene shows over the song (let go and the picture is back where the song is), other pads fire dance presets, knobs ride intensity, switch rate and the per-stem gains, and the desk's four macro knobs follow the hardware. The same mapping layer (`ui_static/midi.js`) serves the VJ page and the desk; a Python bridge (`midi_bridge.py`) carries the controller into browsers without Web MIDI and into renders.

## Plug in an Arturia MiniLab 3

1. USB in. Leave the controller on its **Arturia** program (the default after power-up; hold Shift and tap the first pad row if it was left in DAW mode). The map below is the factory Arturia-mode template.
2. Open `http://127.0.0.1:47317/vj` in Chrome, Edge or Opera and allow MIDI when asked. The HUD (P) shows `MIDI: 1 input(s)`.
3. Firefox or Safari (no Web MIDI): run `xenoform midi serve` in a terminal; the HUD shows `MIDI: bridge`.

## The default map

| Control | MIDI | VJ page target | Desk target |
|---|---|---|---|
| Knob 1 | CC 74 ch 1 | intensity (0–2) | macro: intensity |
| Knob 2 | CC 71 | switch rate (follow / 1 / 2 / 4 / 8 beats) | macro: speed |
| Knob 3 | CC 76 | drums gain | macro: chaos |
| Knob 4 | CC 77 | bass gain | macro: glow |
| Knob 5 | CC 93 | other gain | stem lane 1 |
| Knob 6 | CC 18 | vocals gain | stem lane 2 |
| Knob 7 | CC 19 | stem 1 gain | stem lane 3 |
| Knob 8 | CC 16 | stem 2 gain | stem lane 4 |
| Faders 1–4 | CC 82, 83, 85, 17 | stems 3–6 gain | drums / bass / other / vocals lanes |
| Mod strip | CC 1 | intensity | — |
| Main encoder | CC 28, relative | step through the premium transitions | — |
| Pads A1–A8 | notes 36–43 ch 10 | hold a scene: `pad:1`..`pad:8` (the loaded scenes in order, or the cut's shots with `/vj?job=<id>`) | — |
| Pads B1–B6 | notes 44–49 ch 10 | dance presets 1–6 | — |
| Pad B7 / B8 | notes 50 / 51 ch 10 | strobe / record (toggles) | — |

"stem N" means the Nth stem of the loaded song once **Use this song's stems** (VJ) or the **Stem reactions** drawer (desk) has split it; before that the knob says so and does nothing.

**Hold pads.** Pads are temporary overriders (mode `hold`): note-on shows the pad's scene, note-off snaps back to whatever the song position holds, as if the pad was never pressed. The transport never stops: the beat clock, the scene switches and the track run on underneath, so letting go lands on the scene the song has reached. Several held pads stack, the last one pressed shows; let go of it and the one under it is back. A CC button works the same way (on at 64 and up). Any pad on a dance preset, strobe, mirror or kaleido can be set to **On while held** too: the look applies while the pad is down and goes back to what it was on release. A page drives the stack through `XenoMidi.holds` (`press(id)`, `release(id)`, `top(prefix)`, `clear()`, `on(fn)`), or `XenoMidi.init({onHold(target, on, {top, stack})})`. If a controller is unplugged mid-hold its pads let go. The previous map put the premium transitions on pads A; the encoder still steps through them and Learn puts any of them on a pad.

Dance presets (`S.dance` in `vj.html`): the VJ page has no separate post-look, so a preset is a combination that lands on the next switch: 1 clean (auto transitions, no mirror, no strobe, intensity 1), 2 mirror, 3 strobe, 4 mirror + strobe at 1.3, 5 echo trail at 1.4, 6 chrome refraction + mirror at 1.6.

**Soft takeover.** Knobs and faders are absolute (0–127 to the target's range), and a control moves its target only once the hardware passes the value on screen, or comes within 3 % of it. A knob left somewhere else by a song change, a page change, a reset or a mouse drag never makes the picture jump: turn it towards the value and it takes over as it goes past. Each row shows an arrow while its control is away (▲ turn it up, ▼ turn it down, with both positions in the tooltip). A page gives the value its targets show through `XenoMidi.init({read: target => number})`; a target it does not answer for (the switch rate, a stepped choice) follows at once. Encoders step from the value on screen.

**Uncertainty.** Knobs, faders, mod strip and pads are confirmed against Arturia's MiniLab 3 and MIDI Control Center manuals. The clickable main encoder is assumed to send relative CC 28 in Arturia mode; if yours differs, Learn mode fixes it in one twist. Pads can be switched to CC in MIDI Control Center; this map expects notes.

Targets you can map to: `intensity`, `every`, `pad:1`..`pad:8`, `fx:next`, `fx:prev`, `fx:step`, `fx:auto`, `fx:1`..`fx:8`, `dance:1`..`dance:6`, `mirror`, `strobe`, `kaleido` (expert), `record`, `tap`, `hud`, the role gains `drums` `bass` `other` `vocals`, `stem:<name>` or `stem:<N>`; on the desk `macro:intensity|speed|chaos|glow`, the role lanes and `stem:<N>`. Modes: `abs` (0..127 to min..max), `toggle`, `trigger` (note-on only), `rel` (encoder steps), `hold` (on while the pad is down). A "generic" profile is there for anything else: knobs on CC 1–8 in CC order to intensity, speed, chaos, glow and the stem gains, sliders on CC 9–12 to the drums, bass, other and vocals levels, pads on notes 36–51 in note order to the scenes and then the dance presets.

## Maps by device name

Every controller has its own map, picked by its port name the moment it connects (Web MIDI's `MIDIInput.name`, or the port the bridge reads, which each bridged event now carries). In order:

1. **Your map** for that device, if you have changed anything: kept on the desk's machine in `~/.xenoform/midi_map.json` (`XENO_HOME` moves the folder), one entry per device name with a list of rows per page, and mirrored in the page's `localStorage["xeno-midi"]`. The newer copy of a device wins, so a map survives a desk restart, a cleared browser, a song change and a video change. The desk and `/vj` save only their own page, so neither overwrites the other's rows. `GET/PUT/DELETE /api/midi/maps/{device}` and `GET /api/midi/maps` are the routes.
2. **A shipped preset** whose `match` (a regex, case ignored) finds the name, or whose `device` is the name: `configs/midi_presets/*.json` (see the README there; `XENO_MIDI_PRESETS` moves the folder).
3. **A built-in profile** whose name pattern fits: the MiniLab 3 (`mini\s*lab\s*3`, so Windows' `Minilab3`, macOS's `Minilab3 MIDI` and the bridge's `Minilab3 0` all find it).
4. **The generic map** for anything else.

A name with a port number on the end is the same device as the name without it (`Minilab3 0` is `Minilab3`). Several controllers at once each play their own map; the panel shows and edits one of them (a picker appears with two or more), preferring a known controller and never a side port such as `MIDIIN2 (Minilab3)` while the main port is there. Plugging a controller in or out (Web MIDI's `onstatechange`, or a new port on the bridge) re-picks the map and says so; a controller unplugged mid-hold lets go of its pads.

**Reset to default** drops your rows for the device on this page, and its preset, profile or generic map is back. **Export** downloads the device's map (`{"kind": "xenoform-midi-map", "version": 2, "device", "profile", "mappings": [this page], "pages": {every page}}`); **Import** takes that file (or a version 1 export, or a bare list of rows) for the device shown, and keeps a shared layout's other pages too. **Save as the shipped preset** writes the device's map for every page into `configs/midi_presets/<device>.json` through `POST /api/midi/presets`, for the repository.

A table saved by the first `midi.js` (one map a page, no device names) is taken over by the first controller of its profile that connects, if it was your own work; an untouched copy of the factory map of the time is left behind, so the new hold pads come in.

## Learn mode

Press **L** on the VJ page (or the **Learn mode** button in the MIDI panel of the help overlay, `?`), click the control you want (a transition, mirror, strobe, record, HUD, a stem knob on the desk), then move a knob or hit a pad. Done; the row appears in the panel. Each row has its own **learn** and **×**. The panel also names the controller and its map, **Start from** (a built-in profile, when a controller's name was not recognised), **Reset to default**, **Export JSON** (downloads `xenoform-midi-vj.json`), **Import JSON** (paste and press Import) and **Save as the shipped preset**. On the desk the panel sits under Knobs → **MIDI controller**.

## The Python bridge

```
pip install "xenoform[midi]"          # mido + python-rtmidi + websockets (nothing else needs them)
xenoform midi list                    # ports
xenoform midi serve                   # first MiniLab (or --port NAME) -> http://127.0.0.1:47317
xenoform midi serve --desk http://127.0.0.1:47330 --quiet
```

`serve` reads the port, normalises every message to `{"type": "cc"|"note"|"pitch"|"prog"|"touch", "ch": 1..16, "num", "value": 0..127, "t"}` and posts batches (every 8 ms) to `POST /api/midi/event` with the port's name in `X-Xeno-Midi-Device`. The desk fans them out to every page on the websocket `/ws/midi`, and to `GET /api/midi/stream` (server-sent events) for a page or a server without websockets. `GET /api/midi/status` shows listeners, the last event, whether mido is installed (`bridge`), whether the desk can upgrade a websocket (`websocket`: uvicorn needs the `websockets` package the extra brings) and the port each source reads (`devices`); the websocket's `hello` carries `devices` too, so a page with no Web MIDI of its own still knows which controller it hears. A page asks the status first and goes straight to SSE when the websocket cannot upgrade, so a desk without the extra logs no failed `/ws/midi`. Any script can post the same JSON to drive a page. Without mido every command stops with the install line and nothing else changes.

Add `?webmidi=0` to a page's URL to take the controller from the bridge only: Web MIDI opens every input it listens to, and on Windows an open input is exclusive, so a second window must not hold the port another app needs.

## Recording a take

```
xenoform midi record take.json --seconds 90 [--port NAME] [--envelopes curves.json --fps 24]
```

Knob rides and pad hits go to `take.json`: `{"kind": "xenoform-midi-take", "version": 1, "profile": "minilab3", "port": ..., "seconds": 88.2, "events": [{"type": "cc", "ch": 1, "num": 74, "value": 96, "t": 1.204}, ...]}` with `t` in seconds from the start of the take. Play the song from a DAW or the VJ page while you record and the timing lines up with the render.

## How a take reaches the render

`midi_bridge.automation_to_envelopes(take, fps=24)` resolves the take through the profile's VJ map (or a mapping you pass) into per-frame curves:

```json
{"fps": 24, "frames": 2117, "seconds": 88.2, "source": "midi", "profile": "minilab3",
 "targets": {"intensity": [0.0, 0.0, 0.47, ...], "drums": [...], "stem:Kick": [...], "strobe": [0, 0, 1.0, ...], "pad:3": [0, 0, 1.0, 1.0, 0, ...]},
 "hits": {"pad:3": [12.5, 20.0], "dance:2": [32.0]}, "holds": {"pad:3": [[12.5, 13.1], [20.0, 20.4]]}}
```

Continuous targets are sample-and-hold between moves, 0..1 (intensity's 0..2 is scaled to 0..1); toggles are 0/1 curves; triggers are a 1 on the frame of the hit plus the times in `hits`; a held pad is a gate (1 on every frame it was down, at least one frame however short the press) with its presses in `hits` and its spans in `holds`. The desk carries this as `state["midi_take"]` on the job (the converted dict, or a path to the take JSON); `midi_bridge.take_value(env, "intensity", t)` samples it. Reading it on the render side is the next step: the beat-FX intensity follows `intensity`, cut choices honour `hits["fx:N"]`, and stem gains follow `stem:<name>` the same way the macro lanes do.
