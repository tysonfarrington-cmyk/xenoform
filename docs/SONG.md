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
2. **Draws a look a passage, by taste** (`song_plan.looks`). The vibe you chose takes the main drop, the moment the
   song is built on (or, when the body is a loved chain you applied, the passage that chain fits). The loved chains
   (`configs/chain_presets.json`) take the passages they fit: the opener (glow sea) the intro, the finale (the gold) the
   outro, the calm ones (smooth, Chaos 0.2 and under: the black glass rose, the smoke dragon) the grooves, the ones on
   the beat (Chaos 0.4 and over: the glass hand, the origami icons) the drops and builds; a chain keeps its own style,
   timing, effects, look and knobs, and the song's Shape. The rest take the featured vibes in their order, then the
   others that morph, the quiet ones (tags like organic, ink, smoke) on the quiet passages and the loud ones (neon,
   chrome, digital) on the drops and builds, a vibe whose library could not carry the passage passed over. Under the
   taste file no vibe comes twice and the demoted ones stay out. The intro and the outro are one passage each, one
   look each.
3. **Picks every window's objects** (`song_plan.objects`), the way its Make would pick them (the chain it plans, the
   pick under the taste file with natural or iconic families first, a fresh family on a drop run's first beat, one
   family a scene under full Breathe), the windows picking in the order the looks were drawn (the intro, the outro, the
   main drop, the other drops, then the longest passages) so the song's moments get first call on the library, each
   window leaving out every object the windows before it took and the objects a loved chain pins: **no object twice
   across passages**. A vibe's own line that names a family too small for its passage (cosmic's "star field") is
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
   only where both windows have picture); a window that plays a stretch shifted by whole beats is checked against its
   picture first (`check`, montage_check.py's test); the flash tame once over the whole when Breathe is on (each
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

Not yet: a Clips cut and a Stems cut are not made whole (each is one Make: Length Full song); no performer shots in a
whole song; a passage cut in two (Final) carries on from the still its first window landed on, so that still shows at
the join twice by design (the morph continues through it).

## The body keys

| Key | What it does |
|---|---|
| `song_morph_cap` | The whole song's morphs: `"auto"` (default) is the profile table's own count, passage by passage; a number caps the song, the planner spending it by role (the calm passages give theirs up first, a deep cap squeezes the drops' half-bar entries too). The desk's Fine-tune → Morphs row under Whole song. |
| `song_title` | The title on the last hit: `"Xenoform"` (the hand-made video's) by default, `""` for none, any other short line. |
| `breathe`, `drop_mode` | The Shape row, over the whole song (Breathe off by default, decision 2 of the plan). A loved chain's own Shape does not apply: its look does. |
| `quality_tier` | The tier every window renders on: `draft`, `fast`, `final` (12 morphs a Make: longer passages are two windows) or `cloud` (needs `cloud_final_ok`, the credits tick). |
| `vibe`, `idea`, `chain_pins` | The vibe you chose (the main drop's look), your line (every passage that is not a loved chain carries it), your pins (with the vibe, to its passage). |
| `song_passage` | Set by the plan on each window's body, never by hand: the window's stretch of the song plan (`plan`) and its place in the song (`offset`, `passage_start`, `passage_end`, `first_drop`, `opener`, `calm_seen`, `role_seen`, `opens`, `turn`, `song`). A re-cut of the window keeps it (`recut_state`). |
| `length_exact` | On a window's body: the desk trims at `length_start` as given (no snap back to a beat) with a hundredth of a second of fade. |

Routes: `POST /api/song` (`{"body": make body, "song_cap": ...}`: plan, record, queue; refuses a clips cut, a Stems cut,
a song under 20 s or without sections, and Cloud without the tick), `GET /api/song` (the songs on this desk),
`GET /api/song/<id>` (the view: status, n of m, the passage rendering, the passages with their looks, objects, jobs
and states, the estimate, the video once laid together), `POST /api/song/<id>/stop`, `/resume`, `/assemble`.
`GET /api/simple/options?...&whole_song=1[&song_cap=n]` adds the song's estimate (`song`) to the desk's options.

## The record

`work/ui/jobs/<song id>/song.json` (`song_run.new`, kept in step with the queue's batch by `song_run.sync`):

- `song`: the label, the audio id, the file, its length, tempo, drop, first drop and beats;
- `tier`, `aspect`, `breathe`, `drop_mode`, `cap`, `window_cap`, `taste` (whether the taste file was on), `plan` (the
  song's morphs, shots, the line "14 passages, 78 morphs; 5 drops, the main at 2:21", the steps, the bar phase, the
  beat), `title` (its text and the hit), `estimate` (every tier);
- `passages`: each with its role, span, heat and run, its morphs, its windows, its look (the vibe, the loved chain
  when it is one, why it was drawn, its line, pins, style, timing, effects, look and knobs, its seed) and its objects;
- `windows`: each with its passage and part, its span in the song, its morphs, the stills it morphs through, their
  nouns and families, its whole Make body, and from the queue its job, status, progress, attempts, failures and time;
- `batch`: the queue's batch (`work/ui/batches/<id>.json`), `status`;
- `assembly`, once laid together: the video, its length and size, every cut (where the plan wanted it, where it fell,
  why: "a passage starts: pinned on its beat", "the outgoing morph lands", "beat 1", "beat 3", "the nearest beat"),
  the loudness (the gain, the integrated loudness and true peak measured on the file), the tame (frames, flashes,
  tamed, kept), the title, the QA summary (flash frames, the worst 8 bars, off-beat cuts) and each window's job, song
  start, length and shift. An assembly that cannot run says why in `assembly.error` and writes nothing else.

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
- **Run a window again**: Resume after a failure or a stop queues every window not done; a window that renders again
  takes its morphs from the cache.
