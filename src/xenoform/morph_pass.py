"""Simple mode's GPU pass: per-scene stills chained as A->B guided morphs.

Each scene is one LTX 0.9.5 morph from still i to still i+1 through
``workflows/xenoform_morph.json`` (two LTXVAddGuide endpoints, 512x288),
submitted with comfy-sdk through comfy-api-proxy. Morph i ends on the exact
still morph i+1 starts from, so every handoff is continuous, and every handoff
sits on a scene boundary snapped to the beat grid.

The stills are a curated set per vibe in ``ui_static/objects`` (library
objects regraded per vibe; paper-summer was made once with Z-Image Turbo).
Nothing is generated at run time except the morphs.
"""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import os

import numpy as np

log = logging.getLogger("xenoform.morph_pass")

OBJECTS = Path(__file__).resolve().parent / "ui_static" / "objects"
GRAPH = Path(__file__).resolve().parents[2] / "workflows" / "xenoform_morph.json"
FPS = 24
_size = os.environ.get("XENO_MORPH_SIZE", "512x288").lower().split("x")
WIDTH, HEIGHT = int(_size[0]), int(_size[1])
STEPS = int(os.environ.get("XENO_MORPH_STEPS", "20"))
MIN_LEN, MAX_LEN = 25, 121
OUT_W, OUT_H = max(768, WIDTH), max(432, HEIGHT)  # lanczos upscale for playback; the render is WIDTH x HEIGHT

GRAPH25 = GRAPH.with_name("ltx25_morph_api.json")
# Files the LTX-2.5 morph needs (the official ComfyUI FLF2V template's low-VRAM set,
# from the gated Hugging Face repo Lightricks/LTX-2.5).
LTX25_FILES = (
    ("diffusion_models", "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"),
    ("text_encoders", "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"),
    ("vae", "ltx-2.5-video-vae-bf16.safetensors"),
    ("vae", "ltx-2.5-audio-vae-bf16.safetensors"),
)

VIBE_LOOK = {
    "liquid-gold": "molten gold and liquid mercury, warm amber studio glow, dark umber backdrop",
    "bloom": "iridescent petals and pearly glass, soft magenta rim light, fresh spring-green backdrop",
    "neon-night": "rain-slick black glass and smoked chrome, hot magenta and sodium-amber neon reflections, deep crimson-black backdrop",
    "ocean": "iridescent shell and chrome, aqua caustic light, deep teal water backdrop",
    "cosmic": "iridescent glass and pearl, cobalt and violet glow, deep indigo backdrop",
    "paper-summer": "folded white paper and glazed porcelain, warm morning sunlight, soft cream backdrop",
    "black": "black glass and iridescent liquid metal, violet and teal edge light, pure black void, no floor",
}
from xenoform import vibes as _vibes  # noqa: E402

VIBE_LOOK.update({v["id"]: v["look"] for v in _vibes.extended() if v.get("look")})
PALETTE_VIBE = {"gold": "liquid-gold", "violet": "cosmic", "grey-green": "ocean", "bronze": "bloom", "neutral": "paper-summer"}
NEGATIVE = ("text, letters, watermark, logo, two objects, duplicated features, extra copies, cut, flicker, "
            "blurry, low quality, cartoon, cartoonish, warped, people, hands")


def manifest() -> dict[str, list[dict]]:
    """The shipped pools alone (``objects.json``); ``catalogue()`` is what the chain draws on."""
    return json.loads((OBJECTS / "objects.json").read_text(encoding="utf-8"))


def catalogue() -> dict[str, list[dict]]:
    """Every vibe's pool: the shipped stills and the ones grown on this machine (``stills.catalogue``), each
    row with its ``path``. A vibe with grown stills and no shipped ones counts as having a pool."""
    from xenoform import stills

    return stills.catalogue(manifest())


def vibe_for(state: dict) -> str:
    from xenoform import stills

    vibe = str(state.get("vibe") or "")
    pools = catalogue()
    if len(pools.get(vibe) or []) >= stills.MIN_POOL:  # one or two grown stills are not a pool yet: keep borrowing
        return vibe
    borrowed = _vibes.pool(vibe)
    if borrowed in pools:
        log.info("vibe %s has no stills of its own; borrowing the %s pool (look prompt stays %s)", vibe, borrowed, vibe)
        return borrowed
    if vibe:
        log.warning("vibe %r has no object pool and no declared fallback; using liquid-gold stills", vibe)
    if str(state.get("preset") or "") == "liquid-metal":
        return "liquid-gold"
    return PALETTE_VIBE.get(str(state.get("palette") or ""), "liquid-gold")


def _idea_words(state: dict) -> list[str]:
    """The words the user typed: the idea line and the brief. They name the family and the lead object before any
    other text does, so "a heron over the marsh" opens on the heron whatever the storyboard says."""
    text = " ".join(str(state.get(key) or "") for key in ("idea", "brief"))
    return re.findall(r"[a-z]+", text.lower().replace("_", " ").replace("-", " "))


def _story_words(state: dict) -> list[str]:
    bits = [str(state.get("brief") or ""), str(state.get("story") or ""), str(state.get("idea") or "")]
    # the Director storyboard's scene cards come with every Make; a Simple cut never renders them, so their words
    # must not steer its objects ("the rocket climbs past the bulb" named the fruit family on the demo, 26 Oct)
    if str(state.get("mode") or "") != "simple":
        for scene in state.get("scenes") or []:  # the Advanced desk's scene list; a string here is the Simple scenes choice
            if isinstance(scene, dict):
                bits += [str(scene.get(key) or "") for key in ("form", "action", "guide", "text")]
    for custom in state.get("customs") or []:
        bits.append(str(custom.get("noun") or custom.get("name") or ""))
    return re.findall(r"[a-z]+", " ".join(bits).lower().replace("_", " ").replace("-", " "))


AUTOTUNE = Path(__file__).resolve().parents[2] / "configs" / "autotune.json"


def autotune() -> dict:
    """Reviewed output of scripts/autotune (per-vibe settings and a bad-pair list), if installed."""
    path = Path(os.environ.get("XENO_AUTOTUNE", str(AUTOTUNE)))
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tuned(vibe: str) -> dict:
    """Per-vibe morph settings from autotune; an explicit XENO_MORPH_STEPS still wins for steps."""
    got = {**_vibes.ltx(vibe), **dict((autotune().get("vibes") or {}).get(vibe) or {})}
    if "XENO_MORPH_STEPS" in os.environ:
        got.pop("steps", None)
    return got


def _drop_bad_pairs(pool: list[dict], bad: set) -> list[dict]:
    """Reorder so no adjacent pair is on the autotune blocklist (either order), when a reorder can do it."""
    if not bad:
        return pool
    bad = set(bad) | {(b, a) for a, b in bad}
    out, rest = [pool[0]], list(pool[1:])
    while rest:
        nxt = next((o for o in rest if (out[-1]["file"], o["file"]) not in bad), rest[0])
        rest.remove(nxt)
        out.append(nxt)
    return out


def chain_walk(pool: list[dict], count: int) -> list[dict]:
    """``count`` stills from ``pool`` as a chain whose consecutive pairs, the closing pair back to the first
    included, repeat as late as possible. The first lap is the pool in order (as before); after that each step
    takes the least-used object whose pairing with the current one has not been seen, so a long song's 24
    morphs over 12 objects are 24 different pairings instead of the same 12 twice."""
    n = len(pool)
    if count <= 0:
        return []
    if count <= n or n < 3:
        return [pool[i % n] for i in range(count)]
    used: set[tuple[int, int]] = set()
    seen = [0] * n
    order = [0]
    seen[0] = 1
    for step in range(count - 1):
        cur = order[-1]
        last = step == count - 2
        cands = [j for j in range(n) if j != cur]
        fresh = [j for j in cands if (min(cur, j), max(cur, j)) not in used]
        if last:  # the chain closes on the first still: prefer an end whose pairing with it is fresh too
            closing = [j for j in fresh if (0, j) not in used and j != 0]
            fresh = closing or fresh
        choice = min(fresh or cands, key=lambda j: (seen[j], (j - cur) % n))
        used.add((min(cur, choice), max(cur, choice)))
        seen[choice] += 1
        order.append(choice)
    return [pool[i] for i in order]


SCENE_CHOICES = ("off", "mix", "only")
SCENE_EVERY = 4  # "mix" on a cut with no passage changes to follow: a scene opens it and returns every fourth still
THEME_CHAIN_MIN = 8  # a theme or named family with this many stills (or the whole chain) carries the chain alone


def scenes_choice(state: dict | None) -> str:
    """The Simple make body's ``scene_stills`` ("off" by default, "mix", "only"): whether the cut morphs scenes as
    well as objects. ``scenes`` as a string means the same (the list form of ``scenes`` is the Advanced desk's scene
    list and is left alone)."""
    raw = (state or {}).get("scene_stills")
    if raw is None and isinstance((state or {}).get("scenes"), str):
        raw = state["scenes"]
    text = str(raw or "off").strip().lower()
    return text if text in SCENE_CHOICES else "off"


BACKDROPS = ("plain", "places", "scenes")
# a vibe with this many settings cuts in its places unless the Backdrop row says otherwise: one shipped pool's worth, so
# the default 30 s cut does not fall to five long morphs over a first grow of six (a pool that small asks for places)
PLACES_DEFAULT_MIN = 12


def _vibe_rows(state: dict | None) -> list[dict]:
    """The catalogue rows a cut of ``state`` draws on: the pool vibe's, and the asked vibe's when it borrows."""
    pools = catalogue()
    vibe = vibe_for(state or {})
    asked = str((state or {}).get("vibe") or "")
    return list(pools.get(vibe) or []) + (list(pools.get(asked) or []) if asked and asked != vibe else [])


def backdrop_choice(state: dict | None, rows: list[dict] | None = None) -> str:
    """The Simple make body's ``backdrop``: what the morphs stand on. "plain" is an object on the vibe's studio ground (as
    every cut was), "places" an object standing in a place (``stills`` kind "setting"), "scenes" wide frames alone (the
    Scenes row's "only"). Not given (or "auto"): "scenes" when the old ``scene_stills`` says "only", else "places" when the
    vibe has ``PLACES_DEFAULT_MIN`` settings, else "plain". ``rows`` are the cut's catalogue rows when the caller has them."""
    raw = str((state or {}).get("backdrop") or "").strip().lower()
    if raw in BACKDROPS:
        return raw
    if scenes_choice(state) == "only":
        return "scenes"
    from xenoform import stills

    rows = _vibe_rows(state) if rows is None else rows
    n = sum(1 for r in rows if stills.kind_of(r) == "setting")
    return "places" if n >= PLACES_DEFAULT_MIN else "plain"


def scene_mode(state: dict | None, rows: list[dict] | None = None) -> str:
    """The Scenes choice the pick runs on: "only" when the Backdrop is "scenes", else ``scenes_choice`` (off, mix, only).
    The Scenes row's Mix still lands a scene on each passage change whatever the Backdrop puts between."""
    return "only" if backdrop_choice(state, rows) == "scenes" else scenes_choice(state)


def rows_of_kind(rows: list[dict], choice: str, backdrop: str = "plain") -> list[dict]:
    """The rows a cut may draw on under ``choice`` and ``backdrop``: scenes alone ("only", or the Backdrop "scenes"); else
    the stills the Backdrop stands the morphs on (objects for "plain", settings for "places", objects again when the vibe
    has no settings), with the scenes as well under "mix"."""
    from xenoform import stills

    if choice == "only" or backdrop == "scenes":
        return [r for r in rows if stills.kind_of(r) == "scene"]
    between = "setting" if backdrop == "places" and any(stills.kind_of(r) == "setting" for r in rows) else "object"
    want = {between, "scene"} if choice == "mix" else {between}
    return [r for r in rows if stills.kind_of(r) in want]


def scene_slots(shots: list[dict] | None, count: int, choice: str = "mix", assign: list | None = None) -> list[int]:
    """Which stills of a ``count``-still chain are scenes. Under "mix": the first still (the cut opens wide) and the
    still every passage change lands on, a shot with a ``boundary`` or a new ``section`` (its morph is ``assign[i]``
    when the long-song chain gives one, else ``i``, and morph ``m`` lands on still ``m``). A cut with no passage
    changes to follow (a short clip's dense plan) gets a scene every ``SCENE_EVERY`` stills. "only" is every still,
    "off" none."""
    count = int(count)
    if choice == "off" or count <= 0:
        return []
    if choice == "only":
        return list(range(count))
    slots = {0}
    found = False
    shots = list(shots or [])
    for i, shot in enumerate(shots):
        if i == 0:
            continue
        prev = shots[i - 1]
        change = bool(shot.get("boundary")) or (shot.get("section") is not None and shot.get("section") != prev.get("section"))
        if change:
            found = True
            k = int(assign[i]) if assign and i < len(assign) else i
            if 0 <= k < count:
                slots.add(k)
    if not found:
        slots.update(range(0, count, SCENE_EVERY))
    return sorted(slots)


def pins_of(state: dict | None) -> dict[int, str]:
    """The Simple make body's ``chain_pins``: the stills the user chose slot by slot on the Chain row, as a mapping
    of chain index to still file (``"cosmic/042_wolf_skull.jpg"``). Accepts a dict (``{"3": file}``) or a list with
    one entry a slot (``[null, null, file]``); an empty or malformed entry is no pin."""
    raw = (state or {}).get("chain_pins")
    pairs: list = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        pairs = list(enumerate(raw))
    out: dict[int, str] = {}
    for k, v in pairs:
        try:
            k = int(k)
        except (TypeError, ValueError):
            continue
        text = str(v or "").strip().replace("\\", "/") if isinstance(v, str) else str((v or {}).get("file") or "").strip() if isinstance(v, dict) else ""
        if k >= 0 and text:
            out[k] = text
    return out


PIN_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _pin_on_disk(f: str, vibe: str) -> dict | None:
    """A pinned file the catalogue does not list but the stills folder has (a still dropped in by hand, or pinned
    from another vibe's folder): a row for it, so the pin holds. Only an image inside the local or the shipped stills
    folder counts; anything else (a missing file, a path out of the folder) is None.

    Tys, 30 Oct: a Make over the API with two pinned stills that were on disk but not in ``stills.json`` rendered the
    None pool's shaker, kettle and lamp instead, with nothing but an info line in the log to say why."""
    from xenoform import stills

    for base, shipped in ((stills.root(), False), (stills.SHIPPED, True)):
        try:
            base = Path(base).resolve()
            path = (base / f).resolve()
        except (OSError, ValueError):
            continue
        if path.suffix.lower() in PIN_EXTS and path.is_file() and path.is_relative_to(base):
            noun = re.sub(r"^\d+_", "", path.stem).replace("_", " ").strip() or path.stem
            return {"file": f, "noun": noun, "path": str(path), "shipped": shipped, "_vibe": vibe}
    return None


def _pinned_rows(pins: dict[int, str], cat: dict, vibe: str, asked: str, count: int) -> dict[int, dict]:
    """The pinned slots resolved to catalogue rows (the vibe's pool, then the asked vibe's own, then any image in the
    stills folders the catalogue does not list: ``_pin_on_disk``): a slot past the chain's end, a file that is nowhere,
    or a file pinned twice (the lower slot keeps it) is dropped, with a warning."""
    by_file: dict[str, dict] = {}
    for under in ([vibe] + ([asked] if asked and asked != vibe else [])):
        for r in cat.get(under) or []:
            by_file.setdefault(str(r.get("file") or ""), {**r, "_vibe": under})
    out: dict[int, dict] = {}
    seen: set[str] = set()
    for k in sorted(pins):
        f = pins[k]
        if k >= count or f in seen:
            log.warning("chain pin %s: %s %s; the slot is picked as usual", k, f,
                        "is past the chain's end" if k >= count else "is pinned twice")
            continue
        row = by_file.get(f) or _pin_on_disk(f, vibe)
        if row is None:
            log.warning("chain pin %s: %s is not in the %s library or the stills folder; the slot is picked as usual", k, f, vibe)
            continue
        seen.add(f)
        out[k] = {**row, "pinned": True}
    return out


def pick_stills(state: dict, count: int, record: bool = True, scene_at: list[int] | None = None,
                pins: dict | None = None) -> tuple[str, list[dict]]:
    """``count`` stills for the vibe. A story noun that names a pool object leads; ``record`` marks the picks
    as used so the next cut prefers the others (``stills.mark_used``).

    Scenes (``scenes_choice``): "off" draws on objects alone, "only" on scene rows alone, "mix" puts a scene at
    each index in ``scene_at`` (``scene_slots``: the passage changes, else every fourth) and objects between, no
    still twice; past the scene rows the pool has, a slot is an object, and a pool with no scenes is objects only.

    Backdrop (``backdrop_choice``): "places" puts settings (an object standing in a place) where the objects would go,
    the family, theme and lead rules running on them as on objects; a vibe with no settings stays on its objects.
    "scenes" is "only". The user's own shapes and images lead as before, whatever the Backdrop.

    Pins (``pins``, else the body's ``chain_pins`` through ``pins_of``): a mapping of chain index to still file the
    user chose on the Chain row. A pinned slot holds that still whatever the order or the scene slots would have put
    there; the other slots are filled as they always were, from the pool without the pinned stills, so no still
    appears twice. The pinned rows come back with ``pinned`` True.

    Returns the *look* vibe (what the prompt, negative and tuning use) and the stills.
    A registry vibe without stills of its own borrows the pool ``vibes.pool()`` names,
    but keeps its own look, so "neon-noir" renders neon-night stills with the neon-noir prompt.
    """
    from xenoform import stills

    vibe = vibe_for(state)
    asked = str(state.get("vibe") or "")
    cat = catalogue()
    backdrop = backdrop_choice(state, list(cat.get(vibe) or []) + (list(cat.get(asked) or []) if asked and asked != vibe else []))
    choice = "only" if backdrop == "scenes" else scenes_choice(state)
    count = int(count)
    pins = pins_of({"chain_pins": pins}) if pins is not None else pins_of(state)
    held = _pinned_rows(pins, cat, vibe, asked, count)
    held_files = {str(r.get("file")) for r in held.values()}
    free_slots = [k for k in range(count) if k not in held]
    if scene_at is None and choice == "mix":
        scene_at = scene_slots(None, count, "mix")  # the default on the whole chain, before the pins take their slots
    if scene_at is not None:  # the scene slots the pins left, as indices into the free slots
        scene_at = [free_slots.index(int(k)) for k in scene_at if int(k) in free_slots]
    # the objects this vibe has used least first (a cut never laps a library bigger than itself, and the next cut
    # opens on objects the last one left alone), shipped order within; rows remember the vibe they are used under
    avoid_nouns = {str(n).strip().lower() for n in state.get("avoid_nouns") or []}  # a Stems layer: what the layers before
    held_files |= {str(f) for f in state.get("avoid_stills") or []} | {str(r.get("file")) for under in (vibe, asked)  # it used,
                   for r in cat.get(under) or [] if str(r.get("noun") or "").strip().lower() in avoid_nouns}  # by file and by name
    rows = [{**r, "_vibe": vibe} for r in stills.order_fresh(vibe, list(cat[vibe])) if str(r.get("file")) not in held_files]
    scene_rows = [r for r in rows if stills.kind_of(r) == "scene"]
    setting_rows = [r for r in rows if stills.kind_of(r) == "setting"]
    pool = [r for r in rows if stills.kind_of(r) == "object"]
    from xenoform import idea as _idea

    reading = _idea.reading_for(state)  # what the idea line asked for (xenoform.idea): its scenes and shapes lead
    # the user's own shapes lead when this cut asks for them: the line names them (its shapes, its theme's things) or
    # Your own shapes lists them. Any other is an ordinary still of the pool: a trophy, a pearl and an icicle grown for
    # one line used to open every neon-noir cut after it (Tys, 28 Oct: "this sequence doesnt make sense").
    asked_own = {stills.clean_noun(n) for n in list(reading.get("own") or []) + list(reading.get("objects") or [])
                 + list(reading.get("theme_things") or []) + stills.own_nouns(str(state.get("own_shapes") or ""))}
    own_rows = [r for r in pool if r.get("own")]
    pool = [r for r in pool if not r.get("own")]
    own = [r for r in own_rows if str(r.get("noun") or "").lower() in asked_own]
    pool = pool + [r for r in own_rows if str(r.get("noun") or "").lower() not in asked_own]
    # a vibe that borrows a pool (none or too few stills of its own) still leads with every still it does have, since
    # those are in its own material
    if asked != vibe and asked in cat:
        asked_rows = [{**r, "_vibe": asked} for r in stills.order_fresh(asked, list(cat[asked])) if str(r.get("file")) not in held_files]
        scene_rows = [r for r in asked_rows if stills.kind_of(r) == "scene"] + scene_rows
        setting_rows = [r for r in asked_rows if stills.kind_of(r) == "setting"] + setting_rows
        own = [r for r in asked_rows if stills.kind_of(r) == "object"] + own
    if backdrop == "places" and setting_rows:
        # the morphs stand in places: the settings take the objects' part, and only the shapes the user asked for lead
        pool = setting_rows
        own = [r for r in own if r.get("own")]
    look_vibe = asked if asked in VIBE_LOOK else vibe
    if reading.get("own") and own:
        wanted = {stills.clean_noun(o) for o in reading["own"]}
        own.sort(key=lambda r: 0 if str(r.get("noun") or "").lower() in wanted else 1)  # the line's shapes first among yours
    if reading.get("scenes") and scene_rows:
        wanted_scenes = {stills.clean_noun(s, stills.SCENE_NOUN_LIMIT) for s in reading["scenes"]}
        scene_rows.sort(key=lambda r: 0 if str(r.get("noun") or "").lower() in wanted_scenes else 1)  # the typed place opens
    words = stills.content_words(_story_words(state))  # the stop words out: "to" must not pick the reel-to-reel
    typed = stills.content_words(_idea_words(state))  # the idea line and the brief: what the user actually asked for
    # objects that belong together: the cut draws on one family first (the idea line's word, else the vibe's
    # heaviest family, the tie turned by the seed), freshest first within it, the rest of the pool after
    named = str(reading.get("family") or "") or stills.family_named(asked or vibe, typed) \
        or stills.family_named(asked or vibe, words)  # the idea's family first
    family = named or stills.family_for_cut(asked or vibe, set(), seed=int(state.get("seed") or 0))
    for r in pool:
        r["family"] = stills.family_of(str(r.get("noun") or ""))
    if family:
        # never-used objects of the family, then never-used others, then the used ones (family first), so a second
        # cut still opens on what the first left alone; the stable sort keeps order_fresh's order inside each group.
        # The shipped stills are a curated chain (black: rose -> jellyfish -> butterfly -> swallow -> drops), so
        # only a family the idea line names reorders them; the vibe's own family groups the grown library behind.
        used = stills.usage().get(vibe) or {}  # a tick a cut, so a bigger number is a more recent cut

        def key(r):
            tick = int(used.get(str(r.get("file")), 0))
            in_family = 0 if (named or not r.get("shipped")) and r.get("family") == family else 1
            # the idea's family leads over freshness (a second cut of the chess idea still opens on the machines,
            # longest-unused first); the vibe's own family only groups the fresh rows
            return (in_family, tick) if named else (0 if tick == 0 else 1, in_family, tick)

        pool.sort(key=key)
    lead = next((i for i, item in enumerate(pool) if set(item["noun"].split()) & typed), None)
    if lead is None:
        lead = next((i for i, item in enumerate(pool) if set(item["noun"].split()) & words), None)
    if lead:
        # the object the idea names opens the cut; the rest keep their order (a rotation here once pushed the family
        # just grown for the idea to the back of the pool, behind the lead, 26 Oct), unless the pool is a curated
        # shipped chain with no family sort, where the rotation keeps the chain's own pairings
        pool = [pool[lead]] + pool[:lead] + pool[lead + 1:] if (named or any(not r.get("shipped") for r in pool))             else pool[lead:] + pool[:lead]
    # a theme or a family the line names keeps the chain on it: its things and the family's stills, walked again
    # (chain_walk pairs them afresh) rather than topped up with whatever the vibe has (a wishing well, a peony and a
    # snare drum after a rally car, 28 Oct). Too few of them to carry a chain, and the rest of the pool follows them.
    if reading.get("theme") or named:
        themed = {stills.clean_noun(n) for n in list(reading.get("theme_things") or []) + list(reading.get("objects") or [])}
        named_here = [r for r in pool if set(str(r.get("noun") or "").split()) & typed]  # what the line names leads its family
        core = named_here + [r for r in pool if r not in named_here and (str(r.get("noun") or "").lower() in themed
                                                                          or (named and r.get("family") == family))]
        if len(core) + len(own) >= min(int(count), THEME_CHAIN_MIN):  # the line's own shapes count: they are its things
            pool = core
        elif core:
            pool = core + [r for r in pool if r not in core]
    elif len(pool) >= stills.REALM_LIBRARY:
        # no line: the cut stays in one realm (creatures, garden, cosmos, machines, dark fantasy, home and craft) with
        # enough stills to carry it, the one this vibe has used least (the seed breaks a tie, so cuts take turns),
        # family by family, so neighbours belong together
        by_realm: dict[str, list[dict]] = {}
        for r in pool:
            name = stills.realm_of(str(r.get("family") or ""))
            if name:
                by_realm.setdefault(name, []).append(r)
        fit = sorted(n for n, rows in by_realm.items() if len(rows) >= min(int(count), THEME_CHAIN_MIN))
        if fit:
            used = stills.usage().get(vibe) or {}
            worn = {n: sum(int(used.get(str(r.get("file")), 0)) for r in by_realm[n]) / len(by_realm[n]) for n in fit}
            fresh = [n for n in fit if worn[n] == min(worn.values())]
            name = fresh[int(state.get("seed") or 0) % len(fresh)] if len(fresh) > 1 else fresh[0]
            fams = stills.REALMS[name]
            pool = sorted(by_realm[name], key=lambda r: fams.index(r.get("family")))
    pool = _drop_bad_pairs(pool, {tuple(p) for p in autotune().get("bad_pairs") or []})
    # A chain of ``count`` takes the first ``count`` objects when the pool is bigger, so the walk below only
    # repeats pairings when the whole pool is smaller than the cut (a 20 s clip over twelve stills never repeats one).
    objects = user_targets(state) + own + pool
    n_free = len(free_slots)  # the slots the pins left are filled as before, over the pool without the pinned stills
    if n_free and not objects and not scene_rows:
        # the pins took the whole pool: the free slots walk the pinned stills again rather than crash on nothing
        objects = [dict(r) for r in held.values()]
    if choice == "only" and scene_rows:
        free = chain_walk(user_targets(state) + scene_rows, n_free)
    elif choice == "mix" and scene_rows:
        slots = scene_at if scene_at is not None else scene_slots(None, n_free, "mix")
        slots = sorted({int(k) for k in slots if 0 <= int(k) < n_free})[:len(scene_rows)]  # no scene twice
        n_obj = n_free - len(slots)
        between = chain_walk(objects, n_obj) if objects else chain_walk(scene_rows[len(slots):] or scene_rows, n_obj)
        free, scenes_, si, oi = [], scene_rows[:len(slots)], 0, 0
        for k in range(n_free):
            if k in slots:
                free.append(scenes_[si])
                si += 1
            else:
                free.append(between[oi])
                oi += 1
    else:
        free = chain_walk(objects, n_free)
    picked = [held[k] if k in held else free.pop(0) for k in range(count)]  # the pins hold their slots
    if record:
        for under in {p["_vibe"] for p in picked if p.get("_vibe")}:
            stills.mark_used(under, [p["file"] for p in picked if p.get("_vibe") == under])
    return look_vibe, [{**{k: v for k, v in item.items() if k != "_vibe"}, "path": item.get("path") or str(OBJECTS / item["file"])} for item in picked]


def user_targets(state: dict) -> list[dict]:
    """The user's own images as morph targets (state["morph_targets"]: local paths). They lead, in order."""
    out = []
    for raw in list((state or {}).get("morph_targets") or [])[:12]:
        path = Path(str(raw))
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path.is_file():
            out.append({"noun": path.stem.replace("_", " ")[:40] or "image", "file": path.name, "path": str(path.resolve()), "user": True})
    return out


def handoffs(scenes: list[dict], beats: list, duration: float) -> list[float]:
    """Scene boundaries, each snapped to the nearest beat within 0.25s."""
    grid = [float(b) for b in beats or []]
    bounds = [0.0]
    for scene in scenes[:-1]:
        t = float(scene.get("end") or 0.0)
        if grid:
            near = min(grid, key=lambda b: abs(b - t))
            if abs(near - t) <= 0.25:
                t = near
        if t - bounds[-1] >= 0.5:
            bounds.append(t)
    end = float(scenes[-1].get("end") or duration) if scenes else duration
    bounds.append(max(end, bounds[-1] + 0.5))
    return bounds


def gen_length(frames: int) -> int:
    n = 8 * math.ceil(max(frames - 1, 0) / 8) + 1
    return int(min(MAX_LEN, max(MIN_LEN, n)))


# The morph prompt for a pair that touches a scene (``stills.kind`` "scene"): the object prompt's "one single
# sculptural object ... stays centred" contradicts a wide frame at the guide, and LTX then abandons the scene at
# frame 1 (a cut, not a morph: the dark shore into the astrolabe, 26 Oct). One variant per pair kind, so a run
# encodes at most three extra prompts on the CPU.
SCENE_OPENINGS = {
    ("scene", "object"): "A wide landscape scene slowly melts and flows into one single sculptural object that forms at its centre",
    ("object", "scene"): "One single sculptural object slowly melts and spreads out into a wide landscape scene",
    ("scene", "scene"): "A wide landscape scene slowly melts and flows into another wide landscape scene",
    ("scene", "setting"): "A wide landscape scene slowly melts and gathers into one object standing in a place at its centre",
    ("setting", "scene"): "The object standing in its place slowly melts and spreads out into a wide landscape scene",
}
# A pair that touches a setting (``stills`` kind "setting": an object standing in a place, 31 Oct): the object prompt's
# "the object stays centred ... macro product photography" is a studio, and the vibe's look names a backdrop or a void
# the place has replaced. Setting to setting keeps the morph style (it is how the object changes) and lets the place
# shift with it; a setting next to a plain object has the place grow in or fade out.
SETTING_OPENINGS = {
    ("object", "setting"): "One single sculptural object slowly transforms into another while a place slowly grows around it",
    ("setting", "object"): "The object standing in its place slowly transforms into another while the place slowly fades away around it",
}
SETTING_TAIL = ("the object stays large and whole in the middle of the frame, the camera steady, {look}, one single object, every "
                "feature appears once, cinematic photograph, crisp, clean, high detail")


def pair_kinds(a: dict | None, b: dict | None) -> tuple[str, str]:
    """The kinds of a morph's two stills (scene, setting or object), ``("object", "object")`` for the plain chain."""
    out = []
    for row in (a, b):
        kind = str((row or {}).get("kind") or "")
        out.append(kind if kind in ("scene", "setting") else "object")
    return tuple(out)


def place_look(vibe: str) -> str:
    """The vibe's look for a pair in a place: its material and light without the backdrop or void words."""
    from xenoform import stills

    return stills.place_look(VIBE_LOOK.get(vibe, VIBE_LOOK["liquid-gold"])) or "its own materials and light"


def guide_compression(kinds: tuple[str, str] | None, value) -> tuple[int, int]:
    """The ``img_compression`` of a morph's two guide stills, start and end: ``value`` for an object, 0 for a scene. The
    compression is the freedom the morph takes from the guide, and a wide frame loses its texture to it at once: the
    Draft rule since 26 Oct, and the Final and Cloud rule since 31 Oct (LTX-2.5's loose 30 used to reach scenes too)."""
    kinds = tuple(kinds) if kinds else ("object", "object")
    return tuple(0 if k == "scene" else int(value) for k in kinds[:2])


def prompt_for(vibe: str, engine: str = "ltx095", kinds: tuple[str, str] | None = None, style: str = "melt") -> str:
    """One prompt per vibe and style, not per pair: the two guide stills carry the objects.

    The text encoder runs on the CPU (it is what pushed the card past 11.5 GB),
    so the prompt stays identical across a run's morphs of one style for
    ComfyUI to encode it once and reuse it. A pair that touches a scene
    (``kinds``, see ``pair_kinds``) gets the scene variant, the same text for
    every such pair in the run, whatever the style (``morph_style``: a style is
    how an object changes). Melt is the prompt every morph had before the
    styles, word for word.

    A pair in a place (a setting at either end, no scene): two settings take the
    style's opening and "the place slowly shifts with it", the camera steady; a
    setting beside a plain object has the place grow in or fade out
    (``SETTING_OPENINGS``). Its look drops the vibe's backdrop words.
    """
    look = VIBE_LOOK.get(vibe, VIBE_LOOK["liquid-gold"])
    lead = "Use the provided start image as the first frame and the provided end image as the final frame anchor. " if engine == "ltx25" else ""
    kinds = tuple(kinds) if kinds else ("object", "object")
    opening = SCENE_OPENINGS.get(kinds)
    if opening:
        return lead + (
            f"{opening}, one continuous liquid transformation, the picture never cuts, the frame stays steady, "
            f"gentle slow camera drift, {look}, every feature appears once, cinematic, crisp, clean, high detail"
        )
    from xenoform.morph_style import OPENINGS, normal

    if "setting" in kinds:
        tail = SETTING_TAIL.format(look=place_look(vibe))
        if kinds == ("setting", "setting"):
            return lead + f"{OPENINGS[normal(style, allow_auto=False)]}, while the place around it slowly shifts with it, {tail}"
        return lead + f"{SETTING_OPENINGS[kinds]}, one continuous transformation, the picture never cuts, {tail}"
    return lead + (
        f"{OPENINGS[normal(style, allow_auto=False)]}, the object stays centred, gentle slow camera drift, {look}, "
        "one single object, every feature appears once, macro product photography, crisp, clean, high detail"
    )


def ltx25_present(root: Path | None = None) -> bool:
    if root is None:
        try:
            from xenoform.models_setup import models_root  # was models_dir, which never existed: always False

            root = Path(models_root() or "")
        except Exception:
            return False
    return all((Path(root) / folder / name).is_file() for folder, name in LTX25_FILES)


def pick_engine() -> str:
    """``ltx095`` unless ``XENO_MORPH_ENGINE=ltx25`` asks for LTX-2.5 and its four files are on disk.

    LTX-2.5 used to be picked whenever its files were there (the check never found them). It is opt-in now: on the 29 Oct
    test pair its first/last-frame graph held the first object and cut to the second near the end rather than morphing,
    and the 22B model on a 12 GB card takes minutes a morph against the Draft's seconds."""
    forced = os.environ.get("XENO_MORPH_ENGINE", "").strip().lower()
    if forced == "ltx25":
        return "ltx25" if ltx25_present() and GRAPH25.exists() else "ltx095"
    return "ltx095"


def _graph_path(work: Path, engine: str = "ltx095") -> Path:
    if engine == "ltx25":
        return GRAPH25
    if GRAPH.exists():
        return GRAPH
    from xenoform.morph.workflow import graph

    dest = work / "xenoform_morph.json"
    dest.write_text(json.dumps(graph(), indent=1), encoding="utf-8")
    return dest


def _ffmpeg() -> str:
    try:
        from xenoform.video import ffmpeg_bin

        return ffmpeg_bin()
    except Exception:
        return "ffmpeg"


def _read_frames(path: Path, w: int, h: int) -> np.ndarray:
    raw = subprocess.run(
        [_ffmpeg(), "-v", "error", "-i", str(path), "-vf", f"scale={w}:{h}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True,
        capture_output=True,
    ).stdout
    frames = np.frombuffer(raw, np.uint8)
    return frames.reshape(-1, h, w, 3)


def _fit(frames: np.ndarray, count: int) -> np.ndarray:
    """Exactly ``count`` frames, first and last kept, so handoffs stay on the grid."""
    if len(frames) == 0:
        raise RuntimeError("A morph came back with no frames.")
    pick = np.round(np.linspace(0, len(frames) - 1, count)).astype(int)
    return frames[pick]


def _result(client, job, index: int, failed):
    """``job.result()``, riding out the proxy's transient "expired".

    comfy-api-proxy 0.1.6 reports a job that is between ComfyUI's queue and its
    history as ``expired`` (a terminal state), then ``succeeded`` a moment later.
    Seen once in seven morphs on the 3080 Ti; re-reading the job recovers it.
    """
    for attempt in range(6):
        try:
            return job.result()
        except failed as exc:
            if "expired" not in str(exc) or attempt == 5:
                raise RuntimeError(f"Comfy job failed for morph {index + 1}: {exc}") from exc
            log.info("morph %d read as expired; re-reading job %s", index + 1, job.id)
            time.sleep(0.5 + attempt * 0.5)
            job = client.jobs.get(job.id)


_TERMINAL = {"succeeded", "failed", "canceled", "cancelled"}


def cancel_jobs(jobs: list, settle_s: float = 4.0) -> int:
    """Cancel every job of ours that has not finished, on the proxy (and so in ComfyUI).

    ``POST /api/v2/jobs/{id}/cancel`` maps to ComfyUI's atomic per-id cancel: a queued
    job is dequeued, the running one is interrupted at the next node boundary. Jobs
    from other clients are never touched. Returns how many jobs were cancelled.

    Queued jobs go first and the running one last: interrupting the running job
    first lets ComfyUI start the next queued one, and a new prompt clears the
    interrupt flag, so that one would run to the end. A short sweep then catches
    any job that slipped from queued to running while the cancels went out.
    """
    cancelled: set = set()

    def status(job) -> str:
        try:
            job.refresh()
        except Exception:
            log.debug("refresh of %s failed", getattr(job, "id", "?"))
        return str(getattr(job, "status", "")).lower()

    def one_pass() -> int:
        live = [(job, status(job)) for job in jobs]
        live = [(job, st) for job, st in live if st not in _TERMINAL and st != "expired"]
        live.sort(key=lambda pair: pair[1] in ("running", "in_progress"))
        for job, _ in live:
            try:
                job.cancel()
                cancelled.add(getattr(job, "id", id(job)))
            except Exception:
                log.exception("could not cancel job %s", getattr(job, "id", "?"))
        return len(live)

    left = one_pass()
    deadline = time.monotonic() + settle_s
    while left and time.monotonic() < deadline:
        time.sleep(0.5)
        left = one_pass()
    if cancelled:
        log.info("cancelled %d queued/running morph job(s)", len(cancelled))
    return len(cancelled)


def stop_queued(jobs: list, cancel: Callable[[], bool] | None) -> None:
    """Raise ``JobCancelled`` after cancelling what is already queued, if the desk cancelled."""
    if cancel and cancel():
        from xenoform.turbo import JobCancelled

        n = cancel_jobs(jobs)
        raise JobCancelled(f"Cancelled. {n} queued morph{'s' if n != 1 else ''} removed from the GPU queue.")


def wait_or_cancel(job, jobs: list, cancel: Callable[[], bool] | None, poll_s: float = 0.4) -> None:
    """Block until ``job`` is terminal, checking ``cancel`` between polls.

    ``job.result()`` alone blocks with no way out, so a Stop on the desk used to
    leave every queued morph running on the GPU.
    """
    if not cancel:
        return
    while True:
        stop_queued(jobs, cancel)
        try:
            job.refresh()
        except Exception:
            log.debug("refresh of %s failed; trying again", getattr(job, "id", "?"))
        status = str(getattr(job, "status", "")).lower()
        if status in _TERMINAL or status == "expired":
            return
        time.sleep(poll_s)


def _qa_reroll(client, graph, asset, a, b, vibe, engine, count, seed, dest, tune, cancel) -> dict:
    """Check a finished morph (flicker, pops, optional CLIP failure prompts); reroll once if it fails.

    The reroll gets a new seed and less freedom (full end guide, no compression,
    cfg 3), and replaces the clip only if it scores better. Off with XENO_QA=0.
    """
    if os.environ.get("XENO_QA", "1") == "0":
        return {}
    from xenoform import shot_qa

    good = f"a clean single sculptural object, {VIBE_LOOK.get(vibe, VIBE_LOOK['liquid-gold'])}"
    if "setting" in pair_kinds(a, b):  # the object stands in a place: the studio words would mark it down
        good = f"one single object standing large in a place, {place_look(vibe)}"
    try:
        from xenoform.anchors import subject_in

        subject = subject_in(f"{a.get('noun', '')} {b.get('noun', '')}")
        first = shot_qa.check(_read_frames(dest, 320, 180), good, subject)
    except Exception as exc:  # QA must never break a render
        log.warning("shot QA skipped: %s", exc)
        return {}
    if first["ok"] or engine == "ltx25" or (cancel and cancel()):
        return {"first": first}
    wf = client.workflows.from_file(str(graph))
    wf.set_input("6", "image", asset(a["path"]))
    wf.set_input("7", "image", asset(b["path"]))
    wf.set_input("3", "text", prompt_for(vibe, engine, pair_kinds(a, b)))
    wf.set_input("4", "text", _vibes.negative(vibe) or NEGATIVE)
    wf.set_input("9", "width", WIDTH)
    wf.set_input("9", "height", HEIGHT)
    wf.set_input("9", "length", gen_length(count))
    wf.set_input("11", "steps", int(tune.get("steps", STEPS)))
    wf.set_input("14", "cfg", 3.0)
    wf.set_input("8", "img_compression", 0)
    wf.set_input("21", "img_compression", 0)
    wf.set_input("22", "strength", 1.0)
    wf.set_input("13", "noise_seed", seed + 101)
    wf.set_input("18", "fps", float(FPS))
    try:
        from comfy_sdk import JobFailed

        result = _result(client, client.submit(wf), 0, JobFailed)
        outputs = list(result.get_outputs("19")) or list(result.outputs)
        alt = dest.with_name(dest.stem + "-reroll.mp4")
        outputs[0].to_file(str(alt))
        second = shot_qa.check(_read_frames(alt, 320, 180), good, subject)
    except Exception as exc:
        log.warning("shot QA reroll failed: %s", exc)
        return {"first": first, "reroll": "failed"}
    if second["score"] > first["score"]:
        alt.replace(dest)
        return {"first": first, "reroll": second, "kept": "reroll"}
    return {"first": first, "reroll": second, "kept": "first"}


def run_morph_pass(
    directed: dict,
    scenes: list[dict],
    audio_path: Path,
    out_path: Path,
    work: Path,
    cfg: dict,
    state: dict,
    report: Callable[[str, float, str], None],
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """LTX-2.5 when it is installed, LTX 0.9.5 otherwise, and 0.9.5 again if 2.5 fails.

    ``cancel`` is the desk's Stop: when it fires, every morph this pass queued is
    cancelled on the proxy and the chain stops with ``JobCancelled``.
    """
    engine = pick_engine()
    if engine == "ltx25":
        try:
            return _render(directed, scenes, audio_path, out_path, work, cfg, state, report, "ltx25", cancel=cancel)
        except Exception as exc:
            from xenoform.turbo import JobCancelled

            if isinstance(exc, JobCancelled):
                raise
            log.exception("LTX-2.5 morph pass failed; falling back to LTX 0.9.5")
            report("restyle", 0.1, "LTX-2.5 did not run here. Falling back to LTX 0.9.5 morphs.")
            info = _render(directed, scenes, audio_path, out_path, work, cfg, state, report, "ltx095", cancel=cancel)
            info["fallback_from"] = f"ltx25: {exc}"[:300]
            return info
    return _render(directed, scenes, audio_path, out_path, work, cfg, state, report, engine, cancel=cancel)


def _render(
    directed: dict,
    scenes: list[dict],
    audio_path: Path,
    out_path: Path,
    work: Path,
    cfg: dict,
    state: dict,
    report: Callable[[str, float, str], None],
    engine: str = "ltx095",
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    from xenoform.restyle import _make_client

    started = time.perf_counter()
    work = Path(work) / "morphs"
    work.mkdir(parents=True, exist_ok=True)
    duration = float(directed.get("duration") or (scenes[-1].get("end") if scenes else 0) or 0)
    bounds = handoffs(scenes, list(directed.get("beats") or []), duration)
    shots = len(bounds) - 1
    vibe, stills = pick_stills(state, shots + 1)
    marks = [int(round(t * FPS)) for t in bounds]
    counts = [max(2, marks[i + 1] - marks[i]) for i in range(shots)]
    seed = int(state.get("seed") or 2727)

    client = _make_client(cfg)
    graph = _graph_path(work, engine)
    tune = tuned(vibe) if engine != "ltx25" else {}
    assets: dict[str, Any] = {}

    def asset(path: str):
        if path not in assets:
            assets[path] = client.assets.from_file(path)
        return assets[path]

    jobs = []
    for i in range(shots):
        a, b = stills[i], stills[i + 1]
        wf = client.workflows.from_file(str(graph))
        wf.set_input("6", "image", asset(a["path"]))
        wf.set_input("7", "image", asset(b["path"]))
        wf.set_input("3", "text", prompt_for(vibe, engine, pair_kinds(a, b)))
        wf.set_input("4", "text", _vibes.negative(vibe) or NEGATIVE)
        wf.set_input("9", "width", WIDTH)
        wf.set_input("9", "height", HEIGHT)
        wf.set_input("9", "length", gen_length(counts[i]))
        if engine == "ltx25":
            # Distilled: the fixed 8-sigma schedule in the graph, CFG 1; audio latent sized to match.
            wf.set_input("25", "frames_number", gen_length(counts[i]))
        else:
            wf.set_input("11", "steps", int(tune.get("steps", STEPS)))
            if "cfg" in tune:
                wf.set_input("14", "cfg", float(tune["cfg"]))
            if "img_compression" in tune:
                wf.set_input("8", "img_compression", int(tune["img_compression"]))
                wf.set_input("21", "img_compression", int(tune["img_compression"]))
            if "guide_end_strength" in tune:
                wf.set_input("22", "strength", float(tune["guide_end_strength"]))
        wf.set_input("13", "noise_seed", seed + i)
        wf.set_input("18", "fps", float(FPS))
        stop_queued(jobs, cancel)
        jobs.append(client.submit(wf))
        log.info("morph %d/%d %s -> %s submitted as %s", i + 1, shots, a["noun"], b["noun"], jobs[-1].id)
    submitted = time.perf_counter() - started
    report("restyle", 0.12, f"{shots} morphs queued on the GPU · {vibe}")

    from comfy_sdk import JobFailed

    clips = []
    qa_log: list[dict] = []
    timings = []
    for i, job in enumerate(jobs):
        wait_or_cancel(job, jobs, cancel)
        result = _result(client, job, i, JobFailed)
        outputs = list(result.get_outputs("19")) or list(result.outputs)
        if not outputs:
            raise RuntimeError(f"Morph {i + 1} finished with no video.")
        chosen = next((o for o in outputs if getattr(o, "type", None) == "video"), outputs[0])
        dest = work / f"m{i:02d}.mp4"
        chosen.to_file(str(dest))
        qa = _qa_reroll(client, graph, asset, stills[i], stills[i + 1], vibe, engine, counts[i], seed + i, dest, tune, cancel)
        qa_log.append(qa)
        clips.append(dest)
        timings.append(round(time.perf_counter() - started, 2))
        report(
            "restyle",
            0.12 + 0.8 * (i + 1) / shots,
            f"Morph {i + 1} of {shots} · {stills[i]['noun']} into {stills[i + 1]['noun']}",
        )

    stop_queued(jobs, cancel)
    report("assemble", 0.6, "Locking the morphs to the beat")
    gpu_path = Path(out_path).with_name(Path(out_path).stem + "-gpu.mp4")
    enc = subprocess.Popen(
        [
            _ffmpeg(), "-v", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-",
            "-i", str(audio_path),
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
            str(gpu_path),
        ],
        stdin=subprocess.PIPE,
    )
    try:
        for clip, count in zip(clips, counts):
            enc.stdin.write(_fit(_read_frames(clip, OUT_W, OUT_H), count).tobytes())
    finally:
        enc.stdin.close()
        code = enc.wait()
    if code:
        raise RuntimeError(f"ffmpeg could not write the morph cut (exit {code}).")
    try:
        from xenoform.video import overlay_text

        overlay_text(gpu_path, directed.get("text_cards") or [])
    except Exception:
        log.exception("text cards on the morph cut")
    gpu_path.replace(out_path)
    info = {
        "engine": ("ltx-2.5 22B distilled int8" if engine == "ltx25" else "ltx-095") + " A->B morph chain (comfy-sdk -> comfy-api-proxy)",
        "workflow": str(graph),
        "vibe": vibe,
        "render": f"{WIDTH}x{HEIGHT}",
        "output": f"{OUT_W}x{OUT_H}",
        "steps": 8 if engine == "ltx25" else int(tune.get("steps", STEPS)),
        "autotune": tune or None,
        "fps": FPS,
        "handoffs_s": [round(t, 3) for t in bounds],
        "frames": counts,
        "stills": [s["file"] for s in stills],
        "qa": qa_log,
        "submitted_s": round(submitted, 2),
        "done_s": timings,
        "seconds": round(time.perf_counter() - started, 2),
    }
    (work / "morph_pass.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return info
