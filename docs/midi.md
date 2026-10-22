# MIDI controllers (`/vj`, the desk, and `xenoform midi`)

Plug a controller in and the picture is in your hands: pads fire transitions and dance presets, knobs ride intensity, switch rate and the per-stem gains, and the desk's four macro knobs follow the hardware. The same mapping layer (`ui_static/midi.js`) serves the VJ page and the desk; a Python bridge (`midi_bridge.py`) carries the controller into browsers without Web MIDI and into renders.

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
| Pads A1–A8 | notes 36–43 ch 10 | premium transitions 1–8 (clean cut, match-cut, flow carry, liquid flow, depth parallax, lens breath, chrome refraction, echo trail) | — |
| Pads B1–B6 | notes 44–49 ch 10 | dance presets 1–6 | — |
| Pad B7 / B8 | notes 50 / 51 ch 10 | strobe / record (toggles) | — |

"stem N" means the Nth stem of the loaded song once **Use this song's stems** (VJ) or the **Stem reactions** drawer (desk) has split it; before that the knob says so and does nothing.

Dance presets (`S.dance` in `vj.html`): the VJ page has no separate post-look, so a preset is a combination that lands on the next switch: 1 clean (auto transitions, no mirror, no strobe, intensity 1), 2 mirror, 3 strobe, 4 mirror + strobe at 1.3, 5 echo trail at 1.4, 6 chrome refraction + mirror at 1.6.

**Uncertainty.** Knobs, faders, mod strip and pads are confirmed against Arturia's MiniLab 3 and MIDI Control Center manuals. The clickable main encoder is assumed to send relative CC 28 in Arturia mode; if yours differs, Learn mode fixes it in one twist. Pads can be switched to CC in MIDI Control Center; this map expects notes.

Targets you can map to: `intensity`, `every`, `fx:next`, `fx:prev`, `fx:step`, `fx:auto`, `fx:1`..`fx:8`, `dance:1`..`dance:6`, `mirror`, `strobe`, `kaleido` (expert), `record`, `tap`, `hud`, the role gains `drums` `bass` `other` `vocals`, `stem:<name>` or `stem:<N>`; on the desk `macro:intensity|speed|chaos|glow`, the role lanes and `stem:<N>`. Modes: `abs` (0..127 to min..max), `toggle`, `trigger` (note-on only), `rel` (encoder steps). A "generic" profile (CC 1–8, notes 36–51) is there for anything else.

## Learn mode

Press **L** on the VJ page (or the **Learn mode** button in the MIDI panel of the help overlay, `?`), click the control you want (a transition, mirror, strobe, record, HUD, a stem knob on the desk), then move a knob or hit a pad. Done; the row appears in the panel. Each row has its own **learn** and **×**. The panel also lists the inputs, the active profile, **Factory map**, **Export JSON** (downloads `xenoform-midi-vj.json`) and **Import JSON** (paste and press Import). Mappings persist per page in `localStorage["xeno-midi"]`. On the desk the panel sits under Macros → **MIDI controller**.

## The Python bridge

```
pip install "xenoform[midi]"          # mido + python-rtmidi (nothing else needs them)
xenoform midi list                    # ports
xenoform midi serve                   # first MiniLab (or --port NAME) -> http://127.0.0.1:47317
xenoform midi serve --desk http://127.0.0.1:47330 --quiet
```

`serve` reads the port, normalises every message to `{"type": "cc"|"note"|"pitch"|"prog"|"touch", "ch": 1..16, "num", "value": 0..127, "t"}` and posts batches (every 8 ms) to `POST /api/midi/event`. The desk fans them out to every page on the websocket `/ws/midi`, and to `GET /api/midi/stream` (server-sent events) for a page or a server without websockets. `GET /api/midi/status` shows listeners, the last event and whether mido is installed. Any script can post the same JSON to drive a page. Without mido every command stops with the install line and nothing else changes.

## Recording a take

```
xenoform midi record take.json --seconds 90 [--port NAME] [--envelopes curves.json --fps 24]
```

Knob rides and pad hits go to `take.json`: `{"kind": "xenoform-midi-take", "version": 1, "profile": "minilab3", "port": ..., "seconds": 88.2, "events": [{"type": "cc", "ch": 1, "num": 74, "value": 96, "t": 1.204}, ...]}` with `t` in seconds from the start of the take. Play the song from a DAW or the VJ page while you record and the timing lines up with the render.

## How a take reaches the render

`midi_bridge.automation_to_envelopes(take, fps=24)` resolves the take through the profile's VJ map (or a mapping you pass) into per-frame curves:

```json
{"fps": 24, "frames": 2117, "seconds": 88.2, "source": "midi", "profile": "minilab3",
 "targets": {"intensity": [0.0, 0.0, 0.47, ...], "drums": [...], "stem:Kick": [...], "strobe": [0, 0, 1.0, ...], "fx:3": [0, 0, 1.0, 0, ...]},
 "hits": {"fx:3": [12.5, 20.0], "dance:2": [32.0]}}
```

Continuous targets are sample-and-hold between moves, 0..1 (intensity's 0..2 is scaled to 0..1); toggles are 0/1 curves; triggers are a 1 on the frame of the hit plus the times in `hits`. The desk carries this as `state["midi_take"]` on the job (the converted dict, or a path to the take JSON); `midi_bridge.take_value(env, "intensity", t)` samples it. Reading it on the render side is the next step: the beat-FX intensity follows `intensity`, cut choices honour `hits["fx:N"]`, and stem gains follow `stem:<name>` the same way the macro lanes do.
