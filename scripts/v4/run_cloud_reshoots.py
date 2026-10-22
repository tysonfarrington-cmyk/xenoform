"""v4 Cloud reshoots (approved by Tys 2026-10-20 17:17): OPEN-WEIGHTS graphs only, cap US$3, spend logged.
Usage: python work/v4/run_cloud_reshoots.py <keyfile|-> [--dry] [--only NAME]
Key: one-use keyfile (deleted on read) or COMFY_ORG_API_KEY. Never printed. --dry = guard/map check only, no key, no send."""
import json, os, sys, time, copy
import os
from pathlib import Path
sys.path.insert(0, "src")
from xenoform.cloud_backend import CloudBackend
from xenoform.config import load_config
W = Path("work/v4"); W.mkdir(parents=True, exist_ok=True); OUT = W / "cloud"; OUT.mkdir(parents=True, exist_ok=True)
LEDGER = OUT / "spend.jsonl"; CAP = 3.00; USD_PER_S = 0.03 / 5 * 1.5  # 50% margin over ~3c/5s
CO = Path(os.environ.get("XENO_COMFY_OUT", str(Path.home() / "AI" / "ComfyUI" / "output" / "xenoform")))
NEG = "blurry, low resolution, flicker, text, watermark, two objects, cut, dissolve, crossfade, hands, people, camera shake"

def morph(prompt, a, b, seed, w=576, h=1024, length=121):
    g = json.load(open("workflows/ltx25_morph_api.json"))
    g["3"]["inputs"]["text"] = prompt; g["4"]["inputs"]["text"] = NEG
    g["9"]["inputs"].update(width=w, height=h, length=length); g["25"]["inputs"]["frames_number"] = length
    g["13"]["inputs"]["noise_seed"] = seed; g["19"]["inputs"]["filename_prefix"] = "xenoform/v4"
    return {"graph": g, "inputs": {"6": a, "7": b}, "secs": length / 24}

JOBS = {
 "origami": morph("One continuous physical transformation, no dissolve: a folded white paper origami crane on pure black "
    "unfolds its creases, its wings lengthen into scaled paper wings, the neck stretches and the head sprouts horns, "
    "paper folds ripple along a long tail, becoming a folded paper origami dragon. Single object centred, slow orbit, studio rim light.",
    CO / "v31_still_origami_a_00001_.png", CO / "v31_still_origami_b_00001_.png", 4401),
}
def polly(drive, seed, w=576, h=1024):
    sys.path.insert(0, "work/polly_v3"); from xenoform import moves as M
    app = ("A beautiful 22-year-old adult woman with fair light skin, light natural freckles, grey-blue eyes and a warm friendly smile, "
        "a soft messy chin-length ash-silver bob with one thin teal streak at the front. She wears an oversized white cropped bomber jacket "
        "with thin teal piping, a plain white t-shirt, light blue wide-leg jeans and white sneakers. Slender, realistic adult proportions")
    g = M.graph(app, M.clip(drive.split("_")[1] if False else "px_8688817"), seed=seed,
                style="closed-mouth smile, calm expression, anatomically correct hands with five fingers, relaxed natural fingers, sharp face")
    g["15"]["inputs"].update(width=w, height=h); g["17"]["inputs"]["steps"] = 8; g["19"]["inputs"]["noise_seed"] = seed
    g["31"]["inputs"]["filename_prefix"] = "xenoform/v4_polly"
    return {"graph": g, "inputs": {"9": IN / "polly_576.png", "10": Path("work/polly_v3") / drive}, "secs": 81 / 24 * 3}

IN = Path("work/v4/in")
JOBS["mcp_koi"] = morph("A glass koi fish made of clear iridescent glass swims in a slow graceful arc on pure black, caustic light ripples "
    "through its fins and tail, fine refraction detail, crisp focus, one continuous shot, centred.", IN / "koi_a.png", IN / "koi_b.png", 4402)
JOBS["stem_ferro"] = morph("A chrome ferrofluid sculpture on pure black pulses and spikes rhythmically as if driven by bass, mirror reflections, "
    "spikes rise and fall, crisp focus, centred, slow orbit.", IN / "ferro_a.png", IN / "ferro_a.png", 4403)
JOBS["polly_lively"] = polly("drive_px_8688817_68.mp4", 921)
JOBS["polly_hands"] = polly("drive_px_8377696_20.mp4", 922)
def origami2(seed, end_strength):
    j = morph("Stop-motion style physical paper folding, no dissolve, no transparency, no double exposure: a single golden paper origami crane "
        "on pure black; its paper physically refolds in visible steps, the wings bend and grow pointed membranes, the neck shortens, two horns "
        "fold up from the head, the tail extends into a zigzag of folds, becoming a golden origami dragon. One solid opaque object the whole time.",
        CO / "v31_still_origami_a_00001_.png", CO / "v31_still_origami_b_00001_.png", seed, length=145)
    j["graph"]["22"]["inputs"]["strength"] = end_strength; j["graph"]["4"]["inputs"]["text"] += ", ghosting, semi-transparent, crossfade, morphing blend"
    return j
JOBS2 = {"origami_s1": origami2(5511, 0.55), "origami_s2": origami2(5512, 0.75)}
if "--round2" in sys.argv: JOBS = JOBS2


def log(**kw):
    kw["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    open(LEDGER, "a", encoding="utf-8").write(json.dumps(kw, default=str) + "\n"); print("LEDGER", json.dumps(kw, default=str))

def spent():
    if not LEDGER.exists(): return 0.0
    return sum(json.loads(l).get("est_usd", 0) for l in open(LEDGER) if '"step": "done"' in l or '"step": "failed"' in l and 'Nothing was sent' not in l)

def main():
    a = sys.argv[1] if len(sys.argv) > 1 else "-"; dry = "--dry" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    if a != "-" and Path(a).is_file():
        os.environ["COMFY_ORG_API_KEY"] = Path(a).read_bytes().decode("utf-8-sig", "ignore").strip().strip("\x00"); Path(a).unlink()
    print("key loaded:", bool(os.environ.get("COMFY_ORG_API_KEY")), "len", len(os.environ.get("COMFY_ORG_API_KEY", "")))
    be = CloudBackend.from_config(load_config(None))
    for name, j in JOBS.items():
        if only and name != only: continue
        be.prepare(j["graph"])  # guard: raises on partner nodes / unmapped models
        est = round(j["secs"] * USD_PER_S, 3)
        if dry: print("DRY OK", name, "est US$", est); continue
        if spent() + est > CAP: log(step="refused_cap", job=name, est_usd=est, spent=spent()); continue
        log(step="submit", job=name, est_usd=est)
        try:
            files = be.run(j["graph"], OUT / name, inputs={k: Path(v) for k, v in j["inputs"].items()})
            log(step="done", job=name, est_usd=est, files=[str(f) for f in files])
        except Exception as e:
            log(step="failed", job=name, est_usd=est, error=str(e)[:300])
    print("SPENT_EST_USD", round(spent(), 3))

if __name__ == "__main__":
    main()



