"""Plan a morph from two existing shots. No new subject is allowed in."""

from __future__ import annotations

import re
from typing import Any

from xenoform.hardware import FAST_CHECKPOINT
from xenoform.morph.gate import review
from xenoform.morph.workflow import graph
from xenoform.storyboard import _LEXICON, _PLACE_PREP, _tokens, _read_np, parse_brief

SEED = 2727
WIDTH = 384
HEIGHT = 224
QUALITY_WIDTH = 704
QUALITY_HEIGHT = 384
CHECKPOINT = FAST_CHECKPOINT
METHODS = ("v2v-ramp", "region-staged", "keyframe-blend", "cross-clip")
_MOTION = {"run", "walk", "chase", "flee", "gallop", "sprint"}
_STOP = frozenset(
    "a an the of to from into and or with at on in is are was be this that for its it".split()
)


def nouns(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {word for word in words if word not in _STOP and len(word) > 2}


def restyle_checkpoint(fast: bool = False, tier_id: str | None = None) -> tuple[str, int, int]:
    """LTX-2.3 when that file is on the machine. LTX 0.9.5 is the fast option.

    12 GB (and an unknown card) only accepts an fp8 or int8 file. 24 GB may use
    the full weights. 8 GB stays on 0.9.5. Turbo never calls this.
    """
    if fast:
        return CHECKPOINT, WIDTH, HEIGHT
    if not tier_id:
        from xenoform.hardware import detect_tier

        tier_id = str(detect_tier().get("id") or "")
    from xenoform.hardware import _ltx23_for

    if tier_id == "8gb":
        name = ""
    elif tier_id == "24gb":
        name = _ltx23_for("24gb")
    else:
        name = _ltx23_for("12gb")
    if name:
        return name, QUALITY_WIDTH, QUALITY_HEIGHT
    return CHECKPOINT, WIDTH, HEIGHT


def _verb_forms(verb: str) -> set[str]:
    info = _LEXICON.get(str(verb or "").lower())
    if not info:
        return {verb.lower()} if verb else set()
    base = info["base"]
    return {word for word, row in _LEXICON.items() if row["base"] == base}


def _becomes_object(text: str) -> str:
    """The noun after ``becomes`` or ``into``, read with the storyboard noun phrase."""
    tokens = _tokens(text)
    for index, word in enumerate(tokens):
        info = _LEXICON.get(word)
        if info and info["base"] == "become":
            words, _cursor = _read_np(tokens, index + 1)
            if words:
                return " ".join(words)
        if word == "into":
            words, _cursor = _read_np(tokens, index + 1)
            if words:
                return " ".join(words)
    return ""


def _motion(text: str) -> str:
    for word in _tokens(text):
        info = _LEXICON.get(word)
        if info and info["kind"] != "base" and info["base"] not in {"become", "be"}:
            return word
    return ""


def _place_phrase(text: str, setting: str) -> str:
    if not setting:
        return ""
    tokens = _tokens(text)
    head = setting.split()[0]
    if head not in tokens:
        return ""
    index = tokens.index(head)
    cursor = index - 1
    while cursor >= 0 and tokens[cursor] in {"a", "an", "the"}:
        cursor -= 1
    prep = tokens[cursor] if cursor >= 0 and tokens[cursor] in _PLACE_PREP else ""
    if not prep:
        return ""
    article = "the" if prep in {"in", "on", "at", "inside"} else "a"
    return f" {prep} {article} {setting}"


def _bare_name(value: str) -> str:
    text = " ".join(str(value or "").replace("-", " ").split()).lower()
    if text.startswith("the "):
        return text[4:]
    return text


def _story_cast(before: dict, after: dict) -> dict[str, str] | None:
    """Subject B is the story's form change, not a noun guessed from the action line."""
    target = _bare_name(after.get("becomes") or "")
    if not target:
        return None
    subject = _bare_name(before.get("protagonist") or before.get("form") or "")
    if not subject or subject == target:
        subject = _bare_name(before.get("form") or "")
    if not subject:
        return None
    motion = str(after.get("motion") or before.get("motion") or "").strip()
    verb = motion or str(after.get("change_verb") or before.get("change_verb") or "")
    article = after.get("becomes_article")
    if article is None:
        article = "a"
    return {
        "subject": subject,
        "other": target,
        "verb": verb,
        "setting": str(after.get("place") or before.get("place") or ""),
        "article": str(article),
    }


def read_cast(text: str) -> dict[str, str]:
    """Subject, the thing it becomes, the action, and the place. Same parser as the storyboard."""
    parsed = parse_brief(text) if str(text or "").strip() else {}
    subject = str(parsed.get("subject") or "")
    verb = str(parsed.get("motion_verb") or parsed.get("verb") or "")
    other = str(parsed.get("becomes") or "") or _becomes_object(text)
    if not parsed.get("motion_verb") and str(parsed.get("base") or "") == "become":
        motion = _motion(text)
        if motion:
            verb = motion
    article = str(parsed.get("becomes_article") or "") if parsed.get("becomes") else None
    return {
        "subject": subject,
        "other": other,
        "verb": verb,
        "setting": str(parsed.get("setting") or ""),
        "article": article,
    }


def _cast_from(brief: str, before: dict, after: dict) -> dict[str, str]:
    """The story's form change wins. The brief is next. Register fields are ignored."""
    story = _story_cast(before, after)
    if story and story["subject"] and story["other"]:
        return story
    chosen = read_cast(brief)
    if chosen["subject"] and chosen["other"]:
        return chosen
    left = read_cast(str(before.get("action") or ""))
    right = read_cast(str(after.get("action") or ""))
    subject = chosen["subject"] or left["subject"] or right["subject"]
    other = chosen["other"] or right["other"] or left["other"]
    if not other:
        other = right["subject"] if right["subject"] and right["subject"] != subject else subject
    verb = chosen["verb"] or _motion(brief) or left["verb"] or right["verb"]
    setting = chosen["setting"] or left["setting"] or right["setting"]
    article = chosen.get("article")
    if not chosen["other"]:
        article = right.get("article") or left.get("article") or article
    return {"subject": subject, "other": other, "verb": verb, "setting": setting, "article": article if article is not None else "a"}


def build_prompt(cast: dict[str, str], source: str) -> str:
    """One sentence. Camera words are fixed. Subjects come only from the cast."""
    subject = cast.get("subject") or "subject"
    other = cast.get("other") or subject
    verb = cast.get("verb") or ""
    info = _LEXICON.get(verb) or {}
    base = info.get("base") or (verb or "move")
    gerund = next((word for word, row in _LEXICON.items() if row["base"] == base and row["kind"] == "gerund"), base)
    side = " side-on" if base in _MOTION else ""
    stride = " mid-stride" if base == "run" else ""
    place = _place_phrase(source, cast.get("setting") or "")
    article = cast.get("article")
    if article is None:
        article = "a"
    into = f"{article} {other}".strip() if str(article).strip() else other
    return (
        f"A photoreal {subject} {gerund}{side}{place}, "
        f"its body smoothly reshaping into {into}{stride}; "
        f"same camera, same lighting, continuous {base}"
    )


def cast_words(cast: dict[str, str]) -> set[str]:
    found: set[str] = set()
    for key in ("subject", "other", "setting"):
        found |= nouns(cast.get(key) or "")
    found |= _verb_forms(cast.get("verb") or "")
    return {word for word in found if word}


def snap_beat(when: float, beats: list) -> tuple[float, float]:
    clock = []
    for beat in beats or []:
        try:
            clock.append(float(beat))
        except (TypeError, ValueError):
            continue
    if not clock:
        return float(when), 0.0
    nearest = min(clock, key=lambda beat: abs(beat - float(when)))
    return nearest, abs(nearest - float(when))


def plan_join(
    before: dict,
    after: dict,
    method: str,
    beats: list,
    when: float | None = None,
    brief: str = "",
    fast: bool = False,
) -> dict[str, Any]:
    """One blend. The prompt names subject A, the action, and subject B, and nothing from the register."""
    kind = str(method or "")
    start = float(after.get("start") or 0.0) if when is None else float(when)
    at, drift = snap_beat(start, beats)
    source = " ".join(part for part in (brief, str(before.get("action") or ""), str(after.get("action") or "")) if part)
    cast = _cast_from(brief, before, after)
    checkpoint, width, height = restyle_checkpoint(fast)
    region = ""
    if kind == "region-staged":
        region = cast["other"] or cast["subject"] or "subject"
    samples = 0 if kind in ("keyframe-blend", "cross-clip") else 4
    strength = [0.0, 0.0] if samples == 0 else [0.15, 0.35]
    allowed = cast_words(cast)
    plan = {
        "method": kind,
        "at": round(at, 4),
        "drift": round(drift, 4),
        "seed": SEED,
        "width": width,
        "height": height,
        "checkpoint": checkpoint,
        "fast": bool(fast),
        "subject_a": cast["subject"],
        "subject_b": cast["other"],
        "action": cast["verb"],
        "setting": cast["setting"],
        "nouns": sorted(allowed),
        "cast": sorted(allowed),
        "prompt": build_prompt(cast, source),
        "region": region,
        "samples": samples,
        "strength": strength,
        "before": str(before.get("action") or ""),
        "after": str(after.get("action") or ""),
    }
    plan["workflow"] = graph(plan)
    plan["qa"] = review(plan, beats)
    return plan


def plan_board(
    scenes: list[dict],
    beats: list,
    method: str = "keyframe-blend",
    brief: str = "",
    fast: bool = False,
    lock: bool = False,
    sections: list | None = None,
    drops: list | None = None,
    hit: bool = False,
) -> dict[str, Any]:
    """Up to two signature joins. Anything past that stays a hard cut.

    ``lock`` lands each join on a downbeat or a drop and keeps breakdowns sparse.
    """
    from xenoform.morph.lock import choose_joins, land_time

    marks = [index for index, scene in enumerate(scenes or []) if scene.get("signature") and index > 0]
    if lock and sections:
        chosen, dropped = choose_joins(scenes, sections, method)
        note = "Drops chain on the downbeat. Breakdowns keep one morph."
        if dropped:
            note = f"Kept {len(chosen)}. The rest stay hard cuts."
    else:
        chosen = [
            {
                "index": index,
                "section": "",
                "pace": "signature",
                "reason": "Signature morph.",
            }
            for index in marks[:2]
        ]
        dropped = max(0, len(marks) - 2)
        note = "No morph on this cut. Hard cuts only." if not chosen else ""
        if len(marks) > 2:
            note = "Kept 2. The rest stay hard cuts."
    joins = []
    for row in chosen:
        index = int(row["index"])
        start = float(scenes[index].get("start") or 0)
        if lock:
            at, kind = land_time(start, beats, section=str(row.get("section") or ""), drops=drops)
        else:
            at, kind = start, "beat"
        plan = plan_join(
            scenes[index - 1],
            scenes[index],
            method,
            beats,
            when=at,
            brief=brief,
            fast=fast,
        )
        plan["land"] = kind if lock else "beat"
        plan["pace"] = row["pace"]
        plan["reason"] = row["reason"]
        plan["hit"] = bool(hit) and bool(lock) and kind in {"downbeat", "drop"}
        plan["downbeat"] = round(float(plan["at"]), 4) if lock else None
        joins.append(plan)
    if lock and not joins:
        note = "No morph on this cut. Hard cuts only."
    passed = all(join["qa"]["pass"] for join in joins) if joins else True
    return {
        "method": str(method or ""),
        "joins": joins,
        "pass": passed and str(method or "") in METHODS,
        "note": note,
        "kept": len(joins),
        "dropped": dropped,
        "lock": bool(lock),
        "hit": bool(hit) and bool(lock),
    }
