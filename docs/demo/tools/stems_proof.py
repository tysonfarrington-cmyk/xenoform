"""The Stems mode proof (docs/MUSIC_VIDEO_PLAN.md section 7b, its acceptance; docs/STEMS_MODE.md) on the bundled Glitch Out.

    python stems_proof.py make <out dir> --desk http://127.0.0.1:47331 [--start 90] [--length 30]
           [--layers drums:objects:liquid-gold:0.8,other:objects:bioluminescent:0.6] [--again drums=0.35,other=1.0]
    python stems_proof.py sheets <job dir> <out dir> [--tag first]
    python stems_proof.py again <out dir> --desk ... --job <id> --again drums=0.35,other=1.0

``make``: loads the song on the desk, splits its stems there (POST /api/stems/split: on the CPU, no GPU, no queue) and
waits for them, waits for an idle ComfyUI queue (it never jumps the queue: GET /queue running and pending both empty)
and sends one local Draft Stems Make (never Final, never Cloud), waits for it, then makes the sheets, the copies and the
second composite (``again``) and writes proof.json. ``sheets``: from a finished Stems job, the moments sheet (each
layer alone and the composite at the moments that show the mode: both layers where their stems overlap, the drums alone
on a drop, the other alone in the breakdown), the composite every half second with both alphas, the alpha curves, and
the layers side by side with the song. ``again``: the same layers at another prominence, laid again on the desk with
no render (POST /api/jobs/<id>/composite), then laid back at the first prominence to check the record rebuilds the
first file byte for byte.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
COMFY = "http://127.0.0.1:8188"
MACROS = {"intensity": 0.5, "speed": 0.5, "chaos": 0.3, "glow": 0.4}
TYS_USAGE = Path(r"C:\Projects\xenoform-rc2\work\ui\objects\usage.json")  # read only: hashed before and after
FONT = r"C:\Windows\Fonts\segoeui.ttf"
FONT_B = r"C:\Windows\Fonts\segoeuib.ttf"
HUES = {"drums": (236, 92, 112), "other": (88, 196, 228), "bass": (236, 170, 70), "vocals": (176, 120, 236)}


def mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    try:
        return ImageFont.truetype(FONT_B if bold else FONT, size)
    except OSError:
        return ImageFont.load_default()


def _frame(video: Path, t: float, w: int, h: int):
    """One frame of ``video`` at ``t`` seconds, ``w`` x ``h``."""
    from PIL import Image

    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    if not raw:
        return Image.new("RGB", (w, h), (40, 0, 0))
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _load(job: Path) -> dict:
    from xenoform import stems_composite as SC

    rec = json.loads((job / "simple" / "simple.json").read_text(encoding="utf-8"))
    comp = rec["composite"]
    curves = SC.read_curves(job)
    layers = [{**l, "prominence": comp["prominence"].get(l["stem"], l.get("prominence")),
               "blend": comp["blends"].get(l["stem"], l.get("blend"))} for l in rec["layers"]]
    frames = int(comp["frames"])
    alphas = SC.alphas(layers, curves["activity"], frames, solo=bool(comp.get("solo", True)))
    acts = {k: SC.fit(v, frames) for k, v in curves["activity"].items()}
    first = json.loads(Path(layers[0]["record"]).read_text(encoding="utf-8"))
    shots = {l["stem"]: json.loads(Path(l["record"]).read_text(encoding="utf-8")).get("shots") or [] for l in layers}
    return {"rec": rec, "comp": comp, "layers": layers, "alphas": alphas, "acts": acts, "fps": int(comp["fps"]),
            "frames": frames, "start": float((rec.get("window") or {}).get("song_start") or 0.0), "shots": shots,
            "first": first}


def _role_at(shots: list[dict], t: float) -> str:
    for s in shots:
        if float(s["start"]) - 1e-6 <= t < float(s["end"]):
            return str(s.get("section") or "")
    return ""


def moments(d: dict, n_overlap: int = 3, n_drums: int = 2, n_other: int = 3) -> list[tuple[float, str]]:
    """The times that show the mode: both layers where both stems play, the drums alone (a drop's first beat when it
    has one), the other alone (the breakdown); spread, at least 1.5 s apart, in time order."""
    fps, n = d["fps"], d["frames"]
    stems = [l["stem"] for l in d["layers"]]
    if len(stems) < 2:
        return [(t, "") for t in (2.0, 10.0, 20.0)]
    a, b = d["alphas"][stems[0]], d["alphas"][stems[1]]
    cand = {"both": [], stems[0]: [], stems[1]: []}
    for k in range(int(fps * 0.5), n - int(fps * 0.5), max(1, fps // 4)):
        if a[k] >= 0.35 and b[k] >= 0.35:
            cand["both"].append(k / fps)
        elif a[k] >= 0.8 and b[k] < 0.08:
            cand[stems[0]].append(k / fps)
        elif b[k] >= 0.8 and a[k] < 0.08:
            cand[stems[1]].append(k / fps)
    drops = [float(s["start"]) + 0.6 for s in d["shots"].get(stems[0], []) if s.get("event") == "drop"]

    def spread(ts: list[float], k: int, prefer: list[float] | None = None) -> list[float]:
        out: list[float] = []
        for p in prefer or []:
            near = [t for t in ts if abs(t - p) < 0.8]
            if near and len(out) < k:
                out.append(min(near, key=lambda t: abs(t - p)))
        if ts:
            for q in range(k):
                t = ts[int(round(q * (len(ts) - 1) / max(1, k - 1)))]
                if len(out) < k and all(abs(t - o) >= 1.5 for o in out):
                    out.append(t)
        return out

    picks = [(t, "both play") for t in spread(cand["both"], n_overlap)]
    picks += [(t, f"{stems[0]} alone") for t in spread(cand[stems[0]], n_drums, drops)]
    picks += [(t, f"{stems[1]} alone") for t in spread(cand[stems[1]], n_other)]
    picks.sort()
    kept: list[tuple[float, str]] = []
    for t, why in picks:
        if all(abs(t - u) >= 1.5 for u, _ in kept):
            kept.append((t, why))
    return kept


def moments_sheet(d: dict, job: Path, dest: Path, title: str, picks: list[tuple[float, str]] | None = None) -> list[dict]:
    from PIL import Image, ImageDraw

    stems = [l["stem"] for l in d["layers"]]
    picks = picks or moments(d)
    tw, th, label_w, head_h, cap_h = 216, 384, 190, 92, 76
    rows = [(f"{l['stem']} layer", Path(l["video"]), l) for l in d["layers"]] + [("composite", job / "xenoform.mp4", None)]
    W = label_w + tw * len(picks) + 8 * len(picks) + 8
    H = head_h + (cap_h + 6) + (th + 8) * len(rows) + 10
    sheet = Image.new("RGB", (W, H), (12, 12, 16))
    dr = ImageDraw.Draw(sheet)
    dr.text((14, 10), title, font=_font(22, True), fill=(240, 240, 240))
    sub = "Each column is one moment of the cut (song time). Rows: each layer's own cut, then the composite Tys watches. " \
          "Under the time: the passage and each layer's alpha (prominence x its stem's activity; a layer playing alone is opaque)."
    dr.text((14, 44), sub, font=_font(15), fill=(185, 185, 195))
    out = []
    for c, (t, why) in enumerate(picks):
        x = label_w + 8 + c * (tw + 8)
        k = min(d["frames"] - 1, int(round(t * d["fps"])))
        song_t = d["start"] + t
        role = _role_at(d["shots"].get(stems[0], []), t)
        dr.text((x, head_h - 4), f"{mmss(song_t)}  ·  {why}", font=_font(16, True), fill=(250, 220, 120))
        dr.text((x, head_h + 20), f"passage: {role.replace('_', ' ') or '-'}", font=_font(13), fill=(200, 200, 210))
        line = "   ".join(f"{s} {float(d['alphas'][s][k]):.2f}" for s in stems)
        dr.text((x, head_h + 40), f"alpha  {line}", font=_font(13), fill=(200, 200, 210))
        for r, (name, video, layer) in enumerate(rows):
            y = head_h + cap_h + 6 + r * (th + 8)
            im = _frame(video, t, tw, th)
            sheet.paste(im, (x, y))
            if layer is not None:
                a = float(d["alphas"][layer["stem"]][k])
                col = HUES.get(layer["stem"], (200, 200, 200))
                dr.rectangle([x, y + th - 8, x + int(tw * a), y + th], fill=col)
        out.append({"t": round(t, 3), "song_t": mmss(song_t), "why": why, "role": role,
                    "alpha": {s: round(float(d["alphas"][s][k]), 3) for s in stems},
                    "activity": {s: round(float(d["acts"][s][k]), 3) for s in stems}})
    for r, (name, video, layer) in enumerate(rows):
        y = head_h + cap_h + 6 + r * (th + 8)
        dr.text((14, y + 8), name, font=_font(18, True), fill=(240, 240, 240))
        if layer is not None:
            what = f"{layer['kind']}: {layer.get('vibe') or ''}" if layer["kind"] == "objects" else "your clips"
            dr.text((14, y + 36), what, font=_font(14), fill=(190, 190, 200))
            dr.text((14, y + 58), f"prominence {float(layer['prominence']):.2f}", font=_font(14), fill=(190, 190, 200))
            dr.text((14, y + 80), f"blend {layer['blend']}", font=_font(14), fill=(190, 190, 200))
            dr.text((14, y + 102), "bar: its alpha", font=_font(13), fill=HUES.get(layer["stem"], (200, 200, 200)))
        else:
            order = " under ".join(reversed(d["comp"]["order"]))
            dr.text((14, y + 36), f"{order}", font=_font(14), fill=(190, 190, 200))
            dr.text((14, y + 58), "over black", font=_font(14), fill=(190, 190, 200))
    sheet.save(dest, quality=90)
    return out


def composite_sheet(d: dict, video: Path, dest: Path, title: str, step: float = 0.5, cols: int = 12) -> None:
    from PIL import Image, ImageDraw

    stems = [l["stem"] for l in d["layers"]]
    n = int(d["frames"] / d["fps"] / step)
    tw, th, cap = 135, 240, 46
    rows = (n + cols - 1) // cols
    W, H = cols * (tw + 6) + 6, 70 + rows * (th + cap + 8)
    sheet = Image.new("RGB", (W, H), (12, 12, 16))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 8), title, font=_font(20, True), fill=(240, 240, 240))
    dr.text((8, 38), "The composite every half second. Under each frame: song time, passage, and each layer's alpha as a bar "
                     + "  ".join(f"({s})" for s in stems) + ".", font=_font(14), fill=(185, 185, 195))
    for i in range(n):
        t = (i + 0.5) * step
        k = min(d["frames"] - 1, int(round(t * d["fps"])))
        x = 6 + (i % cols) * (tw + 6)
        y = 70 + (i // cols) * (th + cap + 8)
        sheet.paste(_frame(video, t, tw, th), (x, y))
        role = _role_at(d["shots"].get(stems[0], []), t)
        dr.text((x + 2, y + th + 2), f"{mmss(d['start'] + t)} {role.replace('_', ' ')}", font=_font(12, True), fill=(250, 220, 120))
        for j, s in enumerate(stems):
            a = float(d["alphas"][s][k])
            yy = y + th + 22 + j * 9
            dr.rectangle([x, yy, x + tw, yy + 6], fill=(40, 40, 48))
            dr.rectangle([x, yy, x + int(tw * a), yy + 6], fill=HUES.get(s, (200, 200, 200)))
    sheet.save(dest, quality=90)


def alpha_chart(d: dict, dest: Path, title: str) -> None:
    from PIL import Image, ImageDraw

    W, H, pad, top = 1500, 380, 60, 60
    im = Image.new("RGB", (W, H), (14, 14, 18))
    dr = ImageDraw.Draw(im)
    dr.text((pad, 14), title, font=_font(20, True), fill=(240, 240, 240))
    dur = d["frames"] / d["fps"]
    x_of = lambda t: pad + (W - 2 * pad) * t / dur  # noqa: E731
    y_of = lambda v: H - 50 - (H - top - 70) * v  # noqa: E731
    stems = [l["stem"] for l in d["layers"]]
    last = None
    for s in d["shots"].get(stems[0], []):
        role = str(s.get("section") or "")
        if role != last:
            dr.line([x_of(float(s["start"])), top, x_of(float(s["start"])), H - 50], fill=(60, 60, 70))
            dr.text((x_of(float(s["start"])) + 3, top), role.replace("_", " "), font=_font(12), fill=(170, 170, 180))
            last = role
    for s in stems:
        col = HUES.get(s, (200, 200, 200))
        act = d["acts"][s]
        pts = [(x_of(k / d["fps"]), y_of(float(act[k]))) for k in range(0, d["frames"], 2)]
        dr.line(pts, fill=tuple(int(c * 0.55) for c in col), width=1)
        al = d["alphas"][s]
        pts = [(x_of(k / d["fps"]), y_of(float(al[k]))) for k in range(0, d["frames"], 2)]
        dr.line(pts, fill=col, width=3)
    for i in range(0, int(dur) + 1, 2):
        dr.text((x_of(i) - 14, H - 40), mmss(d["start"] + i), font=_font(12), fill=(170, 170, 180))
    legend = "   ".join(f"{s}: thick = alpha, thin = activity" for s in stems)
    dr.text((pad, H - 22), legend, font=_font(13), fill=(200, 200, 210))
    im.save(dest)


def side_by_side(d: dict, job: Path, dest: Path) -> None:
    """Each layer alone and the composite, 360x640 each, named, with the composite's sound (the song once)."""
    font = "C\\:/Windows/Fonts/segoeuib.ttf"
    inputs = [Path(l["video"]) for l in d["layers"]] + [job / "xenoform.mp4"]
    labels = [f"{l['stem']} layer" for l in d["layers"]] + ["composite"]
    ins, parts = [], []
    for k, (p, label) in enumerate(zip(inputs, labels)):
        ins += ["-i", str(p)]
        parts.append(f"[{k}:v]scale=360:640,setsar=1,drawtext=fontfile='{font}':text='{label}':x=10:y=10:fontsize=24:"
                     f"fontcolor=white:box=1:boxcolor=black@0.6[v{k}]")
    graph = ";".join(parts) + ";" + "".join(f"[v{k}]" for k in range(len(inputs))) + f"hstack=inputs={len(inputs)}[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", graph, "-map", "[v]", "-map", f"{len(inputs) - 1}:a",
                    "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(dest)], check=True)


def sheets(job: Path, out: Path, *, tag: str = "", title: str = "", picks: list[tuple[float, str]] | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    d = _load(job)
    stems = [l["stem"] for l in d["layers"]]
    what = ", ".join(f"{l['stem']} = {l['kind'] if l['kind'] == 'clips' else (l.get('vibe') or '') + ' objects'} "
                     f"({float(l['prominence']):.2f}, {l['blend']})" for l in d["layers"])
    head = title or f"Stems mode · Glitch Out {mmss(d['start'])} to {mmss(d['start'] + d['frames'] / d['fps'])} · Draft · {what}"
    sfx = f"_{tag}" if tag else ""
    info = {"moments": moments_sheet(d, job, out / f"stems_moments_sheet{sfx}.jpg", head, picks)}
    composite_sheet(d, job / "xenoform.mp4", out / f"stems_composite_sheet{sfx}.jpg", head)
    alpha_chart(d, out / f"stems_alpha_curves{sfx}.png", head)
    if not tag:
        side_by_side(d, job, out / "stems_layers_side_by_side.mp4")
    info["layers"] = [{k: l.get(k) for k in ("stem", "kind", "vibe", "prominence", "blend", "lead", "shots", "morphs",
                                               "silent_s", "drops_kept", "stills", "engine", "guardrails", "plan_line")}
                      for l in d["layers"]]
    info["order"] = d["comp"]["order"]
    info["alpha_mean"] = {s: round(float(d["alphas"][s].mean()), 3) for s in stems}
    info["seconds_alone"] = {s: round(float(((d["alphas"][s] >= 0.8) & (d["alphas"][[x for x in stems if x != s][0]] < 0.08)).sum()) / d["fps"], 2)
                             for s in stems} if len(stems) == 2 else {}
    info["seconds_both"] = round(float(((d["alphas"][stems[0]] >= 0.35) & (d["alphas"][stems[-1]] >= 0.35)).sum()) / d["fps"], 2)
    return info


# ------------------------------------------------------------------------------------------------ the desk


def _get(url: str, **kw):
    import requests

    return requests.get(url, timeout=kw.pop("timeout", 60), **kw)


def _post(url: str, body: dict, timeout: float = 300):
    import requests

    return requests.post(url, json=body, timeout=timeout)


def queue_idle() -> bool:
    try:
        q = _get(f"{COMFY}/queue", timeout=10).json()
    except Exception:
        return False
    return not q.get("queue_running") and not q.get("queue_pending")


def wait_job(desk: str, job: str, log) -> dict:
    last = ""
    while True:
        time.sleep(5)
        try:
            j = _get(f"{desk}/api/jobs/{job}").json()
        except Exception as exc:
            log(f"  poll: {exc}")
            continue
        line = f"  {j.get('stage')} {round(float(j.get('progress') or 0) * 100)}% {j.get('detail')}"
        if line != last:
            log(line)
            last = line
        if j.get("status") in ("done", "error", "cancelled"):
            return j


def layers_arg(text: str, vibe: str) -> list[dict]:
    out = []
    for part in text.split(","):
        stem, kind, what, pro = (part.split(":") + ["", "", "", ""])[:4]
        layer = {"stem": stem, "kind": kind or "objects", "prominence": float(pro or 0.7), "blend": "screen"}
        if layer["kind"] == "clips":
            layer["clips_folder"] = what
        else:
            layer["vibe"] = what or vibe
        out.append(layer)
    return out


def pro_arg(text: str) -> dict:
    return {k: float(v) for k, v in (p.split("=") for p in text.split(",") if "=" in p)}


def again(out: Path, desk: str, job: str, prominence: dict, first_sha: str, log, picks=None) -> dict:
    """The same layers at another prominence, laid on the desk with no render, then back at the first (``picks``: the
    first sheet's moments, so the two sheets show the same frames)."""
    job_dir = ROOT / "work" / "ui" / "jobs" / job
    rec = json.loads((job_dir / "simple" / "simple.json").read_text(encoding="utf-8"))
    was = dict(rec["composite"]["prominence"])
    t0 = time.perf_counter()
    r = _post(f"{desk}/api/jobs/{job}/composite", {"prominence": prominence})
    if r.status_code != 200:
        raise SystemExit(f"composite refused: {r.status_code} {r.text[:300]}")
    j = wait_job(desk, job, log)
    took = round(time.perf_counter() - t0, 1)
    name = "glitch_out_stems_" + "_".join(f"{k}{int(round(v * 100)):03d}" for k, v in prominence.items()) + ".mp4"
    shutil.copy2(job_dir / "xenoform.mp4", out / name)
    second = sheets(job_dir, out, tag="again", picks=picks)
    second_sha = sha256(out / name)
    r = _post(f"{desk}/api/jobs/{job}/composite", {"prominence": was})
    j2 = wait_job(desk, job, log)
    back_sha = sha256(job_dir / "xenoform.mp4")
    return {"file": name, "prominence": prominence, "seconds": took, "status": j.get("status"), "detail": j.get("detail"),
            "sha256": second_sha, "back_to": was, "back_sha256": back_sha, "byte_for_byte": back_sha == first_sha,
            "back_detail": j2.get("detail"), "sheet": second}


def make(out: Path, *, desk: str, start: float, length: float, layers: list[dict], vibe: str, wait_s: float,
         again_pro: dict, seed: int = 2727) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    logf = open(out / "proof_log.txt", "a", encoding="utf-8")

    def log(msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        logf.write(line + "\n")
        logf.flush()

    usage_before = sha256(TYS_USAGE) if TYS_USAGE.is_file() else None
    r = _post(f"{desk}/api/songs/load", {"id": "glitch-out"})
    audio_id = r.json().get("audio_id")
    log(f"song loaded: {audio_id}")
    t0 = time.perf_counter()
    st = _post(f"{desk}/api/stems/split", {"audio_id": audio_id}).json()
    while st.get("status") in ("queued", "running"):
        time.sleep(3)
        st = _get(f"{desk}/api/stems/status", params={"audio_id": audio_id}).json()
    split = {"status": st.get("status"), "engine": st.get("engine"), "seconds": st.get("seconds"),
             "waited_s": round(time.perf_counter() - t0, 1), "stems": [{k: r.get(k) for k in ("name", "role", "active", "onsets")}
                                                                        for r in st.get("stems") or []]}
    log(f"stems: {split}")
    if st.get("status") != "done":
        raise SystemExit(f"the split did not finish: {st}")
    waited = 0.0
    while not queue_idle():
        if waited >= wait_s:
            raise SystemExit(f"the ComfyUI queue was busy for {int(waited)} s: make the sheet from the plan instead")
        log("  the ComfyUI queue is busy: waiting")
        time.sleep(30)
        waited += 30
    body = {"audio_id": audio_id, "live": True, "mode": "stems", "song": "Glitch Out", "vibe": vibe, "idea": "",
            "quality": "turbo", "quality_tier": "draft", "aspect": "9:16", "length_s": length, "length_start": start,
            "energy_preset": "dense", "morph_source": "objects", "morph_count": "auto", "morph_style": "auto",
            "morph_timing": "smooth", "effects": [], "beat_fx": True, "dance_fx": "auto", "foreshadow": "auto",
            "scene_stills": "off", "scenes_chosen": True, "backdrop": "plain", "macros": dict(MACROS), "end_card": False,
            "open_weights_only": True, "paid_cloud": False, "vertical_mode": "auto", "stem_orbit": True, "seed": int(seed),
            "chain_pins": {}, "breathe": False, "drop_mode": "auto", "auto_grow": False, "layers": layers}
    log(f"queue idle after {int(waited)} s: Make {json.dumps(layers)}")
    t1 = time.perf_counter()
    r = _post(f"{desk}/api/generate", body, timeout=300)
    if r.status_code != 200:
        raise SystemExit(f"the Make was refused: {r.status_code} {r.text[:400]}")
    job = r.json()["id"]
    guard = [m for m in (r.json().get("guardrails") or {}).get("messages") or [] if m.startswith("[stems]")]
    log(f"job {job}; {guard}")
    j = wait_job(desk, job, log)
    made_s = round(time.perf_counter() - t1, 1)
    log(f"job {job} {j.get('status')} in {made_s} s: {j.get('detail')}")
    if j.get("status") != "done":
        raise SystemExit(f"the Make did not finish: {j.get('error') or j.get('detail')}")
    job_dir = ROOT / "work" / "ui" / "jobs" / job
    first = out / f"glitch_out_stems_{int(start // 60)}m{int(start % 60):02d}_draft.mp4"
    shutil.copy2(job_dir / "xenoform.mp4", first)
    for l in json.loads((job_dir / "simple" / "simple.json").read_text(encoding="utf-8"))["layers"]:
        shutil.copy2(l["video"], out / f"layer_{l['stem']}_alone.mp4")
    info = sheets(job_dir, out)
    first_sha = sha256(first)
    # the record's own hash of the file it laid (the desk's QA pass may re-time a cut after it; the rebuild is checked
    # against what the record made)
    rec_sha = json.loads((job_dir / "simple" / "simple.json").read_text(encoding="utf-8"))["composite"]["sha256"]
    log(f"first composite {first_sha[:12]}, the record's {rec_sha[:12]}{'' if first_sha == rec_sha else ' (QA re-timed the published file)'}")
    picks = [(m["t"], m["why"]) for m in info["moments"]]
    more = again(out, desk, job, again_pro, rec_sha, log, picks) if again_pro else None
    usage_after = sha256(TYS_USAGE) if TYS_USAGE.is_file() else None
    proof = {"job": job, "job_dir": str(job_dir), "made_s": made_s, "split": split, "queue_wait_s": waited,
             "guardrails": guard, "first": {"file": first.name, "sha256": first_sha, "record_sha256": rec_sha},
             "sheets": info, "again": more,
             "tys_usage": {"path": str(TYS_USAGE), "before": usage_before, "after": usage_after,
                           "unchanged": usage_before == usage_after},
             "record": json.loads((job_dir / "simple" / "simple.json").read_text(encoding="utf-8"))}
    (out / "proof.json").write_text(json.dumps(proof, indent=1, default=str), encoding="utf-8")
    log(f"done: {out}")
    return proof


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("out")
    m.add_argument("--desk", default="http://127.0.0.1:47331")
    m.add_argument("--start", type=float, default=90.0)
    m.add_argument("--length", type=float, default=30.0)
    m.add_argument("--vibe", default="liquid-gold")
    m.add_argument("--layers", default="drums:objects:liquid-gold:0.8,other:objects:bioluminescent:0.6")
    m.add_argument("--layers-json", default="", help="the layers as a JSON list (pins and all), in place of --layers")
    m.add_argument("--seed", type=int, default=2727)
    m.add_argument("--again", default="drums=0.35,other=1.0")
    m.add_argument("--wait", type=float, default=2400.0)
    s = sub.add_parser("sheets")
    s.add_argument("job")
    s.add_argument("out")
    s.add_argument("--tag", default="")
    g = sub.add_parser("again")
    g.add_argument("out")
    g.add_argument("--desk", default="http://127.0.0.1:47331")
    g.add_argument("--job", required=True)
    g.add_argument("--again", default="drums=0.35,other=1.0")
    a = ap.parse_args()
    if a.cmd == "make":
        layers = json.loads(Path(a.layers_json).read_text(encoding="utf-8")) if a.layers_json else layers_arg(a.layers, a.vibe)
        make(Path(a.out), desk=a.desk, start=a.start, length=a.length, layers=layers, vibe=a.vibe,
             wait_s=a.wait, again_pro=pro_arg(a.again), seed=a.seed)
    elif a.cmd == "sheets":
        print(json.dumps(sheets(Path(a.job), Path(a.out), tag=a.tag), indent=1, default=str))
    else:
        out = Path(a.out)
        job_dir = ROOT / "work" / "ui" / "jobs" / a.job
        first = json.loads((job_dir / "simple" / "simple.json").read_text(encoding="utf-8"))["composite"]["sha256"]
        print(json.dumps(again(out, a.desk, a.job, pro_arg(a.again), first, print), indent=1, default=str))


if __name__ == "__main__":
    main()
