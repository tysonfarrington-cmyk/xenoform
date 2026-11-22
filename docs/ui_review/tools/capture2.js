// Phase 2: the finished cut's screens. Rerun: NODE_PATH=C:\Projects\xf-uiaudit\node_modules node capture2.js [baseUrl]
// Never presses Make/Render/Re-render/Regenerate/Generate/Dream/Queue/Grow/Apply/Reset/Re-cut.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const BASE = process.argv[2] || 'http://127.0.0.1:47340';
const JOB = '31680167';
const OUT = 'C:/Projects/xf-uireview/docs/ui_review/shots';
const MF = path.join(OUT, 'manifest.json');
let manifest = JSON.parse(fs.readFileSync(MF, 'utf8')).filter(m => !/^(4\d|50)/.test(m.file));
const added = [];
let errs = { page: new Set(), con: new Set() };
const wait = (p, ms) => p.waitForTimeout(ms);
function hook(p) {
  p.on('pageerror', e => errs.page.add(String(e.message).slice(0, 160)));
  p.on('console', m => { if (m.type() === 'error') errs.con.add(m.text().slice(0, 160)); });
}
async function settle(p, ms = 1500) { try { await p.waitForLoadState('networkidle', { timeout: 8000 }); } catch (e) {} await wait(p, ms); }
async function shot(p, file, note, full = true) {
  const f = file + '.jpg'; const vp = p.viewportSize();
  try { await p.screenshot({ path: path.join(OUT, f), type: 'jpeg', quality: 80, fullPage: full }); } catch (e) { note += ' [SHOT FAILED ' + e.message.slice(0, 80) + ']'; }
  added.push({ file: f, url: p.url(), viewport: vp.width + 'x' + vp.height + (full ? ' fullPage' : ' viewport'), note, pageErrors: [...errs.page], consoleErrors: [...errs.con] });
  errs = { page: new Set(), con: new Set() };
  console.log(f, note);
}
function skip(file, note) { added.push({ file: file + '.jpg', url: '', viewport: '', note: 'NOT CAPTURED: ' + note, pageErrors: [], consoleErrors: [] }); console.log('SKIP', file, note); }
async function step(file, fn) { try { await fn(); } catch (e) { skip(file, String(e.message).split('\n')[0].slice(0, 200)); } }
async function reopen(p) {
  await p.goto(BASE + '/', { waitUntil: 'networkidle' });
  await settle(p);
  await p.locator('#tutorial-later').click({ timeout: 2000 }).catch(() => {});
  const card = p.locator('#my-videos > *').filter({ hasText: 'Glitch Out (30 s cut)' }).locator('button[data-act="video-open"]').first();
  if (await card.count()) await card.click({ timeout: 5000 });
  else await p.locator('#my-videos button[data-act="video-open"]').first().click({ timeout: 5000 });
  await settle(p, 3000);
}
async function scrollTo(p, sel) { await p.evaluate((s) => { const e = document.querySelector(s); if (e) e.scrollIntoView({ block: 'start' }); }, sel); await wait(p, 700); }

(async () => {
  const b = await chromium.launch({ channel: 'chrome', args: ['--autoplay-policy=no-user-gesture-required', '--use-angle=d3d11'] });
  let ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  let p = await ctx.newPage(); hook(p);

  await step('40_result_full', async () => {
    await reopen(p);
    if (!/result/.test(p.url())) throw new Error('did not reach result: ' + p.url());
    await shot(p, '40_result_full', 'Reopen on the Glitch Out (30 s cut) card');
    await p.evaluate(() => window.scrollTo(0, 0)); await wait(p, 500);
    await shot(p, '40b_result_viewport', 'result viewport', false);
  });
  await step('41_guardrails_open', async () => {
    await p.evaluate(() => { const d = document.querySelector('details.guardnotes'); if (!d) throw new Error('no guardnotes'); d.open = true; d.querySelector('summary').scrollIntoView({ block: 'center' }); });
    await wait(p, 600);
    const t = await p.evaluate(() => document.querySelector('details.guardnotes').innerText.replace(/\s+/g, ' ').slice(0, 220));
    await shot(p, '41_guardrails_open', 'guardnotes open: ' + t, false);
  });
  await step('42_shot_drawer_shot', async () => {
    await p.locator('[data-act="easy-tl-shot"]').first().click({ timeout: 5000 });
    await wait(p, 1000);
    const tabs = await p.evaluate(() => Array.from(document.querySelectorAll('[data-act="easy-tl-tab"]')).map(e => e.dataset.value + '=' + e.textContent.trim()).join(', '));
    console.log('TABS', tabs);
    await scrollTo(p, '.tl-drawer-head');
    await p.locator('[data-act="easy-tl-tab"][data-value="shot"]').click({ timeout: 4000 }).catch(() => {});
    await wait(p, 700); await scrollTo(p, '.tl-drawer-head');
    await shot(p, '42_shot_drawer_shot', 'drawer, Shot tab. tabs: ' + tabs, false);
    for (const [v, f] of [['look', '42b_shot_drawer_look'], ['join', '42c_shot_drawer_join'], ['gpu', '42d_shot_drawer_regenerate']]) {
      await step(f, async () => {
        if (v === 'join') { await p.locator('[data-act="easy-tl-shot"]').nth(1).click({ timeout: 4000 }); await wait(p, 800); }
        const t = p.locator(`[data-act="easy-tl-tab"][data-value="${v}"]`);
        if (!(await t.count())) throw new Error('tab ' + v + ' absent' + (v === 'join' ? ' on shot 1 (no join before first shot)' : ''));
        await t.click({ timeout: 4000 }); await wait(p, 800); await scrollTo(p, '.tl-drawer-head');
        await shot(p, f, 'drawer tab ' + v, false);
      });
    }
  });
  await step('43_seam', async () => {
    await p.locator('[data-act="easy-tl-bound"][title^="The join into shot 10 "]').click({ timeout: 5000 });
    await wait(p, 1000); await scrollTo(p, '.tl-drawer-head');
    await shot(p, '43_seam', 'join into shot 10', false);
    await p.locator('[data-act="easy-tl-close"]').first().click().catch(() => {});
    await wait(p, 500);
  });
  await step('44_share_row', async () => {
    const ok = await p.evaluate(() => { const e = document.querySelector('[data-act="easy-share"]'); if (!e) return false; e.scrollIntoView({ block: 'center' }); return true; });
    if (!ok) throw new Error('no share button');
    await wait(p, 700);
    await shot(p, '44_share_row', 'Share section', false);
  });
  await step('45_side_column_hidden', async () => {
    await p.locator('[data-act="easy-knobs-fold"]').first().click({ timeout: 4000 });
    await wait(p, 1000);
    await shot(p, '45_side_column_hidden', 'after Hide');
    const sh = p.locator('[data-act="easy-knobs-fold"]').first();
    await sh.click({ timeout: 4000 }).catch(() => {});
    await wait(p, 800);
  });
  // vj link: from vjUrl() if exposed, else the first screen's WIP drawer link
  await step('50_vj_from_cut', async () => {
    let href = await p.evaluate(() => { try { return typeof vjUrl === 'function' ? vjUrl() : null; } catch (e) { return null; } });
    let how = 'vjUrl() on the result screen';
    if (!href) href = await p.evaluate(() => { const a = Array.from(document.querySelectorAll('a')).find(x => /\/vj/.test(x.getAttribute('href') || '')); return a && a.getAttribute('href'); });
    if (!href) {
      await p.locator('[data-act="easy-again"]').first().click({ timeout: 4000 });
      await settle(p, 1500);
      await p.evaluate(() => { const s = Array.from(document.querySelectorAll('summary')).find(x => x.textContent.trim().startsWith('Work in progress')); if (s) s.parentElement.open = true; });
      href = await p.evaluate(() => { const a = Array.from(document.querySelectorAll('a')).find(x => /\/vj/.test(x.getAttribute('href') || '')); return a && a.getAttribute('href'); });
      how = 'first screen Work in progress link';
    }
    if (!href) throw new Error('no VJ link found anywhere');
    const q = await ctx.newPage(); hook(q);
    await q.setViewportSize({ width: 1280, height: 720 });
    await q.goto(new URL(href, BASE).toString(), { waitUntil: 'networkidle' });
    await wait(q, 3000);
    const info = await q.evaluate(() => ({ vids: Array.from(document.querySelectorAll('video')).map(v => v.currentSrc || v.src).slice(0, 4), jobInRoot: !!(window.VJ && VJ.S && VJ.S.scenes), q: location.search }));
    await shot(q, '50_vj_from_cut', 'link from ' + how + ': ' + href + ' ; page video srcs: ' + JSON.stringify(info.vids) + ' ; query ' + info.q + ' (the link carries track and stems only, no job id: plays library loops, not the cut morphs)', false);
    await q.close();
  });
  // 49
  await step('49_my_videos_done', async () => {
    await p.goto(BASE + '/', { waitUntil: 'networkidle' }); await settle(p);
    await scrollTo(p, '#my-videos');
    await shot(p, '49_my_videos_done', 'My videos with the finished card', false);
  });
  // 48 seed
  await step('48_seed_json', async () => {
    const q = await ctx.newPage(); hook(q);
    await q.setViewportSize({ width: 1440, height: 900 });
    await q.goto(BASE + '/api/jobs/' + JOB + '/seed', { waitUntil: 'networkidle' });
    await wait(q, 800);
    await shot(q, '48_seed_json', '/api/jobs/' + JOB + '/seed', false);
    await q.close();
  });
  await ctx.close();

  await step('46_result_mobile', async () => {
    const c2 = await b.newContext({ viewport: { width: 430, height: 932 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 });
    const q = await c2.newPage(); hook(q);
    await reopen(q);
    await shot(q, '46_result_mobile', 'reopened in a fresh mobile context');
    await c2.close();
  });
  await step('47_result_narrow', async () => {
    const c3 = await b.newContext({ viewport: { width: 1024, height: 768 } });
    const q = await c3.newPage(); hook(q);
    await reopen(q);
    await shot(q, '47_result_narrow', 'reopened at 1024x768');
    await c3.close();
  });

  manifest = manifest.concat(added).sort((a, c) => a.file.localeCompare(c.file));
  fs.writeFileSync(MF, JSON.stringify(manifest, null, 1));
  console.log('done', added.length);
  await b.close();
})().catch(e => { console.log('FATAL', e); process.exit(1); });
