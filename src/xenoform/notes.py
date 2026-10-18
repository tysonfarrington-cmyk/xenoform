"""Director's notes.

A plain-English note becomes a patch on the storyboard. The patch is checked
against a fixed schema, shown as a diff, then applied. Only segments whose
card hash, seed, model, or resolution changed are rendered again. Retimes are
stored in seconds so a later full-resolution pass lands on the same beats.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from xenoform.beatlock import anchors_at_fps, detect, snap
from xenoform.director import TRANSITIONS
from xenoform.lessons import approach_dst, builtin_flags, saved_flags, saved_patch, stamp_scene
from xenoform.storyboard import _guide

DEFAULT_SEED = 2727
MODEL_ID = "checkpoint"

RECIPES: tuple[str, ...] = (
    "snap",
    "ribbon",
    "pour-harden",
    "droplet-burst",
    "droplet-gather",
    "spike-burst",
    "grow-out",
    "dive-splash",
    "fly-through",
    "bolt-strike hold",
    "swim hold",
)

_RECIPE_CANON = {
    "bolt-strike hold": "bolt-strike",
    "bolt strike": "bolt-strike",
    "swim hold": "swim",
    "hard cut": "snap",
    "dissolve": "pour-harden",
    "continuous": "grow-out",
    "continuous take": "grow-out",
}

ALLOWED_FIELDS = ("action", "form", "shot", "move", "edit", "mood", "bars", "hold")
HASH_FIELDS = (
    "action",
    "form",
    "shot",
    "move",
    "edit",
    "mood",
    "bars",
    "guide",
    "retime",
    "guide_strengths",
    "fade_frames",
)

PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["target_scenes", "changes", "rerender", "rationale"],
    "properties": {
        "target_scenes": {"type": "array", "items": {"type": "string"}},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["field", "old", "new"],
                "properties": {
                    "scene": {"type": "string"},
                    "field": {"type": "string"},
                    "old": {},
                    "new": {},
                },
            },
        },
        "transition_type": {"type": ["string", "null"]},
        "speed": {"type": ["string", "null"]},
        "retime": {"type": ["object", "null"]},
        "guide_strengths": {"type": ["object", "null"]},
        "recipe": {"type": ["string", "null"]},
        "rerender": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
}

SYSTEM_PROMPT = """You are the note interpreter for Xenoform, a music-video director.
A director's note is plain English about a cut they just watched. Map it to one JSON patch.
Change only what the note asks. Keep every other scene card as it is.

Recipe catalogue (transition_type): snap, ribbon, pour-harden, droplet-burst, droplet-gather, spike-burst, grow-out, dive-splash, fly-through, bolt-strike hold, swim hold.

Scene ids are s0, s1, … matching the storyboard index. "scene 3" means s2 (people count from 1). "ending" is the last scene. "auto" means you choose from the note.

Allowed change fields: action, form, shot, move, edit, mood, bars, hold.
edit uses a catalogue id (dive-splash, bolt-strike, swim) or dissolve, hard cut, continuous.
A splash or a plop landing is dive-splash. A bolt or a strike that should hit the beat is bolt-strike, speed "hold", retime mode "snap-peak".
Slow-motion into an impact is an anticlimax: speed "trim", and the peak lands on or before its source time.
Guide caps: bolt guide/mid/bolt <= 0.30, every other recipe <= 0.40, end guides late, offset_frames 32. Dissolves stay at 8 frames or under.
A scene that is too dark moves mood to dawn and sets guide_strengths.exposure to 1.35.
A scene that is blown out moves mood to night and sets guide_strengths.exposure to 0.72.

Return only JSON with this shape:
{
  "target_scenes": ["s6"],
  "changes": [{"scene": "s6", "field": "edit", "old": "dissolve", "new": "dive-splash"}],
  "transition_type": "dive-splash",
  "speed": null,
  "retime": null,
  "guide_strengths": null,
  "recipe": null,
  "rerender": ["s6"],
  "rationale": "one sentence"
}
"""


class PatchError(ValueError):
    """The model returned a patch this desk will not apply."""


def scene_id(scene: dict) -> str:
    return f"s{int(scene['index'])}"


def scene_label(scene: dict) -> str:
    return f"Scene {int(scene['index']) + 1:02d}"


def identity(quality: str) -> tuple[str, str]:
    name = str(quality)
    if name == "final":
        return MODEL_ID, "640x360"
    if name == "turbo":
        return "ltx-095", "384x224"
    if name == "live":
        return "live", "preview"
    return MODEL_ID, "512x288"


def canonical_transition(name: str | None) -> str | None:
    if name in (None, ""):
        return None
    key = " ".join(str(name).strip().lower().split())
    key = _RECIPE_CANON.get(key, key)
    if key in TRANSITIONS:
        return key
    raise PatchError(f"unknown transition {name}")


def canonical_edit(name: str) -> str:
    try:
        mapped = canonical_transition(name)
    except PatchError:
        mapped = None
    if mapped:
        return mapped
    key = " ".join(str(name).strip().lower().split())
    if key in {"hard cut", "dissolve", "continuous"}:
        return key
    raise PatchError(f"unknown edit {name}")


def resolve_one(item: str, scenes: list[dict]) -> dict | None:
    text = " ".join(str(item).strip().lower().split())
    if text in {"", "auto"}:
        return None
    if text in {"ending", "last", "outro", "finale"}:
        return scenes[-1] if scenes else None
    if text in {"opening", "first", "intro"}:
        return scenes[0] if scenes else None
    match = re.fullmatch(r"s(\d+)", text)
    if match:
        index = int(match.group(1))
        return next((scene for scene in scenes if int(scene["index"]) == index), None)
    match = re.fullmatch(r"scene\s*(\d+)", text)
    if match or text.isdigit():
        number = int(match.group(1) if match else text)
        return next((scene for scene in scenes if int(scene["index"]) == number - 1), None)
    return None


def resolve_scenes(spec: list, scenes: list[dict]) -> list[dict]:
    found: list[dict] = []
    for item in spec:
        scene = resolve_one(str(item), scenes)
        if scene is not None and scene not in found:
            found.append(scene)
    return found


def _blank(**kwargs: Any) -> dict[str, Any]:
    return {
        "target_scenes": list(kwargs.get("target_scenes") or ["auto"]),
        "changes": list(kwargs.get("changes") or []),
        "transition_type": kwargs.get("transition_type"),
        "speed": kwargs.get("speed"),
        "retime": kwargs.get("retime"),
        "guide_strengths": kwargs.get("guide_strengths"),
        "recipe": kwargs.get("recipe"),
        "rerender": list(kwargs.get("rerender") or []),
        "rationale": str(kwargs.get("rationale") or ""),
    }


def validate_patch(raw: Any, scenes: list[dict]) -> dict[str, Any]:
    """Return a cleaned patch or raise ``PatchError``."""
    if not isinstance(raw, dict):
        raise PatchError("patch")
    for key in ("target_scenes", "changes", "rerender", "rationale"):
        if key not in raw:
            raise PatchError(key)
    targets = raw["target_scenes"]
    if not isinstance(targets, list) or not targets or not all(isinstance(item, str) for item in targets):
        raise PatchError("target_scenes")
    if not isinstance(raw["changes"], list) or not isinstance(raw["rerender"], list):
        raise PatchError("changes")
    if not isinstance(raw["rationale"], str):
        raise PatchError("rationale")
    if targets != ["auto"] and not resolve_scenes(targets, scenes):
        raise PatchError("target_scenes")
    transition = raw.get("transition_type")
    if transition not in (None, ""):
        transition = canonical_transition(str(transition))
    changes = []
    for change in raw["changes"]:
        if not isinstance(change, dict) or "field" not in change or "new" not in change or "old" not in change:
            raise PatchError("changes")
        field = str(change["field"])
        if field not in ALLOWED_FIELDS:
            raise PatchError("field")
        new = change["new"]
        if field == "edit":
            new = canonical_edit(str(new))
        if field == "bars":
            new = int(new)
        row = {"field": field, "old": change["old"], "new": new}
        if change.get("scene"):
            row["scene"] = str(change["scene"])
        changes.append(row)
    rerender = [str(item) for item in raw["rerender"]]
    guide = raw.get("guide_strengths")
    if guide is not None and not isinstance(guide, dict):
        raise PatchError("guide_strengths")
    retime = raw.get("retime")
    if retime is not None and not isinstance(retime, dict):
        raise PatchError("retime")
    speed = raw.get("speed")
    if speed is not None:
        speed = str(speed)
    return _blank(
        target_scenes=list(targets),
        changes=changes,
        transition_type=transition,
        speed=speed,
        retime=retime,
        guide_strengths=dict(guide) if isinstance(guide, dict) else None,
        recipe=raw.get("recipe") if raw.get("recipe") in (None, "") or isinstance(raw.get("recipe"), str) else None,
        rerender=rerender,
        rationale=raw["rationale"].strip(),
    )


def _loads_json(text: str) -> Any:
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?", "", body).strip()
        body = re.sub(r"```$", "", body).strip()
    return json.loads(body)


def ground(note: str, scenes: list[dict], features: dict | None) -> str:
    cards = []
    for scene in scenes:
        cards.append(
            {
                "id": scene_id(scene),
                "label": scene_label(scene),
                "beat": scene.get("beat"),
                "action": scene.get("action"),
                "form": scene.get("form"),
                "shot": scene.get("shot"),
                "move": scene.get("move"),
                "edit": scene.get("edit"),
                "mood": scene.get("mood"),
                "bars": scene.get("bars"),
                "start": scene.get("start"),
                "end": scene.get("end"),
            }
        )
    beats = [round(float(beat), 4) for beat in (features or {}).get("beats") or []]
    return json.dumps(
        {
            "note": note,
            "storyboard": cards,
            "beat_grid": beats[:64],
            "tempo": (features or {}).get("tempo"),
            "fps": (features or {}).get("fps"),
            "recipes": list(RECIPES),
        },
        ensure_ascii=True,
    )


def _mentioned_scene(note: str, scenes: list[dict]) -> dict | None:
    match = re.search(r"scene\s*(\d+)", note, re.I)
    if match:
        return resolve_one(f"scene {match.group(1)}", scenes)
    if re.search(r"\b(ending|last|outro|finale)\b", note, re.I):
        return scenes[-1]
    if re.search(r"\b(opening|first scene|intro)\b", note, re.I):
        return scenes[0]
    return None


def _section_level(scene: dict, features: dict | None) -> float:
    if not features:
        return 1.0
    for section in features.get("sections") or []:
        if abs(float(section.get("start", -1)) - float(scene.get("start", -2))) < 0.08:
            return float(section.get("level") or 0.0)
    return 1.0


def _quiet_scene(scenes: list[dict], features: dict | None) -> dict:
    best = scenes[0]
    best_level = 1e9
    for scene in scenes:
        level = _section_level(scene, features)
        if level < best_level:
            best = scene
            best_level = level
    return best


def _splash_action(action: str) -> str:
    text = " ".join(str(action or "").replace(",", " ").split())
    text = re.sub(r"\bchanged$", "", text).strip()
    text = re.sub(r"\bin a big splash$", "", text).strip()
    if not text:
        text = "the form lands"
    return f"{text} in a big splash"


def _change(scene: dict, field: str, new: Any) -> dict:
    return {"scene": scene_id(scene), "field": field, "old": scene.get(field), "new": new}


def _bolt_scene(note: str, scenes: list[dict]) -> dict:
    named = _mentioned_scene(note, scenes)
    if named is not None and not re.search(r"\b(ending|last|outro)\b", note, re.I):
        return named
    for scene in scenes:
        if re.search(r"bolt|strike|lightning", str(scene.get("action") or ""), re.I):
            return scene
    for scene in scenes:
        if scene.get("beat") == "climax":
            return scene
    return scenes[-1]


def rules_interpret(note: str, scenes: list[dict], features: dict | None = None) -> dict[str, Any]:
    """Deterministic reading of a note. Used when no local model is up."""
    text = " ".join(str(note or "").lower().split())
    if not text or not scenes:
        return _blank(rationale="The note was empty.")
    if re.search(r"splash|plop", text):
        scene = _mentioned_scene(text, scenes) or scenes[-1]
        edit = "dive-splash"
        action = _splash_action(str(scene.get("action") or ""))
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[_change(scene, "edit", edit), _change(scene, "action", action)],
            transition_type="dive-splash",
            rerender=[scene_id(scene)],
            rationale="The landing should hit as a dive-splash. The dissolve on that card becomes the splash, and the action says so.",
        )
    if re.search(r"too dark|too dim|muddy|murky|brighter|lift the|lighten", text):
        scene = _mentioned_scene(text, scenes) or _quiet_scene(scenes, features)
        mood = "dawn" if scene.get("mood") != "dawn" else "neon"
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[_change(scene, "mood", mood)],
            guide_strengths={"exposure": 1.35},
            rerender=[scene_id(scene)],
            rationale=f"{scene_label(scene)} is {scene.get('mood')}. The note lifts it to {mood} and raises exposure.",
        )
    if re.search(r"too bright|blown|blowout|hot highlights", text):
        scene = _mentioned_scene(text, scenes) or scenes[0]
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[_change(scene, "mood", "night")],
            guide_strengths={"exposure": 0.72},
            rerender=[scene_id(scene)],
            rationale=f"{scene_label(scene)} is hot. Night light and a lower exposure pull it back.",
        )
    if re.search(r"slow-motion|slow mo|slow-mo|anticlimax|too slow", text):
        scene = _mentioned_scene(text, scenes) or next((item for item in scenes if item.get("beat") == "climax"), scenes[-1])
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[],
            speed="trim",
            retime={"mode": "snap-peak", "scene": scene_id(scene)},
            rerender=[scene_id(scene)],
            rationale=f"{scene_label(scene)} was easing into the hit. The approach trims onto the beat, and any slow-mo sits after the impact.",
        )
    if re.search(r"cap the dissolve|long dissolve|double exposure|ghost", text):
        scene = _mentioned_scene(text, scenes) or next(
            (item for item in scenes if item.get("edit") in {"swim", "droplet-gather", "dissolve", "pour-harden"}),
            scenes[-1],
        )
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[_change(scene, "edit", "pour-harden")],
            transition_type="pour-harden",
            rerender=[scene_id(scene)],
            rationale=f"{scene_label(scene)} dissolve caps at 8 frames. The regather is a zoom from a point, not a long ghost.",
        )
    if re.search(r"guide is hot|cap (?:the |it )?(?:guide|mid|bolt)", text) or ("guide" in text and "cap" in text):
        scene = _mentioned_scene(text, scenes) or _bolt_scene(text, scenes)
        limit = 0.30 if "0.30" in text or scene.get("edit") == "bolt-strike" or "bolt" in text else 0.40
        key = "mid" if "mid" in text else "guide"
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[],
            guide_strengths={key: limit},
            rerender=[scene_id(scene)],
            rationale=f"{scene_label(scene)} {key} caps at {limit:.2f}. End guides stay late.",
        )
    if re.search(r"\b(bolt|lightning)\b", text) or "strike" in text or "on the beat" in text:
        scene = _bolt_scene(text, scenes)
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[_change(scene, "edit", "bolt-strike")],
            transition_type="bolt-strike hold",
            speed="hold",
            retime={"mode": "snap-peak", "scene": scene_id(scene)},
            rerender=[scene_id(scene)],
            rationale=f"The strike on {scene_label(scene)} locks to the nearest beat, and the cut becomes a bolt-strike.",
        )
    if "swim" in text:
        scene = _mentioned_scene(text, scenes) or next((item for item in scenes if item.get("beat") == "release"), scenes[-1])
        return _blank(
            target_scenes=[scene_id(scene)],
            changes=[_change(scene, "edit", "swim")],
            transition_type="swim hold",
            speed="hold",
            rerender=[scene_id(scene)],
            rationale=f"{scene_label(scene)} holds and swims instead of cutting away.",
        )
    for recipe in RECIPES:
        if recipe in text:
            scene = _mentioned_scene(text, scenes) or scenes[-1]
            edit = canonical_transition(recipe)
            return _blank(
                target_scenes=[scene_id(scene)],
                changes=[_change(scene, "edit", edit)],
                transition_type=recipe,
                rerender=[scene_id(scene)],
                rationale=f"{scene_label(scene)} takes the {recipe} recipe.",
            )
    return _blank(rationale="No scene field matched that note. Name a scene, a recipe, or what looked wrong.")


def retime_for_scene(scene: dict, features: dict | None, mode: str = "snap-peak") -> dict[str, Any]:
    """Anchors in seconds. The peak of the scene snaps to the nearest beat."""
    features = features or {}
    fps = float(features.get("fps") or 24.0) or 24.0
    start = float(scene.get("start") or 0.0)
    end = float(scene.get("end") or start + float(scene.get("seconds") or 1.0))
    duration = max(0.05, end - start)
    src = duration * 0.55
    beats = [float(beat) for beat in features.get("beats") or []]
    inside = [beat for beat in beats if start - 1e-4 <= beat <= end + 1e-4]
    if inside:
        nearest = min(inside, key=lambda beat: abs((beat - start) - src))
        dst = approach_dst(src, min(duration, max(0.0, nearest - start)))
    else:
        bpm = float(features.get("tempo") or 120.0) or 120.0
        snapped = snap(src * fps, bpm=bpm, fps=fps)
        dst = approach_dst(src, min(duration, max(0.0, snapped / fps)))
    return {
        "mode": mode,
        "speed": "trim",
        "anchors_s": [
            [0.0, 0.0],
            [round(src, 4), round(dst, 4)],
            [round(duration, 4), round(duration, 4)],
        ],
    }


def _targets(patch: dict, scenes: list[dict]) -> list[dict]:
    if patch.get("target_scenes") == ["auto"]:
        ids = [change.get("scene") for change in patch.get("changes") or [] if change.get("scene")]
        found = resolve_scenes([str(item) for item in ids], scenes)
        if found:
            return found
        return scenes[:1]
    return resolve_scenes(list(patch.get("target_scenes") or []), scenes)


def apply_patch(scenes: list[dict], patch: dict, features: dict | None = None) -> list[dict]:
    """Copy the cards and write the patch. Guides are rebuilt."""
    out = copy.deepcopy(scenes)
    by_id = {scene_id(scene): scene for scene in out}
    targets = _targets(patch, out)
    for change in patch.get("changes") or []:
        field = change.get("field")
        if field not in ALLOWED_FIELDS:
            continue
        sid = change.get("scene")
        if sid and sid in by_id:
            chosen = [by_id[sid]]
        elif len(targets) == 1:
            chosen = targets
        else:
            continue
        for scene in chosen:
            value = change.get("new")
            if field == "edit":
                value = canonical_edit(str(value))
            if field == "bars":
                value = max(1, int(value))
                scene["hold"] = round(value * float(scene.get("bar_seconds") or 2.0), 4)
            if field == "action":
                value = " ".join(str(value).split())[:180]
            scene[field] = value
            scene["edited"] = True
    if patch.get("transition_type"):
        edit = canonical_transition(str(patch["transition_type"]))
        for scene in targets:
            scene["edit"] = edit
            scene["edited"] = True
    if isinstance(patch.get("guide_strengths"), dict):
        for scene in targets:
            scene["guide_strengths"] = {key: value for key, value in patch["guide_strengths"].items()}
            scene["edited"] = True
    if patch.get("retime") or patch.get("speed"):
        mode = "snap-peak"
        if isinstance(patch.get("retime"), dict) and patch["retime"].get("mode"):
            mode = str(patch["retime"]["mode"])
        for scene in targets:
            built = retime_for_scene(scene, features, mode=mode)
            if patch.get("speed"):
                built["speed"] = str(patch["speed"])
            scene["retime"] = built
            scene["edited"] = True
    for scene in targets:
        stamp_scene(scene)
    for scene in out:
        scene["guide"] = _guide(scene)
    return out


def human_diff(before: list[dict], after: list[dict]) -> list[dict]:
    rows = []
    for old, new in zip(before, after):
        label = scene_label(old)
        sid = scene_id(old)
        for field in ("action", "form", "shot", "move", "edit", "mood", "bars", "hold"):
            if old.get(field) != new.get(field):
                rows.append(
                    {
                        "scene": sid,
                        "label": label,
                        "field": field,
                        "old": old.get(field),
                        "new": new.get(field),
                    }
                )
        old_exposure = (old.get("guide_strengths") or {}).get("exposure", 1)
        new_exposure = (new.get("guide_strengths") or {}).get("exposure", old_exposure)
        if new.get("guide_strengths") and old_exposure != new_exposure:
            rows.append(
                {
                    "scene": sid,
                    "label": label,
                    "field": "exposure",
                    "old": old_exposure,
                    "new": new_exposure,
                }
            )
        if new.get("retime") and old.get("retime") != new.get("retime"):
            speed = str((new.get("retime") or {}).get("speed") or "")
            rows.append(
                {
                    "scene": sid,
                    "label": label,
                    "field": "retime",
                    "old": "free" if not old.get("retime") else str((old.get("retime") or {}).get("speed") or "free"),
                    "new": "trim into the hit" if speed == "trim" else "snap onto the beat",
                }
            )
        for key in ("guide", "mid", "bolt"):
            old_strengths = old.get("guide_strengths") or {}
            new_strengths = new.get("guide_strengths") or {}
            if new_strengths.get(key) is not None and old_strengths.get(key) != new_strengths.get(key):
                rows.append(
                    {
                        "scene": sid,
                        "label": label,
                        "field": key,
                        "old": old_strengths.get(key, "unset"),
                        "new": new_strengths.get(key),
                    }
                )
        if old.get("fade_frames") not in (None, new.get("fade_frames")) and int(old.get("fade_frames") or 0) > int(
            new.get("fade_frames") or 0
        ):
            rows.append(
                {
                    "scene": sid,
                    "label": label,
                    "field": "fade",
                    "old": f"{old.get('fade_frames')}f",
                    "new": f"{new.get('fade_frames')}f",
                }
            )
    return rows


def diff_text(rows: list[dict], rationale: str, plan: dict | None = None) -> str:
    lines = [f"{row['label']} · {row['field']}: {row['old']} → {row['new']}" for row in rows]
    if rationale:
        lines.append(rationale)
    if plan:
        lines.append(plan_sentence(plan))
    return "\n".join(line for line in lines if line)


def plan_sentence(plan: dict, *, quality: str = "draft", seed: int = DEFAULT_SEED) -> str:
    misses = list(plan.get("misses") or [])
    hits = list(plan.get("hits") or [])
    if str(quality) == "live":
        return f"Live is the browser picture. Edits land on the next frame. Seed {seed} is what a recording carries into Turbo, Draft, and Final."
    if str(quality) == "turbo":
        if not misses:
            return f"Turbo reuses every segment at seed {seed}. The animatic is already cached."
        listed = ", ".join(misses)
        return (
            f"Turbo re-renders {listed} at 384×224, 4 steps, LTX 0.9.5. Seed {seed}. "
            "Same guides and the same retime in seconds as Final."
        )
    if str(quality) == "final":
        return f"Final renders every segment at 640×360. Seed {seed}. Retime stays in seconds and lands on the new frame grid."
    if not misses:
        return f"These segments are already cached at seed {seed}."
    listed = ", ".join(misses)
    if hits:
        return f"Re-render {listed}. {len(hits)} segments keep seed {seed}."
    return f"Re-render {listed}."


def interpret_note(
    note: str,
    scenes: list[dict],
    features: dict | None = None,
    llm: Callable[[str, str], str] | None = None,
    *,
    try_local: bool = False,
    lessons: list[dict] | None = None,
    allow_cloud: bool = False,
) -> dict[str, Any]:
    """Map a note to a validated patch and a human diff.

    ``llm`` is a callable ``(system, user) -> text`` used by tests. A saved
    lesson whose note matches is the local default and wins first. With
    ``try_local``, a reachable Ollama (or the OpenAI-compatible backend)
    gets the next chance. A bad payload falls back to the rules.
    """
    source = "rules"
    model = None
    patch = None
    learned = saved_patch(note, scenes, list(lessons or []))
    if learned:
        try:
            candidate = validate_patch(learned, scenes)
        except PatchError:
            candidate = None
        if candidate is not None and human_diff(scenes, apply_patch(scenes, candidate, features)):
            patch = candidate
            source = "lesson"
    user = ground(note, scenes, features)
    raw = None
    if patch is None and llm is not None:
        try:
            raw = llm(SYSTEM_PROMPT, user)
        except Exception:
            raw = None
        model = "mock"
        source = "llm"
    elif patch is None and try_local:
        from xenoform.llm import chat, model_name, reachable

        if reachable():
            raw = chat(SYSTEM_PROMPT, user, PATCH_SCHEMA, allow_cloud=allow_cloud)
            model = model_name()
            source = "llm"
    if raw:
        try:
            patch = validate_patch(_loads_json(str(raw)), scenes)
        except (PatchError, json.JSONDecodeError, TypeError, ValueError):
            patch = None
    if patch is not None:
        preview = apply_patch(scenes, patch, features)
        if not human_diff(scenes, preview):
            patch = None
    if patch is None:
        patch = rules_interpret(note, scenes, features)
        if source == "llm":
            source = "rules-fallback"
            model = None
    after = apply_patch(scenes, patch, features)
    rows = human_diff(scenes, after)
    if not patch.get("rerender"):
        patch["rerender"] = [row["scene"] for row in rows if row["scene"] not in patch["rerender"]]
        # unique, stable
        seen: list[str] = []
        for sid in patch["rerender"]:
            if sid not in seen:
                seen.append(sid)
        patch["rerender"] = seen
    return {
        "patch": patch,
        "diff": rows,
        "text": diff_text(rows, patch.get("rationale") or ""),
        "source": source,
        "model": model,
        "rationale": patch.get("rationale") or "",
        "rerender": list(patch.get("rerender") or []),
        "scenes": after,
    }


def card_hash(scene: dict) -> str:
    payload = {}
    for key in HASH_FIELDS:
        value = scene.get(key)
        if value not in (None, "", [], {}):
            payload[key] = value
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def segment_key(scene: dict, seed: int, model: str, resolution: str) -> str:
    return f"{card_hash(scene)}:{int(seed)}:{model}:{resolution}"


def classify(
    before: list[dict],
    after: list[dict],
    cache: dict[str, dict],
    seed: int,
    model: str,
    resolution: str,
) -> dict[str, list[str]]:
    """Hits keep their cache key. Misses changed, or were never stored at this identity."""
    changed: list[str] = []
    hits: list[str] = []
    misses: list[str] = []
    for old, new in zip(before, after):
        sid = scene_id(new)
        if segment_key(old, seed, model, resolution) != segment_key(new, seed, model, resolution):
            changed.append(sid)
        cached = cache.get(sid) or {}
        if cached.get("key") == segment_key(new, seed, model, resolution):
            hits.append(sid)
        else:
            misses.append(sid)
    for new in after[len(before) :]:
        sid = scene_id(new)
        changed.append(sid)
        misses.append(sid)
    return {"changed": changed, "hits": hits, "misses": misses, "rerender": misses}


def warm_cache(
    scenes: list[dict],
    video: str = "",
    *,
    seed: int = DEFAULT_SEED,
    model: str = MODEL_ID,
    resolution: str = "512x288",
) -> dict[str, dict]:
    cache = {}
    for scene in scenes:
        sid = scene_id(scene)
        cache[sid] = {
            "key": segment_key(scene, seed, model, resolution),
            "path": video,
            "retime": scene.get("retime"),
        }
    return cache


def stamp_retime(features: dict | None, scenes: list[dict]) -> dict | None:
    """Copy each scene's second-based retime onto the frames it owns.

    Also stores the anchor list at the feature fps, so a later final pass can
    re-expand the same seconds at the new rate.
    """
    if not features:
        return None
    fps = float(features.get("fps") or 24.0) or 24.0
    frames = [dict(frame) for frame in features.get("frames") or []]
    out = dict(features)
    out["frames"] = frames
    for scene in scenes:
        retime = scene.get("retime")
        if not retime:
            continue
        start = float(scene.get("start") or 0.0)
        end = float(scene.get("end") or start)
        frame_anchors = anchors_at_fps(retime.get("anchors_s") or [], fps)
        last = scene is scenes[-1]
        for frame in frames:
            t = float(frame.get("t") or 0.0)
            if start <= t < end or (last and t == end):
                frame["retime"] = {
                    "anchors_s": retime.get("anchors_s") or [],
                    "anchors": frame_anchors,
                    "mode": retime.get("mode"),
                    "speed": retime.get("speed"),
                    "fps": fps,
                }
                if scene.get("guide_strengths"):
                    frame["guide_strengths"] = dict(scene["guide_strengths"])
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_version(
    *,
    note: str,
    patch: dict | None,
    scenes: list[dict],
    renders: dict[str, str],
    parent: str | None,
    seed: int,
    quality: str,
    video: str,
    plan: dict | None = None,
) -> dict[str, Any]:
    vid = "draft" if note == "Draft" and parent is None else uuid.uuid4().hex[:8]
    label = "Draft" if vid == "draft" else " ".join(note.split())[:72]
    return {
        "id": vid,
        "parent": parent,
        "note": note,
        "label": label,
        "patch": patch,
        "scenes": copy.deepcopy(scenes),
        "renders": dict(renders),
        "retime": {scene_id(scene): scene.get("retime") for scene in scenes if scene.get("retime")},
        "seed": int(seed),
        "quality": quality,
        "video": video,
        "plan": plan or {},
        "created": _now(),
    }


def new_notebook(scenes: list[dict], video: str = "") -> dict[str, Any]:
    cache = warm_cache(scenes, video)
    draft = make_version(
        note="Draft",
        patch=None,
        scenes=scenes,
        renders={scene_id(scene): video for scene in scenes},
        parent=None,
        seed=DEFAULT_SEED,
        quality="draft",
        video=video,
    )
    return {"cache": cache, "versions": [draft], "current": draft["id"], "seed": DEFAULT_SEED}


def version_summary(version: dict) -> dict[str, Any]:
    patch = version.get("patch") if isinstance(version.get("patch"), dict) else {}
    return {
        "id": version["id"],
        "parent": version.get("parent"),
        "note": version.get("note"),
        "label": version.get("label"),
        "created": version.get("created"),
        "video": version.get("video"),
        "quality": version.get("quality"),
        "seed": version.get("seed"),
        "rerender": list((version.get("plan") or {}).get("misses") or patch.get("rerender") or []),
    }


def apply_to_notebook(
    book: dict,
    note: str,
    scenes: list[dict],
    patch: dict,
    features: dict | None,
    render_one: Callable[[dict, int, str, Path], str],
    out_dir: Path,
    *,
    quality: str = "draft",
    video: str = "",
    release: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Unload the LLM, render cache misses, store a version."""
    if release is None:
        from xenoform.llm import release_llm

        release_llm()
    else:
        release()
    cleaned = validate_patch(patch, scenes)
    after = apply_patch(scenes, cleaned, features)
    model, resolution = identity(quality)
    seed = int(book.get("seed") or DEFAULT_SEED)
    plan = classify(scenes, after, book.get("cache") or {}, seed, model, resolution)
    # The note names the segments it cares about. A warm cache rerenders those
    # misses. A cold cache also fills anything never stored. Final changes the
    # resolution, so every key misses.
    renders: dict[str, str] = {}
    out_dir.mkdir(parents=True, exist_ok=True)
    for scene in after:
        sid = scene_id(scene)
        if sid in plan["hits"]:
            renders[sid] = (book["cache"].get(sid) or {}).get("path") or video
            continue
        path = render_one(scene, seed, resolution, out_dir)
        book.setdefault("cache", {})[sid] = {
            "key": segment_key(scene, seed, model, resolution),
            "path": path,
            "retime": scene.get("retime"),
        }
        renders[sid] = path
    parent = book.get("current")
    version = make_version(
        note=note or cleaned.get("rationale") or "Note",
        patch=cleaned,
        scenes=after,
        renders=renders,
        parent=parent,
        seed=seed,
        quality=quality,
        video=video or (book["versions"][-1]["video"] if book.get("versions") else ""),
        plan=plan,
    )
    book.setdefault("versions", []).append(version)
    book["current"] = version["id"]
    stamped = stamp_retime(features, after)
    return {
        "version": version,
        "scenes": after,
        "plan": plan,
        "cache_line": plan_sentence(plan, quality=quality, seed=seed),
        "stamped_frames": sum(1 for frame in (stamped or {}).get("frames") or [] if frame.get("retime")),
        "features": stamped,
    }


def revert_notebook(book: dict, version_id: str, *, video: str = "") -> dict[str, Any]:
    found = next((version for version in book.get("versions") or [] if version["id"] == version_id), None)
    if found is None:
        raise KeyError(version_id)
    scenes = copy.deepcopy(found["scenes"])
    quality = str(found.get("quality") or "draft")
    model, resolution = identity(quality)
    seed = int(book.get("seed") or DEFAULT_SEED)
    cache = warm_cache(scenes, video or found.get("video") or "", seed=seed, model=model, resolution=resolution)
    for sid, path in (found.get("renders") or {}).items():
        if sid in cache and path:
            cache[sid]["path"] = path
            cache[sid]["retime"] = (found.get("retime") or {}).get(sid)
    book["cache"] = cache
    version = make_version(
        note=f"Revert to {found.get('label') or version_id}",
        patch={"revert": version_id, "target_scenes": ["auto"], "changes": [], "rerender": [], "rationale": "revert"},
        scenes=scenes,
        renders=dict(found.get("renders") or {}),
        parent=book.get("current"),
        seed=seed,
        quality=quality,
        video=found.get("video") or video,
        plan={"hits": list(cache), "misses": [], "changed": [], "rerender": []},
    )
    book.setdefault("versions", []).append(version)
    book["current"] = version["id"]
    return {"version": version, "scenes": scenes}


def render_manifest(scene: dict, seed: int, resolution: str, out_dir: Path) -> str:
    """Write the segment plan. The beauty pass reads this when it reruns the card."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"s{int(scene['index'])}.json"
    payload = {
        "segment": scene_id(scene),
        "seed": int(seed),
        "model": MODEL_ID,
        "resolution": resolution,
        "card_hash": card_hash(scene),
        "action": scene.get("action"),
        "edit": scene.get("edit"),
        "mood": scene.get("mood"),
        "guide": scene.get("guide"),
        "guide_strengths": scene.get("guide_strengths"),
        "retime": scene.get("retime"),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def harding_flash_rate(frames, fps: float) -> float:
    """Worst count of opposing flashes in any 1 second. Guideline is 3."""
    if frames is None or len(frames) < 2:
        return 0.0
    import numpy as np

    luma = frames.astype(np.float64).mean(axis=(1, 2, 3)) / 255.0
    lin = np.clip((luma - 16 / 255) / (219 / 255), 0, 1) ** 2.4
    cd = 200.0 * lin
    events = []
    prev = 0
    for index in range(1, len(cd)):
        delta = float(cd[index] - cd[index - 1])
        if abs(delta) < 20 or min(float(cd[index]), float(cd[index - 1])) >= 160:
            continue
        sign = 1 if delta > 0 else -1
        if prev and sign == -prev:
            events.append(index)
        prev = sign
    if not events:
        return 0.0
    window = max(1, int(round(float(fps) or 24)))
    worst = 1
    for frame in events:
        count = sum(1 for other in events if 0 <= frame - other < window)
        worst = max(worst, count)
    return float(worst)


def _board_notes(scenes: list[dict], features: dict | None) -> list[dict]:
    if not scenes:
        return []
    notes = []
    last = scenes[-1]
    if last.get("edit") in {"dissolve", "pour-harden", "continuous", "grow-out"} and re.search(
        r"fall|land|earth|return|end", str(last.get("action") or ""), re.I
    ):
        notes.append(
            {
                "note": "the ending plops, make it a big splash",
                "reason": "The last cut is a soft dissolve on a landing.",
                "score": 0.86,
                "scene": scene_id(last),
            }
        )
    cold = []
    for scene in scenes:
        if scene.get("mood") in {"cold", "night", "void"}:
            cold.append((scene, _section_level(scene, features)))
    if cold:
        scene, level = min(cold, key=lambda row: row[1])
        loudest = max((item[1] for item in cold), default=1.0)
        if level <= loudest * 0.92:
            notes.append(
                {
                    "note": f"scene {int(scene['index']) + 1} too dark",
                    "reason": f"{scene_label(scene)} is {scene.get('mood')} and sits in a quieter span.",
                    "score": 0.64,
                    "scene": scene_id(scene),
                }
            )
    for scene in scenes:
        if re.search(r"bolt|strike|lightning", str(scene.get("action") or ""), re.I) and scene.get("edit") not in {
            "bolt-strike",
            "snap",
            "hard cut",
        }:
            notes.append(
                {
                    "note": "bolt should strike on the beat",
                    "reason": f"{scene_label(scene)} says strike and the cut is not on the grid.",
                    "score": 0.78,
                    "scene": scene_id(scene),
                }
            )
            break
    return notes


def critic_notes(
    frames=None,
    features: dict | None = None,
    scenes: list[dict] | None = None,
    fps: float = 24,
    vlm: Callable[[], str | None] | None = None,
    lessons: list[dict] | None = None,
    looks: list[dict] | None = None,
) -> dict[str, Any]:
    """Ranked notes from the board plus frame heuristics.

    Frame checks reuse beatlock's motion peak, cut, and freeze detectors, and
    a Harding-style flash count (more than 3 opposing flashes in a second).
    ``vlm`` may return one short qualitative line.
    """
    board = list(scenes or [])
    suggestions = _board_notes(board, features)
    suggestions.extend(builtin_flags(board, looks))
    suggestions.extend(saved_flags(board, list(lessons or [])))
    rate = float(fps or (features or {}).get("fps") or 24)
    if frames is not None and len(frames) > 1:
        events = detect(frames)
        frozen = events["frozen"]
        if len(frozen) >= max(4, int(0.45 * len(frames))):
            suggestions.append(
                {
                    "note": "a stretch of the draft is frozen, give it a breath of motion",
                    "reason": f"{len(frozen)} sampled frames barely move. Stills posing as motion read dead; a hit wants dive-splash or droplet-burst.",
                    "score": 0.9,
                    "scene": "auto",
                }
            )
        beats = [float(beat) for beat in (features or {}).get("beats") or []]
        beat_at = [int(round(beat * rate)) for beat in beats]
        # Sampled frames are every Nth source frame when the caller downsamples.
        # Compare in sample index when the beat grid was not rescaled; skip the
        # beat test when we have no beats.
        off_cuts = 0
        for cut in events["cuts"]:
            if beat_at and min(abs(cut - beat) for beat in beat_at) > max(2, int(rate * 0.12)):
                off_cuts += 1
        if off_cuts:
            suggestions.append(
                {
                    "note": "a hard cut misses the beat",
                    "reason": f"{off_cuts} cut{'s' if off_cuts != 1 else ''} land off the grid.",
                    "score": 0.74,
                    "scene": "auto",
                }
            )
        if beat_at:
            peak = int(events["peak"])
            if min(abs(peak - beat) for beat in beat_at) > max(2, int(rate * 0.15)):
                suggestions.append(
                    {
                        "note": "the hit lands off the beat",
                        "reason": "The motion peak is away from the beat grid.",
                        "score": 0.7,
                        "scene": "auto",
                    }
                )
        import numpy as np

        mean = float(np.asarray(frames).mean())
        if mean > 220:
            suggestions.append(
                {
                    "note": "the picture is blown out, pull the exposure down",
                    "reason": f"Mean sample level is {mean:.0f}.",
                    "score": 0.88,
                    "scene": "auto",
                }
            )
        elif mean < 18:
            suggestions.append(
                {
                    "note": "the picture is too dark",
                    "reason": f"Mean sample level is {mean:.0f}.",
                    "score": 0.84,
                    "scene": "auto",
                }
            )
        flashes = harding_flash_rate(frames, rate)
        if flashes > 3:
            suggestions.append(
                {
                    "note": "ease the flashes, more than three a second",
                    "reason": f"Harding-style check sees {flashes:.0f} opposing flashes in one second. The guideline is 3.",
                    "score": 0.92,
                    "scene": "auto",
                }
            )
    qualitative = None
    if callable(vlm):
        try:
            qualitative = vlm()
        except Exception:
            qualitative = None
        if qualitative:
            qualitative = " ".join(str(qualitative).split())[:180]
            suggestions.append(
                {
                    "note": qualitative,
                    "reason": "Local vision model.",
                    "score": 0.6,
                    "scene": "auto",
                }
            )
    suggestions.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    deduped = []
    seen = set()
    for item in suggestions:
        if item["note"] in seen:
            continue
        seen.add(item["note"])
        deduped.append(item)
    return {"notes": deduped[:5], "qualitative": qualitative}
