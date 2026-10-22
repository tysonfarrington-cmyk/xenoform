"""The extended vibe registry, its assets, anchor stills and shot QA."""

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
REG = json.loads((ROOT / "configs" / "vibes.json").read_text(encoding="utf-8"))
ALL = list(REG["vibes"])
REG = {**REG, "vibes": [v for v in ALL if v.get("ready", True)]}
SHOTS = ("wide", "medium", "close", "reveal")
FIELDS = ("id", "name", "line", "look", "negative", "palette", "lighting", "material", "motion", "ltx", "transitions")
BANNED = ("aphex", "tipper", "amon tobin", "sega", "playstation", "ps1", "nintendo", "vaporwave", "hr giger", "giger")


def _pool_backed(vid: str) -> bool:
    """A vibe that ships its own object stills (and so a 4-shot library strip and a clip pack)."""
    return (STATIC / "objects" / vid).is_dir()


def test_registry_is_big_distinct_and_complete():
    from xenoform import transitions_fx  # noqa: F401  (names must be real transitions)
    from xenoform.transitions_fx import TRANSITIONS
    from xenoform.vibes import ORIGINAL

    vibes = ALL
    assert len(vibes) >= 15 and len(REG["vibes"]) >= 10
    ids = [v["id"] for v in vibes]
    assert len(set(ids)) == len(ids)
    # The seven originals keep their hand-tuned entries in morph_pass/autotune; the registry only
    # re-lists one when it is a featured Simple-mode vibe (liquid-gold since UI v6).
    relisted = set(ids) & set(ORIGINAL)
    assert all(next(v for v in vibes if v["id"] == r).get("featured", 0) > 0 for r in relisted), relisted
    looks = [v["look"] for v in vibes]
    assert len(set(looks)) == len(looks)
    for v in vibes:
        for field in FIELDS:
            assert v.get(field), (v["id"], field)
        text = (v["look"] + " " + v["negative"] + " " + v.get("still_style", "")).lower()
        assert not any(word in text for word in BANNED), v["id"]
        assert "shimmer" in v["negative"]
        assert set(v["transitions"]) == {"drop", "switch", "beat", "silence"}
        assert set(v["transitions"].values()) <= set(TRANSITIONS)
        assert 8 <= v["ltx"]["steps"] <= 20 and 1 <= v["ltx"]["cfg"] <= 5


def test_each_ready_vibe_ships_a_hero_still_and_a_usable_pool():
    """Every ready vibe has a picker thumbnail and resolves to an object pool: its own, or the one
    its ``pool`` key names (the look prompt stays the vibe's own; only the guide stills are borrowed).
    A vibe that ships its own pool also ships the 4-shot library strip and a clip pack."""
    from xenoform import vibes

    objects = json.loads((STATIC / "objects" / "objects.json").read_text(encoding="utf-8"))
    pack = json.loads((ROOT / "configs" / "clip_pack.json").read_text(encoding="utf-8"))
    for v in REG["vibes"]:
        vid = v["id"]
        assert (STATIC / "vibes" / f"{vid}.jpg").stat().st_size > 20_000, vid
        pool = vibes.pool(vid)
        assert pool and pool in objects, (vid, "no object pool of its own and no usable `pool` fallback")
        if pool != vid:
            assert v["pool"] == pool and v.get("featured", 0) > 0, (vid, "only featured vibes may borrow a pool")
            continue
        assert len(objects[vid]) >= 8
        for row in objects[vid]:
            assert (STATIC / "objects" / row["file"]).stat().st_size > 8_000
        if vid in vibes.ORIGINAL:
            continue  # the originals' library clips and packs predate clip_pack.json
        for shot in SHOTS:
            size = (STATIC / "library" / vid / f"{shot}.mp4").stat().st_size
            assert 500 < size < 1_200_000
            assert (STATIC / "library" / vid / f"{shot}.jpg").stat().st_size > 4_000
        assert pack["vibes"][vid]["clips"]


def test_borrowed_pool_keeps_the_vibes_own_look(monkeypatch):
    """A registry vibe whose stills are missing borrows the pool its ``pool`` key names, but the
    prompt, negative and tuning stay its own. Every featured vibe ships stills now, so the
    borrowing is simulated by hiding one vibe's pool."""
    from xenoform import morph_pass as mp, vibes

    v = next(v for v in REG["vibes"] if v.get("pool"))
    assert vibes.pool(v["id"]) == v["id"], "ships its own stills; the `pool` key is only a fallback"
    real = mp.manifest()
    hidden = {k: rows for k, rows in real.items() if k != v["id"]}
    monkeypatch.setattr(mp, "manifest", lambda: hidden)
    monkeypatch.setattr(vibes, "pools", lambda: set(hidden))
    assert vibes.pool(v["id"]) == v["pool"]
    assert mp.vibe_for({"vibe": v["id"]}) == v["pool"]
    look_vibe, stills = mp.pick_stills({"vibe": v["id"]}, 3)
    assert look_vibe == v["id"] and len(stills) == 3
    assert all(Path(s["path"]).parent.name == v["pool"] for s in stills)
    assert v["look"] in mp.prompt_for(look_vibe) and v["negative"] == vibes.negative(look_vibe)
    assert vibes.pool("no-such-vibe") == ""


def test_ui_lists_every_vibe():
    """app.js (Simple + Advanced desk) lists every ready vibe; judges.html cuts a pre-rendered
    shot library, so it lists exactly the pool-backed vibes and no vibe whose library is missing."""
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    page = (STATIC / "judges.html").read_text(encoding="utf-8")
    for v in REG["vibes"]:
        vid = v["id"]
        assert f'id: "{vid}"' in app or f'"id": "{vid}"' in app, vid
        listed = f'data-vibe="{vid}"' in page
        assert listed == _pool_backed(vid), (vid, "judges page vs library strip")
        if listed:
            assert f"vibes/{vid}.jpg" in page
    featured = [v for v in REG["vibes"] if v.get("featured", 0) > 0]
    assert len(featured) == 12 and all(f'"id": "{v["id"]}"' in app for v in featured)


def test_morph_pass_uses_the_registry():
    from xenoform import morph_pass as mp
    from xenoform import vibes

    v = REG["vibes"][0]
    assert v["look"] in mp.prompt_for(v["id"])
    assert "every feature appears once" in mp.prompt_for("cosmic")
    assert mp.vibe_for({"vibe": v["id"]}) == v["id"]
    assert mp.tuned(v["id"])["steps"] == v["ltx"]["steps"]
    assert mp.tuned("ocean")["steps"] == 16  # autotune still wins for the originals
    assert "duplicated features" in mp.NEGATIVE
    assert vibes.ids()[:7] == list(vibes.ORIGINAL)
    vibe, stills = mp.pick_stills({"vibe": v["id"]}, 3)
    assert vibe == v["id"] and all(Path(s["path"]).is_file() for s in stills)


def test_real_subjects_use_public_domain_anchor_stills(tmp_path):
    from xenoform import anchors, continuity

    man = json.loads((ROOT / "configs" / "anchors.json").read_text(encoding="utf-8"))
    for name, row in man.items():
        assert "Public domain" in row["licence"] and row["source"].startswith("https://images.nasa.gov/")
        assert (ROOT / row["file"]).stat().st_size > 20_000
    hit = anchors.anchor_for("A storm turns on Jupiter")
    assert hit["name"] == "jupiter"
    assert "two red spots" in anchors.harden_negative("text", "Jupiter at dawn")
    assert anchors.anchor_for("a jupiterish blob") == {}
    rows = continuity.ensure_stills([{"id": "place", "kind": "wide", "sentence": "The planet Jupiter, huge in black space."}], tmp_path)
    assert rows[0]["anchor"] == "jupiter"
    assert Path(rows[0]["still"]).read_bytes() == (ROOT / man["jupiter"]["file"]).read_bytes()
    lib = json.loads((ROOT / "assets" / "library" / "manifest.json").read_text(encoding="utf-8"))
    images = {it["file"]: it for it in lib["items"] if it["kind"] == "image"}
    for row in man.values():
        assert images[row["file"]]["redistribute"] is True and images[row["file"]]["source"] == "nasa"
    from xenoform import footage
    assert not footage.validate(lib) if hasattr(footage, "validate") else True


def test_shot_qa_flags_flicker_and_passes_a_smooth_morph(monkeypatch):
    from xenoform import shot_qa

    monkeypatch.setenv("XENO_QA_CLIP_OFF", "1")
    ramp = np.stack([np.full((18, 32, 3), 60 + i, np.uint8) for i in range(30)])
    assert shot_qa.check(ramp)["ok"]
    strobe = np.stack([np.full((18, 32, 3), 30 if i % 2 else 200, np.uint8) for i in range(30)])
    bad = shot_qa.check(strobe)
    assert not bad["ok"] and bad["reasons"]


def test_planet_check_flags_duplicated_red_spots():
    from xenoform import shot_qa

    disk = np.zeros((90, 160, 3), np.uint8)
    yy, xx = np.mgrid[:90, :160]
    disk[(yy - 45) ** 2 + (xx - 80) ** 2 < 40 ** 2] = (200, 180, 150)
    one = disk.copy()
    one[(yy - 55) ** 2 + (xx - 95) ** 2 < 25] = (220, 40, 30)
    two = one.copy()
    two[(yy - 35) ** 2 + (xx - 65) ** 2 < 25] = (220, 40, 30)
    assert shot_qa.planet_check(np.stack([one] * 3), "jupiter") == []
    assert shot_qa.planet_check(np.stack([two] * 3), "jupiter")
    assert shot_qa.planet_check(np.stack([two] * 3), "") == []


def test_mcp_and_transitions_read_the_registry():
    from xenoform import mcp_tools, transitions_fx

    for v in REG["vibes"]:
        assert v["id"] in mcp_tools.VIBES
        assert transitions_fx.recommend(v["id"], "drop") == v["transitions"]["drop"]
