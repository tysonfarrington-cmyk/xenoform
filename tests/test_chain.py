"""The chain, chosen before Make (26 Oct 2026): ``morph_pass.pick_stills`` honours a slot-to-file mapping of pins
(``chain_pins`` in the make body) and fills the rest as it always did, no still twice; the record says which slots
were pinned and which morph each shot plays; ``dense.chain_preview`` is the one chain the render and the stills
animatic share; the desk previews it (``GET``/``POST /api/simple/chain``), lists a vibe's library rows and serves the
thumbnails (``/api/stills/thumb``); the front end draws the Chain row."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform import dense, morph_pass as mp, stills as S

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/xenoform/ui_static/app.js").read_text(encoding="utf-8")
DEMO = ROOT / "examples" / "demo.wav"


def _mock_pool(monkeypatch, n_objects=12, n_scenes=4, vibe="cosmic"):
    objects = [{"file": f"{vibe}/{i:02d}_thing{i}.jpg", "noun": f"thing{i}"} for i in range(n_objects)]
    scenes = [{"file": f"{vibe}/{100 + i:03d}_scene{i}.jpg", "noun": f"scene {i}", "kind": "scene"} for i in range(n_scenes)]
    monkeypatch.setattr(mp, "manifest", lambda: {vibe: objects})
    monkeypatch.setattr(S, "grown", lambda: {vibe: scenes} if n_scenes else {})
    monkeypatch.setattr(S, "usage", lambda: {})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    return objects, scenes


# ---------------------------------------------------------------------------------------------- the pins


def test_pins_of_reads_a_dict_or_a_list_and_drops_the_malformed():
    assert mp.pins_of({}) == {} and mp.pins_of(None) == {} and mp.pins_of({"chain_pins": "x"}) == {}
    assert mp.pins_of({"chain_pins": {"2": "cosmic/a.jpg", "x": "b", "3": "", -1: "c", 4: None}}) == {2: "cosmic/a.jpg"}
    assert mp.pins_of({"chain_pins": [None, "", "cosmic\\b.jpg", {"file": "cosmic/c.jpg"}, 7]}) == {2: "cosmic/b.jpg", 3: "cosmic/c.jpg"}


def test_a_pin_holds_its_slot_and_the_rest_are_picked_as_before(monkeypatch):
    objects, _ = _mock_pool(monkeypatch)
    state = {"vibe": "cosmic"}
    _, plain = mp.pick_stills(state, 6, record=False)
    pin = objects[9]["file"]
    _, picked = mp.pick_stills({**state, "chain_pins": {"2": pin}}, 6, record=False)
    assert picked[2]["file"] == pin and picked[2]["pinned"] is True
    assert not any(p.get("pinned") for i, p in enumerate(picked) if i != 2)
    assert len({p["file"] for p in picked}) == 6
    # the other slots keep the order the plain pick gave them, the pinned still taken out of the pool
    plain_files = [p["file"] for p in plain]
    assert [p["file"] for i, p in enumerate(picked) if i != 2] == [f for f in plain_files if f != pin][:5]
    # the ``pins`` argument is the same as the body key, and wins over it
    _, again = mp.pick_stills({**state, "chain_pins": {"0": objects[4]["file"]}}, 6, record=False, pins={2: pin})
    assert [p["file"] for p in again] == [p["file"] for p in picked]
    assert all("path" in p for p in picked)


def test_a_pin_on_a_still_the_plain_pick_had_elsewhere_moves_it_and_never_doubles_it(monkeypatch):
    objects, _ = _mock_pool(monkeypatch)
    _, picked = mp.pick_stills({"vibe": "cosmic", "chain_pins": {"0": objects[3]["file"]}}, 5, record=False)
    files = [p["file"] for p in picked]
    assert files[0] == objects[3]["file"] and files.count(objects[3]["file"]) == 1 and len(set(files)) == 5


def test_pins_past_the_chain_unknown_files_and_doubles_are_dropped(monkeypatch):
    objects, _ = _mock_pool(monkeypatch)
    pins = {"9": objects[1]["file"], "1": "cosmic/nope.jpg", "2": objects[5]["file"], "3": objects[5]["file"]}
    _, picked = mp.pick_stills({"vibe": "cosmic", "chain_pins": pins}, 5, record=False)
    assert picked[2]["file"] == objects[5]["file"] and picked[2]["pinned"]
    assert not picked[1].get("pinned") and not picked[3].get("pinned") and len({p["file"] for p in picked}) == 5


def test_a_pin_on_a_still_the_folder_has_but_the_catalogue_does_not_list_holds(monkeypatch, tmp_path):
    # Tys, 30 Oct: two stills pinned over the API were on disk but not in stills.json, and the Make rendered the pool's
    # own objects instead; a file in the stills folder holds its slot, a path out of the folder never does
    objects, _ = _mock_pool(monkeypatch)
    monkeypatch.setenv("XENO_STILLS", str(tmp_path))
    (tmp_path / "none").mkdir()
    (tmp_path / "none" / "990_xf_protea_frame.jpg").write_bytes(b"\xff\xd8\xff")
    (tmp_path.parent / "outside.jpg").write_bytes(b"\xff\xd8\xff")
    pins = {"0": "none/990_xf_protea_frame.jpg", "1": "../outside.jpg"}
    _, picked = mp.pick_stills({"vibe": "cosmic", "chain_pins": pins}, 4, record=False)
    assert picked[0]["file"] == "none/990_xf_protea_frame.jpg" and picked[0]["pinned"]
    assert picked[0]["noun"] == "xf protea frame" and Path(picked[0]["path"]).is_file()
    assert not picked[1].get("pinned") and picked[1]["file"] != "../outside.jpg" and len({p["file"] for p in picked}) == 4


def test_a_pinned_scene_slot_takes_the_pin_and_the_scenes_move_on(monkeypatch):
    objects, scenes = _mock_pool(monkeypatch)
    state = {"vibe": "cosmic", "scene_stills": "mix"}
    _, picked = mp.pick_stills({**state, "chain_pins": {"0": objects[2]["file"]}}, 9, record=False, scene_at=[0, 3, 6])
    kinds = [S.kind_of(p) for p in picked]
    assert picked[0]["file"] == objects[2]["file"] and kinds[0] == "object"
    assert kinds[3] == "scene" and kinds[6] == "scene" and kinds.count("scene") == 2 and len({p["file"] for p in picked}) == 9
    # a scene pinned onto an object slot: the slot holds the scene, the scene slots keep theirs, the scene is not drawn twice
    _, picked = mp.pick_stills({**state, "chain_pins": {"1": scenes[3]["file"]}}, 9, record=False, scene_at=[0, 3, 6])
    assert picked[1]["file"] == scenes[3]["file"] and len({p["file"] for p in picked}) == 9
    assert [S.kind_of(p) for p in picked][:4] == ["scene", "scene", "object", "scene"]
    # the every-fourth default is laid on the whole chain before the pins take their slots
    _, picked = mp.pick_stills({**state, "chain_pins": {"4": objects[6]["file"]}}, 9, record=False)
    assert [i for i, p in enumerate(picked) if S.kind_of(p) == "scene"] == [0, 8] and picked[4]["file"] == objects[6]["file"]


def test_pins_that_take_the_whole_pool_still_make_a_chain(monkeypatch):
    objects, _ = _mock_pool(monkeypatch, n_objects=3, n_scenes=0)
    pins = {str(i): objects[i]["file"] for i in range(3)}
    _, picked = mp.pick_stills({"vibe": "cosmic", "chain_pins": pins}, 5, record=False)
    assert len(picked) == 5 and [p["file"] for p in picked[:3]] == [o["file"] for o in objects]


def test_pins_count_as_used_when_the_render_records(monkeypatch):
    objects, _ = _mock_pool(monkeypatch)
    marked = []
    monkeypatch.setattr(S, "mark_used", lambda vibe, files: marked.append((vibe, list(files))))
    mp.pick_stills({"vibe": "cosmic", "chain_pins": {"1": objects[7]["file"]}}, 3, record=True)
    assert marked == [("cosmic", [p for p in marked[0][1]])] and objects[7]["file"] in marked[0][1]


def test_the_curated_black_chain_keeps_its_pins(monkeypatch):
    import xenoform.cloud_morph as cm

    seen = {}
    monkeypatch.setattr(mp, "pick_stills", lambda state, count, record=True, scene_at=None, pins=None: (seen.update(state), ("black", []))[1])
    cm.chain_stills({"vibe": "black", "idea": "a rose", "chain_pins": {"1": "black/01.jpg"}}, 3)
    assert seen["chain_pins"] == {"1": "black/01.jpg"} and "idea" not in seen


# ---------------------------------------------------------------------------------------------- the preview and the record


def test_chain_preview_is_the_chain_the_render_picks_and_the_animatic_cuts(monkeypatch, tmp_path):
    objects, _ = _mock_pool(monkeypatch)
    directed = {"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}
    state = {"vibe": "cosmic", "energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16", "chain_pins": {"1": objects[8]["file"]}}
    pre = dense.chain_preview(directed, state, tmp_path / "song.wav")
    assert pre["stills"][1]["file"] == objects[8]["file"] and pre["stills"][1]["pinned"] and not pre["long_song"]
    assert len(pre["stills"]) == len(pre["shots"]) + 1 and pre["picks"] == pre["stills"][:len(pre["shots"])]
    _, again = mp.pick_stills(state, len(pre["stills"]), record=False)
    assert [s["file"] for s in again] == [s["file"] for s in pre["stills"]]
    # the stills animatic reads the same preview (one chain for the render and the draft)
    calls = []
    monkeypatch.setattr(dense, "chain_preview", lambda d, s, a: (calls.append(1), pre)[1])
    monkeypatch.setattr(dense.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr("xenoform.turbo.publish_file", lambda tmp, dest: None)
    info = dense.stills_animatic(directed, state, tmp_path / "song.wav", tmp_path / "draft.mp4", tmp_path / "w", size=(384, 216))
    assert calls == [1] and info["shots"] == len(pre["shots"]) and info["vibe"] == "cosmic"
    listing = (tmp_path / "w" / "animatic_stills.txt").read_text(encoding="utf-8")
    assert objects[8]["file"].split("/")[-1] in listing


def test_run_simple_records_the_pinned_slots_and_which_morph_each_shot_plays(tmp_path, monkeypatch):
    from xenoform import beatfx
    import xenoform.cloud_morph as cm

    objects, _ = _mock_pool(monkeypatch)
    pin = objects[10]["file"]

    def fake_mock(shots, stills, work, w, h):
        out = []
        for i in range(len(shots)):
            p = Path(work) / f"m{i:02d}.mp4"
            p.write_bytes(b"mp4")
            out.append(p)
        return out

    def fake_compose(clips, shots, audio, out, **kw):
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "768x432", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}}

    monkeypatch.setattr(cm, "_mock_clips", fake_mock)
    monkeypatch.setattr(beatfx, "compose", fake_compose)
    state = {"vibe": "cosmic", "aspect": "16:9", "quality_tier": "draft", "energy_preset": "dense", "chain_pins": {"2": pin}}
    info = dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, DEMO, tmp_path / "x.mp4", tmp_path, {}, state,
                            lambda *a: None, engine="mock")
    assert info["pins"] == {"2": pin} and info["pinned"] == [2] and info["stills"][2] == pin
    assert len(set(info["stills"])) == len(info["stills"]) == len(info["shots"]) + 1
    assert [s["morph"] for s in info["shots"]] == list(range(len(info["shots"])))
    assert info["prep"] == {"background": None, "native_draft": False, "native": False, "draft_size": None} and info["swaps"] == []
    assert info["recut_state"]["chain_pins"] == {"2": pin}
    rec = json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert rec["pinned"] == [2] and rec["pins"] == {"2": pin} and [s["morph"] for s in rec["plan_shots"]] == [s["morph"] for s in info["shots"]]
    # a performer slot plays its own clip: no morph index on the merged shot
    shots = [{"start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24, "effects": [], "morph": i} for i in range(4)]
    merged, _ = dense.apply_performer_slots(shots, ["c0", "c1", "c2", "c3"], [{"first": 1, "last": 2, "instrument": "drums"}],
                                            {1: {"clip": "p.mp4"}})
    assert [s.get("morph") for s in merged] == [0, None, 3]


# ---------------------------------------------------------------------------------------------- the desk


def test_the_desk_previews_the_chain_with_pins_and_serves_the_library_thumbnails():
    from xenoform.ui import create_app

    client = TestClient(create_app())
    got = client.get("/api/simple/chain?vibe=cosmic").json()
    assert got["count"] == got["morphs"] + 1 == got["shots"] + 1 and got["vibe"] == "cosmic" and got["pinned"] == []
    assert all(s["thumb"] == "/api/stills/thumb?file=" + s["file"] and s["file"].startswith("cosmic/") for s in got["stills"])
    pin = got["stills"][5]["file"]
    body = {"audio_id": "demo", "vibe": "cosmic", "mode": "simple", "energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16",
            "chain_pins": {"1": pin, "40": pin}}  # the desk's make body: the same keys the GET defaults
    again = client.post("/api/simple/chain", json=body).json()
    assert again["stills"][1]["file"] == pin and again["stills"][1]["pinned"] and again["pinned"] == [1]
    assert len({s["file"] for s in again["stills"]}) == again["count"] == got["count"]
    # a bare body (no energy, as a flow make) is a different, shorter chain: the preview follows the body it is given
    assert client.post("/api/simple/chain", json={"audio_id": "demo", "vibe": "cosmic"}).json()["count"] < got["count"]
    # the GET form takes the pins as a JSON object
    same = client.get("/api/simple/chain?vibe=cosmic&chain_pins=" + json.dumps({"1": pin})).json()
    assert [s["file"] for s in same["stills"]] == [s["file"] for s in again["stills"]]
    assert client.get("/api/simple/chain?vibe=cosmic&chain_pins=notjson").status_code == 400
    assert client.get("/api/simple/chain?audio_id=gone&vibe=cosmic").status_code == 400
    thumb = client.get(again["stills"][1]["thumb"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/jpeg" and len(thumb.content) > 1000
    assert client.get("/api/stills/thumb?file=../objects.json").status_code == 404
    assert client.get("/api/stills/thumb?file=cosmic/nope.jpg").status_code == 404
    assert client.get("/api/stills/thumb?file=C:/Windows/win.ini").status_code == 404
    rows = client.get("/api/stills?vibe=cosmic").json()["rows"]
    objects = [r for r in S.shipped()["cosmic"] if S.kind_of(r) == "object"]
    assert len(rows) == len(objects) and rows[0]["thumb"] == "/api/stills/thumb?file=" + rows[0]["file"] and all(r["kind"] == "object" for r in rows)
    assert "rows" not in client.get("/api/stills").json()


def test_a_length_cut_previews_its_window_and_the_pins_reach_the_render(monkeypatch):
    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())
    whole = client.get("/api/simple/chain?vibe=cosmic").json()
    cut = client.get("/api/simple/chain?vibe=cosmic&length_s=6").json()
    assert cut["length_s"] == 6 and 1 < cut["count"] < whole["count"]
    seen = {}
    monkeypatch.setattr(_ui, "_run_job", lambda job_id, audio_path, body, cfg, out, cancel_event=None: seen.update(body))
    r = client.post("/api/generate", json={"audio_id": "demo", "vibe": "cosmic", "mode": "simple", "chain_pins": {"1": "cosmic/02_pearl_iridescent.jpg"},
                                           "tiny": True})
    assert r.status_code == 200, r.text
    assert seen.get("chain_pins") == {"1": "cosmic/02_pearl_iridescent.jpg"}
    with _ui._LOCK:
        _ui._JOBS.clear()


# ---------------------------------------------------------------------------------------------- the front end


def test_front_end_draws_the_chain_row_and_sends_the_pins():
    assert "function chainRow(easy)" in APP and "${chainRow(easy)}" in APP
    assert 'data-act="easy-chain-slot"' in APP and 'libraryPicker(easy.vibe, "easy-pin"' in APP and 'data-act="easy-unpin"' in APP
    assert 'data-act="easy-chain-reset"' in APP and "/api/simple/chain" in APP and "async function loadChain" in APP
    payload = APP.split("function payload()")[1].split("function renderSetup")[0]
    assert "chain_pins:" in payload
    assert '"pins"' in APP.split("const EASY_SAVED_KEYS")[1].split("\n")[0]
    assert 'act === "easy-pin"' in APP and 'act === "easy-unpin"' in APP and 'act === "easy-chain-reset"' in APP
    css = (ROOT / "src/xenoform/ui_static/app.css").read_text(encoding="utf-8")
    assert ".chain-strip" in css and ".chain-slot" in css and ".lib-picker" in css
