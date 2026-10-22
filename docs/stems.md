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

## Stems in the desk (on demand)

Splitting runs only when you ask for it: open the **Stem reactions** drawer under Macros, or press **Use this song's stems** on the VJ page. Nothing is split on Make.

- `POST /api/stems` with `{"audio_id": "<id from /api/analyze, or demo>"}` or `{"path": "C:/song.wav"}`, optional `"engine": "auto"|"demucs"|"bands"` and `"fps"`. Returns `{"id": <16-hex song hash>, "status": "running"|"done", "engine", "engines": {"demucs": bool, "bands": true}}`; a song already split answers `done` at once with `"cached": true`.
- `GET /api/stems/<id>` → `{"status", "engine", "stems": [names], "count", "roles", "frames", "fps", "envelopes": "/api/stems/<id>/envelopes.json", "error"?}`.
- `GET /api/stems/<id>/envelopes.json` → the `save_envelopes` JSON (per-stem curves, role curves, `drum_hits`, `stems`, `roles`, `fps`, `frames`, plus `engine`, `song`, `files` = stem wav paths). `vj.html` reads it via `?stems=`. `GET /api/stems/<id>/<name>.wav` serves one stem.
- Files live in `work/ui/stems/<song hash>/{stems.json, drums.wav, ...}`; the hash is of the audio bytes, so a renamed copy shares the cache. Up to 32 stems.
- `xenoform stems song.wav [--out dir] [--engine auto|demucs|bands] [--fps 24]` writes the same files from the command line (`--engine bands` never needs Demucs; it reports `engine: librosa`).
- The desk's drawer shows `splitting stems…` then `4 stems (librosa)` / `6 stems (demucs:htdemucs_6s)` and rebuilds the lanes, one per real stem; their gains ride on the job as `macros.stems` and the split's id as `macros.stems_id`.
- For a render: `stems_api.stems_path_for(audio_path)` returns the cached `stems.json` (or `None`; `build=True` splits now). The job state key is **`state["stems_path"]`**: the path of that file, so `dense.run_simple` can feed `stem_react.apply_frame` without splitting again.
