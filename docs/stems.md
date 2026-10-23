# Stem-reactive engine (`xenoform.stem_react`)

Stems drive the picture. Each stem has its own job:

| Stem | Drives |
|---|---|
| drums | cut candidates (`cut_points`: strong hits, snapped to beats, min gap), stutter energy, RGB transient kick |
| bass | scale breath and liquid displacement |
| other (+ vocals at half weight) | colour saturation and texture |

- Separation uses **Demucs htdemucs (MIT)** when installed. The installers (`install.bat` / `install.ps1`, `install.sh`) put it in `.venv` by default (the `stems` extra, with a CPU torch wheel); pass `-NoStems` / `--no-stems` to skip it, or add it later with `pip install demucs`. It runs on the **CPU** by default (`device="cpu"`), so it never takes VRAM from ComfyUI: on an 8-core box a 4-minute mp3 took 59 s and a 60 s cut 22 s (`-j 2`). Without Demucs, a librosa band split is used (HPSS percussive → drums, <150 Hz → bass, harmonic → other); it is also the fallback when Demucs cannot run (say, no network for its first model download, about 80 MB).
- `envelopes(stems, fps=24)` gives per-frame 0..1 curves plus `drum_hits` and `drum_strong`. Save them with `save_envelopes` and point a scene-edit spec at the file with `"stems": "env.json"`. `scene_edit` then uses `stem_react.apply_frame` instead of the plain bass pulse.
- The routing lives in `drive(env, t)` and can be changed in one place.

The contest demo v2 was cut with Demucs stems of Morph Engine v2.

## Stems in the desk (by default)

Every song the desk loads is split in the background the moment `/api/analyze` or `/api/demo` hands out its id (`stems_api.start_background_split(path)`), so by the first **Make** the stems are ready or on their way: Demucs on the CPU when it is installed, the librosa band split otherwise. The **Stem reactions** line under the knobs shows it without opening anything: `splitting stems (demucs)… 40 s`, then `4 stems (demucs)` (`4 stems (librosa)` for the band split, `6 stems (demucs)` for `htdemucs_6s`), and the lanes become one per real stem. One split runs at a time (a second song waits `queued`); results are cached by song hash, so a song split in an earlier session is `done` at once. The drawer and the VJ page's **Use this song's stems** still work the old way (`POST /api/stems`) and find the same split.

- `stems_api.start_background_split(song, engine="auto", fps=24)` is non-blocking and idempotent: one thread per song hash, a second call while it is queued or running returns that status, a cached `stems.json` is `done` without a thread, and it never raises (a missing file is `{"status": "error"}`). `split_status(song)` reads the registry: `{"status": "none"|"queued"|"running"|"done"|"error", "id", "engine", "seconds", "path", "error"}` (`seconds` is the elapsed time while it runs, the wall time when done).
- `GET /api/stems/for/<audio_id>` → that status for a desk song id (`demo`, or the id `/api/analyze` returned) without starting anything, plus `stems`, `count` and `envelopes` when done; `404` when the song is not loaded. The desk polls it every 2 s.
- `POST /api/stems` with `{"audio_id": "<id from /api/analyze, or demo>"}` or `{"path": "C:/song.wav"}`, optional `"engine": "auto"|"demucs"|"bands"` and `"fps"`. Starts the same background split (or finds it) and returns `{"id": <16-hex song hash>, "status": "running"|"done", "engine", "engines": {"demucs": bool, "bands": true}}`; a song already split answers `done` at once with `"cached": true`. This route and `GET /api/stems/<id>` report a `queued` split as `running` (with `"queued": true`), since older pages only keep polling on `running`.
- `GET /api/stems/<id>` → `{"status", "engine", "stems": [names], "count", "roles", "frames", "fps", "envelopes": "/api/stems/<id>/envelopes.json", "error"?}`.
- `GET /api/stems/<id>/envelopes.json` → the `save_envelopes` JSON (per-stem curves, role curves, `drum_hits`, `stems`, `roles`, `fps`, `frames`, plus `engine`, `song`, `files` = stem wav paths). `vj.html` reads it via `?stems=`. `GET /api/stems/<id>/<name>.wav` serves one stem.
- Files live in `work/ui/stems/<song hash>/{stems.json, drums.wav, ...}`; the hash is of the audio bytes, so a renamed copy shares the cache. Up to 32 stems.
- `xenoform stems song.wav [--out dir] [--engine auto|demucs|bands] [--fps 24]` writes the same files from the command line (`--engine bands` never needs Demucs; it reports `engine: librosa`).
- The desk's status line rebuilds the lanes, one per real stem, as soon as the split is done; their gains ride on the job as `macros.stems` and the split's id as `macros.stems_id`. Opening the drawer POSTs `/api/stems` as a fallback for a desk without the background hook.
- Demucs on the CPU runs `-j 2` (two segments in parallel; each already uses every core through torch). On the 60 s cut `-j 1` took 25 s, `-j 2` 22 s and `-j 4` 18 s; the 4-minute mp3 took 59 s at `-j 2`. More jobs are quicker but take the cores a Make composing at the same time needs, and more RAM; `XENO_DEMUCS_JOBS` sets it for a machine. `--segment` (`XENO_DEMUCS_SEGMENT`) lowers memory, not time.
- For a render: `stems_api.stems_path_for(audio_path)` returns the cached `stems.json` (or `None`; `build=True` splits now). The job state key is **`state["stems_path"]`**: the path of that file, so `dense.run_simple` can feed `stem_react.apply_frame` without splitting again.
