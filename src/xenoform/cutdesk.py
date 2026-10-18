"""Re-cut a storyboard from shots that are already planned.

Nothing in this module loads a model or a GPU. The energy slider, the story
sheet, hero lock, conform, continuous take, the QA panel, and title cards are
pure functions of the cached scene cards and the song's beat clock.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from xenoform.storyboard import MORPH_EDITS, bar_seconds, blocks_from_scenes, snap_bars

_CONTENT = (
    "action",
    "form",
    "shot",
    "move",
    "verb",
    "protagonist",
    "goal",
    "payoff",
    "mood",
    "motif",
    "beat",
    "hero_image",
    "guide",
)


def energy_level(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number:
        return 0.0
    return max(0.0, min(1.0, number))


def morph_budget(energy: Any) -> int:
    """Calm allows none. Hype allows two. The cap is two morphs per clip."""
    return min(2, int(round(energy_level(energy) * 2)))


def is_morph(edit: Any) -> bool:
    """A continuous take is a chain of frames, not one of the two morphs."""
    name = str(edit or "")
    return name in MORPH_EDITS and name != "continuous"


def _duration(features: dict) -> float:
    duration = float(features.get("duration") or 0)
    sections = list(features.get("sections") or [])
    if duration <= 0 and sections:
        duration = float(sections[-1].get("end") or 0)
    beats = list(features.get("beats") or [])
    if duration <= 0 and beats:
        duration = float(beats[-1]) + 0.5
    return duration if duration > 0 else 1.0


def _drop_times(features: dict) -> list[float]:
    times: list[float] = []
    for drop in features.get("drops") or []:
        if isinstance(drop, dict):
            times.append(float(drop.get("start") or 0))
        else:
            try:
                times.append(float(drop))
            except (TypeError, ValueError):
                continue
    return times


def cut_windows(features: dict, energy: Any) -> list[tuple[float, float]]:
    """Calm is one window per section. Higher energy samples more beats."""
    duration = _duration(features)
    sections = [
        section
        for section in (features.get("sections") or [])
        if float(section.get("end") or 0) > float(section.get("start") or 0)
    ]
    level = energy_level(energy)
    beats = sorted(
        {
            round(float(beat), 4)
            for beat in (features.get("beats") or [])
            if 0 < float(beat) < duration - 0.05
        }
    )
    section_count = max(1, len(sections))
    if level <= 0 or not beats:
        if sections:
            return [(float(section["start"]), float(section["end"])) for section in sections]
        return [(0.0, duration)]
    cap = min(max(len(beats), section_count), section_count * 4, 24)
    count = section_count + int(round(level * (cap - section_count)))
    count = max(section_count, min(cap, count))
    if count <= 1:
        return [(0.0, duration)]
    if count - 1 >= len(beats):
        picks = list(beats)
    else:
        picks = []
        for index in range(1, count):
            slot = min(len(beats) - 1, max(0, int(round(index * len(beats) / count)) - 1))
            picks.append(beats[slot])
        picks = sorted(set(picks))
    bounds = [0.0]
    for beat in picks:
        if beat - bounds[-1] >= 0.18:
            bounds.append(float(beat))
    if duration - bounds[-1] < 0.18:
        bounds[-1] = duration
    else:
        bounds.append(duration)
    return list(zip(bounds, bounds[1:]))


def _morph_slots(windows: list[tuple[float, float]], features: dict, allowed: int) -> set[int]:
    if allowed <= 0 or len(windows) < 2:
        return set()
    drops = _drop_times(features)
    if not drops:
        drops = [_duration(features) * 0.66]
    ranked = sorted(
        range(1, len(windows)),
        key=lambda index: min(abs(windows[index][0] - drop) for drop in drops),
    )
    return set(ranked[:allowed])


def _signature_edit(scenes: list[dict]) -> str:
    for scene in scenes:
        edit = str(scene.get("edit") or "")
        if is_morph(edit):
            return edit
    return "ribbon"


def recut(scenes: list[dict], features: dict, energy: Any = 0, morph_cap: int | None = None) -> list[dict]:
    """Lay the cached shots onto a new beat grid. The pictures are not rendered.

    ``morph_cap`` forces the morph count. ``None`` keeps the energy budget.
    ``0`` is a hard cut on every join.
    """
    if not scenes:
        return []
    source = [copy.deepcopy(scene) for scene in scenes]
    windows = cut_windows(features, energy)
    allowed = morph_budget(energy)
    if morph_cap is not None:
        allowed = max(0, min(2, int(morph_cap)))
    morphs = _morph_slots(windows, features, allowed)
    signature = _signature_edit(source)
    bar = bar_seconds(float(features.get("tempo") or 120))
    laid: list[dict] = []
    for index, (start, end) in enumerate(windows):
        row = source[index % len(source)]
        seconds = max(0.05, float(end) - float(start))
        bars = snap_bars(seconds, bar)
        morph = index in morphs
        row["index"] = index
        row["start"] = round(float(start), 4)
        row["end"] = round(float(end), 4)
        row["seconds"] = round(seconds, 4)
        row["bars"] = bars
        row["bar_seconds"] = round(bar, 4)
        row["hold"] = round(bars * bar, 4)
        row["edit"] = signature if morph else "hard cut"
        row["signature"] = morph
        row["conditioning"] = "signature" if morph else "first-frame"
        row["chain_from"] = None
        row["guide_from"] = "hero" if row.get("hero_image") else ""
        row.pop("retime", None)
        laid.append(row)
    return laid


def chain_take(scenes: list[dict], beats: list | None = None) -> list[dict]:
    """Last frame of each shot becomes the first frame of the next.

    The hit inside the shot, about four fifths of the way through, snaps to
    the nearest beat in that window.
    """
    clock = []
    for beat in beats or []:
        try:
            clock.append(float(beat))
        except (TypeError, ValueError):
            continue
    clock.sort()
    chained: list[dict] = []
    for index, scene in enumerate(scenes):
        row = copy.deepcopy(scene)
        if index == 0:
            row["guide_from"] = "hero"
            row["chain_from"] = None
            row["conditioning"] = "first-frame"
            chained.append(row)
            continue
        start = float(row.get("start") or 0)
        end = float(row.get("end") or start)
        impact = start + 0.8 * max(0.0, end - start)
        inside = [beat for beat in clock if start <= beat <= end]
        if inside:
            target = min(inside, key=lambda beat: abs(beat - impact))
        else:
            target = impact
        row["edit"] = "continuous"
        row["signature"] = False
        row["conditioning"] = "first-frame"
        row["chain_from"] = index - 1
        row["guide_from"] = "previous-last"
        row["retime"] = {
            "speed": "hold",
            "anchors_s": [[round(impact, 4), round(float(target), 4)]],
        }
        chained.append(row)
    return chained


def lock_hero(scenes: list[dict], image: str, name: str = "") -> list[dict]:
    """One reference anchors every shot. The action line stays as written."""
    picture = str(image or "").strip()
    who = " ".join(str(name or "").split())
    locked: list[dict] = []
    note = "Hero reference on the first frame."
    for scene in scenes:
        row = copy.deepcopy(scene)
        row["hero_image"] = picture
        row["conditioning"] = "first-frame"
        if who and not str(row.get("protagonist") or "").strip():
            row["protagonist"] = who
        if row.get("guide_from") != "previous-last":
            row["guide_from"] = "hero"
        guide = str(row.get("guide") or "").strip()
        if note not in guide:
            row["guide"] = f"{guide} {note}".strip()
        locked.append(row)
    return locked


def conform_story(scenes: list[dict], features: dict) -> list[dict]:
    """Keep the story and lay it on a different song.

    Matching section counts take those boundaries. Otherwise the old timeline
    scales onto the new duration.
    """
    if not scenes:
        return []
    sections = [
        section
        for section in (features.get("sections") or [])
        if float(section.get("end") or 0) > float(section.get("start") or 0)
    ]
    duration = _duration(features)
    old_end = max((float(scene.get("end") or 0) for scene in scenes), default=0.0) or duration
    scale = duration / old_end if old_end else 1.0
    matched = len(sections) == len(scenes)
    bar = bar_seconds(float(features.get("tempo") or 120))
    laid: list[dict] = []
    for index, scene in enumerate(scenes):
        row = copy.deepcopy(scene)
        if matched:
            start = float(sections[index]["start"])
            end = float(sections[index]["end"])
        else:
            start = float(scene.get("start") or 0) * scale
            end = float(scene.get("end") or start) * scale
        seconds = max(0.05, end - start)
        bars = snap_bars(seconds, bar)
        row["index"] = index
        row["start"] = round(start, 4)
        row["end"] = round(end, 4)
        row["seconds"] = round(seconds, 4)
        row["bars"] = bars
        row["bar_seconds"] = round(bar, 4)
        row["hold"] = round(bars * bar, 4)
        laid.append(row)
    return laid


def story_sheet(brief: str, scenes: list[dict], quality: str, etas: dict | None) -> dict[str, Any]:
    """Logline, hero, journey, the shot list, and a GPU estimate."""
    hero = ""
    for scene in scenes:
        name = str(scene.get("protagonist") or "").strip()
        if name:
            hero = name
            break
    journey = []
    for beat in ("setup", "rising", "climax", "release"):
        line = next((str(scene.get("action") or "") for scene in scenes if scene.get("beat") == beat), "")
        if line:
            journey.append({"beat": beat, "line": line})
    shots = [
        {
            "index": scene.get("index", index),
            "start": scene.get("start"),
            "end": scene.get("end"),
            "shot": scene.get("shot") or "",
            "move": scene.get("move") or "",
            "edit": scene.get("edit") or "",
            "action": scene.get("action") or "",
            "because": scene.get("because") or "",
        }
        for index, scene in enumerate(scenes)
    ]
    logline = " ".join(str(brief or "").split())
    if not logline and scenes:
        logline = str(scenes[0].get("action") or "")
    table = etas or {}
    row = table.get(str(quality or "live")) or {}
    try:
        seconds = int(row.get("first_s") or 0)
    except (TypeError, ValueError):
        seconds = 0
    if str(quality or "live") == "live" or seconds <= 0:
        gpu = {"seconds": 0, "line": "no GPU"}
    else:
        gpu = {"seconds": seconds, "line": str(row.get("line") or f"{seconds} seconds")}
    return {
        "logline": logline,
        "hero": hero,
        "journey": journey,
        "shots": shots,
        "gpu": gpu,
        "quality": str(quality or "live"),
    }


def _nearest_beat(cut: float, beats: list[float]) -> float:
    return min(abs(cut - beat) for beat in beats)


def qa_report(scenes: list[dict], features: dict, energy: Any, flash: str) -> dict[str, Any]:
    """Sync, motion, morph share, flash safety, and whether the energy band hit."""
    beats = []
    for beat in features.get("beats") or []:
        try:
            beats.append(float(beat))
        except (TypeError, ValueError):
            continue
    cuts = [float(scene.get("start") or 0) for scene in scenes[1:]]
    if not beats:
        sync = {
            "score": 1.0,
            "pass": True,
            "detail": "No beat clock, so cut alignment was not scored.",
        }
    elif not cuts:
        sync = {"score": 1.0, "pass": True, "detail": "One shot, so there is no cut to score."}
    else:
        hits = sum(1 for cut in cuts if _nearest_beat(cut, beats) <= 0.1)
        score = hits / len(cuts)
        sync = {
            "score": round(score, 3),
            "pass": score >= 0.8,
            "detail": f"{hits} of {len(cuts)} cuts sit on a beat.",
        }

    moves = [str(scene.get("move") or "hold") for scene in scenes]
    moving = sum(1 for move in moves if move != "hold")
    share = moving / len(moves) if moves else 0.0
    motion = {
        "share": round(share, 3),
        "pass": share >= 0.5,
        "detail": f"{moving} of {len(moves)} shots move.",
    }

    morphs = [scene for scene in scenes if is_morph(scene.get("edit"))]
    count = len(morphs)
    morph_share = count / len(scenes) if scenes else 0.0
    morph = {
        "count": count,
        "share": round(morph_share, 3),
        "pass": count <= 2,
        "detail": f"{count} morphs. The cap is 2.",
    }

    duration = _duration(features)
    rate = (len(beats) / duration) if duration else 0.0
    mode = str(flash or "normal")
    flash_pass = mode == "minimal" or rate <= 3.0
    if mode == "minimal":
        flash_detail = "Flash is minimal."
    else:
        flash_detail = f"Beat flash rate {rate:.2f}/s."
    flash_row = {"pass": flash_pass, "rate": round(rate, 3), "detail": flash_detail}

    allowed = morph_budget(energy)
    sections = list(features.get("sections") or [])
    section_count = max(1, len(sections)) if sections else max(1, len(scenes))
    density = (len(scenes) / section_count) if scenes else 0.0
    level = energy_level(energy)
    expected = 1.0 + level * 3.0
    low = max(0.5, expected - 1.5)
    high = expected + 1.75
    energy_pass = count <= allowed and low <= density <= high
    energy_row = {
        "pass": energy_pass,
        "morphs": count,
        "allowed": allowed,
        "density": round(density, 3),
        "energy": round(level, 3),
        "detail": f"Energy {level:.2f} allows {allowed} morphs. This cut has {count}.",
    }
    return {
        "sync": sync,
        "motion": motion,
        "morph": morph,
        "flash": flash_row,
        "energy": energy_row,
    }


def title_cards(title: str, end: str, duration: float) -> list[dict[str, Any]]:
    """Opening and closing cards. They stay off the recipe's drop and outro list."""
    cues: list[dict[str, Any]] = []
    opening = " ".join(str(title or "").split())
    closing = " ".join(str(end or "").split())
    length = float(duration or 0)
    if opening:
        start = 0.35
        stop = min(length or 3.0, 3.0)
        if stop - start >= 0.35:
            cues.append({"at": "title", "text": opening[:90], "start": round(start, 3), "end": round(stop, 3)})
    if closing and length > 0:
        stop = length
        start = max(0.0, stop - 2.8)
        if stop - start >= 0.35:
            cues.append({"at": "end", "text": closing[:90], "start": round(start, 3), "end": round(stop, 3)})
    return cues


def beat_grid(scenes: list[dict], features: dict) -> dict[str, Any]:
    return {
        "duration": round(_duration(features), 4),
        "beats": [round(float(beat), 4) for beat in features.get("beats") or []],
        "cuts": [round(float(scene.get("start") or 0), 4) for scene in scenes],
        "morphs": [round(float(scene.get("start") or 0), 4) for scene in scenes if is_morph(scene.get("edit"))],
    }


def desk_pass(
    scenes: list[dict],
    features: dict,
    *,
    energy: Any = 0,
    continuous: bool = False,
    hero_image: str = "",
    hero_name: str = "",
    flash: str = "normal",
    brief: str = "",
    quality: str = "live",
    etas: dict | None = None,
    morph_cap: int | None = None,
) -> dict[str, Any]:
    """Recut, then optional chain and hero lock. Returns the grid, QA, and story."""
    cut = recut(scenes, features, energy, morph_cap)
    if continuous:
        cut = chain_take(cut, features.get("beats") or [])
    if str(hero_image or "").strip():
        cut = lock_hero(cut, hero_image, hero_name)
    from xenoform.continuity import continuity_bible, stamp_continuity, story_logic

    cut = stamp_continuity(cut, brief)
    return {
        "scenes": cut,
        "blocks": blocks_from_scenes(cut) if cut else [],
        "grid": beat_grid(cut, features),
        "qa": qa_report(cut, features, energy, flash),
        "story": story_sheet(brief, cut, quality, etas),
        "continuity": continuity_bible(brief, cut),
        "logic": story_logic(brief, cut),
    }


def maybe_stamp(path: str | Path, state: dict, fps: float) -> None:
    """Stamp hero and chain frames only when the desk asked for them."""
    scenes = list(state.get("scenes") or [])
    hero = str(state.get("hero_path") or "")
    continuous = bool(state.get("continuous")) or any(
        str(scene.get("guide_from") or "") == "previous-last" or scene.get("chain_from") not in (None, "")
        for scene in scenes
    )
    if (not hero and not continuous) or not scenes or not Path(path).exists():
        return
    apply_frame_guides(path, scenes, fps, hero or None, continuous=continuous)


def apply_frame_guides(
    video: str | Path,
    scenes: list[dict],
    fps: float,
    hero_path: str | None = None,
    *,
    continuous: bool = False,
) -> None:
    """Put the hero on each shot start, then chain last frame to next first frame.

    Scene 0 keeps the hero. Later shots in a continuous take take the previous
    shot's last frame, so the chain wins over the hero after the opening.
    """
    import numpy as np

    from xenoform.video import probe_video, read_all_frames, write_mp4

    dest = Path(video)
    frames = read_all_frames(dest)
    if len(frames) == 0:
        return
    info = probe_video(dest)
    rate = float(info.get("fps") or fps or 12) or 12.0
    height, width = int(frames.shape[1]), int(frames.shape[2])

    def frame_index(second: float) -> int:
        return max(0, min(len(frames) - 1, int(round(float(second) * rate))))

    hero = _load_rgb(hero_path, width, height) if hero_path else None
    if hero is not None:
        for scene in scenes:
            frames[frame_index(float(scene.get("start") or 0))] = hero
    else:
        for scene in scenes:
            if str(scene.get("guide_from") or "") == "previous-last":
                continue
            still = _load_rgb(scene.get("reference_still"), width, height)
            if still is not None:
                frames[frame_index(float(scene.get("start") or 0))] = still

    for index, scene in enumerate(scenes):
        if index == 0:
            continue
        chained = (
            continuous
            or str(scene.get("guide_from") or "") == "previous-last"
            or scene.get("chain_from") not in (None, "")
        )
        if not chained:
            continue
        previous = scenes[index - 1]
        src = frame_index(float(previous.get("end") or 0) - (1.0 / rate))
        dst = frame_index(float(scene.get("start") or 0))
        if src == dst and dst > 0:
            src = dst - 1
        frames[dst] = np.array(frames[src], copy=True)

    temporary = dest.with_suffix(".stamp.mp4")
    write_mp4(temporary, frames, rate)
    temporary.replace(dest)


def _load_rgb(path: str | Path | None, width: int, height: int):
    import subprocess

    import numpy as np

    from xenoform.video import ffmpeg_bin

    picture = Path(str(path or ""))
    if not picture.is_file():
        return None
    cmd = [
        ffmpeg_bin(),
        "-v",
        "error",
        "-i",
        str(picture),
        "-vf",
        f"scale={width}:{height}",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    try:
        raw = subprocess.check_output(cmd)
    except (OSError, subprocess.CalledProcessError):
        return None
    needed = width * height * 3
    if len(raw) < needed:
        return None
    return np.frombuffer(raw[:needed], dtype=np.uint8).reshape(height, width, 3).copy()
