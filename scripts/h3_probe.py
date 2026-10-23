"""MiniMax H3 feasibility probe: one audio-anchored image-to-video clip through ComfyUI.

Submits workflows/minimax_h3_i2v_api.json via comfy-sdk (comfy-api-proxy :8189, like
scripts/vibe_objects/make_library.py), times the job, polls ComfyUI's /system_stats for VRAM
before/during/after, saves the clip, optionally copies it to the Desktop, and writes a
<out>.json record next to the clip (timings, VRAM peak, graph settings, log excerpt).

    .venv\\Scripts\\python scripts\\h3_probe.py --still work\\v4\\in\\polly_576.png ^
        --audio <scratch>\\seg_196s_5p5s.wav --length 124 --out <scratch>\\h3_124.mp4 --copy-desktop

Never restarts or reconfigures ComfyUI; it only queues one prompt.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8189"
os.environ.pop("COMFY_API_KEY", None)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from comfy_sdk import Comfy, JobFailed  # noqa: E402

GRAPH = ROOT / "workflows" / "minimax_h3_i2v_api.json"
COMFY = "http://127.0.0.1:8188"
COMFY_LOG = Path(r"C:\Users\tyson\AI\ComfyUI\user\comfyui_8188.log")
DESKTOP_COPY = Path(r"C:\Users\tyson\Desktop\xeno_h3_test.mp4")
GB = 1024 ** 3


def _get(url: str, timeout: float = 5.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def stats_sample() -> dict:
    s = _get(f"{COMFY}/system_stats")
    d = s["devices"][0]
    return {
        "t": time.time(),
        "vram_used_gb": round((d["vram_total"] - d["vram_free"]) / GB, 2),
        "torch_vram_gb": round(d["torch_vram_total"] / GB, 2),
        "ram_free_gb": round(s["system"]["ram_free"] / GB, 2),
    }


class VramPoller(threading.Thread):
    """Samples /system_stats; each sample is tagged ``mine`` when our prompt is the one
    ComfyUI is executing, so other people's queued jobs don't pollute the peak."""

    def __init__(self, period: float = 2.0) -> None:
        super().__init__(daemon=True)
        self.period = period
        self.samples: list[dict] = []
        self.job_id: str | None = None
        self._halt = threading.Event()  # not ``_stop``: Thread.join() calls self._stop()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                s = stats_sample()
                running = _get(f"{COMFY}/queue").get("queue_running", [])
                s["mine"] = bool(self.job_id) and any(len(it) > 1 and it[1] == self.job_id for it in running)
                self.samples.append(s)
            except Exception as e:  # ComfyUI busy or momentarily unreachable
                self.samples.append({"t": time.time(), "error": str(e)[:80]})
            self._halt.wait(self.period)

    def stop(self) -> None:
        self._halt.set()


def log_excerpt(n: int = 200) -> list[str]:
    """Interesting lines from the last n lines of the ComfyUI log (never more)."""
    try:
        lines = COMFY_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []
    keys = ("minimax", "qwen", "oom", "out of memory", "it/s", "prompt executed", "error", "traceback",
            "staged", "requested to load", "lowvram", "partially")
    return [ln for ln in lines if any(k in ln.lower() for k in keys)][-40:]


def ffprobe(path: Path) -> dict:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size:stream=codec_type,width,height,r_frame_rate,sample_rate,channels",
             "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    except Exception as e:
        return {"error": str(e)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--still", required=True, help="first-frame still (png/jpg)")
    ap.add_argument("--audio", required=True, help="soundtrack to anchor at frame 0 (wav/mp3)")
    ap.add_argument("--prompt", default=None, help="override the graph's prompt")
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--height", type=int, default=832)
    ap.add_argument("--length", type=int, default=124, help="frames at 24 fps; snaps up to 17k+5 (124 = 5.17 s)")
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", required=True, help="where to save the mp4")
    ap.add_argument("--copy-desktop", action="store_true", help=f"also copy to {DESKTOP_COPY}")
    ap.add_argument("--poll", type=float, default=2.0, help="seconds between /system_stats samples")
    ap.add_argument("--no-audio-guide", action="store_true",
                    help="control run: drop the AddGuide/LoadAudio nodes so H3 invents its own soundtrack")
    a = ap.parse_args()

    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    still, audio = Path(a.still).resolve(), Path(a.audio).resolve()
    for p in (still, audio, GRAPH):
        if not p.exists():
            print(f"missing: {p}", file=sys.stderr)
            return 2

    queue = _get(f"{COMFY}/queue")
    busy = len(queue.get("queue_running", [])) + len(queue.get("queue_pending", []))
    before = stats_sample()
    print(f"queue before submit: {busy} job(s); VRAM used {before['vram_used_gb']} GB, "
          f"RAM free {before['ram_free_gb']} GB", flush=True)

    client = Comfy(client_info="xenoform-h3-probe", timeout=None)
    wf = client.workflows.from_file(str(GRAPH))
    wf.set_input("15", "image", client.assets.from_file(str(still)))
    if a.no_audio_guide:
        wf.json["6"]["inputs"]["conditioning"] = ["5", 0]  # guider straight off the i2v conditioning
        wf.json.pop("17"), wf.json.pop("16")
    else:
        wf.set_input("16", "audio", client.assets.from_file(str(audio)))
    if a.prompt:
        wf.set_input("5", "prompt", a.prompt)
    wf.set_input("5", "width", a.width)
    wf.set_input("5", "height", a.height)
    wf.set_input("5", "length", a.length)
    wf.set_input("8", "steps", a.steps)
    wf.set_input("9", "noise_seed", a.seed)
    wf.set_input("14", "filename_prefix", f"video/xenoform_h3_{out.stem}")

    poller = VramPoller(a.poll)
    poller.start()
    t0 = time.time()
    record: dict = {
        "graph": str(GRAPH), "still": str(still), "audio": str(audio),
        "width": a.width, "height": a.height, "length": a.length, "steps": a.steps, "seed": a.seed,
        "prompt": wf.json["5"]["inputs"]["prompt"], "queue_ahead": busy, "stats_before": before,
        "audio_guide": not a.no_audio_guide,
    }
    try:
        job = client.submit(wf)
        record["job_id"] = getattr(job, "id", None) or getattr(job, "job_id", None)
        poller.job_id = record["job_id"]
        print(f"submitted job {record['job_id']}", flush=True)
        r = job.result()
        wall = time.time() - t0
        outs = list(r.get_outputs("14")) or list(r.outputs)
        vid = next((x for x in outs if getattr(x, "type", None) == "video"), outs[0])
        vid.to_file(str(out))
        record["status"] = "ok"
    except JobFailed as e:
        wall = time.time() - t0
        record["status"] = "failed"
        record["error"] = str(e)[:2000]
        print(f"JOB FAILED after {wall:.0f}s: {e}", file=sys.stderr)
    finally:
        poller.stop()
        poller.join(timeout=5)

    time.sleep(2)
    after = stats_sample()
    good = [s for s in poller.samples if "vram_used_gb" in s]
    mine = [s for s in good if s.get("mine")] or good  # fall back to all samples if never tagged
    peak = max(mine, key=lambda s: s["vram_used_gb"]) if mine else None
    first_mine = next((s["t"] for s in good if s.get("mine")), None)
    record.update({
        "wall_s": round(wall, 1),
        "queue_wait_s": round(first_mine - t0, 1) if first_mine else None,
        "run_s": round(t0 + wall - first_mine, 1) if first_mine else None,
        "stats_after": after,
        "vram_peak_used_gb": peak["vram_used_gb"] if peak else None,
        "torch_vram_peak_gb": max((s["torch_vram_gb"] for s in mine), default=None),
        "ram_free_min_gb": min((s["ram_free_gb"] for s in mine), default=None),
        "samples": len(poller.samples),
        "samples_mine": len([s for s in good if s.get("mine")]),
        "log_excerpt": log_excerpt(),
    })
    if record["status"] == "ok":
        record["output"] = str(out)
        record["probe"] = ffprobe(out)
        if a.copy_desktop:
            shutil.copyfile(out, DESKTOP_COPY)
            record["desktop_copy"] = str(DESKTOP_COPY)
    rec_path = out.with_suffix(".json")
    rec_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("status", "wall_s", "queue_wait_s", "run_s", "vram_peak_used_gb",
                                              "torch_vram_peak_gb", "ram_free_min_gb", "output") if k in record}, indent=1))
    print(f"record: {rec_path}")
    return 0 if record["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
