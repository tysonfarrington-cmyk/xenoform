"""Stems: the split, each stem's activity, and the status the desk's Stems step polls.

The split itself lives in ``stem_react`` (Demucs htdemucs on the CPU when installed, else the librosa band split) and its
cache and background thread in ``stems_api`` (``work/ui/stems/<song hash>/stems.json`` and the stem wavs). The Stems mode
(``stems_mode``, docs/STEMS_MODE.md) needs three things on top, all here:

- ``activity_for(stems_json, fps, period)``: per stem, a 0..1 **activity** a frame, the curve a layer's opacity follows
  (``prominence x activity``) and its planner reads: the stem's RMS over a beat-long window, normalised to the stem's own
  loud level (never above a quarter of the loudest stem's, so a silent stem's bleed stays silent), gated, then followed with
  an attack that arrives within a beat and a release over two. Also each stem's **onsets** (times), gated by the activity.
  Cached as ``activity.json`` beside the split; a Length window's stems (``stems_api.slice_stems``) read the whole song's
  and cut it to the window, so the window's edges see the music around them.
- ``status(song)`` and ``start(song)``: the split as the Stems step shows it, with a progress estimate while Demucs runs
  (it prints no progress the desk can read; the estimate is the measured rate, docs/stems.md) and each stem's envelope
  once the activity is ready.
- ``fake_split``: a split engine for tests (synthetic stems from the song's length: drums on a 120 BPM grid with a
  breakdown with no drums in the middle fifth, a bass, an "other" that carries the breakdown, silent vocals), so the
  suite never runs Demucs.

``stem_status`` and ``separate`` are the older install-check hooks (models_setup reads ``stem_status``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

import numpy as np

log = logging.getLogger("xenoform")

ACTIVITY_VERSION = 1
ACTIVITY_FILE = "activity.json"
GATE = 0.12            # a beat-window RMS under this share of the stem's loud level is no activity at all
KNEE = 0.55            # ...and from this share up the stem counts as fully active
REL_FLOOR = 0.25       # a stem's loud level is never taken under this share of the loudest stem's (bleed stays silent)
ABS_FLOOR = 1e-4       # an RMS under this (about -80 dBFS) is silence whatever the song
ATTACK_BEATS = 1.0     # the activity reaches 90 % of a rise within a beat
RELEASE_BEATS = 2.0    # and falls 90 % of the way over two
ONSET_MIN_ACTIVITY = 0.1  # an onset where the stem is not active (bleed, a click in the tail) is not the stem's
ENVELOPE_POINTS = 240  # the envelope the desk draws: at most this many points a stem
SR = 22050
ENGINES = ("auto", "demucs", "bands", "fake")
DEFAULT_ENGINE = "auto"  # tests set "fake": the suite never runs Demucs
# what a split costs on this kind of machine (docs/stems.md: a 4-minute mp3 took 59 s with Demucs at -j 2 on 8 cores),
# for the progress the Stems step shows while Demucs runs, a little slack on top
DEMUCS_S_PER_SONG_S = 0.3
DEMUCS_LOAD_S = 6.0
BANDS_S_PER_SONG_S = 0.06

_ACT_LOCK = threading.Lock()
_ACT_THREADS: dict[str, threading.Thread] = {}  # stems.json path -> the thread building its activity
_ACT_ERRORS: dict[str, str] = {}


# ------------------------------------------------------------------------------------------------ install check


def stem_status() -> dict:
    try:
        import demucs  # noqa: F401

        engine = "demucs"
        detail = "Demucs is installed. Stem splits can use it."
    except Exception:
        engine = "librosa"
        detail = (
            "Demucs is not installed. Beats, bass, mids, and highs still come from librosa. "
            "Ableton is not required."
        )
    return {"engine": engine, "required": False, "detail": detail}


def separate(audio, sr: int) -> dict:
    """Return a band split. Demucs is preferred and never required."""
    status = stem_status()
    if status["engine"] == "demucs":
        try:
            return _demucs(audio, sr)
        except Exception:
            status = {
                "engine": "librosa",
                "required": False,
                "detail": "Demucs did not run. The desk used the librosa band split.",
            }
    return {"engine": "librosa", "detail": status["detail"], "bands": ("sub", "bass", "mid", "high")}


def _demucs(audio, sr: int) -> dict:
    """A thin hook. The analysis path already has librosa bands if this raises."""
    from demucs.pretrained import get_model

    get_model("htdemucs")
    return {"engine": "demucs", "detail": "Demucs htdemucs is available.", "sr": int(sr), "samples": len(audio)}


# ------------------------------------------------------------------------------------------------ the split


def engine_of(value) -> str:
    """A split engine name: auto, demucs, bands (``librosa`` is its alias) or fake; anything else is ``DEFAULT_ENGINE``."""
    text = str(value or "").strip().lower()
    if text == "librosa":
        text = "bands"
    if text in ("", "auto"):
        text = DEFAULT_ENGINE
    return text if text in ENGINES else "auto"


def song_seconds(song: str | Path) -> float:
    """The song's length from its header (soundfile), else a decode; 0 when it will not read."""
    try:
        import soundfile as sf

        return float(sf.info(str(song)).duration)
    except Exception:
        try:
            import librosa

            return float(librosa.get_duration(path=str(song)))
        except Exception:
            return 0.0


def fake_split(song: str | Path, out_dir: str | Path, *, sr: int = SR) -> dict[str, str]:
    """The test engine: four synthetic stems as long as ``song`` (only its length is read), deterministic, in a moment.

    - drums: a short noise burst on every beat of a 120 BPM grid, none in the breakdown (the middle fifth of the song);
    - bass: a 55 Hz tone everywhere but the last tenth;
    - other: two tones from 30 % to 70 % of the song (it carries the breakdown);
    - vocals: silence (as the band split's vocals are).
    Returns ``{stem: wav path, "engine": "fake"}`` as ``stem_react.split`` does."""
    import soundfile as sf

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    duration = max(1.0, song_seconds(song))
    n = int(round(duration * sr))
    t = np.arange(n, dtype=np.float64) / sr
    rng = np.random.default_rng(7)
    drums = np.zeros(n, dtype=np.float64)
    burst = int(0.08 * sr)
    env = np.exp(-np.arange(burst) / (0.015 * sr))
    lo, hi = 0.4 * duration, 0.6 * duration
    for k in range(int(duration / 0.5) + 1):
        at = k * 0.5
        if lo <= at < hi:
            continue
        a = int(at * sr)
        b = min(n, a + burst)
        if a < n:
            drums[a:b] += 0.6 * env[: b - a] * rng.standard_normal(b - a)
    bass = 0.3 * np.sin(2 * np.pi * 55.0 * t) * (t < 0.9 * duration)
    other = (0.15 * np.sin(2 * np.pi * 440.0 * t) + 0.1 * np.sin(2 * np.pi * 660.0 * t)) * ((t >= 0.3 * duration) & (t < 0.7 * duration))
    vocals = np.zeros(n, dtype=np.float64)
    paths: dict[str, str] = {}
    for name, sig in (("drums", drums), ("bass", bass), ("other", other), ("vocals", vocals)):
        p = out / f"{name}.wav"
        sf.write(str(p), sig.astype(np.float32), sr)
        paths[name] = str(p)
    return {**paths, "engine": "fake"}


def ensure_split(song: str | Path, *, engine: str | None = None, fps: int = 24) -> Path:
    """The song's ``stems.json``, split now (blocking) when it has none: ``stems_api.run_split`` for Demucs and the band
    split, ``fake_split`` for the test engine, in the same folder and the same layout either way."""
    from xenoform import stem_react, stems_api

    song = Path(song)
    out = stems_api.stems_json_path(song)
    if out.is_file():
        return out
    engine = engine_of(engine)
    if engine != "fake":
        return Path(stems_api.run_split(song, engine=engine, fps=fps)["path"])
    t0 = time.perf_counter()
    files = fake_split(song, out.parent)
    env = stem_react.envelopes(files, fps=fps)
    env["song"] = str(song)
    env["files"] = {k: str(v) for k, v in files.items() if k != "engine"}
    env["seconds"] = round(time.perf_counter() - t0, 2)
    tmp = out.with_suffix(".json.part")
    stem_react.save_envelopes(env, tmp)
    os.replace(tmp, out)
    return out


def expected_seconds(song: str | Path, engine: str | None) -> float:
    """About how long the split of ``song`` takes here: the measured Demucs rate (docs/stems.md), else the band split's."""
    secs = song_seconds(song) or 180.0
    text = str(engine or "")
    if text.startswith("demucs"):
        return DEMUCS_LOAD_S + DEMUCS_S_PER_SONG_S * secs
    return 2.0 + BANDS_S_PER_SONG_S * secs


# ------------------------------------------------------------------------------------------------ activity


def _load(path: str | Path, sr: int = SR, offset: float = 0.0, duration: float | None = None) -> np.ndarray:
    import librosa

    y, _ = librosa.load(str(path), sr=sr, mono=True, offset=float(offset), duration=duration)
    return np.asarray(y, dtype=np.float64)


def beat_rms(y: np.ndarray, *, sr: int = SR, fps: int = 24, period: float = 0.5) -> np.ndarray:
    """The RMS a frame of ``y`` over a beat-long window centred on the frame (a stem's hits average out within it)."""
    n = int(len(y) * fps // sr)
    if n <= 0:
        return np.zeros(0)
    cs = np.concatenate([[0.0], np.cumsum(np.asarray(y, dtype=np.float64) ** 2)])
    edges = np.minimum(len(y), np.round(np.arange(n + 1) * sr / fps).astype(np.int64))
    e = (cs[edges[1:]] - cs[edges[:-1]]) / np.maximum(1, np.diff(edges))
    width = max(1, int(round(float(period) * fps)))
    if width > 1:
        pad = width // 2
        padded = np.concatenate([np.full(pad, e[0]), e, np.full(width - 1 - pad, e[-1])])
        e = np.convolve(padded, np.ones(width) / width, mode="valid")
    return np.sqrt(np.maximum(e, 0.0))


def follow(x: np.ndarray, *, fps: int = 24, period: float = 0.5, attack_beats: float = ATTACK_BEATS,
           release_beats: float = RELEASE_BEATS) -> np.ndarray:
    """A peak follower: rises 90 % of the way within ``attack_beats``, falls 90 % of the way over ``release_beats``."""
    x = np.asarray(x, dtype=np.float64)
    if not x.size:
        return x
    up = 1.0 - 0.1 ** (1.0 / max(1.0, attack_beats * period * fps))
    down = 1.0 - 0.1 ** (1.0 / max(1.0, release_beats * period * fps))
    out = np.empty_like(x)
    y = float(x[0])
    for i, v in enumerate(x):
        y += (v - y) * (up if v > y else down)
        out[i] = y
    return out


def gate(x: np.ndarray, ref: float) -> np.ndarray:
    """``x`` (an RMS) as 0..1 activity against the stem's loud level ``ref``: nothing under ``GATE``, all from ``KNEE``."""
    if ref <= ABS_FLOOR:
        return np.zeros_like(np.asarray(x, dtype=np.float64))
    rel = np.asarray(x, dtype=np.float64) / ref
    return np.clip((rel - GATE) / (KNEE - GATE), 0.0, 1.0)


def stem_onsets(y: np.ndarray, act: np.ndarray, *, sr: int = SR, fps: int = 24) -> list[float]:
    """The stem's onsets (seconds), only where the stem is active."""
    if not len(y) or not np.any(np.abs(y) > ABS_FLOOR):
        return []
    import librosa

    hop = 512
    env = librosa.onset.onset_strength(y=np.asarray(y, dtype=np.float32), sr=sr, hop_length=hop)
    times = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=hop, units="time", delta=0.2,
                                       wait=max(1, int(0.1 * sr / hop)))
    out = []
    for t in times:
        k = min(len(act) - 1, max(0, int(round(float(t) * fps)))) if len(act) else 0
        if len(act) and act[k] >= ONSET_MIN_ACTIVITY:
            out.append(round(float(t), 3))
    return out


def activity(files: dict[str, str], *, fps: int = 24, period: float = 0.5, sr: int = SR, offset: float = 0.0,
             duration: float | None = None) -> dict:
    """Each stem's activity curve (0..1 a frame) and its onsets, from the stem wavs ``files`` ({name: path}); ``offset``
    and ``duration`` read a stretch of them. Every curve has the same number of frames."""
    names = [str(k) for k in files if k != "engine"]
    raw: dict[str, np.ndarray] = {}
    audio: dict[str, np.ndarray] = {}
    for name in names:
        try:
            y = _load(files[name], sr, offset, duration)
        except Exception as exc:  # a stem that will not read is silent, not a failed Make
            log.warning("stem %s will not read (%s); it counts as silent", name, exc)
            y = np.zeros(0)
        audio[name] = y
        raw[name] = beat_rms(y, sr=sr, fps=fps, period=period)
    n = max((len(v) for v in raw.values()), default=0)
    for name in names:  # one length for all: a short stem is padded with silence
        if len(raw[name]) < n:
            raw[name] = np.concatenate([raw[name], np.zeros(n - len(raw[name]))])
    level = {name: float(np.percentile(v[v > ABS_FLOOR], 95)) if np.any(v > ABS_FLOOR) else 0.0 for name, v in raw.items()}
    loudest = max(level.values(), default=0.0)
    curves: dict[str, list[float]] = {}
    onsets: dict[str, list[float]] = {}
    refs: dict[str, float] = {}
    for name in names:
        ref = max(level[name], REL_FLOOR * loudest) if level[name] > 0 else 0.0
        refs[name] = round(ref, 6)
        act = follow(gate(raw[name], ref), fps=fps, period=period)
        curves[name] = [round(float(v), 3) for v in act]
        onsets[name] = stem_onsets(audio[name], act, sr=sr, fps=fps)
    return {"version": ACTIVITY_VERSION, "fps": int(fps), "period": round(float(period), 4), "frames": int(n),
            "stems": names, "activity": curves, "onsets": onsets, "refs": refs,
            "gate": GATE, "knee": KNEE, "attack_beats": ATTACK_BEATS, "release_beats": RELEASE_BEATS}


def _fresh(cached: dict, *, fps: int, period: float, stems: list[str], source_mtime: float, cache_mtime: float) -> bool:
    return (isinstance(cached, dict) and cached.get("version") == ACTIVITY_VERSION and int(cached.get("fps") or 0) == int(fps)
            and abs(float(cached.get("period") or 0.0) - float(period)) <= 0.01 and list(cached.get("stems") or []) == list(stems)
            and cache_mtime >= source_mtime)


def _read(path: Path) -> dict | None:
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else None
    except (OSError, ValueError):
        return None


def cached_activity(stems_json: str | Path, *, fps: int = 24, period: float = 0.5) -> dict | None:
    """The activity already worked out for this split at this fps and beat (``activity.json``), or None. Reads only."""
    stems_json = Path(stems_json)
    rec = _read(stems_json)
    if rec is None:
        return None
    src = _source(rec)
    if src is not None:
        full = cached_activity(src[0], fps=fps, period=period)
        return slice_activity(full, src[1], src[2]) if full else None
    path = stems_json.with_name(ACTIVITY_FILE)
    cached = _read(path) if path.is_file() else None
    if cached and _fresh(cached, fps=fps, period=period, stems=_names(rec), source_mtime=stems_json.stat().st_mtime,
                         cache_mtime=path.stat().st_mtime):
        return cached
    return None


def _names(rec: dict) -> list[str]:
    files = rec.get("files") if isinstance(rec.get("files"), dict) else {}
    return [str(n) for n in (rec.get("stems") or list(files)) if str(n) in files]


def _source(rec: dict) -> tuple[Path, float, float] | None:
    """A Length window's stems (``stems_api.slice_stems``): the whole song's stems.json, the start and the length."""
    from xenoform import stems_api

    cut = rec.get("sliced_from") if isinstance(rec.get("sliced_from"), dict) else None
    if not cut or not cut.get("song"):
        return None
    song = Path(str(cut["song"]))
    try:
        src = stems_api.stems_json_path(song) if song.is_file() else None
    except OSError:
        src = None
    if src is None or not src.is_file():
        return None
    return src, float(cut.get("start") or 0.0), float(cut.get("length") or 0.0)


def slice_activity(full: dict, start: float, length: float) -> dict:
    """``full`` (a whole song's activity) cut to ``[start, start + length]``, its onsets in window time."""
    fps = int(full.get("fps") or 24)
    a = max(0, int(round(float(start) * fps)))
    n = int(round(float(length) * fps))
    out = {k: v for k, v in full.items() if k not in ("activity", "onsets")}
    out["activity"] = {}
    for name, curve in (full.get("activity") or {}).items():
        part = list(curve[a:a + n])
        out["activity"][name] = part + [0.0] * max(0, n - len(part))
    out["onsets"] = {name: [round(float(t) - float(start), 3) for t in times if float(start) <= float(t) < float(start) + float(length)]
                     for name, times in (full.get("onsets") or {}).items()}
    out["frames"] = n
    out["sliced_from"] = {"start": round(float(start), 3), "length": round(float(length), 3)}
    return out


def activity_for(stems_json: str | Path, *, fps: int = 24, period: float = 0.5, refresh: bool = False) -> dict:
    """The activity of a split (``stems.json``) at ``fps`` and beat ``period``: cached as ``activity.json`` beside it and
    worked out when missing or stale (a new split, own stems, another fps or beat). A Length window's split reads the
    whole song's and cuts it to the window. Raises FileNotFoundError when the split is not there."""
    stems_json = Path(stems_json)
    rec = _read(stems_json)
    if rec is None:
        raise FileNotFoundError(f"No stems at {stems_json}: split the song first.")
    src = _source(rec)
    if src is not None:
        full = activity_for(src[0], fps=fps, period=period, refresh=refresh)
        return slice_activity(full, src[1], src[2])
    files = rec.get("files") if isinstance(rec.get("files"), dict) else {}
    names = _names(rec)
    cut = rec.get("sliced_from") if isinstance(rec.get("sliced_from"), dict) else None
    path = stems_json.with_name(ACTIVITY_FILE)
    if not refresh:
        hit = cached_activity(stems_json, fps=fps, period=period)
        if hit is not None:
            return hit
    t0 = time.perf_counter()
    if cut:  # a window whose song's own stems are gone: its stretch of the stem files, read where they are
        got = activity({n: files[n] for n in names}, fps=fps, period=period, offset=float(cut.get("start") or 0.0),
                       duration=float(cut.get("length") or 0.0) or None)
    else:
        got = activity({n: files[n] for n in names}, fps=fps, period=period)
    got["split_engine"] = rec.get("engine")
    got["source"] = str(stems_json)
    got["seconds"] = round(time.perf_counter() - t0, 2)
    tmp = path.with_suffix(".json.part")
    tmp.write_text(json.dumps(got), encoding="utf-8")
    os.replace(tmp, path)
    log.info("stem activity for %s: %d stems, %d frames in %.1f s", stems_json.parent.name, len(names), got["frames"], got["seconds"])
    return got


def envelope(curve, points: int = ENVELOPE_POINTS) -> list[float]:
    """A curve brought down to at most ``points`` values (the max of each stretch), for the desk to draw."""
    v = np.asarray(curve or [], dtype=np.float64)
    if v.size <= points:
        return [round(float(x), 3) for x in v]
    edges = np.linspace(0, v.size, points + 1).astype(int)
    return [round(float(v[a:b].max()) if b > a else 0.0, 3) for a, b in zip(edges[:-1], edges[1:])]


def summary(act: dict, roles: dict | None = None) -> list[dict]:
    """One row a stem for the desk: its name, role, envelope, the share of the song it is active, its onset count."""
    from xenoform import stem_react

    rows = []
    for name in act.get("stems") or []:
        curve = (act.get("activity") or {}).get(name) or []
        arr = np.asarray(curve, dtype=np.float64)
        rows.append({"name": name, "role": (roles or {}).get(name) or stem_react.role(name),
                     "envelope": envelope(curve), "active": round(float((arr >= 0.25).mean()) if arr.size else 0.0, 3),
                     "onsets": len((act.get("onsets") or {}).get(name) or [])})
    return rows


# ------------------------------------------------------------------------------------------------ status


def _build_activity(stems_json: Path, fps: int, period: float) -> None:
    key = str(stems_json)
    try:
        activity_for(stems_json, fps=fps, period=period)
        _ACT_ERRORS.pop(key, None)
    except Exception as exc:
        log.exception("stem activity for %s", stems_json)
        _ACT_ERRORS[key] = "the stem envelopes did not build; the desk's log has why"
    finally:
        with _ACT_LOCK:
            if _ACT_THREADS.get(key) is threading.current_thread():
                _ACT_THREADS.pop(key, None)


def _start_activity(stems_json: Path, fps: int, period: float) -> None:
    key = str(stems_json)
    with _ACT_LOCK:
        t = _ACT_THREADS.get(key)
        if t is not None and t.is_alive():
            return
        _ACT_THREADS[key] = t = threading.Thread(target=_build_activity, args=(stems_json, fps, period), daemon=True,
                                                 name=f"stem-activity-{stems_json.parent.name}")
    t.start()


def status(song: str | Path, *, fps: int = 24, period: float | None = None, build: bool = True) -> dict:
    """The Stems step's line for ``song``: ``status`` none / queued / running / done / error, ``stage`` (split, then
    envelopes), ``progress`` 0..1 and ``eta_s`` while Demucs runs (the measured rate, ``expected_seconds``), and when done
    ``stems``: one row a stem with its envelope (``summary``). With ``build`` the activity is worked out on a thread the
    first time the split is found done (the status says ``running``, stage ``envelopes``, until it is)."""
    from xenoform import stems_api

    period = float(period or 0.5)
    st = stems_api.split_status(song)
    out = {"status": st.get("status"), "id": st.get("id"), "engine": st.get("engine"), "seconds": st.get("seconds"),
           "error": st.get("error"), "song": Path(str(song)).name, "own": bool(st.get("own")), "stage": "split"}
    if st.get("status") in ("queued", "running"):
        expected = expected_seconds(song, st.get("engine"))
        done = float(st.get("seconds") or 0.0) if st.get("status") == "running" else 0.0
        out["progress"] = round(min(0.95, done / max(1.0, expected)), 3)
        out["eta_s"] = int(max(0.0, expected - done))
        return out
    if st.get("status") != "done" or not st.get("path"):
        out["progress"] = 0.0
        return out
    stems_json = Path(str(st["path"]))
    act = cached_activity(stems_json, fps=fps, period=period)
    if act is None:
        err = _ACT_ERRORS.get(str(stems_json))
        if err:
            return {**out, "status": "error", "error": err, "progress": 1.0}
        if build:
            _start_activity(stems_json, fps, period)
        return {**out, "status": "running", "stage": "envelopes", "progress": 0.97, "eta_s": 5}
    roles = st.get("roles") if isinstance(st.get("roles"), dict) else {}
    return {**out, "status": "done", "stage": "done", "progress": 1.0, "path": str(stems_json), "fps": int(fps),
            "frames": int(act.get("frames") or 0), "stems": summary(act, roles), "names": list(act.get("stems") or [])}


def start(song: str | Path, *, engine: str | None = None, fps: int = 24, period: float | None = None) -> dict:
    """Split ``song`` (or find its split) and start its envelopes; returns ``status``. Demucs and the band split run on
    ``stems_api``'s background thread (one at a time, cached by song hash); the test engine runs here, in a moment."""
    from xenoform import stems_api

    engine = engine_of(engine)
    if engine == "fake":
        ensure_split(song, engine="fake", fps=fps)
    else:
        stems_api.start_background_split(song, engine=engine, fps=fps)
    return status(song, fps=fps, period=period)


def period_of(beats, default: float = 0.5) -> float:
    """The median beat gap of ``beats`` (seconds), else ``default``."""
    b = sorted(float(x) for x in beats or [])
    gaps = sorted(y - x for x, y in zip(b, b[1:]) if y > x)
    if not gaps:
        return float(default)
    g = gaps[len(gaps) // 2]
    return float(g) if 0.2 <= g <= 2.0 else float(default)


def wait(song: str | Path, *, fps: int = 24, period: float | None = None, timeout: float = 1800.0,
         poll: float = 0.5) -> dict:
    """``status`` polled until it is done or error (a Make that found the split still running waits for it)."""
    end = time.monotonic() + float(timeout)
    st = status(song, fps=fps, period=period)
    while st.get("status") in ("queued", "running") and time.monotonic() < end:
        time.sleep(poll)
        st = status(song, fps=fps, period=period)
    return st
