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

## Short (about 1:52)

| Time | Picture | Voice |
| --- | --- | --- |
| 0:00 | Three cuts, fast: a liquid-gold Cloud Final, the Caligari to NASA clips cut, a neon noir Cloud Final | Xenoform turns a song into a music video where every beat is a transformation. |
| 0:07 | The Song step: drop a song; the vibe grid, None last | Drop in a song and pick a vibe: molten gold, neon noir, ink and paper, or None, the things just as they are. |
| 0:15 | The idea line: "underwater" grows its chips | Then say what it morphs through. A theme like underwater brings fifteen things of its own. |
| 0:22 | Make; the making screen, the chain, the steps | Make listens to the song, plans the shots on its bars and beats, picks the objects, and renders a morph for every shot. |
| 0:32 | The result playing: the None "underwater" Cloud Final | Every shot is one object turning into the next, cut to the song's own bars. |
| 0:39 | Morph styles side by side: Melt, Shatter, Bloom, Spin, Fold | Five ways to change, and the change can land right on the beat. |
| 0:47 | Effects: dither, feedback, kaleido, slit-scan | Effects ride the kick and the loudness. |
| 0:54 | The timeline: picture tiles, the Look tab, a colour change, Apply | Then edit it like a timeline. Colour, effects, order and cuts, shot by shot, re-cut from the cached morphs with no GPU. |
| 1:07 | Morph > Your clips: Caligari, Nosferatu, NASA | Or morph your own film clips into each other. |
| 1:15 | Draft, Fast Final, Final, Cloud Final, with their times | A Draft in minutes, a Fast Final at 1080p, the full local Final, or Cloud Final, the same morphs on Comfy Cloud. |
| 1:23 | How it's built: song → stems and bars → plan → ComfyUI graphs → LTX morphs → re-cut (a diagram over the desk) | How it's built: the song is split into stems and bars, the plan becomes ComfyUI graphs sent through the Comfy SDK, and LTX renders every morph on any card from 12 GB up. All open weights, local by default. |
| 1:37 | What's new: the song's waveform under the timeline; the MCP panel | What's new: the edit comes from the music itself, every shot is generated, and you change it like an editor, not a prompt box. An MCP server lets any AI drive it. |
| 1:48 | End card: github.com/tysonfarrington-cmyk/xenoform, #OpenSourceHiggsfield | Xenoform. Open source, on GitHub. |

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
2. **The voice**, from the locked script, one paragraph a row, timed; the picture is cut to the read.
3. **The screen**: the desk in headless Edge at 1920x1080 driven over the DevTools protocol (Node's own WebSocket, no
   installs), each row a scripted action with its frames captured, on a desk with a quiet GPU so nothing stalls on
   camera. A finished cut is opened from its record rather than rendered on camera.
4. **The outputs**: the overnight Finals (after the Thursday 9 pm freeze), the clips cut and a None cut, played full
   frame where the voice talks about the result.
5. **The edit** with ffmpeg: picture to the read, captions from the voice's timing, the demo song under the voice and
   ducked, the end card; then a check of the length (under 1:55), black frames and loudness.
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

## Still to decide

- Which Kokoro voice: af_heart (US female), am_michael (US male) or bm_george (UK male). Swapping is a re-read and a
  re-assembly, about ten minutes.
