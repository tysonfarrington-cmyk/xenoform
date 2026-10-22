# Changelog

## 0.3.0 (22 October 2026)

The contest round. Everything below runs on open weights on a local GPU through the Comfy SDK and `comfy-api-proxy`.

### Simple mode and the house look
- Simple mode is three decisions: song, vibe, Make. Everything else moved into a Fine-tune drawer.
- Default aspect is 9:16, rendered natively in portrait (LTX-2.3 at 448x768, Real-ESRGAN x4plus to 1080x1920); 16:9 and 1:1 remain.
- `demo_house` default profile (`configs/defaults_demo.json`, `demo_house.py`): 9:16 at 24 fps, black morph grounds, no shimmer, 15 forms per 20 s, the look per shot, transition rules, -14 LUFS.
- `dance_fx`: stem-reactive, subject-safe looks for character and object shots (split-tone grade, halation, light echo, edge tint, beat light leak, glass, wash, bleed, negative). Presets `warm-leak`, `cool-echo`, `noir-glow`, `bloom-rush`, `negative-rush`, `cyan-flash`; `auto` follows the house roles (cyan-flash intro, cool-echo body, negative-rush into the end card).
- `stem_orbit`: rigid, spring-damped audio-reactive subject rotation (yaw from the bass, kicks from strong drum hits, pitch from the rest). Needs OpenCV, now a dependency.
- Macro knobs Intensity, Speed, Chaos, Glow on the job payload (`macros`), wired to beat FX, morph count, echo length and bloom.
- Forms control: Auto from clip length and BPM, or 1 to 40; recipe codes carry it.
- Guardrails (`configs/guardrails.json`): every render clamps known flaky settings and reports what changed; expert mode warns only.
- No-repeat sources in the morph path and the auto-editor (path plus perceptual hash); fewer, longer morphs when a still pool would wrap.
- Final tier ETA from measured LTX-2.3 fp8 shots; per-shot fallback (no upscale, then the Draft shot) on failure or out of memory.

### Stems and MIDI
- Up to 32 stems split in-app: `POST /api/stems`, `GET /api/stems/{id}`, `xenoform stems`. Demucs on the CPU when installed (`.[stems]`), librosa band split otherwise. One reaction lane per stem, per-stem gains as `macros.stems`.
- MIDI: Web MIDI on the desk and the VJ page, Arturia MiniLab 3 factory map, learn mode, JSON export and import. Python bridge `xenoform midi list|serve|record` (`.[midi]`) feeds browsers without Web MIDI and converts recorded takes to per-frame curves.
- VJ mode at `/vj`: mic or line-in, loaded-track beat grid, the song's real stems through four uniforms, premium shader transitions, mirror, strobe, HUD, fixed-size webm recording.

### Transitions
- Six premium transitions (`match-cut`, `flow-carry`, `depth-parallax`, `lens-breath`, `chrome-refract`, `echo-trail`) plus the clean `cut`; at most two uses of any type per video (`transition_variety`), overflow becomes a clean cut. `luma-wipe`, `stutter-cut` and `zoom-through` are expert-only Classic.
- `scene-morph`: LTX-2.3 first/last-frame render from clip A's last frame to clip B's first, native 9:16, with a CPU `flow-morph` fallback.

### Vibes and footage
- 29 vibes in the registry (`configs/vibes.json`), 12 featured. 20 extended vibes with 12 Z-Image Turbo stills each and a default clip pack cut from a checked LTX 0.9.5 morph (`configs/clip_pack.json`). Featured vibes without their own stills borrow a pool.
- NASA public-domain anchor stills for Jupiter, Saturn, Earth, Moon and Mars; `shot_qa` flags duplicated planet features and rerolls once.
- NASA seed clips fetched from the original masters on first run (not committed; `XENO_OFFLINE=1` skips).
- Real footage: `xenoform.footage` scans, detects scenes and plans a beat cut; `camera_roll` orders stills by visual distance; `scene_edit` renders a spec.
- Moves (beta): Wan Animate 2 copies a real dancer's motion onto a character still (`/moves`, `workflows/moves_wan_animate2.json`, 480x832, 81 frames, 11.6 GB peak). Fifteen Pexels and Mixkit driving clips listed in `configs/moves.json` and fetched by `scripts/fetch_moves.py`.

### QA
- `media_qa` (`python -m xenoform.media_qa video.mp4`): loudness and true peak against the house target, clicks, black and frozen frames, static shots, opening cuts, duration, transition rules, text legibility.
- Post-render QA on every job: freezedetect, mpdecimate, fps conform and interpolation, beat-alignment report with a 40 ms snap, low-res gate, artifact flags.

### MCP and AI
- MCP server rebuilt on the official Python SDK, 45 tools: status, catalogue, project, render, recipes, AI director, storyboard, guardrails (`list_guardrails`, `check_guardrails`) and the look (`set_look`, `list_looks`, `review_render`, `get_qa`). Prompts `get_started`, `make_music_video`, `review_cut`; resources incl. `xenoform://guide` from `docs/AI_GUIDE.md`. Stdio and streamable HTTP on `127.0.0.1:47319/mcp`. Paid tiers need `confirm_spend=true`.
- Versioned `xf2.` recipe codes carry transitions and shot edits; `xf1.` and `XF-` still decode.

### Install and packaging
- Python 3.12 required (`requires-python >=3.12`, CI on 3.12). `install.sh` now installs the package; `opencv-python-headless` is a dependency.
- `Xenoform.bat` sets up `.venv` on first run, starts `comfy-api-proxy` on 8189 and the desk on 47317, with `XENO_PORT` and `XENO_PROXY_PORT` overrides and per-port logs.
- `[project.urls] Repository` is the public repo; the end card burns it.
- Paid paths (LTX-2.5 partner node, Comfy Cloud backend, Add-ons) stay off by default behind `XENO_PAID_CLOUD`, `comfy.backend` and `XENO_ADDONS`; `tests/test_eligibility.py` audits every default workflow.

### Docs
- README rewritten around the contest block, Simple mode and the open-weights table; details moved to `docs/`.
- New: `docs/REPRODUCE.md`, `docs/CONTEST.md`, this changelog, `tests/test_docs.py`. `CREDITS.md` and `docs/LICENCES.md` record how every shipped picture was made, with Wan Animate 2 and the lightx2v LoRA added to the licence table.

## 0.1 and 0.2

The stage pipeline (`synth`, `analyze`, `render`, `restyle`, `assemble`, `osc`), the director desk with registers, Director's notes, Review & fix and versions, the first Simple mode (Energy, Aspect, Quality, 15 s hook, recipe codes, My videos), the Final tier, the overnight autotune, and the judges page.
