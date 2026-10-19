"""Source library: load a fixture index, filter licences, pick morph partners."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from xenoform.source_library import (
    attach_library_credits,
    credit_line,
    item_allowed,
    load_library,
    pick_pair,
    poster_path,
    safe_child,
    write_render_credits,
    write_sample_library,
)
from xenoform.ui import create_app

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "source_library" / "library.json"
APP = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "app.js"
HTML = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "index.html"
CSS = Path(__file__).resolve().parents[1] / "src" / "xenoform" / "ui_static" / "app.css"


def _library(tmp_path: Path):
    dest = tmp_path / "library"
    dest.mkdir()
    (dest / "library.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    for rel in ("shapes/gold.png", "shapes/fire.png", "loops/dst.png", "stills/bismuth.png", "gpu/blob.png"):
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"secret")
    return load_library(dest)


def test_missing_index_is_an_empty_library(tmp_path: Path):
    library = load_library(tmp_path / "absent")
    assert library.missing_index is True
    assert library.items == []
    assert "library.json" in library.note


def test_bad_json_does_not_raise(tmp_path: Path):
    folder = tmp_path / "library"
    folder.mkdir()
    (folder / "library.json").write_text("{", encoding="utf-8")
    library = load_library(folder)
    assert library.items == []
    assert library.missing_index is True


def test_unknown_categories_and_missing_files_stay(tmp_path: Path):
    library = _library(tmp_path)
    categories = {item["category"] for item in library.items}
    assert {"gpu_objects", "gpu_morphs", "objects_gr"} <= categories
    missing = {item["id"] for item in library.items if item["missing"]}
    assert "chain_src" in missing
    assert "gpu_warp" in missing
    assert "escaped" in missing
    assert "still_gold" not in missing
    assert library.by_id["chain_src"]["category"] == "loops"


def test_faces_and_pd_us_are_filtered_by_default(tmp_path: Path):
    library = _library(tmp_path)
    face = library.by_id["face_close"]
    reel = library.by_id["pd_us_reel"]
    assert item_allowed(face) is False
    assert item_allowed(face, exclude_faces=False) is True
    assert item_allowed(reel) is False
    assert item_allowed(reel, allow_pd_us=True) is True
    pair = pick_pair(library, vibe="liquid-gold", mood="forge", energy=0.2, beat="setup")
    ids = {pair["source"]["id"], (pair["target"] or {}).get("id")}
    assert "face_close" not in ids
    assert "pd_us_reel" not in ids


def test_drop_prefers_the_precomputed_chain(tmp_path: Path):
    library = _library(tmp_path)
    pair = pick_pair(library, vibe="liquid-gold", mood="forge", energy=0.9, beat="climax", section="drop")
    assert pair["chain"] is True
    assert {pair["source"]["id"], pair["target"]["id"]} == {"chain_src", "chain_dst"}
    assert "drop" in pair["reason"].lower()


def test_calm_prefers_a_still_shape(tmp_path: Path):
    library = _library(tmp_path)
    pair = pick_pair(library, vibe="liquid-gold", mood="forge", energy=0.1, beat="setup", section="calm")
    assert pair["chain"] is False
    assert pair["source"]["id"] == "still_gold"
    assert pair["source"]["motion"] == "static"


def test_pin_and_ban(tmp_path: Path):
    library = _library(tmp_path)
    pinned = pick_pair(
        library,
        vibe="liquid-gold",
        mood="forge",
        energy=0.9,
        beat="drop",
        pinned=["still_gold"],
    )
    assert pinned["source"]["id"] == "still_gold"
    assert pinned["chain"] is True
    assert pinned["target"]["id"] == "decoy_far"
    banned = pick_pair(
        library,
        vibe="liquid-gold",
        mood="forge",
        energy=0.9,
        beat="drop",
        banned=["chain_dst"],
    )
    assert (banned["target"] or {}).get("id") != "chain_dst"
    assert banned["source"]["id"] != "chain_dst"


def test_credits_use_only_fields_on_the_item(tmp_path: Path):
    library = _library(tmp_path)
    line = credit_line(library.by_id["bismuth_credit"])
    assert line is not None
    assert "François Nguyen" in line
    assert "CC BY 2.0" in line
    assert "commons.wikimedia.org" in line
    bare = credit_line(library.by_id["cc_by_bare"])
    assert bare is not None
    assert "author not in the index" in bare
    assert credit_line(library.by_id["still_gold"]) is None
    assert credit_line(library.by_id["pd_us_reel"]) is None
    path = write_render_credits(
        tmp_path / "job",
        [library.by_id["bismuth_credit"], library.by_id["still_gold"], library.by_id["cc_by_bare"]],
    )
    text = path.read_text(encoding="utf-8")
    assert path.name == "CREDITS.md"
    assert "François Nguyen" in text
    assert "author not in the index" in text
    assert "Own work" not in text


def test_poster_cannot_escape_the_folder(tmp_path: Path):
    library = _library(tmp_path)
    assert safe_child(library.folder, "../../outside.png") is None
    assert poster_path(library, library.by_id["escaped"]) is None
    assert poster_path(library, library.by_id["still_gold"]) == library.folder / "shapes" / "gold.png"


def test_render_credits_follow_the_job_folder(tmp_path: Path):
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    (library_dir / "library.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    job = tmp_path / "jobs" / "abc"
    info = attach_library_credits(
        job,
        {
            "library_folder": str(library_dir),
            "vibe": "liquid-gold",
            "exclude_faces": True,
            "allow_pd_us": False,
            "scenes": [{"index": 2, "beat": "climax", "mood": "forge", "start": 4.0, "signature": True}],
            "sections": [{"start": 0, "end": 8, "label": "drop", "level": 0.9}],
        },
    )
    text = (job / "CREDITS.md").read_text(encoding="utf-8")
    assert info["pairs"][0]["chain"] is True
    assert {info["pairs"][0]["source"], info["pairs"][0]["target"]} == {"chain_src", "chain_dst"}
    assert "No CC BY item was used" in text


def test_library_routes_and_the_desk_controls(tmp_path: Path):
    library = _library(tmp_path)
    client = TestClient(create_app())
    missing = client.get("/api/library", params={"folder": str(tmp_path / "nope")})
    assert missing.status_code == 200
    assert missing.json()["count"] == 0
    assert missing.json()["missing_index"] is True
    listed = client.get(
        "/api/library",
        params={"folder": str(library.folder), "exclude_faces": "true", "allow_pd_us": "false"},
    )
    assert listed.status_code == 200
    body = listed.json()
    ids = {item["id"] for item in body["items"]}
    assert "gpu_blob" in ids
    assert "gpu_warp" in ids
    assert "face_close" not in ids
    assert "pd_us_reel" not in ids
    assert "bismuth_credit" in ids
    thumb = client.get("/api/library/thumb", params={"id": "still_gold", "folder": str(library.folder)})
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/")
    escaped = client.get("/api/library/thumb", params={"id": "escaped", "folder": str(library.folder)})
    assert escaped.status_code == 404
    picked = client.post(
        "/api/library/pick",
        json={
            "folder": str(library.folder),
            "vibe": "cosmic",
            "mood": "night",
            "energy": 0.8,
            "beat": "drop",
            "exclude_faces": True,
            "allow_pd_us": False,
        },
    )
    assert picked.status_code == 200
    assert picked.json()["chain"] is True
    html = HTML.read_text(encoding="utf-8")
    assert 'id="library-folder"' in html
    assert 'id="exclude-faces"' in html
    assert "checked" in html.split('id="exclude-faces"', 1)[0][-80:] or 'id="exclude-faces" checked' in html
    assert 'id="allow-pd-us"' in html
    script = APP.read_text(encoding="utf-8")
    assert "library-browser" in script
    assert 'data-act="library-pin"' in script
    assert 'data-act="library-ban"' in script
    easy = script.split("function renderEasy()", 1)[1].split("function placeKey", 1)[0]
    assert "library-browser" not in easy
    css = CSS.read_text(encoding="utf-8")
    assert ".library-grid" in css
    assert "shimmer" not in css


def test_sample_library_is_procedural(tmp_path: Path):
    dest = write_sample_library(tmp_path / "library")
    library = load_library(dest)
    assert len(library.items) == 5
    assert all(item["licence_bucket"] == "own_work_procedural" for item in library.items)
    assert (dest / "shapes" / "blob.png").stat().st_size > 32
    assert (dest / "loops" / "pulse.mp4").stat().st_size > 32
    pair = pick_pair(library, vibe="liquid-gold", mood="forge", energy=0.9, beat="drop")
    assert pair["source"] and pair["target"]
    assert pair["chain"] is True
    blocked = dest / "library.json"
    payload = json.loads(blocked.read_text(encoding="utf-8"))
    payload["items"] = payload["items"] * 4
    blocked.write_text(json.dumps(payload), encoding="utf-8")
    try:
        write_sample_library(dest)
    except RuntimeError as exc:
        assert "Pass --force" in str(exc)
    else:
        raise AssertionError("a large index should be left in place")
