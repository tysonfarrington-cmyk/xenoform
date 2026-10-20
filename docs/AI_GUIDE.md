# Xenoform for AI assistants

Xenoform turns a song into a music video: a liquid object morphs on the beat, then open-weights LTX on the user's GPU (ComfyUI) restyles it. Everything runs locally and is free by default.

## Flow
1. `get_status`: desk, ComfyUI, GPU tier, final-tier readiness, recent jobs.
2. `create_project(prompt, vibe)`: a one-line idea and/or `image_paths`. These images become **morph targets**: the object morphs through them on draft and final.
3. `load_audio(path)` (optional; the built-in demo track otherwise).
4. `update_settings(...)`: vibe, aspect, tier, energy, transitions, beat FX.
5. `start_render` → `wait_for_render` / `get_render_progress` → `get_output`.
6. `cancel_render(job_id)` to stop. `list_videos` for history.

## Defaults
- Aspect **9:16 native** (rendered portrait 448×768, upscaled to 1080×1920).
- Vibe **black** (pure black void, iridescent liquid metal).
- Tier **preview**. Open weights only. Cloud off.

## Tiers
| tier | what | time |
|---|---|---|
| preview | CPU animatic, no model | seconds |
| draft | LTX on GPU, small | a few minutes |
| final | LTX-2.3 + upscale | ~90 s per shot on 12 GB |
| cloud | PAID, opt-in | needs `cloud=true, confirm_spend=true` and the user's OK |

## Vibes
liquid-gold, bloom, neon-night, ocean, cosmic, paper-summer, black. Each has an autotuned recipe (`get_autotune_recipe`) applied automatically on draft/final.

## Transitions
`list_transitions` gives in-shot morph transitions (pour/harden, droplet burst, ribbon, snap…) and whole-scene transitions with picks per vibe. Use the vibe's recommendation unless the user asks.

## Recipe codes
`encode_recipe` gives a shareable code (`xf1.` or, with transitions or shot edits, `xf2.`). `remix_recipe(code)` loads it back.

## Energy
`flow` (fewer, longer shots) or `dense` (cuts on more beats, harder drop).

## Good practice
- Preview first; share the `preview_url`; ask before draft/final.
- One GPU render at a time (the desk allows two cuts; the GPU is 12 GB).
- Never spend money without an explicit yes. No keys or secrets are ever returned.

## Guardrails

Every render (desk, MCP, CLI) first passes through `configs/guardrails.json`, which clamps settings known to cause flaky output and reports what it changed in the job's `guardrails` field. Call `list_guardrails` to show them and `check_guardrails` for a dry run. Defaults: about 15 forms per 20 s (over 18 is clamped), no stutter or wobble inside morph runs, complex shapes over simple objects (warning), NASA anchors for planets, stock-dance motion for characters, a 0.15 minimum motion score for footage, native 448x768 9:16 plus RealESRGAN x4, black morph stills, the Gemma encoder on LTX-2.x (never T5), 12 GB VRAM limits, low FX on app shots with wobble at most twice, no shimmer, and no partner nodes in open-weights mode. `start_render(expert=true)` keeps the user's values and only warns; use it only when the user asks. Shimmer and the encoder fix always apply.

### Auto-edit guardrails (demo v4 audit)

- **No repeats:** one use per source within a video, tracked by path and perceptual hash. When the pool runs dry the editor pulls more library clips, else it uses fewer, longer shots and warns. The VJ plays each loop once per pass.
- **Lag QA:** after every render, freezedetect, mpdecimate and an fps check. Mismatched fps is conformed to the project fps, and judder or short freezes get held frames interpolated. The job's `qa` report and guardrail notes say what happened. Clips are conformed to the project fps before compositing.
- **Low-res gate:** sources below the output size are upscaled (RealESRGAN x4) or rejected, using native size and Laplacian sharpness. NASA library clips also need a 720 px short side and a 0.15 motion score, and soft ones are marked in the manifest.
- **Artifacts:** heavy chromatic aberration (3 px or more) or glitch bands on non-VJ renders are flagged.
- **Beats:** cuts more than 40 ms off the beat are reported, and explicit cut lists are snapped.
- **Characters (Polly):** at most 3 appearances and none in the first 15% unless expert.
- **Kaleidoscope:** retired from VJ defaults (expert only).
- **Stem-reactive:** bass drives scale and displacement, drums drive chroma and stutter, other/vocals drive emission glow and colour.
