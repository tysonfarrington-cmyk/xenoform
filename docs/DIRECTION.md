# Where Xenoform is going, and the week to the contest

Written 24 Oct 2026 from Tys's notes after his first real sessions with the desk, six code readers, three plans and two judges. Contest cutoff: Fri 30 Oct 9 am Pacific (Sat 31 Oct 3 am AEDT); Tys works to Fri 9 pm AEDT and does the push, the public flip, the upload, the post and the Typeform himself.

## The purpose, in one line

Drop in a song, pick a vibe, press Make: Xenoform directs the music video on your own GPU with open weights. It reads the beats, one object morphs into the next on every hit in the house look, Polly (MiniMax H3) sings or drums the drop, and then it shows you the cut so you can change what you want. VJ mode plays the same pictures live.

The app has felt directionless because the taste lived in the hand-built demo spec and the desk only exposed knobs. The fix is to move the taste into the code and config the director reads, then let the editor be the place you override it.

## What Tys asked for, clarified

1. **Know where I am and let me go back.** After "Watch a finished one" the only way out was a muted text button ninth in the side column; the browser's Back leaves the site because the phase never touches the URL.
2. **Controls that fit.** One CSS rule makes every segmented row shrink instead of wrap (`app.css:2090`), the Look chips' wrap fix is scoped to the Fine-tune drawer only, and Fine-tune lives in a 340 px side column that leaves about 214 px per row.
3. **Tell the truth about time.** The Simple bar is elapsed divided by a guessed ETA capped at 95 %; the guess is a constant for a 20 s clip (at most 130 s), so every multi-minute run pins at 95 % within two minutes. "6:40" was elapsed, not remaining. The server measures the whole run (`job.seconds`, "Cut ready in N s") and Simple overwrites it with "Your cut is ready."
4. **One desk, not two apps.** Simple is already the desk a visitor sees; Advanced is a second render path behind a toggle. Depth should come from drawers and drop-downs on the one screen.
5. **An autonomous director with our taste, and far more material.** Every vibe has 12 stills; ten of the twelve featured vibes borrow another vibe's 12. A 4-minute cut renders 24 morphs from 12 stills and replays them across about 150 shots. The demo's polish came from a hand cut (LTX-2.3 forms QA'd frame by frame, played at 0.6 to 0.95x, hand-picked premium transitions, a grade, labels, VO, a designed end card); Simple renders Draft LTX 0.9.5 at 320x576, speeds morphs up, fires only liquid-melt at switches and nothing on the drop.
6. **Editing-software feel.** A timeline you can insert scenes into, with one button that cuts whatever is on it to the beat. The director fills the timeline first; the editor is review and override, never a blank canvas.
7. **VJ should be the fun half**: easy to start, powerful with the MiniLab, and connected to the desk.
8. **A clear direction so the app is easier to build on**, and a real chance at the contest.

## Straight answers

- **Are the vibes static images or references?** Static images, used literally. Each LTX morph pins still A as its first frame and still B as its last (`workflows/xenoform_morph.json`, `morph_pass.py:476-479`); the vibe's one "look" sentence is the only prompt. Nothing is used as a style reference. The pictures in a vibe are the frames the video passes through.
- **Same handful of images?** Yes: 12 per vibe, and a long song repeats each pair about six times (`dense.py:448-460`, `morph_pass.py:148`). More stills cost about 4 GPU seconds each with Z-Image Turbo; 36 more per featured vibe is about 30 GPU minutes plus a cull by eye.
- **Videos instead of stills?** The morph engine needs two frames to travel between, so stills stay the morph inputs. Video enters as clips cut 1:1, which is how Polly's shots and Your footage already work (`own_media.py`). The 4 NASA library clips never reach a Simple cut yet.
- **How long did it take?** Already measured: `work/ui/jobs/<id>/turbo.json` and `simple/simple.json` carry `seconds`. The result screen will say "Took m:ss" with a breakdown.
- **Why over twenty minutes?** On a full song it is the CPU, not the GPU: the look pass runs one frame at a time at about 0.2 s a frame (`dense.py:54`, measured 1440 frames in 285 s), so a 4-minute song is about 19 minutes of compose against 2 to 5 minutes of Draft morphs. With Polly on, add 8 to 10 minutes a shot. The look pass resets its state per shot (`beatfx.py:448-458`), so shots can be composed in parallel: that is the single biggest lever on the complaint.
- **Can Simple reach the demo's polish autonomously?** The mechanical half this week (cut density like the demo, distinct pairs, premium transitions on every featured vibe, a look per vibe, a real cut as the showcase). What stays manual: repairing a bad morph, compositing, VO, the designed card. The demo's model is the Final tier at about 290 s a morph (56 minutes for 20 s, measured 24 Oct), so Draft carries the taste for iteration and Final is the overnight keeper.

## The week (about 4 to 5 landed hours a day; JS and CSS go live on a reload, Python is batched into one desk restart a day)

**Sat 24 / Sun 25: find your way, fit, honest time.**
- Back button first in the result and making headers; the showcase becomes its own phase ("Showcase, made earlier", Back as the one primary action, no Share or Re-cut for a video you did not make); a Song > Vibe > Make > Video strip on every Simple screen; the phase in the URL so the browser's Back works; the logo as home; the song guard on the result-screen vibe cards.
- Unsquish: segmented rows wrap (`flex: 0 1 auto; min-width: max-content`), Look chips wrap everywhere, Fine-tune moves out of the side column into grouped drawers in the main column (Picture, Cast, Look, Sources, Machine), header actions wrap, a 1100 px breakpoint, short Model and GPU labels.
- Honest clock, client: the bar is seeded from the plan estimate the page already shows and driven by the server's progress, labelled "elapsed, stage, about N left"; "almost there" only in the last stage. "Took m:ss" from `job.seconds` on the result screen.
- Server batch for one restart: `t0`, stage timestamps, `took_s` and a breakdown on the job; the silent tail reports (end card, save, each QA pass); `/api/videos` carries seconds (with a fallback for old folders); a stage-ordered overall so the bar never runs backwards; the draft preview stops restarting on every compose shot.
- Housekeeping in the same commits: the three stale "about a minute" claims rewritten; the showcase replaced by a real Simple cut (the Final 20 s cosmic cut); Simple state persisted in localStorage; the VJ Desk link and `vjUrl()` with the song and stems; About unhidden; the pinned tests edited with the UI (`test_simple.py:26-27`, `test_rail.py:28-29`, `test_ui_v7.py:111-113`, `test_docs.py:29-30`).

**Mon 26: the twenty minutes.** The look pass over shots in a process pool, stitched in order with the transitions afterwards; a frame-count and duration test. If it proves too risky for the contest branch, fall back to the stage-weighted bar alone and accept a 20 to 30 minute full song with an honest clock.

**Tue 27: taste that is real on long songs.** Distinct morph pairs (`morph_pass.py:147-149`, `dense.py:448-460`); premium transitions for the twelve featured vibes (`configs/vibes.json` transitions, scene-morph remapped to match-cut inside `boundary_transitions`, the story-plan gate dropped); the cut-density lever (`STORY_BEATS` drop 2 to 4, build 4 to 8, `clip_s` toward 5 s) since for any cut over 20 s the chain overwrites every shot's render length and speed (`dense.py:838-840`). One 60 s A/B judged on three fixed checks: pour tempo, the drop transition, colour; plus a duration check against the song. Queue the 432-still Z-Image batch overnight if Tys says yes. *Done 24 Oct: both cuts ran exactly 60 s; Tys judged viscous the winner (18 shots, two match-cuts, against tight's 33 and one), so viscous is the Simple default and tight is the `pace` option.*

**Wed 28: material and honesty.** Cull the stills into `objects.json` and drop the ten pool keys; per-vibe `fx_defaults.dance_fx` (config only); the "Live" tier renamed "Browser preview" with an honest "ComfyUI is not answering" note instead of the silent fallback; a read-only shots lane under the result player (the seed of the timeline); `pyproject.toml` version bump; `test_docs` accepts a real demo link. *Done 25 Oct, three days early: the stills library replaced the cull (the keepers live in the local set, the pool keys stay as the registry's fallback), the rest landed as written.*

**Added 25 Oct (Tys: the same shapes keep coming back; hundreds or thousands, generated by the app):** the stills library (`docs/stills.md`): one pool of shipped and locally grown stills, a 395-subject catalogue weighted per vibe, prompts on each pool's own style prefix, five checks against the pool, own shapes first in the chain, least-used objects first. Video objects (a still plus an idle clip of it) wait until after the contest.

**Thu 29: freeze by evening.** README top block with the purpose line and a three-line pitch; truthful still and timing claims; the MiniMax H3 territory note (not licensed in the USA, EU, UK, KR); a picture-first one-liner and post; "Advanced" relabelled "Director tools" with its id intact; a VJ and MIDI paragraph on /judges; CHANGELOG 0.3.3; full pytest in two halves; local commit. Demo decision: capture Simple making a cut plus 10 s of VJ into a v10 if Tuesday's A/B passed, else submit v9.3 as it is.

**Fri 30: Tys's day.** Judge-path walk on his desk, then the public flip, the upload, `DEMO_VIDEO_URL`, the post, the Typeform.

**Cut from this week** (first two weeks of November, in this order): the one-desk fold (render() always draws Simple, Advanced steps as drawers, about 6 h); the timeline as the cut plan (GET/POST `/api/jobs/{id}/timeline`, edits as a 71 s no-GPU recut); re-render one shot by index; the editable lane with insert, trim, reorder and "Cut it to the beat"; the clip library and a Real footage switch; Advanced per-shot looks and transitions reaching the Simple cut; VJ closing the loop (a performance's switch log rendered as a cut, the house look in the shader, MIDI takes into the render, your own renders as the loop pool); stills painted from the idea line at Make time; a self-calibrating ETA; Final tier at a sane cost; grade and grain; shot QA re-rolls.

## Working rules for the week

- Targeted direct edits; agents only for genuinely parallel, well-scoped reads; no browser screenshots unless a layout fix needs one.
- Every test cut gets a duration check against the song (the compose height bug silently truncated three cuts this week).
- Every change that touches a string a test pins edits that test in the same commit.
- Python changes batch into one restart a day; Tys restarts his desks by asking in words, or the preview launcher on 47322 verifies first.
- A version stamp goes into `simple.json` and the recipe when cut defaults change, so old recipes are reproducible.

## Decisions Tys owns

1. Stills: run about 30 GPU minutes of Z-Image generation overnight (432 stills), with a contact sheet to cull? Without it, variety this week is distinct pairs only.
2. Render-time budget: is about 1.5x today's Draft time acceptable for a visibly better cut, or must a 30 s Draft stay under five minutes?
3. Demo: re-cut v9.3 into a v10 with a screen capture of Simple and 10 s of VJ (Thursday, about 5 h), or submit v9.3 unchanged?
4. One mode by Friday: "Advanced" relabelled "Director tools" with the real fold the week after (recommended), or the 6 h fold now at the cost of the taste work?
5. Own footage: any clips of yours to use this week? If yes, the Real footage switch moves into Tuesday.
