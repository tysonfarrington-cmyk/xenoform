from pathlib import Path

from xenoform import dense, footage, guardrails as g


def test_quality_rank_prefers_sharp():
    items = [{"path": "soft.mp4", "kind": "video", "qa": {"verdict": "upscale", "soft": True}},
             {"path": "sharp.mp4", "kind": "video", "qa": {"verdict": "ok", "soft": False}},
             {"path": "mid.mp4", "kind": "video", "qa": {"verdict": "upscale", "soft": False}}]
    plan = footage.plan_edit(items, [i * 0.5 for i in range(40)], 12.0, bars_per_shot=1, hash_fn=lambda p, t: None)
    assert [s["src"] for s in plan["segments"]][:3] == ["sharp.mp4", "mid.mp4", "soft.mp4"]


def test_nasa_prefers_orig():
    import inspect
    assert '"~orig.mp4", "~large.mp4"' in inspect.getsource(footage.nasa_media_url)


def test_stretch_fills_duration():
    shots = [{"seconds": 2.0, "start": 0.0, "frames": 48}, {"seconds": 2.0, "start": 2.0, "frames": 48}]
    out = dense._stretch(shots, 8.0)
    assert [s["seconds"] for s in out] == [4.0, 4.0] and out[1]["start"] == 4.0 and out[1]["frames"] == 96


def test_morph_path_never_repeats_stills(monkeypatch, tmp_path):
    pool = [{"path": f"s{i}.png", "noun": f"n{i}"} for i in range(4)]
    def fake_stills(state, count):
        return "black", [pool[i % len(pool)] for i in range(count)]
    seen = {}
    def fake_shots(state, directed, audio):
        n = state.get("morph_count")
        n = 10 if n in (None, "auto") else int(n)
        seen["n"] = n
        return [{"seconds": 2.0, "start": 2.0 * i, "frames": 48} for i in range(n)], {"name": "flow", "shots": []}
    monkeypatch.setattr(dense, "stills_for", fake_stills, raising=False)
    monkeypatch.setattr(dense, "shots_for", fake_shots)
    captured = {}
    def fake_mock(shots, stills, work, w, h):
        captured["stills"] = [s["path"] for s in stills]
        captured["shots"] = shots
        raise RuntimeError("stop")
    import xenoform.cloud_morph as cm
    monkeypatch.setattr(cm, "_mock_clips", fake_mock)
    try:
        dense.run_simple({"duration": 20.0, "beats": []}, Path("x.wav"), tmp_path / "o.mp4", tmp_path, {}, {"aspect": "16:9"},
                         lambda *a: None, engine="mock")
    except RuntimeError as exc:
        assert str(exc) == "stop"
    assert seen["n"] == 3
    st = captured["stills"][: len(captured["shots"]) + 1]
    assert len(st) == len(set(st)) == 4


def test_vj_stem_uniforms_drive_effects():
    html = (Path(g.ROOT) / "src/xenoform/ui_static/vj.html").read_text(encoding="utf-8")
    for u in ("sDrum", "sBass", "sOther", "sVoc"):
        assert f"f1('{u}'" in html and u in html.split("uniform float t,m")[1].split(";")[0]
    shader = html.split("const FS=")[1].split("void main()")[1].split("gl_FragColor")[0]
    assert "sBass*inten" in shader and "sDrum*inten" in shader and "sOther*inten" in shader and "sVoc*inten" in shader
    assert "Q.get('stems')" in html and "stemAt('drums'" in html
