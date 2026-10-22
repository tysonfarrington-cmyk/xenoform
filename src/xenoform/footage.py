"""Real footage: the built-in library (manifest + fetch) and the "Your footage" import path.

Xenoform starts from real footage. Bring your own clips and images (or pull library clips by
vibe), and Xenoform finds the scenes, cuts them on the beat and joins them with
``transitions_fx``. Each clip gets a mode:

- ``as-is``: used as shot, beat-cut, with audio-reactive post effects
- ``animate``: a still (or a frame from the clip) is brought to life with LTX-2.3 img2vid
- ``morph-into-next``: the boundary into the next clip becomes a ``scene-morph``

Manifest format (``assets/library/manifest.json``, shared with the vibe anchor stills):
{"version": 1, "items": [{"id", "kind": "video"|"image", "title", "source": "nasa"|"pexels"|"mixkit"|"local",
  "source_url", "licence", "attribution", "redistribute": bool, "vibes": [...], "tags": [...],
  "fetch": {"nasa_id"|"url", "in", "out"}, "file": "assets/library/<vibe>/<id>.mp4"}]}
Only items with ``redistribute: true`` (public domain / CC0) may be committed; the rest are
fetched by ``scripts/fetch_library.py`` into a git-ignored folder.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import logging
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("xenoform.footage")
MANIFEST = ROOT / "assets" / "library" / "manifest.json"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MODES = ("as-is", "animate", "morph-into-next")
SOURCES = ("nasa", "pexels", "mixkit", "local", "wikimedia")
REQUIRED = ("id", "kind", "title", "source", "source_url", "licence", "vibes", "redistribute")


# ------------------------------------------------------------------ library
def load_manifest(path: Path | str = MANIFEST) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = validate(data)
    if problems:
        raise ValueError("; ".join(problems))
    return data


def validate(data: dict) -> list[str]:
    out, seen = [], set()
    for i, it in enumerate(data.get("items", [])):
        tag = it.get("id", f"#{i}")
        for k in REQUIRED:
            if k not in it:
                out.append(f"{tag}: missing {k}")
        if it.get("source") not in SOURCES:
            out.append(f"{tag}: unknown source {it.get('source')!r}")
        if it.get("kind") not in ("video", "image"):
            out.append(f"{tag}: kind must be video or image")
        if it.get("source") in ("pexels", "mixkit") and it.get("redistribute"):
            out.append(f"{tag}: Pexels/Mixkit clips cannot be redistributed; fetch them instead")
        if tag in seen:
            out.append(f"{tag}: duplicate id")
        seen.add(tag)
    return out


def by_vibe(vibe: str, data: dict | None = None, kind: str | None = None) -> list[dict]:
    data = data or load_manifest()
    return [it for it in data["items"] if vibe in it.get("vibes", []) and (kind is None or it["kind"] == kind)]


def local_path(item: dict, root: Path = ROOT) -> Path:
    if item.get("file"):
        return root / item["file"]
    sub = "fetched" if not item.get("redistribute") else (item.get("vibes") or ["misc"])[0]
    ext = ".mp4" if item["kind"] == "video" else ".jpg"
    return root / "assets" / "library" / sub / f"{item['id']}{ext}"


def nasa_media_url(nasa_id: str, prefer: Iterable[str] = ("~orig.mp4", "~large.mp4", "~medium.mp4", "~small.mp4")) -> str:
    q = urllib.parse.quote(nasa_id)
    with urllib.request.urlopen(f"https://images-assets.nasa.gov/video/{q}/collection.json", timeout=30) as r:
        urls = json.load(r)
    for suf in prefer:
        for u in urls:
            if u.endswith(suf):
                return u.replace("http://", "https://").replace(" ", "%20")
    raise LookupError(f"no mp4 for NASA id {nasa_id}")


def fetch_item(item: dict, root: Path = ROOT, *, force: bool = False) -> Path:
    """Download (and trim/mute) one manifest item. Returns the local file."""
    dest = local_path(item, root)
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    f = item.get("fetch", {})
    url = f.get("url") or (nasa_media_url(f["nasa_id"]) if f.get("nasa_id") else None)
    if not url:
        raise ValueError(f"{item['id']}: no fetch url or nasa_id")
    if item["kind"] == "image":
        with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as fh:
            shutil.copyfileobj(r, fh)
        return dest
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if f.get("in") is not None:
        cmd += ["-ss", str(f["in"])]
    cmd += ["-i", url]
    if f.get("out") is not None:
        cmd += ["-t", str(float(f["out"]) - float(f.get("in") or 0))]
    cmd += ["-an", "-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)]
    subprocess.run(cmd, check=True)
    return dest


def missing_seeds(root: Path = ROOT, data: dict | None = None) -> list[dict]:
    """Redistributable video seeds (NASA, public domain) that are not on disk yet.

    The clips are not committed (32 MB of mp4 kept the repo heavy); they are
    re-created from their NASA ids on the first run or by ``scripts/fetch_library.py``.
    """
    data = data or load_manifest()
    return [it for it in data["items"] if it.get("redistribute") and it["kind"] == "video"
            and not local_path(it, root).is_file()]


def fetch_seeds(root: Path = ROOT, *, background: bool = True) -> list[dict]:
    """Fetch every missing seed clip; in the background by default so the desk opens at once.

    Returns the list that was missing when called. ``XENO_OFFLINE=1`` skips the fetch.
    """
    import os
    import threading

    try:
        missing = missing_seeds(root)
    except (OSError, ValueError) as exc:
        log.warning("library manifest unreadable: %s", exc)
        return []
    if not missing or os.environ.get("XENO_OFFLINE", "").strip() in {"1", "true", "yes"}:
        return missing

    def work() -> None:
        for it in missing:
            try:
                fetch_item(it, root)
                log.info("library seed fetched: %s", it["id"])
            except Exception as exc:  # one dead link must not stop the rest
                log.warning("library seed %s not fetched (%s); run scripts/fetch_library.py later", it["id"], exc)

    if background:
        threading.Thread(target=work, name="xeno-seeds", daemon=True).start()
    else:
        work()
    return missing


# ------------------------------------------------------------------ your footage
def scan_folder(folder: Path | str) -> list[dict]:
    """Every clip and image in a folder (not recursive), sorted by name."""
    items = []
    for p in sorted(Path(folder).iterdir()):
        ext = p.suffix.lower()
        if ext in VIDEO_EXT:
            items.append({"path": str(p), "kind": "video"})
        elif ext in IMAGE_EXT:
            items.append({"path": str(p), "kind": "image"})
    return items


def probe_duration(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def detect_scenes(path: str, threshold: float = 0.3, min_len: float = 0.8) -> list[tuple[float, float]]:
    """Shot boundaries via ffmpeg's scene score. Returns [(start, end)] scenes."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf", f"select='gt(scene,{threshold})',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    cuts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    dur = probe_duration(path)
    edges = [0.0] + [c for c in cuts if 0 < c < dur] + [dur]
    scenes = []
    for a, b in zip(edges, edges[1:]):
        if b - a >= min_len:
            scenes.append((round(a, 3), round(b, 3)))
        elif scenes:
            scenes[-1] = (scenes[-1][0], round(b, 3))
    return scenes or [(0.0, dur)]


def plan_edit(items: list[dict], beats: list[float], duration: float, *, vibe: str = "black",
              bars_per_shot: int = 2, beats_per_bar: int = 4, sections: list[float] | None = None,
              modes: dict[int, str] | None = None, allow_repeats: bool = False, hash_fn=None,
              more=None, expert: bool = False) -> dict:
    """Turn footage (scan_folder output, optionally with 'scenes') into a scene_edit spec.

    Cuts land on the beat grid (every ``bars_per_shot`` bars); boundaries that fall on a
    section change get the vibe's recommended 'drop' transition (scene-morph by default),
    others its 'beat' transition. ``modes[i]`` sets a clip's mode.
    """
    from xenoform import transitions_fx as T

    from xenoform import guardrails as G

    modes = modes or {}
    warnings: list[str] = []
    hash_fn = hash_fn or _frame_hash
    tracker = G.SourceTracker()

    def add_item(i, it, shots):
        mode = modes.get(i, it.get("mode", "as-is"))
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if (it.get("quality") or it.get("qa") or {}).get("verdict") == "reject":
            warnings.append(f"{Path(str(it['path'])).name}: below the output resolution, skipped")
            return
        # one use per source within a video: the first scene of each source (allow_repeats keeps them all)
        for a, b in (it.get("scenes") or [(0.0, None)])[: None if allow_repeats else 1]:
            ph = None if allow_repeats else hash_fn(it["path"], a)
            if not allow_repeats and tracker.seen(it["path"], ph):
                warnings.append(f"{Path(str(it['path'])).name}: same source or look as an earlier shot, skipped")
                continue
            tracker.add(it["path"], ph)
            shots.append({"src": it["path"], "in": a, "kind": it["kind"], "mode": mode, "fit": "crop",
                          "character": G.is_character(it),
                          "upscale": (it.get("quality") or it.get("qa") or {}).get("verdict") == "upscale"})

    shots: list[dict] = []
    # guardrail source_quality: high-res sources first, soft (e.g. 720x406 NASA) ones last
    order = sorted(range(len(items)), key=lambda i: quality_rank(items[i]))
    for i in order:
        add_item(i, items[i], shots)
    if not shots:
        raise ValueError("no footage")
    step = max(1, bars_per_shot * beats_per_bar)
    grid = [b for b in beats[::step] if 0 < b < duration] or [duration / 2]
    edges = [0.0] + grid + [duration]
    need = len(edges) - 1
    if not allow_repeats and need > len(shots) and more is not None:
        try:  # pool ran dry: pull more (library clips for this vibe, or anything the caller can generate)
            for j, it in enumerate(more(need - len(shots)) or []):
                add_item(len(items) + j, it, shots)
        except Exception as exc:
            warnings.append(f"could not pull more footage: {exc}")
    # character sparing: not in the opening 15%, at most N appearances
    cs = G.rules().get("character_sparing") or {}
    if not expert and cs:
        chars = [s for s in shots if s.get("character")]
        rest = [s for s in shots if not s.get("character")]
        cap = int(cs.get("max_appearances", 3))
        if len(chars) > cap:
            warnings.append(f"{len(chars) - cap} character shot(s) over the {cap}-appearance cap dropped")
            chars = chars[:cap]
        early = max(1, int(round(need * float(cs.get("not_before_frac", 0.15)) + 0.4999)))
        order = rest[:early] + [x for pair in zip(chars, rest[early:]) for x in pair]
        used = {id(x) for x in order}
        order += [x for x in chars + rest if id(x) not in used]
        shots = order
    if not allow_repeats and need > len(shots):
        warnings.append(f"only {len(shots)} unique source(s) for {need} beat slots: using fewer, longer shots instead of repeating. Add footage for faster cutting.")
        keep = sorted(set(round(i * need / len(shots)) for i in range(1, len(shots))))
        edges = [0.0] + [edges[i] for i in keep] + [duration]
    sections = sections or []
    segs, trs = [], []
    for k in range(len(edges) - 1):
        s = dict(shots[k % len(shots)])
        s["dur"] = round(edges[k + 1] - edges[k], 4)
        segs.append(s)
        if k:
            t = edges[k]
            prev_mode = segs[k - 1]["mode"]
            at_section = any(abs(t - x) < 0.5 for x in sections)
            if prev_mode == "morph-into-next":
                kind = "scene-morph"
            elif at_section:  # one premium spell per section change, each type at most twice
                kind = T.recommend(vibe, "drop")
                used = {}
                for x in trs:
                    used[x["kind"]] = used.get(x["kind"], 0) + 1
                if kind not in T.EXEMPT_FROM_CAP and used.get(kind, 0) >= 2:
                    kind = T.pick_premium(used, T.np.random.default_rng(k))
            else:  # most boundaries: a clean cut on the beat
                kind = "cut"
            trs.append({"kind": kind, "win": round(T.TRANSITIONS[kind]["beats"] * (beats[1] - beats[0] if len(beats) > 1 else 0.5), 3),
                        "intensity": 0.6})
    return {"segments": segs, "transitions": trs, "vibe": vibe, "warnings": warnings}


def quality_rank(item: dict) -> int:
    """0 = sharp at output size, 1 = needs upscale, 2 = soft, 3 = reject (sorts first to last)."""
    q = item.get("quality") or item.get("qa") or {}
    if not q:
        return 1
    if q.get("verdict") == "reject":
        return 3
    if q.get("soft"):
        return 2
    return 0 if q.get("verdict") == "ok" else 1


def _frame_hash(path, t: float = 0.0) -> str | None:
    """Perceptual hash of the frame at ``t`` (None when it cannot be read)."""
    try:
        from xenoform.guardrails import dhash
        from xenoform.post_qa import frames_at

        got = frames_at(path, [float(t or 0.0) + 0.1], short=64)
        return dhash(got[0]) if got else None
    except Exception:
        return None


def qa_item(item: dict, root: Path = ROOT, out_w: int = 1080, out_h: int = 1920) -> dict:
    """Size, sharpness and motion for one library item; NASA clips also need a min size + motion."""
    from xenoform.guardrails import rules
    from xenoform.post_qa import source_quality

    r = rules().get("source_quality") or {}
    path = local_path(item, root)
    q = source_quality(path, out_w, out_h, video=item.get("kind") == "video")
    if item.get("source") == "nasa" and item.get("kind") == "video":
        small = min(q["width"], q["height"]) < int(r.get("nasa_min_short_side", 720))
        still = q.get("motion_score", 1.0) < float(r.get("nasa_min_motion", 0.15))
        q["soft"] = bool(q["soft"] or small or still)
        if still:
            q["note"] = "near-static"
    return q


ANIMATE_PROMPT = ("Use the provided start image as the first frame and the provided end image as the final frame anchor. "
                  "The scene comes alive with subtle natural motion, gentle parallax and slow camera drift, "
                  "the same scene throughout, crisp, clean, high detail.")


def animate_graph(image_png: str, *, seconds: float = 3.0, seed: int = 77, vertical: bool = True) -> dict:
    """'animate' mode: LTX-2.3 with the still as both first and last frame gives a seamless living loop."""
    from xenoform import transitions_fx as T

    g = T.scene_morph_graph(image_png, image_png, seconds=seconds, seed=seed, vertical=vertical, prefix="xenoform/animate")
    g["4"]["inputs"]["text"] = ANIMATE_PROMPT + (" Vertical 9:16 portrait framing." if vertical else "")
    return g
