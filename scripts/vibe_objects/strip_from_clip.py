"""A library strip from a finished morph clip: wide / medium / close / reveal at 768x432 with a jpg poster each, the format
``make_library.py`` writes, cut from a clip that already exists (a Cloud Final morph of the vibe's own stills) instead of a
new LTX 0.9.5 render of orb -> nautilus. No GPU, no ComfyUI: ffmpeg only (31 Oct 2026: 23 strips were re-cut this way).

    python scripts/vibe_objects/strip_from_clip.py <vibe> <clip.mp4> [--from A --to B] [--source JSON] [--pack] [--out DIR]

* wide is the whole frame, medium a centre crop of 1/1.15, close of 1/1.5, reveal the wide cut played backwards (the object the
  morph ends on, turning back into the one it began with); the posters are the clean object each clip starts on (frame 0), the
  reveal's the last frame.
* a portrait clip (9:16) is cut to its centre 16:9 band first.
* each mp4 must be over 500 B and at most 1,200,000 B (``tests/test_vibe_registry.py``); the CRF starts at 30 and rises until the
  file fits, the lowest that does is kept. Each poster is over 4 KB.
* ``--pack`` updates ``configs/clip_pack.json`` for the vibe: ``clips``, ``source_morph`` (``--from`` -> ``--to``, the stills'
  file stems), ``source_clip`` (``--source``: the job and shot as JSON), ``qa`` (the temporal check on the new clip) and
  ``checked``; an ``autotune_score`` (a measure of the LTX 0.9.5 render) is dropped, it no longer describes the clip.

Writes ``<out>/<vibe>/{wide,medium,close,reveal}.{mp4,jpg}`` (``--out`` defaults to ``ui_static/library``).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src" / "xenoform" / "ui_static"
PACK = ROOT / "configs" / "clip_pack.json"
W, H, FPS = 768, 432, 24
CUTS = {"wide": (1.0, False), "medium": (1.15, False), "close": (1.5, False), "reveal": (1.0, True)}  # name -> (centre crop factor, reversed)
MAX_BYTES, MIN_BYTES, MIN_POSTER = 1_200_000, 500, 4_000
CRF_FROM, CRF_TO = 30, 42  # CRF 22, 26 and 30 looked the same at 1:1 on a contact sheet; 30 keeps a 4 s strip at 0.1 to 0.6 MB


def probe(clip: Path) -> dict:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                                   "stream=width,height,nb_read_frames", "-of", "json", str(clip)], text=True)
    s = json.loads(out)["streams"][0]
    return {"w": int(s["width"]), "h": int(s["height"]), "frames": int(s["nb_read_frames"])}


def vf_for(info: dict, zoom: float, reverse: bool) -> str:
    chain = []
    if info["h"] > info["w"]:  # a portrait clip: its centre 16:9 band
        band = (info["w"] * 9 // 16) // 2 * 2
        chain.append(f"crop={info['w']}:{band}:0:(ih-{band})/2")
    if zoom != 1.0:
        chain.append(f"crop=iw/{zoom}:ih/{zoom}")
    chain.append(f"scale={W}:{H}:flags=lanczos")
    chain.append("format=yuv420p")
    if reverse:
        chain.append("reverse")
    return ",".join(chain)


def encode(clip: Path, vf: str, crf: int, dest: Path) -> int:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", vf, "-an", "-r", str(FPS), "-c:v", "libx264",
                    "-crf", str(crf), "-preset", "slow", "-movflags", "+faststart", str(dest)], check=True)
    return dest.stat().st_size


def poster(mp4: Path, last: bool, frames: int, dest: Path) -> None:
    pick = f"select=eq(n\\,{frames - 1})" if last else "select=eq(n\\,0)"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", pick, "-frames:v", "1", "-q:v", "3", str(dest)], check=True)


def cut(clip: Path, out: Path) -> dict:
    """The four mp4s and posters in ``out``; returns the CRF each took and the frame count."""
    info = probe(clip)
    out.mkdir(parents=True, exist_ok=True)
    crfs = {}
    for name, (zoom, rev) in CUTS.items():
        vf = vf_for(info, zoom, rev)
        mp4 = out / f"{name}.mp4"
        crf, size = CRF_FROM, 0
        while True:
            size = encode(clip, vf, crf, mp4)
            if size <= MAX_BYTES or crf >= CRF_TO:
                break
            crf += 2 if size < MAX_BYTES * 1.6 else 4
        if not MIN_BYTES < size <= MAX_BYTES:
            raise SystemExit(f"{mp4}: {size} bytes does not fit {MIN_BYTES} to {MAX_BYTES} at crf {crf}")
        n = int(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                                         "stream=nb_read_frames", "-of", "csv=p=0", str(mp4)], text=True).strip().rstrip(","))
        poster(mp4, rev, n, out / f"{name}.jpg")
        if (out / f"{name}.jpg").stat().st_size <= MIN_POSTER:
            raise SystemExit(f"{out / (name + '.jpg')} is under {MIN_POSTER} bytes")
        crfs[name] = crf
    return {"crf": crfs, "frames": info["frames"], "size": [info["w"], info["h"]]}


def qa(mp4: Path) -> dict:
    """The temporal QA ``make_library.py`` records (the CLIP part is off: the desk's venv has no torch)."""
    os.environ.setdefault("XENO_QA_CLIP_OFF", "1")
    sys.path.insert(0, str(ROOT / "src"))
    from xenoform import morph_pass as mp, shot_qa

    return shot_qa.check(mp._read_frames(mp4, 320, 180), "a clean single sculptural object", "")


def update_pack(vibe: str, args, ok: bool) -> None:
    pack = json.loads(PACK.read_text(encoding="utf-8"))
    entry = {"clips": [f"library/{vibe}/{name}.mp4" for name in CUTS]}  # a fresh entry: the old morph's score and source no longer apply
    if args.src and args.dst:
        entry["source_morph"] = f"{args.src} -> {args.dst}"
    if args.source:
        entry["source_clip"] = json.loads(args.source)
    entry["qa"] = bool(ok)
    entry["checked"] = args.checked or "re-cut from a finished morph clip, frames checked by eye"
    pack["vibes"][vibe] = entry
    PACK.write_text(json.dumps(pack, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("vibe")
    ap.add_argument("clip")
    ap.add_argument("--from", dest="src", default="", help="the still the morph starts on (file stem), for source_morph")
    ap.add_argument("--to", dest="dst", default="", help="the still the morph ends on (file stem), for source_morph")
    ap.add_argument("--source", default="", help='JSON naming the clip, e.g. \'{"job": "a2d64f77", "shot": 6, "engine": "..."}\'')
    ap.add_argument("--checked", default="", help="the clip_pack `checked` line")
    ap.add_argument("--pack", action="store_true", help="update configs/clip_pack.json for the vibe")
    ap.add_argument("--out", default=str(STATIC / "library"))
    args = ap.parse_args(argv)

    clip = Path(args.clip)
    if not clip.is_file():
        raise SystemExit(f"{clip} is missing")
    dest = Path(args.out) / args.vibe
    done = cut(clip, dest)
    verdict = qa(dest / "wide.mp4")
    sizes = {n: (dest / f"{n}.mp4").stat().st_size for n in CUTS}
    print(json.dumps({"vibe": args.vibe, "clip": clip.name, "crf": done["crf"], "bytes": sizes, "qa_ok": verdict["ok"],
                      "qa_score": verdict["score"], "reasons": verdict["reasons"]}), flush=True)
    if args.pack:
        update_pack(args.vibe, args, bool(verdict["ok"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
