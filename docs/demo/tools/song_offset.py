"""Where a cut's audio sits in the song: the cut's trimmed wav (work/ui/uploads/<audio id>.wav, named in the job's
meta.json) cross-correlated against the song, at 1 kHz then refined at 8 kHz around the peak. The desk snaps a window's
start back to a beat and keeps no record of it, so the montage measures it.

    python song_offset.py <job id> <requested start>   -> prints the offset in seconds and the match (1.0 = exact)
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(r"C:\Projects\xenoform-rc2")
SONG = ROOT / "examples" / "songs" / "glitch_out.mp3"


def pcm(path, rate, start=0.0, dur=None):
    args = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"] + (["-t", f"{dur:.3f}"] if dur else []) + [
        "-i", str(path), "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(args, capture_output=True, check=True).stdout, np.float32)


def xcorr_peak(a, b):
    """Lag of b inside a (a longer), by FFT correlation of the onset-ish envelopes."""
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    return int(np.argmax(c[: len(a) - len(b) + 1]))


def offset(job, approx, song=SONG):
    """The desk snaps the requested start (``approx``) back to a beat, so the cut starts in the second before it: the
    raw waveforms at 8 kHz, correlated over that second only (a wider search finds a look-alike drop elsewhere)."""
    meta = json.loads((ROOT / "work" / "ui" / "jobs" / job / "meta.json").read_text(encoding="utf-8"))
    cut = ROOT / "work" / "ui" / "uploads" / f"{meta['audio_id']}.wav"
    rate, skip = 8000, 0.5  # past the cut's 0.3 s fade-in
    lo = max(0.0, approx - 1.2)
    a = pcm(song, rate, lo + skip, 1.5 + 6.0)
    b = pcm(cut, rate, skip, 6.0)
    lag = xcorr_peak(a, b) / rate
    score = float(np.dot(a[int(lag * rate):int(lag * rate) + len(b)], b) / (np.linalg.norm(b) * np.linalg.norm(a[int(lag * rate):int(lag * rate) + len(b)]) + 1e-9))
    return round(lo + lag, 4), round(score, 3)


if __name__ == "__main__":
    print(offset(sys.argv[1], float(sys.argv[2])))
