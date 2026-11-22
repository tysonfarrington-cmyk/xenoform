"""First-run model check. Downloads are ungated Hugging Face files. No token.

A model counts when ComfyUI's own ``GET /models/<folder>`` lists its files, so
the legacy clip and unet folders and an ``extra_model_paths.yaml`` count too.
When ComfyUI does not answer, the desk looks in the models folder instead.

A quantised file counts. ``ltx-2.3-22b-distilled-fp8`` matches the LTX-2.3
slot, and ``z_image_turbo_int8_convrot`` matches Z-Image Turbo. The desk
remembers which file the user picked.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from xenoform.errors import PlainError
from xenoform.hardware import disk_free, detect_tier

# Sizes and the LTX 0.9.5 sha256 were read from the public Hugging Face file
# listings. Optional packs stay optional: the dry-run demo does not need them.
_LTX = "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.5.safetensors"
_T5 = "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors"
_LTX23 = "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled.safetensors"
# The four files the Final loads by name (final_tier.FILES), with the sizes and sha256 the Hugging Face file listings and
# the copies on Tys's machine agree on (checked 4 Nov 2026 with HEAD requests: nothing was downloaded to read them).
_LTX23_FP8 = "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-distilled-fp8.safetensors"
_GEMMA3 = "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors"
_LTX23_UPSCALER = "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
_ESRGAN = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
_Z = "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files"
_ACE = "https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files/resolve/main/checkpoints/ace_step_1.5_turbo_aio.safetensors"
_WAN = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main"

CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "ltx-095",
        "name": "LTX 0.9.5 fast",
        "short": "LTX 0.9.5",
        "required": True,
        "badge": "Morphs",
        "blurb": "Renders every Draft morph.",
        "detail": "Draft renders every morph with LTX 0.9.5, and Fast Final upscales that Draft. With the T5-XXL fp8 text encoder it is the required download. A dry run does not need the file. Cloud Final renders its morphs on Comfy Cloud (COMFY_ORG_API_KEY in the desk's environment) and falls back to this Draft model for a morph that fails there.",
        "files": (
            {
                "path": "checkpoints/ltx-video-2b-v0.9.5.safetensors",
                "url": _LTX,
                "bytes": 6340729500,
                "sha256": "720d15c9f19f7d0f6b2a92bbbc34410e2cfb2f6856a100b38f734fbf973d4adf",
            },
            {
                "path": "text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors",
                "url": _T5,
                "bytes": 5157348688,
                "sha256": "",
            },
        ),
    },
    {
        "id": "ltx-23",
        "name": "LTX-2.3 distilled",
        "required": False,
        "badge": "Final",
        "min_gb": 11,
        "blurb": "Renders the Final.",
        "detail": "Final renders each morph with the LTX-2.3 22B distilled fp8 file, the Gemma 3 12B text encoder and the x2 spatial upscaler, then upscales the frames 4x with Real-ESRGAN. It uses LTX-2.5 instead once that card's four files are installed. Draft and Fast Final do not load these files. Final loads the fp8 file on every card, so the 46 GB full weights are not part of this download.",
        "files": (
            # first for the slot logic (the family of the file the desk can pick between); not part of the download
            {
                "label": "LTX-2.3 22B distilled, full weights",
                "path": "checkpoints/ltx-2.3-22b-distilled.safetensors",
                "url": _LTX23,
                "bytes": 46149345038,
                "sha256": "14409a4d1337a8ded02fa87fb895b17a91ab2c6588f7cc3352e624ff18a689bf",
                "optional": True,
            },
            {
                "label": "LTX-2.3 22B distilled fp8",
                "path": "checkpoints/ltx-2.3-22b-distilled-fp8.safetensors",
                "url": _LTX23_FP8,
                "bytes": 29531884062,
                "sha256": "d9646b6f2d5c42d337b23671634c43bfeece6989644f51b4a3aa088465ccd3b2",
                "exact": True,
            },
            {
                "label": "Gemma 3 12B text encoder",
                "path": "text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
                "url": _GEMMA3,
                "bytes": 9447702218,
                "sha256": "aaca463d11e6d8d2a4bdb0d6299214c15ef78a3f73e0ef8113d5a9d0219b3f6d",
                "exact": True,
            },
            {
                "label": "x2 spatial upscaler",
                "path": "latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
                "url": _LTX23_UPSCALER,
                "bytes": 995743560,
                "sha256": "5f416311fa8172b65af67530758964708d29a317b830d689a51143b7f91913ed",
                "exact": True,
            },
            {
                "label": "Real-ESRGAN x4 upscaler",
                "path": "upscale_models/RealESRGAN_x4plus.pth",
                "url": _ESRGAN,
                "bytes": 67040989,
                "sha256": "",
                "exact": True,
            },
        ),
    },
    {
        "id": "ltx-25",
        "name": "LTX-2.5 distilled",
        "required": False,
        "badge": "Final",
        "manual": True,
        "min_gb": 11,
        "no_pick": True,
        "disk": True,  # the desk picks the Final's model by these files on disk (morph_pass.ltx25_present), so Setup looks there too
        "manual_note": "LTX-2.5 is a gated download, so Setup does not fetch it. Ask for access to Lightricks/LTX-2.5 on Hugging Face, then put the four files in the folders shown.",
        "blurb": "Renders the Final when all four files are here. Not downloaded by Setup.",
        "detail": "When these four files are installed the Final renders with LTX-2.5 (22B distilled int8, 576×1024 scaled to 1080×1920) instead of LTX-2.3. The weights are a gated Hugging Face repository (Lightricks/LTX-2.5): ask for access there, accept its licence, and put each file in the folder shown. Setup does not download them. Without them the Final uses LTX-2.3.",
        "files": (
            {"label": "LTX-2.5 22B distilled transformer (int8)", "path": "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors",
             "url": "", "bytes": 0, "approx_bytes": 21504034224, "sha256": "", "exact": True},
            {"label": "Gemma 4 12B text encoder (int8)", "path": "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors",
             "url": "", "bytes": 0, "approx_bytes": 15372969374, "sha256": "", "exact": True},
            {"label": "Video VAE", "path": "vae/ltx-2.5-video-vae-bf16.safetensors",
             "url": "", "bytes": 0, "approx_bytes": 1472223346, "sha256": "", "exact": True},
            {"label": "Audio VAE", "path": "vae/ltx-2.5-audio-vae-bf16.safetensors",
             "url": "", "bytes": 0, "approx_bytes": 364866540, "sha256": "", "exact": True},
        ),
    },
    {
        "id": "z-image",
        "name": "Z-Image Turbo",
        "required": False,
        "badge": "Stills",
        "blurb": "Makes new vibe stills.",
        "detail": "Stills model on the open-weights path. Diffusion weights, a text encoder, and the VAE. Local FLUX.2 Klein and FLUX.3 Klein can stand in.",
        "files": (
            {
                "path": "diffusion_models/z_image_turbo_bf16.safetensors",
                "url": f"{_Z}/diffusion_models/z_image_turbo_bf16.safetensors",
                "bytes": 12309866400,
                "sha256": "",
            },
            {
                "path": "text_encoders/qwen_3_4b_fp8_mixed.safetensors",
                "url": f"{_Z}/text_encoders/qwen_3_4b_fp8_mixed.safetensors",
                "bytes": 5631994051,
                "sha256": "",
            },
            {
                "path": "vae/ae.safetensors",
                "url": f"{_Z}/vae/ae.safetensors",
                "bytes": 335304388,
                "sha256": "",
            },
        ),
    },
    {
        "id": "flux2-klein",
        "name": "FLUX.2 Klein",
        "required": False,
        "badge": "Local",
        "manual": True,
        "blurb": "Optional local stills. You place the files.",
        "detail": "Optional local stills. Place flux-2-klein-4b-fp8.safetensors, qwen_3_4b.safetensors, and flux2-vae.safetensors. Setup does not download them.",
        "files": (
            {"path": "diffusion_models/flux-2-klein-4b-fp8.safetensors", "url": "", "bytes": 0, "sha256": ""},
            {"path": "text_encoders/qwen_3_4b.safetensors", "url": "", "bytes": 0, "sha256": ""},
            {"path": "vae/flux2-vae.safetensors", "url": "", "bytes": 0, "sha256": ""},
        ),
    },
    {
        "id": "flux3-klein",
        "name": "FLUX.3 Klein",
        "required": False,
        "badge": "Local",
        "manual": True,
        "blurb": "Optional local stills. You place the files.",
        "detail": "Optional local stills. Place flux3-image-klein-int8-convrot.safetensors, qwen3vl_4b_int8_convrot.safetensors, and flux2-vae.safetensors. The FLUX 3 API is an Add-on, off by default.",
        "files": (
            {"path": "diffusion_models/flux3-image-klein-int8-convrot.safetensors", "url": "", "bytes": 0, "sha256": ""},
            {"path": "text_encoders/qwen3vl_4b_int8_convrot.safetensors", "url": "", "bytes": 0, "sha256": ""},
            {"path": "vae/flux2-vae.safetensors", "url": "", "bytes": 0, "sha256": ""},
        ),
    },
    {
        "id": "ace-step",
        "name": "ACE-Step",
        "required": False,
        "blurb": "Optional music model.",
        "detail": "Optional music model, one all-in-one file. The bundled demo track does not need it.",
        "files": (
            {
                "path": "checkpoints/ace_step_1.5_turbo_aio.safetensors",
                "url": _ACE,
                "bytes": 10025478736,
                "sha256": "",
            },
        ),
    },
    {
        "id": "wan22-ti2v",
        "name": "Wan 2.2 TI2V 5B",
        "required": False,
        "badge": "Optional",
        "blurb": "Optional first-frame action shots.",
        "detail": "Optional alternative for first-frame action shots. About 18 GB with the VAE and text encoder. Only a recipe that asks for Wan loads it.",
        "files": (
            {
                "path": "diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
                "url": f"{_WAN}/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors",
                "bytes": 9999658848,
                "sha256": "456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e",
            },
            {
                "path": "vae/wan2.2_vae.safetensors",
                "url": f"{_WAN}/split_files/vae/wan2.2_vae.safetensors",
                "bytes": 1409400960,
                "sha256": "",
            },
            {
                "path": "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "url": f"{_WAN}/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
                "bytes": 6735906897,
                "sha256": "",
            },
        ),
    },
    {
        "id": "wan22-i2v",
        "name": "Wan 2.2 I2V 14B",
        "required": False,
        "badge": "Optional",
        "blurb": "Optional heavier image-to-video.",
        "detail": "Optional heavier image-to-video alternative. High-noise and low-noise 14B fp8. Only a recipe that asks for Wan loads it.",
        "files": (
            {
                "path": "diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                "url": f"{_WAN}/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                "bytes": 14294742832,
                "sha256": "",
            },
            {
                "path": "diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "url": f"{_WAN}/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                "bytes": 14294742832,
                "sha256": "",
            },
        ),
    },
)


def wan_ready(root: Path | None = None) -> bool:
    """True when the TI2V diffusion weights are on disk. The exact pack can still be partial."""
    root = root or models_root()
    path = root / "diffusion_models" / "wan2.2_ti2v_5B_fp16.safetensors"
    return path.is_file() and path.stat().st_size > 1_000_000


def size_label(nbytes: int) -> str:
    if nbytes >= 1_000_000_000:
        return f"{nbytes / 1_000_000_000:.1f} GB"
    if nbytes >= 1_000_000:
        return f"{nbytes / 1_000_000:.0f} MB"
    return f"{nbytes} B"


def _comfy_model_dirs() -> list[Path]:
    home = Path.home()
    return [
        home / "AI" / "ComfyUI" / "models",
        home / "ComfyUI" / "models",
        home / "ComfyUI_windows_portable" / "ComfyUI" / "models",
        home / "Desktop" / "ComfyUI_windows_portable" / "ComfyUI" / "models",
        home / "Documents" / "ComfyUI" / "models",  # ComfyUI Desktop's default
    ]


def models_root() -> Path:
    # cmd's `set XENO_MODELS=C:\...\models && python ...` keeps the space before &&, and
    # "models \checkpoints" is not a folder: every model read as missing on 29 Oct
    env = os.environ.get("XENO_MODELS", "").strip().strip('"').strip()
    if env:
        return Path(env)
    try:
        import folder_paths

        return Path(folder_paths.models_dir)
    except Exception:
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "models").is_dir() and (parent / "custom_nodes").is_dir():
            return parent / "models"
    for candidate in _comfy_model_dirs():
        if candidate.is_dir():
            return candidate
    from xenoform.ui import repo_root

    return repo_root() / "models"


def by_id(model_id: str) -> dict:
    for item in CATALOG:
        if item["id"] == model_id:
            return item
    raise PlainError("That model is not in the setup list.")


_QUANT_TOKEN = re.compile(
    r"(?i)(?:^|[-_])(?:fp8|fp16|bf16|fp32|fp4|int8|int4|q8_0|q6_k|q5_k|q4_k|q8|q6|q5|q4|nf4|gguf|scaled|mixed|convrot|e4m3fn|e5m2)(?=$|[-_])"
)
_MIN_VARIANT = 1_000_000


def quant_stripped(name: str) -> str:
    """Drop precision and quantiser tags so fp8 and int8 files share a family."""
    stem = Path(str(name or "")).stem
    previous = None
    while previous != stem:
        previous = stem
        stem = _QUANT_TOKEN.sub("", stem)
    return stem.strip("-_").lower()


def is_quantised(name: str) -> bool:
    return bool(_QUANT_TOKEN.search(Path(str(name or "")).stem))


def same_family(candidate: str, canonical: str) -> bool:
    """True when the names are the same file, or one is a quantised variant."""
    left = Path(str(candidate or "")).name.lower()
    right = Path(str(canonical or "")).name.lower()
    if left == right:
        return True
    family = quant_stripped(right)
    if len(family) < 6:
        return False
    return quant_stripped(left) == family


def _file_present(root: Path, file: dict) -> bool:
    path = root / file["path"]
    if not path.is_file():
        return False
    expected = int(file["bytes"])
    if expected <= 0:
        return path.stat().st_size > _MIN_VARIANT
    return path.stat().st_size == expected


_LISTED: dict[tuple[str, str], tuple[float, list[str] | None]] = {}
_LISTED_FOR = 5.0


def comfy_base(url: str = "") -> str:
    from xenoform.comfy_health import DEFAULT_COMFY

    base = str(url or os.environ.get("XENO_COMFY_URL") or DEFAULT_COMFY).strip().rstrip("/")
    return base or DEFAULT_COMFY


def _fetch_listing(base: str, folder: str) -> list[str] | None:
    try:
        request = Request(f"{base}/models/{folder}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=1.5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    return [str(item) for item in data]


def comfy_listing(folder: str, url: str = "") -> list[str] | None:
    """The files ComfyUI lists for one model folder, or None when it does not answer.

    Held a few seconds, so one Setup check asks once a folder, and a ComfyUI that
    is down costs one timeout, not one a slot."""
    base = comfy_base(url)
    key = (base, folder)
    now = time.monotonic()
    held = _LISTED.get(key)
    if held and now - held[0] < _LISTED_FOR:
        return held[1]
    names = _fetch_listing(base, folder)
    _LISTED[key] = (time.monotonic(), names)  # stamped when it came back, not when it was asked: a slow answer is not stale at birth
    return names


def prefetch_listings(url: str = "") -> None:
    """Ask ComfyUI for every model folder the catalog reads, all at once.

    A ComfyUI that does not answer costs one timeout for the whole check, not one for each folder in turn (on Windows a
    closed port takes the full 1.5 s: the nine folders were 25 s of a Setup page that said nothing meanwhile)."""
    from concurrent.futures import ThreadPoolExecutor

    def ask(folder: str) -> None:
        try:
            comfy_listing(folder, url)
        except Exception:  # noqa: BLE001 - the check below asks again and reads the answer it gets
            pass

    folders = sorted({Path(file["path"]).parent.as_posix() for spec in CATALOG for file in spec["files"]} | {"checkpoints"})
    with ThreadPoolExecutor(max_workers=min(8, len(folders))) as pool:
        list(pool.map(ask, folders))


def slot_variants(root: Path, file: dict, *, comfy_url: str = "") -> list[str]:
    """Relative paths that satisfy one catalog slot, canonical name first.

    ComfyUI's list for the folder decides when ComfyUI answers. The models folder
    on disk, with its size checks, is the fallback."""
    canonical = Path(file["path"]).name
    listed = comfy_listing(Path(file["path"]).parent.as_posix(), comfy_url)
    if listed is not None:
        # top level only: the shipped graphs load a bare file name, never one in a subfolder
        names = sorted(name for name in listed if "/" not in name and "\\" not in name and name.lower().endswith(".safetensors"))
        hits = [name for name in names if same_family(name, canonical)]
        hits.sort(key=lambda name: name.lower() != canonical.lower())
        return [(Path(file["path"]).parent / name).as_posix() for name in hits]
    folder = root / Path(file["path"]).parent
    found: list[str] = []
    if _file_present(root, file):
        found.append(file["path"].replace("\\", "/"))
    if not folder.is_dir():
        return found
    for path in sorted(folder.glob("*.safetensors")):
        if not same_family(path.name, canonical):
            continue
        if path.stat().st_size <= _MIN_VARIANT and path.name.lower() != canonical.lower():
            continue
        rel = str(Path(file["path"]).parent / path.name).replace("\\", "/")
        if rel not in found:
            found.append(rel)
    return found


def exact_variants(root: Path, file: dict, *, comfy_url: str = "", disk: bool = False) -> list[str]:
    """The slot's file when it is there under its own name, else nothing.

    The Final loads its four files by name, so a quantised cousin does not count for them. ComfyUI's list for the
    folder decides when ComfyUI answers; the models folder on disk is the fallback, and the only judge when ``disk``
    says the desk itself picks by those files."""
    if not disk:
        wanted = Path(file["path"]).name.lower()
        listed = comfy_listing(Path(file["path"]).parent.as_posix(), comfy_url)
        if listed is not None:
            return [file["path"]] if any(name.lower() == wanted for name in listed) else []
    return [file["path"]] if _file_present(root, file) else []


def _partial_bytes(root: Path, file: dict) -> int:
    """What an interrupted download of this file already holds (``download_file`` resumes from the .part)."""
    dest = root / file["path"]
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        return int(part.stat().st_size) if part.is_file() else 0
    except OSError:
        return 0


def model_parts(spec: dict, root: Path, *, comfy_url: str = "") -> list[tuple[dict, dict]]:
    """Every file the model needs, each with whether it is in place: ``(catalog file, row)``. A file marked
    ``optional`` is an alternative the card does not ask for."""
    out: list[tuple[dict, dict]] = []
    for file in spec["files"]:
        if file.get("optional"):
            continue
        if file.get("exact"):
            found = exact_variants(root, file, comfy_url=comfy_url, disk=bool(spec.get("disk")))
        else:
            found = slot_variants(root, file, comfy_url=comfy_url)
        size = int(file["bytes"]) or int(file.get("approx_bytes") or 0)
        out.append((file, {
            "label": file.get("label") or Path(file["path"]).name,
            "name": Path(file["path"]).name,
            "folder": Path(file["path"]).parent.as_posix(),
            "bytes": size,
            "size_label": size_label(size) if size else "",
            "present": bool(found),
        }))
    return out


def bytes_to_fetch(parts: list[tuple[dict, dict]], root: Path) -> int:
    """What a Download still has to fetch: the files not in place, less what a stopped download already holds."""
    total = 0
    for file, row in parts:
        if row["present"] or not file.get("url"):
            continue
        total += max(0, int(file["bytes"]) - _partial_bytes(root, file))
    return total


def _prefer(variants: list[str], canonical: str) -> str:
    names = {Path(item).name.lower(): item for item in variants}
    canon = Path(canonical).name.lower()
    if canon in names:
        return names[canon]
    quant = [item for item in variants if is_quantised(Path(item).name)]
    if quant:
        return sorted(quant)[0]
    return variants[0]


def _picks_path(root: Path) -> Path:
    return root / ".xenoform-picks.json"


def load_picks(root: Path | None = None) -> dict[str, str]:
    root = root or models_root()
    path = _picks_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def choose_file(model_id: str, relative: str, root: Path | None = None) -> dict[str, Any]:
    """Remember the file the user picked. The path has to be one of the variants."""
    root = root or models_root()
    spec = by_id(model_id)
    primary = spec["files"][0]
    allowed = slot_variants(root, primary)
    wanted = str(relative or "").replace("\\", "/").lstrip("/")
    if wanted not in allowed:
        raise PlainError("That file is not one of the weights for this model.")
    picks = load_picks(root)
    picks[model_id] = wanted
    _picks_path(root).write_text(json.dumps(picks, indent=2), encoding="utf-8")
    return {"id": model_id, "chosen": wanted, "filename": Path(wanted).name}


def chosen_file(model_id: str, root: Path | None = None, *, comfy_url: str = "") -> str:
    """Relative path of the weight in use. Empty when nothing is installed."""
    root = root or models_root()
    spec = by_id(model_id)
    primary = spec["files"][0]
    variants = slot_variants(root, primary, comfy_url=comfy_url)
    if not variants:
        return ""
    picked = load_picks(root).get(model_id) or ""
    if picked in variants:
        return picked
    return _prefer(variants, primary["path"])


def chosen_filename(model_id: str, root: Path | None = None) -> str:
    """Filename ComfyUI lists in its dropdown. The catalog name when the disk is empty."""
    spec = by_id(model_id)
    found = chosen_file(model_id, root)
    if found:
        return Path(found).name
    return Path(spec["files"][0]["path"]).name


def quantised_file(model_id: str, root: Path | None = None) -> str:
    """An fp8, int8, or other quantised variant, honouring a quantised user pick."""
    root = root or models_root()
    spec = by_id(model_id)
    variants = slot_variants(root, spec["files"][0])
    picked = load_picks(root).get(model_id) or ""
    if picked in variants and is_quantised(Path(picked).name):
        return Path(picked).name
    quant = [item for item in variants if is_quantised(Path(item).name)]
    if not quant:
        return ""
    return Path(sorted(quant)[0]).name


def model_present(model_id: str, root: Path | None = None, *, comfy_url: str = "") -> bool:
    root = root or models_root()
    spec = by_id(model_id)
    files = list(spec["files"])
    if not files:
        return False
    slots = [slot_variants(root, file, comfy_url=comfy_url) for file in files]
    if spec["required"]:
        return all(bool(found) for found in slots)
    return bool(slots[0])


def file_ready(path: Path, *, sha256: str, expected_bytes: int) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != int(expected_bytes):
        return False
    if not sha256:
        return True
    return _sha256(path) == sha256


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def llm_status() -> dict:
    try:
        from xenoform.llm import model_name, reachable

        up = bool(reachable())
    except Exception:
        up = False
        model_name = lambda: "qwen2.5:7b-instruct"  # noqa: E731
    name = model_name()
    if up:
        detail = f"Ollama is running: the idea line can be read by {name} when XENO_LLM_URL is set; the built-in rules work without it."
    else:
        detail = "Ollama is not running: the idea line is read by the built-in rules. No cloud key is required."
    return {"id": "llm", "name": "Local LLM", "required": False, "present": up, "model": name, "detail": detail, "bytes": 0, "size_label": "optional"}


def film_pack_status() -> dict:
    """The free film pack's Setup row (xenoform.film_pack): the keys of a model row, drawn by the same page code. The
    check never fails on the pack: a row that says why stands in when it cannot be read."""
    try:
        from xenoform import film_pack

        return film_pack.status()
    except Exception as exc:
        from xenoform.errors import plain_error

        return {"id": "film-pack", "name": "Free film pack", "required": False, "badge": "Clips", "manual": False, "present": False,
                "count": 0, "total": 0, "films": 0, "folder": "", "bytes": 0, "size_label": "0 B", "files": [], "detail": plain_error(exc)}


def inspect_setup(root: Path | None = None, comfy_url: str = "") -> dict:
    # no XENO_MODELS and no folder given: the desk guessed, and a guess that misses ComfyUI's folder
    # (ComfyUI Desktop's lives in Documents) sends 11.5 GB of downloads where ComfyUI never looks
    guessed = root is None and not os.environ.get("XENO_MODELS", "").strip()
    root = root or models_root()
    tier = detect_tier()
    free = disk_free(root)
    prefetch_listings(comfy_url)
    models = []
    for spec in CATALOG:
        parts = model_parts(spec, root, comfy_url=comfy_url)
        many = len(parts) > 1
        total = sum(row["bytes"] for _file, row in parts)
        present = model_present(spec["id"], root, comfy_url=comfy_url)
        ready = all(row["present"] for _file, row in parts) if many else present
        if spec.get("disk"):
            present = ready
        variants = [] if spec.get("no_pick") else (slot_variants(root, spec["files"][0], comfy_url=comfy_url) if spec["files"] else [])
        chosen = "" if spec.get("no_pick") else chosen_file(spec["id"], root, comfy_url=comfy_url)
        need = 0 if ready or spec.get("manual") else bytes_to_fetch(parts, root)
        models.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "short": spec.get("short") or spec["name"],
                "required": bool(spec["required"]),
                "badge": spec.get("badge") or ("Default" if spec["required"] else "Optional"),
                "manual": bool(spec.get("manual")),
                "present": present,
                "ready": ready,
                "bytes": total,
                "size_label": size_label(total),
                "need_bytes": need,
                "need_label": size_label(need),
                "why_not": "" if ready or spec.get("manual") else why_not_download(spec, tier, need, free),
                "blurb": spec.get("blurb") or "",
                "detail": spec["detail"],
                "files": [file["path"] for file in spec["files"]],
                "parts": [row for _file, row in parts] if many else [],
                "variants": variants,
                "chosen": chosen,
                "filename": Path(chosen).name if chosen else "",
            }
        )
    from xenoform.stems import stem_status

    missing = [item["name"] for item in models if item["required"] and not item["present"]]
    answered = comfy_listing("checkpoints", comfy_url) is not None
    if answered:
        checked = f"Checked against the files ComfyUI at {comfy_base(comfy_url)} can load. Downloads go to {root}."
    else:
        checked = f"ComfyUI is not answering, so the desk checked the files in {root}."
    if guessed:
        checked += " If ComfyUI's models folder is elsewhere, set XENO_MODELS to it and restart the desk."
    return {
        "tier": tier,
        "models_dir": str(root),
        "checked": checked,
        "comfy_answered": answered,
        "comfy_url": comfy_base(comfy_url),
        "disk": {"free_bytes": free, "free_label": f"{size_label(free)} free"},
        "models": models,
        "llm": llm_status(),
        "stems": stem_status(),
        "film_pack": film_pack_status(),
        "ableton": False,
        "missing_required": missing,
        "ffmpeg": ffmpeg_status(),
        "gate": make_gate(models, reliable=answered or not guessed),
        "final": final_summary(),
        "try_it": "The bundled demo needs no model download.",
    }


_SPARE = 512 * 1024 * 1024  # room a download leaves on the drive (the same margin _run_download asks for)


def why_not_download(spec: dict, tier: dict, need: int, free: int) -> str:
    """Why this model's Download is off, in a sentence, or an empty string when it can run."""
    min_gb = spec.get("min_gb")
    if min_gb and tier.get("gb") is not None and float(tier["gb"]) < float(min_gb):
        return f"Final needs a 12 GB card; this one reads as {tier.get('label') or 'smaller'}, so Final falls back to the Draft."
    from xenoform.film_pack import offline

    if offline():
        return "XENO_OFFLINE is set, so nothing is downloaded."
    if need and free < need + _SPARE:
        return f"Needs {size_label(need)} plus a little spare room; the models drive has {size_label(free)} free."
    return ""


def ffmpeg_status() -> dict:
    """Whether ffmpeg and ffprobe are on PATH, for the Setup page. The installers do not install ffmpeg (they say so
    as they run, where it scrolls away), and without it the desk opens but no song is read and no video written."""
    import platform
    import shutil

    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if not missing:
        return {"found": True, "missing": [], "line": "", "how": ""}
    how = {"Windows": "In a terminal: winget install Gyan.FFmpeg",
           "Darwin": "In Terminal: brew install ffmpeg"}.get(platform.system(), "Install it with your package manager, for example: sudo apt install ffmpeg")
    return {"found": False, "missing": missing,
            "line": f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not on this machine's PATH",
            "how": f"Xenoform needs ffmpeg to read songs and write videos. {how}. Then close Xenoform's windows and start it again."}


def make_gate(models: list[dict], *, reliable: bool) -> dict:
    """What the desk says beside Make while a required model is missing (the Make button leads to Setup until it is in).

    It stays quiet when the answer is a guess: ComfyUI does not answer and the models folder was not named, so the
    files may simply be where this desk does not look."""
    absent = [item for item in models if item["required"] and not item["ready"]]
    need = sum(int(item["need_bytes"]) for item in absent)
    label = size_label(need)
    names = ", ".join(item["short"] for item in absent)
    return {
        "blocked": bool(absent) and reliable,
        "reliable": reliable,
        "names": [item["short"] for item in absent],
        "bytes": need,
        "size_label": label,
        "line": f"To make videos you need {names}, {label}" if absent else "",
        "button": f"Get the {label} model" if absent else "",
    }


def final_summary() -> dict:
    """The model Final resolves to here, for Setup's header and the tier sentence."""
    from xenoform.hardware import final_model

    model = final_model()
    return {"model": model, "label": "LTX-2.5" if model == "ltx25" else "LTX-2.3"}


_DOWNLOADS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def download_status(model_id: str) -> dict:
    if model_id == "film-pack":  # the free film pack keeps its own job (xenoform.film_pack)
        from xenoform import film_pack

        return film_pack.download_status()
    with _LOCK:
        row = dict(_DOWNLOADS.get(model_id) or {"status": "idle", "progress": 0, "detail": "", "error": None})
    return row


def start_download(model_id: str, root: Path | None = None) -> dict:
    if model_id == "llm":
        return _start_llm()
    if model_id == "film-pack":  # the same Download button and status route as a model; the pack runs its own thread
        from xenoform import film_pack

        return film_pack.start()
    spec = by_id(model_id)
    if spec.get("manual"):
        raise PlainError(spec.get("manual_note") or "Place the local file. Setup does not download FLUX Klein weights.")
    from xenoform.film_pack import offline

    if offline():  # the film pack already said no; a model is gigabytes from the web, so it says no too
        raise PlainError("XENO_OFFLINE is set, so nothing is downloaded. Unset it and press Download again.")
    where = root or models_root()
    prefetch_listings()
    parts = model_parts(spec, where)
    why = why_not_download(spec, detect_tier(), bytes_to_fetch(parts, where), disk_free(where))
    if why:  # the card's own reason, as a refusal: the drive is too small, or the card is
        raise PlainError(why)
    with _LOCK:
        current = _DOWNLOADS.get(model_id) or {}
        if current.get("status") == "running":
            return dict(current)
        _DOWNLOADS[model_id] = {"status": "running", "progress": 0.0, "detail": "Starting", "error": None}
    thread = threading.Thread(target=_run_download, args=(model_id, root or models_root()), daemon=True, name=f"xenoform-get-{model_id}")
    thread.start()
    return download_status(model_id)


def _start_llm() -> dict:
    with _LOCK:
        _DOWNLOADS["llm"] = {"status": "running", "progress": 0.2, "detail": "Asking Ollama", "error": None}
    thread = threading.Thread(target=_pull_llm, daemon=True, name="xenoform-llm")
    thread.start()
    return download_status("llm")


def _pull_llm() -> None:
    try:
        from xenoform.llm import model_name, reachable

        if not reachable():
            raise PlainError(
                "Ollama is not running on this machine. The idea line still works: "
                "the built-in rules read it when no model is loaded."
            )
        _set("llm", status="running", progress=0.5, detail=f"Pulling {model_name()}", error=None)
        _ollama_pull(model_name())
        _set("llm", status="done", progress=1.0, detail=f"{model_name()} is ready.", error=None)
    except Exception as exc:
        from xenoform.errors import plain_error

        _set("llm", status="error", progress=0, detail=plain_error(exc), error=plain_error(exc))


def _ollama_pull(name: str) -> None:
    import json
    from urllib.request import Request as UrlRequest
    from urllib.request import urlopen as open_url

    from xenoform.llm import _base

    payload = json.dumps({"name": name, "stream": False}).encode("utf-8")
    request = UrlRequest(_base() + "/api/pull", data=payload, headers={"Content-Type": "application/json"})
    with open_url(request, timeout=600) as response:
        response.read()


def _set(model_id: str, **fields: Any) -> None:
    with _LOCK:
        row = _DOWNLOADS.setdefault(model_id, {})
        row.update(fields)


def _run_download(model_id: str, root: Path) -> None:
    from xenoform.errors import plain_error

    try:
        spec = by_id(model_id)
        prefetch_listings()
        parts = model_parts(spec, root)
        # only what is not in place: a Final with the fp8 file already here fetches the text encoder and the upscalers
        todo = [file for file, row in parts if not row["present"] and file.get("url")]
        total = sum(int(file["bytes"]) for file in todo) or 1
        need = bytes_to_fetch(parts, root)
        free = disk_free(root)
        if free < need + _SPARE:
            raise PlainError(
                f"This download needs {size_label(need)} plus a little spare room. The drive has {size_label(free)} free."
            )
        done = 0
        for file in todo:
            dest = root / file["path"]

            def on_progress(frac: float, detail: str, *, base=done, size=int(file["bytes"])) -> None:
                overall = (base + frac * size) / total
                _set(model_id, status="running", progress=round(overall, 4), detail=detail, error=None)

            download_file(
                file["url"],
                dest,
                sha256=str(file.get("sha256") or ""),
                expected_bytes=int(file["bytes"]),
                on_progress=on_progress,
            )
            done += int(file["bytes"])
        _set(model_id, status="done", progress=1.0, detail=f"{spec['name']} is in place.", error=None)
    except Exception as exc:
        _set(model_id, status="error", progress=0, detail=plain_error(exc), error=plain_error(exc))


def download_file(
    url: str,
    dest: Path,
    *,
    sha256: str,
    expected_bytes: int,
    on_progress: Callable[[float, str], None] | None = None,
    opener: Callable[..., tuple] | None = None,
) -> Path:
    """Download with resume. A bad checksum deletes the partial file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if file_ready(dest, sha256=sha256, expected_bytes=expected_bytes):
        if on_progress:
            on_progress(1.0, f"{dest.name} is already here")
        return dest
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    if have > expected_bytes:
        part.unlink()
        have = 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    status, read, _length = (opener or _open)(url, headers)
    if status == 200 and have:
        have = 0
        mode = "wb"
    elif status in (200, 206):
        mode = "ab" if status == 206 and have else "wb"
        if mode == "wb":
            have = 0
    else:
        raise PlainError(f"The download of {dest.name} did not start.")
    with part.open(mode) as handle:
        done = have
        while True:
            chunk = read()
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if on_progress and expected_bytes:
                on_progress(min(0.99, done / expected_bytes), f"{dest.name} · {size_label(done)} of {size_label(expected_bytes)}")
    if not file_ready(part, sha256=sha256, expected_bytes=expected_bytes):
        part.unlink(missing_ok=True)
        raise PlainError(f"{dest.name} did not match its {'checksum' if sha256 else 'size'}. Nothing was kept. Run the download again.")
    part.replace(dest)
    if on_progress:
        note = "checksum matches" if sha256 else "size matches"
        on_progress(1.0, f"{dest.name} is in place, and the {note}.")
    return dest


def _open(url: str, headers: dict) -> tuple[int, Callable[[], bytes], int]:
    request = Request(url, headers=headers)
    response = urlopen(request, timeout=120)
    status = getattr(response, "status", 200)

    def read() -> bytes:
        return response.read(1024 * 256)

    length = int(response.headers.get("Content-Length") or 0)
    return status, read, length
