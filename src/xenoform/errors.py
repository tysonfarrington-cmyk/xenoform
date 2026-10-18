"""Plain sentences for the desk. Tracebacks stay in the diagnostics copy."""

from __future__ import annotations

import platform
import traceback
from typing import Any

from xenoform import __version__


class PlainError(RuntimeError):
    """An error whose text is already safe to show."""


def is_oom(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = f"{name} {exc}".lower()
    if isinstance(exc, MemoryError):
        return True
    if "outofmemory" in name or "out of memory" in text or "cuda error: out of memory" in text:
        return True
    return "cuda" in text and "memory" in text


def plain_error(exc: BaseException) -> str:
    """One sentence. No stack, no file paths unless the sentence needs none."""
    if isinstance(exc, PlainError):
        return " ".join(str(exc).split())
    if is_oom(exc):
        return "The GPU ran out of memory. Xenoform dropped to a smaller preset and will try again."
    text = " ".join(str(exc).split())
    low = text.lower()
    if isinstance(exc, FileNotFoundError) or "no such file" in low:
        return "A file this step needs is not on the machine."
    if "ffmpeg" in low:
        return "ffmpeg is not installed, or it could not write the video."
    if any(word in low for word in ("connection refused", "timed out", "failed to establish", "name or service not known")):
        return "ComfyUI did not answer. A dry run still works without it."
    if "demucs" in low:
        return "Stem separation is not installed. The desk uses the librosa band split instead."
    if not text or text.lower().startswith("traceback"):
        return "That step failed. Use Copy diagnostics if you need to send the details."
    if len(text) > 180:
        text = text[:177].rstrip() + "..."
    return text


def audio_read_error(exc: BaseException) -> str:
    """A sentence for a failed decode. File paths stay in the log, not on screen."""
    sentence = plain_error(exc)
    if not sentence or "/" in sentence or "\\" in sentence:
        return "Could not read that audio."
    return sentence


def diagnostics(exc: BaseException | None = None, *, extra: dict[str, Any] | None = None, include_trace: bool = True) -> str:
    """Text for the Copy diagnostics button. The on-screen error stays the short sentence."""
    lines = [
        f"Xenoform {__version__}",
        f"Python {platform.python_version()} on {platform.system()} {platform.release()}",
    ]
    if extra:
        for key, value in extra.items():
            lines.append(f"{key}: {value}")
    if exc is not None:
        lines.append(f"error: {type(exc).__name__}: {' '.join(str(exc).split())}")
        if include_trace:
            lines.append(traceback.format_exc() if exc.__traceback__ else "")
    return "\n".join(line for line in lines if line).strip()
