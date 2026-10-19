"""Overnight self-scoring auto-tuner for Simple mode's morph engine (LTX 0.9.5 A->B graph).

Renders single morphs through comfy-sdk -> comfy-api-proxy (127.0.0.1:8189) with the
fixed graph ``workflows/xenoform_morph.json``, scores each with ``score.py`` (CPU, run
as a worker under ComfyUI's venv), keeps a leaderboard, and steers sampling toward
promising settings with a small evolutionary search. Free and local: no API keys,
no tokens, no cloud.

Phases
  1 coverage  - the shipping default on every adjacent pair of every vibe pool
                (the pairs Simple mode actually renders) -> pair baselines, bad pairs.
  2 search    - per vibe: mutate one setting of a top config (UCB over pair-centred
                scores), 25% fresh random configs, random pair from the pool.
  final       - recommended defaults per vibe, bad-pair blocklist, contact sheet,
                best-of reel.

Resumable: every finished clip is a line in runs.jsonl; a restart replays it.
Hard stop: stops queuing when the next job would cross --until, finalises, exits.

usage: autotune.py [--until 06:30 | --minutes 10] [--out DIR] [--phase1-limit N]
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import datetime as dt
import json
import math
import os
import random
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "workflows" / "xenoform_morph.json"
OBJECTS = ROOT / "src" / "xenoform" / "ui_static" / "objects"
SCORER = Path(__file__).with_name("score.py")
COMFY_PY = Path(os.environ.get("XENO_COMFY_PY", r"C:\Users\tyson\AI\ComfyUI\.venv\Scripts\python.exe"))
COMFY_BAT = Path(os.environ.get("XENO_COMFY_BAT", r"C:\Users\tyson\AI\ComfyUI\run_comfy_3080ti_tf32off.bat"))
PROXY_BAT = ROOT / "_judge_proxy.bat"
COMFY = "http://127.0.0.1:8188"
PROXY = "http://127.0.0.1:8189"
VRAM_LIMIT = int(os.environ.get("XENO_VRAM_LIMIT_MIB", "11500"))
LENGTH = 65          # frames per test morph (~2.7 s at 24 fps; Simple-mode shots are 49-121)
JOB_TIMEOUT = 300
BLOCK = int(os.environ.get("XENO_TUNE_BLOCK", "12"))

sys.path.insert(0, str(ROOT / "src"))
from xenoform.morph_pass import NEGATIVE, VIBE_LOOK, prompt_for  # noqa: E402

SPACE = {
    "steps": [12, 16, 20],
    "cfg": [2.0, 3.0, 4.0],
    "comp": [0, 18, 30],
    "prompt": ["vibe", "pair", "plain"],
    "res": ["512x288", "640x352"],
    "strength": [1.0, 0.85],
}
DEFAULT = {"steps": 20, "cfg": 3.0, "comp": 18, "prompt": "vibe", "res": "512x288", "strength": 1.0}
MIN_N = int(os.environ.get("XENO_TUNE_MIN_N", "3"))         # samples before a setting can be recommended
MIN_GAIN = float(os.environ.get("XENO_TUNE_MIN_GAIN", "1.5"))  # score points over the default to switch
TIME_BUDGET_S = float(os.environ.get("XENO_TUNE_BUDGET_S", "8.0"))  # per-morph render budget for the live default


def key(cfg: dict) -> str:
    return "s{steps}_c{cfg:g}_k{comp}_{prompt}_{res}_g{strength:g}".format(**cfg)


def now() -> dt.datetime:
    return dt.datetime.now()


class Log:
    def __init__(self, path: Path):
        self.f = open(path, "a", encoding="utf-8")

    def __call__(self, *parts):
        line = f"{now():%Y-%m-%d %H:%M:%S} " + " ".join(str(p) for p in parts)
        print(line, flush=True)
        self.f.write(line + "\n"); self.f.flush()


def http_ok(url: str, timeout: float = 5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def wmi_launch(cmdline: str, cwd: str):
    ps = (f"Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
          f"@{{CommandLine='{cmdline}'; CurrentDirectory='{cwd}'}} | Out-Null")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


def ensure_services(log: Log, allow_restart: bool) -> bool:
    if not http_ok(COMFY + "/system_stats"):
        if not allow_restart:
            log("ComfyUI not answering; waiting (restart only allowed at start)")
            for _ in range(60):
                time.sleep(10)
                if http_ok(COMFY + "/system_stats"):
                    break
            else:
                return False
        else:
            log("ComfyUI down at start; relaunching", COMFY_BAT.name, "detached via WMI")
            wmi_launch(f"cmd /c {COMFY_BAT}", str(COMFY_BAT.parent))
            for _ in range(36):
                time.sleep(10)
                if http_ok(COMFY + "/system_stats"):
                    log("ComfyUI is up"); break
            else:
                log("ComfyUI did not come up"); return False
    if not http_ok(PROXY + "/api/v2/assets", 5) and not _port_open(8189):
        log("proxy on 8189 down; starting", PROXY_BAT.name)
        wmi_launch(f"cmd /c {PROXY_BAT}", str(ROOT))
        for _ in range(12):
            time.sleep(5)
            if _port_open(8189):
                break
        else:
            log("proxy did not come up"); return False
    return True


def _port_open(port: int) -> bool:
    import socket
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", port)) == 0


class VramMon(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.peak = 0; self.cur = 0; self.lock = threading.Lock()

    def run(self):
        while True:
            try:
                out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
                v = int(out[0]) if out else 0
                with self.lock:
                    self.cur = v; self.peak = max(self.peak, v)
            except Exception:
                pass
            time.sleep(0.5)

    def reset(self) -> None:
        with self.lock:
            self.peak = self.cur

    def take(self) -> int:
        with self.lock:
            return self.peak


class Scorer:
    def __init__(self, log: Log):
        env = dict(os.environ, HF_HUB_DISABLE_IMPLICIT_TOKEN="1", PYTHONIOENCODING="utf-8")
        env.pop("HF_TOKEN", None)
        if os.environ.get("XENO_SCORE_ONLINE") != "1":
            env["HF_HUB_OFFLINE"] = "1"
        self.p = subprocess.Popen([str(COMFY_PY), str(SCORER), "--worker"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=open(log.f.name + ".scorer", "a"),
                                  text=True, encoding="utf-8", env=env, cwd=str(SCORER.parent))

    def score(self, **req) -> dict:
        self.p.stdin.write(json.dumps(req) + "\n"); self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            return {"ok": False, "error": "scorer exited"}
        return json.loads(line)

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(10)
        except Exception:
            self.p.kill()


def pools() -> dict[str, list[dict]]:
    man = json.loads((OBJECTS / "objects.json").read_text(encoding="utf-8"))
    return {v: [dict(o, path=str(OBJECTS / o["file"])) for o in items] for v, items in man.items()}


def pairs_for(pool: list[dict]) -> list[tuple[int, int]]:
    return [(i, (i + 1) % len(pool)) for i in range(len(pool))]


def prompt_text(variant: str, vibe: str, a: dict, b: dict) -> str:
    if variant == "pair":
        return (f"a {a['noun']} slowly melts and flows into a {b['noun']}, one continuous liquid transformation, "
                f"centred, {VIBE_LOOK.get(vibe, '')}, macro product photography, crisp, high detail")
    if variant == "plain":
        return f"one object smoothly transforms into another, {VIBE_LOOK.get(vibe, '')}, crisp, high detail"
    return prompt_for(vibe)


class Tuner:
    def __init__(self, out: Path, deadline: dt.datetime, log: Log, seed: int, phase1_limit: int | None):
        self.out = out; self.deadline = deadline; self.log = log
        self.clips = out / "clips"; self.clips.mkdir(parents=True, exist_ok=True)
        self.runs_path = out / "runs.jsonl"
        self.rng = random.Random(seed)
        self.pools = pools()
        self.runs: list[dict] = []
        if self.runs_path.exists():
            for line in self.runs_path.read_text(encoding="utf-8").splitlines():
                try:
                    self.runs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        self.banned_res: set[str] = {r["cfg"]["res"] for r in self.runs if r.get("vram_peak", 0) > VRAM_LIMIT}
        self.phase1_limit = phase1_limit
        self.vram = VramMon(); self.vram.start()
        self.scorer = Scorer(log)
        self.client = None
        self.graph = json.loads(GRAPH.read_text(encoding="utf-8"))
        self.assets = {}
        self.follow: list[tuple[str, dict, str]] = []

    # ---------- bookkeeping ----------
    def ok_runs(self, vibe: str | None = None) -> list[dict]:
        return [r for r in self.runs if r.get("ok") and (vibe is None or r["vibe"] == vibe)]

    def pair_mean(self) -> dict[str, float]:
        acc: dict[str, list[float]] = {}
        for r in self.ok_runs():
            acc.setdefault(r["pair"], []).append(r["score"])
        return {k: sum(v) / len(v) for k, v in acc.items()}

    def config_table(self, vibe: str | None = None) -> list[dict]:
        pm = self.pair_mean()
        acc: dict[str, dict] = {}
        for r in self.ok_runs(vibe):
            e = acc.setdefault(key(r["cfg"]), {"cfg": r["cfg"], "adv": [], "score": [], "secs": [], "vram": []})
            e["adv"].append(r["score"] - pm[r["pair"]]); e["score"].append(r["score"])
            e["secs"].append(r["render_s"]); e["vram"].append(r.get("vram_peak", 0))
        rows = []
        for k, e in acc.items():
            n = len(e["adv"])
            rows.append({"key": k, "cfg": e["cfg"], "n": n, "adv": sum(e["adv"]) / n, "score": sum(e["score"]) / n,
                         "secs": sorted(e["secs"])[n // 2], "min_secs": min(e["secs"]), "vram": max(e["vram"])})
        return sorted(rows, key=lambda r: -r["adv"])

    # ---------- sampling ----------
    def done_phase1(self) -> set[str]:
        return {r["pair"] for r in self.runs if key(r["cfg"]) == key(DEFAULT)}

    def next_job(self) -> tuple[str, int, int, dict, str]:
        done = self.done_phase1()
        todo = [(v, a, b) for v, pool in self.pools.items() for a, b in pairs_for(pool)
                if f"{v}:{a}-{b}" not in done]
        n1 = len(self.done_phase1())
        if todo and (self.phase1_limit is None or n1 < self.phase1_limit):
            v, a, b = todo[0]  # vibe by vibe, so the CPU text encode is cached
            return v, a, b, dict(DEFAULT), "coverage"
        # Stay on one vibe for a block of jobs: the text encoder runs on the CPU, and a
        # prompt change costs ~12 s, so switching vibe every job would waste the night.
        if self.follow:
            v, cfg, how = self.follow.pop(0)
            a, b = self.rng.choice(pairs_for(self.pools[v]))
            return v, a, b, cfg, how
        vibes = list(self.pools)
        v = vibes[(len(self.runs) // BLOCK) % len(vibes)]
        a, b = self.rng.choice(pairs_for(self.pools[v]))
        table = self.config_table(v)
        if not table or self.rng.random() < 0.25:
            cfg = {k: self.rng.choice(vals) for k, vals in SPACE.items()}
            how = "random"
        else:
            total = sum(r["n"] for r in table)
            ucb = sorted(table, key=lambda r: -(r["adv"] + 4.0 * math.sqrt(math.log(total + 1) / r["n"])))
            parent = ucb[min(len(ucb) - 1, int(self.rng.random() ** 2 * min(5, len(ucb))))]
            cfg = dict(parent["cfg"])
            if self.rng.random() < 0.3 and parent["n"] < 4:
                how = f"repeat {parent['key']}"
            else:
                k = self.rng.choice(list(SPACE))
                cfg[k] = self.rng.choice([x for x in SPACE[k] if x != cfg[k]])
                how = f"mutate {k} of {parent['key']}"
        if cfg["res"] in self.banned_res:
            cfg["res"] = "512x288"
        if not any(r["n"] for r in table if r["key"] == key(cfg)):
            self.follow += [(v, dict(cfg), f"follow-up {key(cfg)}")] * 2  # judge a new setting on 3 pairs
        return v, a, b, cfg, how

    # ---------- rendering ----------
    def _client(self):
        if self.client is None:
            os.environ["COMFY_BASE_URL"] = PROXY
            os.environ.pop("COMFY_API_KEY", None)
            from comfy_sdk import Comfy
            self.client = Comfy(client_info="xenoform-autotune", timeout=None)
        return self.client

    def _asset(self, path: str):
        if path not in self.assets:
            self.assets[path] = self._client().assets.from_file(path)
        return self.assets[path]

    def render(self, vibe: str, a: dict, b: dict, cfg: dict, seed: int, dest: Path) -> float:
        g = json.loads(json.dumps(self.graph))
        w, h = (int(x) for x in cfg["res"].split("x"))
        g["9"]["inputs"].update(width=w, height=h, length=LENGTH)
        g["11"]["inputs"]["steps"] = cfg["steps"]
        g["14"]["inputs"]["cfg"] = cfg["cfg"]
        g["8"]["inputs"]["img_compression"] = cfg["comp"]; g["21"]["inputs"]["img_compression"] = cfg["comp"]
        g["22"]["inputs"]["strength"] = cfg["strength"]
        g["3"]["inputs"]["text"] = prompt_text(cfg["prompt"], vibe, a, b)
        g["4"]["inputs"]["text"] = NEGATIVE
        g["13"]["inputs"]["noise_seed"] = seed
        g["19"]["inputs"]["filename_prefix"] = "xenoform/autotune"
        tmp = Path(tempfile.gettempdir()) / f"xeno_autotune_{os.getpid()}.json"
        tmp.write_text(json.dumps(g), encoding="utf-8")
        c = self._client()
        wf = c.workflows.from_file(str(tmp))
        wf.set_input("6", "image", self._asset(a["path"]))
        wf.set_input("7", "image", self._asset(b["path"]))
        t0 = time.perf_counter()
        job = c.submit(wf)
        box: dict = {}

        def wait():
            from comfy_sdk import JobFailed
            j = job
            for attempt in range(6):
                try:
                    box["r"] = j.result(); return
                except JobFailed as exc:
                    if "expired" not in str(exc) or attempt == 5:
                        box["e"] = exc; return
                    time.sleep(0.5 + attempt * 0.5)
                    j = c.jobs.get(j.id)
                except Exception as exc:
                    box["e"] = exc; return

        th = threading.Thread(target=wait, daemon=True); th.start(); th.join(JOB_TIMEOUT)
        if th.is_alive():
            self._interrupt()
            raise TimeoutError(f"job {job.id} over {JOB_TIMEOUT}s; interrupted")
        if "e" in box:
            raise box["e"]
        outs = list(box["r"].get_outputs("19")) or list(box["r"].outputs)
        if not outs:
            raise RuntimeError("no video output")
        outs[0].to_file(str(dest))
        return time.perf_counter() - t0

    def _interrupt(self):
        try:
            urllib.request.urlopen(urllib.request.Request(COMFY + "/interrupt", data=b"{}", method="POST",
                                                          headers={"Content-Type": "application/json"}), timeout=5)
        except Exception:
            pass

    # ---------- main loop ----------
    def est_job_s(self) -> float:
        secs = [r["render_s"] + r.get("score_s", 1) for r in self.runs[-20:] if r.get("ok")]
        return max(secs) if secs else 60.0

    def loop(self):
        self.log(f"autotune start; deadline {self.deadline:%Y-%m-%d %H:%M}; {len(self.runs)} runs on file")
        fails = 0
        while True:
            margin = dt.timedelta(seconds=self.est_job_s() + 15)
            if now() + margin >= self.deadline:
                self.log("deadline reached; stopping"); break
            if not ensure_services(self.log, allow_restart=False):
                self.log("services unavailable; stopping"); break
            v, ia, ib, cfg, how = self.next_job()
            pool = self.pools[v]; a, b = pool[ia], pool[ib]
            rid = f"{len(self.runs):05d}"
            seed = 1000 + self.rng.randrange(100000)
            dest = self.clips / f"{rid}_{v}_{ia:02d}-{ib:02d}_{key(cfg)}.mp4"
            rec = {"id": rid, "t": now().isoformat(timespec="seconds"), "vibe": v, "pair": f"{v}:{ia}-{ib}",
                   "a": a["noun"], "b": b["noun"], "cfg": cfg, "seed": seed, "how": how, "clip": dest.name}
            self.vram.reset()
            try:
                rec["render_s"] = round(self.render(v, a, b, cfg, seed, dest), 2)
                rec["vram_peak"] = self.vram.take()
                s = self.scorer.score(clip=str(dest), a=a["path"], b=b["path"], na=a["noun"], nb=b["noun"])
                if not s.get("ok"):
                    raise RuntimeError("score: " + str(s.get("error")))
                rec.update(ok=True, score=s["score"], sub=s["sub"], metrics=s["metrics"], score_s=s["score_s"])
                fails = 0
            except Exception as exc:
                rec.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:400], vram_peak=self.vram.take())
                fails += 1
            if rec.get("vram_peak", 0) > VRAM_LIMIT:
                self.banned_res.add(cfg["res"])
                self.log(f"VRAM {rec['vram_peak']} MiB over {VRAM_LIMIT}; banning {cfg['res']}")
            self.runs.append(rec)
            with open(self.runs_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
            self.log(rid, v, f"{a['noun']}->{b['noun']}", key(cfg), how,
                     f"score={rec.get('score')}" if rec.get("ok") else f"FAIL {rec.get('error')}",
                     f"{rec.get('render_s', '-')}s", f"{rec.get('vram_peak')}MiB")
            if fails >= 5:
                self.log("5 failures in a row; pausing 60 s"); time.sleep(60)
                if fails >= 15:
                    self.log("15 failures in a row; stopping"); break
            if len(self.runs) % 10 == 0:
                self.write_reports()
        self.write_reports()

    # ---------- outputs ----------
    def write_reports(self):
        rows = self.config_table()
        with open(self.out / "leaderboard.csv", "w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f)
            wr.writerow(["rank", "config", "n", "pair_centred_adv", "mean_score", "median_render_s", "min_render_s",
                         "vram_peak_mib"])
            for i, r in enumerate(rows, 1):
                wr.writerow([i, r["key"], r["n"], f"{r['adv']:.2f}", f"{r['score']:.2f}", r["secs"], r["min_secs"], r["vram"]])
        rec = {"generated": now().isoformat(timespec="seconds"), "runs": len(self.runs),
               "ok_runs": len(self.ok_runs()), "time_budget_s_per_morph": TIME_BUDGET_S,
               "default": DEFAULT, "vibes": {}}
        for v in self.pools:
            t = self.config_table(v)
            sure = [r for r in t if r["n"] >= MIN_N]
            # What the app can apply: the one-per-vibe prompt at 512x288 (a per-pair prompt
            # re-encodes on the CPU every morph); within the per-morph time budget.
            app_ok = [r for r in sure if r["cfg"]["prompt"] == "vibe" and r["cfg"]["res"] == "512x288"
                      and r["min_secs"] <= TIME_BUDGET_S]
            base = next((r for r in t if r["key"] == key(DEFAULT)), None)
            base_adv = base["adv"] if base else 0.0
            pick = app_ok[0] if app_ok and app_ok[0]["adv"] >= base_adv + MIN_GAIN else None
            rec["vibes"][v] = {
                "recommended": pick["cfg"] if pick else dict(DEFAULT),
                "why": (f"+{pick['adv'] - base_adv:.1f} over the default on {pick['n']} pairs" if pick
                        else "no app-usable setting beat the default by the margin; keep the default"),
                "adv": round(pick["adv"], 2) if pick else round(base_adv, 2),
                "n": pick["n"] if pick else (base["n"] if base else 0),
                "min_render_s": pick["min_secs"] if pick else (base["min_secs"] if base else None),
                "best_any": ({"cfg": sure[0]["cfg"], "adv": round(sure[0]["adv"], 2), "n": sure[0]["n"],
                              "median_render_s": sure[0]["secs"]} if sure else None),
                "default_adv": round(base_adv, 2) if base else None,
                "default_n": base["n"] if base else 0,
            }
        (self.out / "recommended.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        # bad pairs: mean score well below the vibe's pairs, or below an absolute floor
        pm: dict[str, list[float]] = {}
        sub: dict[str, dict] = {}
        for r in self.ok_runs():
            pm.setdefault(r["pair"], []).append(r["score"])
            for k, val in r["sub"].items():
                sub.setdefault(r["pair"], {}).setdefault(k, []).append(val)
        bad = []
        for v, pool in self.pools.items():
            means = {p: sum(s) / len(s) for p, s in pm.items() if p.startswith(v + ":")}
            if len(means) < 3:
                continue
            vals = sorted(means.values()); med = vals[len(vals) // 2]
            for p, m in means.items():
                if (m < 70 or m < med - 8) and (len(pm[p]) >= 2 or m < 70):
                    ia, ib = (int(x) for x in p.split(":")[1].split("-"))
                    worst = sorted(((sum(x) / len(x), k) for k, x in sub[p].items()))[:2]
                    bad.append({"vibe": v, "a": pool[ia]["file"], "b": pool[ib]["file"], "mean_score": round(m, 2),
                                "vibe_median": round(med, 2), "n": len(pm[p]),
                                "weakest": [f"{k} {val:.2f}" for val, k in worst]})
        (self.out / "bad_pairs.json").write_text(json.dumps({"generated": rec["generated"], "pairs": bad}, indent=1),
                                                 encoding="utf-8")
        # app-readable bundle (copy to configs/autotune.json after review)
        app = {"generated": rec["generated"], "source": "scripts/autotune",
               "vibes": {v: {"steps": d["recommended"]["steps"], "cfg": d["recommended"]["cfg"],
                             "img_compression": d["recommended"]["comp"], "guide_end_strength": d["recommended"]["strength"]}
                         for v, d in rec["vibes"].items()},
               "bad_pairs": [[b["a"], b["b"]] for b in bad]}
        (self.out / "autotune.json").write_text(json.dumps(app, indent=1), encoding="utf-8")

    def finalize(self):
        self.write_reports()
        ok = sorted(self.ok_runs(), key=lambda r: -r["score"])
        if not ok:
            return
        ff = os.environ.get("FFMPEG", "ffmpeg")
        tmp = self.out / "_sheet"; tmp.mkdir(exist_ok=True)
        font = "C\\:/Windows/Fonts/arial.ttf"

        def label(r):
            return f"{r['score']:.1f} {r['vibe']} {r['a']}-{r['b']} {key(r['cfg'])}".replace(":", " ").replace("'", "")

        def tile(rows, name):
            pics = []
            for i, r in enumerate(rows):
                p = tmp / f"{name}_{i:02d}.png"
                subprocess.run([ff, "-v", "error", "-y", "-ss", "1.3", "-i", str(self.clips / r["clip"]), "-frames:v", "1",
                                "-vf", f"scale=320:180,drawtext=fontfile='{font}':text='{label(r)}':fontsize=11:"
                                       "fontcolor=white:box=1:boxcolor=black@0.6:x=4:y=4", str(p)], check=False)
                if p.exists():
                    pics.append(p)
            if pics:
                cols = 4; rows_n = math.ceil(len(pics) / cols)
                subprocess.run([ff, "-v", "error", "-y", "-i", str(tmp / f"{name}_%02d.png"), "-vf",
                                f"tile={cols}x{rows_n}", "-frames:v", "1", str(self.out / f"{name}.jpg")], check=False)
        tile(ok[:24], "contact_best")
        tile(ok[-12:], "contact_worst")
        best = []
        for v in self.pools:
            vb = [r for r in ok if r["vibe"] == v][:2]
            best += vb
        lst = tmp / "reel.txt"
        parts = []
        for i, r in enumerate(best):
            p = tmp / f"reel_{i:02d}.mp4"
            subprocess.run([ff, "-v", "error", "-y", "-i", str(self.clips / r["clip"]), "-vf",
                            f"scale=768:432:flags=lanczos,fps=24,drawtext=fontfile='{font}':text='{label(r)}':"
                            "fontsize=16:fontcolor=white:box=1:boxcolor=black@0.5:x=10:y=10",
                            "-an", "-c:v", "libx264", "-crf", "22", "-pix_fmt", "yuv420p", str(p)], check=False)
            if p.exists():
                parts.append(p)
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        subprocess.run([ff, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        str(self.out / "best_of_reel.mp4")], check=False)
        self.log("final outputs written:", "leaderboard.csv recommended.json bad_pairs.json autotune.json",
                 "contact_best.jpg contact_worst.jpg best_of_reel.mp4")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="HH:MM local hard stop (next occurrence)")
    ap.add_argument("--minutes", type=float, help="run for N minutes (dry run)")
    ap.add_argument("--out", default=str(ROOT / "judge_logs" / "autotune" / "night"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--phase1-limit", type=int, default=None, help="cap coverage jobs (dry run)")
    o = ap.parse_args()
    out = Path(o.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    log = Log(out / "autotune.log")
    start = now()
    if o.minutes:
        deadline = start + dt.timedelta(minutes=o.minutes)
    else:
        hh, mm = (int(x) for x in (o.until or "06:30").split(":"))
        deadline = start.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if deadline <= start:
            deadline += dt.timedelta(days=1)
        if deadline - start > dt.timedelta(hours=9):
            log(f"refusing: deadline {deadline} is more than 9 h away"); return
    # finalising (sheet + reel) needs a couple of minutes before the hard stop
    loop_deadline = deadline - dt.timedelta(minutes=4 if not o.minutes else 1)
    try:  # keep the PC awake while running (ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)
    except Exception:
        pass
    if not ensure_services(log, allow_restart=True):
        log("ComfyUI/proxy unavailable at start; exiting"); return
    t = Tuner(out, loop_deadline, log, o.seed or int(start.timestamp()), o.phase1_limit)
    try:
        t.loop()
    finally:
        try:
            t.finalize()
        finally:
            t.scorer.close()
            try:
                urllib.request.urlopen(urllib.request.Request(COMFY + "/free", data=json.dumps(
                    {"unload_models": True, "free_memory": True}).encode(), method="POST",
                    headers={"Content-Type": "application/json"}), timeout=10)
            except Exception:
                pass
            log(f"autotune exit; {len(t.runs)} runs on file")


if __name__ == "__main__":
    main()
