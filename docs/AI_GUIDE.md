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
- **No repeated stills in morphs:** when a vibe's still pool would wrap, the morph path uses fewer, longer morphs and says so.
- **High-res first:** the auto-editor orders sources sharp, then upscale, then soft, then rejected. NASA clips download from the original master.
- **VJ stems:** separate uniforms for drums (chroma split), bass (scale and displacement), other (colour) and vocals (emission). They come from `?stems=<stem_react JSON>` or an in-browser band split.

- Dance FX (`xenoform.dance_fx`): subject-safe, stem-reactive in-scene passes for character shots: stem-driven split-tone grade, highlight halation / light bleed, light frame echo trail, edge tint (no offset), beat light leak, static glass texture, soft fades. Colour and light only: never warp, displace, scale or offset a dancer. Presets are listed under **The house look** below.

## The house look (demo_house)

`xenoform.demo_house.DEMO_HOUSE` is the contest demo's profile, merged into `config.load_config()["house"]` and read through `config.house(section)`. Every look module falls back to it when an argument is `None`: `dance_fx.DanceFX(preset=None, intensity=None, role=...)` and `dance_fx.render_shot(..., fps=None)`, `transitions_fx.apply(intensity=None)` / `guard` / `plan` / `recommend` (`cap`, `allowed`, `banned`, `classic`), `stem_orbit.plan/apply/render_shot` (`fps`, `focal`, every `DEFAULTS` key). The profile: 9:16 native 1080x1920 at 24 fps, black morph stills, no shimmer, no character wobble, 15 morph forms, transitions allowed `flow-morph` / `echo-trail` / `lens-breath` (banned: wipe, iris, stutter, kaleidoscope, mid-morph-stutter; at most 2 of a type; at most 3 shots in the first 15 s), -14 LUFS / -2 dBTP, 120 s cap.

**dance_fx presets** (all colour and light only; `list_looks` returns these notes):
| preset | look |
|---|---|
| warm-leak | warm split-tone grade, film halation on the bass, corner light leak on the beat; no echo |
| cool-echo | cool blue grade, light ghost trail on 'other', cyan edge tint on the drums, frosted glass (the house VJ look) |
| noir-glow | high-contrast noir grade, violet edges, moderate halation and leak, a touch of glass |
| bloom-rush | hero / flower preset: long trails, heavy bloom, cyan-magenta gradient wash and chroma bleed |
| negative-rush | bloom-rush plus a stem-driven negative: luma flips on the bass/beat, hue kept, eased |
| cyan-flash | electric-blue beat flashes, negative pulse on big hits, slow light sweep, depth bloom, exposure breath |

House roles (`DEMO_HOUSE["dance_fx"]`): intro = cyan-flash 1.25, vj = cool-echo 1.4, flower = bloom-rush 1.5, into_card = negative-rush 1.2 with `invert_floor_ramp_frames` 14 (the last 14 frames ramp to a full negative so the shot lands inverted on the end card). In a Simple render the first shot is `intro`, the last shot `into_card` when the end card is on, every other shot `vj`.

**stem_orbit** (`xenoform.stem_orbit`): a rigid camera orbit of the subject (yaw from the bass, eased kicks from strong drum hits, a little pitch from 'other'), spring-damped, no warp. Parameters are the house `stem_orbit` block (max_yaw 28, max_pitch 4, max_roll 1.5, bass 1.0, drums 0.7, other 0.4, spin 0, stiffness 6, focal 1.6). It needs OpenCV on the desk; without it the frames pass through and the job's `look.notes` say so.

**Stems:** a render uses the job's split stems when `state["stems_path"]` points at a `stem_react.envelopes` JSON (`POST /api/stems` writes `work/ui/stems/<hash>/stems.json`); otherwise a 4-role envelope is derived from the mix (kick flux -> bass, transient flux -> drums, loudness -> other) with the beat grid as drum hits. Up to **32 named stems** are accepted (`stem_react.MAX_STEMS`); `macros.stems {name: gain 0..1}` weights each stem before it feeds its role (drums / bass / other / vocals).

**/api/generate payload keys** for the look (Simple mode, read by `dense.options` / `dense.macros`):
- `dance_fx`: `"auto"` (default: the vibe's `fx_defaults.dance_fx` from configs/vibes.json when set, else the house role presets) | `"off"` | a preset name.
- `stem_orbit`: `true` (default) | `false`.
- `macros`: `{"intensity": 0..1, "speed": 0..1, "chaos": 0..1, "glow": 0..1, "stems": {"<stem>": 0..1}}` (0.5 / 0.5 / 0.3 / 0.4 neutral). `intensity` scales the beat FX, `chaos` above 0.5 adds wobble (never in the 9:16 house look), `speed` biases the auto morph count (x0.6 .. x1.4) and shortens dance_fx echo trails, `glow` scales halation / depth bloom and the beat-FX bloom, `stems` are the per-stem gains.
- `stems_path`: the job's `stems.json` (optional; set by the desk when the song was split).
- `look_profile`: `"demo_house"` (the only profile today).
The finished job's `simple.json` carries `look` (preset per shot, stem_orbit on/off, seconds spent, notes), `fps`, `macros` and `stems_path`.

**MCP tools for the look:** `set_look(project_id="", profile="demo_house", dance_fx="auto"|preset|"off", stem_orbit=bool, macros={...})` writes those keys into the project that `start_render` sends; `list_looks()` returns the presets with notes, the house summary, the stem_orbit parameters and the 32-stem cap; `review_render(job_id)` runs `media_qa.run_file` on the finished file (loudness vs the house target, clicks, black / freeze, static shots, opening cuts, duration, transition rules) and keeps the report; `get_qa(job_id)` returns that report with the desk's own post-render QA.
