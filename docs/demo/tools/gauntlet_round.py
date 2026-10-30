"""One round of the review gauntlet with Owly (Tys's Grok Bot assistant, who cannot message this session but reads and
writes files): a folder on the OneDrive Desktop with this round's review copies, a contact sheet a video with the
time on every frame, a shot list a video from the cuts' own records, and REVIEW_REQUEST.md saying what to judge and
how to answer (OWLY_NOTES.md beside it, one line an issue, with a time).

    python gauntlet_round.py <round number>
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
M = HERE / "montage"
DESK = Path(r"C:\Users\tyson\Desktop\xeno_walkthrough_29oct")
ROOT = Path(r"C:\Users\tyson\OneDrive\Desktop\xenoform_review_gauntlet")
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"
LOOKS = {}
for name in ("renders_169.json", "renders_916.json"):
    for r in json.loads((M / name).read_text(encoding="utf-8")):
        LOOKS.setdefault(r["label"], r)


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def ideas():
    """label -> the idea line its cut was made with (montage_renders.py's CUTS, read as text)."""
    import re
    text = (HERE / "montage_renders.py").read_text(encoding="utf-8")
    marks = [(m.start(), m.group(1)) for m in re.finditer(r'"label": "(\w+)"', text)] + [(len(text), "")]
    out = {}
    for (a, lab), (b, _) in zip(marks, marks[1:]):
        m = re.search(r'"idea": "([^"]*)"', text[a:b])
        if m:
            out[lab] = m.group(1)
    return out


IDEAS = ideas()


def describe(label):
    label = label.replace("@169", "")  # a 9:16 plan's 16:9 strip
    if label == "clips_flash":
        return "free film pack clips cut (Apollo 11, Un Chien Andalou's pianos, Metropolis's robot), re-cut with the cyan-flash look and dither"
    if label.startswith("clips"):
        return "free film pack clips cut (public-domain films morphing into each other), Final on this GPU, re-cut with the bloom-rush look"
    r = LOOKS.get(label) or {}
    fx = ", ".join(r.get("effects") or []) or "no effects"
    idea = f"; objects: {IDEAS[label]}" if IDEAS.get(label) else ""
    return f"{r.get('vibe', '?')} vibe, {r.get('style', '?')} morphs on {r.get('timing', '?')} timing, {fx}, look {r.get('look', '?')}{idea}"


def montage_list(js):
    d = json.loads(js.read_text(encoding="utf-8"))
    rows, t0 = [], d["song_start"]
    for s in d["slots"]:
        rows.append(f"| {mmss(s['song_in'] - t0)} to {mmss(s['song_out'] - t0)} | {s['label']} | {describe(s['label'])} |")
    rows.append(f"| {mmss(d['title'] - t0)} | title | Xenoform over the last shot, the song plays out |")
    return "| Time | Shot | What it is |\n| --- | --- | --- |\n" + "\n".join(rows)


def demo_list(js, copy):
    d = json.loads(js.read_text(encoding="utf-8"))
    text = {r["id"]: r["text"] for r in json.loads(Path(copy).read_text(encoding="utf-8"))["lines"]}
    rows = [f"| 0:00.0 | intro | the montage's opening (song alone) |"]
    for s in d["segments"]:
        rows.append(f"| {mmss(s['start'])} | {s['id']} | {text.get(s['id'], '')[:110]} |")
    return "| Time | Scene | First line said |\n| --- | --- | --- |\n" + "\n".join(rows)


def sheet(src, dest, step, w, h):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
                    f"fps=1/{step},scale={w}:{h},drawtext=fontfile='{FONT}':text='%{{pts\\:hms}}':x=6:y=6:fontsize=18:"
                    f"fontcolor=yellow:box=1:boxcolor=black@0.6,tile=8x8", "-q:v", "3", str(dest)], check=False)


def main():
    n = int(sys.argv[1])
    out = ROOT / f"round{n}"
    out.mkdir(parents=True, exist_ok=True)
    vids = [("montage_16x9", DESK / "review720_montage.mp4", 1.0, 240, 135),
            ("montage_9x16", DESK / "review540_montage_9x16.mp4", 1.0, 108, 192),
            ("demo_16x9", DESK / "review720_demo.mp4", 2.0, 240, 135),
            ("demo_9x16", DESK / "review540_demo_9x16.mp4", 2.0, 108, 192),
            ("long_16x9", DESK / "review540_long.mp4", 6.0, 240, 135)]
    for name, src, step, w, h in vids:
        shutil.copy2(src, out / f"{name}.mp4")
        sheet(src, out / f"{name}_sheet_%02d.jpg", step, w, h)
    lists = {"Montage (16:9 and 9:16, same cut)": montage_list(M / "xenoform_montage.json"),
             "Demo (16:9 and 9:16, same cut)": demo_list(HERE / f"short_af_heart_{sys.argv[2] if len(sys.argv) > 2 else 'v14'}.json",
                                                         r"C:\Projects\xenoform-rc2\docs\demo\short_voice.json")}
    req = [f"# Xenoform video review, round {n} (from Claude, for Owly)", "",
           "Tys asked for a gauntlet: you review, I fix what holds up, then the next round. Judge as a viewer seeing it cold,",
           "and as Tys would: he wants it slick, on the beat, every morph clear and on interesting objects, no look shown",
           "twice in the montage, the first 20 seconds the strongest, the outputs on screen long enough to see, the voice",
           "natural with pauses, nothing boring, unclear or repeated, nothing that shakes or zooms on the app screens.", "",
           "Tys, 30 Oct: the montage is its own standalone music video now; objects should be symbolic or iconic, not generic.", "",
           "## Files in this folder",
           "- `montage_16x9.mp4`, `montage_9x16.mp4`: the montage, now its own music video on the whole of Tys's Glitch Out (no voice).",
           "- `demo_16x9.mp4`, `demo_9x16.mp4`: the contest demo (must stay under 2:00).",
           "- `long_16x9.mp4`: the long walkthrough (opens on the montage's two minutes from 1:56 to its title).",
           "- `*_sheet_NN.jpg`: contact sheets, the time on every frame (montage 1 s apart, demo 2 s, long 6 s).", "",
           "## How to answer",
           "Write `OWLY_NOTES.md` in this folder, one line an issue, most important first:",
           "`video | time (m:ss) | what is wrong | what you would do instead`",
           "Say `no notes` for a video that is fine. Keep it to what you would actually change; I fix the ones that hold up",
           "and say which and why for the rest in round " + str(n + 1) + ".", ""]
    answer = M / f"response_round{n - 1}.md"  # what was done with the last round's notes, and what was not and why
    if answer.exists():
        req += [answer.read_text(encoding="utf-8"), ""]
    for title, table in lists.items():
        req += [f"## {title}", "", table, ""]
    (out / "REVIEW_REQUEST.md").write_text("\n".join(req), encoding="utf-8")
    print(out, sorted(p.name for p in out.iterdir()))


main()
