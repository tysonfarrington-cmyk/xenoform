"""Each guardrail field reaches the render code and changes its output."""
import numpy as np

from xenoform import guardrails as g


def test_nasa_anchor_changes_prompt_and_negative():
    st = {"anchor": "nasa", "prompt": "Jupiter storm"}
    assert "NASA" in g.guard_prompt("a planet", st)
    assert g.guard_prompt("a planet", {}) == "a planet"
    assert g.negative_for("text", st) != "text"


def test_stock_dance_and_black_in_prompt():
    p = g.guard_prompt("Polly dances", {"motion_source": "stock-dance", "still_background": "black"})
    assert "stock dance reference" in p and "pure black background" in p


def test_negative_extra_added_once():
    st = {"negative_extra": "extra fingers, text"}
    out = g.negative_for("text, watermark", st)
    assert out == "text, watermark, extra fingers"


def test_director_prompt_table_is_guarded():
    out = g.guard_prompts({"negative": "text", "s0": "a feather"}, {"negative_extra": "cartoon", "anchor": "nasa", "prompt": "x"})
    assert "cartoon" in out["negative"] and "NASA" in out["s0"]


def test_director_uses_guard_prompts():
    import inspect
    from xenoform import director, final_tier, cloud_morph
    assert "guard_prompts(" in inspect.getsource(director.run_directed)
    src = inspect.getsource(final_tier.final_clips)
    assert "guard_prompt(" in src and "negative=negative" in src
    assert "guard_prompt(" in inspect.getsource(cloud_morph._local_clips)


def test_final_graph_takes_negative():
    from xenoform import final_tier
    gr = final_tier.graph("p", length=9, seed=1, negative="NEG")
    assert gr["5"]["inputs"]["text"] == "NEG"
    assert final_tier.graph("p", length=9, seed=1)["5"]["inputs"]["text"] == final_tier.NEGATIVE


def test_min_motion_drops_static_footage():
    assert not g.motion_ok({"kind": "video", "motion_score": 0.05}, 0.15)
    assert g.motion_ok({"kind": "video", "motion_score": 0.4}, 0.15)
    assert g.motion_ok({"kind": "image"}, 0.15)
    assert g.motion_ok({"kind": "video", "motion_score": 0.0}, 0.0)


def test_pick_pair_honours_min_motion():
    from xenoform import source_library as sl
    import inspect
    assert "min_motion" in inspect.signature(sl.pick_pair).parameters
    assert "min_motion" in inspect.signature(sl.plan_for_scenes).parameters
    assert sl.library_filters({"min_motion_score": 0.15})["min_motion"] == 0.15


def test_black_ground_crushes_dark_ground_only():
    from xenoform.portrait import black_ground
    img = np.full((60, 40, 3), 12, np.uint8)
    img[20:40, 10:30] = 200
    out = black_ground(img)
    assert out[0, 0].max() == 0 and out[30, 20].min() == 200
    light = np.full((60, 40, 3), 230, np.uint8)
    assert (black_ground(light) == light).all()


def test_black_stills_written(tmp_path):
    from xenoform.portrait import black_stills, load_rgb, save_png
    img = np.full((64, 64, 3), 20, np.uint8)
    img[20:44, 20:44] = 180
    src = save_png(img, tmp_path / "a.png")
    got = black_stills([{"path": str(src)}], tmp_path)
    assert got[0]["black_ground"] and load_rgb(got[0]["path"])[0, 0].max() == 0


def test_shot_fx_scales_and_wobbles():
    from xenoform.beatfx import beat_fx
    rng = np.random.default_rng(1)
    f = rng.integers(0, 255, (64, 96, 3), dtype=np.uint8)
    kw = dict(kick=1.0, trans=1.0, punch=1.0, loud=1.0, beat_index=1)
    full = beat_fx(f, **kw).astype(int)
    low = beat_fx(f, intensity=0.25, **kw).astype(int)
    none = beat_fx(f, intensity=0.0, **kw).astype(int)
    assert np.abs(low - none).mean() < np.abs(full - none).mean()
    still = beat_fx(f, intensity=0.0, wobble=0.0, t=0.125, **kw)
    wob = beat_fx(f, intensity=0.0, wobble=1.0, t=0.125, **kw)
    assert not np.array_equal(still, wob)
    assert g.shot_fx({"fx_intensity": 0.25, "wobble": 0.1}) == (0.25, 0.1)
    assert g.shot_fx({}) == (1.0, 0.0)


def test_block_fx_carried_to_shots():
    shots = [{"frames": 10}, {"frames": 10}]
    out = g.carry_block_fx(shots, {"blocks": [{"fx_intensity": 0.2}, {"wobble": 0.1}]})
    assert out[0]["fx_intensity"] == 0.2 and out[1]["wobble"] == 0.1


def test_compose_reads_shot_fx():
    import inspect
    from xenoform import beatfx, dense
    assert "shot_fx(shot)" in inspect.getsource(beatfx.compose)
    src = inspect.getsource(dense.run_simple)
    assert "carry_block_fx" in src and "black_stills" in src


def test_still_background_only_for_black_vibes():
    body, _ = g.apply({"blocks": [{"form": "feather"}], "vibe": "black"})
    assert body["still_background"] == "black"
    body, _ = g.apply({"blocks": [{"form": "feather"}], "vibe": "paper-summer"})
    assert "still_background" not in body or g.black_ground_vibe("paper-summer")
