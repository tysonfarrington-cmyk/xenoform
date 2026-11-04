// Xenoform OSC out: streams what the live page computes to the desk, which sends it as OSC (TouchDesigner's OSC In CHOP, port 7000).
// A browser cannot send UDP: this posts a batch of frames to the desk every animation frame (about 60 Hz, never below 30)
// over /ws/osc, or POST /api/osc/frame when there is no websocket, and the desk (osc_relay.py) forwards it. See docs/osc.md.
//
// What the page gives this file (vj.html calls both once, after XenoMidi.init; no layout change is needed):
//   XenoOsc.init({frame: () => ({...}), toast})   frame() returns the values the page shows right now. Any subset of
//        bass mid high (0..1, the HUD meters) · beat (the beat counter) beat_env · scene scene_name transition transition_fx
//        intensity bpm · t (song position, seconds) · stems {drums,bass,other,vocals} · sub rms (XenoOsc.audio(an,buf,sr) makes
//        these two from the analyser) · section is_drop mutate (when the page knows the song's sections). What it leaves out is
//        derived here: energy, onset_env/is_onset, beat_env/is_beat (from the counter), a live section/is_drop/mutate
//        estimate, frame, fps.
//   XenoOsc.mount(el, "before")                   adds the one small control ("OSC to TouchDesigner": host, port, Send OSC) inside el,
//        or just before it; its box is made to scroll if the page lets it overflow.
// XenoMidi's parameter changes and raw events are copied into the stream by wrapping XenoMidi.fire / XenoMidi.handle; midi.js is
// not touched and behaves as before.
(function () {
const KEY = "xeno-osc";
const base = () => window.XENO_BASE || "";
const num = v => (typeof v === "number" && isFinite(v) ? v : typeof v === "boolean" ? +v : NaN);
const store = {
  get() { try { return JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) { return {}; } },
  set(o) { try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
};
const MUTATE = { calm: 0, sustain: 0.2, build: 0.35, release: 0.45, drop: 1 };

// A live section estimate: the offline classifier (analyze.detect_sections) on a sliding 30 s window of the energy curve.
// calm, build, drop, release or sustain; a new label has to hold 1.4 s before it replaces the old one.
function Sections() { this.lv = 0; this.hist = []; this.label = "calm"; this.cand = "calm"; this.since = 0; }
Sections.prototype.step = function (t, dt, energy) {
  this.lv += (energy - this.lv) * (1 - Math.exp(-dt / 1.0));
  const H = this.hist;
  if (!H.length || t - H[H.length - 1][0] >= 0.5) H.push([t, this.lv]);
  while (H.length && t - H[0][0] > 30) H.shift();
  if (H.length < 6) return this.label; // about 3 s of music before it says anything
  let peak = 0, sum = 0;
  for (const h of H) { peak = Math.max(peak, h[1]); sum += h[1]; }
  const mean = sum / H.length, old = H[Math.max(0, H.length - 4)], slope = (this.lv - old[1]) / Math.max(0.5, t - old[0]);
  let lab;
  if (peak < 0.15) lab = "calm"; // quiet in absolute terms
  else if (this.lv < peak * 0.45 && slope < 0.28) lab = "calm";
  else if (slope > 0.12) lab = "build";
  else if (slope < -0.10) lab = "release";
  else if (this.lv < mean - 0.02) lab = "calm";
  else lab = "sustain";
  // the offline rule also calls any loud stretch (peak > 0.62) a drop; live, a drop has to stand out from the last 30 s
  if (slope <= 0.12 && peak >= 0.15 && peak > mean + 0.08 && this.lv >= peak * 0.82) lab = "drop"; // still climbing is a build
  if (lab !== this.cand) { this.cand = lab; this.since = t; }
  if (lab !== this.label && t - this.since >= 1.4) this.label = lab;
  return this.label;
};

const X = {
  on: false, available: null, detail: "", cfg: { host: "127.0.0.1", port: 7000, rate: 60, websocket: true }, transport: "off",
  sent: 0, failed: 0, last: null, st: null,
  _opts: {}, _frames: [], _params: {}, _trig: new Set(), _midi: [], _ws: null, _busy: false, _running: false,
  _next: 0, _n: 0, _avgDt: 1 / 60, _lastNow: 0, _en: 0, _prevE: 0, _avgFlux: 0, _lastOnset: -1e9, _onsetEnv: 0, _beatEnv: 0,
  _lastBeat: null, _rmsPeak: 0.02, _sec: new Sections(), _wsTried: 0, _el: null, _poll: 0, _raf: 0, _iv: 0,

  // ---- the page's two calls
  init(opts) {
    this._opts = opts || {};
    this.hookMidi();
    const s = store.get();
    if (s.used) this.refresh().then(() => {
      // a desk restarted since: put the host and port this browser remembers back (quietly), then carry on streaming if it is on
      if (s.host && s.port && !this.on && (this.cfg.host !== s.host || this.cfg.port !== s.port)) this.set({ host: s.host, port: s.port }, true);
      if (this.on) this.start();
    });
    return this;
  },
  mount(ref, where) { // inside ref, or just before it with where === "before"
    if (!ref || this._el) return this;
    if (!document.getElementById("xeno-osc-css")) {
      const st = document.createElement("style");
      st.id = "xeno-osc-css";
      st.textContent = `#xeno-osc-panel{font:12px/1.5 inherit;color:inherit;margin-top:12px;padding-top:8px;border-top:1px solid rgba(128,128,128,.25)}
#xeno-osc-panel h3{margin:0 0 4px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.7}
#xeno-osc-panel .xo-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0}
#xeno-osc-panel input,#xeno-osc-panel button{font:inherit;padding:2px 10px;border-radius:999px;border:1px solid rgba(128,128,128,.35);background:rgba(128,128,128,.08);color:inherit}
#xeno-osc-panel input{width:9.5em;cursor:text}#xeno-osc-panel input.xo-port{width:4.6em}#xeno-osc-panel button{cursor:pointer}
#xeno-osc-panel button.on{background:#f4f3fb;color:#0a0a10}#xeno-osc-panel .xo-st{opacity:.75}#xeno-osc-panel .xo-err{color:#ff8a7a}`;
      document.head.appendChild(st);
    }
    const el = document.createElement("div");
    el.id = "xeno-osc-panel";
    el.innerHTML = `<h3>OSC to TouchDesigner</h3>
<div class="xo-row"><input class="xo-host" value="${this.cfg.host}" aria-label="OSC host" spellcheck="false"> <b>:</b>
<input class="xo-port" value="${this.cfg.port}" aria-label="OSC port" inputmode="numeric"> <button class="xo-go" type="button">Send OSC</button></div>
<div class="xo-row xo-st"></div><div class="xo-row xo-err"></div>`;
    if (where === "before" && ref.parentNode) ref.parentNode.insertBefore(el, ref); else ref.appendChild(el);
    this._el = el;
    const box = el.parentNode; // a box the page lets overflow would hide the control on a short screen: make it scroll
    try { if (getComputedStyle(box).overflowY === "visible") { box.style.maxHeight = "calc(100vh - 32px)"; box.style.overflowY = "auto"; } } catch (e) {}
    // the help overlay closes on any click and the page's hotkeys listen on window: neither should see this control
    ["click", "pointerdown", "keydown", "keyup", "keypress"].forEach(ev => el.addEventListener(ev, e => e.stopPropagation()));
    el.querySelector(".xo-go").onclick = () => this.toggle();
    el.querySelectorAll("input").forEach(i => i.addEventListener("keydown", e => { if (e.key === "Enter") this.apply(); }));
    el.querySelectorAll("input").forEach(i => i.addEventListener("change", () => this.apply()));
    // ask the desk (GET /api/osc) when the control is first seen, not on every page load: a desk without python-osc answers 503
    if (window.IntersectionObserver) new IntersectionObserver(es => { if (es.some(e => e.isIntersecting)) this.refresh(); }).observe(el);
    else this.refresh();
    this._paint();
    return this;
  },

  // ---- the desk's settings
  async refresh() {
    try {
      const r = await fetch(base() + "/api/osc"), j = await r.json().catch(() => ({}));
      if (!r.ok) { this.available = false; this.detail = j.detail || "The desk answered " + r.status + "."; this.on = false; this.stop(); }
      else { this.available = true; this.detail = ""; this.cfg = { ...this.cfg, ...j }; this.on = !!j.on; }
    } catch (e) { this.available = false; this.detail = "The desk does not answer."; this.on = false; }
    this._paint();
    return this.cfg;
  },
  async set(patch, quiet) {
    try {
      const r = await fetch(base() + "/api/osc", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { this.detail = j.detail || "The desk answered " + r.status + "."; if (r.status === 503) { this.available = false; this.on = false; this.stop(); } if (!quiet) this.toast(this.detail); this._paint(); return false; }
      this.available = true; this.detail = ""; this.cfg = { ...this.cfg, ...j }; this.on = !!j.on;
      store.set({ used: true, host: this.cfg.host, port: this.cfg.port });
      if (this.on) this.start(); else this.stop();
      this._paint();
      return true;
    } catch (e) { this.detail = "The desk does not answer."; this._paint(); return false; }
  },
  apply() { // the host and port boxes (and Send OSC) to the desk
    if (!this._el) return Promise.resolve(false);
    const host = this._el.querySelector(".xo-host").value.trim(), port = parseInt(this._el.querySelector(".xo-port").value, 10);
    return this.set({ host, port: isNaN(port) ? 0 : port });
  },
  async toggle() {
    if (this.on) { if (await this.set({ on: false })) this.toast("OSC off"); return; }
    const host = this._el ? this._el.querySelector(".xo-host").value.trim() : this.cfg.host, port = this._el ? parseInt(this._el.querySelector(".xo-port").value, 10) : this.cfg.port;
    if (await this.set({ host, port: isNaN(port) ? 0 : port, on: true })) this.toast("OSC to " + this.cfg.host + ":" + this.cfg.port);
  },
  toast(t) { if (this._opts.toast) this._opts.toast(t); },

  // ---- the stream
  start() {
    if (this._running) return;
    this._running = true; this._next = 0; this._wsTried = 0;
    this._openWs();
    // Two clocks feed one fixed-rate scheduler (_tick): the animation frame, and a timer at half the period. A page that renders
    // at 30 fps (a busy GPU, a throttled pane) or none at all (a hidden or covered window) still sends `rate` updates a second.
    const raf = () => { if (!this._running) return; this._raf = requestAnimationFrame(raf); this._tick(performance.now()); };
    this._raf = requestAnimationFrame(raf);
    this._iv = setInterval(() => this._tick(performance.now()), Math.max(4, Math.round(1000 / (this.cfg.rate || 60) / 2)));
    this._poll = setInterval(() => this.poll(), 1000);
    this.poll();
  },
  stop() {
    if (!this._running) { this.transport = "off"; return; }
    this._running = false;
    cancelAnimationFrame(this._raf); clearInterval(this._iv); clearInterval(this._poll);
    if (this._ws) { const w = this._ws; this._ws = null; try { w.close(); } catch (e) {} }
    this._frames = []; this._params = {}; this._trig.clear(); this._midi = []; this.transport = "off";
    this._paint();
  },
  _tick(now) {
    if (!this._running) return;
    const period = 1000 / Math.max(30, this.cfg.rate || 60);
    if (now < this._next - 2) return; // faster than the rate (a 144 Hz screen, both clocks at once): merged down to it
    this._next = this._next + period < now - period ? now : this._next + period;
    let f = null;
    try { f = this._opts.frame ? this._opts.frame() : null; } catch (e) { f = null; }
    this._frames.push(this.derive(f || {}, now));
    if (this._frames.length > 8) this._frames.shift(); // never grows without bound if the desk stalls
    this._flush();
  },
  // The channels the page does not give: energy, onsets, beats from the counter, a section estimate, frame and fps.
  derive(f, now) {
    const d = Object.assign({}, f);
    const dt = this._lastNow ? Math.min(0.25, Math.max(0.001, (now - this._lastNow) / 1000)) : 1 / 60;
    if (this._lastNow) this._avgDt += (dt - this._avgDt) * 0.05; // the mean interval, so a burst of two ticks does not read as 120 Hz
    this._lastNow = now;
    const g = k => (num(d[k]) || 0);
    d.frame = ++this._n;
    if (d.fps == null) d.fps = Math.round(10 / this._avgDt) / 10;
    if (d.energy == null) { const e = 0.3 * g("sub") + 0.4 * g("bass") + 0.2 * g("mid") + 0.1 * g("high"); this._en += (e - this._en) * (1 - Math.exp(-dt / 0.08)); d.energy = this._en; }
    if (d.is_onset == null && d.onset_env == null) { // spectral flux of the bands, the page's own onset rule
      const e = 2 * g("bass") + g("mid") + g("high"), flux = Math.max(0, e - this._prevE);
      this._prevE = e; this._avgFlux = this._avgFlux * 0.95 + flux * 0.05;
      const hit = this._n > 2 && flux > 0.04 && flux > this._avgFlux * 2.4 && now - this._lastOnset > 120; // not on the first frame: 0 to the room is not a hit
      if (hit) this._lastOnset = now;
      this._onsetEnv = hit ? 1 : this._onsetEnv * Math.exp(-dt / 0.085);
      d.is_onset = hit ? 1 : 0; d.onset_env = this._onsetEnv;
    }
    if (d.is_beat == null && d.beat != null) { d.is_beat = this._lastBeat != null && d.beat !== this._lastBeat ? 1 : 0; this._lastBeat = d.beat; }
    if (d.beat_env == null) { this._beatEnv = d.is_beat ? 1 : this._beatEnv * Math.exp(-dt / 0.05); d.beat_env = this._beatEnv; }
    if (d.section == null) {
      const lab = this._sec.step(now / 1000, dt, g("energy"));
      d.section = lab;
      if (d.is_drop == null) d.is_drop = lab === "drop" ? 1 : 0;
      if (d.mutate == null) d.mutate = MUTATE[lab];
    }
    for (const k of ["rms", "sub", "bass", "mid", "high"]) if (d[k] == null) d[k] = 0;
    return d;
  },
  // the Web Audio part the page does not compute: sub (20-60 Hz) and rms, from its analyser and its byte spectrum
  audio(an, buf, sr) {
    if (!an || !buf || !sr) return {};
    const hz = sr / an.fftSize;
    const avg = (lo, hi) => { let s = 0, n = 0; for (let i = Math.max(1, Math.floor(lo / hz)); i < Math.min(buf.length, Math.ceil(hi / hz)); i++) { s += buf[i]; n++; } return n ? s / n / 255 : 0; };
    const out = { sub: avg(20, 60), mid: avg(150, 2000) };
    try { // the time domain is not smoothed, so reading it leaves what the page sees alone
      if (!this._td || this._td.length !== an.fftSize) this._td = new Float32Array(an.fftSize);
      an.getFloatTimeDomainData(this._td);
      let s = 0;
      for (let i = 0; i < this._td.length; i++) s += this._td[i] * this._td[i];
      const r = Math.sqrt(s / this._td.length);
      this._rmsPeak = Math.max(r, this._rmsPeak * 0.9995, 0.02);
      out.rms = Math.min(1, r / this._rmsPeak);
    } catch (e) {}
    return out;
  },
  _flush() {
    const body = { frames: this._frames };
    if (Object.keys(this._params).length) body.params = this._params;
    if (this._trig.size) body.triggers = [...this._trig];
    if (this._midi.length) body.midi = this._midi;
    const ws = this._ws;
    if (ws && ws.readyState === 1) {
      if (ws.bufferedAmount > 262144) { this._frames = this._frames.slice(-1); return; } // the desk is behind: drop, do not queue
      ws.send(JSON.stringify(body));
    } else {
      if (this._busy) return; // one post in flight; frames wait here (at most 8) and go in the next
      this._busy = true;
      fetch(base() + "/api/osc/frame", { method: "POST", headers: { "Content-Type": "application/json", "X-Xeno-Osc-Source": "vj" }, body: JSON.stringify(body) })
        .then(r => { if (!r.ok) return r.json().catch(() => ({})).then(j => this._fail(j.detail || "The desk answered " + r.status + ".", r.status)); })
        .catch(() => this._fail("The desk does not answer.", 0))
        .finally(() => { this._busy = false; });
    }
    this.sent++; this._frames = []; this._params = {}; this._trig.clear(); this._midi = [];
  },
  _fail(detail, status) {
    this.failed++; this.detail = detail;
    if (status === 503 || status === 400) { this.on = false; this.available = status === 503 ? false : this.available; this.stop(); this.toast(detail); }
    this._paint();
  },
  _openWs() {
    if (!window.WebSocket || this.cfg.websocket === false || this._ws || this._wsTried >= 3 || !this._running) return;
    let url;
    try { url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + base() + "/ws/osc?name=vj"; } catch (e) { return; }
    let opened = false;
    const ws = new WebSocket(url);
    this._ws = ws;
    ws.onopen = () => { opened = true; this.transport = "websocket"; this._paint(); };
    ws.onmessage = m => { try { const j = JSON.parse(m.data); if (j && j.type === "error") this._fail(j.detail || "The desk refused the websocket.", 503); } catch (e) {} };
    ws.onclose = ws.onerror = () => {
      if (this._ws !== ws) return;
      this._ws = null; this.transport = this._running ? "post" : "off";
      if (!opened) this._wsTried++;
      this._paint();
      if (this._running && opened) setTimeout(() => this._openWs(), 1500);
    };
    this.transport = "post";
  },

  // ---- XenoMidi: parameter changes and raw events ride along. Wrapped, not edited: midi.js keeps its behaviour.
  hookMidi() {
    const M = window.XenoMidi;
    if (!M || M.__oscHooked) return false;
    const fire = M.fire, handle = M.handle;
    if (typeof fire === "function") M.fire = function (target, val, ev, entry) { try { X.param(target, val, entry); } catch (e) {} return fire.apply(this, arguments); };
    if (typeof handle === "function") M.handle = function (ev, origin) { try { X.midi(ev); } catch (e) {} return handle.apply(this, arguments); };
    M.__oscHooked = true;
    return typeof fire === "function" || typeof handle === "function";
  },
  param(target, val, entry) {
    if (!this._running) return;
    const v = num(val);
    if (!target || isNaN(v)) return;
    this._params[target] = v;
    if (entry && entry.mode === "trigger") this._trig.add(target);
  },
  midi(ev) {
    if (!this._running || !ev || !ev.type) return;
    this._midi.push({ type: ev.type, ch: ev.ch, num: ev.num, value: ev.value, t: ev.t });
    if (this._midi.length > 64) this._midi.shift();
  },

  // ---- the control
  async poll() {
    try { const r = await fetch(base() + "/api/osc/status"); if (r.ok) { this.st = await r.json(); this.last = this.st.last_message; } } catch (e) {}
    this._paint();
  },
  status() { return { on: this.on, available: this.available, transport: this.transport, sent: this.sent, failed: this.failed, cfg: this.cfg, desk: this.st }; },
  _paint() {
    const el = this._el;
    if (!el) return;
    const go = el.querySelector(".xo-go"), st = el.querySelector(".xo-st"), er = el.querySelector(".xo-err");
    go.classList.toggle("on", this.on);
    go.textContent = this.on ? "Sending OSC" : "Send OSC";
    go.disabled = this.available === false;
    const hostIn = el.querySelector(".xo-host"), portIn = el.querySelector(".xo-port");
    if (document.activeElement !== hostIn) hostIn.value = this.cfg.host;
    if (document.activeElement !== portIn) portIn.value = this.cfg.port;
    const s = this.st;
    st.textContent = this.on
      ? "to " + this.cfg.host + ":" + this.cfg.port + " · " + (s ? Math.round(s.rate_hz) + " updates/s" : "starting") + " · " + (this.transport === "websocket" ? "websocket" : "post") +
        (s && s.last_message ? " · " + s.last_message.address + " " + JSON.stringify(s.last_message.args).replace(/[\[\]"]/g, "") : "")
      : (this.available === false ? "" : "Streams this page's bass, beat, scene and your MIDI knobs as OSC (docs/osc.md).");
    er.textContent = this.detail || "";
  },
  Sections
};
window.XenoOsc = X;
})();
