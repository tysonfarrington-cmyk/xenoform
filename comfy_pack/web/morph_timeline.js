// Xenoform's Morph Timeline: the song strip, full window, inside ComfyUI.
//
// The canvas is the song (docs/UI_REVIEW.md 6.1 and 6.2): SECTIONS colour-coded with the drop flagged, the WAVE, the
// BEATS (bars heavier), the SHOTS as blocks snapped to beats, the INTENSITY keyframe lane and the OBJECTS lane (the
// still the chain lands on at each cut, pinned or picked). Nothing here is a camera or a 3D view.
//
// The editor never computes the plan: the node does (comfy_pack/storyboard.py). It edits a small list of changes
// (cuts, a shot's own style, timing, hold and seed, intensity points, object pins) and writes it into the node's hidden
// `timeline` widget, so it is saved with the workflow. "Plan the edits" queues this node alone (no morph renders).
// No library: plain DOM and a 2D canvas.

import { app } from "../../scripts/app.js";

const TIMELINE = "XenoformMorphTimeline";
const ASSEMBLE = "XenoformAssemble";
const TEXT_NODES = new Set(["XenoformSongAnalysis", "XenoformStoryboard", "XenoformMorphPair", "XenoformAssemble", TIMELINE]);
const EDITS = "xenoform.timeline/1";
const HUES = { intro: 210, calm: 200, sustain: 190, build: 40, release: 60, drop: 350, drop_late: 20, outro: 230 };
const MAX_MORPHS = 16;
const LANES = [
  ["ruler", 22], ["sections", 26], ["wave", 52], ["beats", 20], ["shots", 62], ["intensity", 66], ["objects", 58],
];
const LABELS = { sections: "SECTIONS", wave: "WAVE", beats: "BEATS", shots: "SHOTS", intensity: "INTENSITY", objects: "OBJECTS" };
const GUTTER = 84;

// ------------------------------------------------------------------------------------------------ small helpers

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const keyOf = (t) => Number(t).toFixed(3);
const clone = (o) => JSON.parse(JSON.stringify(o));
const hueOf = (label) => (HUES[label] != null ? HUES[label] : 260);
function clock(t) {
  const s = Math.max(0, Number(t) || 0);
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(2).padStart(5, "0")}`;
}
function el(tag, attrs = {}, kids = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "style") n.style.cssText = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const kid of [].concat(kids)) if (kid != null) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return n;
}

function injectStyle() {
  if (document.getElementById("xf-tl-style")) return;
  const css = `
.xf-tl{position:fixed;inset:0;z-index:10000;display:flex;flex-direction:column;background:#0b0b0f;color:#ececf1;
  font:13px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;user-select:none}
.xf-tl header{display:flex;align-items:center;gap:12px;padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.08);background:#141419}
.xf-tl h1{font:600 15px "Space Grotesk",system-ui,sans-serif;margin:0;letter-spacing:.02em}
.xf-tl .meta{color:#a9a9b6;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.xf-tl button{height:30px;padding:0 12px;border-radius:6px;border:1px solid rgba(255,255,255,.12);background:#23232c;color:#ececf1;cursor:pointer;font:inherit}
.xf-tl button:hover{border-color:rgba(255,255,255,.25)}
.xf-tl button.primary{background:#7c6cff;border-color:#7c6cff}
.xf-tl button.primary:hover{background:#9488ff}
.xf-tl button[disabled]{opacity:.45;cursor:default}
.xf-tl .stage{flex:1;position:relative;min-height:240px}
.xf-tl canvas{position:absolute;inset:0;width:100%;height:100%;cursor:default}
.xf-tl .insp{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;padding:10px 14px;border-top:1px solid rgba(255,255,255,.08);background:#141419;min-height:58px}
.xf-tl .insp .who{min-width:260px;color:#a9a9b6}
.xf-tl .insp .who b{color:#ececf1;font-weight:600}
.xf-tl .chips{display:flex;gap:4px;align-items:center}
.xf-tl .chips span{color:#74747f;margin-right:4px}
.xf-tl .chip{height:26px;padding:0 10px;border-radius:13px;font-size:12px}
.xf-tl .chip.on{background:rgba(124,108,255,.22);border-color:#7c6cff}
.xf-tl input[type=number]{width:96px;height:26px;background:#0f0f14;color:#ececf1;border:1px solid rgba(255,255,255,.12);border-radius:6px;padding:0 6px}
.xf-tl footer{padding:7px 14px;color:#74747f;font-size:12px;border-top:1px solid rgba(255,255,255,.06);display:flex;gap:16px;flex-wrap:wrap}
.xf-tl footer b{color:#a9a9b6;font-weight:500}
.xf-tl .note{color:#f2b14a}
.xf-tl .picker{position:absolute;z-index:3;background:#1b1b22;border:1px solid rgba(255,255,255,.14);border-radius:10px;padding:10px;
  max-width:560px;max-height:360px;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:8px;box-shadow:0 10px 30px rgba(0,0,0,.5)}
.xf-tl .picker .opt{display:flex;flex-direction:column;gap:3px;align-items:center;cursor:pointer;padding:4px;border-radius:6px;font-size:11px;color:#a9a9b6;text-align:center}
.xf-tl .picker .opt:hover,.xf-tl .picker .opt.on{background:rgba(124,108,255,.18);color:#ececf1}
.xf-tl .picker img{width:88px;height:50px;object-fit:cover;border-radius:4px;background:#0f0f14}
.xf-tl .picker .head{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;color:#ececf1}
.xf-tl .empty{position:absolute;inset:0;display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;color:#a9a9b6}
`;
  document.head.append(el("style", { id: "xf-tl-style", text: css }));
}

// ------------------------------------------------------------------------------------------------ the node side

function widgetOf(node, name) {
  return (node.widgets || []).find((w) => w.name === name);
}

function hideWidget(node, name) {
  // each step on its own: a frontend whose widget class makes one of these read-only still gets the others
  const w = widgetOf(node, name);
  if (!w) return;
  const tryIt = (fn) => { try { fn(); } catch (e) { /* read-only here */ } };
  tryIt(() => { w.hidden = true; });
  tryIt(() => { w.type = "hidden"; });
  tryIt(() => { w.computeSize = () => [0, -4]; });
  tryIt(() => { if (w.options) w.options.hidden = true; });
  for (const key of ["element", "inputEl"]) tryIt(() => { if (w[key]?.style) w[key].style.display = "none"; });
}

function readEdits(node, board) {
  const w = widgetOf(node, "timeline");
  try {
    const got = w && w.value ? JSON.parse(w.value) : null;
    // edits made on another song are not this song's: the node ignores them (song_key), so the editor starts afresh
    // too, instead of drawing the old cuts over the new song and stamping them with its key at the first change
    const other = got && got.song_key && board?.song?.key && got.song_key !== board.song.key;
    if (got && got.format === EDITS && !other) return got;
  } catch (e) { /* an empty or foreign value: start afresh */ }
  return { format: EDITS, song_key: board?.song?.key || "", cuts: null, shots: {}, intensity: [], pins: [] };
}

function writeEdits(node, edits) {
  const w = widgetOf(node, "timeline");
  if (!w) return;
  const empty = edits.cuts == null && !Object.keys(edits.shots || {}).length && !(edits.intensity || []).length && !(edits.pins || []).length;
  w.value = empty ? "" : JSON.stringify(edits);
  w.callback?.(w.value);
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
  try { app.graph?.change?.(); } catch (e) { /* older graphs have no change() */ }
}

function showText(node, text) {
  if (!text) return;
  const value = Array.isArray(text) ? text.join("\n") : String(text);
  let w = widgetOf(node, "xf_summary");
  if (!w) {
    w = node.addWidget("text", "xf_summary", "", () => {}, { serialize: false });
    try { w.serialize = false; w.disabled = true; } catch (e) { /* the option above says it */ }
  }
  w.value = value.split("\n")[0];
  try { w.label = ""; } catch (e) { /* a read-only label keeps its name */ }
  node._xfText = value;
  node.setDirtyCanvas?.(true, true);
}

function drawMini(node, ctx) {
  const view = node._xf;
  if (!view || node.flags?.collapsed) return;
  const board = view.board;
  const dur = board?.song?.duration || 0;
  if (!dur) return;
  const x0 = 10, w = node.size[0] - 20, h = 26, y0 = node.size[1] - h - 8;
  ctx.save();
  ctx.fillStyle = "#0f0f14";
  ctx.fillRect(x0, y0, w, h);
  for (const s of board.song.sections || []) {
    ctx.fillStyle = `hsla(${hueOf(s.label)},55%,45%,.55)`;
    ctx.fillRect(x0 + (s.start / dur) * w, y0, Math.max(1, ((s.end - s.start) / dur) * w), 8);
  }
  for (const s of board.shots || []) {
    const a = x0 + (s.start / dur) * w, b = x0 + (s.end / dur) * w;
    ctx.fillStyle = `hsla(${hueOf(s.section || s.song_section)},40%,62%,.85)`;
    ctx.fillRect(a + 0.5, y0 + 10, Math.max(1, b - a - 1), h - 12);
  }
  if (board.song.drop != null) {
    ctx.fillStyle = "#ff6464";
    ctx.fillRect(x0 + (board.song.drop / dur) * w - 1, y0, 2, h);
  }
  ctx.restore();
}

// ------------------------------------------------------------------------------------------------ the editor

let EDITOR = null;

function openEditor(node) {
  injectStyle();
  if (EDITOR) EDITOR.close(false);
  EDITOR = new Editor(node);
}

class Editor {
  constructor(node) {
    this.node = node;
    this.view = node._xf || null;
    this.board = this.view?.board || null;
    this.edits = readEdits(node, this.board);
    this.saved = JSON.stringify(this.edits);
    this.undo = [];
    this.sel = null; // {kind: "shot"|"point"|"slot", index}
    this.drag = null;
    this.thumbs = new Map();
    this.pps = 60; // pixels a second
    this.t0 = 0; // seconds at the left edge of the lanes
    this.playhead = 0;
    this.audio = null;
    this.build();
    this.fit();
    this.render();
    this.onKey = (e) => this.key(e);
    window.addEventListener("keydown", this.onKey, true);
    this.onResize = () => this.render();
    window.addEventListener("resize", this.onResize);
  }

  // ---- data
  song() { return this.board?.song || {}; }
  duration() { return Number(this.song().duration || 0); }
  beats() { return this.song().beats || []; }
  planCuts() { return (this.view?.plan_cuts || (this.board?.shots || []).slice(1).map((s) => s.start)).map(Number); }
  cuts() { return this.edits.cuts != null ? this.edits.cuts.map(Number) : this.boardCuts(); }
  boardCuts() { return (this.board?.shots || []).slice(1).map((s) => Number(s.start)); }
  bounds() { return [0, ...this.cuts(), this.duration()]; }
  dirty() { return JSON.stringify(this.edits) !== this.saved; }
  shotAt(i) {
    // the board's own row for a shot whose span the plan has (start and end), else a row made from the cuts: a shot
    // whose cut moved, split or joined is planned on the next run
    const b = this.bounds();
    const start = b[i], end = b[i + 1];
    const row = (this.board.shots || []).find((r) => Math.abs(r.start - start) < 1e-3 && Math.abs(r.end - end) < 1e-3) || null;
    const o = (this.edits.shots || {})[keyOf(start)] || {};
    return {
      index: i, start, end, seconds: end - start, frames: Math.round(end * 24) - Math.round(start * 24),
      style: o.style || row?.style || "melt", styleSet: !!o.style, timing: o.timing || row?.timing_mode || "smooth",
      timingSet: !!o.timing, hold: o.hold != null ? !!o.hold : !!row?.hold, seed: o.seed != null ? o.seed : row?.seed,
      intensity: this.intensityAt(start, row), from: this.stillAt(i)?.noun || row?.from || "", to: this.stillAt(i + 1)?.noun || row?.to || "",
      section: row?.section || row?.song_section || this.sectionAt(start), planned: !!row, length: row?.length,
      planStyle: row ? (row.style_set ? "auto" : row.style) : "auto",
    };
  }
  shotCount() { return this.bounds().length - 1; }
  sectionAt(t) {
    for (const s of this.song().sections || []) if (t >= s.start - 1e-6 && t < s.end) return s.label;
    return "";
  }
  intensityAt(t, row) {
    const pts = (this.edits.intensity || []).slice().sort((a, b) => a[0] - b[0]);
    if (!pts.length) return row?.fx_intensity != null ? Number(row.fx_intensity) : null;
    if (t <= pts[0][0]) return pts[0][1];
    if (t >= pts[pts.length - 1][0]) return pts[pts.length - 1][1];
    for (let k = 1; k < pts.length; k++) {
      if (t <= pts[k][0]) {
        const [ta, va] = pts[k - 1], [tb, vb] = pts[k];
        return va + ((t - ta) / Math.max(1e-6, tb - ta)) * (vb - va);
      }
    }
    return null;
  }
  pinAt(slot) {
    const b = this.bounds();
    for (const [t, file] of this.edits.pins || []) {
      let best = 0;
      b.forEach((x, k) => { if (Math.abs(x - t) < Math.abs(b[best] - t)) best = k; });
      if (best === slot) return file;
    }
    return null;
  }
  stillAt(slot) {
    const file = this.pinAt(slot);
    if (file) {
      const row = (this.board.pool || []).find((r) => r.file === file);
      return { file, noun: row?.noun || file.split("/").pop(), pinned: true };
    }
    return (this.board.stills || [])[slot] || null;
  }

  // ---- edits
  change(fn) {
    this.undo.push(JSON.stringify(this.edits));
    if (this.undo.length > 200) this.undo.shift();
    fn(this.edits);
    this.edits.song_key = this.song().key || this.edits.song_key || "";
    this.render();
  }
  rekey(oldStart, newStart) {
    const shots = this.edits.shots || {};
    const o = shots[keyOf(oldStart)];
    if (o) { delete shots[keyOf(oldStart)]; shots[keyOf(newStart)] = o; }
  }
  setShot(i, patch) {
    const start = this.bounds()[i];
    this.change((e) => {
      e.shots = e.shots || {};
      const o = { ...(e.shots[keyOf(start)] || {}), ...patch };
      for (const k of Object.keys(o)) if (o[k] == null || o[k] === "") delete o[k];
      if (Object.keys(o).length) e.shots[keyOf(start)] = o; else delete e.shots[keyOf(start)];
    });
  }
  snap(t, ev) {
    if (ev?.altKey) return t;
    const grid = [0, ...(ev?.shiftKey ? this.song().downbeats || [] : this.beats()), this.duration()];
    let best = grid[0];
    for (const g of grid) if (Math.abs(g - t) < Math.abs(best - t)) best = g;
    return best;
  }
  split(t) {
    const cuts = this.cuts();
    const b = this.bounds();
    if (b.some((x) => Math.abs(x - t) < 0.25)) return;
    this.change((e) => { e.cuts = [...cuts, Number(t.toFixed(4))].sort((x, y) => x - y); });
  }
  join(i) {
    const cuts = this.cuts();
    if (!cuts.length) return;
    const k = i > 0 ? i - 1 : 0; // shot i joins the one before it (the first joins the next)
    const gone = cuts[k];
    this.change((e) => {
      e.cuts = cuts.filter((_, j) => j !== k);
      if (e.shots) delete e.shots[keyOf(gone)];
    });
    this.sel = { kind: "shot", index: Math.max(0, i - 1) };
  }

  // ---- layout
  lanes() {
    // the lanes' base heights, the spare height of the window shared out to the wave, the shots, the intensity and
    // the objects (each at most twice its base), so a tall window shows a bigger strip, not an empty floor
    const H = this.canvas?.clientHeight || 0;
    const base = LANES.reduce((a, [, h]) => a + h, 0);
    const spare = Math.max(0, H - base - 8);
    const share = { wave: 0.3, shots: 0.25, intensity: 0.25, objects: 0.2 };
    return LANES.map(([n, h]) => [n, Math.round(h + Math.min(h, spare * (share[n] || 0)))]);
  }
  laneRect(name) {
    let y = 0;
    for (const [n, h] of this.lanes()) {
      if (n === name) return { y, h };
      y += h;
    }
    return { y: 0, h: 0 };
  }
  laneAt(y) {
    let top = 0;
    for (const [n, h] of this.lanes()) {
      if (y >= top && y < top + h) return n;
      top += h;
    }
    return null;
  }
  x(t) { return GUTTER + (t - this.t0) * this.pps; }
  t(x) { return this.t0 + (x - GUTTER) / this.pps; }
  fit() {
    const w = Math.max(400, (this.canvas?.clientWidth || window.innerWidth) - GUTTER - 16);
    const d = this.duration() || 10;
    this.pps = w / d;
    this.t0 = 0;
  }
  clampView() {
    const w = this.canvas.clientWidth - GUTTER;
    const d = this.duration();
    this.pps = clamp(this.pps, Math.max(4, (w - 16) / Math.max(d, 1)), 900);
    this.t0 = clamp(this.t0, 0, Math.max(0, d - w / this.pps + 0.5));
  }

  // ---- DOM
  build() {
    const song = this.song();
    this.root = el("div", { class: "xf-tl", tabindex: "-1" });
    this.meta = el("div", { class: "meta" });
    this.playBtn = el("button", { text: "Play", title: "Space", onclick: () => this.togglePlay() });
    const head = el("header", {}, [
      el("h1", { text: "Morph Timeline" }), this.meta, this.playBtn,
      el("button", { text: "Fit", title: "The whole song in view", onclick: () => { this.fit(); this.render(); } }),
      el("button", { text: "Undo", title: "Ctrl+Z", onclick: () => this.doUndo() }),
      el("button", { text: "Reset edits", title: "Back to the plan", onclick: () => this.change((e) => { e.cuts = null; e.shots = {}; e.intensity = []; e.pins = []; }) }),
      el("button", { text: "Plan the edits", title: "Save, then run this node alone: the plan comes back here, no morph is rendered", onclick: () => this.plan() }),
      el("button", { text: "Cancel", onclick: () => this.close(true) }),
      el("button", { class: "primary", text: "Save", title: "Saved in the workflow; Queue renders the edited cut", onclick: () => this.save(true) }),
    ]);
    this.stage = el("div", { class: "stage" });
    this.canvas = el("canvas");
    this.stage.append(this.canvas);
    this.insp = el("div", { class: "insp" });
    this.foot = el("footer", {}, [
      el("span", {}, [el("b", { text: "Wheel" }), " zooms, Shift+wheel or drag the ruler pans"]),
      el("span", {}, [el("b", { text: "Drag a cut" }), " along the beats (Shift: bars, Alt: free)"]),
      el("span", {}, [el("b", { text: "Double-click" }), " a shot to split it on the beat; Delete joins it to the one before"]),
      el("span", {}, [el("b", { text: "Click the intensity lane" }), " to add a point; drag it; Delete removes it"]),
      el("span", {}, [el("b", { text: "Click an object" }), " to pin a still at that cut"]),
    ]);
    this.root.append(head, this.stage, this.insp, this.foot);
    document.body.append(this.root);
    if (!this.board) {
      this.stage.append(el("div", { class: "empty" }, [
        el("div", { text: "The timeline has no song yet. Plan it once: the analysis and the storyboard run, no morph renders." }),
        el("button", { class: "primary", text: "Plan the song (no GPU)", onclick: () => this.plan() }),
      ]));
    }
    this.canvas.addEventListener("wheel", (e) => this.wheel(e), { passive: false });
    this.canvas.addEventListener("mousedown", (e) => this.down(e));
    this.canvas.addEventListener("dblclick", (e) => this.dbl(e));
    this.onMove = (e) => this.move(e);
    this.onUp = (e) => this.up(e);
    window.addEventListener("mousemove", this.onMove);
    window.addEventListener("mouseup", this.onUp);
    if (song.path) {
      this.audio = new Audio(`/xenoform_nodes/song?path=${encodeURIComponent(song.path)}`);
      this.audio.preload = "auto";
      this.audio.addEventListener("ended", () => { this.playBtn.textContent = "Play"; });
    }
    this.root.focus();
  }

  close(ask) {
    if (ask && this.dirty() && !confirm("Leave the Morph Timeline without saving the edits?")) return;
    this.stopPlay();
    window.removeEventListener("keydown", this.onKey, true);
    window.removeEventListener("resize", this.onResize);
    window.removeEventListener("mousemove", this.onMove);
    window.removeEventListener("mouseup", this.onUp);
    this.root.remove();
    if (EDITOR === this) EDITOR = null;
  }

  save(close) {
    writeEdits(this.node, this.edits);
    this.saved = JSON.stringify(this.edits);
    if (close) this.close(false);
    else this.render();
  }

  async plan() {
    this.save(false);
    this.status = "Planning: the strip refreshes when the node has run.";
    this.render();
    try {
      await app.queuePrompt(0, 1, [String(this.node.id)]);  // this node and what feeds it: no morph is rendered
    } catch (e) {
      this.status = "Could not queue this node alone here: right-click it and choose Queue Selected Output Nodes.";
      this.render();
    }
  }

  refresh(view) {
    const first = !this.board;
    this.view = view;
    this.board = view.board;
    this.inspKey = null;
    if (first) this.fit();
    const empty = this.stage.querySelector(".empty");
    if (empty) empty.remove();
    if (!this.dirty()) {
      this.edits = readEdits(this.node, this.board);
      this.saved = JSON.stringify(this.edits);
    }
    this.status = "";
    if (!this.duration()) return;
    if (!this.audio && this.song().path) this.audio = new Audio(`/xenoform_nodes/song?path=${encodeURIComponent(this.song().path)}`);
    this.render();
  }

  // ---- playback
  togglePlay() {
    if (!this.audio) return;
    if (this.audio.paused) {
      this.audio.currentTime = this.playhead || 0;
      this.audio.play().catch(() => {});
      this.playBtn.textContent = "Pause";
      const tick = () => {
        if (!this.audio || this.audio.paused || !this.root.isConnected) return;
        this.playhead = this.audio.currentTime;
        const w = this.canvas.clientWidth - GUTTER;
        if (this.x(this.playhead) > GUTTER + w * 0.9) this.t0 = this.playhead - (w * 0.1) / this.pps;
        this.render();
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    } else {
      this.stopPlay();
    }
  }
  stopPlay() {
    if (this.audio && !this.audio.paused) this.audio.pause();
    if (this.playBtn) this.playBtn.textContent = "Play";
  }

  // ---- input
  key(e) {
    if (!this.root.isConnected) return;
    const tag = (e.target?.tagName || "").toLowerCase();
    if (tag === "input") return;
    e.stopPropagation();
    if (e.key === "Escape") { if (this.picker) this.closePicker(); else this.close(true); e.preventDefault(); }
    else if (e.key === " ") { this.togglePlay(); e.preventDefault(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { this.doUndo(); e.preventDefault(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { this.save(true); e.preventDefault(); }
    else if (e.key === "Delete" || e.key === "Backspace") { this.deleteSel(); e.preventDefault(); }
  }
  doUndo() {
    const last = this.undo.pop();
    if (last) { this.edits = JSON.parse(last); this.render(); }
  }
  deleteSel() {
    if (!this.sel) return;
    if (this.sel.kind === "shot") this.join(this.sel.index);
    else if (this.sel.kind === "point") { const k = this.sel.index; this.change((e) => { e.intensity.splice(k, 1); }); this.sel = null; }
    else if (this.sel.kind === "slot") this.unpin(this.sel.index);
  }
  pos(e) {
    const r = this.canvas.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }
  wheel(e) {
    e.preventDefault();
    const { x } = this.pos(e);
    if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
      this.t0 += ((e.shiftKey ? e.deltaY : e.deltaX) || 0) / this.pps;
    } else {
      const at = this.t(x);
      this.pps *= Math.exp(-e.deltaY * 0.0015);
      this.clampView();
      this.t0 = at - (x - GUTTER) / this.pps;
    }
    this.clampView();
    this.render();
  }
  cutNear(x) {
    const cuts = this.cuts();
    let best = -1, dist = 7;
    cuts.forEach((c, k) => { const d = Math.abs(this.x(c) - x); if (d < dist) { dist = d; best = k; } });
    return best;
  }
  shotIndexAt(t) {
    const b = this.bounds();
    for (let i = 0; i < b.length - 1; i++) if (t >= b[i] && t < b[i + 1]) return i;
    return b.length - 2;
  }
  down(e) {
    if (!this.board || e.button !== 0) return;
    this.closePicker();
    const { x, y } = this.pos(e);
    const lane = this.laneAt(y);
    const t = this.t(x);
    if (x < GUTTER) return;
    if (lane === "shots") {
      const k = this.cutNear(x);
      if (k >= 0) {
        this.undo.push(JSON.stringify(this.edits));
        this.drag = { kind: "cut", k, from: this.cuts()[k], cuts: this.cuts() };
        return;
      }
      this.sel = { kind: "shot", index: this.shotIndexAt(t) };
      this.render();
      return;
    }
    if (lane === "intensity") {
      const r = this.laneRect("intensity");
      const pts = this.edits.intensity || [];
      const hit = pts.findIndex(([pt, pv]) => Math.abs(this.x(pt) - x) < 7 && Math.abs(r.y + 6 + (1 - pv) * (r.h - 12) - y) < 7);
      if (hit >= 0) {
        this.undo.push(JSON.stringify(this.edits));
        this.sel = { kind: "point", index: hit };
        this.drag = { kind: "point", index: hit };
      } else {
        const v = clamp(1 - (y - r.y - 6) / (r.h - 12), 0, 1);
        const at = this.snap(t, e);
        this.change((ed) => { ed.intensity = [...(ed.intensity || []), [Number(at.toFixed(4)), Number(v.toFixed(3))]].sort((a, b) => a[0] - b[0]); });
        const idx = this.edits.intensity.findIndex((p) => Math.abs(p[0] - at) < 1e-4);
        this.sel = { kind: "point", index: idx };
        this.drag = { kind: "point", index: idx };
      }
      this.render();
      return;
    }
    if (lane === "objects") {
      const b = this.bounds();
      let slot = -1, dist = 30;
      b.forEach((bt, k) => { const d = Math.abs(this.x(bt) - x); if (d < dist) { dist = d; slot = k; } });
      if (slot >= 0) { this.sel = { kind: "slot", index: slot }; this.openPicker(slot, x, y); this.render(); }
      return;
    }
    // the ruler, the sections, the wave, the beats: seek and pan
    this.playhead = clamp(t, 0, this.duration());
    if (this.audio && !this.audio.paused) this.audio.currentTime = this.playhead;
    this.drag = { kind: "pan", x, t0: this.t0, moved: false };
    this.render();
  }
  move(e) {
    if (!this.drag) {
      if (!this.board || !this.canvas.isConnected) return;
      const { x, y } = this.pos(e);
      const lane = this.laneAt(y);
      this.canvas.style.cursor = lane === "shots" && this.cutNear(x) >= 0 ? "ew-resize" : lane === "intensity" ? "crosshair"
        : lane === "objects" ? "pointer" : lane && x > GUTTER ? "grab" : "default";
      return;
    }
    const { x, y } = this.pos(e);
    if (this.drag.kind === "pan") {
      this.t0 = this.drag.t0 - (x - this.drag.x) / this.pps;
      this.clampView();
      this.render();
    } else if (this.drag.kind === "cut") {
      const cuts = this.drag.cuts.slice();
      const k = this.drag.k;
      const lo = (k > 0 ? cuts[k - 1] : 0) + 0.25, hi = (k + 1 < cuts.length ? cuts[k + 1] : this.duration()) - 0.25;
      let t = this.snap(this.t(x), e);
      if (t < lo || t > hi) t = clamp(this.t(x), lo, hi);
      cuts[k] = Number(t.toFixed(4));
      const old = this.cuts()[k];
      this.rekey(old, cuts[k]);
      this.edits.cuts = cuts;
      this.render();
    } else if (this.drag.kind === "point") {
      const r = this.laneRect("intensity");
      const pts = this.edits.intensity;
      const p = pts[this.drag.index];
      if (!p) return;
      p[0] = Number(clamp(this.snap(this.t(x), e), 0, this.duration()).toFixed(4));
      p[1] = Number(clamp(1 - (y - r.y - 6) / (r.h - 12), 0, 1).toFixed(3));
      this.render();
    }
  }
  up() {
    if (!this.drag) return;
    if (this.drag.kind === "point") {
      const p = this.edits.intensity[this.drag.index];
      this.edits.intensity.sort((a, b) => a[0] - b[0]);
      this.sel = { kind: "point", index: this.edits.intensity.indexOf(p) };
    }
    if (this.drag?.kind === "cut" && JSON.stringify(this.drag.cuts) === JSON.stringify(this.cuts())) this.undo.pop();
    this.drag = null;
    this.render();
  }
  dbl(e) {
    if (!this.board) return;
    const { x, y } = this.pos(e);
    const lane = this.laneAt(y);
    if (lane === "shots") {
      this.split(this.snap(this.t(x), e));
    } else if (lane === "intensity" && this.sel?.kind === "point") {
      const p = this.edits.intensity[this.sel.index];
      const got = prompt("Intensity at this point, 0 to 1", String(p[1]));
      if (got != null && !Number.isNaN(Number(got))) this.change((ed) => { ed.intensity[this.sel.index][1] = clamp(Number(got), 0, 1); });
    }
  }

  // ---- the object picker
  openPicker(slot, x, y) {
    this.closePicker();
    const b = this.bounds();
    const current = this.stillAt(slot);
    const box = el("div", { class: "picker" });
    box.append(el("div", { class: "head" }, [
      el("span", { text: `The still the chain lands on at ${clock(b[slot])}` }),
      el("button", { class: "chip", text: "Unpin", onclick: () => { this.unpin(slot); this.closePicker(); } }),
    ]));
    for (const row of this.board.pool || []) {
      const opt = el("div", { class: `opt${current?.file === row.file ? " on" : ""}`, title: row.file, onclick: () => { this.pin(slot, row.file); this.closePicker(); } }, [
        el("img", { src: `/xenoform_nodes/still?file=${encodeURIComponent(row.file)}&w=176`, loading: "lazy", alt: row.noun }),
        el("span", { text: row.noun }),
      ]);
      box.append(opt);
    }
    const stageW = this.stage.clientWidth, stageH = this.stage.clientHeight;
    box.style.left = `${clamp(x - 280, 8, Math.max(8, stageW - 570))}px`;
    box.style.top = `${clamp(y - 380, 8, Math.max(8, stageH - 370))}px`;
    this.stage.append(box);
    this.picker = box;
  }
  closePicker() { if (this.picker) { this.picker.remove(); this.picker = null; } }
  pin(slot, file) {
    const t = this.bounds()[slot];
    this.change((e) => { e.pins = (e.pins || []).filter((p) => this.slotOf(p[0]) !== slot); e.pins.push([Number(t.toFixed(4)), file]); });
  }
  unpin(slot) { this.change((e) => { e.pins = (e.pins || []).filter((p) => this.slotOf(p[0]) !== slot); }); }
  slotOf(t) {
    const b = this.bounds();
    let best = 0;
    b.forEach((x, k) => { if (Math.abs(x - t) < Math.abs(b[best] - t)) best = k; });
    return best;
  }
  thumb(file) {
    if (!file) return null;
    if (this.thumbs.has(file)) return this.thumbs.get(file);
    const img = new Image();
    img.onload = () => this.render();
    img.src = `/xenoform_nodes/still?file=${encodeURIComponent(file)}&w=120`;
    this.thumbs.set(file, img);
    return img;
  }

  // ---- drawing
  render() {
    if (!this.root?.isConnected) return;
    const song = this.song();
    const n = this.board ? this.shotCount() : 0;
    const edited = this.edits.cuts != null || Object.keys(this.edits.shots || {}).length || (this.edits.intensity || []).length || (this.edits.pins || []).length;
    this.meta.textContent = this.board
      ? `${song.name} · ${clock(this.duration())} · ${Math.round(song.tempo || 0)} BPM · ${song.drop != null ? `drop at ${clock(song.drop)} · ` : ""}${n} shots on the beat · ${this.board.vibe_name}${edited ? " · edited" : ""}${this.dirty() ? " (not saved)" : ""}${this.status ? ` · ${this.status}` : ""}`
      : "No song yet";
    this.drawCanvas();
    // the inspector is DOM: rebuilt only when what it shows changes, or a click on one of its chips (mousedown,
    // mouseup, click) would land on a button replaced in between, and a playing song would rebuild it every frame
    const key = JSON.stringify([this.sel, this.edits, this.board ? this.board.shots.length : 0, this.board?.notes, this.view?.board?.edits]);
    if (key !== this.inspKey) {
      this.inspKey = key;
      this.drawInspector();
    }
  }

  drawCanvas() {
    const c = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, H = c.clientHeight;
    if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
    const g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.fillStyle = "#0b0b0f";
    g.fillRect(0, 0, W, H);
    if (!this.board || !this.duration()) return;
    this.clampView();
    const song = this.song();
    const d = this.duration();
    const xa = this.x(0), xb = this.x(d);
    const vis = (t) => this.x(t) >= GUTTER - 2 && this.x(t) <= W + 2;
    g.font = "11px system-ui, sans-serif";
    g.textBaseline = "middle";
    // lane backgrounds and names
    for (const [name, h] of this.lanes()) {
      const r = this.laneRect(name);
      g.fillStyle = name === "shots" ? "#141419" : "#0f0f14";
      g.fillRect(GUTTER, r.y + 1, W - GUTTER, h - 2);
      if (LABELS[name]) { g.fillStyle = "#74747f"; g.fillText(LABELS[name], 10, r.y + h / 2); }
    }
    g.save();
    g.beginPath();
    g.rect(GUTTER, 0, W - GUTTER, H);
    g.clip();
    // ruler: seconds and bars
    const rr = this.laneRect("ruler");
    const step = [0.5, 1, 2, 5, 10, 15, 30, 60].find((s) => s * this.pps > 70) || 60;
    g.fillStyle = "#a9a9b6";
    for (let t = Math.floor(this.t0 / step) * step; t <= d; t += step) {
      if (!vis(t)) continue;
      g.fillRect(this.x(t), rr.y + rr.h - 6, 1, 6);
      g.fillText(clock(t).replace(/\.00$/, ""), this.x(t) + 3, rr.y + rr.h / 2 - 2);
    }
    // sections, colour-coded, the drop flagged
    const sr = this.laneRect("sections");
    for (const s of song.sections || []) {
      const a = this.x(s.start), b = this.x(s.end);
      g.fillStyle = `hsla(${hueOf(s.label)},55%,42%,.75)`;
      g.fillRect(a, sr.y + 2, Math.max(1, b - a - 1), sr.h - 4);
      if (b - a > 34) { g.fillStyle = "#ececf1"; g.fillText(s.label, a + 5, sr.y + sr.h / 2); }
    }
    // the wave: the song's loudness, mirrored
    const wr = this.laneRect("wave");
    const wave = song.wave || [];
    const wf = song.wave_fps || 12;
    if (wave.length) {
      g.fillStyle = "rgba(169,169,182,.55)";
      const mid = wr.y + wr.h / 2;
      const i0 = Math.max(0, Math.floor(this.t0 * wf)), i1 = Math.min(wave.length, Math.ceil(this.t(W) * wf) + 1);
      const px = Math.max(1, this.pps / wf);
      for (let i = i0; i < i1; i++) {
        const amp = Math.max(0.5, wave[i] * (wr.h / 2 - 3));
        g.fillRect(this.x(i / wf), mid - amp, Math.max(1, px - (px > 3 ? 1 : 0)), amp * 2);
      }
    }
    // beats, bars heavier
    const br = this.laneRect("beats");
    const beats = this.beats();
    const showBeats = this.pps * (song.beat_s || 0.5) > 3;
    beats.forEach((b, k) => {
      if (!vis(b)) return;
      const bar = k % 4 === 0;
      if (!bar && !showBeats) return;
      g.fillStyle = bar ? "rgba(236,236,241,.75)" : "rgba(236,236,241,.3)";
      g.fillRect(this.x(b), br.y + (bar ? 2 : 8), 1, br.h - (bar ? 4 : 10));
    });
    // the drop, through every lane below the ruler
    if (song.drop != null) {
      const x = this.x(song.drop);
      g.fillStyle = "rgba(255,100,100,.9)";
      g.fillRect(x - 1, sr.y, 2, H - sr.y);
      g.fillStyle = "#ff6464";
      g.fillText("drop", x + 4, br.y + br.h / 2);
    }
    // shots: blocks snapped to the beats
    const hr = this.laneRect("shots");
    const b = this.bounds();
    for (let i = 0; i < b.length - 1; i++) {
      const s = this.shotAt(i);
      const a = this.x(s.start), e = this.x(s.end);
      if (e < GUTTER || a > W) continue;
      const on = this.sel?.kind === "shot" && this.sel.index === i;
      g.fillStyle = `hsla(${hueOf(s.section)},38%,${on ? 46 : 32}%,1)`;
      g.fillRect(a + 1, hr.y + 4, Math.max(1, e - a - 2), hr.h - 8);
      if (!s.planned) {  // a cut not planned yet: hatched until the node runs again
        g.strokeStyle = "rgba(255,255,255,.18)";
        for (let hx = a - hr.h; hx < e; hx += 7) { g.beginPath(); g.moveTo(Math.max(a + 1, hx), hr.y + hr.h - 4); g.lineTo(Math.min(e - 1, hx + hr.h - 8), hr.y + 4); g.stroke(); }
      }
      if (on) { g.strokeStyle = "#7c6cff"; g.lineWidth = 2; g.strokeRect(a + 1, hr.y + 4, Math.max(1, e - a - 2), hr.h - 8); g.lineWidth = 1; }
      if (e - a > 26) {
        g.fillStyle = "#ececf1";
        g.fillText(String(i), a + 5, hr.y + 15);
        if (e - a > 70) {
          g.fillStyle = "#a9a9b6";
          const tag = (s.hold ? "hold" : s.style) + (s.timing !== "smooth" ? ` · ${s.timing === "beat" ? "on the beat" : "snap"}` : "");
          g.fillText(tag + (s.styleSet || s.timingSet ? " *" : ""), a + 5, hr.y + 32);
          if (e - a > 120) { g.fillStyle = "#74747f"; g.fillText(`${s.seconds.toFixed(2)} s`, a + 5, hr.y + 48); }
        }
      }
    }
    for (const t of this.cuts()) { g.fillStyle = "rgba(236,236,241,.85)"; g.fillRect(this.x(t) - 1, hr.y + 2, 2, hr.h - 4); }
    // intensity: the points, or the plan's per-shot values as a step line
    const ir = this.laneRect("intensity");
    const yv = (v) => ir.y + 6 + (1 - v) * (ir.h - 12);
    g.strokeStyle = "rgba(255,255,255,.07)";
    g.beginPath(); g.moveTo(xa, yv(0.5)); g.lineTo(xb, yv(0.5)); g.stroke();
    const pts = (this.edits.intensity || []).slice().sort((p, q) => p[0] - q[0]);
    if (pts.length) {
      g.strokeStyle = "#f2b14a"; g.lineWidth = 2; g.beginPath();
      g.moveTo(xa, yv(pts[0][1]));
      for (const [pt, pv] of pts) g.lineTo(this.x(pt), yv(pv));
      g.lineTo(xb, yv(pts[pts.length - 1][1])); g.stroke(); g.lineWidth = 1;
      (this.edits.intensity || []).forEach(([pt, pv], k) => {
        const on = this.sel?.kind === "point" && this.sel.index === k;
        g.fillStyle = on ? "#ececf1" : "#f2b14a";
        g.beginPath(); g.arc(this.x(pt), yv(pv), on ? 6 : 4.5, 0, Math.PI * 2); g.fill();
      });
    } else {
      g.strokeStyle = "rgba(242,177,74,.55)"; g.beginPath();
      for (let i = 0; i < b.length - 1; i++) {
        const v = this.shotAt(i).intensity;
        if (v == null) continue;
        g.moveTo(this.x(b[i]), yv(v)); g.lineTo(this.x(b[i + 1]), yv(v));
      }
      g.stroke();
      g.fillStyle = "#74747f";
      g.fillText("the plan's intensity: click to set your own", GUTTER + 8, ir.y + ir.h - 9);
    }
    // objects: the still the chain lands on at each cut
    const or = this.laneRect("objects");
    for (let k = 0; k < b.length; k++) {
      const x = this.x(b[k]);
      if (x < GUTTER - 60 || x > W + 60) continue;
      const still = this.stillAt(k);
      const on = this.sel?.kind === "slot" && this.sel.index === k;
      const tw = 62, th = 35, tx = clamp(x - tw / 2, this.x(0), this.x(d) - tw), ty = or.y + 4;
      const img = this.thumb(still?.file);
      g.fillStyle = "#23232c"; g.fillRect(tx, ty, tw, th);
      if (img && img.complete && img.naturalWidth) g.drawImage(img, tx, ty, tw, th);
      g.strokeStyle = still?.pinned ? "#7c6cff" : on ? "#ececf1" : "rgba(255,255,255,.15)";
      g.lineWidth = still?.pinned || on ? 2 : 1; g.strokeRect(tx, ty, tw, th); g.lineWidth = 1;
      if (still?.pinned) { g.fillStyle = "#7c6cff"; g.beginPath(); g.arc(tx + tw - 5, ty + 5, 4, 0, Math.PI * 2); g.fill(); }
      const gap = k + 1 < b.length ? this.x(b[k + 1]) - x : 999;
      if (gap > 70 || k === b.length - 1) { g.fillStyle = "#a9a9b6"; g.fillText((still?.noun || "").slice(0, 18), tx, ty + th + 9); }
    }
    // the playhead
    if (this.playhead > 0 || (this.audio && !this.audio.paused)) {
      g.fillStyle = "#3ccf8e";
      g.fillRect(this.x(this.playhead) - 1, 0, 2, H);
    }
    g.restore();
  }

  drawInspector() {
    const box = this.insp;
    box.textContent = "";
    if (!this.board) return;
    const notes = [...(this.board.notes || [])];
    if (this.sel?.kind !== "shot") {
      const pts = (this.edits.intensity || []).length, pins = (this.edits.pins || []).length;
      box.append(el("div", { class: "who" }, [
        el("b", { text: "Select a shot" }), " to give it its own style, timing, hold or seed. ",
        `${pts} intensity point${pts === 1 ? "" : "s"}, ${pins} pinned object${pins === 1 ? "" : "s"}.`,
      ]));
      if (notes.length) box.append(el("div", { class: "note", text: notes.join(" ") }));
      return;
    }
    const i = this.sel.index;
    if (i >= this.shotCount()) { this.sel = null; return this.drawInspector(); }
    const s = this.shotAt(i);
    const beatS = this.song().beat_s || 0.5;
    const barOf = (t) => { const beats = this.beats(); const k = beats.findIndex((b) => b >= t - 1e-3); const n = k < 0 ? beats.length : k; return `bar ${Math.floor(n / 4) + 1}.${(n % 4) + 1}`; };
    box.append(el("div", { class: "who" }, [
      el("b", { text: `Shot ${i}` }), ` · ${clock(s.start)} to ${clock(s.end)} (${barOf(s.start)}) · ${s.seconds.toFixed(2)} s, ${s.frames} frames, ${(s.seconds / beatS).toFixed(1)} beats`,
      el("br"), `${s.from} into ${s.to}${s.section ? ` · ${s.section}` : ""}${s.intensity != null ? ` · intensity ${s.intensity.toFixed(2)}` : ""}${s.planned ? "" : " · planned on the next run"}`,
    ]));
    const chips = (label, options, current, set, labels) => el("div", { class: "chips" }, [el("span", { text: label }), ...options.map((o) =>
      el("button", { class: `chip${current === o ? " on" : ""}`, text: (labels || {})[o] || o, onclick: () => set(o) }))]);
    const styles = ["plan", ...(this.view?.styles || ["melt", "shatter", "bloom", "spin", "fold"])];
    box.append(chips("Style", styles, s.styleSet ? s.style : "plan", (o) => this.setShot(i, { style: o === "plan" ? null : o }),
      { ...(this.view?.style_labels || {}), plan: `Plan (${s.planStyle})` }));
    box.append(chips("Timing", ["plan", "smooth", "beat", "snap"], s.timingSet ? s.timing : "plan", (o) => this.setShot(i, { timing: o === "plan" ? null : o }),
      { plan: "Plan", smooth: "Smooth", beat: "On the beat", snap: "Snap" }));
    box.append(el("div", { class: "chips" }, [
      el("button", { class: `chip${s.hold ? " on" : ""}`, text: s.hold ? "Held on the first still" : "Hold", title: "The shot shows its first still and does not morph", onclick: () => this.setShot(i, { hold: s.hold ? null : true }) }),
    ]));
    const seed = el("input", { type: "number", value: String(s.seed ?? ""), title: "This morph's seed" });
    seed.addEventListener("change", () => this.setShot(i, { seed: seed.value === "" ? null : Math.round(Number(seed.value)) }));
    box.append(el("div", { class: "chips" }, [el("span", { text: "Seed" }), seed]));
    box.append(el("div", { class: "chips" }, [
      el("button", { class: "chip", text: "Split on the middle beat", onclick: () => this.split(this.snap((s.start + s.end) / 2)) }),
      el("button", { class: "chip", text: i > 0 ? "Join to the shot before" : "Join to the next", onclick: () => this.join(i) }),
    ]));
    if (notes.length) box.append(el("div", { class: "note", text: notes.join(" ") }));
  }
}

// ------------------------------------------------------------------------------------------------ the Assemble's inputs

function tidyMorphInputs(node) {
  // morph_1 .. morph_16: the connected ones plus one free socket, so the node is not sixteen sockets tall
  try {
    const morphs = (node.inputs || []).map((inp, slot) => ({ inp, slot })).filter(({ inp }) => /^morph_\d+$/.test(inp.name));
    let lastLinked = 0;
    for (const { inp } of morphs) if (inp.link != null) lastLinked = Math.max(lastLinked, Number(inp.name.split("_")[1]));
    const keep = Math.min(MAX_MORPHS, lastLinked + 1);
    for (let k = morphs.length - 1; k >= 0; k--) {
      const { inp, slot } = morphs[k];
      if (Number(inp.name.split("_")[1]) > keep && inp.link == null) node.removeInput(slot);
    }
    const names = new Set((node.inputs || []).map((i) => i.name));
    for (let k = 1; k <= keep; k++) if (!names.has(`morph_${k}`)) node.addInput(`morph_${k}`, "IMAGE");
    node.setSize?.([node.size[0], Math.max(node.size[1], node.computeSize()[1])]);
  } catch (e) { /* the frontend keeps every socket then */ }
}

// ------------------------------------------------------------------------------------------------ registration

app.registerExtension({
  name: "xenoform.morphTimeline",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!TEXT_NODES.has(nodeData.name)) return;
    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);
      showText(this, message?.text);
      if (nodeData.name === TIMELINE && message?.xenoform_board?.length) {
        try {
          this._xf = JSON.parse(message.xenoform_board[0]);
          if (EDITOR && EDITOR.node === this) EDITOR.refresh(this._xf);
        } catch (e) { console.warn("Xenoform: the timeline's board did not parse", e); }
        this.setDirtyCanvas?.(true, true);
      }
    };
    if (nodeData.name === TIMELINE) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated?.apply(this, arguments);
        hideWidget(this, "timeline");
        const open = this.addWidget("button", "Open the Morph Timeline", null, () => openEditor(this), { serialize: false });
        try { open.serialize = false; } catch (e) { /* the option above says it */ }
        this.setSize?.([Math.max(this.size[0], 300), Math.max(this.size[1], 120)]);
        return r;
      };
      const onConfigure = nodeType.prototype.onConfigure;
      nodeType.prototype.onConfigure = function () {
        const r = onConfigure?.apply(this, arguments);
        hideWidget(this, "timeline");
        return r;
      };
      const onDrawForeground = nodeType.prototype.onDrawForeground;
      nodeType.prototype.onDrawForeground = function (ctx) {
        onDrawForeground?.apply(this, arguments);
        drawMini(this, ctx);
      };
    }
    if (nodeData.name === ASSEMBLE) {
      const onNodeCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        const r = onNodeCreated?.apply(this, arguments);
        setTimeout(() => tidyMorphInputs(this), 0);
        return r;
      };
      const onConfigure = nodeType.prototype.onConfigure;
      nodeType.prototype.onConfigure = function () {
        const r = onConfigure?.apply(this, arguments);
        setTimeout(() => tidyMorphInputs(this), 0);
        return r;
      };
      const onConnectionsChange = nodeType.prototype.onConnectionsChange;
      nodeType.prototype.onConnectionsChange = function () {
        const r = onConnectionsChange?.apply(this, arguments);
        setTimeout(() => tidyMorphInputs(this), 0);
        return r;
      };
    }
  },
});
