"""Run the stages in order. Stage 3 stays a dry-run unless asked to go live."""

from __future__ import annotations

import logging
from pathlib import Path

from xenoform.analyze import analyze_audio, read_features, write_features
from xenoform.assemble import assemble
from xenoform.config import load_config
from xenoform.osc_export import export_bundle
from xenoform.render import render_sequence
from xenoform.restyle import restyle
from xenoform.synth import read_wav, synthesize, write_wav

log = logging.getLogger("xenoform")


def analyze_file(audio_path: Path, cfg: dict, out_path: Path) -> dict:
    audio, sr = read_wav(audio_path)
    features = analyze_audio(
        audio,
        sr,
        fps=float(cfg["fps"]),
        onset_tau=float(cfg["analyze"]["onset_tau"]),
        beat_tau=float(cfg["analyze"]["beat_tau"]),
        section_min_seconds=float(cfg["analyze"]["section_min_seconds"]),
    )
    write_features(out_path, features)
    log.info(
        "analyzed %s frames, %s sections, tempo %.1f",
        features["n_frames"],
        len(features["sections"]),
        features["tempo"],
    )
    return features


def render_file(
    features: dict,
    cfg: dict,
    out_path: Path,
    audio_path: Path | None,
    work: Path,
    on_progress=None,
) -> None:
    render_cfg = cfg["render"]
    depth = work / "depth.mp4" if render_cfg.get("write_depth") else None
    mask = work / "mask.mp4" if render_cfg.get("write_mask") else None
    png = work / "png" if render_cfg.get("write_png") else None
    render_sequence(
        features,
        out_path,
        width=int(render_cfg["width"]),
        height=int(render_cfg["height"]),
        max_steps=int(render_cfg["max_steps"]),
        backend=str(render_cfg["backend"]),
        crf=int(render_cfg["crf"]),
        audio_path=audio_path,
        depth_path=depth,
        mask_path=mask,
        png_dir=png,
        on_progress=on_progress,
    )


def run_pipeline(
    cfg: dict,
    out_path: Path,
    audio_path: Path | None = None,
    work: Path | None = None,
    live: bool = False,
    dry_run: bool = False,
    base_only: bool = False,
    synth: bool = False,
) -> None:
    work = Path(work or "work")
    work.mkdir(parents=True, exist_ok=True)
    if audio_path is None and synth:
        audio_path = work / "synth.wav"
        audio = synthesize(
            duration=float(cfg["audio"]["duration"]),
            sr=int(cfg["sr"]),
            bpm=float(cfg["audio"]["bpm"]),
            seed=int(cfg["seed"]),
        )
        write_wav(audio_path, audio, int(cfg["sr"]))
        log.info("synthesized %s", audio_path)
    if audio_path is None:
        raise RuntimeError("Pass an audio file, or --synth to generate the test track.")

    features_path = work / "features.json"
    features = analyze_file(Path(audio_path), cfg, features_path)
    export_bundle(features, work / "touchdesigner")

    base_path = work / "base.mp4"
    render_file(features, cfg, base_path, Path(audio_path), work)
    if base_only:
        # The caller asked for the beauty pass only. Copy it to --out when
        # that path is different from the work file.
        if Path(out_path).resolve() != base_path.resolve():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(base_path.read_bytes())
            log.info("base-only output %s", out_path)
        return

    mode = "live" if live else "dry-run" if dry_run else cfg["comfy"]["mode"]
    manifest = restyle(features, base_path, work / "chunks", cfg, mode=mode)
    # Re-read features: render_file smooths mutate in memory, which is what we
    # want the assembler flashes to see, and the file on disk is the raw analysis.
    features = read_features(features_path)
    assemble(
        manifest,
        audio_path,
        out_path,
        features=features,
        crossfade_frames=int(cfg["assemble"]["crossfade_frames"]),
        beat_flashes=bool(cfg["assemble"]["beat_flashes"]),
        flash_amount=float(cfg["assemble"]["flash_amount"]),
        crf=int(cfg["assemble"]["crf"]),
    )


def load(path: str | None) -> dict:
    return load_config(path)
