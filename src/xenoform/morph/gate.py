"""The morph gate. A join fails if it invents a subject or leaves the beat."""

from __future__ import annotations

import re

from xenoform.eligibility import audit_graph, local_text_encoder
from xenoform.hardware import FAST_CHECKPOINT
from xenoform.storyboard import _ARTICLES, _PLACE_PREP, _PREP

_METHODS = ("v2v-ramp", "region-staged", "keyframe-blend", "cross-clip")
_STOP = frozenset("a an the of to from into and or with at on in is are was be this that for its it".split())
_SCAFFOLD = frozenset(
    "photoreal side body smoothly reshaping mid stride same camera lighting continuous its".split()
)
_SEED = 2727


def nouns(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {word for word in words if word not in _STOP and len(word) > 2}


def _beat_limit(beats: list | None) -> float:
    """Half a beat. A section cut may sit between the grid and still land on the nearest beat."""
    clock: list[float] = []
    for beat in beats or []:
        try:
            clock.append(float(beat))
        except (TypeError, ValueError):
            continue
    clock = sorted(set(clock))
    if len(clock) < 2:
        return 0.1
    gaps = [right - left for left, right in zip(clock, clock[1:]) if right > left]
    if not gaps:
        return 0.1
    gaps.sort()
    return max(0.1, gaps[len(gaps) // 2] / 2.0)


def _content(text: str) -> set[str]:
    return nouns(text) - _SCAFFOLD - _ARTICLES - _PREP - _PLACE_PREP


def _checkpoint_problem(plan: dict) -> str:
    name = str(plan.get("checkpoint") or "")
    folded = name.lower()
    if not name or "wan" in folded:
        return "Wrong picture model."
    fast_file = name == FAST_CHECKPOINT or "0.9.5" in folded
    quality_file = "2.3" in folded or "ltx-23" in folded or "22b" in folded
    if plan.get("fast") and not fast_file:
        return "Fast morphs stay on LTX 0.9.5."
    if not fast_file and not quality_file:
        return "Wrong picture model."
    return ""


def review(plan: dict, beats: list | None = None) -> dict:
    """Pass only when the blend stays inside the two shots."""
    reasons: list[str] = []
    method = str(plan.get("method") or "")
    if method not in _METHODS:
        reasons.append("Unknown blend.")
    width = int(plan.get("width") or 0)
    height = int(plan.get("height") or 0)
    if width % 32 or height % 32:
        reasons.append("Picture size is off the 32 grid.")
    if int(plan.get("seed") or 0) != _SEED:
        reasons.append("Seed moved.")
    checkpoint_problem = _checkpoint_problem(plan)
    if checkpoint_problem:
        reasons.append(checkpoint_problem)
    prompt = str(plan.get("prompt") or "")
    prompt_low = prompt.lower()
    subject_b = [word for word in str(plan.get("subject_b") or "").split() if word not in _ARTICLES]
    if not subject_b or any(re.search(rf"\b{re.escape(word)}\b", prompt_low) is None for word in subject_b):
        reasons.append("The second subject is missing.")
    allowed = set(plan.get("cast") or plan.get("nouns") or [])
    extra = _content(prompt) - allowed
    if extra:
        reasons.append("The blend names something neither shot shows.")
    if plan.get("region"):
        region_words = nouns(str(plan.get("region")))
        if region_words and not region_words <= allowed and str(plan.get("region")) not in ("subject",):
            # A region may be the form word already counted, or the word "subject".
            if region_words - allowed - {"subject"}:
                reasons.append("The region is not in either shot.")
    drift = float(plan.get("drift") or 0)
    if beats and drift > _beat_limit(beats):
        reasons.append("The blend is off the beat.")
    samples = int(plan.get("samples") or 0)
    if method in ("keyframe-blend", "cross-clip") and samples != 0:
        reasons.append("This blend should mix frames, not sample new ones.")
    if method in ("v2v-ramp", "region-staged"):
        strength = plan.get("strength") or [0, 0]
        if any(float(value) > 0.35 for value in strength):
            reasons.append("The blend is strong enough to invent a frame.")
    workflow = plan.get("workflow") or {}
    if workflow:
        reasons.extend(audit_graph(workflow, "morph"))
        if method in ("v2v-ramp", "region-staged") and not local_text_encoder(workflow):
            reasons.append("Prompt encoding is not local.")
        if method in ("keyframe-blend", "cross-clip"):
            kinds = _class_types(workflow)
            if "SamplerCustomAdvanced" in kinds:
                reasons.append("A frame mix must not sample.")
    return {"pass": not reasons, "reasons": reasons}


def _class_types(data: object) -> set[str]:
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            kind = node.get("class_type")
            if isinstance(kind, str):
                found.add(kind)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found
