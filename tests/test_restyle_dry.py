import json
from pathlib import Path

import numpy as np

from xenoform.config import load_config
from xenoform.restyle import restyle
from xenoform.video import read_all_frames, write_mp4


def _features(n_frames, fps):
    frames = []
    for i in range(n_frames):
        section = "drop" if i > n_frames // 2 else "calm"
        frames.append(
            {
                "i": i,
                "t": i / fps,
                "energy": 0.8 if section == "drop" else 0.2,
                "onset_env": 0.0,
                "section": section,
                "is_drop": section == "drop",
                "is_beat": i % 6 == 0,
                "beat_env": 1.0 if i % 6 == 0 else 0.0,
            }
        )
    return {
        "fps": fps,
        "n_frames": n_frames,
        "duration": n_frames / fps,
        "beats": [frame["t"] for frame in frames if frame["is_beat"]],
        "sections": [
            {"start_frame": 0, "end_frame": n_frames // 2, "label": "calm"},
            {"start_frame": n_frames // 2, "end_frame": n_frames, "label": "drop"},
        ],
        "frames": frames,
    }


def test_first_frame_defaults_to_ltx_and_wan_stays_optional(monkeypatch):
    from xenoform.hardware import FAST_CHECKPOINT, LARGE_CHECKPOINT
    from xenoform.restyle import build_jobs

    monkeypatch.setattr("xenoform.models_setup.wan_ready", lambda root=None: True)
    features = _features(36, 12)
    for frame in features["frames"]:
        frame["conditioning"] = "first-frame"
    cfg = load_config()
    cfg["quality"] = "draft"
    cfg["segment"] = {"target_seconds": 1.0, "min_seconds": 0.7, "max_seconds": 1.6}
    jobs = build_jobs(features, cfg)
    assert jobs
    assert {job["engine"] for job in jobs} == {"ltx-095"}
    assert all(job["checkpoint_name"] == FAST_CHECKPOINT for job in jobs)
    assert all(abs(job["preserve_strength"] - 0.08) < 1e-9 for job in jobs)

    cfg["comfy"]["checkpoint_name"] = LARGE_CHECKPOINT
    cfg["comfy"]["video_model"] = "ltx-23"
    large = build_jobs(features, cfg)
    assert {job["engine"] for job in large} == {"ltx-23"}
    assert all(job["checkpoint_name"] == LARGE_CHECKPOINT for job in large)

    cfg["comfy"]["video_model"] = "wan"
    wan = build_jobs(features, cfg)
    assert {job["engine"] for job in wan} == {"wan2.2-ti2v"}
    assert all(job["checkpoint_name"] == FAST_CHECKPOINT for job in wan)
    assert all("wan" not in str(job["checkpoint_name"]).lower() for job in wan)

    cfg["quality"] = "turbo"
    cfg["comfy"]["video_model"] = "wan"
    cfg["comfy"]["checkpoint_name"] = LARGE_CHECKPOINT
    turbo = build_jobs(features, cfg)
    assert {job["engine"] for job in turbo} == {"ltx-095"}
    assert all("2.3" not in job["checkpoint_name"] for job in turbo)


def test_dry_run_passthrough_does_not_need_comfy(tmp_path: Path):
    fps = 12
    n = 36
    frames = []
    for i in range(n):
        color = np.zeros((32, 32, 3), dtype=np.uint8)
        color[..., 0] = 20 + i
        frames.append(color)
    video = tmp_path / "base.mp4"
    write_mp4(video, frames, fps, crf=23)
    cfg = load_config()
    cfg["segment"] = {"target_seconds": 1.0, "min_seconds": 0.7, "max_seconds": 1.6}
    cfg["comfy"]["mode"] = "dry-run"
    cfg["comfy"]["width"] = 512
    cfg["comfy"]["height"] = 320
    features = _features(n, fps)
    manifest = restyle(features, video, tmp_path / "chunks", cfg, mode="dry-run")
    assert manifest["mode"] == "dry-run"
    assert manifest["chunks"]
    covered = 0
    for chunk in manifest["chunks"]:
        assert (chunk["length"] - 1) % 8 == 0
        assert chunk["prompt"]
        assert "3.text" in chunk["inputs"]
        path = Path(chunk["output"])
        assert path.exists()
        assert read_all_frames(path).shape[0] == chunk["length"]
        covered += chunk["source_frames"]
        if chunk["section"] == "drop":
            assert chunk["denoise"] > 0.4
    assert covered == n
    # Manifest is the contract a later live run would submit.
    saved = json.loads((tmp_path / "chunks" / "manifest.json").read_text())
    assert saved["note"].startswith("dry-run")
