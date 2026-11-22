"""A dry run of the pack with ComfyUI's own Python, ComfyUI not started.

    <ComfyUI>/.venv/Scripts/python.exe -I comfy_pack/tools/dry_import.py <pack folder> <scratch folder>

``folder_paths`` and ``server`` (ComfyUI's modules) are stubbed, the pack is loaded the way ComfyUI 0.33 loads a custom
node folder, and every node runs on the bundled demo song: the analysis (numpy, since ComfyUI ships no librosa), the
storyboard, the timeline with an edit, both morph pairs (real torch IMAGE tensors), and the Assemble on stand-in
frames through ffmpeg. Writes ``dry_import.json`` in the scratch folder. No GPU is touched: torch makes CPU tensors.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
import types
from pathlib import Path


def stub_comfy(scratch: Path) -> dict:
    routes = []
    fp = types.ModuleType("folder_paths")
    for name, sub in (("get_input_directory", "input"), ("get_output_directory", "output"), ("get_temp_directory", "temp")):
        (scratch / sub).mkdir(parents=True, exist_ok=True)
        setattr(fp, name, (lambda s=str(scratch / sub): s))
    sys.modules["folder_paths"] = fp

    class Routes:
        def get(self, path):
            def wrap(fn):
                routes.append(path)
                return fn
            return wrap

    server = types.ModuleType("server")

    class PromptServer:
        instance = types.SimpleNamespace(routes=Routes())

    server.PromptServer = PromptServer
    sys.modules["server"] = server
    return {"routes": routes}


def load(pack: Path):
    name = str(pack).replace(".", "_x_")
    spec = importlib.util.spec_from_file_location(name, str(pack / "__init__.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    pack, scratch = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False, "python": sys.version.split()[0]}
    try:
        import numpy
        import torch

        report.update({"numpy": numpy.__version__, "torch": torch.__version__})
        try:
            import librosa  # noqa: F401

            report["librosa"] = True
        except Exception:
            report["librosa"] = False
        stub = stub_comfy(scratch)
        mod = load(pack)
        nodes = mod.NODE_CLASS_MAPPINGS
        report["nodes"] = sorted(nodes)
        report["web"] = mod.WEB_DIRECTORY
        report["web_files"] = sorted(p.name for p in (pack / mod.WEB_DIRECTORY).glob("*.js"))
        report["routes"] = sorted(stub["routes"]) == ["/xenoform_nodes/info", "/xenoform_nodes/song", "/xenoform_nodes/still"]
        for cls in nodes.values():
            cls.INPUT_TYPES()
        song = nodes["XenoformSongAnalysis"]().analyse("demo.wav", 12, "auto")["result"][0]
        report.update({"engine": song["engine"], "beats": len(song["features"]["beats"]), "drop": song["drop"],
                       "tempo": song["features"]["tempo"]})
        board = nodes["XenoformStoryboard"]().plan(song, "chrome-mercury", "", "dense", 2, 0.5, 0.3, 0.5, "auto", "smooth",
                                                   "viscous", "16:9", 2727)["result"][0]
        report["shots"] = [[s["start"], s["end"], s["style"], s["length"]] for s in board["shots"]]
        edits = {"format": "xenoform.timeline/1", "song_key": board["song"]["key"], "cuts": None,
                 "shots": {"0.000": {"style": "fold"}}, "intensity": [], "pins": []}
        edited = nodes["XenoformMorphTimeline"]().edit(board, json.dumps(edits))
        report["edited_style"] = edited["result"][0]["shots"][0]["style"]
        report["ui_board_bytes"] = len(edited["ui"]["xenoform_board"][0])
        clips = {}
        for i in range(len(board["shots"])):
            out = nodes["XenoformMorphPair"]().pair(edited["result"][0], i)["result"]
            if i == 0:
                report["image_a"] = list(out[0].shape)
                report["image_dtype"] = str(out[0].dtype)
                report["pair0"] = {"prompt": out[2][:60], "length": out[7], "steps": out[8], "seed": out[9], "cfg": out[10]}
            n = out[7]
            ramp = torch.linspace(0, 1, n).view(n, 1, 1, 1).expand(n, 288, 512, 3).contiguous()
            clips[f"morph_{i + 1}"] = ramp
        cut = nodes["XenoformAssemble"]().cut(edited["result"][0], "stop", True, "xenoform/dry", **clips)
        path = Path(cut["result"][0])
        report["mp4"] = str(path)
        report["mp4_bytes"] = path.stat().st_size if path.is_file() else 0
        report["frames"] = sum(s["frames"] for s in edited["result"][0]["shots"])
        report["cut"] = cut["ui"]["text"][0]
        report["ok"] = report["mp4_bytes"] > 1000 and report["routes"]
    except Exception:
        report["error"] = traceback.format_exc()[-3000:]
    (scratch / "dry_import.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "error"}, indent=1))
    if report.get("error"):
        print(report["error"], file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
