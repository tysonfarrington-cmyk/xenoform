"""First-run model check. Downloads are ungated Hugging Face files. No token.

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
_Z = "https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files"
_ACE = "https://huggingface.co/Comfy-Org/ace_step_1.5_ComfyUI_files/resolve/main/checkpoints/ace_step_1.5_turbo_aio.safetensors"
_WAN = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main"

CATALOG: tuple[dict[str, Any], ...] = (
    {
        "id": "ltx-095",
        "name": "LTX 0.9.5 fast",
        "required": True,
        "badge": "Morphs",
        "detail": "LTX 0.9.5 covers morphs, Turbo, and 8 GB or 12 GB cards. It is the required download. Turbo never loads LTX-2.3. A dry run does not need the file.",
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
        "badge": "Core",
        "detail": "Sole core video model. Draft and Final use it on a 24 GB card, and on a 12 GB card when an fp8 or int8 file is present. The full weights are about 43 GB. Morph restyles use the same file when it is present, fp8 on 12 GB. LTX 0.9.5 is the fast morph. Turbo never loads this file.",
        "files": (
            {
                "path": "checkpoints/ltx-2.3-22b-distilled.safetensors",
                "url": _LTX23,
                "bytes": 46149345038,
                "sha256": "",
            },
        ),
    },
    {
        "id": "z-image",
        "name": "Z-Image Turbo",
        "required": False,
        "badge": "Stills",
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
        "detail": "Optional alternative for first-frame action shots. About 18 GB with the VAE and text encoder. Turbo never loads it.",
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
        "detail": "Optional heavier image-to-video alternative. High-noise and low-noise 14B fp8. Turbo never loads it.",
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
    ]


def models_root() -> Path:
    env = os.environ.get("XENO_MODELS")
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


def slot_variants(root: Path, file: dict) -> list[str]:
    """Relative paths that satisfy one catalog slot, canonical name first."""
    folder = root / Path(file["path"]).parent
    canonical = Path(file["path"]).name
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


def chosen_file(model_id: str, root: Path | None = None) -> str:
    """Relative path of the weight in use. Empty when nothing is on disk."""
    root = root or models_root()
    spec = by_id(model_id)
    primary = spec["files"][0]
    variants = slot_variants(root, primary)
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


def model_present(model_id: str, root: Path | None = None) -> bool:
    root = root or models_root()
    spec = by_id(model_id)
    files = list(spec["files"])
    if not files:
        return False
    slots = [slot_variants(root, file) for file in files]
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
        detail = f"Ollama is running. Director's notes can use {name}. The rule reader still works if you skip it."
    else:
        detail = (
            "Ollama is not running. Director's notes reads the note with its built-in rules. "
            "No cloud key is required."
        )
    return {"id": "llm", "name": "Local LLM", "required": False, "present": up, "model": name, "detail": detail, "bytes": 0, "size_label": "optional"}


def inspect_setup(root: Path | None = None) -> dict:
    root = root or models_root()
    tier = detect_tier()
    models = []
    for spec in CATALOG:
        total = sum(int(file["bytes"]) for file in spec["files"])
        present = model_present(spec["id"], root)
        variants = slot_variants(root, spec["files"][0]) if spec["files"] else []
        chosen = chosen_file(spec["id"], root)
        models.append(
            {
                "id": spec["id"],
                "name": spec["name"],
                "required": bool(spec["required"]),
                "badge": spec.get("badge") or ("Default" if spec["required"] else "Optional"),
                "manual": bool(spec.get("manual")),
                "present": present,
                "bytes": total,
                "size_label": size_label(total),
                "detail": spec["detail"],
                "files": [file["path"] for file in spec["files"]],
                "variants": variants,
                "chosen": chosen,
                "filename": Path(chosen).name if chosen else "",
            }
        )
    free = disk_free(root)
    from xenoform.stems import stem_status

    missing = [item["name"] for item in models if item["required"] and not item["present"]]
    return {
        "tier": tier,
        "models_dir": str(root),
        "disk": {"free_bytes": free, "free_label": f"{size_label(free)} free"},
        "models": models,
        "llm": llm_status(),
        "stems": stem_status(),
        "ableton": False,
        "missing_required": missing,
        "try_it": "The bundled demo and the Pynchon register need no model download.",
    }


_DOWNLOADS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def download_status(model_id: str) -> dict:
    with _LOCK:
        row = dict(_DOWNLOADS.get(model_id) or {"status": "idle", "progress": 0, "detail": "", "error": None})
    return row


def start_download(model_id: str, root: Path | None = None) -> dict:
    if model_id == "llm":
        return _start_llm()
    spec = by_id(model_id)
    if spec.get("manual"):
        raise PlainError("Place the local file. Setup does not download FLUX Klein weights.")
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
                "Ollama is not running on this machine. Director's notes still works. "
                "Its rule reader handles the note when no model is loaded."
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
        total = sum(int(file["bytes"]) for file in spec["files"])
        free = disk_free(root)
        if free < total + 512 * 1024 * 1024:
            raise PlainError(
                f"This download needs {size_label(total)} plus a little spare room. The drive has {size_label(free)} free."
            )
        done = 0
        for file in spec["files"]:
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
        raise PlainError(f"{dest.name} did not match its checksum. Nothing was kept. Run the download again.")
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
