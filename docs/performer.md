# Performer shots (`xenoform.performer`)

Polly, the bundled fictional performer (`src/xenoform/ui_static/performer/polly.png`, or your own full-body still), performs the song on screen: drums on the drop and the build, singing into a studio microphone on the intro, the calm passages and the outro. The picture is made by **MiniMax H3**, an open-weights model that generates video and audio together, run **image-to-video on your own GPU through ComfyUI** with the real song segment anchored at frame 0, so the performance is generated against the music the viewer hears rather than against a soundtrack the model invents. The desk cuts each shot 1:1 into the morph chain (Fine-tune → Performer, off by default); LTX-Video stays the core morph model.

## Model files

All open weights, loaded by ComfyUI from its `models/` folders. `performer.available()` checks these lists (`/models/diffusion_models`, `/models/text_encoders`, `/models/vae`, `/models/loras` on the ComfyUI port; the comfy-api-proxy on 8189 does not forward them) and caches the answer for 60 s.

| File | ComfyUI folder | Size | What |
|---|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `diffusion_models/` | 19.5 GB | the H3 transformer (33B, int8 "convrot" repack) |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders/` | 14.6 GB | Qwen3-VL-32B text encoder, nvfp4 (`CLIPLoader` type `minimax`) |
| `minimax_h3_video_vae_fp16.safetensors` | `vae/` | 4.9 GB | video VAE |
| `minimax_h3_audio_vae_fp32.safetensors` | `vae/` | 0.56 GB | audio VAE (32 kHz stereo) |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `loras/` | 1.96 GB | lightx2v Minimax-h3-Turbo 8-step distillation LoRA (optional) |

Without the LoRA the desk still works: `available()["steps"]` is 20 and the base graph is used; a 5 s shot then takes about 6.5 minutes instead of a few.

## The turbo LoRA

`lightx2v/Minimax-h3-Turbo` ("FL2VA Turbo 8-step v1.0", ComfyUI file above). Its card and the `ModelTC/Minimax-H3-Turbo` repository recommend, for this 544p-class mixed-aspect LoRA:

- **8 NFE** (steps), 4 in a pinch; LoRA **strength 1.0**;
- **sigma shift video 12, audio 3** (`MiniMaxH3SigmaShift`); the 768p LoRAs want 6 / 3 instead;
- the example graph samples with **`euler`**, scheduler **`simple`**, denoise 1, no CFG (`BasicGuider`).

The LoRA sits on the model only (`LoraLoaderModelOnly`), so the text encoder and both VAEs are the same files as the base graph.

## The graphs

Both are API-format graphs with the same node ids, so `render_slot` fills the same inputs whichever it submits:

| Node | Class | Role |
|---|---|---|
| 1 | `UNETLoader` | the H3 model |
| **18** | `LoraLoaderModelOnly` | **turbo graph only**: the LoRA, strength 1, fed by node 1 |
| **19** | `MiniMaxH3SigmaShift` | **turbo graph only**: shift video 12 / audio 3, fed by node 18; feeds the guider (6) and the scheduler (8) |
| 2, 3, 4 | `CLIPLoader`, `VAELoader` ×2 | text encoder, video VAE, audio VAE |
| 15, 16 | `LoadImage`, `LoadAudio` | the fitted still and the 32 kHz song segment (uploaded per shot) |
| 5 | `MiniMaxH3ImageToVideo` | prompt, width, height, length (frames); the still is `first_frame` |
| 17 | `MiniMaxH3AddGuide` | anchors the song segment at `frame_idx` 0 |
| 6, 7, 8, 9, 10 | `BasicGuider`, `KSamplerSelect`, `BasicScheduler`, `RandomNoise`, `SamplerCustomAdvanced` | sampling (`euler` / 8 steps with the LoRA, `res_multistep` / 20 without) |
| 11, 12, 13, 14 | `VAEDecode`, `VAEDecodeAudio`, `CreateVideo`, `SaveVideo` | decode and save the mp4 at 24 fps |

- `workflows/minimax_h3_i2v_api.json`: base model, 20 steps; nodes 6 and 8 take the model straight from node 1.
- `workflows/minimax_h3_i2v_turbo_api.json`: the same with nodes 18 and 19 between node 1 and nodes 6 / 8, 8 steps, `euler`.

## How a shot is made

`render_slot(audio_path, t0, seconds, still, prompt, work, cfg, seed=0, steps=None, size=(480, 832), fps=24, client=None, report=None, beats=None, max_tries=2)`:

1. **Grid.** H3 accepts 17k+5 frames at 24 fps: `GRID = [124, 141, 158, 175, 192, 209, 226, 243, 260]` (5.17 s to 10.8 s). `grid_frames(seconds)` is the smallest length covering `seconds` (nearest frame, so 5.17 s means 124 frames), capped at 260; `MIN_SECONDS = 124 / 24`.
2. **Song segment.** `[t0, t0 + grid seconds + 0.5]` is cut with ffmpeg to a stereo 32 kHz wav (the audio VAE's rate); the half second of slack means the last frames are not generated against silence.
3. **Still.** The reference is cover-cropped to the render size (`fit_still`), because the H3 node stretches `first_frame` to the canvas.
4. **Submit** through `cloud_morph._client(cfg)` (the comfy-sdk client on the local proxy, as the morph passes do) with the turbo graph when the LoRA is installed, the base graph otherwise; steps from `available()` unless given. While it runs, `report("restyle", frac, "Performer shot at 196.0 s - about 120 s left")` ticks from `estimate_seconds`.
5. **Trim and mux.** The render is trimmed to exactly `round(seconds * fps)` frames and the **original song segment** is muxed over it (libx264 crf 17, AAC 48 kHz), not the VAE round trip, so the desk can treat the file as a clip of `seconds` seconds. The raw H3 output (with its own decoded audio) is kept beside it as `performer_<t0>_h3_<try>.mp4`.
6. **Measure.** `motion_energy` (mean |frame difference| on a 96 px grey copy) gives `sync_score`, `freeze_s` (how long the opening holds the still) and `cuts` (frames where the picture hard-cuts, which is how a shot that lost Polly shows up).
7. **Retry.** With `beats` (song time) and a drum prompt, a shot that is poor (strokes at chance against the beats *and* a held still or a cut-away, see "Sync score") is re-rolled once with `seed + 1`; the better-scoring try is kept, the other stays on disk as `performer_<t0>_try<n>.mp4`. Singing shots never retry. A retry costs another full render, so the rule is deliberately narrow.

Result: `{"clip": Path, "frames": int, "seconds": float, "sync": float | None, "tries": int, "steps": int, "lora": str | None, "render_s": float, "vram_gb": float | None, "freeze_s": float, "cuts": list[int], "seed": int, "raw": Path, "grid_frames": int, "scores": list, "prompt": str}`. The clip is `work/performer_<t0>.mp4` (`t0` with two decimals).

## The rest of the API

- `available(cfg=None) -> dict`: `ok`, `model`, `text_encoder`, `video_vae`, `audio_vae`, `lora` (filename or None), `steps` (8 with the LoRA, 20 without), `missing`, `note` (one line for the desk).
- `default_reference() -> Path`: the bundled Polly still.
- `prompt_for(role, vibe_look, instrument=None) -> str`: see the prompt rules below.
- `sync_score(clip, beats) -> float`: 0..1, see below.
- `estimate_seconds(seconds, steps) -> float`: wall time of one shot from the measurements below.

## Timings and VRAM (RTX 3080 Ti, 12 GB, 32 GB RAM, ComfyUI 0.33)

The 19.5 GB model does not fit the card; ComfyUI streams it from RAM every step ("dynamic VRAM loading"), so the per-step cost is bandwidth-bound and the whole run needs about 11 GB of VRAM and 20 GB of free RAM. Portrait 480×832, one job at a time, nothing else on the GPU.

| Shot | Steps | Frames | Run (model loads included) | Peak VRAM | Notes |
|---|---|---|---|---|---|
| drums, base model | 20 | 124 (5.17 s) | 393 s | 11.8 GB | probe, no audio anchor |
| drums, base model | 20 | 192 (8.0 s) | 963 s | 11.3 GB | probe, audio anchored; held the still for 4 s |
| drums, turbo LoRA, weights cold (from disk) | 8 | 124 (5.17 s) | 441 s (sampling 8 × 42 s) | 11.8 GB | Polly held; still for 8 frames, then a cut to her at the kit |
| drums, turbo LoRA, weights warm (in RAM) | 8 | 124 (5.17 s) | 383 s (sampling 8 × 41.7 s) | 11.8 GB | the seed+1 re-roll: still for 1.3 s, then the cut |
| singing (intro, song start), turbo LoRA | 8 | 124 (5.17 s) | 441 s (sampling 8 × 41.8 s) | 11.8 GB | Polly held: she starts singing in the standing shot (0.8 s), then a cut to a close-up at the microphone, her white jacket turning to molten gold as the liquid-gold look asks |
| drums, continuity prompt (seed 9), turbo LoRA | 8 | 124 (5.17 s) | 439 s (sampling 8 × 41.8 s) | 11.8 GB | Polly held; still for 8 frames, then the same cut to her at the kit; the "no cuts" wording changed nothing |

**The LoRA does not make a 12 GB card faster.** A base-model step takes about 15 s here, a LoRA step about 42 s: with dynamic VRAM loading the weights are streamed from RAM every step and the LoRA's 208 patches are re-applied to each streamed weight, so 8 patched steps (334 s) cost about the same as 20 plain ones (300 s). The LoRA pays off on a card that holds the 19.5 GB model and patches it once (24 GB and up), or at 4 steps (its card allows "8 / 4"), untested here. `available()` still prefers it when it is installed, because that is the configuration the model card recommends and the picture quality at 8 steps was good.

`estimate_seconds(seconds, steps) = 49 + per · steps · frames · (frames / 124)`, with `per` 0.34 s for the LoRA path (steps ≤ 8) and 0.14 s for the base model: 386 s for a 5.17 s turbo shot (383 measured warm), 396 s for the 20-step base shot (393 measured), 881 s for 8 s at 20 steps (963 measured). The first shot after ComfyUI has been doing other work pays the model loads again (the text encoder alone stages 15 GB, about a minute more); queue wait is not included.

## Sync score

`sync_score(clip, beats)` asks whether the picture's strokes sit on the beats. Per-frame motion energy → the N strongest local maxima (N = beats inside the clip, at least 3 frames apart) → the share of beats with a stroke within ±2 frames (83 ms) at the best lag in −1..+3 frames → lifted above what a randomly shifted beat grid scores with the same strokes (200 shifts), so a frozen or unrelated picture is ~0 and a locked one is 1.

Measured: the 20-step probe clips that moved scored 0.09–0.10 (the audio-anchored drum shot and the no-audio control alike), the two turbo drum shots 0.0 and 0.0, the clip that held the still for 4 s 0.01; synthetic clips flashing on the beat score 1.0 and half a beat late 0.0. In other words H3 moves with the music but its sticks do not land on the beat grid at 90 bpm: on this measure a real shot is at chance, so the score alone cannot tell an ordinary shot from a broken one. "Poor" therefore means **both**: `sync < POOR_SYNC` (0.05) **and** the picture shows a failure mode, `freeze_s >= 1.0` (it held the still for a second or more) or a hard cut after frame 12 (it cut away from the performance; a cut inside the first half second is the model's own way from the standing still into the shot). Only drum shots retry, once, with `seed + 1`, and the better-scoring try is kept. The desk's beat sync lives in the cut, not inside the performance.

## Prompt rules

`prompt_for(role, vibe_look, instrument=None)` builds: continuity and identity → action → look → camera and audio.

- **Continuity and identity first:** "One continuous unbroken take with no cuts and no scene change: the woman from the first frame, with exactly the same face, hair and outfit from the first frame to the last, …". The still is the first frame, so the prompt names her by it.
- **Already performing:** "… is already playing a drum kit when the clip starts and never pauses: both sticks hitting the snare, toms and cymbals on every beat of the music …" for `drop`, `build`, `drop_late`; "… is already singing into a studio microphone when the clip starts and keeps singing: lips shaping every word of the vocal line …" for `intro`, `calm`, `sustain`, `release`, `outro` (and any other role). `instrument` overrides (`"drums"`, `"vocals"`, or a noun such as `"guitar"`).
- **The vibe's look** follows as "Look: …" (`morph_pass.VIBE_LOOK[vibe]`).
- **Camera and audio last:** "The first frame flows straight into the performance and the camera never cuts away: medium shot, steady camera, she stays centred and fully in frame for the whole clip. Audio: the music track only, no speech."
- What the model did with earlier wordings: "the scene opens on the figure from the first frame" held the still for 4 s on an 8 s probe before anything moved; "a chrome figure plays a drum kit" (no identity sentence) held 8 frames then cut to its own drummer. With the identity sentence and "is already playing … when the clip starts" the drummer after the cut **was Polly** (same face, white jacket, jeans, hair lit by the vibe's neon) at a kit in the vibe's dark red studio, but the shot still opened on the standing still for 8 frames (seed 7) or 1.3 s (seed 8) and then hard-cut, because the still (full body, white studio, no instrument) and the scene (kit, crimson backdrop) cannot be joined without one. The continuity sentence ("One continuous unbroken take with no cuts and no scene change … the camera never cuts away") was tried against that on a third seed: Polly held again, and the cut came again at frame 9. Prompting cannot join a standing still on white to a drum kit in a crimson studio; the still has to change (Polly already seated at the kit, or standing at the microphone, in the vibe's setting), or the desk accepts a third of a second of the still before the performance.

## Limits

- 5.17 s to 10.8 s per shot (one grid length); longer slots must be split by the caller. Trained range is about 124–362 frames; the desk stops at 260.
- Portrait 480×832 by default (both sides multiples of 32). Bigger canvases cost more than linearly: the attention runs over every frame.
- A 12 GB card streams the model from RAM: one shot at a time, about 11 GB VRAM and 20 GB free RAM; do not run a morph pass on the GPU at the same time.
- The audio anchor reproduces the segment faithfully (waveform correlation 0.9 with the input), but the final clip uses the original song anyway.
- Identity held in every measured shot (Polly's face, jacket and jeans survive the vibe's lighting), but the standing still on white is not the first frame of a drum shot: the model holds it for 8–31 frames and then hard-cuts to the performance. `freeze_s` (opening motion below 1.5 on the 0–255 difference scale) and `cuts` (a frame difference above 40) in the result flag both. A still that already shows the performer at the instrument, in the vibe's setting, would remove the reason for the cut. H3 is a generalist video model, not a lip-sync model: singing shots mouth along, they do not read lyrics.
- With the LoRA on a 12 GB card a shot is about 6.5 minutes either way (see Timings); a retry doubles it. Budget 7 minutes per slot, 14 with a retry.
- ComfyUI must stay up: a shot in flight is lost if the server restarts.

## Licence

**MiniMax H3** is released under the **MiniMax H3 Community License Agreement** (MiniMaxAI/MiniMax-H3 model card, LICENSE dated 2 August 2026, checked 23 October 2026). Open weights, downloaded from Hugging Face and run locally; no API, no account. Key terms:

- Royalty-free use, reproduction, modification and distribution, including commercial use; products or services making **more than US$20 million a year** need MiniMax's prior written authorisation.
- A commercial product must **display "MiniMax H3" prominently in its user interface**; distributions carry the licence and a NOTICE; modified files say they are modified. "Powered by MiniMax H3" labelling and AI-generation marks are encouraged, not required.
- **Excluded territories: the European Union, the United Kingdom, the Republic of Korea and the United States of America** (a separate licence can be requested for them). Australia is in the applicable territory.
- An acceptable-use policy (no military use, no unlicensed professional advice, no high-risk automated decisions, and so on); the works and their outputs may not be used to improve any other AI model.
- Fine-tunes and LoRAs are "Model Derivatives" under the same terms. **MiniMax claims no rights over the outputs.** Hong Kong law.
- The text encoder, Qwen3-VL-32B, is Apache 2.0.

The turbo LoRA (`ModelTC/Minimax-H3-Turbo`, published as `lightx2v/Minimax-h3-Turbo`) is **Apache-2.0** per its repository; as a derivative of H3 it is used under the H3 terms as well.

For the desk this means: the performer feature is open weights running locally, off by default, and the desk's licence page names "MiniMax H3" with the terms above. See [LICENCES.md](LICENCES.md).
