"""The stills library (``xenoform.stills``; ``xenoform.library`` is the judges shot-library baker): the objects a
vibe's morphs travel between, and how it grows on the user's own GPU.

A cut is a chain of morphs between stills of single objects rendered in the vibe's material. The repo ships a
seed set (``ui_static/objects/<vibe>/``, listed in ``objects.json``); this module adds a second, local set under
the work folder (``work/ui/objects/<vibe>/``, listed in ``stills.json``) that the app generates with Z-Image
Turbo through the same comfy-sdk -> comfy-api-proxy path the morphs use. The chain sees both as one pool
(``catalogue``), puts the user's own shapes first, and prefers the objects a vibe has used least (``usage``), so
a long library never laps inside a cut and two cuts of the same song do not open on the same object.

Subjects come from ``configs/subjects.json``: families of nouns with a weight per vibe, so chrome draws on solids
and instruments while a print vibe draws on creatures and plants, instead of every vibe sharing one dozen.
Prompts come from ``configs/still_prompts.json``: the style prefix each shipped pool was made with, so a new
still sits on the same backdrop and light as the pool it joins (a vibe without an entry falls back to its
``still_style`` in vibes.json).

Every candidate is checked against the pool it joins before it is kept (``check``): backdrop (the border
colour stays with the pool), size (the subject neither fills the frame nor vanishes), cropped (it does not run
off the edge), soft (it is as sharp as the pool), duplicate (a near copy of an object already there). Rejects
are kept under ``<vibe>/rejected/`` for the eye, never listed. The five original vibes (liquid-gold, bloom,
neon-night, ocean, cosmic) were graded after rendering; ``grade`` repeats that pass here.

A second kind of still, **scenes** (``kind="scene"``): wide frames in the vibe's material and light with no single
centred object, from ``configs/scenes.json`` and the ``scene`` prefix in ``still_prompts.json``, so a Simple cut can
morph scenes and not only objects (the make body's ``scene_stills``: "mix" lands a scene on every passage change,
"only" draws on scenes alone). A scene skips the object-shaped checks (no centred-subject size, no backdrop drift,
no cropped edge, no zoom) and keeps the soft and duplicate checks.

A third kind, **settings** (``kind="setting"``, 31 Oct): one object standing in a place that suits the vibe (the gold
scarab on dusk dunes, the black glass rose on wet obsidian under mist, a lantern on a rain-slick street), the object
still the hero, large and readable, the place soft behind it, for Tys's "the blank background really kills these ones ...
maybe bigger objects?". The places come from ``configs/settings.json`` (a list per vibe, else the default), the prompt
from the vibe's ``setting`` template in ``still_prompts.json`` (else the ``default`` one), the subject sentence first,
since with the style first Z-Image drew a statue or a blob beside the creature. A setting is checked like a scene (no
backdrop, size or cropped check; soft and duplicate stay), is not graded (the prompt carries the vibe's colour), and is
zoomed in on when its hero is small (``normalise_scale`` with the setting ``fill``). Its row carries the object as
``noun`` and the ``place``; the make body's ``backdrop`` "places" draws on them (``morph_pass.backdrop_choice``).

Nothing here touches ComfyUI's process. ``XENO_STILLS`` moves the local set (tests point it at a temp dir).
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger("xenoform.stills")

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = Path(__file__).resolve().parent / "ui_static" / "objects"
GRAPH = ROOT / "workflows" / "zimage_t2i_api.json"
SUBJECTS = ROOT / "configs" / "subjects.json"
PROMPTS = ROOT / "configs" / "still_prompts.json"
SCENES = ROOT / "configs" / "scenes.json"
SETTINGS = ROOT / "configs" / "settings.json"
VIBES_JSON = ROOT / "configs" / "vibes.json"
W, H = 1024, 576
JPG_QUALITY = 92
# the Z-Image Turbo files the graph loads (ComfyUI's /models lists say whether they are installed)
UNET = "z_image_turbo_int8_convrot.safetensors"
TEXT_ENCODER = "qwen_3_4b.safetensors"
VAE = "ae.safetensors"
N_TEXT, N_SEED, N_SIZE, N_SAVE = "5", "10", "7", "12"
SECONDS_PER_STILL = 6.0  # measured 5.7 s a still on a 3080 Ti (432 stills in 2475 s, 24 Oct 2026)
MAX_OWN = 12             # own shapes a request renders
MAX_GROW = 120           # stills one grow request renders
MIN_POOL = 3             # grown stills a vibe with no shipped ones needs before it stops borrowing a pool
DEFAULT_GROW = 36
DEFAULT_GROW_SCENES = 8  # scenes one chip grows: the vibe's list is six to eight wide frames, a second pass varies the seed
DEFAULT_GROW_SETTINGS = 8  # settings one chip grows: eight objects, each in the next of the vibe's places
KINDS = ("object", "scene", "setting")
WHOLE_FRAME = ("scene", "setting")  # kinds whose frame is the picture: no backdrop, size or cropped check, never graded
# a scene is a whole frame: the wide-frame tail every scene prompt ends on when a vibe has no ``scene`` prefix
SCENE_TAIL = ("a wide scene filling the whole frame edge to edge, no single centred object, no people, no faces, no text, "
              "no letters, no watermark, crisp focus, high detail.")
# the shipped pools' taste rule (tests/test_morph_pass.py): no retro or sci-fi props, whatever the catalogue says
BANNED = ("rocket", "sputnik", "satellite", "film reel", "rotary", "vintage", "vinyl", "ringed planet", "gear", "clock", "phone")
REASONS = ("backdrop", "size", "cropped", "soft", "duplicate")

# ------------------------------------------------------------------------------------------------ where


def root() -> Path:
    """The local stills folder: ``XENO_STILLS``, else ``work/ui/objects`` beside the desk's other work."""
    env = os.environ.get("XENO_STILLS", "").strip()
    path = Path(env) if env else ROOT / "work" / "ui" / "objects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path() -> Path:
    return root() / "stills.json"


def usage_path() -> Path:
    return root() / "usage.json"


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------ catalogue


def shipped() -> dict[str, list[dict]]:
    """The seed set the repo ships (``objects.json``): rows of file / noun / finish / source."""
    return _read_json(SHIPPED / "objects.json", {})


def grown() -> dict[str, list[dict]]:
    """The local set (``stills.json``), rows whose file has been deleted dropped: deleting a jpg is the cull."""
    idx = _read_json(index_path(), {})
    base = root()
    out: dict[str, list[dict]] = {}
    for vibe, rows in idx.items():
        kept = [r for r in rows if (base / str(r.get("file") or "")).is_file()]
        if kept:
            out[vibe] = kept
    return out


def catalogue(shipped_rows: dict[str, list[dict]] | None = None) -> dict[str, list[dict]]:
    """Every vibe's pool as the chain sees it: the shipped rows first, then the grown ones, each with ``path``.
    ``shipped_rows`` replaces ``objects.json`` (morph_pass passes its own ``manifest()``, which tests patch)."""
    out: dict[str, list[dict]] = {}
    for vibe, rows in (shipped() if shipped_rows is None else shipped_rows).items():
        out[vibe] = [{**r, "path": str(SHIPPED / r["file"]), "shipped": True} for r in rows]
    base = root()
    for vibe, rows in grown().items():
        out.setdefault(vibe, []).extend({**r, "path": str(base / r["file"]), "shipped": False} for r in rows)
    return out


def kind_of(row: dict) -> str:
    """``"scene"`` for a scene row, ``"setting"`` for an object standing in a place, ``"object"`` for everything else (the
    shipped rows carry no kind)."""
    kind = str((row or {}).get("kind") or "")
    return kind if kind in ("scene", "setting") else "object"


def counts(vibe: str | None = None) -> dict:
    """``shipped`` / ``grown`` / ``own`` / ``scenes`` / ``settings`` / ``total`` for one vibe, or ``{vibe: counts}`` for
    all (``grown`` is the objects grown here; scenes and settings are counted apart)."""
    cat = catalogue()
    if vibe is not None:
        rows = cat.get(vibe) or []
        n_ship = sum(1 for r in rows if r.get("shipped"))
        n_own = sum(1 for r in rows if r.get("own"))
        n_scene = sum(1 for r in rows if kind_of(r) == "scene")
        n_setting = sum(1 for r in rows if kind_of(r) == "setting")
        return {"shipped": n_ship, "grown": len(rows) - n_ship - n_own - n_scene - n_setting, "own": n_own, "scenes": n_scene,
                "settings": n_setting, "total": len(rows)}
    return {v: counts(v) for v in cat}


def nouns_in(vibe: str) -> set[str]:
    """The object nouns a vibe has (scenes and settings apart: a scene, a setting and an object may share a word)."""
    return {str(r.get("noun") or "").lower() for r in catalogue().get(vibe) or [] if kind_of(r) == "object"}


def scene_nouns_in(vibe: str) -> set[str]:
    return {str(r.get("noun") or "").lower() for r in catalogue().get(vibe) or [] if kind_of(r) == "scene"}


def setting_nouns_in(vibe: str) -> set[str]:
    """The objects a vibe already has standing in a place (the same object may also be a plain still)."""
    return {str(r.get("noun") or "").lower() for r in catalogue().get(vibe) or [] if kind_of(r) == "setting"}


# ------------------------------------------------------------------------------------------------ usage


def usage() -> dict[str, dict[str, int]]:
    return _read_json(usage_path(), {})


def mark_used(vibe: str, files: list[str]) -> None:
    """Record that a cut used these objects (one tick per call, so the next cut prefers the others)."""
    if not files:
        return
    data = usage()
    tick = int(data.get("_tick") or 0) + 1
    data["_tick"] = tick
    row = data.setdefault(vibe, {})
    for f in files:
        row[str(f)] = tick
    _write_json(usage_path(), data)


def order_fresh(vibe: str, rows: list[dict]) -> list[dict]:
    """The user's own shapes first, then the objects used longest ago (never used first), pool order within."""
    used = usage().get(vibe) or {}
    return sorted(rows, key=lambda r: (0 if r.get("own") else 1, int(used.get(str(r.get("file")), 0))))


# ------------------------------------------------------------------------------------------------ subjects


def subjects() -> dict:
    return _read_json(SUBJECTS, {})


def _ok_noun(noun: str) -> bool:
    low = noun.lower()
    return bool(low) and not any(b in low for b in BANNED)


def nouns_for(vibe: str, count: int, have: set[str] | None = None, seed: int | None = None) -> list[str]:
    """``count`` subjects for ``vibe`` from the catalogue's families, weighted by the vibe's entry (else the
    defaults), skipping ``have`` and the banned props. Weighted sampling without replacement, so a core family
    leads but never crowds the others out."""
    data = subjects()
    fams = data.get("families") or {}
    entry = (data.get("vibes") or {}).get(vibe) or {}
    weights = dict(entry.get("weights") or data.get("default_weights") or {})
    for fam in entry.get("avoid") or []:
        weights.pop(fam, None)
    have = {h.lower() for h in (have or set())}
    rng = random.Random(seed)
    pool = []
    for fam, w in weights.items():
        for noun in (fams.get(fam) or {}).get("nouns") or []:
            noun = str(noun).strip().lower()
            if noun in have or not _ok_noun(noun):
                continue
            pool.append((rng.random() ** (1.0 / max(float(w), 0.01)), noun))
    pool.sort(reverse=True)
    out, seen = [], set()
    for _, noun in pool:
        if noun not in seen:
            out.append(noun)
            seen.add(noun)
        if len(out) >= count:
            break
    return out


_FAMILY_INDEX: dict | None = None


def family_index() -> dict[str, str]:
    """noun -> family id, from the catalogue (cached)."""
    global _FAMILY_INDEX
    if _FAMILY_INDEX is None:
        idx = {}
        for fam, row in (subjects().get("families") or {}).items():
            for noun in row.get("nouns") or []:
                idx[str(noun).strip().lower()] = fam
        _FAMILY_INDEX = idx
    return _FAMILY_INDEX


def family_of(noun: str) -> str:
    """The family a noun belongs to ("" when the catalogue does not know it); a grown still's noun is in the
    catalogue, a shipped one too, an own shape usually not."""
    low = str(noun or "").strip().lower()
    idx = family_index()
    if low in idx:
        return idx[low]
    words = set(low.split())
    for n, fam in idx.items():  # "orb iridescent" -> "orb"; "crescent moon oil slick" -> "crescent moon"
        if n in low or (set(n.split()) <= words):
            return fam
    return ""


STOP_WORDS = frozenset("a an the and or of to in on by with for from at into over under as is are its it this that".split())


def content_words(words) -> set[str]:
    """The words of an idea line that can name an object or a family: the stop words out, so "lamps and lanterns"
    is not picked by "and" nor "reel to reel" by "to" (26 Oct review)."""
    return {str(w).lower() for w in (words or ()) if str(w).lower() not in STOP_WORDS and len(str(w)) > 1}


# Realms: families that belong in one cut. A cut no line gives a theme stays in its family's realm (morph_pass.pick_stills)
# instead of wandering the whole library: trilobite, sea fan, dragon shield, harpsichord read as a shuffle (28 Oct).
REALMS = {
    "creatures": ("sea-creatures", "shells-and-corals", "insects-and-small-creatures", "birds-and-beasts", "living-things"),
    "garden": ("flowers", "pods-and-cones", "fruit-and-food"),
    "cosmos": ("celestial-bodies", "solids-and-knots", "crystals-and-minerals", "weather-and-liquid"),
    "machines": ("intricate-machines", "machine-parts", "time-and-navigation", "musical-instruments", "retro-tech",
                 "vehicles-and-craft", "big-iconic", "toys-and-games"),
    "dark fantasy": ("grimdark", "high-fantasy", "anatomy-and-bones", "strange-and-surreal", "keys-and-curios"),
    "home and craft": ("vessels-and-tableware", "lamps-and-lanterns", "origami-and-paper", "knots-and-textiles",
                       "architectural-fragments"),
}
REALM_LIBRARY = 40  # a vibe with this many object stills is cut within one realm; a smaller one keeps its curated chain


def realm_of(family: str) -> str:
    """The realm a family belongs to ("" for none)."""
    return next((name for name, fams in REALMS.items() if family in fams), "")


GENERIC_LABEL_WORDS = frozenset("things big living high strange intricate".split())  # "Big iconic things" names nothing by "things"
NOUN_JOINS = re.compile(r"\s(?:with|holding|of|on|in|under|from|made|full|into|topped|carved|crowned|perched|curled|mid)\s")


def noun_keys(noun: str) -> set[str]:
    """The words of a catalogue noun that name it in an idea line. A short noun answers to each of its words ("sea
    turtle"); a described one only to its head ("seashell holding a tiny city" to "seashell", "dragon skull with curling
    horns" to "skull"), or a line with "city" in it would pick the surreal family (28 Oct)."""
    words = str(noun).lower().split()
    if len(words) <= 2:
        return content_words(words)
    head = NOUN_JOINS.split(" " + str(noun).lower() + " ", maxsplit=1)[0].split()
    return content_words(head[-1:]) if head else set()


def family_named(vibe: str, words: set[str] | None = None) -> str:
    """The family a word of the idea line names (a family's noun or its label), or "" when none does."""
    fams = (subjects().get("families") or {})
    words = content_words(words)
    if not words:
        return ""
    for fam, row in fams.items():
        label_words = (content_words(re.findall(r"[a-z]+", str(row.get("label") or "").lower())) | content_words(fam.split("-"))) - GENERIC_LABEL_WORDS
        if words & label_words:
            return fam
        for noun in row.get("nouns") or []:
            if noun_keys(noun) & words:
                return fam
    return ""


def family_for_cut(vibe: str, words: set[str] | None = None, seed: int | None = None) -> str:
    """The family a cut draws on, so its objects belong together instead of being thrown together: a word of the
    idea line that names a family's noun or its label picks that family ("a chrome moth circles a neon sign" ->
    insects, ``family_named``); else the vibe's heaviest family, the tie broken by ``seed`` so two cuts of one song
    differ."""
    data = subjects()
    fams = data.get("families") or {}
    named = family_named(vibe, words)
    if named:
        return named
    entry = (data.get("vibes") or {}).get(vibe) or {}
    weights = dict(entry.get("weights") or data.get("default_weights") or {})
    if not weights:
        return ""
    top = max(weights.values())
    best = [f for f, w in weights.items() if w == top and f in fams]
    if not best:
        return ""
    return best[(int(seed) if seed is not None else 0) % len(best)]


def family_nouns(vibe: str, family: str, count: int, have: set[str] | None = None) -> list[str]:
    """``count`` nouns of ``family`` the vibe does not have yet, in catalogue order (the idea line's family grown
    for the cut, so its objects belong together)."""
    row = (subjects().get("families") or {}).get(family) or {}
    have = {h.lower() for h in (have or set())}
    out = []
    for noun in row.get("nouns") or []:
        noun = str(noun).strip().lower()
        if noun not in have and _ok_noun(noun):
            out.append(noun)
        if len(out) >= count:
            break
    return out


def clean_noun(text: str, limit: int = 40) -> str:
    """A typed shape as a noun: lowercase, one space, no article, letters and digits only, ``limit`` characters
    (40 for an object; a scene subject gets 80, since "corridor of mirrors in violet light" is a sentence)."""
    low = re.sub(r"[^a-z0-9 \-']+", " ", str(text).lower())
    low = re.sub(r"\s+", " ", low).strip()
    while True:  # "one single lantern", "the astrolabe": the articles and counters go, however many lead
        stripped = re.sub(r"^(a|an|the|one|single|my) ", "", low)
        if stripped == low:
            break
        low = stripped
    return clip_words(low, limit)


def clip_words(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters at a word: "a canyon of birds until the thread holds" read back as
    "...a canyon of birds unt" (28 Oct). A single word longer than half the limit is cut where it falls."""
    text = str(text).strip()
    if len(text) <= limit:
        return text
    head = text[:limit + 1]
    cut = head.rsplit(" ", 1)[0] if " " in head else ""
    return (cut if len(cut) >= limit // 2 else text[:limit]).strip()


SCENE_NOUN_LIMIT = 80


def scene_subjects() -> dict:
    return _read_json(SCENES, {})


def scene_list(vibe: str) -> list[str]:
    """The vibe's scene subjects from ``configs/scenes.json`` (else the default list), cleaned, in order."""
    data = scene_subjects()
    raw = (data.get("vibes") or {}).get(vibe) or data.get("default") or []
    out: list[str] = []
    for item in raw:
        noun = clean_noun(item, SCENE_NOUN_LIMIT)
        if noun and noun not in out:
            out.append(noun)
    return out


def scene_nouns_for(vibe: str, count: int, have: set[str] | None = None, seed: int | None = None) -> list[str]:
    """``count`` scene subjects for ``vibe``: the ones it has not rendered yet first (list order, or shuffled by
    ``seed``), then the list again, since a second render of the shore on a new seed is a different picture (the
    duplicate check catches a near copy). Empty only when the catalogue has no list at all."""
    rows = scene_list(vibe)
    if not rows or count <= 0:
        return []
    have = {h.lower() for h in (have or set())}
    fresh = [n for n in rows if n not in have]
    if seed is not None:
        random.Random(seed).shuffle(fresh)
    out = list(fresh)
    while len(out) < count:
        out.extend(rows)
    return out[:count]


PLACE_LIMIT = 100  # a place is a phrase ("on the polished stone floor of an ancient temple, shafts of warm light")


def setting_subjects() -> dict:
    return _read_json(SETTINGS, {})


def clean_place(text: str) -> str:
    """A place as the prompt puts it after the object: one line, no quotes or braces, ``PLACE_LIMIT`` characters."""
    low = re.sub(r"[^A-Za-z0-9 ,\-']+", " ", str(text or ""))
    return clip_words(re.sub(r"\s+", " ", low).strip(" ,"), PLACE_LIMIT)


def place_list(vibe: str) -> list[str]:
    """The vibe's places from ``configs/settings.json`` (else the default list), cleaned, in order."""
    data = setting_subjects()
    raw = (data.get("vibes") or {}).get(vibe) or data.get("default") or []
    out: list[str] = []
    for item in raw:
        place = clean_place(item)
        if place and place not in out:
            out.append(place)
    return out


def places_for(vibe: str, count: int, *, start: int = 0, seed: int | None = None) -> list[str]:
    """``count`` places for ``vibe``'s next settings: the list in order (shuffled by ``seed``), from ``start`` (how many
    settings the vibe has, so a second grow moves on to the places the first did not reach), round again when the list
    runs out. Deterministic for the same arguments: the desk plans a grow and then grows it, and both must agree."""
    rows = place_list(vibe)
    if not rows or count <= 0:
        return []
    if seed is not None:
        random.Random(seed).shuffle(rows)
    return [rows[(int(start) + i) % len(rows)] for i in range(int(count))]


# the words that put an object on a studio ground: a setting's prompt and its morph keep the vibe's material and light but
# drop these, since the place is the ground now ("plain dark grey backdrop" under a scarab on the dunes)
GROUND_WORDS = ("backdrop", "void", "no floor", "studio", "seamless", "on pure black", "on black", "black background")


def place_look(look: str) -> str:
    """A vibe's look without its ground: the comma clauses that name a backdrop, a void or a studio go, the rest (the
    material, the light, the colour) stays."""
    parts = [p.strip() for p in str(look or "").split(",")]
    kept = [p for p in parts if p and not any(w in p.lower() for w in GROUND_WORDS)]
    return ", ".join(kept).strip().rstrip(".")


def own_nouns(text: str | list) -> list[str]:
    """The shapes typed into the desk ("a brass astrolabe, wolf skull"): distinct, cleaned, at most MAX_OWN."""
    parts = text if isinstance(text, list) else re.split(r"[,\n;]+", str(text))
    out = []
    for p in parts:
        noun = clean_noun(p)
        if noun and noun not in out:
            out.append(noun)
    return out[:MAX_OWN]


# ------------------------------------------------------------------------------------------------ prompts


def prompts() -> dict:
    return _read_json(PROMPTS, {})


def _vibe_meta(vibe: str) -> dict:
    data = _read_json(VIBES_JSON, {})
    entries = data.get("vibes", data)
    items = entries if isinstance(entries, list) else [dict(id=k, **v) for k, v in entries.items()]
    return next((x for x in items if x.get("id") == vibe), {})


SETTING_DEFAULT = ("One single {noun}{made}, {place}. Close-up cinematic shot from a low camera angle, one single object towering "
                   "large in the foreground and filling two thirds of the frame height, centred and whole, {look}the place "
                   "stretching out behind it in soft focus, shallow depth of field, crisp focus on the object, high detail, no text, "
                   "no letters, no logos, no people, no faces.")  # the ``default`` row of still_prompts.json, when it is missing
SETTING_PLACE = "in a place that suits it"  # a setting with no place given and a vibe with no list


def setting_prompt(vibe: str, noun: str, place: str | None = None) -> str:
    """A setting's prompt: the vibe's ``setting`` template (still_prompts.json), else the ``default`` one with the vibe's
    material and its look without the ground words, the object and the place put in. The subject sentence leads: with
    the vibe's style first and the subject last, Z-Image drew a gold statue with a tiny dragonfly at its feet, or a pair
    of gold legs for "the subject cast in gold, towering" (31 Oct trials); the noun first kept the creature every time."""
    data = prompts()
    tmpl = str((data.get(vibe) or {}).get("setting") or "").strip()
    if not tmpl:
        tmpl = str((data.get("default") or {}).get("setting") or SETTING_DEFAULT).strip()
        meta = _vibe_meta(vibe)
        material = str(meta.get("material") or "").strip()
        look = str(meta.get("look") or "").strip()
        if not look:
            try:
                from xenoform.morph_pass import VIBE_LOOK  # the original five carry their look there, not in the registry

                look = str(VIBE_LOOK.get(vibe) or "")
            except Exception:  # pragma: no cover - the registry is always importable in the app
                look = ""
        look = place_look(look)
        tmpl = tmpl.replace("{made}", f" made of {material}" if material else "").replace("{look}", f"{look}, " if look else "")
    place = clean_place(place) if place else ""
    if not place:
        places = place_list(vibe)
        place = places[0] if places else SETTING_PLACE
    return re.sub(r"\s+", " ", tmpl.replace("{noun}", str(noun).strip()).replace("{place}", place)).strip()


def prompt_for(vibe: str, noun: str, kind: str = "object", place: str | None = None) -> str:
    """The still's prompt: the pool's own style prefix and subject sentence when the vibe has one, else the
    vibe's ``still_style`` with a plain subject sentence in its material. A scene takes the vibe's ``scene``
    prefix (wide frame, the vibe's material and light, no centred object, no people, no text) and the subject as a
    sentence ("Dark shore under a star field, seen wide."); a vibe without one gets its ``look`` in front of the
    wide-frame tail. A setting is the object ``noun`` standing in ``place`` (``setting_prompt``)."""
    if kind == "setting":
        return setting_prompt(vibe, noun, place)
    row = prompts().get(vibe) or {}
    if kind == "scene":
        prefix = str(row.get("scene") or "").strip()
        if not prefix:
            meta = _vibe_meta(vibe)
            look = str(meta.get("look") or meta.get("still_style") or "").strip().rstrip(".")
            prefix = f"Cinematic wide establishing shot, {look}, {SCENE_TAIL}" if look else f"Cinematic wide establishing shot, {SCENE_TAIL}"
        noun = str(noun).strip()
        return f"{prefix} {noun[:1].upper()}{noun[1:]}, seen wide.".strip()
    prefix = str(row.get("prefix") or "").strip()
    subject = str(row.get("subject") or "").strip()
    if not prefix:
        meta = _vibe_meta(vibe)
        prefix = str(meta.get("still_style") or meta.get("look") or "Studio macro photograph, one single object centred, seamless dark backdrop, crisp focus, no text, no people.").strip()
        material = str(meta.get("material") or "").strip()
        subject = f"One single {{noun}} made of {material}." if material else "One single {noun}."
    return f"{prefix} {subject.format(noun=noun)}".strip()


def slug(noun: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", noun.lower()).strip("_") or "object"


# ------------------------------------------------------------------------------------------------ the checks

SMALL = (256, 144)  # every measure runs on a small copy: a pool of fifty is profiled in well under a second
EDGE_SHARE = 0.12   # of an outer band that must be object for the edge to count as touched


def _small(path: Path | str | Image.Image, size=SMALL) -> np.ndarray:
    im = path.convert("RGB") if isinstance(path, Image.Image) else Image.open(path).convert("RGB")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def _border(a: np.ndarray, band: float = 0.06) -> np.ndarray:
    h, w = a.shape[:2]
    bh, bw = max(1, int(h * band)), max(1, int(w * band))
    ring = np.concatenate([a[:bh].reshape(-1, 3), a[-bh:].reshape(-1, 3), a[:, :bw].reshape(-1, 3), a[:, -bw:].reshape(-1, 3)])
    return ring.mean(axis=0)


def _backdrop_fit(a: np.ndarray, band: float = 0.06) -> np.ndarray:
    """The backdrop as a smooth surface fitted to the border ring (a quadratic in x and y per channel), so a
    graded gradient or a floor glow reads as backdrop and only the object stands out from it. A subject that
    runs into the ring biases the fit a little, and then reads as cropped anyway."""
    h, w = a.shape[:2]
    bh, bw = max(1, int(h * band)), max(1, int(w * band))
    yy, xx = np.mgrid[0:h, 0:w]
    ring = np.zeros((h, w), dtype=bool)
    ring[:bh], ring[-bh:], ring[:, :bw], ring[:, -bw:] = True, True, True, True
    xn, yn = (xx / max(w - 1, 1)) * 2 - 1, (yy / max(h - 1, 1)) * 2 - 1
    basis = np.stack([np.ones_like(xn), xn, yn, xn * xn, yn * yn, xn * yn], axis=-1).astype(np.float32)
    coef, *_ = np.linalg.lstsq(basis[ring], a[ring], rcond=None)
    fit = basis.reshape(-1, 6) @ coef
    residual = float(np.median(np.abs(a[ring] - fit.reshape(h, w, 3)[ring]).mean(axis=1)))
    return fit, residual


def _grey(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def _sharpness(g: np.ndarray) -> float:
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def _box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """A ``k`` x ``k`` mean over each channel (edges reflected), OpenCV when present, else summed-area tables."""
    try:
        import cv2  # type: ignore

        return cv2.blur(np.ascontiguousarray(a, dtype=np.float32), (k, k), borderType=cv2.BORDER_REFLECT)
    except Exception:  # pragma: no cover - OpenCV is a dependency
        r = k // 2
        pad = [(r, r), (r, r)] + [(0, 0)] * (a.ndim - 2)
        p = np.pad(a.astype(np.float64), pad, mode="reflect")
        c = p.cumsum(0).cumsum(1)
        c = np.pad(c, [(1, 0), (1, 0)] + [(0, 0)] * (a.ndim - 2))
        h, w = a.shape[:2]
        s = c[k:k + h, k:k + w] - c[:h, k:k + w] - c[k:k + h, :w] + c[:h, :w]
        return (s / (k * k)).astype(np.float32)


def hero_box(im: Path | str | Image.Image) -> tuple[float, float, float, float] | None:
    """The box (x0, y0, x1, y1, fractions of the frame) of a setting's hero: the object in focus in front of a soft
    place. A setting has no plain ground for ``features`` to subtract, so this reads where the picture is sharp and
    stands out of its own surroundings, weighted toward the centre the prompt puts the object at, and keeps the
    strongest blob. It errs large (the in-focus ground at the object's feet joins it), so a zoom it drives under-zooms
    rather than crops the object. None when nothing stands out."""
    a = _small(im)
    h, w = a.shape[:2]
    g = _grey(a)
    lap = np.zeros_like(g)
    lap[1:-1, 1:-1] = np.abs(-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    energy = _box_blur(lap, 9)
    contrast = _box_blur(np.abs(a - _box_blur(a, 41)).mean(axis=2), 5)
    yy, xx = np.mgrid[0:h, 0:w]
    prior = np.exp(-(((xx - w / 2) / (0.42 * w)) ** 2 + ((yy - h / 2) / (0.55 * h)) ** 2))
    e = energy / (float(np.percentile(energy, 99)) + 1e-6)
    c = contrast / (float(np.percentile(contrast, 99)) + 1e-6)
    score = (0.6 * np.clip(e, 0, 1.5) + 0.4 * np.clip(c, 0, 1.5)) * prior
    mask = score > max(0.18, float(np.percentile(score, 80)))
    try:
        import cv2  # type: ignore

        mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2) > 0
        n, labels = cv2.connectedComponents(mask.astype(np.uint8))
        if n > 1:  # the blob carrying the most of the score
            mass = np.bincount(labels.ravel(), weights=score.ravel(), minlength=n)
            mass[0] = 0.0
            mask = labels == int(np.argmax(mass))
    except Exception:  # pragma: no cover - OpenCV is a dependency; the whole mask then stands for the blob
        pass
    if not mask.any():
        return None
    rows_sum, cols_sum = mask.sum(axis=1), mask.sum(axis=0)
    rows = np.where(rows_sum > 0.02 * rows_sum.max())[0]
    cols = np.where(cols_sum > 0.02 * cols_sum.max())[0]
    return (float(cols[0]) / w, float(rows[0]) / h, float(cols[-1] + 1) / w, float(rows[-1] + 1) / h)


def features(path: Path | str) -> dict:
    """One still's measures: border colour, subject area and bounding box, edges the subject touches,
    sharpness, and the small grey copy the duplicate check correlates."""
    a = _small(path)
    h, w = a.shape[:2]
    border = _border(a)
    fit, residual = _backdrop_fit(a)
    dist = np.abs(a - fit.reshape(h, w, 3)).mean(axis=2)
    fg = dist > 28.0
    area = float(fg.mean())
    rows = np.where(fg.sum(axis=1) > 0.01 * w)[0]
    cols = np.where(fg.sum(axis=0) > 0.01 * h)[0]
    box = (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])) if len(rows) and len(cols) else (0, 0, 0, 0)
    # an edge is touched when a real share of its outer band is object, not when a speckle of residual reaches it
    my, mx = max(1, int(0.02 * h)), max(1, int(0.02 * w))
    edges = int(sum(float(band.mean()) > EDGE_SHARE for band in (fg[:my], fg[-my:], fg[:, :mx], fg[:, -mx:])))
    g = _grey(a)
    return {"border": border, "residual": residual, "area": area, "edges": edges, "box": box, "sharp": _sharpness(g), "grey": g}


def profile(paths: list[Path | str]) -> dict:
    """What a pool looks like, for the checks to calibrate against: the median border colour and the pool's
    spread around it, the subject-area range, the most edges any member touches, the median sharpness, and
    every member's hash. An empty pool profiles as ``None`` fields and the checks fall back to fixed bounds."""
    feats = [features(p) for p in paths]
    if not feats:
        return {"n": 0, "border": None, "spread": 0.0, "residual": None, "area": (None, None), "edges": 0, "sharp": None, "greys": []}
    borders = np.stack([f["border"] for f in feats])
    median = np.median(borders, axis=0)
    spread = float(np.median(np.abs(borders - median[None, :]).mean(axis=1)))
    areas = [f["area"] for f in feats]
    return {"n": len(feats), "border": median, "spread": spread, "residual": float(np.median([f["residual"] for f in feats])),
            "area": (min(areas), max(areas)), "edges": max(f["edges"] for f in feats),
            "sharp": float(np.median([f["sharp"] for f in feats])), "greys": [f["grey"] for f in feats]}


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 0 else 0.0


# Calibrated on the shipped pools and the 24 Oct batch: the eye accepted a uniform warm or bright shift that
# measured 26 to 45, the grey studio and cluttered rooms it rejected measured 60 and up; distinct objects in one
# pool correlate at most 0.86, the same still re-encoded, shifted three pixels or rescaled three per cent at 0.97 and up.
BACKDROP_FLOOR = 40.0
RESIDUAL_FLOOR = 18.0
DUPLICATE_NCC = 0.93


def check(path: Path | str, prof: dict, *, extra_greys: list | None = None, kind: str = "object") -> dict:
    """The verdict on one candidate against ``prof``: ``ok`` and the reasons it failed (``why``), with the
    measures behind them. Thresholds scale with the pool: a backdrop may drift three times as far as the pool's
    own members do (never under ``BACKDROP_FLOOR`` of 255) and the border ring must be as smooth as the pool's
    (a quadratic surface fits it within ``RESIDUAL_FLOOR``, else bars or clutter), the area may be 0.4 times the
    smallest or twice the largest, the subject may touch one edge (none, when the pool is a clean void; any, when
    the pool's own stills are scene-like), sharpness must reach a third of the pool's median, and a still that
    correlates with a member above ``DUPLICATE_NCC`` is the same object again. A scene (``kind="scene"``) is a
    whole frame with no backdrop and no centred subject, so only soft and duplicate apply to it; a setting (an object
    standing in a place) is a whole frame too, its place reaching every edge, so it is checked the same way."""
    f = features(path)
    why: list[str] = []
    drift = 0.0
    whole = kind in WHOLE_FRAME
    if whole:
        pass  # no backdrop, size or cropped check: the frame is the picture
    elif prof.get("border") is not None:
        drift = float(np.abs(f["border"] - prof["border"]).mean())
        if drift > max(BACKDROP_FLOOR, 3.0 * float(prof.get("spread") or 0.0)):
            why.append("backdrop")
    # a backdrop the smooth fit cannot describe (side bars, a cluttered room, a table edge) is structure, not a gradient
    if not whole and f["residual"] > max(RESIDUAL_FLOOR, 3.0 * float(prof.get("residual") or 0.0)) and "backdrop" not in why:
        why.append("backdrop")
    # size holds the pool's scale loosely: a pool's own twelve already span three to four times in area, and a morph
    # between a small and a large object is a zoom, not a fault; what it catches is the frame-filler and the speck
    amin, amax = prof.get("area") or (None, None)
    lo = max(0.03, 0.4 * amin) if amin is not None else 0.03
    hi = min(0.85, 2.0 * amax) if amax is not None else 0.85
    if not whole and not lo <= f["area"] <= hi:
        why.append("size")
    # a pool whose own stills reach two or more edges (smoke, rain, wet reflections: neon-noir) is scene-like, and
    # the mask cannot tell object from backdrop at the frame edge there, so the cropped check steps aside for it
    pool_edges = int(prof.get("edges") or 0)
    if not whole and f["edges"] > (4 if pool_edges >= 2 else 1):
        why.append("cropped")
    if prof.get("sharp") is not None and f["sharp"] < 0.3 * float(prof["sharp"]):
        why.append("soft")
    greys = list(prof.get("greys") or []) + list(extra_greys or [])
    dup = max((_ncc(g, f["grey"]) for g in greys), default=0.0)
    if dup >= DUPLICATE_NCC:
        why.append("duplicate")
    return {"ok": not why, "why": why, "backdrop": round(drift, 1), "residual": round(f["residual"], 1), "area": round(f["area"], 3),
            "edges": f["edges"], "sharp": round(f["sharp"], 1), "dup": round(dup, 3), "grey": f["grey"]}


# ------------------------------------------------------------------------------------------------ grade

# The five original pools were rendered as glass and mercury on black and graded afterwards (scripts/vibe_objects/
# grade.py): a hue nudge of the iridescent teal, a tinted additive backdrop where the still is dark, a gentle lift.
GRADE = {
    "liquid-gold": dict(hue=38, top=(70, 40, 8), bot=(150, 92, 24), k=0.85, tint=(1.18, 1.0, 0.70), sat=1.0),
    "bloom": dict(hue=335, top=(70, 110, 50), bot=(150, 185, 90), k=0.90, tint=(1.05, 1.0, 0.95), sat=1.15),
    "neon-night": dict(hue=338, top=(45, 4, 30), bot=(175, 22, 95), k=0.95, tint=(1.12, 0.95, 1.08), sat=1.2, lift=1.6),
    "ocean": dict(hue=185, top=(4, 40, 60), bot=(20, 110, 120), k=0.85, tint=(0.9, 1.02, 1.08), sat=1.1),
    "cosmic": dict(hue=228, top=(2, 8, 40), bot=(30, 45, 135), k=0.80, tint=(0.95, 0.95, 1.12), sat=1.2),
}


def grade(im: Image.Image, vibe: str) -> Image.Image:
    """The original five's post-render grade; any other vibe comes back untouched."""
    v = GRADE.get(vibe)
    if not v:
        return im
    size = im.size
    hsv = np.asarray(im.convert("RGB").convert("HSV")).astype(np.float32)
    h, s = hsv[..., 0] * 360 / 255, hsv[..., 1]
    teal = (np.abs(((h - 180) + 180) % 360 - 180) < 35) & (s > 40)
    hsv[..., 0] = np.where(teal, v["hue"], h) * 255 / 360
    hsv[..., 1] = np.clip(s * v["sat"], 0, 255)
    rgb = np.asarray(Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")).astype(np.float32)
    rgb *= np.array(v["tint"])[None, None, :]
    width, height = size
    yy, xx = np.mgrid[0:height, 0:width]
    t = (yy / height)[..., None]
    back = np.array(v["top"]) * (1 - t) + np.array(v["bot"]) * t
    r = np.sqrt(((xx - width / 2) / (width * 0.6)) ** 2 + ((yy - height * 0.55) / (height * 0.7)) ** 2)[..., None]
    back = back * np.clip(1.25 - r, 0.25, 1.0)
    lum = rgb.mean(-1, keepdims=True) / 255
    w = v["k"] * np.clip(1 - lum * 3.0, 0, 1)
    out = rgb + back * w
    out = 255 * (1 - (1 - np.clip(out, 0, 255) / 255) ** v.get("lift", 1.15))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


# ------------------------------------------------------------------------------------------------ scale

SUBJECT_MIN = 0.45   # of the frame height: a subject smaller than this is zoomed in on
SUBJECT_TARGET = 0.62
ZOOM_MAX = 2.2
# The fill target: how much of the frame height a still's subject is zoomed up to when it is under the kind's minimum.
# A setting's object is the hero of a whole picture, so it is held bigger than a plain object (Tys, 30 Oct: "maybe bigger
# objects?"), and its zoom is gentler, since a crop of a place loses the place and the hero box errs large.
FILL = {"object": SUBJECT_TARGET, "setting": 0.74}
FILL_MIN = {"object": SUBJECT_MIN, "setting": 0.55}
FILL_ZOOM_MAX = {"object": ZOOM_MAX, "setting": 1.5}


def normalise_scale(im: Image.Image, kind: str = "object", fill: float | None = None) -> Image.Image:
    """A small subject is zoomed in on so every still in a pool sits at a similar scale: a typed octopus a quarter
    the size of the typed key beside it made the morph between them a zoom (the 25 Oct judge panel). The zoom is a
    centred crop on the subject's box, never a zoom out (padding a gradient backdrop would show a seam), capped at
    ``ZOOM_MAX``, and only when the box is under ``SUBJECT_MIN`` of the frame height.

    A setting (``kind="setting"``) finds its hero with ``hero_box`` (its place is no plain ground) and is zoomed to its
    ``FILL`` target when the hero is under ``FILL_MIN``, at most ``FILL_ZOOM_MAX``, only when the box holds the frame's
    centre (the prompt centres the object: a sharp corner is not the hero) and never so far that the box leaves the
    crop. ``fill`` replaces the kind's target."""
    if kind == "setting":
        return _fill_setting(im, float(fill) if fill is not None else FILL["setting"])
    if kind == "scene":
        return im
    target = float(fill) if fill is not None else SUBJECT_TARGET
    w, h = im.size
    a = _small(im) if isinstance(im, Image.Image) else _small(Path(str(im)))
    sh, sw = a.shape[:2]
    fit, _ = _backdrop_fit(a)
    fg = np.abs(a - fit.reshape(sh, sw, 3)).mean(axis=2) > 28.0
    rows = np.where(fg.sum(axis=1) > 0.01 * sw)[0]
    cols = np.where(fg.sum(axis=0) > 0.01 * sh)[0]
    if not len(rows) or not len(cols):
        return im
    box_h = (rows[-1] - rows[0] + 1) / sh
    if box_h >= SUBJECT_MIN or box_h <= 0:
        return im
    zoom = min(ZOOM_MAX, target / box_h)
    cw, ch = w / zoom, h / zoom
    cx = (cols[0] + cols[-1] + 1) / 2 / sw * w
    cy = (rows[0] + rows[-1] + 1) / 2 / sh * h
    left = min(max(0.0, cx - cw / 2), w - cw)
    top = min(max(0.0, cy - ch / 2), h - ch)
    return im.crop((int(round(left)), int(round(top)), int(round(left + cw)), int(round(top + ch)))).resize((w, h), Image.LANCZOS)


def _fill_setting(im: Image.Image, target: float) -> Image.Image:
    """``normalise_scale`` for a setting: a crop on the hero, zoomed to ``target`` of the frame height."""
    box = hero_box(im)
    if box is None:
        return im
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    centred = x0 <= 0.5 <= x1 and y0 - 0.15 <= 0.5 <= y1 + 0.15  # the centre column, and near the middle row
    if bh >= FILL_MIN["setting"] or bh <= 0 or not centred:
        return im
    zoom = min(FILL_ZOOM_MAX["setting"], target / bh, 1.0 / max(bw, 1e-3), 1.0 / max(bh, 1e-3))
    if zoom <= 1.02:
        return im
    w, h = im.size
    cw, ch = w / zoom, h / zoom
    cx, cy = (x0 + x1) / 2 * w, (y0 + y1) / 2 * h
    left = min(max(0.0, cx - cw / 2), w - cw)
    top = min(max(0.0, cy - ch / 2), h - ch)
    return im.crop((int(round(left)), int(round(top)), int(round(left + cw)), int(round(top + ch)))).resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------------------------------------ ingest


def _next_index(folder: Path) -> int:
    nums = [int(m.group(1)) for p in folder.glob("*.jpg") if (m := re.match(r"^(\d+)_", p.name))]
    return (max(nums) + 1) if nums else 0


def pool_profile(vibe: str, kind: str = "object") -> dict:
    """The profile a candidate for ``vibe`` is checked against: the look (backdrop, size, edges, sharpness) comes
    from the shipped stills alone, so a batch cannot drag the vibe's look toward itself import by import; the
    duplicate check sees every object still, shipped or grown. A vibe with no shipped stills profiles on what it
    has. A scene candidate (``kind="scene"``) takes the pool's sharpness and is a duplicate only of another scene; a
    setting likewise of another setting."""
    rows = catalogue().get(vibe) or []
    objects = [r for r in rows if kind_of(r) == "object"]
    anchor = [r["path"] for r in objects if r.get("shipped")] or [r["path"] for r in objects]
    prof = profile(anchor)
    if kind in WHOLE_FRAME:
        prof["greys"] = [features(r["path"])["grey"] for r in rows if kind_of(r) == kind]
        return prof
    extra = [features(r["path"])["grey"] for r in objects if not r.get("shipped")] if prof["n"] else []
    prof["greys"] = list(prof.get("greys") or []) + extra
    return prof


def ingest(vibe: str, source: Path | str, noun: str, *, prof: dict | None = None, own: bool = False,
           origin: str = "Z-Image Turbo (Apache 2.0), grown on this machine", extra_greys: list | None = None,
           seed: int | None = None, keep_rejects: bool = True, kind: str = "object", place: str | None = None) -> dict:
    """One candidate into the vibe's local set: graded if the vibe grades, checked against the pool, then
    either written as the next numbered jpg and listed in ``stills.json`` (``kept`` True) or set aside under
    ``rejected/`` with its reasons in the name. Returns the verdict with ``file`` when kept. A scene is neither
    graded nor zoomed (the frame is the picture) and the row carries ``kind: "scene"``. A setting is not graded either
    (its prompt carries the vibe's colour, and the grade's tinted backdrop would wash its place), is zoomed to its fill
    target when its object is small, and its row carries ``kind: "setting"`` and the ``place``."""
    folder = root() / vibe
    folder.mkdir(parents=True, exist_ok=True)
    kind = kind if kind in KINDS else "object"
    prof = prof if prof is not None else pool_profile(vibe, kind)
    im = Image.open(source).convert("RGB")
    if kind == "object":
        im = normalise_scale(grade(im, vibe))
    elif kind == "setting":
        im = normalise_scale(im, "setting")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    tmp = folder / f"_candidate_{slug(noun)}.jpg"
    im.save(tmp, quality=JPG_QUALITY)
    verdict = check(tmp, prof, extra_greys=extra_greys, kind=kind)
    verdict["noun"] = noun
    if not verdict["ok"]:
        if keep_rejects:
            rej = folder / "rejected"
            rej.mkdir(exist_ok=True)
            dest = rej / f"{int(time.time()) % 100000:05d}_{slug(noun)}_{'_'.join(verdict['why'])}.jpg"
            os.replace(tmp, dest)
            verdict["file"] = str(dest.relative_to(root())).replace("\\", "/")
        else:
            tmp.unlink(missing_ok=True)
        verdict["kept"] = False
        return verdict
    n = _next_index(folder)
    dest = folder / f"{n:03d}_{slug(noun)}.jpg"
    os.replace(tmp, dest)
    rel = str(dest.relative_to(root())).replace("\\", "/")
    row = {"file": rel, "noun": noun, "source": origin, "made": time.strftime("%Y-%m-%d"),
           "qa": {k: verdict[k] for k in ("backdrop", "residual", "area", "edges", "sharp", "dup")}}
    if own:
        row["own"] = True
    if kind in WHOLE_FRAME:
        row["kind"] = kind
    if kind == "setting" and place:
        row["place"] = clean_place(place)
    if seed is not None:
        row["seed"] = int(seed)
    idx = _read_json(index_path(), {})
    idx.setdefault(vibe, []).append(row)
    _write_json(index_path(), idx)
    verdict.update({"kept": True, "file": rel, "path": str(dest)})
    return verdict


def import_folder(vibe: str, folder: Path | str, *, origin: str = "", own: bool = False,
                  progress: Callable | None = None, kind: str = "object") -> dict:
    """Every png or jpg in ``folder`` as a candidate for ``vibe`` (the noun from the file name, a leading
    number and a reject's reason suffix dropped): the same checks and grade as a grown still, so a vibe's
    ``rejected/`` folder can be run again after the checks change. ``kind="scene"`` imports them as scenes,
    ``kind="setting"`` as settings (the noun is the object; the place is not known). Returns the tally."""
    folder = Path(folder)
    kind = kind if kind in KINDS else "object"
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    prof = pool_profile(vibe, kind)
    have = scene_nouns_in(vibe) if kind == "scene" else setting_nouns_in(vibe) if kind == "setting" else nouns_in(vibe)
    greys: list = []
    out = {"vibe": vibe, "kind": kind, "asked": len(files), "kept": 0, "rejected": {}, "rejected_n": 0, "skipped": 0, "files": []}
    reasons = "|".join(REASONS + ("render",))
    for i, p in enumerate(files):
        stem = re.sub(rf"(_(?:{reasons}))+$", "", re.sub(r"^\d+[_\- ]*", "", p.stem))  # a reject's name carries its reasons
        noun = clean_noun(stem.replace("_", " "), SCENE_NOUN_LIMIT if kind == "scene" else 40)
        if not _ok_noun(noun) or (noun in have and not own and kind == "object"):
            out["skipped"] += 1
            continue
        v = ingest(vibe, p, noun, prof=prof, own=own, origin=origin or f"Z-Image Turbo (Apache 2.0), imported from {folder.name}", extra_greys=greys, kind=kind)
        if v["kept"]:
            greys.append(v["grey"])  # a reject must not block a later good one as its duplicate
            out["kept"] += 1
            out["files"].append(v["file"])
            have.add(noun)
        else:
            out["rejected_n"] += 1
            for why in v["why"]:
                out["rejected"][why] = out["rejected"].get(why, 0) + 1
        if progress:
            progress(i + 1, len(files), out["kept"])
    return out


# ------------------------------------------------------------------------------------------------ generate


def available(cfg: dict | None = None, *, fetch: Callable | None = None) -> dict:
    """Whether ComfyUI has the Z-Image Turbo files the graph loads (its /models lists, like the performer)."""
    from xenoform import performer as _perf

    lists = (fetch or _perf._fetch_model_lists)(cfg)
    if lists is None:
        return {"ok": False, "missing": [UNET, TEXT_ENCODER, VAE], "note": "ComfyUI is not answering; start it to grow the library."}
    missing = [name for folder, name in (("diffusion_models", UNET), ("text_encoders", TEXT_ENCODER), ("vae", VAE))
               if not _perf._has(lists, folder, name)]
    note = "Z-Image Turbo is installed." if not missing else "Z-Image Turbo files missing from ComfyUI: " + ", ".join(missing)
    return {"ok": not missing, "missing": missing, "note": note}


def estimate_seconds(count: int) -> float:
    return 20.0 + SECONDS_PER_STILL * max(0, int(count))


def plan(vibe: str, count: int | None = None, *, nouns: list[str] | None = None, own: bool = False, seed: int | None = None,
         kind: str = "object") -> dict:
    """What a grow would render: the nouns and prompts, before any GPU work (the desk shows it, tests use it).
    ``kind="scene"`` plans scene subjects (``DEFAULT_GROW_SCENES`` of them, from ``configs/scenes.json``; typed
    ``nouns`` are scene subjects too, never "own"). ``kind="setting"`` plans objects (typed ``nouns``, else the vibe's
    families as an object grow draws them, skipping the ones already standing in a place) and gives each the next of
    the vibe's places (``places_for``, from ``configs/settings.json``), ``DEFAULT_GROW_SETTINGS`` of them."""
    kind = kind if kind in KINDS else "object"
    own = bool(own) and kind == "object"
    default = {"scene": DEFAULT_GROW_SCENES, "setting": DEFAULT_GROW_SETTINGS}.get(kind, DEFAULT_GROW)
    count = max(1, min(int(count or default), MAX_GROW))
    places: list[str] = []
    if own:
        picked = own_nouns(nouns or [])
    elif kind == "scene":
        picked = [clean_noun(n, SCENE_NOUN_LIMIT) for n in (nouns or []) if clean_noun(n, SCENE_NOUN_LIMIT)] \
            or scene_nouns_for(vibe, count, have=scene_nouns_in(vibe), seed=seed)
        picked = picked[:MAX_GROW]
    elif kind == "setting":
        picked = [clean_noun(n) for n in (nouns or []) if clean_noun(n)] \
            or nouns_for(vibe, count, have=setting_nouns_in(vibe), seed=seed)
        picked = picked[:MAX_GROW]
        places = places_for(vibe, len(picked), start=counts(vibe).get("settings", 0), seed=seed)
    else:
        picked = [clean_noun(n) for n in (nouns or []) if clean_noun(n)] or nouns_for(vibe, count, have=nouns_in(vibe), seed=seed)
        picked = picked[:MAX_GROW]
    prompts_ = [prompt_for(vibe, n, kind, place=places[i] if places else None) for i, n in enumerate(picked)]
    out = {"vibe": vibe, "kind": kind, "nouns": picked, "prompts": prompts_, "own": bool(own),
           "seconds": estimate_seconds(len(picked)), "have": counts(vibe)}
    if kind == "setting":
        out["places"] = places
    return out


def _client(cfg: dict | None):
    from xenoform import restyle

    return restyle._make_client(cfg or {"comfy": {"proxy_url": "http://127.0.0.1:8189"}})


def grow(vibe: str, count: int | None = None, *, nouns: list[str] | None = None, own: bool = False, cfg: dict | None = None,
         seed: int | None = None, progress: Callable | None = None, cancel: Callable[[], bool] | None = None,
         client=None, sheet: bool = True, kind: str = "object") -> dict:
    """Render ``count`` new stills for ``vibe`` (or the user's own ``nouns`` with ``own``), check each against the
    pool, keep the good ones. Every prompt is queued at once and collected in order; ``progress(done, total,
    kept)`` after each; ``cancel()`` true stops collecting (queued renders still finish on the GPU, unused).
    ``kind="scene"`` renders scenes through the same graph (the scene prompt, the relaxed checks, ``kind`` on the
    row); ``kind="setting"`` renders each object in its planned place (``plan``'s ``places``, on the row too).
    Returns the tally: ``asked``, ``made``, ``kept``, ``rejected`` by reason, ``files``, ``seconds``."""
    kind = kind if kind in KINDS else "object"
    p = plan(vibe, count, nouns=nouns, own=own, seed=seed, kind=kind)
    own = p["own"]
    picked = p["nouns"]
    places = list(p.get("places") or [])
    out = {"vibe": vibe, "kind": kind, "own": bool(own), "asked": len(picked), "made": 0, "kept": 0, "rejected": {}, "rejected_n": 0,
           "files": [], "seconds": 0.0, "nouns": picked}
    if places:
        out["places"] = places
    if not picked:
        out["note"] = "nothing to render: no subjects left for this vibe" if not own else "type a shape or two first"
        return out
    t0 = time.time()
    client = client or _client(cfg)
    base_seed = int(seed) if seed is not None else random.randrange(1, 2**31)
    jobs = []
    for i, noun in enumerate(picked):
        place = places[i] if i < len(places) else None
        wf = client.workflows.from_file(str(GRAPH))
        wf.set_input(N_TEXT, "text", prompt_for(vibe, noun, kind, place=place))
        wf.set_input(N_SEED, "seed", base_seed + i)
        wf.set_input(N_SIZE, "width", W)
        wf.set_input(N_SIZE, "height", H)
        wf.set_input(N_SAVE, "filename_prefix", f"xenoform/stills/{vibe}")
        jobs.append((noun, base_seed + i, client.submit(wf), place))
    prof = pool_profile(vibe, kind)
    greys: list = []
    incoming = root() / vibe / "_incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    kept_paths = []
    for k, (noun, sd, job, place) in enumerate(jobs):
        if cancel and cancel():
            out["note"] = "stopped"
            break
        try:
            r = job.result()
            o = list(r.get_outputs(N_SAVE)) or list(r.outputs)
            src = incoming / f"{k:03d}_{slug(noun)}.png"
            o[0].to_file(str(src))
        except Exception as exc:  # one failed render is one fewer still, not a failed batch
            log.warning("stills %s: %s failed: %s", vibe, noun, exc)
            out["rejected"]["render"] = out["rejected"].get("render", 0) + 1
            out["rejected_n"] += 1
            if progress:
                progress(k + 1, len(jobs), out["kept"])
            continue
        out["made"] += 1
        v = ingest(vibe, src, noun, prof=prof, own=own, extra_greys=greys, seed=sd, kind=kind, place=place)
        src.unlink(missing_ok=True)
        if v["kept"]:
            greys.append(v["grey"])
            out["kept"] += 1
            out["files"].append(v["file"])
            kept_paths.append(v["path"])
        else:
            out["rejected_n"] += 1
            for why in v["why"]:
                out["rejected"][why] = out["rejected"].get(why, 0) + 1
        if progress:
            progress(k + 1, len(jobs), out["kept"])
    try:
        incoming.rmdir()
    except OSError:
        pass
    if sheet and kept_paths:
        name = {"scene": "scenes.jpg", "setting": "settings.jpg"}.get(kind, "sheet.jpg")
        out["sheet"] = str(contact_sheet(kept_paths, root() / vibe / name))
    out["seconds"] = round(time.time() - t0, 1)
    return out


def contact_sheet(paths: list[str | Path], out: Path, cols: int = 6, thumb=(224, 126)) -> Path:
    """A labelled board of the stills, for a look at a batch without opening fifty files."""
    from PIL import ImageDraw

    paths = [Path(p) for p in paths]
    rows = (len(paths) + cols - 1) // cols
    board = Image.new("RGB", (cols * thumb[0], max(1, rows) * (thumb[1] + 16)), (18, 18, 18))
    draw = ImageDraw.Draw(board)
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail(thumb)
        x, y = (i % cols) * thumb[0], (i // cols) * (thumb[1] + 16)
        board.paste(im, (x, y))
        draw.text((x + 4, y + thumb[1] + 2), p.stem[:30], fill=(255, 255, 80))
    board.save(out, quality=88)
    return out


def summary_line(result: dict) -> str:
    """One line for the desk and the CLI: "Kept 30 of 36 · rejected 6 (backdrop 2, cropped 3, soft 1)". A still can
    fail for two reasons, so the reasons can add up to more than the stills rejected."""
    rej = result.get("rejected") or {}
    n_rej = int(result.get("rejected_n", sum(rej.values())))
    bits = ", ".join(f"{k} {v}" for k, v in rej.items())
    line = f"Kept {result.get('kept', 0)} of {result.get('made', result.get('asked', 0))}"
    if n_rej:
        line += f" · rejected {n_rej} ({bits})"
    if result.get("note"):
        line += f" · {result['note']}"
    return line
