# Stems mode: a layer for each stem

Tys, 31 Oct 2026: "a mode where i can apply a certain object/clip to a individual stems, and have them maybe overlap.
it would probably have to be a separate mode altogether, it should follow the same rules but ... opacity may have to be
adjusted or that can be a setting for how dominant or prominent the stem is so if theres two scenes/stems running for
example you can see both".

Stems is the third source on the desk, beside **Objects** and **Your clips** (the Morph row under the vibes). Each stem
you turn on becomes a **layer**: its own cut, objects or clips, made by the same planner as every Make but on that
stem's drive, so it plays where its stem plays and rests where its stem rests. The layers are then laid over one another,
each as visible as its stem is active and as prominent as you set it. Where two stems play at once you see both.

(This file is `STEMS_MODE.md` and not `STEMS.md` because `docs/stems.md`, the split and the stem reactions, already
exists, and on Windows the two names are one file.)

## What happens on a Make

1. **The split.** The song's stems come from the split the desk already makes for every song it loads (`stems_api`:
   Demucs htdemucs on the CPU when installed, else the librosa band split; your own stems when you gave them). The
   Stems step's **Split stems** button starts it, or finds it, and shows its progress; a Make that finds no split runs
   it first. No GPU and no ComfyUI queue are involved. The first Demucs run downloads its weights (about 80 MB).
2. **Each stem's activity** (`stems.activity_for`, cached as `activity.json` beside the split): a 0..1 curve a frame,
   the stem's RMS over a beat-long window, normalised to the stem's own loud level (never above a quarter of the loudest
   stem's level, so a stem that is only bleed stays silent), gated (nothing under 12 % of that level, all from 55 %),
   then followed with an attack that arrives within a beat and a release over two beats. Also the stem's onsets. A
   Length window reads the whole song's curves and cuts them to the window, so its edges hear the music around them.
3. **Each layer's cut** (`stems_mode.run`, then `dense.run_simple` or `clip_cut.run` per layer, under
   `<job>/layers/<stem>/`): the whole Make's knobs, Shape (Breathe, Drops), Look, Timing and Effects, on the song's
   shared passages, with the layer's vibe and pins or its clips, its own seed, and the stem's drive. The planner's shots
   are reshaped by the drive (`stems_mode.drive`, hooked into `dense.shots_for` by the `stem_drive` key):
   - where the stem goes out for a bar or more, the layer cuts: on the first beat inside the silence and on the last beat
     before the stem comes back (`stem_cut`), whatever the planner's shots were, so the return is a fresh morph;
   - a stretch where the stem is silent (mean activity under 0.12, peak under 0.3) folds into **one** shot, marked
     `stem_silent`, with no effects and no event: one morph at most is spent where nothing shows, and the layer fades
     out there;
   - two **quiet** shots of a passage (mean under 0.4) become one, at most 16 beats long: a quiet stem cuts half as often;
   - a drop run's **heat** on a layer is the run's heat times how hard the stem plays it (full from 0.8 activity, never
     under 0.2 while it plays);
   - a drop's **event** (its punch, stutter and drop boundary) stays only on a layer whose stem plays the drop's first
     beat (activity 0.35 or more): the stem that carries the drop gets the event; on the others the boundary is a plain
     switch;
   - every shot says how active its stem was (`stem_activity`) and how many of its onsets it holds (`stem_onsets`).
4. **The composite** (`stems_composite.build`): the layers laid together into the job's `xenoform.mp4`, the song mixed
   in once (AAC 192k, as every cut is). See *Prominence and blend* below.

The making screen shows one bar for the whole Make: every layer's morphs and cut count as the morph phase, layer by
layer ("Drums layer (1 of 2): Morph 3 of 12"), then the layers are laid together. The desk's estimate multiplies by the
layers that are on (and so do Cloud's credits).

## The rules it keeps

- **The same planner, the same passages.** Every layer is planned by `pacing.song_plan` on the mix's sections, so
  Breathe, the drop runs and their heat are shared; only the shots inside a passage follow the stem. With a **lead**
  layer, the passages are the mix's split where the lead stem goes out for two bars or more (that stretch is a release,
  a breakdown, for every layer).
- **One Shape for all.** The knobs, Breathe and Drops, the Look, Timing and Effects are one setting for every layer; a
  re-cut with new knobs re-cuts every layer.
- **Every body passes the guardrails.** The Make's body is checked once (`guardrails.apply`, which validates the layers
  and writes a `[stems]` line), and every layer's own body passes `guardrails.apply` again before it renders, so the
  taste file, the kind guards and the rest apply per layer; each layer's report lines are kept in the record.
- **Objects or clips, never both in a layer.** A layer is `objects` (the vibe's stills, the Chain row's pins if you
  ask) or `clips` (your clips, each morphing into the next, as a clips cut). An objects layer and a clips layer may run
  at once and overlap (decision 10 of the plan, Tys, 31 Oct). Pins sent with a clips layer, or clips with an objects
  layer, are left out with a `[stems]` line.
- **No object twice across layers.** Each objects layer leaves out the stills the layers before it used and every
  still of the same name (`avoid_stills` and `avoid_nouns`, honoured by `morph_pass.pick_stills`: no orb in gold on
  one layer and an orb in glow on the next); your own images lead only the first objects layer.
- **One palette per cut** by default: a layer without a vibe takes the cut's. You may pick another vibe per layer.
- **No Polly, no end card on a layer.** The performer is off in layers; the end card, when on, is burned into the
  composite.
- **Cloud stays behind the tick.** Cloud Final runs only with "Spend my Comfy Cloud credits" ticked, as always, and a
  layer of clips stops a Cloud Make before anything is sent (Cloud has no clips path). The estimate says the credits
  multiply by the layers.
- **Four layers at most**, one a stem.

## The body keys

The Make body (`POST /api/generate`) of a Stems cut:

```json
{
  "mode": "stems",
  "vibe": "black",
  "layers": [
    {"stem": "drums", "kind": "objects", "vibe": "liquid-gold", "pins": {"0": "liquid-gold/012_sun_disk.jpg"},
     "prominence": 0.8, "blend": "screen", "lead": false},
    {"stem": "other", "kind": "clips", "clips_folder": "D:/film pack", "prominence": 0.6, "blend": "screen"}
  ],
  "...": "every other Make key as usual (quality_tier, aspect, length_s, breathe, drop_mode, macros, ...)"
}
```

- `stem`: a stem of the song's split (drums, bass, other, vocals from Demucs; the band split's; your own stems' names).
- `kind`: `objects` (default) or `clips`.
- `vibe` (objects): the layer's vibe; empty is the cut's.
- `pins` (objects): chain slot to still file, as the Chain row's `chain_pins`.
- `clips`, `clips_folder` or `own_id` (clips): a list of clip paths, a folder, or the files dropped on the desk.
- `prominence`: 0..1, how dominant the layer is (default 0.7).
- `blend`: `screen` (default), `normal`, `add`, `lighten` or `multiply`.
- `lead`: true on at most one layer: its stem's entrances and exits set the passages.
- `on`: false leaves a row out (the desk sends only the rows that are on).

What `stems_mode` adds to each layer's own body: `mode: "simple"`, the layer's `vibe`, `chain_pins` or `own_clips`
and `morph_source`, its seed (the cut's plus 97 a layer), `stem_drive` (the stem's activity, onsets, fps and beat),
`avoid_stills` and `avoid_nouns`, `stem_layer`, `end_card: false`, `performer: 0`.

## The record

`<job>/simple/simple.json` of a Stems cut:

- `mode: "stems"`, `plan_name: "stems"`, `engine`, `tier`, `aspect`, `fps`, `size`, `audio_path`, `beats`, `window`;
- `stems`: the split (`engine`, `path` of its stems.json, `hash`, `names`, `activity` file, `period`, `sliced_from`);
- `layers`: one a layer, with its settings and its own `folder` (`<job>/layers/<stem>/`), `record` (a complete
  Simple record, `layers/<stem>/simple/simple.json`, which the timeline and the re-cut use as for any cut), `video`
  (the layer's own cut, `layers/<stem>/xenoform.mp4`, with the song, so it can be watched alone), `shots`, `morphs`,
  `stills`, `silent_s`, `drops_kept`, `guardrails`;
- `composite`: `order` (bottom to top), `blends`, `prominence`, `solo`, `ground`, `curve_source` ("activity"),
  `curves` (`composite/curves.json`: each layer's activity a frame for this cut), `fps`, `size`, `frames`, `audio`,
  `sha256` of the file it made, `alpha_mean`;
- `lead` and, with a lead, the `sections` it made; `pacing.line`; `recuts`, `composites`.

The composite is rebuilt from the layer files and the curves alone: the same record makes the same file, byte for
byte (`stems_composite.build`; the bitexact flags, the encoder's threads pinned, no metadata).

## Prominence and blend

**Alpha.** A layer's alpha a frame is `prominence x activity(stem)`, so the layer breathes with its stem: it comes up
within a beat of the stem coming in and fades over two beats when it stops. A layer that is the **only** one active is
drawn opaque: its alpha rises toward 1 by how alone it is,
`alpha = a + (1 - a) x activity x product(1 - activity of every other layer)` with `a = prominence x activity`. So one
stem playing alone is never a dim picture over black, and where two stems play at once they share the frame by
prominence. (The plan's "the lowest opaque when it is the only one active", made continuous and given to any layer that
plays alone.)

**Order.** Bottom to top by prominence: the least prominent first, the most prominent on top (ties in the layers'
order). The ground is black; the bottom layer is laid over it at its alpha.

**Blend**, for each layer above the bottom, always at the layer's alpha:

| Blend | What it does | How |
|---|---|---|
| screen (default) | bright objects on black overlap without mud: both show, brighter where they meet | the layer premultiplied against black, then screen: `b + aL(1 - b)` |
| add | like screen, hotter: overlaps can clip to white | premultiplied against black, then addition: `b + aL` |
| lighten | the brighter of the two, pixel by pixel | premultiplied against black, then lighten: `max(b, aL)` |
| multiply | the layer darkens what is under it (a shadow layer) | premultiplied against white, then multiply: `b(1 - a(1 - L))` |
| normal | the layer covers what is under it by its alpha | overlay: `b(1 - a) + aL` |

The alpha reaches ffmpeg as a 1x1 gray8 rawvideo stream at the cut's fps (one byte a frame), scaled to the frame and
`alphamerge`d onto the layer.

**Changing them costs no render.** On the cut's screen the Layers block over the timeline has a prominence slider and
a blend for each layer; **Lay them again** (`POST /api/jobs/<id>/composite`) re-composites from the files and the curves
in seconds, no GPU and no re-cut. The order follows the new prominence.

## The desk

- **The Stems step** (Morph: Stems): Split stems with its progress (Demucs prints nothing the desk can read, so the bar is
  the measured rate: about 0.3 s a second of song on 8 cores), then a row a stem: its envelope drawn, On or Off,
  Objects or Clips, the vibe and "Chain row's pins" or a folder of clips, prominence, blend, Lead. Drums and other are on
  at first. Four layers at most.
- **The cut's screen**: the Layers block over the timeline, a row a layer (its stem's activity filled, its alpha dashed,
  prominence, blend), a tab a layer. The timeline shows the chosen layer's own shots; its edits (Hold, the order, the
  look, the joins) re-cut that layer alone (`POST /api/jobs/<id>/recut` with `layer`), then the layers are laid again.
  The knobs' Re-cut re-cuts every layer. Swap, Re-render, Generate here and Dream act on one cut and are not offered on
  a layer yet.
- Render at Final from a Stems prototype keeps every layer's stills, as a plain Final keeps its chain.

## Routes

- `POST /api/stems/split` `{"audio_id"}` or `{"path"}`, optional `engine`: starts (or finds) the split and its
  envelopes; answers the status at once.
- `GET /api/stems/status?audio_id=` (or `path=`): `status` none / queued / running / done / error, `stage` split then
  envelopes, `progress` and `eta_s` while it runs, `stems` (a row a stem: `name`, `role`, `envelope`, `active`,
  `onsets`) when done. Registered before `GET /api/stems/<id>`.
- `POST /api/jobs/<id>/composite` `{"prominence": {stem: 0..1}, "blend": {stem: mode}}`: the re-composite.
- `POST /api/jobs/<id>/recut` takes `layer` (the timeline's maps are that layer's) and `prominence` / `blend`.
- `GET /api/videos/<id>/shots`: for a Stems cut, `mode: "stems"`, `layers` (each with its `lane`, `envelope`, `alpha`),
  `order`, `prominence`, `blends`; the top level is the first layer's lane.

## Tests

`tests/test_stems_mode.py`: the activity and onsets, the cache and a Length window's slice, the status, the compositor's
blends and alpha, the byte-for-byte rebuild, the re-composite, the layers' validation and the `[stems]` line, the drive,
the lead, a full two-layer Make on the mock engine (objects and objects on one vibe, and objects with clips), the re-cut
of one layer and of all, the routes and the desk. The split there is `stems.fake_split` (synthetic stems: drums with a
breakdown, an "other" that carries it), so Demucs never runs in the suite.
