"""Continuity bible and cast lock.

One hero, one of each key prop, one place, one time of day, one weather.
Each element has a single sentence and one reference still. The sentence is
inserted into every shot prompt where the element appears. The still is the
guide for those shots.

Story logic runs before a render. After a render, a local comparator — colour,
shape, and a small image embedding, no downloaded weights and no network —
flags a prop that changes shape. Review & fix re-renders only those shots.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

CAST_KINDS = ("hero", "prop", "location", "time", "weather")

_PROPS: dict[str, dict[str, Any]] = {
    "phone": {
        "words": ("voicemail", "phone", "handset"),
        "variants": ("flip phone", "smartphone", "mobile phone", "cell phone", "iphone"),
        "sentence": "The phone is one handset, the same shape and size in every shot.",
    },
    "letter": {
        "words": ("letter", "envelope", "note"),
        "variants": ("postcard", "email", "telegram"),
        "sentence": "The letter is one page, the same object in every shot.",
    },
    "key": {
        "words": ("key",),
        "variants": ("keycard", "fob"),
        "sentence": "The key is one key, the same object in every shot.",
    },
    "camera": {
        "words": ("camera",),
        "variants": ("phone camera", "camcorder"),
        "sentence": "The camera is one body, the same object in every shot.",
    },
}

_PLACES = (
    "jupiter",
    "earth",
    "moon",
    "mars",
    "kitchen",
    "street",
    "beach",
    "desert",
    "ocean",
    "station",
    "apartment",
    "bedroom",
    "alley",
    "lighthouse",
    "harbour",
    "harbor",
    "shore",
    "cliff",
    "forest",
    "cabin",
    "dock",
    "pier",
    "island",
)
_TIMES = ("dawn", "morning", "noon", "afternoon", "dusk", "sunset", "night", "midnight")
_WEATHER = ("rain", "storm", "snow", "fog", "wind", "clear", "overcast")
_ATMOSPHERE = re.compile(
    r"\b(haze|glow|atmosphere|vibe|drifts?|fog|bokeh|abstract|wash|ambient|mood)\b",
    re.I,
)
_CAUSE = re.compile(r"\b(because|after|so|then|still|carries|follows|the same)\b", re.I)
_MANY = r"\b(two|three|several|many|another|a second|a different|both)\b(?:\s+\w+){{0,3}}\s+{noun}s?\b"


def cast_lock(name: str = "") -> dict[str, Any]:
    """One hero, one sentence. Cast lock, from the open-weights picture pass."""
    who = _who(name)
    return {
        "id": "hero",
        "kind": "hero",
        "name": who,
        "sentence": f"The hero is {who}, the same silhouette in every shot.",
        "lock": "cast",
    }


def continuity_bible(brief: str, scenes: list[dict] | None = None) -> dict[str, Any]:
    """Canonical elements for this piece. Sentences only. Stills are filled later."""
    return _bible(brief, list(scenes or []))


def stamp_continuity(scenes: list[dict], brief: str = "") -> list[dict]:
    """Write the bible onto the cards. Actions stay as the planner wrote them."""
    board = list(scenes or [])
    bible = _bible(brief, board)
    locks = _locks(bible)
    for index, scene in enumerate(board):
        lines = _lines_for(scene, bible, brief)
        scene["lines"] = lines
        scene["lock_words"] = locks
        scene["element_ids"] = [row["id"] for row in bible["elements"] if row["sentence"] in lines]
        scene["because"] = _because(board[index - 1] if index else None, scene, bible)
        guide = apply_lock(str(scene.get("guide") or ""), locks)
        for line in lines:
            if line not in guide:
                guide = f"{guide} {line}".strip()
        if guide:
            scene["guide"] = guide
    return board


def story_logic(brief: str, scenes: list[dict] | None = None) -> dict[str, Any]:
    """One line of cause and effect per shot, and one sentence a stranger would get."""
    board = list(scenes or [])
    bible = _bible(brief, board)
    what = str(bible.get("what") or "")
    flags: list[dict[str, Any]] = []
    if not _readable(what):
        flags.append({"shot": None, "plain": "The piece has no one-sentence story a stranger would get."})
    from xenoform.storyboard import brief_cast, hero_has_verb

    names = _hero_names(board)
    cast = brief_cast(brief)
    target = str(cast.get("becomes") or "")
    if len(names) > 1 and not _allows_many(brief, "hero"):
        allowed = {_who(cast.get("hero") or "").lower()}
        if target:
            allowed.add(_who(target).lower())
        changed = bool(target) and {name.lower() for name in names} <= allowed
        if not changed:
            flags.append({"shot": None, "plain": "A second hero appears. The piece keeps one."})
    for index, scene in enumerate(board):
        if index and not _linked(board[index - 1], scene, bible):
            flags.append(
                {
                    "shot": index,
                    "plain": f"Shot {index + 1} is only atmosphere. It does not follow from the previous shot.",
                }
            )
        for element in bible["elements"]:
            if element["kind"] != "prop" or _allows_many(brief, element["name"]):
                continue
            if _variant_in(_blob(scene), element):
                flags.append(
                    {
                        "shot": index,
                        "plain": f"Shot {index + 1} introduces a new {element['name']}. The piece keeps one.",
                    }
                )
    for scene in board:
        if hero_has_verb(str(scene.get("protagonist") or "")):
            flags.append({"shot": None, "plain": "The hero contains a verb."})
            break
    if board and any("prop" in scene or "place" in scene for scene in board):
        cast = brief_cast(brief)
        blob = " ".join(_blob(scene) for scene in board)
        for noun in (cast.get("prop"), cast.get("place"), cast.get("threat"), cast.get("becomes")):
            missing = [word for word in str(noun or "").split() if word and not _has_word(blob, word)]
            if missing:
                flags.append({"shot": None, "plain": f"The brief's {noun} is missing from the story."})
    detail = flags[0]["plain"] if flags else "The story holds in one line."
    return {"ok": not flags, "what": what, "flags": flags, "detail": detail}


def apply_lock(text: str, locks: list[dict] | None) -> str:
    """Replace a variant with the one canonical name. Longer phrases first."""
    out = str(text or "")
    rows = sorted(locks or [], key=lambda row: len(str(row.get("from") or "")), reverse=True)
    for row in rows:
        src = str(row.get("from") or "").strip()
        dst = str(row.get("to") or "").strip()
        if not src or not dst or src.lower() == dst.lower():
            continue
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)
    return out


def render_guide(scene: dict) -> str:
    """The prompt the picture pass sees: locked words, then each canonical sentence once."""
    text = apply_lock(str(scene.get("prompt") or scene.get("guide") or ""), scene.get("lock_words"))
    for line in scene.get("lines") or []:
        sentence = str(line or "").strip()
        if sentence and sentence not in text:
            text = f"{text} {sentence}".strip()
    return text


def ensure_stills(elements: list[dict], folder) -> list[dict]:
    """Paint each reference still once. The same sentence returns the same file."""
    from pathlib import Path

    from xenoform.craft import paint_review_png

    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    painted = []
    for element in elements or []:
        row = dict(element)
        sentence = str(row.get("sentence") or "").strip()
        if not sentence:
            painted.append(row)
            continue
        name = _still_name(row.get("id") or row.get("kind") or "element", sentence)
        path = dest / name
        if not (path.exists() and path.stat().st_size > 32):
            painted_path = paint_review_png(
                dest,
                seed=2727,
                shot=str(row.get("kind") or "wide"),
                prompt=sentence,
                index=_kind_index(str(row.get("kind") or "")),
            )
            if painted_path != path:
                path.write_bytes(painted_path.read_bytes())
        row["still_name"] = name
        row["still"] = str(path)
        row["url"] = f"/media/continuity/{name}"
        painted.append(row)
    return painted


def attach_stills(scenes: list[dict], elements: list[dict]) -> list[dict]:
    """Point each shot at the still for the element it contains. A prop wins over the hero."""
    by_id = {str(row.get("id") or ""): row for row in elements or []}
    for scene in scenes or []:
        ids = [str(item) for item in (scene.get("element_ids") or [])]
        chosen = None
        for element_id in ids:
            row = by_id.get(element_id)
            if row and row.get("kind") == "prop":
                chosen = row
                break
        if chosen is None and ids:
            chosen = by_id.get(ids[0])
        if not chosen:
            continue
        if chosen.get("still"):
            scene["reference_still"] = chosen["still"]
        if chosen.get("still_name"):
            scene["still_name"] = chosen["still_name"]
        if chosen.get("url"):
            scene["reference_url"] = chosen["url"]
        if scene.get("guide_from") != "previous-last":
            scene["guide_from"] = "reference"
    return scenes


def compare_element(name: str, reference, shots: list[dict], *, sentence: str = "", still: str = "", still_name: str = "") -> dict | None:
    """Flag shots whose picture does not match the reference still."""
    bad = []
    for shot in shots or []:
        image = shot.get("image")
        if image is None or reference is None:
            continue
        score = similarity(reference, image)
        if not score["pass"]:
            bad.append(shot)
    if not bad:
        return None
    indices = [int(shot.get("index") or 0) for shot in bad]
    span = _span(indices)
    noun = str(name or "element").strip() or "element"
    start = float(bad[0].get("start") or 0)
    shots_ids = [f"s{index}" for index in indices]
    return {
        "id": f"continuity-{_slug(noun)}",
        "check": "continuity",
        "scene": shots_ids[0],
        "label": span[:1].upper() + span[1:] if span else "Continuity",
        "kind": "rerender",
        "plain": f"{noun} differs, {span}",
        "before": "reference still",
        "after": "re-render from the reference",
        "t": round(start, 4),
        "rank": 4,
        "op": {
            "op": "recast",
            "index": indices[0],
            "sentence": sentence,
            "still": still,
            "still_name": still_name,
            "shots": shots_ids,
        },
    }


def critique(scenes: list[dict], frames: dict[int, Any], elements: list[dict] | None = None) -> list[dict]:
    """Compare each canonical element across the shots that contain it."""
    catalog = {str(row.get("id") or ""): row for row in elements or []}
    grouped: dict[str, dict[str, Any]] = {}
    for scene in scenes or []:
        index = int(scene.get("index") or 0)
        image = frames.get(index)
        for element in _elements_on(scene, catalog):
            key = str(element.get("id") or "")
            if not key:
                continue
            bucket = grouped.setdefault(key, {"element": element, "shots": []})
            if image is None:
                continue
            bucket["shots"].append(
                {"index": index, "start": float(scene.get("start") or 0), "image": image}
            )
    flags = []
    for bucket in grouped.values():
        element = bucket["element"]
        reference = element.get("image")
        if reference is None:
            reference = _read_image(element.get("still") or "")
        if reference is None:
            continue
        flag = compare_element(
            str(element.get("name") or ""),
            reference,
            bucket["shots"],
            sentence=str(element.get("sentence") or ""),
            still=str(element.get("still") or ""),
            still_name=str(element.get("still_name") or ""),
        )
        if flag:
            flags.append(flag)
    return flags


def similarity(reference, image) -> dict[str, Any]:
    """Local comparator. Colour histogram, shape, and a downsampled embedding."""
    import numpy as np

    left = np.asarray(reference)
    right = np.asarray(image)
    colour = _colour_score(left, right)
    aspect = _aspect_ratio(_shape(left), _shape(right))
    embed = _cosine(_embed(left), _embed(right))
    shape_ok = aspect <= 1.45
    return {
        "colour": round(colour, 4),
        "aspect": round(aspect, 4),
        "embed": round(embed, 4),
        "pass": bool(colour >= 0.72 and shape_ok and embed >= 0.55),
    }


def rerender_ids(findings: list[dict]) -> list[str]:
    """Scene ids a review fix should send back to the picture pass."""
    ids: list[str] = []
    for row in findings or []:
        if row.get("kind") != "rerender":
            continue
        shots = [str(item) for item in ((row.get("op") or {}).get("shots") or []) if str(item)]
        if not shots:
            scene = str(row.get("scene") or "")
            shots = [scene] if scene and scene != "board" else []
        for shot in shots:
            if shot not in ids:
                ids.append(shot)
    return ids


def resolve_still(name: str, folder) -> str:
    from pathlib import Path

    base = Path(str(name or "")).name
    if not base:
        return ""
    path = Path(folder) / base
    return str(path) if path.is_file() else ""


def _bible(brief: str, scenes: list[dict]) -> dict[str, Any]:
    text = _corpus(brief, scenes)
    names = _hero_names(scenes)
    hero = cast_lock(names[0] if names else "")
    elements = [hero]
    for name, spec in _PROPS.items():
        if not any(_has_word(text, word) for word in spec["words"]):
            continue
        if _allows_many(brief, name):
            continue
        elements.append(
            {
                "id": f"prop-{name}",
                "kind": "prop",
                "name": name,
                "sentence": spec["sentence"],
                "words": list(spec["words"]),
                "variants": list(spec["variants"]),
                "lock": "prop",
            }
        )
    known_props = {element["name"] for element in elements if element["kind"] == "prop"}
    for scene in scenes:
        prop = " ".join(str(scene.get("prop") or "").split()).lower()
        if not prop or prop in known_props or _allows_many(brief, prop):
            continue
        if not _has_word(text, prop):
            continue
        known_props.add(prop)
        elements.append(
            {
                "id": f"prop-{_slug(prop)}",
                "kind": "prop",
                "name": prop,
                "sentence": f"The {prop} is one {prop}, the same object in every shot.",
                "words": [prop],
                "variants": [],
                "lock": "prop",
            }
        )
    place = _first_word(text, _PLACES)
    if not place:
        for scene in scenes:
            named = " ".join(str(scene.get("place") or "").split()).lower()
            if named:
                place = named
                break
    if place:
        elements.append(
            {
                "id": f"place-{place}",
                "kind": "location",
                "name": _title_place(place),
                "sentence": f"The place is {_place_phrase(place)}, the same ground in every shot.",
                "words": [place],
                "lock": "place",
            }
        )
    hour = _first_word(text, _TIMES)
    if hour and not _changes(brief, "time"):
        elements.append(
            {
                "id": f"time-{hour}",
                "kind": "time",
                "name": hour,
                "sentence": f"The time of day is {hour}, the same hour in every shot.",
                "words": [hour],
                "lock": "time",
            }
        )
    sky = _first_word(text, _WEATHER)
    if sky and not _changes(brief, "weather"):
        elements.append(
            {
                "id": f"weather-{sky}",
                "kind": "weather",
                "name": sky,
                "sentence": f"The weather is {sky}, the same sky in every shot.",
                "words": [sky],
                "lock": "weather",
            }
        )
    return {"what": _what(brief, scenes, hero), "elements": elements, "cast": hero}


def _lines_for(scene: dict, bible: dict, brief: str) -> list[str]:
    lines = []
    blob = _blob(scene)
    journey = _journey(brief)
    for element in bible["elements"]:
        if _appears(scene, element, blob, journey):
            sentence = str(element.get("sentence") or "")
            if sentence and sentence not in lines:
                lines.append(sentence)
    return lines


def _appears(scene: dict, element: dict, blob: str, journey: bool) -> bool:
    kind = element.get("kind")
    if kind == "hero":
        if not str(scene.get("protagonist") or "").strip():
            return False
        who = str(element.get("name") or "").lower()
        current = _who(str(scene.get("protagonist") or "")).lower()
        return current == who
    if kind == "prop":
        if any(_has_word(blob, word) for word in element.get("words") or []):
            return True
        if _variant_in(blob, element):
            return True
        return str(scene.get("beat") or "") == "setup"
    if kind in {"time", "weather"}:
        return True
    if kind == "location":
        if any(_has_word(blob, word) for word in element.get("words") or []):
            return True
        return not journey
    return False


def _because(previous: dict | None, scene: dict, bible: dict) -> str:
    if previous is None:
        return "This opens the piece."
    line = _link_line(previous, scene, bible)
    return line


def _linked(previous: dict, scene: dict, bible: dict) -> bool:
    return bool(_link_line(previous, scene, bible))


def _link_line(previous: dict, scene: dict, bible: dict) -> str:
    prev_who = _who(str(previous.get("protagonist") or "")).lower()
    who = _who(str(scene.get("protagonist") or "")).lower()
    if who and who != "the lead" and who == prev_who:
        return f"{_who(str(scene.get('protagonist') or ''))} carries across the cut."
    blob = _blob(scene)
    prev = _blob(previous)
    for element in bible["elements"]:
        if element.get("kind") not in {"prop", "location"}:
            continue
        if _mentioned(blob, element) and _mentioned(prev, element):
            return f"The {element['name']} carries across the cut."
    if _CAUSE.search(blob) and not _ATMOSPHERE.search(blob):
        action = " ".join(str(scene.get("action") or "").split())
        return f"This follows because {action}." if action else ""
    if _ATMOSPHERE.search(blob) and not (who and who == prev_who):
        return ""
    action = " ".join(str(scene.get("action") or "").split())
    if action and not _ATMOSPHERE.search(blob):
        verb = str(scene.get("verb") or "").strip()
        if verb and verb in action:
            return f"This follows because {action}."
    return ""


def _mentioned(blob: str, element: dict) -> bool:
    if any(_has_word(blob, word) for word in element.get("words") or []):
        return True
    return _variant_in(blob, element)


def _variant_in(blob: str, element: dict) -> bool:
    return any(_has_word(blob, word) for word in element.get("variants") or [])


def _locks(bible: dict) -> list[dict[str, str]]:
    rows = []
    for element in bible["elements"]:
        if element.get("kind") != "prop":
            continue
        for variant in element.get("variants") or []:
            rows.append({"from": variant, "to": element["name"]})
    return rows


def _what(brief: str, scenes: list[dict], hero: dict) -> str:
    text = " ".join(str(brief or "").split())
    if text:
        sentence = text.split(".")[0].strip().rstrip(",")
        if sentence and not sentence.endswith("."):
            sentence += "."
        return sentence[:180]
    who = str(hero.get("name") or "the lead")
    goal = ""
    for scene in scenes:
        goal = " ".join(str(scene.get("goal") or "").split())
        if goal:
            break
    if goal:
        sentence = goal[:1].upper() + goal[1:]
        if not sentence.endswith("."):
            sentence += "."
        return sentence[:180]
    return ""


def _readable(sentence: str) -> bool:
    words = str(sentence or "").replace(".", " ").split()
    return len(words) >= 3


def _hero_names(scenes: list[dict]) -> list[str]:
    names = []
    seen = set()
    for scene in scenes:
        name = _who(str(scene.get("protagonist") or ""))
        if not str(scene.get("protagonist") or "").strip():
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _who(name: str) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        return "the lead"
    if text.lower().startswith("the "):
        return text
    return f"the {text}"


def _corpus(brief: str, scenes: list[dict]) -> str:
    parts = [str(brief or "")]
    for scene in scenes:
        parts.append(_blob(scene))
    return " ".join(parts).lower()


def _blob(scene: dict) -> str:
    """The words the planner and the director wrote. The stamped guide is not a source."""
    return " ".join(
        str(scene.get(key) or "")
        for key in ("action", "prompt", "verb", "protagonist")
    ).lower()


def _has_word(text: str, word: str) -> bool:
    return bool(re.search(rf"\b{re.escape(word.lower())}\b", str(text or "").lower()))


def _first_word(text: str, words: tuple[str, ...]) -> str:
    for word in words:
        if _has_word(text, word):
            return word
    return ""


def _title_place(name: str) -> str:
    if name.lower() in {"jupiter", "mars", "earth", "moon"}:
        return name[:1].upper() + name[1:]
    return name


def _place_phrase(name: str) -> str:
    titled = _title_place(name)
    if name.lower() in {"jupiter", "mars", "earth", "moon"}:
        return titled
    if titled.lower().startswith("the "):
        return titled
    return f"the {titled}"


def _journey(brief: str) -> bool:
    return bool(re.search(r"\bfrom\b.+\bto\b", str(brief or ""), re.I))


def _changes(brief: str, kind: str) -> bool:
    text = str(brief or "")
    if kind == "time":
        return bool(re.search(r"\b(from \w+ to \w+|time passes|hours later|the next day)\b", text, re.I))
    return bool(re.search(r"\b(the weather changes|then the rain|then the sun)\b", text, re.I))


def _allows_many(brief: str, noun: str) -> bool:
    pattern = _MANY.format(noun=re.escape(noun.lower()))
    return bool(re.search(pattern, str(brief or ""), re.I))


def _elements_on(scene: dict, catalog: dict[str, dict]) -> list[dict]:
    rows = []
    for element_id in scene.get("element_ids") or []:
        key = str(element_id)
        known = catalog.get(key) or {}
        rows.append(
            {
                "id": key,
                "name": known.get("name") or _name_from_id(key),
                "sentence": known.get("sentence") or "",
                "still": known.get("still") or "",
                "still_name": known.get("still_name") or "",
                "image": known.get("image"),
            }
        )
    return rows


def _name_from_id(element_id: str) -> str:
    if element_id == "hero":
        return "hero"
    if "-" in element_id:
        return element_id.split("-", 1)[1]
    return element_id


def _span(indices: list[int]) -> str:
    nums = [index + 1 for index in indices]
    if not nums:
        return "the cut"
    if len(nums) == 1:
        return f"shot {nums[0]}"
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"shots {nums[0]}-{nums[-1]}"
    return "shots " + ", ".join(str(num) for num in nums)


def _slug(name: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return token or "element"


def _still_name(element_id: str, sentence: str) -> str:
    digest = hashlib.sha256(f"{element_id}:{sentence}".encode("utf-8")).hexdigest()[:16]
    return f"{digest}.png"


def _kind_index(kind: str) -> int:
    try:
        return CAST_KINDS.index(kind)
    except ValueError:
        return 0


def _colour_score(left, right) -> float:
    import numpy as np

    def hist(image):
        flat = np.asarray(image, dtype=np.float64).reshape(-1, image.shape[-1])[:, :3]
        bins = (flat / 32).astype(np.int32).clip(0, 7)
        index = bins[:, 0] * 64 + bins[:, 1] * 8 + bins[:, 2]
        counts = np.bincount(index, minlength=512).astype(np.float64)
        total = counts.sum() or 1.0
        return counts / total

    a = hist(left)
    b = hist(right)
    return float(np.minimum(a, b).sum())


def _shape(image) -> dict[str, float]:
    import numpy as np

    gray = np.asarray(image, dtype=np.float64).mean(axis=2) if np.asarray(image).ndim == 3 else np.asarray(image, dtype=np.float64)
    mask = gray > float(gray.mean())
    if int(mask.sum()) < 8:
        return {"aspect": 1.0}
    ys, xs = np.where(mask)
    height = float(ys.max() - ys.min() + 1)
    width = float(xs.max() - xs.min() + 1)
    return {"aspect": width / max(height, 1.0)}


def _aspect_ratio(left: dict, right: dict) -> float:
    a = max(float(left.get("aspect") or 1.0), 0.05)
    b = max(float(right.get("aspect") or 1.0), 0.05)
    return max(a, b) / min(a, b)


def _embed(image):
    import numpy as np

    gray = np.asarray(image, dtype=np.float64).mean(axis=2) if np.asarray(image).ndim == 3 else np.asarray(image, dtype=np.float64)
    ys = np.linspace(0, gray.shape[0] - 1, 8).astype(int)
    xs = np.linspace(0, gray.shape[1] - 1, 8).astype(int)
    small = gray[ys][:, xs].reshape(-1)
    norm = float(np.linalg.norm(small)) or 1.0
    return small / norm


def _cosine(left, right) -> float:
    import numpy as np

    return float(np.dot(left, right))


def _read_image(path: str):
    from pathlib import Path

    picture = Path(str(path or ""))
    if not picture.is_file():
        return None
    import subprocess

    import numpy as np

    from xenoform.video import ffmpeg_bin, ffprobe_bin

    raw = subprocess.check_output(
        [
            ffmpeg_bin(),
            "-v",
            "error",
            "-i",
            str(picture),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]
    )
    if not raw:
        return None
    probe = subprocess.check_output(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(picture),
        ],
        text=True,
    ).strip()
    width, height = (int(part) for part in probe.split("x"))
    count = height * width * 3
    return np.frombuffer(raw[:count], dtype=np.uint8).reshape(height, width, 3)
