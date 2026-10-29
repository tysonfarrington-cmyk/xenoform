# The walkthrough videos: script and shot list (draft, 29 Oct)

Two videos from one recording session: a **short** one for the contest (under 2:00, the Typeform's demo video) and a
**long** one that walks through every part of the desk. Both 1920x1080 (16:9), with a 1080x1920 cut of the short one for
the social post. Voice-over over the screen, the outputs played full frame, captions burned in, the repo URL and
#OpenSourceHiggsfield on the end card. Every number said on screen was measured on this machine (one RTX 3080 Ti, 12 GB).

## What the contest asks of the video

- **The contest page** (comfy.org/open-source-higgsfield, read 29 Oct) sets no length, format or voice rules. It judges
  the work, not the editing; the best demo shows the work in action and explains how it was built; an entry for Most
  Innovative must say in the video why it is new. Every entry is considered for Best Overall.
- **Our submission** (docs/CONTEST.md): the form takes a demo video under 2:00 by public link, the repo with its licence
  and setup instructions, and the URL of a public post tagged #OpenSourceHiggsfield that carries the video and the repo
  link. Categories claimed: Open Weights Only, and the LTX bonus (LTX as the core video model).
- So the short video must, inside 1:55: show the desk making and editing a cut, show real outputs, say how it is built
  (song analysis, ComfyUI graphs through the Comfy SDK, LTX on any card from 12 GB up, all open weights) and say what is new.
  It ends on the repo URL. The long one is for the README and the post's replies, with no limit.

## Short (1:59.0: the montage's first 24 s, then the walkthrough)

Every cut lands on a beat of Glitch Out (Tys's own track, the montage's song too); the voice reads one sentence at a
time with a breath between, and the screens play still and full frame. Rows with two sentences are read apart.

| Time | Picture | Voice |
| --- | --- | --- |
| 0:00 | The montage's opening: the black glass rose blooming into the lotus, then on the drop lava-obsidian dinosaurs, the deep-sea fish in their feedback trails, shadow-self magic, the free film pack, origami noir, Cyberspace 1995, neon noir; the title lands on the next drop | (the song alone) |
| 0:24 | The title | Xenoform turns a song into a music video where every beat is a transformation. |
| 0:30 | The Song step: the vibe grid, None picked | Drop in a song and pick a vibe, or None, the things just as they are. |
| 0:35 | The idea line: "underwater" grows its chips | Then say what it morphs through. A theme like underwater brings fifteen things of its own. |
| 0:42 | Make; the making screen, the chain, Cloud Final coming back three morphs at a time | Make plans the shots on the song's bars and beats, and renders a morph for every shot. |
| 0:48 | The result, full frame: None "underwater" on Cloud Final, made on the very seconds of the song under it | Every shot is one object turning into the next, cut to the song's own bars. |
| 0:54 | Neon noir, Spin on Snap (labelled) | Five ways to change, and the change can land right on the beat. |
| 0:59 | Cyberspace 1995, Kaleido, Feedback and Slit-scan (labelled) | Effects ride the kick and the loudness. |
| 1:03 | The timeline: picture tiles, the Look tab, a colour change, Apply, the re-cut | Then edit it like a timeline, shot by shot. Colour, effects, order and cuts, re-cut from the cached morphs with no GPU. |
| 1:13 | Morph > Your clips > Free film pack, then the clips cut: Metropolis, the Moon, The Lost World, the Odessa steps | Or morph film clips into each other: a free pack of public-domain films, or your own. |
| 1:23 | How it's built: song, plan, ComfyUI graphs, LTX morphs, the cut (each box on its sentence) | How it's built: the song is split into stems and bars. The plan becomes ComfyUI graphs, sent through the Comfy SDK. LTX renders every morph, on any card from 12 GB up, or on Comfy Cloud. All open weights, local by default. |
| 1:41 | What's new: the playhead over the timeline; the MCP panel | What's new: the edit comes from the music itself. Every shot is generated, and you change it like an editor, not a prompt box. An MCP server lets any AI drive it. |
| 1:55 | End card: github.com/tysonfarrington-cmyk/xenoform, #OpenSourceHiggsfield | Xenoform. Open source, on GitHub. |

The Model line (Draft, Fast Final, Final, Cloud Final) left the short for the intro's room under 2:00; the long keeps
it, and Comfy Cloud is named in How it's built.

## Long (about 7 minutes), chapters

1. **What it is** (0:30). The three cuts again; song in, music video out; the morph engine at its heart; what is new
   (the edit comes from the music, every shot generated, edited like a timeline).
2. **Song and vibe** (0:45). The bundled demo or your own song; the twelve vibes and None; what a vibe sets (the material and
   light of every object, the morph's motion, the colour, the transitions).
3. **What it morphs through** (1:00). Things, a theme, a place, a feel; the chips under the line; a theme's fifteen things;
   Make draws the new ones first. The library: grown on this GPU, checked, culled by eye.
4. **Make and the making screen** (0:40). The chain, the steps, the draft playing while it renders; Draft, Fast Final,
   Final, Cloud Final and where the time goes (the tooltip).
5. **The engine** (1:20). Morph styles; Timing (Smooth, On the beat, Snap); Effects; the Look; Foreshadow; Scenes; the
   knobs (Intensity, Speed, Chaos, Glow); every change applied in one re-cut.
6. **The timeline** (1:20). Picture tiles; the Shot, Look, Join and Regenerate tabs; move, duplicate, delete, move a cut;
   colour per shot; re-render one morph, Generate here, Dream here.
7. **Your clips** (0:40). Morph > Your clips; the busiest stretch of each clip; a morph from one clip into the next.
8. **Share** (0:30). A 720p share cut, the 15 s hook, Edit in Resolve (the folder opens, File › Import › Timeline),
   the recipe code; Variations for the night.
9. **Under the hood** (1:10; Tys, 29 Oct: the demo "is like a black box at the moment"). One Make's own files, the None
   "underwater" cut: the song's waveform with its 70 beats and the drop (features.json); the plan of 22 shots with their
   beat effects (simple.json); the chain of 23 stills, three drawn first for the line (chain.json); one morph from its two
   stills through the prompt that names them to the clip, rendered by LTX-2.5 through ComfyUI and the Comfy SDK; the
   re-timing, the effects and the cut; the job folder's files. `cards/underhood.html` is built from the job by
   `underhood.py`, the lines are `underhood_voice.json` (u1-u6, merged into the long copy after Share).
10. **How it's built: open weights, the Comfy SDK and MCP** (0:30). The models (LTX-2.5 for the Final, here or on Comfy
    Cloud) and their licences; every render through the Comfy SDK; the MCP server; Setup & models.

## How it gets made

1. **Lock the script** (this page): the short one's 238 words read in about 1:35 at 150 a minute, which leaves about
   15 s for the outputs to play with no voice over them.
2. **The voice**, from the locked script, one sentence a row (`scratchpad/wt/split_copy.py`), each read on its own so
   the voice stops between sentences, timed; the picture is cut to the read.
3. **The screen**: the desk in headless Edge at 1920x1080 driven over the DevTools protocol (Node's own WebSocket, no
   installs), each row a scripted action with its frames captured, on a desk with a quiet GPU so nothing stalls on
   camera. A finished cut is opened from its record rather than rendered on camera.
4. **The outputs**: the overnight Finals (after the Thursday 9 pm freeze), the clips cut and a None cut, played full
   frame where the voice talks about the result.
5. **The edit** with ffmpeg (`scratchpad/wt/cutlib.py`, `assemble.py`, `assemble_v.py`, `montage.py`): picture to the
   read, a breath before and after each scene and between its sentences, every scene ending on a beat of the bed,
   captions from the voice's timing, the bed under the voice and ducked, the end card; the montage cut by song time
   from renders made on the same song; then a check of the length (under 2:00), black frames and loudness.
6. **Tys uploads and posts** (YouTube, public or unlisted), puts the link in README.md, CONTEST.md and the post, and
   submits the form. Nothing is uploaded or posted by an agent.

## Made (29 Oct)

- **The voice** is Kokoro-82M (Apache 2.0, open weights, read on the CPU with kokoro-onnx), from the voice copies
  `short_voice.json` and `long_voice.json` (one line a shot; `say` is what the voice reads where it differs from the
  caption). "Xenoform" is read ZEE-no-form (espeak's own guess is ZEN-o-form). Every line is measured before it is
  used: no clipping, no long gap inside a line, and no ending that rises 15% or more over the line's own pitch (one
  line was reworded to land).
- **The screen** was recorded from a desk on this machine in headless Edge over the DevTools protocol at 1440x810, 4/3
  scale (1920x1080 frames), with a drawn cursor and highlights; the Make, the underwater chips and the timeline edit are
  real (a None "underwater" cut; racing was the first example, dropped: "you want to see cars driving not
  morphing"). Recording found the desk blinking on every click (fixed in
  f9eaa7e).
- **The short** (1:43 af_heart, 1:48 am_michael, 1:47 bm_george) and **the long** (6:52 in af_heart, ten chapters with
  labels) were rebuilt on the frozen app on 29 Oct (last at 9 am) and are in `Desktop\xeno_walkthrough_29oct`, with 720p
  review copies. Every desk shot was re-recorded on the final commit (the Make on camera is a Fast Final of the None
  "underwater" cut, b251df0c); captions are burned in from the voice copy; the music bed is Tys's Suno track
  XF_HipHop_BoomBap_01, ducked under the voice (looped under the long one); the mix is -16 LUFS.
- **The long one's chapters** (for the YouTube description, af_heart timing): 0:00 What it is · 0:20 Song and vibe ·
  0:54 What it morphs through · 1:37 Make · 2:17 The engine · 3:24 The timeline · 4:13 Your clips · 4:40 Share ·
  5:03 Under the hood · 6:13 How it's built.
- **The showcase cuts** (29 Oct, 7:40 am, Tys: "go ahead and render it"): three 30 s cuts made on Cloud Final through
  the desk like any Make, every morph LTX-2.5 on Comfy Cloud, 1080x1920, no Draft fallbacks: None "underwater" on
  XF_HipHop_BoomBap_01 (job 0c3864af, 16 morphs, 4:21), neon noir on XF_DnB_Liquid_01_v1 (e649e412, 9 morphs, 5:52)
  and liquid gold on XF_Ambient_01 (7cdc5b35, 12 morphs, 5:32); 37 morphs, and the Comfy Cloud dashboard went from
  11,924 credits (4 am) to 11,789 after them (135 credits, with the morning's guide experiments). They open the short
  (gold, the clips cut, neon) and the long, and the None cut is the short's result shot and the long's None example;
  the Model grid in the long gets a Cloud Final tile beside Draft, Fast Final and Final. The None cut's chain holds a
  seahorse pair (two seahorse stills, 7 to 12 s), so its shots start past it. The first attempt through the API ran the
  classic chunk render instead (the Make body needs `quality: "turbo"`, as the desk sends it); those three jobs
  (abdf7a0d, b599647d, 8057c0c0) spent nothing on Cloud and sit in desk 47326's My videos.
- **"Any card from 12 GB up"** (Tys, 29 Oct 9 am: the demo "can run on 12gb vram and up cards not just a 12gb"): the
  short's How it's built line, the long's l36 and the diagram's LTX box said "one 12 GB card"; they now say any card
  from 12 GB up (so does docs/CONTEST.md's Runs on row). Only those two lines were re-read (`kokoro-tts/reread_line.py`
  replaces one line's wav in a read and its seconds; the measures held: no rising end, one sample at the peak), the
  cards re-recorded with the cue moved from "card." to "gigabytes up.", and both cuts re-assembled.
- **The example cuts** (Tys, 29 Oct 9 am: "we have heaps of credits left so we should make a few example videos"):
  one 30 s Cloud Final cut for each of the other ten featured vibes, through the desk like any Make, on Tys's Suno
  instrumentals (`scratchpad/wt/examples.py`), in `Desktop\xeno_examples_29oct` with a 16-frame sheet each and
  `examples.json` (job, chain, time): Liquid chrome / Techno (dad92e3f), Porcelain & gold / Breakbeat (18dcd1a8),
  Deep-sea glow "underwater" / DnB v2 (d2f19f7a), Risograph / Hip-hop (00ac3e00), Iridescent glass / Synthwave v2
  (fbd103a4), Ink & paper / Riff Tool (d4ed04ab), Cyberspace 1995 / Psytrance (a56d1354), Wet paint / Bass (3991568a),
  Shadow self / Riff Korn (b4fd5b3f), Bloom timelapse / Ambient (ec770cb9). 128 morphs in 63 minutes, 5:02 to 7:32 a
  cut (a cut that grows fresh objects for its chain first is the slow end); the dashboard went 11,789 to 11,325
  credits (464, about 3.6 a morph). With the three showcase cuts that is one Cloud Final cut per vibe, for the post
  and the README once Tys uploads them. Seen on the sheets: bright vibes (porcelain, glass, ink, wet paint) show the
  boundary wipes as pale bands across the ground for a few frames, which the dark vibes hide.
- **The vibe thumbnails** (Tys: "update thumbnails for vibes") are now one frame from each vibe's Cloud Final cut
  (`scratchpad/wt/make_thumbs.py` with `picks_thumbs.json`: the centre square of the frame on the same frame blurred,
  1280x800 like before; the old files are in `scratchpad/wt/thumbs_old`). One judge a vibe picked the frame from the
  sheet (a fully formed object, a strong silhouette at 150 px), checked by eye. The README's two screenshots were
  retaken with them (`readme_shots.py`).
- **Every desk shot re-recorded** (Tys, 29 Oct 10 am: "Full re record, make sure it's high quality too and polished",
  then "you may as well use our credits as well"): `rerecord_all.sh` ran both recorders on desk 47326 with the new
  tiles, and the Make on camera is now a **Cloud Final** (job 566cc4c8, the None "underwater" cut, 16 morphs from
  Comfy Cloud in 3:42, so the making screen shows the real thing coming back three morphs at a time); the Model shot
  clicks through all four chips. Both cuts re-assembled (short 1:43 / 1:48 / 1:47, long 6:52), then checked
  (`qa_cut.py`): no black frames in the short, one 0.5 s black at the Under the hood card's start in the long, no
  frozen stretch beyond the held screens and the card's panels, -15.9 / -16.0 LUFS, true peak under -2.5 dBFS,
  contact sheets looked over. The Model grid's Fast Final tile keeps the 7 am Fast Final (b251df0c) so the four
  tiles stay what their labels say. The previous recording is in `scratchpad/wt/rec_prev`.
- **The clips segment, recut on the free film pack** (Tys, 29 Oct noon: "the nostufaru and the dr caligri clips arent
  the most interesting in the demo, and the scene sort of ends abruptly"). The segment is now a clips cut made on the
  pack as Setup & models makes it (`work/ui/film_pack`, 24 clips from 17 public-domain films, chosen from contact
  sheets of the full films): job 1d376198 on desk 47326, the hip hop beat, None, 16:9, Fast Final, 20 s, so the Machine-Man
  of Metropolis turns into the Moon's face from A Trip to the Moon, the Moon into Jekyll and Hyde, Steamboat Willie into
  the Odessa steps, then Apollo 11, Nosferatu rising and Keaton's cannon. The short's line reads "Or morph film clips into
  each other: a free pack of public-domain films, or your own" (re-read in all three voices), the desk shot clicks Your
  clips and then the new Free film pack button (the folder fills, the note names the pack), the cut plays about 7 s from
  its start and fades to black into the next screen (both assemblers have a `wide` picture with a `fade`; the old `one`
  showed a 9:16 cut on a blur). The long's Your clips chapter (l29 to l31, two lines reworded and re-read) shows the
  cut through, then replays its opening under the line that names those handoffs. Two of the pack's sources carry black
  bars baked into their 16:9 uploads (the Méliès and the Apollo files): the manifest marks a `crop` and they were remade
  before the Make. The short is 1:47 in af_heart (1:52 am_michael, 1:51 bm_george), the long 6:53, the 9:16 cut 1:47
  (the clips segment as the strip, the fade included). Checked (`qa_cut.py`): no black frame in the short beyond the
  9:16 end card's fade-in, the only frozen stretches the held screens and the Under the hood panels, -15.9 / -16.0 LUFS,
  true peak under -3 dBFS, the contact sheets and the clips segment's frames looked over.
- **The glow-up and the montage** (Tys, 29 Oct 3 pm: "a bit of a shake and zoom on the app parts which we shouldnt
  do", "the script doesnt seem to stop for pauses", "a 1 min montage intro of different styles and themes ... push it
  to the limit max it out, and use the best quality we can", "it should pretty much be on beat ... but let scenes finish
  properly"; on its first cut, "bump the time up to 2 mins", "dont do the same ones twice", "the first 20 seconds
  should be the really superlative"). **The montage** (`xenoform_montage.mp4`, 2:02, 16:9, and
  `xenoform_montage_9x16.mp4`) is Glitch Out from 1:56 to its own end, 23 looks with none twice. Each is a Cloud Final
  cut made through the desk like any Make on a 30 s window of the same song, so every picture plays over the seconds it
  was made on and its beat FX land on the song's hits (`scratchpad/wt/montage_renders.py`, `montage.py`). Every cut
  falls on a beat of the song's own grid, moved to the beat where the outgoing morph has finished. It opens on the
  black glass rose of the posted morph reel opening into the lotus (the chain pinned so they fall on the two bars
  before the drop). Then come lava-obsidian dinosaurs, the deep-sea fish in their feedback trails, shadow-self magic, and
  a local Final clips cut on the free film pack's most striking windows (Moloch, the Moon, the Phantom, the Kitchen of
  Tomorrow, Apollo 11, Maria). After them origami noir, Cyberspace 1995, neon noir, Bloom timelapse with scenes, cosmic,
  risograph, porcelain kintsugi, Y2K chrome, ice, the reel's black glass creatures, chrome robots, porcelain marble,
  ferrofluid, None with pirates, iridescent glass in space, brutalist and neon night, and liquid gold under the title.
  All five morph styles, the three timings, every effect (kaleido only on the fish), Foreshadow and Scenes are in it.
  Out after Tys's notes: wet paint ("pretty terrible"), the odd machine, the jug, the wheel and the guitar. Three vibes
  without a still library (hologram, thermal, ink-water) came out gold on that desk and were left out. In all, 46
  finished cuts and 709 morphs on Comfy Cloud, about 2,600 credits by the 3.6-a-morph measure (the dashboard was
  not read). **The demo** (`xenoform_demo_video.mp4`, 1:59.0, and the 9:16) opens on the montage's first 24 s, the
  title landing on the drop. The walkthrough after it is re-paced. The desk shots play still and full frame, with no
  push-in. Every sentence is read on its own (`split_copy.py`), with a breath between sentences and around each scene;
  the copy is down to 73 s of voice, with the Model line moved to the long and Comfy Cloud named in How it's built.
  Every scene ends on a beat of Glitch Out (`cutlib.py`). The outputs play full frame from Cloud Finals made on the
  bed's own seconds, each ending on a shot boundary. **The long** (`xenoform_long_walkthrough.mp4`, 8:13) has the same
  intro and pauses, the knob-panel shots re-recorded on the polished desk (the page no longer jumps under a chip), and
  l31 naming the new clips cut (its `say` had still read the old Caligari line). Chapters: 0:00 intro · 0:23 What it
  is · 0:45 Song and vibe · 1:24 What it morphs through · 2:14 Make · 3:01 The engine · 4:18 The timeline ·
  5:15 Your clips · 5:51 Share · 6:17 Under the hood · 7:30 How it's built. Checked with `qa_cut.py`: no black frame
  beyond the dark card grounds, the only frozen stretches the title under its line and the cards' held panels, -16 LUFS,
  true peak -2.4 to -3.5 dBFS.

## Decided

- **The voice is af_heart** (Tys, 29 Oct 10:30 am). The contest video is
  `Desktop\xeno_walkthrough_29oct\xenoform_demo_video.mp4` (the af_heart short, 1:59.0 since the glow-up, under the
  form's 2:00); the long one for the README and the post's replies is `xenoform_long_walkthrough.mp4` (8:13); the
  montage stands on its own as `xenoform_montage.mp4` (2:02). The am_michael and bm_george shorts of the morning stay
  beside them, unchanged.
- **A 9:16 cut for the post** (Tys, 29 Oct 10:40 am: "May as well do a 9:16 cut as well"):
  `xenoform_demo_video_9x16.mp4`, 1080x1920, the same plan, read, bed and loudness, laid out for a phone by
  `scratchpad/wt/assemble_v.py`: the 9:16 cuts play full frame (since the glow-up, the intro and the outputs are Cloud
  Finals made at 9:16), the desk
  recordings sit as a 1080x608 strip high in the frame over their own blur with the captions large beneath, grids go
  two or three columns, and the two cards are recorded again for the phone (`cards/cards_v.html`, five steps as a
  column; `record_cards_v.py`). While at it the cards' model chip, which still said LTX-2.3, says LTX-2.5 in both
  layouts, and the captions no longer overlap in time (libass stacks a caption that starts while the last one shows a
  line higher, for its whole life: into a grid or the card's chips on the phone), so every cut was rebuilt once more.
