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
    assert by[("note", 36)]["target"] == "fx:1" and by[("note", 36)]["mode"] == "trigger" and by[("note", 36)]["source"]["ch"] == 10
    assert by[("note", 50)]["target"] == "strobe" and by[("note", 50)]["mode"] == "toggle"
    assert by[("cc", 28)]["mode"] == "rel"
    desk = {m["target"] for m in mb.profile_mapping("minilab3", "desk")}
    assert {"macro:intensity", "macro:glow", "drums", "vocals", "stem:1"} <= desk
    assert len(mb.PROFILES["minilab3"]["controls"]) == 8 + 4 + 2 + 16
    assert mb.profile_mapping("generic", "vj") and mb.profile_mapping("nope", "vj") == mb.profile_mapping("generic", "vj")
    st = {}
    cc = by[("cc", 74)]
    assert mb.apply(cc, {"type": "cc", "num": 74, "value": 127}, st) == ("intensity", 2.0)
    tog = by[("note", 50)]
    assert mb.apply(tog, {"type": "note", "num": 50, "value": 100}, st) == ("strobe", 1.0)
    assert mb.apply(tog, {"type": "note", "num": 50, "value": 0}, st) is None
    assert mb.apply(tog, {"type": "note", "num": 50, "value": 100}, st) == ("strobe", 0.0)
    trig = by[("note", 36)]
    assert mb.apply(trig, {"type": "note", "num": 36, "value": 0}, st) is None
    assert mb.apply(trig, {"type": "note", "num": 36, "value": 1}, st) == ("fx:1", 1.0)
    assert mb.rel_delta(65) == 1 and mb.rel_delta(63) == -1 and mb.rel_delta(0) == 0
    assert mb.matches({"source": {"type": "cc", "ch": 0, "num": 1}}, {"type": "cc", "ch": 7, "num": 1})
    assert not mb.matches({"source": {"type": "cc", "ch": 2, "num": 1}}, {"type": "cc", "ch": 7, "num": 1})


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
    assert env["targets"]["fx:3"] == [0, 0, 1.0, 0, 0, 0, 0, 0, 0] and env["hits"]["fx:3"] == [0.5]
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
def test_websocket_fan_out_and_http_ingest():
    stems_api.hub.__init__()
    c = TestClient(create_app())
    with c.websocket_connect("/ws/midi?name=vj") as a, c.websocket_connect("/ws/midi") as b:
        assert a.receive_json()["type"] == "hello" and b.receive_json()["type"] == "hello"
        a.send_json({"type": "note", "ch": 10, "num": 36, "value": 100, "t": 1.0})
        got = b.receive_json()
        assert got["type"] == "note" and got["num"] == 36 and got["src"] == "vj" and got["seq"] == 1
        r = c.post("/api/midi/event", json={"events": [{"type": "cc", "ch": 1, "num": 74, "value": 10}, {"type": "clock"}]},
                   headers={"X-Xeno-Midi-Source": "bridge"})
        assert r.json()["sent"] == 1 and r.json()["listeners"] == 2
        assert a.receive_json()["src"] == "bridge" and b.receive_json()["num"] == 74
        a.send_text("not json")
        a.send_json({"bytes": [0xB0, 1, 99]})
        assert b.receive_json()["value"] == 99
    st = c.get("/api/midi/status").json()
    assert st["seq"] == 3 and st["listeners"] == 0 and "bridge" in st["sources"] and st["bridge"]["available"] is False
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
        return R()

    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    assert mb.post_events("http://127.0.0.1:47317/", [{"type": "cc", "ch": 1, "num": 1, "value": 1, "t": 0}])["sent"] == 1
    assert captured["url"] == "http://127.0.0.1:47317/api/midi/event" and captured["body"]["events"][0]["num"] == 1 and captured["src"] == "bridge"
