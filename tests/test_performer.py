"""xenoform.performer: grid, prompts, availability parsing, sync score, and render_slot with a fake client.

No GPU and no ComfyUI: the client is a stub that answers with ffmpeg-made colour clips, the
availability lists are literal, and the "ComfyUI" URL in the config points at a closed port.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import performer as p

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")

FULL = {
    "diffusion_models": [p.UNET, "other.safetensors"],
    "text_encoders": [p.TEXT_ENCODER],
    "vae": [p.VIDEO_VAE, p.AUDIO_VAE],
    "loras": ["sub\\" + p.LORA, "wan.safetensors"],
}
CLOSED = {"comfy": {"base_url": "http://127.0.0.1:9", "proxy_url": ""}}  # nothing listens: polls fail fast


# --------------------------------------------------------------------------- grid, prompts, estimates

def test_grid_frames_snaps_to_h3_lengths():
    assert p.GRID == [124, 141, 158, 175, 192, 209, 226, 243, 260]
    assert p.FPS == 24 and p.SIZE == (480, 832) and p.MIN_SECONDS == pytest.approx(124 / 24)
    assert p.grid_frames(5.17) == 124  # 5.17 s is the rounded 124-frame length, not 125 frames
    assert p.grid_frames(124 / 24) == 124
    assert p.grid_frames(5.0) == 124
    assert p.grid_frames(0) == 124
    assert p.grid_frames(5.3) == 141
    assert p.grid_frames(8.0) == 192
    assert p.grid_frames(30) == 260  # capped at the longest length the desk uses


def test_prompt_for_roles_and_look():
    look = "molten gold and liquid mercury, warm amber studio glow"
    for role in ("drop", "build", "drop_late"):
        s = p.prompt_for(role, look)
        assert "drum kit" in s and "microphone" not in s
        assert "first frame" in s and "already playing" in s and look in s
    for role in ("intro", "calm", "sustain", "release", "outro"):
        s = p.prompt_for(role, look)
        assert "synthesizer keyboard" in s and "drum" not in s and look in s  # quiet roles play keys unless the vocal stem sings
    assert "drum kit" in p.prompt_for("calm", look, instrument="drums")
    assert "electric guitar" in p.prompt_for("drop", look, instrument="guitar")
    assert p.prompt_for("drop", "").endswith("no speech.")
    assert "Look:" not in p.prompt_for("drop", "")


def test_estimate_seconds_grows_with_steps_and_length():
    assert p.estimate_seconds(5.17, 8) < p.estimate_seconds(5.17, 20)
    assert p.estimate_seconds(5.17, 8) < p.estimate_seconds(8.0, 8)
    assert 60 < p.estimate_seconds(5.17, 8) < 600
    assert p.estimate_seconds(5.17, None) == p.estimate_seconds(5.17, p.STEPS_TURBO)  # the desk's estimate asks without the step count
    assert p.estimate_seconds(5.17, 8) == pytest.approx(192 + 0.193 * 8 * 175, abs=1)  # 124 frames plus the two-second pre-roll


def test_default_reference_is_the_polly_still(tmp_path, monkeypatch):
    ref = p.default_reference()
    assert ref.name in {"polly.png", "polly_576.png"}
    # posed stills beside polly.png are picked by the performance (voice -> vocals); a missing pose falls back
    for name in ("polly.png", "polly_drums.png", "polly_vocals.png", "polly_dance.png", "polly_dance_2.png", "polly_dancer_x.png"):
        (tmp_path / name).write_bytes(b"png")
    monkeypatch.setattr(p, "STILL", tmp_path / "polly.png")
    assert p.default_reference("drums").name == "polly_drums.png"
    assert p.default_reference("voice").name == "polly_vocals.png"
    assert p.default_reference("keys").name == "polly.png" and p.default_reference(None).name == "polly.png"
    # numbered variants rotate with the slot index; an unrelated name that shares the prefix is not a variant
    assert [p.default_reference("dance", k).name for k in range(3)] == ["polly_dance.png", "polly_dance_2.png", "polly_dance.png"]


# --------------------------------------------------------------------------- availability

def test_parse_available_full_set_uses_the_turbo_lora():
    a = p._parse_available(FULL)
    assert a["ok"] and a["model"] and a["text_encoder"] and a["video_vae"] and a["audio_vae"]
    assert a["lora"] == p.LORA and a["steps"] == 8 and a["missing"] == []
    assert "turbo" in a["note"]


def test_parse_available_without_lora_falls_back_to_20_steps():
    lists = dict(FULL, loras=["wan.safetensors"])
    a = p._parse_available(lists)
    assert a["ok"] and a["lora"] is None and a["steps"] == 20
    assert "without" in a["note"]


def test_parse_available_reports_missing_files_and_dead_server():
    lists = dict(FULL, text_encoders=[], vae=[p.VIDEO_VAE])
    a = p._parse_available(lists)
    assert not a["ok"] and a["missing"] == [p.TEXT_ENCODER, p.AUDIO_VAE]
    assert p.TEXT_ENCODER in a["note"]
    dead = p._parse_available(None)
    assert not dead["ok"] and dead["lora"] is None and dead["steps"] == 20 and "ComfyUI" in dead["note"]


def test_available_caches_for_a_minute(monkeypatch):
    p._CACHE.clear()
    calls = []

    def fetch(cfg):
        calls.append(cfg)
        return FULL

    first = p.available(CLOSED, fetch=fetch)
    assert first["ok"] and len(calls) == 1
    monkeypatch.setattr(p, "_fetch_model_lists", lambda cfg, timeout=4.0: None)
    again = p.available(CLOSED)  # served from the cache, the dead fetch is not consulted
    assert again["ok"] and again["lora"] == p.LORA
    stale = p.available(CLOSED, max_age=0)
    assert not stale["ok"]
    p._CACHE.clear()


# --------------------------------------------------------------------------- clip stubs

def _song(path: Path, seconds: float = 12.0) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=44100:duration={seconds}",
                    "-ac", "2", str(path)], check=True)
    return path


def _clip(path: Path, frames: int, flashes: list[int] | None = None, size=(64, 112), fps: int = 24) -> Path:
    """A grey clip whose centre patch flashes white for one frame at each frame in ``flashes``
    (a stroke, not a full-frame cut), with silent stereo audio."""
    w, h = size
    pix = np.full((frames, h, w), 60, dtype=np.uint8)
    for f in flashes or []:
        if 0 <= f < frames:
            pix[f, h // 2 - 12:h // 2 + 12, w // 2 - 12:w // 2 + 12] = 230
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                    "-f", "lavfi", "-t", f"{frames / fps + 0.1:.3f}", "-i", "anullsrc=r=32000:cl=stereo",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
                   input=pix.tobytes(), check=True)
    return path


def _audio_rms(path: Path) -> float:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    return float(np.sqrt((x ** 2).mean())) if len(x) else 0.0


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


# --------------------------------------------------------------------------- sync score

def test_sync_score_flashing_clip(tmp_path):
    beats = [0.3 + k * (60 / 90) for k in range(8)]  # 90 bpm, like the test song
    beat_frames = [int(round(b * 24)) for b in beats]
    locked = _clip(tmp_path / "locked.mp4", 124, beat_frames)
    off = _clip(tmp_path / "off.mp4", 124, [f + 8 for f in beat_frames])  # half a beat late
    still = _clip(tmp_path / "still.mp4", 124, [])
    assert p.sync_score(locked, beats) >= 0.8
    assert p.sync_score(off, beats) <= 0.2
    assert p.sync_score(still, beats) == 0.0
    assert p.sync_score(locked, []) == 0.0
    assert p.sync_score(locked, [b + 100 for b in beats]) == 0.0  # no beat inside the clip


def test_diagnose_sees_a_held_still_and_a_hard_cut():
    motion = np.array([0.1] * 9 + [134.0] + [6.0] * 50, dtype=np.float32)
    d = p.diagnose(motion)
    assert d["freeze_s"] == pytest.approx(9 / 24, abs=0.01)
    assert d["cuts"] == [10]
    assert p.diagnose(np.full(100, 6.0, dtype=np.float32)) == {"freeze_s": 0.0, "cuts": []}


# --------------------------------------------------------------------------- render_slot with a fake client

class _Out:
    type = "video"

    def __init__(self, src: Path):
        self.src = src

    def to_file(self, dest: str):
        shutil.copyfile(self.src, dest)


class _Wf:
    def __init__(self, graph: dict):
        self.json = graph

    def set_input(self, nid, field, value):
        self.json.setdefault(nid, {}).setdefault("inputs", {})[field] = value


class _Job:
    id = "fake"

    def __init__(self, src: Path):
        self.src = src

    def result(self):
        src = self.src

        class R:
            outputs = []

            def get_outputs(self, nid):
                return [_Out(src)] if nid == p.N_SAVE else []

        return R()


class FakeClient:
    """Answers each submit with the next stub clip; records the graphs it was given."""

    def __init__(self, clips: list[Path]):
        self.clips = list(clips)
        self.submits: list[dict] = []
        self.assets = self
        self.workflows = self

    def from_file(self, path):
        if str(path).endswith(".json"):
            return _Wf(json.loads(Path(path).read_text(encoding="utf-8")))
        return f"asset:{Path(path).name}"

    def submit(self, wf, api_key=None):
        self.submits.append(json.loads(json.dumps(wf.json)))
        return _Job(self.clips.pop(0))


@pytest.fixture
def song(tmp_path):
    return _song(tmp_path / "song.wav")


def _turbo(monkeypatch):
    monkeypatch.setattr(p, "available", lambda cfg=None, **kw: dict(p._parse_available(FULL)))


def test_render_slot_trims_and_muxes_the_song(tmp_path, song, monkeypatch):
    _turbo(monkeypatch)
    beats = [2.0 + 0.3 + k * (60 / 90) for k in range(8)]  # song time; the slot starts at t0 = 2.0
    # the song is fed from t0 - 2.0 = 0.0 (the pre-roll), so song time b lands on frame b * 24 of the render
    # a flash at frame 10 stands in for the performance starting inside the pre-roll (a static opening is a held still)
    flashing = _clip(tmp_path / "h3.mp4", 175, [10] + [int(round(b * 24)) for b in beats])  # longer than the slot
    client = FakeClient([flashing])
    events = []
    res = p.render_slot(song, 2.0, 5.17, p.default_reference(), p.prompt_for("drop", "chrome"), tmp_path / "w", CLOSED,
                        seed=11, client=client, beats=beats, report=lambda *a: events.append(a))
    assert res["clip"] == tmp_path / "w" / "performer_2.00.mp4" and res["clip"].exists()
    assert res["frames"] == 124 and res["seconds"] == pytest.approx(124 / 24)
    assert p.count_frames(res["clip"]) == 124
    assert _duration(res["clip"]) == pytest.approx(124 / 24, abs=0.06)
    assert _audio_rms(res["clip"]) > 0.05  # the song's tone, not the stub's silence
    assert res["tries"] == 1 and res["steps"] == 8 and res["lora"] == p.LORA and res["seed"] == 11
    assert res["sync"] >= 0.8 and res["cuts"] == [] and res["freeze_s"] < 0.5
    assert res["render_s"] >= 0 and res["grid_frames"] == 175 and res["skip_frames"] == 48 and res["pre_roll_s"] == 2.0
    assert res["leak_frames"] == 0 and res["drift_frames"] == 0 and res["room_frames"] == 51 and res["gone_frame"] is None
    g = client.submits[0]
    assert g["18"]["class_type"] == "LoraLoaderModelOnly" and g["18"]["inputs"]["lora_name"] == p.LORA
    assert g["19"]["class_type"] == "MiniMaxH3SigmaShift" and g["19"]["inputs"]["shift_video"] == 12.0
    assert g["6"]["inputs"]["model"] == ["19", 0] and g["8"]["inputs"]["model"] == ["19", 0]
    assert g["8"]["inputs"]["steps"] == 8 and g["9"]["inputs"]["noise_seed"] == 11
    assert g["5"]["inputs"]["length"] == 175 and (g["5"]["inputs"]["width"], g["5"]["inputs"]["height"]) == (480, 832)
    assert "drum kit" in g["5"]["inputs"]["prompt"]
    assert g["15"]["inputs"]["image"].startswith("asset:performer_2.00_still") and g["16"]["inputs"]["audio"].startswith("asset:performer_2.00_seg")
    assert events and events[-1][0] == "restyle" and events[-1][1] == 1.0 and "Performer shot" in events[-1][2]
    seg = tmp_path / "w" / "performer_2.00_seg.wav"
    assert _duration(seg) == pytest.approx(175 / 24 + 0.5, abs=0.02)  # the anchored segment runs 0.5 s past the video


def test_render_slot_retries_a_poor_drum_shot_once(tmp_path, song, monkeypatch):
    _turbo(monkeypatch)
    beats = [0.3 + k * (60 / 90) for k in range(8)]
    still = _clip(tmp_path / "still.mp4", 124, [])
    locked = _clip(tmp_path / "locked.mp4", 124, [int(round(b * 24)) for b in beats])
    client = FakeClient([still, locked])
    res = p.render_slot(song, 0.0, 124 / 24, p.default_reference(), p.prompt_for("drop", "chrome"), tmp_path / "w", CLOSED,
                        seed=3, client=client, beats=beats)
    assert res["tries"] == 2 and len(client.submits) == 2
    assert [g["9"]["inputs"]["noise_seed"] for g in client.submits] == [3, 4]
    assert res["seed"] == 4 and res["sync"] >= 0.8 and res["scores"][0] == 0.0
    assert p.count_frames(res["clip"]) == 124


def _frames_clip(path: Path, pix: np.ndarray, fps: int = 24) -> Path:
    """Encode a (frames, h, w) grey array as an mp4 with silent stereo audio."""
    n, h, w = pix.shape
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
                    "-f", "lavfi", "-t", f"{n / fps + 0.1:.3f}", "-i", "anullsrc=r=32000:cl=stereo",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
                   input=np.ascontiguousarray(pix).tobytes(), check=True)
    return path


def _dissolve(path: Path, still_png: Path, frames: int = 175, hold: int = 30, fade: int = 15, size=(64, 112)) -> Path:
    """An image-to-video stand-in: the still (a bright patch at the top) held ``hold`` frames, dissolved over
    ``fade`` frames into a different scene (the patch at the bottom) that then flashes every 8 frames. No
    frame is a hard cut and the dissolve is not a freeze, so only the resemblance to the still sees it."""
    w, h = size
    top = np.full((h, w), 60, dtype=np.float32)
    top[10:34, 20:44] = 230
    bottom = np.full((h, w), 60, dtype=np.float32)
    bottom[70:94, 20:44] = 230
    pix = np.zeros((frames, h, w), dtype=np.float32)
    for i in range(frames):
        a = min(1.0, max(0.0, (i - hold) / float(fade)))
        pix[i] = top * (1 - a) + bottom * a
        if i >= hold + fade and (i - hold - fade) % 8 == 0:
            pix[i, 70:94, 20:44] = 120
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}", "-i", "-",
                    "-frames:v", "1", str(still_png)], input=top.astype(np.uint8).tobytes(), check=True)
    return _frames_clip(path, pix.astype(np.uint8))


def test_still_gone_reads_the_resemblance_curve():
    r = np.array([1.0] * 20 + [0.9, 0.8, 0.7, 0.6, 0.45, 0.3, 0.2] + [0.0] * 60, dtype=np.float32)
    assert p.still_gone(r) == 27  # the settled scene sits at 0: gone at the first of three frames under 0.1 (90 % of the way)
    assert p.still_gone(r, share=0.5) == 24
    assert p.still_gone(np.array([1.0] * 10 + [0.7] * 30, dtype=np.float32)) is None  # the scene keeps resembling the still: in place
    assert p.still_gone(np.full(80, 0.98, dtype=np.float32)) is None  # the picture never leaves the still: a hold, or play in place
    assert p.still_gone(np.array([0.1] * 80, dtype=np.float32)) is None  # the opening frame is not the still
    assert p.still_gone(np.array([1.0] * 3 + [0.0] * 3, dtype=np.float32)) == 3
    assert p.still_gone(np.array([1.0] * 4 + [0.3] * 4 + [0.0] * 4, dtype=np.float32)) == 8  # 0.3 is not far enough along


def test_resemblance_sees_a_dissolve_that_no_cut_or_freeze_would(tmp_path):
    raw = _dissolve(tmp_path / "raw.mp4", tmp_path / "still.png")
    r = p.resemblance(raw, tmp_path / "still.png")
    assert len(r) == 175 and r[0] > 0.95 and r[:30].min() > 0.9 and float(np.median(r[90:])) < 0.3
    gone = p.still_gone(r)
    assert gone is not None and 40 <= gone <= 47  # at the end of the dissolve (frames 30-45), where the ghost of the still has faded
    d = p.diagnose(p.motion_energy(raw))
    assert d["cuts"] == [] and 26 <= round(d["freeze_s"] * 24) <= 32  # the freeze ends when the dissolve starts; no hard cut


def test_render_slot_skips_a_dissolve_by_resemblance(tmp_path, song, monkeypatch):
    _turbo(monkeypatch)
    raw = _dissolve(tmp_path / "raw.mp4", tmp_path / "still.png")
    client = FakeClient([raw])
    res = p.render_slot(song, 0.0, 124 / 24, tmp_path / "still.png", p.prompt_for("calm", "chrome", "keys"), tmp_path / "w", CLOSED,
                        client=client, beats=[0.5, 1.2, 1.9])
    assert res["tries"] == 1 and res["grid_frames"] == 175 and res["pre_roll_s"] == 0.0  # the top of the song: no earlier music
    assert res["gone_frame"] is not None and 40 <= res["gone_frame"] <= 47
    assert res["skip_frames"] == res["gone_frame"] and res["leak_frames"] == 0 and res["drift_frames"] == res["skip_frames"]
    assert p.count_frames(res["clip"]) == 124


def test_render_slot_rerolls_a_shot_whose_still_leaks_whatever_she_plays(tmp_path, song, monkeypatch):
    _turbo(monkeypatch)
    held = _clip(tmp_path / "still.mp4", 124, [])  # never performs: the still would fill the whole slot
    playing = _clip(tmp_path / "playing.mp4", 124, list(range(10, 124, 8)))
    client = FakeClient([held, playing])
    res = p.render_slot(song, 0.0, 124 / 24, p.default_reference(), p.prompt_for("intro", "chrome", "voice"), tmp_path / "w", CLOSED,
                        client=client, beats=[0.5, 1.2, 1.9])
    assert res["tries"] == 2 and res["seed"] == 1 and res["leak_frames"] == 9 and res["clip"].exists()  # the whole shot wins
    assert [g["9"]["inputs"]["noise_seed"] for g in client.submits] == [0, 1]
    # a shot that performs is kept on the first try: singing or not, beats or not
    client = FakeClient([playing, playing])
    res = p.render_slot(song, 0.0, 124 / 24, p.default_reference(), p.prompt_for("intro", "chrome", "voice"), tmp_path / "w2", CLOSED,
                        client=client, beats=[0.5, 1.2, 1.9])
    assert res["tries"] == 1 and res["sync"] is not None
    client = FakeClient([playing, playing])
    res = p.render_slot(song, 0.0, 124 / 24, p.default_reference(), p.prompt_for("drop", "chrome"), tmp_path / "w3", CLOSED,
                        client=client)
    assert res["tries"] == 1 and res["sync"] is None


def test_render_slot_without_the_lora_uses_the_base_graph(tmp_path, song, monkeypatch):
    monkeypatch.setattr(p, "available", lambda cfg=None, **kw: dict(p._parse_available(dict(FULL, loras=[]))))
    client = FakeClient([_clip(tmp_path / "c.mp4", 175, list(range(10, 175, 8)))])  # performs from frame 10: no re-roll
    res = p.render_slot(song, 1.0, 5.17, p.default_reference(), p.prompt_for("calm", "gold"), tmp_path / "w", CLOSED,
                        client=client)
    g = client.submits[0]
    assert len(client.submits) == 1 and res["pre_roll_s"] == 1.0 and res["skip_frames"] == 24  # the song starts 1 s before the slot
    assert "18" not in g and "19" not in g and g["6"]["inputs"]["model"] == ["1", 0]
    assert g["8"]["inputs"]["steps"] == 20 and res["steps"] == 20 and res["lora"] is None
    assert res["frames"] == 124


def test_prompt_sings_only_when_asked_and_pins_the_outfit():
    assert "microphone" in p.prompt_for("intro", "chrome", "voice") and "keys" not in p.prompt_for("intro", "chrome", "voice")
    assert "synthesizer keyboard" in p.prompt_for("intro", "chrome") and "mouth closed" in p.prompt_for("intro", "chrome")
    assert "drum kit" in p.prompt_for("drop", "chrome") and "electric guitar" in p.prompt_for("calm", "", "guitar")
    assert "dancing" in p.prompt_for("calm", "", "dance") and p.OUTFIT in p.prompt_for("drop", "chrome")
