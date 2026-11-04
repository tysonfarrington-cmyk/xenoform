# Setup, the machine and the side-page shell (branch `setup-shell`, 4 Nov 2026)

The "Setup and the machine" row of [UI_REVIEW.md](../UI_REVIEW.md) section 7: M1, M2, M3, M5, M6, S1, S2, A1 to A4, W3, W5, N8,
F8, F11, F14. Cut from `ui-review-4nov` (574c1fc); nothing pushed, nothing merged. `renderEasy`, the timeline drawer, `vj.html`
and `midi.js` are untouched.

## What landed

| Id | What it does now |
| --- | --- |
| M1 | `/api/setup` carries `gate` (`blocked`, `line`, `button`). While a required model is missing the Make buttons read "Get the 11.5 GB model", a line under Make says "To make videos you need LTX 0.9.5, 11.5 GB. Open Setup", and Make opens Setup (a song and a vibe need not be picked). A guess about the models folder never blocks (ComfyUI not answering and no `XENO_MODELS`). |
| M2 | The Final card lists the four files the Final loads by name (fp8 checkpoint, Gemma 3 12B encoder, x2 spatial upscaler, Real-ESRGAN x4plus), each installed or missing, one total (40.0 GB); Download fetches only what is missing, resumes from a `.part`, checks size and sha256. The full 46 GB weights are not part of it (the Final loads the fp8 file on every card). New LTX-2.5 card: its four files, where each goes, "not downloaded by Setup" (gated repository); it counts as installed only when the four files are on disk, which is how `final_tier.model()` picks LTX-2.5. |
| M3 | A Download that does not fit is disabled with the reason under the card ("Needs 28.6 GB plus a little spare room; the models drive has 4.6 GB free", live on this machine); a card under 12 GB is told the Final falls back to the Draft. The tier heading is "12 GB GPU preset" with "Detected 12.0 GB of video memory"; when ComfyUI stops answering the "read from ComfyUI" line turns amber ("Out of date: ComfyUI is not connected now") and Setup reloads when ComfyUI comes or goes. `/api/setup?comfy=` asks the address the header pings. The check asks ComfyUI for all nine folders at once (a closed port cost 1.5 s each: 25 s a check on Windows, now one timeout). |
| M5 | The tier sentence is written from `final_tier.model()` (LTX-2.5 when installed, else LTX-2.3 fp8), so Setup and About agree; a GPU that is not CUDA reads "GPU not recognised" (only NVIDIA is detected, as before). |
| M6, S1, S2 | One header (brand, page name, Open weights, one "Back to the desk") built once in `ui.py` for Judges, Variations, Moves, Licences and Credits, all on `theme.css`, `app.css`, `desk.css` and the new `side.css`; the judges' prompt is `--x-text-2` and the slider `--x-accent`; Moves has a tile per move (a frame of the clip when downloaded, a drawn placeholder when not), the credit behind a Source button, a styled file picker and a line saying what enables "Render this move". |
| A1 | The primary fill is `--x-primary` #5b4be0: white text 5.95:1 flat, 5.4:1 under the highlight, hover and pressed above 4.5:1 (was 3.9:1 and 2.9:1). The other white-on-accent spots (menu and palette rows, the step number, the badges) use it too. |
| A2 | The tour's arrow keys leave a focused slider, radio, tab or menu alone. |
| A3 | The play badge is a button beside the card (`.vibe-cell`), a Tab stop only for the card the group tabs to: two stops in the grid, not thirteen. The example layer is a native modal `<dialog>`: the page behind it is inert, Tab stays inside, Escape closes it without stopping a render, focus returns to the badge. |
| A4 | Passage buttons keep a focus ring; arrowing the mini vibe cards on the cut's screen focuses the new card each time. |
| W3, W5 | Setup, Settings, About and the Work in progress drawer in short present-tense lines, the long paragraphs behind Details; "Performer (Polly)"; no "no longer", "as it always has", "Pynchon register", "live restyle"; each Settings line says it lives in "this browser" (or "set by the desk" for the paid-cloud env switch). |
| N8, F8 | A stopped or failed whole song has "Back to the song" beside Resume, shows each failed passage's own detail and the assembly error, and offers "Lay it together again" when only the assembly failed; the logo leaves a making screen when nothing is running. |
| F11 | A banner under the toolbar: "ComfyUI is not answering at <address>. Make plays this vibe's pictures in the browser…", Open Settings, Dismiss; the facts agree (they were drawn before the first answer); the address is kept in this browser (`xeno-endpoint`); Settings says renders go through the proxy on 8189 and how to change that. |
| F14 | `/api/videos` rows carry `status` and `progress`; a cut still rendering shows "Rendering · 42 %" and Open (follows the job on the making screen), not Reopen, Re-render or Copy recipe. |

## How it was verified

- Tests: `tests/test_setup_final.py` (server), `tests/test_desk_shell_pass.py` (front end, and the contrast computed from the
  CSS), `tests/test_side_pages.py`; `test_film_pack.py`, `test_ui_v7.py`, `test_desk_design.py` adjusted for markup that moved.
- On my own desks (47360 with the real models, 47362 with an empty models folder and a dead ComfyUI address): Setup with the real
  `/api/setup`; the gate end to end (Make became "Get the 11.5 GB model", pressing it opened Setup, nothing downloaded);
  the primary button's computed colours; Tab order and the example layer with real key presses; the tour against a focused knob;
  arrow keys on the cut's screen (a finished 30 s Draft); the five side pages at 1366 and 375 px, no sideways scroll.
- Screenshots: `docs/ui_review/after/shell/` (`manifest.json` says which are real and which set one answer or the page's state:
  the gate, the banner, the failed song and the rendering card; `docs/ui_review/tools/capture_shell.js` reruns them).

## Not done, or not proved

- **W3** only where the brief put it (Setup, Settings, About, the drawer). The 60 to 85 word notes under Knobs, Shape, Dense and
  the Final stay: they sit in the rows T5 rewrites (C4, C9); only the changelog words in the Shape notes changed.
- **F11** keeps the address in this browser and says plainly where renders go; it does not persist it on the desk or route
  renders through it.
- No model was downloaded (4.6 GB free on the models drive), so the new URLs and checksums are read from Hugging Face's file
  headers and the files on this machine, not proved by a download. The Moves thumbnails were seen with synthetic clips (none of
  the fifteen is downloaded here); "Render this move" was never pressed.
- A whole song that really failed, and a cut really rendering in My videos, were not forced (state set in the page).

## For the merge and for Tys

- T5: the step bar's Make button can read `window.XENO_STATE().setup.gate` or just keep `data-act="easy-make"` (`paintMakeGate`
  renames every such button after each `render()`). T4: Settings and About copy is done (M4's text), not the project scope. R0:
  `followRunningCut` (F14) is a small stand-in for resuming a running job; use yours if N3 landed.
- Tys: the Final's Download is now the fp8 set (40.0 GB) on every card; say if a 24 GB card should still get the 46 GB weights.
  Run `python scripts/fetch_moves.py` to see real Moves thumbnails. Side effect worth knowing: Moves and Variations now follow
  a proxy base path (`<body data-base>`) for their links, files and API calls, as the desk does.
