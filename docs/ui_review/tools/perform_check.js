// Perform check (T2 of docs/HANDOFF_4NOV.md): the control view and the output window of /vj, a take, and its proof.
//
// It makes a click track (a 3 ms burst every 0.5 s from 0.25 s), loads it with Load track, sets the song's beats to the
// clicks themselves, opens the output window from the control view, records ten seconds with REC, stops, and asserts:
//   - the take is saved on the desk as an mp4 (and its webm), at the output window's canvas size;
//   - nothing but the picture is in it: the top corners, where a REC dot or a HUD would sit, have no red in any frame;
//   - its sound and picture are in sync within one frame: with ?sync=1 the picture turns white for 50 ms from each beat
//     of the song's clock, so each click and the rise of its flash should land together (perform_sync.py measures it).
// The same take is then recorded in the control view alone (no output window), the path a one-screen set uses.
//
// Rerun: set NODE_PATH=C:\Projects\xf-uiaudit\node_modules, then: node perform_check.js [baseUrl] [outDir]
// (a desk started from this checkout; ffmpeg and ffprobe on PATH; PYTHON= a python with numpy, default the rc2 venv).
const { chromium } = require('playwright');
const { execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const BASE = process.argv[2] || 'http://127.0.0.1:47356';
const OUT = process.argv[3] || fs.mkdtempSync(path.join(os.tmpdir(), 'xf-perform-'));
const PY = process.env.PYTHON || (fs.existsSync('C:/Projects/xenoform-rc2/.venv/Scripts/python.exe') ? 'C:/Projects/xenoform-rc2/.venv/Scripts/python.exe' : 'python');
const SYNC = path.join(__dirname, 'perform_sync.py');
const SECONDS = 10, PERIOD = 0.5, FIRST = 0.25, FPS = 60;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const fails = [];
const check = (ok, what) => { console.log((ok ? 'PASS ' : 'FAIL ') + what); if (!ok) fails.push(what); };

async function fetchTo(url, file) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + ' ' + r.status);
  fs.writeFileSync(file, Buffer.from(await r.arrayBuffer()));
  return file;
}

async function take(page, label, during) {
  const lat = [];
  const probe = setInterval(() => { page.evaluate(() => XPA.latency()).then((l) => l && lat.push(l)).catch(() => {}); }, 1000);
  const going = page.evaluate((s) => XP.go({ start: 0, seconds: s }), SECONDS);
  if (during) { await wait(4000); await during(); }
  const t = await going;
  clearInterval(probe);
  if (lat.length) console.log(`${label}: audio latency while recording (s): ${JSON.stringify(lat[Math.floor(lat.length / 2)])}`);
  check(!!t && t.status === 'done', `${label}: the take is saved as an mp4 (${t ? t.status : 'none'})`);
  if (!t) return null;
  const mp4 = await fetchTo(BASE + t.mp4, path.join(OUT, `${label}-${t.id}.mp4`));
  const webm = await fetchTo(BASE + t.webm, path.join(OUT, `${label}-${t.id}.webm`));
  const m = {};
  for (const [kind, file] of [['mp4', mp4], ['webm', webm]]) {
    m[kind] = JSON.parse(execFileSync(PY, [SYNC, file, '--period', String(PERIOD), '--first', String(FIRST), '--start-pos', String(t.start_pos || 0), '--json']).toString());
  }
  return { take: t, mp4, webm, m };
}

function judge(label, res, canvas) {
  if (!res) return;
  const { take: t, m } = res;
  const frame = 1000 / 30;  // a frame of a 30 fps take, the default; the check records at 60 to measure finer
  check(fs.statSync(res.mp4).size > 10000 && fs.statSync(res.webm).size > 10000, `${label}: the mp4 and the webm exist`);
  check(m.mp4.width === canvas.w && m.mp4.height === canvas.h, `${label}: the take is the canvas's size (${m.mp4.width}x${m.mp4.height} vs ${canvas.w}x${canvas.h})`);
  check(m.mp4.corner_red < 40 && m.webm.corner_red < 40, `${label}: no overlay in the corners (reddest corner pixel ${m.mp4.corner_red} in the mp4, ${m.webm.corner_red} in the webm)`);
  const n = Math.floor((SECONDS - 0.5) / PERIOD);
  check(m.mp4.av.n >= n - 3, `${label}: clicks paired with flashes (${m.mp4.av.n} of about ${n})`);
  for (const kind of ['webm', 'mp4']) {
    const av = m[kind].av;
    check(av.n > 0 && Math.abs(av.median_ms) <= frame, `${label} ${kind}: picture against sound, median ${av.median_ms} ms (range ${av.min_ms} to ${av.max_ms}), within a frame (${frame.toFixed(1)} ms)`);
  }
  check(m.webm.drift && m.webm.drift.max_abs_ms < 3, `${label}: the take's clicks keep the source's spacing (worst ${m.webm.drift && m.webm.drift.max_abs_ms} ms)`);
  console.log(JSON.stringify({ label, take: t.id, size: t.size, seconds: t.seconds, start_pos: t.start_pos, webm: m.webm, mp4: m.mp4 }));
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const wav = path.join(OUT, 'click.wav');
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-f', 'lavfi', '-i', `aevalsrc='if(lt(mod(t+${PERIOD - FIRST},${PERIOD}),0.003),0.9*sin(2*PI*2500*t),0)':s=48000:d=20`, '-ac', '2', wav]);
  const clicks = Array.from({ length: Math.floor((20 - FIRST) / PERIOD) + 1 }, (_, k) => +(FIRST + k * PERIOD).toFixed(4));
  const b = await chromium.launch({ channel: 'chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--use-angle=d3d11'] });
  const ctx = await b.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', (e) => errs.push('control: ' + e.message));
  await page.goto(`${BASE}/vj?sync=1&vibes=none&footage=0&fps=${FPS}`);
  await page.waitForFunction(() => window.XP && window.XC, null, { timeout: 20000 });
  await page.setInputFiles('#track', wav);
  await page.waitForFunction(() => XC.track && XP.song(), null, { timeout: 30000 });
  // the desk analyses the upload; wait for its answer, then put the song's beats on the clicks
  await page.waitForFunction(() => (XP.song() && XP.song().src === 'desk') || /did not analyse|no analysis/.test(document.getElementById('src-note').textContent), null, { timeout: 60000 }).catch(() => {});
  await page.evaluate((c) => XP.setSong({ src: 'test', duration: 20, tempo: 120, beats: c, bars: c.filter((_, i) => i % 4 === 0), bar_phase: 0, passages: [] }), clicks);

  // 1. the output window
  const [out] = await Promise.all([page.waitForEvent('popup'), page.click('#outb')]);
  out.on('pageerror', (e) => errs.push('output: ' + e.message));
  await out.waitForLoadState('load');
  await page.waitForFunction(() => XP.linked(), null, { timeout: 15000 });
  await wait(1500);
  const outCanvas = await out.evaluate(() => ({ w: document.getElementById('c').width, h: document.getElementById('c').height, clean: getComputedStyle(document.getElementById('pf')).display === 'none' && getComputedStyle(document.body).cursor === 'none' }));
  check(outCanvas.clean, 'the output window shows the canvas and nothing else (no controls, no cursor)');
  const monitor = await page.evaluate(() => { const v = document.getElementById('mon'); return { shown: !v.hidden, w: v.videoWidth }; });
  check(monitor.shown && monitor.w > 0, `the control view's monitor shows the output window (${monitor.w} px wide)`);
  // the output window changes size mid-take (fullscreen, a drag): the take keeps the size it started at (V10)
  const outRes = await take(page, 'output', async () => {
    await out.setViewportSize({ width: 1000, height: 640 });
    await wait(600);
    const mid = await out.evaluate(() => ({ w: document.getElementById('c').width, h: document.getElementById('c').height }));
    check(mid.w === outCanvas.w && mid.h === outCanvas.h, `the output canvas holds ${outCanvas.w}x${outCanvas.h} while recording though its window became 1000x640 (it read ${mid.w}x${mid.h})`);
  });
  judge('output', outRes, outCanvas);
  await wait(500);
  const after = await out.evaluate(() => document.getElementById('c').width);
  check(after === 1000, `after the take the output canvas follows its window again (${after} px wide)`);
  await out.close();
  await page.waitForFunction(() => !XP.linked(), null, { timeout: 8000 }).catch(() => {});
  await wait(800);

  // 2. the control view alone
  const ctlCanvas = await page.evaluate(() => ({ w: document.getElementById('c').width, h: document.getElementById('c').height }));
  const ctlRes = await take(page, 'control');
  judge('control', ctlRes, ctlCanvas);

  await b.close();

  // 3. mic / line-in (V6): the input goes into the take; leaving mid-take asks first (V7)
  const bm = await chromium.launch({ channel: 'chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--use-angle=d3d11', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] });
  const pm = await (await bm.newContext({ viewport: { width: 1366, height: 900 } })).newPage();
  pm.on('pageerror', (e) => errs.push('mic: ' + e.message));
  await pm.goto(`${BASE}/vj?vibes=none&footage=0`);
  await pm.waitForFunction(() => window.XP && window.XC, null, { timeout: 20000 });
  await pm.click('#mic2');
  await pm.waitForFunction(() => !!XC.mic, null, { timeout: 10000 }).catch(() => {});
  check(await pm.evaluate(() => !!XC.mic), 'Mic / line-in opens the input');
  await pm.click('#recb');
  await wait(3500);
  let asked = false;
  pm.once('dialog', (d) => { asked = d.type() === 'beforeunload'; d.dismiss().catch(() => {}); });
  await pm.close({ runBeforeUnload: true });
  await wait(800);
  check(asked && !pm.isClosed(), 'closing the control view during a take asks first, and staying keeps the take running');
  await pm.click('#recb');
  let mt = null;
  for (let i = 0; i < 120; i++) { await wait(500); mt = await pm.evaluate(() => { const r = XP.report().rec; return r.on ? null : r.take; }); if (mt && mt.status !== 'finishing') break; }
  check(!!mt && mt.status === 'done', `the mic take is saved (${mt ? mt.status : 'none'})`);
  if (mt) {
    const f = await fetchTo(BASE + mt.mp4, path.join(OUT, `mic-${mt.id}.mp4`));
    const vol = spawnSync('ffmpeg', ['-hide_banner', '-i', f, '-vn', '-af', 'volumedetect', '-f', 'null', '-'], { encoding: 'utf8' }).stderr || '';
    const max = parseFloat((/max_volume: (-?[\d.]+) dB/.exec(vol) || [])[1]);
    check(max > -40, `the mic take has the input's sound in it (max ${max} dB)`);
  }
  await bm.close();
  // a refused microphone says so instead of failing silently
  const bd = await chromium.launch({ channel: 'chrome', headless: true, args: ['--use-angle=d3d11', '--use-fake-device-for-media-stream', '--deny-permission-prompts'] });
  const pd = await (await bd.newContext()).newPage();
  await pd.goto(`${BASE}/vj?vibes=none&footage=0`);
  await pd.waitForFunction(() => window.XP && window.XC, null, { timeout: 20000 });
  await pd.click('#mic2');
  await wait(1500);
  const said = await pd.evaluate(() => document.getElementById('src-note').textContent);
  check(/blocked|not connected|did not open|Another program/.test(said) && !(await pd.evaluate(() => !!XC.mic)), `a refused microphone says why: "${said}"`);
  await bd.close();

  check(!errs.length, 'no page errors' + (errs.length ? ': ' + errs.slice(0, 4).join(' | ') : ''));
  console.log(`files in ${OUT}`);
  console.log(fails.length ? `${fails.length} check(s) failed` : 'all checks passed');
  process.exit(fails.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
