"""The proof of a whole song made through a desk's Whole song button (on Cloud Final for the judged set of 1 Nov, any tier
works), delivered. CPU only: it reads the records and the mp4 and sends nothing, so it spends no credits.

Reads the song's record (``work/ui/jobs/<id>/song.json``), its laid-together composite (``simple/simple.json``), each
window's job and the Cloud Final morph cache's sidecars (``work/ui/morph_cache/ltx25cloud/*.json``: the job a clip was
rendered for), and writes into ``--dest``:

- the song's mp4 as made, and a copy under 25 MiB (two-pass x264 at 1280x720, AAC 128k);
- a tile sheet: one tile per passage start and per drop event, labelled with the time, the passage, the vibe and the
  objects on screen;
- the passage table (``passages.md`` and ``passages.csv``) and ``sent.json`` (each window's morphs: planned, sent to
  Comfy Cloud, answered by the cache, fallen back to Draft).

    python docs/demo/tools/cloud_song_deliver.py --song <song id> --dest <output folder> --name <base name> [--skip-small]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / "work" / "ui"
LIMIT = 25 * 1024 * 1024
TW, TH = 384, 216
GUT = 12
BG = (18, 18, 20)
FG = (235, 235, 235)
DIM = (165, 165, 170)
HOT = (255, 170, 90)


def font(size: int, bold: bool = False):
    for name in (("consolab.ttf" if bold else "consola.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def clock(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size,bit_rate:stream=codec_type,width,height,r_frame_rate",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def frame_at(video: Path, t: float, w: int, h: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    if len(raw) < w * h * 3:
        return np.zeros((h, w, 3), np.uint8)
    return np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3)


def small_copy(src: Path, dest: Path, seconds: float) -> dict:
    """Two-pass x264 at 1280x720 with AAC 128k, aimed at 23 MiB so the file lands under 25 MiB."""
    tries = []
    for target_mib in (23.0, 21.0, 19.0):
        kbps = int(target_mib * 8 * 1024 * 1024 / max(seconds, 1.0) / 1000) - 128
        log = dest.with_suffix(".2pass")
        common = ["-vf", "scale=1280:720:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-b:v", f"{kbps}k",
                  "-pix_fmt", "yuv420p", "-passlogfile", str(log)]
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *common, "-pass", "1", "-an", "-f", "mp4", os.devnull], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *common, "-pass", "2", "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart", str(dest)], check=True)
        for p in dest.parent.glob(log.name + "*"):
            p.unlink(missing_ok=True)
        size = dest.stat().st_size
        tries.append({"video_kbps": kbps, "bytes": size})
        if size < LIMIT:
            return {"path": str(dest), "bytes": size, "mib": round(size / 1048576, 2), "video_kbps": kbps, "tries": tries}
    raise SystemExit(f"could not get the copy under 25 MiB: {tries}")


def sent_by_job() -> dict[str, int]:
    """Cloud morphs rendered (sent and back) per job, from the cache sidecars' source paths."""
    out: dict[str, int] = {}
    for side in (WORK / "morph_cache" / "ltx25cloud").glob("*.json"):
        try:
            src = str(json.loads(side.read_text(encoding="utf-8")).get("source") or "")
        except (OSError, ValueError):
            continue
        m = re.search(r"[\\/]jobs[\\/]([0-9a-f]{8})[\\/]", src)
        if m:
            out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out


def window_facts(job: str) -> dict:
    """A window job's own record: its stills' nouns, its shots, and what Cloud Final said of its morphs."""
    folder = WORK / "jobs" / job
    try:
        rec = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    notes = rec.get("fallbacks") or []
    fall = [n for n in notes if isinstance(n, dict) and n.get("fallback")]
    line = next((n.get("cloud_final") for n in notes if isinstance(n, dict) and n.get("cloud_final")), "")
    took = {}
    try:
        took = json.loads((folder / "took.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return {"stills": rec.get("stills") or [], "chain": rec.get("chain"), "shots": rec.get("shots") or [], "fallbacks": fall,
            "cloud_line": line, "took_s": took.get("took_s"), "clips_cloud": len(list((folder / "simple").glob("cloud[0-9][0-9].mp4"))),
            "clips_draft": len(list((folder / "simple").glob("draft_fallback[0-9][0-9].mp4")))}


def noun_of(still: str) -> str:
    stem = Path(str(still)).stem
    stem = re.sub(r"^\d+_", "", stem)
    return stem.replace("_", " ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--name", required=True, help="the base name of the delivered mp4")
    ap.add_argument("--skip-small", action="store_true")
    args = ap.parse_args()
    folder = WORK / "jobs" / args.song
    rec = json.loads((folder / "song.json").read_text(encoding="utf-8"))
    asm = rec.get("assembly") or {}
    if not asm.get("video"):
        raise SystemExit(f"the song is not laid together: {asm.get('error') or rec.get('status')}")
    comp = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    video = folder / asm["video"]
    full = dest / f"{args.name}.mp4"
    if not (args.skip_small and full.is_file() and full.stat().st_size == video.stat().st_size):
        shutil.copy2(video, full)
    info = probe(full)
    seconds = float(info["format"]["duration"])
    small = None
    if not args.skip_small:
        small = small_copy(full, dest / f"{args.name}_under25MiB.mp4", seconds)

    # each window: planned morphs, sent to Comfy Cloud and back, fallen back to Draft, answered by the cache
    sent = sent_by_job()
    wins = []
    for w in rec["windows"]:
        job = w.get("job_id") or ""
        facts = window_facts(job) if job else {}
        jobs_all = [job] + [f.get("job_id") for f in w.get("failed") or [] if f.get("job_id")]
        back = sum(sent.get(j, 0) for j in jobs_all if j)
        fell = len(facts.get("fallbacks") or [])
        wins.append({"window": w["index"], "passage": w["passage"], "role": w.get("role"), "start": w.get("start"), "end": w.get("end"),
                     "morphs": int(w.get("morphs") or 0), "job": job, "failed_jobs": jobs_all[1:], "status": w.get("status"),
                     "attempts": w.get("attempts"), "cloud_back": back, "draft_fallbacks": fell, "sent": back + fell,
                     "from_cache": max(0, int(w.get("morphs") or 0) - back - fell), "cloud_line": facts.get("cloud_line"),
                     "took_s": w.get("took_s") or facts.get("took_s"), "nouns": w.get("nouns") or [],
                     "fallback_why": [str(f.get("why") or "")[:160] for f in facts.get("fallbacks") or []]})
    total = {k: sum(int(x[k] or 0) for x in wins) for k in ("morphs", "sent", "cloud_back", "draft_fallbacks", "from_cache")}
    est = ((rec.get("estimate") or {}).get("tiers") or {}).get("cloud") or {}
    (dest / "sent.json").write_text(json.dumps({"song": args.song, "estimate_cloud": est, "windows": wins, "total": total}, indent=1),
                                    encoding="utf-8")

    # the passage table
    rows = []
    for p in rec["passages"]:
        look = p.get("look") or {}
        wids = p.get("windows") or []
        rows.append({"P": p["index"], "role": p["role"] + (" (main)" if p.get("main") else ""), "start": clock(float(p["start"])),
                     "end": clock(float(p["end"])), "seconds": round(float(p["end"]) - float(p["start"]), 2),
                     "heat": p.get("heat") if p.get("heat") is not None else "", "morphs": p.get("morphs"),
                     "vibe": look.get("name") or look.get("vibe") or "", "chain": look.get("preset") or "",
                     "why": look.get("why") or "", "style": look.get("morph_style") or "",
                     "window jobs": " ".join(wins[k]["job"] for k in wids), "cloud": sum(wins[k]["cloud_back"] for k in wids),
                     "draft": sum(wins[k]["draft_fallbacks"] for k in wids), "objects": ", ".join(p.get("objects") or [])})
    with open(dest / "passages.csv", "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    md = ["| P | Role | Start | End | Length | Heat | Morphs | On Cloud | Draft fallback | Vibe | Loved chain | Why | Window job | Objects |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['P']} | {r['role']} | {r['start']} | {r['end']} | {r['seconds']} s | {r['heat']} | {r['morphs']} | {r['cloud']} | "
                  f"{r['draft']} | {r['vibe']} | {r['chain']} | {r['why']} | {r['window jobs']} | {r['objects']} |")
    (dest / "passages.md").write_text("# Passages\n\n" + "\n".join(md) + "\n", encoding="utf-8")

    # the tiles: every passage start, and every drop event
    shots = comp.get("shots") or []
    marks = []
    for p in rec["passages"]:
        marks.append({"t": float(p["start"]), "kind": "start", "passage": p["index"]})
    for s in shots:
        ev = s.get("event")
        if not ev:
            continue
        t = float(s["start"])
        near = next((m for m in marks if abs(m["t"] - t) < 0.08), None)
        if near:
            near["kind"] += f" + {ev} event"
        else:
            marks.append({"t": t, "kind": f"{ev} event", "passage": s.get("passage", s.get("song_passage"))})
    marks.sort(key=lambda m: m["t"])

    def objects_at(t: float, pidx: int) -> str:
        shot = next((s for s in shots if float(s["start"]) - 1e-3 <= t < float(s["end"])), None)
        if shot is not None:
            wi = int(shot["window"]) if shot.get("window") is not None and int(shot["window"]) < len(wins) else None
            win = wins[wi] if wi is not None else None
            facts = window_facts(win["job"]) if win and win["job"] else {}
            nouns = list(rec["windows"][wi].get("nouns") or []) if wi is not None else []
            stills = nouns or [noun_of(s) for s in facts.get("stills") or []]
            k = shot.get("shot_in_window")
            wshots = facts.get("shots") or []
            m = None
            if k is not None and int(k) < len(wshots):
                m = wshots[int(k)].get("morph")
            if m is None:
                m = shot.get("morph")
            if m is not None and int(m) + 1 < len(stills):
                return f"{stills[int(m)]} -> {stills[int(m) + 1]}"
        objs = rec["passages"][pidx].get("objects") or []
        return ", ".join(objs[:4]) + (" ..." if len(objs) > 4 else "")

    f_title, f_lab, f_small = font(22, True), font(15, True), font(13)
    cols = 4
    lab_h = 62
    n_rows = -(-len(marks) // cols)
    width = cols * TW + (cols + 1) * GUT
    title_h = 70
    sheet = Image.new("RGB", (width, title_h + n_rows * (TH + lab_h + GUT) + GUT), BG)
    d = ImageDraw.Draw(sheet)
    tiers = {"draft": "Draft", "fast": "Fast Final", "final": "Final", "cloud": "Cloud Final"}
    breathe = rec.get("breathe")
    shape = f"Breathe {float(breathe):.1f}" if breathe not in (None, False, 0, 0.0, "off") else "Breathe off"
    drops = {"auto": "Drops Auto", "max": "Drops Max", "off": "Drops off"}.get(str(rec.get("drop_mode") or "auto"), "Drops Auto")
    chosen = str((rec.get("body") or {}).get("vibe") or "")
    chosen = next(((p.get("look") or {}).get("name") for p in rec["passages"]
                   if (p.get("look") or {}).get("vibe") == chosen and (p.get("look") or {}).get("name")), chosen)
    d.text((GUT, 10), f"{rec['song']['label']} as a whole song on {tiers.get(str(rec.get('tier')), rec.get('tier'))}, "
                      f"{rec.get('aspect')}, {shape}, {drops}{', ' + chosen if chosen else ''}", font=f_title, fill=FG)
    d.text((GUT, 42), f"One tile per passage start and per drop event (the frame 0.3 s after it; orange: an event), labelled time, "
                      f"passage, vibe (loved chain), the objects morphing. From {full.name}", font=f_small, fill=DIM)
    for i, m in enumerate(marks):
        r, c = divmod(i, cols)
        x = GUT + c * (TW + GUT)
        y = title_h + r * (TH + lab_h + GUT)
        sheet.paste(Image.fromarray(frame_at(full, m["t"] + 0.3, TW, TH)), (x, y))
        p = rec["passages"][int(m["passage"])]
        look = p.get("look") or {}
        hot = "event" in m["kind"]
        d.text((x, y + TH + 4), f"{clock(m['t'])}  P{p['index']} {p['role']}{' (main)' if p.get('main') else ''}  {m['kind']}"[:44],
               font=f_lab, fill=HOT if hot else FG)
        d.text((x, y + TH + 24), f"{look.get('name') or look.get('vibe')}{'  · ' + look['preset'] if look.get('preset') else ''}",
               font=f_small, fill=DIM)
        d.text((x, y + TH + 42), objects_at(m["t"] + 0.3, int(m["passage"]))[:52], font=f_small, fill=DIM)
    sheet_path = dest / f"{args.name}_tiles.jpg"
    sheet.save(sheet_path, quality=90)
    print(json.dumps({"video": str(full), "seconds": seconds, "bytes": full.stat().st_size, "small": small, "tiles": str(sheet_path),
                      "tile_count": len(marks), "total": total}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
