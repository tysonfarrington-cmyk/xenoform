# Test drive, 25 October 2026

Tys asked for the test list to be run for him, with randomized variations, so the ones that worked best could become
defaults and guard rails. Everything below ran on the preview desk (port 47322) on commit 93332e1 and after, on the
3080 Ti, with ComfyUI untouched. Every video and a tile sheet (one tile a second) is in
`C:\Users\tyson\Desktop\xeno_tests_25oct\`. Three judges (a workflow of three agents with different lenses: the pour,
the picture, cleanliness) scored the eleven Phase A cuts from the tile sheets; their notes name tiles.

## What ran

| Step | What | Result |
|---|---|---|
| Grow cosmic by 36 | catalogue subjects, Z-Image Turbo | kept 30 of 36 in 244 s (5 soft, 1 backdrop, 1 cropped) |
| A1 | cosmic, 60 s, Draft, viscous, look auto | 188 s; 18 shots, 6 morphs over 6 objects; QA ok |
| Own shapes | wolf skull, paper lantern, glass octopus, brass key | kept 4 of 4 |
| A2 | cosmic, 30 s, after the own shapes | 162 s; the four typed shapes lead the chain; 1 cut off the beat |
| A3 | chrome, 30 s, your footage: one of Tys's films + an earlier cut + 4 images | 100 s; 2 clips cut in, 4 images lead; 2 glitch flags |
| V1 to V8 | eight 30 s or 15 s Draft cuts with randomized settings | all finished; see the table |
| B1 | cosmic, 30 s from 40 s, Performer 2 | 1234 s (Polly 1110 s); sings 8 s, dances 6 s; 2 cuts off the beat |
| B2 | cosmic, 20 s, Final tier | 3767 s (63 min); 12 morphs over 13 objects at 1080x1920; 4 row-artifact flags |
| Screens | showcase, Back, crumbs, reopen, VJ page | all as designed; a reopened cut now shows its Took line |
| Clock | a demo cut started from the screen | "Took 3:07 · morphs 2:32 · cut 0:29 · check 0:02" |
| Phase C | grow every vibe by 36 | see the end of this page |

MIDI was left for Tys, who has the controller.

## The variations

| Cut | Vibe | Song | Energy | Pace | Look | Aspect | Orbit | Beat FX | Took | Shots / morphs / objects | QA | Judges (pour / picture / clean) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V1 | liquid-gold | Glitch Out 30 s | dense | viscous | auto (warm-leak) | 9:16 | on | on | 100 s | 9 / 6 / 6 | ok | 4 / 3 / 3 |
| V2 | bioluminescent | Morphing Wobble 15 s | flow | viscous | cyan-flash | 16:9 | on | off | 44 s | 0 / none | judder 66 %, 36 freezes | 2 / 2 / 2 |
| V3 | risograph | Morphing Wobble 15 s | dense | tight | negative-rush | 16:9 | on | off | 110 s | 11 / 11 / 12 | 8 cuts off the beat; 38 hard flashes | 1 / 3 / 1 |
| V4 | iridescent-glass | Morphing Wobble 15 s | flow | viscous | noir-glow | 9:16 | on | on | 81 s | 3 / 3 / 4 | ok | 5 / 5 / 4 |
| V5 | neon-noir | Glitch Out 30 s | dense | viscous | auto (noir-glow) | 9:16 | on | on | 103 s | 9 / 6 / 6 | ok | 4 / 4 / 5 |
| V6 | chrome-mercury | Glitch Out 30 s | dense | tight | off | 9:16 | off | on | 88 s | 15 / 6 / 6 | 7 glitch flags, 3 freezes | 2 / 2 / 2 |
| V7 | cosmic | Glitch Out 30 s | dense | viscous | negative-rush | 16:9 | on | on | 90 s | 9 / 6 / 6 | ok | 3 / 2 / 2 |
| V8 | botanical | Glitch Out 30 s | dense | viscous | off | 9:16 | off | off | 98 s | 9 / 6 / 6 | judder 16 %, 8 freezes, 3 glitches | 3 / 4 / 3 |

Hard flashes are frame-to-frame mean-luma jumps over 40 of 255; every cut but V3 measured under 0.25 a second.

## What worked best

- **Viscous pace with the look on, in 9:16**: V4 (4.7 of 5) and V5 (4.3) are the two best cuts by every judge. Each
  morph plays across three to five seconds, the look unifies the stills, the frame is filled.
- **Look Auto**: it gave the most on-vibe grade (neon-noir's noir-glow). The per-vibe defaults are now in `vibes.json`.
- **Beat FX on**: the only setting that produced visible punches and a faster second half on the drop.
- **Own shapes**: typed subjects render in the vibe's material and lead the chain (A2, B1, B2, V7 all open on them).
- **Final tier**: crisp objects, no fallbacks; 63 minutes for 20 s is the price.

## What did not, and what changed because of it

1. **One morph held over fifteen seconds (V2).** Flow at 16:9 with Beat FX off on a short song went through the plain
   morph pass, not the Simple compose. A Simple cut now always takes the compose (`dense.wants_finishing`).
2. **The negative pulse as a strobe (V3, V7).** Negative-rush flips the frame's luma; on a bright risograph page that
   was 38 hard flashes in 15 s, on cosmic a lavender wash. The pulse now scales with the frame's darkness (a bright
   page flips a quarter as far), the QA pass counts hard flashes and reports more than one every two seconds, and
   the look chips say so on a bright vibe.
3. **Dead holds with the look and the orbit both off (V6, V8).** Identical adjacent frames read as freezes and the
   QA pass had to interpolate. With the look off the stem orbit now stays on, and the cut's notes say so.
4. **The object loop (A1, every 30 s cut).** A 60 s cut walked six objects three times in the same order, which every
   judge called. The morph budget is now one unique morph per five seconds of song (was ten): a 60 s cut shows
   twelve objects, a 30 s cut still six, for 12 to 20 s of GPU a morph. Tys's render-budget decision, made on this
   evidence; one constant (`dense.CLIP_SECONDS_PER`) reverts it.
5. **Scale not matched between stills (A2).** A typed octopus a quarter the size of the typed key made the morph a
   zoom. A still whose subject is under 45 % of the frame height is zoomed in on at ingest; seven of the 381 grown
   stills were.
6. **The countdown sat still between the server's stage ticks** ("about 2:40 left" for half a minute while the first
   morph rendered). The page now counts down the seconds since the last tick itself.
7. **A reopened cut showed no Took line.** It does now.

## Still open, with the evidence

- **Tight pace**: never produced a followable morph on any sheet; on a 15 s song it is a slideshow with 8 cuts off the
  beat. It stays as an option, not a default. The off-beat cuts are the half-bar plan against the 24 fps grid.
- **16:9**: the weaker frame for this engine's stills (objects small in the middle, blurred wings). 9:16 stays the
  default; the stills library renders at 1024x576, so 16:9 could be improved by generating 16:9 pools natively.
- **Own footage** (A3): clips are hard-cut in and played as they are, ungraded against the chrome stills, so every
  clip boundary is a luma jump. A half-second dissolve at each clip boundary and a luma match to the vibe would fix it;
  not done this week. The "cosmic snowflake in the chrome cut" the judges saw was one of my test clips, an earlier
  cosmic cut, not a pool leak.
- **Beat FX bloom on bright vibes** (V1 tiles 13 to 15 blow out to white): a soft clip on the highlights would hold it.
- **Final-tier handoffs** (B2): four row-artifact flags at the morph joins; worth a look at the join frames.
- **Every cut opens on a 2 to 4 s hold of its first still** before the first morph: a pre-roll cap would tighten it.

## Recommended defaults

| Setting | Default | Why |
|---|---|---|
| Pace | viscous | the only pace that let a morph play; Tys's A/B and all three judges |
| Look | auto | the per-vibe look; off only for photographic vibes, and then the orbit stays on |
| Beat FX | on | punches and a visible drop |
| Orbit | on | kept on whenever the look is off |
| Aspect | 9:16 | fills the frame; 16:9 leaves wings |
| Energy | dense | Flow is fine with Beat FX on (V4), but dense gives the drop its shape |
| Length | 30 s to test, 60 s to show | a 60 s cut now shows twelve objects |
| Negative-rush, cyan-flash | dark vibes only | softened automatically on bright ones |
| Performer | 2 shots when the song has a vocal window | 20 minutes a shot on this card |
| Final tier | once, for the showcase | about 3 minutes a morph |

## Phase C

Pending at the time of writing: every vibe grown by 36 (see `xenoform stills status`).
