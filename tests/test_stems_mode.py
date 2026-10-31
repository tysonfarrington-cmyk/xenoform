"""Stems mode (docs/STEMS_MODE.md): the stems' activity and onsets, the cache, the status, the fake split engine.

Every test splits with ``stems.fake_split`` (synthetic stems from the song's length: drums on a 120 BPM grid with no
drums in the middle fifth, a bass, an "other" that carries the breakdown, silent vocals), so Demucs never runs here."""
import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from xenoform import stems, stems_api


def _song(tmp_path, name="song.wav", sec=20.0, sr=22050):
    """A plain tone as long as the song should be: the fake split reads only its length."""
    t = np.arange(int(sr * sec)) / sr
    p = Path(tmp_path) / name
    sf.write(str(p), (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
    return p


@pytest.fixture
def stems_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(stems_api, "stems_root", lambda: tmp_path / "stems")
    monkeypatch.setattr(stems, "DEFAULT_ENGINE", "fake")
    stems_api._JOBS.clear()
    stems._ACT_ERRORS.clear()
    return tmp_path / "stems"


def _at(curve, t, fps=24):
    return curve[int(round(t * fps))]


# ------------------------------------------------------------------------------------------------ the fake split


def test_fake_split_writes_four_stems_the_songs_length(tmp_path):
    song = _song(tmp_path, sec=6.0)
    files = stems.fake_split(song, tmp_path / "out")
    assert files["engine"] == "fake"
    assert set(files) - {"engine"} == {"drums", "bass", "other", "vocals"}
    for name in ("drums", "bass", "other", "vocals"):
        info = sf.info(files[name])
        assert abs(info.duration - 6.0) < 0.01
    drums, sr = sf.read(files["drums"])
    mid = drums[int(0.42 * 6.0 * sr):int(0.58 * 6.0 * sr)]
    assert np.abs(mid).max() == 0.0  # the breakdown has no drums
    assert np.abs(drums).max() > 0.1
    vocals, _ = sf.read(files["vocals"])
    assert np.abs(vocals).max() == 0.0


def test_ensure_split_fake_writes_the_split_layout(stems_dir, tmp_path):
    song = _song(tmp_path)
    path = stems.ensure_split(song)
    assert path == stems_api.stems_json_path(song) and path.is_file()
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["engine"] == "fake" and set(rec["stems"]) == {"drums", "bass", "other", "vocals"}
    assert all(Path(p).is_file() for p in rec["files"].values())
    assert stems.ensure_split(song) == path  # cached: the second call splits nothing
    assert stems_api.split_status(song)["status"] == "done"


# ------------------------------------------------------------------------------------------------ the activity


def test_activity_follows_each_stem_and_gates_silence(tmp_path):
    song = _song(tmp_path)
    files = stems.fake_split(song, tmp_path / "out")
    act = stems.activity(files, fps=24, period=0.5)
    curves = act["activity"]
    assert act["frames"] == 480 and all(len(v) == 480 for v in curves.values())
    assert set(act["stems"]) == {"drums", "bass", "other", "vocals"}
    d, o, b, v = curves["drums"], curves["other"], curves["bass"], curves["vocals"]
    assert _at(d, 5.0) > 0.8 and _at(d, 15.0) > 0.8  # the drums play either side of the breakdown
    assert _at(d, 10.0) < 0.05  # and are gone in it
    assert _at(o, 3.0) < 0.05 and _at(o, 10.0) > 0.8 and _at(o, 16.0) < 0.05  # the other carries the breakdown
    assert _at(b, 10.0) > 0.8 and _at(b, 19.6) < 0.1
    assert max(v) == 0.0  # a silent stem never shows
    assert all(0.0 <= x <= 1.0 for c in curves.values() for x in c)


def test_activity_attack_within_a_beat_release_over_two(tmp_path):
    song = _song(tmp_path)
    files = stems.fake_split(song, tmp_path / "out")
    d = stems.activity(files, fps=24, period=0.5)["activity"]["drums"]
    # the drums stop after the burst at 7.5 s and come back at 12.0 s (a beat is 0.5 s here)
    assert _at(d, 7.4) > 0.7
    assert _at(d, 7.83 + 2 * 0.5 + 0.05) < 0.12  # 90 % of the fall within two beats of the last hit leaving the window
    assert _at(d, 12.0 - 0.25 + 0.5 + 0.1) > 0.8  # 90 % of the rise within a beat of the first hit entering it


def test_follow_and_gate_shapes():
    step = np.r_[np.zeros(48), np.ones(96), np.zeros(96)]
    y = stems.follow(step, fps=24, period=0.5)
    assert y[48 + 11] >= 0.899 and y[48 + 10] < 0.89  # 90 % of the rise on the twelfth frame: a beat
    assert y[144 + 23] <= 0.101 and y[144 + 21] > 0.11  # 10 % left on the twenty-fourth: two beats
    g = stems.gate(np.array([0.0, 0.1, 0.12, 0.335, 0.55, 2.0]), 1.0)
    assert list(np.round(g, 3)) == [0.0, 0.0, 0.0, 0.5, 1.0, 1.0]
    assert not stems.gate(np.array([0.5]), 0.0).any()


def test_bleed_under_a_quarter_of_the_loudest_stem_stays_silent(tmp_path):
    sr = 22050
    t = np.arange(sr * 8) / sr
    loud = 0.5 * np.sin(2 * np.pi * 110 * t)
    bleed = 0.003 * np.sin(2 * np.pi * 440 * t)  # about -44 dB under the loud stem
    paths = {}
    for name, sig in (("bass", loud), ("vocals", bleed)):
        p = tmp_path / f"{name}.wav"
        sf.write(str(p), sig.astype(np.float32), sr)
        paths[name] = str(p)
    act = stems.activity(paths, fps=24, period=0.5)
    assert max(act["activity"]["vocals"]) == 0.0
    assert min(act["activity"]["bass"][24:-24]) > 0.9


def test_onsets_are_the_stems_own_and_only_where_it_plays(tmp_path):
    song = _song(tmp_path)
    files = stems.fake_split(song, tmp_path / "out")
    act = stems.activity(files, fps=24, period=0.5)
    hits = act["onsets"]["drums"]
    assert len(hits) >= 20
    assert not [t for t in hits if 8.3 < t < 11.9]  # nothing in the breakdown
    grid = np.arange(0, 20, 0.5)
    assert np.median([np.abs(grid - t).min() for t in hits]) < 0.05  # on the drum grid
    assert act["onsets"]["vocals"] == []


# ------------------------------------------------------------------------------------------------ the cache


def test_activity_for_caches_beside_the_split_and_recomputes_when_stale(stems_dir, tmp_path):
    song = _song(tmp_path)
    path = stems.ensure_split(song)
    first = stems.activity_for(path, fps=24, period=0.5)
    cache = path.with_name(stems.ACTIVITY_FILE)
    assert cache.is_file() and first["source"] == str(path) and first["split_engine"] == "fake"
    stamp = cache.stat().st_mtime_ns
    again = stems.activity_for(path, fps=24, period=0.5)
    assert cache.stat().st_mtime_ns == stamp and again["activity"] == first["activity"]
    assert stems.cached_activity(path, fps=24, period=0.5)["frames"] == first["frames"]
    assert stems.cached_activity(path, fps=24, period=0.667) is None  # another beat: not this cache
    other = stems.activity_for(path, fps=24, period=0.667)
    assert other["period"] == 0.667
    with pytest.raises(FileNotFoundError):
        stems.activity_for(tmp_path / "nope" / "stems.json")


def test_a_length_window_reads_the_whole_songs_activity(stems_dir, tmp_path):
    song = _song(tmp_path, "full.wav", sec=20.0)
    full_json = stems.ensure_split(song)
    full = stems.activity_for(full_json, fps=24, period=0.5)
    cut = _song(tmp_path, "cut.wav", sec=6.0)  # the trimmed window, as ui._trim_audio writes it
    win_json = stems_api.slice_stems(full_json, 7.0, 6.0, cut)
    win = stems.activity_for(win_json, fps=24, period=0.5)
    assert win["frames"] == 144
    assert win["activity"]["drums"] == full["activity"]["drums"][168:168 + 144]
    assert all(0.0 <= t < 6.0 for t in win["onsets"]["drums"])
    assert win["sliced_from"] == {"start": 7.0, "length": 6.0}
    assert not (win_json.parent / stems.ACTIVITY_FILE).exists()  # the window keeps no copy of its own


# ------------------------------------------------------------------------------------------------ the status


def test_status_none_then_done_with_envelopes(stems_dir, tmp_path):
    song = _song(tmp_path)
    assert stems.status(song)["status"] == "none"
    st = stems.start(song, engine="fake", fps=24, period=0.5)
    assert st["status"] in ("running", "done")
    for _ in range(200):
        st = stems.status(song, period=0.5)
        if st["status"] != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done" and st["progress"] == 1.0 and st["stage"] == "done"
    rows = {r["name"]: r for r in st["stems"]}
    assert set(rows) == {"drums", "bass", "other", "vocals"}
    assert rows["drums"]["role"] == "drums" and rows["vocals"]["active"] == 0.0
    assert 0 < len(rows["drums"]["envelope"]) <= stems.ENVELOPE_POINTS
    assert 0.6 < rows["drums"]["active"] < 0.9


def test_status_waits_for_the_envelopes_without_building_them(stems_dir, tmp_path):
    song = _song(tmp_path)
    stems.ensure_split(song)
    st = stems.status(song, period=0.5, build=False)
    assert st["status"] == "running" and st["stage"] == "envelopes"
    assert not (stems_api.stems_json_path(song).parent / stems.ACTIVITY_FILE).exists()


def test_status_while_demucs_runs_estimates_progress(stems_dir, tmp_path):
    song = _song(tmp_path, sec=100.0)
    sid = stems_api.song_hash(song)
    stems_api._JOBS[sid] = {"id": sid, "status": "running", "engine": "demucs", "seconds": 0.0, "path": None, "error": None,
                            "song": song.name, "running_since": time.time() - 18.0, "started": time.time() - 20.0}
    st = stems.status(song)
    expected = stems.expected_seconds(song, "demucs")
    assert expected == pytest.approx(stems.DEMUCS_LOAD_S + stems.DEMUCS_S_PER_SONG_S * 100.0, rel=0.01)
    assert st["status"] == "running" and st["stage"] == "split"
    assert 0.4 < st["progress"] < 0.6 and 10 <= st["eta_s"] <= 20
    stems_api._JOBS[sid]["running_since"] = time.time() - 1000.0
    assert stems.status(song)["progress"] == 0.95  # never full until it is done
    stems_api._JOBS.clear()


def test_engine_names_and_period():
    assert stems.engine_of("librosa") == "bands" and stems.engine_of("Demucs") == "demucs"
    assert stems.engine_of("magic") == "auto"
    assert stems.period_of([0.0, 0.5, 1.0, 1.5]) == 0.5 and stems.period_of([]) == 0.5
    assert stems.envelope(list(range(10)), points=5) == [1.0, 3.0, 5.0, 7.0, 9.0]


# ------------------------------------------------------------------------------------------------ the composite

from xenoform import stems_composite as SC  # noqa: E402


def _solid(path, level, frames=24, size=(32, 32), fps=24):
    """A clip of one grey level (yuv444, lossless), as a layer's cut stands in for one."""
    import subprocess

    from xenoform.video import ffmpeg_bin

    colour = f"0x{level:02x}{level:02x}{level:02x}"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s={size[0]}x{size[1]}:r={fps}:d={frames / fps}",
                    "-frames:v", str(frames), "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p", str(path)], check=True)
    return Path(path)


def _frames(path, size=(32, 32)):
    import subprocess

    from xenoform.video import ffmpeg_bin

    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, size[1], size[0], 3)


def test_alpha_is_prominence_times_activity_and_a_lone_layer_is_opaque():
    layers = [{"stem": "drums", "prominence": 0.8}, {"stem": "other", "prominence": 0.5}]
    act = {"drums": [1.0, 1.0, 0.0, 0.5], "other": [1.0, 0.0, 1.0, 0.0]}
    plain = SC.alphas(layers, act, 4, solo=False)
    assert list(np.round(plain["drums"], 3)) == [0.8, 0.8, 0.0, 0.4]
    assert list(np.round(plain["other"], 3)) == [0.5, 0.0, 0.5, 0.0]
    solo = SC.alphas(layers, act, 4)
    assert list(np.round(solo["drums"], 3)) == [0.8, 1.0, 0.0, 0.7]  # both play: by prominence; alone: opaque
    assert list(np.round(solo["other"], 3)) == [0.5, 0.0, 1.0, 0.0]
    assert len(SC.alphas(layers, {"drums": [1.0]}, 3)["other"]) == 3  # a missing or short curve is padded


def test_order_is_bottom_to_top_by_prominence():
    layers = [{"stem": "drums", "prominence": 0.9}, {"stem": "other", "prominence": 0.4}, {"stem": "bass", "prominence": 0.4}]
    assert SC.order_of(layers) == ["other", "bass", "drums"]
    assert SC.blend_of("Lighten") == "lighten" and SC.blend_of("overlay") == "screen"
    assert SC.prominence_of(3) == 1.0 and SC.prominence_of("x", 0.7) == 0.7


@pytest.mark.parametrize("mode,expect", [("screen", 0.502 + 0.502 * 0.784 * 0.498), ("add", 0.502 + 0.502 * 0.784),
                                         ("lighten", 0.502), ("multiply", 0.502 * (1 - 0.502 * (1 - 0.784))),
                                         ("normal", 0.502 * 0.498 + 0.784 * 0.502)])
def test_each_blend_lays_the_layer_at_its_alpha(tmp_path, mode, expect):
    base = _solid(tmp_path / "base.mp4", 128)
    top = _solid(tmp_path / "top.mp4", 200)
    out = tmp_path / f"{mode}.mp4"
    made = SC.render({"base": base, "top": top}, {"base": np.ones(24), "top": np.full(24, 0.5)}, ["base", "top"],
                     {"top": mode}, None, out, fps=24, size=(32, 32), work=tmp_path / "w")
    assert made["frames"] == 24 and len(made["sha256"]) == 64
    px = _frames(out)
    assert px.shape[0] == 24
    assert abs(float(px[12, 16, 16].mean()) / 255.0 - expect) < 0.025


def test_the_bottom_layer_sits_on_black_at_its_alpha(tmp_path):
    clip = _solid(tmp_path / "a.mp4", 200)
    out = tmp_path / "one.mp4"
    curve = np.r_[np.zeros(8), np.full(8, 0.5), np.ones(8)]
    SC.render({"a": clip}, {"a": curve}, ["a"], {}, None, out, fps=24, size=(32, 32), work=tmp_path / "w")
    px = _frames(out)[:, 16, 16].mean(axis=1)
    assert px[4] < 8 and abs(px[12] - 100) < 8 and abs(px[20] - 200) < 8


def _stems_job(tmp_path, song=None):
    """A finished Stems cut's folder as stems_mode leaves it: two layer cuts, the curves, the record."""
    job = Path(tmp_path) / "job"
    (job / "simple").mkdir(parents=True)
    a = _solid(Path(tmp_path) / "drums.mp4", 220, frames=48)
    b = _solid(Path(tmp_path) / "other.mp4", 90, frames=48)
    layers = [{"stem": "drums", "kind": "objects", "prominence": 0.8, "blend": "screen", "video": str(a)},
              {"stem": "other", "kind": "objects", "prominence": 0.5, "blend": "screen", "video": str(b)}]
    act = {"drums": [1.0] * 16 + [0.0] * 16 + [1.0] * 16, "other": [1.0] * 48}
    SC.write_curves(job, act, fps=24, frames=48)
    comp = SC.section(layers, fps=24, size=(32, 32), frames=48, audio=str(song) if song else None)
    rec = {"mode": "stems", "layers": layers, "composite": comp}
    (job / "simple" / "simple.json").write_text(json.dumps(rec), encoding="utf-8")
    return job, rec


def _streams(path):
    import subprocess

    from xenoform.video import ffprobe_bin

    return sorted(subprocess.run([ffprobe_bin(), "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0",
                                  str(path)], capture_output=True, text=True).stdout.split())


def test_the_composite_is_rebuilt_byte_for_byte_from_the_record(tmp_path):
    song = _song(tmp_path, "song.wav", sec=2.0)
    job, rec = _stems_job(tmp_path, song)
    first = SC.build(job, rec)
    one = (job / "xenoform.mp4").read_bytes()
    assert first["sha256"] == SC.sha256_of(job / "xenoform.mp4") and first["order"] == ["other", "drums"]
    again = SC.build(job, rec)
    assert (job / "xenoform.mp4").read_bytes() == one and again["sha256"] == first["sha256"]
    assert _streams(job / "xenoform.mp4") == ["audio", "video"]  # the song mixed in once
    px = _frames(job / "xenoform.mp4")[:, 16, 16].mean(axis=1)
    assert px[24] < px[8] - 40  # the drums gone in the middle: the other layer alone, darker


def test_a_prominence_change_recomposites_without_a_render(tmp_path):
    song = _song(tmp_path, "song.wav", sec=2.0)
    job, rec = _stems_job(tmp_path, song)
    SC.build(job, rec)
    before = SC.sha256_of(job / "xenoform.mp4")
    out = SC.rebuild(job, prominence={"other": 1.0, "drums": 0.2}, blend={"drums": "normal", "nope": "add"})
    assert out["composite"]["order"] == ["drums", "other"]  # the other now on top
    assert out["composite"]["prominence"] == {"drums": 0.2, "other": 1.0}
    assert out["composite"]["blends"]["drums"] == "normal" and "nope" not in out["composite"]["blends"]
    assert out["composites"] == 1
    after = SC.sha256_of(job / "xenoform.mp4")
    assert after != before and out["composite"]["sha256"] == after
    saved = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert saved["composite"]["sha256"] == after
    (job / "simple" / "simple.json").write_text(json.dumps({"mode": "simple"}), encoding="utf-8")
    with pytest.raises(ValueError):
        SC.rebuild(job, prominence={"drums": 0.5})


def test_a_missing_layer_or_song_says_so(tmp_path):
    song = _song(tmp_path, "song.wav", sec=2.0)
    job, rec = _stems_job(tmp_path, song)
    Path(rec["layers"][0]["video"]).unlink()
    with pytest.raises(FileNotFoundError, match="drums"):
        SC.build(job, rec)
    job2, rec2 = _stems_job(tmp_path / "b", tmp_path / "gone.wav")
    with pytest.raises(FileNotFoundError, match="song"):
        SC.build(job2, rec2)
