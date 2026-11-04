# Xenoform for ComfyUI

A song becomes a music video of LTX morphs on the beat, inside ComfyUI. The nodes read the song (beats, sections, the
drop), plan the cut the way the Xenoform desk does (shots on the beat, a chain of objects, each morph's style and
timing), hand each morph to ComfyUI's own LTX 0.9.5 nodes, and cut the rendered morphs to the song. The **Morph
Timeline** opens the song strip full screen inside ComfyUI: move a cut along the beats, pin an object, draw the
intensity; the edits are saved with the workflow.

Everything is the song's: the canvas is its sections, beats and drops, and every shot is snapped to them. There is no
camera and no 3D view.

## Install

**ComfyUI-Manager, from the git URL** (the way to install it until the pack is on the Comfy Registry):

1. Manager > **Install via Git URL** > `https://github.com/tysonfarrington-cmyk/xenoform`
2. Restart ComfyUI. ComfyUI loads custom nodes only when it starts.
3. Load `custom_nodes/xenoform/comfy_pack/workflows/xenoform_demo.json` (drag it onto the canvas) and press **Queue**.

The Manager clones the whole repository into `custom_nodes/xenoform`; the repository's `__init__.py` registers these
nodes and serves the editor. Its `requirements.txt` lists nothing, so nothing is pip-installed into ComfyUI's Python.

**By hand, the same thing:** `git clone https://github.com/tysonfarrington-cmyk/xenoform` inside `ComfyUI/custom_nodes`,
then restart ComfyUI.

**The pack folder alone:** copy `comfy_pack/` into `ComfyUI/custom_nodes/` under any name (`xenoform-nodes`, say) and
restart. It carries what it needs: the demo song, the dozen Liquid chrome stills of that vibe's curated chain, and the
vibe registry's looks and tuning. Every other vibe borrows those stills and keeps its own look; the whole repository has
every vibe's own stills. Install one or the other, not both (the second copy's nodes would replace the first's).

**Models** (the stock LTX 0.9.5 morph, as the desk's Draft uses): `models/checkpoints/ltx-video-2b-v0.9.5.safetensors`
and `models/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors` (the links are in `pyproject.toml`). ComfyUI 0.33 has
every node the demo uses. ffmpeg must be on PATH, or the `imageio-ffmpeg` ComfyUI installs usually carry, for the
Assemble.

**Python packages:** none beyond ComfyUI's own (numpy, Pillow, torch, PyAV). If librosa is installed, the song analysis
runs the desk's own librosa code; without it, the same steps run in numpy and give the same beats, sections and drop on
the bundled songs (the tests measure it).

## The nodes

| Node | In | Out | What it does |
| --- | --- | --- | --- |
| **Xenoform Song Analysis** | a song from the list (the bundled demo, the repository's six bundled songs, any audio file in ComfyUI's `input/`), or a `LoadAudio` AUDIO, or a desk `features.json` | `song`, a summary, tempo, duration | The desk's analysis: per-frame bands and energy, beats on a 24 fps clock, onsets, sections labelled calm, build, drop, release or sustain, and the main drop (the biggest one-bar jump in loudness). |
| **Xenoform Storyboard** | `song`, a vibe, an idea line, the knobs (energy Dense or Flow, forms, speed, chaos, intensity, morph style, morph timing, pace, aspect, seed), optionally a folder of your own images | `storyboard`, a summary, the morph count | The shot list a desk Make would plan: Dense cuts a bar before the drop and a half bar after it, with punches, stutters and a hold; Flow one shot about every 5 s; a whole song over 20 s the story plan, one morph a shot and no object twice. The chain of objects (the vibe's curated pool, the object your idea line names first), each morph's style (Auto: Melt, Shatter on the drop, Bloom at the opening) and timing. |
| **Xenoform Morph Timeline** | `storyboard` | the edited `storyboard`, a summary | The editor (below). Without edits it passes the plan on. |
| **Xenoform Morph Pair** | `storyboard`, an index (0 is the first morph) | the two guide images, the prompt, the negative, frame rate, width, height, length, steps, seed, cfg, the two guide compressions, guide B's strength, the slot's frames, the request as JSON | One morph's request, value for value what the desk sends LTX 0.9.5 through `workflows/xenoform_morph.json`: the guides go to `LTXVPreprocess` and `LTXVAddGuide` (frame 0 and frame -1), the prompts to `CLIPTextEncode`, the size and the 8k + 1 length to `EmptyLTXVLatentVideo`, the steps to `LTXVScheduler`, the seed to `RandomNoise`, the cfg to `CFGGuider`. |
| **Xenoform Assemble** | `storyboard`, the decoded frames of each morph (`morph_1` is morph 0), fill, punch | the mp4's path, and a preview on the node | Each morph laid in its slot on the beat (first frame on still A, last on still B, so every handoff is continuous), re-timed by the plan (speed, ease, stutter, hold, skip, reverse, and the timing On the beat or Snap), the plan's punches scaled by each shot's intensity, muxed with the song by ffmpeg into `output/xenoform/`. A shot with no morph connected ends the cut there, or with fill `stills` plays a crossfade of its two stills, so the whole song can be heard with what is rendered. |

## The Morph Timeline

The button **Open the Morph Timeline** on the node opens the editor over the whole window. If the node has not run, the
editor offers **Plan the song (no GPU)**: it queues this node alone (the analysis and the storyboard run, no morph is
rendered) and the strip fills in. Right-click the node > **Queue Selected Output Nodes** does the same.

The lanes, top to bottom: **SECTIONS** (colour-coded, the drop flagged), **WAVE** (the song's loudness), **BEATS** (bars
heavier), **SHOTS** (one block a shot, on the beats), **INTENSITY** (keyframes on the beats; each shot takes the value
at its start), **OBJECTS** (the still the chain lands on at each cut).

- Wheel zooms; Shift+wheel or dragging the ruler pans; **Fit** shows the whole song; **Play** (Space) plays the song
  with a playhead; click the ruler to seek.
- Drag a cut along the beats (Shift snaps to bars, Alt is free). Double-click a shot to split it on the beat; Delete
  joins the selected shot to the one before. A cut the plan has not seen yet is hatched until the next run.
- Select a shot: its own **style** (Melt, Shatter, Bloom, Spin, Fold), **timing** (Smooth, On the beat, Snap), **Hold**
  (it shows its first still), **seed**.
- Click the intensity lane to add a point, drag it, Delete removes it, double-click types its value.
- Click an object to pin a still of the pool at that cut; the rest of the chain fills around it, no still twice.
- **Save** writes the edits into the workflow (a hidden widget on the node), **Plan the edits** saves and runs the node
  alone, **Reset edits** returns to the plan, Ctrl+Z undoes.

The edits are kept apart from the plan: change the vibe or the knobs upstream and the edits land on the new plan; edits
made for another song are kept but not applied, and the summary says so.

## Honest limits

- The pacing engine of the desk (Breathe's rests, the drop runs and their heat) is not in the pack: a whole song plans
  as the desk does with Breathe and Drops off.
- The chain is the vibe's curated order with the idea line's object first; the desk's taste file, object families,
  grown stills and usage history are the desk's.
- The Assemble is the plain cut: no beat FX layer, no transitions, no look pass, no end card (the desk does those).
- Draft only: LTX 0.9.5 at 512x288 (320x576 for 9:16). The desk's Final and Cloud tiers stay on the desk.
- The editor edits the plan's cuts, styles, timings, holds, seeds, intensity and pins; it does not render. Each Queue
  renders every Morph Pair again when anything upstream of it changed (ComfyUI's cache is per input).

## For Tys, after the contest

Install through the Manager from the git URL (above) and restart ComfyUI once: it loads custom nodes only at start, so
nothing here is in the running ComfyUI until then. Then fill in `PublisherId` in `pyproject.toml` (this folder's, to
publish the pack alone; the repository root has its own `[tool.comfy]` for the whole repository) and run
`comfy node publish` to put it on the Registry, where the Manager's search finds it.
