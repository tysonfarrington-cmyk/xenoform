"""Backdrops (31 Oct 2026, docs/MUSIC_VIDEO_PLAN.md section 5). Tys: "the blank background really kills these ones - not
sure what to do, maybe bigger objects?" and "maybe have those scenes morph, not just have objects themselves morph but
scenes morph".

Track A: a scene pair on Final and Cloud is sent as a scene, as the Draft sends it: no "one object centred ... empty
background above and below it" portrait sentence, its guide uncompressed, and its frame never crushed to black or re-laid
as an object.

Track B: a third kind of still, the setting: one object standing in a place that suits the vibe, the object still the
hero and big in the frame. Its places, prompts, checks, zoom, grow, desk route and CLI. No GPU and no Comfy Cloud here:
fakes stand in for both."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from xenoform import cloud_backend, cloud_final, dense, final_tier as ft, morph_pass as mp, portrait
from xenoform import stills as S
from xenoform.portrait import PROMPT_SUFFIX

SETTING_VIBES = ("none", "liquid-gold", "neon-noir", "black", "bioluminescent", "shadow-self", "origami-noir", "iridescent-glass",
                 "chrome-mercury", "botanical")


# ---------------------------------------------------------------------------------------------- fakes


class _Out:
    type = "video"

    def to_file(self, dest):
        Path(dest).write_bytes(b"mp4")


class _Result:
    outputs = [_Out()]

    def get_outputs(self, node):
        return self.outputs


class _Job:
    id = "j"
    status = "succeeded"

    def result(self):
        return _Result()


class _WF:
    def __init__(self, g):
        self.g = g

    def set_input(self, *a):
        pass


class _FinalClient:
    """A comfy-sdk client for the Final tier: keeps every graph it is sent."""

    def __init__(self):
        self.graphs = []
        self.assets = type("A", (), {"from_file": staticmethod(lambda p: p)})()
        self.workflows = type("W", (), {"from_json": staticmethod(lambda g: _WF(g))})()

    def submit(self, wf):
        self.graphs.append(wf.g)
        return _Job()


class _Cloud:
    """Stands in for cloud_backend.CloudBackend (as tests/test_cloud_final.py's FakeCloud does)."""

    max_parallel = 3

    def __init__(self):
        self.graphs = {}
        self.lock = threading.Lock()

    def prepare(self, graph, open_weights=True):
        assert cloud_backend.guard(graph) == []
        return graph

    def run(self, graph, out_dir, inputs=None, open_weights=True):
        save = next(n for n in graph.values() if n["class_type"] == "SaveVideo")
        i = int(save["inputs"]["filename_prefix"][-2:])
        with self.lock:
            self.graphs[i] = graph
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        out = Path(out_dir) / f"m{i:02d}.mp4"
        out.write_bytes(b"mp4")
        return [out]


def _pairs(tmp_path):
    """A scene opening onto two objects: the (scene, object) pair and the (object, object) pair."""
    rows = [{"path": str(tmp_path / "shore.png"), "noun": "dark shore", "kind": "scene", "file": "cosmic/100_dark_shore.jpg"},
            {"path": str(tmp_path / "orb.png"), "noun": "orb", "file": "cosmic/00_orb.jpg"},
            {"path": str(tmp_path / "owl.png"), "noun": "owl", "file": "cosmic/01_owl.jpg"}]
    for r in rows:
        Path(r["path"]).write_bytes(b"png")
    return rows


def _no_relay(monkeypatch):
    """The portrait re-lay reads real pictures; these fakes are not, and the re-lay is tested on its own below."""
    monkeypatch.setattr(portrait, "portrait_stills", lambda stills, work, *a, **k: [dict(s) for s in stills])
    monkeypatch.setattr(mp, "wait_or_cancel", lambda job, jobs, cancel, poll_s=0.4: None)


# ---------------------------------------------------------------------------------------------- Track A: Final and Cloud


def test_the_helpers_keep_a_scene_wide_and_uncompressed():
    assert portrait.suffix_for(("object", "object")) == PROMPT_SUFFIX
    assert portrait.suffix_for(("scene", "object")) == "" and portrait.suffix_for(("object", "scene")) == ""
    assert portrait.suffix_for(("scene", "scene")) == "" and portrait.suffix_for(None) == PROMPT_SUFFIX
    assert mp.guide_compression(("scene", "object"), 30) == (0, 30) and mp.guide_compression(("object", "scene"), 18) == (18, 0)
    assert mp.guide_compression(("object", "object"), 30) == (30, 30) and mp.guide_compression(None, 12) == (12, 12)
    g = ft.graph("p", length=49, seed=1, img_compression=(0, 30))
    assert g["102"]["inputs"]["img_compression"] == 0 and g["103"]["inputs"]["img_compression"] == 30
    g = cloud_final.graph("p", length=49, seed=1, width=576, height=1024, img_compression=(30, 0))
    assert g["8"]["inputs"]["img_compression"] == 30 and g["21"]["inputs"]["img_compression"] == 0
    assert ft.graph("p", length=49, seed=1, img_compression=22)["103"]["inputs"]["img_compression"] == 22  # one number: both


def test_a_vertical_final_on_ltx23_sends_a_scene_pair_as_a_scene(tmp_path, monkeypatch):
    _no_relay(monkeypatch)
    client = _FinalClient()
    shots = [{"render_s": 2, "seconds": 2.0}, {"render_s": 2, "seconds": 2.0}]
    ft.final_clips(shots, _pairs(tmp_path), tmp_path, {}, 40, "cosmic", client=client, vertical=True,
                   draft=lambda idx: {})
    by_seed = {g["14"]["inputs"]["noise_seed"]: g for g in client.graphs}
    scene, plain = by_seed[40], by_seed[41]
    assert "wide landscape scene" in scene["4"]["inputs"]["text"] and PROMPT_SUFFIX.strip() not in scene["4"]["inputs"]["text"]
    assert plain["4"]["inputs"]["text"].endswith(PROMPT_SUFFIX.strip())  # two objects keep the portrait sentence
    tune = ft.tuned("cosmic").get("img_compression", 18)
    assert scene["102"]["inputs"]["img_compression"] == 0 and scene["103"]["inputs"]["img_compression"] == tune
    assert plain["102"]["inputs"]["img_compression"] == tune == plain["103"]["inputs"]["img_compression"]


def test_a_vertical_final_on_ltx25_keeps_the_loose_guides_for_objects_only(tmp_path, monkeypatch):
    _no_relay(monkeypatch)
    monkeypatch.setenv("XENO_FINAL_MODEL", "ltx25")
    monkeypatch.setattr(cloud_final, "to_full_size", lambda clips, work, out, cfg, **k: (clips, []))
    client = _FinalClient()
    shots = [{"render_s": 3, "seconds": 3.0}, {"render_s": 3, "seconds": 3.0}]
    ft.final_clips(shots, _pairs(tmp_path), tmp_path, {}, 7, "cosmic", client=client, vertical=True, draft=lambda idx: {})
    by_prefix = {g["19"]["inputs"]["filename_prefix"]: g for g in client.graphs}
    scene, plain = by_prefix["xenoform/final00"], by_prefix["xenoform/final01"]
    assert scene["8"]["inputs"]["img_compression"] == 0 and scene["21"]["inputs"]["img_compression"] == cloud_final.LOOSE["img_compression"]
    assert plain["8"]["inputs"]["img_compression"] == plain["21"]["inputs"]["img_compression"] == cloud_final.LOOSE["img_compression"]
    assert scene["22"]["inputs"]["strength"] == cloud_final.LOOSE["end_strength"]  # the end guide stays loose: only the compression
    assert PROMPT_SUFFIX.strip() not in scene["3"]["inputs"]["text"] and scene["3"]["inputs"]["text"].startswith(cloud_final.lead("dark shore", "orb"))
    assert plain["3"]["inputs"]["text"].endswith(PROMPT_SUFFIX.strip())


def test_a_clips_cut_on_final_keeps_its_own_prompt_suffix_and_guides(tmp_path, monkeypatch):
    """clip_cut sends the clip frames as kind "scene" with its own prompt: that path is left exactly as it was."""
    _no_relay(monkeypatch)
    client = _FinalClient()
    frames = [{"path": str(tmp_path / "a.png"), "noun": "clip a", "kind": "scene"}, {"path": str(tmp_path / "b.png"), "noun": "clip b", "kind": "scene"}]
    ft.final_clips([{"render_s": 2, "seconds": 2.0}], frames, tmp_path, {}, 3, "none", client=client, vertical=True, relay=False,
                   prompt_text="A film transition.", draft=lambda idx: {})
    g = client.graphs[0]
    assert g["4"]["inputs"]["text"] == "A film transition." + PROMPT_SUFFIX and g["102"]["inputs"]["img_compression"] == 18


def test_cloud_final_sends_a_scene_pair_without_the_object_sentence_or_the_compression(tmp_path, monkeypatch):
    _no_relay(monkeypatch)
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    fake = _Cloud()
    shots = [{"seconds": 2.0}, {"seconds": 2.0}]
    cloud_final.cloud_clips(shots, _pairs(tmp_path), tmp_path, {}, 2727, "cosmic", vertical=True, backend=fake, name="ltx25")
    scene, plain = fake.graphs[0], fake.graphs[1]
    loose = cloud_final.LOOSE["img_compression"]
    assert (scene["8"]["inputs"]["img_compression"], scene["21"]["inputs"]["img_compression"]) == (0, loose)
    assert (plain["8"]["inputs"]["img_compression"], plain["21"]["inputs"]["img_compression"]) == (loose, loose)
    assert "wide landscape scene" in scene["3"]["inputs"]["text"] and PROMPT_SUFFIX.strip() not in scene["3"]["inputs"]["text"]
    assert plain["3"]["inputs"]["text"].endswith(PROMPT_SUFFIX.strip())
    flat = _Cloud()  # 16:9 never had the portrait sentence, and still has none
    cloud_final.cloud_clips(shots, _pairs(tmp_path), tmp_path / "w", {}, 2727, "cosmic", vertical=False, backend=flat, name="ltx25")
    assert PROMPT_SUFFIX.strip() not in flat.graphs[1]["3"]["inputs"]["text"] and flat.graphs[0]["8"]["inputs"]["img_compression"] == 0


def test_the_draft_keeps_a_scene_guide_uncompressed_without_an_autotune_value(tmp_path, monkeypatch):
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(mp, "tuned", lambda vibe: {"steps": 12})  # no img_compression for this vibe
    wfs = []

    class WF:
        def __init__(self):
            self.inputs = {}

        def set_input(self, node, key, value):
            self.inputs[(node, key)] = value

    class Stop(Exception):
        pass

    class Job:
        def result(self):
            raise Stop()

    class Client:
        class assets:
            @staticmethod
            def from_file(path):
                return path

        class workflows:
            @staticmethod
            def from_file(path):
                wf = WF()
                wfs.append(wf)
                return wf

        def submit(self, wf):
            return Job()

    stills = [{"path": "a.png", "kind": "scene"}, {"path": "b.png"}, {"path": "c.png"}]
    try:
        cm._local_clips([{"seconds": 2.0, "render_s": 2}] * 2, stills, tmp_path, {}, 1, "porcelain-kintsugi", client=Client())
    except Stop:
        pass
    assert (wfs[0].inputs[("8", "img_compression")], wfs[0].inputs[("21", "img_compression")]) == (0, 18)
    assert ("8", "img_compression") not in wfs[1].inputs  # an object pair with no tune keeps the graph's own value


# ---------------------------------------------------------------------------------------------- Track A: the stills


def _object_on_black(w=1280, h=720):
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = 10  # a dark ground the crush takes to 0
    img[h // 2 - 60:h // 2 + 60, w // 2 - 80:w // 2 + 80] = 210
    return img


def _dusk_scene(w=1280, h=720):
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.stack([30 + 160 * (1 - yy / h), 20 + 90 * (1 - yy / h), 60 + 40 * (xx / w)], axis=-1)
    img[int(h * 0.7):] = 6  # a dark shore along the bottom: near black, the crush would take it
    return np.clip(img, 0, 255).astype(np.uint8)


def test_the_black_crush_passes_a_scene_through_and_crushes_an_object(tmp_path):
    scene = portrait.save_png(_dusk_scene(), tmp_path / "shore.png")
    obj = portrait.save_png(_object_on_black(), tmp_path / "orb.png")
    out = portrait.black_stills([{"path": str(scene), "kind": "scene"}, {"path": str(obj)}], tmp_path)
    assert out[0]["path"] == str(scene) and not out[0].get("black_ground") and not (tmp_path / "black" / "shore_black.png").exists()
    assert out[1]["black_ground"] and Path(out[1]["path"]).name == "orb_black.png"
    crushed = portrait.load_rgb(Path(out[1]["path"]))
    assert crushed[:40].max() == 0  # the object's dark ground is pure black now
    # the portrait pass with the black ground asked for crushes the object only, and frames the scene by its kind
    got = portrait.portrait_stills([{"path": str(scene), "kind": "scene"}, {"path": str(obj)}], tmp_path, 360, 640, background="black")
    assert Path(got[0]["path"]).name == "shore_360x640.png" and Path(got[1]["path"]).name == "orb_black_360x640.png"


def test_frame_portrait_crops_a_scene_by_its_kind_not_by_its_box():
    from xenoform.beatfx import crop_box, resize

    still = _object_on_black()  # an object on a ground: re-laid whole, by default
    relaid = portrait.frame_portrait(still, 360, 640)
    assert relaid[:60].max() <= 12 and relaid[-60:].max() <= 12  # the ground above and below
    as_scene = portrait.frame_portrait(still, 360, 640, kind="scene")  # the same pixels as a scene: the centre crop
    x, y, cw, ch = crop_box(1280, 720, "9:16", 0.5, 0.5)
    assert np.array_equal(as_scene, resize(still[y:y + ch, x:x + cw], 360, 640))
    rng = np.random.default_rng(1)  # a kindless full frame is still cropped, as before
    full = rng.integers(40, 255, (720, 1280, 3), dtype=np.uint8)
    assert portrait.frame_portrait(full, 360, 640).std() > 20


def test_the_crush_test_reads_the_first_object_not_an_opening_scene(tmp_path):
    scene = portrait.save_png(_dusk_scene(), tmp_path / "shore.png")
    obj = portrait.save_png(_object_on_black(), tmp_path / "orb.png")
    assert dense.ground_is_black([{"path": str(scene), "kind": "scene"}, {"path": str(obj)}])  # the object's ground decides
    assert not dense.ground_is_black([{"path": str(scene)}])  # read as an object, the dusk sky is not black
    assert not dense.ground_is_black([{"path": str(scene), "kind": "scene"}])  # scenes alone: nothing to crush


# ---------------------------------------------------------------------------------------------- Track B: the setting kind

W, H = 512, 288


def _setting(path: Path, *, r: float = 0.34, seed: int = 0, blur: float = 0.0, cx: float = 0.5) -> Path:
    """A synthetic setting: a soft, textured place (a sky over a ground, blurred like a shallow depth of field) and one
    sharp, finely textured object standing in front of it."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    sky = np.stack([90 + 80 * (1 - yy / H), 60 + 60 * (1 - yy / H), 40 + 30 * (xx / W)], axis=-1)
    ground = (yy > H * (0.62 + 0.03 * np.sin(xx / 23.0 + seed)))[..., None]
    place = np.where(ground, np.array([120, 90, 50]) + 60 * rng.random((H, W, 1)), sky)
    place = np.asarray(Image.fromarray(np.clip(place, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(4)), np.float32)
    rr = r * H
    disc = ((xx - cx * W) / rr) ** 2 + ((yy - 0.5 * H) / rr) ** 2 <= 1.0
    texture = 140 + 100 * (rng.random((H, W, 1)) > 0.5)  # a crisp checker of grain: the object is in focus
    out = np.where(disc[..., None], np.concatenate([texture, texture * 0.8, texture * 0.4], axis=-1), place)
    im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


def _grown_setting(vibe: str, name: str, noun: str, place: str, seed: int = 0) -> Path:
    path = _setting(S.root() / vibe / name, seed=seed)
    idx = S._read_json(S.index_path(), {})
    idx.setdefault(vibe, []).append({"file": f"{vibe}/{name}", "noun": noun, "kind": "setting", "place": place})
    S._write_json(S.index_path(), idx)
    return path


def test_every_setting_vibe_has_a_subject_first_template_and_six_to_eight_places():
    data = json.loads(S.SETTINGS.read_text(encoding="utf-8"))
    prompts = S.prompts()
    bad = ("person", "people ", "woman", "man ", "face", "text", "letters", "logo", "sign ", "signs", "jellyfish")
    for vibe in SETTING_VIBES:
        places = data["vibes"][vibe]
        assert 6 <= len(places) <= 8 and len(set(places)) == len(places), vibe
        assert all(not any(w in p.lower() for w in bad) for p in places), vibe
        assert all(p.split()[0] in ("on", "in", "under", "among", "above", "at", "beside") for p in places), vibe  # read after the object
        tmpl = prompts[vibe]["setting"]
        assert "{noun}" in tmpl and "{place}" in tmpl and tmpl.index("{noun}") < tmpl.index(".") < len(tmpl) // 4, vibe  # the subject leads
        assert "no people" in tmpl and "no text" in tmpl and "key light" not in tmpl.lower(), vibe
        assert "backdrop" not in tmpl and "void" not in tmpl, vibe  # the place is the ground now
        assert "filling two thirds of the frame height" in tmpl, vibe  # big in the frame
    assert 6 <= len(data["default"]) <= 8 and "{place}" in prompts["default"]["setting"]
    assert S.place_list("some-new-vibe") == [S.clean_place(p) for p in data["default"]]
    for row in prompts.values():  # every row still reads as an object prompt too (tests/test_stills.py)
        assert "{noun}" in row["subject"]


def test_a_setting_prompt_puts_the_object_first_in_its_place():
    gold = S.prompt_for("liquid-gold", "scarab", "setting", place="on wind-rippled sand dunes at dusk")
    assert gold.startswith("One single scarab cast in solid polished gold, on wind-rippled sand dunes at dusk. ")
    assert "{" not in gold and "key light" not in gold.lower()
    first = S.prompt_for("neon-noir", "lantern", "setting")  # no place given: the vibe's first place
    assert S.place_list("neon-noir")[0] in first and first.startswith("One single lantern made of black wet lacquered glass")
    # a vibe with no template: the default, with its material and its look minus the backdrop words
    other = S.prompt_for("ferrofluid", "owl", "setting", place="on a stone ledge in soft light")
    assert other.startswith("One single owl made of oily black magnetic fluid, on a stone ledge in soft light.")
    assert "jet-black glossy ferrofluid" in other and "void" not in other and "{" not in other
    cosmic = S.prompt_for("cosmic", "orb", "setting", place="on a rooftop at dusk")  # an original: its look is morph_pass's
    assert "cobalt and violet glow" in cosmic and "backdrop" not in cosmic
    assert S.prompt_for("cosmic", "orb") == S.prompt_for("cosmic", "orb", "object")  # objects as before
    assert S.place_look("each object in its own real materials, soft natural studio light, plain dark grey backdrop, photorealistic") \
        == "each object in its own real materials, photorealistic"


def test_kind_counts_and_nouns_tell_settings_apart():
    _grown_setting("cosmic", "000_owl.jpg", "owl", "on a rooftop at dusk")
    assert S.kind_of({"kind": "setting"}) == "setting" and S.kind_of({"kind": "scene"}) == "scene" and S.kind_of({}) == "object"
    assert S.kind_of({"kind": "weird"}) == "object"
    assert S.counts("cosmic") == {"shipped": 12, "grown": 0, "own": 0, "scenes": 0, "settings": 1, "total": 13}
    assert S.setting_nouns_in("cosmic") == {"owl"} and "owl" not in S.nouns_in("cosmic") - {"owl"}
    assert S.grown()["cosmic"][0]["place"] == "on a rooftop at dusk"


def test_a_setting_is_checked_like_a_scene(tmp_path):
    pool = [Path(str(tmp_path / f"p{i}.png")) for i in range(6)]
    for i, p in enumerate(pool):  # a pool of objects on a plain dark ground
        a = np.full((H, W, 3), 10, np.uint8)
        a[100:190, 180 + 6 * i:300 + 6 * i] = 200
        Image.fromarray(a).save(p)
    prof = S.profile(pool)
    place = _setting(tmp_path / "scarab.png", seed=3)
    as_object = S.check(place, prof)
    assert not as_object["ok"] and set(as_object["why"]) <= {"backdrop", "size", "cropped"}
    as_setting = S.check(place, prof, kind="setting")
    assert as_setting["ok"] and as_setting["why"] == [] and as_setting["backdrop"] == 0.0
    assert S.check(_setting(tmp_path / "soft.png", seed=3, blur=9.0), prof, kind="setting")["why"] == ["soft"]
    again = S.check(_setting(tmp_path / "again.png", seed=3), prof, kind="setting", extra_greys=[as_setting["grey"]])
    assert again["why"] == ["duplicate"]


def test_the_hero_box_finds_the_object_in_its_place_and_the_fill_zoom_makes_a_small_one_big(tmp_path):
    big = S.hero_box(_setting(tmp_path / "big.png", r=0.36))
    assert big is not None and big[0] < 0.5 < big[2] and big[1] < 0.5 < big[3] and big[3] - big[1] >= 0.6
    small_path = _setting(tmp_path / "small.png", r=0.13, seed=5)
    small = S.hero_box(small_path)
    assert small is not None and small[3] - small[1] < S.FILL_MIN["setting"] and small[0] < 0.5 < small[2]
    im = Image.open(small_path).convert("RGB")
    zoomed = S.normalise_scale(im, "setting")
    assert zoomed.size == im.size and not np.array_equal(np.asarray(zoomed), np.asarray(im))
    after = S.hero_box(zoomed)
    assert after[3] - after[1] > (small[3] - small[1]) * 1.3  # the object is bigger in the frame
    same = Image.open(_setting(tmp_path / "big2.png", r=0.36)).convert("RGB")
    assert np.array_equal(np.asarray(S.normalise_scale(same, "setting")), np.asarray(same))  # a big hero is left alone
    off = Image.open(_setting(tmp_path / "corner.png", r=0.12, cx=0.16)).convert("RGB")  # a sharp thing off to the side is no hero
    assert np.array_equal(np.asarray(S.normalise_scale(off, "setting")), np.asarray(off))
    assert S.FILL["setting"] > S.FILL["object"]  # a setting's object is held bigger than a plain one


def test_ingest_keeps_a_setting_ungraded_zooms_it_by_its_fill_and_lists_its_place(tmp_path, monkeypatch):
    graded, zoomed = [], []
    monkeypatch.setattr(S, "grade", lambda im, vibe: (graded.append(vibe), im)[1])
    real = S.normalise_scale
    monkeypatch.setattr(S, "normalise_scale", lambda im, kind="object", fill=None: (zoomed.append(kind), real(im, kind, fill))[1])
    v = S.ingest("liquid-gold", _setting(tmp_path / "scarab.png", seed=8), "scarab", kind="setting", place="on wind-rippled sand dunes at dusk", seed=42)
    assert v["kept"] and v["file"].startswith("liquid-gold/000_scarab") and not graded and zoomed == ["setting"]
    row = S.grown()["liquid-gold"][0]
    assert row["kind"] == "setting" and row["place"] == "on wind-rippled sand dunes at dusk" and row["noun"] == "scarab" and row["seed"] == 42
    again = S.ingest("liquid-gold", _setting(tmp_path / "scarab.png", seed=8), "scarab", kind="setting")
    assert not again["kept"] and again["why"] == ["duplicate"]  # a duplicate of the first setting
    assert S.counts("liquid-gold")["settings"] == 1


def test_a_culled_still_never_lends_its_number_and_row_to_the_next(tmp_path):
    first = S.ingest("neon-noir", _setting(tmp_path / "key.png", seed=11), "skeleton key", kind="setting", place="on the subway steps")
    assert first["kept"] and first["file"] == "neon-noir/000_skeleton_key.jpg"
    (S.root() / first["file"]).unlink()  # the cull: delete the jpg
    again = S.ingest("neon-noir", _setting(tmp_path / "key2.png", seed=12), "skeleton key", kind="setting", place="on a loading dock")
    assert again["kept"] and again["file"] == "neon-noir/001_skeleton_key.jpg"  # not 000 again
    rows = S.grown()["neon-noir"]
    assert [(r["file"], r["place"]) for r in rows] == [("neon-noir/001_skeleton_key.jpg", "on a loading dock")]  # the culled row stays gone


def test_a_settings_plan_places_each_object_and_moves_on_round_the_places():
    places = S.place_list("liquid-gold")
    p = S.plan("liquid-gold", kind="setting", seed=4)
    assert p["kind"] == "setting" and len(p["nouns"]) == S.DEFAULT_GROW_SETTINGS == len(p["places"])
    assert set(p["places"]) <= set(places) and len(set(p["places"])) == min(len(places), len(p["places"]))
    assert all(pr.startswith(f"One single {n} cast in solid polished gold, {pl}.") for n, pl, pr in zip(p["nouns"], p["places"], p["prompts"]))
    assert S.plan("liquid-gold", kind="setting", seed=4)["places"] == p["places"]  # the desk plans, then grows the same
    typed = S.plan("neon-noir", 3, nouns=["lantern", "the rose", "koi fish"], kind="setting")
    assert typed["nouns"] == ["lantern", "rose", "koi fish"] and not typed["own"]
    assert len(set(typed["places"])) == 3 and set(typed["places"]) <= set(S.place_list("neon-noir"))
    assert "water" in typed["places"][2] or "pier" in typed["places"][2]  # the koi fish to the water, not to a car bonnet
    assert S.places_for("neon-noir", 2, start=7) == [S.place_list("neon-noir")[7 % 8], S.place_list("neon-noir")[0]]
    shore = S.places_for("none", 3, nouns=["seahorse", "compass", "owl"])
    assert ("pool" in shore[0] or "beach" in shore[0]) and ("table" in shore[1] or "library" in shore[1] or "workshop" in shore[1])
    assert S.place_fit("nautilus", "in a rock pool on a sunny shore") > S.place_fit("nautilus", "on a workbench in a dusty workshop")
    many = S.places_for("none", 10, nouns=["owl"] * 10)
    assert len(set(many[:8])) == 8 and set(many[8:]) <= set(many[:8])  # every place once before any twice


class _GrowClient:
    """A comfy-sdk client whose renders are synthetic settings (the shape tests/test_stills.py's fake uses)."""

    def __init__(self):
        self.prompts = []

    class _WF:
        def __init__(self):
            self.inputs = {}

        def set_input(self, node, name, value):
            self.inputs[(node, name)] = value

    @property
    def workflows(self):
        class WFs:
            def from_file(self, path):
                assert Path(path).name == "zimage_t2i_api.json"
                return _GrowClient._WF()

        return WFs()

    def submit(self, wf):
        self.prompts.append(wf.inputs[(S.N_TEXT, "text")])
        k = len(self.prompts) - 1

        class Out:
            def to_file(self, path):
                _setting(Path(path), seed=30 + k, r=0.34)

        class Result:
            outputs = []

            def get_outputs(self, node):
                return [Out()]

        class Job:
            def result(self):
                return Result()

        return Job()


def test_grow_with_kind_setting_renders_each_object_in_its_place_and_lists_settings():
    fake = _GrowClient()
    res = S.grow("neon-noir", 3, nouns=["lantern", "rose", "koi fish"], client=fake, seed=9, kind="setting", sheet=True)
    assert res["kind"] == "setting" and res["kept"] == 3 and res["rejected"] == {} and len(res["places"]) == 3
    assert [p.split(",")[0] for p in fake.prompts] == ["One single lantern made of black wet lacquered glass",
                                                        "One single rose made of black wet lacquered glass",
                                                        "One single koi fish made of black wet lacquered glass"]
    assert all(pl in pr for pl, pr in zip(res["places"], fake.prompts))
    rows = S.grown()["neon-noir"]
    assert [r["kind"] for r in rows] == ["setting"] * 3 and [r["place"] for r in rows] == res["places"]
    assert Path(res["sheet"]).name == "settings.jpg" and S.counts("neon-noir")["settings"] == 3
    nxt = S.plan("neon-noir", 2, kind="setting")  # the next grow moves on to the places not reached yet
    assert nxt["places"] == S.places_for("neon-noir", 2, start=3, nouns=nxt["nouns"])


def test_the_desk_grows_settings_and_counts_them(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    client = TestClient(_ui.create_app())
    got = client.get("/api/stills?vibe=liquid-gold").json()
    assert got["default_grow_settings"] == S.DEFAULT_GROW_SETTINGS and got["setting_places"] == len(S.place_list("liquid-gold"))
    assert got["have"]["settings"] == 0
    monkeypatch.setattr(S, "available", lambda cfg=None, **kw: {"ok": True, "note": ""})
    calls = {}

    def fake_grow(vibe, count=36, *, nouns=None, own=False, cfg=None, seed=None, progress=None, cancel=None, client=None, sheet=True,
                  kind="object"):
        calls.update({"vibe": vibe, "count": count, "nouns": nouns, "own": own, "kind": kind})
        progress(1, 1, 1)
        return {"vibe": vibe, "kind": kind, "asked": 1, "made": 1, "kept": 1, "rejected": {}, "files": [], "seconds": 1.0, "nouns": nouns}

    monkeypatch.setattr(S, "grow", fake_grow)
    try:
        started = client.post("/api/stills/grow", json={"vibe": "liquid-gold", "kind": "setting", "nouns": "scarab, owl"}).json()
        assert started["ok"] and started["kind"] == "setting" and started["nouns"] == ["scarab", "owl"]
        assert started["places"] == S.plan("liquid-gold", 2, nouns=["scarab", "owl"], kind="setting")["places"]
        assert started["places"][1] == "on wind-rippled sand dunes at dusk"  # the owl to the dunes; the scarab takes what is left
        import time as _t

        for _ in range(50):
            job = client.get("/api/stills").json()["job"]
            if job.get("status") == "done":
                break
            _t.sleep(0.05)
        assert job["status"] == "done" and job["kind"] == "setting"
        assert calls["kind"] == "setting" and calls["nouns"] == ["scarab", "owl"] and calls["own"] is False
    finally:
        with _ui._LOCK:
            _ui._STILLS_JOB.clear()


def test_the_cli_grows_settings(capsys):
    from xenoform import cli

    cli.main(["stills", "grow", "liquid-gold", "--kind", "setting", "--nouns", "scarab", "--plan", "--seed", "1"])
    out = capsys.readouterr().out
    assert "scarab: One single scarab cast in solid polished gold, " in out and "1 settings" in out


# ---------------------------------------------------------------------------------------------- the Backdrop choice and the pick


def _pool(monkeypatch, n_objects=12, n_settings=14, n_scenes=4, vibe="cosmic"):
    """A catalogue of objects, settings and scenes for one vibe, nothing on disk (the pick reads rows only)."""
    objects = [{"file": f"{vibe}/{i:02d}_thing{i}.jpg", "noun": f"thing{i}"} for i in range(n_objects)]
    settings = [{"file": f"{vibe}/{200 + i:03d}_place{i}.jpg", "noun": f"thing{i}", "kind": "setting", "place": f"on ground {i}"}
                for i in range(n_settings)]
    scenes = [{"file": f"{vibe}/{100 + i:03d}_scene{i}.jpg", "noun": f"scene {i}", "kind": "scene"} for i in range(n_scenes)]
    monkeypatch.setattr(mp, "manifest", lambda: {vibe: objects})
    monkeypatch.setattr(S, "grown", lambda: {vibe: settings + scenes} if (settings or scenes) else {})
    monkeypatch.setattr(S, "usage", lambda: {})
    monkeypatch.setattr(mp, "autotune", lambda: {})
    return objects, settings, scenes


def test_the_backdrop_choice_reads_the_body_else_the_vibe(monkeypatch):
    _pool(monkeypatch, n_settings=14)
    assert mp.BACKDROPS == ("plain", "places", "scenes")
    assert mp.backdrop_choice({"vibe": "cosmic"}) == "places"  # fourteen places: a vibe with them cuts in them
    assert mp.backdrop_choice({"vibe": "cosmic", "backdrop": "PLAIN"}) == "plain" and mp.backdrop_choice({"vibe": "cosmic", "backdrop": "auto"}) == "places"
    assert mp.backdrop_choice({"vibe": "cosmic", "scene_stills": "only"}) == "scenes"  # the old Scenes value still reads
    assert mp.scene_mode({"vibe": "cosmic", "backdrop": "scenes"}) == "only" and mp.scene_mode({"vibe": "cosmic", "scene_stills": "mix"}) == "mix"
    _pool(monkeypatch, n_settings=mp.PLACES_DEFAULT_MIN - 1)
    assert mp.backdrop_choice({"vibe": "cosmic"}) == "plain"  # too few to carry a cut: the studio ground, unless asked
    assert mp.backdrop_choice({"vibe": "cosmic", "backdrop": "places"}) == "places"
    rows = list(S.grown()["cosmic"]) + [{"file": "x", "noun": "x"}]
    assert {S.kind_of(r) for r in mp.rows_of_kind(rows, "off", "places")} == {"setting"}
    assert {S.kind_of(r) for r in mp.rows_of_kind(rows, "mix", "places")} == {"setting", "scene"}
    assert {S.kind_of(r) for r in mp.rows_of_kind(rows, "mix", "plain")} == {"object", "scene"}
    assert {S.kind_of(r) for r in mp.rows_of_kind(rows, "off", "scenes")} == {"scene"}
    objects_only = [{"file": "o", "noun": "o"}]
    assert mp.rows_of_kind(objects_only, "off", "places") == objects_only  # no settings: the objects, as the pick does


def test_places_draws_on_settings_mix_lands_scenes_between_and_plain_keeps_them_out(monkeypatch):
    _pool(monkeypatch)
    _, placed = mp.pick_stills({"vibe": "cosmic", "backdrop": "places"}, 9, record=False)
    assert all(S.kind_of(p) == "setting" for p in placed) and len({p["file"] for p in placed}) == 9
    _, mixed = mp.pick_stills({"vibe": "cosmic", "backdrop": "places", "scene_stills": "mix"}, 9, record=False, scene_at=[0, 4, 8])
    assert [S.kind_of(p) for p in mixed] == ["scene", "setting", "setting", "setting", "scene", "setting", "setting", "setting", "scene"]
    _, plain = mp.pick_stills({"vibe": "cosmic", "backdrop": "plain"}, 9, record=False)
    assert all(S.kind_of(p) == "object" for p in plain)
    _, scenes = mp.pick_stills({"vibe": "cosmic", "backdrop": "scenes"}, 4, record=False)
    assert all(S.kind_of(p) == "scene" for p in scenes)
    _, auto = mp.pick_stills({"vibe": "cosmic"}, 6, record=False)  # fourteen places and no word: places
    assert all(S.kind_of(p) == "setting" for p in auto)
    _pool(monkeypatch, n_settings=0)
    _, bare = mp.pick_stills({"vibe": "cosmic", "backdrop": "places"}, 6, record=False)
    assert all(S.kind_of(p) == "object" for p in bare)  # no places yet: the objects, never an empty cut


def test_a_typed_object_leads_its_places_cut(monkeypatch):
    _, settings, _ = _pool(monkeypatch)
    for row, noun in zip(settings, ("owl", "rose", "kettle", "scarab", "lantern", "anchor", "comet", "tulip", "harp", "kite",
                                    "acorn", "bell", "drum", "fern")):
        row["noun"] = noun
    _, picked = mp.pick_stills({"vibe": "cosmic", "backdrop": "places", "idea": "a scarab at dusk"}, 5, record=False)
    assert picked[0]["noun"] == "scarab" and S.kind_of(picked[0]) == "setting"  # the line's object opens, in its place


def test_a_pair_in_a_place_gets_its_own_prompt_on_draft_final_and_cloud():
    from xenoform.morph_style import OPENINGS

    look = mp.VIBE_LOOK["none"]
    assert "backdrop" in look  # the plain look names its studio ground ...
    two = mp.prompt_for("none", kinds=("setting", "setting"))
    assert two.startswith(OPENINGS["melt"])
    assert "the place around it slowly shifts with it" in two and "the camera steady" in two
    assert "backdrop" not in two and "macro product photography" not in two and "the object stays centred" not in two  # ... a place has none
    shatter = mp.prompt_for("none", kinds=("setting", "setting"), style="shatter")
    assert "shatters" in shatter and "slowly shifts with it" in shatter  # the style is how the object changes, in its place too
    grow_in = mp.prompt_for("liquid-gold", kinds=("object", "setting"))
    assert "a place slowly grows around it" in grow_in and "the picture never cuts" in grow_in
    assert "fades away around it" in mp.prompt_for("liquid-gold", kinds=("setting", "object"))
    wide = mp.prompt_for("cosmic", kinds=("scene", "setting"))
    assert "wide landscape scene" in wide and "one object standing in a place" in wide
    assert mp.prompt_for("cosmic", "ltx25", ("setting", "setting")).startswith("Use the provided start image")
    assert mp.pair_kinds({"kind": "setting"}, {"kind": "scene"}) == ("setting", "scene") and mp.pair_kinds({}, {"kind": "x"}) == ("object", "object")
    assert mp.prompt_for("cosmic") == mp.prompt_for("cosmic", kinds=("object", "object"))  # the plain chain, word for word
    assert portrait.suffix_for(("setting", "setting")) == portrait.SETTING_SUFFIX and portrait.suffix_for(("setting", "scene")) == ""
    assert mp.guide_compression(("setting", "object"), 30) == (30, 30)  # a setting's object morphs: its guide keeps the freedom


def test_cloud_final_sends_a_setting_pair_with_the_place_sentence(tmp_path, monkeypatch):
    _no_relay(monkeypatch)
    monkeypatch.setenv(cloud_backend.KEY_ENV, "sk-test-not-a-key")
    rows = [{"path": str(tmp_path / f"s{i}.png"), "noun": n, "kind": "setting"} for i, n in enumerate(("scarab", "owl"))]
    fake = _Cloud()
    cloud_final.cloud_clips([{"seconds": 2.0}], rows, tmp_path, {}, 5, "liquid-gold", vertical=True, backend=fake, name="ltx25")
    text = fake.graphs[0]["3"]["inputs"]["text"]
    assert text.startswith(cloud_final.lead("scarab", "owl")) and text.endswith(portrait.SETTING_SUFFIX.strip())
    assert "slowly shifts with it" in text and PROMPT_SUFFIX.strip() not in text
    assert fake.graphs[0]["8"]["inputs"]["img_compression"] == cloud_final.LOOSE["img_compression"]


def test_the_portrait_pass_leaves_a_setting_alone_and_crops_around_its_object(tmp_path):
    from xenoform.beatfx import crop_box, resize

    big = np.asarray(Image.open(_setting(tmp_path / "s.png", r=0.3, cx=0.3)).convert("RGB").resize((1280, 720)))
    out = portrait.frame_portrait(big, 360, 640, kind="setting")
    hero = S.hero_box(Image.fromarray(big))
    x, y, cw, ch = crop_box(1280, 720, "9:16", (hero[0] + hero[2]) / 2, 0.5)
    assert x < crop_box(1280, 720, "9:16", 0.5, 0.5)[0]  # the window moved toward the object on the left
    assert np.array_equal(out, resize(big[y:y + ch, x:x + cw], 360, 640))
    src = portrait.save_png(big, tmp_path / "place.png")
    passed = portrait.black_stills([{"path": str(src), "kind": "setting"}], tmp_path)
    assert passed[0]["path"] == str(src) and not passed[0].get("black_ground")  # its place is never crushed to black
    assert not dense.ground_is_black([{"path": str(src), "kind": "setting"}])


def test_the_long_song_pool_counts_the_settings_a_places_cut_draws_on(monkeypatch, tmp_path):
    _pool(monkeypatch, n_objects=30, n_settings=6, n_scenes=0)
    labels = ["intro", "calm", "build", "drop", "calm", "build", "drop", "outro"]
    duration, period = 238.8, 0.4
    step = duration / len(labels)
    sections = [{"label": lab, "start": round(i * step, 3), "end": round((i + 1) * step, 3)} for i, lab in enumerate(labels)]
    directed = {"duration": duration, "beats": [round(i * period, 4) for i in range(int(duration / period))], "sections": sections,
                "drop": 119.6}
    state = {"vibe": "cosmic", "energy_preset": "dense", "quality_tier": "draft", "aspect": "9:16", "backdrop": "places"}
    shots, plan = dense.shots_for(state, directed, tmp_path / "song.wav")
    _, _, chain, _ = dense.long_song_chain(state, directed, tmp_path / "song.wav", shots, plan, dense.options(state), engine="mock")
    assert chain["morphs"] == 5  # six places: five morphs, no place twice
    plain = {**state, "backdrop": "plain"}
    shots_p, plan_p = dense.shots_for(plain, directed, tmp_path / "song.wav")
    _, _, chain_p, _ = dense.long_song_chain(plain, directed, tmp_path / "song.wav", shots_p, plan_p, dense.options(plain), engine="mock")
    assert chain_p["morphs"] > 5  # the thirty objects


def _run_mock(tmp_path, monkeypatch, state, out_name):
    from xenoform import beatfx
    import xenoform.cloud_morph as cm

    rendered: dict = {}

    def fake_mock(shots, stills, work, w, h):
        rendered["stills"] = stills
        return [tmp_path / f"m{i:02d}.mp4" for i in range(len(shots))]

    def fake_compose(clips, shots, audio, out, **kw):
        rendered["shots"] = shots
        rendered["transitions"] = kw.get("transitions")
        Path(out).write_bytes(b"mp4")
        return {"frames": 1, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}}

    monkeypatch.setattr(cm, "_mock_clips", fake_mock)
    monkeypatch.setattr(beatfx, "compose", fake_compose)
    demo = Path(__file__).resolve().parents[1] / "examples" / "demo.wav"
    info = dense.run_simple({"duration": 20.0, "beats": [i * 0.5 for i in range(40)]}, demo, tmp_path / f"{out_name}.mp4",
                            tmp_path / out_name, {}, state, lambda *a: None, engine="mock")
    return info, rendered


def test_a_places_cut_records_its_backdrop_its_settings_and_the_kinds_each_shot_morphs_between(tmp_path, monkeypatch):
    from xenoform import lane

    for i in range(14):
        _grown_setting("ocean", f"{200 + i:03d}_thing{i}.jpg", f"thing{i}", f"on ground {i}", seed=40 + i)
    info, rendered = _run_mock(tmp_path, monkeypatch, {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft",
                                                       "energy_preset": "dense"}, "auto")
    assert info["backdrop"] == "places" and info["recut_state"]["backdrop"] == "places"  # fourteen places: the default
    assert info["setting_files"] == info["stills"] and info["scene_files"] == [] and info["scene_mode"] == "off"
    assert all(s.get("still_kinds") == ["setting", "setting"] for s in rendered["shots"])
    rec = json.loads((tmp_path / "auto" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert rec["backdrop"] == "places" and rec["setting_files"] == info["setting_files"]
    assert all(s.get("still_kinds") == ["setting", "setting"] for s in rec["plan_shots"])  # a re-cut reads them too
    built = lane.build(rec, "job")
    assert all(r.get("to_kind") == "setting" for r in built["shots"] if "to_kind" in r)
    assert {c["kind"] for c in built["stills"]} == {"setting"}
    chain = json.loads((tmp_path / "auto" / "simple" / "chain.json").read_text(encoding="utf-8"))
    assert {c["kind"] for c in chain} == {"setting"}  # the making screen's chain names them
    plain, _ = _run_mock(tmp_path, monkeypatch, {"vibe": "ocean", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense",
                                                 "backdrop": "plain"}, "plain")
    assert plain["backdrop"] == "plain" and plain["setting_files"] == [] and not set(info["setting_files"]) & set(plain["stills"])
    bare, _ = _run_mock(tmp_path, monkeypatch, {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense",
                                                "backdrop": "places"}, "bare")
    assert bare["setting_files"] == [] and any("backdrop" in n for n in bare["fallbacks"])  # asked with none: a note, objects


def test_the_record_rows_and_the_rerender_variants_know_settings(tmp_path):
    from xenoform import lane

    for i in range(2):
        _grown_setting("ocean", f"{200 + i:03d}_thing{i}.jpg", f"thing{i}", f"on ground {i}", seed=60 + i)
    files = ["ocean/200_thing0.jpg", "ocean/201_thing1.jpg"]
    rows = dense._still_rows(files, set(), set(files))
    assert [r["kind"] for r in rows] == ["setting", "setting"]
    shots = [{"morph": 0}, {"clip": 0}, {"morph": 5}]
    dense.stamp_still_kinds(shots, [{"kind": "scene"}, rows[0]])
    assert shots[0]["still_kinds"] == ["scene", "setting"] and shots[1]["still_kinds"] == ["scene", "setting"] and "still_kinds" not in shots[2]
    assert dense.RERENDER_VARIANTS["setting"] == ("setting", "setting") and dense.RERENDER_VARIANTS["scene-setting"] == ("scene", "setting")
    assert {"setting", "setting-scene", "scene-setting"} <= set(lane.choices()["rerender_variants"])


# ---------------------------------------------------------------------------------------------- the layers that want a plain ground


def test_the_foreshadow_trace_steps_aside_for_a_landing_in_a_place():
    from xenoform import foreshadow as F

    shots = [{"frames": 48, "still_kinds": ["object", "object"]}, {"frames": 48, "still_kinds": ["object", "setting"]},
             {"frames": 48, "still_kinds": ["setting", "object"]}]
    clips = ["c0.mp4", "c1.mp4", "c2.mp4"]
    frame = np.zeros((72, 128, 3), np.uint8)
    beats = [i * 0.5 for i in range(40)]
    traced = F.plan(shots, clips, beats, 24, "trace", F.params(None), read_edge=lambda clip, which: frame)
    assert traced[0] is None or traced[0]["target"] is None  # shot 1 lands in a place: no outline of the place leads it in
    assert traced[1]["target"] is not None and traced[1]["prev"] is None  # shot 2 lands on an object; nothing of the place fades
    sliced = F.plan(shots, clips, beats, 24, "slices", F.params(None), read_edge=lambda clip, which: frame)
    assert sliced[0]["target"] is not None and sliced[1]["prev"] is not None  # slices of any picture work: they stay
    plain = [dict(s) for s in shots]
    for s in plain:
        s.pop("still_kinds")
    old = F.plan(plain, clips, beats, 24, "silhouette", F.params(None), read_edge=lambda clip, which: frame)
    assert old[0]["target"] is not None  # a record from before the kinds: as it was cut


def test_the_match_cut_and_parallax_hand_off_plainly_into_a_place():
    from xenoform import transitions_fx as T

    shots = [{"still_kinds": ["object", "object"]}, {"still_kinds": ["object", "setting"]}, {"still_kinds": ["setting", "setting"]},
             {"still_kinds": ["setting", "object"]}, {"still_kinds": ["object", "object"]}]
    tr = [None, {"kind": "match-cut", "frames": 8}, {"kind": "depth-parallax", "frames": 8}, {"kind": "flow-carry", "frames": 8},
          {"kind": "match-cut", "frames": 8, "user": True}]
    out = T.kind_guard(tr, shots)
    assert out[1] == tr[1]  # object -> object at that boundary: kept
    assert out[2] is None  # into a place from a place: a plain handoff
    assert out[3] == tr[3]  # flow-carry reads motion, not a ground: kept
    assert out[4] == tr[4]  # a timeline pick is the user's
    assert T.kind_guard(None, shots) is None and T.kind_guard([None, {"kind": "match-cut"}], [{}, {}]) == [None, {"kind": "match-cut"}]
    assert set(T.NEEDS_PLAIN_GROUND) <= set(T.TRANSITIONS)


def test_a_cropped_cut_keeps_a_setting_shot_centred(tmp_path):
    import shutil
    import subprocess

    from xenoform import beatfx

    if shutil.which("ffmpeg") is None:
        return

    def clip(path: Path) -> Path:  # a bright sky patch to the left: the brightness centre is not the object
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:size=192x108:rate=24:duration=1",
                        "-vf", "drawbox=x=4:y=8:w=40:h=40:color=white:t=fill", "-pix_fmt", "yuv420p", str(path)], check=True)
        return path

    audio = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100:duration=2", str(audio)], check=True)
    clips = [clip(tmp_path / f"c{i}.mp4") for i in range(2)]
    shots = [{"index": 0, "start": 0.0, "end": 1.0, "seconds": 1.0, "frames": 24, "speed": 1.0, "ease": "", "effects": []},
             {"index": 1, "start": 1.0, "end": 2.0, "seconds": 1.0, "frames": 24, "speed": 1.0, "ease": "", "effects": [],
              "still_kinds": ["setting", "setting"]}]
    kw = dict(aspect="9:16", quality="draft", fx=False, overlay=False, beats=[0.5, 1.0, 1.5], size=(54, 96), fps=24, dance_fx="off",
              stem_orbit=False, seed=1)
    made = beatfx.compose(clips, shots, audio, tmp_path / "out.mp4", **kw)
    first, second = made["centres"]
    assert first[0][0] < 0.4  # an object shot follows its brightness, as before
    assert tuple(second[0]) == (0.5, 0.5) and tuple(second[1]) == (0.5, 0.5)  # a setting shot stays centred


def test_the_desk_has_the_backdrop_row_next_to_scenes_and_sends_it():
    js = (Path(mp.OBJECTS).parents[0] / "app.js").read_text(encoding="utf-8")
    assert "function backdropRow(easy)" in js and js.count("${scenesRow(easy)}${backdropRow(easy)}") == 2  # both knob blocks
    assert 'simpleSeg("easy-backdrop", current, [["plain", "Plain"], ["places", "Places"], ["scenes", "Scenes"]], "Backdrop")' in js
    assert 'act === "easy-backdrop"' in js and 'act === "easy-grow-settings"' in js and "Grow ${growPlaces} places" in js
    payload = js.split("function payload()")[1].split("function renderSetup")[0]
    assert 'backdrop: (state.easy && state.easy.backdrop) || "auto"' in payload
    assert '"backdrop"' in js.split("const EASY_SAVED_KEYS")[1].split("\n")[0]
    assert "const PLACES_DEFAULT_MIN = 12;" in js and mp.PLACES_DEFAULT_MIN == 12  # the row's default says what the pick does
    assert 'kind: "setting"' in js and "default_grow_settings" in js


def test_the_chain_preview_says_the_backdrop_and_names_settings(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui as _ui

    for i in range(3):
        _grown_setting("cosmic", f"{200 + i:03d}_thing{i}.jpg", f"thing{i}", f"on ground {i}", seed=70 + i)
    client = TestClient(_ui.create_app())
    got = client.post("/api/simple/chain", json={"audio_id": "demo", "vibe": "cosmic", "backdrop": "places", "length_s": 8}).json()
    assert got["backdrop"] == "places" and {r["kind"] for r in got["stills"]} == {"setting"}
    plain = client.get("/api/simple/chain?vibe=cosmic&backdrop=plain").json()
    assert plain["backdrop"] == "plain" and {r["kind"] for r in plain["stills"]} == {"object"}
