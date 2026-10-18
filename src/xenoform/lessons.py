"""Render lessons as defaults and Critic rules.

The curated log is ``docs/LESSONS.md``. Rules a director saves from a note
live in ``lessons.json`` and are appended to that log. Built-in lessons apply
even when the JSON file is empty.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

DISSOLVE_CAP = 8
GUIDE_OFFSET_FRAMES = 32
MID_GUIDE_CAP = 0.40
BOLT_GUIDE_CAP = 0.30

# Soft dissolves ghost when they run long. Grow-out stays a zoom regather.
SOFT_DISSOLVES = {"dissolve", "pour-harden", "ribbon", "droplet-gather", "swim"}
IMPACT_EDITS = {"dive-splash", "bolt-strike", "droplet-burst", "spike-burst", "snap"}
SLOW_SPEEDS = {"slow", "half", "0.5", "0.50", "half-speed", "slow-mo", "slowmo", "slow motion"}
FORBIDDEN_LOOKS = ("shimmer", "wavy", "warp")

# Raw fade lengths. Soft dissolves are capped at DISSOLVE_CAP.
_RAW_FADE = {
    "pour-harden": 8,
    "dissolve": 8,
    "droplet-burst": 2,
    "ribbon": 4,
    "snap": 0,
    "hard cut": 0,
    "grow-out": 14,
    "continuous": 14,
    "droplet-gather": 10,
    "spike-burst": 1,
    "dive-splash": 6,
    "fly-through": 3,
    "bolt-strike": 0,
    "swim": 12,
}

BUILTIN: tuple[dict[str, Any], ...] = (
    {
        "id": "slow-into-impact",
        "date": "2026-10-17",
        "lesson": "Half-speed slow-mo to beat-lock the dive made the ending limp.",
        "rule": "Slow-mo on an impact is an anticlimax. Trim into the hit; slow only after.",
        "note": "slow-motion into the impact is an anticlimax; speed up into the hit and slow only after",
        "builtin": True,
    },
    {
        "id": "no-shimmer",
        "date": "2026-10-17",
        "lesson": "Wavy shimmer post effect ruins visuals.",
        "rule": "Never a default. Not offered as a preset.",
        "note": "drop the shimmer look; it is not a preset",
        "builtin": True,
    },
    {
        "id": "bolt-guide-cap",
        "date": "2026-10-17",
        "lesson": "Bright bolt guide >0.3 blows out dark forms.",
        "rule": "Bolt guide strength caps at 0.30.",
        "note": "the bolt guide is hot; cap it at 0.30",
        "builtin": True,
    },
    {
        "id": "mid-guide-cap",
        "date": "2026-10-17",
        "lesson": "LTX mid guides >0.4 cause hard cuts and land about 32 frames early.",
        "rule": "Mid guides stay at or under 0.40. End guides sit late, with a 32-frame offset.",
        "note": "the mid guide is hot and lands early; cap it at 0.40 and push the end late",
        "builtin": True,
    },
    {
        "id": "dissolve-cap",
        "date": "2026-10-17",
        "lesson": "Long soft dissolves ghost.",
        "rule": "Dissolves stay at 8 frames or under, with a zoom-from-point regather.",
        "note": "cap the dissolve at 8 frames and regather from a point",
        "builtin": True,
    },
    {
        "id": "draft-carries",
        "date": "2026-10-17",
        "lesson": "Fast low-res drafts beat polish for iteration.",
        "rule": "Draft then Final. Seed 2727 and second-based retimes carry to full resolution.",
        "note": "",
        "builtin": True,
    },
    {
        "id": "iterate-fast",
        "date": "2026-10-17",
        "lesson": "Iteration speed beats polish; draft fast, polish once.",
        "rule": "Live, then Turbo, then Draft, then Final. The seed and the retime in seconds stay put.",
        "note": "",
        "builtin": True,
    },
    {
        "id": "live-first",
        "date": "2026-10-17",
        "lesson": "The browser picture is the cut that always exists.",
        "rule": "Live plays with no model. Turbo, Draft, and Final are the optional passes.",
        "note": "",
        "builtin": True,
    },
    {
        "id": "freeze-fluid",
        "date": "2026-10-17",
        "lesson": "Stills posing as motion read dead.",
        "rule": "Critic flags frozen frames. Impacts prefer dive-splash or droplet-burst.",
        "note": "the hit is a still; cut it as a dive-splash or a droplet-burst",
        "builtin": True,
    },
    {
        "id": "registers-headline",
        "date": "2026-10-17",
        "lesson": "Varied themes show the tool better than polishing one clip.",
        "rule": "Registers and the dice stay the headline.",
        "note": "",
        "builtin": True,
    },
    {
        "id": "shots-not-morphs",
        "date": "2026-10-17",
        "lesson": "Keyframe morphs read as a blend. A cut wants shots.",
        "rule": "One action shot per card, hard-cut on the bar. A morph is a signature, once or twice, usually on the drop. Liquid metal is a Look. LTX-2.3 is the core video model. LTX 0.9.5 covers morphs and Turbo. Wan 2.2 is an optional open-weights alternative.",
        "note": "the board is morphing; cut the action and keep one signature",
        "builtin": True,
    },
    {
        "id": "motion-director",
        "date": "2026-10-17",
        "lesson": "A fresh-eyes pass ships the cut, or it asks for one more pass.",
        "rule": "Review samples the picture on its own, retells it with the sound off, and scores a measured bar. The planner pitches treatments and a style bible before the full render. The picture locks to timing.json. Values come from the seed and the frame.",
        "note": "the cut is not ready for a fresh pair of eyes",
        "builtin": True,
    },
    {
        "id": "continuity",
        "date": "2026-10-17",
        "lesson": "The phone changed shape in every opening shot, and the story looked cool but did not make sense.",
        "rule": "One hero, one prop, one place. The same sentence and the same reference still go into every shot where they appear. Each shot follows from the last. Review re-renders only the shots that break it.",
        "note": "",
        "builtin": True,
    },
)


def cap_for(edit: str, key: str) -> float:
    """Guide ceiling for a recipe. Bolt stays at 0.30. Everything else at 0.40."""
    if str(edit) in {"bolt-strike", "bolt-strike hold"} and key in {"guide", "mid", "bolt"}:
        return BOLT_GUIDE_CAP
    return MID_GUIDE_CAP


def clamp_strengths(edit: str, strengths: dict | None) -> dict[str, Any]:
    """Cap keys the note already set. Does not invent a guide the note never touched."""
    out = dict(strengths or {})
    for key in ("guide", "mid", "bolt"):
        if key not in out:
            continue
        try:
            value = float(out[key])
        except (TypeError, ValueError):
            continue
        out[key] = round(min(value, cap_for(edit, key)), 4)
    if any(key in out for key in ("guide", "mid", "bolt", "exposure")):
        out["end"] = "late"
        try:
            offset = int(out.get("offset_frames") or 0)
        except (TypeError, ValueError):
            offset = 0
        out["offset_frames"] = max(offset, GUIDE_OFFSET_FRAMES)
    return out


def default_strengths(edit: str, current: dict | None = None) -> dict[str, Any]:
    """Render default: mid and guide sit on the recipe cap, end guide late by 32 frames."""
    base: dict[str, Any] = {
        "mid": cap_for(edit, "mid"),
        "guide": cap_for(edit, "guide"),
        "end": "late",
        "offset_frames": GUIDE_OFFSET_FRAMES,
    }
    base.update(current or {})
    return clamp_strengths(edit, base)


def fade_frames(name: str) -> int:
    """Frame count for a transition. Soft dissolves never exceed 8."""
    raw = int(_RAW_FADE.get(str(name), 4))
    if str(name) in SOFT_DISSOLVES:
        return min(raw, DISSOLVE_CAP)
    return raw


def capped_fade(transition: str) -> int:
    """Same cap, reading the director table so new recipes stay in sync."""
    try:
        from xenoform.director import TRANSITION_FADE

        raw = int(TRANSITION_FADE.get(str(transition), _RAW_FADE.get(str(transition), 4)))
    except Exception:
        raw = int(_RAW_FADE.get(str(transition), 4))
    if str(transition) in SOFT_DISSOLVES:
        return min(raw, DISSOLVE_CAP)
    return raw


def look_allowed(preset: dict) -> bool:
    blob = " ".join(str(preset.get(key) or "") for key in ("id", "name", "note")).lower()
    return not any(word in blob for word in FORBIDDEN_LOOKS)


def approach_dst(src: float, dst: float) -> float:
    """Land the impact on or before the source peak so the approach speeds up."""
    return round(max(0.0, min(float(dst), float(src))), 4)


def is_impact(scene: dict) -> bool:
    if scene.get("beat") == "climax":
        return True
    if str(scene.get("edit") or "") in IMPACT_EDITS:
        return True
    return bool(re.search(r"impact|splash|strike|bolt|dive|\bland\b", str(scene.get("action") or ""), re.I))


def _slow(scene: dict) -> bool:
    retime = scene.get("retime") or {}
    speed = str(retime.get("speed") or "").lower()
    if speed in SLOW_SPEEDS or "slow" in speed:
        return True
    anchors = retime.get("anchors_s") or []
    if len(anchors) >= 2:
        try:
            return float(anchors[1][1]) > float(anchors[1][0]) + 0.04
        except (TypeError, ValueError, IndexError):
            return False
    return False


def stamp_scene(scene: dict) -> dict:
    """Write lesson defaults onto one card: guide caps, dissolve length, impact trim."""
    edit = str(scene.get("edit") or "")
    scene["guide_strengths"] = clamp_strengths(edit, scene.get("guide_strengths"))
    scene["fade_frames"] = fade_frames(edit)
    if is_impact(scene) and _slow(scene):
        retime = dict(scene.get("retime") or {})
        anchors = [list(pair) for pair in retime.get("anchors_s") or []]
        if len(anchors) >= 2:
            anchors[1][1] = approach_dst(float(anchors[1][0]), float(anchors[1][1]))
            retime["anchors_s"] = anchors
        speed = str(retime.get("speed") or "").lower()
        if speed in SLOW_SPEEDS or "slow" in speed:
            retime["speed"] = "trim"
        scene["retime"] = retime
    return scene


def builtin_flags(scenes: list[dict], looks: list[dict] | None = None) -> list[dict]:
    """Critic notes from the curated lessons."""
    notes: list[dict] = []
    for scene in scenes:
        sid = f"s{int(scene['index'])}"
        label = f"Scene {int(scene['index']) + 1:02d}"
        edit = str(scene.get("edit") or "")
        if is_impact(scene) and _slow(scene):
            notes.append(
                {
                    "note": "slow-motion into the impact is an anticlimax; speed up into the hit and slow only after",
                    "reason": f"{label} eases into the hit. Trim into the impact and let the slow-mo happen after.",
                    "score": 0.93,
                    "scene": sid,
                    "lesson_id": "slow-into-impact",
                }
            )
        strengths = scene.get("guide_strengths") or {}
        for key in ("guide", "mid", "bolt"):
            if key not in strengths:
                continue
            try:
                value = float(strengths[key])
            except (TypeError, ValueError):
                continue
            limit = cap_for(edit, key)
            if value > limit + 1e-6:
                notes.append(
                    {
                        "note": f"scene {int(scene['index']) + 1} guide is hot; cap {key} at {limit:.2f}",
                        "reason": f"{label} {key} is {value:.2f}. The cap for this recipe is {limit:.2f}. End guides sit late.",
                        "score": 0.9,
                        "scene": sid,
                        "lesson_id": "bolt-guide-cap" if limit == BOLT_GUIDE_CAP else "mid-guide-cap",
                    }
                )
                break
        fade = scene.get("fade_frames")
        if fade is None:
            fade = _RAW_FADE.get(edit, 0)
        if edit in SOFT_DISSOLVES and int(fade) > DISSOLVE_CAP:
            notes.append(
                {
                    "note": "cap the dissolve at 8 frames and regather from a point",
                    "reason": f"{label} dissolves for {int(fade)} frames. Long soft dissolves ghost.",
                    "score": 0.84,
                    "scene": sid,
                    "lesson_id": "dissolve-cap",
                }
            )
        if scene.get("beat") == "climax" and scene.get("move") == "hold" and edit in {"dissolve", "continuous", "pour-harden"}:
            notes.append(
                {
                    "note": "the hit is a still; cut it as a dive-splash or a droplet-burst",
                    "reason": f"{label} holds through the climax. A still reads as a dead hit.",
                    "score": 0.8,
                    "scene": sid,
                    "lesson_id": "freeze-fluid",
                }
            )
    for look in looks or []:
        if not look_allowed(look):
            notes.append(
                {
                    "note": "drop the shimmer look; it is not a preset",
                    "reason": "A wavy shimmer post effect is not offered.",
                    "score": 0.95,
                    "scene": "auto",
                    "lesson_id": "no-shimmer",
                }
            )
            break
    return notes


def _scene_for(cond: dict, scenes: list[dict]) -> dict | None:
    if not scenes:
        return None
    token = str(cond.get("scene") or "")
    if token == "ending":
        return scenes[-1]
    match = re.fullmatch(r"s(\d+)", token)
    if match:
        index = int(match.group(1))
        return next((scene for scene in scenes if int(scene["index"]) == index), None)
    return None


def saved_flags(scenes: list[dict], saved: list[dict]) -> list[dict]:
    """Critic notes learned from this project's lessons.json."""
    notes = []
    for lesson in saved:
        if lesson.get("builtin"):
            continue
        text = " ".join(str(lesson.get("note") or "").split())
        if not text:
            continue
        for cond in lesson.get("when") or []:
            scene = _scene_for(cond, scenes)
            if scene is None:
                continue
            was = cond.get("edit_was")
            if was and scene.get("edit") != was:
                continue
            mood_was = cond.get("mood_was")
            if mood_was and cond.get("mood") and scene.get("mood") != mood_was:
                continue
            notes.append(
                {
                    "note": text,
                    "reason": f"Saved lesson: {lesson.get('rule') or lesson.get('lesson')}",
                    "score": 0.82,
                    "scene": f"s{int(scene['index'])}",
                    "lesson_id": lesson.get("id"),
                }
            )
            break
    return notes


def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _close(left: str, right: str) -> bool:
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    stop = {"the", "a", "an", "to", "of", "and", "it", "is", "on", "in"}
    words_a = {word for word in re.findall(r"[a-z0-9]+", a) if word not in stop and len(word) > 2}
    words_b = {word for word in re.findall(r"[a-z0-9]+", b) if word not in stop and len(word) > 2}
    return len(words_a & words_b) >= 4


def _changed(before: list[dict], after: list[dict]) -> bool:
    for old, new in zip(before, after):
        for key in ("action", "edit", "mood", "shot", "move", "retime", "guide_strengths", "fade_frames"):
            if old.get(key) != new.get(key):
                return True
    return False


def _when(before: list[dict], after: list[dict]) -> list[dict]:
    rows = []
    for old, new in zip(before, after):
        if old.get("edit") == new.get("edit") and old.get("mood") == new.get("mood") and old.get("action") == new.get("action"):
            continue
        token = "ending" if old is before[-1] else f"s{int(old['index'])}"
        rows.append(
            {
                "scene": token,
                "source": f"s{int(old['index'])}",
                "edit_was": old.get("edit"),
                "edit": new.get("edit"),
                "mood_was": old.get("mood"),
                "mood": new.get("mood"),
            }
        )
    return rows


def _rule_line(before: list[dict], after: list[dict]) -> str:
    for old, new in zip(before, after):
        if old.get("edit") != new.get("edit"):
            label = f"Scene {int(old['index']) + 1:02d}"
            return f"{label} edit {old.get('edit')} becomes {new.get('edit')}."
        if old.get("mood") != new.get("mood"):
            label = f"Scene {int(old['index']) + 1:02d}"
            return f"{label} mood {old.get('mood')} becomes {new.get('mood')}."
        if old.get("action") != new.get("action"):
            return f"Scene {int(old['index']) + 1:02d} action rewritten."
    return "Saved from a director's note."


def offer_for(
    note: str,
    before: list[dict],
    after: list[dict],
    suggestions: list[dict],
    saved: list[dict],
) -> dict | None:
    """Offer to save a note when it fixes a problem the critic already raises."""
    text = " ".join(str(note or "").split())
    if not text or not _changed(before, after):
        return None
    if any(_norm(row.get("note")) == _norm(text) for row in saved):
        return None
    recurring = any(_close(text, item.get("note") or "") for item in suggestions)
    if not recurring:
        recurring = any(_close(text, item.get("note") or "") or _close(text, item.get("lesson") or "") for item in BUILTIN)
    if not recurring:
        return None
    return {
        "offer": True,
        "lesson": text,
        "rule": _rule_line(before, after),
        "note": text,
        "when": _when(before, after),
        "prompt": "This note fixes a problem that keeps showing up. Save it as a lesson and the critic will raise it on the next cut.",
    }


def _retarget_patch(patch: dict, when: list, scenes: list[dict]) -> dict:
    """Point a stored patch at the current board. 'ending' follows the last card."""
    import copy

    out = copy.deepcopy(patch)
    if not scenes:
        return out
    last = f"s{int(scenes[-1]['index'])}"
    mapping: dict[str, str] = {}
    for cond in when or []:
        if not isinstance(cond, dict):
            continue
        source = str(cond.get("source") or "")
        token = str(cond.get("scene") or "")
        if token == "ending":
            dest = last
        else:
            match = re.fullmatch(r"s(\d+)", token)
            if not match:
                continue
            index = int(match.group(1))
            if not any(int(scene["index"]) == index for scene in scenes):
                continue
            dest = token
        if source:
            mapping[source] = dest
        elif token == "ending":
            targets = [item for item in out.get("target_scenes") or [] if item != "auto"]
            if len(targets) == 1:
                mapping[str(targets[0])] = dest

    def rewrite(value: Any) -> Any:
        return mapping.get(str(value), value)

    if mapping and out.get("target_scenes") and out["target_scenes"] != ["auto"]:
        out["target_scenes"] = [rewrite(item) for item in out["target_scenes"]]
    for change in out.get("changes") or []:
        if isinstance(change, dict) and change.get("scene"):
            change["scene"] = rewrite(change["scene"])
    retime = out.get("retime")
    if isinstance(retime, dict) and retime.get("scene"):
        retime["scene"] = rewrite(retime["scene"])
    if isinstance(out.get("rerender"), list):
        out["rerender"] = [rewrite(item) for item in out["rerender"]]
    return out


def saved_patch(note: str, scenes: list[dict], saved: list[dict]) -> dict | None:
    """Return a stored patch when this note is one the director already saved."""
    text = " ".join(str(note or "").split())
    if not text or not scenes:
        return None
    for lesson in saved:
        if lesson.get("builtin") or not isinstance(lesson.get("patch"), dict):
            continue
        if not _close(text, lesson.get("note") or ""):
            continue
        return _retarget_patch(lesson["patch"], list(lesson.get("when") or []), scenes)
    return None


def load_saved(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("lessons") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _append_log(path: Path, lesson: dict) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lesson_text = str(lesson.get("lesson") or "")
    if lesson_text and lesson_text in text:
        return
    day = lesson.get("date") or date.today().isoformat()
    rule = str(lesson.get("rule") or "").replace("|", "/")
    line = f"| {day} | {lesson_text.replace('|', '/')} | {rule} |\n"
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text + line, encoding="utf-8")


def save_learned(path: Path, lesson: dict, log_path: Path | None = None) -> dict:
    """Store one learned lesson. A repeat of the same note returns the existing row."""
    rows = load_saved(path)
    for row in rows:
        if _norm(row.get("note")) == _norm(lesson.get("note")):
            return row
    stored = {
        "id": "user-" + uuid.uuid4().hex[:8],
        "date": date.today().isoformat(),
        "lesson": " ".join(str(lesson.get("lesson") or lesson.get("note") or "").split())[:240],
        "rule": " ".join(str(lesson.get("rule") or "").split())[:240],
        "note": " ".join(str(lesson.get("note") or "").split())[:240],
        "when": list(lesson.get("when") or []),
        "patch": lesson.get("patch") if isinstance(lesson.get("patch"), dict) else None,
        "builtin": False,
    }
    rows.append(stored)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"lessons": rows}, indent=2) + "\n", encoding="utf-8")
    if log_path is not None:
        _append_log(log_path, stored)
    return stored


def catalog() -> list[dict]:
    """Built-in lessons, for the panel."""
    return [
        {"id": item["id"], "date": item["date"], "lesson": item["lesson"], "rule": item["rule"], "builtin": True}
        for item in BUILTIN
    ]
