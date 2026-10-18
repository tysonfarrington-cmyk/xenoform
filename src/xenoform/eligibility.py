"""Contest eligibility for the default path.

Open weights only: local models, no partner nodes, no closed APIs.
``comfy.addons`` (and the desk Add-ons switch) is off unless set.
The demo, the judges page, and setup do not read it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

ADDONS_DEFAULT = False

DEFAULT_WORKFLOWS = (
    "workflows/ltx_v2v_api.json",
    "workflows/ltx_v2v_guide_api.json",
    "workflows/xenoform_draft.json",
    "workflows/xenoform_final.json",
    "workflows/xenoform_morph.json",
    "workflows/ltx25_a2v_api.json",
    "workflows/ltx25_multishot_api.json",
    "workflows/ltx25_layout_api.json",
)

# Sampler graphs. These must encode prompts with a local loader.
LTX_WORKFLOWS = (
    "workflows/ltx_v2v_api.json",
    "workflows/ltx_v2v_guide_api.json",
    "workflows/xenoform_morph.json",
    "workflows/ltx25_a2v_api.json",
    "workflows/ltx25_multishot_api.json",
    "workflows/ltx25_layout_api.json",
)

# Substrings of a node class_type or UI node type. Filenames are not scanned,
# so the shipped ``*_api.json`` graphs stay clean.
CLOSED_MARKERS = (
    "partner",
    "higgsfield",
    "h3",
    "fluxpro",
    "fluxapi",
    "kontext",
    "blackforest",
    "bfl",
    "openai",
    "dalle",
    "dall-e",
    "gemini",
    "ideogram",
    "kling",
    "runway",
    "luma",
    "recraft",
    "minimax",
    "pixverse",
    "seedance",
    "wavespeed",
    "topaz",
    "meshy",
    "tripo",
    "rodin",
    "anthropic",
    "claude",
    "grok",
    "api",
)

STILLS = "Z-Image Turbo"
STILLS_OPTIONAL = ("FLUX.2 Klein", "FLUX.3 Klein")
VIDEO_CORE = "LTX-2.3"
VIDEO_MORPH = "LTX 0.9.5"
VIDEO_UPGRADE = "LTX-2.5"

# Checked against https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x on 18 Oct 2026.
LTX25_LICENCE = {
    "model": "LTX-2.5",
    "licence": "LTX-2.x Community License Agreement",
    "date": "2026-08-11",
    "url": "https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x",
    "open_weights": True,
    "partner_nodes": False,
    "revenue": "Free commercial use under $10,000,000 annual revenue. Above that, a paid licence.",
    "weights": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
    "lora": "ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors",
}


def ltx25_licence() -> dict:
    """The checked LTX-2.5 terms. Open weights, local graphs, no partner node."""
    return dict(LTX25_LICENCE)


def ltx25_allowed() -> bool:
    info = ltx25_licence()
    return bool(info.get("open_weights")) and not info.get("partner_nodes")

# Local prompt encoders. GemmaAPITextEncode calls api.ltx.video and is not one of these.
LOCAL_TEXT_ENCODERS = frozenset(
    {
        "cliploader",
        "dualcliploader",
        "triplecliploader",
        "cliptextencode",
        "ltxavtextencoderloader",
    }
)

# ComfyUI partner nodes for LTX-2.5 (comfy_api_nodes/nodes_ltxv.py).
LTX_PARTNER_NODES = frozenset(
    {
        "ltxapi25texttovideo",
        "ltxapi25imagetovideo",
        "ltxapi25audiotovideo",
    }
)

_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def addons_enabled(cfg: dict | None = None) -> bool:
    """True only when the config or ``XENO_ADDONS`` asks for closed APIs.

    ``XENO_ADDONS=0`` (also false, no, off) forces Add-ons off, including when a
    local config would otherwise turn them on.
    """
    flag = os.environ.get("XENO_ADDONS", "").strip().lower()
    if flag in _ON:
        return True
    if flag in _OFF:
        return False
    comfy = (cfg or {}).get("comfy") or {}
    return bool(comfy.get("addons", ADDONS_DEFAULT))


def partner_key(cfg: dict | None, environ: dict | None = None) -> str:
    """Partner-node key. Empty while Add-ons is off."""
    if not addons_enabled(cfg):
        return ""
    env = os.environ if environ is None else environ
    name = str(((cfg or {}).get("comfy") or {}).get("partner_api_key_env") or "").strip()
    if not name:
        return ""
    return str(env.get(name) or "")


def host_is_local(url: str) -> bool:
    """Loopback and private hosts are local models. A public host is a cloud API."""
    text = (url or "").strip()
    if not text:
        return True
    if "://" not in text:
        text = "http://" + text
    host = (urlparse(text).hostname or "").lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"} or host.endswith(".localhost"):
        return True
    try:
        import ipaddress

        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def call_allowed(url: str, *, allow_cloud: bool = False) -> bool:
    """Local endpoints stay available. A cloud LLM needs Add-ons."""
    if allow_cloud or addons_enabled(None):
        return True
    return host_is_local(url)


def closed_marker(node_type: str) -> str | None:
    folded = str(node_type or "").casefold()
    if not folded:
        return None
    for marker in CLOSED_MARKERS:
        if marker in folded:
            return marker
    return None


def node_types(data: object) -> list[str]:
    """API-format ``class_type`` and UI-format node ``type``. Not filenames or slot types."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            kind = node.get("class_type")
            if isinstance(kind, str):
                found.append(kind)
            nodes = node.get("nodes")
            if isinstance(nodes, list):
                for item in nodes:
                    if isinstance(item, dict) and isinstance(item.get("type"), str):
                        found.append(item["type"])
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _node_title(node: dict) -> str:
    meta = node.get("_meta") if isinstance(node.get("_meta"), dict) else {}
    return str(node.get("title") or meta.get("title") or "")


def _is_api_key_name(name: object) -> bool:
    folded = str(name or "").casefold().replace(" ", "").replace("_", "")
    return folded in {"apikey", "ltxapikey"} or "ltxapikey" in folded


def _filled_secret(value: object) -> bool:
    """A linked input is not a secret. A non-empty string is."""
    if isinstance(value, str):
        return bool(value.strip())
    return False


def is_api_text_encoder(node_type: str) -> bool:
    folded = str(node_type or "").casefold()
    return "gemmaapi" in folded or "apitextencode" in folded


def is_ltx_partner(node_type: str) -> bool:
    folded = str(node_type or "").casefold().replace("_", "").replace(" ", "")
    if folded in LTX_PARTNER_NODES or folded.startswith("ltxapi"):
        return True
    return "ltx" in folded and "partner" in folded


def iter_nodes(data: object) -> list[dict]:
    found: list[dict] = []

    def walk(node: object, *, in_list: bool) -> None:
        if isinstance(node, dict):
            if in_list or isinstance(node.get("class_type"), str):
                found.append(node)
            nodes = node.get("nodes")
            if isinstance(nodes, list):
                for item in nodes:
                    walk(item, in_list=True)
            for key, value in node.items():
                if key == "nodes":
                    continue
                if isinstance(value, (dict, list)):
                    walk(value, in_list=False)
        elif isinstance(node, list):
            for item in node:
                walk(item, in_list=False)

    walk(data, in_list=False)
    return found


def _key_literals(node: dict) -> list[str]:
    """String values sitting in an LTX API key field. Links are skipped."""
    values: list[str] = []
    title = _node_title(node)
    if "ltx api key" in title.casefold():
        widgets = node.get("widgets_values")
        if isinstance(widgets, list) and widgets and isinstance(widgets[0], str):
            values.append(widgets[0])
        elif isinstance(widgets, str):
            values.append(widgets)
    inputs = node.get("inputs")
    if isinstance(inputs, dict):
        for key, value in inputs.items():
            if _is_api_key_name(key) and isinstance(value, str):
                values.append(value)
    elif isinstance(inputs, list):
        for index, slot in enumerate(inputs):
            if not isinstance(slot, dict) or not _is_api_key_name(slot.get("name") or slot.get("label")):
                continue
            if slot.get("link") is not None:
                continue
            widgets = node.get("widgets_values")
            if isinstance(widgets, list) and index < len(widgets) and isinstance(widgets[index], str):
                values.append(widgets[index])
    kind = str(node.get("class_type") or node.get("type") or "")
    if is_api_text_encoder(kind):
        widgets = node.get("widgets_values")
        if isinstance(widgets, list) and widgets and isinstance(widgets[0], str):
            values.append(widgets[0])
    return values


def audit_graph(data: object, label: str = "graph") -> list[str]:
    hits = []
    seen: set[str] = set()

    def add(message: str) -> None:
        if message not in seen:
            seen.add(message)
            hits.append(message)

    for name in node_types(data):
        marker = closed_marker(name)
        if marker:
            add(f"{label}: {name} ({marker})")
        if is_ltx_partner(name):
            add(f"{label}: {name} (ltx partner node)")
        if is_api_text_encoder(name):
            add(f"{label}: {name} (api text encoder)")
    for node in iter_nodes(data):
        if any(_filled_secret(value) for value in _key_literals(node)):
            add(f"{label}: LTX API key field is set")
    return hits


def local_text_encoder(data: object) -> bool:
    """True when prompt encoding is a local loader, not the LTX API encoder."""
    names = {name.casefold() for name in node_types(data)}
    if any(is_api_text_encoder(name) for name in names):
        return False
    return any(name in LOCAL_TEXT_ENCODERS for name in names)


def audit_default_workflows(root: Path | None = None) -> list[str]:
    """Violations in the shipped graphs. Empty means the default path is open weights."""
    root = root or repo_root()
    violations: list[str] = []
    for rel in DEFAULT_WORKFLOWS:
        path = root / rel
        if not path.is_file():
            violations.append(f"{rel}: missing")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            violations.append(f"{rel}: {exc}")
            continue
        violations.extend(audit_graph(data, rel))
        if rel in LTX_WORKFLOWS and not local_text_encoder(data):
            violations.append(f"{rel}: prompt encoding is not a local text encoder")
    return violations
