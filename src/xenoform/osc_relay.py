"""Live OSC: the desk forwards what the live page computes to TouchDesigner (or anything that speaks OSC).

The offline export (``osc_export``) streams a finished song's features. This module streams the *live* page:

    /vj (browser)  --POST /api/osc/frame, or /ws/osc-->  desk  --UDP, OSC-->  TouchDesigner (OSC In CHOP)
                                                          |
                                                          +--/ws/osc, /api/osc/stream-->  ``xenoform osc relay``

A browser cannot send UDP, so the page posts what it computes every animation frame (a batch of frames, the MIDI-bound
parameter values that moved and the raw MIDI events) and this module turns each batch into one OSC bundle on the same
address map the offline export uses (``/xenoform/rms|sub|bass|mid|high|onset_env|beat_env|energy|mutate|is_onset|is_beat|
is_drop|frame|section|fps``), plus the live extras (``/xenoform/scene``, ``/xenoform/transition``, ``/xenoform/intensity``,
...), ``/xenoform/param/<target>`` for every MIDI target that moved and ``/xenoform/midi`` for the raw events.

``python-osc`` is optional (``pip install "xenoform[osc]"``). It is imported when an update is sent, never at import, and
without it every ``/api/osc`` route answers the one sentence in ``INSTALL_HINT`` and nothing else in the desk changes.

Rate. The page posts about ``rate`` frames a second (60 by default, never below 30). The relay sends one bundle per post
(frames that arrive inside a post are merged: the newest values, and a beat or onset flag from any of them stays), holds
a beat or onset flag high for ``pulse_ms`` so a 60 Hz receiver cannot miss a one-frame pulse, and never sends faster than
twice ``rate`` (a 144 Hz display is merged down). ``GET /api/osc/status`` reports the rate measured over the last second.

The headless relay (``xenoform osc relay``) reads the same batches from the desk and sends the OSC itself, from another
process or machine; it runs the same ``OscRelay`` so both ways give TouchDesigner identical messages.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from types import SimpleNamespace
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from xenoform.midi_bridge import normalise as normalise_midi
from xenoform.osc_export import OSC_CHANNELS

log = logging.getLogger("xenoform")
router = APIRouter()

INSTALL_HINT = "Live OSC needs the optional python-osc package: pip install 'xenoform[osc]'  (or: pip install python-osc)"
PREFIX = "/xenoform"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7000
RATE_MIN, RATE_MAX, RATE_DEFAULT = 30, 240, 60
DEFAULT_DESK = "http://127.0.0.1:47317"
MAX_FRAMES, MAX_PARAMS, MAX_MIDI = 64, 128, 128
PULSES = ("is_onset", "is_beat")  # one-frame flags in the features; is_drop is a state (the whole drop), so it is not held
MAX_BUNDLE_BYTES = 1200  # a bundle stays under one Ethernet frame (1472 bytes of UDP payload), so nothing is fragmented
REFRESH_S = 1.0  # every known parameter is sent again at this interval, so a receiver started late has them within a second


class OscUnavailable(RuntimeError):
    """python-osc is not installed: the message is the one sentence to show."""


class RelayStop(RuntimeError):
    """The headless relay cannot go on and says why (no websockets package, the desk refuses): it does not retry."""


def _osc() -> SimpleNamespace:
    """The python-osc pieces, imported on every call (never at module import) so a missing package is found when it is
    needed and a test can hide it."""
    try:
        from pythonosc.osc_bundle_builder import IMMEDIATELY, OscBundleBuilder
        from pythonosc.osc_message_builder import OscMessageBuilder
        from pythonosc.udp_client import UDPClient
    except ImportError as exc:
        raise OscUnavailable(INSTALL_HINT) from exc
    return SimpleNamespace(IMMEDIATELY=IMMEDIATELY, OscBundleBuilder=OscBundleBuilder, OscMessageBuilder=OscMessageBuilder,
                           UDPClient=UDPClient)


def osc_available() -> bool:
    try:
        _osc()
    except OscUnavailable:
        return False
    return True


def websocket_capable() -> bool:
    """Whether this desk can upgrade a websocket (uvicorn needs the websockets or wsproto package for it). The page asks
    before it opens /ws/osc, so a desk without the package never logs a failed upgrade; it posts instead."""
    import importlib.util

    return any(importlib.util.find_spec(name) is not None for name in ("websockets", "wsproto"))


def osc_version() -> str:
    try:
        from importlib.metadata import version

        return version("python-osc")
    except Exception:  # not installed through pip, or no metadata
        return ""


# ---------------------------------------------------------------- the address map
# frame field -> (kind, address under /xenoform). The batch the page posts uses the left-hand names.
FIELDS: dict[str, tuple[str, str]] = {
    **{name: ("f", name) for name in OSC_CHANNELS},
    "frame": ("i", "frame"), "section": ("s", "section"), "fps": ("f", "fps"),
    "t": ("f", "time"), "beat": ("i", "beat"), "bpm": ("f", "bpm"),
    "scene": ("i", "scene"), "scene_name": ("s", "scene_name"),
    "transition": ("f", "transition"), "transition_fx": ("i", "transition_fx"), "intensity": ("f", "intensity"),
}
STEM_ROLES = ("drums", "bass", "other", "vocals")  # frame["stems"][role] -> /xenoform/stem/<role>
# (address under /xenoform, osc type, range, group, what it is). One table: the API, the README and the tests read it.
CHANNELS: tuple[tuple[str, str, str, str, str], ...] = (
    ("rms", "float", "0..1", "audio", "Loudness of the signal (RMS)."),
    ("sub", "float", "0..1", "audio", "Sub-bass energy, 20 to 60 Hz."),
    ("bass", "float", "0..1", "audio", "Bass energy, the bass meter of the live page's HUD."),
    ("mid", "float", "0..1", "audio", "Mid energy, 150 Hz to 2 kHz."),
    ("high", "float", "0..1", "audio", "High energy, 4 to 12 kHz."),
    ("energy", "float", "0..1", "audio", "One loudness curve: 0.3 sub + 0.4 bass + 0.2 mid + 0.1 high, smoothed."),
    ("onset_env", "float", "0..1", "beat", "Jumps to 1 on a transient and falls away in about a quarter of a second."),
    ("beat_env", "float", "0..1", "beat", "Jumps to 1 on a beat and falls away; the pulse the picture breathes with."),
    ("is_onset", "float", "0 or 1", "beat", "1 for about 50 ms after a transient."),
    ("is_beat", "float", "0 or 1", "beat", "1 for about 50 ms after a beat of the song's grid."),
    ("is_drop", "float", "0 or 1", "beat", "1 while the song is in its drop (a live estimate on the live page)."),
    ("mutate", "float", "0..1", "beat", "How far the song asks the picture to change: calm 0, sustain 0.2, build 0.35, release 0.45, drop 1."),
    ("frame", "int", "counts up", "clock", "Update counter, one per update: a heartbeat and a rate meter."),
    ("fps", "float", "Hz", "clock", "Updates per second the stream is sending (measured; the offline export sends its feature rate)."),
    ("time", "float", "seconds", "clock", "Song position in seconds while a track plays, else the page's clock."),
    ("section", "string", "calm, build, drop, release, sustain", "clock", "The section the song is in. The OSC In CHOP skips strings; use mutate there."),
    ("bpm", "float", "BPM", "show", "Tempo of the track or the tap."),
    ("beat", "int", "counts up", "show", "Beats counted since the page loaded."),
    ("scene", "int", "0 and up", "show", "Index of the loop on screen; changes when the picture cuts."),
    ("scene_name", "string", "text", "show", "Name of the loop on screen (OSC In DAT; the OSC In CHOP skips strings)."),
    ("transition", "float", "0..1", "show", "Progress of the transition in flight, 0 between transitions."),
    ("transition_fx", "int", "0..14", "show", "Which transition the page is using or last used."),
    ("intensity", "float", "0..2", "show", "The page's effect intensity."),
    ("stem/drums", "float", "0..1", "stems", "Drums energy (the stem when the song is split, else a band estimate)."),
    ("stem/bass", "float", "0..1", "stems", "Bass stem energy."),
    ("stem/other", "float", "0..1", "stems", "Everything else."),
    ("stem/vocals", "float", "0..1", "stems", "Vocals energy."),
    ("param/<target>", "float", "target range", "params",
     "A MIDI-bound parameter that moved: param/intensity (0..2), param/every, param/drums, param/stem:1 ... param/fx:3 and "
     "param/dance:2 are 1 for about 50 ms (pads), param/mirror and param/strobe are 0 or 1."),
    ("midi", "string, int, int, int", "type, channel, number, value", "midi",
     "A raw MIDI event: type (cc, note, pitch, prog, touch), channel 1 to 16, number, value 0 to 127."),
    ("midi/<type>/<ch>/<num>", "int", "0..127", "midi", "The same event as a channel of its own: midi/cc/1/74 holds the last value of CC 74 on channel 1."),
)


def live_channels() -> list[dict]:
    return [{"address": f"{PREFIX}/{a}", "type": t, "range": r, "group": g, "meaning": m} for a, t, r, g, m in CHANNELS]


def live_address_map() -> dict[str, str]:
    return {f"{PREFIX}/{a}": t for a, t, *_ in CHANNELS}


# ---------------------------------------------------------------- cleaning what the page posts
FLOAT32_MAX = 3.4028234e38


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)) and math.isfinite(v):
        # OSC floats are 32 bit: a finite number past that range made python-osc raise at every later update, with the
        # value kept to be sent again, so one post silenced the output until the desk restarted
        return max(-FLOAT32_MAX, min(FLOAT32_MAX, float(v)))
    return None


def clean_frame(raw: Any) -> dict[str, float | int | str]:
    """One posted frame to {address under /xenoform: value}. Unknown keys and non-numbers are dropped."""
    out: dict[str, float | int | str] = {}
    if not isinstance(raw, dict):
        return out
    for key, (kind, addr) in FIELDS.items():
        if key not in raw:
            continue
        v = raw[key]
        if kind == "s":
            if isinstance(v, str) and v.strip():
                out[addr] = v.strip()[:64]
            continue
        f = _num(v)
        if f is not None:
            out[addr] = f if kind == "f" else int(round(f))
    stems = raw.get("stems")
    if isinstance(stems, dict):
        for role in STEM_ROLES:
            f = _num(stems.get(role))
            if f is not None:
                out[f"stem/{role}"] = f
    return out


_TARGET_BAD = re.compile(r"[^A-Za-z0-9_.:+\-]")


def clean_target(name: Any) -> str:
    """A MIDI target ('intensity', 'fx:3', 'stem:Kick') as the last part of an OSC address."""
    return _TARGET_BAD.sub("_", str(name).strip())[:48].strip("_.") if name is not None else ""


class Batch:
    """What one post carries, size-limited but not yet cleaned (so a headless relay can re-read exactly this)."""

    __slots__ = ("frames", "params", "triggers", "midi")

    def __init__(self, frames: list, params: dict, triggers: list, midi: list) -> None:
        self.frames, self.params, self.triggers, self.midi = frames, params, triggers, midi

    def as_dict(self) -> dict:
        return {"frames": self.frames, "params": self.params, "triggers": self.triggers, "midi": self.midi}


def split_body(body: Any) -> Batch:
    """The three shapes a poster may send: ``{"frames": [...], "params": {...}, "triggers": [...], "midi": [...]}``, one
    frame (a dict of channels) or a list of frames."""
    if isinstance(body, list):
        body = {"frames": body}
    if not isinstance(body, dict):
        raise ValueError("Send one frame, a list of frames or {\"frames\": [...], \"params\": {...}, \"midi\": [...]}.")
    if not any(k in body for k in ("frames", "params", "triggers", "midi")):
        body = {"frames": [body]}
    frames = body.get("frames") or []
    params = body.get("params") or {}
    triggers = body.get("triggers") or []
    midi = body.get("midi") or []
    if isinstance(frames, dict):
        frames = [frames]
    if not isinstance(frames, list) or not isinstance(params, dict) or not isinstance(triggers, list) or not isinstance(midi, list):
        raise ValueError("The frames and midi must be lists, the params an object of name: value, the triggers a list of names.")
    return Batch([f for f in frames[-MAX_FRAMES:] if isinstance(f, dict)],
                 dict(list(params.items())[:MAX_PARAMS]), [t for t in triggers[:MAX_PARAMS] if isinstance(t, str)], midi[-MAX_MIDI:])


# ---------------------------------------------------------------- settings
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,252}$")
SETTING_KEYS = ("on", "send", "host", "port", "rate", "bundle", "strings", "pulse_ms")


def _check_setting(key: str, v: Any) -> Any:
    if key in ("on", "send", "bundle", "strings"):
        if not isinstance(v, bool):
            raise ValueError(f"{key} must be true or false.")
        return v
    if key == "host":
        if not isinstance(v, str) or not _HOST_RE.match(v.strip()):
            raise ValueError("The host must be a name or an address such as 127.0.0.1 (no http:// and no port).")
        return v.strip()
    if key == "port":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not 1 <= int(v) <= 65535:
            raise ValueError("The port must be a whole number from 1 to 65535.")
        return int(v)
    if key == "rate":
        f = _num(v)
        if f is None or isinstance(v, bool) or not RATE_MIN <= f <= RATE_MAX:
            raise ValueError(f"The rate must be from {RATE_MIN} to {RATE_MAX} updates a second.")
        return int(round(f))
    if key == "pulse_ms":
        f = _num(v)
        if f is None or isinstance(v, bool) or not 0 <= f <= 500:
            raise ValueError("pulse_ms must be from 0 to 500.")
        return float(f)
    raise ValueError(f"Unknown setting {key!r}. The settings are: {', '.join(SETTING_KEYS)}.")


# ---------------------------------------------------------------- the relay
class OscRelay:
    """Turns batches of live frames into OSC and sends them. One instance serves the desk (``relay`` below); the headless
    ``xenoform osc relay`` makes its own. ``client_factory(host, port)`` returns an object with ``send(osc_message_or_bundle)``
    and ``close()`` (python-osc's ``UDPClient`` by default; a test passes a fake)."""

    def __init__(self, *, client_factory: Callable[[str, int], Any] | None = None, clock: Callable[[], float] = time.perf_counter) -> None:
        self.client_factory = client_factory or self._udp_client
        self.clock = clock
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.settings: dict[str, Any] = {"on": False, "send": True, "host": DEFAULT_HOST, "port": DEFAULT_PORT, "rate": RATE_DEFAULT,
                                             "bundle": True, "strings": True, "pulse_ms": 50.0}
            self._client = None
            self._client_key: tuple | None = None
            self.state: dict[str, float | int | str] = {}
            self.params: dict[str, float] = {}
            self._moved: set[str] = set()
            self._trig_until: dict[str, float] = {}
            self._pulse_until: dict[str, float] = {}
            self._pulse_now: set[str] = set()
            self._midi: list[dict] = []
            self._last_emit = -1e9
            self._last_refresh = -1e9
            self._last_in: float | None = None
            self._in_times: deque = deque()
            self._out_times: deque = deque()
            self.frames_in = self.bundles_out = self.messages_out = self.coalesced = self.errors = self.frame_no = 0
            self.last_error = ""
            self.last_message: dict | None = None
            self.last_frame: dict = {}

    # ---- the socket
    @staticmethod
    def _udp_client(host: str, port: int):
        client = _osc().UDPClient(host, port)
        try:  # Windows: an ICMP "port unreachable" (TouchDesigner not listening yet) must not make the next send raise
            client._sock.ioctl(socket.SIO_UDP_CONNRESET, False)  # type: ignore[attr-defined]
        except (AttributeError, OSError, ValueError):
            pass
        return client

    def _ensure_client(self):
        key = (self.settings["host"], self.settings["port"])
        if self._client is not None and self._client_key == key:
            return self._client
        self._close_client()
        try:
            self._client = self.client_factory(*key)
        except OscUnavailable:
            raise
        except OSError as exc:
            raise ValueError(f"Cannot send to {key[0]}:{key[1]}: {exc.strerror or exc}.") from exc
        self._client_key = key
        return self._client

    def _close_client(self) -> None:
        client, self._client, self._client_key = self._client, None, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            self._close_client()

    # ---- settings
    def public(self) -> dict:
        with self._lock:
            return {**self.settings, "available": osc_available(), "python_osc": osc_version(), "addresses": len(CHANNELS),
                    "websocket": websocket_capable()}

    def configure(self, patch: Any) -> dict:
        """Apply some settings (``on``, ``send``, ``host``, ``port``, ``rate``, ``bundle``, ``strings``, ``pulse_ms``). Raises
        ValueError with a plain sentence for a bad one, and changes nothing then."""
        if not isinstance(patch, dict):
            raise ValueError("Send an object such as {\"on\": true, \"host\": \"127.0.0.1\", \"port\": 7000}.")
        with self._lock:
            new = dict(self.settings)
            for key, v in patch.items():
                new[key] = _check_setting(key, v)
            old, self.settings = self.settings, new
            try:
                if new["on"] and new["send"]:
                    self._ensure_client()  # a host that does not resolve, or no python-osc, shows now rather than silently
                elif (old["host"], old["port"]) != (new["host"], new["port"]):
                    self._close_client()
            except Exception:
                self.settings = old
                raise
            if not new["on"] and old["on"]:
                self._moved.clear()
            return self.public()

    # ---- ingest
    def ingest(self, body: Any) -> dict:
        return self.ingest_batch(split_body(body))

    def ingest_batch(self, batch: Batch) -> dict:
        """Merge a post into the state and send an update when one is due. Returns what happened (the POST answers with it)."""
        with self._lock:
            now = self.clock()
            for raw in batch.frames:
                cleaned = clean_frame(raw)
                self.frames_in += 1
                self._in_times.append(now)
                for name in PULSES:
                    if cleaned.get(name):
                        self._pulse_now.add(name)
                        self._pulse_until[name] = now + self.settings["pulse_ms"] / 1000.0
                self.state.update(cleaned)
            trig = {clean_target(t) for t in batch.triggers}
            hold = max(self.settings["pulse_ms"], 1.0) / 1000.0
            moved = 0
            for name, value in batch.params.items():
                key, f = clean_target(name), _num(value)
                if not key or f is None:
                    continue
                moved += 1
                self._moved.add(key)
                if key in trig:
                    self._trig_until[key] = now + hold
                    self.params[key] = 0.0  # a pad is not a level: it comes back to 0 and the refresh must not replay the 1
                else:
                    self.params[key] = f
            events = [e for e in (normalise_midi(m) for m in batch.midi) if e]
            self._midi.extend(events)
            del self._midi[:-MAX_MIDI]
            self._last_in = now
            self._prune(now)
            sent = self._maybe_emit(now)
            return {"ok": True, "frames": len(batch.frames), "params": moved, "midi": len(events), "sent": sent,
                    "rate_hz": self._rate(self._out_times, now)}

    def _prune(self, now: float) -> None:
        for q in (self._in_times, self._out_times):
            while q and now - q[0] > 1.0:
                q.popleft()

    @staticmethod
    def _rate(q: deque, now: float) -> float:
        return float(sum(1 for t in q if now - t <= 1.0))

    def _maybe_emit(self, now: float) -> bool:
        if not (self.settings["on"] and self.settings["send"]):
            self._midi = []  # transient: not kept to be sent late, in a burst, when sending starts
            self._moved.clear()
            return False
        if now - self._last_emit < 0.5 / self.settings["rate"]:  # faster than twice the rate: merged into the next update
            self.coalesced += 1
            return False
        try:
            return self._emit(now)
        except OscUnavailable as exc:
            self.errors += 1
            self.last_error = str(exc)
            return False
        except (ValueError, OverflowError) as exc:  # the host stopped resolving, or a value OSC cannot carry
            self.errors += 1
            self.last_error = str(exc)
            return False

    # ---- what one update holds
    def build(self, now: float) -> list[tuple[str, list]]:
        """The messages of one update, as (address, args)."""
        st, msgs = self.state, []
        for name in OSC_CHANNELS:
            if name in PULSES:
                v = 1.0 if (name in self._pulse_now or now <= self._pulse_until.get(name, -1.0)) else 0.0
            else:
                v = float(st.get(name, 0.0))
            msgs.append((f"{PREFIX}/{name}", [v]))
        measured = self._rate(self._in_times, now)
        msgs.append((f"{PREFIX}/frame", [int(st["frame"]) if "frame" in st else self.frame_no]))
        msgs.append((f"{PREFIX}/fps", [float(st["fps"]) if "fps" in st else measured]))
        for key in ("time", "beat", "bpm", "scene", "transition", "transition_fx", "intensity"):
            if key in st:
                msgs.append((f"{PREFIX}/{key}", [st[key]]))
        for role in STEM_ROLES:
            if f"stem/{role}" in st:
                msgs.append((f"{PREFIX}/stem/{role}", [float(st[f"stem/{role}"])]))
        if self.settings["strings"]:
            for key in ("section", "scene_name"):
                if key in st:
                    msgs.append((f"{PREFIX}/{key}", [str(st[key])]))
        send = set(self._moved)
        if now - self._last_refresh >= REFRESH_S:
            send |= set(self.params)
            self._last_refresh = now
        for key in sorted(send | set(self._trig_until)):
            if key in self._trig_until:
                v = 1.0 if now <= self._trig_until[key] else 0.0
                if v == 0.0:
                    del self._trig_until[key]
            else:
                v = float(self.params.get(key, 0.0))
            msgs.append((f"{PREFIX}/param/{key}", [v]))
        for ev in self._midi:
            if self.settings["strings"]:
                msgs.append((f"{PREFIX}/midi", [ev["type"], int(ev["ch"]), int(ev["num"]), int(ev["value"])]))
            msgs.append((f"{PREFIX}/midi/{ev['type']}/{int(ev['ch'])}/{int(ev['num'])}", [int(ev["value"])]))
        return msgs

    def _packets(self, o: SimpleNamespace, built: list) -> list:
        """One bundle per update (more when it would not fit one Ethernet frame), or the bare messages with ``bundle`` off."""
        if not self.settings["bundle"]:
            return built
        packets: list = []
        group: list = []
        size = 16

        def close() -> None:
            nonlocal group, size
            if group:
                bb = o.OscBundleBuilder(o.IMMEDIATELY)
                for g in group:
                    bb.add_content(g)
                packets.append(bb.build())
            group, size = [], 16

        for m in built:
            if group and size + m.size + 4 > MAX_BUNDLE_BYTES:
                close()
            group.append(m)
            size += m.size + 4
        close()
        return packets

    def _emit(self, now: float) -> bool:
        client = self._ensure_client()
        o = _osc()
        self.frame_no += 1
        msgs = self.build(now)
        built = []
        for address, args in msgs:
            b = o.OscMessageBuilder(address=address)
            for a in args:
                b.add_arg(a)
            built.append(b.build())
        packets = self._packets(o, built)
        try:
            for packet in packets:
                client.send(packet)
        except OSError as exc:  # unreachable, a full buffer: counted, never raised into the page's post
            self.errors += 1
            self.last_error = f"{type(exc).__name__}: {exc.strerror or exc}"
            return False
        self._last_emit = now
        self._out_times.append(now)
        self.bundles_out += len(packets)
        self.messages_out += len(built)
        self.last_message = {"address": msgs[-1][0], "args": msgs[-1][1], "at": time.time()}
        self.last_frame = {a.removeprefix(PREFIX + "/"): (round(v[0], 4) if isinstance(v[0], float) else v[0])
                           for a, v in msgs if not a.startswith((f"{PREFIX}/midi", f"{PREFIX}/param"))}
        self._pulse_now.clear()
        self._moved.clear()
        self._midi = []
        return True

    # ---- reporting
    def status(self) -> dict:
        with self._lock:
            now = self.clock()
            self._prune(now)
            idle = None if self._last_in is None else round(now - self._last_in, 3)
            return {
                "on": self.settings["on"], "send": self.settings["send"], "host": self.settings["host"], "port": self.settings["port"],
                "rate": self.settings["rate"],
                "sending": bool(self.settings["on"] and self.settings["send"] and idle is not None and idle < 1.0),
                "rate_hz": self._rate(self._out_times, now), "in_rate_hz": self._rate(self._in_times, now),
                "idle_s": idle, "frames_in": self.frames_in, "bundles": self.bundles_out, "messages": self.messages_out,
                "coalesced": self.coalesced, "errors": self.errors, "last_error": self.last_error,
                "last_message": self.last_message, "last_frame": self.last_frame, "params": dict(self.params),
            }


relay = OscRelay()


# ---------------------------------------------------------------- the frame hub (what the headless relay subscribes to)
class FrameHub:
    """Fans every posted batch out to the connected listeners (websocket and SSE). Keeps the last 64 so a late listener can
    catch up with ``since=<seq>``. The shape is the MIDI hub's (``stems_api.MidiHub``)."""

    def __init__(self, keep: int = 64) -> None:
        self.seq = 0
        self.recent: deque = deque(maxlen=keep)
        self.listeners: dict[int, asyncio.Queue] = {}
        self._next = 1
        self.sources: dict[str, float] = {}

    def subscribe(self) -> tuple[int, asyncio.Queue]:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        k, self._next = self._next, self._next + 1
        self.listeners[k] = q
        return k, q

    def unsubscribe(self, k: int) -> None:
        self.listeners.pop(k, None)

    def publish(self, batch: dict, *, source: str = "http", skip: int | None = None) -> dict:
        self.seq += 1
        msg = {**batch, "seq": self.seq, "src": source}
        self.recent.append(msg)
        self.sources[source] = time.time()
        for k, q in list(self.listeners.items()):
            if k == skip:
                continue
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:  # a stalled listener loses its oldest
                try:
                    q.get_nowait()
                    q.put_nowait(msg)
                except Exception:
                    pass
        return msg

    def since(self, seq: int) -> list[dict]:
        return [m for m in self.recent if m["seq"] > seq]


hub = FrameHub()


def reset() -> None:
    """Back to the defaults (tests; also what a desk restart gives)."""
    relay.close()
    relay.reset()
    hub.__init__()


# ---------------------------------------------------------------- routes
def _need() -> None:
    """Every /api/osc route stops here without python-osc, with the one sentence."""
    try:
        _osc()
    except OscUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


async def _json(request: Request) -> Any:
    try:
        return await request.json()
    except Exception as exc:
        raise HTTPException(400, "Send JSON.") from exc


def _ingest(body: Any, source: str, skip: int | None = None) -> dict:
    try:
        batch = split_body(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    msg = hub.publish(batch.as_dict(), source=source, skip=skip)
    info = relay.ingest_batch(batch)
    return {**info, "seq": msg["seq"], "listeners": len(hub.listeners)}


@router.get("/api/osc")
async def osc_get() -> dict:
    """The live OSC settings: ``on``, ``send``, ``host``, ``port``, ``rate`` (30 to 240 Hz), ``bundle``, ``strings``, ``pulse_ms``."""
    _need()
    return relay.public()


@router.put("/api/osc")
async def osc_put(request: Request) -> dict:
    """Change some of them: ``{"on": true, "host": "127.0.0.1", "port": 7000, "rate": 60}``."""
    _need()
    body = await _json(request)
    try:
        return relay.configure(body)
    except OscUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/osc/frame")
async def osc_frame(request: Request) -> dict:
    """The live page (or any script) posts a batch: ``{"frames": [{"t", "rms", "sub", "bass", ...}], "params": {"intensity": 1.2},
    "triggers": ["fx:3"], "midi": [{"type": "cc", "ch": 1, "num": 74, "value": 64}]}``, one frame, or a list of frames."""
    _need()
    body = await _json(request)
    return _ingest(body, str(request.headers.get("x-xeno-osc-source") or "http")[:32])


@router.get("/api/osc/status")
async def osc_status() -> dict:
    """The rate measured over the last second, the last message sent, errors and listeners."""
    _need()
    return {**relay.status(), "listeners": len(hub.listeners), "seq": hub.seq, "sources": dict(hub.sources)}


@router.get("/api/osc/addresses")
async def osc_addresses() -> dict:
    """Every address the stream uses, its type, range and meaning (the table in td/README.md)."""
    _need()
    return {"prefix": PREFIX, "channels": live_channels()}


@router.get("/api/osc/stream")
async def osc_stream(since: int = -1, limit: int = 0, timeout: float = 0.0) -> StreamingResponse:
    """Server-sent events of every posted batch (the headless relay's way in when the websocket is not available).
    ``since`` replays buffered batches after that seq; ``limit``/``timeout`` end the stream (scripts, tests)."""
    _need()
    k, q = hub.subscribe()

    async def gen():
        n = 0
        t_end = time.monotonic() + timeout if timeout > 0 else None
        try:
            yield "retry: 1000\n\n"
            if since >= 0:
                for msg in hub.since(since):
                    n += 1
                    yield f"data: {json.dumps(msg)}\n\n"
                    if limit and n >= limit:
                        return
            while True:
                wait = None if t_end is None else max(0.0, t_end - time.monotonic())
                if wait is not None and wait <= 0:
                    return
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=wait if wait is not None else 15.0)
                except asyncio.TimeoutError:
                    if t_end is not None:
                        return
                    yield ": keep-alive\n\n"
                    continue
                n += 1
                yield f"data: {json.dumps(msg)}\n\n"
                if limit and n >= limit:
                    return
        finally:
            hub.unsubscribe(k)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.websocket("/ws/osc")
async def osc_ws(ws: WebSocket) -> None:
    """Two-way, like /ws/midi: every batch a client sends is merged, sent as OSC and fanned out to the other clients; every
    batch posted elsewhere is pushed to this client (the headless relay only listens)."""
    await ws.accept()
    try:
        _osc()
    except OscUnavailable as exc:
        await ws.send_json({"type": "error", "detail": str(exc)})
        await ws.close(code=1011)
        return
    k, q = hub.subscribe()
    name = str(ws.query_params.get("name") or (ws.client.host if ws.client else "ws"))[:32]

    async def pump():
        while True:
            await ws.send_json(await q.get())

    sender = asyncio.ensure_future(pump())
    try:
        await ws.send_json({"type": "hello", "seq": hub.seq, "listeners": len(hub.listeners), **relay.public()})
        while True:
            data = await ws.receive_text()
            try:
                body = json.loads(data)
            except ValueError:
                continue
            try:
                _ingest(body, name, skip=k)
            except HTTPException:
                continue
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        log.debug("osc ws closed", exc_info=True)
    finally:
        sender.cancel()
        hub.unsubscribe(k)


# ---------------------------------------------------------------- the headless relay: xenoform osc relay
def build_relay_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xenoform osc relay",
        description="Read the live page's frames from the desk (websocket /ws/osc, or server-sent events) and send them as OSC "
                    "from this process: for TouchDesigner on another machine, or to start and stop the sending apart from the desk. "
                    "The desk still needs python-osc (pip install 'xenoform[osc]'), and so does this.",
    )
    p.add_argument("--host", help=f"Where TouchDesigner listens (default: the config's osc.host, {DEFAULT_HOST}).")
    p.add_argument("--port", type=int, help=f"OSC In CHOP port (default: the config's osc.port, {DEFAULT_PORT}).")
    p.add_argument("--desk", default=DEFAULT_DESK, help=f"The desk to read from (default {DEFAULT_DESK}).")
    p.add_argument("--rate", type=int, default=RATE_DEFAULT, help=f"Updates a second, {RATE_MIN} to {RATE_MAX} (default {RATE_DEFAULT}).")
    p.add_argument("--transport", choices=("auto", "ws", "sse"), default="auto",
                   help="auto = the websocket when the websockets package is installed, else server-sent events.")
    p.add_argument("--seconds", type=float, default=None, help="Stop after this long (default: until Ctrl-C).")
    p.add_argument("--no-bundle", action="store_true", help="One UDP packet per message instead of one bundle per update.")
    p.add_argument("--no-strings", action="store_true", help="Leave out the string messages (section, scene_name, midi).")
    p.add_argument("--pulse-ms", type=float, default=50.0, help="How long a beat or onset flag stays 1 (default 50).")
    p.add_argument("--takeover", action="store_true",
                   help="Turn the desk's own sending off while this runs (and on again after), so TouchDesigner does not get every message twice.")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--config", help="JSON config; its osc.host and osc.port are the defaults for --host and --port.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _desk_call(desk: str, path: str, body: dict | None = None, timeout: float = 3.0) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(desk.rstrip("/") + path, data=data, method="GET" if body is None else "PUT",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (the desk the user named)
        return json.loads(r.read().decode("utf-8") or "{}")


def _sse_batches(desk: str, opener=urllib.request.urlopen, timeout: float = 20.0):
    with opener(desk.rstrip("/") + "/api/osc/stream", timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("data:"):
                try:
                    yield json.loads(line[5:].strip())
                except ValueError:
                    continue


def _ws_batches(desk: str, timeout: float = 20.0):
    try:
        from websockets.sync.client import connect
    except ImportError as exc:
        raise RelayStop("The websocket transport needs the websockets package: pip install websockets (or use --transport sse).") from exc
    url = re.sub(r"^http", "ws", desk.rstrip("/")) + "/ws/osc?name=relay"
    with connect(url, open_timeout=timeout) as conn:
        for message in conn:
            try:
                msg = json.loads(message)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "error":
                raise RelayStop(str(msg.get("detail") or "The desk refused the websocket."))
            if isinstance(msg, dict) and msg.get("type") != "hello":
                yield msg


def run_relay(args: argparse.Namespace, cfg: dict | None = None, *, out: Callable[[str], None] = print,
              relay_obj: OscRelay | None = None, batches: Callable[[str, str], Any] | None = None,
              stop: Callable[[], bool] | None = None) -> dict:
    """Subscribe to the desk and send OSC until ``--seconds`` pass or Ctrl-C. ``batches(desk, transport)`` yields the posted batches
    (tests pass a fake). Returns {"frames", "messages", "rate_hz"} at the end."""
    _osc()  # python-osc first: the one sentence before anything connects
    cfg = cfg or {}
    osc_cfg = cfg.get("osc") or {}
    host = args.host or osc_cfg.get("host") or DEFAULT_HOST
    port = args.port if args.port is not None else int(osc_cfg.get("port") or DEFAULT_PORT)
    if not RATE_MIN <= args.rate <= RATE_MAX:
        raise ValueError(f"The rate must be from {RATE_MIN} to {RATE_MAX} updates a second.")
    rl = relay_obj or OscRelay()
    rl.configure({"on": True, "host": host, "port": port, "rate": args.rate, "bundle": not args.no_bundle,
                  "strings": not args.no_strings, "pulse_ms": float(args.pulse_ms)})
    transport = args.transport
    if transport == "auto":
        try:
            import websockets  # noqa: F401
            transport = "ws"
        except ImportError:
            transport = "sse"
    taken: dict | None = None
    if args.takeover:
        try:
            taken = _desk_call(args.desk, "/api/osc")
            _desk_call(args.desk, "/api/osc", {"on": True, "send": False})
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise RuntimeError(f"Cannot reach the desk at {args.desk} to take over its sending: {exc}") from exc
    else:
        try:
            desk = _desk_call(args.desk, "/api/osc")
            if desk.get("on") and desk.get("send") and (desk.get("host"), desk.get("port")) == (host, port):
                out(f"The desk is also sending to {host}:{port}, so TouchDesigner would get every message twice: run with --takeover, "
                    "or turn off 'OSC to TouchDesigner' in the live page.")
            elif not desk.get("on"):
                out("Waiting for the live page: open /vj, press ?, and turn on 'OSC to TouchDesigner' (or run with --takeover).")
        except (urllib.error.URLError, OSError, ValueError):
            pass
    source = batches or (lambda desk, tr: _ws_batches(desk) if tr == "ws" else _sse_batches(desk))
    t0, last_print, frames = time.monotonic(), 0.0, 0
    out(f"Relaying {args.desk} ({transport}) -> OSC {host}:{port} at {args.rate} Hz. Ctrl-C to stop.")

    def finished() -> bool:
        return (stop is not None and stop()) or (args.seconds is not None and time.monotonic() - t0 >= args.seconds)

    # A reader thread holds the (blocking) connection and reconnects; this thread sends, prints and watches the clock.
    inbox: queue.Queue = queue.Queue(maxsize=2048)
    done = threading.Event()
    end_of_stream = object()

    def reader() -> None:
        while not done.is_set():
            try:
                for msg in source(args.desk, transport):
                    if done.is_set():
                        return
                    inbox.put(msg)
                if batches is not None:  # a fake source ends; the desk's stream only ends when the desk does
                    inbox.put(end_of_stream)
                    return
            except RelayStop as exc:
                inbox.put(exc)
                return
            except Exception as exc:  # the desk went away: say so and try again
                inbox.put(f"Lost the desk ({exc}); trying again in 2 s.")
            if done.wait(2.0):
                return

    threading.Thread(target=reader, name="osc-relay-reader", daemon=True).start()
    try:
        while not finished():
            try:
                item = inbox.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is end_of_stream:
                break
            if isinstance(item, RelayStop):
                raise item
            if isinstance(item, str):
                if not args.quiet:
                    out(item)
                continue
            rl.ingest_batch(split_body({k: item.get(k) for k in ("frames", "params", "triggers", "midi") if k in item}))
            frames += len(item.get("frames") or [])
            now = time.monotonic()
            if not args.quiet and now - last_print >= 1.0:
                st = rl.status()
                out(f"{st['rate_hz']:.0f} updates/s -> {host}:{port}  {st['messages']} messages  {st['errors']} errors")
                last_print = now
    except KeyboardInterrupt:
        pass
    finally:
        done.set()
        if taken is not None:
            try:
                _desk_call(args.desk, "/api/osc", {"send": bool(taken.get("send", True)), "on": bool(taken.get("on", False))})
            except (urllib.error.URLError, OSError, ValueError):
                pass
    st = rl.status()
    rl.close()
    return {"frames": frames, "messages": st["messages"], "bundles": st["bundles"], "rate_hz": st["rate_hz"], "errors": st["errors"]}


def main_relay(argv: list[str]) -> int:
    """``xenoform osc relay ...`` (cli.main hands the rest of the line here)."""
    from xenoform.config import load_config

    args = build_relay_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    try:
        res = run_relay(args, load_config(args.config))
    except (OscUnavailable, RuntimeError, ValueError) as exc:
        log.error("%s", exc)
        return 1
    if not args.quiet:
        print(f"{res['frames']} frames in, {res['messages']} messages sent.")
    return 0
