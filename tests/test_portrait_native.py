"""Native vertical Final: portrait stills, the 448x768 graph, defaults and the crop fallback. No GPU."""

from __future__ import annotations

import numpy as np
import pytest

from xenoform import dense, final_tier as ft, simple_recipe
from xenoform.portrait import frame_portrait, portrait_stills, save_png, subject_box


def _wide_object():
    img = np.zeros((720, 1280, 3), np.uint8)
    img[300:420, 140:1140] = 220  # a wide shape that a centre crop would cut off
    return img


def test_wide_object_lands_whole_and_centred_on_black():
    out = frame_portrait(_wide_object(), 720, 1280)
    assert out.shape == (1280, 720, 3)
    x0, y0, x1, y1 = subject_box(out, np.zeros(3, np.float32))
    assert x0 > 0 and x1 < 720 and y0 > 0 and y1 < 1280  # nothing spills off the edge
    assert abs((x0 + x1) / 2 - 360) <= 4 and abs((y0 + y1) / 2 - 640) <= 4
    assert out[:100].max() == 0 and out[-100:].max() == 0


def test_full_frame_scene_is_centre_cropped():
    rng = np.random.default_rng(1)
    scene = rng.integers(40, 255, (720, 1280, 3), dtype=np.uint8)
    out = frame_portrait(scene, 360, 640)
    assert out.shape == (640, 360, 3) and out.std() > 20


def test_portrait_stills_are_cached_files(tmp_path):
    src = save_png(_wide_object(), tmp_path / "wing.png")
    got = portrait_stills([{"path": str(src), "file": "wing.png"}] * 2, tmp_path)
    assert len(got) == 2 and got[0]["path"] == got[1]["path"] and got[0]["portrait"]
    assert (tmp_path / "portrait" / "wing_720x1280.png").is_file()


def test_vertical_graph_is_portrait_and_ltx_legal():
    w, h = ft.RENDER_916
    ow, oh = ft.out_916()
    g = ft.graph("p", length=ft.gen_length(2), seed=3, width=w, height=h, out_w=ow, out_h=oh)
    lw, lh = g["7"]["inputs"]["width"], g["7"]["inputs"]["height"]
    assert (lw, lh) == (224, 384) and lw % 32 == 0 and lh % 32 == 0 and w % 32 == 0 and h % 32 == 0
    assert (g["42"]["inputs"]["width"], g["42"]["inputs"]["height"]) == (1080, 1920)
    assert (g["7"]["inputs"]["length"] - 1) % 8 == 0
    assert w * h == ft.RENDER_W * ft.RENDER_H  # same pixels as landscape: same memory and ETA


def test_graph_refuses_illegal_sizes_and_lengths():
    with pytest.raises(ValueError):
        ft.graph("p", length=49, seed=1, width=450, height=768)
    with pytest.raises(ValueError):
        ft.graph("p", length=50, seed=1)


def test_720_output_switch(monkeypatch):
    monkeypatch.setenv("XENO_FINAL_916_OUT", "720")
    assert ft.out_916() == (720, 1280) and ft.sizes(True) == {"render": (448, 768), "out": (720, 1280)}
    assert ft.sizes(False) == {"render": (768, 448), "out": (1280, 720)}


def test_native_is_the_default_for_final_9x16_and_crop_stays_an_option():
    assert dense.options({"aspect": "9:16", "quality_tier": "final"})["vertical"] == "native"
    assert dense.options({"aspect": "9:16", "quality_tier": "final", "vertical_mode": "crop"})["vertical"] == "crop"
    assert dense.options({"aspect": "9:16", "quality_tier": "draft", "vertical_mode": "native"})["vertical"] == "crop"


def test_recipe_carries_the_vertical_choice():
    base = {"vibe": "black", "aspect": "9:16", "quality_tier": "final"}
    assert "vertical_mode" not in simple_recipe.decode(simple_recipe.encode(base))
    back = simple_recipe.decode(simple_recipe.encode({**base, "vertical_mode": "crop"}))
    assert back["vertical_mode"] == "crop"


def test_final_clips_native_uses_portrait_stills_and_prompt(tmp_path, monkeypatch):
    src = save_png(_wide_object(), tmp_path / "a.png")
    seen = {}

    class Job:
        pass

    class WF:
        def __init__(self, g):
            seen["graph"] = g

        def set_input(self, node, key, value):
            seen.setdefault("inputs", []).append((node, value))

    class Client:
        class assets:
            @staticmethod
            def from_file(p):
                return p

        class workflows:
            @staticmethod
            def from_json(g):
                return WF(g)

        def submit(self, wf):
            raise RuntimeError("CUDA out of memory")

    from xenoform import morph_pass as mp

    monkeypatch.setattr(mp, "wait_or_cancel", lambda *a, **k: None)
    monkeypatch.setattr(mp, "stop_queued", lambda *a, **k: None)
    clips, notes = ft.final_clips([{"render_s": 2, "seconds": 2}], [{"path": str(src)}, {"path": str(src)}], tmp_path, {},
                                  1, "black", client=Client(), draft=lambda ix: {i: tmp_path / "d.mp4" for i in ix},
                                  vertical=True)
    g = seen["graph"]
    assert (g["7"]["inputs"]["width"], g["7"]["inputs"]["height"]) == (224, 384)
    assert "portrait" in g["4"]["inputs"]["text"].lower()
    assert all("portrait" in str(v) for _, v in seen["inputs"])
    assert [n["fallback"] for n in notes] == ["ltx095-draft"] and notes[0]["oom"]  # OOM fallback kept


def test_fill_is_bigger_but_never_clips():
    from xenoform import portrait

    assert (portrait.FILL_W, portrait.FILL_H) == (0.95, 0.72)
    wide = frame_portrait(_wide_object(), 720, 1280)
    x0, y0, x1, y1 = subject_box(wide, np.zeros(3, np.float32))
    assert x0 > 0 and x1 < 720 and (x1 - x0) / 720 >= 0.80  # fills the width, stays whole
    tall = np.zeros((720, 1280, 3), np.uint8)
    tall[40:680, 600:700] = 200
    out = frame_portrait(tall, 720, 1280)
    x0, y0, x1, y1 = subject_box(out, np.zeros(3, np.float32))
    assert y0 > 0 and y1 < 1280 and (y1 - y0) / 1280 <= 0.72 and (y1 - y0) / 1280 >= 0.6  # height-limited


def test_every_entry_defaults_9x16_final_to_native():
    from pathlib import Path

    assert dense.options({"aspect": "9:16", "quality_tier": "final", "cut_plan": dense.demo1_plan()})["vertical"] == "native"
    code = simple_recipe.encode({"vibe": "black", "aspect": "9:16", "quality_tier": "final"})
    assert dense.options(simple_recipe.decode(code))["vertical"] == "native"
    js = (Path(dense.ROOT) / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    assert 'easy.vertical === "crop" ? "crop" : "native"' in js and '["native", "Native"], ["crop", "Crop"]' in js