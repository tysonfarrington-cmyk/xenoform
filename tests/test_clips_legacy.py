"""Breathe off with Drops off is today's clips cut, byte for byte (Clips mode got the pacing engine on 1 Nov; a clips cut
made before it, and any made with the Shape row on Breathe off and Drops off, comes out as it did).

``tests/fixtures/clips_legacy_cut.json`` was written by ``build_cases`` on a scratch export of the mainline before clips
got the pacing engine (contest-rc2 640488f, ``git archive`` into a temp folder, this file run there with
``XENO_BUILD_CLIPS_FIXTURE=1`` and ``PYTHONPATH`` on the export's ``src``): for four clips Makes on the bundled songs'
analyses (the 20 s clip whole, a 30 s window of Glitch Out at 9:16, Morphing Wobble whole with an effect and a wild
Chaos, the whole of Glitch Out with clips that come round again) it holds what the guardrail did to the body, the shots
the compositor got with every field, its arguments and the files it got, the record's plan, styles, kinds and chain,
and for the 20 s clip the composed file's sha256 (real clips, the mock engine's cross-fades for the morphs, composed
at a small size).

The same Makes now must give exactly that. No GPU; the clips are made here from a seeded noise, so they are the same
bytes on every run."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx, dense, guardrails
from xenoform import cloud_morph as _cm

_REAL_MOCK = _cm._mock_clips
_REAL_COMPOSE = beatfx.compose

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "tests" / "fixtures" / "analyses"  # frozen, so a rebuilt song moves no plan here
DEMO = ROOT / "examples" / "demo.wav"
FIXTURE = ROOT / "tests" / "fixtures" / "clips_legacy_cut.json"
LEGACY = {"breathe": False, "drop_mode": "off"}
COMPOSE_KEYS = ("aspect", "quality", "fx", "overlay", "size", "fps", "dance_fx", "stem_orbit", "macros", "end_card", "seed",
                "adaptive", "transitions", "foreshadow", "boundary_fx", "effects", "tones", "tame")
RECORD_KEYS = ("plan_name", "drop", "morph_style", "morph_styles", "morph_timing", "effects", "smear", "boundary_fx",
               "handoffs_s", "macros", "stills", "source", "vibe", "fps", "size", "seed")
# the clips: (file, seconds, seed); a moving bright bar over seeded noise, so each has a busiest stretch to find
CLIPS = (("01_reel_a.mp4", 3.0, 11), ("02_reel_b.mp4", 5.0, 22), ("03_reel_c.mp4", 6.0, 33), ("04_reel_d.mp4", 4.0, 44),
         ("05_reel_e.mp4", 3.5, 55))
BASE = {"quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "seed": 2727, "morph_source": "clips",
        "auto_grow": False, **LEGACY}
# name: (song, window start or None, length, the drop the planner is handed, clips, state extras)
CASES = {
    "short20": ("morphing-wobble-20s", None, 0, 12.79, 3, {"vibe": "none", "aspect": "16:9"}),
    "glitch_window30": ("glitch-out", 125.0, 30.0, 14.71, 4, {"vibe": "neon-noir", "aspect": "9:16"}),
    "wobble_whole_wild": ("morphing-wobble", None, 0, 84.42, 5, {"vibe": "cosmic", "aspect": "16:9", "effects": ["dither"],
                                                                 "macros": {"chaos": 0.8, "intensity": 0.7}}),
    "glitch_whole": ("glitch-out", None, 0, 139.71, 4, {"vibe": "liquid-gold", "aspect": "16:9"}),
}
REAL_CASE = "short20"
REAL_SIZE = (192, 108)


def _features(song: str) -> dict:
    return json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))


def _window(features: dict, start: float, length: float) -> dict:
    beats = [float(b) for b in features["beats"]]
    earlier = [b for b in beats if b <= start + 1e-6]
    if earlier:
        start = max(earlier)
    end = start + length
    return {"duration": length, "beats": [round(b - start, 4) for b in beats if start <= b < end],
            "sections": [{**s, "start": round(max(0.0, float(s["start"]) - start), 4), "end": round(min(length, float(s["end"]) - start), 4)}
                         for s in features["sections"] if float(s["end"]) > start and float(s["start"]) < end]}


def _whole(features: dict) -> dict:
    return {"duration": float(features["duration"]), "beats": [float(b) for b in features["beats"]],
            "sections": list(features["sections"])}


def make_clips(folder: Path) -> list[dict]:
    """The clips, as own_media.scan lists them."""
    from xenoform.video import write_mp4

    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name, seconds, seed in CLIPS:
        path = folder / name
        if not path.is_file():
            rng = np.random.default_rng(seed)
            base = rng.integers(20, 200, size=3)
            frames = []
            n = int(seconds * 24)
            for k in range(n):
                f = np.clip(rng.normal(base, 30, (72, 128, 3)), 0, 255).astype(np.uint8)
                x = int((k / max(1, n - 1)) * 100) + (seed % 17)
                f[:, x % 120:x % 120 + 8] = 250
                frames.append(f)
            write_mp4(path, frames, 24)
        out.append({"path": str(path), "seconds": float(seconds)})
    return out


def _round(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {str(k): _round(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(v) for v in value]
    return value


def _snap(shots: list[dict]) -> list[dict]:
    return _round(copy.deepcopy(shots))


def run_case(name: str, tmp: Path, monkeypatch, *, real: bool = False) -> dict:
    """One clips Make of ``CASES[name]`` through the guardrail and ``run_simple`` on the mock engine: what the compositor
    was handed and the record (and, ``real``, the composed file's sha256)."""
    song, start, length, drop, n_clips, more = CASES[name]
    feats = _features(song)
    directed = _whole(feats) if start is None else _window(feats, start, length)
    clips = make_clips(tmp / "clips")[:n_clips]
    body = {**BASE, **more, "own_clips": clips}
    guarded, report = guardrails.apply(body, duration=directed["duration"], beats=directed["beats"])
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: drop)
    tiny = tmp / "tiny_morph.mp4"
    if not real and not tiny.is_file():
        _REAL_MOCK([{"render_s": 1}], [{"path": str(_still(tmp, 0))}, {"path": str(_still(tmp, 1))}], tmp, 64, 36)
        shutil.move(str(tmp / "mock00.mp4"), tiny)

    def fake_mock(shots, stills, work, w, h):
        if real:
            return _REAL_MOCK(shots, stills, work, w, h)
        dest = Path(work) / "mock00.mp4"
        shutil.copyfile(tiny, dest)
        return [dest]

    monkeypatch.setattr(_cm, "_mock_clips", fake_mock)
    seen: list[dict] = []

    def spy(clips_, shots, audio, out, **kw):
        seen.append({"clips": [Path(c).name for c in clips_], "shots": _snap(shots),
                     "kw": _round({k: copy.deepcopy(kw.get(k)) for k in COMPOSE_KEYS}),
                     "extra": sorted(k for k, v in kw.items() if k not in COMPOSE_KEYS and k not in ("report", "house", "beats",
                                                                                                    "palette_image", "stem_env")
                                     and v not in (None, False, "", [], {}))})
        if real:
            made = _REAL_COMPOSE(clips_, shots, audio, out, **{**kw, "size": REAL_SIZE})
            seen[-1]["sha256"] = hashlib.sha256(Path(out).read_bytes()).hexdigest()
            return made
        Path(out).write_bytes(b"mp4")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"],
                "fx": True, "overlay": False, "centres": [], "fps": kw.get("fps") or 24, "look": {"dance_fx": kw.get("dance_fx")},
                "transitions": [], "boundary_fx": {}, "foreshadow": {}, "effects": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    job = tmp / name
    job.mkdir(parents=True, exist_ok=True)
    dense.run_simple(directed, DEMO, job / "xenoform.mp4", job, {}, dict(guarded), lambda *a: None, engine="mock")
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    chain = json.loads((job / "simple" / "chain.json").read_text(encoding="utf-8"))
    record = _round({k: rec.get(k) for k in RECORD_KEYS})
    record["clips"] = [Path(c).name for c in rec.get("clips") or []]
    record["chain"] = chain
    return {"morph_count": guarded.get("morph_count", "auto"), "guard": list(report["messages"]), "compose": seen[-1],
            "record": record, "plan_shots": _snap(rec.get("plan_shots") or [])}


def _still(tmp: Path, k: int) -> Path:
    from PIL import Image

    p = tmp / f"tiny{k}.png"
    if not p.is_file():
        Image.new("RGB", (64, 36), (40 + 150 * k, 60, 200 - 120 * k)).save(p)
    return p


def build_cases(tmp: Path, monkeypatch) -> dict:
    """What the fixture holds: every case, and the real composed one."""
    out = {name: run_case(name, tmp / name, monkeypatch) for name in CASES}
    out["real:" + REAL_CASE] = run_case(REAL_CASE, tmp / "real", monkeypatch, real=True)
    return out


@pytest.mark.skipif(not os.environ.get("XENO_BUILD_CLIPS_FIXTURE"), reason="builds the fixture, on a scratch export of the mainline")
def test_build_the_fixture_on_the_mainline(tmp_path, monkeypatch):
    FIXTURE.write_text(json.dumps(build_cases(tmp_path, monkeypatch), indent=1), encoding="utf-8")


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_clips_cut_with_breathe_off_and_drops_off_is_todays(name, golden, tmp_path, monkeypatch):
    got = json.loads(json.dumps(run_case(name, tmp_path / name, monkeypatch)))
    want = golden[name]
    for key in ("morph_count", "guard", "record", "plan_shots"):
        assert got[key] == want[key], f"{name}: {key} differs from the mainline's"
    assert got["compose"]["clips"] == want["compose"]["clips"], f"{name}: the files the compositor got"
    assert got["compose"]["shots"] == want["compose"]["shots"], f"{name}: the shots the compositor got"
    assert got["compose"]["kw"] == want["compose"]["kw"], f"{name}: the compositor's arguments"
    assert got["compose"]["extra"] == want["compose"]["extra"], f"{name}: the compositor's switches"


def test_the_composed_clips_cut_is_the_mainlines_byte_for_byte(golden, tmp_path, monkeypatch):
    got = json.loads(json.dumps(run_case(REAL_CASE, tmp_path / "real", monkeypatch, real=True)))
    want = golden["real:" + REAL_CASE]
    assert got["compose"]["kw"] == want["compose"]["kw"]
    assert got["compose"]["shots"] == want["compose"]["shots"]
    assert got["compose"]["sha256"] == want["compose"]["sha256"], "the composed mp4 differs from the mainline's"
