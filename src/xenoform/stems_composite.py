"""Stems mode's compositor: the layers' cuts laid one over another, each as visible as its stem is active.

Each layer of a Stems Make (``stems_mode``) is its own cut, rendered silent of purpose (its own song track is ignored
here). This module lays them together with ffmpeg, deterministically from the record:

- **alpha** a frame per layer: ``prominence x activity(stem)`` (``stems.activity_for``: the stem's smoothed, normalised
  RMS, attack within a beat, release over two), so a layer breathes with its stem. A layer that is the only one active
  is drawn opaque (``SOLO``): its alpha rises toward 1 by how alone it is, ``a + (1 - a) x act x prod(1 - act_other)``,
  so one stem playing alone is never a dim picture over black, and two playing at once share the frame by prominence.
- **order**: bottom to top by prominence (the most prominent on top), ties in the layers' own order, and the lead layer
  (the lead instrument) on top whatever its prominence. The ground is black; the bottom layer is laid over it at its alpha.
- **blend** of each layer above the bottom: ``screen`` (the default: objects on black overlap without mud), ``normal``,
  ``add``, ``lighten`` or ``multiply``, each at the layer's alpha. Screen, add and lighten blend the layer premultiplied
  against black (the screen of an ``a``-premultiplied layer is screen at opacity ``a``: ``b + aL(1 - b)``); multiply
  blends it premultiplied against white (``1 - a(1 - L)``, multiply at opacity ``a``); normal is an overlay at the alpha.
- The alpha reaches ffmpeg as a 1x1 gray8 rawvideo stream at the cut's fps (one byte a frame), scaled to the frame and
  ``alphamerge``d onto the layer. The song is mixed in once, as ``beatfx.compose`` muxes it (AAC 192k, as it is).
- Deterministic: the bitexact flags, the encoder's threads pinned, no metadata; the inputs are the layer files and the
  curves in ``composite/curves.json``, so ``rebuild`` makes the same file byte for byte, and a prominence or blend
  change re-composites in seconds with no GPU.
- Stop (``cancel``, the desk's Stop on an edit): ``compose`` makes the composite beside the cut and looks at Stop
  while ffmpeg runs (ffmpeg is ended, ``JobCancelled`` raised, nothing of the cut touched); ``build`` then replaces
  the cut's file. Nothing looks at Stop, and nothing is reported, once the file is replaced.
- A re-composite of a finished cut (``rebuild``) replaces the file and the record in one step that lands both or puts
  both back (``cut_swap``); the Make's own ``build`` writes a cut that did not exist before, so it has nothing to keep.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("xenoform")

BLENDS = ("screen", "normal", "add", "lighten", "multiply")
BLEND_DEFAULT = "screen"
FF_MODES = {"screen": "screen", "add": "addition", "lighten": "lighten", "multiply": "multiply"}
SOLO = True
GROUND = "black"
X264_THREADS = 8  # pinned so the same record makes the same bytes on any machine with this ffmpeg
CURVES_FILE = "curves.json"
FOLDER = "composite"
POLL_S = 0.2  # how often a composite that is running looks at Stop


def blend_of(value) -> str:
    text = str(value or "").strip().lower()
    return text if text in BLENDS else BLEND_DEFAULT


def prominence_of(value, default: float = 0.7) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return default


def order_of(layers: list[dict]) -> list[str]:
    """The stems bottom to top: the least prominent first (the most prominent on top), ties in the layers' order; the
    lead layer (``lead``: the lead instrument) always on top."""
    ranked = sorted(enumerate(layers), key=lambda kv: (bool(kv[1].get("lead")), prominence_of(kv[1].get("prominence")), kv[0]))
    return [str(layer["stem"]) for _, layer in ranked]


def fit(curve, frames: int) -> np.ndarray:
    """A curve cut or padded (with its last value, else 0) to ``frames`` values in 0..1."""
    v = np.clip(np.asarray(curve or [], dtype=np.float64), 0.0, 1.0)
    if v.size >= frames:
        return v[:frames]
    tail = float(v[-1]) if v.size else 0.0
    return np.concatenate([v, np.full(frames - v.size, tail)])


def alphas(layers: list[dict], activity: dict[str, list], frames: int, *, solo: bool = SOLO) -> dict[str, np.ndarray]:
    """Each layer's alpha a frame: ``prominence x activity``, and with ``solo`` a layer playing alone drawn opaque."""
    acts = {str(layer["stem"]): fit(activity.get(str(layer["stem"])), frames) for layer in layers}
    out: dict[str, np.ndarray] = {}
    for layer in layers:
        stem = str(layer["stem"])
        a = prominence_of(layer.get("prominence")) * acts[stem]
        if solo:
            others = np.ones(frames)
            for other, act in acts.items():
                if other != stem:
                    others = others * (1.0 - act)
            a = a + (1.0 - a) * acts[stem] * others
        out[stem] = np.clip(a, 0.0, 1.0)
    return out


def alpha_bytes(alpha: np.ndarray) -> bytes:
    """One gray8 byte a frame: the 1x1 rawvideo ffmpeg reads."""
    return np.round(np.clip(np.asarray(alpha, dtype=np.float64), 0.0, 1.0) * 255.0).astype(np.uint8).tobytes()


def filtergraph(order: list[str], blends: dict[str, str], size: tuple[int, int], fps: int, frames: int) -> str:
    """The ffmpeg graph: inputs 0..n-1 the layer videos (in ``order``), n..2n-1 their alphas; out ``[out]``."""
    w, h = int(size[0]), int(size[1])
    n = len(order)
    dur = f"{frames / float(fps):.6f}"
    parts: list[str] = []
    for i, stem in enumerate(order):
        parts.append(f"[{i}:v]fps={fps},scale={w}:{h}:flags=bicubic,setsar=1,format=gbrap[v{i}]")
        parts.append(f"[{n + i}:v]scale={w}:{h}:flags=neighbor,format=gray[a{i}]")
        parts.append(f"[v{i}][a{i}]alphamerge[m{i}]")
    parts.append(f"color=c=black:s={w}x{h}:r={fps}:d={dur},format=gbrp[g]")
    parts.append("[g][m0]overlay=format=gbrp:shortest=1[c0]")
    for i in range(1, n):
        mode = blend_of(blends.get(order[i]))
        if mode == "normal":
            parts.append(f"[c{i - 1}][m{i}]overlay=format=gbrp:shortest=1[c{i}]")
            continue
        ground = "white" if mode == "multiply" else "black"
        parts.append(f"color=c={ground}:s={w}x{h}:r={fps}:d={dur},format=gbrp[k{i}]")
        parts.append(f"[k{i}][m{i}]overlay=format=gbrp:shortest=1[p{i}]")
        parts.append(f"[c{i - 1}][p{i}]blend=all_mode={FF_MODES[mode]}:shortest=1[c{i}]")
    parts.append(f"[c{n - 1}]format=yuv420p[out]")
    return ";".join(parts)


def sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stop_if(cancel: Callable[[], bool] | None) -> None:
    """Raise ``JobCancelled`` when ``cancel`` (the desk's Stop) says so."""
    if cancel and cancel():
        from xenoform.turbo import JobCancelled

        raise JobCancelled("Stopped before the layers were laid together.")


def discard(path: Path, *, tries: int = 8, pause: float = 0.1) -> None:
    """Remove a file made beside the cut (a stopped composite's, a re-cut's that will not land). Never raises: on
    Windows a file of an ffmpeg that was just ended can stay held for a moment, so it is tried a few times."""
    for attempt in range(tries):
        try:
            Path(path).unlink(missing_ok=True)
            return
        except OSError:
            if attempt < tries - 1:
                time.sleep(pause)


def _ffmpeg(cmd: list[str], cancel: Callable[[], bool] | None) -> tuple[int, str]:
    """Run ffmpeg to its end: its exit code and what it said. ``cancel`` is asked every ``POLL_S`` while it runs; when
    it says so ffmpeg is ended and ``JobCancelled`` raised. Its words go to a file, not a pipe nobody reads meanwhile."""
    import tempfile

    with tempfile.TemporaryFile() as said:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=said)
        try:
            while True:
                try:
                    proc.wait(timeout=POLL_S)
                    break
                except subprocess.TimeoutExpired:
                    stop_if(cancel)
        finally:
            if proc.poll() is None:  # Stop, or anything else that takes us away: ffmpeg does not run on alone
                proc.kill()
                proc.wait()
        said.seek(0)
        return int(proc.returncode), said.read().decode("utf-8", errors="replace")


def render(videos: dict[str, Path], layer_alphas: dict[str, np.ndarray], order: list[str], blends: dict[str, str],
           audio: Path | None, out: Path, *, fps: int, size: tuple[int, int], work: Path,
           cancel: Callable[[], bool] | None = None) -> dict:
    """Lay the layer ``videos`` together into ``out`` (the song from ``audio`` mixed in once). Raises on ffmpeg's error,
    and ``JobCancelled`` when ``cancel`` says Stop while ffmpeg runs (ffmpeg is ended and ``out`` is not written)."""
    from xenoform.video import ffmpeg_bin

    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    frames = min(len(layer_alphas[s]) for s in order)
    cmd = [ffmpeg_bin(), "-v", "error", "-y", "-nostdin"]
    for stem in order:
        cmd += ["-i", str(videos[stem])]
    for stem in order:
        raw = work / f"alpha_{_safe(stem)}.gray"
        raw.write_bytes(alpha_bytes(layer_alphas[stem][:frames]))
        cmd += ["-f", "rawvideo", "-pix_fmt", "gray", "-video_size", "1x1", "-framerate", str(int(fps)), "-i", str(raw)]
    if audio is not None:
        cmd += ["-i", str(audio)]
    graph = filtergraph(order, blends, size, int(fps), frames)
    (work / "graph.txt").write_text(graph, encoding="utf-8")
    cmd += ["-filter_complex", graph, "-map", "[out]"]
    if audio is not None:
        cmd += ["-map", f"{2 * len(order)}:a", "-c:a", "aac", "-b:a", "192k", "-flags:a", "+bitexact", "-shortest"]
    cmd += ["-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-threads:v", str(X264_THREADS), "-flags:v", "+bitexact", "-fflags", "+bitexact", "-map_metadata", "-1",
            "-movflags", "+faststart"]
    tmp = Path(out).with_name(Path(out).stem + ".composite.mp4")
    cmd.append(str(tmp))
    t0 = time.perf_counter()
    try:
        code, said = _ffmpeg(cmd, cancel)
    except BaseException:  # stopped: the half-written file goes
        discard(tmp)
        raise
    if code:
        discard(tmp)
        tail = " | ".join(said.strip().splitlines()[-3:])
        raise RuntimeError(f"ffmpeg could not lay the layers together (exit {code}): {tail}")
    tmp.replace(out)
    return {"frames": frames, "seconds": round(time.perf_counter() - t0, 2), "size": [int(size[0]), int(size[1])],
            "fps": int(fps), "sha256": sha256_of(out)}


def _safe(stem: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(stem))[:48] or "stem"


def curves_path(job_dir: Path) -> Path:
    return Path(job_dir) / FOLDER / CURVES_FILE


def write_curves(job_dir: Path, activity: dict[str, list], *, fps: int, frames: int, source: dict | None = None) -> Path:
    """``composite/curves.json``: each layer's activity a frame for this cut (the curve source of the composite)."""
    path = curves_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"fps": int(fps), "frames": int(frames), "activity": {k: [round(float(x), 3) for x in fit(v, frames)] for k, v in activity.items()},
            "source": source or {}}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def read_curves(job_dir: Path) -> dict:
    path = curves_path(job_dir)
    if not path.is_file():
        raise FileNotFoundError("This Stems cut has no curves to lay its layers by; make it again.")
    return json.loads(path.read_text(encoding="utf-8"))


def section(layers: list[dict], *, fps: int, size: tuple[int, int], frames: int, audio: str | None, solo: bool = SOLO,
            order: list[str] | None = None) -> dict:
    """The record's ``composite`` block for these layers (order, blends, prominence, the curve source)."""
    return {"order": list(order or order_of(layers)), "blends": {str(l["stem"]): blend_of(l.get("blend")) for l in layers},
            "prominence": {str(l["stem"]): prominence_of(l.get("prominence")) for l in layers}, "solo": bool(solo),
            "ground": GROUND, "curve_source": "activity", "curves": f"{FOLDER}/{CURVES_FILE}", "fps": int(fps),
            "size": [int(size[0]), int(size[1])], "frames": int(frames), "audio": audio}


def staged_path(job_dir: Path) -> Path:
    """Where ``compose`` leaves the composite until it is put in the cut's place."""
    return Path(job_dir) / FOLDER / "composite.mp4"


def compose(job_dir: Path, rec: dict, *, report: Callable[[str, float, str], None] | None = None,
            cancel: Callable[[], bool] | None = None, videos: dict[str, Path] | None = None) -> dict:
    """The composite of a Stems record (``rec``: its ``layers`` and ``composite``) from the layer files and the curves
    alone, made at ``staged_path`` with the cut's own file left as it is; returns the composite block with what it
    made. ``videos`` names another file for a layer's cut ({stem: path}: a re-cut made beside it and not yet put in its
    place). ``cancel`` (Stop) is looked at before, while and after ffmpeg runs, and a ``report`` that raises ends it as
    well: either way the staged file is removed and nothing else has changed."""
    job_dir = Path(job_dir)
    comp = dict(rec.get("composite") or {})
    layers = [dict(l) for l in rec.get("layers") or [] if l.get("video")]
    if not layers:
        raise FileNotFoundError("This Stems cut has no layer files; make it again.")
    for layer in layers:  # the record's prominence and blends are the composite's own
        stem = str(layer["stem"])
        layer["prominence"] = (comp.get("prominence") or {}).get(stem, layer.get("prominence"))
        layer["blend"] = (comp.get("blends") or {}).get(stem, layer.get("blend"))
    other = {str(s): Path(p) for s, p in (videos or {}).items()}
    videos = {str(l["stem"]): other.get(str(l["stem"]), Path(str(l["video"]))) for l in layers}
    gone = [s for s, p in videos.items() if not p.is_file()]
    if gone:
        raise FileNotFoundError(f"The {', '.join(gone)} layer's cut is gone; make it again.")
    curves = read_curves(job_dir)
    fps = int(comp.get("fps") or curves.get("fps") or 24)
    frames = int(comp.get("frames") or curves.get("frames") or 0)
    size = tuple(comp.get("size") or (540, 960))
    order = [s for s in (comp.get("order") or order_of(layers)) if s in videos]
    order += [s for s in order_of(layers) if s not in order]
    lay = alphas(layers, curves.get("activity") or {}, frames, solo=bool(comp.get("solo", SOLO)))
    audio = Path(str(comp["audio"])) if comp.get("audio") else None
    if audio is not None and not audio.is_file():
        raise FileNotFoundError("The song file for this video is gone; load it again and render.")
    stop_if(cancel)
    if report:
        report("assemble", 0.62, f"Laying {len(order)} layers over one another ({', '.join(reversed(order))} on top first)")
    made_file = staged_path(job_dir)
    made = render(videos, lay, order, comp.get("blends") or {}, audio, made_file, fps=fps, size=size, work=job_dir / FOLDER,
                  cancel=cancel)
    comp.update({"order": order, "frames": made["frames"], "seconds": made["seconds"], "sha256": made["sha256"],
                 "alpha_mean": {s: round(float(lay[s].mean()), 3) for s in order}})
    try:  # said before the cut's file is replaced: a desk whose report raises on Stop still stops with the cut whole
        if report:
            report("assemble", 0.95, "The layers are laid together")
        stop_if(cancel)
    except BaseException:
        discard(made_file)
        raise
    return comp


def build(job_dir: Path, rec: dict, out: Path | None = None, *, report: Callable[[str, float, str], None] | None = None,
          cancel: Callable[[], bool] | None = None) -> dict:
    """``compose``, then the composite put in place: writes ``out`` (default ``<job>/xenoform.mp4``) and returns the
    composite block with what it made. Stop (``cancel``) is honoured until the composite is made, and ``out`` is
    replaced last, with no report after it: when this raises ``JobCancelled``, ``out`` is the file it was."""
    from xenoform.turbo import publish_file

    job_dir = Path(job_dir)
    comp = compose(job_dir, rec, report=report, cancel=cancel)
    publish_file(staged_path(job_dir), Path(out) if out else job_dir / "xenoform.mp4")
    return comp


def rebuild(job_dir: Path, *, prominence: dict | None = None, blend: dict | None = None,
            report: Callable[[str, float, str], None] | None = None, cancel: Callable[[], bool] | None = None) -> dict:
    """Re-composite a finished Stems cut with new prominence or blends (no GPU, no re-cut): the record's composite block
    changes, the order follows the new prominence, ``<job>/xenoform.mp4`` is replaced and the record written back.
    Stop (``cancel``) ends it with ``JobCancelled`` while the composite is being made, the file and the record as they
    were; once the file is replaced the record is written whatever Stop says, and the caller tells Stop it was late.
    The file and the record are replaced in one step (``cut_swap.Swap``): if either will not be replaced, both are put
    back and ``cut_swap.SwapFailed`` says whether the cut is as it was."""
    job_dir = Path(job_dir)
    path = job_dir / "simple" / "simple.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    if str(rec.get("mode") or "") != "stems":
        raise ValueError("This cut is not a Stems cut: it has one picture, not layers.")
    comp = dict(rec.get("composite") or {})
    stems_in = [str(l["stem"]) for l in rec.get("layers") or []]
    pro = dict(comp.get("prominence") or {})
    for stem, value in (prominence or {}).items():
        if str(stem) in stems_in:
            pro[str(stem)] = prominence_of(value, pro.get(str(stem), 0.7))
    bl = dict(comp.get("blends") or {})
    for stem, value in (blend or {}).items():
        if str(stem) in stems_in:
            bl[str(stem)] = blend_of(value)
    layers = [{**l, "prominence": pro.get(str(l["stem"]), l.get("prominence")), "blend": bl.get(str(l["stem"]), l.get("blend"))}
              for l in rec.get("layers") or []]
    comp.update({"prominence": pro, "blends": bl, "order": order_of(layers)})
    rec["composite"] = comp
    rec["layers"] = layers
    rec["composite"] = compose(job_dir, rec, report=report, cancel=cancel)
    rec["composites"] = int(rec.get("composites") or 0) + 1
    from xenoform import cut_swap

    # the file and the record land together or neither does (a record that would not be written used to leave the new
    # composite under the old record)
    swap = cut_swap.Swap("The new composite", root=job_dir)
    swap.file(staged_path(job_dir), job_dir / "xenoform.mp4")
    swap.text(path, json.dumps(rec, indent=1, default=str))
    swap.commit()
    return rec
