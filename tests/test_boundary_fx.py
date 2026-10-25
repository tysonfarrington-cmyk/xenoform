"""Boundary kinds (26 Oct 2026): a cut with every knob at 1 reads as a different, wilder cut than the defaults. Four
kinds at the shot handoffs (a smear on the drums, a luma-safe strobe cut past Chaos 0.7, a wipe on the bar, a chromatic
rip from Intensity), a picker from Chaos and the section role (the drop the loudest, never the same twice in a row,
none at Chaos 0), the record, the lane, the re-cut and the knob note."""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from xenoform import boundary_fx as B
from xenoform import post_qa

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
DEMO = ROOT / "examples" / "demo.wav"


def _frame(h=72, w=128, back=(12, 12, 16), disc=(200, 180, 160), cx=0.5, cy=0.5, r=0.25):
    a = np.zeros((h, w, 3), np.uint8)
    a[:] = back
    yy, xx = np.mgrid[0:h, 0:w]
    a[((xx - cx * w) ** 2 + (yy - cy * h) ** 2) < (r * h) ** 2] = disc
    return a


LIVE = _frame()
OTHER = _frame(back=(230, 225, 215), disc=(40, 60, 200), cx=0.3, cy=0.6, r=0.2)
P = B.params({"intensity": 1.0, "chaos": 1.0})
BEATS = [i * 0.5 for i in range(80)]  # 120 bpm: a beat is 12 frames, a bar 48


# ------------------------------------------------------------------------------------------------ the kinds


@pytest.mark.parametrize("kind,variant", [("smear", ""), ("strobe", ""), ("wipe", "strips"), ("wipe", "iris"), ("rip", "")])
def test_every_kind_keeps_shape_and_dtype_and_does_nothing_at_amount_zero(kind, variant):
    out = B.treat(LIVE, OTHER, kind, 0.0, amount=P["amount"], stem=1.0, p=P, j=1, seed=5, variant=variant)
    assert out.shape == LIVE.shape and out.dtype == np.uint8
    assert np.abs(out.astype(int) - LIVE.astype(int)).mean() > 8  # the handoff is visible at the cut
    same = B.treat(LIVE, OTHER, kind, 0.0, amount=0.0, stem=1.0, p=P, j=1, seed=5, variant=variant)
    assert (same == LIVE).all()
    edge = B.treat(LIVE, OTHER, kind, 1.0, amount=1.0, stem=1.0, p=P, j=1, seed=5, variant=variant)
    assert (edge == LIVE).all()  # the window's edges hand back the live frame: no jump into or out of the window
    assert (B.treat(LIVE, OTHER[:, :64], kind, 0.0, amount=1.0, p=P) == LIVE).all()  # a size mismatch is a no-op
    assert (B.treat(LIVE, OTHER, "shimmer", 0.0, amount=1.0, p=P) == LIVE).all()  # an unknown kind is a no-op


def test_the_kinds_differ_from_each_other():
    # mid-window: at the cut itself both wipes have covered the frame and read the same
    outs = {k: B.treat(LIVE, OTHER, k, 0.45, amount=1.0, stem=1.0, p=P, j=1, seed=5, variant="iris") for k in B.KINDS}
    outs["wipe-strips"] = B.treat(LIVE, OTHER, "wipe", 0.45, amount=1.0, stem=1.0, p=P, j=1, seed=5, variant="strips")
    keys = list(outs)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            assert np.abs(outs[a].astype(int) - outs[b].astype(int)).mean() > 5, (a, b)


def test_the_strobe_alternates_but_never_flashes():
    """A dark object against a near-white one is the worst case: the odd frames swap the picture, the mean luma stays."""
    frames = [B.treat(LIVE, OTHER, "strobe", (j - 6) / 6.0, amount=1.0, stem=1.0, p=P, j=j, seed=1) for j in range(12)]
    luma = [float(f.astype(np.float32).mean()) for f in frames]
    rep = post_qa.flash_counts(luma)
    assert rep["flashes"] == 0 and rep["max_jump"] < 10  # the QA flash check counts mean-luma jumps over 40 of 255
    assert np.abs(frames[5].astype(int) - frames[6].astype(int)).mean() > 20  # the pictures do alternate
    assert (frames[6] == LIVE).all()  # even frames are the live picture
    disc = (OTHER == np.array([40, 60, 200], np.uint8)).all(axis=2)  # the other picture is a dark disc on a light ground
    odd = frames[7].astype(np.float32).mean(axis=2)
    assert odd[disc].mean() < odd[~disc].mean()  # the odd frame carries the other picture's pattern, pulled to the live luma
    assert LIVE.astype(np.float32).mean(axis=2)[disc].mean() >= LIVE.astype(np.float32).mean(axis=2)[~disc].mean() * 0.9


def test_the_rip_offset_follows_intensity_and_the_strips_follow_chaos():
    lo, hi = B.params({"intensity": 0.0, "chaos": 0.0}), B.params({"intensity": 1.0, "chaos": 1.0})
    assert lo["offset"] < hi["offset"] and lo["amount"] == 0.4 and hi["amount"] == 1.0
    assert lo["strips"] == 2 and hi["strips"] == 16 and B.params(None)["strips"] == 6
    soft = B.treat(LIVE, OTHER, "rip", 0.0, amount=1.0, stem=1.0, p=lo, j=1)
    hard = B.treat(LIVE, OTHER, "rip", 0.0, amount=1.0, stem=1.0, p=hi, j=1)

    def red_edge(img):  # the red channel is the live picture pushed right: the disc's left edge in red moves with Intensity
        return int(np.argmax(img[36, :, 0] > 100))

    assert red_edge(hard) - red_edge(LIVE) > red_edge(soft) - red_edge(LIVE) >= 1
    mid = B.treat(LIVE, OTHER, "wipe", 0.5, amount=1.0, stem=0.0, p=hi, j=1, variant="strips")
    changed = np.abs(mid[:, 4].astype(int) - LIVE[:, 4].astype(int)).sum(axis=1) > 0
    flips = int((changed[1:] != changed[:-1]).sum())
    assert 12 <= flips <= 16  # 16 bands, every other one entered from the left: a column near the left edge alternates


def test_the_smear_rides_the_drums_and_grows_toward_the_cut():
    def moved(img):
        return (np.abs(img.astype(int) - LIVE.astype(int)).sum(axis=2) > 0).mean()

    quiet = B.treat(LIVE, OTHER, "smear", 0.0, amount=1.0, stem=0.0, p=P, seed=9)
    loud = B.treat(LIVE, OTHER, "smear", 0.0, amount=1.0, stem=1.0, p=P, seed=9)
    assert moved(loud) > moved(quiet) > 0
    early = B.treat(LIVE, OTHER, "smear", -0.7, amount=1.0, stem=0.5, p=P, seed=9)
    late = B.treat(LIVE, OTHER, "smear", -0.1, amount=1.0, stem=0.5, p=P, seed=9)
    assert moved(late) > moved(early)  # the same seeded block order, more of it nearer the cut
    assert B.envelope(0.0) == 1.0 and B.envelope(1.0) == 0.0 and B.envelope(-1.0) == 0.0 and 0.4 < B.envelope(0.5) < 0.6


# ------------------------------------------------------------------------------------------------ the picker


def _story_shots(n_pre=6, n_drop=8, n_post=6, shot_s=1.0, fps=24):
    shots, t = [], 0.0

    def add(role, boundary=""):
        nonlocal t
        s = {"index": len(shots), "start": round(t, 3), "end": round(t + shot_s, 3), "seconds": shot_s, "frames": int(shot_s * fps),
             "section": role, "effects": []}
        if boundary:
            s["boundary"] = boundary
        shots.append(s)
        t += shot_s

    for k in range(n_pre):
        add("intro" if k < 2 else "build", "switch" if k == 2 else "")
    for k in range(n_drop):
        add("drop" if k < 4 else "drop_late", "drop" if k == 0 else "")
    for k in range(n_post):
        add("outro", "silence" if k == 0 else "")
    return shots


def test_pick_is_plain_at_chaos_zero_and_wild_at_one():
    shots = _story_shots()
    assert B.pick(shots, {"chaos": 0.0}, BEATS, 24) == [None] * len(shots)
    assert B.pick(shots, {"chaos": 0.15}, BEATS, 24) == [None] * len(shots)
    assert B.share(0.0) == 0.0 and B.share(1.0) == 1.0 and 0.15 < B.share(0.3) < 0.3
    wild = B.pick(shots, {"chaos": 1.0, "intensity": 1.0}, BEATS, 24, seed=3)
    kinds = [e["kind"] for e in wild if e]
    assert wild[0] is None and len(kinds) == len(shots) - 1  # every boundary
    assert set(kinds) == set(B.KINDS)  # all four across the song
    assert all(a != b for a, b in zip(kinds, kinds[1:]))  # never the same twice in a row
    drop = next(i for i, s in enumerate(shots) if s.get("boundary") == "drop")
    assert wild[drop]["kind"] == "strobe" and wild[drop]["boundary"] == "drop"  # the drop gets the loudest
    strobes = [e["t"] for e in wild if e and e["kind"] == "strobe"]
    assert len(strobes) >= 2 and all(b - a >= B.STROBE_GAP_S for a, b in zip(strobes, strobes[1:]))
    wipes = [e for e in wild if e and e["kind"] == "wipe"]
    assert {e["variant"] for e in wipes} == {"iris", "strips"}  # an iris where the song is loud, strips elsewhere
    assert all(e["variant"] == "" for e in wild if e and e["kind"] != "wipe")
    some = B.pick(shots, {"chaos": 0.3}, BEATS, 24, seed=3)
    n_some = sum(1 for e in some if e)
    assert 1 <= n_some < len(kinds) // 2  # the defaults get a taste, not the lot
    assert some[drop] is not None  # the drop comes first
    mild = B.pick(shots, {"chaos": 0.6}, BEATS, 24)
    assert "strobe" not in {e["kind"] for e in mild if e}  # strobes only past 0.7
    assert mild[drop]["kind"] == "rip"  # the loudest it may have under 0.7
    other_seed = [e["kind"] for e in B.pick(shots, {"chaos": 1.0}, BEATS, 24, seed=4) if e]
    assert other_seed != kinds and set(other_seed) == set(B.KINDS)  # the seed rotates the order, the rules hold


def test_pick_windows_fit_the_shots_and_follow_the_beat():
    shots = _story_shots(shot_s=1.0)
    wild = B.pick(shots, {"chaos": 1.0}, BEATS, 24)
    for i, e in enumerate(wild):
        if not e:
            continue
        assert e["tail"] <= shots[i - 1]["frames"] // 2 and e["head"] <= shots[i]["frames"] // 2
        assert e["frames"] == e["tail"] + e["head"] and e["stem"] == B.STEM[e["kind"]] and e["section"] == shots[i]["section"]
    strobe = next(e for e in wild if e and e["kind"] == "strobe")
    assert strobe["frames"] == 12  # a beat at 120 bpm
    wide = B.pick(_story_shots(shot_s=4.0), {"chaos": 1.0}, BEATS, 24)
    wipe = next(e for e in wide if e and e["kind"] == "wipe")
    assert wipe["frames"] == 48 and wipe["tail"] == 24 and wipe["head"] == 24  # a bar, when the shots can hold it
    tiny = [{"start": 0.0, "end": 0.1, "frames": 2, "section": "drop"},
            {"start": 0.1, "end": 0.2, "frames": 2, "section": "drop", "boundary": "drop"}]
    assert B.pick(tiny, {"chaos": 1.0}, BEATS, 24) == [None, None]  # too short for a window
    assert B.pick(shots[:1], {"chaos": 1.0}, BEATS, 24) == [None]
    flat = [{"start": float(i), "end": float(i + 1), "frames": 24} for i in range(8)]  # a plan with no sections (the dense plan)
    assert all(e for e in B.pick(flat, {"chaos": 1.0}, BEATS, 24)[1:])
    dropped = B.pick(flat, {"chaos": 1.0}, BEATS, 24, drop=4.1)  # the plan's drop marks the boundary nearest it
    assert dropped[4]["kind"] == "strobe" and dropped[4]["boundary"] == "drop"
    assert {e["variant"] for e in dropped[1:4] if e["kind"] == "wipe"} <= {"strips"}  # strips before the drop
    assert {e["variant"] for e in dropped[4:] if e["kind"] == "wipe"} == {"iris"}  # irises from the drop on
    assert B.pick(flat, {"chaos": 1.0}, BEATS, 24, drop=40.0)[4]["boundary"] == ""  # a drop off the cut marks nothing


def test_pick_leaves_the_vibes_premium_picks_except_the_drop_past_point_seven():
    shots = _story_shots()
    drop = next(i for i, s in enumerate(shots) if s.get("boundary") == "drop")
    switch = next(i for i, s in enumerate(shots) if s.get("boundary") == "switch")
    premium = [None] * len(shots)
    premium[switch] = {"kind": "chrome-refract", "frames": 8, "boundary": "switch"}
    premium[drop] = {"kind": "match-cut", "frames": 12, "boundary": "drop"}
    wild = B.pick(shots, {"chaos": 1.0}, BEATS, 24, premium=premium)
    assert wild[switch] is None and wild[drop]["kind"] == "strobe"
    cleared = B.clear_premium(premium, wild)
    assert cleared[switch] == premium[switch] and cleared[drop] is None
    mild = B.pick(shots, {"chaos": 0.6}, BEATS, 24, premium=premium)
    assert mild[drop] is None and mild[switch] is None  # under 0.7 the vibe's drop pick stays
    assert B.clear_premium(None, wild) is None
    assert B.label({"kind": "wipe", "variant": "iris"}) == "iris wipe" and B.label({"kind": "wipe"}) == "strip wipe"
    assert B.label({"kind": "strobe"}) == "strobe cut" and B.label({"kind": "rip"}) == "chromatic rip" and B.label(None) == ""
    rep = B.info(wild, B.params({"chaos": 1.0}))
    assert rep["boundaries"] == sum(1 for e in wild if e) and set(rep["kinds"]) == set(B.KINDS) and rep["params"]["chaos"] == 1.0
    assert "strobe cut" in rep["labels"]


def test_plan_reads_the_new_object_at_each_handoff():
    shots = [{"frames": 48}, {"frames": 48}, {"frames": 60, "performer": True}, {"frames": 48}]
    clips = ["c0.mp4", "c1.mp4", "polly.mp4", "c3.mp4"]
    reads = []

    def fake_read(clip, which):
        reads.append((clip.name, which))
        return _frame(disc=(len(reads) * 20 % 255, 100, 100))

    picks = [None, {"kind": "wipe", "tail": 6, "head": 6, "variant": "strips"}, {"kind": "rip", "tail": 4, "head": 5},
             {"kind": "smear", "tail": 3, "head": 3}]
    out = B.plan(picks, shots, clips, read_edge=fake_read)
    assert out[0]["tail"]["kind"] == "wipe" and out[0]["tail"]["frames"] == 6 and "head" not in out[0]
    assert out[1]["head"]["kind"] == "wipe" and out[1]["head"]["offset"] == 6 and out[1]["tail"]["kind"] == "rip"
    assert out[3]["head"]["kind"] == "smear" and "tail" not in out[3]
    assert reads == [("c1.mp4", "last"), ("polly.mp4", "first"), ("polly.mp4", "last"), ("c3.mp4", "first")]  # each edge once
    # a morph landing shows where the shot lands on both halves; the hard cut into Polly shows her first frame in the
    # tail before her and the object that left in her head; out of her, the next object's first frame arrives
    assert (out[0]["tail"]["other"] == out[1]["head"]["other"]).all()
    assert not (out[1]["tail"]["other"] == out[2]["head"]["other"]).all()
    half, u, j = B.at(out[1], 0, 48)
    assert half["kind"] == "wipe" and 0 < u < 1 and j == 6  # the head continues the window the tail began
    half, u, j = B.at(out[1], 44, 48)
    assert half["kind"] == "rip" and -1 < u < 0 and j == 0
    assert B.at(out[1], 20, 48) is None and B.at(None, 0, 10) is None
    assert B.plan([None] * 4, shots, clips, read_edge=fake_read) == [None] * 4


# ------------------------------------------------------------------------------------------------ the cut


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")
def test_a_composed_cut_carries_the_kinds_only_at_the_handoffs(tmp_path):
    from xenoform import beatfx

    def clip(path, seconds, hue):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size=64x112:rate=24:duration={seconds}",
                        "-vf", f"hue=h={hue}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
        return path

    audio = tmp_path / "a.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100:duration=6", str(audio)], check=True)
    clips = [clip(tmp_path / f"c{i}.mp4", 2.0, hue) for i, hue in enumerate((0, 120, 240))]
    shots = [{"index": i, "start": 2.0 * i, "end": 2.0 * (i + 1), "seconds": 2.0, "frames": 48, "speed": 1.0, "ease": "", "effects": [],
              "section": "build" if i < 2 else "drop", **({"boundary": "drop"} if i == 2 else {})} for i in range(3)]
    beats = [i * 0.5 for i in range(12)]
    macros = {"intensity": 1.0, "speed": 0.5, "chaos": 1.0, "glow": 0.5}
    kw = dict(aspect="9:16", quality="draft", fx=False, overlay=False, beats=beats, size=(64, 112), fps=24, dance_fx="off", stem_orbit=False,
              macros=macros, seed=1)
    picks = B.pick(shots, macros, beats, 24, seed=1)
    assert picks[0] is None and all(picks[1:]) and picks[2]["kind"] == "strobe"
    plain = beatfx.compose(clips, shots, audio, tmp_path / "plain.mp4", **kw)
    wild = beatfx.compose(clips, shots, audio, tmp_path / "wild.mp4", boundary_fx=picks, **kw)
    assert plain["frames"] == wild["frames"] == 144
    assert plain["boundary_fx"]["boundaries"] == 0 and wild["boundary_fx"]["boundaries"] == 2
    assert wild["boundary_fx"]["kinds"] == {picks[1]["kind"]: 1, "strobe": 1} and wild["boundary_fx"]["params"]["amount"] == 1.0
    a = beatfx.read_frames(tmp_path / "plain.mp4")
    b = beatfx.read_frames(tmp_path / "wild.mp4")
    diff = np.abs(a.astype(int) - b.astype(int)).mean(axis=(1, 2, 3))
    # away from the handoffs the frames are the same picture (x264 adds a little noise around changed frames, under 4)
    assert diff[20] < 4 and diff[70] < 4 and diff[130] < 4, diff.round(1).tolist()
    assert max(diff[46], diff[47], diff[48]) > 10, diff.round(1).tolist()  # at the cuts the handoff is visible
    assert max(diff[94], diff[95], diff[96]) > 10, diff.round(1).tolist()
    # a premium transition at a boundary a kind took is not drawn over it
    both = beatfx.compose(clips, shots, audio, tmp_path / "both.mp4", boundary_fx=picks,
                          transitions=[None, {"kind": "match-cut", "frames": 8}, None], **kw)
    assert both["transitions"] == [] and both["frames"] == 144


def test_run_simple_records_the_kinds_and_the_lane_names_them(tmp_path, monkeypatch):
    from xenoform import beatfx, dense, lane

    seen = {}

    def fake_compose(clips, shots, audio, out, **kw):
        seen.update(kw)
        Path(out).write_bytes(b"mp4")
        return {"frames": 24, "seconds": 1.0, "size": "540x960", "aspect": kw["aspect"], "fx": True, "overlay": False, "centres": [],
                "fps": 24, "look": {"dance_fx": kw.get("dance_fx"), "frames": 24, "seconds": 0.5},
                "boundary_fx": B.info(kw.get("boundary_fx") or [])}

    n = 8
    plan_shots = [{"start": float(i), "end": float(i + 1), "seconds": 1.0, "frames": 24, "render_s": 2, "speed": 2.0, "effects": [],
                   "section": "drop" if i >= 4 else "build", **({"boundary": "drop"} if i == 4 else {})} for i in range(n)]
    monkeypatch.setattr(dense, "stills_for", lambda state, k, **kw: ("black", [{"path": f"s{i}.png", "file": f"s{i}.png"} for i in range(k)]))
    monkeypatch.setattr(dense, "shots_for", lambda state, directed, audio: ([dict(s) for s in plan_shots], {"name": "t", "shots": []}))
    import xenoform.cloud_morph as cm

    monkeypatch.setattr(cm, "_mock_clips", lambda shots, stills, work, w, h: [tmp_path / f"m{i}.mp4" for i in range(len(shots))])
    monkeypatch.setattr(beatfx, "compose", fake_compose)
    monkeypatch.setattr("xenoform.portrait.black_stills", lambda stills, work: stills)
    monkeypatch.setattr("xenoform.portrait.portrait_stills", lambda stills, work, w=720, h=1280, background=None: stills)
    beats = [i * 0.5 for i in range(16)]
    wild = dense.run_simple({"duration": 8.0, "beats": beats}, DEMO, tmp_path / "x.mp4", tmp_path, {},
                            {"vibe": "black", "aspect": "16:9", "dance_fx": "off", "stem_orbit": False,
                             "macros": {"chaos": 1.0, "intensity": 1.0}}, lambda *a: None, engine="mock")
    kinds = [e["kind"] if e else None for e in seen["boundary_fx"]]
    assert kinds[0] is None and all(kinds[1:]) and set(kinds[1:]) == set(B.KINDS) and kinds[4] == "strobe"
    assert wild["boundary_fx"] == seen["boundary_fx"] and wild["handoffs"]["boundaries"] == n - 1
    assert any("boundary_fx" in note for note in wild["fallbacks"])
    rec = json.loads((tmp_path / "simple" / "simple.json").read_text(encoding="utf-8"))
    rows = lane.build(rec, "v1")["shots"]
    assert "transition" not in rows[0] and rows[4]["transition"] == "strobe cut" and rows[4]["kind"] == "strobe"
    assert {r.get("kind") for r in rows[1:]} == set(B.KINDS)
    assert all(r["transition"] in ("smear", "strobe cut", "iris wipe", "strip wipe", "chromatic rip") for r in rows[1:])
    seen.clear()
    calm = dense.run_simple({"duration": 8.0, "beats": beats}, DEMO, tmp_path / "y.mp4", tmp_path / "y", {},
                            {"vibe": "black", "aspect": "16:9", "dance_fx": "off", "stem_orbit": False, "macros": {"chaos": 0.0}},
                            lambda *a: None, engine="mock")
    assert seen["boundary_fx"] == [None] * n and calm["handoffs"]["boundaries"] == 0
    assert not any("boundary_fx" in note for note in calm["fallbacks"])
    rows = lane.build(json.loads((tmp_path / "y" / "simple" / "simple.json").read_text(encoding="utf-8")), "v2")["shots"]
    assert not any("transition" in r for r in rows)  # the calm cut keeps the plain handoff


def test_the_recut_keeps_the_kinds_from_the_knobs(tmp_path, monkeypatch):
    from xenoform import beatfx, dense
    from xenoform.cloud_morph import custom_shots

    job = tmp_path / "jobs" / "abc"
    work = job / "simple"
    work.mkdir(parents=True)
    clips = []
    for i in range(4):
        c = work / f"local0{i}.mp4"
        c.write_bytes(b"x")
        clips.append(c)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    shots = custom_shots({"shots": [{"start": float(i), "end": float(i + 1), "render_s": 2} for i in range(4)]}, 4.0)
    rec = {"plan_shots": shots, "shots": shots, "clips": [str(c) for c in clips], "audio_path": str(audio), "vibe": "black", "tier": "draft",
           "size": [64, 112], "fps": 24, "seed": 3, "plan_name": "dense (auto)", "vertical_house": True, "beats": [i * 0.5 for i in range(8)],
           "recut_state": {"vibe": "black", "aspect": "9:16", "quality_tier": "draft", "dance_fx": "off", "stem_orbit": False,
                           "beat_fx": False, "macros": {"chaos": 0.0}}}
    (work / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    (job / "xenoform.mp4").write_bytes(b"old")
    seen = {}

    def spy(clips_, shots_, audio_, out, **kw):
        seen.update(kw)
        Path(out).write_bytes(b"new")
        return {"frames": 96, "seconds": 4.0, "size": "64x112", "aspect": "9:16", "fx": False, "overlay": False, "centres": [], "fps": 24,
                "look": {}, "transitions": [], "boundary_fx": B.info(kw.get("boundary_fx") or [])}

    monkeypatch.setattr(beatfx, "compose", spy)
    out = dense.recut_from_cache(job, {"macros": {"chaos": 1.0, "intensity": 1.0}})
    kinds = [e["kind"] if e else None for e in seen["boundary_fx"]]
    assert kinds[0] is None and all(kinds[1:]) and out["boundary_fx"] == seen["boundary_fx"] and out["handoffs"]["boundaries"] == 3
    saved = json.loads((work / "simple.json").read_text(encoding="utf-8"))
    assert saved["boundary_fx"] == out["boundary_fx"] and saved["recut_state"]["macros"]["chaos"] == 1.0
    again = dense.recut_from_cache(job, {"macros": {"chaos": 1.0, "intensity": 1.0}})
    assert again["boundary_fx"] == out["boundary_fx"]  # the same knobs give the same kinds
    calm = dense.recut_from_cache(job, {"macros": {"chaos": 0.0}})
    assert calm["boundary_fx"] == [None] * 4 and calm["handoffs"]["boundaries"] == 0


def test_the_knob_note_names_the_kinds():
    note = APP[APP.index("Chaos is the punches"):APP.index("Glow is the bloom")]
    assert "strobe" in note and "smear" in note and "wipe" in note and "rip" in note and "0.7" in note
