"""Per-job chain records of the cuts that were published or shipped, without the machine's paths.

    python scripts/export_records.py [--jobs work/ui/jobs] [--out docs/demo/records/chains.json]

``work/`` is git-ignored and a job's ``simple/simple.json`` holds absolute paths, so what a published slot, an example cut,
a loved morph, a chain preset, a library strip, a demo segment or a film-pack cut was made of would be lost with the
machine. This writes one record per job, keyed by its job id: where it was used, the vibe, tier and engine, the seed, the
morph style, timing, effects, look, foreshadow and knobs, the idea line, the stills in chain order (and the pins), the shots
(start, end, render seconds, speed, the pair of stills each morph runs between) and the recipe code (``xf1.``: paste it into
the desk to remix). A cut of film clips lists the clips instead of the stills. The jobs come from

* ``docs/demo/records/as_cut_169.json`` and ``as_cut_916.json`` (the 68 slots of the Glitch Out music video as cut),
* ``examples/cuts/cuts.json``, ``examples/morphs/morphs.json``, ``configs/chain_presets.json``, ``configs/clip_pack.json``,
* the demo plan ``docs/demo/tools/plans/plan_short.json`` (the segments' jobs) and the five film-pack cuts below.

A song that is not bundled is named neutrally (``SONGS``): the 29 October Suno demos were uploaded under file names that
name artists and are not credited in this repo, so neither the record nor its recipe code carries one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "docs" / "demo" / "records"
sys.path.insert(0, str(ROOT / "src"))

# meta["song"] (before " (30 s cut)") -> (bundled song id or None, a label that names no artist)
SONGS = {
    "Glitch Out": ("glitch-out", "Glitch Out"),
    "hip_hop_boom_bap": ("hip-hop-boom-bap", "Hip hop, boom bap"),
    "XF_HipHop_BoomBap_01": ("hip-hop-boom-bap", "Hip hop, boom bap"),
    "XF_Ambient_01": ("ambient", "Ambient"),
    "XF_DnB_Liquid_01_v2": ("liquid-dnb", "Liquid drum and bass"),
    "XF_DnB_Liquid_01_v1": (None, "Suno demo, liquid drum and bass, an earlier take (not bundled)"),
    "XF_Techno_01": (None, "Suno demo, techno (not bundled)"),
    "XF_Breakbeat_Prodigy_01_v1": (None, "Suno demo, breakbeat (not bundled)"),
    "XF_Synthwave_01_v2": (None, "Suno demo, synthwave (not bundled)"),
    "XF_Riff_Tool_01": (None, "Suno demo, slow heavy riff (not bundled)"),
    "XF_Psytrance_01": (None, "Suno demo, psytrance (not bundled)"),
    "XF_Bass_ZedsDead_01_v1": (None, "Suno demo, bass music (not bundled)"),
    "XF_Riff_Korn_01": (None, "Suno demo, heavy riff (not bundled)"),
}
FILM_PACK = {
    "0935c309": "film-pack cut on the hip-hop song, Fast Final, the whole 24-clip pack offered (the first pack cut, 29 October)",
    "1d376198": "film-pack cut on the hip-hop song, Fast Final, the whole 24-clip pack offered (29 October)",
    "ed2796a2": "film-pack cut clips_montage on Glitch Out, LTX-2.3 Final (docs/demo/tools/plans/clips_glitch.json)",
    "66da0461": "film-pack cut clips_demo on Glitch Out, LTX-2.3 Final: the demo's clips segment",
    "c11d5c0f": "film-pack cut clips_flash on Glitch Out: clips_demo's clips re-cut with the cyan-flash look and dither",
}


def neutral_song(meta_song: str) -> tuple[str | None, str, int | None]:
    """(bundled id, neutral label, window seconds) of a job's ``meta["song"]`` such as ``"Glitch Out (30 s cut)"``."""
    name = re.sub(r"\s*\([^)]*\)\s*$", "", meta_song or "").replace(".mp3", "")
    window = re.search(r"\((\d+(?:\.\d+)?) s cut\)", meta_song or "")
    sid, label = SONGS.get(name, (None, "a song that is not bundled"))
    return sid, label, int(float(window.group(1))) if window else None


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def used_in() -> dict[str, list[str]]:
    """job id -> where it was used, from the files in the repo that name jobs."""
    out: dict[str, list[str]] = {}

    def add(job, text):
        if job and text not in out.setdefault(str(job), []):
            out[str(job)].append(text)

    for aspect, name in (("16:9", "as_cut_169.json"), ("9:16", "as_cut_916.json")):
        for s in read(RECORDS / name)["slots"]:
            crop = " (the 16:9 render cropped)" if s["label"].endswith("@169") else ""
            add(s["job"], f"Glitch Out music video, {aspect} cut, slot {s['label']}{crop}: song {s['song_in']} to {s['song_out']} s")
    for c in read(ROOT / "examples" / "cuts" / "cuts.json")["cuts"]:
        add(c["source"]["job"], f"example cut of {c['vibe']} (examples/cuts/{c['file']})")
    for m in read(ROOT / "examples" / "morphs" / "morphs.json")["morphs"]:
        add(m.get("job"), f"loved morph {m['id']} (shot {m.get('shot')})")
        for a in m.get("also_used_in", []):
            add(a.get("job"), f"loved morph {m['id']}, the same clip (shot {a.get('shot')})")
    presets = ROOT / "configs" / "chain_presets.json"
    if presets.is_file():
        for p in read(presets)["presets"]:
            add((p.get("source") or {}).get("job"), f"chain preset {p['id']}")
    pack = ROOT / "configs" / "clip_pack.json"
    if pack.is_file():
        for vibe, row in read(pack)["vibes"].items():
            src = row.get("source_clip")
            if isinstance(src, dict):
                add(src.get("job"), f"library strip of {vibe} (shot {src.get('shot')})")
    plan = ROOT / "docs" / "demo" / "tools" / "plans" / "plan_short.json"
    if plan.is_file():
        for seg in read(plan)["segments"]:
            for job in sorted(set(re.findall(r"jobs/([0-9a-f]{8})/", json.dumps(seg)))):
                add(job, f"the contest demo video, segment {seg.get('id')}")
    for job, text in FILM_PACK.items():
        add(job, text)
    return out


def record(job: str, uses: list[str], jobs: Path) -> dict:
    from xenoform import simple_recipe

    base = jobs / job
    meta = read(base / "meta.json")
    s = read(base / "simple" / "simple.json")
    sid, label, window = neutral_song(meta.get("song", ""))
    recipe = meta.get("recipe", "")
    if recipe:
        state = simple_recipe.decode(recipe)
        suffix = re.search(r"\s*(\([^)]*\))\s*$", state.get("song") or "")
        want = label.split(" (")[0] + (f" {suffix.group(1)}" if suffix else "")  # the same label examples/cuts/cuts.json gave
        if state.get("song") != want:
            state["song"] = want[:80]
            recipe = simple_recipe.encode(state)
    macros = s.get("macros") or {}
    look = s.get("look") or {}
    fore = s.get("foreshadow") or {}
    idea = s.get("idea")
    rendered = next((f["cloud_final"] for f in s.get("fallbacks") or [] if isinstance(f, dict) and "cloud_final" in f), "")
    fps = s.get("fps") or 24
    rec: dict = {
        "used_in": sorted(uses),
        "made": (meta.get("created") or "")[:10],
        "vibe": meta.get("vibe") or s.get("vibe"),
        "aspect": meta.get("aspect") or s.get("aspect"),
        "tier": meta.get("quality_tier"),
        "engine": s.get("engine", ""),
        "open_weights": bool(s.get("open_weights")),
        "song": {"id": sid, "label": label, "window_s": window},
        "seconds": round((s.get("frames") or 0) / fps, 2),
        "size": s.get("size"),
        "seed": s.get("seed"),
        "energy": meta.get("energy_preset") or s.get("energy"),
        "morph_style": s.get("morph_style"),
        "morph_timing": s.get("morph_timing"),
        "effects": s.get("effects") or [],
        "look": look.get("dance_fx") if isinstance(look, dict) else look,
        "foreshadow": fore.get("mode") if isinstance(fore, dict) else fore,
        "knobs": {k: macros[k] for k in ("intensity", "speed", "chaos", "glow") if k in macros},
        "drop_s": s.get("drop"),
    }
    if rendered:
        rec["rendered"] = rendered
    if isinstance(idea, dict) and idea.get("line"):
        rec["idea"] = idea["line"]
    elif isinstance(idea, str) and idea:
        rec["idea"] = idea
    chain = s.get("chain") if isinstance(s.get("chain"), dict) else {}
    if s.get("source") == "clips":
        rec["clips"] = [{"file": PureWindowsPath(c["path"]).name, "label": c.get("label", ""), "seconds": c.get("seconds")}
                        for c in s.get("own_clips") or []]
        rec["shots"] = [{"i": sh["index"], "start": sh["start"], "end": sh["end"], "render_s": sh.get("render_s"),
                         "clip": sh.get("source"), "clip_start": sh.get("clip_start"),
                         **({"effects": sh["effects"]} if sh.get("effects") else {})} for sh in s["shots"]]
    else:
        stills = list(s.get("stills") or [])
        styles = list(s.get("morph_styles") or [])
        mixed = len(set(styles)) > 1
        rec["morphs"] = chain.get("morphs", len(s["shots"]))
        if mixed:
            rec["morph_styles"] = styles
        if s.get("scene_mode") and s.get("scene_mode") != "off":
            rec["scene_mode"] = s["scene_mode"]
        rec["chain"] = stills
        if s.get("pins"):
            rec["pins"] = s["pins"]
        shots = []
        for sh in s["shots"]:
            m = int(sh.get("morph", sh["index"]))
            row = {"i": sh["index"], "start": sh["start"], "end": sh["end"], "render_s": sh.get("render_s"), "speed": sh.get("speed"),
                   "from": stills[m] if m < len(stills) else None, "to": stills[m + 1] if m + 1 < len(stills) else None}
            if m != sh["index"]:
                row["morph"] = m
            if mixed and m < len(styles):
                row["style"] = styles[m]
            if sh.get("ease"):
                row["ease"] = sh["ease"]
            if sh.get("effects"):
                row["effects"] = sh["effects"]
            shots.append(row)
        rec["shots"] = shots
    rec["recipe"] = recipe
    return rec


def fmt(v, ind: int = 0) -> str:
    """JSON with one line a shot (a list of objects is one object a line, a list of numbers or names stays inline)."""
    pad = " " * ind
    if isinstance(v, dict):
        if not v:
            return "{}"
        rows = [f"{pad} {json.dumps(k, ensure_ascii=False)}: {fmt(x, ind + 1)}" for k, x in v.items()]
        return "{\n" + ",\n".join(rows) + f"\n{pad}}}"
    if isinstance(v, list):
        if not any(isinstance(x, (dict, list)) for x in v):
            return json.dumps(v, ensure_ascii=False)
        rows = [f"{pad} {json.dumps(x, ensure_ascii=False)}" for x in v]
        return "[\n" + ",\n".join(rows) + f"\n{pad}]"
    return json.dumps(v, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--jobs", default=str(ROOT / "work" / "ui" / "jobs"))
    ap.add_argument("--out", default=str(RECORDS / "chains.json"))
    args = ap.parse_args(argv)
    jobs = Path(args.jobs)
    uses = used_in()
    out, missing = {}, []
    for job in sorted(uses):
        if not (jobs / job / "simple" / "simple.json").is_file() or not (jobs / job / "meta.json").is_file():
            missing.append(job)
            continue
        out[job] = record(job, uses[job], jobs)
    top = {
        "version": 1,
        "note": ("What each published, example, loved, preset, strip, demo and film-pack job was made of (scripts/export_records.py "
                 "from the job folders, which are not in the repo): the stills in chain order, the pair each morph runs between, the "
                 "timing of every shot, the settings and the recipe code. No paths; a song that is not bundled is named neutrally. "
                 "`chain`, `pins` and a shot's `from` and `to` are file names of ui_static/objects: the stills that were on screen in "
                 "a published cut or an example excerpt are shipped there, the rest (a chain renders more morphs than a slot shows) "
                 "stay in the author's grown set, so a pin on one of them is dropped on another machine. The as-cut records of the "
                 "music video are as_cut_169.json and as_cut_916.json."),
        "jobs": out,
    }
    Path(args.out).write_text(fmt(top) + "\n", encoding="utf-8", newline="\n")
    print(len(out), "records", "| not found:", missing or "none", "|", Path(args.out).stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
