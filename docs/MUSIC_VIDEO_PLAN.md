# Xenoform: the music-video plan

Written 31 Oct 2026, the day after the contest entry, from Tys's notes and four research passes over the sessions,
the transcripts, the code and the hand-made Glitch Out montage. Research files (this machine only, not in git):
`C:\Projects\xenoform-rc2\work\notes\research_31oct\` (`pipeline_map.md` with file:line hooks, `montage_rules.md`
and `montage_grammar.json`, `lessons_from_sessions.md` with Tys's words in order, `assets_inventory.md` and `.json`).

Tys's asks, in his words: save the assets from the videos and experiments into the app; handle the drops better
("more, faster, better morphs/effects/transitions during those periods"); a breathe mode so a music video is not
"a fancy VJ output" with "the intensity the whole time"; bake in his tastes and design decisions; fix the blank
backdrops ("morph an entire scene, not just a shape").

## 0. What the research found, and what it changes

1. **Section roles mostly do not run.** `dense.story_plan` is the only planner with roles (intro, calm, sustain,
   build, release, drop, drop_late, outro), but the `morph_density` guardrail rewrites Forms "auto" to a count for
   any Dense song above 90 BPM and under about 160 s, which sends the default 30 s prototype through `dense_plan`
   (no roles, no boundaries, no premium transitions, no section-aware style). Speed off 0.5, a hand-set Forms count
   or a feel word do the same. 45 of 256 job records are story plans. Drop handling and breathing both live in
   roles, so plan selection is fixed first or nothing else shows.
2. **"Drop" is one moment.** The plan honours one `drop_time`; a shot is role `drop` only for 8 bars after it;
   every later loud stretch is `drop_late`, cut every 8 beats like a verse. The analyser labels 38 % of Glitch Out
   "drop". `_merge_to` merges the shortest shots first, so denser drops are the first thing merged away under a
   cap. This is why the 1:50 build and the 1:59 drop "doesn't feel very audio reactive".
3. **Nothing taste-like reaches a Make.** lessons, critic, notes and review are Director-only; `lessons.json` is
   empty; most `fx_defaults` are unread. `guardrails.apply` is the one hook every Make body passes through (not the
   re-cut). The house ban on `wipe` never reaches boundary kinds, which is the repetitive "bar".
4. **The montage's grammar, measured** (34 looks, 87 renders, 11 rounds of notes): a look (vibe, objects, style,
   timing, effects, knobs) is held for whole bars and cut on the bar line; holds shrink as the song loudens (8 s in
   the quietest third, 6.5, 5.25 in the loudest); a new look opens 7 of 9 drops; timing smooth in intro and outro,
   on the beat in grooves, snap on drops; styles bloom and melt early, shatter on drops; one effect at a time,
   44 % of looks none, kaleido never; Chaos never over 0.5, 0.15 in the intro; no flash before the first drop; the
   outro one long gold look with the title on the last hit. Morph density itself barely varies (6.6 to 9.8 morphs
   per 8 bars). **Breathing is dynamics, not slow motion**: what rests is the look, the effects and the chaos, and a
   hero object is given airtime ("give the fish more time, linger with the effects like burn in").
5. **What he loved shares one setting**: smooth timing, none or one effect, Chaos 0.15 to 0.4, natural or iconic
   subjects, one palette. What drew the shake, bar, flash and mush notes was Chaos 0.9 to 1 with flash looks, wipes
   and feedback. The complaint that never stopped was boring, generic or random objects (12 messages, 5 days).
6. **Backdrops**: 35 of 36 still prompts say "seamless backdrop" and the morph prompt repeats "the object stays
   centred, macro product photography". Scenes exist end to end but are off by default, and on Final and Cloud a
   scene pair gets the object suffix ("one object centred, empty background"), a compressed guide and the black
   crush. There is no "object in a place" kind. "The blank background really kills these ones" is unsolved.
7. **Assets**: 415 stills are on screen in the published cuts and 376 exist only in git-ignored `work/ui/objects`;
   the loved morphs are located to job and shot (the rose into the lotus, 4ab7c8ca shot 1, and the kaleido fish,
   a2d64f77 shots 6-7, are in no published video); finished clips have no registry and no cache across jobs; 31
   identical requests were rendered twice (about 120 to 200 credits); a seed does not bring a clip back (10 of 30
   reruns matched), so clips are saved, not seeds.

## 1. The shape of the work

| Stage | What lands | Session | Model | Main files | After |
|---|---|---|---|---|---|
| 0 | Roles that are true: plan selection, per-run drops, a beat grid fallback, the window offset in the record | pacing-engine | Opus 5.5 | dense.py, guardrails.py, job_timing.py, beatfx.py (drop_time), ui.py (record), tests | now |
| 1 | The pacing engine: Breathe, the drop treatment, the build ramp, rests, the flash tame, the Shape row | pacing-engine | Opus 5.5 | dense.py, morph_style.py, morph_timing.py, boundary_fx.py, transitions_fx.py, beatfx.py, post_qa.py, app.js, lane.py, tests | with 0 |
| 3 | Backdrops: the Final/Cloud scene fixes, the `setting` kind (an object in a place), a Backdrop row, Draft sheets | backdrops | Opus 5.5 | stills.py, portrait.py, morph_pass.py (scene parts), cloud_final.py, final_tier.py, configs/still_prompts.json, configs/settings.json, app.js (one row), tests | now |
| 4 | Assets into the app: the stills, the loved clips, the showcase, example cuts and cards, chain presets, records, strips | assets-in | Sonnet 5.5 | ui_static/**, examples/**, configs/chain_presets.json, configs/clip_pack.json, scripts/**, CREDITS.md, docs/LICENCES.md, vibes.py, stills.py (catalogue dedupe), app.js (preset chips), tests | now |
| 2 | The taste file and its enforcement, chain presets as the carrier of what he loves, the morph cache, a stills import route | taste | Opus 5.5 | taste.py, configs/taste.json, guardrails.py, morph_pass.py, boundary_fx.py, beatfx.py, batch.py, morph_cache.py, ui.py, docs/TASTE.md | 1, 3 and 4 merged |
| 5 | The whole-song music video: passages become window Makes, queued, assembled on the beat into one cut | song-plan | Opus 5.5 | song_plan.py, song_assemble.py, batch.py, dense.py, ui.py, app.js, docs/SONG.md | landed 1 Nov as c74d844 |
| 6 | Stems mode: each stem its own layer, objects or clips, cut by the same planner on the stem's drive, composited by prominence; a Stems step | stems-mode | Opus 5.5 | stems.py, stems_mode.py, stems_composite.py, dense.py (dispatch), guardrails.py, ui.py, app.js, docs/STEMS.md, tests | now (Tys's ask of 31 Oct) |

Each session works in its own worktree and branch cut from `contest-rc2`, commits as Owly, never pushes. The
orchestrator merges the branches into `contest-rc2` as each reported (31 Oct: 3 as 91fd5d2, 4 as 39791dd, 1 with 0 as 99d4d95, each builder merging `contest-rc2` into its branch first; then Breathe round two aac4ec2, 6 as f226c5e, 2 as 8a3c12d), then 5, running the
whole suite after each merge. Tys's desks 47320 and 47321 are never restarted without his word.

## 2. Stage 0: roles that are true

- `dense.shots_for` keeps the story plan whenever the song is over `LONG_SONG_S` and has sections: a requested
  count or an off-centre Speed scales the story tables (`max_shots` is already a parameter) instead of switching to
  `dense_plan`. `dense_plan` stays for clips of 20 s and under and for Flow.
- The `morph_density` guardrail stops rewriting "auto" for a story plan: it hands the planner a budget
  (forms per 20 s) that the planner spends by role, drops first, calm last. Expert keeps the old behaviour.
- Every drop-labelled run from `_story_roles` becomes its own drop passage with `drop_run` (index) and `heat`
  (0..1 by level; the run at `beatfx.drop_time` is 1.0). `drop_late` is the tail of a long run (after 16 bars
  inside the same run), never "every drop after the first".
- A beatless stretch (Ambient's first 72 s) gets a tempo grid from the song's BPM so no shot is 72 s long.
- `plan_summary` and `job_timing.plan_for` plan with the same function as the Make, so the desk's count and clock
  match the cut.
- The record carries the window: `simple.json["window"] = {song_start, length_s}` (today the desk keeps
  `trimmed_from` only in memory); the Resolve export and any later assembly read it.
- `_merge_to` and `clip_plan` take a protected flag: drop and build shots are merged last; calm passages give up
  morphs first. The pool cap (pool - 1) and `grow_family_for_cut` are unchanged.

## 3. Stage 1: the pacing engine (Breathe and the drops)

One table drives both features. A **passage** is a run of one role, snapped to bar lines (beat 1), section
starts pinned. Each passage gets a **profile**: shot length in beats, timing mode, morph style, effects (at most
one), Look preset family, Chaos cap, Intensity, handoff-kind share, foreshadow mode, and a `rest`. Profiles are
written into the shots as per-shot fields the timeline already understands (`timing`, `fx_names`, `look`,
`fx_intensity`) plus the new ones below, so a re-cut can change them without a GPU.

New names (checked free in the code): body keys `breathe` (true/false; default false until Tys has judged the
sheets, his decision of 31 Oct) and `drop_mode`
("auto" default, "max", "off"); shot fields `heat` (0..1), `drop_run` (int), `rest` (beats the arrived object
dwells before the next shot). Never reuse `drop`, `effects`, `source`, `style`, `timing`, `energy`, `breath`.

Profile table, Breathe on (the numbers are the montage's, section 5 of `montage_rules.md`; a bar is 4 beats):

| Role | Shot (beats) | Timing | Style | Effects | Chaos cap | Intensity | Handoff kinds | Flash | Rest |
|---|---|---|---|---|---|---|---|---|---|
| intro | 4 to 8 (first shot 8) | smooth | bloom, melt | feedback or none | 0.15 | 0.4 to 0.6 | none | none | last shot 4 beats |
| calm, sustain | 4 | beat | melt, bloom | none, one in three passages slitscan or dither | 0.4 | 0.8 | plain 64 %, wipe at most 1 in 4, rip, smear | low | passage end 4 beats |
| build | 4, then 2 for the last 2 bars | beat, snap in the last bar | fold, bloom | dither | 0.4 | ramps 0.6 to 1.0 | none | rising | none |
| drop (heat h) | 4; 2 in the first 2 bars when h >= 0.8 | snap (beat when h < 0.5) | shatter, spin, bloom | dither, then feedback | 0.45 | 1.0 | 42 % of handoffs, wipe at most 1 in 4, strobe only at h = 1 and 2 s apart | capped | none |
| drop_late | 4 | beat | melt, spin | one | 0.4 | 0.9 | 36 % | capped | an 8-bar event (below) |
| release, breakdown | 4 to 8 | beat, smooth | melt | smear or dither | 0.4 | 0.9 | 36 % | capped | passage end 4 beats |
| outro | 4 to 8, one look | smooth | melt | none | 0.4 | 1.0 | none | none | title on the last hit |

Breathe off reproduces today's cut (the viscous table, one drop) so every existing record re-cuts the same.

The drop treatment (every drop run, scaled by `heat`; `drop_mode` "max" sets heat 1 on every run, "off" is today):
- The entry: the shot on the run's first beat gets punch 1.0 and the stutter, Snap timing, a Shatter (or Spin on
  the second run of the same look), the vibe's `drop` premium transition, a boundary kind, and a **new look**: a
  fresh object family or the idea's hero object pinned here, so the eye gets an event (7 of 9 montage drops opened
  on a new look). `transitions_fx.guard` counts its cap per passage, not per cut.
- The build before it ramps: the last four bars halve the shot length, Intensity rises to 1.0, dither comes in,
  foreshadow lead lengthens; when stems exist, build shot boundaries prefer `drum_strong` hits (`stem_react`).
- A long run does not go flat: every 8 bars of `drop_late` plants one event (a style change or a boundary kind).
- More morphs where it matters: the budget moves from calm passages to drops before any cap; drop shots are
  merged last.
- Faster morphs only where the music asks: 2-beat shots in the first two bars at heat 0.8 or more; nothing under
  2 beats; nothing played whole over 2 bars except intro and outro.

Rests ("let it breathe", "linger with the effects like burn in"): a shot with `rest` plays its morph over the first
part of the shot at no slower than 0.6x, then holds the arrived object for `rest` beats with the beat FX alive and,
in the intro and the grooves, the feedback trail; the join after a rest is a morph, not a hard cut (unlike the
timeline's Hold). Rests never exceed 8 beats and never sit in a drop. A 5 s morph clip is the ceiling, so a 2-bar
shot at 90 BPM (5.3 s) is the longest whole morph; longer shots are morph plus rest, never slow motion under 0.6x.

The flash tame: port `docs/demo/tools/deflash.py` into the compose path (a frame is a flash when its mean luma is
more than 6 levels above the darker of the 5 frames each side; lift the veil, lay 35 % back) as the last pass before
publish, on when Breathe is on; a per-role flash budget (intro 0) in the look pass; `post_qa` reports flash frames
per 8 bars by the same test.

UI: one **Shape** row beside Timing, in both knob blocks: `Breathe` (on/off) and `Drops` (auto / max / off); the
lane shows passages by role (it already colours sections) and a rest badge; the Make's report says what the plan
did ("3 drops, the main at 1:59; 6 passages; 4 rests").

Acceptance: the default 30 s prototype and a whole song both get roles; on Glitch Out the plan's table matches the
profile table (looks per minute 4 in the intro, 10 to 11 in drops; timing and style mix; handoff share; flash
frames per 8 bars after the tame under 45 everywhere and 0 in the intro); every drop run opens with an event;
`plan_summary` equals the plan; `breathe: false` reproduces the old cut on the mock engine; the suite is green;
a Draft tile sheet of today against Breathe on the 1:45 to 2:15 window and the 0:00 to 0:30 window of Glitch Out
(local Draft, free, only when the ComfyUI queue is idle) for Tys to look at.

## 4. Stage 2: the taste file

`configs/taste.json` (loaded by a new `taste.py`, mtime-cached, a missing or bad file means no rules) carries
Tys's standing rules as data, starting from Appendix 4 of `lessons_from_sessions.md`:
- banned subjects (cups, jugs, wheels, acoustic guitars and the "musical" run, wigs, helmets, hay, lava dinosaurs,
  pirates, parrots, binoculars, cartoon crabs, random landmarks, the sphinx and snake, a horn, a plain lightning
  bolt, the black heart and DNA helix, the gold hat and clock) and banned families;
- banned or demoted looks (wet paint, the pink odd-machine, plain marble chess, black-and-white film clips in a
  music video, kaleido on living things), as `featured: false` or a `taste` note on the vibe, never deleted;
- loved chains (the black glass rose into the lotus, the glow sea opener, the smoke dragon, the gold finale, origami
  noir, the glass hand) as `configs/chain_presets.json` entries, each a vibe, pins, style, timing, effects, look and
  knobs, offered as chips on the idea line and applied by one click;
- limits: Chaos cap 0.5 for Breathe, opener Intensity 0.6, no flash looks before the first drop, no `slices`
  foreshadow, no kind twice in a row, wipes at most a quarter of handoffs, no strobe under heat 1, one effect at
  a time, no object twice in a cut, no vibe twice in a song plan, clips and objects never mixed, natural or iconic
  subjects first (a family weight), one palette per cut.

Enforcement, three places and the re-cut: `guardrails.apply` (every Make body, with `[taste] ...` report lines the
desk shows), `morph_pass.pick_stills` (bans before the walk, loved chains as pins), and the kind pickers
(`boundary_fx.pick`, `beatfx.resolve_dance_preset`, `effects.names_of`, `transitions_fx.guard`, the house block);
`recut_from_cache` calls the same helpers. `docs/TASTE.md` explains each rule with the note it came from. Also in
this stage: a desk route over `stills.import_folder` (Library row: Import a folder), and `morph_cache.py`, a
content-addressed clip cache (`work/ui/morph_cache/<engine>/<key>.mp4` + sidecar; key = both guide stills' bytes,
the final prompt and negative, seed, frames, engine, graph, img_compression, end_strength, steps, cfg) consulted by
the Cloud, Final and Draft loops before a render and seeded from the jobs on disk.

## 5. Stage 3: backdrops

Track A, cheap and first: Final and Cloud scene pairs drop `portrait.PROMPT_SUFFIX`, keep the scene guide
uncompressed as Draft does, and skip the black crush for scenes; a Draft sheet of the five Cloud scene jobs' pairs
re-cut plain against fixed (no spend).

Track B, the real fix: a third still kind **`setting`**, an object standing in a place that suits the vibe (the gold
scarab on dusk dunes, the black glass rose on wet obsidian under mist, a neon noir lantern on a rain-slick street),
the object still the hero and readable. Per-vibe `setting` prefixes in `still_prompts.json`, a places list per vibe
in `configs/settings.json` (modelled on `scenes.json`), checks that skip `backdrop` and `cropped` like a scene,
`portrait.frame_portrait` and `black_stills` that leave settings alone, picking through a **Backdrop** row (plain /
places / scenes; "places" default for vibes that have them), morph prompts for setting pairs ("the object transforms
while the place slowly shifts with it"), and a kind-aware guard on the layers that assume a bright object on black
(foreshadow trace and silhouette, match-cut depth proxy, centroid crops fall back to plain handoffs). Objects get a
`fill` target so a setting's object is big ("maybe bigger objects"). Acceptance: grow, check, pick, prompt, record,
lane and re-cut all handle `setting` with tests; a Draft tile sheet per vibe for none, liquid-gold and neon-noir
with plain, setting and scene pairs side by side; a Cloud judged set only on Tys's word. Compositing a keyed object
over an evolving environment plate is noted as a later route (no matting library in the venv).

## 6. Stage 4: assets into the app

In rank order (`assets_inventory.md` section 1 has every path, job id, shot, pair, seed and prompt):
1. The stills on screen in the published cuts (about 367 after the banned-noun test and the taste flags, 31 MB)
   into `ui_static/objects/<vibe>/` with `objects.json` rows, `source` carrying model and seed, CREDITS lines;
   `stills.catalogue` de-duplicates a shipped copy against the same grown file.
2. The loved morphs' raw Cloud clips (40, 34 MB) into `examples/morphs/` with a manifest modelled on
   `examples/songs/songs.json`; the showcase reel rebuilt from them on Glitch Out's bars by
   `scripts/build_showcase.py`, its licence line corrected (LTX-2.3 Community License for the old reel); the gold
   outro as a 540p clip in `examples/clips/`.
3. The ten example cuts and three showcase cuts as 540p excerpts, one per vibe, with `examples/cuts/cuts.json`
   (id, vibe, song, recipe, seed, tier, morphs, credit, file), an `example` URL on `vibes._row`, shown on the vibe
   card and in the showcase aside; the 15 older vibe cards re-cut from those frames (bring `make_thumbs.py` into
   `scripts/vibe_objects/`).
4. `configs/chain_presets.json` with the loved chains (vibe, idea, pins by slot, style, timing, effects, look,
   foreshadow, knobs, seed, engine) and idea chips for them; a preset applies in one click. Stage 2 adds the rules.
5. Records: the published-slot chain records and the as-cut montage JSON into `docs/demo/records/`, the YouTube kit
   into `docs/demo/youtube/`, the pre-app provenance (prompts, seeds, models) into `scripts/vibe_objects/provenance/`
   and the six CREDITS rows that say "origin unrecorded" made true.
6. The 21 library strips that are all one orb-to-nautilus morph re-cut from each vibe's own Cloud clips (no GPU),
   `clip_pack.json` updated, the judges page regenerated.
Not shipped: the 235 MB masters, the 2.2 GB of raw clips, the partner-node reels (not open weights), the nine
uncredited Suno demos until renamed and credited. Repo growth to state in the report (about 70 MB expected).

## 7. Stage 5: the whole-song music video

What the montage did by hand becomes a Make: the passages of Stage 1, each a window Make of at most 16 morphs on
the chosen tier, queued one at a time through the Variations machinery (idle desk, idle queue, owner token), each
with its own look drawn by taste (no vibe twice, no object twice, natural or iconic first, the intro and outro
their one long looks), assembled on the song's beat grid as `montage.py` does (cut on beat 1 or 3, prefer the
outgoing morph's landing, pin section starts, a look may play a shifted stretch by whole beats, the window checked),
the title on the last hit, -16 LUFS. Draft for free prototyping of a whole song; Cloud only on Tys's word (Glitch
Out would be about 110 morphs, 400 to 650 credits). This is the stage that turns "a fancy VJ output" into a music
video, and it is built last because it stands on all the others.

## 7b. Stage 6: Stems mode (layers)

Tys's ask of 31 Oct, in his words: "a mode where i can apply a certain object/clip to a individual stems, and have
them maybe overlap. it would probably have to be a separate mode altogether, it should follow the same rules but
... opacity may have to be adjusted or that can be a setting for how dominant or prominent the stem is so if theres
two scenes/stems running for example you can see both".

What exists: `stems.py` splits a song with Demucs when installed (it is, in the venv, on CPU torch) and falls back
to the librosa band split; the CLI `stems` command writes `stems.json` and the stem wavs under
`work/ui/stems/<song hash>/`; `beatfx.mix_stem_env` and `dance_fx` already read a 4-role stem envelope for the
house look. None of this cuts picture per stem.

The mode. A third source beside Objects and Clips, chosen on the desk as a Stems step. The Make body carries
`mode: "stems"` and `layers`, a list of up to four, each `{stem, kind, vibe, pins | clips, prominence, blend, lead}`:
- `stem` is one of drums, bass, vocals, other (Demucs) or sub, bass, mid, high (the band split);
- `kind` is objects or clips; within a layer the two are never mixed (the standing rule); across layers both may
  run at once, overlapping, because that is what he asked for (decision 10);
- `prominence` 0 to 1 says how dominant the layer is; `blend` is screen (the default for objects on black ground,
  so two layers overlap without mud), normal, add, lighten or multiply; `lead` marks the layer whose stem sets the
  passages when the mix's own sections are not wanted (default: the mix's sections stay the passages).

Each layer is its own cut, made by the same planner on the stem's drive: the mix's sections remain the passages
(so Breathe, the drop runs and their heat are shared), but inside them the stem's own activity envelope and onsets
set the layer's shot density, its heat and its events. A stem that is silent in a passage gets no shots there and
its layer fades out; a stem that carries the drop gets the event. All the rules apply per layer: the taste file,
the kind guards, Breathe, the Shape row (one setting for all layers), no object twice across layers, one palette
per cut (layers default to one vibe; he may pick another per layer).

Opacity. A layer's alpha per frame is `prominence x activity(stem)`, the activity a smoothed, normalised RMS of the
stem (attack within a beat, release over two), so the layer breathes with its stem; layers are composited bottom
to top in prominence order, the lowest opaque when it is the only one active. A prominence slider re-composites
without a GPU, like a timeline re-cut.

Composition. Per layer the cut renders as today (Draft, Final or Cloud morphs, `recut_from_cache`), silent; then
`stems_composite.py` layers them with ffmpeg: for each layer a per-frame alpha stream (a 1x1 gray8 rawvideo at the
cut's fps from the alpha curve, scaled to the frame, `alphamerge`), `blend` or `overlay` in order, the song mixed
in once, the usual loudness. Deterministic from the record: the composite is rebuilt from the layer files and the
curves alone.

Splitting. A Split stems button runs Demucs (htdemucs, CPU, minutes) as a background job with progress, cached per
song hash; the band split is the fallback and the test engine. No GPU and no Comfy queue are involved in a split.
Tiers multiply by the number of layers: the estimate on the desk says so; Cloud stays behind Tys's word.

Desk and record. A Stems step: Split stems, then one row per stem (on or off, Objects or Clips, the vibe and pins
or the clips picker, prominence, blend, lead). The lane shows the layers stacked with each stem's envelope drawn;
the timeline gets a tab per layer with its own shot and boundary overrides. `simple.json` gains `mode`, `layers`
(each with its own record folder `layers/<stem>/`), `stems` (engine, path, hash) and `composite` (order, blends,
curve source). Files: `stems.py` (activity envelopes, the cache, status), new `stems_mode.py` (layers to bodies,
the run, the record) and `stems_composite.py`, `dense.py` (the dispatch in `run_simple` and the re-cut),
`guardrails.apply` (layer validation and the [stems] report line), `ui.py` (POST /api/stems/split, GET
/api/stems/status, the re-composite route), `app.js` (the step, the rows, the lane), `docs/STEMS.md`, tests
(`test_stems_mode.py`, with a fake split so Demucs never runs in the suite).

Acceptance: a two-layer Draft Make of Glitch Out 1:30 to 2:00 (drums on one vibe's objects, other or vocals on a
second vibe or on clips) whose tile sheet shows both layers visible where they overlap, the drums layer gone in
the breakdown, the event on the drop; a prominence change re-composited without a render; the record rebuilds the
same composite byte for byte; the suite green with the fake split.

## 8. Decisions for Tys

1. Repo size: decided 31 Oct, the stills and the loved clips ship in the repo itself (about 70 MB).
2. Breathe default: decided 31 Oct, off until Tys has judged the sheets; the drop treatment stays on ("auto").
3. Credits: the judged Cloud sets for backdrops and for Breathe, and later a whole song on Cloud. None is spent
   until he says so; Draft sheets come first and are free. The backdrops pick (31 Oct): the 6 scene pairs of job
   5b974778 (botanical 9:16, which both old faults hit), about 24 to 36 credits; the 8 pairs of 87678e34 would
   add 32 to 48; 44cc2f6e is skipped (its scenes come from an old idea line). Re-sending only the pairs needs a
   small script, since no route re-renders a Cloud cut.
4. Wet paint and the pink odd-machine: decided 31 Oct, off the featured cards, kept in the registry (the assets
   session lands it).
5. Places by themselves: the backdrops stage (merged 31 Oct as 91fd5d2) moves a vibe to Places once it holds 12
   settings (PLACES_DEFAULT_MIN); the builder chose 12 so a first grow of 8 does not turn a 30 s cut into five
   long morphs. No vibe ships settings yet, so default output is unchanged. Keep 12, or never switch by itself?
6. The 24 proof settings (8 each for none, liquid-gold and neon-noir, in the library folder under
   Desktop/xeno_backdrops_31oct): into the main library as the first places, or left out?
7. Assets: landed 31 Oct as 39791dd (1230 passed on its tree). The repo grew by about 90 MB net, not the 70
   estimated; the parts the plan asked for add to 90. Left out: the 235 MB masters (13 silent 540p excerpts stand
   in), the raw clips beyond the 38 loved ones and the strips, partner-node reels, the nine uncredited Suno demos,
   the overnight run media.
8. Assets questions: (a) wet-paint keeps its old strip, though a Cloud morph is ready for it (c7b83789 shot 1);
   lava-obsidian and odd-machine still show orb to nautilus; re-cut those three? (b) neon-night.jpg and poster.jpg
   stay origin unrecorded. (c) Nine stills held back for a look: cosmic rocket and ringed planet fail the banned
   noun test; Taj Mahal, three helmets, lightning bolt, piano puddle, hermit crab want a look (sheet: Desktop/xeno_assets_31oct/held_back_stills_sheet.jpg). (d) Comfy Cloud output
   terms are unchecked, and CREDITS and LICENCES say so. (e) The Loved chains chips are their own row under the
   idea line, not entries in ideas.json.
9. Pacing: landed 31 Oct as 99d4d95 (1294 passed on its tree). Breathe stays off by default; every preset carries
   Breathe off and Drops off, so a loved chain re-makes as it was cut (confirm). Flash frames in the worst 8 bars:
   1:45 window 142 today, 138 plain now, 39 Breathe; 0:00 window 151, 69, 13 with none in the intro. Open: may a
   whole song pass 60 Draft morphs (one per 4 s holds the density; builds run 14.3 looks a minute, grooves 4.9);
   the desk drop card says the big moment is 1:31 while the prototype window now centres on the main drop run at
   2:21 (make them agree). Left for later: a hero object pinned at drops (only the fresh family is), a title on
   the last hit, handoff kinds at 21 percent against the montage 36, a window that starts inside a drop run opens
   on an event. Proof: Desktop/xeno_pacing_31oct (two side by sides with the song, six Draft cuts with sheets,
   the whole song planned three ways, pacing_proof.py under docs/demo/tools).
10. Stems mode (Tys, 31 Oct): in Stems mode an objects layer and a clips layer may run at once and overlap; within
    one layer objects and clips stay unmixed. Breathe round two (Tys, 31 Oct): the first profile read too subtle
    in the side-by-sides; Breathe is to read as scenes (long holds, one look per calm passage, rests) against
    eventful drops, with a Breathe amount in the API; the proof is a stacked plain-over-Breathe passage that
    crosses groove, build, drop and release, never three small panels.
    Round two landed 31 Oct as aac4ec2 (1305 passed on its tree): breathe takes true or 0 to 1 (On is 1.0, 0.5 is
    round one); at full Breathe each calm passage holds one look from one family in shots of 3 to 4 bars (a morph
    of at most two bars, then a rest), no effects or wipes, Chaos 0.15, no flash; builds go from 2 bars to 1; drops
    as before; a Breathe Make may spend fewer morphs than its budget. Whole song: grooves 2.5 looks a minute, drops
    10.3 (4.1 times). Flash frames in the worst 8 bars, plain against Breathe: 146 to 24 (1:30 to 3:00), 136 to 38
    (0:30 to 2:00), 71 to 0 (0:00 to 0:30). Left: the camera orbit follows the cut's Chaos, not the shot's; one
    place per passage is one family only (settings not yet held); a round-one record re-cuts with the new looks but
    its old shot lengths. Proof: Desktop/xeno_pacing_31oct/round2 (stacked plain over Breathe with a rhythm strip).
11. Stems mode: landed 31 Oct as f226c5e (1352 passed on its tree, with Breathe round two merged in first). Decided by
    the orchestrator: a layer playing alone is opaque and prominence matters only where two stems play; defaults
    drums and other on, drums 0.8, the rest 0.6, screen; drive thresholds: silent under 0.12 mean and 0.3 peak,
    quiet under 0.4 (two quiet shots become one, at most 16 beats), a cut where the stem is out for a bar, the drop
    event stays on a layer whose stem plays the first beat at 0.35 or more; the idea line applies to every objects
    layer, no object twice across layers. For Tys: Lead means the lead stem's exits of 2 bars or more become
    release passages for every layer; is that what he meant? Not yet on a layer: swap, re-render, Generate here,
    Dream; Edit in Resolve exports the composite as one picture; the draft preview uses the cut's vibe even for
    clip layers. The doc is docs/STEMS_MODE.md (docs/stems.md already existed; Windows ignores case). Found on the
    way, handed to the taste stage: pick_stills with no idea line and a pool of 40 or more narrows to one realm of
    min(count, 8) stills, so a chain longer than the realm repeats objects (the orb and the mobius twice in a
    default liquid-gold cut); bioluminescent's default pick reaches the DNA helix.
12. Taste: landed 31 Oct as 8a3c12d (1507 passed on its tree): configs/taste.json and taste.py, the rules at
    guardrails.apply, pick_stills, the kind pickers and the re-cut with [taste] report lines, docs/TASTE.md, Import a
    folder (POST /api/stills/import), morph_cache.py with xenoform morph-cache seed|status, the realm-repeat fix
    (a cut with no line sizes each realm by what it may draw after the bans and walks on instead of lapping), and
    the rules inside each Stems layer. With no taste file a cut is the mainline byte for byte (fixture). Proof:
    Desktop/xeno_taste_31oct (None, same seed: 14 machines without, 14 sea creatures with; the cache made the same
    Make again with zero renders, 7 s for the morph stage against 490). For Tys: (a) no-wig-helmet-hay bans every
    helmet, samurai, astronaut and diving included; (b) no-vessels-family drops shipped stills: wine glass, perfume
    flask, liquid-gold amphora, mortar and pestle, teapot; (c) natural-first at 1.5 lets almost only the creatures
    realm open a cut and makes None all creatures; lower it and cosmos, dark fantasy and garden take turns; (d) the
    cache was only dry-run on work/ui (3170 clips, 183 repeated requests, 29 of them Cloud): xenoform morph-cache
    seed fills it; a Cloud Make with every morph cached runs without the key but still needs the credits tick.
    Kept as built: flash looks stand down before the first drop even when chosen; kaleido steps aside per shot on
    living things; an idea line naming a small family still repeats (28 Oct decision); one-palette skips None;
    quiet-opener bites above Intensity 0.6.
13. The whole song: landed 1 Nov as c74d844 (1547 passed on its tree): song_plan.py, song_run.py (POST /api/song
    through the Variations queue, resumable, stoppable), song_assemble.py (the beat grid as montage.py, the title on
    the last hit, tame and QA once, -16 LUFS, re-assemble with no GPU, song.json, Edit in Resolve), Whole song in
    the Length row with the estimate by tier, docs/SONG.md. Proof: Desktop/xeno_song_1nov, Glitch Out 3:58 at
    Draft 16:9, Neon noir on the main drop, 14 passages: Breathe 1.0 made 78 morphs in 23 minutes (23 flash frames
    in all); plain 86 morphs (242 flash frames, no tame). The 60-cap question is settled by the design: no Make over
    13 morphs. Cloud Final would be 281 to 468 credits for the Breathe song (the plan guessed 400 to 650); Final
    here about 10 hours; Fast Final under two. Decided by the builder, for Tys to confirm: two loved chains never
    pin one object in two passages (the lower slot keeps it); the title defaults to Xenoform (song_title, empty for
    none); windows are hidden from My videos and never grow stills; Clips and Stems are refused as a whole song.
    For Tys: (a) the chosen vibe takes only the main drop and no-vibe-twice spreads 14 vibes over one song,
    non-featured ones included (Low-poly, Lava obsidian): too many looks? (b) a loved chain keeps its own style,
    timing and effects in its passage, so the origami drop runs at 4.2 looks a minute against 8 to 12 elsewhere;
    (c) the whole-noun test lets near-repeats through (dragon and origami dragon, rose and enchanted rose, glove
    and helmet); (d) should a whole song always tame, even with Breathe off; (e) should the QA lag fix skip song
    windows (it reads Breathe rests as freezes and cut windows short before aeb1b41).
14. Demos of 1 Nov on the ZedsDead tracks (Desktop/xeno_demos_1nov: v1 Ferrofluid 16:9 with Breathe and plain, v2
    Molten gold 9:16 with Breathe, v2 from the film pack with Breathe and plain). Found: a whole song can drift out
    of sync by seconds when a window ends on a rest, because the window QA lag fix drops trailing held frames and
    the assembly pads at most 0.25 s and checks the sound length rather than the picture (demo 2 ran 1.8 s early
    from passage 2; repaired by hand; the fix is with the whole-song builder). The chosen vibe took the loudest
    5 s run while the 24 s run after it went to a drawn vibe: decided 1 Nov, the main drop run is the heaviest by
    heat times length and the chosen vibe owns it. Clips: the pacing engine reaches clips as the shot plan only
    (73 shots under Breathe against 89), with no effects and no tame, and the rests freeze film (51 s of still
    picture against 28); a clips cut renders a morph between clips (36 morphs, about 5 min). For Tys: Breathe and
    the drops for clips, or rests off for clips; repeats by head noun (five skulls, three dragons); the objects the
    rules do not see (pocket watch, chalice, plague mask, gauntlet and glove, heart, brain, femur, plain solids);
    a curated clip set rather than the whole pack in order; the title for these tracks; portrait by Fast Final
    (about an hour) for anything shared.
    Fixed 1 Nov as 8ebffd6: a window keeps the rest it ends on through QA; the assembly checks each window by its
    own picture frames and holds a short one on its last frame up to the larger of a bar and the planned rest plus
    a beat, refusing beyond that with a line that says the limit; the main drop run is the heaviest by heat times
    length and the chosen vibe owns it (ZedsDead v1: Ferrofluid moves to the 23.7 s run at 2:25). Still open: a
    rest inside a window is smoothed by the lag fix within a shot.
15. Clips pacing (Tys, 1 Nov: build it): Clips mode gets the whole pacing engine, with rests that never freeze film
    (a rest in clips is the clip playing on; a morph lands on the incoming clip's first frame), the taste rules for
    clips (no clip twice, black-and-white film as a note not a ban), and the whole-song maker takes clips. An Opus
    builder started 1 Nov from 346d766 (desk 47335; proof on ZedsDead v2 in Desktop/xeno_clips_1nov, stacked plain
    over Breathe with a still-picture count).
    Landed 1 Nov as 577ae08 (1590 passed on its tree): a paced clips cut follows the plan an object cut gets,
    rests play the film on, a morph lands on the incoming clip's first frame and never runs slower than 0.6x, one
    film per Breathe scene, drop runs open on a cut to a fresh film with punch and stutter and Snap, no shot under a
    bar outside a hot run's opening bars, a shot held two bars plays a film that moves; taste: no-clip-twice, the
    kaleido off living things (a word list shared with object stills), black-and-white measured and noted; a clips
    song is one Make of the whole song (one look, Final as one job, no Cloud path), laid together with the title.
    Proof on ZedsDead v2 (Desktop/xeno_clips_1nov): 42 shots both ways; frozen picture 5.3 s with Breathe against
    the demo's 55 s; flash frames 0 against 259 plain. For Tys: no clip twice against a 24-clip pack means long
    holds (a 15 s build on one clip, drops holding one film 9 to 11 s after their opening bars): keep it, let clips
    return in drops and builds after a gap, or a bigger or curated pack of about 40. Follow-up: Edit in Resolve
    names clip shots your clip, not the film. The estimate test now sees no measured cuts (d9644f2).
16. The curated film pack (Tys, 1 Nov: build a bigger curated clip pack, about 40 clips, colour and action first,
    so every cut the plan wants shows a clip once): version 2 of configs/film_pack.json from archive.org, NASA and
    other public-domain or CC0 sources only, each with its licence basis, at least 28 colour clips with six to
    eight quiet ones for calm passages and the strongest black-and-white kept for the drops, new fields colour,
    motion, living and mood that the cutter and the kaleido rule read; nothing of the footage in the repository.
    An Opus builder started 1 Nov from d9644f2 (desk 47336; proof in Desktop/xeno_pack_1nov: the pack contact
    sheet and ZedsDead v2 on the new pack stacked against the 24-pack cut).
    Tys, 1 Nov: The General (general_cannon, general_bridge) and Battleship Potemkin (potemkin_steps) are out of
    the pack for good (the bridge overused and too low in quality); a banned_clips list in the taste file keeps them out even where the old files remain.
17. Tys's answers of 1 Nov: Breathe stays off by default; fourteen vibes in a song is fine and a Vibes control
    lets a song use as few as one (song_vibes, follow-ups round); the taste calls stand as built (every helmet,
    the vessels family, natural-first, no head-noun merging); Lead in Stems mode means the lead instrument, like a
    lead synth; the title default stays Xenoform; the Cloud credits are approved for the two judged sets (the six
    botanical scene pairs, then ZedsDead v1 as a Breathe whole song with Ferrofluid, about 281 to 468 credits);
    contest-rc2 is pushed to the public main as each round lands; the follow-ups are resolved as recommended:
    vibes per song, Lead as the lead instrument, a hero object opening the main drop, the drop card agreeing with
    the planner, Resolve naming clip shots after the film, swap and re-render on Stems layers, rests inside a
    window kept through QA (an Opus builder started 1 Nov, desk 47337, proof in Desktop/xeno_followups_1nov);
    the morph cache was seeded on the mainline checkout.

## 9. Working rules for every session

Own worktree and branch off `contest-rc2`; commit as `git -c user.name=Owly -c user.email=owly@local commit` with
the Co-Authored-By line; never push; never stash, reset or switch branches in the main checkout. Tests with the
main checkout's venv and `PYTHONPATH=<worktree>\src` (the editable install otherwise imports the main checkout).
A desk from a worktree runs on its own port (47327 and up); never restart ComfyUI (8188), the proxy (8189) or
Tys's desks 47320 and 47321. GPU work only when `GET http://127.0.0.1:8188/queue` is idle, Draft only, no Cloud,
no Final, `cloud_final_ok` never ticked. Git Bash heredocs mangle apostrophes and backslashes: write files with
the Write tool. Every change Tys will judge gets a tile sheet or a cut he can open, with full paths in the report.
