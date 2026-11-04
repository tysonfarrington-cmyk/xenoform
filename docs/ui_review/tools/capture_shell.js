// The after shots for Setup and the machine and the side-page shell (setup-shell, 4 Nov 2026).
// Rerun: set NODE_PATH=C:\Projects\xf-uiaudit\node_modules, then: node capture_shell.js [baseUrl] [outDir]
// The five side pages and Setup are real answers from a desk. The five "mocked" shots (the Make gate, Setup with the required
// model missing, the ComfyUI banner, a failed whole song, a cut still rendering) change one answer on its way to the page
// (/api/setup, /api/comfy) or set the page's own state, to show what this machine does not have: the manifest says which.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.argv[2] || 'http://127.0.0.1:47360';
const OUT = process.argv[3] || path.resolve(__dirname, '..', 'after', 'shell');
fs.mkdirSync(OUT, { recursive: true });
const SIZES = [{ tag: '1366', width: 1366, height: 768 }, { tag: '375', width: 375, height: 812 }];
// the last two are long documents: their first screen shows the shell, the rest is the same table again
const SIDE = [['judges', '/judges', true], ['variations', '/variations', true], ['moves', '/moves', true], ['licences', '/licences', false], ['credits', '/credits', false]];
const manifest = [];

async function settle(page, ms = 900) {
  try { await page.waitForLoadState('networkidle', { timeout: 8000 }); } catch (e) { /* a desk polls forever */ }
  await page.waitForTimeout(ms);
}

async function shot(page, name, note, opts = {}) {
  const file = `${name}.jpg`;
  await page.screenshot({ path: path.join(OUT, file), type: 'jpeg', quality: 82, fullPage: opts.full !== false });
  const vp = page.viewportSize();
  const sideScroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  manifest.push({ file, url: page.url(), viewport: `${vp.width}x${vp.height}`, fullPage: opts.full !== false, note, mocked: !!opts.mocked, horizontalOverflowPx: sideScroll });
  console.log(file, sideScroll > 0 ? `OVERFLOW ${sideScroll}px` : 'ok', note);
}

// the real /api/setup answer with LTX 0.9.5 and its T5 encoder marked missing, as on a clean machine
function withMissingRequired(json) {
  const need = json.models.find((m) => m.required);
  need.present = false; need.ready = false;
  need.parts.forEach((p) => { p.present = false; });
  need.need_bytes = need.bytes; need.need_label = need.size_label; need.why_not = '';
  json.missing_required = [need.name];
  json.gate = { blocked: true, reliable: true, names: [need.short], bytes: need.bytes, size_label: need.size_label,
    line: `To make videos you need ${need.short}, ${need.size_label}`, button: `Get the ${need.size_label} model` };
  return json;
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome', args: ['--autoplay-policy=no-user-gesture-required'] });
  for (const size of SIZES) {
    const context = await browser.newContext({ viewport: { width: size.width, height: size.height }, deviceScaleFactor: 1, hasTouch: size.width < 600 });
    await context.addInitScript(() => { try { localStorage.setItem('xenoform.tutorial', JSON.stringify({ offered: true })); } catch (e) { /* none */ } });
    const page = await context.newPage();
    for (const [name, url, full] of SIDE) {
      await page.goto(BASE + url, { waitUntil: 'domcontentloaded' });
      await settle(page);
      await shot(page, `${name}-${size.tag}`, `the ${name} page`, { full });
    }
    // the judges page's empty screen (S2): the prompt and the slider on their tokens
    await page.goto(BASE + '/judges', { waitUntil: 'domcontentloaded' });
    await settle(page);
    const screen = await page.$('#screen');
    if (screen) { await screen.scrollIntoViewIfNeeded(); await page.screenshot({ path: path.join(OUT, `judges-empty-screen-${size.tag}.jpg`), type: 'jpeg', quality: 82, clip: await screen.boundingBox() });
      manifest.push({ file: `judges-empty-screen-${size.tag}.jpg`, url: page.url(), viewport: `${size.width}x${size.height}`, fullPage: false, note: 'the judges empty screen: the prompt in --x-text-2', mocked: false }); }
    // Setup with the real answer
    await page.goto(BASE + '/#setup', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.setup .model-card', { timeout: 20000 });
    await settle(page, 1200);
    await shot(page, `setup-${size.tag}`, 'Setup & models, the real /api/setup answer on this machine');
    // the desk's first screen and Setup on a clean machine (mocked): a page of its own, so the mock is there at the first load
    const clean = await context.newPage();
    await clean.route('**/api/setup*', async (route) => {
      const response = await route.fetch();
      await route.fulfill({ response, json: withMissingRequired(await response.json()) });
    });
    await clean.goto(BASE + '/#simple', { waitUntil: 'domcontentloaded' });
    await clean.waitForSelector('[data-act="easy-make"][data-gate="setup"]', { timeout: 30000 });
    await settle(clean, 1500);
    await shot(clean, `desk-make-gate-${size.tag}`, 'the first screen while LTX 0.9.5 is missing: Make reads Get the 11.5 GB model (answer mocked)', { full: false, mocked: true });
    await clean.evaluate(() => { location.hash = '#setup'; });
    await clean.waitForSelector('.setup-need', { timeout: 20000 });
    await settle(clean, 1200);
    await shot(clean, `setup-missing-${size.tag}`, 'Setup with the required model missing: what Make needs on top (answer mocked)', { mocked: true });
    await clean.close();
    // a ComfyUI that does not answer: the banner and the facts (mocked)
    const down = await context.newPage();
    await down.route('**/api/comfy*', (route) => route.fulfill({ json: { ok: false } }));
    await down.goto(BASE + '/#simple', { waitUntil: 'domcontentloaded' });
    await down.waitForSelector('#comfy-banner', { timeout: 30000 });
    await settle(down, 1500);
    await shot(down, `desk-comfy-banner-${size.tag}`, 'ComfyUI not answering: the banner with the address, the facts say no render (answer mocked)', { full: false, mocked: true });
    await down.close();
    // a whole song that failed, and a cut still rendering in My videos: states a desk reaches only after hours of GPU, so the
    // page's own state is set the way the server's answers would set it (mocked)
    const made = await context.newPage();
    await made.goto(BASE + '/#simple', { waitUntil: 'domcontentloaded' });
    await made.waitForFunction(() => window.XENO_STATE && window.XENO_STATE() && window.XENO_STATE().easy && window.XENO_STATE().setup, null, { timeout: 30000 });
    await settle(made, 1200);
    await made.evaluate(() => {
      const s = window.XENO_STATE();
      s.easy.song = 'demo'; s.easy.songLabel = 'Demo'; s.easy.vibe = s.easy.vibe || 'chrome-mercury';
      const win = (index, job, status, detail) => [{ index, job_id: job, status, detail, progress: status === 'done' ? 1 : 0 }];
      const t = easySongSeconds() / 3;  // three passages that fill the song the page has loaded
      s.easy.songRun = { id: 'shot0001', status: 'failed', done: 2, of: 3, tier: 'draft', morphs: 11, line: 'A whole song in 3 passages', assembly: {},
        passages: [{ index: 0, role: 'intro', start: 0, end: t, name: 'Liquid chrome', vibe: 'chrome-mercury', morphs: 3, windows: win(0, 'j1', 'done', '') },
          { index: 1, role: 'drop', start: t, end: 2 * t, name: 'Liquid chrome', vibe: 'chrome-mercury', morphs: 5, windows: win(1, 'j2', 'error', 'ComfyUI ran out of memory on the second morph.') },
          { index: 2, role: 'outro', start: 2 * t, end: 3 * t, name: 'Liquid chrome', vibe: 'chrome-mercury', morphs: 3, windows: win(2, 'j3', 'done', '') }] };
      setEasyPhase('making'); render();
    });
    await settle(made, 600);
    await shot(made, `desk-song-failed-${size.tag}`, 'a whole song with one passage failed: the reason, Resume and Back to the song (state set in the page)', { full: false, mocked: true });
    await made.evaluate(() => {
      const s = window.XENO_STATE();
      s.easy.songRun = null;
      s.videos = [
        { id: 'run00001', created: '2026-11-04T14:02:00', seconds: 95, vibe: 'chrome-mercury', song: 'Glitch Out', recipe: 'xf1.a', energy: 'dense', aspect: '9:16', tier: 'draft', url: '/api/videos/31680167/video', hook: false, status: 'running', progress: 0.42 },
        { id: 'done0002', created: '2026-11-04T13:00:00', seconds: 300, vibe: 'neon-noir', song: 'Glitch Out', recipe: 'xf1.b', energy: 'dense', aspect: '9:16', tier: 'draft', url: '/api/videos/31680167/video', hook: false, status: 'done', progress: 1 }];
      setEasyPhase('choose'); render();
      document.getElementById('my-videos').scrollIntoView();
    });
    await settle(made, 800);
    await shot(made, `desk-my-videos-rendering-${size.tag}`, 'My videos: the cut still rendering says so and offers Open (state set in the page)', { full: false, mocked: true });
    await made.close();
    await context.close();
  }
  await browser.close();
  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 2));
  const over = manifest.filter((m) => m.horizontalOverflowPx > 0);
  console.log(over.length ? `${over.length} shots overflow sideways` : 'no shot scrolls sideways');
})().catch((err) => { console.error(err); process.exit(1); });
