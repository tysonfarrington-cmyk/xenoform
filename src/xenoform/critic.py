"""Fresh-eyes critic.

It sees the picture, the audio meter, and the beat clock. It does not read
the storyboard, the prompts, the recipe, or a guide strength. ``measure`` is
the pure pass: numpy frames in, a verdict out. ``fresh_eyes`` is the pass
that samples a file for itself.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

from xenoform.notes import harding_flash_rate

_SPECS = {
    "live": (384, 216, 12.0),
    "turbo": (384, 216, 12.0),
    "draft": (512, 288, 12.0),
    "final": (640, 360, 24.0),
}

_STILL = 3.0
_CUT = 18.0


def delivery_spec(quality: str, *, height: int | None = None, duration: float | None = None) -> dict[str, Any]:
    """The measured bar for a tier. Turbo's animatic is 384×216; the video pass is 384×224."""
    name = str(quality or "turbo")
    if name == "turbo" and height == 224:
        width, height_px, fps = 384, 224, 12.0
    else:
        width, height_px, fps = _SPECS.get(name, _SPECS["turbo"])
    spec: dict[str, Any] = {"quality": name, "width": width, "height": height_px, "fps": fps}
    if duration:
        spec["duration"] = float(duration)
    return spec


def _problem(check: str, t: float, plain: str, rank: int) -> dict[str, Any]:
    return {"id": check, "t": round(float(t), 3), "plain": plain, "rank": rank, "op": {}}


def _bar(check: str, measured: bool, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": check, "measured": bool(measured), "pass": bool(passed) if measured else True, "detail": detail}


def _relative(rgb: np.ndarray) -> np.ndarray:
    sample = np.clip(rgb.astype(np.float64) / 255.0, 0.0, 1.0)
    low = sample <= 0.04045
    linear = np.where(low, sample / 12.92, ((sample + 0.055) / 1.055) ** 2.4)
    return 0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]


def _text_on(frame: np.ndarray) -> dict[str, Any]:
    """A caption is a band flatter than the middle of the frame. Otherwise there is no text."""
    height, width = frame.shape[:2]
    if height < 8 or width < 8:
        return {"text": False, "contrast": None, "margins": True}
    y0 = int(height * 0.82)
    band = frame[y0:]
    center = frame[int(height * 0.30) : int(height * 0.70)]
    if center.size == 0 or band.size == 0:
        return {"text": False, "contrast": None, "margins": True}
    band_std = float(band.astype(np.float64).std())
    center_std = float(center.astype(np.float64).std())
    if band_std >= center_std:
        return {"text": False, "contrast": None, "margins": True}
    rel = _relative(band)
    median = float(np.median(rel))
    ink = rel <= median
    paper = ~ink
    if not ink.any() or not paper.any():
        return {"text": True, "contrast": 1.0, "margins": False}
    lighter = max(float(rel[ink].mean()), float(rel[paper].mean()))
    darker = min(float(rel[ink].mean()), float(rel[paper].mean()))
    ratio = (lighter + 0.05) / (darker + 0.05)
    ys, xs = np.where(ink)
    ys = ys + y0
    margin_x = 0.05 * width
    margin_y = 0.05 * height
    inside = bool(
        xs.min() >= margin_x
        and xs.max() <= (width - 1) - margin_x
        and ys.min() >= margin_y
        and ys.max() <= (height - 1) - margin_y
    )
    return {"text": True, "contrast": float(ratio), "margins": inside}


def _sheet(frames: np.ndarray | None, times: np.ndarray | None) -> tuple[np.ndarray | None, np.ndarray | None]:
    if frames is None or len(frames) < 2:
        return None, None
    clock = np.asarray(times if times is not None else np.arange(len(frames)) * 0.5, dtype=np.float64)
    if len(clock) != len(frames):
        clock = np.arange(len(frames), dtype=np.float64) * 0.5
    end = float(clock[-1])
    targets = np.arange(0.0, end + 1e-6, 0.5)
    if len(targets) < 2:
        targets = np.array([float(clock[0]), end])
    chosen: list[int] = []
    for target in targets:
        index = int(np.argmin(np.abs(clock - float(target))))
        if index not in chosen:
            chosen.append(index)
    if len(chosen) < 2:
        return None, None
    return frames[chosen], clock[chosen]


def _retell(sheet: np.ndarray | None, times: np.ndarray | None) -> tuple[bool, str]:
    if sheet is None or len(sheet) < 2:
        return False, "The silent sheet does not carry a story."
    luma = sheet.astype(np.float64).mean(axis=(1, 2, 3))
    diffs = np.mean(np.abs(sheet[1:].astype(np.float64) - sheet[:-1].astype(np.float64)), axis=(1, 2, 3))
    change = abs(float(luma[-1] - luma[0]))
    peak_index = int(np.argmax(diffs)) if len(diffs) else 0
    peak = float(diffs[peak_index]) if len(diffs) else 0.0
    readable = change >= 8.0 or (peak >= 6.0 and peak_index > 0)
    if not readable:
        return False, "The silent sheet does not carry a story."

    def tone(value: float) -> str:
        if value < 40:
            return "dark"
        if value > 140:
            return "bright"
        return "mid"

    clock = np.asarray(times if times is not None else np.arange(len(sheet)) * 0.5, dtype=np.float64)
    when = float(clock[min(peak_index + 1, len(clock) - 1)])
    return True, f"It opens {tone(float(luma[0]))}, the movement lands near {when:.2f}s, and it closes {tone(float(luma[-1]))}."


def measure(
    frames: np.ndarray | None,
    times: np.ndarray | None = None,
    *,
    spec: dict | None = None,
    actual: dict | None = None,
    beats: list[float] | None = None,
    loudness: dict | None = None,
    prior_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Score a picture the critic sampled itself. No storyboard is read here."""
    spec = dict(spec or {})
    actual = dict(actual or {})
    clock = None
    if frames is not None and len(frames):
        clock = np.asarray(times if times is not None else np.arange(len(frames), dtype=np.float64) / float(spec.get("fps") or 12), dtype=np.float64)
        if len(clock) != len(frames):
            clock = np.arange(len(frames), dtype=np.float64) / float(spec.get("fps") or 12)
    problems: list[dict] = []
    bar: list[dict] = []
    has_frames = frames is not None and len(frames) > 0
    file_fps = float(actual.get("fps") or spec.get("fps") or 24.0) or 24.0

    if not has_frames:
        problems.append(_problem("no-picture", 0.0, "There is no picture to review.", 1))

    if spec.get("duration") is not None and actual.get("duration") is not None:
        tolerance = 1.0 / max(file_fps, 1.0)
        gap = abs(float(actual["duration"]) - float(spec["duration"]))
        ok = gap <= tolerance + 1e-3
        bar.append(_bar("duration", True, ok, f"{float(actual['duration']):.3f}s against {float(spec['duration']):.3f}s"))
        if not ok:
            problems.append(_problem("duration", 0.0, f"The picture is {float(actual['duration']):.2f}s. The delivery is {float(spec['duration']):.2f}s.", 14))
    else:
        bar.append(_bar("duration", False, True, "Duration was not measured."))

    if actual.get("width") and actual.get("height") and spec.get("width") and spec.get("height"):
        ok = int(actual["width"]) == int(spec["width"]) and int(actual["height"]) == int(spec["height"])
        bar.append(_bar("size", True, ok, f"{int(actual['width'])}×{int(actual['height'])}"))
        if not ok:
            problems.append(
                _problem(
                    "size",
                    0.0,
                    f"The picture is {int(actual['width'])}×{int(actual['height'])}. This tier is {int(spec['width'])}×{int(spec['height'])}.",
                    14,
                )
            )
    else:
        bar.append(_bar("size", False, True, "Size was not measured."))

    if actual.get("fps") and spec.get("fps"):
        ok = abs(float(actual["fps"]) - float(spec["fps"])) <= 0.05
        bar.append(_bar("fps", True, ok, f"{float(actual['fps']):.3f} fps"))
        if not ok:
            problems.append(_problem("fps", 0.0, f"The picture is {float(actual['fps']):.2f} fps. This tier is {float(spec['fps']):.2f}.", 14))
    else:
        bar.append(_bar("fps", False, True, "Frame rate was not measured."))

    if has_frames:
        first = frames[0].astype(np.float64)
        mean = float(first.mean())
        spread = float(first.std())
        ok = mean > 12.0 and spread > 4.0
        bar.append(_bar("frame-one", True, ok, f"luma {mean:.1f}, spread {spread:.1f}"))
        if not ok:
            problems.append(_problem("frame-one", float(clock[0]), "Frame 1 is not a finished picture.", 6))

        if len(frames) > 1:
            diffs = np.mean(np.abs(frames[1:].astype(np.float64) - frames[:-1].astype(np.float64)), axis=(1, 2, 3))
        else:
            diffs = np.zeros(0, dtype=np.float64)
        low = diffs < _STILL
        frozen = 0.0
        worst = 0.0
        worst_t = float(clock[0])
        cursor = 0
        cut_times: list[float] = []
        while cursor < len(low):
            if not low[cursor]:
                if float(diffs[cursor]) >= _CUT:
                    cut_times.append(float(clock[cursor + 1]))
                cursor += 1
                continue
            end = cursor
            while end < len(low) and low[end]:
                end += 1
            span = float(clock[end] - clock[cursor])
            frozen += max(0.0, span)
            if span > worst:
                worst = span
                worst_t = float(clock[cursor])
            cursor = end
        duration = float(actual.get("duration") or 0.0)
        if duration <= 0 and len(clock) > 1:
            duration = float(clock[-1] - clock[0])
        budget = duration / 30.0 if duration else 0.0
        still_ok = worst <= 0.5 + 1e-6 and frozen <= budget + 1e-6
        bar.append(_bar("still-stretch", True, still_ok, f"longest {worst:.2f}s, frozen {frozen:.2f}s"))
        if not still_ok:
            problems.append(
                _problem(
                    "still-stretch",
                    worst_t,
                    f"A still holds for {worst:.2f}s at {worst_t:.2f}s. The bar is half a second, and under a second frozen in every thirty.",
                    7,
                )
            )

        beat_clock = [float(beat) for beat in (beats or [])]
        if not beat_clock:
            bar.append(_bar("cut-beat", True, True, "No beat clock, so cut alignment was not scored."))
        else:
            tolerance = 1.0 / max(file_fps, 1.0)
            late = [cut for cut in cut_times if min(abs(cut - beat) for beat in beat_clock) > tolerance + 1e-4]
            ok = not late
            bar.append(_bar("cut-beat", True, ok, f"{len(cut_times)} cuts, {len(late)} off the beat"))
            if late:
                problems.append(
                    _problem(
                        "cut-beat",
                        late[0],
                        f"A cut at {late[0]:.2f}s misses the beat by more than one frame.",
                        8,
                    )
                )

        step = max(1, len(frames) // 5)
        notes = [_text_on(frame) for frame in frames[::step]]
        captions = [note for note in notes if note["text"]]
        if not captions:
            bar.append(_bar("contrast", True, True, "No text."))
            bar.append(_bar("margins", True, True, "No text."))
        else:
            worst_ratio = min(float(note["contrast"] or 0) for note in captions)
            contrast_ok = worst_ratio >= 4.5
            margins_ok = all(note["margins"] for note in captions)
            bar.append(_bar("contrast", True, contrast_ok, f"{worst_ratio:.2f}:1"))
            bar.append(_bar("margins", True, margins_ok, "Inside the safe margins." if margins_ok else "Text leaves the safe margins."))
            if not contrast_ok:
                problems.append(_problem("contrast", 0.0, f"Text contrast is {worst_ratio:.2f}:1. The bar is 4.5:1.", 11))
            if not margins_ok:
                problems.append(_problem("margins", 0.0, "Text sits outside the safe margins.", 11))

        rate = file_fps
        if len(clock) > 2:
            step = float(np.median(np.diff(clock)))
            if step > 1e-4:
                rate = 1.0 / step
        flashes = harding_flash_rate(frames, rate)
        harding_ok = flashes <= 3
        bar.append(_bar("harding", True, harding_ok, f"{flashes:.0f} opposing flashes in a second"))
        if not harding_ok:
            problems.append(_problem("harding", 0.0, f"The picture flashes {flashes:.0f} times in a second. The gate allows 3.", 9))
    else:
        for check, detail in (
            ("frame-one", "Frame 1 was not measured."),
            ("still-stretch", "Motion was not measured."),
            ("cut-beat", "Cuts were not measured."),
            ("contrast", "Text was not measured."),
            ("margins", "Margins were not measured."),
            ("harding", "The flash gate was not measured."),
        ):
            bar.append(_bar(check, False, True, detail))

    if loudness and loudness.get("measured"):
        integrated = loudness.get("integrated")
        if integrated is None:
            bar.append(_bar("loudness", False, True, "Integrated loudness was not measured."))
        else:
            ok = -16.0 <= float(integrated) <= -12.0
            bar.append(_bar("loudness", True, ok, f"{float(integrated):.1f} LUFS"))
            if not ok:
                problems.append(_problem("loudness", 0.0, f"Loudness is {float(integrated):.1f} LUFS. The bar is about -14.", 12))
        peak = loudness.get("true_peak")
        if peak is None:
            bar.append(_bar("peak", False, True, "True peak was not measured."))
        else:
            ok = float(peak) <= -1.0 + 1e-6
            bar.append(_bar("peak", True, ok, f"{float(peak):.2f} dBTP"))
            if not ok:
                problems.append(_problem("peak", 0.0, f"True peak is {float(peak):.2f} dBTP. The bar is -1.", 12))
        sample = loudness.get("sample_peak")
        if sample is None:
            bar.append(_bar("clipping", False, True, "Sample peak was not measured."))
        else:
            ok = float(sample) < 0.999
            bar.append(_bar("clipping", True, ok, f"sample peak {float(sample):.3f}"))
            if not ok:
                problems.append(_problem("clipping", 0.0, "The audio clips.", 12))
    else:
        bar.append(_bar("loudness", False, True, "Loudness was not measured."))
        bar.append(_bar("peak", False, True, "True peak was not measured."))
        bar.append(_bar("clipping", False, True, "Clipping was not measured."))

    sheet, sheet_times = _sheet(frames if has_frames else None, clock)
    readable, retelling = _retell(sheet, sheet_times)
    if not readable:
        problems.append(_problem("story-unclear", 0.0, "With the sound off, the story does not read.", 2))

    problems.sort(key=lambda row: (int(row["rank"]), float(row["t"]), row["id"]))
    current = {row["id"] for row in problems}
    rechecked = [
        {"id": str(item), "status": "open" if str(item) in current else "cleared"}
        for item in (prior_ids or [])
        if str(item)
    ]
    failed = [item["id"] for item in bar if item["measured"] and not item["pass"]]
    verdict = "ship" if not problems and not failed else "one more pass"
    return {
        "verdict": verdict,
        "problems": problems,
        "bar": bar,
        "sound_off": {"readable": readable, "retelling": retelling, "fps": 2},
        "retelling": retelling,
        "rechecked": rechecked,
    }


def next_fix(findings: list[dict]) -> dict | None:
    """The biggest problem that the board can actually change."""
    rows = [row for row in findings or [] if (row.get("op") or {}).get("op")]
    rows.sort(key=lambda row: (int(row.get("rank") or 50), str(row.get("id") or "")))
    return rows[0] if rows else None


def _parse_loudness(text: str) -> tuple[float | None, float | None]:
    """Integrated loudness and the summary true peak. Progress lines are ignored."""
    summary = text.split("Summary:", 1)[-1] if "Summary:" in text else ""
    integrated = None
    true_peak = None
    seen_peak = False
    for line in summary.splitlines():
        stripped = line.strip()
        if stripped.startswith("I:"):
            try:
                integrated = float(stripped.split()[1])
            except (IndexError, ValueError):
                continue
        if stripped.startswith("True peak"):
            seen_peak = True
            continue
        if seen_peak and stripped.startswith("Peak:"):
            parts = stripped.replace(":", " ").split()
            for part in parts:
                try:
                    true_peak = float(part)
                    break
                except ValueError:
                    continue
            break
    return integrated, true_peak


def read_loudness(path: Path | None) -> dict | None:
    """Integrated loudness, true peak, and sample peak. A failed meter is unmeasured, not a fail."""
    if path is None or not Path(path).exists():
        return None
    from xenoform.video import ffmpeg_bin

    try:
        proc = subprocess.run(
            [ffmpeg_bin(), "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")
    integrated, true_peak = _parse_loudness(text)
    sample_peak = None
    try:
        pcm = subprocess.run(
            [ffmpeg_bin(), "-v", "error", "-i", str(path), "-ac", "1", "-t", "30", "-f", "f32le", "-"],
            capture_output=True,
            timeout=60,
        )
        if pcm.returncode == 0 and pcm.stdout:
            samples = np.frombuffer(pcm.stdout, dtype=np.float32)
            if samples.size:
                sample_peak = float(np.max(np.abs(samples)))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        sample_peak = None
    if integrated is None and true_peak is None and sample_peak is None:
        return None
    return {"measured": True, "integrated": integrated, "true_peak": true_peak, "sample_peak": sample_peak}


def _decode(path: Path, fps: float, width: int, height: int, limit: int, ss: float = 0.0) -> tuple[np.ndarray | None, np.ndarray | None]:
    from xenoform.video import ffmpeg_bin

    cmd = [ffmpeg_bin(), "-v", "error"]
    if ss > 0:
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += [
        "-i",
        str(path),
        "-vf",
        f"fps={fps},scale={width}:{height}",
        "-frames:v",
        str(max(1, limit)),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    frame = width * height * 3
    if proc.returncode != 0 or len(proc.stdout) < frame:
        return None, None
    count = len(proc.stdout) // frame
    frames = np.frombuffer(proc.stdout[: count * frame], dtype=np.uint8).reshape(count, height, width, 3).copy()
    times = ss + (np.arange(count, dtype=np.float64) / float(fps))
    return frames, times


def _sample_index(times: np.ndarray, target: float) -> int:
    return int(np.argmin(np.abs(times - float(target))))


def _select(frames: np.ndarray, times: np.ndarray, indexes: list[int]) -> tuple[np.ndarray, np.ndarray]:
    order = sorted(set(indexes))
    return frames[order], times[order]


def fresh_eyes(
    video: Path | None,
    audio: Path | None,
    spec: dict | None = None,
    beats: list[float] | None = None,
    prior_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Sample the file on a 0.2s grid, denser around cuts. The storyboard is not an input."""
    spec = dict(spec or delivery_spec("turbo"))
    loudness = read_loudness(Path(audio) if audio else None)
    path = Path(video) if video else None
    if path is None or not path.exists():
        return measure(None, None, spec=spec, actual={}, beats=beats, loudness=loudness, prior_ids=prior_ids)

    from xenoform.video import probe_video

    try:
        info = probe_video(path)
    except (OSError, subprocess.CalledProcessError, KeyError, ValueError, IndexError):
        return measure(None, None, spec=spec, actual={}, beats=beats, loudness=loudness, prior_ids=prior_ids)
    fps = float(info.get("fps") or 0) or float(spec.get("fps") or 12)
    frames_n = int(info.get("frames") or 0)
    duration = frames_n / fps if fps and frames_n else float(spec.get("duration") or 0)
    duration = min(duration, 120.0) if duration else 0.0
    actual = {"width": int(info["width"]), "height": int(info["height"]), "fps": fps, "duration": duration}
    if duration <= 0:
        return measure(None, None, spec=spec, actual=actual, beats=beats, loudness=loudness, prior_ids=prior_ids)

    rate = 20.0 if duration <= 12.0 else 5.0
    limit = int(duration * rate) + 2
    decoded, decoded_times = _decode(path, rate, 160, 90, limit)
    if decoded is None or decoded_times is None:
        return measure(None, None, spec=spec, actual=actual, beats=beats, loudness=loudness, prior_ids=prior_ids)

    base: list[int] = []
    cursor = 0.0
    while cursor <= float(decoded_times[-1]) + 1e-6:
        base.append(_sample_index(decoded_times, cursor))
        cursor += 0.2
    base_frames, base_times = _select(decoded, decoded_times, base)
    dense = list(base)
    if len(base_frames) > 1:
        diffs = np.mean(np.abs(base_frames[1:].astype(np.float64) - base_frames[:-1].astype(np.float64)), axis=(1, 2, 3))
        cuts = [float(base_times[index + 1]) for index, value in enumerate(diffs) if float(value) >= _CUT]
        for cut in cuts[:24]:
            step = 0.0
            while step <= 0.1 + 1e-9:
                for sign in (-1.0, 1.0):
                    target = cut + sign * step
                    if target < 0:
                        continue
                    if rate >= 20.0:
                        dense.append(_sample_index(decoded_times, target))
                    else:
                        extra, extra_times = _decode(path, 20.0, 160, 90, 1, ss=max(0.0, target))
                        if extra is not None and extra_times is not None:
                            decoded = np.concatenate([decoded, extra], axis=0)
                            decoded_times = np.concatenate([decoded_times, extra_times])
                            dense.append(len(decoded_times) - 1)
                step += 0.05
    sample, sample_times = _select(decoded, decoded_times, dense if rate >= 20.0 else base)
    if rate < 20.0 and len(decoded) > len(base_frames):
        sample, sample_times = decoded, decoded_times
        order = np.argsort(sample_times)
        sample, sample_times = sample[order], sample_times[order]
    return measure(sample, sample_times, spec=spec, actual=actual, beats=beats, loudness=loudness, prior_ids=prior_ids)
