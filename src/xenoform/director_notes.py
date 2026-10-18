"""A shot list and a seed file for every render.

The shot list is for a person. The seed file is the same choices, so another
machine can re-render the cut. Neither file stores an API key.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _clock(seconds: float) -> str:
    total = max(0.0, float(seconds))
    minutes = int(total // 60)
    rest = total - minutes * 60
    return f"{minutes}:{rest:04.1f}"


def _section_at(features: dict | None, start: float) -> str:
    for section in (features or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        try:
            begin = float(section.get("start") or 0.0)
            end = float(section.get("end") or begin)
        except (TypeError, ValueError):
            continue
        if begin <= start < end or (end == begin and abs(begin - start) < 1e-6):
            return str(section.get("label") or "")
    return ""


def _pairs(state: dict, features: dict | None) -> list[dict]:
    try:
        from xenoform.source_library import library_filters, load_library, plan_for_scenes
    except Exception:
        return []
    try:
        library = load_library(str(state.get("library_folder") or ""))
        filters = library_filters(state)
        plan = plan_for_scenes(
            library,
            list(state.get("scenes") or []),
            list((features or {}).get("sections") or []),
            vibe=filters["vibe"],
            mood=filters["mood"],
            energy=filters["energy"],
            beat=filters["beat"],
            pinned=filters["pinned"],
            banned=filters["banned"],
            exclude_faces=filters["exclude_faces"],
            allow_pd_us=filters["allow_pd_us"],
        )
    except Exception:
        return []
    return list(plan.get("pairs") or [])


def _why(scene: dict, pair: dict | None, section: str) -> str:
    if pair and pair.get("reason"):
        chain = " Morph chain." if pair.get("chain") else ""
        return f"{pair['reason']}{chain}"
    if section == "drop" or str(scene.get("beat") or "") in {"drop", "climax"}:
        return "Drop. The change lands on the downbeat."
    if scene.get("signature"):
        return "Signature morph. One change, then hard cuts."
    return "Hard cut. The section holds."


def shot_lines(state: dict, features: dict | None) -> list[dict[str, str]]:
    pairs = _pairs(state, features)
    by_scene = {}
    for pair in pairs:
        if pair.get("scene") is not None:
            by_scene[pair.get("scene")] = pair
    lines = []
    for scene in state.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        start = float(scene.get("start") or 0.0)
        end = float(scene.get("end") or start)
        section = _section_at(features, start) or str(scene.get("beat") or "")
        pair = by_scene.get(scene.get("index"))
        source = ((pair or {}).get("source") or {}).get("id") or str(scene.get("form") or "")
        target = ((pair or {}).get("target") or {}).get("id") or str(scene.get("becomes") or scene.get("form") or "")
        lines.append(
            {
                "time": f"{_clock(start)}–{_clock(end)}",
                "section": section or "section",
                "source": source or "—",
                "target": target or "—",
                "why": _why(scene, pair, section),
            }
        )
    return lines


def shots_markdown(state: dict, features: dict | None, seed: int) -> str:
    rows = shot_lines(state, features)
    lines = [
        "# Director's notes",
        "",
        f"Seed {int(seed)}. Same seed, same scenes, same library filters: the cut can be rendered again.",
        "",
        "| Time | Section | Source | Target | Why |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not rows:
        lines.append("| — | — | — | — | No scenes on this cut. |")
    for row in rows:
        cells = [row["time"], row["section"], row["source"], row["target"], row["why"].replace("|", "/")]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def seed_document(state: dict, features: dict | None, cfg: dict | None, seed: int) -> dict[str, Any]:
    comfy = (cfg or {}).get("comfy") or {}
    scenes = []
    for scene in state.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        scenes.append(
            {
                "index": scene.get("index"),
                "start": scene.get("start"),
                "end": scene.get("end"),
                "action": scene.get("action") or "",
                "form": scene.get("form") or "",
                "shot": scene.get("shot") or "",
                "beat": scene.get("beat") or "",
                "prompt": scene.get("prompt") or "",
                "signature": bool(scene.get("signature")),
            }
        )
    sections = []
    for section in (features or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        sections.append(
            {
                "label": section.get("label") or "",
                "start": section.get("start"),
                "end": section.get("end"),
            }
        )
    return {
        "seed": int(seed),
        "quality": str(state.get("quality") or (cfg or {}).get("quality") or ""),
        "video_model": str(state.get("video_model") or comfy.get("video_model") or ""),
        "brief": str(state.get("brief") or ""),
        "register": str(state.get("register") or ""),
        "flash": str(state.get("flash") or ""),
        "fps": (features or {}).get("fps") or (cfg or {}).get("fps"),
        "width": comfy.get("width"),
        "height": comfy.get("height"),
        "morph_hit": bool(state.get("morph_hit")),
        "library_folder": str(state.get("library_folder") or ""),
        "exclude_faces": state.get("exclude_faces", True) is not False,
        "allow_pd_us": bool(state.get("allow_pd_us")),
        "library_pins": list(state.get("library_pins") or []),
        "library_bans": list(state.get("library_bans") or []),
        "scenes": scenes,
        "sections": sections,
    }


def write_director_notes(
    folder: str | Path,
    state: dict | None,
    features: dict | None = None,
    cfg: dict | None = None,
) -> dict[str, str]:
    """Write ``SHOTS.md`` and ``seed.json`` next to the render."""
    dest = Path(folder)
    dest.mkdir(parents=True, exist_ok=True)
    state = state or {}
    seed = int(state.get("seed") or (cfg or {}).get("seed") or 2727)
    shots = dest / "SHOTS.md"
    seed_path = dest / "seed.json"
    shots.write_text(shots_markdown(state, features, seed), encoding="utf-8")
    seed_path.write_text(json.dumps(seed_document(state, features, cfg, seed), indent=2), encoding="utf-8")
    return {"shots": str(shots), "seed": str(seed_path)}
