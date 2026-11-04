// Rerun: set NODE_PATH=C:\Projects\xf-uiaudit\node_modules, then: node capture_after.js [baseUrl]
// The Songline round 1 screens (docs/notes/t5-strip.md): each step at 1440x900 and at 375x812, into docs/ui_review/after
// with manifest.json. It needs the bundled songs and cut 31680167 (Glitch Out, 30 s) in My videos. It never presses
// Render Draft, Re-cut, Queue, Grow or any other GPU button; the progress shot is the desk's own client state with a
// pretend job (marked SIMULATED), so nothing runs.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const BASE = process.argv[2] || 'http://127.0.0.1:47354';
const OUT = path.join(__dirname, '..', 'after');
const CUT = '31680167';
fs.mkdirSync(OUT, { recursive: true });
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
// A full-page capture keeps the layout viewport, so the sticky step bar would be drawn mid-page over whatever sits
// there, and a page scrolled down loses inner scroll positions (the strip's): the page goes to the top and the bar is
// drawn where the page ends, for the capture only. The viewport shots show the bar as it sits on screen.
async function shot(p, file, note, full = true) {
  const f = file + '.jpg';
  const vp = p.viewportSize();
  if (full) {
    await p.evaluate(() => {
      window.scrollTo(0, 0);
      const s = document.createElement('style');
      s.id = 'capture-static';
      s.textContent = '.step-bar { position: static; }';
      document.head.appendChild(s);
    });
    await wait(p, 400);
    note += ' (full page: the step bar drawn where the page ends; on screen it sticks to the bottom)';
  }
  try {
    await p.screenshot({ path: path.join(OUT, f), type: 'jpeg', quality: 80, fullPage: full });
  } catch (e) { note += ' [SHOT FAILED ' + e.message.slice(0, 80) + ']'; }
  if (full) await p.evaluate(() => { const s = document.getElementById('capture-static'); if (s) s.remove(); });
  manifest.push({ file: f, url: p.url(), viewport: vp.width + 'x' + vp.height + (full ? ' fullPage' : ' viewport'), note,
    pageErrors: [...errs.page], consoleErrors: [...errs.con] });
  errs = { page: new Set(), con: new Set() };
  console.log(((Date.now() - T0) / 1000).toFixed(0) + 's', f);
}
function skip(file, note) {
  manifest.push({ file: file + '.jpg', url: '', viewport: '', note: 'NOT CAPTURED: ' + note, pageErrors: [], consoleErrors: [] });
  console.log('SKIP', file, note);
}
async function step(file, fn) {
  try { await fn(); } catch (e) { skip(file, String(e.message).split('\n')[0].slice(0, 200)); }
}
async function open(p, hash) {
  await p.goto(BASE + '/' + hash);
  await p.reload();  // a hash alone does not reload the desk
  await settle(p, 3500);
  await p.locator('#tutorial-later').click({ timeout: 1500 }).catch(() => {});
}
async function toStep(p, key) {
  await p.locator(`nav.step-nav [data-step="${key}"]`).first().click({ timeout: 5000 });
  await settle(p, 2500);
}

async function walk(p, w) {
  const t = '_' + w;
  const phone = w < 600;
  // on a phone, also the screen as it is held: the top of the step with the step bar stuck to the bottom
  const screen = async (file, note) => {
    if (!phone) return;
    await p.evaluate(() => window.scrollTo(0, 0));
    await wait(p, 300);
    await shot(p, file + '_screen', note + ' (the phone screen as it opens, the step bar stuck to the bottom)', false);
  };
  await step('01_source' + t, async () => {
    await open(p, '#source');
    const note = 'Source with no song: the strip ghosted until a song is in, the bundled songs with the demo among them by name, My videos, one action in the step bar (Choose a song)';
    await screen('01_source' + t, note);
    await shot(p, '01_source' + t, note);
  });
  await step('02_plan' + t, async () => {
    await p.locator('[data-act="easy-song"][data-id="glitch-out"]').click({ timeout: 5000 });
    await p.waitForFunction(() => location.hash === '#plan', null, { timeout: 20000 });
    await settle(p, 2500);
    await p.locator('.sl-rail [data-act="easy-vibe"]').first().click({ timeout: 5000 });
    await settle(p, 5000);  // the chain preview and the strip
    if (!phone) await shot(p, '02_plan_first_screen' + t, 'Plan on Glitch Out, the first screen: the sketch monitor (labelled Sketch, no GPU) beside the vibe rail, the strip with the planned shots inside the Draft window, the step bar', false);
    const note = phone
      ? 'Plan on Glitch Out with the first vibe: one column, the sketch monitor, then the strip as the section overview with the Draft window and its line, then the vibes'
      : 'Plan on Glitch Out with the first vibe: the sketch monitor, the vibe rail, the strip (sections, wave, beats, shots, Intensity, objects) and one estimate in the step bar';
    await screen('02_plan' + t, note);
    await shot(p, '02_plan' + t, note);
  });
  // the phone's strip is the overview, with no shots to click: the inspector shots are the desktop's
  if (!phone) {
    await step('02b_plan_dock' + t, async () => {
      await p.locator('.song-strip .xs-shot').nth(4).click({ timeout: 5000 });
      await settle(p, 1500);
      await shot(p, '02b_plan_dock' + t, 'Plan: a planned shot clicked on the strip docks the object it lands on under the strip, in song time, bar and beat');
    });
  }
  await step('03_tweak' + t, async () => {
    await toStep(p, 'tweak');
    if (!phone) await p.locator('.sl-tweak .xf-knob[data-k="chaos"]').hover({ timeout: 3000 }).catch(() => {});
    await wait(p, 500);
    const note = 'Tweak: the strip short, the Feel row (House, Dreamy, Hard glitch, Warm haze, Clean), the four knobs, the rows with their cost tags, the hint line (the Chaos knob under the pointer at 1440), the Project panel';
    await screen('03_tweak' + t, note);
    await shot(p, '03_tweak' + t, note);
  });
  if (!phone) {
    await step('04c_render_progress_simulated' + t, async () => {
      await p.evaluate(() => {
        state.job = { id: 'simulated', status: 'running', detail: 'Morph 6 of 13', progress: 0.42, overall: 0.42, stage: 'morph', timing: { phase: 'morph' } };
        state.easy.recutting = false;
        state.easy.reopenId = '';
        state.easy.phase = 'making';
        state.easy.step = 'render';
        render();
      });
      await wait(p, 500);
      await p.locator('.song-strip [data-xs="fit"]').first().click({ timeout: 3000 }).catch(() => {});
      await p.evaluate(() => window.scrollTo(0, 0));
      await wait(p, 500);
      await shot(p, '04c_render_progress_simulated' + t, 'SIMULATED in client state, no job ran: a Make on Render, the monitor pill saying Morph 6 of 13 on the GPU, shots 1 to 5 solid, 6 pulsing and 7 to 13 hatched on the strip, the clock and Stop in the step bar', false);
    });
  }
  await step('04_render' + t, async () => {
    await open(p, '#render/' + CUT);
    await settle(p, 2500);
    const note = `Render with cut ${CUT} reopened from its link: the player, the strip with the rendered shots on the song at 2:08, Quality and Render the whole song in the step bar, the share row`;
    await screen('04_render' + t, note);
    await shot(p, '04_render' + t, note);
  });
  if (!phone) {
    await step('04b_render_inspector' + t, async () => {
      await p.locator('.song-strip .xs-shot').nth(4).click({ timeout: 5000 });
      await settle(p, 1500);
      // a viewport shot of the timeline: a second full-page capture of one page paints the strip's own scroller at
      // 0:00 though the page keeps its place (Chromium; the DOM reads 13 shots in view)
      await p.evaluate(() => {
        const panel = document.querySelector('.tl-panel');
        if (panel) window.scrollTo(0, window.scrollY + panel.getBoundingClientRect().top - 72);
      });
      await wait(p, 500);
      await shot(p, '04b_render_inspector' + t, 'Render: shot 5 clicked on the strip, the inspector docked under it with its tabs, its head in song time, bar and beat as well as the clock', false);
    });
  }
  await step('05_perform' + t, async () => {
    await toStep(p, 'perform');
    const note = 'Perform: the card that opens /vj with this cut (the perform session builds the page itself)';
    await screen('05_perform' + t, note);
    await shot(p, '05_perform' + t, note);
  });
}

(async () => {
  const b = await chromium.launch({ channel: 'chrome', args: ['--autoplay-policy=no-user-gesture-required'] });
  for (const [w, h] of [[1440, 900], [375, 812]]) {
    const ctx = await b.newContext({ viewport: { width: w, height: h } });
    const p = await ctx.newPage();
    hook(p);
    await walk(p, w);
    await ctx.close();
  }
  await b.close();
  manifest.sort((a, c) => a.file.localeCompare(c.file));
  fs.writeFileSync(path.join(OUT, 'manifest.json'), JSON.stringify(manifest, null, 1));
  console.log('done', manifest.length, 'entries', ((Date.now() - T0) / 1000).toFixed(0) + 's');
})();
