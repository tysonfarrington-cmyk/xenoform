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
    p.parent.mkdir(parents=True, exist_ok=True)
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


# ------------------------------------------------------------------------------------------------ the layers

from xenoform import dense, guardrails, stems_mode  # noqa: E402


def test_layers_are_validated_one_a_stem_four_at_most_never_mixed():
    raw = [{"stem": "drums", "kind": "objects", "pins": {"0": "black/001_rose.jpg"}, "clips": ["a.mp4"], "prominence": 3},
           {"stem": "drums", "kind": "objects"},
           {"stem": "kazoo"},
           {"stem": "other", "kind": "clips", "clips_folder": "C:/clips", "pins": {"1": "x.jpg"}, "blend": "Lighten", "lead": True},
           {"stem": "bass", "kind": "clips"},
           {"stem": "vocals", "on": False},
           {"stem": "bass", "kind": "weird", "lead": True},
           {"stem": "vocals"},
           {"stem": "sub"},
           "nonsense"]
    layers, notes = stems_mode.layers_of(raw, vibe="black")
    assert [l["stem"] for l in layers] == ["drums", "other", "bass", "vocals"]
    drums, other, bass, vocals = layers
    assert drums["kind"] == "objects" and drums["pins"] == {"0": "black/001_rose.jpg"} and "clips" not in drums
    assert drums["prominence"] == 1.0 and drums["blend"] == "screen" and drums["vibe"] == "black"
    assert other["kind"] == "clips" and "pins" not in other and other["clips_folder"] == "C:/clips"
    assert other["blend"] == "lighten" and other["lead"] is True and bass["lead"] is False
    assert bass["kind"] == "objects" and vocals["prominence"] == stems_mode.PROMINENCE_DEFAULT
    text = " | ".join(notes)
    for bit in ("clips were left out", "second drums layer", "not kazoo", "pinned stills were left out", "has none",
                "no kind called weird", "one lead a cut", "4 layers at most", "not a layer"):
        assert bit in text, bit
    only, _ = stems_mode.layers_of([{"stem": "Drums"}, {"stem": "Guitar"}], names=["Drums", "Guitar"])
    assert [l["stem"] for l in only] == ["Drums", "Guitar"]  # your own stems' names


def test_guardrails_validates_the_layers_and_writes_a_stems_line():
    body = {"mode": "stems", "vibe": "black", "layers": [{"stem": "drums", "prominence": 0.8},
                                                         {"stem": "other", "kind": "clips", "clips_folder": "C:/x", "prominence": 0.6},
                                                         {"stem": "bogus"}]}
    clean, rep = guardrails.apply(body)
    assert [l["stem"] for l in clean["layers"]] == ["drums", "other"]
    lines = [m for m in rep["messages"] if m.startswith("[stems]")]
    assert any("not bogus" in m for m in lines)
    assert any("2 layers: drums as objects of black (prominence 0.8, screen), other as your clips (prominence 0.6, screen)"
               " ; the passages are the mix's sections".replace(" ;", ";") in m for m in lines)
    expert, rep2 = guardrails.apply({**body, "expert": True})
    assert [l["stem"] for l in expert["layers"]] == ["drums", "other"]  # a broken layer is structure: even Expert loses it
    plain, rep3 = guardrails.apply({"mode": "simple", "layers": [{"stem": "drums"}]})
    assert "layers" not in plain and not [m for m in rep3["messages"] if m.startswith("[stems]")]
    none, rep4 = guardrails.apply({"mode": "stems", "layers": []})
    assert none["layers"] == [] and any("no layer is on" in m for m in rep4["messages"])
    cloud, rep5 = guardrails.apply({**body, "quality_tier": "cloud"})
    assert any("Cloud Final has no clips path" in m for m in rep5["messages"])


def test_a_layer_body_keeps_the_cuts_knobs_with_its_own_stem_and_stills():
    parent = {"mode": "stems", "vibe": "black", "seed": 100, "macros": {"chaos": 0.3}, "breathe": True, "drop_mode": "auto",
              "end_card": True, "performer": 2, "chain_pins": {"0": "x"}, "morph_targets": ["me.png"], "guardrails": {"x": 1},
              "layers": [{"stem": "drums"}]}
    obj = stems_mode.layer_body(parent, {"stem": "drums", "kind": "objects", "vibe": "liquid-gold", "pins": {"2": "liquid-gold/a.jpg"}},
                                1, avoid=["black/1.jpg", ""], avoid_nouns=["Orb ", "rose"], drive={"stem": "drums"}, own_images=False)
    assert obj["mode"] == "simple" and obj["vibe"] == "liquid-gold" and obj["seed"] == 100 + stems_mode.SEED_STEP
    assert obj["end_card"] is False and obj["performer"] == 0 and obj["breathe"] is True and obj["macros"] == {"chaos": 0.3}
    assert obj["chain_pins"] == {"2": "liquid-gold/a.jpg"} and obj["avoid_stills"] == ["black/1.jpg"]
    assert obj["avoid_nouns"] == ["orb", "rose"]
    assert obj["morph_targets"] == [] and obj["stem_drive"] == {"stem": "drums"} and obj["stem_layer"] == "drums"
    assert "layers" not in obj and "guardrails" not in obj and parent["layers"]  # the parent is left as it was
    first = stems_mode.layer_body(parent, {"stem": "drums", "kind": "objects", "vibe": ""}, 0)
    assert first["vibe"] == "black" and first["morph_targets"] == ["me.png"] and first["seed"] == 100


def test_the_pick_leaves_out_what_earlier_layers_took_by_file_and_by_name():
    from xenoform import morph_pass as mp

    _, plain = mp.pick_stills({"vibe": "bioluminescent", "seed": 1}, 6, record=False)
    names = [r["noun"] for r in plain]
    _, out = mp.pick_stills({"vibe": "bioluminescent", "seed": 1, "avoid_stills": [plain[0]["file"]],
                             "avoid_nouns": [names[1].upper()]}, 6, record=False)
    assert plain[0]["file"] not in {r["file"] for r in out} and names[1] not in {r["noun"] for r in out}
    assert len({r["file"] for r in out}) == 6
    from xenoform import cloud_morph

    _, first = cloud_morph.chain_stills({"vibe": "black"}, 5, record=False)  # the black chain's own path keeps the keys too
    _, black = cloud_morph.chain_stills({"vibe": "black", "avoid_nouns": [first[0]["noun"]]}, 5, record=False)
    assert first[0]["noun"] not in {str(r.get("noun")) for r in black}


def test_a_clips_layer_takes_only_its_clips(tmp_path):
    from xenoform.video import write_mp4

    folder = tmp_path / "clips"
    folder.mkdir()
    for k in range(2):
        write_mp4(folder / f"0{k}_reel.mp4", [np.full((32, 32, 3), 40 * k, np.uint8)] * 72, 24)
    body = stems_mode.layer_body({"vibe": "black", "chain_pins": {"0": "x"}, "morph_targets": ["me.png"]},
                                 {"stem": "other", "kind": "clips", "clips_folder": str(folder)}, 0)
    assert body["morph_source"] == "clips" and len(body["own_clips"]) == 2 and body["morph_targets"] == []
    assert "chain_pins" not in body and "avoid_stills" not in body


# ------------------------------------------------------------------------------------------------ the drive


def _plan_shots(edges, sections, passages, extra=None):
    shots = []
    for i, (a, b) in enumerate(zip(edges, edges[1:])):
        s = {"index": i, "start": float(a), "end": float(b), "seconds": float(b - a), "frames": int(round(b * 24)) - int(round(a * 24)),
             "render_s": 2, "speed": round(2 / (b - a), 3), "effects": [{"type": "punch", "t": float(a), "strength": 0.6}],
             "section": sections[i], "passage": passages[i]}
        s.update((extra or {}).get(i, {}))
        shots.append(s)
    return shots


def test_the_drive_folds_silence_halves_quiet_and_keeps_the_drop_where_the_stem_carries_it():
    edges = [0, 2, 4, 6, 8, 10, 12, 14, 16]
    sections = ["calm", "calm", "calm", "calm", "drop", "drop", "drop", "drop"]
    passages = [0, 0, 0, 0, 1, 1, 1, 1]
    extra = {4: {"event": "drop", "boundary": "drop", "heat": 1.0, "drop_run": 0,
                 "effects": [{"type": "punch", "t": 8.0, "strength": 1.0}, {"type": "stutter", "t": 8.0, "frames": 2, "repeat": 4}]},
             5: {"heat": 1.0, "drop_run": 0}, 6: {"heat": 1.0, "drop_run": 0}, 7: {"heat": 1.0, "drop_run": 0}}
    shots = _plan_shots(edges, sections, passages, extra)
    # silent 0..4 s, quiet 4..8 s, loud (0.9) 8..12 s, half (0.5) 12..16 s
    act = [0.0] * 96 + [0.3] * 96 + [0.9] * 96 + [0.5] * 96
    out, plan = stems_mode.drive((shots, {"name": "story", "shots": []}),
                                 {"stem_drive": {"stem": "drums", "fps": 24, "period": 0.5, "activity": act, "onsets": [8.0, 9.0]}})
    starts = [s["start"] for s in out]
    assert starts == [0.0, 4.0, 8.0, 10.0, 12.0, 14.0]  # the silence one shot, the two quiet ones one, the rest kept
    assert out[0]["stem_silent"] and out[0]["effects"] == [] and out[0]["end"] == 4.0 and out[0]["frames"] == 96
    assert out[1]["seconds"] == 4.0 and not out[1].get("stem_silent") and out[1]["stem_activity"] == 0.3
    assert out[2]["event"] == "drop" and out[2]["boundary"] == "drop" and out[2]["heat"] == 1.0  # it carries the drop
    assert out[4]["heat"] == pytest.approx(0.625)  # the run's heat times how hard the stem plays it (0.5 / 0.8)
    assert [s["index"] for s in out] == list(range(6)) and sum(s["frames"] for s in out) == 384
    assert plan["stem_drive"]["shots_in"] == 8 and plan["stem_drive"]["shots_out"] == 6 and plan["stem_drive"]["silent_s"] == 4.0
    assert plan["stem_drive"]["drops_kept"] == 1 and len(plan["shots"]) == 6
    # the same plan for a stem that is out at the drop: the event, its punch and stutter go, the boundary is a switch
    act2 = [0.9] * 192 + [0.0] * 24 + [0.6] * 168
    out2, plan2 = stems_mode.drive((_plan_shots(edges, sections, passages, extra), {"name": "story"}),
                                   {"stem_drive": {"stem": "other", "fps": 24, "period": 0.5, "activity": act2}})
    drop_shot = next(s for s in out2 if s["start"] == 8.0)
    assert "event" not in drop_shot and drop_shot["boundary"] == "switch"
    assert not [fx for fx in drop_shot["effects"] if fx["type"] == "stutter"]
    assert plan2["stem_drive"]["drops_left"] == 1


def test_the_drive_cuts_a_long_shot_where_its_stem_goes_out_and_comes_back():
    shots = _plan_shots([0, 10, 12], ["release", "release"], [0, 0], {0: {"effects": [{"type": "punch", "t": 0.0}, {"type": "punch", "t": 9.0}],
                                                                         "boundary": "switch", "rest": 2, "rest_s": 1.0}})
    act = [1.0] * 72 + [0.0] * 120 + [1.0] * 96  # in for 3 s, out for 5 s (ten beats), back at 8 s
    out, plan = stems_mode.drive((shots, {}), {"stem_drive": {"stem": "drums", "fps": 24, "period": 0.5, "activity": act}},
                                 {"beats": [i * 0.5 for i in range(24)]})
    assert [(s["start"], s["end"]) for s in out] == [(0.0, 3.0), (3.0, 8.0), (8.0, 10.0), (10.0, 12.0)]
    assert not out[0].get("stem_silent") and out[0]["boundary"] == "switch" and [fx["t"] for fx in out[0]["effects"]] == [0.0]
    assert out[1]["stem_silent"] and out[1]["effects"] == [] and out[1]["stem_cut"]
    assert out[2]["stem_cut"] and "boundary" not in out[2] and out[2]["rest"] == 2  # the return: a fresh morph, its rest kept
    assert all(s["speed"] == round(s["render_s"] / (s["end"] - s["start"]), 3) for s in out[:3])
    assert out[2]["render_s"] == dense._render_s(2.0 - 1.0, 1.25)  # the morph renders for the piece less its rest
    assert plan["stem_drive"]["cuts"] == [3.0, 8.0] and plan["stem_drive"]["shots_in"] == 2
    assert stems_mode.silences(np.asarray(act, float), 24, 0.5) == [(3.0, 8.0)]
    assert stems_mode.silences(np.asarray([1.0] * 24 + [0.0] * 36 + [1.0] * 24, float), 24, 0.5) == []  # three beats: not a bar
    # the cuts fall on the beat inside the silence: the first beat after it starts, the last before it ends
    odd = [1.0] * 70 + [0.0] * 124 + [1.0] * 94  # out from 2.92 s to 8.08 s
    _, plan2 = stems_mode.drive((_plan_shots([0, 10, 12], ["release", "release"], [0, 0]), {}),
                                {"stem_drive": {"stem": "drums", "fps": 24, "period": 0.5, "activity": odd}}, {"beats": [i * 0.5 for i in range(24)]})
    assert plan2["stem_drive"]["cuts"] == [3.0, 8.0]


def test_under_full_breathe_a_layer_keeps_its_scenes_and_its_stem_still_cuts_them():
    """Breathe round two: a calm passage is a scene (holds of three to four bars, a morph then a rest). A layer whose stem
    plays it keeps the scene as planned; a stem that goes out for a bar inside a scene still cuts it there and on its
    return, and a piece with no room for a morph before its rest gives the rest up."""
    directed = {"duration": 48.0, "beats": [i * 0.5 for i in range(96)], "tempo": 120,
                "sections": [{"label": "calm", "start": 0.0, "end": 20.0, "level": 0.4, "role": "calm"},
                             {"label": "build", "start": 20.0, "end": 28.0, "level": 0.7, "role": "build"},
                             {"label": "drop", "start": 28.0, "end": 40.0, "level": 0.95, "role": "drop"},
                             {"label": "calm", "start": 40.0, "end": 48.0, "level": 0.5, "role": "calm"}]}
    state = {"energy_preset": "dense", "quality_tier": "draft", "aspect": "16:9", "drop_mode": "auto", "breathe": 1.0}
    plain, _ = dense.shots_for(state, directed, None, drop=28.0)
    scenes = [s for s in plain if s["section"] == "calm"]
    assert scenes and all(s.get("rest") for s in scenes)  # the planner's scenes rest
    full = {"stem": "other", "fps": 24, "period": 0.5, "activity": [1.0] * (24 * 48)}
    kept, _ = dense.shots_for({**state, "stem_drive": full}, directed, None, drop=28.0)
    assert [(s["start"], s["end"], s.get("rest"), s.get("rest_s")) for s in kept] == \
        [(s["start"], s["end"], s.get("rest"), s.get("rest_s")) for s in plain]  # a stem that plays: the cut as planned
    out_act = [1.0] * (24 * 48)
    for k in range(6 * 24, 10 * 24):  # out for two bars inside the second scene's run-up
        out_act[k] = 0.0
    cut, plan = dense.shots_for({**state, "stem_drive": {**full, "activity": out_act}}, directed, None, drop=28.0)
    assert plan["stem_drive"]["cuts"] == [6.0, 10.0]
    silent = next(s for s in cut if s.get("stem_silent"))
    back = next(s for s in cut if s.get("stem_cut") and not s.get("stem_silent"))
    assert (silent["start"], silent["end"]) == (6.0, 10.0) and "rest" not in silent
    assert back["start"] == 10.0 and "rest" not in back  # four beats with a four-beat rest: no room for the morph
    assert back["render_s"] >= 2 and back["speed"] == round(back["render_s"] / (back["end"] - back["start"]), 3)
    assert [s.get("rest") for s in cut if s["start"] in (0.0, 12.0, 40.0)] == [4, 8, 8]  # the other scenes keep theirs


def test_the_drive_never_merges_across_a_passage_and_leaves_a_plan_without_a_drive_alone():
    edges = [0, 2, 4, 6, 8]
    shots = _plan_shots(edges, ["calm", "calm", "build", "build"], [0, 0, 1, 1], {2: {"boundary": "switch"}})
    act = [0.3] * 192
    out, _ = stems_mode.drive((shots, {}), {"stem_drive": {"stem": "bass", "fps": 24, "period": 0.5, "activity": act}})
    assert [s["start"] for s in out] == [0.0, 4.0]  # two quiet pairs, one a passage
    same, plan = stems_mode.drive((shots, {"name": "x"}), {})
    assert same is shots and plan == {"name": "x"}


def test_shots_for_runs_the_drive_for_a_layer(monkeypatch):
    directed = {"duration": 30.0, "beats": [i * 0.5 for i in range(60)],
                "sections": [{"label": "calm", "start": 0.0, "end": 12.0, "level": 0.4},
                             {"label": "drop", "start": 12.0, "end": 24.0, "level": 0.9},
                             {"label": "calm", "start": 24.0, "end": 30.0, "level": 0.4}]}
    state = {"energy_preset": "dense", "quality_tier": "draft", "aspect": "16:9", "drop_mode": "auto"}
    plain, _ = dense.shots_for(state, directed, None, drop=12.0)
    act = [0.0] * (12 * 24) + [1.0] * (12 * 24) + [0.0] * (6 * 24)
    driven, plan = dense.shots_for({**state, "stem_drive": {"stem": "drums", "fps": 24, "period": 0.5, "activity": act}},
                                   directed, None, drop=12.0)
    assert len(driven) < len(plain)
    assert driven[0]["stem_silent"] and driven[0]["start"] == 0.0 and driven[0]["end"] == 12.0
    assert driven[-1]["stem_silent"] and plan["stem_drive"]["silent_s"] == 18.0
    assert any(s.get("event") == "drop" for s in driven)  # the drums carry the drop
    assert abs(sum(s["seconds"] for s in driven) - 30.0) < 1e-6


def test_a_lead_layer_splits_the_passages_where_its_stem_goes_out():
    directed = {"duration": 32.0, "beats": [i * 0.5 for i in range(64)],
                "sections": [{"label": "calm", "start": 0.0, "end": 16.0, "level": 0.5, "role": "calm"},
                             {"label": "drop", "start": 16.0, "end": 32.0, "level": 0.9, "role": "drop"}]}
    curve = [1.0] * (6 * 24) + [0.0] * (6 * 24) + [1.0] * (20 * 24)
    rows = stems_mode.lead_sections(directed, curve, 24)
    assert [(r["role"], r["start"], r["end"]) for r in rows] == [("calm", 0.0, 6.0), ("release", 6.0, 12.0),
                                                                ("calm", 12.0, 16.0), ("drop", 16.0, 32.0)]
    assert rows[1]["lead_out"] is True
    short = [1.0] * (6 * 24) + [0.0] * 24 + [1.0] * (25 * 24)  # out for under two bars: no passage of its own
    assert [r["role"] for r in stems_mode.lead_sections(directed, short, 24)] == ["calm", "drop"]


SECTIONS = [{"label": "calm", "start": 0.0, "end": 8.0, "level": 0.4},
            {"label": "drop", "start": 8.0, "end": 16.0, "level": 0.9},
            {"label": "calm", "start": 16.0, "end": 24.0, "level": 0.5}]


@pytest.fixture
def fake_render(monkeypatch, stems_dir):
    """The mock engine's morphs as empty files and the compositor's layer cuts as tiny grey clips of the right length:
    every layer is a real file the composite lays together, in seconds."""
    import xenoform.cloud_morph as cm
    from xenoform import beatfx

    made = {"mock": [], "compose": []}
    levels = iter([200, 90, 150, 60, 210, 120, 170, 80] * 8)

    def fake_mock_clips(shots, stills, work, w, h):
        out = []
        for i in range(len(shots)):
            p = Path(work) / f"mock{i:02d}.mp4"
            p.write_bytes(b"mp4")
            out.append(p)
        made["mock"].append([s.get("file") for s in stills])
        return out

    def fake_compose(clips, shots, audio, out, **kw):
        frames = sum(int(s["frames"]) for s in shots)
        _solid(out, next(levels), frames=frames)
        made["compose"].append({"shots": [dict(s) for s in shots], "out": str(out), "audio": str(audio)})
        return {"frames": frames, "seconds": frames / 24.0, "size": "32x32", "aspect": kw["aspect"], "fx": True, "overlay": False,
                "centres": [], "fps": 24, "look": {}, "boundary_fx": {}}

    monkeypatch.setattr(cm, "_mock_clips", fake_mock_clips)
    monkeypatch.setattr(beatfx, "compose", fake_compose)
    return made


def _stems_make(tmp_path, job, layers, sec=24.0, sections=None, **extra):
    song = _song(tmp_path, "song.wav", sec=sec)
    beats = [i * 0.5 for i in range(int(sec * 2))]
    directed = {"duration": sec, "beats": beats, "sections": [dict(s) for s in (sections or SECTIONS)]}
    body = {"mode": "stems", "vibe": "liquid-gold", "aspect": "16:9", "energy_preset": "dense", "quality_tier": "draft",
            "dance_fx": "off", "drop_mode": "auto", "seed": 5, "layers": layers, **extra}
    clean, rep = guardrails.apply(body, duration=sec, beats=beats)
    seen = []
    job.mkdir(parents=True, exist_ok=True)
    rec = dense.run_simple(directed, song, job / "xenoform.mp4", job, {}, clean, lambda *a: seen.append(a), engine="mock")
    return rec, rep, seen, song


TWO = [{"stem": "drums", "kind": "objects", "prominence": 0.8}, {"stem": "other", "kind": "objects", "prominence": 0.5}]


def test_a_stems_make_cuts_each_layer_on_its_stem_and_lays_them_together(tmp_path, fake_render):
    job = tmp_path / "job"
    rec, rep, seen, song = _stems_make(tmp_path, job, [dict(l) for l in TWO])
    assert any(m.startswith("[stems] 2 layers: drums as objects of liquid-gold (prominence 0.8") for m in rep["messages"])
    assert rec["mode"] == "stems" and [l["stem"] for l in rec["layers"]] == ["drums", "other"]
    assert rec["composite"]["order"] == ["other", "drums"]  # the most prominent on top
    assert rec["stems"]["engine"] == "fake" and rec["stems"]["names"] == ["drums", "bass", "other", "vocals"]
    saved = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4") and saved["layers"][0]["video"].endswith("xenoform.mp4")
    assert _streams(job / "xenoform.mp4") == ["audio", "video"] and _frames(job / "xenoform.mp4").shape[0] == 576
    drums = json.loads((job / "layers" / "drums" / "simple" / "simple.json").read_text(encoding="utf-8"))
    other = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    # the drums are out in the breakdown (the middle fifth): one silent shot there; the other is silent before and after it
    gap = [s for s in drums["shots"] if s.get("stem_silent")]
    assert gap and all(9.0 <= s["start"] and s["end"] <= 15.5 for s in gap)
    assert other["shots"][0].get("stem_silent") and other["shots"][0]["start"] == 0.0
    assert other["shots"][-1].get("stem_silent")
    assert len(drums["shots"]) != len(other["shots"])  # each layer cut on its own stem's drive
    assert not set(drums["stills"]) & set(other["stills"])  # no object twice across layers (the same vibe)
    nouns = [stems_mode._chain_nouns(job / "layers" / s) for s in ("drums", "other")]
    assert nouns[0] and nouns[1] and not set(nouns[0]) & set(nouns[1])  # by name too
    assert (job / "simple" / "chain.json").is_file()
    assert any("Drums layer (1 of 2)" in a[2] for a in seen) and any("Other layer (2 of 2)" in a[2] for a in seen)
    assert all(a[0] in ("restyle", "assemble") for a in seen)
    # deterministic from the record: the same file again, byte for byte
    first = (job / "xenoform.mp4").read_bytes()
    SC.build(job, saved)
    assert (job / "xenoform.mp4").read_bytes() == first
    # a layer re-cut from its cached morphs with its own timeline edit, then the knobs over every layer
    out = dense.recut_from_cache(job, {"layer": "drums", "shot_overrides": {"1": {"play": "hold"}}})
    assert out["recuts"] == 1
    drums2 = json.loads((job / "layers" / "drums" / "simple" / "simple.json").read_text(encoding="utf-8"))
    other2 = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert drums2["shot_overrides"] == {"1": {"play": "hold"}} and drums2["recuts"] == 1 and not other2.get("recuts")
    out = dense.recut_from_cache(job, {"macros": {"chaos": 0.1}, "shot_overrides": {"0": {"play": "hold"}}})
    other3 = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert out["recuts"] == 2 and other3["recuts"] == 1 and not other3.get("shot_overrides")  # maps need a layer
    with pytest.raises(ValueError):
        dense.recut_from_cache(job, {"layer": "vocals"})


def test_a_stems_make_says_no_before_it_renders(tmp_path, fake_render):
    with pytest.raises(RuntimeError, match="needs a layer"):
        _stems_make(tmp_path / "a", tmp_path / "a" / "job", [])
    with pytest.raises(RuntimeError, match="not your clips"):
        _stems_make(tmp_path / "b", tmp_path / "b" / "job", [{"stem": "other", "kind": "clips", "clips_folder": str(tmp_path)}],
                    quality_tier="cloud", cloud_final_ok=True)
    assert not fake_render["compose"]


def test_an_objects_layer_and_a_clips_layer_run_at_once_each_unmixed(tmp_path, fake_render):
    from xenoform.video import write_mp4

    folder = tmp_path / "reels"
    folder.mkdir()
    for k in range(2):
        write_mp4(folder / f"0{k}_reel{k}.mp4", [np.full((36, 64, 3), 60 + 90 * k, np.uint8)] * 96, 24)
    job = tmp_path / "job"
    layers = [{"stem": "drums", "kind": "objects", "prominence": 0.8},
              {"stem": "other", "kind": "clips", "clips_folder": str(folder), "prominence": 0.6, "pins": {"0": "x.jpg"}}]
    rec, rep, seen, song = _stems_make(tmp_path, job, layers)
    drums = json.loads((job / "layers" / "drums" / "simple" / "simple.json").read_text(encoding="utf-8"))
    other = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert drums.get("source") != "clips" and drums["stills"] and not drums["own"]["clips"]  # objects only
    assert other["source"] == "clips" and other["stills"] == [] and len(other["own_clips"]) == 2  # clips only
    assert any("its pinned stills were left out" in m for m in rep["messages"])
    assert rec["layers"][1]["kind"] == "clips" and (job / "xenoform.mp4").is_file()
    with pytest.raises(RuntimeError, match="clips were not found"):
        _stems_make(tmp_path / "z", tmp_path / "z" / "job", [{"stem": "other", "kind": "clips", "clips_folder": str(tmp_path / "none")}])


def test_a_lead_layer_sets_the_passages_for_every_layer(tmp_path, fake_render):
    job = tmp_path / "job"
    layers = [{"stem": "drums", "kind": "objects", "prominence": 0.8, "lead": True}, {"stem": "other", "kind": "objects", "prominence": 0.5}]
    sections = [{"label": "calm", "start": 0.0, "end": 14.0, "level": 0.4}, {"label": "drop", "start": 14.0, "end": 26.0, "level": 0.9},
                {"label": "calm", "start": 26.0, "end": 40.0, "level": 0.5}]
    rec, rep, seen, song = _stems_make(tmp_path, job, layers, sec=40.0, sections=sections)  # the drums out from 16 s to 24 s
    assert rec["lead"] == "drums" and any(s.get("lead_out") for s in rec["sections"])
    assert any("the passages follow the drums" in m for m in rep["messages"])
    other = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert any(s.get("section") == "release" for s in other["shots"])  # the drums' breakdown is a passage for the other too


def test_the_desk_routes_split_lane_and_recomposite(tmp_path, fake_render, monkeypatch):
    from fastapi.testclient import TestClient

    from xenoform import ui

    work = tmp_path / "work"
    monkeypatch.setattr(ui, "work_dir", lambda: work)
    job = work / "jobs" / "abc12345"
    rec, rep, seen, song = _stems_make(tmp_path, job, [dict(l) for l in TWO])
    c = TestClient(ui.create_app())
    lane = c.get("/api/videos/abc12345/shots").json()
    assert lane["mode"] == "stems" and [l["stem"] for l in lane["layers"]] == ["drums", "other"]
    assert lane["layer"] == "drums" and lane["swappable"] is True and lane["rerenderable"] is True  # a layer's own (1 Nov)
    assert lane["insertable"] is False and lane["dreamable"] is False  # Generate here and Dream: not on a layer
    assert lane["shots"] == lane["layers"][0]["lane"]["shots"] and lane["layers"][1]["lane"]["tl_key"] == "abc12345:other"
    assert 0 < len(lane["layers"][0]["envelope"]) <= stems.ENVELOPE_POINTS and len(lane["layers"][1]["alpha"]) > 0
    assert lane["order"] == ["other", "drums"] and lane["prominence"] == {"drums": 0.8, "other": 0.5}
    before = rec["composite"]["sha256"]
    assert c.post("/api/jobs/abc12345/composite", json={"prominence": {"nope": 1}}).status_code == 400
    assert c.post("/api/jobs/abc12345/composite", json={"blend": {"drums": "dodge"}}).status_code == 400
    r = c.post("/api/jobs/abc12345/composite", json={"prominence": {"other": 1.0}, "blend": {"drums": "add"}})
    assert r.status_code == 200 and r.json()["status"] == "running"
    for _ in range(400):
        j = c.get("/api/jobs/abc12345").json()
        if j["status"] != "running":
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["detail"] == "Laid together again" and j["video_version"] == 1
    saved = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert saved["composite"]["order"] == ["drums", "other"] and saved["composite"]["blends"]["drums"] == "add"
    assert saved["composite"]["sha256"] != before and saved["composites"] == 1
    r = c.post("/api/jobs/abc12345/recut", json={"layer": "other", "shot_overrides": {"2": {"play": "hold"}}})
    assert r.status_code == 200
    for _ in range(400):
        j = c.get("/api/jobs/abc12345").json()
        if j["status"] != "running":
            break
        time.sleep(0.05)
    assert j["detail"] == "Re-cut ready"
    other = json.loads((job / "layers" / "other" / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert other["shot_overrides"] == {"2": {"play": "hold"}}
    plain = work / "jobs" / "plain0001"
    (plain / "simple").mkdir(parents=True)
    (plain / "simple" / "simple.json").write_text(json.dumps({"shots": []}), encoding="utf-8")
    (plain / "xenoform.mp4").write_bytes(b"x")
    assert c.post("/api/jobs/plain0001/composite", json={}).status_code == 400
    assert c.post("/api/jobs/nothere1/composite", json={}).status_code == 404


def test_the_split_and_status_routes(tmp_path, stems_dir):
    from fastapi.testclient import TestClient

    from xenoform import ui

    song = _song(tmp_path, "s.wav", sec=12.0)
    c = TestClient(ui.create_app())
    assert c.get("/api/stems/status", params={"path": str(song)}).json()["status"] == "none"  # not the {sid} route
    first = c.post("/api/stems/split", json={"path": str(song)})
    assert first.status_code == 200 and first.json()["status"] in ("running", "done") and "path" not in first.json()
    for _ in range(200):
        st = c.get("/api/stems/status", params={"path": str(song)}).json()
        if st["status"] != "running":
            break
        time.sleep(0.05)
    assert st["status"] == "done" and [r["name"] for r in st["stems"]] == ["drums", "bass", "other", "vocals"]
    assert st["engine"] == "fake" and all(len(r["envelope"]) <= stems.ENVELOPE_POINTS for r in st["stems"])
    assert c.get("/api/stems/status", params={"path": str(tmp_path / "x.txt")}).status_code == 400
    assert c.post("/api/stems/split", json={"audio_id": "not-loaded-xyz"}).status_code == 404


def test_the_clock_counts_every_layer():
    plan = {"analyze": 3.0, "morphs": 100.0, "cut": 40.0, "qa": 5.0}
    out = stems_mode.timing(plan, {"layers": [{"stem": "drums"}, {"stem": "other"}, {"stem": "bass", "on": False}]}, 30.0)
    assert out["morphs"] == 280.0 and out["cut"] == pytest.approx(stems_mode.COMPOSITE_BASE_S + stems_mode.COMPOSITE_S_PER_S * 30.0)
    assert dense.wants_finishing({"mode": "stems", "energy_preset": "flow", "aspect": "16:9"})
