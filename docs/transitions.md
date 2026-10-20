# Scene transitions

Xenoform has two kinds of transition:

- **Object morph styles** (`pour-harden`, `ribbon`, `snap` and so on, in `director.TRANSITIONS`). These shape how one object becomes the next *inside* a morph shot.
- **Scene transitions** (this page, `xenoform.transitions_fx`). These join two **whole clips** at an edit point. They run as post effects driven by the track analysis. Their intensity follows the bass/onset envelope, and every cut can snap to the beat grid.

The catalogue is served at `GET /api/v1/transitions` (`scene_transitions`). Defaults live in `configs/transitions.json`.

## The set

| id | Name | Length | What it does | Use it for |
|---|---|---|---|---|
| `scene-morph` | Scene morph | ~4 beats (2 s) | LTX-2.3 first/last-frame render from the last frame of clip A to the first frame of clip B (448×768 native 9:16, upscaled to 1080×1920). The whole frame melts into the next clip. GPU, open weights. | Section changes and drops. The signature move: one clip literally becomes the next. |
| `flow-morph` | Flow morph | 2 beats | Optical-flow warp plus blend (OpenCV when installed, otherwise a liquid displacement blend). | The CPU fallback for `scene-morph`, and quick previews. |
| `liquid-melt` | Liquid chrome melt | 2 beats | The frame ripples like molten chrome with a soft specular crest, then sets as clip B. | Smooth switch-ups and liquid vibes (liquid-gold, ocean). |
| `luma-wipe` | Luma matte wipe | 2 beats | A's shadows open first and reveal B through its darks. Black backgrounds make this very clean. | Elegant and sleek. Calm sections and outros. |
| `stutter-cut` | Beat cut + stutter | 1 beat | A hard cut on the beat. B's first frames stutter (with a 1-frame RGB kick at high intensity). | Breakbeat edits (Prodigy-style), fills, the first hit after a break. |
| `tape-stop` | Tape-stop warp | 2 beats | A decelerates, sags and dims to a freeze, then B drops in. | Pitch-down FX, half-time switch-ups, before a bass drop (Zeds Dead-style). |
| `datamosh` | Datamosh burst | 1 beat | A short block-smear burst: B's motion vectors push through A's pixels, then it resolves. Kept short on purpose. | Glitch fills and neon-night. Use sparingly: once or twice per video. |
| `chroma-split` | Chromatic split | 1 beat | RGB channels tear apart into the transient and snap back on B. | Snare/transient hits, futuristic and cyber looks. |
| `zoom-through` | Zoom-through | 1 beat | Push into the centre of A and land inside B (a match-cut on the centred object). | Centred objects (most Xenoform shots), cosmic, and risers. |
| `black-hold` | Silence = black | 2 beats | A fades to pure black for the gap, and B returns exactly on the hit. | Silences, breakdown gaps, and the beat before a drop. |

Post effect, not a boundary: **`bass-pulse`**. The frame scale breathes with the bass (3% by default), with a small chroma kick on strong onsets. It runs under every cut. Keep it subtle.

No shimmer or sparkle overlays, by design.

## Recommended defaults per vibe

| Vibe | drop | switch-up | on-beat | silence |
|---|---|---|---|---|
| liquid-gold | scene-morph | liquid-melt | stutter-cut | black-hold |
| neon-night | chroma-split | datamosh | stutter-cut | black-hold |
| paper-summer | scene-morph | luma-wipe | zoom-through | black-hold |
| ocean | scene-morph | liquid-melt | luma-wipe | black-hold |
| cosmic | zoom-through | scene-morph | chroma-split | black-hold |
| black | scene-morph | tape-stop | stutter-cut | black-hold |
| bloom | scene-morph | luma-wipe | liquid-melt | black-hold |

House taste (superlative, exquisite, futuristic, sleek): use **one signature move per section** (`scene-morph` at section changes), hard **beat cuts** inside sections, and **black holds** on the gaps. Switch-ups beat progressive builds: change the transition *type* when the music changes character, not every bar. Use glitch types (`datamosh`, `chroma-split`) as accents, not wallpaper.

## Beat snap

`beat_snap` in a scene-edit spec (or `configs/transitions.json`) moves every edit point to the nearest beat (`every: 1`), half-bar (`2`) or bar (`4`). A cut further than `max_shift` seconds (0.35 by default) from the grid is left where it is, so deliberate off-grid cuts survive.

## How scene-morph is rendered

1. Grab A's last frame and B's first frame, fitted to 448×768 on black.
2. Run `transitions_fx.scene_morph_graph(a_png, b_png)`: the LTX-2.3 22B distilled fp8 two-stage graph from `final_tier` (224×384 → 2× latent upsample → 448×768), RealESRGAN to 1080×1920, 49 frames (2 s at 24 fps), with the scene-morph prompt. About 1.5–3 minutes on a 12 GB 3080 Ti, depending on what else is queued. Peak VRAM matches the Final tier (~11.9 GB).
3. Splice A → morph → B (`splice_scene_morph`, with 3-frame seam blends), or let `scene_edit` drop the frames into the boundary window.
4. If there's no GPU or the render fails, use `flow-morph` instead.

## Building an edit

```
python -m xenoform.scene_edit spec.json
```

See the docstring in `scene_edit.py` for the spec. The contest tech reel (every transition, labelled, cut to Morph Engine v2) was built with this.
