"""Feature export for TouchDesigner or anything else that speaks OSC.

The core app does not import TouchDesigner and does not require ``python-osc``.
``features.json`` is the source of truth. This module also writes a CSV and an
address map, and can stream the same rows over OSC when python-osc is installed.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

# One address per channel. TouchDesigner OSC In CHOP picks these up by name.
OSC_CHANNELS = (
    "rms",
    "sub",
    "bass",
    "mid",
    "high",
    "onset_env",
    "beat_env",
    "energy",
    "mutate",
    "is_onset",
    "is_beat",
    "is_drop",
)


def address_map() -> dict[str, str]:
    return {f"/xenoform/{name}": "float" for name in OSC_CHANNELS} | {
        "/xenoform/frame": "int",
        "/xenoform/section": "string",
        "/xenoform/fps": "float",
    }


def export_bundle(features: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    features_path = out_dir / "features.json"
    features_path.write_text(json.dumps(features, indent=2), encoding="utf-8")
    map_path = out_dir / "osc_addresses.json"
    map_path.write_text(json.dumps(address_map(), indent=2), encoding="utf-8")
    csv_path = out_dir / "frames.csv"
    fieldnames = ["i", "t", "section", *OSC_CHANNELS]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for frame in features["frames"]:
            row = {key: frame.get(key, "") for key in fieldnames}
            for key in ("is_onset", "is_beat", "is_drop"):
                row[key] = int(bool(frame.get(key)))
            writer.writerow(row)
    return {
        "features": str(features_path),
        "addresses": str(map_path),
        "csv": str(csv_path),
    }


def stream(features: dict[str, Any], host: str, port: int, realtime: bool = True) -> None:
    try:
        from pythonosc.udp_client import SimpleUDPClient
    except ImportError as exc:
        raise RuntimeError(
            "OSC streaming needs the optional python-osc package: pip install 'xenoform[osc]'"
        ) from exc
    import time

    client = SimpleUDPClient(host, int(port))
    fps = float(features["fps"])
    client.send_message("/xenoform/fps", fps)
    period = 1.0 / fps if fps and realtime else 0.0
    for frame in features["frames"]:
        client.send_message("/xenoform/frame", int(frame["i"]))
        client.send_message("/xenoform/section", str(frame["section"]))
        for name in OSC_CHANNELS:
            value = frame.get(name, 0)
            if isinstance(value, bool):
                value = int(value)
            client.send_message(f"/xenoform/{name}", float(value))
        if period:
            time.sleep(period)
