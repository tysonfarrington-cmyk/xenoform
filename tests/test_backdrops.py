"""Backdrops (31 Oct 2026, docs/MUSIC_VIDEO_PLAN.md section 5). Tys: "the blank background really kills these ones - not
sure what to do, maybe bigger objects?" and "maybe have those scenes morph, not just have objects themselves morph but
scenes morph".

Track A: a scene pair on Final and Cloud is sent as a scene, as the Draft sends it: no "one object centred ... empty
background above and below it" portrait sentence, its guide uncompressed, and its frame never crushed to black or re-laid
as an object. No GPU and no Comfy Cloud here: fakes stand in for both."""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from xenoform import cloud_backend, cloud_final, dense, final_tier as ft, morph_pass as mp, portrait
from xenoform.portrait import PROMPT_SUFFIX


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
