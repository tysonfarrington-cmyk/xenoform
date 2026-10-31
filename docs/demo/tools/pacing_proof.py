"""The pacing proof (docs/MUSIC_VIDEO_PLAN.md section 3, its acceptance) on the bundled Glitch Out.

    python pacing_proof.py table <out dir> [--no-flash] [--vibe cosmic] [--stills <copy of a grown library>]
    python pacing_proof.py sheets <out dir> --desk http://127.0.0.1:47327 [--vibe bioluminescent] [--idea underwater] [--starts 105,0]
                                            [--modes today,plain,breathe] [--stills <the desk's XENO_STILLS>]
    python pacing_proof.py stacked <out dir> --desk http://127.0.0.1:47327 [--windows 90:90,30:90,0:30] [--vibe ...] [--idea ...]
                                             [--stills <the desk's XENO_STILLS>]

``table``: the whole song cut three ways through the Make's own ``dense.run_simple`` on the mock engine (no GPU, no
model: each morph a cross-fade of its two stills, the beat FX, kinds, looks and the tame all real): today's cut
(Breathe off, Drops off: the mainline as it was), a plain Make now (Breathe off, Drops auto: the desk's default) and
Breathe (on, Drops auto). Per passage role it prints what each cut does beside the profile table's numbers (looks a
minute, morphs per 8 bars, the timing, style and effect mix, the share of handoffs given a boundary kind, rests, drop
entries) and, unless --no-flash, the flash frames per 8 bars on the composed cut by deflash's own test. Writes
plan_table.md and plan_table.json (with every plan's passages and shots) in <out dir>.

``sheets``: local Draft Makes through a desk (free; each waits for an idle ComfyUI queue and never sends a Final or a
Cloud tier) of today's cut, a plain Make now and Breathe on 30 s windows of the song, a timed tile sheet of each (a
frame every half second), the cuts side by side with the song, and the plan lines the desk reported (sheets.json).

``stacked`` (round two, Tys 31 Oct: Breathe "may be too subtle"): local Draft Makes at 16:9 of a plain Make (Breathe
off, Drops auto) and Breathe (on), each window stacked plain above Breathe at full width with the song, a cut-rhythm
strip under each panel (a tick at every shot change in the colour of the passage's role, a white mark at each drop
event, a playhead), and the looks a minute, shots, holds and rests of every passage of both cuts (stacked.json).

A look (montage_rules.md 5.4) is a bundle held for whole bars: here a run of shots with one morph style, one timing,
one effect and one colour look (one vibe a Make, so the vibe does not change).
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SONG = ROOT / "examples" / "songs" / "glitch_out.mp3"
FEATURES = ROOT / "examples" / "songs" / "glitch-out.features.json"
MODES = {  # name: (label, body keys)
    "today": ("Today (Breathe off, Drops off)", {"breathe": False, "drop_mode": "off"}),
    "plain": ("Plain Make now (Breathe off, Drops auto)", {"breathe": False, "drop_mode": "auto"}),
    "breathe": ("Breathe (on: 1.0, Drops auto)", {"breathe": True, "drop_mode": "auto"}),
}
GROUPS = ("intro", "groove", "build", "drop", "drop_late", "release", "outro")
GROUP_OF = {"calm": "groove", "sustain": "groove", "breakdown": "release"}
# the profile table (plan section 3) and the montage's measures (montage_rules.md 5.3 and 5.4) a role is held to
PROFILE = {
    "intro": {"looks": "4", "morphs": "6.6", "timing": "smooth", "styles": "bloom, melt", "effect": "none (feedback)",
              "kinds": "none", "flash": "0"},
    "groove": {"looks": "10-11", "morphs": "9.3", "timing": "beat", "styles": "melt, bloom",
               "effect": "none; 1 passage in 3 slitscan or dither", "kinds": "36 %, wipes <= 1/4", "flash": "low (25)"},
    "build": {"looks": "10-11", "morphs": "9.1", "timing": "beat, snap last bar", "styles": "fold, bloom", "effect": "dither",
              "kinds": "none", "flash": "rising (39-43)"},
    "drop": {"looks": "10-11", "morphs": "9.8", "timing": "snap (beat under heat 0.5)", "styles": "shatter, spin, bloom",
             "effect": "dither, then feedback", "kinds": "42 %, strobe only at heat 1", "flash": "capped (39-43)"},
    "drop_late": {"looks": "10-11", "morphs": "9.8", "timing": "beat", "styles": "melt, spin", "effect": "one",
                  "kinds": "36 %", "flash": "capped"},
    "release": {"looks": "10-11", "morphs": "9.2", "timing": "beat, smooth", "styles": "melt", "effect": "smear or dither",
                "kinds": "36 %", "flash": "capped"},
    "outro": {"looks": "4", "morphs": "8.9", "timing": "smooth", "styles": "melt", "effect": "none", "kinds": "none",
              "flash": "none (5)"},
}
FLASH_CAP = 45  # the acceptance: flash frames per 8 bars after the tame under 45 everywhere, 0 in the intro
MACROS = {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def _features() -> dict:
    return json.loads(FEATURES.read_text(encoding="utf-8"))


class Usage:
    """A stills library's usage.json, put back as it was before every Make (``--stills`` is a copy of a grown library:
    every cut picks from the same state, and the copy is all that is ticked)."""

    def __init__(self, folder: Path | None):
        self.path = Path(folder) / "usage.json" if folder else None
        self.saved = self.path.read_bytes() if self.path and self.path.exists() else None

    def reset(self) -> None:
        if self.path is None:
            return
        if self.saved is None:
            self.path.unlink(missing_ok=True)
        else:
            self.path.write_bytes(self.saved)


def _period(beats: list[float]) -> float:
    gaps = sorted(b - a for a, b in zip(beats, beats[1:]) if b > a)
    return gaps[len(gaps) // 2] if gaps else 0.5


# ------------------------------------------------------------------------------------------------ the table


def make(mode: str, work: Path, *, flash: bool, vibe: str) -> dict:
    """One whole-song Make of ``mode`` on the mock engine: the shots and switches the compositor got, the record, and
    (with ``flash``) the composed cut."""
    from xenoform import beatfx, dense, guardrails

    feats = _features()
    directed = {"duration": float(feats["duration"]), "beats": [float(b) for b in feats["beats"]],
                "sections": list(feats["sections"])}
    body = {"vibe": vibe, "aspect": "9:16", "quality_tier": "draft", "energy_preset": "dense", "mode": "simple", "seed": 2727,
            "morph_count": "auto", "morph_style": "auto", "morph_timing": "smooth", "effects": [], "dance_fx": "auto",
            "foreshadow": "auto", "beat_fx": True, "stem_orbit": True, "macros": dict(MACROS), **MODES[mode][1]}
    guarded, report = guardrails.apply(body, duration=directed["duration"], beats=directed["beats"])
    job = work / mode
    job.mkdir(parents=True, exist_ok=True)
    seen: list[dict] = []
    real = beatfx.compose

    def spy(clips, shots, audio, out, **kw):
        seen.append({"shots": copy.deepcopy(shots), "kw": {k: copy.deepcopy(v) for k, v in kw.items()
                                                           if k in ("transitions", "boundary_fx", "dance_fx", "effects",
                                                                    "foreshadow", "tame", "fps")}})
        if flash:
            return real(clips, shots, audio, out, **kw)
        Path(out).write_bytes(b"")
        return {"frames": sum(int(s["frames"]) for s in shots), "seconds": 1.0, "size": "540x960", "aspect": kw.get("aspect"),
                "fx": True, "overlay": False, "centres": [], "fps": kw.get("fps") or 24, "look": {"dance_fx": kw.get("dance_fx")},
                "transitions": [], "boundary_fx": {}, "foreshadow": {}, "effects": []}

    import xenoform.cloud_morph as cm
    saved = (beatfx.compose, cm._mock_clips)
    beatfx.compose = spy
    if not flash:  # the plan alone: no clip is looked at
        def fake_clips(shots, stills, work_dir, w, h):
            out = []
            for i in range(len(shots)):
                p = Path(work_dir) / f"m{i:02d}.mp4"
                p.write_bytes(b"clip")
                out.append(p)
            return out
        cm._mock_clips = fake_clips
    t0 = time.perf_counter()
    try:
        info = dense.run_simple(directed, SONG, job / "xenoform.mp4", job, {}, dict(guarded), lambda *a: None, engine="mock")
    finally:
        beatfx.compose, cm._mock_clips = saved
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    return {"mode": mode, "guard": sorted({x["id"] for x in report["applied"]}), "info": {k: info.get(k) for k in ("plan_name",)},
            "compose": seen[-1], "record": rec, "mp4": str(job / "xenoform.mp4") if flash else "",
            "seconds": round(time.perf_counter() - t0, 1), "beats": directed["beats"], "duration": directed["duration"]}


def _shot_rows(made: dict) -> list[dict]:
    """Each shot as the table reads it: its role group, span, style, timing, effect, colour look, kind and rest."""
    rec, kw = made["record"], made["compose"]["kw"]
    shots = made["compose"]["shots"]
    styles = rec.get("morph_styles") or []
    cut_timing = str(rec.get("morph_timing") or "smooth")
    kinds = kw.get("boundary_fx") or []
    prem = kw.get("transitions") or []
    rows = []
    for i, s in enumerate(shots):
        role = str(s.get("section") or "")
        m = int(s.get("morph", s.get("clip", i)) or 0)
        fx = s["fx_names"] if "fx_names" in s else list(kw.get("effects") or [])
        bfx = kinds[i] if i < len(kinds) else None
        rows.append({
            "i": i, "role": role, "group": GROUP_OF.get(role, role), "start": float(s["start"]), "end": float(s["end"]),
            "style": styles[m] if m < len(styles) else "?", "timing": str((s.get("timing") or {}).get("mode") or cut_timing),
            "fx": ",".join(fx) or "none", "look": str(s.get("dance_fx") or kw.get("dance_fx") or ""),
            "kind": (bfx or {}).get("kind") if isinstance(bfx, dict) else None,
            "premium": (prem[i] or {}).get("kind") if i < len(prem) and isinstance(prem[i], dict) else None,
            "rest": int(s.get("rest") or 0), "event": s.get("event"), "heat": s.get("heat"), "drop_run": s.get("drop_run"),
            "passage": s.get("passage"), "chaos": s.get("chaos"), "fx_intensity": s.get("fx_intensity"),
        })
    return rows


def _flash_flags(mp4: str):
    from xenoform import deflash, post_qa

    return deflash.flash_frames(post_qa._grey_lumas(mp4))


def measure(made: dict) -> dict:
    """The table's numbers for one cut: per role group and for the whole song."""
    rows = _shot_rows(made)
    period = _period(made["beats"])
    bar8 = 32 * period
    fps = float(made["compose"]["kw"].get("fps") or 24)
    flags = _flash_flags(made["mp4"]) if made.get("mp4") and Path(made["mp4"]).exists() and Path(made["mp4"]).stat().st_size else None
    out: dict[str, dict] = {}
    groups = [g for g in GROUPS if any(r["group"] == g for r in rows)] + sorted({r["group"] for r in rows} - set(GROUPS))
    looks_at = [i for i, r in enumerate(rows) if i == 0 or (r["style"], r["timing"], r["fx"], r["look"]) !=
                (rows[i - 1]["style"], rows[i - 1]["timing"], rows[i - 1]["fx"], rows[i - 1]["look"])]
    windows = []
    if flags is not None:
        w = max(1, int(round(bar8 * fps)))
        windows = [(k * w / fps, min(len(flags), (k + 1) * w) / fps, int(flags[k * w:(k + 1) * w].sum()))
                   for k in range((len(flags) + w - 1) // w)]

    def group_at(t: float) -> str:
        r = next((r for r in rows if r["start"] <= t < r["end"]), rows[-1])
        return r["group"]

    for g in groups + ["all"]:
        mine = [r for r in rows if g == "all" or r["group"] == g]
        secs = sum(r["end"] - r["start"] for r in mine)
        if secs <= 0:
            continue
        handoffs = [r for r in mine if r["i"] > 0]
        timing = Counter()
        for r in mine:
            timing[r["timing"]] += r["end"] - r["start"]
        row = {
            "seconds": round(secs, 1), "shots": len(mine),
            "morphs_per_8_bars": round(len(mine) / (secs / bar8), 2),
            "looks_per_min": round(sum(1 for i in looks_at if g == "all" or rows[i]["group"] == g) / (secs / 60.0), 1),
            "median_shot_beats": round(statistics.median((r["end"] - r["start"]) / period for r in mine), 1),
            "timing": {k: round(100 * v / secs) for k, v in timing.most_common()},
            "styles": {k: round(100 * v / len(mine)) for k, v in Counter(r["style"] for r in mine).most_common()},
            "effects": {k: round(100 * v / len(mine)) for k, v in Counter(r["fx"] for r in mine).most_common()},
            "looks": dict(Counter(r["look"] for r in mine).most_common()),
            "kinds_share": round(100 * sum(1 for r in handoffs if r["kind"]) / max(1, len(handoffs))),
            "kinds": dict(Counter(r["kind"] for r in handoffs if r["kind"]).most_common()),
            "premium": dict(Counter(r["premium"] for r in mine if r["premium"]).most_common()),
            "rests": sum(1 for r in mine if r["rest"]), "rest_beats": sum(r["rest"] for r in mine),
            "drop_entries": sum(1 for r in mine if r["event"] == "drop"),
        }
        if flags is not None:
            frames = [k for k in range(len(flags)) if flags[k] and (g == "all" or group_at(k / fps) == g)]
            row["flash_frames"] = len(frames)
            row["flash_per_8_bars"] = round(len(frames) / (secs / bar8), 1)
            mine_w = [n for (a, b, n) in windows if g == "all" or group_at((a + b) / 2) == g]
            row["flash_max_8_bars"] = max(mine_w) if mine_w else 0
        out[g] = row
    # the wipes against all handoffs and the strobes, the plan's rules
    kinds_all = Counter(r["kind"] for r in rows[1:] if r["kind"])
    out["all"]["wipe_share_of_handoffs"] = round(100 * kinds_all.get("wipe", 0) / max(1, len(rows) - 1), 1)
    out["all"]["strobes"] = kinds_all.get("strobe", 0)
    out["all"]["same_kind_twice"] = sum(1 for a, b in zip(rows[1:], rows[2:]) if a["kind"] and a["kind"] == b["kind"])
    return {"groups": out, "rows": rows, "period": period, "bar8_s": round(bar8, 3),
            "windows": [{"start": round(a, 2), "end": round(b, 2), "flash": n} for a, b, n in windows]}


def _mix(d: dict, top: int = 3) -> str:
    return ", ".join(f"{k} {v}" for k, v in list(d.items())[:top]) or "-"


def table(out_dir: Path, *, flash: bool, vibe: str, stills: Path | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    # a copy of a grown library (a whole song needs a pool past its morph count), else the shipped pools alone
    os.environ["XENO_STILLS"] = str(stills) if stills else tempfile.mkdtemp(prefix="xeno_proof_stills_")
    usage = Usage(stills)
    work = Path(tempfile.mkdtemp(prefix="xeno_proof_"))
    made, measured = {}, {}
    for mode in MODES:
        usage.reset()
        print(f"{mode}: making the whole song on the mock engine{' with the compositor' if flash else ''} ...", flush=True)
        made[mode] = make(mode, work, flash=flash, vibe=vibe)
        measured[mode] = measure(made[mode])
        if flash and made[mode]["mp4"]:
            shutil.copy2(made[mode]["mp4"], out_dir / f"mock_whole_{mode}.mp4")
        print(f"  {made[mode]['record'].get('plan_name')!r}, {len(made[mode]['compose']['shots'])} shots, "
              f"{made[mode]['seconds']} s", flush=True)
    lines = [f"# Glitch Out, the whole song: the plan against the profile table",
             "",
             f"The Make's own `dense.run_simple` on the mock engine (each morph a cross-fade of its two stills; the beat FX, "
             f"kinds, looks and the tame are the real ones), vibe {vibe}, seed 2727, Forms auto, Timing Smooth, Morph Auto, "
             f"no effects, the Look on Auto, knobs at their defaults; 90 BPM, a bar 2.67 s, 8 bars "
             f"{measured['today']['bar8_s']} s. Made by `docs/demo/tools/pacing_proof.py table`.",
             ""]
    for mode, (label, keys) in MODES.items():
        rec = made[mode]["record"]
        pac = rec.get("pacing") or {}
        lines += [f"## {label}", "", f"Plan `{rec.get('plan_name')}`, {len(made[mode]['compose']['shots'])} shots; guardrail "
                  f"{', '.join(made[mode]['guard']) or 'none'}; the Make's line: {pac.get('line') or '(none: no passages)'}", ""]
        head = "| role | seconds | shots | looks/min | morphs/8 bars | median shot (beats) | timing (% of s) | styles (% of shots) | effects | handoffs with a kind | rests | entries |"
        if flash:
            head += " flash/8 bars (max) |"
        lines += [head, "|" + "---|" * (head.count("|") - 1)]
        for g, row in measured[mode]["groups"].items():
            cells = [g, row["seconds"], row["shots"], row["looks_per_min"], row["morphs_per_8_bars"], row["median_shot_beats"],
                     _mix(row["timing"]), _mix(row["styles"]), _mix(row["effects"], 2),
                     f"{row['kinds_share']} % ({_mix(row['kinds'], 3)})", row["rests"] or "-", row["drop_entries"] or "-"]
            if flash:
                cells.append(f"{row.get('flash_per_8_bars', '-')} ({row.get('flash_max_8_bars', '-')})")
            lines.append("| " + " | ".join(str(c) for c in cells) + " |")
        a = measured[mode]["groups"]["all"]
        lines += ["", f"Wipes {a['wipe_share_of_handoffs']} % of all handoffs, {a['strobes']} strobes, "
                  f"{a['same_kind_twice']} kinds twice in a row; premium transitions {_mix(a['premium'], 4)}.", ""]
        if pac.get("passages"):
            lines += ["Passages: " + "; ".join(
                f"{p['role']} {mmss(p['start'])}-{mmss(p['end'])}" + (f" heat {p['heat']}" if p.get("heat") is not None else "")
                for p in pac["passages"]), ""]
    lines += ["## The profile table (plan section 3) and the montage's measures", "",
              "| role | looks/min | morphs/8 bars | timing | styles | effect | handoff kinds | flash/8 bars |",
              "|---|---|---|---|---|---|---|---|"]
    for g, p in PROFILE.items():
        lines.append(f"| {g} | {p['looks']} | {p['morphs']} | {p['timing']} | {p['styles']} | {p['effect']} | {p['kinds']} | {p['flash']} |")
    if flash:
        b = measured["breathe"]
        worst = max((w["flash"] for w in b["windows"]), default=0)
        intro = b["groups"].get("intro", {}).get("flash_frames", 0)
        lines += ["", f"Flash after the tame (Breathe): the worst 8 bars hold {worst} flash frames (under {FLASH_CAP}: "
                  f"{'yes' if worst < FLASH_CAP else 'NO'}); the intro {intro} (0: {'yes' if intro == 0 else 'NO'})."]
    text = "\n".join(lines) + "\n"
    (out_dir / "plan_table.md").write_text(text, encoding="utf-8")
    dump = {mode: {"label": MODES[mode][0], "plan_name": made[mode]["record"].get("plan_name"), "guard": made[mode]["guard"],
                   "pacing": made[mode]["record"].get("pacing"), "groups": measured[mode]["groups"],
                   "windows": measured[mode]["windows"], "shots": measured[mode]["rows"]} for mode in MODES}
    (out_dir / "plan_table.json").write_text(json.dumps(dump, indent=1), encoding="utf-8")
    print(text)
    usage.reset()
    shutil.rmtree(work, ignore_errors=True)
    return dump


# ------------------------------------------------------------------------------------------------ the sheets


def _queue_idle(comfy: str) -> bool:
    import requests

    try:
        q = requests.get(f"{comfy}/queue", timeout=10).json()
    except Exception:
        return False
    return not q.get("queue_running") and not q.get("queue_pending")


def _sheet(mp4: Path, dest: Path, step: float = 0.5, cols: int = 10, w: int = 144, h: int = 256) -> None:
    font = "C\\:/Windows/Fonts/segoeuib.ttf"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf",
                    f"fps=1/{step},scale={w}:{h},drawtext=fontfile='{font}':text='%{{pts\\:hms}}':x=4:y=4:fontsize=13:"
                    f"fontcolor=yellow:box=1:boxcolor=black@0.6,tile={cols}x{int(30 / step / cols + 0.999)}",
                    "-frames:v", "1", "-q:v", "3", str(dest)], check=False)


def _side_by_side(cuts: list[Path], dest: Path, labels: list[str]) -> None:
    """The cuts next to each other at 360x640, each named, with the first one's sound."""
    font = "C\\:/Windows/Fonts/segoeuib.ttf"
    parts, ins = [], []
    for k, (cut, label) in enumerate(zip(cuts, labels)):
        ins += ["-i", str(cut)]
        parts.append(f"[{k}:v]scale=360:640,setsar=1,drawtext=fontfile='{font}':text='{label}':x=10:y=10:fontsize=22:"
                     f"fontcolor=white:box=1:boxcolor=black@0.6[v{k}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{k}]" for k in range(len(cuts))) + f"hstack=inputs={len(cuts)}[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
                    "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-shortest", str(dest)], check=False)


def sheets(out_dir: Path, *, desk: str, comfy: str, vibe: str, starts: list[float], idea: str = "",
           modes: tuple[str, ...] = ("today", "plain", "breathe"), stills: Path | None = None) -> list[dict]:
    """``stills``: the desk's XENO_STILLS (a copy), whose usage.json goes back as it was before each Make."""
    import requests

    out_dir.mkdir(parents=True, exist_ok=True)
    usage = Usage(stills)
    song = requests.post(f"{desk}/api/songs/load", json={"id": "glitch-out"}, timeout=300)
    if song.status_code != 200:
        with open(SONG, "rb") as fh:
            song = requests.post(f"{desk}/api/analyze", files={"file": (SONG.name, fh, "audio/mpeg")}, timeout=900)
    audio_id = song.json().get("audio_id")
    if not audio_id:
        raise SystemExit(f"no audio id: {song.text[:300]}")
    log_path = out_dir / "sheets.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    for start in starts:
        for mode in modes:
            label = f"{int(start // 60)}m{int(start % 60):02d}_{mode}"
            if any(r["label"] == label and r.get("status") == "done" for r in log):
                continue
            while not _queue_idle(comfy):
                print("  the ComfyUI queue is busy: waiting", flush=True)
                time.sleep(30)
            usage.reset()
            body = {"audio_id": audio_id, "live": True, "mode": "simple", "song": "Glitch Out", "vibe": vibe, "idea": idea,
                    "quality": "turbo", "quality_tier": "draft", "aspect": "9:16", "length_s": 30, "length_start": start,
                    "energy_preset": "dense", "morph_source": "objects", "morph_count": "auto", "morph_style": "auto",
                    "morph_timing": "smooth", "effects": [], "beat_fx": True, "dance_fx": "auto", "foreshadow": "auto",
                    "scene_stills": "off", "scenes_chosen": True, "backdrop": "plain", "macros": dict(MACROS), "end_card": False,
                    "open_weights_only": True, "paid_cloud": False, "vertical_mode": "auto", "stem_orbit": True, "seed": 2727,
                    "chain_pins": {}, **MODES[mode][1]}
            r = requests.post(f"{desk}/api/generate", json=body, timeout=180)
            if r.status_code != 200:
                print(label, "refused", r.status_code, r.text[:300], flush=True)
                log.append({"label": label, "error": r.text[:300]})
                continue
            job = r.json()["id"]
            print(label, "job", job, flush=True)
            t0 = time.perf_counter()
            last = ""
            while True:
                time.sleep(10)
                try:
                    j = requests.get(f"{desk}/api/jobs/{job}", timeout=60).json()
                except Exception as exc:
                    print("  poll:", exc, flush=True)
                    continue
                line = f"  {j.get('stage')} {round(float(j.get('progress') or 0) * 100)}% {j.get('detail')}"
                if line != last:
                    print(line, flush=True)
                    last = line
                if j.get("status") in ("done", "error", "cancelled"):
                    break
            row = {"label": label, "mode": mode, "start": start, "job": job, "status": j.get("status"),
                   "seconds": round(time.perf_counter() - t0, 1), "error": j.get("error")}
            jobs_dir = ROOT / "work" / "ui" / "jobs" / job
            mp4 = jobs_dir / "xenoform.mp4"
            if j.get("status") == "done" and mp4.exists():
                shutil.copy2(mp4, out_dir / f"{label}.mp4")
                _sheet(mp4, out_dir / f"{label}_sheet.jpg")
                try:
                    rec = json.loads((jobs_dir / "simple" / "simple.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    rec = {}
                row.update({"plan_name": rec.get("plan_name"), "line": (rec.get("pacing") or {}).get("line"),
                            "shots": len(rec.get("plan_shots") or []), "window": rec.get("window"),
                            "styles": rec.get("morph_styles"), "boundary_fx": [(b or {}).get("kind") for b in rec.get("boundary_fx") or []]})
                try:  # flash frames per 8 bars of the window, on the song's own beats from where the cut sits
                    from xenoform import post_qa
                    at = float((rec.get("window") or {}).get("song_start") or start)
                    beats = [b - at for b in _features()["beats"] if at <= float(b) < at + 30.0]
                    row["veil"] = {k: v for k, v in post_qa.veil_report(mp4, 24.0, beats).items() if k != "windows"}
                except Exception as exc:  # a report only
                    row["veil"] = {"error": str(exc)}
            log = [x for x in log if x["label"] != label] + [row]
            log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
            print(label, row["status"], "in", row["seconds"], "s", flush=True)
        tag = f"{int(start // 60)}m{int(start % 60):02d}"
        made = [m for m in modes if (out_dir / f"{tag}_{m}.mp4").exists()]
        if len(made) > 1:
            names = {"today": "Today", "plain": "Plain now", "breathe": "Breathe"}
            _side_by_side([out_dir / f"{tag}_{m}.mp4" for m in made], out_dir / f"{tag}_side_by_side.mp4", [names[m] for m in made])
    return log


ROLE_RGB = {"intro": (176, 160, 240), "calm": (70, 205, 190), "sustain": (70, 205, 190), "build": (245, 180, 60),
            "drop": (245, 70, 95), "drop_late": (250, 130, 185), "release": (95, 155, 245), "outro": (160, 160, 170)}
PANEL = (960, 540)   # each cut at full width
STRIP_H = 30         # the cut-rhythm strip under a panel


def rhythm_strip(rec: dict, length: float, dest: Path, width: int = PANEL[0], height: int = STRIP_H) -> Path:
    """The cut's rhythm as a strip: the passages a faint band by role, a tick in the role's colour at every shot change,
    a white mark with a cap at each drop event."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (14, 14, 18))
    d = ImageDraw.Draw(img)
    shots = rec.get("shots") or []
    x_of = (lambda t: int(round(width * max(0.0, min(1.0, float(t) / max(1e-6, length))))))
    for s in shots:  # the passage band
        rgb = ROLE_RGB.get(str(s.get("section") or ""), (110, 110, 120))
        d.rectangle([x_of(s["start"]), height - 6, max(x_of(s["start"]), x_of(s["end"]) - 1), height - 1],
                    fill=tuple(int(c * 0.55) for c in rgb))
    for i, s in enumerate(shots):
        if i == 0:
            continue
        x = x_of(s["start"])
        rgb = ROLE_RGB.get(str(s.get("section") or ""), (200, 200, 200))
        if s.get("event") == "drop":
            d.rectangle([x - 2, 2, x + 2, height - 7], fill=(255, 255, 255))
            d.polygon([(x - 6, 0), (x + 6, 0), (x, 7)], fill=(255, 255, 255))
        else:
            d.rectangle([x - 1, 6, x, height - 7], fill=rgb)
    img.save(dest)
    return dest


def _playhead(dest: Path, height: int = STRIP_H) -> Path:
    from PIL import Image

    Image.new("RGB", (3, height), (255, 255, 255)).save(dest)
    return dest


def stacked_video(top: Path, top_strip: Path, bottom: Path, bottom_strip: Path, dest: Path, length: float,
                  labels: tuple[str, str] = ("Plain (Breathe off)", "Breathe")) -> None:
    """Plain above Breathe at full width, each with its rhythm strip and a playhead moving over it; the song once."""
    font = "C\\:/Windows/Fonts/segoeuib.ttf"
    head = _playhead(dest.with_name(dest.stem + "_playhead.png"))
    w, h = PANEL

    def label(i: int, text: str) -> str:
        return (f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"drawtext=fontfile='{font}':text='{text}':x=14:y=12:fontsize=26:fontcolor=white:box=1:boxcolor=black@0.55")
    graph = ";".join([
        label(0, labels[0]) + "[a]",
        label(1, labels[1]) + "[b]",
        f"[2:v]fps=24,format=rgb24[sa];[4:v]fps=24,format=rgb24[pa];[sa][pa]overlay=x='t/{length:.3f}*{w}':y=0:eval=frame,format=yuv420p[ta]",
        f"[3:v]fps=24,format=rgb24[sb];[5:v]fps=24,format=rgb24[pb];[sb][pb]overlay=x='t/{length:.3f}*{w}':y=0:eval=frame,format=yuv420p[tb]",
        "[a][ta][b][tb]vstack=inputs=4[v]"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(top), "-i", str(bottom),
                    "-loop", "1", "-t", f"{length:.3f}", "-i", str(top_strip), "-loop", "1", "-t", f"{length:.3f}", "-i", str(bottom_strip),
                    "-loop", "1", "-t", f"{length:.3f}", "-i", str(head), "-loop", "1", "-t", f"{length:.3f}", "-i", str(head),
                    "-filter_complex", graph, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "19", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dest)], check=True)
    head.unlink(missing_ok=True)


def passage_looks(rec: dict, song_start: float = 0.0) -> list[dict]:
    """Each passage of a cut from its record: its role, where it sits in the song, its shots, its median hold in bars,
    its rests and its looks a minute (a look: a run of shots with one morph style, one timing, one effect, one colour
    look)."""
    shots = rec.get("shots") or []
    styles = rec.get("morph_styles") or []
    beats = sorted(float(b) for b in rec.get("beats") or [])
    bar = 4 * _period(beats) if len(beats) > 2 else 4 * 60.0 / 90.0

    def key(s: dict) -> tuple:
        m = int(s.get("morph", s.get("clip", 0)) or 0)
        return (styles[m] if m < len(styles) else "", str((s.get("timing") or {}).get("mode") or rec.get("morph_timing") or "smooth"),
                tuple(s.get("fx_names") or []), str(s.get("dance_fx") or ""))
    rows: list[dict] = []
    for i, s in enumerate(shots):
        p = s.get("passage", s.get("section"))
        if not rows or rows[-1]["passage"] != p:
            rows.append({"passage": p, "role": str(s.get("section") or ""), "start": float(s["start"]), "end": float(s["end"]),
                         "shots": 0, "looks": 0, "rests": 0, "holds": [], "_last": None})
        r = rows[-1]
        r["end"] = float(s["end"])
        r["shots"] += 1
        r["rests"] += int(bool(s.get("rest")))
        r["holds"].append((float(s["end"]) - float(s["start"])) / bar)
        k = key(s)
        r["looks"] += int(k != r["_last"])
        r["_last"] = k
    out = []
    for r in rows:
        secs = r["end"] - r["start"]
        holds = sorted(r["holds"])
        out.append({"role": r["role"], "at": mmss(song_start + r["start"]), "seconds": round(secs, 1), "shots": r["shots"],
                    "looks": r["looks"], "looks_per_min": round(60.0 * r["looks"] / max(1e-6, secs), 1),
                    "hold_bars": round(holds[len(holds) // 2], 1) if holds else 0.0, "rests": r["rests"]})
    return out


def stacked(out_dir: Path, *, desk: str, comfy: str, vibe: str, idea: str, windows: list[tuple[float, float]],
            stills: Path | None = None) -> list[dict]:
    """Round two's proof: for each window (start, length) a plain Make and a Breathe Make, Draft at 16:9 through the desk
    (each only when ComfyUI's queue is empty, the library's usage put back before each), stacked with their strips."""
    import requests

    out_dir.mkdir(parents=True, exist_ok=True)
    usage = Usage(stills)
    song = requests.post(f"{desk}/api/songs/load", json={"id": "glitch-out"}, timeout=300)
    audio_id = song.json().get("audio_id")
    if not audio_id:
        raise SystemExit(f"no audio id: {song.text[:300]}")
    log_path = out_dir / "stacked.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    for start, length in windows:
        tag = f"{int(start // 60)}m{int(start % 60):02d}_{int(length)}s"
        made = {}
        for mode in ("plain", "breathe"):
            label = f"{tag}_{mode}"
            row = next((r for r in log if r["label"] == label and r.get("status") == "done"), None)
            if row is None:
                while not _queue_idle(comfy):
                    print("  the ComfyUI queue is busy: waiting", flush=True)
                    time.sleep(30)
                usage.reset()
                body = {"audio_id": audio_id, "live": True, "mode": "simple", "song": "Glitch Out", "vibe": vibe, "idea": idea,
                        "quality": "turbo", "quality_tier": "draft", "aspect": "16:9", "length_s": length, "length_start": start,
                        "energy_preset": "dense", "morph_source": "objects", "morph_count": "auto", "morph_style": "auto",
                        "morph_timing": "smooth", "effects": [], "beat_fx": True, "dance_fx": "auto", "foreshadow": "auto",
                        "scene_stills": "off", "scenes_chosen": True, "backdrop": "plain", "macros": dict(MACROS),
                        "end_card": False, "open_weights_only": True, "paid_cloud": False, "vertical_mode": "auto",
                        "stem_orbit": True, "seed": 2727, "chain_pins": {}, **MODES[mode][1]}
                r = requests.post(f"{desk}/api/generate", json=body, timeout=180)
                if r.status_code != 200:
                    print(label, "refused", r.status_code, r.text[:300], flush=True)
                    continue
                job = r.json()["id"]
                print(label, "job", job, flush=True)
                t0 = time.perf_counter()
                last = ""
                while True:
                    time.sleep(10)
                    try:
                        j = requests.get(f"{desk}/api/jobs/{job}", timeout=60).json()
                    except Exception as exc:
                        print("  poll:", exc, flush=True)
                        continue
                    line = f"  {j.get('stage')} {round(float(j.get('progress') or 0) * 100)}% {j.get('detail')}"
                    if line != last:
                        print(line, flush=True)
                        last = line
                    if j.get("status") in ("done", "error", "cancelled"):
                        break
                row = {"label": label, "mode": mode, "start": start, "length": length, "job": job, "status": j.get("status"),
                       "seconds": round(time.perf_counter() - t0, 1), "error": j.get("error")}
                log = [x for x in log if x["label"] != label] + [row]
                log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
                print(label, row["status"], "in", row["seconds"], "s", flush=True)
            if row.get("status") != "done":
                continue
            jobs_dir = ROOT / "work" / "ui" / "jobs" / row["job"]
            rec = json.loads((jobs_dir / "simple" / "simple.json").read_text(encoding="utf-8"))
            shutil.copy2(jobs_dir / "xenoform.mp4", out_dir / f"{label}.mp4")
            at = float((rec.get("window") or {}).get("song_start") or start)
            rhythm_strip(rec, float(length), out_dir / f"{label}_strip.png")
            row.update({"line": (rec.get("pacing") or {}).get("line"), "song_start": at, "shots": len(rec.get("shots") or []),
                        "passages": passage_looks(rec, at)})
            try:
                from xenoform import post_qa
                beats = [b - at for b in _features()["beats"] if at <= float(b) < at + float(length)]
                row["veil"] = {k: v for k, v in post_qa.veil_report(jobs_dir / "xenoform.mp4", 24.0, beats).items() if k != "windows"}
            except Exception as exc:  # a report only
                row["veil"] = {"error": str(exc)}
            log = [x for x in log if x["label"] != label] + [row]
            log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
            made[mode] = row
        if len(made) == 2:
            stacked_video(out_dir / f"{tag}_plain.mp4", out_dir / f"{tag}_plain_strip.png", out_dir / f"{tag}_breathe.mp4",
                          out_dir / f"{tag}_breathe_strip.png", out_dir / f"{tag}_plain_over_breathe.mp4", float(length))
            print(tag, "stacked", flush=True)
    return log


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("table", "sheets", "stacked"))
    ap.add_argument("out", type=Path)
    ap.add_argument("--no-flash", action="store_true")
    ap.add_argument("--vibe", default="")
    ap.add_argument("--desk", default="http://127.0.0.1:47327")
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--starts", default="105,0")
    ap.add_argument("--idea", default="")
    ap.add_argument("--modes", default="today,plain,breathe")
    ap.add_argument("--stills", type=Path, default=None, help="a copy of a grown stills library (its usage.json is put back)")
    ap.add_argument("--windows", default="90:90,30:90,0:30", help="start:length pairs for stacked")
    a = ap.parse_args()
    if a.what == "table":
        table(a.out, flash=not a.no_flash, vibe=a.vibe or "cosmic", stills=a.stills)
    elif a.what == "stacked":
        stacked(a.out, desk=a.desk, comfy=a.comfy, vibe=a.vibe or "bioluminescent", idea=a.idea, stills=a.stills,
                windows=[(float(w.split(":")[0]), float(w.split(":")[1])) for w in a.windows.split(",")])
    else:
        sheets(a.out, desk=a.desk, comfy=a.comfy, vibe=a.vibe or "black", starts=[float(x) for x in a.starts.split(",")],
               idea=a.idea, modes=tuple(m for m in a.modes.split(",") if m in MODES), stills=a.stills)


if __name__ == "__main__":
    sys.exit(main())
