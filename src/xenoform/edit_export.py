"""Share › Edit in Resolve: the cut as an editor's timeline, so a video made here can be finished in DaVinci Resolve,
Premiere or Final Cut (from Pause's demo: every edit its own clip, 27 Oct).

``build`` writes a pack for the cut as it is now under ``<job>/edit/<version>/`` and zips it beside:

- V1: the composed cut split at the shot boundaries into a file a shot, named for its objects ("04 chameleon to wet
  street"), a clip shot for its film ("05 Metropolis robot": the clip's label in its folder's pack.json or labels.json,
  else its file name), laid end to end. The editor plays exactly the cut, look and FX included, and each shot is a clip of its own
  in the bin to trim, move, grade or replace. One x264 pass at CRF 14 with a keyframe forced on every boundary, split
  there by the segment muxer: frame-exact, visually lossless. No sound on these, so nothing doubles the song.
- A1: the song as the cut plays it (the record's ``audio_path`` starts where the cut starts), one clip under the cut.
- Markers at the drop and at each dressed handoff (smear, strobe cut, wipe, rip, or the vibe's transition), one a frame.
- The same timeline three ways: FCP7 XML (Premiere, and Resolve, which takes its markers), FCPXML 1.10 (Final Cut,
  Resolve) and a CMX3600 EDL.
- ``media/morphs``: each morph as the GPU made it, before the cut's speed and FX, to rebuild a shot clean.

The timelines name the media by absolute path inside the pack's folder: on this machine they open with nothing to
relink; on another, relink to the zip's ``media`` folder (README.txt says how). A re-cut makes a new version folder (an
editor may hold the old media open); an unchanged cut reuses its pack. Checked in Resolve 21 Free on 27 Oct: all three
import with the clips frame-exact, and a render of the imported timeline matches the cut frame for frame, song in sync.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from xenoform import lane
from xenoform.video import ffmpeg_bin, ffprobe_bin

HOUR = 3600  # the timelines start at 01:00:00:00, as an editor's do
CRF = 14
_BUILD = threading.Lock()


def _probe(path: Path) -> dict:
    """What the timelines need from a file: the picture's size, exact rate and frame count; the audio's rate, channels
    and length in samples."""
    raw = subprocess.check_output([ffprobe_bin(), "-v", "error", "-show_entries",
                                   "stream=codec_type,width,height,r_frame_rate,nb_frames,duration,sample_rate,channels,duration_ts,time_base",
                                   "-of", "json", str(path)], text=True)
    out: dict = {}
    for s in json.loads(raw).get("streams") or []:
        if s.get("codec_type") == "video" and "video" not in out:
            rate = Fraction(str(s.get("r_frame_rate") or "0/1"))
            rate = rate if rate > 0 else Fraction(24)
            nb = str(s.get("nb_frames") or "")
            frames = int(nb) if nb.isdigit() else round(float(s.get("duration") or 0.0) * rate)
            out["video"] = {"width": int(s["width"]), "height": int(s["height"]), "fps": rate, "frames": int(frames)}
        elif s.get("codec_type") == "audio" and "audio" not in out:
            rate = int(s.get("sample_rate") or 48000)
            if s.get("duration_ts") is not None and s.get("time_base"):
                samples = int(Fraction(int(s["duration_ts"])) * Fraction(str(s["time_base"])) * rate)
            else:
                samples = int(float(s.get("duration") or 0.0) * rate)
            out["audio"] = {"rate": rate, "channels": int(s.get("channels") or 2), "samples": samples}
    return out


def _frame(seconds, fps: Fraction, frames: int) -> int:
    return max(0, min(frames, round(Fraction(float(seconds or 0.0)) * fps)))


def _rows(rec: dict) -> list[dict]:
    return lane.build(rec)["shots"] if rec.get("shots") else []


def _shot_name(i: int, row: dict, film: str = "") -> str:
    n = f"{i + 1:02d}"
    if row.get("performer"):
        return f"{n} Polly"
    if row.get("own"):
        return f"{n} {film or 'your clip'}"
    pair = f"{row.get('from') or '?'} → {row.get('to') or '?'}"
    if row.get("generated") is not None:
        pair = f"generated {pair}"
    return f"{n} {pair}" + (" (held)" if row.get("hold") else "")


def folder_labels(folder: Path) -> dict[str, str]:
    """{file name: label} of a clip folder: its ``pack.json`` (the free film pack's record: each clip's ``label``, else
    its ``title``) over its ``labels.json`` (your own labels, and the pack's), {} when it has neither."""
    out: dict[str, str] = {}
    for name in ("labels.json", "pack.json"):
        try:
            data = json.loads((Path(folder) / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if name == "labels.json" and isinstance(data, dict):
            out.update({str(k): v.strip() for k, v in data.items() if isinstance(v, str) and v.strip()})
        elif isinstance(data, dict):
            for r in data.get("clips") or []:
                label = str((r or {}).get("label") or (r or {}).get("title") or "").strip() if isinstance(r, dict) else ""
                if label and r.get("file"):
                    out[str(r["file"])] = label
    return out


def film_names(rec: dict) -> dict[int, str]:
    """What Edit in Resolve calls each clip shot, after the film (the follow-ups of 1 Nov: not "your clip"): the label
    the clip's folder gives it, in ``pack.json`` or ``labels.json`` (``folder_labels``), else the label the clip was cut
    with (``own_clips``: the folder's labels.json when the cut was made), else its file name. {shot index: name}; a
    clips cut's shot names its clip in ``source``, an objects cut's own-footage slot in ``own.slots``."""
    shots = list(rec.get("shots") or [])
    paths: dict[str, Path] = {}
    given: dict[str, str] = {}
    for c in rec.get("own_clips") or []:
        p = c.get("path") if isinstance(c, dict) else c
        if p:
            paths[Path(str(p)).name] = Path(str(p))
            if isinstance(c, dict) and str(c.get("label") or "").strip():
                given[Path(str(p)).name] = str(c["label"]).strip()
    own = rec.get("own") if isinstance(rec.get("own"), dict) else {}
    slot_clip: dict[int, Path] = {}
    for sl in own.get("slots") or []:
        if isinstance(sl, dict) and sl.get("clip"):
            for j in range(int(sl.get("first", 0)), int(sl.get("last", sl.get("first", 0))) + 1):
                slot_clip[j] = Path(str(sl["clip"]))
    folders: dict[Path, dict[str, str]] = {}
    out: dict[int, str] = {}
    for i, s in enumerate(shots):
        if not s.get("own"):
            continue
        src = str(s.get("source") or "")
        path = paths.get(Path(src).name) if src else slot_clip.get(i)
        name = Path(src).name if src else (path.name if path is not None else "")
        if not name:
            continue
        labels: dict[str, str] = {}
        if path is not None:
            if path.parent not in folders:
                folders[path.parent] = folder_labels(path.parent)
            labels = folders[path.parent]
        out[i] = labels.get(name) or given.get(name) or Path(name).stem
    return out


def segments(rec: dict, frames: int, fps: Fraction) -> list[dict]:
    """V1's clips: the cut split at its shot boundaries, frame-exact at the cut's rate, each named for its shot (a morph
    for its objects, "A → B"; a clip for its film, ``film_names``) and contiguous by construction. Frames past the last
    shot (an end card) are a clip of their own; a cut with no shot record is one clip."""
    shots = list(rec.get("shots") or [])
    rows = _rows(rec)
    films = film_names(rec)
    bounds = [_frame(s.get("start"), fps, frames) for s in shots]
    last_end = _frame(shots[-1].get("end"), fps, frames) if shots else 0
    tail = bool(shots) and frames - last_end > 2  # more than rounding left over: the end card
    out: list[dict] = []
    for i, row in enumerate(rows):
        end = bounds[i + 1] if i + 1 < len(rows) else (last_end if tail else frames)
        start = out[-1]["end"] if out else 0
        if end > start:  # a shot under a frame at this rate folds into its neighbour
            out.append({"shot": i, "name": _shot_name(i, row, films.get(i, "")), "start": start, "end": end})
    if tail or not out:
        start = out[-1]["end"] if out else 0
        out.append({"shot": None, "name": f"{len(out) + 1:02d} end card" if out else "the cut", "start": start, "end": frames})
    return out


def markers(rec: dict, frames: int, fps: Fraction) -> list[dict]:
    """The drop and every dressed handoff. Resolve keeps one marker a frame, so a handoff on the drop is one marker
    named for both."""
    from xenoform import transitions_fx as T

    shots = list(rec.get("shots") or [])
    at: dict[int, list[tuple[str, str]]] = {}
    window = rec.get("window") if isinstance(rec.get("window"), dict) else {}
    start = float(window.get("song_start") or 0.0)
    if start > 0:  # a Length cut: where it sits in the song (dense.window_of), so the edit can be laid back on the song
        clock = f"{int(start // 60)}:{start % 60:04.1f}"
        at.setdefault(0, []).append((f"Song {clock}", f"the cut starts {clock} into the song"))
    if rec.get("drop") is not None:
        at.setdefault(_frame(rec["drop"], fps, frames), []).append(("Drop", "the drop the cut is built on"))
    song = rec.get("song") if str(rec.get("mode") or "") == "song" and isinstance(rec.get("song"), dict) else None
    for p in (song or {}).get("passages") or []:  # a whole song: where each passage, and its look, comes in
        look = str(p.get("name") or p.get("vibe") or "")
        jobs = ", ".join(j for j in p.get("jobs") or [] if j)
        at.setdefault(_frame(p.get("start"), fps, frames), []).append(
            (f"Passage {int(p.get('index') or 0) + 1} · {p.get('role') or ''}" + (f" · {look}" if look else ""),
             f"made by {jobs}" if jobs else "a passage of the song"))
    for i, row in enumerate(_rows(rec)):
        if i and row.get("transition"):
            kind = str(row.get("transition_id") or row["transition"])
            label = str(row["transition"]) if row.get("kind") else str((T.TRANSITIONS.get(kind) or {}).get("label") or kind)
            note = f"handoff into shot {i + 1}" + (", set on the timeline" if row.get("fx_override") else "")
            at.setdefault(_frame(shots[i].get("start"), fps, frames), []).append((label, note))
    return [{"frame": f, "name": " · ".join(n for n, _ in v), "note": "; ".join(x for _, x in v)}
            for f, v in sorted(at.items()) if f < frames]


def file_name(name: str) -> str:
    """A clip name as a file name an editor's bin shows and any disk takes: "04 chameleon to wet street"."""
    text = _ascii(name.replace("→", "to"))
    text = "".join(c if c.isalnum() or c in " -_()" else " " for c in text)
    return " ".join(text.split())[:80] or "shot"


# --- the three timeline formats -------------------------------------------------------------------------------------
# Each takes the plan ``build`` makes: ``segments`` with their ``path`` (a file a shot, frame 0 its first frame),
# ``markers`` on the cut's frames, the ``song``, the picture's size and exact rate.

def _ascii(text: str) -> str:
    return text.replace("→", ">").replace("·", "-").encode("ascii", "replace").decode("ascii")


def _timebase(fps: Fraction) -> tuple[int, bool]:
    """The integer timebase and NTSC flag the FCP7 XML and the EDL count timecode in."""
    return round(fps), fps.denominator == 1001


def timecode(frame: int, fps: Fraction) -> str:
    tb, _ = _timebase(fps)
    s, f = divmod(int(frame), tb)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


def _t(frames: int, fps: Fraction) -> str:
    """FCPXML time: a frame count as rational seconds, unreduced the way Final Cut writes it (72 frames at 24 is 72/24s)."""
    return "0s" if not frames else f"{frames * fps.denominator}/{fps.numerator}s"


def fcpxml(p: dict) -> str:
    fps, segs, song = p["fps"], p["segments"], p.get("song")
    start = HOUR * _timebase(fps)[0]
    t = lambda n: _t(n, fps)  # noqa: E731
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE fcpxml>", '<fcpxml version="1.10">', "  <resources>",
             f'    <format id="r1" frameDuration="{_t(1, fps)}" width="{p["width"]}" height="{p["height"]}"/>']
    for k, seg in enumerate(segs):
        lines += [f'    <asset id="s{k + 1}" name={quoteattr(seg["path"].stem)} start="0s" duration="{t(seg["end"] - seg["start"])}" '
                  'hasVideo="1" videoSources="1" format="r1">',
                  f'      <media-rep kind="original-media" src={quoteattr(seg["path"].as_uri())}/>', "    </asset>"]
    if song:
        lines += [f'    <asset id="a1" name={quoteattr(song["path"].stem)} start="0s" duration="{song["samples"]}/{song["rate"]}s" '
                  f'hasAudio="1" audioSources="1" audioChannels="{song["channels"]}" audioRate="{song["rate"]}">',
                  f'      <media-rep kind="original-media" src={quoteattr(song["path"].as_uri())}/>', "    </asset>"]
    lines += ["  </resources>", "  <library>", '    <event name="Xenoform">', f"      <project name={quoteattr(p['title'])}>",
              f'        <sequence format="r1" duration="{t(p["frames"])}" tcStart="{t(start)}" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
              "          <spine>"]
    for k, seg in enumerate(segs):
        lines.append(f'            <asset-clip ref="s{k + 1}" name={quoteattr(seg["name"])} offset="{t(start + seg["start"])}" '
                     f'start="0s" duration="{t(seg["end"] - seg["start"])}" format="r1" tcFormat="NDF">')
        if k == 0 and song:  # the song hangs under the first clip and runs the length of the cut (A1)
            lines.append(f'              <asset-clip ref="a1" lane="-1" name={quoteattr(song["path"].stem)} offset="0s" start="0s" duration="{t(song["frames"])}"/>')
        for m in p["markers"]:  # Final Cut keeps markers on clips: each in the clip it falls in, on the clip's own frames
            if seg["start"] <= m["frame"] < seg["end"]:
                lines.append(f'              <marker start="{t(m["frame"] - seg["start"])}" duration="{_t(1, fps)}" '
                             f'value={quoteattr(m["name"])} note={quoteattr(m["note"])}/>')
        lines.append("            </asset-clip>")
    lines += ["          </spine>", "        </sequence>", "      </project>", "    </event>", "  </library>", "</fcpxml>", ""]
    return "\n".join(lines)


def _pathurl(path: Path) -> str:
    return "file://localhost/" + path.as_uri()[len("file:///"):]


def xmeml(p: dict) -> str:
    """FCP7 XML (xmeml 5), what Premiere imports; Resolve reads it too, markers included."""
    fps, segs, song = p["fps"], p["segments"], p.get("song")
    tb, ntsc = _timebase(fps)
    rate = f"<rate><timebase>{tb}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"
    start = HOUR * tb
    video_chars = (f"<samplecharacteristics>{rate}<width>{p['width']}</width><height>{p['height']}</height>"
                   "<anamorphic>FALSE</anamorphic><pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics>")
    zero_tc = f"<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<!DOCTYPE xmeml>", '<xmeml version="5">', '  <sequence id="sequence-1">',
           f"    <name>{escape(p['title'])}</name>", f"    <duration>{p['frames']}</duration>", f"    {rate}",
           f"    <timecode>{rate}<string>{timecode(start, fps)}</string><frame>{start}</frame><displayformat>NDF</displayformat></timecode>",
           "    <media>", "      <video>", f"        <format>{video_chars}</format>", "        <track>"]
    for k, seg in enumerate(segs):
        n = seg["end"] - seg["start"]
        out.append(f'          <clipitem id="clipitem-{k + 1}"><masterclipid>masterclip-{k + 1}</masterclipid><name>{escape(seg["name"])}</name>'
                   f"<enabled>TRUE</enabled><duration>{n}</duration>{rate}<start>{seg['start']}</start><end>{seg['end']}</end>"
                   f'<in>0</in><out>{n}</out><file id="file-{k + 1}"><name>{escape(seg["path"].name)}</name>'
                   f"<pathurl>{escape(_pathurl(seg['path']))}</pathurl>{rate}<duration>{n}</duration>{zero_tc}"
                   f"<media><video>{video_chars}</video></media></file></clipitem>")
    out += ["        </track>", "      </video>"]
    if song:
        song_len = round(Fraction(song["samples"], song["rate"]) * fps)
        out += ["      <audio>", "        <numOutputChannels>2</numOutputChannels>",
                "        <format><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics></format>",
                "        <track>",
                f'          <clipitem id="clipitem-song"><masterclipid>masterclip-song</masterclipid><name>{escape(song["path"].stem)}</name>'
                f"<enabled>TRUE</enabled><duration>{song_len}</duration>{rate}<start>0</start><end>{song['frames']}</end>"
                f"<in>0</in><out>{song['frames']}</out>"
                f'<file id="file-song"><name>{escape(song["path"].name)}</name><pathurl>{escape(_pathurl(song["path"]))}</pathurl>{rate}'
                f"<duration>{song_len}</duration><media><audio><samplecharacteristics><depth>16</depth><samplerate>{song['rate']}</samplerate>"
                f"</samplecharacteristics><channelcount>{song['channels']}</channelcount></audio></media></file>"
                "<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>",
                "        </track>", "      </audio>"]
    out.append("    </media>")
    for m in p["markers"]:
        out.append(f"    <marker><name>{escape(m['name'])}</name><comment>{escape(m['note'])}</comment><in>{m['frame']}</in><out>-1</out></marker>")
    out += ["  </sequence>", "</xmeml>", ""]
    return "\n".join(out)


def edl(p: dict) -> str:
    """CMX3600: one event a shot on V, the song on A, clip names in FROM CLIP NAME (how Resolve and Premiere match the
    media); ASCII only. Resolve takes the picture from an EDL, not the sound."""
    fps, start = p["fps"], HOUR * _timebase(p["fps"])[0]
    out = [f"TITLE: {_ascii(p['title'])}", "FCM: NON-DROP FRAME", ""]
    n = 0
    for seg in p["segments"]:
        n += 1
        out += [f"{n:03d}  AX       V     C        {timecode(0, fps)} {timecode(seg['end'] - seg['start'], fps)} "
                f"{timecode(start + seg['start'], fps)} {timecode(start + seg['end'], fps)}",
                f"* FROM CLIP NAME: {seg['path'].name}", ""]
    song = p.get("song")
    if song:
        n += 1
        out += [f"{n:03d}  AX       A     C        {timecode(0, fps)} {timecode(song['frames'], fps)} "
                f"{timecode(start, fps)} {timecode(start + song['frames'], fps)}",
                f"* FROM CLIP NAME: {song['path'].name}", ""]
    return "\r\n".join(out)


def readme(p: dict) -> str:
    """How to open the pack in each editor, what the media are, the shots and markers at their timecodes (ASCII, so
    any text viewer reads it)."""
    fps, base = p["fps"], p["base"]
    hour = HOUR * _timebase(fps)[0]
    lines = [p["title"], "",
             "The cut as a timeline: every shot its own clip on V1, the song on A1, markers at the drop and at each dressed handoff.",
             f"{p['width']}x{p['height']} at {float(fps):g} fps, {len(p['segments'])} clips, {timecode(p['frames'], fps)} long, starting at 01:00:00:00.",
             "",
             f"DaVinci Resolve: File > Import > Timeline..., pick {base}.xml. The clips, the song and the markers come in,",
             f"  on a {p['width']}x{p['height']} timeline. ({base}.fcpxml works too, without the markers.)",
             f"Premiere Pro: File > Import, pick {base}.xml.",
             f"Final Cut Pro: File > Import > XML, pick {base}.fcpxml.",
             f"Anything else: {base}.edl (import the media first; clips match by name; Resolve takes only the picture from it).",
             "",
             "The timelines point at the media in this pack's folder on the machine that made it. On another machine, relink to",
             "the media folder here (Resolve: select the clips in the Media Pool, right-click > Relink Selected Clips;",
             "Premiere asks on open; Final Cut: File > Relink Files).",
             "",
             "media/shots: the cut, a file a shot, look and FX included, without sound (the song is on A1).",
             (f"media/{p['song']['path'].name}: the song from where the cut starts." if p.get("song") else "The cut has no sound."),
             ("media/morphs: each morph as the GPU made it, before the cut's speed and FX." if p.get("morphs") else ""),
             "", "Shots"]
    lines += [f"  {timecode(hour + seg['start'], fps)}  {seg['name']}" for seg in p["segments"]]
    if p["markers"]:
        lines += ["", "Markers"]
        lines += [f"  {timecode(hour + m['frame'], fps)}  {m['name']} ({m['note']})" for m in p["markers"]]
    return _ascii("\r\n".join(lines) + "\r\n")


# --- the pack -------------------------------------------------------------------------------------------------------

def _link(src: Path, dest: Path) -> None:
    """A hard link where the volume allows (no second copy on disk), else a copy."""
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)


def _split(cut: Path, segs: list[dict], dest: Path) -> list[Path]:
    """The cut's picture as a file a segment, named for it: one encode with a keyframe forced on each boundary, split
    there by the segment muxer (frame-exact). No B-frames: with them the first file starts two frames late (the
    encoder's delay) and Resolve shows those frames black. A cut of one clip is a stream copy."""
    dest.mkdir(parents=True, exist_ok=True)
    names = [dest / f"{file_name(s['name'])}.mp4" for s in segs]
    if len(segs) == 1:
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", str(cut), "-map", "0:v:0", "-c", "copy", "-an",
                        "-movflags", "+faststart", str(names[0])], check=True)
        return names
    cuts = [s["start"] for s in segs[1:]]
    with tempfile.TemporaryDirectory(dir=dest) as tmp:
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", str(cut), "-map", "0:v:0", "-an", "-c:v", "libx264",
                        "-preset", "fast", "-crf", str(CRF), "-bf", "0", "-pix_fmt", "yuv420p",
                        "-force_key_frames", "expr:" + "+".join(f"eq(n,{f})" for f in cuts),
                        "-f", "segment", "-segment_frames", ",".join(str(f) for f in cuts), "-reset_timestamps", "1",
                        "-segment_format_options", "movflags=+faststart", str(Path(tmp) / "seg%05d.mp4")], check=True)
        made = sorted(Path(tmp).glob("seg*.mp4"))
        if len(made) != len(segs):
            raise RuntimeError(f"The cut split into {len(made)} files, not its {len(segs)} shots.")
        for src, name in zip(made, names):
            os.replace(src, name)
    return names


def _signature(job_dir: Path) -> dict:
    sig = {}
    for name in ("xenoform.mp4", "simple/simple.json"):
        path = job_dir / name
        if path.is_file():
            st = path.stat()
            sig[name] = [st.st_mtime_ns, st.st_size]
    return sig


def build(job_dir: Path, video_id: str | None = None) -> dict:
    """The pack for the cut as it is now (made once a version): the folder, the zip, and what is in it."""
    job_dir = Path(job_dir)
    vid = video_id or job_dir.name
    cut_src = job_dir / "xenoform.mp4"
    if not cut_src.is_file():
        raise FileNotFoundError("This video is not on this machine.")
    with _BUILD:
        sig = _signature(job_dir)
        when = time.localtime(cut_src.stat().st_mtime)
        version = time.strftime("%Y%m%d-%H%M%S", when)
        root = job_dir / "edit"
        folder = root / version
        zip_path = root / f"xenoform-{vid}-{version}.zip"
        pack_file = folder / "pack.json"
        if pack_file.is_file() and zip_path.is_file():
            try:
                done = json.loads(pack_file.read_text(encoding="utf-8"))
                if done.get("signature") == sig:
                    return done
            except ValueError:
                pass
        for old in list(root.glob("*")) if root.is_dir() else []:  # earlier versions: gone unless an editor holds them open
            try:
                shutil.rmtree(old) if old.is_dir() else old.unlink()
            except OSError:
                pass
        media = folder / "media"
        media.mkdir(parents=True, exist_ok=True)
        rec: dict = {}
        rec_path = job_dir / "simple" / "simple.json"
        if rec_path.is_file():
            try:
                rec = json.loads(rec_path.read_text(encoding="utf-8"))
            except ValueError:
                rec = {}
        base = f"xenoform-{vid}"
        info = _probe(cut_src)["video"]
        fps, frames = info["fps"], info["frames"]
        segs = segments(rec, frames, fps)
        for seg, path in zip(segs, _split(cut_src, segs, media / "shots")):
            seg["path"] = path
        song = None
        song_src = Path(str(rec.get("audio_path") or ""))
        if rec.get("audio_path") and song_src.is_file():
            song_path = media / f"{base}-song{song_src.suffix.lower()}"
            _link(song_src, song_path)
        else:  # the song file is gone (an upload from an earlier session): the cut's own sound, as heard
            song_path = media / f"{base}-song.wav"
            made = subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", str(cut_src), "-map", "0:a:0", "-c:a", "pcm_s16le",
                                   str(song_path)], capture_output=True)
            if made.returncode != 0:
                song_path.unlink(missing_ok=True)
        if song_path.is_file():
            a = _probe(song_path).get("audio")
            if a and a["samples"] > 0:
                song = {"path": song_path, **a, "frames": min(frames, int(Fraction(a["samples"], a["rate"]) * fps))}
        marks = markers(rec, frames, fps)
        morphs = []
        clips = [Path(str(c)) for c in rec.get("clips") or []]
        if clips:
            (media / "morphs").mkdir(exist_ok=True)
            names = {s["shot"]: s["name"] for s in segs if s["shot"] is not None}
            for i, clip in enumerate(clips):
                if clip.is_file():
                    dest = media / "morphs" / f"{file_name(names.get(i) or f'{i + 1:02d}')} (morph){clip.suffix.lower()}"
                    _link(clip, dest)
                    morphs.append(dest.name)
        tier = "Final" if str(rec.get("tier") or "") == "final" else "Draft" if rec else ""
        title = " · ".join(x for x in (f"Xenoform {vid}", " ".join(x for x in (str(rec.get("vibe") or ""), tier) if x),
                                         time.strftime("%d %b %H:%M", when)) if x)
        p = {"title": title, "base": base, "song": song, "width": info["width"], "height": info["height"],
             "fps": fps, "frames": frames, "segments": segs, "markers": marks, "morphs": morphs}
        files = {f"{base}.xml": xmeml(p), f"{base}.fcpxml": fcpxml(p), f"{base}.edl": edl(p), "README.txt": readme(p)}
        for name, text in files.items():
            (folder / name).write_text(text, encoding="utf-8", newline="")
        tmp = zip_path.with_suffix(".part")
        top = f"{base}-edit"
        with zipfile.ZipFile(tmp, "w") as z:
            for path in sorted(folder.rglob("*")):
                if path.is_file() and path.name != "pack.json":
                    kind = zipfile.ZIP_STORED if path.suffix.lower() in (".mp4", ".mov", ".m4a", ".mp3") else zipfile.ZIP_DEFLATED
                    z.write(path, f"{top}/{path.relative_to(folder).as_posix()}", compress_type=kind)
        os.replace(tmp, zip_path)
        done = {"id": vid, "version": version, "title": title, "folder": str(folder), "zip": str(zip_path),
                "zip_name": f"{base}-edit.zip", "mb": round(zip_path.stat().st_size / 1e6, 1),
                "timeline": f"{base}.xml", "fcpxml": f"{base}.fcpxml", "edl": f"{base}.edl",
                "size": [info["width"], info["height"]], "fps": float(fps), "seconds": round(float(Fraction(frames) / fps), 3),
                "shots": len(segs), "markers": len(marks), "song": bool(song), "morphs": len(morphs),
                "clips": [{"name": s["name"], "file": s["path"].name, "start": s["start"], "end": s["end"]} for s in segs],
                "marker_list": [{"name": m["name"], "frame": m["frame"]} for m in marks], "signature": sig}
        pack_file.write_text(json.dumps(done, indent=1), encoding="utf-8")
        return done
