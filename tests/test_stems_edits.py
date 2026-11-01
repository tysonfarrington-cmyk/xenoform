"""Swap and Re-render on a Stems layer (docs/STEMS_MODE.md, the follow-ups of 1 Nov): the lane's swap and the re-render
variants route to one layer, render that layer's own morphs (the mock engine here), re-cut it, and lay the layers
together again with no GPU; Generate here and Dream stay off on a layer with a plain note. The split is stems.fake_split."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from xenoform import morph_pass, stems_mode
from xenoform import stems_composite as SC

from test_stems_mode import TWO, _stems_make, fake_render, stems_dir  # noqa: F401  (fixtures)


def _layer(job: Path, stem: str) -> dict:
    return json.loads((job / "layers" / stem / "simple" / "simple.json").read_text(encoding="utf-8"))


def _free_still(job: Path, vibe: str = "liquid-gold") -> str:
    taken = set(_layer(job, "drums")["stills"]) | set(_layer(job, "other")["stills"])
    nouns = {str((morph_pass.catalogue().get(vibe) and next((r.get("noun") for r in morph_pass.catalogue()[vibe] if r.get("file") == f), "")) or "")
             for f in taken}
    return next(r["file"] for r in morph_pass.catalogue()[vibe]
                if r.get("file") not in taken and str(r.get("noun") or "") not in nouns and "/" in str(r.get("file")))


def test_a_swap_on_one_layer_renders_its_morphs_and_lays_the_layers_again(tmp_path, fake_render):
    job = tmp_path / "job"
    rec, _rep, _seen, _song = _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = rec["composite"]["sha256"]
    other_before = (job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8")
    file = _free_still(job)
    slot = 2
    from xenoform import dense

    made = len(fake_render["mock"])
    out = stems_mode.layer_edit(job, "drums", lambda d, rep: dense.swap_still(d, slot, file, report=rep), kind="swap",
                                detail={"slot": slot, "file": file})
    drums = _layer(job, "drums")
    assert drums["stills"][slot] == file and len(drums["swaps"]) == 1 and drums["recuts"] == 1
    assert len(fake_render["mock"]) - made == 2  # the two morphs that touch the still: the drums layer's own, only
    assert (job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8") == other_before
    assert out["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4") != before  # laid together again
    assert out["edits"][-1]["layer"] == "drums" and out["edits"][-1]["kind"] == "swap" and out["edits"][-1]["file"] == file
    by = {l["stem"]: l for l in out["layers"]}
    assert by["drums"]["stills"][slot] == file and by["drums"]["recuts"] == 1
    with pytest.raises(ValueError, match="no vocals layer"):
        stems_mode.layer_of(out, "vocals")
    assert stems_mode.taken_elsewhere(out, "other", file) == "drums"  # no object twice across layers
    assert stems_mode.taken_elsewhere(out, "drums", file) == ""


def test_the_desk_swaps_and_re_renders_a_layer_and_refuses_generate_and_dream(tmp_path, fake_render, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui

    work = tmp_path / "work"
    monkeypatch.setattr(ui, "work_dir", lambda: work)
    monkeypatch.delitem(ui._JOBS, "stemedit1", raising=False)  # the desk's jobs are the module's: start and end clean
    job = work / "jobs" / "stemedit1"
    rec, _rep, _seen, _song = _stems_make(tmp_path, job, [dict(l) for l in TWO])
    c = TestClient(ui.create_app())
    lane = c.get("/api/videos/stemedit1/shots").json()
    drums_lane = lane["layers"][0]["lane"]
    assert drums_lane["swappable"] is True and drums_lane["rerenderable"] is True  # a Draft objects layer, as any cut
    assert drums_lane["insertable"] is False and drums_lane["dreamable"] is False
    assert "Generate here and Dream act on one cut" in drums_lane["layer_note"]

    def wait():
        for _ in range(600):
            j = c.get("/api/jobs/stemedit1").json()
            if j["status"] != "running":
                return j
            time.sleep(0.05)
        return j

    file = _free_still(job)
    assert c.post("/api/jobs/stemedit1/swap", json={"slot": 1, "file": file}).status_code == 400  # which layer?
    assert c.post("/api/jobs/stemedit1/swap", json={"slot": 1, "file": file, "layer": "vocals"}).status_code == 400
    theirs = _layer(job, "other")["stills"][1]
    r = c.post("/api/jobs/stemedit1/swap", json={"slot": 1, "file": theirs, "layer": "drums"})
    assert r.status_code == 400 and "in the other layer already" in r.json()["detail"]
    r = c.post("/api/jobs/stemedit1/swap", json={"slot": 1, "file": file, "layer": "drums"})
    assert r.status_code == 200, r.text
    j = wait()
    assert j["detail"] == "Swap ready" and _layer(job, "drums")["stills"][1] == file
    shot = next(i for i, s in enumerate(_layer(job, "other")["shots"]) if not s.get("stem_silent"))
    r = c.post("/api/jobs/stemedit1/rerender", json={"shot": shot, "layer": "other", "seed": 77})
    assert r.status_code == 200 and r.json()["layer"] == "other"
    j = wait()
    assert j["detail"] == "Re-render ready"
    other = _layer(job, "other")
    assert other["rerenders"][-1]["shot"] == shot and other["rerenders"][-1]["seed"] == 77
    saved = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert [e["kind"] for e in saved["edits"]] == ["swap", "rerender"] and saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4")
    for route in ("insert", "dream"):
        r = c.post(f"/api/jobs/stemedit1/{route}", json={"first": 0, "seconds": 2})
        assert r.status_code == 400 and r.json()["detail"] == stems_mode.LAYER_ONLY
    ui._JOBS.pop("stemedit1", None)


def test_the_drawer_routes_swap_and_re_render_to_the_layer_and_says_what_stays_off():
    app = (Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    swap = app.split("async function swapStill(id, slot, file) {", 1)[1].split("\n}\n", 1)[0]
    assert 'if (lane && lane.mode === "stems") swap.layer = lane.layer;' in swap and "JSON.stringify(swap)" in swap
    rerender = app.split("async function rerenderShot(index, style) {", 1)[1].split("\n}\n", 1)[0]
    assert 'if (lane.mode === "stems") body.layer = lane.layer;' in rerender
    drawer = app.split("function timelineDrawer(easy, lane, tl, picked) {", 1)[1].split("\n}\n", 1)[0]
    assert 'lane.insertable === false ? ""' in drawer and "lane.layer_note" in drawer
