"""One storyboard, one ComfyUI workflow.

The file is the UI format ComfyUI loads (nodes, links, version 0.4). Every
class is a core LTX node from the shipped graphs. No partner node, no key.
"""

from __future__ import annotations

from typing import Any

from xenoform.hardware import FAST_CHECKPOINT

_NEGATIVE = "text, watermark, logo, human, face, flicker, low detail"


def latent_length(seconds: float, fps: float) -> int:
    frames = max(9, int(round(max(0.2, float(seconds)) * max(1.0, float(fps)))))
    quanta = max(1, int(round((frames - 1) / 8.0)))
    return quanta * 8 + 1


class _Graph:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.links: list[list] = []
        self._node = 1
        self._link = 1

    def add(
        self,
        class_type: str,
        title: str,
        widgets: list,
        *,
        inputs: list[tuple[str, str]],
        outputs: list[tuple[str, str]],
        pos: tuple[int, int],
    ) -> int:
        node_id = self._node
        self._node += 1
        self.nodes.append(
            {
                "id": node_id,
                "type": class_type,
                "title": title,
                "pos": [int(pos[0]), int(pos[1])],
                "size": [340, 120],
                "flags": {},
                "order": node_id,
                "mode": 0,
                "inputs": [{"name": name, "type": kind, "link": None} for name, kind in inputs],
                "outputs": [{"name": name, "type": kind, "links": []} for name, kind in outputs],
                "properties": {"Node name for S&R": class_type},
                "widgets_values": list(widgets),
            }
        )
        return node_id

    def connect(self, src: int, src_slot: int, dst: int, dst_slot: int, kind: str) -> None:
        link_id = self._link
        self._link += 1
        self.links.append([link_id, src, src_slot, dst, dst_slot, kind])
        source = next(node for node in self.nodes if node["id"] == src)
        target = next(node for node in self.nodes if node["id"] == dst)
        source["outputs"][src_slot]["links"].append(link_id)
        target["inputs"][dst_slot]["link"] = link_id

    def document(self) -> dict[str, Any]:
        return {
            "last_node_id": self._node - 1,
            "last_link_id": self._link - 1,
            "nodes": self.nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {"xenoform": "storyboard", "open_weights": True},
            "version": 0.4,
        }


def _prompt(scene: dict, index: int) -> str:
    text = str(scene.get("prompt") or scene.get("action") or scene.get("guide") or "").strip()
    if text:
        return text
    form = str(scene.get("form") or "object")
    return f"Shot {index + 1}. One {form}, continuous, no text."


def storyboard_workflow(body: dict | None) -> dict[str, Any]:
    """The whole board as one loadable ComfyUI workflow."""
    body = body or {}
    scenes = [scene for scene in (body.get("scenes") or []) if isinstance(scene, dict)]
    if not scenes:
        scenes = [{"prompt": str(body.get("brief") or "One object, dark studio"), "start": 0, "end": 2}]
    fps = float(body.get("fps") or 12)
    width = int(body.get("width") or 512)
    height = int(body.get("height") or 320)
    width -= width % 32
    height -= height % 32
    width = max(64, width)
    height = max(64, height)
    seed = int(body.get("seed") or 2727)
    checkpoint = str(body.get("checkpoint") or FAST_CHECKPOINT)
    clip_name = str(body.get("clip_name") or "t5xxl_fp8_e4m3fn_scaled.safetensors")
    negative = str(body.get("negative") or _NEGATIVE)
    graph = _Graph()
    checkpoint_id = graph.add(
        "CheckpointLoaderSimple",
        "LTX checkpoint, local weights",
        [checkpoint],
        inputs=[],
        outputs=[("MODEL", "MODEL"), ("CLIP", "CLIP"), ("VAE", "VAE")],
        pos=(40, 40),
    )
    clip_id = graph.add(
        "CLIPLoader",
        "Local text encoder",
        [clip_name, "ltxv"],
        inputs=[],
        outputs=[("CLIP", "CLIP")],
        pos=(40, 220),
    )
    negative_id = graph.add(
        "CLIPTextEncode",
        "Negative",
        [negative],
        inputs=[("clip", "CLIP")],
        outputs=[("CONDITIONING", "CONDITIONING")],
        pos=(40, 400),
    )
    graph.connect(clip_id, 0, negative_id, 0, "CLIP")
    for index, scene in enumerate(scenes):
        column = 460 + index * 380
        start = float(scene.get("start") or 0)
        end = float(scene.get("end") or start + 2)
        length = latent_length(max(0.2, end - start), fps)
        label = str(scene.get("beat") or scene.get("section") or f"shot {index + 1}")
        positive = graph.add(
            "CLIPTextEncode",
            f"Shot {index + 1} · {label}",
            [_prompt(scene, index)],
            inputs=[("clip", "CLIP")],
            outputs=[("CONDITIONING", "CONDITIONING")],
            pos=(column, 40),
        )
        graph.connect(clip_id, 0, positive, 0, "CLIP")
        conditioning = graph.add(
            "LTXVConditioning",
            f"Frame rate · shot {index + 1}",
            [fps],
            inputs=[("positive", "CONDITIONING"), ("negative", "CONDITIONING")],
            outputs=[("positive", "CONDITIONING"), ("negative", "CONDITIONING")],
            pos=(column, 200),
        )
        graph.connect(positive, 0, conditioning, 0, "CONDITIONING")
        graph.connect(negative_id, 0, conditioning, 1, "CONDITIONING")
        latent = graph.add(
            "EmptyLTXVLatentVideo",
            f"Latent · shot {index + 1}",
            [width, height, length, 1],
            inputs=[],
            outputs=[("LATENT", "LATENT")],
            pos=(column, 360),
        )
        scheduler = graph.add(
            "LTXVScheduler",
            f"Steps · shot {index + 1}",
            [8, 2.05, 0.95, True, 0.1],
            inputs=[("latent", "LATENT")],
            outputs=[("SIGMAS", "SIGMAS")],
            pos=(column, 520),
        )
        graph.connect(latent, 0, scheduler, 0, "LATENT")
        sampler = graph.add(
            "KSamplerSelect",
            "Sampler",
            ["euler"],
            inputs=[],
            outputs=[("SAMPLER", "SAMPLER")],
            pos=(column, 680),
        )
        noise = graph.add(
            "RandomNoise",
            f"Seed {seed + index}",
            [seed + index],
            inputs=[],
            outputs=[("NOISE", "NOISE")],
            pos=(column, 820),
        )
        sampling = graph.add(
            "ModelSamplingLTXV",
            "Shift",
            [2.05, 0.95],
            inputs=[("model", "MODEL"), ("latent", "LATENT")],
            outputs=[("MODEL", "MODEL")],
            pos=(column, 960),
        )
        graph.connect(checkpoint_id, 0, sampling, 0, "MODEL")
        graph.connect(latent, 0, sampling, 1, "LATENT")
        guider = graph.add(
            "CFGGuider",
            "CFG",
            [3.0],
            inputs=[("model", "MODEL"), ("positive", "CONDITIONING"), ("negative", "CONDITIONING")],
            outputs=[("GUIDER", "GUIDER")],
            pos=(column, 1120),
        )
        graph.connect(sampling, 0, guider, 0, "MODEL")
        graph.connect(conditioning, 0, guider, 1, "CONDITIONING")
        graph.connect(conditioning, 1, guider, 2, "CONDITIONING")
        sample = graph.add(
            "SamplerCustomAdvanced",
            f"Sample · shot {index + 1}",
            [],
            inputs=[
                ("noise", "NOISE"),
                ("guider", "GUIDER"),
                ("sampler", "SAMPLER"),
                ("sigmas", "SIGMAS"),
                ("latent_image", "LATENT"),
            ],
            outputs=[("LATENT", "LATENT")],
            pos=(column, 1280),
        )
        graph.connect(noise, 0, sample, 0, "NOISE")
        graph.connect(guider, 0, sample, 1, "GUIDER")
        graph.connect(sampler, 0, sample, 2, "SAMPLER")
        graph.connect(scheduler, 0, sample, 3, "SIGMAS")
        graph.connect(latent, 0, sample, 4, "LATENT")
        decode = graph.add(
            "VAEDecode",
            "Decode",
            [],
            inputs=[("samples", "LATENT"), ("vae", "VAE")],
            outputs=[("IMAGE", "IMAGE")],
            pos=(column, 1460),
        )
        graph.connect(sample, 0, decode, 0, "LATENT")
        graph.connect(checkpoint_id, 2, decode, 1, "VAE")
        video = graph.add(
            "CreateVideo",
            "Picture",
            [fps],
            inputs=[("images", "IMAGE")],
            outputs=[("VIDEO", "VIDEO")],
            pos=(column, 1620),
        )
        graph.connect(decode, 0, video, 0, "IMAGE")
        save = graph.add(
            "SaveVideo",
            f"Save shot {index + 1}",
            [f"xenoform/shot-{index + 1:02d}", "auto", "auto"],
            inputs=[("video", "VIDEO")],
            outputs=[],
            pos=(column, 1760),
        )
        graph.connect(video, 0, save, 0, "VIDEO")
    document = graph.document()
    document["xenoform"] = {"shots": len(scenes), "seed": seed, "checkpoint": checkpoint}
    return document
