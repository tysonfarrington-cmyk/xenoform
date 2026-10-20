import json
import threading
import time

import pytest

from xenoform import cloud_backend as cb

KEY = "sk-test-SECRET-123"


class FakeCloud:
    def __init__(self, statuses=("queued_waiting", "executing", "success"), delay=0.0):
        self.calls = []
        self.statuses = list(statuses)
        self.delay = delay
        self.live = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.n = 0

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if url.startswith("https://signed.example/"):
            assert "X-API-Key" not in headers
            return 200, {}, b"MP4DATA"
        assert headers.get("X-API-Key") == KEY
        path = url.split("cloud.comfy.org", 1)[1]
        if path == "/api/upload/image":
            return 200, {}, json.dumps({"name": "abc123.png", "subfolder": ""}).encode()
        if path == "/api/prompt":
            with self.lock:
                self.n += 1
                pid = f"p{self.n}"
                self.live += 1
                self.peak = max(self.peak, self.live)
            return 200, {}, json.dumps({"prompt_id": pid}).encode()
        if path.endswith("/status"):
            time.sleep(self.delay)
            pid = path.split("/")[3]
            st = self.statuses[min(len([c for c in self.calls if c[1].endswith(f"/{pid}/status")]) - 1,
                                   len(self.statuses) - 1)]
            if st == "success" or st in cb.TERMINAL_FAIL:
                with self.lock:
                    self.live -= 1
            return 200, {}, json.dumps({"status": st}).encode()
        if path.startswith("/api/history/"):
            pid = path.rsplit("/", 1)[1]
            out = {"9": {"video": [{"filename": f"{pid}.mp4", "subfolder": "", "type": "output"}]}}
            return 200, {}, json.dumps({pid: {"outputs": out}}).encode()
        if path.startswith("/api/view"):
            return 302, {"Location": "https://signed.example/x.mp4?sig=1"}, b""
        return 404, {}, b"nope"


def graph(*extra):
    g = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "local.png"}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "ltx-2.3-22b-distilled.safetensors"}},
        "9": {"class_type": "SaveVideo", "inputs": {}},
    }
    for i, ct in enumerate(extra):
        g[str(20 + i)] = {"class_type": ct, "inputs": {}}
    return g


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv(cb.KEY_ENV, KEY)


def backend(fake, **kw):
    return cb.CloudBackend(transport=fake, sleep=lambda s: None, poll_s=0.01,
                           model_map={"ltx-2.3-22b-distilled.safetensors": "ltx-2.3-22b-distilled-fp8.safetensors"}, **kw)


def test_local_is_default_and_untouched():
    assert cb.backend_name({}) == "local"
    assert cb.make_backend({"comfy": {"base_url": "http://127.0.0.1:8188"}}) is None
    assert isinstance(cb.make_backend({"comfy": {"backend": "cloud"}}), cb.CloudBackend)
    with pytest.raises(ValueError):
        cb.make_backend({"comfy": {"backend": "runpod?"}})


def test_parallel_capped_at_three():
    b = cb.CloudBackend.from_config({"comfy": {"backend": "cloud", "cloud_parallel": 9}})
    assert b.max_parallel == 3


def test_full_run_upload_map_submit_download(tmp_path, key):
    src = tmp_path / "in.png"
    src.write_bytes(b"PNG")
    fake = FakeCloud()
    saved = backend(fake).run(graph(), tmp_path / "out", inputs={"1": src})
    assert [p.name for p in saved] == ["p1.mp4"] and saved[0].read_bytes() == b"MP4DATA"
    sent = json.loads(next(c[3] for c in fake.calls if c[1].endswith("/api/prompt")))["prompt"]
    assert sent["1"]["inputs"]["image"] == "abc123.png"
    assert sent["2"]["inputs"]["ckpt_name"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    assert "extra_data" not in json.loads(next(c[3] for c in fake.calls if c[1].endswith("/api/prompt")))


@pytest.mark.parametrize("node", ["LtxApi25ImageToVideo", "GemmaAPITextEncode",
                                  "FluxProUltraImageNode", "BlackForestLabsFlux3API", "KlingApiImage2Video"])
def test_partner_nodes_hard_blocked_before_any_http(tmp_path, key, node):
    fake = FakeCloud()
    with pytest.raises(cb.CloudRefused, match="partner"):
        backend(fake).run(graph(node), tmp_path)
    assert fake.calls == []


def test_upscale_stays_local(tmp_path, key):
    fake = FakeCloud()
    with pytest.raises(cb.CloudRefused, match="local"):
        backend(fake).run(graph("ImageUpscaleWithModel"), tmp_path)
    assert fake.calls == []


def test_core_ltx_nodes_not_flagged():
    for ct in ["LTXVConditioning", "LTXVAudioVAELoader", "CLIPVisionEncode", "ModelSamplingAuraFlow",
               "WanAnimate2ToVideo", "SamplerCustomAdvanced", "LTXVImgToVideoInplace"]:
        assert not cb.is_partner_node(ct), ct


def test_batch_refused_whole_if_one_bad(tmp_path, key):
    fake = FakeCloud()
    jobs = [{"graph": graph(), "out_dir": tmp_path / "a"},
            {"graph": graph("LtxApi25ImageToVideo"), "out_dir": tmp_path / "b"}]
    with pytest.raises(cb.CloudRefused):
        backend(fake).run_many(jobs)
    assert fake.calls == []


def test_run_many_three_at_a_time(tmp_path, key):
    fake = FakeCloud(statuses=("executing", "executing", "success"), delay=0.02)
    jobs = [{"graph": graph(), "out_dir": tmp_path / str(i)} for i in range(7)]
    res = backend(fake).run_many(jobs)
    assert all(isinstance(r, list) and len(r) == 1 for r in res)
    assert 1 <= fake.peak <= 3


def test_missing_key_refuses_without_leak(tmp_path, monkeypatch):
    monkeypatch.delenv(cb.KEY_ENV, raising=False)
    fake = FakeCloud()
    with pytest.raises(cb.CloudRefused, match="COMFY_ORG_API_KEY"):
        backend(fake).run(graph(), tmp_path)
    assert fake.calls == []


def test_failures_and_key_never_in_messages(tmp_path, key):
    fake = FakeCloud(statuses=("executing", "error"))
    with pytest.raises(cb.CloudJobFailed) as e:
        backend(fake).run(graph(), tmp_path)
    assert KEY not in str(e.value)

    def credits(method, url, headers, body):
        return 402, {}, KEY.encode()
    with pytest.raises(cb.CloudJobFailed, match="credits") as e:
        backend(credits).run(graph(), tmp_path)
    assert KEY not in str(e.value)


def test_timeout(tmp_path, key):
    fake = FakeCloud(statuses=("queued_waiting",))
    b = backend(fake)
    b.timeout_s = 0.05
    with pytest.raises(cb.CloudJobFailed, match="timed out"):
        b.run(graph(), tmp_path)


def test_model_map_file_loads():
    m = cb.load_model_map()
    assert "ltx-2.3-22b-distilled-fp8.safetensors" in m


def test_smoke_combo_options_both_styles():
    import importlib.util, pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "cloud_smoke.py"
    spec = importlib.util.spec_from_file_location("cloud_smoke", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.combo_options([["a.safetensors"], {}]) == ["a.safetensors"]
    assert m.combo_options(["COMBO", {"options": ["b.safetensors"]}]) == ["b.safetensors"]
    assert m.combo_options(["INT", {"default": 1}]) is None
