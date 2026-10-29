"""Write plan_long.json: the long walkthrough, one segment a line, each line's sentences read apart (split_copy.py: l05,
l05_2 ...) and expanded here into the segment's ids; the montage in front, Glitch Out under it all (bed.py), every
segment ending on its beat (cutlib); the desk recordings still (no zoom); the outputs the Glitch Out Cloud Finals."""
import json
from pathlib import Path

HERE = Path(__file__).parent
S = HERE.parent.as_posix()
J = "C:/Projects/xenoform-rc2/work/ui/jobs"
CUT = (HERE / "rec" / "cut.txt").read_text().strip()  # the None "underwater" cut made on camera
NONE_RACING, CLIPS, NEON, GOLD, BOTANICAL, NEON_DRAFT = (f"{J}/{j}/xenoform.mp4" for j in (CUT, "a8d18556", "4a7b6108", "aa1b7043", "52131ecf", "7bfc273b"))
# the showcase cuts, Cloud Final (LTX-2.5 on Comfy Cloud, 29 Oct 7:40 am): None "underwater" on XF_HipHop_BoomBap_01,
# neon-noir on XF_DnB_Liquid_01_v1, liquid-gold on XF_Ambient_01; the None cut holds a seahorse pair from 7 to 12 s
NONE_CLOUD, NEON_CLOUD, GOLD_CLOUD = (f"{J}/{j}/xenoform.mp4" for j in ("0c3864af", "e649e412", "7cdc5b35"))
NONE_FAST = f"{J}/b251df0c/xenoform.mp4"  # the Fast Final of the None cut made on camera on 29 Oct 7 am, for the Model grid's tile
REEL = "C:/Users/tyson/Desktop/xeno_round_28oct_night/clip_morph_reel_caligari_nosferatu_nasa.mp4"
# the clips cut on the free film pack (29 Oct, job 1d376198 on desk 47326, from work/ui/film_pack as Setup made it): Metropolis -> A Trip to the Moon -> Jekyll
# and Hyde -> Steamboat Willie -> the Odessa steps -> Apollo 11 -> Nosferatu -> The General, 16:9 Fast Final, 20 s
FILMCUT = f"{J}/1d376198/xenoform.mp4"


def made(label, fallback):
    """A Glitch Out render by its label (montage/renders_169.json, clips_glitch.json), else the older cut."""
    for name in ("renders_169.json", "clips_glitch.json"):
        f = HERE / "montage" / name
        if f.exists():
            for r in json.loads(f.read_text(encoding="utf-8")):
                if r["label"] == label and r.get("status") == "done":
                    return f"{J}/{r['job']}/xenoform.mp4"
    return fallback


FILMCUT = made("clips_demo", FILMCUT)
NONE_W = made("body_none_underwater", NONE_CLOUD)
SPIN_W = made("body_spin_snap", NEON_CLOUD)
FX_W = made("body_fx_kaleido", NEON_CLOUD)
GOLD_W = made("gold_bloom_smooth", GOLD_CLOUD)
DEEP_W = made("deepsea_bloom_beat", NONE_CLOUD)
BLACK_W = made("black_flowers_melt", NONE_CLOUD)


def wide(path, t0, fade=0.0):
    out = {"pic": "wide", "video": [path, t0]}
    if fade:
        out["fade"] = fade
    return out


def screen(shot, pieces, zoom=None):
    """A desk recording, still and full frame (the old push-ins are dropped: Tys, 29 Oct, no shake and zoom)."""
    return {"pic": "screen", "shot": shot, "pieces": pieces}


def one(path, t0):
    return {"pic": "one", "video": [path, t0]}


def chain(*parts):
    return {"pic": "chain", "parts": [list(p) for p in parts]}


STYLES = [[f"{S}/wt/styles/{s}_720.mp4", s.title()] for s in ("melt", "shatter", "bloom", "spin", "fold")]
EFFECTS = [[f"{S}/effects/plain.mp4", "As made"], [f"{S}/effects/dither_look.mp4", "Dither"],
           [f"{S}/effects/feedback_kaleido.mp4", "Feedback + Kaleido"], [f"{S}/effects/slitscan_dither_hits.mp4", "Slit-scan"]]
IDEA_ZOOM = [[1.25, 700, 430], [1.45, 640, 520]]

segments = [
    # the title for three seconds, then the black glass creatures of the morph reel under the rest of the line
    {"id": "l01", "lead": 0.8, "min": 8.0, "pic": chain([3.2, {"pic": "still", "full": True, "image": f"{S}/wt/cards/title_still_169.png"}],
                                                       [None, wide(BLACK_W, 10.0)])},
    {"id": "l02", "pic": screen("tour", [[0.3, "tour_end", 1.15]])},
    {"id": "l03", "min": 5.0, "pic": screen("vibe", [[0.3, 2.8, 0.55]], [[1.3, 700, 300], [1.35, 700, 320]])},
    {"id": "l04", "pic": screen("drop", [[0.2, "drop_end", 0.75]], [[1.2, 700, 330], [1.3, 700, 330]])},
    {"id": "l05", "pic": screen("vibe", [[2.4, "none_click-0.4", 0.57]], [[1.1, 760, 600], [1.2, 760, 620]])},
    {"id": "l06", "pic": chain([3.5, screen("vibe", [["none_click-0.5", "vibe_end", 0.8]])], [None, {**wide(NONE_W, 4.0), "land": True}])},
    {"id": "l07", "pic": screen("ideaintro", [[0.3, "examples+2.0", 0.8]], [[1.25, 650, 480], [1.35, 650, 500]])},
    {"id": "l08", "pic": screen("idea", [[0.4, "idea_end", 0.78]], IDEA_ZOOM)},
    {"id": "l09", "pic": screen("ideafeel", [[3.0, "knobs+2.5", 1.35]], [[1.15, 700, 520], [1.2, 700, 560]])},
    {"id": "l10", "pic": screen("idea", [["chips-1.2", "idea_end", 0.52]], [[1.5, 640, 520], [1.6, 640, 520]])},
    {"id": "l11", "pic": screen("library", [[0.2, "library_end", 0.72]])},
    {"id": "l12", "pic": screen("make", [["make_click-0.6", 7.5, 0.87]])},
    {"id": "l13", "min": 4.5, "pic": screen("make", [[7.5, "make_end", 2.2]])},
    {"id": "l14", "pic": chain([6.5, screen("tiers", [[0.3, "tier_final+2.4", 1.45]])],
                               [None, {"pic": "grid", "start": 1.0, "clips": [[NEON_DRAFT, "Draft"], [NONE_FAST, "Fast Final"], [NEON, "Final"], [NEON_CLOUD, "Cloud Final"]]}])},
    {"id": "l15", "pic": screen("tiers", [["tier_fast-0.3", "tiers_end", 1.25]])},
    {"id": "l16", "pic": chain([9.0, screen("stylechips", [[0.8, "stylechips_end", 1.92]])], [None, {"pic": "grid", "rate": 0.4, "clips": STYLES}])},
    {"id": "l17", "pic": screen("timing", [[0.6, "timing_end", 1.07]])},
    {"id": "l18", "pic": chain([3.6, screen("fxchips", [[0.3, 7.5, 2.0]])], [None, {"pic": "grid", "start": 3.0, "clips": EFFECTS}])},
    {"id": "l19", "pic": screen("foreshadow", [[0.6, "foreshadow_end", 1.55]])},
    {"id": "l20", "pic": screen("knobs", [[0.3, "knobs_end", 0.94]])},
    {"id": "l21", "pic": screen("timeline", [["apply_click-4.0", "apply_click+0.6", 1.0], ["apply_click+0.6", "recut_done", 12.0, "Sped up"],
                                             ["recut_done", "timeline_end", 1.0]])},
    {"id": "l22", "pic": screen("playhead", [[0.3, "playhead_end", 0.81]])},
    {"id": "l23", "min": 4.0, "pic": screen("tabs", [[0.2, "tab_shot", 1.05]])},
    {"id": "l24", "pic": screen("tabs", [["tab_shot-0.3", "tab_look-0.3", 0.8]])},
    {"id": "l25", "pic": screen("timeline", [[0.3, "apply_click-0.3", 1.4]])},
    {"id": "l26", "pic": screen("tabs", [["tab_join-0.3", "tab_gpu-0.3", 0.8]])},
    {"id": "l27", "pic": screen("tabs", [["tab_gpu-0.3", "tabs_end", 0.8]])},
    {"id": "l28", "pic": {**wide(DEEP_W, 6.0), "land": True}},
    {"id": "l29", "pic": chain([5.0, screen("clips", [[0.3, "clips_end", 1.2]], [[1.35, 760, 600], [1.45, 820, 620]])], [None, wide(FILMCUT, 0.0)])},
    {"id": "l30", "pic": {**wide(FILMCUT, 4.0), "land": True}},
    {"id": "l31", "pic": wide(FILMCUT, 0.0)},  # the line names the opening handoffs, so the cut replays from its start
    {"id": "l32", "pic": screen("share", [[0.3, "easy-copy-recipe-0.2", 0.75]])},
    {"id": "l33", "pic": {"pic": "still", "image": f"{S}/resolve/resolve_timeline_import.png", "width": 1840,
                          "label": "The neon noir cut, imported into DaVinci Resolve"}},
    {"id": "l34", "pic": chain([3.0, screen("share", [["easy-copy-recipe-0.4", "share_end", 0.7]])], [None, screen("variations", [[0.3, "variations_end", 1.0]])])},
    {"ids": ["u1", "u2", "u3", "u4", "u5", "u6"], "id": "u1", "lead": 0.4, "pic": {"pic": "card", "video": [f"{S}/wt/rec/underhood.mp4", 0.0]}},
    {"id": "l36", "lead": 0.4, "pic": {"pic": "card", "video": [f"{S}/wt/rec/built_long.mp4", 0.0]}},
    {"id": "l37", "pic": screen("connect", [[0.3, "connect_end", 1.0]], [[1.2, 700, 400], [1.2, 700, 560]])},
    {"id": "l38", "pic": screen("setup", [[0.3, "setup_end", 1.4]])},
    {"id": "l39", "lead": 0.6, "min": 5.5, "pic": {"pic": "card", "video": [f"{S}/wt/rec/end.mp4", 0.0]}},
]
# each segment's lines become their sentences, read apart: l05 -> l05, l05_2, ...
COPY = json.loads(Path("C:/Projects/xenoform-rc2/docs/demo/long_voice.json").read_text(encoding="utf-8"))["lines"]
for seg in segments:
    base = seg.get("ids") or [seg["id"]]
    seg["ids"] = [r["id"] for b in base for r in COPY if r["id"] == b or r["id"].startswith(b + "_")]
    seg["id"] = seg["ids"][0]
INTRO = HERE / "montage" / "intro_long.mp4"  # the whole montage up to its title (Tys, 30 Oct: the short intro was "weak" for the long)
plan = {"copy": "C:/Projects/xenoform-rc2/docs/demo/long_voice.json", "music": f"{S}/wt/montage/bed_long.wav", "music_start": 0.0,
        "music_gain_db": -9, "music_fade_in": 0.05, "lead": 0.5, "gap": 0.7, "tail": 0.8,
        "grid": {"features": f"{S}/wt/montage/bed_long.beats.json", "bar_phase": 0, "bar_slack": 1.0, "half_slack": 0.45},
        "segments": segments}
if INTRO.exists():  # the intro up to its title on the hit, then l01 over the title
    meta = json.loads(INTRO.with_suffix(".json").read_text(encoding="utf-8"))
    plan["intro"] = INTRO.as_posix()
    plan["intro_tail"] = {"song": "C:/Projects/xenoform-rc2/examples/songs/glitch_out.mp3", "start": meta["title"], "seconds": 1.6,
                          "gain_db": meta["gain_db"]}
(HERE / "plan_long.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
print(len(segments), "segments")
