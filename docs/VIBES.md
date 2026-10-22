# Vibes

Xenoform ships 7 original vibes plus 19 extended ones. The originals live in `morph_pass.VIBE_LOOK` and `configs/autotune.json`. The extended ones are in `configs/vibes.json`, which `src/xenoform/vibes.py` loads.

Each registry entry carries: `look` (the morph prompt fragment), `negative`, `palette`, `lighting`, `material`, `motion` (notes for the edit), `ltx` (LTX-Video 0.9.5 morph settings: steps, cfg, img_compression, guide_end_strength), `transitions` (recommended per boundary: drop, switch, beat, silence), `still_style` (the Z-Image Turbo prompt used for its stills) and `tags` (for the source library).

The desk reads one list: `GET /api/vibes` (`vibes.catalog()`), the featured registry vibes in their featured order, then the seven originals (their names and one-liners live in `vibes.ORIGINAL_META`), then the rest of the ready registry with `legacy: true`. Each row carries its still URL, its object `pool`, `has_library` (its own 4-shot strip under `ui_static/library/<id>/`) and `library` (the folder the strip resolves to, through `pool` when it has none of its own). `app.js` falls back to its hardcoded arrays only when that fetch fails. Simple mode shows the featured vibes and keeps the legacy ones behind "More vibes". The judges page lists the pool-backed vibes; `scripts/gen_judges_cards.py` rewrites its cards from the same catalogue.

Autotune results in `configs/autotune.json` win over a registry `ltx` block. Backgrounds are black by default and every negative includes `shimmer`. No prompt names an artist or a franchise.

| id | name | one line | recommended transitions (drop / switch / beat) |
|---|---|---|---|
| `chrome-mercury` | Chrome mercury | A mirror-chrome droplet pours itself into the next form. | scene-morph / liquid-melt / stutter-cut |
| `ferrofluid` | Ferrofluid | Black magnetic liquid bristles into spikes on the kick. | scene-morph / datamosh / stutter-cut |
| `glass-prism` | Glass prism | Clear glass splits light into rainbow caustics. | scene-morph / luma-wipe / chroma-split |
| `hologram` | Hologram | A projected light-form flickers into being, line by line. | chroma-split / scene-morph / stutter-cut |
| `y2k-chrome` | Y2K chrome | Inflated chrome and frosted ice-blue plastic, millennium-clean. | zoom-through / liquid-melt / stutter-cut |
| `low-poly` | Low-poly 32-bit | Flat-shaded polygons from a late-90s console intro. | stutter-cut / zoom-through / stutter-cut |
| `seapunk` | Seapunk | Aqua and hot-pink gloss swims through retro web 3D. | liquid-melt / scene-morph / zoom-through |
| `psy-fractal` | Psy fractal | Ultraviolet sacred geometry unfolds in fractal layers. | zoom-through / scene-morph / chroma-split |
| `odd-machine` | Odd machine | Rubbery biomechanics twitch with uncanny precision. | datamosh / tape-stop / stutter-cut |
| `brutalist` | Brutalist | Raw concrete monoliths under a hard sun. | luma-wipe / stutter-cut / stutter-cut |
| `bioluminescent` | Bioluminescent | Deep-sea life glows cyan in the dark. | scene-morph / luma-wipe / liquid-melt |
| `ink-water` | Ink in water | Vermilion and gold ink blooms through dark water. | scene-morph / liquid-melt / luma-wipe |
| `porcelain-marble` | Porcelain marble | White marble and blue-glazed porcelain on black velvet. | scene-morph / luma-wipe / zoom-through |
| `lava-obsidian` | Lava obsidian | Glowing magma cracks through black volcanic glass. | scene-morph / liquid-melt / stutter-cut |
| `thermal` | Thermal camera | False-colour heat vision: white-hot to deep violet. | luma-wipe / chroma-split / stutter-cut |
| `crt-phosphor` | CRT phosphor | A glowing tube screen, soft scanlines, warm tape bleed. | tape-stop / datamosh / stutter-cut |
| `ice-crystal` | Ice crystal | Backlit frost crystals grow and fracture. | scene-morph / luma-wipe / chroma-split |
| `origami-noir` | Origami noir | Black and gold-foil paper folds itself into new forms. | stutter-cut / zoom-through / stutter-cut |
| `alien-botanical` | Alien botanical | Iridescent alien flora with glowing veins unfurls. | scene-morph / luma-wipe / liquid-melt |

## Assets per vibe

- `ui_static/objects/<id>/`: 8 stills (orb, nautilus, lotus, torus knot, jellyfish, crystal, feather, mobius ribbon) in the vibe's material. Simple mode chains them as A->B morphs. Generated with Z-Image Turbo (`scripts/vibe_objects/gen_extended.py`, prompts in `extended_prompts.json`).
- `ui_static/vibes/<id>.jpg`: the picker thumbnail.
- `ui_static/library/<id>/{wide,medium,close,reveal}.mp4`: the pre-rendered default clip pack, cut from a hand-checked orb -> nautilus morph. `configs/clip_pack.json` records each clip's autotune score and QA result. Everything is generated locally, so nothing needs fetching.

## Real-world subjects: anchor stills

Letting a model paint Jupiter gives two Great Red Spots and cartoon bands. `configs/anchors.json` maps real subjects (Jupiter, Saturn, Earth, Moon, Mars) to public-domain NASA photographs in `ui_static/anchors/`, with the source URL, credit and licence for each. When a continuity sentence names one, `continuity.ensure_stills` uses that photograph as the keyframe instead of a painted still. `anchors.harden()` and `anchors.harden_negative()` add single-feature, photoreal wording (for example `second great red spot, two red spots, extra moons` in the negative), and `anchors.ANCHOR_TUNE` lowers the model's freedom: full end guide, no compression, cfg 3.

## Shot QA

`src/xenoform/shot_qa.py` checks every finished morph for temporal flicker and luma pops. When torch, transformers and a cached CLIP ViT-B/32 are available, it also scores sampled frames against a good-shot prompt and failure prompts (duplicated features, cartoon, warped blob, smeared, text). `morph_pass` rerolls a failed shot once, with a new seed and less freedom, and keeps whichever version scores higher. The result goes in `morph_pass.json` under `qa`. Set `XENO_QA=0` to turn it off and `XENO_QA_CLIP_OFF=1` to skip CLIP. `XENO_QA_FLICKER` and `XENO_QA_POP` set the thresholds.
