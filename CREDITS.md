# Credits

Checked on 22 October 2026 against the files, the commit that added each one, `src/xenoform/ui_static/objects/objects.json` (which records a source per still), `configs/clip_pack.json`, `scripts/vibe_objects/README.md`, `assets/library/manifest.json` and `configs/moves.json`. Where the repo holds no record of how a file was made, the row says **origin unrecorded**. That is not permission and it was not filled in from a guess. On 31 October 2026 the stills of the first six vibes were traced to the prototype run kept in `scripts/vibe_objects/provenance/` (the stills table below); the picker and poster files that nothing traces still say so.

No picture or clip in this repo is a CC BY work that needs a credit line, so none is stated.

## Vibe stills (`src/xenoform/ui_static/objects/<vibe>/`)

| Vibes | How they were made | Credit |
| --- | --- | --- |
| The 20 extended vibes: chrome-mercury, ferrofluid, y2k-chrome, low-poly, odd-machine, brutalist, porcelain-marble, lava-obsidian, ice-crystal, origami-noir, neon-noir, porcelain-kintsugi, bioluminescent, risograph, iridescent-glass, ink-wash, cyberspace-95, wet-paint, shadow-self, botanical (12 stills each) | Generated locally by the author with Z-Image Turbo (Apache 2.0) through comfy-sdk and comfy-api-proxy: `scripts/vibe_objects/gen_extended.py`, prompts in `extended_prompts.json` and `featured_prompts.json`. `objects.json` names the script and model for every still. | Author's own output. |
| paper-summer (12 stills) | Z-Image Turbo, seeds 2000 to 2011, 1024x576, close framing: `scripts/vibe_objects/zimage_batch.py` with `paper_prompts2.json` (`scripts/vibe_objects/README.md`). | Author's own output. |
| liquid-gold, bloom, neon-night, ocean, cosmic (12 each) and black (17) | Made in the author's overnight library run of 18 and 19 October 2026, before the app, and kept in `scripts/vibe_objects/provenance/` (`README.md` there tells the run): each object a Z-Image Turbo still (the GGUF Q8_0 quantisation, Apache 2.0, ComfyUI, 1024x576, the prompt of `plan.json` and the seed of `objects_seeds.json`); the mercury, chrome, iridescent, oil-slick and black-glass ones a FLUX.2 Klein 4B edit of it (`flux-2-klein-4b.safetensors`, Apache 2.0, seed 77, `klein_edits.json`); the "gr" ones the Z-Image still as drawn (glossy black iridescent ferrofluid). The author's local `library/gpu_objects/` copies of those stills were then regraded with `scripts/vibe_objects/grade.py` (liquid-gold, bloom, neon-night, ocean, cosmic) or cut out onto pure black (black: the script that cut them out was not kept). `objects.json` names the source still, the seed, the models and the grade of every one of the 77, and `lineage.json` records how each shipped jpg was tied to its source still on 31 October 2026 (`grade.py` reproduces the 60 graded ones to 32.8 dB or better; feature matching finds the same object in all 77). The source stills and the run's clips are not in the repo; its prompts, seeds, models and scripts are. | Author's own output. |
| The stills added on 31 October 2026: 367 in 22 vibes (bioluminescent, black, botanical, brutalist, chrome-mercury, cosmic, cyberspace-95, ferrofluid, ice-crystal, ink-wash, iridescent-glass, liquid-gold, neon-noir, none, ocean, origami-noir, porcelain-kintsugi, porcelain-marble, risograph, shadow-self, wet-paint, y2k-chrome), listed in `objects.json` after each pool's first rows | The stills that are on screen in the published Glitch Out cuts, the ten example cuts and the three showcase cuts, copied byte for byte (same file names) from the author's local grown set (`work/ui/objects`, not in the repo) by `scripts/vibe_objects/ship_grown.py`; `shipped_31oct.txt` beside it is the list. Generated locally by the author with Z-Image Turbo (Apache 2.0) through comfy-sdk and comfy-api-proxy, 24 to 30 October 2026: the desk's Library row (`stills.grow`, prompts from `configs/still_prompts.json` and `configs/subjects.json`) and, for 35 of them, the 24 October hand-made sets (`scripts/vibe_objects/gen_v2.py`). Every row of `objects.json` carries the model, the seed, the size, the prompt file and the date; four are wide scenes (`kind: "scene"`). Three more (bioluminescent `123_koi`, iridescent-glass `118_brass_orrery`, origami-noir `001_praying_mantis`) came with the loved morphs that begin or end on them (`shipped_31oct_morphs.txt`), and six black glass flowers (black `025_peony`, `026_dahlia`, `029_orchid` to `032_magnolia`) with the chain preset that pins them (`shipped_31oct_presets.txt`), and four more (low-poly `031_cube` and `032_trefoil_knot`, ink-wash `122_crane` and `123_dragon`) with the two library strips cut from the morphs between them (`shipped_31oct_strips.txt`). | Author's own output. |

## Picker thumbnails (`src/xenoform/ui_static/vibes/<vibe>.jpg`)

| Files | Credit |
| --- | --- |
| `chrome-mercury.jpg`, `neon-noir.jpg`, `porcelain-kintsugi.jpg`, `bioluminescent.jpg`, `risograph.jpg`, `iridescent-glass.jpg`, `liquid-gold.jpg`, `ink-wash.jpg`, `cyberspace-95.jpg`, `wet-paint.jpg`, `shadow-self.jpg`, `botanical.jpg`, `none.jpg` (the 13 featured vibes) | Re-cut on 29 October 2026 (commit `06cf7bb`) from one frame of each vibe's Cloud Final example cut (LTX-2.5 22B distilled, open weights, run on Comfy Cloud, from the vibe's own stills): the centre square of the 9:16 frame on its own blurred ground, 1280x800. The picks (job and second) are in `scripts/vibe_objects/picks_thumbs.json` and, as `excerpt.card_s`, in `examples/cuts/cuts.json`; `scripts/vibe_objects/make_card.py` cuts them. Author's own output. |
| `black.jpg`, `brutalist.jpg`, `cosmic.jpg`, `ferrofluid.jpg`, `ice-crystal.jpg`, `low-poly.jpg`, `ocean.jpg`, `origami-noir.jpg`, `porcelain-marble.jpg`, `y2k-chrome.jpg` | Re-cut on 31 October 2026 the same way from one frame of a 16:9 Cloud Final montage render of each vibe (the jobs and seconds are in `scripts/vibe_objects/picks_cards.json`). Author's own output. |
| `paper-summer.jpg`, `bloom.jpg` | Replaced on 23 October 2026 by the first still of each vibe's pool (see the stills table above; bloom's is the graded dandelion of the overnight run, `scripts/vibe_objects/provenance/lineage.json`). |
| `lava-obsidian.jpg`, `odd-machine.jpg` | Written by the local Z-Image Turbo and LTX-Video 0.9.5 runs of the stills and clip packs above (commits `9c50818`, `43c626b` and later). Author's own output. |
| `neon-night.jpg` | JPEG comment `Lavc60.31.102` (ffmpeg) only. It arrived in the first snapshot commit (`68790ba`) with no generation script or seed in the repo. It shows a neon city and nothing in the overnight run (`scripts/vibe_objects/provenance/`) is a city, so it traces to nothing there. Origin unrecorded. |

## Default clip packs (`src/xenoform/ui_static/library/<vibe>/{wide,medium,close,reveal}.{mp4,jpg}`)

| Files | Credit |
| --- | --- |
| The 22 vibes bioluminescent, black, botanical, brutalist, chrome-mercury, cosmic, cyberspace-95, ferrofluid, ice-crystal, ink-wash, iridescent-glass, liquid-gold, low-poly, neon-noir, none, ocean, origami-noir, porcelain-kintsugi, porcelain-marble, risograph, shadow-self, y2k-chrome | Re-cut on 31 October 2026 by `scripts/vibe_objects/strip_from_clip.py` (ffmpeg, no GPU) from one raw Cloud Final morph of the vibe's own stills (credited above): LTX-2.5 22B distilled, open weights, under the LTX-2.x Community License Agreement of 11 August 2026, run on Comfy Cloud, 1024x576, no audio. wide is the whole frame, medium its centre 1/1.15, close its centre 1/1.5, reveal the wide cut played backwards, each 768x432 at 24 fps with a jpg poster. `configs/clip_pack.json` names the job, the shot and the two stills of each (`source_clip`, `source_morph`) and `docs/demo/records/chains.json` has the job's whole chain. Author's own output. Comfy Cloud's own terms for what its GPUs render were not checked in this audit. |
| lava-obsidian, odd-machine, wet-paint | Cut by `scripts/vibe_objects/make_library.py` from one hand-checked orb to nautilus morph rendered locally with LTX-Video 0.9.5 (Lightricks Open RAIL-M) from the vibe's own Z-Image Turbo stills. `configs/clip_pack.json` records each clip's autotune score and QA note: "All files are generated locally with open weights (Z-Image Turbo stills, LTX-Video 0.9.5 morphs)". Left as they were on 31 October 2026. Author's own output. |
| paper-summer, bloom, neon-night, and the four root files `library/{wide,medium,close,reveal}.mp4` (copies of the neon-night clips) | Regenerated on 23 October 2026: one LTX-Video 0.9.5 morph per vibe from the first two stills of its pool (`scripts/vibe_objects/make_library.py` recipe, seed 2727), cut into wide, medium, close and reveal. Author's own output. |

## Showcase reel and poster

| File | Credit |
| --- | --- |
| `src/xenoform/ui_static/showcase/showcase.mp4`, `.jpg`, `.json` | Rebuilt on 31 October 2026 by `scripts/build_showcase.py` from five of the loved morphs in `examples/morphs/` (Cloud Final: LTX-2.5 22B distilled, open weights, LTX-2.x Community License Agreement of 11 August 2026, run on Comfy Cloud, between the author's own stills), each cut to six beats of "Glitch Out" (`examples/songs/glitch_out.mp3`, made by the author with Suno) from 1:55.8, so the 1:59 drop lands on a cut. The reel it replaced (19 October 2026, five clips cut to the bars of `examples/demo.wav`) was made of LTX-2.3 22B distilled clips rendered locally, under the LTX-2 Community License Agreement of 5 January 2026; its record said LTX-Video 0.9.5, which was wrong. It is in the git history. Author's own output. |
| `src/xenoform/ui_static/poster.jpg` | JPEG comment `Lavc60.31.102` only; first snapshot commit. Origin unrecorded. |

## Loved morphs, clips and example cuts (`examples/morphs/`, `examples/clips/`, `examples/cuts/`)

| Files | Credit |
| --- | --- |
| `examples/morphs/*.mp4` (38 raw clips) and `examples/morphs/morphs.json` | The raw Cloud Final clips of the morphs the author named as loved, made on 29 and 30 October 2026: LTX-2.5 22B distilled (open weights, LTX-2.x Community License Agreement of 11 August 2026) run on Comfy Cloud, each between two stills of the shipped pools (the stills are credited above), no audio. `morphs.json` records the pair, the seed, the style, the timing, the effects, the look and the knobs of each, and the author's words about it. Author's own output. Comfy Cloud's own terms for what its GPUs render were not checked in this audit. |
| `examples/cuts/*.mp4` (13 excerpts) and `examples/cuts/cuts.json` | About 15 s of each of the thirteen 30 s Cloud Final cuts made on 29 October 2026 for the walkthroughs (the ten example cuts and the three showcase cuts), one a featured vibe, 540x960, no audio (`scripts/cut_examples.py`): LTX-2.5 22B distilled (open weights, run on Comfy Cloud) between the vibe's own stills. Seven of the ten example cuts were made to Suno demos of the author's that are not bundled and not credited in this repo, so the excerpts carry no sound and the manifest and its recipe codes name none of those songs; the five whose songs are bundled say so (`song`). Author's own output. |
| `examples/clips/gold_outro.mp4` | The gold outro of the "Glitch Out" music video (phoenix, lion head, dragon, eagle on the infinity knot, scarab, koi; 12 s), a 960x540 copy of the 1080p clip the author cut from the video: the same Cloud Final morphs as above, with the song's last seconds ("Glitch Out", made by the author with Suno). Author's own output. |

## NASA library (`assets/library/manifest.json`)

Public domain. NASA media are generally not subject to copyright in the United States. No NASA endorsement is implied and no NASA insignia is used (https://www.nasa.gov/nasa-brand-center/images-and-media/). The anchor stills are committed; the clips are fetched on first run and by `scripts/fetch_library.py`.

| Item | Source |
| --- | --- |
| SDO: arching eruption off the solar limb (clip) | https://images.nasa.gov/details/GSFC_20150630_SDO_m11908_ArchingEruption |
| SDO: X1.6 flare in 131 Å (clip) | https://images.nasa.gov/details/GSFC_20141024_SDO_m11718_Flares |
| ISS: Earth at night, city lights and lightning (clip) | https://images.nasa.gov/details/GSFC_20181022_ICON_m12902_Airglow |
| ISS: Soyuz relocation time-lapse over Earth (clip) | https://images.nasa.gov/details/jsc2021m000100_Expedition_64_Soyuz_MS17_Relocation_Timelapse_210319 |
| Jupiter, Cassini true colour (anchor still), NASA/JPL/University of Arizona | https://images.nasa.gov/details/PIA02873 |
| Saturn, Cassini natural colour mosaic (anchor still), NASA/JPL/Space Science Institute | https://images.nasa.gov/details/PIA06193 |
| Earth, Blue Marble, Suomi NPP (anchor still) | https://images.nasa.gov/details/PIA18033 |
| Moon, Galileo (anchor still), NASA/JPL | https://images.nasa.gov/details/PIA00405 |
| Mars, Viking 1 mosaic (anchor still), NASA/JPL/USGS | https://images.nasa.gov/details/PIA00407 |

## Moves driving clips (`configs/moves.json`)

Fifteen dance clips, ten from Pexels and five from Mixkit, used only as motion sources for Wan Animate 2; the dancer's face never appears in the output. Their licences allow free use but forbid redistributing the unaltered files, so the mp4s are not shipped. `python scripts/fetch_moves.py` downloads them into `library/moves/` (git-ignored). Every clip's title, author, source URL, licence and attribution line is in `configs/moves.json`.

## Free film pack (`configs/film_pack.json`)

Not in the repo. Version 2 (1 November 2026): 40 short clips from 29 sources, pulled on request: Setup & models has ffmpeg read each window straight from its archive.org or NASA URL into `work/ui/film_pack/` (under `work/`, which git ignores). Every source's title, year, maker, page, URL, the file taken with its size, and its licence line is in `configs/film_pack.json` (the licence bases are in [docs/LICENCES.md](docs/LICENCES.md)), and each download writes them, with the clips and their times, to `work/ui/film_pack/CREDITS.md` beside the clips. Where a source is NASA footage, no NASA endorsement is implied and no NASA insignia is used. The sources:

- Ocean Moon Glint and City Night Lights (2017), NASA (Jack Fischer, from the ISS). https://archive.org/details/Ocean-Moon-Glint-And-City-Night-Lights-In-4K-UHD
- Ultimate Saturn V Launch (1969), NASA Marshall Space Flight Center. https://images.nasa.gov/details/Ultimate%20Saturn%20V%20Launch%20w%20Enhanced%20Sound
- Design for Dreaming (1956), MPO Productions for General Motors. https://archive.org/details/Designfo1956
- Show 'Em the Road (Part II) (1954), Sid Davis Productions for General Petroleum. https://archive.org/details/ShowEmth1954_2
- Time-Lapse Astronaut Photography of Earth: Aurora Australis, Madagascar (2011), NASA Johnson Space Center. https://archive.org/details/Time-lapseAstronautPhotographyOfEarth
- Ingenuity in Action (Part II) (1958), Sid Davis Productions for Hot Rod Magazine. https://archive.org/details/Ingenuit1958_2
- Metropolis (1927), Fritz Lang. https://archive.org/details/metropolis-1927_202511
- STS-133 Space Shuttle Launch (2011), NASA Kennedy Space Center. https://archive.org/details/NASAKennedy-RxFwUG9PiYM
- A Touch of Magic (1961), MPO Television Films for General Motors. https://archive.org/details/TouchofM1961
- At the End of the Rainbow (Part I) (1946), The Jam Handy Organization for Sun-Kraft. https://archive.org/details/AttheEnd1946
- New Orleans Carnival Week, February 22, 1941 (amateur film) (1941), unknown amateur. https://archive.org/details/NewOrlea1941
- Volcano Eruptions (1959), United States government (National Archives, FedFlix). https://archive.org/details/gov.archives.arc.68933
- Solar Highlights of 2016/2017: Twisting Solar Material (2016), NASA Goddard Space Flight Center (Solar Dynamics Observatory). https://images.nasa.gov/details/GSFC_20160624_SDO_m12292_TwistingSolarMaterial
- Supersonic Thunderbirds (1959), United States Air Force (National Archives, FedFlix). https://archive.org/details/gov.archives.arc.67591
- 6 1/2 Magic Hours (1958), Kahlenberg for Pan American World Airways. https://archive.org/details/612Magic1958
- A Trip to the Moon (1902), Georges Méliès. https://archive.org/details/levoyagedanslalune_georgesmelies
- American Harvest (Part I) (1955), The Jam Handy Organization for Chevrolet. https://archive.org/details/American1955
- Cosmic Careers: Divers (2024), NASA Johnson Space Center. https://images.nasa.gov/details/CosmicCareers_Diving_Videographer_edit._MP4
- Air Force Now: Thunderbirds (undated), United States Air Force. https://archive.org/details/AirForceNow-Thunderbirds
- World's Fair Night Aerials (1964), unknown (New York World's Fair footage). https://archive.org/details/tmp_1964Worl
- American Thrift (Part II) (1962), The Jam Handy Organization for Chevrolet. https://archive.org/details/American1962_2
- Midwest Holiday (Part II) (1952), Wilding Picture Productions for Standard Oil. https://archive.org/details/MidwestH1952_2
- Volcanoes (1955), Art Carter. https://archive.org/details/volcanoes
- Time-Lapse Astronaut Photography of Earth: Aurora Australis, Australia to New Zealand (2011), NASA Johnson Space Center. https://archive.org/details/Time-lapseAstronautPhotographyOfEarth
- Artemis I Isolated Launch Views (2022), NASA Kennedy Space Center. https://images.nasa.gov/details/KSC-20221116-MH-AJN01-0001-Artemis_I_Isolated_Launch_Views-3314595
- Time-Lapse Astronaut Photography of Earth 2: Halfway Across the World (2011), NASA Johnson Space Center. https://archive.org/details/Time-lapseAstronautPhotographyOfEarth-2
- Steamboat Willie (1928), Walt Disney and Ub Iwerks. https://archive.org/details/steamboat-willie-1928-by-walt-disney
- Your Fire Department (Part I) (1949), Los Angeles Fire Department. https://archive.org/details/YourFire1949
- To New Horizons (1940), The Jam Handy Organization for General Motors. https://archive.org/details/ToNewHor1940

## Fonts

Both families are under the SIL Open Font License 1.1; the copyright lines and licence text are in `src/xenoform/ui_static/fonts/OFL.txt`.

| Font | Copyright |
| --- | --- |
| Space Grotesk | Copyright 2020 The Space Grotesk Project Authors |
| Share Tech Mono | Copyright (c) 2012, Carrois Type Design, Ralph du Carrois, with Reserved Font Name 'Share' |

## Sound

| File | Credit |
| --- | --- |
| `examples/demo.wav` | Synthesised by `xenoform synth` in this repository. No third-party recording. |
| "Morph Engine v2" (the song in the contest demo video) | Made by the author on Suno Pro on 20 October 2026, inside the Pro billing period, so the author owns it with commercial-use rights under Suno's terms. Not shipped. |

## Bundled songs (`examples/songs/`)

Six instrumentals made by the author with Suno, added on 29 October 2026 and included for use with Xenoform. The manifest is `examples/songs/songs.json`; each song ships with its analysis (`<id>.features.json`, made by `scripts/analyse_bundled_songs.py`). No third-party recording.

| File | Title | Credit |
| --- | --- | --- |
| `morphing_wobble_20s.mp3` | Morphing Wobble (20 s) | Made by the author with Suno; included for use with Xenoform. |
| `morphing_wobble.mp3` | Morphing Wobble | Made by the author with Suno; included for use with Xenoform. |
| `hip_hop_boom_bap.mp3` | Hip hop, boom bap | Made by the author with Suno; included for use with Xenoform. |
| `liquid_dnb.mp3` | Liquid drum and bass | Made by the author with Suno; included for use with Xenoform. |
| `ambient.mp3` | Ambient | Made by the author with Suno; included for use with Xenoform. |
| `glitch_out.mp3` | Glitch Out | Made by the author with Suno; included for use with Xenoform. |

## Models

Model licences (LTX-Video 0.9.5, LTX-2.3, Z-Image Turbo, Wan Animate 2, Real-ESRGAN, FLUX.2 Klein, ACE-Step) are in [docs/LICENCES.md](docs/LICENCES.md).
