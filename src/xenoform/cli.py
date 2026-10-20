"""Command line for the Xenoform pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from xenoform import __version__
from xenoform.analyze import read_features
from xenoform.assemble import assemble
from xenoform.config import load_config
from xenoform.osc_export import export_bundle, stream
from xenoform.pipeline import analyze_file, render_file, run_pipeline
from xenoform.restyle import restyle
from xenoform.synth import synthesize, write_wav


def _logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def _add_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="JSON config. Omitted keys fall back to built-in defaults.")
    parser.add_argument("-v", "--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xenoform",
        description="Audio-reactive alien-biotech forms, restyled with ComfyUI LTX.",
    )
    parser.add_argument("--version", action="version", version=f"xenoform {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    synth = sub.add_parser("synth", help="Write a royalty-free test track.")
    synth.add_argument("--out", required=True)
    synth.add_argument("--duration", type=float)
    synth.add_argument("--sr", type=int)
    synth.add_argument("--bpm", type=float)
    synth.add_argument("--seed", type=int)
    _add_config(synth)

    analyze = sub.add_parser("analyze", help="Audio file to per-frame feature JSON.")
    analyze.add_argument("audio")
    analyze.add_argument("--out", required=True)
    analyze.add_argument("--fps", type=float)
    _add_config(analyze)

    render = sub.add_parser("render", help="Raymarch the base form to an mp4.")
    render.add_argument("--features", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--audio", help="Mux this audio into the mp4.")
    _add_config(render)

    restyle_p = sub.add_parser("restyle", help="Slice the base video and run LTX video-to-video.")
    restyle_p.add_argument("--features", required=True)
    restyle_p.add_argument("--video", required=True)
    restyle_p.add_argument("--out", required=True, help="Directory for chunks and manifest.json.")
    restyle_p.add_argument("--live", action="store_true", help="Submit to ComfyUI via the Comfy SDK.")
    restyle_p.add_argument("--dry-run", action="store_true", help="Write the manifest and pass the base slices through.")
    _add_config(restyle_p)

    assemble_p = sub.add_parser("assemble", help="Crossfade chunks and mux the original audio.")
    assemble_p.add_argument("--manifest", required=True)
    assemble_p.add_argument("--audio", required=True)
    assemble_p.add_argument("--out", required=True)
    assemble_p.add_argument("--features", help="Feature JSON, used for beat flashes.")
    _add_config(assemble_p)

    osc = sub.add_parser("osc", help="Export CSV/JSON and optionally stream OSC.")
    osc.add_argument("features")
    osc.add_argument("--out", help="Directory for features.json, frames.csv, osc_addresses.json.")
    osc.add_argument("--stream", action="store_true")
    osc.add_argument("--host")
    osc.add_argument("--port", type=int)
    osc.add_argument("--fast", action="store_true", help="Send the OSC burst without sleeping to fps.")
    _add_config(osc)

    run = sub.add_parser("run", help="Analyze, render, restyle, assemble.")
    run.add_argument("--audio")
    run.add_argument("--out", required=True)
    run.add_argument("--work", default="work")
    run.add_argument("--synth", action="store_true", help="Generate the test track when --audio is omitted.")
    run.add_argument("--base-only", action="store_true", help="Stop after the beauty pass.")
    run.add_argument("--live", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    _add_config(run)

    ui = sub.add_parser("ui", help="Open the director desk in a browser.")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=47317)
    _add_config(ui)

    mcp = sub.add_parser("mcp", help="Expose the desk to an agent. Stdio by default. HTTP stays on localhost.")
    mcp.add_argument("--http", action="store_true", help="Streamable HTTP on 127.0.0.1. Off unless you pass this.")
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=47319)
    mcp.add_argument("--desk", default="", help="Desk base URL. Defaults to XENO_DESK, else the desk answering on 47330 then 47317.")

    guard = sub.add_parser("guardrails", help="List the guardrails, or check a settings JSON against them (no render).")
    guard.add_argument("settings", nargs="?", default="", help="Render settings JSON to check. Omit to list the guardrails.")
    guard.add_argument("--duration", type=float, default=None, help="Clip length in seconds (for morph density).")
    guard.add_argument("--vram-gb", type=float, default=None)
    guard.add_argument("--expert", action="store_true", help="Keep values; warn only (hard bans still apply).")
    guard.add_argument("--out", default="", help="Write the clamped settings here.")
    _add_config(guard)

    sample = sub.add_parser("sample-library", help="Write a few procedural shapes into ./library.")
    sample.add_argument("--out", default="library")
    sample.add_argument("--force", action="store_true", help="Replace a library.json that already has many items.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _logging(getattr(args, "verbose", False))
    cfg = load_config(getattr(args, "config", None))
    try:
        _dispatch(args, cfg)
    except Exception as exc:
        logging.getLogger("xenoform").error("%s", exc)
        return 1
    return 0


def _dispatch(args, cfg: dict) -> None:
    if args.cmd == "synth":
        duration = args.duration if args.duration is not None else float(cfg["audio"]["duration"])
        sr = args.sr if args.sr is not None else int(cfg["sr"])
        bpm = args.bpm if args.bpm is not None else float(cfg["audio"]["bpm"])
        seed = args.seed if args.seed is not None else int(cfg["seed"])
        audio = synthesize(duration=duration, sr=sr, bpm=bpm, seed=seed)
        write_wav(args.out, audio, sr)
        print(args.out)
        return

    if args.cmd == "analyze":
        if args.fps is not None:
            cfg["fps"] = args.fps
        features = analyze_file(Path(args.audio), cfg, Path(args.out))
        print(f"{features['n_frames']} frames, {len(features['sections'])} sections -> {args.out}")
        return

    if args.cmd == "render":
        features = read_features(args.features)
        work = Path(args.out).parent
        render_file(features, cfg, Path(args.out), Path(args.audio) if args.audio else None, work)
        print(args.out)
        return

    if args.cmd == "restyle":
        if args.live and args.dry_run:
            raise RuntimeError("Pass only one of --live and --dry-run.")
        mode = "live" if args.live else "dry-run" if args.dry_run else cfg["comfy"]["mode"]
        manifest = restyle(read_features(args.features), args.video, args.out, cfg, mode=mode)
        print(f"{manifest['mode']}: {len(manifest['chunks'])} chunks -> {args.out}/manifest.json")
        return

    if args.cmd == "assemble":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        features = read_features(args.features) if args.features else None
        assemble(
            manifest,
            args.audio,
            args.out,
            features=features,
            crossfade_frames=int(cfg["assemble"]["crossfade_frames"]),
            beat_flashes=bool(cfg["assemble"]["beat_flashes"]),
            flash_amount=float(cfg["assemble"]["flash_amount"]),
            crf=int(cfg["assemble"]["crf"]),
        )
        print(args.out)
        return

    if args.cmd == "osc":
        features = read_features(args.features)
        if args.out:
            paths = export_bundle(features, args.out)
            print(json.dumps(paths, indent=2))
        if args.stream or not args.out:
            host = args.host or cfg["osc"]["host"]
            port = args.port if args.port is not None else int(cfg["osc"]["port"])
            stream(features, host, port, realtime=not args.fast)
            print(f"streamed {features['n_frames']} frames to {host}:{port}")
        return

    if args.cmd == "guardrails":
        from xenoform import guardrails as _guard

        if not args.settings:
            for g in _guard.summary():
                print(f"{g['id']}{' (hard)' if g['hard'] else ''}: {g['why']}")
                print(f"    defaults: {json.dumps(g['defaults'])}")
            return
        body = json.loads(Path(args.settings).read_text(encoding="utf-8"))
        clean, report = _guard.apply(body, expert=args.expert, duration=args.duration, vram_gb=args.vram_gb, cfg=cfg)
        for line in report["messages"] or ["No changes: these settings pass every guardrail."]:
            print(line)
        if args.out:
            Path(args.out).write_text(json.dumps(clean, indent=2), encoding="utf-8")
            print(args.out)
        return

    if args.cmd == "run":
        from xenoform import guardrails as _guard

        for line in _guard.check_config(cfg)["messages"]:
            logging.getLogger("xenoform").warning("guardrail %s", line)
        if args.live and args.dry_run:
            raise RuntimeError("Pass only one of --live and --dry-run.")
        run_pipeline(
            cfg,
            out_path=Path(args.out),
            audio_path=Path(args.audio) if args.audio else None,
            work=Path(args.work),
            live=bool(args.live),
            dry_run=bool(args.dry_run),
            base_only=bool(args.base_only),
            synth=bool(args.synth),
        )
        print(args.out)
        return

    if args.cmd == "ui":
        from xenoform.ui import serve

        serve(host=args.host, port=int(args.port), cfg=cfg)
        return

    if args.cmd == "mcp":
        host = str(args.host or "127.0.0.1")
        if args.http and host not in {"127.0.0.1", "localhost", "::1"}:
            raise SystemExit("The agent port stays on this machine. Use 127.0.0.1.")
        from xenoform.mcp_server import serve as serve_mcp

        try:
            serve_mcp(
                "streamable-http" if args.http else "stdio",
                host=host,
                port=int(args.port),
                desk=args.desk or None,
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        return

    if args.cmd == "sample-library":
        from xenoform.source_library import write_sample_library

        dest = write_sample_library(args.out, force=bool(args.force))
        print(dest)
        return

    raise RuntimeError(f"Unknown command {args.cmd}")


if __name__ == "__main__":
    sys.exit(main())
