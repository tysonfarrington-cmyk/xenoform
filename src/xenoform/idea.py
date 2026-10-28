"""The idea line (``xenoform.idea``): what the Simple desk's one line asks the cut for.

The line used to be read for catalogue words alone: a noun of ``configs/subjects.json`` opened the cut and its family
filled the chain, and every other word did nothing, so "girl dancing to rave music in a cyber punk city outside
wearhouse, lazers" on an ink-wash cut (Tys, 26 Oct) gave the pool's usual octopus and jellyfish. This module reads
the line into three things the cut already knows how to make:

- **scenes**: the place and its light, as scene subjects (``stills.grow(kind="scene")`` renders a typed wide frame):
  "a cyberpunk city outside a warehouse, lasers";
- **objects**: the catalogue nouns the line names (``objects``: the pick opens on them and their family fills the
  chain, as before) and the things the catalogue lacks (``own``: grown as the user's own shapes, first in the chain):
  "laser";
- **performer**: a person doing something ("girl dancing" → dancing; "singing" → sing; a person with no performance →
  the auto mix). Polly is in the desk's Work in progress (28 Oct): the line cues her style, it no longer switches her on.

``read`` is a rule parser, no model: a few lexicons (places, skies and lights, people, performances, music words), a
spelling map for the typos a line is typed with, comma groups split again at the prepositions that introduce a
place. ``xenoform.llm`` refines it when ``XENO_LLM_URL`` is set (``refine``): the model gets the same three slots to
fill and the rules keep what it cannot (an object it names is kept only when the catalogue knows it or it is short
enough to grow as a shape). ``shape_state`` turns a reading into make-body choices (Scenes to Mix when the line gave a
scene and the user left it Off; the cued style when Polly is on); ``grow_plan`` says what a
Make will grow first. The desk shows ``summary`` under the line (``POST /api/simple/idea``), the record keeps the
whole reading, and ``morph_pass.pick_stills`` puts the typed scenes and shapes first through ``reading_for``.
"""
from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("xenoform.idea")

MAX_SCENES = 2          # scene subjects one line can ask for (a third place is noise)
MAX_OBJECTS = 6         # catalogue nouns kept from one line
MAX_OWN = 5             # typed shapes grown for one line (about six seconds each); a theme brings five
SCENES_PER_SUBJECT = 3  # renders of one typed scene subject (one seed each; the duplicate check culls near copies)
SCENES_MAX = 4          # scenes one Make grows for the line
SHAPES_MAX = 5          # shapes (own and catalogue) one Make grows for the line
SUBJECT_LIMIT = 80      # a scene subject is a short sentence (stills.SCENE_NOUN_LIMIT)


def _clip(text: str) -> str:
    """A scene subject cut to ``SUBJECT_LIMIT`` at a word (``stills.clip_words``), never "...of birds unt"."""
    from xenoform.stills import clip_words

    return clip_words(text, SUBJECT_LIMIT)
PERFORMER_DEFAULT = 2   # Polly's slots when she is switched on (the line no longer switches her on; kept for callers)

STOP = frozenset(("a an the and or of to in on by with for from at into over under as is are its it this that these those "
                  "my our your his her their some any one two three very really just while then there here where when "
                  "who which what also too so up down out off through across along around about like than").split())

# the typos a line is typed with, and the two-word forms of one-word places
SPELL = {"wearhouse": "warehouse", "warhouse": "warehouse", "lazer": "laser", "lazers": "lasers", "lazors": "lasers",
         "neone": "neon", "cyber punk": "cyberpunk", "cyber-punk": "cyberpunk", "cyberpunk city": "cyberpunk city",
         "night club": "nightclub", "night-club": "nightclub", "sky scraper": "skyscraper", "skyscrapers": "skyscrapers",
         "car-park": "car park", "sci fi": "sci-fi", "scifi": "sci-fi", "disco-ball": "disco ball",
         "dancefloor": "dance floor", "dancing floor": "dance floor", "grafitti": "graffiti", "grafiti": "graffiti",
         "allyway": "alleyway", "ally": "alley", "forrest": "forest", "dessert": "desert", "cementery": "cemetery",
         "cemetary": "cemetery", "lightening": "lightning", "fireworks": "fireworks", "rooftops": "rooftops"}

PREPOSITIONS = frozenset(("in inside outside at on under over above beneath below through across beyond near by into onto "
                          "along around behind before against among between amid amidst within atop underneath past "
                          "towards toward down up out").split())

# places: the word makes its chunk a scene subject
PLACES = frozenset(("city cities street streets alley alleys alleyway alleyways lane lanes road roads highway freeway motorway "
                    "bridge bridges tunnel tunnels underpass overpass subway metro station platform warehouse warehouses "
                    "factory factories mill hangar garage basement bunker rooftop rooftops roof skyline downtown suburb "
                    "suburbs town village harbour harbor pier docks dock port marina beach shore shoreline coast coastline "
                    "cliff cliffs cove lagoon reef sea ocean lake lakes river rivers waterfall swamp marsh marshes wetland "
                    "bog forest forests woods woodland jungle rainforest grove orchard garden gardens park meadow field "
                    "fields farm prairie steppe savanna savannah desert dune dunes canyon gorge valley mountain mountains "
                    "peak summit ridge glacier volcano crater cave caves cavern grotto mine quarry plain plains plateau "
                    "tundra island islands archipelago atoll cathedral church chapel temple shrine monastery mosque palace "
                    "castle fortress ruins ruin tower towers skyscraper skyscrapers observatory laboratory lab library "
                    "museum gallery theatre theater cinema arena stadium club nightclub disco bar pub lounge cafe diner "
                    "kitchen bedroom bathroom hallway corridor corridors hall ballroom attic loft studio stage backstage "
                    "festival carnival fairground arcade mall market bazaar office classroom school hospital asylum prison "
                    "courtyard plaza square greenhouse graveyard cemetery crypt catacomb catacombs sewer sewers aquarium pool "
                    "rink carpark parking airport runway deck cabin cockpit elevator lift room rooms world land landscape "
                    "cityscape seascape wasteland battlefield badlands quarry dam canal canals pyramids metropolis "
                    "dance floor floor void abyss space outer cosmos orbit nebula galaxy galaxies universe planet planets "
                    "sky skies horizon heavens underworld underground underwater seabed seafloor abyssal").split())

# skies, weather and light: the detail of a scene; a scene with none of these is still a scene
SKIES = frozenset(("moon moonlight sun sunset sunrise dawn dusk twilight night midnight noon stars starlight starfield aurora "
                   "lightning storm thunder thunderstorm rain rainstorm drizzle snow snowfall blizzard hail fog mist haze "
                   "smoke steam dust ash embers sparks fire flames neon glow glowing lights light beams candlelight lamplight "
                   "moonlit sunlit backlit rainbow rainbows clouds cloud overcast eclipse comet comets meteor meteors shadows "
                   "shadow darkness dark gloom daylight sunlight").split())
# "at dusk", "in the rain": no article on a time of day or a weather
NO_ARTICLE = frozenset(("dusk dawn night midnight noon sunset sunrise twilight rain snow fog mist haze smoke dust steam ash "
                        "moonlight sunlight starlight daylight candlelight lamplight darkness neon lightning space dark gloom "
                        "thunder drizzle hail sleet").split())

# lights and props that are things in their own right: a scene detail and a shape to grow (the brief's "lasers")
LIGHT_OBJECTS = {"laser": "laser", "lasers": "laser", "strobe": "strobe light", "strobes": "strobe light",
                 "spotlight": "spotlight", "spotlights": "spotlight", "searchlight": "searchlight", "searchlights": "searchlight",
                 "firework": "firework burst", "fireworks": "firework burst", "sparkler": "sparkler", "sparklers": "sparkler",
                 "flare": "flare", "flares": "flare", "glowstick": "glow stick", "glowsticks": "glow stick",
                 "headlights": "headlight", "lanterns": "lantern", "lantern": "lantern", "candles": "candle", "candle": "candle"}

PEOPLE = frozenset(("girl girls woman women boy boys man men lady guy guys dancer dancers singer singers drummer drummers "
                    "guitarist pianist keyboardist dj djs performer performers musician musicians vocalist rapper band crowd "
                    "people person someone somebody she he her him polly character figure kid kids child children "
                    "model").split())

# what she does: the word -> the Performance chip (dense.PERFORMER_STYLES); -ing forms and role nouns imply a person
PERFORMANCES = {
    "dance": ("dance", "dances", "dancing", "danced", "dancer", "dancers", "raving", "raves", "voguing", "twerking", "moshing",
              "headbanging", "jumping", "bouncing"),
    "sing": ("sing", "sings", "singing", "singer", "singers", "vocals", "vocal", "vocalist", "lipsync", "karaoke", "rapping",
             "raps", "rapper", "serenading", "crooning"),
    "drums": ("drumming", "drummer", "drummers", "drum", "drums", "percussion"),
    "keys": ("keys", "keyboard", "keyboards", "synth", "synths", "synthesizer", "synthesizers", "piano", "pianist",
             "keyboardist", "organ"),
    "guitar": ("guitar", "guitars", "guitarist", "strumming", "shredding", "bass"),
}
PERSON_VERBS = frozenset(w for style, words in PERFORMANCES.items() for w in words
                         if w.endswith("ing") or w.endswith("er") or w.endswith("ers") or w.endswith("ist"))
PERFORM_VERBS = frozenset("plays playing performs performing performance perform jamming jams".split())
INSTRUMENT_NOUNS = frozenset(("drum", "drums", "keys", "keyboard", "keyboards", "synth", "synths", "synthesizer", "synthesizers",
                              "piano", "guitar", "guitars", "bass", "organ", "percussion", "vocals", "vocal"))
PARTY = frozenset("rave party club nightclub disco festival dancefloor techno house trance edm dubstep".split())
MUSIC = frozenset(("music song songs track tracks beat beats bass bpm tempo rhythm sound sounds audio techno house trance "
                   "dubstep edm hiphop hip hop rap rock metal jazz funk soul pop disco electro electronic ambient drone "
                   "lofi lo fi synthwave vaporwave").split())
# the words a scene chunk keeps as its own: anything else that is not a place, sky, article or adjective-like modifier
# stays too (a "cyberpunk city" keeps cyberpunk); these never become a shape on their own
MODIFIERS = frozenset(("cyberpunk neon dark bright wet rainy foggy misty empty abandoned giant huge tiny small big old ancient "
                       "futuristic retro vintage glowing burning frozen golden silver chrome glass black white red blue green "
                       "purple violet pink magenta cyan amber orange yellow cold hot warm cool wild slow fast deep high low "
                       "endless infinite outer inner lonely strange alien haunted holy sacred secret hidden broken shattered "
                       "melting liquid dripping floating flying spinning falling rising exploding electric digital cosmic "
                       "lunar solar sci-fi dystopian utopian industrial gothic baroque brutalist minimal surreal dreamy "
                       "epic moody grimy gritty glossy shiny matte rusty mossy snowy sunny stormy windy quiet loud busy "
                       "crowded deserted derelict flooded submerged ruined crumbling vast tall long wide narrow").split())

CONNECTORS = frozenset("and or to with of".split())

# A theme the line names grows its things (Tys, 28 Oct: "make a theme word like 'car rally racing' grow four or five
# related things on its own"). A comma group whose last word is one of a theme's words (a trailing "theme", "vibe" or
# "style" ignored) is that theme, unless it names something the library knows or a place: "car rally racing" and
# "pirates" are themes, "a rally car" is a thing. Each theme's things are single objects a still can show whole on a
# plain ground; the catalogue's own nouns among them join the objects, the rest are grown as shapes.
THEMES: dict[str, dict] = {
    "racing": {"words": "racing race races rally rallies rallying motorsport motorsports grandprix nascar f1 drifting karting",
               "things": ["rally car", "racing helmet", "trophy", "chequered flag", "steering wheel"]},
    "space": {"words": "astronaut astronauts spaceflight cosmonaut nasa scifi spacefaring",
              "things": ["astronaut helmet", "rocket", "satellite", "ringed planet", "lunar lander"]},
    "underwater": {"words": "undersea marine nautical diving scuba",
                   "things": ["diving helmet", "anchor", "jellyfish", "ship's wheel", "seashell"]},
    "pirates": {"words": "pirate pirates buccaneer buccaneers",
                "things": ["treasure chest", "pirate hat", "cutlass", "ship in a bottle", "compass"]},
    "halloween": {"words": "halloween spooky horror",
                  "things": ["carved pumpkin", "skull", "witch hat", "black cat", "candelabra"]},
    "christmas": {"words": "christmas xmas festive yuletide",
                  "things": ["bauble", "reindeer", "snow globe", "gift box", "candy cane"]},
    "football": {"words": "football soccer",
                 "things": ["football", "football boot", "trophy", "whistle", "goalkeeper glove"]},
    "basketball": {"words": "basketball nba",
                   "things": ["basketball", "basketball hoop", "sneaker", "trophy", "scoreboard"]},
    "skateboarding": {"words": "skating skateboarding skater skaters",
                      "things": ["skateboard", "sneaker", "spray can", "boombox", "traffic cone"]},
    "surfing": {"words": "surf surfing surfer surfers",
                "things": ["surfboard", "seashell", "palm tree", "sunglasses", "flip flop"]},
    "gaming": {"words": "gaming gamer gamers videogame videogames",
               "things": ["arcade cabinet", "game controller", "joystick", "pixel heart", "cassette tape"]},
    "coffee": {"words": "coffee espresso barista",
               "things": ["coffee cup", "espresso machine", "coffee bean", "moka pot", "croissant"]},
    "cooking": {"words": "cooking baking chef chefs cookery",
                "things": ["chef's knife", "cast iron pan", "whisk", "layer cake", "pepper grinder"]},
    "medieval": {"words": "medieval knight knights kingdom chivalry",
                 "things": ["knight's helmet", "sword", "shield", "crown", "goblet"]},
    "samurai": {"words": "samurai ninja ninjas dojo",
                "things": ["katana", "samurai helmet", "paper lantern", "bonsai tree", "folding fan"]},
    "egypt": {"words": "egypt egyptian pharaoh pharaohs",
              "things": ["pharaoh mask", "scarab", "ankh", "sphinx", "canopic jar"]},
    "wild west": {"words": "western cowboy cowboys wildwest",
                  "things": ["cowboy hat", "horseshoe", "sheriff badge", "cactus", "cowboy boot"]},
    "magic": {"words": "magic wizard wizards witch witches witchcraft sorcery sorcerer",
              "things": ["wizard hat", "crystal ball", "spell book", "potion bottle", "magic wand"]},
    "dinosaurs": {"words": "dinosaur dinosaurs prehistoric jurassic",
                  "things": ["t-rex skull", "dinosaur egg", "ammonite", "amber", "fern"]},
    "robots": {"words": "robot robots robotics android androids cyborg cyborgs",
               "things": ["robot head", "circuit board", "robotic arm", "gear", "microchip"]},
    "casino": {"words": "casino casinos gambling poker vegas",
               "things": ["dice", "poker chip", "playing card", "slot machine", "roulette wheel"]},
    "circus": {"words": "circus funfair",
               "things": ["circus tent", "carousel horse", "juggling pin", "ringmaster hat", "balloon animal"]},
    "fashion": {"words": "fashion couture catwalk",
                "things": ["high heel", "handbag", "perfume bottle", "sunglasses", "lipstick"]},
    "gardening": {"words": "gardening gardener botanical florist",
                  "things": ["watering can", "rose", "tulip", "garden gnome", "flower pot"]},
    "aviation": {"words": "aviation airshow aeroplanes airplanes planes pilots",
                 "things": ["propeller plane", "pilot goggles", "jet engine", "hot air balloon", "paper plane"]},
    "trains": {"words": "train trains railway railways railroad",
               "things": ["steam locomotive", "railway signal", "pocket watch", "train ticket", "lantern"]},
    "science": {"words": "science scientist scientists chemistry physics",
                "things": ["microscope", "test tube", "atom model", "beaker", "telescope"]},
    "camping": {"words": "camping hiking outdoors",
                "things": ["tent", "lantern", "compass", "hiking boot", "campfire"]},
    "sweets": {"words": "candy sweets dessert desserts confectionery",
               "things": ["lollipop", "cupcake", "macaron", "doughnut", "gummy bear"]},
    "boxing": {"words": "boxing boxer boxers",
               "things": ["boxing glove", "championship belt", "punching bag", "boxing bell", "trophy"]},
    "golf": {"words": "golf golfing golfer",
             "things": ["golf ball", "golf club", "golf flag", "trophy", "golf cart"]},
    "travel": {"words": "travel travelling traveling holiday vacation",
               "things": ["suitcase", "passport", "globe", "camera", "postcard"]},
    "romance": {"words": "wedding romance valentine valentines",
                "things": ["wedding ring", "rose", "heart locket", "champagne glass", "love letter"]},
}
THEME_OF = {w: name for name, t in THEMES.items() for w in t["words"].split()}
THEME_TAIL = frozenset("theme themed vibe vibes style aesthetic stuff".split())  # "a racing theme" is the racing theme
THEME_THINGS = 5  # what one theme grows at most (the shapes cap is the same)

EMPTY: dict = {"line": "", "scenes": [], "objects": [], "own": [], "family": "", "performer": None, "feel": None, "summary": "",
               "source": "rules", "theme": "", "theme_things": []}

# ------------------------------------------------------------------------------------------------ the feel
# How it should feel (27 Oct; Pause's demo: "Add your clips. Then say how it should feel."): a comma group made only of
# feel words ("slow and dreamy", "hard and glitchy", "warm, hazy") sets the four knobs and the Look the way a director
# asks for them. Only a whole group of feel words counts, so "a dark lake" stays a place and "a hard hat" a thing. The
# values are knob positions (0..1); several words average per knob, "very" pushes a word a step further out, and the
# first colour word picks the Look.
FEEL_WORDS: dict[str, dict] = {
    # pace (Speed: the cut density and the trail length)
    "slow": {"speed": 0.2}, "slower": {"speed": 0.2}, "unhurried": {"speed": 0.2}, "languid": {"speed": 0.15},
    "floaty": {"speed": 0.25, "glow": 0.6}, "floating": {"speed": 0.25, "glow": 0.6}, "drifting": {"speed": 0.25},
    "fast": {"speed": 0.85}, "faster": {"speed": 0.85}, "quick": {"speed": 0.8}, "rapid": {"speed": 0.9},
    "frantic": {"speed": 0.95, "chaos": 0.8, "intensity": 0.85}, "hectic": {"speed": 0.9, "chaos": 0.7},
    # energy (Intensity: the beat pulse and the flash)
    "calm": {"intensity": 0.25, "chaos": 0.1, "speed": 0.35}, "gentle": {"intensity": 0.25, "chaos": 0.1},
    "soft": {"intensity": 0.3, "glow": 0.5}, "chill": {"intensity": 0.3, "speed": 0.35, "chaos": 0.1},
    "mellow": {"intensity": 0.3, "speed": 0.35}, "peaceful": {"intensity": 0.2, "chaos": 0.05, "speed": 0.3},
    "serene": {"intensity": 0.2, "chaos": 0.05, "glow": 0.55},
    "meditative": {"intensity": 0.2, "speed": 0.2, "chaos": 0.0}, "quiet": {"intensity": 0.2},
    "subtle": {"intensity": 0.25, "glow": 0.3}, "minimal": {"intensity": 0.2, "chaos": 0.0, "glow": 0.2},
    "punchy": {"intensity": 0.8}, "hard": {"intensity": 0.85, "chaos": 0.6}, "heavy": {"intensity": 0.85, "speed": 0.6},
    "aggressive": {"intensity": 0.9, "chaos": 0.7, "speed": 0.75}, "intense": {"intensity": 0.9},
    "energetic": {"intensity": 0.8, "speed": 0.7}, "hype": {"intensity": 0.85, "speed": 0.75},
    "hyped": {"intensity": 0.85, "speed": 0.75}, "explosive": {"intensity": 0.95, "chaos": 0.7},
    "loud": {"intensity": 0.85}, "bouncy": {"intensity": 0.7, "speed": 0.65},
    # chaos (Chaos: the punches, the stutters, the camera's swing and the handoff kinds)
    "glitchy": {"chaos": 0.9}, "glitch": {"chaos": 0.9}, "chaotic": {"chaos": 1.0, "speed": 0.85},
    "wild": {"chaos": 0.85}, "crazy": {"chaos": 0.9, "speed": 0.8}, "manic": {"chaos": 0.95, "speed": 0.9},
    "unhinged": {"chaos": 1.0, "intensity": 0.9}, "maxed": {"chaos": 1.0, "speed": 1.0, "intensity": 1.0, "glow": 1.0},
    "chopped": {"chaos": 0.8, "speed": 0.85}, "clean": {"chaos": 0.05, "glow": 0.2},
    "smooth": {"chaos": 0.1, "speed": 0.35}, "steady": {"chaos": 0.05}, "still": {"chaos": 0.0, "speed": 0.2},
    "hypnotic": {"speed": 0.3, "chaos": 0.15, "glow": 0.55},
    # light (Glow: the bloom)
    "dreamy": {"glow": 0.75, "speed": 0.3, "chaos": 0.1}, "hazy": {"glow": 0.7}, "glowing": {"glow": 0.8},
    "ethereal": {"glow": 0.75, "intensity": 0.35}, "luminous": {"glow": 0.8}, "blooming": {"glow": 0.8},
    "bright": {"glow": 0.65}, "dark": {"glow": 0.2}, "moody": {"glow": 0.25, "look": "noir-glow"},
    "noir": {"glow": 0.3, "look": "noir-glow"}, "gritty": {"glow": 0.15, "chaos": 0.5}, "crisp": {"glow": 0.1},
    "sharp": {"glow": 0.1},
    # colour (the Look)
    "warm": {"look": "warm-leak"}, "golden": {"look": "warm-leak"}, "cold": {"look": "cool-echo"},
    "cool": {"look": "cool-echo"}, "icy": {"look": "cool-echo"}, "trippy": {"look": "negative-rush", "chaos": 0.6},
    "psychedelic": {"look": "negative-rush", "chaos": 0.7, "glow": 0.7},
    "electric": {"look": "cyan-flash", "intensity": 0.8}, "flashy": {"look": "cyan-flash", "intensity": 0.75},
}
FEEL_BOOST = frozenset("very super extremely really so totally insanely".split())
FEEL_FILLER = frozenset(("and a an the but yet then with feel feels feeling vibe vibes mood tone pace paced energy it "
                         "should be make keep more quite kinda bit little all over overall throughout").split()) | FEEL_BOOST
FEEL_KNOBS = ("intensity", "speed", "chaos", "glow")


def feel_of(group_words: list[str]) -> dict | None:
    """The feel a comma group asks for when every word in it is a feel word or a filler; None otherwise."""
    words = [w for w in group_words if w]
    if not words or not any(w in FEEL_WORDS for w in words):
        return None
    if any(w not in FEEL_WORDS and w not in FEEL_FILLER for w in words):
        return None
    picked: list[str] = []
    sums: dict[str, list[float]] = {}
    look = ""
    for i, w in enumerate(words):
        spec = FEEL_WORDS.get(w)
        if not spec:
            continue
        boost = i > 0 and words[i - 1] in FEEL_BOOST
        picked.append(("very " if boost else "") + w)
        for knob, value in spec.items():
            if knob == "look":
                look = look or str(value)
                continue
            v = float(value)
            if boost:
                v = v + 0.1 if v > 0.5 else v - 0.1
            sums.setdefault(knob, []).append(max(0.0, min(1.0, v)))
    macros = {k: round(sum(v) / len(v), 2) for k, v in sums.items()}
    return {"words": picked, "macros": {k: macros[k] for k in FEEL_KNOBS if k in macros}, "look": look}


def _merge_feel(a: dict | None, b: dict | None) -> dict | None:
    if not a:
        return b
    if not b:
        return a
    macros = dict(a.get("macros") or {})
    for k, v in (b.get("macros") or {}).items():
        macros[k] = round((macros[k] + v) / 2, 2) if k in macros else v
    return {"words": list(a.get("words") or []) + list(b.get("words") or []),
            "macros": {k: macros[k] for k in FEEL_KNOBS if k in macros}, "look": a.get("look") or b.get("look") or ""}


# ------------------------------------------------------------------------------------------------ words


def _normalise(line: str) -> str:
    text = str(line or "").lower().replace("_", " ")
    text = re.sub(r"[’']", "", text)  # "girl's" -> "girls"
    text = re.sub(r"[^a-z0-9,;/.!?&\- ]+", " ", text)
    text = text.replace("&", " and ")
    for wrong, right in sorted(SPELL.items(), key=lambda kv: -len(kv[0])):
        if " " in wrong or "-" in wrong:
            text = text.replace(wrong, right)
    words = []
    for w in re.split(r"(\s+|[,;/.!?])", text):
        if not w or w.isspace():
            words.append(w)
            continue
        if w in ",;/.!?":
            words.append(w)
            continue
        words.append(SPELL.get(w, w) if "-" not in w else w)
    return re.sub(r"\s+", " ", "".join(words)).strip()


def singular(word: str) -> str:
    """"lanterns" -> "lantern", "butterflies" -> "butterfly", "glasses" -> "glass"; a word that is not plural stays."""
    w = str(word or "").lower()
    if len(w) <= 3 or w.endswith(("ss", "us", "is", "ous")):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("ches", "shes", "xes", "sses", "zes")):
        return w[:-2]
    if w.endswith("ses") and not w.endswith("ases"):
        return w[:-1]
    if w.endswith("s"):
        return w[:-1]
    return w


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-]*", str(text or "").lower())


def split_feel(line: str) -> tuple[str, str]:
    """``line`` as typed, split into the rest and its feel groups: "a moth, a lantern, moody and punchy" ->
    ("a moth, a lantern", "moody and punchy"). The variations put another feel clause in its place."""
    groups = [g.strip() for g in re.split(r"[,;/.!?]+", str(line or "")) if g.strip()]
    feel = [g for g in groups if feel_of(_words(_normalise(g)))]
    return ", ".join(g for g in groups if g not in feel), ", ".join(feel)


def _chunks(group: str) -> list[list[str]]:
    """A comma group split at the prepositions that introduce a place, each chunk its words (the preposition kept
    in front): "girl dancing to rave music in a cyberpunk city outside warehouse" -> four chunks."""
    words = _words(group)
    out: list[list[str]] = []
    cur: list[str] = []
    for w in words:
        if w in PREPOSITIONS and cur:
            out.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        out.append(cur)
    return out


def _catalogue() -> tuple[dict[str, str], dict[str, str]]:
    """``(nouns, labels)``: catalogue noun -> family, family label word set -> family (``stills.subjects``)."""
    from xenoform import stills

    nouns: dict[str, str] = {}
    labels: dict[str, str] = {}
    for fam, row in (stills.subjects().get("families") or {}).items():
        for noun in row.get("nouns") or []:
            nouns[str(noun).strip().lower()] = fam
        label = " ".join(_words(str(row.get("label") or ""))).strip()
        if label:
            labels[label] = fam
        labels[fam.replace("-", " ")] = fam
    return nouns, labels


def _find_nouns(text: str, nouns: dict[str, str]) -> list[str]:
    """The catalogue nouns ``text`` names, longest first, each word used once ("a paper lantern" is the paper lantern,
    not the lantern too); plurals match their singular."""
    words = _words(text)
    sing = [singular(w) for w in words]
    taken = [False] * len(words)
    found: list[str] = []
    for noun in sorted(nouns, key=lambda n: -len(n.split())):
        parts = noun.split()
        n = len(parts)
        for i in range(0, len(words) - n + 1):
            if any(taken[i:i + n]):
                continue
            if all(words[i + k] == parts[k] or sing[i + k] == parts[k] for k in range(n)):
                for k in range(n):
                    taken[i + k] = True
                if noun not in found:
                    found.append(noun)
    return found


def _family_label(text: str, labels: dict[str, str]) -> str:
    low = " ".join(_words(text))
    for label, fam in sorted(labels.items(), key=lambda kv: -len(kv[0])):
        if label and re.search(r"\b" + re.escape(label) + r"\b", low):
            return fam
        # "sea creatures" names the family by its label's content words; "instruments" by one of them
        parts = [p for p in label.split() if p not in STOP and len(p) > 3]
        if parts and all(re.search(r"\b" + re.escape(p) + r"s?\b", low) for p in parts):
            return fam
    return ""


# ------------------------------------------------------------------------------------------------ the reading


def _article(phrase: list[str]) -> list[str]:
    """"warehouse" -> "a warehouse"; a phrase that opens on a determiner, a plural or a modifier-only tail stays."""
    if not phrase:
        return phrase
    if phrase[0] in {"a", "an", "the", "some", "this", "that", "my", "our", "your", "no", "every"} or phrase[0].isdigit():
        return phrase
    last = phrase[-1]
    if last in NO_ARTICLE or (last.endswith("s") and singular(last) != last):
        return phrase
    return (["an"] if phrase[0][0] in "aeiou" else ["a"]) + phrase


def _scene_phrase(chunks: list[list[str]], first: bool) -> list[str]:
    """One place chunk as words: its preposition kept unless it opens the subject, an article added, the person,
    performance and music words out ("in a cyberpunk city" -> "a cyberpunk city")."""
    out: list[str] = []
    for chunk in chunks:
        prep = chunk[0] if chunk[0] in PREPOSITIONS else ""
        body = [w for w in (chunk[1:] if prep else chunk)
                if w not in PEOPLE and w not in PERSON_VERBS and w not in PERFORM_VERBS and w not in MUSIC
                and w not in LIGHT_OBJECTS and not any(w in v for v in PERFORMANCES.values())]
        while body and body[0] in CONNECTORS:
            body = body[1:]
        while body and body[-1] in CONNECTORS:
            body = body[:-1]
        if not body:
            continue
        body = _article(body)
        if out or not first:
            out += ([prep] if prep else []) + body
        else:
            out += body
        first = False
    return out


def _theme_of(group_words: list[str]) -> str:
    """The theme a comma group names (``THEMES``): its last content word, a trailing "theme" or "vibe" dropped, is one
    of a theme's words. "" for a group that names a thing ("a rally car" ends on the car)."""
    content = [w for w in group_words if w not in STOP]
    while content and content[-1] in THEME_TAIL:
        content.pop()
    return THEME_OF.get(content[-1], "") if content else ""


def read(line: str, vibe: str = "", *, llm: bool | None = None) -> dict:
    """The reading of ``line`` for ``vibe``: ``scenes`` (subjects to grow as wide frames), ``objects`` (catalogue
    nouns), ``own`` (typed shapes the catalogue lacks), ``family`` (the family the line names, if any), ``performer``
    (``{"style", "cue"}`` or None), ``summary`` (one line for the desk), ``source`` ("rules" or "llm"). ``llm`` None
    asks the model only when ``XENO_LLM_URL`` is set; True forces a try, False never asks."""
    text = _normalise(line)
    if not text:
        return dict(EMPTY)
    nouns, labels = _catalogue()
    groups = [g.strip() for g in re.split(r"[,;/.!?]+", text) if g.strip()]
    scenes: list[str] = []
    details: list[str] = []
    own: list[str] = []
    objects: list[str] = []
    themes: list[str] = []
    feel: dict | None = None
    kept: list[str] = []
    for group in groups:  # "slow and dreamy" is how the cut should feel, not a thing or a place
        group_feel = feel_of(_words(group))
        if group_feel:
            feel = _merge_feel(feel, group_feel)
        else:
            kept.append(group)
    if feel:
        groups = kept
        text = ", ".join(kept)
    all_words = _words(text)
    for group in groups:
        chunks = _chunks(group)
        group_words = _words(group)
        found = _find_nouns(group, nouns)
        for noun in found:
            if noun not in objects:
                objects.append(noun)
        named_family = _family_label(group, labels)  # "sea creatures" names a family, not the sea
        music_chunks = [c for c in chunks if any(w in MUSIC for w in c)]  # "to rave music" is the song, not a place
        place_chunks = [c for c in chunks if c not in music_chunks and any(w in PLACES for w in c)]
        sky_chunks = [c for c in chunks if c not in place_chunks and c not in music_chunks and any(w in SKIES for w in c)]
        if not named_family and (place_chunks or (sky_chunks and not found)):
            # a place with its light: "in a cyberpunk city outside warehouse" + "in the rain" -> "a cyberpunk city outside
            # a warehouse in the rain"; sky chunks alone ("under a red moon") are a scene too when nothing else is named.
            # The places lead when every sky chunk brings its preposition; "cold-blue dusk over a flooded car park" keeps
            # the line's order
            if sky_chunks and all(c[0] in PREPOSITIONS for c in sky_chunks):
                words_ = _scene_phrase(place_chunks, True) + _scene_phrase(sky_chunks, not place_chunks)
            else:
                words_ = _scene_phrase([c for c in chunks if c in place_chunks or c in sky_chunks], True)
            subject = " ".join(words_).strip()
            if subject and subject not in scenes and len(scenes) < MAX_SCENES:
                scenes.append(_clip(subject))
            for chunk in chunks:  # "car rally racing in a desert at dusk": the place is a scene, the racing a theme
                theme = _theme_of(chunk) if chunk not in place_chunks and chunk not in sky_chunks and chunk not in music_chunks else ""
                if theme and theme not in themes:
                    themes.append(theme)
            continue
        lights = [LIGHT_OBJECTS[w] for w in group_words if w in LIGHT_OBJECTS]
        if lights:
            for shape in lights:
                if shape not in own and shape not in objects and nouns.get(shape) is None:
                    own.append(shape)
                elif nouns.get(shape) is not None and shape not in objects:
                    objects.append(shape)
            details += [w for w in group_words if w in LIGHT_OBJECTS and w not in details]
            continue
        if found or named_family:
            continue
        theme = _theme_of(group_words)
        if theme:  # "car rally racing": the theme's things, below, not one shape called "car rally racing"
            if theme not in themes:
                themes.append(theme)
            continue
        content = [w for w in group_words if w not in STOP and w not in PEOPLE and w not in PERSON_VERBS
                   and w not in PERFORM_VERBS and w not in MUSIC and w not in PARTY and w not in SKIES
                   and not any(w in v for v in PERFORMANCES.values())]
        if content and len(content) <= 3 and len(chunks) == 1 and not any(w in MODIFIERS for w in content[-1:]) \
                and content[-1] not in INSTRUMENT_NOUNS:
            # a short comma item that names a thing the catalogue lacks: "a chrome hoverboard", "wolf skull"
            shape = " ".join(content[:-1] + [singular(content[-1])]).strip()
            if shape and shape not in own and len(own) < MAX_OWN:
                own.append(shape)
    # a theme's things after the ones typed: the catalogue's own join the objects, the rest are grown as shapes
    theme_things: list[str] = []
    for theme in themes:
        for thing in THEMES[theme]["things"]:
            if len(theme_things) >= THEME_THINGS:
                break
            if nouns.get(thing) is not None:
                if thing not in objects:
                    objects.append(thing)
                    theme_things.append(thing)
            elif thing not in own and len(own) < MAX_OWN:
                own.append(thing)
                theme_things.append(thing)
    # the lights of a later group belong to the first scene: "..., lasers" -> "a cyberpunk city ..., lasers"
    for w in all_words:
        if w in LIGHT_OBJECTS and w not in details and not any(w in s.split() for s in scenes):
            details.append(w)
    if scenes and details:
        extra = [d for d in details if d not in scenes[0].split()]
        if extra:
            scenes[0] = _clip(scenes[0] + " with " + " and ".join(extra))
    family = (nouns.get(objects[0]) if objects else "") or _family_label(text, labels)
    if not family:
        # the pick's own lookup ("a chess game played by machines" -> the chess knight's family), so the desk says what
        # the pick will do; the song, the party and the performance are not objects ("rave music" once named the music
        # box's family, "playing keys" the skeleton key's)
        from xenoform import stills

        family = stills.family_named(vibe, stills.content_words(family_words(all_words)))
    performer = _performer(all_words)
    reading = {"line": str(line or "").strip(), "scenes": scenes, "objects": objects[:MAX_OBJECTS], "own": own[:MAX_OWN],
               "family": family or "", "performer": performer, "feel": feel, "source": "rules",
               "theme": themes[0] if themes else "", "theme_things": theme_things}
    ask = bool(os.environ.get("XENO_LLM_URL", "").strip()) if llm is None else bool(llm)
    if ask:
        reading = refine(reading, text if feel else line, vibe)  # the feel words are not things for the model to grow
    reading["summary"] = summary(reading)
    return reading


def family_words(words: list[str]) -> list[str]:
    """The words of a line that may name an object family: the song, the party, the people and what they play out."""
    return [w for w in words if w not in MUSIC and w not in PARTY and w not in PEOPLE and w not in PERSON_VERBS
            and w not in PERFORM_VERBS and not any(w in v for v in PERFORMANCES.values())]


def _performer(words: list[str]) -> dict | None:
    """Polly's cue: a performance word names the style; a person with none is the auto mix (a rave or club around
    her makes it dance); a bare instrument with no person is an object, not a performer."""
    person = any(w in PEOPLE for w in words) or any(w in PERSON_VERBS for w in words) or any(w in PERFORM_VERBS for w in words)
    style = ""
    cue = ""
    for name, forms in PERFORMANCES.items():
        hit = next((w for w in words if w in forms), "")
        if not hit:
            continue
        if hit in INSTRUMENT_NOUNS and not person:
            continue  # "a grand piano", "drums on a rooftop": things, not Polly
        if not style:
            style, cue = name, hit
    if not style and not person:
        return None
    if not style and any(w in PARTY for w in words):
        style, cue = "dance", next(w for w in words if w in PARTY)
    who = next((w for w in words if w in PEOPLE), "")
    parts = [who] if who else []
    if cue and cue != who:
        parts.append(cue)
    return {"style": style or "auto", "cue": " ".join(parts) or "performer"}


PERFORMER_WORDS = {"dance": "dancing", "sing": "singing", "drums": "drumming", "keys": "on keys", "guitar": "on guitar",
                   "auto": "performing"}


def summary(reading: dict) -> str:
    """One line for the desk: "Scenes: a cyberpunk city outside a warehouse, lasers. Objects: laser (new shape).
    Polly: dancing." Empty when the line gives the cut nothing it can use."""
    bits = []
    if reading.get("scenes"):
        bits.append("Scenes: " + "; ".join(reading["scenes"]) + ".")
    things = list(reading.get("objects") or [])
    own = [f"{o} (new shape)" for o in (reading.get("own") or [])]
    if not things and reading.get("family"):
        things = [reading["family"].replace("-", " ") + " (the family)"]
    if things or own:
        bits.append("Objects: " + ", ".join(things + own) + (f" (the {reading['theme']} theme)" if reading.get("theme") else "") + ".")
    perf = reading.get("performer")
    if perf:  # read, but she renders only when switched on in Work in progress
        bits.append("Polly: " + PERFORMER_WORDS.get(str(perf.get("style") or "auto"), "performing") + " (in Work in progress).")
    feel = reading.get("feel")
    if feel:
        knobs = [f"{k.capitalize()} {round(float(v) * 100)}" for k, v in (feel.get("macros") or {}).items()]
        if feel.get("look"):
            knobs.append("Look " + str(feel["look"]).replace("-", " "))
        bits.append("Feel: " + ", ".join(feel.get("words") or []) + (f" ({', '.join(knobs)})" if knobs else "") + ".")
    return " ".join(bits)


# ------------------------------------------------------------------------------------------------ the model


LLM_SYSTEM = ("You read one line a user typed for a music video made of still pictures morphing into one another. "
              "Answer with JSON only: {\"scenes\": [..], \"objects\": [..], \"performer\": {\"style\": ..} or null}. "
              "scenes: up to two wide places with their light, as short noun phrases, no people (\"a cyberpunk city street "
              "outside a warehouse, lasers\"). objects: up to six single concrete things named or implied, singular nouns, "
              "no people. performer: when the line has a person doing something, the style: one of sing, drums, keys, guitar, "
              "dance, or auto; else null.")


def refine(reading: dict, line: str, vibe: str = "") -> dict:
    """The rules reading refined by the local model (``xenoform.llm.chat``): its scenes replace the rules' when it gives
    any; its objects are kept where the catalogue knows them, else grown as shapes (short ones only); its performer
    wins when given. Any failure keeps the rules reading."""
    try:
        from xenoform import llm

        raw = llm.chat(LLM_SYSTEM, f"Line: {line}\nVibe: {vibe or 'any'}", schema={"type": "object"}, timeout=8.0)
        if not raw:
            return reading
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
        if not isinstance(data, dict):
            return reading
    except Exception as exc:  # the model is a refinement, never a dependency
        log.info("idea refine skipped: %s", exc)
        return reading
    out = dict(reading)
    scenes = [_clip(re.sub(r"\s+", " ", str(s)).strip().lower()) for s in (data.get("scenes") or []) if str(s).strip()]
    if scenes:
        out["scenes"] = scenes[:MAX_SCENES]
    nouns, _ = _catalogue()
    objects = list(out.get("objects") or [])
    own = list(out.get("own") or [])
    for item in data.get("objects") or []:
        noun = " ".join(_words(str(item)))
        noun = " ".join(noun.split()[:-1] + [singular(noun.split()[-1])]) if noun else ""
        if not noun:
            continue
        if noun in nouns:
            if noun not in objects:
                objects.append(noun)
        elif len(noun.split()) <= 3 and noun not in own and len(own) < MAX_OWN and not any(w in PEOPLE for w in noun.split()):
            own.append(noun)
    out["objects"], out["own"] = objects[:MAX_OBJECTS], own[:MAX_OWN]
    if objects:
        out["family"] = nouns.get(objects[0], out.get("family") or "")
    perf = data.get("performer")
    if isinstance(perf, dict) and str(perf.get("style") or ""):
        style = str(perf.get("style")).strip().lower()
        out["performer"] = {"style": style if style in PERFORMANCES or style == "auto" else "auto", "cue": "the model"}
    elif perf is None and "performer" in data:
        out["performer"] = None
    out["source"] = "llm"
    return out


# ------------------------------------------------------------------------------------------------ the make


def reading_for(state: dict | None) -> dict:
    """The reading a make body carries (``idea_reading``, set by ``shape_state``), else the rules reading of its
    ``idea`` line (no model: the pick is called on every keystroke of the Chain row), else the empty reading."""
    state = state or {}
    got = state.get("idea_reading")
    if isinstance(got, dict) and "scenes" in got:
        return got
    line = str(state.get("idea") or "").strip()
    if not line:
        return dict(EMPTY)
    return read(line, str(state.get("vibe") or ""), llm=False)


def applies(state: dict | None) -> bool:
    """The line shapes a Simple cut (the make body's ``mode`` "simple", or none: the CLI and the MCP tools); a Director
    render carries the Simple desk's line without having been typed for it."""
    return str((state or {}).get("mode") or "simple") == "simple"


def shape_state(state: dict, reading: dict | None = None) -> dict:
    """A copy of ``state`` with the line's choices in it: Scenes to Mix when the line gave a scene and the user left
    it Off (Only stays Only; an Off picked by hand, ``scenes_chosen``, stays Off); the cued style for Polly when she is
    on and her style is Auto (the line never switches her on: she is in Work in progress); ``idea_reading`` for the
    record and the pick. A state that is not a Simple cut or has no line comes back as it was."""
    state = dict(state or {})
    if not applies(state) or not str(state.get("idea") or "").strip():
        return state
    reading = reading if reading is not None else reading_for(state)
    state["idea_reading"] = reading
    from xenoform import dense as _dense
    from xenoform import morph_pass as _mp

    if reading.get("scenes") and _mp.scenes_choice(state) == "off" and not state.get("scenes_chosen"):
        state["scene_stills"] = "mix"
        state.pop("scenes", None) if isinstance(state.get("scenes"), str) else None
    feel = reading.get("feel")
    if feel:  # the desk moves its knobs itself and sends them; a call with no knobs (MCP, the CLI) takes the line's
        if not isinstance(state.get("macros"), dict) and feel.get("macros"):
            state["macros"] = dict(feel["macros"])
        if feel.get("look") and str(state.get("dance_fx") or "auto") == "auto":
            state["dance_fx"] = feel["look"]
    perf = reading.get("performer")
    # Polly is in the desk's Work in progress (docs/MORPH_ENGINE_PLAN.md §3): the line no longer switches her on, but
    # when she is on, the performance it cues ("girl dancing") still sets her style over Auto
    if perf and _dense.performer_choice(state) > 0:
        style = str(perf.get("style") or "auto")
        if style != "auto" and _dense.performer_style(state) == "auto":
            state["performer_style"] = style
    return state


def grow_plan(reading: dict, vibe: str) -> dict:
    """What a Make grows for the line before the cut, under the pool vibe ``vibe``: the typed scene subjects the vibe
    has not rendered (``SCENES_PER_SUBJECT`` renders each, ``SCENES_MAX`` in all), the typed shapes (own) and the
    named catalogue nouns the pool lacks (``SHAPES_MAX`` in all). ``seconds`` is the estimate."""
    from xenoform import stills

    scenes: list[str] = []
    shapes_own: list[str] = []
    shapes_nouns: list[str] = []
    if vibe and reading:
        have_scenes = stills.scene_nouns_in(vibe)
        have_nouns = stills.nouns_in(vibe)
        for subject in reading.get("scenes") or []:
            clean = stills.clean_noun(subject, stills.SCENE_NOUN_LIMIT)
            if clean and clean not in have_scenes and clean not in scenes:
                scenes.append(clean)
        for shape in reading.get("own") or []:
            clean = stills.clean_noun(shape)
            if clean and clean not in have_nouns and clean not in shapes_own:
                shapes_own.append(clean)
        for noun in reading.get("objects") or []:
            clean = stills.clean_noun(noun)
            if clean and clean not in have_nouns and clean not in shapes_nouns:
                shapes_nouns.append(clean)
    per = SCENES_PER_SUBJECT if len(scenes) <= 1 else max(1, SCENES_MAX // len(scenes))
    scene_prompts = [s for s in scenes for _ in range(per)][:SCENES_MAX]
    shapes_own = shapes_own[:SHAPES_MAX]
    shapes_nouns = shapes_nouns[:max(0, SHAPES_MAX - len(shapes_own))]
    count = len(scene_prompts) + len(shapes_own) + len(shapes_nouns)
    return {"scenes": scene_prompts, "own": shapes_own, "nouns": shapes_nouns, "count": count,
            "seconds": int(stills.estimate_seconds(count)) if count else 0}
