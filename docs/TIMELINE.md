# The timeline: a cut you edit shot by shot and boundary by boundary

Tys, 26 Oct: "the real power with this app would be if you can work directly on the timeline. Then you can choose the
effects and the transition types, if you want the scenes to morph or if you just want a normal transition. And then you
can dig down further into the actual scene and use the morph engine in the scene. For certain scenes you might want to
generate a 10 second clip quickly and insert it. Make everything audio reactive. All the settings and features that
we've come up with. I want something that I know how to use; at the moment it's a bit too convoluted and I don't feel
like I have enough control."

This page is the model behind that: what a timeline of a Xenoform cut is, what you can change on it, and how every
change maps onto the record a Make writes (`<job>/simple/simple.json`) and the desk's routes. The rule that makes it
usable: **every edit is a re-cut from the cached morphs, about 30 s on the CPU and no GPU, except two.** Re-rendering one
morph pair costs about a minute on a 12 GB card (Draft), and generating a run of new morphs costs about a minute a
morph. Nothing else touches ComfyUI. The one-flow plan in [WORKFLOW_AUDIT.md](WORKFLOW_AUDIT.md) (Song, Look, Prototype,
Render, Share) puts this timeline on the Prototype stage: the 30 s Draft the director makes is the default timeline, and
the editor is where you override it, never a blank canvas.

---

## 1. The model

### 1.1 Tracks

A cut is one picture track with two kinds of thing laid over it and the song under it.

| Track | What is on it | Where it comes from |
| --- | --- | --- |
| **Shots** | One block a shot. Each shot plays one morph clip (still A becoming still B) across its frames, cut on the beat, with its in-shot effects (punch, stutter, hold, skip, reverse), its beat FX and the house look. Between two shots sits a **boundary**. | `shots` / `plan_shots` and `clips` in the record (`dense.run_simple`); the lane's `shots` rows (`lane.build`) |
| **Inserts** | Bars over a run of shots that play one clip 1:1 instead of morphs: Polly's performer slots, your own clips, and a **generated run** (a short Draft chain made on the timeline, see 1.6). | `performer.slots`, `own.slots`, `inserts` in the record; the lane's `overlays` |
| **Song** | The passages (intro, calm, build, drop, drop_late, release, outro), the beats and the drop; under it the stems (drums, bass, vocals, other) that drive the look, the orbit, the foreshadow and the boundary kinds, with the per-stem gains of the Stems knob row. | `roles`, `beats`, `drop`, `stems_path`, `macros.stems`; the lane's `sections` |

The chain the shots walk is `stills`: n morphs over n + 1 distinct stills, each morph landing on the still the next one
leaves from. That is why a plain handoff is continuous: at the boundary between shot i and shot i + 1 both frames show
the same object. Every edit below keeps the chain's timing (the beat grid is the plan's); what changes is what plays
inside a shot and what happens at its edges.

### 1.2 Per shot

| Control | Choices | Cost | How it lands in the record |
| --- | --- | --- | --- |
| **The object or scene** it lands on | any still of the vibe's library (objects, then scenes) | GPU, two morphs (the existing swap) | `stills[slot]`, the two `clips` that touch the slot, a `swaps` log entry; `POST /api/jobs/{id}/swap` |
| **Play** | **Morph** (the clip plays whole: A becomes B) or **Hold** (the shot holds its start object, A, still; the orbit, the look, the beat FX and the foreshadow still run on it) | re-cut | `shot_overrides[i].play` = `"hold"`; the composed shot carries `hold: true` and `shot_indices` plays frame 0 throughout |
| **Look** | Auto (the vibe's look), Off, or one preset (warm-leak, cool-echo, noir-glow, bloom-rush, negative-rush, cyan-flash, ...) | re-cut | `shot_overrides[i].look`; the composed shot carries `dance_fx` (the resolved preset or `"off"`), which `beatfx.LookPass` uses for that shot instead of the cut's mode |
| **FX intensity** | 0 to 1 | re-cut | `shot_overrides[i].fx_intensity`; replaces the Intensity knob's value for that shot (`fx_intensity` on the composed shot, read by `guardrails.shot_fx` in `beatfx.beat_fx`) |
| **Re-render this morph** | another seed, another length (2 to 5 s of source), a prompt variant | GPU, one morph | `rerenders` log, `clips[i]` replaced, the shot's `render_s` / `speed` updated; `POST /api/jobs/{id}/rerender` (1.5) |
| **Morph** (style) | Melt, Shatter, Bloom, Spin or Fold: how this shot's object becomes the next (`xenoform.morph_style`, 28 Oct) | GPU, one morph | the same re-render with `style`; `morph_styles[i]` in the record, the shot's `style` on the lane |
| **Generate here** | a run of fresh morphs over this shot and the next ones, about 10 s | GPU, one morph a shot | `inserts` (1.6); `POST /api/jobs/{id}/insert` |

A shot under Polly, under your own clip or under a generated run has no object to swap and no morph to re-render; it
takes a look and an FX intensity like any shot, and it can be held.

### 1.3 Per boundary

A boundary is the join into shot i (i from 1). Two rows:

| Row | Choices | What it does |
| --- | --- | --- |
| **Handoff** | **Morph** (continuous, as now) or **Cut** (a plain beat cut) | A chain of morphs has no visible join: the morph before the boundary lands on the object the next one starts from. The only way to *see* a cut there is for the shot before it to stop morphing, so **Cut sets the shot before to Hold**: object A held through that shot, then a hard cut on the beat to object B, which the next shot morphs on from. Morph clears that hold. The two handles write one thing (`shot_overrides[i - 1].play`), so Hold on a shot and Cut on the boundary after it are the same edit seen from either side. |
| **Dress it** | **Auto** (the pickers decide, as now), **None** (a bare handoff), a **premium transition** (match-cut, flow-carry, depth-parallax, lens-breath, chrome-refract, echo-trail, black-hold; the core and classic kinds too, all CPU), or a **boundary kind** (smear, strobe cut, wipe, chromatic rip) | A premium transition takes the window centred on the join (half from the tail before it, half from the head after it; `beatfx.compose` and `transitions_fx.apply`). A boundary kind takes the same window inside the look pass, riding its stem (`boundary_fx`). A boundary never carries both: the kind wins, as it does today when Chaos assigns one (`boundary_fx.clear_premium`). |

Auto is what a Make does: the vibe's premium pick at each section boundary under the two-of-a-kind cap
(`dense.boundary_transitions`, `transitions_fx.guard`) and the boundary kinds Chaos and the section role pick
(`boundary_fx.pick`). A dressed boundary you chose by hand is kept as you chose it, whatever the pickers would have
done around it; the record notes when a hand-picked kind takes a premium type past the cap, it does not re-pick it.
Across a Cut (a held shot into the next) a premium transition blends two different objects, which is what those
transitions were built for; across a Morph handoff it dresses the landing.

### 1.4 What stays audio-reactive, and how the stems drive it

Nothing on the timeline is a static overlay. Every layer below reads the song at the frame it draws, from the stems
when the song was split (`stem_react.envelopes`, the record's `stems_path`) and from the mix when it was not
(`beatfx.mix_stem_env`), with the per-stem gains of the Stems row (`macros.stems`) on top:

| Layer | Stem it rides | Knob | Where |
| --- | --- | --- | --- |
| Beat FX (zoom, punch, bloom, the hit flash) | kick / transient / loudness of the mix | Intensity (and the per-shot FX intensity), Glow for the bloom | `beatfx.beat_fx`, `guardrails.shot_fx` |
| The look (grade, halation, echo, light leak, the negative pulse) | the role levels of all four stems | Speed (echo decay), Glow (halation), the per-stem gains; Auto follows the vibe's palette | `beatfx.LookPass`, `dance_fx.drive_from_env` |
| The orbit (the camera's drift round a held or morphing object) | bass and drums | Chaos (0 is a camera that does not move) | `stem_orbit.plan` |
| Foreshadow (the next object traced, negative, sliced or silhouetted in before its shot) | "other", else the beat | Intensity (the cap), Chaos (slices, jitter), Glow (the halo) | `foreshadow.plan`, `foreshadow.treat` |
| Boundary kinds | smear and strobe on the drums, the wipe on the bass, the rip on "other" (drums when that lane is flat) | Intensity (how hard), Chaos (how many, the strip count) | `boundary_fx.treat` |
| Premium transitions | the house transition intensity | the house profile | `transitions_fx.apply` |
| The cut itself (where the shots fall, the stutters, the holds, the punches) | the beat grid, the drop, the section roles | Energy, Speed (density), Chaos (punches and stutters) | `dense.dense_plan`, `story_plan`, `apply_macros` |

A held shot is the clearest case: with the morph stopped, what moves is the orbit on the bass, the look on the stems,
the beat FX on the kick and the next object arriving on "other" in its tail. A generated run is composed like any run
of shots, so it is as reactive as the rest of the cut, shot by shot.

### 1.5 Dig into a scene: the pair renderer

Every shot's morph is one LTX 0.9.5 render of two stills through the morph graph (`cloud_morph._local_clips`; the
swap already renders single pairs through it). Re-rendering one shot's morph takes the same path with three things you
can change:

- **Seed**: the cut rendered morph m with `seed + m`; a re-render takes the seed you give, else the next in a per-shot
  sequence (`seed + m + 1009 × tries`), so "again" never repeats.
- **Length**: 2 to 5 s of source (`render_s`). The shot's frames stay on the beat; a longer source plays slower across
  them (`speed` is recomputed), a shorter one faster.
- **Prompt variant**: Auto picks the prompt by the pair's kinds (`morph_pass.prompt_for(kinds=)`: object to object,
  scene to object, object to scene, scene to scene); the variants force one of those four, which is how a scene-shaped
  object can be asked to melt out wide or an object to form at the centre of a wide frame.

The pair is prepared as the cut prepared its stills (black ground, portrait re-lay; the record's `prep`), the new clip is
written under `simple/rerenders/<n>/morph<m>.mp4`, `clips[i]` points at it, the record logs it under `rerenders` (shot,
morph, seed, render_s, variant, seconds, time) and the cut re-composes through the re-cut path with the overrides as they
stand. A Final cut is refused (its morphs are LTX-2.3; make it again) as the swap refuses it. A shot under an insert has
no morph to re-render.

### 1.6 Generate 10 s here: a run of new morphs inserted as shots

"Generate here" on a shot takes that shot and the ones after it until about 10 s are covered (5, 10 or 15 s to choose,
whole shots, never past the end, never into Polly or an own clip) and renders a fresh Draft chain for that span: k shots
need k morphs over k + 1 stills. The stills come from `morph_pass.pick_stills` for the cut's vibe and idea, with the Chain
row's pins honoured slot by slot and the stills already in the cut left out, so the run brings new objects (or scenes)
in; each morph renders at its shot's `render_s` through the pair renderer, about a minute a morph on a 12 GB card.

The run goes into the cut the way an own clip does: it occupies a run of shots and the lane draws it as a bar over them
("Generated · k morphs"), but inside the run each shot keeps its own clip, its beat timing, its effects, its look and its
FX, so the run is cut to the beat like the rest of the cut rather than played as one 1:1 clip. In the record the shots of
the run carry `generated: {insert, index}` and no `morph` index (the chain's `stills` are untouched), `clips[i]` point at
`simple/inserts/<n>/morph<k>.mp4`, and `inserts` logs the run (first, last, start, end, seconds, stills, clips, pins,
seed, time). The join into the run's first shot and out of its last are hard cuts (the run's first still is not the
object the shot before it landed on), so the foreshadow layer and the boundary kinds treat them as they treat a cut into
Polly: the new picture is the clip arriving, and the object that left echoes out. A run can be dressed at either edge
like any boundary and its shots held like any shot. "Generate again" over the same span renders a new chain (a new
seed, the pins kept); a swap or a re-render inside a run is refused, since those act on the chain.

### 1.7 The default timeline

What a Make produces is the timeline with no overrides: `shot_overrides` and `boundary_overrides` empty, every shot
playing its morph, every boundary on Auto. A Simple cut today is exactly that, and stays so: the story plan's shots on
the beat, the vibe's premium pick at each section boundary, the boundary kinds Chaos picks, the vibe's look, the orbit,
the foreshadow, Polly and your clips where their slots fall. The timeline adds nothing to a Make; it is where you change
the result, and a Re-cut with new knobs keeps every timeline edit (the overrides live in the record, not in the request).

---

## 2. The record

`<job>/simple/simple.json`, written by `dense.run_simple` and updated in place by every edit. What the timeline reads
and writes, beside the keys the record already has:

| Key | Written by | Meaning |
| --- | --- | --- |
| `shots` | run_simple, every re-cut | the composed shots (after the knobs and the overrides): `start`, `end`, `frames`, `render_s`, `speed`, `effects`, `section`, `boundary`, `morph` (the chain morph it plays), `fx_intensity`, and when set `hold`, `dance_fx`, `performer` / `own` / `generated` |
| `plan_shots` | run_simple, the insert | the shots before the knobs: a re-cut starts from here. The insert marks its run here too, since every re-cut rebuilds `shots` from this list |
| `clips` | run_simple, swap, rerender, insert | one clip a shot, in shot order |
| `stills`, `scene_files`, `pins`, `pinned`, `swaps`, `prep` | run_simple, swap | the chain and how its stills were prepared (the swap, the rerender and the insert prepare theirs the same way) |
| `transitions`, `boundary_fx` | every re-cut | one entry a shot: the premium window into that shot, the boundary kind into that shot, after the overrides |
| `recut_state`, `macros` | every re-cut | the knobs, look, orbit, foreshadow, scenes as they stand |
| **`shot_overrides`** | the re-cut with overrides | `{"<i>": {"play": "hold" \| "morph", "look": "auto" \| "off" \| preset, "fx_intensity": 0..1}}`, only the keys set; an index past the cut or an empty entry is dropped |
| **`boundary_overrides`** | the re-cut with overrides | `{"<i>": {"fx": "auto" \| "none" \| premium kind \| boundary kind}}` for i from 1 |
| **`rerenders`** | the rerender | `[{"shot", "morph", "seed", "render_s", "variant", "clip", "seconds", "at"}]` |
| **`inserts`** | the insert | `[{"first", "last", "start", "end", "seconds", "stills", "clips", "pins", "seed", "at"}]` |
| `recuts` | every re-cut | a count; the desk's `video_version` moves with it |

A record from before this page (no override keys) is a default timeline. A record whose clips are gone cannot be
re-cut, as today.

---

## 3. The routes

| Route | Body | Cost | What it does |
| --- | --- | --- | --- |
| `GET /api/videos/{id}/shots` | | none | the timeline (`lane.build`): the shots with their object, slot, section, boundary, the transition or kind into them and their overrides (`hold`, `look`, `fx_intensity`), the overlays (Polly, own, generated), the sections, the chain, and the choices the panel offers (`transition_kinds`: id, label, note and group for every premium, core and boundary kind) |
| `POST /api/jobs/{id}/recut` | the knobs as today, plus `shot_overrides` and `boundary_overrides` (whole maps; each replaces the record's when present) | CPU, about 30 s | `dense.recut_from_cache`: re-composes from the cached clips with the knobs and the overrides, persists both |
| `POST /api/jobs/{id}/swap` | `slot`, `file` | GPU, two morphs | as today; the re-compose keeps the overrides |
| **`POST /api/jobs/{id}/rerender`** | `shot`; optional `seed`, `render_s` (2 to 5), `variant` (`auto`, `object`, `scene-object`, `object-scene`, `scene`) | GPU, one morph | `dense.rerender_morph` (1.5) |
| **`POST /api/jobs/{id}/insert`** | `first`; optional `seconds` (5, 10, 15; default 10), `pins` (`{"<k>": file}`), `seed` | GPU, one morph a shot | `dense.insert_generated` (1.6) |

All three GPU routes run as the swap runs: the job goes `running`, the making screen shows the progress, the desk polls
`GET /api/jobs/{id}`, `video_version` bumps when the re-compose lands, and a cut reopened after a desk restart is
registered from its folder. Two cuts rendering on the card at once stay refused (409).

---

## 4. How an edit becomes picture

The order inside `recut_from_cache`, which every GPU edit ends in:

1. Start from `plan_shots` and `clips`; apply the knobs (`apply_macros`: intensity, chaos, the stutters and punches).
2. **Shot overrides.** `play: hold` sets `hold: true` on the shot (and `cut_out: true`, so the layers know the join
   after it is a cut); `look` sets `dance_fx` on the shot to the resolved preset (`beatfx.resolve_dance_preset`, the
   cut's vibe); `fx_intensity` replaces the shot's value.
3. **The pickers run as today**: the premium picks at the section boundaries (story plan), the boundary kinds from the
   knobs, both deterministic for the same knobs and seed.
4. **Boundary overrides** are laid over them: `none` clears both lists at i; a premium kind sets `transitions[i]` (its
   window sized as the picker sizes it) and clears the kind; a boundary kind sets `boundary_fx[i]` (an entry shaped as
   `pick` shapes one: the window in beats, the stem, the wipe's iris or strips from the section) and clears the premium
   window; `auto` leaves the pickers' choice.
5. `beatfx.compose` with the shots, the clips, the lists and the look. Inside it: a held shot plays its first frame on
   every output frame (`shot_indices`), the foreshadow plan and the boundary plan read a held shot's "last" edge as its
   first frame and treat the join after it as a hard cut (as they do for Polly), and `LookPass` takes the shot's
   `dance_fx` when it has one.
6. The record is rewritten with the composed `shots`, the lists and the override maps; `xenoform.mp4` is replaced.

A re-render or an insert does its GPU work first (the pair or the run), rewrites `clips` and the shots it touched, then
runs the six steps. A swap keeps doing the same.

---

## 5. On the desk

The lane under the result player becomes the **Timeline** panel (the first slice):

- The overlays row (Polly, your clips, generated runs), the shots row, the boundary handles between the shots, and the
  song row with the passages under them. A click on a shot or a boundary seeks the player there and opens its drawer
  under the timeline; a shot that differs from the default timeline is marked.
- The **shot drawer**: Play (Morph / Hold), Look (the chips the Look row uses), FX intensity (a slider), then the GPU
  buttons: Swap the object (the existing picker), Re-render this morph (seed, length, variant), Generate here.
- The **boundary drawer**: Handoff (Morph / Cut), Dress it (Auto, None, the premium kinds, the boundary kinds), each
  with its one-line note.
- **Apply** re-cuts with the overrides as they stand (one request, the whole maps), **Reset the timeline** clears them.
  While the re-cut runs the making screen shows it; when it lands the player reloads and seeks to what you last clicked,
  so the composed cut previews the change. Before Apply, the stills animatic under the Chain row is still the instant
  preview of the chain; the timeline's edits are previewed by the re-cut itself, which is the cheap step.
- The second slice adds the GPU buttons' flows: Re-render and Generate here post their routes and the panel reloads
  when the job lands, as the swap does.

What is not on the timeline, on purpose: moving or trimming shots (the beat grid is the plan's; "Cut it to the beat"
with inserts and trims is the DIRECTION list's next step after the contest), the Final tier (a Final cut re-cuts and
takes overrides but its morphs are not re-rendered pair by pair), and the Director tools' storyboard (a different
render path; the timeline is the Simple cut's).
