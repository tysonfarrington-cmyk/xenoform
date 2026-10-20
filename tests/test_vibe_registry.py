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


def test_registry_is_big_distinct_and_complete():
    from xenoform import transitions_fx  # noqa: F401  (names must be real transitions)
    from xenoform.transitions_fx import TRANSITIONS

    vibes = ALL
    assert len(vibes) >= 15 and len(REG["vibes"]) >= 10
    ids = [v["id"] for v in vibes]
    assert len(set(ids)) == len(ids)
    assert not set(ids) & {"liquid-gold", "paper-summer", "bloom", "neon-night", "ocean", "cosmic", "black"}
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


def test_each_new_vibe_ships_pool_still_and_clip_pack():
    objects = json.loads((STATIC / "objects" / "objects.json").read_text(encoding="utf-8"))
    pack = json.loads((ROOT / "configs" / "clip_pack.json").read_text(encoding="utf-8"))
    for v in REG["vibes"]:
        vid = v["id"]
        assert len(objects[vid]) >= 8
        for row in objects[vid]:
            assert (STATIC / "objects" / row["file"]).stat().st_size > 8_000
        assert (STATIC / "vibes" / f"{vid}.jpg").stat().st_size > 20_000
        for shot in SHOTS:
            size = (STATIC / "library" / vid / f"{shot}.mp4").stat().st_size
            assert 500 < size < 1_200_000
            assert (STATIC / "library" / vid / f"{shot}.jpg").stat().st_size > 4_000
        assert pack["vibes"][vid]["clips"]


def test_ui_lists_every_vibe():
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    page = (STATIC / "judges.html").read_text(encoding="utf-8")
    for v in REG["vibes"]:
        assert f'id: "{v["id"]}"' in app
        assert f'data-vibe="{v["id"]}"' in page
        assert f"vibes/{v['id']}.jpg" in page


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
