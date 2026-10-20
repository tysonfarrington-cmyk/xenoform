"""Simple-path tools for the Xenoform MCP server.

Every tool here calls the running desk over localhost (the same REST API the
browser uses), so no render, vibe or recipe logic is duplicated. The only state
kept here is the agent's project settings, saved to a small JSON file so a
server restart picks up where it left off.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
GUIDE_FILE = REPO / "docs" / "AI_GUIDE.md"

VIBES = ("liquid-gold", "bloom", "neon-night", "ocean", "cosmic", "paper-summer", "black")
ASPECTS = ("9:16", "16:9", "1:1")
VERTICAL = ("native", "crop", "auto")
ENERGIES = ("flow", "dense")
# preview: the CPU animatic (no GPU model). draft/final: open-weights LTX on ComfyUI.
TIERS = ("preview", "draft", "final")
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif", ".m4a"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD = 200 * 1024 * 1024
ANALYSIS_KEYS = ("duration", "tempo", "beats", "drops", "sections")
BOARD_KEYS = ANALYSIS_KEYS + ("blocks", "scenes", "cards", "sliders", "palette", "register", "flash", "customs", "locks", "preset")
_SECRET = re.compile(r"(api[_-]?key|secret|password|token|auth|cookie|credential|key_present)", re.I)

DEFAULTS: dict[str, Any] = {
    "prompt": "",
    "vibe": "black",
    "aspect": "9:16",
    "vertical_mode": "native",
    "tier": "preview",
    "energy": "flow",
    "transitions": [],
    "beat_fx": True,
    "end_card": False,
    "audio_id": "demo",
    "song": "Built-in demo track",
    "hero_id": "",
    "images": [],
    "shot_edits": [],
    "cloud": False,
}


try:  # the SDK turns ToolError into an isError result carrying this message
    from mcp.server.mcpserver.exceptions import ToolError as _Base
except ImportError:  # pragma: no cover - the SDK is optional
    _Base = Exception


class XenoformError(_Base):
    """Raised for bad input or a desk failure. The MCP SDK sends the message back as a tool error."""


def scrub(value: Any) -> Any:
    """Drop anything that looks like a credential, at any depth."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if not _SECRET.search(str(k))}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def state_file() -> Path:
    raw = os.environ.get("XENO_MCP_STATE")
    if raw:
        return Path(raw)
    return Path.home() / ".xenoform" / "mcp_project.json"


class Desk:
    """Thin JSON client for the desk. Raises XenoformError with the desk's own message."""

    def __init__(self, base: str, timeout: float = 60.0):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _open(self, request: urllib.request.Request, timeout: float | None) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(detail).get("detail") or detail
            except (ValueError, AttributeError):
                pass
            raise XenoformError(f"Desk answered {exc.code}: {str(detail)[:400]}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise XenoformError(
                f"Cannot reach the Xenoform desk at {self.base} ({exc}). Start Xenoform.bat, or set XENO_DESK to its URL."
            ) from None

    def json(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        raw = self._open(req, timeout)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise XenoformError(f"Desk sent something that is not JSON for {path}.") from None

    def upload(self, path: str, file: Path, timeout: float | None = None) -> dict:
        boundary = uuid.uuid4().hex
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{file.name}\"\r\n"
                f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
        body = head + file.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(self.base + path, data=body, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        raw = self._open(req, timeout or 300.0)
        return json.loads(raw.decode("utf-8") or "{}")

    def download(self, path: str, dest: Path, timeout: float | None = None) -> int:
        req = urllib.request.Request(self.base + path, method="GET")
        raw = self._open(req, timeout or 300.0)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        return len(raw)


def _pick(name: str, value: str, allowed: tuple[str, ...]) -> str:
    value = str(value or "").strip().lower()
    if value not in allowed:
        raise XenoformError(f"Unknown {name} '{value}'. Use one of: {', '.join(allowed)}.")
    return value


def _job_id(job_id: str) -> str:
    job_id = str(job_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", job_id):
        raise XenoformError("job_id looks wrong. Use the id start_render returned.")
    return job_id


def _local_file(path: str, suffixes: set[str], kind: str) -> Path:
    if not str(path or "").strip():
        raise XenoformError(f"Give the full path to a {kind} file on this PC.")
    file = Path(str(path).strip().strip('"')).expanduser()
    if file.suffix.lower() not in suffixes:
        raise XenoformError(f"{file.name} is not a {kind} file. Use {', '.join(sorted(suffixes))}.")
    if not file.is_file():
        raise XenoformError(f"No file at {file}.")
    if file.stat().st_size > MAX_UPLOAD:
        raise XenoformError(f"{file.name} is over 200 MB.")
    return file


RECIPE_VERSION = 2


def encode_v2(base: str, transitions: list, blocks: list) -> str:
    """xf2.<base64url(zlib(json))>: the desk's xf1 code plus transitions and shot edits."""
    import base64
    import zlib

    keep = [{k: b[k] for k in ("form", "hold", "transition", "energy") if k in b} for b in blocks][:64]
    raw = json.dumps({"v": RECIPE_VERSION, "base": base, "transitions": list(transitions)[:32], "blocks": keep},
                     separators=(",", ":")).encode("utf-8")
    return "xf2." + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")


def decode_v2(code: str) -> dict:
    import base64
    import binascii
    import zlib

    body = code[4:]
    try:
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))).decode("utf-8"))
    except (binascii.Error, zlib.error, ValueError, UnicodeDecodeError):
        raise XenoformError("That xf2 recipe code is damaged. Copy it again.") from None
    if not isinstance(data, dict) or not str(data.get("base") or "").startswith(("xf1.", "XF-")):
        raise XenoformError("That xf2 recipe code is damaged. Copy it again.")
    if int(data.get("v") or 0) > RECIPE_VERSION:
        raise XenoformError("That recipe comes from a newer Xenoform. Update to remix it.")
    return {"base": data["base"], "transitions": [str(t) for t in data.get("transitions") or []],
            "blocks": [b for b in data.get("blocks") or [] if isinstance(b, dict)], "recipe_version": int(data.get("v") or 2)}


def read_guide() -> str:
    try:
        return GUIDE_FILE.read_text(encoding="utf-8")
    except OSError:
        return "# Xenoform\nSee docs/mcp.md in the repo. Call get_status, then list_vibes."


class App:
    """The agent's view of the app. One instance per MCP server process."""

    def __init__(self, desk: Desk, state_path: Path | None = None):
        self.desk = desk
        self.lock = threading.RLock()
        self.path = state_path or state_file()
        self.project = dict(DEFAULTS)
        self.jobs: dict[str, dict] = {}
        self.boards: dict[str, dict] = {}
        self._load()

    # ---- state -------------------------------------------------------
    def _load(self) -> None:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(saved, dict):
            self.project.update({k: v for k, v in (saved.get("project") or {}).items() if k in DEFAULTS})
            self.jobs = {k: v for k, v in (saved.get("jobs") or {}).items() if isinstance(v, dict)}
            self.boards = {k: v for k, v in (saved.get("boards") or {}).items() if isinstance(v, dict)}

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"project": self.project, "jobs": self.jobs, "boards": self.boards}, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    # ---- read-only ---------------------------------------------------
    def status(self) -> dict:
        out: dict[str, Any] = {"desk": self.desk.base, "project": self.settings()}
        try:
            out["health"] = self.desk.json("GET", "/api/v1/health", timeout=10)
            out["desk_ok"] = True
        except XenoformError as exc:
            out["desk_ok"] = False
            out["detail"] = str(exc)
            return scrub(out)
        for key, path in (("comfy", "/api/comfy"), ("diagnostics", "/api/diagnostics"),
                          ("final_tier", "/api/simple/options?duration=20")):
            try:
                out[key] = self.desk.json("GET", path, timeout=15)
            except XenoformError as exc:
                out[key] = {"detail": str(exc)}
        diag = str((out.get("diagnostics") or {}).get("diagnostics") or "")
        out["gpu_tier"] = next((line.split(":", 1)[1].strip() for line in diag.splitlines() if line.startswith("tier:")), "")
        with self.lock:
            out["my_jobs"] = [dict(job, id=jid) for jid, job in list(self.jobs.items())[-10:]]
        return scrub(out)

    def vibes(self) -> dict:
        looks: dict = {}
        tuned: dict = {}
        try:
            from xenoform import morph_pass

            looks = dict(morph_pass.VIBE_LOOK)
            tuned = (morph_pass.autotune() or {}).get("vibes") or {}
        except Exception:
            pass
        recs: dict = {}
        try:
            from xenoform import transitions_fx

            recs = dict(getattr(transitions_fx, "RECOMMENDED", {}) or {})
        except Exception:
            pass
        return {"vibes": [{"id": v, "look": looks.get(v, ""), "autotune": tuned.get(v) or {},
                           "recommended_transitions": recs.get(v) or {}} for v in VIBES],
                "default": DEFAULTS["vibe"]}

    def autotune(self, vibe: str = "") -> dict:
        try:
            from xenoform import morph_pass

            data = morph_pass.autotune() or {}
        except Exception as exc:
            raise XenoformError(f"Autotune recipes are not readable: {exc}") from None
        if vibe:
            vibe = _pick("vibe", vibe, VIBES)
            return {"vibe": vibe, "recipe": (data.get("vibes") or {}).get(vibe) or {},
                    "note": "Applied automatically on draft and final renders."}
        return data

    def transitions(self) -> dict:
        out = self.desk.json("GET", "/api/v1/transitions")
        try:
            from xenoform import transitions_fx

            out["scene_transitions"] = transitions_fx.public_list()
            out["recommended"] = getattr(transitions_fx, "RECOMMENDED", {})
        except Exception:
            out["scene_transitions"] = []
        return out

    def shapes(self) -> dict:
        data = self.desk.json("GET", "/api/catalog")
        return {"shapes": [{k: f.get(k) for k in ("id", "name", "pack", "blurb", "kind")} for f in data.get("forms") or []]}

    def settings(self) -> dict:
        with self.lock:
            return dict(self.project)

    # ---- edits -------------------------------------------------------
    def update(self, **changes: Any) -> dict:
        clean: dict[str, Any] = {}
        for key, value in changes.items():
            if value is None:
                continue
            if key == "vibe":
                clean[key] = _pick("vibe", value, VIBES)
            elif key == "aspect":
                clean[key] = _pick("aspect", value, ASPECTS)
            elif key == "vertical_mode":
                clean[key] = _pick("vertical_mode", value, VERTICAL)
            elif key == "tier":
                clean[key] = _pick("tier", value, TIERS)
            elif key == "energy":
                clean[key] = _pick("energy", value, ENERGIES)
            elif key == "prompt":
                text = str(value).strip()
                if len(text) > 2000:
                    raise XenoformError("Keep the prompt under 2000 characters.")
                clean[key] = text
            elif key == "transitions":
                if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
                    raise XenoformError("transitions must be a list of transition ids.")
                known = self._transition_ids()
                bad = [t for t in value if known and t not in known]
                if bad:
                    raise XenoformError(f"Unknown transitions {bad}. Call list_transitions.")
                clean[key] = list(value)[:32]
            elif key in ("beat_fx", "end_card"):
                clean[key] = bool(value)
            else:
                raise XenoformError(f"Unknown setting {key}.")
        with self.lock:
            self.project.update(clean)
            self._save()
            return dict(self.project)

    def _transition_ids(self) -> set[str]:
        ids: set[str] = set()
        try:
            ids |= {t["id"] for t in self.desk.json("GET", "/api/v1/transitions", timeout=10).get("transitions") or []}
        except (XenoformError, KeyError, TypeError):
            pass
        try:
            from xenoform import transitions_fx

            ids |= {t.get("id") for t in transitions_fx.public_list()}
        except Exception:
            pass
        return ids

    def create(self, prompt: str = "", vibe: str = "black", aspect: str = "9:16", tier: str = "preview",
               energy: str = "flow", audio_path: str = "", image_paths: list[str] | None = None) -> dict:
        if not str(prompt).strip() and not image_paths:
            raise XenoformError("Give a prompt (an idea in a line) or at least one image.")
        fresh = dict(DEFAULTS)
        with self.lock:
            self.project = fresh
        project = self.update(prompt=prompt, vibe=vibe, aspect=aspect, tier=tier, energy=energy)
        if audio_path:
            self.load_audio(audio_path)
        for image in image_paths or []:
            self.attach_image(image)
        return {"project": self.settings(), "next": "Call start_render, then wait_for_render."}

    def load_audio(self, path: str) -> dict:
        file = _local_file(path, AUDIO_SUFFIXES, "audio")
        data = self.desk.upload("/api/analyze", file)
        audio_id = str(data.get("audio_id") or "")
        if not audio_id:
            raise XenoformError("The desk did not accept that song.")
        with self.lock:
            self.boards = {audio_id: {k: data[k] for k in BOARD_KEYS if k in data}}
            self.project.update(audio_id=audio_id, song=file.stem)
            self._save()
        return {"audio_id": audio_id, "song": file.stem, "duration": data.get("duration"),
                "tempo": data.get("tempo") or data.get("bpm")}

    def attach_image(self, path: str, role: str = "morph_target") -> dict:
        role = _pick("role", role, ("morph_target", "first_frame"))
        file = _local_file(path, IMAGE_SUFFIXES, "image")
        if role == "first_frame":
            hero = str(self.desk.upload("/api/hero", file).get("id") or "")
            with self.lock:
                self.project["hero_id"] = hero
                self._save()
            return {"image_id": hero, "role": role, "detail": "This picture is the first frame of every shot."}
        with self.lock:
            images = [i for i in self.project.get("images") or [] if i.get("path") != str(file.resolve())]
            images.append({"name": file.name, "path": str(file.resolve())})
            self.project["images"] = images[-12:]
            self._save()
            count = len(self.project["images"])
        return {"role": role, "morph_targets": count,
                "detail": "The object morphs through your images in order, then the vibe's own objects (draft and final)."}

    # ---- renders -----------------------------------------------------
    def body(self) -> dict:
        p = self.settings()
        live = p["tier"] != "preview"
        return {
            "mode": "simple", "audio_id": p["audio_id"], "song": p["song"], "vibe": p["vibe"],
            "idea": p["prompt"], "brief": p["prompt"], "aspect": p["aspect"],
            "vertical_mode": p["vertical_mode"], "energy_preset": p["energy"],
            "quality_tier": "final" if p["tier"] == "final" else "draft",
            "quality": "turbo" if p["tier"] == "preview" else p["tier"],
            "live": live, "beat_fx": p["beat_fx"], "end_card": p["end_card"],
            "transitions": p["transitions"], "hero_id": p["hero_id"],
            "morph_targets": [i["path"] for i in p.get("images") or [] if i.get("path")],
            "paid_cloud": False, "cloud_quality": False, "cloud_confirm": "", "video_model": "ltx-23",
        }

    def board(self, audio_id: str) -> dict:
        """The desk's own scene plan for the song (blocks, scenes, cards...), as the browser sends it."""
        with self.lock:
            cached = self.boards.get(audio_id)
        if cached:
            return dict(cached)
        edits = self.settings().get("shot_edits") or []
        if audio_id != "demo":
            raise XenoformError("The desk no longer has that song (it restarted?). Call load_audio again.")
        data = self.desk.json("GET", "/api/demo")
        board = {k: data[k] for k in BOARD_KEYS if k in data}
        if edits:
            board["blocks"] = [dict(b) for b in edits]
        return board

    def _set_board(self, audio_id: str, board: dict) -> None:
        with self.lock:
            self.boards = {audio_id: board}
            self._save()

    # ---- recipes -----------------------------------------------------
    def recipe_fields(self) -> dict:
        b = self.body()
        return {k: b[k] for k in ("vibe", "idea", "aspect", "vertical_mode", "energy_preset", "quality_tier",
                                  "beat_fx", "end_card", "song", "transitions")}

    def encode_recipe(self) -> dict:
        code = str(self.desk.json("POST", "/api/simple/recipe/encode", self.recipe_fields()).get("recipe") or "")
        p = self.settings()
        if code and (p.get("transitions") or p.get("shot_edits")):
            code = encode_v2(code, p.get("transitions") or [], p.get("shot_edits") or [])
        return {"recipe": code, "settings": self.recipe_fields(),
                "detail": "Paste this code into Xenoform (or remix_recipe) to remake the look."}

    def _recipe_or_blank(self) -> str:
        try:
            return self.encode_recipe()["recipe"]
        except XenoformError:
            return ""

    def decode_recipe(self, code: str) -> dict:
        code = str(code or "").strip()
        if not code or len(code) > 4000:
            raise XenoformError("Paste a recipe code (it starts with xf1. or XF-).")
        extra: dict[str, Any] = {}
        if code.startswith("xf2."):
            extra = decode_v2(code)
            code = extra.pop("base")
        path = "/api/simple/recipe/decode" if code.startswith("xf") else "/api/recipe/decode"
        out = scrub(self.desk.json("POST", path, {"recipe": code}))
        out.update(extra)
        return out

    def remix(self, code: str, prompt: str | None = None, vibe: str | None = None, aspect: str | None = None,
              tier: str | None = None) -> dict:
        state = self.decode_recipe(code)
        changes: dict[str, Any] = {}
        if state.get("vibe") in VIBES:
            changes["vibe"] = state["vibe"]
        if state.get("aspect") in ASPECTS:
            changes["aspect"] = state["aspect"]
        if state.get("energy_preset") in ENERGIES:
            changes["energy"] = state["energy_preset"]
        if state.get("idea"):
            changes["prompt"] = str(state["idea"])
        for key in ("beat_fx", "end_card"):
            if key in state:
                changes[key] = bool(state[key])
        if isinstance(state.get("transitions"), list):
            changes["transitions"] = [str(t) for t in state["transitions"]]
        for key, value in (("prompt", prompt), ("vibe", vibe), ("aspect", aspect), ("tier", tier)):
            if value:
                changes[key] = value
        project = self.update(**changes)
        blocks = state.get("blocks")
        with self.lock:
            self.project["shot_edits"] = [dict(b) for b in blocks if isinstance(b, dict)][:64] if isinstance(blocks, list) else []
            self._save()
            project = dict(self.project)
        return {"project": project, "from_recipe": {k: state.get(k) for k in ("vibe", "idea", "aspect", "seed")},
                "next": "Call start_render."}

    # ---- director ----------------------------------------------------
    def analysis(self) -> dict:
        audio_id = self.settings()["audio_id"]
        board = self.board(audio_id)
        beats = list(board.get("beats") or [])
        return {"audio_id": audio_id, "duration": board.get("duration"), "tempo": board.get("tempo"),
                "beat_count": len(beats), "beats": beats[:400], "drops": board.get("drops"),
                "sections": board.get("sections") or []}

    def timeline(self) -> dict:
        board = self.board(self.settings()["audio_id"])
        beats = list(board.get("beats") or [])
        at = 0.0
        rows = []
        for i, block in enumerate(board.get("blocks") or []):
            hold = float(block.get("hold") or 0)
            near = min(beats, key=lambda b: abs(b - at)) if beats else None
            rows.append({"index": i, "start": round(at, 3), "end": round(at + hold, 3), "hold": hold,
                         "form": block.get("form"), "transition": block.get("transition"), "energy": block.get("energy"),
                         "off_beat_s": round(abs(near - at), 3) if near is not None else None})
            at += hold
        return {"duration": board.get("duration"), "tempo": board.get("tempo"), "cut_length": round(at, 3),
                "shots": rows, "sections": board.get("sections") or [], "drops": board.get("drops")}

    def apply_edits(self, edits: list) -> dict:
        if not isinstance(edits, list) or not edits or len(edits) > 64:
            raise XenoformError("edits must be a list of 1-64 objects like {index, hold, transition, form, energy}.")
        audio_id = self.settings()["audio_id"]
        board = self.board(audio_id)
        blocks = [dict(b) for b in board.get("blocks") or []]
        trans = self._transition_ids()
        forms = set()
        try:
            forms = {f.get("id") for f in self.shapes()["shapes"]}
        except XenoformError:
            pass
        for n, edit in enumerate(edits):
            if not isinstance(edit, dict):
                raise XenoformError(f"Edit {n} is not an object.")
            op = str(edit.get("op") or "set")
            idx = edit.get("index")
            if op == "append":
                idx = len(blocks)
                blocks.append(dict(blocks[-1]) if blocks else {"form": "sphere", "hold": 2.0, "transition": "snap", "energy": "calm"})
            if not isinstance(idx, int) or not 0 <= idx < len(blocks):
                raise XenoformError(f"Edit {n}: index must be 0..{len(blocks) - 1}.")
            if op == "delete":
                if len(blocks) <= 1:
                    raise XenoformError("A cut needs at least one shot.")
                blocks[idx] = None  # removed after the loop so indexes stay stable
                continue
            if op not in {"set", "append"}:
                raise XenoformError(f"Edit {n}: op is set, append or delete.")
            block = blocks[idx]
            if block is None:
                raise XenoformError(f"Edit {n}: shot {idx} was deleted earlier in this list.")
            if "hold" in edit:
                hold = float(edit["hold"])
                if not 0.25 <= hold <= 30:
                    raise XenoformError(f"Edit {n}: hold must be 0.25-30 s.")
                block["hold"] = round(hold, 4)
            if "transition" in edit:
                if trans and edit["transition"] not in trans:
                    raise XenoformError(f"Edit {n}: unknown transition {edit['transition']}.")
                block["transition"] = str(edit["transition"])
            if "form" in edit:
                if forms and edit["form"] not in forms:
                    raise XenoformError(f"Edit {n}: unknown form {edit['form']}. Call list_shapes.")
                block["form"] = str(edit["form"])
            if "energy" in edit:
                block["energy"] = str(edit["energy"])[:20]
        board["blocks"] = [b for b in blocks if b is not None]
        self._set_board(audio_id, board)
        with self.lock:
            self.project["shot_edits"] = board["blocks"]
            self._save()
        return self.timeline()

    def full_body(self) -> dict:
        body = self.body()
        edits = self.settings().get("shot_edits") or []
        if edits:
            body["shot_edits_blocks"] = [dict(b) for b in edits]
        board = self.board(body["audio_id"])
        if body.get("shot_edits_blocks"):
            board["blocks"] = body.pop("shot_edits_blocks")
        picks = list(body.get("transitions") or [])
        if picks:
            try:
                shot_ids = {t.get("id") for t in self.desk.json("GET", "/api/v1/transitions", timeout=10).get("transitions") or []}
            except XenoformError:
                shot_ids = set()
            picks = [t for t in picks if t in shot_ids]
        if picks:
            board["blocks"] = [dict(b, transition=picks[i % len(picks)]) for i, b in enumerate(board.get("blocks") or [])]
        return {**board, **body}

    def start(self, cloud: bool = False, confirm_spend: bool = False) -> dict:
        body = self.full_body()
        cost = None
        if cloud:
            if confirm_spend is not True:
                raise XenoformError("Cloud quality costs money. Ask the user, then call again with confirm_spend=true.")
            plan = self.desk.json("POST", "/api/cloud/estimate", {**body, "paid_cloud": True})
            token = str(plan.get("token") or "")
            if not token or not plan.get("can_submit"):
                raise XenoformError("Cloud quality is not ready (over the cost cap, node missing, or no key set).")
            cost = scrub(plan.get("estimate"))
            body.update(paid_cloud=True, cloud_quality=True, cloud_confirm=token)
        with self.lock:
            running = [j for j, v in self.jobs.items() if v.get("status") == "running"]
        data = self.desk.json("POST", "/api/generate", body, timeout=60)
        job_id = str(data.get("id") or "")
        if not job_id:
            raise XenoformError("The desk did not start a render.")
        with self.lock:
            self.jobs[job_id] = {"status": "running", "tier": self.project["tier"], "vibe": self.project["vibe"],
                                 "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "cloud": bool(cloud)}
            self.jobs = dict(list(self.jobs.items())[-50:])
            self._save()
        out = {"job_id": job_id, "tier": self.project["tier"], "settings": self.settings(),
               "recipe": self._recipe_or_blank(),
               "next": "Poll get_render_progress or call wait_for_render."}
        if running:
            out["also_running"] = running
        if cost:
            out["cost"] = cost
        return out

    def progress(self, job_id: str) -> dict:
        job_id = _job_id(job_id)
        data = self.desk.json("GET", f"/api/jobs/{job_id}")
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = data.get("status")
                self._save()
        out = {k: data.get(k) for k in ("id", "status", "stage", "progress", "detail", "error", "tier", "seconds")}
        if data.get("video"):
            out["preview_url"] = self.desk.base + str(data["video"])
        return scrub(out)

    def wait(self, job_id: str, timeout_s: float = 300.0, poll_s: float = 3.0) -> dict:
        timeout_s = max(1.0, min(float(timeout_s), 780.0))
        end = time.monotonic() + timeout_s
        while True:
            state = self.progress(job_id)
            if state.get("status") in {"done", "error", "failed", "cancelled"}:
                if state.get("status") == "done":
                    state["output"] = self.output(job_id)
                return state
            if time.monotonic() >= end:
                state["detail"] = f"Still {state.get('stage')} after {timeout_s:.0f}s. Call wait_for_render again."
                return state
            time.sleep(max(0.2, poll_s))

    def cancel(self, job_id: str) -> dict:
        job_id = _job_id(job_id)
        data = self.desk.json("POST", f"/api/jobs/{job_id}/cancel", {})
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id]["status"] = data.get("status")
                self._save()
        return {"job_id": job_id, "status": data.get("status"), "detail": data.get("detail")}

    def videos(self, limit: int = 10) -> dict:
        limit = max(1, min(int(limit), 100))
        try:
            rows = self.desk.json("GET", f"/api/videos?limit={limit}").get("videos") or []
        except XenoformError:
            rows = []
        for row in rows:
            row["url"] = self.desk.base + str(row.get("url") or "")
            row.pop("recipe", None) if len(str(row.get("recipe") or "")) > 400 else None
        with self.lock:
            mine = [dict(v, job_id=k) for k, v in self.jobs.items()]
        return {"videos": rows, "this_session": mine[-limit:]}

    def output(self, job_id: str, save_to: str = "") -> dict:
        job_id = _job_id(job_id)
        url = f"/api/jobs/{job_id}/video"
        out: dict[str, Any] = {"job_id": job_id, "url": self.desk.base + url}
        local = self._local_path(job_id)
        if local:
            out["path"] = str(local)
        if save_to:
            dest = Path(save_to).expanduser()
            if dest.suffix.lower() != ".mp4":
                dest = dest / f"xenoform-{job_id}.mp4"
            out["saved_bytes"] = self.desk.download(url, dest)
            out["path"] = str(dest)
        elif not local:
            # The desk may run from another checkout; copy the file next to our state.
            dest = self.path.parent / "outputs" / f"xenoform-{job_id}.mp4"
            out["saved_bytes"] = self.desk.download(url, dest)
            out["path"] = str(dest)
        return out

    def _local_path(self, job_id: str) -> Path | None:
        roots = []
        try:
            from xenoform.ui import work_dir

            roots.append(work_dir())
        except Exception:
            pass
        roots.append(REPO / "work")
        for root in roots:
            file = Path(root) / "jobs" / job_id / "xenoform.mp4"
            if file.is_file():
                return file
        return None


INSTRUCTIONS = """You are connected to Xenoform, a local music-video app: a song drives a liquid, audio-reactive object that morphs on the beat, restyled by open-weights LTX on the user's own GPU (ComfyUI).
Workflow: get_status -> create_project (prompt, vibe) -> load_audio (optional; the demo track is used otherwise) -> update_settings -> start_render -> wait_for_render -> get_output.
Defaults: native 9:16 vertical, black background vibe, tier 'preview' (fast CPU animatic, no GPU model). 'draft' and 'final' use the GPU and take minutes; final is about 90 s per shot on 12 GB.
Spend rules: everything is open weights and free by default. Cloud quality is paid: never set cloud=true unless the user explicitly agreed to the cost, and then pass confirm_spend=true.
Best practice: preview first, show the user the preview_url, then draft/final. One GPU render at a time. Use the vibe's recommended transitions (list_vibes). Read xenoform://guide for vibes, transitions, tiers and recipes.
On first contact greet the user with "Connected to Xenoform, here's what you can do", offer 3-4 starters (e.g. "Make a 15 s neon-night morph to my track", "Show me the vibes and transitions", "Render a preview of the demo track in 9:16", "List my videos"), then ask what they want to make."""

EXAMPLES = """# Xenoform example requests
1. "Make a 9:16 black-vibe preview of the demo track"  -> create_project(prompt='chrome jellyfish', vibe='black') -> start_render -> wait_for_render
2. "Use my song C:\\Music\\track.wav, neon-night, dense energy" -> create_project(prompt=..., vibe='neon-night', energy='dense', audio_path=...)
3. "Start from this picture" -> attach_image('C:\\pics\\hero.png') then start_render
4. "Go final quality" -> update_settings(tier='final') -> start_render  (GPU, minutes)
5. "Stop that" -> cancel_render(job_id)
6. "What did I make?" -> list_videos -> get_output(job_id)
7. "Which settings does autotune use for ocean?" -> get_autotune_recipe('ocean')
"""


def register(server, app: App) -> None:
    """Add the Simple-path tools, prompts and resources to an MCPServer."""

    @server.tool()
    def get_status() -> dict:
        """Who am I talking to: desk health, ComfyUI connection, GPU tier, installed models / final-tier readiness, my recent jobs and the current project settings. Call this first."""
        return app.status()

    @server.tool()
    def list_vibes() -> dict:
        """List the vibes (looks) with their description, autotuned recipe, and recommended transitions."""
        return app.vibes()

    @server.tool()
    def list_shapes() -> dict:
        """List the morph shapes/forms in the catalogue (id, name, pack, blurb)."""
        return app.shapes()

    @server.tool()
    def list_transitions() -> dict:
        """List the transition types: in-shot morph transitions and whole-scene transitions, plus picks per vibe."""
        return app.transitions()

    @server.tool()
    def get_autotune_recipe(vibe: str = "") -> dict:
        """Autotune results (steps, cfg, compression, end strength). Pass a vibe for one recipe, empty for all."""
        return app.autotune(vibe)

    @server.tool()
    def get_settings() -> dict:
        """The current project settings that the next render will use."""
        return app.settings()

    @server.tool()
    def create_project(prompt: str = "", vibe: str = "black", aspect: str = "9:16", tier: str = "preview",
                       energy: str = "flow", audio_path: str = "", image_paths: list[str] | None = None) -> dict:
        """Start a new morph project from a one-line prompt and/or local images. vibe: liquid-gold, bloom, neon-night, ocean, cosmic, paper-summer, black. aspect: 9:16 (native, default), 16:9, 1:1. tier: preview (fast, no GPU), draft, final. energy: flow or dense. audio_path: optional local song; demo track otherwise."""
        return app.create(prompt, vibe, aspect, tier, energy, audio_path, image_paths)

    @server.tool()
    def update_settings(prompt: str | None = None, vibe: str | None = None, aspect: str | None = None,
                        vertical_mode: str | None = None, tier: str | None = None, energy: str | None = None,
                        transitions: list[str] | None = None, beat_fx: bool | None = None,
                        end_card: bool | None = None) -> dict:
        """Change any project setting. Omitted fields stay. vertical_mode: native (rendered in portrait), crop, auto. transitions: ids from list_transitions."""
        return app.update(prompt=prompt, vibe=vibe, aspect=aspect, vertical_mode=vertical_mode, tier=tier,
                          energy=energy, transitions=transitions, beat_fx=beat_fx, end_card=end_card)

    @server.tool()
    def load_audio(path: str) -> dict:
        """Upload a local song (wav, mp3, flac, ogg, aiff, m4a) to the desk and use it for the project. Returns duration and tempo."""
        return app.load_audio(path)

    @server.tool()
    def attach_image(path: str, role: str = "morph_target") -> dict:
        """Use a local image (png, jpg, webp). role morph_target (default): the object morphs through your images, in order, on draft/final. role first_frame: the picture opens every shot."""
        return app.attach_image(path, role)

    @server.tool()
    def start_render(cloud: bool = False, confirm_spend: bool = False) -> dict:
        """Render the project with the current settings. Free open weights by default. cloud=true is PAID and also needs confirm_spend=true after the user agrees to the cost."""
        return app.start(cloud=cloud, confirm_spend=confirm_spend)

    @server.tool()
    def get_render_progress(job_id: str) -> dict:
        """Status of a render: status, stage, progress 0-1, detail, and preview_url once a frame is watchable."""
        return app.progress(job_id)

    @server.tool()
    def wait_for_render(job_id: str, timeout_s: float = 300) -> dict:
        """Block until the render finishes or timeout_s passes (max 780). Returns the output path when done."""
        return app.wait(job_id, timeout_s)

    @server.tool()
    def cancel_render(job_id: str) -> dict:
        """Cancel a running render."""
        return app.cancel(job_id)

    @server.tool()
    def list_videos(limit: int = 10) -> dict:
        """List finished videos on this PC (newest first) and the renders started in this session."""
        return app.videos(limit)

    @server.tool()
    def get_output(job_id: str, save_to: str = "") -> dict:
        """Path and URL of a finished render. save_to (a folder or .mp4 path) copies it there."""
        return app.output(job_id, save_to)

    @server.tool()
    def encode_recipe() -> dict:
        """A short shareable recipe code for the current settings: xf1.? or, with transitions or shot edits, xf2.? (both remix). Every render's code also shows in My videos."""
        return app.encode_recipe()

    @server.tool()
    def decode_recipe(code: str) -> dict:
        """Read a recipe code back into its settings (vibe, idea, aspect, seed, energy...)."""
        return app.decode_recipe(code)

    @server.tool()
    def remix_recipe(code: str, prompt: str | None = None, vibe: str | None = None, aspect: str | None = None,
                     tier: str | None = None) -> dict:
        """Load a recipe code into the project, optionally overriding prompt/vibe/aspect/tier, ready to render."""
        return app.remix(code, prompt, vibe, aspect, tier)

    @server.tool()
    def get_audio_analysis() -> dict:
        """Beats, tempo, drops and sections of the project's song."""
        return app.analysis()

    @server.tool()
    def get_cut_timeline() -> dict:
        """The cut as an editor sees it: each shot's start/end, hold, form, transition, energy, and how far its cut sits off the nearest beat."""
        return app.timeline()

    @server.tool()
    def apply_edit_list(edits: list[dict]) -> dict:
        """Re-cut: a list of edits applied in order, e.g. [{"index":2,"hold":1.0,"transition":"snap"},{"op":"delete","index":4},{"op":"append","form":"sphere"}]. ops: set (default), append, delete. Returns the new timeline; render to see it."""
        return app.apply_edits(edits)

    @server.prompt()
    def review_cut() -> str:
        """AI director: review pacing like an editor and propose a re-cut."""
        return ("Act as a music-video editor. Call get_audio_analysis, get_cut_timeline and get_frames (contact sheet), "
                "and run_review for the built-in critique. Judge pacing against the beats, drops and sections: cuts off the beat, "
                "shots that overstay, energy that does not match the section, repeated transitions. Propose a short edit list "
                "with reasons, apply it with apply_edit_list only after I agree, then render a preview.")

    @server.prompt()
    def get_started() -> str:
        """Onboarding: check the setup, greet, and offer starters."""
        return ("Call get_status and list_vibes. Then greet me with 'Connected to Xenoform, here's what you can do', "
                "summarise in two lines what my PC can render (GPU tier, whether final quality is ready), "
                "offer 4 starter ideas that fit those vibes, and ask what I want to make. Keep it short.")

    @server.prompt()
    def make_music_video(idea: str, vibe: str = "black", song_path: str = "") -> str:
        """Make a music video end to end: preview first, then final on approval."""
        song = f" Load my song from {song_path}." if song_path else " Use the demo track."
        return (f"Make a Xenoform music video. Idea: {idea}. Vibe: {vibe}. Native 9:16.{song} "
                "Use the vibe's recommended transitions. Render a preview, wait for it, give me the preview link, "
                "and ask before you render draft or final. Never use cloud quality unless I say so.")

    @server.resource("xenoform://guide", mime_type="text/markdown", description="How Xenoform works: vibes, transitions, tiers, recipes.")
    def guide_resource() -> str:
        return read_guide()

    @server.resource("xenoform://examples", mime_type="text/markdown", description="Example requests and the tool calls behind them.")
    def examples_resource() -> str:
        return EXAMPLES

    @server.resource("xenoform://vibes", mime_type="application/json", description="Vibes with looks and autotune recipes.")
    def vibes_resource() -> str:
        return json.dumps(app.vibes())

    @server.resource("xenoform://settings", mime_type="application/json", description="Current project settings.")
    def settings_resource() -> str:
        return json.dumps(app.settings())
