"""The step that puts an edit in a cut's place lands all of it or puts all of it back (``xenoform.cut_swap``;
docs/notes/review-21nov.md, "The failed swap, fixed").

Before: a re-cut was made beside its cut and then put in place by several renames and small writes. One of them failing
(a full disk, a file that will not be replaced) left the cut part old and part new: a layer's new cut under its old
record, the new composite over layers that were still the old ones, a new file under the old record. The desk then
added "The cut is as it was" to the error.

Here a swap is failed at every file it puts in place, in turn, as a full disk fails it (``_FailAt``); each time every
file and record of the cut must be what it was, byte for byte, with nothing left beside it. Where putting the cut back
fails too, the error must say the cut is part old and part new and name the file, and the desk must not add "as it
was". The cuts are test_stems_mode's and test_swap's fakes; the composite is the real ffmpeg."""
from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from xenoform import cut_swap, dense
from xenoform import stems_composite as SC
from xenoform import stems_mode
from xenoform.cut_swap import Swap, SwapFailed

from test_stems_mode import TWO, _song, _stems_job, _stems_make, fake_render, stems_dir  # noqa: F401  (fixtures)
from test_stems_stop import KNOBS, _left_beside, _state

REAL_PUT = cut_swap._put
FULL = "No space left on device"


class _FailAt:
    """Stands in for ``cut_swap._put``: the ``k``-th file put in place fails as a full disk fails it (``half``: after
    it has overwritten half of the file, as a copy cut short does). Every other one is the real thing, and so is
    putting the files back, except those in ``never_back``, which will not be replaced again either."""

    def __init__(self, monkeypatch, k: int, *, half: bool = False, never_back=()):
        self.k, self.half, self.never_back = k, half, {Path(p) for p in never_back}
        self.puts: list[Path] = []
        self.failed: Path | None = None
        monkeypatch.setattr(cut_swap, "_put", self)

    def __call__(self, src, dest) -> None:
        src, dest = Path(src), Path(dest)
        back = src.name.endswith((cut_swap.WAS, cut_swap.BEFORE))
        if back and dest in self.never_back:
            raise PermissionError(errno.EACCES, "Permission denied", str(dest))
        if not back:
            self.puts.append(dest)
            if len(self.puts) == self.k:
                self.failed = dest
                if self.half:
                    dest.write_bytes(b"half")
                raise OSError(errno.ENOSPC, FULL, str(dest))
        REAL_PUT(src, dest)


def _beside(folder: Path) -> list[str]:
    """What a swap makes beside the files it replaces (``.was`` and ``.before`` copies, ``.new`` records) and what an
    edit makes beside its cut: none of it outlives the edit."""
    made = [p.relative_to(folder).as_posix() for p in Path(folder).rglob("*")
            if p.name.endswith((cut_swap.WAS, cut_swap.BEFORE, cut_swap.NEW))]
    return sorted(made + _left_beside(Path(folder)))


def _every_step_fails_in_turn(monkeypatch, run, state, folder: Path, *, half: bool = False) -> list[Path]:
    """Run ``run()`` with the 1st, 2nd, ... file it puts in place failing, until one run puts them all in place.
    After each failure ``state()`` must be what it was. Returns the files that failed, in order."""
    before = state()
    failed: list[Path] = []
    for k in range(1, 40):
        fail = _FailAt(monkeypatch, k, half=half)
        try:
            run()
        except SwapFailed as exc:
            assert fail.failed is not None and exc.restored and exc.left == [] and exc.reason == FULL
            assert FULL in str(exc) and "part old and part new" not in str(exc)
            assert state() == before, f"a swap that failed at {fail.failed.name} (step {k}) left the cut changed"
            assert _beside(folder) == [], f"a swap that failed at step {k} left files beside the cut"
            failed.append(fail.failed)
            continue
        assert fail.failed is None
        break
    monkeypatch.setattr(cut_swap, "_put", REAL_PUT)
    assert state() != before and _beside(folder) == []  # run to its end, it landed
    return failed


# ------------------------------------------------------------------------------------------------ the swap itself


def _three(tmp_path: Path) -> tuple[Path, dict[str, bytes], Swap]:
    """A cut of two files and a record, and the swap that replaces all three and adds a fourth file."""
    cut = tmp_path / "cut"
    (cut / "simple").mkdir(parents=True)
    was = {"a.mp4": b"old a", "b.mp4": b"old b", "simple/simple.json": b'{"n": 1}'}
    for name, data in was.items():
        (cut / name).write_bytes(data)
    swap = Swap("The re-cut", root=cut)
    for name in ("a", "b", "c"):
        (cut / f"{name}.staged.mp4").write_bytes(f"new {name}".encode())
        swap.file(cut / f"{name}.staged.mp4", cut / f"{name}.mp4")
    swap.text(cut / "simple" / "simple.json", '{"n": 2}')
    return cut, was, swap


def _files(cut: Path) -> dict[str, bytes]:
    return {p.relative_to(cut).as_posix(): p.read_bytes() for p in sorted(cut.rglob("*")) if p.is_file()}


def test_a_swap_lands_every_file_and_record_and_leaves_nothing_beside_them(tmp_path):
    cut, _was, swap = _three(tmp_path)
    swap.commit()
    assert _files(cut) == {"a.mp4": b"new a", "b.mp4": b"new b", "c.mp4": b"new c", "simple/simple.json": b'{"n": 2}'}


@pytest.mark.parametrize("half", [False, True])
@pytest.mark.parametrize("k", [1, 2, 3, 4])
def test_a_swap_that_fails_at_any_file_puts_back_every_one_it_replaced(tmp_path, monkeypatch, k, half):
    """Whichever file fails, and whether it failed before it was touched or half overwritten: the cut is what it was,
    a file that did not exist before (c.mp4) is gone again, and the staged files and the copies are removed."""
    cut, was, swap = _three(tmp_path)
    fail = _FailAt(monkeypatch, k, half=half)
    with pytest.raises(SwapFailed) as raised:
        swap.commit()
    exc = raised.value
    assert _files(cut) == was and fail.failed is not None
    assert exc.restored and exc.left == [] and exc.reason == FULL and isinstance(exc.__cause__, OSError)
    assert str(exc) == f"The re-cut was made but could not be put in the cut's place ({FULL}). Every file and record was put back."


def test_a_swap_that_cannot_keep_a_copy_touches_nothing(tmp_path, monkeypatch):
    """The usual place for a full disk: the copy of what is about to be replaced does not fit. Nothing was replaced."""
    cut, was, swap = _three(tmp_path)
    real = cut_swap.shutil.copy2

    def copy2(src, dst, **kw):
        if Path(src).name == "b.mp4":
            Path(dst).write_bytes(b"ha")  # the copy that did not fit, half-written
            raise OSError(errno.ENOSPC, FULL, str(dst))
        return real(src, dst, **kw)

    monkeypatch.setattr(cut_swap.shutil, "copy2", copy2)
    puts = _FailAt(monkeypatch, 99)
    with pytest.raises(SwapFailed) as raised:
        swap.commit()
    assert puts.puts == [] and _files(cut) == was and raised.value.restored
    assert str(raised.value) == f"The re-cut was made but could not be put in the cut's place ({FULL}). Nothing of the cut was touched."


def test_a_swap_that_cannot_be_put_back_says_the_cut_is_part_new_and_keeps_what_the_file_was(tmp_path, monkeypatch):
    cut, was, swap = _three(tmp_path)
    _FailAt(monkeypatch, 3, never_back=[cut / "a.mp4"])  # a and b are replaced, c fails, and a will not go back
    with pytest.raises(SwapFailed) as raised:
        swap.commit()
    exc = raised.value
    assert not exc.restored and exc.left == [cut / "a.mp4"] and exc.reason == FULL
    assert "putting the cut back failed too" in str(exc) and "part old and part new: a.mp4 could not be restored" in str(exc)
    assert "was put back" not in str(exc) and "as it was" not in str(exc)
    assert _files(cut) == {"a.mp4": b"new a", "a.mp4.was": b"old a", "b.mp4": b"old b", "simple/simple.json": b'{"n": 1}'}


def test_what_a_failed_edit_says_and_whether_the_cut_is_as_it_was():
    plain = cut_swap.failed_edit("Re-cut did not run.", RuntimeError("the knobs did not read"))
    assert plain == ("Re-cut did not run. the knobs did not read", True)
    back = SwapFailed("The re-cut was made but could not be put in the cut's place (x). Every file and record was put back.", restored=True)
    assert cut_swap.failed_edit("Re-cut did not run.", back) == (str(back), True)  # the swap's own sentence, no "did not run"
    part = SwapFailed("It is part old and part new.", restored=False, left=[Path("a.mp4")])
    assert cut_swap.failed_edit("Re-cut did not run.", part) == ("It is part old and part new.", False)


# ------------------------------------------------------------------------------------------------ a plain cut's re-cut


def _layer_state(folder: Path) -> dict:
    return {"cut": (folder / "xenoform.mp4").read_bytes(), "record": (folder / "simple" / "simple.json").read_text(encoding="utf-8")}


def test_a_recut_from_cache_that_fails_at_its_file_or_its_record_leaves_both_as_they_were(tmp_path, fake_render, monkeypatch):
    """``dense.recut_from_cache`` on one cut (a layer's own cut is a plain cut): the file, then the record."""
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    drums = job / "layers" / "drums"
    failed = _every_step_fails_in_turn(
        monkeypatch, lambda: dense.recut_from_cache(drums, {"shot_overrides": {"1": {"play": "hold"}}}),
        lambda: _layer_state(drums), drums)
    assert [p.relative_to(drums).as_posix() for p in failed] == ["xenoform.mp4", "simple/simple.json"]
    saved = json.loads(_layer_state(drums)["record"])
    assert saved["recuts"] == 1 and saved["shot_overrides"] == {"1": {"play": "hold"}}


def test_a_recut_whose_compose_fails_leaves_nothing_beside_the_cut(tmp_path, fake_render, monkeypatch):
    from xenoform import beatfx

    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    drums = job / "layers" / "drums"
    before = _layer_state(drums)

    def compose(clips, shots, audio, out, **kw):
        Path(out).write_bytes(b"half a re-cut")
        raise RuntimeError("the encoder gave up")

    monkeypatch.setattr(beatfx, "compose", compose)
    with pytest.raises(RuntimeError, match="the encoder gave up"):
        dense.recut_from_cache(drums, {"macros": {"chaos": 0.1}})
    assert _layer_state(drums) == before and _beside(drums) == []


# ------------------------------------------------------------------------------------------------ a Stems cut


def test_a_stems_recut_that_fails_at_any_file_of_its_swap_leaves_every_file_and_record_as_it_was(tmp_path, fake_render, monkeypatch):
    """A knob re-cut of two layers puts six things in place: each layer's cut and record, the composite, the cut's
    record. A failure at the third used to leave the drums layer new, the other layer's cut new under its old record,
    and the old composite and record over them."""
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    assert len(_state(job)) == 6
    failed = _every_step_fails_in_turn(monkeypatch, lambda: stems_mode.recut(job, dict(KNOBS)), lambda: _state(job), job)
    assert [p.relative_to(job).as_posix() for p in failed] == [
        "layers/drums/xenoform.mp4", "layers/drums/simple/simple.json", "layers/other/xenoform.mp4",
        "layers/other/simple/simple.json", "xenoform.mp4", "simple/simple.json"]
    saved = json.loads(_state(job)["record"])  # and the run that was not failed landed whole
    assert saved["recuts"] == 1 and [l["recuts"] for l in saved["layers"]] == [1, 1]
    assert saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4")


def test_a_stems_recut_whose_file_is_half_overwritten_when_it_fails_is_put_back_too(tmp_path, fake_render, monkeypatch):
    """A file a browser holds is copied over, not renamed over; a copy cut short leaves half a file in the cut's place."""
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)
    for k in (1, 3, 5):  # each of the three videos
        fail = _FailAt(monkeypatch, k, half=True)
        with pytest.raises(SwapFailed) as raised:
            stems_mode.recut(job, dict(KNOBS))
        assert fail.failed.name == "xenoform.mp4" and raised.value.restored
        assert _state(job) == before and _beside(job) == []


def test_a_stems_recut_that_cannot_be_put_back_names_what_is_left(tmp_path, fake_render, monkeypatch):
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)
    other = job / "layers" / "other" / "xenoform.mp4"
    _FailAt(monkeypatch, 5, never_back=[other])  # both layers landed, the composite fails, one layer will not go back
    with pytest.raises(SwapFailed) as raised:
        stems_mode.recut(job, dict(KNOBS))
    exc = raised.value
    assert not exc.restored and exc.left == [other]
    assert "part old and part new: layers/other/xenoform.mp4 could not be restored" in str(exc)
    after = _state(job)
    assert after["other cut"] != before["other cut"]  # the one file that is new
    assert {k: v for k, v in after.items() if k != "other cut"} == {k: v for k, v in before.items() if k != "other cut"}
    assert cut_swap.beside(other, cut_swap.WAS).read_bytes() == before["other cut"]  # what it was, kept beside it
    assert _beside(job) == ["layers/other/xenoform.mp4.was"]


def test_lay_them_again_that_fails_at_its_file_or_its_record_leaves_both_as_they_were(tmp_path, monkeypatch):
    """The composite was replaced and then the record written: a record that would not be written left the new
    composite under the old record."""
    job, rec = _stems_job(tmp_path, _song(tmp_path, "song.wav", sec=2.0))
    SC.build(job, rec)
    failed = _every_step_fails_in_turn(
        monkeypatch, lambda: SC.rebuild(job, prominence={"other": 1.0, "drums": 0.2}, blend={"drums": "add"}),
        lambda: _state(job), job)
    assert [p.relative_to(job).as_posix() for p in failed] == ["xenoform.mp4", "simple/simple.json"]
    saved = json.loads(_state(job)["record"])
    assert saved["composites"] == 1 and saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4")


def _hold(folder: Path, report=None) -> dict:
    """A layer's edit, as the lane's swap or a re-render ends: the layer's own cut re-cut and put in its place."""
    return dense.recut_from_cache(folder, {"shot_overrides": {"1": {"play": "hold"}}}, report=report)


def test_a_layer_edit_whose_composite_fails_puts_the_layer_back(tmp_path, fake_render, monkeypatch):
    """A swap or re-render on a layer lands in the layer first. When the composite then failed, the layer stayed new
    under a cut and a record that were the old ones."""
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)
    seen = {}

    def compose(job_dir, rec, **kw):
        seen["drums"] = (job / "layers" / "drums" / "xenoform.mp4").read_bytes()
        raise RuntimeError("ffmpeg could not lay the layers together (exit 1): no room")

    monkeypatch.setattr(SC, "compose", compose)
    with pytest.raises(RuntimeError, match="could not lay the layers together"):
        stems_mode.layer_edit(job, "drums", _hold, kind="swap")
    assert seen["drums"] != before["drums cut"]  # the edit had landed in the layer when the composite failed
    assert _state(job) == before and _beside(job) == []


def test_a_layer_edit_that_fails_anywhere_in_its_swaps_leaves_every_file_and_record_as_it_was(tmp_path, fake_render, monkeypatch):
    """Four things are put in place: the layer's cut and record (the layer's own re-cut), then the composite and the
    cut's record."""
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    failed = _every_step_fails_in_turn(
        monkeypatch, lambda: stems_mode.layer_edit(job, "drums", _hold, kind="swap", detail={"slot": 1}),
        lambda: _state(job), job)
    assert [p.relative_to(job).as_posix() for p in failed] == [
        "layers/drums/xenoform.mp4", "layers/drums/simple/simple.json", "xenoform.mp4", "simple/simple.json"]
    saved = json.loads(_state(job)["record"])
    assert saved["edits"][-1]["kind"] == "swap" and saved["edits"][-1]["slot"] == 1 and saved["recuts"] == 1
    assert saved["composite"]["sha256"] == SC.sha256_of(job / "xenoform.mp4")


def test_a_layer_edit_that_is_stopped_or_fails_after_it_changed_the_layer_puts_the_layer_back(tmp_path, fake_render):
    from xenoform.turbo import JobCancelled

    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)

    def landed_then(exc):
        def edit(folder, report=None):
            _hold(folder)
            raise exc

        return edit

    for exc in (RuntimeError("the morph came back empty"), JobCancelled("Stopped")):
        with pytest.raises(type(exc)):
            stems_mode.layer_edit(job, "drums", landed_then(exc), kind="rerender")
        assert _state(job) == before and _beside(job) == []


def test_a_layer_that_cannot_be_put_back_is_named(tmp_path, fake_render, monkeypatch):
    job = tmp_path / "job"
    _stems_make(tmp_path, job, [dict(l) for l in TWO])
    before = _state(job)
    drums = job / "layers" / "drums" / "xenoform.mp4"
    monkeypatch.setattr(SC, "compose", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no room")))
    _FailAt(monkeypatch, 99, never_back=[drums])
    with pytest.raises(SwapFailed) as raised:
        stems_mode.layer_edit(job, "drums", _hold, kind="swap")
    exc = raised.value
    assert not exc.restored and exc.left == [drums] and exc.reason == "no room"
    assert str(exc).startswith("The drums layer's swap did not land (no room), and putting the cut back failed too.")
    assert "layers/drums/xenoform.mp4 could not be restored" in str(exc)
    after = _state(job)
    assert after["drums cut"] != before["drums cut"] and after["drums record"] == before["drums record"]
    assert "kept beside it with .before after its name" in str(exc)
    assert cut_swap.beside(drums, cut_swap.BEFORE).read_bytes() == before["drums cut"]
    assert _beside(job) == ["layers/drums/xenoform.mp4.before"]


# ------------------------------------------------------------------------------------------------ an edit that wrote its record first


def test_a_swap_whose_recut_does_not_land_puts_its_record_back(tmp_path, monkeypatch):
    """A swap, a re-render, a take, a generated run and a dream write the record (the new clips) and then re-cut. When
    the re-cut failed, the record named the new still and its morphs over a video that still played the old ones."""
    from test_swap import _cut, _grown

    seen: dict = {}
    job = _cut(tmp_path, monkeypatch, seen)
    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    before = _layer_state(job)
    for k in (1, 2):  # the re-cut's file, then its record
        _FailAt(monkeypatch, k)
        with pytest.raises(SwapFailed) as raised:
            dense.swap_still(job, 3, new)
        assert raised.value.restored and _layer_state(job) == before and _beside(job) == []
    monkeypatch.setattr(cut_swap, "_put", REAL_PUT)
    rec = dense.swap_still(job, 3, new)  # and the same swap lands when the disk has room
    assert rec["stills"][3] == new and len(rec["swaps"]) == 1 and (job / "xenoform.mp4").read_bytes() == b"new"


def test_an_edit_whose_recut_fails_before_any_swap_puts_its_record_back_too(tmp_path, monkeypatch):
    from xenoform import beatfx
    from test_swap import _cut, _grown

    seen: dict = {}
    job = _cut(tmp_path, monkeypatch, seen)
    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    before = _layer_state(job)

    def compose(clips, shots, audio, out, **kw):
        raise RuntimeError("the encoder gave up")

    monkeypatch.setattr(beatfx, "compose", compose)
    with pytest.raises(RuntimeError, match="the encoder gave up"):
        dense.swap_still(job, 3, new)
    assert _layer_state(job) == before and _beside(job) == []


def test_an_edits_record_that_cannot_be_put_back_says_the_record_is_ahead_of_the_video(tmp_path, monkeypatch):
    from xenoform import beatfx
    from test_swap import _cut, _grown

    seen: dict = {}
    job = _cut(tmp_path, monkeypatch, seen)
    new = _grown("cosmic", "000_wolf_skull.jpg", "wolf skull")
    before = _layer_state(job)
    monkeypatch.setattr(beatfx, "compose", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("the encoder gave up")))
    _FailAt(monkeypatch, 1)  # the record's way back is the one thing put in place here, and it fails
    with pytest.raises(SwapFailed) as raised:
        dense.swap_still(job, 3, new)
    exc = raised.value
    assert not exc.restored and exc.left == [job / "simple" / "simple.json"]
    assert str(exc).startswith("The edit did not land (the encoder gave up), and its record could not be put back")
    assert "The video is as it was, but the record names the edit's new clips" in str(exc)
    after = _layer_state(job)
    assert after["cut"] == before["cut"] and json.loads(after["record"])["stills"][3] == new
