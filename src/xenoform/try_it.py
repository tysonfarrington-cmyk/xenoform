"""One-button draft: the bundled register and a short royalty-free track."""

from __future__ import annotations

from pathlib import Path

from xenoform.config import load_config
from xenoform.hardware import detect_tier, run_resilient
from xenoform.synth import synthesize, write_wav


def _tiny_cut(work: Path, out: Path, register: str) -> dict:
    """Analyze, raymarch, dry-run restyle, and assemble a one-second track.

    The frame count is pinned to 9, which is the smallest LTX length (8*k+1).
    Two extra copies of the last frame are encoded so a decoder that drops the
    final frame still has nine to read.
    """
    from xenoform.analyze import analyze_audio, write_features
    from xenoform.assemble import assemble
    from xenoform.director import register_by_id
    from xenoform.render import render_sequence
    from xenoform.restyle import restyle
    from xenoform.synth import read_wav
    from xenoform.video import read_frame_range, write_mp4

    audio_path = work / "tiny.wav"
    write_wav(audio_path, synthesize(duration=1.5, sr=22050, bpm=120, seed=7), 22050)
    audio, sr = read_wav(audio_path)
    features = analyze_audio(audio, sr, fps=8, section_min_seconds=0.4)
    frames = list(features["frames"][:9])
    while len(frames) < 9:
        frames.append(dict(frames[-1] if frames else {"t": 0}))
    features["frames"] = frames
    features["n_frames"] = 9
    for section in features.get("sections") or []:
        section["start_frame"] = min(int(section.get("start_frame") or 0), 8)
        section["end_frame"] = 9
    cfg = load_config(None)
    cfg["fps"] = 8
    cfg["render"].update({"width": 64, "height": 32, "max_steps": 4, "backend": "cpu"})
    cfg["comfy"].update({"mode": "dry-run", "width": 64, "height": 32, "steps": 1})
    cfg["segment"].update({"target_seconds": 1.0, "min_seconds": 0.5, "max_seconds": 2.0})
    cfg["prompts"] = {**cfg["prompts"]}
    voice = register_by_id(register)
    features["register"] = voice["id"]
    write_features(work / "features.json", features)
    base = work / "base.mp4"
    render_sequence(
        features,
        base,
        width=64,
        height=32,
        max_steps=4,
        backend="cpu",
        audio_path=None,
    )
    readable = read_frame_range(base, 0, 9)
    if readable.shape[0] < 9:
        padded = [readable[i] for i in range(readable.shape[0])]
        padded.extend([padded[-1]] * (9 - len(padded)))
        write_mp4(base, padded, 8)
    manifest = restyle(features, base, work / "chunks", cfg, mode="dry-run")
    assemble(manifest, audio_path, out, features=features, crossfade_frames=0, beat_flashes=False, crf=28)
    return {
        "message": f"Draft is ready ({voice['name']}, dry run, cpu).",
        "path": str(out),
        "tier": "cpu",
        "register": voice["id"],
        "note": "",
    }


def try_demo(
    *,
    quality: str = "draft",
    register: str = "pynchon",
    tiny: bool = False,
    work: Path | None = None,
    out: Path | None = None,
) -> dict:
    """Render a dry-run cut. ``tiny`` is the CPU smoke path: a one-second track, a small frame."""
    from xenoform.director import register_by_id, run_directed
    from xenoform.storyboard import DEMO_BRIEF, plan_with_hook
    from xenoform.ui import repo_root

    if str(quality) == "live" and not tiny:
        return {
            "message": "Live plays in the desk. Open the UI and press Play. No model was started.",
            "path": "",
            "tier": "browser",
            "register": register,
            "note": "",
        }
    root = repo_root()
    work = Path(work or root / "work" / "try")
    work.mkdir(parents=True, exist_ok=True)
    out = Path(out or work / "xenoform.mp4")
    if tiny:
        return _tiny_cut(work, out, register)
    else:
        audio_path = root / "examples" / "demo.wav"
        if not audio_path.exists():
            audio_path = work / "demo.wav"
            write_wav(audio_path, synthesize(duration=12.0, sr=44100, bpm=120, seed=7), 44100)

    cfg = load_config(None)
    cfg["comfy"]["mode"] = "dry-run"
    voice = register_by_id(register)

    def once(tier_id: str) -> dict:
        # The storyboard is planned inside the attempt so a retry sees the same cards.
        from xenoform.analyze import analyze_audio
        from xenoform.synth import read_wav

        audio, sr = read_wav(audio_path)
        features = analyze_audio(audio, sr, fps=8 if tiny else float(cfg["fps"]))
        scenes, _source = plan_with_hook(features, voice, DEMO_BRIEF)
        state = {
            "quality": "draft" if tiny else quality,
            "live": False,
            "register": voice["id"],
            "scenes": scenes,
            "brief": DEMO_BRIEF,
            "tiny": tiny,
            "blocks": [],
        }
        return run_directed(cfg, audio_path, state, out, work / tier_id, tier_id=tier_id)

    _result, tier_id, note = run_resilient(once, detect_tier())
    label = "Draft" if tiny else {"turbo": "Turbo", "final": "Final"}.get(quality, "Draft")
    message = f"{label} is ready ({voice['name']}, dry run, {tier_id})."
    if note:
        message = f"{note} {message}"
    return {"message": message, "path": str(out), "tier": tier_id, "register": voice["id"], "note": note}
