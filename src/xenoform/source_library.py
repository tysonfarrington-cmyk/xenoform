"""Morph source library: load an index, filter by licence, pick a partner pair.

The media pack is not in the repo. ``library.json`` is enough. Missing files
and categories this desk has never seen (``gpu_objects``, ``gpu_morphs``) stay
in the index. A missing index is an empty library, not an error.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from pathlib import Path
from typing import Any

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DROP_ENERGY = 0.66
_ITEM_CAP = 8000

# Tags that actually show up on the pack, plus the desk's vibe and mood words.
VIBE_TAGS: dict[str, tuple[str, ...]] = {
    "liquid-gold": ("liquid", "metal", "iridescent", "crystal", "gold", "warm"),
    "paper-summer": ("paper", "bright", "clean", "light"),
    "bloom": ("organic", "flower", "bloom", "plant"),
    "neon-night": ("dark", "noir", "neon", "night"),
    "ocean": ("water", "ocean", "liquid", "wave"),
    "cosmic": ("space", "spiral", "star", "cosmic"),
}
MOOD_TAGS: dict[str, tuple[str, ...]] = {
    "dawn": ("bright", "warm", "clean"),
    "neon": ("neon", "dark", "vivid"),
    "storm": ("storm", "water", "dark"),
    "cold": ("cool", "cold", "noir"),
    "forge": ("fire", "warm", "metal", "crystal"),
    "night": ("dark", "noir", "night"),
    "marble": ("clean", "stone", "still"),
    "void": ("abstract", "dark"),
}
_CALM_MOTION = {"static", "hold", "drift", "breathe", "slow", "still"}
_HOT_MOTION = {"bursting", "morphing", "sdf_morph", "spinning", "rising", "splash", "merging"}
_POSTER_KEYS = ("poster", "thumb", "thumbnail", "matte", "clay", "rgba", "preview")

_CACHE: dict[str, tuple[int, "SourceLibrary"]] = {}
_CACHE_LOCK = threading.Lock()


class SourceLibrary:
    def __init__(self, folder: Path, items: list[dict], note: str, missing_index: bool) -> None:
        self.folder = folder
        self.items = items
        self.by_id = {}
        for item in items:
            self.by_id.setdefault(str(item["id"]), item)
        self.categories = {str(item.get("category") or "") for item in items}
        self.note = note
        self.missing_index = missing_index


def default_library_folder(root: Path | None = None) -> Path:
    """``./library`` beside the repo when ``root`` is the repo, else the cwd."""
    base = root if root is not None else Path.cwd()
    return (base / "library").resolve()


def resolve_library_folder(value: str | Path | None, root: Path | None = None) -> Path:
    text = str(value or "").strip()
    if not text:
        return default_library_folder(root)
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return path.resolve()
    except OSError:
        return path


def safe_child(folder: Path, relative: str) -> Path | None:
    """A file under ``folder``. ``..`` and absolute paths stay outside and are refused."""
    raw = str(relative or "").replace("\\", "/").strip()
    if not raw or "\x00" in raw or raw.startswith("/") or raw.startswith("//"):
        return None
    root = folder.resolve()
    try:
        candidate = (root / raw).resolve()
    except OSError:
        return None
    if candidate != root and root not in candidate.parents:
        return None
    return candidate


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")


def _flag(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return value is True or value == 1


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def item_file_rels(item: dict) -> list[str]:
    ordered: list[str] = []
    files = item.get("files")
    if isinstance(files, dict):
        for key in _POSTER_KEYS:
            rel = files.get(key)
            if isinstance(rel, str) and rel.strip():
                ordered.append(rel.strip())
        for rel in files.values():
            if isinstance(rel, str) and rel.strip() and rel.strip() not in ordered:
                ordered.append(rel.strip())
    elif isinstance(files, list):
        ordered.extend(str(rel).strip() for rel in files if str(rel).strip())
    single = item.get("file")
    if isinstance(single, str) and single.strip() and single.strip() not in ordered:
        ordered.append(single.strip())
    return ordered


def _any_media(folder: Path, item: dict) -> bool:
    for rel in item_file_rels(item):
        path = safe_child(folder, rel)
        if path is not None and path.is_file():
            return True
    return False


def poster_path(library: SourceLibrary, item: dict) -> Path | None:
    for rel in item_file_rels(item):
        path = safe_child(library.folder, rel)
        if path is None or not path.is_file():
            continue
        if path.suffix.lower() in IMAGE_EXTS:
            return path
    return None


def is_pd_us_only(item: dict) -> bool:
    bucket = str(item.get("licence_bucket") or "").upper().replace("-", "_").replace(" ", "_")
    if "PD_US" in bucket:
        return True
    return _flag(item.get("pd_us")) and item.get("pd_eu") is False


def needs_attribution(item: dict) -> bool:
    if _flag(item.get("attribution_required")):
        return True
    bucket = str(item.get("licence_bucket") or "").upper().replace("_", " ").replace("-", " ")
    if "CC BY" in bucket:
        return True
    licence = str(item.get("licence") or "")
    return re.search(r"\bCC\s*BY\b", licence, re.IGNORECASE) is not None


def credit_line(item: dict) -> str | None:
    """A credit built only from fields on the item. Nothing is invented."""
    if not needs_attribution(item):
        return None
    explicit = str(item.get("credit_line") or "").strip()
    if explicit:
        return explicit
    ident = str(item.get("id") or "item")
    bits: list[str] = []
    author = str(item.get("author") or item.get("credit") or "").strip()
    makers = [str(name).strip() for name in _as_list(item.get("makers")) if str(name).strip()]
    if author:
        bits.append(author)
    elif makers:
        bits.append(", ".join(makers))
    film = str(item.get("film_title") or "").strip()
    year = item.get("year")
    if film:
        bits.append(f"{film} ({year})" if year else film)
    licence = str(item.get("licence") or item.get("commons_licence_tag") or "").strip()
    if licence:
        bits.append(licence)
    source = str(item.get("source_page") or item.get("source_title") or "").strip()
    if not source:
        raw_source = str(item.get("source") or "").strip()
        if raw_source.startswith("http"):
            source = raw_source
    if source:
        bits.append(source)
    if not bits:
        return f"{ident}: CC BY attribution required; author not in the index"
    line = f"{ident}: " + "; ".join(bits)
    if not author and not makers:
        line += "; author not in the index"
    return line


def item_allowed(
    item: dict,
    *,
    exclude_faces: bool = True,
    allow_pd_us: bool = False,
    banned: set[str] | None = None,
) -> bool:
    if banned and str(item.get("id") or "") in banned:
        return False
    if exclude_faces and _flag(item.get("face_present")):
        return False
    if not allow_pd_us and is_pd_us_only(item):
        return False
    return True


def tag_bag(item: dict) -> set[str]:
    bag: set[str] = set()
    for tag in _as_list(item.get("tags")):
        token = _norm(tag)
        if token:
            bag.add(token)
    colour = item.get("colour") if isinstance(item.get("colour"), dict) else item.get("color")
    if isinstance(colour, dict):
        for mood in _as_list(colour.get("mood")):
            token = _norm(mood)
            token = token.removeprefix("colour-").removeprefix("color-")
            if token:
                bag.add(token)
    for key in ("silhouette", "motion", "shape_family"):
        token = _norm(item.get(key))
        if token:
            bag.add(token)
    return bag


def wanted_tags(vibe: str, mood: str) -> set[str]:
    wanted: set[str] = set()
    vibe_key = _norm(vibe)
    for tag in VIBE_TAGS.get(vibe_key, ()):
        wanted.add(tag)
    for tag in MOOD_TAGS.get(_norm(mood), ()):
        wanted.add(tag)
    for token in re.split(r"[^a-z0-9]+", f"{vibe} {mood}".lower()):
        if len(token) >= 3:
            wanted.add(token)
    return wanted


def similarity(item: dict, wanted: set[str]) -> float:
    bag = tag_bag(item)
    if not wanted or not bag:
        return 0.0
    inter = len(bag & wanted)
    if not inter:
        return 0.0
    return inter / len(bag | wanted)


def motion_level(item: dict) -> float:
    raw = item.get("motion_level")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return max(0.0, min(1.0, float(raw)))
    motion = _norm(item.get("motion"))
    if motion in _CALM_MOTION:
        return 0.15
    if motion in _HOT_MOTION:
        return 0.85
    return 0.5


def partners_of(item: dict) -> list[tuple[str, float]]:
    raw = item.get("morph_partners")
    if not isinstance(raw, list):
        return []
    pairs: list[tuple[str, float]] = []
    for row in raw:
        if isinstance(row, str) and row.strip():
            pairs.append((row.strip(), 0.0))
            continue
        if not isinstance(row, dict) or not row.get("id"):
            continue
        try:
            iou = float(row.get("iou") or 0.0)
        except (TypeError, ValueError):
            iou = 0.0
        pairs.append((str(row["id"]), iou))
    return pairs


def _energy(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:  # NaN
        return 0.0
    return max(0.0, min(1.0, number))


def wants_chain(beat: str, section: str, energy: float) -> bool:
    label = f"{beat} {section}".lower()
    if "drop" in label or "climax" in label:
        return True
    return _energy(energy) >= DROP_ENERGY


def _rank(item: dict, wanted: set[str], energy: float, hot: bool) -> float:
    sim = similarity(item, wanted)
    motion = motion_level(item)
    if hot:
        motion_fit = motion
    elif energy < 0.35:
        motion_fit = 1.0 - motion
    else:
        motion_fit = 1.0 - abs(motion - energy)
    score = 0.72 * sim + 0.28 * motion_fit
    if item.get("missing"):
        score -= 0.08
    return score


def _id_set(values: Any) -> set[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in values if str(item).strip()}


def load_library(folder: str | Path | None = None, root: Path | None = None) -> SourceLibrary:
    path = resolve_library_folder(folder, root)
    index = path / "library.json"
    try:
        stamp = index.stat().st_mtime_ns if index.is_file() else 0
    except OSError:
        stamp = 0
    key = str(path)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    library = _read_library(path, index)
    with _CACHE_LOCK:
        _CACHE[key] = (stamp, library)
    return library


def clear_library_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def _read_library(path: Path, index: Path) -> SourceLibrary:
    if not index.is_file():
        name = path.name or str(path)
        return SourceLibrary(path, [], f"No library.json in {name}.", True)
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return SourceLibrary(path, [], "library.json could not be read.", True)
    raw_items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(raw_items, list):
        raw_items = []
    items: list[dict] = []
    for raw in raw_items[:_ITEM_CAP]:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        if not item_id:
            continue
        stored = dict(raw)
        stored["id"] = item_id
        stored["category"] = str(raw.get("category") or "unknown")
        stored["missing"] = not _any_media(path, stored)
        items.append(stored)
    note = "" if items else "The index has no items."
    return SourceLibrary(path, items, note, False)


def public_item(item: dict) -> dict[str, Any]:
    colour = item.get("colour") if isinstance(item.get("colour"), dict) else {}
    moods = [str(mood) for mood in _as_list(colour.get("mood"))]
    return {
        "id": item.get("id") or "",
        "category": item.get("category") or "",
        "tags": [str(tag) for tag in _as_list(item.get("tags"))],
        "moods": moods,
        "motion": str(item.get("motion") or ""),
        "silhouette": str(item.get("silhouette") or ""),
        "licence_bucket": str(item.get("licence_bucket") or ""),
        "face_present": _flag(item.get("face_present")),
        "pd_us_only": is_pd_us_only(item),
        "missing": bool(item.get("missing")),
        "credit": credit_line(item) or "",
        "partners": [{"id": pid, "iou": round(iou, 4)} for pid, iou in partners_of(item)[:8]],
    }


def pick_pair(
    library: SourceLibrary,
    *,
    vibe: str = "",
    mood: str = "",
    energy: float = 0.0,
    beat: str = "",
    section: str = "",
    pinned: Any = None,
    banned: Any = None,
    exclude_faces: bool = True,
    allow_pd_us: bool = False,
) -> dict[str, Any]:
    """Source and target for one scene. Drops prefer a precomputed morph chain."""
    ban = _id_set(banned)
    pins = [item_id for item_id in _id_set(pinned)]
    # Preserve pin order from the list the desk sent.
    if isinstance(pinned, (list, tuple)):
        pins = [str(item).strip() for item in pinned if str(item).strip()]
    allowed = [
        item
        for item in library.items
        if item_allowed(item, exclude_faces=exclude_faces, allow_pd_us=allow_pd_us, banned=ban)
    ]
    empty = {
        "source": None,
        "target": None,
        "chain": False,
        "reason": library.note or "Nothing in the library passed the licence filters.",
        "credits": [],
    }
    if not allowed:
        return empty
    wanted = wanted_tags(vibe, mood)
    level = _energy(energy)
    hot = wants_chain(beat, section, level)
    by_id = {item["id"]: item for item in allowed}
    pinned_item = next((by_id[item_id] for item_id in pins if item_id in by_id), None)

    def partner_choice(source: dict) -> tuple[dict, float] | None:
        best: tuple[dict, float] | None = None
        for pid, iou in partners_of(source):
            other = by_id.get(pid)
            if other is None or other["id"] == source["id"]:
                continue
            sim = similarity(other, wanted)
            score = float(iou) * (0.55 + 0.45 * sim)
            if other.get("missing"):
                score -= 0.05
            if best is None or score > best[1]:
                best = (other, score)
        return best

    source: dict | None = None
    target: dict | None = None
    chain = False
    reason = "Tag match."

    if hot:
        best_total = -1e9
        pool = [pinned_item] if pinned_item is not None else allowed
        for item in pool:
            if item is None:
                continue
            choice = partner_choice(item)
            if choice is None:
                continue
            other, pscore = choice
            total = pscore + 0.35 * _rank(item, wanted, level, True)
            if total > best_total:
                best_total = total
                source, target, chain = item, other, True
                reason = "Morph chain on the drop."
        if pinned_item is not None and source is None:
            source = pinned_item
            reason = "Pinned source. No partner passed the filters."

    if source is None:
        ranked = sorted(allowed, key=lambda item: _rank(item, wanted, level, hot), reverse=True)
        source = pinned_item or ranked[0]
        if pinned_item is not None:
            reason = "Pinned source."
        elif level < 0.35 and not hot:
            reason = "Calm match."
        target = next((item for item in ranked if item["id"] != source["id"]), None)
        if hot and target is not None and chain is False and reason == "Tag match.":
            reason = "No precomputed partner passed the filters."
        chain = False

    if target is None and source is not None:
        choice = partner_choice(source)
        if choice is not None:
            target = choice[0]
            chain = hot

    used = [item for item in (source, target) if item is not None]
    credits = []
    seen: set[str] = set()
    for item in used:
        line = credit_line(item)
        if line and item["id"] not in seen:
            seen.add(item["id"])
            credits.append(line)
    return {
        "source": public_item(source) if source else None,
        "target": public_item(target) if target else None,
        "chain": chain,
        "reason": reason,
        "credits": credits,
    }


def _section_at(sections: list, start: Any) -> dict:
    try:
        at = float(start or 0)
    except (TypeError, ValueError):
        at = 0.0
    for section in sections or []:
        if not isinstance(section, dict):
            continue
        try:
            begin = float(section.get("start") or 0)
            end = float(section.get("end") or 0)
        except (TypeError, ValueError):
            continue
        if begin <= at < end:
            return section
    return {}


def _interesting(scene: dict) -> bool:
    beat = str(scene.get("beat") or "").lower()
    if scene.get("signature") or "drop" in beat or "climax" in beat:
        return True
    return False


def plan_for_scenes(
    library: SourceLibrary,
    scenes: list | None,
    sections: list | None = None,
    *,
    vibe: str = "",
    mood: str = "",
    energy: float = 0.0,
    beat: str = "",
    pinned: Any = None,
    banned: Any = None,
    exclude_faces: bool = True,
    allow_pd_us: bool = False,
) -> dict[str, Any]:
    rows = [scene for scene in (scenes or []) if isinstance(scene, dict)]
    if not rows:
        rows = [{"mood": mood, "beat": beat, "start": 0}]
    focus = [scene for scene in rows if _interesting(scene)] or rows[:1]
    kwargs = {
        "vibe": vibe,
        "pinned": pinned,
        "banned": banned,
        "exclude_faces": exclude_faces,
        "allow_pd_us": allow_pd_us,
    }
    pairs = []
    used: list[dict] = []
    for scene in focus[:8]:
        section = _section_at(sections or [], scene.get("start"))
        pair = pick_pair(
            library,
            mood=str(scene.get("mood") or mood or ""),
            energy=section.get("level", energy),
            beat=str(scene.get("beat") or beat or ""),
            section=str(section.get("label") or ""),
            **kwargs,
        )
        pair["scene"] = scene.get("index")
        pairs.append(pair)
        for key in ("source", "target"):
            public = pair.get(key)
            if not public:
                continue
            item = library.by_id.get(public.get("id") or "")
            if item is not None:
                used.append(item)
    return {"pairs": pairs, "credits": _unique_credits(used), "note": library.note}


def _unique_credits(items: list[dict]) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in items:
        line = credit_line(item)
        ident = str(item.get("id") or "")
        if line and ident not in seen:
            seen.add(ident)
            lines.append(line)
    return lines


def render_credits_markdown(items: list[dict]) -> str:
    lines = [
        "# Render credits",
        "",
        "CC BY items used in this cut. Each line is taken from the library index.",
        "",
    ]
    body = _unique_credits(items)
    if body:
        lines.extend(f"- {line}" for line in body)
    else:
        lines.append("No CC BY item was used in this cut.")
    lines.append("")
    return "\n".join(lines)


def write_render_credits(folder: str | Path, items: list[dict]) -> Path:
    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "CREDITS.md"
    path.write_text(render_credits_markdown(items), encoding="utf-8")
    return path


def _exclude_faces(value: Any) -> bool:
    if value is None or value == "":
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def library_filters(body: dict) -> dict[str, Any]:
    return {
        "vibe": str(body.get("vibe") or ""),
        "mood": str(body.get("mood") or ""),
        "energy": body.get("energy") or 0,
        "beat": str(body.get("beat") or ""),
        "section": str(body.get("section") or ""),
        "pinned": body.get("pinned") if body.get("pinned") is not None else body.get("library_pins") or [],
        "banned": body.get("banned") if body.get("banned") is not None else body.get("library_bans") or [],
        "exclude_faces": _exclude_faces(body.get("exclude_faces", True)),
        "allow_pd_us": _flag(body.get("allow_pd_us", False)),
    }


def attach_library_credits(
    job_dir: str | Path,
    body: dict,
    features: dict | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Write ``CREDITS.md`` beside a render and return the lines for the job."""
    library = load_library(str(body.get("library_folder") or ""), root)
    filters = library_filters(body)
    filters["exclude_faces"] = _exclude_faces(body.get("exclude_faces", True))
    plan = plan_for_scenes(
        library,
        list(body.get("scenes") or []),
        list((features or {}).get("sections") or body.get("sections") or []),
        **{key: filters[key] for key in ("vibe", "mood", "energy", "beat", "pinned", "banned", "exclude_faces", "allow_pd_us")},
    )
    used: list[dict] = []
    for pair in plan["pairs"]:
        for key in ("source", "target"):
            public = pair.get(key) or {}
            item = library.by_id.get(public.get("id") or "")
            if item is not None:
                used.append(item)
    path = write_render_credits(job_dir, used)
    return {
        "credits": plan["credits"],
        "credits_file": path.name,
        "pairs": [
            {
                "scene": pair.get("scene"),
                "source": (pair.get("source") or {}).get("id"),
                "target": (pair.get("target") or {}).get("id"),
                "chain": pair.get("chain"),
                "reason": pair.get("reason"),
            }
            for pair in plan["pairs"]
        ],
        "library_note": library.note,
    }


def _ffmpeg_frame(path: Path, frame: bytes, width: int, height: int, *, video: bool = False, fps: int = 12) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
    ]
    if video:
        command += ["-frames:v", str(len(frame) // (width * height * 3)), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28"]
    else:
        command += ["-frames:v", "1"]
    command.append(str(path))
    try:
        subprocess.run(command, input=frame, check=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required to build the sample library.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace")[-400:]
        raise RuntimeError(f"ffmpeg could not write {path.name}. {detail}") from exc


def _canvas(width: int, height: int, paint) -> bytes:
    buf = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            red, green, blue = paint(x, y)
            index = (y * width + x) * 3
            buf[index] = red
            buf[index + 1] = green
            buf[index + 2] = blue
    return bytes(buf)


def write_sample_library(folder: str | Path, *, force: bool = False) -> Path:
    """A few procedural shapes so the desk runs without the 500 MB pack."""
    dest = Path(folder).expanduser()
    if not dest.is_absolute():
        dest = Path.cwd() / dest
    dest.mkdir(parents=True, exist_ok=True)
    index = dest / "library.json"
    if index.is_file() and not force:
        try:
            existing = json.loads(index.read_text(encoding="utf-8"))
            count = len(existing.get("items") or []) if isinstance(existing, dict) else 0
        except (OSError, json.JSONDecodeError):
            count = 0
        if count > 12:
            raise RuntimeError(
                f"{index} already has {count} items. Pass --force to replace it with the sample."
            )
    width = height = 96
    ink = (18, 16, 28)
    gold = (212, 168, 74)
    vermilion = (232, 81, 46)
    paper = (232, 228, 216)

    def disk(cx, cy, radius, fill, edge=1.0):
        def paint(x, y):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= radius * edge:
                return fill
            return ink
        return paint

    def drop_paint(x, y):
        nx = (x - 48) / 22
        ny = (y - 58) / 28
        circle = nx * nx + ny * ny <= 1
        tip = abs(x - 48) <= (y - 18) * 0.55 and 16 <= y <= 58
        return gold if circle or tip else ink

    def ring_paint(x, y):
        dx = x - 48
        dy = y - 48
        dist = (dx * dx + dy * dy) ** 0.5
        return vermilion if 18 <= dist <= 30 else ink

    def spiral_paint(x, y):
        dx = x - 48
        dy = y - 48
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 8 or dist > 42:
            return ink
        import math

        arm = (math.atan2(dy, dx) + dist * 0.18) % 1.2
        return paper if arm < 0.28 else ink

    shapes = {
        "shapes/blob.png": disk(48, 48, 28, vermilion),
        "shapes/drop.png": drop_paint,
        "shapes/ring.png": ring_paint,
        "shapes/spiral.png": spiral_paint,
        "loops/pulse.png": disk(48, 48, 20, gold),
    }
    for rel, paint in shapes.items():
        _ffmpeg_frame(dest / rel, _canvas(width, height, paint), width, height)

    frames = []
    for step in range(12):
        radius = 16 + (step if step < 6 else 12 - step) * 2
        frames.append(_canvas(width, height, disk(48, 48, radius, gold)))
    _ffmpeg_frame(dest / "loops/pulse.mp4", b"".join(frames), width, height, video=True, fps=12)

    document = {
        "name": "Xenoform sample library",
        "version": 1,
        "note": "Procedural stand-in. The full pack is not in the repo.",
        "schema": {
            "category": "shapes|silhouettes|loops|footage|film|stills|objects_gr|gpu_objects|gpu_morphs",
        },
        "items": [
            {
                "id": "sample_blob",
                "category": "shapes",
                "files": {"poster": "shapes/blob.png", "rgba": "shapes/blob.png"},
                "silhouette": "round",
                "motion": "merging",
                "tags": ["liquid", "organic"],
                "colour": {"mood": ["warm"]},
                "licence_bucket": "own_work_procedural",
                "licence": "Own work (procedural); free to use",
                "face_present": False,
                "morph_partners": [{"id": "sample_drop", "iou": 0.82}, {"id": "sample_pulse", "iou": 0.74}],
            },
            {
                "id": "sample_drop",
                "category": "silhouettes",
                "files": {"poster": "shapes/drop.png"},
                "silhouette": "drop",
                "motion": "static",
                "tags": ["water", "drop", "liquid"],
                "colour": {"mood": ["warm"]},
                "licence_bucket": "own_work_procedural",
                "licence": "Own work (procedural); free to use",
                "face_present": False,
                "morph_partners": [{"id": "sample_blob", "iou": 0.82}],
            },
            {
                "id": "sample_ring",
                "category": "shapes",
                "files": {"poster": "shapes/ring.png"},
                "silhouette": "ring",
                "motion": "spinning",
                "tags": ["abstract", "ring"],
                "colour": {"mood": ["vivid"]},
                "licence_bucket": "own_work_procedural",
                "licence": "Own work (procedural); free to use",
                "face_present": False,
                "morph_partners": [{"id": "sample_spiral", "iou": 0.7}],
            },
            {
                "id": "sample_spiral",
                "category": "shapes",
                "files": {"poster": "shapes/spiral.png"},
                "silhouette": "spiral",
                "motion": "spinning",
                "tags": ["spiral", "space"],
                "colour": {"mood": ["cool"]},
                "licence_bucket": "own_work_procedural",
                "licence": "Own work (procedural); free to use",
                "face_present": False,
                "morph_partners": [{"id": "sample_ring", "iou": 0.7}],
            },
            {
                "id": "sample_pulse",
                "category": "loops",
                "file": "loops/pulse.mp4",
                "files": {"poster": "loops/pulse.png"},
                "silhouette": "round",
                "motion": "morphing",
                "tags": ["liquid", "morph", "metal"],
                "colour": {"mood": ["warm"]},
                "licence_bucket": "own_work_procedural",
                "licence": "Own work (procedural); free to use",
                "face_present": False,
                "morph_partners": [{"id": "sample_blob", "iou": 0.9}],
            },
        ],
    }
    index.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    clear_library_cache()
    return dest
