"""ComfyUI health. The desk pings /system_stats on the local server."""

from __future__ import annotations

from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_COMFY = "http://127.0.0.1:8188"


def ping(url: str = "", timeout: float = 1.5) -> dict:
    """Ask ComfyUI for /system_stats. Connected, or not connected."""
    base = str(url or DEFAULT_COMFY).strip().rstrip("/") or DEFAULT_COMFY
    target = base + "/system_stats"
    try:
        request = Request(target, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            ok = 200 <= status < 300
    except (URLError, TimeoutError, OSError, ValueError):
        ok = False
    return {
        "ok": ok,
        "url": base,
        "detail": "Connected" if ok else "Not connected",
    }
