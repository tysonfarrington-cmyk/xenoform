"""MIDI maps by device name: the per-device store (~/.xenoform/midi_map.json, XENO_HOME), its routes, the shipped
presets (configs/midi_presets) and the bridge's device names on the events."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from xenoform import midi_maps as mm
from xenoform import stems_api
from xenoform.ui import create_app

KNOB = {"source": {"type": "cc", "ch": 1, "num": 74}, "target": "macro:intensity", "mode": "abs", "min": 0, "max": 1, "label": "Knob 1"}
PAD = {"source": {"type": "note", "ch": 10, "num": 36}, "target": "pad:1", "mode": "hold", "min": 0, "max": 1}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XENO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XENO_MIDI_PRESETS", str(tmp_path / "presets"))
    return tmp_path


def test_names_and_rows():
    assert mm.bare("Minilab3 0") == "Minilab3" and mm.bare("MIDIIN2 (Minilab3) 1") == "MIDIIN2 (Minilab3)"
    assert mm.same_device("Minilab3", "Minilab3 0") and mm.same_device("Minilab3 0", "Minilab3")
    assert not mm.same_device("Minilab3", "MIDIIN2 (Minilab3)") and not mm.same_device("", "")
    with pytest.raises(ValueError):
        mm.clean_device("  \n ")
    rows = mm.clean_rows([KNOB, PAD, {"source": {"type": "sysex", "num": 1}, "target": "x"}, {"target": "no source"},
                          {"source": {"type": "cc", "ch": 99, "num": 300}, "target": "t" * 99, "mode": "weird", "max": None}, "junk"])
    assert rows[:2] == [KNOB, PAD] and len(rows) == 3
    assert rows[2] == {"source": {"type": "cc", "ch": 16, "num": 127}, "target": "t" * 64, "mode": "abs", "min": 0.0, "max": 1.0}
    with pytest.raises(ValueError):
        mm.clean_rows({"not": "a list"})
    assert mm.default_match("Minilab3") == "Minilab3" and mm.default_match("Arturia KeyLab 49 0") == r"Arturia\s*KeyLab\s*49"


def test_maps_survive_a_restart_and_merge_by_page(home):
    c = TestClient(create_app())
    assert c.get("/api/midi/maps").json()["devices"] == {}
    r = c.put("/api/midi/maps/Minilab3", json={"pages": {"desk": [KNOB]}, "profile": "minilab3", "updated": 100.0})
    assert r.status_code == 200 and r.json()["map"]["pages"] == {"desk": [KNOB]}
    # /vj saves its page without touching the desk's
    assert c.put("/api/midi/maps/Minilab3", json={"page": "vj", "rows": [PAD]}).status_code == 200
    path = home / "home" / "midi_map.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["kind"] == "xenoform-midi-maps" and on_disk["devices"]["Minilab3"]["pages"] == {"desk": [KNOB], "vj": [PAD]}
    # a new desk process (a restart) reads the same file; the bridge's name for the port finds the same map
    c2 = TestClient(create_app())
    got = c2.get("/api/midi/maps/Minilab3%200").json()
    assert got["map"]["pages"]["vj"] == [PAD] and got["map"]["profile"] == "minilab3" and got["preset"] is None
    assert c2.get("/api/midi/maps").json()["devices"]["Minilab3"]["pages"]["desk"] == [KNOB]
    # a device name with spaces, brackets and a slash round-trips through the path
    name = "MIDIIN2 (Minilab3)/port"
    assert c2.put("/api/midi/maps/" + name.replace(" ", "%20").replace("/", "%2F"), json={"page": "vj", "rows": [PAD]}).status_code == 200
    assert c2.get("/api/midi/maps/MIDIIN2%20(Minilab3)%2Fport").json()["map"]["device"] == name
    # Reset to default: one page, then the whole device
    assert c2.delete("/api/midi/maps/Minilab3", params={"page": "vj"}).json()["removed"] is True
    assert c2.get("/api/midi/maps/Minilab3").json()["map"]["pages"] == {"desk": [KNOB]}
    assert c2.delete("/api/midi/maps/Minilab3", params={"page": "vj"}).json()["removed"] is False
    assert c2.delete("/api/midi/maps/Minilab3").json()["removed"] is True and c2.get("/api/midi/maps/Minilab3").json()["map"] is None
    # what the routes refuse
    assert c2.put("/api/midi/maps/Minilab3", json={"nothing": 1}).status_code == 400
    assert c2.put("/api/midi/maps/Minilab3", json={"pages": {"../etc": [KNOB]}}).status_code == 400
    assert c2.put("/api/midi/maps/Minilab3", json={"pages": {"vj": "nope"}}).status_code == 400
    assert c2.delete("/api/midi/maps/Minilab3", params={"page": "Bad Page"}).status_code == 400


def test_an_unreadable_maps_file_is_kept_aside_not_overwritten(home):
    path = mm.maps_path()
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    assert mm.load_maps()["devices"] == {} and mm.load_maps()["unreadable"] is True
    mm.put_map("Minilab3", {"page": "desk", "rows": [KNOB]})
    kept = list(path.parent.glob("midi_map.unreadable-*.json"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == "{ not json"
    assert mm.get_map("Minilab3")["pages"]["desk"] == [KNOB]


def test_the_oldest_devices_go_past_the_cap(home, monkeypatch):
    monkeypatch.setattr(mm, "MAX_DEVICES", 3)
    for i in range(5):
        mm.put_map(f"Pad {i}", {"page": "vj", "rows": [PAD], "updated": 100.0 + i})
    assert sorted(mm.load_maps()["devices"]) == ["Pad 2", "Pad 3", "Pad 4"]


def test_presets_load_match_and_ship(home):
    folder = home / "presets"
    folder.mkdir()
    (folder / "README.md").write_text("not a preset", encoding="utf-8")
    (folder / "broken.json").write_text("{", encoding="utf-8")
    (folder / "empty.json").write_text(json.dumps({"device": "X", "pages": {"vj": []}}), encoding="utf-8")
    (folder / "badregex.json").write_text(json.dumps({"device": "Launchpad", "match": "(", "pages": {"vj": [PAD]}}), encoding="utf-8")
    (folder / "keylab.json").write_text(json.dumps({"device": "KeyLab 49", "match": r"key\s*lab", "label": "KeyLab",
                                                    "profile": "generic", "pages": {"vj": [PAD], "desk": [KNOB]}}), encoding="utf-8")
    got = mm.load_presets()
    assert [p["id"] for p in got] == ["badregex", "keylab"]  # broken JSON, the README and an empty map are skipped
    assert got[0]["match"] == "" and got[1]["pages"]["desk"] == [KNOB]
    assert mm.preset_for("Arturia KeyLab 49 MIDI")["id"] == "keylab" and mm.preset_for("Launchpad 0")["id"] == "badregex"
    assert mm.preset_for("Minilab3") is None
    c = TestClient(create_app())
    listed = c.get("/api/midi/presets").json()
    assert listed["dir"] == str(folder) and [p["id"] for p in listed["presets"]] == ["badregex", "keylab"]
    assert c.get("/api/midi/maps/Arturia%20KeyLab%2049").json()["preset"]["label"] == "KeyLab"
    # "Save as the shipped preset": both pages, the port it saw, a match that finds the controller on any backend
    r = c.post("/api/midi/presets", json={"device": "Minilab3 0", "port": "Minilab3 0", "label": "Tys's MiniLab 3", "profile": "minilab3",
                                          "match": r"mini\s*lab\s*3", "pages": {"vj": [PAD], "desk": [KNOB]}})
    assert r.status_code == 200 and r.json()["id"] == "minilab3"
    shipped = json.loads((folder / "minilab3.json").read_text(encoding="utf-8"))
    assert shipped["kind"] == "xenoform-midi-preset" and shipped["device"] == "Minilab3" and shipped["port"] == "Minilab3 0"
    assert shipped["pages"] == {"vj": [PAD], "desk": [KNOB]} and shipped["saved"]
    assert mm.preset_for("Minilab3")["label"] == "Tys's MiniLab 3" and mm.preset_for("MIDIIN2 (Minilab3)")["id"] == "minilab3"
    assert c.post("/api/midi/presets", json={"device": "Minilab3", "pages": {"vj": []}}).status_code == 400
    assert c.post("/api/midi/presets", json={"device": "Minilab3", "match": "(", "pages": {"vj": [PAD]}}).status_code == 400
    assert c.post("/api/midi/presets", json={"pages": {"vj": [PAD]}}).status_code == 400
    # the default match: the name without its port number
    c.post("/api/midi/presets", json={"device": "nanoKONTROL2 1", "pages": {"desk": [KNOB]}})
    assert json.loads((folder / "nanokontrol2.json").read_text(encoding="utf-8"))["match"] == "nanoKONTROL2"


def test_the_shipped_presets_folder_has_its_readme():
    folder = Path(mm.ROOT) / "configs" / "midi_presets"
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "Save as the shipped preset" in readme and "Minilab3" in readme
    for path in folder.glob("*.json"):  # whatever ships must load
        assert path.stem in {p["id"] for p in mm.load_presets()}, path.name


def test_bridge_events_carry_their_device(home):
    stems_api.hub.__init__()
    c = TestClient(create_app())
    with c.websocket_connect("/ws/midi?name=vj") as ws:
        assert ws.receive_json()["type"] == "hello"
        c.post("/api/midi/event", json={"events": [{"type": "note", "ch": 10, "num": 36, "value": 100}]},
               headers={"X-Xeno-Midi-Source": "bridge", "X-Xeno-Midi-Device": "Minilab3 0"})
        ev = ws.receive_json()
        assert ev["dev"] == "Minilab3 0" and ev["num"] == 36 and ev["src"] == "bridge"
        c.post("/api/midi/event", json={"events": [{"type": "note", "ch": 10, "num": 36, "value": 0}]})
        assert "dev" not in ws.receive_json()  # a script that names no device
