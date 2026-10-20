# Real footage: your clips, the library, camera roll

Xenoform's strengths are editing, beat sync, audio reactivity, transitions and morphs. Real footage is the starting point.

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

- **NASA / public domain** items are preferred. They're committed as small seeds: 720px wide, 8s, muted.
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
