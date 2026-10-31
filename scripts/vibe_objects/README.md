How `src/xenoform/ui_static/objects/` (the stills), `vibes/` (the picker cards) and `library/` (the default clip packs) were made. Where each file came from is in [CREDITS.md](../../CREDITS.md).

The first six vibes (19 Oct 2026)

- `pools.py`: the twelve objects per vibe, in chain order.
- `grade.py`: regrades a library still (1024x576 from `library/gpu_objects/`) for a vibe: the teal glow is re-hued, a vibe backdrop is added where the still is dark, then a gentle lift.
- `provenance/`: where those library stills came from. The overnight run of 18 and 19 October (Z-Image Turbo objects, FLUX.2 Klein 4B material edits, LTX-2.3 clips) with its plan, scripts, seeds, prompts and the check that ties each of the 77 shipped stills of liquid-gold, bloom, neon-night, ocean, cosmic and black to its source still. See its README. The library stills themselves are not in this repo; only the graded jpgs ship.
- `SEED0=2000 zimage_batch.py zimage_t2i_api.json paper_prompts2.json paper2`: the twelve Paper summer stills (close framing), Z-Image Turbo through comfy-sdk -> comfy-api-proxy, about 4 s each warm on a 3080 Ti. The jellyfish gets a 1.3x centre zoom. `paper_prompts.json` is the first, smaller-framed set.

The other vibes (20 to 31 Oct 2026)

- `gen_extended.py` with `extended_prompts.json` and `featured_prompts.json`: the twelve stills of each of the 20 extended vibes. `gen_v2.py`: thirty-six more for each featured vibe (24 Oct). `regrade_bio.py`: the bioluminescent colour pull.
- `ship_grown.py` with `shipped_31oct.txt`, `shipped_31oct_morphs.txt` and `shipped_31oct_presets.txt`: the stills grown on the author's machine (`work/ui/objects`, git-ignored) that are on screen in a finished cut, a loved morph or a chain preset, copied byte for byte into `ui_static/objects/<vibe>/` with a row each in `objects.json` (model, seed, prompt file, date). `stills.catalogue` lists a shipped copy of a grown still once.
- `make_library.py`: one orb to nautilus LTX 0.9.5 morph of a vibe's own stills cut into wide, medium, close and reveal (the 20 Oct and 23 Oct strips), the temporal QA of each going into `configs/clip_pack.json`.
- `make_card.py` with `picks_thumbs.json` and `picks_cards.json`: a vibe's picker card from one frame of a finished Cloud Final cut.
