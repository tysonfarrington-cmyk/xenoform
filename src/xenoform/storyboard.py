"""Deterministic storyboard planner.

A one-line brief becomes a literal story: one protagonist, a goal, and a payoff.
Each song section is an action shot with a verb, a shot size, and a camera move.
The default join is a hard cut on the bar. A morph is a signature transition,
once or twice, usually on the drop. An optional local model can rephrase the cards when ``XENO_LLM_URL`` is set,
or when Ollama or a ComfyUI chat route is already up. ``plan_storyboard`` itself
stays on the rule parser and does not touch the network.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

BEATS: tuple[str, ...] = ("setup", "rising", "climax", "release")
SHOTS: tuple[str, ...] = ("wide", "close", "macro", "overhead", "tracking", "medium", "reveal")
MOVES: tuple[str, ...] = ("push in", "pull back", "orbit", "follow", "hold")
EDITS: tuple[str, ...] = (
    "dissolve",
    "hard cut",
    "continuous",
    "pour-harden",
    "droplet-burst",
    "ribbon",
    "snap",
    "grow-out",
    "droplet-gather",
    "spike-burst",
    "dive-splash",
    "fly-through",
    "bolt-strike",
    "swim",
)
MOODS: tuple[str, ...] = ("dawn", "neon", "storm", "cold", "forge", "night", "marble", "void")

DEMO_BRIEF = "A rocket's life, from birth to falling back to earth, cold and paranoid."

# Register palette → light, when the brief does not name one.
_PALETTE_MOOD = {
    "violet": "cold",
    "grey-green": "night",
    "gold": "forge",
    "bronze": "marble",
    "neutral": "void",
}

_MOOD_WORDS = {
    "dawn": "dawn",
    "sunrise": "dawn",
    "neon": "neon",
    "storm": "storm",
    "thunder": "storm",
    "cold": "cold",
    "paranoid": "cold",
    "violet": "cold",
    "forge": "forge",
    "gold": "forge",
    "molten": "forge",
    "night": "night",
    "marble": "marble",
    "bronze": "marble",
    "quiet": "night",
}

# Verb phrases. The liquid does these; the form is what it has become.
_VERBS: dict[str, dict[str, str]] = {
    "sphere": {"setup": "gathers into a held sphere", "rising": "tightens", "climax": "takes the whole peak", "release": "lets the sphere go"},
    "rocket": {"setup": "is born", "rising": "climbs its arc", "climax": "spends the arc", "release": "falls back"},
    "bulb": {"setup": "sits dark in the glass", "rising": "flickers awake", "climax": "refuses to go out", "release": "keeps arguing with the dark"},
    "octopus": {"setup": "unfolds in the ink", "rising": "reaches", "climax": "inks the peak", "release": "draws its arms in"},
    "tower": {"setup": "stands up", "rising": "takes the strain", "climax": "splits on the strike", "release": "holds the ruin"},
    "scream": {"setup": "keeps its mouth shut", "rising": "opens", "climax": "becomes a mouth", "release": "goes quiet"},
    "dead-drop": {"setup": "finds the cache", "rising": "waits under the hand", "climax": "is opened once", "release": "is left where it was"},
    "streetlamp": {"setup": "pools one light", "rising": "holds the corner", "climax": "flares and no one stops", "release": "dims to a habit"},
    "typewriter": {"setup": "sits with the cover on", "rising": "takes a line it will not show", "climax": "strikes once", "release": "closes"},
    "briefcase": {"setup": "squares itself", "rising": "keeps the latch shut", "climax": "is the whole plot", "release": "is carried off"},
    "ring": {"setup": "draws itself into a circle", "rising": "refuses to cool", "climax": "burns at the centre", "release": "keeps the circle"},
    "forge": {"setup": "heats before it has a shape", "rising": "takes the tool", "climax": "spills", "release": "cools at the edge"},
    "tree": {"setup": "roots in the dark", "rising": "lifts a crown", "climax": "holds against the gust", "release": "stands after"},
    "mountain": {"setup": "rises as a ridge", "rising": "takes the weather", "climax": "is the peak", "release": "keeps the snow"},
    "coin": {"setup": "is struck blank", "rising": "takes a face", "climax": "is spent", "release": "stays in the hand"},
    "bust": {"setup": "lifts a profile", "rising": "holds still", "climax": "is looked at and does not blink", "release": "is left on the plinth"},
    "legion": {"setup": "becomes a standard", "rising": "advances", "climax": "does not ask", "release": "plants the staff"},
    "lion": {"setup": "sets its weight", "rising": "watches the gate", "climax": "answers the drop", "release": "lies back down"},
}

_DEFAULT_VERB = {
    "setup": "gathers out of the dark",
    "rising": "leans into the climb",
    "climax": "breaks open on the peak",
    "release": "settles, changed",
}

_SHOT_FOR = {"setup": "wide", "rising": "medium", "climax": "close", "release": "reveal"}
_MOVE_FOR_SHOT = {"wide": "pull back", "medium": "follow", "close": "push in", "reveal": "pull back", "macro": "push in", "overhead": "pull back", "tracking": "follow"}
_RISING_VERBS = ("climbs", "turns", "pushes", "crosses")

# Morphs are the signature join. Everything else in a default board is a hard cut.
MORPH_EDITS = {
    "dissolve",
    "pour-harden",
    "ribbon",
    "droplet-burst",
    "grow-out",
    "continuous",
    "droplet-gather",
    "dive-splash",
    "swim",
    "fly-through",
    "spike-burst",
}

SHOT_LENS = {
    "wide": "wide",
    "medium": "studio",
    "close": "studio",
    "reveal": "wide",
    "macro": "macro",
    "overhead": "wide",
    "tracking": "studio",
}
SHOT_ENERGY = {
    "wide": 0.32,
    "medium": 0.5,
    "close": 0.7,
    "reveal": 0.4,
    "macro": 0.84,
    "overhead": 0.4,
    "tracking": 0.58,
}
SHOT_LABEL = {
    "wide": "Wide shot",
    "medium": "Medium shot",
    "close": "Close shot",
    "reveal": "Reveal",
    "macro": "Macro shot",
    "overhead": "Overhead shot",
    "tracking": "Tracking shot",
}
MOVE_BIAS = {"push in": 0.12, "pull back": -0.12, "orbit": 0.05, "follow": 0.08, "hold": 0.0}


def bar_seconds(tempo: float) -> float:
    bpm = float(tempo) if tempo and float(tempo) > 20 else 120.0
    return 4.0 * 60.0 / bpm


def snap_bars(seconds: float, bar: float) -> int:
    if bar <= 0:
        return 1
    return max(1, int(round(max(0.05, float(seconds)) / bar)))


_ARTICLES = {"a", "an", "the"}
_PREP = {"from", "to", "of", "in", "on", "at", "by", "with", "without", "for", "into", "onto", "out", "over", "under", "across", "through", "during"}
_PLACE_PREP = {"from", "in", "on", "at", "into", "onto", "inside", "under", "across", "through", "over", "near", "beside", "along", "around", "to", "beneath", "behind", "above", "below"}
_PARTICLES = {"out", "up", "down", "off", "away", "back"}
_PHRASAL = {"wait", "look", "carry", "run", "take", "hold", "keep", "break", "call", "drop", "pull", "push", "hide", "leave", "come", "go", "set", "work", "watch", "help", "cry", "fill", "stand", "sit", "live", "time"}
_ROLE = {
    "keeper", "captain", "guard", "driver", "pilot", "warden", "watchman", "attendant",
    "sailor", "farmer", "archivist", "baker", "astronaut", "diver", "conductor", "shepherd",
    "child", "clerk", "nurse", "rider",
}
_PLACE_WORDS = (
    "jupiter", "earth", "moon", "mars", "kitchen", "street", "beach", "desert", "ocean",
    "station", "apartment", "bedroom", "alley", "lighthouse", "harbour", "harbor", "shore",
    "cliff", "forest", "cabin", "dock", "pier", "island", "yard", "hall", "reef", "stacks",
)
_IRREGULAR = {
    "go": ("goes", "went", "going"),
    "see": ("sees", "saw", "seeing"),
    "come": ("comes", "came", "coming"),
    "run": ("runs", "ran", "running"),
    "fall": ("falls", "fell", "falling"),
    "leave": ("leaves", "left", "leaving"),
    "keep": ("keeps", "kept", "keeping"),
    "hold": ("holds", "held", "holding"),
    "find": ("finds", "found", "finding"),
    "take": ("takes", "took", "taking"),
    "give": ("gives", "gave", "giving"),
    "bring": ("brings", "brought", "bringing"),
    "catch": ("catches", "caught", "catching"),
    "fight": ("fights", "fought", "fighting"),
    "fly": ("flies", "flew", "flying"),
    "swim": ("swims", "swam", "swimming"),
    "break": ("breaks", "broke", "breaking"),
    "rise": ("rises", "rose", "rising"),
    "lose": ("loses", "lost", "losing"),
    "sleep": ("sleeps", "slept", "sleeping"),
    "seek": ("seeks", "sought", "seeking"),
    "lead": ("leads", "led", "leading"),
    "meet": ("meets", "met", "meeting"),
    "build": ("builds", "built", "building"),
    "stand": ("stands", "stood", "standing"),
    "sit": ("sits", "sat", "sitting"),
    "hide": ("hides", "hid", "hiding"),
    "wake": ("wakes", "woke", "waking"),
    "be": ("is", "was", "being"),
    "become": ("becomes", "became", "becoming"),
    "grow": ("grows", "grew", "growing"),
    "cut": ("cuts", "cut", "cutting"),
    "set": ("sets", "set", "setting"),
    "let": ("lets", "let", "letting"),
    "put": ("puts", "put", "putting"),
    "hit": ("hits", "hit", "hitting"),
}
_REGULAR = (
    "rescue", "save", "wait", "walk", "watch", "live", "follow", "carry", "open", "close",
    "look", "return", "stay", "share", "cross", "enter", "climb", "pull", "push", "lift",
    "chase", "flee", "guide", "guard", "free", "steal", "sail", "burn", "mend", "bury",
    "dig", "plant", "sing", "call", "hunt", "reach", "turn", "face", "shelter", "brave",
    "outlast", "drag", "haul", "win", "answer", "drop", "lock", "unlock", "search",
    "discover", "protect", "abandon", "approach", "escape", "survive", "help", "start",
    "finish", "weather", "transform", "morph", "melt",
)
# A form change, not an action. ``become`` takes a noun. The others need ``into``.
_CHANGE_INTO = frozenset({"turn", "transform", "morph", "melt", "grow"})
_CHANGE_BASES = frozenset({"become"}) | _CHANGE_INTO


def _third_person(base: str) -> str:
    if base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        return base[:-1] + "ies"
    if base.endswith(("s", "x", "z", "ch", "sh", "o")):
        return base + "es"
    return base + "s"


def _gerund(base: str) -> str:
    if base.endswith("ie"):
        return base[:-2] + "ying"
    if base.endswith("e") and not base.endswith("ee"):
        return base[:-1] + "ing"
    return base + "ing"


def _past(base: str) -> str:
    if base.endswith("e"):
        return base + "d"
    if base.endswith("y") and len(base) > 1 and base[-2] not in "aeiou":
        return base[:-1] + "ied"
    return base + "ed"


def _lexicon() -> dict[str, dict[str, str]]:
    lex: dict[str, dict[str, str]] = {}

    def add(base: str, third: str, past: str, gerund: str) -> None:
        row = {"base": base, "third": third}
        lex[base] = {**row, "kind": "base"}
        lex.setdefault(third, {**row, "kind": "third"})
        lex.setdefault(past, {**row, "kind": "past"})
        lex.setdefault(gerund, {**row, "kind": "gerund"})

    for base, forms in _IRREGULAR.items():
        add(base, forms[0], forms[1], forms[2])
    for base in _REGULAR:
        if base in _IRREGULAR:
            continue
        add(base, _third_person(base), _past(base), _gerund(base))
    return lex


_LEXICON = _lexicon()
_VERB_STOP = set(_LEXICON) | {"who", "that", "which", "while", "and", "or", "is", "are", "was", "were"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z][a-z']*", str(text or "").lower())


def _read_np(tokens: list[str], start: int) -> tuple[list[str], int]:
    """Nouns until a verb or a preposition. Articles are skipped."""
    words: list[str] = []
    index = start
    while index < len(tokens):
        word = tokens[index]
        if word in _ARTICLES:
            if words:
                break
            index += 1
            continue
        if word == "of" and words:
            nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
            nxt_info = _LEXICON.get(nxt)
            if nxt and nxt not in _ARTICLES and nxt not in _PREP and nxt not in _PLACE_PREP and nxt != "and":
                if not (nxt_info and nxt_info["kind"] != "base"):
                    words.append("of")
                    index += 1
                    continue
            break
        if word in _PREP or word in _PLACE_PREP or word == "and":
            break
        info = _LEXICON.get(word)
        if info and words and info["kind"] != "base":
            break
        words.append(word)
        index += 1
        if len(words) >= 4:
            break
    return words, index


def _verb_at(tokens: list[str]) -> int | None:
    hits = []
    for index, word in enumerate(tokens):
        if word not in _LEXICON:
            continue
        prior = [item for item in tokens[:index] if item not in _ARTICLES and item not in _PREP and item != "and"]
        if prior:
            hits.append(index)
    conjugated = [index for index in hits if _LEXICON[tokens[index]]["kind"] != "base"]
    if conjugated:
        return conjugated[0]
    return hits[0] if hits else None


def _empty_svo() -> dict[str, str]:
    return {
        "subject": "",
        "verb": "",
        "base": "",
        "third": "",
        "object": "",
        "setting": "",
        "threat": "",
        "threat_prep": "",
        "place_prep": "",
        "particle": "",
        "prop_role": "",
    }


def _is_place_noun(noun: str) -> bool:
    words = [word for word in str(noun or "").split() if word and word not in _ARTICLES]
    if not words:
        return False
    return any(word in _PLACE_WORDS for word in words)


def _parse_svo(text: str) -> dict[str, str]:
    """Subject, verb, object, and setting. Empty when the line has no verb.

    ``from a storm`` is a threat, not a place, unless the noun is a real place
    (``from the dock``). A phrasal particle keeps its object as the threat
    (``wait out the storm``). When the brief names no place, a role compound
    such as ``lighthouse keeper`` lends its place word.
    """
    empty = _empty_svo()
    tokens = _tokens(text)
    at = _verb_at(tokens)
    if at is None:
        return empty
    info = _LEXICON[tokens[at]]
    subject_tokens = tokens[:at]
    hero_tokens = subject_tokens
    prop_words: list[str] = []
    prop_role = "object"
    if "and" in subject_tokens:
        split = subject_tokens.index("and")
        hero_tokens = subject_tokens[:split]
        prop_words, _ = _read_np(subject_tokens, split + 1)
        prop_role = "companion"
    hero_words, _ = _read_np(hero_tokens, 0)
    if not hero_words:
        return empty
    rest = tokens[at + 1 :]
    particle = ""
    if rest and rest[0] in _PARTICLES and info["base"] in _PHRASAL:
        particle = rest[0]
        rest = rest[1:]
    if prop_role != "companion" and rest:
        prop_words, cursor = _read_np(rest, 0)
        rest = rest[cursor:]
    threat = ""
    threat_prep = ""
    if particle and rest and rest[0] not in _PLACE_PREP:
        threat_words, cursor = _read_np(rest, 0)
        rest = rest[cursor:]
        if threat_words:
            threat = " ".join(threat_words)
            threat_prep = particle
    elif prop_role == "companion":
        cursor = 0
        while cursor < len(rest) and rest[cursor] not in _PLACE_PREP:
            cursor += 1
        rest = rest[cursor:]
    setting = ""
    place_prep = ""
    if rest and rest[0] in _PLACE_PREP:
        prep = rest[0]
        place_words, _ = _read_np(rest, 1)
        noun = " ".join(place_words)
        if prep == "from" and noun and not _is_place_noun(noun):
            threat = noun
            threat_prep = "from"
        elif noun and _is_place_noun(noun):
            setting = noun
            place_prep = prep
    if not setting:
        for word in _PLACE_WORDS:
            if word in tokens and word not in hero_words and word not in prop_words and word not in threat.split():
                setting = word
                place_prep = "at"
                break
    if not setting and len(hero_words) >= 2 and hero_words[-1] in _ROLE and hero_words[0] in _PLACE_WORDS:
        setting = hero_words[0]
        place_prep = "at"
    return {
        "subject": " ".join(hero_words),
        "verb": tokens[at],
        "base": info["base"],
        "third": info["third"],
        "object": " ".join(prop_words),
        "setting": setting,
        "threat": threat,
        "threat_prep": threat_prep,
        "place_prep": place_prep,
        "particle": particle,
        "prop_role": prop_role if prop_words else "",
    }


def _np_article(tokens: list[str], start: int) -> tuple[str, list[str], int]:
    """Article plus the noun phrase. The article is empty when the brief names none."""
    article = ""
    index = start
    if index < len(tokens) and tokens[index] in _ARTICLES:
        article = tokens[index]
        index += 1
    words, cursor = _read_np(tokens, index)
    return article, words, cursor


def _place_from_tokens(tokens: list[str]) -> tuple[str, str]:
    """The first real place after a place preposition. A verb is not a place."""
    for index, word in enumerate(tokens):
        if word not in _PLACE_PREP:
            continue
        words, _cursor = _read_np(tokens, index + 1)
        noun = " ".join(words)
        if noun and _is_place_noun(noun):
            return noun, word
    return "", ""


def _subject_np(tokens: list[str]) -> str:
    words, _cursor = _read_np(tokens, 0)
    return " ".join(words)


def _form_change(text: str) -> dict[str, str] | None:
    """A transformation in the brief. Empty when the line does not change form.

    ``becomes a horse`` and ``turns into a flower`` name the new form.
    A verb before that (``runs``) stays the action. ``along a beach`` stays the place.
    """
    tokens = _tokens(text)
    at = None
    for index, word in enumerate(tokens):
        info = _LEXICON.get(word)
        if not info or info["kind"] == "base":
            continue
        base = info["base"]
        if base == "become":
            at = index
            break
        if base in _CHANGE_INTO and index + 1 < len(tokens) and tokens[index + 1] == "into":
            at = index
            break
    if at is None:
        return None
    info = _LEXICON[tokens[at]]
    if info["base"] == "become":
        article, words, cursor = _np_article(tokens, at + 1)
        phrase = tokens[at]
    else:
        article, words, cursor = _np_article(tokens, at + 2)
        phrase = f"{tokens[at]} into"
    if not words:
        return None
    head = tokens[:at]
    while head and head[-1] in {"and", "then"}:
        head.pop()
    tail = tokens[cursor:]
    motion = _empty_svo()
    if _verb_at(head) is not None:
        motion = _parse_svo(" ".join(head))
    if motion["base"] in _CHANGE_BASES:
        motion = _empty_svo()
    subject = motion["subject"] or _subject_np(head)
    setting = motion["setting"]
    place_prep = motion["place_prep"]
    if not setting:
        setting, place_prep = _place_from_tokens(head)
    if not setting:
        setting, place_prep = _place_from_tokens(tail)
    return {
        "subject": subject,
        "becomes": " ".join(words),
        "becomes_article": article,
        "change_phrase": phrase,
        "change_verb": tokens[at],
        "setting": setting,
        "place_prep": place_prep,
        "motion_verb": motion["verb"],
        "motion_base": motion["base"],
        "motion_third": motion["third"],
        "threat": motion["threat"],
        "threat_prep": motion["threat_prep"],
    }


def parse_brief(text: str) -> dict[str, Any]:
    raw = " ".join(str(text or "").split())
    low = raw.lower()
    moods: list[str] = []
    for word, mood in _MOOD_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", low) and mood not in moods:
            moods.append(mood)
    tone_bits = []
    for word in ("cold", "paranoid", "quiet", "violent", "tender"):
        if re.search(rf"\b{word}\b", low):
            tone_bits.append(word)
    journey = re.search(r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:,|;|$)", low)
    named = re.search(r"\b(?:a|an|the)\s+([a-z][a-z' -]{1,40}?)(?:'s|s')\s+life\b", low)
    svo = _empty_svo()
    change: dict[str, str] | None = None
    if named:
        svo["subject"] = named.group(1).strip()
        for word in _PLACE_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", low) and word not in svo["subject"].split():
                svo["setting"] = word
                break
    else:
        head = re.split(r"[,:;]", low, maxsplit=1)[0]
        change = _form_change(head)
        if change:
            svo["subject"] = change["subject"]
            svo["setting"] = change["setting"]
            svo["place_prep"] = change["place_prep"]
            svo["threat"] = change["threat"]
            svo["threat_prep"] = change["threat_prep"]
            if change["motion_verb"]:
                svo["verb"] = change["motion_verb"]
                svo["base"] = change["motion_base"]
                svo["third"] = change["motion_third"]
            else:
                svo["verb"] = change["change_verb"]
                svo["base"] = _LEXICON[change["change_verb"]]["base"]
                svo["third"] = _LEXICON[change["change_verb"]]["third"]
        else:
            svo = _parse_svo(head)
    return {
        "text": raw,
        "subject": svo["subject"],
        "verb": svo["verb"],
        "base": svo["base"],
        "third": svo["third"],
        "object": svo["object"],
        "setting": svo["setting"],
        "threat": svo.get("threat") or "",
        "threat_prep": svo.get("threat_prep") or "",
        "place_prep": svo.get("place_prep") or "",
        "particle": svo.get("particle") or "",
        "prop_role": svo.get("prop_role") or "",
        "becomes": (change or {}).get("becomes") or "",
        "becomes_article": (change or {}).get("becomes_article") or "",
        "change_phrase": (change or {}).get("change_phrase") or "",
        "change_verb": (change or {}).get("change_verb") or "",
        "motion_verb": (change or {}).get("motion_verb") or "",
        "motion_base": (change or {}).get("motion_base") or "",
        "motion_third": (change or {}).get("motion_third") or "",
        "origin": journey.group(1).strip(" .") if journey else "",
        "destination": journey.group(2).strip(" .") if journey else "",
        "moods": moods,
        "tone": " and ".join(tone_bits),
    }


def hero_has_verb(name: str) -> bool:
    """True when a conjugated verb is glued onto the hero."""
    for word in _tokens(name):
        info = _LEXICON.get(word)
        if info and info["kind"] in {"third", "past", "gerund"}:
            return True
    return False


def brief_cast(text: str) -> dict[str, str]:
    """Hero, key prop, place, and threat read from the brief. Empty when the line names none."""
    parsed = parse_brief(text)
    hero = str(parsed.get("subject") or "")
    prop = str(parsed.get("object") or "")
    place = str(parsed.get("setting") or "")
    threat = str(parsed.get("threat") or "")
    if prop in {hero, place, threat} or prop in _PLACE_WORDS:
        prop = ""
    if place == hero:
        place = ""
    if threat in {hero, place, prop}:
        threat = ""
    becomes = str(parsed.get("becomes") or "")
    if becomes in {hero, place, prop}:
        becomes = ""
    return {"hero": hero, "prop": prop, "place": place, "threat": threat, "becomes": becomes}


def _spoken(form: dict) -> str:
    form_id = str(form.get("id") or "liquid")
    if form_id in _VERBS:
        return form_id.replace("-", " ")
    name = str(form.get("name") or form.get("noun") or "liquid").strip()
    return name.split(",")[0].lower()


def _form_index_by_name(brief_low: str, catalog: list[dict]) -> str:
    """A form the brief actually names, preferring a longer name."""
    hits = []
    for form in catalog:
        form_id = str(form.get("id") or "")
        spoken = form_id.replace("-", " ")
        name = str(form.get("name") or "").lower()
        if spoken and re.search(rf"\b{re.escape(spoken)}\b", brief_low):
            hits.append((len(spoken), form_id))
        elif name and name in brief_low:
            hits.append((len(name), form_id))
    if not hits:
        return ""
    hits.sort(reverse=True)
    return hits[0][1]


def climax_index(sections: list[dict], override: int | None = None) -> int:
    if not sections:
        return 0
    if override is not None and 0 <= int(override) < len(sections):
        return int(override)
    drops = [i for i, section in enumerate(sections) if str(section.get("label")) == "drop"]
    pool = drops or list(range(len(sections)))
    return max(pool, key=lambda i: float(sections[i].get("level") or sections[i].get("energy") or 0.0))


def assign_beats(n: int, climax: int) -> list[str]:
    beats = []
    for index in range(n):
        if index == climax:
            beats.append("climax")
        elif index < climax:
            beats.append("setup" if index == 0 else "rising")
        else:
            beats.append("release")
    return beats


def _signature_edit(register: dict) -> str:
    """The one morph a board is allowed to spend, taken from the register's drop."""
    transitions = register.get("transitions") or {}
    chosen = str(transitions.get("drop") or "droplet-burst")
    mapped = {"snap": "droplet-burst", "hard cut": "droplet-burst"}.get(chosen, chosen)
    if mapped not in MORPH_EDITS:
        mapped = "droplet-burst"
    return mapped


def _edit_for(beat: str, register: dict) -> str:
    transitions = register.get("transitions") or {}
    if beat == "climax":
        chosen = str(transitions.get("drop") or "snap")
    elif beat == "setup":
        chosen = str(transitions.get("calm") or "pour-harden")
    elif beat == "rising":
        chosen = str(transitions.get("build") or "ribbon")
    else:
        chosen = str(transitions.get("outro") or transitions.get("release") or "grow-out")
    return {
        "snap": "hard cut",
        "pour-harden": "dissolve",
        "grow-out": "continuous",
    }.get(chosen, chosen if chosen in EDITS else "ribbon")


def _destination_line(subject: str, destination: str) -> str:
    dest = destination.strip()
    if dest.startswith("falling "):
        return f"the {subject} falls {dest[len('falling '):]}, changed"
    if dest.startswith("returning "):
        return f"the {subject} returns {dest[len('returning '):]}, changed"
    return f"the {subject} arrives at {dest}, changed"


def _template_hero(name: str) -> bool:
    """True when the hero is one of the register forms, so the liquid verbs still apply."""
    bare = str(name or "").lower().removeprefix("the ").strip()
    key = bare.replace(" ", "-")
    return bool(bare) and (bare in _VERBS or key in _VERBS)


def _protagonist_name(parsed: dict, opening_form: dict) -> str:
    subject = " ".join(str(parsed.get("subject") or parsed.get("hero") or "").split())
    if subject:
        return subject
    return _spoken(opening_form)


def _spine(parsed: dict, name: str) -> tuple[str, str, str]:
    who = f"the {name}" if not name.startswith("the ") else name
    origin = str(parsed.get("origin") or "")
    destination = str(parsed.get("destination") or "")
    if origin and destination:
        goal = f"{who} goes from {origin} to {destination}"
        payoff = _destination_line(name, destination)
    else:
        goal = f"follow {who} through the song"
        payoff = f"{who} lands the last shot, changed"
    return who, goal, payoff


def _verb_for(beat: str, *, first: bool, last: bool, parsed: dict, rising_index: int) -> str:
    if first and parsed.get("origin") in {"birth", "a birth", "the birth"}:
        return "is born"
    if last and parsed.get("destination"):
        return "lands"
    if beat == "rising":
        return _RISING_VERBS[rising_index % len(_RISING_VERBS)]
    return {"setup": "enters", "climax": "hits", "release": "leaves"}.get(beat, "moves")


# The spine is a verb ("cross", "open", "hold"). Never put "the" in front of it:
# "moves closer to the cross" reads as a noun and garbles the story.
_SPINE = {
    "setup": ("begins to {base}", "sets out to {base}"),
    "rising": ("closes in to {base}", "gets ready to {base}", "keeps on", "draws near"),
    "climax": ("{third}",),
    "release": ("comes to rest", "lets go", "settles"),
}
_BARE = frozenset("one two three next other another it them this that these those".split())
_QUANT = ("one ", "two ", "three ", "every ", "each ", "some ", "the ", "a ", "an ")


def _phrase(text: str) -> str:
    """A prop, place or threat that can follow "the". Drops a bare "one" or "next"."""
    words = str(text or "").strip()
    low = words.lower()
    if not words or low in _BARE:
        return ""
    for lead in _QUANT:
        if low.startswith(lead) and len(words) > len(lead):
            return words[len(lead):].strip()
    return words
_VARIED = {
    "setup": ("arrives", "steps in", "comes up"),
    "rising": ("keeps watch", "looks again", "moves closer", "holds the line"),
    "climax": ("holds on", "takes the moment", "commits"),
    "release": ("stays", "lets go", "remains"),
}


def _join(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _pick_line(options: list[tuple[str, str]], beat: str, counts: dict[str, int]) -> tuple[str, str]:
    index = counts.get(beat, 0)
    counts[beat] = index + 1
    verb, action = options[index % len(options)]
    return verb, action


def _natural_line(
    who: str,
    beat: str,
    parsed: dict,
    counts: dict[str, int],
    *,
    last: bool,
) -> tuple[str, str]:
    """One spoken line for a parsed hero. The climax does the verb to the prop.

    A threat keeps its own preposition (``from the storm``, ``out the storm``).
    A place keeps the brief's preposition (``into the stacks``). Setup, approach,
    and release each say that differently, so the board does not repeat one tail.
    """
    base = str(parsed.get("base") or "")
    third = str(parsed.get("third") or base)
    prop = _phrase(parsed.get("prop") or "")
    place = _phrase(parsed.get("place") or "")
    threat = _phrase(parsed.get("threat") or "")
    role = str(parsed.get("prop_role") or "object")
    place_prep = str(parsed.get("place_prep") or "at")
    threat_prep = str(parsed.get("threat_prep") or "from")
    particle = str(parsed.get("particle") or "")
    obj = f"the {prop}" if prop else ""
    place_bit = f"{place_prep} the {place}" if place else ""
    threat_bit = f"{threat_prep} the {threat}" if threat else ""
    with_prop = f"with the {prop}" if prop else ""

    if beat == "climax":
        if role == "companion" and particle and threat:
            return third, _join(who, third, particle, f"the {threat}")
        if role == "companion" and prop:
            return third, _join(who, third, with_prop, place_bit)
        if obj and threat:
            return third, _join(who, third, obj, threat_bit)
        if obj and place:
            return third, _join(who, third, obj, place_bit)
        return third, _join(who, third, obj, place_bit, threat_bit)

    if beat == "setup":
        if role == "companion":
            return "begins", _join(who, "begins to", base, with_prop, f"at the {place}" if place else "")
        if obj and threat and place:
            return "sets out", _join(who, "sets out from the", place, "to", base, obj)
        if obj and place:
            return "begins", _join(who, "begins to", base, obj, place_bit)
        if obj and threat:
            return "begins", _join(who, "begins to", base, obj, threat_bit)
        return "begins", _join(who, "begins to", base, obj, place_bit)

    if beat == "release" and last:
        if role == "companion" and prop:
            return "goes", _join(who, "goes on to", base, with_prop, "one last time")
        if obj and threat:
            return "goes", _join(who, "goes on to", base, obj, f"{threat_prep} the {threat}")
        if obj and place:
            return "goes", _join(who, "goes on to", base, obj, place_bit, "one last time")
        if place:
            return "goes", _join(who, "goes on to", base, place_bit, "one last time")
        return "goes", _join(who, "goes on to", base, obj, "one last time")

    if beat == "rising" and role == "companion":
        return _pick_line(
            [
                ("keeps", _join(who, "keeps watch", with_prop)),
                ("looks", _join(who, "looks for a break", f"in the {threat}" if threat else with_prop)),
                ("stays", _join(who, "stays", with_prop, f"at the {place}" if place else "")),
                ("stands", _join(who, "stands through the", threat or place, with_prop)),
            ],
            beat,
            counts,
        )

    if beat == "rising" and obj and threat and place:
        return _pick_line(
            [
                ("searches", _join(who, "searches the", place, "for", obj)),
                ("spots", _join(who, "spots", obj, "in the", threat)),
                ("reaches", _join(who, "reaches", obj, "ahead of the", threat)),
                ("braces", _join(who, "braces at the", place, "as the", threat, "closes")),
            ],
            beat,
            counts,
        )

    if beat == "rising" and obj and place:
        return _pick_line(
            [
                ("nears", _join(who, "nears the", place, "with", obj)),
                ("holds", _join(who, "holds", obj, "toward the", place)),
                ("crosses", _join(who, "crosses toward the", place, "with", obj)),
                ("keeps", _join(who, "keeps", obj, "close at the", place)),
            ],
            beat,
            counts,
        )

    if beat == "rising" and obj and threat:
        return _pick_line(
            [
                ("searches", _join(who, "searches for", obj, threat_bit)),
                ("spots", _join(who, "spots", obj, threat_bit)),
                ("reaches", _join(who, "reaches", obj, "ahead of the", threat)),
                ("braces", _join(who, "braces", threat_bit, "and keeps", obj, "in sight")),
            ],
            beat,
            counts,
        )

    if beat == "rising" and obj:
        return _pick_line(
            [
                ("moves", _join(who, "moves closer to", obj)),
                ("looks", _join(who, "looks again at", obj)),
                ("keeps", _join(who, "keeps going toward", obj)),
                ("draws", _join(who, "draws near", obj)),
            ],
            beat,
            counts,
        )

    if beat == "rising":
        return _pick_line(
            [
                ("moves", _join(who, "moves closer")),
                ("looks", _join(who, "looks again")),
                ("keeps", _join(who, "keeps going", place_bit)),
                ("draws", _join(who, "draws in")),
            ],
            beat,
            counts,
        )

    if role == "companion":
        return _pick_line(
            [
                ("steps", _join(who, "steps back", with_prop, f"at the {place}" if place else "")),
                ("eases", _join(who, "eases off", f"after the {threat}" if threat else "", with_prop)),
                ("rests", _join(who, "rests", with_prop, f"at the {place}" if place else "")),
            ],
            beat,
            counts,
        )
    if obj and threat and place:
        return _pick_line(
            [
                ("shelters", _join(who, "shelters", obj, f"at the {place}")),
                ("walks", _join(who, "walks", obj, "clear of the", threat)),
                ("dries", _join(who, "dries", obj, "after the", threat)),
            ],
            beat,
            counts,
        )
    if obj and place:
        return _pick_line(
            [
                ("lowers", _join(who, "lowers", obj, place_bit)),
                ("rests", _join(who, "rests", obj, "at the", place)),
                ("sets", _join(who, "sets", obj, "down at the", place)),
            ],
            beat,
            counts,
        )
    if obj:
        return _pick_line(
            [
                ("pauses", _join(who, "pauses at", obj)),
                ("rests", _join(who, "rests by", obj)),
                ("leaves", _join(who, "leaves", obj, "behind")),
            ],
            beat,
            counts,
        )
    return _pick_line(
        [
            ("settles", _join(who, "settles", place_bit)),
            ("lets", _join(who, "lets go")),
            ("rests", _join(who, "comes to rest", place_bit)),
        ],
        beat,
        counts,
    )


def _counted_verb(table: dict[str, tuple[str, ...]], beat: str, counts: dict[str, int], **fills: str) -> str:
    choices = table.get(beat) or table["rising"]
    index = counts.get(beat, 0)
    counts[beat] = index + 1
    return choices[index % len(choices)].format(**fills)


def _action_line(
    who: str,
    verb: str,
    form: dict,
    parsed: dict,
    *,
    first: bool,
    last: bool,
    callback: str,
    prop: str = "",
    place: str = "",
) -> str:
    if last and callback.strip():
        return " ".join(callback.split())[:180]
    spoken = _spoken(form)
    bare = who[4:] if who.startswith("the ") else who
    if first and parsed.get("origin"):
        origin = str(parsed["origin"])
        if origin in {"birth", "a birth", "the birth"}:
            line = f"{who} is born"
        else:
            line = f"{who} begins at {origin}"
        if parsed.get("tone"):
            line += ", " + parsed["tone"]
        return line
    if last and parsed.get("destination"):
        return _destination_line(bare, str(parsed["destination"]))
    if _template_hero(bare) and spoken and spoken != bare and verb not in {"is born", "lands"}:
        line = f"{who} {verb} past the {spoken}"
    else:
        line = f"{who} {verb}"
        if not _template_hero(bare):
            if prop:
                line += f" with the {prop}"
            if place and f"at the {place}" not in line:
                line += f" at the {place}"
    if verb == "hits" and parsed.get("tone"):
        line += ", " + parsed["tone"]
    return line


def _guide(scene: dict) -> str:
    shot = str(scene.get("shot") or "wide")
    phrase = SHOT_LABEL.get(shot, "Wide shot")
    who = scene.get("protagonist") or "the subject"
    verb = scene.get("verb") or "moves"
    action = scene.get("action") or ""
    move = scene.get("move") or "hold"
    mood = scene.get("mood") or "void"
    if scene.get("signature"):
        return (
            f"Signature transition. {phrase} of {who}. Action: {verb}. {action}. "
            f"Camera {move}. {mood} light."
        )
    return (
        f"First frame only. {phrase} of {who}. Action: {verb}. {action}. "
        f"Camera {move}. Hard cut on the bar. {mood} light."
    )


def transition_for_edit(edit: str) -> str:
    from xenoform.director import TRANSITIONS

    mapped = {
        "dissolve": "pour-harden",
        "hard cut": "snap",
        "continuous": "grow-out",
        "bolt-strike hold": "bolt-strike",
        "swim hold": "swim",
    }.get(edit, edit)
    return mapped if mapped in TRANSITIONS else "ribbon"


def blocks_from_scenes(scenes: list[dict]) -> list[dict[str, Any]]:
    blocks = []
    last = len(scenes) - 1
    for index, scene in enumerate(scenes):
        beat = str(scene.get("beat") or "rising")
        if beat == "climax":
            energy = "drop"
        elif beat == "setup":
            energy = "calm"
        elif beat == "rising":
            energy = "build"
        elif index == last:
            energy = "outro"
        else:
            energy = "release"
        hold = float(scene.get("hold") or scene.get("seconds") or 1.0)
        blocks.append(
            {
                "form": str(scene.get("form") or "sphere"),
                "hold": round(max(0.2, hold), 2),
                "transition": transition_for_edit(str(scene.get("edit") or "ribbon")),
                "energy": energy,
            }
        )
    return blocks


def camera_for_scene(scene: dict) -> dict[str, Any]:
    shot = str(scene.get("shot") or "wide")
    move = str(scene.get("move") or "hold")
    if shot not in SHOT_ENERGY:
        shot = "wide"
    if move not in MOVE_BIAS:
        move = "hold"
    energy = min(1.0, max(0.0, SHOT_ENERGY[shot] + MOVE_BIAS[move]))
    push = 0.62 if move == "push in" else 0.38 if move == "pull back" else 0.5
    return {
        "camera_energy": round(energy, 4),
        "camera_push": round(push, 4),
        "lens": SHOT_LENS[shot],
        "shot": shot,
        "move": move,
    }


def _catalog(register: dict, customs: list[dict] | None) -> list[dict]:
    from xenoform.director import FORM_PACK, form_by_id

    rows = [dict(form) for form in FORM_PACK]
    for custom in customs or []:
        if custom.get("id"):
            rows.append(
                {
                    "id": custom["id"],
                    "name": custom.get("name") or custom.get("noun") or "Custom",
                    "noun": custom.get("noun") or "",
                }
            )
    # Keep register order available even if a form id is missing from the pack.
    for form_id in list(register.get("forms") or []):
        if form_by_id(form_id, customs) is None and not any(row["id"] == form_id for row in rows):
            rows.append({"id": form_id, "name": form_id})
    return rows


def _pick_forms(
    register: dict,
    n: int,
    climax: int,
    catalog: list[dict],
    named: str,
    motif: str,
    callback: str,
) -> list[str]:
    order = [str(form) for form in (register.get("forms") or []) if form]
    if not order:
        order = [named] if named else ["sphere"]
    drop_forms = [str(form) for form in (register.get("drop_forms") or []) if form] or order[-1:]
    calm = [form for form in order if form not in drop_forms] or list(order)
    known = {str(form.get("id")) for form in catalog}
    forms: list[str] = []
    cursor = 0
    for index in range(n):
        if index == climax:
            choice = drop_forms[0]
        elif index == 0 and named and named in known:
            choice = named
        else:
            choice = calm[cursor % len(calm)]
            cursor += 1
            if forms and choice == forms[-1]:
                choice = calm[cursor % len(calm)]
                cursor += 1
        if forms and choice == forms[-1] and not (motif and choice == motif):
            for candidate in calm + drop_forms:
                if candidate != forms[-1]:
                    choice = candidate
                    break
        forms.append(choice)
    if motif and motif in known:
        for index in range(1, n):
            if index != climax:
                forms[index] = motif
                break
    if callback.strip() and n:
        target = _form_index_by_name(callback.lower(), catalog) or forms[0]
        forms[-1] = target
    return forms


def _score(scenes: list[dict], sections: list[dict], motif: str) -> dict[str, Any]:
    climax = climax_index(sections)
    on_peak = any(scene.get("beat") == "climax" and int(scene.get("index", -1)) == climax for scene in scenes)
    loops = 0
    for left, right in zip(scenes, scenes[1:]):
        if left.get("form") and left.get("form") == right.get("form") and left.get("form") != motif:
            loops += 1
    hook = bool(scenes) and scenes[0].get("beat") == "setup" and len(str(scenes[0].get("action") or "")) > 8
    varied = len({scene.get("edit") for scene in scenes}) >= min(3, len(scenes))
    score = (25 if on_peak else 0) + (12 if hook else 0) + (6 if varied else 0) - 20 * loops
    return {"score": score, "loops": loops, "hook": hook, "climax_on_peak": on_peak}


def _gerund_of(base: str) -> str:
    for word, row in _LEXICON.items():
        if row["base"] == base and row["kind"] == "gerund":
            return word
    return _gerund(base) if base else ""


def _slug(name: str) -> str:
    return "-".join(str(name or "").split()) or "subject"


def _place_bit(parsed: dict) -> str:
    place = str(parsed.get("place") or parsed.get("setting") or "")
    if not place:
        return ""
    prep = str(parsed.get("place_prep") or "at")
    return f"{prep} the {place}"


def _spoken_target(parsed: dict) -> str:
    target = str(parsed.get("becomes") or "")
    article = str(parsed.get("becomes_article") or "")
    if article and target:
        return f"{article} {target}"
    return target


def _change_spine(parsed: dict) -> tuple[str, str]:
    subject = f"the {parsed.get('subject') or 'subject'}"
    phrase = str(parsed.get("change_phrase") or "becomes")
    place = _place_bit(parsed)
    goal = _join(subject, phrase, _spoken_target(parsed))
    motion = str(parsed.get("motion_third") or "")
    payoff = _join(f"the {parsed.get('becomes') or 'subject'}", motion or "holds", place)
    return goal, payoff


_BEFORE_MOTION = (
    "begins to {base}",
    "{third}",
    "keeps {gerund}",
    "stays {gerund}",
    "is {gerund}",
    "goes on {gerund}",
)
_AFTER_MOTION = (
    "{third}",
    "keeps {gerund}",
    "stays {gerund}",
    "is {gerund}",
    "goes on {gerund}",
    "carries on {gerund}",
)
_BEFORE_STILL = ("begins", "holds", "waits", "rests", "pauses", "settles")
_AFTER_STILL = ("holds", "rests", "settles", "stays", "remains", "stands")


def _change_who(parsed: dict, index: int, peak: int) -> str:
    subject = str(parsed.get("subject") or "subject")
    target = str(parsed.get("becomes") or subject)
    if index > peak:
        return f"the {target}"
    return f"the {subject}"


def _change_line(parsed: dict, index: int, peak: int, who: str, counts: dict[str, int]) -> tuple[str, str]:
    """Scenes before the change stay subject A. The climax is the change. Scenes after are subject B.

    The action verb stays a verb. It is never turned into a prop.
    """
    place = _place_bit(parsed)
    phrase = str(parsed.get("change_phrase") or "becomes")
    spoken = _spoken_target(parsed)
    subject = f"the {parsed.get('subject') or 'subject'}"
    if index == peak:
        motion = str(parsed.get("motion_third") or "")
        verb = str(parsed.get("change_verb") or "becomes")
        if motion:
            return verb, _join(subject, motion, "and", phrase, spoken, place)
        return verb, _join(subject, phrase, spoken, place)
    phase = "after" if index > peak else "before"
    base = str(parsed.get("motion_base") or "")
    third = str(parsed.get("motion_third") or base)
    key = f"change-{phase}"
    slot = counts.get(key, 0)
    counts[key] = slot + 1
    if base:
        pattern = _AFTER_MOTION if phase == "after" else _BEFORE_MOTION
        text = pattern[slot % len(pattern)].format(base=base, third=third, gerund=_gerund_of(base))
        return text.split()[0], _join(who, text, place)
    still = _AFTER_STILL if phase == "after" else _BEFORE_STILL
    verb = still[slot % len(still)]
    return verb, _join(who, verb, place)


def plan_storyboard(
    features: dict,
    register: dict | str,
    brief: str = "",
    *,
    customs: list[dict] | None = None,
    climax: int | None = None,
    motif: str = "",
    callback: str = "",
    previous: list[dict] | None = None,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """One scene per song section. ``seed`` rotates which calm form leads."""
    from xenoform.director import form_by_id, register_by_id

    if isinstance(register, str):
        register = register_by_id(register)
    sections = list(features.get("sections") or [])
    duration = float(features.get("duration") or 0.0)
    if not sections:
        sections = [{"label": "calm", "start": 0.0, "end": max(duration, 1.0), "level": 1.0}]
    catalog = _catalog(register, customs)
    parsed = parse_brief(brief)
    cast = brief_cast(brief)
    parsed["hero"] = cast["hero"]
    parsed["prop"] = cast["prop"]
    parsed["place"] = cast["place"]
    parsed["threat"] = cast["threat"]
    named = _form_index_by_name(parsed["text"].lower(), catalog)
    if parsed["subject"]:
        named = _form_index_by_name(parsed["subject"], catalog) or named
    peak = climax_index(sections, climax)
    beats = assign_beats(len(sections), peak)
    bar = bar_seconds(float(features.get("tempo") or 120.0))
    mood = (parsed["moods"][0] if parsed["moods"] else "") or _PALETTE_MOOD.get(str(register.get("palette")), "void")
    if mood not in MOODS:
        mood = "void"
    forms = _pick_forms(register, len(sections), peak, catalog, named, motif, callback)
    opening = form_by_id(forms[0], customs) or {"id": forms[0], "name": forms[0].replace("-", " ")}
    if parsed.get("becomes"):
        who = f"the {parsed.get('subject') or 'subject'}"
        goal, payoff = _change_spine(parsed)
    else:
        who, goal, payoff = _spine(parsed, _protagonist_name(parsed, opening))
    signature = _signature_edit(register)
    second_signature = len(sections) >= 8 and peak > 1
    if seed:
        calm_ids = [form for form in forms]
        # Rotate non-climax, non-callback forms so the dice can prefer another opening.
        rotatable = [i for i in range(len(forms)) if i != peak and not (callback.strip() and i == len(forms) - 1)]
        order = [str(form) for form in (register.get("forms") or ["sphere"])]
        for offset, index in enumerate(rotatable):
            forms[index] = order[(seed + offset) % len(order)]
        if named and 0 in rotatable:
            forms[0] = named
        _ = calm_ids
    if parsed.get("becomes"):
        subject_slug = _slug(str(parsed.get("subject") or "subject"))
        target_slug = _slug(str(parsed.get("becomes") or "subject"))
        forms = [target_slug if index >= peak else subject_slug for index in range(len(forms))]
    elif cast["hero"] and not _template_hero(cast["hero"]) and (cast["prop"] or cast["place"]):
        forms = [cast["hero"].replace(" ", "-")] * len(forms)
    scenes = []
    rising_index = 0
    verb_counts = {"setup": 0, "rising": 0, "climax": 0, "release": 0}
    spine = str(parsed.get("base") or "")
    for index, section in enumerate(sections):
        form_id = forms[index]
        form = form_by_id(form_id, customs) or {"id": form_id, "name": form_id.replace("-", " ")}
        seconds = max(0.2, float(section["end"]) - float(section["start"]))
        bars = snap_bars(seconds, bar)
        beat = beats[index]
        first = index == 0
        last = index == len(sections) - 1
        verb = _verb_for(beat, first=first, last=last, parsed=parsed, rising_index=rising_index)
        if beat == "rising":
            rising_index += 1
        if parsed.get("becomes"):
            who = _change_who(parsed, index, peak)
            verb, action = _change_line(parsed, index, peak, who, verb_counts)
            motion = str(parsed.get("motion_third") or "")
            becomes = str(parsed.get("becomes") or "") if index == peak else ""
            becomes_article = str(parsed.get("becomes_article") or "") if index == peak else ""
        else:
            motion = ""
            becomes = ""
            becomes_article = ""
            spoken = (
                not _template_hero(who)
                and spine
                and not (last and str(callback or "").strip())
                and not (first and parsed.get("origin"))
                and not (last and parsed.get("destination"))
            )
            if spoken:
                verb, action = _natural_line(who, beat, parsed, verb_counts, last=last)
            else:
                if not _template_hero(who) and spine:
                    verb = _counted_verb(
                        _SPINE,
                        beat,
                        verb_counts,
                        base=spine,
                        third=str(parsed.get("third") or spine),
                    )
                elif not _template_hero(who):
                    verb = _counted_verb(_VARIED, beat, verb_counts)
                action = _action_line(
                    who,
                    verb,
                    form,
                    parsed,
                    first=first,
                    last=last,
                    callback=callback,
                    prop=str(parsed.get("prop") or ""),
                    place=str(parsed.get("place") or ""),
                )
        shot = "wide" if first else "reveal" if last else "close" if beat == "climax" else _SHOT_FOR[beat]
        if parsed.get("becomes"):
            is_signature = index == peak
        else:
            is_signature = index == peak or (second_signature and index == peak - 1)
        edit = signature if index == peak else "ribbon" if is_signature else "hard cut"
        scene = {
            "index": index,
            "start": round(float(section["start"]), 4),
            "end": round(float(section["end"]), 4),
            "seconds": round(seconds, 4),
            "bars": bars,
            "bar_seconds": round(bar, 4),
            "hold": round(bars * bar, 4),
            "beat": beat,
            "form": form_id,
            "protagonist": who,
            "goal": goal,
            "payoff": payoff,
            "verb": verb,
            "action": action,
            "prop": str(parsed.get("prop") or ""),
            "place": str(parsed.get("place") or ""),
            "motion": motion,
            "becomes": becomes,
            "becomes_article": becomes_article,
            "change_verb": str(parsed.get("change_verb") or "") if parsed.get("becomes") else "",
            "shot": shot,
            "move": _MOVE_FOR_SHOT.get(shot, "follow"),
            "edit": edit,
            "signature": is_signature,
            "conditioning": "signature" if is_signature else "first-frame",
            "mood": mood,
            "motif": bool(motif) and form_id == motif and index != 0 and index != peak,
            "edited": False,
        }
        scene["guide"] = _guide(scene)
        scenes.append(scene)
    if previous:
        for index, prev in enumerate(previous):
            if index >= len(scenes) or not prev.get("edited"):
                continue
            kept = scenes[index]
            for key in ("action", "form", "shot", "move", "edit", "mood", "bars", "hold", "verb", "protagonist", "goal", "payoff", "signature", "conditioning"):
                if prev.get(key) not in (None, ""):
                    kept[key] = prev[key]
            kept["edited"] = True
            kept["guide"] = _guide(kept)
            if callback.strip() and index == len(scenes) - 1:
                kept["action"] = " ".join(callback.split())[:180]
                kept["guide"] = _guide(kept)
    return scenes


def roll_storyboards(
    features: dict,
    register: dict | str,
    brief: str,
    *,
    customs: list[dict] | None = None,
    climax: int | None = None,
    motif: str = "",
    callback: str = "",
    rolls: int = 6,
) -> dict[str, Any]:
    """Roll a handful of cheap plans, score them, keep the best. Loops cost 20."""
    from xenoform.director import register_by_id

    if isinstance(register, str):
        register = register_by_id(register)
    sections = list(features.get("sections") or [])
    best_scenes: list[dict] = []
    best_meta = {"score": -10**9, "loops": 0, "hook": False, "climax_on_peak": False}
    count = max(1, min(int(rolls), 8))
    for seed in range(count):
        scenes = plan_storyboard(
            features,
            register,
            brief,
            customs=customs,
            climax=climax,
            motif=motif,
            callback=callback,
            seed=seed,
        )
        meta = _score(scenes, sections, motif)
        meta["seed"] = seed
        if meta["score"] > best_meta["score"]:
            best_scenes = scenes
            best_meta = meta
    return {"scenes": best_scenes, "score": best_meta}


def _merge_scene_patches(scenes: list[dict], incoming: list) -> list[dict] | None:
    if len(incoming) != len(scenes):
        return None
    merged = []
    for scene, patch in zip(scenes, incoming):
        if not isinstance(patch, dict):
            return None
        row = dict(scene)
        for key, options in (
            ("action", None),
            ("verb", None),
            ("protagonist", None),
            ("goal", None),
            ("payoff", None),
            ("shot", SHOTS),
            ("move", MOVES),
            ("edit", EDITS),
            ("mood", MOODS),
        ):
            value = patch.get(key)
            if value in (None, ""):
                continue
            if options is not None and value not in options:
                continue
            if key in {"action", "verb", "protagonist", "goal", "payoff"}:
                row[key] = " ".join(str(value).split())[:180]
            else:
                row[key] = value
        if hero_has_verb(str(row.get("protagonist") or "")):
            return None
        row["guide"] = _guide(row)
        row["source"] = "llm"
        merged.append(row)
    return merged


def _keeps_cast(merged: list[dict], cast: dict[str, str]) -> bool:
    blob = " ".join(str(scene.get("action") or "") for scene in merged).lower()
    for noun in (cast.get("prop"), cast.get("place"), cast.get("threat"), cast.get("becomes")):
        for word in str(noun or "").split():
            if word and not re.search(rf"\b{re.escape(word)}\b", blob):
                return False
    verbs = [str(scene.get("verb") or "") for scene in merged]
    if len(verbs) > 1 and len(set(verbs)) < 2:
        return False
    return True


def _post_json(url: str, payload: dict, timeout: float) -> dict | None:
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _patches_from_body(text: str, count: int) -> list | None:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    incoming = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(incoming, list) or len(incoming) != count:
        return None
    return incoming


def _story_prompt(brief: str, scenes: list[dict], cast: dict[str, str]) -> tuple[str, str]:
    system = (
        "Rewrite each shot as one cinematic action. Keep the same hero, prop, place, and threat. "
        "The brief's verb is the spine: the opening begins it, the climax does it, the last shot resolves it. "
        "Every shot uses a different verb. Reply with JSON {\"scenes\": [{\"action\": \"\", \"verb\": \"\"}]}."
    )
    user = json.dumps(
        {
            "brief": brief,
            "hero": cast.get("hero") or "",
            "verb": cast.get("verb") or "",
            "prop": cast.get("prop") or "",
            "place": cast.get("place") or "",
            "threat": cast.get("threat") or "",
            "scenes": [{"beat": scene.get("beat"), "action": scene.get("action")} for scene in scenes],
        }
    )
    return system, user


def _ollama_story(brief: str, scenes: list[dict], cast: dict[str, str], allow_cloud: bool = False) -> list | None:
    from xenoform.llm import chat, reachable

    if not reachable(timeout=0.25):
        return None
    system, user = _story_prompt(brief, scenes, cast)
    raw = chat(system, user, {"type": "object"}, timeout=8.0, allow_cloud=allow_cloud)
    if not raw:
        return None
    return _patches_from_body(raw, len(scenes))


def _comfy_story(brief: str, scenes: list[dict], cast: dict[str, str], allow_cloud: bool = False) -> list | None:
    """A ComfyUI OpenAI-compatible chat route, when one is already listening."""
    from xenoform.comfy_health import DEFAULT_COMFY, ping
    from xenoform.eligibility import call_allowed

    base = os.environ.get("XENO_COMFY_URL", DEFAULT_COMFY).strip().rstrip("/") or DEFAULT_COMFY
    if not call_allowed(base, allow_cloud=allow_cloud):
        return None
    if not ping(base, timeout=0.25)["ok"]:
        return None
    system, user = _story_prompt(brief, scenes, cast)
    data = _post_json(
        base + "/v1/chat/completions",
        {
            "model": os.environ.get("XENO_LLM_MODEL", "local"),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.2,
        },
        8.0,
    )
    if not data:
        return None
    try:
        raw = str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        return None
    return _patches_from_body(raw, len(scenes))


def refine_with_llm(
    brief: str,
    scenes: list[dict],
    register_name: str,
    *,
    allow_cloud: bool = False,
) -> list[dict] | None:
    """Optional rewrite. The rule-based cards stand when no local model answers.

    Tries ``XENO_LLM_URL``, then Ollama, then a ComfyUI ``/v1/chat/completions`` route.
    A cloud host is skipped unless Add-ons is on. A rewrite that drops the prop,
    the place, or the threat, or that puts a verb in the hero, is discarded.
    """
    cast = brief_cast(brief)
    cast["verb"] = parse_brief(brief).get("verb") or ""
    url = os.environ.get("XENO_LLM_URL", "").strip()
    incoming = None
    if url:
        from xenoform.eligibility import call_allowed

        if call_allowed(url, allow_cloud=allow_cloud):
            payload = {
                "brief": brief,
                "register": register_name,
                "hero": cast.get("hero") or "",
                "prop": cast.get("prop") or "",
                "place": cast.get("place") or "",
                "threat": cast.get("threat") or "",
                "scenes": [
                    {key: scene.get(key) for key in ("beat", "action", "form", "shot", "move", "edit", "mood", "bars")}
                    for scene in scenes
                ],
            }
            data = _post_json(url, payload, 8)
            if data:
                incoming = data.get("scenes") if isinstance(data.get("scenes"), list) else None
    if not isinstance(incoming, list):
        incoming = _ollama_story(brief, scenes, cast, allow_cloud)
    if not isinstance(incoming, list):
        incoming = _comfy_story(brief, scenes, cast, allow_cloud)
    if not isinstance(incoming, list):
        return None
    merged = _merge_scene_patches(scenes, incoming)
    if not merged or not _keeps_cast(merged, cast):
        return None
    return merged


TREATMENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "life",
        "name": "The life",
        "moments": ("Birth", "The climb", "The return"),
        "idea": "One life, told in three moves.",
        "through": "Birth, the climb, and the return are the same body.",
        "lead": "The lead is one figure, the same silhouette in every shot.",
        "colour": "One accent from the register, on a black ground.",
    },
    {
        "id": "witness",
        "name": "The witness",
        "moments": ("The first look", "The hit", "The last hold"),
        "idea": "Someone watches the whole song.",
        "through": "The first look, the hit, and the last hold are one gaze.",
        "lead": "The lead is one figure, the same silhouette in every shot.",
        "colour": "Cool shadow, one warm hit on the drop.",
    },
    {
        "id": "cut",
        "name": "The cut",
        "moments": ("Wide open", "The signature", "The reveal"),
        "idea": "A cut that finds one subject.",
        "through": "Wide open, the signature, then the reveal.",
        "lead": "The lead is one figure, the same silhouette in every shot.",
        "colour": "Hard contrast, one colour, no second palette.",
    },
)


def treatment_by_id(treatment: str) -> dict[str, Any]:
    chosen = pick_treatment("", treatment)
    return next(item for item in TREATMENTS if item["id"] == chosen)


def pitch_treatments(brief: str = "") -> list[dict[str, Any]]:
    """Two or three treatments. Each one names three signature moments. The brief is not rewritten."""
    _ = brief
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "moments": list(item["moments"]),
            "idea": item["idea"],
            "through": item["through"],
            "lead": item["lead"],
            "colour": item["colour"],
        }
        for item in TREATMENTS
    ]


def pick_treatment(brief: str = "", treatment: str = "") -> str:
    """A life with an origin and a destination picks itself. Anything else opens on the cut."""
    chosen = str(treatment or "").strip()
    if any(item["id"] == chosen for item in TREATMENTS):
        return chosen
    parsed = parse_brief(brief)
    if parsed.get("origin") and parsed.get("destination"):
        return "life"
    return "cut"


def stamp_treatment(scenes: list[dict], treatment: str) -> list[dict]:
    """Name the first card, the climax, and the last card. Actions stay as the planner wrote them."""
    chosen = pick_treatment("", treatment)
    card = treatment_by_id(chosen)
    moments = card["moments"]
    if not scenes:
        return scenes
    for scene in scenes:
        scene.pop("moment", None)
        scene.pop("signature_moment", None)
    climax = next((scene for scene in scenes if scene.get("beat") == "climax"), scenes[len(scenes) // 2])
    lead = card["lead"]
    target = next((str(scene.get("becomes") or "") for scene in scenes if scene.get("becomes")), "")
    if target:
        subject = str(scenes[0].get("protagonist") or "the lead")
        article = str(next((scene.get("becomes_article") for scene in scenes if scene.get("becomes")), "") or "")
        spoken = f"{article} {target}".strip() if article else target
        lead = f"{subject} changes into {spoken} on the morph. Before the change, one silhouette. After it, the new one."
    named = []
    for scene, label in ((scenes[0], moments[0]), (climax, moments[1]), (scenes[-1], moments[2])):
        if scene in named:
            if scene.get("beat") == "climax":
                scene["moment"] = moments[1]
                scene["signature_moment"] = moments[1]
            continue
        scene["moment"] = label
        scene["signature_moment"] = label
        named.append(scene)
    for scene in scenes:
        scene["lead"] = lead
    return scenes


def _swatch(accent: str, seed: int, frame: int) -> str:
    from xenoform.seeded import unit

    text = str(accent or "").lstrip("#")
    if len(text) != 6:
        red, green, blue = 120, 90, 160
    else:
        red, green, blue = int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    shift = int(unit(seed, frame, salt=11) * 48) - 16

    def clamp(value: int) -> int:
        return max(0, min(255, value + shift))

    return f"#{clamp(red):02x}{clamp(green):02x}{clamp(blue):02x}"


def style_bible(
    register: dict | str,
    preset_id: str = "",
    *,
    moments: list[str] | None = None,
    seed: int = 2727,
) -> dict[str, Any]:
    """Palette, look, motion rules, textures, and three style frames. The frames are prompts, not a render."""
    from xenoform.director import register_by_id

    if isinstance(register, str):
        register = register_by_id(register)
    label = str(register.get("palette_label") or register.get("palette") or "neutral")
    look = "Liquid Metal" if str(preset_id) == "liquid-metal" else "Action Cut"
    textures = [f"{label} brushed metal", f"{label} matte shadow", f"{label} hard specular"]
    names = list(moments or ["Open", "Hit", "Land"])[:3]
    while len(names) < 3:
        names.append(("Open", "Hit", "Land")[len(names)])
    frames = []
    for index, name in enumerate(names):
        frames.append(
            {
                "name": name,
                "prompt": f"{name}. {look}. Palette {label}. Texture {textures[index]}. One subject, one move.",
                "swatch": _swatch(str(register.get("accent") or ""), seed, index),
            }
        )
    return {
        "palette": label,
        "look": look,
        "motion": [
            "Hard cut on the bar.",
            "One signature on the drop.",
            "The camera follows the verb.",
        ],
        "textures": textures,
        "frames": frames,
    }


def plan_with_hook(
    features: dict,
    register: dict | str,
    brief: str = "",
    **kwargs: Any,
) -> tuple[list[dict], str]:
    """Template plan, then the LLM hook if it is configured and answers."""
    from xenoform.director import register_by_id

    if isinstance(register, str):
        register = register_by_id(register)
    allow_cloud = bool(kwargs.pop("allow_cloud", False))
    rolls = int(kwargs.pop("rolls", 1) or 1)
    if rolls > 1:
        kwargs.pop("previous", None)
        kwargs.pop("seed", None)
        rolled = roll_storyboards(features, register, brief, rolls=rolls, **kwargs)
        scenes = rolled["scenes"]
    else:
        scenes = plan_storyboard(features, register, brief, **kwargs)
    refined = refine_with_llm(brief, scenes, str(register.get("name") or ""), allow_cloud=allow_cloud)
    if refined:
        return refined, "llm"
    return scenes, "template"


def scene_prompt(scene: dict, base: str, *, liquid: bool = False) -> str:
    """Action prompt. The first frame is the guide. Titles and lyrics stay out of the prompt."""
    from xenoform.continuity import render_guide
    from xenoform.craft import apply_lead

    guide = render_guide(scene) or str(scene.get("prompt") or scene.get("guide") or scene.get("action") or "").strip()
    if liquid:
        body = " ".join(str(base or "").split())
        shot = f"{guide} {body}".strip() if guide and body else guide or body
    else:
        who = str(scene.get("protagonist") or "").strip()
        if who and not _template_hero(who):
            subject = who[4:] if who.lower().startswith("the ") else who
        else:
            subject = str(scene.get("form") or "subject").replace("-", " ")
        shot = f"{guide} The subject in frame is the {subject}. The shot plays the action."
        if scene.get("signature"):
            shot += " This is the signature morph."
        else:
            shot += " It does not morph into the next card."
    return apply_lead(shot, str(scene.get("lead") or ""))
