"""The prototype run behind the first six vibes' stills, compiled into small records and checked against the shipped stills.

The run (``overnight.py``, ``ov_lib.py`` and ``plan.json`` beside this file, copied as they were) was the author's overnight
library run of 18 and 19 October 2026, before the app: Z-Image Turbo objects, FLUX.2 Klein 4B material edits of them,
LTX-2.3 clips. Its media (557 MB) are not in the repo; every prompt, seed and model is, compiled from the run's own files:

    python scripts/vibe_objects/provenance/build.py compile --proto <xenoform_proto/overnight>
        objects_seeds.json   the seed each of the 116 objects and textures was made with (objects/<name>.png.json)
        klein_edits.json     the 117 material edits (klein/ov_<object>_<material>.png): model, seed, prompt
        clips.json           the 93 LTX-2.3 clips (clips/<id>.mp4.json): prompt, seed, guides, size, gate, takes
    python scripts/vibe_objects/provenance/build.py verify --proto <...>
        lineage.json         each of the 77 stills of liquid-gold, bloom, neon-night, ocean, cosmic and black matched to
                             its source still of the run (needs numpy, Pillow and opencv-python)
    python scripts/vibe_objects/provenance/build.py stamp
        objects.json         the ``source`` of those 77 rows: the still, the seed, the model, the material edit, the grade

``verify`` is how the rows were tied to the run (nothing is a guess from a file name): ``grade.py`` applied to the run's
still gives the shipped jpg to 32 dB or better for the five graded pools (a raw still is 11 to 20 dB off), and SIFT
feature matching with a RANSAC similarity fit finds the same object in all 77 (13 to 1,207 agreeing matches): in 73 of
them at the same place (scale 1, shift under 4 px), in four black ones (manta ray, dragonfly, ribbon, liquid orb) at the
scale the cut-out re-framed them to (0.77 to 1.37).
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OBJECTS = ROOT / "src" / "xenoform" / "ui_static" / "objects" / "objects.json"
GRADED = ("liquid-gold", "bloom", "neon-night", "ocean", "cosmic")  # grade.py has a row for each; black is cut out
LIBRARY = re.compile(r"^library/gpu_objects/(?P<stem>[^ ]+)\.png")
CHECKED = "2026-10-31"
KLEIN_SEED = 77  # ov_lib.kjob's default; the run never passed another
MATERIAL = {"gr": "ferrofluid", "chrome": "chrome", "mercury": "mercury", "iridescent": "iridescent",
            "black_glass": "black glass", "oil_slick": "oil slick"}


def plan() -> dict:
    return json.loads((HERE / "plan.json").read_text(encoding="utf-8"))


def constants() -> dict:
    """KEDIT and MIDSRC from overnight.py, read without importing it (ov_lib opens a log file on import)."""
    found = {}
    for node in ast.parse((HERE / "overnight.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", "") in ("KEDIT", "MIDSRC"):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    return found


def split_material(stem: str, materials) -> tuple[str, str]:
    """``droplet_mercury`` -> (``droplet``, ``mercury``); the longest material that ends the stem wins."""
    mat = next(m for m in sorted(materials, key=len, reverse=True) if stem.endswith("_" + m))
    return stem[: -(len(mat) + 1)], mat


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- compile
def compile_objects(proto: Path, p: dict) -> dict:
    cull = read(proto / "cull.json") if (proto / "cull.json").is_file() else {}
    rows = {}
    for item in p["objects"] + p["textures"]:
        name = item["name"]
        rec_path = proto / "objects" / f"{name}.png.json"
        if not rec_path.is_file():
            continue
        rec = read(rec_path)
        planned, used = int(item["seed"]), int(rec["seed"])
        how = "reroll" if rec.get("reroll") else "planned" if used == planned else "retry" if used == planned + 1000 else "other"
        row = {"seed": used, "planned": planned, "how": how, "kind": "texture" if item in p["textures"] else "object"}
        if how == "reroll" and name in cull.get("reroll", {}):
            row["prompt_add"] = cull["reroll"][name].get("prompt_add", "")
        rows[name] = row
    return {"version": 1, "note": ("The seed each object and texture of plan.json was made with (the run's objects/<name>.png.json). "
            "Z-Image Turbo, GGUF Q8_0, 1024x576, 9 steps, the prompt of plan.json (plus prompt_add for a reroll). `how`: planned "
            "(the plan's seed), retry (the plan's seed + 1000, after the still gate refused the first), reroll (the review's "
            "seed and added sentence, cull.json)."), "objects": rows}


def compile_klein(proto: Path, p: dict) -> dict:
    k = constants()
    refs = k["MIDSRC"]["gr"]
    out = []
    for path in sorted((proto / "klein").glob("*.png")):
        m = re.match(r"^ov_(?P<mid>mid_)?(?P<what>.+)\.png$", path.name)
        what, mat = split_material(m["what"], p["materials"])
        if m["mid"]:
            kind, reference = "mid", refs[what]
        else:
            kind, reference = "object", f"ov_{what}_gr.png"
        out.append({"file": path.name, "kind": kind, "what": what, "material": mat, "reference": reference})
    return {"version": 1, "model": "flux-2-klein-4b.safetensors (FLUX.2 Klein 4B, Apache 2.0)", "seed": KLEIN_SEED, "steps": 4,
            "size": [1024, 576], "note": ("Each file is one edit of a reference image (ov_<object>_gr.png is the 768x448 centre crop of "
            "objects/<object>.png, the Z-Image still; a mid reference is one of the run's own guide stills): ov_lib.kgraph, "
            "euler, cfg 1, reference scaled to one megapixel, seed 77, the prompt of its material in `prompts` (overnight.py's "
            "KEDIT with the material's phrase from plan.json)."),
            "prompts": {m: k["KEDIT"].format(M=text) for m, text in p["materials"].items() if m != "gr"}, "edits": out}


def compile_clips(proto: Path, p: dict) -> dict:
    wanted = {c["id"] for c in p["clips"] + p.get("heroes", [])}
    folder = proto / "clips"
    clips, failed = [], []
    for cid in sorted(wanted):
        final = folder / f"{cid}.mp4.json"
        if not final.is_file():
            note = folder / f"{cid}.mp4.failed"
            if note.is_file():
                failed.append({"id": cid, "why": note.read_text(encoding="utf-8").strip()[:120]})
            continue
        rec = read(final)
        takes = []
        for tp in sorted(folder.glob(f"{cid}_s*.mp4.json")):
            t = read(tp)
            takes.append({"seed": t["seed_used"], "ok": bool(t["gate"].get("ok")), "why": t["gate"].get("why", [])})
        rejected = [read(rp)["seed_used"] for rp in sorted(folder.glob(f"{cid}_rej*.mp4.json"))]
        clips.append({
            "id": cid, "from": rec["A"], "via": rec.get("B") if rec.get("C") else None, "to": rec.get("C") or rec["B"],
            "recipe": rec["recipe"], "material": rec["material"], "guide": rec.get("guide"),
            "seed_planned": rec["seed"], "seed_used": rec["seed_used"], "res": rec["res"], "fps": rec["fps"],
            "frames": rec["L"], "prompt": rec["prompt"], "guides": rec["guides"], "model": rec["model"],
            "compute_s": rec.get("compute_s"), "gate_ok": bool(rec["gate"].get("ok")), "gate_why": rec["gate"].get("why", []),
            "takes": takes, "rejected_takes": rejected})
    return {"version": 1, "note": ("The LTX-2.3 clips of the run that reached a file: ltx-2.3-22b-distilled-fp8 two-stage with the "
            "x2 spatial upscaler (ov_lib.ltx23), guides as listed (image or video@skip@frames, frame index, strength), the prompt "
            "as sent. `takes` are every render of the clip (the run tried the plan's seed, then +500); `gate_ok` is the run's own "
            "motion gate on the kept take. The clips are not in the repo."), "clips": clips, "not_rendered": failed}


def compile_all(proto: Path) -> None:
    p = plan()
    write(HERE / "objects_seeds.json", compile_objects(proto, p))
    write(HERE / "klein_edits.json", compile_klein(proto, p))
    write(HERE / "clips.json", compile_clips(proto, p))
    print("compiled", sorted(x.name for x in HERE.glob("*.json")))


# ---------------------------------------------------------------- verify
def pool_rows(objects: dict):
    for pool, rows in objects.items():
        for r in rows:
            m = LIBRARY.match(r["source"])
            if m:
                yield pool, r, m["stem"]


def source_still(proto: Path, name: str, mat: str) -> tuple[Path, str]:
    if mat == "gr":
        return proto / "objects" / f"{name}.png", f"objects/{name}.png"
    return proto / "klein" / f"ov_{name}_{mat}.png", f"klein/ov_{name}_{mat}.png"


def verify(proto: Path, sift: bool = True) -> None:
    import numpy as np
    from PIL import Image

    sys.path.insert(0, str(HERE.parent))
    import grade as G

    cv2 = None
    if sift:
        import cv2  # noqa: F811

    p, seeds = plan(), read(HERE / "objects_seeds.json")["objects"]
    objects = read(OBJECTS)
    shipped_dir = OBJECTS.parent
    out = []
    for pool, row, stem in pool_rows(objects):
        name, mat = split_material(stem, p["materials"])
        path, rel = source_still(proto, name, mat)
        shipped = Image.open(shipped_dir / row["file"]).convert("RGB")
        rec = {"file": row["file"], "pool": pool, "still": f"{stem}.png", "object": name, "material": mat,
               "seed": seeds[name]["seed"], "from": rel}
        if pool in GRADED:
            a = np.asarray(G.grade(path, pool), dtype=np.float32)
            b = np.asarray(shipped, dtype=np.float32)
            mse = float(((a - b) ** 2).mean())
            rec["grade_psnr_db"] = round(10 * np.log10(255.0 ** 2 / max(mse, 1e-9)), 1)
        if cv2 is not None:
            sf = cv2.SIFT_create(nfeatures=1500)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            a = clahe.apply(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE))
            b = clahe.apply(cv2.imread(str(shipped_dir / row["file"]), cv2.IMREAD_GRAYSCALE))
            ka, da = sf.detectAndCompute(a, None)
            kb, db = sf.detectAndCompute(b, None)
            good = []
            if da is not None and db is not None and len(ka) > 2 and len(kb) > 2:
                good = [m[0] for m in cv2.BFMatcher().knnMatch(da, db, k=2) if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
            inl, scale, shift = 0, None, None
            if len(good) >= 4:
                pa = np.float32([ka[g.queryIdx].pt for g in good])
                pb = np.float32([kb[g.trainIdx].pt for g in good])
                M, mask = cv2.estimateAffinePartial2D(pa, pb, method=cv2.RANSAC, ransacReprojThreshold=4.0)
                if M is not None:
                    inl = int(mask.sum())
                    scale = round(float(np.hypot(M[0, 0], M[1, 0])), 3)
                    shift = [round(float(M[0, 2]), 1), round(float(M[1, 2]), 1)]
            rec["match"] = {"inliers": inl, "scale": scale, "shift_px": shift}
        out.append(rec)
        print(rec, flush=True)
    graded = [r["grade_psnr_db"] for r in out if "grade_psnr_db" in r]
    inliers = [r["match"]["inliers"] for r in out if "match" in r]
    reframed = [r["file"] for r in out if "match" in r and r["match"]["scale"] and abs(r["match"]["scale"] - 1) > 0.02]
    write(HERE / "lineage.json", {
        "version": 1, "checked": CHECKED,
        "method": ("grade_psnr_db: scripts/vibe_objects/grade.py applied to the run's still against the shipped jpg (the five graded "
                   "pools). match: SIFT features (CLAHE-lifted grey, ratio test 0.75) between the run's still and the shipped jpg, "
                   "RANSAC similarity fit; inliers = agreeing matches, scale and shift_px = the fitted placement (1.0 and 0 mean the "
                   "same frame, as for every graded row; the black pool's cut-out re-framed the rows listed in `reframed`)."),
        "summary": {"rows": len(out), "graded_rows": len(graded), "min_grade_psnr_db": min(graded) if graded else None,
                    "min_inliers": min(inliers) if inliers else None, "reframed": reframed},
        "rows": out})
    print("rows", len(out), "min psnr", min(graded), "min inliers", min(inliers), "reframed", reframed)


# ---------------------------------------------------------------- stamp
def source_text(pool: str, stem: str, name: str, mat: str, seed: int) -> str:
    made = (f"Z-Image Turbo (GGUF Q8_0, Apache 2.0) object \"{name}\", seed {seed}, 1024x576, overnight run of 18 October 2026")
    if mat != "gr":
        made += f", then a FLUX.2 Klein 4B (Apache 2.0) edit to {MATERIAL[mat]} (seed {KLEIN_SEED}, 19 October 2026)"
    how = f"(regraded for {pool} by scripts/vibe_objects/grade.py)" if pool in GRADED else "(cut out onto pure black)"
    return f"library/gpu_objects/{stem}.png {how}: {made}; scripts/vibe_objects/provenance/lineage.json"


def stamp() -> None:
    p, seeds = plan(), read(HERE / "objects_seeds.json")["objects"]
    lineage = {r["file"]: r for r in read(HERE / "lineage.json")["rows"]}
    objects = read(OBJECTS)
    n = 0
    for pool, row, stem in pool_rows(objects):
        name, mat = split_material(stem, p["materials"])
        if row["file"] not in lineage:
            raise SystemExit(f"{row['file']} is not in lineage.json: run verify first")
        text = source_text(pool, stem, name, mat, seeds[name]["seed"])
        if row["source"] != text:
            row["source"] = text
            n += 1
    OBJECTS.write_text(json.dumps(objects, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(n, "sources written")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("step", choices=["compile", "verify", "stamp"])
    ap.add_argument("--proto", help="the prototype run's folder (xenoform_proto/overnight)")
    ap.add_argument("--no-sift", action="store_true", help="verify: only the grade check (no opencv)")
    args = ap.parse_args(argv)
    if args.step != "stamp":
        if not args.proto or not Path(args.proto).is_dir():
            raise SystemExit("--proto <xenoform_proto/overnight> is needed")
    if args.step == "compile":
        compile_all(Path(args.proto))
    elif args.step == "verify":
        verify(Path(args.proto), sift=not args.no_sift)
    else:
        stamp()
    return 0


if __name__ == "__main__":
    sys.exit(main())
