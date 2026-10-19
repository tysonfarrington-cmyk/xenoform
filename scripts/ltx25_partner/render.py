"""LTX-2.5 partner-node A->B morph (first/last frame) through comfy-sdk + comfy-api-proxy.

PAID PATH. ``LtxApi25ImageToVideo`` runs on Lightricks' servers and spends
Comfy credits from the account whose API key is sent with the job. This is an
Add-on, not the default open-weights path (see ``xenoform.eligibility``).

Default is a dry run: the graph is built and validated locally against
ComfyUI's ``/object_info`` (read-only GETs; nothing is queued, nothing is
uploaded, no credits move) and the exact cost is printed from the node's own
price table. Only ``--confirm`` submits, one entry at a time, under a price cap.

    python scripts/ltx25_partner/render.py --list
    python scripts/ltx25_partner/render.py X01                 # dry run
    python scripts/ltx25_partner/render.py --all               # dry run every entry
    python scripts/ltx25_partner/render.py X01 --model pro --duration 6
    python scripts/ltx25_partner/render.py --balance           # free read, needs the key
    python scripts/ltx25_partner/render.py X01 --confirm       # PAID: one render

Auth: ComfyUI reads partner auth from the /prompt body's ``extra_data``
(``auth_token_comfy_org`` from a signed-in browser tab, or
``api_key_comfy_org``). A browser sign-in does not carry over to API/SDK
submits, and comfy-api-proxy 0.1.6 forwards only ``api_key_comfy_org``. So a
paid run needs a Comfy API key (platform.comfy.org -> API keys) in the
environment variable named by ``--key-env`` (default ``COMFY_ORG_API_KEY``).
It is sent as ``submit(..., api_key=...)`` and never printed or logged.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GRAPH = ROOT / "workflows" / "ltx25_partner_flf_api.json"
SHORTLIST = HERE / "shortlist.json"
NODE = "LtxApi25ImageToVideo"
NODE_ID, FIRST_ID, LAST_ID, SAVE_ID = "3", "1", "2", "4"
MODELS = {"fast": "LTX-2.5 (Fast)", "pro": "LTX-2.5 (Pro)"}
CREDITS_PER_USD = 211.0  # docs.comfy.org partner pricing: 211 credits = US$1
AUD_PER_USD = 1.44
DEFAULT_MAX_USD = 1.10
# Fallback only; the live table is parsed from the node's price_badge.
FALLBACK_PRICES = {
    "ltx-2.5 (fast)": {"1280x720": 0.1287, "720x1280": 0.1287, "1920x1080": 0.1859, "1080x1920": 0.1859,
                        "2560x1440": 0.2717, "1440x2560": 0.2717, "3840x2160": 0.429, "2160x3840": 0.429},
    "ltx-2.5 (pro)": {"1280x720": 0.1716, "720x1280": 0.1716, "1920x1080": 0.2431, "1080x1920": 0.2431},
}


def get_json(url: str, timeout: float = 20.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:  # GET only
        return json.loads(r.read().decode("utf-8"))


def object_info(comfy: str, classes: list[str]) -> dict:
    info = {}
    for name in classes:
        try:
            info.update(get_json(f"{comfy.rstrip('/')}/object_info/{name}"))
        except urllib.error.HTTPError:
            pass
    return info


def price_table(node_info: dict) -> tuple[dict, str]:
    """USD per second by model and resolution, read from the node's own price badge."""
    expr = ((node_info or {}).get("price_badge") or {}).get("expr") or ""
    table = {}
    for model, body in re.findall(r'"(ltx-2\.5 \((?:fast|pro)\))"\s*:\s*\{([^}]*)\}', expr):
        table[model] = {res: float(v) for res, v in re.findall(r'"(\d+x\d+)"\s*:\s*([0-9.]+)', body)}
    if table:
        return table, "live price_badge from /object_info"
    return FALLBACK_PRICES, "fallback table (price_badge not parsed)"


def cost(table: dict, model_label: str, resolution: str, duration: int) -> dict:
    pps = table.get(model_label.lower(), {}).get(resolution)
    if pps is None:
        raise ValueError(f"no price for {model_label} at {resolution}")
    usd = pps * int(duration)
    return {"usd_per_s": pps, "seconds": int(duration), "usd": round(usd, 4),
            "credits": round(usd * CREDITS_PER_USD, 1), "aud": round(usd * AUD_PER_USD, 2)}


def load_shortlist() -> list[dict]:
    return json.loads(SHORTLIST.read_text(encoding="utf-8"))["entries"]


def build_graph(entry: dict, model: str, duration: int, resolution: str, fps: int, seed: int) -> dict:
    g = json.loads(GRAPH.read_text(encoding="utf-8"))
    n = g[NODE_ID]["inputs"]
    n["model"] = MODELS[model]
    n["model.duration"] = str(duration)
    n["model.resolution"] = resolution
    n["model.fps"] = str(fps)
    n["model.generate_audio"] = False  # our own music goes on top; price does not depend on it
    n["prompt"] = entry["prompt"]
    n["seed"] = int(seed)
    g[FIRST_ID]["inputs"]["image"] = Path(entry["from"]).name
    g[LAST_ID]["inputs"]["image"] = Path(entry["to"]).name
    g[SAVE_ID]["inputs"]["filename_prefix"] = f"xenoform/ltx25_partner/{entry['id']}"
    return g


def _spec(info: dict, cls: str, name: str):
    inp = info[cls]["input"]
    for sect in ("required", "optional"):
        if name in inp.get(sect, {}):
            return sect, inp[sect][name]
    return None, None


def _check_value(label: str, spec, value, errors: list[str]):
    kind, opts = spec[0], (spec[1] if len(spec) > 1 else {}) or {}
    if isinstance(kind, list):
        kind, opts = "COMBO", {"options": kind}
    if kind == "COMBO":
        options = [str(o) for o in opts.get("options", [])]
        if options and str(value) not in options:
            errors.append(f"{label}: {value!r} not in {options}")
    elif kind == "INT":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{label}: expected INT, got {value!r}")
        elif not (opts.get("min", value) <= value <= opts.get("max", value)):
            errors.append(f"{label}: {value} outside [{opts.get('min')}, {opts.get('max')}]")
    elif kind == "BOOLEAN" and not isinstance(value, bool):
        errors.append(f"{label}: expected BOOLEAN, got {value!r}")
    elif kind == "STRING" and not isinstance(value, str):
        errors.append(f"{label}: expected STRING, got {value!r}")


def _check_dynamic(label: str, key: str, spec, inputs: dict, errors: list[str]) -> None:
    """A COMFY_DYNAMICCOMBO_V3 input: the chosen key, then its nested inputs as ``key.sub``."""
    val = inputs[key]
    options = {o["key"]: o for o in spec[1]["options"]}
    if val not in options:
        errors.append(f"{label}.{key}: {val!r} not in {list(options)}")
        return
    for sub, subspec in (options[val].get("inputs") or {}).get("required", {}).items():
        full = f"{key}.{sub}"
        if full not in inputs:
            errors.append(f"{label}: missing {full!r}")
        elif subspec[0] == "COMFY_DYNAMICCOMBO_V3":
            _check_dynamic(label, full, subspec, inputs, errors)
        else:
            _check_value(f"{label}.{full}", subspec, inputs[full], errors)


def validate(graph: dict, info: dict) -> list[str]:
    """Local mirror of ComfyUI's prompt validation for this graph. No request is sent."""
    errors: list[str] = []
    for nid, node in graph.items():
        cls = node.get("class_type")
        if cls not in info:
            errors.append(f"node {nid}: class {cls!r} is not installed")
            continue
        inputs = node.get("inputs", {})
        decl = info[cls]["input"]
        for name, spec in decl.get("required", {}).items():
            if name not in inputs:
                errors.append(f"node {nid} {cls}: missing required input {name!r}")
                continue
            val = inputs[name]
            if spec[0] == "COMFY_DYNAMICCOMBO_V3":
                _check_dynamic(f"node {nid} {cls}", name, spec, inputs, errors)
                continue
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                continue  # link, checked below
            if cls == "LoadImage" and name == "image":
                continue  # uploaded at submit time; file existence checked separately
            _check_value(f"node {nid} {cls}.{name}", spec, val, errors)
        for name, val in inputs.items():
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                src, idx = val
                if src not in graph:
                    errors.append(f"node {nid}.{name}: links to missing node {src}")
                    continue
                outs = info.get(graph[src]["class_type"], {}).get("output", [])
                sect, spec = _spec(info, cls, name)
                if idx >= len(outs):
                    errors.append(f"node {nid}.{name}: node {src} has no output {idx}")
                elif spec is not None and outs[idx] != spec[0]:
                    errors.append(f"node {nid}.{name}: type {outs[idx]} -> expects {spec[0]}")
    return errors


def image_size(path: Path) -> tuple[int, int]:
    """Width and height of a PNG or JPEG without Pillow."""
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        seg = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + seg
    raise ValueError("unknown image format")


def image_checks(entry: dict, resolution: str) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    w, h = (int(x) for x in resolution.split("x"))
    for key in ("from", "to"):
        p = ROOT / entry[key]
        if not p.is_file():
            errors.append(f"{key} still missing: {entry[key]}")
            continue
        try:
            iw, ih = image_size(p)
            if abs(iw / ih - w / h) > 0.02:
                notes.append(f"{key} still is {iw}x{ih}; aspect differs from {resolution}")
            else:
                notes.append(f"{key} still {iw}x{ih} ok for {resolution}")
        except Exception as exc:  # PIL missing is not fatal
            notes.append(f"{key} still present (size not read: {exc.__class__.__name__})")
    return errors, notes


def plan(entry: dict, args, info: dict, table: dict) -> dict:
    model = args.model or entry.get("model", "fast")
    duration = int(args.duration or entry.get("duration", 5))
    resolution = args.resolution or entry.get("resolution", "1280x720")
    fps = int(args.fps or entry.get("fps", 24))
    seed = int(args.seed if args.seed is not None else entry.get("seed", 2727))
    graph = build_graph(entry, model, duration, resolution, fps, seed)
    errors = validate(graph, info)
    img_err, notes = image_checks(entry, resolution)
    errors += img_err
    price = cost(table, MODELS[model], resolution, duration)
    paid = [nid for nid, n in graph.items() if info.get(n["class_type"], {}).get("api_node")]
    return {"id": entry["id"], "from": entry["from"], "to": entry["to"], "model": MODELS[model],
            "duration": duration, "resolution": resolution, "fps": fps, "seed": seed,
            "paid_nodes": [f"{nid}:{graph[nid]['class_type']}" for nid in paid],
            "cost": price, "valid": not errors, "errors": errors, "notes": notes, "graph": graph}


def show(p: dict) -> None:
    c = p["cost"]
    print(f"[{p['id']}] {p['model']} {p['resolution']} {p['duration']}s @{p['fps']}fps seed {p['seed']}")
    print(f"    {Path(p['from']).name} -> {Path(p['to']).name}")
    print(f"    graph: {'VALID' if p['valid'] else 'INVALID'}; paid nodes: {', '.join(p['paid_nodes']) or 'none'}")
    for e in p["errors"]:
        print(f"    ERROR {e}")
    for n in p["notes"]:
        print(f"    note  {n}")
    print(f"    cost: {c['seconds']}s x US${c['usd_per_s']}/s = US${c['usd']:.4f} = {c['credits']} credits = A${c['aud']:.2f}")


def balance(args) -> int:
    key = os.environ.get(args.key_env, "").strip()
    if not key:
        print(f"No key in ${args.key_env}; balance needs a Comfy API key (or check ComfyUI Settings > Credits).")
        return 2
    req = urllib.request.Request("https://api.comfy.org/customers/balance", headers={"X-API-KEY": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"balance read failed: HTTP {exc.code}")
        return 1
    print(json.dumps(data, indent=1))
    return 0


def submit(p: dict, args, entry: dict) -> int:
    key = os.environ.get(args.key_env, "").strip()
    if not key:
        print(f"REFUSED: no Comfy API key in ${args.key_env}. Nothing was submitted.")
        return 2
    if p["cost"]["usd"] > args.max_usd:
        print(f"REFUSED: US${p['cost']['usd']:.2f} is over --max-usd {args.max_usd:.2f}. Nothing was submitted.")
        return 2
    os.environ["COMFY_BASE_URL"] = args.proxy
    os.environ.pop("COMFY_API_KEY", None)  # the proxy takes no bearer; the partner key rides in extra_data
    from comfy_sdk import Comfy

    client = Comfy(timeout=None)
    wf = client.workflows.from_json(copy.deepcopy(p["graph"]))
    wf.set_input(FIRST_ID, "image", client.assets.from_file(str(ROOT / entry["from"])))
    wf.set_input(LAST_ID, "image", client.assets.from_file(str(ROOT / entry["to"])))
    print(f"SUBMITTING PAID RENDER {p['id']}: US${p['cost']['usd']:.4f} ({p['cost']['credits']} credits)")
    t0 = time.time()
    job = client.submit(wf, api_key=key)
    result = job.result()
    outs = list(result.get_outputs(SAVE_ID)) or list(result.outputs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{p['id']}_{p['model'].split('(')[1][:-1].lower()}_{p['duration']}s.mp4"
    outs[0].to_file(str(dest))
    rec = {k: v for k, v in p.items() if k != "graph"}
    rec.update({"job": job.id, "file": str(dest), "seconds": round(time.time() - t0, 1),
                "at": datetime.now(timezone.utc).isoformat()})
    with open(out_dir / "ledger.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"saved {dest} in {rec['seconds']}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entry", nargs="?", help="shortlist id, e.g. X01")
    ap.add_argument("--all", action="store_true", help="dry-run every shortlist entry")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--balance", action="store_true", help="read the credit balance (free; needs the key)")
    ap.add_argument("--model", choices=sorted(MODELS))
    ap.add_argument("--duration", type=int)
    ap.add_argument("--resolution")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--comfy", default="http://127.0.0.1:8188", help="ComfyUI, read-only /object_info")
    ap.add_argument("--proxy", default="http://127.0.0.1:8189", help="comfy-api-proxy (submit path)")
    ap.add_argument("--key-env", default="COMFY_ORG_API_KEY")
    ap.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    ap.add_argument("--out", default=str(ROOT / "judge_logs" / "ltx25_partner"))
    ap.add_argument("--json", help="write the dry-run report here")
    ap.add_argument("--confirm", action="store_true", help="PAID: actually submit this one entry")
    args = ap.parse_args(argv)

    entries = load_shortlist()
    if args.list:
        for e in entries:
            print(f"{e['id']}  {Path(e['from']).stem} -> {Path(e['to']).stem}  ({e['vibe']}; {e['lineage']})")
        return 0
    if args.balance:
        return balance(args)
    if args.confirm and (args.all or not args.entry):
        print("REFUSED: --confirm takes exactly one entry id, never --all.")
        return 2
    chosen = entries if args.all else [e for e in entries if e["id"].lower() == (args.entry or "").lower()]
    if not chosen:
        ap.error("give an entry id (see --list) or --all")

    info = object_info(args.comfy, [NODE, "LoadImage", "SaveVideo"])
    if NODE not in info:
        print(f"{NODE} is not available on {args.comfy}.")
        return 1
    table, source = price_table(info[NODE])
    print(f"DRY RUN: validated locally against {args.comfy}/object_info; prices: {source}.")
    print("Nothing is queued or uploaded and no credits are spent without --confirm.\n")
    plans = [plan(e, args, info, table) for e in chosen]
    for p in plans:
        show(p)
    total = sum(p["cost"]["usd"] for p in plans)
    if len(plans) > 1:
        print(f"\nTOTAL if every entry ran once: US${total:.2f} = {total * CREDITS_PER_USD:.0f} credits = A${total * AUD_PER_USD:.2f}")
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps({"price_source": source, "plans": plans}, indent=1), encoding="utf-8")
    if not all(p["valid"] for p in plans):
        return 1
    if not args.confirm:
        print("\nDry run only. Re-run one entry with --confirm to spend credits.")
        return 0
    return submit(plans[0], args, chosen[0])


if __name__ == "__main__":
    sys.exit(main())
