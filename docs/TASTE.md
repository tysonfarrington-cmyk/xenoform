# The taste file

`configs/taste.json` holds Tys's standing rules for a music video as data: the subjects he never wants to see, the looks
that are kept but demoted, and the limits a cut keeps to. Every Make and every re-cut reads it; the code that reads it
is `src/xenoform/taste.py`. The rules come from his notes on the cuts and the montage between 25 and 30 October 2026
(the plan's research, `docs/MUSIC_VIDEO_PLAN.md` section 0), each written here in plain words with the day it came from.

## How it works

- **Read at every Make.** The file is read again whenever it changes (its time and size are checked), so an edit lands
  at the next Make or re-cut with no restart. `XENO_TASTE` points the app at another file.
- **No file, no rules.** A missing or broken file means no rules at all and one warning in the log, never an error.
  Every hook then does exactly what it did before the taste file existed: `tests/test_taste_absent.py` holds six Makes
  and a re-cut, and one composed file, to the mainline's cut byte for byte.
- **A rule** is one row: an `id`, a `kind`, its data, a one-line `reason` and the day it came from (`since`). A row
  without an id, a known kind or a reason is left out with a warning; `"off": true` switches one off.
- **What it never does.** It deletes nothing: a banned still stays in the library and a demoted vibe stays in the
  registry. It never overrides what you choose by hand: a pinned still, a shape you type on the idea line or in Your own
  shapes, your own images, and the timeline's per-shot and per-boundary picks are yours. Breathe stays off by default.
  Under Expert the clamps it would make to your settings become warnings and your values stay (except clips or objects,
  which is never mixed).
- **What it says.** Each rule that acts writes a `[taste]` line that names it. The guardrail's lines (what it changed in
  the Make's settings, and what the Make will do with them) and the Make's own lines (what the pick and the pickers did)
  show together under the cut's player on the desk, in the Guardrails notes. The record keeps them as its `taste` block
  (`simple/simple.json`: the file, the rules that fired, the lines); a re-cut writes its own as `taste_recut`.

## Where the rules act

| Hook | What the taste file does there |
|---|---|
| `guardrails.apply` (every Make body) | caps Chaos under Breathe, turns the sliced foreshadow into the trace, keeps clips and objects apart, and notes the rest: a demoted vibe, the quiet opener, a flash look, several effects, the kaleido, a banned noun typed on the line |
| `morph_pass.pick_stills` (every pick, the Chain row's preview too) | bans before the walk, and before a cut with no line chooses its realm; the natural and iconic families first; a second still of one object, a second instrument, a demoted still and a still off the palette to the back of the pool; a realm is sized on what the cut may draw from it, and one with fewer objects than the cut walks on into the next instead of repeating |
| `dense.long_song_chain`, the desk's count and clock | count the pool as the pick will use it, so a pool the bans shrink plans fewer morphs rather than repeat a still; a Stems layer counts it without the stills and objects the layers before it took |
| `stills.nouns_for`, `stills.family_nouns`, `stills.family_for_cut` | a grow never grows a banned noun or family; the family weight steers the cut's family and the grow |
| `boundary_fx.pick` | wipes at most a quarter of the handoffs, the strobe only at full heat, never the kind just used |
| `transitions_fx.guard` | a premium transition never follows itself |
| `beatfx.resolve_dance_preset` and the house look | a flash look resolves to the calm look before the first drop, the house look's opening flash to its VJ preset |
| `dense.shape_shots` (a Make and a re-cut) | the opener at the quiet Intensity, the looks before the first drop, the effects one at a time and off living things |
| `dense.foreshadow_mode` | no slices |
| the knobs (`taste.cap_macros`) | Chaos capped under Breathe, in the Make and the re-cut |
| `batch` (Variations by vibe) | no vibe twice, no demoted vibe after the one you chose |
| `dense.recut_from_cache` | goes through the same helpers, so a timeline re-cut keeps the same rules |
| `stems_mode.run` (the Stems mode) | every layer is a cut of its own through `guardrails.apply` and the Make, so each hook above acts inside each layer; the Make's notes carry each layer's lines, named by its stem (`[taste] drums layer: ...`) |

## The rules

Banned subjects (`kind: subject`): a still whose noun holds one of the words, as whole words (`cup` never matches
`cupola`), is never picked by the app; `except` spares a phrase that shares a word (a pitcher plant is a plant), and
`head: true` reads only what the noun is, not what it has (a dragon skull with curling horns is a skull).

| Rule | What it keeps out | Why | Since |
|---|---|---|---|
| `no-cups-or-jugs` | cups, teacups, mugs, jugs, pitchers | Plain household things to morph; the first montage opened on two of them and they fell flat. | 29 Oct |
| `no-wheels` | every wheel: steering, ship, valve, ferris, spinning, a tyre | Wheels went on the veto list after the first montage. | 29 Oct |
| `no-acoustic-guitar` | the acoustic guitar | The plainest object of the first montage's run of instruments. | 29 Oct |
| `no-wig-helmet-hay` | a wig (and the golden fleece, which the None vibe renders as one), helmets, hay | The None vibe read Greek myths literally and the objects were dull. | 30 Oct |
| `no-lava-dinosaurs` | dinosaurs, their skulls, bones and eggs | The one stretch of the montage he did not like, and not for the first time. | 30 Oct |
| `no-pirates` | the pirate run: hats, galleons, cutlasses, pistols, cannons, a ship in a bottle | The run had no link to the song. | 30 Oct |
| `no-parrots` | parrots | It rendered wrong. | 30 Oct |
| `no-binoculars` | binoculars, and the spyglass that renders as them | No context, and it held the screen too long. | 30 Oct |
| `no-cartoon-crabs` | crabs | It came out like a cartoon, twice in one stretch. | 30 Oct |
| `no-random-landmarks` | the Taj Mahal and famous buildings like it | A landmark dropped into a chain is dull and out of place; the moai and Stonehenge stayed in the montage. | 30 Oct |
| `no-sphinx-or-snake` | the sphinx, the snake, the rest of the neon Egypt set | He did not want the look at all; the scarab stays, it is a favourite. | 30 Oct |
| `no-plain-horn` | a horn (the ram's golden horns) | It turned up at random among the chrome relics and read as plain. | 30 Oct |
| `no-plain-lightning-bolt` | a plain lightning bolt | Also at random among the chrome relics. | 30 Oct |
| `no-black-heart-or-dna` | the DNA helix, the anatomical (black glass) heart | Unpleasant to watch, and the heart unattractive. | 30 Oct |
| `no-hat-or-clock` | hats (not the wizard's), clocks | Generic objects with nothing symbolic about them, in the gold stretch. | 30 Oct |

A banned family (`kind: family`): `no-vessels-family` keeps the whole cups-and-jugs family of `configs/subjects.json`
(teapots, kettles, shakers, glasses, vases) out of the picks and the grows: plain household vessels are generic in any
vibe (29 Oct, and the shaker and kettle a None cut gave when its pins were missed on 30 Oct).

A run (`kind: run`): `no-musical-run` lets one instrument into a cut at most, whatever its family (the musical
instruments, and a guitar or a piano in the iconic family): pianos into guitars had no reason to be in the song (29 Oct).

Demoted looks (`kind: look`): kept, never deleted, and said.

| Rule | What it does | Why | Since |
|---|---|---|---|
| `wet-paint-weak` | a note when the vibe is chosen; it is already off the featured cards (`configs/vibes.json`) | One of the weakest vibes, its colour scheme does not work. | 29 Oct |
| `pink-odd-machine` | a note when the vibe is chosen; never featured | He does not want the pink odd-machine or its theme. | 29 Oct |
| `plain-marble-chess` | chess pieces go to the back of a porcelain-marble cut | Plain marble chess was dull. | 30 Oct |
| `no-film-clips` | a note on a clips cut drawn from the free film pack | Black-and-white film does not react to the music; the montage dropped it. | 30 Oct |
| `no-kaleido-on-living` | a shot that morphs a living thing (a fish, a bird, an insect) plays another chosen effect, or none, instead of the kaleido | Overused, and on the fish it flattened them into a pattern. | 29 Oct |

Limits (`kind: limit`):

| Rule | What it does | Why | Since |
|---|---|---|---|
| `breathe-chaos-cap` | under Breathe, Chaos is at most 0.5 (the knob itself, so the orbit swing and the wobble follow) | Past it the kick wobble and the orbit swing read as shaky hand-held camera work; the montage capped it there. | 30 Oct |
| `quiet-opener` | the opening passage (up to the first drop, and 20 s at most) plays no hotter than the knobs at Intensity 0.6 would shape it | The opening is the hook and should be calm and consistent; the natural opener ran at 0.6 or under. | 30 Oct |
| `no-flash-before-drop` | before the cut's first drop a flash look (cyan flash, negative rush) plays the cool echo instead, and the house look's opening flash its VJ preset; a cut with no drop keeps its opener calm | White flashes are rare accents; the first flash look arrives with the first drop. | 30 Oct |
| `no-slices` | the sliced foreshadow becomes the trace | The slices draw bars, part of the bar transition he tired of. | 30 Oct |
| `no-kind-twice` | the handoff kinds and the premium transitions never take the kind just used | The same handoff again and again made the bars repetitive. | 30 Oct |
| `wipes-a-quarter` | at most a quarter of a cut's handoffs are wipes | The strip wipe was overused; the montage kept it under a quarter. | 30 Oct |
| `strobe-at-full-heat` | the strobe cut only on a boundary at full heat: the main drop | The loudest handoff there is belongs to the biggest moment. | 30 Oct |
| `one-effect` | the cut's effects take turns, one a passage (or one a stretch on a cut with no passages), never two on one shot | Effects are optional and sparing; the montage never stacked two. | 28 Oct |
| `no-object-twice` | two stills of one object count as a repeat: the second goes to the back, the pool is counted without it, and a realm with fewer objects than the cut walks on into the next (31 Oct: a default ten-morph cut of liquid gold drew a cosmos of nine stills and showed the orb and the mobius twice) | No image repeats in a cut. | 25 Oct |
| `no-vibe-twice` | a batch of variations (and the song plan, when it comes) never uses one vibe twice | Nothing shown twice in a montage. | 29 Oct |
| `clips-or-objects` | an object cut takes no clips and a clips cut no stills, under Expert too; in Stems mode the rule holds within a layer, and an objects layer may overlap a clips layer (the plan's decision 10, 31 Oct) | A film clip dissolving into a still read as two videos stitched together. | 28 Oct |
| `one-palette` | a still off the vibe's palette goes to the back of the pool: on a neutral vibe (black glass) a colourful still, else a still whose hues do not overlap the vibe's own stills by 30 percent; vibes of many colours (None, botanical, the primaries, the rainbows) are left alone | A pink rose blooming among black glass flowers made the opener uneven. | 30 Oct |

The family weight (`kind: weight`): `natural-first` weighs each family of `configs/subjects.json` (sea creatures,
living things and insects 3, birds and flowers 2.5, shells, the heavens, high fantasy and the surreal 2, down to 0.5
for machine parts, retro tech and the like). A cut with no idea line draws on the realms whose families weigh 1.5 or
more on average first (creatures before machines and the home), the heavier families leading inside a realm; a vibe's
own family for the cut and its grows are weighed the same way. A family the idea line names still leads: the weight
orders what the app chooses, not what you ask for. Natural subjects worked best in the montage, and an object should
carry a symbol (30 Oct).

## Adding a rule

1. Open `configs/taste.json` and add a row to `rules`. Give it an `id` (lowercase, with dashes), a `kind`, its data,
   a `reason` in one line and the day it came from in `since` (`2026-11-02`).
2. Pick the kind:
   - a subject: `{"id": "no-umbrellas", "kind": "subject", "words": ["umbrella", "parasol"], "reason": "...", "since": "..."}`;
     add `"except": ["..."]` for a phrase that shares a word, `"head": true` when only the noun's head counts;
   - a family: `{"kind": "family", "families": ["toys-and-games"], ...}` (the ids are the keys of `configs/subjects.json`);
   - a run: `{"kind": "run", "families": [...], "words": [...], "max": 1, ...}`;
   - a demoted look: `{"kind": "look", "vibe": "risograph", "demote": "note", ...}` for a note on a vibe, `"demote":
     "stills"` with `words` to send those stills of the vibe to the back;
   - the family weight: change a number in `natural-first`'s `weights`, or `first_at` (lower it to let more realms in).
3. A limit's numbers are data (`max`, `share`, `heat`, `seconds`, `min_overlap`): change them in place. A new kind of
   limit needs code in `taste.py` and a hook; the hooks above are where to look.
4. Make a Draft: the cut's Guardrails notes say which rules fired and what they did. `tests/test_taste_file.py` checks
   every row has an id, a kind, its data and a reason; run it with the suite.

To switch the whole file off, move it aside or point `XENO_TASTE` at no file: the cut is then the mainline's.
