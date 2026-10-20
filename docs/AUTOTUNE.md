# Autotune

`configs/autotune.json` holds per-vibe settings for the free LTX 0.9.5 morph pass (Draft and
Simple). `morph_pass.tuned(vibe)` reads it; both the classic morph pass and the Simple/Dense
path (`cloud_morph._local_clips`) apply **steps, CFG, guide image compression and end-guide
strength**. `XENO_AUTOTUNE` points at another file; a missing file means the built-in defaults
(20 steps, CFG 3, compression 18, end strength 1.0). `XENO_MORPH_STEPS` still overrides steps.
The LTX-2.3 Final tier is not affected: the sweep only ran on LTX 0.9.5.

## Method

`scripts/autotune` ran overnight on the 12 GB RTX 3080 Ti (19-20 Oct 2026, 1303 renders, all OK).
For each vibe it rendered A->B morphs from the vibe's own still pool over a grid of steps,
CFG, compression, prompt style, resolution and end strength, and scored each clip
automatically (CLIP object/quality similarity, exposure, haze, temporal checks). A setting is
only *recommended* when it is usable in the app (512x288, the vibe prompt, under the 8 s per
morph budget) and beats the default by a margin on the same pairs.

## Results (honest version)

| Vibe | Setting | Evidence |
|---|---|---|
| black | 20 steps, CFG 3, compression 0 | +1.5 over default on 3 pairs |
| liquid-gold | 16 steps, CFG 4, compression 0 | +3.3 on 3 pairs |
| neon-night | 20 steps, CFG 3, compression 0 | +4.2 on 4 pairs |
| ocean | 16 steps, CFG 4 | +2.9 on 5 pairs |
| cosmic | 20 steps, CFG 4 | +1.9 on 5 pairs |
| paper-summer | 12 steps, CFG 4, end strength 0.85 | +3.8 on 3 pairs |
| bloom | default | nothing beat the default by the margin |

These are **leads from 3-5 pairs each**, scored by a metric, not by people. They are small
gains and could be noise; treat them as better-than-default starting points, not proof. No
setting is slower than the default (all <=20 steps, ~6.8 s a morph measured, budget 8 s).

**Bad pairs.** Four still pairs scored well under their vibe's median and are kept apart (in
either order) when the chain is built: ocean scallop/sand dollar, cosmic DNA helix/sea urchin,
cosmic sea urchin/soap orb, paper-summer lantern/conch. If a pool cannot be reordered to avoid
one, the chain keeps going rather than failing.
