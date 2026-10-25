# The stills library

Every Simple cut is a chain of morphs between stills of single objects rendered in the vibe's material. The video model
does not invent those objects: they come from a library. This page says where the library lives, how it grows on your
own GPU, how a still earns its place, and how the chain draws on it.

## Two sets, one pool

- **Shipped** (`src/xenoform/ui_static/objects/<vibe>/`, listed in `objects.json`): the seed set in the repo, twelve a vibe,
  made once with Z-Image Turbo and kept small so a clone stays light.
- **Grown here** (`work/ui/objects/<vibe>/`, listed in `stills.json`): what this machine has rendered. Not in the repo.
  `XENO_STILLS` moves the folder.

The chain sees both as one pool (`stills.catalogue`). A grown still is an ordinary jpg: **delete it to drop it** from the
pool; the listing skips files that are gone.

## Growing

Fine-tune → **Library** shows the vibe's counts (shipped, grown here, your own) and two ways to add:

- **Grow 36 more** renders 36 subjects the vibe has not rendered yet, picked from `configs/subjects.json`: 24 families of
  nouns (celestial bodies, sea creatures, solids and knots, musical instruments, lamps, architectural fragments, bones,
  paper forms, and so on), each vibe weighting the families that suit its material and avoiding the ones that do not.
  Chrome draws on solids, instruments and machine parts; a risograph on creatures and plants; botanical on flowers and
  pods. Weighted sampling without replacement, so a core family leads without crowding the rest out. The 395 nouns are
  single sculptural subjects with no people, faces, text, brands or weapons.
- **Your own shapes**: type subjects ("a brass astrolabe, a wolf skull"), press **Make them**, and they are rendered in
  the vibe's material and listed as yours. They go **first in the chain** of the next cut. Up to twelve a request.

Both run on this GPU through the same path as the morphs (comfy-sdk → comfy-api-proxy → ComfyUI) with Z-Image Turbo
(open weights, Apache 2.0), about 6 s a still on a 12 GB card; the desk shows "Growing: 14 of 36 rendered · kept 11 ·
about 2:10 left" and the tally at the end. One grow at a time; **Stop** stops collecting (renders already queued finish
on the GPU, unused). The same from a terminal:

```bash
xenoform stills grow chrome-mercury --count 36
```

```bash
xenoform stills grow chrome-mercury --nouns "a brass astrolabe, a wolf skull"
```

```bash
xenoform stills import cosmic C:\some\folder\of\pngs
```

`--plan` prints the subjects and prompts without rendering; `xenoform stills status` prints the counts.

## The prompt

A new still must sit on the same backdrop and light as the pool it joins, or a morph between an old and a new still
morphs the room as well as the object. So the prompt is the **style prefix each shipped pool was actually made with**
(`configs/still_prompts.json`, taken from the batch prompts in `scripts/vibe_objects/`) plus a subject sentence in the
vibe's material: `One single {noun} made of liquid mirror chrome.`; `A sumi-e ink wash painting of one single {noun}.`
The five original vibes (liquid-gold, bloom, neon-night, ocean, cosmic) were rendered as glass or mercury on black and
graded afterwards; the library repeats that grade. A vibe with no entry falls back to its `still_style` in `vibes.json`.

## The checks

Every candidate is measured against the pool it joins (`stills.check`), so the thresholds calibrate to the vibe
instead of one rule for chrome and ink alike. The look (backdrop, size, edges, sharpness) is profiled on the **shipped**
stills alone, so a batch cannot drag a vibe's look toward itself import by import; the duplicate check sees every still:

| Check | Fails when | Calibrated on |
|---|---|---|
| backdrop | the border colour drifts more than three times the pool's own spread, never under 40 of 255; or the border ring is not a smooth surface (a quadratic fit leaves a residual over 18, or three times the pool's) | a uniform warm or bright shift the eye accepted measured 26 to 45; a grey studio against a black void, 60 and up; black side bars and cluttered rooms by the residual |
| size | the subject's area is under 0.4 times the pool's smallest or over twice its largest (a pool's own twelve already span three to four times) | a print that fills the frame; a speck |
| cropped | more than a tenth of an outer band is subject on more than one edge; stands aside for a pool whose own stills reach two or more edges (smoke, rain, wet floors), where the mask cannot tell object from backdrop | a bonsai running off the top; a whale centred on cosmic's graded gradient passes, because the subject is measured against a backdrop surface fitted to the border ring, not one border colour |
| soft | sharpness under a third of the pool's median | a blurred render |
| duplicate | the still correlates above 0.93 with a pool member or an earlier keeper | distinct objects in one pool correlate at most 0.86; a re-encode or three-pixel shift at 0.97 and up |

Rejects are set aside under `<vibe>/rejected/` with the reasons in the file name, never listed. The checks do not read
text or logos; the prompts forbid them and the eye catches the rest. The 24 Oct batch of 432 stills went through these
checks on import: 335 kept, 52 rejected (liquid-gold lost 19 to backdrop because that batch was rendered on a warm tan
studio where its pool sits on a dark gradient; iridescent-glass lost 10, mostly to black side bars its pool does not
have; the regenerated chrome kept 31), 45 skipped as banned props (pocket watch, vinyl record, cassette, vintage
microphone) or nouns the pool already had. The grey-studio chrome pass fails whole on backdrop.

## Scenes

A second kind of still beside the objects: **scenes**, wide frames in the vibe's material and light with no single
centred object (cosmic: a dark shore under a star field, a corridor of mirrors in violet light; neon-noir: a rain-slick
alley lit by magenta and cyan neon). `configs/scenes.json` lists four to eight subjects per featured vibe (and a default
list for the rest) and `configs/still_prompts.json` carries a `scene` prefix per vibe: wide frame, the vibe's material
and light, no centred object, no people, no text. They render through the same Z-Image graph into the vibe's folder,
listed in `stills.json` with `kind: "scene"`:

```bash
xenoform stills grow cosmic --kind scene --count 8
```

The Library row's **Grow 8 scenes** chip and `POST /api/stills/grow` with `kind: "scene"` do the same. A scene is a whole
frame, so the object-shaped checks step aside for it (no centred-subject size, no backdrop drift, no cropped edge, and no
zoom in `normalise_scale`); **soft** and **duplicate** still apply, the duplicate check against the vibe's other scenes.

Fine-tune → **Scenes** (the make body's `scene_stills`: `"off"` by default, `"mix"`, `"only"`) says how the chain uses
them. **Mix** lands a scene on every passage change (the story plan's section boundaries; on a short clip with no
passages, the first still and every fourth) with objects between, so the shore morphs into the orb and the orb into the
corridor of mirrors; **Only** morphs scenes alone; **Off** never draws a scene, even when the vibe has them. No still
repeats either way: past the scenes a vibe has, a slot is an object. The record (`simple/simple.json`) carries
`scene_mode` and `scene_files` (which stills were scenes), the stills animatic previews the same slots, and a re-cut
keeps them. A vibe asked for scenes it has none of cuts objects only and says so in the record's notes.

A morph that touches a scene gets its own prompt (`morph_pass.prompt_for(kinds=)`: "a wide landscape scene slowly melts
and flows into one single sculptural object that forms at its centre", and the reverse, and scene to scene) and its
scene guide stays uncompressed: the object prompt's "one single object ... stays centred" contradicts a wide frame at
the guide, and LTX then abandoned the scene at frame 1 (a cut, not a morph) on the first cosmic test. One variant per
pair kind, so a run encodes at most three more prompts on the CPU.

## The chain

`morph_pass.pick_stills` orders the pool before walking it: **your own shapes first**, then the objects the vibe has
**used least** (`work/ui/objects/usage.json`, one tick per cut), shipped order within. A cut of fifteen morphs over a pool
of fifty takes fifteen fresh objects, and the next cut of the same song opens on the thirty-five it left alone. The chain
walk itself still never repeats a pairing while the pool is bigger than the cut. The stills animatic that plays while
the morphs render previews the same picks without counting as a use, so the skeleton and the finished cut show the same
objects. A vibe with no shipped stills borrows a pool until it has three of its own; while it borrows, the stills it
does have (your own shapes included) lead the chain.

## Limits

- Stills only. A moving object to morph into (a still plus a short idle clip of it) is the next step after the contest.
- A thousand stills is about 65 MB on disk, so they stay in the work folder, never in the repo.
- Growing needs ComfyUI up with the Z-Image Turbo files; the Library row says so when they are missing.
