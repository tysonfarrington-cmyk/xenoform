"""Simple-mode recipe codes: one short string that reproduces a Simple video.

``xf1.<base64url(zlib(json))>``. It carries the vibe, idea line, seed, energy preset,
aspect, quality tier, finishing switches and an optional cut plan, so anyone with the
same song gets the same film, and can paste it to remix. Unknown keys are dropped;
values are clamped to what the desk offers.
"""

from __future__ import annotations

import base64
import json
import zlib

PREFIX = "xf1."
ENERGY = ("flow", "dense")
ASPECTS = ("16:9", "9:16", "1:1")
TIERS = ("draft", "fast", "final", "cloud")
FORESHADOW = ("auto", "off", "trace", "negative", "slices", "silhouette")
MAX_LEN = 6000


class RecipeError(ValueError):
    pass


def _morphs(value) -> int | str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "auto"
    return max(1, min(120, n)) if n > 0 else "auto"


def _style(value) -> str:
    from xenoform.morph_style import normal

    return normal(value or "auto")


def _effects(state: dict) -> list[str]:
    from xenoform.effects import names_of

    return names_of(state)


def _timing(value) -> str:
    from xenoform.morph_timing import normal

    return normal(value)


def _breathe(state: dict) -> float:
    """The Breathe amount the cut was made at (0 off, 1 the bold profile, 0.5 the first one)."""
    from xenoform.pacing import breathe_amount

    return round(breathe_amount(state), 2)


def _drop_mode(state: dict) -> str:
    from xenoform.pacing import drop_mode_of

    return drop_mode_of(state)


def _clean(state: dict) -> dict:
    out = {
        "vibe": str(state.get("vibe") or "")[:40],
        "idea": str(state.get("idea") or state.get("brief") or "")[:170],
        "seed": int(state.get("seed") or 2727),
        "energy": state.get("energy_preset") if state.get("energy_preset") in ENERGY else "flow",
        "aspect": state.get("aspect") if state.get("aspect") in ASPECTS else "16:9",
        "tier": state.get("quality_tier") if state.get("quality_tier") in TIERS else "draft",
        "fx": bool(state.get("beat_fx", True)),
        "overlay": bool(state.get("beat_overlay")),
        "card": bool(state.get("end_card")),
        "vertical": state.get("vertical_mode") if state.get("vertical_mode") in ("native", "crop") else "auto",
        "morphs": _morphs(state.get("morph_count")),
        "foreshadow": str(state.get("foreshadow") or "auto").lower() if str(state.get("foreshadow") or "auto").lower() in FORESHADOW else "auto",
        "style": _style(state.get("morph_style")),  # how the morphs change (morph_style)
        "timing": _timing(state.get("morph_timing")),  # when the change happens inside each morph (morph_timing)
        "effects": _effects(state),  # the TouchDesigner-style effects and the blocky smear (xenoform.effects)
        "breathe": _breathe(state),  # the shape (xenoform.pacing): Breathe, and how the drops hit
        "drops": _drop_mode(state),
    }
    song = str(state.get("song") or "")[:80]
    if song:
        out["song"] = song
    plan = state.get("cut_plan")
    if isinstance(plan, dict) and plan.get("shots"):
        out["plan"] = {"shots": plan["shots"], **({"stills": plan["stills"]} if plan.get("stills") else {})}
    return out


_SHORT = {"vibe": "v", "idea": "i", "seed": "s", "energy": "e", "aspect": "a", "tier": "t", "fx": "f",
          "overlay": "o", "card": "c", "song": "g", "plan": "p", "vertical": "vm", "morphs": "n", "foreshadow": "fs",
          "style": "ms", "timing": "mt", "effects": "ef", "breathe": "br", "drops": "dm"}
# a code from before the shape keys made its cut with Breathe off and the Drops off (the cut as it was), so those are
# the codec's defaults: a new code carries the shape it was made in, an old one decodes to the cut it made
_DEFAULTS = {"idea": "", "seed": 2727, "energy": "flow", "aspect": "16:9", "tier": "draft", "fx": True,
             "overlay": False, "card": False, "vertical": "auto", "morphs": "auto", "foreshadow": "auto", "style": "auto",
             "timing": "smooth", "effects": [], "breathe": False, "drops": "off"}


def encode(state: dict) -> str:
    full = _clean(state)
    short = {_SHORT[k]: v for k, v in full.items() if _DEFAULTS.get(k, object()) != v}
    raw = json.dumps(short, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def decode(code: str) -> dict:
    """The desk state a code stands for (keys as the desk sends them)."""
    code = str(code or "").strip()
    if not code.startswith(PREFIX) or len(code) > MAX_LEN:
        raise RecipeError("That is not a Xenoform recipe code (they start with xf1.).")
    body = code[len(PREFIX):]
    try:
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))))
    except Exception as exc:  # noqa: BLE001
        raise RecipeError("That recipe code is damaged. Copy it again.") from exc
    if not isinstance(data, dict):
        raise RecipeError("That recipe code is damaged. Copy it again.")
    longer = {v: k for k, v in _SHORT.items()}
    data = {**_DEFAULTS, **{longer.get(k, k): v for k, v in data.items()}}
    clean = _clean({"vibe": data.get("vibe"), "idea": data.get("idea"), "seed": data.get("seed"),
                    "energy_preset": data.get("energy"), "aspect": data.get("aspect"),
                    "quality_tier": data.get("tier"), "beat_fx": data.get("fx", True),
                    "beat_overlay": data.get("overlay"), "end_card": data.get("card"), "song": data.get("song"),
                    "vertical_mode": data.get("vertical"), "cut_plan": data.get("plan"),
                    "morph_count": data.get("morphs"), "foreshadow": data.get("foreshadow"), "morph_style": data.get("style"),
                    "morph_timing": data.get("timing"), "effects": data.get("effects"),
                    "breathe": data.get("breathe"), "drop_mode": data.get("drops")})
    state = {"vibe": clean["vibe"], "idea": clean["idea"], "seed": clean["seed"], "energy_preset": clean["energy"],
             "aspect": clean["aspect"], "quality_tier": clean["tier"], "beat_fx": clean["fx"],
             "beat_overlay": clean["overlay"], "end_card": clean["card"], "song": clean.get("song", ""),
             "breathe": clean["breathe"], "drop_mode": clean["drops"]}
    if clean["morphs"] != "auto":
        state["morph_count"] = clean["morphs"]
    if clean["vertical"] != "auto":
        state["vertical_mode"] = clean["vertical"]
    if clean["foreshadow"] != "auto":
        state["foreshadow"] = clean["foreshadow"]
    if clean["style"] != "auto":
        state["morph_style"] = clean["style"]
    if clean["timing"] != "smooth":
        state["morph_timing"] = clean["timing"]
    if clean["effects"]:
        state["effects"] = clean["effects"]
    if "plan" in clean:
        from xenoform.cloud_morph import CutPlanError, custom_shots

        try:
            custom_shots(clean["plan"])
        except (CutPlanError, KeyError, TypeError, ValueError) as exc:
            raise RecipeError(f"The cut plan inside that code does not render: {exc}") from exc
        state["cut_plan"] = clean["plan"]
    return state
