"""FREE local previews of the LTX-2.5 shortlist with our own LTX 0.9.5 morph graph.

Same first/last stills as the paid partner render, through
``workflows/xenoform_morph.json`` on the local GPU (comfy-sdk -> comfy-api-proxy).
Refuses to submit any graph that contains a partner/API node.

    python scripts/ltx25_partner/preview.py            # all entries
    python scripts/ltx25_partner/preview.py X01 X04
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from render import get_json, load_shortlist  # noqa: E402

GRAPH = ROOT / "workflows" / "xenoform_morph.json"
NEG = "text, letters, watermark, logo, two objects, cut, flicker, blurry, low quality, cartoon, people, hands, face"


def assert_free(graph: dict, comfy: str) -> None:
    for nid, node in graph.items():
        cls = node["class_type"]
        info = get_json(f"{comfy}/object_info/{cls}").get(cls, {})
        if info.get("api_node") or "api" in cls.lower():
            raise SystemExit(f"REFUSED: node {nid} {cls} is a paid partner/API node.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--size", default="512x288")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--comfy", default="http://127.0.0.1:8188")
    ap.add_argument("--proxy", default="http://127.0.0.1:8189")
    ap.add_argument("--out", default=str(ROOT / "judge_logs" / "ltx25_partner" / "previews"))
    args = ap.parse_args(argv)

    entries = [e for e in load_shortlist() if not args.ids or e["id"] in args.ids]
    w, h = (int(x) for x in args.size.split("x"))
    frames = int(round(args.seconds * 24))
    length = ((frames - 1 + 7) // 8) * 8 + 1  # LTX wants 8n+1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    os.environ["COMFY_BASE_URL"] = args.proxy
    os.environ.pop("COMFY_API_KEY", None)
    from comfy_sdk import Comfy, JobFailed

    client = Comfy(timeout=None)
    base = json.loads(GRAPH.read_text(encoding="utf-8"))
    assert_free(base, args.comfy)
    log = []
    for e in entries:
        t0 = time.time()
        wf = client.workflows.from_json(json.loads(json.dumps(base)))
        wf.set_input("6", "image", client.assets.from_file(str(ROOT / e["from"])))
        wf.set_input("7", "image", client.assets.from_file(str(ROOT / e["to"])))
        wf.set_input("3", "text", e["preview_prompt"])
        wf.set_input("4", "text", NEG)
        wf.set_input("9", "width", w)
        wf.set_input("9", "height", h)
        wf.set_input("9", "length", length)
        wf.set_input("11", "steps", args.steps)
        wf.set_input("13", "noise_seed", int(e.get("seed", 2727)))
        wf.set_input("19", "filename_prefix", f"xenoform/ltx25_preview/{e['id']}")
        job = client.submit(wf)  # no api_key: a free local graph
        result = None
        for attempt in range(6):
            try:
                result = job.result()
                break
            except JobFailed as exc:  # proxy 0.1.6 transient "expired"
                if "expired" not in str(exc) or attempt == 5:
                    raise
                time.sleep(1 + attempt)
                job = client.jobs.get(job.id)
        outs = list(result.get_outputs("19")) or list(result.outputs)
        raw = out / f"{e['id']}_raw.mp4"
        outs[0].to_file(str(raw))
        final = out / f"{e['id']}_preview_ltx095.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-vf", "scale=768:432:flags=lanczos",
                        "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(final)],
                       check=True)
        raw.unlink(missing_ok=True)
        secs = round(time.time() - t0, 1)
        log.append({"id": e["id"], "file": str(final), "seconds": secs, "frames": length, "size": args.size})
        print(f"{e['id']}: {final.name} in {secs}s", flush=True)
    (out / "previews.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
