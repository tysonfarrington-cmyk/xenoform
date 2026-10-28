"""How A becomes B: the morph styles (docs/MORPH_ENGINE_PLAN.md E1).

Every morph used to run on one prompt, "one single sculptural object slowly melts and flows into another", so every
transformation in every cut was a melt. A style swaps that opening for another way the object changes; the two guide
stills, the vibe's look, the seed and the rest of the prompt stay as they were. The Draft test of eight styles on two
pairs with the same seed (28 Oct, the sheets and the reel in the plan's section 4a) kept the four that read as their own
on film, and Tys shipped them beside Melt: **Shatter** (a burst of shards that snap together), **Bloom** (petals or wings
unfolding), **Spin** (a swirl, the most motion of the five) and **Fold** (flat planes and creases). Smoke, Ink and Pour
read too close to Melt and were left out.

A cut takes one setting (``morph_style`` in the make body: ``auto`` or a style for every morph) and the timeline sets a
shot's own (a re-render of that morph, ``dense.rerender_morph(style=)``). **Auto** follows the song and the Chaos knob:
Melt through the verses and Shatter on the drop; under Chaos 0.6 the opening morph Blooms; from 0.6 the builds Fold and
every other loud shot after the drop Spins; at Chaos 0.15 or less everything melts. A pair that touches a scene keeps
the scene prompt (``morph_pass.SCENE_OPENINGS``): a style is how an object changes, and a wide frame told to shatter
drops its scene at frame 1.

- ``STYLES``, ``OPENINGS``, ``LABELS``, ``NOTES``: the five, their prompt openings, the desk's names and one-line notes
- ``normal(value)``: a known style; ``auto`` stays ``auto`` where it is allowed; anything else is Melt
- ``auto(shots, drop, chaos)``: one style a shot by the rules above
- ``for_cut(state, shots, drop)``: the cut's styles: the shot list the body carries (Render at Final keeps a prototype's
  styles), else the setting, else Auto
"""
from __future__ import annotations

STYLES = ("melt", "shatter", "bloom", "spin", "fold")
OPENINGS = {
    "melt": "One single sculptural object slowly melts and flows into another, one continuous liquid transformation",
    "shatter": "One single sculptural object cracks and shatters into hundreds of glittering shards that swirl and snap "
               "together into another object, one continuous transformation",
    "bloom": "One single sculptural object unfolds like a blooming flower, its petals opening and peeling back as another "
             "object grows out of its centre, one continuous organic transformation",
    "spin": "One single sculptural object spins fast on its axis and changes shape as it turns, slowing to reveal another "
            "object, one continuous transformation",
    "fold": "One single sculptural object folds and creases like paper origami, its flat planes flipping and refolding "
            "into another object, one continuous transformation",
}
LABELS = {"auto": "Auto", "melt": "Melt", "shatter": "Shatter", "bloom": "Bloom", "spin": "Spin", "fold": "Fold"}
NOTES = {
    "auto": "Melt through the verses, Shatter on the drop; the opening Blooms, or with Chaos past 0.6 the builds Fold and "
            "the loud shots after the drop Spin.",
    "melt": "The object melts and flows into the next: one continuous liquid change.",
    "shatter": "The object cracks into shards that swirl and snap together as the next.",
    "bloom": "The object opens like a flower, and the next grows out of its centre.",
    "spin": "The object spins and changes shape as it turns: the most motion.",
    "fold": "The object folds like paper, its planes flipping into the next.",
}
CALM_CHAOS = 0.15   # at or under: every morph melts
WILD_CHAOS = 0.6    # from here: builds fold and the shots after the drop spin; under it the opening blooms
LOUD = ("drop", "drop_late", "build")


def normal(value, allow_auto: bool = True) -> str:
    v = str(value or "").strip().lower()
    if v == "auto" and allow_auto:
        return "auto"
    return v if v in STYLES else "melt"


def drop_index(shots: list[dict], drop: float | None) -> int | None:
    """The shot whose morph plays as the drop hits: the one that starts on it, else the first that starts after it."""
    if drop is None or not shots:
        return None
    d = float(drop)
    for i, s in enumerate(shots):
        if float(s.get("start") or 0.0) >= d - 0.05:
            return i
    return None


def _building(shot: dict, drop: float | None) -> bool:
    if str(shot.get("section") or "") == "build":
        return True
    return drop is not None and float(shot.get("start") or 0.0) < float(drop) and abs(float(shot.get("end") or 0.0) - float(drop)) < 0.05


def _loud(shot: dict, drop: float | None) -> bool:
    section = str(shot.get("section") or "")
    if section:
        return section in LOUD
    return drop is not None and float(shot.get("start") or 0.0) >= float(drop) - 1e-3


def auto(shots: list[dict], drop: float | None = None, chaos: float = 0.3) -> list[str]:
    n = len(shots)
    styles = ["melt"] * n
    if not n or float(chaos) <= CALM_CHAOS:
        return styles
    d = drop_index(shots, drop)
    if d is not None:
        styles[d] = "shatter"
    if float(chaos) >= WILD_CHAOS:
        for i, s in enumerate(shots):
            if styles[i] != "melt":
                continue
            if (d is None or i < d) and _building(s, drop):
                styles[i] = "fold"
            elif d is not None and i > d and (i - d) % 2 == 0 and _loud(s, drop):
                styles[i] = "spin"
    elif n > 1 and styles[0] == "melt":
        styles[0] = "bloom"
    return styles


def for_cut(state: dict, shots: list[dict], drop: float | None = None) -> list[str]:
    state = state or {}
    given = state.get("morph_styles")
    if isinstance(given, list) and given and len(given) == len(shots):
        return [normal(s, allow_auto=False) for s in given]
    setting = normal(state.get("morph_style") or "auto")
    if setting != "auto":
        return [setting] * len(shots)
    macros = state.get("macros") if isinstance(state.get("macros"), dict) else {}
    chaos = float(macros.get("chaos", 0.3)) if macros.get("chaos") is not None else 0.3
    return auto(shots, drop, chaos)


def info(styles: list[str]) -> dict:
    """``{"shatter": 1, "bloom": 1, "melt": 7}`` for the record's notes."""
    out: dict[str, int] = {}
    for s in styles:
        out[s] = out.get(s, 0) + 1
    return out
