import json
from pathlib import Path
from xenoform import vibes
def test_eleven_featured_distinct_and_none():
    """Twelve on the desk's first row: eleven vibes and None. Wet paint left the featured cards on 31 Oct (Tys: its colours
    are "pretty terrible"); it and the odd machine stay in the registry, behind More vibes, with everything they ship."""
    f = [v for v in vibes.every() if v.get("featured", 0) > 0]
    assert len(f) == 12 and f[-1]["id"] == "none"  # Tys, 29 Oct: "in vibes we have an option for none as well"
    assert [v["featured"] for v in f] == list(range(1, 13)) and "wet-paint" not in {v["id"] for v in f}
    assert len({(v["palette"], v["material"]) for v in f}) == 12
    assert sum(1 for v in f if "shell" in (v.get("look", "") + v.get("still_style", "")).lower()) <= 1
    root = Path(vibes.REGISTRY).parents[1] / "src/xenoform/ui_static/vibes"
    assert all((root / f"{v['id']}.jpg").is_file() for v in f)


def test_a_cut_on_the_none_vibe_takes_its_own_stills(tmp_path, monkeypatch):
    from xenoform import dense

    root = Path(__file__).resolve().parents[1]
    plan = [{"start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24, "render_s": 2} for i in range(3)]
    monkeypatch.setattr(dense, "shots_for", lambda state, directed, audio: ([dict(s) for s in plan], {"name": "t", "shots": []}))
    state = {"vibe": "none", "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple"}
    rec = dense.run_simple({"duration": 3.0, "beats": [i * 0.5 for i in range(6)]}, root / "examples" / "demo.wav", tmp_path / "x.mp4",
                           tmp_path, {}, state, lambda *a: None, engine="mock")
    assert rec["vibe"] == "none" and rec["stills"]
    assert all(str(p).replace("\\", "/").startswith("none/") for p in rec["stills"])  # paths run under objects/
