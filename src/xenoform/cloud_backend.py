"""Comfy Cloud backend switch.

``comfy.backend`` picks where a ComfyUI API-format graph runs:

* ``local`` (default) - nothing here is used; the existing local paths are unchanged.
* ``cloud`` - https://cloud.comfy.org, authenticated with ``X-API-Key`` from
  ``COMFY_ORG_API_KEY``. The key is read from the environment at call time and is
  never logged, printed, or put in an exception message.

Cloud flow per job: upload inputs (``/api/upload/image``) -> rename models to the
Cloud library names (configs/cloud_models.json) -> guard -> ``POST /api/prompt``
-> poll ``/api/job/{id}/status`` -> ``/api/jobs/{id}`` -> ``/api/view`` (302 to a
signed URL, fetched WITHOUT the key). At most ``max_parallel`` (3, Creator) jobs run.

Guards (cloud only):
* open-weights renders refuse any partner/API node (contest: Open Weights Only);
* upscaling stays local, so upscale-model nodes are refused on cloud.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

KEY_ENV = "COMFY_ORG_API_KEY"
CLOUD_URL = "https://cloud.comfy.org"
MAX_PARALLEL = 3  # Creator tier concurrency
MAX_RUNTIME_S = 30 * 60  # Standard/Creator per-workflow cap
TERMINAL_FAIL = {"error", "non_retryable_error", "lost", "cancelled"}
MODELS_MAP = Path(__file__).resolve().parents[2] / "configs" / "cloud_models.json"

# Partner (paid, closed-model) nodes seen in our graphs, plus a name rule.
PARTNER_NODES = {
    "LtxApi25ImageToVideo", "GemmaAPITextEncode", "FluxProUltraImageNode",
    "BlackForestLabsFlux3API",
}
_PARTNER_RE = re.compile(r"(Api|API)(Node)?\d*$|API[A-Z]|Api[A-Z0-9]")
UPSCALE_NODES = {"UpscaleModelLoader", "ImageUpscaleWithModel"}
INPUT_FIELDS = {"LoadImage": "image", "LoadVideo": "file", "LoadAudio": "audio"}
MODEL_FIELDS = {"ckpt_name", "text_encoder", "unet_name", "clip_name", "clip_name1", "clip_name2",
                "vae_name", "lora_name", "model_name", "upscale_model_name"}


class CloudRefused(RuntimeError):
    """Raised before anything is sent."""


class CloudJobFailed(RuntimeError):
    pass


# transport(method, url, headers, body) -> (status, headers_dict, bytes); no redirects followed
Transport = Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None,
                     timeout: float = 120.0) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


def backend_name(cfg: dict | None) -> str:
    return str(((cfg or {}).get("comfy") or {}).get("backend") or "local").lower()


def is_partner_node(class_type: str) -> bool:
    return class_type in PARTNER_NODES or bool(_PARTNER_RE.search(class_type))


def load_model_map(path: Path | None = None) -> dict[str, str]:
    p = Path(path or MODELS_MAP)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in (data.get("map") or data).items() if isinstance(v, str)}


def guard(graph: dict, *, open_weights: bool = True) -> list[str]:
    """Problems that block a cloud run. Empty list means OK."""
    problems = []
    for nid, node in graph.items():
        ct = str(node.get("class_type", ""))
        if open_weights and is_partner_node(ct):
            problems.append(f"node {nid} {ct}: partner/API node blocked on cloud open-weights render")
        if ct in UPSCALE_NODES:
            problems.append(f"node {nid} {ct}: upscaling stays local (RealESRGAN on the PC)")
    return problems


def map_models(graph: dict, mapping: dict[str, str]) -> tuple[dict, list[str]]:
    """Copy of graph with model filenames renamed; also returns names used."""
    g = json.loads(json.dumps(graph))
    used = []
    for node in g.values():
        for k, v in (node.get("inputs") or {}).items():
            if k in MODEL_FIELDS and isinstance(v, str):
                node["inputs"][k] = mapping.get(v, v)
                used.append(node["inputs"][k])
    return g, used


def _multipart(field_name: str, path: Path, extra: dict[str, str]) -> tuple[bytes, str]:
    boundary = "xf" + uuid.uuid4().hex
    parts = []
    for k, v in extra.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; '
                  f'filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode())
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


@dataclass
class CloudBackend:
    base_url: str = CLOUD_URL
    transport: Transport = urllib_transport
    max_parallel: int = MAX_PARALLEL
    poll_s: float = 3.0
    timeout_s: float = MAX_RUNTIME_S + 10 * 60  # queue wait + 30-min run cap
    model_map: dict[str, str] = field(default_factory=load_model_map)
    sleep: Callable[[float], None] = time.sleep

    @classmethod
    def from_config(cls, cfg: dict | None, **kw) -> "CloudBackend":
        c = (cfg or {}).get("comfy") or {}
        return cls(base_url=str(c.get("cloud_url") or CLOUD_URL).rstrip("/"),
                   max_parallel=max(1, min(int(c.get("cloud_parallel", MAX_PARALLEL)), MAX_PARALLEL)),
                   **kw)

    # -- plumbing -------------------------------------------------------------
    def _key(self) -> str:
        k = os.environ.get(KEY_ENV, "").strip()
        if not k:
            raise CloudRefused(f"No Comfy API key in {KEY_ENV}. Nothing was sent.")
        return k

    def _call(self, method: str, path: str, *, body: bytes | None = None,
              ctype: str | None = "application/json") -> tuple[int, dict, bytes]:
        headers = {"X-API-Key": self._key()}
        if ctype:
            headers["Content-Type"] = ctype
        status, hdrs, data = self.transport(method, self.base_url + path, headers, body)
        if status in (401, 402, 429):
            meaning = {401: "API key rejected", 402: "out of credits", 429: "subscription inactive"}[status]
            raise CloudJobFailed(f"Comfy Cloud HTTP {status}: {meaning}")
        return status, hdrs, data

    def _json(self, method: str, path: str, payload: Any = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode()
        status, _, data = self._call(method, path, body=body)
        if status >= 400:
            raise CloudJobFailed(f"{method} {path} -> HTTP {status}: {data[:300].decode(errors='replace')}")
        return json.loads(data or b"{}")

    # -- steps ----------------------------------------------------------------
    def object_info(self) -> dict:
        return self._json("GET", "/api/object_info")

    def upload(self, path: Path) -> str:
        body, ctype = _multipart("image", Path(path), {"type": "input", "overwrite": "true"})
        status, _, data = self._call("POST", "/api/upload/image", body=body, ctype=ctype)
        if status >= 400:
            raise CloudJobFailed(f"upload {Path(path).name} -> HTTP {status}")
        return json.loads(data)["name"]

    def upload_inputs(self, graph: dict, inputs: dict[str, Path]) -> dict:
        """inputs: node_id -> local file; sets the node's file field to the cloud name."""
        g = json.loads(json.dumps(graph))
        for nid, p in inputs.items():
            ct = g[nid]["class_type"]
            fld = INPUT_FIELDS.get(ct)
            if not fld:
                raise CloudRefused(f"node {nid} {ct} is not an input loader")
            g[nid]["inputs"][fld] = self.upload(Path(p))
        return g

    def prepare(self, graph: dict, *, open_weights: bool = True) -> dict:
        g, _ = map_models(graph, self.model_map)
        problems = guard(g, open_weights=open_weights)
        if problems:
            raise CloudRefused("Refused, nothing sent: " + "; ".join(problems))
        return g

    def submit(self, graph: dict) -> str:
        res = self._json("POST", "/api/prompt", {"prompt": graph})
        if res.get("error") or res.get("node_errors"):
            raise CloudJobFailed(f"workflow rejected: {res.get('error') or res.get('node_errors')}")
        return res["prompt_id"]

    def wait(self, prompt_id: str) -> dict:
        waited = 0.0
        while waited <= self.timeout_s:
            st = self._json("GET", f"/api/job/{prompt_id}/status").get("status")
            if st == "success":
                # Cloud has no /api/history (404 "Use /api/jobs/{prompt_id}"); verified 2026-10-20
                job = self._json("GET", f"/api/jobs/{prompt_id}")
                return job.get("outputs") or {}
            if st in TERMINAL_FAIL:
                raise CloudJobFailed(f"job {prompt_id} ended {st}")
            self.sleep(self.poll_s)
            waited += self.poll_s
        raise CloudJobFailed(f"job {prompt_id} timed out after {int(self.timeout_s)}s")

    def download(self, outputs: dict, out_dir: Path) -> list[Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for node_out in outputs.values():
            for key in ("images", "video", "videos", "gifs", "audio"):
                for fi in node_out.get(key, []) or []:
                    q = urllib.parse.urlencode({"filename": fi["filename"],
                                                "subfolder": fi.get("subfolder", ""),
                                                "type": fi.get("type", "output")})
                    status, hdrs, data = self._call("GET", f"/api/view?{q}", ctype=None)
                    if status in (301, 302, 303, 307, 308):
                        loc = hdrs.get("Location") or hdrs.get("location")
                        # signed URL carries its own auth: send NO key
                        status, _, data = self.transport("GET", loc, {}, None)
                    if status >= 400:
                        raise CloudJobFailed(f"download {fi['filename']} -> HTTP {status}")
                    dest = out_dir / Path(fi["filename"]).name
                    dest.write_bytes(data)
                    saved.append(dest)
        return saved

    # -- one job / many ---------------------------------------------------------
    def run(self, graph: dict, out_dir: Path, *, inputs: dict[str, Path] | None = None,
            open_weights: bool = True) -> list[Path]:
        g = self.prepare(graph, open_weights=open_weights)  # guard before any upload
        if inputs:
            g = self.upload_inputs(g, inputs)
        return self.download(self.wait(self.submit(g)), out_dir)

    def run_many(self, jobs: list[dict]) -> list[list[Path] | BaseException]:
        """jobs: dicts with graph, out_dir, optional inputs/open_weights. <= max_parallel at once."""
        for j in jobs:  # refuse the whole batch up front if any job is bad
            self.prepare(j["graph"], open_weights=j.get("open_weights", True))

        def one(j):
            try:
                return self.run(j["graph"], j["out_dir"], inputs=j.get("inputs"),
                                open_weights=j.get("open_weights", True))
            except BaseException as e:  # noqa: BLE001
                return e
        with ThreadPoolExecutor(max_workers=self.max_parallel) as ex:
            return list(ex.map(one, jobs))


def make_backend(cfg: dict | None, **kw):
    """None for local (callers keep their existing code path); CloudBackend for cloud."""
    name = backend_name(cfg)
    if name == "local":
        return None
    if name == "cloud":
        return CloudBackend.from_config(cfg, **kw)
    raise ValueError(f"unknown comfy.backend {name!r} (local|cloud)")
