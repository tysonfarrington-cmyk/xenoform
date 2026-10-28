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


def animatic(directed: dict, state: dict, audio_path: Path, out_path: Path, work: Path, *,
             size: tuple[int, int] = (216, 384), fps: int = 12) -> dict:
    """The quick draft before a clips cut renders: the clips' stretches hard-cut on the planned shots with the song, a
    stretch where each morph will be too (the next clip), in seconds. Never the vibe's stills: a clips cut shows only
    clips, from its first frame (Tys, 28 Oct)."""
    import subprocess

    from xenoform import dense, own_media
    from xenoform.turbo import publish_file
    from xenoform.video import ffmpeg_bin

    clips_in = [c for c in (state.get("own_clips") or []) if isinstance(c, dict) and c.get("path")]
    if not clips_in:
        raise ValueError("Clips mode needs your clips.")
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    shots, _plan = dense.shots_for(state, directed, Path(audio_path))
    shots = merge_first([dict(s) for s in shots])
    plan_slots = slots(len(shots), len(clips_in))
    w, h = int(size[0]), int(size[1])
    parts = []
    for i, (s, sl) in enumerate(zip(shots, plan_slots)):
        k = sl["clip"] if sl["kind"] == "clip" else sl["b"]
        frames = max(1, int(round((float(s["end"]) - float(s["start"])) * fps)))
        start = own_media.window_start(float(clips_in[k].get("seconds") or 0.0), frames / float(fps))
        parts.append(own_media.render_clip(clips_in[k]["path"], start, frames, (w, h), work / "animatic" / f"a{i:02d}.mp4", fps=fps))
    listing = work / "animatic_clips.txt"
    listing.write_text("".join(f"file '{str(p).replace(chr(92), '/')}'\n" for p in parts), encoding="utf-8")
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

    started = time.perf_counter()
    clips_in = [c for c in (state.get("own_clips") or []) if isinstance(c, dict) and c.get("path")]
    if not clips_in:
        raise ValueError("Clips mode needs your clips: choose a folder of clips (or drop them on the desk), then Make.")
    opt = dense.options(state)
    work = Path(work) / "simple"
    work.mkdir(parents=True, exist_ok=True)
    shots, plan = dense.shots_for(state, directed, Path(audio_path))
    shots = merge_first([dict(s) for s in shots])
    for i, s in enumerate(shots):
        s["index"] = i
    engine = engine or ("ltx23" if opt["tier"] == "final" else "ltx095")
    out_size, morph_size = sizes(opt, engine)
    hp = dense.house(state, cfg)
    vertical_house = opt["aspect"] == "9:16" and str((hp.get("format") or {}).get("aspect") or "") == "9:16"
    fps = int((hp.get("format") or {}).get("fps") or beatfx.FPS) if vertical_house else beatfx.FPS
    vibe = str(state.get("vibe") or "")
    seed = int(state.get("seed") or 2727)
    plan_slots = slots(len(shots), len(clips_in))
    names = [Path(c["path"]).stem.split("_", 1)[-1].replace("_", " ") if "_" in Path(c["path"]).stem else Path(c["path"]).stem
             for c in clips_in]
    dense.write_chain(work, [{"noun": names[sl["clip"]], "kind": "clip"} for sl in plan_slots if sl["kind"] == "clip"])
    n_morphs = sum(1 for sl in plan_slots if sl["kind"] == "morph")
    report("restyle", 0.05, f"{len(shots)} shots on the beat: {len(shots) - n_morphs} stretches of your {len(clips_in)} clips, "
                            f"{n_morphs} morphs between them")
    # 1. the clips' stretches, at the cut's size, exactly as long as their shots
    files: list[Path | None] = [None] * len(shots)
    for i, (s, sl) in enumerate(zip(shots, plan_slots)):
        if sl["kind"] != "clip":
            continue
        clip = clips_in[sl["clip"]]
        need = int(s["frames"]) / float(fps)
        start = window(clip, need, sl["turn"])
        files[i] = own_media.render_clip(clip["path"], start, int(s["frames"]), out_size, work / "clips" / f"clip{i:02d}.mp4", fps=fps)
        s.update({"own": True, "speed": 1.0, "source": Path(clip["path"]).name, "label": names[sl["clip"]],
                  "clip_start": start, "effects": [e for e in (s.get("effects") or []) if e.get("type") == "punch"]})
        s.pop("ease", None)
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
    # 3. the cut, as an object cut is composed: the look, the knobs, the beat FX, the boundary kinds, the effects
    report("assemble", 0.6, "Cutting to the beat" + (" with beat FX" if opt["fx"] else ""))
    m = dense.macros(state)
    plan_shots = copy.deepcopy(shots)
    dense.apply_macros(shots, m, hp if vertical_house else None)
    timing_mode = _mt.normal(state.get("morph_timing"))
    _mt.plan(shots, timing_mode, directed.get("beats") or [], plan.get("drop"))
    effect_names = _E.names_of(state)
    smear = _E.smear_setting(state)
    from xenoform import boundary_fx as _B

    boundary_fx = _B.pick(shots, m, directed.get("beats") or [], fps, seed=seed, premium=None, drop=plan.get("drop"), smear=smear)
    look_preset = beatfx.resolve_dance_preset(opt["dance_fx"], vibe, hp)
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
                          tones=_E.palette_from_clips(clips).tolist() if _E.wants_tones(look_preset, effect_names, shots) else None)
    card = None
    if opt["end_card"]:
        report("assemble", 0.96, "Burning the end card")
        card = beatfx.end_card(tmp, opt["recipe"] or "(none)")
    report("assemble", 0.98, "Saving the video")
    shutil.copyfile(tmp, out_path)
    engine_name = {"ltx23": "LTX-2.3 morphs between your clips (Final)", "mock": "mock cross-fades (test)"}.get(
        engine, "LTX 0.9.5 morphs between your clips" + (", upscaled (Fast Final)" if opt.get("fast") else " (Draft)"))
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
            | {"foreshadow": "off"},  # no next object to foreshadow: the next picture is footage
            "handoffs_s": [s["start"] for s in shots] + [shots[-1]["end"]], "fallbacks": notes,
            "beats": [round(float(b), 4) for b in (directed.get("beats") or [])], "render": made["size"],
            "frames": made["frames"], "seconds": round(time.perf_counter() - started, 2), "look": made.get("look") or {},
            "macros": m, "handoffs": made.get("boundary_fx"), "house": str(hp.get("name") or ""),
            "stems_path": str(state.get("stems_path") or "")}
    (work / "simple.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
    return info
