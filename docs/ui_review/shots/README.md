# UI review screenshots (4 Nov, review desk 127.0.0.1:47340)

Rerun (desk must be up; script lives in the session scratchpad):

    set NODE_PATH=C:\Projects\xf-uiaudit\node_modules
    node C:\Users\tyson\AppData\Local\Temp\claude\9919beaa12ed540b\db66f353-8088-4995-9a09-2da304a5ab80\scratchpad\shots\capture1.js [baseUrl]

Writes NN_state.jpg plus manifest.json (url, viewport, note, deduplicated page and console errors per shot). About 160 s. Never presses Make, Queue, Grow, Render, Dream, Re-render or Generate.

| State | Notes |
|---|---|
| 01-03 | Tutorial offer, five tour steps, desk after tour: all reached. |
| 04, 04b | Glitch Out chip; stems line still "splitting with Demucs... 61 s" at 30 s. |
| 05a, 05 | Once a song is chosen the song file input is removed from the DOM; the picker only returns after clicking "Change" (05a). liquid_dnb.mp3 then analysed fine (3:42, 120 BPM). |
| 06-14 | Vibe, More vibes, Morph chips (Your clips shows "1 clip here" after upload), Stems, idea line, loved chain, stem/MIDI panels, Fine-tune, Work in progress: all reached. 12, 12b are viewport shots. |
| 15-17b | More menu, Settings, bad endpoint :9 (header says "ComfyUI not connected", Settings note names the address; restored to :8188), About. |
| 18-19 | #setup and #connect are both pages. |
| 20 | Ctrl+K palette, typed "look". |
| 21-22 | Showcase and My videos (empty). |
| 23-27 | /variations /judges /moves /licences /credits all HTTP 200. |
| 28-28f | /vj at 1280x720; glitch_out.mp3 gave bpm 90.7; rec toggled. |
| 29-30 | Mobile 430x932 and 1024x768, tutorial dismissed with Not now. |
| 31 | 16:9 survived reload (Fine-tune summary still "16:9"); set back to 9:16 afterwards. |

Surprising: the desk and /vj open ws://.../ws/midi which returns 404 on this desk (console error on most shots); a 404 resource load on 01, 21 and 28e; fullPage shots taken after scrolling show the sticky header overlapping the page top (for example 08b).

## Phase 2: the finished cut (job 31680167), capture2.js

Rerun: `node ...\scratchpad\shots\capture2.js` (appends 40-50 to manifest.json; it needs the Glitch Out (30 s cut) card in My videos).

| State | Notes |
|---|---|
| 40, 40b | Result screen via Reopen (#simple/result). |
| 41 | NOT captured: a reopened cut has a stub job in state, so the Guardrails bar never renders although the job JSON holds the messages. |
| 42-42d | Shot drawer tabs Shot, Look, Regenerate on shot 1; Join needs shot 2 (shot 1 has no Join tab). The third tab is labelled Regenerate (data-value gpu). |
| 43, 44, 45 | Join into shot 10, Share row, side column hidden then shown again. |
| 46, 47 | Mobile 430x932 and 1024x768 reopened. |
| 48, 49 | Seed JSON, My videos with the done card. |
| 50 | VJ link on the result screen is /vj?track=demo&stemsId=...: it names the demo track, not Glitch Out, and carries no job id, so VJ plays library loops, not the cut's morphs. |

Note: the job was re-assembling (status running, 84%) during the first run; the second run followed completion.

## Rerunning the capture (4 Nov, added after the review)

The scripts are in `docs/ui_review/tools/`: `probe.js` (one page, checks Playwright and Chrome), `capture1.js`
(states 01 to 31, a fresh desk, no GPU) and `capture2.js` (states 40 to 50, the finished cut; it needs a finished
30 s Draft in My videos, so run a Make first or point it at a desk that has one). They need Playwright 1.64 with the
installed Chrome (`channel: 'chrome'`, because the bundled Chromium cannot decode H.264); on this PC the node_modules
live in `C:\Projects\xf-uiaudit` and are not in the repo:

    set NODE_PATH=C:\Projects\xf-uiaudit\node_modules
    node docs\ui_review\tools\capture1.js http://127.0.0.1:47340
    node docs\ui_review\tools\capture2.js http://127.0.0.1:47340

Elsewhere: `npm i playwright@1.64` in any folder and set NODE_PATH to its node_modules. The review desk itself is the
launch entry `xenoform-review-47340` in `.claude/launch.json` (the worktree's code via PYTHONPATH, its own clean
`work/ui`, the shared `.venv` of `C:\Projects\xenoform-rc2`).

## Shots 60 to 65b: the hand walk

These are captures of the browser pane during the hand walk (800×600 at 0.8 scale, so 640×480), not Playwright: the
Making screen at 0:03, 0:13, 1:13, 2:59 and 5:28 of the one GPU Make (60 to 60e), the cut's screen as the Make landed
(61), the Guardrails bar opened (62), the Regenerate and Join tabs on the live job (63, 63b), the re-cut's making screen
at 3 s and 33 s (64, 64b), and `/vj` as it opened and after L (65, 65b). Shot 41 stays in the manifest as a note with
no file: the Guardrails bar does not render on a reopened cut.
