"""1-clip Comfy Cloud smoke test (LTX-2.3 Final morph, no upscale; upscaling stays local).

  # free, no GPU: checks key, nodes and model names against Cloud's /api/object_info
  .venv\\Scripts\\python scripts\\cloud_smoke.py --preflight
  # ONE real job (~5 s clip, spends a few Cloud credits). Needs --yes.
  .venv\\Scripts\\python scripts\\cloud_smoke.py --run --yes --a first.png --b last.png

Key comes from COMFY_ORG_API_KEY and is never printed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from xenoform import cloud_backend as cb  # noqa: E402
from xenoform import final_tier as ft  # noqa: E402

PROMPT = ("a smooth biomechanical morph, iridescent chrome surface flowing into a new form, "
          "studio lighting, black background, cinematic")


def smoke_graph(seconds: float) -> dict:
    fps = int(getattr(ft, "FPS", 24))
    length = int(round(seconds * fps / 8)) * 8 + 1
    return ft.graph(PROMPT, length=length, seed=4242, upscale=False, prefix="xenoform/cloud_smoke")


def combo_options(spec) -> list | None:
    """Option list for both object_info styles: [[...], {..}] and ["COMBO", {"options": [...]}]."""
    if not isinstance(spec, list) or not spec:
        return None
    if isinstance(spec[0], list):
        return spec[0]
    if len(spec) > 1 and isinstance(spec[1], dict) and isinstance(spec[1].get("options"), list):
        return spec[1]["options"]
    return None


def preflight(b: cb.CloudBackend, g: dict) -> list[str]:
    info = b.object_info()
    issues = []
    for nid, node in g.items():
        ct = node["class_type"]
        spec = info.get(ct)
        if spec is None:
            issues.append(f"node {nid}: {ct} not available on Cloud")
            continue
        req = {**(spec.get("input", {}).get("required") or {}), **(spec.get("input", {}).get("optional") or {})}
        for k, v in node["inputs"].items():
            if k in cb.MODEL_FIELDS and isinstance(v, str) and k in req:
                opts = combo_options(req[k])
                if isinstance(opts, list) and v not in opts:
                    near = [o for o in opts if isinstance(o, str) and v.split(".")[0][:10] in o][:5]
                    issues.append(f"node {nid} {ct}.{k}: '{v}' not in Cloud library; close: {near}")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="confirm ONE paid Cloud job")
    ap.add_argument("--a", type=Path)
    ap.add_argument("--b", type=Path)
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "cloud_smoke")
    a = ap.parse_args()

    b = cb.CloudBackend()
    g = b.prepare(smoke_graph(a.seconds), open_weights=True)  # guard + model map, local only
    print(f"graph OK: {len(g)} nodes, no partner/upscale nodes; models: "
          f"{sorted({v for n in g.values() for k, v in n['inputs'].items() if k in cb.MODEL_FIELDS})}")
    if not (a.preflight or a.run):
        print("dry: nothing sent. Use --preflight or --run --yes.")
        return 0
    issues = preflight(b, g)
    for i in issues:
        print("PREFLIGHT:", i)
    if issues:
        print("Fix configs/cloud_models.json (or import the model on Creator) before --run.")
        return 2
    print("preflight OK: every node and model exists on Comfy Cloud")
    if not a.run:
        return 0
    if not a.yes:
        print("Refusing to spend credits without --yes.")
        return 3
    if not (a.a and a.b and a.a.exists() and a.b.exists()):
        print("--run needs --a and --b first/last frame images.")
        return 4
    t = time.time()
    files = b.run(g, a.out, inputs={"100": a.a, "101": a.b}, open_weights=True)
    print(f"done in {time.time() - t:.0f}s wall: " + ", ".join(str(f) for f in files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
