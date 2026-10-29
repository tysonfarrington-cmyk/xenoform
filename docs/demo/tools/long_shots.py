"""The long walkthrough's extra screen shots (the short's are reused), recorded like shots.py into rec/<name>/.

    python long_shots.py prep tour drop ideaintro ideafeel library stylechips timing fxchips foreshadow knobs tabs share setup
"""
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rec"))
sys.path.insert(0, str(HERE))
import cdp  # noqa: E402
from shots import DESK, cast, drag, end, goto, prep, reopen, soft  # noqa: E402


async def click_through(p, act, values, pause=1.3, mark=True):
    for v in values:
        await p.click(f'[data-act={act}][data-value="{v}"]', ms=550)
        if mark:
            p.mark(f"{act}_{v}")
        await asyncio.sleep(pause)


async def tour(p):
    """The whole desk, top to bottom, slowly."""
    await p.js("window.scrollTo(0, 0); 1")
    await asyncio.sleep(0.6)
    await cast(p, "tour")
    await asyncio.sleep(1.2)
    height = await p.js("document.documentElement.scrollHeight - innerHeight")
    steps = 14
    for k in range(steps):
        await p.js(f"window.scrollTo({{top: {int(height * (k + 1) / steps)}, behavior: 'smooth'}}); 1")
        await asyncio.sleep(0.75)
    await asyncio.sleep(0.8)
    await p.js("window.scrollTo({top: 0, behavior: 'smooth'}); 1")
    await asyncio.sleep(1.5)
    await end(p, "tour")


async def drop(p):
    await p.js("window.scrollTo(0, 0); 1")
    await asyncio.sleep(0.5)
    await cast(p, "drop")
    await asyncio.sleep(0.6)
    await p.highlight("#drop-open", 8)
    await asyncio.sleep(2.2)
    await p.click("[data-act=open-drop]", ms=600)
    p.mark("play_drop")
    await asyncio.sleep(3.5)
    await p.highlight(None)
    await end(p, "drop")


async def ideaintro(p):
    await p.scroll_to("#easy-idea", "center", 1.0)
    await cast(p, "ideaintro")
    await asyncio.sleep(0.6)
    await p.highlight("#easy-idea", 8)
    await asyncio.sleep(2.6)
    await p.highlight(None)
    await soft(p.click(None, "Other examples", ms=600), "examples")
    p.mark("examples")
    await asyncio.sleep(2.4)
    await soft(p.click(None, "Other examples", ms=400), "examples 2")
    await asyncio.sleep(2.2)
    await end(p, "ideaintro")


async def ideafeel(p):
    await p.js("(() => { const i = document.getElementById('easy-idea'); i.value = ''; i.dispatchEvent(new Event('input', {bubbles: true})); return 1; })()")
    await p.scroll_to("#easy-idea", "center", 1.0)
    await cast(p, "ideafeel")
    await asyncio.sleep(0.5)
    await p.click("#easy-idea", ms=500)
    await p.type("a wet street at night, moody and punchy", 0.06)
    p.mark("typed")
    await soft(p.wait_for("(document.getElementById('easy-idea-reading')||{}).textContent.toLowerCase().includes('moody')", 25, 0.3), "chips")
    await asyncio.sleep(0.5)
    await soft(p.scroll_to("#easy-idea-reading", "center", 0.8), "chips scroll")
    await p.highlight("#easy-idea-reading", 8)
    p.mark("chips")
    await asyncio.sleep(3.0)
    await p.highlight(None)
    await soft(p.scroll_to(".simple-knobs", "center", 1.0), "knobs scroll")
    await p.highlight(".simple-knobs", 6)
    p.mark("knobs")
    await asyncio.sleep(2.6)
    await p.highlight(None)
    await end(p, "ideafeel")


async def library(p):
    await p.js("(() => { const d = document.getElementById('fine-tune'); if (d && !d.open) d.open = true; return 1; })()")
    await asyncio.sleep(1.0)
    await soft(p.scroll_to(".library-row", "center", 1.0), "library scroll")
    await cast(p, "library")
    await asyncio.sleep(0.6)
    await soft(p.highlight(".library-row", 8), "library hl")
    await asyncio.sleep(2.6)
    await p.highlight(None)
    await soft(p.scroll_to(".chain-strip", "center", 1.2), "chain scroll")
    await soft(p.highlight(".chain-strip", 8), "chain hl")
    p.mark("chain")
    await asyncio.sleep(3.0)
    await p.highlight(None)
    await end(p, "library")
    await p.js("(() => { const d = document.getElementById('fine-tune'); if (d) d.open = false; return 1; })()")


async def stylechips(p):
    await p.scroll_to("[data-act=easy-morph-style][data-value=melt]", "center", 1.0)
    await cast(p, "stylechips")
    await asyncio.sleep(0.5)
    await click_through(p, "easy-morph-style", ("melt", "shatter", "bloom", "spin", "fold", "auto"), 0.9)
    await asyncio.sleep(0.8)
    await end(p, "stylechips")


async def timing(p):
    await p.scroll_to("[data-act=easy-morph-timing][data-value=smooth]", "center", 1.0)
    await cast(p, "timing")
    await asyncio.sleep(0.5)
    await click_through(p, "easy-morph-timing", ("smooth", "beat", "snap"), 1.8)
    await click_through(p, "easy-morph-timing", ("smooth",), 0.8, mark=False)
    await end(p, "timing")


async def fxchips(p):
    await p.scroll_to("[data-act=easy-effect]", "center", 1.0)
    await cast(p, "fxchips")
    await asyncio.sleep(0.5)
    for label in ("Dither hits", "Feedback", "Kaleido", "Slit-scan"):
        await soft(p.click("[data-act=easy-effect]", label, ms=500), label)
        await asyncio.sleep(0.9)
    await asyncio.sleep(1.0)
    for label in ("Dither hits", "Feedback", "Kaleido", "Slit-scan"):  # back as they were
        await soft(p.js(f"(() => {{ const b = [...document.querySelectorAll('[data-act=easy-effect]')].find((e) => e.textContent.trim().startsWith({label!r})); b && b.click(); return 1; }})()"), label)
        await asyncio.sleep(0.15)
    await end(p, "fxchips")


async def foreshadow(p):
    await p.scroll_to("[data-act=easy-foreshadow][data-value=trace]", "center", 1.0)
    await cast(p, "foreshadow")
    await asyncio.sleep(0.5)
    await click_through(p, "easy-foreshadow", ("trace", "slices", "silhouette"), 1.4)
    await click_through(p, "easy-scenes", ("mix",), 1.6)
    await click_through(p, "easy-foreshadow", ("auto",), 0.3, mark=False)
    await click_through(p, "easy-scenes", ("off",), 0.6, mark=False)
    await end(p, "foreshadow")


async def knobs(p):
    await p.scroll_to(".xf-knobs", "center", 1.0)
    await cast(p, "knobs")
    await asyncio.sleep(0.5)
    for k in ("intensity", "speed", "chaos", "glow"):
        r = await p.rect(f'.xf-knob[data-k="{k}"]')
        if not r:
            continue
        await p.move(r["x"], r["y"], 450)
        await p.js(f"window.__rec.highlight(document.querySelector('.xf-knob[data-k=\"{k}\"]'), 10)")
        p.mark(f"knob_{k}")
        await asyncio.sleep(1.2)
    await p.highlight(None)
    await asyncio.sleep(0.6)
    await end(p, "knobs")


async def tabs(p):
    await reopen(p)
    await p.scroll_to("#lane-track", "center", 1.0)
    await cast(p, "tabs")
    await asyncio.sleep(0.5)
    await p.click('[data-act=easy-tl-shot][data-index="4"]', ms=600)
    p.mark("open")
    await asyncio.sleep(1.4)
    await soft(p.scroll_to(".tl-tabs", "start", 0.8), "tabs scroll")
    for tab in ("shot", "look", "join", "gpu"):
        await soft(p.click(f"[data-act=easy-tl-tab][data-value={tab}]", ms=550), tab)
        p.mark(f"tab_{tab}")
        await asyncio.sleep(3.0)
    await end(p, "tabs")


async def share(p):
    await reopen(p)
    await soft(p.scroll_to("[data-act=easy-share]", "center", 1.0), "share scroll")
    await cast(p, "share")
    await asyncio.sleep(0.5)
    for sel in ("[data-act=easy-share]", "[data-act=easy-hook]", "[data-act=easy-edit-open]", "[data-act=easy-copy-recipe]"):
        r = await p.rect(sel)
        if r:
            await p.move(r["x"], r["y"], 500)
            await p.js(f"window.__rec.highlight(document.querySelector({sel!r}), 6)")
            p.mark(sel.split("=")[1].rstrip("]"))
            await asyncio.sleep(1.5)
    await p.highlight(None)
    await asyncio.sleep(0.5)
    await end(p, "share")


async def variations(p):
    await goto(p, DESK)
    sel = "[data-act=easy-batch]"
    await p.scroll_to(sel, "center", 1.0)
    await cast(p, "variations")
    await asyncio.sleep(0.5)
    await p.js(f"window.__rec.highlight(document.querySelector({sel!r}).closest('section, .panel, .easy-batch') || document.querySelector({sel!r}).parentElement, 8)")
    await asyncio.sleep(0.6)
    await click_through(p, "easy-batch-n", ("5",), 1.0)
    await click_through(p, "easy-batch-vary", ("vibe",), 1.4)
    await click_through(p, "easy-batch-n", ("3",), 0.4, mark=False)
    await click_through(p, "easy-batch-vary", ("seed",), 0.8, mark=False)
    await p.highlight(None)
    await end(p, "variations")


async def setup(p):
    await goto(p, DESK.replace("#simple", "#setup"))
    await soft(p.wait_for("!document.body.textContent.includes('Checking this machine')", 60, 1.0, "setup check"), "setup check")
    await asyncio.sleep(1.0)
    await p.js("window.scrollTo(0, 0); 1")
    await cast(p, "setup")
    await asyncio.sleep(1.5)
    for _ in range(3):
        await p.scroll_by(300, 1.3)
    await asyncio.sleep(0.8)
    await end(p, "setup")
    await goto(p, DESK)


SHOTS = {f.__name__: f for f in (prep, tour, drop, ideaintro, ideafeel, library, stylechips, timing, fxchips, foreshadow, knobs, tabs, share, variations, setup)}


async def main():
    p = await cdp.connect(9341, "")
    await cdp.viewport(p, 1440, 810, 4 / 3)
    await p.overlay()
    for name in sys.argv[1:]:
        print("==", name, flush=True)
        await SHOTS[name](p)
    await p.ws.close()
    await p.session.close()


if __name__ == "__main__":
    asyncio.run(main())
