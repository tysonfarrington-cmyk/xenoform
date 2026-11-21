"""compose's and reframe_file's encoder (21 Nov 2026): an ffmpeg that takes raw frames on stdin and ends the file at
the song's end (``-shortest``).

When the picture outlasts the song ffmpeg has its file whole, stops reading and leaves with exit 0, and how soon it
closes stdin is the build's: an ffmpeg before 7 closes it about ten frames on (Ubuntu 24.04's 6.1, the smoke CI),
ffmpeg 8 reads on for a while first. The writer met a closed pipe on the one and not on the other, and called it
``BrokenPipeError`` with a good file on disk. Whether the encode worked is ffmpeg's exit code, told with ffmpeg's own
words, and nothing else."""
import logging
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from xenoform import beatfx
from xenoform.cloud_morph import custom_shots

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")

W, H = 64, 112
_POPEN = subprocess.Popen  # the real one, whichever stand-in a test has put in its place
# A stand-in for the encoder: it takes three frames and then does what its mode says. ``leaves`` is ffmpeg at the
# song's end (the file written, exit 0, stdin closed with frames still to come); ``fails`` is an encode that broke
# (exit 3, its reason on stderr, no file); ``says-much`` fails before it reads a frame, after saying more than a
# pipe holds, so a writer that sent its words to a pipe nobody reads would wait for good.
STAND_IN = """
import sys

mode, frame_bytes, out = sys.argv[1], int(sys.argv[2]), sys.argv[-1]
if mode == "says-much":
    sys.stderr.write("word " * 60000 + "the last of many words")
    sys.exit(3)
sys.stdin.buffer.read(3 * frame_bytes)
if mode == "fails":
    sys.stderr.write("no room on the drive")
    sys.exit(3)
with open(out, "wb") as f:
    f.write(b"the cut, to the song's end")
"""


def _clip(path: Path, seconds: float, hue: int, audio: bool = False) -> Path:
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate=24:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=220:sample_rate=44100:duration={seconds}", "-c:a", "aac"]
    subprocess.run([*cmd, "-vf", f"hue=h={hue}", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def _wav(path: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=110:sample_rate=44100:duration={seconds}",
                    "-ac", "2", str(path)], check=True)
    return path


def _frames(path: Path) -> int:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return int(probe.stdout.strip())


def _cut(tmp_path: Path, shots_n: int, song_s: float):
    clips = [_clip(tmp_path / f"c{i}.mp4", 1.0, 40 * i) for i in range(shots_n)]
    shots = custom_shots({"shots": [{"start": float(i), "end": float(i + 1), "render_s": 2} for i in range(shots_n)]}, float(shots_n))
    return clips, shots, _wav(tmp_path / "song.wav", song_s)


def _stand_in(tmp_path: Path, monkeypatch, mode: str, frame_bytes: int) -> None:
    """The raw-frame encoder becomes the stand-in; every other ffmpeg call (the clips' decode, the probes) is real."""
    script = tmp_path / "stand_in_encoder.py"
    script.write_text(STAND_IN, encoding="utf-8")

    def popen(cmd, *args, **kw):
        if kw.get("stdin") == subprocess.PIPE and "rawvideo" in list(cmd) and list(cmd)[-1].endswith(".mp4"):
            return _POPEN([sys.executable, str(script), mode, str(frame_bytes), *list(cmd)[1:]], *args, **kw)
        return _POPEN(cmd, *args, **kw)

    monkeypatch.setattr(subprocess, "Popen", popen)


KW = dict(aspect="9:16", fx=False, size=(W, H), seed=7)


def test_a_picture_that_outlasts_its_song_is_cut_at_the_songs_end(tmp_path, monkeypatch, caplog):
    """The real ffmpeg, six seconds of picture on a one-second song: every build has left long before the last frame
    is offered (ffmpeg 8.1 took 37 frames of such a cut, 6.0 about ten past the song's end)."""
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 6, 1.0)
    out = tmp_path / "cut.mp4"
    with caplog.at_level(logging.INFO, logger="xenoform.beatfx"):
        made = beatfx.compose(clips, shots, song, out, **KW)
    assert made["frames"] == 144 and len(made["centres"]) == 6  # every shot was still worked, as on a build that reads on
    assert 23 <= _frames(out) <= 26  # the song's second, as -shortest cuts it
    assert not (tmp_path / "cut.compose.mp4").exists()
    assert any("song's end" in r.getMessage() for r in caplog.records)  # said once, in the log, not raised


def test_an_encoder_that_leaves_at_the_songs_end_is_no_broken_pipe(tmp_path, monkeypatch):
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 3, 3.0)
    _stand_in(tmp_path, monkeypatch, "leaves", W * H * 3)
    out = tmp_path / "cut.mp4"
    made = beatfx.compose(clips, shots, song, out, **KW)
    assert made["frames"] == 72
    assert out.read_bytes() == b"the cut, to the song's end"  # ffmpeg's file is the cut, put in place


def test_an_encode_that_fails_is_told_with_its_exit_code_and_ffmpegs_words(tmp_path, monkeypatch):
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 3, 3.0)
    out = tmp_path / "cut.mp4"
    out.write_bytes(b"the cut as it was")
    _stand_in(tmp_path, monkeypatch, "fails", W * H * 3)
    with pytest.raises(RuntimeError, match=r"ffmpeg could not write the cut \(exit 3\): no room on the drive") as told:
        beatfx.compose(clips, shots, song, out, **KW)
    assert "Broken pipe" not in str(told.value) and "Invalid argument" not in str(told.value)
    assert out.read_bytes() == b"the cut as it was"  # a failed encode replaces nothing


def test_an_encoder_with_much_to_say_is_heard_out_and_its_last_words_are_told(tmp_path, monkeypatch):
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 3, 3.0)
    _stand_in(tmp_path, monkeypatch, "says-much", W * H * 3)
    with pytest.raises(RuntimeError, match=r"ffmpeg could not write the cut \(exit 3\)") as told:
        beatfx.compose(clips, shots, song, tmp_path / "cut.mp4", **KW)
    assert str(told.value).endswith("the last of many words") and len(str(told.value)) < 600


def test_the_flash_tames_frames_go_through_the_same_writer(tmp_path, monkeypatch):
    """With ``tame`` the frames reach the encoder a few behind, from the tame's own buffer and its flush."""
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 3, 3.0)
    _stand_in(tmp_path, monkeypatch, "leaves", W * H * 3)
    out = tmp_path / "cut.mp4"
    made = beatfx.compose(clips, shots, song, out, tame=[None] * 72, **KW)
    assert made["frames"] == 72 and "tame" in made
    assert out.read_bytes() == b"the cut, to the song's end"


def test_reframe_has_the_same_encoder(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", 2.0, 90, audio=True)
    w, h = beatfx.out_size("9:16", "draft")
    _stand_in(tmp_path, monkeypatch, "leaves", w * h * 3)
    dest = tmp_path / "tall.mp4"
    made = beatfx.reframe_file(src, dest, "9:16")
    assert made["frames"] == 48 and dest.read_bytes() == b"the cut, to the song's end"

    _stand_in(tmp_path, monkeypatch, "fails", w * h * 3)
    dest.write_bytes(b"the cut as it was")
    with pytest.raises(RuntimeError, match=r"ffmpeg could not reframe the cut \(exit 3\): no room on the drive"):
        beatfx.reframe_file(src, dest, "9:16")
    assert dest.read_bytes() == b"the cut as it was"
