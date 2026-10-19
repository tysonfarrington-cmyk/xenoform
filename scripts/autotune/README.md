# Morph auto-tune (overnight, local)

This script tunes Simple mode's morph engine (LTX 0.9.5, `workflows/xenoform_morph.json`) by rendering single A->B morphs through comfy-sdk -> comfy-api-proxy and scoring each one. Everything is free and local: no API keys, no tokens, no cloud.

- `autotune.py`: the runner. It is resumable: `runs.jsonl` is replayed on start. It stops queuing jobs before `--until`, keeps the VRAM peak under 11.5 GB (a resolution that goes over is banned), and starts ComfyUI with `run_comfy_3080ti_tf32off.bat` only if it is down when the run starts. It never restarts a running ComfyUI.
  - Phase 1 renders the shipping default (20 steps, cfg 3, compression 18, vibe prompt, 512x288) on every adjacent pool pair. Those are the pairs Simple mode renders.
  - Phase 2 is a small evolutionary search per vibe over steps 12/16/20, cfg 2/3/4, compression 0/18/30, prompt vibe/pair/plain, 512x288 or 640x352, and end-guide strength 1.0/0.85. It uses UCB on pair-centred scores, so a hard pair doesn't count against a setting.
- `score.py`: the CPU scorer. It runs under ComfyUI's venv, which already has torch, transformers and OpenCV. It compares the middle of the morph with the clip's own first and last frames:
  - exposure drop
  - contrast drop
  - haze (mid-band detail ratio plus dark channel)
  - crosshatch (high-frequency to mid-band energy ratio, plus spectral peaks)
  - smoothness (frame-difference pops and luma jitter)
  - endpoint match to the stills (PSNR)
  - CLIP ViT-B/32 on the CPU: whether the frames look like the A or B object rather than a blob or noise, and a quality prompt pair
  
  The total is out of 100. `cal.py` scores a list of known clips.
- `run_overnight.bat` and `schedule.ps1`: a one-off scheduled task, `XenoformAutotune`. It starts at 23:00, the runner stops itself at 06:30, and Task Scheduler kills it at 06:40 at the latest.

## Outputs (`judge_logs/autotune/night/`)
- `runs.jsonl`: every clip, with settings, score, sub-scores, raw metrics, render time and VRAM peak.
- `leaderboard.csv`: configs ranked by pair-centred advantage.
- `recommended.json`: per vibe, the best setting within the 8 s/morph budget, the best at any speed, and the default's advantage.
- `bad_pairs.json`: pool pairs that score well under their vibe's median, with their weakest sub-scores.
- `autotune.json`: the app-readable bundle. After review, copy it to `configs/autotune.json`. `morph_pass` then uses each vibe's steps, cfg, compression and end-guide strength, and reorders the pool so no blocklisted pair is adjacent. `XENO_AUTOTUNE` points at another file, and `XENO_MORPH_STEPS` still wins for steps.
- `contact_best.jpg`, `contact_worst.jpg`, `best_of_reel.mp4` (the top two per vibe), `clips/`, `autotune.log`, `runner.log`.
