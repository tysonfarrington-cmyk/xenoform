"""Xenoform's nodes for ComfyUI. The pack's layout lands first; the nodes come next (Song Analysis, Storyboard,
Morph Timeline, Morph Pair, Assemble), each a thin wrapper over a pure function so the tests run them without ComfyUI."""

from __future__ import annotations

NODE_CLASS_MAPPINGS: dict = {}
NODE_DISPLAY_NAME_MAPPINGS: dict = {}
