"""The flash tame (docs/MUSIC_VIDEO_PLAN.md section 3; Tys, 30 Oct 3:15 pm: "we also need to tone down the white flashing
light. its already pretty intense so that has to be used sparingly and subtly").

The demo's ``docs/demo/tools/deflash.py`` ported into the compose path, as the last pass over the picture before it is
encoded (``beatfx.compose``'s ``tame``): a frame is a flash when its mean luma stands more than ``THRESH`` levels above the
darker of the darkest of the ``N`` frames before it and the darkest of the ``N`` after (a cut from a dark shot into a
bright one is a step, level with the frames after it, and is left alone). A flash is read as a white veil over the
picture; the veil is lifted and ``keep`` of it laid back, the frame's brightness pinned so it never goes under its
ground: the beat still pulses, subtly.

``Tame`` runs as the frames stream to the encoder, ``AHEAD`` frames behind them, each frame with the rule of the passage
it sits in (``pacing.flash_rules``: none in the intro and the outro, a few in the calm, rising through a build, capped
in the drops): the share of a flash it keeps, and how many flash frames an 8-bar window of it may hold before the next
one is tamed under the threshold. It decides a frame as the test will read the result: a beat pulse lasts several
frames, and taming its middle leaves its edges standing over the lowered frames, so it settles the whole pulse ahead
(the test run again over what it would write, until nothing in it stands over the line) before it lets the first
frame go. ``flash_frames`` is the same test on a luma series, for the QA report (``post_qa``).
"""
from __future__ import annotations

from collections import deque

import numpy as np

THRESH = 6.0   # luma levels (limited range, as ffmpeg's YAVG reads an encoded frame) above the ground
N = 5          # frames each side
KEEP = 0.35    # the share of a flash's veil laid back (the demo's)
VEIL_MAX = 0.6
AHEAD = 4 * N  # frames the tame looks ahead: a beat pulse (the test's ground is N frames each side of it) and its ground
MARGIN = 1.0   # levels under the line the tame already treats as a flash: the encode moves a frame's mean by about one


def luma(frame: np.ndarray) -> float:
    """A frame's mean luma as an encoded yuv420p frame's Y plane reads it (BT.601, limited range 16..235)."""
    small = np.asarray(frame)[::4, ::4, :3].astype(np.float32)
    return float((16.0 + small[..., 0] * 0.2568 + small[..., 1] * 0.5041 + small[..., 2] * 0.0979).mean())


def flash_frames(y, thresh: float = THRESH, n: int = N) -> np.ndarray:
    """True for every frame of the luma series ``y`` that the test calls a flash (a frame within ``n`` of either end has
    no ground on one side and never is)."""
    y = np.asarray(list(y), dtype=np.float64)
    out = np.zeros(len(y), dtype=bool)
    for i in range(n, len(y) - n):
        base = max(y[i - n:i].min(), y[i + 1:i + 1 + n].min())
        out[i] = bool(y[i] > base + thresh and y[i] > 1)
    return out


def per_window(flags, window: int) -> list[int]:
    """Flash frames in each window of ``window`` frames, from the first frame."""
    f = np.asarray(flags, dtype=bool)
    w = max(1, int(window))
    return [int(f[i:i + w].sum()) for i in range(0, len(f), w)]


def lift(frame: np.ndarray, y: float, base: float, keep: float) -> np.ndarray:
    """One flash frame tamed: the veil ``(y - base) / (255 - base)`` lifted, ``keep`` of it laid back, and the frame's
    luma pinned to its ground plus ``keep`` of the rise: blended back toward the original where the veil model went too
    dark (on the montage it over-darkened frames under their neighbours, a dark blink instead of a flash), dimmed by a
    gain where a veil past ``VEIL_MAX`` left it too bright (so an empty budget really is no flash)."""
    v = min(VEIL_MAX, (y - base) / max(1.0, 255.0 - base))
    if v <= 1e-4:
        return frame
    orig = frame.astype(np.float32)
    clean = (orig - 255.0 * v) / (1.0 - v)
    lifted = np.clip(clean * (1.0 - keep * v) + 255.0 * keep * v, 0, 255)
    target = base + keep * (y - base)
    have = luma(lifted)
    if have > target + 0.25:  # still too bright: the rest by a gain (luma is 16 plus a share of the RGB)
        lifted = np.clip(lifted * ((target - 16.0) / max(1e-3, have - 16.0)), 0, 255)
    elif have < target - 0.25 and y - have > 1e-3:  # too dark: the original laid back over it, to the target
        a = float(np.clip((y - target) / (y - have), 0.0, 1.0))
        lifted = a * lifted + (1.0 - a) * orig
    return np.clip(lifted + 0.5, 0, 255).astype(np.uint8)


class Tame:
    """The flash tame as frames stream to the encoder: ``push(frame, rule)`` returns the frames it has now decided (it
    runs ``ahead`` behind), ``flush()`` the rest. ``rule`` is ``(keep, budget, window)`` for the frame: the share of a flash
    kept, the flash frames its window may hold, and the window in frames; None leaves the frame alone (it is still
    ground for its neighbours)."""

    def __init__(self, thresh: float = THRESH, n: int = N, ahead: int = AHEAD, margin: float = MARGIN) -> None:
        self.thresh, self.n, self.margin = float(thresh), int(n), float(margin)
        self.ahead = max(int(ahead), 2 * self.n)
        self.frames: deque = deque()
        self.lumas: deque = deque()
        self.rules: deque = deque()
        self.before: deque = deque(maxlen=self.n)  # the decided frames' lumas as written: the ground the next stands on
        self.kept: deque = deque()                 # frame numbers of the flashes left over the threshold, in the window
        self.count = 0
        self.flashes = 0
        self.tamed = 0
        self.kept_total = 0

    def push(self, frame: np.ndarray, rule: tuple | None) -> list[np.ndarray]:
        self.frames.append(frame)
        self.lumas.append(luma(frame))
        self.rules.append(rule)
        out = []
        while len(self.frames) > self.ahead:
            out.append(self._decide())
        return out

    def flush(self) -> list[np.ndarray]:
        out = []
        while self.frames:
            out.append(self._decide())
        return out

    def _room(self, i: int, rule: tuple) -> bool:
        """True when the oldest frame's window may still hold a flash (its budget not spent in the last ``window``)."""
        budget, window = rule[1], int(rule[2] or 0)
        while self.kept and window and self.kept[0] <= i - window:
            self.kept.popleft()
        return budget is None or len(self.kept) < int(budget)

    def _settle(self, i: int) -> tuple[float, float, bool] | None:
        """The oldest buffered frame's luma once the pulse around it settles: the test run over the decided ground and
        the buffer, every flash in it brought under the line (the oldest keeps its share when its window has room),
        again until nothing in it stands over the line. ``(luma, ground, kept)``, or None to leave the frame as it is.
        A frame needs ``n`` frames each side to be judged (the buffer's last ``n`` wait for more)."""
        n, t = self.n, self.thresh
        before = list(self.before)
        if len(before) < n or self.rules[0] is None:
            return None
        z = before + list(self.lumas)
        rules = [None] * len(before) + list(self.rules)
        off = len(before)
        oldest = None
        kept = False
        for _ in range(4 * n + 4):
            moved = False
            for j in range(off, len(z) - n):
                rule = rules[j]
                if rule is None or (j == off and kept):
                    continue
                base = max(min(z[j - n:j]), min(z[j + 1:j + 1 + n]))
                rise = z[j] - base
                if not (rise > t - self.margin and z[j] > 1):
                    continue
                keep = float(rule[0])
                if j == off:
                    if oldest is None and keep * rise > t and self._room(i, rule):
                        kept = True  # its window has room: the flash keeps its share, over the line
                    else:
                        keep = min(keep, 0.75 * t / rise)
                    oldest = base
                else:  # a frame still to come is brought under the line, as it will be if its window is full
                    keep = min(keep, 0.75 * t / rise)
                z[j] = base + keep * rise
                moved = True
            if not moved:
                break
        if oldest is None:
            return None
        return z[off], oldest, kept

    def _decide(self) -> np.ndarray:
        i = self.count
        settled = self._settle(i)
        frame, y, _rule = self.frames.popleft(), self.lumas.popleft(), self.rules.popleft()
        self.count += 1
        if settled is None:
            self.before.append(y)
            return frame
        target, base, kept = settled
        self.flashes += 1
        if kept:
            self.kept.append(i)
            self.kept_total += 1
        self.tamed += 1
        keep = max(0.0, (target - base) / max(1e-3, y - base))
        out = lift(frame, y, base, keep)
        self.before.append(luma(out))
        return out

    def info(self) -> dict:
        return {"frames": self.count, "flashes": self.flashes, "tamed": self.tamed, "kept": self.kept_total}
