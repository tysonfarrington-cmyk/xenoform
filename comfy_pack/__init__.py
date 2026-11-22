"""Xenoform for ComfyUI: a song becomes a music video of LTX morphs on the beat.

The node pack. ComfyUI imports this file when the pack folder sits in ``custom_nodes/`` (as ``custom_nodes/xenoform-nodes``
or any name: the imports are relative), and the repository's own ``__init__.py`` imports it when the whole repository is
cloned there. It needs nothing ComfyUI does not already ship (numpy, Pillow, torch, PyAV); librosa is used when it is
installed. See README.md.

Nodes: Xenoform Song Analysis, Storyboard, Morph Timeline, Morph Pair, Assemble. The Morph Timeline's editor is the web
extension in ``web/``.
"""

from __future__ import annotations

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"
__version__ = "0.1.0"

try:  # the editor's thumbnails and song: only when ComfyUI's server is up
    from .routes import register as _register

    _register()
except Exception as exc:  # the nodes work without the routes; the editor then shows no thumbnails
    print(f"Xenoform nodes: the timeline's routes were not added ({exc}).")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
