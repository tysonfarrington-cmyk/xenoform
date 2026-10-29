"""Polish checks on an assembled walkthrough: length, black or frozen stretches, loudness, a contact sheet to look at.

    python qa_cut.py <mp4> <sheet jpg> [seconds a frame]
"""
import re
import subprocess
import sys

mp4, sheet = sys.argv[1], sys.argv[2]
step = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4],
                           capture_output=True, text=True).stdout.strip())
print(f"length {int(dur // 60)}:{dur % 60:04.1f}")
det = subprocess.run(["ffmpeg", "-v", "info", "-i", mp4, "-vf", "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=0.002:d=4",
                      "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
blacks = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", det)
freezes = re.findall(r"freeze_start: ([\d.]+)|freeze_end: ([\d.]+)", det)
starts = [float(a) for a, b in freezes if a]
ends = [float(b) for a, b in freezes if b]
print("black stretches over 0.5 s:", [(float(a), float(b)) for a, b in blacks] or "none")
print("frozen stretches over 4 s:", list(zip(starts, ends)) or "none")
tail = det[det.rfind("Integrated loudness"):]  # the summary, not the per-frame lines
loud = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
peak = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
print("loudness", loud.group(1) if loud else "?", "LUFS, true peak", peak.group(1) if peak else "?", "dBFS")
n = int(dur / step) + 1
cols = 10
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-vf", f"fps=1/{step},scale=288:162,tile={cols}x{(n + cols - 1) // cols}",
                "-frames:v", "1", "-q:v", "4", sheet], check=False)
print("sheet", sheet, n, "frames")
