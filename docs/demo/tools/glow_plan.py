"""Fill plan_short.json with the glow-up's renders: the output scenes (result, styles, effects, clips) take their Glitch
Out cuts by label, 16:9 ("video") and 9:16 ("video_v", when that cut exists at 9:16), each with an in point near the
song time it plays over (they were made on the very seconds of the bed they sit on); the intro is the montage's demo
excerpt (montage/intro_169.mp4, intro_916.mp4) with its ring-out.

    python glow_plan.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
M = HERE / "montage"
J = "C:/Projects/xenoform-rc2/work/ui/jobs"
SONG = "C:/Projects/xenoform-rc2/examples/songs/glitch_out.mp3"


def rows(name):
    p = M / name
    return {r["label"]: r for r in json.loads(p.read_text(encoding="utf-8")) if r.get("status") == "done"} if p.exists() else {}


r169, r916, clips = rows("renders_169.json"), rows("renders_916.json"), rows("clips_glitch.json")
offsets = json.loads((M / "offsets.json").read_text(encoding="utf-8")) if (M / "offsets.json").exists() else {}
plan = json.loads((HERE / "plan_short.json").read_text(encoding="utf-8"))
music_start = float(plan.get("music_start", 0.0))

# the body's timeline as cutlib will lay it, for each scene's song time
import sys  # noqa: E402
sys.path.insert(0, str(HERE))
import cutlib  # noqa: E402
lines = {r["id"]: r for r in json.loads(Path(r"C:\Projects\kokoro-tts\reads\short2_af_heart\lines.json").read_text(encoding="utf-8"))["lines"]}
segs, _ = cutlib.timeline(plan, lines)
song_at = {s["id"]: music_start + s["start"] for s in segs}

# the effects scene: risograph (Owly, round 1: the green kaleido repeated the intro's)
SCENES = {"result": "body_none_underwater", "styles": "body_spin_snap", "effects": "body_fx_riso"}


def in_point(job, song_t, window):
    """Where in a cut the bed's song time falls (its measured start, else the requested window)."""
    off = offsets.get(job)
    if off is None:
        sys.path.insert(0, str(HERE))
        from song_offset import offset
        off = offset(job, window)[0]
        offsets[job] = off
    return max(0.0, round(song_t - off, 3))


for seg in plan["segments"]:
    sid = seg.get("id") or seg["ids"][0]
    if sid in SCENES and SCENES[sid] in r169:
        r = r169[SCENES[sid]]
        seg["pic"]["video"] = [f"{J}/{r['job']}/xenoform.mp4", in_point(r["job"], song_at[sid], r["window"])]
        if SCENES[sid] in r916:
            v = r916[SCENES[sid]]
            seg["pic"]["video_v"] = [f"{J}/{v['job']}/xenoform.mp4", in_point(v["job"], song_at[sid], v["window"])]
    if sid == "clips" and "clips_demo" in clips:
        r = clips["clips_demo"]
        part = seg["pic"]["parts"][1][1]
        screen_s = seg["pic"]["parts"][0][0]
        # whole beats later when the plan asks (the Moon is in the intro; from the Lost World on)
        later = float(part.get("shift_beats") or 0) * 0.6667
        part["video"] = [f"{J}/{r['job']}/xenoform.mp4", round(in_point(r["job"], song_at[sid] + screen_s, r["window"]) + later, 3)]
    if sid == "open" and seg["pic"].get("pic") == "still":  # since 30 Oct 2 pm the open line plays over the orchid opening, not a card
        seg["pic"]["image_v"] = (HERE / "cards" / "title_still_916.png").as_posix()
for aspect, key in (("169", "intro"), ("916", "intro_v")):
    intro = M / f"intro_{aspect}.mp4"
    if intro.exists():
        meta = json.loads(intro.with_suffix(".json").read_text(encoding="utf-8"))
        plan[key] = intro.as_posix()
        # Tys, 30 Oct 1:50 pm: the demo opens on the montage's gold outro, title and song played out, like the long ("you can
        # remove the 30 intro it currently has"): an intro past its title needs no ring-out
        full = float(meta["seconds"]) > float(meta["title"]) - float(meta["song_start"]) + 0.5
        if aspect == "169":
            if full:
                plan.pop("intro_tail", None)
            else:
                plan["intro_tail"] = {"song": SONG, "start": meta["title"], "seconds": 1.6, "gain_db": meta["gain_db"]}
(M / "offsets.json").write_text(json.dumps(offsets, indent=1), encoding="utf-8")
(HERE / "plan_short.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False), encoding="utf-8")
for seg in plan["segments"]:
    sid = seg.get("id") or seg["ids"][0]
    pic = seg["pic"]
    print(f"{sid:9} {song_at[sid]:6.2f}", pic.get("video") or (pic.get("parts") or [[0, {}]])[-1][1].get("video") or "", pic.get("video_v") or "")
print("intro", plan.get("intro"), plan.get("intro_v"))
