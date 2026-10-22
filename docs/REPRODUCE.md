# Reproduce the demo in about ten minutes

This page is for a judge. It goes from a clean checkout to the same kind of film as the demo video, on open weights, on your own GPU. Steps 1 to 3 need no GPU and take about two minutes; the rest need ComfyUI and a 12 GB card.

The song in the demo video ("Morph Engine v2") was made by the author on Suno and is not in the repo. Use `examples/demo.wav`, the bundled synthesised track, or any song of your own. The cut, the look and the transitions are the same; only the music changes.

## 1. Install (2 minutes plus the pip download)

You need Python 3.12 and `ffmpeg` on `PATH`.

- Windows: double-click `Xenoform.bat`. It offers to create `.venv` (about 5 minutes on the first run, nothing is installed into ComfyUI's Python), then opens http://127.0.0.1:47317.
- Linux or macOS: `bash install.sh`, then `.venv/bin/python -m xenoform ui`, and open http://127.0.0.1:47317.

## 2. The no-GPU path (60 seconds)

Press **Watch a finished one** for a pre-rendered reel of LTX morphs cut to the bar. Then pick **Bundled demo**, a vibe, and **Make**. A draft animatic plays after about 3 seconds. Without ComfyUI that animatic is the result; everything after this step replaces it with real LTX renders.

## 3. Run the tests (1 minute)

```bash
.venv/bin/python -m pytest tests/test_install.py tests/test_eligibility.py tests/test_docs.py -q
```

`test_eligibility.py` is the open-weights check: it fails if any default workflow references a partner or API node, fills an LTX API key, or encodes prompts through an API.

## 4. Start ComfyUI and the models

1. Start ComfyUI 0.33 or newer on port 8188. The shipped graphs use core nodes only.
2. Open **Setup** in the desk header. It lists each model with its size and a Download button (downloads resume and are checksummed):
   - **LTX-Video 0.9.5** (6.3 GB) and **T5-XXL fp8** (5.2 GB): required for Draft morphs. At 100 Mbit/s that is about 15 minutes together; on a faster line, a few minutes.
   - **LTX-2.3 22B distilled fp8** for Final, plus `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` and the Gemma 3 12B text encoder. The full distilled file on the Setup page is 46 GB; the fp8 file the 12 GB path uses goes in `models/checkpoints` by hand.
   - **Real-ESRGAN x4plus** (`models/upscale_models/RealESRGAN_x4plus.pth`, from the Real-ESRGAN v0.1.0 release on GitHub) for the Final upscale.
   - Optional: **Z-Image Turbo** (18 GB) only if you want to make new vibe stills; the shipped stills already cover 29 vibes. **Wan Animate 2** (Comfy-Org `Wan2.2-Animate-2` repack: int8 model, lightx2v LoRA, UMT5-XXL fp8, CLIP vision H, Wan 2.1 VAE) only for Moves.
3. `Xenoform.bat` starts `comfy-api-proxy` on port 8189 for you. By hand: `.venv/bin/comfy-api-proxy run --comfyui http://127.0.0.1:8188 --port 8189`. The desk header shows **connected** when `/system_stats` answers.

## 5. The demo cut in Simple mode (about 3 minutes on a 12 GB card)

Simple mode is three decisions. Leave everything in the **Fine-tune** drawer at its default: that is the `demo_house` profile from `configs/defaults_demo.json`, the look used in the demo video.

1. Song: **Bundled demo** (or drop your own file).
2. Vibe: **chrome-mercury** (the first featured vibe) gives the chrome-pour chain; any of the 12 featured vibes works the same way.
3. **Make**. The animatic plays, then the GPU pass replaces each scene with an LTX 0.9.5 morph from still to still. On an RTX 3080 Ti a 20 s clip with 7 morphs takes about a minute warm, about two minutes if ComfyUI has just had another model loaded.

What the defaults give you, and where each one lives:

| Setting | Demo value | Where |
| --- | --- | --- |
| Aspect | 9:16 native, 1080x1920 at 24 fps | `defaults_demo.json` → `format` |
| Energy | Dense (a shot every bar to the drop, every half bar after) | Fine-tune → Energy |
| Forms | 15 morphs per 20 s (auto) | `look.morph_forms` |
| Look (`dance_fx`) | `auto`: **cyan-flash** on the intro shot (1.25), **cool-echo** on the body (1.4), **bloom-rush** on a flower shot (1.5), **negative-rush** into the end card (1.2, the last 14 frames ramp to a full negative) | `defaults_demo.json` → `dance_fx` |
| Stem orbit | on: yaw up to 28 degrees from the bass, kicks from strong drum hits | `stem_orbit` |
| Transitions | `flow-morph`, `echo-trail`, `lens-breath`, at most 2 of a type, at most 3 shots in the first 15 s | `transitions` |
| Audio | -14 LUFS, -2 dBTP | `audio` |
| End card | off by default; switch it on for the demo's ending: recipe code plus `github.com/tysonfarrington-cmyk/xenoform` burned into the last two seconds, with the negative-rush ramp into it | Fine-tune → End card |

To get the demo's Final quality instead of Draft, set Quality to **Final** in the drawer. That is LTX-2.3 fp8 in two stages at 448x768 native portrait and Real-ESRGAN to 1080x1920, about 90 to 240 seconds a shot, so the desk shows an estimate first.

## 6. Stems (1 minute)

Open **Stem reactions** (in the Fine-tune drawer) and split the song. `POST /api/stems` runs Demucs on the CPU when `pip install -e .[stems]` has been done, otherwise a librosa band split; a two-minute song takes about 20 s with Demucs on an 8-core CPU. One lane per stem appears (up to 32), and the next Make uses them: drums drive the cuts and the chroma kick, bass the scale and the orbit, the rest the colour and glow. From the command line: `xenoform stems examples/demo.wav`.

## 7. VJ page and MIDI (2 minutes)

Open http://127.0.0.1:47317/vj. **Start mic / line-in** or **Load track**, then **Use this song's stems**. Space switches loops, 1 to 8 pick a premium transition, 0 is auto, F is fullscreen. Plug in an Arturia MiniLab 3 and it works without setup in Chrome or Edge (pads fire transitions, knobs ride intensity and the stem gains); any other controller maps in Learn mode (L). Firefox and Safari: `xenoform midi serve` carries the controller in over the desk. `xenoform midi record take.json --seconds 90` records a take that a render can follow. Details: [midi.md](midi.md), [vj.md](vj.md).

## 8. An MCP session (2 minutes)

With the desk running:

```bat
claude mcp add xenoform --env XENO_DESK=http://127.0.0.1:47317 -- .venv\Scripts\python.exe -m xenoform.mcp
```

(or the Claude Desktop and Cursor JSON in [mcp.md](mcp.md)). Then, in the client: "Connect to Xenoform and make a chrome-mercury video of the demo track in the house look." The server has 45 tools; the ones the demo used are `get_status`, `create_project`, `set_look(dance_fx="auto")`, `start_render`, `wait_for_render`, `get_output`, `review_render` and `get_qa`. It never spends money without `confirm_spend=true`, and the paid cloud tier is off.

## 9. Check the render (30 seconds)

```bash
.venv/bin/python -m xenoform.media_qa work/ui/<job>/final.mp4
```

The report covers loudness against the house target, clicks, black and frozen frames, static shots, the opening cut count, duration, and the transition rules (banned types, at most two of a type). The same checks run as the MCP tool `review_render`, and the desk's own post-render QA (freeze detect, fps conform) is on every job under `qa`.

## What you should see

A 9:16 film where one chrome object pours into the next on every beat, the picture breathing with the bass, a blue flash on the intro hits, a cool echo through the body, and the last shot inverting into an end card with the recipe code and the repo URL. Paste that recipe code into another machine's *Make my video* box and it renders the same film.
