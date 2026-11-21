"""The step that puts an edit in a cut's place: all of it lands, or all of it is put back.

A re-cut is made beside its cut and then swapped in: the cut's file, its record, and for a Stems cut each layer's file
and record and the composite. That swap is several renames and small writes. One of them can fail (a full disk, a file
that will not be replaced), and before this module the cut was then left part old and part new while the desk said
"The cut is as it was" (docs/notes/review-21nov.md).

``Swap`` does it in three parts:

1. Beside the cut, with nothing of it touched: each record's new text is written to ``<name>.new`` and a copy of every
   file about to be replaced is kept as ``<name>.was``. A failure here (the usual place for a full disk) removes what
   was made, and the cut has not been touched.
2. Each new file is put over its place (``turbo.publish_file``, which waits out a browser that is reading the cut). A
   failure here puts back every place already replaced, and the one that failed, from its ``.was`` copy; a place that
   had no file before has it removed.
3. The ``.was`` copies are removed.

A swap that fails raises ``SwapFailed``. ``restored`` says whether every file and record is as it was, and only then
may anyone say so. When putting one back failed too, ``left`` names it, its ``.was`` copy stays on disk, and the
sentence says the cut is part old and part new. Nothing here reports progress or looks at Stop: a swap is too short
to stop, and a Stop that comes during it is told it came too late by the caller.

Not covered: a process that is killed in part 2 leaves the ``.was`` copies beside a cut that may be part new; nothing
puts them back at the next start.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from xenoform.errors import PlainError

log = logging.getLogger("xenoform")

WAS = ".was"  # a file as it was, kept beside it while the swap runs
BEFORE = ".before"  # a file as it was before a whole edit that swaps more than once (a Stems layer's edit); the two
# copies live in one folder, so they must not share a name
NEW = ".new"  # a record's new text, written beside it before the swap


class SwapFailed(PlainError):
    """The swap did not land. ``restored``: every file and record is as it was before it. ``left``: the files that
    could not be put back (their ``.was`` copies are kept). The text is a sentence the desk can show."""

    def __init__(self, sentence: str, *, restored: bool, left: list[Path] | None = None, reason: str = ""):
        super().__init__(sentence)
        self.restored = bool(restored)
        self.left = list(left or [])
        self.reason = str(reason)  # the first failure in a few words (``why``)


def beside(path: Path, suffix: str) -> Path:
    path = Path(path)
    return path.with_name(path.name + suffix)


def _put(src: Path, dest: Path) -> None:
    """``src`` moved over ``dest`` (the one place a swap replaces a file; the tests fail it here)."""
    from xenoform.turbo import publish_file

    publish_file(src, dest)


def discard(path: Path | None, *, tries: int = 8, pause: float = 0.1) -> None:
    """Remove a file made beside the cut. Never raises (Windows can hold a file for a moment)."""
    if path is None:
        return
    for attempt in range(tries):
        try:
            Path(path).unlink(missing_ok=True)
            return
        except OSError:
            if attempt < tries - 1:
                time.sleep(pause)


def why(exc: BaseException) -> str:
    """The reason in a few words, with no path in it: the system's own words for an OSError."""
    if isinstance(exc, SwapFailed) and exc.reason:
        return exc.reason
    text = str(getattr(exc, "strerror", "") or "") if isinstance(exc, OSError) else ""
    text = text or " ".join(str(exc).split()) or type(exc).__name__
    return (text[:157].rstrip() + "..." if len(text) > 160 else text).rstrip(".")


def _name(path: Path, root: Path | None) -> str:
    try:
        return Path(path).relative_to(root).as_posix() if root is not None else Path(path).name
    except ValueError:
        return Path(path).name


def _sentence(head: str, reason: str, left: list[Path], root: Path | None, *, untouched: bool = False,
              suffix: str = WAS) -> str:
    """What a failed swap says: ``head`` (what did not land), the reason, and what became of the cut."""
    if untouched:
        return f"{head} ({reason}). Nothing of the cut was touched."
    if not left:
        return f"{head} ({reason}). Every file and record was put back."
    names = ", ".join(_name(p, root) for p in left)
    return (f"{head} ({reason}), and putting the cut back failed too. The cut is part old and part new: "
            f"{names} could not be restored. What each was is kept beside it with {suffix} after its name. Free some "
            "disk space or close what holds the file, then make the edit again.")


class Kept:
    """Copies of files as they are now, kept beside them (``<name>.was``, or another ``suffix``), to put back if what
    follows fails. A file that does not exist yet is remembered as absent: putting it back removes it."""

    def __init__(self, paths, *, root: Path | None = None, suffix: str = WAS):
        self.root = Path(root) if root is not None else None
        self.suffix = str(suffix)
        self._was: dict[Path, Path | None] = {}
        self._left: set[Path] = set()  # the files that could not be put back: their copies are not removed
        try:
            for path in paths:
                self.add(Path(path))
        except BaseException:
            self.drop()
            raise

    def add(self, path: Path) -> None:
        if path in self._was:
            return
        if path.exists():
            copy = beside(path, self.suffix)
            self._was[path] = copy  # named before it is made: a copy that fails half-written is removed too
            shutil.copy2(path, copy)
        else:
            self._was[path] = None

    def restore(self, only=None) -> list[Path]:
        """Put the files back (all of them, or ``only`` those). Returns the ones that could not be put back; their
        copies stay on disk. The copies of the files put back are gone."""
        left: list[Path] = []
        for path in reversed(list(self._was) if only is None else [Path(p) for p in only]):
            if path not in self._was:
                continue
            copy = self._was[path]
            try:
                if copy is None:
                    path.unlink(missing_ok=True)
                elif copy.exists():
                    _put(copy, path)
                else:
                    raise FileNotFoundError(f"the copy of {path.name} is gone")
            except Exception:
                log.exception("could not put %s back", path)
                left.append(path)
        self._left.update(left)
        return left

    def drop(self) -> None:
        """Remove the copies: what they were kept for has landed, or never began."""
        for path, copy in self._was.items():
            if path not in self._left:
                discard(copy)


class Swap:
    """One edit put in a cut's place. ``what`` names it in the error ("The re-cut"); ``root`` is the cut's folder, so
    a file that could not be restored is named from there. ``file`` and ``text`` only note what is to be done;
    ``commit`` does all of it or none of it."""

    def __init__(self, what: str, *, root: Path | None = None):
        self.what = str(what)
        self.root = Path(root) if root is not None else None
        self._steps: list[dict] = []

    def file(self, new: Path, dest: Path) -> "Swap":
        """``new`` (made beside the cut) is to be moved over ``dest``. A failed swap removes ``new``."""
        self._steps.append({"new": Path(new), "dest": Path(dest), "text": None})
        return self

    def text(self, dest: Path, text: str) -> "Swap":
        """``dest`` (a record) is to hold ``text``."""
        self._steps.append({"new": beside(dest, NEW), "dest": Path(dest), "text": str(text)})
        return self

    def _head(self) -> str:
        return f"{self.what} was made but could not be put in the cut's place"

    def _clear(self) -> None:
        for step in self._steps:
            discard(step["new"])

    def commit(self) -> None:
        kept = Kept([], root=self.root)
        try:  # 1. beside the cut: nothing of it is touched yet
            for step in self._steps:
                if step["text"] is not None:
                    step["new"].parent.mkdir(parents=True, exist_ok=True)
                    step["new"].write_text(step["text"], encoding="utf-8")
                kept.add(step["dest"])
        except BaseException as exc:
            kept.drop()
            self._clear()
            if isinstance(exc, Exception):
                raise SwapFailed(_sentence(self._head(), why(exc), [], self.root, untouched=True), restored=True,
                                 reason=why(exc)) from exc
            raise
        touched: list[Path] = []
        try:  # 2. the swap itself
            for step in self._steps:
                touched.append(step["dest"])  # named before it is replaced: one that fails half-way is put back too
                _put(step["new"], step["dest"])
        except BaseException as exc:
            left = kept.restore(touched)
            kept.drop()  # a file that could not be put back keeps its copy: it is all that is left of what it was
            self._clear()
            if isinstance(exc, Exception) or left:
                raise SwapFailed(_sentence(self._head(), why(exc), left, self.root), restored=not left, left=left,
                                 reason=why(exc)) from exc
            raise
        kept.drop()  # 3. it landed


def write(dest: Path, data: bytes | str) -> None:
    """``dest`` holds ``data``, replaced in one move (written beside it first): a record put back to what it was."""
    dest = Path(dest)
    new = beside(dest, NEW)
    try:
        if isinstance(data, bytes):
            new.write_bytes(data)
        else:
            new.write_text(data, encoding="utf-8")
        _put(new, dest)
    except BaseException:
        discard(new)
        raise


def put_back(what: str, exc: BaseException, kept: Kept) -> None:
    """An edit failed (``exc``) after it may have changed the files ``kept`` holds: put them back. Returns when all of
    them are back, and the caller raises its own error again; raises ``SwapFailed`` naming the ones that are not."""
    left = kept.restore()
    kept.drop()
    if left:
        earlier = list(getattr(exc, "left", []) or [])  # what a swap inside the edit could not put back itself
        suffix = f"{WAS} or {kept.suffix}" if earlier and kept.suffix != WAS else kept.suffix
        left = earlier + [p for p in left if p not in earlier]
        raise SwapFailed(_sentence(f"{what} did not land", why(exc), left, kept.root, suffix=suffix), restored=False,
                         left=left, reason=why(exc)) from exc


def failed_edit(failed: str, exc: BaseException) -> tuple[str, bool]:
    """What a job says of an edit that raised ``exc``: the sentence, and whether the cut is as it was. ``failed`` is
    the edit's own opening ("Re-cut did not run."); a swap that failed says all of it itself."""
    from xenoform.errors import plain_error

    if isinstance(exc, SwapFailed):
        return plain_error(exc), exc.restored
    return f"{failed} {plain_error(exc)}", True
