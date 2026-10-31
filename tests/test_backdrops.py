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


def test_a_settings_plan_places_each_object_and_moves_on_round_the_places():
    places = S.place_list("liquid-gold")
    p = S.plan("liquid-gold", kind="setting", seed=4)
    assert p["kind"] == "setting" and len(p["nouns"]) == S.DEFAULT_GROW_SETTINGS == len(p["places"])
    assert set(p["places"]) <= set(places) and len(set(p["places"])) == min(len(places), len(p["places"]))
    assert all(pr.startswith(f"One single {n} cast in solid polished gold, {pl}.") for n, pl, pr in zip(p["nouns"], p["places"], p["prompts"]))
    assert S.plan("liquid-gold", kind="setting", seed=4)["places"] == p["places"]  # the desk plans, then grows the same
    typed = S.plan("neon-noir", 3, nouns=["lantern", "the rose", "koi fish"], kind="setting")
    assert typed["nouns"] == ["lantern", "rose", "koi fish"] and typed["places"] == S.place_list("neon-noir")[:3] and not typed["own"]
    assert S.places_for("neon-noir", 2, start=7) == [S.place_list("neon-noir")[7 % 8], S.place_list("neon-noir")[0]]


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
    assert nxt["places"] == S.places_for("neon-noir", 2, start=3)


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
        assert started["places"] == S.place_list("liquid-gold")[:2]
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
