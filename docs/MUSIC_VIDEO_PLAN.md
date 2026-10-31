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
| 5 | The whole-song music video: passages become window Makes, queued, assembled on the beat into one cut | song-plan | Opus 5.5 | song_plan.py, batch.py, dense.py, ui.py, app.js | 2 merged, Tys's go |

Each session works in its own worktree and branch cut from `contest-rc2`, commits as Owly, never pushes. The
orchestrator merges the branches into `contest-rc2` in the order 1 (with 0), 3, 4, then 2, then 5, running the
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

New names (checked free in the code): body keys `breathe` (true/false, default true) and `drop_mode`
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

## 8. Decisions for Tys

1. Repo size: shipping the on-screen stills and the loved clips adds about 70 MB to a 90 MB repo. Yes, or a
   release asset fetched by `scripts/fetch_library.py`?
2. Breathe on by default (the music-video shape; Breathe off is today's VJ cut), or off until judged?
3. Credits: the judged Cloud sets for backdrops and for Breathe, and later a whole song on Cloud. None is spent
   until he says so; Draft sheets come first and are free.
4. Wet paint and the pink odd-machine: hidden from the featured cards (still in the registry), or left as they are?

## 9. Working rules for every session

Own worktree and branch off `contest-rc2`; commit as `git -c user.name=Owly -c user.email=owly@local commit` with
the Co-Authored-By line; never push; never stash, reset or switch branches in the main checkout. Tests with the
main checkout's venv and `PYTHONPATH=<worktree>\src` (the editable install otherwise imports the main checkout).
A desk from a worktree runs on its own port (47327 and up); never restart ComfyUI (8188), the proxy (8189) or
Tys's desks 47320 and 47321. GPU work only when `GET http://127.0.0.1:8188/queue` is idle, Draft only, no Cloud,
no Final, `cloud_final_ok` never ticked. Git Bash heredocs mangle apostrophes and backslashes: write files with
the Write tool. Every change Tys will judge gets a tile sheet or a cut he can open, with full paths in the report.
