How `src/xenoform/ui_static/objects/` was made (19 Oct 2026).

- `pools.py`: the eight objects per vibe, in chain order.
- `grade.py`: regrades a library still (1024x576 from `library/gpu_objects/`) for a vibe: the teal glow is re-hued, a vibe backdrop is added where the still is dark, then a gentle lift.
- `zimage_batch.py zimage_t2i_api.json paper_prompts.json paper`: the eight Paper summer stills, Z-Image Turbo through comfy-sdk -> comfy-api-proxy (seeds 1000-1007, about 4 s each warm on a 3080 Ti).

The library stills are not in this repo; only the graded jpgs ship.
