import asyncio,sys,time,os
from playwright.async_api import async_playwright
SH=sys.argv[1]; OUT=f"cap_{SH}"; os.makedirs(OUT,exist_ok=True)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(channel="msedge")
        pg=await b.new_page(viewport={"width":540,"height":960},device_scale_factor=2)
        await pg.goto("http://127.0.0.1:47330/"); await pg.wait_for_timeout(2500)
        for t in ["Not now","Skip"]:
            try: await pg.get_by_role("button",name=t).first.click(timeout=1500)
            except Exception: pass
        await pg.add_style_tag(content="[class*=tutorial],[class*=coach],[class*=toast]{display:none!important}")
        idx=[0]; log=open(OUT+".txt","w"); last=[time.time()]
        async def snap(n=1):
            for _ in range(n):
                await pg.screenshot(path=f"{OUT}/{idx[0]:04d}.jpg",type="jpeg",quality=92)
                t=time.time(); log.write(f"file '{OUT}/{idx[0]:04d}.jpg'\nduration {t-last[0]:.3f}\n") if idx[0] else None; last[0]=t; idx[0]+=1
        async def scroll_to(sel,frames=14):
            y0=await pg.evaluate("scrollY"); y1=await pg.evaluate(f"(()=>{{const e=document.querySelector('{sel}');return e.getBoundingClientRect().top+scrollY-70}})()")
            for k in range(1,frames+1):
                x=k/frames; e=x*x*(3-2*x); await pg.evaluate(f"scrollTo(0,{y0+(y1-y0)*e})"); await snap()
        if SH=="vibes":
            await pg.evaluate("(()=>{const e=document.querySelector('.vibe-card');scrollTo(0,e.getBoundingClientRect().top+scrollY-200)})()"); await pg.wait_for_timeout(800)
            await snap(4)
            for v in ["ferrofluid","chrome-mercury","origami-noir","liquid-gold"]:
                c=pg.locator(f'.vibe-card[data-vibe="{v}"]'); await c.hover(); await snap(14)
        else:
            await pg.evaluate("(()=>{const e=document.querySelector('#my-videos');scrollTo(0,e.getBoundingClientRect().top+scrollY-70)})()")
            await pg.wait_for_timeout(1500); await snap(4)
            await pg.evaluate("document.querySelectorAll('#my-videos video').forEach(v=>{v.muted=true;v.preload='auto';v.load()})"); await pg.wait_for_timeout(4000)
            tiles=pg.locator('#my-videos video, #my-videos .tile, #my-videos figure')
            n=await tiles.count(); print("tiles",n)
            for i in range(min(n,6)):
                try: await tiles.nth(i).hover(timeout=2000)
                except Exception: pass
                await snap(12)
        log.write(f"file '{OUT}/{idx[0]-1:04d}.jpg'\n"); log.close(); print(SH,idx[0]); await b.close()
asyncio.run(main())

