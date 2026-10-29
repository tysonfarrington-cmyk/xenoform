"""The montage's title (cards/title.html) as transparent PNGs, 1920x1080 and 1080x1920, from my headless Edge (9341).

    python title_png.py
"""
import asyncio
import base64
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rec"))
import cdp  # noqa: E402


async def main():
    p = await cdp.connect(9341, "")
    await p.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
    for name, (w, h), q in (("title_169.png", (1920, 1080), ""), ("title_916.png", (1080, 1920), "?v")):
        await cdp.viewport(p, w, h, 1)
        await p.send("Page.navigate", {"url": (HERE / "cards" / "title.html").as_uri() + q})
        await asyncio.sleep(1.2)
        await p.js("document.fonts.ready.then(() => 1)")
        await asyncio.sleep(0.3)
        shot = await p.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (HERE / "cards" / name).write_bytes(base64.b64decode(shot["data"]))
        print("wrote", name, flush=True)
    await p.send("Emulation.setDefaultBackgroundColorOverride", {})
    await p.send("Page.navigate", {"url": "about:blank"})
    await p.ws.close()
    await p.session.close()


asyncio.run(main())
