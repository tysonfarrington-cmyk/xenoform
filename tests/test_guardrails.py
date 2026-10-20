from xenoform import guardrails as g


def ids(rep):
    return {x["id"] for x in rep["applied"]}


def test_config_loads_all_rules():
    r = g.rules()
    for k in ("morph_density", "morph_run_clean", "simple_objects", "duplicate_features", "character_motion",
              "footage_motion", "native_vertical", "morph_background", "text_encoder", "vram", "ui_effects",
              "shimmer", "open_weights"):
        assert k in r
    assert len(g.summary()) == len(r)


def test_morph_density_clamps_22_in_20s():
    body, rep = g.apply({"morph_count": 22}, duration=20)
    assert body["morph_count"] == 15 and "morph_density" in ids(rep)


def test_morph_density_warns_between_caps_and_expert_keeps():
    body, rep = g.apply({"morph_count": 17}, duration=20)
    assert body["morph_count"] == 17 and rep["warnings"]
    body, rep = g.apply({"morph_count": 22, "expert": True}, duration=20)
    assert body["morph_count"] == 22 and rep["expert"] and not rep["applied"] and rep["warnings"]


def test_stutter_removed_from_morph_run():
    blocks = [{"form": "feather", "transition": "stutter", "effects": [{"type": "stutter", "t": 12.8}, {"type": "punch"}]}]
    body, rep = g.apply({"blocks": blocks})
    b = body["blocks"][0]
    assert b["transition"] == "morph" and b["effects"] == [{"type": "punch"}]
    assert body["still_background"] == "black"


def test_simple_objects_warn():
    _, rep = g.apply({"blocks": [{"form": "cup"}, {"form": "ball"}, {"form": "feather"}]})
    assert any(w["id"] == "simple_objects" for w in rep["warnings"])


def test_jupiter_gets_nasa_anchor_and_negative():
    body, rep = g.apply({"prompt": "giant Jupiter storm"})
    assert body["anchor"] == "nasa" and "multiple storms" in body["negative_extra"]


def test_character_motion_stock_dance():
    body, _ = g.apply({"prompt": "Polly dancing through worlds", "motion_source": "pose"})
    assert body["motion_source"] == "stock-dance" and "hands" in body["negative_extra"]


def test_motion_score_floor():
    body, rep = g.apply({"min_motion_score": 0.01})
    assert body["min_motion_score"] == 0.15
    body, _ = g.apply({})
    assert body["min_motion_score"] == 0.15


def test_vertical_crop_goes_native():
    body, rep = g.apply({"aspect": "9:16", "vertical_mode": "crop"})
    assert body["vertical_mode"] == "native" and body["upscaler"] == "realesrgan-x4"


def test_t5_on_ltx2_is_hard_fix_even_in_expert():
    cfg = {"comfy": {"checkpoint_name": "ltx-2.3-22b-distilled.safetensors", "clip_name": "t5xxl_fp8.safetensors"}}
    _, rep = g.apply({"expert": True}, cfg=cfg)
    assert "text_encoder" in ids(rep) and cfg["comfy"]["clip_name"].startswith("gemma")


def test_t5_ok_on_ltx095():
    cfg = {"comfy": {"checkpoint_name": "ltx-video-2b-v0.9.5.safetensors", "clip_name": "t5xxl_fp8.safetensors"}}
    assert not g.check_config(cfg)["applied"]


def test_vram_12gb():
    body, rep = g.apply({"width": 720, "height": 1280, "render_s": 8, "parallel": 3}, vram_gb=12)
    assert (body["width"], body["height"], body["render_s"], body["parallel"]) == (448, 768, 5, 1)


def test_ui_effects_and_wobble_budget():
    blocks = [{"form": "x", "kind": "ui", "fx_intensity": 0.9, "wobble": 0.5}, {"form": "y", "wobble": 0.1},
              {"form": "z", "wobble": 0.1}]
    body, _ = g.apply({"blocks": blocks})
    b = body["blocks"]
    assert b[0]["fx_intensity"] == 0.25 and b[0]["wobble"] == 0.1 and b[2]["wobble"] == 0


def test_shimmer_banned_even_expert():
    body, rep = g.apply({"transitions": ["shimmer", "snap"], "blocks": [{"form": "a", "transition": "wavy"}], "expert": True})
    assert body["transitions"] == ["snap"] and body["blocks"][0]["transition"] == "dissolve"
    assert "shimmer" in ids(rep)


def test_partner_off_in_contest_mode_expert_labels():
    body, rep = g.apply({"paid_cloud": True, "cloud_quality": True, "cloud_confirm": "t"})
    assert body["paid_cloud"] is False and body["cloud_confirm"] == ""
    body, rep = g.apply({"paid_cloud": True, "cloud_quality": True, "expert": True})
    assert body["paid_cloud"] is True and body["open_weights_only"] is False
    body, rep = g.apply({"paid_cloud": True, "open_weights_only": False})
    assert body["paid_cloud"] is True


def test_clean_body_untouched():
    body, rep = g.apply({"aspect": "16:9", "morph_count": "auto"})
    assert not rep["applied"] and "expert" not in body and body["guardrails"] is rep


def test_cli_lists_and_checks(tmp_path, capsys):
    import json
    from xenoform import cli
    assert cli.main(["guardrails"]) == 0
    assert "morph_density" in capsys.readouterr().out
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"morph_count": 22, "aspect": "9:16", "vertical_mode": "crop"}))
    out = tmp_path / "o.json"
    assert cli.main(["guardrails", str(f), "--duration", "20", "--out", str(out)]) == 0
    clean = json.loads(out.read_text())
    assert clean["morph_count"] == 15 and clean["vertical_mode"] == "native"


def test_mcp_registers_guardrail_tools():
    import inspect
    from xenoform import mcp_tools
    src = inspect.getsource(mcp_tools)
    assert "def list_guardrails" in src and "def check_guardrails" in src and "guardrails" in src.split("def get_started")[1][:900]


def test_desk_generate_applies_guardrails(monkeypatch):
    from fastapi.testclient import TestClient
    from xenoform import ui
    app = ui.create_app() if hasattr(ui, "create_app") else None
    if app is None:
        import pytest
        pytest.skip("no app factory")
    c = TestClient(app)
    r = c.get("/api/guardrails")
    assert r.status_code == 200 and len(r.json()["guardrails"]) >= 13
    r = c.post("/api/guardrails/check", json={"morph_count": 30, "duration": 20, "transitions": ["shimmer"]})
    rep = r.json()["report"]
    assert {"morph_density", "shimmer"} <= {x["id"] for x in rep["applied"]}
