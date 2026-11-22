// Runs ui_static/osc_out.js in a vm with stubs (no browser) and checks its logic: the derived channels, the section estimate,
// the Web Audio helper, the XenoMidi hook and the fixed-rate scheduler. `node tests/js/osc_out_check.js` prints one line per
// check and exits 1 on the first failure; tests/test_osc_relay.py runs it when node is installed.
const fs = require("fs"), vm = require("vm"), path = require("path"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "src", "xenoform", "ui_static", "osc_out.js"), "utf8");

function load() {
  const sent = [], posts = [], clock = { t: 1000 }, timers = [];
  const ctx = {
    console, Math, JSON, Date, Float32Array, Uint8Array, Object, Array, Set, Promise, isFinite, isNaN, parseInt, setTimeout: () => 0,
    localStorage: (() => { const m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; })(),
    performance: { now: () => clock.t },
    requestAnimationFrame: fn => { timers.push(fn); return timers.length; }, cancelAnimationFrame: () => {},
    setInterval: () => 1, clearInterval: () => {},
    location: { protocol: "http:", host: "127.0.0.1:47317" },
    fetch: (url, opts) => { posts.push({ url, opts }); return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ rate_hz: 60, last_message: null }) }); },
    WebSocket: class { constructor(url) { this.url = url; this.readyState = 1; this.bufferedAmount = 0; this.sent = sent; } send(s) { this.sent.push(JSON.parse(s)); } close() {} },
    document: { getElementById: () => null, activeElement: null },
  };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return { X: ctx.XenoOsc, ctx, sent, posts, clock };
}
const ok = name => console.log("ok  " + name);

// ---- derived channels
{
  const { X } = load();
  let d = X.derive({ bass: 0.6, mid: 0.4, high: 0.2, beat: 1 }, 1000);
  for (const k of ["rms", "sub", "bass", "mid", "high", "energy", "onset_env", "beat_env", "is_onset", "is_beat", "is_drop", "mutate", "frame", "fps", "section"]) assert.ok(d[k] != null, "missing " + k);
  assert.strictEqual(d.frame, 1); assert.strictEqual(d.is_beat, 0, "the first beat counter is only remembered");
  d = X.derive({ bass: 0.6, mid: 0.4, high: 0.2, beat: 2 }, 1016);
  assert.strictEqual(d.is_beat, 1); assert.strictEqual(d.beat_env, 1);
  d = X.derive({ bass: 0.6, mid: 0.4, high: 0.2, beat: 2 }, 1033);
  assert.strictEqual(d.is_beat, 0); assert.ok(d.beat_env < 0.8 && d.beat_env > 0, "beat_env falls away: " + d.beat_env);
  d = X.derive({ bass: 0.1, beat_env: 0.77, is_beat: 1, section: "drop", is_drop: 1, mutate: 1, energy: 0.9 }, 1050);
  assert.strictEqual(d.beat_env, 0.77); assert.strictEqual(d.section, "drop"); assert.strictEqual(d.energy, 0.9, "what the page gives is kept");
  ok("derive fills every channel and keeps what the page gives");
}
// ---- an onset from the spectral flux
{
  const { X } = load();
  let hit = 0;
  for (let i = 0; i < 120; i++) { const d = X.derive({ bass: 0.1, mid: 0.1, high: 0.1 }, 1000 + i * 16.7); hit += d.is_onset; }
  assert.strictEqual(hit, 0, "a steady signal has no onsets");
  const d = X.derive({ bass: 0.9, mid: 0.5, high: 0.4 }, 1000 + 121 * 16.7);
  assert.strictEqual(d.is_onset, 1); assert.strictEqual(d.onset_env, 1);
  const e = X.derive({ bass: 0.9, mid: 0.5, high: 0.4 }, 1000 + 122 * 16.7);
  assert.strictEqual(e.is_onset, 0); assert.ok(e.onset_env < 1 && e.onset_env > 0.5);
  ok("onsets come from the flux, one per hit");
}
// ---- the live section estimate: calm, a build, the drop, the release
{
  const { X } = load();
  const labels = [];
  const run = (secs, f) => { for (let i = 0; i < secs * 60; i++) { labels.push(null); const d = X.derive({ energy: f(i / 60) }, 1000 + labels.length * 16.667); labels[labels.length - 1] = d.section; } };
  run(10, () => 0.08);                      // quiet intro
  assert.strictEqual(labels[labels.length - 1], "calm");
  run(4, s => 0.08 + 0.8 * (s / 4));        // a ramp
  assert.ok(labels.slice(-120).includes("build"), "the ramp reads as a build: " + [...new Set(labels.slice(-240))]);
  run(8, () => 0.9);                        // the loud plateau
  const end = X.derive({ bass: 0.9, mid: 0.9, high: 0.9 }, 1000 + (labels.length + 1) * 16.667);
  assert.strictEqual(end.section, "drop"); assert.strictEqual(end.is_drop, 1); assert.strictEqual(end.mutate, 1);
  run(6, s => 0.9 - 0.8 * Math.min(1, s / 2)); // it falls away
  assert.ok(["release", "calm"].includes(labels[labels.length - 1]), "after the drop: " + labels[labels.length - 1]);
  run(8, () => 0.08);
  assert.strictEqual(labels[labels.length - 1], "calm");
  ok("the section estimate follows calm > build > drop > release");
}
// ---- the Web Audio helper
{
  const { X } = load();
  assert.strictEqual(JSON.stringify(X.audio(null, null, 0)), "{}");
  const an = { fftSize: 2048, getFloatTimeDomainData(a) { for (let i = 0; i < a.length; i++) a[i] = 0.5 * Math.sin(i / 5); } };
  const buf = new Uint8Array(1024); buf[1] = 200; buf[2] = 200; buf[10] = 100;     // 23 and 47 Hz at 48 kHz, and 234 Hz
  const a = X.audio(an, buf, 48000);
  assert.ok(a.sub > 0.1 && a.sub <= 1, "sub " + a.sub); assert.ok(a.mid > 0, "mid " + a.mid); assert.ok(a.rms > 0.9 && a.rms <= 1, "rms follows its own peak: " + a.rms);
  const quiet = { fftSize: 2048, getFloatTimeDomainData(a) { a.fill(0.0001); } };
  assert.ok(X.audio(quiet, buf, 48000).rms < 0.05);
  ok("audio() gives sub, mid and rms from the analyser");
}
// ---- XenoMidi: wrapped, behaviour kept, parameters and events copied into the stream
{
  const { X, ctx } = load();
  const calls = [];
  ctx.XenoMidi = { fire(target, val, ev, entry) { calls.push(["fire", target, val]); return "kept"; }, handle(ev, origin) { calls.push(["handle", ev.num]); this.fire("intensity", 1.5, ev, { mode: "abs" }); return 7; } };
  assert.strictEqual(X.hookMidi(), true); assert.strictEqual(X.hookMidi(), false, "hooked once");
  X._running = true;
  const r = ctx.XenoMidi.handle({ type: "cc", ch: 1, num: 74, value: 64, t: 1 }, "webmidi");
  assert.strictEqual(r, 7, "the return value is the original's");
  assert.deepStrictEqual(calls, [["handle", 74], ["fire", "intensity", 1.5]]);
  ctx.XenoMidi.fire("fx:3", 1, {}, { mode: "trigger" });
  assert.strictEqual(JSON.stringify(X._params), JSON.stringify({ intensity: 1.5, "fx:3": 1 })); assert.deepStrictEqual([...X._trig], ["fx:3"]);
  assert.strictEqual(X._midi.length, 1); assert.strictEqual(X._midi[0].num, 74);
  X._running = false; X._params = {}; X._midi = [];
  ctx.XenoMidi.fire("intensity", 0.2, {}, {});
  assert.strictEqual(JSON.stringify(X._params), "{}", "nothing is collected while OSC is off");
  ok("XenoMidi.fire and handle are wrapped and still do their own job");
}
// ---- the fixed-rate scheduler: a 30, 60, 144 or 240 Hz screen all give the configured rate
for (const [hz, rate] of [[60, 60], [144, 60], [240, 60], [60, 30], [144, 120], [30, 60]]) {
  const { X, sent, clock } = load();
  X.cfg.rate = rate; X.cfg.websocket = true; X._opts = { frame: () => ({ bass: 0.5, beat: 0 }) };
  X._running = true; X._openWs();
  let t = 5000, n = 0; const step = 1000 / hz;
  for (let i = 0; i < hz * 2; i++) { t += step + (i % 3 === 0 ? 0.4 : -0.2); clock.t = t; X._tick(t, true); }
  const frames = sent.reduce((a, b) => a + b.frames.length, 0), per = frames / 2;
  const want = Math.min(hz, rate);
  assert.ok(per >= want * 0.93 && per <= want * 1.07, `${hz} Hz screen at rate ${rate}: ${per} frames a second, wanted about ${want}`);
}
ok("the fixed-rate scheduler holds the rate on 30, 60, 144 and 240 Hz screens");
// ---- a page that renders at 30 fps (a busy GPU, a throttled pane) still sends 60 updates a second: the timer fills in
{
  const { X, sent, clock } = load();
  X.cfg.rate = 60; X._opts = { frame: () => ({ bass: 0.5 }) }; X._running = true; X._openWs();
  let t = 7000;
  for (let i = 0; i < 240; i++) { t += 8.333; clock.t = t; X._tick(t); if (i % 4 === 0) X._tick(t); } // timer every 8.3 ms, a frame every 33 ms
  const per = sent.reduce((a, b) => a + b.frames.length, 0) / 2;
  assert.ok(per >= 56 && per <= 64, "a 30 fps page sent " + per + " updates a second");
  ok("a 30 fps page still sends 60 updates a second");
}
// ---- a hidden window: no animation frames, the timer carries the stream; and not twice while frames run
{
  const { X, sent, clock } = load();
  X.cfg.rate = 60; X._opts = { frame: () => ({ bass: 0.5 }) }; X._running = true; X._openWs();
  let t = 9000;
  for (let i = 0; i < 120; i++) { t += 8.33; clock.t = t; X._tick(t, false); }   // timer only, every 8.3 ms for a second
  const hidden = sent.reduce((a, b) => a + b.frames.length, 0);
  assert.ok(hidden >= 55 && hidden <= 65, "hidden: " + hidden);
  sent.length = 0;
  for (let i = 0; i < 60; i++) { t += 16.667; clock.t = t; X._tick(t, true); X._tick(t + 8, false); }  // frames run: the timer adds nothing
  const visible = sent.reduce((a, b) => a + b.frames.length, 0);
  assert.ok(visible >= 55 && visible <= 62, "visible: " + visible);
  ok("a hidden window is carried by the timer, a visible one is not doubled");
}
// ---- no websocket: posts, one in flight, frames wait for it
{
  const { X, ctx, posts, clock } = load();
  X.cfg.websocket = false; X._opts = { frame: () => ({ bass: 0.5 }) }; X._running = true; X._openWs();
  assert.strictEqual(X._ws, null, "the desk said no websocket");
  let t = 100;
  for (let i = 0; i < 5; i++) { t += 16.7; clock.t = t; X._tick(t, true); }
  assert.strictEqual(posts.length, 1, "one request in flight at a time");
  assert.strictEqual(posts[0].url, "/api/osc/frame"); assert.strictEqual(JSON.parse(posts[0].opts.body).frames.length, 1);
  assert.strictEqual(X._frames.length, 4, "the other four wait for the answer");
  ok("without a websocket the frames are posted one request at a time");
}
console.log("all osc_out checks passed");
