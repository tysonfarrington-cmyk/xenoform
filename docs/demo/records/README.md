What the published and shipped cuts were made of (31 Oct 2026). `work/` is git-ignored and a job's `simple/simple.json` holds
absolute paths, so these keep what would be lost with the machine. `docs/demo/tools/plans/` keeps only slot label to job id.

| File | What it is |
| --- | --- |
| `as_cut_169.json`, `as_cut_916.json` | The "Glitch Out" music video as it was cut, the 16:9 (3:58, the YouTube upload) and the 9:16: 34 slots each, written by `docs/demo/tools/montage.py` on 30 October (16:29 and 16:54) and copied as they were. A slot has its label (the one in `docs/demo/tools/plans/montage_*.json`), the Cloud Final job it played, the song seconds it covers (`song_in` to `song_out`), the second of that job's cut it began at (`cut_in`) and its `frames`; `title` is where the title card lands and `gain_db` the song's level. A label ending in `@169` is the 16:9 render cropped into the 9:16 cut. 62 different jobs in all. |
| `chains.json` | One record per job, 96 in all: the 62 above, the thirteen example and showcase cuts (`examples/cuts/`), the jobs of the loved morphs (`examples/morphs/`), the chain presets (`configs/chain_presets.json`), the contest demo's segments and the five film-pack cuts. What each was made of: the vibe, tier and engine, the seed, the morph style, timing, effects, look, foreshadow and knobs, the idea line, the stills in chain order and the pair each shot's morph runs between, every shot's start, end, render seconds and speed, and the `xf1.` recipe code. No paths. A song that is not bundled is named neutrally: the 29 October Suno demos were uploaded under file names that name artists and are not credited in this repo, so neither the records nor their recipe codes carry one. `scripts/export_records.py` writes it from the job folders. |

`chain`, `pins` and a shot's `from` and `to` are file names of `src/xenoform/ui_static/objects/`. The stills that were on screen in
a published cut or an example excerpt are shipped there (444 of the 797 the records name); the rest stay in the author's grown set,
so a pin on one of them is dropped on another machine. A recipe code carries no pins: `chains.json` has them.
