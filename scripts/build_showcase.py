"""Build the instant "Watch one" showcase reel that judges see with no GPU wait.

Cuts a few finished morph clips to the bars of a short track and writes
src/xenoform/ui_static/showcase/showcase.mp4, a poster, and showcase.json.
The desk serves the result as a static file, so it plays in well under a second.

    python scripts/build_showcase.py --track song.wav --clips a.mp4 b.mp4 ... [--seconds 20]

Each clip is trimmed around its middle, where the morph happens. Cuts land on
the bar (every 4 beats) nearest an even share of the track. ffmpeg must be on PATH.

A window of a bundled song, a shot a fixed number of beats (31 Oct 2026: the reel was rebuilt from the loved Cloud
morphs, each 4 s, on 6 beats of Glitch Out at 90 BPM, so the clip plays whole and the drop lands on a cut):

    python scripts/build_showcase.py --track examples/songs/glitch_out.mp3 \
        --features examples/songs/glitch-out.features.json --start 115.8 --shot-beats 6 \
        --clips examples/morphs/black-rose-to-lotus.mp4 ... --size 1024x576 --note "..." --credit "..."

``--features`` is the song's analysis (the bundled songs ship one), so the beat grid is the desk's own and the
window is not re-analysed; ``--start`` snaps to the nearest beat and is where the audio begins; ``--shot-beats N`` cuts
every N beats (the reel is as long as its clips are numerous: 5 clips x 6 beats = 30 beats, 20 s at 90 BPM; ``--seconds``
is ignored); ``--poster-at`` is the second of the reel the poster is taken from.
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
DEFAULT_NOTE = "Pre-rendered with open weights. Plays instantly; no GPU needed."


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


def beat_cuts(features: Path, start: float, shots: int, shot_beats: int) -> tuple[float, list[float], float]:
    """(the audio's start on the song's own beat, the cuts from there, the tempo): shot ``k`` runs from beat
    ``i0 + k * shot_beats`` to the next cut, so every cut is on a beat of the song's analysis."""
    feats = json.loads(features.read_text(encoding="utf-8"))
    beats = [float(b) for b in feats.get("beats") or []]
    if len(beats) < 2:
        raise SystemExit(f"{features} has no beat grid")
    i0 = min(range(len(beats)), key=lambda i: abs(beats[i] - start))
    if i0 + shots * shot_beats >= len(beats):
        raise SystemExit(f"{shots} shots of {shot_beats} beats from {beats[i0]:.2f} s run past the song's last beat")
    t0 = beats[i0]
    cuts = [round(beats[i0 + k * shot_beats] - t0, 3) for k in range(shots + 1)]
    return t0, cuts, float(feats.get("tempo") or 0.0)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True)
    ap.add_argument("--clips", nargs="+", required=True)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--crf", type=int, default=24)
    ap.add_argument("--features", default="", help="the track's analysis json (its beats), instead of analysing the window")
    ap.add_argument("--start", type=float, default=0.0, help="where in the track the reel begins (snapped to a beat with --features)")
    ap.add_argument("--shot-beats", type=int, default=0, help="a shot every N beats of --features (the reel's length follows)")
    ap.add_argument("--size", default=f"{W}x{H}", help="WIDTHxHEIGHT of the reel")
    ap.add_argument("--poster-at", type=float, default=1.0, help="the second of the reel the poster is taken from")
    ap.add_argument("--note", default=DEFAULT_NOTE, help="the note written to showcase.json")
    ap.add_argument("--credit", default="", help="a credit line written to showcase.json")
    args = ap.parse_args()

    width, height = (int(v) for v in args.size.lower().split("x"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clips = [Path(c) for c in args.clips]
    t0 = float(args.start)
    if args.features and args.shot_beats:
        t0, cuts, tempo = beat_cuts(Path(args.features), t0, len(clips), args.shot_beats)
        beats: list[float] = []
    else:
        if args.start:
            raise SystemExit("--start needs --features and --shot-beats (the bar finder analyses the first seconds of the track)")
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
            f"setpts=PTS/{speed:.5f},fps={FPS},scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height},format=yuv420p"
        )
        subprocess.check_call([
            "ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-i", str(clip), "-t", f"{want / speed:.3f}",
            "-vf", vf, "-an", "-c:v", "libx264", "-crf", str(args.crf), "-preset", "slow", "-t", f"{want:.3f}", str(part),
        ])
        parts.append(part)
        shots.append({"clip": clip.name, "start": cuts[i], "end": cuts[i + 1], "source_in": round(start, 3),
                      **({"speed": round(speed, 3)} if speed != 1.0 else {})})
    listing = work / "list.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    reel = out / "showcase.mp4"
    subprocess.check_call([
        "ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-ss", f"{t0:.3f}", "-i", str(args.track),
        "-t", f"{cuts[-1]:.3f}", "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-af", f"afade=t=out:st={max(0.0, cuts[-1] - 0.4):.3f}:d=0.4", "-movflags", "+faststart", str(reel),
    ])
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-ss", f"{args.poster_at}", "-i", str(reel), "-frames:v", "1", "-q:v", "3", str(out / "showcase.jpg")])
    meta = {
        "video": "showcase.mp4",
        "poster": "showcase.jpg",
        "seconds": cuts[-1],
        "tempo": tempo,
        "size": [width, height],
        "track": Path(args.track).name,
        "track_start": round(t0, 3),
        "cuts": cuts,
        "shots": shots,
        "note": args.note,
    }
    if args.shot_beats:
        meta["shot_beats"] = args.shot_beats
    if args.credit:
        meta["credit"] = args.credit
    (out / "showcase.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({"reel": str(reel), "bytes": reel.stat().st_size, "cuts": cuts, "tempo": tempo, "track_start": round(t0, 3)}))


if __name__ == "__main__":
    main()
