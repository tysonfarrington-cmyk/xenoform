"""The default path stays open weights only."""

from xenoform.config import load_config
from xenoform.eligibility import (
    ADDONS_DEFAULT,
    STILLS,
    VIDEO_CORE,
    VIDEO_MORPH,
    addons_enabled,
    audit_default_workflows,
    audit_graph,
    call_allowed,
    local_text_encoder,
    partner_key,
)
from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT
from xenoform.restyle import _action_model


def test_default_workflows_have_no_partner_or_api_nodes():
    assert audit_default_workflows() == []


def test_ltx_api_key_stays_empty_and_encoding_stays_local():
    empty = {
        "nodes": [
            {"type": "CLIPLoader", "inputs": {"clip_name": "t5xxl_fp8_e4m3fn_scaled.safetensors", "type": "ltxv"}},
            {"type": "CLIPTextEncode", "inputs": [{"name": "text", "type": "STRING"}]},
            {"type": "PrimitiveString", "title": "LTX API KEY", "widgets_values": [""]},
        ]
    }
    assert audit_graph(empty, label="synthetic") == []
    assert local_text_encoder(empty) is True

    filled = {
        "nodes": [
            {"type": "CLIPLoader"},
            {"type": "PrimitiveString", "title": "LTX API KEY", "widgets_values": ["ltx-secret"]},
        ]
    }
    filled_hits = audit_graph(filled, label="synthetic")
    assert any("LTX API key field is set" in hit for hit in filled_hits)
    assert all("ltx-secret" not in hit for hit in filled_hits)

    api_inputs = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a shot", "api_key": "ltx-secret"}}}
    assert any("LTX API key field is set" in hit for hit in audit_graph(api_inputs, label="synthetic"))
    blank = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a shot", "api_key": ""}}}
    assert audit_graph(blank, label="synthetic") == []

    remote = {"4": {"class_type": "GemmaAPITextEncode", "inputs": {"api_key": "", "prompt": "a shot"}}}
    remote_hits = audit_graph(remote, label="synthetic")
    assert any("api text encoder" in hit for hit in remote_hits)
    assert local_text_encoder(remote) is False


def test_ltx_25_partner_nodes_fail_the_audit():
    for kind in ("LtxApi25TextToVideo", "LtxApi25ImageToVideo", "LtxApi25AudioToVideo"):
        hits = audit_graph({"1": {"class_type": kind, "inputs": {"prompt": "a shot"}}}, label="synthetic")
        assert any("ltx partner node" in hit for hit in hits), kind


def test_a_partner_or_api_node_fails_the_audit():
    flux = audit_graph({"9": {"class_type": "FluxProUltraImageNode"}}, label="synthetic")
    assert flux and "FluxProUltraImageNode" in flux[0]
    h3 = audit_graph({"nodes": [{"type": "HiggsfieldH3"}]}, label="synthetic")
    assert h3 and "HiggsfieldH3" in h3[0]
    api = audit_graph({"1": {"class_type": "BlackForestLabsFlux3API"}}, label="synthetic")
    assert api


def test_addons_env_off_overrides_a_config_that_asks(monkeypatch):
    monkeypatch.setenv("XENO_ADDONS", "0")
    assert addons_enabled({"comfy": {"addons": True}}) is False
    monkeypatch.setenv("XENO_ADDONS", "false")
    assert addons_enabled({"comfy": {"addons": True}}) is False
    monkeypatch.setenv("XENO_ADDONS", "1")
    assert addons_enabled({"comfy": {"addons": False}}) is True


def test_addons_default_off_and_partner_key_stays_put(monkeypatch):
    monkeypatch.delenv("XENO_ADDONS", raising=False)
    cfg = load_config()
    assert ADDONS_DEFAULT is False
    assert cfg["comfy"]["addons"] is False
    assert addons_enabled(cfg) is False
    cfg["comfy"]["partner_api_key_env"] = "XENO_PARTNER_TEST"
    env = {"XENO_PARTNER_TEST": "secret-key"}
    assert partner_key(cfg, env) == ""
    cfg["comfy"]["addons"] = True
    assert partner_key(cfg, env) == "secret-key"
    cfg["comfy"]["addons"] = False
    assert partner_key(cfg, env) == ""


def test_cloud_llm_needs_addons_and_loopback_does_not():
    assert call_allowed("http://127.0.0.1:11434") is True
    assert call_allowed("") is True
    assert call_allowed("https://api.openai.com/v1") is False
    assert call_allowed("https://api.openai.com/v1", allow_cloud=True) is True


def test_morphs_use_ltx_095_and_action_stays_on_ltx_23():
    cfg = {"comfy": {"video_model": "ltx-23", "addons": False}}
    engine, checkpoint = _action_model(cfg, "final", "signature", LARGE_CHECKPOINT)
    assert engine == "ltx-23"
    assert checkpoint == LARGE_CHECKPOINT
    engine, checkpoint = _action_model(cfg, "turbo", "signature", LARGE_CHECKPOINT)
    assert engine == "ltx-095"
    assert "2.3" not in checkpoint
    engine, checkpoint = _action_model(cfg, "final", "first-frame", LARGE_CHECKPOINT)
    assert engine == "ltx-23"
    assert checkpoint == LARGE_CHECKPOINT
    engine, checkpoint = _action_model(cfg, "turbo", "first-frame", LARGE_CHECKPOINT)
    assert engine == "ltx-095"
    assert "2.3" not in checkpoint
    assert STILLS == "Z-Image Turbo"
    assert VIDEO_CORE == "LTX-2.3"
    assert VIDEO_MORPH == "LTX 0.9.5"
