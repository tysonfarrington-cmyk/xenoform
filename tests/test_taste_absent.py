"""With configs/taste.json absent a Make is the mainline's cut, byte for byte (docs/MUSIC_VIDEO_PLAN.md section 4: the taste
file is data the code reads; no file, no rules).

``tests/fixtures/taste_absent_cut.json`` was written by ``build_cases`` on the mainline before the taste file
(contest-rc2 63e039c): for six Makes on the bundled songs (the None vibe on a 30 s window of Glitch Out, liquid gold on the
whole song as made today and as made before the pacing engine at a wild Chaos, cosmic on the 20 s clip at full Chaos with
two effects, the slices and a flash look, black glass under Breathe at a wild Chaos with three effects and a flash look,
the ocean on a 30 s window of Morphing Wobble with the kaleido) it holds what the guardrail said and did to the body, the
stills the pick chose from the shipped pools, the plan, the shots the compositor got with every field, its arguments, the
record, and a re-cut of the record with new knobs. One more Make, the 20 s clip at full Chaos, is composed for real at a
small size on the mock engine's cross-fades: its file's sha256 is in the fixture too.

The same Makes with ``XENO_TASTE`` pointing at no file must give exactly that. The pick is real (the shipped pools, an empty
local library, a fresh usage file a Make); the compositor a spy except in the real case; no GPU."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from xenoform import beatfx, dense, guardrails
from xenoform import cloud_morph as _cm

# the real mock engine and compositor, taken before any test patches them (a case patches both, and a later case in the
# same patch context would otherwise wrap the earlier case's spy)
_REAL_MOCK = _cm._mock_clips
_REAL_COMPOSE = beatfx.compose

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "tests" / "fixtures" / "analyses"  # frozen, so a rebuilt song moves no plan here
DEMO = ROOT / "examples" / "demo.wav"
FIXTURE = ROOT / "tests" / "fixtures" / "taste_absent_cut.json"
COMPOSE_KEYS = ("aspect", "quality", "fx", "overlay", "size", "fps", "dance_fx", "stem_orbit", "macros", "end_card", "seed",
                "adaptive", "transitions", "foreshadow", "boundary_fx", "effects", "tones", "tame")
RECORD_KEYS = ("plan_name", "drop", "chain", "morph_style", "morph_styles", "morph_timing", "effects", "smear", "roles",
               "transitions", "boundary_fx", "handoffs_s", "macros", "stills", "families", "pins", "vibe", "pacing")
RECUT = {"macros": {"intensity": 0.8, "chaos": 0.85, "glow": 0.6}, "morph_timing": "beat", "foreshadow": "slices",
         "effects": ["kaleido", "dither"]}


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


BASE = {"aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "seed": 2727, "auto_grow": False}
WILD = {"chaos": 0.95, "intensity": 0.9, "glow": 0.7}
# name: (song, window start or None, length, the drop the planner is handed, state extras)
CASES = {
    "none_window30": ("glitch-out", 125.0, 30.0, 14.71, {"vibe": "none"}),
    "gold_whole": ("glitch-out", None, 0, 139.71, {"vibe": "liquid-gold"}),
    "gold_whole_legacy_wild": ("glitch-out", None, 0, 139.71, {"vibe": "liquid-gold", "breathe": False, "drop_mode": "off",
                                                               "macros": dict(WILD)}),
    "cosmic_short20_wild": ("morphing-wobble-20s", None, 0, 12.79, {"vibe": "cosmic", "breathe": False, "drop_mode": "off",
                                                                    "macros": dict(WILD), "effects": ["dither", "kaleido"],
                                                                    "foreshadow": "slices", "dance_fx": "cyan-flash"}),
    "black_breathe_wild": ("glitch-out", 125.0, 30.0, 14.71, {"vibe": "black", "breathe": True, "macros": dict(WILD),
                                                              "effects": ["feedback", "kaleido", "slitscan"],
                                                              "dance_fx": "negative-rush"}),
    "ocean_wobble_kaleido": ("morphing-wobble", 60.0, 30.0, 24.42, {"vibe": "ocean", "effects": ["kaleido"],
                                                                    "macros": {"chaos": 0.75}}),
}
REAL_CASE = "cosmic_short20_wild"
REAL_SIZE = (192, 108)


def _round(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {str(k): _round(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(v) for v in value]
    return value


def _snap(shots: list[dict]) -> list[dict]:
    return _round([{k: v for k, v in s.items() if k not in ("clip_path",)} for s in shots])


def run_case(name: str, tmp: Path, monkeypatch, *, real: bool = False) -> dict:
    """One Make of ``CASES[name]`` through the guardrail and ``run_simple`` on the mock engine with the real pick, and a
    re-cut of its record; what the compositor was handed both times (and, ``real``, the composed file's sha256)."""
    song, start, length, drop, more = CASES[name]
    feats = _features(song)
    directed = _whole(feats) if start is None else _window(feats, start, length)
    body = {**BASE, **more}
    library = tmp / f"{name}_library"
    library.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XENO_STILLS", str(library))  # an empty local library and a fresh usage file for each Make
    guarded, report = guardrails.apply(body, duration=directed["duration"], beats=directed["beats"])
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: drop)
    import xenoform.cloud_morph as cm

    def fake_clips(shots, stills, work, w, h):
        if real:
            return _REAL_MOCK(shots, stills, work, 192, 108)
        out = []
        for i in range(len(shots)):
            p = Path(work) / f"m{i:02d}.mp4"
            p.write_bytes(b"clip")
            out.append(p)
        return out

    monkeypatch.setattr(cm, "_mock_clips", fake_clips)
    seen: list[dict] = []

    def spy(clips, shots, audio, out, **kw):
        seen.append({"clips": [Path(c).name for c in clips], "shots": _snap(copy.deepcopy(shots)),
                     "kw": _round({k: copy.deepcopy(kw.get(k)) for k in COMPOSE_KEYS}),
                     "extra": sorted(k for k, v in kw.items() if k not in COMPOSE_KEYS and k not in ("report", "house", "beats",
                                                                                                    "palette_image", "stem_env")
                                     and v not in (None, False, "", [], {}))})
        if real:
            made = _REAL_COMPOSE(clips, shots, audio, out, **{**kw, "size": REAL_SIZE})
            seen[-1]["sha256"] = hashlib.sha256(Path(out).read_bytes()).hexdigest()
            return made
        Path(out).write_bytes(b"mp4")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"],
                "fx": True, "overlay": False, "centres": [], "fps": kw.get("fps") or 24, "look": {"dance_fx": kw.get("dance_fx")},
                "transitions": [], "boundary_fx": {}, "foreshadow": {}, "effects": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    job = tmp / name
    job.mkdir(parents=True, exist_ok=True)
    audio = DEMO
    info = dense.run_simple(directed, audio, job / "xenoform.mp4", job, {}, dict(guarded), lambda *a: None, engine="mock")
    made = seen[-1]
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    out = {"morph_count": guarded.get("morph_count", "auto"), "guard": list(report["messages"]),
           "compose": made, "record": _round({k: rec.get(k) for k in RECORD_KEYS}),
           "plan_shots": _snap(rec.get("plan_shots") or [])}
    if not real:
        dense.recut_from_cache(job, copy.deepcopy(RECUT))
        out["recut"] = seen[-1]
    assert info["plan_name"] == out["record"]["plan_name"]
    return out


def build_cases(tmp: Path, monkeypatch) -> dict:
    """What the fixture holds: every case, and the real composed one."""
    out = {name: run_case(name, tmp, monkeypatch) for name in CASES}
    out["real:" + REAL_CASE] = run_case(REAL_CASE, tmp / "real", monkeypatch, real=True)
    return out


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture()
def no_taste(tmp_path, monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(tmp_path / "no_such_taste.json"))


@pytest.mark.parametrize("name", sorted(CASES))
def test_a_make_with_no_taste_file_is_the_mainlines_cut(name, golden, tmp_path, monkeypatch, no_taste):
    got = json.loads(json.dumps(run_case(name, tmp_path, monkeypatch)))
    want = golden[name]
    for key in ("morph_count", "guard", "record", "plan_shots"):
        assert got[key] == want[key], f"{name}: {key} differs from the mainline's"
    for which in ("compose", "recut"):
        assert got[which]["clips"] == want[which]["clips"], f"{name}: {which} clips"
        assert got[which]["shots"] == want[which]["shots"], f"{name}: {which} shots"
        assert got[which]["kw"] == want[which]["kw"], f"{name}: {which} compose arguments"
        assert got[which]["extra"] == want[which]["extra"], f"{name}: {which} compositor switches"


def test_the_composed_file_with_no_taste_file_is_the_mainlines_byte_for_byte(golden, tmp_path, monkeypatch, no_taste):
    got = json.loads(json.dumps(run_case(REAL_CASE, tmp_path, monkeypatch, real=True)))
    want = golden["real:" + REAL_CASE]
    assert got["compose"]["kw"] == want["compose"]["kw"]
    assert got["compose"]["shots"] == want["compose"]["shots"]
    assert got["compose"]["sha256"] == want["compose"]["sha256"], "the composed mp4 differs from the mainline's"
