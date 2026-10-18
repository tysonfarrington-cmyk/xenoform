"""Local LLM for director's notes.

Ollama is the default, on ``http://127.0.0.1:11434``. Set
``XENO_LLM_BACKEND=openai`` and ``XENO_NOTES_LLM_URL`` (or ``XENO_LLM_URL``)
to an OpenAI-compatible ``/v1`` base when another local server should read
the note. Nothing here calls a cloud.

``release_llm`` asks Ollama to unload the model (``keep_alive`` 0) so a 12GB
GPU can run ComfyUI. A missing server is not an error.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_MODEL = "qwen2.5:7b-instruct"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"


def backend() -> str:
    name = os.environ.get("XENO_LLM_BACKEND", "ollama").strip().lower()
    return "openai" if name in {"openai", "openai-compatible", "v1"} else "ollama"


def model_name() -> str:
    return os.environ.get("XENO_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def vlm_model() -> str:
    return os.environ.get("XENO_VLM_MODEL", "").strip()


def ollama_base() -> str:
    return os.environ.get("XENO_OLLAMA_URL", DEFAULT_OLLAMA).rstrip("/")


def openai_base() -> str:
    raw = (
        os.environ.get("XENO_NOTES_LLM_URL")
        or os.environ.get("XENO_LLM_URL")
        or f"{DEFAULT_OLLAMA}/v1"
    ).strip().rstrip("/")
    suffix = "/chat/completions"
    if raw.endswith(suffix):
        raw = raw[: -len(suffix)]
    return raw


def _post(url: str, payload: dict, timeout: float) -> dict | None:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


def reachable(timeout: float = 0.4) -> bool:
    """True when an Ollama server answers ``/api/tags``."""
    try:
        with urllib.request.urlopen(f"{ollama_base()}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def chat(
    system: str,
    user: str,
    schema: dict | None = None,
    *,
    timeout: float = 8.0,
    model: str | None = None,
    allow_cloud: bool = False,
) -> str | None:
    """One completion. ``None`` when the server is down or the body is unusable.

    A cloud host is skipped unless Add-ons is on. Loopback Ollama stays available.
    """
    from xenoform.eligibility import call_allowed

    target = openai_base() if backend() == "openai" else ollama_base()
    if not call_allowed(target, allow_cloud=allow_cloud):
        return None
    chosen = model or model_name()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    if backend() == "openai":
        payload: dict[str, Any] = {
            "model": chosen,
            "messages": messages,
            "temperature": 0.2,
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}
        data = _post(f"{openai_base()}/chat/completions", payload, timeout)
        if not data:
            return None
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            return None

    payload = {
        "model": chosen,
        "messages": messages,
        "stream": False,
        "format": schema if schema is not None else "json",
        "options": {"temperature": 0.2},
    }
    data = _post(f"{ollama_base()}/api/chat", payload, timeout)
    if not data:
        return None
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return str(content) if content else None


def describe_frames(
    prompt: str,
    images_b64: list[str],
    *,
    timeout: float = 12.0,
    model: str | None = None,
    allow_cloud: bool = False,
) -> str | None:
    """Optional vision note. ``XENO_VLM_MODEL`` must be set, or pass ``model``."""
    from xenoform.eligibility import call_allowed

    target = openai_base() if backend() == "openai" else ollama_base()
    if not call_allowed(target, allow_cloud=allow_cloud):
        return None
    chosen = (model or vlm_model()).strip()
    if not chosen or not images_b64:
        return None
    if backend() == "openai":
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images_b64[:4]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                }
            )
        payload = {
            "model": chosen,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
        }
        data = _post(f"{openai_base()}/chat/completions", payload, timeout)
        if not data:
            return None
        try:
            return str(data["choices"][0]["message"]["content"]).strip() or None
        except (KeyError, IndexError, TypeError):
            return None

    payload = {
        "model": chosen,
        "messages": [{"role": "user", "content": prompt, "images": images_b64[:4]}],
        "stream": False,
    }
    data = _post(f"{ollama_base()}/api/chat", payload, timeout)
    if not data:
        return None
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict) or not message.get("content"):
        return None
    return str(message["content"]).strip() or None


def release_llm(model: str | None = None) -> bool:
    """Unload Ollama weights (``keep_alive`` 0). False when Ollama is down.

    Also unloads ``XENO_VLM_MODEL`` when that variable is set. Safe to call
    before every video job.
    """
    names = []
    for candidate in (model or model_name(), vlm_model()):
        if candidate and candidate not in names:
            names.append(candidate)
    ok = False
    for name in names:
        data = _post(
            f"{ollama_base()}/api/generate",
            {"model": name, "prompt": "", "keep_alive": 0, "stream": False},
            timeout=1.5,
        )
        ok = ok or data is not None
    return ok
