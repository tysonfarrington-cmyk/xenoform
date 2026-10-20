"""The reviewed overnight autotune: shipped, sane, applied to the Simple path, bad pairs kept apart."""

from __future__ import annotations

import json

from xenoform import morph_pass as mp


def test_shipped_autotune_is_within_budget():
    data = json.loads(mp.AUTOTUNE.read_text(encoding="utf-8"))
    assert set(data["vibes"]) >= {"black", "ocean", "cosmic", "bloom", "neon-night", "liquid-gold", "paper-summer"}
    for vibe, s in data["vibes"].items():
        assert 8 <= s["steps"] <= 20 and 1.0 <= s["cfg"] <= 5.0
        assert 0 <= s["img_compression"] <= 40 and 0.5 <= s["guide_end_strength"] <= 1.0
    assert all(e["min_render_s"] < data["time_budget_s_per_morph"] for e in data["evidence"].values())
    assert len(data["bad_pairs"]) == 4


def test_bad_pairs_are_kept_apart_in_either_order():
    pool = [{"file": f} for f in ("a", "b", "c", "d")]
    out = mp._drop_bad_pairs(pool, {("b", "a")})
    files = [o["file"] for o in out]
    assert all({x, y} != {"a", "b"} for x, y in zip(files, files[1:]))


def test_real_pools_avoid_the_four_bad_pairs():
    bad = {frozenset(p) for p in mp.autotune()["bad_pairs"]}
    for vibe in ("ocean", "cosmic", "paper-summer"):
        _, stills = mp.pick_stills({"vibe": vibe}, 12)
        files = [s["file"] for s in stills]
        assert not any(frozenset(p) in bad for p in zip(files, files[1:])), vibe


def test_simple_path_applies_compression_and_end_strength(monkeypatch, tmp_path):
    from xenoform import cloud_morph

    sets = []

    class WF:
        def set_input(self, node, key, value):
            sets.append((node, key, value))

    class Job:
        pass

    class Client:
        class assets:
            @staticmethod
            def from_file(p):
                return p

        class workflows:
            @staticmethod
            def from_file(p):
                return WF()

        def submit(self, wf):
            raise KeyboardInterrupt  # stop after the first graph is filled in

    monkeypatch.setattr(mp, "_graph_path", lambda work, engine: tmp_path / "g.json")
    monkeypatch.setattr(mp, "tuned", lambda vibe: {"steps": 12, "cfg": 4.0, "img_compression": 0, "guide_end_strength": 0.85})
    shots = [{"seconds": 2, "render_s": 2}]
    stills = [{"path": "a.png"}, {"path": "b.png"}]
    try:
        cloud_morph._local_clips(shots, stills, tmp_path, {}, 1, "paper-summer", client=Client())
    except KeyboardInterrupt:
        pass
    got = {(n, k): v for n, k, v in sets}
    assert got[("11", "steps")] == 12 and got[("14", "cfg")] == 4.0
    assert got[("8", "img_compression")] == 0 and got[("21", "img_compression")] == 0
    assert got[("22", "strength")] == 0.85


def test_final_tier_uses_the_vibe_autotune():
    from xenoform import final_tier
    from xenoform.morph_pass import autotune

    v = autotune()["vibes"]["black"]
    t = final_tier.tuned("black")
    assert t == {"img_compression": int(v["img_compression"]), "end_strength": float(v["guide_end_strength"])}
    g = final_tier.graph("x", length=49, seed=1, **t)
    assert g["102"]["inputs"]["img_compression"] == t["img_compression"]
    assert g["111"]["inputs"]["strength"] == t["end_strength"]
