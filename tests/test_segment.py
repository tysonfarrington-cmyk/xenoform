from xenoform.prompting import chunk_drive, prompt_for
from xenoform.segment import plan_chunks, snap_8n1


def _features(n_frames=144, fps=12.0):
    frames = []
    for i in range(n_frames):
        t = i / fps
        if t < 3:
            section, drop, energy = "calm", False, 0.15
        elif t < 6:
            section, drop, energy = "build", False, 0.4
        elif t < 9:
            section, drop, energy = "drop", True, 0.9
        else:
            section, drop, energy = "release", False, 0.35
        frames.append(
            {
                "i": i,
                "t": t,
                "energy": energy,
                "onset_env": 1.0 if i % 12 == 0 else 0.0,
                "section": section,
                "is_drop": drop,
            }
        )
    return {
        "fps": fps,
        "n_frames": n_frames,
        "beats": [i / 2 for i in range(int(n_frames / fps * 2))],
        "sections": [
            {"start_frame": 0, "end_frame": 36, "label": "calm"},
            {"start_frame": 36, "end_frame": 72, "label": "build"},
            {"start_frame": 72, "end_frame": 108, "label": "drop"},
            {"start_frame": 108, "end_frame": n_frames, "label": "release"},
        ],
        "frames": frames,
    }


def test_snap_and_chunks_tile_the_timeline():
    assert snap_8n1(49) == 49
    assert snap_8n1(50) == 49
    assert snap_8n1(1) == 9
    features = _features()
    chunks = plan_chunks(features, target_seconds=4.0, min_seconds=2.8, max_seconds=5.2)
    assert chunks
    cursor = 0
    for chunk in chunks:
        assert chunk["start_frame"] == cursor
        assert (chunk["length"] - 1) % 8 == 0
        assert chunk["length"] >= 9
        assert chunk["pad"] == max(0, chunk["length"] - chunk["source_frames"])
        cursor += chunk["source_frames"]
    assert cursor == features["n_frames"]


def test_drop_chunk_denoises_harder_than_calm():
    features = _features()
    chunks = plan_chunks(features, target_seconds=4.0, min_seconds=2.8, max_seconds=5.2)
    drives = [(chunk["section"], chunk_drive(features["frames"], chunk)) for chunk in chunks]
    calm = next(drive for section, drive in drives if section == "calm")
    drop = next(drive for section, drive in drives if section == "drop")
    assert drop["denoise"] > calm["denoise"]
    assert abs(drop["preserve_strength"] + drop["denoise"] - 1.0) < 1e-6
    prompts = {
        "calm": "chrome",
        "drop": "grotesque circuitry",
        "build": "swelling",
        "release": "settling",
        "sustain": "hover",
    }
    assert prompt_for("drop", prompts) != prompt_for("calm", prompts)
