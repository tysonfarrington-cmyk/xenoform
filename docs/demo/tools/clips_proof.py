"""The clips proof (docs/SONG.md, Clips; docs/MUSIC_VIDEO_PLAN.md section 8, item 15): a song made whole in your clips
through a desk's own Whole song route, once with Breathe 1.0 and once with Breathe off, stacked plain over Breathe.

    python clips_proof.py make <out dir> --desk http://127.0.0.1:47335 --song <mp3> --pack <clips folder>
                                         [--comfy http://127.0.0.1:8188] [--modes plain,breathe] [--keep <file> ...]
    python clips_proof.py proof <out dir> --jobs <the desk's work/ui/jobs> [--demo <mp4>=<label> ...]
    python clips_proof.py readme <out dir> [--intro <markdown file>]

``make``: the song handed to the desk (``POST /api/analyze``, the desk's own analysis), then for each Shape a whole song
of your clips (``POST /api/song``: Draft, 16:9, the vibe None, Drops Auto, the clips folder), queued only when
ComfyUI's queue is empty (``GET /queue``: nothing running, nothing pending) and followed to its end (``GET
/api/song/<id>``), one at a time; each ``--keep`` file (a library's usage file) is put back exactly as it was after
every Make. ``clips_proof.json`` in the out dir keeps the audio id and each song's id, so a run picks up where it
stopped.

``proof``: from the two songs' records and cuts under ``--jobs``: each cut with the song (``clips_<mode>.mp4``) and a
copy under 25 MiB, a tile sheet a cut (one tile a shot change, up to 60, each with its song time, passage, role and the
clip or the morph it shows; the cut's full path in the heading), the still picture in each (ffmpeg's freezedetect at
noise 0.02 for 0.6 s or longer, the 1 Nov demo's detector, so its 51.5 s with Breathe on and 28.0 s off compare; any
``--demo`` cut is measured the same way), the shot table a passage (seconds, shots, the median shot in beats, the drop
and cut events, the effects) and the totals, the stacked mp4 (plain above Breathe at full width, the song under them, a
cut-rhythm strip under each panel with a playhead) and its copy under 25 MiB, all of it as data in
``clips_proof_summary.json``.

``readme``: README.md naming every file with its full path, the still picture of each cut beside the measured demos,
each cut's shot table and totals and its [taste] lines, opened by an intro written by hand (``--intro``).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

MODES = {  # mode: (label, the Shape)
    "plain": ("Plain (Breathe off, Drops Auto)", {"breathe": False, "drop_mode": "auto"}),
    "breathe": ("Breathe 1.0 (Drops Auto)", {"breathe": True, "drop_mode": "auto"}),
}
MACROS = {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}
TILES_MAX = 60
SMALL_MIB = 24.5


def mmss(t: float) -> str:
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}"


# ------------------------------------------------------------------------------------------------ make


class Keep:
    """Files put back exactly as they were (a library's usage file): their bytes now, written back by ``restore`` (a
    file that was not there is removed again)."""

    def __init__(self, paths: list[Path]):
        self.saved = {p: (p.read_bytes() if p.exists() else None) for p in paths}

    def restore(self) -> None:
        for p, data in self.saved.items():
            if data is None:
                p.unlink(missing_ok=True)
            elif not p.exists() or p.read_bytes() != data:
                p.write_bytes(data)


def queue_idle(comfy: str) -> bool:
    import requests

    try:
        q = requests.get(f"{comfy}/queue", timeout=10).json()
    except Exception:
        return False
    return not q.get("queue_running") and not q.get("queue_pending")


def body(audio_id: str, label: str, pack: Path, shape: dict) -> dict:
    """The desk's own make body for a whole song of your clips (app.js payload, Morph: Your clips, Length: Whole song)."""
    return {"audio_id": audio_id, "song": label, "mode": "simple", "live": True, "quality": "turbo", "quality_tier": "draft",
            "aspect": "16:9", "energy_preset": "dense", "vibe": "none", "idea": "", "brief": "", "morph_source": "clips",
            "own_folder": str(pack), "own_id": "", "morph_count": "auto", "morph_style": "auto", "morph_timing": "smooth",
            "effects": [], "beat_fx": True, "dance_fx": "auto", "foreshadow": "auto", "scene_stills": "off", "backdrop": "auto",
            "end_card": False, "open_weights_only": True, "paid_cloud": False, "cloud_final_ok": False, "stem_orbit": True,
            "seed": 2727, "chain_pins": {}, "macros": dict(MACROS), "vertical_mode": "auto", "performer": 0, **shape}


def make(out: Path, *, desk: str, comfy: str, song: Path, pack: Path, modes: list[str], keep: list[Path]) -> dict:
    import requests

    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "clips_proof.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    guard = Keep(keep)

    def save() -> None:
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")

    if not log.get("audio_id"):
        with open(song, "rb") as f:
            r = requests.post(f"{desk}/api/analyze", files={"file": (song.name, f, "audio/mpeg")}, timeout=900)
        r.raise_for_status()
        log.update({"audio_id": r.json()["audio_id"], "song": song.stem, "song_path": str(song)})
        save()
        print("analysed", song.name, "as", log["audio_id"], flush=True)
    songs = log.setdefault("songs", {})
    for mode in modes:
        row = songs.get(mode) or {}
        if row.get("status") == "done":
            continue
        if not row.get("id"):
            while not queue_idle(comfy):
                print("  the ComfyUI queue is not empty: waiting", flush=True)
                time.sleep(30)
            r = requests.post(f"{desk}/api/song", json={"body": body(log["audio_id"], song.stem, pack, MODES[mode][1])}, timeout=900)
            if r.status_code != 200:
                raise SystemExit(f"{mode}: the desk refused the song: {r.status_code} {r.text[:400]}")
            v = r.json()
            row = {"id": v["id"], "line": v.get("line"), "queued": time.time(), "label": MODES[mode][0]}
            songs[mode] = row
            save()
            print(mode, "queued as", v["id"], "-", v.get("line"), flush=True)
        last = ""
        while True:
            time.sleep(20)
            try:
                v = requests.get(f"{desk}/api/song/{row['id']}", timeout=60).json()
            except Exception as exc:
                print("  poll:", exc, flush=True)
                continue
            run = v.get("running") or {}
            line = f"  {v.get('status')} {v.get('done')}/{v.get('of')} {run.get('detail') or ''} {round(float(run.get('progress') or 0) * 100)}%"
            if line != last:
                print(line, flush=True)
                last = line
            if v.get("status") in ("done", "failed", "stopped"):
                break
        guard.restore()
        row.update({"status": v.get("status"), "finished": time.time(), "minutes": round((time.time() - row["queued"]) / 60.0, 1)})
        save()
        print(mode, v.get("status"), "in", row["minutes"], "min", flush=True)
    return log


# ------------------------------------------------------------------------------------------------ proof


def still_picture(mp4: Path) -> dict:
    """Near-still picture by ffmpeg's freezedetect (noise 0.02, 0.6 s or longer: the 1 Nov demo's detector): the seconds
    in all and each run."""
    from xenoform import song_assemble

    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-map", "0:v:0", "-vf", "freezedetect=n=0.02:d=0.6",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", err)]
    length = float(song_assemble.probe(mp4)["picture_s"])
    runs = [(a, ends[k] if k < len(ends) else length) for k, a in enumerate(starts)]
    return {"seconds": round(sum(b - a for a, b in runs), 1), "runs": [[round(a, 2), round(b, 2)] for a, b in runs],
            "length_s": round(length, 2)}


def _passages(rec: dict) -> dict:
    """The song's passages by the plan passage index a whole clips window's shots carry."""
    return {int(p.get("plan_passage", p["index"])): p for p in rec["passages"]}


def what(s: dict) -> str:
    m = s.get("clip_morph") if isinstance(s.get("clip_morph"), dict) else None
    if m:
        return f"morph: {m.get('from')} into {m.get('to')}"
    return f"{s.get('label') or s.get('source') or 'clip'}" + (" (carried on)" if s.get("cont") else "")


def changes(comp: dict) -> list[int]:
    """The shots that change the picture: every shot but a film carried on into the next passage."""
    return [i for i, s in enumerate(comp.get("shots") or []) if i == 0 or not s.get("cont")]


def tile_sheet(mp4: Path, comp: dict, rec: dict, dest: Path, heading: str) -> int:
    from PIL import Image, ImageDraw

    from song_proof import COLS, LABEL_H, TILE, _font, grab

    shots = comp.get("shots") or []
    idx = changes(comp)
    if len(idx) > TILES_MAX:
        idx = [idx[int(round(k * (len(idx) - 1) / (TILES_MAX - 1)))] for k in range(TILES_MAX)]
    by = _passages(rec)
    rows = math.ceil(len(idx) / COLS)
    head_h = 48
    img = Image.new("RGB", (TILE[0] * COLS, head_h + (TILE[1] + LABEL_H) * rows), (12, 12, 16))
    d = ImageDraw.Draw(img)
    d.text((12, 12), heading, font=_font(17, 600), fill=(240, 238, 250))
    big, small = _font(14, 600), _font(12, 400)
    for k, i in enumerate(idx):
        s = shots[i]
        x, y = (k % COLS) * TILE[0], head_h + (k // COLS) * (TILE[1] + LABEL_H)
        start, end = float(s["start"]), float(s["end"])
        img.paste(grab(mp4, start + min(0.5, 0.4 * (end - start))), (x, y))
        p = by.get(int(s.get("passage") or 0)) or {}
        role = str(s.get("section") or p.get("role") or "")
        event = {"drop": " · opens a drop", "cut": " · a cut to a fresh film"}.get(str(s.get("event") or ""), "")
        d.text((x + 8, y + TILE[1] + 4), f"{mmss(start)} · passage {int(p.get('index', 0)) + 1} · {role}{event}"[:56], font=big,
               fill=(245, 243, 255))
        d.text((x + 8, y + TILE[1] + 24), what(s)[:60], font=small, fill=(200, 196, 230))
        d.text((x + 8, y + TILE[1] + 42), f"shot {i + 1}, {end - start:.2f} s" + (f", rests {s['rest']} beats on film" if s.get("rest") else ""),
               font=small, fill=(160, 158, 180))
    img.save(dest, quality=88)
    return len(idx)


def table(comp: dict, rec: dict, period: float) -> tuple[list[dict], dict]:
    """The shot table a passage (seconds, shots, the median shot in beats, the drop and cut events, the effects) and the
    totals over the cut."""
    shots = comp.get("shots") or []
    by = _passages(rec)
    rows: dict[int, dict] = {}
    for i, s in enumerate(shots):
        p = by.get(int(s.get("passage") or 0)) or {"index": 0, "role": s.get("section"), "start": s["start"], "end": s["end"]}
        r = rows.setdefault(int(p["index"]), {"passage": int(p["index"]) + 1, "role": p["role"], "start": round(float(p["start"]), 2),
                                             "end": round(float(p["end"]), 2), "shots": 0, "clips": 0, "morphs": 0, "_beats": [],
                                             "drops": 0, "cuts": 0, "rests": 0, "effects": {}})
        if not (i and s.get("cont")):  # a film carried on into this passage is the same picture: no change, no new shot
            r["shots"] += 1
            r["clips"] += int(bool(s.get("own")))
            r["morphs"] += int(bool(s.get("clip_morph")))
        r["_beats"].append((float(s["end"]) - float(s["start"])) / period)
        r["drops"] += int(s.get("event") == "drop")
        r["cuts"] += int(s.get("event") == "cut")
        r["rests"] += int(bool(s.get("rest")))
        for n in s.get("fx_names") or []:
            r["effects"][n] = r["effects"].get(n, 0) + 1
    out = []
    for r in sorted(rows.values(), key=lambda x: x["passage"]):
        beats = sorted(r.pop("_beats"))
        r["seconds"] = round(r["end"] - r["start"], 1)
        r["median_beats"] = round(beats[len(beats) // 2], 1) if beats else 0.0
        r["effects"] = ", ".join(f"{k} x{v}" for k, v in sorted(r["effects"].items())) or "none"
        out.append(r)
    lengths = [(float(s["end"]) - float(s["start"])) / period for i, s in enumerate(shots) if i == 0 or not s.get("cont")]
    totals = {"shots": len(changes(comp)), "clips": sum(r["clips"] for r in out), "morphs": sum(r["morphs"] for r in out),
              "median_beats": round(statistics.median(lengths), 1) if lengths else 0.0,
              "drops": sum(r["drops"] for r in out), "cuts": sum(r["cuts"] for r in out), "rests": sum(r["rests"] for r in out),
              "hard_cuts": sum(1 for s in shots if s.get("cut_in") and s.get("own")),
              "under_a_bar": sum(1 for b in lengths if b < 3.5)}
    return out, totals


def proof(out: Path, *, jobs: Path, demos: list[tuple[Path, str]]) -> dict:
    from xenoform import song_assemble, song_run

    from pacing_proof import rhythm_strip, stacked_video

    log = json.loads((out / "clips_proof.json").read_text(encoding="utf-8"))
    made: dict[str, dict] = {}
    for mode, row in (log.get("songs") or {}).items():
        if row.get("status") != "done":
            continue
        folder = jobs / row["id"]
        rec = song_run.load(folder)
        comp = json.loads((folder / "simple" / "simple.json").read_text(encoding="utf-8"))
        window = rec["windows"][0]
        cut_rec = json.loads((jobs / window["job_id"] / "simple" / "simple.json").read_text(encoding="utf-8"))
        name = f"clips_{mode}"
        mp4 = out / f"{name}.mp4"
        shutil.copyfile(folder / "xenoform.mp4", mp4)
        info = song_assemble.probe(mp4)
        small = out / f"{name}_small.mp4"
        song_assemble.small_copy(mp4, small, max_mib=SMALL_MIB, height=min(720, int(info["height"])))
        beats = sorted(float(b) for b in comp.get("beats") or [])
        gaps = sorted(y - x for x, y in zip(beats, beats[1:]) if y > x)
        period = gaps[len(gaps) // 2] if gaps else 0.5
        rows, totals = table(comp, rec, period)
        heading = f"{mp4}  ·  {MODES[mode][0]}  ·  {(rec.get('plan') or {}).get('line') or ''}"
        tiles = tile_sheet(mp4, comp, rec, out / f"{name}_sheet.jpg", heading)
        still = still_picture(mp4)
        rhythm_strip(comp, float(info["picture_s"]), out / f"{name}_strip.png")
        a = rec.get("assembly") or {}
        made[mode] = {"name": name, "label": MODES[mode][0], "song_id": rec["id"], "job": window.get("job_id"),
                      "line": (rec.get("plan") or {}).get("line"), "cut_line": (cut_rec.get("pacing") or {}).get("line"),
                      "seconds": round(float(info["picture_s"]), 2), "size": [info["width"], info["height"]],
                      "mib": round(mp4.stat().st_size / 1048576, 1), "small_mib": round(small.stat().st_size / 1048576, 1),
                      "tiles": tiles, "still": still, "table": rows, "totals": totals, "taste": (cut_rec.get("taste") or {}).get("lines"),
                      "title": a.get("title"), "loudness": a.get("loudness"), "tame": a.get("tame"), "qa": a.get("qa"),
                      "render_min": round(sum(float(w.get("took_s") or 0.0) for w in rec["windows"]) / 60.0, 1),
                      "assembly_min": round(float(a.get("took_s") or 0.0) / 60.0, 1), "morphs": int((rec.get("plan") or {}).get("morphs") or 0)}
        print(name, made[mode]["line"], f"still {still['seconds']} s", flush=True)
    if {"plain", "breathe"} <= set(made):
        length = min(made["plain"]["seconds"], made["breathe"]["seconds"])
        stacked = out / "clips_plain_over_breathe.mp4"
        stacked_video(out / "clips_plain.mp4", out / "clips_plain_strip.png", out / "clips_breathe.mp4", out / "clips_breathe_strip.png",
                      stacked, length, labels=("Plain (Breathe off)", "Breathe 1.0"))  # no colon: drawtext splits on it
        song_assemble.small_copy(stacked, out / "clips_plain_over_breathe_small.mp4", max_mib=SMALL_MIB, height=720)
    measured = []
    for mp4, label in demos:
        measured.append({"file": str(mp4), "label": label, "still": still_picture(mp4)})
        print("measured", label, measured[-1]["still"]["seconds"], "s", flush=True)
    summary = {"songs": made, "demos": measured, "log": log}
    (out / "clips_proof_summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    return summary


def _table_md(rows: list[dict]) -> list[str]:
    out = ["| Passage | Role | Song time | Seconds | Shots | Clips | Morphs | Median shot (beats) | Events | Rests | Effects |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        events = ", ".join(x for x in (f"{r['drops']} drop" if r["drops"] else "", f"{r['cuts']} cut" if r["cuts"] else "") if x) or "none"
        out.append(f"| {r['passage']} | {r['role']} | {mmss(r['start'])} to {mmss(r['end'])} | {r['seconds']} | {r['shots']} | "
                   f"{r['clips']} | {r['morphs']} | {r['median_beats']} | {events} | {r['rests']} | {r['effects']} |")
    return out


def readme(out: Path, intro: Path | None = None) -> Path:
    """README.md in the out dir: every file with its full path, the still picture of each cut beside the demo's, each
    cut's shot table and totals, its [taste] lines; an intro from ``intro`` (markdown) when given."""
    s = json.loads((out / "clips_proof_summary.json").read_text(encoding="utf-8"))
    songs = s.get("songs") or {}
    lines = ["# Clips with the pacing engine: ZedsDead v2 as a whole song in the free film pack", ""]
    if intro and intro.exists():
        lines += [intro.read_text(encoding="utf-8").strip(), ""]
    lines += ["## The files", ""]
    stacked = out / "clips_plain_over_breathe.mp4"
    for f in [stacked, out / "clips_plain_over_breathe_small.mp4"]:
        if f.exists():
            lines.append(f"- `{f}` ({f.stat().st_size / 1048576:.1f} MiB): " + ("plain above Breathe at full width, the song under "
                         "them, a cut-rhythm strip under each panel (a tick at every shot change in its passage's colour, a white "
                         "mark at each drop's opening cut, a playhead)" if f == stacked else "the same, under 25 MiB to share"))
    for mode in ("plain", "breathe"):
        m = songs.get(mode)
        if not m:
            continue
        for suffix, what_ in (("", "the cut with the song (the title on the last hit, -16 LUFS)"), ("_small", "the same under 25 MiB"),
                              ("_sheet", f"the tile sheet: a tile at each of {m['tiles']} shot changes, with its song time, passage, "
                                         "role and the clip or morph it shows; the cut's full path in the heading"),
                              ("_strip", "its cut-rhythm strip")):
            ext = ".jpg" if suffix == "_sheet" else ".png" if suffix == "_strip" else ".mp4"
            f = out / f"{m['name']}{suffix}{ext}"
            if f.exists():
                lines.append(f"- `{f}` ({f.stat().st_size / 1048576:.1f} MiB): {m['label']}: {what_}")
    for f in (out / "clips_proof.json", out / "clips_proof_summary.json"):
        lines.append(f"- `{f}`: " + ("the run: the audio id and each song's id" if f.name == "clips_proof.json" else
                                     "everything below as data, the frozen-picture runs too"))
    lines += ["", "## Still picture", "",
              "Near-still picture by ffmpeg's freezedetect (noise 0.02, 0.6 s or longer), the detector the 1 Nov demo used:", "",
              "| Cut | Still picture | Runs | Length |", "|---|---|---|---|"]
    for mode in ("plain", "breathe"):
        m = songs.get(mode)
        if m:
            lines.append(f"| {m['label']} (this proof) | {m['still']['seconds']} s | {len(m['still']['runs'])} | {mmss(m['still']['length_s'])} |")
    for d in s.get("demos") or []:
        runs = d["still"]["runs"]
        tail = runs[-1][1] - runs[-1][0] if runs and abs(runs[-1][1] - d["still"]["length_s"]) < 0.05 else 0.0
        note = f" ({d['still']['seconds'] - tail:.1f} s without the {tail:.1f} s its last run holds into the file's end)" if tail else ""
        lines.append(f"| {d['label']} | {d['still']['seconds']} s{note} | {len(runs)} | {mmss(d['still']['length_s'])} |")
    for mode in ("plain", "breathe"):
        m = songs.get(mode)
        if not m:
            continue
        t = m["totals"]
        qa = m.get("qa") or {}
        loud = m.get("loudness") or {}
        lines += ["", f"## {m['label']}", "",
                  f"The song's plan: {m['line']}. The cut's own line: {m.get('cut_line')}.", "",
                  *_table_md(m["table"]), "",
                  f"Totals: {t['shots']} shots ({t['clips']} clips, {t['morphs']} morphs), the median shot {t['median_beats']} beats, "
                  f"{t['drops']} drop runs opening on a cut to a fresh film, {t['cuts']} more {'cut' if t['cuts'] == 1 else 'cuts'} "
                  f"at a long run's eight-bar event, {t['hard_cuts']} hard cuts in all, {t['rests']} shots carrying a rest (film "
                  f"playing), {t['under_a_bar']} shots under a bar (the hot drops' half-bar entries). {m['morphs']} morphs on Draft "
                  f"(those rendered for the first try answered by the morph cache): {m['render_min']} min for the Make, "
                  f"{m['assembly_min']} min laying it together. Flash frames {qa.get('flash_frames')}, the worst 8 bars "
                  f"{qa.get('max_flash_8_bars')}; {loud.get('lufs')} LUFS. Title: {(m.get('title') or {}).get('text')} at "
                  f"{mmss((m.get('title') or {}).get('at') or 0)}."]
        if m.get("taste"):
            lines += ["", "The taste file on this cut:", ""] + [f"- {x}" for x in m["taste"]]
    path = out / "README.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("make", "proof", "readme"))
    ap.add_argument("out", type=Path)
    ap.add_argument("--desk", default="http://127.0.0.1:47335")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--song", type=Path)
    ap.add_argument("--pack", type=Path)
    ap.add_argument("--modes", default="plain,breathe")
    ap.add_argument("--keep", type=Path, action="append", default=[])
    ap.add_argument("--jobs", type=Path)
    ap.add_argument("--demo", action="append", default=[], help="<mp4>=<label>: an older cut to measure the same way")
    ap.add_argument("--intro", type=Path, help="readme: a markdown file to open the README with")
    a = ap.parse_args()
    if a.what == "make":
        make(a.out, desk=a.desk, comfy=a.comfy, song=a.song, pack=a.pack, modes=a.modes.split(","), keep=a.keep)
    elif a.what == "proof":
        demos = [(Path(x.split("=", 1)[0]), x.split("=", 1)[1] if "=" in x else Path(x).stem) for x in a.demo]
        proof(a.out, jobs=a.jobs, demos=demos)
    else:
        print(readme(a.out, a.intro))


if __name__ == "__main__":
    main()
