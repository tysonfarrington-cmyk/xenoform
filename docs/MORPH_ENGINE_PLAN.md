# Morph engine first: the plan to the deadline, 28 October 2026

Tys, after a Final with the idea line "car rally race" (job 8923522f): "I think it would make more sense to have the app make
music videos ... but keep that separated from the morph engine." Then, on time: "we should probably perfect the morph engine
part. The app is called Xenoform, that's the main feature really, so let's make sure we nail that down, and perhaps expand some of
its features: morph types, transitions, effects, audio-reactiveness. Everything else should probably be hidden behind a drop-down
tab and be 'work in progress'."

This page is that plan. It was made by reading the code behind the desk (`ui_static/app.js`, `morph_pass.py`, `transitions_fx.py`,
`boundary_fx.py`, `dance_fx.py`, `beatfx.py`, `idea.py`, `footage.py`, `scene_edit.py`) and the rally test's own files. Nothing was
rendered for it. Line numbers are from commit ece1da0 on `contest-rc2`.

**The deadline:** Tys's own margin is Fri 30 Oct 9 pm AEDT (the form closes Sat 31 Oct 3 am). The demo video under 2:00 still has to
be cut, and a 12 s Final takes about 2 hours on the 3080 Ti, so features freeze on **Thu 29 Oct 9 pm** and the night after is
for the demo's Finals.

---

## 1. What the rally test showed

The idea line can only choose *which objects are morphed*. "car rally race" read as one new shape ("car rally race") plus the
catalogue family "vehicles and craft", so the chain was: a car silhouette on black, a hot air balloon, a sailboat, then the vibe's
usual orb, nautilus, lotus, torus knot, jellyfish, crystal, feather, ribbon and DNA helix. The car is on screen for under half a
second of the first morph (`simple/final00.mp4`). That is the right behaviour for a morph engine and the wrong one for a video about
a race, which is why the footage-first music video maker is the later project (section 5), not this one.

## 2. The morph engine today

| Part | What it has | Where |
|---|---|---|
| Morph | One prompt for every morph of a run: "one single sculptural object slowly melts and flows into another" (or its scene variant). Every morph is a melt. | `morph_pass.prompt_for` (morph_pass.py:444), `SCENE_OPENINGS` |
| Stills | 29 vibes, a shipped pool, Grow (Z-Image Turbo, about 6 s a still), your own shapes, scenes, your own images leading the chain | `stills.py`, the Library and Chain rows |
| Models | Draft: LTX 0.9.5 at 320x576 (about 35 s a morph). Final: LTX-2.3 22B distilled fp8 plus a 4x upscale (about 12.7 min a morph measured). An LTX-2.5 22B distilled int8 transformer is installed and unused by the desk. | `dense.py`, `final_tier.py`, `morph_pass.LTX25_FILES` |
| Transitions | 17 kinds in `transitions_fx` (one GPU: scene-morph; 16 CPU: flow-morph, liquid-melt, luma-wipe, stutter-cut, tape-stop, datamosh, chroma-split, zoom-through, black-hold, cut, match-cut, flow-carry, depth-parallax, lens-breath, chrome-refract, echo-trail) and 4 boundary kinds (smear, strobe cut, strip/iris wipe, chromatic rip) | `transitions_fx.py`, `boundary_fx.py` |
| Effects | 6 Looks (warm-leak, cool-echo, noir-glow, bloom-rush, negative-rush, cyan-flash); beat FX (kick pulse, edge flash, bloom, loudness lift); foreshadow; subject orbit; end card | `dance_fx.PRESETS`, `beatfx.py` |
| Audio | Beat grid, drop, sections; the kick scales the frame, transients light the edges, loudness drives exposure; stems drive the orbit, the boundary kinds, the negative pulse and the Look's trails | `beatfx.envelopes`, `stem_orbit`, `boundary_fx.STEM` |
| Knobs | Intensity, Speed, Chaos, Glow; feel words in the idea line set them | `idea.FEEL_WORDS` |
| Timeline | Per shot: hold or morph, Look, FX intensity, re-render this morph; per boundary: cut or morph and a kind; Generate here | `lane.py`, docs/TIMELINE.md |

The engine is broad on the CPU side (21 transition kinds, 6 Looks) and narrow at its centre: **every morph is the same melt**, and
the morph's own timing ignores the beat (the cut lands on the beat; the transformation inside the shot runs at the model's pace).

## 3. Work in progress: one drawer for everything that is not the engine

One collapsed drawer, **Work in progress**, at the bottom of Fine-tune (a `details` like Fine-tune itself, closed by default, its
state remembered). Each item keeps working exactly as now; it only moves, and its row says "Work in progress" and why in one line.
No mode switch (the one-desk rule from docs/WORKFLOW_AUDIT.md).

| Moves into Work in progress | Today | Why it is not the engine |
|---|---|---|
| Performer (Polly, MiniMax H3) | Fine-tune, `performerRow` (app.js:1087) | a person singing or drumming, not a morph |
| Your clips | Fine-tune, `ownRow` (app.js:1112) | footage cut in on the beat: the start of the music video maker |
| Paid cloud and cloud quality | Fine-tune, `cloudToggles` (app.js:2219) | the entry is Open Weights Only |
| Moves (Wan Animate dance) | side column link (app.js:917) | character animation |
| VJ mode and the MIDI controller | side column (app.js:918), Share row (app.js:723) | live performance |
| Connect an AI (agents, MCP) | the "..." menu and the line under Make (app.js:921) | for agents, not for making a cut |

Two behaviours change with it:
- **The idea line no longer switches Polly on.** A person in the line ("girl dancing") is still read, and the summary says Polly is
  in Work in progress; she renders only when switched on there (`idea.shape_state`).
- **Your own images stay in the engine.** Morphing between your own photos is the engine; only clips move. The Library row gets
  "Use your own images" (the image half of today's Your footage).

Stays where it is: Song, Vibe and the idea line, the knobs, Look, Foreshadow, Scenes, Fine-tune's Energy / Aspect / Length / Model /
Forms / Beat FX / Subject orbit / End card, the Library and Chain rows, Make, Variations, the timeline, Render whole song / Final,
Share (720p, hook, recipe, Download, Edit in Resolve).

## 4. The engine work, in order

Each item is one Owly commit with tests, made and checked on desk 47324, with a sheet or reel Tys can watch before it is called
done. GPU work waits for an idle ComfyUI queue. If time runs out, everything above the cut-off has landed whole.

**W. The Work in progress drawer** (section 3). JS and a little Python (`shape_state`). About 2 hours, no GPU.

**T. Desk truths** seen on the 27 Oct runs, small and all on the engine's own screens:
- the making screen's "The chain:" line shows the pre-Make preview, not the chain Make grows for the line (the moth, the street);
- the cut screen's Scenes row says Off when the idea line turned scenes on;
- the Final estimate says "roughly 90 s of GPU per second of video"; measured is about 600 (2:00:32 for the 12 s demo);
- `clockText` prints 120:32 for two hours.
About 1 hour, no GPU.

**E1. Morph styles: how A becomes B.** The biggest gap. Today one prompt makes every morph a melt. Add styles as prompt variants:
Melt (today), Shatter (breaks into shards that reassemble), Bloom (unfolds like a flower), Smoke (dissolves into smoke that
reforms), Ink (blooms like ink in water), Fold (folds like paper into the next), Spin (turns as it changes), Pour (pours like
liquid metal into the new shape).
1. Test sheet first: the 8 styles on the same two pairs at Draft (16 morphs, about 10 min of GPU), then the 3 best at Final on one
   pair (about 40 min), because LTX-2.3 follows a prompt better than 0.9.5. Tys watches the sheet; only the styles that read as
   different on film ship.
2. Wire: a **Morph** chip row beside Look (Auto: melt in verses, the loudest kept style on the drop and in builds); per shot on
   the timeline ("Re-render this morph as Shatter"); recorded in `simple.json`; Variations can vary the style; the recipe carries it.
3. Cost rule kept: the text encoder runs on the CPU, so a run encodes one prompt per style it uses (today's scene variants work the
   same way). Auto uses at most three a cut.
About 4 hours plus the GPU above.

**E2. Morphs that move on the beat.** Today the cut lands on the beat and the transformation inside the shot runs at the model's
pace. Measure each morph clip's change curve (frame-to-frame difference, CPU), then time-remap it so the object holds, changes
fastest on the kick and settles: a **Morph timing** row, Smooth (today), On the beat (the change peaks on beats), Snap (hold, then
the whole change in a beat on the downbeat; the drop snaps hardest). Works on cached morphs, so a re-cut applies it in about a
minute with no GPU. Proof: the change curve against the beat grid before and after, and a tile sheet. About 3 hours.

**E3. Transitions: grade the 21, add the best new ones.** First a reel of all 21 kinds on the same two shots, for Tys to mark
keep / cut / fix (the weak ones leave the Auto pick but stay on the timeline). Then 3 or 4 new CPU kinds, flash-safe by
`post_qa.flash_counts` like the strobe, from: shockwave (a ripple from the centre on the kick), mirror fold, slit-scan smear,
pixel sort, kaleido turn, light-leak burst. Tys picks from the reel. About 3 hours, no GPU.

**E4. Looks: grade the 6, add 2 or 3.** A reel of the 6 Looks on one cut; candidates: thermal, tape (VHS bleed and tracking on
the snare), chrome mono, infrared print. Tys picks. About 2 hours, no GPU.

**E5. Audio-reactiveness you can see and steer.** A **Reacts to** row (Drums, Bass, Vocals, Everything: which stem leads the beat FX,
the orbit and the boundary kinds) and a proof plot per cut (the song's envelopes under the effect curves they drove) on the cut's
screen, so "is it really reacting?" is answered by a picture. About 2 hours, no GPU.

**E6. A middle tier, only if it earns it.** Measure the installed LTX-2.5 22B distilled int8 (8 steps) on one pair against Draft and
Final. If a morph takes 3 minutes or less and is plainly sharper than Draft, it becomes **Standard** between them; if not, it is
dropped and this page says what was measured. About 1 hour plus 30 min of GPU, run while E2 to E4 are coded.

Suggested days: Wed evening W, T and the E1 test sheet (Tys watches it overnight); Thu E1 wiring, E2, the E3 and E4 reels for
Tys's picks, then the new kinds, E5, E6's measurement in a GPU gap; Thu 9 pm freeze; Thu night the demo's Finals; Fri the demo
video, README and CHANGELOG, and Tys pushes and submits.

## 4a. Progress

**28 Oct evening: W and T landed** (one Owly commit, `tests/test_wip_drawer.py`). The drawer is as section 3 says. Notes:
- Paid cloud's opt-in moved into the drawer with Cloud quality; the Beat overlay row stays in Fine-tune (it is an effect).
- The Final estimate is now the median of the Finals measured on this machine near the cut's length: 1:14:30 for the
  12 s demo here (six Finals measured), where the formula said about 16 min.

**E1 step 1: the style test sheet.** The 8 styles on two pairs at Draft, the same seed a pair, 3 s each, 21 s a morph
(16 morphs in about 6 minutes). Files: `Desktop\xeno_morph_styles_28oct\` (the reel plays each pair's eight side by side,
at speed and at half speed; a sheet a pair). "vs Melt" is the mean difference of the middle frames from Melt's (0 to
255); "motion" the mean change frame to frame.

| Style | soap orb > chameleon: vs Melt, motion | brain coral > dragonfly: vs Melt, motion | On film |
|---|---|---|---|
| Melt (today) | 0, 5.9 | 0, 5.9 | the liquid flow |
| Shatter | 13.3, 8.8 | 16.0, 7.5 | a burst of shards at a third of the way, clearly its own |
| Bloom | 9.0, 6.2 | 18.1, 5.6 | wings or petals unfolding (strong on the dragonfly, soft on the orb) |
| Spin | 15.8, 9.0 | 16.0, 7.9 | the most motion: a swirl and strands |
| Fold | 10.8, 8.3 | 16.4, 6.9 | flat planes and creases |
| Ink | 10.4, 5.1 | 13.8, 3.9 | wisps and strands, calm |
| Smoke | 13.0, 5.3 | 10.2, 5.8 | a haze under the object; reads close to Melt |
| Pour | 5.4, 5.7 | 12.3, 6.2 | the closest to Melt |

Recommendation: ship Shatter, Bloom, Spin and Fold beside Melt; Ink maybe; drop Smoke and Pour unless Final shows more.
Next in E1: Tys's pick, then the 3 best at Final on one pair (the Finals measured here run about 5 min of GPU a second
of video, so about 15 min each).

## 5. After the contest: the music video maker

The split Tys described stays the direction: a music video maker (song plus footage, an audio-reactive auto-edit) with the morph
engine used on its timeline as a transition between two shots, an insert over a span, or an overlay (the morphs are objects on
black, so a screen blend lays them over footage without masks). Much of it is in the repo but not used by the desk:
`footage.plan_edit` (a folder of clips cut on the beat, a scene-morph at section changes), `scene_edit.py` (renders that plan),
`footage.detect_scenes`, `footage.animate_graph` (LTX-2.3 image-to-video of a still, how "car rally race" could become rally
shots), `own_media.py`. Missing: a Make where footage is the base and morphs are guests, a Footage stage, a crop that follows
footage rather than a bright object on black, an overlay track. It starts from the Work in progress drawer's Your clips.

## 6. Questions for Tys

1. The eight morph styles in E1: any to drop, or your own to add?
2. Polly into Work in progress too? This plan says yes, as you said "everything else".
3. Anything in section 3's table you want kept on the main desk?
