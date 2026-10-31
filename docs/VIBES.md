# Vibes

Xenoform has 30 vibes in `configs/vibes.json`, which `src/xenoform/vibes.py` loads: 11 featured and None on the desk, 10 more behind More vibes, and 8 not yet ready (`ready: false`), which the desk never shows. Six more come from the original set (`vibes.ORIGINAL_META`, with their looks in `morph_pass.VIBE_LOOK` and `configs/autotune.json`) and sit behind More vibes too, so the desk lists 28: the 11 featured and None, then 16 more behind More vibes. Wet paint was featured until 31 October 2026 (Tys: its colours are "pretty terrible"); it and the odd machine carry a `taste` note saying why they are off the first row, and keep their entry, stills, strip, card and example cut, so either still works when chosen by name. The eight not ready are `glass-prism`, `hologram`, `seapunk`, `psy-fractal`, `ink-water`, `thermal`, `crt-phosphor` and `alien-botanical`.

Each registry entry carries: `look` (the morph prompt fragment), `negative`, `palette`, `lighting`, `material`, `motion` (notes for the edit), `ltx` (LTX-Video 0.9.5 morph settings: steps, cfg, img_compression, guide_end_strength), `transitions` (recommended per boundary: drop, switch, beat, silence), `still_style` (the Z-Image Turbo prompt used for its stills) and `tags` (for the source library).

The desk reads one list: `GET /api/vibes` (`vibes.catalog()`), the featured registry vibes in their featured order, then the originals that are not featured (their names and one-liners live in `vibes.ORIGINAL_META`), then the rest of the ready registry with `legacy: true`. Each row carries its still URL, its object `pool`, `has_library` (its own 4-shot strip under `ui_static/library/<id>/`) and `library` (the folder the strip resolves to, through `pool` when it has none of its own). `app.js` falls back to its hardcoded arrays only when that fetch fails. Simple mode shows the featured vibes and keeps the legacy ones behind "More vibes". The judges page lists the pool-backed vibes; `scripts/gen_judges_cards.py` rewrites its cards from the same catalogue.

Autotune results in `configs/autotune.json` win over a registry `ltx` block. Backgrounds are black by default and every negative includes `shimmer`. No prompt names an artist or a franchise.

| id | name | one line | recommended transitions (drop / switch / beat) |
|---|---|---|---|
| `chrome-mercury` | Liquid chrome | A mirror-chrome drop pours itself into the next form. | match-cut / chrome-refract / cut |
| `neon-noir` | Neon noir | Wet streets, magenta and cyan rim light, rain in the haze. | flow-carry / echo-trail / cut |
| `porcelain-kintsugi` | Porcelain & gold | White porcelain that cracks open in gold on the beat. | match-cut / lens-breath / cut |
| `bioluminescent` | Deep-sea glow | Deep-sea forms that glow from inside. | flow-carry / depth-parallax / cut |
| `risograph` | Risograph | Two-colour print grain, inks sliding out of register. | match-cut / depth-parallax / cut |
| `iridescent-glass` | Iridescent glass | Blown glass with a rainbow film and swimming caustics. | match-cut / chrome-refract / cut |
| `liquid-gold` | Molten gold | Molten gold that pours, drips and cools to a polish. | match-cut / chrome-refract / cut |
| `ink-wash` | Ink & paper | Sumi ink blooming across wet paper. | match-cut / depth-parallax / cut |
| `cyberspace-95` | Cyberspace 1995 | Green wireframe on an endless grid, 1995. | match-cut / flow-carry / cut |
| `shadow-self` | Shadow self | A backlit silhouette and smoke in one shaft of light. | match-cut / echo-trail / cut |
| `botanical` | Bloom timelapse | A single bloom on black, scrubbed by the song. | match-cut / lens-breath / cut |
| `none` | None | No vibe: the things as they are, their own materials, plain light, no grade. | match-cut / depth-parallax / cut |
| `wet-paint` | Wet paint | Thick glossy paint folding into the next shape. (off the featured cards since 31 Oct) | match-cut / flow-carry / cut |
| `paper-summer` | Paper summer | A paper boat crosses a bright kitchen. | none recorded |
| `bloom` | Bloom | A flower opens on a green hill. | none recorded |
| `neon-night` | Neon night | A neon sign holds one quiet street. | none recorded |
| `ocean` | Ocean | A swimmer crosses a calm harbour. | none recorded |
| `cosmic` | Cosmic | A star field turns over a dark shore. | none recorded |
| `black` | Black | Black glass grows from one living form into the next. | none recorded |
| `ferrofluid` | Ferrofluid | Black magnetic liquid bristles into spikes on the kick. | scene-morph / datamosh / cut |
| `y2k-chrome` | Y2K chrome | Inflated chrome and frosted ice-blue plastic, millennium-clean. | match-cut / liquid-melt / cut |
| `low-poly` | Low-poly 32-bit | Flat-shaded polygons from a late-90s console intro. | cut / match-cut / cut |
| `odd-machine` | Odd machine | Rubbery biomechanics twitch with uncanny precision. | datamosh / tape-stop / cut |
| `brutalist` | Brutalist | Raw concrete monoliths under a hard sun. | depth-parallax / cut / cut |
| `porcelain-marble` | Porcelain marble | White marble and blue-glazed porcelain on black velvet. | scene-morph / depth-parallax / cut |
| `lava-obsidian` | Lava obsidian | Glowing magma cracks through black volcanic glass. | scene-morph / liquid-melt / cut |
| `ice-crystal` | Ice crystal | Backlit frost crystals grow and fracture. | scene-morph / depth-parallax / cut |
| `origami-noir` | Origami noir | Black and gold-foil paper folds itself into new forms. | cut / match-cut / cut |

**None** is the last featured card: each object in its own real materials and colours on a plain dark grey backdrop in soft studio light, photoreal, with a light glow and no dance look. Its stills (`configs/still_prompts.json` `none`) are grown from every subject family, so a None cut keeps to whatever realm or theme the line names.

## Assets per vibe

- `ui_static/objects/<id>/`: 12 stills (orb, nautilus, lotus, torus knot, jellyfish, crystal, feather, mobius ribbon, DNA helix, seed pod, conch, butterfly) in the vibe's material (`black` has 17), then the stills the finished videos show, listed after them in `objects.json`. Simple mode chains them as A->B morphs. Generated with Z-Image Turbo (`scripts/vibe_objects/gen_extended.py`, prompts in `extended_prompts.json`).
- `ui_static/vibes/<id>.jpg`: the picker thumbnail.
- `ui_static/library/<id>/{wide,medium,close,reveal}.mp4`: the pre-rendered default clip pack, cut from a hand-checked orb -> nautilus morph. `configs/clip_pack.json` records each clip's autotune score and QA result. Everything is generated locally, so nothing needs fetching.

## Real-world subjects: anchor stills

Letting a model paint Jupiter gives two Great Red Spots and cartoon bands. `configs/anchors.json` maps real subjects (Jupiter, Saturn, Earth, Moon, Mars) to public-domain NASA photographs in `ui_static/anchors/`, with the source URL, credit and licence for each. When a continuity sentence names one, `continuity.ensure_stills` uses that photograph as the keyframe instead of a painted still. `anchors.harden()` and `anchors.harden_negative()` add single-feature, photoreal wording (for example `second great red spot, two red spots, extra moons` in the negative), and `anchors.ANCHOR_TUNE` lowers the model's freedom: full end guide, no compression, cfg 3.

## Shot QA

`src/xenoform/shot_qa.py` checks every finished morph for temporal flicker and luma pops. When torch, transformers and a cached CLIP ViT-B/32 are available, it also scores sampled frames against a good-shot prompt and failure prompts (duplicated features, cartoon, warped blob, smeared, text). `morph_pass` rerolls a failed shot once, with a new seed and less freedom, and keeps whichever version scores higher. The result goes in `morph_pass.json` under `qa`. Set `XENO_QA=0` to turn it off and `XENO_QA_CLIP_OFF=1` to skip CLIP. `XENO_QA_FLICKER` and `XENO_QA_POP` set the thresholds.
