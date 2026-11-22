"""ComfyUI custom-node entry for the whole repository.

ComfyUI-Manager clones this repository into ``custom_nodes/xenoform`` and imports this file. It registers the node pack
in ``comfy_pack/`` first (Song Analysis, Storyboard, Morph Timeline, Morph Pair, Assemble: nothing beyond what ComfyUI
ships), then, when the desk's own package under ``src/`` imports, its two nodes (Try It, Setup Check) and the desk at
/xenoform on ComfyUI's port. The web folder is the pack's: the Morph Timeline editor, and the desk's tab, which shows
itself only when /xenoform answers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

WEB_DIRECTORY = "./comfy_pack/web"
NODE_CLASS_MAPPINGS: dict = {}
NODE_DISPLAY_NAME_MAPPINGS: dict = {}

if __package__:  # ComfyUI loads this file as a package; pytest imports it as a plain module, with no pack to import
    try:
        from .comfy_pack import NODE_CLASS_MAPPINGS as _PACK_NODES, NODE_DISPLAY_NAME_MAPPINGS as _PACK_NAMES

        NODE_CLASS_MAPPINGS.update(_PACK_NODES)
        NODE_DISPLAY_NAME_MAPPINGS.update(_PACK_NAMES)
    except Exception as exc:  # ComfyUI should still boot if the pack cannot load
        print(f"Xenoform nodes did not load: {exc}")

try:
    import importlib.util

    # the desk's nodes and /xenoform need the desk's own install: without it they would register, then fail at every
    # queue and answer every ComfyUI page load's GET /xenoform with a 500
    if importlib.util.find_spec("fastapi") is None:
        raise ImportError("fastapi is not installed in ComfyUI's Python")
    from xenoform.comfy_nodes import NODE_CLASS_MAPPINGS as _DESK_NODES, NODE_DISPLAY_NAME_MAPPINGS as _DESK_NAMES
    from xenoform.comfy_server import mount_prompt_server

    NODE_CLASS_MAPPINGS.update(_DESK_NODES)
    NODE_DISPLAY_NAME_MAPPINGS.update(_DESK_NAMES)
    mount_prompt_server()
except Exception as exc:  # the desk needs its own install (install.bat); the pack's nodes do not
    print(f"Xenoform desk nodes did not load (the node pack did). Run the desk's installer for them: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
