"""Record the two cards (cards/cards.html) in my headless Edge into rec/built and rec/end, the "built" nodes cued to the
read: each box appears as its phrase is said (the phrase's share of the line's characters, after the segment's lead).

    python record_cards.py <voice read dir> [lead seconds]
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


async def record(p, name, url, seconds):
    await p.send("Page.navigate", {"url": url})
    await asyncio.sleep(0.8)
    await p.send("Page.reload", {"ignoreCache": True})  # #built -> #end is only a hash change
    await asyncio.sleep(2.0)
    await p.js("document.fonts.ready.then(() => 1)")
    await cast(p, name)
    await asyncio.sleep(0.05)
    await p.js("window.go()")
    await asyncio.sleep(seconds)
    await end(p, name)


def long_cues(read_long, gap=0.7):
    """The long walkthrough's diagram runs under l36 alone (the Under the hood chapter before it has the song and the
    plan in full), read as two sentences (l36, l36_2) with the plan's gap: the song box with the line, the rest on its
    phrases."""
    copy_l = {r["id"]: r for r in json.loads(Path(r"C:\Projects\xenoform-rc2\docs\demo\long_voice.json").read_text(encoding="utf-8"))["lines"]}
    secs = {r["id"]: r["seconds"] for r in json.loads((read_long / "lines.json").read_text(encoding="utf-8"))["lines"]}
    start = {"l36": lead, "l36_2": lead + secs["l36"] + gap}

    def at(line, cue):
        b = copy_l[line].get("say", copy_l[line]["text"])
        return round(start[line] + secs[line] * b.index(cue) / len(b), 2)
    cues = [round(lead, 2), at("l36", "The plan becomes"), at("l36", "ComfyUI graphs"), at("l36_2", "LTX")]
    cues += [round(cues[-1] + 1.3, 2), at("l36_2", "all open weights")]
    return cues, start["l36_2"] + secs["l36_2"] + 1.5


async def main():
    p = await cdp.connect(9341, "")
    await cdp.viewport(p, 1440, 810, 4 / 3)
    base = (HERE / "cards" / "cards.html").as_uri()
    if len(sys.argv) > 3:  # a long read too: its diagram, cued over two lines
        cues, seconds = long_cues(Path(sys.argv[3]))
        print("long cues", cues, flush=True)
        await record(p, "built_long", f"{base}#built?d={','.join(map(str, cues))}", seconds)
    await record(p, "built", f"{base}#built?d={','.join(map(str, times))}", seconds)
    await record(p, "end", f"{base}#end", 7.0)
    await p.send("Page.navigate", {"url": "http://127.0.0.1:47326/#simple"})
    await p.ws.close()
    await p.session.close()


asyncio.run(main())
