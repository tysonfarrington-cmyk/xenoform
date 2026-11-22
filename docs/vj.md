# Perform (`/vj`): the control view and the output window

`/vj` is one page in two windows (docs/UI_REVIEW.md 6.5):

- **The control view** (`/vj`): the transport, the song strip, now and next, the pads, the knobs, the source, REC. With
  no output window open it also shows the picture, as the old live page did.
- **The output window** (`/vj?out=1`): the canvas and nothing else. No bar, no HUD, no toast, no cursor, no keys except
  Esc, which hands focus back to the control view. Double-click it for fullscreen.

**Open output window** puts it on your second screen with the browser's Window Management API where it exists (Chrome
and Edge ask once for "window management"), fullscreen from that same click, and as a plain window you drag elsewhere
otherwise. The two talk over a `BroadcastChannel` ("xeno-rig"): the control view sends the scenes, the song's analysis,
the look, the knobs and the held pad; the output renders and records and reports its size, fps and REC state back. The
control view's monitor then shows the output window's live picture.

**The song plays in the control view** (the window you click in, so the browser lets it start), from its decoded buffer
on the AudioContext clock. The output window reads that clock, the analyser and the sound for a take straight from the
control view that opened it. The picture follows the sound as it is heard (`getOutputTimestamp`), one frame ahead,
which is also what keeps a take in sync (measured: docs/notes/t2-perform.md).

## Sources

- **This cut** (`/vj?job=<id>`, the cut's **Perform it** link beside Download): the cut's own clips are the first
  scenes, its song plays, its stems drive the effects, and the strip shows its own sections, beats and drop
  (`GET /api/perform/job/<id>`). **Follow the song** plays the cut as it was made: each shot's clip on the song's clock
  at the speed it was cut at. The other switch settings (every beat, 2 beats, bar, 2 bars) cut between its clips on the
  grid instead.
- **Library loops**: the shipped vibe loops and the desk's footage, plus **Add loops** (your own files). They load as
  they come up.
- **Load track** sends the file to the desk (`/api/analyze`), so the strip shows the song's passages, beats, bars and
  drops from the desk's analysis (`/api/simple/strip`, else `/api/perform/song/<id>`); until it answers, the beats come
  from the browser. `?track=<id>` opens a desk song (the desk's Perform link passes the song in use).
- **Mic / line-in**: beats from the input's energy, or tap tempo (T). The input goes to the analyser and into a take,
  never to the speakers. Echo cancellation, noise suppression and auto-gain are off so the music isn't processed away.
  A refused permission says how to allow it; choosing another input swaps the source.

## Playing

- **Transport**: Play/Pause (Space), back to the start (Home), the clock, **Cue next drop** (D). A cue lands on the next
  bar (the next beat when the switch is on every beat). Click a section on the strip to cue it; click the beat row to
  jump there.
- **Pads**: eight, the cut's own objects first, then looks (strobe, mirror, freeze, invert). Hold a pad (mouse, touch,
  Shift+1–8, or a learned MIDI note) and it shows; let go and the picture snaps back to where the song is, as if the pad
  was never pressed. Several held: the last one shows. A hold draws as a block on the strip's pad lane. Drag a scene, a
  still of the cut or a look onto a pad to change it (saved per cut in this browser). **Blackout** (B) is the panic.
- **Look**: the transition (1–8, 0 = auto), Mirror (M), Strobe (S), Kaleido (K, `?expert=1`), the knobs (Intensity,
  Speed, Glow, Chaos), **Master fade**, and the stem reactions. The effects run in WebGL with one fragment shader; the
  GPU cost is trivial and nothing is rendered by ComfyUI.

## REC

The REC dot and its timer live in the control view; the take is the output window's canvas (or this window's, with no
output window open) at its size, held while it runs, with the song's sound or the mic's. Chunks go to the desk every
second (`POST /api/perform/takes/<id>/chunk`), so a crash loses seconds, not the set; a take cut short is finished the
next time Perform opens. Stop has the desk make an H.264/AAC mp4 beside the webm in `work/ui/takes/<id>/`; the take
shows in My videos. Leaving the page during a take asks first.

## Flags

`?w=&h=` fix the canvas size (a take of exactly that size), `?fps=` the take's frame rate (30), `?vbr=` its bitrate,
`?clean=1` the monitor alone, `?seed=`, `?classic=1`, `?expert=1`, `?vibes=` and `?footage=0` choose the library,
`?sync=1` flashes white on every beat (the sync check). `window.VJ.go({start, seconds})` records a take for scripts.

## Stems from the loaded track

**Use this song's stems** sends the loaded track to the desk (`/api/analyze` gives it an id), asks `POST /api/stems` to
split it (Demucs when installed, else the band split; cached by song hash so the second time is instant), and the
envelopes drive the four stem uniforms (`sDrum`, `sBass`, `sOther`, `sVoc`) in both windows. The address keeps
`?stems=/api/stems/<id>/envelopes.json&track=<id>` so a reload picks the same track back up from `/media/audio/<id>`.
Per-stem gains are the desk's Stem reactions lanes (`localStorage["xeno-macros"]`, keys `stem:<name>`); the four role
gains ride on MIDI knobs 3–6 and the Stem reactions lanes here.

## MIDI

An Arturia MiniLab 3 works out of the box (pads = transitions and dance presets, knobs = intensity, switch rate and stem
gains). Any controller maps in Learn mode (L): the pads (`pad:1`–`pad:8`), Blackout, Master fade, the knobs, Play and Cue
next drop learn too. Firefox/Safari and headless runs get the controller through `xenoform midi serve`. See
[midi.md](midi.md).

## Checking it

`docs/ui_review/tools/perform_check.js` (Playwright) opens both windows, records ten seconds of a click track and proves
the take: saved as an mp4, the canvas's size, nothing in the corners, the sound and picture within a frame
(`perform_sync.py` measures it).
