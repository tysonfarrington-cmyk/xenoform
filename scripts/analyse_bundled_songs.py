"""(Re)build the shipped analyses of the bundled songs.

For every row of ``examples/songs/songs.json`` this writes ``examples/songs/<id>.features.json`` exactly as the desk's
``/api/analyze`` makes an upload's features (librosa load at the file's own rate, mono; ``analyze.analyze_audio`` with
the desk's config: ``cfg["fps"]`` and ``cfg["analyze"]``), so a bundled song loads at once with no librosa pass. It also
refreshes the manifest's measured fields: ``seconds`` from ffprobe (to 0.1 s) and ``bpm`` from the analysis (rounded).
Titles, feel lines and credits are left as written.

    .venv/Scripts/python.exe scripts/analyse_bundled_songs.py              # every song
    .venv/Scripts/python.exe scripts/analyse_bundled_songs.py glitch-out   # one song

No GPU, no network. A four-minute song takes about half a minute on the CPU. The features files are written compact
(no indentation; the same data) to keep a four-minute song's file near 1.5 MB.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SONGS = ROOT / "examples" / "songs"
MANIFEST = SONGS / "songs.json"
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def ffprobe_seconds(path: Path) -> float | None:
    """The file's length by ffprobe, or None when ffprobe is not on PATH."""
    if shutil.which("ffprobe") is None:
        return None
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    from xenoform.songs_api import analyse

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = manifest["songs"]
    wanted = set(argv) or {row["id"] for row in rows}
    unknown = wanted - {row["id"] for row in rows}
    if unknown:
        print("not in the manifest:", ", ".join(sorted(unknown)))
        return 2
    for row in rows:
        if row["id"] not in wanted:
            continue
        path = SONGS / row["file"]
        if not path.is_file():
            print(f"{row['id']}: missing {path.name}")
            return 1
        print(f"{row['id']}: analysing {path.name}...", flush=True)
        features = analyse(path)
        dest = SONGS / f"{row['id']}.features.json"
        tmp = dest.with_suffix(".json.part")
        tmp.write_text(json.dumps(features, separators=(",", ":")), encoding="utf-8")
        tmp.replace(dest)
        measured = ffprobe_seconds(path)
        if measured is not None:
            row["seconds"] = round(measured, 1)
        row["bpm"] = int(round(float(features.get("tempo") or 0)))
        print(f"  {row['seconds']} s, {row['bpm']} BPM, {features['n_frames']} frames at {features['fps']:g} fps, "
              f"{len(features.get('sections') or [])} sections, {dest.stat().st_size / 1024:.0f} KB")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("manifest refreshed:", MANIFEST.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
