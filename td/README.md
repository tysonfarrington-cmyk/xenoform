# Xenoform → TouchDesigner

The live page (`/vj`) sends what it hears and what you play to TouchDesigner as OSC, 60 times a second: the bands and the
beat, the scene on screen, the transition in flight, the stems, and every knob and pad of your MIDI controller. This page
takes you from nothing to a network moving to the music in about ten minutes. (What the desk does with it:
[docs/osc.md](../docs/osc.md).)

You need the Xenoform desk, `pip install "xenoform[osc]"` (python-osc, optional), and TouchDesigner 2022 or later.

## 1. Send (1 minute)

1. `pip install "xenoform[osc]"`, then start the desk: `xenoform ui` (it answers on `http://127.0.0.1:47317`).
2. Open `/vj` in the browser, **Load track** and pick a song, press **?**, find **OSC to TouchDesigner** (just above the MIDI
   panel), leave `127.0.0.1` and `7000` and press **Send OSC**. The line under it reads `to 127.0.0.1:7000 · 60 updates/s`.
3. Keep the `/vj` window visible: a browser pauses a window that is covered or minimised, and then there is nothing to send.
   Put it on a second screen or beside TouchDesigner.

No browser? `curl -X PUT http://127.0.0.1:47317/api/osc -H "Content-Type: application/json" -d "{\"on\": true}"`, and
anything that POSTs frames to `/api/osc/frame` is a source ([docs/osc.md](../docs/osc.md)).

## 2. Receive, one paste (2 minutes)

In TouchDesigner open the Textport (**Alt+T**) and paste two lines, with the path of your Xenoform folder:

```python
XENOFORM_DIR = r"C:\path\to\xenoform"
exec(open(XENOFORM_DIR + r"\td\xenoform_bridge.py").read())
```

That makes `/project1/xenoform_bridge`, a Base COMP, and touches nothing else in your project. Inside it (the same network
section 3 builds by hand): the **OSC In CHOP** on port 7000 with named channels, a **Select CHOP** and a **Null CHOP** per
family, a rate meter, a **Movie File In TOP** for a loop, and the example, a **Feedback TOP** and a **Displace TOP** driven by
`bass` and `beat_env` with a **Level** and a **Composite**. Click the COMP and open its **Xenoform** page: *Port*, *Clip* (a
movie file), *Displace*, *Feedback*, *Beatflash*. The picture is the `out` TOP inside; the COMP's tile shows it. Press play
on the track in `/vj` and it moves. To keep it as a file, right-click the COMP and **Save Component .tox** (or call
`build(save_tox=True)` in the Textport, which writes `td/xenoform_bridge.tox`).

## 3. Receive, by hand (8 minutes)

Everything below goes in one network; Tab opens the operator menu. Names are only for the expressions to find each other.

1. **OSC In CHOP**, name `osc_in`. *Network Port* `7000`, *Active* on, **Strip Prefix Segments `1`** so `/xenoform/bass`
   arrives as the channel `bass` (the table in section 5 uses these names). Its viewer shows about thirty channels as soon as
   the page streams. Allow TouchDesigner through the Windows firewall if it asks (private networks).
2. **A Select CHOP per family**, each with *CHOPs* `osc_in`, then a **Null CHOP** after it (reference the Null, never the Select):

   | Select CHOP | *Channel Names* | Null |
   |---|---|---|
   | `sel_audio` | `rms sub bass mid high energy` | `out_audio` |
   | `sel_beat` | `onset_env beat_env is_onset is_beat is_drop mutate` | `out_beat` |
   | `sel_show` | `intensity transition transition_fx scene bpm beat time fps frame` | `out_show` |
   | `sel_stems` | `stem*` | `out_stems` |
   | `sel_params` | `param*` | `out_params` |
   | `sel_midi` | `midi*` | `out_midi` |

3. **A rate meter.** Select CHOP `frame` → **Slope CHOP** → **Lag CHOP** (*Lag* 0.5). The channel reads the updates a second
   TouchDesigner receives: about 60 while the page streams (it counts the `frame` messages).
4. **Movie File In TOP**, name `movie`, *File* a loop (section 7 says where they are), *Play Mode* `Sequential`, *Extend
   Left* and *Extend Right* `Cycle`.
5. **The example: feedback, displace, level, composite.**
   - **Noise TOP** `noise`: *Type* `Simplex 3D (GPU)`, *Period* `0.35`, *Amplitude* `0.5`, *Offset* `0.5`, *Monochrome* off;
     *Translate Z* expression `absTime.seconds * 0.25`. It is the map that pushes the picture around.
   - **Composite TOP** `mix`, *Operation* `Screen`; input 1 `movie`, input 2 `fb_level` (below).
   - **Displace TOP** `displace`; input 1 `mix`, input 2 `noise`; *Displace Weight* X and Y expression
     `(op('out_audio')['bass'] or 0) * 0.08` (bass pushes the picture; the `or 0` keeps it quiet until the first message).
   - **Level TOP** `level`; input `displace`; *Brightness* expression `1 + 0.35 * (op('out_beat')['beat_env'] or 0)` (every beat
     brightens it). Then a **Null TOP** `out`: that is the picture.
   - The loop: **Feedback TOP** `feedback` (input `movie`, *Target TOP* `level`) → **Transform TOP** `fb_transform` (*Scale* X and
     Y expression `1.008 + 0.03 * (op('out_beat')['beat_env'] or 0)`) → **Level TOP** `fb_level` (*Opacity* `0.82`) → input 2 of `mix`.
6. **MIDI parameters** arrive in `out_params` as `param/<target>`. Drive anything with them, for example the Level's
   *Opacity*: `(op('out_params')['param/intensity'] or 1) / 2`. Section 6 lists the targets.

If a channel shows as `param_intensity` in your build instead of `param/intensity`, use the spelling the Null's viewer shows;
the patterns `param*` and `stem*` find both.

## 4. Check it moves (1 minute)

- `/vj` is playing and the line under **Send OSC** says `60 updates/s`; the rate meter in TouchDesigner reads about 60.
- Move a knob on the controller: a `param/...` channel changes (and `midi/cc/<channel>/<number>` shows the raw 0 to 127).
- Nothing? `curl http://127.0.0.1:47317/api/osc/status` shows `frames_in` rising when the page sends and `errors` when the
  desk cannot reach the port; section 9 has the usual causes.

## 5. Every address

OSC bundles of floats and ints at 60 Hz (never below 30), on one port. The names are after *Strip Prefix Segments* `1`.
`bass`, `mid` and `high` are the live page's HUD meters (the offline export's bands are normalised per song and a little
different); `is_onset`, `is_beat` and the pads are held at 1 for 50 ms so a 60 Hz receiver cannot miss them. Strings
(`section`, `scene_name`, the first `midi` form) are skipped by the OSC In CHOP; `mutate`, `is_drop` and the numeric `scene`
carry the same information.

| Address | Type | Range | Select CHOP | What it is |
|---|---|---|---|---|
| `/xenoform/rms` | float | 0..1 | `sel_audio` | Loudness of the signal (RMS). |
| `/xenoform/sub` | float | 0..1 | `sel_audio` | Sub-bass energy, 20 to 60 Hz. |
| `/xenoform/bass` | float | 0..1 | `sel_audio` | Bass energy, the bass meter of the live page's HUD. |
| `/xenoform/mid` | float | 0..1 | `sel_audio` | Mid energy, 150 Hz to 2 kHz. |
| `/xenoform/high` | float | 0..1 | `sel_audio` | High energy, 4 to 12 kHz. |
| `/xenoform/energy` | float | 0..1 | `sel_audio` | One loudness curve: 0.3 sub + 0.4 bass + 0.2 mid + 0.1 high, smoothed. |
| `/xenoform/onset_env` | float | 0..1 | `sel_beat` | Jumps to 1 on a transient and falls away in about a quarter of a second. |
| `/xenoform/beat_env` | float | 0..1 | `sel_beat` | Jumps to 1 on a beat and falls away; the pulse the picture breathes with. |
| `/xenoform/is_onset` | float | 0 or 1 | `sel_beat` | 1 for about 50 ms after a transient. |
| `/xenoform/is_beat` | float | 0 or 1 | `sel_beat` | 1 for about 50 ms after a beat of the song's grid. |
| `/xenoform/is_drop` | float | 0 or 1 | `sel_beat` | 1 while the song is in its drop (a live estimate on the live page). |
| `/xenoform/mutate` | float | 0..1 | `sel_beat` | How far the song asks the picture to change: calm 0, sustain 0.2, build 0.35, release 0.45, drop 1. |
| `/xenoform/frame` | int | counts up | `sel_show` | Update counter, one per update: a heartbeat and a rate meter. |
| `/xenoform/fps` | float | Hz | `sel_show` | Updates per second the stream is sending (measured; the offline export sends its feature rate). |
| `/xenoform/time` | float | seconds | `sel_show` | Song position in seconds while a track plays, else the page's clock. |
| `/xenoform/section` | string | calm, build, drop, release, sustain | - | The section the song is in. The OSC In CHOP skips strings; use mutate there. |
| `/xenoform/bpm` | float | BPM | `sel_show` | Tempo of the track or the tap. |
| `/xenoform/beat` | int | counts up | `sel_show` | Beats counted since the page loaded. |
| `/xenoform/scene` | int | 0 and up | `sel_show` | Index of the loop on screen; changes when the picture cuts. |
| `/xenoform/scene_name` | string | text | - | Name of the loop on screen (OSC In DAT; the OSC In CHOP skips strings). |
| `/xenoform/transition` | float | 0..1 | `sel_show` | Progress of the transition in flight, 0 between transitions. |
| `/xenoform/transition_fx` | int | 0..14 | `sel_show` | Which transition the page is using or last used. |
| `/xenoform/intensity` | float | 0..2 | `sel_show` | The page's effect intensity. |
| `/xenoform/stem/drums` | float | 0..1 | `sel_stems` | Drums energy (the stem when the song is split, else a band estimate). |
| `/xenoform/stem/bass` | float | 0..1 | `sel_stems` | Bass stem energy. |
| `/xenoform/stem/other` | float | 0..1 | `sel_stems` | Everything else. |
| `/xenoform/stem/vocals` | float | 0..1 | `sel_stems` | Vocals energy. |
| `/xenoform/param/<target>` | float | target range | `sel_params` | A MIDI-bound parameter that moved: param/intensity (0..2), param/every, param/drums, param/stem:1 ... param/fx:3 and param/dance:2 are 1 for about 50 ms (pads), param/mirror and param/strobe are 0 or 1. |
| `/xenoform/midi` | string, int, int, int | type, channel, number, value | - | A raw MIDI event: type (cc, note, pitch, prog, touch), channel 1 to 16, number, value 0 to 127. |
| `/xenoform/midi/<type>/<ch>/<num>` | int | 0..127 | `sel_midi` | The same event as a channel of its own: midi/cc/1/74 holds the last value of CC 74 on channel 1. |

The twelve audio and beat channels (down to `mutate`) plus `frame`, `fps` and `section` are the address map of the offline export
(`xenoform osc song.features.json`), so a network built on the live stream also plays a finished song; the rest is live only.

## 6. MIDI controller → parameters

One controller drives the page and TouchDesigner. The page applies your MIDI map (the MiniLab 3 default, or whatever you
learned with **L**, [docs/midi.md](../docs/midi.md)) and the desk forwards the result: `param/intensity` (0 to 2), `param/every`,
`param/drums|bass|other|vocals` and `param/stem:<N>` (0 to 1), `param/mirror|strobe|kaleido|record|hud` (0 or 1),
`param/fx:<N>` and `param/dance:<N>` (a pad: 1 for 50 ms, then 0). A parameter appears the first time it moves and is
repeated once a second, so a network started late has the last value within a second. For your own mapping use the raw
events: `midi/cc/<channel>/<number>` holds the last value of a knob, `midi/note/<channel>/<number>` is the velocity of a pad
and 0 on release.

## 7. The loops (Movie File In TOP)

- `/vj` plays the vibe loops in `<xenoform>/src/xenoform/ui_static/library/<vibe>/{wide,reveal,close,medium}.mp4`.
- The footage library is `<xenoform>/assets/library/<vibe>/<id>.mp4` (and `assets/library/fetched/` for what
  `scripts/fetch_library.py` pulls). `GET http://127.0.0.1:47317/api/footage?kind=video` lists it: each item has `id`, `title`,
  `vibes`, `available` and `url` (`/library-media/<id>`, served by the desk). Movie File In reads a URL too, but a local file
  is the safe choice.
- Your own renders are under `<xenoform>/work/ui/` (one folder per job), and any file works.
- The `scene` channel says which loop the page is showing; TouchDesigner plays its own copy, so switch yours on `scene` or
  `is_beat` if you want the two to cut together.

## 8. Picture into TD

A browser cannot hand TouchDesigner a texture (no Spout or Syphon from a web page), so the picture takes one of two routes,
and the OSC above runs in parallel either way:

1. **Window capture: the Screen Grab TOP**, TouchDesigner's way to take what is on a display. Run the clean output window full
   screen on a second display (the perform window, `/vj?out=1`; until it lands, `/vj?clean=1` and **F**) and point a Screen
   Grab TOP at that display.
2. **OBS to NDI.** OBS captures the window (or a Browser source of `/vj?clean=1`), its NDI output plugin (DistroAV) publishes
   it, and an **NDI In TOP** receives it.

Both carry the browser's picture at screen resolution. For the cleanest result rebuild the look in TouchDesigner from the loops
(section 7) and let the OSC drive it, which is what this page's example does.

## 9. If nothing arrives

- The line under **Send OSC** shows the desk's own answer. Without python-osc it says `Live OSC needs the optional python-osc
  package: pip install 'xenoform[osc]'`.
- `curl http://127.0.0.1:47317/api/osc/status`: `frames_in` not rising means the page is not sending (hidden window, **Send OSC**
  off); `errors` rising means the port is closed or blocked.
- One OSC In per UDP port: another OSC In CHOP or DAT on 7000 (or another program) takes it. Use another port in both places.
- TouchDesigner on another computer: put that computer's address in the host box (and open UDP 7000 in its firewall).
- Every message twice: the desk and `xenoform osc relay` are both sending to the same port; use `--takeover`.
- Strings in TouchDesigner: an OSC In DAT cannot share the CHOP's port. Run `xenoform osc relay --port 7001` beside the desk and
  put the DAT on 7001 (not tried in TouchDesigner).

## 10. What is not here, and what was not checked

- **No `.tox` ships.** TouchDesigner was not open while this was written, so the network is a script that builds it
  (`xenoform_bridge.py`) rather than a saved component; run it once and save the `.tox` (section 2).
- **Not run inside TouchDesigner.** The script and this page were checked against the Python stubs that ship with TouchDesigner
  (parameter names, wiring) and a stand-in for it in `tests/test_td_bridge.py`, and the stream was measured with a UDP listener
  (60 Hz on every channel from the real `/vj` page), not with an OSC In CHOP. A menu token your build spells differently is skipped with a
  line in the Textport; the rest still builds.
- **No Spout or Syphon** out of the browser (section 8).
