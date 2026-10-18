"""ComfyUI custom-node entry.

ComfyUI Manager clones this repository into custom_nodes and imports this file.
The Python package lives under src/. This module puts it on the path, registers
the nodes, and serves the desk at /xenoform on ComfyUI's own port.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

WEB_DIRECTORY = "./web"

try:
    from xenoform.comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
    from xenoform.comfy_server import mount_prompt_server

    mount_prompt_server()
except Exception as exc:  # ComfyUI should still boot if a dependency is missing.
    NODE_CLASS_MAPPINGS = {}
    NODE_DISPLAY_NAME_MAPPINGS = {}
    print(f"Xenoform did not finish loading. Open the Xenoform tab after the install script, or read the message: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
