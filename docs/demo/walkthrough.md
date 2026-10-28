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
  (song analysis, ComfyUI graphs through the Comfy SDK, LTX on one 12 GB card, all open weights) and say what is new.
  It ends on the repo URL. The long one is for the README and the post's replies, with no limit.

## Short (about 1:52)

| Time | Picture | Voice |
| --- | --- | --- |
| 0:00 | Three cuts, fast: a liquid-gold Final, the Caligari to NASA clips cut, a None cut | Xenoform turns a song into a music video where every beat is a transformation. |
| 0:07 | The Song step: drop a song; the vibe grid, None last | Drop in a song and pick a vibe: molten gold, neon noir, ink and paper, or None, the things just as they are. |
| 0:15 | The idea line: "underwater" grows its chips | Then say what it morphs through. A theme like underwater brings fifteen things of its own. |
| 0:22 | Make; the making screen, the chain, the steps | Make listens to the song, plans the shots on its bars and beats, picks the objects, and renders a morph for every shot. |
| 0:32 | The result playing | Every shot is one object turning into the next, cut to the song's own bars. |
| 0:39 | Morph styles side by side: Melt, Shatter, Bloom, Spin, Fold | Five ways to change, and the change can land right on the beat. |
| 0:47 | Effects: dither, feedback, kaleido, slit-scan | Effects ride the kick and the loudness. |
| 0:54 | The timeline: picture tiles, the Look tab, a colour change, Apply | Then edit it like a timeline. Colour, effects, order and cuts, shot by shot, re-cut from the cached morphs with no GPU. |
| 1:07 | Morph > Your clips: Caligari, Nosferatu, NASA | Or morph your own film clips into each other. |
| 1:15 | Draft, Fast Final, Final, Cloud Final, with their times | A Draft in minutes, a Fast Final at 1080p, the full local Final, or Cloud Final, the same morphs on Comfy Cloud. |
| 1:23 | How it's built: song → stems and bars → plan → ComfyUI graphs → LTX morphs → re-cut (a diagram over the desk) | How it's built: the song is split into stems and bars, the plan becomes ComfyUI graphs sent through the Comfy SDK, and LTX renders every morph on one 12 GB card. All open weights, local by default. |
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
- **The short** (1:42 af_heart, 1:48 am_michael, 1:46 bm_george) and **the long** (6:52 in af_heart, ten chapters with
  labels) were rebuilt on the frozen app on 29 Oct at 7 am and are in `Desktop\xeno_walkthrough_29oct`, with 720p review
  copies. Every desk shot was re-recorded on the final commit (the Make on camera is a Fast Final of the None
  "underwater" cut, b251df0c); captions are burned in from the voice copy; the music bed is Tys's Suno track
  XF_HipHop_BoomBap_01, ducked under the voice (looped under the long one); the mix is -16 LUFS.
- **The long one's chapters** (for the YouTube description, af_heart timing): 0:00 What it is · 0:20 Song and vibe ·
  0:54 What it morphs through · 1:37 Make · 2:17 The engine · 3:24 The timeline · 4:13 Your clips · 4:40 Share ·
  5:03 Under the hood · 6:13 How it's built.

## Still to decide

- Which Kokoro voice: af_heart (US female), am_michael (US male) or bm_george (UK male). Swapping is a re-read and a
  re-assembly, about ten minutes.
- The three opening cuts: which Finals to render overnight after the Thursday 9 pm freeze (the cut uses earlier Finals
  until then).
- The opening and result shots still play Fast Final cuts and the earlier Finals; once showcase Finals are rendered on
  Cloud Final (LTX-2.5), swap them into `plan_short.json` (open, result) and `make_plan_long.py` and re-assemble.
