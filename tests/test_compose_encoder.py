"""compose's and reframe_file's encoder (21 Nov 2026): an ffmpeg that takes raw frames on stdin and ends the file at
the song's end (``-shortest``).

When the picture outlasts the song ffmpeg has its file whole, stops reading and leaves with exit 0, and how soon it
closes stdin is the build's: an ffmpeg before 7 closes it about ten frames on (Ubuntu 24.04's 6.1, the smoke CI),
ffmpeg 8 reads on for a while first. The writer met a closed pipe on the one and not on the other, and called it
``BrokenPipeError`` with a good file on disk. Whether the encode worked is ffmpeg's exit code, told with ffmpeg's own
words, and nothing else.

22 Nov 2026: an ffmpeg that stops reading and neither closes its end of the pipe nor leaves. A write into a full pipe
waits without limit, so the cut waited with it. The encoder now waits ``ENCODER_STALL_S`` for a frame to be taken and
no longer, drops the frames still to come, gives ffmpeg ``ENCODER_END_S`` to end on its own (exit 0 is then the song's
end, as ever) and otherwise stops it and says the encode failed."""
import errno
import logging
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from xenoform import beatfx
from xenoform.cloud_morph import custom_shots

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is needed for the clip stubs")

W, H = 64, 112
_POPEN = subprocess.Popen  # the real one, whichever stand-in a test has put in its place
# A stand-in for the encoder: it takes three frames and then does what its mode says. ``leaves`` is ffmpeg at the
# song's end (the file written, exit 0, stdin closed with frames still to come); ``fails`` is an encode that broke
# (exit 3, its reason on stderr, no file); ``says-much`` fails before it reads a frame, after saying more than a
# pipe holds, so a writer that sent its words to a pipe nobody reads would wait for good. ``stalls`` has its file
# written and then neither reads, nor closes its stdin, nor leaves: a writer that only writes waits on it for good.
# ``stalls-until-told`` does the same until a file named after its own with ``.leave`` appears, then leaves with exit 0.
STAND_IN = """
import os
import sys
import time

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
while mode == "stalls" or (mode == "stalls-until-told" and not os.path.exists(out + ".leave")):
    time.sleep(0.01)
"""
_STARTED: list[subprocess.Popen] = []  # every stand-in a test started


@pytest.fixture(autouse=True)
def _no_stand_in_outlives_its_test():
    yield
    while _STARTED:
        proc = _STARTED.pop()
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _in_time(work, seconds: float = 20.0):
    """``work()`` on a thread of its own, its result and how long it took. A writer that waits for good fails its
    test here after ``seconds`` (and the fixture above then stops the stand-in it waits on); it does not hold the
    suite, as the smoke CI was held for six hours."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = work()
        except BaseException as exc:  # noqa: BLE001  (raised again below, in the test's own thread)
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    t0 = time.perf_counter()
    thread.start()
    thread.join(seconds)
    took = time.perf_counter() - t0
    assert not thread.is_alive(), f"the writer is still waiting on its encoder after {seconds:g} s"
    if "error" in box:
        raise box["error"]
    return box.get("value"), took


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
            _STARTED.append(_POPEN([sys.executable, str(script), mode, str(frame_bytes), *list(cmd)[1:]], *args, **kw))
            return _STARTED[-1]
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


# ---------------------------------------------------------------- an ffmpeg that stops reading and stays (22 Nov 2026)
def _impatient(monkeypatch, stall_s: float = 0.1, end_s: float = 0.1) -> None:
    monkeypatch.setattr(beatfx, "ENCODER_STALL_S", stall_s, raising=False)
    monkeypatch.setattr(beatfx, "ENCODER_END_S", end_s, raising=False)


def _encoder(out: Path) -> "beatfx._Encoder":
    return beatfx._Encoder(["ffmpeg", "-f", "rawvideo", "-s", f"{W}x{H}", "-i", "-", str(out)])


FRAME = np.zeros((H, W, 3), np.uint8)
MANY = 60  # 1.3 MB of frames: more than any pipe holds, so the writer must meet the stall


def test_an_encoder_that_stops_reading_and_stays_does_not_hold_the_writer(tmp_path, monkeypatch):
    """The stall itself, on the encoder alone: the stand-in takes three frames and then neither reads, nor closes its
    stdin, nor leaves. The writer that only wrote is still in its write when the suite is cancelled."""
    _impatient(monkeypatch)
    _stand_in(tmp_path, monkeypatch, "stalls", W * H * 3)
    threads = threading.active_count()

    def encode():
        here = threading.active_count()
        enc = _encoder(tmp_path / "cut.mp4")
        assert threading.active_count() == here  # no thread until the first frame: compose forks its workers first
        for _ in range(MANY):
            enc.write(FRAME)
        return enc, *enc.finish()

    (enc, code, said), took = _in_time(encode)
    assert took < 5.0, took  # the encoder's patience (0.1 s and 0.1 s), not the stand-in's, which has no end
    assert enc.stalled >= 0.1 and enc.stopped and code != 0  # it was stopped, and its exit code says so
    assert 3 <= enc.taken < MANY and enc.left == MANY - enc.taken  # the rest were counted and dropped, not written
    assert enc.proc.poll() is not None and threading.active_count() == threads  # nothing is left running
    with pytest.raises(RuntimeError, match=r"ffmpeg could not write the cut: it took no frame for 0\.1 s and did not "
                                           rf"end, so it was stopped after {enc.taken} of {MANY} frames"):
        enc.judge(code, said, "write the cut")


def test_a_stalled_encoder_that_ends_on_its_own_with_exit_0_is_the_songs_end(tmp_path, monkeypatch, caplog):
    """Stalled, with its file whole, and then gone with exit 0 without being stopped: ffmpeg finishing a large file
    (the faststart pass reads nothing). Its exit code is the measure, as ever."""
    _impatient(monkeypatch, end_s=20.0)
    _stand_in(tmp_path, monkeypatch, "stalls-until-told", W * H * 3)
    out = tmp_path / "cut.mp4"

    def encode():
        enc = _encoder(out)
        for _ in range(MANY):
            enc.write(FRAME)
        assert enc.stalled and enc.proc.poll() is None  # stalled, and still there
        Path(str(out) + ".leave").write_bytes(b"")
        return enc, *enc.finish()

    with caplog.at_level(logging.INFO, logger="xenoform.beatfx"):
        (enc, code, said), took = _in_time(encode)
        enc.judge(code, said, "write the cut")  # no error
    assert code == 0 and not enc.stopped and took < 5.0, (code, took)
    assert out.read_bytes() == b"the cut, to the song's end" and enc.left == MANY - enc.taken > 0
    assert any("song's end" in r.getMessage() for r in caplog.records)


def test_an_error_that_is_not_the_closed_pipe_is_still_raised(tmp_path, monkeypatch):
    """The frames go down the pipe on the encoder's own thread now; what the pipe raises there (other than "closed")
    comes out where the frames come from: at the next frame, or from ``judge`` when there is no next frame."""
    _stand_in(tmp_path, monkeypatch, "leaves", W * H * 3)

    class NoRoom:
        def __init__(self, pipe):
            self.pipe = pipe

        def write(self, data):
            raise OSError(errno.ENOSPC, "No space left on device")

        def close(self):
            self.pipe.close()

    def encode(frames: int, pause: float):
        enc = _encoder(tmp_path / "cut.mp4")
        enc.proc.stdin = NoRoom(enc.proc.stdin)
        try:
            for _ in range(frames):
                enc.write(FRAME)
                time.sleep(pause)
        finally:
            code, said = enc.finish()
        return enc, code, said

    with pytest.raises(OSError, match="No space left on device"):
        _in_time(lambda: encode(400, 0.005))  # at the next frame
    (enc, code, said), _ = _in_time(lambda: encode(1, 0.0))
    with pytest.raises(OSError, match="No space left on device"):
        enc.judge(code, said, "write the cut")  # with no next frame, before the exit code is read as a good encode


def test_a_stalled_encoder_fails_the_cut_in_words_and_replaces_nothing(tmp_path, monkeypatch):
    """compose on an encoder that stalls for good: an error that says so, in a moment, and the cut as it was."""
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 3, 3.0)
    out = tmp_path / "cut.mp4"
    out.write_bytes(b"the cut as it was")
    _impatient(monkeypatch)
    _stand_in(tmp_path, monkeypatch, "stalls", W * H * 3)
    with pytest.raises(RuntimeError, match=r"ffmpeg could not write the cut: it took no frame for 0\.1 s and did not "
                                           r"end, so it was stopped after \d+ of 72 frames"):
        _in_time(lambda: beatfx.compose(clips, shots, song, out, **KW))
    assert out.read_bytes() == b"the cut as it was"
    assert all(proc.poll() is not None for proc in _STARTED)  # the stalled encoder was stopped, not left behind


def test_the_flash_tames_frames_meet_the_same_stall(tmp_path, monkeypatch):
    monkeypatch.setenv(beatfx.LOOK_WORKERS_ENV, "1")
    clips, shots, song = _cut(tmp_path, 3, 3.0)
    _impatient(monkeypatch)
    _stand_in(tmp_path, monkeypatch, "stalls", W * H * 3)
    with pytest.raises(RuntimeError, match=r"it took no frame for 0\.1 s and did not end, so it was stopped"):
        _in_time(lambda: beatfx.compose(clips, shots, song, tmp_path / "cut.mp4", tame=[None] * 72, **KW))


def test_reframe_meets_the_same_stall(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", 2.0, 90, audio=True)
    w, h = beatfx.out_size("9:16", "draft")
    dest = tmp_path / "tall.mp4"
    dest.write_bytes(b"the cut as it was")
    _impatient(monkeypatch)
    _stand_in(tmp_path, monkeypatch, "stalls", w * h * 3)
    with pytest.raises(RuntimeError, match=r"ffmpeg could not reframe the cut: it took no frame for 0\.1 s and did not "
                                           r"end, so it was stopped after \d+ of 48 frames"):
        _in_time(lambda: beatfx.reframe_file(src, dest, "9:16"))
    assert dest.read_bytes() == b"the cut as it was"
    assert all(proc.poll() is not None for proc in _STARTED)
