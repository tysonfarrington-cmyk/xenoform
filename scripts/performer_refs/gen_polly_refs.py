"""Polly reference stills posed at the kit, the mic, the keys, with a guitar and dancing (24 Oct 2026).

Z-Image Turbo (text-to-image, open weights) through comfy-sdk -> comfy-api-proxy on :8189, the same path as
scripts/vibe_objects/gen_extended.py with the graph scripts/vibe_objects/zimage_t2i_api.json. Text-to-image
cannot copy a face, so every pose is rendered at several seeds and the closest likeness to polly.png is picked
by eye from the contact sheets; the pick is cover-cropped to 576x1024 and saved beside polly.png as
src/xenoform/ui_static/performer/polly_<performance>.png, which performer.default_reference(instrument)
hands to MiniMax H3 for that performance (so the shot opens on her already at the instrument).

usage: gen_polly_refs.py OUTDIR [--seeds 8] [--only drums,dance] [--seed0 7000]
    -> OUTDIR/raw/<performance>_<variant>_<seed>.png and OUTDIR/<performance>_sheet.jpg (labelled)
"""
import argparse
import json
import os
import time
from pathlib import Path

os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8189"
os.environ.pop("COMFY_API_KEY", None)
from comfy_sdk import Comfy  # noqa: E402

HERE = Path(__file__).resolve().parent
GRAPH = HERE.parent / "vibe_objects" / "zimage_t2i_api.json"
PROMPTS = HERE / "polly_prompts.json"
W, H = 768, 1344  # portrait, near the H3 render's 480x832


def sheet(paths: list[Path], out: Path, cols: int = 4, thumb=(192, 336)) -> None:
    from PIL import Image, ImageDraw

    rows = (len(paths) + cols - 1) // cols
    board = Image.new("RGB", (cols * thumb[0], rows * thumb[1]), (20, 20, 20))
    draw = ImageDraw.Draw(board)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail(thumb)
        x, y = (i % cols) * thumb[0], (i // cols) * thumb[1]
        board.paste(im, (x, y))
        label = p.stem.split("_", 1)[1]
        draw.rectangle([x, y, x + 8 + 7 * len(label), y + 16], fill=(0, 0, 0))
        draw.text((x + 4, y + 2), label, fill=(255, 255, 80))
    board.save(out, quality=88)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--seed0", type=int, default=7000)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    out = Path(a.out)
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    spec = json.loads(PROMPTS.read_text(encoding="utf-8"))
    only = {s.strip() for s in a.only.split(",") if s.strip()}
    c = Comfy(client_info="xenoform-polly", timeout=None)
    t0 = time.time()
    jobs = []
    for perf, scenes in spec["performances"].items():
        if only and perf not in only:
            continue
        for v, scene in enumerate(scenes):
            prompt = spec["base"].replace("{scene}", scene)
            for k in range(a.seeds):
                seed = a.seed0 + 100 * v + k
                dst = raw / f"{perf}_{v}_{seed}.png"
                if dst.exists():
                    continue
                wf = c.workflows.from_file(str(GRAPH))
                wf.set_input("5", "text", prompt)
                wf.set_input("10", "seed", seed)
                wf.set_input("7", "width", W)
                wf.set_input("7", "height", H)
                wf.set_input("12", "filename_prefix", "xenoform/polly")
                jobs.append((dst, c.submit(wf)))
    print("queued", len(jobs), flush=True)
    for dst, j in jobs:
        r = j.result()
        o = list(r.get_outputs("12")) or list(r.outputs)
        o[0].to_file(str(dst))
        print(dst.name, f"+{time.time() - t0:.0f}s", flush=True)
    for perf in spec["performances"]:
        if only and perf not in only:
            continue
        paths = sorted(raw.glob(f"{perf}_*.png"))
        if paths:
            sheet(paths, out / f"{perf}_sheet.jpg")
    print("DONE", round(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
