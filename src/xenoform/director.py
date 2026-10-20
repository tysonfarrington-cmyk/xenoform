"""Song-to-shot script, look presets, and the shareable recipe code.

Each scene card is an action shot. The first frame is the guide, and the
default join is a hard cut on the bar. A morph is a signature, once or twice.
Liquid metal is one optional Look. The recipe is the whole desk packed into a
short code — sliders, locks, quality, preset, timeline, and custom nouns.
Uploaded image bytes stay on this machine; the code only remembers that a photo
was attached.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("xenoform")

TRANSITIONS: tuple[str, ...] = (
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
TRANSITION_FADE = {
    "pour-harden": 8,
    "droplet-burst": 2,
    "ribbon": 4,
    "snap": 0,
    "grow-out": 14,
    "droplet-gather": 10,
    "spike-burst": 1,
    "dive-splash": 6,
    "fly-through": 3,
    "bolt-strike": 0,
    "swim": 12,
}
TRANSITION_LABEL = {
    "pour-harden": "Pour / harden",
    "droplet-burst": "Droplet burst",
    "ribbon": "Ribbon",
    "snap": "Snap",
    "grow-out": "Grow out",
    "droplet-gather": "Droplet gather",
    "spike-burst": "Spike burst",
    "dive-splash": "Dive splash",
    "fly-through": "Fly through",
    "bolt-strike": "Bolt strike",
    "swim": "Swim hold",
}
ENERGIES: tuple[str, ...] = ("", "calm", "build", "drop", "release", "outro", "sustain")
PALETTES: tuple[str, ...] = ("violet", "grey-green", "gold", "bronze", "neutral")
FLASHES: tuple[str, ...] = ("minimal", "soft", "normal", "hard")
CUSTOM_BASE = 48
UNTITLED_FORM = 254

SLIDERS: tuple[str, ...] = (
    "kick",
    "bass",
    "hats",
    "vocals",
    "liquidity",
    "chaos",
    "material",
    "camera",
)

# Crockford-ish, without I/O/0/1, so a code can be read aloud.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_SECTION_FORMS = {
    "calm": ("sphere", "bulb"),
    "build": ("rocket",),
    "drop": ("tower", "scream"),
    "release": ("octopus",),
    "sustain": ("bulb",),
}
_SECTION_TRANSITION = {
    "calm": "pour-harden",
    "build": "ribbon",
    "drop": "droplet-burst",
    "release": "ribbon",
    "sustain": "snap",
}


def _svg(body: str, accent: str) -> str:
    return (
        f'<svg viewBox="0 0 80 64" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        f'<rect width="80" height="64" rx="4" fill="#1a1612"/>'
        f"{body}"
        f"</svg>"
    )


FORM_PACK: list[dict[str, Any]] = [
    {
        "id": "sphere",
        "name": "Liquid sphere",
        "pack": "Gravity's Rainbow",
        "blurb": "The body before it chooses a face. Chrome, held in tension.",
        "accent": "#d7dde6",
        "svg": _svg(
            '<circle cx="40" cy="34" r="16" fill="none" stroke="#d7dde6" stroke-width="1.6"/>'
            '<path d="M28 30c6-8 18-8 24 0" fill="none" stroke="#d7dde6" stroke-width="1.2"/>',
            "#d7dde6",
        ),
        "prompt": (
            "Macro cinematic shot of one liquid sphere of alien-biotech chrome and wet flesh, "
            "hovering in a black studio. Glossy membrane, slow continuous morph, soft specular "
            "highlights, faint internal filaments, no text, no logos, no people."
        ),
    },
    {
        "id": "rocket",
        "name": "V-2 on its arc",
        "pack": "Gravity's Rainbow",
        "blurb": "A rocket laid over the rainbow it rides. The arc is the move.",
        "accent": "#e23d1b",
        "svg": _svg(
            '<path d="M14 50c16-6 28-22 46-30" fill="none" stroke="#e23d1b" stroke-width="1.4"/>'
            '<path d="M48 16l10 6-8 2 2 8-6-8z" fill="#e23d1b"/>'
            '<path d="M18 48c8 2 14-4 16-10" fill="none" stroke="#c6a15a" stroke-width="1"/>',
            "#e23d1b",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid chrome organism stretched into a V-2 rocket "
            "climbing a colored arc across a black sky. Wet metal skin, a rainbow contrail "
            "made of the same liquid, continuous motion, no text, no logos, no people, no explosion gore."
        ),
    },
    {
        "id": "bulb",
        "name": "Byron the Bulb",
        "pack": "Gravity's Rainbow",
        "blurb": "A bulb that refuses to burn out. Filament as scripture.",
        "accent": "#ffb25a",
        "svg": _svg(
            '<circle cx="40" cy="26" r="14" fill="none" stroke="#ffb25a" stroke-width="1.5"/>'
            '<path d="M34 24h12M36 28h8M38 20h4" stroke="#ffb25a" stroke-width="1.2"/>'
            '<rect x="34" y="40" width="12" height="8" fill="none" stroke="#c6a15a" stroke-width="1.2"/>',
            "#ffb25a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid-chrome organism gathering into an immortal light bulb, "
            "Byron the Bulb, glass skin over a glowing filament of wet biotech wire. Black void, "
            "warm specular core, continuous morph, no text, no logos, no people."
        ),
    },
    {
        "id": "octopus",
        "name": "Grigori the octopus",
        "pack": "Gravity's Rainbow",
        "blurb": "Arms instead of a face. Ink is a material, not a stain.",
        "accent": "#7d9a6a",
        "svg": _svg(
            '<ellipse cx="40" cy="24" rx="12" ry="9" fill="none" stroke="#7d9a6a" stroke-width="1.5"/>'
            '<path d="M30 30c-6 10-2 18 2 20M36 32c-2 12 2 18 4 20M44 32c2 12-1 18-2 20M50 30c6 10 2 18-2 20" '
            'fill="none" stroke="#7d9a6a" stroke-width="1.3"/>',
            "#7d9a6a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid alien organism resolving into Grigori, an octopus of "
            "glossy chrome flesh and dark ink. Eight slow arms, wet specular suckers, black water, "
            "continuous motion, no text, no logos, no people."
        ),
    },
    {
        "id": "tower",
        "name": "The Tower",
        "pack": "Gravity's Rainbow",
        "blurb": "Tarot XVI. The structure fails in one held pose.",
        "accent": "#c6a15a",
        "svg": _svg(
            '<rect x="30" y="16" width="20" height="32" fill="none" stroke="#c6a15a" stroke-width="1.5"/>'
            '<path d="M34 22l12 20M46 22L34 42" stroke="#e23d1b" stroke-width="1.2"/>'
            '<path d="M26 14l8-6 8 6" fill="none" stroke="#c6a15a" stroke-width="1.2"/>',
            "#c6a15a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid-chrome biotech body locking into The Tower tarot card, "
            "a tall struck structure splitting along a lightning seam. Black studio, brass and rust "
            "speculars, continuous morph, no readable text, no logos, no people."
        ),
    },
    {
        "id": "scream",
        "name": "Schwarzgerät scream",
        "pack": "Gravity's Rainbow",
        "blurb": "The device, at the moment it becomes a mouth.",
        "accent": "#f3eadc",
        "svg": _svg(
            '<ellipse cx="40" cy="32" rx="16" ry="18" fill="none" stroke="#f3eadc" stroke-width="1.5"/>'
            '<ellipse cx="40" cy="36" rx="6" ry="9" fill="#f3eadc"/>'
            '<circle cx="33" cy="26" r="1.4" fill="#f3eadc"/>'
            '<circle cx="47" cy="26" r="1.4" fill="#f3eadc"/>',
            "#f3eadc",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid chrome-flesh organism torn into the scream of the "
            "Schwarzgerät, a white-hot open mouth of metal and membrane. Black void, harsh speculars, "
            "continuous motion, no text, no logos, no people."
        ),
    },
    {
        "id": "dead-drop",
        "name": "Dead drop",
        "pack": "le Carré",
        "blurb": "A place the hand already knows. Nothing is exchanged on screen.",
        "accent": "#8aa394",
        "svg": _svg(
            '<rect x="22" y="28" width="36" height="16" fill="none" stroke="#8aa394" stroke-width="1.4"/>'
            '<path d="M22 28l8-8h28" fill="none" stroke="#8aa394" stroke-width="1.3"/>'
            '<circle cx="48" cy="36" r="2" fill="#8aa394"/>',
            "#8aa394",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid metal organism settling into a dead-drop cache, "
            "a plain box in wet grey-green shadow. No people, no readable text, no logos, continuous motion."
        ),
    },
    {
        "id": "streetlamp",
        "name": "Streetlamp",
        "pack": "le Carré",
        "blurb": "One lamp. The rest of the street is withheld.",
        "accent": "#8aa394",
        "svg": _svg(
            '<path d="M40 50V22" stroke="#8aa394" stroke-width="1.4"/>'
            '<path d="M28 22h24l-4 8H32z" fill="none" stroke="#c5d2c6" stroke-width="1.3"/>'
            '<circle cx="40" cy="18" r="2" fill="#c5d2c6"/>',
            "#8aa394",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid-metal body drawn up into a single streetlamp, "
            "grey-green night, one pool of light, wet stone, no people, no text, no logos."
        ),
    },
    {
        "id": "typewriter",
        "name": "Typewriter",
        "pack": "le Carré",
        "blurb": "The report is the weapon. The keys are shut.",
        "accent": "#8aa394",
        "svg": _svg(
            '<rect x="18" y="30" width="44" height="16" fill="none" stroke="#8aa394" stroke-width="1.4"/>'
            '<path d="M24 30c4-8 28-8 32 0" fill="none" stroke="#8aa394" stroke-width="1.2"/>'
            '<circle cx="30" cy="38" r="1.3" fill="#8aa394"/>'
            '<circle cx="40" cy="38" r="1.3" fill="#8aa394"/>'
            '<circle cx="50" cy="38" r="1.3" fill="#8aa394"/>',
            "#8aa394",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid chrome organism hardened into a closed typewriter, "
            "grey-green office dark, round keys, no readable letters, no people, no logos."
        ),
    },
    {
        "id": "briefcase",
        "name": "Briefcase",
        "pack": "le Carré",
        "blurb": "Handle up. The latch is the whole plot.",
        "accent": "#8aa394",
        "svg": _svg(
            '<rect x="18" y="26" width="44" height="24" fill="none" stroke="#8aa394" stroke-width="1.4"/>'
            '<path d="M32 26v-6h16v6" fill="none" stroke="#8aa394" stroke-width="1.3"/>'
            '<rect x="36" y="34" width="8" height="5" fill="none" stroke="#c5d2c6" stroke-width="1.2"/>',
            "#8aa394",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid-metal organism squared into a worn briefcase, "
            "grey-green, one latch, black studio, no people, no text, no logos."
        ),
    },
    {
        "id": "ring",
        "name": "Ring",
        "pack": "Tolkien",
        "blurb": "A circle that refuses to cool. Not a relic from a page.",
        "accent": "#e0a84a",
        "svg": _svg(
            '<circle cx="40" cy="32" r="14" fill="none" stroke="#e0a84a" stroke-width="3"/>'
            '<circle cx="40" cy="32" r="7" fill="none" stroke="#a86820" stroke-width="1"/>',
            "#e0a84a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid gold organism gathering into a plain ring, "
            "molten metal, dark forge-black background, no inscription, no people, no logos."
        ),
    },
    {
        "id": "forge",
        "name": "Forge",
        "pack": "Tolkien",
        "blurb": "Heat before the shape. The tool is still deciding.",
        "accent": "#e0a84a",
        "svg": _svg(
            '<path d="M24 44h32l-6-16H30z" fill="none" stroke="#e0a84a" stroke-width="1.4"/>'
            '<path d="M34 28c2-8 10-8 12 0" fill="none" stroke="#ffb25a" stroke-width="1.3"/>'
            '<path d="M30 44v6h20v-6" stroke="#a86820" stroke-width="1.2"/>',
            "#e0a84a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid gold body opening into a forge mouth, "
            "molten light, slow grow, black workshop, no people, no text, no logos."
        ),
    },
    {
        "id": "tree",
        "name": "Tree",
        "pack": "Tolkien",
        "blurb": "One trunk. The branches are still liquid.",
        "accent": "#e0a84a",
        "svg": _svg(
            '<path d="M40 50V30" stroke="#c6a15a" stroke-width="1.6"/>'
            '<circle cx="40" cy="24" r="10" fill="none" stroke="#e0a84a" stroke-width="1.4"/>'
            '<path d="M30 24c4 6 16 6 20 0" fill="none" stroke="#e0a84a" stroke-width="1"/>',
            "#e0a84a",
        ),
        "prompt": (
            "Macro cinematic shot of a molten-gold organism rising into a single tree, "
            "wet bark of metal, black night, slow continuous growth, no people, no text, no logos."
        ),
    },
    {
        "id": "mountain",
        "name": "Mountain",
        "pack": "Tolkien",
        "blurb": "The hold, made geological. It takes the whole bar.",
        "accent": "#e0a84a",
        "svg": _svg(
            '<path d="M12 48L32 16l10 14 8-10 18 28z" fill="none" stroke="#e0a84a" stroke-width="1.4"/>'
            '<path d="M32 16l6 10" stroke="#fff4d2" stroke-width="1.2"/>',
            "#e0a84a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid gold body locking into a mountain ridge, "
            "molten edges, black sky, slow grow, no people, no text, no logos."
        ),
    },
    {
        "id": "coin",
        "name": "Coin",
        "pack": "Rome",
        "blurb": "A face worn down to a value.",
        "accent": "#c6a36a",
        "svg": _svg(
            '<circle cx="40" cy="32" r="16" fill="none" stroke="#c6a36a" stroke-width="1.6"/>'
            '<circle cx="40" cy="32" r="11" fill="none" stroke="#efe6d6" stroke-width="1"/>'
            '<path d="M34 30h12M36 35h8" stroke="#c6a36a" stroke-width="1.2"/>',
            "#c6a36a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid bronze organism struck into a worn coin, "
            "marble light, no readable legend, no people, no logos, hard specular edge."
        ),
    },
    {
        "id": "bust",
        "name": "Bust",
        "pack": "Rome",
        "blurb": "Marble, cropped at the chest. The eyes are shut.",
        "accent": "#c6a36a",
        "svg": _svg(
            '<circle cx="40" cy="24" r="9" fill="none" stroke="#efe6d6" stroke-width="1.4"/>'
            '<path d="M26 48c2-12 26-12 28 0" fill="none" stroke="#c6a36a" stroke-width="1.4"/>'
            '<path d="M34 24h4M44 24h4" stroke="#efe6d6" stroke-width="1"/>',
            "#c6a36a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid marble-and-bronze organism resolving into a cropped bust, "
            "closed eyes, studio black, no pedestal text, no people around it, no logos."
        ),
    },
    {
        "id": "legion",
        "name": "Legion standard",
        "pack": "Rome",
        "blurb": "The pole is the cut. Cloth is metal here.",
        "accent": "#c6a36a",
        "svg": _svg(
            '<path d="M34 50V14" stroke="#c6a36a" stroke-width="1.5"/>'
            '<path d="M34 16h22l-4 8 4 8H34" fill="none" stroke="#efe6d6" stroke-width="1.3"/>'
            '<circle cx="34" cy="12" r="2" fill="#c6a36a"/>',
            "#c6a36a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid bronze body pulled into a legion standard, "
            "marble highlight, a metal flag with no emblem text, black field, no people, no logos."
        ),
    },
    {
        "id": "lion",
        "name": "Lion",
        "pack": "Rome",
        "blurb": "Bronze animal. It does not perform.",
        "accent": "#c6a36a",
        "svg": _svg(
            '<ellipse cx="38" cy="34" rx="14" ry="10" fill="none" stroke="#c6a36a" stroke-width="1.4"/>'
            '<circle cx="50" cy="30" r="6" fill="none" stroke="#efe6d6" stroke-width="1.3"/>'
            '<path d="M24 30c-6 2-8 8-4 12" fill="none" stroke="#c6a36a" stroke-width="1.2"/>',
            "#c6a36a",
        ),
        "prompt": (
            "Macro cinematic shot of a liquid bronze organism hardening into a lion at rest, "
            "marble studio light, no collar text, no people, no logos, a hard snapped pose."
        ),
    },
]


def _look(
    id_: str,
    name: str,
    note: str,
    quality: str,
    kick: float,
    bass: float,
    hats: float,
    vocals: float,
    liquidity: float,
    chaos: float,
    material: float,
    camera: float,
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "note": note,
        "quality": quality,
        "sliders": {
            "kick": kick,
            "bass": bass,
            "hats": hats,
            "vocals": vocals,
            "liquidity": liquidity,
            "chaos": chaos,
            "material": material,
            "camera": camera,
        },
    }


PRESETS: list[dict[str, Any]] = [
    _look("slow-chrome", "Slow Chrome", "A held sphere. The kick barely arrives.", "final", 0.28, 0.40, 0.22, 0.48, 0.72, 0.18, 0.84, 0.30),
    _look("rocket-noon", "Rocket Noon", "Camera on the arc. Bass does the pushing.", "final", 0.55, 0.86, 0.34, 0.40, 0.48, 0.42, 0.70, 0.88),
    _look("bulb-gospel", "Bulb Gospel", "Vocals in the filament. Almost no panic.", "final", 0.22, 0.36, 0.30, 0.90, 0.40, 0.16, 0.78, 0.34),
    _look("octopus-ink", "Octopus Ink", "Loose, dark, too many directions.", "draft", 0.48, 0.52, 0.26, 0.44, 0.92, 0.74, 0.28, 0.46),
    _look("tower-fall", "Tower Fall", "The hit is the cut. Liquidity pulled back.", "final", 0.90, 0.70, 0.48, 0.30, 0.22, 0.86, 0.62, 0.58),
    _look("scream-white", "Scream White", "Hats and kick, material pushed to glare.", "final", 0.84, 0.46, 0.92, 0.70, 0.36, 0.64, 0.96, 0.40),
    _look("arc-weld", "Arc Weld", "A bright, nervous camera. Ribbon energy.", "draft", 0.60, 0.74, 0.80, 0.36, 0.58, 0.50, 0.66, 0.82),
    _look("night-assembly", "Night Assembly", "Everything turned down until the song leads.", "final", 0.40, 0.42, 0.28, 0.38, 0.50, 0.24, 0.55, 0.32),
    _look("action-cut", "Action Cut", "Hard cuts on the bar. The first frame is the guide.", "live", 0.62, 0.55, 0.40, 0.42, 0.18, 0.36, 0.58, 0.52),
    _look("liquid-metal", "Liquid Metal", "Optional look. One liquid body, used when you ask for it.", "final", 0.48, 0.50, 0.30, 0.44, 0.86, 0.40, 0.70, 0.38),
]


def _reg(
    id_: str,
    name: str,
    voice: str,
    palette: str,
    palette_label: str,
    accent: str,
    flash: str,
    pacing: str,
    forms: list[str],
    drop_forms: list[str],
    transitions: dict[str, str],
    cards: list[dict[str, str]],
    sliders: dict[str, float],
    pack: str,
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "voice": voice,
        "palette": palette,
        "palette_label": palette_label,
        "accent": accent,
        "flash": flash,
        "pacing": pacing,
        "forms": forms,
        "drop_forms": drop_forms,
        "transitions": transitions,
        "cards": cards,
        "sliders": sliders,
        "pack": pack,
    }


# Original lines, written for this desk. Not quotations.
REGISTERS: list[dict[str, Any]] = [
    _reg(
        "pynchon",
        "Pynchon",
        "Cold violet. The drop bursts.",
        "violet",
        "Cold violet",
        "#9b8cff",
        "normal",
        "cut",
        ["rocket", "bulb", "octopus", "tower", "scream"],
        ["tower", "scream"],
        {"calm": "ribbon", "build": "pour-harden", "drop": "droplet-burst", "release": "ribbon", "outro": "pour-harden", "sustain": "ribbon"},
        [
            {"at": "drop", "text": "The arc completes itself. Nobody signed the order."},
            {"at": "outro", "text": "Somewhere a bulb is still arguing with the dark."},
        ],
        {"kick": 0.72, "bass": 0.58, "hats": 0.44, "vocals": 0.36, "liquidity": 0.62, "chaos": 0.70, "material": 0.48, "camera": 0.56},
        "Gravity's Rainbow",
    ),
    _reg(
        "lecarre",
        "le Carré",
        "Grey-green. Slow harden, almost no flash.",
        "grey-green",
        "Grey-green",
        "#8aa394",
        "minimal",
        "slow",
        ["dead-drop", "streetlamp", "typewriter", "briefcase"],
        ["briefcase"],
        {"calm": "pour-harden", "build": "pour-harden", "drop": "pour-harden", "release": "pour-harden", "outro": "pour-harden", "sustain": "pour-harden"},
        [
            {"at": "drop", "text": "Leave it under the third lamp. Do not wait."},
            {"at": "outro", "text": "He burned the carbons and kept the habit."},
        ],
        {"kick": 0.22, "bass": 0.30, "hats": 0.18, "vocals": 0.26, "liquidity": 0.34, "chaos": 0.14, "material": 0.40, "camera": 0.26},
        "le Carré",
    ),
    _reg(
        "tolkien",
        "Tolkien",
        "Molten gold. The form grows out.",
        "gold",
        "Molten gold",
        "#e0a84a",
        "soft",
        "grow",
        ["ring", "forge", "tree", "mountain"],
        ["mountain"],
        {"calm": "grow-out", "build": "grow-out", "drop": "grow-out", "release": "grow-out", "outro": "grow-out", "sustain": "grow-out"},
        [
            {"at": "drop", "text": "The metal remembered the hand that woke it."},
            {"at": "outro", "text": "Ash cooled. The road did not."},
        ],
        {"kick": 0.30, "bass": 0.48, "hats": 0.20, "vocals": 0.55, "liquidity": 0.58, "chaos": 0.24, "material": 0.80, "camera": 0.36},
        "Tolkien",
    ),
    _reg(
        "rome",
        "Rome",
        "Marble and bronze. Drops snap.",
        "bronze",
        "Marble / bronze",
        "#c6a36a",
        "hard",
        "cut",
        ["coin", "bust", "legion", "lion"],
        ["lion"],
        {"calm": "ribbon", "build": "pour-harden", "drop": "snap", "release": "ribbon", "outro": "ribbon", "sustain": "ribbon"},
        [
            {"at": "drop", "text": "The standard does not ask."},
            {"at": "outro", "text": "What the coin bought, the city kept."},
        ],
        {"kick": 0.84, "bass": 0.66, "hats": 0.32, "vocals": 0.28, "liquidity": 0.26, "chaos": 0.46, "material": 0.86, "camera": 0.64},
        "Rome",
    ),
    _reg(
        "custom",
        "Custom",
        "Your words. Your pictures.",
        "neutral",
        "Unset",
        "#d9cbb8",
        "normal",
        "cut",
        [],
        [],
        {"calm": "ribbon", "build": "pour-harden", "drop": "ribbon", "release": "ribbon", "outro": "pour-harden", "sustain": "ribbon"},
        [
            {"at": "drop", "text": ""},
            {"at": "outro", "text": ""},
        ],
        {"kick": 0.50, "bass": 0.50, "hats": 0.40, "vocals": 0.45, "liquidity": 0.50, "chaos": 0.35, "material": 0.55, "camera": 0.40},
        "Yours",
    ),
]


def register_by_id(register_id: str) -> dict[str, Any]:
    for register in REGISTERS:
        if register["id"] == register_id:
            return register
    return REGISTERS[0]


def _drive(amount: float) -> float:
    """0.5 leaves a band alone. 0 ducks it, 1 leans on it."""
    return 0.15 + 1.7 * float(amount)


def _clip(value: float, lo: float = 0.0, hi: float = 1.5) -> float:
    return float(max(lo, min(hi, value)))


def form_by_id(form_id: str, customs: list[dict] | None = None) -> dict[str, Any] | None:
    for form in FORM_PACK:
        if form["id"] == form_id:
            return form
    for form in customs or []:
        if form.get("id") == form_id:
            return form
    return None


def custom_prompt(noun: str) -> str:
    subject = " ".join(noun.split()) or "an unnamed object"
    return (
        f"Macro cinematic shot of a liquid chrome-flesh alien organism resolving into {subject}. "
        "Black studio, wet specular metal, continuous morph, no text, no logos, no people."
    )


def public_forms(customs: list[dict] | None = None) -> list[dict[str, Any]]:
    rows = []
    for form in FORM_PACK:
        rows.append(
            {
                "id": form["id"],
                "name": form["name"],
                "pack": form["pack"],
                "blurb": form["blurb"],
                "accent": form["accent"],
                "svg": form["svg"],
                "kind": "preset",
            }
        )
    for form in customs or []:
        rows.append(
            {
                "id": form["id"],
                "name": form.get("name") or form.get("noun") or "Custom",
                "pack": "Yours",
                "blurb": form.get("blurb") or "Added on this desk.",
                "accent": form.get("accent") or "#e7d7c3",
                "svg": form.get("svg") or "",
                "kind": form.get("kind") or "noun",
                "image": form.get("image") or "",
                "noun": form.get("noun") or "",
            }
        )
    return rows


def public_presets() -> list[dict[str, Any]]:
    from xenoform.lessons import look_allowed

    return [
        {
            "id": preset["id"],
            "name": preset["name"],
            "note": preset["note"],
            "quality": preset["quality"],
            "sliders": dict(preset["sliders"]),
        }
        for preset in PRESETS
        if look_allowed(preset)
    ]


def public_transitions() -> list[dict[str, str]]:
    return [{"id": key, "label": TRANSITION_LABEL[key]} for key in TRANSITIONS]


def default_locks() -> dict[str, bool]:
    locks = {key: False for key in SLIDERS}
    locks["quality"] = False
    locks["preset"] = False
    locks["script"] = False
    locks["register"] = False
    return locks


def default_sliders() -> dict[str, float]:
    return dict(PRESETS[0]["sliders"])


def preset_by_id(preset_id: str) -> dict[str, Any]:
    for preset in PRESETS:
        if preset["id"] == preset_id:
            return preset
    return PRESETS[0]


def empty_state() -> dict[str, Any]:
    look = preset_by_id("action-cut")
    return {
        "preset": look["id"],
        "quality": look["quality"],
        "sliders": dict(look["sliders"]),
        "locks": default_locks(),
        "register": "pynchon",
        "palette": "violet",
        "flash": "normal",
        "cards": [dict(card) for card in REGISTERS[0]["cards"]],
        "blocks": [
            {"form": "sphere", "hold": 4.0, "transition": "pour-harden", "energy": "calm"},
            {"form": "rocket", "hold": 4.0, "transition": "ribbon", "energy": "build"},
            {"form": "scream", "hold": 4.0, "transition": "droplet-burst", "energy": "drop"},
        ],
        "customs": [],
        "brief": "",
        "mode": "simple",
        "scenes": [],
        "motif": "",
        "callback": "",
        "climax": None,
        "live": False,
        "endpoint": "",
    }


def script_from_sections(features: dict) -> list[dict[str, Any]]:
    """One block per analyzed section, with a form and the way in."""
    counts = {label: 0 for label in _SECTION_FORMS}
    blocks = []
    for section in features.get("sections") or []:
        label = str(section.get("label") or "sustain")
        choices = _SECTION_FORMS.get(label, ("sphere",))
        form = choices[counts.get(label, 0) % len(choices)]
        counts[label] = counts.get(label, 0) + 1
        hold = max(0.2, float(section["end"]) - float(section["start"]))
        blocks.append(
            {
                "form": form,
                "hold": round(hold, 2),
                "transition": _SECTION_TRANSITION.get(label, "ribbon"),
            }
        )
    return blocks or empty_state()["blocks"]


def _span(sections: list[dict], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "start": float(sections[0]["start"]),
        "end": float(sections[-1]["end"]),
    }


def _groups_for_pacing(sections: list[dict], pacing: str) -> list[dict[str, Any]]:
    if not sections:
        return []
    if pacing == "grow":
        drops = [section for section in sections if section.get("label") == "drop"]
        if not drops:
            size = max(1, int(round(len(sections) / 4)))
            groups = []
            for index in range(0, len(sections), size):
                chunk = sections[index : index + size]
                groups.append(_span(chunk, str(chunk[0].get("label") or "calm")))
            return groups[:4] or groups
        first = drops[0]["start"]
        last = drops[-1]["end"]
        before = [section for section in sections if float(section["end"]) <= float(first) + 1e-6]
        after = [section for section in sections if float(section["start"]) >= float(last) - 1e-6]
        groups = []
        if before:
            groups.append(_span(before, str(before[0].get("label") or "calm")))
        groups.append(_span(drops, "drop"))
        if len(after) >= 2:
            groups.append(_span(after[:-1], str(after[0].get("label") or "release")))
            groups.append(_span(after[-1:], "outro"))
        elif after:
            groups.append(_span(after, "outro"))
        return groups
    if pacing == "slow":
        groups = []
        for section in sections:
            label = str(section.get("label") or "calm")
            dur = float(section["end"]) - float(section["start"])
            if not groups:
                groups.append(_span([section], label))
                continue
            previous = groups[-1]["label"]
            same_class = (label == "drop") == (previous == "drop")
            if dur < 2.2 and same_class:
                groups[-1]["end"] = float(section["end"])
            else:
                groups.append(_span([section], label))
        return groups
    return [
        {"label": str(section.get("label") or "calm"), "start": float(section["start"]), "end": float(section["end"])}
        for section in sections
    ]


def _fill_groups(groups: list[dict], count: int) -> list[dict]:
    """Split the longest holds until every form in the pack has a place."""
    groups = [dict(group) for group in groups]
    while count > 0 and len(groups) < count:
        index = max(range(len(groups)), key=lambda i: float(groups[i]["end"]) - float(groups[i]["start"]))
        group = groups[index]
        start = float(group["start"])
        end = float(group["end"])
        if end - start < 0.8:
            break
        mid = (start + end) / 2
        groups[index : index + 1] = [
            {**group, "end": mid},
            {**group, "start": mid},
        ]
    return groups


def script_for_register(features: dict, register: dict | str, customs: list[dict] | None = None) -> list[dict[str, Any]]:
    """Lay the register's forms across the song in the order they tend to appear."""
    if isinstance(register, str):
        register = register_by_id(register)
    sections = list(features.get("sections") or [])
    duration = float(features.get("duration") or 0.0)
    if duration <= 0 and sections:
        duration = float(sections[-1]["end"])
    groups = _groups_for_pacing(sections, str(register.get("pacing") or "cut"))
    if not groups:
        groups = [{"label": "calm", "start": 0.0, "end": max(duration, 1.0)}]
    if str(register.get("pacing") or "cut") in {"slow", "grow"} and register.get("id") != "custom":
        groups = _fill_groups(groups, len(register.get("forms") or []))
    if register.get("id") == "custom":
        order = [str(custom.get("id")) for custom in (customs or []) if custom.get("id")]
        if not order:
            return [
                {
                    "form": "",
                    "hold": round(max(duration, 0.2), 2),
                    "transition": "ribbon",
                    "energy": "calm",
                }
            ]
        blocks = []
        transitions = register.get("transitions") or {}
        for index, group in enumerate(groups):
            energy = "drop" if group["label"] == "drop" else ("outro" if index == len(groups) - 1 else group["label"])
            key = energy if energy in transitions else str(group["label"])
            blocks.append(
                {
                    "form": order[index % len(order)],
                    "hold": round(max(0.2, float(group["end"]) - float(group["start"])), 2),
                    "transition": transitions.get(key) or "ribbon",
                    "energy": energy if energy in ENERGIES else "calm",
                }
            )
        return blocks
    else:
        order = list(register.get("forms") or ["sphere"])
        drop_forms = list(register.get("drop_forms") or order[-1:])
    transitions = register.get("transitions") or {}
    pacing = str(register.get("pacing") or "cut")
    blocks = []
    if pacing in {"slow", "grow"}:
        for index, group in enumerate(groups):
            form = order[index % len(order)]
            energy = "drop" if group["label"] == "drop" else ("outro" if index == len(groups) - 1 else group["label"])
            key = energy if energy in transitions else group["label"]
            transition = transitions.get(key) or transitions.get("calm") or "ribbon"
            blocks.append(
                {
                    "form": form,
                    "hold": round(max(0.2, float(group["end"]) - float(group["start"])), 2),
                    "transition": transition,
                    "energy": energy if energy in ENERGIES else "calm",
                }
            )
        return blocks
    calm_forms = [form for form in order if form not in drop_forms] or list(order)
    calm_i = 0
    drop_i = 0
    for index, group in enumerate(groups):
        last = index == len(groups) - 1
        if group["label"] == "drop":
            form = drop_forms[drop_i % len(drop_forms)]
            drop_i += 1
            energy = "drop"
            transition = transitions.get("drop") or "snap"
        else:
            form = calm_forms[calm_i % len(calm_forms)]
            calm_i += 1
            energy = "outro" if last else str(group["label"])
            key = "outro" if energy == "outro" else str(group["label"])
            transition = transitions.get(key) or transitions.get("calm") or "ribbon"
        if transition not in TRANSITION_FADE:
            transition = "ribbon"
        blocks.append(
            {
                "form": form,
                "hold": round(max(0.2, float(group["end"]) - float(group["start"])), 2),
                "transition": transition,
                "energy": energy if energy in ENERGIES else "calm",
            }
        )
    return blocks


def all_scripts(features: dict, customs: list[dict] | None = None) -> dict[str, list[dict[str, Any]]]:
    return {register["id"]: script_for_register(features, register, customs) for register in REGISTERS}


def layout_blocks(blocks: list[dict], duration: float) -> list[dict[str, Any]]:
    """Fit authored holds onto the song. Widths are shares, not a second clock."""
    duration = max(float(duration), 0.001)
    cleaned = []
    for block in blocks:
        form = str(block.get("form") or "sphere")
        hold = float(block.get("hold") or 1.0)
        transition = str(block.get("transition") or "ribbon")
        if transition not in TRANSITION_FADE:
            transition = "ribbon"
        cleaned.append(
            {
                "form": form,
                "hold": max(0.2, min(25.5, hold)),
                "transition": transition,
                "energy": str(block.get("energy") or ""),
            }
        )
    total = sum(block["hold"] for block in cleaned) or 1.0
    cursor = 0.0
    laid = []
    for block in cleaned:
        span = duration * block["hold"] / total
        laid.append({**block, "start": cursor, "end": cursor + span})
        cursor += span
    if laid:
        laid[-1]["end"] = duration
    return laid


def _form_index(form_id: str, customs: list[dict]) -> int:
    if not form_id:
        return UNTITLED_FORM
    ids = [form["id"] for form in FORM_PACK]
    if form_id in ids:
        return ids.index(form_id)
    for index, custom in enumerate(customs):
        if custom.get("id") == form_id:
            return CUSTOM_BASE + index
    return 0


def _encode_base32(data: bytes) -> str:
    bits = 0
    nbits = 0
    out: list[str] = []
    for byte in data:
        bits = (bits << 8) | byte
        nbits += 8
        while nbits >= 5:
            nbits -= 5
            out.append(_ALPHABET[(bits >> nbits) & 31])
    if nbits:
        out.append(_ALPHABET[(bits << (5 - nbits)) & 31])
    return "".join(out)


def _decode_base32(text: str) -> bytes:
    bits = 0
    nbits = 0
    out = bytearray()
    for char in text:
        index = _ALPHABET.find(char)
        if index < 0:
            raise ValueError(f"Recipe has a character this desk does not use: {char}")
        bits = (bits << 5) | index
        nbits += 5
        if nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 255)
    return bytes(out)


def _u8(value: float) -> int:
    return max(0, min(255, int(round(float(value) * 255))))


def _lock_bits(locks: dict) -> int:
    bits = 0
    for index, key in enumerate(SLIDERS):
        if locks.get(key):
            bits |= 1 << index
    if locks.get("quality"):
        bits |= 1 << 8
    if locks.get("preset"):
        bits |= 1 << 9
    if locks.get("script"):
        bits |= 1 << 10
    if locks.get("register"):
        bits |= 1 << 11
    return bits


def _locks_from_bits(bits: int) -> dict[str, bool]:
    locks = default_locks()
    for index, key in enumerate(SLIDERS):
        locks[key] = bool(bits & (1 << index))
    locks["quality"] = bool(bits & (1 << 8))
    locks["preset"] = bool(bits & (1 << 9))
    locks["script"] = bool(bits & (1 << 10))
    locks["register"] = bool(bits & (1 << 11))
    return locks


def encode_recipe(state: dict) -> str:
    """Pack the desk into XF- groups of four. Image bytes are not included."""
    preset_ids = [preset["id"] for preset in PRESETS]
    preset = state.get("preset") or ""
    if preset not in preset_ids:
        preset = ""
    quality = {"draft": 0, "final": 1, "turbo": 2, "live": 3}.get(str(state.get("quality") or "draft"), 0)
    sliders = state.get("sliders") or default_sliders()
    locks = state.get("locks") or default_locks()
    customs = list(state.get("customs") or [])[:8]
    blocks = list(state.get("blocks") or [])[:24]
    if not blocks:
        blocks = empty_state()["blocks"]

    register_ids = [register["id"] for register in REGISTERS]
    register = state.get("register") or ""
    if register not in register_ids:
        register = ""
    palette = state.get("palette") or "neutral"
    if palette not in PALETTES:
        palette = "neutral"
    flash = state.get("flash") or "normal"
    if flash not in FLASHES:
        flash = "normal"
    cards = [card for card in (state.get("cards") or []) if card.get("at") in {"drop", "outro"}][:4]

    buf = bytearray()
    buf.append(4)
    buf.append(quality)
    buf.append(preset_ids.index(preset) if preset else 255)
    for key in SLIDERS:
        buf.append(_u8(sliders.get(key, 0.5)))
    bits = _lock_bits(locks)
    buf.append(bits & 255)
    buf.append((bits >> 8) & 255)
    buf.append(len(blocks))
    for block in blocks:
        buf.append(_form_index(str(block.get("form") or "sphere"), customs))
        hold = max(0.2, min(25.5, float(block.get("hold") or 1.0)))
        buf.append(int(round(hold * 10)))
        transition = str(block.get("transition") or "ribbon")
        transition_index = TRANSITIONS.index(transition) if transition in TRANSITIONS else 2
        energy = str(block.get("energy") or "")
        energy_index = ENERGIES.index(energy) if energy in ENERGIES else 0
        buf.append(transition_index | (energy_index << 4))
    buf.append(len(customs))
    for custom in customs:
        noun = str(custom.get("noun") or custom.get("name") or "form")[:40].encode("utf-8")
        buf.append(len(noun))
        buf.extend(noun)
        buf.append(1 if custom.get("kind") == "image" else 0)
    buf.append(register_ids.index(register) if register else 255)
    buf.append(PALETTES.index(palette))
    buf.append(FLASHES.index(flash))
    buf.append(len(cards))
    for card in cards:
        text = str(card.get("text") or "")[:80].encode("utf-8")
        buf.append(0 if card.get("at") == "drop" else 1)
        buf.append(len(text))
        buf.extend(text)

    buf.extend(_story_tail(state, customs))

    raw = _encode_base32(bytes(buf))
    groups = [raw[i : i + 4] for i in range(0, len(raw), 4)]
    return "XF-" + "-".join(groups)


class RecipeError(ValueError):
    pass


def decode_recipe(code: str) -> dict[str, Any]:
    """Restore a desk from a recipe. Photos must be attached again."""
    text = "".join(code.upper().split())
    if text.startswith("XF-"):
        text = text[3:]
    text = text.replace("-", "")
    if not text:
        raise RecipeError("That recipe is empty.")
    try:
        data = _decode_base32(text)
    except ValueError as exc:
        raise RecipeError(str(exc)) from exc
    if len(data) < 14 or data[0] not in (1, 2, 3, 4):
        raise RecipeError("This desk does not read that recipe version.")
    version = data[0]

    cursor = 1
    quality = {0: "draft", 1: "final", 2: "turbo", 3: "live"}.get(int(data[cursor]), "draft")
    cursor += 1
    preset_index = data[cursor]
    cursor += 1
    preset_ids = [preset["id"] for preset in PRESETS]
    preset = preset_ids[preset_index] if preset_index < len(preset_ids) else ""
    sliders = {}
    for key in SLIDERS:
        sliders[key] = round(data[cursor] / 255.0, 4)
        cursor += 1
    if cursor + 2 > len(data):
        raise RecipeError("Recipe ended inside the locks.")
    bits = data[cursor] | (data[cursor + 1] << 8)
    cursor += 2
    if cursor >= len(data):
        raise RecipeError("Recipe ended before the script.")
    n_blocks = data[cursor]
    cursor += 1
    if n_blocks < 1 or n_blocks > 24:
        raise RecipeError("Recipe script length is not usable.")
    raw_blocks = []
    for _ in range(n_blocks):
        if cursor + 3 > len(data):
            raise RecipeError("Recipe ended inside a block.")
        raw_blocks.append((data[cursor], data[cursor + 1], data[cursor + 2]))
        cursor += 3
    if cursor >= len(data):
        raise RecipeError("Recipe ended before the custom forms.")
    n_custom = data[cursor]
    cursor += 1
    if n_custom > 8:
        raise RecipeError("Too many custom forms in the recipe.")
    customs = []
    for index in range(n_custom):
        if cursor >= len(data):
            raise RecipeError("Recipe ended inside a custom form.")
        length = data[cursor]
        cursor += 1
        if cursor + length + 1 > len(data):
            raise RecipeError("Recipe ended inside a custom name.")
        noun = data[cursor : cursor + length].decode("utf-8", errors="replace")
        cursor += length
        kind = "image" if data[cursor] == 1 else "noun"
        cursor += 1
        customs.append(
            {
                "id": f"c{index}",
                "noun": noun,
                "name": noun,
                "kind": kind,
                "blurb": "Photo was not stored in the code — attach it again."
                if kind == "image"
                else "Restored from the recipe.",
                "accent": "#e7d7c3",
            }
        )
    blocks = []
    pack_ids = [form["id"] for form in FORM_PACK]
    custom_base = 16 if version == 1 else CUSTOM_BASE
    for form_index, hold_q, packed in raw_blocks:
        transition_index = packed & 0x0F
        energy_index = packed >> 4
        if form_index == UNTITLED_FORM:
            form = ""
        elif version == 1 and form_index < 6:
            form = pack_ids[form_index]
        elif version != 1 and form_index < len(pack_ids):
            form = pack_ids[form_index]
        elif custom_base <= form_index < custom_base + len(customs):
            form = customs[form_index - custom_base]["id"]
        else:
            form = "sphere"
        transition = TRANSITIONS[transition_index] if transition_index < len(TRANSITIONS) else "ribbon"
        energy = ENERGIES[energy_index] if energy_index < len(ENERGIES) else ""
        blocks.append(
            {
                "form": form,
                "hold": round(hold_q / 10.0, 2),
                "transition": transition,
                "energy": energy,
            }
        )
    register = ""
    palette = "neutral"
    flash = "normal"
    cards: list[dict[str, str]] = []
    if version >= 2 and cursor + 4 <= len(data):
        register_ids = [item["id"] for item in REGISTERS]
        register_index = data[cursor]
        cursor += 1
        register = register_ids[register_index] if register_index < len(register_ids) else ""
        palette_index = data[cursor]
        cursor += 1
        palette = PALETTES[palette_index] if palette_index < len(PALETTES) else "neutral"
        flash_index = data[cursor]
        cursor += 1
        flash = FLASHES[flash_index] if flash_index < len(FLASHES) else "normal"
        n_cards = data[cursor]
        cursor += 1
        if n_cards > 4:
            raise RecipeError("Too many text cards in the recipe.")
        for _ in range(n_cards):
            if cursor + 2 > len(data):
                raise RecipeError("Recipe ended inside a text card.")
            at = "drop" if data[cursor] == 0 else "outro"
            cursor += 1
            length = data[cursor]
            cursor += 1
            if cursor + length > len(data):
                raise RecipeError("Recipe ended inside a text card.")
            text = data[cursor : cursor + length].decode("utf-8", errors="replace")
            cursor += length
            cards.append({"at": at, "text": text})
    brief = ""
    mode = "simple"
    scenes: list[dict[str, Any]] = []
    motif = ""
    callback = ""
    climax = None
    if version in (3, 4):
        brief, mode, scenes, motif, callback, climax, cursor = _read_story_tail(
            data, cursor, customs, extended=version >= 4
        )
    return {
        "preset": preset,
        "quality": quality,
        "sliders": sliders,
        "locks": _locks_from_bits(bits),
        "blocks": blocks,
        "customs": customs,
        "register": register,
        "palette": palette,
        "flash": flash,
        "cards": cards,
        "brief": brief,
        "mode": mode,
        "scenes": scenes,
        "motif": motif,
        "callback": callback,
        "climax": climax,
    }


def _pack_text(buf: bytearray, text: str, limit: int) -> None:
    raw = " ".join(str(text or "").split()).encode("utf-8")[:limit]
    buf.append(len(raw))
    buf.extend(raw)


def _read_text(data: bytes, cursor: int) -> tuple[str, int]:
    if cursor >= len(data):
        raise RecipeError("Recipe ended inside the storyboard.")
    length = data[cursor]
    cursor += 1
    if cursor + length > len(data):
        raise RecipeError("Recipe ended inside the storyboard.")
    text = data[cursor : cursor + length].decode("utf-8", errors="replace")
    return text, cursor + length


def _story_tail(state: dict, customs: list[dict]) -> bytes:
    from xenoform.storyboard import BEATS, EDITS, MOODS, MOVES, SHOTS

    buf = bytearray()
    buf.append(1 if state.get("mode") == "director" else 0)
    _pack_text(buf, str(state.get("brief") or ""), 180)
    motif = str(state.get("motif") or "")
    buf.append(_form_index(motif, customs) if motif else 255)
    climax = state.get("climax")
    buf.append(255 if climax is None else max(0, min(255, int(climax))))
    _pack_text(buf, str(state.get("callback") or ""), 140)
    scenes = list(state.get("scenes") or [])[:24]
    buf.append(len(scenes))
    for scene in scenes:
        buf.append(_form_index(str(scene.get("form") or "sphere"), customs))
        beat = str(scene.get("beat") or "rising")
        buf.append(BEATS.index(beat) if beat in BEATS else 1)
        shot = str(scene.get("shot") or "wide")
        buf.append(SHOTS.index(shot) if shot in SHOTS else 0)
        move = str(scene.get("move") or "hold")
        buf.append(MOVES.index(move) if move in MOVES else 4)
        edit = str(scene.get("edit") or "ribbon")
        buf.append(EDITS.index(edit) if edit in EDITS else 5)
        mood = str(scene.get("mood") or "void")
        buf.append(MOODS.index(mood) if mood in MOODS else 7)
        buf.append(max(1, min(255, int(scene.get("bars") or 1))))
        hold = max(0.2, min(25.5, float(scene.get("hold") or 1.0)))
        buf.append(int(round(hold * 10)))
        start_cs = max(0, min(65535, int(round(float(scene.get("start") or 0.0) * 100))))
        end_cs = max(0, min(65535, int(round(float(scene.get("end") or 0.0) * 100))))
        buf.append((start_cs >> 8) & 255)
        buf.append(start_cs & 255)
        buf.append((end_cs >> 8) & 255)
        buf.append(end_cs & 255)
        flags = (1 if scene.get("edited") else 0) | (2 if scene.get("motif") else 0) | (4 if scene.get("signature") else 0)
        buf.append(flags)
        _pack_text(buf, str(scene.get("action") or ""), 160)
        _pack_text(buf, str(scene.get("verb") or ""), 40)
        _pack_text(buf, str(scene.get("protagonist") or ""), 80)
        _pack_text(buf, str(scene.get("goal") or ""), 160)
        _pack_text(buf, str(scene.get("payoff") or ""), 160)
    return bytes(buf)


def _read_story_tail(data: bytes, cursor: int, customs: list[dict], extended: bool = False) -> tuple:
    from xenoform.storyboard import BEATS, EDITS, MOODS, MOVES, SHOTS, _guide

    if cursor >= len(data):
        raise RecipeError("Recipe ended before the storyboard.")
    mode = "director" if data[cursor] == 1 else "simple"
    cursor += 1
    brief, cursor = _read_text(data, cursor)
    if cursor + 1 > len(data):
        raise RecipeError("Recipe ended inside the storyboard.")
    motif_index = data[cursor]
    cursor += 1
    if cursor >= len(data):
        raise RecipeError("Recipe ended inside the storyboard.")
    climax_index = data[cursor]
    cursor += 1
    callback, cursor = _read_text(data, cursor)
    if cursor >= len(data):
        raise RecipeError("Recipe ended before the scenes.")
    n_scenes = data[cursor]
    cursor += 1
    if n_scenes > 24:
        raise RecipeError("Too many scenes in the recipe.")
    pack_ids = [form["id"] for form in FORM_PACK]
    scenes = []
    for index in range(n_scenes):
        if cursor + 13 > len(data):
            raise RecipeError("Recipe ended inside a scene.")
        form_index = data[cursor]
        beat = BEATS[data[cursor + 1]] if data[cursor + 1] < len(BEATS) else "rising"
        shot = SHOTS[data[cursor + 2]] if data[cursor + 2] < len(SHOTS) else "wide"
        move = MOVES[data[cursor + 3]] if data[cursor + 3] < len(MOVES) else "hold"
        edit = EDITS[data[cursor + 4]] if data[cursor + 4] < len(EDITS) else "ribbon"
        mood = MOODS[data[cursor + 5]] if data[cursor + 5] < len(MOODS) else "void"
        bars = data[cursor + 6] or 1
        hold = round(data[cursor + 7] / 10.0, 2)
        start = ((data[cursor + 8] << 8) | data[cursor + 9]) / 100.0
        end = ((data[cursor + 10] << 8) | data[cursor + 11]) / 100.0
        flags = data[cursor + 12]
        cursor += 13
        action, cursor = _read_text(data, cursor)
        verb = ""
        protagonist = ""
        goal = ""
        payoff = ""
        if extended:
            verb, cursor = _read_text(data, cursor)
            protagonist, cursor = _read_text(data, cursor)
            goal, cursor = _read_text(data, cursor)
            payoff, cursor = _read_text(data, cursor)
        if form_index == UNTITLED_FORM:
            form = ""
        elif form_index < len(pack_ids):
            form = pack_ids[form_index]
        elif CUSTOM_BASE <= form_index < CUSTOM_BASE + len(customs):
            form = customs[form_index - CUSTOM_BASE]["id"]
        else:
            form = "sphere"
        scene = {
            "index": index,
            "start": round(start, 4),
            "end": round(end, 4),
            "seconds": round(max(0.0, end - start), 4),
            "bars": int(bars),
            "hold": hold,
            "beat": beat,
            "form": form,
            "action": action,
            "shot": shot,
            "move": move,
            "edit": edit,
            "mood": mood,
            "motif": bool(flags & 2),
            "edited": bool(flags & 1),
            "signature": bool(flags & 4),
            "verb": verb,
            "protagonist": protagonist,
            "goal": goal,
            "payoff": payoff,
            "conditioning": "signature" if flags & 4 else "first-frame",
        }
        scene["guide"] = _guide(scene)
        scenes.append(scene)
    motif = _motif_from_index(motif_index, customs)
    climax = None if climax_index == 255 else int(climax_index)
    return brief, mode, scenes, motif, callback, climax, cursor


def _motif_from_index(motif_index: int, customs: list[dict]) -> str:
    pack_ids = [form["id"] for form in FORM_PACK]
    if motif_index in (255, UNTITLED_FORM):
        return ""
    if motif_index < len(pack_ids):
        return pack_ids[motif_index]
    if CUSTOM_BASE <= motif_index < CUSTOM_BASE + len(customs):
        return customs[motif_index - CUSTOM_BASE]["id"]
    return ""


def apply_director(features: dict, state: dict) -> dict:
    """Copy features and stamp the script, the band map, and the globals onto it.

    When the desk has a storyboard, those scene cards win: each one becomes a
    block, a restyle prompt, and a camera.
    """
    from xenoform.lessons import capped_fade, default_strengths
    from xenoform.storyboard import blocks_from_scenes, camera_for_scene

    state = dict(state)
    scenes = list(state.get("scenes") or [])
    if scenes:
        state["blocks"] = blocks_from_scenes(scenes)
    out = copy.deepcopy(features)
    duration = float(out.get("duration") or 0.0)
    if duration <= 0 and out.get("frames"):
        duration = float(out["frames"][-1]["t"])
    fps = float(out["fps"])
    laid = layout_blocks(list(state.get("blocks") or []), duration)
    customs = list(state.get("customs") or [])
    sliders = state.get("sliders") or default_sliders()
    kick = _drive(sliders.get("kick", 0.5))
    bass_gain = _drive(sliders.get("bass", 0.5))
    hats = _drive(sliders.get("hats", 0.5))
    vocals = _drive(sliders.get("vocals", 0.5))

    sections = []
    fades = []
    for index, block in enumerate(laid):
        start_frame = int(round(block["start"] * fps))
        end_frame = int(round(block["end"] * fps))
        start_frame = max(0, min(start_frame, int(out["n_frames"]) - 1))
        end_frame = max(start_frame + 1, min(end_frame, int(out["n_frames"])))
        sections.append(
            {
                "index": index,
                "label": block["form"],
                "start": round(block["start"], 6),
                "end": round(block["end"], 6),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "level": 0.0,
                "slope": 0.0,
                "mutate": 0.0,
            }
        )
        fade_frames = capped_fade(block["transition"])
        fades.append(
            {
                "frame": start_frame,
                "fade": fade_frames,
                "transition": block["transition"],
            }
        )

    for frame in out["frames"]:
        t = float(frame["t"])
        block = laid[-1]
        chosen = len(laid) - 1
        for index, candidate in enumerate(laid):
            if candidate["start"] <= t < candidate["end"]:
                block = candidate
                chosen = index
                break
        frame["analyzed_section"] = frame.get("section")
        frame["section"] = f"s{chosen}" if scenes else block["form"]
        frame["form"] = block["form"]
        frame["transition"] = block["transition"]
        frame["transition_fade"] = capped_fade(block["transition"])
        frame["onset_env"] = round(_clip(float(frame["onset_env"]) * kick), 6)
        frame["bass"] = round(_clip(float(frame["bass"]) * bass_gain), 6)
        frame["high"] = round(_clip(float(frame["high"]) * hats), 6)
        frame["mid"] = round(_clip(float(frame["mid"]) * vocals), 6)
        frame["liquidity"] = round(float(sliders.get("liquidity", 0.5)), 4)
        frame["chaos"] = round(float(sliders.get("chaos", 0.5)), 4)
        frame["material"] = round(float(sliders.get("material", 0.5)), 4)
        frame["camera_energy"] = round(float(sliders.get("camera", 0.5)), 4)
        frame["camera_push"] = round(float(sliders.get("bass", 0.5)), 4)
        frame["surface"] = round(float(sliders.get("vocals", 0.5)), 4)
        if scenes and chosen < len(scenes):
            camera = camera_for_scene(scenes[chosen])
            frame["camera_energy"] = camera["camera_energy"]
            frame["camera_push"] = camera["camera_push"]
            frame["lens"] = camera["lens"]
            frame["shot"] = camera["shot"]
            frame["move"] = camera["move"]
            frame["guide"] = scenes[chosen].get("guide") or scenes[chosen].get("action") or ""
            if scenes[chosen].get("conditioning"):
                frame["conditioning"] = scenes[chosen]["conditioning"]
            elif scenes[chosen].get("signature"):
                frame["conditioning"] = "signature"
            else:
                frame["conditioning"] = "first-frame"
            if scenes[chosen].get("retime"):
                frame["retime"] = scenes[chosen]["retime"]
            strengths = default_strengths(str(scenes[chosen].get("edit") or ""), scenes[chosen].get("guide_strengths"))
            frame["guide_strengths"] = strengths
            frame["guide_offset_frames"] = int(strengths.get("offset_frames") or 32)
            exposure = strengths.get("exposure")
            if exposure not in (None, ""):
                frame["exposure"] = float(exposure)
        palette = state.get("palette") or ""
        if palette and palette != "neutral":
            frame["palette"] = palette

    out["sections"] = sections
    out["director_fades"] = fades
    from xenoform.cutdesk import title_cards

    extras = title_cards(str(state.get("title_card") or ""), str(state.get("end_card") or ""), duration)
    out["text_cards"] = text_card_cues(laid, list(state.get("cards") or []) + extras, duration)
    out["director"] = {
        "preset": state.get("preset"),
        "quality": state.get("quality"),
        "register": state.get("register"),
        "palette": state.get("palette"),
        "recipe": encode_recipe(state),
    }
    return out


def text_card_cues(laid: list[dict], cards: list[dict], duration: float) -> list[dict[str, Any]]:
    """Times for the drop card and the outro card. Empty lines are skipped."""
    cues = []
    for card in cards:
        text = " ".join(str(card.get("text") or "").split())
        if not text:
            continue
        if card.get("at") == "drop":
            block = next((item for item in laid if item.get("energy") == "drop"), None)
            if block is None:
                continue
            start = float(block["start"])
            end = min(float(block["end"]), start + 2.4)
        elif card.get("at") == "outro":
            end = float(duration)
            start = max(0.0, end - 2.6)
        elif card.get("at") == "title":
            start = float(card["start"]) if card.get("start") not in (None, "") else 0.35
            end = float(card["end"]) if card.get("end") not in (None, "") else min(float(duration) or 3.0, 3.0)
        elif card.get("at") == "end":
            end = float(card["end"]) if card.get("end") not in (None, "") else float(duration)
            start = float(card["start"]) if card.get("start") not in (None, "") else max(0.0, end - 2.8)
        else:
            continue
        if end - start < 0.35:
            continue
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": text[:90], "at": card.get("at")})
    return cues


def resolve_flash(state: dict, base: float) -> tuple[float, bool]:
    """Register flash policy. Minimal means no beat flash at all."""
    mode = str(state.get("flash") or "normal")
    if mode == "minimal":
        return 0.0, False
    scale = {"soft": 0.45, "normal": 1.0, "hard": 1.7}.get(mode, 1.0)
    amount = float(base) * scale
    if any(block.get("transition") == "droplet-burst" for block in state.get("blocks") or []):
        amount += 0.12
    return min(0.5, amount), True


def prompts_for_state(state: dict) -> dict[str, str]:
    from xenoform.storyboard import scene_prompt

    prompts = {}
    for form in FORM_PACK:
        prompts[form["id"]] = form["prompt"]
    for custom in state.get("customs") or []:
        prompts[custom["id"]] = custom.get("prompt") or custom_prompt(str(custom.get("noun") or custom.get("name") or "form"))
    for index, scene in enumerate(state.get("scenes") or []):
        form = form_by_id(str(scene.get("form") or ""), state.get("customs"))
        base = ""
        if form:
            base = str(form.get("prompt") or "")
        if not base:
            base = custom_prompt(str(scene.get("form") or "form"))
        liquid = str(state.get("preset") or "") == "liquid-metal"
        prompts[f"s{index}"] = scene_prompt(scene, base, liquid=liquid)
    return prompts


def apply_quality(cfg: dict, state: dict) -> dict:
    """Turbo is 384p. Draft is a fast 512-wide pass. Final is 640×360 / 24 fps."""
    out = copy.deepcopy(cfg)
    quality = str(state.get("quality") or "draft")
    out["quality"] = quality
    out.setdefault("comfy", {})
    out.setdefault("segment", {})
    if quality == "final":
        out["fps"] = 24
        out["render"]["width"] = 640
        out["render"]["height"] = 360
        out["render"]["max_steps"] = 40
        out["comfy"]["width"] = int(out["comfy"].get("width") or 512)
        out["comfy"]["height"] = int(out["comfy"].get("height") or 320)
    elif quality == "live":
        out["fps"] = 12
        out["render"]["width"] = 384
        out["render"]["height"] = 216
        out["render"]["max_steps"] = 4
    elif quality == "turbo":
        out["fps"] = 12
        out["render"]["width"] = 384
        out["render"]["height"] = 224
        out["render"]["max_steps"] = 8
        out["comfy"]["width"] = 384
        out["comfy"]["height"] = 224
        out["comfy"]["steps"] = 4
        out["comfy"]["checkpoint_name"] = "ltx-video-2b-v0.9.5.safetensors"
        out["comfy"]["resident"] = True
        out["segment"]["target_seconds"] = 2.0
        out["segment"]["min_seconds"] = 1.0
        out["segment"]["max_seconds"] = 3.0
    else:
        out["fps"] = 12
        out["render"]["width"] = 512
        out["render"]["height"] = 288
        out["render"]["max_steps"] = 24
        out["comfy"]["width"] = 512
        out["comfy"]["height"] = 320
        out["comfy"]["steps"] = min(int(out["comfy"].get("steps") or 20), 12)
    return out


def apply_endpoint(cfg: dict, state: dict) -> dict:
    out = copy.deepcopy(cfg)
    endpoint = str(state.get("endpoint") or "").strip()
    if endpoint:
        out["comfy"]["base_url"] = endpoint
    if state.get("live"):
        out["comfy"]["mode"] = "live"
    else:
        out["comfy"]["mode"] = "dry-run"
    if "addons" in state:
        out["comfy"]["addons"] = bool(state.get("addons"))
    asked = str(state.get("video_model") or "").strip().lower()
    if asked in {"ltx-25", "ltx2.5", "ltx25", "2.5"}:
        out["comfy"]["video_model"] = "ltx-25"
    return out


def fades_for_cuts(features: dict, cuts: list[int], default: int = 4) -> list[int]:
    marks = features.get("director_fades") or []
    if not marks:
        return [default for _ in cuts]
    fps = float(features.get("fps") or 24)
    window = max(1, int(round(0.45 * fps)))
    fades = []
    for cut in cuts:
        nearest = min(marks, key=lambda mark: abs(int(mark["frame"]) - int(cut)))
        if abs(int(nearest["frame"]) - int(cut)) <= window:
            fades.append(int(nearest["fade"]))
        else:
            fades.append(default)
    return fades


def waveform_peaks(features: dict, buckets: int = 420) -> list[float]:
    frames = features["frames"]
    if not frames:
        return []
    peaks = []
    count = len(frames)
    for index in range(buckets):
        start = int(index * count / buckets)
        end = max(start + 1, int((index + 1) * count / buckets))
        peaks.append(max(float(frame["rms"]) for frame in frames[start:end]))
    scale = max(peaks) or 1.0
    return [round(peak / scale, 4) for peak in peaks]


def drop_spans(features: dict) -> list[dict[str, float]]:
    spans = []
    active = None
    for frame in features["frames"]:
        if frame.get("is_drop") and active is None:
            active = float(frame["t"])
        elif active is not None and not frame.get("is_drop"):
            spans.append({"start": round(active, 4), "end": round(float(frame["t"]), 4)})
            active = None
    if active is not None and features["frames"]:
        spans.append({"start": round(active, 4), "end": round(float(features["duration"]), 4)})
    return spans


def public_registers() -> list[dict[str, Any]]:
    rows = []
    for register in REGISTERS:
        rows.append(
            {
                "id": register["id"],
                "name": register["name"],
                "voice": register["voice"],
                "palette": register["palette"],
                "palette_label": register["palette_label"],
                "accent": register["accent"],
                "flash": register["flash"],
                "pacing": register["pacing"],
                "forms": list(register["forms"]),
                "drop_forms": list(register["drop_forms"]),
                "transitions": dict(register["transitions"]),
                "cards": [dict(card) for card in register["cards"]],
                "sliders": dict(register["sliders"]),
                "pack": register["pack"],
            }
        )
    return rows


def session_payload(
    features: dict,
    *,
    audio_id: str,
    title: str,
    video: str,
    endpoint: str,
) -> dict[str, Any]:
    from xenoform.storyboard import (
        BEATS,
        DEMO_BRIEF,
        EDITS,
        MOODS,
        MOVES,
        SHOTS,
        blocks_from_scenes,
        pick_treatment,
        pitch_treatments,
        plan_with_hook,
        stamp_treatment,
        style_bible,
    )

    state = empty_state()
    filled = register_by_id("pynchon")
    brief = DEMO_BRIEF
    scenes, planner = plan_with_hook(features, filled, brief)
    treatment = pick_treatment(brief)
    scenes = stamp_treatment(scenes, treatment)
    treatments = pitch_treatments(brief)
    bible = style_bible(filled, "", moments=next(item["moments"] for item in treatments if item["id"] == treatment))
    state["blocks"] = blocks_from_scenes(scenes)
    state["scenes"] = scenes
    state["brief"] = brief
    state["mode"] = "simple"
    state["sliders"] = dict(filled["sliders"])
    state["cards"] = [dict(card) for card in filled["cards"]]
    state["palette"] = filled["palette"]
    state["flash"] = filled["flash"]
    state["register"] = "pynchon"
    state["preset"] = ""
    state["endpoint"] = endpoint
    state["quality"] = "live"
    state["climax"] = next((scene["index"] for scene in scenes if scene.get("beat") == "climax"), None)
    return {
        "audio_id": audio_id,
        "title": title,
        "duration": round(float(features["duration"]), 4),
        "fps": float(features["fps"]),
        "tempo": round(float(features.get("tempo") or 0.0), 1),
        "waveform": waveform_peaks(features),
        "beats": [round(float(beat), 4) for beat in features.get("beats") or []],
        "drops": drop_spans(features),
        "sections": [
            {
                "label": section["label"],
                "start": round(float(section["start"]), 4),
                "end": round(float(section["end"]), 4),
            }
            for section in features.get("sections") or []
        ],
        "forms": public_forms(),
        "presets": public_presets(),
        "transitions": public_transitions(),
        "registers": public_registers(),
        "scripts": all_scripts(features),
        "blocks": state["blocks"],
        "customs": [],
        "sliders": state["sliders"],
        "locks": state["locks"],
        "quality": state["quality"],
        "preset": state["preset"],
        "register": state["register"],
        "palette": state["palette"],
        "flash": state["flash"],
        "cards": state["cards"],
        "brief": state["brief"],
        "mode": state["mode"],
        "scenes": state["scenes"],
        "motif": "",
        "callback": "",
        "climax": state["climax"],
        "planner": planner,
        "treatments": treatments,
        "treatment": treatment,
        "bible": bible,
        "shots": list(SHOTS),
        "moves": list(MOVES),
        "edits": list(EDITS),
        "moods": list(MOODS),
        "beats_arc": list(BEATS),
        "live": False,
        "endpoint": endpoint,
        "video": video,
        "video_label": "Reference base form",
        "recipe": encode_recipe(state),
        "etas": _eta_table(),
        "audio_url": f"/media/audio/{audio_id}",
        "drive": _live_drive(features),
    }


def _eta_table() -> dict:
    from xenoform.turbo import eta_table

    return eta_table()


def _live_drive(features: dict) -> dict:
    from xenoform.live_mode import live_drive

    return live_drive(features)


Progress = Callable[[str, float, str], None]


def run_directed(
    cfg: dict,
    audio_path: Path,
    state: dict,
    out_path: Path,
    work: Path,
    on_progress: Progress | None = None,
    tier_id: str | None = None,
    cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Analyze, stamp the script, render, restyle, and assemble."""
    from xenoform.analyze import write_features
    from xenoform.assemble import assemble
    from xenoform.hardware import apply_tier, resolve_tier
    from xenoform.pipeline import analyze_file, render_file
    from xenoform.restyle import restyle

    def report(stage: str, frac: float, detail: str) -> None:
        if cancel and cancel():
            from xenoform.turbo import JobCancelled

            raise JobCancelled("Cancelled. The card changed.")
        if on_progress:
            on_progress(stage, frac, detail)

    work.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    quality = str(state.get("quality") or "draft")
    if quality == "live" and not state.get("tiny"):
        report("done", 1.0, "Live is the browser picture. Record writes the mp4.")
        return {
            "mode": "live-preview",
            "chunks": 0,
            "fades": [],
            "seconds": 0.0,
            "detail": "Live plays in the browser.",
        }
    if quality == "turbo" and not state.get("tiny"):
        from xenoform.turbo import run_turbo

        return run_turbo(
            cfg,
            audio_path,
            state,
            out_path,
            work,
            on_progress=on_progress,
            tier_id=tier_id,
            cancel=cancel,
        )
    tuned = apply_endpoint(apply_quality(cfg, state), state)
    tuned = apply_tier(tuned, resolve_tier(tier_id), quality=str(state.get("quality") or "draft"))
    tuned["seed"] = int(state.get("seed") or 2727)
    if state.get("tiny"):
        tuned["fps"] = 8
        tuned["render"]["width"] = 64
        tuned["render"]["height"] = 32
        tuned["render"]["max_steps"] = 4
        tuned["render"]["backend"] = "cpu"
        tuned["comfy"]["mode"] = "dry-run"
        tuned["comfy"]["width"] = 64
        tuned["comfy"]["height"] = 32
        tuned["comfy"]["steps"] = 1
    tuned["prompts"] = {**tuned.get("prompts", {}), **prompts_for_state(state)}
    from xenoform.guardrails import guard_prompts

    tuned["prompts"] = guard_prompts(tuned["prompts"], state)  # anchor / motion_source / still_background / negative_extra

    from xenoform.llm import release_llm

    release_llm()
    report("analyze", 0.05, "Reading the track")
    features_path = work / "features.json"
    features = analyze_file(Path(audio_path), tuned, features_path)
    directed = apply_director(features, state)
    write_features(features_path, directed)
    report("analyze", 1.0, f"{directed['n_frames']} frames on the script")

    report("render", 0.0, "Beauty pass")

    def on_frame(index: int, total: int) -> None:
        report("render", index / max(total, 1), f"Frame {index} / {total}")

    base_path = work / "base.mp4"
    guide = Path(str(state.get("guide_path") or ""))
    used_guide = False
    if guide.is_file() and not state.get("tiny") and quality in {"draft", "final"}:
        from xenoform.errors import plain_error
        from xenoform.live_mode import fit_guide

        try:
            fit_guide(
                guide,
                base_path,
                int(tuned["render"]["width"]),
                int(tuned["render"]["height"]),
                float(tuned["fps"]),
            )
            used_guide = True
            report("render", 1.0, "Live recording is the motion guide")
        except Exception as exc:
            report("render", 0.2, f"The Live recording did not fit. {plain_error(exc)}")
    if not used_guide:
        render_file(directed, tuned, base_path, Path(audio_path), work, on_progress=on_frame)

    from xenoform.cutdesk import maybe_stamp

    maybe_stamp(base_path, state, float(tuned["fps"]))

    mode = "live" if state.get("live") else "dry-run"
    report("restyle", 0.1, "Dry run — base slices pass through" if mode == "dry-run" else "Submitting chunks")
    manifest = restyle(directed, base_path, work / "chunks", tuned, mode=mode)
    report("restyle", 1.0, f"{len(manifest['chunks'])} chunks · {manifest['mode']}")

    report("assemble", 0.3, "Locking the cuts to the track")
    cuts = []
    cursor = 0
    for chunk in manifest["chunks"][:-1]:
        cursor += int(chunk["source_frames"])
        cuts.append(cursor)
    fades = fades_for_cuts(directed, cuts, default=int(tuned["assemble"]["crossfade_frames"]))
    flash, flashes_on = resolve_flash(state, float(tuned["assemble"]["flash_amount"]))
    hit_times: list[float] = []
    if state.get("morph_hit") and not state.get("tiny"):
        from xenoform.morph.plan import plan_board

        locked = plan_board(
            list(state.get("scenes") or []),
            list(directed.get("beats") or []),
            method="keyframe-blend",
            brief=str(state.get("brief") or ""),
            lock=True,
            sections=list(directed.get("sections") or []),
            drops=list(directed.get("drops") or []),
            hit=True,
        )
        hit_times = [float(join["at"]) for join in locked.get("joins") or [] if join.get("hit")]
    assemble(
        manifest,
        audio_path,
        out_path,
        features=directed,
        crossfade_frames=fades,
        beat_flashes=flashes_on and bool(tuned["assemble"]["beat_flashes"]),
        flash_amount=flash,
        crf=int(tuned["assemble"]["crf"]),
        hit_times=hit_times,
    )
    from xenoform.video import overlay_text

    if state.get("interpolate") and not state.get("tiny"):
        from xenoform.errors import plain_error
        from xenoform.live_mode import fill_frames

        try:
            tool = fill_frames(Path(out_path), float(tuned["fps"]), 24.0)
            report("assemble", 0.85, f"Filled to 24 fps with {tool}")
        except Exception as exc:
            report("assemble", 0.85, f"Frame fill did not run. {plain_error(exc)}")
    overlay_text(Path(out_path), directed.get("text_cards") or [])
    try:
        from xenoform.director_notes import write_director_notes

        write_director_notes(work, state, directed, tuned)
    except Exception:
        log.exception("director notes")
    report("assemble", 1.0, "Cut locked")
    report("done", 1.0, "Ready to watch")
    return {"mode": mode, "chunks": len(manifest["chunks"]), "fades": fades}
