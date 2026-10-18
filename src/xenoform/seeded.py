"""Every varying number is a function of the seed and the frame.

The same seed and the same frame index always return the same unit value.
Renders stay reproducible. Nothing here reads the clock.
"""

from __future__ import annotations


def unit(seed: int, frame: int, salt: int = 0) -> float:
    """A value in ``[0, 1)``. ``frame`` is the frame index, not a clock time."""
    n = (int(seed) * 374761393 + int(frame) * 668265263 + int(salt) * 2246822519) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    n = (n ^ (n >> 16)) & 0xFFFFFFFF
    return (n & 0xFFFFFF) / float(0x1000000)
