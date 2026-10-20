"""Guardrails: stop known causes of flaky output before a render.

One place for every rule (configs/guardrails.json). ``apply(body)`` returns a
cleaned copy of the render settings plus a report. The desk (/api/generate),
the MCP tools and the CLI all call it. ``expert=True`` keeps the user's values
and turns each clamp into a warning, except hard bans (shimmer, the T5 encoder
on LTX-2.x) which always apply.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "guardrails.json"


def load(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 0, "rules": {}}


def rules(path: str | Path | None = None) -> dict:
    return load(path).get("rules") or {}


def summary() -> list[dict]:
    """One line per guardrail with its defaults, for the desk, MCP and CLI."""
    out = []
    for rid, r in rules().items():
        defaults = {k: v for k, v in r.items() if k != "why"}
        out.append({"id": rid, "why": r.get("why", ""), "defaults": defaults, "hard": bool(r.get("hard"))})
    return out


def _words(*texts: Any) -> str:
    return " ".join(str(t or "") for t in texts).lower()


def _has(text: str, words) -> list[str]:
    import re
    return [w for w in words if re.search(r"\b" + re.escape(w) + r"\b", text)]


class Report:
    def __init__(self, expert: bool):
        self.expert = expert
        self.applied: list[dict] = []
        self.warnings: list[dict] = []

    def clamp(self, rid: str, msg: str, hard: bool = False) -> bool:
        """Record a fix. Returns True when the fix should be applied."""
        if self.expert and not hard:
            self.warnings.append({"id": rid, "message": msg + " (expert override: kept your value)"})
            return False
        self.applied.append({"id": rid, "message": msg})
        return True

    def warn(self, rid: str, msg: str) -> None:
        self.warnings.append({"id": rid, "message": msg})

    def as_dict(self) -> dict:
        return {"expert": self.expert, "applied": self.applied, "warnings": self.warnings,
                "messages": [f"[{x['id']}] {x['message']}" for x in self.applied + self.warnings]}


def _add_negative(body: dict, text: str) -> None:
    cur = str(body.get("negative_extra") or "")
    if text not in cur:
        body["negative_extra"] = (cur + ", " + text).strip(", ") if cur else text


def apply(body: dict | None, *, expert: bool | None = None, duration: float | None = None,
          beats: list | None = None, vram_gb: float | None = None, cfg: dict | None = None,
          path: str | Path | None = None) -> tuple[dict, dict]:
    """Validate and auto-clamp render settings. Returns (clean_body, report)."""
    body = copy.deepcopy(body or {})
    expert = bool(body.get("expert") if expert is None else expert)
    R = rules(path)
    rep = Report(expert)
    blocks = [b for b in (body.get("blocks") or []) if isinstance(b, dict)]
    text = _words(body.get("prompt"), body.get("idea"), body.get("vibe"),
                  " ".join(str(b.get("form") or "") for b in blocks),
                  " ".join(str(c.get("noun") or c.get("name") or "") for c in body.get("customs") or [] if isinstance(c, dict)))
    duration = float(duration if duration is not None else body.get("duration") or 0) or None

    # shimmer: hard ban
    r = R.get("shimmer")
    if r:
        banned = r.get("banned") or []
        tr = [t for t in body.get("transitions") or [] if isinstance(t, str)]
        bad = [t for t in tr if any(b in t.lower() for b in banned)]
        if bad and rep.clamp("shimmer", f"removed banned looks {bad}", hard=True):
            body["transitions"] = [t for t in tr if t not in bad]
        for b in blocks:
            if any(x in str(b.get("transition") or "").lower() for x in banned):
                rep.clamp("shimmer", f"block transition {b.get('transition')} is banned; set to dissolve", hard=True)
                b["transition"] = "dissolve"
        for key in ("look", "post_fx", "preset"):
            if any(x in str(body.get(key) or "").lower() for x in banned):
                rep.clamp("shimmer", f"{key} '{body.get(key)}' is banned; cleared", hard=True)
                body[key] = ""

    # transition variety: classic wipes expert-only, max 2 of any one type, overflow -> clean cut
    r = R.get("transition_variety")
    st = body.get("scene_transitions")
    if r and isinstance(st, list) and st:
        from xenoform import transitions_fx as _T
        kinds = [t.get("kind") if isinstance(t, dict) else t for t in st]
        new, msgs = _T.guard(kinds, expert=expert)
        for m in msgs:
            rep.clamp("transition_variety", m) if not expert else rep.warn("transition_variety", m)
        if not expert:
            body["scene_transitions"] = [dict(t, kind=k) if isinstance(t, dict) else k for t, k in zip(st, new)]

    # morph density
    r = R.get("morph_density")
    if r and duration:
        cap = max(1, int(round(duration / 20.0 * float(r.get("max_forms_per_20s", 15)))))
        hard_cap = max(cap, int(round(duration / 20.0 * float(r.get("hard_max_forms_per_20s", 18)))))
        mc = body.get("morph_count", "auto")
        n = None
        if mc in (None, "", "auto", 0, "0"):
            try:
                from xenoform import dense
                n = dense.resolve_morph_count(body, duration, beats or body.get("beats") or [])
            except Exception:
                n = None
            if n and n > cap:
                rep.clamp("morph_density", f"auto picked {n} forms for {duration:.0f}s; capped at {cap} (~15 per 20 s)") and body.__setitem__("morph_count", cap)
        else:
            try:
                n = int(mc)
            except (TypeError, ValueError):
                n = None
            if n and n > hard_cap:
                if rep.clamp("morph_density", f"{n} forms in {duration:.0f}s reads as laggy; clamped to {cap} (~15 per 20 s)"):
                    body["morph_count"] = cap
            elif n and n > cap:
                rep.warn("morph_density", f"{n} forms in {duration:.0f}s is above the ~{cap} sweet spot")

    # clean morph runs
    r = R.get("morph_run_clean")
    if r:
        strip = set(r.get("strip") or [])
        for b in blocks:
            fx = b.get("effects")
            if isinstance(fx, list):
                bad = [e for e in fx if isinstance(e, dict) and e.get("type") in strip]
                if bad and rep.clamp("morph_run_clean", f"removed {[e.get('type') for e in bad]} from a morph run"):
                    b["effects"] = [e for e in fx if e not in bad]
            if str(b.get("transition") or "") in strip and rep.clamp("morph_run_clean", f"'{b.get('transition')}' inside a morph run; set to morph"):
                b["transition"] = "morph"
        if body.get("morph_stutter") and rep.clamp("morph_run_clean", "mid-morph stutter off"):
            body["morph_stutter"] = False

    # simple objects
    r = R.get("simple_objects")
    if r and blocks:
        simple = set(r.get("simple") or [])
        hits = [b.get("form") for b in blocks if str(b.get("form") or "").lower() in simple]
        if hits and len(hits) / len(blocks) > float(r.get("max_share", 0.34)):
            rep.warn("simple_objects", f"{len(hits)}/{len(blocks)} forms are simple objects {sorted(set(map(str, hits)))}; they morph boringly, try complex shapes")
    elif r and _has(text, r.get("simple") or []) and not blocks:
        rep.warn("simple_objects", f"simple object in the idea ({', '.join(_has(text, r['simple']))}); pair it with complex shapes")

    # duplicate features
    r = R.get("duplicate_features")
    if r:
        hit = _has(text, r.get("subjects") or [])
        if hit:
            if body.get("anchor") not in (r.get("anchor"),) and rep.clamp("duplicate_features", f"{hit[0]} anchored on NASA images to stop duplicate features"):
                body["anchor"] = r.get("anchor")
            _add_negative(body, r.get("negative", ""))

    # character motion
    r = R.get("character_motion")
    if r:
        hit = _has(text, r.get("subjects") or [])
        if hit or body.get("character"):
            src = body.get("motion_source")
            if src != r.get("motion_source") and rep.clamp("character_motion", f"character ({(hit or ['character'])[0]}): motion driven by stock dance clips, not free poses"):
                body["motion_source"] = r.get("motion_source")
            _add_negative(body, r.get("negative", ""))

    # footage motion
    r = R.get("footage_motion")
    if r:
        lo = float(r.get("min_motion_score", 0.15))
        cur = body.get("min_motion_score")
        if cur is None or float(cur) < lo:
            if cur is None:
                body["min_motion_score"] = lo
            elif rep.clamp("footage_motion", f"min_motion_score {cur} lets near-static clips through; raised to {lo}"):
                body["min_motion_score"] = lo

    # native vertical
    r = R.get("native_vertical")
    if r and str(body.get("aspect") or "") == "9:16":
        if str(body.get("vertical_mode") or "auto") != "native" and rep.clamp("native_vertical", f"9:16 was '{body.get('vertical_mode') or 'auto'}' (wide crop); render native {r['width']}x{r['height']} + upscale"):
            body["vertical_mode"] = "native"
        body.setdefault("upscaler", r.get("upscaler"))

    # morph background
    r = R.get("morph_background")
    if r and blocks:
        if black_ground_vibe(body.get("vibe")):
            bg = str(body.get("still_background") or r.get("background"))
            if bg != r.get("background") and rep.clamp("morph_background", f"morph stills on '{bg}'; set to black"):
                bg = r.get("background")
            body["still_background"] = bg

    # text encoder (hard: wrong dims crash or give noise)
    r = R.get("text_encoder")
    if r and cfg:
        comfy = cfg.get("comfy") or {}
        model = _words(comfy.get("checkpoint_name"), comfy.get("video_model"))
        enc = str(comfy.get("clip_name") or comfy.get("text_encoder") or "")
        if _has_sub(model, r.get("ltx2_models") or []) and _has_sub(enc.lower(), r.get("bad") or []):
            if rep.clamp("text_encoder", f"{enc} (T5, 4096) on LTX-2.x (Gemma, 2048); switched to {r['ltx2_encoder']}", hard=True):
                comfy["clip_name"] = r["ltx2_encoder"]

    # VRAM
    r = R.get("vram")
    gb = vram_gb if vram_gb is not None else body.get("vram_gb")
    if r and gb and float(gb) <= float(r.get("gb", 12)):
        w, h = int(body.get("width") or 0), int(body.get("height") or 0)
        if w and h and w * h > int(r["max_pixels"]) and rep.clamp("vram", f"{w}x{h} on {gb} GB will OOM; using 448x768 (upscale after)"):
            body["width"], body["height"] = (448, 768) if h >= w else (768, 448)
        rs = body.get("render_s")
        if rs and float(rs) > float(r["max_render_s"]) and rep.clamp("vram", f"render_s {rs} on {gb} GB; capped at {r['max_render_s']}"):
            body["render_s"] = r["max_render_s"]
        par = body.get("parallel")
        if par and int(par) > int(r["max_local_parallel"]) and not body.get("cloud_backend") and rep.clamp("vram", "parallel local jobs on 12 GB; set to 1"):
            body["parallel"] = int(r["max_local_parallel"])

    # UI effects
    r = R.get("ui_effects")
    if r:
        kinds = set(r.get("ui_kinds") or [])
        wobbles = 0
        for b in blocks:
            ui = str(b.get("kind") or b.get("source") or "").lower() in kinds or bool(b.get("ui"))
            if ui:
                fi = b.get("fx_intensity")
                if fi is not None and float(fi) > r["max_fx_intensity"] and rep.clamp("ui_effects", f"FX {fi} on an app shot; turned down to {r['max_fx_intensity']}"):
                    b["fx_intensity"] = r["max_fx_intensity"]
            wb = b.get("wobble")
            if wb:
                wobbles += 1
                lim = r["max_wobble"] if ui else max(r["max_wobble"], 0.2)
                if float(wb) > lim and rep.clamp("ui_effects", f"wobble {wb} too strong; {lim}"):
                    b["wobble"] = lim
                if wobbles > int(r["max_wobble_moments"]) and rep.clamp("ui_effects", f"more than {r['max_wobble_moments']} wobble moments; extra wobble removed"):
                    b["wobble"] = 0
        if body.get("ui_shot") and body.get("fx_intensity") is not None and float(body["fx_intensity"]) > r["max_fx_intensity"]:
            if rep.clamp("ui_effects", f"FX {body['fx_intensity']} on an app shot; {r['max_fx_intensity']}"):
                body["fx_intensity"] = r["max_fx_intensity"]

    # no repeats: one use per source within a video
    r = R.get("no_repeat")
    if r:
        for key in ("segments", "footage", "clips"):
            rows = body.get(key)
            if not isinstance(rows, list):
                continue
            seen, keep, dups = set(), [], []
            for row in rows:
                src = str((row or {}).get("src") or (row or {}).get("path") or (row or {}).get("id") or "") if isinstance(row, dict) else str(row)
                k = (src.lower(), str((row or {}).get("phash") or "") if isinstance(row, dict) else "")
                if src and (src.lower() in {x[0] for x in seen} or (k[1] and k[1] in {x[1] for x in seen})):
                    dups.append(src)
                    continue
                seen.add(k)
                keep.append(row)
            if dups and rep.clamp("no_repeat", f"{len(dups)} repeated source(s) in {key} removed ({', '.join(Path(d).name for d in dups[:3])})"):
                body[key] = keep

    # character sparing
    r = R.get("character_sparing")
    if r and duration:
        match = [m.lower() for m in r.get("match") or []]
        t, count = 0.0, 0
        rows = blocks if blocks else [x for x in body.get("segments") or [] if isinstance(x, dict)]
        for row in rows:
            dur = float(row.get("hold") or row.get("dur") or 0.0)
            name = _words(row.get("form"), row.get("src"), row.get("kind"), row.get("name"), row.get("title"))
            if row.get("character") or any(m in name for m in match):
                count += 1
                early = t < float(r.get("not_before_frac", 0.15)) * duration
                over = count > int(r.get("max_appearances", 3))
                if (early or over) and rep.clamp("character_sparing",
                        f"character shot at {t:.1f}s {'in the opening 15%' if early else 'over the ' + str(r['max_appearances']) + '-appearance cap'}; dropped"):
                    row["_drop"] = True
                    count -= 1
            t += dur
        if blocks:
            blocks[:] = [b for b in blocks if not b.pop("_drop", False)]
        elif body.get("segments"):
            body["segments"] = [x for x in body["segments"] if not (isinstance(x, dict) and x.pop("_drop", False))]

    # beat alignment: snap explicit cut times
    r = R.get("beat_alignment")
    grid = beats or body.get("beats") or []
    if r and grid and isinstance(body.get("cuts"), list) and body["cuts"]:
        from xenoform.post_qa import snap_cuts
        snapped = snap_cuts(body["cuts"], grid, float(r["tolerance_s"]), float(r["max_snap_s"]))
        moved = sum(1 for a, b in zip(body["cuts"], snapped) if abs(float(a) - b) > 1e-6)
        if moved and rep.clamp("beat_alignment", f"{moved} cut(s) more than {int(r['tolerance_s'] * 1000)} ms off the beat snapped"):
            body["cuts"] = snapped

    # kaleidoscope: expert only
    r = R.get("kaleidoscope")
    if r:
        tr = [t for t in body.get("transitions") or [] if isinstance(t, str)]
        if (body.get("kal") or any("kaleid" in t.lower() for t in tr)) and rep.clamp("kaleidoscope", "kaleidoscope is retired (expert only); off"):
            body["kal"] = 0
            body["transitions"] = [t for t in tr if "kaleid" not in t.lower()]

    # open weights
    r = R.get("open_weights")
    if r:
        ow = body.get("open_weights_only", r.get("contest_mode", True))
        body["open_weights_only"] = bool(ow)
        if ow and (body.get("paid_cloud") or body.get("cloud_quality")):
            if rep.clamp("open_weights", "partner/API node (hosted LTX-2.5) is not open weights; paid cloud turned off in contest mode"):
                body["paid_cloud"] = False
                body["cloud_quality"] = False
                body["cloud_confirm"] = ""
            else:
                body["open_weights_only"] = False
                rep.warn("open_weights", "this render is NOT contest-eligible (partner node)")

    body["blocks"] = blocks if "blocks" in body else body.get("blocks")
    if body["blocks"] is None:
        body.pop("blocks")
    body.pop("expert", None)
    out = rep.as_dict()
    body["guardrails"] = out
    return body, out


def _has_sub(text: str, subs) -> bool:
    return any(s in text for s in subs)


def check_config(cfg: dict) -> dict:
    """Config-level checks for the CLI pipeline (text encoder)."""
    _, rep = apply({}, cfg=cfg)
    return rep


_VRAM: list = []


def cached_vram() -> float | None:
    """Detected GPU memory, looked up once per process."""
    if not _VRAM:
        try:
            from xenoform.hardware import detect_vram_gb
            _VRAM.append(detect_vram_gb())
        except Exception:
            _VRAM.append(None)
    return _VRAM[0]


# ------------------------------------------------------------ consumers
# The render code calls these so each guardrail field changes the output.

HINTS = {
    "nasa": "photographic, faithful to NASA reference imagery, one single accurate subject, physically correct features",
    "stock-dance": "motion follows a real stock dance reference clip, smooth continuous movement, natural anatomically correct hands",
    "black": "pure black background",
}


def black_ground_vibe(vibe: Any) -> bool:
    """True for vibes whose morph stills sit on black (the black pool, or a still_style on black)."""
    v = str(vibe or "").strip()
    if v in ("", "black"):
        return True
    try:
        from xenoform import vibes as _v
        info = _v.get(v) or {}
    except Exception:
        return False
    return "black" in str(info.get("still_style") or info.get("look") or "").lower()


def prompt_hint(state: dict | None) -> str:
    st = state or {}
    parts = []
    if st.get("anchor") in HINTS:
        parts.append(HINTS[st["anchor"]])
    if st.get("motion_source") in HINTS:
        parts.append(HINTS[st["motion_source"]])
    if st.get("still_background") == "black":
        parts.append(HINTS["black"])
    return ", ".join(parts)


def _subject_text(state: dict | None) -> str:
    st = state or {}
    return " ".join(str(st.get(k) or "") for k in ("prompt", "idea"))


def guard_prompt(prompt: str, state: dict | None) -> str:
    hint = prompt_hint(state)
    prompt = str(prompt or "")
    if (state or {}).get("anchor") == "nasa":
        try:  # the named real subject's NASA anchor prompt (configs/anchors.json)
            from xenoform.anchors import harden
            prompt = harden(prompt, _subject_text(state) + " " + prompt)
        except Exception:
            pass
    if not hint or hint in prompt:
        return prompt
    return (prompt.rstrip().rstrip(".") + ", " + hint + ".").lstrip(", ")


def negative_for(base: str, state: dict | None) -> str:
    extra = str((state or {}).get("negative_extra") or "").strip()
    base = str(base or "")
    if (state or {}).get("anchor") == "nasa":
        try:
            from xenoform.anchors import harden_negative
            base = harden_negative(base, _subject_text(state))
        except Exception:
            pass
    if not extra:
        return base
    new = [t.strip() for t in extra.split(",") if t.strip() and t.strip().lower() not in base.lower()]
    return ", ".join([base.rstrip(", ")] + new) if base else ", ".join(new)


def guard_prompts(prompts: dict, state: dict | None) -> dict:
    """The director's prompt table: hints on every positive prompt, extras on the negative."""
    out = {}
    for k, v in (prompts or {}).items():
        out[k] = negative_for(v, state) if k == "negative" else guard_prompt(v, state) if isinstance(v, str) else v
    if "negative" not in out and (state or {}).get("negative_extra"):
        out["negative"] = negative_for("", state)
    return out


def motion_ok(item: dict, min_score: float) -> bool:
    """Footage picker: drop near-static clips. Stills (no motion data) always pass."""
    if not min_score:
        return True
    kind = str(item.get("kind") or item.get("type") or "").lower()
    if kind in ("image", "still", "photo"):
        return True
    if item.get("motion_score") is not None:
        return float(item["motion_score"]) >= float(min_score)
    if item.get("motion_level") is None and not item.get("motion"):
        return True
    from xenoform.source_library import motion_level
    return motion_level(item) >= float(min_score)


def shot_fx(shot: dict | None) -> tuple[float, float]:
    """(fx intensity 0..1, wobble 0..1) for one shot; defaults are full FX, no wobble."""
    s = shot or {}
    try:
        inten = float(s.get("fx_intensity", 1.0))
    except (TypeError, ValueError):
        inten = 1.0
    try:
        wob = float(s.get("wobble") or 0.0)
    except (TypeError, ValueError):
        wob = 0.0
    return max(0.0, min(1.0, inten)), max(0.0, min(1.0, wob))


def carry_block_fx(shots: list[dict], state: dict | None) -> list[dict]:
    """Copy per-block fx_intensity / wobble onto the shot with the same index."""
    blocks = [b for b in ((state or {}).get("blocks") or []) if isinstance(b, dict)]
    out = []
    for i, shot in enumerate(shots):
        b = blocks[i] if i < len(blocks) else {}
        extra = {k: b[k] for k in ("fx_intensity", "wobble") if k in b and k not in shot}
        out.append({**shot, **extra} if extra else shot)
    return out


# ------------------------------------------------------------ no-repeat / character helpers
def dhash(img) -> str:
    """64-bit difference hash of an RGB/gray frame (hex)."""
    import numpy as np
    g = np.asarray(img, dtype=np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    h, w = g.shape
    ys = (np.arange(8) * h / 8).astype(int)
    xs = (np.arange(9) * w / 9).astype(int)
    small = g[np.ix_(ys, xs)]
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return "%016x" % int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except (TypeError, ValueError):
        return 64


class SourceTracker:
    """One use per source (path) and per look (perceptual hash) within a video."""

    def __init__(self, max_hamming: int | None = None):
        r = rules().get("no_repeat") or {}
        self.max_hamming = int(r.get("max_hamming", 6) if max_hamming is None else max_hamming)
        self.sources: set[str] = set()
        self.hashes: list[str] = []

    def seen(self, src: str, phash: str | None = None) -> bool:
        if str(src).lower() in self.sources:
            return True
        return bool(phash) and any(hamming(phash, h) <= self.max_hamming for h in self.hashes)

    def add(self, src: str, phash: str | None = None) -> None:
        self.sources.add(str(src).lower())
        if phash:
            self.hashes.append(phash)


def is_character(item: dict) -> bool:
    r = rules().get("character_sparing") or {}
    if item.get("character"):
        return True
    text = _words(item.get("title"), item.get("id"), item.get("src"), item.get("path"), " ".join(item.get("tags") or []))
    return any(m in text for m in r.get("match") or [])
