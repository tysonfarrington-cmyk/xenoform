"""compose spreads the per-shot work over worker processes (24 Oct 2026): the frames are the same as the
serial pass, byte for byte, the order holds through a transition, and the worker count follows the cut."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from xenoform import beatfx
from xenoform.cloud_morph import custom_shots

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")


def _clip(path: Path, seconds: float, colour: str) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=64x112:rate=24:duration={seconds}",
                    "-vf", f"hue=h={abs(hash(colour)) % 360}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _wav(path: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=110:sample_rate=44100:duration={seconds}",
                    "-ac", "2", str(path)], check=True)
    return path


def _decoded_md5(path: Path) -> str:
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v", "-f", "md5", "-"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_look_workers_follow_the_cut(monkeypatch):
    monkeypatch.delenv(beatfx.LOOK_WORKERS_ENV, raising=False)
    assert beatfx.look_workers(100, heavy=True) == 1  # too short to be worth a pool
    assert beatfx.look_workers(5000, heavy=False) == 1  # nothing heavy per frame
    assert 1 <= beatfx.look_workers(5000, heavy=True) <= 6
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "3")
    assert beatfx.look_workers(10, heavy=False) == 3
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "nope")
    assert beatfx.look_workers(100, heavy=True) == 1


def test_parallel_compose_matches_the_serial_pass(tmp_path, monkeypatch):
    n = 8
    clips = [_clip(tmp_path / f"c{i}.mp4", 1.0, f"colour{i}") for i in range(n)]
    audio = _wav(tmp_path / "s.wav", float(n))
    shots = custom_shots({"shots": [{"start": float(i), "end": float(i + 1), "render_s": 2} for i in range(n)]}, float(n))
    beats = [0.25 + k * 0.5 for k in range(2 * n)]
    transitions = [None, None, {"kind": "match-cut", "frames": 8}, None, None, {"kind": "lens-breath", "frames": 6}, None, None]
    kw = dict(aspect="9:16", fx=True, beats=beats, dance_fx="house", stem_orbit=False, size=(64, 112), transitions=transitions, seed=7)
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    serial = beatfx.compose(clips, shots, audio, tmp_path / "serial.mp4", **kw)
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "3")
    parallel = beatfx.compose(clips, shots, audio, tmp_path / "parallel.mp4", **kw)
    assert serial["workers"] == 1 and parallel["workers"] == 3
    assert serial["frames"] == parallel["frames"] == 24 * n
    assert serial["transitions"] == parallel["transitions"] == ["match-cut", "lens-breath"]
    assert serial["centres"] == parallel["centres"]
    assert serial["look"]["frames"] == parallel["look"]["frames"] and serial["look"]["roles"] == parallel["look"]["roles"]
    assert _decoded_md5(tmp_path / "serial.mp4") == _decoded_md5(tmp_path / "parallel.mp4")  # the same picture, frame for frame
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames",
                            "-of", "csv=p=0", str(tmp_path / "parallel.mp4")], capture_output=True, text=True, check=True)
    assert int(probe.stdout.strip()) == 24 * n
