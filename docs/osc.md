# Live OSC: the live page into TouchDesigner (`/vj` → desk → UDP)

The offline export (`xenoform osc song.features.json`, see [vj.md](vj.md)) plays a finished song's features as OSC. This
is the other half: what the **live page** computes every frame (bass, beat, the scene on screen, the knobs on your MIDI
controller) goes to TouchDesigner, Resolume, Max or anything else that speaks OSC while you play. A browser cannot send
UDP, so the page posts to the desk and the desk sends. Optional: `pip install "xenoform[osc]"` (python-osc). Without it
every route below answers `Live OSC needs the optional python-osc package: pip install 'xenoform[osc]'` and the rest
of the desk is unchanged.

```
/vj (browser)  --POST /api/osc/frame, or /ws/osc-->  desk  --UDP, OSC bundles, 60 Hz-->  127.0.0.1:7000
  osc_out.js                                          |                                   (TouchDesigner OSC In CHOP)
                                                      +--/ws/osc, /api/osc/stream-->  xenoform osc relay (headless)
```

TouchDesigner side: [td/README.md](../td/README.md) (ten minutes from nothing to a network moving to the music).

## Turn it on

1. Open `/vj`, press **?** and find **OSC to TouchDesigner** just above the MIDI panel. Pick the host and port (the defaults,
   `127.0.0.1` and `7000`, are what an OSC In CHOP on port 7000 expects) and press **Send OSC**.
2. Or without the page: `curl -X PUT http://127.0.0.1:47317/api/osc -H "Content-Type: application/json" -d "{\"on\": true}"`.
   The page streams while `on` is true, including after a reload.
3. Keep the `/vj` window visible: browsers pause a page that is fully covered or minimised, and then it has nothing to send
   (put it on a second screen, or beside TouchDesigner).

## What is sent

One OSC bundle per update, 60 times a second by default, on the address map of the offline export
(`/xenoform/rms|sub|bass|mid|high|onset_env|beat_env|energy|mutate|is_onset|is_beat|is_drop|frame|section|fps`) plus the live
extras. Every address, its type and range: `GET /api/osc/addresses`, and the table in [td/README.md](../td/README.md).

| Address | Type | Meaning |
|---|---|---|
| `/xenoform/rms` `sub` `bass` `mid` `high` `energy` | float 0..1 | loudness and the bands (bass, mid and high are the HUD's meters) |
| `/xenoform/onset_env` `beat_env` | float 0..1 | jump to 1 on a transient or a beat, then fall away |
| `/xenoform/is_onset` `is_beat` | float 0/1 | held at 1 for `pulse_ms` (50 ms) so a one-frame flag is not missed |
| `/xenoform/is_drop` `mutate` | float | live estimate of the song's drop and how far it asks the picture to change |
| `/xenoform/frame` `fps` `time` | int, float | update counter (a rate meter), updates a second as measured, song position in seconds |
| `/xenoform/section` `scene_name` | string | strings; the OSC In CHOP skips them, the OSC In DAT shows them |
| `/xenoform/bpm` `beat` `scene` `transition` `transition_fx` `intensity` | float, int | what the live page is doing |
| `/xenoform/stem/drums` `bass` `other` `vocals` | float 0..1 | the four stem energies that drive the picture |
| `/xenoform/param/<target>` | float | a MIDI-bound parameter that moved (`param/intensity` 0..2, `param/drums`, `param/stem:1`, ...); pad targets (`fx:3`, `dance:2`) are 1 for `pulse_ms` then 0; every known parameter is repeated once a second so a receiver started late has it |
| `/xenoform/midi` | string, 3 ints | a raw MIDI event: type (`cc` `note` `pitch` `prog` `touch`), channel, number, value |
| `/xenoform/midi/<type>/<ch>/<num>` | int 0..127 | the same event as a channel of its own (`midi/cc/1/74`, `midi/note/10/36`) |

## The API

`GET /api/osc` reads and `PUT /api/osc` changes (any subset; a bad value answers 400 with a sentence and changes nothing):

| Setting | Default | |
|---|---|---|
| `on` | `false` | the page streams while this is true |
| `send` | `true` | the desk sends the UDP itself (`false` while a headless relay does) |
| `host`, `port` | `127.0.0.1`, `7000` | where TouchDesigner listens (a name or an address, no `http://`) |
| `rate` | `60` | updates a second, 30 to 240; the page posts at about this rate and the desk never sends faster than twice it |
| `bundle` | `true` | one bundle per update; `false` sends each message as its own packet for receivers that dislike bundles |
| `strings` | `true` | `false` leaves out the string messages (`section`, `scene_name`, `midi`) |
| `pulse_ms` | `50` | how long a beat, an onset or a pad stays 1 |

`POST /api/osc/frame` takes what the page computes: `{"frames": [{"t": 12.5, "rms": 0.4, "sub": 0.3, "bass": 0.6, "mid": 0.3,
"high": 0.2, "onset_env": 0.1, "beat_env": 0.9, "energy": 0.5, "is_onset": 0, "is_beat": 1, "is_drop": 0, "frame": 750,
"section": "build", "fps": 60, "scene": 3, "scene_name": "neon-night · wide", "transition": 0.4, "transition_fx": 9, "intensity": 1.2,
"bpm": 128, "beat": 25, "stems": {"drums": 0.2, "bass": 0.5, "other": 0.1, "vocals": 0}}], "params": {"intensity": 1.2},
"triggers": ["fx:3"], "midi": [{"type": "cc", "ch": 1, "num": 74, "value": 64}]}`. A single frame object or a list of frames works
too; missing channels are sent as 0 (the twelve of the offline map) or left out (the extras). The same JSON over the websocket
`/ws/osc` is cheaper per frame, and every batch posted is fanned out to the other listeners (the websocket, and
`GET /api/osc/stream` as server-sent events), the way `/ws/midi` does for MIDI.

`GET /api/osc/status` reports `rate_hz` (updates sent in the last second), `in_rate_hz` (frames received), `idle_s`,
`last_message` (address, arguments, time), `last_frame` (the values last sent), `errors` and `last_error` (a closed port is
counted, never raised), `listeners` and the parameters it holds.

## Rate

The page sends `rate` updates a second from a fixed-rate scheduler that both the animation frame and a timer feed, so a page
that renders at 30 fps (a busy GPU) still sends 60 and a covered window is carried by the timer (browsers slow the timers of
hidden pages to about one a second unless the page is playing audio, so keep `/vj` visible). The desk sends one bundle per
post: frames that arrive together are merged (newest values; a beat or onset flag from any of them stays) and anything faster
than twice `rate` (a 144 Hz screen) is merged into the next update. Measured on this PC with the real `/vj` page playing a
song, rendering at 30 fps in the app's browser pane: all 27 frame channels arrived at 59.8 messages a second and never below
59 in any second over 25 s; see [notes/t3-td-bridge.md](notes/t3-td-bridge.md).

## The headless relay

```
xenoform osc relay --host 127.0.0.1 --port 7000 --desk http://127.0.0.1:47317
```

Reads the same batches from the desk's `/ws/osc` (or server-sent events with `--transport sse`) and sends the OSC from its
own process: TouchDesigner on another machine, a recorder, a desk that must not send. `--takeover` turns the desk's own
sending off while it runs (and back on after) so TouchDesigner does not get every message twice. `--rate`, `--no-bundle`,
`--no-strings`, `--pulse-ms`, `--seconds`, `--quiet` as above.

UDP carries no password: send only to machines you trust.
