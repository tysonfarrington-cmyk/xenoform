"""29 Oct, retaking the README shots: Setup & models said Download for LTX 0.9.5, LTX-2.3 and Z-Image while ComfyUI
rendered with all of them. The desk's launch line (`set XENO_MODELS=...models && python ...`) left a space on the
folder, so the check looked in "models \\checkpoints". Now ComfyUI's own /models/<folder> lists decide, the folder
is the fallback when ComfyUI is down, the variable is trimmed, and the page says Draft / Fast Final / Final."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
LOADERS = {"CheckpointLoaderSimple": "checkpoints", "UNETLoader": "diffusion_models", "CLIPLoader": "text_encoders", "VAELoader": "vae"}


def _comfy(monkeypatch, listing: dict[str, list[str]]) -> list[tuple[str, str]]:
    asked: list[tuple[str, str]] = []

    def fetch(base, folder):
        asked.append((base, folder))
        return list(listing.get(folder, []))

    monkeypatch.setattr("xenoform.models_setup._fetch_listing", fetch)
    return asked


def _graph_files(name: str) -> dict[str, list[str]]:
    graph = json.loads((ROOT / "workflows" / name).read_text(encoding="utf-8"))
    files: dict[str, list[str]] = {}
    for node in graph.values():
        folder = LOADERS.get(node.get("class_type"))
        for value in (node.get("inputs") or {}).values():
            if folder and isinstance(value, str) and value.endswith(".safetensors"):
                files.setdefault(folder, []).append(value)
    return files


def _weight(path: Path, size: int = 2_000_000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)


def test_what_comfyui_lists_counts_although_the_models_folder_is_empty(tmp_path, monkeypatch):
    from xenoform.models_setup import inspect_setup

    asked = _comfy(monkeypatch, {
        "checkpoints": ["ltx-video-2b-v0.9.5.safetensors", "ltx-2.3-22b-distilled-fp8.safetensors", "ace_step_1.5_turbo_aio.safetensors"],
        # the T5 the brief thought was missing: ComfyUI also reads models/clip and extra_model_paths.yaml
        "text_encoders": ["t5xxl_fp8_e4m3fn_scaled.safetensors", "qwen_3_4b.safetensors", "LTX\\gemma_sub.safetensors"],
        "diffusion_models": ["z_image_turbo_int8_convrot.safetensors", "z_image_int8_convrot.safetensors"],
        "vae": ["ae.safetensors"],
    })
    setup = inspect_setup(tmp_path, comfy_url="http://127.0.0.1:8188/")
    by_id = {item["id"]: item for item in setup["models"]}
    assert setup["missing_required"] == []
    assert by_id["ltx-095"]["present"] and by_id["ltx-23"]["present"] and by_id["ace-step"]["present"]
    assert by_id["ltx-23"]["chosen"] == "checkpoints/ltx-2.3-22b-distilled-fp8.safetensors"
    # Z-Image: the int8 file the stills graph loads, never the base z_image model
    assert by_id["z-image"]["present"] and by_id["z-image"]["variants"] == ["diffusion_models/z_image_turbo_int8_convrot.safetensors"]
    assert by_id["wan22-i2v"]["present"] is False
    assert "ComfyUI at http://127.0.0.1:8188 " in setup["checked"]
    # one question a folder for the whole check, not one a slot
    assert len(asked) == len(set(asked)) and {base for base, _ in asked} == {"http://127.0.0.1:8188"}


def test_the_shipped_graphs_files_are_the_ones_that_count(tmp_path, monkeypatch):
    from xenoform.models_setup import chosen_filename, model_present

    for graph, model_id in (("zimage_t2i_api.json", "z-image"), ("xenoform_morph.json", "ltx-095"), ("ltx_v2v_api.json", "ltx-095")):
        listing = _graph_files(graph)
        _comfy(monkeypatch, listing)
        monkeypatch.setattr("xenoform.models_setup._LISTED", {})
        assert model_present(model_id, tmp_path), graph
        loaded = [name for names in listing.values() for name in names]
        assert chosen_filename(model_id, tmp_path) in loaded, graph


def test_comfyui_decides_and_the_folder_is_only_the_fallback(tmp_path, monkeypatch):
    from xenoform.models_setup import inspect_setup, model_present

    _weight(tmp_path / "diffusion_models" / "z_image_turbo_int8_convrot.safetensors")
    # ComfyUI down (conftest): the folder answers
    setup = inspect_setup(tmp_path)
    assert next(item for item in setup["models"] if item["id"] == "z-image")["present"] is True
    assert setup["checked"] == f"ComfyUI is not answering, so the desk checked the files in {tmp_path}."
    # ComfyUI up without that file: the graph could not load it, so it is missing
    _comfy(monkeypatch, {"diffusion_models": ["flux-2-klein-4b.safetensors"]})
    monkeypatch.setattr("xenoform.models_setup._LISTED", {})
    assert model_present("z-image", tmp_path) is False


def test_a_space_after_the_models_folder_is_trimmed(tmp_path, monkeypatch):
    from xenoform.models_setup import model_present, models_root

    _weight(tmp_path / "checkpoints" / "ltx-2.3-22b-distilled-fp8.safetensors")
    monkeypatch.setenv("XENO_MODELS", f"{tmp_path} ")
    assert models_root() == tmp_path
    assert model_present("ltx-23") is True
    monkeypatch.setenv("XENO_MODELS", f'"{tmp_path}"')
    assert models_root() == tmp_path


def test_the_setup_route_asks_the_desks_comfyui_and_the_page_says_how_it_checked(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    asked = _comfy(monkeypatch, {"checkpoints": ["ltx-video-2b-v0.9.5.safetensors"], "text_encoders": ["t5xxl_fp8_e4m3fn_scaled.safetensors"]})
    data = TestClient(create_app()).get("/api/setup").json()
    assert data["missing_required"] == [] and data["checked"].startswith("Checked against the files ComfyUI at")
    assert asked and all(base == "http://127.0.0.1:8188" for base, _ in asked)
    setup = APP.split("function renderSetup()", 1)[1].split("\n}\n", 1)[0]
    assert "setup.checked" in setup


def test_the_tier_sentence_is_draft_fast_final_and_final():
    from xenoform.hardware import tier_for_gb

    for gb in (8, 12, 24):
        detail = tier_for_gb(gb)["detail"]
        assert "Draft is LTX-Video 0.9.5" in detail and "Fast Final" in detail and "Final" in detail, gb
        assert "Draft and Final use LTX-2.3" not in detail and "Turbo" not in detail, gb
    assert "LTX-2.3 22B distilled fp8" in tier_for_gb(12)["detail"]
