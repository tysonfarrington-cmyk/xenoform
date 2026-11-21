"""Stop on a Stems cut's re-cut and on "Lay them again" (docs/notes/review-21nov.md, the two Stems Stop bugs).

A Stop that ends the edit must leave every file and record of the cut as it was; a Stop that comes after the cut is
replaced must be told it came too late. Before: the re-cut's progress callback raised on Stop at a report that came
after ``xenoform.mp4`` was replaced (and, on a knob re-cut, after the first layer's cut and record were), so the job
said "the cut is as it was" over a changed cut; and "Lay them again" had no Stop of its own, so it could not be stopped.

The layers' cuts are test_stems_mode's fakes (tiny grey clips); the composite is the real ffmpeg, except where a test
needs ffmpeg to still be running when Stop arrives: there ``slow_ffmpeg`` stands in for it (a process that begins its
file and would run a minute), so the Stop provably ends a running process."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from xenoform import stems_composite as SC
from xenoform import stems_mode
from xenoform.turbo import JobCancelled

from test_stems_mode import TWO, _song, _stems_job, _stems_make, fake_render, stems_dir  # noqa: F401  (fixtures)

JOB = "stemstop1"
KNOBS = {"macros": {"chaos": 0.1}}  # a knob re-cut: every layer is re-cut, then the layers are laid together


def _state(job: Path) -> dict:
    """Everything of a Stems cut an edit may replace: the cut and each layer's cut (bytes), and their records (text)."""
    out = {"cut": (job / "xenoform.mp4").read_bytes(), "record": (job / "simple" / "simple.json").read_text(encoding="utf-8")}
    for stem in ("drums", "other"):
        folder = job / "layers" / stem
        if folder.is_dir():
            out[f"{stem} cut"] = (folder / "xenoform.mp4").read_bytes()
            out[f"{stem} record"] = (folder / "simple" / "simple.json").read_text(encoding="utf-8")
    return out


def _left_beside(job: Path) -> list[str]:
    """What a re-cut or a composite makes beside the cut before it is put in place: none of it outlives the edit."""
    names = ("xenoform.recut.mp4", "composite.mp4", "composite.composite.mp4")
    return sorted(p.relative_to(job).as_posix() for p in job.rglob("*") if p.name in names)


class _SlowFfmpeg:
    """Stands in for ``subprocess`` inside stems_composite once ``take_over`` is called: an ffmpeg that has begun its
    output file and would run for a minute."""

    DEVNULL = subprocess.DEVNULL
    TimeoutExpired = subprocess.TimeoutExpired
    BODY = "import sys, time; open(sys.argv[1], 'wb').write(b'half'); time.sleep(60)"

    def __init__(self, monkeypatch):
        self._monkeypatch = monkeypatch
        self.procs: list[subprocess.Popen] = []
        self.files: list[Path] = []

    def take_over(self) -> None:
        self._monkeypatch.setattr(SC, "subprocess", self)

    def Popen(self, cmd, **kw):  # noqa: N802  (subprocess's own name)
        self.files.append(Path(cmd[-1]))
        self.procs.append(subprocess.Popen([sys.executable, "-c", self.BODY, str(cmd[-1])], **kw))
        return self.procs[-1]

    def writing(self) -> bool:
        """True once the stand-in runs and has begun its file: the composite is under way."""
        return bool(self.files) and self.files[-1].is_file()

    def ended(self) -> bool:
        return bool(self.procs) and all(p.poll() is not None for p in self.procs)


@pytest.fixture
def slow_ffmpeg(monkeypatch):
    slow = _SlowFfmpeg(monkeypatch)
    yield slow
    for proc in slow.procs:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


class _StopAtReport:
    """A desk's progress callback with Stop pressed at its ``k``-th report: it raises there, as the re-cut route's does."""

    def __init__(self, k: int):
        self.k, self.lines = k, []

    def __call__(self, stage: str, frac: float, detail: str) -> None:
        self.lines.append(detail)
        if len(self.lines) == self.k:
            raise JobCancelled("Stopped")


# ------------------------------------------------------------------------------------------------ the composite


def test_nothing_is_reported_once_the_composite_has_replaced_the_cut(tmp_path):
    """The report that raised on Stop came after the file was replaced. Every report now finds the cut's old file."""
    job, rec = _stems_job(tmp_path, _song(tmp_path, "song.wav", sec=2.0))
    SC.build(job, rec)
    old = SC.sha256_of(job / "xenoform.mp4")
    seen = []
    out = SC.rebuild(job, prominence={"other": 1.0, "drums": 0.2},
                     report=lambda stage, frac, detail: seen.append((detail, SC.sha256_of(job / "xenoform.mp4"))))
    assert [d for d, _ in seen][-1] == "The layers are laid together" and len(seen) >= 2
    assert all(sha == old for _, sha in seen)
    assert out["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4") != old and _left_beside(job) == []


def test_a_report_that_raises_on_stop_leaves_the_file_and_the_record_whatever_report_it_is(tmp_path):
    job, rec = _stems_job(tmp_path, _song(tmp_path, "song.wav", sec=2.0))
    SC.build(job, rec)
    before = _state(job)
    stopped = []
    for k in range(1, 10):
        stop = _StopAtReport(k)
        try:
            SC.rebuild(job, prominence={"other": 1.0, "drums": 0.2}, report=stop)
        except JobCancelled:
            stopped.append(stop.lines[-1])
            assert _state(job) == before, f"Stop at report {k} ({stop.lines[-1]}) changed the cut"
            assert _left_beside(job) == []
            continue
        break
    assert "The layers are laid together" in stopped  # the last report, the one that used to follow the publish
    assert _state(job)["cut"] != before["cut"] and json.loads(_state(job)["record"])["composites"] == 1


def test_stop_ends_ffmpeg_while_the_layers_are_laid_and_the_cut_is_as_it_was(tmp_path, slow_ffmpeg):
    job, rec = _stems_job(tmp_path, _song(tmp_path, "song.wav", sec=2.0))
    SC.build(job, rec)
    before = _state(job)
    slow_ffmpeg.take_over()
    t0 = time.perf_counter()
    with pytest.raises(JobCancelled):
        SC.rebuild(job, prominence={"other": 1.0, "drums": 0.2}, cancel=slow_ffmpeg.writing)
    assert time.perf_counter() - t0 < 30  # it did not wait for ffmpeg's minute
    assert len(slow_ffmpeg.procs) == 1 and slow_ffmpeg.ended()  # ffmpeg was ended, not left running
    assert _state(job) == before and _left_beside(job) == []  # its half-written file is gone too


def test_a_stop_set_before_the_composite_starts_no_ffmpeg(tmp_path, slow_ffmpeg):
    job, rec = _stems_job(tmp_path, _song(tmp_path, "song.wav", sec=2.0))
    SC.build(job, rec)
    before = _state(job)
    slow_ffmpeg.take_over()
    with pytest.raises(JobCancelled):
        SC.rebuild(job, blend={"drums": "add"}, cancel=lambda: True)
    assert slow_ffmpeg.procs == [] and _state(job) == before


def test_ffmpegs_own_failure_is_still_told_in_its_words_and_leaves_no_file(tmp_path):
    job, rec = _stems_job(tmp_path, _song(tmp_path, "song.wav", sec=2.0))
    SC.build(job, rec)
    before = _state(job)
    Path(rec["layers"][0]["video"]).write_bytes(b"not a film")
    with pytest.raises(RuntimeError, match=r"ffmpeg could not lay the layers together \(exit \d+\): \S"):
        SC.rebuild(job, blend={"drums": "add"}, cancel=lambda: False)
    assert _state(job) == before and _left_beside(job) == []


# ------------------------------------------------------------------------------------------------ the re-cut


def test_a_stems_recut_stopped_at_any_report_leaves_every_file_and_record_as_it_was(tmp_path, fake_render):
    """Stop is tried at each report of a knob re-cut in turn: in the first layer's re-cut, in the second's (the first
    used to be published by then), before the composite and after it (it used to be published by then)."""
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)
    assert len(before) == 6 and _left_beside(job) == []
    stopped = []
    for k in range(1, 30):
        stop = _StopAtReport(k)
        try:
            out = stems_mode.recut(job, dict(KNOBS), report=stop)
        except JobCancelled:
            stopped.append(stop.lines[-1])
            assert _state(job) == before, f"Stop at report {k} ({stop.lines[-1]}) changed the cut"
            assert _left_beside(job) == []
            continue
        break
    assert any("Other layer (2 of 2)" in line for line in stopped)  # Stop in the second layer, the first already re-cut
    assert stopped[-1] == "The layers are laid together"  # and at the very last report
    after = _state(job)
    assert all(after[key] != before[key] for key in before)  # run to its end, all of it landed
    saved = json.loads(after["record"])
    assert out["recuts"] == saved["recuts"] == 1 and [l["recuts"] for l in saved["layers"]] == [1, 1]
    assert saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4") and _left_beside(job) == []
    SC.build(job, saved)  # laid from the layers' re-cuts before they were put in place: the same file as from them now
    assert (job / "xenoform.mp4").read_bytes() == after["cut"]


def test_a_stems_recut_stopped_while_ffmpeg_lays_the_layers_has_landed_nothing(tmp_path, fake_render, slow_ffmpeg):
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)
    composed = len(fake_render["compose"])
    slow_ffmpeg.take_over()
    with pytest.raises(JobCancelled):
        stems_mode.recut(job, dict(KNOBS), cancel=slow_ffmpeg.writing)
    assert len(fake_render["compose"]) - composed == 2  # both layers were re-cut before Stop came
    assert slow_ffmpeg.ended() and _state(job) == before and _left_beside(job) == []


def test_a_layers_recut_made_beside_its_cut_is_put_in_place_by_land_recut(tmp_path, fake_render):
    from xenoform import dense

    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    drums = job / "layers" / "drums"
    before = _state(job)
    rec = dense.recut_from_cache(drums, {"shot_overrides": {"1": {"play": "hold"}}}, stage=True)
    assert _state(job) == before and (drums / dense.RECUT_FILE).is_file() and rec["recuts"] == 1
    staged = (drums / dense.RECUT_FILE).read_bytes()
    dense.land_recut(drums, rec)
    assert (drums / "xenoform.mp4").read_bytes() == staged and not (drums / dense.RECUT_FILE).exists()
    saved = json.loads((drums / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert saved["shot_overrides"] == {"1": {"play": "hold"}} and saved["recuts"] == 1


# ------------------------------------------------------------------------------------------------ the desk


@pytest.fixture
def desk(tmp_path, fake_render, monkeypatch):
    """A desk with one finished two-layer Stems cut (``JOB``), reopened from its folder."""
    from fastapi.testclient import TestClient

    from xenoform import ui

    work = tmp_path / "work"
    monkeypatch.setattr(ui, "work_dir", lambda: work)
    job = work / "jobs" / JOB
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    yield TestClient(ui.create_app()), job
    with ui._LOCK:
        ui._JOBS.pop(JOB, None)
        ui._CANCEL.pop(JOB, None)


def _wait(until, seconds: float = 20.0) -> bool:
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        if until():
            return True
        time.sleep(0.02)
    return False


def _settle(client, seconds: float = 30.0) -> dict:
    job: dict = {}

    def over() -> bool:
        job.clear()
        job.update(client.get(f"/api/jobs/{JOB}").json())
        return job["status"] != "running"

    _wait(over, seconds)
    return job


def _lands_then_waits(monkeypatch, module, name):
    """``module.name`` runs to its end (the cut is replaced, the record written) and then waits: the moment a late Stop
    arrives in."""
    landed, release, real = threading.Event(), threading.Event(), getattr(module, name)

    def run(*args, **kwargs):
        out = real(*args, **kwargs)
        landed.set()
        release.wait(20)
        return out

    monkeypatch.setattr(module, name, run)
    return landed, release


def test_the_desk_stops_a_stems_recut_while_its_layers_are_laid_and_the_cut_is_as_it_was(desk, slow_ffmpeg):
    client, job = desk
    before = _state(job)
    slow_ffmpeg.take_over()
    assert client.post(f"/api/jobs/{JOB}/recut", json=KNOBS).status_code == 200
    assert _wait(slow_ffmpeg.writing)  # both layers are re-cut and ffmpeg is laying them together
    answer = client.post(f"/api/jobs/{JOB}/cancel").json()
    assert answer["status"] == "running" and answer["detail"].startswith("Stopping")
    j = _settle(client)
    assert j["status"] == "cancelled" and j["detail"] == "Stopped: the re-cut did not land, and the cut is as it was."
    assert j["edit"] == "recut" and j["video_version"] == j["edit_from"] == 0  # no new version
    assert slow_ffmpeg.ended() and _state(job) == before and _left_beside(job) == []


def test_a_stop_that_comes_after_a_stems_recut_landed_is_told_it_was_too_late(desk, monkeypatch):
    client, job = desk
    before = _state(job)
    landed, release = _lands_then_waits(monkeypatch, stems_mode, "recut")
    try:
        assert client.post(f"/api/jobs/{JOB}/recut", json=KNOBS).status_code == 200 and landed.wait(30)
        client.post(f"/api/jobs/{JOB}/cancel")
    finally:
        release.set()
    j = _settle(client)
    assert j["status"] == "done" and j["detail"] == "Re-cut ready. Stop came too late to undo it, so the edit landed."
    assert j["video_version"] == 1 and j["edit_from"] == 0  # the new version the desk reloads
    after = _state(job)
    assert all(after[key] != before[key] for key in before)
    assert json.loads(after["record"])["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4")


def test_the_desk_stops_lay_them_again_and_the_cut_is_as_it_was(desk, slow_ffmpeg):
    """It had no Stop of its own: the desk said "Stopping the edit" and the composite landed without a word."""
    client, job = desk
    before = _state(job)
    slow_ffmpeg.take_over()
    r = client.post(f"/api/jobs/{JOB}/composite", json={"prominence": {"other": 1.0}, "blend": {"drums": "add"}})
    assert r.status_code == 200 and _wait(slow_ffmpeg.writing)
    answer = client.post(f"/api/jobs/{JOB}/cancel").json()
    assert answer["status"] == "running" and answer["detail"].startswith("Stopping")
    j = _settle(client)
    assert j["status"] == "cancelled" and j["error"] is None
    assert j["detail"] == "Stopped: the layers were not laid again, and the cut is as it was."
    assert j["edit"] == "composite" and j["video_version"] == j["edit_from"] == 0
    assert slow_ffmpeg.ended() and _state(job) == before and _left_beside(job) == []
    # and the cut takes the next edit: stopped is not "still rendering", and the stand-in is gone
    slow_ffmpeg._monkeypatch.setattr(SC, "subprocess", subprocess)
    assert client.post(f"/api/jobs/{JOB}/composite", json={"prominence": {"other": 1.0}}).status_code == 200
    j = _settle(client)
    assert j["status"] == "done" and j["detail"] == "Laid together again" and j["video_version"] == 1


def test_lay_them_again_has_a_stop_of_its_own_and_a_late_one_is_told_so(desk, monkeypatch):
    from xenoform import ui

    client, job = desk
    stale = threading.Event()
    stale.set()  # the Stop of an edit long over, still under the cut's id
    with ui._LOCK:
        ui._CANCEL[JOB] = stale
    assert client.post(f"/api/jobs/{JOB}/composite", json={"prominence": {"other": 1.0}}).status_code == 200
    j = _settle(client)
    assert j["status"] == "done" and j["detail"] == "Laid together again" and j["video_version"] == 1
    with ui._LOCK:
        assert ui._CANCEL[JOB] is not stale and not ui._CANCEL[JOB].is_set()
    landed, release = _lands_then_waits(monkeypatch, SC, "rebuild")
    try:
        assert client.post(f"/api/jobs/{JOB}/composite", json={"blend": {"drums": "add"}}).status_code == 200 and landed.wait(30)
        client.post(f"/api/jobs/{JOB}/cancel")
    finally:
        release.set()
    j = _settle(client)
    assert j["status"] == "done" and j["video_version"] == 2
    assert j["detail"] == "Laid together again. Stop came too late to undo it, so the edit landed."
    saved = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    assert saved["composites"] == 2 and saved["composite"]["blends"]["drums"] == "add"
    assert saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4")
