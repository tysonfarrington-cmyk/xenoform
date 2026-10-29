"""Record the two cards laid out for a phone (cards/cards_v.html, 540x960 CSS at 2x = 1080x1920) into rec/built_v and
rec/end_v, the "built" nodes cued to the read like record_cards.py.

    python record_cards_v.py <voice read dir> [lead seconds]
"""
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rec"))
import cdp  # noqa: E402
from shots import cast, end  # noqa: E402

read = Path(sys.argv[1])
lead = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
copy = {r["id"]: r for r in json.loads(Path(r"C:\Projects\xenoform-rc2\docs\demo\short_voice.json").read_text(encoding="utf-8"))["lines"]}
spoken = {r["id"]: r["seconds"] for r in json.loads((read / "lines.json").read_text(encoding="utf-8"))["lines"]}
# the line is four sentences read apart (built .. built_4, the plan's gap between them): each box comes up on its phrase
GAP = 0.7
SENT = ["built", "built_2", "built_3", "built_4"]
starts, at = {}, lead
for i in SENT:
    starts[i] = at
    at += spoken[i] + GAP
seconds = at - GAP + 1.5


def cue(line, phrase):
    say = copy[line].get("say", copy[line]["text"])
    return round(starts[line] + spoken[line] * say.index(phrase) / len(say), 2)


times = [cue("built", "the song is split"), cue("built_2", "The plan becomes"), cue("built_2", "ComfyUI graphs"),
         cue("built_3", "LTX renders"), 0.0, cue("built_4", "All open weights")]
times[4] = round(times[3] + 1.6, 2)  # "The cut" box follows LTX's; the line does not name it
print("cues", times, flush=True)


async def cast_v(p, name):
    """Like shots.cast, but the screencast is allowed 1080x1920 (its default cap of 1080 high gave 540x960 frames)."""
    d = HERE / "rec" / name
    if d.exists():
        for f in d.iterdir():
            f.unlink()
    p.frame_no = 0
    await p.start_cast(d, 1080, 1920)
    p.mark(f"{name}_start")


async def record(p, name, url, seconds):
    await p.send("Page.navigate", {"url": url})
    await asyncio.sleep(0.8)
    await p.send("Page.reload", {"ignoreCache": True})
    await asyncio.sleep(2.0)
    await p.js("document.fonts.ready.then(() => 1)")
    await cast_v(p, name)
    await asyncio.sleep(0.05)
    await p.js("window.go()")
    await asyncio.sleep(seconds)
    await end(p, name)


async def main():
    p = await cdp.connect(9341, "")
    await cdp.viewport(p, 1080, 1920, 1)  # the page is 1080x1920 itself (cards_v.html zooms its 540x960 layout 2x)
    base = (HERE / "cards" / "cards_v.html").as_uri()
    await record(p, "built_v", f"{base}#built?d={','.join(map(str, times))}", seconds)
    await record(p, "end_v", f"{base}#end", 7.0)
    await cdp.viewport(p, 1440, 810, 4 / 3)
    await p.send("Page.navigate", {"url": "http://127.0.0.1:47326/#simple"})
    await p.ws.close()
    await p.session.close()


asyncio.run(main())
