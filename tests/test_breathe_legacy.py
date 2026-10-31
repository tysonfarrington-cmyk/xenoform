"""Breathe off with Drops off is today's cut (docs/MUSIC_VIDEO_PLAN.md section 3: "Breathe off reproduces today's cut,
the viscous table, one drop, so every existing record re-cuts the same").

``tests/fixtures/legacy_cut.json`` was written by ``build_cases`` on the mainline before the pacing engine (b271454) and
is re-made on a scratch export of each mainline merged in since (contest-rc2 0ef7823, the backdrops stage, which gave
each shot its ``still_kinds``): for seven Makes on the bundled songs (the whole of Glitch Out on a big pool and on a
shipped twelve-still pool, Glitch Out with Speed off-centre, Morphing Wobble whole and as a 30 s window, Ambient whole,
the 20 s clip) it holds what the guardrail did to the body, the plan, the shots the compositor got with every field, the
premium transitions and boundary kinds, the look, the record's chain and styles, and the source frame each output frame
plays. The same Makes with ``breathe: False`` and ``drop_mode: "off"`` must give exactly that, and a re-cut of the
record (with and without the two keys in its ``recut_state``, as an old record has neither) must hand the compositor
what it handed it then. Mock engine, the compositor a spy: no GPU, no ffmpeg."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from xenoform import beatfx, dense, guardrails
from xenoform.cloud_morph import shot_indices

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
DEMO = ROOT / "examples" / "demo.wav"
FIXTURE = ROOT / "tests" / "fixtures" / "legacy_cut.json"
LEGACY = {"breathe": False, "drop_mode": "off"}
COMPOSE_KEYS = ("aspect", "quality", "fx", "overlay", "size", "fps", "dance_fx", "stem_orbit", "macros", "end_card", "seed",
                "adaptive", "transitions", "foreshadow", "boundary_fx", "effects", "tones")
RECORD_KEYS = ("plan_name", "drop", "chain", "morph_style", "morph_styles", "morph_timing", "effects", "smear", "roles",
               "transitions", "boundary_fx", "handoffs_s", "macros", "stills")


def _features(song: str) -> dict:
    return json.loads((SONGS / f"{song}.features.json").read_text(encoding="utf-8"))


def _window(features: dict, start: float, length: float) -> dict:
    """The window a Length Make trims, as the Chain row previews it (ui._chain_for): beats and sections shifted."""
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


BASE = {"vibe": "cosmic", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "seed": 2727}
# name: (song, window start or None, length, the drop beatfx.drop_time found on the bundled mp3, the pool size, state extras)
CASES = {
    "glitch_whole_pool80": ("glitch-out", None, 0, 139.71, 80, {}),
    "glitch_whole_pool12": ("glitch-out", None, 0, 139.71, 12, {}),
    "glitch_speed": ("glitch-out", None, 0, 139.71, 80, {"macros": {"speed": 0.8}}),
    "wobble_whole": ("morphing-wobble", None, 0, 84.42, 80, {}),
    "wobble_window30": ("morphing-wobble", 70.92, 30.0, 13.5, 80, {}),
    "ambient_whole": ("ambient", None, 0, 120.12, 80, {}),
    "short20": ("morphing-wobble-20s", None, 0, 12.79, 12, {}),
}


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


def run_case(name: str, tmp: Path, monkeypatch, extra: dict | None = None) -> dict:
    """One Make of ``CASES[name]`` through the guardrail and ``run_simple`` on the mock engine, and a re-cut of its
    record; what the compositor was handed both times."""
    song, start, length, drop, pool_n, more = CASES[name]
    feats = _features(song)
    directed = _whole(feats) if start is None else _window(feats, start, length)
    body = {**BASE, **more, **(extra or {})}
    guarded, report = guardrails.apply(body, duration=directed["duration"], beats=directed["beats"])
    pool = [{"path": f"s{i:02d}.png", "file": f"cosmic/{i:02d}_thing.jpg", "noun": f"thing {i}", "family": "solids-and-knots"}
            for i in range(pool_n)]
    monkeypatch.setattr(dense, "stills_for", lambda state, n, **kw: ("cosmic", [dict(pool[i % pool_n]) for i in range(n)]))
    monkeypatch.setattr("xenoform.morph_pass.catalogue", lambda: {"cosmic": [{"file": r["file"], "noun": r["noun"]} for r in pool]})
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    monkeypatch.setattr(dense, "find_drop", lambda audio, beats, duration: drop)
    import xenoform.cloud_morph as cm

    def fake_clips(shots, stills, work, w, h):
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
        Path(out).write_bytes(b"mp4")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"],
                "fx": True, "overlay": False, "centres": [], "fps": kw.get("fps") or 24, "look": {"dance_fx": kw.get("dance_fx")},
                "transitions": [], "boundary_fx": {}, "foreshadow": {}, "effects": []}

    monkeypatch.setattr(beatfx, "compose", spy)
    job = tmp / name
    job.mkdir(parents=True, exist_ok=True)
    info = dense.run_simple(directed, DEMO, job / "xenoform.mp4", job, {}, dict(guarded), lambda *a: None, engine="mock")
    made = seen[-1]
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    out = {"morph_count": guarded.get("morph_count", "auto"), "guard": sorted({x["id"] for x in report["applied"]}),
           "compose": made, "record": _round({k: rec.get(k) for k in RECORD_KEYS}),
           "plan_shots": _snap(rec.get("plan_shots") or []),
           "indices": [shot_indices(s, 97).tolist() for s in made["shots"]]}
    # a re-cut of the record with new knobs: the record as this code wrote it, and as an old record (no pacing keys)
    for which in ("recut", "recut_old"):
        rec2 = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
        if which == "recut_old":
            for key in ("breathe", "drop_mode"):
                (rec2.get("recut_state") or {}).pop(key, None)
            (job / "simple" / "simple.json").write_text(json.dumps(rec2), encoding="utf-8")
        dense.recut_from_cache(job, {"macros": {"intensity": 0.7, "chaos": 0.5, "glow": 0.6}, "morph_timing": "beat"})
        out[which] = seen[-1]
        (job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")  # the Make's record again
    assert info["plan_name"] == out["record"]["plan_name"]
    return out


def build_cases(tmp: Path, monkeypatch, extra: dict | None = None) -> dict:
    return {name: run_case(name, tmp, monkeypatch, extra) for name in CASES}


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(CASES))
def test_breathe_off_and_drops_off_is_todays_cut(name, golden, tmp_path, monkeypatch):
    got = json.loads(json.dumps(run_case(name, tmp_path, monkeypatch, LEGACY)))
    want = golden[name]
    for key in ("morph_count", "guard", "record", "plan_shots", "indices"):
        assert got[key] == want[key], f"{name}: {key} differs from today's"
    for which in ("compose", "recut", "recut_old"):
        assert got[which]["clips"] == want[which]["clips"], f"{name}: {which} clips"
        assert got[which]["shots"] == want[which]["shots"], f"{name}: {which} shots"
        assert got[which]["kw"] == want[which]["kw"], f"{name}: {which} compose arguments"
        assert not got[which]["extra"], f"{name}: {which} new compositor switches on in legacy: {got[which]['extra']}"
