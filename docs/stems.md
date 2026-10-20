# Stem-reactive engine (`xenoform.stem_react`)

Stems drive the picture. Each stem has its own job:

| Stem | Drives |
|---|---|
| drums | cut candidates (`cut_points`: strong hits, snapped to beats, min gap), stutter energy, RGB transient kick |
| bass | scale breath and liquid displacement |
| other (+ vocals at half weight) | colour saturation and texture |

- Separation uses **Demucs htdemucs (MIT)** when installed (`pip install demucs`). It runs on the **CPU** by default (`device="cpu"`), so it never takes VRAM from ComfyUI. A 2-minute track takes about 20s on an 8-core CPU. Without Demucs, a librosa split is used (HPSS percussive → drums, <150 Hz → bass, harmonic → other).
- `envelopes(stems, fps=24)` gives per-frame 0..1 curves plus `drum_hits` and `drum_strong`. Save them with `save_envelopes` and point a scene-edit spec at the file with `"stems": "env.json"`. `scene_edit` then uses `stem_react.apply_frame` instead of the plain bass pulse.
- The routing lives in `drive(env, t)` and can be changed in one place.

The contest demo v2 was cut with Demucs stems of Morph Engine v2.
