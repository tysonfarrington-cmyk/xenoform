"""One-click review of the storyboard and, when a picture exists, the frames.

Every check is a rule the desk can explain in a sentence. Fixes split in two:
the board can absorb a retime, a trim, a dissolve cap, an accent, a flash
gate, or a grade with no GPU. A new edit, form, or camera move needs a new
picture, and only those scenes are named for the current tier.

No language model is required. A reachable local model may add one extra line.
"""

from __future__ import annotations

import copy
import os
import subprocess
from typing import Any

import numpy as np

from xenoform.beatlock import detect
from xenoform.lessons import (
    BOLT_GUIDE_CAP,
    DISSOLVE_CAP,
    IMPACT_EDITS,
    SOFT_DISSOLVES,
    approach_dst,
    cap_for,
    catalog,
    is_impact,
    look_allowed,
)
from xenoform.lessons import _slow as scene_is_slow
from xenoform.notes import harding_flash_rate

MORPHS = SOFT_DISSOLVES | {"continuous", "grow-out"}
HARD_CUTS = {"hard cut", "snap"}
RHYTHM_MIN = 3.5
RHYTHM_MAX = 6.5
HOOK_WINDOW = 20.0

# Lessons the audit watches. A quiet board does not reprint the ones that are
# already satisfied.
_WATCHED = tuple(item["id"] for item in catalog())


def _label(scene: dict) -> str:
    return f"Scene {int(scene.get('index') or 0) + 1:02d}"


def _sid(scene: dict) -> str:
    return f"s{int(scene.get('index') or 0)}"


def _beats(features: dict | None) -> list[float]:
    return [float(beat) for beat in (features or {}).get("beats") or []]


def _nearest(moment: float, beats: list[float], window: float = 0.35) -> float | None:
    if not beats:
        return None
    beat = min(beats, key=lambda item: abs(item - moment))
    if abs(beat - moment) > window or abs(beat - moment) < 0.04:
        return None
    return round(float(beat), 4)


def _fade_of(scene: dict) -> int:
    edit = str(scene.get("edit") or "")
    raw = scene.get("fade_frames")
    if raw is None:
        from xenoform.lessons import fade_frames

        return int(fade_frames(edit))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _finding(
    *,
    check: str,
    scene: dict | None,
    kind: str,
    plain: str,
    before: str,
    after: str,
    op: dict | None,
    lesson_id: str = "",
    rank: int = 50,
) -> dict[str, Any]:
    index = int(scene.get("index")) if scene else None
    return {
        "id": f"{check}-{_sid(scene) if scene else 'board'}",
        "check": check,
        "lesson_id": lesson_id,
        "scene": _sid(scene) if scene else "board",
        "label": _label(scene) if scene else "Board",
        "kind": kind,
        "plain": plain,
        "before": before,
        "after": after,
        "op": op or {},
        "rank": int(rank),
    }


def _dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def _fades(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        edit = str(scene.get("edit") or "")
        if edit not in SOFT_DISSOLVES:
            continue
        fade = _fade_of(scene)
        if fade <= DISSOLVE_CAP:
            continue
        rows.append(
            _finding(
                check="ghosting-dissolve",
                scene=scene,
                kind="cpu",
                lesson_id="dissolve-cap",
                plain=f"{_label(scene)} dissolves for {fade} frames. Long dissolves ghost, so this one comes down to {DISSOLVE_CAP}.",
                before=f"{fade}-frame {edit}",
                after=f"{DISSOLVE_CAP}-frame {edit}",
                op={"op": "fade", "index": int(scene["index"]), "value": DISSOLVE_CAP},
            )
        )
    return rows


def _guides(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        strengths = dict(scene.get("guide_strengths") or {})
        edit = str(scene.get("edit") or "")
        hot = []
        for key in ("guide", "mid", "bolt"):
            if key not in strengths:
                continue
            try:
                value = float(strengths[key])
            except (TypeError, ValueError):
                continue
            limit = cap_for(edit, key)
            if value > limit + 1e-6:
                hot.append((key, value, limit))
        both = 0
        for key in ("guide", "bolt"):
            try:
                if float(strengths.get(key) or 0) > 0.2:
                    both += 1
            except (TypeError, ValueError):
                continue
        if both >= 2:
            rows.append(
                _finding(
                    check="stacked-accents",
                    scene=scene,
                    kind="cpu",
                    lesson_id="bolt-guide-cap",
                    plain=f"{_label(scene)} stacks a bolt and a guide on the same hit. The bolt stays, capped, and the extra guide comes off.",
                    before="bolt and guide together",
                    after=f"bolt at {BOLT_GUIDE_CAP:.2f}, guide off",
                    op={"op": "unstick", "index": int(scene["index"])},
                )
            )
            continue
        if not hot:
            continue
        key, value, limit = hot[0]
        lesson = "bolt-guide-cap" if limit <= BOLT_GUIDE_CAP + 1e-6 else "mid-guide-cap"
        rows.append(
            _finding(
                check="guide-cap",
                scene=scene,
                kind="cpu",
                lesson_id=lesson,
                plain=f"{_label(scene)} {key} is {value:.2f}. The cap is {limit:.2f}, and the end of the guide sits late.",
                before=f"{key} {value:.2f}",
                after=f"{key} {limit:.2f}",
                op={"op": "guides", "index": int(scene["index"])},
            )
        )
    return rows


def _slow_hits(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        if not (is_impact(scene) and scene_is_slow(scene)):
            continue
        rows.append(
            _finding(
                check="slow-into-impact",
                scene=scene,
                kind="cpu",
                lesson_id="slow-into-impact",
                plain=f"{_label(scene)} eases into the hit. The approach speeds up, and any slow-mo waits until after the impact.",
                before="slow into the hit",
                after="trim into the hit",
                op={"op": "trim-impact", "index": int(scene["index"])},
            )
        )
    return rows


def _hard_inside_morph(scenes: list[dict]) -> list[dict]:
    rows = []
    for previous, scene in zip(scenes, scenes[1:]):
        edit = str(scene.get("edit") or "")
        if edit not in HARD_CUTS:
            continue
        if str(previous.get("edit") or "") not in MORPHS and edit != "hard cut":
            continue
        if str(previous.get("edit") or "") not in MORPHS:
            continue
        if str(scene.get("conditioning") or "") == "first-frame" or previous.get("signature"):
            continue
        rows.append(
            _finding(
                check="hard-cut-in-morph",
                scene=scene,
                kind="rerender",
                plain=f"{_label(scene)} cuts hard while {_label(previous)} is still morphing. The join becomes a ribbon.",
                before=edit,
                after="ribbon",
                op={"op": "edit", "index": int(scene["index"]), "value": "ribbon"},
            )
        )
    return rows


def _frozen_cards(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        edit = str(scene.get("edit") or "")
        if scene.get("beat") == "climax" and scene.get("move") == "hold" and edit in MORPHS:
            rows.append(
                _finding(
                    check="still-as-motion",
                    scene=scene,
                    kind="rerender",
                    lesson_id="freeze-fluid",
                    plain=f"{_label(scene)} holds through the climax. A still reads as a dead hit, so the edit becomes a dive-splash.",
                    before=f"hold, {edit}",
                    after="dive-splash",
                    op={"op": "edit", "index": int(scene["index"]), "value": "dive-splash"},
                )
            )
    return rows


def _loops(scenes: list[dict], forms: list[str], motif: str) -> list[dict]:
    rows = []
    pool = [form for form in forms if form] or ["sphere", "rocket", "bulb"]
    for previous, scene in zip(scenes, scenes[1:]):
        form = str(scene.get("form") or "")
        if not form or form != previous.get("form") or form == motif:
            continue
        replacement = next((item for item in pool if item != form), pool[0] if pool[0] != form else "sphere")
        if replacement == form:
            continue
        rows.append(
            _finding(
                check="loop",
                scene=scene,
                kind="rerender",
                plain=f"{_label(scene)} repeats {form} right after {_label(previous)}. The second one becomes {replacement}.",
                before=form,
                after=replacement,
                op={"op": "form", "index": int(scene["index"]), "value": replacement},
            )
        )
    return rows


_STILL_VERBS = {"hold", "holds", "waits", "wait", "sits", "sit", "stands", "stand"}


def _is_morph(scene: dict) -> bool:
    from xenoform.storyboard import MORPH_EDITS

    if scene.get("signature"):
        return True
    return str(scene.get("edit") or "") in MORPH_EDITS


def _scene_seconds(scene: dict) -> float:
    return max(0.0, float(scene.get("end") or 0) - float(scene.get("start") or 0))


def _low_motion(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        verb = str(scene.get("verb") or "").strip().lower()
        held = str(scene.get("move") or "") == "hold" or verb in _STILL_VERBS
        if not held:
            continue
        move = "push in" if scene.get("beat") == "climax" or str(scene.get("shot") or "") in {"close", "macro"} else "follow"
        verb_out = ""
        if verb in _STILL_VERBS:
            verb_out = "hits" if scene.get("beat") == "climax" else "moves"
        after = f"camera {move}" + (f", verb {verb_out}" if verb_out else "")
        rows.append(
            _finding(
                check="low-motion",
                scene=scene,
                kind="rerender",
                lesson_id="shots-not-morphs",
                plain=f"{_label(scene)} barely moves. An action shot needs a camera move, so this one goes to {move}.",
                before=str(scene.get("move") or "hold"),
                after=after,
                op={"op": "motion", "index": int(scene["index"]), "move": move, "verb": verb_out},
                rank=4,
            )
        )
    return rows


def _morph_heavy(scenes: list[dict]) -> list[dict]:
    morphs = [scene for scene in scenes if _is_morph(scene)]
    if len(morphs) <= 1:
        return []
    total = sum(_scene_seconds(scene) for scene in scenes) or 1.0
    spent = sum(_scene_seconds(scene) for scene in morphs)
    if len(morphs) <= 2 and spent / total <= 0.45:
        return []
    keepers: list[int] = []
    climax = next((scene for scene in morphs if scene.get("beat") == "climax"), None)
    if climax is None:
        climax = next((scene for scene in morphs if scene.get("signature")), None)
    if climax is not None:
        keepers.append(int(climax["index"]))
    extra = next((scene for scene in morphs if scene.get("signature") and int(scene["index"]) not in keepers), None)
    if extra is not None and len(keepers) < 2:
        keepers.append(int(extra["index"]))
    rows = []
    for scene in morphs:
        if int(scene["index"]) in keepers:
            continue
        rows.append(
            _finding(
                check="morph-heavy",
                scene=scene,
                kind="rerender",
                lesson_id="shots-not-morphs",
                plain=f"{_label(scene)} is another morph. The signature stays on the drop, and this card becomes a hard cut.",
                before=str(scene.get("edit") or "morph"),
                after="hard cut",
                op={"op": "edit", "index": int(scene["index"]), "value": "hard cut"},
                rank=5,
            )
        )
    return rows


def _story_gaps(scenes: list[dict]) -> list[dict]:
    if not scenes:
        return []
    rows = []
    if any(
        not str(scene.get(key) or "").strip()
        for scene in scenes
        for key in ("protagonist", "goal", "payoff")
    ):
        who = "the subject"
        rows.append(
            _finding(
                check="missing-story",
                scene=None,
                kind="cpu",
                lesson_id="shots-not-morphs",
                plain="The board is missing a protagonist, a goal, or a payoff. Every card takes the same spine.",
                before="no story spine",
                after=f"{who}, a goal, a payoff",
                op={
                    "op": "story",
                    "protagonist": who,
                    "goal": f"follow {who} through the song",
                    "payoff": f"{who} lands the last shot, changed",
                },
                rank=3,
            )
        )
    beats = {str(scene.get("beat") or "") for scene in scenes}
    missing = []
    if "setup" not in beats:
        missing.append("setup")
    if "climax" not in beats:
        missing.append("climax")
    if "release" not in beats and str(scenes[-1].get("beat") or "") != "climax":
        missing.append("release")
    if missing:
        named = ", ".join(missing)
        rows.append(
            _finding(
                check="missing-beats",
                scene=scenes[0],
                kind="rerender",
                lesson_id="shots-not-morphs",
                plain=f"The story is missing {named}. The first card, the middle, and the last card take setup, climax, and release.",
                before=named,
                after="setup, climax, release",
                op={"op": "beats"},
            )
        )
    return rows


def _hook(scenes: list[dict]) -> list[dict]:
    if not scenes:
        return []
    early = [scene for scene in scenes if float(scene.get("start") or 0) < HOOK_WINDOW]
    strong = [
        scene
        for scene in early
        if str(scene.get("edit") or "") in IMPACT_EDITS
        or str(scene.get("move") or "") in {"push in", "orbit", "follow"}
        or len(str(scene.get("action") or "")) > 12
    ]
    first = scenes[0]
    if float(first.get("start") or 0) >= HOOK_WINDOW:
        return [
            _finding(
                check="missing-hook",
                scene=first,
                kind="cpu",
                plain=f"The first scene starts at {float(first.get('start') or 0):.1f}s. The hook has to land inside the first {HOOK_WINDOW:.0f} seconds, so it moves to the top.",
                before=f"starts at {float(first.get('start') or 0):.1f}s",
                after="starts at 0s",
                op={"op": "start", "index": int(first["index"]), "value": 0.0},
            )
        ]
    if strong:
        return []
    return [
        _finding(
            check="missing-hook",
            scene=first,
            kind="rerender",
            plain=f"Nothing in the first {HOOK_WINDOW:.0f} seconds grabs the eye. {_label(first)} opens on a droplet-burst and a push in.",
            before=str(first.get("edit") or "soft open"),
            after="droplet-burst, push in",
            op={"op": "hook", "index": int(first["index"])},
        )
    ]


def _rhythm(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        start = float(scene.get("start") or 0)
        end = float(scene.get("end") or start)
        length = max(0.0, end - start)
        if length > RHYTHM_MAX + 0.2:
            target = round(start + RHYTHM_MAX, 4)
            rows.append(
                _finding(
                    check="rhythm",
                    scene=scene,
                    kind="cpu",
                    plain=f"{_label(scene)} runs {length:.1f}s. The cut wants a {RHYTHM_MIN:.1f}–{RHYTHM_MAX:.1f}s pulse, so the hold trims to {RHYTHM_MAX:.1f}s.",
                    before=f"{length:.1f}s",
                    after=f"{RHYTHM_MAX:.1f}s",
                    op={"op": "trim-end", "index": int(scene["index"]), "value": target},
                )
            )
        elif 0.4 < length < RHYTHM_MIN - 0.2 and str(scene.get("edit") or "") in MORPHS:
            rows.append(
                _finding(
                    check="rhythm-short",
                    scene=scene,
                    kind="rerender",
                    plain=f"{_label(scene)} is only {length:.1f}s and still tries to morph. A short section wants a snap.",
                    before=f"{length:.1f}s {scene.get('edit')}",
                    after="snap",
                    op={"op": "edit", "index": int(scene["index"]), "value": "snap"},
                )
            )
    return rows


def _offbeat(scenes: list[dict], beats: list[float]) -> list[dict]:
    rows = []
    for scene in scenes:
        end = float(scene.get("end") or 0)
        beat = _nearest(end, beats, 0.3)
        if beat is None:
            continue
        rows.append(
            _finding(
                check="off-beat",
                scene=scene,
                kind="cpu",
                plain=f"{_label(scene)} ends at {end:.2f}s, off the beat. It locks to {beat:.2f}s.",
                before=f"ends {end:.2f}s",
                after=f"ends {beat:.2f}s",
                op={"op": "trim-end", "index": int(scene["index"]), "value": beat},
            )
        )
    return rows


def _variety(scenes: list[dict]) -> list[dict]:
    if len(scenes) < 3:
        return []
    edits = {str(scene.get("edit") or "") for scene in scenes}
    if len(edits) >= min(3, len(scenes)):
        return []
    climax = next((scene for scene in scenes if scene.get("beat") == "climax"), scenes[len(scenes) // 2])
    if str(climax.get("edit") or "") in IMPACT_EDITS:
        return []
    return [
        _finding(
            check="variety",
            scene=climax,
            kind="rerender",
            plain=f"The edits barely change. {_label(climax)} takes the accent as a droplet-burst so the rhythm is not one move.",
            before=str(climax.get("edit") or "one edit"),
            after="droplet-burst",
            op={"op": "edit", "index": int(climax["index"]), "value": "droplet-burst"},
        )
    ]


def _dead(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        length = float(scene.get("end") or 0) - float(scene.get("start") or 0)
        if length < 5 or scene.get("move") != "hold" or scene.get("beat") == "climax":
            continue
        if str(scene.get("edit") or "") not in MORPHS | {"continuous"}:
            continue
        rows.append(
            _finding(
                check="dead-stretch",
                scene=scene,
                kind="rerender",
                plain=f"{_label(scene)} holds still for {length:.1f}s. The camera goes to an orbit so the stretch is not a straight line.",
                before="hold",
                after="orbit",
                op={"op": "move", "index": int(scene["index"]), "value": "orbit"},
            )
        )
    return rows


def _accents(scenes: list[dict]) -> list[dict]:
    rows = []
    hits = [scene for scene in scenes if str(scene.get("edit") or "") in IMPACT_EDITS]
    for left, right in zip(hits, hits[1:]):
        if abs(float(left.get("start") or 0) - float(right.get("start") or 0)) > 1.0:
            continue
        victim = right if right.get("beat") != "climax" else left
        if victim.get("beat") == "climax" and left.get("beat") == "climax":
            continue
        rows.append(
            _finding(
                check="stacked-hits",
                scene=victim,
                kind="rerender",
                plain=f"{_label(left)} and {_label(right)} both accent the same second. {_label(victim)} becomes a ribbon and keeps one hit.",
                before=str(victim.get("edit") or "accent"),
                after="ribbon",
                op={"op": "edit", "index": int(victim["index"]), "value": "ribbon"},
            )
        )
    return rows


def _flash_gate(flash: str) -> list[dict]:
    if str(flash or "normal") != "hard":
        return []
    return [
        _finding(
            check="harding-flash",
            scene=None,
            kind="cpu",
            plain="The flash is set to hard. More than three opposing flashes in a second gets pulled back, so the gate goes to soft.",
            before="hard flash",
            after="soft flash",
            op={"op": "flash", "value": "soft"},
        )
    ]


def _shimmer(preset: dict | None) -> list[dict]:
    if not preset or look_allowed(preset):
        return []
    return [
        _finding(
            check="shimmer",
            scene=None,
            kind="cpu",
            lesson_id="no-shimmer",
            plain="That look is a wavy shimmer. It is not a preset here, so the look comes off.",
            before=str(preset.get("name") or preset.get("id") or "shimmer"),
            after="no shimmer look",
            op={"op": "clear-preset"},
        )
    ]


def _grade(frames: np.ndarray | None, sliders: dict | None) -> list[dict]:
    if frames is None or len(frames) < 2:
        return []
    mean = float(np.asarray(frames).mean())
    material = float((sliders or {}).get("material") or 0.5)
    if mean > 200:
        target = round(min(material, 0.35), 2)
        return [
            _finding(
                check="exposure-high",
                scene=None,
                kind="cpu",
                plain=f"The picture averages {mean:.0f}, blown out. Material comes down to {target:.2f} and the flash stays soft.",
                before=f"mean {mean:.0f}",
                after=f"material {target:.2f}",
                op={"op": "grade", "material": target, "flash": "soft"},
            )
        ]
    if mean < 16:
        target = round(max(material, 0.75), 2)
        return [
            _finding(
                check="exposure-low",
                scene=None,
                kind="cpu",
                plain=f"The picture averages {mean:.0f}, crushed. Material comes up to {target:.2f} so the body can read.",
                before=f"mean {mean:.0f}",
                after=f"material {target:.2f}",
                op={"op": "grade", "material": target},
            )
        ]
    return []


def _frame_motion(frames: np.ndarray, scenes: list[dict], fps: float, beats: list[float]) -> list[dict]:
    rows = []
    events = detect(frames)
    frozen = events["frozen"]
    if len(frozen) >= max(4, int(0.45 * len(frames))):
        scene = next((item for item in scenes if item.get("beat") == "climax"), scenes[0] if scenes else None)
        if scene is not None and str(scene.get("edit") or "") not in {"dive-splash", "droplet-burst"}:
            rows.append(
                _finding(
                    check="frozen-frames",
                    scene=scene,
                    kind="rerender",
                    lesson_id="freeze-fluid",
                    plain=f"{len(frozen)} sampled frames barely move. {_label(scene)} becomes a dive-splash so the still is not pretending to be a hit.",
                    before="frozen stretch",
                    after="dive-splash",
                    op={"op": "edit", "index": int(scene["index"]), "value": "dive-splash"},
                )
            )
    rate = float(fps or 24)
    beat_at = [int(round(beat * rate)) for beat in beats]
    off = 0
    for cut in events["cuts"]:
        if beat_at and min(abs(cut - beat) for beat in beat_at) > max(2, int(rate * 0.12)):
            off += 1
    if off and scenes:
        scene = scenes[min(len(scenes) - 1, off % len(scenes))]
        end = float(scene.get("end") or 0)
        beat = _nearest(end, beats, 0.45)
        if beat is not None:
            rows.append(
                _finding(
                    check="cut-off-beat",
                    scene=scene,
                    kind="cpu",
                    plain=f"{off} hard cut{'s' if off != 1 else ''} miss the grid. {_label(scene)} locks its end to the beat at {beat:.2f}s.",
                    before=f"{off} off the beat",
                    after=f"end {beat:.2f}s",
                    op={"op": "trim-end", "index": int(scene["index"]), "value": beat},
                )
            )
    flashes = harding_flash_rate(frames, rate)
    if flashes > 3:
        rows.append(
            _finding(
                check="harding-frames",
                scene=None,
                kind="cpu",
                plain=f"The frames show {flashes:.0f} opposing flashes in one second. The gate allows 3, so the flash goes soft.",
                before=f"{flashes:.0f} flashes in a second",
                after="soft flash",
                op={"op": "flash", "value": "soft"},
            )
        )
    # A seam is a hard cut sitting on a scene boundary that asked for a dissolve.
    if scenes and events["cuts"]:
        for scene in scenes:
            if str(scene.get("edit") or "") not in SOFT_DISSOLVES:
                continue
            boundary = int(round(float(scene.get("start") or 0) * rate))
            if any(abs(cut - boundary) <= max(2, int(rate * 0.12)) for cut in events["cuts"]):
                rows.append(
                    _finding(
                        check="seam",
                        scene=scene,
                        kind="rerender",
                        lesson_id="dissolve-cap",
                        plain=f"A hard edge sits on the join into {_label(scene)}. That scene needs a new picture; the dissolve stays at {min(_fade_of(scene), DISSOLVE_CAP)} frames.",
                        before="seam on the overlap",
                        after=f"dissolve ≤ {DISSOLVE_CAP}f, scene re-rendered",
                        op={"op": "fade", "index": int(scene["index"]), "value": min(_fade_of(scene), DISSOLVE_CAP)},
                    )
                )
                break
    return rows


def _duration_gap(scenes: list[dict], audio: float | None, video: float | None) -> list[dict]:
    rows = []
    if audio and scenes:
        end = float(scenes[-1].get("end") or 0)
        if abs(end - float(audio)) > 0.45 and end > float(audio) + 0.45:
            rows.append(
                _finding(
                    check="av-length",
                    scene=scenes[-1],
                    kind="cpu",
                    plain=f"The board runs to {end:.1f}s and the song is {float(audio):.1f}s. The last scene trims to the song.",
                    before=f"board {end:.1f}s",
                    after=f"board {float(audio):.1f}s",
                    op={"op": "trim-end", "index": int(scenes[-1]["index"]), "value": round(float(audio), 4)},
                )
            )
    if audio and video and abs(float(video) - float(audio)) > 0.45:
        rows.append(
            _finding(
                check="av-mismatch",
                scene=None,
                kind="cpu",
                plain=f"The picture is {float(video):.1f}s and the song is {float(audio):.1f}s. A fresh render in this tier locks them together.",
                before=f"picture {float(video):.1f}s",
                after=f"song {float(audio):.1f}s",
                op={},
            )
        )
    return rows


_SCALE = {"macro": 0, "close": 1, "medium": 2, "tracking": 2, "wide": 3, "overhead": 3, "reveal": 4}
_DECOR = ("particles", "particle", "glitch", "sparkle", "confetti", "lens flare", "bokeh")
_TURNING = {"turn", "turns", "orbit", "orbits", "circle", "circles"}


def _shot_scale(scene: dict) -> int:
    return _SCALE.get(str(scene.get("shot") or ""), 2)


def _one_subject(scenes: list[dict]) -> list[dict]:
    names: list[str] = []
    first = ""
    for scene in scenes:
        who = " ".join(str(scene.get("protagonist") or "").split())
        key = who.lower()
        if not key:
            continue
        if not first:
            first = who
        if key not in names:
            names.append(key)
    if len(names) < 2:
        return []
    return [
        _finding(
            check="one-subject",
            scene=None,
            kind="cpu",
            lesson_id="motion-director",
            plain=f"The film names {len(names)} subjects. One of them carries it, so every card takes {first}.",
            before=", ".join(names),
            after=first,
            op={"op": "protagonist", "protagonist": first},
            rank=3,
        )
    ]


def _unmotivated_cut(scenes: list[dict], beats: list[float]) -> list[dict]:
    rows = []
    for previous, scene in zip(scenes, scenes[1:]):
        edit = str(scene.get("edit") or "")
        if edit not in HARD_CUTS:
            continue
        if scene.get("signature") or previous.get("signature"):
            continue
        start = float(scene.get("start") or 0)
        off = False
        beat = None
        if beats:
            nearest = min(beats, key=lambda item: abs(item - start))
            if abs(nearest - start) > (1.0 / 24.0) + 1e-3:
                off = True
                beat = nearest
        jump = abs(_shot_scale(scene) - _shot_scale(previous))
        left = str(previous.get("move") or "")
        right = str(scene.get("move") or "")
        oppose = (left == "push in" and right == "pull back") or (left == "pull back" and right == "push in")
        if not off and not (jump > 2 and oppose):
            continue
        if off and beat is not None:
            op = {"op": "trim-end", "index": int(previous["index"]), "value": round(float(beat), 4)}
            after = f"end {float(beat):.2f}s"
        else:
            op = {"op": "move", "index": int(scene["index"]), "value": "follow"}
            after = "camera follow"
        rows.append(
            _finding(
                check="unmotivated-cut",
                scene=scene,
                kind="cpu" if off else "rerender",
                lesson_id="motion-director",
                plain=f"{_label(scene)} cuts without a reason on screen. A hard cut lands on the beat, at a matching size.",
                before=edit,
                after=after,
                op=op,
                rank=4,
            )
        )
    return rows


def _follow_through(scenes: list[dict]) -> list[dict]:
    climax_at = next((index for index, scene in enumerate(scenes) if scene.get("beat") == "climax"), None)
    if climax_at is None or climax_at + 1 >= len(scenes):
        return []
    nxt = scenes[climax_at + 1]
    if str(nxt.get("move") or "") != "hold":
        return []
    return [
        _finding(
            check="follow-through",
            scene=nxt,
            kind="rerender",
            lesson_id="motion-director",
            plain=f"{_label(nxt)} holds after the hit. The lead move needs a follow-through.",
            before="hold",
            after="camera follow",
            op={"op": "motion", "index": int(nxt["index"]), "move": "follow"},
            rank=4,
        )
    ]


def _repeated_layout(scenes: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    rows = []
    cycle = ("follow", "push in", "pull back", "orbit")
    for scene in scenes:
        shot = str(scene.get("shot") or "")
        move = str(scene.get("move") or "")
        if not shot or not move:
            continue
        key = (shot, move)
        if key not in seen:
            seen.add(key)
            continue
        replacement = next((item for item in cycle if (shot, item) not in seen), "follow")
        seen.add((shot, replacement))
        rows.append(
            _finding(
                check="repeated-layout",
                scene=scene,
                kind="rerender",
                lesson_id="motion-director",
                plain=f"{_label(scene)} repeats {shot} / {move}. The next shot changes scale or move.",
                before=f"{shot} / {move}",
                after=f"{shot} / {replacement}",
                op={"op": "move", "index": int(scene["index"]), "value": replacement},
                rank=4,
            )
        )
    return rows


def _decorative(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        blob = " ".join(str(scene.get(key) or "") for key in ("action", "guide")).lower()
        if not any(word in blob for word in _DECOR):
            continue
        rows.append(
            _finding(
                check="decorative",
                scene=scene,
                kind="rerender",
                lesson_id="motion-director",
                plain=f"{_label(scene)} spends the frame on particles, a glitch, or a flare. The effect has to earn the shot.",
                before="decorative effect",
                after="effect removed",
                op={"op": "strip", "index": int(scene["index"])},
                rank=6,
            )
        )
    return rows


def _camera_motivated(scenes: list[dict]) -> list[dict]:
    rows = []
    for scene in scenes:
        move = str(scene.get("move") or "")
        if move != "orbit":
            continue
        verb = str(scene.get("verb") or "").strip().lower()
        if verb in _TURNING:
            continue
        rows.append(
            _finding(
                check="unmotivated-camera",
                scene=scene,
                kind="rerender",
                lesson_id="motion-director",
                plain=f"{_label(scene)} orbits with nothing on screen turning. The camera follows the verb.",
                before="orbit",
                after="camera follow",
                op={"op": "move", "index": int(scene["index"]), "value": "follow"},
                rank=4,
            )
        )
    return rows


def _extra_line(scenes: list[dict]) -> str:
    """One optional sentence from a local model. A missing model adds nothing."""
    if os.environ.get("XENO_REVIEW_LLM") != "1":
        return ""
    try:
        from xenoform.llm import chat, reachable

        if not reachable(timeout=0.3):
            return ""
        brief = "; ".join(f"{_label(scene)} {scene.get('edit')}" for scene in scenes[:8])
        reply = chat(
            "You are a music-video editor. One sentence, no quotes from books.",
            f"Name one plain problem in this cut, or say it holds: {brief}",
            timeout=2.0,
        )
    except Exception:
        return ""
    text = ""
    if isinstance(reply, dict):
        text = str(reply.get("content") or reply.get("text") or "")
    elif isinstance(reply, str):
        text = reply
    text = " ".join(text.split())[:180]
    return text


def audit(
    scenes: list[dict],
    features: dict | None = None,
    *,
    frames: np.ndarray | None = None,
    fps: float = 24.0,
    flash: str = "normal",
    sliders: dict | None = None,
    preset: dict | None = None,
    register_forms: list[str] | None = None,
    motif: str = "",
    audio_duration: float | None = None,
    video_duration: float | None = None,
    ask_model: bool = False,
) -> dict[str, Any]:
    """Return a plain report. Nothing here renders a frame or calls a model unless asked."""
    board = list(scenes or [])
    beats = _beats(features)
    forms = list(register_forms or [])
    rows: list[dict] = []
    rows.extend(_fades(board))
    rows.extend(_guides(board))
    rows.extend(_slow_hits(board))
    rows.extend(_hard_inside_morph(board))
    rows.extend(_frozen_cards(board))
    rows.extend(_loops(board, forms, motif))
    rows.extend(_low_motion(board))
    rows.extend(_morph_heavy(board))
    rows.extend(_story_gaps(board))
    rows.extend(_one_subject(board))
    rows.extend(_unmotivated_cut(board, beats))
    rows.extend(_follow_through(board))
    rows.extend(_repeated_layout(board))
    rows.extend(_decorative(board))
    rows.extend(_camera_motivated(board))
    rows.extend(_hook(board))
    rows.extend(_rhythm(board))
    rows.extend(_offbeat(board, beats))
    rows.extend(_variety(board))
    rows.extend(_dead(board))
    rows.extend(_accents(board))
    rows.extend(_flash_gate(flash))
    rows.extend(_shimmer(preset))
    rows.extend(_grade(frames, sliders))
    if frames is not None and len(frames) > 1:
        rows.extend(_frame_motion(frames, board, fps, beats))
    duration = audio_duration
    if duration is None and features is not None:
        duration = float(features.get("duration") or 0) or None
    rows.extend(_duration_gap(board, duration, video_duration))
    rows = _dedupe(rows)
    note = _extra_line(board) if ask_model else ""
    if note:
        rows.append(
            _finding(
                check="model-note",
                scene=None,
                kind="note",
                plain=note,
                before="",
                after="",
                op={},
            )
        )
    cpu = [row["scene"] for row in rows if row["kind"] == "cpu"]
    rerender = []
    for row in rows:
        if row["kind"] == "rerender" and row["scene"] not in rerender and row["scene"] != "board":
            rerender.append(row["scene"])
    if not rows:
        summary = "The board holds. Nothing obvious to fix."
    else:
        board_n = sum(1 for row in rows if row["kind"] == "cpu")
        picture_n = len(rerender)
        parts = []
        if board_n:
            parts.append(f"{board_n} fix{'es' if board_n != 1 else ''} on the board, no GPU")
        if picture_n:
            parts.append(f"{picture_n} scene{'s' if picture_n != 1 else ''} need a new picture")
        notes_n = sum(1 for row in rows if row["kind"] == "note")
        if notes_n and not parts:
            parts.append(f"{notes_n} note{'s' if notes_n != 1 else ''}")
        summary = ". ".join(parts) + "." if parts else "Review finished."
    return {
        "summary": summary,
        "findings": rows,
        "rerender": rerender,
        "cpu": cpu,
        "watched": list(_WATCHED),
        "clear": not any(row["kind"] in {"cpu", "rerender"} for row in rows),
    }


def apply_findings(
    scenes: list[dict],
    findings: list[dict],
    *,
    sliders: dict | None = None,
    flash: str = "normal",
    preset: str = "",
) -> dict[str, Any]:
    """Write the zero-GPU fixes and the card edits. Returns the board, not a video."""
    out = copy.deepcopy(list(scenes or []))
    by_index = {int(scene.get("index") or 0): scene for scene in out}
    sliders = dict(sliders or {})
    flash_out = str(flash or "normal")
    preset_out = str(preset or "")
    applied = []
    for row in findings or []:
        op = row.get("op") or {}
        name = str(op.get("op") or "")
        if not name:
            continue
        index = op.get("index")
        scene = by_index.get(int(index)) if index is not None else None
        if name == "fade" and scene is not None:
            scene["fade_frames"] = int(op.get("value") or DISSOLVE_CAP)
        elif name == "guides" and scene is not None:
            strengths = dict(scene.get("guide_strengths") or {})
            edit = str(scene.get("edit") or "")
            for key in ("guide", "mid", "bolt"):
                if key in strengths:
                    try:
                        strengths[key] = round(min(float(strengths[key]), cap_for(edit, key)), 4)
                    except (TypeError, ValueError):
                        continue
            strengths["end"] = "late"
            strengths["offset_frames"] = max(int(strengths.get("offset_frames") or 0), 32)
            scene["guide_strengths"] = strengths
        elif name == "unstick" and scene is not None:
            strengths = dict(scene.get("guide_strengths") or {})
            strengths["guide"] = 0.0
            if "bolt" in strengths:
                strengths["bolt"] = round(min(float(strengths.get("bolt") or 0), BOLT_GUIDE_CAP), 4)
            strengths["end"] = "late"
            scene["guide_strengths"] = strengths
        elif name == "trim-impact" and scene is not None:
            retime = dict(scene.get("retime") or {})
            anchors = [list(pair) for pair in retime.get("anchors_s") or []]
            if len(anchors) >= 2:
                anchors[1][1] = approach_dst(float(anchors[1][0]), float(anchors[1][1]))
                retime["anchors_s"] = anchors
            retime["speed"] = "trim"
            scene["retime"] = retime
        elif name == "edit" and scene is not None:
            scene["edit"] = str(op.get("value") or scene.get("edit") or "ribbon")
            if scene["edit"] in {"hard cut", "snap"}:
                scene["signature"] = False
                scene["conditioning"] = "first-frame"
            scene["edited"] = True
        elif name == "motion" and scene is not None:
            scene["move"] = str(op.get("move") or "follow")
            if op.get("verb"):
                scene["verb"] = str(op["verb"])
            scene["edited"] = True
            _refresh_guide(scene)
        elif name == "story":
            who = str(op.get("protagonist") or "the subject")
            goal = str(op.get("goal") or f"follow {who} through the song")
            payoff = str(op.get("payoff") or f"{who} lands the last shot, changed")
            for item in out:
                item["protagonist"] = who
                item["goal"] = goal
                item["payoff"] = payoff
                _refresh_guide(item)
        elif name == "protagonist":
            who = str(op.get("protagonist") or "the subject")
            for item in out:
                item["protagonist"] = who
                _refresh_guide(item)
        elif name == "strip" and scene is not None:
            import re

            pattern = re.compile(r"\b(particles?|glitch(?:es)?|sparkles?|confetti|lens flares?|bokeh)\b", re.I)
            for key in ("action", "guide"):
                if scene.get(key):
                    scene[key] = " ".join(pattern.sub("", str(scene[key])).split())
            scene["edited"] = True
        elif name == "beats":
            _assign_story_beats(out)
        elif name == "form" and scene is not None:
            scene["form"] = str(op.get("value") or scene.get("form"))
            scene["edited"] = True
        elif name == "move" and scene is not None:
            scene["move"] = str(op.get("value") or "orbit")
            scene["edited"] = True
        elif name == "hook" and scene is not None:
            scene["edit"] = "droplet-burst"
            scene["move"] = "push in"
            scene["shot"] = scene.get("shot") or "close"
            scene["edited"] = True
        elif name == "start" and scene is not None:
            scene["start"] = float(op.get("value") or 0)
        elif name == "trim-end" and scene is not None:
            end = float(op.get("value") or scene.get("end") or 0)
            start = float(scene.get("start") or 0)
            if end > start + 0.2:
                scene["end"] = round(end, 4)
                scene["seconds"] = round(end - start, 4)
                scene["hold"] = scene["seconds"]
        elif name == "recast":
            targets = []
            wanted = {str(item) for item in (op.get("shots") or [])}
            if wanted:
                targets = [item for item in out if f"s{int(item.get('index') or 0)}" in wanted]
            elif scene is not None:
                targets = [scene]
            sentence = " ".join(str(op.get("sentence") or "").split())
            still = str(op.get("still") or "")
            still_name = str(op.get("still_name") or "")
            for item in targets:
                guide = str(item.get("guide") or "")
                if sentence and sentence not in guide:
                    item["guide"] = f"{guide} {sentence}".strip()
                lines = [str(line) for line in (item.get("lines") or [])]
                if sentence and sentence not in lines:
                    lines.append(sentence)
                    item["lines"] = lines
                if still:
                    item["reference_still"] = still
                if still_name:
                    item["still_name"] = still_name
                if item.get("guide_from") != "previous-last":
                    item["guide_from"] = "reference"
                item["edited"] = True
        elif name == "flash":
            flash_out = str(op.get("value") or "soft")
        elif name == "grade":
            if "material" in op:
                sliders["material"] = float(op["material"])
            if op.get("flash"):
                flash_out = str(op["flash"])
        elif name == "clear-preset":
            preset_out = ""
        else:
            continue
        applied.append(row.get("id"))
    return {"scenes": out, "sliders": sliders, "flash": flash_out, "preset": preset_out, "applied": applied}


def _assign_story_beats(scenes: list[dict]) -> None:
    if not scenes:
        return
    have = {str(scene.get("beat") or "") for scene in scenes}
    if "setup" not in have:
        scenes[0]["beat"] = "setup"
    have = {str(scene.get("beat") or "") for scene in scenes}
    if "climax" not in have:
        scenes[len(scenes) // 2]["beat"] = "climax"
    have = {str(scene.get("beat") or "") for scene in scenes}
    if "release" not in have and str(scenes[-1].get("beat") or "") != "climax":
        scenes[-1]["beat"] = "release"


def _refresh_guide(scene: dict) -> None:
    from xenoform.storyboard import _guide

    scene["guide"] = _guide(scene)


def contact_sheet(scenes: list[dict], palette: str = "violet") -> bytes:
    """A small PNG of the board. One cell a scene, up to eight, no video model."""
    tints = {
        "violet": (120, 70, 140),
        "grey-green": (70, 110, 90),
        "gold": (170, 130, 60),
        "bronze": (150, 90, 50),
        "neutral": (140, 130, 120),
    }
    tint = tints.get(palette, tints["neutral"])
    cells = list(scenes[:8]) or [{"index": 0, "form": "sphere", "edit": "ribbon"}]
    cols = 4 if len(cells) > 2 else max(1, len(cells))
    rows = int(np.ceil(len(cells) / cols))
    cw, ch = 160, 90
    image = np.zeros((rows * ch, cols * cw, 3), dtype=np.uint8)
    image[:, :] = (18, 14, 12)
    for pos, scene in enumerate(cells):
        row, col = divmod(pos, cols)
        y0, x0 = row * ch, col * cw
        tile = image[y0 + 4 : y0 + ch - 4, x0 + 4 : x0 + cw - 4]
        tile[:] = (28, 22, 18)
        cy, cx = tile.shape[0] // 2, tile.shape[1] // 2
        yy, xx = np.ogrid[: tile.shape[0], : tile.shape[1]]
        radius = 18 + (int(scene.get("index") or 0) % 5) * 3
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius ** 2
        color = np.array(tint, dtype=np.uint8)
        if str(scene.get("edit") or "") in IMPACT_EDITS:
            color = np.minimum(color + np.array([40, 20, 10]), 255).astype(np.uint8)
        tile[mask] = color
    return _png(image)


def _png(image: np.ndarray) -> bytes:
    height, width, _ = image.shape
    proc = subprocess.run(
        [
            os.environ.get("FF", "ffmpeg"),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-i",
            "-",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        input=np.ascontiguousarray(image).tobytes(),
        capture_output=True,
        check=True,
    )
    return proc.stdout


def sample_video(path: str, fps: float = 4.0, width: int = 96, height: int = 54, limit: int = 48) -> np.ndarray | None:
    """Downsampled RGB frames for the frame checks. Missing files return None."""
    if not path or not os.path.exists(path):
        return None
    proc = subprocess.run(
        [
            os.environ.get("FF", "ffmpeg"),
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            f"fps={fps},scale={width}:{height}",
            "-frames:v",
            str(limit),
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        return None
    frame = width * height * 3
    count = len(proc.stdout) // frame
    if count < 2:
        return None
    return np.frombuffer(proc.stdout[: count * frame], dtype=np.uint8).reshape(count, height, width, 3)
