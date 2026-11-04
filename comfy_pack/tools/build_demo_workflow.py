"""Write the demo workflow, in ComfyUI's UI format and its API format, from the node definitions.

    python comfy_pack/tools/build_demo_workflow.py          (writes comfy_pack/workflows/xenoform_demo.json and _api.json)
    python comfy_pack/tools/build_demo_workflow.py --check  (exits 1 when either file differs from what it would write)

The demo: the bundled demo song through Song analysis, Storyboard (Dense, two forms: a morph up to the drop and one
from it), the Morph Timeline, two Morph Pairs, each into the LTX 0.9.5 morph graph of ``workflows/xenoform_morph.json``
(the same nodes and values, with the pair's outputs where the desk sets inputs), and the Assemble. The stock nodes'
definitions are ComfyUI 0.33's own (``tests/fixtures/comfy_object_info_ltx095.json``), the pack's come from its classes,
so the widget order and the slots are the ones ComfyUI builds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
REPO = PACK.parent
STOCK = REPO / "tests" / "fixtures" / "comfy_object_info_ltx095.json"
OUT_UI = PACK / "workflows" / "xenoform_demo.json"
OUT_API = PACK / "workflows" / "xenoform_demo_api.json"
WIDGET_TYPES = ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO")
FRONTEND_ONLY = ("Note", "MarkdownNote")


def pack_defs() -> dict:
    """The pack's nodes in ``/object_info`` form (ComfyUI's ``node_info`` for a V1 node)."""
    sys.path.insert(0, str(REPO))
    from comfy_pack.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    out = {}
    for name, cls in NODE_CLASS_MAPPINGS.items():
        spec = cls.INPUT_TYPES()
        out[name] = {"input": spec, "input_order": {k: list(v) for k, v in spec.items() if k in ("required", "optional")},
                     "output": list(cls.RETURN_TYPES), "output_name": list(getattr(cls, "RETURN_NAMES", cls.RETURN_TYPES)),
                     "output_node": bool(getattr(cls, "OUTPUT_NODE", False)), "name": name,
                     "display_name": NODE_DISPLAY_NAME_MAPPINGS.get(name, name), "category": getattr(cls, "CATEGORY", "")}
    return out


def all_defs() -> dict:
    stock = json.loads(STOCK.read_text(encoding="utf-8"))
    stock.pop("_note", None)
    return {**stock, **pack_defs()}


def spec_type(spec) -> str:
    t = spec[0] if isinstance(spec, (list, tuple)) else spec
    return "COMBO" if isinstance(t, list) else str(t)


def is_widget(spec) -> bool:
    opts = spec[1] if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict) else {}
    return spec_type(spec) in WIDGET_TYPES and not opts.get("forceInput")


def has_control(name: str, spec) -> bool:
    """The frontend's rule: an INT widget gets a control_after_generate widget when its spec asks, else when it is
    called seed or noise_seed."""
    opts = spec[1] if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict) else {}
    if spec_type(spec) != "INT":
        return False
    flag = opts.get("control_after_generate")
    return bool(flag) if flag is not None else name in ("seed", "noise_seed")


def inputs_of(d: dict) -> list[tuple[str, object, bool]]:
    """(name, spec, required) in the node's input order."""
    out = []
    order = d.get("input_order") or {k: list(v) for k, v in d["input"].items() if k in ("required", "optional")}
    for group in ("required", "optional"):
        for name in order.get(group) or []:
            spec = (d["input"].get(group) or {}).get(name)
            if spec is not None:
                out.append((name, spec, group == "required"))
    return out


class Node:
    def __init__(self, graph: "Graph", nid: int, kind: str, pos, size, title: str | None, values: dict):
        self.graph, self.id, self.type, self.pos, self.size, self.title = graph, nid, kind, list(pos), list(size), title
        self.values = dict(values)
        self.d = graph.defs.get(kind)
        self.links_in: dict[str, int] = {}
        self.links_out: dict[int, list[int]] = {}

    def widget_values(self) -> list:
        if self.type in FRONTEND_ONLY:
            return [self.values.get("text", "")]
        vals = []
        for name, spec, _req in inputs_of(self.d):
            if not is_widget(spec):
                continue
            if name in self.values:
                v = self.values[name]
            else:
                opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                v = opts.get("default")
                if v is None and isinstance(spec[0], list):
                    v = spec[0][0] if spec[0] else ""
                if v is None:
                    v = "" if spec_type(spec) == "STRING" else 0
            vals.append(v)
            if has_control(name, spec):
                vals.append(self.values.get(f"{name}__control", "fixed"))
        return vals

    def slots(self) -> list[dict]:
        """The input slots the UI file lists: every socket input, then every widget input that is linked."""
        if self.type in FRONTEND_ONLY:
            return []
        out = []
        for name, spec, req in inputs_of(self.d):
            if is_widget(spec):
                continue
            slot = {"name": name, "type": spec_type(spec), "link": self.links_in.get(name)}
            if not req:
                slot["shape"] = 7
            out.append(slot)
        for name, spec, _req in inputs_of(self.d):
            if is_widget(spec) and name in self.links_in:
                out.append({"name": name, "type": spec_type(spec), "widget": {"name": name}, "link": self.links_in[name]})
        return out


class Graph:
    def __init__(self, defs: dict):
        self.defs = defs
        self.nodes: list[Node] = []
        self.links: list[list] = []
        self.groups: list[dict] = []

    def add(self, kind: str, pos, size=(320, 120), title: str | None = None, **values) -> Node:
        if kind not in self.defs and kind not in FRONTEND_ONLY:
            raise KeyError(f"{kind} is not a node ComfyUI or the pack defines")
        node = Node(self, len(self.nodes) + 1, kind, pos, size, title, values)
        self.nodes.append(node)
        return node

    def link(self, src: Node, out: str, dst: Node, inp: str) -> None:
        names = list(src.d.get("output_name") or src.d["output"])
        slot = names.index(out)
        typ = src.d["output"][slot]
        lid = len(self.links) + 1
        dst.links_in[inp] = lid
        src.links_out.setdefault(slot, []).append(lid)
        self.links.append([lid, src.id, slot, dst.id, None, typ, inp])

    def group(self, title: str, bounding, color: str) -> None:
        self.groups.append({"id": len(self.groups) + 1, "title": title, "bounding": list(bounding), "color": color,
                            "font_size": 22, "flags": {}})

    def order(self) -> dict[int, int]:
        deps = {n.id: set() for n in self.nodes}
        for lid, a, _s, b, _t, _typ, _inp in self.links:
            deps[b].add(a)
        done: list[int] = []
        while len(done) < len(self.nodes):
            ready = sorted(nid for nid, d in deps.items() if nid not in done and d <= set(done))
            if not ready:
                raise ValueError("the demo graph has a cycle")
            done += ready
        return {nid: k for k, nid in enumerate(done)}

    def ui(self) -> dict:
        order = self.order()
        nodes, links = [], []
        slot_of: dict[int, int] = {}
        for n in self.nodes:
            slots = n.slots()
            for k, s in enumerate(slots):
                if s.get("link") is not None:
                    slot_of[s["link"]] = k
        for n in self.nodes:
            row = {"id": n.id, "type": n.type, "pos": n.pos, "size": n.size, "flags": {}, "order": order[n.id], "mode": 0,
                   "inputs": n.slots(), "outputs": [], "properties": {"Node name for S&R": n.type},
                   "widgets_values": n.widget_values()}
            if n.type in FRONTEND_ONLY:
                row["properties"] = {}
                row["color"], row["bgcolor"] = "#432", "#653"
            else:
                names = list(n.d.get("output_name") or n.d["output"])
                for k, (typ, name) in enumerate(zip(n.d["output"], names)):
                    row["outputs"].append({"name": name, "type": typ, "links": n.links_out.get(k) or None, "slot_index": k})
            if n.title:
                row["title"] = n.title
            nodes.append(row)
        for lid, a, s, b, _t, typ, _inp in self.links:
            links.append([lid, a, s, b, slot_of[lid], typ])
        return {"id": "8f5c2d9e-6a1b-4c3d-9e7f-0a1b2c3d4e5f", "revision": 0, "last_node_id": len(self.nodes),
                "last_link_id": len(self.links), "nodes": nodes, "links": links, "groups": self.groups, "config": {},
                "extra": {"ds": {"scale": 0.5, "offset": [60, 40]},
                          "xenoform": {"made_by": "comfy_pack/tools/build_demo_workflow.py",
                                       "about": "The Xenoform node pack's demo: two LTX 0.9.5 morphs on the demo song, cut on the beat."}},
                "version": 0.4}

    def api(self) -> dict:
        out = {}
        for n in self.nodes:
            if n.type in FRONTEND_ONLY:
                continue
            inputs = {}
            for name, spec, _req in inputs_of(n.d):
                if name in n.links_in:
                    lid = n.links_in[name]
                    _l, a, s, _b, _t, _typ, _inp = self.links[lid - 1]
                    inputs[name] = [str(a), s]
                elif is_widget(spec):
                    vals = dict(zip([nm for nm, sp, _r in inputs_of(n.d) if is_widget(sp)], self._plain_values(n)))
                    inputs[name] = vals[name]
            out[str(n.id)] = {"class_type": n.type, "inputs": inputs, "_meta": {"title": n.title or n.d.get("display_name") or n.type}}
        return out

    @staticmethod
    def _plain_values(n: Node) -> list:
        vals, raw = [], n.widget_values()
        k = 0
        for name, spec, _req in inputs_of(n.d):
            if not is_widget(spec):
                continue
            vals.append(raw[k])
            k += 2 if has_control(name, spec) else 1
        return vals


NOTE = ("Xenoform demo. Queue renders two LTX 0.9.5 morphs (about a minute on a 12 GB card, by the desk's estimate) and cuts them to the demo "
        "song on its beats: Liquid chrome, a Bloom up to the drop and a Shatter from it.\n\n"
        "Open the Morph Timeline (the button on its node) to see the song strip: sections, beats, the drop, the shots on "
        "the beat, the intensity lane and the objects. Edit there, Save, and Queue again; the edits are saved in this workflow.\n\n"
        "More morphs: raise forms on the Storyboard, copy a Morph Pair group with the next index, and connect its decode "
        "to the next morph input of Assemble. Set Assemble's fill to stills to hear the whole song with what is rendered.")


def build() -> Graph:
    g = Graph(all_defs())
    song = g.add("XenoformSongAnalysis", (40, 60), (330, 190), song="demo.wav", fps=12, engine="auto", features_json="")
    board = g.add("XenoformStoryboard", (40, 300), (330, 470), vibe="chrome-mercury", idea="", energy="dense", forms=2, speed=0.5,
                  chaos=0.3, intensity=0.5, morph_style="auto", morph_timing="smooth", pace="viscous", aspect="16:9", seed=2727,
                  images_folder="")
    timeline = g.add("XenoformMorphTimeline", (40, 820), (330, 150), timeline="")
    g.add("Note", (40, 1020), (330, 330), title="Read me", text=NOTE)
    g.link(song, "song", board, "song")
    g.link(board, "storyboard", timeline, "storyboard")
    ckpt = g.add("CheckpointLoaderSimple", (430, 1560), (330, 100), title="LTX 0.9.5", ckpt_name="ltx-video-2b-v0.9.5.safetensors")
    clip = g.add("CLIPLoader", (430, 1700), (330, 110), title="Local text encoder",
                 clip_name="t5xxl_fp8_e4m3fn_scaled.safetensors", type="ltxv", device="cpu")
    sampler = g.add("KSamplerSelect", (430, 1850), (330, 60), sampler_name="euler")
    assemble = g.add("XenoformAssemble", (2880, 600), (340, 300), fill="stop", punch=True, filename_prefix="xenoform/demo")
    g.link(timeline, "storyboard", assemble, "storyboard")
    for m in range(2):
        y = 40 + m * 760
        x = 430
        g.group(f"Morph {m}: the stock LTX 0.9.5 graph (workflows/xenoform_morph.json)", (x - 20, y - 40, 2400, 720),
                "#3f789e" if m == 0 else "#8a6f3f")
        pair = g.add("XenoformMorphPair", (x, y), (330, 430), title=f"Xenoform Morph Pair {m}", index=m)
        g.link(timeline, "storyboard", pair, "storyboard")
        pos = g.add("CLIPTextEncode", (x + 380, y), (360, 160), title="Positive (the pair's prompt)", text="")
        neg = g.add("CLIPTextEncode", (x + 380, y + 200), (360, 160), title="Negative", text="")
        cond = g.add("LTXVConditioning", (x + 380, y + 400), (360, 80), title="Frame rate", frame_rate=24.0)
        pre_a = g.add("LTXVPreprocess", (x + 780, y), (300, 80), title="Guide A", img_compression=18)
        pre_b = g.add("LTXVPreprocess", (x + 780, y + 120), (300, 80), title="Guide B", img_compression=18)
        latent = g.add("EmptyLTXVLatentVideo", (x + 780, y + 240), (300, 130), title="Latent", width=512, height=288, length=49, batch_size=1)
        guide_a = g.add("LTXVAddGuide", (x + 1120, y), (320, 160), title="Guide A at frame 0", frame_idx=0, strength=1.0)
        guide_b = g.add("LTXVAddGuide", (x + 1120, y + 200), (320, 160), title="Guide B at the last frame", frame_idx=-1, strength=1.0)
        sched = g.add("LTXVScheduler", (x + 1480, y), (300, 160), steps=20, max_shift=2.05, base_shift=0.95, stretch=True, terminal=0.1)
        noise = g.add("RandomNoise", (x + 1480, y + 200), (300, 80), title="Seed", noise_seed=2727)
        msamp = g.add("ModelSamplingLTXV", (x + 1480, y + 320), (300, 100), max_shift=2.05, base_shift=0.95)
        guider = g.add("CFGGuider", (x + 1480, y + 460), (300, 100), cfg=3.0)
        sample = g.add("SamplerCustomAdvanced", (x + 1820, y), (280, 110), title="Sample")
        crop = g.add("LTXVCropGuides", (x + 1820, y + 150), (280, 80))
        decode = g.add("VAEDecodeTiled", (x + 1820, y + 270), (280, 150), tile_size=512, overlap=64, temporal_size=32, temporal_overlap=8)
        g.link(pair, "prompt", pos, "text")
        g.link(pair, "negative", neg, "text")
        g.link(clip, "CLIP", pos, "clip")
        g.link(clip, "CLIP", neg, "clip")
        g.link(pos, "CONDITIONING", cond, "positive")
        g.link(neg, "CONDITIONING", cond, "negative")
        g.link(pair, "frame_rate", cond, "frame_rate")
        g.link(pair, "image_a", pre_a, "image")
        g.link(pair, "image_b", pre_b, "image")
        g.link(pair, "compression_a", pre_a, "img_compression")
        g.link(pair, "compression_b", pre_b, "img_compression")
        g.link(pair, "width", latent, "width")
        g.link(pair, "height", latent, "height")
        g.link(pair, "length", latent, "length")
        g.link(cond, "positive", guide_a, "positive")
        g.link(cond, "negative", guide_a, "negative")
        g.link(ckpt, "VAE", guide_a, "vae")
        g.link(latent, "LATENT", guide_a, "latent")
        g.link(pre_a, "output_image", guide_a, "image")
        g.link(guide_a, "positive", guide_b, "positive")
        g.link(guide_a, "negative", guide_b, "negative")
        g.link(ckpt, "VAE", guide_b, "vae")
        g.link(guide_a, "latent", guide_b, "latent")
        g.link(pre_b, "output_image", guide_b, "image")
        g.link(pair, "guide_strength_b", guide_b, "strength")
        g.link(pair, "steps", sched, "steps")
        g.link(guide_b, "latent", sched, "latent")
        g.link(pair, "seed", noise, "noise_seed")
        g.link(ckpt, "MODEL", msamp, "model")
        g.link(guide_b, "latent", msamp, "latent")
        g.link(msamp, "MODEL", guider, "model")
        g.link(guide_b, "positive", guider, "positive")
        g.link(guide_b, "negative", guider, "negative")
        g.link(pair, "cfg", guider, "cfg")
        g.link(noise, "NOISE", sample, "noise")
        g.link(guider, "GUIDER", sample, "guider")
        g.link(sampler, "SAMPLER", sample, "sampler")
        g.link(sched, "SIGMAS", sample, "sigmas")
        g.link(guide_b, "latent", sample, "latent_image")
        g.link(guide_b, "positive", crop, "positive")
        g.link(guide_b, "negative", crop, "negative")
        g.link(sample, "output", crop, "latent")
        g.link(crop, "latent", decode, "samples")
        g.link(ckpt, "VAE", decode, "vae")
        g.link(decode, "IMAGE", assemble, f"morph_{m + 1}")
    return g


def render() -> tuple[str, str]:
    g = build()
    return (json.dumps(g.ui(), indent=1, ensure_ascii=False) + "\n", json.dumps(g.api(), indent=1, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="say which file differs and exit 1, write nothing")
    args = ap.parse_args()
    ui, api = render()
    if args.check:
        stale = [p for p, text in ((OUT_UI, ui), (OUT_API, api)) if not p.is_file() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"stale: {p.relative_to(REPO)}")
        return 1 if stale else 0
    OUT_UI.parent.mkdir(parents=True, exist_ok=True)
    OUT_UI.write_text(ui, encoding="utf-8")
    OUT_API.write_text(api, encoding="utf-8")
    print(f"wrote {OUT_UI.relative_to(REPO)} and {OUT_API.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
