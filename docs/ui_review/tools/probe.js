// Probe: can Playwright drive the installed Chrome against the review desk and save a jpeg?
const { chromium } = require('playwright');
const [,, base, out] = process.argv;
(async () => {
  const b = await chromium.launch({ channel: 'chrome', args: ['--autoplay-policy=no-user-gesture-required', '--use-angle=d3d11'] });
  const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push('pageerror ' + e.message));
  p.on('console', m => { if (m.type() === 'error') errs.push('console ' + m.text().slice(0, 160)); });
  await p.goto(base + '/', { waitUntil: 'networkidle', timeout: 30000 });
  await p.waitForTimeout(2000);
  await p.screenshot({ path: out, type: 'jpeg', quality: 82, fullPage: true });
  const h = await p.evaluate(() => ({ scrollHeight: document.documentElement.scrollHeight, title: document.title, videos: document.querySelectorAll('video').length, buttons: document.querySelectorAll('button').length }));
  console.log(JSON.stringify({ ok: true, h, errs }));
  await b.close();
})().catch(e => { console.log(JSON.stringify({ ok: false, err: String(e) })); process.exit(1); });
