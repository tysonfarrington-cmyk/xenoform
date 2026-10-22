"""'demo_house': the contest demo's look and mix, as the app's default profile.

Merged into config.DEFAULTS["house"] and read through ``config.house(section)``. Consumed by: dance_fx
(DanceFX / render_shot role presets, fps), transitions_fx (apply / guard / plan / recommend fallbacks),
stem_orbit (DEFAULTS, fps, focal), beatfx.compose + dense.run_simple (format fps / native 9:16 size, look,
the Simple ``dance_fx`` / ``stem_orbit`` payload defaults), media_qa (audio + transition rules) and the
MCP ``set_look`` / ``list_looks`` tools.
"""
from __future__ import annotations

DEMO_HOUSE: dict = {
    "name": "demo_house",
    "format": {"aspect": "9:16", "width": 1080, "height": 1920, "fps": 24, "native_vertical": True},
    "look": {
        "morph_background": "black", "shimmer": False, "character_wobble": False,
        "ui_shots": {"clean": True, "zoom_on_text": False},
        "morph_forms": 15,
    },
    "dance_fx": {  # preset -> intensity used in the demo
        "intro": {"preset": "cyan-flash", "intensity": 1.25},
        "vj": {"preset": "cool-echo", "intensity": 1.4},
        "flower": {"preset": "bloom-rush", "intensity": 1.5},
        "into_card": {"preset": "negative-rush", "intensity": 1.2, "invert_floor_ramp_frames": 14},
    },
    "stem_orbit": {"max_yaw": 28.0, "max_pitch": 4.0, "max_roll": 1.5, "bass": 1.0, "drums": 0.7, "other": 0.4,
                   "spin": 0.0, "stiffness": 6.0, "focal": 1.6},
    "transitions": {
        "allowed": ["flow-morph", "echo-trail", "lens-breath"],
        "banned": ["wipe", "iris", "stutter", "kaleidoscope", "mid-morph-stutter"],
        "max_uses_per_type": 2,
        "max_shots_first_15s": 3,
    },
    "audio": {
        "target_lufs": -14.0, "true_peak_dbtp": -2.0,
        "compressor": {"threshold_db": -12, "ratio": 2, "attack_ms": 15, "release_ms": 150, "knee_db": 6},
        "limiter": {"attack_ms": 5, "release_ms": 120, "oversample_hz": 192000},
        "vo_fade_min_ms": 35, "vo_line_end_fade_ms": 220, "vo_line_end_curve": "equal-power",
        "bed_crossfade_ms": 60, "music_duck_db": -3.0,
        "vo_chain": "eased",  # the eased v8.8 VO effects level (fixed gain, no per-cut refit)
    },
    "duration_cap_s": 120.0,
}
