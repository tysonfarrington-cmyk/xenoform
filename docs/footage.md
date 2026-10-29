# Real footage: your clips, the library, camera roll

Xenoform's strengths are editing, beat sync, audio reactivity, transitions and morphs. Real footage is the starting point.

## Your images and clips on the desk (`xenoform.own_media`)
Fine-tune -> Your images: a folder on this machine, or images dropped or picked on the row (`POST /api/own`). They lead the vibe's morph chain as morph targets, in name order (`state["morph_targets"]`), up to 12. Clips never go into an object cut (Tys, 28 Oct). For clips, pick Morph: Your clips at the top of the Vibe step: the song's shots alternate a clip and a morph, each clip playing its busiest stretch at 1:1 (`xenoform.clip_cut`, up to 24 clips, `own_media.MAX_CLIPS`). Each row keeps its own folder. The job records them under `own` in `simple.json`. The full edit below (scene detection, per-clip modes) is for scripts, through `python -m xenoform.scene_edit`.

## The free film pack (`xenoform.film_pack`)
Morph: Your clips has a **Free film pack** button: 24 short clips from 17 public-domain films (Méliès, the Lumières, Murnau, Keaton, Lang and more), listed with their archive.org URLs and licence lines in `configs/film_pack.json`. Nothing from the films is in the repo. Setup & models shows the pack as a row with a Download button: ffmpeg reads each window straight from its archive.org URL (a byte-range read, a few MB a clip; a source marked `whole` is downloaded in full first, cut from disk and removed once its clips are in place; a source whose upload has black bars baked into its frame carries a `crop`, and the bars are cut off) into `work/ui/film_pack/` (`XENO_FILM_PACK` moves it), one `NN_<id>.mp4` a clip in the manifest's order, with `CREDITS.md` (every film's title, year, maker, item URL and licence line, and the clips with their times), `pack.json` (what was made) and `labels.json` (what the chain calls each clip) beside them. A clip that fails three times is named and the rest continue. The list is curated over time and `pack.json` records the start, seconds and url each file was cut from, so Download again remakes a clip whose window moved, moves one the list reordered to its new name instead of pulling it again, and removes a file the pack made for a clip that left the list; a file of your own in the folder is never touched. The row's size is what is on disk once the clips are there, an estimate (about 300 KB a second) before. `GET /api/film_pack` is the status; `POST /api/setup/download {"id": "film-pack"}` starts it; `XENO_OFFLINE=1` refuses it. A clips cut takes up to 24 clips from a folder (`own_media.MAX_CLIPS`; images stay at 12) and cycles through them all.

## Your footage (`xenoform.footage`)
1. Drop in clips and images. `scan_folder(folder)` lists them.
2. `detect_scenes(clip)` finds shot boundaries (ffmpeg scene score), so a long clip becomes several shots.
3. `plan_edit(items, beats, duration, vibe=..., sections=[...])` cuts on the beat grid (every N bars). Section changes get the vibe's recommended *drop* transition; other boundaries get its *beat* transition (see `docs/transitions.md`).
4. Per-clip mode:
   - `as-is`: beat-cut, with stem-reactive post effects.
   - `animate`: `animate_graph(still)` runs LTX-2.3 with the same still as first and last frame, giving a seamless living loop.
   - `morph-into-next`: the boundary into the next clip becomes a `scene-morph`.
5. Render the spec with `python -m xenoform.scene_edit spec.json`.

## Built-in library (`assets/library/manifest.json`)
This is one manifest format for clips and the vibe anchor stills (`kind: image`), shared with the vibe-anchor work:

```json
{"version": 1, "items": [{"id": "nasa_sdo_arching_eruption", "kind": "video", "title": "...", "source": "nasa",
  "source_url": "https://images.nasa.gov/details/...", "licence": "...", "attribution": "...",
  "redistribute": true, "vibes": ["liquid-gold", "black"], "tags": ["sun", "centred"],
  "fetch": {"nasa_id": "...", "in": 8, "out": 16}, "file": "assets/library/liquid-gold/nasa_sdo_arching_eruption.mp4"}]}
```

- **NASA / public domain** items are preferred. Their mp4s are not committed (32 MB); the desk fetches the missing seeds in the background on first run (`footage.fetch_seeds`, skipped with `XENO_OFFLINE=1`), and `scripts/fetch_library.py` does the same by hand. The anchor stills stay in git.
- **Pexels/Mixkit** items must be `redistribute: false`. `scripts/fetch_library.py` downloads them into `assets/library/fetched/` (git-ignored). The validator rejects a Pexels/Mixkit item marked redistributable.
- `python scripts/fetch_library.py [--vibe ocean] [--force]` re-pulls everything (NASA seeds at up to 1920px).
- The desk serves `GET /api/footage?vibe=&kind=` and `/library-media/<id>`.

Seed clips (NASA, public domain; no NASA endorsement implied): SDO sun (gold), SDO flare on the limb (violet), SDO 131Å (teal), ISS Earth limb, ISS ocean swirl, ISS Hurricane Ian eye. They cover liquid-gold, cosmic, ocean, black, neon-night, bloom and paper-summer.

## Camera-roll morph (`xenoform.camera_roll`)
Point it at a folder or album. `pick_best` samples stills and frames from clips, scores them (sharpness, exposure, colourfulness; faces off), and drops near-duplicates. `order_chain` then orders them nearest-neighbour by colour histogram plus a 16×16 shape layout, so each morph travels a short visual distance. `morph_pairs` gives the (a, b) pairs for LTX scene-morphs, and `edit_spec` gives a beat-cut spec where every boundary is a scene-morph.

## Motion check (NASA seeds)

Every committed NASA clip must genuinely move. Seeds are scored by mean absolute frame difference
(96x54 grey, 4 fps) and stored as `motion_score`; the test suite requires >= 3. Current seeds:
SDO arching eruption (4.3), SDO X1.6 flare (13.9), ISS Earth at night with lightning (16.3),
ISS Soyuz relocation time-lapse (15.7). The earlier slow Earth-pan / quiet-sun seeds (score < 2) were removed.
