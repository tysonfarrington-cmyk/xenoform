"""The stills library, xenoform.stills (25 Oct 2026): shipped and grown stills are one pool, the chain prefers what the last cut
left alone and puts the user's own shapes first, subjects follow the vibe's families, prompts follow the pool,
every candidate passes the checks against its pool, a grow runs through a client, and the desk exposes it."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from xenoform import stills as L
from xenoform import morph_pass as mp

W, H = 512, 288


def _still(path: Path, *, cx=0.5, cy=0.5, r=0.18, back=(8, 8, 10), fill=(170, 175, 180), blur=0.0, noise=3):
    """A synthetic object still: a disc on a plain backdrop, a little noise so sharpness is not zero."""
    im = Image.new("RGB", (W, H), back)
    d = ImageDraw.Draw(im)
    rr = r * H
    d.ellipse((cx * W - rr, cy * H - rr, cx * W + rr, cy * H + rr), fill=fill)
    d.ellipse((cx * W - rr * 0.4, cy * H - rr * 0.5, cx * W + rr * 0.1, cy * H - rr * 0.1), fill=(230, 230, 235))
    a = np.asarray(im).astype(np.int16)
    rng = np.random.default_rng(int(cx * 1000 + cy * 100 + r * 10))
    a = np.clip(a + rng.integers(-noise, noise + 1, a.shape), 0, 255).astype(np.uint8)
    im = Image.fromarray(a)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def _pool(folder: Path, n: int = 6) -> list[Path]:
    return [_still(folder / f"p{i}.png", cx=0.35 + 0.06 * i, cy=0.45 + 0.02 * i, r=0.2 + 0.012 * i) for i in range(n)]


def _grown(vibe: str, name: str, noun: str, **row) -> Path:
    """A grown still on disk and in stills.json (the conftest points XENO_STILLS at a temp dir)."""
    path = _still(L.root() / vibe / name)
    idx = L._read_json(L.index_path(), {})
    idx.setdefault(vibe, []).append({"file": f"{vibe}/{name}", "noun": noun, **row})
    L._write_json(L.index_path(), idx)
    return path


# ---------------------------------------------------------------------------------------------- catalogue


def test_catalogue_merges_shipped_and_grown_and_drops_deleted_files():
    assert L.counts("cosmic") == {"shipped": 12, "grown": 0, "own": 0, "total": 12}
    _grown("cosmic", "000_astrolabe.jpg", "astrolabe")
    _grown("cosmic", "001_gone.jpg", "gone")
    (L.root() / "cosmic" / "001_gone.jpg").unlink()  # deleting the jpg is the cull
    rows = L.catalogue()["cosmic"]
    assert len(rows) == 13 and rows[0]["shipped"] and not rows[-1]["shipped"]
    assert rows[-1]["noun"] == "astrolabe" and Path(rows[-1]["path"]).is_file()
    assert L.counts("cosmic")["grown"] == 1 and "astrolabe" in L.nouns_in("cosmic")
    assert "cosmic" in mp.catalogue() and len(mp.catalogue()["cosmic"]) == 13
    _grown("brand-new", "000_thing.jpg", "thing")
    assert mp.vibe_for({"vibe": "brand-new"}) == "liquid-gold"  # one grown still is not a pool yet: the fallback carries it
    _grown("brand-new", "001_other.jpg", "other")
    _grown("brand-new", "002_third.jpg", "third")
    assert mp.vibe_for({"vibe": "brand-new"}) == "brand-new"  # three grown stills alone make a pool


def test_order_fresh_puts_own_shapes_first_then_the_least_used():
    rows = [{"file": "a"}, {"file": "b"}, {"file": "c"}, {"file": "d", "own": True}]
    L.mark_used("v", ["a", "b"])
    L.mark_used("v", ["a"])
    assert [r["file"] for r in L.order_fresh("v", rows)] == ["d", "c", "b", "a"]
    assert L.usage()["_tick"] == 2


def test_pick_stills_prefers_what_the_last_cut_left_alone_and_own_shapes_lead():
    _, first = mp.pick_stills({"vibe": "cosmic"}, 5)
    _, second = mp.pick_stills({"vibe": "cosmic"}, 5)
    assert not {s["file"] for s in first} & {s["file"] for s in second}  # twelve stills: the second cut takes fresh ones
    _, third = mp.pick_stills({"vibe": "cosmic"}, 5, record=False)
    files = {s["file"] for s in third}
    assert not files & {s["file"] for s in second} and len(files & {s["file"] for s in first}) == 3  # the 2 never used, then the 3 used longest ago
    _grown("cosmic", "000_astrolabe.jpg", "astrolabe", own=True)
    _, own = mp.pick_stills({"vibe": "cosmic"}, 4, record=False)
    assert own[0]["noun"] == "astrolabe" and own[0].get("own") and Path(own[0]["path"]).is_file()


# ---------------------------------------------------------------------------------------------- subjects


def test_nouns_follow_the_vibe_families_and_skip_the_banned_and_the_owned():
    data = L.subjects()
    assert len(data["families"]) >= 18 and sum(len(f["nouns"]) for f in data["families"].values()) >= 320
    allowed = set()
    entry = data["vibes"]["botanical"]
    for fam in entry["weights"]:
        allowed |= set(data["families"][fam]["nouns"])
    picks = L.nouns_for("botanical", 30, have=L.nouns_in("botanical"), seed=3)
    assert len(picks) == 30 and len(set(picks)) == 30
    assert set(picks) <= allowed and not set(picks) & L.nouns_in("botanical")
    for vibe in data["vibes"]:
        for noun in L.nouns_for(vibe, 400, have=set()):
            assert not any(b in noun for b in L.BANNED), (vibe, noun)
    assert L.nouns_for("botanical", 10, seed=5) == L.nouns_for("botanical", 10, seed=5)
    assert L.nouns_for("botanical", 10, seed=5) != L.nouns_for("botanical", 10, seed=6)
    assert L.nouns_for("no-such-vibe", 5)  # the defaults carry a vibe without an entry


def test_own_shapes_are_cleaned_distinct_and_capped():
    assert L.own_nouns("A brass Astrolabe, the wolf skull;  , a brass astrolabe\nOne single Lantern!") == ["brass astrolabe", "wolf skull", "lantern"]
    assert L.own_nouns(["x"] * 3 + [f"shape {i}" for i in range(20)]) == ["x"] + [f"shape {i}" for i in range(L.MAX_OWN - 1)]
    assert L.clean_noun("  ") == "" and L.slug("brass astrolabe!") == "brass_astrolabe"


def test_prompts_follow_the_pool_and_fall_back_to_the_vibe_style():
    cosmic = L.prompt_for("cosmic", "astrolabe")
    assert "One single astrolabe made of iridescent dichroic glass" in cosmic and "pure black void" in cosmic
    chrome = L.prompt_for("chrome-mercury", "astrolabe")
    assert chrome.endswith("One single astrolabe made of liquid mirror chrome.") and "softbox" not in chrome.lower()
    assert "A sumi-e ink wash painting of one single koi." in L.prompt_for("ink-wash", "koi")
    assert L.prompt_for("ferrofluid", "astrolabe").endswith("One single astrolabe made of oily black magnetic fluid.")
    plain = L.prompt_for("no-such-vibe", "thing")
    assert plain.endswith("One single thing.") and "no text" in plain
    assert len(L.prompts()) >= 29 and all("{noun}" in row["subject"] for row in L.prompts().values())


# ---------------------------------------------------------------------------------------------- the checks


def test_checks_against_the_pool(tmp_path):
    pool = _pool(tmp_path / "pool")
    prof = L.profile(pool)
    assert prof["n"] == 6 and prof["edges"] == 0 and 0.05 < prof["area"][0] < prof["area"][1] < 0.3
    good = _still(tmp_path / "good.png", cx=0.55, cy=0.5, r=0.22)
    assert L.check(good, prof)["ok"]
    grey = _still(tmp_path / "grey.png", r=0.22, back=(120, 120, 124))
    assert "backdrop" in L.check(grey, prof)["why"]
    huge = _still(tmp_path / "huge.png", r=0.75)
    assert set(L.check(huge, prof)["why"]) >= {"cropped"}
    tiny = _still(tmp_path / "tiny.png", r=0.03)
    assert "size" in L.check(tiny, prof)["why"]  # a speck is also softer than the pool
    soft = _still(tmp_path / "soft.png", cx=0.5, cy=0.5, r=0.22, blur=6.0, noise=0)
    assert "soft" in L.check(soft, prof)["why"]
    same = L.check(pool[2], prof)
    assert same["why"] == ["duplicate"] and same["dup"] > L.DUPLICATE_NCC
    assert L.check(good, prof, extra_greys=[L.features(good)["grey"]])["why"] == ["duplicate"]
    empty = L.profile([])
    assert L.check(good, empty)["ok"] and L.check(grey, empty)["ok"]  # no pool: fixed bounds, no backdrop to hold to


def test_a_graded_gradient_backdrop_is_backdrop_not_subject(tmp_path):
    """cosmic's stills sit on a radial blue gradient; a centred object on it must not read as touching every edge."""
    pool = _pool(tmp_path / "pool")
    prof = L.profile(pool)
    plain = _still(tmp_path / "plain.png", cx=0.5, cy=0.5, r=0.22)
    im = Image.open(plain)
    graded = L.grade(im, "cosmic")
    graded.save(tmp_path / "graded.png")
    f = L.features(tmp_path / "graded.png")
    assert f["edges"] == 0 and f["residual"] < L.RESIDUAL_FLOOR and 0.05 < f["area"] < 0.3
    bars = Image.open(plain).convert("RGB")
    bars.paste((160, 160, 160), (0, 0, int(W * 0.08), H))  # a studio bar down one side: structure the fit cannot describe
    bars.save(tmp_path / "bars.png")
    assert "backdrop" in L.check(tmp_path / "bars.png", prof)["why"]
    scene = dict(prof, edges=3)  # a scene-like pool: the cropped check stands aside
    huge = _still(tmp_path / "huge.png", r=0.75)
    assert "cropped" not in L.check(huge, scene)["why"] and "cropped" in L.check(huge, prof)["why"]


def test_grade_touches_only_the_original_five():
    im = Image.fromarray(np.full((72, 128, 3), (20, 120, 110), dtype=np.uint8))
    assert np.asarray(L.grade(im, "chrome-mercury")).tolist() == np.asarray(im).tolist()
    out = np.asarray(L.grade(im, "cosmic")).astype(int)
    assert out.shape == (72, 128, 3) and out[..., 2].mean() > out[..., 1].mean()  # the teal is nudged to blue


# ---------------------------------------------------------------------------------------------- ingest and grow


def test_import_folder_keeps_checks_numbers_and_sets_rejects_aside(tmp_path):
    folder = tmp_path / "batch"
    _still(folder / "00_astrolabe.png", cx=0.5, cy=0.5, r=0.16)
    _still(folder / "01_tiny_thing.png", r=0.02)
    _still(folder / "02_vinyl_record.png", cx=0.4, cy=0.5, r=0.15)  # a banned prop: skipped, never rendered into the pool
    res = L.import_folder("synthetic", folder)
    assert res["kept"] == 1 and res["rejected"] == {"size": 1} and res["skipped"] == 1
    assert res["files"] == ["synthetic/000_astrolabe.jpg"] and (L.root() / "synthetic" / "000_astrolabe.jpg").is_file()
    rej = list((L.root() / "synthetic" / "rejected").glob("*_tiny_thing_size.jpg"))
    assert len(rej) == 1
    rows = L.grown()["synthetic"]
    assert rows[0]["noun"] == "astrolabe" and rows[0]["qa"]["edges"] == 0 and "imported from batch" in rows[0]["source"]
    again = L.import_folder("synthetic", folder)
    assert again["kept"] == 0 and again["skipped"] == 2  # already in the pool, and the banned one
    assert L.summary_line(res) == "Kept 1 of 3 · rejected 1 (size 1)"


class _FakeClient:
    """comfy-sdk's surface as grow uses it: workflows.from_file, submit, job.result().get_outputs()."""

    def __init__(self):
        self.prompts = []
        self.seeds = []

    class _WF:
        def __init__(self, outer):
            self.outer, self.inputs = outer, {}

        def set_input(self, node, key, value):
            self.inputs[(node, key)] = value

    class _Out:
        def __init__(self, k):
            self.k = k

        def to_file(self, path):
            _still(Path(path), cx=0.3 + 0.07 * self.k, cy=0.5, r=0.15 + 0.01 * self.k)

    class _Job:
        def __init__(self, k):
            self.k = k

        def result(self):
            job = self

            class R:
                outputs = []

                def get_outputs(self, node):
                    assert node == L.N_SAVE
                    return [_FakeClient._Out(job.k)]

            return R()

    @property
    def workflows(self):
        outer = self

        class WFs:
            def from_file(self, path):
                assert Path(path).name == "zimage_t2i_api.json"
                return _FakeClient._WF(outer)

        return WFs()

    def submit(self, wf):
        self.prompts.append(wf.inputs[(L.N_TEXT, "text")])
        self.seeds.append(wf.inputs[(L.N_SEED, "seed")])
        return _FakeClient._Job(len(self.prompts) - 1)


def test_grow_renders_checks_and_lists(tmp_path):
    fake = _FakeClient()
    ticks = []
    res = L.grow("synthetic", 3, client=fake, seed=11, progress=lambda d, t, k: ticks.append((d, t, k)), sheet=True)
    assert res["asked"] == 3 and res["made"] == 3 and res["kept"] == 3 and res["rejected"] == {}
    assert fake.seeds == [11, 12, 13] and all(p.startswith("Studio macro photograph") or "One single" in p for p in fake.prompts)
    assert ticks == [(1, 3, 1), (2, 3, 2), (3, 3, 3)] and Path(res["sheet"]).is_file()
    rows = L.grown()["synthetic"]
    assert [r["noun"] for r in rows] == res["nouns"] and rows[0]["seed"] == 11 and not rows[0].get("own")
    assert not (L.root() / "synthetic" / "_incoming").exists()
    own = L.grow("synthetic", nouns=["a brass astrolabe"], own=True, client=fake, seed=50, sheet=False)
    assert own["kept"] == 1 and L.grown()["synthetic"][-1]["own"] is True
    assert fake.prompts[-1].endswith("One single brass astrolabe.")
    _, picked = mp.pick_stills({"vibe": "synthetic"}, 3, record=False)
    assert picked[0]["noun"] == "brass astrolabe"
    assert L.grow("synthetic", nouns=[], own=True, client=fake)["note"].startswith("type a shape")
    assert L.plan("cosmic", 5, seed=1)["seconds"] == L.estimate_seconds(5) and len(L.plan("cosmic", 5)["prompts"]) == 5


def test_grow_stops_on_cancel_and_survives_a_failed_render(tmp_path):
    fake = _FakeClient()
    res = L.grow("synthetic", 4, client=fake, seed=1, cancel=lambda: True, sheet=False)
    assert res["made"] == 0 and res["note"] == "stopped"

    class Broken(_FakeClient):
        def submit(self, wf):
            job = super().submit(wf)
            if job.k == 1:
                class Bad:
                    def result(self):
                        raise RuntimeError("boom")
                return Bad()
            return job

    res = L.grow("synthetic", 3, client=Broken(), seed=1, sheet=False)
    assert res["made"] == 2 and res["kept"] == 2 and res["rejected"] == {"render": 1}


def test_available_reads_the_model_lists():
    full = {"diffusion_models": [L.UNET], "text_encoders": [L.TEXT_ENCODER], "vae": [L.VAE], "loras": []}
    assert L.available(fetch=lambda cfg: full) == {"ok": True, "missing": [], "note": "Z-Image Turbo is installed."}
    part = {**full, "vae": []}
    assert L.available(fetch=lambda cfg: part)["missing"] == [L.VAE]
    assert L.available(fetch=lambda cfg: None)["ok"] is False


# ---------------------------------------------------------------------------------------------- the desk


def test_desk_routes_count_grow_and_stop(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())
    got = client.get("/api/stills?vibe=cosmic").json()
    assert got["counts"]["cosmic"]["shipped"] == 12 and got["have"]["total"] == 12 and got["subjects_left"] > 100
    assert got["job"] == {} and got["default_grow"] == L.DEFAULT_GROW
    monkeypatch.setattr(L, "available", lambda cfg=None, **kw: {"ok": False, "note": "ComfyUI is not answering"})
    assert client.post("/api/stills/grow", json={"vibe": "cosmic"}).status_code == 503
    assert client.post("/api/stills/grow", json={"vibe": ""}).status_code == 400
    assert client.post("/api/stills/grow", json={"vibe": "cosmic", "own": True, "nouns": " , "}).status_code == 400
    monkeypatch.setattr(L, "available", lambda cfg=None, **kw: {"ok": True, "note": ""})
    calls = {}

    def fake_grow(vibe, count=36, *, nouns=None, own=False, cfg=None, seed=None, progress=None, cancel=None, client=None, sheet=True):
        calls.update({"vibe": vibe, "count": count, "nouns": nouns, "own": own})
        progress(1, 2, 1)
        progress(2, 2, 2)
        return {"vibe": vibe, "asked": 2, "made": 2, "kept": 2, "rejected": {}, "files": [], "seconds": 1.5, "nouns": nouns or ["a", "b"]}

    monkeypatch.setattr(L, "grow", fake_grow)
    started = client.post("/api/stills/grow", json={"vibe": "cosmic", "own": True, "nouns": "a brass astrolabe, wolf skull"}).json()
    assert started["ok"] and started["nouns"] == ["brass astrolabe", "wolf skull"]
    import time as _t

    for _ in range(50):
        job = client.get("/api/stills").json()["job"]
        if job.get("status") == "done":
            break
        _t.sleep(0.05)
    assert job["status"] == "done" and job["kept"] == 2 and job["note"] == "Kept 2 of 2" and "result" not in job
    assert calls == {"vibe": "cosmic", "count": 36, "nouns": ["brass astrolabe", "wolf skull"], "own": True}
    with _ui._LOCK:
        _ui._STILLS_JOB.update({"status": "running"})
    assert client.post("/api/stills/grow", json={"vibe": "cosmic"}).status_code == 409
    assert client.post("/api/stills/stop").json() == {"ok": True, "stopping": True}
    with _ui._LOCK:
        assert _ui._STILLS_JOB["cancel"] is True
        _ui._STILLS_JOB.clear()


def test_the_animatic_previews_the_renders_picks_without_a_tick():
    from xenoform import cloud_morph

    state = {"vibe": "cosmic", "cut_plan": None}
    _, a = cloud_morph.stills_for(state, 6, record=False)
    _, b = cloud_morph.stills_for(state, 6, record=False)
    assert [s["file"] for s in a] == [s["file"] for s in b] and L.usage() == {}  # the preview reads, never ticks
    _, c = cloud_morph.stills_for(state, 6)
    assert [s["file"] for s in c] == [s["file"] for s in a] and L.usage()["_tick"] == 1  # the render makes the same picks, once
    assert "_vibe" not in c[0]


def test_a_grown_only_vibe_borrows_until_it_has_three_and_leads_with_its_own():
    _grown("hologram", "000_astrolabe.jpg", "astrolabe", own=True)
    assert mp.vibe_for({"vibe": "hologram"}) == "liquid-gold"  # one still is not a pool: keep borrowing the fallback
    _, picked = mp.pick_stills({"vibe": "hologram"}, 5, record=False)
    assert picked[0]["noun"] == "astrolabe" and len({s["file"] for s in picked}) == 5
    assert all(Path(s["path"]).parent.name == "liquid-gold" for s in picked[1:])
    _grown("hologram", "001_fox.jpg", "fox")
    _grown("hologram", "002_lantern.jpg", "lantern")
    assert mp.vibe_for({"vibe": "hologram"}) == "hologram"
    mp.pick_stills({"vibe": "hologram"}, 3)
    assert set(L.usage()["hologram"]) == {"hologram/000_astrolabe.jpg", "hologram/001_fox.jpg", "hologram/002_lantern.jpg"}


def test_own_shapes_lead_even_when_the_story_names_an_object():
    _grown("cosmic", "000_astrolabe.jpg", "astrolabe", own=True)
    _, picked = mp.pick_stills({"vibe": "cosmic", "brief": "a mobius at dawn"}, 5, record=False)
    assert picked[0]["noun"] == "astrolabe" and "mobius" in picked[1]["noun"]


def test_a_rejected_candidate_does_not_block_a_later_keeper(tmp_path):
    for i in range(3):
        _grown("synthetic2", f"00{i}_p{i}.jpg", f"p{i}")
    folder = tmp_path / "batch"
    _still(folder / "00_astrolabe.png", cx=0.5, cy=0.5, r=0.2, back=(120, 120, 124))  # the pool's object on a drifted backdrop
    _still(folder / "01_astrolabe_again.png", cx=0.5, cy=0.5, r=0.2)
    res = L.import_folder("synthetic2", folder)
    assert res["kept"] == 1 and "duplicate" not in res["rejected"] and res["rejected_n"] == 1


def test_grow_route_reserves_the_slot_before_the_probe(monkeypatch):
    import threading
    import time as _t

    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())

    def slow_available(cfg=None, **kw):
        _t.sleep(0.4)
        return {"ok": True, "note": ""}

    got = {}

    def fake_grow(vibe, count=36, *, nouns=None, own=False, cfg=None, seed=None, progress=None, cancel=None, client=None, sheet=True):
        got["nouns"] = list(nouns or [])
        return {"vibe": vibe, "asked": len(nouns or []), "made": 0, "kept": 0, "rejected": {}, "files": [], "seconds": 0.1, "nouns": nouns}

    monkeypatch.setattr(L, "available", slow_available)
    monkeypatch.setattr(L, "grow", fake_grow)
    codes, replies = [], []

    def post():
        r = client.post("/api/stills/grow", json={"vibe": "cosmic", "count": 4})
        codes.append(r.status_code)
        replies.append(r.json())

    threads = [threading.Thread(target=post) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 409]
    started = next(r for r in replies if r.get("ok"))
    for _ in range(50):
        if client.get("/api/stills").json()["job"].get("status") == "done":
            break
        _t.sleep(0.05)
    assert got["nouns"] == started["nouns"] and len(started["nouns"]) == 4  # the thread renders the subjects the reply listed
    monkeypatch.setattr(L, "available", lambda cfg=None, **kw: {"ok": False, "note": "ComfyUI is not answering"})
    assert client.post("/api/stills/grow", json={"vibe": "cosmic"}).status_code == 503
    assert client.get("/api/stills").json()["job"]["status"] == "error"  # a failed start leaves the slot free
    with _ui._LOCK:
        _ui._STILLS_JOB.clear()


def test_cli_import_refuses_a_non_folder(tmp_path):
    from xenoform import cli

    with pytest.raises(SystemExit, match="not a folder"):
        cli.main(["stills", "import", "cosmic", str(tmp_path / "nope")])


def test_front_end_has_the_library_row():
    js = (Path(mp.OBJECTS).parents[0] / "app.js").read_text(encoding="utf-8")
    assert "function stillsRow(easy)" in js and "${stillsRow(easy)}" in js
    assert 'data-act="easy-grow"' in js and 'id="easy-own-shapes"' in js and 'data-act="easy-make-shapes"' in js
    assert '"/api/stills/grow"' in js and "ownShapes" in js.split("const EASY_SAVED_KEYS")[1].split("\n")[0]
