"""Every render can explain itself and be run again from the seed file."""

import json
from pathlib import Path

from xenoform.director_notes import write_director_notes
from xenoform.eligibility import repo_root


def test_shot_list_and_seed_roundtrip(tmp_path: Path):
    state = {
        "seed": 2727,
        "quality": "draft",
        "video_model": "ltx-23",
        "brief": "A rocket's life, from birth to falling back to earth, cold and paranoid.",
        "library_folder": str(repo_root() / "tests" / "fixtures" / "source_library"),
        "exclude_faces": True,
        "allow_pd_us": False,
        "scenes": [
            {"index": 0, "start": 0.0, "end": 2.0, "form": "blob", "beat": "hold", "action": "holds", "prompt": "hold"},
            {
                "index": 1,
                "start": 2.0,
                "end": 4.0,
                "form": "horse",
                "beat": "climax",
                "action": "hits",
                "signature": True,
                "prompt": "drop",
            },
        ],
    }
    features = {
        "fps": 12,
        "sections": [
            {"label": "calm", "start": 0.0, "end": 2.0},
            {"label": "drop", "start": 2.0, "end": 4.0},
        ],
    }
    cfg = {"seed": 2727, "comfy": {"width": 512, "height": 320, "video_model": "ltx-23"}}
    first = write_director_notes(tmp_path, state, features, cfg)
    text = Path(first["shots"]).read_text(encoding="utf-8")
    assert "Seed 2727" in text
    assert "0:00.0" in text
    assert "calm" in text
    assert "drop" in text
    assert "Why" in text
    assert "chain" in text.lower() or "downbeat" in text.lower() or "Hard cut" in text or "Drop" in text
    seed = json.loads(Path(first["seed"]).read_text(encoding="utf-8"))
    assert seed["seed"] == 2727
    assert seed["brief"].startswith("A rocket's life")
    assert len(seed["scenes"]) == 2
    assert seed["sections"][1]["label"] == "drop"
    assert "api_key" not in json.dumps(seed).lower()
    second = write_director_notes(tmp_path, state, features, cfg)
    assert Path(second["seed"]).read_text(encoding="utf-8") == Path(first["seed"]).read_text(encoding="utf-8")
    assert Path(second["shots"]).read_text(encoding="utf-8") == text


def test_missing_job_notes_are_a_404():
    from fastapi.testclient import TestClient

    from xenoform.ui import create_app

    client = TestClient(create_app())
    assert client.get("/api/jobs/no-such-cut/notes").status_code == 404
    assert client.get("/api/jobs/no-such-cut/seed").status_code == 404
