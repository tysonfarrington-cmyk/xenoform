# Whole song: the music video in passages

Stage 5 of `docs/MUSIC_VIDEO_PLAN.md` (section 7). What the hand-made Glitch Out montage of 29 Oct did by hand
(`docs/demo/tools/montage.py`: 30 s window cuts laid end to end by song time, a look a stretch, the title on the last
hit) is a Make: **Fine-tune → Length → Whole song**, then **Make the whole song**.

## What it does

1. **Plans the song as its passages** (`song_plan.py`). The pacing engine plans the whole song once
   (`pacing.song_plan` on the song's own analysis, with the Shape row's Breathe and Drops over the whole song): its
   passages (a run of one role: intro, calm, build, drop, release, outro; every drop run its own passage with its heat)
   and every shot in them at the profile table's beats a shot. Each passage is a **window Make** of at most 16 morphs on
   the chosen tier (Final's own cap is 12, so on Final a longer passage is two Makes, cut where a shot starts on a bar
   line). The song's total is the sum of its passages: the per-Make caps (Draft's 60 on a four-minute song, Cloud's 16 a
   Make) guard one Make and do not cap the song. Glitch Out at Breathe 1.0 is 14 passages and 78 morphs, at Breathe
   off 86.
2. **Draws a look a passage, by taste** (`song_plan.looks`). The vibe you chose owns the main drop run, the stretch
   the song is built on: the heaviest drop run by its heat times its length (`song_plan.main_run`, decided 1 Nov), not
   only the run the song's loudest moment opens, which keeps the drop's event (on ZedsDead v1 that run is 5.3 s at
   2:20 and the 23.7 s run after it is now the main); a tie goes to the run the drop opens. When the body is a loved
   chain you applied, that chain goes on the passage it fits instead. The loved chains
   (`configs/chain_presets.json`) take the passages they fit: the opener (glow sea) the intro, the finale (the gold) the
   outro, the calm ones (smooth, Chaos 0.2 and under: the black glass rose, the smoke dragon) the grooves, the ones on
   the beat (Chaos 0.4 and over: the glass hand, the origami icons) the drops and builds; a chain keeps its own style,
   timing, effects, look and knobs, and the song's Shape. The rest take the featured vibes in their order, then the
   others that morph, the quiet ones (tags like organic, ink, smoke) on the quiet passages and the loud ones (neon,
   chrome, digital) on the drops and builds, a vibe whose library could not carry the passage passed over. Under the
   taste file no vibe comes twice and the demoted ones stay out. The intro and the outro are one passage each, one
   look each.

   **Vibes** (Fine-tune, under Whole song: Auto, 1, 2, 3, 5, 8, All; the body key `song_vibes`) keeps the song to fewer
   vibes. Auto, the default, and All are the look a passage above (Tys, 1 Nov: fourteen vibes in a song is fine). A
   count N is at most N vibes (`song_plan.share`): every passage starts with a vibe of its own, then the cheapest move
   first, a calm passage shares another scene's vibe, then the outro, a release and the intro do, a build shares another
   build's; then the scenes and the builds take the vibe you chose; then a drop shares the drop look nearest its heat;
   the drops' looks go last. So **1** is the vibe you chose over the whole song; **2** is your vibe on the main drop and
   the rest of the song, and one more vibe drawn by taste on the other drops (the one with the best pull for a drop that
   shares fewest tags with yours: the contrast); **3** keeps two drop looks, and so on. A loved chain counts toward N:
   it takes a passage it fits and its vibe becomes its group's, and inside a group a loved chain of that vibe may take a
   passage it fits (the gold finale on the outro of a Liquid gold song). The other passages of a group take its vibe with
   your own settings. One vibe's library is smaller than a whole song (Ferrofluid holds 27 objects; ZedsDead v1 as a whole
   song shows 91 stills), so under a count a window whose vibe has run out lets objects come round again, as few as it needs, the ones
   the song has shown least and farthest away first (never another passage's pinned object); the record names them
   (`vibes.again`, and each window's `again`). The estimate does not change with Vibes: the morphs are the pacing's.
   **A hero object opens the main drop** (`song_plan.place_hero`). The main drop run's first shot lands on the hero of
   its look: the first object your Chain row pins (your pins then moved along so it sits there, in the order you set
   them), else the vibe's card object, the still of the object its picker card shows (`configs/vibe_heroes.json`: the
   ferrofluid phoenix, the black glass lotus, the radio telescope; read from the cut each card was made from and checked
   against the card by picture), else the vibe's first shipped still the taste file allows. It is pinned into that
   passage's first window at slot 1 (the first shot morphs from slot 0 into it on the drop's hit), no other passage
   shows it, and the record says so (`hero`: the still, its noun, why, the passage, the window, the slot). The desk's
   Fine-tune facts name it under Whole song.
3. **Picks every window's objects** (`song_plan.objects`), the way its Make would pick them (the chain it plans, the
   pick under the taste file with natural or iconic families first, a fresh family on a drop run's first beat, one
   family a scene under full Breathe), the windows picking in the order the looks were drawn (the intro, the outro, the
   main drop, the other drops, then the longest passages) so the song's moments get first call on the library, each
   window leaving out every object the windows before it took and the objects a loved chain pins: **no object twice
   across passages**. Two loved chains that pin one object (the glow sea's jellyfish and the black glass rose's, the
   smoke dragon's dragon and the gold finale's: with Breathe off their passages reach those stills) keep it in the
   chain that pins it first, the lower slot, and the other chain walks on to its next still; your own pins (the vibe's
   on the desk, the loved chain you chose) stay as you set them and keep the object (`song_plan._hold_pins`). A vibe's
   own line that names a family too small for its passage (cosmic's "star field") is
   dropped for that pick, which then walks on instead of lapping the family. Every slot is pinned in the window's body,
   so the Make renders exactly those stills and a re-run asks the morph cache for the very same morphs.
4. **Runs the windows through the Variations queue** (`batch.Runner`, `song_run.py`): one batch, `vary` "song", one
   window at a time on an idle desk and an idle ComfyUI queue (another desk's render goes first), owned by the desk
   that queued it. Each window is an ordinary Make of its passage (`length_s` and `length_start` with `length_exact`:
   the desk trims the song exactly at the passage, a hundredth of a second of fade, the song's own beats and roles
   beside it) whose body carries its stretch of the song plan and its place in the song (`song_passage`), so it cuts
   as the song's passage: the bar lines, the build's ramp into the drop after it, the drop run's event and the style it
   opens on, the calm passage's turn for an effect, the opener's quiet Intensity only in the song's opener, no flash
   look before the song's first drop. A window that fails goes again once at the back of the queue; **Resume** queues
   every window not done and keeps the done ones; **Stop** ends the whole. The morph cache answers a re-run's morphs
   (`morph_cache`): a morph rendered for a passage is never rendered again. A window never grows stills: the looks are
   drawn from the library as it is when the song is planned.
5. **Lays the passages together** (`song_assemble.py`), with no GPU, when the last window is done: every window's cut
   end to end by song time, so its picture plays over the very seconds it was made on and its beat FX land on the
   song's own hits; each cut on a beat of the song's grid (`place`, montage.py's rules: a passage's start is pinned on
   its beat; inside a passage cut in two the cut goes where the outgoing morph lands, then on beat 1, then on beat 3,
   only where both windows have picture); every window checked by its own picture frames, never its file's length
   (`check`, montage_check.py's test: a window's sound runs its passage's whole length even when its picture came out
   short), a picture short of its slot held on its last frame for the whole shortfall, up to the larger of a bar and
   the rest the window's own plan ends on plus a beat (a rest an older QA pass cut away is known from the plan: the
   ZedsDead intro's 49 frames, at 144 BPM where a bar is 40, are held), and the assembly refused past that, as a window
   really broken, with the window to make again; a window that plays a stretch shifted by whole beats must have the
   picture for it; the laid picture counted frame for frame against the song; the flash tame once over the whole when Breathe is on (each
   passage's rule, `pacing.flash_rules`); the title on the song's last hit (the last bar line with the song's loudest
   onset and level, at least 3 s from the end: 3:51 on Glitch Out, where the hand-made video put it), the shot dimmed
   under it; the song itself as the sound at -16 LUFS (a fixed gain from its measured loudness and a delay-compensated
   limiter at -3 dBFS, cutlib's); the picture faded over the last 1.2 s and the sound over 2.2; the QA pass once over the
   whole (`post_qa.run`).

The desk shows the estimate before anything runs (the morphs, the minutes on Draft, Fast Final, Final and Cloud Final,
and what Cloud would spend), the passages as they render (n of m, the one rendering, a track of the passages with their
looks and states, Stop and Resume), and when it is laid together the song in the player with its timeline: the
passages over the shots, each with its look and its window's job; a click opens the passage's own cut. Cloud Final
stays behind the usual credits tick: a whole song on Cloud is its windows' credits, the estimate says how many
(3.6 to 6 credits a morph: 464 for 128 morphs measured on 29 Oct, about 6 for a single 3 s morph).

Not yet: a Stems cut is not made whole (it is one Make: Length Full song); no performer shots in a whole song; a passage
cut in two (Final) carries on from the still its first window landed on, so that still shows at the join twice by
design (the morph continues through it).

## Clips

A whole song takes your clips (1 Nov): **Morph → Your clips** (a folder, the files dropped on the desk, or the free film
pack), then **Length → Whole song** and **Make the whole song**. It is the same maker, with one difference: a clips song
is one Make, not a window a passage.

1. **Planned by its passages** (`song_plan.clips_passages`). The song plan is the one an objects song gets (`whole`: the
   pacing engine over the whole song at the Shape row's Breathe and Drops), and its passages are the same; the clips cut
   is laid out on it as any clips cut is (`clip_cut.fit`, below), so each passage's morphs are the morphs the cut plays
   in it and the estimate is the cut's own.
2. **One window, the whole song** (`windows[0].whole`). Its body is a clips cut of your clips at Length Full song (the
   song as it is, no trim), carrying the whole song plan (`song_passage.plan`) and a context with no passage of its own
   (`whole`, no `passage_start`): the Make plays the song plan as planned and shapes it passage by passage, as any cut
   is shaped (`pacing.song_context` reads only a passage's window). One picture keeps every passage in sync by its own
   frames (the 1 Nov fix: nothing is laid end to end that could drift), and the morphs between passages are the cut's
   own: a passage opens on a morph, a hard cut on a drop's first beat, or a film carried on, as the music asks.
3. **One look**: the vibe you chose over your clips (its colour pass and the knobs as set), every passage
   (`song_plan.clips_look`); no vibe is drawn by taste and no object is picked: the cut shows your clips, each once
   under the taste file (`no-clip-twice`), the drops opening on a fresh film.
4. **Queued and laid together as any whole song**: one item through the Variations queue (an idle desk, an idle ComfyUI
   queue), then `song_assemble` lays that one cut with the title on the last hit, the flash tame under Breathe, the song
   at -16 LUFS, the QA once; the composite record (`simple/simple.json`, `source` "clips", the cut's own pacing block)
   is what the timeline, My videos and **Edit in Resolve** read (every shot its own clip on V1, named for your clip or the
   morph between two, the song on A1, a marker at each passage).

What a clips cut does with the pacing engine (`clip_cut`, the same for a clips song and a clips cut of any Length):

- **Every drop run opens on an event**: a cut on its first beat to a fresh film (none of the last three films shown), the
  punch and the stutter on that clip, its morphs on Snap (On the beat under heat 0.5), half-bar cuts only in a hot run's
  first two bars (heat 0.8 and over), a cut to a fresh film again at each eight-bar event of a long run, Chaos rising with
  its heat. Drops Auto, Max and off as for objects (off: one drop, no opening cut).
- **Rests are film playing, never a held frame**: a clip plays on over its rest; a morph that would rest lands on the
  incoming clip's first frame and hands over to it moving, so no morph sits on its soft last frame, and no morph plays
  slower than 0.6x (a longer one gives the rest of its time to the clip it lands on). Where that clip opens the next
  passage, it starts in this one and carries on into its own (`cont`: the same film, no cut), so every passage keeps
  the span the song gives it.
- **Under Breathe a calm passage holds one film** (the film the pack says a clip is from) for three or four bars a clip,
  cut on the bar, with no effects and no boundary kinds, Chaos 0.15; builds tighten from two bars a shot to one; the
  flash tame applies. A shot held two bars or longer plays a film that moves (`clip_cut.motion`): a film whose own
  picture barely moves (the Moon's face, Caligari's stairs, the city of tomorrow) held for bars reads as a frozen
  picture, so it goes to the short shots of the drops and builds, where it flashes by.
- **No shot under a bar** but in a hot drop run's first two bars: the plan's two-beat slivers fold into a neighbour.
- The record carries the pacing block (passages, runs, rests, the line), and the timeline's re-cut obeys the same rules.
  Breathe off with Drops off is the clips cut as it was made before, byte for byte (`tests/test_clips_legacy.py`).

## The body keys

| Key | What it does |
|---|---|
| `song_morph_cap` | The whole song's morphs: `"auto"` (default) is the profile table's own count, passage by passage; a number caps the song, the planner spending it by role (the calm passages give theirs up first, a deep cap squeezes the drops' half-bar entries too). The desk's Fine-tune → Morphs row under Whole song. |
| `song_title` | The title on the last hit: `"Xenoform"` (the hand-made video's) by default, `""` for none, any other short line. |
| `song_vibes` | How many vibes the song uses: `"auto"` (default) and `"all"` a look a passage, no vibe twice; a count from 1, at most that many (1: your vibe over the whole song; 2: yours on the main drop and the rest, one more on the other drops). The desk's Fine-tune → Vibes row under Whole song. A clips song is one look and ignores it. |
| `breathe`, `drop_mode` | The Shape row, over the whole song (Breathe off by default, decision 2 of the plan). A loved chain's own Shape does not apply: its look does. |
| `quality_tier` | The tier every window renders on: `draft`, `fast`, `final` (12 morphs a Make: longer passages are two windows) or `cloud` (needs `cloud_final_ok`, the credits tick). |
| `vibe`, `idea`, `chain_pins` | The vibe you chose (the main drop's look), your line (every passage that is not a loved chain carries it), your pins (with the vibe, to its passage). |
| `song_passage` | Set by the plan on each window's body, never by hand: the window's stretch of the song plan (`plan`) and its place in the song (`offset`, `passage_start`, `passage_end`, `first_drop`, `opener`, `calm_seen`, `role_seen`, `opens`, `turn`, `song`). A re-cut of the window keeps it (`recut_state`). |
| `length_exact` | On a window's body: the desk trims at `length_start` as given (no snap back to a beat) with a hundredth of a second of fade. |

Routes: `POST /api/song` (`{"body": make body, "song_cap": ...}`: plan, record, queue; a clips body is planned on its
clips, read from its folder or the files dropped; refuses a clips body with no clips, a Stems cut, a song under 20 s or
without sections, and Cloud without the tick), `GET /api/song` (the songs on this desk),
`GET /api/song/<id>` (the view: status, n of m, the passage rendering, the passages with their looks, objects, jobs
and states, the estimate, the video once laid together), `POST /api/song/<id>/stop`, `/resume`, `/assemble`.
`GET /api/simple/options?...&whole_song=1[&song_cap=n]` adds the song's estimate (`song`) to the desk's options;
`&source=clips&own_folder=...` (or `&own_id=...`, the files dropped) plans a clips song on those clips.

## The record

`work/ui/jobs/<song id>/song.json` (`song_run.new`, kept in step with the queue's batch by `song_run.sync`):

- `song`: the label, the audio id, the file, its length, tempo, drop, first drop and beats;
- `tier`, `aspect`, `breathe`, `drop_mode`, `cap`, `window_cap`, `taste` (whether the taste file was on), `plan` (the
  song's morphs, shots, the line "14 passages, 78 morphs; 5 drops, the main at 2:21", the steps, the bar phase, the
  beat), `title` (its text and the hit), `estimate` (every tier), `vibes` (what `song_vibes` asked: `choice` "auto",
  "all" or the count; the vibes drawn in song order and their `count`; `again`, the objects a vibe's library let come
  round), `hero` (the object the main drop opens on: `still`, `noun`, `why`, `vibe`, `passage`, `window`, `slot`, `at`);
- `passages`: each with its role, span, heat and run, its morphs, its windows, its look (the vibe, the loved chain
  when it is one, why it was drawn, its `group` under a Vibes count, its line, pins, style, timing, effects, look and
  knobs, its seed) and its objects;
- `windows`: each with its passage and part, its span in the song, its morphs, the stills it morphs through, their
  nouns and families, its whole Make body, and from the queue its job, status, progress, attempts, failures and time;
- `batch`: the queue's batch (`work/ui/batches/<id>.json`), `status`;
- `assembly`, once laid together: the video, its length and size, every cut (where the plan wanted it, where it fell,
  why: "a passage starts: pinned on its beat", "the outgoing morph lands", "beat 1", "beat 3", "the nearest beat"),
  the loudness (the gain, the integrated loudness and true peak measured on the file), the tame (frames, flashes,
  tamed, kept), the title, the QA summary (flash frames, the worst 8 bars, off-beat cuts) and each window's job, song
  start, picture length and frames, sound length, shift and the frames its last picture was held for
  (`padded_frames`). An assembly that cannot run says why in `assembly.error` and writes nothing else.

A window's QA (`post_qa`) leaves the rest it closes on alone: held frames at a cut's end are a hold by design, not lag
(they count neither as duplicates nor as a short freeze), and a lag fix that does run on a window holds its last
picture on to the picture's own end, so it keeps every frame it had. Before 1 Nov a fix could cut that rest away: a
ZedsDead intro came out 243 frames for its 292, and its song played 1.8 s early from there until it was laid again.

Beside it: `xenoform.mp4` (the song), `simple/simple.json` (`mode` "song": every shot in song time with its passage,
window, job and vibe, a window's first shot a hard cut; the timeline, Edit in Resolve and My videos read it, the
Resolve export marking every passage with its look), `meta.json` (My videos: "<song> · whole song") and `took.json`
(the windows' render time plus the assembly). The windows' own jobs are hidden from My videos (`meta.json` `part_of`)
and open from the song's timeline.

## Re-assemble, and re-cut one passage

- **Re-assemble** (no GPU): the song's result screen → **Lay it together again**, or `POST /api/song/<id>/assemble`.
  It reads every window's cut as it is now and lays the song again: the cuts, the tame, the title, the sound, the QA,
  the composite record. In Python: `song_assemble.assemble(work/ui/jobs/<id>, work/ui/jobs)`.
- **Re-cut one passage**: click the passage on the song's timeline (or in the list beside it) to open its own cut. Its
  timeline works as on any cut: the knobs and the Shape re-cut it with no GPU, a shot's morph re-renders, an object
  swaps, its handoffs change; the window keeps its place in the song (`recut_state.song_passage`). Then **Back to the
  whole song** and **Lay it together again**. The song itself does not re-cut as one cut (`POST /api/jobs/<song id>/recut`
  answers that it re-cuts a passage at a time).
- **Shift a stretch**: set `shift_beats` on a window in `song.json` (whole beats; positive plays a later stretch of the
  cut) and re-assemble. The window is checked first: a window is made exactly as long as its passage, so a shift only
  fits where the window has picture to spare, and one that runs out is refused with the times it asks for.
- **A window refused as short**: "window 2 (drop, passage 2) has 122 frames of picture for the 192 its slot plays: 70
  short (2.92 s), more than the 2.67 s it may be held on its last frame (a bar; its plan ends on no rest); make that
  passage again". The limit is a bar, or the rest the window's plan ends on and a beat when that is longer. Resume does not run a
  window that is done: make the whole song again from the desk. Every morph already rendered comes from the morph
  cache (the second plain Glitch Out rendered 6 of its 86), so it costs the windows' Makes around them, and a window's
  QA no longer cuts its rest away.
- **Run a window again**: Resume after a failure or a stop queues every window not done; a window that renders again
  takes its morphs from the cache.
