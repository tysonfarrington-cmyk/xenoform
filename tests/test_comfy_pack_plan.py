"""The node pack's planner and morph request (comfy_pack/plan.py, looks.py, stills.py) against the desk's own.

The pack copies the desk's planners so it runs in ComfyUI's Python with no desk installed. These tests run both on the
frozen analyses (tests/fixtures/analyses) and fail when they part: a change to dense, cloud_morph, morph_pass,
morph_style or morph_timing that the pack does not follow shows up here.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfy_pack import looks  # noqa: E402
from comfy_pack import plan as P  # noqa: E402
from comfy_pack import song as S  # noqa: E402
from comfy_pack import stills  # noqa: E402

FROZEN = ROOT / "tests" / "fixtures" / "analyses"
SONGS = sorted(p.name.split(".")[0] for p in FROZEN.glob("*.features.json"))
KEYS = ("start", "end", "seconds", "frames", "render_s", "speed", "ease", "effects", "section", "boundary")


def _song(name: str) -> tuple[dict, float | None]:
    f = json.loads((FROZEN / f"{name}.features.json").read_text(encoding="utf-8"))
    return {"duration": f["duration"], "beats": f["beats"], "sections": f["sections"], "tempo": f.get("tempo")}, S.drop_from_features(f)


def _rows(shots):
    return [{k: s.get(k) for k in KEYS} for s in shots]


@pytest.mark.parametrize("name", SONGS)
@pytest.mark.parametrize("energy,forms,speed", [("dense", "auto", 0.5), ("flow", "auto", 0.5), ("dense", 3, 0.5),
                                                ("flow", 4, 0.5), ("dense", "auto", 0.9), ("flow", "auto", 0.1)])
def test_the_shots_are_the_desks(name, energy, forms, speed):
    from xenoform import dense

    directed, drop = _song(name)
    knobs = {"energy_preset": energy, "morph_count": forms, "macros": {"speed": speed}}
    # the pack plans as the desk does with the pacing engine off (Breathe and Drops off)
    desk, desk_plan = dense.shots_for({**knobs, "breathe": False, "drop_mode": "off"}, directed, None, drop=drop)
    pack, pack_plan = P.shots_for(knobs, directed, drop=drop)
    assert _rows(pack) == _rows(desk)
    assert pack_plan.get("name") == desk_plan.get("name")
    assert pack_plan.get("drop") == desk_plan.get("drop")


@pytest.mark.parametrize("name", SONGS)
def test_the_long_song_chain_is_the_desks(name):
    from xenoform import dense

    directed, drop = _song(name)
    state = {"energy_preset": "dense", "breathe": False, "drop_mode": "off"}
    shots, _ = dense.shots_for(state, directed, None, drop=drop)
    for pool in (12, 28):
        desk = dense.clip_plan(shots, directed["duration"], directed["beats"], pool=pool)
        pack = P.clip_plan(shots, directed["duration"], directed["beats"], pool=pool)
        assert pack == desk
        if not desk["fits"]:
            want = dense.fit_chain(state, directed, None, desk, pool, "draft", drop=drop)
            got = P.fit_chain({"energy_preset": "dense"}, directed, pack, pool, "draft", drop=drop)
            assert _rows(got[0]) == _rows(want[0]) and got[2] == want[2]


def test_the_knobs_shape_the_shots_as_the_desks():
    from xenoform import dense

    directed, drop = _song("morphing-wobble-20s")
    for chaos, intensity in ((0.1, 0.2), (0.3, 0.5), (0.7, 0.9), (0.9, 1.0)):
        m = {"intensity": intensity, "speed": 0.5, "chaos": chaos, "glow": 0.4}
        shots, _ = dense.shots_for({"energy_preset": "dense"}, directed, None, drop=drop)
        desk = dense.apply_macros(json.loads(json.dumps(shots)), m)
        pack = P.apply_macros(json.loads(json.dumps(shots)), m)
        assert pack == desk
    assert P.macros({"macros": {"chaos": 3, "speed": "x"}}) == dense.macros({"macros": {"chaos": 3, "speed": "x"}})


def test_styles_and_timing_are_the_desks():
    from xenoform import morph_style, morph_timing

    for name in SONGS:
        directed, drop = _song(name)
        shots, plan = P.shots_for({"energy_preset": "dense"}, directed, drop=drop)
        for chaos in (0.1, 0.3, 0.6, 0.9):
            assert looks.auto_styles(shots, plan.get("drop"), chaos) == morph_style.auto(shots, plan.get("drop"), chaos)
        for mode in ("smooth", "beat", "snap"):
            a, b = json.loads(json.dumps(shots)), json.loads(json.dumps(shots))
            assert looks.plan_timing(a, mode, directed["beats"], plan.get("drop")) == morph_timing.plan(b, mode, directed["beats"], plan.get("drop"))
            assert a == b


def test_the_prompt_the_length_and_the_tuning_are_morph_passs():
    from xenoform import morph_pass as mp
    from xenoform import vibes

    kinds = [("object", "object"), ("scene", "object"), ("object", "scene"), ("setting", "setting"), ("object", "setting"),
             ("setting", "object"), ("scene", "scene")]
    for vibe in vibes.ids()[:40] + ["no-such-vibe"]:
        assert looks.look_of(vibe) == mp.VIBE_LOOK.get(vibe, mp.VIBE_LOOK["liquid-gold"]), vibe
        assert looks.tuned(vibe) == mp.tuned(vibe), vibe
        for k in kinds:
            for style in looks.STYLES:
                assert looks.prompt_for(vibe, k, style) == mp.prompt_for(vibe, "ltx095", k, style), (vibe, k, style)
    assert looks.NEGATIVE == mp.NEGATIVE
    assert [looks.gen_length(n) for n in range(0, 200, 7)] == [mp.gen_length(n) for n in range(0, 200, 7)]
    for value in (0, 18, 30):
        for k in kinds:
            assert looks.guide_compression(k, value) == mp.guide_compression(k, value)
    assert looks.bad_pairs() == {tuple(p) for p in mp.autotune().get("bad_pairs") or []}


def test_the_chain_walk_and_the_bad_pairs_are_morph_passs():
    from xenoform import morph_pass as mp

    pool = [{"file": f"v/{i:02d}.jpg", "noun": f"n{i}"} for i in range(7)]
    for count in (0, 1, 3, 7, 8, 15, 30):
        assert stills.chain_walk(pool, count) == mp.chain_walk(pool, count)
    bad = {("v/00.jpg", "v/01.jpg"), ("v/02.jpg", "v/03.jpg")}
    assert stills.drop_bad_pairs(pool, bad) == mp._drop_bad_pairs(pool, bad)


def test_merge_and_stretch_are_the_desks():
    from xenoform import dense

    directed, drop = _song("liquid-dnb")
    shots, _ = dense.shots_for({"energy_preset": "dense", "breathe": False, "drop_mode": "off"}, directed, None, drop=drop)
    for n in (5, 12, 30):
        assert P.merge_to(shots, n) == dense._merge_to(shots, n)
    assert P.stretch(shots[:6], 30.0) == dense._stretch(shots[:6], 30.0)


def test_the_pack_data_is_the_repositorys():
    """The copies the pack folder carries (comfy_pack/data, comfy_pack/objects) are what sync_bundle would write now."""
    import subprocess
    import sys

    got = subprocess.run([sys.executable, str(ROOT / "comfy_pack" / "tools" / "sync_bundle.py"), "--check"],
                         capture_output=True, text=True)
    assert got.returncode == 0, got.stdout + got.stderr
    bundled = json.loads((ROOT / "comfy_pack" / "objects" / "objects.json").read_text(encoding="utf-8"))
    shipped = json.loads((ROOT / "src" / "xenoform" / "ui_static" / "objects" / "objects.json").read_text(encoding="utf-8"))
    for vibe, rows in bundled.items():
        assert rows == shipped[vibe][: len(rows)]
