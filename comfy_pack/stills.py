"""The objects a cut morphs through: the vibes' stills, the chain they make, and the guide images LTX gets.

Where the stills come from. In the whole repository (``custom_nodes/xenoform``), the desk's shipped library
(``src/xenoform/ui_static/objects``, every vibe's pool, ``objects.json`` its manifest). With the pack folder alone, the
dozen Liquid chrome stills it carries (``comfy_pack/objects``, the same manifest rows), which every vibe borrows when its
own are not here, keeping its own look (as the desk lets a vibe with no stills borrow a pool). A folder of your own
images can lead the chain (the desk's "Your images").

The chain is the desk's rule for a shipped pool (``morph_pass.pick_stills`` with no grown stills, no usage history and
no taste file): the pool in its curated order, the object the idea line names opening it, the autotune file's bad
pairs moved apart, your images first, then ``chain_walk``. Pins (a still chosen for a slot on the Morph Timeline) hold
their slots and the rest fill from the pool without them, so no still shows twice.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import looks

PACK = Path(__file__).resolve().parent
BUNDLED = PACK / "objects"
REPO_OBJECTS = PACK.parent / "src" / "xenoform" / "ui_static" / "objects"
BUNDLED_VIBE = "chrome-mercury"
MIN_POOL = 3
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
STOP_WORDS = frozenset("a an the and or of to in on by with for from at into over under as is are its it this that".split())
PALETTE_VIBE = {"gold": "liquid-gold", "violet": "cosmic", "grey-green": "ocean", "bronze": "bloom", "neutral": "paper-summer"}


def roots() -> list[Path]:
    """The libraries on disk, the repository's first (its pools are whole)."""
    return [p for p in (REPO_OBJECTS, BUNDLED) if (p / "objects.json").is_file()]


@lru_cache(maxsize=1)
def catalogue() -> dict[str, list[dict]]:
    """Every vibe's pool from the first library that has it: rows with ``file`` (``vibe/name.jpg``), ``noun``,
    ``kind`` and ``path``; a row whose file is missing is left out."""
    out: dict[str, list[dict]] = {}
    for root in roots():
        try:
            manifest = json.loads((root / "objects.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for vibe, rows in (manifest or {}).items():
            if vibe in out or not isinstance(rows, list):
                continue
            kept = []
            for r in rows:
                f = str((r or {}).get("file") or "")
                path = root / f
                if f and path.is_file():
                    kept.append({"file": f, "noun": str(r.get("noun") or noun_of(f)),
                                 "kind": str(r.get("kind") or "object"), "path": str(path)})
            if kept:
                out[vibe] = kept
    return out


def noun_of(file: str) -> str:
    stem = Path(str(file)).stem
    return re.sub(r"^\d+[_\- ]*", "", stem).replace("_", " ").strip() or stem


def vibe_ids() -> list[str]:
    """The vibes the desk knows (``vibes.ids``): the seven originals, then the registry's, then any library vibe."""
    ids = list(looks.ORIGINAL_NAMES) + [str(v["id"]) for v in looks.extended() if v.get("id")]
    ids += [v for v in catalogue() if v not in ids]
    seen, out = set(), []
    for v in ids:
        if v not in seen and v != "none":
            seen.add(v)
            out.append(v)
    return out


def pool_vibe(vibe: str) -> str:
    """The pool a vibe's stills come from (``morph_pass.vibe_for``): its own, else the registry's ``pool``, else liquid
    gold's (the desk's last resort), else the bundled Liquid chrome (the pack folder alone carries no other)."""
    cat = catalogue()
    if len(cat.get(vibe) or []) >= MIN_POOL:
        return vibe
    borrowed = str(looks.vibe_row(vibe).get("pool") or "")
    if borrowed in cat:
        return borrowed
    for fallback in ("liquid-gold", BUNDLED_VIBE):
        if fallback in cat:
            return fallback
    return next(iter(cat), "")


def pool(vibe: str) -> list[dict]:
    """The object rows a cut of ``vibe`` draws on (scenes and settings left out: the pack morphs objects)."""
    rows = list(catalogue().get(pool_vibe(vibe)) or [])
    objects = [r for r in rows if r.get("kind") == "object"]
    return objects or rows


def find(file: str) -> dict | None:
    """A catalogue row by its file (``vibe/name.jpg``), from any vibe."""
    f = str(file or "").replace("\\", "/").strip()
    for rows in catalogue().values():
        for r in rows:
            if r["file"] == f:
                return r
    return None


def user_rows(folder: str | Path | None, limit: int = 12) -> list[dict]:
    """Your own images (a folder of png, jpg or webp) as rows that lead the chain, in name order (``user_targets``)."""
    if not folder:
        return []
    base = Path(str(folder)).expanduser()
    if not base.is_dir():
        return []
    files = sorted(p for p in base.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.is_file())[:limit]
    return [{"file": p.name, "noun": p.stem.replace("_", " ")[:40] or "image", "kind": "object", "path": str(p.resolve()),
             "user": True} for p in files]


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", str(text or "").lower().replace("_", " ").replace("-", " "))
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


def drop_bad_pairs(rows: list[dict], bad: set) -> list[dict]:
    """``morph_pass._drop_bad_pairs``: reorder so no neighbouring pair is on the autotune blocklist, when a reorder can."""
    if not bad or not rows:
        return rows
    bad = set(bad) | {(b, a) for a, b in bad}
    out, rest = [rows[0]], list(rows[1:])
    while rest:
        nxt = next((o for o in rest if (out[-1]["file"], o["file"]) not in bad), rest[0])
        rest.remove(nxt)
        out.append(nxt)
    return out


def chain_walk(rows: list[dict], count: int) -> list[dict]:
    """``morph_pass.chain_walk``: ``count`` stills whose neighbouring pairs, the closing pair included, repeat as late
    as possible; the first lap is the pool in order."""
    n = len(rows)
    if count <= 0 or n == 0:
        return []
    if count <= n or n < 3:
        return [rows[i % n] for i in range(count)]
    used: set[tuple[int, int]] = set()
    seen = [0] * n
    order = [0]
    seen[0] = 1
    for step in range(count - 1):
        cur = order[-1]
        last = step == count - 2
        cands = [j for j in range(n) if j != cur]
        fresh = [j for j in cands if (min(cur, j), max(cur, j)) not in used]
        if last:
            closing = [j for j in fresh if (0, j) not in used and j != 0]
            fresh = closing or fresh
        choice = min(fresh or cands, key=lambda j: (seen[j], (j - cur) % n))
        used.add((min(cur, choice), max(cur, choice)))
        seen[choice] += 1
        order.append(choice)
    return [rows[i] for i in order]


def pick(vibe: str, count: int, *, idea: str = "", pins: dict[int, str] | None = None,
         user_folder: str | Path | None = None) -> list[dict]:
    """``count`` stills for a chain of ``count - 1`` morphs. Pins (slot to file) hold their slots."""
    count = max(0, int(count))
    held: dict[int, dict] = {}
    for k in sorted((pins or {})):
        row = find(pins[k]) if isinstance(pins[k], str) else None
        if row is not None and 0 <= int(k) < count and row["file"] not in {r["file"] for r in held.values()}:
            held[int(k)] = {**row, "pinned": True}
    held_files = {r["file"] for r in held.values()}
    rows = [r for r in pool(vibe) if r["file"] not in held_files]
    typed = content_words(idea)
    lead = next((i for i, r in enumerate(rows) if set(str(r["noun"]).lower().split()) & typed), None)
    if lead:
        rows = rows[lead:] + rows[:lead]  # a curated shipped chain keeps its pairings: the named object opens it
    rows = drop_bad_pairs(rows, looks.bad_pairs())
    objects = user_rows(user_folder) + rows
    free_slots = [k for k in range(count) if k not in held]
    if free_slots and not objects:
        objects = list(held.values())
    free = chain_walk(objects, len(free_slots))
    return [held[k] if k in held else free.pop(0) for k in range(count)]


def distinct(rows: list[dict]) -> int:
    return len({r["file"] for r in rows})


# ------------------------------------------------------------------------------------------------ the guide images


def load_rgb(path: str | Path) -> np.ndarray:
    """A still as an RGB uint8 array (height, width, 3)."""
    from PIL import Image

    with Image.open(str(path)) as im:
        return np.asarray(im.convert("RGB"), dtype=np.uint8).copy()


def _ground(rgb: np.ndarray) -> tuple[int, int, int]:
    """The still's own ground: the median colour of its border pixels."""
    edge = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]], axis=0)
    return tuple(int(v) for v in np.median(edge, axis=0))


def guide_image(path: str | Path, aspect: str = "16:9") -> np.ndarray:
    """The guide LTX gets for a still: the still as it is for 16:9 (``LTXVAddGuide`` scales it to the latent), and for
    9:16 the whole still re-laid on a 320x576 portrait canvas of its own ground, so a wide object is never cropped
    (the desk's Draft 9:16, ``portrait.portrait_stills``)."""
    rgb = load_rgb(path)
    if aspect != "9:16":
        return rgb
    from PIL import Image

    w, h = looks.PORTRAIT
    canvas = Image.new("RGB", (w, h), _ground(rgb))
    im = Image.fromarray(rgb)
    scale = min(w / im.width, h / im.height)
    fit = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    canvas.paste(fit, ((w - fit.width) // 2, (h - fit.height) // 2))
    return np.asarray(canvas, dtype=np.uint8).copy()


def to_image_tensor(rgb: np.ndarray):
    """ComfyUI's IMAGE: a float32 torch tensor (1, height, width, 3) in 0..1."""
    import torch

    return torch.from_numpy(np.asarray(rgb, dtype=np.float32) / 255.0)[None, ...]
