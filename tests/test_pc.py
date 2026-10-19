"""The desk on a real 12 GB Windows machine: variants, the brief, ComfyUI."""

from pathlib import Path

from xenoform.analyze import read_features
from xenoform.comfy_health import DEFAULT_COMFY, ping
from xenoform.config import DEFAULTS
from xenoform.continuity import continuity_bible, story_logic
from xenoform.hardware import FAST_CHECKPOINT, apply_tier, tier_for_gb
from xenoform.models_setup import choose_file, inspect_setup
from xenoform.storyboard import plan_storyboard, scene_prompt


def _features():
    return read_features("examples/demo_features.json")


def _weight(folder: Path, name: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"x" * 1_000_001)


def test_quantised_filenames_count_and_can_be_picked(tmp_path):
    _weight(tmp_path / "checkpoints", "ltx-2.3-22b-distilled-fp8.safetensors")
    _weight(tmp_path / "diffusion_models", "z_image_turbo_int8_convrot.safetensors")
    setup = inspect_setup(tmp_path)
    by_id = {item["id"]: item for item in setup["models"]}
    assert by_id["ltx-23"]["present"] is True
    assert by_id["ltx-23"]["filename"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    assert "ltx-2.3-22b-distilled-fp8.safetensors" in by_id["ltx-23"]["variants"][0]
    assert by_id["z-image"]["present"] is True
    assert "int8" in by_id["z-image"]["filename"]
    assert "LTX 0.9.5 fast" in setup["missing_required"]
    picked = choose_file("ltx-23", "checkpoints/ltx-2.3-22b-distilled-fp8.safetensors", tmp_path)
    assert picked["filename"].endswith("fp8.safetensors")
    again = inspect_setup(tmp_path)
    ltx = next(item for item in again["models"] if item["id"] == "ltx-23")
    assert ltx["chosen"].endswith("ltx-2.3-22b-distilled-fp8.safetensors")


def test_12gb_loads_fp8_ltx23_and_turbo_does_not(tmp_path, monkeypatch):
    monkeypatch.setenv("XENO_MODELS", str(tmp_path))
    cfg = {
        "fps": 24,
        "render": {"width": 640, "height": 360, "max_steps": 40, "backend": "cpu"},
        "comfy": {"width": 640, "height": 360, "steps": 30, "video_model": "ltx"},
    }
    _weight(tmp_path / "checkpoints", "ltx-2.3-22b-distilled.safetensors")
    full = apply_tier(cfg, tier_for_gb(12), quality="final")
    assert full["comfy"]["checkpoint_name"] == FAST_CHECKPOINT
    assert full["comfy"]["video_model"] == "ltx-095"

    _weight(tmp_path / "checkpoints", "ltx-2.3-22b-distilled-fp8.safetensors")
    final = apply_tier(cfg, tier_for_gb(12), quality="final")
    assert final["comfy"]["checkpoint_name"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    assert final["comfy"]["video_model"] == "ltx-23"
    assert final["comfy"]["width"] == 704
    assert final["comfy"]["height"] == 384
    assert final["render"]["width"] % 32 == 0
    turbo = apply_tier(cfg, tier_for_gb(12), quality="turbo")
    assert turbo["comfy"]["checkpoint_name"] == FAST_CHECKPOINT
    assert "2.3" not in turbo["comfy"]["checkpoint_name"]
    assert "does not fit" not in tier_for_gb(12)["detail"]


def test_lighthouse_brief_does_not_star_the_rocket():
    brief = "A lighthouse keeper and a fox wait out the storm."
    scenes = plan_storyboard(_features(), "pynchon", brief)
    assert scenes[0]["protagonist"] == "the lighthouse keeper"
    assert scenes[0]["prop"] == "fox"
    assert scenes[0]["place"] == "lighthouse"
    blob = " ".join(scene["action"] for scene in scenes).lower()
    assert "rocket" not in blob
    assert "fox" in scenes[0]["action"]
    assert "at the lighthouse" in scenes[0]["action"]
    assert "faces with" not in blob
    prompt = scene_prompt(scenes[0], "base")
    assert "rocket" not in prompt.lower()
    assert "lighthouse keeper" in prompt.lower()
    assert "does not morph" in prompt
    bible = continuity_bible(brief, scenes)
    names = [element["name"] for element in bible["elements"]]
    assert "fox" in names
    assert any("lighthouse" in element["sentence"] for element in bible["elements"])
    assert story_logic(brief, scenes)["ok"] is True


def test_comfy_health_pings_system_stats(monkeypatch):
    assert DEFAULTS["comfy"]["base_url"] == "http://127.0.0.1:8188"
    assert DEFAULT_COMFY.endswith(":8188")
    seen = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{}"

    def opener(request, timeout=0):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr("xenoform.comfy_health.urlopen", opener)
    up = ping("http://127.0.0.1:8188")
    assert up["ok"] is True
    assert up["detail"] == "Connected"
    assert seen["url"] == "http://127.0.0.1:8188/system_stats"

    def down(request, timeout=0):
        raise OSError("refused")

    monkeypatch.setattr("xenoform.comfy_health.urlopen", down)
    missing = ping("")
    assert missing["ok"] is False
    assert missing["detail"] == "Not connected"
    assert missing["url"] == "http://127.0.0.1:8188"


def test_models_root_finds_comfy_under_the_home_ai_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("XENO_MODELS", raising=False)
    models = tmp_path / "AI" / "ComfyUI" / "models"
    models.mkdir(parents=True)
    monkeypatch.setattr("xenoform.models_setup.Path.home", classmethod(lambda cls: tmp_path))
    from xenoform.models_setup import models_root

    assert models_root() == models


def test_installer_keeps_its_own_venv_and_the_desk_port():
    ps1 = Path("install.ps1").read_text(encoding="utf-8")
    bat = Path("Xenoform.bat").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    assert ".venv" in ps1
    assert "3.12" in ps1
    assert "LinkNodes" in ps1
    assert "47317" in ps1
    assert "python_embeded" not in ps1
    assert "47317" in bat
    assert "/MIN" in bat
    assert "Get-NetTCPConnection" not in bat
    assert "netstat" in bat
    assert "api/v1/health" in bat
    assert "xenoform_duplicate.log" in bat
    assert "xenoform_server.log" in bat
    assert "XENO_ADDONS=0" in bat
    assert "configs\\local.json" in bat
    assert "--config" in bat
    assert "47317" in readme
    assert "47291" not in readme
    assert "Xenoform.bat" in readme


def test_missing_demo_files_are_written(tmp_path, monkeypatch):
    from xenoform.demo_assets import ensure_demo_assets

    def fake_demo(**kwargs):
        Path(kwargs["out"]).write_bytes(b"0" * 200)
        return {"path": str(kwargs["out"])}

    monkeypatch.setattr("xenoform.try_it.try_demo", fake_demo)
    made = ensure_demo_assets(tmp_path)
    assert Path(made["wav"]).is_file()
    assert Path(made["video"]).stat().st_size > 100
    assert (tmp_path / "examples" / "demo_features.json").is_file()
    again = ensure_demo_assets(tmp_path)
    assert again["wav"] == ""
    assert again["video"] == ""
