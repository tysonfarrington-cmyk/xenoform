# Stem-reactive engine (`xenoform.stem_react`)

(A layer of picture a stem, objects or clips, laid over one another by prominence: that is Stems mode,
[STEMS_MODE.md](STEMS_MODE.md).)

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

Every song the desk loads is split in the background the moment `/api/analyze`, `/api/demo` or `/api/songs/load` (a bundled song) hands out its id (`stems_api.start_background_split(path)`), so by the first **Make** the stems are ready or on their way: Demucs on the CPU when it is installed, the librosa band split otherwise. The **Stems** line under the song on the Song step shows it without opening anything: `Stems: splitting with Demucs… 40 s`, then `4 stems from Demucs: drums, bass, other, vocals` (`4 stems from the band split: …` without Demucs, six names for `htdemucs_6s`), and the lanes become one per real stem. The same line takes your own stems (below). One split runs at a time (a second song waits `queued`); results are cached by song hash, so a song split in an earlier session is `done` at once. The drawer and the VJ page's **Use this song's stems** still work the old way (`POST /api/stems`) and find the same split.

- `stems_api.start_background_split(song, engine="auto", fps=24)` is non-blocking and idempotent: one thread per song hash, a second call while it is queued or running returns that status, a cached `stems.json` is `done` without a thread, and it never raises (a missing file is `{"status": "error"}`). `split_status(song)` reads the registry: `{"status": "none"|"queued"|"running"|"done"|"error", "id", "engine", "seconds", "path", "error"}` (`seconds` is the elapsed time while it runs, the wall time when done).
- `GET /api/stems/for/<audio_id>` → that status for a desk song id (`demo`, the id `/api/analyze` returned, or a bundled `song-<id>`) without starting anything, plus `own` (true when your own stems are in use, below), `stems`, `roles`, `count` and `envelopes` when done; `404` when the song is not loaded. The desk's Stems line polls it every 2 s while a split runs; the knob strip's Stem reactions summary mirrors that line rather than asking again.
- `POST /api/stems` with `{"audio_id": "<id from /api/analyze, or demo>"}` or `{"path": "C:/song.wav"}`, optional `"engine": "auto"|"demucs"|"bands"` and `"fps"`. Starts the same background split (or finds it) and returns `{"id": <16-hex song hash>, "status": "running"|"done", "engine", "engines": {"demucs": bool, "bands": true}}`; a song already split answers `done` at once with `"cached": true`. This route and `GET /api/stems/<id>` report a `queued` split as `running` (with `"queued": true`), since older pages only keep polling on `running`.
- `GET /api/stems/<id>` → `{"status", "engine", "stems": [names], "count", "roles", "frames", "fps", "envelopes": "/api/stems/<id>/envelopes.json", "error"?}`.
- `GET /api/stems/<id>/envelopes.json` → the `save_envelopes` JSON (per-stem curves, role curves, `drum_hits`, `stems`, `roles`, `fps`, `frames`, plus `engine`, `song`, `files` = stem wav paths). `vj.html` reads it via `?stems=`. `GET /api/stems/<id>/<name>.wav` serves one stem.
- Files live in `work/ui/stems/<song hash>/{stems.json, drums.wav, ...}`; the hash is of the audio bytes, so a renamed copy shares the cache. Up to 32 stems.
- `xenoform stems song.wav [--out dir] [--engine auto|demucs|bands] [--fps 24]` writes the same files from the command line (`--engine bands` never needs Demucs; it reports `engine: librosa`).
- The Stems line feeds the **Stem reactions** lanes under the knobs (`window.XENO_STEMS_UPDATE` in `ui_v6.js`): one lane per stem in use, rebuilt when the split is done and again when your own stems arrive or go, so the names in the lanes are the names in `stems.json`; their gains ride on the job as `macros.stems` and the split's id as `macros.stems_id`. Opening the drawer POSTs `/api/stems` as a fallback for a desk without the background hook.
- Demucs on the CPU runs `-j 2` (two segments in parallel; each already uses every core through torch). On the 60 s cut `-j 1` took 25 s, `-j 2` 22 s and `-j 4` 18 s; the 4-minute mp3 took 59 s at `-j 2`. More jobs are quicker but take the cores a Make composing at the same time needs, and more RAM; `XENO_DEMUCS_JOBS` sets it for a machine. `--segment` (`XENO_DEMUCS_SEGMENT`) lowers memory, not time.
- For a render: `stems_api.stems_path_for(audio_path)` returns the cached `stems.json` (or `None`; `build=True` splits now). The job state key is **`state["stems_path"]`**: the path of that file, so `dense.run_simple` can feed `stem_react.apply_frame` without splitting again.

## Your own stems

If you already have the song's stems (a DAW export, Suno's stems of its own songs), they can take the split's place. On the Song step the Stems line under the song has **Use your own stems**: pick the files, and the line reads `Stems: reading your 11 files…`, then `11 stems of your own: Drums, Bass, Guitar…`. The next Make, a re-cut and the VJ page read them where the split's stems were; nothing else changes.

The rules:

- 1 to 32 files, wav, mp3, flac, ogg, aiff or m4a, each the song's length within 1.5 s (a stem of another length is refused by name, with both lengths). Mixed sample rates are fine. A file over the desk's upload cap (120 MB) is refused by name.
- Names come from the files, with a leading index (one or two digits) and its separators dropped: `1 Drums.wav` is **Drums**, `02_bass.wav` is **bass**, `Lead Vocals.wav` stays **Lead Vocals**, `808 Bass.wav` keeps its 808, and letters of any alphabet stay (`Batería`, `Батарея`). Two files that clean to the same name get a number; a name that is a key of `stems.json` (`song`, `files`, `frames`, …) gets ` stem` after it.
- Roles are read from the names (`stem_react.role`): drum, kick, snare, hat, perc, beat, cymbal, tom, clap are **drums**; bass, sub, 808 are **bass**; vocal, vox, voice, choir, sing are **vocals**; everything else (guitar, keys, strings, synth, brass, woodwinds, other) is **other**. The role curves are the max of their members, as for a split.
- **Back to Demucs** (**Back to the split** on a desk without Demucs) removes your stems and brings the split back: the Demucs `stems.json` that was there is kept as `stems.split.json` and restored at once; with none kept, the background split runs again. A split still running when your stems arrive finishes on its thread and is kept aside the same way, never written over your file.
- Files live in `work/ui/stems/<song hash>/own/<name><ext>`; the envelopes are the song's `stems.json` with `engine: "user"` and `own: true`, built on a background thread through the split registry, so `GET /api/stems/for/<audio_id>` reports them like a split (`status`, `own`, `engine`, `stems`, `roles`, `count`, `envelopes`).
- `POST /api/stems/own`: multipart, `audio_id` (`demo`, an upload id or a bundled `song-<id>`) and `files`; answers the status at once (`queued`, then `running`, then `done`) with `stems` and `roles`; a refusal is a 400 (413 for the size cap) with a plain sentence naming the file, and on the desk it stays on the line for ten seconds while the split's poll goes on under it. `POST /api/stems/own/clear` with `{"audio_id"}` is Back to Demucs and answers the status it went back to.
- Two picks at once, or a pick while the set before is still being read, take turns: each request saves into a folder of its own and the newer set wins; its build waits for the one before to let go of the files (Windows keeps an open wav locked) and the one before writes nothing. Back to Demucs during a build waits the same way, so nothing is left under `own/`.
- `xenoform stems song.wav --own a.wav b.wav [--out dir]` builds the same `stems.json` from the command line, from the files where they are, under the same rules (`stems_api.own_stems_from_files`); without `--out` it goes into the song's cache folder and keeps a split's file aside the way the route does, so the desk's Back to Demucs finds it.

Checked with Suno's eleven stems of Morphing Wobble (102.6 s, 48 kHz): the envelopes took about 3 s on the CPU, the checks on the 217 MB of wav under a second; Lead Vocals read as vocals, Drums and Percussion as drums, Bass as bass, and Guitar, Keyboard, Strings, Synth, Other, Brass and Woodwinds as other.
