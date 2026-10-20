# Live VJ mode (`/vj`)

Open `http://127.0.0.1:<desk port>/vj` and press **Start mic / line-in**. You can pick the input device, for example a USB audio interface's line-in. Then go fullscreen (F).

- It plays pre-rendered morph loops: library clips from `/api/footage`, or your own files via **Add loops**.
- Audio is analysed in the browser (WebAudio `AnalyserNode`). Bass (30–150 Hz) drives the scale breath and liquid displacement. Highs (4–12 kHz) drive the chromatic split.
- Beats (energy flux, bass-gated, at least 1.4s apart) switch to the next loop using the selected transition: scene morph (liquid), luma wipe, chroma split, zoom-through, or hard cut + stutter. The effects run in WebGL with one fragment shader. The GPU cost is trivial and nothing is rendered by ComfyUI.
- Keys: space = next, 1–5 = transition, F = fullscreen, H = hide controls.
- Echo cancellation, noise suppression and auto-gain are switched off so the music isn't processed away.
