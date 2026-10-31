"""The whole-song proof (docs/MUSIC_VIDEO_PLAN.md section 7, docs/SONG.md), from a song made through a desk's own
Whole song button and laid together there.

    python song_proof.py make <song folder> <out dir> --name <file stem> [--label "Breathe 1.0"] [--small-mib 24.5]
    python song_proof.py readme <out dir> [--intro <markdown file>]

``make``: from the song's record (``song.json``) and its cut (``xenoform.mp4``) under ``work/ui/jobs/<song id>``: the
mp4 with the song (``<name>.mp4``), a copy under 25 MiB to share (``<name>_small.mp4``, no taller than 720 lines), a
tile sheet (``<name>_sheet.jpg``: a tile at each passage start and each drop event, and one at the title's hit, each
labelled with the song time, the passage, its role, its vibe and its objects) and ``<name>.json``: the passage table
(passage, seconds, vibe, morphs, looks a minute) and the song's totals (morphs, the Draft minutes it took, what Final
and Fast Final would take on this card and what Cloud would cost), read back by ``readme``.

``readme``: ``README.md`` in the out dir naming every file the ``make`` runs wrote, each song's passage table and
totals, an intro paragraph from ``--intro`` when given.

A look (montage_rules.md 5.4, pacing_proof.passage_looks) is a run of shots with one morph style, one timing, one effect
and one colour look; a passage's looks a minute are its look changes over its length.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
FONT = ROOT / "src" / "xenoform" / "ui_static" / "fonts"
TILE = (384, 216)
LABEL_H = 66
COLS = 4


def mmss(t: float) -> str:
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}"


def _font(size: int, weight: int = 500):
    from PIL import ImageFont

    for name in (f"space-grotesk-{weight}.woff2", "space-grotesk-500.woff2", "space-grotesk-400.woff2"):
        try:
            return ImageFont.truetype(str(FONT / name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def grab(mp4: Path, t: float, size: tuple[int, int] = TILE):
    from PIL import Image

    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(mp4), "-frames:v", "1", "-vf",
                          f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,crop={size[0]}:{size[1]}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    if len(raw) < size[0] * size[1] * 3:
        return Image.new("RGB", size, (0, 0, 0))
    return Image.frombytes("RGB", size, raw[:size[0] * size[1] * 3])


def looks_a_minute(comp: dict, rec: dict) -> dict[int, dict]:
    """Each passage's shots, looks and looks a minute from the song's composite record (its shots in song time)."""
    styles = comp.get("morph_styles") or []
    out: dict[int, dict] = {}
    for i, s in enumerate(comp.get("shots") or []):
        p = int(s.get("song_passage") or 0)
        row = out.setdefault(p, {"shots": 0, "looks": 0, "_last": None})
        key = (styles[i] if i < len(styles) else "", str((s.get("timing") or {}).get("mode") or "smooth"),
               tuple(s.get("fx_names") or []), str(s.get("dance_fx") or ""), str(s.get("vibe") or ""))
        row["shots"] += 1
        row["looks"] += int(key != row["_last"])
        row["_last"] = key
    for p in rec["passages"]:
        row = out.setdefault(p["index"], {"shots": 0, "looks": 0, "_last": None})
        secs = max(1e-6, float(p["end"]) - float(p["start"]))
        row["looks_per_min"] = round(60.0 * row["looks"] / secs, 1)
        row.pop("_last", None)
    return out


def tiles(rec: dict, comp: dict) -> list[dict]:
    """Where the sheet's tiles fall: every passage's start (a little in, past the cut) and every drop event inside a
    run (a style change or a boundary kind every 8 bars), and the title's hit."""
    out = []
    shots = comp.get("shots") or []
    for p in rec["passages"]:
        first = next((s for s in shots if int(s.get("song_passage") or -1) == p["index"]), None)
        span = (float(first["end"]) - float(first["start"])) if first else 1.0
        look = p.get("look") or {}
        what = f"opens drop {int(p['drop_run']) + 1}" + (" (the main)" if p.get("main") else "") + f", heat {float(p.get('heat') or 0):.2f}" \
            if p.get("drop_run") is not None else ""
        out.append({"at": float(p["start"]) + min(1.0, 0.35 * span), "start": float(p["start"]), "passage": p["index"] + 1,
                    "role": p["role"], "vibe": look.get("name") or look.get("vibe") or "", "preset": look.get("preset") or "",
                    "objects": p.get("objects") or [], "event": what})
    for s in shots:
        if s.get("event") in ("style", "kind"):
            p = rec["passages"][int(s.get("song_passage") or 0)]
            look = p.get("look") or {}
            out.append({"at": float(s["start"]) + 0.3, "start": float(s["start"]), "passage": p["index"] + 1, "role": p["role"],
                        "vibe": look.get("name") or look.get("vibe") or "", "preset": look.get("preset") or "",
                        "objects": [], "event": f"8 bars on: {'a style change' if s['event'] == 'style' else 'a boundary kind'}"})
    title = rec.get("title") or {}
    if title.get("at") is not None and title.get("text"):
        out.append({"at": float(title["at"]) + 1.2, "start": float(title["at"]), "passage": len(rec["passages"]), "role": "title",
                    "vibe": "", "preset": "", "objects": [], "event": f"the title \"{title['text']}\" on the last hit"})
    return sorted(out, key=lambda r: r["at"])


def sheet(mp4: Path, rows: list[dict], dest: Path, heading: str) -> Path:
    from PIL import Image, ImageDraw

    n = len(rows)
    cols = COLS
    lines = math.ceil(n / cols)
    head_h = 44
    w, h = TILE[0] * cols, head_h + (TILE[1] + LABEL_H) * lines
    img = Image.new("RGB", (w, h), (12, 12, 16))
    d = ImageDraw.Draw(img)
    d.text((12, 10), heading, font=_font(20, 600), fill=(240, 238, 250))
    big, small = _font(14, 600), _font(12, 400)
    for k, r in enumerate(rows):
        x, y = (k % cols) * TILE[0], head_h + (k // cols) * (TILE[1] + LABEL_H)
        img.paste(grab(mp4, r["at"]), (x, y))
        first = f"{mmss(r['start'])} · {'passage ' + str(r['passage']) if r['role'] != 'title' else 'end'} · {r['role']}"
        second = (r["vibe"] + (f" ({r['preset']})" if r["preset"] else "") + (f" · {r['event']}" if r["event"] else "")).strip(" ·")
        third = ", ".join(r["objects"][:6]) + ("..." if len(r["objects"]) > 6 else "")
        d.text((x + 8, y + TILE[1] + 4), first, font=big, fill=(245, 243, 255))
        d.text((x + 8, y + TILE[1] + 24), second[:58], font=small, fill=(200, 196, 230))
        d.text((x + 8, y + TILE[1] + 42), third[:62], font=small, fill=(160, 158, 180))
    img.save(dest, quality=88)
    return dest


def totals(rec: dict) -> dict:
    """The song's totals: its morphs, what the Draft took here (the windows' renders and the assembly, as measured),
    and what the other tiers would take and Cloud would cost (the plan's estimate on this card)."""
    renders = sum(float(w.get("took_s") or 0.0) for w in rec["windows"])
    assembly = float((rec.get("assembly") or {}).get("took_s") or 0.0)
    tiers = (rec.get("estimate") or {}).get("tiers") or {}
    started = min((float(w["started_at"]) for w in rec["windows"] if w.get("started_at")), default=None)
    finished = max((float(w["finished_at"]) for w in rec["windows"] if w.get("finished_at")), default=None)
    return {"morphs": int((rec.get("plan") or {}).get("morphs") or sum(int(w.get("morphs") or 0) for w in rec["windows"])),
            "windows": len(rec["windows"]), "passages": len(rec["passages"]),
            "draft_render_min": round(renders / 60.0, 1), "assembly_min": round(assembly / 60.0, 1),
            "wall_min": round((finished - started) / 60.0, 1) if started and finished else None,
            "draft_estimate_min": (tiers.get("draft") or {}).get("minutes"),
            "fast_estimate_min": (tiers.get("fast") or {}).get("minutes"),
            "final_estimate_min": (tiers.get("final") or {}).get("minutes"),
            "cloud_estimate_min": (tiers.get("cloud") or {}).get("minutes"),
            "cloud_credits": (tiers.get("cloud") or {}).get("credits")}


def make(folder: Path, out: Path, name: str, label: str, small_mib: float) -> dict:
    from xenoform import song_assemble, song_run

    rec = song_run.load(folder)
    if rec is None:
        raise SystemExit(f"no song record in {folder}")
    comp = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    src = folder / "xenoform.mp4"
    mp4 = out / f"{name}.mp4"
    shutil.copyfile(src, mp4)
    info = song_assemble.probe(mp4)
    small = out / f"{name}_small.mp4"
    song_assemble.small_copy(mp4, small, max_mib=small_mib, height=min(720, int(info["height"])))
    rows = tiles(rec, comp)
    looks = looks_a_minute(comp, rec)
    heading = f"{(rec.get('song') or {}).get('label') or 'Song'} · whole song · {label} · {(rec.get('plan') or {}).get('line') or ''}"
    sheet(mp4, rows, out / f"{name}_sheet.jpg", heading)
    table = []
    for p in rec["passages"]:
        look = p.get("look") or {}
        table.append({"passage": p["index"] + 1, "role": p["role"], "start": round(float(p["start"]), 2),
                      "end": round(float(p["end"]), 2), "seconds": round(float(p["end"]) - float(p["start"]), 1),
                      "vibe": look.get("name") or look.get("vibe") or "", "vibe_id": look.get("vibe") or "",
                      "preset": look.get("preset") or "", "why": look.get("why") or "", "morphs": int(p.get("morphs") or 0),
                      "shots": looks.get(p["index"], {}).get("shots"), "looks": looks.get(p["index"], {}).get("looks"),
                      "looks_per_min": looks.get(p["index"], {}).get("looks_per_min"), "objects": p.get("objects") or [],
                      "heat": p.get("heat"), "main": bool(p.get("main")),
                      "jobs": [rec["windows"][k].get("job_id") or "" for k in p.get("windows") or []]})
    a = rec.get("assembly") or {}
    summary = {"name": name, "label": label, "song_id": rec["id"], "song": (rec.get("song") or {}).get("label"),
               "line": (rec.get("plan") or {}).get("line"), "tier": rec.get("tier"), "aspect": rec.get("aspect"),
               "breathe": rec.get("breathe"), "drop_mode": rec.get("drop_mode"), "taste": rec.get("taste"),
               "files": {"video": mp4.name, "small": small.name, "sheet": f"{name}_sheet.jpg", "data": f"{name}.json"},
               "size": [info["width"], info["height"]], "seconds": round(info["seconds"], 2),
               "mib": round(mp4.stat().st_size / 1024 / 1024, 1), "small_mib": round(small.stat().st_size / 1024 / 1024, 1),
               "table": table, "totals": totals(rec), "cuts": a.get("cuts") or [], "loudness": a.get("loudness"),
               "tame": a.get("tame"), "qa": a.get("qa"), "title": rec.get("title"), "tiles": len(rows)}
    (out / f"{name}.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(f"wrote {mp4.name} ({summary['mib']} MiB), {small.name} ({summary['small_mib']} MiB), {name}_sheet.jpg "
          f"({len(rows)} tiles), {name}.json")
    return summary


def _table_md(s: dict) -> list[str]:
    out = ["| Passage | Song time | Role | Seconds | Vibe | Morphs | Looks a minute | Objects |", "|---|---|---|---|---|---|---|---|"]
    for r in s["table"]:
        vibe = r["vibe"] + (f" (loved chain: {r['preset']})" if r["preset"] else "")
        role = r["role"] + (f", heat {float(r['heat']):.2f}" if r.get("heat") is not None else "") + (", the main drop" if r["main"] else "")
        objects = ", ".join(r["objects"][:8]) + ("..." if len(r["objects"]) > 8 else "")
        out.append(f"| {r['passage']} | {mmss(r['start'])} to {mmss(r['end'])} | {role} | {r['seconds']} | {vibe} | {r['morphs']} | "
                   f"{r['looks_per_min']} | {objects} |")
    return out


def readme(out: Path, intro: Path | None) -> Path:
    songs = sorted((json.loads(p.read_text(encoding="utf-8")) for p in out.glob("*.json")), key=lambda s: str(s.get("name")))
    songs = [s for s in songs if s.get("table")]
    lines = ["# Whole song: Glitch Out, made through the desk's Whole song button", ""]
    if intro and intro.is_file():
        lines += [intro.read_text(encoding="utf-8").strip(), ""]
    lines += ["## The files", ""]
    for s in songs:
        f = s["files"]
        lines += [f"- `{f['video']}`: {s['label']}, the whole song with its sound ({s['seconds']} s, {s['size'][0]}x{s['size'][1]}, "
                  f"{s['mib']} MiB).",
                  f"- `{f['small']}`: the same under 25 MiB to share ({s['small_mib']} MiB).",
                  f"- `{f['sheet']}`: {s['tiles']} tiles, one at each passage start and each drop event and one at the title, each "
                  f"labelled with the song time, the passage, its role, its vibe and its objects.",
                  f"- `{f['data']}`: the passage table, the totals, every cut the assembly made and why, the loudness, the tame "
                  f"and the QA, as data."]
    lines.append("- `README.md`: this file.")
    for s in songs:
        t = s["totals"]
        lines += ["", f"## {s['label']}", "", f"{s['line']}. Draft at {s['aspect']}, Breathe {s['breathe']}, Drops {s['drop_mode']}, "
                  f"the taste file {'on' if s.get('taste') else 'off'}. Song id `{s['song_id']}` on the desk.", ""]
        lines += _table_md(s)
        credits = t.get("cloud_credits") or [None, None]
        loud = s.get("loudness") or {}
        qa = s.get("qa") or {}
        lines += ["", "Totals:", "",
                  f"- Morphs: {t['morphs']} in {t['windows']} Makes over {t['passages']} passages (at most 16 a Make).",
                  f"- Draft: {t['draft_render_min']} min of renders here (the windows' own times) and {t['assembly_min']} min to lay it "
                  f"together" + (f"; {t['wall_min']} min from the first window's start to the last one's end" if t.get("wall_min") else "")
                  + f" (the plan estimated {t['draft_estimate_min']} min).",
                  f"- Final on this card would take about {t['final_estimate_min']} min ({round((t['final_estimate_min'] or 0) / 60, 1)} h); "
                  f"Fast Final about {t['fast_estimate_min']} min.",
                  f"- Cloud Final would take about {t['cloud_estimate_min']} min and spend {credits[0]} to {credits[1]} Comfy Cloud credits "
                  f"(3.6 to 6 a morph). Nothing was spent.",
                  f"- Sound: {loud.get('lufs')} LUFS integrated (target -16), true peak {loud.get('true_peak_db')} dB.",
                  f"- Flash frames after the tame: {qa.get('flash_frames')} in all, {qa.get('max_flash_8_bars')} in the worst 8 bars; "
                  f"cuts off the beat: {qa.get('off_beat')}."]
    path = out / "README.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("folder", type=Path)
    m.add_argument("out", type=Path)
    m.add_argument("--name", required=True)
    m.add_argument("--label", default="")
    m.add_argument("--small-mib", type=float, default=24.5)
    r = sub.add_parser("readme")
    r.add_argument("out", type=Path)
    r.add_argument("--intro", type=Path, default=None)
    args = ap.parse_args()
    if args.cmd == "make":
        make(args.folder, args.out, args.name, args.label or args.name, args.small_mib)
    else:
        print("wrote", readme(args.out, args.intro))


if __name__ == "__main__":
    main()
