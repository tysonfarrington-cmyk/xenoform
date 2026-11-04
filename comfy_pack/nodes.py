"""Xenoform's nodes for ComfyUI: the song, the storyboard on the beat, the Morph Timeline, the morph pairs, the cut.

Each node is a thin wrapper over a pure function (``song.analyze``, ``storyboard.build``, ``storyboard.apply_edits``,
``storyboard.pair``, ``assemble.assemble``) so the tests run them without ComfyUI. The pairs plug into ComfyUI's own LTX
nodes (``LTXVPreprocess``, ``LTXVAddGuide``, ``LTXVConditioning``, ``EmptyLTXVLatentVideo``, ``LTXVScheduler``,
``RandomNoise``, ``CFGGuider``): nothing here samples, the stock graph does.

Two types of the pack's own travel between them: ``XENOFORM_SONG`` (the song's features, its file, its drop) and
``XENOFORM_STORYBOARD`` (the shots, the chain, the knobs; a plain dict, see ``storyboard.py``).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import assemble as A
from . import looks
from . import song as S
from . import stills
from . import storyboard as SB

CATEGORY = "Xenoform"
SONG = "XENOFORM_SONG"
STORYBOARD = "XENOFORM_STORYBOARD"
PACK = Path(__file__).resolve().parent
DEMO_SONG = "demo.wav"
MAX_MORPHS = 16  # the Assemble's morph inputs; the editor shows them one at a time as they are connected


def _folder_paths():
    try:
        import folder_paths  # ComfyUI's own module: there only when ComfyUI loaded the pack

        return folder_paths
    except Exception:
        return None


def _input_dir() -> Path | None:
    fp = _folder_paths()
    try:
        return Path(fp.get_input_directory()) if fp else None
    except Exception:
        return None


def _out_dir() -> Path:
    fp = _folder_paths()
    try:
        if fp:
            return Path(fp.get_output_directory())
    except Exception:
        pass
    return Path(os.environ.get("XENO_PACK_OUT") or (Path.cwd() / "output"))


def _temp_dir() -> Path:
    fp = _folder_paths()
    try:
        if fp:
            return Path(fp.get_temp_directory())
    except Exception:
        pass
    return Path(os.environ.get("XENO_PACK_TEMP") or (Path.cwd() / "temp"))


def bundled_songs() -> dict[str, Path]:
    """The songs the pack can open by name: the demo (the pack's own copy, else the repository's) and, in the whole
    repository, the six bundled songs under ``examples/songs``."""
    out: dict[str, Path] = {}
    for demo in (PACK / "examples" / DEMO_SONG, PACK.parent / "examples" / DEMO_SONG):
        if demo.is_file():
            out[DEMO_SONG] = demo
            break
    songs = PACK.parent / "examples" / "songs"
    if songs.is_dir():
        for p in sorted(songs.iterdir()):
            if p.suffix.lower() in S.AUDIO_EXTS:
                out[f"songs/{p.name}"] = p
    return out


def song_choices() -> list[str]:
    names = list(bundled_songs())
    base = _input_dir()
    if base and base.is_dir():  # the top of the input folder, as LoadAudio lists it
        for p in sorted(base.iterdir()):
            if p.is_file() and p.suffix.lower() in S.AUDIO_EXTS and p.name not in names:
                names.append(p.name)
    return names or [DEMO_SONG]


def resolve_song(name: str) -> Path:
    """A song by its name in the list: a bundled one, else a file in ComfyUI's input folder, else a path as given."""
    name = str(name or "").strip()
    found = bundled_songs().get(name)
    if found:
        return found
    base = _input_dir()
    if base:
        candidate = (base / name).resolve()
        if candidate.is_file() and candidate.is_relative_to(base.resolve()):
            return candidate
    path = Path(name).expanduser()
    if path.is_file():
        return path
    raise S.SongError(f"There is no song called {name!r} here: put it in ComfyUI's input folder, or pick the bundled demo.")


def _text_ui(text: str, **extra) -> dict:
    return {"text": [text], **extra}


# ------------------------------------------------------------------------------------------------ Song analysis


class XenoformSongAnalysis:
    """A song's beats, sections, drops and energy: the desk's analysis, here."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "song": (song_choices(), {"default": DEMO_SONG, "tooltip": "A bundled song, or any audio file in ComfyUI's input folder."}),
                "fps": ("INT", {"default": int(S.FPS), "min": 4, "max": 60, "tooltip": "The analysis rate. The desk analyses at 12; beats keep a 24 fps clock of their own."}),
                "engine": (list(S.ENGINES), {"default": "auto", "tooltip": "auto: librosa when this Python has it (the desk's own), else the same steps in numpy."}),
            },
            "optional": {
                "audio": ("AUDIO", {"tooltip": "A LoadAudio output instead of the list: written to a temporary WAV for the cut."}),
                "features_json": ("STRING", {"default": "", "tooltip": "A features.json the desk exported: read instead of analysing."}),
            },
        }

    RETURN_TYPES = (SONG, "STRING", "FLOAT", "FLOAT")
    RETURN_NAMES = ("song", "summary", "tempo", "duration")
    FUNCTION = "analyse"
    CATEGORY = CATEGORY
    DESCRIPTION = "Reads a song the way the Xenoform desk does: beats, sections (calm, build, drop, release, sustain), the main drop and the energy."

    @classmethod
    def IS_CHANGED(cls, song, fps, engine, audio=None, features_json=""):
        parts = [str(fps), str(engine), str(features_json)]
        try:
            parts.append(S.file_key(resolve_song(song)))
        except Exception:
            parts.append(str(song))
        if features_json and Path(features_json).is_file():
            parts.append(S.file_key(features_json))
        return "|".join(parts)

    def analyse(self, song, fps=int(S.FPS), engine="auto", audio=None, features_json=""):
        name = str(song)
        if features_json:
            feats = S.read_features(Path(str(features_json)).expanduser())
            path = resolve_song(song) if audio is None else None
            used = "features.json"
        else:
            feats, path, used = None, None, ""
        if audio is not None:
            y, sr = S.from_comfy_audio(audio)
            path = S.write_wav(_temp_dir() / "xenoform" / f"song_{int(time.time() * 1000)}.wav", y, sr)
            name = "AUDIO input"
            if feats is None:
                feats = S.analyze(y, sr, fps=float(fps), engine=engine)
                used = feats["engine"]
        elif feats is None:
            path = resolve_song(song)
            y, sr = S.load_audio(path)
            feats = S.analyze(y, sr, fps=float(fps), engine=engine)
            used = feats["engine"]
        value = S.song_value(feats, path=path, name=name if audio is not None else Path(name).name, engine=used)
        text = S.describe(value)
        f = value["features"]
        return {"ui": _text_ui(text), "result": (value, text, float(f.get("tempo") or 0.0), float(f.get("duration") or 0.0))}


# ------------------------------------------------------------------------------------------------ Storyboard


class XenoformStoryboard:
    """Shots on the beat with the chain of objects: what a Make on the desk would plan for this song and these knobs."""

    @classmethod
    def INPUT_TYPES(cls):
        vibes = stills.vibe_ids()
        return {
            "required": {
                "song": (SONG,),
                "vibe": (vibes, {"default": stills.BUNDLED_VIBE if stills.BUNDLED_VIBE in vibes else vibes[0],
                                 "tooltip": "The look: its stills, its prompt words and its LTX tuning."}),
                "idea": ("STRING", {"default": "", "multiline": False, "tooltip": "A line of words: an object it names opens the chain."}),
                "energy": (list(SB.ENERGIES), {"default": "dense", "tooltip": "dense: a shot a bar, a half bar after the drop. flow: about one shot every 5 s."}),
                "forms": ("INT", {"default": 0, "min": 0, "max": 40, "tooltip": "How many morphs. 0 is Auto (from the song's length and tempo)."}),
                "speed": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Auto's count, x0.6 at 0 to x1.4 at 1."}),
                "chaos": ("FLOAT", {"default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Calm drops the stutters and holds; wild doubles them, and from 0.6 the builds fold and the drop's shots spin."}),
                "intensity": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How hard the punches land (0.5 is four fifths)."}),
                "morph_style": (["auto"] + list(looks.STYLES), {"default": "auto", "tooltip": looks.STYLE_NOTES["auto"]}),
                "morph_timing": (list(looks.TIMINGS), {"default": "smooth", "tooltip": "When the change happens inside a shot: even, on every beat, or a snap on the downbeat."}),
                "pace": (["viscous", "tight"], {"default": "viscous", "tooltip": "A whole song only: two bars a shot (viscous) or a bar on the builds (tight)."}),
                "aspect": (list(SB.ASPECTS), {"default": "16:9", "tooltip": "16:9 renders 512x288; 9:16 renders 320x576 from stills re-laid whole."}),
                "seed": ("INT", {"default": 2727, "min": 0, "max": 2 ** 31 - 1, "control_after_generate": False,
                                 "tooltip": "Morph i renders with seed + i. It stays as set (a plan is repeatable)."}),
            },
            "optional": {
                "images_folder": ("STRING", {"default": "", "tooltip": "A folder of your own images: they lead the chain."}),
            },
        }

    RETURN_TYPES = (STORYBOARD, "STRING", "INT")
    RETURN_NAMES = ("storyboard", "summary", "morphs")
    FUNCTION = "plan"
    CATEGORY = CATEGORY
    DESCRIPTION = "Plans the cut on the song's beats the way the Xenoform desk does: shots, the chain of objects, each morph's style and timing."

    def plan(self, song, vibe, idea, energy, forms, speed, chaos, intensity, morph_style, morph_timing, pace, aspect, seed,
             images_folder=""):
        board = SB.build(song, vibe=vibe, idea=idea, energy=energy, forms=forms, speed=speed, chaos=chaos, intensity=intensity,
                         morph_style=morph_style, morph_timing=morph_timing, pace=pace, aspect=aspect, seed=seed,
                         user_folder=images_folder)
        text = SB.summary(board)
        return {"ui": _text_ui(text), "result": (board, text, len(board["shots"]))}


# ------------------------------------------------------------------------------------------------ Morph Timeline


class XenoformMorphTimeline:
    """The song strip, full screen: sections, beats, drops, the shots as blocks on the beat, the object pins and the
    intensity lane. The edits are saved in the workflow (the hidden ``timeline`` widget) and laid over the plan."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard": (STORYBOARD,),
                "timeline": ("STRING", {"default": "", "multiline": True, "tooltip": "The edits, written by the editor (Open the Morph Timeline)."}),
            },
        }

    RETURN_TYPES = (STORYBOARD, "STRING")
    RETURN_NAMES = ("storyboard", "summary")
    FUNCTION = "edit"
    CATEGORY = CATEGORY
    OUTPUT_NODE = True  # so "Queue selected output nodes" plans the strip without rendering a morph
    DESCRIPTION = "Edit the cut on the song: move or split a shot on the beats, pin an object to a beat, set a shot's style and timing, draw the intensity."

    def edit(self, storyboard, timeline=""):
        edits = SB.parse_edits(timeline)
        board = SB.apply_edits(storyboard, edits)
        text = SB.summary(board)
        view = {"board": board, "plan_cuts": list((storyboard.get("plan") or {}).get("cuts") or []),
                "edits": edits or SB.empty_edits(storyboard), "styles": list(looks.STYLES),
                "style_labels": looks.STYLE_LABELS, "timings": list(looks.TIMINGS), "timing_labels": looks.TIMING_LABELS}
        return {"ui": _text_ui(text, xenoform_board=[json.dumps(view)]), "result": (board, text)}


# ------------------------------------------------------------------------------------------------ Morph Pair


class XenoformMorphPair:
    """One morph's request: the two guide stills and every value the desk sends LTX 0.9.5 for it."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard": (STORYBOARD,),
                "index": ("INT", {"default": 0, "min": 0, "max": 239, "tooltip": "Which morph: 0 is the first shot's."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "STRING", "FLOAT", "INT", "INT", "INT", "INT", "INT", "FLOAT", "INT", "INT", "FLOAT", "INT", "STRING")
    RETURN_NAMES = ("image_a", "image_b", "prompt", "negative", "frame_rate", "width", "height", "length", "steps", "seed", "cfg",
                    "compression_a", "compression_b", "guide_strength_b", "frames", "request")
    OUTPUT_TOOLTIPS = ("Guide A: LTXVPreprocess, then LTXVAddGuide at frame 0.", "Guide B: LTXVPreprocess, then LTXVAddGuide at frame -1.",
                       "CLIPTextEncode (positive).", "CLIPTextEncode (negative).", "LTXVConditioning frame_rate.",
                       "EmptyLTXVLatentVideo width.", "EmptyLTXVLatentVideo height.", "EmptyLTXVLatentVideo length (8k + 1 frames).",
                       "LTXVScheduler steps.", "RandomNoise noise_seed.", "CFGGuider cfg.", "LTXVPreprocess img_compression for A.",
                       "LTXVPreprocess img_compression for B.", "LTXVAddGuide strength for B.",
                       "The shot's slot on the beat grid, in frames (the Assemble fits the morph to it).", "The whole request as JSON.")
    FUNCTION = "pair"
    CATEGORY = CATEGORY
    DESCRIPTION = "The two guide stills, the prompt, the negative, the length on the beat grid, the seed and the tuning for one morph, for ComfyUI's LTX nodes."

    def pair(self, storyboard, index):
        req = SB.pair(storyboard, int(index))
        aspect = str(storyboard.get("aspect") or "16:9")
        image_a = stills.to_image_tensor(stills.guide_image(req["image_a"], aspect))
        image_b = stills.to_image_tensor(stills.guide_image(req["image_b"], aspect))
        text = (f"Morph {req['index']}: {req['from']} into {req['to']} · {req['style']} · {req['length']} frames for a "
                f"{req['frames']}-frame slot · seed {req['seed']}")
        return {"ui": _text_ui(text), "result": (image_a, image_b, req["prompt"], req["negative"], req["frame_rate"], req["width"],
                                                 req["height"], req["length"], req["steps"], req["seed"], req["cfg"],
                                                 req["compression_a"], req["compression_b"], req["guide_strength_b"],
                                                 req["frames"], json.dumps(req, indent=1))}


# ------------------------------------------------------------------------------------------------ Assemble


class XenoformAssemble:
    """The rendered morphs cut to the beat with the song, into one mp4 in ComfyUI's output folder."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "storyboard": (STORYBOARD,),
                "fill": (list(A.FILLS), {"default": "stop", "tooltip": "A shot with no morph connected: stop the cut there, or crossfade its two stills."}),
                "punch": ("BOOLEAN", {"default": True, "tooltip": "The plan's punches (a zoom and a flash on the hits), scaled by each shot's intensity."}),
                "filename_prefix": ("STRING", {"default": "xenoform/cut"}),
            },
            "optional": {f"morph_{k}": ("IMAGE", {"tooltip": f"Morph {k - 1}'s frames (the VAE decode of its LTX render)."})
                         for k in range(1, MAX_MORPHS + 1)},
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("path",)
    FUNCTION = "cut"
    CATEGORY = CATEGORY
    OUTPUT_NODE = True
    DESCRIPTION = "Lays each morph in its slot on the beat (first frame on still A, last on still B) with the song, through ffmpeg."

    def cut(self, storyboard, fill="stop", punch=True, filename_prefix="xenoform/cut", **morphs):
        clips = {k - 1: morphs.get(f"morph_{k}") for k in range(1, MAX_MORPHS + 1) if morphs.get(f"morph_{k}") is not None}
        out_dir = _out_dir()
        prefix = str(filename_prefix or "xenoform/cut").replace("\\", "/").strip("/") or "xenoform/cut"
        sub, stem = (prefix.rsplit("/", 1) if "/" in prefix else ("", prefix))
        folder = out_dir / sub if sub else out_dir
        folder.mkdir(parents=True, exist_ok=True)
        n = 1 + max([int(p.stem.rsplit("_", 1)[-1]) for p in folder.glob(f"{stem}_*.mp4") if p.stem.rsplit("_", 1)[-1].isdigit()] or [0])
        path = folder / f"{stem}_{n:05d}.mp4"
        got = A.assemble(storyboard, clips, path, fill=fill, punch=bool(punch))
        text = (f"{got['shots']} of {got['of']} shots, {got['seconds']:.2f} s ({got['morphs']} morphs"
                + (f", {got['sketched']} sketched from stills" if got["sketched"] else "") + f") at {got['size'][0]}x{got['size'][1]}"
                + ("" if got["audio"] else ", no song file to mux") + f": {path.name}")
        ui = {"images": [{"filename": path.name, "subfolder": sub, "type": "output"}], "animated": (True,), "text": [text]}
        return {"ui": ui, "result": (str(path),)}


NODE_CLASS_MAPPINGS = {
    "XenoformSongAnalysis": XenoformSongAnalysis,
    "XenoformStoryboard": XenoformStoryboard,
    "XenoformMorphTimeline": XenoformMorphTimeline,
    "XenoformMorphPair": XenoformMorphPair,
    "XenoformAssemble": XenoformAssemble,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "XenoformSongAnalysis": "Xenoform Song Analysis",
    "XenoformStoryboard": "Xenoform Storyboard",
    "XenoformMorphTimeline": "Xenoform Morph Timeline",
    "XenoformMorphPair": "Xenoform Morph Pair",
    "XenoformAssemble": "Xenoform Assemble",
}
