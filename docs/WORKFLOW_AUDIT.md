# Workflow audit: one desk instead of two, 26 October 2026

Tys, after being stranded in the Advanced desk: "audit the workflow of the app, it needs a major improvement; get rid of the
simple/advanced and combine it into one; the simple can be kept as a prototyping stage if you want quick results."

This page is that audit and the proposal. It was made by reading the code behind every screen (`src/xenoform/ui_static/app.js`,
`index.html`, the CSS, `ui.py`, `guardrails.py`, `transitions_fx.py`, `turbo.py`, `director.py`) and by driving the preview desk on
port 47322 at 1280 px wide as a first-time visitor would: the demo song, every rail step of Advanced, the logo and Back after the
toggle, a reopened cut (H6 chrome) and its "Open in Advanced" button. Nothing was rendered and nothing was restarted. Line numbers
are from commit 7a3872b on `contest-rc2`.

The one-line finding: **Simple is the product and it mostly works; Advanced is an older app with its own render path, its own
monitor, its own libraries and its own recipe format, reachable through a toggle that has no way back.** The fix is not to polish
Advanced but to take the six or seven controls in it that a Simple user would want, hang them off the Simple stages as drawers, and
delete the rest from the desk (the API behind them can stay for MCP).

---

## 1. The two desks today, screen by screen

### 1.1 Simple (`#simple`, `renderEasy` at app.js:2412)

**S1 · Choose** (`#simple`). Header: brand, the ComfyUI pill, Open weights, Tutorial, a "…" menu (Copy diagnostics, About, Reset
tutorial), **Advanced**. Under it the floating "Expert: override guardrails" checkbox with no context. Then: the Song › Vibe › Make ›
Video crumbs; "Make a music video."; **The drop** card ("The big moment is at 0:05", Play the drop); **Song** (Choose a song, Bundled
demo); **Vibe** (12 featured cards plus Cosmic, a "More vibes · 14 more" drawer, the idea line with Dice and two sample ideas);
**Knobs** (Intensity, Speed, Chaos, Glow, Reset, Stem reactions, MIDI controller, then the Look chips, the Foreshadow row and the
Scenes row); **Fine-tune**, one drawer with fifteen rows (Energy, Aspect, Length, Model, Performer, GPU, Renders on, Paid cloud,
Forms, Beat FX, Subject orbit, End card, a five-sentence note, Your footage, Library with Grow 36 / Grow 8 scenes / Your own shapes /
Make them) and under it "Beat overlay · off", "Paste a recipe code" and **My videos**. The side column: the vibe's sample monitor and
filmstrip, four facts (Video, Shots, Cut, Time), **Make my video**, the house line, a Moves link, a VJ link, a MIDI button, "Watch
a finished one", the ComfyUI note, Open weights.

**S2 · Making** (`#simple/making`). The monitor shows the stills draft within seconds, a filmstrip, a bar, "What is happening"
(Listened, Wrote the story, Painting the shots, Cutting to the beat), the honest clock, Stop. "You can leave this page."

**S3 · Result** (`#simple/result`). Back to the song first, then Share cut, 15 s hook, Copy recipe code, Download; the player; the
shots lane; the Took line and the recipe. The side column: Energy (Calm to Hype), the Knobs again, Look, Foreshadow, Scenes,
**Re-cut with these knobs**, **Try another vibe** (twelve small cards), Make it better, **Open in Advanced**, Back to the song.

**S4 · Showcase** (`#simple/showcase`). The pre-rendered reel, "Make your own", Download the showcase, Open in Advanced.

What already holds (landed 24 to 26 Oct and checked again today): the phase is in the URL, so Back, the crumbs and the logo agree
inside Simple; vibe and Fine-tune choices survive a reload; the clock is the server's; the showcase is its own screen; Reopen from
My videos lands on `#simple/result` with the right title. The judge path in `docs/REPRODUCE.md` steps 2 and 5 is this desk and it works.

### 1.2 Advanced (the header toggle, `renderAdvanced` at app.js:801)

The toggle sets `document.body.dataset.advanced = "1"` and a localStorage flag (`syncAdvanced`, app.js:6847). The hash does not
change. The header grows a nav (Overview, Director, Notes, Connect, Setup, Judges), Settings, "Advanced on", Review & fix, a gate
line ("Live stays in the browser.") and a Generate button that reads **Record** while the quality is Live.

Every Advanced screen is the same frame: a left rail "Your video" with eight numbered steps and four links, a **monitor** in the
middle, an inspector on the right, and a **Timeline** across the bottom. The monitor on arrival is "Browser preview": a purple
liquid blob on black with Play, Record, Live+AI, a Live / Turbo / Draft / Final quality pill, and the caption "Pynchon · seed 2727 ·
Cold violet · Dry run is the default".

| Rail step | Hash | What the inspector holds |
| --- | --- | --- |
| 1 Song (nav "Overview") | `#simple` | Pick or drop a song; Song timing (beat grid, section map, Lyric align with offset and transcript); Guided tours |
| 2 Story | `#simple` | One-line brief, Scale journeys (Shuffle, Dice), Callback, Try the demo / Generate this brief / gate / Open the shots / Music only, the shot list, the scene cards |
| 3 Cast lock | `#simple` | Cut: Calm to Hype slider and beat grid; Story with Approve shot list and Conform; Hero lock (reference image), Continuous take, Title card, End card, QA |
| 4 Look | `#director` | A **Register** strip (Pynchon, le Carré, Tolkien, Rome, Custom, Drop card, Outro card) appears above the whole desk and pushes it down; Treatment "Pick the three moments"; Looks presets, Roll the board; an `XF-` recipe box; Band map |
| 5 Shots | `#director` | Storyboard cards (seven Pynchon rocket shots on the demo) each with a per-shot Look select, Open, Motif; **Transitions, one per boundary** (a 14-kind select per row, max 2 of a type); **Shot review** (Keyframe, Clip, Prompt, Remake, New seed, Test clip) for every shot |
| 6 Morph | `#director` | "Blend two shots that already exist": a source clip, four method chips (Keyframe blend, Cross clip, Video ramp, Staged region) in one pill, Fast, Hit flash, Check the joins, a QA chip; **Source library · Partners for this scene**: five `sample_*` shapes with Pin and Ban |
| 7 Notes & review | `#notes` | Director's notes, pre-filled with "the ending plops, make it a big splash" and a patch already drafted; Apply; the critic chips; Patch, versions, compare |
| 8 Export | `#simple` | Share cut, Shot list, Seed file, ComfyUI workflow, Music only, VJ with stems, Copy MCP connect line, MIDI drawer, the `XF-` recipe |
| Setup & models | `#setup` | The model cards and downloads (the only place they exist) |
| Connect an AI | `#connect` | MCP start, test, three config snippets |

The bottom Timeline shows the demo's sections, a "Score" lane of `sample_spiral → sample_drop` pairs from the Source library, the
waveform, seven shot blocks with a Climax marker, and QA chips that read "Sync · 0 of 6 cuts sit on a beat", "Morphs · 0 morphs.
The cap is 2", "Energy · Energy 0.00 allows 0 morphs" before anything has been made.

**What Generate does from Advanced** (code, not opinion): `generate()` (app.js:4706) first demands an approved shot list and one or
two ticked Test clips; `state.live` is false until Settings → Live ComfyUI is picked (`adoptSession`, app.js:4326), so the first
Generate is a dry run; the body is `payload()` with `mode: state.view === "simple" ? "simple" : "director"` (app.js:322), so the same
Generate pressed on the Song step is a Simple-engine cut and pressed on the Shots step is the old director path. In director mode
the Turbo animatic is the coloured-block CPU animatic (`turbo.py:661-671` takes the stills draft only when `mode` is `"simple"`;
`animatic.render_animatic` paints flat colour per section), and the quality pill's Draft and Final are the old 12 fps
video-to-video restyle (`director.py:1899` onward), not the Fine-tune Draft and Final tiers, which travel as `quality_tier`.

### 1.3 The traps and dead ends, ranked by how badly they strand a user

1. **Advanced is a one-way door.** Confirmed live: after the toggle the hash stays `#simple`; a click on the logo leaves
   `advanced=1`, `mode=desk`, the rail heading "Your video" (`brandLink` returns early when advanced, app.js:5862); the browser has
   no history entry to go back to, and when it does, `hashchange` skips the Simple phases while advanced is on (app.js:5890). The
   nav's **Overview** is the Advanced Song step, not Simple. The only way out is the "Advanced on" button, which reads as a state
   light, not an exit. Tys got stranded here today.
2. **Setup cannot be reached from Simple, and the judge path says to open it.** `render()` draws `renderEasy()` whenever advanced
   is off, whatever the hash (app.js:3459); the nav is `display: none` (app.css:1383). Confirmed live: `#setup` in Simple shows
   "Make a music video." with no Setup panel. `docs/REPRODUCE.md` step 4 says "Open **Setup** in the desk header"; the Performer
   note says "See Setup"; neither is possible without discovering the toggle. Same for `#connect`, `#notes`, `#director`.
3. **"Open in Advanced" from a finished cut loses the cut.** Confirmed live on the reopened H6: it lands on the Advanced Song step
   (`#simple`, step `song`), the monitor is the blob "Browser preview", there is no player, and the storyboard, score lane and
   Source library all describe the demo's seven Pynchon rocket shots and five `sample_*` shapes. Nothing in Advanced can see or
   change a Simple cut; the two desks share a make body, not a cut record.
4. **Advanced's Generate makes something else.** Two gates (Approve shot list, 1 to 2 Test clips) that Simple never asks for; Dry run
   by default, so the first result is the blob animatic with no object or scene on screen and no way to change one (the defect Tys
   saw as "Dry-run cut"); the Draft / Final pill is a different Draft and Final from Fine-tune's; and whether the Simple engine or
   the old director path runs depends on which rail step was open when Generate was pressed.
5. **The Guardrails panel floods.** `transitions_fx.guard` (transitions_fx.py:648-651) appends "match-cut already used 2x; this
   boundary is a clean beat cut" once per overflowing boundary, and `payload()` sends one row per boundary for every make, Simple
   included (`sceneTransitionPlan`, app.js:1096). A 103-shot song with "switch" boundaries recommended as match-cut gives fifty-odd
   identical lines; `paintJob` (app.js:3898) prints them all. Two more lines that always show: "[native_vertical] 9:16 was 'auto'
   (wide crop)" on every cut at the 9:16 default (seen on every job on the desk today), and each "[qa] glitch at 1.5s" as its own
   line. In Simple the whole panel is hidden (`#jobslot`, app.css:1388), so the same cut reports nothing.
6. **The Morph panel.** The four method chips sit inside the `.toggle` pill (`ui_v6.css:55`, `#morph-panel .toggle { flex-wrap:
   wrap }`), wrap two by two, and read as one giant rounded button; a click only sets `state.morphMethod` (app.js:5045) and
   nothing visible changes until a Generate, which Simple users never press. The panel says "Blend two shots that already exist"
   under a clip of a library placeholder. "Partners for this scene" is a second library (`library.json` under `./library`, the
   procedural `sample_*` shapes, Pin and Ban) with no sentence on what it is for; the stills library a Simple user grew under
   Fine-tune → Library is a different thing with a similar name.
7. **Registers, treatments and two recipes.** The Look step summons a Register strip (Pynchon, le Carré, Tolkien, Rome) that
   shifts the whole page down (the rail moves about 100 px, so the next rail click lands on the wrong step; it happened during this
   audit); registers mean nothing to someone who chose "Neon noir". Advanced's recipe is `XF-…`, Simple's is `xf1.…`; the Export
   step shows the `XF-` one.
8. **Notes arrive pre-filled.** Landing on `#notes` writes the sample note into the box and asks the rule reader for a patch
   (`hashchange`, app.js:5891-5895), so the first thing a visitor sees is a diff they did not ask for.
9. **Simple's own weight.** Fine-tune is fifteen rows and three panels in one drawer, which is the "second app" creeping back in;
   the Knobs panel is drawn on both the choose screen and the result; "Make it better" runs the Advanced critic (`easyBetter`,
   app.js:3372) and answers "The cut is a little tighter."; a vibe card on the result screen starts a new GPU render on one click
   (app.js:4809-4818) while the same card on the choose screen only selects; Forms "Auto (12)" on the demo song shows its own guardrail
   warning ("12 forms in 12s reads as laggy; renders as 9"); "Beat overlay · off" is an orphan line; My videos lists nameless
   1.5-second dry-run animatics (b1b4df44, 7c579021, 808efe7f and eight more) beside the real cuts; Length defaults to the full
   song, so a visitor who drops a four-minute track and presses Make waits twenty minutes for a first look.
10. **Smaller.** The Tutorial button in Simple runs the three-step tour; the fourteen-step "first video" tour targets Advanced
    elements only. Review & fix and the gate line live in the header without a sentence on what they review. "Live" means the
    browser canvas in Advanced and "ComfyUI answered" in the job bar.

---

## 2. One flow

### 2.1 Principles

- **One engine, one record.** Every make is the Simple make body through `dense.run_simple`; every result is a cut record
  (`simple.json` with its shots, objects, scenes, boundary kinds, knobs). Everything deeper edits that record and re-cuts it
  (`POST /api/jobs/{id}/recut`, already CPU-only for knobs and boundary kinds). The director fills, the editor overrides.
- **Stages, not modes.** The desk is a left-to-right flow of stages. Depth opens *from* a stage as a drawer or a side panel and
  closes back onto it. There is no second screen set, no toggle, no `dataset.advanced`.
- **Prototype first.** The first button on a fresh song makes a 30 s Draft cut centred on the drop (the setting the test drive
  recommends for testing). The full song, Final, Polly and the rest are the Render stage, after you have seen the prototype.
- **The URL names the stage and Back goes up one stage.** Drawers are remembered, never in the URL.

### 2.2 The stages

| Stage | Hash | On the stage (today's Simple) | Opens from it (today's Advanced, or Fine-tune) | Gone from the desk |
| --- | --- | --- | --- | --- |
| **Song** | `#song` | Choose a song, Bundled demo, the drop card, song facts, Watch a finished one | **Song timing** drawer: beat grid, section map, Lyric align (from rail step 1); Stems (split status, the lanes) | Guided tours panel (the tours move to the Tutorial button) |
| **Look** | `#look` | Vibe grid, More vibes, the idea line, Knobs, Look chips, Foreshadow, Scenes | **Library** drawer (Grow, scenes, own shapes, Your footage); **Story** drawer (the brief, Callback, Scale journeys, Dice; the idea line is its first line); **Performer** drawer (Polly, Performance chips, your own full-body still, which is today's Hero lock) | Registers and Treatments (Pynchon, le Carré, "Pick the three moments"); the Looks preset grid with Roll the board; Band map |
| **Prototype** | `#cut`, `#cut/making`, `#cut/<id>` | **Make a prototype** (30 s, Draft, the drop in the middle), the making screen with the stills draft, then the result: the player, the Took line, Energy, Knobs, Look, Foreshadow, Scenes, Re-cut, Try another vibe (with a confirm, since it renders) | **The lane as the timeline** (today's read-only shots lane): a click on a shot opens a **Shot** drawer with the object or scene it lands on (swap from the vibe's pool), the transition into the next shot (today's per-boundary select, 14 kinds, max 2 of a type), the per-shot Look (today's scene-card select), and later re-render this shot; **Notes** drawer (one box, Apply, the diff, Confirm, Undo, versions: today's Notes & review); **Check the cut** (today's Review & fix, with its findings in plain words); **Guardrails** as one line ("3 settings were clamped") with a disclosure grouped by rule | The blob monitor and the Live / Turbo / Draft / Final pill; the Approve shot list and Test clip gates; the Morph method chips, Fast, Hit flash, Check the joins; the Source library; the Cut panel's Calm-to-Hype duplicate (Energy stays on the result); Continuous take; the Score lane |
| **Render** | `#render`, `#render/making` | Length (Full song, 60 s, 30 s, 15 s), Model (Draft, Final), Aspect, Energy, Forms, Beat FX, Subject orbit, End card, Performer shots, the estimate, **Render** | **Machine** drawer: GPU preset, Renders on (ComfyUI address), Paid cloud renders, video model (LTX-2.3 / 2.5) | Settings' Dry run / Live radio (a make is live when ComfyUI answers, else the stills cut, which is Simple's rule already) |
| **Share** | `#share` | Download, 15 s hook, Copy recipe code, Share cut (720p), My videos | Shot list, Seed file, ComfyUI workflow, VJ with this song's stems, Copy MCP connect line, MIDI drawer (today's Export) | The `XF-` recipe (one recipe, `xf1.`, carrying the cut record) |

Tools that are not stages live behind the header's "…" menu and keep their hashes: **Setup & models** (`#setup`), **Connect an AI**
(`#connect`), Settings (endpoint, paid cloud, library folder), Judges, About, Copy diagnostics, Tutorial, Expert guardrails.
Each opens as a full page with the logo and Back returning to the stage you left.

Where the removed things go: the old director render path (`mode: "director"`, the 12 fps restyle), the registers, the morph
board and the source library stay in the API for MCP and the CLI; they leave the desk. The hero still becomes the Performer's
"your own still". Title and End card text move to Render → End card.

### 2.3 URL and Back

- Stages push a history entry; anything inside a stage (a drawer, a knob, the making screen) replaces it. The logo is `#song`,
  always, and it clears the result the way "Back to the song" does today. A running job keeps its making screen whatever the hash
  (today's rule in `easyPhaseFromHash`).
- Back from `#cut/<id>` goes to `#look`; Back from `#render/making` goes to `#cut/<id>`; Back from a tool goes to the stage it
  was opened from.
- Aliases, so old links keep working: `#simple` → `#song`; `#simple/result` → `#cut/<last id>`; `#simple/showcase` → the showcase
  under `#song`; `#director` and `#scene` → `#cut`; `#notes` → `#cut` with the Notes drawer open and **no** pre-filled note; `#setup`
  and `#connect` unchanged. The VJ page's Desk link (`/#simple`, pinned by `tests/test_simple_nav.py:58`) still lands home.
- `localStorage` keeps which drawers are open (as `xeno-finetune` does today) and drops `xeno-advanced`.

### 2.4 What the first-time visitor meets, after

Song: drop a file or press Bundled demo; the drop card fills in. Look: pick a vibe, maybe type an idea, maybe turn a knob. Press
**Make a prototype**: the stills draft within seconds, the morphs in two to five minutes, then the cut with its lane. Click a shot
you dislike, swap its object or its transition, Re-cut (no GPU). Press **Render** for the whole song or Final. Share. At no point
is there a second desk, and at no point does the logo or Back stop working.

---

## 3. The plan

### 3.1 Before the deadline (Saturday 31 Oct, 3 am AEDT): small fixes, in this order

All JavaScript and CSS go live on a reload; the two Python halves (C2, F2) wait for the one restart a day. Each item names the
tests that pin the strings it touches, since every such change edits the test in the same commit.

| # | Fix | Files | Size |
| --- | --- | --- | --- |
| A | **A way out of Advanced.** The logo always returns to Simple: in the `brandLink` handler drop the `advanced === "1"` early return and call `syncAdvanced(false)` before `setEasyPhase("choose")` (app.js:5859-5871). Put "← Back to Simple" as the first item in the rail (`railHtml`, app.js:578) and in the header toggle's pressed label ("Director tools · back to Simple" instead of "Advanced on", `syncAdvanced`, app.js:6862). Make `hashchange` switch Advanced off when the hash is a Simple phase (`#simple/result`, `#simple/showcase`, app.js:5888). | app.js, index.html (button text), `tests/test_simple.py:26` keeps `id="advanced-toggle"`, `tests/test_rail.py` labels | about 40 lines, 1 h |
| B | **Setup and Connect reachable from Simple.** In `render()` (app.js:3430-3459) draw `renderSetup()` / `renderConnect()` inside the Simple shell when the view is `setup` or `connect` and advanced is off; add "Setup & models" and "Connect an AI" to the "…" menu in `index.html` and a "Setup & models" text link under the ComfyUI note in the Simple side column (app.js:2570). Reword REPRODUCE step 4 at docs/REPRODUCE.md:29 ("Open **Setup** from the … menu"). | app.js, index.html, docs/REPRODUCE.md, `tests/test_docs.py` if it pins the sentence | about 30 lines, 1 h |
| C1 | **Guardrails, grouped on the client.** In `paintJob` (app.js:3898) count identical messages and print each once with "× N"; collapse `[qa]` lines into one "QA: 5 glitch flags at 1.5 s, 4.5 s, …". | app.js | about 15 lines, 30 min |
| C2 | **Guardrails, one line per rule on the server.** `transitions_fx.guard` (transitions_fx.py:648-651) collects the overflow per kind and emits one message: "match-cut already used 2x; 51 more boundaries are clean beat cuts". Drop the `native_vertical` message when the body's aspect is the 9:16 default and `vertical_mode` was never set by the user (guardrails.py, the rule after `morph_density`). | transitions_fx.py, guardrails.py, `tests/test_transitions_fx.py`, `tests/test_guardrails*.py` | about 25 lines, 1 h, needs the restart |
| D | **"Open in Advanced" tells the truth.** On the result and showcase screens relabel it "Director tools (storyboard, notes, export)" and make it open the Export step (`state.step = "export"` before `syncAdvanced(true)`, app.js:5112), where Share cut, Shot list and Seed file act on the last job; or remove it from the result screen, since every result action already exists there. | app.js, `tests/test_simple.py:21` pins "Open in Advanced" | about 8 lines, 20 min |
| E | **The Morph panel reads.** CSS: `#morph-panel .toggle { background: none; border: 0; padding: 0; gap: 6px }` and its buttons styled as `.chips .chip` (separate pills, `app.css` near line 1987). One sentence under the heading: "Which engine blends the two shots at the drop in a storyboard render. It applies on the next Generate." Rename "Partners for this scene" to "Source library (./library, clips and shapes the storyboard may pair with this shot)" with the second sentence "The vibe's objects are a different library: Fine-tune → Library." (app.js:1304-1307). | app.css, app.js | about 20 lines, 30 min |
| F1 | **No surprise dry run.** When ComfyUI answers, Advanced defaults to Live: set `state.live = true` in `refreshComfy` the first time `comfyOk` turns true unless the user chose Dry run in Settings; and label the monitor "Dry-run animatic: coloured blocks on the beat, no pictures. Settings → Live ComfyUI renders." when `state.live` is false (app.js:801-812, `watchJob` label at app.js:4384). | app.js | about 15 lines, 45 min |
| F2 | **The director animatic shows the vibe's stills.** `turbo.py:661`: take the stills draft when `vibe` is set as well as when `mode` is `"simple"`, so an Advanced Generate on a song with a vibe previews real objects on the beat. | turbo.py, `tests/test_story_cut.py` or the turbo test that pins the painted path | about 5 lines, 30 min, needs the restart |
| G | **Simple's small ones.** My videos: hide rows with no song label under 5 s (`galleryPanel`, app.js:2852, or `/api/videos`). Forms: no guardrail line while Auto is on (`morphControl`, app.js:2819). Drop the "Beat overlay · off" line or label it. Confirm before "Try another vibe" renders (a second click on the same card, or a "Make it" button that appears on the chosen card). | app.js, `tests/test_ui_v7.py` if it pins the gallery | about 25 lines, 1 h |

A, B, C1 and E together are about three hours and remove the three ways a judge or Tys gets stranded. D, F1, G are another two
hours. C2 and F2 are the only Python and can ride the next restart. Total about six hours of landed work; "Advanced" relabelled
"Director tools" (already in the DIRECTION plan for Thursday) folds into A.

**Landed, 26 Oct, after Tys said go** ("Yes, land the before-deadline fixes from docs/WORKFLOW_AUDIT.md, A, B, C1 and E
first, then D, F1, G, with C2 and F2 ready for the next desk restart"), each verified on the preview desk at 47322 after a reload
and pinned by `tests/test_one_desk.py` (the desk) and `tests/test_one_desk_server.py` (the server):

| Fix | Commit | What changed on screen |
| --- | --- | --- |
| A | 1cef168 | Director tools lives at `#simple/desk`, `#director`, `#scene`, `#notes`; entering pushes the URL, so Back comes out; the logo goes home; the header button reads "← Back to Simple" while on and the rail opens with the same item; a reopened cut stays on its result when you come back; a reload lands in Simple unless the URL says desk |
| B | 1499571 | `#setup` and `#connect` draw inside the Simple shell with "← Back to the desk"; entries in the … menu and a line under Make my video; REPRODUCE step 4 reworded |
| C1 | eb65d1d | the job bar's Guardrails list folds identical lines ("… (× 51)") and timed QA flags into one line a kind: the H6 report went from 59 lines to 3 |
| E | b928a87 | four separate method pills under a Method label, the panel opens with what the board is and when it applies, the source library is "Clips and shapes the storyboard may pair with this shot" with where they come from and that they are not the vibe's stills |
| D | 63c0f34 | "Director tools: storyboard, notes, export" opens the Export step, whose Shot list and Seed file point at the reopened cut |
| F1 | 6ff4357 | Director tools boots Live once ComfyUI answers (unless Settings chose by hand); the caption, the stage list and the finished label name a dry run as coloured blocks, no pictures |
| G | a172b5d | My videos hides the nine nameless rows; Forms shows no guardrail line while Auto; Beat overlay is an Off / On row with a note; a vibe card on the result selects and shows "Make it with Neon noir" instead of rendering on the click |
| C2, F2 | 35ccaa1 | one guardrail line a kind from `transitions_fx.guard`, no `native_vertical` line at the 9:16 default, the stills draft for a director animatic with a vibe; committed ready, **not on 47322 until a restart** |

### 3.1b The fold, landed early (26 Oct evening)

Tys after the A to G fixes: "I still see a simple and director mode - it looks the same? I thought we were going to streamline
the whole app?" So the restructure below moved up from November and landed the same evening, in one commit. What it is, against
the plan in 3.2:

| Plan step | What landed |
| --- | --- |
| 1. Stage router | One render path (`renderEasy`, or `renderTool` for `#setup` / `#connect`); the strip is **Song › Vibe › Prototype › Refine › Share**; `syncAdvanced`, the toggle, `renderAdvanced`, the rail, the nav and every `data-advanced` rule are gone; old hashes land on the desk. The hashes stay `#simple/...` (not renamed), so the VJ page's Desk link and old bookmarks work. |
| 2. The lane as the timeline | Already built by the timeline session the same afternoon (shot and boundary drawers, re-render, Generate here); the fold made it the Refine stage and gave it the Share row beneath. |
| 3. Fold the panels | Polly's own still into Fine-tune → Performer; shot list, seed file, VJ into Share; Setup, Connect, Settings, Expert into the **…** menu. Removed from the desk, because they changed nothing in a cut: notes and versions, Review & fix, the morph board and source library, registers and treatments, the storyboard, transition and look selects, Energy slider, lyric align, quality pill and live canvas, gates. |
| 4. One engine | The make body is always `mode: "simple"`; the storyboard transition rows and the end-card text are gone from it; the routes behind the removed panels stay for MCP. The `XF-` recipe left the desk with the Export step. |
| Prototype stage | New: a song over 45 s is made first as a 30 s Draft around the drop; the cut's screen offers the whole song and Final. |

Verified on the preview desk (47322): the old URLs, the logo and Back from a tool page, the menu, Settings, a reopened cut's
Refine and Share, a simulated 3.5-minute song's prototype button and make body, and one real Make (bundled demo, Molten gold, End
card on: 4:33, the End card burned into the last frames, the Guardrails line "1 setting adjusted · 1 check flagged").

### 3.2 After the deadline: the restructure (the first two weeks of November)

In this order, each step shippable on its own:

1. **Stage router (about one day).** `render()` always draws the Simple shell. Replace `viewFromHash` / `setEasyPhase` /
   `easyPhaseFromHash` with one `stage` setter over `#song`, `#look`, `#cut`, `#render`, `#share`, `#setup`, `#connect` and the
   aliases in 2.3; crumbs become the stage strip (Song › Look › Cut › Render › Share). Delete `syncAdvanced`, `dataset.advanced`,
   the toggle, `renderAdvanced`, the rail (`RAIL`, `railHtml`, `railHash`, `deskStep`, `goRail`), the nav links, and the
   `body[data-advanced]` CSS. Tests: `test_rail.py` (rewrite), `test_simple.py`, `test_simple_nav.py`, `test_chrome.py:24`,
   `test_ui_v7.py`, `test_docs.py`; README's "Advanced desk" section becomes "Deeper controls".
2. **The lane as the timeline (about two days).** `GET /api/videos/{id}/shots` already carries each shot's object, scene flag,
   transition and boundary kind. Make each block clickable into a Shot drawer; extend `POST /api/jobs/{id}/recut` to accept
   per-shot overrides (`object`, `scene`, `transition`, `dance_fx`) so a swap is a CPU re-cut from the cached morphs when the pair
   exists and a one-morph GPU render when it does not (the DIRECTION's "re-render one shot by index"). The Advanced transition
   select and scene-card Look select move in here as the drawer's two rows.
3. **Fold the panels (about two days).** Story (brief, callback, scale journeys) under Look; Notes and versions under the cut; Review
   & fix becomes "Check the cut" under the cut; Export becomes Share; Song timing under Song; Hero lock becomes the Performer's own
   still; Settings loses the Dry run radio. Delete from the desk: `morphPanel`, the source library UI (`libraryQuery`,
   `paintLibrary*`), `treatmentPanel`, `paintRegisters` and the register slot, `bandMap`, `cutPanel`, `stageMedia`'s live canvas
   (the VJ page keeps `live.js`), `qualityToggle`, `stagesHtml`, `shotReview`, `sceneEditor` (its fields that matter, Subject and
   Shot, live in the Shot drawer). About a third of `app.js` goes.
4. **One engine, one recipe (about one day).** The desk sends `mode: "simple"` always; `payload()` sheds the director-only keys
   (`register`, `palette`, `blocks`, `customs`, `treatment`, `guide_id`, `interpolate`, the `scenes` list except per-shot overrides
   from the lane); the `XF-` recipe leaves the desk, `xf1.` carries the overrides. The director path, registers and the morph board
   stay in `/api/v1/*` and the MCP tools.
5. **Then the DIRECTION list:** insert, trim and reorder on the lane with "Cut it to the beat"; the clip library and a Real footage
   switch; VJ closing the loop.

---

## 4. Evidence log

| Check | Where | What was seen |
| --- | --- | --- |
| Advanced toggle, then logo | live, 47322 | hash `#simple`, `advanced=1`, `mode=desk`, heading "Your video"; Back: no history entry |
| `#setup` with Advanced off | live | "Make a music video.", nav `display: none`, no `.setup` element |
| Reopen H6 → Open in Advanced | live | hash `#simple`, step `song`, headings "Your video / Browser preview / Pick or drop a song / The beat grid", no player |
| Rail step 4 Look | live | Register strip inserted above the desk, the rail shifted, the next click hit the wrong step |
| Rail step 6 Morph | live | four method chips wrapped 2×2 inside one pill; "Partners for this scene": five `sample_*` shapes, "sample_ring → sample_spiral. Morph chain." |
| Rail step 7 Notes | live | box pre-filled "the ending plops, make it a big splash", patch drafted on arrival |
| Advanced Generate's mode | app.js:322, turbo.py:661 | `mode` follows the hash; the stills draft only in `simple` mode |
| Dry run default | app.js:4326, index.html Settings | `live: false` on a fresh session; the radio defaults to Dry run |
| Quality pill vs Fine-tune Model | app.js:418, director.py:1876-1900 | `quality` draft/final = the v2v restyle; `quality_tier` = the Simple tiers |
| Guardrail flood | transitions_fx.py:648-651, app.js:1096, app.js:3898 | one line per overflowing boundary, rows sent for every boundary, printed unfiltered |
| Always-on guardrail line | `/api/jobs/af300ac6`, `e789a0cd`, `b1bcba7e` | "[native_vertical] 9:16 was 'auto' (wide crop)" on all three 9:16 cuts; glitch flags one line each |
| Setup in the judge path | docs/REPRODUCE.md:29 | "Open **Setup** in the desk header" |
| Nameless gallery rows | `/api/videos` | eleven rows with no vibe or song, 0.4 to 4.2 s long |
| Fine-tune size | live, page text | fifteen rows, three panels, one drawer |
| Try another vibe renders at once | app.js:4809-4818 | `easyMake()` on the card click in the result phase |
