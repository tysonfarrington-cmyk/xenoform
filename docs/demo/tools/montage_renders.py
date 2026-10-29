"""The montage's shots: Cloud Final cuts (LTX-2.5 on Comfy Cloud) on Glitch Out, made through a desk like any Make
(Tys, 29 Oct: "use the best quality we can", "push it to the limit max it out"). One after another, so a cut has Comfy
Cloud's three lanes to itself. Each cut is a 30 s window of the song (length_start), so its picture reacts to the
same seconds of the song the montage lays it over. Writes montage/renders.json (job ids, windows, times) and a
16-frame sheet a cut.

    python montage_renders.py <aspect 16:9|9:16> [label ...]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

DESK = "http://127.0.0.1:47325"  # the desk with the Comfy Cloud key in its environment (47326 has none)
HERE = Path(__file__).parent
OUT = HERE / "montage"
JOBS = Path(r"C:\Projects\xenoform-rc2\work\ui\jobs")
SONG = Path(r"C:\Projects\xenoform-rc2\examples\songs\glitch_out.mp3")

# Glitch Out's windows (seconds into the song; the desk snaps each start back to a beat). The montage runs over
# about 114.6 to 176 s: the release, the drop at 119.8, the release, the drop at 132.9, the build, the long drop
# from 141.0, the build at 170.3, the drop at 171.7 and the calm from 174.2.
W1, W2, W3, W4, W5 = 111.9, 125.0, 138.6, 147.0, 158.0
W6, W7, W8 = 178.5, 196.5, 208.8  # the second long drop (182), the drop at 210, the ending (232 to 238.8)
W3B, W5B = 149.5, 170.0  # the long drop's back half and the calm at 174 (round 3)
WB = 21.0  # the demo body's result, styles and effects scenes sit over about 25 to 41 s of the song
MAX = {"intensity": 1.0, "speed": 0.9, "chaos": 0.9, "glow": 0.85, "drums": 0.9, "bass": 0.9, "vocals": 0.5, "other": 0.7}
WILD = {**MAX, "chaos": 1.0, "glow": 1.0, "speed": 1.0}
CUTS = [
    {"label": "neon_shatter_snap", "vibe": "neon-noir", "start": W1, "style": "shatter", "timing": "snap",
     "effects": ["dither", "feedback"], "look": "cyan-flash", "foreshadow": "trace", "macros": WILD},
    {"label": "cyber_fold_beat", "vibe": "cyberspace-95", "start": W1, "style": "fold", "timing": "beat",
     "effects": ["slitscan"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "chrome_spin_snap", "vibe": "chrome-mercury", "start": W2, "style": "spin", "timing": "snap",
     "effects": ["kaleido", "feedback"], "look": "negative-rush", "foreshadow": "negative", "macros": WILD},
    {"label": "paint_melt_beat", "vibe": "wet-paint", "start": W2, "style": "melt", "timing": "beat",
     "effects": ["smear", "slitscan"], "look": "warm-leak", "foreshadow": "auto", "macros": MAX},
    {"label": "gold_bloom_smooth", "vibe": "liquid-gold", "start": W3, "style": "bloom", "timing": "smooth",
     "effects": ["feedback"], "look": "bloom-rush", "foreshadow": "silhouette", "scenes": "mix", "macros": MAX},
    {"label": "shadow_shatter_snap", "vibe": "shadow-self", "start": W3, "style": "shatter", "timing": "snap",
     "effects": ["dither", "smear"], "look": "noir-glow", "foreshadow": "trace", "macros": WILD},
    {"label": "deepsea_bloom_beat", "vibe": "bioluminescent", "start": W4, "style": "bloom", "timing": "beat",
     "idea": "underwater", "effects": ["kaleido"], "look": "cool-echo", "foreshadow": "trace", "macros": MAX},
    {"label": "none_auto_snap", "vibe": "none", "start": W4, "style": "auto", "timing": "snap",
     "effects": ["feedback", "smear"], "look": "auto", "foreshadow": "negative", "macros": WILD},
    {"label": "glass_melt_smooth", "vibe": "iridescent-glass", "start": W1, "style": "melt", "timing": "smooth",
     "effects": ["kaleido"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "botanical_scenes_bloom", "vibe": "botanical", "start": W3, "style": "bloom", "timing": "beat",
     "effects": ["slitscan", "feedback"], "look": "bloom-rush", "foreshadow": "silhouette", "scenes": "mix", "macros": MAX},
    # the ending: the title lands at 174.3 on the calm and sits over this cut (W4 stops at 177)
    {"label": "gold_end_melt", "vibe": "liquid-gold", "start": W5, "style": "melt", "timing": "smooth",
     "effects": ["feedback"], "look": "bloom-rush", "foreshadow": "auto", "macros": MAX},
    # round 2 (Tys, 29 Oct 5:20 pm, on the first montage: wet paint's colours "pretty terrible", the jug at 0:06 and the
    # guitar "too plain and boring", "overdoing it with the kaleidoscope ... demonstrate the morphs a bit more, and have
    # better more interesting and unique objects", "bump the time up to 2 mins"): themes for the objects, the morph
    # styles plain to see (feedback, dither, slit-scan, smear; kaleido left to the deep-sea fish), and the song's back
    # half (W6 the second long drop, W7 the drop after it, W8 the ending)
    {"label": "origami_fold_smooth", "vibe": "origami-noir", "start": W1, "style": "fold", "timing": "smooth",
     "effects": [], "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "lava_dinos_shatter", "vibe": "lava-obsidian", "idea": "dinosaurs", "start": W1, "style": "shatter", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "trace", "macros": WILD},
    {"label": "deepsea_fish_open", "vibe": "bioluminescent", "idea": "underwater", "start": W1, "style": "bloom", "timing": "beat",
     "effects": ["kaleido", "feedback"], "look": "cool-echo", "foreshadow": "trace", "macros": MAX},
    {"label": "neon_robots_shatter", "vibe": "neon-noir", "idea": "robots", "start": W6, "style": "shatter", "timing": "snap",
     "effects": ["feedback", "smear"], "look": "cyan-flash", "foreshadow": "trace", "macros": WILD},
    {"label": "deepsea_fish_feedback", "vibe": "bioluminescent", "idea": "underwater", "start": W6, "style": "bloom", "timing": "beat",
     "effects": ["kaleido", "feedback"], "look": "cool-echo", "foreshadow": "trace", "macros": MAX},
    {"label": "thermal_aviation_spin", "vibe": "thermal", "idea": "aviation", "start": W6, "style": "spin", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "ink_samurai_melt", "vibe": "ink-water", "idea": "samurai", "start": W6, "style": "melt", "timing": "beat",
     "effects": ["slitscan"], "look": "auto", "foreshadow": "silhouette", "macros": MAX},
    {"label": "cyber_egypt_fold", "vibe": "cyberspace-95", "idea": "egypt", "start": W7, "style": "fold", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "ferro_bloom_beat", "vibe": "ferrofluid", "start": W7, "style": "bloom", "timing": "beat",
     "effects": ["feedback"], "look": "auto", "foreshadow": "negative", "macros": MAX},
    {"label": "shadow_magic_melt", "vibe": "shadow-self", "idea": "magic", "start": W2, "style": "melt", "timing": "beat",
     "effects": ["smear"], "look": "noir-glow", "foreshadow": "trace", "macros": MAX},
    {"label": "gold_finale_melt", "vibe": "liquid-gold", "start": W8, "style": "melt", "timing": "smooth",
     "effects": ["feedback"], "look": "auto", "foreshadow": "auto", "macros": {**MAX, "glow": 0.6}},
    {"label": "botanical_finale_bloom", "vibe": "botanical", "start": W8, "style": "bloom", "timing": "smooth",
     "effects": [], "look": "auto", "foreshadow": "silhouette", "macros": {**MAX, "glow": 0.6}},
    {"label": "holo_space_fold", "vibe": "hologram", "idea": "space", "start": W3, "style": "fold", "timing": "beat",
     "effects": ["feedback"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "machine_spin_snap", "vibe": "odd-machine", "start": W2, "style": "spin", "timing": "snap",
     "effects": ["smear"], "look": "auto", "foreshadow": "negative", "macros": WILD},
    # round 3 (Tys, 29 Oct 6:15 pm: "dont do the same ones twice ... make sure its new and it doesnt repeat"): one vibe a
    # slot across the montage's back 98 s, each on its own stretch of the song, the morph plain to see
    {"label": "cosmic_bloom_beat", "vibe": "cosmic", "start": W3B, "style": "bloom", "timing": "beat",
     "effects": ["feedback"], "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "riso_fold_snap", "vibe": "risograph", "start": W3B, "style": "fold", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "kintsugi_shatter_snap", "vibe": "porcelain-kintsugi", "start": W3B, "style": "shatter", "timing": "snap",
     "effects": [], "look": "auto", "foreshadow": "silhouette", "macros": MAX},
    {"label": "y2k_spin_beat", "vibe": "y2k-chrome", "start": W3B, "style": "spin", "timing": "beat",
     "effects": ["slitscan"], "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "ice_melt_smooth", "vibe": "ice-crystal", "start": W5B, "style": "melt", "timing": "smooth",
     "effects": ["feedback"], "look": "auto", "foreshadow": "silhouette", "macros": {**MAX, "glow": 0.8}},
    {"label": "lowpoly_fold_snap", "vibe": "low-poly", "start": W6, "style": "fold", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "none_pirates_beat", "vibe": "none", "idea": "pirates", "start": W7, "style": "auto", "timing": "beat",
     "effects": ["smear"], "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "inkwash_melt_beat", "vibe": "ink-wash", "start": W7, "style": "melt", "timing": "beat",
     "effects": ["slitscan"], "look": "auto", "foreshadow": "silhouette", "macros": MAX},
    {"label": "marble_spin_snap", "vibe": "porcelain-marble", "start": W8, "style": "spin", "timing": "snap",
     "effects": ["feedback"], "look": "auto", "foreshadow": "negative", "macros": MAX},
    {"label": "prism_shatter_snap", "vibe": "glass-prism", "start": W8, "style": "shatter", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "trace", "macros": WILD},
    {"label": "black_bloom_beat", "vibe": "black", "start": W8, "style": "bloom", "timing": "beat",
     "effects": ["feedback", "smear"], "look": "auto", "foreshadow": "trace", "macros": MAX},
    # the morph reel Tys posted (Owly's xenoform_morph_reel_FB_X.mp4, 20 s): one unbroken chain of glossy black liquid
    # forms on pure black, each formed before it flows on, no effects at all; the black vibe made that way opens the
    # montage on the two quiet bars before the drop
    {"label": "black_liquid_smooth", "vibe": "black", "start": W1, "style": "bloom", "timing": "smooth",
     "idea": "rose, lotus, jellyfish, manta ray, nautilus, dragonfly, sea urchin, butterfly",  # the reel's own objects
     "effects": [], "look": "auto", "foreshadow": "off",  # the vibe's own light: the reel's teal/violet edge light and bloom
     "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.15, "glow": 0.6, "drums": 0.6, "bass": 0.6, "vocals": 0.4, "other": 0.4}},
    # Tys, 29 Oct 6:40 pm: "that lotus flower ... its kind of unique compared to the other objects ... can we have more of
    # them?": black glass flowers grown around the reel's lotus, for the calm after the long drop
    {"label": "black_flowers_melt", "vibe": "black", "start": W5B, "style": "bloom", "timing": "smooth",
     "idea": "rose, lotus, orchid, dahlia, protea, peony, passion flower, calla lily, magnolia", "effects": [], "look": "auto",
     "foreshadow": "off", "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.15, "glow": 0.6, "drums": 0.6, "bass": 0.6, "vocals": 0.4, "other": 0.4}},
    # Tys, 29 Oct 6:45 pm, on v97's black glass rose at 0:09 that "sort of opens up": the opener's two bars are this
    # cut's first two shots (to 116.8 s, then to 119.6 s), so the chain is pinned: a droplet grows into the rose, the
    # rose blooms open into the lotus as the drop lands, then the jellyfish
    {"label": "black_rose_open", "vibe": "black", "start": W1, "style": "bloom", "timing": "smooth", "effects": [], "look": "auto",
     "foreshadow": "off", "pins": {"0": "black/11_droplet_black_glass.jpg", "1": "black/00_rose_black_glass.jpg",
                                   "2": "black/05_lotus_black_glass.jpg", "3": "black/01_jellyfish_black_glass.jpg"},
     "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.15, "glow": 0.6, "drums": 0.6, "bass": 0.6, "vocals": 0.4, "other": 0.4}},
    # round 4: hologram, thermal and ink-water have no still library and desk 47325's code (6:25 am) gives a vibe without
    # one a gold look (holo_space_fold, thermal_aviation_spin, ink_samurai_melt all came out amber); these have libraries
    {"label": "chrome_robots_spin", "vibe": "chrome-mercury", "idea": "robots", "start": W6, "style": "spin", "timing": "beat",
     "effects": ["feedback"], "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "marble_spin_w6", "vibe": "porcelain-marble", "start": W6, "style": "spin", "timing": "snap",
     "effects": ["dither"], "look": "auto", "foreshadow": "negative", "macros": MAX},
    {"label": "brutalist_fold_snap", "vibe": "brutalist", "start": W8, "style": "fold", "timing": "snap",
     "effects": ["smear"], "look": "auto", "foreshadow": "slices", "macros": MAX},
    {"label": "neonnight_bloom_beat", "vibe": "neon-night", "start": W8, "style": "bloom", "timing": "beat",
     "idea": "jellyfish, manta ray, sea turtle, lotus, rose, dahlia, amethyst geode, owl", "effects": ["feedback"],
     "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "glass_space_bloom", "vibe": "iridescent-glass", "idea": "space", "start": W8, "style": "bloom", "timing": "beat",
     "effects": ["feedback"], "look": "auto", "foreshadow": "trace", "macros": MAX},
    # Tys, 30 Oct: the rose into the lotus is "a bit too similar to the demo we already did for our facebook page ... do
    # something similar but not so identical": the same idea, other flowers and another light. The opener's two bars are
    # shot 1 (5.58 to 8.33 in the cut): the orchid opening into the passion flower, under the cool-echo grade's teal
    {"label": "black_orchid_open", "vibe": "black", "start": W1, "style": "bloom", "timing": "smooth", "effects": [], "look": "cool-echo",
     "foreshadow": "off", "pins": {"0": "black/024_tulip.jpg", "1": "black/029_orchid.jpg", "2": "black/031_passion_flower.jpg",
                                   "3": "black/030_protea.jpg"},
     "macros": {"intensity": 0.5, "speed": 0.5, "chaos": 0.15, "glow": 0.6, "drums": 0.6, "bass": 0.6, "vocals": 0.4, "other": 0.4}},
    # gauntlet round 1 (Owly, 30 Oct): the fish "read as a flat kaleidoscope, no fish are ever visible" (Tys wanted the fish
    # to have airtime and burn in): feedback trails, no kaleido; neon night read as ferrofluid twice: ocean in its place;
    # the demo's effects shot repeated the intro's kaleido: risograph with dither, slit-scan and feedback
    {"label": "deepsea_fish_clear", "vibe": "bioluminescent", "idea": "underwater", "start": W1, "style": "bloom", "timing": "beat",
     "effects": ["feedback"], "look": "cool-echo", "foreshadow": "trace", "macros": {**MAX, "chaos": 0.6}},
    {"label": "ocean_bloom_beat", "vibe": "ocean", "start": W8, "style": "bloom", "timing": "beat",
     "idea": "jellyfish, nautilus, manta ray, koi, anglerfish, crown splash, pearl, sea anemone", "effects": ["dither"],
     "look": "auto", "foreshadow": "trace", "macros": MAX},
    {"label": "body_fx_riso", "vibe": "risograph", "start": WB, "style": "fold", "timing": "beat",
     "effects": ["dither", "slitscan", "feedback"], "look": "auto", "foreshadow": "slices", "macros": WILD},
    # the demo body's output scene, on the seconds of the bed it plays over (the body's bed is the song from 0)
    {"label": "body_none_underwater", "vibe": "none", "idea": "underwater", "start": WB, "style": "auto", "timing": "smooth",
     "effects": [], "look": "auto", "foreshadow": "auto", "macros": {**MAX, "chaos": 0.5, "glow": 0.6}},
    {"label": "body_spin_snap", "vibe": "neon-noir", "start": WB, "style": "spin", "timing": "snap",
     "effects": ["dither"], "look": "cyan-flash", "foreshadow": "trace", "macros": WILD},
    # cyberspace's black ground carries the kaleidoscope (chrome's pale ground washed it out: chrome_spin_snap)
    {"label": "body_fx_kaleido", "vibe": "cyberspace-95", "start": WB, "style": "melt", "timing": "beat",
     "effects": ["kaleido", "feedback", "slitscan"], "look": "auto", "foreshadow": "negative", "macros": WILD},
]


def make(cut, aspect, audio_id):
    body = {"audio_id": audio_id, "quality": "turbo", "live": True, "mode": "simple", "song": "Glitch Out",
            "vibe": cut["vibe"], "idea": cut.get("idea", ""), "quality_tier": "cloud", "cloud_final_ok": True,
            "aspect": aspect, "length_s": 30, "length_start": cut["start"], "energy_preset": "dense",
            "morph_source": "objects", "morph_count": "auto", "morph_style": cut["style"], "morph_timing": cut["timing"],
            "effects": cut["effects"], "beat_fx": True, "dance_fx": cut["look"], "foreshadow": cut["foreshadow"],
            "scene_stills": cut.get("scenes", "off"), "scenes_chosen": True, "macros": cut["macros"],
            "end_card": False, "open_weights_only": True, "paid_cloud": False, "vertical_mode": "auto", "stem_orbit": True,
            "chain_pins": cut.get("pins") or {}}  # chain slot -> still file, as the Chain row's pins send them
    r = requests.post(f"{DESK}/api/generate", json=body, timeout=180)
    if r.status_code != 200:
        return None, f"refused {r.status_code}: {r.text[:300]}"
    return r.json()["id"], ""


def main():
    aspect = sys.argv[1]
    only = set(sys.argv[2:])
    tag = "169" if aspect == "16:9" else "916"
    OUT.mkdir(exist_ok=True)
    log_path = OUT / f"renders_{tag}.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    done = {row["label"] for row in log if row.get("status") == "done"}
    # an upload, not /api/songs/load: desk 47325 runs code from before the bundled songs (a missing audio id made the
    # first try cut the bundled demo instead, job 79fcb703, cancelled)
    with open(SONG, "rb") as fh:
        song = requests.post(f"{DESK}/api/analyze", files={"file": (SONG.name, fh, "audio/mpeg")}, timeout=900).json()
    audio_id = song.get("audio_id")
    print("song", audio_id, round(float(song.get("duration") or (song.get("features") or {}).get("duration") or 0), 1), flush=True)
    if not audio_id:
        raise SystemExit(f"no audio id: {str(song)[:300]}")
    # at 9:16 the demo's own cuts first (its body scenes, then its intro's), so the 9:16 demo can be built while the
    # rest of the montage renders
    first = ["body_none_underwater", "body_spin_snap", "body_fx_kaleido", "neon_shatter_snap", "chrome_spin_snap",
             "cyber_fold_beat", "paint_melt_beat", "glass_melt_smooth"]
    order = sorted(CUTS, key=lambda c: first.index(c["label"]) if c["label"] in first else len(first)) if aspect == "9:16" else CUTS
    if only:  # named on the command line: in that order
        order = [c for lab in sys.argv[2:] for c in CUTS if c["label"] == lab]
    queue = list(order)
    while queue:
        pri = (OUT / "priority.txt").read_text(encoding="utf-8").split() if (OUT / "priority.txt").exists() else []
        ahead = [c for lab in pri for c in CUTS if c["label"] == lab and lab not in done and c in queue + CUTS]
        ahead = [c for c in ahead if c["label"] not in {r["label"] for r in log}]
        cut = ahead[0] if ahead else queue[0]
        if cut in queue:
            queue.remove(cut)
        # montage/skip.txt: labels vetoed while the queue runs (Tys, 29 Oct: no odd machine, no low-poly), read before each cut
        skip = set((OUT / "skip.txt").read_text(encoding="utf-8").split()) if (OUT / "skip.txt").exists() else set()
        if cut["label"] in skip:
            print(cut["label"], "skipped (skip.txt)", flush=True)
            continue
        if (only and cut["label"] not in only and cut not in ahead) or cut["label"] in done:
            continue  # (a priority cut renders even when the command line did not name it: it looped here, 29 Oct)
        t0 = time.perf_counter()
        job, err = make(cut, aspect, audio_id)
        if not job:
            print(cut["label"], err, flush=True)
            log.append({"label": cut["label"], "aspect": aspect, "error": err})
            log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
            continue
        print(cut["label"], "job", job, flush=True)
        last = ""
        while True:
            time.sleep(10)
            try:
                j = requests.get(f"{DESK}/api/jobs/{job}", timeout=60).json()
            except Exception as exc:  # a busy desk can miss one poll
                print("  poll:", exc, flush=True)
                continue
            line = f"  {j.get('stage')} {round(float(j.get('progress') or 0) * 100)}% {j.get('detail')}"
            if line != last:
                print(line, flush=True)
                last = line
            if j.get("status") in ("done", "error", "cancelled"):
                break
        took = round(time.perf_counter() - t0, 1)
        row = {"label": cut["label"], "aspect": aspect, "job": job, "status": j.get("status"), "seconds": took,
               "window": cut["start"], "vibe": cut["vibe"], "style": cut["style"], "timing": cut["timing"],
               "effects": cut["effects"], "look": cut["look"], "foreshadow": cut["foreshadow"],
               "scenes": cut.get("scenes", "off"), "error": j.get("error")}
        log.append(row)
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(cut["label"], j.get("status"), "in", took, "s", flush=True)
        mp4 = JOBS / job / "xenoform.mp4"
        if j.get("status") == "done" and mp4.exists():
            size = "320:180" if aspect == "16:9" else "180:320"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", f"fps=16/30,scale={size},tile=8x2",
                            "-frames:v", "1", str(OUT / f"sheet_{tag}_{cut['label']}.jpg")], check=False)
    print("done", flush=True)


main()
