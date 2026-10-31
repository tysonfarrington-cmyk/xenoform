The overnight library run (18 and 19 October 2026), before the app: where the first six vibes' stills came from.

CREDITS.md used to say the stills of liquid-gold, bloom, neon-night, ocean, cosmic and black had no generation record in
the repo. They have one, in the author's prototype folder (`xenoform_proto/overnight`, 2.6 GB with its media), and the
small files of it are kept here as they were.

What the run was (`overnight.py`, `ov_lib.py`, `plan.json`; resume-safe, ComfyUI on a 3080 Ti, 22:34 on the 18th to 06:48 on the 19th):

1. **Objects.** 108 objects and 8 textures, each a prompt and a seed in `plan.json` (a glossy black iridescent ferrofluid
   liquid metal object in a black void with a teal halo, "gr"), rendered with Z-Image Turbo, `z-image-turbo-Q8_0.gguf` (a GGUF
   quantisation of the Apache 2.0 model), the Qwen3-4B text encoder and the Flux autoencoder at 1024x576, 9 steps, cfg 1. Every
   first take passed the still gate (`still_gate`; a failure would have been retried at seed + 1000), and the review's
   twelve rerolls (`cull.json`) are in `objects_seeds.json` with the sentence each added.
2. **Material edits.** 117 FLUX.2 Klein 4B (`flux-2-klein-4b.safetensors`, Apache 2.0) edits at seed 77, 4 steps: the object
   or one of the run's guide stills re-rendered in chrome, mercury, iridescent, oil-slick or black glass (`klein_edits.json`
   has the file, the reference and the prompt of each material).
3. **Clips.** 93 LTX-2.3 22B distilled (fp8, two stages with the x2 spatial upscaler, 896x512 or 768x448, 24 fps) morphs
   between the objects, 4 not rendered (`clips.json`: prompt, guides, seeds, every take, the run's motion gate). The 19 October
   showcase reel that `scripts/build_showcase.py` replaced on 31 October was cut from five of them (`h08_rose_to_lotus_to_jellyfish_black_glass`,
   `h02_droplet_swarm_to_butterfly_to_swallow_gr`, `m02_tarot_card_to_orb_gr`, `m13_torus_knot_to_mobius_chrome`,
   `m22_lotus_to_jellyfish_iridescent`; its record called them LTX 0.9.5, which they were not).

What the six vibes took from it (`library/gpu_objects/<object>_<material>.png`, the author's local copies of the stills above,
which are not in the repo): liquid-gold, bloom, neon-night, ocean and cosmic regraded by `../grade.py` (12 each, the pools in
`../pools.py`), black (17) cut out onto pure black by a script that was not kept. `objects.json` carries, for each of the 77
rows, the still, the seed, the models and the grade; `lineage.json` is how each was tied to the run's own still on 31 October
2026, not from a file name:

- `grade.py` applied to the run's still reproduces the shipped jpg of the 60 graded rows to 32.8 dB or better (the raw still
  is 11 to 20 dB off), and
- SIFT feature matching with a RANSAC similarity fit finds the same object in all 77 (13 to 1,207 agreeing matches), at the
  same place in 73 and, for four black ones (manta ray, dragonfly, ribbon, liquid orb), at the scale their cut-out re-framed
  them to (0.77 to 1.37).

Files: `plan.json`, `overnight.py` and `ov_lib.py` are byte for byte the run's (their paths point at the author's machine of
that week); `objects_seeds.json`, `klein_edits.json`, `clips.json` and `lineage.json` are written by `build.py`
(`compile`, `verify` and `stamp` with `--proto <xenoform_proto/overnight>`; `stamp` writes the `source` text of the 77 rows).
Left out: the run's media (557 MB) and `log.jsonl` (run timings, retries and gate results; the seeds and prompts are in the
per-file records above).
