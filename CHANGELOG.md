# Changelog

## 0.3.3 (unreleased, the week to the contest)

- Simple mode knows where you are: a Song > Vibe > Make > Video strip on every screen, a Back button first on the result screen, the showcase as its own screen ("Showcase, made earlier", one way on, no Share or Re-cut for a reel you did not make), the phase in the URL (`#simple/result`, `#simple/showcase`) so the browser's Back and Forward work, and the logo as a home button. One setter (`setEasyPhase`) replaces eleven scattered phase writes.
- Controls fit: segmented rows wrap instead of crushing their labels, the Look chips wrap everywhere, Fine-tune moves out of the 340 px side column into the main column under the knobs, header actions wrap, the desk goes one-column under 1000 px, and the Model and GPU chips are short with the detail in the note under them.
- An honest clock: the bar is seeded from the plan's own estimate and follows the server's weighted progress (`job.overall`); the text reads "m:ss elapsed · stage · about m:ss left" with the server's remaining time (`job.eta_s`) when it sends one, and never "almost there" outside the last stages; the result screen says "Took m:ss" with a morphs / Polly / cut / check breakdown. The job records `t0`, per-phase timestamps, `took_s` and `breakdown` (also in `took.json`), the end card, the save and each QA pass report progress, and My videos carries each video's render time (with a fallback for older folders).
- The look pass runs the shots over worker processes (`beatfx.look_workers`, up to six of the spare cores, `XENO_LOOK_WORKERS` to pin it): the same frames, byte for byte, stitched in order with the transitions; a 30 s cut's compose went from 85 s to 30 s on the 3080 Ti box, and a full song's from about nineteen minutes to six or seven. The plan estimate knows (`look_speedup`).
- The foreshadow layer (`xenoform.foreshadow`, Fine-tune → Foreshadow): the next object arrives before its shot, the way a new sound is introduced before it takes the song. In the tail of every shot the object the next morph lands on (or, across a hard cut, the performer's or own clip's first frame) is brought in as a glowing edge trace in the vibe's tint, a luma-flipped ghost, strips that interleave and multiply, or a tint-filled silhouette; the amount ramps over a bar or so (Speed), rides the song's "other" stem under the Intensity cap (Chaos sets the slice count and jitter, Glow the halo), and across a hard cut the object that just left echoes out for a beat. Auto traces on a dark vibe and slices on a bright one; it runs inside the parallel look pass before the house look, so the look grades it as part of the picture. The record and the re-cut carry it.
- A shots lane under the result player (`xenoform.lane`, `GET /api/videos/{id}/shots`): the finished cut as a read-only strip, one block a shot sized to its share of the cut and coloured by section, the object each morph lands on, the transition at each boundary, Polly's and your own clips' slots as bars above; a click seeks the player. The seed of the timeline.
- Honest when ComfyUI is down: the Simple make screen says "not answering: Make will play the vibe's pictures in the browser, no render" and the result says the same with the address and how to fix it, instead of the silent "Playing the pictures" fallback; Advanced's "Live" tier is "Browser preview" (no model, no GPU).
- Every featured vibe but ink-wash carries its own default look (`fx_defaults.dance_fx` in `configs/vibes.json`): chrome cool-echo, neon-noir and shadow-self noir-glow, porcelain and gold warm-leak, bioluminescent, wet-paint and botanical bloom-rush, iridescent glass and cyberspace cyan-flash; risograph is off (a page is a page: negative-rush washed it to cream in the test drive). Look "Auto" picks it.
- Version 0.3.3 in `pyproject.toml` and the package; the docs test accepts a real demo link in the README top block.
- The stills library grows on your GPU (`xenoform.stills`, Fine-tune → Library, `xenoform stills grow|import|status`, `GET /api/stills`, `POST /api/stills/grow|stop`): the repo's seed set and a local set under `work/ui/objects` are one pool; Grow renders catalogue subjects (`configs/subjects.json`: 24 families, 395 nouns, weights per vibe) with the style prefix each pool was made with (`configs/still_prompts.json`), checks every still against its pool (backdrop drift, subject size, cropped, soft, duplicate by correlation) and sets rejects aside; Your own shapes are typed subjects rendered in the vibe's material and put first in the chain; `pick_stills` prefers the objects a vibe has used least (`usage.json`), so two cuts of one song open on different objects and a cut never laps a library bigger than itself. The 24 Oct batch imported through the checks: 335 kept of 432.
- Taste on long songs: a long song's morphs are distinct pairs (`morph_pass.chain_walk`: 24 morphs over 12 objects are 24 pairings, not 12 twice); the drop gets a real transition in the Simple cut (a vibe's scene-morph pick is a match-cut there, since no GPU scene morph is rendered); every featured vibe carries premium picks in `configs/vibes.json` and the registry now wins over the old table; and the story plan has a pace: `pace: "viscous"` cuts the loud passages on two bars and the drop on the bar, so a 3 s morph plays at or under real time like the demo's pour (`dense.STORY_BEATS_VISCOUS`). Viscous is the Simple default: the 60 s A/B on Glitch Out (24 Oct) went to it on pour tempo, the drop transition and colour, with 18 shots against 33. `pace: "tight"` in the make body keeps the denser plan.
- Housekeeping: the stale "about 1 minute" promise is gone, the VJ link carries the song and stems and opens in a new tab, VJ mode has a Desk link back, About is reachable in Simple, and the vibe and Fine-tune choices survive a reload or a desk restart (localStorage `xeno-easy`). The direction for the week is in docs/DIRECTION.md.

## 0.3.2 (24 October 2026)

- Performer shots open on the performance, not on the reference still. The song is now fed two seconds early (plus the grid's spare frames) and the clip starts where the performance has begun: past a held still, a hard cut, or a dissolve, which a new resemblance check against the fitted still detects (`performer.resemblance`, `still_gone`). The one-second pre-roll it replaces left 7-30 spare frames, so the skip was clamped and up to half a second of the standing still leaked into the drum slot of the 30 s test. A shot whose still would still leak more than half a second, or a singing shot that would run that far ahead of the music, is re-rolled once, whatever she plays; `leak_frames` and `drift_frames` are in the result and the job's `simple.json`. A Length cut hands the performer its source song (`song_source`), so a slot at the top of the cut still has two seconds of real music before it.
- Polly's posed reference stills ship beside `polly.png`: at the kit, the microphone, the keys, with a guitar and two dance poses (`polly_drums.png`, `polly_vocals.png`, `polly_keys.png`, `polly_guitar.png`, `polly_dance.png`, `polly_dance_2.png`; Z-Image Turbo, `scripts/performer_refs/gen_polly_refs.py`, the closest likeness of eight seeds a pose picked by eye). `performer.default_reference(instrument, pick)` hands MiniMax H3 the still for the slot's performance, so the shot starts at the instrument instead of cutting to it; numbered variants rotate by slot.
- The auto performer mix has more dance: she sings where the vocal stem sings, drums on the first drop, dances on the other loud passages, and the quiet passages go keys, dance, guitar, dance (`dense.PERFORMER_QUIET_CYCLE`).
- Your own clips and images in Simple mode (Fine-tune → Your footage: a folder on this machine, or files dropped or picked on the row, `POST /api/own`). The images lead the vibe's morph chain as morph targets, in name order; each clip is cut in on the beat as one run of shots at the start of a passage (2 to 8 s, the first unused clip that fits, never beside a performer shot), trimmed around its middle, cover-cropped to the aspect and played 1:1 with the beat FX, the look and the transitions like any shot (`own_media.py`, `dense.run_simple`, the job's `simple.json` `own` record).
- The Make body takes `length_start` (seconds into the song) with `length_s`, so a Length cut can be placed on a passage of your choosing (a verse with a vocal, say) instead of around the drop.
- Fixed: a cut ended at the shot after its first premium transition. In `beatfx.compose` the transition window's half-length was assigned to `h`, the output frame height, so every later frame was reframed six pixels tall and ffmpeg's raw stream collapsed there; the record still claimed the full frame count. Every story-plan cut with a transition before its last shot was short (the 30 s performer tests came out 20 s long). The window half is its own name now, the writer resizes any frame of the wrong size with a warning, and the test probes the written file.
- Final tier measured on a 20 s Simple cut at native 9:16 (LTX-2.3, 11 morphs of 4-5 s, upscaled to 1080x1920): 56 minutes on the 12 GB 3080 Ti, no fallbacks, against a 17-minute estimate; the estimate now counts each morph at the length the Final tier really renders and adds a quadratic term for the seconds beyond 2 (`final_tier.ETA`), which lands within four percent of that run.
- The performer time estimate is refit on the measured shots (linear in the frame count, 192 s floor; about 8 minutes per 5 s shot with the pre-roll on a 12 GB card).

## 0.3.1 (23 October 2026)

- Performer shots (optional, off by default): MiniMax H3 (open weights, runs locally through the Comfy SDK) has Polly perform the song itself: singing only where the vocal stem sings (lip-synced to the vocal), drums on the drop, keys elsewhere, or the Performance chip you pick; her outfit is pinned to the reference; in two or four slots cut 1:1 into the morph chain (`performer.py`, `dense.performer_slots`, Fine-tune → Performer). A one-second pre-roll hides the held reference still; a shot that holds it anyway is re-rolled once. About seven minutes per 5 s shot on a 12 GB card (measured; the turbo LoRA does not speed up a card that streams the weights). LTX-Video stays the core morph model.
- Story plan (`dense.story_plan`): a full song is cut by its sections. Intro and verses breathe (two bars a shot, real-time morphs), builds and choruses drive (a bar a shot, downbeat punches), the drop punches and runs half bars for eight bars, the outro eases out; the analyser's slivers are merged into passages first.
- Premium transitions at section switches: the vibe's recommendation per boundary (drop / switch / silence), capped at two of a kind, rendered inside compose over a window centred on the cut so the beat sync never moves.
- Re-cut from the cached morphs: `POST /api/jobs/{id}/recut` and the Re-cut button on the result screen re-compose with new knobs, look, orbit or beat FX without the GPU.
- Stems by default: the split starts in the background when a song is analysed, so the first Make is already stem-reactive (Demucs when installed, the band split otherwise).
- The knobs (Intensity, Speed, Chaos, Glow) and the Look chips sit on the first screen of Simple mode. Chaos now shapes the cut: punches scale with it, stutters, holds and skips vanish when calm and double when wild, and the subject's orbit swing follows it.
- The Auto look takes its colours from the vibe's own stills (`dance_fx.palette_tints`): shadows, highlights, edge tint, washes and flashes follow the vibe's palette instead of a fixed blue cast. A named preset keeps its colours.
- Draft 9:16 renders the morphs natively in portrait (320x576) from stills re-laid whole on black, so wide objects are not clipped by a 9:16 crop of a 16:9 render; the stills draft does the same.
- Fine-tune has Machine rows: Model (Draft LTX-Video 0.9.5 / Final LTX-2.3), GPU preset (auto-detected or CPU, 8, 12, 24 GB; the job honours it), the ComfyUI address, and the paid cloud switch (off by default, not open weights).
- Full-length songs in Simple mode: the Dense cut keeps a shot every bar (every half bar after the drop) however long the song is, over a closed loop of 12 to 30 four-second morphs (`dense.clip_plan`), so a four-minute song is a music video instead of eleven morphs stretched into a slideshow. The panel beside Make shows the video length, shots, morphs and a time estimate that includes the look pass.
- **Length** in the Fine-tune drawer: the whole song, or a 60, 30 or 15 second cut centred on the drop (starts on a beat, short fades), analysed as its own song.
- The Simple draft is the vibe's stills cut to the plan (seconds) instead of the CPU blob animatic, which took minutes on a long song.
- A render could fail with `Access is denied` when the browser was still playing the draft while the next version was swapped in; publishing now retries and falls back to copying the bytes into place.
- `dance_fx` blurs run on a reduced copy and the pixel grid is cached: the look pass is 3 to 4 times faster. Draft composes at 540x960.
- A job without a story (API, MCP) no longer crashes in the director; one hold spans the song.
- The original vibes' library strips (liquid-gold, paper-summer, bloom, neon-night, ocean, cosmic) are regenerated from each vibe's own stills with LTX 0.9.5; four stock-looking picker thumbnails replaced by pool stills.
- `media_qa` loudness is BS.1770-4 K-weighted and agrees with ffmpeg ebur128; the click scan is calibrated on the demo mix.

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
