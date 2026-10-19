"""Simple Make renders on the GPU when ComfyUI is up.

The proxy path keeps /api/v2/assets. Stock ComfyUI answers that route with
405, and the same submit then uses /upload/image and /prompt.
"""

import json
from pathlib import Path

import numpy as np

from xenoform.config import load_config
from xenoform.restyle import restyle
from xenoform.video import write_mp4


def _features(n_frames, fps):
    frames = []
    for i in range(n_frames):
        section = "drop" if i >= n_frames // 2 else "calm"
        frames.append(
            {
                "i": i,
                "t": i / fps,
                "energy": 0.4,
                "onset_env": 0.0,
                "section": section,
                "is_drop": section == "drop",
                "is_beat": False,
                "beat_env": 0.0,
            }
        )
    return {
        "fps": fps,
        "n_frames": n_frames,
        "duration": n_frames / fps,
        "beats": [],
        "sections": [
            {"start_frame": 0, "end_frame": n_frames // 2, "label": "calm"},
            {"start_frame": n_frames // 2, "end_frame": n_frames, "label": "drop"},
        ],
        "frames": frames,
    }


def _cfg():
    cfg = load_config()
    cfg["quality"] = "turbo"
    cfg["segment"] = {"target_seconds": 2.0, "min_seconds": 1.0, "max_seconds": 4.0}
    cfg["comfy"]["mode"] = "live"
    cfg["comfy"]["width"] = 384
    cfg["comfy"]["height"] = 224
    cfg["comfy"]["base_url"] = "http://127.0.0.1:8188"
    cfg["comfy"]["proxy_url"] = "http://127.0.0.1:8189"
    cfg["comfy"]["send_api_key"] = False
    return cfg


class _Output:
    type = "video"

    def to_file(self, dest):
        Path(dest).write_bytes(b"sdk-video")


class _Result:
    id = "sdk-job"
    outputs: list = []

    def get_outputs(self, node):
        return [_Output()]


class _Running:
    id = "sdk-job"

    def events(self):
        return []

    def result(self):
        return _Result()


class _Workflow:
    def set_input(self, *args):
        return None


class _Assets:
    def __init__(self):
        self.paths = []

    def from_file(self, path):
        self.paths.append(str(path))
        return {"path": str(path)}


class _Client:
    def __init__(self, status):
        self.workflows = self
        self.assets = _Assets()
        self.status = status
        self.submits = 0
        self.keys = []

    def from_file(self, path):
        return _Workflow()

    def submit(self, workflow, **kwargs):
        self.submits += 1
        self.keys.append(sorted(kwargs))
        if self.status == 405:
            from comfy_sdk import ComfyError

            raise ComfyError(
                "POST /api/v2/assets method not allowed",
                code="method_not_allowed",
                http_status=405,
            )
        if self.status:
            raise RuntimeError("checkpoint missing")
        return _Running()


class _Response:
    def __init__(self, payload=None, content=b""):
        self.status_code = 200
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _Stock:
    def __init__(self, *args, **kwargs):
        self.prompts = []
        self.urls = []

    def post(self, url, **kwargs):
        self.urls.append(url)
        if url.endswith("/upload/image"):
            return _Response({"name": "chunk.mp4", "subfolder": "", "type": "input"})
        if url.endswith("/prompt"):
            body = kwargs.get("json") or {}
            self.prompts.append(body)
            return _Response({"prompt_id": "p1", "node_errors": {}})
        raise AssertionError(url)

    def get(self, url, **kwargs):
        self.urls.append(url)
        if "/history/" in url:
            return _Response(
                {
                    "p1": {
                        "status": {"completed": True, "status_str": "success"},
                        "outputs": {
                            "19": {
                                "videos": [
                                    {"filename": "out.mp4", "subfolder": "", "type": "output"}
                                ]
                            }
                        },
                    }
                }
            )
        if "/view" in url:
            return _Response(content=b"gpu-video")
        raise AssertionError(url)

    def close(self):
        return None


def _video(tmp_path: Path) -> Path:
    frames = [np.zeros((32, 32, 3), dtype=np.uint8) for _ in range(24)]
    path = tmp_path / "base.mp4"
    write_mp4(path, frames, 12, crf=28)
    return path


def test_live_uses_v2_assets_when_the_proxy_accepts_them(tmp_path, monkeypatch):
    client = _Client(status=None)
    monkeypatch.setattr("xenoform.restyle._make_client", lambda cfg: client)

    def stock_forbidden(*args, **kwargs):
        raise AssertionError("stock path used")

    monkeypatch.setattr("xenoform.restyle._run_stock", stock_forbidden)
    manifest = restyle(_features(24, 12), _video(tmp_path), tmp_path / "chunks", _cfg(), mode="live")
    assert client.assets.paths
    assert client.submits >= 1
    assert all("api_key" not in keys for keys in client.keys)
    assert manifest["note"].startswith("chunks were submitted with comfy_sdk")
    assert {chunk["submit"] for chunk in manifest["chunks"]} == {"sdk"}
    for chunk in manifest["chunks"]:
        assert Path(chunk["output"]).read_bytes() == b"sdk-video"


def test_live_falls_back_to_upload_and_prompt_on_405(tmp_path, monkeypatch):
    client = _Client(status=405)
    monkeypatch.setattr("xenoform.restyle._make_client", lambda cfg: client)
    stocks: list[_Stock] = []

    def factory(*args, **kwargs):
        http = _Stock()
        stocks.append(http)
        return http

    monkeypatch.setattr("httpx.Client", factory)
    manifest = restyle(_features(24, 12), _video(tmp_path), tmp_path / "chunks", _cfg(), mode="live")
    assert client.assets.paths
    assert client.submits >= 1
    assert stocks
    assert manifest["note"].startswith("chunks were submitted to stock ComfyUI")
    assert {chunk["submit"] for chunk in manifest["chunks"]} == {"stock"}
    for http in stocks:
        assert any(url.endswith("/upload/image") for url in http.urls)
        assert any(url.endswith("/prompt") for url in http.urls)
        assert any("/history/" in url for url in http.urls)
        assert http.prompts
        posted = json.dumps(http.prompts)
        assert "api_key" not in posted
        assert "/upload/image" not in posted
        for body in http.prompts:
            assert body["client_id"] == "xenoform"
            assert body["prompt"]["6"]["inputs"]["file"] == "chunk.mp4"
    for chunk in manifest["chunks"]:
        assert Path(chunk["output"]).read_bytes() == b"gpu-video"


def test_a_missing_checkpoint_does_not_pretend_to_be_stock(tmp_path, monkeypatch):
    monkeypatch.setattr("xenoform.restyle._make_client", lambda cfg: _Client(status=500))

    def stock_forbidden(*args, **kwargs):
        raise AssertionError("stock path used")

    monkeypatch.setattr("xenoform.restyle._run_stock", stock_forbidden)
    try:
        restyle(_features(24, 12), _video(tmp_path), tmp_path / "chunks", _cfg(), mode="live")
    except RuntimeError as exc:
        assert "checkpoint missing" in str(exc)
    else:
        raise AssertionError("expected the checkpoint error")


def test_simple_make_asks_for_a_live_render_and_keeps_the_preview():
    root = Path(__file__).resolve().parents[1]
    script = (root / "src" / "xenoform" / "ui_static" / "app.js").read_text(encoding="utf-8")
    make = script.split("async function easyMake", 1)[1].split("async function easyBetter", 1)[0]
    assert "state.comfyOk" in make
    assert "state.live = true" in make
    assert "state.live = false" not in make
    assert "Cutting a preview, then the GPU pass." in make
    assert "showEasyPreview" in script
    css = (root / "src" / "xenoform" / "ui_static" / "app.css").read_text(encoding="utf-8")
    assert "shimmer" not in css
