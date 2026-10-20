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
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
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


def nasa_media_url(nasa_id: str, prefer: Iterable[str] = ("~large.mp4", "~medium.mp4", "~orig.mp4", "~small.mp4")) -> str:
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
              modes: dict[int, str] | None = None) -> dict:
    """Turn footage (scan_folder output, optionally with 'scenes') into a scene_edit spec.

    Cuts land on the beat grid (every ``bars_per_shot`` bars); boundaries that fall on a
    section change get the vibe's recommended 'drop' transition (scene-morph by default),
    others its 'beat' transition. ``modes[i]`` sets a clip's mode.
    """
    from xenoform import transitions_fx as T

    modes = modes or {}
    shots = []
    for i, it in enumerate(items):
        mode = modes.get(i, it.get("mode", "as-is"))
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        for a, b in it.get("scenes") or [(0.0, None)]:
            shots.append({"src": it["path"], "in": a, "kind": it["kind"], "mode": mode, "fit": "crop"})
    if not shots:
        raise ValueError("no footage")
    step = max(1, bars_per_shot * beats_per_bar)
    grid = [b for b in beats[::step] if 0 < b < duration] or [duration / 2]
    edges = [0.0] + grid + [duration]
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
    return {"segments": segs, "transitions": trs, "vibe": vibe}


ANIMATE_PROMPT = ("Use the provided start image as the first frame and the provided end image as the final frame anchor. "
                  "The scene comes alive with subtle natural motion, gentle parallax and slow camera drift, "
                  "the same scene throughout, crisp, clean, high detail.")


def animate_graph(image_png: str, *, seconds: float = 3.0, seed: int = 77, vertical: bool = True) -> dict:
    """'animate' mode: LTX-2.3 with the still as both first and last frame gives a seamless living loop."""
    from xenoform import transitions_fx as T

    g = T.scene_morph_graph(image_png, image_png, seconds=seconds, seed=seed, vertical=vertical, prefix="xenoform/animate")
    g["4"]["inputs"]["text"] = ANIMATE_PROMPT + (" Vertical 9:16 portrait framing." if vertical else "")
    return g
