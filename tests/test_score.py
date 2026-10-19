"""Director's Score maps bands to what a section becomes, then one segment can re-render."""

from xenoform.eligibility import repo_root
from xenoform.score import directors_score, stem_role
from xenoform.source_library import load_library
from xenoform.ui import create_app


def _features():
    frames = []
    for i in range(8):
        frames.append(
            {
                "i": i,
                "section": "drop" if i >= 4 else "calm",
                "bass": 0.2 if i < 4 else 0.9,
                "mid": 0.2,
                "high": 0.95 if i < 4 else 0.1,
                "energy": 0.3 if i < 4 else 0.9,
            }
        )
    # A third window is bass-heavy and not a drop.
    for i in range(8, 12):
        frames.append({"i": i, "section": "sustain", "bass": 0.8, "mid": 0.2, "high": 0.1, "energy": 0.4})
    return {
        "fps": 4,
        "frames": frames,
        "sections": [
            {"index": 0, "label": "calm", "start": 0.0, "end": 1.0, "start_frame": 0, "end_frame": 4, "level": 0.2},
            {"index": 1, "label": "drop", "start": 1.0, "end": 2.0, "start_frame": 4, "end_frame": 8, "level": 0.9},
            {"index": 2, "label": "sustain", "start": 2.0, "end": 3.0, "start_frame": 8, "end_frame": 12, "level": 0.4},
        ],
    }


def test_stem_roles():
    assert stem_role("calm", 0.1, 0.2, 0.9) == "impact"
    assert stem_role("drop", 0.9, 0.1, 0.1) == "impact"
    assert stem_role("sustain", 0.8, 0.2, 0.1) == "mass"
    assert stem_role("build", 0.2, 0.7, 0.3) == "hold"


def test_score_names_a_library_pair():
    library = load_library(repo_root() / "tests" / "fixtures" / "source_library")
    rows = directors_score(_features(), library=library, exclude_faces=True, allow_pd_us=False)
    assert [row["role"] for row in rows] == ["impact", "impact", "mass"]
    assert rows[0]["becomes"] == "splash / crystal"
    assert rows[2]["becomes"] == "liquid / metal"
    drop = rows[1]
    assert drop["chain"] is True
    assert drop["source"]
    assert drop["target"]


def test_score_route_uses_cached_features():
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    response = client.post("/api/score", json={"audio_id": "demo", "exclude_faces": True, "allow_pd_us": False})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["segments"])
    assert body["segments"]
    assert body["segments"][0]["role"] in {"impact", "mass", "hold"}
