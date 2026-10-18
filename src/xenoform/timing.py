"""Audio is the clock. The picture locks to it. The music is not stretched.

``timing.json`` is the only list of beats, drops, and key actions. Animation
reads that file back before it paints.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def timing_document(features: dict, scenes: list[dict] | None = None, *, seed: int = 2727) -> dict[str, Any]:
    beats = [round(float(beat), 4) for beat in (features.get("beats") or [])]
    drops = []
    for span in features.get("drops") or []:
        if isinstance(span, dict):
            drops.append({"start": round(float(span.get("start") or 0), 4), "end": round(float(span.get("end") or 0), 4)})
    actions = []
    for scene in scenes or []:
        actions.append(
            {
                "t": round(float(scene.get("start") or 0), 4),
                "end": round(float(scene.get("end") or 0), 4),
                "scene": int(scene.get("index") or 0),
                "beat": str(scene.get("beat") or ""),
                "verb": str(scene.get("verb") or ""),
                "moment": str(scene.get("moment") or ""),
            }
        )
    return {
        "version": 1,
        "seed": int(seed),
        "tempo": round(float(features.get("tempo") or 0), 3),
        "duration": round(float(features.get("duration") or 0), 4),
        "fps": float(features.get("fps") or 24),
        "beats": beats,
        "drops": drops,
        "actions": actions,
        "sections": [
            {
                "label": str(section.get("label") or ""),
                "start": round(float(section.get("start") or 0), 4),
                "end": round(float(section.get("end") or 0), 4),
            }
            for section in (features.get("sections") or [])
        ],
        "rule": "The picture locks to these times. The music is not stretched.",
    }


def write_timing(path: Path, document: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return path


def read_timing(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_timing(features: dict, path: Path) -> dict:
    """Replace the beat clock with the file on disk. The picture reads this, not a second analysis."""
    document = read_timing(path)
    features = dict(features)
    features["beats"] = [float(beat) for beat in document.get("beats") or []]
    features["tempo"] = float(document.get("tempo") or features.get("tempo") or 0)
    if document.get("duration"):
        features["duration"] = float(document["duration"])
    return features


def music_command(audio: Path, dest: Path) -> list[str]:
    """Audio only. No picture, no atempo, no stretch."""
    from xenoform.video import ffmpeg_bin

    return [
        ffmpeg_bin(),
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(audio),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(dest),
    ]


def export_music(audio: Path, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = music_command(Path(audio), dest)
    if any(part == "atempo" or str(part).startswith("atempo") for part in command):
        raise RuntimeError("Music export does not stretch the song.")
    subprocess.run(command, check=True)
    return dest
