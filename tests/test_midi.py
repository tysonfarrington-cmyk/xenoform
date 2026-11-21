"""MIDI bridge: normalisation, profiles, a fake mido backend for serve/record, take -> envelopes, the desk hub."""
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from xenoform import midi_bridge as mb
from xenoform import stems_api
from xenoform.cli import main
from xenoform.ui import create_app


# ---------------------------------------------------------------- fake mido
class FakeInput:
    def __init__(self, msgs):
        self.msgs = list(msgs)

    def iter_pending(self):
        while self.msgs:
            yield self.msgs.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeMido:
    def __init__(self, ports=("Arturia MiniLab3 MIDI 0", "Other"), msgs=()):
        self.ports = list(ports)
        self.msgs = list(msgs)
        self.opened = []

    def get_input_names(self):
        return list(self.ports)

    def open_input(self, name):
        self.opened.append(name)
        return FakeInput(self.msgs)


def msg(**kw):
    return SimpleNamespace(**kw)


KNOB = [msg(type="control_change", channel=0, control=74, value=v) for v in (0, 64, 127)]
PAD = [msg(type="note_on", channel=9, note=36, velocity=100), msg(type="note_off", channel=9, note=36, velocity=0)]


# ---------------------------------------------------------------- normalise
def test_normalise_every_input_shape():
    assert mb.normalise(KNOB[1], 1.5) == {"type": "cc", "ch": 1, "num": 74, "value": 64, "t": 1.5}
    assert mb.normalise(PAD[0], 0.0)["value"] == 100 and mb.normalise(PAD[1], 0.0)["value"] == 0
    assert mb.normalise([0x99, 38, 90], 2.0) == {"type": "note", "ch": 10, "num": 38, "value": 90, "t": 2.0}
    assert mb.normalise(bytes([0xB0, 1, 127]), 0)["type"] == "cc"
    assert mb.normalise([0xE0, 0, 64], 0) == {"type": "pitch", "ch": 1, "num": 0, "value": 64, "t": 0.0}
    assert mb.normalise({"type": "cc", "ch": "10", "num": 7, "value": 200.0, "t": 3}) == {"type": "cc", "ch": 10, "num": 7, "value": 127, "t": 3.0}
    assert mb.normalise({"bytes": [0x90, 60, 1], "t": 9})["num"] == 60
    assert mb.normalise(msg(type="clock")) is None and mb.normalise([0xF8]) is None and mb.normalise({"type": "sysex"}) is None
    assert mb.normalise("junk") is None and mb.normalise(None) is None


def test_profiles_and_modes():
    vj = mb.profile_mapping("minilab3", "vj")
    by = {(m["source"]["type"], m["source"]["num"]): m for m in vj}
    assert by[("cc", 74)]["target"] == "intensity" and by[("cc", 74)]["max"] == 2.0
    # pads A1-A8 hold a scene (pad:N, shown while held); bank B keeps the dance presets, strobe and record
    assert by[("note", 36)]["target"] == "pad:1" and by[("note", 36)]["mode"] == "hold" and by[("note", 36)]["source"]["ch"] == 10
    assert by[("note", 44)]["target"] == "dance:1" and by[("note", 44)]["mode"] == "trigger"
    assert by[("note", 50)]["target"] == "strobe" and by[("note", 50)]["mode"] == "toggle"
    assert by[("cc", 28)]["mode"] == "rel"
    desk = {m["target"] for m in mb.profile_mapping("minilab3", "desk")}
    assert {"macro:intensity", "macro:glow", "drums", "vocals", "stem:1"} <= desk
    assert len(mb.PROFILES["minilab3"]["controls"]) == 8 + 4 + 2 + 16
    assert mb.profile_mapping("generic", "vj") and mb.profile_mapping("nope", "vj") == mb.profile_mapping("generic", "vj")
    # the generic map (an unknown controller): knobs in CC order, sliders to the master levels, pads in note order
    gen = {(m["source"]["type"], m["source"]["num"]): m["target"] for m in mb.profile_mapping("generic", "desk")}
    assert [gen[("cc", n)] for n in range(1, 5)] == ["macro:intensity", "macro:speed", "macro:chaos", "macro:glow"]
    assert [gen[("cc", n)] for n in range(5, 13)] == ["stem:1", "stem:2", "stem:3", "stem:4", "drums", "bass", "other", "vocals"]
    gvj = {(m["source"]["type"], m["source"]["num"]): m for m in mb.profile_mapping("generic", "vj")}
    assert gvj[("note", 36)]["target"] == "pad:1" and gvj[("note", 36)]["mode"] == "hold" and gvj[("note", 44)]["target"] == "dance:1"
    assert mb.mode_for("pad:3", "cc") == "hold" and mb.mode_for("intensity", "cc") == "abs" and mb.mode_for("fx:2", "note") == "trigger"
    # a CC on a one-shot target fires on the press, not on every tick: up through 64, or a 127-only button again
    tap = {"source": {"type": "cc", "ch": 1, "num": 20}, "target": "tap", "mode": mb.mode_for("tap", "cc"), "min": 0, "max": 1}
    assert tap["mode"] == "trigger" and mb.mode_for("record", "cc") == "toggle"
    st2 = {}
    fired = [mb.apply(tap, {"type": "cc", "num": 20, "value": v}, st2) is not None for v in (10, 70, 90, 30, 127, 127, 0)]
    assert fired == [False, True, False, False, True, True, False]
    st = {}
    cc = by[("cc", 74)]
    assert mb.apply(cc, {"type": "cc", "num": 74, "value": 127}, st) == ("intensity", 2.0)
    tog = by[("note", 50)]
    assert mb.apply(tog, {"type": "note", "num": 50, "value": 100}, st) == ("strobe", 1.0)
    assert mb.apply(tog, {"type": "note", "num": 50, "value": 0}, st) is None
    assert mb.apply(tog, {"type": "note", "num": 50, "value": 100}, st) == ("strobe", 0.0)
    trig = by[("note", 44)]
    assert mb.apply(trig, {"type": "note", "num": 44, "value": 0}, st) is None
    assert mb.apply(trig, {"type": "note", "num": 44, "value": 1}, st) == ("dance:1", 1.0)
    hold = by[("note", 36)]
    assert mb.apply(hold, {"type": "note", "num": 36, "value": 90}, st) == ("pad:1", 1.0)
    assert mb.apply(hold, {"type": "note", "num": 36, "value": 0}, st) == ("pad:1", 0.0)  # the release lets go
    assert mb.is_release({"type": "cc", "value": 63}) and not mb.is_release({"type": "cc", "value": 64})
    assert mb.rel_delta(65) == 1 and mb.rel_delta(63) == -1 and mb.rel_delta(0) == 0
    assert mb.matches({"source": {"type": "cc", "ch": 0, "num": 1}}, {"type": "cc", "ch": 7, "num": 1})
    assert not mb.matches({"source": {"type": "cc", "ch": 2, "num": 1}}, {"type": "cc", "ch": 7, "num": 1})


def test_vj_pads_hold_over_the_song_and_leave_its_timeline_alone():
    """/vj: pad:N rows (mode hold) press and release through XenoMidi.holds; a held pad is drawn over the song in
    frame() and nothing in the hold code moves the song (S.cur, the switcher, the track)."""
    static = stems_api.Path(stems_api.__file__).parent / "ui_static"
    js = (static / "midi.js").read_text(encoding="utf-8")
    assert "function HoldStack()" in js and "holds.press(r.target)" in js and "holds.release(h.t)" in js
    assert 'padA"+i,"pad:"+i' in js and "module.exports=core" in js  # pads A hold pad:N; the core loads under node
    # re-pointed at the 4 Nov merge: t2-perform rewrote vj.html (the control view in vj_control.js, the engine in
    # vj.html); a held pad is S.hold over the song's program (S.prog), which keeps moving on its own clock
    vj = (static / "vj.html").read_text(encoding="utf-8")
    ctl = (static / "vj_control.js").read_text(encoding="utf-8")
    assert 'H.top("pad:")' in ctl and "H.on((id) =>" in ctl and 'H.press("pad:" + n)' in ctl and 'H.release("pad:" + n)' in ctl
    assert "case 'hold':applyHold(a.h||null)" in vj and "const sceneHeld=()=>" in vj
    assert "if(sceneHeld()){const sc=S.scenes[S.prog]" in vj  # the program moves on under a held scene
    hooks = vj.split("function applyHold(h){", 1)[1].split("\n// the sound:", 1)[0]
    looks = vj.split("// Held looks (t1-midi)", 1)[1].split("// read: the value on screen", 1)[0]
    for moves_the_song in ("next(", "prev(", "S.prog=", "S.beats++", "S.beats=", "onBeat(", "trackEl.pause(",
                           "trackEl.play(", "trackEl.currentTime=", "S.used", "lastBeatIdx="):
        assert moves_the_song not in hooks, moves_the_song
        assert moves_the_song not in looks, moves_the_song
    # held looks: a dance/strobe/mirror/kaleido row "On while held" rides the hold stack, the latching handlers skip it
    assert "XenoMidi.holds.on(id=>{if(isLookHold(id))applyLookHolds()})" in vj and "if(!isHold(e))dance(+n)" in vj
    assert '"/api/perform/job/" + encodeURIComponent(id)' in ctl  # ?job=<id>: the cut's clips are the scenes and the pads


def test_soft_takeover_is_wired_on_both_pages():
    """Absolute knobs catch the value on screen before they move it: midi.js decides per (control, target) pair, and
    each page answers read(target) with what its control shows (the desk's macro strip, /vj's intensity and gains)."""
    static = stems_api.Path(stems_api.__file__).parent / "ui_static"
    js = (static / "midi.js").read_text(encoding="utf-8")
    assert "function Takeover(" in js and "takeover.decide(" in js and "if(!d.apply){this._awayChanged(k);continue}" in js
    assert "this.state[e.target]=screen" in js  # an encoder steps from the value on screen
    v6 = (static / "ui_v6.js").read_text(encoding="utf-8")
    assert "window.XENO_MACRO_GET=" in v6 and "read:t=>" in v6
    vj = (static / "vj.html").read_text(encoding="utf-8")  # re-pointed at the 4 Nov merge: t2's XP.readTarget answers
    ctl = (static / "vj_control.js").read_text(encoding="utf-8")
    assert "read:t=>XP.readTarget(t)" in vj and 'if (t === "intensity") return S.inten;' in ctl


def test_the_map_lives_on_the_same_screen():
    """UI_REVIEW 6.5, C7, V3, A5: midi_map.js badges every mappable control, draws the controller (Map), opens Learn as
    a popover anchored to the control, names its buttons and undoes a Remove; /vj docks it (never the ? modal), the
    desk shows it in the Knobs panel's MIDI row; midi.js loads it on demand."""
    static = stems_api.Path(stems_api.__file__).parent / "ui_static"
    face = (static / "midi_map.js").read_text(encoding="utf-8")
    for needle in ("window.XenoMidiMap=", "[data-midi],[data-midi-slot],.xf-knob[data-k],.xf-lane input[data-k]", "Move a knob or hit a pad",
                   'class="generate xm-done">Done', 'class="ghost xm-clear"', "Removed ${esc(undo.what)}", "xm-undo-go\">Undo",
                   'aria-label="${esc("Learn "+n+" again")}"', 'aria-label="${esc("Remove "+s+" from "+n)}"', "Save as the shipped preset",
                   "Reset to default", 'getElementById("midi-panel")', "X.on(\"event\"", "X.away(row)"):
        assert needle in face, needle
    css = (static / "midi_map.css").read_text(encoding="utf-8")
    assert "!important" not in css and "body.clean .xm-dock, body.clean .xm-badges, body.clean .xm-pop" in css
    assert not [c for c in set(stems_api.re.findall(r"#[0-9a-fA-F]{3,8}\b", css)) if c.lower() != "#fff"]  # the desk's tokens only
    js = (static / "midi.js").read_text(encoding="utf-8")
    assert 'api("/static/midi_map.js")' in js and 'api("/static/midi_map.css")' in js and "toggleDock(open)" in js
    assert "#xeno-midi-panel" not in js  # the old in-page table is gone
    # re-pointed at the 4 Nov merge: t2's help sheet keeps #midi-panel only as the fallback for a midi.js without a
    # dock, and drops it when midi.js docks the map (V3: never in the modal); L and the MIDI button call XP.midi()
    vj = (static / "vj.html").read_text(encoding="utf-8")
    ctl = (static / "vj_control.js").read_text(encoding="utf-8")
    assert "if(XenoMidi.dock){const mp=$('midi-panel');if(mp)mp.remove()}" in vj
    assert 'id="midib"' in vj and "else if(/^[lL]$/.test(k))XP.midi()" in vj
    assert "if (XenoMidi.toggleDock) { XenoMidi.toggleDock(); return; }" in ctl and '$("midib").onclick = () => window.XP.midi();' in ctl
    v6 = (static / "ui_v6.js").read_text(encoding="utf-8")
    assert 'data-xm-state="name"' in v6 and "canonical:t=>" in v6 and "targetName:t=>" in v6


# ---------------------------------------------------------------- lazy mido
def test_missing_mido_explains(monkeypatch):
    import builtins

    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "mido":
            raise ImportError("no mido")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(mb.MidiUnavailable, match="xenoform\\[midi\\]"):
        mb.list_ports()
    assert mb.backend_available()["available"] is False
    with pytest.raises(SystemExit, match="pip install"):  # the CLI says what to install (same shape as `xenoform mcp`)
        main(["midi", "list"])


def test_serve_forwards_batches_with_fake_backend():
    fake = FakeMido(msgs=KNOB + PAD + [msg(type="clock")])
    sent = []
    n = mb.serve(None, "http://127.0.0.1:1", seconds=0.1, backend=fake, post=lambda evs: sent.append(evs))
    assert fake.opened == ["Arturia MiniLab3 MIDI 0"]  # a MiniLab wins when no port is named
    flat = [e for b in sent for e in b]
    assert n == 5 == len(flat) and flat[0]["type"] == "cc" and flat[-1]["value"] == 0
    assert all(abs(e["t"] - time.time()) < 5 for e in flat)
    assert mb.serve("other", "http://x", seconds=0.05, backend=FakeMido(), post=lambda evs: None) == 0
    with pytest.raises(mb.MidiUnavailable, match="No MIDI input matches"):
        mb.serve("launchpad", "http://x", seconds=0.01, backend=FakeMido())
    with pytest.raises(mb.MidiUnavailable, match="Plug the controller"):
        mb.serve(None, "http://x", seconds=0.01, backend=FakeMido(ports=()))


def test_record_and_automation_to_envelopes(tmp_path, monkeypatch):
    fake = FakeMido(msgs=KNOB + PAD)
    out = tmp_path / "take.json"
    take = mb.record(out, seconds=0.1, backend=fake)
    assert take["kind"] == "xenoform-midi-take" and len(take["events"]) == 5 and json.loads(out.read_text())["profile"] == "minilab3"
    # a hand-written take: knob 1 ride, a pad hit, a strobe toggle, an encoder step
    take = {"kind": "xenoform-midi-take", "profile": "minilab3", "seconds": 2.0, "events": [
        {"type": "cc", "ch": 1, "num": 74, "value": 0, "t": 0.0}, {"type": "cc", "ch": 1, "num": 74, "value": 127, "t": 1.0},
        {"type": "note", "ch": 10, "num": 38, "value": 100, "t": 0.5}, {"type": "note", "ch": 10, "num": 38, "value": 0, "t": 0.6},
        {"type": "note", "ch": 10, "num": 50, "value": 100, "t": 1.5}, {"type": "cc", "ch": 1, "num": 19, "value": 64, "t": 0.25}]}
    env = mb.automation_to_envelopes(take, fps=4)
    assert env["fps"] == 4 and env["frames"] == 9 and env["source"] == "midi" and env["events"] == 6
    assert env["targets"]["intensity"] == [0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0]  # 0..2 scaled to 0..1, held
    # pad A3 held from 0.5 to 0.6 s: a gate on the frame it went down on (shorter than a frame, still seen), its press
    # in hits, its span in holds
    assert env["targets"]["pad:3"] == [0, 0, 1.0, 0, 0, 0, 0, 0, 0] and env["hits"]["pad:3"] == [0.5]
    assert env["holds"]["pad:3"] == [[0.5, 0.6]]
    long = mb.automation_to_envelopes({"profile": "minilab3", "seconds": 2.0, "events": [
        {"type": "note", "ch": 10, "num": 37, "value": 100, "t": 0.25}, {"type": "note", "ch": 10, "num": 37, "value": 0, "t": 1.0},
        {"type": "note", "ch": 10, "num": 39, "value": 100, "t": 1.5}]}, fps=4)  # A4 still down when the take ends
    assert long["targets"]["pad:2"] == [0, 1.0, 1.0, 1.0, 0, 0, 0, 0, 0] and long["holds"]["pad:4"] == [[1.5, 2.0]]
    assert long["targets"]["pad:4"][6:] == [1.0, 1.0, 1.0]
    assert env["targets"]["strobe"][6:] == [1.0, 1.0, 1.0] and env["targets"]["strobe"][5] == 0.0
    assert env["targets"]["stem:1"][1] == pytest.approx(64 / 127, abs=1e-3)  # knob 7 (CC 19) = stem lane 1
    assert mb.take_value(env, "intensity", 1.2) == 1.0 and mb.take_value(env, "nothing", 0.0, 0.3) == 0.3
    p = tmp_path / "t.json"
    p.write_text(json.dumps(take))
    assert mb.automation_to_envelopes(p, fps=24, duration=3.0)["frames"] == 73
    with pytest.raises(ValueError):
        mb.automation_to_envelopes({"events": "x"})
    # CLI record with the fake backend, plus the envelope side file
    monkeypatch.setattr(mb, "_backend", lambda: FakeMido(msgs=KNOB))
    env_path = tmp_path / "env.json"
    assert main(["midi", "record", str(tmp_path / "cli.json"), "--seconds", "0.05", "--envelopes", str(env_path)]) == 0
    assert "intensity" in json.loads(env_path.read_text())["targets"]
    assert main(["midi", "list"]) == 0


# ---------------------------------------------------------------- the desk hub
def test_websocket_fan_out_and_http_ingest(monkeypatch):
    # the status line reports the backend as it is; pin it, so the answer does not depend on whether this machine has
    # the [midi] extra installed (the shared venv does since 4 Nov) or a controller plugged in
    monkeypatch.setattr(mb, "backend_available", lambda: {"available": False, "detail": mb.INSTALL_HINT})
    stems_api.hub.__init__()
    c = TestClient(create_app())
    with c.websocket_connect("/ws/midi?name=vj") as a, c.websocket_connect("/ws/midi") as b:
        assert a.receive_json()["type"] == "hello" and b.receive_json()["type"] == "hello"
        a.send_json({"type": "note", "ch": 10, "num": 36, "value": 100, "t": 1.0})
        got = b.receive_json()
        assert got["type"] == "note" and got["num"] == 36 and got["src"] == "vj" and got["seq"] == 1
        r = c.post("/api/midi/event", json={"events": [{"type": "cc", "ch": 1, "num": 74, "value": 10}, {"type": "clock"}]},
                   headers={"X-Xeno-Midi-Source": "bridge", "X-Xeno-Midi-Device": "Minilab3 0"})
        assert r.json()["sent"] == 1 and r.json()["listeners"] == 2
        assert a.receive_json()["src"] == "bridge" and b.receive_json()["num"] == 74
        a.send_text("not json")
        a.send_json({"bytes": [0xB0, 1, 99]})
        assert b.receive_json()["value"] == 99
        with c.websocket_connect("/ws/midi") as late:  # a page that joins later learns the bridge's port from hello
            assert late.receive_json()["devices"] == {"bridge": "Minilab3 0"}
    st = c.get("/api/midi/status").json()
    assert st["seq"] == 3 and st["listeners"] == 0 and "bridge" in st["sources"] and st["bridge"]["available"] is False
    assert st["devices"] == {"bridge": "Minilab3 0"} and st["websocket"] is stems_api.ws_upgrade_available()
    assert c.post("/api/midi/event", content=b"nope", headers={"Content-Type": "application/json"}).status_code == 400
    assert c.post("/api/midi/event", json="x").status_code == 400
    # SSE catch-up for browsers without a websocket: replay since a seq, then stop at the limit
    with c.stream("GET", "/api/midi/stream", params={"since": 1, "limit": 2}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        data = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith("data: ")]
    assert [d["seq"] for d in data] == [2, 3]
    with c.stream("GET", "/api/midi/stream", params={"timeout": 0.05}) as r:
        assert all(not l.startswith("data:") for l in r.iter_lines())


def test_post_events_uses_the_hub_endpoint(monkeypatch):
    import urllib.request

    captured = {}

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true, "sent": 1}'

    def fake_open(req, timeout=0):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["src"] = req.get_header("X-xeno-midi-source")
        captured["dev"] = req.get_header("X-xeno-midi-device")
        return R()

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    assert mb.post_events("http://127.0.0.1:47317/", [{"type": "cc", "ch": 1, "num": 1, "value": 1, "t": 0}])["sent"] == 1
    assert captured["url"] == "http://127.0.0.1:47317/api/midi/event" and captured["body"]["events"][0]["num"] == 1 and captured["src"] == "bridge"
    assert captured["dev"] is None
    mb.post_events("http://127.0.0.1:47317", [{"type": "cc", "ch": 1, "num": 1, "value": 1, "t": 0}], device="Minilab3 0")
    assert captured["dev"] == "Minilab3 0"  # the port the bridge reads, so the pages pick its map by name


def test_status_says_whether_the_websocket_can_upgrade(monkeypatch):
    """Without websockets or wsproto uvicorn cannot upgrade /ws/midi; the status says so and midi.js goes to SSE."""
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name in ("websockets", "wsproto") else real(name, *a))
    assert stems_api.ws_upgrade_available() is False
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: object() if name == "wsproto" else real(name, *a))
    assert stems_api.ws_upgrade_available() is True
    js = (stems_api.Path(stems_api.__file__).parent / "ui_static" / "midi.js").read_text(encoding="utf-8")
    assert "/api/midi/status" in js and "websocket!==false" in js


def test_badges_skip_a_folded_row_and_a_pad_steps_a_chip_row():
    # the 4 Nov desk checks (integrate-4nov): a stem lane inside the closed Stem reactions <details> keeps a layout box in
    # Chrome and the hit test found the panel around it, so two phantom K7 badges floated under the MIDI row (SEL matches
    # the lane's label and its input): folded() asks checkVisibility (else a closed <details>), and one badge per target.
    # A pad learned onto a row of chips (feel, effects) took mode "abs", so its velocity picked the chip and its note-off
    # snapped back to the first: a note now steps along the row on its hit and does nothing on its release.
    face = (stems_api.Path(stems_api.__file__).parent / "ui_static" / "midi_map.js").read_text(encoding="utf-8")
    paint = face.split("function paintBadges(){")[1].split("\nlet moved=0;")[0]
    assert "if(!t||done.has(X.canonical(t)))continue;" in paint and "folded(el))continue;" in paint
    assert "done.add(X.canonical(t))" in paint and 'el.closest("[hidden],.hide"))continue' not in paint
    assert 'function folded(el){if(el.closest("[hidden],.hide"))return true;if(el.checkVisibility)return!el.checkVisibility();' in face
    drive = face.split("function drive(t,v,ev,row){")[1].split("\nif(!X.handlers")[0]
    assert 'const pad=!!(ev&&ev.type==="note"),hit=pad&&(ev.value|0)>0;' in drive
    assert 'if(mode==="abs"&&!pad){const i=' in drive and 'else if(pad?hit:v>lo||mode==="toggle")' in drive
    assert 'if(mode==="abs"&&!pad){const up=f>=.5;' in drive and "else if(pad?hit:mode!==\"hold\"||v>lo)el.click()" in drive
