"""4 Nov 2026, the Setup half of docs/UI_REVIEW.md (M1, M2, M3, M5).

M2: the Final card fetched the 46 GB full LTX-2.3 file, not the fp8 file the Final loads, and not the Gemma 3 text
encoder or the upscalers its own text said it needs; it lists those four now, with one total, and an LTX-2.5 card
exists. M3: a Download that does not fit the drive says why. M5: the tier sentence is written from the model the Final
resolves to, and a GPU that is not CUDA reads "GPU not recognised". M1: /api/setup says what Make is missing."""

from pathlib import Path

import pytest

from xenoform import final_tier, hardware
from xenoform import models_setup as ms
from xenoform.errors import PlainError

GB = 1_000_000_000


def _tier(monkeypatch, gb):
    monkeypatch.setattr(ms, "detect_tier", lambda: hardware.tier_for_gb(gb))


def _here(monkeypatch):
    """Presence is the file being there (the real sizes are tens of gigabytes: a test never writes them)."""
    monkeypatch.setattr(ms, "_file_present", lambda root, file: (Path(root) / file["path"]).is_file())


def _put(root: Path, rel: str, size: int = 1_000) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def _row(setup: dict, model_id: str) -> dict:
    return next(item for item in setup["models"] if item["id"] == model_id)


FINAL_FILES = [
    "checkpoints/" + final_tier.CKPT,
    "text_encoders/" + final_tier.TEXT_ENCODER,
    "latent_upscale_models/" + final_tier.LATENT_UPSCALER,
    "upscale_models/" + final_tier.UPSCALER,
]


# ---------------------------------------------------------------- M5: the tier sentence and the heading
def test_the_tier_sentence_is_written_from_the_model_the_final_resolves_to(monkeypatch):
    # conftest pins LTX-2.3: the 12 GB card says so
    twelve = hardware.tier_for_gb(12)["detail"]
    assert "Final is LTX-2.3 22B distilled fp8" in twelve and "LTX-2.5" not in twelve
    # LTX-2.5 installed (final_tier.model reads it): the same card says LTX-2.5, and never the other
    monkeypatch.setenv("XENO_FINAL_MODEL", "ltx25")
    twelve = hardware.tier_for_gb(12)["detail"]
    assert "Final is LTX-2.5 22B distilled int8 at 576×1024" in twelve and "LTX-2.3" not in twelve
    assert "LTX-2.5" in hardware.tier_for_gb(24)["detail"] and "LTX-2.3" not in hardware.tier_for_gb(24)["detail"]
    # a small card names neither: its Final is the Draft
    small = hardware.tier_for_gb(8)["detail"]
    assert "Final needs a 12 GB card" in small and "LTX-2.3" not in small and "LTX-2.5" not in small
    for gb in (8, 12, 24):  # the older pins still hold
        detail = hardware.tier_for_gb(gb)["detail"]
        assert "Draft is LTX-Video 0.9.5" in detail and "Fast Final" in detail and "Turbo" not in detail


def test_the_tier_sentence_reads_the_files_on_disk_when_nothing_forces_a_model(tmp_path, monkeypatch):
    monkeypatch.delenv("XENO_FINAL_MODEL", raising=False)
    monkeypatch.setattr(ms, "models_root", lambda: tmp_path)
    assert hardware.final_model() == "ltx23" and "LTX-2.3" in hardware.tier_for_gb(12)["detail"]
    for folder, name in __import__("xenoform.morph_pass", fromlist=["LTX25_FILES"]).LTX25_FILES:
        _put(tmp_path, f"{folder}/{name}")
    assert hardware.final_model() == "ltx25"
    assert "LTX-2.5" in hardware.tier_for_gb(12)["detail"]
    _tier(monkeypatch, 12)
    setup = ms.inspect_setup(tmp_path)
    assert setup["final"] == {"model": "ltx25", "label": "LTX-2.5"}
    assert "LTX-2.5" in setup["tier"]["detail"]


def test_a_gpu_that_is_not_cuda_reads_gpu_not_recognised_and_a_card_names_its_preset():
    cpu = hardware.tier_for_gb(None)
    assert cpu["heading"] == "GPU not recognised" and cpu["detail"].startswith("GPU not recognised")
    assert "No GPU" not in cpu["detail"] and "CUDA" in cpu["detail"]
    assert "Fine-tune" not in cpu["detail"] and "Tweak → Project · under the hood → GPU" in cpu["detail"]  # the drawer t5 removed
    twelve = hardware.tier_for_gb(12.0)
    assert twelve["heading"] == "12 GB GPU preset" and twelve["vram_label"] == "12.0 GB of video memory"
    assert hardware.tier_for_gb(24)["heading"] == "24 GB+ GPU preset" and hardware.tier_for_gb(8)["heading"] == "8 GB GPU preset"
    assert hardware.resolve_tier("12gb")["heading"] == "12 GB GPU preset"


# ---------------------------------------------------------------- M2: the Final card
def test_the_final_card_lists_every_file_the_final_loads_with_one_total(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    row = _row(ms.inspect_setup(tmp_path), "ltx-23")
    assert [f"{part['folder']}/{part['name']}" for part in row["parts"]] == FINAL_FILES
    assert row["bytes"] == sum(part["bytes"] for part in row["parts"]) and row["size_label"] == "40.0 GB"
    assert row["need_bytes"] == row["bytes"] and row["need_label"] == "40.0 GB" and row["ready"] is False
    # the fp8 file, not the 46 GB full weights: those are an alternative the card does not ask for
    spec = ms.by_id("ltx-23")
    assert spec["files"][0]["optional"] is True and spec["files"][0]["path"].endswith("ltx-2.3-22b-distilled.safetensors")
    assert not any(part["name"] == "ltx-2.3-22b-distilled.safetensors" for part in row["parts"])
    assert row["badge"] == "Final" and "Core" not in row["badge"]


def test_the_final_parts_are_the_ones_the_hugging_face_listings_and_this_machine_agree_on():
    parts = {file["path"].split("/")[-1]: file for file in ms.by_id("ltx-23")["files"]}
    fp8 = parts["ltx-2.3-22b-distilled-fp8.safetensors"]
    assert fp8["url"] == "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-distilled-fp8.safetensors"
    assert fp8["bytes"] == 29531884062 and len(fp8["sha256"]) == 64
    gemma = parts["gemma_3_12B_it_fp4_mixed.safetensors"]
    assert gemma["url"].startswith("https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/")
    assert gemma["bytes"] == 9447702218 and len(gemma["sha256"]) == 64
    upscaler = parts["ltx-2.3-spatial-upscaler-x2-1.1.safetensors"]
    assert upscaler["url"].startswith("https://huggingface.co/Lightricks/LTX-2.3/resolve/main/") and upscaler["bytes"] == 995743560
    esrgan = parts["RealESRGAN_x4plus.pth"]
    assert esrgan["url"] == "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
    assert esrgan["bytes"] == 67040989
    for file in (fp8, gemma, upscaler, esrgan):
        assert file["exact"] is True


def test_a_final_part_counts_under_its_own_name_not_as_a_cousin(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    _here(monkeypatch)
    _put(tmp_path, "checkpoints/ltx-2.3-22b-distilled.safetensors")  # the full weights: the card's slot, not the Final's file
    setup = ms.inspect_setup(tmp_path)
    row = _row(setup, "ltx-23")
    assert row["present"] is True  # some LTX-2.3 checkpoint is installed, as before
    assert row["parts"][0]["present"] is False and row["ready"] is False  # the Final loads the fp8 file by name
    for rel in FINAL_FILES:
        _put(tmp_path, rel)
    row = _row(ms.inspect_setup(tmp_path), "ltx-23")
    assert row["ready"] is True and all(part["present"] for part in row["parts"]) and row["need_bytes"] == 0


def test_comfyuis_own_list_decides_a_final_part_and_a_cousin_does_not_count(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    listing = {"checkpoints": ["ltx-2.3-22b-distilled-fp8.safetensors", "ltx-video-2b-v0.9.5.safetensors"],
               "text_encoders": ["gemma_3_12B_it_fp4_mixed_v2.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors"],
               "latent_upscale_models": ["ltx-2.3-spatial-upscaler-x2-1.1.safetensors"], "upscale_models": ["RealESRGAN_x4plus.pth"]}
    monkeypatch.setattr(ms, "_fetch_listing", lambda base, folder: list(listing.get(folder, [])))
    monkeypatch.setattr(ms, "_LISTED", {})
    setup = ms.inspect_setup(tmp_path, comfy_url="http://127.0.0.1:8188")
    parts = {part["name"]: part["present"] for part in _row(setup, "ltx-23")["parts"]}
    assert parts == {final_tier.CKPT: True, final_tier.TEXT_ENCODER: False, final_tier.LATENT_UPSCALER: True, final_tier.UPSCALER: True}
    assert setup["comfy_answered"] is True and setup["comfy_url"] == "http://127.0.0.1:8188"
    assert _row(setup, "ltx-23")["need_label"] == "9.4 GB"  # only the text encoder is left to fetch


def test_what_a_stopped_download_already_holds_is_not_asked_for_again(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    before = _row(ms.inspect_setup(tmp_path), "ltx-23")["need_bytes"]
    _put(tmp_path, "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors.part", 5_000_000)
    after = _row(ms.inspect_setup(tmp_path), "ltx-23")["need_bytes"]
    assert before - after == 5_000_000


def test_the_final_download_fetches_what_is_missing_in_order_and_checks_each_file(tmp_path, monkeypatch):
    got = []

    def fake(url, dest, *, sha256, expected_bytes, on_progress=None, opener=None):
        got.append((Path(dest).name, url, sha256, expected_bytes))
        if on_progress:
            on_progress(1.0, f"{Path(dest).name} is in place")
        return dest

    monkeypatch.setattr(ms, "download_file", fake)
    monkeypatch.setattr(ms, "disk_free", lambda path: 100 * GB)
    _here(monkeypatch)
    _put(tmp_path, "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors")  # already here
    ms._run_download("ltx-23", tmp_path)
    assert [item[0] for item in got] == [final_tier.CKPT, final_tier.LATENT_UPSCALER, final_tier.UPSCALER]
    assert got[0][2] == ms.by_id("ltx-23")["files"][1]["sha256"] and got[0][3] == 29531884062
    status = ms.download_status("ltx-23")
    assert status["status"] == "done" and status["progress"] == 1.0


def test_a_download_that_does_not_fit_the_drive_says_why_and_never_starts(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    started = []

    class NoThreads:  # the module's own name for threading: the check's thread pool is concurrent.futures' business
        @staticmethod
        def Thread(*args, **kwargs):  # noqa: N802 - the real name
            started.append(kwargs)
            raise AssertionError("a download thread was started")

    monkeypatch.setattr(ms, "threading", NoThreads)
    monkeypatch.setattr(ms, "disk_free", lambda path: int(4.6 * GB))
    setup = ms.inspect_setup(tmp_path)
    row = _row(setup, "ltx-23")
    assert row["why_not"] == "Needs 40.0 GB plus a little spare room; the models drive has 4.6 GB free."
    assert setup["disk"]["free_label"] == "4.6 GB free"
    wan = _row(setup, "wan22-i2v")
    assert "28.6 GB" in wan["why_not"] and "4.6 GB free" in wan["why_not"]
    with pytest.raises(PlainError) as caught:
        ms.start_download("ltx-23", tmp_path)
    assert "plus a little spare room" in str(caught.value)
    assert not started
    # a drive with room: no reason, a model already in place: none either
    monkeypatch.setattr(ms, "disk_free", lambda path: 500 * GB)
    assert _row(ms.inspect_setup(tmp_path), "ltx-23")["why_not"] == ""


def test_a_card_too_small_for_the_final_is_told_so_instead_of_offered_forty_gigabytes(tmp_path, monkeypatch):
    _tier(monkeypatch, 8)
    monkeypatch.setattr(ms, "disk_free", lambda path: 500 * GB)
    row = _row(ms.inspect_setup(tmp_path), "ltx-23")
    assert row["why_not"] == "Final needs a 12 GB card; this one reads as 8 GB, so Final falls back to the Draft."
    with pytest.raises(PlainError):
        ms.start_download("ltx-23", tmp_path)
    _tier(monkeypatch, None)  # a GPU that is not recognised is not a reason to refuse: the user knows their card
    assert _row(ms.inspect_setup(tmp_path), "ltx-23")["why_not"] == ""


# ---------------------------------------------------------------- the LTX-2.5 card
def test_there_is_an_ltx25_card_the_final_uses_when_its_four_files_are_here(tmp_path, monkeypatch):
    from xenoform.morph_pass import LTX25_FILES

    _tier(monkeypatch, 12)
    _here(monkeypatch)
    row = _row(ms.inspect_setup(tmp_path), "ltx-25")
    assert row["manual"] is True and row["badge"] == "Final" and row["ready"] is False and row["present"] is False
    assert [f"{part['folder']}/{part['name']}" for part in row["parts"]] == [f"{folder}/{name}" for folder, name in LTX25_FILES]
    assert row["size_label"] == "38.7 GB" and row["variants"] == [] and row["why_not"] == ""
    assert "gated" in row["detail"] and "Setup does not download them" in row["detail"]
    with pytest.raises(PlainError) as caught:
        ms.start_download("ltx-25", tmp_path)
    assert "gated" in str(caught.value) and "Lightricks/LTX-2.5" in str(caught.value)
    for folder, name in LTX25_FILES[:3]:
        _put(tmp_path, f"{folder}/{name}")
    assert _row(ms.inspect_setup(tmp_path), "ltx-25")["ready"] is False  # three of four is not LTX-2.5
    folder, name = LTX25_FILES[3]
    _put(tmp_path, f"{folder}/{name}")
    row = _row(ms.inspect_setup(tmp_path), "ltx-25")
    assert row["ready"] is True and row["present"] is True and row["need_bytes"] == 0


# ---------------------------------------------------------------- M1: what Make is missing
def test_setup_says_what_make_needs_and_the_button_that_gets_it(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    _here(monkeypatch)
    setup = ms.inspect_setup(tmp_path)
    gate = setup["gate"]
    assert gate["blocked"] is True and gate["reliable"] is True
    assert gate["line"] == "To make videos you need LTX 0.9.5, 11.5 GB" and gate["button"] == "Get the 11.5 GB model"
    assert gate["bytes"] == 6340729500 + 5157348688 and gate["names"] == ["LTX 0.9.5"]
    assert setup["missing_required"] == ["LTX 0.9.5 fast"]
    # one of the two files is here: the line asks only for the rest
    _put(tmp_path, "text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors")
    gate = ms.inspect_setup(tmp_path)["gate"]
    assert gate["line"] == "To make videos you need LTX 0.9.5, 6.3 GB" and gate["button"] == "Get the 6.3 GB model"
    _put(tmp_path, "checkpoints/ltx-video-2b-v0.9.5.safetensors")
    gate = ms.inspect_setup(tmp_path)["gate"]
    assert gate["blocked"] is False and gate["line"] == "" and gate["button"] == "" and gate["bytes"] == 0


def test_the_gate_stays_quiet_when_the_desk_only_guessed_where_the_models_are(tmp_path, monkeypatch):
    # no XENO_MODELS, ComfyUI not answering: "missing" may only mean the desk looked in the wrong folder
    monkeypatch.delenv("XENO_MODELS", raising=False)
    monkeypatch.setattr(ms, "models_root", lambda: tmp_path)
    _tier(monkeypatch, 12)
    gate = ms.inspect_setup()["gate"]
    assert gate["blocked"] is False and gate["reliable"] is False and gate["line"].startswith("To make videos you need")
    # ComfyUI answering makes it a fact again
    monkeypatch.setattr(ms, "_fetch_listing", lambda base, folder: [])
    monkeypatch.setattr(ms, "_LISTED", {})
    assert ms.inspect_setup()["gate"]["blocked"] is True


def test_a_comfyui_that_does_not_answer_costs_the_check_one_timeout_not_one_a_folder(tmp_path, monkeypatch):
    # on Windows a closed port takes the whole 1.5 s: nine folders in turn were 25 s of a Setup page that said nothing
    import threading
    import time

    asked = []
    lock = threading.Lock()

    def slow_down(base, folder):
        with lock:
            asked.append(folder)
        time.sleep(0.5)
        return None

    monkeypatch.setattr(ms, "_fetch_listing", slow_down)
    monkeypatch.setattr(ms, "_LISTED", {})
    _tier(monkeypatch, 12)
    began = time.monotonic()
    setup = ms.inspect_setup(tmp_path, comfy_url="http://127.0.0.1:59999")
    took = time.monotonic() - began
    folders = set(asked)
    assert len(folders) >= 6 and len(asked) == len(folders), asked  # every folder once, none twice
    assert took < 0.5 * len(folders) * 0.6, (took, len(folders))  # in turn they were 0.5 s each (3 s); at once about one, with room for a busy machine
    assert setup["comfy_answered"] is False and setup["checked"].startswith("ComfyUI is not answering")


def test_the_setup_route_asks_the_address_the_header_pings_and_only_an_http_one(monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform.config import load_config
    from xenoform.ui import create_app

    asked = []
    monkeypatch.setattr(ms, "_fetch_listing", lambda base, folder: asked.append(base) or [])
    monkeypatch.setattr(ms, "_LISTED", {})
    client = TestClient(create_app(load_config(None)))
    data = client.get("/api/setup", params={"comfy": "http://10.0.0.7:9000/"}).json()
    assert set(asked) == {"http://10.0.0.7:9000"} and data["comfy_url"] == "http://10.0.0.7:9000" and data["comfy_answered"] is True
    for bad in ("file:///C:/Windows", "ftp://x", "10.0.0.7:9000", ""):  # not an address the desk asks: its own config answers
        asked.clear()
        monkeypatch.setattr(ms, "_LISTED", {})
        assert client.get("/api/setup", params={"comfy": bad}).json()["comfy_url"] == "http://127.0.0.1:8188", bad
        assert set(asked) == {"http://127.0.0.1:8188"}


def test_my_videos_rows_say_whether_a_cut_is_still_rendering(tmp_path, monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from xenoform import ui
    from xenoform.config import load_config

    monkeypatch.setattr(ui, "work_dir", lambda: tmp_path)
    for job_id in ("run00001", "done0002", "edit0003"):  # the animatic of a Make is on disk before the GPU pass ends
        folder = tmp_path / "jobs" / job_id
        folder.mkdir(parents=True)
        (folder / "xenoform.mp4").write_bytes(b"\x00" * 64)
        (folder / "meta.json").write_text(json.dumps({"simple": True, "vibe": "black", "song": "Demo"}), encoding="utf-8")
    monkeypatch.setitem(ui._JOBS, "run00001", {"id": "run00001", "status": "running", "progress": 0.42})
    # a finished cut with an edit running on it (_edit_start: a re-render, a swap, a re-cut) is not rendering: the edit
    # runs where it was started (UI_REVIEW L7), and its card keeps Reopen, Re-render and Copy recipe
    monkeypatch.setitem(ui._JOBS, "edit0003", {"id": "edit0003", "status": "running", "progress": 0.05, "edit": "rerender",
                                               "edit_from": 1, "video_version": 1})
    rows = {row["id"]: row for row in TestClient(ui.create_app(load_config(None))).get("/api/videos").json()["videos"]}
    assert rows["run00001"]["status"] == "running" and rows["run00001"]["progress"] == 0.42
    assert rows["done0002"]["status"] == "done" and rows["done0002"]["progress"] == 1.0
    assert rows["edit0003"]["status"] == "done" and rows["edit0003"]["progress"] == 1.0


def test_the_setup_page_copy_is_in_the_users_words(tmp_path, monkeypatch):
    _tier(monkeypatch, 12)
    setup = ms.inspect_setup(tmp_path)
    assert setup["try_it"] == "The bundled demo needs no model download."  # was "...and the Pynchon register need no..."
    text = " ".join(f"{item.get('detail', '')} {item.get('blurb', '')}" for item in ms.CATALOG) + setup["try_it"]
    assert "live restyle" not in text and "Pynchon" not in text and "no longer" not in text
    assert all(_row(setup, model_id)["blurb"] for model_id in ("ltx-095", "ltx-23", "ltx-25"))
