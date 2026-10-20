import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import footage, stem_react

ROOT = Path(__file__).resolve().parents[1]
HAS_FFMPEG = shutil.which("ffmpeg") is not None


def test_manifest_is_valid_and_seeds_exist():
    data = footage.load_manifest()
    assert data["version"] == 1 and len(data["items"]) >= 6
    vibes = {v for it in data["items"] for v in it["vibes"]}
    assert {"cosmic", "ocean", "black", "liquid-gold"} <= vibes
    for it in data["items"]:
        assert it["licence"] and it["attribution"]
        if it["redistribute"]:
            assert footage.local_path(it).is_file(), it["id"]


def test_validate_rejects_redistributed_pexels():
    bad = {"items": [{"id": "x", "kind": "video", "title": "t", "source": "pexels", "source_url": "u",
                      "licence": "Pexels", "vibes": ["ocean"], "redistribute": True}]}
    assert any("cannot be redistributed" in p for p in footage.validate(bad))
    assert footage.validate({"items": [{"id": "y"}]})


def test_by_vibe():
    assert all("ocean" in it["vibes"] for it in footage.by_vibe("ocean"))


def test_plan_edit_cuts_on_grid_and_morph_mode():
    beats = [i * 0.5 for i in range(80)]
    items = [{"path": "a.mp4", "kind": "video"}, {"path": "b.png", "kind": "image", "mode": "morph-into-next"},
             {"path": "c.mp4", "kind": "video"}]
    spec = footage.plan_edit(items, beats, 20.0, vibe="black", bars_per_shot=1, sections=[8.0])
    segs, trs = spec["segments"], spec["transitions"]
    assert len(trs) == len(segs) - 1
    assert abs(sum(s["dur"] for s in segs) - 20.0) < 1e-6
    assert trs[1]["kind"] == "scene-morph"           # after the morph-into-next image
    from xenoform import transitions_fx as T
    assert trs[3]["kind"] == T.recommend("black", "drop")
    with pytest.raises(ValueError):
        footage.plan_edit(items, beats, 10.0, modes={0: "explode"})


def test_animate_graph_loops_one_still():
    g = footage.animate_graph("still.png")
    assert g["100"]["inputs"]["image"] == g["101"]["inputs"]["image"] == "still.png"
    assert "comes alive" in g["4"]["inputs"]["text"]


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_scan_and_detect_scenes(tmp_path):
    clip = tmp_path / "two.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=160x120:d=2", "-f", "lavfi",
                    "-i", "color=blue:s=160x120:d=2", "-filter_complex", "[0][1]concat=n=2:v=1", "-r", "24", str(clip)], check=True)
    (tmp_path / "still.jpg").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("no")
    items = footage.scan_folder(tmp_path)
    assert [i["kind"] for i in items] == ["image", "video"]
    scenes = footage.detect_scenes(str(clip))
    assert len(scenes) == 2 and abs(scenes[0][1] - 2.0) < 0.1


def _env():
    return {"fps": 10, "drums": [0.0, 0.9, 0.1, 0.0, 1.0, 0.0], "bass": [0.2, 0.9, 0.9, 0.1, 0.0, 0.0],
            "other": [0.5] * 6, "vocals": [0.0] * 6, "drum_strong": [0.1, 0.4, 0.45, 2.0]}


def test_stem_routing():
    p = stem_react.drive(_env(), 0.1)
    assert p["stutter"] > 0 and p["scale"] == pytest.approx(0.9)
    assert stem_react.drive(_env(), 0.0)["stutter"] == 0
    assert stem_react.cut_points(_env(), min_gap=1.0) == [0.1, 2.0]
    assert stem_react.cut_points(_env(), [0.0, 0.5, 2.05], min_gap=0.2, max_shift=0.06) == [0.1, 0.4, 2.05]


def test_apply_frame_shape():
    fr = np.random.default_rng(1).integers(0, 255, (64, 36, 3), dtype=np.uint8)
    out = stem_react.apply_frame(fr, _env(), 0.1)
    assert out.shape == fr.shape and out.dtype == np.uint8


def test_librosa_split_and_envelopes(tmp_path):
    sf = pytest.importorskip("soundfile")
    sr = 22050
    t = np.arange(sr * 3) / sr
    y = 0.4 * np.sin(2 * np.pi * 55 * t)
    for k in range(6):
        i = int(k * 0.5 * sr)
        y[i:i + 400] += np.random.default_rng(k).normal(0, 0.8, 400)
    wav = tmp_path / "s.wav"
    sf.write(str(wav), y.astype(np.float32), sr)
    stems = stem_react.split(wav, tmp_path / "st", engine="librosa")
    assert stems["engine"] == "librosa" and all(Path(stems[s]).is_file() for s in stem_react.STEMS)
    env = stem_react.envelopes(stems, fps=24)
    assert env["frames"] > 60 and max(env["bass"]) > 0.5 and len(env["drum_hits"]) >= 3
    p = stem_react.save_envelopes(env, tmp_path / "env.json")
    assert json.loads(p.read_text())["fps"] == 24


def test_vj_page_and_library_api():
    html = (ROOT / "src" / "xenoform" / "ui_static" / "vj.html").read_text(encoding="utf-8")
    for needle in ("getUserMedia", "AnalyserNode" if "AnalyserNode" in html else "createAnalyser", "webgl", "requestFullscreen", "/api/footage"):
        assert needle in html
    try:
        from fastapi.testclient import TestClient
        from xenoform.ui import create_app
    except Exception:
        pytest.skip("desk app factory not importable here")
    c = TestClient(create_app())
    assert c.get("/vj").status_code == 200
    items = c.get("/api/footage", params={"kind": "video"}).json()["items"]
    assert items and all(i["kind"] == "video" for i in items)
    first = next(i for i in items if i["available"])
    assert c.get(first["url"]).status_code == 200
    assert c.get("/library-media/nope").status_code == 404
    tr = c.get("/api/v1/transitions").json()
    assert any(t["id"] == "scene-morph" for t in tr["scene_transitions"])


def test_camera_roll_scores_and_orders(tmp_path):
    from xenoform import camera_roll as CR

    rng = np.random.default_rng(3)
    sharp = rng.integers(0, 255, (96, 96, 3), dtype=np.uint8)
    flat = np.full((96, 96, 3), 128, np.uint8)
    dark = np.zeros((96, 96, 3), np.uint8)
    assert CR.score(sharp)["score"] > CR.score(flat)["score"] > CR.score(dark)["score"] - 1e-9
    red = np.zeros((96, 96, 3), np.uint8); red[..., 0] = 200
    red2 = red.copy(); red2[40:60, 40:60, 1] = 60
    blue = np.zeros((96, 96, 3), np.uint8); blue[..., 2] = 200
    picks = [{"path": n, "t": None, "_f": CR.features(im)} for n, im in (("red", red), ("blue", blue), ("red2", red2))]
    assert [c["path"] for c in CR.order_chain(picks)] == ["red", "red2", "blue"]
    assert len(CR.morph_pairs(CR.order_chain(picks))) == 2
    spec = CR.edit_spec(CR.order_chain(picks), [i * 0.5 for i in range(40)], 12.0, bars_per_shot=1)
    assert {t["kind"] for t in spec["transitions"]} == {"scene-morph"}


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg")
def test_camera_roll_pick_best_folder(tmp_path):
    from xenoform import camera_roll as CR

    for name, src in (("a.png", "testsrc2=s=192x192"), ("b.png", "color=gray:s=192x192"), ("c.png", "testsrc=s=192x192")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-frames:v", "1", str(tmp_path / name)], check=True)
    picks = CR.pick_best(tmp_path, k=2)
    assert len(picks) == 2 and "b.png" not in [Path(p["path"]).name for p in picks]
    assert all("_f" not in p for p in CR.public(picks))
