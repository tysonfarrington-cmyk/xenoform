"""Drop a ComfyUI workflow into a PNG tEXt chunk, and into an MP4 comment."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def png_with_workflow(workflow: dict, rgb: tuple[int, int, int] = (18, 16, 14)) -> bytes:
    """A small PNG whose tEXt chunks carry the workflow ComfyUI reads on drop."""
    width = height = 48
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    payload = json.dumps(workflow, separators=(",", ":")).encode("utf-8")
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    text = b"workflow\x00" + payload
    prompt = b"prompt\x00" + payload
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"tEXt", text)
        + _chunk(b"tEXt", prompt)
        + _chunk(b"IDAT", zlib.compress(raw, 9))
        + _chunk(b"IEND", b"")
    )


def read_workflow_png(data: bytes) -> dict:
    """Return the workflow JSON stored in a PNG this module wrote."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a png")
    pos = 8
    found = None
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if tag == b"tEXt" and chunk.startswith(b"workflow\x00"):
            found = chunk.split(b"\x00", 1)[1]
        pos += 12 + length
        if tag == b"IEND":
            break
    if found is None:
        raise ValueError("workflow chunk missing")
    return json.loads(found.decode("utf-8"))
