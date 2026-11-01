"""An old Cloud Final cut's scene pairs rendered again on Cloud Final with the scene handling as it is now: the backdrops
set of the judged Cloud sets (docs/MUSIC_VIDEO_PLAN.md section 8, items 3 and 17), first run on 1 Nov on Tys's word.

No route re-renders an old cut's pairs, so this sends exactly those pairs through the Cloud Final path the desk uses
(``cloud_final.cloud_clips``: the morph cache first, the key and graph gate, no partner node, LTX-2.5 on Comfy Cloud),
each with the cut's recorded stills, seed (the cut's seed plus the shot's index), length and morph style. The prompt is
built by the code as it is now from the same inputs: a scene pair carries no portrait object sentence
(``portrait.suffix_for``), its scene guide goes uncompressed (``morph_pass.guide_compression``) and a scene still is
cropped for portrait, never crushed to black (``portrait.portrait_stills``). Every graph is checked against the one the
old clip recorded in its mp4: the prompt must be the recorded prompt (less the portrait sentence on a 9:16 cut), and the
seed, length, end guide, size, negative and models the recorded ones.

It spends Comfy Cloud credits only behind its tick: without ``--spend`` nothing is sent, the graphs are built and
checked and the plan printed (a dry run, with the morph cache moved aside). With ``--spend`` each pair gets at most
``--tries`` sends (2); the first pair failing on every try stops the run (exit 3), and so does any later pair (exit 4).
The Comfy key is read from the environment by ``cloud_backend`` and never printed or written.

    python docs/demo/tools/cloud_scene_pairs.py --job work/ui/jobs/<job id> --stills <folder of <vibe>/<file> stills> \
        --out <work folder> [--pairs 0,3] [--spend]

``--job`` is a copy of the old cut's job folder (``simple/simple.json``, ``simple/chain.json`` and its ``cloudNN.mp4``);
``--stills`` holds the stills the shipped set lacks (grown ones), the rest are found in the shipped set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def recorded_graph(clip: Path) -> dict:
    """The graph ComfyUI wrote into the clip's mp4 (its ``prompt`` tag)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json", str(clip)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(json.loads(out)["format"]["tags"]["prompt"])


def graph_facts(g: dict) -> dict:
    return {
        "prompt": g["3"]["inputs"]["text"],
        "negative": g["4"]["inputs"]["text"],
        "seed": int(g["13"]["inputs"]["noise_seed"]),
        "length": int(g["9"]["inputs"]["length"]),
        "size": [int(g["9"]["inputs"]["width"]), int(g["9"]["inputs"]["height"])],
        "img_compression": [int(g["8"]["inputs"]["img_compression"]), int(g["21"]["inputs"]["img_compression"])],
        "end_strength": float(g["22"]["inputs"]["strength"]),
        "models": sorted(str(v) for n in g.values() if isinstance(n, dict)
                         for k, v in (n.get("inputs") or {}).items() if k in ("unet_name", "clip_name", "vae_name")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--job", required=True, help="the copied job folder (simple/simple.json, simple/chain.json, the old clips)")
    ap.add_argument("--stills", required=True, help="a folder holding the stills the shipped set lacks (<vibe>/<file>)")
    ap.add_argument("--out", required=True, help="the work folder for this run")
    ap.add_argument("--spend", action="store_true", help="the credits tick: send to Comfy Cloud (without it nothing is sent)")
    ap.add_argument("--tries", type=int, default=2, help="sends a pair may take at most (default 2)")
    ap.add_argument("--pairs", default="", help="comma list of shot indices (default: every pair that touches a scene)")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not args.spend:  # a dry run never touches the real morph cache
        os.environ["XENO_MORPH_CACHE"] = str(out / "dry_cache")

    from xenoform import cloud_backend as cb
    from xenoform import cloud_final
    from xenoform import morph_pass as mp
    from xenoform import portrait
    from xenoform import song_plan
    from xenoform.config import load_config
    from xenoform.stills import SHIPPED

    job = Path(args.job).resolve()
    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    chain = json.loads((job / "simple" / "chain.json").read_text(encoding="utf-8"))
    vibe = str(rec["vibe"])
    seed = int(rec["seed"])
    styles = list(rec.get("morph_styles") or [])
    shots = list(rec["shots"])
    vertical = str(rec.get("aspect") or "") == "9:16"
    state = {**dict(rec.get("recut_state") or {}), "cloud_final_ok": bool(args.spend)}
    if len(chain) != len(rec["stills"]) or len(shots) + 1 != len(rec["stills"]):
        raise SystemExit("the record's stills, chain and shots do not line up")

    rows = []
    for name, link in zip(rec["stills"], chain):
        local = Path(args.stills) / name
        path = local if local.is_file() else SHIPPED / name
        if not path.is_file():
            raise SystemExit(f"missing still {name}")
        rows.append({"file": name, "path": str(path.resolve()), "noun": link.get("noun"), "kind": link.get("kind") or "object",
                     "sha256": sha(path)})
    scene_pairs = [i for i in range(len(shots)) if "scene" in mp.pair_kinds(rows[i], rows[i + 1])]
    pairs = [int(p) for p in args.pairs.split(",") if p.strip()] if args.pairs.strip() else scene_pairs
    lo, hi = song_plan.CLOUD_CREDITS
    print(f"job {job.name}: {vibe}, {'9:16' if vertical else '16:9'}, seed {seed}, {len(shots)} morphs; scene pairs {scene_pairs}; "
          f"sending {pairs}", flush=True)
    print(f"estimate: {len(pairs)} Cloud Final morphs ({cloud_final.label()}), the desk's rate {lo} to {hi} credits a morph: "
          f"{round(len(pairs) * lo)} to {round(len(pairs) * hi)} credits; at most {args.tries} sends a pair", flush=True)

    class Recorder(cb.CloudBackend):
        """The desk's Comfy Cloud backend, unchanged, keeping a log of each send and of Comfy Cloud's record of each job."""

        def run(self, graph, out_dir, *, inputs=None, open_weights=True):
            entry = {"prepared": self.prepare(graph, open_weights=open_weights),
                     "inputs": {k: str(v) for k, v in (inputs or {}).items()}, "t0": time.time()}
            self.events.append(entry)
            if not args.spend:
                raise cb.CloudRefused("dry run: nothing sent")
            try:
                got = super().run(graph, out_dir, inputs=inputs, open_weights=open_weights)
                entry["ok"] = True
                return got
            except BaseException as exc:  # noqa: BLE001 - logged, then cloud_clips sees it as ever
                entry["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                raise
            finally:
                entry["t1"] = time.time()

        def submit(self, graph):
            pid = super().submit(graph)
            self.submits.append({"prompt_id": pid, "t": time.time()})
            if self.events:
                self.events[-1]["prompt_id"] = pid
            return pid

        def _json(self, method, path, payload=None):
            res = super()._json(method, path, payload)
            if method == "GET" and path.startswith("/api/jobs/"):
                self.jobs.append({"path": path, "job": res})
            return res

    cfg = load_config(None)
    backend = Recorder.from_config(cfg)
    backend.max_parallel = 1
    backend.events, backend.submits, backend.jobs = [], [], []

    def report(stage, frac, msg):
        print(f"  [{stage} {frac:.2f}] {msg}", flush=True)

    results = []
    status = 0
    for n, i in enumerate(pairs):
        a, b = rows[i], rows[i + 1]
        kinds = mp.pair_kinds(a, b)
        old_clip = job / "simple" / f"cloud{i:02d}.mp4"
        old = graph_facts(recorded_graph(old_clip))
        row = {"pair": i, "kinds": list(kinds), "stills": [a, b], "seed": seed + i, "style": styles[i] if i < len(styles) else "melt",
               "shot": shots[i], "old_clip": str(old_clip), "old": old, "tries": []}
        print(f"pair {i:02d}: {a['noun']} ({kinds[0]}) -> {b['noun']} ({kinds[1]}), seed {seed + i}, "
              f"{row['style']}, render {shots[i].get('render_s')} s", flush=True)
        done = False
        for attempt in range(1, max(1, args.tries) + 1):
            work = out / f"pair{i:02d}" / f"try{attempt}"
            mark = len(backend.events)
            sent_before = len(backend.submits)
            t0 = time.time()
            err = ""
            clip = None
            try:
                clips, notes = cloud_final.cloud_clips([dict(shots[i])], [dict(a), dict(b)], work, cfg, seed + i, vibe,
                                                       report=report if args.spend else None,  # a dry run has nothing back
                                                       draft=None, vertical=vertical, state=state,
                                                       styles=[row["style"]], backend=backend)
                clip = Path(clips[0])
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {str(exc)[:300]}"
            ev = backend.events[mark:]
            prepared = ev[0]["prepared"] if ev else None
            new = graph_facts(prepared) if prepared else None
            checks = {}
            if new:
                suffix = portrait.suffix_for(kinds) if vertical else ""
                checks = {
                    "prompt_is_recorded_less_portrait_sentence": old["prompt"] == new["prompt"] + (portrait.PROMPT_SUFFIX if vertical else ""),
                    "portrait_sentence_now": suffix,
                    "seed": old["seed"] == new["seed"], "length": old["length"] == new["length"],
                    "size": old["size"] == new["size"], "end_strength": old["end_strength"] == new["end_strength"],
                    "negative": old["negative"] == new["negative"], "models": old["models"] == new["models"],
                    "scene_guide_uncompressed": all(c == 0 for c, k in zip(new["img_compression"], kinds) if k == "scene"),
                }
            portraits = sorted((work / "portrait").glob("*.png")) if (work / "portrait").is_dir() else []
            tr = {"try": attempt, "work": str(work), "seconds": round(time.time() - t0, 1), "error": err,
                  "sent": len(backend.submits) - sent_before, "events": [{k: v for k, v in e.items() if k != "prepared"} for e in ev],
                  "new": new, "checks": checks, "clip": str(clip) if clip else "",
                  "portraits": [{"file": p.name, "sha256": sha(p)} for p in portraits]}
            row["tries"].append(tr)
            if not args.spend:
                print(f"  dry run: built, nothing sent; checks {json.dumps(checks)}", flush=True)
                print(f"  new compression {new and new['img_compression']} (old {old['img_compression']})", flush=True)
                done = True
                break
            if clip and clip.is_file():
                print(f"  back in {tr['seconds']} s: {clip} (sent {tr['sent']}); checks ok: "
                      f"{all(v for k, v in checks.items() if k != 'portrait_sentence_now')}", flush=True)
                row["clip"] = str(clip)
                done = True
                break
            print(f"  try {attempt} failed after {tr['seconds']} s: {err}; events {json.dumps(tr['events'])[:400]}", flush=True)
        results.append(row)
        (out / "report.json").write_text(json.dumps({"job": str(job), "vibe": vibe, "seed": seed, "pairs": pairs,
                                                     "spend": args.spend, "credits_rate": [lo, hi],
                                                     "estimate_credits": [round(len(pairs) * lo), round(len(pairs) * hi)],
                                                     "sent": len(backend.submits), "submits": backend.submits,
                                                     "jobs": backend.jobs, "results": results}, indent=1), encoding="utf-8")
        if not done:
            status = 3 if n == 0 else 4
            print(f"STOP: pair {i:02d} failed on all {args.tries} tries" + (" (the first pair: set 1 and set 2 stop)" if n == 0 else ""),
                  flush=True)
            break
    print(f"sent {len(backend.submits)} morphs to Comfy Cloud; report {out / 'report.json'}", flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
