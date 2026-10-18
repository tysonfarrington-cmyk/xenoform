"""One row per review round. Before metrics, then after, in markdown and JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ledger_paths(folder: Path) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "ledger.json", folder / "ledger.md"


def load_ledger(folder: Path) -> list[dict]:
    path, _md = ledger_paths(folder)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rounds = data.get("rounds") if isinstance(data, dict) else data
    return [row for row in rounds or [] if isinstance(row, dict)]


def open_ids(rounds: list[dict]) -> list[str]:
    if not rounds:
        return []
    last = rounds[-1]
    ids = []
    for item in last.get("problems") or []:
        if item.get("id"):
            ids.append(str(item["id"]))
    for item in last.get("rechecked") or []:
        if item.get("status") == "open" and item.get("id") and item["id"] not in ids:
            ids.append(str(item["id"]))
    return ids


def board_metrics(scenes: list[dict]) -> dict[str, Any]:
    morphs = 0
    hard = 0
    layouts = []
    who = ""
    for scene in scenes or []:
        edit = str(scene.get("edit") or "")
        if edit in {"hard cut", "snap"} and not scene.get("signature"):
            hard += 1
        elif edit or scene.get("signature"):
            morphs += 1
        if scene.get("shot") and scene.get("move"):
            layouts.append(f"{scene.get('shot')}|{scene.get('move')}")
        if not who and scene.get("protagonist"):
            who = str(scene["protagonist"])
    repeated = len(layouts) - len(set(layouts))
    return {
        "scenes": len(scenes or []),
        "hard_cuts": hard,
        "morphs": morphs,
        "repeated_layouts": repeated,
        "protagonist": who,
    }


def _line(metrics: dict) -> str:
    if not metrics:
        return ""
    parts = []
    for key in ("verdict", "scenes", "hard_cuts", "morphs", "repeated_layouts", "protagonist", "failed"):
        if key in metrics and metrics[key] not in ("", None):
            parts.append(f"{key} {metrics[key]}")
    return ", ".join(parts)


def _write(folder: Path, rounds: list[dict]) -> None:
    json_path, md_path = ledger_paths(folder)
    json_path.write_text(json.dumps({"rounds": rounds}, indent=2), encoding="utf-8")
    lines = [
        "# Review ledger",
        "",
        "Each round is a fresh-eyes pass. Before is the measurement. After is the board once the biggest problem was fixed.",
        "",
        "| Round | When | Verdict | Before | After | Rechecked |",
        "|---|---|---|---|---|---|",
    ]
    for row in rounds:
        rechecked = row.get("rechecked") or []
        cleared = sum(1 for item in rechecked if item.get("status") == "cleared")
        still = sum(1 for item in rechecked if item.get("status") == "open")
        check = f"{cleared} cleared, {still} open" if rechecked else ""
        when = str(row.get("at") or "").replace("|", "/")
        lines.append(
            "| {round} | {when} | {verdict} | {before} | {after} | {check} |".format(
                round=row.get("round"),
                when=when,
                verdict=str(row.get("verdict") or "").replace("|", "/"),
                before=_line(row.get("before") or {}).replace("|", "/"),
                after=_line(row.get("after") or {}).replace("|", "/"),
                check=check,
            )
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")


def append_round(folder: Path, *, verdict: str, before: dict, problems: list[dict], rechecked: list[dict]) -> dict:
    rounds = load_ledger(folder)
    row = {
        "round": len(rounds) + 1,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "verdict": verdict,
        "before": before,
        "after": {},
        "problems": [{"id": item.get("id"), "t": item.get("t"), "plain": item.get("plain")} for item in problems],
        "rechecked": list(rechecked),
    }
    rounds.append(row)
    _write(folder, rounds)
    return row


def record_after(folder: Path, after: dict) -> dict | None:
    rounds = load_ledger(folder)
    if not rounds:
        return None
    rounds[-1]["after"] = dict(after)
    _write(folder, rounds)
    return rounds[-1]
