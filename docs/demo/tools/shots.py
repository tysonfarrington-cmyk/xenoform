"""The short walkthrough's screen shots, recorded from desk 47325 in my headless Edge (port 9341) at 1440x810 CSS,
4/3 scale, so the frames are 1920x1080. Each shot goes to rec/<name>/ (frames.txt + marks.txt); the page stays
loaded between shots, so they run in the order given.

    python shots.py prep vibe idea make wait timeline playhead clips tiers connect
"""
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "rec"))
import cdp  # noqa: E402

REC = HERE / "rec"
DESK = "http://127.0.0.1:47326/#simple"
LINE = "underwater"  # Tys, 29 Oct: not racing ("you want to see cars driving not morphing")
SONG = r"C:\Users\tyson\OneDrive\Desktop\suno-demos\batch2\XF_HipHop_BoomBap_01.mp3"  # his Suno track, his pick
SHOT = "3"  # the timeline shot the Look edit is made on


def cut_id():
    """The cut made on camera (wait() writes it)."""
    f = REC / "cut.txt"
    return f.read_text().strip() if f.exists() else "5ce3c134"


async def goto(p, url):
    """Load the desk afresh: a navigation that only changes the hash keeps the old page and its stale lists."""
    await p.send("Page.navigate", {"url": url})
    await asyncio.sleep(0.8)
    await p.send("Page.reload", {"ignoreCache": True})
    await asyncio.sleep(2.5)


async def soft(coro, what):
    try:
        return await coro
    except Exception as exc:
        print("SKIPPED", what, exc, flush=True)


async def drag(p, sel, frac_from, frac_to, steps=14):
    r = await p.rect(sel)
    if not r:
        raise RuntimeError(f"no slider {sel}")
    x0 = r["x"] - r["w"] / 2 + r["w"] * frac_from
    x1 = r["x"] - r["w"] / 2 + r["w"] * frac_to
    await p.move(x0, r["y"], 500)
    await p.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x0, "y": r["y"], "button": "left", "clickCount": 1})
    for k in range(1, steps + 1):
        x = x0 + (x1 - x0) * k / steps
        await p.js(f"window.__rec.move({x}, {r['y']}, 40)")
        await p.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": r["y"], "button": "left", "buttons": 1})
        await asyncio.sleep(0.045)
    await p.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x1, "y": r["y"], "button": "left", "clickCount": 1})


async def cast(p, name):
    d = REC / name
    if d.exists():
        for f in d.iterdir():
            f.unlink()
    p.frame_no = 0
    await p.start_cast(d)
    p.mark(f"{name}_start")


async def end(p, name):
    p.mark(f"{name}_end")
    await p.stop_cast()
    print(name, "frames", p.frame_no, flush=True)


async def prep(p):
    await goto(p, DESK)
    await asyncio.sleep(2.5)
    await p.js("localStorage.setItem('xenoform.tutorial', JSON.stringify({offered: true})); 1")
    await p.send("Page.reload")
    await asyncio.sleep(4.0)
    await p.js("window.__rec.mount(); window.scrollTo(0, 0); 1")
    # a clean start: Objects, Draft, an empty idea line, Neon noir picked so None is a change on camera
    for sel in ("[data-act=easy-source][data-value=objects]", "[data-act=easy-tier][data-value=draft]",
                "[data-act=easy-vibe][data-vibe=neon-noir]"):
        await p.js(f"(() => {{ const e = document.querySelector({sel!r}); if (e && !e.classList.contains('on')) e.click(); return 1; }})()")
        await asyncio.sleep(0.8)
    await p.js("(() => { const i = document.getElementById('easy-idea'); if (i) { i.value = ''; i.dispatchEvent(new Event('input', {bubbles: true})); } window.scrollTo(0, 0); return 1; })()")
    await asyncio.sleep(1.0)
    # the song: Tys's own, loaded through the desk's own file input, then 30 s around its drop at Fast Final
    if not await p.js("!!(state.easy && /BoomBap/i.test((state.easy.songLabel || '') + (state.easy.song || '')))"):
        doc = await p.send("DOM.getDocument", {"depth": 1})
        node = await p.send("DOM.querySelector", {"nodeId": doc["root"]["nodeId"], "selector": "#easy-file"})
        await p.send("DOM.setFileInputFiles", {"files": [SONG], "nodeId": node["nodeId"]})
        await p.wait_for("!!document.querySelector('[data-act=open-drop]:not([disabled])')", 300, 1.0, "song analysed")
        await asyncio.sleep(1.0)
    # Cloud Final with its credits tick (Tys, 29 Oct: "you may as well use our credits as well"): the Make on camera is
    # the real thing, LTX-2.5 on Comfy Cloud, about five minutes instead of a Fast Final's twelve
    for sel in ('[data-act=easy-length][data-value="30"]', "[data-act=easy-tier][data-value=cloud]"):
        await p.js(f"(() => {{ const e = document.querySelector({sel!r}); if (e && !e.classList.contains('on')) e.click(); return 1; }})()")
        await asyncio.sleep(1.0)
    await p.js("(() => { const c = document.querySelector('[data-act=easy-cloud-final-ok]'); if (c && !c.checked) c.click(); return !!c; })()")
    await asyncio.sleep(0.8)
    print("cloud tick", await p.js("!!(state.easy && state.easy.tier === 'cloud' && state.easy.cloudFinalOk)"), flush=True)
    await p.js("window.scrollTo(0, 0); window.__rec.move(980, 300, 0); 1")


async def vibe(p):
    await p.js("window.scrollTo(0, 0); 1")
    await asyncio.sleep(0.6)
    await cast(p, "vibe")
    await asyncio.sleep(0.6)
    r = await p.rect("label.upload")
    if r:
        await p.move(r["x"] + 260, r["y"], 650)
    await soft(p.highlight("#drop-open", 8), "drop hl")
    p.mark("song")
    await asyncio.sleep(1.8)
    await p.highlight(None)
    await p.scroll_to("[data-act=easy-vibe][data-vibe=liquid-gold]", "center", 1.1)
    for v in ("liquid-gold", "neon-noir", "ink-wash"):
        r = await p.rect(f"[data-act=easy-vibe][data-vibe={v}]")
        await p.move(r["x"], r["y"], 520)
        await asyncio.sleep(0.45)
    await p.click("[data-act=easy-vibe][data-vibe=none]", ms=650)
    p.mark("none_click")
    await asyncio.sleep(2.6)
    await end(p, "vibe")


async def idea(p):
    await p.scroll_to("#easy-idea", "center", 1.0)
    await cast(p, "idea")
    await asyncio.sleep(0.5)
    await p.click("#easy-idea", ms=600)
    await asyncio.sleep(0.3)
    p.mark("type_start")
    await p.type(LINE, 0.075)
    p.mark("type_end")
    await soft(p.wait_for("(document.getElementById('easy-idea-reading')||{}).textContent.toLowerCase().includes('underwater')", 25, 0.3), "chips")
    await asyncio.sleep(0.6)
    await soft(p.scroll_to("#easy-idea-reading", "center", 0.9), "chips scroll")
    await p.highlight("#easy-idea-reading", 8)
    p.mark("chips")
    await asyncio.sleep(3.2)
    await p.highlight(None)
    await end(p, "idea")


async def make(p):
    await p.js("window.scrollTo({top: 0, behavior: 'smooth'}); 1")
    await asyncio.sleep(1.0)
    await cast(p, "make")
    await asyncio.sleep(0.6)
    await p.click("button.easy-make", ms=650)
    p.mark("make_click")
    await asyncio.sleep(16)
    await end(p, "make")


async def wait(p):
    await p.wait_for("state && state.easy && state.easy.phase === 'result' && !!document.getElementById('player')", 40 * 60, 5.0, "result")
    job = await p.js("state.job && state.job.id")
    (REC / "cut.txt").write_text(str(job))
    print("result", job, flush=True)


async def reopen(p):
    """The made cut on its result screen (Reopen from My videos), unless it is already there."""
    if await p.js("!!document.getElementById('player') && !!document.getElementById('lane-track')"):
        return
    await goto(p, DESK)
    await asyncio.sleep(1.0)
    await p.js(f"(() => {{ const b = document.querySelector('[data-act=video-open][data-id=\"{cut_id()}\"]'); b && b.click(); return !!b; }})()")
    await p.wait_for("!!document.getElementById('player') && !!document.getElementById('lane-track')", 30, 0.5, "reopen")
    await asyncio.sleep(2.0)


async def timeline(p):
    await reopen(p)
    await p.scroll_to("#lane-track", "center", 1.2)
    await cast(p, "timeline")
    await asyncio.sleep(0.6)
    await p.click(f'[data-act=easy-tl-shot][data-index="{SHOT}"]', ms=650)
    await asyncio.sleep(1.2)
    await soft(p.scroll_to(".tl-tabs", "start", 0.9), "tabs scroll")
    await p.click("[data-act=easy-tl-tab][data-value=look]", ms=600)
    await asyncio.sleep(1.0)
    await soft(drag(p, ".tl-grade-in[data-key=hue]", 0.5, 0.25), "hue")
    await asyncio.sleep(0.5)
    await soft(drag(p, ".tl-grade-in[data-key=saturation]", 0.5, 0.85), "saturation")
    await asyncio.sleep(1.0)
    await p.click(".pending-bar [data-act=easy-apply]", ms=700, scroll=False)
    p.mark("apply_click")
    # the re-cut runs on the making screen, then the result comes back
    await soft(p.wait_for("state && state.easy && state.easy.phase !== 'result'", 10, 0.2, "making"), "making")
    await soft(p.wait_for("state && state.easy && state.easy.phase === 'result' && !!document.getElementById('player')", 600, 0.5, "recut"), "recut")
    p.mark("recut_done")
    await asyncio.sleep(0.5)
    await p.scroll_to("#lane-track", "center", 1.0)
    await asyncio.sleep(2.0)
    await end(p, "timeline")


async def playhead(p):
    await reopen(p)
    await p.js("document.getElementById('lane-track').scrollIntoView({block: 'end'}); window.scrollBy(0, 60); 1")
    await asyncio.sleep(1.0)
    await p.js("(() => { const v = document.getElementById('player'); v.muted = true; v.currentTime = 0; return v.play().then(() => 1).catch(String); })()")
    await cast(p, "playhead")
    await asyncio.sleep(7.0)
    await end(p, "playhead")
    await p.js("(() => { const v = document.getElementById('player'); v.pause(); return 1; })()")


async def clips(p):
    await goto(p, DESK)
    await asyncio.sleep(3.0)
    await p.scroll_to("[data-act=easy-source][data-value=clips]", "center", 1.0)
    await cast(p, "clips")
    await asyncio.sleep(0.5)
    await p.click("[data-act=easy-source][data-value=clips]", ms=650)
    p.mark("clips_click")
    await asyncio.sleep(2.2)
    # the free film pack button (29 Oct): the clips row fills with the pack's folder and its note
    if await p.js("document.querySelector('[data-act=easy-film-pack]') ? 1 : 0"):
        await p.click("[data-act=easy-film-pack]", ms=650)
        p.mark("pack_click")
        await asyncio.sleep(2.6)
    await end(p, "clips")
    await p.js("(() => { const e = document.querySelector('[data-act=easy-source][data-value=objects]'); e && e.click(); return 1; })()")
    await asyncio.sleep(1.0)


TIME_DD = "[...document.querySelectorAll('dt')].find((e) => e.textContent === 'Time' && e.offsetParent !== null).nextElementSibling"


async def tiers(p):
    await goto(p, DESK)
    await asyncio.sleep(3.5)
    await p.js("(() => { const d = document.getElementById('fine-tune'); if (d) d.open = false; window.scrollTo(0, 0); return 1; })()")
    await asyncio.sleep(0.6)
    await p.scroll_to("#fine-tune", "center", 1.0)
    await cast(p, "tiers")
    await asyncio.sleep(0.5)
    await p.click("#fine-tune > summary", ms=600)
    await asyncio.sleep(1.0)
    await p.scroll_to("[data-act=easy-tier][data-value=fast]", "center", 1.0)
    await p.js(f"window.__rec.highlight({TIME_DD}, 6)")
    await p.js("(() => { const e = document.querySelector('[data-act=easy-tier][data-value=draft]'); e && e.click(); return 1; })()")
    await asyncio.sleep(0.8)
    for v in ("fast", "final", "cloud"):
        await p.click(f"[data-act=easy-tier][data-value={v}]", ms=600, scroll=False)
        p.mark(f"tier_{v}")
        await asyncio.sleep(0.4)
        await p.js(f"window.__rec.highlight({TIME_DD}, 6)")
        await asyncio.sleep(1.6)
    await asyncio.sleep(0.8)
    await p.highlight(None)
    await end(p, "tiers")
    await p.js("(() => { const e = document.querySelector('[data-act=easy-tier][data-value=draft]'); e && e.click(); "
               "const d = document.getElementById('fine-tune'); if (d) d.open = false; return 1; })()")


async def connect(p):
    await p.send("Page.navigate", {"url": DESK.replace("#simple", "#connect")})
    await asyncio.sleep(3.0)
    await p.js("window.scrollTo(0, 0); 1")
    await cast(p, "connect")
    await asyncio.sleep(1.5)
    await p.scroll_by(320, 1.6)
    await p.scroll_by(320, 1.6)
    await asyncio.sleep(1.0)
    await end(p, "connect")
    await goto(p, DESK)


SHOTS = {f.__name__: f for f in (prep, vibe, idea, make, wait, timeline, playhead, clips, tiers, connect)}


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
