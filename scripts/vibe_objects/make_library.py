"""Library strip for a vibe that ships its own stills: one checked orb -> nautilus LTX 0.9.5 morph
through workflows/xenoform_morph.json (comfy-sdk -> comfy-api-proxy :8189, the settings
morph_pass.tuned() gives the vibe), cut into wide / medium / close / reveal at 768x432 with a
jpg poster each, the way the 20 Oct 2026 batch (commit 9c50818) was made.

    make_library.py <work dir> vibe [vibe ...]

Writes <work>/<vibe>_morph.mp4 (the 512x288 render) and ui_static/library/<vibe>/{wide,medium,close,reveal}.{mp4,jpg}.
Prints one JSON line per vibe (render seconds, temporal QA) for the clip_pack entry. Existing library
clips are overwritten; existing morph renders in <work> are reused.
"""
import json, os, subprocess, sys, time
from pathlib import Path

os.environ["COMFY_BASE_URL"] = "http://127.0.0.1:8189"; os.environ.pop("COMFY_API_KEY", None)
os.environ.setdefault("XENO_QA_CLIP_OFF", "1")  # the desk venv has no torch; score.py (ComfyUI venv) does the CLIP part
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from comfy_sdk import Comfy, JobFailed  # noqa: E402
from xenoform import morph_pass as mp, shot_qa, vibes as _vibes  # noqa: E402

STATIC = ROOT / "src" / "xenoform" / "ui_static"
W, H, FPS, FRAMES = 768, 432, 24, 49
SEED = int(os.environ.get("XENO_LIB_SEED", "2727"))  # morph_pass's default seed; override to re-roll a strip
CUTS = {  # name -> (centre crop factor, reversed)
    "wide": (1.0, False), "medium": (1.15, False), "close": (1.5, False), "reveal": (1.0, True),
}


def render(client, vibe: str, dest: Path, a: Path, b: Path) -> float:
    wf = client.workflows.from_file(str(mp.GRAPH))
    wf.set_input("6", "image", client.assets.from_file(str(a)))
    wf.set_input("7", "image", client.assets.from_file(str(b)))
    wf.set_input("3", "text", mp.prompt_for(vibe))
    wf.set_input("4", "text", _vibes.negative(vibe) or mp.NEGATIVE)
    wf.set_input("9", "width", mp.WIDTH); wf.set_input("9", "height", mp.HEIGHT); wf.set_input("9", "length", FRAMES)
    tune = mp.tuned(vibe)
    wf.set_input("11", "steps", int(tune.get("steps", mp.STEPS)))
    if "cfg" in tune:
        wf.set_input("14", "cfg", float(tune["cfg"]))
    if "img_compression" in tune:
        wf.set_input("8", "img_compression", int(tune["img_compression"])); wf.set_input("21", "img_compression", int(tune["img_compression"]))
    if "guide_end_strength" in tune:
        wf.set_input("22", "strength", float(tune["guide_end_strength"]))
    wf.set_input("13", "noise_seed", SEED); wf.set_input("18", "fps", float(FPS))
    t0 = time.time()
    r = client.submit(wf).result()
    o = list(r.get_outputs("19")) or list(r.outputs)
    next((x for x in o if getattr(x, "type", None) == "video"), o[0]).to_file(str(dest))
    return round(time.time() - t0, 1)


def cut(src: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, (zoom, rev) in CUTS.items():
        vf = f"crop=iw/{zoom}:ih/{zoom},scale={W}:{H}:flags=lanczos,format=yuv420p" if zoom != 1.0 else f"scale={W}:{H}:flags=lanczos,format=yuv420p"
        if rev:
            vf += ",reverse"
        mp4 = out / f"{name}.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-an", "-r", str(FPS),
                        "-c:v", "libx264", "-crf", "22", "-preset", "slow", "-movflags", "+faststart", str(mp4)], check=True)
        # poster: the clean object the clip starts on (frame 0); the reveal poster is its last frame (the orb again)
        pick = f"select=eq(n\\,{FRAMES - 1})" if rev else "select=eq(n\\,0)"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", pick, "-frames:v", "1", "-q:v", "3", str(out / f"{name}.jpg")], check=True)


def main() -> None:
    work = Path(sys.argv[1]); work.mkdir(parents=True, exist_ok=True)
    client = Comfy(client_info="xenoform-library", timeout=None)
    for vibe in sys.argv[2:]:
        a, b = STATIC / "objects" / vibe / "00_orb.jpg", STATIC / "objects" / vibe / "01_nautilus.jpg"
        dest = work / f"{vibe}_morph.mp4"
        secs = render(client, vibe, dest, a, b) if not dest.exists() else 0.0
        good = f"a clean single sculptural object, {mp.VIBE_LOOK.get(vibe, '')}"
        qa = shot_qa.check(mp._read_frames(dest, 320, 180), good, "")
        cut(dest, STATIC / "library" / vibe)
        print(json.dumps({"vibe": vibe, "render_s": secs, "qa_ok": qa["ok"], "qa_score": qa["score"], "reasons": qa["reasons"],
                          "tune": mp.tuned(vibe)}), flush=True)


if __name__ == "__main__":
    main()
