"""Moves library: manifest (no mp4s shipped), prompt defaults, 12 GB graph, avoid list. No GPU."""

from __future__ import annotations

import subprocess

from xenoform import moves as mv


def test_manifest_lists_15_clips_with_sources_and_no_files_in_git():
    data = mv.manifest()
    assert len(data["clips"]) == 15 and "redistribut" in data["redistribution_warning"].lower()
    for c in data["clips"]:
        assert c["source_url"].startswith("https://") and c["download"].startswith("https://") and c["attribution"]
        assert c["fit"] in mv.FIT_ORDER
    tracked = subprocess.run(["git", "ls-files", "library/moves"], cwd=mv.ROOT, capture_output=True, text=True).stdout
    assert tracked.strip() == ""
    assert "library/moves/" in (mv.ROOT / ".gitignore").read_text(encoding="utf-8")


def test_best_first_and_avoid_hidden():
    listed = mv.moves()
    assert listed[0]["id"] == "px_8688817"
    assert all(m["fit"] != "avoid" for m in listed)
    assert {"mk_452", "mk_51314"} <= {m["id"] for m in mv.moves(include_avoid=True)}


def test_graph_defaults_keep_mouth_closed_hands_clean_and_fit_12gb():
    g = mv.graph("A woman with freckles", mv.clip("px_8688817"), seed=9)
    pos = g["4"]["inputs"]["text"]
    assert "closed-mouth smile" in pos and "calm expression" in pos and "detailed hands" in pos
    assert "open mouth" in g["5"]["inputs"]["text"] and "blurry hands" in g["5"]["inputs"]["text"]
    s = g["15"]["inputs"]
    assert (s["width"], s["height"], s["length"]) == (480, 832, 81)
    assert g["19"]["inputs"]["noise_seed"] == 9 and g["31"]["class_type"] == "SaveVideo"
    assert "Api" not in "".join(n["class_type"] for n in g.values())


def test_desk_serves_moves_page_and_list():
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app({}))
    assert client.get("/moves").status_code == 200
    data = client.get("/api/moves").json()
    assert data["size"] == "480x832" and data["moves"][0]["id"] == "px_8688817"
    assert client.post("/api/moves/render", data={"move": "px_8688817"}).status_code == 400
