"""Record cards/underhood.html in my headless Edge into rec/underhood, each panel cued to its voice line. The lines are
read a sentence a wav (u1, u1_2, u1_3, u2 ...), the plan's gap between sentences; a panel comes up on its line's first.

    python record_underhood.py <long read dir> [lead seconds] [gap seconds]
"""
import asyncio
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rec"))
sys.path.insert(0, str(HERE))
import cdp  # noqa: E402
from shots import cast, end  # noqa: E402

read = Path(sys.argv[1])
lead = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
gap = float(sys.argv[3]) if len(sys.argv) > 3 else 0.7
rows = [r for r in json.loads((read / "lines.json").read_text(encoding="utf-8"))["lines"] if re.fullmatch(r"u\d(_\d+)?", r["id"])]
cues, t = [], lead
for r in rows:
    if "_" not in r["id"]:
        cues.append(round(t, 2))
    t += r["seconds"] + gap
total = t - gap + 1.5
print("cues", cues, "total", round(total, 1), flush=True)


async def main():
    p = await cdp.connect(9341, "")
    await cdp.viewport(p, 1440, 810, 4 / 3)
    url = (HERE / "cards" / "underhood.html").as_uri() + "#underhood?d=" + ",".join(map(str, cues))
    await p.send("Page.navigate", {"url": url})
    await asyncio.sleep(0.8)
    await p.send("Page.reload", {"ignoreCache": True})
    await asyncio.sleep(2.5)
    await p.js("document.fonts.ready.then(() => 1)")
    await cast(p, "underhood")
    await asyncio.sleep(0.05)
    await p.js("window.go()")
    await asyncio.sleep(total)
    await end(p, "underhood")
    await p.send("Page.navigate", {"url": "http://127.0.0.1:47326/#simple"})
    await p.ws.close()
    await p.session.close()


asyncio.run(main())
