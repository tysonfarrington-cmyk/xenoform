"""Build the instant "Watch one" showcase reel that judges see with no GPU wait.

Cuts a few finished morph clips to the bars of a short track and writes
src/xenoform/ui_static/showcase/showcase.mp4, a poster, and showcase.json.
The desk serves the result as a static file, so it plays in well under a second.

    python scripts/build_showcase.py --track song.wav --clips a.mp4 b.mp4 ... [--seconds 20]

Each clip is trimmed around its middle, where the morph happens. Cuts land on
the bar (every 4 beats) nearest an even share of the track. ffmpeg must be on PATH.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "xenoform" / "ui_static" / "showcase"
W, H, FPS = 768, 432, 24


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], text=True
    )
    return float(out.strip())


def bar_cuts(track: Path, seconds: float, shots: int) -> tuple[list[float], float, list[float]]:
    from xenoform.analyze import analyze_audio
    from xenoform.synth import read_wav

    wav = Path(tempfile.mkdtemp()) / "track.wav"
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-i", str(track), "-t", f"{seconds}", "-ac", "1", "-ar", "22050", str(wav)])
    audio, sr = read_wav(wav)
    feats = analyze_audio(audio, sr, fps=12)
    beats = [float(b) for b in feats.get("beats") or []]
    bars = beats[::4] if len(beats) >= 8 else beats
    duration = min(seconds, len(audio) / sr)
    cuts = [0.0]
    for i in range(1, shots):
        target = duration * i / shots
        best = min(bars, key=lambda t: abs(t - target)) if bars else target
        if best <= cuts[-1] + 1.0:
            best = target
        cuts.append(round(best, 3))
    cuts.append(round(duration, 3))
    return cuts, float(feats.get("tempo") or 0.0), beats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True)
    ap.add_argument("--clips", nargs="+", required=True)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--crf", type=int, default=24)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clips = [Path(c) for c in args.clips]
    cuts, tempo, beats = bar_cuts(Path(args.track), args.seconds, len(clips))
    work = Path(tempfile.mkdtemp(prefix="showcase_"))
    parts, shots = [], []
    for i, clip in enumerate(clips):
        want = cuts[i + 1] - cuts[i]
        have = probe_duration(clip)
        start = max(0.0, (have - want) / 2.0)
        speed = 1.0
        if have < want:  # stretch a short clip a little rather than freeze
            speed = have / want
            start = 0.0
        part = work / f"part_{i:02d}.mp4"
        vf = (
            f"setpts=PTS/{speed:.5f},fps={FPS},scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},format=yuv420p"
        )
        subprocess.check_call([
            "ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(clip), "-t", f"{want / speed:.3f}",
            "-vf", vf, "-an", "-c:v", "libx264", "-crf", str(args.crf), "-preset", "slow", "-t", f"{want:.3f}", str(part),
        ])
        parts.append(part)
        shots.append({"clip": clip.name, "start": cuts[i], "end": cuts[i + 1], "source_in": round(start, 3)})
    listing = work / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    reel = out / "showcase.mp4"
    subprocess.check_call([
        "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(args.track),
        "-t", f"{cuts[-1]:.3f}", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-af", f"afade=t=out:st={max(0.0, cuts[-1] - 0.4):.3f}:d=0.4", "-movflags", "+faststart", str(reel),
    ])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-ss", "1.0", "-i", str(reel), "-frames:v", "1", "-q:v", "3", str(out / "showcase.jpg")])
    meta = {
        "video": "showcase.mp4",
        "poster": "showcase.jpg",
        "seconds": cuts[-1],
        "tempo": tempo,
        "cuts": cuts,
        "shots": shots,
        "note": "Pre-rendered on an RTX 3080 Ti with open weights (LTX 0.9.5 morphs). Plays instantly; no GPU needed.",
    }
    (out / "showcase.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({"reel": str(reel), "bytes": reel.stat().st_size, "cuts": cuts, "tempo": tempo}))


if __name__ == "__main__":
    main()
