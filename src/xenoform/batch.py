"""Variations: several Drafts of one idea queued for the night and compared in the morning (from Pause's demo,
"Thirty nights. Thirty uploads.", 27 Oct).

``variations(body, count, vary)`` turns the desk's make body into ``count`` Draft bodies that differ in one thing:

- ``seed``: the same settings with a fresh roll (the still pick, the morphs, the handoff kinds all follow the seed);
- ``vibe``: the line in the other featured vibes, in their featured order after the chosen one;
- ``feel``: the line with another feel clause from ``FEELS`` ("slow and dreamy", "hard and glitchy"), its knobs and
  its Look, as the idea line would set them (``idea.feel_of``).

The first is always the body as it came, the Draft the desk would have made. Paid cloud is off in every one.

``Runner`` keeps the queue: one item at a time, and only while the GPU is free (no cut rendering on this desk and
ComfyUI's queue empty), so a batch never runs two GPU jobs at once and never cuts in on another desk's render. A batch is
one JSON file under ``work/ui/batches``; an item a desk restart interrupted is ``stopped`` until resumed. "Render this
one at Final" queues that variation's own body at Final with its chain pinned, after the Drafts still waiting.

``measured(jobs)`` reads the ``took.json`` beside every cut on this machine: what a second of video takes here at
Draft and at Final, which the desk and the page show instead of a guess.
"""
from __future__ import annotations

import copy
import json
import logging
import statistics
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

log = logging.getLogger("xenoform")

COUNTS = (1, 3, 5, 10)  # 1: one Draft of the settings as they are, queued to run when the GPU is free
VARY = ("seed", "vibe", "feel")
SEED = 2727  # dense.run_simple's seed when the body names none
SEED_STEP = 1009
# Feel clauses far apart on the four knobs and the Look, each made only of idea.FEEL_WORDS
FEELS = ("slow and dreamy", "hard and glitchy", "warm and hazy", "cold and sharp", "fast and chaotic", "calm and minimal",
         "dark and heavy", "bright and bouncy", "trippy and ethereal", "electric and punchy", "moody and punchy")
KNOB_DEFAULTS = {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}  # dense.macros' neutral positions
OPEN = ("queued", "waiting", "running")
CLOSED = ("done", "error", "cancelled", "stopped")
# Several desks share one work folder (Tys runs two, and a session runs its own): each batch belongs to the desk that
# queued or resumed it (``owner``, a token a desk process draws at start), that desk alone runs it and touches its
# ``beat`` while it is open, and an open batch whose beat is older than ``STALE_S`` has no desk alive running it.
STALE_S = 60.0
BEAT_S = 15.0


class Elsewhere(ValueError):
    """The batch is running on another desk: act on it there."""


# ------------------------------------------------------------------ the variations
def _draft(body: dict) -> dict:
    out = copy.deepcopy(body)
    out["quality_tier"] = "draft"
    out.update({"paid_cloud": False, "cloud_quality": False, "cloud_confirm": "", "cut_plan": None})
    return out


def _seeds(body: dict, count: int) -> list[tuple[str, dict]]:
    base = int(body.get("seed") or SEED)
    out = []
    for k in range(count):
        b = _draft(body)
        b["seed"] = base + SEED_STEP * k
        out.append((f"Seed {b['seed']}" + (" (as set)" if k == 0 else ""), b))
    return out


def _vibes(body: dict, count: int) -> list[tuple[str, dict]]:
    from xenoform import vibes

    rows = {r["id"]: r for r in vibes.catalog()}
    featured = [v["id"] for v in vibes.featured()]
    first = str(body.get("vibe") or (featured[0] if featured else ""))
    at = featured.index(first) + 1 if first in featured else 0
    order = [first] + [v for v in featured[at:] + featured[:at] if v != first]
    out = []
    for k, vid in enumerate(order[:count]):
        b = _draft(body)
        row = rows.get(vid) or {}
        b["vibe"] = vid
        if k:  # the pins are the first vibe's stills; another vibe picks from its own pool
            b["chain_pins"] = {}
            b["palette"] = row.get("palette") or b.get("palette")
            b["register"] = row.get("register") or b.get("register")
            if not str(b.get("idea") or "").strip():
                b["brief"] = row.get("line") or b.get("brief")
        out.append((str(row.get("name") or vid) + (" (as set)" if k == 0 else ""), b))
    return out


def _feels(body: dict, count: int) -> list[tuple[str, dict]]:
    from xenoform import idea

    line = str(body.get("idea") or "").strip()
    kept, own_text = idea.split_feel(line)
    own = idea.read(own_text, llm=False).get("feel") if own_text else None
    clauses = [c for c in FEELS if c != own_text.lower()][: count - 1]
    out = [((f"{own_text} (your line)" if own_text else "Your line, no feel words (the vibe decides)"), _draft(body))]
    for clause in clauses:
        b = _draft(body)
        b["idea"] = ", ".join(x for x in (kept, clause) if x)
        feel = idea.read(clause, llm=False).get("feel") or {}
        macros = dict(b.get("macros") or {}) if isinstance(b.get("macros"), dict) else {}
        for knob in ((own or {}).get("macros") or {}):  # the line's own feel moved these: back to neutral first
            macros[knob] = KNOB_DEFAULTS.get(knob, 0.5)
        macros.update(feel.get("macros") or {})
        b["macros"] = macros
        b["dance_fx"] = feel.get("look") or "auto"  # no colour word: the vibe's own look
        out.append((clause, b))
    return out


def variations(body: dict, count: int, vary: str) -> list[dict]:
    """``count`` Draft bodies of one idea, the first as it came, each varying ``vary`` (``VARY``)."""
    if int(count) not in COUNTS:
        raise ValueError(f"Make {', '.join(map(str, COUNTS[:-1]))} or {COUNTS[-1]} variations.")
    if vary not in VARY:
        raise ValueError("Vary the seed, the vibe or the feel.")
    made = {"seed": _seeds, "vibe": _vibes, "feel": _feels}[vary](body, int(count))
    return [{"k": k, "label": label, "vary": vary, "kind": "draft", "body": b} for k, (label, b) in enumerate(made)]


# ------------------------------------------------------------------ the GPU and the clock
def comfy_busy(url: str, timeout: float = 3.0) -> str:
    """A sentence while ComfyUI is rendering or holding queued work (another desk's, say) or not answering; '' when
    its queue is empty."""
    base = str(url or "http://127.0.0.1:8188").rstrip("/")
    try:
        with urlopen(Request(base + "/queue", headers={"Accept": "application/json"}), timeout=timeout) as r:
            queue = json.loads(r.read().decode("utf-8") or "{}")
    except (URLError, TimeoutError, OSError, ValueError):
        return f"ComfyUI is not answering at {base}: waiting for it."
    n = len(queue.get("queue_running") or []) + len(queue.get("queue_pending") or [])
    return f"ComfyUI is busy with {n} job{'s' if n != 1 else ''} from elsewhere: waiting for the GPU." if n else ""


def _cut_seconds(folder: Path) -> tuple[str, float]:
    rec = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
    shots = rec.get("shots") or []
    tier = "fast" if rec.get("fast") else str(rec.get("tier") or "draft")  # a Fast Final is a Draft plus its upscale
    return tier, float(shots[-1].get("end") or 0.0) if shots else 0.0


_MEASURED: dict[tuple[str, float], tuple[float, dict]] = {}
MEASURED_TTL_S = 30.0  # the page asks every few seconds while a batch runs; the cuts on disk change every few minutes


def measured(jobs: Path, seconds: float | None = None) -> dict:
    """What a cut takes on this machine, per tier: the median seconds of render per second of video over every
    finished cut (``took.json`` beside it, the record's length), how many cuts, the latest one, and with ``seconds``
    the time one cut that long takes (``eta_s``): the median of the cuts within half again of its length, since a
    short cut carries the same fixed costs (the stills draft, the grows, the look pass), else the rate times it."""
    key = (str(Path(jobs).resolve()), float(seconds or 0.0))
    hit = _MEASURED.get(key)
    if hit and time.monotonic() - hit[0] < MEASURED_TTL_S:
        return copy.deepcopy(hit[1])
    out = _measure(Path(jobs), seconds)
    _MEASURED[key] = (time.monotonic(), out)
    return copy.deepcopy(out)


def _measure(jobs: Path, seconds: float | None) -> dict:
    rows: dict[str, list[tuple[float, float, float]]] = {"draft": [], "fast": [], "final": []}
    for folder in Path(jobs).glob("*") if Path(jobs).is_dir() else []:
        try:
            took = float(json.loads((folder / "took.json").read_text(encoding="utf-8")).get("took_s") or 0.0)
            tier, cut_s = _cut_seconds(folder)
        except (OSError, ValueError, AttributeError, TypeError):
            continue
        if took > 0 and cut_s > 0 and tier in rows:
            rows[tier].append(((folder / "took.json").stat().st_mtime, took, cut_s))
    out = {}
    for tier, got in rows.items():
        if not got:
            continue
        _, took, length = max(got)
        per_s = statistics.median(t / s for _, t, s in got)
        out[tier] = {"per_s": round(per_s, 1), "cuts": len(got), "latest": {"seconds": round(length, 1), "took_s": round(took, 1)}}
        if seconds:
            near = [t for _, t, s in got if seconds / 1.5 <= s <= seconds * 1.5]
            out[tier]["eta_s"] = round(statistics.median(near) if near else per_s * seconds, 1)
    return out


# ------------------------------------------------------------------ the queue
class Runner:
    """The batches on disk under ``root`` and the one queue they share.

    ``start(body)`` starts a cut and returns its job id (raising when the desk refuses); ``job_of(id)`` is the live
    job dict or None; ``busy()`` is a sentence while the GPU is taken, '' when it is free; ``cancel(id)`` stops a job.
    ``step`` is one pass of the scheduler and the whole of its logic; the thread only calls it on a clock."""

    def __init__(self, root: Path, start: Callable[[dict], str], job_of: Callable[[str], dict | None],
                 busy: Callable[[], str], cancel: Callable[[str], Any] | None = None, *, poll_s: float = 5.0,
                 wait_s: float = 20.0):
        self.root = Path(root)
        self._start, self._job_of, self._busy, self._cancel = start, job_of, busy, cancel
        self.poll_s, self.wait_s = poll_s, wait_s
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._batches: dict[str, dict] | None = None
        self.token = uuid.uuid4().hex[:10]  # this desk process: the batches it owns are the ones it runs

    # -- the records
    def mine(self, b: dict | None) -> bool:
        return bool(b) and b.get("owner") == self.token

    def _alive_elsewhere(self, b: dict) -> bool:
        """Another desk owns ``b`` and has touched it lately while it has work open."""
        return (not self.mine(b) and any(i.get("status") in OPEN for i in b.get("items") or [])
                and time.time() - float(b.get("beat") or 0.0) <= STALE_S)

    def _all(self) -> dict[str, dict]:
        """Every batch in the folder: this desk's from memory (the truth while it runs them), the rest read again from
        disk each time, so a batch another desk queued shows up here too. An open batch whose desk stopped beating has
        no desk running it: its open items are stopped until Resume."""
        if self._batches is None:
            self._batches = {}
        now = time.time()
        for path in sorted(self.root.glob("*.json")) if self.root.is_dir() else []:
            if self.mine(self._batches.get(path.stem)):
                continue
            try:
                b = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            stale = [i for i in b.get("items") or [] if i.get("status") in OPEN] if now - float(b.get("beat") or 0.0) > STALE_S else []
            for item in stale:  # the desk that was running it is gone (restarted or closed): its job died with it
                item.update({"status": "stopped", "detail": "The desk restarted before this one finished: Resume runs it again."})
            self._batches[str(b.get("id"))] = b
            if stale:
                self.save(b)
        return self._batches

    def _claim(self, b: dict) -> None:
        """This desk takes ``b`` over (it queued, resumed or extended it): it runs it from now on."""
        if self._alive_elsewhere(b):
            raise Elsewhere("These variations are running on another desk: act on them there.")
        b["owner"], b["beat"] = self.token, time.time()

    def save(self, b: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f"{b['id']}.part"
        tmp.write_text(json.dumps(b, indent=1, default=str), encoding="utf-8")
        tmp.replace(self.root / f"{b['id']}.json")

    def batches(self) -> list[dict]:
        with self._lock:
            return sorted(copy.deepcopy(list(self._all().values())), key=lambda b: str(b.get("created") or ""), reverse=True)

    def get(self, bid: str) -> dict | None:
        with self._lock:
            b = self._all().get(bid)
            return copy.deepcopy(b) if b else None

    def add(self, body: dict, count: int, vary: str, **extra: Any) -> dict:
        """Queue ``count`` variations of ``body``; ``extra`` goes on the record (the desk adds the cut's ``seconds``)."""
        items = variations(body, count, vary)
        now = time.time()
        for item in items:
            item.update({"status": "queued", "detail": "", "job_id": "", "queued_at": now})
        b = {"id": uuid.uuid4().hex[:8], "created": datetime.now().astimezone().isoformat(timespec="seconds"),
             "vary": vary, "count": int(count), "song": str(body.get("song") or ""), "idea": str(body.get("idea") or ""),
             "vibe": str(body.get("vibe") or ""), "length_s": float(body.get("length_s") or 0.0), **extra, "items": items,
             "owner": self.token, "beat": now}
        with self._lock:
            self._all()[b["id"]] = b
            self.save(b)
        self.wake()
        return copy.deepcopy(b)

    def add_final(self, bid: str, k: int, pins: dict | None = None) -> dict:
        """Variation ``k`` again at Final, its chain pinned (``pins``: slot -> still file), queued after the Drafts."""
        with self._lock:
            b = self._all().get(bid)
            src = next((i for i in (b or {}).get("items") or [] if i.get("k") == int(k) and i.get("kind") == "draft"), None)
            if b is None or src is None:
                raise KeyError("No such variation.")
            self._claim(b)
            body = copy.deepcopy(src["body"])
            body["quality_tier"] = "final"
            if pins:
                body["chain_pins"] = {str(s): str(f) for s, f in pins.items()}
            item = {"k": len(b["items"]), "label": f"Final of {src['label']}", "vary": b["vary"], "kind": "final",
                    "of": src["k"], "body": body, "status": "queued", "detail": "", "job_id": "", "queued_at": time.time()}
            b["items"].append(item)
            self.save(b)
        self.wake()
        return copy.deepcopy(item)

    def cancel(self, bid: str) -> dict:
        with self._lock:
            b = self._all().get(bid)
            if b is None:
                raise KeyError("No such batch.")
            if self._alive_elsewhere(b):
                raise Elsewhere("These variations are running on another desk: cancel them there.")
            for item in b["items"]:
                if item["status"] in ("queued", "waiting", "stopped"):
                    item.update({"status": "cancelled", "detail": "Cancelled before it ran."})
                elif item["status"] == "running" and self._cancel and item.get("job_id"):
                    self._cancel(item["job_id"])  # step() reads the job's cancelled status on its next pass
            self.save(b)
            return copy.deepcopy(b)

    def resume(self, bid: str) -> dict:
        with self._lock:
            b = self._all().get(bid)
            if b is None:
                raise KeyError("No such batch.")
            self._claim(b)  # Resume makes this desk the one that runs them
            for item in b["items"]:
                if item["status"] == "stopped":
                    item.update({"status": "queued", "detail": "", "job_id": "", "queued_at": time.time()})
            self.save(b)
        self.wake()
        return self.get(bid) or {}

    # -- the scheduler
    def _open(self) -> list[tuple[dict, dict]]:
        """This desk's open items (another desk's batches are its own to run)."""
        out = [(b, i) for b in self._all().values() if self.mine(b) for i in b.get("items") or [] if i.get("status") in OPEN]
        return sorted(out, key=lambda bi: (bi[1].get("status") != "running", bi[1].get("queued_at") or 0, bi[1]["k"]))

    def _heartbeat(self) -> None:
        """Touch this desk's open batches now and then, so the other desks know someone is running them."""
        now = time.time()
        for b in list((self._batches or {}).values()):
            if self.mine(b) and any(i.get("status") in OPEN for i in b.get("items") or []) and now - float(b.get("beat") or 0.0) >= BEAT_S:
                b["beat"] = now
                self.save(b)

    def step(self) -> str:
        """One pass: follow the running item, else start the next queued one if the GPU is free. Returns what
        happened: "running", "finished", "waiting", "started", "refused" or "idle"."""
        with self._lock:
            todo = self._open()
            self._heartbeat()
            if not todo:
                return "idle"
            b, item = todo[0]
            if item["status"] == "running":
                job = self._job_of(item["job_id"]) or {"status": "error", "detail": "The cut's job record is gone."}
                status = str(job.get("status") or "running")
                if status == "done" and not job.get("took_s"):  # the pipeline said done; the desk's QA pass (CPU) is
                    seen = item.setdefault("done_seen", time.time())  # still checking the file: wait for its numbers
                    if time.time() - float(seen) < 300:
                        return "running"
                if status == "running":
                    item.update({"progress": round(float(job.get("overall") or job.get("progress") or 0.0), 3),
                                 "detail": str(job.get("detail") or ""), "eta_s": job.get("eta_s")})
                    return "running"
                item.update({"status": status if status in CLOSED else "error", "finished_at": time.time(),
                             "detail": str(job.get("error") or job.get("detail") or ""), "progress": 1.0 if status == "done" else item.get("progress"),
                             "took_s": round(float(job.get("took_s") or (time.time() - float(item.get("started_at") or time.time()))), 1)})
                self.save(b)
                return "finished"
        busy = self._busy()  # outside the lock: a slow ComfyUI must not hold up the desk's reads
        with self._lock:
            if item["status"] not in ("queued", "waiting"):  # cancelled meanwhile
                return "idle"
            if busy:
                if item.get("detail") != busy or item["status"] != "waiting":
                    item.update({"status": "waiting", "detail": busy})
                    self.save(b)
                return "waiting"
            try:
                job_id = self._start(copy.deepcopy(item["body"]))
            except Exception as exc:  # the desk refused (no song after a restart, a bad body): the next one runs
                detail = getattr(exc, "detail", None) or str(exc)
                item.update({"status": "error", "detail": str(detail), "finished_at": time.time()})
                self.save(b)
                return "refused"
            item.update({"status": "running", "job_id": job_id, "started_at": time.time(), "detail": "Starting", "progress": 0.0})
            self.save(b)
            return "started"

    def wake(self) -> None:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, name="xenoform-batches", daemon=True)
                self._thread.start()
        self._wake.set()

    def _loop(self) -> None:
        while True:
            try:
                what = self.step()
            except Exception:
                log.exception("batch runner")
                what = "waiting"
            if what in ("started", "finished", "refused"):
                continue
            self._wake.wait(self.wait_s if what == "waiting" else self.poll_s if what == "running" else 60.0)
            self._wake.clear()
