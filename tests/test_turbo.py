"""Turbo: animatic first, LTX 0.9.5 only, same seed on the way to Final."""

import json
import subprocess
import wave
from pathlib import Path

import pytest

from xenoform.comfy_nodes import XenoformTryIt
from xenoform.config import load_config
from xenoform.director import decode_recipe, empty_state, encode_recipe
from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT, apply_tier, tier_for_gb
from xenoform.lessons import BUILTIN
from xenoform.notes import DEFAULT_SEED, identity, plan_sentence, segment_key
from xenoform.turbo import (
    JobCancelled,
    batch_by_checkpoint,
    eta_table,
    guard_checkpoint,
    render_animatic,
    run_turbo,
)


def _wav(path: Path, seconds: float = 2.0, rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))


def _features(seconds: float = 2.0, fps: int = 12) -> dict:
    count = int(seconds * fps)
    frames = []
    for index in range(count):
        frames.append(
            {
                "i": index,
                "t": index / fps,
                "bass": 0.4,
                "sub": 0.2,
                "mid": 0.3,
                "high": 0.25,
                "onset_env": 0.2,
                "beat_env": 1.0 if index % 6 == 0 else 0.0,
                "mutate": 0.3,
                "section": "drop" if index > count // 2 else "calm",
            }
        )
    return {
        "fps": fps,
        "duration": seconds,
        "n_frames": count,
        "tempo": 120.0,
        "beats": [0.5, 1.0, 1.5],
        "onsets": [0.5, 1.5],
        "sections": [
            {"index": 0, "label": "sphere", "start": 0.0, "end": 1.0},
            {"index": 1, "label": "bulb", "start": 1.0, "end": 2.0},
        ],
        "frames": frames,
    }


def _scenes() -> list[dict]:
    return [
        {
            "index": 0,
            "start": 0.0,
            "end": 1.0,
            "form": "sphere",
            "action": "the sphere holds",
            "shot": "wide",
            "move": "hold",
            "edit": "ribbon",
            "mood": "void",
            "guide": "wide on the sphere",
        },
        {
            "index": 1,
            "start": 1.0,
            "end": 2.0,
            "form": "bulb",
            "action": "the bulb breaks",
            "shot": "close",
            "move": "push in",
            "edit": "dive-splash",
            "mood": "cold",
            "guide": "the bulb hits",
            "retime": {"anchors_s": [[0.4, 0.4], [1.4, 1.25]], "mode": "trim", "speed": "trim"},
            "guide_strengths": {"guide": 0.3, "mid": 0.4, "end": "late"},
        },
    ]


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def test_recipe_roundtrip_keeps_turbo():
    state = empty_state()
    state["quality"] = "turbo"
    code = encode_recipe(state)
    restored = decode_recipe(code)
    assert restored["quality"] == "turbo"
    assert encode_recipe(restored) == code


def test_turbo_tier_never_loads_ltx_23(monkeypatch):
    monkeypatch.setattr("xenoform.hardware._large_model_installed", lambda: True)
    # A machine with only the canonical LTX-2.3 weights: no user pick, no fp8/int8 file.
    monkeypatch.setattr("xenoform.models_setup.chosen_filename", lambda key: None)
    monkeypatch.setattr("xenoform.models_setup.quantised_file", lambda key: "")
    cfg = {
        "fps": 24,
        "render": {"width": 640, "height": 360, "max_steps": 40, "backend": "cpu"},
        "comfy": {"width": 640, "height": 360, "steps": 30},
    }
    turbo = apply_tier(cfg, tier_for_gb(24), quality="turbo")
    assert turbo["comfy"]["checkpoint_name"] == FAST_CHECKPOINT
    assert "2.3" not in turbo["comfy"]["checkpoint_name"]
    assert turbo["render"]["width"] == 384
    assert turbo["render"]["height"] == 224
    assert turbo["comfy"]["height"] % 32 == 0
    assert turbo["comfy"]["steps"] == 4
    final = apply_tier(cfg, tier_for_gb(24), quality="final")
    assert final["comfy"]["checkpoint_name"] == LARGE_CHECKPOINT
    assert final["comfy"]["video_model"] == "ltx-23"
    draft = apply_tier(cfg, tier_for_gb(24), quality="draft")
    assert draft["comfy"]["checkpoint_name"] == LARGE_CHECKPOINT
    smaller = apply_tier(cfg, tier_for_gb(12), quality="final")
    assert smaller["comfy"]["checkpoint_name"] == FAST_CHECKPOINT
    assert smaller["comfy"]["video_model"] == "ltx-095"
    asked = {"fps": 24, "render": {"width": 640, "height": 360, "max_steps": 40, "backend": "cpu"}, "comfy": {"video_model": "wan"}}
    wan = apply_tier(asked, tier_for_gb(24), quality="final")
    assert wan["comfy"]["video_model"] == "wan"
    assert wan["comfy"]["checkpoint_name"] == FAST_CHECKPOINT
    turbo_wan = apply_tier(asked, tier_for_gb(24), quality="turbo")
    assert turbo_wan["comfy"]["video_model"] == "ltx-095"
    assert turbo_wan["comfy"]["checkpoint_name"] == FAST_CHECKPOINT


def test_identity_eta_and_one_resident_batch():
    assert identity("turbo") == ("ltx-095", "384x224")
    assert identity("draft")[1] == "512x288"
    assert identity("final")[1] == "640x360"
    scene = _scenes()[0]
    assert segment_key(scene, DEFAULT_SEED, *identity("turbo")) != segment_key(scene, DEFAULT_SEED, *identity("final"))
    table = eta_table()
    assert table["turbo"]["first_s"] <= 90
    assert table["turbo"]["animatic_s"] <= 15
    assert table["turbo"]["again_s"] < table["draft"]["again_s"] < table["final"]["again_s"]
    assert "LTX-2.3" in table["turbo"]["line"]
    sentence = plan_sentence({"misses": ["s1"], "hits": ["s0"]}, quality="turbo", seed=DEFAULT_SEED)
    assert "384" in sentence
    assert "2.3" not in sentence
    guarded = [
        {"id": "s0", "checkpoint": guard_checkpoint(LARGE_CHECKPOINT)},
        {"id": "s1", "checkpoint": guard_checkpoint("ltx-2.3-22b-distilled.safetensors")},
    ]
    assert all(row["checkpoint"] == FAST_CHECKPOINT for row in guarded)
    assert len(batch_by_checkpoint(guarded)) == 1
    assert "turbo" in XenoformTryIt.INPUT_TYPES()["required"]["quality"][0]


def test_animatic_reuses_unchanged_scenes_and_keeps_the_retime(tmp_path: Path):
    audio = tmp_path / "tone.wav"
    _wav(audio)
    dest = tmp_path / "animatic.mp4"
    cache = tmp_path / "cache"
    features = _features()
    scenes = _scenes()
    first = render_animatic(features, scenes, audio, dest, cache, seed=DEFAULT_SEED, palette="violet", flash=0.18)
    assert first["misses"] == 2
    assert first["hits"] == 0
    assert dest.exists()
    assert abs(_duration(dest) - 2.0) < 0.4
    segment = first["segments"][1]
    assert segment["seed"] == DEFAULT_SEED
    assert segment["noise_seed"] == DEFAULT_SEED + 997
    assert segment["anchors_s"] == [[0.4, 0.4], [1.4, 1.25]]
    assert segment["guide"] == "the bulb hits"
    assert segment["resolution"] == "384x224"
    assert segment["checkpoint"] == FAST_CHECKPOINT
    assert "2.3" not in segment["checkpoint"]

    second = render_animatic(features, scenes, audio, dest, cache, seed=DEFAULT_SEED, palette="violet", flash=0.18)
    assert second["hits"] == 2
    assert second["misses"] == 0
    assert second["paint_s"] == 0.0

    changed = _scenes()
    changed[0]["action"] = "the sphere cracks"
    third = render_animatic(features, changed, audio, dest, cache, seed=DEFAULT_SEED, palette="violet", flash=0.18)
    assert third["misses"] == 1
    assert third["hits"] == 1
    assert third["segments"][1]["anchors_s"] == [[0.4, 0.4], [1.4, 1.25]]


def test_cancel_stops_before_the_picture(tmp_path: Path):
    state = empty_state()
    state["quality"] = "turbo"
    state["scenes"] = []
    with pytest.raises(JobCancelled):
        run_turbo(
            load_config(),
            tmp_path / "missing.wav",
            state,
            tmp_path / "out.mp4",
            tmp_path / "jobs" / "cancel",
            cancel=lambda: True,
        )


def test_demo_animatic_is_the_fast_path(tmp_path: Path):
    audio = Path(__file__).resolve().parents[1] / "examples" / "demo.wav"
    state = empty_state()
    state["quality"] = "turbo"
    state["live"] = False
    state["scenes"] = []
    first_work = tmp_path / "jobs" / "one"
    first = run_turbo(load_config(), audio, state, first_work / "xenoform.mp4", first_work)
    assert first["mode"] == "animatic"
    assert first["checkpoint"] == FAST_CHECKPOINT
    assert "2.3" not in first["checkpoint"]
    assert first["seed"] == DEFAULT_SEED
    assert first["rendered_keyframes"] >= 1
    assert first["seconds"] < 45
    assert abs(_duration(first_work / "xenoform.mp4") - 12.0) < 1.5
    manifest = json.loads((first_work / "turbo.json").read_text())
    assert manifest["resident"] is True
    assert manifest["llm"] == "unloaded"
    assert manifest["keyframe_steps"] == 4
    assert manifest["resolution"] == "384x224"
    assert all("2.3" not in row["checkpoint"] for row in manifest["segments"])
    timing = json.loads((first_work / "timing.json").read_text(encoding="utf-8"))
    assert timing["beats"]
    assert "not stretched" in timing["rule"]
    assert (first_work / "proof.mp4").exists()
    assert _duration(first_work / "proof.mp4") < 6
    assert manifest["proof"]["verdict"] in {"ship", "one more pass"}
    assert (first_work / "xenoform.mp4").exists()

    second_work = tmp_path / "jobs" / "two"
    second = run_turbo(load_config(), audio, state, second_work / "xenoform.mp4", second_work)
    assert second["analysis_cached"] is True
    assert second["rendered_keyframes"] == 0
    assert second["cached_keyframes"] == first["rendered_keyframes"]
    assert second["seconds"] < first["seconds"]
    print(
        f"TIMING animatic_first={first['seconds']:.2f}s paint={first['paint_s']:.2f}s "
        f"replay={second['seconds']:.2f}s scenes={first['chunks']}"
    )


def test_lesson_is_on_the_log():
    text = Path("docs/LESSONS.md").read_text(encoding="utf-8")
    assert "Iteration speed beats polish; draft fast, polish once." in text
    assert any(row["lesson"] == "Iteration speed beats polish; draft fast, polish once." for row in BUILTIN)


def test_twelve_gb_final_uses_an_installed_fp8_ltx23(monkeypatch):
    monkeypatch.setattr("xenoform.models_setup.quantised_file", lambda key: "ltx-2.3-22b-distilled-fp8.safetensors")
    cfg = {
        "fps": 24,
        "render": {"width": 640, "height": 360, "max_steps": 40, "backend": "cpu"},
        "comfy": {"width": 640, "height": 360, "steps": 30},
    }
    final = apply_tier(cfg, tier_for_gb(12), quality="final")
    assert final["comfy"]["checkpoint_name"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    turbo = apply_tier(cfg, tier_for_gb(12), quality="turbo")
    assert turbo["comfy"]["checkpoint_name"] == FAST_CHECKPOINT
