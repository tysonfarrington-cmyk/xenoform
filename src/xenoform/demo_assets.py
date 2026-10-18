"""Write the bundled demo track and picture the first time the desk opens."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("xenoform")


def ensure_demo_assets(root: Path | None = None) -> dict[str, str]:
    """Create examples/demo.wav and examples/demo_base.mp4 when they are missing.

    A checkout that already has both files is left alone. The picture is the
    tiny dry-run cut, so the first open does not download a weight.
    """
    from xenoform.ui import repo_root

    base = Path(root) if root is not None else repo_root()
    examples = base / "examples"
    examples.mkdir(parents=True, exist_ok=True)
    wav = examples / "demo.wav"
    video = examples / "demo_base.mp4"
    made = {"wav": "", "video": ""}
    if not wav.is_file() or wav.stat().st_size < 44:
        from xenoform.synth import synthesize, write_wav

        write_wav(wav, synthesize(duration=12.0, sr=44100, bpm=120, seed=7), 44100)
        made["wav"] = str(wav)
    if not video.is_file() or video.stat().st_size < 100:
        from xenoform.try_it import try_demo

        try_demo(tiny=True, work=base / "work" / "demo-seed", out=video)
        made["video"] = str(video)
    features = examples / "demo_features.json"
    if wav.is_file() and (not features.is_file() or features.stat().st_size < 20):
        from xenoform.analyze import analyze_audio, write_features
        from xenoform.synth import read_wav

        audio, sr = read_wav(wav)
        write_features(features, analyze_audio(audio, sr, fps=12))
        made["features"] = str(features)
    return made
