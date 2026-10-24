"""Thirty-six more objects for each featured vibe (24 Oct 2026): Z-Image Turbo through comfy-sdk -> comfy-api-proxy
(:8189), the same path and graph as gen_extended.py, one still per (vibe, noun) at 1024x576.

Each vibe's prompt is its own ``still_style`` from configs/vibes.json plus a subject sentence in that vibe's
material; the nouns come from NOUNS (botanical gets flowers) minus whatever the vibe already owns in
ui_static/objects/objects.json. The stills land in OUTDIR/<vibe>/NN_noun.png with a labelled contact sheet
per vibe (OUTDIR/<vibe>_sheet.jpg) and a README for the cull; Wednesday's wiring copies the keepers into
ui_static/objects/<vibe>/ as graded jpgs and adds their objects.json rows.

usage: gen_v2.py OUTDIR [--vibes a,b] [--count 36] [--seed0 5000]
"""
import argparse
import json
import re
import time
from pathlib import Path

import os

os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8189"
os.environ.pop("COMFY_API_KEY", None)
from comfy_sdk import Comfy  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GRAPH = HERE / "zimage_t2i_api.json"
VIBES = ROOT / "configs" / "vibes.json"
OBJECTS = ROOT / "src" / "xenoform" / "ui_static" / "objects" / "objects.json"
W, H = 1024, 576

# Objects that read as one sculptural subject in any material, in a rough chain order (round things, then
# creatures, then made things); a vibe skips the ones it already owns and takes the first ``count``.
NOUNS = ["crescent moon", "snowflake", "faceted gem", "mobius strip", "dodecahedron", "hourglass", "spinning top", "pocket watch",
         "rose", "tulip", "dragonfly", "seahorse", "hummingbird", "koi fish", "octopus", "chameleon",
         "chess knight", "violin", "saxophone", "vinyl record", "cassette tape", "headphones", "vintage microphone", "grand piano",
         "anchor", "compass", "lantern", "skeleton key", "origami crane", "paper boat", "hot air balloon", "spiral staircase",
         "pinecone", "coral branch", "antler", "bonsai tree", "teapot", "wine glass", "umbrella", "crown",
         "sculpted heart", "theatre mask", "lotus", "jellyfish", "feather", "butterfly", "conch shell", "nautilus"]
FLOWERS = ["rose", "tulip", "peony", "orchid", "lily", "dahlia", "sunflower", "chrysanthemum", "poppy", "iris", "hibiscus", "magnolia",
           "protea", "anemone", "ranunculus", "hydrangea", "carnation", "gardenia", "cherry blossom branch", "fern frond",
           "succulent rosette", "dandelion clock", "thistle", "calla lily", "bird of paradise", "passion flower", "water lily",
           "foxglove", "bluebell", "camellia", "marigold", "wisteria", "lavender sprig", "cactus flower", "snowdrop", "lotus",
           "lisianthus", "zinnia", "cosmos flower", "freesia"]

# The subject sentence per vibe, in the vibe's own material (still_style carries the light and the backdrop).
SUBJECT = {
    "chrome-mercury": "One single {noun} made of liquid mirror chrome.",
    "liquid-gold": "One single {noun} made of molten gold, polished where it has cooled.",
    "neon-noir": "One single {noun} made of black wet lacquered glass, catching the neon.",
    "porcelain-kintsugi": "One single {noun} made of glossy white porcelain with kintsugi gold seams.",
    "bioluminescent": "One single bioluminescent {noun}, glowing teal and violet from within.",
    "risograph": "A risograph print of one single {noun}.",
    "iridescent-glass": "One single {noun} made of hand-blown dichroic iridescent glass.",
    "ink-wash": "A sumi-e ink wash painting of one single {noun}.",
    "cyberspace-95": "One single {noun} as a glowing green wireframe low-poly model.",
    "wet-paint": "One single {noun} sculpted from thick wet swirling acrylic paint.",
    "shadow-self": "The backlit silhouette of one single {noun}, smoke curling around it.",
    "botanical": "One single {noun}, a macro timelapse photograph on pure black.",
}


def slug(noun: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", noun.lower()).strip("_")


def plan(vibes: list[str], count: int) -> dict[str, list[str]]:
    reg = json.loads(VIBES.read_text(encoding="utf-8"))
    entries = reg.get("vibes", reg)
    items = entries if isinstance(entries, list) else [dict(id=k, **v) for k, v in entries.items()]
    styles = {x["id"]: x.get("still_style") or x.get("look") for x in items}
    own = json.loads(OBJECTS.read_text(encoding="utf-8"))
    out = {}
    for vibe in vibes:
        have = {o["noun"].lower() for o in own.get(vibe, [])}
        pool = FLOWERS if vibe == "botanical" else NOUNS
        nouns = [n for n in pool if n.lower() not in have and n.lower().replace(" shell", "") not in have][:count]
        out[vibe] = {"style": styles[vibe], "nouns": nouns}
    return out


def sheet(paths: list[Path], labels: list[str], out: Path, cols: int = 6, thumb=(224, 126)) -> None:
    from PIL import Image, ImageDraw

    rows = (len(paths) + cols - 1) // cols
    board = Image.new("RGB", (cols * thumb[0], rows * (thumb[1] + 16)), (18, 18, 18))
    draw = ImageDraw.Draw(board)
    for i, (p, label) in enumerate(zip(paths, labels)):
        im = Image.open(p).convert("RGB")
        im.thumbnail(thumb)
        x, y = (i % cols) * thumb[0], (i // cols) * (thumb[1] + 16)
        board.paste(im, (x, y))
        draw.text((x + 4, y + thumb[1] + 2), label, fill=(255, 255, 80))
    board.save(out, quality=88)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--vibes", default="")
    ap.add_argument("--count", type=int, default=36)
    ap.add_argument("--seed0", type=int, default=5000)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    vibes = [v for v in a.vibes.split(",") if v] or list(SUBJECT)
    todo = plan(vibes, a.count)
    c = Comfy(client_info="xenoform-vibes-v2", timeout=None)
    t0 = time.time()
    jobs = []
    for vi, (vibe, spec) in enumerate(todo.items()):
        folder = out / vibe
        folder.mkdir(exist_ok=True)
        for i, noun in enumerate(spec["nouns"]):
            dst = folder / f"{i:02d}_{slug(noun)}.png"
            if dst.exists():
                continue
            prompt = f"{spec['style']} {SUBJECT[vibe].format(noun=noun)}"
            wf = c.workflows.from_file(str(GRAPH))
            wf.set_input("5", "text", prompt)
            wf.set_input("10", "seed", a.seed0 + 100 * vi + i)
            wf.set_input("7", "width", W)
            wf.set_input("7", "height", H)
            wf.set_input("12", "filename_prefix", "xenoform/vibes_v2")
            jobs.append((dst, c.submit(wf)))
    print("queued", len(jobs), "stills for", len(todo), "vibes", flush=True)
    for k, (dst, j) in enumerate(jobs):
        r = j.result()
        o = list(r.get_outputs("12")) or list(r.outputs)
        o[0].to_file(str(dst))
        if k % 12 == 11:
            print(f"{k + 1}/{len(jobs)} +{time.time() - t0:.0f}s", flush=True)
    for vibe, spec in todo.items():
        paths = sorted((out / vibe).glob("*.png"))
        if paths:
            sheet(paths, [p.stem for p in paths], out / f"{vibe}_sheet.jpg")
    (out / "README.txt").write_text(
        "Thirty-six new objects per featured vibe (Z-Image Turbo, 24 Oct 2026). One png per (vibe, noun) in <vibe>/, "
        "a labelled contact sheet per vibe in <vibe>_sheet.jpg.\n\nTo cull: delete the pngs you do not want (or move them "
        "into a 'no' folder). What is left in each <vibe>/ folder is what gets wired in as that vibe's own stills.\n"
        f"Made in {time.time() - t0:.0f} s.\n", encoding="utf-8")
    print("DONE", round(time.time() - t0), flush=True)


if __name__ == "__main__":
    main()
