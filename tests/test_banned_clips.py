"""The taste file's banned_clips (Tys, 1 Nov): the Keaton bridge is out (overused, and too low in quality to use), then The
General entirely and Battleship Potemkin with it. The three are on configs/taste.json's banned_clips by their film pack
id and their label, and no clips cut shows them: a folder that still holds the old file, under its pack name or renamed
with its label kept, never plays it. The guardrail leaves them out of the Make with a [taste] line, the cut and the
whole-song plan leave them out too; with no taste file nothing is banned."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xenoform import clip_cut, guardrails, song_plan, taste

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ROOT / "configs" / "taste.json"
DOC = (ROOT / "docs" / "TASTE.md").read_text(encoding="utf-8")
OLD = ["05_potemkin_steps.mp4", "08_general_cannon.mp4", "19_general_bridge.mp4"]


@pytest.fixture()
def shipped(monkeypatch):
    monkeypatch.setenv("XENO_TASTE", str(SHIPPED))
    return taste.load()


def test_the_taste_file_bans_the_three_by_id_and_label(shipped):
    rows = {r["id"]: r for r in taste.banned_clips()}
    assert set(rows) == {"general_bridge", "general_cannon", "potemkin_steps"}
    assert rows["general_bridge"]["label"] == "Keaton bridge" and rows["general_cannon"]["label"] == "Keaton cannon"
    assert rows["potemkin_steps"]["label"] == "Potemkin steps"
    assert all(r["since"] == "2026-11-01" and r["reason"] for r in rows.values())
    raw = json.loads(SHIPPED.read_text(encoding="utf-8"))
    assert [r["id"] for r in raw["banned_clips"]] == ["general_bridge", "general_cannon", "potemkin_steps"]
    # the shipped film pack no longer lists them
    pack = json.loads((ROOT / "configs" / "film_pack.json").read_text(encoding="utf-8"))
    assert not set(rows) & {c["id"] for c in pack["clips"]}


def test_a_clip_is_banned_by_its_pack_id_or_its_label(shipped):
    assert taste.clip_banned({"path": "C:/x/film_pack/19_general_bridge.mp4"})["id"] == "general_bridge"
    assert taste.clip_banned({"path": "D:/clips/general_cannon.mp4"})["id"] == "general_cannon"
    assert taste.clip_banned("C:/x/05_potemkin_steps.mp4")["id"] == "potemkin_steps"
    assert taste.clip_banned({"path": "C:/mine/odessa.mp4", "label": "Potemkin  steps"})["id"] == "potemkin_steps"
    assert taste.clip_banned({"path": "C:/mine/keaton.mp4", "label": "keaton bridge"})["id"] == "general_bridge"
    for fine in ({"path": "C:/x/01_glint_city.mp4", "label": "City lights from orbit"}, {"path": "C:/x/02_bridge.mp4"},
                 {"path": "C:/x/general_bridges.mp4"}, {"path": "C:/x/03_my_general_bridge_party.mp4", "label": "a bridge"}):
        assert taste.clip_banned(fine) is None, fine


def test_with_no_taste_file_nothing_is_banned(monkeypatch, tmp_path):
    monkeypatch.setenv("XENO_TASTE", str(tmp_path / "none.json"))
    assert taste.banned_clips() == [] and taste.clip_banned({"path": "x/19_general_bridge.mp4"}) is None
    clips = [{"path": f"x/{name}"} for name in OLD]
    assert clip_cut.usable(clips) == clips


def test_an_entry_can_be_turned_off(monkeypatch, tmp_path):
    data = json.loads(SHIPPED.read_text(encoding="utf-8"))
    data["banned_clips"][0]["off"] = True
    path = tmp_path / "taste.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("XENO_TASTE", str(path))
    assert taste.clip_banned({"path": "x/19_general_bridge.mp4"}) is None and taste.clip_banned({"path": "x/08_general_cannon.mp4"})


def test_the_guardrail_the_cut_and_the_song_plan_leave_them_out(shipped):
    old = [{"path": f"C:/work/ui/film_pack/{name}", "seconds": 14.0} for name in OLD]
    keep = [{"path": f"C:/work/ui/film_pack/{k:02d}_reel_{k}.mp4", "seconds": 14.0, "label": f"reel {k}", "colour": True}
            for k in range(30, 33)]
    body = {"morph_source": "clips", "own_clips": old + keep, "vibe": "none", "expert": True}
    clean, rep = guardrails.apply(dict(body), duration=60.0)
    assert [c["path"] for c in clean["own_clips"]] == [c["path"] for c in keep]  # under Expert too: a ban is hard
    assert any("[taste] 3 clips the taste file bans left out" in m and "(banned_clips)" in m for m in rep["messages"]), rep
    with taste.collecting() as lines:
        assert clip_cut.usable(old + keep) == keep
    assert lines and lines[0]["ids"] == ["banned_clips"] and "general bridge" in lines[0]["line"]
    # a clips song plans on the clips its Make will show
    features = json.loads((ROOT / "tests" / "fixtures" / "analyses" / "glitch-out.features.json").read_text(encoding="utf-8"))
    state = {"morph_source": "clips", "own_clips": old + keep, "quality_tier": "draft", "aspect": "16:9", "vibe": "none",
             "energy_preset": "dense"}
    planned = song_plan.plan(features, state, drop=139.71, pick=False)
    assert planned["clips"] == len(keep)


def test_the_doc_says_what_the_list_does():
    assert "`banned_clips`" in DOC and "Keaton bridge" in DOC and "Potemkin steps" in DOC
    line = next(x for x in DOC.splitlines() if "`banned_clips`" in x)
    assert "1 Nov" in line
