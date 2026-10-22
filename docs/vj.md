# Live VJ mode (`/vj`)

Open `http://127.0.0.1:<desk port>/vj` and press **Start mic / line-in**. You can pick the input device, for example a USB audio interface's line-in. Then go fullscreen (F).

- It plays pre-rendered morph loops: library clips from `/api/footage`, or your own files via **Add loops**.
- Audio is analysed in the browser (WebAudio `AnalyserNode`). Bass (30–150 Hz) drives the scale breath and liquid displacement. Highs (4–12 kHz) drive the chromatic split.
- Beats (energy flux, bass-gated, at least 1.4s apart) switch to the next loop using the selected transition: scene morph (liquid), luma wipe, chroma split, zoom-through, or hard cut + stutter. The effects run in WebGL with one fragment shader. The GPU cost is trivial and nothing is rendered by ComfyUI.
- Keys: space = next, 1–8 = premium transition, 0 = auto, F = fullscreen, H = hide controls, L = MIDI learn mode, ? = help.
- Echo cancellation, noise suppression and auto-gain are switched off so the music isn't processed away.

## Stems from the loaded track

**Load track** plays a file with a beat grid analysed in the browser. **Use this song's stems** sends that file to the desk (`/api/analyze` gives it an id), asks `POST /api/stems` to split it (Demucs when installed, else the band split; cached by song hash so the second time is instant), then reloads the page with `?stems=/api/stems/<id>/envelopes.json&track=<id>` and picks the same track back up from `/media/audio/<id>`, so the four stem uniforms (`sDrum`, `sBass`, `sOther`, `sVoc`) follow real stems instead of the band estimate. The button then reads `Stems on (librosa)` or `Stems on (demucs:htdemucs)`. Per-stem gains are the desk's Stem reactions lanes (`localStorage["xeno-macros"]`, keys `stem:<name>`); the four role gains (`S.gain`) ride on MIDI knobs 3–6.

## MIDI

An Arturia MiniLab 3 works out of the box (pads = transitions and dance presets, knobs = intensity, switch rate and stem gains). Any controller maps in Learn mode (L). Firefox/Safari and headless runs get the controller through `xenoform midi serve`. See [midi.md](midi.md).
