"""Clips mode: a cut made only of your clips, each one morphing into the next.

Tys, 28 Oct: "if we are going to morph movie clips, make it so its just movie clips, and if we are doing objects just
objects". A Make whose body says ``morph_source: "clips"`` takes the clips in the user's folder (``own_clips``) and no
stills at all. The song's shots (``dense.shots_for``, the same plan as an object cut) alternate: a clip, a morph, a
clip, a morph... Each clip shot plays the busiest stretch of a clip at 1:1 (``own_media.busiest_start``); each morph
shot is generated from the last frame the clip before it shows into the first frame the clip after it shows, on the
cut's tier (Draft, Fast Final or Final), so every handoff is a transformation and nothing jumps. The clips cycle when
the song has more shots than the folder has clips, each return a later stretch. The look, the knobs, the beat FX,
the effects and the timeline's Look, Colour and Effects work as on an object cut; a re-cut works from the cached
files; there is no object to swap or re-render (``source: "clips"`` on the record tells the lane).

The pacing engine (1 Nov, Tys: "build it, with rests that never freeze film"): a clips cut the engine plans (any Shape
but Breathe off with Drops off, ``paced``) is laid out by ``arrange`` from the same plan an object cut gets, then shaped
by the same helpers (``dense.shape_shots``: each passage's Chaos, Intensity, timing and its one effect, the taste
file's per-shot rules; ``boundary_fx`` by passage; the flash tame under Breathe):

- no shot under a bar but in a hot drop run's first two bars (``tidy``): the plan's two-beat slivers fold into a
  neighbour, so a film is never a flash between two others outside a drop's entry;
- every drop run opens on a cut on its first beat to a fresh film, and so does each style event a long run plants
  every eight bars (``kinds``): a clip after a clip, the clip before it playing up to the hit; the punch and the stutter
  stay on that clip, the run's morphs snap;
- a rest is film playing, never a held frame (``hand_over``): a clip plays on over its rest; a morph that would rest
  lands on the incoming clip's first frame and hands over to it, so the clip starts there, moving, and no morph sits on
  its soft last frame; and no morph plays slower than ``pacing.MIN_PLAY`` (a longer one gives the rest of its time to
  the clip it lands on);
- under full Breathe a scene passage holds one film (``assign``: the clips of one family, the film the pack says a clip
  is from), and every drop run's cut goes to a film none of the last three were; a clip is never shown twice while
  unused ones remain.

Breathe off with Drops off is the cut as it was made before (``merge_first`` and ``slots``): tests/test_clips_legacy.py
holds it to the mainline's byte for byte.
"""
from __future__ import annotations

import copy
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger("xenoform")

SOURCE = "clips"
MORPH_RENDER_S = (1, 3)  # a morph renders this many seconds at least and at most; the compositor retimes it to its shot
# A clip morph is a film transition, not an object melting on a dark ground: the vibe's object prompts sent the 28 Oct
# Nosferatu-to-NASA morph through black. The vibe still sets the cut's look; the morph keeps both shots' own light.
PROMPT = ("Use the provided start image as the first frame and the provided end image as the final frame anchor. A seamless "
          "cinematic transformation of the whole first shot into the whole second shot: its shapes, light and colours flow "
          "and reform continuously into the second, one unbroken move, the brightness of both shots kept, film grain, crisp, "
          "high detail.")
NEGATIVE = ("fade to black, black frames, darkness, blank frame, white flash, text, letters, watermark, logo, cut, hard cut, "
            "flicker, blurry, low quality, cartoon")
FPS = 24                 # the shots' frames are counted at this rate (cloud_morph.custom_shots)
CUT_BEATS = 4            # a paced clips cut: no shot under a bar, but in a hot drop run's first two bars
FRESH_BACK = 3           # a fresh film is none of the last three shown (pacing.fresh_at_drops' window)
SLOW_MIN = 0.5           # a clip shot longer than its clip plays it slowed, never slower than this, before it holds


def wants(state: dict | None) -> bool:
    """Whether this Make is a clips cut."""
    return str((state or {}).get("morph_source") or "").strip().lower() == SOURCE


def slots(n_shots: int, n_clips: int) -> list[dict]:
    """What each shot plays: ``{"kind": "clip", "clip": k, "turn": t}`` and ``{"kind": "morph", "a": k, "b": k2}``
    alternating, a clip first and a clip last (an even count ends on a clip by giving the first clip two shots, see
    ``merge_first``). ``turn`` counts the clip's earlier appearances, so a return plays a later stretch."""
    out: list[dict] = []
    seen: dict[int, int] = {}
    for i in range(n_shots):
        k = (i // 2) % max(1, n_clips)
        if i % 2 == 0:
            out.append({"kind": "clip", "clip": k, "turn": seen.get(k, 0)})
            seen[k] = seen.get(k, 0) + 1
        else:
            out.append({"kind": "morph", "a": k, "b": (i // 2 + 1) % max(1, n_clips)})
    return out


def merge_first(shots: list[dict]) -> list[dict]:
    """An even number of shots would end on a morph into nothing: the first two shots become one, so the cut opens on a
    longer first clip and ends on a clip."""
    if len(shots) < 2 or len(shots) % 2:
        return shots
    a, b = shots[0], shots[1]
    merged = {**a, "end": b["end"], "seconds": round(float(b["end"]) - float(a["start"]), 4),
              "frames": int(a.get("frames") or 0) + int(b.get("frames") or 0)}
    return [merged] + shots[2:]


def clip_names(clips: list[dict]) -> list[str]:
    """What the chain and the morph lines call each clip: its ``label`` (``own_media.scan`` reads the folder's
    labels.json, which the free film pack writes), else the file's stem after its first underscore ("03_trip_moon_eye"
    reads "trip moon eye"), else the stem."""
    out: list[str] = []
    for c in clips:
        stem = Path(c["path"]).stem
        out.append(str(c.get("label") or (stem.split("_", 1)[-1].replace("_", " ") if "_" in stem else stem)))
    return out


def family_of(clip: dict) -> str:
    """The film a clip is from (its family): the folder's pack.json says it for the free film pack (``own_media.scan``
    reads it as ``family``); any other clip is a film of its own (its file)."""
    fam = str((clip or {}).get("family") or "").strip().lower()
    return fam or Path(str((clip or {}).get("path") or "")).name.lower()


def window(clip: dict, need_s: float, turn: int) -> float:
    """Where a clip's stretch starts: its busiest window the first time, the next busiest that does not overlap on each
    return (``own_media.ranked_starts``)."""
    from xenoform import own_media

    seconds = float(clip.get("seconds") or 0.0)
    ranked = own_media.ranked_starts(clip["path"], seconds, need_s)
    return ranked[max(0, int(turn)) % len(ranked)]


def sizes(opt: dict, engine: str) -> tuple[tuple[int, int], tuple[int, int] | None]:
    """The cut's output size (the clips are rendered at it) and the morph render size (None: the engine's own)."""
    from xenoform import beatfx, dense, upscale_pass

    portrait = opt["aspect"] == "9:16"
    if opt.get("fast"):
        out = upscale_pass.out_size(opt["aspect"])
    elif engine == "ltx23":
        from xenoform import final_tier

        out = final_tier.sizes(True)["out"] if portrait else beatfx.out_size(opt["aspect"], "final")
    else:
        out = (540, 960) if portrait else beatfx.out_size(opt["aspect"], "draft")
    return tuple(out), (dense.DRAFT_916 if portrait else None)


def _frames_png(clip_file: Path, dest: Path, size: tuple[int, int]) -> tuple[Path, Path]:
    from xenoform import own_media

    return own_media.first_last(clip_file, dest, size)


# ------------------------------------------------------------------------------------------------ the paced layout


def paced(state: dict | None, shots: list[dict]) -> bool:
    """True when the clips cut follows the pacing engine: its plan has passages and its Shape is not Breathe off with
    Drops off (``pacing.legacy``: that is the cut as it was made before)."""
    from xenoform import pacing

    return not pacing.legacy(state) and pacing.paced_shots(shots)


def _period(plan: dict | None, beats: list | None) -> float:
    try:
        p = float((plan or {}).get("period") or 0.0)
    except (TypeError, ValueError):
        p = 0.0
    if p > 0.05:
        return p
    b = sorted(float(x) for x in beats or [])
    gaps = sorted(y - x for x, y in zip(b, b[1:]) if y - x > 0.05)
    return gaps[len(gaps) // 2] if gaps else 0.5


def _frames(shots: list[dict]) -> list[dict]:
    """Each shot's index, seconds and frames from its start and end (frames counted on edges at ``FPS``, as
    ``cloud_morph.custom_shots`` counts them, so the shots still add up to the song)."""
    if not shots:
        return shots
    edges = [round(float(s["start"]) * FPS) for s in shots] + [round(float(shots[-1]["end"]) * FPS)]
    for i, (s, a, b) in enumerate(zip(shots, edges, edges[1:])):
        s["index"] = i
        s["seconds"] = round(float(s["end"]) - float(s["start"]), 4)
        s["frames"] = int(b - a)
    return shots


def _join(a: dict, b: dict) -> dict:
    """``b`` folded into ``a``: ``a``'s start, role, passage, boundary and event, ``b``'s end and the rest it ends on,
    the punches of both."""
    out = {**a, "end": b["end"], "effects": list(a.get("effects") or []) + list(b.get("effects") or [])}
    for key in ("rest", "rest_s"):
        out.pop(key, None)
        if b.get(key):
            out[key] = b[key]
    if b.get("ease") == "out":
        out["ease"] = "out"
    return out


def hot_entries(shots: list[dict], period: float) -> set[int]:
    """The shots in a hot drop run's first two bars (``pacing.ENTRY_BARS`` at heat ``pacing.ENTRY_HEAT`` and over): the
    only place a paced clips cut cuts on the half bar."""
    from xenoform import pacing

    out: set[int] = set()
    first: dict[tuple, float] = {}
    for i, s in enumerate(shots):
        run = s.get("drop_run")
        if run is None:
            continue
        key = (s.get("passage"), run)
        first.setdefault(key, float(s["start"]))
        if (str(s.get("section") or "") == "drop" and float(s.get("heat") or 0.0) >= pacing.ENTRY_HEAT - 1e-9
                and float(s["start"]) < first[key] + pacing.ENTRY_BARS * 4 * period - 1e-3):
            out.add(i)
    return out


def tidy(shots: list[dict], period: float) -> list[dict]:
    """No shot under a bar (``CUT_BEATS``) but in a hot drop run's first two bars: the plan's bar snapping leaves
    two-beat slivers where a build's zones change and at a passage's end, and on film each would flash a clip by. A
    shorter shot folds into the shot before it in its passage (or the one after, when it opens the passage or the one
    before opens on an event)."""
    out = [dict(s) for s in shots]
    least = (CUT_BEATS - 0.5) * float(period)  # a tracked bar can come out a little short of four beats
    for _ in range(len(out) + 1):
        hot = hot_entries(out, period)
        done = True
        for i, s in enumerate(out):
            if i in hot or float(s["end"]) - float(s["start"]) >= least:
                continue

            def same(j: int) -> bool:
                return 0 <= j < len(out) and out[j].get("passage") == s.get("passage")

            if same(i - 1) and not s.get("event") and not s.get("boundary"):
                out[i - 1:i + 1] = [_join(out[i - 1], s)]
            elif same(i + 1) and not out[i + 1].get("event"):
                out[i:i + 2] = [_join(s, out[i + 1])]
            else:
                continue
            done = False
            break
        if done:
            break
    return _frames(out)


def kinds(shots: list[dict]) -> tuple[list[dict], list[str]]:
    """Clip or morph, a shot: a clip first and last, a morph only between two clips. A drop run's first beat, and a long
    run's planted style event (a clip morph has one style: on film the event is the cut; the shot's ``event`` says
    "cut"), open on a cut to a fresh film: the shot there is a clip after a clip, the morph that would have led into it
    folded into the clip before it (which plays up to the hit), or a clip of its own when it opens its passage. A cut
    that would end on a morph ends on a clip the same way. Returns the shots and their kinds."""
    out = [dict(s) for s in shots]
    for s in out:
        if s.get("event") == "style":
            s["event"] = "cut"
    kind: list[str] = []
    i = 0
    while i < len(out):
        if i == 0:
            kind.append("clip")
        elif str(out[i].get("event") or "") in ("drop", "cut"):
            if kind[i - 1] == "morph":
                if out[i - 1].get("boundary"):
                    kind[i - 1] = "clip"
                else:
                    out[i - 2:i] = [_join(out[i - 2], out[i - 1])]
                    kind.pop()
                    i -= 1
            kind.append("clip")
        else:
            kind.append("morph" if kind[i - 1] == "clip" else "clip")
        i += 1
    if len(kind) > 1 and kind[-1] == "morph":
        if out[-1].get("boundary"):
            kind[-1] = "clip"
        else:
            out[-2:] = [_join(out[-2], out[-1])]
            kind.pop()
    return _frames(out), kind


def _regroup(shots: list[dict]) -> list[dict]:
    """Each in-shot effect (a punch, a stutter) back on the shot it falls in, after the shots' edges moved."""
    every = sorted((fx for s in shots for fx in s.get("effects") or []), key=lambda fx: float(fx.get("t", 0.0)))
    for s in shots:
        s["effects"] = []
    k = 0
    for fx in every:
        t = float(fx.get("t", 0.0))
        while k + 1 < len(shots) and t >= float(shots[k]["end"]) - 1e-6:
            k += 1
        while k > 0 and t < float(shots[k]["start"]) - 1e-6:
            k -= 1
        shots[k]["effects"].append(fx)
    return shots


def hand_over(shots: list[dict], kind: list[str], period: float, beats: list | None = None) -> tuple[list[dict], list[str]]:
    """A rest is film playing, never a held frame. A clip shot plays on over its rest (the shot keeps ``rest``, its beats,
    without ``rest_s``: nothing holds). A morph shot that rests lands on the incoming clip's first frame and hands over
    there: it ends where its rest began and the clip after it starts there, moving, the rest's beats on it. And no morph
    plays slower than ``pacing.MIN_PLAY``: a longer one ends on the last beat of the song that keeps it under, and the
    clip it lands on takes the rest of its time. Where that clip opens the next passage, it starts here as a shot of this
    passage and carries on into its own as one more shot (``cont``: the same film, no cut), so every passage keeps the
    span the song gives it. Returns the shots and their kinds."""
    from xenoform import pacing

    out = [dict(s) for s in shots]
    kd = list(kind)
    grid = sorted(float(b) for b in beats or [])
    longest = MORPH_RENDER_S[1] / pacing.MIN_PLAY
    i = 0
    while i < len(out):
        s = out[i]
        rest_s = float(s.pop("rest_s", 0.0) or 0.0)
        rest = int(s.pop("rest", 0) or 0)
        if kd[i] == "clip":
            if rest:
                s["rest"] = int(s.get("rest") or 0) + rest
            i += 1
            continue
        if i + 1 >= len(out):
            i += 1
            continue
        a, b = float(s["start"]), float(s["end"])
        at = b - rest_s if rest_s > 0 else b
        if at - a > longest + 1e-3:
            on = [t for t in grid if a + 2 * period - 1e-3 <= t <= a + longest + 1e-3]
            at = on[-1] if on else a + longest
        if at >= b - 1e-3:
            i += 1
            continue
        held = max(1, int(round((b - at) / max(1e-6, float(period)))))
        s["end"] = round(at, 4)
        nxt = out[i + 1]
        if nxt.get("passage") == s.get("passage"):
            nxt["start"] = round(at, 4)
            nxt["rest"] = int(nxt.get("rest") or 0) + held
            i += 1
            continue
        head = {"start": round(at, 4), "end": round(b, 4), "effects": [], "rest": held,
                **{k: s[k] for k in ("section", "passage", "heat", "drop_run") if s.get(k) is not None}}
        nxt["cont"] = True
        out.insert(i + 1, head)
        kd.insert(i + 1, "clip")
        i += 2
    return _frames(_regroup(out)), kd


def assign(shots: list[dict], kind: list[str], clips: list[dict], *, scenes: bool = False) -> list[dict]:
    """The clip each clip shot plays, and the clips each morph runs between: ``slots``' shape, a clip shot's slot with its
    ``family`` and ``cut`` (it opens with a hard cut), a shot that carries a clip on (``cont``) the clip before it.
    Unused clips first, in the folder's order, so a clip comes back (a later stretch, ``turn``) only once every clip has
    played; a cut on an event goes to a fresh film (none of the last ``FRESH_BACK``); under full Breathe (``scenes``) a
    scene passage holds one film, the one with the most clips left (not the film of the scene before, where another
    will do); a clip long enough for its shot before one that is not; no clip right after one of its own film outside a
    scene, where another will do."""
    from xenoform import pacing

    fam = [family_of(c) for c in clips]
    used = [0] * len(clips)
    shown: list[int] = []
    passages = pacing.passage_of(shots)
    scene_film: dict[int, str] = {}
    before = ""
    out: list[dict] = []
    for i, (s, k) in enumerate(zip(shots, kind)):
        if k != "clip":
            out.append({"kind": "morph"})
            continue
        if s.get("cont") and out and out[-1]["kind"] == "clip":  # the same film carried on into the next passage
            out.append({**out[-1], "cut": False, "cont": True})
            p = passages[i]
            if scenes and str(s.get("section") or "") in pacing.SCENE_ROLES and p not in scene_film \
                    and any(not used[c] and fam[c] == out[-1]["family"] for c in range(len(clips))):
                scene_film[p] = before = out[-1]["family"]  # the scene goes on with the film it opened on
            continue
        need = float(s["end"]) - float(s["start"])
        if i + 1 < len(shots) and shots[i + 1].get("cont"):
            need += float(shots[i + 1]["end"]) - float(shots[i + 1]["start"])
        cut = i > 0 and kind[i - 1] == "clip"
        scene = scenes and str(s.get("section") or "") in pacing.SCENE_ROLES and s.get("drop_run") is None
        p = passages[i]
        if scene and p not in scene_film:
            left = {}
            for c, f in enumerate(fam):
                if not used[c]:
                    left[f] = left.get(f, 0) + 1
            want = sum(1 for j, kk in enumerate(kind) if kk == "clip" and passages[j] == p)
            if left:
                scene_film[p] = max(sorted(left), key=lambda f: (min(left[f], want), f != before, left[f]))
                before = scene_film[p]
        recent = {fam[c] for c in shown[-FRESH_BACK:]}
        last = fam[shown[-1]] if shown else ""

        def rank(c: int) -> tuple:
            return (used[c],
                    (fam[c] != scene_film[p]) if scene and p in scene_film else (fam[c] in recent) if cut else (fam[c] == last),
                    float(clips[c].get("seconds") or 0.0) < need - 0.05,
                    c)

        c = min(range(len(clips)), key=rank)
        out.append({"kind": "clip", "clip": c, "turn": used[c], "family": fam[c], "cut": cut})
        used[c] += 1
        shown.append(c)
    for i, sl in enumerate(out):
        if sl["kind"] == "morph":
            sl.update({"a": out[i - 1]["clip"], "b": out[i + 1]["clip"]})
    return out


def arrange(shots: list[dict], plan: dict, clips: list[dict], state: dict, beats: list | None = None) -> dict:
    """What a clips cut plays, shot by shot, before anything renders: ``{"shots", "slots", "paced", "clip_shots"}``. A
    paced cut is ``tidy``, ``kinds``, ``hand_over`` and ``assign`` on the plan's shots; any other is the cut as it was
    (``merge_first``, ``slots``)."""
    from xenoform import pacing

    if not paced(state, shots):
        laid = merge_first([dict(s) for s in shots])
        sl = slots(len(laid), len(clips))
        return {"shots": laid, "slots": sl, "paced": False, "clip_shots": sum(1 for x in sl if x["kind"] == "clip")}
    period = _period(plan, beats)
    laid, kind = kinds(tidy(shots, period))
    laid, kind = hand_over(laid, kind, period, beats)
    scenes = pacing.boldness(pacing.breathe_amount(state)) >= 0.5
    sl = assign(laid, kind, clips, scenes=scenes)
    return {"shots": laid, "slots": sl, "paced": True,
            "clip_shots": sum(1 for x in sl if x["kind"] == "clip" and not x.get("cont"))}


def fit(plan_at: Callable[[int | None], tuple[list[dict], dict]], clips: list[dict], state: dict, *, beats: list | None,
        duration: float, given: bool = False) -> dict:
    """``arrange`` on the plan ``plan_at(None)`` gives (``plan_at(cap)`` plans at most ``cap`` shots; ``given``, a whole
    song's window, plays the song plan as it came). Adds ``plan``."""
    shots, plan = plan_at(None)
    lay = arrange(shots, plan, clips, state, beats)
    lay["plan"] = plan
    return lay


def layout(state: dict, directed: dict, audio_path: Path | None, clips: list[dict]) -> dict:
    """The clips cut's shots and slots for this Make (``fit`` over ``dense.shots_for``, the plan an object cut gets; a
    whole song's window plays its stretch of the song plan as given)."""
    from xenoform import dense

    def plan_at(cap: int | None) -> tuple[list[dict], dict]:
        return dense.shots_for({**state, "max_shots": cap} if cap else state, directed, audio_path)

    return fit(plan_at, clips, state, beats=list(directed.get("beats") or []),
               duration=float(directed.get("duration") or 0.0), given=dense.song_window(state) is not None)


def nouns(shots: list[dict]) -> list[dict]:
    """What a clips cut shows at each handoff, read the way the taste file's per-shot rules read a chain's stills
    (``taste.shot_nouns``: shot i between entries i and i + 1): the clip a clip shot plays, the clips a morph runs
    between."""
    out: list[dict] = []
    for i, s in enumerate(shots):
        m = s.get("clip_morph") if isinstance(s.get("clip_morph"), dict) else None
        head = str((m or {}).get("from") or s.get("label") or "")
        tail = str((m or {}).get("to") or s.get("label") or "")
        if i == 0:
            out.append({"noun": head})
        out.append({"noun": tail})
    return out


# ------------------------------------------------------------------------------------------------ the draft and the cut


def animatic(directed: dict, state: dict, audio_path: Path, out_path: Path, work: Path, *,
             size: tuple[int, int] = (216, 384), fps: int = 12) -> dict:
    """The quick draft before a clips cut renders: the clips' stretches hard-cut on the planned shots with the song, a
    stretch where each morph will be too (the next clip), in seconds. Never the vibe's stills: a clips cut shows only
    clips, from its first frame (Tys, 28 Oct)."""
    import subprocess

    from xenoform import own_media
    from xenoform.turbo import publish_file
    from xenoform.video import ffmpeg_bin

    clips_in = [c for c in (state.get("own_clips") or []) if isinstance(c, dict) and c.get("path")]
    if not clips_in:
        raise ValueError("Clips mode needs your clips.")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    lay = layout(state, directed, Path(audio_path), clips_in)
    shots, plan_slots = lay["shots"], lay["slots"]
    w, h = int(size[0]), int(size[1])
    parts = []
    for i, (s, sl) in enumerate(zip(shots, plan_slots)):
        k = sl["clip"] if sl["kind"] == "clip" else sl["b"]
        frames = max(1, int(round((float(s["end"]) - float(s["start"])) * fps)))
        start = own_media.window_start(float(clips_in[k].get("seconds") or 0.0), frames / float(fps))
        parts.append(own_media.render_clip(clips_in[k]["path"], start, frames, (w, h), work / "animatic" / f"a{i:02d}.mp4", fps=fps))
    listing = work / "animatic_clips.txt"
    # an apostrophe in the path (a repo under C:\Users\O'Brien) is escaped for the concat list, as dense.py does
    listing.write_text("".join("file '" + str(p).replace(chr(92), "/").replace("'", "'\\''") + "'\n" for p in parts), encoding="utf-8")
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.mp4")
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio_path),
                    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(tmp)], check=True)
    publish_file(tmp, out_path)
    return {"shots": len(shots), "clips": len(clips_in), "seconds": round(float(directed.get("duration") or 0.0), 3),
            "size": f"{w}x{h}", "fps": fps, "source": SOURCE}


def run(directed: dict, audio_path: Path, out_path: Path, work: Path, cfg: dict, state: dict,
        report: Callable[[str, float, str], None], *, cancel: Callable[[], bool] | None = None, client=None,
        engine: str | None = None) -> dict:
    """Render a clips cut and write its record (``simple/simple.json``), as ``dense.run_simple`` does for objects."""
    from xenoform import beatfx, dense, own_media
    from xenoform import effects as _E
    from xenoform import morph_style as _ms
    from xenoform import morph_timing as _mt
    from xenoform import pacing as _pc
    from xenoform import taste as _taste

    started = time.perf_counter()
    clips_in = [c for c in (state.get("own_clips") or []) if isinstance(c, dict) and c.get("path")]
    if not clips_in:
        raise ValueError("Clips mode needs your clips: choose a folder of clips (or drop them on the desk), then Make.")
    opt = dense.options(state)
    if opt["cloud"]:
        # the clips cut has no Cloud path yet: it would render Draft morphs here and call the cut "cloud"
        raise RuntimeError("Cloud Final morphs the library's objects, not your clips yet: pick Draft, Fast Final or Final "
                           "for a clips cut. Nothing was sent.")
    work = Path(work) / "simple"
    work.mkdir(parents=True, exist_ok=True)
    lay = layout(state, directed, Path(audio_path), clips_in)
    shots, plan, plan_slots, is_paced = lay["shots"], lay["plan"], lay["slots"], lay["paced"]
    for i, s in enumerate(shots):
        s["index"] = i
    engine = engine or ("ltx23" if opt["tier"] == "final" else "ltx095")
    out_size, morph_size = sizes(opt, engine)
    hp = dense.house(state, cfg)
    vertical_house = opt["aspect"] == "9:16" and str((hp.get("format") or {}).get("aspect") or "") == "9:16"
    fps = int((hp.get("format") or {}).get("fps") or beatfx.FPS) if vertical_house else beatfx.FPS
    vibe = str(state.get("vibe") or "")
    seed = int(state.get("seed") or 2727)
    names = clip_names(clips_in)
    dense.write_chain(work, [{"noun": names[sl["clip"]], "kind": "clip"} for sl in plan_slots
                             if sl["kind"] == "clip" and not sl.get("cont")])
    n_morphs = sum(1 for sl in plan_slots if sl["kind"] == "morph")
    n_runs = sum(1 for sl in plan_slots if sl["kind"] == "clip" and not sl.get("cont"))
    report("restyle", 0.05, f"{len(shots)} shots on the beat: {n_runs} stretches of your {len(clips_in)} clips, "
                            f"{n_morphs} morphs between them")
    duration = float(directed.get("duration") or 0.0)
    if is_paced:  # what the pacing engine planned, in a line (the record keeps it too)
        report("restyle", 0.05, _pc.summary_line(shots, breathe=_pc.breathe_of(state),
                                                 song_start=dense.window_of(state, duration)["song_start"], drop=plan.get("drop"),
                                                 song=_pc.song_context(state)))
    # 1. the clips' stretches, at the cut's size, exactly as long as their shots (a paced cut's clip slowed, never
    # frozen, when its shot outlasts it)
    keep = ("punch", "stutter") if is_paced else ("punch",)  # a paced drop opens on the punch and the stutter
    files: list[Path | None] = [None] * len(shots)
    i = 0
    while i < len(shots):
        sl = plan_slots[i]
        if sl["kind"] != "clip" or sl.get("cont"):
            i += 1
            continue
        j = i + 1  # the shots that carry this clip on into the next passage (hand_over) play the stretch after it
        while j < len(shots) and plan_slots[j].get("cont"):
            j += 1
        clip = clips_in[sl["clip"]]
        need = sum(int(shots[x]["frames"]) for x in range(i, j)) / float(fps)
        start = window(clip, need, sl["turn"])
        have = float(clip.get("seconds") or 0.0)
        speed = max(SLOW_MIN, min(1.0, (have - 0.05) / need)) if is_paced and have and need > have - 0.05 else 1.0
        at = 0.0 if speed < 1.0 else start
        for x in range(i, j):
            s = shots[x]
            files[x] = own_media.render_clip(clip["path"], at, int(s["frames"]), out_size, work / "clips" / f"clip{x:02d}.mp4",
                                             fps=fps, **({"speed": speed} if speed < 1.0 else {}))
            s.update({"own": True, "speed": 1.0, "source": Path(clip["path"]).name, "label": names[sl["clip"]],
                      "clip_start": round(at, 4) if x > i else at,
                      "effects": [e for e in (s.get("effects") or []) if e.get("type") in keep]})
            if is_paced:
                s["family"] = sl.get("family") or family_of(clip)
                if x == i and sl.get("cut"):
                    s["cut_in"] = True  # a hard cut on the beat into this clip (a drop run's, an event's)
                if speed < 1.0:
                    s["clip_speed"] = round(speed, 3)
            s.pop("ease", None)
            at += int(s["frames"]) / float(fps) * speed
        i = j
    # 2. the morphs: the last frame shown before into the first frame shown after, on the cut's tier
    style = _ms.normal(state.get("morph_style") or "auto")
    style = style if style in _ms.STYLES else "melt"
    morph_at = [i for i, sl in enumerate(plan_slots) if sl["kind"] == "morph"]
    notes: list[dict] = []
    for k, i in enumerate(morph_at):
        from xenoform import morph_pass as mp

        mp.stop_queued([], cancel)
        report("restyle", 0.1 + 0.45 * k / max(1, len(morph_at)),
               f"Morph {k + 1} of {len(morph_at)}: {names[plan_slots[i]['a']]} into {names[plan_slots[i]['b']]}")
        frames_dir = work / "clips" / f"ends{i:02d}"
        render_px = morph_size or ((448, 768) if engine == "ltx23" and opt["aspect"] == "9:16" else (512, 288))
        _, a_last = _frames_png(files[i - 1], frames_dir / "a", render_px)
        b_first, _ = _frames_png(files[i + 1], frames_dir / "b", render_px)
        pair = [{"path": str(a_last), "noun": names[plan_slots[i]["a"]], "kind": "scene", "file": a_last.name},
                {"path": str(b_first), "noun": names[plan_slots[i]["b"]], "kind": "scene", "file": b_first.name}]
        render_s = max(MORPH_RENDER_S[0], min(MORPH_RENDER_S[1], int(round(float(shots[i]["seconds"])))))
        one = [{"seconds": float(render_s), "render_s": render_s}]
        sub = work / "clips" / f"morph{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        if engine == "mock":
            from xenoform.cloud_morph import _mock_clips

            made = _mock_clips(one, pair, sub, *render_px)[0]
        elif engine == "ltx23":
            from xenoform import final_tier

            got, fin_notes = final_tier.final_clips(one, pair, sub, cfg, seed + i, vibe, client=client, cancel=cancel,
                                                    vertical=opt["aspect"] == "9:16", state=state, styles=[style], relay=False,
                                                    prompt_text=PROMPT, negative_text=NEGATIVE,
                                                    draft=lambda idx: {j: dense._draft_clips(one, pair, sub, cfg, seed + i, vibe, client,
                                                                                              cancel, state, size=morph_size,
                                                                                              styles=[style], prompt=PROMPT,
                                                                                              negative=NEGATIVE)[0] for j in idx})
            made = got[0]
            notes.extend(fin_notes)
        else:
            made = dense._draft_clips(one, pair, sub, cfg, seed + i, vibe, client, cancel, state, size=morph_size, styles=[style],
                                      prompt=PROMPT, negative=NEGATIVE)[0]
            if opt.get("fast"):
                from xenoform import upscale_pass

                up, up_notes = upscale_pass.upscale_clips([made], sub, upscale_pass.out_size(opt["aspect"]), cfg, client=client,
                                                          cancel=cancel, fps=fps)
                made = up[0]
                notes.extend(up_notes)
        files[i] = Path(made)
        shots[i]["clip_morph"] = {"from": names[plan_slots[i]["a"]], "to": names[plan_slots[i]["b"]]}
        shots[i]["style"] = style
    # 3. the cut, as an object cut is composed: the look, the knobs (a paced cut: each passage's profile, the taste file's
    # per-shot rules), the beat FX, the boundary kinds, the effects, the flash tame under Breathe
    report("assemble", 0.6, "Cutting to the beat" + (" with beat FX" if opt["fx"] else ""))
    m = _taste.cap_macros(dense.macros(state), state)
    plan_shots = copy.deepcopy(shots)
    look_preset = beatfx.resolve_dance_preset(opt["dance_fx"], vibe, hp)
    shaped = dense.shape_shots(shots, state, m, hp if vertical_house else None, look=look_preset,
                               beats=directed.get("beats") or [], stills=nouns(shots), house=hp, drop=plan.get("drop"))
    if shaped:
        notes.append({"pacing": shaped})
    timing_mode = _mt.normal(state.get("morph_timing"))
    timed = _mt.plan(shots, timing_mode, directed.get("beats") or [], plan.get("drop"))
    if timed and is_paced:
        notes.append({"morph_timing": timed})
    effect_names = _E.names_of(state)
    smear = _E.smear_setting(state)
    from xenoform import boundary_fx as _B

    boundary_fx = _B.pick(shots, m, directed.get("beats") or [], fps, seed=seed, premium=None, drop=plan.get("drop"), smear=smear,
                          paced=dense.paced_kinds(state, shots))
    if any(boundary_fx) and is_paced:
        notes.append({"boundary_fx": _B.info(boundary_fx)})
    clips = [Path(f) for f in files]
    palette = own_media.first_last(clips[0], work / "clips" / "palette", (108, 192))[0]  # the look's colours: the opening clip
    tmp = Path(out_path).with_name(Path(out_path).stem + ".simple.mp4")
    made = beatfx.compose(clips, shots, Path(audio_path), tmp, aspect=opt["aspect"],
                          quality="final" if engine == "ltx23" else "draft", fx=opt["fx"], overlay=opt["overlay"],
                          beats=directed.get("beats") or [], report=report, size=out_size, fps=fps,
                          dance_fx=look_preset, stem_orbit=opt["stem_orbit"], stem_env=dense.stem_env_for(state), macros=m,
                          house=hp, end_card=opt["end_card"], seed=seed, palette_image=str(palette),
                          adaptive=str(opt.get("dance_fx") or "auto").strip().lower() == "auto", transitions=None,
                          foreshadow=None, boundary_fx=boundary_fx, effects=effect_names,
                          tones=_E.palette_from_clips(clips).tolist() if _E.wants_tones(look_preset, effect_names, shots) else None,
                          tame=dense.tame_rules(state, shots, fps, directed.get("beats") or []))
    if made.get("tame"):
        notes.append({"tame": made["tame"]})  # the flash tame (Breathe): flash frames found and how many it lifted
    card = None
    if opt["end_card"]:
        report("assemble", 0.96, "Burning the end card")
        card = beatfx.end_card(tmp, opt["recipe"] or "(none)")
    report("assemble", 0.98, "Saving the video")
    shutil.copyfile(tmp, out_path)
    engine_name = {"ltx23": "LTX-2.3 morphs between your clips (Final)", "mock": "mock cross-fades (test)"}.get(
        engine, "LTX 0.9.5 morphs between your clips" + (", upscaled (Fast Final)" if opt.get("fast") else " (Draft)"))
    win = dense.song_window(state)
    info = {"engine": engine_name, "source": SOURCE, "fast": bool(opt.get("fast")), "open_weights": True,
            "energy": opt["energy"], "aspect": opt["aspect"], "tier": opt["tier"], "fx": opt["fx"], "overlay": made["overlay"],
            "end_card": card, "vibe": vibe, "stills": [], "shots": shots, "plan_shots": plan_shots, "plan_name": plan.get("name", ""),
            "clips": [str(c) for c in clips], "own_clips": [dict(c) for c in clips_in], "audio_path": str(audio_path),
            "transitions": None, "boundary_fx": boundary_fx, "drop": plan.get("drop"), "size": list(out_size), "fps": fps,
            "seed": seed, "morph_style": style, "morph_styles": [s.get("style") or "melt" for s in shots],
            "morph_timing": timing_mode, "effects": effect_names, "smear": smear, "palette_image": str(palette),
            "vertical_house": vertical_house,
            "recut_state": {k: state.get(k) for k in ("vibe", "aspect", "quality_tier", "energy_preset", "dance_fx", "stem_orbit",
                                                      "pace", "beat_fx", "beat_overlay", "end_card", "stems_path", "macros",
                                                      "morph_source", "morph_style", "morph_timing", "effects", "boundary_smear")}
            | {"foreshadow": "off",  # no next object to foreshadow: the next picture is footage
               # the shape the cut was made in, so a re-cut starts there (a record without them: both off)
               "breathe": _pc.breathe_amount(state), "drop_mode": _pc.drop_mode_of(state)}
            | ({"song_passage": {k: v for k, v in win.items() if k != "plan"}} if win is not None else {}),
            "pacing": _pc.record(plan, shots, state, dense.window_of(state, duration)),
            "handoffs_s": [s["start"] for s in shots] + [shots[-1]["end"]], "fallbacks": notes,
            "beats": [round(float(b), 4) for b in (directed.get("beats") or [])], "render": made["size"],
            "frames": made["frames"], "seconds": round(time.perf_counter() - started, 2), "look": made.get("look") or {},
            "macros": m, "handoffs": made.get("boundary_fx"), "house": str(hp.get("name") or ""),
            "stems_path": str(state.get("stems_path") or ""),
            "window": dense.window_of(state, duration)}  # where the cut sits in the song
    if made.get("tame"):
        info["pacing"]["tame"] = made["tame"]
    if _taste.active():  # what the taste file did in this Make, as [taste] lines (none in the record without the file)
        info["taste"] = _taste.record(_taste.current())
        for line in info["taste"]["lines"]:
            log.info("%s", line)
    (work / "simple.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
    return info
