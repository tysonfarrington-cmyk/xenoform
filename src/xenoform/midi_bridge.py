"""Python-side MIDI: read a controller with mido, forward it to the desk, record a take, and turn a
recorded take into per-frame curves a render can follow.

    xenoform midi list                       # ports
    xenoform midi serve [--port NAME] [--desk http://127.0.0.1:47317]
    xenoform midi record take.json --seconds 60

``mido`` (and its ``python-rtmidi`` backend) are imported lazily: ``pip install xenoform[midi]``.
Without them every command explains what to install and nothing else breaks. The event format is
the same everywhere (browser Web MIDI, the websocket, this bridge, recorded takes):

    {"type": "cc"|"note"|"pitch"|"prog"|"touch", "ch": 1..16, "num": 0..127, "value": 0..127, "t": seconds}

A recorded take (``xenoform midi record``) is ``{"kind": "xenoform-midi-take", "events": [...]}``;
``automation_to_envelopes(take, fps)`` resolves it through a mapping into
``{"fps", "frames", "targets": {name: [0..1 per frame]}, "hits": {name: [t, ...]}}`` which is what
``state["midi_take"]`` carries into a render.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("xenoform")

INSTALL_HINT = "MIDI needs mido and python-rtmidi: pip install \"xenoform[midi]\"  (or: pip install mido python-rtmidi)"


class MidiUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------- profiles
# Arturia MiniLab 3 factory map (Arturia-mode template, confirmed against Arturia's MIDI Control Center
# manual and the MiniLab 3 user manual): knobs 1-8 = CC 74 71 76 77 93 18 19 16, faders 1-4 = CC 82 83 85 17,
# mod strip = CC 1, pads bank A = notes 36-43 and bank B = notes 44-51 on channel 10, keys + knobs on channel 1.
# UNCERTAIN: the clickable main encoder. The factory template sends it as a relative CC 28 in Arturia mode
# (DAW mode uses MCU/HUI messages instead). If yours differs, Learn mode re-binds it in one twist.
PROFILES: dict[str, dict] = {
    "minilab3": {
        "label": "Arturia MiniLab 3 (factory map)",
        "controls": [
            *[{"id": f"knob{i + 1}", "label": f"Knob {i + 1}", "type": "cc", "ch": 1, "num": n, "mode": "abs"}
              for i, n in enumerate((74, 71, 76, 77, 93, 18, 19, 16))],
            *[{"id": f"fader{i + 1}", "label": f"Fader {i + 1}", "type": "cc", "ch": 1, "num": n, "mode": "abs"}
              for i, n in enumerate((82, 83, 85, 17))],
            {"id": "mod", "label": "Mod strip", "type": "cc", "ch": 1, "num": 1, "mode": "abs"},
            {"id": "encoder", "label": "Main encoder (relative, uncertain)", "type": "cc", "ch": 1, "num": 28, "mode": "rel"},
            *[{"id": f"padA{i + 1}", "label": f"Pad A{i + 1}", "type": "note", "ch": 10, "num": 36 + i, "mode": "trigger"}
              for i in range(8)],
            *[{"id": f"padB{i + 1}", "label": f"Pad B{i + 1}", "type": "note", "ch": 10, "num": 44 + i, "mode": "trigger"}
              for i in range(8)],
        ],
        # default targets per page; the browser (midi.js) holds the same table
        "vj": {"knob1": "intensity", "knob2": "every", "knob3": "drums", "knob4": "bass", "knob5": "other", "knob6": "vocals",
               "knob7": "stem:1", "knob8": "stem:2", "fader1": "stem:3", "fader2": "stem:4", "fader3": "stem:5", "fader4": "stem:6",
               "mod": "intensity", "encoder": "fx:step",
               **{f"padA{i + 1}": f"fx:{i + 1}" for i in range(8)},
               "padB1": "dance:1", "padB2": "dance:2", "padB3": "dance:3", "padB4": "dance:4", "padB5": "dance:5", "padB6": "dance:6",
               "padB7": "strobe", "padB8": "record"},
        "desk": {"knob1": "macro:intensity", "knob2": "macro:speed", "knob3": "macro:chaos", "knob4": "macro:glow",
                 "knob5": "stem:1", "knob6": "stem:2", "knob7": "stem:3", "knob8": "stem:4",
                 "fader1": "drums", "fader2": "bass", "fader3": "other", "fader4": "vocals"},
    },
    "generic": {
        "label": "Generic controller (CC 1-8 knobs, notes 36-51 pads)",
        "controls": [
            *[{"id": f"knob{i + 1}", "label": f"CC {i + 1}", "type": "cc", "ch": 0, "num": i + 1, "mode": "abs"} for i in range(8)],
            *[{"id": f"pad{i + 1}", "label": f"Note {36 + i}", "type": "note", "ch": 0, "num": 36 + i, "mode": "trigger"} for i in range(16)],
        ],
        "vj": {"knob1": "intensity", "knob2": "every", "knob3": "drums", "knob4": "bass", "knob5": "other", "knob6": "vocals",
               **{f"pad{i + 1}": f"fx:{i + 1}" for i in range(8)}, **{f"pad{i + 9}": f"dance:{i + 1}" for i in range(6)},
               "pad15": "strobe", "pad16": "record"},
        "desk": {"knob1": "macro:intensity", "knob2": "macro:speed", "knob3": "macro:chaos", "knob4": "macro:glow",
                 "knob5": "drums", "knob6": "bass", "knob7": "other", "knob8": "vocals"},
    },
}

MODES = ("abs", "toggle", "trigger", "rel")
_TRIGGER_TARGETS = ("fx:", "dance:", "tap", "record", "fx:next", "fx:prev")


def profile_mapping(profile: str = "minilab3", page: str = "vj") -> list[dict]:
    """The mapping table (source -> target) a profile ships for a page, in the shared JSON shape:
    ``{"source": {"type", "ch", "num"}, "target", "mode", "min", "max"}``. ``ch`` 0 = any channel."""
    prof = PROFILES.get(profile) or PROFILES["generic"]
    targets = prof.get(page) or {}
    out = []
    for c in prof["controls"]:
        tgt = targets.get(c["id"])
        if not tgt:
            continue
        mode = c["mode"]
        if mode == "trigger" and tgt in ("strobe", "mirror", "hud", "kaleido", "record"):
            mode = "toggle"
        lo, hi = (0.0, 2.0) if tgt == "intensity" else (0.0, 1.0)
        out.append({"source": {"type": c["type"], "ch": c["ch"], "num": c["num"]}, "target": tgt, "mode": mode,
                    "min": lo, "max": hi, "label": c["label"]})
    return out


# ---------------------------------------------------------------- events
def normalise(msg, t: float | None = None) -> dict | None:
    """One MIDI message (a mido Message, raw bytes/list, or an already-normalised dict) to the shared
    event dict, or None for messages the desk does not use (clock, sysex, ...)."""
    if msg is None:
        return None
    if isinstance(msg, dict):
        if "bytes" in msg and not msg.get("type"):
            return normalise(msg["bytes"], msg.get("t", t))
        kind = str(msg.get("type") or "")
        if kind not in ("cc", "note", "pitch", "prog", "touch"):
            return None
        try:
            ev = {"type": kind, "ch": max(1, min(16, int(msg.get("ch", 1) or 1))), "num": max(0, min(127, int(msg.get("num", 0) or 0))),
                  "value": max(0, min(127, int(round(float(msg.get("value", 0) or 0))))),
                  "t": float(msg.get("t", t if t is not None else time.time()))}
        except (TypeError, ValueError):
            return None
        return ev
    if isinstance(msg, (bytes, bytearray, list, tuple)):
        b = [int(x) & 0xFF for x in msg]
        if not b or b[0] < 0x80:
            return None
        st, ch = b[0] & 0xF0, (b[0] & 0x0F) + 1
        d1 = b[1] if len(b) > 1 else 0
        d2 = b[2] if len(b) > 2 else 0
        tt = float(t if t is not None else time.time())
        if st == 0x90:
            return {"type": "note", "ch": ch, "num": d1, "value": d2, "t": tt}
        if st == 0x80:
            return {"type": "note", "ch": ch, "num": d1, "value": 0, "t": tt}
        if st == 0xB0:
            return {"type": "cc", "ch": ch, "num": d1, "value": d2, "t": tt}
        if st == 0xE0:
            return {"type": "pitch", "ch": ch, "num": 0, "value": (d1 | (d2 << 7)) >> 7, "t": tt}
        if st == 0xC0:
            return {"type": "prog", "ch": ch, "num": d1, "value": d1, "t": tt}
        if st == 0xD0:
            return {"type": "touch", "ch": ch, "num": 0, "value": d1, "t": tt}
        if st == 0xA0:
            return {"type": "touch", "ch": ch, "num": d1, "value": d2, "t": tt}
        return None
    kind = getattr(msg, "type", None)  # mido Message
    if kind is None:
        return None
    tt = float(t if t is not None else time.time())
    ch = int(getattr(msg, "channel", 0)) + 1
    if kind == "note_on":
        return {"type": "note", "ch": ch, "num": int(msg.note), "value": int(msg.velocity), "t": tt}
    if kind == "note_off":
        return {"type": "note", "ch": ch, "num": int(msg.note), "value": 0, "t": tt}
    if kind == "control_change":
        return {"type": "cc", "ch": ch, "num": int(msg.control), "value": int(msg.value), "t": tt}
    if kind == "pitchwheel":
        return {"type": "pitch", "ch": ch, "num": 0, "value": (int(msg.pitch) + 8192) >> 7, "t": tt}
    if kind == "program_change":
        return {"type": "prog", "ch": ch, "num": int(msg.program), "value": int(msg.program), "t": tt}
    if kind == "aftertouch":
        return {"type": "touch", "ch": ch, "num": 0, "value": int(msg.value), "t": tt}
    if kind == "polytouch":
        return {"type": "touch", "ch": ch, "num": int(msg.note), "value": int(msg.value), "t": tt}
    return None


def matches(entry: dict, ev: dict) -> bool:
    s = entry.get("source") or {}
    if s.get("type") != ev.get("type") or int(s.get("num", -1)) != int(ev.get("num", -2)):
        return False
    ch = int(s.get("ch") or 0)
    return ch == 0 or ch == int(ev.get("ch") or 0)


def rel_delta(value: int) -> int:
    """Relative encoder step (Arturia 'relative 1': 65..127 clockwise, 1..63 anticlockwise)."""
    v = int(value)
    return v - 64 if v >= 64 else -(64 - v) if v > 0 else 0


def apply(entry: dict, ev: dict, state: dict) -> tuple[str, float] | None:
    """Resolve one event through one mapping entry -> (target, value) or None (ignored note-off etc.).
    ``state`` keeps toggle/relative values between calls (target -> last value)."""
    tgt = str(entry.get("target") or "")
    mode = entry.get("mode") or "abs"
    lo, hi = float(entry.get("min", 0.0)), float(entry.get("max", 1.0))
    v = int(ev.get("value", 0))
    if mode == "abs":
        val = lo + (hi - lo) * v / 127.0
    elif mode == "rel":
        val = max(lo, min(hi, float(state.get(tgt, lo)) + (hi - lo) * rel_delta(v) / 100.0))
    elif mode == "toggle":
        if ev.get("type") == "note" and v == 0:
            return None
        val = hi if float(state.get(tgt, lo)) <= lo else lo
    else:  # trigger
        if v == 0:
            return None
        val = hi
    state[tgt] = val
    return tgt, round(float(val), 4)


# ---------------------------------------------------------------- mido (lazy)
def _backend():
    try:
        import mido
    except ImportError as exc:
        raise MidiUnavailable(INSTALL_HINT) from exc
    try:
        mido.set_backend("mido.backends.rtmidi")
    except Exception:
        pass
    return mido


def backend_available() -> dict:
    try:
        mido = _backend()
    except MidiUnavailable:
        return {"available": False, "detail": INSTALL_HINT}
    try:
        ports = list(mido.get_input_names())
    except Exception as exc:  # mido without a working rtmidi
        return {"available": False, "detail": f"mido is installed but no backend answers: {exc}. {INSTALL_HINT}"}
    return {"available": True, "ports": ports}


def list_ports(backend=None) -> list[str]:
    mido = backend or _backend()
    return list(mido.get_input_names())


def _pick_port(mido, port: str | None) -> str:
    names = list(mido.get_input_names())
    if not names:
        raise MidiUnavailable("No MIDI input found. Plug the controller in (USB) and try again.")
    if not port:
        pref = [n for n in names if "minilab" in n.lower()] or names
        return pref[0]
    for n in names:
        if port.lower() in n.lower():
            return n
    raise MidiUnavailable(f"No MIDI input matches {port!r}. Ports: {', '.join(names)}")


def _read(inp, seconds: float | None, on_event, idle: float = 0.004) -> int:
    """Pump ``inp.iter_pending()`` until ``seconds`` pass (None = until KeyboardInterrupt). Returns the count."""
    t0 = time.monotonic()
    n = 0
    try:
        while seconds is None or time.monotonic() - t0 < seconds:
            got = False
            for msg in inp.iter_pending():
                ev = normalise(msg, time.monotonic() - t0)
                if ev:
                    n += 1
                    on_event(ev)
                    got = True
            if not got:
                time.sleep(idle)
    except KeyboardInterrupt:
        pass
    return n


def post_events(desk: str, events: list[dict], *, source: str = "bridge", timeout: float = 2.0) -> dict:
    """Send a batch to the desk's ``POST /api/midi/event`` (stdlib only)."""
    req = urllib.request.Request(desk.rstrip("/") + "/api/midi/event", data=json.dumps({"events": events}).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "X-Xeno-Midi-Source": source}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (localhost desk)
        return json.loads(r.read().decode("utf-8") or "{}")


def serve(port: str | None = None, desk: str = "http://127.0.0.1:47317", *, seconds: float | None = None,
          backend=None, post=None, batch_ms: float = 8.0, echo=None) -> int:
    """Read the controller and forward normalised events to the desk. Events are batched every
    ``batch_ms`` so a knob sweep is one request, not a hundred. Returns the number of events sent."""
    mido = backend or _backend()
    name = _pick_port(mido, port)
    send = post or (lambda evs: post_events(desk, evs))
    pending: list[dict] = []
    sent = 0
    last_flush = time.monotonic()
    t_start = time.time()

    def flush():
        nonlocal pending, sent, last_flush
        if pending:
            batch, pending = pending, []
            try:
                send(batch)
                sent += len(batch)
            except Exception as exc:
                log.warning("desk unreachable at %s: %s", desk, exc)
        last_flush = time.monotonic()

    def on_event(ev):
        ev = {**ev, "t": round(t_start + ev["t"], 4)}
        pending.append(ev)
        if echo:
            echo(ev)
        if (time.monotonic() - last_flush) * 1000.0 >= batch_ms:
            flush()

    log.info("MIDI bridge: %s -> %s/api/midi/event (Ctrl-C to stop)", name, desk)
    with mido.open_input(name) as inp:
        t0 = time.monotonic()
        while seconds is None or time.monotonic() - t0 < seconds:
            try:
                n = _read(inp, batch_ms / 1000.0, on_event)
            except KeyboardInterrupt:
                break
            flush()
            if n == 0 and seconds is None:
                time.sleep(0.002)
    flush()
    return sent


def record(out: str | Path, seconds: float = 60.0, port: str | None = None, *, backend=None, profile: str = "minilab3",
           echo=None) -> dict:
    """Record a timed performance (knob rides, pad hits) to ``out`` as a take JSON."""
    mido = backend or _backend()
    name = _pick_port(mido, port)
    events: list[dict] = []

    def on_event(ev):
        ev = {**ev, "t": round(ev["t"], 4)}
        events.append(ev)
        if echo:
            echo(ev)

    log.info("recording %s for %.0fs (Ctrl-C to stop early)", name, seconds)
    with mido.open_input(name) as inp:
        _read(inp, seconds, on_event)
    take = {"kind": "xenoform-midi-take", "version": 1, "profile": profile, "port": name,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(float(events[-1]["t"] if events else seconds), 3),
            "events": events}
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(take), encoding="utf-8")
    return take


# ---------------------------------------------------------------- takes -> curves
def load_take(take) -> dict:
    if isinstance(take, (str, Path)):
        take = json.loads(Path(take).read_text(encoding="utf-8"))
    if not isinstance(take, dict) or not isinstance(take.get("events"), list):
        raise ValueError("not a MIDI take: expected {\"kind\": \"xenoform-midi-take\", \"events\": [...]}")
    return take


def automation_to_envelopes(take, fps: int = 24, *, mapping: list[dict] | None = None, page: str = "vj",
                            duration: float | None = None) -> dict:
    """Turn a recorded take into per-target per-frame curves (sample-and-hold between moves, 0..1,
    intensity 0..2 scaled back to 0..1) plus hit times for trigger targets. This is ``state["midi_take"]``:

        {"fps": 24, "frames": n, "seconds": s, "targets": {"intensity": [...], "stem:Kick": [...]},
         "hits": {"fx:3": [1.25, 4.0], "dance:2": [...]}, "profile": "minilab3", "source": "midi"}
    """
    take = load_take(take)
    events = sorted((normalise(e) for e in take["events"]), key=lambda e: e["t"] if e else 0.0)
    events = [e for e in events if e]
    mapping = mapping or profile_mapping(str(take.get("profile") or "minilab3"), page)
    secs = float(duration or take.get("seconds") or (events[-1]["t"] if events else 0.0))
    n = max(1, int(round(secs * fps)) + 1)
    state: dict = {}
    tracks: dict[str, list[tuple[int, float]]] = {}
    hits: dict[str, list[float]] = {}
    for ev in events:
        k = min(n - 1, max(0, int(round(ev["t"] * fps))))
        for entry in mapping:
            if not matches(entry, ev):
                continue
            res = apply(entry, ev, state)
            if res is None:
                continue
            tgt, val = res
            if entry.get("mode") == "trigger":
                hits.setdefault(tgt, []).append(round(float(ev["t"]), 4))
            hi = float(entry.get("max", 1.0)) or 1.0
            tracks.setdefault(tgt, []).append((k, val / hi if hi > 1.0 else val))
    targets: dict[str, list[float]] = {}
    for tgt, pts in tracks.items():
        curve = [0.0] * n
        trig = any(e.get("mode") == "trigger" and e.get("target") == tgt for e in mapping)
        if trig:
            for k, v in pts:
                curve[k] = max(curve[k], v)
        else:
            cur = 0.0
            i = 0
            for k in range(n):
                while i < len(pts) and pts[i][0] <= k:
                    cur = pts[i][1]
                    i += 1
                curve[k] = round(cur, 4)
        targets[tgt] = curve
    return {"fps": int(fps), "frames": n, "seconds": round(secs, 3), "targets": targets, "hits": hits,
            "profile": take.get("profile") or "minilab3", "source": "midi", "events": len(events)}


def take_value(env: dict, target: str, t: float, default: float = 0.0) -> float:
    """Sample a converted take at time t."""
    v = (env.get("targets") or {}).get(target)
    if not v:
        return default
    k = int(round(t * float(env.get("fps") or 24)))
    return float(v[min(max(k, 0), len(v) - 1)])
