"""Demo v4 audit guardrails: no repeats, lag QA, low-res gate, artifacts, beats, stems, characters, kaleidoscope."""
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import footage, guardrails as g, post_qa as q

FF = shutil.which("ffmpeg")
needs_ff = pytest.mark.skipif(not FF, reason="ffmpeg missing")


def _make(path, vf="", size="320x568", rate=24, dur=2):
    src = f"testsrc2=size={size}:rate={rate}:duration={dur}"
    cmd = [FF, "-v", "error", "-y", "-f", "lavfi", "-i", src]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-pix_fmt", "yuv420p", "-c:v", "libx264", "-r", str(rate), str(path)]
    subprocess.run(cmd, check=True)
    return path


# ---------------- config
def test_new_rules_in_config():
    r = g.rules()
    for k in ("no_repeat", "lag_qa", "source_quality", "artifact_qa", "beat_alignment", "character_sparing", "kaleidoscope"):
        assert k in r and r[k].get("why")


# ---------------- no repeats
def test_apply_drops_repeated_sources():
    body, rep = g.apply({"segments": [{"src": "a.mp4"}, {"src": "b.mp4"}, {"src": "A.mp4"}]})
    assert [s["src"] for s in body["segments"]] == ["a.mp4", "b.mp4"]
    assert "no_repeat" in {x["id"] for x in rep["applied"]}


def test_tracker_catches_same_look_different_path():
    t = g.SourceTracker(max_hamming=6)
    img = np.random.default_rng(0).integers(0, 255, (64, 64, 3)).astype(np.uint8)
    t.add("a.mp4", g.dhash(img))
    assert t.seen("copy_of_a.mp4", g.dhash(np.clip(img.astype(int) + 3, 0, 255)))
    assert not t.seen("c.mp4", g.dhash(255 - img))


def _items(n, **kw):
    return [{"path": f"clip{i}.mp4", "kind": "video", **kw} for i in range(n)]


def test_plan_edit_never_repeats_and_warns_when_dry():
    beats = [i * 0.5 for i in range(80)]
    plan = footage.plan_edit(_items(3), beats, 40.0, bars_per_shot=1, hash_fn=lambda p, t: None)
    srcs = [s["src"] for s in plan["segments"]]
    assert len(srcs) == len(set(srcs)) == 3
    assert any("unique source" in w for w in plan["warnings"])
    assert abs(sum(s["dur"] for s in plan["segments"]) - 40.0) < 1e-6


def test_plan_edit_pulls_more_when_dry():
    beats = [i * 0.5 for i in range(80)]
    more = lambda n: [{"path": f"lib{i}.mp4", "kind": "video"} for i in range(n)]
    plan = footage.plan_edit(_items(2), beats, 16.0, bars_per_shot=1, hash_fn=lambda p, t: None, more=more)
    srcs = [s["src"] for s in plan["segments"]]
    assert len(srcs) == len(set(srcs)) and any(s.startswith("lib") for s in srcs)


def test_plan_edit_dedupes_by_hash():
    plan = footage.plan_edit(_items(4), [i * 0.5 for i in range(40)], 8.0, hash_fn=lambda p, t: "ffffffffffffffff")
    assert len(plan["segments"]) == 1


def test_plan_edit_allow_repeats_keeps_old_behaviour():
    plan = footage.plan_edit(_items(2), [i * 0.5 for i in range(80)], 16.0, bars_per_shot=1, allow_repeats=True)
    assert len(plan["segments"]) > 2


# ---------------- characters
def test_character_sparing_in_plan_edit():
    items = [{"path": f"polly_take{i}.mp4", "kind": "video"} for i in range(5)] + _items(10)
    plan = footage.plan_edit(items, [i * 0.5 for i in range(80)], 30.0, bars_per_shot=1, hash_fn=lambda p, t: None)
    segs, t = plan["segments"], 0.0
    chars = []
    for s in segs:
        if s["character"]:
            chars.append(t)
        t += s["dur"]
    assert 0 < len(chars) <= 3 and min(chars) >= 0.15 * 30.0 - 1e-6


def test_character_sparing_guardrail_blocks():
    blocks = [{"form": "polly", "hold": 2}] + [{"form": "feather", "hold": 2} for _ in range(3)] + [{"form": "polly", "hold": 2} for _ in range(5)]
    body, rep = g.apply({"blocks": blocks}, duration=18)
    forms = [b["form"] for b in body["blocks"]]
    assert forms[0] != "polly" and forms.count("polly") <= 3
    body, rep = g.apply({"blocks": blocks, "expert": True}, duration=18)
    assert [b["form"] for b in body["blocks"]].count("polly") == 6


# ---------------- kaleidoscope
def test_kaleidoscope_expert_only():
    body, _ = g.apply({"kal": 1, "transitions": ["kaleidoscope", "snap"]})
    assert body["kal"] == 0 and body["transitions"] == ["snap"]
    body, _ = g.apply({"kal": 1, "expert": True})
    assert body["kal"] == 1


def test_vj_kaleido_gated_and_no_repeat():
    html = (Path(g.ROOT) / "src/xenoform/ui_static/vj.html").read_text(encoding="utf-8")
    assert "kal:EXPERT?" in html and "nextUnused()" in html and "if(EXPERT)tog('kal','kal')" in html


# ---------------- beats
def test_beat_report_and_snap():
    beats = [0.0, 0.5, 1.0, 1.5, 2.0]
    rep = q.beat_report([0.5, 1.07, 1.52], beats)
    assert [o["cut"] for o in rep["off_beat"]] == [1.07]
    assert q.snap_cuts([0.5, 1.07, 1.52, 1.75, 2.4], beats) == [0.5, 1.0, 1.52, 1.5, 2.4]


def test_guardrail_snaps_cut_list():
    body, rep = g.apply({"cuts": [0.56, 1.0]}, beats=[0.0, 0.5, 1.0])
    assert body["cuts"] == [0.5, 1.0]


# ---------------- artifacts
def _texture(seed=0):
    rng = np.random.default_rng(seed)
    base = (rng.random((90, 160)) > 0.5).astype(np.float32)
    base = np.kron(base, np.ones((4, 4)))[:360, :640] * 200 + 20
    return np.repeat(base[..., None], 3, axis=2).astype(np.uint8)


def test_chroma_shift_detected():
    img = _texture()
    assert q.chroma_shift_px(img) == 0
    bad = img.copy()
    bad[..., 0] = np.roll(img[..., 0], 5, axis=1)
    assert q.chroma_shift_px(bad) >= 3


def test_glitch_rows_detected():
    smooth = np.tile(np.linspace(0, 255, 640, dtype=np.uint8)[None, :, None], (360, 1, 3))
    assert q.glitch_rows(smooth) < 0.03
    bad = smooth.copy()
    for y in range(0, 360, 12):
        bad[y:y + 6] = np.roll(bad[y:y + 6], 200, axis=1)
    assert q.glitch_rows(bad) >= 0.03


# ---------------- sharpness / low-res gate
def test_laplacian_sharp_vs_blur():
    img = _texture()
    blur = img.astype(np.float32)
    for _ in range(6):
        blur = (blur + np.roll(blur, 1, 0) + np.roll(blur, 1, 1) + np.roll(blur, -1, 0) + np.roll(blur, -1, 1)) / 5
    assert q.laplacian_var(img) > 10 * q.laplacian_var(blur)


@needs_ff
def test_source_quality_gate(tmp_path):
    small = _make(tmp_path / "small.mp4", size="160x284")
    assert q.source_quality(small, 1080, 1920)["verdict"] == "reject"
    mid = _make(tmp_path / "mid.mp4", size="480x854")
    assert q.source_quality(mid, 1080, 1920)["verdict"] in ("upscale", "reject")
    big = _make(tmp_path / "big.mp4", size="1080x1920", dur=1)
    v = q.source_quality(big, 1080, 1920)
    assert v["verdict"] == "ok" and v["motion_score"] > 0


@needs_ff
def test_nasa_static_marked_soft(tmp_path, monkeypatch):
    still = tmp_path / "still.mp4"
    subprocess.run([FF, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24:duration=0.04",
                    "-vf", "tpad=stop_mode=clone:stop_duration=2", "-pix_fmt", "yuv420p", str(still)], check=True)
    monkeypatch.setattr(footage, "local_path", lambda item, root=None: still)
    got = footage.qa_item({"id": "x", "kind": "video", "source": "nasa"})
    assert got["soft"] and got.get("note") == "near-static"


def test_plan_edit_skips_rejected():
    items = [{"path": "bad.mp4", "kind": "video", "quality": {"verdict": "reject"}}] + _items(2)
    plan = footage.plan_edit(items, [i * 0.5 for i in range(20)], 4.0, hash_fn=lambda p, t: None)
    assert "bad.mp4" not in [s["src"] for s in plan["segments"]]


# ---------------- lag
@needs_ff
def test_clean_video_has_no_lag(tmp_path):
    v = _make(tmp_path / "ok.mp4")
    rep = q.lag_report(v, 24)
    assert not rep["lag"], rep


@needs_ff
def test_fps_mismatch_conformed(tmp_path):
    v = _make(tmp_path / "30.mp4", rate=30)
    rep = q.lag_report(v, 24)
    assert rep["lag"] and any("fps" in i for i in rep["issues"])
    fix = q.fix_lag(v, rep, 24)
    assert fix["fixed"] and abs(q.probe(v)["fps"] - 24) < 0.05


@needs_ff
def test_held_frames_detected_and_interpolated(tmp_path):
    v = _make(tmp_path / "held.mp4", vf="fps=6,fps=24")
    rep = q.lag_report(v, 24)
    assert rep["lag"] and rep["dup_ratio"] > 0.5
    fix = q.fix_lag(v, rep, 24)
    assert fix["fixed"] and fix["method"].startswith("interpolate")
    after = q.lag_report(v, 24)
    assert after["dup_ratio"] < rep["dup_ratio"]
    assert abs(q.probe(v)["duration"] - 2.0) < 0.3


@needs_ff
def test_run_reports(tmp_path):
    v = _make(tmp_path / "r.mp4")
    rep = q.run(v, fps=24, beats=[0.0, 0.5, 1.0, 1.5], fix=False)
    assert "lag" in rep and "artifacts" in rep and "beats" in rep


def test_desk_job_runs_post_qa():
    import inspect
    from xenoform import ui
    src = inspect.getsource(ui._run_job)
    assert "post_qa.run(" in src and 'job["qa"]' in src


def test_compose_conforms_fps():
    import inspect
    from xenoform import beatfx
    assert "_conformed(" in inspect.getsource(beatfx.compose)


# ---------------- stem-reactive
def test_frame_change_tracks_stem_energy():
    from xenoform import stem_react as sr
    n = 48
    t = np.arange(n) / 24
    bass = (0.5 + 0.5 * np.sin(2 * np.pi * 1.0 * t)).round(4).tolist()
    vocals = (0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t + 1)).round(4).tolist()
    zero = [0.0] * n
    rng = np.random.default_rng(3)
    frame = (rng.random((96, 64, 3)) * 255).astype(np.uint8)
    for stem, curve in (("bass", bass), ("vocals", vocals)):
        env = {"fps": 24, "drums": zero, "bass": zero, "other": zero, "vocals": zero, stem: curve}
        diffs = [np.abs(sr.apply_frame(frame, env, k / 24).astype(np.float32) - frame).mean() for k in range(n)]
        r = np.corrcoef(diffs, curve)[0, 1]
        assert r > 0.7, (stem, r)


def test_drive_routes_every_stem():
    from xenoform import stem_react as sr
    env = {"fps": 24, "drums": [0.9], "bass": [0.8], "other": [0.4], "vocals": [0.7]}
    d = sr.drive(env, 0.0)
    assert d["scale"] == 0.8 and d["displace"] == 0.8 and d["chroma"] == 0.9 and d["emission"] == 0.7 and d["hue"] == 0.7
