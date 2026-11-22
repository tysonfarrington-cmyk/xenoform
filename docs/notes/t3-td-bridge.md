# T3, the TouchDesigner bridge (branch `t3-td-bridge`, 4 Nov 2026)

Cut from `ui-review-4nov` (574c1fc). Task T3 of [HANDOFF_4NOV.md](../HANDOFF_4NOV.md): stream OSC live from the desk beside the
offline export, send the MIDI-to-parameter bindings as OSC too, ship a TouchDesigner bridge with instructions. Nothing pushed,
nothing merged.

## What landed

| # | Commit | What |
|---|---|---|
| 1 | `0d5775c` | **The relay.** `osc_relay.py`: `POST /api/osc/frame` and `/ws/osc` take the page's frames, MIDI-bound parameters and raw MIDI; one OSC bundle per update on the offline address map plus the live extras, `/xenoform/param/<target>` and `/xenoform/midi`; `GET/PUT /api/osc` (host, port, on, rate 30 to 240, bundle, strings, pulse_ms, send); `GET /api/osc/status` (rate over the last second, the last message); `GET /api/osc/stream` (SSE) and `/ws/osc` fan every batch out like `/ws/midi`; python-osc lazy, every route answers one sentence without it (503). [docs/osc.md](../osc.md). |
| 2 | `1a92fe0` | **The sender.** `ui_static/osc_out.js`: a fixed-rate scheduler fed by both `requestAnimationFrame` and a timer, posting the HUD's values plus the derived ones (sub, rms, energy, onsets, beats, a live section/drop/mutate estimate) over `/ws/osc` or `POST /api/osc/frame`; wraps `XenoMidi.fire` and `handle` (midi.js untouched); the one control, **OSC to TouchDesigner** (host, port, Send OSC), above the MIDI panel in `?`. `vj.html`: a script tag and one block (`XenoOsc.init`, `XenoOsc.mount`). |
| 3 | `42792e5` | **The CLI.** `xenoform osc relay --host --port --desk --rate --transport auto/ws/sse --takeover --seconds ...`: reads the desk's `/ws/osc` or SSE, runs the same `OscRelay`, reconnects, warns when the desk sends to the same place, `--takeover` mutes the desk's own sending while it runs. `xenoform osc features.json` is untouched. |
| 4 | `bb16412` | **The TD bridge.** [td/README.md](../../td/README.md) (ten minutes: OSC In CHOP with named channels, a Select CHOP per family, a Movie File In TOP and where the loops live, the Feedback + Displace + Level + Composite example driven by bass and beat, `param/*`, every address with range and meaning, Picture into TD) and `td/xenoform_bridge.py` (builds it from the Textport in two lines; `build(save_tox=True)` writes the `.tox`). |
| 5 | this one | Tests (48 new), the measured numbers below, this note, and two small fixes the tests turned up (`vj.html`'s block is guarded by `if(window.XenoOsc)`, the control's install hint is neutral not red). |

Also edited: `ui.py` (three lines: include the router), `cli.py` (`main()` hands `osc relay` to `osc_relay.main_relay`; the `osc` help
points to it), `ui_static/vj.html` (below). New files only otherwise. `README.md`, `CHANGELOG.md`, `docs/vj.md` are **not** touched on
purpose (every session edits them; the lines to add at merge are at the end).

## Real `.tox`: no. README and script only

TouchDesigner was not running (the tdmcp bridge answered `connected: false` at 127.0.0.1:9980 twice, an hour apart) and I did not
launch it: it is installed (`C:\Program Files\Derivative\TouchDesigner`) but the GPU was holding 7.4 of 12 GB for Tys's ComfyUI, and the
brief says no GPU work. So **no `.tox` ships**. `td/xenoform_bridge.py` builds the same network when pasted in the Textport and says so in
the README (section 10). The next time TouchDesigner is open (with tdmcp, or just the Textport) it is two lines and "Save Component
.tox"; commit the result as `td/xenoform_bridge.tox`.

What stands in for running it: the parameter names and the wiring were checked against the Python stubs that ship with the installed
TouchDesigner (`bin/Lib/tdi/ops`, a 2023/2024 build, Python 3.11; this also caught that the OSC In CHOP's "Strip Prefix Segments" is
`stripprefixes` in that build, `stripsegments` in the older docs, so the script tries both), and `tests/test_td_bridge.py` runs the
script against a fake TouchDesigner that accepts only the real parameter names (`tests/fixtures/td_pars.json`, read from the stubs).
Menu tokens (`sequential`, `cycle`, `screen`, `simplex3d`) come from TouchDesigner's own help pages; a build that spells one differently
gets a line in the Textport and the rest still builds.

## The measured rate (a UDP listener counting messages per address per second)

| Path | Result |
|---|---|
| The real `/vj` page in the app's browser pane, a song playing, the page rendering at **30 fps**, websocket | all 27 frame channels **59.8 Hz mean, 59 or more in every one of 25 whole seconds** (plus the MIDI addresses when a controller event came) |
| Same, before the fix (the sender followed the render loop) | 29 to 30 Hz: a page that renders at 30 fps sent 30. The timer now feeds the same scheduler, so the stream no longer depends on the render rate |
| `xenoform osc relay` against that desk, websocket and SSE | 27 channels at 60 Hz (min 60) over 9 and 5 whole seconds |
| pytest, a paced 60 Hz poster over HTTP / over the websocket, 2 s, a quiet machine | per channel per second `[61, 60]` / `[59, 61]` |
| pytest, the headless relay against a real desk in a thread, SSE / websocket | `[61, 56]` / `[58, 57]` |
| The same HTTP test with four test suites running on the PC | `[51, 54]`: still over 30, but the poster's catch-up bursts are merged by the rate guard and the starved listener drops a few. When the poster itself cannot reach 40 posts a second the test skips instead of failing (it was 11 a second at the worst moment) |
| The relay alone (no HTTP), 60 Hz poster | 60.0 Hz, 27 addresses; one update costs 0.06 ms median, 0.77 ms p95 |

Measured at the UDP socket, **not inside TouchDesigner's OSC In CHOP**: TouchDesigner was not available. The README's rate meter (Slope
of the `frame` channel) is the in-TouchDesigner check; I could not run it.

## How to try it with TouchDesigner in ten minutes

1. `pip install "xenoform[osc]"`, `xenoform ui`, open `/vj`, load a song, `?` → **OSC to TouchDesigner** → **Send OSC** (127.0.0.1:7000).
2. TouchDesigner, Textport (Alt+T): `XENOFORM_DIR = r"C:\...\xenoform"` then `exec(open(XENOFORM_DIR + r"\td\xenoform_bridge.py").read())`. Put a loop in the COMP's *Clip*
   parameter (`src/xenoform/ui_static/library/neon-night/wide.mp4` is picked automatically when `XENOFORM_DIR` is set).
3. Play the song. `updates_per_second` inside the COMP reads about 60, the picture is `out`. By hand instead: section 3 of the README.

## Things you might not expect

- **The relay sends per post, not from a timer of its own.** On Windows `asyncio` sleeps in 15.6 ms steps (and `time.monotonic()` ticks
  that slowly before Python 3.13), which turns a 60 Hz timer into bursts of two; the sender owns the clock and the relay is a pure
  forwarder with a rate guard (never faster than 2x `rate`; frames inside one post, or inside the guard, are merged and a beat flag is kept).
- **`rate`** (30 to 240, default 60) is what the page posts at; the floor is enforced by validation and by the sender's scheduler.
- **Pulses.** `is_onset`, `is_beat` and pad parameters are held at 1 for `pulse_ms` (50), because a one-frame 1 at 60 Hz is easy to miss
  in a 60 fps cook. `is_drop` is a state and is not held.
- **A desk without python-osc** answers 503 with one sentence on every `/api/osc*` route and on `/ws/osc`; the page does not ask until
  the control has been seen or this browser used OSC before, so a default install never logs that 503. `GET /api/osc` also reports
  `websocket` (T1's lesson from `/ws/midi`): no upgrade is tried on a desk that cannot.
- **Strings** (`section`, `scene_name`, `/xenoform/midi`) are sent by default (the offline map has `section`) and the OSC In CHOP skips
  them; `strings:false` turns them off. I could not check whether a build warns on them.
- **`osc relay` is intercepted before argparse**, so the `osc` parser stays as it was. A features file literally named `relay` needs `./relay`.
- **Section/drop/mutate on the live page are an estimate** (the offline classifier on a sliding 30 s window); they differ from the
  offline export, which sees the whole song. `bass`/`mid`/`high` are the HUD's meters, not the offline bands.
- **osc_out.js makes its own box scrollable** if the page lets it overflow: the Help overlay clipped everything under the key table on a
  short screen (the MIDI mapping rows were unreachable). That is a page bug the review may already list; it is only patched for this control.

## What was not possible

- A real `.tox` and any run inside TouchDesigner (above). The `td/xenoform_bridge.py` first run is the real test of the script.
- **Spout/Syphon out of a browser** is not possible; the README documents the Screen Grab TOP route and OBS to NDI. Neither was run.
- The perform window (`/vj?out=1`) is T2's: the README names it and says to use `/vj?clean=1` until it lands.
- A window that is fully covered: the timer carries the stream and the node checks cover it, but Chrome slows timers of hidden pages
  (not those playing audio); I did not test a covered window in a real browser. Docs say to keep `/vj` visible.

## What is left, what needs Tys

- Run the two lines in TouchDesigner once, fix what the Textport reports, save and commit `td/xenoform_bridge.tox`.
- **T2 (perform window).** If `vj.html` is rewritten keep: the script tag after `midi.js`, and after `XenoMidi.init(...)` the guarded block
  (`XenoOsc.init({toast, frame})`, `XenoOsc.mount(el, 'before')`); `frame()` returns what the page shows (see the block and `osc_out.js`'s
  header). A perform window that has no help overlay can skip `mount` and turn OSC on through `PUT /api/osc`.
- **T1 (MIDI).** `osc_out.js` wraps `XenoMidi.fire(target, val, ev, entry)` and `XenoMidi.handle(ev, origin)` after `XenoMidi.init`. If either is
  renamed `hookMidi()` returns false and the parameters stop riding along (the node check and `tests/test_osc_out.py` pin the names).
  `entry.mode === 'trigger'` marks a pad.
- At merge, add to `CHANGELOG.md` (0.3.3): "**Live OSC to TouchDesigner** (T3 of the 4 Nov handoff). The live page streams its bass, beat, scene,
  transition, stems and every MIDI-bound parameter to TouchDesigner as OSC, 60 times a second, through the desk (`osc_relay.py`,
  `ui_static/osc_out.js`, `xenoform osc relay`); `td/README.md` and `td/xenoform_bridge.py` build the network. python-osc stays optional
  (`pip install "xenoform[osc]"`)." and a link to [osc.md](../osc.md) from `docs/vj.md` and `README.md`.
- The shared venv now has `python-osc 1.10.2` (the `[osc]` extra), as the brief allowed.

## Verification of this branch

- New: `tests/test_osc_relay.py` (28: the wire format with a fake clock, pulses, coalescing, params, MIDI, packet size, the routes, the
  UDP listener at 60 Hz over HTTP and websocket, the CLI parsing, a headless relay against a real desk on a free port),
  `tests/test_osc_optional.py` (3: every route answers the one sentence without python-osc; the module and the desk import without it; the
  offline export keeps its own sentence; this file imports nothing from python-osc, so it runs on a clean install where the other OSC
  tests skip: use `pip install -e ".[dev,osc]"` to run all of them), `tests/test_osc_out.py` (6: the node checks run from pytest, the page
  wiring, midi.js not edited), `tests/test_td_bridge.py` (11: the script against the fake TouchDesigner, the README against the channel
  table). 48 pass.
- Full suite once before the last commit (1748 tests collected; the repo's pytest config is `-q`, so I ran it with another `-q` and read
  only the failures): **two failures, neither from this branch.** `tests/test_midi.py::test_websocket_fan_out_and_http_ingest` fails on the
  untouched base (574c1fc) too: the shared venv now has mido (T1's `[midi]` install) and the test expects it absent; T1's branch rewrote
  that test. `tests/test_stems_own.py::test_clear_restores_the_split_kept_aside` failed once with four suites running on the PC at once
  and passes alone, on this branch and on the base. `test_turbo.py::test_demo_animatic_is_the_fast_path` (the timing test) passed.
- The real browser: `/vj` on my own desk (port 47358), a song playing, OSC to a UDP listener; the control, the MIDI hook (a CC and a pad
  through `XenoMidi.handle` gave `param/intensity` and `param/fx:3` plus the raw events), and the headless relay against it.
