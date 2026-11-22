// Rerun: set NODE_PATH=C:\Projects\xf-uiaudit\node_modules, then: node capture1.js [baseUrl]
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const BASE = process.argv[2] || 'http://127.0.0.1:47340';
const OUT = 'C:/Projects/xf-uireview/docs/ui_review/shots';
fs.mkdirSync(OUT, { recursive: true });
const SONGS = 'C:/Projects/xenoform-rc2/examples/songs/';
const manifest = [];
let errs = { page: new Set(), con: new Set() };
const T0 = Date.now();
const wait = (p, ms) => p.waitForTimeout(ms);

function hook(p) {
  p.on('pageerror', e => errs.page.add(String(e.message).slice(0, 160)));
  p.on('console', m => { if (m.type() === 'error') errs.con.add(m.text().slice(0, 160)); });
}
async function settle(p, ms = 1500) {
  try { await p.waitForLoadState('networkidle', { timeout: 8000 }); } catch (e) {}
  await wait(p, ms);
}
async function shot(p, file, note, opts = {}) {
  const f = file + '.jpg';
  const vp = p.viewportSize();
  try {
    await p.screenshot({ path: path.join(OUT, f), type: 'jpeg', quality: 80, fullPage: opts.full !== false });
  } catch (e) { note += ' [SHOT FAILED ' + e.message.slice(0, 80) + ']'; }
  manifest.push({
    file: f, url: p.url(), viewport: vp.width + 'x' + vp.height + (opts.full !== false ? ' fullPage' : ' viewport'),
    note, pageErrors: [...errs.page], consoleErrors: [...errs.con],
  });
  errs = { page: new Set(), con: new Set() };
  console.log(((Date.now() - T0) / 1000).toFixed(0) + 's', f, note);
}
function skip(file, note) {
  manifest.push({ file: file + '.jpg', url: '', viewport: '', note: 'NOT CAPTURED: ' + note, pageErrors: [], consoleErrors: [] });
  console.log('SKIP', file, note);
}
async function step(file, fn) {
  try { await fn(); } catch (e) { skip(file, String(e.message).split('\n')[0].slice(0, 200)); }
}
async function clickAct(p, act, text) {
  const loc = p.locator(`[data-act="${act}"]`).filter({ hasText: text }).first();
  await loc.click({ timeout: 5000 });
}
async function openDetails(p, text) {
  const ok = await p.evaluate((t) => {
    const s = Array.from(document.querySelectorAll('summary')).find(x => x.textContent.trim().startsWith(t));
    if (!s) return false;
    s.parentElement.open = true; s.scrollIntoView({ block: 'start' }); return true;
  }, text);
  if (!ok) throw new Error('summary not found: ' + text);
  await wait(p, 600);
}

(async () => {
  const b = await chromium.launch({ channel: 'chrome', args: ['--autoplay-policy=no-user-gesture-required', '--use-angle=d3d11'] });
  let ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
  let p = await ctx.newPage(); hook(p);

  // 01
  await step('01_first_visit', async () => {
    await p.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 30000 });
    await settle(p);
    await shot(p, '01_first_visit', 'fresh context, tutorial offer', { full: false });
    await shot(p, '01b_first_visit_full', 'fresh context fullPage', { full: true });
  });

  // 02
  await step('02_tutorial_step1', async () => {
    await p.click('#tutorial-start', { timeout: 5000 });
    await settle(p, 1200);
    const names = ['02_tutorial_step1', '02b_tutorial_step2', '02c_tutorial_step3', '02d_tutorial_step4', '02e_tutorial_step5'];
    for (let i = 0; i < names.length; i++) {
      await shot(p, names[i], 'tour step ' + (i + 1), { full: false });
      if (i < names.length - 1) {
        const nx = p.locator('#tour-next');
        try { await nx.click({ timeout: 4000 }); } catch (e) { skip(names[i + 1], 'Next not clickable: ' + e.message.split('\n')[0]); break; }
        await settle(p, 1500);
      }
    }
    // finish tour
    for (let k = 0; k < 4; k++) {
      const vis = await p.locator('#tour-next').isVisible().catch(() => false);
      if (!vis) break;
      await p.locator('#tour-next').click({ timeout: 3000 }).catch(() => {});
      await wait(p, 1000);
    }
    await wait(p, 1000);
    // make sure it's gone
    const still = await p.locator('#tour-skip').isVisible().catch(() => false);
    if (still) await p.locator('#tour-skip').click().catch(() => {});
    await settle(p, 800);
  });

  // 03
  await step('03_first_screen_full', async () => {
    await p.goto(BASE + '/', { waitUntil: 'networkidle' });
    await settle(p);
    await shot(p, '03_first_screen_full', 'after the tour');
  });

  // 04
  await step('04_song_bundled_glitch_out', async () => {
    await clickAct(p, 'easy-song', 'Glitch Out');
    await wait(p, 3000);
    await shot(p, '04_song_bundled_glitch_out', 'Glitch Out chip, 3 s');
    await wait(p, 28000);
    await shot(p, '04b_song_bundled_glitch_out_30s', 'Glitch Out chip, 30 s later');
  });

  // 05
  await step('05_song_upload', async () => {
    if (!(await p.locator('#easy-file').count())) {
      await p.getByText('Change', { exact: true }).first().click({ timeout: 5000 });
      await wait(p, 1000);
    }
    await shot(p, '05a_song_change_open', 'after clicking Change (song picker back)', { full: false });
    await p.setInputFiles('#easy-file', SONGS + 'liquid_dnb.mp3');
    let changed = false;
    for (let i = 0; i < 30; i++) {
      await wait(p, 2000);
      const t = await p.evaluate(() => document.body.innerText);
      if (/liquid_dnb/i.test(t)) { changed = true; if (i > 2) break; }
    }
    await settle(p, 1500);
    await shot(p, '05_song_upload', 'uploaded liquid_dnb.mp3; name appeared in page text: ' + changed);
  });

  // 06
  await step('06_vibe_selected', async () => {
    await clickAct(p, 'easy-vibe', 'Neon noir');
    await wait(p, 1500);
    await shot(p, '06_vibe_selected', 'Neon noir clicked');
  });

  // 07
  await step('07_more_vibes_open', async () => {
    await openDetails(p, 'More vibes');
    await shot(p, '07_more_vibes_open', 'More vibes open');
    await p.evaluate(() => { const s = Array.from(document.querySelectorAll('summary')).find(x => x.textContent.trim().startsWith('More vibes')); if (s) s.parentElement.open = false; });
  });

  // 08
  await step('08_morph_your_clips', async () => {
    await clickAct(p, 'easy-source', 'Your clips');
    await wait(p, 1500);
    await shot(p, '08_morph_your_clips', 'Morph: Your clips (empty state)');
    const inp = p.locator('input[data-act="easy-own-files"], input[type=file]:not(#easy-file)');
    const n = await inp.count();
    if (!n) { skip('08b_morph_clips_uploaded', 'no clips file input found'); return; }
    // pick one that accepts video
    let target = null;
    for (let i = 0; i < n; i++) {
      const acc = (await inp.nth(i).getAttribute('accept')) || '';
      if (/video|mp4/.test(acc) || n === 1) { target = inp.nth(i); break; }
    }
    if (!target) target = inp.first();
    await target.setInputFiles('C:/Users/tyson/Desktop/demo_v5_preview.mp4');
    await settle(p, 4000);
    await shot(p, '08b_morph_clips_uploaded', 'after uploading demo_v5_preview.mp4 to clips input');
  });

  // 09
  await step('09_morph_stems', async () => {
    await clickAct(p, 'easy-source', 'Stems');
    await wait(p, 1500);
    await shot(p, '09_morph_stems', 'Morph: Stems');
    await clickAct(p, 'easy-source', 'Objects');
    await wait(p, 1000);
  });

  // 10
  await step('10_idea_line', async () => {
    await p.fill('#easy-idea', 'a moth, a lantern, a brass key');
    await p.keyboard.press('Tab');
    await wait(p, 1800);
    await p.locator('#easy-idea').scrollIntoViewIfNeeded();
    await shot(p, '10_idea_line', 'idea line typed + blur');
  });

  // 11
  await step('11_loved_chain', async () => {
    await clickAct(p, 'easy-preset', 'Black glass rose');
    await wait(p, 1500);
    await shot(p, '11_loved_chain', 'Black glass rose chain chip');
  });

  // 12
  await step('12_knobs_stems_open', async () => {
    await openDetails(p, 'Stem reactions');
    await shot(p, '12_knobs_stems_open', 'Stem reactions open', { full: false });
  });
  await step('12b_midi_panel', async () => {
    await openDetails(p, 'MIDI controller');
    await shot(p, '12b_midi_panel', 'MIDI controller panel open', { full: false });
  });

  // 13
  await step('13_fine_tune_open', async () => {
    await openDetails(p, 'Fine-tune');
    await shot(p, '13_fine_tune_open', 'Fine-tune open');
  });
  // 14
  await step('14_wip_open', async () => {
    await openDetails(p, 'Work in progress');
    await shot(p, '14_wip_open', 'Work in progress open');
  });

  // 15
  await step('15_more_menu', async () => {
    await p.evaluate(() => window.scrollTo(0, 0));
    await p.click('.more-menu summary');
    await wait(p, 700);
    await shot(p, '15_more_menu', 'header menu open', { full: false });
  });
  // 16
  await step('16_settings_dialog', async () => {
    await p.click('#open-settings');
    await wait(p, 1200);
    await shot(p, '16_settings_dialog', 'Settings dialog', { full: false });
    await p.fill('#endpoint', 'http://127.0.0.1:9');
    await p.click('#save-settings');
    await wait(p, 5000);
    const st = await p.evaluate(() => (document.getElementById('comfy-status') || {}).textContent + ' | ' + (document.getElementById('comfy-settings-status') || {}).textContent);
    await shot(p, '16b_settings_bad_endpoint', 'endpoint set to :9 and saved. status: ' + st.replace(/\s+/g, ' ').slice(0, 200), { full: false });
    // restore
    const open = await p.evaluate(() => document.getElementById('settings').open);
    if (!open) { await p.evaluate(() => window.scrollTo(0, 0)); await p.click('.more-menu summary').catch(() => {}); await p.click('#open-settings'); await wait(p, 600); }
    await p.fill('#endpoint', 'http://127.0.0.1:8188');
    await p.click('#save-settings');
    await wait(p, 2500);
    await p.evaluate(() => { const d = document.getElementById('settings'); if (d.open) d.close(); });
  });

  // 17
  await step('17_about_dialog', async () => {
    await p.evaluate(() => window.scrollTo(0, 0));
    await p.click('.more-menu summary').catch(() => {});
    await p.click('#open-about');
    await wait(p, 1000);
    await shot(p, '17_about_dialog', 'About dialog', { full: false });
    await p.evaluate(() => { const d = document.getElementById('about'); d.scrollTop = d.scrollHeight; const f = d.querySelector('form'); if (f) f.scrollTop = f.scrollHeight; });
    await wait(p, 500);
    await shot(p, '17b_about_dialog_scrolled', 'About dialog scrolled to bottom', { full: false });
    await p.evaluate(() => document.getElementById('about').close());
  });

  // 18, 19
  await step('18_setup_page', async () => {
    await p.goto(BASE + '/#setup', { waitUntil: 'networkidle' });
    await settle(p, 2500);
    await shot(p, '18_setup_page', '#setup');
  });
  await step('19_connect_page', async () => {
    await p.goto(BASE + '/#connect', { waitUntil: 'networkidle' });
    await settle(p, 2500);
    const t = await p.evaluate(() => (document.querySelector('main') || document.body).innerText.slice(0, 80).replace(/\s+/g, ' '));
    await shot(p, '19_connect_page', '#connect; main starts: ' + t);
  });

  // 20
  await step('20_command_palette', async () => {
    await p.goto(BASE + '/#simple', { waitUntil: 'networkidle' });
    await settle(p);
    await p.keyboard.press('Control+k');
    await wait(p, 600);
    await p.keyboard.type('look', { delay: 60 });
    await wait(p, 800);
    await shot(p, '20_command_palette', 'Ctrl+K, typed "look"', { full: false });
    await p.keyboard.press('Escape');
  });

  // 21
  await step('21_showcase', async () => {
    await p.goto(BASE + '/#simple', { waitUntil: 'networkidle' });
    await settle(p);
    await clickAct(p, 'easy-showcase', 'Watch a finished one');
    await wait(p, 4000);
    await shot(p, '21_showcase', 'Watch a finished one, 4 s');
    await shot(p, '21b_showcase_viewport', 'showcase viewport', { full: false });
  });
  // 22
  await step('22_my_videos', async () => {
    const ok = await p.evaluate(() => { const e = document.getElementById('my-videos'); if (!e) return false; e.scrollIntoView({ block: 'start' }); return true; });
    if (!ok) { await p.goto(BASE + '/#simple', { waitUntil: 'networkidle' }); await settle(p); const ok2 = await p.evaluate(() => { const e = document.getElementById('my-videos'); if (!e) return false; e.scrollIntoView(); return true; }); if (!ok2) throw new Error('#my-videos not on page'); }
    await wait(p, 800);
    await shot(p, '22_my_videos', 'My videos section', { full: false });
  });

  // 23-27
  const pages = [['23_variations_page', '/variations'], ['24_judges_page', '/judges'], ['25_moves_page', '/moves'], ['26_licences', '/licences'], ['27_credits', '/credits']];
  for (const [n, u] of pages) {
    await step(n, async () => {
      const r = await p.goto(BASE + u, { waitUntil: 'networkidle', timeout: 30000 });
      await settle(p, 2000);
      await shot(p, n, 'HTTP ' + (r && r.status()));
    });
  }

  // 28
  await step('28_vj_first', async () => {
    await p.setViewportSize({ width: 1280, height: 720 });
    await p.goto(BASE + '/vj', { waitUntil: 'networkidle' });
    await settle(p, 2000);
    await shot(p, '28_vj_first', '/vj untouched', { full: false });
    await p.keyboard.press('?'); await wait(p, 800);
    await shot(p, '28b_vj_help', 'pressed ?', { full: false });
    await p.keyboard.press('?'); await wait(p, 400);
    await p.keyboard.press('Escape'); await wait(p, 300);
    await p.keyboard.press('p'); await wait(p, 800);
    await shot(p, '28c_vj_hud', 'pressed p (HUD)', { full: false });
    await p.keyboard.press('p'); await wait(p, 300);
    await p.keyboard.press('l'); await wait(p, 800);
    await shot(p, '28d_vj_midi_learn', 'pressed l', { full: false });
    await p.keyboard.press('l'); await wait(p, 300);
  });
  await step('28e_vj_track', async () => {
    await p.setInputFiles('#track', SONGS + 'glitch_out.mp3');
    let bpm = 0;
    for (let i = 0; i < 30; i++) {
      await wait(p, 2000);
      bpm = await p.evaluate(() => (window.VJ && VJ.S && VJ.S.bpm) || 0);
      if (bpm > 0) break;
    }
    await wait(p, 1500);
    const hudHidden = await p.evaluate(() => document.getElementById('hud').classList.contains('hide'));
    if (hudHidden) await p.keyboard.press('p');
    await wait(p, 1000);
    await shot(p, '28e_vj_track', 'glitch_out.mp3 loaded; bpm=' + bpm, { full: false });
    await p.keyboard.press('r'); await wait(p, 2000);
    await shot(p, '28f_vj_rec', 'pressed r (recording on)', { full: false });
    await p.keyboard.press('r'); await wait(p, 1000);
  });

  // 31 (main context, before closing)
  await step('31_reload_mid_state', async () => {
    await p.setViewportSize({ width: 1440, height: 900 });
    await p.goto(BASE + '/#simple', { waitUntil: 'networkidle' });
    await settle(p);
    await openDetails(p, 'Fine-tune');
    await clickAct(p, 'easy-aspect', '16:9');
    await wait(p, 800);
    const before = await p.evaluate(() => (Array.from(document.querySelectorAll('summary')).find(x => x.textContent.trim().startsWith('Fine-tune')) || {}).textContent);
    await p.reload({ waitUntil: 'networkidle' });
    await settle(p);
    const after = await p.evaluate(() => (Array.from(document.querySelectorAll('summary')).find(x => x.textContent.trim().startsWith('Fine-tune')) || {}).textContent);
    await shot(p, '31_reload_mid_state', 'Fine-tune summary before reload: "' + (before || '').replace(/\s+/g, ' ') + '" after: "' + (after || '').replace(/\s+/g, ' ') + '"');
  });
  // restore aspect to 9:16 (default) so the desk is as found
  await step('31x', async () => { await openDetails(p, 'Fine-tune'); await clickAct(p, 'easy-aspect', '9:16'); });
  manifest.splice(manifest.findIndex(m => m.file === '31x.jpg') >= 0 ? manifest.findIndex(m => m.file === '31x.jpg') : manifest.length, 1);

  await ctx.close();

  // 29 mobile
  await step('29_mobile_first', async () => {
    const c2 = await b.newContext({ viewport: { width: 430, height: 932 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1 });
    const q = await c2.newPage(); hook(q);
    await q.goto(BASE + '/', { waitUntil: 'networkidle' });
    await settle(q);
    await q.locator('#tutorial-later').click({ timeout: 3000 }).catch(() => {});
    await wait(q, 800);
    await shot(q, '29_mobile_first', 'fresh 430x932 context, tutorial dismissed (Not now)');
    await c2.close();
  });
  // 30 narrow
  await step('30_narrow_first', async () => {
    const c3 = await b.newContext({ viewport: { width: 1024, height: 768 } });
    const q = await c3.newPage(); hook(q);
    await q.goto(BASE + '/', { waitUntil: 'networkidle' });
    await settle(q);
    await q.locator('#tutorial-later').click({ timeout: 3000 }).catch(() => {});
    await wait(q, 800);
    await shot(q, '30_narrow_first', 'fresh 1024x768 context, tutorial dismissed');
    await c3.close();
  });

  manifest.sort((a, c) => a.file.localeCompare(c.file));
  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 1));
  console.log('done', manifest.length, 'entries', ((Date.now() - T0) / 1000).toFixed(0) + 's');
  await b.close();
})().catch(e => { console.log('FATAL', e); process.exit(1); });
