"""The live OSC relay (osc_relay.py): what a batch of frames becomes on the wire, the /api/osc routes, the 30 Hz floor measured with a
UDP listener, the missing-python-osc sentence on every route, and the headless ``xenoform osc relay``."""
import json
import socket
import threading
import time
from collections import Counter, defaultdict

import pytest

pytest.importorskip("pythonosc")
from fastapi.testclient import TestClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_bundle import OscBundle
from pythonosc.osc_server import ThreadingOSCUDPServer

from xenoform import osc_export, osc_relay
from xenoform.cli import main
from xenoform.osc_relay import OscRelay
from xenoform.ui import create_app


@pytest.fixture(autouse=True)
def _fresh_relay():
    osc_relay.reset()
    yield
    osc_relay.reset()


# ---------------------------------------------------------------- helpers
class FakeClient:
    """Stands in for python-osc's UDPClient: keeps what would have gone on the wire."""

    def __init__(self, fail=None):
        self.sent, self.fail, self.closed = [], fail, False

    def send(self, content):
        if self.fail:
            raise self.fail
        self.sent.append(content)

    def close(self):
        self.closed = True


def make_relay(**settings):
    box = {"t": 100.0}
    client = FakeClient()
    rl = OscRelay(client_factory=lambda host, port: client, clock=lambda: box["t"])
    rl.configure({"on": True, **settings})
    return rl, client, box


def messages(client, since=0):
    """Every (address, args) sent after the first `since` packets, bundles flattened."""
    out = []
    for packet in client.sent[since:]:
        for m in (packet if isinstance(packet, OscBundle) else [packet]):
            out.append((m.address, list(m.params)))
    return out


def by_address(msgs):
    d = defaultdict(list)
    for a, args in msgs:
        d[a].append(args)
    return d


FRAME = {"t": 12.5, "rms": 0.4, "sub": 0.3, "bass": 0.6, "mid": 0.3, "high": 0.2, "onset_env": 0.1, "beat_env": 0.9, "energy": 0.5,
         "mutate": 0.2, "is_onset": 0, "is_beat": 1, "is_drop": 0, "frame": 750, "section": "build", "fps": 60, "scene": 3,
         "scene_name": "neon-night · wide", "transition": 0.4, "transition_fx": 9, "intensity": 1.2, "bpm": 128, "beat": 25,
         "stems": {"drums": 0.2, "bass": 0.5, "other": 0.1, "vocals": 0}}


class Listener:
    """A python-osc UDP server on a free port that counts every message by address and by second since the first one."""

    def __init__(self):
        self.lock = threading.Lock()
        self.t0 = None
        self.bins = defaultdict(Counter)
        self.last = {}
        d = Dispatcher()
        d.set_default_handler(self.on_message)
        self.server = ThreadingOSCUDPServer(("127.0.0.1", 0), d)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def on_message(self, address, *args):
        with self.lock:
            now = time.perf_counter()
            self.t0 = self.t0 or now
            self.bins[int(now - self.t0)][address] += 1
            self.last[address] = list(args)

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def per_second(self, address, seconds=2):
        with self.lock:
            return [self.bins[s][address] for s in range(seconds)]

    def total(self, address):
        with self.lock:
            return sum(c[address] for c in self.bins.values())

    def addresses(self):
        with self.lock:
            return {a for c in self.bins.values() for a in c}


def post_at(rate, seconds, post, frame=FRAME):
    """A paced poster: `rate` posts a second for `seconds`, spin-waiting to the deadline (Windows sleeps in 15 ms steps)."""
    start, n = time.perf_counter(), 0
    while time.perf_counter() - start < seconds:
        due = start + n / rate
        while time.perf_counter() < due:
            pass
        post({**frame, "frame": n, "is_beat": n % 30 == 0})
        n += 1
    return n


FRAME_CHANNELS = [f"/xenoform/{n}" for n in (*osc_export.OSC_CHANNELS, "frame", "fps")]


# ---------------------------------------------------------------- the address map
def test_the_live_address_map_extends_the_offline_one():
    live = osc_relay.live_address_map()
    for address, kind in osc_export.address_map().items():
        assert live[address] == kind, address
    assert {"/xenoform/scene", "/xenoform/transition", "/xenoform/intensity", "/xenoform/param/<target>", "/xenoform/midi"} <= set(live)
    assert len(osc_relay.live_channels()) == len(osc_relay.CHANNELS) and all(c["meaning"] for c in osc_relay.live_channels())


# ---------------------------------------------------------------- one update on the wire
def test_a_posted_frame_goes_out_as_one_bundle_on_the_offline_address_map():
    rl, client, _ = make_relay()
    info = rl.ingest({"frames": [FRAME]})
    assert info["sent"] and len(client.sent) == 1 and isinstance(client.sent[0], OscBundle)
    got = by_address(messages(client))
    for name in osc_export.OSC_CHANNELS:
        assert isinstance(got[f"/xenoform/{name}"][0][0], float), name
    assert got["/xenoform/bass"] == [[pytest.approx(0.6)]] and got["/xenoform/is_beat"] == [[1.0]] and got["/xenoform/is_drop"] == [[0.0]]
    assert got["/xenoform/frame"] == [[750]] and got["/xenoform/section"] == [["build"]] and got["/xenoform/fps"] == [[60.0]]
    assert got["/xenoform/scene"] == [[3]] and got["/xenoform/scene_name"] == [["neon-night · wide"]] and got["/xenoform/time"] == [[12.5]]
    assert got["/xenoform/transition_fx"] == [[9]] and got["/xenoform/intensity"] == [[pytest.approx(1.2)]] and got["/xenoform/beat"] == [[25]]
    assert got["/xenoform/stem/drums"] == [[pytest.approx(0.2)]] and got["/xenoform/stem/bass"] == [[pytest.approx(0.5)]]
    assert all(len(a) == 1 for a in got.values())


def test_a_poster_that_sends_little_still_gets_the_whole_offline_map_and_a_frame_counter():
    rl, client, box = make_relay()
    rl.ingest({"frames": [{"bass": 0.5}]})
    box["t"] += 0.02
    rl.ingest({"bass": 0.7})
    got = by_address(messages(client))
    assert all(f"/xenoform/{n}" in got for n in osc_export.OSC_CHANNELS) and got["/xenoform/rms"] == [[0.0], [0.0]]
    assert [a[0] for a in got["/xenoform/frame"]] == [1, 2], "the relay counts the updates when the page does not"
    assert "/xenoform/scene" not in got and "/xenoform/section" not in got, "the extras are left out until they are posted"
    assert got["/xenoform/bass"] == [[0.5], [pytest.approx(0.7)]]  # OSC floats are 32 bit


def test_a_beat_or_onset_stays_up_for_pulse_ms_so_a_60hz_receiver_cannot_miss_it():
    rl, client, box = make_relay()
    seen = []
    for i, t in enumerate((0.0, 0.016, 0.033, 0.049, 0.066, 0.083)):
        box["t"] = 100.0 + t
        rl.ingest({"frames": [{"is_beat": 1 if i == 0 else 0, "is_onset": 0, "is_drop": 1 if i >= 2 else 0}]})
        seen.append(by_address(messages(client, len(client.sent) - 1))["/xenoform/is_beat"][0][0])
    assert seen == [1.0, 1.0, 1.0, 1.0, 0.0, 0.0]  # 50 ms, then down
    drops = [a[0] for a in by_address(messages(client))["/xenoform/is_drop"]]
    assert drops == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0], "is_drop is a state, not a pulse"
    rl.configure({"pulse_ms": 0})
    box["t"] += 1
    rl.ingest({"frames": [{"is_beat": 1}]})
    box["t"] += 0.02
    rl.ingest({"frames": [{"is_beat": 0}]})
    assert [a[0] for a in by_address(messages(client, len(client.sent) - 2))["/xenoform/is_beat"]] == [1.0, 0.0]


def test_frames_in_one_post_are_merged_and_a_flag_from_any_of_them_survives():
    rl, client, _ = make_relay()
    rl.ingest({"frames": [{"bass": 0.1, "is_beat": 1}, {"bass": 0.2}, {"bass": 0.3, "is_beat": 0}]})
    assert len(client.sent) == 1
    got = by_address(messages(client))
    assert got["/xenoform/bass"] == [[pytest.approx(0.3)]] and got["/xenoform/is_beat"] == [[1.0]]


def test_posts_faster_than_twice_the_rate_are_coalesced_into_the_next_update():
    rl, client, box = make_relay(rate=60)
    rl.ingest({"frames": [{"bass": 0.1}]})
    box["t"] += 0.002  # 500 Hz poster: inside half the 60 Hz period
    rl.ingest({"frames": [{"bass": 0.2, "is_beat": 1}]})
    box["t"] += 0.002
    rl.ingest({"frames": [{"bass": 0.3}]})
    assert len(client.sent) == 1 and rl.status()["coalesced"] == 2
    box["t"] += 0.010
    rl.ingest({"frames": [{"bass": 0.4}]})
    got = by_address(messages(client, 1))
    assert got["/xenoform/bass"] == [[pytest.approx(0.4)]] and got["/xenoform/is_beat"] == [[1.0]], "the beat of the skipped post is not lost"


# ---------------------------------------------------------------- parameters and MIDI
def test_midi_parameters_that_moved_are_sent_once_and_repeated_every_second():
    rl, client, box = make_relay()
    rl.ingest({"frames": [{}], "params": {"intensity": 1.5, "stem:Kick": 0.25}})
    first = by_address(messages(client))
    assert first["/xenoform/param/intensity"] == [[1.5]] and first["/xenoform/param/stem:Kick"] == [[0.25]]
    box["t"] += 0.1
    rl.ingest({"frames": [{}]})
    assert "/xenoform/param/intensity" not in by_address(messages(client, 1)), "only what moved"
    box["t"] += 1.0
    rl.ingest({"frames": [{}]})
    assert by_address(messages(client, 2))["/xenoform/param/intensity"] == [[1.5]], "a receiver started late has it within a second"
    assert rl.params == {"intensity": 1.5, "stem:Kick": 0.25}


def test_a_pad_is_a_pulse_not_a_level():
    rl, client, box = make_relay()
    rl.ingest({"frames": [{}], "params": {"fx:3": 1}, "triggers": ["fx:3"]})
    values = [by_address(messages(client))["/xenoform/param/fx:3"][-1][0]]
    for dt in (0.02, 0.02, 0.02, 0.02):
        box["t"] += dt
        n = len(client.sent)
        rl.ingest({"frames": [{}]})
        values.append(by_address(messages(client, n)).get("/xenoform/param/fx:3", [[None]])[-1][0])
    assert values == [1.0, 1.0, 1.0, 0.0, None], values  # high for 50 ms, one 0, then silence
    box["t"] += 2.0
    n = len(client.sent)
    rl.ingest({"frames": [{}]})
    assert "/xenoform/param/fx:3" not in by_address(messages(client, n)) or by_address(messages(client, n))["/xenoform/param/fx:3"] == [[0.0]]


def test_raw_midi_events_go_out_as_a_message_and_as_a_channel_of_their_own():
    rl, client, _ = make_relay()
    rl.ingest({"frames": [{}], "midi": [{"type": "cc", "ch": 1, "num": 74, "value": 64, "t": 1.0}, {"type": "note", "ch": 10, "num": 36, "value": 100},
                                       {"type": "clock"}, "junk"]})
    got = by_address(messages(client))
    assert got["/xenoform/midi"] == [["cc", 1, 74, 64], ["note", 10, 36, 100]]
    assert got["/xenoform/midi/cc/1/74"] == [[64]] and got["/xenoform/midi/note/10/36"] == [[100]]
    rl.ingest({"frames": [{}]})
    assert "/xenoform/midi" not in by_address(messages(client, 1)), "an event is sent once"


def test_the_settings_bundle_and_strings_change_what_is_sent():
    rl, client, _ = make_relay(strings=False, bundle=False)
    rl.ingest({"frames": [FRAME], "midi": [{"type": "cc", "ch": 1, "num": 74, "value": 64}]})
    assert all(not isinstance(p, OscBundle) for p in client.sent) and len(client.sent) > 20, "one packet a message"
    got = by_address(messages(client))
    assert "/xenoform/section" not in got and "/xenoform/scene_name" not in got and "/xenoform/midi" not in got
    assert got["/xenoform/midi/cc/1/74"] == [[64]] and got["/xenoform/bass"]


def test_a_big_update_is_split_so_no_packet_passes_an_ethernet_frame():
    rl, client, _ = make_relay()
    rl.ingest({"frames": [FRAME], "params": {f"p{i}": i / 100 for i in range(100)}})
    assert len(client.sent) > 1 and all(len(p.dgram) <= 1472 for p in client.sent)
    got = by_address(messages(client))
    assert len([a for a in got if a.startswith("/xenoform/param/")]) == 100 and got["/xenoform/bass"]


def test_a_closed_port_is_counted_and_never_raised_into_the_post():
    rl = OscRelay(client_factory=lambda h, p: FakeClient(fail=ConnectionResetError(10054, "forcibly closed")))
    rl.configure({"on": True})
    assert rl.ingest({"frames": [{"bass": 1}]})["sent"] is False
    st = rl.status()
    assert st["errors"] == 1 and "ConnectionResetError" in st["last_error"] and st["frames_in"] == 1


def test_clean_target_and_clean_frame_keep_the_address_safe():
    assert osc_relay.clean_target("fx:3") == "fx:3" and osc_relay.clean_target("stem:Kick Drum/1") == "stem:Kick_Drum_1"
    assert osc_relay.clean_target(None) == "" and osc_relay.clean_target("///") == ""
    f = osc_relay.clean_frame({"bass": float("nan"), "mid": "x", "high": True, "scene": 2.6, "section": "  drop ", "junk": 1, "stems": {"drums": 2}})
    assert f == {"high": 1.0, "scene": 3, "section": "drop", "stem/drums": 2.0}


# ---------------------------------------------------------------- the routes
def test_api_osc_reads_and_changes_the_settings():
    c = TestClient(create_app())
    st = c.get("/api/osc").json()
    assert st["on"] is False and st["host"] == "127.0.0.1" and st["port"] == 7000 and st["rate"] == 60 and st["available"] is True
    assert {"bundle", "strings", "pulse_ms", "send", "addresses", "websocket"} <= set(st)
    st = c.put("/api/osc", json={"on": True, "host": "127.0.0.1", "port": 7123, "rate": 90}).json()
    assert st["on"] is True and st["port"] == 7123 and st["rate"] == 90
    assert c.get("/api/osc").json()["port"] == 7123
    for bad, sentence in (({"port": 0}, "port"), ({"port": 70000}, "port"), ({"port": "7000"}, "port"), ({"rate": 29}, "rate"), ({"rate": 241}, "rate"),
                          ({"host": "http://x"}, "host"), ({"host": ""}, "host"), ({"on": "yes"}, "on"), ({"pulse_ms": -1}, "pulse_ms"),
                          ({"nope": 1}, "Unknown setting"), ([1], "Send an object")):
        r = c.put("/api/osc", json=bad)
        assert r.status_code == 400 and sentence in r.json()["detail"], (bad, r.json())
    assert c.get("/api/osc").json()["port"] == 7123, "a bad value changes nothing"
    assert c.put("/api/osc", content=b"nope", headers={"Content-Type": "application/json"}).status_code == 400
    assert c.put("/api/osc", json={"host": "no-such-host.invalid"}).status_code in (200, 400)
    assert c.put("/api/osc", json={"on": False}).json()["on"] is False


def test_api_osc_status_reports_the_rate_over_the_last_second_and_the_last_message():
    c = TestClient(create_app())
    listener = Listener()
    try:
        c.put("/api/osc", json={"on": True, "port": listener.port})
        st = c.get("/api/osc/status").json()
        assert st["rate_hz"] == 0 and st["last_message"] is None and st["idle_s"] is None and st["sending"] is False
        for i in range(12):
            r = c.post("/api/osc/frame", json={"frames": [{**FRAME, "frame": i}]})
            assert r.status_code == 200 and r.json()["ok"] is True
            time.sleep(0.02)
        st = c.get("/api/osc/status").json()
        assert st["on"] and st["sending"] and st["frames_in"] == 12 and st["errors"] == 0 and st["port"] == listener.port
        assert 0 < st["rate_hz"] <= 12 and st["rate_hz"] == st["in_rate_hz"], "one update per post, counted over the last second"
        assert st["last_message"]["address"].startswith("/xenoform/") and "args" in st["last_message"] and st["last_message"]["at"] > 1e9
        assert st["last_frame"]["bass"] == pytest.approx(0.6) and st["last_frame"]["frame"] == 11 and st["last_frame"]["section"] == "build"
        time.sleep(1.1)
        st = c.get("/api/osc/status").json()
        assert st["rate_hz"] == 0 and st["sending"] is False and st["idle_s"] >= 1.0, "a second of silence is reported as silence"
    finally:
        listener.close()


def test_api_osc_addresses_lists_every_address_with_its_range():
    rows = TestClient(create_app()).get("/api/osc/addresses").json()
    assert rows["prefix"] == "/xenoform" and {"address", "type", "range", "meaning", "group"} <= set(rows["channels"][0])
    assert "/xenoform/bass" in {r["address"] for r in rows["channels"]}


def test_post_frame_takes_one_frame_a_list_or_a_batch_and_says_what_is_wrong():
    c = TestClient(create_app())
    c.put("/api/osc", json={"on": True, "port": 9})
    assert c.post("/api/osc/frame", json={"bass": 1}).json()["frames"] == 1
    assert c.post("/api/osc/frame", json=[{"bass": 1}, {"bass": 2}]).json()["frames"] == 2
    assert c.post("/api/osc/frame", json={"frames": [{"bass": 1}], "params": {"intensity": 1}, "midi": [{"type": "cc", "ch": 1, "num": 1, "value": 1}]}).json()["params"] == 1
    assert c.post("/api/osc/frame", json={"frames": [{"bass": 1}] * 200}).json()["frames"] == 64, "a batch is capped"
    for body in ("x", 3, {"frames": "x"}, {"params": [1]}):
        r = c.post("/api/osc/frame", json=body)
        assert r.status_code == 400 and r.json()["detail"], body
    assert c.post("/api/osc/frame", content=b"nope", headers={"Content-Type": "application/json"}).json()["detail"] == "Send JSON."


def test_websocket_ingest_and_fan_out_like_the_midi_hub():
    c = TestClient(create_app())
    with c.websocket_connect("/ws/osc?name=vj") as a, c.websocket_connect("/ws/osc") as b:
        hello = a.receive_json()
        assert hello["type"] == "hello" and hello["rate"] == 60 and b.receive_json()["type"] == "hello"
        a.send_json({"frames": [{"bass": 0.9}], "params": {"intensity": 1.1}})
        got = b.receive_json()
        assert got["frames"] == [{"bass": 0.9}] and got["params"] == {"intensity": 1.1} and got["src"] == "vj" and got["seq"] == 1
        r = c.post("/api/osc/frame", json={"bass": 0.1}, headers={"X-Xeno-Osc-Source": "script"})
        assert r.json()["listeners"] == 2 and a.receive_json()["src"] == "script" and b.receive_json()["frames"] == [{"bass": 0.1}]
        a.send_text("not json")
        a.send_json({"bass": 0.3})
        assert b.receive_json()["frames"] == [{"bass": 0.3}]
    st = c.get("/api/osc/status").json()
    assert st["seq"] == 3 and st["listeners"] == 0 and {"vj", "script"} <= set(st["sources"])
    with c.stream("GET", "/api/osc/stream", params={"since": 1, "limit": 2}) as r:  # server-sent events, replayed from a seq
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        data = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [d["seq"] for d in data] == [2, 3]
    with c.stream("GET", "/api/osc/stream", params={"timeout": 0.05}) as r:
        assert all(not line.startswith("data:") for line in r.iter_lines())


def test_the_websocket_capability_is_reported_so_the_page_never_logs_a_failed_upgrade(monkeypatch):
    import importlib.util

    assert isinstance(osc_relay.websocket_capable(), bool)
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert osc_relay.websocket_capable() is False
    assert TestClient(create_app()).get("/api/osc").json()["websocket"] is False


# ---------------------------------------------------------------- the 30 Hz floor, measured
def _assert_rates(listener, posted, seconds, floor=30, share=0.75):
    """Nearly every post is one update: the relay never doubles one, and loses only what the rate guard merges (posts that arrive within
    half a period of each other, as a poster does when a busy machine makes it catch up) or what a starved UDP listener drops. When the
    poster really delivered 40 or more a second, that is the 30 Hz floor on every channel in each of two whole seconds. A machine too busy
    to post that fast just now (the suite shares it with other work) cannot measure the floor, and the test says so rather than failing
    on the poster's speed."""
    for address in FRAME_CHANNELS:
        got = listener.total(address)
        assert posted * share <= got <= posted + 1, f"{address}: {got} updates for {posted} posts"
    if posted / seconds < 40:
        pytest.skip(f"the poster managed only {posted / seconds:.0f} posts a second on this busy machine: too few to measure the 30 Hz floor")
    for address in FRAME_CHANNELS:
        per = listener.per_second(address)
        assert min(per) >= floor, f"{address}: {per} messages in each of the two seconds, wanted {floor} or more"


def test_a_60hz_poster_over_http_reaches_a_udp_listener_at_30hz_or_more_on_every_channel():
    c = TestClient(create_app())
    listener = Listener()
    try:
        c.put("/api/osc", json={"on": True, "port": listener.port})
        n = post_at(60, 2.0, lambda f: c.post("/api/osc/frame", json={"frames": [f]}))
        time.sleep(0.3)
        st = c.get("/api/osc/status").json()
        assert st["errors"] == 0 and st["frames_in"] == n and n > 0
        assert set(FRAME_CHANNELS) <= listener.addresses()
        print(f"http 60 Hz poster: {n} posts in 2 s, per channel per second {listener.per_second('/xenoform/bass')}")
        _assert_rates(listener, n, 2.0)
    finally:
        listener.close()


def test_a_60hz_poster_over_the_websocket_reaches_a_udp_listener_at_30hz_or_more_on_every_channel():
    c = TestClient(create_app())
    listener = Listener()
    try:
        c.put("/api/osc", json={"on": True, "port": listener.port})
        with c.websocket_connect("/ws/osc?name=vj") as ws:
            ws.receive_json()
            n = post_at(60, 2.0, lambda f: ws.send_json({"frames": [f], "params": {"intensity": f["frame"] / 100}} if f["frame"] % 6 == 0 else {"frames": [f]}))
            time.sleep(0.3)
        assert n > 0 and min(listener.per_second("/xenoform/param/intensity")) >= 1
        print(f"websocket 60 Hz poster: {n} posts in 2 s, per channel per second {listener.per_second('/xenoform/bass')}")
        _assert_rates(listener, n, 2.0)
    finally:
        listener.close()


# ---------------------------------------------------------------- the headless relay: xenoform osc relay
def test_the_relay_command_parses_its_arguments():
    p = osc_relay.build_relay_parser()
    a = p.parse_args([])
    assert (a.host, a.port, a.desk, a.rate, a.transport, a.seconds, a.takeover, a.no_bundle, a.no_strings, a.pulse_ms, a.quiet) == \
        (None, None, "http://127.0.0.1:47317", 60, "auto", None, False, False, False, 50.0, False)
    a = p.parse_args(["--host", "10.0.0.5", "--port", "7001", "--desk", "http://127.0.0.1:47330", "--rate", "120", "--transport", "sse", "--seconds", "5",
                      "--takeover", "--no-bundle", "--no-strings", "--pulse-ms", "80", "--quiet"])
    assert (a.host, a.port, a.desk, a.rate, a.transport, a.seconds, a.takeover, a.no_bundle, a.no_strings, a.pulse_ms, a.quiet) == \
        ("10.0.0.5", 7001, "http://127.0.0.1:47330", 120, "sse", 5.0, True, True, True, 80.0, True)
    with pytest.raises(SystemExit):
        p.parse_args(["--transport", "carrier-pigeon"])
    with pytest.raises(SystemExit):
        p.parse_args(["--port", "seven"])


def test_xenoform_osc_relay_reaches_the_relay_and_the_offline_osc_parser_is_untouched(monkeypatch):
    seen = []
    monkeypatch.setattr(osc_relay, "main_relay", lambda argv: seen.append(argv) or 0)
    assert main(["osc", "relay", "--host", "127.0.0.1", "--port", "7000", "--desk", "http://127.0.0.1:47317"]) == 0
    assert seen == [["--host", "127.0.0.1", "--port", "7000", "--desk", "http://127.0.0.1:47317"]]
    from xenoform.cli import build_parser

    a = build_parser().parse_args(["osc", "song.features.json", "--out", "x", "--stream", "--host", "h", "--port", "9", "--fast"])
    assert (a.cmd, a.features, a.out, a.stream, a.host, a.port, a.fast) == ("osc", "song.features.json", "x", True, "h", 9, True)
    assert main(["osc", "relay.json", "--stream"]) == 1 and seen == [["--host", "127.0.0.1", "--port", "7000", "--desk", "http://127.0.0.1:47317"]], \
        "a features file that merely starts with relay is not the relay command"


def test_xenoform_osc_relay_help_lists_its_flags_and_the_osc_help_points_to_it(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["osc", "relay", "--help"])
    out = capsys.readouterr().out
    assert exc.value.code == 0 and "xenoform osc relay" in out and all(f in out for f in ("--host", "--port", "--desk", "--rate", "--takeover", "--transport"))
    with pytest.raises(SystemExit):
        main(["osc", "--help"])
    assert "xenoform osc relay" in capsys.readouterr().out


def _no_desk(*args, **kwargs):
    raise OSError("no desk here")  # a closed port answers after two seconds on Windows: the tests that need no desk say so


def test_the_relay_rejects_a_rate_below_the_floor_and_takes_host_and_port_from_the_config(monkeypatch):
    monkeypatch.setattr(osc_relay, "_desk_call", _no_desk)
    p = osc_relay.build_relay_parser()
    nowhere = "http://127.0.0.1:9"
    with pytest.raises(ValueError, match="30 to 240"):
        osc_relay.run_relay(p.parse_args(["--rate", "10", "--desk", nowhere]), relay_obj=OscRelay(client_factory=lambda h, pt: FakeClient()),
                            batches=lambda d, t: iter(()))
    seen = {}
    rl = OscRelay(client_factory=lambda h, pt: seen.setdefault("to", (h, pt)) and FakeClient())
    osc_relay.run_relay(p.parse_args(["--seconds", "0.2", "--quiet", "--transport", "sse", "--desk", nowhere]), {"osc": {"host": "10.1.2.3", "port": 7100}},
                        relay_obj=rl, batches=lambda d, t: iter(()))
    assert seen["to"] == ("10.1.2.3", 7100)


def test_the_relay_sends_what_the_desk_publishes_from_a_stream_it_reads(monkeypatch):
    monkeypatch.setattr(osc_relay, "_desk_call", _no_desk)
    rl, client, box = make_relay()
    batches = [{"frames": [FRAME], "params": {"intensity": 1.0}, "triggers": [], "midi": [], "seq": 1, "src": "vj"},
               {"frames": [{**FRAME, "bass": 0.1}], "seq": 2, "src": "vj"}]
    out = []
    args = osc_relay.build_relay_parser().parse_args(["--seconds", "5", "--quiet", "--transport", "sse", "--desk", "http://127.0.0.1:9"])
    box_t = iter(range(10**6))
    rl.clock = lambda: next(box_t) * 0.02  # one update every 20 ms of the fake clock
    res = osc_relay.run_relay(args, relay_obj=rl, out=out.append, batches=lambda desk, tr: iter(batches))
    assert res["frames"] == 2 and res["errors"] == 0
    got = by_address(messages(client))
    assert got["/xenoform/bass"] == [[pytest.approx(0.6)], [pytest.approx(0.1)]] and got["/xenoform/param/intensity"] == [[1.0]]


class RealDesk:
    """The desk on a free port in a thread (uvicorn), for the tests that need real sockets end to end."""

    def __init__(self):
        import uvicorn

        self.config = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="error", timeout_graceful_shutdown=2)
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.time() + 20
        while not self.server.started and time.time() < deadline:
            time.sleep(0.05)
        assert self.server.started, "the desk did not start"
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"

    def call(self, method, path, body=None):
        import urllib.request

        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(), method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode() or "{}")

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.mark.parametrize("transport", ["sse", "ws"])
def test_the_headless_relay_reads_a_real_desk_and_sends_osc_at_30hz_or_more(transport):
    if transport == "ws":
        pytest.importorskip("websockets")
    desk, listener = RealDesk(), Listener()
    try:
        desk.call("PUT", "/api/osc", {"on": True, "send": False})  # the desk does not send: the relay does
        args = osc_relay.build_relay_parser().parse_args(["--desk", desk.url, "--port", str(listener.port), "--transport", transport, "--seconds", "5.6", "--quiet"])
        result = {}
        t = threading.Thread(target=lambda: result.update(osc_relay.run_relay(args)), daemon=True)
        t.start()
        time.sleep(1.2)  # the subscription is up
        n = post_at(60, 3.2, lambda f: desk.call("POST", "/api/osc/frame", {"frames": [f]}))  # two whole seconds even if the subscription was a second late
        t.join(timeout=15)
        desk.call("POST", "/api/osc/frame", {"frames": [FRAME]})  # wakes the reader thread, which then lets go of the stream
        time.sleep(0.3)
        assert not t.is_alive() and result["frames"] > 0 and result["errors"] == 0
        assert desk.call("GET", "/api/osc/status")["messages"] == 0, "the desk did not send: the relay did"
        print(f"headless relay over {transport}: {n} posts, per channel per second {listener.per_second('/xenoform/bass')}")
        _assert_rates(listener, n, 3.2, share=0.75)
    finally:
        desk.close()
        listener.close()
