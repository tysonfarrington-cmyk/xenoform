"""Clips cuts on Glitch Out from the free film pack's most striking windows, through desk 47326 as real Makes (Morph =
Your clips, a folder of chosen pack clips in the order they play), one after another: the montage's film stretch and
the demo's clips scene, each a window of the song so its picture reacts to the seconds it is laid over (Tys, 29 Oct:
"we have a lot of cool footage to use from the clips and i feel like you chose some kind of boring ones").

    python clips_glitch.py <tier final|fast> [label ...]
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

DESK = "http://127.0.0.1:47326"
HERE = Path(__file__).parent
OUT = HERE / "montage"
SONG = Path(r"C:\Projects\xenoform-rc2\examples\songs\glitch_out.mp3")
PACK = Path(r"C:\Projects\xenoform-rc2\work\ui\film_pack")
OWN = Path(r"C:\Projects\xenoform-rc2\work\ui\own")
CUTS = [
    {"label": "clips_montage", "start": 124.0, "length": 20, "clips": [
        "13_metropolis_moloch", "02_trip_moon_face", "15_phantom_unmask", "12_atomic_blast", "10_design_dreaming_dance",
        "06_apollo11_launch", "18_metropolis_face", "14_haxan_sabbath"]},
    {"label": "clips_demo", "start": 50.0, "length": 20, "clips": [
        "01_metropolis_robot", "02_trip_moon_face", "11_lost_world_fight", "05_potemkin_steps", "19_general_bridge",
        "04_steamboat_whistle", "06_apollo11_launch", "16_chien_andalou_pianos"]},
]


def folder_for(cut):
    """A folder of copies in play order (01_, 02_ ...) with the pack's labels beside them."""
    d = OWN / f"glitch_{cut['label']}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    names = json.loads((PACK / "labels.json").read_text(encoding="utf-8"))
    labels = {}
    for k, stem in enumerate(cut["clips"], 1):
        new = f"{k:02d}_{stem.split('_', 1)[1]}.mp4"
        shutil.copy2(PACK / f"{stem}.mp4", d / new)
        labels[new] = names.get(f"{stem}.mp4", stem.split("_", 1)[1].replace("_", " "))
    (d / "labels.json").write_text(json.dumps(labels, indent=1), encoding="utf-8")
    if (PACK / "CREDITS.md").exists():
        shutil.copy2(PACK / "CREDITS.md", d / "CREDITS.md")
    return d


def main():
    tier = sys.argv[1]
    only = set(sys.argv[2:])
    OUT.mkdir(exist_ok=True)
    log_path = OUT / "clips_glitch.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    with open(SONG, "rb") as fh:
        a = requests.post(f"{DESK}/api/analyze", files={"file": (SONG.name, fh, "audio/mpeg")}, timeout=900).json()
    audio_id = a.get("audio_id")
    if not audio_id:
        raise SystemExit(f"no audio id: {str(a)[:300]}")
    print("song", audio_id, flush=True)
    for cut in CUTS:
        if only and cut["label"] not in only:
            continue
        folder = folder_for(cut)
        t0 = time.perf_counter()
        body = {"audio_id": audio_id, "quality": "turbo", "live": True, "mode": "simple", "song": "Glitch Out", "vibe": "none",
                "idea": "", "quality_tier": tier, "cloud_final_ok": False, "aspect": "16:9", "length_s": cut["length"],
                "length_start": cut["start"], "energy_preset": "dense", "morph_source": "clips", "own_folder": str(folder),
                "morph_count": "auto", "morph_style": "auto", "morph_timing": "beat", "beat_fx": True, "dance_fx": "auto",
                "foreshadow": "auto", "scene_stills": "off", "end_card": False, "open_weights_only": True, "paid_cloud": False,
                "vertical_mode": "auto", "stem_orbit": True,
                "macros": {"intensity": 0.9, "speed": 0.8, "chaos": 0.6, "glow": 0.7, "drums": 0.9, "bass": 0.9, "vocals": 0.5, "other": 0.6}}
        r = requests.post(f"{DESK}/api/generate", json=body, timeout=180)
        if r.status_code != 200:
            print(cut["label"], "refused", r.status_code, r.text[:300], flush=True)
            continue
        job = r.json()["id"]
        print(cut["label"], "job", job, flush=True)
        last = ""
        while True:
            time.sleep(15)
            try:
                j = requests.get(f"{DESK}/api/jobs/{job}", timeout=60).json()
            except Exception as exc:
                print("  poll:", exc, flush=True)
                continue
            line = f"  {j.get('stage')} {round(float(j.get('progress') or 0) * 100)}% {j.get('detail')}"
            if line != last:
                print(line, flush=True)
                last = line
            if j.get("status") in ("done", "error", "cancelled"):
                break
        took = round(time.perf_counter() - t0, 1)
        log.append({"label": cut["label"], "tier": tier, "job": job, "status": j.get("status"), "seconds": took,
                    "window": cut["start"], "clips": cut["clips"], "error": j.get("error")})
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(cut["label"], j.get("status"), "in", took, "s", flush=True)
        mp4 = Path(r"C:\Projects\xenoform-rc2\work\ui\jobs") / job / "xenoform.mp4"
        if j.get("status") == "done" and mp4.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", f"fps=24/{cut['length']},scale=320:180,tile=8x3",
                            "-frames:v", "1", str(OUT / f"sheet_{cut['label']}_{tier}.jpg")], check=False)
    print("done", flush=True)


main()
