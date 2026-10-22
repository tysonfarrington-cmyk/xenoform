# Scene transitions

Xenoform has two kinds of transition:

- **Object morph styles** (`pour-harden`, `ribbon`, `snap` and so on, in `director.TRANSITIONS`). These shape how one object becomes the next *inside* a morph shot.
- **Scene transitions** (this page, `xenoform.transitions_fx`). These join two **whole clips** at an edit point. They run as post effects driven by the track analysis. Their intensity follows the bass/onset envelope, and every cut can snap to the beat grid.

The catalogue is served at `GET /api/v1/transitions` (`scene_transitions`, plus `scene_recommended`: the per-vibe pick for each boundary kind). Defaults live in `configs/transitions.json`.

## Picking one per boundary on the desk

Advanced > Shots lists one `<select>` per scene boundary. Auto follows `transitions_fx.recommend(vibe, kind)` where the kind is read off the storyboard: `drop` (the climax or a signature morph), `switch` (a section change), `silence` (a quiet section), else `beat`. Premium and core transitions are offered; classic wipes only with the Expert box. A live counter shows uses per type against the house cap (2); cuts, scene morphs and black holds are exempt.

The desk sends `scene_transitions: [{kind, boundary, index, auto}]` (one per boundary) and mirrors the pick onto `scenes[i].transition`. `guardrails.apply` enforces the cap on `scene_transitions` (overflow becomes a clean `cut`, Expert keeps and warns) and the result is forwarded in the job body and on `GET /api/jobs/{id}` as `scene_transitions`. `scene_edit.build` renders exactly that shape (`spec["transitions"]`); the Simple/dense render path does not yet read it, so for a dense cut the picks are recorded, guarded and reported but the boundaries still follow the planner. Per-shot `scenes[i].dance_fx` (the Look override on each card) is forwarded the same way as `shot_looks`; `beatfx.compose` applies one `dance_fx` mode per video today.

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

## v5: premium transitions ("new spells") and Classic

Wipes, iris, slice and hard stutter read as cheap and PowerPoint-like when they're overused. From v5, **most boundaries are a clean beat cut** (`cut`). A section change gets one premium transition, and the `transition_variety` guardrail (`configs/guardrails.json`) allows **at most 2 of any one type per video**. Any extra use becomes a clean cut. `cut`, `scene-morph` and `black-hold` are exempt from the cap.

| id | Name | Length | What it does |
|---|---|---|---|
| `cut` | Clean beat cut | 0 | A straight cut on the beat. This is the default boundary. |
| `match-cut` | Match-cut | 2 beats | The dominant subject of B (from a soft luma mask) is aligned onto A's silhouette in position and scale at the cut, then glides home to its own framing. Favoured by auto-pick. |
| `flow-carry` | Flow carry | 2 beats | A's own optical flow (from its last two frames) pushes through the cut, and B arrives already moving the same way, so it reads as one take. Favoured by auto-pick. |
| `depth-parallax` | Depth parallax dissolve | 2 beats | A depth estimate (soft luma + local sharpness + a floor prior, tuned for a lit subject on a dark ground) drives parallax: near layers drift further, and B resolves near-first. |
| `lens-breath` | Lens breath | 2 beats | Rack-defocus with real disc bokeh in linear light. The swap is hidden at peak defocus, with a 1.5% focus-breathing scale and a faint warm leak. |
| `chrome-refract` | Chrome refraction carry | 2 beats | B is seen through A's surface normals like liquid-chrome glass, and the refraction relaxes as B takes over. |
| `echo-trail` | Echo trail | 2 beats | A leaves a decaying ghost trail, the cut lands on the beat (mid-window), and the afterimage fades off B. |

Each one is a single smooth bump (`sin(pi t)`) with no oscillation over time, so there's **no shimmer**, and each one ends exactly on clip B.

**Classic (expert only, off by default):** `luma-wipe`, `stutter-cut`, `zoom-through`. Without Expert, the guardrail swaps them for a premium pick. `recommend()` maps old picks to `depth-parallax`, `cut` and `match-cut`. `transitions_fx.plan()` and `guard()` are the auto-pick and the guardrail. The VJ page (`/vj`) follows the same rules: mostly clean cuts, with premium spells on bar lines, and its Classic group only joins Auto with `?classic=1`.