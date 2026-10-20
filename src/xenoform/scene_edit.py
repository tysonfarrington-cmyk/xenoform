"""Scene edit: cut clips on the beat with transitions_fx boundaries, a bass pulse and small labels.

Spec (JSON): segments [{src, in, dur, speed, fit: pad|crop, pre, align: end}], transitions
[{kind, win, intensity, morph}] (one per boundary), labels [{t0, t1, title, note}], audio,
audio_in, analysis (xenoform analyse JSON with beats/env_t/env_bass), beat_snap {every, max_shift},
out. ``python -m xenoform.scene_edit spec.json``.
"""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from xenoform import transitions_fx as T

FONTS = ["/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf",
         "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def _font(size):
    from PIL import ImageFont
    for f in FONTS:
        if Path(f).is_file():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def snap_segments(segs, beats, every=1, max_shift=0.35):
    """Snap every segment boundary to the beat grid; returns new durations (in place)."""
    edges, t = [], 0.0
    for s in segs[:-1]:
        t += s["dur"]; edges.append(t)
    snapped = T.snap_to_beats(edges, beats, every=every, max_shift=max_shift)
    prev = 0.0
    total = sum(s["dur"] for s in segs)
    for s, e in zip(segs, snapped + [total]):
        s["dur"] = round(e - prev, 4); prev = e
    return segs

def probe_dur(p):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",p]).decode().strip() or 0)

def vf(seg, W, H, fps):
    sp = seg.get("speed", 1.0)
    fit = seg.get("fit", "pad")
    f = ([seg["pre"]] if seg.get("pre") else []) + [f"setpts=PTS/{sp}", f"fps={fps}"]
    if fit == "crop":
        f.append(f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}")
    else:
        sc = seg.get("scale", 1.0)
        f.append(f"scale={int(W*sc)}:{int(H*sc)}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black")
    f.append(f"tpad=stop_mode=clone:stop_duration=30,format=rgb24")
    return ",".join(f)

def reader(seg, t_src, nframes, W, H, fps):
    """yield nframes frames from seg source starting at source-time t_src (after speed)."""
    sp = seg.get("speed", 1.0)
    real_in = seg.get("in", 0.0) + max(0.0, t_src) * sp
    cmd = ["ffmpeg","-v","error","-ss",f"{real_in:.3f}","-i",seg["src"],"-vf",vf(seg,W,H,fps),
           "-frames:v",str(nframes),"-f","rawvideo","-pix_fmt","rgb24","-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    sz = W*H*3; last = None
    for _ in range(nframes):
        b = p.stdout.read(sz)
        if len(b) < sz:
            fr = last if last is not None else np.zeros((H,W,3),np.uint8)
        else:
            fr = np.frombuffer(b,np.uint8).reshape(H,W,3); last = fr
        yield fr
    p.stdout.close(); p.wait()

def label_img(title, note, W):
    from PIL import Image, ImageDraw
    ft, fn = _font(46), _font(30)
    for f, ax in ((ft, [32, 600]), (fn, [14, 350])):
        try: f.set_variation_by_axes(ax)
        except Exception: pass
    im = Image.new("RGBA",(W,230),(0,0,0,0)); d = ImageDraw.Draw(im)
    x = 72
    d.rectangle([x, 40, x+46, 43], fill=(210,225,255,230))
    d.text((x, 58), title.upper(), font=ft, fill=(255,255,255,240))
    # wrap note
    words, lines, cur = note.split(), [], ""
    for w in words:
        if d.textlength(cur+" "+w, font=fn) > W-2*x: lines.append(cur); cur = w
        else: cur = (cur+" "+w).strip()
    lines.append(cur)
    for k, ln in enumerate(lines[:2]):
        d.text((x, 122+k*40), ln, font=fn, fill=(220,225,235,205))
    return np.asarray(im).astype(np.float32)

def build(spec):
    W, H, fps = spec.get("W",1080), spec.get("H",1920), spec.get("fps",24)
    segs, trs = spec["segments"], spec["transitions"]
    if len(trs) != len(segs)-1:
        raise ValueError("need one transition per boundary (len(segments)-1)")
    if spec.get("beat_snap") and spec.get("analysis"):
        bs = spec["beat_snap"] if isinstance(spec["beat_snap"], dict) else {}
        beats = [b - spec.get("audio_in", 0.0) for b in json.load(open(spec["analysis"]))["beats"]]
        snap_segments(segs, beats, every=int(bs.get("every", 1)), max_shift=float(bs.get("max_shift", 0.35)))
    starts = [0.0]
    for s in segs: starts.append(starts[-1]+s["dur"])
    total = starts[-1]
    nT = int(round(total*fps))
    fr_of = lambda t: int(round(t*fps))
    # windows (frame ranges) per boundary
    win = []
    for j, tr in enumerate(trs):
        Tb = starts[j+1]; w = tr.get("win", 1.0)
        if tr["kind"] == "cut": a0 = a1 = Tb
        elif tr["kind"] == "black-hold": a0, a1 = Tb-w, Tb
        else: a0, a1 = Tb-w/2, Tb+w/2
        win.append((fr_of(a0), fr_of(a1)))
    # segment source origin: timeline time where source-time 0 sits
    origin = []
    for i, s in enumerate(segs):
        o = starts[i] - (starts[i]-win[i-1][0]/fps if i>0 else 0)  # default: source starts at prev window start
        if i>0 and trs[i-1]["kind"]=="scene-morph" and trs[i-1].get("morph"):
            o = win[i-1][1]/fps
        if s.get("align")=="end":  # source ends exactly where the body ends (scene-morph A side)
            end_body = win[i][0]/fps if i < len(trs) else starts[i+1]
            o = end_body - probe_dur(s["src"])/s.get("speed",1.0)
        origin.append(o)
    # precompute transition frames
    tframes = []
    for j, tr in enumerate(trs):
        f0, f1 = win[j]; n = f1-f0
        if n <= 0:
            tframes.append([]); continue
        A = list(reader(segs[j], f0/fps-origin[j], n, W, H, fps))
        B = list(reader(segs[j+1], f0/fps-origin[j+1], n, W, H, fps))
        mf = None
        if tr["kind"]=="scene-morph" and tr.get("morph"):
            d = probe_dur(tr["morph"]); m = int(d*fps)
            mf = list(reader({"src":tr["morph"]}, 0, m, W, H, fps))
        inten = tr.get("intensity", 0.6)
        tframes.append(T.apply(tr["kind"], A, B, inten, morph_frames=mf))
        print("transition", j, tr["kind"], n, flush=True)
    # envelopes
    ex = json.load(open(spec["analysis"])) if spec.get("analysis") else None
    a_in = spec.get("audio_in",0.0)
    if ex:
        et = np.array(ex["env_t"])-a_in; eb = np.array(ex["env_bass"]); er = np.array(ex["env_rms"])
        on = np.clip(np.concatenate([[0],np.diff(eb)])*8,0,1)
    stems = json.load(open(spec["stems"])) if spec.get("stems") else None
    labels = [(fr_of(l["t0"]),fr_of(l["t1"]),label_img(l["title"],l.get("note",""),W)) for l in spec.get("labels",[])]
    out = spec["out"]
    enc = subprocess.Popen(["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24","-s",f"{W}x{H}","-r",str(fps),"-i","-",
        "-ss",str(a_in),"-t",f"{total:.3f}","-i",spec["audio"],"-map","0:v","-map","1:a","-c:v","libx264","-preset","medium","-crf",str(spec.get("crf",18)),
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","256k","-af",f"afade=t=out:st={total-1.5:.2f}:d=1.5","-movflags","+faststart","-shortest",out], stdin=subprocess.PIPE)
    k = 0
    for i, s in enumerate(segs):
        b0 = win[i-1][1] if i>0 else 0
        b1 = win[i][0] if i < len(trs) else nT
        for fr in reader(s, b0/fps-origin[i], max(0,b1-b0), W, H, fps):
            emit(enc, fr, k, fps, spec, ex and (et,eb,on), labels, H, stems); k += 1
        if i < len(trs):
            for fr in tframes[i]:
                emit(enc, fr, k, fps, spec, ex and (et,eb,on), labels, H, stems); k += 1
    enc.stdin.close(); enc.wait()
    print("done", out, k/fps)

def emit(enc, fr, k, fps, spec, env, labels, H, stems=None):
    t = k/fps
    if stems is not None and spec.get("pulse", True):
        from xenoform import stem_react as SR
        fr = SR.apply_frame(fr, stems, t + spec.get("audio_in", 0.0) - spec.get("stems_offset", 0.0), depth=spec.get("pulse_depth", 0.03))
    elif env and spec.get("pulse", True):
        et, eb, on = env
        fr = T.bass_pulse(fr, float(np.interp(t, et, eb)), float(np.interp(t, et, on)), depth=spec.get("pulse_depth",0.03))
    for (l0,l1,img) in labels:
        if l0 <= k < l1:
            a = min(1,(k-l0)/(0.3*fps),(l1-k)/(0.3*fps))
            h = img.shape[0]; y = H-h-spec.get("label_bottom",170)
            reg = fr[y:y+h].astype(np.float32); al = img[...,3:4]/255*a
            fr = fr.copy(); fr[y:y+h] = (reg*(1-al)+img[...,:3]*al).astype(np.uint8)
    enc.stdin.write(np.ascontiguousarray(fr).tobytes())

if __name__ == "__main__":
    build(json.load(open(sys.argv[1])))
