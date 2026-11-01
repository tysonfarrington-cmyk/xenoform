"""Clean anchor stills for real-world subjects (planets, the Moon).

Letting a model invent Jupiter gives two Great Red Spots and cartoon bands.
When a shot names a subject in ``configs/anchors.json`` the desk uses the
manifest's public-domain photograph (also listed as a kind=image item in assets/library/manifest.json) as the first/last keyframe instead of a
painted still, with a hardened prompt and negative and a lower freedom (the
guide strength stays high and the morph's end guide is not relaxed).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "configs" / "anchors.json"
STATIC = Path(__file__).resolve().parent / "ui_static"
HARDEN = "photoreal, one single subject, every feature appears once, accurate real-world detail, no duplicated features"
HARD_NEGATIVE = "duplicate features, repeated features, extra copies, cartoon, illustration, warped, melted, deformed"
# Anchored shots get less freedom: the end guide stays at full strength and no
# compression, so the model interpolates the photograph rather than repainting it.
ANCHOR_TUNE = {"guide_end_strength": 1.0, "img_compression": 0, "cfg": 3.0}


@lru_cache(maxsize=2)
def _manifest(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def manifest() -> dict:
    return _manifest(str(MANIFEST))


# What may follow a subject's word and leave it the head of its noun phrase, the thing named ("the moon", "a jellyfish
# under the moon", "the moon rises over the sea"): nothing, a pause, a function word, or a verb or adverb it does. Any
# other word after it makes it a modifier of that word, the first word of a longer noun (the follow-ups of 1 Nov: "moon
# jellyfish" is a jellyfish, "moon rocks" are rocks of the moon, the Glow sea chain's line sent the NASA moon into its
# prompts). Unsure is no: a word this list lacks reads as a noun, so the anchor stays off.
FUNCTION_WORDS = frozenset((
    "a an the and or nor but of to in on at by with for from into onto over under above below beneath behind beside "
    "between among against across through around near along past beyond within without inside outside upon toward "
    "towards up down off out as like than then while when where who which that this these those its it is are was were "
    "be been being am has have had will would can could do does did not no").split())
HEAD_VERBS = frozenset((
    "rise rises rising rose risen set sets setting glow glows glowing glowed shine shines shining shone hang hangs hanging "
    "hung loom looms looming float floats floating drift drifts drifting burn burns burning burned melt melts melting "
    "melted turn turns turning turned become becomes becoming became morph morphs morphing morphed dissolve dissolves "
    "dissolving grow grows growing grew fade fades fading faded appear appears appearing sit sits sitting rest rests "
    "resting fall falls falling fell spin spins spinning orbit orbits orbiting pulse pulses pulsing crack cracks cracking "
    "explode explodes exploding emerge emerges emerging shimmer shimmers shimmering hover hovers hovering watch watches "
    "watching wax waxes waxing wane wanes waning reflect reflects reflecting overhead tonight again slowly gently softly "
    "brightly").split())
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*(?:'s)?|[^\sa-z0-9]")
# a real subject's own features, the ones its NASA photograph is there to keep single (the negatives' "multiple storms,
# extra spots, extra rings"): after the subject's name they leave it the thing shown ("a giant Jupiter storm" is Jupiter
# with its storm, "Saturn's rings" Saturn), where any other noun after it is what the line is about ("moon rocks")
SUBJECT_FEATURES = frozenset("storm storms spot spots ring rings band bands".split())


def head_follower(word: str) -> bool:
    """True when ``word``, coming after a noun, leaves that noun the head of its phrase (a pause, a function word, a verb
    or an adverb); False for a word that makes it a modifier (``moon`` before ``jellyfish``)."""
    w = str(word or "").lower()
    return not w or not w[0].isalnum() or w in FUNCTION_WORDS or w in HEAD_VERBS


def _plural_of(word: str, base: str) -> bool:
    return word in (base, base + "s", base + "es") or (base.endswith("y") and word == base[:-1] + "ies")


def named(word: str, text: str, *, features: frozenset = frozenset()) -> bool:
    """True when ``text`` names ``word`` as a whole noun: whole words only (a hyphen joins a compound: "moon-jellyfish" is
    one word), plural or not, and as the head of its noun phrase, never as the first word of a longer one ("moon
    jellyfish", "moon rocks", "the moon's surface" do not name the moon; "the moon", "a full moon", "a jellyfish under
    the moon", "the moon rises" do). A word in ``features`` after it, possessive or not, leaves it named (a real
    subject's own storms and rings: ``SUBJECT_FEATURES``)."""
    parts = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(word or "").lower())
    if not parts:
        return False
    toks = _TOKEN.findall(str(text or "").lower().replace("’", "'"))
    n = len(parts)
    for i in range(len(toks) - n + 1):
        seg = toks[i:i + n]
        last = seg[-1]
        owner = last.endswith("'s")
        base = last[:-2] if owner else last
        if seg[:-1] != parts[:-1] or not _plural_of(base, parts[-1]):
            continue
        nxt = toks[i + n] if i + n < len(toks) else ""
        if nxt in features:
            return True  # "a giant Jupiter storm", "Saturn's rings": the subject with its own feature
        if not owner and head_follower(nxt):  # "the moon's surface": the moon's, which modifies what comes after it
            return True
    return False


def subject_in(text: str) -> str:
    """The first manifest subject ``text`` names as a whole noun (``named``: "the moon" yes, "moon jellyfish" no, "a
    giant Jupiter storm" yes, its own feature), or ''."""
    for name in manifest():
        if named(name, text, features=SUBJECT_FEATURES):
            return name
    return ""


def anchor_for(text: str) -> dict:
    """``{"name", "path", "prompt", "negative", ...}`` for a named real subject, else {}."""
    name = subject_in(text)
    if not name:
        return {}
    row = dict(manifest()[name])
    path = ROOT / row["file"]
    if not path.is_file():
        return {}
    row["name"] = name
    row["path"] = str(path)
    return row


def harden(prompt: str, text: str = "") -> str:
    """Add single-feature, photoreal constraints when the shot names a real subject."""
    row = anchor_for(text or prompt)
    if not row:
        return prompt
    return f"{prompt}, {row.get('prompt', '')}, {HARDEN}".strip(", ")


def harden_negative(negative: str, text: str) -> str:
    row = anchor_for(text)
    if not row:
        return negative
    return ", ".join(x for x in (negative, row.get("negative", ""), HARD_NEGATIVE) if x)
